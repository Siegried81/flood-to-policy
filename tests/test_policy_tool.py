"""Tests for the static policy tool page, on synthetic tables.

The page is e-mailed to a jury and opened offline, so the tests check what
would break that or mislead a reader: no network reference in any src/href,
no external script or stylesheet, hero and per-place numbers equal to the table
values, NaN printed as "n/a" and never 0, and no personal names (Annexes 3 and
7 allow "Team N" only). Nothing here reads the real data or touches the network.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
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
                "residents_outside_rp100": res * scale * out100,
                "share_residents_outside_rp10": out100 + 0.05,
                "share_residents_outside_rp100": out100,
                "share_residents_outside_rp500": NAN if iso == "NL" else out100 - 0.02,
                "buildings_observed": bld,
                "graded_destroyed": destroyed * scale, "graded_damaged": NAN,
            })
    return pd.DataFrame(rows)


def _product(**kw) -> dict:
    base = {"residential_buildings_observed": 10, "non_residential_buildings_observed": 2,
            "detection_method": "Semi-automatic extraction", "graded_destroyed": NAN,
            "graded_damaged": NAN, "graded_possibly_damaged": NAN, "observed_km2": 1.0,
            "residents_outside_rp100": NAN, "buildings_observed": 0}
    return {**base, **kw}


def _products() -> pd.DataFrame:
    return pd.DataFrame([
        _product(country="BE", product_id="EMSR518_AOI01_DEL_PRODUCT_v1", emsr="EMSR518",
                 aoi="AOI01", product_type="DEL", product_kind="PRODUCT", locality="Liege",
                 observed_km2=7.52, residents_observed=1355.7,
                 share_residents_outside_rp100=0.129, buildings_observed=138),
        _product(country="DE", product_id="EMSR517_AOI15_GRA_PRODUCT_v1", emsr="EMSR517",
                 aoi="AOI15", product_type="GRA", product_kind="PRODUCT",
                 locality="Bad Neuenahr-Ahrweiler", observed_km2=4.81, residents_observed=3739.3,
                 residents_outside_rp100=1889.1, share_residents_outside_rp100=0.505,
                 buildings_observed=3287, residential_buildings_observed=3257,
                 graded_destroyed=336.0, graded_damaged=687.0, graded_possibly_damaged=2791.0),
        _product(country="DE", product_id="EMSR517_AOI15_GRA_MONIT01_v3", emsr="EMSR517",
                 aoi="AOI15", product_type="GRA", product_kind="MONIT01",
                 locality="Bad Neuenahr-Ahrweiler", observed_km2=10.79, residents_observed=NAN,
                 share_residents_outside_rp100=NAN, buildings_observed=7031,
                 graded_destroyed=753.0),
        # Small: below both thresholds, so not offered as a place.
        _product(country="DE", product_id="EMSR517_AOI20_GRA_PRODUCT_v1", emsr="EMSR517",
                 aoi="AOI20", product_type="GRA", product_kind="PRODUCT", locality="Garzweiler",
                 residents_observed=4.1, share_residents_outside_rp100=1.0),
        # Large and unnamed: offered after the named places.
        _product(country="DE", product_id="EMSR517_AOI06_DEL_PRODUCT_v1", emsr="EMSR517",
                 aoi="AOI06", product_type="DEL", product_kind="PRODUCT", locality="Duisburg",
                 residents_observed=7142.2, share_residents_outside_rp100=0.061),
    ])


def _exposure() -> pd.DataFrame:
    return pd.DataFrame({
        "nuts_id": ["DEB12", "BE335", "NL423", "XX000", "CH011"],
        "country": ["DE", "BE", "NL", "XX", "CH"],
        "region": ["Ahrweiler", "Verviers", "Noord-Limburg", "Nowhere", "Vaud"],
        "return_period": [100, 100, 100, 100, 100],
        "exposed_pop": [11_000.0, 3_000.0, 120_000.0, NAN, 999_999.0],
        "total_pop": [100_000.0, 200_000.0, 600_000.0, 50_000.0, 1_000_000.0],
    })


def _square(code: str, lon: float, lat: float) -> dict:
    ring = [[lon, lat], [lon + 1, lat], [lon + 1, lat + 1], [lon, lat + 1], [lon, lat]]
    return {"type": "Feature", "properties": {"nuts_id": code},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


def _layer() -> dict:
    return {"png": "data:image/png;base64,iVBORw0KGgo=", "width": 400, "height": 300,
            "outline": "M0 0L10 0L10 10", "nuts": "", "towns": [("Altenahr (Ahr)", 390.0, 20.0)],
            "scale": (2, 100.0), "pixel_m": 20.0}


@pytest.fixture(scope="module")
def page() -> str:
    return P.render_page(
        countries=_countries(), products=_products(), exposure=_exposure(),
        place_layers={"EMSR517_AOI15": _layer()},
        locator={"width": 600, "height": 400, "borders": "M0 0L1 1", "labels": [],
                 "aoi": {"EMSR517_AOI15": "M0 0L5 0L5 5Z"}},
        europe_features=[_square("DEB12", 6, 50), _square("BE335", 5, 50),
                         _square("NL423", 6, 51), _square("XX000", 7, 51)],
    )


# --- offline and anonymous ------------------------------------------------------

def test_no_network_reference_in_any_src_or_href(page):
    """A citation may name a site in text; nothing may be loaded from one."""
    for attr in re.findall(r'\b(?:src|href|xlink:href)\s*=\s*["\']([^"\']*)', page, re.I):
        assert not attr.lower().startswith(("http://", "https://", "//")), attr
        assert attr.startswith("data:"), attr
    assert "url(http" not in page.lower()
    assert "@import" not in page


def test_no_external_script_or_stylesheet(page):
    assert not re.search(r"<script[^>]*\bsrc\s*=", page, re.I)
    assert not re.search(r"<link[^>]*\bhref\s*=", page, re.I)
    assert not re.search(r"<iframe\b", page, re.I)


def test_no_ai_service_or_fetch_in_the_page(page):
    """Annex 3: the tool calls no AI service. No fetch or XHR at all, then."""
    for token in ("fetch(", "XMLHttpRequest", "WebSocket", "api.anthropic", "openai"):
        assert token not in page


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


# --- numbers read from the tables ---------------------------------------------------

def _hero_values(page: str) -> dict[str, tuple[str, str]]:
    found = re.findall(r'data-hero="([^"]+)" data-value="([^"]*)">([^<]+)<', page)
    return {k: (raw, shown) for k, raw, shown in found}


def test_hero_numbers_equal_the_table_values(page):
    hero = _hero_values(page)
    assert set(hero) == {"missed", "harm", "europe", "when"}
    ahr = _products().iloc[1]
    assert float(hero["missed"][0]) == pytest.approx(ahr["share_residents_outside_rp100"])
    assert hero["missed"][1] == P.fmt_share(ahr["share_residents_outside_rp100"]) == "50 %"
    de = _countries().query("extent_basis == 'product' and country == 'DE'").iloc[0]
    assert float(hero["harm"][0]) == de["graded_destroyed"]
    assert hero["harm"][1] == "375"
    # EU-27 only: DE, BE and NL count; XX (NaN) and CH (not EU) do not.
    assert float(hero["europe"][0]) == pytest.approx(11_000 + 3_000 + 120_000)
    assert hero["europe"][1] == "0.1 million"
    assert hero["when"] == ("", "22 Dec 2027")


def test_hero_lines_carry_headcounts_from_the_tables(page):
    assert "About half of the people" in page
    assert "1,890 of 3,740 residents" in page                     # Ahr, read not multiplied
    assert "about 32,600 residents there; 12,200 of them" in page  # DE residents_outside_rp100
    assert "bring it to 750" in page                               # DE with later passes


def test_country_strip_equals_the_table(page):
    for iso, shown, share in (("BE", "1,990", "12 %"), ("DE", "32,600", "38 %"),
                              ("NL", "2,450", "12 %")):
        cell = re.search(rf'data-strip="{iso}">(.*?)</span>', page).group(1)
        assert shown in cell and share in cell


def test_place_figures_equal_the_table():
    places = {p["key"]: p for p in P.place_records(_products())}
    ahr = places["EMSR517_AOI15"]
    assert ahr["figures"]["residents"] == "3,740"
    assert ahr["figures"]["share"] == "50 %" and ahr["figures"]["share_words"] == "about half"
    assert ahr["figures"]["residential"] == "3,257"
    assert ahr["figures"]["destroyed"] == "336"
    assert ahr["later"]["residents"] == "n/a"  # the later pass has no residents figure


def test_each_figure_names_its_population_grid(page):
    """The event figures use GHS-POP E2020, the European ones E2025: the page says which."""
    small = {h["id"]: h["small"] for h in P.hero(_products(), _countries(), _exposure())}
    assert "E2020" in small["missed"] and "E2025" not in small["missed"]
    assert "E2025" in small["europe"] and "E2020" not in small["europe"]
    population = next(s for s in P.SOURCES if s.startswith("Population:"))
    assert "E2020" in population and "E2025" in population
    grids = next(item for item in P.LIMITS if "Population is a model" in item)
    assert "E2020" in grids and "E2025" in grids
    for item in (small["missed"], small["europe"], population):
        assert P.esc(item) in page


def test_limits_say_design_standards_are_not_guarantees(page):
    defences = [item for item in P.LIMITS if "not guarantees" in item]
    assert len(defences) == 1 and "Ahrweiler" in defences[0]
    assert defences[0] in page
    assert any("PESETA" in s for s in P.SOURCES)


def test_places_named_first_then_large_ones_only():
    keys = [p["key"] for p in P.place_records(_products())]
    assert keys == ["EMSR517_AOI15", "EMSR518_AOI01", "EMSR517_AOI06"]
    labels = [p["label"] for p in P.place_records(_products())]
    assert labels[:2] == ["Ahr valley", "Liège (Meuse–Vesdre)"]


def test_nan_renders_as_na_never_zero(page):
    liege = next(p for p in P.place_records(_products()) if p["key"] == "EMSR518_AOI01")
    assert liege["figures"]["destroyed"] == "n/a"
    assert P.fmt_share(NAN) == "n/a" and P.fmt_count(None) == "n/a"
    assert P.fmt_people(NAN) == "n/a" and P.fmt_km2(NAN) == "n/a"
    assert P.share_words(NAN) == "n/a" and P.fmt_millions(None) == "n/a"
    chart = P.chart_html(P.outside_shares(_countries()))
    assert chart.count('<span class="v">n/a</span>') == 1  # NL at 1-in-500
    assert 'data-value=""' in chart
    # A place without a map image says so instead of drawing nothing.
    assert "No map image" in page


def test_rounding_is_honest():
    assert P.fmt_people(32561.889) == "32,600"
    assert P.fmt_people(1355.7) == "1,360"
    assert P.fmt_people(638.3) == "640"
    assert P.fmt_people(4.1) == "4"
    assert P.fmt_share(0.003) == "<1 %"
    assert P.fmt_share(0.0) == "0 %"
    assert P.fmt_millions(25_737_004) == "25.7 million"
    assert P.share_words(0.505) == "about half"
    assert P.share_words(0.124) == "about 1 in 8"
    assert P.share_words(0.376) == "about 2 in 5"


def test_chart_heading_is_written_from_the_shares():
    heading = P.chart_heading(P.outside_shares(_countries()))
    assert heading == ("Germany: 38 % lived outside the 1-in-100-year zone; "
                       "Belgium and the Netherlands: about 1 in 8")


def test_europe_classes_and_highlights(page):
    shares = P.europe_shares(_exposure())
    # EU-27 only: the Swiss and the unknown-country regions are left out.
    assert set(shares) == {"DEB12", "BE335", "NL423"}
    unmeasured = _exposure().assign(country=["DE", "BE", "NL", "DE", "CH"])
    assert P.europe_shares(unmeasured)["XX000"] is None
    assert P.europe_class(0.01) == 0 and P.europe_class(0.05) == 2 and P.europe_class(0.2) == 3
    assert P.europe_class(None) is None
    assert "Ahrweiler 11 %" in page and "Verviers 2 %" in page
    assert "low: under 2 %" in page and "not measured" in page


def test_story_map_overlay_keeps_labels_inside_the_frame():
    html = P.story_map_html({"label": "Ahr valley"}, _layer())
    assert 'text-anchor="end"' in html  # the town at x=390 of 400 runs leftward
    assert 'src="data:image/png;base64,' in html


def test_reduce_classes_never_tips_a_tie_to_outside():
    from src.story_maps import reduce_classes

    observed = np.array([[1, 1], [0, 0]], dtype=bool)
    wet = np.array([[1, 0], [0, 0]], dtype=bool)
    aoi = np.ones((2, 2), dtype=bool)
    assert reduce_classes(observed, wet, aoi, 2).tolist() == [[3]]   # 1 in, 1 out: inside
    wet[0, 0] = False
    assert reduce_classes(observed, wet, aoi, 2).tolist() == [[4]]   # 0 in, 2 out: outside
    none = np.zeros((2, 2), dtype=bool)
    assert reduce_classes(none, none, none, 1).tolist() == [[0, 0], [0, 0]]


def test_placeholders_are_present_by_default(page):
    for slot in ("[TITLE]", "[DECISION QUESTION]", "[RECOMMENDATION]", "[NAMED ACTOR]",
                 "[INSTRUMENT, COST]"):
        assert slot in page


def test_page_carries_the_briefs_recommendations_and_a_conclusion(page):
    import html
    text = html.unescape(page)
    for what, who, how in P.RECOMMENDATIONS:
        assert what in text and who in text and how in text
    assert P.CONCLUSION in text
    assert P.PLAN_REVIEW_DATE in P.CONCLUSION
    # No measured figure typed by hand: only the event's name, the legal date and labels.
    rest = P.CONCLUSION
    for allowed in (P.PLAN_REVIEW_DATE, "July 2021", "1-in-100", "Recommendations 2 and 3",
                    "Recommendation 1"):
        rest = rest.replace(allowed, "")
    assert not any(ch.isdigit() for ch in rest)


def test_user_text_is_escaped():
    out = P.render_page(countries=_countries(), products=_products(), exposure=_exposure(),
                        title="<script>x</script>")
    assert "<script>x</script>" not in out


def test_the_europe_map_draws_and_counts_the_eu27_only():
    shares = P.europe_shares(_exposure())
    svg = P.europe_svg([_square(c, i, 50) for i, c in enumerate(["DEB12", "BE335", "CH011"])], shares)
    assert "DEB12" in svg and "CH011" not in svg
    assert "of 3</b> EU-27 regions" in P.europe_text(shares, _exposure())


def test_unreported_countries_come_from_the_context_table():
    context = pd.DataFrame({
        "nuts_id": ["IE061", "IE062", "LT011", "BE335", "NO011"],
        "apsfr_cycle": ["2018"] * 5,
        "apsfr_country_reported": [False, False, False, True, False],
    })
    # Norway is outside the EU-27, so the EU statistic never names it.
    assert P.unreported_countries(context) == ("2018", ["Ireland", "Lithuania"])


def test_europe_map_names_the_unreported_states_only_when_given(page):
    assert "Not in the European risk-area layer" not in page
    out = P.render_page(countries=_countries(), products=_products(), exposure=_exposure(),
                        unreported=("2018", ["Ireland", "Lithuania"]))
    assert "Not in the European risk-area layer (2018 cycle): Ireland, Lithuania." in out


def test_eu27_names_cover_every_eu27_code():
    assert P.EU27 == frozenset(P.EU27_NAMES) and len(P.EU27) == 27
