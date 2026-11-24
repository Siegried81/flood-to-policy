"""The Risk Data Hub figures quoted in the docs, re-measured on the real cache.

`tests/test_losses.py` checks the arithmetic on a synthetic scale model, so it
stays green whatever the live API does. The numbers a reader actually sees
(`docs/datasets.md`, the `src/losses.py` docstring, the brief) come from the
cached Belgian answer instead. RDH v3.3 regrouped events and may have renumbered
their codes, so a refreshed cache can drop `FLBE202107130001` or change its row
counts without any synthetic test noticing. These tests read the files under
`data/processed/rdh_cache/` and fail on the first quoted figure that no longer
holds. They skip when the cache is absent (CI, a fresh clone): no file, no claim
to check. No network.
"""

from __future__ import annotations

import json

import pytest

from src import losses as L
from src.rdh import CACHE_DIR

BELGIUM = CACHE_DIR / "losses__admin_unit_country_code-BE.json"
HAZARDS = CACHE_DIR / "hazard.json"
JULY_2021 = "FLBE202107130001"
JULY_2021_EU = "FLEU202107120015"


def _load(path):
    if not path.exists():
        pytest.skip(f"dev-machine data: {path} (RDH cache, absent in CI)")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows():
    return _load(BELGIUM)


@pytest.fixture(scope="module")
def frame(rows):
    return L.to_frame(rows)


def test_row_counts_quoted_in_datasets_md(rows):
    """1,297 rows for Belgium, 793 of them floods, spanning 1983-2024."""
    assert len(rows) == 1297
    assert sum(r["hazard_type"] == "Flood" for r in rows) == 793
    years = [r["event_start_date_year"] for r in rows]
    assert (min(years), max(years)) == (1983, 2024)


def test_hazard_catalogue_size():
    assert len(_load(HAZARDS)) == 77


def test_july_2021_event_codes_still_exist(rows):
    """The codes the docs cite. A renumbering in a new API version shows up here."""
    national = [r for r in rows if r["event_code"] == JULY_2021]
    assert len(national) == 67
    assert {r["event_code_eu"] for r in national} == {JULY_2021_EU}


def test_nesting_figures_for_july_2021_casualties(frame):
    """114.01 summed over every level, 29.67 at each of the top three, 25.00 at NUTS3."""
    raw = frame[(frame["event_code"] == JULY_2021) & (frame["metric"] == "casualty_count")]
    assert len(raw) == 25
    assert raw["value_2015_event_src_average"].sum() == pytest.approx(114.01, abs=0.01)
    for level, expected in [("Country", 29.67), ("NUTS1", 29.67), ("NUTS2", 29.67), ("NUTS3", 25.00)]:
        picked = L.select_level(frame, "casualty_count", level, event_code=JULY_2021)
        assert picked[L.VALUE_COLUMN].sum() == pytest.approx(expected, abs=0.01), level


def test_nuts3_coverage_figures(frame):
    """0.843 overall; BE31 has no NUTS3 row; Liege's children exceed the province."""
    totals = L.total_by_unit(frame, "casualty_count", "NUTS3", event_code=JULY_2021)
    assert totals["parent_coverage_ratio"].iloc[0] == pytest.approx(0.843, abs=0.001)
    cov = L.level_coverage(frame, "casualty_count", "NUTS3", event_code=JULY_2021)
    by_parent = cov.set_index("parent_code")
    assert by_parent.loc["BE31", "parent_total"] == pytest.approx(3.33, abs=0.01)
    assert by_parent.loc["BE31", "child_total"] == 0.0
    assert by_parent.loc["BE33", "parent_total"] == pytest.approx(13.67, abs=0.01)
    assert by_parent.loc["BE33", "child_total"] == pytest.approx(16.5, abs=0.01)


def test_euro_vintage_ratio_is_flat(frame):
    """The two value fields differ by exactly 1.16 on every monetary row."""
    money = frame[frame["quantity_kind"] == L.CURRENCY_KIND]
    ratio = money["value_event_src_average"] / money["value_2015_event_src_average"]
    assert set(ratio.round(4).dropna()) == {1.16}
