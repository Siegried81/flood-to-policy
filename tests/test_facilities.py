"""Tests for `src/facilities.py`: hospitals and schools in the flood footprint.

Built on synthetic rasters and points, so they run without `data/`. What they
pin is what "flooded" means here: the same threshold and masks as the people
count, an unknown protection standard that never protects, and a facility
counted in exactly one region.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from src import facilities


def _raster(path, data, nodata=None):
    """A 4 x 4 raster over lon 0..4, lat 46..50, in EPSG:4326."""
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(0, 50, 1, 1), nodata=nodata,
    ) as dst:
        dst.write(np.asarray(data, dtype="float32"), 1)
    return str(path)


@pytest.fixture
def points():
    # One point per column of the first row, then one off the raster.
    return gpd.GeoDataFrame(
        {"id": ["a", "b", "c", "d", "e"], "cap_beds": [100, 200, 300, 400, 500]},
        geometry=[Point(0.5, 49.5), Point(1.5, 49.5), Point(2.5, 49.5), Point(3.5, 49.5),
                  Point(10.0, 10.0)],
        crs="EPSG:4326",
    )


def test_a_point_is_flooded_above_the_threshold_not_at_it(tmp_path, points):
    """Strictly above, as the people count: a facility at exactly 0.5 m is not
    in the flood there, so it must not be here either."""
    depth = np.zeros((4, 4))
    depth[0] = [0.2, 0.5, 1.0, np.nan]
    hazard = _raster(tmp_path / "depth.tif", depth, nodata=np.nan)
    wet = facilities.flooded(points, hazard, min_depth_m=0.5)
    assert wet.tolist() == [False, False, True, False, False]


def test_a_masked_cell_is_never_flooded(tmp_path, points):
    """Permanent water is patched in at 1.00 m: a hospital beside the river is
    not in the flood because the channel is wet."""
    depth = np.ones((4, 4))
    hazard = _raster(tmp_path / "depth.tif", depth, nodata=np.nan)
    mask = np.full((4, 4), np.nan)
    mask[0, 1] = 1.0
    water = _raster(tmp_path / "water.tif", mask, nodata=None)
    wet = facilities.flooded(points, hazard, min_depth_m=0.5, masks=[water])
    assert wet.tolist() == [True, False, True, True, False]


def test_an_unknown_protection_standard_never_holds(tmp_path, points):
    standards = np.full((4, 4), -1.0)
    standards[0] = [100, 50, -1, 1000]
    protection = _raster(tmp_path / "prot.tif", standards, nodata=-1.0)
    assert facilities.held(points, protection, 100).tolist() == [True, False, False, True, False]


def test_counts_land_in_one_region_and_weights_are_summed(points):
    admin = gpd.GeoDataFrame(
        {"nuts_id": ["W", "E", "EMPTY"], "country": ["AA", "AA", "AA"]},
        geometry=[box(0, 46, 2, 50), box(2, 46, 4, 50), box(20, 20, 21, 21)],
        crs="EPSG:4326",
    )
    flags = {"flooded_rp100": np.array([True, False, True, True, True])}
    out = facilities.counts_by_region(points, admin, flags, prefix="hospitals", weight="cap_beds")
    assert out["hospitals_total"].tolist() == [2, 2, 0]
    assert out["hospitals_flooded_rp100"].tolist() == [1, 2, 0]
    assert out["hospitals_cap_beds_flooded_rp100"].tolist() == [100, 700, 0]
    # The point at (10, 10) is in no region and is counted nowhere.
    assert out["hospitals_total"].sum() == 4


def test_a_country_the_layer_does_not_cover_is_not_measured_not_zero(points):
    """GISCO holds no German hospital: German regions must read NaN, or the
    table says the most populous Member State has none in the water."""
    admin = gpd.GeoDataFrame(
        {"nuts_id": ["W", "EMPTY_SAME", "DE1"], "country": ["AA", "AA", "DE"]},
        geometry=[box(0, 46, 4, 50), box(20, 20, 21, 21), box(30, 30, 31, 31)],
        crs="EPSG:4326",
    )
    out = facilities.counts_by_region(points, admin, {"flooded_rp100": np.ones(5, bool)},
                                      prefix="hospitals")
    assert out["hospitals_total"].tolist()[:2] == [4, 0], "covered country: a real 0"
    assert np.isnan(out["hospitals_total"].iloc[2]), "uncovered country: not measured"


def test_a_hospital_without_a_bed_figure_is_unknown_not_zero_beds(points):
    """A hospital whose bed figure is missing adds no beds it may have: a
    region's bed total is NaN as soon as one of its hospitals lacks the figure,
    and a flooded-beds column as soon as one of its flagged hospitals does."""
    points = points.copy()
    points["cap_beds"] = [100, np.nan, 300, 400, 500]
    admin = gpd.GeoDataFrame(
        {"nuts_id": ["W", "E", "EMPTY"], "country": ["AA", "AA", "AA"]},
        geometry=[box(0, 46, 2, 50), box(2, 46, 4, 50), box(20, 20, 21, 21)],
        crs="EPSG:4326",
    )
    flags = {
        "flooded_rp100": np.array([True, True, True, False, True]),
        "flooded_rp10": np.array([True, False, False, False, False]),
    }
    out = facilities.counts_by_region(points, admin, flags, prefix="hospitals", weight="cap_beds")
    assert out["hospitals_cap_beds_known"].tolist() == [1, 2, 0]
    assert np.isnan(out["hospitals_cap_beds_total"].iloc[0]), "W: one of two beds unknown"
    assert np.isnan(out["hospitals_cap_beds_flooded_rp100"].iloc[0]), "a flooded bed count unknown"
    assert out["hospitals_cap_beds_flooded_rp10"].iloc[0] == 100, "only the known hospital is flagged"
    assert out["hospitals_cap_beds_total"].iloc[1] == 700
    assert out["hospitals_cap_beds_total"].iloc[2] == 0, "no hospital: a real 0"
    assert out["hospitals_total"].tolist() == [2, 2, 0], "the hospital is still counted"


def test_a_country_reporting_no_beds_has_known_zero_and_beds_nan(points):
    points = points.copy()
    points["cap_beds"] = np.nan
    admin = gpd.GeoDataFrame({"nuts_id": ["W"], "country": ["AA"]},
                             geometry=[box(0, 46, 4, 50)], crs="EPSG:4326")
    out = facilities.counts_by_region(points, admin, {"flooded_rp100": np.ones(5, bool)},
                                      prefix="hospitals", weight="cap_beds")
    assert out["hospitals_cap_beds_known"].tolist() == [0]
    assert np.isnan(out["hospitals_cap_beds_total"].iloc[0])
    assert np.isnan(out["hospitals_cap_beds_flooded_rp100"].iloc[0])
