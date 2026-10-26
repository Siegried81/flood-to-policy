"""Tests for the Risk Data Hub client. No network: every HTTP call is mocked.

The guarantees worth testing here are the ones that fail *silently* against this
particular API, because those are the ones that put a wrong number in a policy
brief instead of raising:

- a bot-defence challenge page arriving under HTTP 200, which a client that
  trusts the status code parses as data;
- a server default page size of 10, which truncates a 1,297-row result set
  without any signal that it did;
- a missing token reading as "no recorded losses" rather than "nobody logged in".

The paging and nesting numbers in the assertions are shaped after a real
response: `/losses/losses/items` for Belgium returns rows at Country, NUTS1,
NUTS2 and NUTS3 for the same event, so row counts here deliberately exceed one
page.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src import rdh as R


class _Response:
    """Minimal stand-in for requests.Response.

    `content` is padded past `fetch.MIN_DOCUMENT_BYTES` so that a test about
    paging or filtering does not accidentally trip the short-body floor that
    `_why_not_a_document` applies.
    """

    def __init__(self, payload=None, status=200, content=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"features": []}
        self._content = content if content is not None else json.dumps(
            {**self._payload, "_pad": "x" * 2_500}
        ).encode()

    @property
    def content(self) -> bytes:
        return self._content

    def json(self):
        return self._payload


def _page(n: int, matched: int, start: int = 0) -> dict:
    """One OGC API - Features page of `n` features out of `matched` total."""
    return {
        "numberMatched": matched,
        "features": [
            {"properties": {"admin_unit_code": f"BE{start + i:03d}"}} for i in range(n)
        ],
    }


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A fresh cache directory and no inherited token.

    `src/__init__.py` loads the real `.env`, so a developer with a live
    RDH_BEARER_TOKEN would otherwise see the no-token test pass for the wrong
    reason.
    """
    monkeypatch.setattr(R, "CACHE_DIR", tmp_path / "rdh_cache")
    monkeypatch.delenv("RDH_BEARER_TOKEN", raising=False)
    return tmp_path


def test_no_token_raises_and_names_the_recovery_step(isolated):
    """A missing token must not read as an empty result set: a brief that says
    'no recorded losses' because nobody logged in is worse than no brief."""
    with pytest.raises(R.RdhUnavailable, match="EU Login"):
        R.items("losses")


def test_token_argument_wins_over_a_missing_environment(isolated):
    """The token expires every 10 hours, so passing it per call has to work."""
    with patch.object(R.requests, "get", return_value=_Response(_page(1, 1))) as get:
        R.items("hazard", token="explicit-token")
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer explicit-token"


def test_bot_defence_page_under_http_200_is_rejected(isolated):
    """The real failure mode of this host, measured 2026-10-06: an unauthenticated
    call returns an F5/Shape JavaScript challenge with status 200, not a 401."""
    challenge = b'<html><script>window["bobcmn"] = "1011"</script>' + b"x" * 3_000
    with patch.object(R.requests, "get", return_value=_Response(content=challenge)):
        with pytest.raises(R.RdhUnavailable, match="WAF|bot-defence"):
            R.items("hazard", token="t")


def test_paging_follows_number_matched(isolated):
    """The silent truncation this loop exists to prevent."""
    pages = [_Response(_page(2, matched=3)), _Response(_page(1, matched=3, start=2))]
    with patch.object(R.requests, "get", side_effect=pages) as get:
        rows = R.items("division", token="t")
    assert len(rows) == 3
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["params"]["offset"] == 2


def test_an_explicit_limit_is_always_sent(isolated):
    """Never rely on the server default, which is 10 rows."""
    with patch.object(R.requests, "get", return_value=_Response(_page(1, 1))) as get:
        R.items("metric", token="t")
    assert get.call_args.kwargs["params"]["limit"] == R.PAGE_LIMIT


def test_an_empty_page_stops_the_loop(isolated):
    """A server whose numberMatched disagrees with what it returns must not spin."""
    pages = [_Response(_page(1, matched=99)), _Response(_page(0, matched=99))]
    with patch.object(R.requests, "get", side_effect=pages) as get:
        rows = R.items("hazard", token="t")
    assert len(rows) == 1
    assert get.call_count == 2


def test_second_call_is_served_from_disk(isolated):
    """Caching is the rule for every remote source in this kit: the demo must not
    depend on a reachable Commission server."""
    with patch.object(R.requests, "get", return_value=_Response(_page(1, 1))) as get:
        first = R.items("hazard", token="t")
        second = R.items("hazard", token="t")
    assert first == second
    assert get.call_count == 1


def test_different_parameters_do_not_share_a_cache_entry(isolated):
    """Belgian losses and Italian losses are not the same answer."""
    with patch.object(R.requests, "get", return_value=_Response(_page(1, 1))) as get:
        R.flood_losses(token="t", country="BE")
        R.flood_losses(token="t", country="IT")
    assert get.call_count == 2


def test_http_error_names_the_expired_token(isolated):
    with patch.object(R.requests, "get", return_value=_Response(status=401)):
        with pytest.raises(R.RdhUnavailable, match="token expired"):
            R.items("losses", token="t")


def test_a_transport_failure_is_reported_not_swallowed(isolated):
    with patch.object(R.requests, "get", side_effect=OSError("connection reset")):
        with pytest.raises(R.RdhUnavailable, match="connection reset"):
            R.items("losses", token="t")


def test_unknown_collection_is_refused_before_any_request(isolated):
    with patch.object(R.requests, "get") as get:
        with pytest.raises(R.RdhUnavailable, match="unknown collection"):
            R.items("rainfall", token="t")
    assert get.call_count == 0


def test_base_url_comes_from_sources_yaml():
    """config/sources.yaml owns every URL in this repo, including this one."""
    assert R.base_url().startswith("https://drmkc.jrc.ec.europa.eu/")


def _mixed_hazards_page() -> dict:
    """One page shaped like the real response: the hazard parameter is ignored,
    so a request for floods comes back carrying storms and earthquakes too."""
    rows = [
        {"admin_unit_code": "BE332", "hazard_type": "Flood", "hazard": "nat-hyd-flo-riv",
         "metric": "casualty_count", "value_event_src_average": 10.0},
        {"admin_unit_code": "BE332", "hazard_type": "Flood", "hazard": "nat-hyd-flo-fla",
         "metric": "casualty_count", "value_event_src_average": 5.0},
        {"admin_unit_code": "BE332", "hazard_type": "Storm", "hazard": "nat-met-sto-sto",
         "metric": "casualty_count", "value_event_src_average": 7.0},
        {"admin_unit_code": "BE332", "hazard_type": "Earthquake", "hazard": "nat-geo-ear-gro",
         "metric": "casualty_count", "value_event_src_average": 3.0},
    ]
    return {"numberMatched": len(rows),
            "features": [{"properties": r} for r in rows]}


def test_non_flood_hazards_are_dropped_from_a_flood_query(isolated):
    """The server accepts admin_hazard_type and ignores it - measured 2026-10-06,
    1,297 rows for Belgium of which 413 were storms, 63 heatwaves and 28
    earthquakes. Totalling that as flood losses is a wrong number that looks
    right, so the filter has to be applied to the rows."""
    with patch.object(R.requests, "get", return_value=_Response(_mixed_hazards_page())):
        rows = R.flood_losses(token="t", country="BE")
    assert len(rows) == 2
    assert {r["hazard_type"] for r in rows} == {"Flood"}
    assert sum(r["value_event_src_average"] for r in rows) == 15.0


def test_the_ignored_hazard_parameter_is_not_sent(isolated):
    """Sending a parameter the server ignores would only fragment the on-disk
    cache into one file per subset of one unfiltered answer."""
    with patch.object(R.requests, "get", return_value=_Response(_mixed_hazards_page())) as get:
        R.flood_losses(token="t", country="BE")
    params = get.call_args.kwargs["params"]
    assert "admin_hazard_type" not in params
    assert "hazard" not in params
    assert params["admin_unit_country_code"] == "BE"


def test_caller_can_narrow_to_river_flooding(isolated):
    """Riverine is the only subtype the JRC hazard rasters model, so the honest
    validation uses that code rather than every flood. Confirmed present in the
    live /admin/hazard/items response as nat-hyd-flo-riv."""
    with patch.object(R.requests, "get", return_value=_Response(_mixed_hazards_page())) as get:
        rows = R.flood_losses(token="t", hazard="nat-hyd-flo-riv")
    assert [r["hazard"] for r in rows] == ["nat-hyd-flo-riv"]
    assert "hazard" not in get.call_args.kwargs["params"]


def test_vulnerability_pins_the_year(isolated):
    """RDH publishes the index per unit AND per year; an unpinned year averages
    across a decade by accident."""
    with patch.object(R.requests, "get", return_value=_Response(_page(1, 1))) as get:
        R.vulnerability(token="t", year=2020)
    assert get.call_args.kwargs["params"]["vulnerability_year"] == 2020
