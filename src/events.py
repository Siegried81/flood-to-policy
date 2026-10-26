"""Reported flood events, used to probe the hazard model's blind spots.

**This is a validation layer, never evidence.** Nothing here may enter the
ranking, the vulnerability index or a headline figure. News coverage is not flood
incidence: it is biased by media attention, country, language, population size
and how newsworthy a place is. A region with twice the coverage did not have
twice the flooding, and treating counts as risk is exactly the "context standing
as evidence" error this project is supposed to avoid.

**What it is for.** The JRC hazard maps have two documented blind spots: they
model river flooding only, so surface runoff - a large part of what destroyed the
Vesdre valley in 2021 - is absent, and they cover basins above 150 km2 only. So
when reported flooding lands in a region the model ranks low, that disagreement
is a methods result worth putting in the brief: *our hazard layer misses X, and
here is where that showed.* That is a finding about the model, not about the
region.

**Why GDELT first.** It needs no key, covers European languages, and reaches back
years. NewsAPI supplements it when `NEWSAPI_KEY` is set, but its free tier only
reaches back about a month and is English-biased - fine as a recency top-up,
useless as the backbone. With neither available the signal degrades to
"unavailable" rather than inventing a number, the same way
`ing-usecase/reputation.py` handles a missing key.

**NEVER CALL THIS LIVE IN FRONT OF A JURY.** GDELT asks for one request every five
seconds, and its rate limiting is per-IP and *sustained*: once tripped, it kept
returning HTTP 429 for well over a minute of complete silence, with the limit
explained in a plain-text body under a 429 status. Measured here, repeatedly. So
`coverage()` writes every answer to `data/processed/events_cache.json` and reads
it back on the next call. Run this once, days before the event, and demo from the
cache - which is the same rule the rest of the kit already follows for rasters.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from src.data_io import DATA

CACHE = DATA / "processed" / "events_cache.json"

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_URL = "https://newsapi.org/v2/everything"
TIMEOUT_S = 30
# GDELT's published limit: one request every 5 seconds. Firing them back to back
# gets HTTP 429 on every call, with the limit explained in a plain-text body - so
# the module reports "unavailable" everywhere and looks like a network problem.
# Measured the hard way; the throttle is not optional.
GDELT_MIN_INTERVAL_S = 5.0
# At 5 s per place, checking all ~1,166 NUTS3 regions would take over an hour.
# This check is for a shortlist - the tail of a ranking you already have - not a
# sweep. The cap makes that a loud failure rather than a silent afternoon.
MAX_PLACES = 40
# Provider record cap. A count equal to it is censored, not measured.
GDELT_MAX_RECORDS = 250

_last_gdelt_call = 0.0
_gdelt_lock = threading.Lock()

# Flood vocabulary in the languages of the countries most of the corpus covers.
# Kept explicit rather than translated at runtime: a mistranslation here would
# silently change what is being counted, and the list is short enough to review.
FLOOD_TERMS = {
    "en": ["flood", "flooding", "inundation"],
    "fr": ["inondation", "crue", "submersion"],
    "nl": ["overstroming", "wateroverlast"],
    "de": ["hochwasser", "überschwemmung"],
    "it": ["alluvione", "inondazione"],
    "es": ["inundación", "riada"],
}


@dataclass(frozen=True)
class EventSignal:
    """Reported-coverage count for one place over one window. Not a risk measure."""

    place: str
    articles: int
    window_days: int
    sources: tuple[str, ...]
    available: bool = True
    # True when the count hit the provider's record cap, so it is a lower bound
    # rather than a measurement. Two saturated places are not comparable, and a
    # brief that ranks them would be ranking the cap.
    censored: bool = False

    @classmethod
    def unavailable(cls, place: str, window_days: int) -> "EventSignal":
        """No provider reachable. Explicitly not zero: 'we did not look' and
        'we looked and found nothing' are different statements, and collapsing
        them is how an absence of data becomes a claim of absence."""
        return cls(place, 0, window_days, (), available=False)


def _wait_for_gdelt() -> None:
    """Hold the 5-second spacing GDELT asks for, across threads."""
    global _last_gdelt_call
    with _gdelt_lock:
        wait = GDELT_MIN_INTERVAL_S - (time.monotonic() - _last_gdelt_call)
        # Reserve the slot before sleeping, so a second thread queues behind this
        # call rather than racing it to the same instant.
        _last_gdelt_call = time.monotonic() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)


def _gdelt_count(place: str, days: int, languages: tuple[str, ...]) -> int | None:
    """Articles mentioning flooding alongside `place`, or None if unreachable."""
    terms = " OR ".join(t for lang in languages for t in FLOOD_TERMS.get(lang, []))
    query = f'({terms}) "{place}"'
    _wait_for_gdelt()
    try:
        response = requests.get(
            GDELT_DOC_URL,
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": GDELT_MAX_RECORDS,
                "format": "json",
                "timespan": f"{days}d",
            },
            headers={"User-Agent": "flood-policy-kit/0.1 (student project)"},
            timeout=TIMEOUT_S,
        )
        if response.status_code == 429:
            # Rate limited, not broken. Distinguished because the fix is to wait,
            # not to drop the source - and because a silent None here reads as
            # "no provider reachable" across every place at once.
            return None
        response.raise_for_status()
        # GDELT answers a malformed query with HTML and HTTP 200, so the JSON
        # decode is the real validity check rather than the status code.
        articles = response.json().get("articles", [])
        return len(articles)
    except Exception:
        return None


def _newsapi_count(place: str, days: int) -> int | None:
    """Recency top-up. Returns None when no key is set - never 0, see above."""
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        return None
    since = (datetime.now(timezone.utc) - timedelta(days=min(days, 28))).date().isoformat()
    try:
        response = requests.get(
            NEWSAPI_URL,
            params={
                "q": f'({" OR ".join(FLOOD_TERMS["en"])}) AND "{place}"',
                "from": since,
                "pageSize": 100,
            },
            headers={"X-Api-Key": key},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        return int(response.json().get("totalResults", 0))
    except Exception:
        return None


def _cache_read() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _cache_write(key: str, signal: "EventSignal") -> None:
    """Persist one answer. Only successful lookups are cached: caching an
    'unavailable' would freeze a transient rate limit into a permanent gap."""
    if not signal.available:
        return
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    data = _cache_read()
    data[key] = asdict(signal)
    CACHE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def coverage(place: str, days: int = 365,
             languages: tuple[str, ...] = ("en", "fr", "nl", "de"),
             use_cache: bool = True) -> EventSignal:
    """How much flood coverage one place attracted. A proxy with known bias.

    Cached to disk, because GDELT's rate limiting makes a live call unreliable
    (see the module docstring). Prepare the cache before the event.
    """
    key = f"{place}|{days}|{','.join(languages)}"
    if use_cache:
        cached = _cache_read().get(key)
        if cached:
            return EventSignal(**cached)

    counts, sources = [], []
    gdelt = _gdelt_count(place, days, languages)
    if gdelt is not None:
        counts.append(gdelt)
        sources.append("gdelt")
    newsapi = _newsapi_count(place, days)
    if newsapi is not None:
        counts.append(newsapi)
        sources.append("newsapi")
    if not counts:
        return EventSignal.unavailable(place, days)

    # max, not sum: the providers overlap heavily, and adding them would double
    # count the same event. The larger of two biased counts is still one count.
    signal = EventSignal(place, max(counts), days, tuple(sources),
                         censored=max(counts) >= GDELT_MAX_RECORDS)
    if use_cache:
        _cache_write(key, signal)
    return signal


def blind_spots(ranked: "list[dict]", place_key: str, rank_key: str = "exposed_pop",
                bottom_share: float = 0.5, **kwargs) -> list[dict]:
    """Regions the model ranks low that nonetheless attracted flood coverage.

    This is the output worth putting in a brief's limitations section. It does not
    say the model is wrong - coverage is not incidence - it says *look here*, and
    the two documented blind spots (surface runoff, basins under 150 km2) are the
    first things to check when you do.

    Pass a ranked list, best-first. `bottom_share` is the fraction of the ranking
    treated as "low exposure".
    """
    cut = int(len(ranked) * (1 - bottom_share))
    low = ranked[cut:]
    if len(low) > MAX_PLACES:
        raise ValueError(
            f"{len(low)} places to check at {GDELT_MIN_INTERVAL_S}s each is "
            f"{len(low) * GDELT_MIN_INTERVAL_S / 60:.0f} minutes. Shortlist first "
            f"(lower bottom_share, or pass the tail you actually care about); "
            f"the cap is MAX_PLACES={MAX_PLACES}."
        )
    out = []
    for row in low:
        signal = coverage(str(row[place_key]), **kwargs)
        if signal.available and signal.articles > 0:
            out.append({
                place_key: row[place_key],
                "model_rank": ranked.index(row) + 1,
                rank_key: row.get(rank_key),
                "articles": signal.articles,
                "sources": list(signal.sources),
                # Said in the payload so it cannot be dropped on the way to a slide.
                "caveat": "Coverage is not incidence. This flags where to look, not what is true.",
            })
    return sorted(out, key=lambda r: r["articles"], reverse=True)
