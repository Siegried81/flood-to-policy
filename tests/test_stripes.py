"""The windowed build must not depend on how many windows it used.

`scripts/build_exposure.py` cuts a continental run into pieces to fit in memory,
and the figure has to be the same however many pieces that was. The invariant is
one line to state, and its absence let a real error live: when the pieces were
cut on the HAZARD raster, a population cell lying across two of them was written
by both, and the answer moved with the window count.

Measured on RP100 over all 1,345 NUTS3 regions on 2026-10-06, under that scheme:
13 pieces gave 29,808,232 exposed and 3 gave 29,732,746 — 75,486 people apart,
with 215 regions disagreeing and the worst, PL514, by 14.7%. More pieces meant
more internal boundaries and a larger over-count, which is the signature of
double counting rather than of floating-point noise. The pieces are now cut on
the population grid, where a cell belongs to exactly one of them by construction.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
import geopandas as gpd
from shapely.geometry import box

from src.exposure import exposed_population
from scripts.build_exposure import (
    _exposure_one_period,
    _hazard_window,
    _stripes,
)


def _raster(path, array, *, transform, nodata=None, crs="EPSG:3035"):
    """A one-band GeoTIFF. `nodata` is explicit at every call site: a sentinel
    the test did not choose is a sentinel the test is not testing."""
    with rasterio.open(
        path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
        count=1, dtype="float32", crs=crs, transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(array.astype("float32"), 1)
    return str(path)


@pytest.fixture
def scene(tmp_path):
    """A hazard raster four times finer than the population grid.

    The ratio is the point. A population cell spans several hazard rows, so
    `_hazard_window` has to work out which hazard rows cover a given population
    window and read them with enough margin. On a 1:1 grid that mapping is
    trivial and the test would pass without exercising it.
    """
    rng = np.random.default_rng(0)
    hazard = np.where(rng.random((48, 48)) < 0.3, 2.0, -9999.0)
    hazard_path = _raster(
        tmp_path / "haz.tif", hazard,
        transform=from_origin(0, 4800, 100, 100), nodata=-9999.0,
    )
    pop = np.full((12, 12), 1000.0)
    pop_path = _raster(
        tmp_path / "pop.tif", pop, transform=from_origin(0, 4800, 400, 400),
    )
    admin = gpd.GeoDataFrame(
        {"id": ["a", "b"]},
        geometry=[box(0, 0, 2400, 4800), box(2400, 0, 4800, 4800)],
        crs="EPSG:3035",
    )
    return hazard_path, pop_path, admin


@pytest.mark.parametrize("stripes", [2, 3, 5, 7, 13])
def test_the_figure_does_not_depend_on_the_stripe_count(scene, stripes):
    """One stripe or thirteen, the same raster must give the same people."""
    hazard_path, pop_path, admin = scene
    kwargs = dict(min_depth_m=0.5, mode="fraction", masks=[])
    whole = _exposure_one_period(hazard_path, pop_path, admin, stripes=1, **kwargs)
    split = _exposure_one_period(hazard_path, pop_path, admin, stripes=stripes, **kwargs)

    np.testing.assert_allclose(
        split["exposed_pop"].to_numpy(dtype="float64"),
        whole["exposed_pop"].to_numpy(dtype="float64"),
        rtol=1e-9,
        err_msg=f"{stripes} stripes disagree with one stripe",
    )


def test_more_stripes_never_inflates_the_total(scene):
    """The failure mode was directional: every added boundary added people.

    Pinned separately from the equality above because it is the symptom that
    would be seen first in a real build, where nobody re-runs with one stripe.
    """
    hazard_path, pop_path, admin = scene
    kwargs = dict(min_depth_m=0.5, mode="fraction", masks=[])
    totals = [
        _exposure_one_period(hazard_path, pop_path, admin, stripes=n, **kwargs)["exposed_pop"].sum()
        for n in (1, 4, 16)
    ]
    assert totals[0] == pytest.approx(totals[1]) == pytest.approx(totals[2])


# --- the three failures the windowing rewrite shipped ---------------------------

def test_the_hazard_window_is_never_narrowed_in_longitude(tmp_path):
    """A population row band spans the whole ellipse, and a longitude transform
    of its bounds does not say so.

    The population grid is global Mollweide, and its own bounding box is about
    900 m wider than the projection's valid domain - so `transform_bounds` gets
    `inf` at the corners, drops those points, and under-reports the longitude
    range. At one window it returned left == right == 0.0, and the continental
    build then read a four-pixel strip on the Greenwich meridian out of 110,162
    columns, silently. The window must cover every column at every count.
    """
    pop = _raster(
        tmp_path / "pop_global.tif", np.full((18, 36), 1000.0),
        transform=from_origin(-18_041_000, 9_000_000, 1_002_277, 1_000_000),
        crs="ESRI:54009", nodata=-200.0,
    )
    hazard = _raster(
        tmp_path / "haz_global.tif", np.full((20, 40), 2.0),
        transform=from_origin(-180, 85, 9, 8.5), crs="EPSG:4326", nodata=-9999.0,
    )
    with rasterio.open(hazard) as haz, rasterio.open(pop) as src:
        for count in (1, 2, 3, 10):
            for window in _stripes(pop, count):
                got = _hazard_window(haz, src, window)
                if got is None:
                    continue
                assert got.col_off == 0, f"{count} windows: lost columns on the left"
                assert got.width == haz.width, (
                    f"{count} windows: read {got.width} of {haz.width} columns"
                )


def test_a_window_the_hazard_misses_still_owns_its_population(tmp_path):
    """`cells_counted` is the denominator of `hazard_coverage`, so a skipped
    window cannot be skipped silently.

    Measured before the fix on this very fixture: coverage read 0.25, 0.50 and
    0.75 and the headline figure spanned 36,000 to 144,000 people, all from the
    same data - because a window with no hazard dropped its population cells out
    of the denominator entirely.
    """
    pop = _raster(
        tmp_path / "pop.tif", np.full((12, 12), 1000.0),
        transform=from_origin(0, 12_000, 1000, 1000), nodata=-200.0,
    )
    # Hazard over the top three population rows only: a quarter of the grid.
    hazard = _raster(
        tmp_path / "haz.tif", np.full((3, 12), 2.0),
        transform=from_origin(0, 12_000, 1000, 1000), nodata=-9999.0,
    )
    admin = gpd.GeoDataFrame(
        {"id": ["whole"]}, geometry=[box(0, 0, 12_000, 12_000)], crs="EPSG:3035"
    )
    kwargs = dict(min_depth_m=0.5, mode="fraction", masks=[])
    runs = {
        n: _exposure_one_period(hazard, pop, admin, stripes=n, **kwargs)
        for n in (1, 2, 3, 4, 12)
    }
    for column in ("cells_counted", "hazard_coverage", "exposed_pop"):
        values = [float(f[column].iat[0]) for f in runs.values()]
        assert max(values) - min(values) < 1e-6, (
            f"{column} depends on the window count: {dict(zip(runs, values))}"
        )
    assert float(runs[1]["cells_counted"].iat[0]) == 144
    assert float(runs[1]["hazard_coverage"].iat[0]) == pytest.approx(0.25)


def test_binary_mode_is_not_extrapolated_by_the_build(tmp_path):
    """`exposed_population` refuses to divide binary mode, with a comment saying
    why. The build script divided it anyway, producing a third figure that was
    neither the binary count nor anything documented."""
    pop = _raster(
        tmp_path / "pop.tif", np.full((4, 4), 1000.0),
        transform=from_origin(0, 4000, 1000, 1000), nodata=-200.0,
    )
    hazard = _raster(
        tmp_path / "haz.tif", np.full((4, 2), 2.0),
        transform=from_origin(0, 4000, 1000, 1000), nodata=-9999.0,
    )
    admin = gpd.GeoDataFrame(
        {"id": ["whole"]}, geometry=[box(0, 0, 4000, 4000)], crs="EPSG:3035"
    )
    direct = exposed_population(hazard, pop, admin, mode="binary", min_depth_m=0.5)
    built = _exposure_one_period(
        hazard, pop, admin, stripes=1, min_depth_m=0.5, mode="binary", masks=[]
    )
    assert float(built["exposed_pop"].iat[0]) == pytest.approx(
        float(direct["exposed_pop"].iat[0])
    )
