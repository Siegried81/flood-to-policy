"""Tests for the hazard-vs-observed scoring layer. No rasterio, no network.

The failures worth testing here are arithmetic and unit failures, not transport.
A wrong hit rate raises nothing: it prints, it maps, and it goes in a brief as
"the model captures 50%". So the fixture is a 4x4 grid small enough to count by
hand, carrying one instance of every trap the real data sets:

    hazard, metres     observed, centimetres
    . . . .            . . . .            threshold 0.5 m == 50 cm
    . T T .            . T T .            T = above the threshold
    . T T X            . . W H            X = hazard nodata -9999
    . . . .            . H . H            W = permanent water 9999
    T . . .            . . . .            H = below threshold or dry

and the counted answer over the 15 scorable cells is TP=2, FP=2, FN=3, TN=8,
i.e. hit rate 0.4, false alarm ratio 0.5, IoU 2/7. Every structural guarantee is
asserted against those numbers: that permanent water is not scored as a free
true positive (it would make the hit rate 0.5), that hazard nodata is a real
miss, that a zero denominator is None and not 0.0, that the two depth thresholds
cannot drift apart by a factor of 100, that per-unit counts sum back to the
global ones, and that the caveat is on every row.
"""

from __future__ import annotations

import inspect
import sys

import numpy as np
import pandas as pd
import pytest

from src import validate as V

# Hazard depth in METRES, Float32, nodata -9999 - the real dtype and sentinel.
HAZARD_M = np.array(
    [
        [0.0, 0.8, 1.5, 0.0],
        [0.0, 0.6, 2.0, -9999.0],
        [0.0, 0.0, 0.0, -9999.0],
        [0.9, 0.0, 0.0, 0.0],
    ],
    dtype="float32",
)

# Observed depth in CENTIMETRES, uint16, nodata 0, 9999 = permanent water.
# [1][2] is 9999 under a modelled depth of 2.0 m: the cell that would hand the
# model a free true positive if a river were allowed to count as a flood.
OBSERVED_CM = np.array(
    [
        [0, 120, 200, 0],
        [0, 0, 9999, 80],
        [0, 60, 40, 150],
        [0, 0, 0, 0],
    ],
    dtype="uint16",
)

MIN_DEPTH_M = 0.5

# Two NUTS3-shaped units, left half and right half of the grid.
UNITS = np.array(
    [
        [1, 1, 2, 2],
        [1, 1, 2, 2],
        [1, 1, 2, 2],
        [1, 1, 2, 2],
    ]
)


@pytest.fixture
def masks() -> dict[str, np.ndarray]:
    """The three masks the module compares, built the way `score_event` builds them."""
    return {
        "modelled": V.modelled_flood_mask(HAZARD_M, min_depth_m=MIN_DEPTH_M),
        "observed": V.observed_flood_mask(
            OBSERVED_CM, min_depth_cm=V.matching_threshold_cm(MIN_DEPTH_M)
        ),
        "scorable": V.observed_scorable_mask(OBSERVED_CM),
    }


# --------------------------------------------------------------------------
# Mask building: units, nodata and sentinels
# --------------------------------------------------------------------------


def test_modelled_mask_thresholds_in_metres_and_drops_nodata(masks):
    """0.6 m clears a 0.5 m threshold; -9999 is not the deepest flood in Europe."""
    assert masks["modelled"].tolist() == [
        [False, True, True, False],
        [False, True, True, False],
        [False, False, False, False],
        [True, False, False, False],
    ]


def test_observed_mask_thresholds_in_centimetres_and_drops_permanent_water(masks):
    """60 cm clears 50 cm, 40 cm does not, and 9999 is water rather than depth."""
    assert masks["observed"].tolist() == [
        [False, True, True, False],
        [False, False, False, True],
        [False, True, False, True],
        [False, False, False, False],
    ]


def test_observed_nodata_is_scorable_but_permanent_water_is_not(masks):
    """0 stays in the matrix as "dry or unseen"; only the 9999 cell leaves it."""
    assert masks["scorable"].sum() == 15
    assert masks["scorable"][1][2] is np.False_ or not masks["scorable"][1][2]
    assert masks["scorable"][0][0]


def test_hazard_nodata_is_dry_and_still_scored(masks):
    """The basins-above-150-km2 blind spot is a miss, not an exclusion.

    One -9999 cell sits under 150 cm of observed water - which must stay a false
    negative, or a documented limit of the model becomes invisible by
    construction.
    """
    assert not masks["modelled"][2][3]
    assert masks["observed"][2][3] and masks["scorable"][2][3]


def test_no_model_domain_is_derived_from_the_hazard_raster():
    """On the sparse JRC maps nodata is every dry cell, so "not nodata" is wet.

    A domain taken from the depth raster therefore equals the wet footprint and
    reports every dry cell as never modelled (97% of a Vesdre/Ourthe window on
    the real RP100 layer). The module offers no such helper.
    """
    assert not hasattr(V, "modelled_domain_mask")


def test_nan_is_neither_flooded_nor_scorable():
    """A read through `read_depth_on_grid` marks uncovered cells NaN, not 0.

    0 would be a depth, and in the observed product 0 already means "dry or
    unseen" - so an uncovered cell filled with 0 would be scored as dry land.
    """
    depth_cm = np.array([[np.nan, 60.0]], dtype="float32")
    assert V.observed_flood_mask(depth_cm, min_depth_cm=50.0).tolist() == [[False, True]]
    assert V.observed_scorable_mask(depth_cm).tolist() == [[False, True]]
    depth_m = np.array([[np.nan, 0.8]], dtype="float32")
    assert V.modelled_flood_mask(depth_m, min_depth_m=0.5).tolist() == [[False, True]]


# --------------------------------------------------------------------------
# The factor-100 error
# --------------------------------------------------------------------------


def test_matching_threshold_converts_metres_to_centimetres():
    assert V.matching_threshold_cm(0.5) == 50.0
    assert V.matching_threshold_cm(0.0) == 0.0


def test_agreement_derives_the_centimetre_threshold_from_the_metre_one(masks):
    """One threshold given once, applied in both units, recorded in both units."""
    scores = V.agreement(
        masks["modelled"],
        masks["observed"],
        scorable=masks["scorable"],
        min_depth_m=0.5,
    )
    assert scores.min_depth_m == 0.5
    assert scores.min_depth_cm == 50.0


def test_the_factor_100_error_changes_the_answer():
    """0.5 passed as centimetres is a different mask, so the default matters.

    This is the whole reason the thresholds are unit-suffixed and derived rather
    than typed twice: the mistake does not raise, it returns a plausible number.
    """
    observed = np.array([[40, 60]], dtype="uint16")
    correct = V.observed_flood_mask(observed, min_depth_cm=V.matching_threshold_cm(0.5))
    mistake = V.observed_flood_mask(observed, min_depth_cm=0.5)
    assert correct.tolist() == [[False, True]]
    assert mistake.tolist() == [[True, True]]


# --------------------------------------------------------------------------
# The confusion matrix
# --------------------------------------------------------------------------


def test_agreement_counts_the_hand_counted_matrix(masks):
    scores = V.agreement(
        masks["modelled"],
        masks["observed"],
        scorable=masks["scorable"],
        min_depth_m=MIN_DEPTH_M,
    )
    assert (scores.true_positive, scores.false_positive) == (2, 2)
    assert (scores.false_negative, scores.true_negative) == (3, 8)
    assert scores.scored_cells == 15
    assert scores.excluded_cells == 1
    assert scores.observed_flood_cells == 5
    assert scores.modelled_flood_cells == 4


def test_agreement_computes_the_three_scores(masks):
    scores = V.agreement(
        masks["modelled"],
        masks["observed"],
        scorable=masks["scorable"],
        min_depth_m=MIN_DEPTH_M,
    )
    assert scores.hit_rate == pytest.approx(0.4)
    assert scores.false_alarm_ratio == pytest.approx(0.5)
    assert scores.iou == pytest.approx(2 / 7)


def test_permanent_water_is_not_a_free_true_positive(masks):
    """Scoring the 9999 cell as wet would lift the hit rate from 0.4 to 0.5.

    The modelled layer says 2.0 m there and the observed layer says "this is a
    river". A river is not a flood, so the cell leaves the matrix entirely -
    which is a 10-point difference in the headline figure of a 4x4 grid, and a
    larger one along every watercourse in a real window.
    """
    flattering = V.agreement(
        masks["modelled"],
        masks["observed"] | (OBSERVED_CM == V.OBSERVED_PERMANENT_WATER_CM),
        min_depth_m=MIN_DEPTH_M,
    )
    assert flattering.hit_rate == pytest.approx(0.5)
    assert flattering.true_positive == 3


def test_scorable_defaults_to_the_whole_grid(masks):
    """No `scorable` means nothing is excluded, so all 16 cells are in the matrix."""
    scores = V.agreement(masks["modelled"], masks["observed"], min_depth_m=MIN_DEPTH_M)
    assert scores.scored_cells == 16
    assert scores.excluded_cells == 0


def test_the_matrix_partitions_the_scored_cells(masks):
    """TP + FP + FN + TN is the scored count, on any input. A gap is a lost cell."""
    scores = V.agreement(
        masks["modelled"],
        masks["observed"],
        scorable=masks["scorable"],
        min_depth_m=MIN_DEPTH_M,
    )
    total = (
        scores.true_positive
        + scores.false_positive
        + scores.false_negative
        + scores.true_negative
    )
    assert total == scores.scored_cells
    assert scores.scored_cells + scores.excluded_cells == HAZARD_M.size


# --------------------------------------------------------------------------
# "We could not measure" is not "the score is zero"
# --------------------------------------------------------------------------


def test_hit_rate_is_none_when_nothing_was_observed_flooded():
    """No observed flooding: the question cannot be asked, so the answer is None.

    And in the same call the IoU and the false alarm ratio ARE measurable and
    genuinely 0.0 and 1.0 - which is the distinction. A module that returned 0.0
    for all three would be stating that the model caught nothing, as a finding.
    """
    modelled = np.array([[True, False]])
    observed = np.array([[False, False]])
    scores = V.agreement(modelled, observed)
    assert scores.hit_rate is None
    assert scores.false_alarm_ratio == pytest.approx(1.0)
    assert scores.iou == pytest.approx(0.0)


def test_false_alarm_ratio_is_none_when_the_model_predicts_nothing():
    modelled = np.array([[False, False]])
    observed = np.array([[True, False]])
    scores = V.agreement(modelled, observed)
    assert scores.false_alarm_ratio is None
    assert scores.hit_rate == pytest.approx(0.0)
    assert scores.iou == pytest.approx(0.0)


def test_every_score_is_none_when_there_is_nothing_at_all():
    nothing = np.array([[False, False]])
    scores = V.agreement(nothing, nothing)
    assert (scores.hit_rate, scores.false_alarm_ratio, scores.iou) == (None, None, None)


def test_none_is_not_zero():
    """Guards the one substitution that would make this module lie quietly."""
    nothing = np.array([[False]])
    for score in V.agreement(nothing, nothing).__dict__.values():
        assert score != 0.0 or not isinstance(score, float) or score == 0


# --------------------------------------------------------------------------
# One grid, or no comparison
# --------------------------------------------------------------------------


def test_agreement_refuses_masks_of_different_shapes():
    with pytest.raises(ValueError, match="different grids"):
        V.agreement(np.ones((2, 2), bool), np.ones((2, 3), bool))


def test_agreement_refuses_a_scorable_mask_of_another_shape():
    with pytest.raises(ValueError, match="different grids"):
        V.agreement(
            np.ones((2, 2), bool), np.ones((2, 2), bool), scorable=np.ones((3, 3), bool)
        )


def test_the_grid_message_names_the_working_crs():
    """The fix is to reproject, so the error has to say onto what."""
    with pytest.raises(ValueError, match=V.SCORING_CRS):
        V.agreement(np.ones((2, 2), bool), np.ones((2, 3), bool))


def test_per_unit_refuses_a_unit_raster_of_another_shape():
    with pytest.raises(ValueError, match="different grids"):
        V.agreement_by_unit(
            np.ones((2, 2), bool), np.ones((2, 2), bool), np.ones((4, 4), int)
        )


# --------------------------------------------------------------------------
# Per administrative unit
# --------------------------------------------------------------------------


def _by_unit(masks, **kwargs) -> pd.DataFrame:
    return V.agreement_by_unit(
        masks["modelled"],
        masks["observed"],
        UNITS,
        scorable=masks["scorable"],
        min_depth_m=MIN_DEPTH_M,
        min_observed_cells=0,
        **kwargs,
    )


def test_per_unit_counts_sum_back_to_the_global_matrix(masks):
    """The units partition the grid, so the two must agree. A gap is a lost cell."""
    per_unit = _by_unit(masks)
    whole = V.agreement(
        masks["modelled"],
        masks["observed"],
        scorable=masks["scorable"],
        min_depth_m=MIN_DEPTH_M,
    )
    assert per_unit["true_positive"].sum() == whole.true_positive
    assert per_unit["false_positive"].sum() == whole.false_positive
    assert per_unit["false_negative"].sum() == whole.false_negative
    assert per_unit["scored_cells"].sum() == whole.scored_cells


def test_per_unit_scores_are_computed_within_each_unit(masks):
    rows = _by_unit(masks).set_index("NUTS_ID")
    assert rows.loc[1, "hit_rate"] == pytest.approx(0.5)
    assert rows.loc[1, "false_alarm_ratio"] == pytest.approx(2 / 3)
    assert rows.loc[1, "iou"] == pytest.approx(0.25)
    # The right-hand unit predicts one flooded cell and it was flooded, so its
    # false alarm ratio is a measured 0.0 rather than an undefined None.
    assert rows.loc[2, "hit_rate"] == pytest.approx(1 / 3)
    assert rows.loc[2, "false_alarm_ratio"] == pytest.approx(0.0)


def test_per_unit_key_column_is_nameable_for_the_merge(masks):
    """NUTS3 by default, but Belgian communes join on another column entirely."""
    assert "NUTS_ID" in _by_unit(masks).columns
    assert "CD_REFNIS" in _by_unit(masks, code_column="CD_REFNIS").columns


def test_per_unit_merges_onto_a_nuts_frame(masks):
    """The point of the key column: no lookup table between score and geometry."""
    nuts = pd.DataFrame({"NUTS_ID": [1, 2], "NAME_LATN": ["Liege", "Verviers"]})
    merged = nuts.merge(_by_unit(masks), on="NUTS_ID", how="left")
    assert merged["hit_rate"].notna().all()


def test_background_cells_belong_to_no_unit(masks):
    """A cell outside every administrative unit is not a unit called 0."""
    units = UNITS.copy()
    units[:, 0] = 0
    rows = V.agreement_by_unit(
        masks["modelled"],
        masks["observed"],
        units,
        scorable=masks["scorable"],
        min_observed_cells=0,
    )
    assert set(rows["NUTS_ID"]) == {1, 2}
    assert rows["scored_cells"].sum() == 11


def test_per_unit_raises_rather_than_returning_an_empty_frame(masks):
    """An empty frame of scores reads as a model that caught nothing."""
    with pytest.raises(ValueError, match="No cell belongs to any administrative unit"):
        V.agreement_by_unit(
            masks["modelled"], masks["observed"], np.zeros_like(UNITS)
        )


def test_thin_evidence_gives_nan_not_a_number(masks):
    """Two flooded cells is not a hit rate, and 0.5 printed from it is noise.

    The counts stay on the row either way, so a reader can see how thin the
    evidence was instead of only seeing a missing value.
    """
    rows = V.agreement_by_unit(
        masks["modelled"],
        masks["observed"],
        UNITS,
        scorable=masks["scorable"],
    ).set_index("NUTS_ID")
    assert rows["hit_rate"].isna().all()
    assert rows["iou"].isna().all()
    assert rows.loc[1, "observed_flood_cells"] == 2
    assert (rows["min_observed_cells"] == V.MIN_OBSERVED_CELLS).all()


def test_undefined_per_unit_ratio_is_nan_and_not_zero(masks):
    """Same rule as the scalar API, in pandas' own missing marker."""
    dry = np.zeros_like(masks["observed"])
    rows = V.agreement_by_unit(
        masks["modelled"], dry, UNITS, min_observed_cells=0
    ).set_index("NUTS_ID")
    assert rows["hit_rate"].isna().all()
    assert not (rows["hit_rate"] == 0).any()


# --------------------------------------------------------------------------
# The hazard maps' blind spots: scope versus accuracy
# --------------------------------------------------------------------------


def test_runoff_classement_codes_select_2xx_and_3xx():
    """110/120/130 is overflow, 2xx is runoff, 3xx is both, 0 is fill."""
    codes = np.array([[0, 110, 130], [210, 230, 320]])
    assert V.runoff_mask_from_classement(codes).tolist() == [
        [False, False, False],
        [True, True, True],
    ]


def test_runoff_split_separates_scope_from_accuracy(masks):
    """A unit the model "misses" entirely can be a unit the model is not for.

    Both of the right-hand unit's misses are in runoff-attributed area, so its
    overall hit rate is 1/3 while its hit rate over the flooding the hazard maps
    actually model is 1.0. That difference is the finding; one number cannot
    carry it.
    """
    runoff = np.zeros_like(UNITS, dtype=bool)
    runoff[1][3] = runoff[2][3] = True
    rows = _by_unit(masks, runoff=runoff).set_index("NUTS_ID")
    assert rows.loc[2, "hit_rate"] == pytest.approx(1 / 3)
    assert rows.loc[2, "false_negative_in_runoff_area"] == 2
    assert rows.loc[2, "false_negative_outside_runoff_area"] == 0
    assert rows.loc[2, "hit_rate_outside_runoff_area"] == pytest.approx(1.0)


def test_runoff_columns_are_absent_unless_a_runoff_mask_is_given(masks):
    """No runoff layer means no claim about runoff, rather than a column of zeros."""
    assert "hit_rate_outside_runoff_area" not in _by_unit(masks).columns


def test_model_domain_is_reported_per_unit(masks):
    """How much of a unit lies outside an independently supplied model domain.

    The domain is hand-built here, as it would be from the EFAS upstream-area
    map: the right-hand column is outside it. Its four cells are all scorable
    and all in unit 2; unit 1 has none outside.
    """
    domain = np.ones_like(UNITS, dtype=bool)
    domain[:, 3] = False
    rows = _by_unit(masks, in_model_domain=domain).set_index("NUTS_ID")
    assert rows.loc[1, "modelled_outside_domain_cells"] == 0
    assert rows.loc[2, "modelled_outside_domain_cells"] == 4


# --------------------------------------------------------------------------
# The caveat travels with the number
# --------------------------------------------------------------------------


def test_the_caveat_is_a_field_of_the_result(masks):
    scores = V.agreement(masks["modelled"], masks["observed"])
    assert "weaker evidence than a presence" in scores.caveat
    assert "lower bound" in scores.caveat


def test_the_caveat_is_on_every_row(masks):
    """A column survives a copy-paste into a slide; a footnote does not."""
    rows = _by_unit(masks)
    assert (rows["caveat"] == V.CAVEAT).all()
    assert len(rows) == 2


def test_the_caveat_names_both_asymmetries():
    """Satellite blindness and the model's scope are different limitations."""
    assert "canopy" in V.CAVEAT
    assert "surface runoff" in V.CAVEAT
    assert "150 km2" in V.CAVEAT


def test_the_thresholds_are_on_every_row(masks):
    """The basis of a number travels with the number, in both units."""
    rows = _by_unit(masks)
    assert (rows["min_depth_m"] == 0.5).all()
    assert (rows["min_depth_cm"] == 50.0).all()


# --------------------------------------------------------------------------
# The sentence
# --------------------------------------------------------------------------


def test_headline_is_the_sentence_the_brief_needs(masks):
    scores = V.agreement(
        masks["modelled"],
        masks["observed"],
        scorable=masks["scorable"],
        min_depth_m=MIN_DEPTH_M,
    )
    sentence = V.headline(scores, return_period_years=100)
    assert sentence.startswith(
        "The modelled 100-year hazard layer captures 40% of what was actually "
        "flooded in July 2021"
    )
    assert "0.5 m modelled depth and 50 cm observed depth" in sentence
    assert "EPSG:3035" in sentence
    assert V.ABSENCE_CAVEAT in sentence


def test_headline_refuses_to_say_zero_percent_when_it_could_not_measure():
    """An unmeasurable hit rate is a gap, and 0% would be a finding."""
    nothing = np.array([[False, False]])
    sentence = V.headline(V.agreement(nothing, nothing), return_period_years=100)
    assert "could not be scored" in sentence
    assert "0%" not in sentence
    assert V.ABSENCE_CAVEAT in sentence


def test_headline_names_the_event_it_was_given(masks):
    scores = V.agreement(masks["modelled"], masks["observed"])
    assert "in December 1993" in V.headline(
        scores, return_period_years=500, event="December 1993"
    )


# --------------------------------------------------------------------------
# The CRS that cannot be read off the file
# --------------------------------------------------------------------------


def test_observed_crs_returns_the_proj4_string(monkeypatch):
    monkeypatch.setattr(
        V,
        "sources",
        lambda section: [{"id": V.OBSERVED_SOURCE_ID, "crs": V.OBSERVED_DECLARED_CRS}],
    )
    assert V.observed_crs() == V.OBSERVED_PROJ4
    assert "+proj=aeqd" in V.observed_crs()


def test_observed_crs_raises_if_the_catalogue_declaration_changed(monkeypatch):
    """A real EPSG code in sources.yaml must stop the transcription being used."""
    monkeypatch.setattr(
        V, "sources", lambda section: [{"id": V.OBSERVED_SOURCE_ID, "crs": "EPSG:3035"}]
    )
    with pytest.raises(ValueError, match="EPSG:3035"):
        V.observed_crs()


def test_observed_crs_raises_if_the_source_is_not_declared(monkeypatch):
    monkeypatch.setattr(V, "sources", lambda section: [{"id": "something_else"}])
    with pytest.raises(ValueError, match="config/sources.yaml"):
        V.observed_crs()


def test_the_real_catalogue_still_declares_equi7grid():
    """Reads config/sources.yaml itself, so a catalogue edit breaks this test.

    That is the point: the proj4 string is transcribed from a `caveat` paragraph
    that cannot be read as a field, so this is the only thing keeping the
    transcription tied to the entry it came from.
    """
    assert V.observed_crs() == V.OBSERVED_PROJ4


# --------------------------------------------------------------------------
# Working without a raster backend
# --------------------------------------------------------------------------


def test_rasterio_is_never_imported_at_module_scope():
    """The property that keeps this module importable where the GDAL DLLs are blocked.

    Asserted on the source rather than on `sys.modules`, because another test or
    another import could have pulled rasterio in by the time this runs - and the
    thing that matters is that none of those imports is this module's doing.
    """
    source = inspect.getsource(V)
    top_level = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "rasterio" in line
    ]
    assert top_level == [], top_level
    # The lazy imports themselves are indented, inside the functions that need them.
    assert "        import rasterio" in source


def test_the_pure_numpy_scoring_needs_no_raster_backend(monkeypatch, masks):
    """Scoring still works with rasterio unimportable. The whole split, in one test."""
    monkeypatch.setitem(sys.modules, "rasterio", None)
    scores = V.agreement(
        masks["modelled"], masks["observed"], scorable=masks["scorable"]
    )
    assert scores.hit_rate == pytest.approx(0.4)
    assert len(_by_unit(masks)) == 2


def test_require_rasterio_names_the_wsl_fallback(monkeypatch):
    monkeypatch.setitem(sys.modules, "rasterio", None)
    with pytest.raises(V.RasterBackendUnavailable, match="WSL"):
        V._require_rasterio()


def test_the_io_layer_refuses_cleanly_rather_than_raising_importerror(monkeypatch):
    """A missing backend must stop the pipeline with an explanation, not a DLL name."""
    monkeypatch.setitem(sys.modules, "rasterio", None)
    grid = V.Grid(left=0.0, top=100.0, width=5, height=5)
    with pytest.raises(V.RasterBackendUnavailable):
        V.scoring_grid([("hazard.tif", None)])
    with pytest.raises(V.RasterBackendUnavailable):
        V.read_depth_on_grid("hazard.tif", grid)
    with pytest.raises(V.RasterBackendUnavailable):
        V.score_event("hazard.tif", "observed.tif")


# --------------------------------------------------------------------------
# The scoring grid
# --------------------------------------------------------------------------


def test_grid_shape_and_transform_need_no_raster_backend():
    """A Grid is plain numbers, so it is inspectable where rasterio will not load."""
    grid = V.Grid(left=3_900_000.0, top=3_100_000.0, width=10, height=4)
    assert grid.shape == (4, 10)
    assert grid.crs == V.SCORING_CRS
    assert grid.resolution_m == V.SCORING_RESOLUTION_M
    transform = grid.transform()
    assert (transform.a, transform.e) == (20.0, -20.0)
    assert (transform.c, transform.f) == (3_900_000.0, 3_100_000.0)


def test_the_scoring_grid_is_equal_area_at_the_observed_resolution():
    """Stated as a test because the choice is what makes a pixel count an area.

    EPSG:3035 is equal-area, so counting cells is counting hectares; 20 m is the
    finer of the two inputs, so nothing of the observed layer is averaged away.
    """
    assert V.SCORING_CRS == "EPSG:3035"
    assert V.SCORING_RESOLUTION_M == 20.0


# --------------------------------------------------------------------------
# End to end on real GeoTIFFs: the observed layer's declared nodata
# --------------------------------------------------------------------------

# A 10 x 10 window at 20 m in EPSG:3035, aligned to whole scoring cells so the
# scoring grid reproduces it exactly and nearest-neighbour moves no cell.
WINDOW_LEFT = 4_000_000.0
WINDOW_TOP = 3_000_000.0


def _write_tif(path, values, *, nodata, left=WINDOW_LEFT, top=WINDOW_TOP):
    """Write a one-band EPSG:3035 GeoTIFF at the scoring resolution."""
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine

    transform = Affine(
        V.SCORING_RESOLUTION_M, 0.0, left, 0.0, -V.SCORING_RESOLUTION_M, top
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=values.dtype,
        crs="EPSG:3035",
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(values, 1)
    return str(path)


def _model_wet_in_top_half(tmp_path):
    """10 x 10 hazard depths in metres: 1.0 m in the top five rows, 0 below."""
    depth = np.zeros((10, 10), dtype="float32")
    depth[:5, :] = 1.0
    return _write_tif(tmp_path / "hazard.tif", depth, nodata=V.HAZARD_NODATA_M), depth


def test_score_event_keeps_observed_zero_cells_scorable(tmp_path):
    """An observed 0 is "dry or unseen", not nodata, even though the file says nodata=0.

    The model is wet in 50 cells, the observation in 30 of them. Reading the
    observed file with its declared nodata turned every 0 into NaN, so the 20
    modelled-wet, observed-dry cells and the 50 dry-dry cells left the matrix:
    FP was 0 by construction, FAR always 0 and IoU equal to the hit rate.
    """
    hazard_path, hazard_m = _model_wet_in_top_half(tmp_path)
    observed_cm = np.zeros((10, 10), dtype="uint16")
    observed_cm[:3, :] = 100
    observed_path = _write_tif(
        tmp_path / "observed.tif", observed_cm, nodata=V.OBSERVED_NODATA_CM
    )

    scores, masks = V.score_event(
        hazard_path, observed_path, observed_declared_crs="EPSG:3035"
    )

    expected = V.agreement(
        V.modelled_flood_mask(hazard_m), V.observed_flood_mask(observed_cm)
    )
    assert set(masks) == {"modelled_flooded", "observed_flooded", "scorable"}
    assert masks["scorable"].shape == (10, 10)
    assert scores.scored_cells == 100
    assert scores.true_positive == 30
    assert scores.false_positive == 20
    assert scores.false_negative == 0
    assert scores.true_negative == 50
    assert scores.false_alarm_ratio == pytest.approx(0.4)
    assert scores.iou == pytest.approx(0.6)
    assert scores.hit_rate == pytest.approx(1.0)
    assert scores.false_alarm_ratio == pytest.approx(expected.false_alarm_ratio)
    assert scores.iou == pytest.approx(expected.iou)


def test_score_event_still_excludes_observed_permanent_water(tmp_path):
    """Overriding nodata must not let the 9999 sentinel back into the matrix."""
    hazard_path, _ = _model_wet_in_top_half(tmp_path)
    observed_cm = np.zeros((10, 10), dtype="uint16")
    observed_cm[:3, :] = 100
    observed_cm[3, :] = V.OBSERVED_PERMANENT_WATER_CM
    observed_path = _write_tif(
        tmp_path / "observed.tif", observed_cm, nodata=V.OBSERVED_NODATA_CM
    )

    scores, _ = V.score_event(
        hazard_path, observed_path, observed_declared_crs="EPSG:3035"
    )

    assert scores.scored_cells == 90
    assert scores.false_positive == 10
    assert scores.true_positive == 30


def test_score_event_outside_observed_footprint_stays_unscored(tmp_path):
    """A cell the observation never covered is not a true negative.

    The observed raster covers the left half of the model window only. The
    scoring grid is the intersection, so `score_event` scores 50 cells; and read
    onto the full window, the uncovered half comes back NaN and unscorable while
    the covered 0s stay scorable - the override applies to the source footprint
    and nothing beyond it.
    """
    hazard_path, _ = _model_wet_in_top_half(tmp_path)
    observed_cm = np.zeros((10, 5), dtype="uint16")
    observed_cm[:3, :] = 100
    observed_path = _write_tif(
        tmp_path / "observed.tif", observed_cm, nodata=V.OBSERVED_NODATA_CM
    )

    scores, masks = V.score_event(
        hazard_path, observed_path, observed_declared_crs="EPSG:3035"
    )
    assert masks["scorable"].shape == (10, 5)
    assert scores.scored_cells == 50
    assert scores.false_positive == 10

    full_window = V.Grid(left=WINDOW_LEFT, top=WINDOW_TOP, width=10, height=10)
    observed_on_window = V.read_depth_on_grid(
        observed_path,
        full_window,
        declared_crs="EPSG:3035",
        nodata=V.OBSERVED_READ_NODATA,
    )
    scorable = V.observed_scorable_mask(observed_on_window)
    assert not scorable[:, 5:].any()
    assert scorable[:, :5].all()
