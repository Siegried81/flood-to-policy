"""The challenge "policy tool": one static HTML page for the July 2021 flood.

Annex 4 of the European AI Challenge asks for a file that is e-mailed, then shown
in a five-minute demo, and Annex 3 forbids the tool from calling any AI service.
So this module renders ONE self-contained HTML string - inline CSS, inline SVG,
a few lines of inline JS for the click-to-zoom - that opens by double-click with
the network off. `scripts/build_policy_tool.py` reads the files and the geometry
and calls `render_page`; everything here is pure, so the tests run on synthetic
tables.

Rules the page follows, and why:

- **Every figure is read from a table, never typed.** The formatters below take
  the table value and nothing else, and each headline carries its raw value in a
  `data-value` attribute so a test (or a sceptical juror with dev tools) can
  check the rounding against the source.
- **A missing figure prints "n/a", never 0.** Belgium and the Netherlands have
  no graded (GRA) products, so they have no damage grades; writing 0 destroyed
  would state that nothing was destroyed there, which nobody measured.
- **Rounding is honest.** Residents are a model (GHS-POP weighted by flooded
  cell share), so they are shown to three significant figures and said to be
  rounded; building points are counted, so they are shown exactly.
- **No link anywhere.** Sources are cited as text: Annex 3 and 7 forbid a repo
  link, and a page that fetches nothing cannot break on a venue network.
- **Readable in greyscale and by colour-blind readers.** Every colour pair on
  the page differs in lightness as well as hue, and the chart prints its values
  beside the bars rather than relying on the colour key.
"""

from __future__ import annotations

import html
import json
import math
from typing import Any, Iterable, Sequence

import pandas as pd

from src import svgmap

NA = "n/a"
TEAM = "Team N"
HEADLINE_BASIS = "product"
COUNTRIES = ("BE", "DE", "NL")
COUNTRY_NAMES = {"BE": "Belgium", "DE": "Germany", "NL": "Netherlands"}
CHART_RPS = (10, 100, 500)

# Lightness-ordered blues: the observed water is the darkest mark on the event
# map, so it stays the darkest grey when printed in black and white.
FLOOD_FILL = "#08519c"
MONIT_FILL = "#9ecae1"
AOI_STROKE = "#d95f02"
CHART_FILLS = {10: "#c6dbef", 100: "#4292c6", 500: "#08306b"}


# --- formatting -------------------------------------------------------------

def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


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


def fmt_share(value: Any) -> str:
    """A 0-1 share as a whole percentage; "<1%" rather than a misleading "0%"."""
    if _missing(value):
        return NA
    pct = float(value) * 100
    if 0 < pct < 0.5:
        return "<1%"
    return f"{pct:.0f}%"


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


def headlines(countries: pd.DataFrame) -> list[dict[str, Any]]:
    """The four headline cards: label, scope, and per-country (raw, shown) values.

    Read from `event_2021_countries`, which is deduplicated cell by cell and
    building by building across products, so two AOIs over the Ahr are not
    counted twice - which a sum over the products table would do.
    """
    first = country_rows(countries, HEADLINE_BASIS)
    later = country_rows(countries, "product_and_monit")

    def per_country(column: str, fmt, rows=first) -> list[dict[str, Any]]:
        out = []
        for iso in COUNTRIES:
            raw = rows[iso][column] if iso in rows and column in rows[iso] else None
            raw = None if _missing(raw) else float(raw)
            out.append({"country": iso, "raw": raw, "shown": fmt(raw)})
        return out

    return [
        {
            "id": "residents",
            "label": "Residents inside the observed flood extent",
            "values": per_country("residents_observed", fmt_people),
            "scope": ("GHS-POP 2020 population model, rounded; inside the areas "
                      "Copernicus EMS mapped on its first pass only. With the later "
                      "monitoring passes: "
                      + ", ".join(f"{v['country']} {v['shown']}" for v in
                                  per_country("residents_observed", fmt_people, later))
                      + "."),
        },
        {
            "id": "outside_rp100",
            "label": "...of whom live OUTSIDE the JRC 1-in-100-year flood map",
            "values": per_country("share_residents_outside_rp100", fmt_share),
            "scope": ("Share of those residents outside the JRC river-flood hazard "
                      "map for a 100-year flood (undefended). The map covers rivers "
                      "with catchments of 150 km² and more, not runoff."),
        },
        {
            "id": "buildings",
            "label": "Buildings inside the observed flood extent",
            "values": per_country("buildings_observed", fmt_count),
            "scope": ("GHS-OBAT building points inside the mapped water, first pass. "
                      "A floor where radar maps stop at walls: within 25 m of the "
                      "water the counts are "
                      + ", ".join(f"{v['country']} {v['shown']}" for v in
                                  per_country("buildings_within_25m_of_observed", fmt_count))
                      + "."),
        },
        {
            "id": "destroyed",
            "label": "Buildings graded destroyed",
            "values": per_country("graded_destroyed", fmt_count),
            "scope": ("Copernicus EMS damage grading, by analysts on imagery, first "
                      "pass; only German areas were graded, so Belgium and the "
                      "Netherlands are n/a (not measured), not zero. Graded damaged: "
                      + ", ".join(f"{v['country']} {v['shown']}" for v in
                                  per_country("graded_damaged", fmt_count))
                      + "."),
        },
    ]


def aoi_key(emsr: str, aoi: str) -> str:
    """`EMSR517_AOI15`: one mapped area, whatever pass or product type."""
    aoi = str(aoi)
    return f"{emsr}_{aoi if aoi.startswith('AOI') else 'AOI' + aoi}"


def _panel_figures(row: pd.Series | None) -> dict[str, str]:
    if row is None:
        return {}
    graded = str(row.get("product_type")) == "GRA"
    out = {
        "Observed water": f"{fmt_km2(row.get('observed_km2'))} km²",
        "Residents in it": fmt_people(row.get("residents_observed")),
        "Outside the 100-year map": fmt_share(row.get("share_residents_outside_rp100")),
        "Buildings in it": fmt_count(row.get("buildings_observed")),
        "  residential": fmt_count(row.get("residential_buildings_observed")),
        "  non-residential": fmt_count(row.get("non_residential_buildings_observed")),
        "Graded destroyed": fmt_count(row.get("graded_destroyed")) if graded else NA,
        "Graded damaged": fmt_count(row.get("graded_damaged")) if graded else NA,
        "Graded possibly damaged": (fmt_count(row.get("graded_possibly_damaged"))
                                    if graded else NA),
    }
    return out


def aoi_records(products: pd.DataFrame) -> list[dict[str, Any]]:
    """One record per AOI: its first-pass figures and, if any, its monitoring pass.

    Pre-formatted here so the page's JavaScript only inserts strings: one
    formatter, in Python, for every number on the page.
    """
    records = []
    for (emsr, aoi), group in products.groupby(["emsr", "aoi"], sort=False):
        first = group[group["product_kind"] == "PRODUCT"]
        monit = group[group["product_kind"] != "PRODUCT"]
        row = first.iloc[0] if len(first) else group.iloc[0]
        records.append({
            "key": aoi_key(emsr, aoi),
            "country": str(row["country"]),
            "locality": str(row.get("locality", "")),
            "type": str(row.get("product_type", "")),
            "method": str(row.get("detection_method", "")),
            "residents_raw": None if _missing(row.get("residents_observed"))
                             else float(row["residents_observed"]),
            "first": _panel_figures(row if len(first) else None),
            "monit": _panel_figures(monit.iloc[-1]) if len(monit) else {},
            "monit_id": str(monit.iloc[-1]["product_id"]) if len(monit) else "",
        })
    order = {c: i for i, c in enumerate(COUNTRIES)}
    records.sort(key=lambda r: (order.get(r["country"], 9), -(r["residents_raw"] or 0)))
    return records


def outside_shares(countries: pd.DataFrame) -> dict[str, dict[int, float | None]]:
    """Share of residents outside the RP10/100/500 maps, per country, first pass."""
    first = country_rows(countries, HEADLINE_BASIS)
    out: dict[str, dict[int, float | None]] = {}
    for iso in COUNTRIES:
        row = first.get(iso)
        out[iso] = {}
        for rp in CHART_RPS:
            col = f"share_residents_outside_rp{rp}"
            raw = None if row is None or col not in row or _missing(row[col]) else float(row[col])
            out[iso][rp] = raw
    return out


def europe_shares(exposure: pd.DataFrame, return_period: int = 100) -> dict[str, float | None]:
    """Share of residents in the hazard zone per NUTS3: `exposed_pop / total_pop`.

    The rule the kit's UIs already apply (`app/streamlit_app.py`, `api/main.py`):
    one return period, the share rather than the headcount, NaN kept as None so
    the map paints it "not measured" rather than zero. The table is the
    undefended map: dikes are not in it.
    """
    view = exposure[exposure["return_period"] == return_period]
    out: dict[str, float | None] = {}
    for code, num, den in zip(view["nuts_id"], view["exposed_pop"], view["total_pop"]):
        out[str(code)] = None if _missing(num) or _missing(den) or not den else float(num) / float(den)
    return out


def europe_caption(shares: dict[str, float | None], exposure: pd.DataFrame,
                   reference: str = "DEB12", threshold: float = 0.10) -> str:
    """Plain words for the Europe map, every number counted from `shares`."""
    measured = sorted(v for v in shares.values() if v is not None)
    if not measured:
        return "No region has a measured share in this table."
    median = measured[(len(measured) - 1) // 2]
    above = sum(v >= threshold for v in measured)
    text = (f"Of {len(measured):,} measured regions, {above:,} have {fmt_share(threshold)} "
            f"or more of their residents inside the 1-in-100-year flood zone; the "
            f"median region has {fmt_share(median)}.")
    ref = shares.get(reference)
    if ref is not None:
        names = exposure.loc[exposure["nuts_id"] == reference, "region"]
        name = str(names.iloc[0]) if len(names) else reference
        higher = sum(v > ref for v in measured)
        text += (f" {esc(name)} ({reference}), where the Ahr flooded, has "
                 f"{fmt_share(ref)}: {higher:,} regions rank higher on this map.")
    return text


# --- SVG ----------------------------------------------------------------------

def path_d(geometry: dict[str, Any], to_xy) -> str:
    """SVG path data for a GeoJSON Polygon/MultiPolygon, rings via `svgmap._rings`.

    `to_xy` maps a coordinate pair to viewBox units. Points that round onto the
    previous one are dropped, which is most of the size saving at 10 m precision.
    """
    parts = []
    for ring in svgmap._rings(geometry):
        pts: list[str] = []
        for p in ring:
            x, y = to_xy(float(p[0]), float(p[1]))
            s = f"{x:.2f} {y:.2f}"
            if not pts or pts[-1] != s:
                pts.append(s)
        if len(pts) >= 3:
            parts.append("M" + "L".join(pts) + "Z")
    return "".join(parts)


def event_map_svg(layers: dict[str, Any], records: Sequence[dict[str, Any]]) -> str:
    """The event map: NUTS3 context, country borders, observed water, AOI outlines.

    `layers` carries geometry already projected to EPSG:3035 metres as GeoJSON
    dicts: `bounds` (minx, miny, maxx, maxy), `nuts` (list of (id, geom)),
    `borders` (list of geom), `labels` (list of (text, x, y)), `monit` and
    `observed` (list of geom), `aoi` (dict key -> geom). The viewBox is in
    kilometres from the top-left, so a click-to-zoom is a viewBox change and
    stroke widths stay put through `vector-effect`.
    """
    minx, miny, maxx, maxy = layers.get("bounds", (0.0, 0.0, 1000.0, 1000.0))
    w, h = (maxx - minx) / 1000, (maxy - miny) / 1000

    def to_xy(x: float, y: float) -> tuple[float, float]:
        return (x - minx) / 1000, (maxy - y) / 1000

    known = {r["key"]: r for r in records}
    out = [f'<svg id="eventmap" viewBox="0 0 {w:.2f} {h:.2f}" data-home="0 0 {w:.2f} {h:.2f}" '
           'role="img" aria-label="Map of the July 2021 flood: observed water and mapped areas">',
           f'<rect x="0" y="0" width="{w:.2f}" height="{h:.2f}" class="sea"/>']
    out.append('<g class="nuts">' + "".join(
        f'<path d="{path_d(g, to_xy)}"><title>{esc(code)}</title></path>'
        for code, g in layers.get("nuts", [])) + "</g>")
    out.append('<g class="borders">' + "".join(
        f'<path d="{path_d(g, to_xy)}"/>' for g in layers.get("borders", [])) + "</g>")
    out.append(f'<g class="monit" fill="{MONIT_FILL}">' + "".join(
        f'<path d="{path_d(g, to_xy)}"/>' for g in layers.get("monit", [])) + "</g>")
    out.append(f'<g class="observed" fill="{FLOOD_FILL}">' + "".join(
        f'<path d="{path_d(g, to_xy)}"/>' for g in layers.get("observed", [])) + "</g>")
    for text, x, y in layers.get("labels", []):
        cx, cy = to_xy(x, y)
        out.append(f'<text class="country" x="{cx:.1f}" y="{cy:.1f}">{esc(text)}</text>')
    aois = []
    for key, g in layers.get("aoi", {}).items():
        rec = known.get(key)
        name = rec["locality"] if rec else key
        aois.append(f'<path class="aoi" data-aoi="{esc(key)}" tabindex="0" stroke="{AOI_STROKE}" '
                    f'd="{path_d(g, to_xy)}"><title>{esc(name)} ({esc(key)})</title></path>')
    out.append('<g class="aois">' + "".join(aois) + "</g>")
    out.append("</svg>")
    return "".join(out)


def hazard_chart_svg(shares: dict[str, dict[int, float | None]]) -> str:
    """Grouped horizontal bars: share of residents outside each hazard map.

    Values are printed beside each bar and every bar is labelled with its
    return period, so the chart reads without the colours. A missing share
    draws no bar and prints n/a.
    """
    bar_h, gap, group_gap, left, width = 22, 4, 22, 150, 520
    rows = []
    y = 10
    for iso in COUNTRIES:
        rows.append(f'<text x="0" y="{y + 1.5 * bar_h + gap:.0f}" class="ctry">'
                    f'{esc(COUNTRY_NAMES[iso])}</text>')
        for rp in CHART_RPS:
            raw = shares.get(iso, {}).get(rp)
            bw = 0 if raw is None else max(raw, 0) * width
            rows.append(
                f'<text x="{left - 6}" y="{y + bar_h - 6}" class="rp" text-anchor="end">'
                f'1-in-{rp}</text>'
                f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{bar_h}" '
                f'fill="{CHART_FILLS[rp]}" stroke="#333" stroke-width="0.5" data-value="{raw}"/>'
                f'<text x="{left + bw + 6:.1f}" y="{y + bar_h - 6}" class="val">{fmt_share(raw)}</text>')
            y += bar_h + gap
        y += group_gap
    axis = (f'<line x1="{left}" y1="4" x2="{left}" y2="{y - group_gap + 4}" stroke="#333"/>'
            f'<text x="{left + width}" y="{y + 6}" class="rp" text-anchor="end">100% of residents</text>')
    return (f'<svg viewBox="0 0 {left + width + 60} {y + 12}" role="img" '
            'aria-label="Share of flooded residents outside each hazard map, by country">'
            + "".join(rows) + axis + "</svg>")


# --- page ------------------------------------------------------------------------

LIMITS: tuple[str, ...] = (
    "<b>Satellite snapshots, not the peak.</b> Copernicus EMS maps show the water "
    "visible on one image, often a day or more after the crest. The true extent "
    "was larger.",
    "<b>Outside a mapped area means not mapped, not dry.</b> Only the outlined "
    "areas were mapped; whole flooded valleys lie outside them.",
    "<b>Two kinds of maps.</b> Delineation (DEL) maps, drawn semi-automatically "
    "from radar, stop at building walls, so they miss water between houses; "
    "grading (GRA) maps, drawn by analysts, carry the water through the towns. "
    "Belgium has only DEL maps, which is why its building count is low.",
    "<b>Population is a model.</b> GHS-POP 2020 (E2020) spreads residents evenly "
    "within each ~1 km cell; it does not know who was home in July 2021.",
    "<b>Hazard maps cover large rivers only.</b> The JRC maps model rivers with "
    "catchments of 150 km² and more, without dikes, and no surface runoff or "
    "small streams: much of the 2021 damage came from exactly those.",
    "<b>Permanent water is excluded from the map scores</b> (it is wet in every "
    "map and would count as a free hit); residents beside it are still counted.",
)

SOURCES: tuple[str, ...] = (
    "Flood hazard: JRC / Copernicus EMS river flood hazard maps for Europe "
    "(v3.1.1, return periods 10 to 500 years), © European Union, CC BY 4.0.",
    "Observed flood and damage grading: Copernicus Emergency Management Service "
    "Rapid Mapping, activations EMSR517 (Germany), EMSR518 (Belgium), EMSR520 "
    "(Netherlands), July 2021, © European Union.",
    "Buildings: GHS-OBAT R2024A (epoch 2020), JRC, © European Union.",
    "Population: GHS-POP R2023A, epoch 2020 (E2020), JRC, © European Union.",
    "Boundaries: GISCO NUTS 2024, © EuroGeographics for the administrative boundaries.",
)

CSS = """
:root{--ink:#1f2328;--muted:#555;--line:#c9ccd1;--paper:#ffffff;--soft:#f4f5f2;
--accent:#d95f02;--flood:#08519c}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:18px/1.45 "Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:1240px;margin:0 auto;padding:24px 16px 40px}
h1{font-size:2rem;margin:0 0 .2em}
h2{font-size:1.3rem;margin:1.6em 0 .4em;border-bottom:2px solid var(--ink);padding-bottom:.15em}
.question{font-size:1.25rem;color:var(--muted);margin:0 0 1em}
.slot{background:#fff4d6;border:1px dashed #8a6d00;padding:0 .3em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.card{border:1px solid var(--line);border-left:6px solid var(--flood);padding:10px 12px;background:var(--soft)}
.card h3{font-size:.95rem;margin:0 0 6px;font-weight:600}
.card .nums{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:6px}
.card .num{font-size:1.7rem;font-weight:700;line-height:1.1}
.card .num small{display:block;font-size:.75rem;font-weight:400;color:var(--muted)}
.scope{font-size:.78rem;color:var(--muted)}
.mapwrap{display:grid;grid-template-columns:minmax(0,2.2fr) minmax(0,1fr);gap:14px;align-items:start}
@media (max-width:900px){.mapwrap{grid-template-columns:1fr}}
#eventmap{width:100%;height:auto;display:block;border:1px solid var(--line);background:#eef3f7}
#eventmap .sea{fill:#eef3f7}
#eventmap .nuts path{fill:#f7f7f2;stroke:#b8bcc2;stroke-width:.6;vector-effect:non-scaling-stroke}
#eventmap .borders path{fill:none;stroke:#444;stroke-width:1.6;vector-effect:non-scaling-stroke}
#eventmap .observed path{stroke:#08519c;stroke-width:1.2;vector-effect:non-scaling-stroke}
#eventmap .monit path{stroke:#9ecae1;stroke-width:1.2;vector-effect:non-scaling-stroke}
#eventmap .country{font-size:6px;fill:#666;letter-spacing:.15em;text-anchor:middle;
font-weight:600;pointer-events:none}
#eventmap .aoi{fill:rgba(217,95,2,.04);stroke-width:2;stroke-dasharray:6 3;
vector-effect:non-scaling-stroke;cursor:pointer}
#eventmap .aoi:hover,#eventmap .aoi:focus,#eventmap .aoi.on{stroke:#000;stroke-width:3.5;
stroke-dasharray:none;fill:rgba(217,95,2,.12);outline:none}
body.hide-monit #eventmap .monit{display:none}
#eventmap.zoomed .country{display:none}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:.85rem;margin:6px 0}
.sw{display:inline-block;width:16px;height:12px;vertical-align:-1px;margin-right:5px;border:1px solid #333}
.panel{border:1px solid var(--line);padding:10px 12px;background:var(--soft);min-height:200px}
.panel h3{margin:0 0 4px;font-size:1.1rem}
.panel table{border-collapse:collapse;width:100%;font-size:.9rem}
.panel td{padding:2px 4px;border-bottom:1px solid #e1e3e6}
.panel td:nth-child(n+2){text-align:right;font-variant-numeric:tabular-nums}
.panel th{text-align:right;font-size:.75rem;color:var(--muted);font-weight:600}
.aoilist{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.aoilist button{font:inherit;font-size:.78rem;padding:2px 6px;border:1px solid #888;background:#fff;cursor:pointer}
.aoilist button.on{background:#000;color:#fff}
.controls button,.controls label{font:inherit;font-size:.85rem}
.controls button{padding:3px 10px;border:1px solid #444;background:#fff;cursor:pointer}
.chart svg{width:100%;max-width:760px;height:auto;display:block}
.chart .ctry{font-size:15px;font-weight:700;fill:#1f2328}
.chart .rp,.chart .val{font-size:13px;fill:#1f2328}
.europe svg{max-width:900px;margin:0 auto}
.europe .lg{fill:#374151 !important}
.reco{border:3px solid var(--ink);padding:14px 16px;font-size:1.2rem;background:#fff}
.limits{border:2px solid #8a6d00;background:#fffaf0;padding:10px 16px}
.limits li{margin:.3em 0;font-size:.92rem}
footer{margin-top:2em;border-top:1px solid var(--line);padding-top:8px;font-size:.78rem;color:var(--muted)}
footer li{margin:.15em 0}
@media print{body{font-size:12pt}.controls,.aoilist{display:none}main{max-width:none}
h2{break-after:avoid}.card,.panel,.limits,.reco,svg{break-inside:avoid}}
"""

JS = """
(function(){
var svg=document.getElementById('eventmap');if(!svg)return;
var data=JSON.parse(document.getElementById('aoidata').textContent);
var byKey={};data.forEach(function(r){byKey[r.key]=r;});
var panel=document.getElementById('panel');var home=svg.getAttribute('data-home');
var anim=null;
function setBox(target){var from=svg.getAttribute('viewBox').split(' ').map(Number);
var to=target.split(' ').map(Number);var t0=null;svg.classList.toggle('zoomed',target!==home);if(anim)cancelAnimationFrame(anim);
function step(ts){if(!t0)t0=ts;var k=Math.min(1,(ts-t0)/450);k=k*(2-k);
svg.setAttribute('viewBox',from.map(function(v,i){return (v+(to[i]-v)*k).toFixed(2);}).join(' '));
if(k<1)anim=requestAnimationFrame(step);}anim=requestAnimationFrame(step);}
function row(label,a,b){return '<tr><td>'+label.replace(/^  /,'&nbsp;&nbsp;&middot; ')+'</td><td>'+a+'</td>'+(b===undefined?'':'<td>'+b+'</td>')+'</tr>';}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function show(key,zoom){var r=byKey[key];if(!r)return;
document.querySelectorAll('.aoi.on,.aoilist button.on').forEach(function(e){e.classList.remove('on');});
document.querySelectorAll('[data-aoi="'+key+'"]').forEach(function(e){e.classList.add('on');});
var hasM=Object.keys(r.monit).length>0;
var h='<h3>'+esc(r.locality)+'</h3><div class="scope">'+esc(r.key)+' &middot; '+esc(r.country)+' &middot; '+
(r.type==='GRA'?'grading map (analysts, water drawn through streets)':'delineation map ('+esc(r.method.toLowerCase())+')')+'</div>';
h+='<table>'+(hasM?'<tr><th></th><th>first pass</th><th>later pass</th></tr>':'');
Object.keys(r.first).forEach(function(k){h+=row(k,esc(r.first[k]),hasM?esc(r.monit[k]):undefined);});
h+='</table>';if(hasM)h+='<div class="scope">Later pass: '+esc(r.monit_id)+'. A later image, not the peak; usually a larger extent.</div>';
panel.innerHTML=h;
if(zoom){var el=svg.querySelector('.aoi[data-aoi="'+key+'"]');if(el){var b=el.getBBox();
var pad=Math.max(b.width,b.height)*0.25+1;var hw=svg.viewBox.baseVal;
var hb=home.split(' ').map(Number);var ar=hb[3]/hb[2];
var w=b.width+2*pad,hh=b.height+2*pad;if(hh/w>ar){w=hh/ar;}else{hh=w*ar;}
setBox([b.x+b.width/2-w/2,b.y+b.height/2-hh/2,w,hh].map(function(v){return v.toFixed(2);}).join(' '));}}}
svg.querySelectorAll('.aoi').forEach(function(el){var k=el.getAttribute('data-aoi');
el.addEventListener('mouseenter',function(){show(k,false);});
el.addEventListener('click',function(){show(k,true);});
el.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();show(k,true);}});});
document.querySelectorAll('.aoilist button').forEach(function(b){b.addEventListener('click',function(){show(b.getAttribute('data-aoi'),true);});});
var reset=document.getElementById('reset');if(reset)reset.addEventListener('click',function(){setBox(home);});
var tog=document.getElementById('monit');if(tog)tog.addEventListener('change',function(){document.body.classList.toggle('hide-monit',!tog.checked);});
})();
"""


def _cards_html(cards: Iterable[dict[str, Any]]) -> str:
    out = []
    for card in cards:
        nums = "".join(
            f'<div class="num" data-headline="{esc(card["id"])}" data-country="{esc(v["country"])}" '
            f'data-value="{"" if v["raw"] is None else repr(v["raw"])}">{esc(v["shown"])}'
            f'<small>{esc(COUNTRY_NAMES.get(v["country"], v["country"]))}</small></div>'
            for v in card["values"])
        out.append(f'<div class="card"><h3>{esc(card["label"])}</h3><div class="nums">{nums}</div>'
                   f'<div class="scope">{esc(card["scope"])}</div></div>')
    return '<div class="cards">' + "".join(out) + "</div>"


def render_page(
    *,
    countries: pd.DataFrame,
    products: pd.DataFrame,
    exposure: pd.DataFrame,
    event_layers: dict[str, Any] | None = None,
    europe_features: Sequence[dict[str, Any]] = (),
    title: str = "[TITLE]",
    question: str = "[DECISION QUESTION]",
    recommendation: str = "[RECOMMENDATION]",
    actor: str = "[NAMED ACTOR]",
    built: str = "",
) -> str:
    """The whole page, top to bottom in the funnel order of the brief.

    Headline numbers, then the event, then the hazard-map gap, then Europe, then
    the recommendation, then what the data cannot say. Placeholders in square
    brackets are left for the team to fill on the day.
    """
    records = aoi_records(products)
    cards = headlines(countries)
    shares = europe_shares(exposure)
    layers = event_layers or {}
    europe_svg = svgmap.choropleth_svg(
        list(europe_features), shares, key="nuts_id", label="share of residents in the 1-in-100-year flood zone",
        percent=True, width=900, height=760,
    ) if europe_features else '<p class="scope">No boundary file was available to draw this map.</p>'
    later = country_rows(countries, "product_and_monit")
    first = country_rows(countries, HEADLINE_BASIS)
    km2_first = ", ".join(f"{iso} {fmt_km2(first[iso]['observed_km2'])}" for iso in COUNTRIES if iso in first)
    km2_later = ", ".join(f"{iso} {fmt_km2(later[iso]['observed_km2'])}" for iso in COUNTRIES if iso in later)

    def slot(text: str) -> str:
        return f'<span class="slot">{esc(text)}</span>' if text.startswith("[") else esc(text)

    buttons = "".join(
        f'<button type="button" data-aoi="{esc(r["key"])}">{esc(r["country"])} · {esc(r["locality"])}</button>'
        for r in records)
    aoi_json = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · {TEAM}</title>
<style>{CSS}</style></head>
<body><main>
<header><h1>{slot(title)}</h1>
<p class="question">{slot(question)}</p></header>

<section aria-label="Headline numbers">{_cards_html(cards)}</section>

<h2>1 · July 2021: where the water was seen</h2>
<div class="mapwrap"><div>
<div class="legend">
<span><span class="sw" style="background:{FLOOD_FILL}"></span>water observed on the first satellite pass</span>
<span><span class="sw" style="background:{MONIT_FILL}"></span>more water on a later pass</span>
<span><span class="sw" style="background:#fff;border:2px dashed {AOI_STROKE}"></span>area mapped by Copernicus EMS</span>
<span><span class="sw" style="background:#f7f7f2;border-color:#b8bcc2"></span>NUTS3 region (grey lines)</span>
</div>
{event_map_svg(layers, records)}
<div class="controls" style="margin-top:6px"><button type="button" id="reset">Reset view</button>
<label><input type="checkbox" id="monit" checked> show later passes</label></div>
<p class="scope">Water outside the dashed boxes was not mapped; it is not dry land.
Observed area, first pass: {km2_first} km². With later passes: {km2_later} km².</p>
</div>
<div><div class="panel" id="panel"><h3>Pick a mapped area</h3>
<p class="scope">Hover or click a dashed box on the map, or a name below, to see its water,
residents, buildings and damage grades. Clicking zooms in.</p></div>
<div class="aoilist">{buttons}</div></div></div>

<h2>2 · The JRC hazard map missed many of them</h2>
<div class="chart">{hazard_chart_svg(outside_shares(countries))}</div>
<p class="scope">Share of the residents inside the observed water (first pass) who live outside the JRC hazard map
for each flood size. The bigger flood maps contain the smaller ones, so the share can only fall
from 1-in-10 to 1-in-500. What remains outside even the 1-in-500 map is water the map does not model:
small streams, runoff, or a flood beyond its assumptions.</p>

<h2>3 · Is July 2021 a one-off?</h2>
<div class="europe">{europe_svg}</div>
<p class="scope">{europe_caption(shares, exposure)} Share of each region's residents living in the zone a
1-in-100-year river flood would reach if there were no dikes (JRC hazard map, GHS-POP); protected
low-lying areas such as much of the Netherlands therefore show high. Classes are sixths of the regions
(quantiles); grey is not measured, not zero.</p>

<h2>4 · What we recommend</h2>
<div class="reco">{slot(recommendation)} — addressed to {slot(actor)}</div>

<h2>What this cannot tell you</h2>
<div class="limits"><ul>{"".join(f"<li>{item}</li>" for item in LIMITS)}</ul></div>

<footer>
<p><b>Sources.</b></p><ul>{"".join(f"<li>{esc(s)}</li>" for s in SOURCES)}</ul>
<p>Every number on this page is read from the team's computed tables by a script; none is typed by hand.
This file is static: it calls no AI service and loads nothing from the internet. {esc(built)}</p>
<p><b>{TEAM}</b></p>
</footer>
</main>
<script type="application/json" id="aoidata">{aoi_json}</script>
<script>{JS}</script>
</body></html>
"""
