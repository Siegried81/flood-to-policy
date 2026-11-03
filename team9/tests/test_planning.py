"""Shelter planning scenario: demand origins (Python) and the browser allocator planning/alloc.js (run with Node).
The allocation optimum is checked independently with a linear program (scipy / HiGHS)."""
import json
import shutil
import subprocess
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import shapely

from planning import demand as dm

ALLOC = Path(__file__).resolve().parents[1] / "planning" / "alloc.js"
M = dm.METRIC_CRS
node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def run_js(origins, facilities, cands, max_dist):
    code = f"""const A = require({json.dumps(str(ALLOC))}); const i = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const r = A.run(i.o, i.f, i.c, i.d);
console.log(JSON.stringify({{total: r.total, flows: r.flows, byOrigin: Array.from(r.byOrigin), byFacility: Array.from(r.byFacility),
  gaps: r.gaps, gapTotals: r.gapTotals}}));"""
    out = subprocess.run(["node", "-e", code], input=json.dumps({"o": origins, "f": facilities, "c": cands, "d": max_dist}),
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def check_constraints(origins, facilities, res, max_dist, eps=1e-6):
    """Demand conservation, capacity limits, distance limit, no duplicate origin-facility pair."""
    pairs = [(f["o"], f["f"]) for f in res["flows"]]
    assert len(pairs) == len(set(pairs)), "duplicate allocation pair"
    for f in res["flows"]:
        o, k = origins[f["o"]], facilities[f["f"]]
        assert f["amount"] > 0 and np.hypot(o["x"] - k["x"], o["y"] - k["y"]) <= max_dist + eps
    by_o = np.zeros(len(origins)); by_f = np.zeros(len(facilities))
    for f in res["flows"]:
        by_o[f["o"]] += f["amount"]; by_f[f["f"]] += f["amount"]
    assert np.allclose(by_o, res["byOrigin"]) and np.allclose(by_f, res["byFacility"])
    assert (by_o <= np.array([o["demand"] for o in origins]) + eps).all(), "origin assigned more than its residents"
    assert (by_f <= np.array([k["cap"] for k in facilities]) + eps).all(), "facility over capacity"
    assert abs(by_o.sum() - res["total"]) < eps
    unassigned = sum(o["demand"] for o in origins) - res["total"]
    assert abs(sum(res["gapTotals"].values()) - unassigned) < 1e-5, "assigned + unassigned != demand"


def lp_optimum(origins, facilities, max_dist):
    """Independent check: maximise sum of flows s.t. origin and capacity limits, edges only within max_dist."""
    from scipy.optimize import linprog
    edges = [(i, k) for i, o in enumerate(origins) for k, f in enumerate(facilities)
             if f["cap"] > 0 and np.hypot(o["x"] - f["x"], o["y"] - f["y"]) <= max_dist]
    if not edges:
        return 0.0
    A = np.zeros((len(origins) + len(facilities), len(edges)))
    for e, (i, k) in enumerate(edges):
        A[i, e] = 1; A[len(origins) + k, e] = 1
    b = [o["demand"] for o in origins] + [f["cap"] for f in facilities]
    r = linprog(-np.ones(len(edges)), A_ub=A, b_ub=b, bounds=(0, None), method="highs")
    assert r.success
    return -r.fun


# --------------------------------------------------------------------------- hand-checkable example
# Shelter S (100 places) at 0 m, shelter T (50 places) at 5,000 m, distance limit 3,000 m.
# A (80 residents) at -1,000 m reaches only S. B (70) at 2,500 m reaches S and T (both 2,500 m away).
# Best: A 80 -> S, B 20 -> S + 50 -> T = 150 (everyone). Filling S with B first (B 70 -> S, A 30 -> S) leaves 50
# of A unassigned while T stays empty: 100 only. C (10) at 20 km has nothing in reach; D (5) at 40 km has only a
# school with unknown capacity in reach; E (7) at 60 km has only a facility marked unavailable.
HAND_O = [{"x": -1000, "y": 0, "demand": 80}, {"x": 2500, "y": 0, "demand": 70}, {"x": 20000, "y": 0, "demand": 10},
          {"x": 40000, "y": 0, "demand": 5}, {"x": 60000, "y": 0, "demand": 7}]
HAND_F = [{"x": 0, "y": 0, "cap": 100}, {"x": 5000, "y": 0, "cap": 50}]
HAND_C = [{"x": 0, "y": 0, "state": "places"}, {"x": 5000, "y": 0, "state": "places"},
          {"x": 41000, "y": 0, "state": "unknown"}, {"x": 61000, "y": 0, "state": "unavailable"}]


@node
def test_hand_example_competing_demand():
    r = run_js(HAND_O, HAND_F, HAND_C, 3000)
    check_constraints(HAND_O, HAND_F, r, 3000)
    assert r["total"] == pytest.approx(150)
    assert r["byOrigin"][:2] == pytest.approx([80, 70]) and r["byFacility"] == pytest.approx([100, 50])
    flows = {(f["o"], f["f"]): f["amount"] for f in r["flows"]}
    assert flows == pytest.approx({(0, 0): 80, (1, 0): 20, (1, 1): 50})
    assert r["gaps"] == [None, None, "no_candidate", "capacity_unknown", "unavailable"]
    assert r["gapTotals"] == pytest.approx({"capacity_full": 0, "capacity_unknown": 5, "unavailable": 7, "no_candidate": 10})


@node
def test_hand_example_shortage_and_recalculation():
    # T removed (as if marked unavailable): S is shared by A and B; 150 residents compete for 100 places
    f = [HAND_F[0], {**HAND_F[1], "cap": 0}]
    r = run_js(HAND_O[:2], f, HAND_C[:1], 3000)
    check_constraints(HAND_O[:2], f, r, 3000)
    assert r["total"] == pytest.approx(100) and r["byFacility"][0] == pytest.approx(100)
    assert r["gapTotals"]["capacity_full"] == pytest.approx(50)
    # a shorter distance limit cuts B off: B is now a distance gap, A still gets 80
    r = run_js(HAND_O[:2], HAND_F, HAND_C[:2], 2000)
    assert r["total"] == pytest.approx(80) and r["gaps"] == [None, "no_candidate"]


@node
@pytest.mark.parametrize("seed", range(12))
def test_random_instances_match_lp_optimum(seed):
    rng = np.random.default_rng(seed)
    n_o, n_f = rng.integers(5, 60), rng.integers(1, 25)
    o = [{"x": float(x), "y": float(y), "demand": float(d)} for x, y, d in
         zip(rng.uniform(0, 30000, n_o), rng.uniform(0, 30000, n_o), rng.exponential(40, n_o))]
    f = [{"x": float(x), "y": float(y), "cap": float(c)} for x, y, c in
         zip(rng.uniform(0, 30000, n_f), rng.uniform(0, 30000, n_f), rng.choice([0, 20, 50, 150, 400], n_f))]
    c = [{"x": k["x"], "y": k["y"], "state": "places" if k["cap"] > 0 else "unknown"} for k in f]
    d = float(rng.choice([2000, 5000, 10000]))
    r = run_js(o, f, c, d)
    check_constraints(o, f, r, d)
    assert r["total"] == pytest.approx(lp_optimum(o, f, d), rel=1e-7, abs=1e-6)


# --------------------------------------------------------------------------- demand origins
def test_demand_split_conserves_and_places_origins():
    # one flood polygon (300 residents) across two hexagon-like squares: left has 3 residential buildings, right 1
    flood = gpd.GeoDataFrame({"residents": [300.0, 12.0, 0.0]},
                             geometry=[shapely.box(0, 0, 800, 100), shapely.box(5000, 0, 5100, 100), shapely.box(9000, 0, 9100, 100)], crs=M)
    hexes = gpd.GeoDataFrame({"q": [0, 1], "r": [0, 0], "n_res": [3, 1], "country": ["DEU", "BEL"]},
                             geometry=[shapely.box(0, -200, 400, 200), shapely.box(400, -200, 800, 200)], crs=M)
    o = dm.build_demand(flood, hexes)
    assert dm.check_demand(o, flood) == []
    by = o.set_index("origin_id")["residents"]
    assert by["h0_0"] == pytest.approx(225) and by["h1_0"] == pytest.approx(75)   # 3:1 split, equal area shares
    assert by["p1"] == pytest.approx(12)                                           # no residential building: kept whole
    assert len(o) == 3 and o.set_index("origin_id").at["h1_0", "country"] == "BEL"
