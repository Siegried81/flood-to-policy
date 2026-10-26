"""Tests for the CEMS rapid-mapping activation summary. The HTTP is always mocked.

Pinned: a wildfire counted as a flood, a multi-country activation counted once
in the country table (or twice in the total), a non-EU country flagged EU-27,
pagination dropped, and a cache that triggers a second download.
"""

from __future__ import annotations

import json

import pytest

from scripts import cems_activations as script
from src import activations

LISTED = [
    {"code": "EMSR700", "countries": ["Slovenia", "Croatia"], "category": "Flood",
     "activationTime": "2023-08-05T10:00:00", "eventTime": "2023-08-04T00:00:00", "name": "Flood SI/HR"},
    {"code": "EMSR701", "countries": ["Slovenia"], "category": "flood",
     "activationTime": "2024-09-15T10:00:00", "name": "Flood SI"},
    {"code": "EMSR702", "countries": ["Greece"], "category": "Wildfire",
     "activationTime": "2024-07-01T10:00:00", "name": "Fire GR"},
    {"code": "EMSR703", "countries": ["Bosnia and Herzegovina"], "category": "Flood",
     "activationTime": None, "eventTime": "2024-10-04T00:00:00", "name": "Flood BA"},
]


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _Session:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, timeout):
        self.calls.append(url)
        return _Response(self.pages[url])


def test_only_floods_one_row_per_country():
    rows = activations.floods(LISTED)
    assert sorted(rows["code"].unique()) == ["EMSR700", "EMSR701", "EMSR703"]
    assert len(rows) == 4  # EMSR700 counts for Slovenia AND Croatia
    assert rows.set_index("country")["eu27"].to_dict()["Bosnia and Herzegovina"] == False  # noqa: E712
    # No activation time: the event year stands in.
    assert rows.loc[rows["code"] == "EMSR703", "year"].iloc[0] == 2024


def test_table_by_country_and_year_and_headline():
    rows = activations.floods(LISTED)
    table = activations.by_country_year(rows).set_index("country")
    assert table.loc["Slovenia", "2023"] == 1 and table.loc["Slovenia", "2024"] == 1
    assert table.loc["Slovenia", "total"] == 2
    assert list(table.index[:2]) == ["Slovenia", "Croatia"]  # EU-27 first, by total
    head = activations.headline(rows)
    assert head == {"flood_activations": 3, "eu27_flood_activations": 2,
                    "first_year": 2023, "last_year": 2024}


def test_fetch_follows_pages_and_caches(tmp_path):
    cache = tmp_path / "a.json"
    session = _Session({
        "https://x/1": {"count": 4, "next": "https://x/2", "results": LISTED[:2]},
        "https://x/2": {"count": 4, "next": None, "results": LISTED[2:]},
    })
    got = activations.fetch("https://x/1", cache=cache, session=session)
    assert len(got) == 4 and session.calls == ["https://x/1", "https://x/2"]
    again = activations.fetch("https://x/1", cache=cache, session=session)
    assert again == got and len(session.calls) == 2  # read from the cache


def test_fetch_refuses_an_unexpected_payload(tmp_path):
    session = _Session({"https://x/1": {"detail": "throttled"}})
    with pytest.raises(ValueError, match="unexpected payload"):
        activations.fetch("https://x/1", cache=tmp_path / "a.json", session=session)
    assert not (tmp_path / "a.json").exists()


def test_script_writes_the_csv_from_the_cache(tmp_path, capsys):
    cache = tmp_path / "a.json"
    cache.write_text(json.dumps(LISTED), encoding="utf-8")
    out = tmp_path / "by_country.csv"
    assert script.main(["--cache", str(cache), "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "country,eu27,2023,2024,total"
    assert "3 floods (2 touching the EU-27)" in capsys.readouterr().out
