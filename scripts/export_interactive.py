"""Per-place data for the web's interactive (Leaflet) map, written as small
files loaded on demand, not baked into the main artefact.

The main `event_2021_web.json` stays small and offline: it carries the flat
satellite image of each place. The interactive map is an *enhancement* that only
works online (it needs basemap tiles), so its heavier data lives in separate
files the browser fetches when the viewer opens it:

    web/public/interactive/index.json            # the keys available
    web/public/interactive/<key>/flood.geojson   # observed 2021 water, lon/lat
    web/public/interactive/<key>/depth.png        # EFAS 1-in-100 depth, 4326, transparent where dry
    web/public/interactive/<key>/meta.json        # overlay bounds, centre, depth legend

Depth is the JRC 1-in-100-year hazard map, read on the scoring grid (EPSG:3035)
and reprojected to EPSG:4326 (nearest, so no depth is invented) so a Leaflet
`imageOverlay` with lat/lng bounds lines up with the tiles. It is coloured by
class (purple ramp); a click reads the pixel's colour back to its depth class.

Run: `python scripts/export_interactive.py`            # the three border places
     `python scripts/export_interactive.py --all`      # every mapped place
     `python scripts/export_interactive.py --aois EMSR517_AOI09,EMSR518_AOI01`
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROCESSED = ROOT / "data" / "processed"
EMS_CACHE = ROOT / "data" / "raw" / "challenge_2021" / "ems"
OUT_DIR = ROOT / "web" / "public" / "interactive"

#: The three border places open the story, so they get the interactive map first.
BORDER_AOIS = ("EMSR517_AOI09", "EMSR518_AOI01", "EMSR520_AOI01")

#: EFAS depth classes (metres), lower bounds, and a purple ramp — the fourth hue
#: family of the shared map (people warm, buildings green, observed blue, modelled
#: purple), colourblind-safe and perceptually ordered. The channel is purely for
#: display; the click reads the class back by matching the colour.
DEPTH_BREAKS = (0.1, 0.5, 1.0, 2.0, 4.0, 8.0)
DEPTH_LABELS = ("0.1–0.5 m", "0.5–1 m", "1–2 m", "2–4 m", "4–8 m", "≥ 8 m")
DEPTH_COLOURS = ((243, 237, 247), (218, 205, 232), (188, 162, 212), (158, 118, 191),
                 (122, 73, 165), (74, 20, 110))
#: Keep each overlay image at most this many pixels on its long side, so a place's
#: depth PNG stays a few tens of kB.
MAX_PX = 820
#: Simplify the flood outline at about 15 m, in degrees, to keep the GeoJSON small.
SIMPLIFY_DEG = 0.00015


def _load(product_id: str):
    """The AOI and the observed water of one product, as lon/lat shapely polygons."""
    import pyogrio

    from scripts.event_2021 import _union
    from src import event2021 as E

    gpkg = EMS_CACHE / f"{product_id}.gpkg"
    if not gpkg.exists():
        return None, None
    aoi = _union(pyogrio.read_dataframe(gpkg, layer="areaOfInterestA").geometry)
    events = pyogrio.read_dataframe(gpkg, layer="observedEventA")
    observed = _union(events[events["notation"].isin(E.OBSERVED_NOTATIONS)].geometry)
    if observed is not None and aoi is not None:
        observed = _union([observed.intersection(aoi)])
    return aoi, observed


def _depth_overlay(aoi) -> tuple[bytes, list[list[float]]] | None:
    """The 1-in-100 depth over the AOI as an RGBA PNG and its [[s,w],[n,e]] bounds.

    The depth is read on the EPSG:3035 scoring grid, classified, then reprojected
    to EPSG:4326 (nearest) so a lat/lng `imageOverlay` is geographically correct.
    Transparent where the map is dry or has nothing to say.
    """
    from PIL import Image
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    from scripts.validate_2021 import HAZARD, window_grid
    from src import validate as V

    grid = window_grid(tuple(aoi.bounds))
    depth = V.read_depth_on_grid(str(HAZARD).format(rp=100), grid)  # metres, NaN = nodata
    classes = np.digitize(np.nan_to_num(depth, nan=0.0), DEPTH_BREAKS).astype(np.uint8)  # 0..6
    if not classes.any():
        return None  # nothing modelled here

    src_transform = grid.transform()
    bottom = grid.top - grid.height * grid.resolution_m
    right = grid.left + grid.width * grid.resolution_m
    dst_transform, dw, dh = calculate_default_transform(
        grid.crs, "EPSG:4326", grid.width, grid.height, grid.left, bottom, right, grid.top)
    scale = max(1.0, max(dw, dh) / MAX_PX)
    if scale > 1.0:  # cap the long side so the PNG stays small
        dw, dh = int(round(dw / scale)), int(round(dh / scale))
        from rasterio.transform import Affine
        dst_transform = Affine(dst_transform.a * scale, 0, dst_transform.c,
                               0, dst_transform.e * scale, dst_transform.f)
    dst = np.zeros((dh, dw), np.uint8)
    reproject(classes, dst, src_transform=src_transform, src_crs=grid.crs,
              dst_transform=dst_transform, dst_crs="EPSG:4326", resampling=Resampling.nearest)

    rgba = np.zeros((dh, dw, 4), np.uint8)
    for i, colour in enumerate(DEPTH_COLOURS, start=1):
        mask = dst == i
        rgba[mask, :3] = colour
        rgba[mask, 3] = 205
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)

    west, north = dst_transform.c, dst_transform.f
    east = west + dw * dst_transform.a
    south = north + dh * dst_transform.e  # e is negative
    return buf.getvalue(), [[south, west], [north, east]]


def export_one(key: str, product_id: str, label: str, out_dir: Path) -> dict[str, Any] | None:
    """Write flood.geojson, depth.png and meta.json for one place; return its index row."""
    import shapely

    aoi, observed = _load(product_id)
    if aoi is None:
        print(f"  {key}: missing gpkg, skipped")
        return None
    place_dir = out_dir / key
    place_dir.mkdir(parents=True, exist_ok=True)

    flood = observed if observed is not None else aoi
    geojson = {"type": "Feature", "properties": {},
               "geometry": json.loads(shapely.to_geojson(flood.simplify(SIMPLIFY_DEG)))}
    (place_dir / "flood.geojson").write_text(json.dumps(geojson), encoding="utf-8")

    depth = _depth_overlay(aoi)
    if depth is not None:
        png, bounds = depth
        (place_dir / "depth.png").write_bytes(png)
    else:
        bounds = None

    minx, miny, maxx, maxy = aoi.bounds
    meta = {
        "key": key, "label": label,
        "center": [(miny + maxy) / 2, (minx + maxx) / 2],
        "aoi_bounds": [[miny, minx], [maxy, maxx]],
        "depth": None if bounds is None else {
            "image": "depth.png", "bounds": bounds,
            "classes": [{"label": lab, "colour": "#%02x%02x%02x" % col}
                        for lab, col in zip(DEPTH_LABELS, DEPTH_COLOURS)],
            "return_period": 100,
        },
        "credit": "Imagery © Esri, Maxar, Earthstar Geographics · Flood: Copernicus EMS · Depth: JRC/EFAS",
    }
    (place_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    size = sum(p.stat().st_size for p in place_dir.iterdir())
    print(f"  {key} ({label}): {size / 1e3:.0f} kB" + ("" if depth else "  [no depth modelled]"))
    return {"key": key, "label": label, "has_depth": depth is not None}


def main(argv: list[str] | None = None) -> int:
    """Write the interactive files for the chosen places and an index.json."""
    from src import policy_tool as P

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="every selectable place, not only the border three")
    parser.add_argument("--aois", default="", help="comma-separated aoi_keys to restrict to")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    products = pd.read_parquet(PROCESSED / "event_2021_products.parquet")
    first = P.first_pass(products)
    records = {r["key"]: r for r in P.place_records(products)}
    if args.aois:
        wanted = [s.strip() for s in args.aois.split(",") if s.strip()]
    elif args.all:
        wanted = list(records)
    else:
        wanted = list(BORDER_AOIS)

    args.out.mkdir(parents=True, exist_ok=True)
    index = []
    for key in wanted:
        if key not in first or key not in records:
            print(f"  {key}: not a mapped place, skipped")
            continue
        row = export_one(key, str(first[key]["product_id"]), records[key]["label"], args.out)
        if row:
            index.append(row)
    (args.out / "index.json").write_text(json.dumps({"places": index}), encoding="utf-8")
    print(f"{args.out / 'index.json'}  ({len(index)} places)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
