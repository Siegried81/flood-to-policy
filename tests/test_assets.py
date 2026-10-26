"""Tests for the built-up surface half of exposure.

The module is deliberately thin - it hands the built-up raster to the same
function that sums population - so these tests pin the three things that are its
own: that the archive is resolved and refused clearly, that the unit is renamed
so nothing downstream reads square metres as people, and that the share has a
denominator it can be trusted with.
"""

from __future__ import annotations

import zipfile

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from src import assets


def _tif(path, array, *, transform, nodata=None, crs="EPSG:3035"):
    """A one-band raster. `nodata` is passed explicitly everywhere below: without
    it `rasterstats` picks -999 of its own accord and warns, and a sentinel the
    test did not choose is a sentinel the test is not testing."""
    with rasterio.open(
        path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
        count=1, dtype="float32", crs=crs, transform=transform, nodata=nodata,
    ) as dst:
        dst.write(array.astype("float32"), 1)
    return str(path)


@pytest.fixture
def scene(tmp_path):
    """Four 1 km cells of built-up surface under a hazard that floods two.

    Numbers chosen so the expected answers are readable by hand: every cell holds
    250,000 m2 of footprint, a quarter of the cell, and the hazard covers the left
    half of the grid.
    """
    built = np.full((2, 2), 250_000.0)
    built_path = _tif(
        tmp_path / "built.tif", built,
        transform=from_origin(0, 2000, 1000, 1000), nodata=-200.0,
    )
    hazard = np.array([[2.0, -9999.0], [2.0, -9999.0]])
    hazard_path = _tif(
        tmp_path / "haz.tif", hazard,
        transform=from_origin(0, 2000, 1000, 1000), nodata=-9999.0,
    )
    admin = gpd.GeoDataFrame(
        {"id": ["whole"]}, geometry=[box(0, 0, 2000, 2000)], crs="EPSG:3035"
    )
    return hazard_path, built_path, admin


def test_a_missing_archive_says_how_to_get_it(tmp_path):
    """`data/` is gitignored, so this is the first error a fresh clone hits."""
    with pytest.raises(SystemExit, match="src.fetch"):
        assets.built_path(tmp_path / "absent.zip")


def test_an_archive_with_two_rasters_is_refused(tmp_path):
    """One archive, one raster. Two means the wrong GHS product was fetched -
    the residential and non-residential variants are published separately, and
    silently picking the first would make every figure the wrong one."""
    archive = tmp_path / "two.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.tif", b"x")
        zf.writestr("b.tif", b"y")
    with pytest.raises(SystemExit, match="exactly one"):
        assets.built_path(archive)


def test_the_archive_path_points_inside_the_zip(tmp_path):
    """The fetcher keeps the archive packed, so the path has to be a GDAL
    zip:// path and not a filesystem one."""
    archive = tmp_path / "one.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("GHS_BUILT_S_only.tif", b"x")
    path = assets.built_path(archive)
    assert path.startswith("zip://")
    assert path.endswith("!/GHS_BUILT_S_only.tif")


def test_the_column_is_metres_not_people(scene):
    """`exposed_pop` on a surface raster would be a lie about the unit, and the
    kind that survives into a brief because the number still looks plausible."""
    hazard_path, built_path, admin = scene
    out = assets.exposed_built_surface(hazard_path, built_path, admin, min_depth_m=0.5)
    assert "exposed_built_m2" in out.columns
    assert "exposed_pop" not in out.columns
    assert "hazard_coverage" in out.columns, "the extrapolation flag must survive"


def test_the_exposed_surface_is_the_flooded_half(scene):
    """Two of four cells flooded, 250,000 m2 each, so 500,000 m2 exposed."""
    hazard_path, built_path, admin = scene
    out = assets.exposed_built_surface(hazard_path, built_path, admin, min_depth_m=0.5)
    assert out["exposed_built_m2"].iat[0] == pytest.approx(500_000.0)


def test_the_share_is_exposed_over_total(scene):
    """Half the grid floods and the footprint is uniform, so the share is 0.5."""
    hazard_path, built_path, admin = scene
    out = assets.built_exposure(hazard_path, built_path, admin, min_depth_m=0.5)
    assert out["built_total_m2"].iat[0] == pytest.approx(1_000_000.0)
    assert out["built_share_exposed"].iat[0] == pytest.approx(0.5)
    assert out["built_share_exposed"].iat[0] <= 1.0


def test_a_region_with_nothing_built_has_no_share(tmp_path):
    """Not 0%. A region with no footprint at all has no share to report, and
    calling it zero puts it at the safe end of a ranking it is absent from."""
    built_path = _tif(
        tmp_path / "built.tif", np.zeros((2, 2)),
        transform=from_origin(0, 2000, 1000, 1000), nodata=-200.0,
    )
    hazard_path = _tif(
        tmp_path / "haz.tif", np.full((2, 2), 2.0),
        transform=from_origin(0, 2000, 1000, 1000), nodata=-9999.0,
    )
    admin = gpd.GeoDataFrame(
        {"id": ["empty"]}, geometry=[box(0, 0, 2000, 2000)], crs="EPSG:3035"
    )
    out = assets.built_exposure(hazard_path, built_path, admin, min_depth_m=0.5)
    assert np.isnan(out["built_share_exposed"].iat[0])


def test_the_share_can_never_exceed_one(tmp_path):
    """It reached 2.0: the numerator carried the extrapolation onto unobserved
    ground and the denominator did not, so a unit whose unobserved half was
    empty reported 200% of its built-up surface exposed - on the column this
    module calls the one to rank on."""
    built = np.array([[400_000.0], [0.0]])
    built_path = _tif(
        tmp_path / "built.tif", built,
        transform=from_origin(0, 2000, 1000, 1000), nodata=-200.0,
    )
    # The layer looks at the top cell only; the bottom one is outside it.
    hazard_path = _tif(
        tmp_path / "haz.tif", np.array([[3.0], [-9999.0]]),
        transform=from_origin(0, 2000, 1000, 1000), nodata=-9999.0,
    )
    admin = gpd.GeoDataFrame(
        {"id": ["half-seen"]}, geometry=[box(0, 0, 1000, 2000)], crs="EPSG:3035"
    )
    out = assets.built_exposure(
        hazard_path, built_path, admin, min_depth_m=0.5, nodata_means_dry=False
    )
    share = out["built_share_exposed"].iat[0]
    assert share <= 1.0, f"share is {share}"
    assert share == pytest.approx(1.0), "all the built-up there is, is flooded"
