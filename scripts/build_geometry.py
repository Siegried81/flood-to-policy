"""Freeze the choropleth's polygons into `data/processed/regions.geojson`.

The React UI draws the map as SVG straight from GeoJSON - no tile provider, no
API key - so the map still renders with the venue Wi-Fi unplugged. That design
needs one file nothing in this repo produced: `api/main.py` serves
`data/processed/regions.geojson` on `/api/geometry`, and without it the endpoint
answers 404 and `Choropleth.jsx` returns null. The map was unbuildable from a
clean checkout. This script is the missing half.

Three choices here are load-bearing:

* **Simplify in EPSG:3035, convert to 4326 afterwards.** A tolerance is a
  distance, and degrees are not one: 0.01 deg is about 1.1 km north-south
  everywhere but 700 m east-west at Belgian latitudes and under 500 m in
  northern Finland. Simplifying in degrees therefore thins the north of the map
  harder than the south, which is visible as ragged Scandinavian coastline next
  to smooth Mediterranean coastline.

* **The property names ARE the join key.** `Choropleth.jsx` looks up
  `feature.properties[idKey]`, where `idKey` is whatever `/api/exposure`
  reports - `nuts_id` for a NUTS3 run, `lau_id` for a LAU zoom
  (`api.main._region_key`). GISCO calls the same field `NUTS_ID`. Shipping the
  GISCO spelling draws all 1,345 regions in the "not measured" grey, because the
  join finds nothing and nothing errors.

* **Every other attribute is dropped.** GISCO carries 17 per polygon; the UI
  reads two, `nuts_id` and `name`. The rest is bytes a browser downloads on
  every page load and never looks at.

The output is a derived file and, unlike `exposure.parquet`, it is not
committed: it is a copy of the GISCO geometry, whose terms do not let a public
repository pass it on (`data/processed/DATA_NOTICE.md`). So this runs after
`python -m src.fetch` and before the first demo, on every machine. A machine
that skipped both - the hosted Streamlit app - gets it from `ensure`, which
downloads the GISCO layer from GISCO and builds the file on first use.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_io import load_vector, to_web  # noqa: E402

BOUNDARIES = ROOT / "data" / "raw" / "download" / "gisco_nuts3.geojson"
OUT = ROOT / "data" / "processed" / "regions.geojson"

#: GISCO's own column names, mapped to what the UI joins on. `NAME_LATN` rather
#: than `NUTS_NAME`: the latter is in the national script, so Greek and Bulgarian
#: regions arrive in alphabets the brief is not written in.
FIELDS = {"NUTS_ID": "nuts_id", "NAME_LATN": "name"}

#: Metres. One screen pixel is several kilometres at a continental viewport, so
#: detail below this cannot be seen - it is only downloaded. Lower it for a
#: single-country zoom, where the viewport is 20x tighter.
DEFAULT_TOLERANCE_M = 1000.0

#: Decimal degrees kept per coordinate. 4 is about 11 m at the equator, far below
#: the simplification above; the digits past it are noise that still costs bytes.
DEFAULT_DECIMALS = 4


def _round(coords, decimals: int):
    """Round a nested GeoJSON coordinate structure in place of its floats.

    Recursive because a coordinate list is a point, a ring, a polygon or a
    multipolygon depending on depth, and the depth is not known here.
    """
    if isinstance(coords[0], (int, float)):
        return [round(float(v), decimals) for v in coords]
    return [_round(part, decimals) for part in coords]


def build(
    source: Path = BOUNDARIES,
    tolerance_m: float = DEFAULT_TOLERANCE_M,
    decimals: int = DEFAULT_DECIMALS,
) -> dict:
    """The FeatureCollection the UI joins its numbers onto.

    Returns the parsed GeoJSON rather than writing it, so a test can assert on
    the join key without touching the filesystem.
    """
    gdf = load_vector(source)  # EPSG:3035, the metric CRS the tolerance is in
    missing = sorted(set(FIELDS) - set(gdf.columns))
    if missing:
        raise SystemExit(
            f"{source.name} has no {missing} column(s). Expected the GISCO NUTS "
            f"layer declared as `gisco_nuts3` in config/sources.yaml; got columns "
            f"{sorted(gdf.columns)}."
        )

    # preserve_topology keeps a polygon a polygon: the fast algorithm can push an
    # edge through its own neighbour, and a self-intersecting ring renders as a
    # black smear rather than failing.
    gdf = gdf.assign(geometry=gdf.geometry.simplify(tolerance_m, preserve_topology=True))
    gdf = to_web(gdf)

    features = [
        {
            "type": "Feature",
            "properties": {out: row[src] for src, out in FIELDS.items()},
            "geometry": {
                "type": geom["type"],
                "coordinates": _round(geom["coordinates"], decimals),
            },
        }
        for _, row in gdf.iterrows()
        if (geom := mapping(row.geometry))
    ]
    return {"type": "FeatureCollection", "features": features}


def write(collection: dict, out: Path = OUT) -> None:
    """Write the collection compactly, replacing `out` only once it is complete.

    separators: the default json dump pads every comma, which on ~1,345 polygons
    is megabytes of spaces the browser downloads. The temporary file matters for
    `ensure`: a page that reads `out` while it is being written would otherwise
    parse half a FeatureCollection.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".part")
    partial.write_text(json.dumps(collection, separators=(",", ":")), encoding="utf-8")
    partial.replace(out)


def ensure(out: Path = OUT, source: Path = BOUNDARIES) -> str | None:
    """Make sure `out` exists, downloading the GISCO layer if it must. None on success.

    The hosted Streamlit app clones the repository, and the repository cannot
    carry the polygons (module docstring). So the app fetches the boundaries
    from GISCO itself, the first time a page asks for the map: the copy comes
    from the publisher, not from this repository. A machine that already built
    `out` never touches the network, which keeps the venue demo offline.

    Returns the reason as text rather than raising, because the caller is a page
    that must still render everything that is not the map.
    """
    if out.exists():
        return None
    if not source.exists():
        from src.fetch import fetch_source  # requests, only when there is something to fetch

        result = fetch_source("gisco_nuts3")
        if not result.ok:
            return f"could not download the GISCO boundaries: {result.error}"
    try:
        write(build(source), out)
    # Broad on purpose: pyogrio, shapely and the column check each raise their
    # own type, and any of them must leave the page rendering without a map.
    except (Exception, SystemExit) as exc:
        return f"could not build {out.name}: {exc}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tolerance-m",
        type=float,
        default=DEFAULT_TOLERANCE_M,
        help=f"Simplification tolerance in METRES, applied in EPSG:3035 "
             f"(default {DEFAULT_TOLERANCE_M:g}). Lower it for a one-country zoom.",
    )
    parser.add_argument(
        "--decimals",
        type=int,
        default=DEFAULT_DECIMALS,
        help=f"Decimal degrees kept per coordinate (default {DEFAULT_DECIMALS}).",
    )
    parser.add_argument("--source", type=Path, default=BOUNDARIES)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(
            f"{args.source} is missing. Run `python -m src.fetch` first: the "
            f"boundaries are declared as `gisco_nuts3` in config/sources.yaml and "
            f"`data/raw/` is not committed."
        )

    collection = build(args.source, args.tolerance_m, args.decimals)
    write(collection, args.out)
    # relative_to(ROOT) raises on a relative `--out`, after the file is written.
    shown = args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out
    print(
        f"{shown}: {len(collection['features'])} regions, "
        f"{args.out.stat().st_size / 1e6:.1f} MB, simplified at "
        f"{args.tolerance_m:g} m, keyed on `{FIELDS['NUTS_ID']}`"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
