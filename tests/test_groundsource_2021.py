"""Tests for scripts/groundsource_2021.py on synthetic polygons and rasters. No network.

The real inputs are a 667 MB parquet and a continental raster that CI does not
have, so what is tested is every rule that moves a count: which dates are in
the window, when a polygon is "dry" in the RP100 map (touch, not centre; nodata
and zero are both dry), the EMS AOI flag, the size classes, and the summary.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import rasterio
import shapely
from rasterio.transform import from_origin
from shapely.geometry import box

from scripts import groundsource_2021 as G

# --------------------------------------------------------------------------
# Date rule
# --------------------------------------------------------------------------


def test_date_rule_keeps_starts_in_the_window_both_ends_included():
    start = pd.Series(["2021-07-11", "2021-07-12", "2021-07-20", "2021-07-21", "2021-07-08",
                       "2021-07-01"])
    end = pd.Series(["2021-07-11", "2021-07-13", "2021-07-25", "2021-07-22", "2021-07-14",
                     "2021-07-05"])
    out = G.date_rule(start, end).tolist()
    assert out == ["outside", "in_window", "in_window", "outside", "overlaps_only", "outside"]


def test_read_events_pushes_the_date_filter_and_the_box(tmp_path):
    """Only rows starting in [lo, hi] and meeting the box come back, as polygons."""
    near, far = box(6.0, 50.0, 6.1, 50.1), box(30.0, 10.0, 30.1, 10.1)
    table = pa.table({
        "uuid": ["a", "b", "c"],
        "area_km2": [1.0, 1.0, 1.0],
        "geometry": [shapely.to_wkb(near), shapely.to_wkb(near), shapely.to_wkb(far)],
        "start_date": ["2021-07-14", "2021-08-01", "2021-07-14"],
        "end_date": ["2021-07-15", "2021-08-02", "2021-07-15"],
    })
    path = tmp_path / "gs.parquet"
    pq.write_table(table, path)
    out = G.read_events(path)
    assert out["uuid"].tolist() == ["a"]
    assert out.crs.to_epsg() == 4326 and out.geometry.iloc[0].equals(near)


# --------------------------------------------------------------------------
# Wet / dry in the RP100 map
# --------------------------------------------------------------------------

NODATA = -9999.0


@pytest.fixture
def raster(tmp_path):
    """10 x 10 cells of 0.1 degree from (0, 1) down to (1, 0).

    Cell (row 2, col 2) is wet (1.5 m); cell (row 7, col 7) holds 0 m; the rest
    is nodata, which is how the JRC map stores "dry".
    """
    depth = np.full((10, 10), NODATA, np.float32)
    depth[2, 2] = 1.5
    depth[7, 7] = 0.0
    path = tmp_path / "rp100.tif"
    with rasterio.open(path, "w", driver="GTiff", height=10, width=10, count=1, dtype="float32",
                       crs="EPSG:4326", transform=from_origin(0.0, 1.0, 0.1, 0.1),
                       nodata=NODATA) as dst:
        dst.write(depth, 1)
    return path


def _cells(raster, geom):
    with rasterio.open(raster) as src:
        return G.rp100_cells(geom, src)


def test_a_polygon_over_the_wet_cell_is_wet(raster):
    # Cell (2, 2) spans x 0.2-0.3, y 0.7-0.8.
    cells, wet = _cells(raster, box(0.15, 0.65, 0.35, 0.85))
    assert wet == 1 and cells == 9


def test_a_polygon_far_from_water_is_dry(raster):
    assert _cells(raster, box(0.51, 0.11, 0.59, 0.19))[1] == 0


def test_touch_not_centre_a_sliver_of_the_wet_cell_counts(raster):
    """A polygon that misses the wet cell's centre but touches the cell is wet.

    The strict rule: a dry verdict must mean no wet cell anywhere in the place.
    """
    cells, wet = _cells(raster, box(0.29, 0.71, 0.45, 0.79))
    assert wet == 1


def test_zero_depth_is_dry_and_nodata_is_dry(raster):
    # Cell (7, 7) spans x 0.7-0.8, y 0.2-0.3 and holds 0 m.
    assert _cells(raster, box(0.72, 0.22, 0.78, 0.28)) == (1, 0)


def test_a_polygon_off_the_raster_edge_reads_nodata(raster):
    cells, wet = _cells(raster, box(0.95, -0.2, 1.3, 0.05))
    assert wet == 0 and cells > 0


def test_add_rp100_reprojects_and_flags_dry(raster):
    events = gpd.GeoDataFrame(
        {"uuid": ["wet", "dry"]},
        geometry=[box(0.21, 0.71, 0.29, 0.79), box(0.51, 0.11, 0.59, 0.19)], crs="EPSG:4326",
    ).to_crs("EPSG:3857")
    out = G.add_rp100(events, raster)
    assert out["rp100_dry"].tolist() == [False, True]
    assert out["rp100_wet_cells"].tolist()[0] == 1


# --------------------------------------------------------------------------
# EMS AOI flag
# --------------------------------------------------------------------------


def test_ems_flag_inside_partial_and_outside():
    aoi = box(0, 0, 1, 1)
    events = gpd.GeoDataFrame(geometry=[box(0.2, 0.2, 0.4, 0.4), box(0.9, 0.9, 1.5, 1.5),
                                        box(2, 2, 3, 3)], crs="EPSG:4326")
    out = G.add_ems_flag(events, aoi)
    assert out["in_ems_aoi"].tolist() == [True, True, False]
    assert out["outside_ems_aoi"].tolist() == [False, False, True]


def test_read_aoi_unions_every_geopackage(tmp_path):
    for i, g in enumerate([box(0, 0, 1, 1), box(5, 5, 6, 6)]):
        gpd.GeoDataFrame(geometry=[g], crs="EPSG:4326").to_file(
            tmp_path / f"p{i}.gpkg", layer="areaOfInterestA", driver="GPKG")
    aoi = G.read_aoi(tmp_path)
    assert aoi.contains(shapely.Point(0.5, 0.5)) and aoi.contains(shapely.Point(5.5, 5.5))
    assert not aoi.contains(shapely.Point(3, 3))


def test_read_aoi_refuses_an_empty_folder(tmp_path):
    with pytest.raises(FileNotFoundError):
        G.read_aoi(tmp_path)


# --------------------------------------------------------------------------
# Place, size class and summary
# --------------------------------------------------------------------------


def test_assign_place_uses_the_representative_point():
    """An L-shaped polygon whose centroid falls outside it still gets its own LAU."""
    lau = gpd.GeoDataFrame({"GISCO_ID": ["BE_1", "DE_1"], "CNTR_CODE": ["BE", "DE"],
                            "LAU_NAME": ["Liege", "Schuld"]},
                           geometry=[box(0, 0, 1, 2), box(1, 0, 3, 2)], crs="EPSG:4326")
    ell = box(0, 0, 0.5, 2).union(box(0, 0, 2.9, 0.4))
    events = gpd.GeoDataFrame({"uuid": ["ell", "sea"]},
                              geometry=[ell, box(10, 10, 11, 11)], crs="EPSG:4326")
    out = G.assign_place(events, lau)
    assert out["country"].iloc[0] in ("BE", "DE")
    assert ell.contains(shapely.Point(out["lon"].iloc[0], out["lat"].iloc[0]))
    assert pd.isna(out["country"].iloc[1])


def test_size_class_bounds_are_inclusive():
    out = G.size_class(pd.Series([0.001, 1.0, 1.01, 100.0, 1000.0, 4999.0])).tolist()
    assert out == ["site <=1 km2", "site <=1 km2", "town <=100 km2", "town <=100 km2",
                   "district <=1000 km2", "region >1000 km2"]


def test_summarise_counts_per_country_and_total():
    same = box(0, 0, 1, 1)
    events = gpd.GeoDataFrame({
        "country": ["BE", "BE", "DE"],
        "area_km2": [0.5, 50.0, 2000.0],
        "rp100_dry": [True, False, False],
        "in_ems_aoi": [False, True, True],
    }, geometry=[same, same, box(2, 2, 3, 3)], crs="EPSG:4326")
    events["outside_ems_aoi"] = ~events["in_ems_aoi"]
    events["size_class"] = G.size_class(events["area_km2"])
    t = G.summarise(events).set_index("country")
    assert t.loc["BE", "events"] == 2 and t.loc["BE", "distinct_polygons"] == 1
    assert t.loc["BE", "rp100_dry"] == 1 and t.loc["BE", "rp100_dry_share"] == 0.5
    assert t.loc["BE", "dry_and_outside_aoi"] == 1
    assert t.loc["DE", "town_scale_events"] == 0 and np.isnan(t.loc["DE", "town_scale_dry_share"])
    assert t.loc["total", "events"] == 3 and t.loc["total", "outside_ems_aoi"] == 1
    assert t.loc["total", "region >1000 km2"] == 1


def test_ensure_groundsource_reports_a_failed_fetch(tmp_path, monkeypatch):
    """A missing file goes through `src.fetch`, mocked here; a failure stops the run."""
    from src import fetch

    class Res:
        error, path = "404 Client Error", None

    monkeypatch.setattr(fetch, "fetch_source", lambda source_id: Res())
    with pytest.raises(SystemExit, match="404"):
        G.ensure_groundsource(tmp_path / "missing.parquet")
