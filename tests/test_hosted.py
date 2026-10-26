"""Tests for the hosted-demo switch and the July 2021 route of the API.

A public demo must not spend a model quota per visitor nor write to the brief,
so with `HOSTED=1` every route that would do either answers 403 before any
provider is touched. The tests make each provider entry point raise if called,
so "403" and "never reached the model" are checked together. Unset, the
routes behave as before. No network: nothing here reaches a provider.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as api
from api.main import app


def _boom(*args, **kwargs):
    raise AssertionError("a provider was called in the hosted demo")


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """A client on a tiny frozen table, with every model entry point booby-trapped."""
    path = tmp_path / "exposure.parquet"
    pd.DataFrame({"nuts_id": ["BE31", "BE32"], "exposed_pop": [10.0, 20.0],
                  "total_pop": [100.0, 200.0], "return_period": [100, 100]}).to_parquet(path)
    monkeypatch.setattr(api, "EXPOSURE", path)
    monkeypatch.setattr(api, "APPROVED", tmp_path / "approved.md")
    monkeypatch.setattr(api.rag, "complete", _boom)
    monkeypatch.setattr(api.rag, "search", _boom)
    monkeypatch.setattr(api.translate, "translate", _boom)
    monkeypatch.setattr(api.nlquery, "ask", _boom)
    monkeypatch.delenv("FLOOD_APPROVE_TOKEN", raising=False)
    return TestClient(app)


MODEL_CALLS = [
    ("/api/draft", {"question": "Who is most exposed?"}),
    ("/api/translate", {"text": "Hello [S1].", "language": "fr"}),
    ("/api/ask", {"question": "Top regions?"}),
    ("/api/approve", {"text": "Approved text."}),
]


@pytest.mark.parametrize("route,body", MODEL_CALLS)
def test_hosted_refuses_every_model_or_write_route(client, monkeypatch, route, body):
    monkeypatch.setenv("HOSTED", "1")
    r = client.post(route, json=body)
    assert r.status_code == 403
    assert "disabled in the hosted demo" in r.json()["detail"]


def test_hosted_approve_writes_nothing(client, monkeypatch):
    monkeypatch.setenv("HOSTED", "1")
    client.post("/api/approve", json={"text": "Approved text."})
    assert not api.APPROVED.exists()


def test_hosted_still_answers_a_spec_without_a_model(client, monkeypatch):
    monkeypatch.setenv("HOSTED", "1")
    r = client.post("/api/ask", json={"spec": {"columns": ["nuts_id", "exposed_pop"],
                                               "return_period": 100, "limit": 5}})
    assert r.status_code == 200


def test_unset_keeps_the_local_behaviour(client, monkeypatch):
    monkeypatch.delenv("HOSTED", raising=False)
    r = client.post("/api/approve", json={"text": "Approved text."})
    assert r.status_code == 200
    assert api.APPROVED.exists()
    with pytest.raises(AssertionError, match="provider was called"):
        client.post("/api/draft", json={"question": "Who is most exposed?"})


@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("", False), ("0", False)])
def test_config_reports_the_mode(client, monkeypatch, value, expected):
    monkeypatch.setenv("HOSTED", value)
    body = client.get("/api/config").json()
    assert body["hosted"] is expected
    assert body["llm_enabled"] is (not expected)
    assert body["approve_enabled"] is (not expected)


def test_event2021_serves_the_file_as_is(client, tmp_path, monkeypatch):
    path = tmp_path / "event_2021_web.json"
    payload = {"schema": 1, "hero": [], "places": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(api, "EVENT_WEB", path)
    monkeypatch.setattr(api, "EVENT_WEB_FULL", tmp_path / "absent.full.json")
    r = client.get("/api/event2021")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == payload
    assert client.get("/api/config").json()["event2021_available"] is True


def test_event2021_missing_is_a_404_that_names_the_builder(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "EVENT_WEB", tmp_path / "absent.json")
    monkeypatch.setattr(api, "EVENT_WEB_FULL", tmp_path / "absent.full.json")
    r = client.get("/api/event2021")
    assert r.status_code == 404
    assert "missing" in r.json()["detail"]
    assert "export_event_web.py" in r.json()["detail"]


def test_event2021_is_served_in_the_hosted_demo(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HOSTED", "1")
    path = tmp_path / "event_2021_web.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(api, "EVENT_WEB", path)
    assert client.get("/api/event2021").status_code == 200


def _two_builds(tmp_path, monkeypatch):
    public, full = tmp_path / "event_2021_web.json", tmp_path / "event_2021_web.full.json"
    public.write_text('{"build": "public"}', encoding="utf-8")
    full.write_text('{"build": "full"}', encoding="utf-8")
    monkeypatch.setattr(api, "EVENT_WEB", public)
    monkeypatch.setattr(api, "EVENT_WEB_FULL", full)


def test_event2021_prefers_the_local_full_build(client, tmp_path, monkeypatch):
    monkeypatch.delenv("HOSTED", raising=False)
    _two_builds(tmp_path, monkeypatch)
    assert client.get("/api/event2021").json() == {"build": "full"}


def test_event2021_hosted_never_serves_the_full_build(client, tmp_path, monkeypatch):
    monkeypatch.setenv("HOSTED", "1")
    _two_builds(tmp_path, monkeypatch)
    assert client.get("/api/event2021").json() == {"build": "public"}
