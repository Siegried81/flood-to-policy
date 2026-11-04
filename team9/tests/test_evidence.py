"""Evidence register: validation rules, locality figures on a toy example, and the committed register itself."""
import copy

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from evidence import register as ev

REG = ev.load()


def test_committed_register_is_valid():
    assert ev.check(REG) == []


def test_records_keep_status_dates_and_sources():
    for r in REG["records"]:
        assert r["status"] != "completed" or r["completion_date"], r["id"]
        assert r["source"]["url"].startswith("https://") and r["checked"] == "2026-10-30"
        assert r["establishes"] and r["unverified"], r["id"]
        assert "lat" not in r and "lon" not in r and "geometry" not in r, "no map position for a record"


@pytest.mark.parametrize("edit, msg", [
    (lambda g: g["records"][0].update(status="done"), "status must be one of"),
    (lambda g: g["records"][0].update(status="completed", completion_date=None), "needs a completion_date"),
    (lambda g: g["records"][0].update(category="other"), "category must be one of"),
    (lambda g: g["records"][0]["source"].update(url="http://x.org"), "https://"),
    (lambda g: g["records"][0]["source"].update(published="April 2026"), "YYYY-MM-DD"),
    (lambda g: g["records"][0].pop("unverified"), "missing 'unverified'"),
    (lambda g: g["records"][1].update(id=g["records"][0]["id"]), "duplicate id"),
    (lambda g: g["actions"][0]["basis"].append({"source": "VAL-01"}), "is not a record of locality"),
    (lambda g: g["actions"][0]["basis"].append({"data": "shortage"}), "unknown data key"),
    (lambda g: g["actions"][0]["basis"].append({"note": "x"}), "needs 'source', 'data' or 'scenario'"),
    (lambda g: g["actions"][0].update(locality="XYZ"), "unknown locality"),
])
def test_check_catches_bad_edits(edit, msg):
    g = copy.deepcopy(REG)
    edit(g)
    assert any(msg in p for p in ev.check(g)), ev.check(g)


def test_locality_facts_toy():
    crs = "EPSG:3035"
    reg = {"localities": [{"id": "A", "municipality": "Atown", "country": "X"}, {"id": "B", "municipality": "Nowhere", "country": "X"}]}
    admin = gpd.GeoDataFrame({"municipality": ["Atown"], "municipality_code": ["1"]}, geometry=[box(0, 0, 1000, 1000)], crs=crs)
    flood = gpd.GeoDataFrame({"kind": ["flooded", "trace"], "activation": ["E1", "E1"]},
                             geometry=[box(0, 0, 100, 100), box(900, 900, 1100, 1100)], crs=crs)
    aoi = gpd.GeoDataFrame(geometry=[box(0, 0, 500, 1000)], crs=crs)
    origins = pd.DataFrame({"x": [50, 950, 2000], "y": [50, 950, 2000], "residents": [10.0, 5.0, 99.0]})
    inv = pd.DataFrame({"municipality": ["Atown", "Atown", "Other"], "candidate_id": ["c1", "c2", "c3"],
                        "screen_category": ["inside_observed", "outside_extent_in_ems", "inside_observed"],
                        "shelter_capacity": [None, None, None]})
    facts, problems = ev.locality_facts(reg, admin, inv, origins, flood, aoi)
    a = facts["A"]
    assert a["residents"] == 15.0 and a["ems_cover"] == 0.5
    assert a["flood_ha"] == {"flooded": 1.0, "trace": 1.0}   # trace clipped to the municipality
    assert a["candidates"] == {"inside_observed": 1, "outside_extent_in_ems": 1} and a["documented_capacity"] == 0
    assert a["candidate_ids"] == ["c1", "c2"] and a["outline"]["features"]
    assert facts["B"]["outline"] is None and "no map link" in problems[0]
