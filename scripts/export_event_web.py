"""Export the July 2021 story as one compact JSON for the React app.

The hosted app (a Space or a static site) clones the repository, which carries
no raw data: no EMS layers, no 1 GB hazard rasters. So the story map cannot be
computed there. This script computes it here, once, and writes a small,
self-contained artefact the app reads as is:

- `data/processed/event_2021_web.json`, served by `GET /api/event2021`;
- `web/public/event_2021_web.json`, the same bytes, which Vite copies into
  `dist/` so a static build works with no API at all.

The figures and the maps come from the same code as the single-file policy
tool: `src.policy_tool` for every number and every formatted string,
`scripts/build_policy_tool.place_layer` and `locator` for the rasterised maps
(same 20 m scoring grid, same hazard mask, same class reduction in
`src.story_maps`). Nothing is re-derived, so the two renderings cannot
disagree.

Both committed copies are the public build: country borders from Natural
Earth (public domain) and no GISCO-derived line, because GISCO's terms keep
its geometry out of a public artefact (see `data/processed/DATA_NOTICE.md`).
`--full` draws the GISCO borders and NUTS3 lines instead and writes them to
`data/processed/event_2021_web.full.json` only, which git ignores and the API
serves in its place when present. The safe build is the default, so a plain
run can never put GISCO geometry into a tracked file.

Run:

    python scripts/export_event_web.py          # public, committed
    python scripts/export_event_web.py --full   # local only, with NUTS3 lines
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src import policy_tool as P
from src import story_maps

PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "event_2021_web.json"
WEB_OUT = ROOT / "web" / "public" / "event_2021_web.json"
FULL_OUT = PROCESSED / "event_2021_web.full.json"
SCHEMA_VERSION = 1
#: The artefact is committed and shipped to every browser: keep it small.
MAX_BYTES = 3_000_000


def _clean(value: Any) -> Any:
    """JSON-safe copy: NaN becomes None, tuples become lists, numpy scalars plain."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, 6)
    return value


def _layer_view(layer: dict[str, Any]) -> dict[str, Any]:
    """The parts of a `place_layer` result the app draws, with labels as objects."""
    km, px = layer.get("scale", (None, None))
    return {
        "png": layer["png"], "width": layer["width"], "height": layer["height"],
        "pixel_m": layer["pixel_m"], "bounds_3035": list(layer["bounds_3035"]),
        "outline_d": layer.get("outline", ""), "nuts_d": layer.get("nuts", ""),
        "outline": layer.get("outline_geojson"), "observed": layer.get("observed_geojson"),
        "towns": [{"label": t, "x": round(x, 1), "y": round(y, 1)} for t, x, y in layer.get("towns", [])],
        "scale": {"km": km, "px": None if px is None else round(px, 1)},
    }


def build_payload(products: pd.DataFrame, countries: pd.DataFrame, exposure: pd.DataFrame,
                  layers: dict[str, dict[str, Any]], locator: dict[str, Any] | None,
                  built: str = "") -> dict[str, Any]:
    """The whole web artefact from the tables and the precomputed map layers.

    Pure: the tests call it with synthetic tables and hand-made layers. Every
    formatted string is the one `src.policy_tool` prints in the single file.
    """
    shares = P.outside_shares(countries)
    places = []
    for place in P.place_records(products):
        layer = layers.get(place["key"])
        places.append({**place, "named": place["key"] in dict(P.NAMED_PLACES),
                       "map": _layer_view(layer) if layer else None})
    loc = None
    if locator:
        loc = {"width": locator["width"], "height": locator["height"],
               "borders_d": locator.get("borders", ""), "nuts_d": locator.get("nuts", ""),
               "labels": [{"text": t, "x": x, "y": y} for t, x, y in locator.get("labels", [])],
               "aoi": locator.get("aoi", {})}
    return _clean({
        "schema": SCHEMA_VERSION,
        "built": built,
        "team": P.TEAM,
        "hero": P.hero(products, countries, exposure),
        "strip": [{**s, "name": P.COUNTRY_NAMES[s["country"]]} for s in P.country_strip(countries)],
        "chart": {
            "return_periods": list(P.CHART_RPS),
            "default": 100,
            "heading": P.chart_heading(shares),
            "rows": [{"country": iso, "name": P.COUNTRY_NAMES[iso],
                      "shares": {str(rp): shares[iso][rp] for rp in P.CHART_RPS},
                      "shown": {str(rp): P.fmt_share(shares[iso][rp]) for rp in P.CHART_RPS}}
                     for iso in P.COUNTRIES],
        },
        "raster_classes": [{"colour": c, "label": t} for c, t in story_maps.RASTER_CLASSES],
        "places": places,
        "locator": loc,
        "how_we_counted": list(P.HOW_WE_COUNTED),
        "limits": list(P.LIMITS),
        "sources": list(P.SOURCES),
        "attribution": attribution(loc),
    })


def attribution(loc: dict[str, Any] | None) -> str:
    """The boundary credit the locator's lines require: GISCO's is mandatory, Natural Earth's a courtesy."""
    if loc and loc["nuts_d"]:
        return "© EuroGeographics for the administrative boundaries"
    if loc and loc["borders_d"]:
        return "Country borders: Natural Earth (public domain)"
    return ""


def write(payload: dict[str, Any], paths: tuple[Path, ...] = (OUT, WEB_OUT)) -> int:
    """Write the same compact JSON to every path; returns its size in bytes."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    data = text.encode("utf-8")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return len(data)


def main(argv: list[str] | None = None) -> int:
    """Read the tables, rasterise each place, write the copies, print the size."""
    from scripts.build_policy_tool import locator, place_layer

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--full", action="store_true",
                        help=f"GISCO borders and NUTS3 lines, written to {FULL_OUT.name} only (never committed)")
    args = parser.parse_args(argv)
    with_nuts = args.full
    paths = (FULL_OUT,) if args.full else (OUT, WEB_OUT)

    products = pd.read_parquet(PROCESSED / "event_2021_products.parquet")
    countries = pd.read_parquet(PROCESSED / "event_2021_countries.parquet")
    exposure = pd.read_parquet(PROCESSED / "exposure.parquet")
    first = P.first_pass(products)
    layers = {}
    for place in P.place_records(products):
        print(f"  map {place['key']} ({place['label']})", flush=True)
        layer = place_layer(str(first[place["key"]]["product_id"]), with_nuts=with_nuts)
        if layer:
            layers[place["key"]] = layer
    payload = build_payload(products, countries, exposure, layers,
                            locator(products, with_nuts=with_nuts),
                            built=dt.date.today().isoformat())
    size = write(payload, paths)
    print(f"{paths[0]}  {size / 1e6:.2f} MB")
    for path in paths[1:]:
        print(f"{path}  (same bytes)")
    if size > MAX_BYTES:
        print(f"WARNING: above the {MAX_BYTES / 1e6:.0f} MB budget")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
