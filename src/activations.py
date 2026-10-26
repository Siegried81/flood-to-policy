"""How often the EU's emergency flood mapping was called, by country and year.

Source: the anonymous CEMS rapid-mapping public dashboard API
(`cems_rapid_mapping_activations` in config/sources.yaml). One GET returns
every activation the dashboard lists - EMSR656 onwards, so from March 2023;
older activations such as EMSR517/518 (July 2021) are not in it, and the
summary says so rather than reading as "no flood before 2023".

Measured 2026-10-24: 268 activations, 90 with `category == "Flood"`, each with
a `countries` list of English short names ("Czechia", "Viet Nam").

**An activation that spans several countries counts once for EACH of them.**
That is the reading a country row needs ("how often was Slovenia mapped"), but
it means the country rows do not add up to the number of activations; the
total is computed separately, on distinct activation codes.

Context for the brief, not an indicator: an activation is a request for
mapping, made by a national authority, and its frequency also reflects how
readily a country asks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

from src.data_io import DATA, sources

CACHE = DATA / "processed" / "cems_activations.json"
SUMMARY = DATA / "processed" / "cems_activations_by_country.csv"
FLOOD = "flood"

#: The EU-27 member states as the dashboard spells them (English short names).
EU27 = frozenset({
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia", "Denmark",
    "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland",
    "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands",
    "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden",
})


def source_url() -> str:
    """The dashboard URL, from config/sources.yaml rather than a second copy."""
    for section in sources().values():
        if isinstance(section, list):
            for entry in section:
                if isinstance(entry, dict) and entry.get("id") == "cems_rapid_mapping_activations":
                    return entry["url"]
    raise KeyError("cems_rapid_mapping_activations is not declared in config/sources.yaml")


def fetch(url: str | None = None, *, cache: Path = CACHE, use_cache: bool = True,
          session=requests) -> list[dict]:
    """Every listed activation, from the cache or one GET (following `next` pages).

    Cached because the kit runs offline at the venue; `use_cache=False`
    refreshes it. A response that is not the expected `{"results": [...]}`
    shape is an error, never an empty list.
    """
    if use_cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    url = url or source_url()
    results: list[dict] = []
    while url:
        response = session.get(url, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError(f"unexpected payload from {url}: {str(payload)[:200]}")
        results += payload["results"]
        url = payload.get("next")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def floods(activations: list[dict]) -> pd.DataFrame:
    """Flood activations, one row per (activation, country), with year and EU-27 flag.

    The year is the ACTIVATION year (when mapping was requested), falling back
    to the event year where the activation time is missing.
    """
    rows = []
    for item in activations:
        if str(item.get("category", "")).strip().lower() != FLOOD:
            continue
        when = item.get("activationTime") or item.get("eventTime")
        year = pd.to_datetime(when, errors="coerce").year if when else None
        for country in item.get("countries") or ["(unknown)"]:
            rows.append({"code": item.get("code"), "country": country, "year": year,
                         "eu27": country in EU27, "name": item.get("name")})
    frame = pd.DataFrame(rows, columns=["code", "country", "year", "eu27", "name"])
    frame["year"] = frame["year"].astype("Int64")
    return frame


def by_country_year(flood_rows: pd.DataFrame) -> pd.DataFrame:
    """Flood activations per country and year, wide by year, with a total.

    Columns: `country`, `eu27`, one per year, `total`. Sorted EU-27 first,
    then by total.
    """
    if flood_rows.empty:
        return pd.DataFrame(columns=["country", "eu27", "total"])
    counts = (flood_rows.drop_duplicates(["code", "country"])
              .pivot_table(index=["country", "eu27"], columns="year", values="code",
                           aggfunc="count", fill_value=0))
    counts.columns = [str(c) for c in counts.columns]
    counts["total"] = counts.sum(axis=1)
    counts = counts.reset_index().sort_values(["eu27", "total", "country"],
                                              ascending=[False, False, True])
    return counts.reset_index(drop=True)


def headline(flood_rows: pd.DataFrame) -> dict:
    """Distinct flood activations in all and touching the EU-27, and the date span."""
    eu = flood_rows[flood_rows["eu27"]]
    return {
        "flood_activations": int(flood_rows["code"].nunique()),
        "eu27_flood_activations": int(eu["code"].nunique()),
        "first_year": None if flood_rows.empty else int(flood_rows["year"].min()),
        "last_year": None if flood_rows.empty else int(flood_rows["year"].max()),
    }
