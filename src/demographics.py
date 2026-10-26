"""Eurostat indicators at NUTS3, so the vulnerability index has something to weigh.

**Why this module exists.** `config/sources.yaml` has declared
`eurostat_population_by_age`, `eurostat_poverty` and `eurostat_gdp_nuts3` since
the start, all three `access: api`, and nothing in the repo called them. The cost
of that was not a missing column: `api/main.py::vulnerability_indicators` offered
exactly one indicator, `exposed_pop`, so the composite index was a weighted mean
of one column - which is that column - and `sensitivity` certified all 1,338
measured regions "robust" at any perturbation, because rescaling one term never
reorders it. The ranking needs a second axis before it means anything.

**What belongs here and what does not.** These are properties of the PEOPLE in a
region, which is what a vulnerability indicator is. `exposed_pop` is a property of
the flood. Both belong in `exposure.parquet`, where the index can see them. GDP is
neither - it is a denominator, and a region is not vulnerable for being rich - so
`gdp_meur` goes to `context.parquet` with the other qualifiers.

**Vintage columns are strings on purpose.** `vulnerability_indicators` picks the
index's inputs by scanning for numeric columns, so a year stored as an integer
would silently become a vulnerability indicator meaning "a more recent census
makes residents more vulnerable". Stored as text it is excluded by construction
rather than by remembering to add it to a list.

**The responses are cached to disk**, under `data/processed/eurostat_cache/`, for
the same reason `src/rdh.py` caches: the build has to be repeatable on a venue
network that is not there, and an indicator that changes between two runs of the
same build breaks the freeze the whole kit rests on.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import requests

from src.data_io import DATA

CACHE_DIR = DATA / "processed" / "eurostat_cache"
BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
TIMEOUT_S = 120

#: The 65-and-over age groups that do NOT overlap.
#:
#: `demo_r_pjangrp3` publishes `Y85-89`, `Y_GE85` and `Y_GE90` side by side, and
#: they are not disjoint. Measured on BE332 (arrondissement de Liège), 2025:
#: Y85-89 = 10,832 and Y_GE90 = 6,723, summing to exactly Y_GE85 = 17,555. So
#: "every code from 65 upwards" counts the over-85s twice and reports 22.76%
#: against a true 20.01% - 2.76 percentage points, in the direction that makes a
#: region look more vulnerable than it is.
#:
#: `Y_GE65` exists as a code and returns an EMPTY series at NUTS3, so there is no
#: ready-made bucket to use instead. Checked 2026-10-07.
AGES_65_PLUS = ("Y65-69", "Y70-74", "Y75-79", "Y80-84", "Y_GE85")

#: Column names that changed, old -> current. The poverty rate is a percentage
#: (0 to 100, as Eurostat publishes it) beside `share_over_65`, a fraction (0 to
#: 1), and a table printing 14.0 next to 0.19 read as a mistake; the unit now
#: sits in the name. `gdp_meur` already followed that rule, with its `_year`
#: companion named after the value column, so the companions follow too.
#: `share_over_65` keeps its name: "share" already says fraction, as in
#: `apsfr_share` and `basin_area_share`.
#:
#: Kept so that a table frozen before the rename still loads under the current
#: names - see `with_current_names`. Remove after one release.
LEGACY_COLUMNS = {
    "poverty_rate": "poverty_rate_pct",
    "poverty_rate_year": "poverty_rate_pct_year",
    "poverty_rate_level": "poverty_rate_pct_level",
}


def with_current_names(df: pd.DataFrame) -> pd.DataFrame:
    """`df` with any legacy column renamed to its current name, values untouched.

    Applied wherever a frozen table is read, so the API, the Streamlit app and
    the MCP tools see one set of names whichever build produced the parquet. A
    table carrying BOTH names is left alone rather than given two columns with
    one name: that table was edited by hand and needs a human.
    """
    renames = {old: new for old, new in LEGACY_COLUMNS.items()
               if old in df.columns and new not in df.columns}
    return df.rename(columns=renames) if renames else df


class EurostatUnavailable(RuntimeError):
    """Eurostat did not answer with data. Raised rather than returning empty.

    An empty frame here becomes a missing indicator, which becomes a vulnerability
    index built on fewer axes than the brief says it was - silently. The build
    stops instead.
    """


def _cache_path(dataset: str, params: dict[str, Any]):
    """One file per dataset and parameter set, named so a human can read it."""
    tag = "_".join(f"{k}-{v}" for k, v in sorted(params.items()))
    safe = "".join(c if c.isalnum() or c in "-_" else "." for c in tag)
    return CACHE_DIR / f"{dataset}{('__' + safe) if safe else ''}.json"


def fetch(dataset: str, *, use_cache: bool = True, **params: Any) -> dict:
    """One JSON-stat 2.0 payload from the Eurostat dissemination API, cached.

    Open API, no credentials. Raises `EurostatUnavailable` on anything that is
    not a parseable payload, so a build never continues on half an indicator.
    """
    cache = _cache_path(dataset, params)
    if use_cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    query = {"format": "JSON", "lang": "EN", **params}
    try:
        response = requests.get(f"{BASE}/{dataset}", params=query, timeout=TIMEOUT_S)
    except Exception as exc:  # network, DNS, timeout
        raise EurostatUnavailable(f"{dataset}: {exc}") from exc
    if response.status_code >= 400:
        raise EurostatUnavailable(f"{dataset}: HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise EurostatUnavailable(f"{dataset}: response was not JSON") from exc
    if "value" not in payload or "dimension" not in payload:
        raise EurostatUnavailable(f"{dataset}: payload carries no JSON-stat cube")

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def tidy(payload: dict, *, with_status: bool = False) -> pd.DataFrame:
    """A JSON-stat 2.0 cube as one row per cell: a column per dimension, plus `value`.

    `with_status` adds a `status` column carrying Eurostat's flag for the cell
    ("p" provisional, "e" estimated, "b" break in series), or None when the cell
    carries none. The flags live in a second sparse dict keyed by the same flat
    offsets, so they are read here rather than re-decoded by each caller.

    JSON-stat stores values in a SPARSE dict keyed by the flat row-major offset
    into the cube, not by coordinates - `{"0": 620167, "11": 637220}` - and a
    missing key means "not published", which is why the result is built by
    decoding the keys present rather than by reshaping a dense array. Reading the
    values in order and zipping them against the geo list is the bug this
    function exists to make impossible: it silently shifts every figure onto the
    wrong region as soon as one cell is unpublished, and nothing downstream looks
    wrong.
    """
    ids = payload["id"]
    sizes = payload["size"]
    codes = [
        [code for code, _ in sorted(
            payload["dimension"][dim]["category"]["index"].items(),
            key=lambda item: item[1],
        )]
        for dim in ids
    ]

    status = payload.get("status") or {}
    rows = []
    for flat, value in payload["value"].items():
        remaining = int(flat)
        position = []
        # Row-major: the LAST dimension varies fastest, so it comes off first.
        for size in reversed(sizes):
            remaining, index = divmod(remaining, size)
            position.append(index)
        position.reverse()
        row = {dim: codes[i][position[i]] for i, dim in enumerate(ids)}
        row["value"] = value
        if with_status:
            row["status"] = status.get(flat)
        rows.append(row)
    return pd.DataFrame(rows)


#: A year still being released is one that carries values for fewer than this
#: share of the regions the year before it carries. See `_latest`.
MIN_YEAR_COVERAGE = 0.9


def _latest(frame: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """The most recent year that is substantially published, and which one it was.

    Not `max(time)`: the cube advertises years that are entirely unpublished at
    NUTS3, and selecting one of those returns an empty indicator that reads as
    "nobody is old here".

    And not "the most recent year with any value" either: Eurostat releases a
    new year country by country, so the newest year is often a fraction of the
    map. Measured 2026-10-12 on `nama_10r_3gdp` (MIO_EUR, NUTS3): 1,307 regions
    in 2023 and 536 in 2024, so "any value" picked 2024 and left GDP blank for
    roughly 770 regions that 2023 covers.

    So, walking back from the newest year, a year is taken once it covers at
    least `MIN_YEAR_COVERAGE` of the regions the year before it covers. Compared
    with the year before rather than with the best year ever, because older years
    carry codes from earlier NUTS vintages and from the United Kingdom - the age
    cube has 1,589 regions in 2019 and 1,338 in 2025 - and a best-year floor would
    send every indicator back to a pre-Brexit vintage. Regions, not cells: a cube
    with an age or unit dimension carries several cells per region.
    """
    if frame.empty:
        raise EurostatUnavailable("no values in the cube at all")
    counts = frame.dropna(subset=["value"]).groupby("time")["geo"].nunique()
    counts = counts[counts > 0].sort_index()
    if counts.empty:
        raise EurostatUnavailable("no values in the cube at all")
    years = list(counts.index)
    year = years[0]
    for newer, older in zip(reversed(years), reversed([None] + years[:-1])):
        if older is None or counts[newer] >= MIN_YEAR_COVERAGE * counts[older]:
            year = newer
            break
    year = str(year)
    return frame[frame["time"] == year], year


def share_over_65(*, use_cache: bool = True) -> pd.DataFrame:
    """Share of residents aged 65 or over, per NUTS3 region.

    The equity lens the brief needs: who, not how many. Older residents are
    harder to evacuate and over-represented in flood mortality, which is why this
    is an indicator and `total_pop` is a denominator.

    Returns `share_over_65` in [0, 1] and `share_over_65_year` as TEXT - see the
    module docstring for why the vintage is not a number.
    """
    payload = fetch(
        "demo_r_pjangrp3", use_cache=use_cache, sex="T", unit="NR",
    )
    frame = tidy(payload)
    frame = frame[frame["geo"].str.len() == 5]  # NUTS3 only, not country or NUTS2
    frame, year = _latest(frame)

    total = frame[frame["age"] == "TOTAL"].set_index("geo")["value"]
    older = (
        frame[frame["age"].isin(AGES_65_PLUS)]
        .groupby("geo")["value"]
        .sum()
    )
    # A region that published a total but no age breakdown is NOT a region with
    # no older residents, so it stays NaN rather than becoming 0.0.
    counted = frame[frame["age"].isin(AGES_65_PLUS)].groupby("geo")["age"].nunique()
    older = older.where(counted == len(AGES_65_PLUS))

    out = pd.DataFrame({"share_over_65": older / total.where(total > 0)})
    out["share_over_65_year"] = year
    return out.dropna(subset=["share_over_65"])


def poverty_rate(*, use_cache: bool = True) -> pd.DataFrame:
    """At-risk-of-poverty rate, published at NUTS2 and applied to its NUTS3 children.

    `ilc_li41` is NUTS2. A vulnerability index that mixes levels has to SAY so -
    the assumption that an arrondissement carries its province's poverty rate is
    defensible, and hiding it is not. So the level travels with the figure in
    `poverty_rate_pct_level`, as text, and the brief can print it.

    **The unit is a PERCENTAGE, 0 to 100, as Eurostat publishes it** - while its
    sibling indicator `share_over_65` is a fraction, 0 to 1. Measured on the real
    data: `poverty_rate_pct` spans 1.4 to 50.7 and `share_over_65` 0.027 to 0.372, so
    a table printing both side by side shows 14.0 next to 0.19 for the same
    region and reads as a mistake. It is not converted here, because Eurostat's
    own figure is the percentage and a brief quoting "14%" must match the source.
    The composite index is unaffected either way - `vulnerability._min_max`
    rescales every indicator to [0, 1] from its own extremes, so a linear change
    of unit cannot reorder it - but anything that DISPLAYS the two columns has to
    label them, and nothing may average them raw.

    Returns a frame indexed by NUTS3 code, which is the kit's working unit: the
    mapping is the first four characters, because a NUTS3 code is its NUTS2
    parent plus one digit.
    """
    payload = fetch("ilc_li41", use_cache=use_cache)
    frame = tidy(payload)
    frame = frame[frame["geo"].str.len() == 4]  # NUTS2 only
    frame, year = _latest(frame)
    by_nuts2 = frame.groupby("geo")["value"].mean()

    out = by_nuts2.rename("poverty_rate_pct").to_frame()
    out["poverty_rate_pct_year"] = year
    out["poverty_rate_pct_level"] = "NUTS2, applied to its NUTS3 children"
    return out


def gdp_meur(*, use_cache: bool = True) -> pd.DataFrame:
    """GDP at current market prices, million EUR, per NUTS3 region.

    A denominator, never an indicator: a region is not vulnerable for being rich.
    It belongs in `context.parquet`, where it turns an absolute loss into a share
    of regional wealth - the comparison a European brief needs, because the same
    100 MEUR means different things in Hainaut and in Oberbayern.

    `MIO_EUR`, `MIO_PPS` and `EUR_HAB` are three different numbers, so the unit is
    pinned here rather than left to the API's default.
    """
    payload = fetch("nama_10r_3gdp", use_cache=use_cache, unit="MIO_EUR")
    frame = tidy(payload)
    frame = frame[frame["geo"].str.len() == 5]
    frame, year = _latest(frame)
    out = frame.set_index("geo")[["value"]].rename(columns={"value": "gdp_meur"})
    out["gdp_meur_year"] = year
    return out


def _flag(frame: pd.DataFrame) -> pd.Series:
    """Eurostat's status flag per region, as text, or None where there is none.

    Kept beside the figure rather than dropped: a provisional ("p") or estimated
    ("e") value is still the published value, but a brief quoting it has to be
    able to say so.
    """
    status = frame.set_index("geo")["status"].astype(object)
    return status.where(status.notna(), None)


def population_density(*, use_cache: bool = True) -> pd.DataFrame:
    """Persons per km2, per NUTS3 region (`demo_r_d3dens`).

    Context, not a vulnerability indicator: density says how concentrated a
    region's people are, which qualifies an exposure count (an evacuation in a
    dense arrondissement is a different operation from one in a rural one)
    without making any resident more or less vulnerable. It therefore lives in
    `context.parquet`; promoting it into the index is a weighting decision.

    The unit is pinned to `PER_KM2` and carried in the column name. The vintage
    and flag are text, like every other vintage in this module, so neither can
    be picked up as a numeric column.
    """
    payload = fetch("demo_r_d3dens", use_cache=use_cache, unit="PER_KM2")
    frame = tidy(payload, with_status=True)
    frame = frame[frame["geo"].str.len() == 5]
    frame, year = _latest(frame)
    out = frame.set_index("geo")[["value"]].rename(
        columns={"value": "pop_density_per_km2"}
    )
    out["pop_density_year"] = year
    out["pop_density_flag"] = _flag(frame)
    return out


def household_income(*, use_cache: bool = True) -> pd.DataFrame:
    """Net disposable household income per inhabitant, in PPS, per NUTS2 region.

    `nama_10r_2hhinc`, pinned to `na_item=B6N` (disposable income, net),
    `direct=BAL` and `unit=PPS_EU27_2020_HAB`. Purchasing power standards rather
    than euros, because the column exists to compare regions across countries
    and a euro buys about three times as much in Bulgaria as in Luxembourg; the
    PPS figure is the one Eurostat itself uses for that comparison. The cube
    also carries `MIO_EUR`, `EUR_HAB`, `MIO_NAC` and `MIO_PPS_EU27_2020`, five
    different numbers under one dataset code, so the unit is in the column name.

    Published at NUTS2 only, like the poverty rate, and applied to each NUTS3
    child by `context_indicators`; `household_income_level` says so as text.
    """
    payload = fetch(
        "nama_10r_2hhinc", use_cache=use_cache,
        unit="PPS_EU27_2020_HAB", na_item="B6N", direct="BAL",
    )
    frame = tidy(payload, with_status=True)
    frame = frame[frame["geo"].str.len() == 4]
    frame, year = _latest(frame)
    out = frame.set_index("geo")[["value"]].rename(
        columns={"value": "household_income_pps_per_hab"}
    )
    out["household_income_year"] = year
    out["household_income_flag"] = _flag(frame)
    out["household_income_level"] = "NUTS2, applied to its NUTS3 children"
    return out


def context_indicators(
    nuts_ids: pd.Index | list[str], *, use_cache: bool = True
) -> pd.DataFrame:
    """Population density and household income, reindexed onto `nuts_ids`.

    For `context.parquet`, never `exposure.parquet`: `api/main.py` picks the
    vulnerability index's inputs by scanning the exposure table's numeric
    columns, and neither of these is a property that makes a resident more
    vulnerable by itself being larger. A region Eurostat does not publish stays
    NaN; a NUTS2 figure reaches a NUTS3 code through its first four characters.
    """
    index = pd.Index(nuts_ids, name="nuts_id")
    out = population_density(use_cache=use_cache).reindex(index)
    income = household_income(use_cache=use_cache)
    parents = pd.Series(index.str[:4], index=index)
    for column in income.columns:
        out[column] = parents.map(income[column])
    return out


def vulnerability_indicators(
    nuts_ids: pd.Index | list[str], *, use_cache: bool = True
) -> pd.DataFrame:
    """The indicator columns for `exposure.parquet`, reindexed onto `nuts_ids`.

    Only the two that are properties of the people: the share of older residents
    and the at-risk-of-poverty rate. A region Eurostat does not publish comes back
    NaN, which `indicator_coverage` already reports as partial rather than
    treating as a zero.
    """
    index = pd.Index(nuts_ids, name="nuts_id")
    older = share_over_65(use_cache=use_cache)
    poverty = poverty_rate(use_cache=use_cache)

    out = older.reindex(index)
    # NUTS3 to its NUTS2 parent: the code is the parent plus one digit.
    parents = pd.Series(index.str[:4], index=index)
    for column in ("poverty_rate_pct", "poverty_rate_pct_year", "poverty_rate_pct_level"):
        out[column] = parents.map(poverty[column])
    return out
