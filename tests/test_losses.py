"""Tests for the loss aggregation layer. No network: every row here is written by hand.

The fixtures are a scale model of the real Belgian response - the July 2021 flood
nested at Country, NUTS1, NUTS2 and NUTS3 with the measured values - because the
failures worth testing in this module are arithmetic, not transport. A wrong total
raises nothing: it prints, it maps, it goes in a brief. So the assertions are the
numbers themselves:

    every row added together       = 114.01   <- the mistake
    Country / NUTS1 / NUTS2        =  29.67
    NUTS3                          =  25.00   <- 84.3% of its parent level

and the structural guarantees around them: that no function will produce 114.01,
that `level` cannot be left out, that an empty selection raises instead of
totalling to zero, and that the source list and euro vintage stay attached to
every number.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import losses as L

EVENT = "FLBE202107130001"
SOURCES = "DFO,EMDAT,HANZE"

# The July 2021 flood as the API serves it: one value per unit per level, with the
# same event repeated at all four. Values are the measured ones, so the totals in
# the assertions below are the real totals.
CASUALTY_TREE: dict[str, dict[str, tuple[str, float]]] = {
    "Country": {"BE": ("EU", 29.67)},
    "NUTS1": {"BE2": ("BE", 5.67), "BE3": ("BE", 24.00)},
    "NUTS2": {
        "BE22": ("BE2", 5.67),
        "BE31": ("BE3", 3.33),
        "BE32": ("BE3", 4.67),
        "BE33": ("BE3", 13.67),
        "BE34": ("BE3", 1.33),
        "BE35": ("BE3", 1.00),
    },
    # Sixteen arrondissements summing to 25.00, not 29.67: Brabant wallon (BE31)
    # has no child row at all, while Liege (BE33) and Namur (BE35) overshoot their
    # province. Both directions are in the real data.
    "NUTS3": {
        "BE223": ("BE22", 2.0),
        "BE224": ("BE22", 1.0),
        "BE225": ("BE22", 0.5),
        "BE32B": ("BE32", 2.5),
        "BE331": ("BE33", 3.0),
        "BE332": ("BE33", 11.5),
        "BE334": ("BE33", 0.5),
        "BE335": ("BE33", 1.5),
        "BE336": ("BE33", 0.0),
        "BE341": ("BE34", 0.5),
        "BE342": ("BE34", 0.0),
        "BE343": ("BE34", 0.5),
        "BE344": ("BE34", 0.0),
        "BE345": ("BE34", 0.0),
        "BE351": ("BE35", 1.0),
        "BE352": ("BE35", 0.5),
    },
}

LEVEL_CODE = {"Country": 0, "NUTS1": 1, "NUTS2": 2, "NUTS3": 3}


def _row(
    code: str,
    parent: str,
    level: str,
    value: float,
    *,
    metric: str = "casualty_count",
    quantity_kind: str = "count",
    value_2015: float | None = None,
    event_code: str = EVENT,
    year: int = 2021,
    hazard: str = L.RIVERINE_FLOOD,
    data_source_list: str = SOURCES,
) -> dict:
    """One loss row with the keys the live response carries.

    `value_2015` defaults to `value` because the two RDH value fields are
    identical for every non-monetary row in the real answer; the monetary fixtures
    pass it explicitly.
    """
    return {
        "event_code": event_code,
        "admin_unit_code": code,
        "admin_unit_name": f"Unit {code}",
        "admin_unit_level": level,
        "admin_unit_level_code": LEVEL_CODE[level],
        "admin_unit_parent_code": parent,
        "admin_unit_country_code": "BE",
        "metric": metric,
        "dimension": "population" if quantity_kind == "count" else "structure",
        "asset": "pop-sec-pop-gen" if quantity_kind == "count" else "unknown",
        "quantity_kind": quantity_kind,
        "hazard": hazard,
        "hazard_type": "Flood",
        "data_source_list": data_source_list,
        "event_start_date_year": year,
        "event_start_date_month": 7,
        "event_start_date_day": 13,
        "event_end_date_year": year,
        "event_end_date_month": 7,
        "event_end_date_day": 16,
        "value_event_src_average": value,
        "value_2015_event_src_average": value if value_2015 is None else value_2015,
    }


def _tree_rows(tree: dict[str, dict[str, tuple[str, float]]], **kwargs) -> list[dict]:
    """Every level of a nested tree as flat rows, the way the API returns them."""
    return [
        _row(code, parent, level, value, **kwargs)
        for level, units in tree.items()
        for code, (parent, value) in units.items()
    ]


@pytest.fixture
def flood_2021() -> pd.DataFrame:
    """The 25-row casualty response for one event, nested at four levels."""
    return L.to_frame(_tree_rows(CASUALTY_TREE))


@pytest.fixture
def economic() -> pd.DataFrame:
    """Monetary rows, where the two RDH value fields differ by a flat 1.16.

    One NUTS2 parent and two NUTS3 children, so the euro vintage can be tested
    without the coverage machinery getting in the way.
    """
    tree = {
        "NUTS2": {"BE33": ("BE3", 116.0)},
        "NUTS3": {"BE331": ("BE33", 58.0), "BE332": ("BE33", 58.0)},
    }
    rows = [
        _row(
            code,
            parent,
            level,
            value,
            metric="economic_loss_value",
            quantity_kind="currency",
            value_2015=value / 1.16,
        )
        for level, units in tree.items()
        for code, (parent, value) in units.items()
    ]
    return L.to_frame(rows)


# --- Trap 1: the rows are nested, and summing them is wrong by 4x --------------


def test_the_frame_offers_no_summable_value_column(flood_2021):
    """`to_frame` keeps all four levels, so there is no correct total to expose.

    The column that can be summed is created by `select_level`, which cannot be
    called without a level. Asking the raw frame for it is a KeyError rather than
    a number.
    """
    assert L.VALUE_COLUMN not in flood_2021.columns
    assert "value" not in flood_2021.columns
    with pytest.raises(KeyError):
        flood_2021[L.VALUE_COLUMN]


def test_the_naive_sum_is_114_and_no_function_returns_it(flood_2021):
    """The mistake, reproduced: adding the raw rows counts the same deaths four
    times over. 114.01 must not be reachable through this module's API."""
    naive = flood_2021["value_event_src_average"].sum()
    assert round(naive, 2) == 114.01

    per_level = {
        level: L.total_by_unit(flood_2021, "casualty_count", level)[
            L.VALUE_COLUMN
        ].sum()
        for level in L.ADMIN_LEVELS
    }
    assert all(round(total, 2) != 114.01 for total in per_level.values())


def test_aggregating_without_a_level_is_impossible(flood_2021):
    """`level` is a required positional argument, not a default a caller forgets."""
    with pytest.raises(TypeError):
        L.total_by_unit(flood_2021, "casualty_count")
    with pytest.raises(TypeError):
        L.select_level(flood_2021, "casualty_count")


def test_each_level_counts_the_event_once(flood_2021):
    """The hierarchy is coherent above NUTS3: three different levels, one total."""
    totals = {
        level: round(
            L.total_by_unit(flood_2021, "casualty_count", level)[L.VALUE_COLUMN].sum(),
            2,
        )
        for level in L.ADMIN_LEVELS
    }
    assert totals == {
        "Country": 29.67,
        "NUTS1": 29.67,
        "NUTS2": 29.67,
        "NUTS3": 25.00,
    }


def test_unit_counts_match_the_level(flood_2021):
    """One row per unit at the pinned level, and no row from any other level."""
    nuts3 = L.total_by_unit(flood_2021, "casualty_count", "NUTS3")
    assert len(nuts3) == 16
    assert set(nuts3["admin_unit_level"]) == {"NUTS3"}
    assert nuts3["admin_unit_code"].is_unique


def test_an_unknown_level_is_refused(flood_2021):
    with pytest.raises(ValueError, match="level must be one of"):
        L.total_by_unit(flood_2021, "casualty_count", "LAU")


# --- Trap 2: NUTS3 is incomplete, by 16% --------------------------------------


def test_every_nuts3_total_carries_its_coverage_ratio(flood_2021):
    """25.00 against 29.67: one casualty in six is not attributed to an
    arrondissement. The ratio sits in a column on every row, because a column
    survives being pasted into a slide and a footnote does not."""
    nuts3 = L.total_by_unit(flood_2021, "casualty_count", "NUTS3")
    assert round(nuts3["parent_coverage_ratio"].iloc[0], 4) == round(25.00 / 29.67, 4)
    assert nuts3["parent_coverage_ratio"].nunique() == 1
    assert nuts3["parent_coverage_ratio"].notna().all()


def test_a_coherent_level_reports_full_coverage(flood_2021):
    """NUTS1 and NUTS2 both reconcile to their parent, so the ratio is 1.0 - which
    is what makes the NUTS3 0.843 a finding rather than a quirk of the method."""
    for level in ("NUTS1", "NUTS2"):
        totals = L.total_by_unit(flood_2021, "casualty_count", level)
        assert round(totals["parent_coverage_ratio"].iloc[0], 6) == 1.0


def test_the_top_level_reports_no_coverage_rather_than_one(flood_2021):
    """Country has no parent. Null, not 1.0: 'nothing to compare against' and
    'fully attributed' are different statements."""
    country = L.total_by_unit(flood_2021, "casualty_count", "Country")
    assert country["parent_coverage_ratio"].isna().all()


def test_coverage_is_null_when_the_parent_level_was_not_fetched(flood_2021):
    """A frame holding only NUTS3 rows cannot be checked against anything, and must
    not therefore look complete."""
    nuts3_only = flood_2021[flood_2021["admin_unit_level"] == "NUTS3"]
    totals = L.total_by_unit(nuts3_only, "casualty_count", "NUTS3")
    assert totals["parent_coverage_ratio"].isna().all()


def test_coverage_is_reported_per_parent_and_runs_both_ways(flood_2021):
    """The overall 0.843 hides the shape of the gap, which is why `level_coverage`
    is per unit: one province has no children at all, two have children that add
    up to more than the province reports."""
    coverage = L.level_coverage(flood_2021, "casualty_count", "NUTS3").set_index(
        "parent_code"
    )

    # No NUTS3 row at all under Brabant wallon: 3.33 casualties unattributed.
    assert coverage.loc["BE31", "n_children"] == 0
    assert coverage.loc["BE31", "coverage_ratio"] == 0.0
    assert round(coverage.loc["BE31", "unattributed"], 2) == 3.33

    # Liege's arrondissements sum to more than Liege: coverage above 1.0, and a
    # negative "unattributed". Not clipped - clipping would hide the inconsistency.
    assert coverage.loc["BE33", "coverage_ratio"] > 1.0
    assert coverage.loc["BE33", "unattributed"] < 0

    # Worst coverage first, so the hole is the first thing a reader sees.
    first = L.level_coverage(flood_2021, "casualty_count", "NUTS3").iloc[0]
    assert first["parent_code"] == "BE31"


def test_coverage_totals_reconcile_with_the_ratio(flood_2021):
    """The per-parent table and the single ratio are two views of one measurement,
    so they have to agree."""
    coverage = L.level_coverage(flood_2021, "casualty_count", "NUTS3")
    assert round(coverage["parent_total"].sum(), 2) == 29.67
    assert round(coverage["child_total"].sum(), 2) == 25.00

    nuts3 = L.total_by_unit(flood_2021, "casualty_count", "NUTS3")
    ratio = coverage["child_total"].sum() / coverage["parent_total"].sum()
    assert round(ratio, 6) == round(nuts3["parent_coverage_ratio"].iloc[0], 6)


def test_coverage_against_a_nonexistent_parent_is_refused(flood_2021):
    with pytest.raises(ValueError, match="top of the hierarchy"):
        L.level_coverage(flood_2021, "casualty_count", "Country")


# --- Trap 3: these are not official figures -----------------------------------


def test_the_value_column_names_its_own_basis(flood_2021):
    """29.67 deaths is an average across DFO, EMDAT and HANZE. The column name
    says so, so the basis cannot be dropped on the way to a table."""
    nuts3 = L.total_by_unit(flood_2021, "casualty_count", "NUTS3")
    assert L.VALUE_COLUMN == "value_inter_source_average"
    assert L.VALUE_COLUMN in nuts3.columns
    assert "value" not in nuts3.columns


def test_the_source_list_travels_with_every_number(flood_2021):
    nuts3 = L.total_by_unit(flood_2021, "casualty_count", "NUTS3")
    assert (nuts3["data_source_list"] == SOURCES).all()


def test_source_lists_are_unioned_across_the_events_in_a_total(flood_2021):
    """A unit whose events came from different source mixes must not report
    whichever list happened to be first - that would be a false provenance claim
    about the rest of the number."""
    extra = _row(
        "BE332",
        "BE33",
        "NUTS3",
        4.0,
        event_code="FLBE201505010001",
        year=2015,
        data_source_list="EMDAT,NOAA",
    )
    df = L.to_frame(_tree_rows(CASUALTY_TREE) + [extra])
    row = L.total_by_unit(df, "casualty_count", "NUTS3", years=(2015, 2021))
    row = row[row["admin_unit_code"] == "BE332"].iloc[0]
    assert row["data_source_list"] == "DFO,EMDAT,HANZE,NOAA"
    assert row["n_events"] == 2
    assert row[L.VALUE_COLUMN] == 15.5


def test_the_euro_vintage_is_recorded_and_the_two_series_differ(economic):
    """Measured on the real rows: the 2024 series is the 2015 series times 1.16,
    every year alike. So mixing them in one table is a flat 16% error, and the
    column exists to make that visible."""
    at_2015 = L.total_by_unit(economic, "economic_loss_value", "NUTS3")
    at_2024 = L.total_by_unit(
        economic, "economic_loss_value", "NUTS3", euro_vintage="euro_2024"
    )
    assert set(at_2015["euro_vintage"]) == {"euro_2015"}
    assert set(at_2024["euro_vintage"]) == {"euro_2024"}
    assert round(
        at_2024[L.VALUE_COLUMN].sum() / at_2015[L.VALUE_COLUMN].sum(), 4
    ) == 1.16


def test_the_default_vintage_is_the_one_that_names_its_base_year(economic):
    """A default is a measurement decision: euro_2015 is chosen because its field
    name states the base year and can therefore be checked in a brief."""
    assert L.DEFAULT_EURO_VINTAGE == "euro_2015"
    default = L.total_by_unit(economic, "economic_loss_value", "NUTS3")
    explicit = L.total_by_unit(
        economic, "economic_loss_value", "NUTS3", euro_vintage="euro_2015"
    )
    assert default[L.VALUE_COLUMN].equals(explicit[L.VALUE_COLUMN])


def test_a_count_gets_no_euro_vintage(flood_2021):
    """Labelling a number of people with a base year would be meaningless, and the
    two RDH fields are identical for counts anyway."""
    nuts3 = L.total_by_unit(flood_2021, "casualty_count", "NUTS3")
    assert nuts3["euro_vintage"].isna().all()


def test_an_unknown_vintage_is_refused(economic):
    with pytest.raises(ValueError, match="euro_vintage must be one of"):
        L.total_by_unit(
            economic, "economic_loss_value", "NUTS3", euro_vintage="euro_2020"
        )


# --- Filters, and the hazard the server did not apply -------------------------


def test_a_single_year_and_a_year_range_both_filter(flood_2021):
    older = _row(
        "BE332", "BE33", "NUTS3", 4.0, event_code="FLBE201505010001", year=2015
    )
    df = L.to_frame(_tree_rows(CASUALTY_TREE) + [older])

    assert round(
        L.total_by_unit(df, "casualty_count", "NUTS3", years=2021)[
            L.VALUE_COLUMN
        ].sum(),
        2,
    ) == 25.00
    assert round(
        L.total_by_unit(df, "casualty_count", "NUTS3", years=(2015, 2021))[
            L.VALUE_COLUMN
        ].sum(),
        2,
    ) == 29.00
    assert L.total_by_unit(df, "casualty_count", "NUTS3", years=2015)[
        "n_events"
    ].sum() == 1


def test_an_event_code_pins_one_event(flood_2021):
    other = _row(
        "BE332", "BE33", "NUTS3", 4.0, event_code="FLBE201505010001", year=2015
    )
    df = L.to_frame(_tree_rows(CASUALTY_TREE) + [other])
    totals = L.total_by_unit(df, "casualty_count", "NUTS3", event_code=EVENT)
    assert round(totals[L.VALUE_COLUMN].sum(), 2) == 25.00


def test_the_hazards_behind_a_total_are_listed_in_the_output(flood_2021):
    """The cached response was requested with admin_hazard_type="Flood" and came
    back holding Storm and Earthquake rows too: the server-side filter did not
    apply. So the codes actually summed are a column, and a non-flood hiding in a
    table labelled "flood" is visible in the table."""
    quake = _row(
        "BE332",
        "BE33",
        "NUTS3",
        6.0,
        event_code="EQBE199200000001",
        year=1992,
        hazard="nat-geo-ear-gro",
    )
    df = L.to_frame(_tree_rows(CASUALTY_TREE) + [quake])

    unfiltered = L.total_by_unit(df, "casualty_count", "NUTS3", years=(1992, 2021))
    liege = unfiltered[unfiltered["admin_unit_code"] == "BE332"].iloc[0]
    assert liege["hazards"] == "nat-geo-ear-gro,nat-hyd-flo-riv"

    riverine = L.total_by_unit(
        df, "casualty_count", "NUTS3", years=(1992, 2021), hazard=L.RIVERINE_FLOOD
    )
    assert set(riverine["hazards"]) == {L.RIVERINE_FLOOD}
    assert round(riverine[L.VALUE_COLUMN].sum(), 2) == 25.00


def test_a_hazard_filter_accepts_the_whole_flood_family(flood_2021):
    flash = _row(
        "BE332",
        "BE33",
        "NUTS3",
        2.0,
        event_code="FLBE201806010001",
        year=2018,
        hazard="nat-hyd-flo-fla",
    )
    df = L.to_frame(_tree_rows(CASUALTY_TREE) + [flash])
    totals = L.total_by_unit(
        df, "casualty_count", "NUTS3", years=(2018, 2021), hazard=L.FLOOD_HAZARDS
    )
    assert round(totals[L.VALUE_COLUMN].sum(), 2) == 27.00
    assert L.RIVERINE_FLOOD in L.FLOOD_HAZARDS


# --- Refusing to produce a number out of nothing -------------------------------


def test_an_empty_selection_raises_instead_of_totalling_zero(flood_2021):
    """0.0 is a claim about a region. A selection that matched nothing has to say
    so, the same way rdh.py refuses to turn a missing token into an empty result."""
    with pytest.raises(ValueError, match="No 'casualty_count' rows"):
        L.total_by_unit(flood_2021, "casualty_count", "NUTS3", years=1999)
    with pytest.raises(ValueError, match="No 'population_affected' rows"):
        L.total_by_unit(flood_2021, "population_affected", "NUTS3")


def test_no_rows_at_all_is_refused_early():
    with pytest.raises(ValueError, match="No loss rows"):
        L.to_frame([])


def test_a_changed_response_shape_is_named(flood_2021):
    """A missing field must not let a total form over the fields that remain."""
    rows = _tree_rows(CASUALTY_TREE)
    for row in rows:
        del row["data_source_list"]
    with pytest.raises(ValueError, match="missing.*data_source_list"):
        L.to_frame(rows)


# --- The join onto the NUTS3 geometry -----------------------------------------


def test_the_result_joins_to_nuts3_on_admin_unit_code(flood_2021):
    """`admin_unit_code` is kept as a column, not an index, so a result merges
    straight onto gisco_nuts3's NUTS_ID. The vintages are not assumed to agree -
    an unmatched code is a result, which is why the merge is checked here."""
    totals = L.total_by_unit(flood_2021, "casualty_count", "NUTS3")
    geometry = pd.DataFrame({"NUTS_ID": ["BE332", "BE331", "BE100"]})
    merged = geometry.merge(
        totals, left_on="NUTS_ID", right_on="admin_unit_code", how="left"
    )
    assert merged.loc[merged["NUTS_ID"] == "BE332", L.VALUE_COLUMN].iloc[0] == 11.5
    # BE100 has no loss row for this event: left as null, never filled with 0.0.
    assert merged.loc[merged["NUTS_ID"] == "BE100", L.VALUE_COLUMN].isna().all()


def test_dates_are_assembled_from_the_day_month_year_triples(flood_2021):
    """The triples are unusable as published; the parsed dates are for display and
    for reading an event's duration, never for the year filter."""
    assert flood_2021["event_start_date"].iloc[0] == pd.Timestamp("2021-07-13")
    assert flood_2021["event_end_date"].iloc[0] == pd.Timestamp("2021-07-16")
