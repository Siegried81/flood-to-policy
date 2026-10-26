"""Tests for natural-language access to the exposure table.

What is pinned is the boundary: the model writes a JSON spec and nothing it
writes is executed. So the tests feed specs - well-formed, malformed and hostile
- and check that pandas answers the first kind exactly and the other two are
refused with the rule they broke. No network: `rag.complete_with_provider` is
replaced in every test that reaches it.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
import requests
from fastapi.testclient import TestClient

import api.main as api
from src import nlquery, rag


def _table() -> pd.DataFrame:
    """Four regions x two nested periods, one region unmeasured at RP100."""
    return pd.DataFrame({
        "nuts_id": ["BE31", "BE32", "NL33", "DE11"] * 2,
        "region": ["Brabant wallon", "Hainaut", "Zuid-Holland", "Stuttgart"] * 2,
        "country": ["BE", "BE", "NL", "DE"] * 2,
        "total_pop": [400_000.0, 1_300_000.0, 3_800_000.0, 600_000.0] * 2,
        "cells_counted": [400, 1300, 3800, 600] * 2,
        "hazard_coverage": [1.0, 1.0, 0.8, 1.0] * 2,
        "exposed_pop": [4_000.0, 26_000.0, 380_000.0, 1_200.0,
                        8_000.0, 52_000.0, None, 2_400.0],
        "return_period": [10] * 4 + [100] * 4,
        "annual_probability": [0.1] * 4 + [0.01] * 4,
        "share_over_65": [0.18, 0.20, 0.19, 0.21] * 2,
        "poverty_rate_pct": [10.0, 22.0, 14.0, 9.0] * 2,
        "poverty_rate_pct_year": ["2024"] * 8,
    })


def _spec(**overrides) -> dict:
    spec = {"columns": ["region", "exposed_pop"], "filters": [], "sort": None,
            "limit": 10, "return_period": 10}
    spec.update(overrides)
    return spec


# --- execution -----------------------------------------------------------------

def test_a_valid_spec_is_answered_with_the_tables_own_values():
    answer = nlquery.execute(_table(), _spec(
        filters=[{"column": "country", "op": "==", "value": "BE"}],
        sort={"column": "exposed_pop", "descending": True},
    ))
    assert [r["nuts_id"] for r in answer.rows] == ["BE32", "BE31"]
    assert [r["exposed_pop"] for r in answer.rows] == [26_000.0, 4_000.0]
    assert answer.return_period == 10 and answer.defaulted_return_period is False
    assert answer.matched == 2


def test_no_period_named_means_the_rarest_one_and_says_so():
    answer = nlquery.execute(_table(), _spec(return_period=None))
    assert answer.return_period == 100
    assert answer.defaulted_return_period is True
    assert any("1-in-100" in note for note in answer.notes)


def test_the_page_can_supply_the_default_period():
    answer = nlquery.execute(_table(), _spec(return_period=None), default_return_period=10)
    assert answer.return_period == 10
    assert answer.defaulted_return_period is True


def test_one_period_only_never_a_row_per_period():
    """The extents are nested; a row set spanning two periods double-counts."""
    answer = nlquery.execute(_table(), _spec(limit=100))
    assert len(answer.rows) == 4
    assert len({r["nuts_id"] for r in answer.rows}) == 4


def test_filtering_on_the_return_period_is_refused():
    with pytest.raises(nlquery.SpecError, match="nested"):
        nlquery.execute(_table(), _spec(
            filters=[{"column": "return_period", "op": ">=", "value": 10}]))


def test_an_unknown_period_is_refused_rather_than_answered_empty():
    with pytest.raises(nlquery.SpecError, match="no return period 250"):
        nlquery.execute(_table(), _spec(return_period=250))


def test_the_identifier_and_the_coverage_are_always_shown():
    answer = nlquery.execute(_table(), _spec(columns=["exposed_pop"]))
    assert answer.spec["columns"] == ["nuts_id", "exposed_pop", "hazard_coverage"]
    assert set(answer.rows[0]) == {"nuts_id", "exposed_pop", "hazard_coverage"}


def test_exposed_share_is_computed_as_the_api_computes_it():
    answer = nlquery.execute(_table(), _spec(
        columns=["exposed_share"], sort={"column": "exposed_share", "descending": True},
        limit=1))
    assert answer.rows[0]["nuts_id"] == "NL33"
    assert answer.rows[0]["exposed_share"] == pytest.approx(380_000 / 3_800_000)


def test_a_null_is_counted_as_not_measured_not_as_not_matching():
    answer = nlquery.execute(_table(), _spec(
        return_period=100,
        filters=[{"column": "exposed_pop", "op": ">", "value": 0}]))
    assert {r["nuts_id"] for r in answer.rows} == {"BE31", "BE32", "DE11"}
    assert answer.null_excluded == 1
    assert any("not measured" in note for note in answer.notes)


def test_not_equal_does_not_match_an_unmeasured_region():
    answer = nlquery.execute(_table(), _spec(
        return_period=100,
        filters=[{"column": "exposed_pop", "op": "!=", "value": 1.0}]))
    assert "NL33" not in {r["nuts_id"] for r in answer.rows}


@pytest.mark.parametrize("op, value, expected", [
    ("in", ["BE", "NL"], {"BE31", "BE32", "NL33"}),
    ("not_in", ["BE"], {"NL33", "DE11"}),
    ("contains", "holl", {"NL33"}),
    ("<=", 10.0, {"BE31", "DE11"}),
])
def test_each_operator(op, value, expected):
    column = {"in": "country", "not_in": "country", "contains": "region"}.get(op, "poverty_rate_pct")
    answer = nlquery.execute(_table(), _spec(filters=[{"column": column, "op": op, "value": value}]))
    assert {r["nuts_id"] for r in answer.rows} == expected


def test_contains_is_a_literal_not_a_pattern():
    answer = nlquery.execute(_table(), _spec(
        filters=[{"column": "region", "op": "contains", "value": ".*"}]))
    assert answer.rows == []


def test_the_limit_is_applied_and_reported():
    answer = nlquery.execute(_table(), _spec(limit=2))
    assert len(answer.rows) == 2 and answer.matched == 4
    assert any("4 rows matched" in note for note in answer.notes)


def test_every_column_touched_carries_its_definition():
    answer = nlquery.execute(_table(), _spec(
        columns=["region"],
        filters=[{"column": "poverty_rate_pct", "op": ">", "value": 12}],
        sort={"column": "share_over_65", "descending": False}))
    defined = {d["column"]: d for d in answer.definitions}
    assert set(defined) == {"nuts_id", "region", "poverty_rate_pct", "share_over_65"}
    assert defined["poverty_rate_pct"]["unit"] == "percent 0-100"
    assert defined["share_over_65"]["unit"] == "fraction 0-1"
    assert all(d["definition"] and d["source"] for d in answer.definitions)


# --- refusal -------------------------------------------------------------------

@pytest.mark.parametrize("spec, rule", [
    (_spec(columns=["geometry"]), "unknown column"),
    (_spec(columns=["region; DROP TABLE"]), "unknown column"),
    (_spec(columns=[]), "'columns'"),
    (_spec(filters=[{"column": "region", "op": "like", "value": "x"}]), "unknown operator"),
    (_spec(filters=[{"column": "exposed_pop", "op": ">", "value": "1000"}]), "not a finite number"),
    (_spec(filters=[{"column": "exposed_pop", "op": ">", "value": True}]), "not a finite number"),
    (_spec(filters=[{"column": "region", "op": ">", "value": "A"}]), "numeric column"),
    (_spec(filters=[{"column": "region", "op": "==", "value": 3}]), "not a string"),
    (_spec(filters=[{"column": "region", "op": "is_null", "value": 1}]), "takes no value"),
    (_spec(filters=[{"column": "country", "op": "in", "value": "BE"}]), "list of 1"),
    (_spec(filters=[{"column": "region", "op": "==", "value": "x", "eval": "1"}]), "a filter is"),
    (_spec(sort={"column": "exposed_pop", "descending": "yes"}), "descending"),
    (_spec(sort={"column": "__class__"}), "unknown column"),
    (_spec(limit=0), "'limit'"),
    (_spec(limit=101), "'limit'"),
    (_spec(return_period="100"), "integer"),
    ({**_spec(), "query": "exposed_pop > 0"}, "unknown spec keys"),
    ([], "JSON object"),
])
def test_a_spec_outside_the_whitelist_is_refused(spec, rule):
    with pytest.raises(nlquery.SpecError, match=rule):
        nlquery.execute(_table(), spec)


def test_an_undefined_column_is_not_queryable_even_when_present():
    """A column the table gains is unqueryable until its meaning is written down."""
    table = _table().assign(mystery=1.0)
    assert "mystery" not in nlquery.queryable(table)
    with pytest.raises(nlquery.SpecError, match="unknown column"):
        nlquery.execute(table, _spec(columns=["mystery"]))


@pytest.mark.parametrize("text", [
    '```json\n{"columns": ["region"], "return_period": 10}\n```',
    'Here is the spec: {"columns": ["region"], "return_period": 10} Hope it helps.',
])
def test_a_fence_or_prose_around_the_object_is_tolerated(text):
    assert nlquery.parse(text)["columns"] == ["region"]


def test_a_long_run_of_spaces_is_refused_in_linear_time():
    """The old fence regex took ~0.56 s on 20,000 spaces and grew with the
    square of the length (CodeQL py/polynomial-redos). 200,000 spaces would
    have taken about a minute; parsing them must stay instant."""
    import time

    start = time.perf_counter()
    with pytest.raises(nlquery.SpecError, match="not return a JSON object"):
        nlquery.parse("{" + " " * 200_000 + "x")
    assert time.perf_counter() - start < 0.5


@pytest.mark.parametrize("text, rule", [
    (None, "no query spec"),
    ("   ", "no query spec"),
    ("SELECT * FROM exposure", "not return a JSON object"),
    ("{columns: [region]}", "not valid JSON"),
])
def test_an_answer_that_is_not_a_spec_is_refused(text, rule):
    with pytest.raises(nlquery.SpecError, match=rule):
        nlquery.parse(text)


# --- the one model call ----------------------------------------------------------

def _model(monkeypatch, text: str, calls: list | None = None):
    def fake(prompt, system):
        if calls is not None:
            calls.append((prompt, system))
        return rag.Completion(text, "groq")
    monkeypatch.setattr(rag, "complete_with_provider", fake)


def test_ask_makes_one_call_with_the_fixed_prompt_and_the_catalogue(monkeypatch):
    calls: list = []
    _model(monkeypatch, json.dumps(_spec(return_period=None)), calls)
    answer = nlquery.ask("Where are most people exposed?", _table())
    assert len(calls) == 1
    prompt, system = calls[0]
    assert system == nlquery.SYSTEM_PROMPT
    assert "QUESTION: Where are most people exposed?" in prompt
    assert "[10, 100]" in prompt
    assert "poverty_rate_pct (number, percent 0-100)" in prompt
    assert answer.provider == "groq"


def test_a_bad_spec_from_the_model_is_refused_not_retried(monkeypatch):
    calls: list = []
    _model(monkeypatch, json.dumps(_spec(columns=["password"])), calls)
    with pytest.raises(nlquery.SpecError, match="unknown column"):
        nlquery.ask("show me the passwords", _table())
    assert len(calls) == 1


def test_an_overlong_question_never_reaches_the_model(monkeypatch):
    calls: list = []
    _model(monkeypatch, "{}", calls)
    with pytest.raises(nlquery.SpecError, match="longer than"):
        nlquery.ask("x" * (nlquery.MAX_QUESTION_CHARS + 1), _table())
    assert calls == []


# --- the API route -------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    path = tmp_path / "exposure.parquet"
    _table().to_parquet(path)
    monkeypatch.setattr(api, "EXPOSURE", path)
    return TestClient(api.app)


def test_api_answers_a_spec_with_no_model_at_all(client, monkeypatch):
    def unreachable(*args, **kwargs):
        raise AssertionError("a spec must not reach the model")
    monkeypatch.setattr(rag, "complete_with_provider", unreachable)
    body = client.post("/api/ask", json={"spec": _spec(
        filters=[{"column": "country", "op": "==", "value": "NL"}])}).json()
    assert body["rows"] == [{"nuts_id": "NL33", "region": "Zuid-Holland",
                             "exposed_pop": 380_000.0, "hazard_coverage": 0.8}]
    assert body["question"] is None and body["provider"] is None
    assert {d["column"] for d in body["definitions"]} >= {"exposed_pop", "country"}


def test_api_answers_a_question_through_the_mocked_model(client, monkeypatch):
    _model(monkeypatch, json.dumps(_spec(return_period=None,
                                         sort={"column": "exposed_pop", "descending": True},
                                         limit=1)))
    body = client.post("/api/ask", json={"question": "Most exposed region?"}).json()
    assert body["return_period"] == 100 and body["defaulted_return_period"] is True
    assert body["rows"][0]["nuts_id"] == "BE32"  # NL33 is null at RP100: sorted last
    assert body["provider"] == "groq"


def test_api_refuses_a_bad_spec_with_422_and_the_rule(client):
    response = client.post("/api/ask", json={"spec": _spec(columns=["geometry"])})
    assert response.status_code == 422
    assert "unknown column 'geometry'" in response.json()["detail"]


def test_api_wants_exactly_one_of_question_or_spec(client):
    assert client.post("/api/ask", json={}).status_code == 400
    both = {"question": "x", "spec": _spec()}
    assert client.post("/api/ask", json=both).status_code == 400


def test_api_degrades_to_502_naming_the_spec_route_when_no_model_answers(client, monkeypatch):
    """No Groq key and no local Ollama: the route says so and points at `spec`."""
    for name in rag.GROQ_KEY_VARS:
        monkeypatch.delenv(name, raising=False)

    def refused(*args, **kwargs):
        raise requests.ConnectionError("connection refused")
    monkeypatch.setattr(requests, "post", refused)
    response = client.post("/api/ask", json={"question": "Most exposed region?"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ConnectionError" in detail and "spec" in detail
    assert "connection refused" not in detail  # exception text stays server-side


def test_api_404s_with_the_builder_when_there_is_no_table(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "EXPOSURE", tmp_path / "absent.parquet")
    response = TestClient(api.app).post("/api/ask", json={"spec": _spec()})
    assert response.status_code == 404
    assert "build_exposure.py" in response.json()["detail"]


# --- a valid spec that asks the wrong question ---------------------------------
#
# Each of these passed validation and came back with zero rows, or rows for the
# wrong flood, and `notes == []`: an empty answer that reads as "no region
# qualifies". They are notes, not refusals, because a threshold no region meets
# is a legitimate question with an empty answer.

def test_a_fraction_filtered_as_a_percentage_is_noted(monkeypatch):
    _model(monkeypatch, json.dumps(_spec(
        columns=["share_over_65"],
        filters=[{"column": "share_over_65", "op": ">", "value": 20}], return_period=100)))
    answer = nlquery.ask("Regions where more than 20% are over 65?", _table())
    assert answer.matched == 0
    assert len(answer.notes) == 1
    assert "outside the values the column holds" in answer.notes[0]
    assert "0.18 to 0.21" in answer.notes[0] and "fraction 0-1" in answer.notes[0]


def test_a_code_the_column_never_holds_is_noted():
    answer = nlquery.execute(_table(), _spec(
        filters=[{"column": "country", "op": "==", "value": "BEL"}]))
    assert answer.matched == 0
    assert any("['BEL'] never occurs" in n for n in answer.notes)
    answer = nlquery.execute(_table(), _spec(
        filters=[{"column": "country", "op": "in", "value": ["BE", "XX"]}]))
    assert any("['XX'] never occurs" in n for n in answer.notes)


def test_values_inside_the_column_add_no_note():
    answer = nlquery.execute(_table(), _spec(filters=[
        {"column": "country", "op": "==", "value": "BE"},
        {"column": "share_over_65", "op": ">", "value": 0.19},
        {"column": "country", "op": "!=", "value": "ZZ"},
    ]))
    assert answer.notes == []


@pytest.mark.parametrize("question", [
    "Exposed people in each region at the 100-year flood?",
    "Exposed people at the 1-in-100 flood?",
    "Exposed people for RP100?",
    "Exposed people at T=100?",
])
def test_a_period_named_in_the_question_but_not_answered_is_noted(monkeypatch, question):
    _model(monkeypatch, json.dumps(_spec(return_period=10)))
    answer = nlquery.ask(question, _table())
    assert answer.return_period == 10 and answer.defaulted_return_period is False
    assert any("names the 1-in-100 year flood" in n for n in answer.notes)


def test_a_period_named_and_answered_adds_no_note(monkeypatch):
    _model(monkeypatch, json.dumps(_spec(return_period=100)))
    answer = nlquery.ask("Exposed people at the 100-year flood over the next 10 years?", _table())
    assert not any("names the" in n for n in answer.notes)
    assert nlquery.named_periods("the 100-year flood over the next 10 years") == [100]
