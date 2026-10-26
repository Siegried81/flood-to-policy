"""Tests for the exposure pipeline, on small synthetic rasters.

Synthetic rather than real data so the expected answer can be computed by hand:
these numbers become the headline figure of a policy brief, and "it looked about
right on the real data" is not a check.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from src.exposure import exposed_population, expected_annual_exposure

CRS = "EPSG:3035"


def _write(path, array, *, nodata=None, dtype="float32", transform=None, crs=CRS):
    """A raster of 100 m cells with its origin at (0, 400), unless told otherwise.

    `dtype` because every fixture here used to be float32 while the real inputs
    are not: `config/sources.yaml` declares the JRC observed layer as uint16
    centimetres and the Walloon classification is class codes. `transform` and
    `crs` so a test can place a raster somewhere else entirely, which is what it
    takes to reach a unit the hazard layer does not cover.
    """
    if transform is None:
        transform = from_origin(0, 400, 100, 100)  # y decreases with the row index
    with rasterio.open(
        path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
        count=1, dtype=dtype, crs=crs, transform=transform, nodata=nodata,
    ) as dst:
        dst.write(array.astype(dtype), 1)
    return str(path)


@pytest.fixture
def rasters(tmp_path):
    """Population of 10 everywhere; the left half of the grid is flooded 1 m deep."""
    pop = np.full((4, 4), 10.0)
    hazard = np.zeros((4, 4))
    hazard[:, :2] = 1.0
    return _write(tmp_path / "pop.tif", pop), _write(tmp_path / "haz.tif", hazard)


def _admin(geoms, ids):
    return gpd.GeoDataFrame({"lau_id": ids, "geometry": geoms}, crs=CRS)


def test_sums_only_the_flooded_half(rasters):
    """The whole grid holds 160 people; half of it is flooded, so 80 are exposed."""
    pop_path, hazard_path = rasters
    admin = _admin([box(0, 0, 400, 400)], ["whole"])
    out = exposed_population(hazard_path, pop_path, admin)
    assert out["exposed_pop"].iat[0] == pytest.approx(80.0)


def test_dry_unit_is_zero_not_missing(rasters):
    """The dry right half is measured and holds nobody exposed: that is 0, a real
    finding, and must be distinguishable from 'not measured'."""
    pop_path, hazard_path = rasters
    admin = _admin([box(200, 0, 400, 400)], ["dry"])
    out = exposed_population(hazard_path, pop_path, admin)
    assert out["exposed_pop"].iat[0] == 0.0
    assert out["cells_counted"].iat[0] > 0


def test_unit_outside_the_raster_is_missing_not_zero(rasters):
    """The bug this guards: numpy sums an empty selection to 0.0, so a commune the
    raster does not cover would read as 'nobody is exposed' instead of 'no data',
    and would be quietly presented as safe in the brief."""
    pop_path, hazard_path = rasters
    admin = _admin([box(10_000, 10_000, 10_400, 10_400)], ["elsewhere"])
    out = exposed_population(hazard_path, pop_path, admin)
    assert out["cells_counted"].iat[0] == 0
    assert out["exposed_pop"].isna().iat[0]


def test_depth_threshold_changes_the_headline_number(rasters):
    """Raising the threshold above the flood depth empties the exposure. The point
    of the parameter is that this choice is explicit and defended, not inherited."""
    pop_path, hazard_path = rasters
    admin = _admin([box(0, 0, 400, 400)], ["whole"])
    deep = exposed_population(hazard_path, pop_path, admin, min_depth_m=2.0)
    assert deep["exposed_pop"].iat[0] == 0.0


def test_neighbouring_units_do_not_double_count(rasters):
    """Summed over adjacent communes, exposure must equal the single-polygon total.
    all_touched=True would count every boundary cell twice and break this."""
    pop_path, hazard_path = rasters
    split = _admin([box(0, 0, 200, 400), box(200, 0, 400, 400)], ["left", "right"])
    whole = _admin([box(0, 0, 400, 400)], ["whole"])
    assert exposed_population(hazard_path, pop_path, split)["exposed_pop"].sum() == pytest.approx(
        exposed_population(hazard_path, pop_path, whole)["exposed_pop"].iat[0]
    )


def test_expected_annual_exposure_ranks_a_strictly_worse_unit_higher():
    """Same scenarios, same probabilities: the unit with more people exposed at
    every return period must come out higher. This is the bridge to cost-benefit,
    so the ordering has to hold."""
    import pandas as pd

    table = pd.DataFrame(
        {
            "lau_id": ["worse", "worse", "better", "better"],
            "return_period": [10, 500, 10, 500],
            "annual_probability": [0.1, 0.002, 0.1, 0.002],
            "exposed_pop": [200.0, 400.0, 100.0, 200.0],
        }
    )
    out = expected_annual_exposure(table).set_index("lau_id")
    assert out.loc["worse", "expected_annual_exposure"] > out.loc["better", "expected_annual_exposure"]


def test_expected_annual_exposure_only_integrates_the_sampled_band():
    """The limitation to state in the brief rather than hide.

    With return periods 10 and 500 the integral covers annual probabilities
    0.002 to 0.1 only - nothing below (rarer than 1-in-500) and nothing above
    (more frequent than 1-in-10). So this is a lower bound on a true Expected
    Annual Damage, and it also means a unit that only floods in rare, severe
    events can out-rank one that floods mildly but often: the trapezoid assumes
    damage ramps linearly across the whole sampled band. Call it what it is.
    """
    import pandas as pd

    table = pd.DataFrame(
        {
            "lau_id": ["often_mild", "often_mild", "rare_severe", "rare_severe"],
            "return_period": [10, 500, 10, 500],
            "annual_probability": [0.1, 0.002, 0.1, 0.002],
            "exposed_pop": [100.0, 120.0, 0.0, 1000.0],
        }
    )
    out = expected_annual_exposure(table).set_index("lau_id")
    # (0 + 1000)/2 * (0.1 - 0.002) = 49 vs (100 + 120)/2 * 0.098 = 10.78
    assert out.loc["rare_severe", "expected_annual_exposure"] == pytest.approx(49.0)
    assert out.loc["often_mild", "expected_annual_exposure"] == pytest.approx(10.78)


def test_fraction_mode_splits_a_partly_flooded_cell(tmp_path):
    """The European case: population cells coarser than the hazard. A 1-cell
    population grid over a half-flooded hazard grid must expose half the people,
    not all of them (binary mode) and not none."""
    import numpy as np
    from rasterio.transform import from_origin

    # Hazard: 4x4 at 100 m, left half 1 m deep. Population: 1 cell of 400 m.
    haz = np.zeros((4, 4)); haz[:, :2] = 1.0
    haz_path = _write(tmp_path / "h.tif", haz)
    with rasterio.open(
        tmp_path / "p.tif", "w", driver="GTiff", height=1, width=1, count=1,
        dtype="float32", crs=CRS, transform=from_origin(0, 400, 400, 400),
    ) as dst:
        dst.write(np.array([[1000.0]], dtype="float32"), 1)

    admin = _admin([box(0, 0, 400, 400)], ["one"])
    frac = exposed_population(haz_path, str(tmp_path / "p.tif"), admin, mode="fraction")
    binary = exposed_population(haz_path, str(tmp_path / "p.tif"), admin, mode="binary")
    assert frac["exposed_pop"].iat[0] == pytest.approx(500.0, rel=0.02)
    assert binary["exposed_pop"].iat[0] == pytest.approx(1000.0)


# --- The hazard layer's own coverage -----------------------------------------
#
# `cells_counted` only ever measured POPULATION-grid coverage. Everything below
# is about the other raster: a unit the hazard map does not reach.


@pytest.fixture
def disjoint_rasters(tmp_path):
    """A population grid and a hazard grid that do not overlap at all.

    Half a degree per cell, geographic CRS, because that is the shape of the
    mistake in the field: a European population grid and a hazard tile delivered
    on a different footprint, both perfectly valid on their own.
    """
    pop = np.zeros((2, 2))
    pop[0, 0] = 500_000.0
    pop_path = _write(
        tmp_path / "pop.tif", pop,
        transform=from_origin(0, 1, 0.5, 0.5), crs="EPSG:4326",
    )
    hazard = np.full((2, 2), 3.0)
    hazard_path = _write(
        tmp_path / "haz.tif", hazard,
        transform=from_origin(50, 10, 0.5, 0.5), crs="EPSG:4326",
    )
    admin = gpd.GeoDataFrame(
        {"lau_id": ["far"], "geometry": [box(0, 0, 1, 1)]}, crs="EPSG:4326"
    )
    return pop_path, hazard_path, admin


@pytest.mark.parametrize("mode", ["fraction", "binary"])
def test_hazard_does_not_cover_the_unit_is_missing_not_zero(disjoint_rasters, mode):
    """The worst failure in the module: 500,000 people reported as 0.0 exposed.

    The population grid covers this unit, so `cells_counted` is 4 and the old
    `count == 0` guard never fired. The hazard raster is on the other side of the
    continent, and both modes flattened that to dry - fraction mode by filling
    unobserved cells with -inf and then with 0.0, binary mode because
    `NaN > min_depth` is False. The unit came out as a measured zero, which reads
    as reassurance about a place nobody had looked at.
    """
    pop_path, hazard_path, admin = disjoint_rasters
    out = exposed_population(hazard_path, pop_path, admin, mode=mode)
    assert out["cells_counted"].iat[0] == 4  # the POPULATION grid does cover it
    assert out["hazard_coverage"].iat[0] == 0.0
    assert out["exposed_pop"].isna().iat[0]


def test_a_measured_dry_unit_is_still_a_measured_zero(rasters):
    """The other half of the same distinction: 0.0 under full hazard coverage is a
    finding, and the coverage guard must not turn it into None."""
    pop_path, hazard_path = rasters
    admin = _admin([box(200, 0, 400, 400)], ["dry"])
    out = exposed_population(hazard_path, pop_path, admin)
    assert out["exposed_pop"].iat[0] == 0.0
    assert out["hazard_coverage"].iat[0] == pytest.approx(1.0)


def test_nodata_holes_do_not_dilute_the_flooded_share(tmp_path):
    """On an AOI-CLIPPED layer, a hole in the hazard layer is not dry ground.

    One 200 m population cell of 1000 people over four 100 m hazard cells: one at
    3 m, three nodata. Averaging the wet mask over the whole cell puts the three
    unobserved cells in the denominator and reports 250 people exposed, as if
    three quarters of the cell had been looked at and found dry. Under
    `nodata_means_dry=False` the flooded share is measured over the quarter that
    was observed - all of it under water - and applied to the cell's people, so
    1000, with `hazard_coverage` 0.25 saying out loud that the figure is
    extrapolated from a quarter of the ground.

    That reading has to be asked for, because it is the wrong one for the layer
    this kit is built on: see the companion test below.
    """
    hazard = np.array([[3.0, -9999.0], [-9999.0, -9999.0]])
    hazard_path = _write(tmp_path / "haz.tif", hazard, nodata=-9999.0)
    pop_path = _write(
        tmp_path / "pop.tif", np.array([[1000.0]]),
        transform=from_origin(0, 400, 200, 200),
    )
    admin = _admin([box(0, 200, 200, 400)], ["one"])
    out = exposed_population(
        hazard_path, pop_path, admin, mode="fraction", nodata_means_dry=False
    )
    assert out["exposed_pop"].iat[0] == pytest.approx(1000.0)
    assert out["hazard_coverage"].iat[0] == pytest.approx(0.25)


def test_a_sparse_hazard_layer_is_not_read_as_three_quarters_unobserved(tmp_path):
    """The same four cells, read the way the EFAS/JRC hazard maps are built.

    `Europe_RP*_filled_depth.tif` stores a depth ONLY where there is inundation:
    measured on RP100 over a 1,468,800-cell window of Belgian land, 4.85% of cells
    carry a value and 100% of those are deeper than 0 m. On such a layer the valid
    mask IS the flood footprint, so dividing the wet share by it gives 1 in every
    cell holding any water at all - the whole cell's population, under the name of
    the fractional measurement. Over BE/NL/LU at RP100 that reads 13,771,935
    people against 5,065,526, bit-identical to what `mode="binary"` returns.

    Under the default the three nodata cells are dry ground, so a quarter of the
    cell is flooded and 250 of its 1000 people are exposed, with `hazard_coverage`
    1.0 because the layer covers all four cells.
    """
    hazard = np.array([[3.0, -9999.0], [-9999.0, -9999.0]])
    hazard_path = _write(tmp_path / "haz.tif", hazard, nodata=-9999.0)
    pop_path = _write(
        tmp_path / "pop.tif", np.array([[1000.0]]),
        transform=from_origin(0, 400, 200, 200),
    )
    admin = _admin([box(0, 200, 200, 400)], ["one"])
    out = exposed_population(hazard_path, pop_path, admin, mode="fraction")
    assert out["exposed_pop"].iat[0] == pytest.approx(250.0)
    assert out["hazard_coverage"].iat[0] == pytest.approx(1.0)


def test_a_dry_unit_inside_a_sparse_layer_is_a_measured_zero(tmp_path):
    """A unit inside the hazard domain with no water in it must read 0.0.

    On a sparse layer every cell of a dry unit is nodata, so a coverage built from
    the valid mask is 0 and `exposed_pop` comes back None - "nobody looked" -
    about a unit the layer covers and found dry. That is the error the None was
    introduced to prevent, pointing the other way: it reads as a gap in the data
    rather than as the finding it is. Both modes are checked, because they build
    coverage differently.
    """
    hazard_path = _write(tmp_path / "haz.tif", np.full((4, 4), -9999.0), nodata=-9999.0)
    pop_path = _write(tmp_path / "pop.tif", np.full((4, 4), 10.0))
    admin = _admin([box(0, 0, 400, 400)], ["dry"])

    for mode in ("fraction", "binary"):
        out = exposed_population(hazard_path, pop_path, admin, mode=mode)
        assert out["exposed_pop"].iat[0] == pytest.approx(0.0), mode
        assert out["hazard_coverage"].iat[0] == pytest.approx(1.0), mode


def test_a_unit_outside_the_hazard_extent_is_still_not_measured(tmp_path):
    """`nodata_means_dry` must not turn "off the map" into a measured zero.

    The population grid reaches further east than the hazard raster, so the
    eastern unit sits outside the hazard's footprint entirely: coverage 0 and
    `exposed_pop` None, the distinction the column exists for. The western unit is
    covered, and wet in its top-left cell.
    """
    hazard = np.full((4, 2), -9999.0)
    hazard[0, 0] = 3.0
    hazard_path = _write(tmp_path / "haz.tif", hazard, nodata=-9999.0)
    pop_path = _write(tmp_path / "pop.tif", np.full((4, 4), 10.0))
    admin = _admin([box(0, 0, 200, 400), box(200, 0, 400, 400)], ["in", "out"])

    for mode in ("fraction", "binary"):
        out = exposed_population(hazard_path, pop_path, admin, mode=mode)
        assert out["hazard_coverage"].iat[0] == pytest.approx(1.0), mode
        assert out["exposed_pop"].iat[0] > 0, mode
        assert out["hazard_coverage"].iat[1] == pytest.approx(0.0), mode
        # isna, not `is None`: beside a measured row pandas holds the column as
        # float and the None arrives as NaN. Same reading, different object.
        assert out["exposed_pop"].isna().iat[1], mode


def test_an_integer_hazard_raster_does_not_crash_the_default_mode(tmp_path):
    """uint16 centimetres is the real JRC observed layer, not an edge case.

    `.filled(-np.inf)` on a masked integer band raised
    `TypeError: Cannot convert fill_value -inf to dtype uint16`, so the default
    mode died on the declared format of `jrc_observed_flood_depth` - and on the
    Walloon class codes too. Every other fixture here is float32, which is why
    nothing caught it. The nodata cell matters: without a masked cell numpy's
    `filled` takes a fast path and never casts the fill value.

    Note the threshold is compared in the BAND's units, so 50 centimetres here.
    """
    hazard = np.zeros((4, 4), dtype="uint16")
    hazard[:, :2] = 300          # 3 m, in centimetres; the right half stays 0
    hazard_path = _write(tmp_path / "haz.tif", hazard, nodata=0, dtype="uint16")
    pop_path = _write(tmp_path / "pop.tif", np.full((4, 4), 10.0))
    admin = _admin([box(0, 0, 400, 400)], ["whole"])

    out = exposed_population(hazard_path, pop_path, admin, min_depth_m=50)
    # The left half is 3 m deep: 8 cells x 10 people.
    assert out["exposed_pop"].iat[0] == pytest.approx(80.0)
    # All of it: the default reading is that nodata is ground the layer looked at
    # and found dry, which is what the 0 means on a depth raster.
    assert out["hazard_coverage"].iat[0] == pytest.approx(1.0)

    # Asked to read nodata as unobserved, the same layer is half covered, because
    # it declares nodata = 0 and a dry cell and an unobserved one are then the
    # same value. A property of the source, not of this code - and the reason the
    # figure has to travel with its coverage rather than alone.
    clipped = exposed_population(
        hazard_path, pop_path, admin, min_depth_m=50, nodata_means_dry=False
    )
    assert clipped["hazard_coverage"].iat[0] == pytest.approx(0.5)


def test_a_misspelled_mode_raises_instead_of_switching_the_measurement(rasters):
    """`mode="fracton"` used to fall through to the binary branch, so a typo
    returned the conservative over-estimate (1000 against 250 on the one-cell
    fixture) under the name of the other measurement."""
    pop_path, hazard_path = rasters
    admin = _admin([box(0, 0, 400, 400)], ["whole"])
    with pytest.raises(ValueError, match="mode must be one of"):
        exposed_population(hazard_path, pop_path, admin, mode="fracton")


# --- What `expected_annual_exposure` integrates, and what it does not ---------


def _three_return_periods(exposure):
    """RP 10 / 100 / 500, the sampling the kit actually ships with."""
    import pandas as pd

    return pd.DataFrame(
        {
            "lau_id": ["u"] * 3,
            "return_period": [10, 100, 500],
            "annual_probability": [0.1, 0.01, 0.002],
            "exposed_pop": exposure,
        }
    )


def test_the_truncated_probability_band_is_reported_with_the_figure():
    """RP {10, 100, 500} integrates p in [0.002, 0.1] - 10% of the probability
    mass. The 90% above it used to be absent from both the figure and the output:
    closing it to zero exposure at p = 1 adds 45, more than the 32.6 reported. The
    band and that tail are columns now, so the figure cannot be read as an EAD by
    accident."""
    out = expected_annual_exposure(_three_return_periods([100.0, 500.0, 900.0]))
    row = out.iloc[0]
    assert row["expected_annual_exposure"] == pytest.approx(32.6)
    assert row["probability_band_low"] == pytest.approx(0.002)
    assert row["probability_band_high"] == pytest.approx(0.1)
    # (100 + 0) / 2 * (1.0 - 0.1): exposure falling linearly to zero at p = 1.
    assert row["frequent_tail_exposure"] == pytest.approx(45.0)
    assert row["expected_annual_exposure_closed"] == pytest.approx(77.6)
    assert row["status"] == "integrated"
    assert row["n_return_periods"] == 3


def test_a_single_return_period_is_refused_not_integrated_to_zero():
    """np.trapezoid of one sample is 0.0 - "nobody is ever exposed" - and that was
    returned silently for a table with one scenario in it."""
    import pandas as pd

    table = pd.DataFrame(
        {"lau_id": ["u"], "return_period": [100],
         "annual_probability": [0.01], "exposed_pop": [500.0]}
    )
    row = expected_annual_exposure(table).iloc[0]
    assert np.isnan(row["expected_annual_exposure"])
    assert np.isnan(row["expected_annual_exposure_closed"])
    assert row["status"] == "insufficient_return_periods"
    assert row["n_return_periods"] == 1


def test_one_unmeasured_scenario_says_so_instead_of_returning_a_bare_nan():
    """A unit the hazard layer does not cover in one scenario has no `exposed_pop`
    there, and the NaN propagated through the integral with nothing to say why.
    Integrating the remaining scenarios would be worse: it would narrow the band
    silently and report the result as a full-set figure."""
    row = expected_annual_exposure(_three_return_periods([100.0, None, 900.0])).iloc[0]
    assert np.isnan(row["expected_annual_exposure"])
    assert np.isnan(row["probability_band_low"])
    assert row["status"] == "missing_exposure"
    assert row["n_return_periods"] == 3


def test_an_unobserved_area_with_nobody_in_it_is_not_extrapolated_onto(tmp_path):
    """The extrapolation is weighted by people, not by cells.

    Two population cells, both fully flooded where the layer looked: one holds
    1,000 people and was observed, the other holds nobody and was not. The
    honest answer is 1,000. Dividing by the unweighted cell mean of coverage -
    0.5 here - reported 2,000, extrapolating the flood onto ground that contains
    no one. This is the domain-edge case on every coastal unit.
    """
    hazard = np.array([[3.0], [-9999.0]])
    hazard_path = _write(tmp_path / "haz.tif", hazard, nodata=-9999.0,
                         transform=from_origin(0, 2000, 1000, 1000))
    pop_path = _write(
        tmp_path / "pop.tif", np.array([[1000.0], [0.0]]),
        transform=from_origin(0, 2000, 1000, 1000),
    )
    admin = _admin([box(0, 0, 1000, 2000)], ["coastal"])
    out = exposed_population(
        hazard_path, pop_path, admin, mode="fraction", nodata_means_dry=False
    )
    assert out["exposed_pop"].iat[0] == pytest.approx(1000.0)
    assert out["exposed_pop_observed"].iat[0] == pytest.approx(1000.0)
    assert out["hazard_coverage"].iat[0] == pytest.approx(0.5), (
        "the area share is still reported as the qualifier it is"
    )


# --- the build checkpoint -------------------------------------------------------

def test_a_finished_return_period_is_parked_before_the_next_one_starts(tmp_path):
    """The defect this exists to stop, measured on 7 October 2026.

    The build held every return period in memory and wrote once at the end, so an
    interruption cost the whole run. The Linux OOM killer took the process during
    RP100 - 15.7 GB resident against a 16 GB WSL cap - after SEVEN periods had
    finished, and all seven were lost. A continental pass is about eight minutes,
    so an hour of compute was thrown away by where the write happened, not by the
    crash.

    The part name carries the parameters that change the numbers, because a part
    built at another depth threshold or in another mode is a different
    measurement and reusing it silently would be worse than recomputing it.
    """
    from scripts.build_exposure import _part_path

    base = _part_path(100, mode="fraction", min_depth_m=0.5, masks=["a", "b"])
    assert base.name.startswith("rp100")

    # Anything that changes the measurement changes the file.
    assert _part_path(100, mode="binary", min_depth_m=0.5, masks=["a", "b"]) != base
    assert _part_path(100, mode="fraction", min_depth_m=0.0, masks=["a", "b"]) != base
    assert _part_path(100, mode="fraction", min_depth_m=0.5, masks=["a"]) != base
    # And a different period is a different file, obviously.
    assert _part_path(500, mode="fraction", min_depth_m=0.5, masks=["a", "b"]) != base


def test_keeping_one_mask_or_the_other_is_two_different_parts():
    """`--keep-permanent-water` and `--keep-spurious-areas` each leave ONE mask.

    A name built from the mask count alone gave both runs the same file, so the
    second silently reused the first one's numbers.
    """
    from scripts.build_exposure import PERMANENT_WATER, SPURIOUS_AREAS, _part_path

    water_only = _part_path(100, mode="fraction", min_depth_m=0.5, masks=[PERMANENT_WATER])
    spurious_only = _part_path(100, mode="fraction", min_depth_m=0.5, masks=[SPURIOUS_AREAS])
    assert water_only != spurious_only


def test_the_default_parts_keep_the_name_they_were_built_under():
    """Both masks (the default) and no mask keep their names, so the nine parts
    already on disk are still found and a rerun does not recompute them."""
    from scripts.build_exposure import PERMANENT_WATER, SPURIOUS_AREAS, _part_path

    both = _part_path(100, mode="fraction", min_depth_m=0.5, masks=[PERMANENT_WATER, SPURIOUS_AREAS])
    assert both.name == "rp100_fraction_d0.5_m2.parquet"
    assert _part_path(100, mode="fraction", min_depth_m=0.5, masks=[]).name == "rp100_fraction_d0.5_m0.parquet"


def test_a_targeted_rebuild_does_not_shrink_the_frozen_table():
    """`--return-period` narrows what is COMPUTED, never what is written.

    Building one period used to rewrite `exposure.parquet` with that period
    alone, which looks complete to every reader - the UIs would show one scenario
    and no error. Measured on 7 October 2026 mid-build: the table went from
    84,407 bytes of nine periods to 64,370 bytes of one. The assembly now reads
    every part parked under the same parameters, so the frozen table only ever
    grows.

    Pinned on the naming, which is what makes the glob correct: the suffix after
    the period is the parameter tag, identical across periods of one run and
    different across runs that measured something else.
    """
    from scripts.build_exposure import _part_path

    names = [
        _part_path(rp, mode="fraction", min_depth_m=0.5, masks=["a", "b"]).name
        for rp in (10, 100, 500)
    ]
    suffixes = {name.split("_", 1)[1] for name in names}
    assert len(suffixes) == 1, "periods of one run must share a parameter tag"

    other = _part_path(10, mode="binary", min_depth_m=0.5, masks=["a", "b"]).name
    assert other.split("_", 1)[1] not in suffixes, (
        "a different measurement must not be swept into the same assembly"
    )
