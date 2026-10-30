"""Pure helpers behind the July 2021 story maps, shared by every renderer.

The single-file policy tool (`scripts/build_policy_tool.py`) and the React
app's web export (`scripts/export_event_web.py`) draw the same maps from the
same 20 m scoring grid. Keeping the class reduction, the PNG encoding and the
geometry-to-pixel conversion here means the two cannot drift: a cell drawn
orange in one is orange in the other, because one function decided it.
Everything here works on arrays and shapely geometries already in memory, so
the tests need neither rasters nor network.
"""

from __future__ import annotations

import base64
import io
from typing import Any, Callable, Sequence

import numpy as np

#: Story-map raster classes, in the order the PNG palette uses them.
#: Water inside the map is darkest, water outside it a light orange: they differ
#: in lightness as well as hue, so greyscale and colour-blind readers see two.
RASTER_CLASSES: tuple[tuple[str, str], ...] = (
    ("#ffffff", "not mapped by Copernicus"),
    ("#f1f0ea", "mapped, no water seen"),
    ("#c9dcee", "1-in-100-year flood zone, no water seen"),
    ("#0b4f9c", "water seen, INSIDE the 1-in-100-year zone"),
    ("#f0a030", "water seen, OUTSIDE the 1-in-100-year zone"),
)


def lines(geom) -> list[list[tuple[float, float]]]:
    """The coordinate lists of a (multi)line or of a polygon's boundary."""
    import shapely

    if geom is None or geom.is_empty:
        return []
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        geom = geom.boundary
    return [list(map(tuple, shapely.get_coordinates(g))) for g in shapely.get_parts(geom)]


def reduce_classes(observed: np.ndarray, wet: np.ndarray, aoi: np.ndarray, k: int) -> np.ndarray:
    """Block-reduce the 20 m masks by `k` into `RASTER_CLASSES` indices.

    0 not mapped, 1 mapped and dry, 2 hazard zone with no water seen, 3 water
    inside the zone, 4 water outside it. A block with any water is water; it is
    "outside" only when its outside cells outnumber its inside cells, so the
    reduction never tips a tie toward the alarming colour. Without water, a
    block takes the zone or mapped class only when that covers at least half
    of it.
    """
    h, w = observed.shape
    H, W = -(-h // k) * k, -(-w // k) * k

    def blocks(mask):
        padded = np.zeros((H, W), dtype=np.int32)
        padded[:h, :w] = mask
        return padded.reshape(H // k, k, W // k, k).sum(axis=(1, 3))

    inside = blocks(observed & wet)
    outside = blocks(observed & ~wet)
    zone = blocks(wet & aoi & ~observed)
    mapped = blocks(aoi)
    half = k * k / 2
    out = np.zeros(inside.shape, dtype=np.uint8)
    out[mapped >= half] = 1
    out[(zone >= half) & (mapped >= half)] = 2
    water = (inside + outside) > 0
    out[water] = np.where(outside[water] > inside[water], 4, 3)
    return out


def png_data_uri(classes: np.ndarray) -> str:
    """A paletted PNG of the class array, as a data URI.

    Paletted (one byte per pixel, five colours) because it compresses to a
    few tens of kB per place, which is what lets a whole story fit in one file.
    """
    from PIL import Image

    image = Image.fromarray(classes, mode="P")
    palette: list[int] = []
    for colour, _ in RASTER_CLASSES:
        palette += [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    image.putpalette(palette + [0] * (768 - len(palette)))
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def satellite_png_data_uri(classes: np.ndarray, bbox_3035: Sequence[float], *, fetch=None) -> str:
    """A photographic basemap (Esri World Imagery) with the flood classes on top.

    Copernicus-style: the real satellite scene, water inside the map in blue and
    water outside it in bright orange, both semi-transparent so the ground shows
    through; the mapped hazard zone a faint blue. Falls back to the flat paletted
    PNG (`png_data_uri`) when the basemap cannot be fetched, so an offline build
    still produces a map. The basemap is baked in, so the result still opens
    offline at runtime.
    """
    from PIL import Image

    h, w = classes.shape
    try:
        base = (fetch or _fetch_world_imagery)(tuple(bbox_3035), (w, h)).convert("RGBA").resize((w, h))
    except Exception as exc:  # no network, blocked host, bad tile: keep the flat map
        print(f"    basemap unavailable ({type(exc).__name__}); flat map used", flush=True)
        return png_data_uri(classes)
    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    overlay[classes == 2] = (11, 79, 156, 55)     # hazard zone, dry: faint blue
    overlay[classes == 3] = (11, 79, 156, 165)    # water inside the zone: blue
    overlay[classes == 4] = (240, 100, 20, 195)   # water outside it: punchy orange
    out = Image.alpha_composite(base, Image.fromarray(overlay, "RGBA")).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _fetch_world_imagery(bbox_3035: Sequence[float], size: tuple[int, int]):
    """Esri World Imagery for an EPSG:3035 box at (w, h) pixels, as a PIL image."""
    import urllib.parse
    import urllib.request

    from PIL import Image

    minx, miny, maxx, maxy = bbox_3035
    w, h = size
    query = urllib.parse.urlencode({
        "bbox": f"{minx},{miny},{maxx},{maxy}", "bboxSR": 3035, "imageSR": 3035,
        "size": f"{w},{h}", "format": "jpg", "f": "image"})
    url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?" + query
    with urllib.request.urlopen(url, timeout=30) as resp:
        return Image.open(io.BytesIO(resp.read()))


def geojson_pixels(geom, to_px: Callable[[float, float], tuple[float, float]],
                   tolerance_m: float = 0.0, digits: int = 1) -> dict[str, Any] | None:
    """A polygonal geometry as GeoJSON in image pixel units (x right, y down).

    Simplified in metres first (so a tolerance is a distance, as everywhere in
    the kit), then each vertex mapped by `to_px` and rounded to `digits`;
    vertices that round onto the previous one are dropped and rings left with
    fewer than four points vanish. Returns None for an empty geometry.
    """
    import shapely

    if geom is None or geom.is_empty:
        return None
    if tolerance_m > 0:
        geom = geom.simplify(tolerance_m, preserve_topology=True)
    polygons = []
    for part in shapely.get_parts(geom):
        if part.geom_type != "Polygon":
            continue
        rings = [_ring_px(part.exterior.coords, to_px, digits)]
        if len(rings[0]) < 4:
            continue
        rings += [r for r in (_ring_px(i.coords, to_px, digits) for i in part.interiors) if len(r) >= 4]
        polygons.append(rings)
    if not polygons:
        return None
    return {"type": "MultiPolygon", "coordinates": polygons}


def _ring_px(coords: Sequence[Sequence[float]], to_px, digits: int) -> list[list[float]]:
    out: list[list[float]] = []
    for c in coords:
        x, y = to_px(float(c[0]), float(c[1]))
        p = [round(x, digits), round(y, digits)]
        if not out or out[-1] != p:
            out.append(p)
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out
