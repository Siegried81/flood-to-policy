"""An offline choropleth, as inline SVG.

**Why SVG and not folium.** `folium` and `streamlit-folium` are declared in
`requirements.txt` and nothing imports them, because a Leaflet map fetches its
basemap tiles from a tile server - and the kit has to run with the Wi-Fi off, in
front of a jury, on a venue network that blocks things. An inline SVG has no
network dependency, no build step and no API key, which is the same reason the
React side draws its own. This module is that drawing, for the Streamlit app.

**Why EPSG:3035 and not raw longitude/latitude.** Plotting degrees directly
stretches Europe east-west by 1/cos(latitude): Lapland comes out three times too
wide against Crete, and the reader is looking at a projection artefact. 3035 is
the European equal-area standard the rest of the kit computes in, so the map and
the numbers agree about where things are.

**Classes, not a linear ramp.** Exposure share is extremely skewed - the median
NUTS3 region is near 3% and the Dutch tail reaches 70% - so a min-max linear
ramp paints almost every region the palest colour and shows nothing. The breaks
are therefore quantiles of the values actually present, printed in the legend, so
a reader can see that the classes are relative rather than absolute.

**A region with no measurement is grey, never the colour of zero.** A region the
hazard raster does not cover is not a region where nobody is exposed, and the one
thing a risk map must not do is paint an unknown as safe.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from pyproj import Transformer

#: Sequential, light to dark. Six classes is the most a reader can tell apart in
#: a legend; beyond that the map looks precise and is not.
PALETTE: tuple[str, ...] = (
    "#fff7bc", "#fee391", "#fe9929", "#ec7014", "#cc4c02", "#8c2d04",
)

#: For a SIGNED quantity, where the question is which way it moves. Blue for a
#: fall, red for a rise, through a near-neutral middle. The classes are still
#: quantiles, so the middle class is not guaranteed to contain zero - the legend
#: prints the bounds and the caller says so. Pass `centre=` to `choropleth_svg`
#: to anchor the classes on a value instead.
PALETTE_DIVERGING: tuple[str, ...] = (
    "#2166ac", "#67a9cf", "#d1e5f0", "#fddbc7", "#ef8a62", "#b2182b",
)

#: For a signed quantity whose classes are anchored on a centre (see
#: `signed_breaks`): two blues below it, four reds above it. Lopsided on
#: purpose, because a river-discharge change is mostly a rise - four classes on
#: a side holding 49 regions would print empty or near-empty bands. Blues are
#: read darkest-first and reds lightest-first, so the colours nearest the centre
#: are always the palest whichever classes a one-sided input collapses.
PALETTE_DIVERGING_SIGNED: tuple[str, ...] = (
    "#2166ac", "#67a9cf",
    "#fddbc7", "#f4a582", "#d6604d", "#b2182b",
)
NEG_CLASSES_SIGNED = 2

#: Not in the palette, deliberately: it has to be unmistakably "no answer"
#: rather than a seventh class of the same ramp.
NO_DATA = "#d9d9d9"

STROKE = "#9aa0a6"

#: NUTS3 prefixes whose regions are not on a map of Europe: French Guiana is in
#: South America, Reunion and Mayotte in the Indian Ocean, the Azores, Madeira
#: and the Canaries in the Atlantic, Svalbard and Jan Mayen in the Arctic.
#:
#: They set the VIEWPORT only - they are still drawn, and `outermost()` names
#: them so a caller can say what is off the map rather than dropping them in
#: silence. Measured on the GISCO NUTS 2024 file: including them makes the
#: extent 12,850 x 9,486 km against 4,680 x 4,029 km without - 6.5 times the
#: area, so continental Europe would occupy about a seventh of the picture.
#:
#: Ceuta and Melilla are deliberately NOT here. They are in Africa but 15 km off
#: the Spanish coast, and measured on the same file they move the extent by
#: nothing at all: 4,680 x 4,029 km either way. Calling them off-map would have
#: been a caption that was simply untrue.
OUTERMOST: tuple[str, ...] = (
    "FRY", "PT20", "PT30", "ES70", "NO0B",
)

_TO_METRES = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def _project(lon: float, lat: float) -> tuple[float, float]:
    return _TO_METRES.transform(lon, lat)


def _rings(geometry: dict[str, Any]) -> list[list[Sequence[float]]]:
    """Every exterior and interior ring of a Polygon or MultiPolygon, flattened.

    Holes are kept as rings rather than dropped: an SVG path with `fill-rule:
    evenodd` renders them as holes, and dropping them fills enclaves with their
    neighbour's colour.
    """
    kind = geometry.get("type")
    if kind == "Polygon":
        return list(geometry.get("coordinates") or [])
    if kind == "MultiPolygon":
        return [ring for poly in geometry.get("coordinates") or [] for ring in poly]
    return []


#: Width of one legend entry and height of one legend row, in viewBox units.
#: 170 fits "6/6 · 10.6% to 75.5%" at 11px with the swatch beside it; the rows
#: wrap from there, see `choropleth_svg`.
LEGEND_SLOT = 170
LEGEND_ROW_H = 20


def quantile_breaks(values: Iterable[float], classes: int = 6) -> list[float]:
    """Upper bound of each class, from the values actually present.

    Returns one bound per class. Duplicate bounds are collapsed, so a
    distribution with many equal values yields fewer classes rather than several
    classes that mean the same thing - which would be a legend that lies.
    """
    finite = sorted(v for v in values if v is not None and math.isfinite(v))
    if not finite:
        return []
    out: list[float] = []
    for i in range(1, classes + 1):
        # Nearest-rank, so every bound is a value that occurs in the data.
        rank = max(0, math.ceil(i / classes * len(finite)) - 1)
        bound = finite[rank]
        if not out or bound > out[-1]:
            out.append(bound)
    return out


def _signed_sides(
    values: Iterable[float],
    neg_classes: int = NEG_CLASSES_SIGNED,
    pos_classes: int = 4,
    centre: float = 0.0,
) -> tuple[list[float], list[float]]:
    """The class bounds below and above `centre`, kept apart.

    Each side runs the nearest-rank rule of `quantile_breaks` on its own values,
    so a class never straddles the centre. The last bound below is forced to
    `centre` itself, which puts the centre on a class boundary in the legend.
    An empty side returns no bounds at all rather than empty swatches.
    """
    finite = [v for v in values if v is not None and math.isfinite(v)]
    below = quantile_breaks([v for v in finite if v < centre], neg_classes)
    above = quantile_breaks([v for v in finite if v >= centre], pos_classes)
    if below:
        below[-1] = centre
    return below, above


def signed_breaks(
    values: Iterable[float],
    neg_classes: int = NEG_CLASSES_SIGNED,
    pos_classes: int = 4,
    centre: float = 0.0,
) -> list[float]:
    """Upper bound of each class, quantiles taken separately on each side of `centre`.

    Plain quantiles of a mostly-positive signed quantity put zero inside the
    first class, so a rise is drawn in the colour of a fall. Splitting at the
    centre first makes the hue carry the sign and the shade carry the rank.
    """
    below, above = _signed_sides(values, neg_classes, pos_classes, centre)
    return below + above


def _class_of(value: float | None, breaks: Sequence[float]) -> int | None:
    if value is None or not math.isfinite(value) or not breaks:
        return None
    for i, bound in enumerate(breaks):
        if value <= bound:
            return i
    return len(breaks) - 1


def load_features(path: str | Path, key: str = "nuts_id") -> list[dict[str, Any]]:
    """The GeoJSON features, keyed and already in lon/lat.

    `scripts/build_geometry.py` writes WGS84, as the GeoJSON format requires, and
    simplifies to 1 km in EPSG:3035 first so the tolerance is a real distance.
    Features without the key are dropped: they cannot be joined to a figure, and
    drawing them uncoloured would read as "measured, and zero".
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        f for f in payload.get("features", [])
        if (f.get("properties") or {}).get(key) is not None
    ]


def outermost(
    features: Sequence[dict[str, Any]],
    key: str = "nuts_id",
    prefixes: Sequence[str] = OUTERMOST,
) -> list[str]:
    """The keys that sit outside a European viewport, sorted.

    Exposed so a caller can print "18 regions are not on this map" instead of
    quietly losing them: a region missing from a picture with no note is
    indistinguishable from a region with nothing to report.
    """
    found = {
        str((f.get("properties") or {}).get(key))
        for f in features
        if str((f.get("properties") or {}).get(key)).startswith(tuple(prefixes))
    }
    return sorted(found)


def choropleth_svg(
    features: Sequence[dict[str, Any]],
    values: dict[str, float | None],
    *,
    key: str = "nuts_id",
    width: int = 900,
    height: int = 620,
    label: str = "value",
    percent: bool = False,
    extent_excludes: Sequence[str] = OUTERMOST,
    palette: Sequence[str] = PALETTE,
    hatch: Sequence[str] = (),
    fmt: Callable[[float], str] | None = None,
    centre: float | None = None,
    hatch_label: str = "models disagree on the direction",
) -> str:
    """One SVG string: the regions, filled by class, with a legend.

    `values` maps a region key to its figure. A key absent from it, or mapped to
    None or NaN, is drawn in `NO_DATA` - see the module docstring on why that is
    not the same as zero.

    `hatch` names regions that carry a figure the reader must not read flat. It
    exists for the climate layer: a region where the model chains disagree about
    the SIGN of the change has a median like any other, and painting it like any
    other states a direction the ensemble does not support. Greying it would be
    the other error - that would say "not measured", and it was. So it keeps its
    colour and gets diagonal hatching over it, which is a third statement:
    measured, and the models do not agree which way.

    `hatch_label` is the words for that third state, in the legend entry and in
    each hatched region's tooltip alike. The caller decides which ensemble test
    drew the hatch (robust at 80 % of members, or unanimous), so the caller
    names it; the default is the generic wording older callers already show.

    `centre` is for a signed quantity. When it is set, the classes come from
    `signed_breaks` around it and the fill from `PALETTE_DIVERGING_SIGNED`
    (`palette` is then not read), so every value below the centre is a blue and
    every value at or above it a red. Left at None, the classes are plain
    quantiles and the output is what it has always been.
    """
    present = [v for v in values.values() if v is not None and math.isfinite(v)]
    if centre is None:
        breaks = quantile_breaks(present)

        def classify(value: float | None) -> int | None:
            return _class_of(value, breaks)

        def colour(index: int) -> str:
            return palette[min(index, len(palette) - 1)]
    else:
        below, above = _signed_sides(present, centre=centre)
        breaks = below + above

        def classify(value: float | None) -> int | None:
            if value is None or not math.isfinite(value) or not breaks:
                return None
            if value < centre:
                return _class_of(value, below)
            return len(below) + _class_of(value, above)

        def colour(index: int) -> str:
            # Blues end on the palest one next to the centre; reds start on the
            # palest one next to it. A collapsed side drops its darkest shades.
            if index < len(below):
                return PALETTE_DIVERGING_SIGNED[NEG_CLASSES_SIGNED - len(below) + index]
            return PALETTE_DIVERGING_SIGNED[
                min(NEG_CLASSES_SIGNED + index - len(below),
                    len(PALETTE_DIVERGING_SIGNED) - 1)
            ]
    low_bound = min(present) if present else 0.0
    shapes: list[tuple[str, str, str]] = []  # (path, fill, tooltip)
    xs: list[float] = []
    ys: list[float] = []
    projected: list[tuple[str, list[list[tuple[float, float]]]]] = []

    skip = tuple(extent_excludes)
    for feature in features:
        code = (feature.get("properties") or {}).get(key)
        # Drawn either way; only the viewport ignores them. See OUTERMOST.
        sets_extent = not (skip and str(code).startswith(skip))
        rings: list[list[tuple[float, float]]] = []
        for ring in _rings(feature.get("geometry") or {}):
            points = [_project(float(p[0]), float(p[1])) for p in ring if len(p) >= 2]
            if len(points) >= 3:
                rings.append(points)
                if sets_extent:
                    xs.extend(p[0] for p in points)
                    ys.extend(p[1] for p in points)
        if rings:
            projected.append((str(code), rings))

    # A frame holding nothing but outermost regions - a zoom on Reunion - still
    # has to be drawable, so fall back to every shape rather than to nothing.
    if not xs:
        for _, rings in projected:
            for ring in rings:
                xs.extend(p[0] for p in ring)
                ys.extend(p[1] for p in ring)

    if not projected or not xs:
        return (
            f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'role="img" aria-label="no geometry to draw"></svg>'
        )

    pad = 8
    # The legend is laid out before the map is scaled, because it owns a band at
    # the bottom of the viewport and the map has to stop above it. Entries wrap
    # onto as many rows as the width allows: six classes plus "not measured"
    # plus the hatch swatch is eight slots, and eight slots on one row ran past
    # the right edge of the viewBox, so the last entries were drawn and clipped.
    # A legend entry that exists in the DOM and not on screen is a colour with
    # no name.
    hatched = {c for c in hatch if classify(values.get(c)) is not None}
    n_entries = len(breaks) + 1 + (1 if hatched else 0)
    per_row = max(1, (width - 2 * pad) // LEGEND_SLOT)
    legend_rows = -(-n_entries // per_row)  # ceiling division
    legend_h = legend_rows * LEGEND_ROW_H
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    span = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    map_h = height - 2 * pad - legend_h
    scale = min((width - 2 * pad) / span[0], map_h / span[1])
    # Centre the drawing in the viewport, and flip Y: SVG counts downwards while
    # a projected northing counts up.
    off_x = pad + ((width - 2 * pad) - span[0] * scale) / 2
    off_y = pad + (map_h - span[1] * scale) / 2

    def place(point: tuple[float, float]) -> str:
        return (
            f"{off_x + (point[0] - x0) * scale:.1f},"
            f"{off_y + (y1 - point[1]) * scale:.1f}"
        )

    def show(value: float) -> str:
        if fmt is not None:
            return fmt(value)
        return f"{value * 100:.1f}%" if percent else f"{value:,.0f}"

    overlays: list[str] = []
    # How many regions each class holds, for the legend tooltips: with quantile
    # classes the counts are near-equal by construction, and saying so is what
    # stops "10.6% to 75.5%" reading as a danger band rather than a top sixth.
    per_class = [0] * len(breaks)
    for code, rings in projected:
        value = values.get(code)
        index = classify(value)
        if index is not None:
            per_class[index] += 1
        fill = NO_DATA if index is None else colour(index)
        path = " ".join(
            "M" + " L".join(place(p) for p in ring) + " Z" for ring in rings
        )
        if index is None:
            tip = "not measured"
        elif code in hatched:
            tip = f"{show(value)} — {hatch_label}"
        else:
            tip = show(value)
        shapes.append((path, fill, f"{code}: {tip}"))
        if code in hatched and index is not None:
            overlays.append(path)

    body = "\n".join(
        f'<path d="{path}" fill="{fill}" stroke="{STROKE}" stroke-width="0.4" '
        f'fill-rule="evenodd"><title>{tooltip}</title></path>'
        for path, fill, tooltip in shapes
    )
    # Drawn after every fill, so the hatching sits on top of its own region and
    # of its neighbours' edges rather than under the next polygon.
    if overlays:
        body += "\n" + "\n".join(
            f'<path d="{path}" fill="url(#disagree)" stroke="none" '
            f'fill-rule="evenodd" pointer-events="none"/>' for path in overlays
        )

    def legend_text(i: int) -> str:
        # The rank comes first because the classes are quantiles: "6/6" says
        # this is the top sixth of the regions present, which is the only
        # reading under which "10.6% to 75.5%" is not a danger band. The first
        # class's lower bound is the smallest value present, not zero: a signed
        # quantity goes below it, and printing "0.0" there would state that
        # nothing in the map falls.
        low = low_bound if i == 0 else breaks[i - 1]
        return f"{i + 1}/{len(breaks)} · {show(low)} to {show(breaks[i])}"

    entries: list[tuple[str, str, str]] = [  # (fill, label, tooltip)
        (
            colour(i),
            legend_text(i),
            f"class {i + 1} of {len(breaks)}: {per_class[i]:,} regions, equal-count "
            + ("(quantile) classes" if centre is None else
               "(quantile) classes within each side of the centre"),
        )
        for i in range(len(breaks))
    ]
    entries.append((NO_DATA, "not measured", "no figure for the region; not a zero"))
    if hatched:
        entries.append(("url(#disagree)", hatch_label,
                        "the median is drawn; the model chains differ on its sign"))

    swatches = []
    for n, (fill, text, tip) in enumerate(entries):
        row, col = divmod(n, per_row)
        y = height - legend_h + row * LEGEND_ROW_H + 2
        x = pad + 4 + col * LEGEND_SLOT
        swatches.append(
            f'<rect x="{x}" y="{y}" width="14" height="14" fill="{fill}" '
            f'stroke="{STROKE}" stroke-width="0.4"><title>{tip}</title></rect>'
            f'<text x="{x + 18}" y="{y + 11}" font-size="11" class="lg">{text}</text>'
        )

    # The GISCO terms require this line on any map drawn from the NUTS
    # boundaries, "in the map legend". Drawn into the SVG rather than captioned
    # by each caller, so no map this module makes can leave it out. Bottom
    # right of the map band, just above the legend, inside the viewBox.
    credit = (
        f'<text x="{width - pad}" y="{height - legend_h - 2}" font-size="9" '
        'text-anchor="end" class="lg">© EuroGeographics for the administrative '
        'boundaries</text>'
    )

    # The legend colour is a class with a dark-mode rule rather than
    # `currentColor`: this SVG is rendered inside an iframe, which inherits
    # neither the app's text colour nor its theme, so `currentColor` would
    # resolve to black and the legend would vanish on a dark background.
    #
    # `height` is set explicitly as well as the viewBox, because an <svg> with
    # only a viewBox and `width="100%"` has no intrinsic height in some
    # containers and collapses to nothing - a map that is in the DOM and zero
    # pixels tall is indistinguishable from a map that was never drawn.
    style = (
        "<style>.lg{fill:#374151}"
        "@media (prefers-color-scheme:dark){.lg{fill:#e5e7eb}}</style>"
    )
    defs = (
        '<defs><pattern id="disagree" width="6" height="6" '
        'patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{STROKE}" '
        'stroke-width="1.6"/></pattern></defs>' if overlays else ""
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'style="display:block;width:100%;height:auto" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="choropleth of {label}">\n{style}{defs}\n{body}\n'
        f'{"".join(swatches)}\n{credit}\n</svg>'
    )
