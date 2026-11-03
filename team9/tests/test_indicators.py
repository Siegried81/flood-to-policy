"""Spatial indicators on synthetic geometries in EPSG:3035 (hexagons, flood areas, coverage, direct hits)."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import shapely

import map as basemap
from priority import indicators as ind

CRS = basemap.METRIC_CRS
X0, Y0 = 4_100_000.0, 3_050_000.0          # somewhere in the study area, EPSG:3035 metres


def gdf(geoms, **cols):
    return gpd.GeoDataFrame(cols, geometry=list(geoms), crs=CRS)


def test_hex_index_matches_polygons():
    rng = np.random.default_rng(0)
    x, y = X0 + rng.random(2000) * 5000, Y0 + rng.random(2000) * 5000
    q, r = basemap.hex_index(x, y)
    polys = basemap.hex_polygons(q, r)
    assert shapely.contains_xy(polys, x, y).mean() > 0.999          # boundary points may fall either side
    assert basemap.hex_polygons(np.array([0]), np.array([0]))[0].area == pytest.approx(ind.HEX_AREA)


def test_region_hexes_cover_region():
    region = shapely.Point(X0, Y0).buffer(3000)
    hx = ind.region_hexes(region)
    assert hx.crs.to_string() == CRS
    assert region.difference(hx.union_all()).area < 1                # no gap
    assert not hx.duplicated(["q", "r"]).any()


def test_area_by_hex():
    hx = ind.region_hexes(shapely.box(X0, Y0, X0 + 2000, Y0 + 2000))
    big = shapely.box(X0 - 5000, Y0 - 5000, X0 + 5000, Y0 + 5000)
    assert np.allclose(ind.area_by_hex(hx, big), ind.HEX_AREA)
    assert ind.area_by_hex(hx, shapely.box(0, 0, 1, 1)).sum() == 0


def test_flood_union_removes_overlaps():
    a, b = shapely.box(X0, Y0, X0 + 100, Y0 + 100), shapely.box(X0 + 50, Y0, X0 + 150, Y0 + 100)  # overlap 50 x 100
    t = shapely.box(X0 + 100, Y0, X0 + 200, Y0 + 100)                                             # trace half under b
    flood = gdf([a, b, t], kind=["flooded", "flooded", "trace"], activation=["EMSR517", "EMSR518", "EMSR517"])
    wet, trace = ind.flood_union(flood)
    assert wet.area == pytest.approx(15_000)          # not 20,000: overlapping activations counted once
    assert trace.area == pytest.approx(5_000)         # trace part already counted as flooded is removed
    assert wet.intersection(trace).area == pytest.approx(0)


def test_pop_by_hex_conserves_total():
    cells = gpd.GeoDataFrame({"pop": [100.0, 50.0]}, geometry=[shapely.box(X0, Y0, X0 + 900, Y0 + 900),
                                                               shapely.box(X0 + 900, Y0, X0 + 1800, Y0 + 900)], crs=CRS)
    hx = ind.region_hexes(shapely.box(X0 - 500, Y0 - 500, X0 + 2300, Y0 + 1400))
    assert ind.pop_by_hex(hx, cells).sum() == pytest.approx(150)


def test_neighbourhood_sums_and_missing_flood():
    hx = pd.DataFrame({"q": [0, 1, -1, 0, 0, 1, -1, 5], "r": [0, 0, 0, 1, -1, -1, 1, 5]})
    hx["pop"] = [7.0, 0, 0, 0, 0, 0, 0, 0]
    hx["bldg"] = 0.0
    hx["a_flood"], hx["a_trace"], hx["a_hex"] = 0.0, 0.0, ind.HEX_AREA
    hx["a_mapped"] = ind.HEX_AREA
    hx.loc[7, "a_mapped"] = 0.0                       # far hexagon outside EMS coverage
    hx.loc[1, "a_flood"] = ind.HEX_AREA / 2
    out = ind.neighbourhood(hx)
    assert (out.loc[:6, "n_pop"] == 7).all() and out.loc[7, "n_pop"] == 0
    assert out.loc[0, "flood_share"] == pytest.approx(0.5 / 7)
    assert np.isnan(out.loc[7, "flood_share"])        # unmapped -> unknown, never 0
    assert out.loc[3, "flood_share"] == pytest.approx(0.5 / 4)   # hex (0,1): 4 grid hexes in its ring, one half flooded
    assert not out["b_gap"].any()                     # 7 residents: below the gap threshold


def test_b_gap_flag():
    hx = pd.DataFrame({"q": [0], "r": [0], "pop": [500.0], "bldg": [0.0], "a_flood": [0.0], "a_trace": [0.0],
                       "a_mapped": [ind.HEX_AREA], "a_hex": [ind.HEX_AREA]})
    assert ind.neighbourhood(hx)["b_gap"].iloc[0]


def test_asset_direct_hits_and_coverage():
    flood = gdf([shapely.box(X0, Y0, X0 + 200, Y0 + 200), shapely.box(X0 + 1000, Y0, X0 + 1200, Y0 + 200)],
                kind=["flooded", "trace"], activation=["EMSR517"] * 2)
    aoi = gdf([shapely.box(X0 - 2000, Y0 - 2000, X0 + 3000, Y0 + 2000)], activation=["EMSR517"])
    region = aoi.buffer(1000).union_all()
    hx = ind.region_hexes(region)
    for c in ("pop", "bldg"):
        hx[c] = 0.0
    hx["a_flood"] = ind.area_by_hex(hx, flood.geometry.iloc[0])
    hx["a_trace"] = ind.area_by_hex(hx, flood.geometry.iloc[1])
    hx["a_mapped"] = ind.area_by_hex(hx, aoi.geometry.iloc[0])
    hx["a_hex"], hx["country"] = ind.HEX_AREA, "DEU"
    hx = ind.neighbourhood(hx)
    assets = gdf([shapely.Point(X0 + 100, Y0 + 100),        # inside flooded area
                  shapely.Point(X0 + 220, Y0 + 100),        # 20 m outside: within the 25 m tolerance
                  shapely.Point(X0 + 1100, Y0 + 100),       # inside trace
                  shapely.Point(X0 + 600, Y0 + 100),        # mapped, not hit
                  shapely.Point(X0 + 3500, Y0)],            # outside coverage (in the 1 km read buffer)
                 osm_id=range(5))
    a = ind.asset_indicators(assets, hx, flood, aoi)
    assert a["hit_flooded"].tolist() == [True, True, False, False, False]
    assert a["hit_trace"].tolist() == [False, False, True, False, False]
    assert a["in_mapped"].tolist() == [True, True, True, True, False]
    assert len(a) == len(assets) and a.crs.to_string() == CRS   # one row per asset: no duplicated joins
