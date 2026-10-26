"""Risk Data Hub loss rows, turned into something joinable to the NUTS3 analysis.

`src/rdh.py` fetches the rows. This module is the layer between those rows and a
table a brief can print, and it exists because three properties of the real
response each produce a wrong number in a way that does not look wrong. All three
were measured against the cached Belgian answer - 1,297 rows, fetched 2026-10-06,
`losses__admin_hazard_type-Flood_admin_unit_country_code-BE.json` under
`data/processed/rdh_cache/` - and the arithmetic is reproduced in
`tests/test_losses.py` so that it stays checkable rather than remembered.

**The rows are nested, and summing them is wrong by 4x.** The same event arrives
once per administrative level. For the July 2021 flood in Belgium
(`event_code == "FLBE202107130001"`, `metric == "casualty_count"`, 25 rows):

    sum of every row                      = 114.01   <- four levels added together
    sum at Country only   (1 unit)        =  29.67
    sum at NUTS1 only     (2 units)       =  29.67
    sum at NUTS2 only     (6 units)       =  29.67   <- the hierarchy is coherent
    sum at NUTS3 only     (16 units)      =  25.00

So an aggregation is only meaningful once one `admin_unit_level` is pinned. That
is why `level` is a required positional argument everywhere below, and why
`to_frame` deliberately does not produce a column called `value`: the summable
column is created by `select_level`, which cannot be called without a level.

**NUTS3 is incomplete, by 16%.** 25.00 against 29.67 means roughly one casualty
in six is not attributed to an arrondissement, and NUTS3 is this project's
working unit, so a NUTS3 total silently understates the event. Nothing here
redistributes the gap - inventing an allocation would be a claim about where
people died. Instead every per-unit total carries `parent_coverage_ratio`, and
`level_coverage` breaks it down per parent unit, because the overall 0.843 hides
both directions: measured per NUTS2 province, Brabant wallon (BE31) has 3.33
casualties and no NUTS3 row at all, while Liege (BE33) sums to 16.5 across its
arrondissements against 13.67 at the province - children exceeding their parent
by 21%. A single ratio would have made that look tidy.

**These are not official figures.** `value_event_src_average` is an average
across the sources named in `data_source_list` (here "DFO,EMDAT,HANZE"), which is
why a casualty count comes back as 29.67 and why one arrondissement shows 11.5
deaths. A brief cannot print "29.67 deaths" without saying what it is. So the
value column is named `value_inter_source_average` rather than `value` - the
basis travels with the number into any CSV, slide or merge - and the source list
and euro vintage are columns of every output, not documentation.

**The euro vintage.** `value_2015_event_src_average` and
`value_event_src_average` differ only for monetary rows (`quantity_kind ==
"currency"`), and the measured ratio is exactly 1.16 for every monetary row in
the Belgian response, 1983 to 2021 alike. So the second series is one rebase of
the first, not a per-year deflator, and it carries no information the first does
not. The default here is therefore `euro_2015`: its field name states its base
year, so a table can say "EUR, constant 2015 prices" and be checked, whereas
`value_event_src_average` names no base and is exactly how two tables get mixed
at a flat 16% error. Whichever is chosen, the choice is written into the
`euro_vintage` column of the result.

**One more thing the response does, that is not in the spec.** The cached answer
was requested with `admin_hazard_type="Flood"` and came back with 793 flood rows
out of 1,297 - the rest are Storm, Extreme temperature and Earthquake. The
server-side hazard filter did not apply. So filtering by hazard is done here, on
the rows, and every per-unit total carries the `hazards` column listing the codes
actually behind it: an earthquake sitting in a table labelled "flood" is then
visible in the table itself. `RIVERINE_FLOOD` is the subtype to pass for any
comparison against the JRC hazard rasters, which model river flooding only.

Everything returns pandas objects, and `admin_unit_code` stays the join key so a
result merges straight onto `gisco_nuts3` (EPSG:3035, NUTS 2024). The RDH rows
declare no NUTS vintage of their own; the Belgian NUTS3 codes observed include
BE32A-BE32D and BE323/BE328/BE329, which is the post-2021 Hainaut split, so they
are NUTS 2021 or later. Check for unmatched codes after the merge rather than
assuming the vintages agree - `config/sources.yaml` warns that NUTS 2021 and 2024
differ in both geometry and codes.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

# Ordered coarse to fine, which is also the parent-to-child order below.
ADMIN_LEVELS = ("Country", "NUTS1", "NUTS2", "NUTS3")
PARENT_LEVEL = {"NUTS3": "NUTS2", "NUTS2": "NUTS1", "NUTS1": "Country"}

# The two value fields RDH publishes, by the base year each is expressed in. They
# differ only for monetary rows; see the module docstring for why euro_2015 is the
# default.
EURO_VINTAGES = {
    "euro_2015": "value_2015_event_src_average",
    "euro_2024": "value_event_src_average",
}
DEFAULT_EURO_VINTAGE = "euro_2015"

# Named so that the basis of the number cannot be separated from the number.
VALUE_COLUMN = "value_inter_source_average"

# `quantity_kind` is the field that says whether a value is money, so the euro
# vintage is applied on what the data declares rather than on a metric name list
# maintained here.
CURRENCY_KIND = "currency"

# The five codes under hazard_type "Flood" in /admin/hazard/items. Riverine is the
# only one the JRC hazard rasters model, so it is the honest filter for validating
# a modelled ranking against observed losses.
RIVERINE_FLOOD = "nat-hyd-flo-riv"
FLOOD_HAZARDS = (
    RIVERINE_FLOOD,
    "nat-hyd-flo-fla",
    "nat-hyd-flo-coa",
    "nat-hyd-flo-flo",
    "nat-hyd-flo-ice",
)

# Columns a row must carry to be usable. Checked up front, because a KeyError
# three functions deep reads like a bug in this module rather than a changed API.
REQUIRED_COLUMNS = (
    "event_code",
    "admin_unit_code",
    "admin_unit_name",
    "admin_unit_level",
    "admin_unit_parent_code",
    "metric",
    "quantity_kind",
    "data_source_list",
    "hazard",
    *(
        f"event_{edge}_date_{part}"
        for edge in ("start", "end")
        for part in ("year", "month", "day")
    ),
    *EURO_VINTAGES.values(),
)


def to_frame(rows: Iterable[dict]) -> pd.DataFrame:
    """RDH loss rows as a DataFrame, with every administrative level still in it.

    Deliberately not aggregated and deliberately without a column called `value`.
    The response nests the same event at Country, NUTS1, NUTS2 and NUTS3, so a
    frame of raw rows has no correct total; `df[VALUE_COLUMN]` raises a KeyError
    here and only exists after `select_level` has pinned one level. The two RDH
    value fields are kept under their own names, so reading one is also naming its
    base year.

    `event_start_date` and `event_end_date` are assembled from the day/month/year
    triples, which are otherwise only usable by hand. Year filtering still goes
    through `event_start_date_year`: an event running across New Year belongs to
    the year it started in, and that choice should not depend on a parsed date.
    """
    df = pd.DataFrame(list(rows))
    if df.empty:
        raise ValueError(
            "No loss rows. An empty frame totals to 0.0, which reads as 'no "
            "recorded losses' rather than 'nothing was fetched' - check the "
            "rdh.items() call instead of aggregating this."
        )

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Loss rows are missing {missing}. These are the fields the response "
            "carried when this was written; if the API changed, fix it here rather "
            "than letting a total form over the fields that remain."
        )

    for column in EURO_VINTAGES.values():
        df[column] = pd.to_numeric(df[column], errors="coerce")
    for edge in ("start", "end"):
        parts = {p: df[f"event_{edge}_date_{p}"] for p in ("year", "month", "day")}
        df[f"event_{edge}_date"] = pd.to_datetime(
            pd.DataFrame(parts), errors="coerce"
        )
    return df


def select_level(
    df: pd.DataFrame,
    metric: str,
    level: str,
    *,
    years: int | tuple[int, int] | None = None,
    event_code: str | None = None,
    hazard: str | Iterable[str] | None = None,
    euro_vintage: str = DEFAULT_EURO_VINTAGE,
) -> pd.DataFrame:
    """One metric at one administrative level, with a summable value column added.

    This is the only function that creates `VALUE_COLUMN`, and it cannot be called
    without `level`: that is the whole defence against the 114.01-instead-of-29.67
    mistake described in the module docstring. `metric` is required for the same
    reason one level down - `quantity_kind` is "count" for casualties and
    "currency" for economic loss, so a frame holding both has no summable column
    either.

    How the value is measured: it is `value_2015_event_src_average` or
    `value_event_src_average` depending on `euro_vintage`, i.e. the mean over the
    sources listed in `data_source_list` for that event and unit. The chosen
    vintage is recorded in the `euro_vintage` column for monetary rows and left
    null for counts, where the two fields are identical.

    `years` is a single year or an inclusive `(first, last)` pair, matched on
    `event_start_date_year`. An empty selection raises rather than returning an
    empty frame, because an empty frame sums to 0.0 and 0.0 is a claim.
    """
    if level not in ADMIN_LEVELS:
        raise ValueError(f"level must be one of {ADMIN_LEVELS}, not {level!r}.")
    if euro_vintage not in EURO_VINTAGES:
        raise ValueError(
            f"euro_vintage must be one of {sorted(EURO_VINTAGES)}, not "
            f"{euro_vintage!r}. The two differ by a flat 1.16 on monetary rows, so "
            "mixing them in one table is a silent 16% error."
        )

    out = df[(df["admin_unit_level"] == level) & (df["metric"] == metric)]
    if event_code is not None:
        out = out[out["event_code"] == event_code]
    if years is not None:
        first, last = (years, years) if isinstance(years, int) else years
        out = out[out["event_start_date_year"].between(first, last)]
    if hazard is not None:
        codes = {hazard} if isinstance(hazard, str) else set(hazard)
        out = out[out["hazard"].isin(codes)]

    if out.empty:
        raise ValueError(
            f"No {metric!r} rows at level {level!r} for "
            f"years={years!r}, event_code={event_code!r}, hazard={hazard!r}. "
            f"Levels present for this metric: "
            f"{sorted(df.loc[df['metric'] == metric, 'admin_unit_level'].unique())}. "
            "Raising rather than returning an empty frame: an empty frame sums to "
            "0.0, which reads as 'no losses here'."
        )

    out = out.copy()
    out[VALUE_COLUMN] = out[EURO_VINTAGES[euro_vintage]]
    is_money = out["quantity_kind"] == CURRENCY_KIND
    out["euro_vintage"] = pd.Series(euro_vintage, index=out.index).where(is_money)
    return out


def total_by_unit(
    df: pd.DataFrame,
    metric: str,
    level: str,
    *,
    years: int | tuple[int, int] | None = None,
    event_code: str | None = None,
    hazard: str | Iterable[str] | None = None,
    euro_vintage: str = DEFAULT_EURO_VINTAGE,
) -> pd.DataFrame:
    """One metric totalled per administrative unit at one pinned level.

    The table a brief or a map joins to, keyed on `admin_unit_code` so it merges
    onto `gisco_nuts3` (`NUTS_ID`, NUTS 2024) without a lookup. One row per unit;
    units with no row for the selection are absent rather than zero.

    How the total is measured: the inter-source averages of every matching event
    are added up at the chosen level only. Over a year range that is the summed
    loss of `n_events` separate events, each of which is itself a mean across
    `data_source_list` - so the total is a sum of averages, which is why the
    column is named for its basis and the sources travel with it.

    Three provenance columns make the traps visible in the output instead of in
    this docstring: `hazards` lists the codes actually behind each total, because
    the server-side hazard filter does not apply; `euro_vintage` names the base
    year of a monetary figure; and `parent_coverage_ratio` is this level's total
    over its parent level's total for the same selection - 0.843 for NUTS3
    casualties in the July 2021 Belgian flood, meaning one in six is unattributed.
    It is repeated on every row on purpose: a column survives a copy-paste into a
    slide, a footnote does not. It is null when the parent level is not in the
    frame, which is not the same as complete.
    """
    rows = select_level(
        df,
        metric,
        level,
        years=years,
        event_code=event_code,
        hazard=hazard,
        euro_vintage=euro_vintage,
    )

    out = (
        rows.groupby("admin_unit_code")
        .agg(
            admin_unit_name=("admin_unit_name", "first"),
            admin_unit_parent_code=("admin_unit_parent_code", "first"),
            **{VALUE_COLUMN: (VALUE_COLUMN, "sum")},
            n_events=("event_code", "nunique"),
            hazards=("hazard", lambda s: ",".join(sorted(set(s)))),
            data_source_list=("data_source_list", _union_of_source_lists),
        )
        .reset_index()
    )
    out["metric"] = metric
    out["admin_unit_level"] = level
    # Null for counts, where the two RDH fields are identical and a base year
    # would be a meaningless label on a number of people.
    is_money = (rows["quantity_kind"] == CURRENCY_KIND).any()
    out["euro_vintage"] = euro_vintage if is_money else pd.NA
    out["parent_coverage_ratio"] = _parent_coverage_ratio(
        df,
        metric,
        level,
        years=years,
        event_code=event_code,
        hazard=hazard,
        euro_vintage=euro_vintage,
        level_total=out[VALUE_COLUMN].sum(),
    )
    return out.sort_values(VALUE_COLUMN, ascending=False, ignore_index=True)


def level_coverage(
    df: pd.DataFrame,
    metric: str,
    level: str,
    *,
    years: int | tuple[int, int] | None = None,
    event_code: str | None = None,
    hazard: str | Iterable[str] | None = None,
    euro_vintage: str = DEFAULT_EURO_VINTAGE,
) -> pd.DataFrame:
    """How much of each parent unit's loss is attributed to its children.

    The breakdown behind `parent_coverage_ratio`, one row per parent unit, worst
    coverage first. Country has no parent and is refused.

    How coverage is measured: for each unit at `PARENT_LEVEL[level]`, the summed
    total of its children at `level` divided by the total at that unit, over the
    same selection. The denominator is the parent, so 1.0 means fully attributed,
    below 1.0 means losses the finer level does not place, and above 1.0 means the
    children add up to more than the parent reports - all three occur in the real
    Belgian rows, which is why this is per unit and not one number.

    `parent_total` is NaN for a child whose parent code has no row at the parent
    level; the children are kept rather than dropped, so an orphan shows up as an
    unknown coverage instead of disappearing from the denominator.
    """
    parent = PARENT_LEVEL.get(level)
    if parent is None:
        raise ValueError(
            f"{level!r} is the top of the hierarchy, so it has no parent to measure "
            f"coverage against. Pass one of {sorted(PARENT_LEVEL)}."
        )

    shared = dict(
        years=years, event_code=event_code, hazard=hazard, euro_vintage=euro_vintage
    )
    children = total_by_unit(df, metric, level, **shared)
    parents = total_by_unit(df, metric, parent, **shared)

    rolled_up = (
        children.groupby("admin_unit_parent_code")
        .agg(child_total=(VALUE_COLUMN, "sum"), n_children=("admin_unit_code", "size"))
        .reset_index()
        .rename(columns={"admin_unit_parent_code": "parent_code"})
    )
    out = parents[["admin_unit_code", "admin_unit_name", VALUE_COLUMN]].rename(
        columns={
            "admin_unit_code": "parent_code",
            "admin_unit_name": "parent_name",
            VALUE_COLUMN: "parent_total",
        }
    )
    out = out.merge(rolled_up, on="parent_code", how="outer")
    out["child_total"] = out["child_total"].fillna(0.0)
    out["n_children"] = out["n_children"].fillna(0).astype(int)
    out["unattributed"] = out["parent_total"] - out["child_total"]
    out["coverage_ratio"] = out["child_total"] / out["parent_total"]
    out["level"] = level
    out["parent_level"] = parent
    out["metric"] = metric
    out["euro_vintage"] = children["euro_vintage"].iloc[0]
    return out.sort_values("coverage_ratio", na_position="first", ignore_index=True)


def _union_of_source_lists(values: Iterable[str]) -> str:
    """Every distinct source behind a total, from RDH's comma-separated field.

    A unit whose events came from different source mixes would otherwise report
    whichever list happened to be first, which is a provenance claim that is not
    true of the whole number.
    """
    sources: set[str] = set()
    for value in values:
        if isinstance(value, str):
            sources.update(part.strip() for part in value.split(",") if part.strip())
    return ",".join(sorted(sources))


def _parent_coverage_ratio(
    df: pd.DataFrame,
    metric: str,
    level: str,
    *,
    level_total: float,
    **selection,
) -> float | None:
    """`level_total` over the same selection summed at the parent level, or None.

    None, never 1.0, when `level` is the top of the hierarchy or when the parent
    level is absent from the frame: "nothing to compare against" and "fully
    attributed" are different statements, and a default of 1.0 would turn the
    second into a silent claim.
    """
    parent = PARENT_LEVEL.get(level)
    if parent is None:
        return None
    try:
        parent_rows = select_level(df, metric, parent, **selection)
    except ValueError:
        return None
    parent_total = parent_rows[VALUE_COLUMN].sum()
    return level_total / parent_total if parent_total else None
