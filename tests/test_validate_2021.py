"""Tests for scripts/validate_2021.py on synthetic rasters and polygons. No network.

The script's real inputs are 6 GiB of rasters that CI does not have, so what is
tested here is every rule that moves a figure: which cells a pair is scored
over, the très faible class choice, the cell-centre rasterisation, the two
population variants and their order, and that resampling the population onto
the 100 m grid moves people without counting them twice.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import validate_2021 as S
from src import validate as V

# --------------------------------------------------------------------------
# Scoring pairs
# --------------------------------------------------------------------------

# 1 x 6 strip. The truth's domain stops at column 4; the model's coverage at 5.
WET = np.array([[True, True, False, True, False, True]])
FLOODED = np.array([[True, False, True, False, True, True]])
DOMAIN = np.array([[True, True, True, True, False, True]])
COVERAGE = np.array([[True, True, True, True, True, False]])


def test_a_pair_is_scored_over_domain_and_coverage_only():
    """Columns 4 and 5 leave the matrix: one outside the truth, one outside the map.

    Over columns 0-3: TP 1, FP 2, FN 1. Scoring the whole strip would add a
    miss at column 4 the truth never looked at and a hit at column 5 the map
    never spoke for.
    """
    out = S.score_table({"m": (WET, COVERAGE)}, {"t": (FLOODED, DOMAIN)}, window="w")
    row = out.iloc[0]
    assert (row.true_positive, row.false_positive, row.false_negative) == (1, 2, 1)
    assert row.scored_cells == 4
    # Below MIN_OBSERVED_CELLS, so the ratios are NaN and the counts stay.
    assert np.isnan(row.hit_rate) and np.isnan(row.csi)


def test_ratios_and_areas_when_the_evidence_is_thick():
    """Enough observed cells: hit rate, FAR and CSI from `validate.agreement`."""
    n = V.MIN_OBSERVED_CELLS
    wet = np.zeros((1, 4 * n), bool)
    flooded = np.zeros_like(wet)
    flooded[0, : 2 * n] = True
    wet[0, n: 3 * n] = True
    out = S.score_table({"m": (wet, None)}, {"t": (flooded, np.ones_like(wet))})
    row = out.iloc[0]
    assert row.hit_rate == pytest.approx(0.5)
    assert row.false_alarm_ratio == pytest.approx(0.5)
    assert row.csi == pytest.approx(1 / 3)
    assert row.observed_km2 == pytest.approx(2 * n * 0.0004)
    assert row.caveat == V.CAVEAT


def test_permanent_water_is_excluded_from_every_pair():
    exclude = np.array([[True, False, False, False, False, False]])
    out = S.score_table({"m": (WET, None)}, {"t": (FLOODED, np.ones_like(WET))},
                        exclude=exclude)
    assert out.iloc[0].scored_cells == 5
    assert out.iloc[0].true_positive == 1  # column 5 only; column 0 is water


def test_a_pair_with_nothing_to_score_is_left_out_not_zeroed():
    """The aléa map has no coverage in the Ahr window: no row, not a row of zeros."""
    nowhere = np.zeros_like(WET)
    out = S.score_table({"alea": (WET, nowhere), "jrc": (WET, None)},
                        {"t": (FLOODED, DOMAIN)})
    assert list(out["model"]) == ["jrc"]


def test_every_row_names_its_definitions():
    out = S.score_table({"alea_excl_tres_faible": (WET, None)},
                        {"wallonia_extent_2021": (FLOODED, DOMAIN)})
    assert "très faible excluded" in out.iloc[0].model_definition
    assert "cell-centre" in out.iloc[0].truth_definition


def test_truth_pairs_score_each_pair_once_over_both_domains():
    """Three truths, three pairs; and only the area both truths looked at."""
    a = (np.array([[True, True, False]]), np.array([[True, True, True]]))
    b = (np.array([[True, False, False]]), np.array([[True, False, True]]))
    c = (np.array([[False, False, True]]), np.array([[True, True, True]]))
    out = S.truth_pairs({"a": a, "b": b, "c": c})
    assert list(zip(out["model"], out["truth"])) == [("a", "b"), ("a", "c"), ("b", "c")]
    ab = out.iloc[0]
    assert ab.scored_cells == 2 and ab.true_positive == 1 and ab.false_positive == 0
    assert (out["kind"] == "truth_vs_truth").all()
    assert (out["caveat"] == V.ABSENCE_CAVEAT).all()


# --------------------------------------------------------------------------
# The très faible choice
# --------------------------------------------------------------------------


def test_alea_mask_includes_or_excludes_tres_faible_on_request():
    codes = np.array([[101, 110, 120, 130, 201, 230, 301, 330, np.nan, 65535, 0, 140]])
    incl = S.alea_mask(codes, include_tres_faible=True)
    excl = S.alea_mask(codes, include_tres_faible=False)
    assert incl.tolist() == [[True] * 8 + [False] * 4]
    assert excl.tolist() == [[False, True, True, True, False, True, False, True]
                             + [False] * 4]


def test_alea_mask_has_no_default_class_choice():
    with pytest.raises(TypeError):
        S.alea_mask(np.array([[101]]))  # type: ignore[call-arg]


# --------------------------------------------------------------------------
# Population: block rules and the two variants
# --------------------------------------------------------------------------


def test_block_any_and_block_centre():
    mask = np.zeros((5, 10), bool)
    mask[0, 0] = True       # corner of block 0: any, not centre
    mask[2, 7] = True       # centre of block 1
    assert S.block_any(mask, 5).tolist() == [[True, True]]
    assert S.block_centre(mask, 5).tolist() == [[False, True]]
    with pytest.raises(ValueError, match="odd"):
        S.block_centre(np.zeros((4, 4), bool), 2)


def test_conservative_counts_no_more_people_outside_than_upper():
    """A map that wets only a corner sub-cell: inside under ANY, outside under CENTRE.

    Two 100 m cells, both observed flooded at their centre, 10 and 30 people.
    The map wets the centre of the second and only a corner of the first.
    """
    flooded = np.zeros((5, 10), bool)
    flooded[2, 2] = flooded[2, 7] = True
    wet = np.zeros_like(flooded)
    wet[0, 0] = True
    wet[2, 7] = True
    pop = np.array([[10.0, 30.0]])
    out = S.population_outside(pop, {"m": (wet, None)},
                               {"t": (flooded, np.ones_like(flooded))}).set_index("variant")
    assert out.loc["conservative", "pop_in_truth"] == 40
    assert out.loc["conservative", "pop_in_truth_outside_model"] == 0
    assert out.loc["upper", "pop_in_truth_outside_model"] == 10
    assert out.loc["upper", "share_outside_model"] == pytest.approx(0.25)
    assert out.loc["conservative", "pop_inside_model_in_window"] == 40
    assert out.loc["upper", "pop_inside_model_in_window"] == 30


def test_population_in_truth_uses_the_centre_rule_and_the_coverage():
    """Observed only at a corner is not observed; outside the map's coverage is not counted."""
    flooded = np.zeros((5, 10), bool)
    flooded[0, 0] = True          # corner only: cell 0 not in the truth
    flooded[2, 7] = True
    coverage = np.zeros_like(flooded)
    coverage[:, :5] = True        # the map covers cell 0 only
    pop = np.array([[10.0, 30.0]])
    whole = S.population_outside(pop, {"m": (np.zeros_like(flooded), None)},
                                 {"t": (flooded, np.ones_like(flooded))})
    assert set(whole["pop_in_truth"]) == {30.0}
    covered = S.population_outside(pop, {"m": (np.zeros_like(flooded), coverage)},
                                   {"t": (flooded, np.ones_like(flooded))})
    assert covered.empty


# --------------------------------------------------------------------------
# Grids and rasterisation (need rasterio)
# --------------------------------------------------------------------------


def test_window_grid_is_whole_population_blocks():
    pytest.importorskip("rasterio")
    grid = S.window_grid((5.5, 50.3, 5.6, 50.4))
    assert grid.width % S.POPULATION_BLOCK == 0 and grid.height % S.POPULATION_BLOCK == 0
    step = grid.resolution_m * S.POPULATION_BLOCK
    assert grid.left % step == 0 and grid.top % step == 0
    pgrid = S.population_grid(grid)
    assert pgrid.resolution_m == 100.0
    assert pgrid.shape == (grid.height // 5, grid.width // 5)


def test_rasterize_on_grid_uses_cell_centres():
    """A 45 m square marks the 2 x 2 cells whose centres it holds, not the 3 x 3 it touches."""
    pytest.importorskip("rasterio")
    from shapely.geometry import box

    grid = V.Grid(left=0.0, top=100.0, width=5, height=5)
    mask = S.rasterize_on_grid([box(0, 55, 45, 100)], grid)
    assert mask.sum() == 4
    assert mask[:2, :2].all()
    assert not S.rasterize_on_grid([], grid).any()


def _write(path, values, *, crs, left, top, res, nodata):
    rasterio = pytest.importorskip("rasterio")
    from affine import Affine

    with rasterio.open(path, "w", driver="GTiff", height=values.shape[0],
                       width=values.shape[1], count=1, dtype=values.dtype, crs=crs,
                       transform=Affine(res, 0, left, 0, -res, top), nodata=nodata) as dst:
        dst.write(values, 1)
    return str(path)


def test_population_resampling_moves_people_without_counting_them_twice(tmp_path):
    """Mollweide 100 m people summed onto a 100 m EPSG:3035 grid keep their total.

    A rotated grid of the same resolution overlaps one or two source cells per
    destination cell; an unweighted sum would count most people about twice.
    Checked against the native count of cells whose centres fall in the grid.
    """
    pytest.importorskip("rasterio")
    from pyproj import Transformer

    # Around Liège, 60 x 60 cells of 7 people, with a nodata hole.
    x0, y0 = Transformer.from_crs("EPSG:4326", "ESRI:54009", always_xy=True).transform(5.5, 50.6)
    left, top = np.floor(x0 / 100) * 100 - 3000, np.ceil(y0 / 100) * 100 + 3000
    values = np.full((60, 60), 7.0, dtype="float32")
    values[10:12, 10:12] = -200.0
    tile = _write(tmp_path / "pop.tif", values, crs="ESRI:54009", left=left, top=top,
                  res=100.0, nodata=-200.0)
    xc, yc = Transformer.from_crs("ESRI:54009", "EPSG:3035", always_xy=True).transform(
        left + 3000, top - 3000)
    grid = V.Grid(left=float(np.floor(xc / 100) * 100 - 2000),
                  top=float(np.ceil(yc / 100) * 100 + 2000),
                  width=40, height=40, resolution_m=100.0)
    resampled = S.read_population_on_grid([tile], grid)
    native = S.native_population_in_grid([tile], grid)
    assert native > 0
    assert resampled.sum() == pytest.approx(native, rel=0.02)
    assert resampled.max() < 7.0 * 1.5


def test_main_writes_both_tables_and_prints_every_truth(tmp_path, monkeypatch, capsys):
    """The wiring, with `build_window` replaced: two files, every truth printed."""
    scores = pd.DataFrame({
        "window": ["w", "w"], "kind": ["model_vs_truth"] * 2, "model": ["jrc_rp100"] * 2,
        "truth": ["wallonia_depth_2021", "wallonia_extent_2021"],
        "observed_km2": [1.0, 5.0], "modelled_km2": [2.0, 2.0],
        "hit_rate": [0.6, 0.2], "false_alarm_ratio": [0.8, 0.7], "csi": [0.1, 0.1]})
    population = pd.DataFrame({
        "truth": ["wallonia_extent_2021"], "model": ["jrc_rp100"], "variant": ["conservative"],
        "pop_in_truth": [100.0], "pop_in_truth_outside_model": [40.0],
        "share_outside_model": [0.4], "pop_inside_model_in_window": [500.0]})
    monkeypatch.setattr(S, "build_window", lambda name, epoch=2025: (scores, population))
    out, out_pop = tmp_path / "v.parquet", tmp_path / "p.parquet"
    assert S.main(["--windows", "wallonia", "--out", str(out),
                   "--out-population", str(out_pop)]) == 0
    assert len(pd.read_parquet(out)) == 2 and len(pd.read_parquet(out_pop)) == 1
    printed = capsys.readouterr().out
    assert "wallonia_depth_2021 0.600, wallonia_extent_2021 0.200" in printed


def test_epoch_2020_reads_its_own_tiles_and_writes_its_own_file(tmp_path, monkeypatch):
    """`--epoch 2020` must not overwrite the 2025 population table."""
    seen = {}
    population = pd.DataFrame({"truth": ["t"], "model": ["m"], "variant": ["v"],
                               "pop_in_truth": [1.0], "pop_in_truth_outside_model": [0.5],
                               "share_outside_model": [0.5], "pop_inside_model_in_window": [1.0]})
    scores = pd.DataFrame({"window": ["w"], "kind": ["x"], "model": ["m"], "truth": ["t"],
                           "observed_km2": [1.0], "modelled_km2": [1.0], "hit_rate": [0.5],
                           "false_alarm_ratio": [0.5], "csi": [0.5]})

    def fake(name, epoch=2025):
        seen["epoch"] = epoch
        return scores, population
    monkeypatch.setattr(S, "build_window", fake)
    monkeypatch.setattr(S, "OUT_POPULATION", tmp_path / "validation_2021_population.parquet")
    assert S.main(["--windows", "wallonia", "--epoch", "2020", "--out", str(tmp_path / "v.parquet")]) == 0
    assert seen["epoch"] == 2020
    assert (tmp_path / "validation_2021_population_e2020.parquet").exists()
    assert not (tmp_path / "validation_2021_population.parquet").exists()
    assert all("E2020" in p.name for p in S.GHSL_TILES[2020])

