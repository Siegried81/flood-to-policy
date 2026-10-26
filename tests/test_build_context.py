"""Tests for the context build script's own plumbing.

The measurements it assembles are tested in their modules; what is pinned here
is the script failing after the work is done.
"""

from __future__ import annotations

from pathlib import Path

from scripts import build_context


def test_a_relative_out_path_does_not_fail_after_the_table_is_written():
    """`--out data/processed/x.parquet` wrote the table, then raised in the
    summary line and exited 1 without printing a single note."""
    relative = Path("data/processed/context.test.parquet")
    assert build_context._shown(relative) == relative


def test_a_path_inside_the_repo_is_shown_relative_to_it():
    inside = build_context.ROOT / "data" / "processed" / "context.parquet"
    assert build_context._shown(inside) == Path("data/processed/context.parquet")


def _admin(ids):
    import geopandas as gpd
    from shapely.geometry import box

    return gpd.GeoDataFrame(
        {"nuts_id": ids}, geometry=[box(i, 0, i + 1, 1) for i in range(len(ids))], crs="EPSG:3035"
    )


def test_residual_columns_are_one_per_return_period_in_region_order(tmp_path, monkeypatch):
    """The residual table is long; the context table is one row per region. A
    region missing from the residual run must read NaN, never 0 - 0 would say
    the defences hold everyone there."""
    import pandas as pd

    protected = tmp_path / "exposure_protected.parquet"
    pd.DataFrame({
        "nuts_id": ["A", "A", "B", "B"],
        "return_period": [10, 100, 10, 100],
        "exposed_pop": [1.0, 5.0, 2.0, 7.0],
    }).to_parquet(protected)
    monkeypatch.setattr(build_context, "PROTECTED_OUT", protected)
    frame, _ = build_context._residual(_admin(["B", "A", "C"]), "nuts_id")
    assert list(frame.columns) == ["residual_exposed_pop_rp10", "residual_exposed_pop_rp100"]
    assert frame["residual_exposed_pop_rp100"].tolist()[:2] == [7.0, 5.0]
    assert frame["residual_exposed_pop_rp100"].isna().tolist()[2]


def test_residual_says_why_it_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(build_context, "PROTECTED_OUT", tmp_path / "absent.parquet")
    frame, why = build_context._residual(_admin(["A"]), "nuts_id")
    assert frame is None and "--protection" in why


def test_only_replaces_the_named_layer_and_keeps_every_other_column(tmp_path, monkeypatch, capsys):
    """`--only residual` must not touch the climate or basin columns: those took
    an afternoon of services to build and are frozen."""
    import argparse

    import pandas as pd

    out = tmp_path / "context.parquet"
    pd.DataFrame({
        "nuts_id": ["A", "B"],
        "shared_with": [["NL"], []],
        "residual_exposed_pop_rp100": [99.0, 99.0],
    }).to_parquet(out)
    protected = tmp_path / "exposure_protected.parquet"
    pd.DataFrame({"nuts_id": ["A", "B"], "return_period": [100, 100],
                  "exposed_pop": [5.0, 7.0]}).to_parquet(protected)
    monkeypatch.setattr(build_context, "PROTECTED_OUT", protected)
    args = argparse.Namespace(out=out, only=["residual"], min_depth_m=0.5,
                              return_period=100, stripes=1)
    assert build_context._update(_admin(["A", "B"]), "nuts_id", args) == 0
    back = pd.read_parquet(out)
    assert back["residual_exposed_pop_rp100"].tolist() == [5.0, 7.0]
    assert [list(v) for v in back["shared_with"]] == [["NL"], []]


def test_only_refuses_a_table_in_another_row_order(tmp_path):
    """Joining on position against a reordered table would hand every region
    its neighbour's figures."""
    import argparse

    import pandas as pd
    import pytest

    out = tmp_path / "context.parquet"
    pd.DataFrame({"nuts_id": ["B", "A"]}).to_parquet(out)
    args = argparse.Namespace(out=out, only=["residual"], min_depth_m=0.5,
                              return_period=100, stripes=1)
    with pytest.raises(SystemExit, match="boundary order"):
        build_context._update(_admin(["A", "B"]), "nuts_id", args)


def test_only_climate_replaces_the_climate_columns_in_place(tmp_path, monkeypatch):
    """New ensemble members on disk must reach the table without rebuilding the
    rasters, and the replaced columns keep their place so a diff shows values."""
    import argparse

    import pandas as pd

    out = tmp_path / "context.parquet"
    pd.DataFrame({
        "nuts_id": ["A", "B"],
        "change_pct_ensemble_median_2041_2070": [1.0, 1.0],
        "shared_with": [["NL"], []],
    }).to_parquet(out)
    monkeypatch.setattr(build_context, "CLIMATE_DIR", tmp_path)
    monkeypatch.setattr(build_context, "_climate", lambda admin, variable, period: (
        pd.DataFrame({"change_pct_ensemble_median_2041_2070": [12.0, -3.0]}, index=admin.index),
        "16 member(s) for 2041-2070",
    ))
    args = argparse.Namespace(out=out, only=["climate"], climate_period=["2041-2070"],
                              climate_variable="rdisreturnmax50", min_depth_m=0.5,
                              return_period=100, stripes=1)
    assert build_context._update(_admin(["A", "B"]), "nuts_id", args) == 0
    back = pd.read_parquet(out)
    assert list(back.columns) == ["nuts_id", "change_pct_ensemble_median_2041_2070", "shared_with"]
    assert back["change_pct_ensemble_median_2041_2070"].tolist() == [12.0, -3.0]
