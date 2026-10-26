"""Tests for the static policy tool page, on synthetic tables.

The page is e-mailed to a jury and opened offline, so the tests check what
would break that or mislead a reader: no network reference in any src/href,
no external script or stylesheet, headline numbers equal to the table values,
NaN printed as "n/a" and never 0, and no personal names (Annexes 3 and 7 allow
"Team N" only). Nothing here reads the real data or touches the network.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd
import pytest

from src import policy_tool as P

NAN = float("nan")


def _countries() -> pd.DataFrame:
    rows = []
    for basis, scale in (("product", 1.0), ("product_and_monit", 2.0)):
        for iso, res, out100, bld, destroyed in (
            ("BE", 1993.979, 0.124353, 176, NAN),
            ("DE", 32561.889, 0.375837, 9286, 375.0),
            ("NL", 2448.656, 0.117453, 216, NAN),
        ):
            rows.append({
                "country": iso, "extent_basis": basis,
                "observed_km2": 10.0 * scale, "residents_observed": res * scale,
                "share_residents_outside_rp10": out100 + 0.05,
                "share_residents_outside_rp100": out100,
                "share_residents_outside_rp500": NAN if iso == "NL" else out100 - 0.02,
                "buildings_observed": bld, "buildings_within_25m_of_observed": bld * 2,
                "graded_destroyed": destroyed, "graded_damaged": NAN if math.isnan(destroyed) else 802.0,
            })
    return pd.DataFrame(rows)


def _products() -> pd.DataFrame:
    base = {
        "residential_buildings_observed": 10, "non_residential_buildings_observed": 2,
        "detection_method": "Semi-automatic extraction",
    }
    return pd.DataFrame([
        {**base, "country": "BE", "product_id": "EMSR518_AOI01_DEL_PRODUCT_v1", "emsr": "EMSR518",
         "aoi": "AOI01", "product_type": "DEL", "product_kind": "PRODUCT", "locality": "Liege",
         "observed_km2": 7.52, "residents_observed": 1355.7, "share_residents_outside_rp100": 0.129,
         "buildings_observed": 138, "graded_destroyed": NAN, "graded_damaged": NAN,
         "graded_possibly_damaged": NAN},
        {**base, "country": "DE", "product_id": "EMSR517_AOI15_GRA_PRODUCT_v1", "emsr": "EMSR517",
         "aoi": "AOI15", "product_type": "GRA", "product_kind": "PRODUCT",
         "locality": "Bad Neuenahr-Ahrweiler", "observed_km2": 4.81, "residents_observed": 3739.3,
         "share_residents_outside_rp100": 0.505, "buildings_observed": 3287,
         "graded_destroyed": 336.0, "graded_damaged": 687.0, "graded_possibly_damaged": 2791.0},
        {**base, "country": "DE", "product_id": "EMSR517_AOI15_GRA_MONIT01_v3", "emsr": "EMSR517",
         "aoi": "AOI15", "product_type": "GRA", "product_kind": "MONIT01",
         "locality": "Bad Neuenahr-Ahrweiler", "observed_km2": 10.79, "residents_observed": NAN,
         "share_residents_outside_rp100": NAN, "buildings_observed": 7031,
         "graded_destroyed": 753.0, "graded_damaged": 5078.0, "graded_possibly_damaged": 1175.0},
    ])


def _exposure() -> pd.DataFrame:
    return pd.DataFrame({
        "nuts_id": ["DEB12", "BE332", "NL423", "XX000"],
        "region": ["Ahrweiler", "Liège", "Noord-Limburg", "Nowhere"],
        "return_period": [100, 100, 100, 100],
        "exposed_pop": [11_000.0, 30_000.0, 120_000.0, NAN],
        "total_pop": [100_000.0, 600_000.0, 600_000.0, 50_000.0],
    })


def _square(code: str, lon: float, lat: float) -> dict:
    ring = [[lon, lat], [lon + 1, lat], [lon + 1, lat + 1], [lon, lat + 1], [lon, lat]]
    return {"type": "Feature", "properties": {"nuts_id": code},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


def _layers() -> dict:
    box = {"type": "Polygon", "coordinates": [[[0, 0], [5000, 0], [5000, 5000], [0, 5000], [0, 0]]]}
    return {"bounds": (-1000.0, -1000.0, 20_000.0, 20_000.0), "nuts": [("DEB12 Ahrweiler", box)],
            "borders": [], "labels": [("GERMANY", 8000.0, 8000.0)], "observed": [box],
            "monit": [box], "aoi": {"EMSR517_AOI15": box}}


@pytest.fixture(scope="module")
def page() -> str:
    return P.render_page(
        countries=_countries(), products=_products(), exposure=_exposure(),
        event_layers=_layers(),
        europe_features=[_square("DEB12", 6, 50), _square("BE332", 5, 50),
                         _square("NL423", 6, 51), _square("XX000", 7, 51)],
    )


def test_no_network_reference_in_any_src_or_href(page):
    """A citation may mention a site in text; nothing may be loaded from one."""
    for attr in re.findall(r'\b(?:src|href|xlink:href)\s*=\s*["\']([^"\']*)', page, re.I):
        assert not attr.lower().startswith(("http://", "https://", "//")), attr
    assert "url(http" not in page.lower()
    assert "@import" not in page


def test_no_external_script_or_stylesheet(page):
    assert not re.search(r"<script[^>]*\bsrc\s*=", page, re.I)
    assert not re.search(r"<link[^>]*\bhref\s*=", page, re.I)
    assert not re.search(r"<(?:img|iframe)\b", page, re.I)


def test_no_ai_service_or_fetch_in_the_page(page):
    """Annex 3: the tool calls no AI service. No fetch or XHR at all, then."""
    for token in ("fetch(", "XMLHttpRequest", "WebSocket", "api.anthropic", "openai"):
        assert token not in page


def test_headline_numbers_equal_the_table_values(page):
    countries = _countries()
    first = countries[countries["extent_basis"] == "product"].set_index("country")
    checks = {"residents": ("residents_observed", P.fmt_people),
              "outside_rp100": ("share_residents_outside_rp100", P.fmt_share),
              "buildings": ("buildings_observed", P.fmt_count),
              "destroyed": ("graded_destroyed", P.fmt_count)}
    found = re.findall(r'data-headline="([^"]+)" data-country="([^"]+)" data-value="([^"]*)">([^<]+)<', page)
    assert len(found) == 4 * 3
    for card, iso, raw, shown in found:
        column, fmt = checks[card]
        value = first.loc[iso, column]
        assert shown == fmt(value)
        if pd.isna(value):
            assert raw == ""
        else:
            assert float(raw) == pytest.approx(float(value))
    # The shown strings themselves, so a formatter change is a visible failure.
    assert 'data-country="DE" data-value="32561.889">32,600<' in page
    assert ">38%<" in page and ">9,286<" in page and ">375<" in page


def test_monitoring_figures_are_read_from_the_monit_rows(page):
    assert "DE 65,100" in page  # 32561.889 x 2, rounded to three figures


def test_nan_renders_as_na_never_zero(page):
    destroyed = re.findall(r'data-headline="destroyed" data-country="(BE|NL)" data-value="">([^<]+)<', page)
    assert destroyed == [("BE", "n/a"), ("NL", "n/a")]
    # NL has no RP500 share: n/a beside the bar, no bar width invented.
    assert P.fmt_share(NAN) == "n/a" and P.fmt_count(None) == "n/a"
    assert P.fmt_people(NAN) == "n/a" and P.fmt_km2(NAN) == "n/a"
    chart = P.hazard_chart_svg(P.outside_shares(_countries()))
    assert chart.count(">n/a<") == 1
    # A DEL product has no grading: n/a, not 0.
    liege = next(r for r in P.aoi_records(_products()) if r["key"] == "EMSR518_AOI01")
    assert liege["first"]["Graded destroyed"] == "n/a"
    # The monitoring pass with no residents figure says so.
    ahr = next(r for r in P.aoi_records(_products()) if r["key"] == "EMSR517_AOI15")
    assert ahr["monit"]["Residents in it"] == "n/a"
    assert ahr["first"]["Graded destroyed"] == "336"


def test_rounding_is_honest():
    assert P.fmt_people(32561.889) == "32,600"
    assert P.fmt_people(1355.7) == "1,360"
    assert P.fmt_people(638.3) == "640"
    assert P.fmt_people(4.1) == "4"
    assert P.fmt_share(0.003) == "<1%"
    assert P.fmt_share(0.0) == "0%"
    assert P.fmt_share(1.0) == "100%"
    assert P.fmt_km2(0.01) == "<0.1"


def test_europe_share_is_exposed_over_total_and_keeps_nan():
    shares = P.europe_shares(_exposure())
    assert shares["NL423"] == pytest.approx(0.2)
    assert shares["XX000"] is None
    caption = P.europe_caption(shares, _exposure())
    assert "Of 3 measured regions" in caption
    assert "Ahrweiler (DEB12)" in caption and "1 regions rank higher" in caption


def test_no_names_beyond_team_n(page):
    """Annexes 3 and 7: "Team N" only. The authors are read from CITATION.cff at
    test time rather than typed here, so this file carries no name either."""
    assert "Team N" in page
    assert not re.search(r'<meta[^>]+name="author"', page, re.I)
    cff = Path(__file__).resolve().parents[1] / "CITATION.cff"
    names = []
    if cff.exists():
        names = re.findall(r"(?:family|given)-names:\s*\"?([^\"\n]+)", cff.read_text(encoding="utf-8"))
    for name in names:
        assert name.strip().lower() not in page.lower()
    assert "@" not in re.sub(r"@media|@import", "", page)  # no e-mail address
    assert "github" not in page.lower()


def test_placeholders_are_present_by_default(page):
    for slot in ("[TITLE]", "[DECISION QUESTION]", "[RECOMMENDATION]", "[NAMED ACTOR]"):
        assert slot in page


def test_user_text_is_escaped():
    out = P.render_page(countries=_countries(), products=_products(), exposure=_exposure(),
                        title="<script>x</script>")
    assert "<script>x</script>" not in out


def test_event_map_draws_aoi_and_water():
    svg = P.event_map_svg(_layers(), P.aoi_records(_products()))
    assert 'data-aoi="EMSR517_AOI15"' in svg
    assert 'class="observed"' in svg and "M" in svg
