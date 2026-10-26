"""Tests for the loading layer, and one guard the suite was missing.

The CRS guard exists because a dead `pyproj` is the silent failure in this
stack: `geopandas` still imports, `GeoDataFrame(..., crs=...)` still returns an
object, and only a `UserWarning` says the CRS was dropped. The boundaries are
EPSG:3035 and the hazard rasters EPSG:4326, so a `crs=None` means every zonal
statistic is computed against unreprojected polygons - the right arithmetic on
the wrong piece of Europe. Measured 2026-10-06: the whole suite passed with
pyproj stubbed out, so nothing caught it.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point

from src.data_io import WEB_CRS, WORKING_CRS


def test_the_crs_engine_is_alive() -> None:
    """A GeoDataFrame given a CRS must come back holding it."""
    frame = gpd.GeoDataFrame({"a": [1]}, geometry=[Point(5.0, 50.0)], crs=WEB_CRS)
    assert frame.crs is not None, "pyproj is not working: every reprojection is a no-op"
    assert frame.crs.to_string() == WEB_CRS


def test_a_reprojection_actually_moves_the_geometry() -> None:
    """The working CRS is metric and the web CRS is degrees, so the numbers must
    change by orders of magnitude. A silent no-op would leave them identical."""
    frame = gpd.GeoDataFrame({"a": [1]}, geometry=[Point(5.0, 50.0)], crs=WEB_CRS)
    moved = frame.to_crs(WORKING_CRS)
    assert moved.crs.to_string() == WORKING_CRS
    x, y = moved.geometry.iloc[0].x, moved.geometry.iloc[0].y
    assert abs(x) > 1000 and abs(y) > 1000, "reprojection did nothing"


def test_the_vector_engine_can_read_a_file(tmp_path) -> None:
    """`load_vector` needs a vector backend; pyogrio is the declared one and it
    was blocked by a Windows policy for part of 2026-10-06."""
    src = gpd.GeoDataFrame({"a": [1]}, geometry=[Point(5.0, 50.0)], crs=WEB_CRS)
    path = tmp_path / "t.geojson"
    src.to_file(path, driver="GeoJSON")
    assert len(gpd.read_file(path)) == 1
