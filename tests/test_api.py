"""Tests for the JSON API the React UI reads.

The failure modes pinned here are the ones where a wrong number still *looks*
like a number: a total summed over nested return periods, a ranking built on a
period nobody chose, a polygon reaching the prompt, and a provider's empty turn
arriving as a 500. Every one of them was reachable with no error anywhere.

No network: `rag.complete` and `rag.search` are monkeypatched in every test that
touches them, and `rag.load_index` is stubbed out of `/api/meta` so the suite
never reads the corpus off disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as api
from api.main import app, vulnerability_indicators

ROOT = Path(__file__).resolve().parents[1]


# Three regions x three nested return periods, built to make both defects visible
# in one table:
#
# - exposure per period is {10: 1500, 100: 6000, 500: 14000}, so a total taken
#   over the whole table is 21500 - the core floodplain counted three times;
# - `exposed_pop` is min-max scaled within whichever rows are ranked, and the
#   spread between the regions is not the same in every period, so the ranking
#   reads BE31, BE32, BE33 on RP10 and BE31, BE33, BE32 on RP500. The
#   second-ranked region flips, which is what makes an unstated period a silent
#   answer to "who do we help first".
#
# `share_over_65` is constant per region, as a real indicator would be: it is a
# property of the population, not of the flood.
def _nested_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nuts_id": ["BE31", "BE32", "BE33"] * 3,
            "exposed_pop": [
                750.0, 675.0, 75.0,      # RP10  -> 1500
                3000.0, 400.0, 2600.0,   # RP100 -> 6000
                7000.0, 700.0, 6300.0,   # RP500 -> 14000
            ],
            "total_pop": [100_000.0, 50_000.0, 30_000.0] * 3,
            "share_over_65": [0.90, 0.50, 0.55] * 3,
            "return_period": [10] * 3 + [100] * 3 + [500] * 3,
            "annual_probability": [0.1] * 3 + [0.01] * 3 + [0.002] * 3,
        }
    )


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    """Point the API at a throwaway parquet, and hand back a writer for it.

    Parquet rather than a stubbed `_table`, so the dtype round-trip the real app
    depends on is in the path under test.
    """

    def write(df: pd.DataFrame) -> None:
        path = tmp_path / "exposure.parquet"
        df.to_parquet(path)
        monkeypatch.setattr(api, "EXPOSURE", path)

    write(_nested_table())
    return write


@pytest.fixture
def client(frozen) -> TestClient:
    return TestClient(app)


# --- the nested-period total ----------------------------------------------------

def test_exposure_without_a_period_does_not_sum_the_nested_periods(client):
    """The defect: no `return_period` meant "every row", so `total_exposed` was
    1500 + 6000 + 14000 = 21500 - the core floodplain counted once per period.

    There is no "all periods" reading of this table, so naming no period now
    narrows to the rarest one and the response says so.
    """
    body = client.get("/api/exposure").json()
    assert body["total_exposed"] == pytest.approx(14000.0)
    assert body["return_period"] == 500
    assert body["defaulted_return_period"] is True
    assert len(body["rows"]) == 3  # one row per region, not one per region x period


@pytest.mark.parametrize("period, total", [(10, 1500.0), (100, 6000.0), (500, 14000.0)])
def test_each_period_reports_only_its_own_exposure(client, period, total):
    body = client.get(f"/api/exposure?return_period={period}").json()
    assert body["total_exposed"] == pytest.approx(total)
    assert body["return_period"] == period
    assert body["defaulted_return_period"] is False


def test_unmeasured_is_not_multiplied_by_the_number_of_periods(client, frozen):
    """`unmeasured` counted the same uncovered region once per period too, so a
    single region with no raster coverage was reported as three."""
    table = _nested_table()
    table.loc[table["nuts_id"] == "BE32", "exposed_pop"] = None
    frozen(table)
    body = TestClient(app).get("/api/exposure").json()
    assert body["unmeasured"] == 1


def test_an_unknown_period_is_refused_rather_than_reported_as_zero(client):
    """An empty selection would report total_exposed 0.0, which reads as
    "measured, nobody exposed" for a scenario that was never computed."""
    response = client.get("/api/exposure?return_period=250")
    assert response.status_code == 400
    assert "250" in response.json()["detail"]


def test_a_table_without_periods_is_served_whole(client, frozen):
    """One row per region already, so there is nothing to narrow and nothing to
    double count."""
    frozen(_nested_table().query("return_period == 100").drop(columns=["return_period"]))
    body = TestClient(app).get("/api/exposure").json()
    assert body["return_period"] is None
    assert body["defaulted_return_period"] is False
    assert body["total_exposed"] == pytest.approx(6000.0)


def test_a_missing_exposure_column_reports_null_not_zero(client, frozen):
    """Another agent owns the exposure columns. If `exposed_pop` is absent the
    totals must come back null: "not measured" and "zero" must not share a shape.
    """
    frozen(_nested_table().drop(columns=["exposed_pop"]))
    body = TestClient(app).get("/api/exposure").json()
    assert body["total_exposed"] is None
    assert body["unmeasured"] is None


def test_an_unknown_column_does_not_break_the_route(client, frozen):
    """A column this UI has never heard of - `hazard_coverage`, added upstream while this
    was written - rides along in `rows` and changes no figure here."""
    table = _nested_table()
    table["hazard_coverage"] = 0.42
    frozen(table)
    body = TestClient(app).get("/api/exposure").json()
    assert body["total_exposed"] == pytest.approx(14000.0)
    assert body["rows"][0]["hazard_coverage"] == pytest.approx(0.42)


def test_exposed_share_is_computed_server_side(client):
    """It is the figure that should be ranked, so it is not left to the client."""
    rows = {r["nuts_id"]: r for r in client.get("/api/exposure?return_period=10").json()["rows"]}
    # BE32 is the most exposed per inhabitant and the second most in absolute
    # count: the two rankings are genuinely different questions.
    assert rows["BE31"]["exposed_share"] == pytest.approx(0.0075)
    assert rows["BE32"]["exposed_share"] == pytest.approx(0.0135)
    assert rows["BE33"]["exposed_share"] == pytest.approx(0.0025)


# --- the ranking's return period ------------------------------------------------

def _rank(client, period=None, indicators=("exposed_pop", "share_over_65")):
    payload = {"indicators": list(indicators), "perturbation": 0.0, "top_n": 1}
    if period is not None:
        payload["return_period"] = period
    body = client.post("/api/vulnerability", json=payload).json()
    return body, [row["nuts_id"] for row in body["rows"]]


def test_the_ranking_is_built_on_the_period_asked_for(client):
    """The defect: `drop_duplicates` kept the first row per region, and the
    periods are concatenated shortest-first, so every ranking was RP10's -
    whatever the user had selected on the map.

    Here the two indicators pull against each other, so the order genuinely
    differs between periods. That is the point: the period is part of the finding.
    """
    _, at_10 = _rank(client, 10)
    _, at_500 = _rank(client, 500)
    assert at_10 == ["BE31", "BE32", "BE33"]
    assert at_500 == ["BE31", "BE33", "BE32"]


def test_the_ranking_names_the_period_it_used(client):
    """Neither UI could state which scenario the ranking was for, because the
    response did not carry it."""
    body, _ = _rank(client, 100)
    assert body["return_period"] == 100
    assert body["defaulted_return_period"] is False


def test_an_unnamed_period_defaults_to_the_rarest_and_admits_it(client):
    """The same default both UIs show, and flagged, so a curl caller that never
    chose can tell the ranking is for one scenario the server picked."""
    body, order = _rank(client)
    assert body["return_period"] == 500
    assert body["defaulted_return_period"] is True
    assert order == _rank(client, 500)[1]


def test_the_ranking_covers_every_region_exactly_once(client):
    """Without the narrowing, `total` was the region count only because
    drop_duplicates silently threw two thirds of the table away."""
    body, order = _rank(client, 10)
    assert body["total"] == 3
    assert len(set(order)) == 3


def test_an_unknown_indicator_is_refused(client):
    response = client.post("/api/vulnerability", json={"indicators": ["not_collected"]})
    assert response.status_code == 400
    assert "not_collected" in response.json()["detail"]


def test_a_scenario_column_is_refused_as_an_indicator(client):
    """`annual_probability` as a vulnerability indicator reads as "a more frequent
    flood makes residents more vulnerable", which is not a claim about
    vulnerability. The offer list excluded it; so does the accept list, or a
    hand-written request could still weight it."""
    response = client.post(
        "/api/vulnerability", json={"indicators": ["exposed_pop", "annual_probability"]}
    )
    assert response.status_code == 400
    assert "annual_probability" in response.json()["detail"]



@pytest.mark.parametrize("column", ["nuts_id", "region_label"])
def test_a_column_that_is_not_a_number_is_refused_as_an_indicator(client, frozen, column):
    """The accept list was "any column", so the join key crashed the scaling
    with a 500 and a text column (a year stored as a string) came back 200 with
    a ranking of zeros. Only what `/api/meta` offers can be weighted."""
    table = _nested_table()
    table["region_label"] = ["Arr. Bruxelles", "Halle-Vilvoorde", "Leuven"] * 3
    frozen(table)
    response = client.post("/api/vulnerability", json={"indicators": ["exposed_pop", column]})
    assert response.status_code == 400
    assert column in response.json()["detail"]


# --- one indicator list, two UIs ------------------------------------------------

def test_scenario_columns_are_never_offered_as_indicators():
    """The list is a weighted mean's membership, so a UI offering one extra column
    reports a different composite score for the same region."""
    offered = vulnerability_indicators(_nested_table())
    assert "return_period" not in offered
    assert "annual_probability" not in offered
    assert offered == ["exposed_pop", "share_over_65"]


def test_a_denominator_is_not_an_indicator():
    """`total_pop` is how many people live there, not how badly they fare.

    Min-max scaled into an equally weighted mean, it ranks a region as vulnerable
    for being populous - Ile-de-France above every flooded valley in Europe. It is
    also absent from `vulnerability.DEFAULT_WEIGHTS`, which is where this index
    says what it is made of, so offering it contradicted the module's own
    definition. Measured 2026-10-06: the continental rebuild added the column and
    the offer list became `["total_pop", "exposed_pop"]` - with `total_pop` first,
    so both UIs, which default to the head of this list, silently changed what
    they scored.
    """
    offered = vulnerability_indicators(_nested_table())
    assert "total_pop" not in offered


def test_the_offer_list_keeps_table_order():
    """Both UIs default to the head of the list, so the order decides the default
    selection and has to match between them."""
    assert vulnerability_indicators(_nested_table())[:2] == [
        "exposed_pop", "share_over_65"
    ]


def test_non_numeric_columns_are_not_offered():
    offered = vulnerability_indicators(_nested_table())
    assert "nuts_id" not in offered


def test_the_streamlit_app_imports_the_shared_decisions_rather_than_restating_them():
    """A source check, deliberately: the two UIs disagreed because each built its
    own list, and the only way that cannot come back is for one of them to have no
    list of its own. Importing the app to assert this would run the whole page.

    `climate_periods` is held to the same rule for the same reason. It decides
    what a period's figures are allowed to claim - whether a one-member period
    reads as "direction not established" or as "the models disagree" - and two
    UIs answering that differently from one file is the same defect as two
    indicator lists.
    """
    source = (api.ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
    imported = next(
        (line for line in source.splitlines() if line.startswith("from api.main import")),
        "",
    )
    for shared in ("vulnerability_indicators", "climate_periods"):
        assert shared in imported, f"{shared} is not imported from api.main"
    assert "vulnerability_indicators(exposure)" in source
    assert "climate_periods(context)" in source
    # The restated comprehension that caused the disagreement, in either spelling.
    assert 'c != "return_period"' not in source
    # And the restated caveat: the suffix arithmetic that reads a period's member
    # count belongs in one place, not in a UI.
    assert 'startswith("ensemble_members_")' not in source


# --- the prompt ------------------------------------------------------------------

def _stub_model(monkeypatch, reply="A sentence about flooding [S1]."):
    """Capture the prompt and answer without a network call."""
    seen = {}

    def complete(prompt, *args, **kwargs):
        seen["prompt"] = prompt
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(
        api.rag, "search",
        lambda q, k=5: [{"text": "Flood risk management plans.", "source": "dir.html", "score": 9.0}],
    )
    monkeypatch.setattr(api.rag, "complete", complete)
    return seen


def test_geometry_never_reaches_the_prompt(client, frozen, monkeypatch):
    """The defect: `to_toon` was called straight on the parquet, and `flatten` is
    the only thing that drops `geometry`. A polygon is thousands of tokens of
    coordinates the model can do nothing with, times `rows`.
    """
    table = _nested_table()
    table["geometry"] = [b"\x01\x06\x00\x00" * 100] * len(table)  # a WKB-shaped stub
    frozen(table)
    seen = _stub_model(monkeypatch)

    response = TestClient(app).post("/api/draft", json={"question": "flood risk plans?"})
    assert response.status_code == 200

    table_block = seen["prompt"].split("TABLE:\n", 1)[1].split("\n\n", 1)[0]
    assert "geometry" not in table_block
    assert "\\x01" not in table_block
    # Header row plus one row per table row, and every row short enough to be the
    # figures rather than a polygon.
    assert all(len(line) < 120 for line in table_block.splitlines())


def _prompt_rows(prompt: str) -> list[dict]:
    """The prompt's TOON table block, one dict per row, keyed by its header."""
    block = prompt.split("TABLE:\n", 1)[1].split("\n\n", 1)[0].splitlines()
    header = block[0].split("{", 1)[1].split("}", 1)[0].split(",")
    return [dict(zip(header, line.strip().split(","))) for line in block[1:] if line.strip()]


def test_a_draft_sees_one_scenario_ranked_by_share(client, monkeypatch):
    """The defect: `_table().head(rows)` is file order, so the model read the
    first 200 rows - Albania to Germany at the 10-year period - whatever the
    page showed. No period now means the rarest one, as on every other route,
    and the rows are the most exposed by share, not the first alphabetically."""
    seen = _stub_model(monkeypatch)
    body = client.post("/api/draft", json={"question": "flood risk plans?"}).json()
    assert body["return_period"] == 500
    rows = _prompt_rows(seen["prompt"])
    assert len(rows) == 3, "one row per region, not one per region x period"
    # RP500 shares: BE33 0.21, BE31 0.07, BE32 0.014.
    assert [r["nuts_id"] for r in rows] == ["BE33", "BE31", "BE32"]
    assert "ranked by the share" in seen["prompt"] and "1-in-500" in seen["prompt"]
    assert body["ranked"] is True


def test_a_draft_never_claims_a_ranking_it_did_not_make(client, frozen, monkeypatch):
    """Without `total_pop` there is no share to rank by, so the rows stay in file
    order - and the prompt and the panel must not call them "ranked by share"."""
    frozen(pd.DataFrame({"nuts_id": ["A", "B", "C"], "exposed_pop": [1.0, 900.0, 50.0]}))
    seen = _stub_model(monkeypatch)
    body = client.post("/api/draft", json={"question": "flood risk plans?"}).json()
    assert body["ranked"] is False
    assert "ranked" not in seen["prompt"].split("TABLE:")[0]
    assert "not the whole table" in seen["prompt"]


def test_a_draft_follows_the_period_the_reader_chose(client, monkeypatch):
    seen = _stub_model(monkeypatch)
    body = client.post("/api/draft", json={"question": "q?", "return_period": 10}).json()
    assert body["return_period"] == 10
    assert sorted(float(r["exposed_pop"]) for r in _prompt_rows(seen["prompt"])) == [75.0, 675.0, 750.0]
    assert client.post("/api/draft", json={"question": "q?", "return_period": 7}).status_code == 400


def test_a_draft_prompt_stays_inside_the_provider_budget(client, frozen, monkeypatch):
    """200 rows of the real table were 29,613 characters against an 11,000
    budget, so every draft over Groq came back 413 and fell to the small local
    model. The table is cut to what the budget leaves."""
    big = pd.DataFrame({
        "nuts_id": [f"XX{i:04d}" for i in range(2000)],
        "exposed_pop": [float(i) for i in range(2000)],
        "total_pop": [10_000.0] * 2000,
        "return_period": [100] * 2000,
        "annual_probability": [0.01] * 2000,
    })
    frozen(big)
    seen = _stub_model(monkeypatch)
    client.post("/api/draft", json={"question": "flood risk plans?", "rows": 2000})
    assert len(seen["prompt"]) + len(api.rag.SYSTEM_PROMPT) <= api.rag.PROMPT_CHAR_BUDGET


def test_the_token_report_describes_the_table_actually_sent(client, frozen, monkeypatch):
    """Reported on the unflattened frame, the saving was a measurement of a prompt
    that is not the one the model received."""
    table = _nested_table()
    table["geometry"] = [b"\x01\x06\x00\x00" * 100] * len(table)
    frozen(table)
    _stub_model(monkeypatch)

    body = TestClient(app).post("/api/draft", json={"question": "flood risk plans?"}).json()
    tokens = body["tokens"]
    if not tokens.get("available", True):
        pytest.skip(tokens["reason"])
    # 600 bytes of WKB per row would dwarf this.
    assert tokens["toon_tokens"] < 400


def test_a_silent_corpus_refuses_before_any_model_call(client, monkeypatch):
    called = []
    monkeypatch.setattr(api.rag, "search", lambda q, k=5: [])
    monkeypatch.setattr(api.rag, "complete", lambda *a, **k: called.append(1))
    body = client.post("/api/draft", json={"question": "capital gains tax in Portugal?"}).json()
    assert body["refused"] is True
    assert body["draft"] is None
    assert not called


# --- an empty turn from the provider --------------------------------------------

def test_an_empty_completion_is_a_502_not_a_500(client, monkeypatch):
    """The defect: `rag.complete` returns None when the model answers with
    message.content: null, and only the call itself was inside the `try`. The
    verification below it then raised TypeError from inside a regex, so the
    provider's empty turn reached the client as a 500 - our bug, not theirs.

    `rag.py` belongs to another agent; this is the call site refusing to pass None
    on to the verification.
    """
    _stub_model(monkeypatch, reply=None)
    response = client.post("/api/draft", json={"question": "flood risk plans?"})
    assert response.status_code == 502
    assert "empty completion" in response.json()["detail"]


def test_an_unreachable_provider_is_a_502(client, monkeypatch):
    _stub_model(monkeypatch, reply=RuntimeError("connection refused"))
    response = client.post("/api/draft", json={"question": "flood risk plans?"})
    assert response.status_code == 502
    assert "No model reachable (RuntimeError)" in response.json()["detail"]


def test_the_provider_error_text_is_logged_not_returned(client, monkeypatch, caplog):
    """CodeQL py/stack-trace-exposure: the exception message was echoed in the
    502 detail, and an SDK or HTTP error names hosts, paths and request parts.
    The class name is enough for the client; the message goes to the log."""
    leak = "connection refused to http://10.0.0.7:11434 reading /home/ops/.env"
    _stub_model(monkeypatch, reply=RuntimeError(leak))
    with caplog.at_level("WARNING", logger="api.main"):
        response = client.post("/api/draft", json={"question": "flood risk plans?"})
    assert response.status_code == 502
    assert "10.0.0.7" not in response.text and "/home/ops" not in response.text
    assert leak in caplog.text


def test_an_unavailable_token_report_keeps_its_reason_server_side(client, monkeypatch, caplog):
    """The reason quotes tiktoken's exception - its cache path or the URL it
    failed to fetch. The response still says nothing was measured."""
    _stub_model(monkeypatch)
    secret = r"tiktoken unavailable: [Errno 13] C:\Users\ops\AppData\Local\Temp\data-gym-cache"
    monkeypatch.setattr(api, "token_report", lambda df, name: {
        "toon_tokens": None, "json_tokens": None, "saving_pct": None,
        "available": False, "reason": secret})
    with caplog.at_level("WARNING", logger="api.main"):
        tokens = client.post("/api/draft", json={"question": "flood risk plans?"}).json()["tokens"]
    assert tokens["available"] is False and tokens["toon_tokens"] is None
    assert "ops" not in tokens["reason"] and "tiktoken unavailable" in tokens["reason"]
    assert secret in caplog.text


def test_a_real_answer_travels_with_its_verification(client, monkeypatch):
    """The draft is never returned on its own: the score and any invalid citation
    go with it, so the human pressing approve is deciding informed."""
    _stub_model(monkeypatch, reply="Flood risk management plans matter [S1][S4].")
    body = client.post("/api/draft", json={"question": "flood risk plans?"}).json()
    assert body["refused"] is False
    assert 0.0 <= body["grounding"] <= 1.0
    assert body["invalid_citations"] == [4]


# --- meta, and the missing-table paths ------------------------------------------

def test_meta_reports_the_periods_and_the_offer_list(client, monkeypatch):
    monkeypatch.setattr(api.rag, "load_index", lambda *a, **k: type("I", (), {"passages": []})())
    body = client.get("/api/meta").json()
    assert body["return_periods"] == [10, 100, 500]
    assert body["indicators"] == ["exposed_pop", "share_over_65"]
    assert body["regions"] == 3
    assert body["rows"] == 9


def test_meta_says_whether_approve_needs_a_token_and_never_what_it_is(client, monkeypatch):
    """The React approve button sent no token, so setting FLOOD_APPROVE_TOKEN as
    `.env.example` advises turned every approval into a 403. The UI now asks the
    approver for it - when, and only when, meta says the server will check."""
    monkeypatch.setattr(api.rag, "load_index", lambda *a, **k: type("I", (), {"passages": []})())
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    assert client.get("/api/meta").json()["approve_token_required"] is False
    monkeypatch.setenv("FLOOD_APPROVE_TOKEN", "s3cret-test-value")
    response = client.get("/api/meta")
    assert response.json()["approve_token_required"] is True
    assert "s3cret-test-value" not in response.text



def test_the_react_map_carries_the_boundary_credit():
    """The GISCO terms require the EuroGeographics line on any map drawn from
    the NUTS boundaries; `svgmap` draws it into the Streamlit map, and the
    React map has to say it in its own caption."""
    source = (ROOT / "web" / "src" / "components" / "Choropleth.jsx").read_text(encoding="utf-8")
    caption = source.split("<figcaption>", 1)[1].split("</figcaption>", 1)[0]
    assert "© EuroGeographics for the administrative boundaries" in caption


def test_the_react_approve_call_carries_the_token_header():
    """The server reads `X-Approve-Token`; a client that never sends it cannot
    approve once the token is set. Pinned on the source, as the other JSX guards are."""
    client_js = (ROOT / "web" / "src" / "api.js").read_text(encoding="utf-8")
    assert '"X-Approve-Token": token' in client_js
    panel = (ROOT / "web" / "src" / "components" / "DraftPanel.jsx").read_text(encoding="utf-8")
    assert "approve(edited, token)" in panel and 'type="password"' in panel


def test_no_table_is_a_404_that_says_how_to_build_one(tmp_path, monkeypatch):
    """The 404 has to name something the reader can RUN. It used to name the
    function `exposure_by_return_period`, which is a library call and not how the
    file is produced; the runnable answer is the script."""
    monkeypatch.setattr(api, "EXPOSURE", tmp_path / "absent.parquet")
    response = TestClient(app).get("/api/exposure")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "scripts/build_exposure.py" in detail
    assert "src.fetch" in detail, "the script needs rasters that are not committed"


def test_no_geometry_is_a_404_that_names_its_builder(tmp_path, monkeypatch):
    """The choropleth is the deliverable the jury looks at first, and this file
    is the one input nothing in the repo produced for months: the endpoint 404s,
    `Choropleth.jsx` returns null, and no error reaches the screen. The message
    is the only place a reader learns which script makes it."""
    monkeypatch.setattr(api, "GEOMETRY", tmp_path / "absent.geojson")
    response = TestClient(app).get("/api/geometry")
    assert response.status_code == 404
    assert "scripts/build_geometry.py" in response.json()["detail"]


def test_no_region_identifier_is_a_500_that_names_the_problem(frozen):
    frozen(_nested_table().drop(columns=["nuts_id"]))
    response = TestClient(app).get("/api/exposure")
    assert response.status_code == 500
    assert "region identifier" in response.json()["detail"]


def test_approve_is_the_only_route_that_writes(tmp_path, monkeypatch, client):
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    body = client.post("/api/approve", json={"text": "Approved text, unchanged."}).json()
    written = (tmp_path / "approved.md").read_text(encoding="utf-8")
    assert "Approved text, unchanged." in written
    assert body["approved_at"]


def test_approve_without_a_token_accepts_the_docker_port_forward(tmp_path, monkeypatch, frozen):
    """No token configured: a caller behind Docker's port-forward may approve.

    The React UI on the host reaches the API container through the published
    port, so the container sees the bridge gateway, never loopback. Refusing
    non-loopback callers turned the Approve button into a 403 under Docker.
    """
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    gateway = TestClient(app, client=("172.17.0.1", 50000))
    assert gateway.post("/api/approve", json={"text": "x"}).status_code == 200
    assert (tmp_path / "approved.md").exists()


def test_approve_requires_the_configured_token(tmp_path, monkeypatch, client):
    """With a token set, even a local caller must present it."""
    monkeypatch.setenv("FLOOD_APPROVE_TOKEN", "s3cret-test-value")
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    assert client.post("/api/approve", json={"text": "x"}).status_code == 403
    wrong = {"X-Approve-Token": "nope"}
    assert client.post("/api/approve", json={"text": "x"}, headers=wrong).status_code == 403
    assert not (tmp_path / "approved.md").exists()
    remote = TestClient(app, client=("203.0.113.7", 50000))
    good = {"X-Approve-Token": "s3cret-test-value"}
    assert remote.post("/api/approve", json={"text": "x"}, headers=good).status_code == 200


def test_approve_caps_the_text_length(tmp_path, monkeypatch, client):
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    too_long = "a" * (api.MAX_APPROVED_CHARS + 1)
    assert client.post("/api/approve", json={"text": too_long}).status_code == 422


@pytest.mark.parametrize("k", [0, -1, api.rag.MAX_PASSAGES + 1])
def test_search_bounds_k(monkeypatch, client, k):
    monkeypatch.setattr(api.rag, "search", lambda q, k=5: [])
    assert client.get("/api/search", params={"q": "flood", "k": k}).status_code == 422


def test_geojson_is_served_verbatim(tmp_path, monkeypatch, client):
    """Drawn as SVG in the browser, so there is no tile provider to fail."""
    path = tmp_path / "regions.geojson"
    payload = {"type": "FeatureCollection", "features": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(api, "GEOMETRY", path)
    assert client.get("/api/geometry").json() == payload


# --- translation ----------------------------------------------------------------

def test_the_languages_route_offers_the_three_and_not_english():
    """The client fetches this rather than hardcoding a list, so the list is a
    route. English is the source: offering it invites a round trip, and a
    translation of a translation is how a figure quietly changes."""
    body = TestClient(app).get("/api/languages").json()
    assert [entry["code"] for entry in body["languages"]] == ["de", "fr", "nl"]
    assert [entry["name"] for entry in body["languages"]] == [
        "German", "French", "Dutch"
    ]


def test_a_faithful_translation_comes_back_with_what_was_checked(monkeypatch):
    """The counts are returned so the panel can say "7 figures checked" rather
    than asking the reader to trust the word translated."""
    from src import translate as translate_module
    monkeypatch.setattr(
        translate_module, "complete",
        lambda *a, **k: "Pour une periode de retour de 100 ans, 29 727 887 "
                        "habitants sont exposes [S1].",
    )
    body = TestClient(app).post("/api/translate", json={
        "text": "At the 100-year return period, 29,727,887 residents are exposed [S1].",
        "language": "fr",
    }).json()
    assert body["language_name"] == "French"
    assert body["numbers_checked"] == 2
    assert body["citations_checked"] == 1
    assert "29 727 887" in body["text"]


def test_a_translation_that_moved_a_figure_is_a_422_not_a_warning(monkeypatch):
    """422 rather than 200 with a flag, deliberately: a client that forgot to
    read the flag would render a paragraph quoting a figure the table does not
    contain, which is the worst state this service can be in."""
    from src import translate as translate_module
    monkeypatch.setattr(
        translate_module, "complete",
        lambda *a, **k: "Pour une periode de retour de 100 ans, 29,7 millions "
                        "d'habitants sont exposes [S1].",
    )
    resp = TestClient(app).post("/api/translate", json={
        "text": "At the 100-year return period, 29,727,887 residents are exposed [S1].",
        "language": "fr",
    })
    assert resp.status_code == 422
    assert "figures changed" in resp.json()["detail"]
    assert "29,7 millions" not in resp.text


def test_an_unknown_language_is_400_not_422(monkeypatch):
    """A bad request, distinguishable from a translation that was produced and
    rejected - the client has to tell "fix your call" from "the model drifted"."""
    from src import translate as translate_module

    def explode(*_a, **_k):
        raise AssertionError("the model must not be called for a bad language")
    monkeypatch.setattr(translate_module, "complete", explode)
    resp = TestClient(app).post("/api/translate", json={"text": "x", "language": "en"})
    assert resp.status_code == 400
    assert "not a target language" in resp.json()["detail"]


def test_an_unreachable_model_is_502(monkeypatch):
    """Same contract as `/api/draft`: the failure is upstream, and the status
    code is the only thing telling the client that."""
    from src import translate as translate_module

    def dead(*_a, **_k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(translate_module, "complete", dead)
    resp = TestClient(app).post("/api/translate", json={"text": "42 [S1]", "language": "nl"})
    assert resp.status_code == 502
    assert "No model reachable" in resp.json()["detail"]


def test_the_react_panel_fetches_the_language_list_rather_than_restating_it():
    """A source check, like the one on the Streamlit indicator list.

    There is no JS test harness in this repo - CI runs pytest only - so the one
    thing worth pinning about the React panel is pinned from here: a hardcoded
    `["fr", "nl", "de"]` in the client would drift from `translate.LANGUAGES` the
    moment a language is added or dropped, and the drift would show up as a tab
    offering a language the server refuses with a 400.
    """
    panel = (ROOT / "web" / "src" / "components" / "TranslationPanel.jsx").read_text(
        encoding="utf-8"
    )
    assert "getLanguages" in panel
    for code in ("fr", "nl", "de"):
        assert f'"{code}"' not in panel.replace('useState("fr")', ""), (
            f"`{code}` is written into the panel; fetch /api/languages instead"
        )


# --- the context table ----------------------------------------------------------

# Two periods, differing only in how many model chains they have, because that is
# the whole point of the block: 2041-2070 carries two members and can agree with
# itself, 2071-2100 carries one and cannot. The real archive is shaped exactly
# this way - `src.climate.ensemble_change_by_region` writes
# `ensemble_agrees_on_sign` False for every region of a one-member period, so a
# reader sees the same zero whether the models were absent or in conflict.
def _context_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nuts_id": ["BE31", "BE32", "BE33"],
            "exposed_built_m2_rp100": [1_000.0, 2_000.0, 3_000.0],
            "built_total_m2": [10_000.0, 10_000.0, 10_000.0],
            "built_share_exposed_rp100": [0.1, 0.2, 0.3],
            "shared_basin_share": [1.0, 0.5, 0.0],
            "apsfr_share": [0.4, None, 0.0],
            "apsfr_declared": [True, False, False],
            # BE32 stands for a region whose country the layer never carried -
            # Ireland on the real service. Its share is None, not 0.0.
            "apsfr_country_reported": [True, False, True],
            "apsfr_cycle": ["2018", "2018", "2018"],
            "basin_countries_max": [3, 2, 1],
            "change_pct_ensemble_median_2041_2070": [10.0, 20.0, 30.0],
            "change_pct_ensemble_min_2041_2070": [5.0, 15.0, 25.0],
            "change_pct_ensemble_max_2041_2070": [15.0, 25.0, 35.0],
            "ensemble_members_2041_2070": [2, 2, 2],
            "ensemble_agrees_on_sign_2041_2070": [True, True, False],
            "change_pct_ensemble_median_2071_2100": [40.0, 50.0, 60.0],
            "change_pct_ensemble_min_2071_2100": [40.0, 50.0, 60.0],
            "change_pct_ensemble_max_2071_2100": [40.0, 50.0, 60.0],
            "ensemble_members_2071_2100": [1, 1, 1],
            "ensemble_agrees_on_sign_2071_2100": [False, False, False],
        }
    )


@pytest.fixture
def frozen_context(tmp_path, monkeypatch):
    """Point the API at a throwaway context parquet, and hand back a writer."""

    def write(df: pd.DataFrame) -> None:
        path = tmp_path / "context.parquet"
        df.to_parquet(path)
        monkeypatch.setattr(api, "CONTEXT", path)

    write(_context_table())
    return write


def test_a_single_member_period_says_why_nothing_agrees(client, frozen_context):
    """The figure a one-member period must NOT be allowed to imply.

    `regions_agreeing_on_sign` is 0 for 2071-2100 because one member cannot
    agree with itself, not because the models conflict - and those two read
    identically off the count alone. `single_member` is the column that separates
    them, so a UI can print "one model chain, direction not established" instead
    of "the models disagree", which is a different and wrong claim.

    The median still travels: it is a real measurement, it just is not a
    projection.
    """
    periods = {p["period"]: p for p in client.get("/api/context").json()["climate_periods"]}

    far = periods["2071-2100"]
    assert far["members"] == 1
    assert far["single_member"] is True
    assert far["regions_agreeing_on_sign"] == 0
    assert far["median_change_pct"] == pytest.approx(50.0)

    near = periods["2041-2070"]
    assert near["single_member"] is False
    assert near["regions_agreeing_on_sign"] == 2
    assert near["median_change_pct"] == pytest.approx(20.0)


def test_chains_far_apart_mark_the_size_as_uncertain(client, frozen_context):
    """Two chains reading +92% and +414% average to +253%, the top of Europe.

    Measured on context.parquet 2026-10-13 for DE94H, 2071-2100. Both chains
    agree on the direction, so the old ranking put the region first, on a median
    that is the mean of two different stories. More than MODEL_SPREAD_PP points
    apart, the region is flagged, counted, and both UIs leave it out of the
    ranking. A region measured nowhere is not uncertain: there is nothing to be
    uncertain about.
    """
    table = _context_table()
    table["change_pct_ensemble_median_2041_2070"] = [253.2, 20.0, None]
    table["change_pct_ensemble_min_2041_2070"] = [92.1, 15.0, None]
    table["change_pct_ensemble_max_2041_2070"] = [414.3, 25.0, None]
    frozen_context(table)
    body = TestClient(app).get("/api/context").json()

    flags = [row["ensemble_size_uncertain_2041_2070"] for row in body["rows"]]
    assert flags == [True, False, False]
    near = {p["period"]: p for p in body["climate_periods"]}["2041-2070"]
    assert near["regions_size_uncertain"] == 1
    assert near["model_spread_pp"] == api.MODEL_SPREAD_PP


def test_the_periods_are_read_off_the_column_names(client, frozen_context):
    """`scripts/build_context.py` suffixes its climate columns with the period, so
    a period added to the build has to surface here without this file changing."""
    table = _context_table()
    table["change_pct_ensemble_median_2011_2040"] = [1.0, 2.0, 3.0]
    table["ensemble_members_2011_2040"] = [2, 2, 2]
    table["ensemble_agrees_on_sign_2011_2040"] = [True, True, True]
    frozen_context(table)
    body = TestClient(app).get("/api/context").json()
    assert [p["period"] for p in body["climate_periods"]] == [
        "2011-2040", "2041-2070", "2071-2100",
    ]


def test_a_period_nothing_was_measured_for_reports_no_median(client, frozen_context):
    """A period whose files covered none of these regions is "not measured", and
    a median of nothing must arrive as null rather than as NaN or 0.0 - the
    second reads as "no change", which is a finding nobody made."""
    table = _context_table()
    for column in ("median", "min", "max"):
        table[f"change_pct_ensemble_{column}_2071_2100"] = None
    table["ensemble_members_2071_2100"] = [0, 0, 0]
    frozen_context(table)
    periods = {
        p["period"]: p
        for p in TestClient(app).get("/api/context").json()["climate_periods"]
    }
    assert periods["2071-2100"]["median_change_pct"] is None
    assert periods["2071-2100"]["regions_measured"] == 0


def test_context_columns_never_become_vulnerability_indicators(client, frozen_context):
    """The trap this table exists to stay out of.

    The index is a weighted mean of min-max scaled numeric columns, picked by
    scanning the frame. Joining the context columns onto the exposure table would
    have made "this region's rivers rise faster" a term in a vulnerability score
    - and `shared_basin_share` a term in one too. So the two tables are loaded
    separately and never merged server-side, and this pins it.
    """
    body = client.get("/api/meta").json()
    assert body["indicators"] == ["exposed_pop", "share_over_65"]
    for leaked in (
        "change_pct_ensemble_median_2071_2100",
        "built_share_exposed_rp100",
        "shared_basin_share",
    ):
        assert leaked not in body["indicators"]


def test_the_built_up_return_period_travels_with_the_figure(client, frozen_context):
    """The built-up columns are measured at one return period, named in the
    column. Served without it the surface invites being read against a different
    scenario's headcount."""
    assert client.get("/api/context").json()["built_up_return_period"] == 100


def test_no_context_is_a_404_that_names_its_builder(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "CONTEXT", tmp_path / "absent.parquet")
    response = TestClient(app).get("/api/context")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "scripts/build_context.py" in detail
    assert "src.fetch" in detail, "the script needs inputs that are not committed"


def test_meta_says_whether_the_context_table_is_there(client, frozen_context, tmp_path, monkeypatch):
    """Like `has_geometry`: the UI has to be able to hide a panel it cannot fill
    rather than render an error into the page."""
    assert client.get("/api/meta").json()["has_context"] is True
    monkeypatch.setattr(api, "CONTEXT", tmp_path / "absent.parquet")
    assert TestClient(app).get("/api/meta").json()["has_context"] is False


def test_the_react_context_panel_cannot_render_a_direction_from_one_chain():
    """A source check, like the one on the language list: CI runs pytest only.

    The one thing worth pinning about this panel is the thing a reader would be
    misled by. A period with one model chain reports zero regions agreeing on the
    sign, and that zero reads as "the models conflict" unless the panel says it
    is "nothing was compared". So the panel must branch on `single_member`, and
    the ranking must sit on the other side of that branch - a table rendered
    regardless would show per-region medians under a heading about agreement.

    It also must not restate the period arithmetic: `climate_periods` on the
    server decides what a period is allowed to claim, and a second computation in
    the client is how the two UIs end up caveating one file differently.
    """
    panel = (ROOT / "web" / "src" / "components" / "ContextPanel.jsx").read_text(
        encoding="utf-8"
    )
    assert "getContext" in panel
    assert "single_member" in panel, "the one-chain branch is the point of the panel"
    assert "!summary.single_member" in panel, (
        "the ranking must be behind the branch, not beside it"
    )
    # The missing member is named, because adding it is the action.
    assert "VIC-WUR-EUR-11" in panel
    # The period summary comes from the server, not from column-name arithmetic.
    assert "ensemble_members_" not in panel

    # `shared_with` arrives as an array of country codes, and JSX renders an
    # array by concatenating its items with nothing between them: four countries
    # printed as `DEFRLUNL`, which is neither one country nor four. Measured on
    # the real table on 7 October, before the join was added.
    assert "join(" in panel, "the country list must be joined, not concatenated"

    # The APSFR block must branch on coverage, never rank a null as a zero: the
    # layer carries 26 country codes across both reporting cycles and Ireland is
    # not one of them, so "no declared area" has a cause that is not about the
    # State. Pinned here because CI runs pytest only.
    assert "apsfr_country_reported" in panel
    # The table lists the UNDECLARED regions. Ranking by share descending fills
    # it with regions a State covered entirely, which is the opposite of what the
    # section asks.
    assert "undeclared.slice(0, 15)" in panel, (
        "the table must show the gap, not the best-covered regions"
    )
    assert "apsfr_share != null" in panel, (
        "an uncovered country has no share; filtering on it is what stops a null "
        "being ranked as a measured zero"
    )


def test_the_react_app_offers_the_context_tab_next_to_the_figure_it_qualifies():
    """Ordered, not just present: a climate caveat met after the brief is written
    is a caveat that changed nothing."""
    source = (ROOT / "web" / "src" / "EuropeView.jsx").read_text(encoding="utf-8")
    assert "ContextPanel" in source
    tabs = source.split("const TABS = [", 1)[1].split("]", 1)[0]
    names = [part.strip().strip('"') for part in tabs.split(",")]
    assert names[:2] == ["Exposure", "Context"]


# --- units in column names, and tables frozen before the rename -------------------

def _with_poverty(name: str) -> pd.DataFrame:
    table = _nested_table()
    table[name] = [14.6, 22.0, 9.1] * 3
    table[f"{name}_year"] = ["2024"] * 9
    return table


def test_a_legacy_table_offers_the_same_indicators_under_the_current_name(frozen):
    """The rename may change a name and nothing else: same columns selected, same
    order, the percentage now saying so."""
    frozen(_with_poverty("poverty_rate"))
    legacy = TestClient(app).get("/api/meta").json()["indicators"]
    frozen(_with_poverty("poverty_rate_pct"))
    current = TestClient(app).get("/api/meta").json()["indicators"]
    assert legacy == current == ["exposed_pop", "share_over_65", "poverty_rate_pct"]


@pytest.mark.parametrize("table_name", ["poverty_rate", "poverty_rate_pct"])
@pytest.mark.parametrize("asked", ["poverty_rate", "poverty_rate_pct"])
def test_the_ranking_is_identical_whichever_name_is_stored_or_asked(frozen, table_name, asked):
    frozen(_with_poverty("poverty_rate_pct"))
    reference = TestClient(app).post(
        "/api/vulnerability", json={"indicators": ["exposed_pop", "poverty_rate_pct"]}).json()
    frozen(_with_poverty(table_name))
    body = TestClient(app).post(
        "/api/vulnerability", json={"indicators": ["exposed_pop", asked]}).json()
    assert body["rows"] == reference["rows"]
    if asked == "poverty_rate":
        assert body["renamed"] == {"poverty_rate": "poverty_rate_pct"}
    else:
        assert "renamed" not in body


def test_exposure_rows_carry_the_current_name_for_a_legacy_table(frozen):
    frozen(_with_poverty("poverty_rate"))
    row = TestClient(app).get("/api/exposure").json()["rows"][0]
    assert row["poverty_rate_pct"] == 14.6 and "poverty_rate" not in row


# --- verification travels with the draft and binds the approval -----------------

def test_the_draft_names_its_unsourced_numbers_and_uncited_sentences(client, monkeypatch):
    """Grounding and the citation range check form: "Article 14" for "Article 7"
    and a claim with no marker both passed them. The draft response now names
    each, and carries the table text an approval re-checks against."""
    _stub_model(monkeypatch, reply=(
        "Flood risk management plans cover 97% of basins [S1]. "
        "Every region must publish flood risk management plans."))
    body = client.post("/api/draft", json={"question": "flood risk plans?"}).json()
    assert body["unsupported_numbers"] == ["97"]
    assert body["uncited_sentences"] == ["Every region must publish flood risk management plans."]
    assert body["invalid_citations"] == []
    assert "TABLE NOTE" in body["table_text"] and "exposure[" in body["table_text"]


def test_the_draft_counts_a_table_figure_as_sourced(client, monkeypatch):
    """The period is in the table note the model was handed, so quoting it is
    not an invented figure."""
    _stub_model(monkeypatch, reply="Flood risk management plans at the 1-in-100 year period [S1].")
    body = client.post("/api/draft", json={"question": "flood risk plans?",
                                           "return_period": 100}).json()
    assert body["unsupported_numbers"] == []


def test_approve_refuses_a_marker_no_draft_can_have(tmp_path, monkeypatch, client):
    """Approve wrote "Invented claim [S9]." into the brief: it never looked at the
    text. No draft is given more than MAX_PASSAGES sources, so [S9] cites nothing
    whatever the sources were."""
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    response = client.post("/api/approve", json={"text": "Invented claim [S9]."})
    assert response.status_code == 422
    assert "[S9]" in response.json()["detail"]
    assert not (tmp_path / "approved.md").exists()


def test_approve_checks_the_markers_against_the_sources_sent(tmp_path, monkeypatch, client):
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    passages = [{"text": "Flood risk management plans.", "source": "dir.html"}]
    response = client.post("/api/approve", json={
        "text": "Plans matter [S2].", "passages": passages})
    assert response.status_code == 422
    assert "1 passages were supplied" in response.json()["detail"]
    assert not (tmp_path / "approved.md").exists()


def test_approve_records_an_unsourced_number_and_still_writes(tmp_path, monkeypatch, client):
    """A figure no source holds can be a human's correct edit, so it is written
    beside the text in the record and returned, not refused."""
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    passages = [{"text": "Flood risk management plans.", "source": "dir.html"}]
    response = client.post("/api/approve", json={
        "text": "Flood risk management plans cover 4,812,000 residents [S1].",
        "passages": passages, "table_text": "exposure[1]{a}:\n  26000"})
    assert response.status_code == 200
    check = response.json()["verification"]
    assert check["unsupported_numbers"] == ["4,812,000"] and check["invalid_citations"] == []
    written = (tmp_path / "approved.md").read_text(encoding="utf-8")
    assert "unsupported numbers 4,812,000" in written
    assert "4,812,000 residents [S1]." in written


def test_approve_without_sources_says_what_it_could_not_check(tmp_path, monkeypatch, client):
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    response = client.post("/api/approve", json={"text": "Plans matter [S1]."})
    assert response.status_code == 200
    assert response.json()["verification"]["unsupported_numbers"] is None
    assert "sources not supplied" in (tmp_path / "approved.md").read_text(encoding="utf-8")


def test_the_europe_view_opens_on_the_1_in_100_year_flood():
    """The brief and the pitch quote RP100; the React view must open there too,
    falling back to the rarest period only when the table has no RP100."""
    source = (ROOT / "web" / "src" / "EuropeView.jsx").read_text(encoding="utf-8")
    assert "export const DEFAULT_RETURN_PERIOD = 100;" in source
    assert "setReturnPeriod(defaultReturnPeriod(m.return_periods))" in source
    assert "return periods.at(-1) ?? null;" in source


def _two_scope_table() -> pd.DataFrame:
    """Two Belgian regions and one Serbian one, at RP100: EU-27 and not."""
    return pd.DataFrame({
        "nuts_id": ["BE31", "BE32", "RS110"],
        "country": ["BE", "BE", "RS"],
        "exposed_pop": [3000.0, 400.0, 5000.0],
        "total_pop": [100_000.0, 50_000.0, 40_000.0],
        "share_over_65": [0.90, 0.50, 0.55],
        "return_period": [100] * 3,
        "annual_probability": [0.01] * 3,
    })


def test_exposure_rows_say_whether_they_are_eu27(frozen):
    frozen(_two_scope_table())
    body = TestClient(app).get("/api/exposure?return_period=100").json()
    assert {r["nuts_id"]: r["eu27"] for r in body["rows"]} == {
        "BE31": True, "BE32": True, "RS110": False}
    # The server total stays the whole table; the UIs narrow it.
    assert body["total_exposed"] == 8400.0


def test_the_eu27_flag_is_never_offered_as_an_indicator(frozen):
    frozen(_two_scope_table())
    assert "eu27" not in TestClient(app).get("/api/meta").json()["indicators"]


def test_the_europe_view_opens_on_the_eu27():
    """The brief's 25.7 million is the EU-27 part of the 37-country total, so
    the view opens on the EU-27, offers the rest, and draws only what it counts."""
    source = (ROOT / "web" / "src" / "EuropeView.jsx").read_text(encoding="utf-8")
    assert 'useState("EU-27")' in source
    assert "geojson={shown}" in source
    assert "rows={ranked}" in source and "[...rows]" in source


def test_the_europe_view_picks_the_return_period_on_a_bar():
    """A bar from 10 to 500 years, one notch per period in the table, so the
    nesting reads left to right; it still opens on the 1-in-100 flood."""
    source = (ROOT / "web" / "src" / "EuropeView.jsx").read_text(encoding="utf-8")
    assert 'type="range"' in source and 'aria-label="Return period"' in source
    assert "max={meta.return_periods.length - 1}" in source
    assert "meta.return_periods.indexOf(returnPeriod)" in source
