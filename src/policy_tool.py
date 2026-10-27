"""The challenge "policy tool": one static HTML page for the July 2021 flood.

Annex 4 of the European AI Challenge asks for a file that is e-mailed, then shown
in a five-minute demo, and Annex 3 forbids the tool from calling any AI service.
So this module renders ONE self-contained HTML string - inline CSS, inline SVG,
inline PNG maps as data URIs and a few lines of inline JS for the place selector
- that opens by double-click with the network off. `scripts/build_policy_tool.py`
reads the files, rasterises the maps and calls `render_page`; everything here is
pure, so the tests run on synthetic tables.

The page is an argument, top to bottom: four numbers that say why act (the map
missed people, the harm, not a one-off, the date to act by), a story map per
flooded place showing where the water went against where the 1-in-100-year map
expected it, the same comparison per country, Europe for context, then the
recommendation and the limits.

Rules the page follows, and why:

- **Every figure is read from a table, never typed.** The formatters take the
  table value and nothing else, and each hero number carries its raw value in a
  `data-value` attribute so a test (or a juror with dev tools) can check the
  rounding against the source. The one exception is a legal date, quoted with
  its article in the footer.
- **A missing figure prints "n/a", never 0.** Belgium and the Netherlands have
  no graded (GRA) products, so no damage grades: 0 destroyed would state that
  nothing was destroyed there, which nobody measured.
- **Rounding is honest.** Residents are a model (GHS-POP weighted by flooded
  cell share), shown to three significant figures; building points are counted
  and shown exactly. A share put into words ("about half") always prints its
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
TEAM = "Team N"
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

#: NUTS country codes of the EU-27, for the Europe-wide headcount.
EU27 = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR",
    "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
})

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
    """Residents, rounded to what a population model can support.

    Three significant figures from 1,000 up, the nearest 10 from 100 up, whole
    people below that. A GHS-POP figure weighted by flooded cell share is not
    known to the person, and printing "32,561" would claim it is.
    """
    if _missing(value):
        return NA
    v = float(value)
    if abs(v) < 100:
        return f"{round(v):,}"
    if abs(v) < 1000:
        return f"{int(round(v, -1)):,}"
    digits = 3 - int(math.floor(math.log10(abs(v)))) - 1
    return f"{int(round(v, digits)):,}"


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
         exposure: pd.DataFrame) -> list[dict[str, Any]]:
    """The four numbers of the argument: missed, harm, not a one-off, when.

    Each is (id, big text, raw value, plain line, small print). The raw value
    is what the test compares with the table; the date has none, since it is
    law, not data.
    """
    ahr = first_pass(products).get(HERO_AOI)
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
         "line": (f"{share_words(ahr_share).capitalize()} of the people the July 2021 water reached in the Ahr valley lived OUTSIDE "
                  f"the European 1-in-100-year flood zone: {fmt_people(ahr_out)} of "
                  f"{fmt_people(ahr_res)} residents."),
         "small": "Bad Neuenahr-Ahrweiler, first satellite map; residents from the GHS-POP 2020 model."},
        {"id": "harm", "big": fmt_count(destroyed), "raw": destroyed,
         "line": (f"buildings graded destroyed in Germany. The water reached about "
                  f"{fmt_people(de_res)} residents there; {fmt_people(de_out)} of them lived "
                  f"outside the 1-in-100-year zone."),
         "small": (f"Copernicus damage grading, first maps only; later maps of the same areas "
                   f"bring it to {fmt_count(destroyed_later)}. Only German areas were graded.")},
        {"id": "europe", "big": fmt_millions(eu), "raw": eu,
         "line": "people in the EU live inside the 1-in-100-year river flood zone. July 2021 was not a one-off risk.",
         "small": "JRC hazard map without dikes, GHS-POP population, all EU-27 regions."},
        {"id": "when", "big": PLAN_REVIEW_DATE_SHORT, "raw": None,
         "line": "is when every Member State must review its flood risk management plans: the next window to act.",
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


def place_records(products: pd.DataFrame) -> list[dict[str, Any]]:
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
        })
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
    return (
        f'<div class="stage" style="aspect-ratio:{w}/{h};width:min(100%,calc(75vh * {w / h:.3f}))">'
        f'<img alt="Water seen in {esc(place["label"])}, inside and outside the 1-in-100-year zone" '
        f'src="{layer["png"]}" width="{w}" height="{h}">'
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
        f'<path class="nutsl" d="{layer.get("nuts", "")}"/>'
        f'<path class="outline" d="{layer.get("outline", "")}"/>'
        f'{towns}{scale}</svg></div>')


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
    "<b>Satellite snapshots, not the peak.</b> Copernicus maps show the water visible "
    "on one image, often a day or more after the crest. The true extent was larger.",
    "<b>Outside a mapped area means not mapped, not dry.</b> Only the outlined areas "
    "were mapped; whole flooded valleys lie outside them.",
    "<b>Two kinds of maps.</b> Delineation maps, drawn semi-automatically from radar, "
    "stop at building walls and miss water between houses; grading maps, drawn by "
    "analysts, carry the water through the towns. Belgium has only delineation maps, "
    "which is why its building count is low.",
    "<b>Population is a model.</b> GHS-POP 2020 (E2020) spreads residents evenly within "
    "each ~1 km cell; it does not know who was home in July 2021.",
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
    "Population: GHS-POP R2023A, epoch 2020 (E2020), JRC, © European Union.",
    "Boundaries: GISCO NUTS 2024, © EuroGeographics for the administrative boundaries.",
    PLAN_REVIEW_SOURCE,
)

HOW_WE_COUNTED: tuple[str, ...] = (
    "<b>The water</b> is what Copernicus EMS outlined as flooded area or flood trace on "
    "its first map of each area (EMSR517/518/520). Later monitoring maps add water "
    "seen days afterwards; they are shown as small print, never mixed into a headline.",
    "<b>Residents</b> are GHS-POP 2020 counts, each ~1 km cell weighted by the share of "
    "it under the observed water, on a 20 m equal-area grid (EPSG:3035).",
    "<b>Outside the 1-in-100-year zone</b> means the 20 m cell is dry in the JRC river "
    "flood hazard map for that return period (depth 0 or no data).",
    "<b>Buildings</b> are GHS-OBAT points inside the observed water; \"destroyed\" is "
    "the Copernicus analysts' damage grade, available only for German grading maps.",
    "<b>Country totals</b> are counted on the union of the areas, cell by cell and "
    "building by building, so two maps over the same valley are not counted twice.",
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
.reco{border:3px solid var(--ink);padding:16px 18px;font-size:1.2rem}
.limits{columns:2 340px;column-gap:32px;padding:16px 20px;margin:0;list-style:none;background:#fffaf0;border:1px solid #d8c48a}
.limits li{break-inside:avoid;margin:0 0 .7em;font-size:.9rem}
footer{margin-top:3em;border-top:1px solid var(--line);padding-top:10px;font-size:.78rem;color:var(--muted)}
footer ul{padding-left:1.1em}
@media print{
body{font-size:11pt}main{max-width:none;padding:0}
.places,.toggle,details summary{display:none}
details{display:block}details>*{display:block}
h2{break-after:avoid;margin-top:1.4em}
.hero,.story,.europe,.reco,.limits,.chart{break-inside:avoid}
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
             "europe": "Not a one-off", "when": "The window to act"}
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
    return (f'<div class="facts" data-key="{esc(p["key"])}">'
            f'<h3>{esc(p["label"])}</h3>'
            f'<div class="fig"><div class="n">{esc(f["residents"])}</div>residents reached by the water '
            f'({esc(f["km2"])} km² seen)</div>'
            f'<div class="fig"><div class="n out">{esc(f["share"])}</div>of them lived outside the '
            f'1-in-100-year zone ({esc(f["share_words"])})</div>'
            f'<div class="fig"><div class="n">{esc(f["residential"])}</div>homes in the water '
            f'({esc(f["buildings"])} buildings in all)</div>{destroyed}'
            f'<p class="small">{esc(p["country"])} · {esc(p["key"])} · first satellite map; {kind}.</p>'
            f'{later}</div>')


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
    built: str = "",
) -> str:
    """The whole page, top to bottom in the order of the argument.

    Placeholders in square brackets are left for the team to fill on the day.
    """
    places = place_records(products)
    layers = place_layers or {}
    shares = outside_shares(countries)
    eu = europe_shares(exposure)
    named = {k for k, _ in NAMED_PLACES}

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

{_hero_html(hero(products, countries, exposure))}
{_strip_html(country_strip(countries))}
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

<h2><span class="kicker">Europe</span>Is July 2021 a one-off?</h2>
<div class="europe"><div>{europe_svg(europe_features, eu)}</div>
<div>{europe_text(eu, exposure)}{europe_legend(eu)}
<p class="small">Share of each region's residents inside the zone a 1-in-100-year river flood would reach
if there were no dikes (JRC hazard map, GHS-POP). Protected low-lying areas, such as much of the
Netherlands, therefore show high. Grey is not measured, not zero.</p></div></div>

<h2><span class="kicker">What we recommend</span>Recommendation</h2>
<div class="reco">{slot(recommendation)} — addressed to {slot(actor)}</div>

<h2><span class="kicker">Read with care</span>What this cannot tell you</h2>
<ul class="limits">{"".join(f"<li>{item}</li>" for item in LIMITS)}</ul>

<footer>
<p><b>Sources.</b></p><ul>{"".join(f"<li>{esc(s)}</li>" for s in SOURCES)}</ul>
<p>Every number on this page is read from the team's computed tables by a script; none is typed by hand,
except the legal date above. This file is static: it calls no AI service and loads nothing from the
internet. {esc(built)}</p>
<p><b>{TEAM}</b></p>
</footer>
</main>
<script type="application/json" id="places">{places_json}</script>
<script>{JS}</script>
</body></html>
"""
