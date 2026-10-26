"""Tests for the Eurostat indicator join.

The failure modes pinned here are the ones where a wrong number still looks like
a number: an age share inflated by overlapping buckets, a value silently landing
on the wrong region, a vintage that drifts into the vulnerability index, and a
missing breakdown reported as "nobody is old here".

No network: `requests.get` is never reached, because `fetch` is monkeypatched or
the cube is passed directly.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src import demographics


def _cube(ids, sizes, categories, values, label=None):
    """A JSON-stat 2.0 payload, shaped like Eurostat's real one.

    `values` is the sparse dict Eurostat actually sends: keys are flat row-major
    offsets as STRINGS, and an absent key means "not published".
    """
    return {
        "class": "dataset",
        "version": "2.0",
        "id": ids,
        "size": sizes,
        "value": values,
        "dimension": {
            dim: {"category": {"index": {code: i for i, code in enumerate(codes)}}}
            for dim, codes in zip(ids, categories)
        },
        "label": label or "",
    }


# --- the sparse cube ------------------------------------------------------------

def test_a_hole_in_the_cube_does_not_shift_every_later_value():
    """The bug this decoder exists to make impossible.

    Eurostat sends values keyed by flat offset, and a region it does not publish
    is simply absent. Reading `payload["value"].values()` in order and zipping
    them against the geo list moves every figure after the hole onto the wrong
    region - and nothing downstream looks wrong, because every number is a real
    number for some region.

    Here BE211 is unpublished. Zipping would put BE212's 20 on BE212's neighbour.
    """
    cube = _cube(
        ids=["geo", "time"],
        sizes=[3, 1],
        categories=[["BE211", "BE212", "BE213"], ["2025"]],
        # offset 0 (BE211) absent on purpose
        values={"1": 20, "2": 30},
    )
    frame = demographics.tidy(cube)
    by_geo = frame.set_index("geo")["value"]

    assert "BE211" not in by_geo.index
    assert by_geo["BE212"] == 20
    assert by_geo["BE213"] == 30


def test_the_last_dimension_varies_fastest():
    """Row-major, like Eurostat. Getting this backwards transposes the cube, which
    on a square one is invisible."""
    cube = _cube(
        ids=["geo", "time"],
        sizes=[2, 2],
        categories=[["BE211", "BE212"], ["2024", "2025"]],
        values={"0": 1, "1": 2, "2": 3, "3": 4},
    )
    frame = demographics.tidy(cube).set_index(["geo", "time"])["value"]
    assert frame[("BE211", "2024")] == 1
    assert frame[("BE211", "2025")] == 2
    assert frame[("BE212", "2024")] == 3
    assert frame[("BE212", "2025")] == 4


# --- the overlapping age buckets ------------------------------------------------

def test_the_65_plus_buckets_do_not_overlap():
    """`demo_r_pjangrp3` publishes Y85-89, Y_GE85 and Y_GE90 side by side, and
    Y_GE85 is the sum of the other two. Measured on BE332 in 2025: 10,832 +
    6,723 = 17,555 exactly. Summing "every code from 65 up" counts the over-85s
    twice and reports 22.76% against a true 20.01%.

    Pinned as a property of the constant, because the arithmetic below cannot
    detect the error - double counting produces a larger, entirely plausible
    share."""
    assert "Y_GE85" in demographics.AGES_65_PLUS
    assert "Y85-89" not in demographics.AGES_65_PLUS
    assert "Y_GE90" not in demographics.AGES_65_PLUS


def _age_cube(values_by_age, geo="BE332"):
    ages = ["TOTAL", "Y65-69", "Y70-74", "Y75-79", "Y80-84", "Y_GE85", "Y85-89"]
    return _cube(
        ids=["geo", "age", "time"],
        sizes=[1, len(ages), 1],
        categories=[[geo], ages, ["2025"]],
        values={
            str(i): values_by_age[age]
            for i, age in enumerate(ages)
            if age in values_by_age
        },
    )


def test_the_share_over_65_is_the_disjoint_sum(monkeypatch):
    """The real BE332 figures, so the test fails if the bucket set ever changes."""
    cube = _age_cube({
        "TOTAL": 637220, "Y65-69": 36702, "Y70-74": 31616, "Y75-79": 26367,
        "Y80-84": 15253, "Y_GE85": 17555,
        # Present in the cube and deliberately NOT summed: it is inside Y_GE85.
        "Y85-89": 10832,
    })
    monkeypatch.setattr(demographics, "fetch", lambda *a, **k: cube)

    out = demographics.share_over_65()
    assert out.loc["BE332", "share_over_65"] == pytest.approx(127493 / 637220)
    assert round(out.loc["BE332", "share_over_65"] * 100, 2) == 20.01


def test_a_region_with_no_age_breakdown_is_not_a_region_with_no_old_people(monkeypatch):
    """A published total and a missing breakdown is "not measured". Reported as
    0.0 it would rank the region as the least vulnerable in Europe."""
    cube = _age_cube({"TOTAL": 637220, "Y65-69": 36702})  # the rest absent
    monkeypatch.setattr(demographics, "fetch", lambda *a, **k: cube)

    out = demographics.share_over_65()
    assert "BE332" not in out.index, "a partial breakdown must not become a share"


# --- the vintage ----------------------------------------------------------------

def test_the_vintage_is_text_so_it_cannot_become_an_indicator(monkeypatch):
    """`vulnerability_indicators` scans for numeric columns. A year stored as an
    integer would be offered as an indicator meaning "a more recent census makes
    residents more vulnerable" - which is the `total_pop` trap again, and this
    time it is excluded by dtype rather than by remembering a list."""
    cube = _age_cube({
        "TOTAL": 100.0, "Y65-69": 10.0, "Y70-74": 5.0, "Y75-79": 3.0,
        "Y80-84": 1.0, "Y_GE85": 1.0,
    })
    monkeypatch.setattr(demographics, "fetch", lambda *a, **k: cube)

    out = demographics.share_over_65()
    # The contract is "not numeric", which is what `vulnerability_indicators`
    # tests, rather than a dtype name: pandas 3 stores text as StringDtype and
    # pandas 2 as object, and both satisfy it.
    assert out["share_over_65_year"].dtype.kind not in "if"
    assert out["share_over_65_year"].iloc[0] == "2025"

    from api.main import vulnerability_indicators
    offered = vulnerability_indicators(out.reset_index())
    assert offered == ["share_over_65"]


def test_the_latest_year_is_the_latest_one_with_values(monkeypatch):
    """Not `max(time)`: the cube advertises years that are entirely unpublished
    at NUTS3, and picking one returns an empty indicator."""
    ages = ["TOTAL", "Y65-69", "Y70-74", "Y75-79", "Y80-84", "Y_GE85"]
    times = ["2024", "2025", "2026"]
    values = {}
    for a, age in enumerate(ages):
        # 2026 (offset 2 within each age) left unpublished throughout.
        values[str(a * len(times) + 0)] = 10.0
        values[str(a * len(times) + 1)] = 20.0
    cube = _cube(
        ids=["geo", "age", "time"],
        sizes=[1, len(ages), len(times)],
        categories=[["BE332"], ages, times],
        values=values,
    )
    monkeypatch.setattr(demographics, "fetch", lambda *a, **k: cube)
    assert demographics.share_over_65()["share_over_65_year"].iloc[0] == "2025"


# --- the NUTS2 poverty rate -----------------------------------------------------

def test_the_poverty_rate_says_it_is_a_nuts2_figure(monkeypatch):
    """`ilc_li41` is published at NUTS2 and the kit works at NUTS3. Applying a
    province's rate to its arrondissements is defensible; doing it silently is
    not, so the level travels with the figure."""
    poverty = _cube(
        ids=["geo", "time"],
        sizes=[2, 1],
        categories=[["BE33", "BE21"], ["2025"]],
        values={"0": 14.6, "1": 7.2},
    )
    ages = _age_cube({
        "TOTAL": 100.0, "Y65-69": 10.0, "Y70-74": 5.0, "Y75-79": 3.0,
        "Y80-84": 1.0, "Y_GE85": 1.0,
    })
    # `vulnerability_indicators` pulls two datasets, so the stub dispatches on
    # which one was asked for: one cube for both would feed NUTS2 poverty rows
    # to the NUTS3 age filter and silently produce an empty indicator.
    cubes = {"demo_r_pjangrp3": ages, "ilc_li41": poverty}
    monkeypatch.setattr(demographics, "fetch", lambda dataset, **k: cubes[dataset])

    out = demographics.vulnerability_indicators(["BE332", "BE213", "FR101"])
    assert out.loc["BE332", "poverty_rate_pct"] == pytest.approx(14.6)
    assert out.loc["BE213", "poverty_rate_pct"] == pytest.approx(7.2)
    assert "NUTS2" in out.loc["BE332", "poverty_rate_pct_level"]
    # A region Eurostat does not publish stays missing rather than inheriting
    # someone else's rate.
    assert pd.isna(out.loc["FR101", "poverty_rate_pct"])


def test_the_two_indicators_keep_their_published_units(monkeypatch):
    """`poverty_rate_pct` is a percentage and `share_over_65` a fraction, on purpose.

    Eurostat publishes the at-risk-of-poverty rate as 14.6, not 0.146, and a
    brief quoting "14.6%" has to match the source. The age share is computed here
    and is a ratio. So the two travel on different scales - 14.6 beside 0.19 for
    the same region - which looks like a defect and is not; the composite index
    min-max rescales each indicator from its own extremes, so the unit cannot
    reorder it. This test exists so that "normalising" one of them later is a
    deliberate act with a failing test in front of it, and not a tidy-up.
    """
    poverty = _cube(
        ids=["geo", "time"], sizes=[1, 1],
        categories=[["BE33"], ["2025"]], values={"0": 14.6},
    )
    ages = _age_cube({
        "TOTAL": 100.0, "Y65-69": 10.0, "Y70-74": 5.0, "Y75-79": 3.0,
        "Y80-84": 1.0, "Y_GE85": 1.0,
    })
    cubes = {"demo_r_pjangrp3": ages, "ilc_li41": poverty}
    monkeypatch.setattr(demographics, "fetch", lambda dataset, **k: cubes[dataset])

    out = demographics.vulnerability_indicators(["BE332"])
    assert out.loc["BE332", "poverty_rate_pct"] == pytest.approx(14.6), (
        "a percentage, as Eurostat publishes it"
    )
    assert out.loc["BE332", "share_over_65"] == pytest.approx(0.20), (
        "a fraction, computed here from the disjoint age bands"
    )


# --- the refusal ----------------------------------------------------------------

def test_an_unreachable_eurostat_raises_rather_than_returning_nothing(monkeypatch, tmp_path):
    """An empty frame here becomes a missing indicator, which becomes a
    vulnerability index built on fewer axes than the brief claims - silently.
    The build has to stop."""
    monkeypatch.setattr(demographics, "CACHE_DIR", tmp_path)

    class _Boom:
        def get(self, *a, **k):
            raise OSError("connection refused")

    monkeypatch.setattr(demographics, "requests", _Boom())
    with pytest.raises(demographics.EurostatUnavailable, match="connection refused"):
        demographics.fetch("demo_r_pjangrp3")


def test_a_payload_without_a_cube_is_refused(monkeypatch, tmp_path):
    """A 200 from this host is not proof of data: an error page parses as JSON."""
    monkeypatch.setattr(demographics, "CACHE_DIR", tmp_path)

    class _Resp:
        status_code = 200

        def json(self):
            return {"error": "no data"}

    class _Session:
        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(demographics, "requests", _Session())
    with pytest.raises(demographics.EurostatUnavailable, match="no JSON-stat cube"):
        demographics.fetch("demo_r_pjangrp3")


def test_a_cached_answer_is_reused_without_a_request(monkeypatch, tmp_path):
    """The freeze the whole kit rests on: an indicator that changes between two
    runs of the same build breaks every figure quoted from the first."""
    monkeypatch.setattr(demographics, "CACHE_DIR", tmp_path)
    cube = _cube(["geo"], [1], [["BE332"]], {"0": 1})
    (tmp_path / "demo_r_pjangrp3.json").write_text(json.dumps(cube), encoding="utf-8")

    class _Boom:
        def get(self, *a, **k):
            raise AssertionError("a cached answer must not reach the network")

    monkeypatch.setattr(demographics, "requests", _Boom())
    assert demographics.fetch("demo_r_pjangrp3") == cube


# --- the unit in the name, and the tables frozen before it -------------------------

def test_the_percentage_carries_its_unit_in_its_name(monkeypatch):
    """`poverty_rate_pct`, with its companions named after it as `gdp_meur_year`
    is; the old names are gone from a fresh build."""
    poverty = _cube(ids=["geo", "time"], sizes=[1, 1],
                    categories=[["BE33"], ["2025"]], values={"0": 14.6})
    ages = _age_cube({"TOTAL": 100.0, "Y65-69": 10.0, "Y70-74": 5.0,
                      "Y75-79": 3.0, "Y80-84": 1.0, "Y_GE85": 1.0})
    cubes = {"demo_r_pjangrp3": ages, "ilc_li41": poverty}
    monkeypatch.setattr(demographics, "fetch", lambda dataset, **k: cubes[dataset])
    out = demographics.vulnerability_indicators(["BE332"])
    assert {"poverty_rate_pct", "poverty_rate_pct_year", "poverty_rate_pct_level"} <= set(out.columns)
    assert not set(demographics.LEGACY_COLUMNS) & set(out.columns)


def test_a_table_frozen_before_the_rename_loads_under_the_current_names():
    old = pd.DataFrame({"nuts_id": ["BE332"], "poverty_rate": [14.6],
                        "poverty_rate_year": ["2025"], "poverty_rate_level": ["NUTS2"]})
    new = demographics.with_current_names(old)
    assert list(new.columns) == ["nuts_id", "poverty_rate_pct", "poverty_rate_pct_year",
                                 "poverty_rate_pct_level"]
    assert new["poverty_rate_pct"].tolist() == [14.6]  # renamed, never rescaled
    current = demographics.with_current_names(new)
    assert current is new, "a current table passes through untouched"


def test_a_table_with_both_names_is_left_for_a_human():
    both = pd.DataFrame({"poverty_rate": [14.6], "poverty_rate_pct": [14.6]})
    assert list(demographics.with_current_names(both).columns) == ["poverty_rate", "poverty_rate_pct"]


# --- the year a column is read from ---------------------------------------------

def test_a_thinly_published_newest_year_is_not_the_vintage(monkeypatch):
    """Eurostat releases a year country by country. Measured on `nama_10r_3gdp`:
    1,307 regions in 2023 and 536 in 2024, and "the newest year with any value"
    left GDP blank for the regions only 2023 covers. Here 2025 carries one region
    of ten, so the column must come from 2024."""
    geos = [f"BE{i:03d}" for i in range(10)]
    times = ["2024", "2025"]
    values = {str(g * 2): 100.0 + g for g in range(10)}
    values["1"] = 999.0  # 2025, first region only
    cube = _cube(["geo", "time"], [10, 2], [geos, times], values)
    monkeypatch.setattr(demographics, "fetch", lambda *a, **k: cube)

    out = demographics.gdp_meur()
    assert set(out["gdp_meur_year"]) == {"2024"}
    assert len(out) == 10
    assert out.loc["BE000", "gdp_meur"] == pytest.approx(100.0)


def test_a_newest_year_that_is_nearly_complete_is_taken():
    """The coverage floor is a floor, not a preference for older data: a year
    missing one region of twenty is the vintage."""
    frame = pd.DataFrame({
        "geo": [f"R{i}" for i in range(20)] * 2,
        "time": ["2024"] * 20 + ["2025"] * 20,
        "value": [1.0] * 20 + [2.0] * 19 + [None],
    })
    _, year = demographics._latest(frame)
    assert year == "2025"


def test_status_flags_land_on_the_cell_they_belong_to():
    """Flags are a second sparse dict keyed by the same flat offsets. A flag
    shifted by one cell would mark the wrong region provisional."""
    cube = _cube(["geo", "time"], [3, 1], [["A", "B", "C"], ["2024"]],
                 {"0": 1.0, "1": 2.0, "2": 3.0})
    cube["status"] = {"1": "p"}
    frame = demographics.tidy(cube, with_status=True).set_index("geo")["status"]
    assert frame["B"] == "p"
    assert pd.isna(frame["A"]) and pd.isna(frame["C"])
    assert "status" not in demographics.tidy(cube).columns


# --- density and household income: context, never an indicator ------------------

def _context_cubes():
    density = _cube(["geo", "time"], [2, 1], [["BE332", "BE211"], ["2024"]],
                    {"0": 808.5, "1": 1100.0})
    density["status"] = {"0": "p"}
    income = _cube(["geo", "time"], [2, 1], [["BE33", "BE21"], ["2023"]],
                   {"0": 21300.0, "1": 25400.0})
    return {"demo_r_d3dens": density, "nama_10r_2hhinc": income}


def test_density_and_income_pin_the_unit_they_are_named_after(monkeypatch):
    """`nama_10r_2hhinc` carries five units and thirteen national-accounts items
    under one code; the API's default is not a choice anyone made."""
    asked = {}
    cubes = _context_cubes()

    def stub(dataset, **params):
        asked[dataset] = params
        return cubes[dataset]

    monkeypatch.setattr(demographics, "fetch", stub)
    demographics.context_indicators(["BE332"])
    assert asked["demo_r_d3dens"]["unit"] == "PER_KM2"
    assert asked["nama_10r_2hhinc"]["unit"] == "PPS_EU27_2020_HAB"
    assert asked["nama_10r_2hhinc"]["na_item"] == "B6N"
    assert asked["nama_10r_2hhinc"]["direct"] == "BAL"


def test_income_is_a_nuts2_figure_and_says_so(monkeypatch):
    cubes = _context_cubes()
    monkeypatch.setattr(demographics, "fetch", lambda dataset, **k: cubes[dataset])

    out = demographics.context_indicators(["BE332", "BE213", "FR101"])
    assert out.loc["BE332", "pop_density_per_km2"] == pytest.approx(808.5)
    assert out.loc["BE332", "pop_density_flag"] == "p"
    assert out.loc["BE332", "household_income_pps_per_hab"] == pytest.approx(21300.0)
    assert out.loc["BE213", "household_income_pps_per_hab"] == pytest.approx(25400.0)
    assert "NUTS2" in out.loc["BE332", "household_income_level"]
    # Not published: missing, never borrowed from a neighbour or set to zero.
    assert pd.isna(out.loc["FR101", "pop_density_per_km2"])
    assert pd.isna(out.loc["FR101", "household_income_pps_per_hab"])
    assert pd.isna(out.loc["BE213", "pop_density_per_km2"])


def test_only_the_two_figures_are_numeric(monkeypatch):
    """Vintages, flags and levels are text, so a scan for numeric columns - the
    way `api/main.py` picks indicators - finds the two figures and nothing else.
    They belong in `context.parquet`; this keeps them harmless even if copied."""
    cubes = _context_cubes()
    monkeypatch.setattr(demographics, "fetch", lambda dataset, **k: cubes[dataset])

    out = demographics.context_indicators(["BE332"])
    numeric = [c for c in out.columns if out[c].dtype.kind in "if"]
    assert numeric == ["pop_density_per_km2", "household_income_pps_per_hab"]
