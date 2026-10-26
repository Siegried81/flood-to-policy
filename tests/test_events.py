"""Tests for the reported-events layer. Offline: every HTTP call is mocked.

What is pinned here is the discipline, not the counting. The counting is a biased
proxy and everyone knows it; the failure that would actually damage the brief is
an unavailable signal quietly reading as a zero, or a caveat getting lost between
the module and a slide.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src import events as E


@pytest.fixture(autouse=True)
def fast_and_isolated(tmp_path, monkeypatch):
    """No real sleeping and no shared cache between tests.

    The 5-second GDELT spacing is correct in production and pure waste in a test
    suite; and a cache written by one test would silently satisfy the next, so
    each test gets its own file.
    """
    monkeypatch.setattr(E, "GDELT_MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(E, "_last_gdelt_call", 0.0)
    monkeypatch.setattr(E, "CACHE", tmp_path / "events_cache.json")


class _Response:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_unavailable_is_not_zero(monkeypatch):
    """'We did not look' and 'we looked and found nothing' are different
    statements. Collapsing them turns an absence of data into a claim of absence,
    which is the one thing this module must never do."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    with patch.object(E.requests, "get", side_effect=RuntimeError("no network")):
        signal = E.coverage("Liege")
    assert signal.available is False
    assert signal.articles == 0  # the value is 0, but `available` says not to use it


def test_providers_are_maxed_not_summed(monkeypatch):
    """GDELT and NewsAPI cover the same events, so adding them double counts one
    flood. The larger of two biased counts is still one count."""
    monkeypatch.setenv("NEWSAPI_KEY", "test-key")
    responses = [
        _Response({"articles": [{}] * 12}),       # gdelt
        _Response({"totalResults": 30}),          # newsapi
    ]
    with patch.object(E.requests, "get", side_effect=responses):
        signal = E.coverage("Verviers")
    assert signal.articles == 30
    assert set(signal.sources) == {"gdelt", "newsapi"}


def test_missing_key_does_not_disable_the_whole_signal(monkeypatch):
    """GDELT needs no key, so the check still works with nothing configured -
    which is what makes it preparable before the event and runnable offline."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    with patch.object(E.requests, "get", return_value=_Response({"articles": [{}] * 5})):
        signal = E.coverage("Rochefort")
    assert signal.available and signal.articles == 5
    assert signal.sources == ("gdelt",)


def test_html_answered_with_http_200_is_not_a_count():
    """GDELT answers a malformed query with HTML under HTTP 200, so decoding the
    JSON is the real validity check - the same trap the collection layer hit."""
    with patch.object(E.requests, "get", return_value=_Response(ValueError("not json"))):
        assert E._gdelt_count("Nowhere", 30, ("en",)) is None


def test_blind_spots_only_looks_at_the_bottom_of_the_ranking(monkeypatch):
    """The question is "where does the model say little and the world says
    something", so the top of the ranking is not interesting here."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    ranked = [{"nuts_id": f"R{i}", "exposed_pop": 100 - i} for i in range(10)]
    with patch.object(E, "coverage", lambda place, **kw: E.EventSignal(place, 7, 365, ("gdelt",))):
        found = E.blind_spots(ranked, "nuts_id", bottom_share=0.5)
    assert [r["nuts_id"] for r in found] == [f"R{i}" for i in range(5, 10)]
    assert all(r["model_rank"] > 5 for r in found)


def test_every_blind_spot_carries_its_caveat(monkeypatch):
    """The caveat travels inside the payload so it cannot be dropped between the
    module and a slide."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    ranked = [{"nuts_id": "A", "exposed_pop": 10}, {"nuts_id": "B", "exposed_pop": 1}]
    with patch.object(E, "coverage", lambda place, **kw: E.EventSignal(place, 3, 365, ("gdelt",))):
        found = E.blind_spots(ranked, "nuts_id", bottom_share=0.5)
    assert found and all("not incidence" in r["caveat"] for r in found)


def test_unavailable_regions_are_not_reported_as_blind_spots(monkeypatch):
    """A region we could not check is not a region the model missed."""
    ranked = [{"nuts_id": "A", "exposed_pop": 10}, {"nuts_id": "B", "exposed_pop": 1}]
    with patch.object(E, "coverage", lambda place, **kw: E.EventSignal.unavailable(place, 365)):
        assert E.blind_spots(ranked, "nuts_id", bottom_share=1.0) == []


def test_a_second_lookup_comes_from_the_cache(monkeypatch):
    """GDELT rate-limits hard enough that a live call cannot be relied on, so the
    answer is persisted and the second lookup must not touch the network."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    with patch.object(E.requests, "get", return_value=_Response({"articles": [{}] * 9})) as get:
        first = E.coverage("Namur")
        second = E.coverage("Namur")
    assert get.call_count == 1
    assert first.articles == second.articles == 9


def test_an_unavailable_answer_is_not_cached(monkeypatch):
    """Caching a transient rate limit would freeze it into a permanent gap."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    with patch.object(E.requests, "get", side_effect=RuntimeError("429")):
        assert E.coverage("Dinant").available is False
    with patch.object(E.requests, "get", return_value=_Response({"articles": [{}] * 4})):
        assert E.coverage("Dinant").articles == 4  # retried, not served from cache


def test_a_saturated_count_is_flagged_as_censored(monkeypatch):
    """A count equal to the provider cap is a lower bound. Two saturated places
    are not comparable, and a brief ranking them would be ranking the cap."""
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    full = _Response({"articles": [{}] * E.GDELT_MAX_RECORDS})
    with patch.object(E.requests, "get", return_value=full):
        assert E.coverage("Emilia-Romagna").censored is True


def test_a_sweep_over_every_region_is_refused(monkeypatch):
    """At 5 s per place, all ~1,166 NUTS3 regions would take over an hour. The cap
    makes that a loud failure rather than a silent afternoon."""
    ranked = [{"nuts_id": f"R{i}", "exposed_pop": 1} for i in range(200)]
    with pytest.raises(ValueError, match="Shortlist first"):
        E.blind_spots(ranked, "nuts_id", bottom_share=1.0)
