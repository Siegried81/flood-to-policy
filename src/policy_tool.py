"""The challenge "policy tool": one static HTML page for the July 2021 flood.

Annex 4 of the European AI Challenge asks for a file that is e-mailed, then shown
in a five-minute demo, and Annex 3 forbids the tool from calling any AI service.
So this module renders ONE self-contained HTML string - inline CSS, inline SVG,
inline PNG and satellite JPEG maps as data URIs and a few lines of inline JS for the place selector
- that opens by double-click with the network off. `scripts/build_policy_tool.py`
reads the files, rasterises the maps and calls `render_page`; everything here is
pure, so the tests run on synthetic tables.

The page is an argument, top to bottom: four numbers that say why act (the map
missed people, the harm, not a one-off, the date to act by), a story map per
flooded place showing where the water went against where the 1-in-100-year map
expected it, the same comparison per country, Europe for context, then the
recommendation and the limits.

Rules the page follows, and why:

- **Every computed figure is read from a table, never typed.** The formatters
  take the table value and nothing else, and each hero number carries its raw
  value in a `data-value` attribute so a test (or a juror with dev tools) can
  check the rounding against the source. The exceptions are typed text, named
  in the footer: legal dates, the recommendations and the per-place cards, whose
  figures are copied from the team's Q3 table and the cited sources.
- **A missing figure prints "n/a", never 0.** Belgium and the Netherlands have
  no graded (GRA) products, so no damage grades: 0 destroyed would state that
  nothing was destroyed there, which nobody measured.
- **Rounding is honest.** Residents are a model (GHS-POP weighted by flooded
  cell share), shown to the whole person like the brief (the precision is the
  model's, not a headcount); building points are counted and shown exactly. A share put into words ("about half") always prints its
  percentage beside the words.
- **No link anywhere.** Sources are cited as text: Annexes 3 and 7 forbid a
  repo link, and a page that fetches nothing cannot break on a venue network.
- **Readable in greyscale and by colour-blind readers.** Water inside the map
  is a dark blue and water outside it a light orange, so the two differ in
  lightness, not only in hue; every chart prints its values as text.
"""

from __future__ import annotations

import html
import json
import math
from typing import Any, Iterable, Sequence

import pandas as pd

from src import story_maps, svgmap

NA = "n/a"
TEAM = "Team 9"
HEADLINE_BASIS = "product"
COUNTRIES = ("BE", "DE", "NL")
COUNTRY_NAMES = {"BE": "Belgium", "DE": "Germany", "NL": "Netherlands"}
CHART_RPS = (10, 100, 500)

#: The hero place: EMSR517 AOI15, Bad Neuenahr-Ahrweiler on the Ahr, graded by
#: analysts (GRA), so its water is drawn through the streets rather than
#: stopped at walls as the radar delineations are.
HERO_AOI = "EMSR517_AOI15"

#: The named places of the story map, in selector order: (AOI key, label).
#: Other AOIs join after them when their first pass reached at least
#: `PLACE_MIN_RESIDENTS` residents or `PLACE_MIN_BUILDINGS` buildings.
NAMED_PLACES: tuple[tuple[str, str], ...] = (
    ("EMSR517_AOI15", "Ahr valley"),
    # EMSR518 AOI01 is named for the Meuse it mostly covers north of Liège, with
    # the lower Vesdre; "Vesdre" alone would promise the valley it barely holds.
    ("EMSR518_AOI01", "Liège (Meuse–Vesdre)"),
    ("EMSR518_AOI02", "Rochefort"),
    ("EMSR517_AOI07", "Erftstadt"),
    ("EMSR520_AOI01", "Venlo–Roermond"),
)
PLACE_MIN_RESIDENTS = 1000
PLACE_MIN_BUILDINGS = 100

#: Towns for orientation on the story maps: labels only, never used in a
#: figure. (name, river, lon, lat), positions of the town centres.
TOWNS: tuple[tuple[str, str, float, float], ...] = (
    ("Bad Neuenahr-Ahrweiler", "Ahr", 7.120, 50.545),
    ("Altenahr", "Ahr", 6.985, 50.516),
    ("Schuld", "Ahr", 6.905, 50.447),
    ("Sinzig", "Ahr", 7.247, 50.545),
    ("Liège", "Meuse", 5.571, 50.633),
    ("Verviers", "Vesdre", 5.862, 50.590),
    ("Pepinster", "Vesdre", 5.805, 50.567),
    ("Chaudfontaine", "Vesdre", 5.638, 50.585),
    ("Rochefort", "Lomme", 5.222, 50.161),
    ("Erftstadt-Blessem", "Erft", 6.776, 50.788),
    ("Roermond", "Meuse", 5.987, 51.194),
    ("Venlo", "Meuse", 6.172, 51.370),
)

#: NUTS country codes of the EU-27 and their English short names: the codes for
#: the Europe-wide headcount, the names for any country the page lists.
EU27_NAMES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DK": "Denmark", "EE": "Estonia", "EL": "Greece", "ES": "Spain",
    "FI": "Finland", "FR": "France", "HR": "Croatia", "HU": "Hungary", "IE": "Ireland",
    "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MT": "Malta",
    "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SE": "Sweden",
    "SI": "Slovenia", "SK": "Slovakia",
}
EU27 = frozenset(EU27_NAMES)

#: Directive 2007/60/EC, Article 14(3), as recorded in config/legislation.yaml:
#: the plans "shall be reviewed, and if necessary updated, ... by 22 December
#: 2021 and every six years thereafter". The next date is that arithmetic.
PLAN_REVIEW_DATE = "22 December 2027"
PLAN_REVIEW_DATE_SHORT = "22 Dec 2027"
PLAN_REVIEW_SOURCE = (
    "Plan review date: Directive 2007/60/EC (Floods Directive), Article 14(3): flood "
    "risk management plans \"shall be reviewed, and if necessary updated ... by 22 "
    "December 2021 and every six years thereafter\"; the next review falls on "
    "22 December 2027.")

#: The brief's three recommendations, in its words, so the tool, the Space and the
#: brief say the same thing (Annex 4, criterion 3). They answer the case's Q4: the
#: places still exposed and the first actions Anna, the cross-border crisis
#: coordinator, can take, using Q1 (who the water reached outside the map), Q2
#: (what is still missing) and Q3 (the shelter gaps), and they act before the
#: water: warn with escalation, name who, break the dam / river-flow silo, the
#: right lever per place. Each is (what, who and by when, instrument).
RECOMMENDATION_1: tuple[str, str, str] = (
    "Alert at the first EFAS notice, with the worst case and one action. Say how bad it could get "
    "and what to do; the 10 July 2021 notice never said it would be far worse "
    "by the 14th. Warn first where warning time is shortest (the Vesdre valley, Eschweiler), then the "
    "zones de secours, the Eupen and Gileppe dam operators and the Meuse authorities across "
    "the border.",
    "Anna, before the forecast rain arrives.",
    "Cell Broadcast (BE-Alert, NL-Alert, DE-Alert); staff time.")
RECOMMENDATIONS: tuple[tuple[str, str, str], ...] = (
    ("Give every street a meeting point. In Liège 855 of the 1,356 people the 2021 water reached had "
     "no dry public building within 500 m: ask the mayors to name, street by street, the nearest "
     "dry building as the meeting point and put it in the alert (\"leave the valley floor, go to "
     "...\"); help first those who cannot act alone (the elderly were overrepresented among the "
     "dead, Thieken et al., 2026); where none is within walking reach, plan transport.",
     "Anna, with the mayors, this week.",
     "The alert message and this tool's map of dry buildings; staff time."),
    ("One border, one picture, before 2027. The decision-makers differ in each country (the "
     "provincial governor in Liège, the safety regions in Dutch Limburg, the Städteregion "
     "Aachen), and their reports cannot be compared: Belgium has no damage grading, Belgian "
     "Limburg no 2021 satellite map. Agree one shared picture (rain, river flow, dam releases), "
     "one alert trigger, common data standards so reports compare, and map the small rivers the European map leaves "
     "out (below about 150 km²). Then the right lever: warning and meeting points, not a bigger "
     "dyke, on big rivers; flash warning, local protection and managed retreat on small ones. "
     "Of the €46 bn of 2021 flood losses in Europe only €11 bn were insured (Munich Re, 2022).",
     "Anna, with her counterparts in Dutch Limburg and the Aachen region, through EMRIC (the "
     "Euregio Meuse-Rhine crisis cooperation) and the International Meuse Commission, for the "
     "2027 plan review.",
     "Floods Directive Article 8(2), one coordinated plan for the Meuse district, and the "
     "Article 14 review (Article 8(5) if a State cannot resolve an issue): no new body."),
)

#: The page's bottom line, the brief's closing paragraph without its figures (the
#: page types none by hand).
CONCLUSION = (
    "July 2021 showed that the flood map can miss many of the people a flood reaches, and "
    "that a forecast which reaches the authorities days ahead can still fail the people who "
    "must act. The border area is better prepared on paper than it is on the ground. "
    "Recommendation 1 is the action for this week's bulletin. Recommendations 2 and 3 close "
    "the shelter gaps and put each place's money on the lever its risk needs. The next window "
    f"to act is the plan review of {PLAN_REVIEW_DATE}.")

#: Story-map raster classes, shared with the web export so both draw the same map.
RASTER_CLASSES = story_maps.RASTER_CLASSES

#: Europe map classes: share of residents in the undefended 1-in-100-year zone.
EUROPE_CLASSES: tuple[tuple[float, str, str], ...] = (
    (0.02, "low: under 2 %", "#fde9c4"),
    (0.05, "moderate: 2–5 %", "#f6b26b"),
    (0.10, "high: 5–10 %", "#d9661f"),
    (math.inf, "very high: 10 % or more", "#7f2704"),
)
EUROPE_HIGHLIGHT = (("DEB12", "Ahrweiler"), ("BE335", "Verviers"))


# --- formatting -------------------------------------------------------------

def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def _num(value: Any) -> float | None:
    return None if _missing(value) else float(value)


def fmt_people(value: Any) -> str:
    """Residents, to the whole person, as the notebook and the brief print them.

    The count is a GHS-POP model weighted by flooded cell share, so its last digits
    are not known to the person; it is printed exactly anyway so that the tool, the
    brief and the notebook quote the same figure (1,107 of 1,213), and the limits
    say it is a model.
    """
    if _missing(value):
        return NA
    return f"{round(float(value)):,}"


def fmt_millions(value: Any) -> str:
    """A large headcount as "25.7 million"."""
    if _missing(value):
        return NA
    return f"{float(value) / 1e6:,.1f} million"


def fmt_share(value: Any) -> str:
    """A 0-1 share as a whole percentage; "<1 %" rather than a misleading "0 %"."""
    if _missing(value):
        return NA
    pct = float(value) * 100
    if 0 < pct < 0.5:
        return "<1 %"
    return f"{pct:.0f} %"


def fmt_count(value: Any) -> str:
    """A counted quantity (building points, graded buildings), shown exactly."""
    if _missing(value):
        return NA
    return f"{int(round(float(value))):,}"


def fmt_km2(value: Any) -> str:
    """An area in km2 to one decimal; "<0.1" for a sliver rather than "0.0"."""
    if _missing(value):
        return NA
    v = float(value)
    if 0 < v < 0.05:
        return "<0.1"
    return f"{v:,.1f}"


#: Plain fractions a share is put into words with, nearest one wins.
_WORDS = ((0.10, "1 in 10"), (0.125, "1 in 8"), (0.20, "1 in 5"), (0.25, "a quarter"),
          (1 / 3, "a third"), (0.40, "2 in 5"), (0.50, "half"), (0.60, "3 in 5"),
          (2 / 3, "two thirds"), (0.75, "three quarters"), (0.90, "9 in 10"))


def share_words(value: Any) -> str:
    """A share as "about half", "about 1 in 8"... or n/a.

    Only ever printed with the percentage next to it, so the words cannot
    round a figure further than the reader can check.
    """
    if _missing(value):
        return NA
    v = float(value)
    if v < 0.05:
        return "almost none"
    if v > 0.95:
        return "almost all"
    return "about " + min(_WORDS, key=lambda w: abs(w[0] - v))[1]


def esc(text: Any) -> str:
    """HTML-escape any value that came from a table."""
    return html.escape(str(text), quote=True)


# --- figures from the tables --------------------------------------------------

def country_rows(countries: pd.DataFrame, basis: str = HEADLINE_BASIS) -> dict[str, pd.Series]:
    """One row per country for one extent basis, keyed by ISO code.

    The headline uses `product` (first delineations and gradings only): the
    monitoring passes were mapped days later and extend the extent, so mixing
    them in would make the headline a union of several dates.
    """
    rows = countries[countries["extent_basis"] == basis]
    return {str(r["country"]): r for _, r in rows.iterrows()}


def aoi_key(emsr: str, aoi: str) -> str:
    """`EMSR517_AOI15`: one mapped area, whatever pass or product type."""
    aoi = str(aoi)
    return f"{emsr}_{aoi if aoi.startswith('AOI') else 'AOI' + aoi}"


def first_pass(products: pd.DataFrame) -> dict[str, pd.Series]:
    """The first-pass (PRODUCT) row of every AOI, keyed by `aoi_key`."""
    rows = products[products["product_kind"] == "PRODUCT"]
    return {aoi_key(r["emsr"], r["aoi"]): r for _, r in rows.iterrows()}


def europe_headcount(exposure: pd.DataFrame, return_period: int = 100) -> float | None:
    """EU-27 residents inside the undefended zone at one return period.

    `exposed_pop` summed over the EU-27 NUTS3 rows of one period only: the
    extents are nested, so a sum over periods counts the floodplain repeatedly.
    """
    view = exposure[(exposure["return_period"] == return_period)
                    & exposure["country"].isin(EU27)]
    if view.empty or view["exposed_pop"].notna().sum() == 0:
        return None
    return float(view["exposed_pop"].sum())


def hero(products: pd.DataFrame, countries: pd.DataFrame,
         exposure: pd.DataFrame, *, hero_aoi: str = HERO_AOI,
         place_name: str = "the Ahr valley",
         place_small: str = "Bad Neuenahr-Ahrweiler, first satellite map; residents from the GHS-POP 2020 (E2020) model.") -> list[dict[str, Any]]:
    """The four numbers of the argument: missed, harm, not a one-off, when.

    Each is (id, big text, raw value, plain line, small print). The raw value
    is what the test compares with the table; the date has none, since it is
    law, not data.
    """
    ahr = first_pass(products).get(hero_aoi)
    ahr_share = _num(ahr["share_residents_outside_rp100"]) if ahr is not None else None
    ahr_out = _num(ahr.get("residents_outside_rp100")) if ahr is not None else None
    ahr_res = _num(ahr["residents_observed"]) if ahr is not None else None
    de = country_rows(countries).get("DE")
    de_all = country_rows(countries, "product_and_monit").get("DE")
    destroyed = _num(de["graded_destroyed"]) if de is not None else None
    destroyed_later = _num(de_all["graded_destroyed"]) if de_all is not None else None
    de_res = _num(de["residents_observed"]) if de is not None else None
    de_out = _num(de.get("residents_outside_rp100")) if de is not None else None
    eu = europe_headcount(exposure)
    return [
        {"id": "missed", "big": fmt_share(ahr_share), "raw": ahr_share,
         "line": (f"{share_words(ahr_share).capitalize()} of the people the July 2021 water reached in {place_name} lived OUTSIDE "
                  f"the European 1-in-100-year flood zone: {fmt_people(ahr_out)} of "
                  f"{fmt_people(ahr_res)} residents."),
         "small": place_small},
        {"id": "harm", "big": fmt_count(destroyed), "raw": destroyed,
         "line": (f"buildings graded destroyed in Germany. The water reached "
                  f"{fmt_people(de_res)} residents there; {fmt_people(de_out)} of them lived "
                  f"outside the 1-in-100-year zone."),
         "small": (f"Copernicus damage grading, first maps only; later maps of the same areas "
                   f"bring it to {fmt_count(destroyed_later)}. Only German areas were graded.")},
        {"id": "europe", "big": fmt_millions(eu), "raw": eu,
         "line": "people in the EU live inside the 1-in-100-year river flood zone. July 2021 was not a one-off risk.",
         "small": "JRC hazard map without dikes, GHS-POP 2025 (E2025, 1 km) population, all EU-27 regions."},
        {"id": "when", "big": PLAN_REVIEW_DATE_SHORT, "raw": None,
         "line": "is when every Member State must review its flood risk management plans: the deadline for recommendation 3.",
         "small": "Floods Directive 2007/60/EC, Article 14(3)."},
    ]


def country_strip(countries: pd.DataFrame) -> list[dict[str, Any]]:
    """Per country: residents reached and share outside the 100-year zone, first pass."""
    first = country_rows(countries)
    out = []
    for iso in COUNTRIES:
        row = first.get(iso)
        res = _num(row["residents_observed"]) if row is not None else None
        share = _num(row["share_residents_outside_rp100"]) if row is not None else None
        out.append({"country": iso, "residents": res, "share": share,
                    "residents_shown": fmt_people(res), "share_shown": fmt_share(share)})
    return out


#: Per-place decision card so the tool answers all four questions and helps a
#: mayor act: a transparent priority ("evacuate first"), Q3 shelter, Q4 lever and
#: Q2 "since 2021". Shelter figures are the team's (OBAT public buildings outside
#: the flood zone, straight-line reach; `outputs/shelter_access.csv`). Keyed by
#: AOI; absent keys get no card.
PLACE_ACTIONS = {
    "EMSR518_AOI01": {
        "priority": "Evacuate first (1 of 3): the farthest from a shelter (855 of 1,356 have none within 500 m), and the Vesdre rises fast.",
        "shelter": "Only 37 % of the people the water reached are within 500 m of a public building on safe ground (median ~1.1 km) — shelter is far for many; and 45 schools and 2 hospitals or care homes sit inside the 1-in-100 zone themselves.",
        "lever": "On the Meuse the defences hold — warn and open shelters, not a bigger dyke. On the Vesdre the water is outside the map (a small river): flash warning, local protection, managed retreat.",
        "since": "Vesdre strategic scheme (2023), resilient bank works, Eupen dam flood reserve raised 2.8→7 M m³ — but only one Walloon reservoir dam has an emergency plan (2025).",
    },
    "EMSR517_AOI09": {
        "priority": "Least warning time (2 of 3): nine in ten were outside the map and the Inde is a small, flashy river — fewer people than Liège, but the shortest lead time.",
        "shelter": "91 % of the people the water reached are within 500 m of a public building on safe ground (median 416 m) — shelter is close here.",
        "lever": "The map misses this valley (the Inde, a small river), so a river dyke will not help: the levers are flash-flood warning, local protection, and managed retreat of the most exposed homes.",
        "since": "The Eifel-Rur water board applied in 2023 for two retention basins on the Vicht upstream of Stolberg (Roetgen-Rott and Mulartshütte); their approval status is not confirmed. German reconstruction aid is documented for North Rhine-Westphalia as a whole, not for the Aachen region.",
    },
    "EMSR520_AOI01": {
        "priority": "Lower (3 of 3): most people are inside the map, the defences hold, and the Maas gives more warning time.",
        "shelter": "60 % of the people the water reached are within 500 m of a public building on safe ground (median 722 m).",
        "lever": "Mostly inside the map and the defences largely hold — the levers are warning, shelter, and the cross-border Meuse signal.",
        "since": "Dutch Limburg programme (Waterveiligheid en Ruimte Limburg) and the Beleidstafel actions — 50 of 80 done by 2026.",
    },
}

#: Shown on every card: the priority weighting is the team's call, never the AI's.
PRIORITY_NOTE = ("Priority weighs people reached, how far outside the map, how far from a shelter and "
                 "how fast the river rises — the weights are the team's choice, not the AI's; weight "
                 "surprise and flashiness higher and Eschweiler/the Vesdre come first.")


def place_records(products: pd.DataFrame, *, first_key: str | None = None) -> list[dict[str, Any]]:
    """The selectable places: named ones first, then any other sizeable AOI.

    Figures are the first pass, like the hero; the later pass is kept for one
    line of small print, since it is a later image and not the peak either.
    """
    first = first_pass(products)
    later: dict[str, pd.Series] = {}
    for _, r in products[products["product_kind"] != "PRODUCT"].iterrows():
        later[aoi_key(r["emsr"], r["aoi"])] = r
    keys = [(k, label) for k, label in NAMED_PLACES if k in first]
    named = {k for k, _ in keys}
    extra = []
    for k, r in first.items():
        if k in named:
            continue
        res, bld = _num(r["residents_observed"]) or 0, _num(r["buildings_observed"]) or 0
        if res >= PLACE_MIN_RESIDENTS or bld >= PLACE_MIN_BUILDINGS:
            extra.append((k, str(r.get("locality", k)), res))
    keys += [(k, label) for k, label, _ in sorted(extra, key=lambda e: -e[2])]
    records = []
    for k, label in keys:
        r = first[k]
        graded = str(r.get("product_type")) == "GRA"
        m = later.get(k)
        records.append({
            "key": k, "label": label, "country": str(r["country"]),
            "locality": str(r.get("locality", "")), "graded": graded,
            "residents": _num(r["residents_observed"]),
            "share": _num(r["share_residents_outside_rp100"]),
            "residential": _num(r.get("residential_buildings_observed")),
            "destroyed": _num(r.get("graded_destroyed")) if graded else None,
            "figures": {
                "residents": fmt_people(r["residents_observed"]),
                "share": fmt_share(r["share_residents_outside_rp100"]),
                "share_words": share_words(r["share_residents_outside_rp100"]),
                "residential": fmt_count(r.get("residential_buildings_observed")),
                "buildings": fmt_count(r.get("buildings_observed")),
                "destroyed": fmt_count(r.get("graded_destroyed")) if graded else NA,
                "damaged": fmt_count(r.get("graded_damaged")) if graded else NA,
                "km2": fmt_km2(r.get("observed_km2")),
            },
            "later": None if m is None else {
                "residents": fmt_people(m["residents_observed"]),
                "share": fmt_share(m["share_residents_outside_rp100"]),
                "km2": fmt_km2(m.get("observed_km2")),
            },
            "action": PLACE_ACTIONS.get(k),
        })
    if first_key:  # bring these to the front (the first one opens the story), keeping the rest in order
        front = [first_key] if isinstance(first_key, str) else list(first_key)
        rank = {k: i for i, k in enumerate(front)}
        records.sort(key=lambda r: rank.get(r["key"], len(front)))
    return records


def outside_shares(countries: pd.DataFrame) -> dict[str, dict[int, float | None]]:
    """Share of residents outside the RP10/100/500 maps, per country, first pass."""
    first = country_rows(countries)
    out: dict[str, dict[int, float | None]] = {}
    for iso in COUNTRIES:
        row = first.get(iso)
        out[iso] = {rp: (None if row is None else _num(row.get(f"share_residents_outside_rp{rp}")))
                    for rp in CHART_RPS}
    return out


def combined_reached(countries: pd.DataFrame) -> dict[str, Any]:
    """Cross-border total the first maps reached: residents, buildings and the
    share outside the 1-in-100 zone, summed over the three countries.

    Same `product` basis as the hero (first maps only), so the dates of the
    monitoring passes are not mixed into one headline. One number for Anna: the
    whole border area at once, not three separate ones.
    """
    rows = country_rows(countries)
    res = sum((_num(r["residents_observed"]) or 0) for r in rows.values())
    bld = sum((_num(r["buildings_observed"]) or 0) for r in rows.values())
    out = sum((_num(r.get("residents_outside_rp100")) or 0) for r in rows.values())
    share = out / res if res else None
    return {"residents": res, "buildings": bld, "share_outside": share,
            "residents_shown": fmt_people(res), "buildings_shown": fmt_count(bld),
            "share_shown": fmt_share(share)}


def map_agreement(countries: pd.DataFrame) -> list[dict[str, Any]]:
    """Per country, the share of the observed flood AREA the maps covered: inside
    the 1-in-100 zone, in the 1-in-500 zone only, or outside both.

    From the cell-weighted hit rate (`product` basis): `in100` = hit rate at
    RP100, `only500` = the extra the RP500 map adds, `outside` = what even the
    RP500 map misses. This answers "was the map right?" by area, next to the
    by-people chart, which answers it by residents.
    """
    rows = country_rows(countries)
    out = []
    for iso in COUNTRIES:
        r = rows.get(iso)
        h100 = _num(r.get("hit_rate_rp100")) if r is not None else None
        h500 = _num(r.get("hit_rate_rp500")) if r is not None else None
        only500 = None if (h100 is None or h500 is None) else max(0.0, h500 - h100)
        outside = None if h500 is None else max(0.0, 1.0 - h500)
        out.append({"country": iso, "name": COUNTRY_NAMES[iso],
                    "in100": h100, "only500": only500, "outside": outside,
                    "in100_shown": fmt_share(h100), "only500_shown": fmt_share(only500),
                    "outside_shown": fmt_share(outside)})
    return out


def chart_heading(shares: dict[str, dict[int, float | None]]) -> str:
    """The chart's title, written from the 1-in-100 shares themselves.

    The highest country gets its percentage; the others are grouped by the
    words their share rounds to, so the heading never claims more than the
    bars show.
    """
    measured = [(iso, s[100]) for iso, s in shares.items() if s.get(100) is not None]
    if not measured:
        return "No country has a measured share."
    measured.sort(key=lambda x: -x[1])
    top, top_share = measured[0]
    parts = [f"{COUNTRY_NAMES[top]}: {fmt_share(top_share)} lived outside the 1-in-100-year zone"]
    groups: dict[str, list[str]] = {}
    for iso, v in measured[1:]:
        groups.setdefault(share_words(v), []).append(COUNTRY_NAMES[iso])
    for words, names in groups.items():
        joined = " and ".join(["the Netherlands" if n == "Netherlands" else n for n in names])
        parts.append(f"{joined[0].upper() + joined[1:]}: {words}")
    return "; ".join(parts)


def europe_shares(exposure: pd.DataFrame, return_period: int = 100) -> dict[str, float | None]:
    """Share of residents in the hazard zone per NUTS3: `exposed_pop / total_pop`.

    The rule the kit's UIs already apply (`app/streamlit_app.py`, `api/main.py`):
    one return period, the share rather than the headcount, NaN kept as None so
    the map paints it "not measured" rather than zero. The table is the
    undefended map: dikes are not in it.

    EU-27 regions only, when the table says which country a region is in: the
    hero's 25.7 million, the brief and the Floods Directive are about the Member
    States, and a map that also ranks Turkish and Serbian regions would set the
    July 2021 places against a different denominator from the headline.
    """
    view = exposure[exposure["return_period"] == return_period]
    if "country" in view.columns:
        view = view[view["country"].isin(EU27)]
    out: dict[str, float | None] = {}
    for code, num, den in zip(view["nuts_id"], view["exposed_pop"], view["total_pop"]):
        out[str(code)] = None if _missing(num) or _missing(den) or not den else float(num) / float(den)
    return out


def europe_class(value: float | None) -> int | None:
    """Index into `EUROPE_CLASSES`, or None when not measured."""
    if value is None:
        return None
    return next(i for i, (upper, _, _) in enumerate(EUROPE_CLASSES) if value < upper)


def europe_text(shares: dict[str, float | None], exposure: pd.DataFrame) -> str:
    """The short text beside the Europe map, every number counted from `shares`."""
    measured = [v for v in shares.values() if v is not None]
    if not measured:
        return "No region has a measured share in this table."
    above = sum(v >= 0.10 for v in measured)
    where = "EU-27" if "country" in exposure.columns else "European"
    text = (f"<p>In <b>{above:,} of {len(measured):,}</b> {where} regions, at least one "
            f"resident in ten lives inside the 1-in-100-year river flood zone.</p>")
    for code, name in EUROPE_HIGHLIGHT:
        v = shares.get(code)
        if v is None:
            continue
        higher = sum(x > v for x in measured)
        text += (f"<p><b>{esc(name)}</b> ({code}): {fmt_share(v)}; {higher:,} regions rank "
                 f"higher.</p>")
    text += ("<p>The places that flooded in 2021 were not at the top of this map: the map "
             "measures large rivers, and much of the 2021 water came from smaller ones. "
             "Many other regions carry the same or a higher risk.</p>")
    return text


# --- SVG ----------------------------------------------------------------------

def path_d(geometry: dict[str, Any], to_xy, digits: int = 1) -> str:
    """SVG path data for a GeoJSON Polygon/MultiPolygon, rings via `svgmap._rings`.

    `to_xy` maps a coordinate pair to viewBox units. Points that round onto the
    previous one are dropped, which is most of the size saving.
    """
    parts = []
    for ring in svgmap._rings(geometry):
        pts: list[str] = []
        for p in ring:
            x, y = to_xy(float(p[0]), float(p[1]))
            s = f"{x:.{digits}f} {y:.{digits}f}"
            if not pts or pts[-1] != s:
                pts.append(s)
        if len(pts) >= 3:
            parts.append("M" + "L".join(pts) + "Z")
    return "".join(parts)


def line_d(lines: Sequence[Sequence[Sequence[float]]], to_xy, digits: int = 1) -> str:
    """SVG path data for open polylines (country borders, NUTS lines)."""
    parts = []
    for line in lines:
        pts = []
        for p in line:
            x, y = to_xy(float(p[0]), float(p[1]))
            s = f"{x:.{digits}f} {y:.{digits}f}"
            if not pts or pts[-1] != s:
                pts.append(s)
        if len(pts) >= 2:
            parts.append("M" + "L".join(pts))
    return "".join(parts)


def story_map_html(place: dict[str, Any], layer: dict[str, Any] | None) -> str:
    """One place's map: the classified PNG with an SVG overlay on top.

    `layer` (from the build script) holds `png` (a data URI), `width`/`height`
    in pixels, `outline` (AOI path data in pixel units), `nuts` (path data),
    `towns` ([(label, x, y)]), `scale` ([km, pixels]) and `pixel_m`. Without
    a layer the place still shows its numbers, with a note instead of a map.
    """
    if not layer:
        return '<div class="nomap">No map image for this place.</div>'
    w, h = layer["width"], layer["height"]
    unit = max(w, h)

    def town(label: str, x: float, y: float) -> str:
        # Labels near the right edge run leftward, so none is cut by the frame.
        right = x > 0.55 * w
        tx = x - unit / 120 if right else x + unit / 120
        return (f'<g class="town"><circle cx="{x:.0f}" cy="{y:.0f}" r="{unit / 220:.1f}"/>'
                f'<text x="{tx:.0f}" y="{y - unit / 160:.0f}" text-anchor="{"end" if right else "start"}" '
                f'font-size="{unit / 48:.0f}">{esc(label)}</text></g>')

    towns = "".join(town(*t) for t in layer.get("towns", []))
    km, px = layer.get("scale", (None, None))
    fs = max(w, h) / 55
    scale = ("" if not km else
             f'<g class="scale"><rect x="{w * 0.03:.0f}" y="{h - fs * 2.2:.0f}" width="{px:.0f}" '
             f'height="{fs / 3:.1f}"/><text x="{w * 0.03:.0f}" y="{h - fs * 2.6:.0f}" '
             f'font-size="{fs:.0f}">{km:g} km</text></g>')
    credit = layer.get("credit", "")
    credit_svg = ("" if not credit else
                  f'<text x="{w * 0.985:.0f}" y="{h - fs * 0.5:.0f}" text-anchor="end" '
                  f'font-size="{fs * 0.85:.0f}" fill="#fff" '
                  f'style="paint-order:stroke;stroke:#00000088;stroke-width:3">{esc(credit)}</text>')
    return (
        f'<div class="stage" style="aspect-ratio:{w}/{h};width:min(100%,calc(75vh * {w / h:.3f}))">'
        f'<img alt="Water seen in {esc(place["label"])}, inside and outside the 1-in-100-year zone" '
        f'src="{layer["png"]}" width="{w}" height="{h}">'
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<path class="nutsl" d="{layer.get("nuts", "")}"/>'
        f'<path class="outline" d="{layer.get("outline", "")}"/>'
        f'{towns}{scale}{credit_svg}</svg></div>')


def locator_svg(locator: dict[str, Any] | None, places: Sequence[dict[str, Any]]) -> str:
    """Small overview of the BE/DE/NL area: borders, every AOI, the chosen one marked.

    `locator` holds `width`/`height` (viewBox units), `borders` (path data),
    `labels` ([(text, x, y)]) and `aoi` ({key: path data}).
    """
    if not locator:
        return ""
    keys = {p["key"] for p in places}
    shapes = "".join(
        f'<path class="loc{" pick" if k in keys else ""}" data-loc="{esc(k)}" d="{d}"/>'
        for k, d in locator.get("aoi", {}).items())
    labels = "".join(f'<text x="{x:.0f}" y="{y:.0f}">{esc(t)}</text>'
                     for t, x, y in locator.get("labels", []))
    return (f'<svg class="locator" viewBox="0 0 {locator["width"]:.0f} {locator["height"]:.0f}" '
            'role="img" aria-label="Where the chosen place is">'
            f'<rect width="100%" height="100%" class="locbg"/>'
            f'<path class="locb" d="{locator.get("borders", "")}"/>{shapes}{labels}</svg>')


def chart_html(shares: dict[str, dict[int, float | None]]) -> str:
    """One bar per country, the 1-in-100 map by default; 1-in-10 and 1-in-500 on a toggle.

    Plain HTML bars sized in %, so the chart reflows with the page and no label
    can be cut at an SVG edge. Each value is printed beside its bar.
    """
    rows = []
    for iso in COUNTRIES:
        bars = []
        for rp in CHART_RPS:
            raw = shares.get(iso, {}).get(rp)
            width = 0 if raw is None else max(0.0, min(raw, 1.0)) * 100
            bars.append(f'<div class="bar rp{rp}" data-value="{"" if raw is None else raw}">'
                        f'<span class="fill" style="width:{width:.1f}%"></span>'
                        f'<span class="v">{fmt_share(raw)}</span></div>')
        rows.append(f'<div class="crow"><div class="cname">{esc(COUNTRY_NAMES[iso])}</div>'
                    f'<div class="track">{"".join(bars)}</div></div>')
    toggle = "".join(
        f'<button type="button" data-rp="{rp}"{" class=on" if rp == 100 else ""}>1-in-{rp}-year map</button>'
        for rp in CHART_RPS)
    return (f'<div class="chart" data-rp="100"><div class="toggle" role="group" '
            f'aria-label="Which flood map">{toggle}</div>{"".join(rows)}</div>')


def europe_svg(features: Sequence[dict[str, Any]], shares: dict[str, float | None],
               width: int = 560, height: int = 520) -> str:
    """Europe in four worded classes, with Ahrweiler and Verviers outlined and named.

    Fixed, worded classes instead of the quantile sixths of `svgmap`: a reader
    needs "high: 5-10 %" more than "class 5/6". Projection and ring handling
    are `svgmap`'s, so this map and the kit's others agree on where things are.
    Regions in `svgmap.OUTERMOST` and Iceland are drawn but do not set the frame.
    """
    projected = []
    xs, ys = [], []
    skip = tuple(svgmap.OUTERMOST) + ("IS",)
    for f in features:
        code = str((f.get("properties") or {}).get("nuts_id"))
        # Only the regions the shares were counted on: one outside them is not
        # "not measured", it is outside the map's scope, so it is not drawn.
        if code not in shares:
            continue
        rings = [[svgmap._project(float(p[0]), float(p[1])) for p in ring]
                 for ring in svgmap._rings(f.get("geometry") or {})]
        rings = [r for r in rings if len(r) >= 3]
        if not rings:
            continue
        projected.append((code, rings))
        if not code.startswith(skip):
            for r in rings:
                xs += [p[0] for p in r]
                ys += [p[1] for p in r]
    if not xs:
        return '<p class="small">No boundary file was available to draw this map.</p>'
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    scale = min(width / (x1 - x0), height / (y1 - y0))

    def to_xy(x, y):
        return (x - x0) * scale, (y1 - y) * scale

    body, marks = [], []
    centres: dict[str, tuple[float, float]] = {}
    for code, rings in projected:
        cls = europe_class(shares.get(code))
        fill = svgmap.NO_DATA if cls is None else EUROPE_CLASSES[cls][2]
        d = path_d({"type": "Polygon", "coordinates": rings}, to_xy)
        v = shares.get(code)
        body.append(f'<path d="{d}" fill="{fill}"><title>{esc(code)}: '
                    f'{fmt_share(v) if v is not None else "not measured"}</title></path>')
        if code in dict(EUROPE_HIGHLIGHT):
            marks.append(f'<path class="hl" d="{d}"/>')
            pts = [to_xy(*p) for r in rings for p in r]
            centres[code] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    labels = []
    for i, (code, name) in enumerate(EUROPE_HIGHLIGHT):
        if code not in centres:
            continue
        cx, cy = centres[code]
        # Ahrweiler's label to the north-east, Verviers' to the south-west, so
        # two neighbours 80 km apart never print on top of each other.
        dx, dy = (60, -55) if i == 0 else (-70, 60)
        anchor = "start" if dx > 0 else "end"
        labels.append(f'<line x1="{cx:.0f}" y1="{cy:.0f}" x2="{cx + dx:.0f}" y2="{cy + dy:.0f}" class="lead"/>'
                      f'<text x="{cx + dx:.0f}" y="{cy + dy - 4:.0f}" text-anchor="{anchor}" class="hlt">'
                      f'{esc(name)} {fmt_share(shares.get(code))}</text>')
    w, h = (x1 - x0) * scale, (y1 - y0) * scale
    return (f'<svg class="eumap" viewBox="0 0 {w:.0f} {h:.0f}" role="img" '
            'aria-label="Share of residents in the 1-in-100-year flood zone, by region">'
            f'<g class="eu">{"".join(body)}</g>{"".join(marks)}{"".join(labels)}'
            f'<text x="{w - 4:.0f}" y="{h - 4:.0f}" text-anchor="end" class="credit">'
            '© EuroGeographics for the administrative boundaries</text></svg>')


def europe_legend(shares: dict[str, float | None]) -> str:
    """Worded classes with the number of regions in each, plus "not measured"."""
    counts = [0] * len(EUROPE_CLASSES)
    missing = 0
    for v in shares.values():
        c = europe_class(v)
        if c is None:
            missing += 1
        else:
            counts[c] += 1
    items = "".join(f'<li><span class="sw" style="background:{fill}"></span>{esc(label)} '
                    f'<span class="small">({n:,} regions)</span></li>'
                    for (_, label, fill), n in zip(EUROPE_CLASSES, counts))
    items += (f'<li><span class="sw" style="background:{svgmap.NO_DATA}"></span>not measured '
              f'<span class="small">({missing:,})</span></li>')
    return f'<ul class="eulegend">{items}</ul>'


# --- page ------------------------------------------------------------------------

LIMITS: tuple[str, ...] = (
    "<b>Built with AI, checked by people.</b> AI wrote most of the code and drafted text. "
    "The team set every definition and weight, recomputed every figure from the organisers' "
    "data and checked it against the sources. No AI runs in this page. How AI was used, and "
    "where it was wrong, is in the team's AI sheet.",
    "<b>Scenarios, not a forecast.</b> The maps are fixed flood scenarios (1-in-10, "
    "1-in-100 and 1-in-500 years). They cannot say what happens in the next 5 to 10 hours "
    "if the rain keeps falling: that comes from the European flood forecast (EFAS) and the "
    "national flash-flood services, and linking their bulletins to this screening is the "
    "next step.",
    "<b>Satellite snapshots, not the peak.</b> Copernicus maps show the water visible "
    "on one image, often a day or more after the crest. The true extent was larger.",
    "<b>Outside a mapped area means not mapped, not dry.</b> Only the outlined areas "
    "were mapped; whole flooded valleys lie outside them. Liège's figures are a floor: "
    "neither satellite map shows water in Verviers or Pepinster, on the Vesdre.",
    "<b>Two readings, both stated.</b> Liège is 13 % outside the map on the first "
    "satellite map and 34 % on the later, wider one. Shelter reach counts the buildings "
    "of all three countries (37 % within 500 m); the Belgian file alone gives 23 %. "
    "The case notebook recomputes the figures independently on the organisers' data, "
    "and an automatic test checks that they match.",
    "<b>Two kinds of maps.</b> Delineation maps, drawn semi-automatically from radar, "
    "stop at building walls and miss water between houses; grading maps, drawn by "
    "analysts, carry the water through the towns. Belgium has only delineation maps, "
    "which is why its building count is low.",
    "<b>Population is a model, on two grids.</b> The July 2021 figures use GHS-POP 2020 "
    "(E2020), as the organisers ask for a 2021 event; the European figures use GHS-POP 2025 "
    "(E2025, 1 km), the grid the EU-wide layer is built on. Both spread residents evenly "
    "within each ~1 km cell and do not know who was home in July 2021.",
    "<b>Design standards are not guarantees.</b> The European figures assume no dikes. "
    "The JRC protection layer counts every exposed resident of the Ahrweiler district as "
    "protected against the 1-in-100-year flood, and the Ahr flooded in 2021.",
    "<b>The hazard map covers large rivers only.</b> The JRC map models rivers with "
    "catchments of 150 km² and more, without dikes, and no surface runoff or small "
    "streams: much of the 2021 damage came from exactly those.",
    "<b>Permanent water is excluded from the map scores</b> (it is wet in every map and "
    "would count as a free hit); residents beside it are still counted.",
)

SOURCES: tuple[str, ...] = (
    "Flood hazard: JRC / Copernicus Emergency Management Service river flood hazard maps "
    "for Europe (v3.1.1, return periods 10 to 500 years), © European Union, CC BY 4.0.",
    "Observed flood and damage grading: Copernicus Emergency Management Service Rapid "
    "Mapping, activations EMSR517 (Germany), EMSR518 (Belgium), EMSR520 (Netherlands), "
    "July 2021, © European Union.",
    "Buildings: GHS-OBAT R2024A (epoch 2020), JRC, © European Union.",
    "Population: GHS-POP R2023A, epoch 2020 (E2020) for the July 2021 event and epoch 2025 "
    "(E2025, 1 km) for the European figures, JRC, © European Union.",
    "Flood protection: JRC PESETA IV flood protection standards (2019), © European Union.",
    "Boundaries: GISCO NUTS 2024, © EuroGeographics for the administrative boundaries.",
    PLAN_REVIEW_SOURCE,
)

HOW_WE_COUNTED: tuple[str, ...] = (
    "<b>The water</b> is what Copernicus EMS outlined as flooded area or flood trace on "
    "its first map of each area (EMSR517/518/520). Later monitoring maps add water "
    "seen days afterwards; they are shown as small print, never mixed into a headline.",
    "<b>Residents</b> are GHS-POP 2020 (E2020) counts, each ~1 km cell weighted by the share of "
    "it under the observed water, on a 20 m equal-area grid (EPSG:3035).",
    "<b>Outside the 1-in-100-year zone</b> means the 20 m cell is dry in the JRC river "
    "flood hazard map for that return period (depth 0 or no data).",
    "<b>Buildings</b> are GHS-OBAT points inside the observed water; \"destroyed\" is "
    "the Copernicus analysts' damage grade, available only for German grading maps.",
    "<b>Country totals</b> are counted on the union of the areas, cell by cell and "
    "building by building, so two maps over the same valley are not counted twice.",
    "<b>Reproduced independently in the case notebook</b>, computed from the data bucket, "
    "not copied from this page.",
)

#: Q2 desk research in one compact block: what each country/region and the EU did
#: after July 2021, so the recommendations rest on the record and not on memory.
#: Sources are cited IN TEXT (institution + date), never a link and never a
#: personal name, under the same rules as SOURCES (the tool loads nothing and
#: names no one but the team). Figures stated as plans are flagged as plans.
#: Full fiches with URLs: docs/perso/q2_sources.md. Each item is (region, bullets).
SINCE_2021: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Belgium — Wallonia and the Vesdre", (
        "Parliamentary inquiry: 161 recommendations (187 with sub-recommendations), adopted "
        "March 2022; the three-year follow-up splits them 126 for the Region, 20 partly, 37 "
        "federal, with 19 more completed since October 2024 and 58 of 88 still in progress "
        "(Walloon Parliament, 2022; Walloon Government, 17 April 2025).",
        "Reconstruction: repair cost about EUR 5.2 billion; emergency river-safety works on "
        "more than 1,000 bank sites, about 46 % done by mid-2022; resilient bank reconstruction "
        "funded (EUR 430 million recovery-plan axis 6, plus EUR 300 million of a EUR 1.1 billion "
        "EIB loan), with about 880 km along the Vesdre planned — a plan, not yet built "
        "(Commissariat à la Reconstruction, 1 July 2022; Walloon Government, 4 July 2022).",
        "Prevention and planning: a circular on building in flood zones in force since 1 April "
        "2022; the 2022–2027 flood-risk management plan (PGRI) approved 19 January 2023 with 671 "
        "local projects; EUR 71.2 million in resilience subsidies to communes (SPW, 2021–2023).",
        "Dams and modelling: an independent review found the Vesdre valley floods from a "
        "1-in-25-year event even with the Eupen dam, and asked for a legal dam-safety framework "
        "and forecast-driven operation (Stucky review, 6 December 2021); a whole-basin Vesdre "
        "model was delivered 19 March 2024 (ULiège ModRec).",
        "Compensation and clean-up: the Region put in about EUR 1 billion so insurers cover 41 % "
        "and the Region 59 % of insured damage, and about 152,000 tonnes of flood waste were "
        "treated (Walloon Government, 4 July 2022).",
    )),
    ("Germany — the Ahr (Rhineland-Palatinate)", (
        "Reconstruction fund of up to EUR 30 billion; about EUR 5.84 billion paid out by 31 "
        "December 2025. The federal government will not fund new flood-protection works from it "
        "(a task of the Länder) and points to EUR 127 million a year in the federal-Länder joint "
        "fund (German Bundestag, 27 February 2026).",
        "Public warning: technical rules for Cell Broadcast / DE-Alert over mobile networks were "
        "published 23 February 2022, the legal basis in force since December 2021 "
        "(Bundesnetzagentur, 23 February 2022).",
        "Prevention: the national flood-protection programme (NHWSP) for 2026–2035 is costed at "
        "about EUR 4 billion for the Länder, and the federal government is pursuing expanded "
        "mandatory natural-hazard insurance (German Bundestag, 27 February 2026).",
    )),
    ("Netherlands — Limburg", (
        "Policy table on flooding: 21 recommendations, all accepted (19 December 2022); the "
        "safety model was widened from three to five layers, adding water-awareness and recovery.",
        "Progress (final report, April 2026): of 80 actions, 50 done, 19 embedded in other "
        "programmes and 11 moved to a future national programme; the Limburg programme has a "
        "governing committee since November 2025 and plans built on 2100 climate projections "
        "(Dutch Ministry of Infrastructure and Water Management, 2022 and 2026).",
        "Limburg is developing risk-based protection standards on one coherent methodology, and a "
        "public web tool lets residents look up flood risk by address (Dutch Ministry of "
        "Infrastructure and Water Management, 2026).",
    )),
    ("EU level", (
        "EU Solidarity Fund (December 2022): EUR 612.6 million to Germany, EUR 87.7 million to "
        "Belgium and EUR 4.7 million to the Netherlands (Decision (EU) 2023/68).",
        "Implementation review (February 2025): only 8 of 21 assessed Member States link spatial "
        "planning and flood-risk management in law or policy, and nature-based solutions are in "
        "every plan but not yet taken up at scale; Belgium is asked for harmonised flood maps, "
        "water depths on every map and explicit climate change (European Commission, COM(2025) 2).",
        "Reporting gaps: about 14,000 areas of potential significant flood risk are declared "
        "EU-wide, but five Member States had not submitted their plans by the September 2023 "
        "cut-off, and the Commission opened proceedings over late adoption (European Commission, "
        "COM(2025) 2).",
    )),
)

#: What to do before the water, from the forecast to the first drop: the mayor's
#: question is the time before, since once the water is there the emergency
#: services know their job. Each step reuses a figure or a source already on the
#: page (EFAS's 10 July 2021 lead time, Q3's shelter reach, the schools and care
#: homes in the zone). Each is (when, who, what).
BEFORE_THE_WATER: tuple[tuple[str, str, str], ...] = (
    ("When EFAS notifies (about four days ahead, as on 10 July 2021)", "Anna",
     "Put the dam operators, the river-flow services and the mayors on one shared picture. "
     "Name each street's meeting point: the nearest dry building."),
    ("Two days ahead", "Anna, with the province and the mayors",
     "Send an alert that carries the worst case and how it could escalate, not a single level. "
     "Put the meeting point in the alert, Liège first, where residents have no dry building close by."),
    ("5 to 10 hours ahead", "Anna triggers; civil protection sends (BE-Alert, NL-Alert, DE-Alert)",
     "A Cell Broadcast that says what to do: \"leave the valley floor\". On the small rivers the "
     "map does not model, do not wait for the map."),
    ("When the water is there", "The emergency services",
     "They know what to do. This plan ends where theirs begins."),
)

#: Next steps on the ground, grounded in the gaps the desk research found (SINCE_2021)
#: and in the official recommendations. Same rules as RECOMMENDATIONS: typed text,
#: cited in place, no link, no personal name. Each is (action, who and by when, basis).
NEXT_STEPS: tuple[tuple[str, str, str], ...] = (
    ("Close the last mile of the warning chain: push a public cell-broadcast alert carrying a "
     "magnitude and an action (\"leave the valley floor\"), wired to the European flood forecast, "
     "not just a generic warning.",
     "Anna triggers it; national and regional civil-protection authorities send it, before the "
     "forecast rain arrives.",
     "The European flood forecast warned national authorities from 10 July 2021, yet 29–35 % of "
     "residents got no warning and up to half of those warned did not know what to do "
     "(peer-reviewed survey of the July 2021 flood, 2023); the cell-broadcast basis exists since "
     "February 2022."),
    ("Do not triage on the 1-in-100-year map alone: trigger on the observed 2021 footprint joined "
     "with that map, and treat small rivers and runoff as unmapped risk.",
     "The crisis coordinator, for this event.",
     "The hazard map models only large rivers; in the Aachen region about nine in ten of the "
     "people the water reached were outside it (this tool's own result)."),
    ("Pre-activate the nearest safe public buildings as shelters for the places where residents "
     "are far from one.",
     "Municipal civil protection, this week.",
     "The shelter reach per place shown in this tool."),
    ("Finish an emergency plan for every reservoir dam, not only the one that has it, and publish "
     "the forecast-driven operating rule for the Vesdre dams.",
     "Provincial governors and the Walloon waterways administration.",
     "The inquiry asked for a plan for every reservoir dam; only one exists; the independent "
     "review (6 December 2021) asked for a legal dam-safety framework and forecast-driven "
     "operation."),
    ("Publish the updated Vesdre strategic scheme, give the hazard map real weight in building "
     "permits, and report the kilometres of resilient bank actually rebuilt, not only the plan.",
     "The Walloon territory and environment administration.",
     "The scheme (2023) binds no commune and its promised update is still unpublished; \"about "
     "880 km\" is a 2022 plan."),
    ("Harmonise the regional flood-map viewers, put water depths on every hazard map, state "
     "climate change, and set quantified, time-bound objectives before the next plan.",
     "The three Belgian regions, before the 22 December 2027 plan review.",
     "The Commission's assessment of Belgium under the Floods Directive (COM(2025) 2)."),
    ("Make cross-border coordination operational on the Meuse and the Vesdre–Rur, not only "
     "planned: shared data, joint forecasting, a common area vision.",
     "The Belgian, German and Dutch basin authorities.",
     "The Dutch policy table asked for cooperation on all cross-border waters (2022); the "
     "Commission asks all three states for clearer international coordination (COM(2025) 2)."),
)

#: Decision-facing warnings: the few cautions a user must hold BEFORE acting on the
#: numbers, as plain do/don't. The fuller methodology is in LIMITS.
WARNINGS: tuple[str, ...] = (
    "Do not triage on the 1-in-100-year map alone. It models only large rivers without dikes; "
    "much of the 2021 water came from small rivers and runoff, and whole valleys flooded outside "
    "it.",
    "Outside a mapped area means not mapped, not dry. Absence of colour on a map is missing data, "
    "not safety.",
    "Works funded are not works finished. \"About 880 km\" of resilient Vesdre banks is a 2022 "
    "plan; no official source confirms how many kilometres are built.",
    "A 1-in-100-year design is not a guarantee. The Ahrweiler district counts as protected to the "
    "1-in-100-year flood, and the Ahr flooded in 2021.",
    "Shelter distances here are straight-line floors. Real walking is longer and bridges may be "
    "cut, so treat the reach figures as optimistic.",
    "In 2021 the forecast existed days ahead; the last mile failed. Warn people with an action, "
    "not just a signal.",
)

CSS = """
:root{--ink:#1d2125;--muted:#5a6068;--line:#d6d9dd;--paper:#ffffff;--soft:#f5f6f3;
--blue:#0b4f9c;--orange:#f0a030;--accent:#b4520c}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 24px 48px;overflow-wrap:break-word}
h1{font-size:2.1rem;line-height:1.2;margin:0 0 .25em}
h2{font-size:1.45rem;line-height:1.3;margin:2.6em 0 .6em}
h2 .kicker{display:block;font-size:.8rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
p{margin:.5em 0}
.question{font-size:1.2rem;color:var(--muted);margin:0 0 1.6em}
.slot{background:#fff4d6;border:1px dashed #8a6d00;padding:0 .3em}
.small{font-size:.8rem;color:var(--muted)}
.hero{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}
@media (max-width:1000px){.hero{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:560px){.hero{grid-template-columns:1fr}}
.arg{border-top:5px solid var(--ink);padding:12px 2px 0}
.arg .step{font-size:.75rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.arg .big{font-size:1.85rem;font-weight:800;line-height:1.1;margin:.2em 0 .25em}
.arg .line{font-size:.98rem;margin:0 0 .4em}
.arg-missed{border-color:var(--orange)} .arg-harm{border-color:var(--accent)}
.arg-europe{border-color:#7f2704} .arg-when{border-color:var(--blue)}
.strip{display:flex;flex-wrap:wrap;gap:8px 28px;margin:22px 0 0;padding:10px 14px;background:var(--soft);font-size:.92rem}
.strip b{font-variant-numeric:tabular-nums}
details{margin:12px 0 0;font-size:.92rem}
details summary{cursor:pointer;font-weight:600;color:var(--accent)}
details ul{margin:.4em 0;padding-left:1.2em}
.places{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
.places button{font:inherit;font-size:.9rem;padding:6px 12px;border:1.5px solid #555;border-radius:999px;background:#fff;cursor:pointer}
.places button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.places.more button{font-size:.8rem;padding:3px 10px;border-color:#999}
.story{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(0,1fr);gap:24px;margin-top:14px;align-items:start}
@media (max-width:860px){.story{grid-template-columns:1fr}}
.place[hidden],.facts[hidden]{display:none}
.stage{position:relative;margin:0 auto;border:1px solid var(--line);background:#fff}
.stage img,.stage svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.stage img{image-rendering:auto}
.stage .outline{fill:none;stroke:#222;stroke-width:1.2;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}
.stage .nutsl{fill:none;stroke:#8d939a;stroke-width:.8;vector-effect:non-scaling-stroke}
.stage .town circle{fill:#111;stroke:#fff;stroke-width:1;vector-effect:non-scaling-stroke}
.stage .town text,.stage .scale text{fill:#111;font-weight:700;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}
.stage .scale rect{fill:#111}
.maplegend{list-style:none;padding:0;margin:8px 0 0;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:.85rem}
.sw{display:inline-block;width:14px;height:14px;vertical-align:-2px;margin-right:6px;border:1px solid #666}
.facts .fig{border-top:1px solid var(--line);padding:10px 0}
.facts .fig:first-of-type{border-top:0;padding-top:0}
.facts .n{font-size:2rem;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums}
.facts .n.out{color:var(--accent)}
.facts h3{font-size:1.2rem;margin:0 0 6px}
.locator{width:100%;height:auto;display:block;margin-top:10px;border:1px solid var(--line)}
.locator .locbg{fill:#f7f7f4}
.locator .locb{fill:none;stroke:#777;stroke-width:1.2}
.locator text{font-size:22px;fill:#555;font-weight:700;letter-spacing:.1em;paint-order:stroke;stroke:#fff;stroke-width:5px;pointer-events:none}
.locator .loc{fill:#e2e2e2;stroke:#bbb;stroke-width:1}
.locator .loc.pick{fill:#c8c8c8;stroke:#999}
.locator .loc.on{fill:var(--orange);stroke:#000;stroke-width:3}
.chart{max-width:760px}
.toggle{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}
.toggle button{font:inherit;font-size:.85rem;padding:4px 10px;border:1.5px solid #555;border-radius:4px;background:#fff;cursor:pointer}
.toggle button.on{background:var(--ink);color:#fff}
.crow{display:grid;grid-template-columns:120px minmax(0,1fr);gap:12px;align-items:center;margin:8px 0}
.cname{font-weight:700}
.bar{display:none;align-items:center;gap:10px}
.chart[data-rp="10"] .bar.rp10,.chart[data-rp="100"] .bar.rp100,.chart[data-rp="500"] .bar.rp500{display:flex}
.bar .fill{display:block;height:28px;background:var(--orange);border:1px solid #6b4500;min-width:1px;flex:none}
.bar .v{font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.europe{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:28px;align-items:start}
@media (max-width:860px){.europe{grid-template-columns:1fr}}
.eumap{width:100%;height:auto;display:block}
.eumap .eu path{stroke:#fff;stroke-width:.3}
.eumap .hl{fill:none;stroke:#000;stroke-width:2.2}
.eumap .lead{stroke:#000;stroke-width:1}
.eumap .hlt{font-size:15px;font-weight:700;fill:#000;paint-order:stroke;stroke:#fff;stroke-width:4px}
.eumap .credit{font-size:9px;fill:#555}
.eulegend{list-style:none;padding:0;margin:10px 0;font-size:.9rem}
.eulegend li{margin:3px 0}
.recos{width:100%;border-collapse:collapse;font-size:.95rem}
.recos th,.recos td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
.recos tr.reco td{border:3px solid var(--ink);font-size:1.05rem}
.conclusion{font-size:1.1rem;border-left:4px solid var(--ink);padding:4px 0 4px 14px}
.warnbox{background:#fff4f0;border:1px solid #d98a6a;border-left:5px solid var(--accent);padding:12px 18px;margin:14px 0}
.warnbox .warnhead{font-weight:700;color:var(--accent);margin:0 0 .4em}
.warnbox ul{margin:.2em 0;padding-left:1.2em}
.warnbox li{margin:.35em 0;font-size:.92rem}
.combined{background:#eef3fb;border-left:5px solid var(--ink);padding:10px 16px;margin:12px 0;font-size:1.05rem}
h3.sub{font-size:1.02rem;margin:1.3em 0 .4em}
.agreetbl{width:100%;border-collapse:collapse;font-size:.92rem;margin:.3em 0}
.agreetbl th,.agreetbl td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:right}
.agreetbl th:first-child,.agreetbl td:first-child{text-align:left}
.limits{columns:2 340px;column-gap:32px;padding:16px 20px;margin:0;list-style:none;background:#fffaf0;border:1px solid #d8c48a}
.limits li{break-inside:avoid;margin:0 0 .7em;font-size:.9rem}
footer{margin-top:3em;border-top:1px solid var(--line);padding-top:10px;font-size:.78rem;color:var(--muted)}
footer ul{padding-left:1.1em}
@media print{
body{font-size:11pt}main{max-width:none;padding:0}
.places,.toggle,details summary{display:none}
details{display:block}details>*{display:block}
h2{break-after:avoid;margin-top:1.4em}
.hero,.story,.europe,.recos,.conclusion,.limits,.chart,.warnbox,.combined,.agreetbl{break-inside:avoid}
.limits{background:none}
}
"""

JS = """
(function(){
function pick(key){
document.querySelectorAll('.place,.facts').forEach(function(e){e.hidden=e.getAttribute('data-key')!==key;});
document.querySelectorAll('.places button').forEach(function(b){b.classList.toggle('on',b.getAttribute('data-key')===key);});
document.querySelectorAll('.locator .loc').forEach(function(p){p.classList.toggle('on',p.getAttribute('data-loc')===key);});
}
document.querySelectorAll('.places button').forEach(function(b){b.addEventListener('click',function(){pick(b.getAttribute('data-key'));});});
var chart=document.querySelector('.chart');
document.querySelectorAll('.toggle button').forEach(function(b){b.addEventListener('click',function(){
chart.setAttribute('data-rp',b.getAttribute('data-rp'));
document.querySelectorAll('.toggle button').forEach(function(x){x.classList.toggle('on',x===b);});});});
var first=document.querySelector('.places button');if(first)pick(first.getAttribute('data-key'));
})();
"""


def _hero_html(args: Sequence[dict[str, Any]]) -> str:
    steps = {"missed": "The map missed people", "harm": "The harm",
             "europe": "Not a one-off", "when": "The plan deadline"}
    return '<section class="hero" aria-label="Why act">' + "".join(
        f'<div class="arg arg-{esc(a["id"])}"><div class="step">{i}. {steps.get(a["id"], "")}</div>'
        f'<div class="big" data-hero="{esc(a["id"])}" data-value="{"" if a["raw"] is None else repr(a["raw"])}">'
        f'{esc(a["big"])}</div><p class="line">{esc(a["line"])}</p>'
        f'<p class="small">{esc(a["small"])}</p></div>'
        for i, a in enumerate(args, 1)) + "</section>"


def _strip_html(strip: Sequence[dict[str, Any]]) -> str:
    cells = "".join(
        f'<span data-strip="{esc(s["country"])}"><b>{esc(COUNTRY_NAMES[s["country"]])}</b>: '
        f'<b>{esc(s["residents_shown"])}</b> residents reached, '
        f'<b>{esc(s["share_shown"])}</b> outside the 1-in-100-year zone</span>'
        for s in strip)
    return f'<div class="strip">{cells}</div>'


def _facts_html(p: dict[str, Any]) -> str:
    f = p["figures"]
    destroyed = (f'<div class="fig"><div class="n">{esc(f["destroyed"])}</div>'
                 f'buildings graded destroyed, {esc(f["damaged"])} damaged</div>'
                 if p["graded"] else
                 '<div class="fig"><div class="n">n/a</div>destroyed buildings: not graded '
                 'on this kind of map</div>')
    later = ""
    if p["later"]:
        later = (f'<p class="small">A later satellite map of this area saw '
                 f'{esc(p["later"]["km2"])} km² of water, {esc(p["later"]["residents"])} residents, '
                 f'{esc(p["later"]["share"])} of them outside the zone.</p>')
    kind = ("grading map: analysts drew the water through the streets" if p["graded"]
            else "delineation map from radar: stops at walls, a floor")
    a = p.get("action")
    action = "" if not a else (
        '<div style="margin-top:.6rem;padding:.6rem .85rem;border-left:3px solid #0b4f9c;'
        'background:rgba(11,79,156,.07);border-radius:3px">'
        f'<p style="margin:0 0 .4rem"><b>Evacuate first? (priority)</b> {esc(a["priority"])}</p>'
        f'<p style="margin:0 0 .4rem"><b>Can we shelter them? (Q3)</b> {esc(a["shelter"])}</p>'
        f'<p style="margin:0 0 .4rem"><b>Which lever? (Q4)</b> {esc(a["lever"])}</p>'
        f'<p class="small" style="margin:0 0 .4rem"><b>Done since 2021 (Q2):</b> {esc(a["since"])}</p>'
        f'<p class="small" style="margin:0">{esc(PRIORITY_NOTE)}</p>'
        '</div>')
    return (f'<div class="facts" data-key="{esc(p["key"])}">'
            f'<h3>{esc(p["label"])}</h3>'
            f'<div class="fig"><div class="n">{esc(f["residents"])}</div>residents reached by the water '
            f'({esc(f["km2"])} km² seen)</div>'
            f'<div class="fig"><div class="n out">{esc(f["share"])}</div>of them lived outside the '
            f'1-in-100-year zone ({esc(f["share_words"])})</div>'
            f'<div class="fig"><div class="n">{esc(f["residential"])}</div>homes in the water '
            f'({esc(f["buildings"])} buildings in all)</div>{destroyed}'
            f'<p class="small">{esc(p["country"])} · {esc(p["key"])} · first satellite map; {kind}.</p>'
            f'{action}{later}</div>')


def _since_html() -> str:
    """The "what has been done since 2021" section, from SINCE_2021.

    Shown in full (not collapsed) so the record is part of the argument; text
    only, every figure cited in place, consistent with the page's no-link,
    no-name rules.
    """
    blocks = "".join(
        f'<p class="sincereg"><b>{esc(region)}</b></p><ul>'
        + "".join(f"<li>{esc(b)}</li>" for b in bullets) + "</ul>"
        for region, bullets in SINCE_2021)
    return ('<div class="since">' + blocks
            + '<p class="small">Official sources, cited in text with their date; figures stated '
            'as plans are not completed works; full fiches in the team Q2 desk-research file.</p></div>')


def _before_the_water_html() -> str:
    """The time before the water as a timeline table, read top to bottom."""
    rows = "".join(f"<tr><td><b>{esc(when)}</b></td><td>{esc(who)}</td><td>{esc(what)}</td></tr>"
                   for when, who, what in BEFORE_THE_WATER)
    return ('<table class="recos"><thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>")


def _next_steps_html() -> str:
    """Grounded next steps, as a table in the same shape as the recommendations."""
    rows = "".join(
        f'<tr><td><b>{i}.</b> {esc(what)}</td><td>{esc(who)}</td><td>{esc(basis)}</td></tr>'
        for i, (what, who, basis) in enumerate(NEXT_STEPS, 1))
    return ('<table class="recos"><thead><tr><th>Next step</th><th>Who, by when</th>'
            f'<th>The evidence it rests on</th></tr></thead><tbody>{rows}</tbody></table>')


def _warnings_html() -> str:
    """The decision-facing warnings callout: plain do/don't, held before acting."""
    items = "".join(f"<li>{esc(w)}</li>" for w in WARNINGS)
    return ('<div class="warnbox"><p class="warnhead">Before you act on these numbers</p>'
            f'<ul>{items}</ul></div>')


def _combined_html(c: dict[str, Any]) -> str:
    """One line: the cross-border total the first maps reached, for the three countries at once."""
    return ('<p class="combined">Across the three countries the first maps reached '
            f'<b>{esc(c["buildings_shown"])}</b> buildings and <b>{esc(c["residents_shown"])}</b> '
            f'residents — and <b>{esc(c["share_shown"])}</b> of those people lived outside the '
            '1-in-100-year flood zone.</p>')


def _agreement_html(rows: Sequence[dict[str, Any]]) -> str:
    """Table: share of the observed flood AREA inside / outside the maps, per country.

    The companion to the by-people chart: it reads the map's blind spot off the
    flooded area itself, so a country with few people but much water (the German
    valleys) still shows how much the map missed.
    """
    body = "".join(
        f'<tr><td>{esc(r["name"])}</td><td>{esc(r["in100_shown"])}</td>'
        f'<td>{esc(r["only500_shown"])}</td><td>{esc(r["outside_shown"])}</td></tr>'
        for r in rows)
    return ('<table class="agreetbl"><thead><tr><th>Country</th><th>Inside the 1-in-100 zone</th>'
            '<th>1-in-500 only</th><th>Outside both maps</th></tr></thead>'
            f'<tbody>{body}</tbody></table>')


def unreported_countries(context: pd.DataFrame) -> tuple[str, list[str]]:
    """The cycle of the European risk-area layer, and the EU-27 States absent from it.

    Read from `context.parquet` (`apsfr_country_reported` False), not typed, so the
    Europe map names exactly the States recommendation 2 is about. Absent means
    the European layer does not carry that State's current cycle, not that the
    State declared nothing: Ireland publishes its areas nationally.
    """
    cycles = context["apsfr_cycle"].dropna().astype(str).unique()
    cycle = cycles[0] if len(cycles) == 1 else "current"
    codes = context.loc[context["apsfr_country_reported"].eq(False), "nuts_id"].str[:2]
    return cycle, sorted(EU27_NAMES[c] for c in set(codes) if c in EU27_NAMES)


def render_page(
    *,
    countries: pd.DataFrame,
    products: pd.DataFrame,
    exposure: pd.DataFrame,
    place_layers: dict[str, dict[str, Any]] | None = None,
    locator: dict[str, Any] | None = None,
    europe_features: Sequence[dict[str, Any]] = (),
    title: str = "[TITLE]",
    question: str = "[DECISION QUESTION]",
    recommendation: str = "[RECOMMENDATION]",
    actor: str = "[NAMED ACTOR]",
    instrument: str = "[INSTRUMENT, COST]",
    unreported: tuple[str, list[str]] | None = None,
    built: str = "",
    hero_aoi: str = HERO_AOI,
    hero_place: str = "the Ahr valley",
    hero_small: str = "Bad Neuenahr-Ahrweiler, first satellite map; residents from the GHS-POP 2020 (E2020) model.",
    front: Sequence[str] | None = None,
) -> str:
    """The whole page, top to bottom in the order of the argument.

    Placeholders in square brackets are left for the team to fill on the day.
    """
    places = place_records(products, first_key=front or hero_aoi)
    layers = place_layers or {}
    shares = outside_shares(countries)
    eu = europe_shares(exposure)
    named = {k for k, _ in NAMED_PLACES}
    unreported_note = ""
    if unreported and unreported[1]:
        unreported_note = (
            f'<p class="small"><b>Not in the European risk-area layer ({esc(unreported[0])} '
            f'cycle): {esc(", ".join(unreported[1]))}.</b> The States designated the areas '
            "but did not report them to the EU layer.</p>")

    def slot(text: str) -> str:
        return f'<span class="slot">{esc(text)}</span>' if text.startswith("[") else esc(text)

    def button(p):
        return f'<button type="button" data-key="{esc(p["key"])}">{esc(p["label"])}</button>'

    main_buttons = "".join(button(p) for p in places if p["key"] in named)
    more_buttons = "".join(button(p) for p in places if p["key"] not in named)
    figures = "".join(
        f'<div class="place" data-key="{esc(p["key"])}">{story_map_html(p, layers.get(p["key"]))}</div>'
        for p in places)
    facts = "".join(_facts_html(p) for p in places)
    legend = "".join(f'<li><span class="sw" style="background:{c}"></span>{esc(t)}</li>'
                     for c, t in RASTER_CLASSES)
    pixel = next((l.get("pixel_m") for l in layers.values() if l.get("pixel_m")), None)
    places_json = json.dumps([{k: p[k] for k in ("key", "label", "residents", "share",
                                                 "residential", "destroyed")}
                              for p in places]).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · {TEAM}</title>
<style>{CSS}</style></head>
<body><main>
<header><h1>{slot(title)}</h1>
<p class="question">{slot(question)}</p></header>

{_hero_html(hero(products, countries, exposure, hero_aoi=hero_aoi, place_name=hero_place, place_small=hero_small))}
{_strip_html(country_strip(countries))}
{_combined_html(combined_reached(countries))}
<h2><span class="kicker">Before the water</span>From the forecast to the first drop</h2>
{_before_the_water_html()}

<details><summary>How we counted</summary><ul>{"".join(f"<li>{x}</li>" for x in HOW_WE_COUNTED)}</ul></details>

<h2><span class="kicker">The story map</span>Where the water went, and where the map expected it</h2>
<div class="places" role="group" aria-label="Choose a place">{main_buttons}</div>
<div class="places more" role="group" aria-label="Other mapped places">{more_buttons}</div>
<div class="story"><div>{figures}
<ul class="maplegend">{legend}</ul>
<p class="small">The colours show where the water was; the percentage counts people, and people live unevenly
along a valley, so the two need not match. Each pixel is about {fmt_count(pixel)} m across; a pixel with any water seen is drawn as water.
The dashed line is the area Copernicus mapped; beyond it nothing is known.</p></div>
<div>{facts}{locator_svg(locator, places)}</div></div>

<h2><span class="kicker">Three countries</span>{esc(chart_heading(shares))}</h2>
{chart_html(shares)}
<p class="small">Share of the residents the water reached (first satellite maps) who lived outside the JRC
flood map. The bigger the flood a map assumes, the more it covers, so the share falls from the 1-in-10 to
the 1-in-500-year map; what stays outside even the 1-in-500 map is water the map does not model.</p>
<h3 class="sub">Was the map right, by area?</h3>
{_agreement_html(map_agreement(countries))}
<p class="small">The share of the observed flood <b>area</b> (first maps) that fell inside the 1-in-100-year zone,
in the 1-in-500 zone only, or outside both — the cell-weighted agreement with the JRC map. The chart above
counts people; this counts flooded ground, so a place with much water but few residents still shows how much
the map missed. "Outside both" mixes flooding beyond the modelled hazard with rivers too small to be modelled
(catchment below the ~150 km² floor).</p>

<h2><span class="kicker">Europe</span>Is July 2021 a one-off?</h2>
<div class="europe"><div>{europe_svg(europe_features, eu)}</div>
<div>{europe_text(eu, exposure)}{europe_legend(eu)}
<p class="small">Share of each region's residents inside the zone a 1-in-100-year river flood would reach
if there were no dikes (JRC hazard map, GHS-POP 2025, E2025). Protected low-lying areas, such as much of the
Netherlands, therefore show high. Grey is not measured, not zero.</p>{unreported_note}</div></div>

<h2><span class="kicker">Read before acting</span>Warnings</h2>
{_warnings_html()}

<h2><span class="kicker">What we recommend</span>Three recommendations: two before the rain, one by the {PLAN_REVIEW_DATE_SHORT} plan review</h2>
<table class="recos"><thead><tr><th>Action</th><th>Who, by when</th><th>Instrument, cost</th></tr></thead><tbody>
<tr class="reco"><td><b>1.</b> {slot(recommendation)}</td><td>{slot(actor)}</td><td>{slot(instrument)}</td></tr>
{"".join(f'<tr><td><b>{i}.</b> {esc(what)}</td><td>{esc(who)}</td><td>{esc(how)}</td></tr>' for i, (what, who, how) in enumerate(RECOMMENDATIONS, 2))}
</tbody></table>

<h2><span class="kicker">Next steps on the ground</span>What to do next, grounded in the gaps above</h2>
{_next_steps_html()}

<h2><span class="kicker">Context</span>What has been done since July 2021</h2>
{_since_html()}
<h2><span class="kicker">In one paragraph</span>Conclusion</h2>
<p class="conclusion">{esc(CONCLUSION)}</p>

<h2><span class="kicker">Read with care</span>What this cannot tell you</h2>
<ul class="limits">{"".join(f"<li>{item}</li>" for item in LIMITS)}</ul>

<footer>
<p><b>Sources.</b></p><ul>{"".join(f"<li>{esc(s)}</li>" for s in SOURCES)}</ul>
<p>Every number on this page is read from the team's computed tables by a script, except dates, the
Directive's own terms, the recommendations and the per-place cards: their shelter figures are copied from the team's Q3 table
(shelter_access.csv) and their "since 2021" lines from the cited public sources. This file is static: it calls no AI service and loads nothing from the
internet. {esc(built)}</p>
<p><b>{TEAM}</b></p>
</footer>
</main>
<script type="application/json" id="places">{places_json}</script>
<script>{JS}</script>
</body></html>
"""
