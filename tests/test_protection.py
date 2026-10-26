"""Tests for the flood protection mask in `scripts/build_exposure.py`.

The residual exposure is the undefended count minus the people the defences
hold. Three properties decide whether that figure means what it says: a cell
is held only up to its design standard, a cell the standards raster does not
cover is never held, and a protected run never overwrites the undefended table.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from scripts import build_exposure


@pytest.fixture
def standards(tmp_path):
    """A 10 x 10 km block in EPSG:3035 whose defences hold the 1-in-100 flood,
    with its western half unknown (-1, the raster's nodata)."""
    path = tmp_path / "standards.tif"
    data = np.full((20, 20), 100.0, dtype="float32")
    data[:, :10] = -1.0
    with rasterio.open(
        path, "w", driver="GTiff", height=20, width=20, count=1, dtype="float32",
        crs="EPSG:3035", transform=from_origin(4_000_000, 3_010_000, 500, 500), nodata=-1.0,
    ) as dst:
        dst.write(data, 1)
    return path


def _held(standards_path, return_period):
    """The mask on a 100 m grid over the same block, in the same CRS."""
    with rasterio.open(standards_path) as protection:
        return build_exposure.protected_cells(
            (100, 100), from_origin(4_000_000, 3_010_000, 100, 100), "EPSG:3035",
            protection, return_period,
        )


def test_a_cell_is_held_up_to_its_design_standard_and_not_beyond(standards):
    """A 1-in-100 dyke holds the 1-in-50 and the 1-in-100 flood, not the 1-in-200."""
    eastern = (slice(None), slice(50, 100))
    assert _held(standards, 50)[eastern].all()
    assert _held(standards, 100)[eastern].all()
    assert not _held(standards, 200)[eastern].any()


def test_a_cell_without_a_known_standard_is_never_held(standards):
    """Unknown protection must not read as protection: the figure stays an
    upper bound there instead of silently shrinking."""
    western = (slice(None), slice(0, 50))
    assert not _held(standards, 2)[western].any()


def test_outside_the_standards_raster_nothing_is_held(standards):
    """A hazard window beyond the raster's extent (Iceland, Turkey) is unprotected."""
    with rasterio.open(standards) as protection:
        held = build_exposure.protected_cells(
            (50, 50), from_origin(6_000_000, 2_000_000, 100, 100), "EPSG:3035",
            protection, 2,
        )
    assert not held.any()


def test_a_protected_run_is_parked_and_written_apart_from_the_undefended_one():
    """Same return period, different figure: the parts must not mix, and the
    residual table must never replace exposure.parquet."""
    plain = build_exposure._part_path(100, mode="fraction", min_depth_m=0.5, masks=["a", "b"])
    protected = build_exposure._part_path(
        100, mode="fraction", min_depth_m=0.5, masks=["a", "b"], protected=True
    )
    assert plain.name == "rp100_fraction_d0.5_m2.parquet", "existing parts must still be found"
    assert protected.name == "rp100_fraction_d0.5_m2_prot.parquet"
    assert build_exposure.PROTECTED_OUT != build_exposure.OUT


def test_a_protected_period_needs_its_return_period():
    """Without the return period the mask has no threshold to compare against."""
    with pytest.raises(ValueError, match="return period"):
        build_exposure._exposure_one_period(
            "unused.tif", "unused.tif", None, stripes=1, min_depth_m=0.5,
            mode="fraction", masks=[], protection="standards.tif",
        )


def test_total_population_is_cached_per_raster(tmp_path, monkeypatch):
    """One fixed cache name made the 2010 epoch read the 2025 totals back: two
    different population grids must never share a cached denominator."""
    import geopandas as gpd
    from shapely.geometry import box

    monkeypatch.setattr(build_exposure, "PARTS", tmp_path / "parts")
    monkeypatch.setattr(build_exposure, "POP_ZIP", tmp_path / "absent.zip")
    admin = gpd.GeoDataFrame({"nuts_id": ["A"]}, geometry=[box(4_000_000, 3_000_000, 4_010_000, 3_010_000)], crs="EPSG:3035")

    def grid(name, value):
        path = tmp_path / name
        with rasterio.open(path, "w", driver="GTiff", height=20, width=20, count=1,
                           dtype="float32", crs="EPSG:3035", nodata=-200.0,
                           transform=from_origin(4_000_000, 3_010_000, 500, 500)) as dst:
            dst.write(np.full((20, 20), value, dtype="float32"), 1)
        return str(path)

    first = build_exposure.total_population(grid("pop_2025.tif", 1.0), admin)
    second = build_exposure.total_population(grid("pop_2010.tif", 2.0), admin)
    assert second.iloc[0] == pytest.approx(2 * first.iloc[0])
    assert len(list((tmp_path / "parts").glob("total_pop*.parquet"))) == 2
