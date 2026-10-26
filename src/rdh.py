"""JRC Risk Data Hub: curated EU losses, exposure and vulnerability.

**What it adds that nothing else in the kit has.** The hazard rasters say where
water goes and GHS-POP says who is there, but neither says what a flood actually
cost. `/losses/losses/items` does: observed economic loss and casualty counts per
administrative unit, per event, with the sources behind each average named in
`data_source_list`. That is the layer that turns a modelled ranking into a
validated one - and `/risks/vulnerability/items` is a ready-made vulnerability
index to compare against the one `src/vulnerability.py` builds, which is a
sensitivity check, not a replacement.

Four things about this API that shape every line below:

**The token cannot be committed, or even kept for a day.** It comes from EU Login
and expires after 10 hours, so it is read from `RDH_BEARER_TOKEN` at call time.
No token is `RdhUnavailable`, never an empty result: "we did not look" and "we
looked and found nothing" are different statements, and collapsing them is how an
absence of data becomes a claim of absence.

**HTTP 200 is not success here.** An absent or expired token does not produce a
clean 401. The host sits behind an F5/Shape bot defence that answers with a
JavaScript challenge page under status 200 - measured against
`/admin/hazard/items` on 2026-10-06. So the body is inspected, and
`fetch._why_not_a_document` is reused rather than re-implemented: there is one
definition in this repo of "this response is not the thing I asked for".

**Never call it live in front of a jury.** Same rule as the rasters and GDELT:
every answer is cached under `data/processed/rdh_cache/`, and a cached answer is
served without touching the network. Fill the cache the day before.

**Paging is mandatory, not optional.** The API's default `limit` is 10 and its
maximum is 10000. A caller who forgets gets the first ten rows and no warning, so
`items()` always sends an explicit limit and follows `numberMatched` to the end.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from src.data_io import DATA, sources
from src.fetch import _why_not_a_document

CACHE_DIR = DATA / "processed" / "rdh_cache"
TIMEOUT_S = 60
# The API's own maximum. Asking for the maximum minimises the number of requests
# aimed at a Commission server, which is the polite direction to err in.
PAGE_LIMIT = 10_000
# A page that returns nothing stops the loop regardless of what numberMatched
# claimed, so a server that disagrees with itself cannot spin this forever.
MAX_PAGES = 100

# The six collections the published spec exposes, by the name used in the docs.
COLLECTIONS = {
    "asset": "/admin/asset/items",
    "division": "/admin/division/items",
    "hazard": "/admin/hazard/items",
    "metric": "/admin/metric/items",
    "losses": "/losses/losses/items",
    "vulnerability": "/risks/vulnerability/items",
}


class RdhUnavailable(RuntimeError):
    """No usable answer from the Risk Data Hub, with the reason in the message.

    A distinct type rather than a None return, because every caller of this
    module is about to put a number in a policy brief: a missing loss figure must
    stop the pipeline and be said out loud, not flow onward as a zero.
    """


def base_url() -> str:
    """The service root, from config/sources.yaml rather than hard-coded here.

    Same rule as the rest of the kit: `sources.yaml` owns every URL, so a moved
    endpoint is a one-line edit and every figure stays traceable to a declared
    source.
    """
    for entry in sources("geodata"):
        if entry["id"] == "drmkc_risk_data_hub":
            return str(entry["url"]).rstrip("/")
    raise RdhUnavailable(
        "no 'drmkc_risk_data_hub' entry in config/sources.yaml - declare the "
        "source before querying it"
    )


def _token(token: str | None) -> str:
    """The bearer token, or a message saying exactly how to get one."""
    resolved = token or os.getenv("RDH_BEARER_TOKEN", "")
    if not resolved.strip():
        raise RdhUnavailable(
            "RDH_BEARER_TOKEN is not set. Log in to EU Login, open the Risk Data "
            "Hub API TOKEN page, copy the token into .env. It lasts 10 hours, so "
            "it has to be refreshed on the day - that is why nothing here caches "
            "the token itself, only the responses."
        )
    return resolved.strip()


def _cache_path(collection: str, params: dict[str, Any]) -> Path:
    """One file per collection and parameter set, named so a human can read it."""
    tag = "_".join(f"{k}-{v}" for k, v in sorted(params.items()) if k != "limit")
    safe = "".join(c if c.isalnum() or c in "-_" else "." for c in tag)
    return CACHE_DIR / f"{collection}{('__' + safe) if safe else ''}.json"


def items(
    collection: str,
    token: str | None = None,
    use_cache: bool = True,
    **params: Any,
) -> list[dict]:
    """Every feature's `properties` from one RDH collection, paged to the end.

    Returns the flat property dicts rather than GeoJSON features: the geometry
    here is the administrative unit, which the kit already has from GISCO at a
    known vintage and CRS. Joining on `admin_unit_code` keeps one authority for
    boundaries instead of two that disagree at the edges.

    Raises RdhUnavailable rather than returning [] whenever the answer is not
    data - no token, a bot-defence page, a transport error.
    """
    if collection not in COLLECTIONS:
        raise RdhUnavailable(
            f"unknown collection {collection!r}; known: {sorted(COLLECTIONS)}"
        )

    cache = _cache_path(collection, params)
    if use_cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    bearer = _token(token)
    url = base_url() + COLLECTIONS[collection]
    rows: list[dict] = []
    offset = 0
    for _ in range(MAX_PAGES):
        query = {**params, "f": "json", "limit": PAGE_LIMIT, "offset": offset}
        try:
            response = requests.get(
                url,
                params=query,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Accept": "application/geo+json",
                },
                timeout=TIMEOUT_S,
            )
        except Exception as exc:  # network, DNS, timeout
            raise RdhUnavailable(f"{collection}: {exc}") from exc

        # Status first, then body: a 200 from this host still has to be proven to
        # be data (see the module docstring).
        if response.status_code >= 400:
            raise RdhUnavailable(
                f"{collection}: HTTP {response.status_code}. A 401 or 403 here "
                "usually means the 10-hour token expired; fetch a new one."
            )
        # min_bytes=0: this is a JSON API, where a valid empty page is 45 bytes.
        # The 2 KiB floor is for policy documents; only the WAF-marker check
        # applies here, which is the part that actually guards this host.
        rejection = _why_not_a_document(response.content, min_bytes=0)
        if rejection:
            raise RdhUnavailable(f"{collection}: {rejection}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RdhUnavailable(f"{collection}: response was not JSON") from exc

        features = payload.get("features", [])
        rows.extend(f.get("properties", {}) for f in features)
        matched = payload.get("numberMatched")
        if not features or (matched is not None and len(rows) >= matched):
            break
        offset += len(features)

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def flood_losses(
    token: str | None = None, country: str | None = None, **params: Any
) -> list[dict]:
    """Observed flood losses, optionally for one country. Filtered HERE, not there.

    **The server ignores `admin_hazard_type`.** Measured 2026-10-06: a request
    for Belgium with `admin_hazard_type="Flood"` came back with 1,297 rows of
    which 793 are floods and the rest are Storm (413), Extreme temperature (63)
    and Earthquake (28). The parameter is in the published spec, it is accepted,
    and it changes nothing - which is the worst kind of filter, because totalling
    the response as "flood losses" silently adds earthquakes to the number. So
    the hazard filter is applied to the returned rows and the parameter is no
    longer sent.

    `hazard_type == "Flood"` keeps every subtype (riverine, flash, coastal, ice
    jam, general). To narrow to river flooding only - the one thing the JRC
    hazard rasters actually model - pass `hazard="nat-hyd-flo-riv"`, which is the
    comparison that makes a validation honest rather than flattering.

    Caching note: the cache key is built from the parameters that are SENT, so
    the hazard narrowing happens after a cached response is read back. One
    cached country response therefore serves every hazard subset of it.
    """
    if country:
        params["admin_unit_country_code"] = country
    # Popped, not forwarded: a hazard parameter the server ignores would only
    # split the on-disk cache into one file per subset of one unfiltered answer.
    wanted = params.pop("hazard", None)
    rows = items("losses", token=token, **params)
    if wanted:
        return [r for r in rows if r.get("hazard") == wanted]
    return [r for r in rows if str(r.get("hazard_type", "")).lower() == "flood"]


def vulnerability(
    token: str | None = None, year: int | None = None, **params: Any
) -> list[dict]:
    """The RDH vulnerability index, as a cross-check on `src/vulnerability.py`.

    Two indices built from different indicators that rank the same regions
    differently is a result worth a paragraph in the brief; two that agree is
    cheap reassurance. Either way it belongs in the sensitivity section, and the
    RDH values are published per administrative unit AND per year, so pin the
    year or you will average across a decade by accident.
    """
    if year is not None:
        params["vulnerability_year"] = year
    return items("vulnerability", token=token, **params)
