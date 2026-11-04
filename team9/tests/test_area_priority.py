"""Area planning priority (planning/priority.js, run with Node) against independently computed examples, and the
fixed 400 m hexagon summary of the demand origins (planning/demand.py) on the real cached data."""
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from planning import demand as dm

ROOT = Path(__file__).resolve().parents[1]
PRIO = ROOT / "planning" / "priority.js"
node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def run_js(P, U, p99, wE, wG):
    code = f"""const A = require({json.dumps(str(PRIO))}); const i = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let r; try {{ r = A.score(i.P.map(p => ({{P: p}})), i.U, i.p99, i.wE, i.wG); }} catch (e) {{ r = {{error: e.message}}; }}
console.log(JSON.stringify(r));"""
    out = subprocess.run(["node", "-e", code], input=json.dumps({"P": P, "U": U, "p99": p99, "wE": wE, "wG": wG}),
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def by_hand(P, U, p99, wE, wG):
    """Independent re-implementation of the documented formulas."""
    tot = wE + wG
    out = []
    for p, u in zip(P, U):
        if p <= 0:
            out.append(None)
            continue
        E = 100 * min(1.0, math.log(1 + p) / math.log(1 + p99))
        G = 100 * u / p
        out.append((E, G, wE / tot * E + wG / tot * G))
    return out


@node
@pytest.mark.parametrize("wE, wG", [(50, 50), (100, 0), (0, 100), (30, 70), (1, 3)])
def test_scores_match_hand_calculation(wE, wG):
    P, U, p99 = [1811.2, 409.7, 100, 0, 3, 0.001], [0, 409.7, 30, 0, 3, 0], 409.7
    r = run_js(P, U, p99, wE, wG)
    for row, ref in zip(r["rows"], by_hand(P, U, p99, wE, wG)):
        if ref is None:
            assert row is None                          # no exposed residents: excluded
        else:
            assert row["E"] == pytest.approx(ref[0]) and row["G"] == pytest.approx(ref[1]) and row["S"] == pytest.approx(ref[2])
    assert sorted(r["order"]) == [0, 1, 2, 4, 5]
    s = [r["rows"][i]["S"] for i in r["order"]]
    assert s == sorted(s, reverse=True)


@node
def test_worked_example():
    # P = 100, U = 30, P99 = 409.7: E = 100·ln(101)/ln(410.7) = 76.69, G = 30, S(50/50) = 53.35
    r = run_js([100], [30], 409.7, 50, 50)["rows"][0]
    assert r["E"] == pytest.approx(76.69, abs=0.01) and r["G"] == 30 and r["S"] == pytest.approx(53.35, abs=0.01)
    assert run_js([5000], [0], 409.7, 1, 0)["rows"][0]["E"] == 100          # capped at P99


@node
def test_zero_weights_are_explicit_and_negative_rejected():
    r = run_js([10, 20], [0, 0], 409.7, 0, 0)
    assert r["w"]["zero"] and r["order"] == [] and all(x["S"] is None for x in r["rows"])
    assert "error" in run_js([10], [0], 409.7, -1, 1)


@node
def test_constant_gap_keeps_exposure_ranking():
    """No capacity: U = P everywhere, G = 100 for all, so the order equals the exposure order (ties: larger P first)."""
    P = [5, 400, 50, 50.0001, 1]
    r = run_js(P, P, 409.7, 50, 50)
    assert r["gConstant"] and r["gValue"] == 100
    assert r["order"] == sorted(range(len(P)), key=lambda i: -P[i])


@pytest.fixture(scope="module")
def real():
    import map as M
    d = M.prepare()
    o = dm.build_demand(d["flood"], d["hexes"])
    hx, oh = dm.hex_summary(o, d["hexes"], M.hex_index, M.hex_polygons)
    return M, d, o, hx, oh


def test_hex_summary_reconciles(real):
    M, d, o, hx, oh = real
    assert dm.check_hex_summary(hx, oh, o) == []
    assert hx["residents"].sum() == pytest.approx(d["flood"]["residents"].sum(), rel=1e-9)
    assert hx["hex_id"].is_unique and len(oh) == len(o)
    # fallback origins are inside the hexagon they were assigned to (same grid as map.py)
    fb = o["origin_id"].str.startswith("p").to_numpy()
    q, r = M.hex_index(o["x"].to_numpy()[fb], o["y"].to_numpy()[fb])
    assert (hx["hex_id"].to_numpy()[oh[fb]] == np.char.add(np.char.add("h", q.astype(str)), np.char.add("_", r.astype(str)))).all()


def test_p99_is_fixed_quantile(real):
    *_, hx, _ = real
    v = np.sort(hx["residents"].to_numpy())
    assert dm.exposure_reference(hx) == pytest.approx(np.quantile(v[v > 0], 0.99))
