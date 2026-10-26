"""Build the challenge policy tool: one offline HTML file and a PNG snapshot of it.

Reads the frozen July 2021 tables (`data/processed/event_2021_*.parquet`), the
Europe tables (`exposure.parquet`), the cached EMS layers
(`data/raw/challenge_2021/ems/*.gpkg`, written by `scripts/event_2021.py`) and
the GISCO NUTS3 boundaries, and writes `docs/perso/policy_tool/policy_tool.html`
plus `policy_tool.png`. That folder is gitignored: the page carries GISCO
geometry, which the GISCO terms keep out of a public repository.

Geometry is simplified here, not in the page, and in EPSG:3035 so a tolerance is
a distance: the observed water at 15 m (it is drawn zoomed to one town), the NUTS3
context at 150 m on the event map and 3 km on the Europe map. That keeps the
single file under ~3 MB, which is what an e-mail attachment can carry.

The PNG comes from headless Chrome (or Edge) at 1600 px; with neither installed
the HTML is still written and the PNG step says why it was skipped.

Run:

    python scripts/build_policy_tool.py
    python scripts/build_policy_tool.py --question "..." --actor "..."
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from src import policy_tool as P

PROCESSED = ROOT / "data" / "processed"
EMS_CACHE = ROOT / "data" / "raw" / "challenge_2021" / "ems"
NUTS3 = ROOT / "data" / "raw" / "download" / "gisco_nuts3.geojson"
OUT_DIR = ROOT / "docs" / "perso" / "policy_tool"
CRS = "EPSG:3035"

OBSERVED_TOLERANCE_M = 15.0
NUTS_EVENT_TOLERANCE_M = 150.0
NUTS_EUROPE_TOLERANCE_M = 3000.0
#: Margin around the union of the AOIs, so the map shows the river context.
EVENT_PAD_M = 12_000.0
CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def _geojson(geom) -> dict:
    from shapely.geometry import mapping

    return mapping(geom)


def ems_layers(products: pd.DataFrame) -> tuple[dict, list, list]:
    """Per-AOI outline, first-pass water and later-pass water, in EPSG:3035.

    Uses the same notations as `scripts/event_2021.py` ("Flooded area" and
    "Flood trace") so the drawn water is the water the figures were counted on.
    The later-pass layer is drawn under the first pass, so what shows in the
    lighter colour is only the extra water.
    """
    import pyogrio
    import shapely

    from src import event2021 as E

    aoi: dict[str, list] = {}
    first, later = [], []
    for row in products.itertuples():
        gpkg = EMS_CACHE / f"{row.product_id}.gpkg"
        if not gpkg.exists():
            print(f"  missing {gpkg.name}: AOI drawn without it")
            continue
        key = P.aoi_key(row.emsr, row.aoi)
        area = pyogrio.read_dataframe(gpkg, layer="areaOfInterestA").to_crs(CRS)
        aoi.setdefault(key, []).extend(area.geometry)
        water = pyogrio.read_dataframe(gpkg, layer="observedEventA")
        water = water[water["notation"].isin(E.OBSERVED_NOTATIONS)].to_crs(CRS)
        if water.empty:
            continue
        geom = shapely.union_all(shapely.make_valid(water.geometry.values))
        geom = geom.intersection(shapely.union_all(area.geometry.values))
        (first if row.product_kind == "PRODUCT" else later).append(geom)
    outlines = {k: shapely.union_all(v).simplify(OBSERVED_TOLERANCE_M) for k, v in aoi.items()}
    simplify = lambda gs: [g.simplify(OBSERVED_TOLERANCE_M, preserve_topology=True)
                           for g in gs if not g.is_empty]
    return outlines, simplify(first), simplify(later)


def event_layers(products: pd.DataFrame) -> dict:
    """Everything the event map draws, as GeoJSON dicts in EPSG:3035 metres."""
    import geopandas as gpd
    import shapely

    outlines, first, later = ems_layers(products)
    minx, miny, maxx, maxy = shapely.union_all(list(outlines.values())).bounds
    bounds = (minx - EVENT_PAD_M, miny - EVENT_PAD_M, maxx + EVENT_PAD_M, maxy + EVENT_PAD_M)
    nuts = gpd.read_file(NUTS3, bbox=bounds) if NUTS3.exists() else None
    layers: dict = {"bounds": bounds, "nuts": [], "borders": [], "labels": []}
    if nuts is not None and not nuts.empty:
        nuts = nuts.to_crs(CRS)
        nuts["geometry"] = nuts.geometry.clip_by_rect(*bounds).simplify(NUTS_EVENT_TOLERANCE_M)
        nuts = nuts[~nuts.geometry.is_empty]
        layers["nuts"] = [(f"{r.NUTS_ID} {r.NAME_LATN}", _geojson(r.geometry)) for r in nuts.itertuples()]
        countries = nuts.dissolve("CNTR_CODE")
        # Country borders as lines: the shared edges of the dissolved countries,
        # not their outer frame (which is just the clipping rectangle).
        frame = shapely.box(*bounds).boundary.buffer(50)
        for code, g in countries.geometry.items():
            line = g.boundary.difference(frame)
            if not line.is_empty:
                layers["borders"].append(_line_geojson(line))
            point = g.representative_point()
            name = {"BE": "BELGIUM", "DE": "GERMANY", "NL": "NETHERLANDS",
                    "LU": "LUX.", "FR": "FRANCE"}.get(code, code)
            layers["labels"].append((name, point.x, point.y))
    layers["observed"] = [_geojson(g) for g in first]
    layers["monit"] = [_geojson(g) for g in later]
    layers["aoi"] = {k: _geojson(g) for k, g in outlines.items()}
    return layers


def _line_geojson(line) -> dict:
    """A border line as a degenerate 'Polygon' whose rings `path_d` can draw.

    `path_d` closes each ring with Z; for an open border that would draw a
    chord back to the start, so each line is stored as a ring of the line
    followed by its reverse - a zero-area shape whose outline is the line.
    """
    import shapely

    rings = []
    for part in getattr(line, "geoms", [line]):
        coords = list(shapely.get_coordinates(part))
        if len(coords) >= 2:
            rings.append([list(c) for c in coords + coords[::-1]])
    return {"type": "Polygon", "coordinates": rings}


def europe_features() -> list[dict]:
    """NUTS3 polygons for the Europe map, simplified at 3 km, back in lon/lat.

    `svgmap.choropleth_svg` expects WGS84 GeoJSON keyed on `nuts_id`, the shape
    `scripts/build_geometry.py` writes; 3 km is about one pixel at 900 px wide.
    """
    import geopandas as gpd

    if not NUTS3.exists():
        return []
    nuts = gpd.read_file(NUTS3).to_crs(CRS)
    nuts["geometry"] = nuts.geometry.simplify(NUTS_EUROPE_TOLERANCE_M, preserve_topology=True)
    nuts = nuts[~nuts.geometry.is_empty].to_crs("EPSG:4326")
    return [{"type": "Feature", "properties": {"nuts_id": r.NUTS_ID}, "geometry": _geojson(r.geometry)}
            for r in nuts.itertuples()]


def chrome() -> Path | None:
    """The first Chrome or Edge executable found, or None."""
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return Path(found)
    return next((p for p in CHROME_CANDIDATES if p.exists()), None)


def snapshot(page: Path, png: Path, width: int = 1600) -> str:
    """Render `page` headless at `width` px and crop the blank tail. Returns a status line."""
    exe = chrome()
    if exe is None:
        return "PNG skipped: no Chrome or Edge found."
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "full.png"
        cmd = [str(exe), "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--no-first-run", "--disable-extensions", f"--user-data-dir={tmp}",
               "--force-device-scale-factor=1", f"--window-size={width},9000",
               "--virtual-time-budget=3000", f"--screenshot={raw}", page.resolve().as_uri()]
        subprocess.run(cmd, check=False, capture_output=True, timeout=120)
        if not raw.exists():
            return "PNG skipped: the browser wrote no screenshot."
        image = Image.open(raw).convert("RGB")
        # Crop trailing rows that are pure page background.
        grey = image.convert("L")
        bottom = grey.height
        while bottom > 1 and grey.crop((0, bottom - 1, grey.width, bottom)).getextrema() == (255, 255):
            bottom -= 1
        image.crop((0, 0, image.width, min(grey.height, bottom + 24))).save(png, optimize=True)
    return f"PNG written by {exe.name}."


def main(argv: list[str] | None = None) -> int:
    """Read the tables and geometry, write the HTML and the PNG, print sizes."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--title", default="[TITLE]")
    parser.add_argument("--question", default="[DECISION QUESTION]")
    parser.add_argument("--recommendation", default="[RECOMMENDATION]")
    parser.add_argument("--actor", default="[NAMED ACTOR]")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args(argv)

    products = pd.read_parquet(PROCESSED / "event_2021_products.parquet")
    countries = pd.read_parquet(PROCESSED / "event_2021_countries.parquet")
    exposure = pd.read_parquet(PROCESSED / "exposure.parquet")

    page = P.render_page(
        countries=countries, products=products, exposure=exposure,
        event_layers=event_layers(products), europe_features=europe_features(),
        title=args.title, question=args.question,
        recommendation=args.recommendation, actor=args.actor,
        built=f"Built {dt.date.today().isoformat()}.",
    )
    args.out.mkdir(parents=True, exist_ok=True)
    html_path = args.out / "policy_tool.html"
    html_path.write_text(page, encoding="utf-8")
    print(f"{html_path}  {html_path.stat().st_size / 1e6:.2f} MB")
    if not args.no_png:
        png = args.out / "policy_tool.png"
        print(snapshot(html_path, png))
        if png.exists():
            print(f"{png}  {png.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
