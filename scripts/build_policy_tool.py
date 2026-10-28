"""Build the challenge policy tool: one offline HTML file and PNG snapshots of it.

Reads the frozen July 2021 tables (`data/processed/event_2021_*.parquet`), the
Europe tables (`exposure.parquet`, and `context.parquet` for the States absent
from the European risk-area layer), the cached EMS layers
(`data/raw/challenge_2021/ems/*.gpkg`, written by `scripts/event_2021.py`), the
JRC 1-in-100-year hazard raster and the GISCO NUTS3 boundaries, and writes
`docs/perso/policy_tool/policy_tool.html` plus PNG snapshots. That folder is
gitignored: the page carries GISCO geometry, which the GISCO terms keep out of a
public repository.

**The story maps are rasterised exactly as the figures were counted.** Each
place's first-pass water is put on the same EPSG:3035 20 m scoring grid as
`scripts/event_2021.py` (`window_grid`, `rasterize_on_grid`, cell-centre rule),
and the hazard mask is `validate.modelled_flood_mask` on the same raster, so a
cell drawn orange is a cell the table counted as outside the 1-in-100 map. The
picture is then reduced to at most `MAX_PIXELS` a side for size; a reduced pixel
holding any water is drawn as water, and as "outside" only when more of its
water cells are outside than inside, so the reduction never tips a tie toward
the alarming colour.

The PNGs come from headless Chrome (or Edge); with neither installed the HTML
is still written and the step says why it was skipped.

Run:

    python scripts/build_policy_tool.py
    python scripts/build_policy_tool.py --question "..." --actor "..."
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from src import policy_tool as P
from src.story_maps import geojson_pixels, lines as _lines, png_data_uri, reduce_classes

PROCESSED = ROOT / "data" / "processed"
EMS_CACHE = ROOT / "data" / "raw" / "challenge_2021" / "ems"
NUTS3 = ROOT / "data" / "raw" / "download" / "gisco_nuts3.geojson"
NATURAL_EARTH = ROOT / "data" / "raw" / "download" / "natural_earth_countries.zip"
COUNTRY_LABELS = {"BE": "BELGIUM", "DE": "GERMANY", "NL": "NETHERLANDS"}
OUT_DIR = ROOT / "docs" / "perso" / "policy_tool"
CRS = "EPSG:3035"

MAX_PIXELS = 900
#: Margin around the observed water, in 20 m cells (1.5 km), and the smallest
#: frame side (6 km), so a small place still shows its valley.
CROP_PAD_CELLS = 75
CROP_MIN_CELLS = 300
NUTS_TOLERANCE_M = 100.0
NUTS_EUROPE_TOLERANCE_M = 5000.0
LOCATOR_WIDTH = 600.0
LOCATOR_PAD_M = 15_000.0
LOCATOR_NUTS_TOLERANCE_M = 1000.0
SCREEN_WIDTHS = (1024, 1280, 1600, 1920)
CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)


def _nuts(bounds) -> "pd.DataFrame | None":
    """NUTS3 polygons intersecting an EPSG:3035 box, or None without the file."""
    import geopandas as gpd

    if not NUTS3.exists():
        return None
    frame = gpd.read_file(NUTS3, bbox=tuple(bounds))
    return frame.to_crs(CRS) if frame.crs and frame.crs.to_string() != CRS else frame


def _natural_earth_countries(bounds) -> dict:
    """Natural Earth country polygons meeting an EPSG:3035 box, keyed by ISO2; {} without the file."""
    import geopandas as gpd
    import shapely

    if not NATURAL_EARTH.exists():
        return {}
    world = gpd.read_file(f"zip://{NATURAL_EARTH.as_posix()}", columns=["ISO_A2_EH"]).to_crs(CRS)
    world = world[world.intersects(shapely.box(*bounds))]
    return dict(zip(world["ISO_A2_EH"], world.geometry))


def border_lines(countries: dict, frame, to_xy) -> tuple[str, list]:
    """Country borders inside `frame` as one SVG path, and a label per large country.

    The frame edge is cut away, so a border is only drawn where two countries
    meet or a coast runs, never along the map's own edge. A country is labelled
    when more than 8 % of the frame lies in it, so a sliver of France at the
    corner gets no name.
    """
    lines, labels = [], []
    for code, geom in sorted(countries.items()):
        country = geom.simplify(500)
        edge = country.boundary.difference(frame.boundary.buffer(100)).intersection(frame)
        lines += _lines(edge)
        inside = country.intersection(frame)
        name = COUNTRY_LABELS.get(code)
        if name and inside.area > 0.08 * frame.area:
            p = inside.representative_point()
            labels.append((name, *to_xy(p.x, p.y)))
    return P.line_d(lines, to_xy), labels


def place_layer(product_id: str, *, with_nuts: bool = True) -> dict | None:
    """The story-map layer of one first-pass product: PNG, outline, NUTS, towns, scale.

    Also returns the AOI outline and the observed water as GeoJSON in the PNG's
    pixel units (`outline_geojson`, `observed_geojson`) and the frame in
    EPSG:3035 metres (`bounds_3035`), which is what the React app overlays;
    the single-file page only uses the SVG path strings. `with_nuts=False`
    leaves the GISCO lines out, for an artefact that must not carry them.
    """
    import pyogrio
    import shapely
    from pyproj import Transformer

    from scripts.event_2021 import _to_grid_crs, _union
    from scripts.validate_2021 import HAZARD, rasterize_on_grid, window_grid
    from src import event2021 as E
    from src import validate as V

    gpkg = EMS_CACHE / f"{product_id}.gpkg"
    if not gpkg.exists():
        print(f"  missing {gpkg.name}: no map for this place")
        return None
    aoi = _union(pyogrio.read_dataframe(gpkg, layer="areaOfInterestA").geometry)
    events = pyogrio.read_dataframe(gpkg, layer="observedEventA")
    observed = _union(events[events["notation"].isin(E.OBSERVED_NOTATIONS)].geometry)
    observed = _union([observed.intersection(aoi)]) if observed is not None else None
    grid = window_grid(tuple(aoi.bounds))
    aoi_mask = rasterize_on_grid(_to_grid_crs(aoi), grid)
    obs_mask = (rasterize_on_grid(_to_grid_crs(observed), grid) & aoi_mask
                if observed is not None else np.zeros(grid.shape, bool))
    wet = V.modelled_flood_mask(V.read_depth_on_grid(str(HAZARD).format(rp=100), grid))

    rows, cols = np.nonzero(obs_mask if obs_mask.any() else aoi_mask)
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    grow_r = max(CROP_PAD_CELLS, (CROP_MIN_CELLS - (r1 - r0)) // 2)
    grow_c = max(CROP_PAD_CELLS, (CROP_MIN_CELLS - (c1 - c0)) // 2)
    r0, r1 = max(0, r0 - grow_r), min(grid.height, r1 + grow_r)
    c0, c1 = max(0, c0 - grow_c), min(grid.width, c1 + grow_c)
    crop = (slice(r0, r1), slice(c0, c1))
    k = max(1, math.ceil(max(r1 - r0, c1 - c0) / MAX_PIXELS))
    classes = reduce_classes(obs_mask[crop], wet[crop], aoi_mask[crop], k)
    height, width = classes.shape

    pixel = grid.resolution_m * k
    left, top = grid.left + c0 * grid.resolution_m, grid.top - r0 * grid.resolution_m
    box = (left, top - height * pixel, left + width * pixel, top)

    def to_px(x, y):
        return (x - left) / pixel, (top - y) / pixel

    outline = P.line_d(_lines(_to_grid_crs(aoi).iloc[0]), to_px)
    nuts_d = ""
    nuts = _nuts(box) if with_nuts else None
    if nuts is not None and len(nuts):
        frame = shapely.box(*box)
        geoms = [g.simplify(NUTS_TOLERANCE_M).boundary.intersection(frame) for g in nuts.geometry]
        nuts_d = P.line_d([l for g in geoms for l in _lines(g)], to_px)
    to_m = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    towns = []
    for name, river, lon, lat in P.TOWNS:
        x, y = to_px(*to_m.transform(lon, lat))
        if 0.02 * width <= x <= 0.98 * width and 0.04 * height <= y <= 0.98 * height:
            towns.append((f"{name} ({river})", x, y))
    span_km = width * pixel / 1000
    km = next((s for s in (1, 2, 5, 10, 20, 50) if s >= span_km / 6), 50)
    observed_m = _to_grid_crs(observed).iloc[0] if observed is not None else None
    return {"png": png_data_uri(classes), "width": width, "height": height,
            "outline": outline, "nuts": nuts_d, "towns": towns,
            "scale": (km, km * 1000 / pixel), "pixel_m": pixel, "bounds_3035": box,
            "outline_geojson": geojson_pixels(_to_grid_crs(aoi).iloc[0], to_px, pixel / 2),
            "observed_geojson": geojson_pixels(observed_m, to_px, pixel / 2)}


def locator(products: pd.DataFrame, *, with_nuts: bool = True) -> dict | None:
    """The overview map: country borders and every first-pass AOI, in a 600-wide viewBox.

    `nuts` holds the NUTS3 lines of the window at 1 km, for context under the
    borders, and the borders are the NUTS3 polygons dissolved by country.
    `with_nuts=False` drops every GISCO-derived line and draws the borders from
    Natural Earth instead: public domain, so the public build still shows which
    country each mapped area is in.
    """
    import pyogrio
    import shapely

    shapes = {}
    for row in products[products["product_kind"] == "PRODUCT"].itertuples():
        gpkg = EMS_CACHE / f"{row.product_id}.gpkg"
        if gpkg.exists():
            area = pyogrio.read_dataframe(gpkg, layer="areaOfInterestA").to_crs(CRS)
            shapes[P.aoi_key(row.emsr, row.aoi)] = shapely.union_all(area.geometry.values)
    if not shapes:
        return None
    minx, miny, maxx, maxy = shapely.union_all(list(shapes.values())).bounds
    box = (minx - LOCATOR_PAD_M, miny - LOCATOR_PAD_M, maxx + LOCATOR_PAD_M, maxy + LOCATOR_PAD_M)
    scale = LOCATOR_WIDTH / (box[2] - box[0])

    def to_xy(x, y):
        return (x - box[0]) * scale, (box[3] - y) * scale

    out = {"width": LOCATOR_WIDTH, "height": (box[3] - box[1]) * scale, "labels": [],
           "borders": "", "nuts": "", "aoi": {}}
    frame = shapely.box(*box)
    nuts = _nuts(box) if with_nuts else None
    if nuts is not None and len(nuts):
        regions = [g.simplify(LOCATOR_NUTS_TOLERANCE_M).boundary.intersection(frame)
                   for g in nuts.geometry]
        out["nuts"] = P.line_d([l for g in regions for l in _lines(g)], to_xy)
        countries = {code: shapely.union_all(group.geometry.values)
                     for code, group in nuts.groupby("CNTR_CODE")}
    else:
        countries = _natural_earth_countries(box)
    out["borders"], out["labels"] = border_lines(countries, frame, to_xy)
    for key, geom in shapes.items():
        out["aoi"][key] = P.path_d(shapely.geometry.mapping(geom.simplify(200)), to_xy)
    return out


def europe_features() -> list[dict]:
    """NUTS3 polygons for the Europe map, simplified at 5 km, back in lon/lat."""
    import geopandas as gpd
    from shapely.geometry import mapping

    if not NUTS3.exists():
        return []
    nuts = gpd.read_file(NUTS3)
    nuts = nuts.to_crs(CRS) if nuts.crs.to_string() != CRS else nuts
    nuts["geometry"] = nuts.geometry.simplify(NUTS_EUROPE_TOLERANCE_M, preserve_topology=True)
    nuts = nuts[~nuts.geometry.is_empty].to_crs("EPSG:4326")
    return [{"type": "Feature", "properties": {"nuts_id": r.NUTS_ID}, "geometry": mapping(r.geometry)}
            for r in nuts.itertuples()]


def chrome() -> Path | None:
    """The first Chrome or Edge executable found, or None."""
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return Path(found)
    return next((p for p in CHROME_CANDIDATES if p.exists()), None)


def screenshot(page: Path, png: Path, width: int, height: int = 9000, crop: bool = True) -> bool:
    """Render `page` headless at `width` x `height` px; crop the blank tail if asked."""
    exe = chrome()
    if exe is None:
        return False
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "shot.png"
        subprocess.run([str(exe), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--no-first-run", "--disable-extensions", f"--user-data-dir={tmp}",
                        "--force-device-scale-factor=1", f"--window-size={width},{height}",
                        "--virtual-time-budget=3000", f"--screenshot={raw}", page.resolve().as_uri()],
                       check=False, capture_output=True, timeout=180)
        if not raw.exists():
            return False
        image = Image.open(raw).convert("RGB")
        if crop:
            grey = image.convert("L")
            bottom = grey.height
            while bottom > 1 and grey.crop((0, bottom - 1, grey.width, bottom)).getextrema() == (255, 255):
                bottom -= 1
            image = image.crop((0, 0, image.width, min(grey.height, bottom + 24)))
        image.save(png, optimize=True)
    return True


def main(argv: list[str] | None = None) -> int:
    """Read the tables and geometry, write the HTML and the PNG snapshots, print sizes."""
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
    context = pd.read_parquet(PROCESSED / "context.parquet")

    first = P.first_pass(products)
    layers = {}
    for place in P.place_records(products):
        print(f"  map {place['key']} ({place['label']})", flush=True)
        layer = place_layer(str(first[place["key"]]["product_id"]))
        if layer:
            layers[place["key"]] = layer
    page = P.render_page(
        countries=countries, products=products, exposure=exposure,
        place_layers=layers, locator=locator(products), europe_features=europe_features(),
        title=args.title, question=args.question,
        recommendation=args.recommendation, actor=args.actor,
        unreported=P.unreported_countries(context),
        built=f"Built {dt.date.today().isoformat()}.",
    )
    args.out.mkdir(parents=True, exist_ok=True)
    html_path = args.out / "policy_tool.html"
    html_path.write_text(page, encoding="utf-8")
    print(f"{html_path}  {html_path.stat().st_size / 1e6:.2f} MB")
    if args.no_png:
        return 0
    shots = [(args.out / "policy_tool.png", 1600, 9000, True),
             (args.out / "policy_tool_1280_hero.png", 1280, 800, False),
             (args.out / "policy_tool_1280_story_ahr.png", 1280, 1700, False)]
    for png, width, height, crop in shots:
        if screenshot(html_path, png, width, height, crop):
            print(f"{png}  {png.stat().st_size / 1e6:.2f} MB")
        else:
            print(f"{png.name} skipped: no Chrome or Edge, or no screenshot written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
