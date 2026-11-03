"""Candidate shelter selection, de-duplication, screening categories and checks on hand-made data (no network)."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely

import shelters as sh

M = sh.METRIC_CRS
# Flood: a 1 km square (flooded) and a trace square next to it; EMS area: 3 km square around both
FLOOD = gpd.GeoDataFrame({"kind": ["flooded", "trace"]},
                         geometry=[shapely.box(0, 0, 1000, 1000), shapely.box(1000, 0, 1500, 1000)], crs=M)
AOI = gpd.GeoDataFrame({"activation": ["EMSR517"]}, geometry=[shapely.box(-1000, -1000, 2000, 2000)], crs=M)


def run(points, footprints=None):
    pts = gpd.GeoSeries(points, crs=M)
    return sh.screen(pts, gpd.GeoSeries(footprints or points, crs=M), FLOOD, AOI)


# --------------------------------------------------------------------------- selection rules
@pytest.mark.parametrize("tags, ftype", [
    ({"amenity": "school"}, "school"),
    ({"amenity": "community_centre"}, "community_centre"),
    ({"leisure": "sports_hall"}, "sports_hall"),
    ({"building": "sports_hall", "leisure": "pitch"}, "sports_hall"),
    ({"leisure": "sports_centre", "building": "yes"}, "sports_hall"),
    ({"leisure": "sports_centre"}, None),                       # outdoor site (R3)
    ({"amenity": "school", "disused": "yes"}, None),            # lifecycle (R5)
    ({"amenity": "community_centre", "construction": "yes"}, None),
    ({"amenity": "kindergarten"}, None),
])
def test_classify(tags, ftype):
    res, _ = sh.classify(tags)
    assert (res and res[0]) == ftype


def test_small_building_excluded():
    tiny = [(7.0, 50.5), (7.0001, 50.5), (7.0001, 50.5001), (7.0, 50.5001), (7.0, 50.5)]  # ≈ 80 m²
    el = {"type": "way", "id": 1, "geometry": [{"lon": x, "lat": y} for x, y in tiny],
          "tags": {"building": "sports_hall"}}
    gdf, ex = sh.candidate_frame([(el, {})], "test")
    assert gdf.empty and ex[0][1].startswith("R4")


# --------------------------------------------------------------------------- de-duplication
def cand(i, geom, ftype="school", name="A", osm_type="node"):
    return {"osm_type": osm_type, "osm_id": i, "facility_type": ftype, "tags": {"name": name}, "geometry": geom}


def test_dedup_contained_and_same_name():
    grounds = shapely.box(0, 0, 200, 200)
    gdf = gpd.GeoDataFrame([
        cand(1, grounds, osm_type="way"),
        cand(2, shapely.Point(100, 100)),                        # node inside the grounds -> dropped
        cand(2, shapely.Point(100, 100)),                        # same element twice (two sources) -> dropped
        cand(3, shapely.Point(230, 100)),                        # same name, 30 m outside -> merged into the polygon
        cand(4, shapely.Point(100, 100), ftype="sports_hall"),   # other type at the same place -> kept
        cand(5, shapely.Point(5000, 5000), name="A"),            # same name, far away -> kept
    ], crs=M)
    out, stats = sh.deduplicate(gdf)
    assert sorted(out["cid"]) == ["node/4", "node/5", "way/1"]
    assert out.set_index("cid").at["way/1", "merged_ids"] == "node/3"
    assert stats["dropped_contained"] == 1 and stats["dropped_same_name_nearby"] == 1


def test_dedup_identical_outlines_keeps_way():
    site = shapely.box(0, 0, 200, 200)
    gdf = gpd.GeoDataFrame([cand(1, site, name="Grounds", osm_type="relation"), cand(2, site, name="College", osm_type="way"),
                            cand(3, shapely.box(10, 10, 60, 60), ftype="sports_hall", osm_type="way")], crs=M)
    out, stats = sh.deduplicate(gdf)
    assert sorted(out["cid"]) == ["way/2", "way/3"] and stats["dropped_same_outline"] == 1
    assert out.set_index("cid").at["way/2", "merged_ids"] == "relation/1"


# --------------------------------------------------------------------------- screening
@pytest.mark.parametrize("pt, cat", [
    ((500, 500), "inside_observed"),
    ((1250, 500), "inside_observed"),               # in a flood trace
    ((1000, 500), "inside_observed"),               # on the flooded/trace shared edge: interior of the union
    ((500, 990), "boundary_unresolved"),            # 10 m inside the edge
    ((500, 1010), "boundary_unresolved"),           # 10 m outside the edge
    ((500, 1500), "outside_extent_in_ems"),
    ((500, 2010), "boundary_unresolved"),           # 10 m outside the EMS area
    ((500, 2500), "outside_ems_coverage"),
])
def test_screen_categories(pt, cat):
    assert run([shapely.Point(pt)])["screen_category"].iloc[0] == cat


def test_screen_footprint_overlap_and_kind():
    r = run([shapely.Point(500, 1100), shapely.Point(1250, 500)],
            [shapely.box(400, 950, 600, 1200), shapely.Point(1250, 500)])
    assert r["screen_category"].tolist() == ["boundary_unresolved", "inside_observed"]
    assert r["screen_reason"].iloc[0].startswith("site or building outline")
    assert r["flood_kind"].tolist() == ["", "trace"]
    assert r["flood_edge_dist_m"].iloc[1] == -250 and r["ems_activation"].iloc[1] == "EMSR517"


def test_screen_invalid_point_is_unresolved():
    r = run([shapely.Point(np.nan, np.nan)], [shapely.Point(0, 0)])
    assert r["screen_category"].iloc[0] == "boundary_unresolved"


def test_screen_rejects_wrong_crs():
    with pytest.raises(AssertionError):
        sh.screen(gpd.GeoSeries([shapely.Point(6, 50)], crs=sh.WEB_CRS), gpd.GeoSeries([shapely.Point(6, 50)]), FLOOD, AOI)


# --------------------------------------------------------------------------- municipality
def test_assign_admin_smallest_and_missing():
    admin = gpd.GeoDataFrame({"municipality": ["Big", "Small"], "municipality_code": ["05362", "05362020"],
                              "municipality_level": [6, 8], "country": ["DEU", "DEU"]},
                             geometry=[shapely.box(0, 0, 100, 100), shapely.box(0, 0, 10, 10)], crs=M)
    pts = gpd.GeoDataFrame(geometry=[shapely.Point(5, 5), shapely.Point(50, 50), shapely.Point(500, 500)], crs=M)
    hexes = gpd.GeoDataFrame({"country": ["BEL"]}, geometry=[shapely.box(0, 0, 100, 100)], crs=M)
    r = sh.assign_admin(pts, admin, hexes)
    assert r["municipality"].tolist() == ["Small", "Big", ""]
    assert r["admin_note"].iloc[2] == "no municipality boundary found"
    assert r["country_check"].iloc[0].startswith("differs") and r["country_check"].iloc[2] == "no OBAT hexagon"
