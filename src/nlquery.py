"""Natural-language questions over the exposure table, answered by pandas.

The team's non-technical members should be able to ask "which Belgian regions
have the most people exposed at the 100-year flood?" without waiting for whoever
writes pandas. The obvious build - ask a model for SQL or for Python and run it -
hands the arithmetic to the model and executes whatever it wrote. This module
does the opposite: the model is asked for a small JSON **query spec** (columns,
filters, one sort key, a row limit, a return period) and nothing else, the spec
is validated against a whitelist, and pandas executes it with boolean masks. No
string from the model is ever evaluated, so a malformed or hostile answer can at
worst be rejected; it cannot compute a figure.

**What the spec can and cannot express, and why.**

- **Exactly one return period.** The extents are nested, so a row set spanning
  two periods counts the core floodplain once per period. The period is its own
  field, never a filter, and naming none selects the rarest period - the same
  default `/api/exposure` applies - and says so in `defaulted_return_period`.
- **Rows, never aggregates.** No sum, no mean, no group-by. Every figure in an
  answer is a value already in the frozen table, so this layer cannot produce a
  number the table does not hold - and a sum over regions is exactly where the
  denominator question (EU-27 or the 1,345 polygons?) gets lost.
- **`exposed_share` is the one derived column**, computed exactly as
  `/api/exposure` computes it (`exposed_pop / total_pop`), because it is the
  figure that should be ranked.

**Every answer carries the definitions of the columns it touched** - selected,
filtered or sorted on - with their unit and where the definition is argued. And
two things are added whether the model asked or not: the region identifier
(a row without it cannot be checked) and `hazard_coverage` beside
`exposed_pop`, because below 1.0 the count is an extrapolation and the reader is
entitled to know that.

**Nulls are counted, not hidden.** A region whose `exposed_pop` was not
measured fails every numeric comparison, which silently reads as "does not
qualify". `null_excluded` reports how many rows of the period were dropped for a
null on a filtered column, so "not measured" never travels as "not exposed".

One LLM call per question, through `rag.complete_with_provider` - the same
provider path, key rotation and local fallback as the drafting step. No retry,
no tool loop: a spec that fails validation is returned as a refusal naming the
rule it broke. And the model is optional: a caller can send the spec itself, so
the table stays queryable with no key and no local model.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

import pandas as pd

from src import rag

#: The columns a spec may name, with what each one means. The whitelist is this
#: mapping intersected with the columns actually present, so a column the table
#: gains is not queryable until it is defined here - its meaning has to be
#: written down before a model can quote it. `source` is where the definition is
#: argued at length.
COLUMNS: dict[str, dict[str, str]] = {
    "nuts_id": {
        "unit": "code",
        "definition": "NUTS3 region code, GISCO NUTS 2024 vintage.",
        "source": "docs/scope.md#the-unit-of-analysis-nuts3",
    },
    "region": {
        "unit": "text",
        "definition": "Region name as GISCO writes it, in the national language.",
        "source": "docs/scope.md#the-unit-of-analysis-nuts3",
    },
    "country": {
        "unit": "code",
        "definition": "Two-letter country code as GISCO writes it (EL for Greece). "
                      "The file covers the EU-27, EFTA and candidate countries.",
        "source": "docs/scope.md#the-unit-of-analysis-nuts3",
    },
    "country_name": {
        "unit": "text",
        "definition": "Country name.",
        "source": "docs/scope.md#the-unit-of-analysis-nuts3",
    },
    "total_pop": {
        "unit": "persons",
        "definition": "Residents of the region on the GHS-POP grid, counting the "
                      "population cells whose centre falls in it.",
        "source": "docs/technical_deep_dive.md#33-four-columns-and-why-none-is-not-00",
    },
    "cells_counted": {
        "unit": "cells",
        "definition": "Population cells whose centre falls in the region. Raster "
                      "bookkeeping, not a property of the people.",
        "source": "docs/technical_deep_dive.md#33-four-columns-and-why-none-is-not-00",
    },
    "hazard_coverage": {
        "unit": "fraction 0-1",
        "definition": "Share of the region the hazard layer covers. Below 1.0, "
                      "exposed_pop is an extrapolation from the observed part.",
        "source": "docs/technical_deep_dive.md#33-four-columns-and-why-none-is-not-00",
    },
    "exposed_pop": {
        "unit": "persons",
        "definition": "People on ground flooded deeper than the build's threshold "
                      "(0.5 m by default) in this return period's scenario, "
                      "extrapolated onto the whole region by people "
                      "(x total / observed population) where the hazard layer "
                      "covers only part of it; null when nothing was measured. "
                      "River flooding only.",
        "source": "docs/technical_deep_dive.md#33-four-columns-and-why-none-is-not-00",
    },
    "exposed_share": {
        "unit": "fraction 0-1",
        "definition": "exposed_pop / total_pop, computed per query exactly as "
                      "/api/exposure computes it. The figure to rank by: an "
                      "absolute count ranks regions by population.",
        "source": "api/main.py#exposure",
    },
    "return_period": {
        "unit": "years",
        "definition": "Return period of the flood scenario. Extents are nested, so "
                      "a query covers exactly one period.",
        "source": "docs/geospatial_crash_course.md#return-period-what-a-100-year-flood-is-not",
    },
    "annual_probability": {
        "unit": "probability per year",
        "definition": "1 / return_period: the chance of the scenario in any one year.",
        "source": "docs/geospatial_crash_course.md#return-period-what-a-100-year-flood-is-not",
    },
    "share_over_65": {
        "unit": "fraction 0-1",
        "definition": "Share of residents aged 65 or over, Eurostat, at NUTS3.",
        "source": "src/demographics.py",
    },
    "share_over_65_year": {
        "unit": "text",
        "definition": "Reference year of share_over_65.",
        "source": "src/demographics.py",
    },
    "poverty_rate_pct": {
        "unit": "percent 0-100",
        "definition": "At-risk-of-poverty rate, Eurostat, published at NUTS2 and "
                      "applied to every NUTS3 child. A percentage, unlike "
                      "share_over_65, which is a fraction.",
        "source": "src/demographics.py",
    },
    "poverty_rate_pct_year": {
        "unit": "text",
        "definition": "Reference year of poverty_rate_pct.",
        "source": "src/demographics.py",
    },
    "poverty_rate_pct_level": {
        "unit": "text",
        "definition": "The NUTS level poverty_rate_pct was published at.",
        "source": "src/demographics.py",
    },
}

#: Comparison operators a filter may use, and nothing else. Each maps to a pandas
#: method call below, never to a string handed to `DataFrame.query` or `eval`.
NUMERIC_OPS = frozenset({"<", "<=", ">", ">="})
EQUALITY_OPS = frozenset({"==", "!="})
SET_OPS = frozenset({"in", "not_in"})
NULL_OPS = frozenset({"is_null", "not_null"})
TEXT_OPS = frozenset({"contains"})
OPERATORS = NUMERIC_OPS | EQUALITY_OPS | SET_OPS | NULL_OPS | TEXT_OPS

SPEC_KEYS = frozenset({"columns", "filters", "sort", "limit", "return_period"})
FILTER_KEYS = frozenset({"column", "op", "value"})
SORT_KEYS = frozenset({"column", "descending"})
DEFAULT_LIMIT = 20
#: Rows an answer may return. A question that needs more than this is a table
#: export, which the UIs already offer, not a question.
MAX_LIMIT = 100
MAX_COLUMNS = 12
MAX_FILTERS = 10
MAX_SET_VALUES = 50
MAX_QUESTION_CHARS = 500

SYSTEM_PROMPT = (
    "You translate a question about a table of flood exposure per European "
    "region into a JSON query spec. You never answer the question yourself and "
    "never write code or SQL. Output ONE JSON object and nothing else, with "
    "these keys: \"columns\" (list of column names to show), \"filters\" (list "
    "of {\"column\", \"op\", \"value\"}), \"sort\" ({\"column\", \"descending\"} "
    "or null), \"limit\" (integer 1-" + str(MAX_LIMIT) + "), \"return_period\" "
    "(one of the available return periods in years, or null if the question "
    "names none). Allowed ops: < <= > >= == != in not_in is_null not_null "
    "contains. Use only the column names listed. Never filter on return_period: "
    "use the return_period key. There are no aggregates: to find the largest, "
    "sort descending and limit. Fractions are 0-1, percentages 0-100, as each "
    "column's unit says. Country codes are two letters as listed (EL for "
    "Greece)."
)


class SpecError(ValueError):
    """A query spec that breaks a rule. The message names the rule.

    Its own type so the API can answer 422 with the reason and the rejected spec,
    and a UI can show the refusal rather than an empty table that reads as
    "no region matches".
    """


@dataclass
class Answer:
    """One executed query, with what a reader needs to quote it."""

    spec: dict
    key: str
    return_period: int | None
    defaulted_return_period: bool
    rows: list[dict]
    matched: int
    null_excluded: int
    definitions: list[dict]
    notes: list[str] = field(default_factory=list)
    provider: str | None = None
    fallback_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "spec": self.spec,
            "key": self.key,
            "return_period": self.return_period,
            "defaulted_return_period": self.defaulted_return_period,
            "rows": self.rows,
            "matched": self.matched,
            "null_excluded": self.null_excluded,
            "definitions": self.definitions,
            "notes": self.notes,
            "provider": self.provider,
            "fallback_reason": self.fallback_reason,
        }


def region_key(df: pd.DataFrame) -> str:
    """The identifier column: the one definition, which `api.main._region_key` wraps."""
    for candidate in ("nuts_id", "lau_id", "id"):
        if candidate in df.columns:
            return candidate
    raise SpecError("the table has no region identifier column (nuts_id, lau_id or id)")


def _with_share(df: pd.DataFrame) -> pd.DataFrame:
    """Add `exposed_share` the way `/api/exposure` does, when both inputs exist."""
    if {"exposed_pop", "total_pop"} <= set(df.columns) and "exposed_share" not in df.columns:
        return df.assign(exposed_share=df["exposed_pop"] / df["total_pop"])
    return df


def queryable(df: pd.DataFrame) -> dict[str, str]:
    """Whitelisted column -> "number" or "text", for the columns this table has.

    Kinds are read off the dtypes rather than declared, so a column that arrives
    as text is never compared as a number.
    """
    df = _with_share(df)
    kinds = {}
    for name in COLUMNS:
        if name in df.columns:
            kinds[name] = "number" if df[name].dtype.kind in "if" else "text"
    return kinds


def _is_number(value: object) -> bool:
    # bool is an int subclass in Python, and `True` is not a population.
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _check_value(column: str, kind: str, op: str, value: object) -> None:
    """Refuse a value whose type cannot mean what the operator asks."""
    if op in NULL_OPS:
        if value is not None:
            raise SpecError(f"filter {op} on {column!r} takes no value")
        return
    if op in TEXT_OPS:
        if kind != "text" or not isinstance(value, str) or not value:
            raise SpecError(f"'contains' needs a text column and a non-empty string, "
                            f"got {column!r} ({kind}) and {value!r}")
        return
    if op in SET_OPS:
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_SET_VALUES:
            raise SpecError(f"filter {op} on {column!r} needs a list of 1 to "
                            f"{MAX_SET_VALUES} values")
        for item in value:
            _check_value(column, kind, "==", item)
        return
    if op in NUMERIC_OPS and kind != "number":
        raise SpecError(f"{op} needs a numeric column; {column!r} is text")
    if kind == "number" and not _is_number(value):
        raise SpecError(f"{column!r} is numeric; {value!r} is not a finite number")
    if kind == "text" and not isinstance(value, str):
        raise SpecError(f"{column!r} is text; {value!r} is not a string")


def validate(spec: object, df: pd.DataFrame) -> dict:
    """The spec, normalised, or `SpecError` naming the first rule it breaks.

    Strict on purpose: an unknown key, column or operator is refused rather than
    ignored, because a silently dropped filter answers a different question with
    the same confidence.
    """
    if not isinstance(spec, dict):
        raise SpecError("the query spec must be a JSON object")
    unknown = set(spec) - SPEC_KEYS
    if unknown:
        raise SpecError(f"unknown spec keys: {sorted(unknown)}; allowed: {sorted(SPEC_KEYS)}")
    kinds = queryable(df)
    key = region_key(df)

    def known(column: object, where: str) -> str:
        if not isinstance(column, str) or column not in kinds:
            raise SpecError(f"unknown column {column!r} in {where}; "
                            f"allowed: {sorted(kinds)}")
        return column

    columns = spec.get("columns")
    if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_COLUMNS:
        raise SpecError(f"'columns' must be a list of 1 to {MAX_COLUMNS} column names")
    columns = list(dict.fromkeys(known(c, "columns") for c in columns))

    filters = spec.get("filters") or []
    if not isinstance(filters, list) or len(filters) > MAX_FILTERS:
        raise SpecError(f"'filters' must be a list of at most {MAX_FILTERS} filters")
    normalised_filters = []
    for item in filters:
        if not isinstance(item, dict) or not {"column", "op"} <= set(item) \
                or set(item) - FILTER_KEYS:
            raise SpecError(f"a filter is {{column, op, value}}; got {item!r}")
        column = known(item["column"], "filters")
        if column == "return_period":
            raise SpecError("filter on return_period refused: the extents are nested, "
                            "so a query covers exactly one period - use the "
                            "'return_period' key")
        op = item["op"]
        if op not in OPERATORS:
            raise SpecError(f"unknown operator {op!r}; allowed: {sorted(OPERATORS)}")
        value = item.get("value")
        _check_value(column, kinds[column], op, value)
        normalised_filters.append({"column": column, "op": op, "value": value})

    sort = spec.get("sort")
    if sort is not None:
        if not isinstance(sort, dict) or "column" not in sort or set(sort) - SORT_KEYS:
            raise SpecError(f"'sort' is {{column, descending}} or null; got {sort!r}")
        descending = sort.get("descending", True)
        if not isinstance(descending, bool):
            raise SpecError("'sort.descending' must be true or false")
        sort = {"column": known(sort["column"], "sort"), "descending": descending}

    limit = spec.get("limit", DEFAULT_LIMIT)
    if limit is None:
        limit = DEFAULT_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise SpecError(f"'limit' must be an integer from 1 to {MAX_LIMIT}")

    period = spec.get("return_period")
    if period is not None:
        if isinstance(period, bool) or not isinstance(period, int):
            raise SpecError("'return_period' must be an integer number of years or null")
        periods = return_periods(df)
        if periods and period not in periods:
            # The same refusal as /api/exposure: an empty selection would read as
            # "measured, nobody exposed" for a scenario that was never computed.
            raise SpecError(f"no return period {period} in the table; available: {periods}")

    # The identifier first, and the coverage beside the count: neither is the
    # model's choice to leave out.
    if key not in columns:
        columns.insert(0, key)
    if "exposed_pop" in columns and "hazard_coverage" in kinds \
            and "hazard_coverage" not in columns:
        columns.insert(columns.index("exposed_pop") + 1, "hazard_coverage")

    return {"columns": columns, "filters": normalised_filters, "sort": sort,
            "limit": limit, "return_period": period}


def return_periods(df: pd.DataFrame) -> list[int]:
    """Return periods present in the table, rarest last. Empty if unmodelled.

    The one definition of this rule: `api.main` imports it rather than keeping
    a second copy that could drift.
    """
    if "return_period" not in df.columns:
        return []
    return sorted(int(p) for p in df["return_period"].dropna().unique())


def _mask(series: pd.Series, op: str, value: object) -> pd.Series:
    """One filter as a boolean mask. Method calls only - nothing is evaluated."""
    if op == "is_null":
        return series.isna()
    if op == "not_null":
        return series.notna()
    if op == "contains":
        return series.astype("string").str.contains(value, case=False, regex=False).fillna(False).astype(bool)
    if op == "in":
        return series.isin(value)
    if op == "not_in":
        return ~series.isin(value) & series.notna()
    compare = {"==": series.eq, "!=": series.ne, "<": series.lt, "<=": series.le,
               ">": series.gt, ">=": series.ge}[op]
    # `ne` is True for a null; a region that was not measured is not "different
    # from" anything, so nulls fail every comparison here, as they do for `<`.
    return compare(value).fillna(False).astype(bool) & series.notna()


def _value_notes(df: pd.DataFrame, filters: list[dict]) -> list[str]:
    """Notes for filter values the table cannot have meant, read off `df` itself.

    A valid spec can still ask the wrong question: "over 20%" written as 20 on a
    0-1 fraction, or the country "BEL" where the table writes "BE". Both match
    nothing, and zero rows reads as "no region qualifies" - an answer, not an
    error. These notes say when the value is outside what the column holds in
    this period, so the reader can tell the two apart. Notes, not refusals: a
    threshold above every region is a legitimate question with an empty answer.
    """
    notes = []
    for item in filters:
        column, op, value = item["column"], item["op"], item["value"]
        series = df[column].dropna()
        if series.empty or op in NULL_OPS:
            continue
        values = value if op in SET_OPS else [value]
        if series.dtype.kind in "if" and op in NUMERIC_OPS | {"==", "in"}:
            low, high = float(series.min()), float(series.max())
            outside = [v for v in values if not low <= v <= high]
            if outside:
                notes.append(
                    f"{column} {op} {value!r}: {outside} is outside the values the "
                    f"column holds here ({low:g} to {high:g}, unit: "
                    f"{COLUMNS[column]['unit']}). Check the unit before reading "
                    "the result as an answer.")
        elif series.dtype.kind not in "if" and op in {"==", "in"}:
            present = set(series.astype(str))
            absent = [v for v in values if v not in present]
            if absent:
                notes.append(
                    f"{column} {op} {value!r}: {absent} never occurs in the column "
                    f"(e.g. {sorted(present)[:5]}). Check the spelling or the code.")
    return notes


#: How a question names a return period: "100-year", "1-in-100", "RP100",
#: "T=100", "T100". Each pattern captures the years.
_PERIOD_PATTERNS = (
    # Singular only: "100-year flood" names a period, "in the next 10 years" does not.
    r"\b(\d+)[\s-]*(?:year|yr)\b(?![\s-]*(?:old|plan))",
    r"\breturn period of (\d+)\b",
    r"\b1[\s-]*in[\s-]*(\d+)\b",
    r"\bRP[\s-]*(\d+)\b",
    r"\bT\s*=?\s*(\d+)\b",
)


def named_periods(question: str) -> list[int]:
    """The return periods the question names, in order, without repeats."""
    found: list[int] = []
    for pattern in _PERIOD_PATTERNS:
        for match in re.finditer(pattern, question, re.IGNORECASE):
            years = int(match.group(1))
            if years not in found:
                found.append(years)
    return found


def execute(df: pd.DataFrame, spec: dict, *, default_return_period: int | None = None) -> Answer:
    """Validate `spec` and run it on `df` with pandas.

    `default_return_period` is the period used when the spec names none: the
    Streamlit page passes the one selected above its tabs, so an answer is about
    the flood on screen; the API passes nothing and gets the rarest period.
    """
    clean = validate(spec, df)
    key = region_key(df)
    periods = return_periods(df)
    period, defaulted = clean["return_period"], False
    if periods:
        if period is None:
            period = default_return_period if default_return_period in periods else periods[-1]
            defaulted = True
        df = df[df["return_period"] == period]
    clean["return_period"] = period
    df = _with_share(df)

    keep = pd.Series(True, index=df.index)
    nulls = pd.Series(False, index=df.index)
    for item in clean["filters"]:
        series = df[item["column"]]
        keep &= _mask(series, item["op"], item["value"])
        if item["op"] not in NULL_OPS:
            nulls |= series.isna()
    matched = df[keep]
    if clean["sort"]:
        matched = matched.sort_values(
            clean["sort"]["column"], ascending=not clean["sort"]["descending"],
            na_position="last", kind="stable",
        )
    shown = matched.head(clean["limit"])[clean["columns"]]

    touched = list(dict.fromkeys(
        clean["columns"]
        + [f["column"] for f in clean["filters"]]
        + ([clean["sort"]["column"]] if clean["sort"] else [])
    ))
    notes = []
    if defaulted and period is not None:
        notes.append(f"No return period named: answered for the 1-in-{period} year "
                     "scenario. Extents are nested; never add periods together.")
    if len(matched) > len(shown):
        notes.append(f"{len(matched)} rows matched; the first {len(shown)} are shown.")
    null_excluded = int((nulls & ~keep).sum())
    if null_excluded:
        notes.append(f"{null_excluded} rows were excluded because a filtered column is "
                     "null there - not measured, which is not the same as not matching.")
    notes += _value_notes(df, clean["filters"])
    return Answer(
        spec=clean,
        key=key,
        return_period=period,
        defaulted_return_period=defaulted,
        rows=json.loads(shown.to_json(orient="records")),  # NaN -> null
        matched=int(len(matched)),
        null_excluded=null_excluded,
        definitions=[{"column": c, **COLUMNS[c]} for c in touched],
        notes=notes,
    )


def _catalogue(df: pd.DataFrame) -> str:
    """The whitelist as the model sees it: name, kind, unit, definition."""
    lines = [f"- {name} ({kind}, {COLUMNS[name]['unit']}): {COLUMNS[name]['definition']}"
             for name, kind in queryable(df).items()]
    return "\n".join(lines)


def prompt(question: str, df: pd.DataFrame) -> str:
    """The user turn: the question, the periods on offer and the column catalogue."""
    return (
        f"AVAILABLE RETURN PERIODS (years): {return_periods(df)}\n"
        f"COLUMNS:\n{_catalogue(df)}\n\n"
        f"QUESTION: {question}"
    )


def parse(text: str | None) -> object:
    """The JSON object in a model answer, or `SpecError`.

    Tolerates a Markdown fence and prose around the object, because both are
    common and harmless; everything inside the braces is then validated as
    strictly as a spec a person typed. The first `{` and the last `}` are what
    skip the fence: no regex, because a fence pattern ending in `\\s*` runs in
    quadratic time on a long run of spaces, and the model's text is untrusted.
    """
    if not isinstance(text, str) or not text.strip():
        raise SpecError("the model returned no query spec")
    body = text.strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise SpecError("the model did not return a JSON object")
    try:
        return json.loads(body[start:end + 1])
    except json.JSONDecodeError as exc:
        raise SpecError(f"the model's query spec is not valid JSON ({exc.msg})") from exc


def ask(question: str, df: pd.DataFrame, *, default_return_period: int | None = None) -> Answer:
    """One model call turns `question` into a spec; pandas answers it.

    Provider failures propagate unchanged (the caller decides how to say "no
    model reachable"); a spec the model got wrong is a `SpecError`, never a
    retry.
    """
    question = question.strip()
    if not question:
        raise SpecError("empty question")
    if len(question) > MAX_QUESTION_CHARS:
        raise SpecError(f"question longer than {MAX_QUESTION_CHARS} characters")
    completion = rag.complete_with_provider(prompt(question, df), SYSTEM_PROMPT)
    answer = execute(df, parse(completion.text), default_return_period=default_return_period)
    # The model chose the period; the question may have named a different one.
    # Said beside the rows rather than corrected, because the reading of the
    # question is the human's to settle.
    named = named_periods(question)
    if named and answer.return_period is not None and answer.return_period not in named:
        answer.notes.append(
            f"The question names the 1-in-{' / 1-in-'.join(map(str, named))} year "
            f"flood, but the answer is for the 1-in-{answer.return_period} year "
            "scenario. Ask again naming the period, or send the spec yourself.")
    answer.provider = completion.provider
    answer.fallback_reason = completion.fallback_reason
    return answer
