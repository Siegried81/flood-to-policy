"""
map.py - Interactive exposure map of the July 2021 floods (Belgium, Germany, Netherlands).

Layers
  1. Flooded areas   Copernicus EMS Rapid Mapping (EMSR517 DE, EMSR518 BE, EMSR520 NL),
                     coloured by OBAT buildings or estimated residents inside each polygon.
  2. Buildings       GHS-OBAT R2024A points aggregated to a 400 m hexagonal grid.
  3. Population      GHS-POP E2020 R2023A residents per 30 arc-second cell.
  4. Candidate shelters  schools, sports halls, community centres (OSM), from the cache built by shelters.py.
  5. Planning scenario   exploratory capacity / allocation scenario in the browser (planning/: demand, alloc.js, ui.js).
  6. Exposed residents and scenario-based planning priority per fixed 400 m hexagon (planning/scenes.js, priority.js).
  7. Context: vulnerable facilities and critical infrastructure with their asset screening scores (priority/assets.js,
     records from priority_map.py, cached in cache/priority/assets.json).
The page is organised in four presentation scenes (What happened? Who was exposed? Where could they go? Where to start?).

Data is read directly from GCS (read-only) and limited to the EMS areas of interest:
OBAT through a spatial mask, GHS-POP through a raster window. Intermediate results are
cached in ./cache so styling changes re-run in seconds.

Usage:  python map.py            # uses cache if present
        python map.py --refresh  # re-read everything from GCS
Output: flood_map.html
"""
import argparse
import base64
import io
import hashlib
import json
import re
from pathlib import Path

import folium
import gcsfs
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import pyogrio
import rasterio
import shapely
from PIL import Image
from pyproj import Transformer
from folium import plugins
from rasterio.features import geometry_mask, rasterize
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.windows import Window, from_bounds

import shelters
from planning import demand as planning_demand

# --------------------------------------------------------------------------- config
BUCKET = "datasets_challenge/working_data"
OBAT = {
    "BEL": "obat_be/GHS_OBAT_GPKG_BEL_E2020_R2024A_V1_0/GHS_OBAT_GPKG_BEL_E2020_R2024A_V1_0.gpkg",
    "NLD": "obat_nl/GHS_OBAT_GPKG_NLD_E2020_R2024A_V1_0/GHS_OBAT_GPKG_NLD_E2020_R2024A_V1_0.gpkg",
    "DEU": "obat_de/GHS_OBAT_GPKG_DEU_E2020_R2024A_V1_0/GHS_OBAT_GPKG_DEU_E2020_R2024A_V1_0.gpkg",
}
POP = "ghs_pop/GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0/GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0.tif"
ACTIVATION_COUNTRY = {"EMSR518": "BEL", "EMSR517": "DEU", "EMSR520": "NLD"}
COUNTRY_NAME = {"BEL": "Belgium", "DEU": "Germany", "NLD": "Netherlands"}

METRIC_CRS = "EPSG:3035"   # equal-area, metres: all areas, counts and hexes are computed here
WEB_CRS = "EPSG:4326"
HEX_WIDTH = 400            # m, distance between opposite edges of a hexagon
AOI_BUFFER = 1000          # m, read buffer around the EMS areas of interest
SIMPLIFY_TOL = 10          # m, flood polygon simplification (well below the EMS mapping scale)
MIN_FLOOD_M2 = 500         # drop flood slivers smaller than this after dissolving
COORD_PRECISION = 1e-5     # degrees (~1 m) for flood coordinates written to the HTML
GRID_PRECISION = 1e-4      # degrees (~10 m) for hexagons and population cells

ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
ESRI_ATTR = "Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors"

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT_HTML = HERE / "flood_map.html"
PLANNING = HERE / "planning"
SCENARIO_DEFAULT_KM = 5    # scenario assumption shown on the slider (1-25 km), not a standard
PRIORITY_WEIGHTS = {"E": 50, "G": 50}   # area priority: illustrative starting assumption (slider values, normalised)
HEX_ZOOM = 12              # from this zoom the fixed hexagons are drawn; below it, overview circles / dots


# Remote GeoPackage reads: fetch large chunks and keep them cached (default 16 KB per request is slow)
GDAL_REMOTE = {"CPL_VSIL_CURL_CHUNK_SIZE": 4_194_304, "CPL_VSIL_CURL_CACHE_SIZE": 1_073_741_824,
               "GDAL_HTTP_MULTIPLEX": "YES", "GDAL_HTTP_VERSION": "2"}
pyogrio.set_gdal_config_options(GDAL_REMOTE)


def vsigs(path):
    return f"/vsigs/{BUCKET}/{path}"


# --------------------------------------------------------------------------- 1. EMS
def load_ems(fs):
    """Read every observedEvent layer (DEL + GRA): 'Flooded area' and 'Flood trace' polygons.

    Flood trace = area flooded earlier but already dry on the image (key in the Ahr / Erft towns).
    """
    events, aois = [], []
    for shp in sorted(fs.glob(f"{BUCKET}/ems_*/*/*_observedEventA_*.shp")):
        act, aoi, kind, phase = re.search(r"(EMSR\d+)_(AOI\d+)_(DEL|GRA)_(PRODUCT|MONIT\d+)", shp).groups()
        # The image acquisition time is not in the vector package; the XML only holds the map production date.
        date = re.search(r"<gco:Date>([\d-]+)</gco:Date>", fs.cat(shp[:-4] + ".xml").decode()).group(1)
        g = gpd.read_file("/vsigs/" + shp)
        g = g[(g["event_type"] == "5-Flood") & g["notation"].isin(["Flooded area", "Flood trace"])]
        events.append(g[["geometry", "notation"]].assign(activation=act, aoi=aoi,
                                                          source=f"{kind} {phase.lower()} ({date})"))
        aoi_shp = fs.glob(shp.rsplit("/", 1)[0] + "/*_areaOfInterestA_*.shp")[0]
        aois.append(gpd.read_file("/vsigs/" + aoi_shp)[["geometry"]].assign(activation=act))

    events = pd.concat(events, ignore_index=True).to_crs(METRIC_CRS)
    events["geometry"] = events.make_valid()
    aois = pd.concat(aois, ignore_index=True).to_crs(METRIC_CRS)

    # Union overlapping products (first image, monitoring, grading) into one maximum observed
    # extent per activation, so no area or building is counted twice. Traces overlapping a
    # flooded area are removed from the traces.
    wet = events[events["notation"] == "Flooded area"].dissolve("activation").reset_index()
    trace = events[events["notation"] == "Flood trace"].dissolve("activation").reset_index()
    trace = gpd.overlay(trace[["activation", "geometry"]], gpd.GeoDataFrame(geometry=[wet.union_all()], crs=METRIC_CRS),
                        how="difference")
    flood = pd.concat([wet[["activation", "geometry"]].assign(kind="flooded"), trace.assign(kind="trace")], ignore_index=True)
    flood = flood.explode(index_parts=False).reset_index(drop=True)
    flood = flood[flood.geom_type == "Polygon"]
    flood = flood[flood.area >= MIN_FLOOD_M2].reset_index(drop=True)

    # List which products contributed to each dissolved polygon
    pts = events.set_geometry(events.representative_point())
    hit = gpd.sjoin(pts, flood[["geometry"]], predicate="intersects")
    flood["sources"] = hit.groupby("index_right")["source"].agg(lambda s: ", ".join(sorted(set(s))))
    flood["area_ha"] = flood.area / 1e4

    return flood, aois


# --------------------------------------------------------------------------- 2. GHS-POP
def load_population(region_wgs):
    """Windowed read of GHS-POP E2020 over the region; returns non-zero cells + grid transform."""
    minx, miny, maxx, maxy = region_wgs.bounds
    with rasterio.open(vsigs(POP)) as src:
        r0, c0 = src.index(minx, maxy)
        r1, c1 = src.index(maxx, miny)
        win = Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1)
        arr = src.read(1, window=win)
        tr = src.window_transform(win)

    rows, cols = np.nonzero(arr > 0)  # zero = no residents -> left transparent
    x0, y0 = tr.c + cols * tr.a, tr.f + rows * tr.e
    cells = gpd.GeoDataFrame(
        {"key": rows * arr.shape[1] + cols, "pop": arr[rows, cols]},
        geometry=shapely.box(x0, y0 + tr.e, x0 + tr.a, y0), crs=WEB_CRS,
    )
    cells = cells[shapely.contains_xy(region_wgs, x0 + tr.a / 2, y0 + tr.e / 2)]
    return cells.reset_index(drop=True), tr, arr.shape[1]


# --------------------------------------------------------------------------- 3. OBAT
def load_buildings(read_areas):
    """Read OBAT points inside the areas of interest only, from all three countries.

    GDAL queries the spatial index with the mask's envelope, so each AOI is read separately
    (small envelope) and buildings in overlapping AOIs are de-duplicated by id.
    """
    parts = []
    for iso, path in OBAT.items():
        xmin, ymin, xmax, ymax = pyogrio.read_info(vsigs(path))["total_bounds"]
        n = 0
        for part in read_areas:
            if not part.intersects(shapely.box(xmin, ymin, xmax, ymax)):
                continue
            df = pyogrio.read_dataframe(vsigs(path), columns=["id", "country", "use"], mask=part)
            n += len(df)
            parts.append(df)
        print(f"  OBAT {iso}: {n:,} buildings read", flush=True)
    return pd.concat(parts, ignore_index=True).drop_duplicates("id").drop(columns="id")


def hex_index(x, y, width=HEX_WIDTH):
    """Axial (q, r) index of pointy-top hexagons with the given flat-to-flat width (metres)."""
    size = width / np.sqrt(3)  # circumradius
    q = (np.sqrt(3) / 3 * x - y / 3) / size
    r = (2 / 3 * y) / size
    # cube rounding
    s = -q - r
    rq, rr, rs = np.round(q), np.round(r), np.round(s)
    dq, dr, ds = np.abs(rq - q), np.abs(rr - r), np.abs(rs - s)
    fix_q = (dq > dr) & (dq > ds)
    fix_r = ~fix_q & (dr > ds)
    rq = np.where(fix_q, -rr - rs, rq)
    rr = np.where(fix_r, -rq - rs, rr)
    return rq.astype(np.int64), rr.astype(np.int64)


def hex_polygons(q, r, width=HEX_WIDTH):
    size = width / np.sqrt(3)
    cx = size * np.sqrt(3) * (q + r / 2)
    cy = size * 1.5 * r
    ang = np.deg2rad(np.arange(6) * 60 - 30)
    xs = cx[:, None] + size * np.cos(ang)[None, :]
    ys = cy[:, None] + size * np.sin(ang)[None, :]
    return shapely.polygons(np.stack([xs, ys], axis=-1))


def mode(s):
    return s.value_counts().index[0]


# --------------------------------------------------------------------------- 4. combine
def prepare(refresh=False):
    CACHE.mkdir(exist_ok=True)
    files = {n: CACHE / f"{n}.parquet" for n in ["flood", "aoi", "hexes", "pop"]}
    if not refresh and all(f.exists() for f in files.values()):
        return {n: gpd.read_parquet(f) for n, f in files.items()}

    fs = gcsfs.GCSFileSystem(token="google_default")
    print("Reading EMS ...")
    flood, aoi = load_ems(fs)
    # Individual AOIs (+ buffer) for reading; AOIs lying entirely inside another are skipped
    areas = aoi.buffer(AOI_BUFFER).to_crs(WEB_CRS)
    areas = [a for i, a in enumerate(areas) if not any(a.within(o) for j, o in enumerate(areas) if j != i and not o.equals(a))]
    areas = list(gpd.GeoSeries(areas).normalize().drop_duplicates())
    region_wgs = shapely.union_all(areas)
    aoi = aoi.dissolve("activation").reset_index()[["activation", "geometry"]]  # outline for display

    print("Reading GHS-POP window ...")
    cells, tr, ncols = load_population(region_wgs)

    print("Reading OBAT (masked to the EMS areas of interest) ...")
    b = load_buildings(areas)

    # Link each building to its population cell
    lon, lat = b.geometry.x.to_numpy(), b.geometry.y.to_numpy()
    b["key"] = np.floor((lat - tr.f) / tr.e).astype(np.int64) * ncols + np.floor((lon - tr.c) / tr.a).astype(np.int64)
    b = b.to_crs(METRIC_CRS)

    # Residents per residential building: each cell's residents shared equally among its
    # residential buildings (use == 1). A simple dasymetric estimate, not an observed count.
    res_per_cell = b[b["use"] == 1].groupby("key").size()
    cells["n_res"] = cells["key"].map(res_per_cell).fillna(0).astype(int)
    rpb = cells.set_index("key")["pop"] / cells.set_index("key")["n_res"].replace(0, np.nan)
    b["residents"] = np.where(b["use"] == 1, b["key"].map(rpb).fillna(0), 0.0)

    # ---- flood polygon metrics
    j = gpd.sjoin(b[["use", "residents", "geometry"]], flood[["geometry"]], predicate="within")
    g = j.groupby("index_right")
    flood["n_bldg"] = g.size()
    flood["n_res_bldg"] = g["use"].apply(lambda u: (u == 1).sum())
    flood["residents"] = g["residents"].sum()
    flood = flood.fillna({"n_bldg": 0, "n_res_bldg": 0, "residents": 0})
    # Fallback: cells with residents but no residential building -> area-weighted share
    orphan = cells[cells["n_res"] == 0].to_crs(METRIC_CRS)
    orphan["cell_m2"] = orphan.area
    ov = gpd.overlay(flood[["geometry"]].reset_index(), orphan[["pop", "cell_m2", "geometry"]], how="intersection")
    ov_res = (ov["pop"] * ov.area / ov["cell_m2"]).groupby(ov["index"]).sum()
    flood["residents"] = flood["residents"].add(ov_res, fill_value=0)
    flood["country"] = flood["activation"].map(ACTIVATION_COUNTRY)
    print(f"  orphan cells (pop > 0, no residential building): {len(orphan):,}, residents assigned by area: {ov_res.sum():,.0f}")

    # ---- hex aggregation of buildings
    b["q"], b["r"] = hex_index(b.geometry.x.to_numpy(), b.geometry.y.to_numpy())
    hx = b.groupby(["q", "r"]).agg(n_bldg=("use", "size"), n_res=("use", lambda u: (u == 1).sum()),
                                   country=("country", mode)).reset_index()
    hexes = gpd.GeoDataFrame(hx, geometry=hex_polygons(hx["q"].to_numpy(), hx["r"].to_numpy()), crs=METRIC_CRS)

    # ---- country of each population cell (majority of its buildings; empty if none)
    cell_country = b.groupby("key")["country"].agg(mode)
    cells["country"] = cells["key"].map(cell_country)

    flood.to_parquet(files["flood"])
    aoi.to_parquet(files["aoi"])
    hexes.to_parquet(files["hexes"])
    cells.to_parquet(files["pop"])
    return {n: gpd.read_parquet(f) for n, f in files.items()}


# --------------------------------------------------------------------------- 4b. EFAS modelled hazard
EFAS = {rp: f"cems-efas/Europe_RP{rp}_filled_depth.tif" for rp in (10, 100, 500)}
EFAS_STEP = 0.1        # m, depth resolution stored in the PNG (palette index = depth / step, 1..255)
EFAS_RES_MERC = 90     # m in Web Mercator units per output pixel (~57 m on the ground at 50.5° N)


def efas_region(aoi):
    """Same read region as OBAT / GHS-POP: EMS areas of interest + buffer, in WGS84."""
    return gpd.GeoSeries([aoi.buffer(AOI_BUFFER).union_all()], crs=METRIC_CRS).to_crs(WEB_CRS).iloc[0]


def load_efas(rp, region_wgs, refresh=False):
    """Windowed read of one EFAS depth map (m) over the region; cells outside the region set to 0. Cached."""
    f = CACHE / f"efas_rp{rp}.npz"
    if f.exists() and not refresh:
        z = np.load(f)
        return z["depth"], rasterio.Affine(*z["transform"])
    with rasterio.open(vsigs(EFAS[rp])) as src:
        win = from_bounds(*region_wgs.bounds, src.transform).round_offsets().round_lengths()
        depth = src.read(1, window=win, masked=True).filled(0).astype("float32")  # nodata (-9999) -> 0
        tr = src.window_transform(win)
    depth[geometry_mask([region_wgs], depth.shape, tr)] = 0
    CACHE.mkdir(exist_ok=True)
    np.savez_compressed(f, depth=depth, transform=np.array(tr)[:6])
    return depth, tr


def efas_palette():
    """256 RGB entries: entry i = colour of the class of depth i * 0.1 m, with i hidden in the lowest bits
    (max. 7/255 per channel, invisible) so a click on the image can read the depth back."""
    i = np.arange(256)
    cls = np.clip(np.digitize(i * EFAS_STEP, EFAS_BREAKS) - 1, 0, len(EFAS_BREAKS) - 1)
    base = (np.array([matplotlib.colors.to_rgb(EFAS_COLORS[c]) for c in cls]) * 255).round().astype(int)
    pal = np.stack([(base[:, 0] & ~7) | (i & 7), (base[:, 1] & ~7) | ((i >> 3) & 7), (base[:, 2] & ~3) | (i >> 6)], axis=1)
    return pal.astype("uint8")


def efas_png(depth, tr):
    """Depth grid -> transparent paletted PNG in Web Mercator (Leaflet stretches images linearly in Mercator)."""
    idx = np.clip(np.round(depth / EFAS_STEP), 0, 255).astype("uint8")
    idx[(depth > 0) & (idx == 0)] = 1
    h0, w0 = idx.shape
    dst_tr, w, h = calculate_default_transform(WEB_CRS, "EPSG:3857", w0, h0, *array_bounds(h0, w0, tr),
                                               resolution=EFAS_RES_MERC)
    out = np.zeros((h, w), "uint8")
    reproject(idx, out, src_transform=tr, src_crs=WEB_CRS, dst_transform=dst_tr, dst_crs="EPSG:3857",
              resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
    img = Image.frombytes("P", (w, h), out.tobytes())
    img.putpalette(efas_palette().flatten().tolist())
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, transparency=0)  # index 0 = no modelled water
    x0, y0, res = dst_tr.c, dst_tr.f, dst_tr.a
    lon, lat = Transformer.from_crs("EPSG:3857", WEB_CRS, always_xy=True).transform([x0, x0 + w * res], [y0 - h * res, y0])
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return uri, [[lat[0], lon[0]], [lat[1], lon[1]]], {"x0": x0, "y0": y0, "res": res, "w": w, "h": h}


def efas_comparison(flood, efas):
    """Share of the observed EMS flood area (flooded + traces) inside the EFAS 100-year zone, in the 500-year
    zone only, or outside both. Computed on the EFAS grid (3 arc-seconds), cells weighted by their true area."""
    (d100, tr), (d500, tr500) = efas[100], efas[500]
    assert d100.shape == d500.shape and tr == tr500
    codes = {"BEL": 1, "DEU": 2, "NLD": 3}
    fl = flood.to_crs(WEB_CRS)
    grid = rasterize(zip(fl.geometry, fl["country"].map(codes)), out_shape=d100.shape, transform=tr, fill=0, dtype="uint8")
    weight = np.cos(np.deg2rad(tr.f + (np.arange(grid.shape[0]) + 0.5) * tr.e))[:, None]  # cell area ~ cos(lat)
    in100, in500 = d100 > 0, (d500 > 0) & ~(d100 > 0)
    rows = {}
    for iso, code in list(codes.items()) + [("Total", None)]:
        m = grid > 0 if code is None else grid == code
        w = np.broadcast_to(weight, grid.shape)
        tot = max(w[m].sum(), 1e-9)  # guard: country without observed flooding
        a, b = w[m & in100].sum() / tot, w[m & in500].sum() / tot
        rows[iso] = {"in100": a, "only500": b, "outside": 1 - a - b}
    return rows


# --------------------------------------------------------------------------- 4c. EMS hydrography (normal water)
HYDRO_POLY_TYPES = ["BH080-Lake", "BH130-Reservoir", "BH140-River", "BH141-Stream"]  # not "Land Subject to Inundation"
HYDRO_LINE_TYPES = ["BH140-River", "BH141-Stream"]
HYDRO_SIMPLIFY = 20      # m, display simplification for the reference water layer
MIN_WATER_M2 = 5000      # drop ponds below 0.5 ha
WATER_COLOR = "#0a1f3d"
WATER_MIN_ZOOM = 11      # the dense stream network would swamp the overview below this zoom


def load_hydro(refresh=False):
    """Normal (pre-event) water from the EMS reference layers, de-duplicated across products. Cached.

    Returns one row per water body polygon (kind='body') and one MultiLineString with all rivers/streams (kind='line').
    """
    f = CACHE / "hydro.parquet"
    if f.exists() and not refresh:
        return gpd.read_parquet(f)
    fs = gcsfs.GCSFileSystem(token="google_default")

    def read(layer, types):
        g = pd.concat([gpd.read_file("/vsigs/" + shp, columns=["obj_type"])
                       for shp in fs.glob(f"{BUCKET}/ems_*/*/*_{layer}_*.shp")], ignore_index=True)
        return g[g["obj_type"].isin(types)].to_crs(METRIC_CRS)

    bodies = read("hydrographyA", HYDRO_POLY_TYPES)
    bodies = gpd.GeoDataFrame(geometry=[bodies.make_valid().union_all()], crs=METRIC_CRS).explode(index_parts=False)
    bodies = bodies[bodies.geom_type == "Polygon"]
    bodies = bodies[bodies.area >= MIN_WATER_M2].assign(kind="body")
    lines = read("hydrographyL", HYDRO_LINE_TYPES)
    lines = lines[~pd.Series(shapely.to_wkb(shapely.normalize(lines.geometry.values))).duplicated().to_numpy()]
    lines = gpd.GeoDataFrame({"kind": ["line"]}, geometry=[shapely.multilinestrings(
        shapely.get_parts(lines.geometry.values))], crs=METRIC_CRS)
    hydro = pd.concat([bodies, lines], ignore_index=True)
    CACHE.mkdir(exist_ok=True)
    hydro.to_parquet(f)
    return hydro


# --------------------------------------------------------------------------- 5. colour classes
def ramp(cmap, n, lo, hi):
    """n colours sampled from a matplotlib colormap between lo and hi (avoids near-white / near-black ends)."""
    return [matplotlib.colors.to_hex(matplotlib.colormaps[cmap](v)) for v in np.linspace(lo, hi, n)]


# Rounded, readable class breaks (lower bounds). Chosen from the value distributions (--stats).
POP_BREAKS = [1, 10, 50, 200, 500, 1000, 2500]           # residents per cell
BLDG_BREAKS = [1, 5, 20, 50, 100, 200, 400]          # buildings per 400 m hexagon
FLOOD_BLDG_BREAKS = [0, 1, 10, 50, 200, 1000]              # buildings per flood polygon
FLOOD_RES_BREAKS = [0, 1, 25, 100, 500, 2000]              # est. residents per flood polygon
EFAS_BREAKS = [0.1, 0.5, 1, 2, 4, 8]                       # modelled water depth, m (same for all return periods)
EFAS_LABELS = ["0.1 – 0.5 m", "0.5 – 1 m", "1 – 2 m", "2 – 4 m", "4 – 8 m", "≥ 8 m (mostly river channels)"]

# Three hue families that stay distinct when overlaid: warm (people), green (buildings), blue (water)
POP_COLORS = ramp("magma_r", len(POP_BREAKS), 0.08, 0.85)
BLDG_COLORS = ramp("Greens", len(BLDG_BREAKS), 0.3, 0.95)
FLOOD_BLDG_COLORS = ramp("Blues", len(FLOOD_BLDG_BREAKS), 0.2, 0.75)  # stops at mid-blue: navy is reserved for normal water
FLOOD_RES_COLORS = FLOOD_BLDG_COLORS
EFAS_COLORS = ramp("Purples", len(EFAS_BREAKS), 0.3, 1.0)   # 4th hue family: purple = modelled
EXPO_BREAKS = [0, 1, 10, 50, 150, 400]                     # estimated exposed residents per fixed 400 m hexagon
EXPO_LABELS = ["< 1", "1 – 9", "10 – 49", "50 – 149", "150 – 399", "≥ 400"]
EXPO_COLORS = ramp("magma_r", len(EXPO_BREAKS), 0.08, 0.8)  # warm = people, like the population layer
PRIO_BREAKS = [0, 20, 35, 50, 65, 80]                      # area priority score S (0-100); also asset score classes
PRIO_LABELS = ["0 – 19", "20 – 34", "35 – 49", "50 – 64", "65 – 79", "80 – 100"]
PRIO_COLORS = ramp("OrRd", len(PRIO_BREAKS), 0.2, 0.95)
ASSET_COLORS = {"people": ramp("RdPu", 6, 0.3, 0.95), "infra": ramp("YlGnBu", 6, 0.35, 1.0)}


def classify(values, breaks, colors):
    idx = np.clip(np.digitize(values, breaks) - 1, 0, len(breaks) - 1)
    return [colors[i] for i in idx]


def class_labels(breaks):
    labels = []
    for i, lo in enumerate(breaks):
        if i == len(breaks) - 1:
            labels.append(f"≥ {lo:,}")
        elif breaks[i + 1] - lo == 1:
            labels.append(f"{lo:,}")
        else:
            labels.append(f"{lo:,} – {breaks[i + 1] - 1:,}")
    return labels


def approx(x):
    """Readable rounded estimate for modelled numbers."""
    return "0" if x < 0.5 else f"≈ {round(x, -1 if x >= 100 else 0):,.0f}"


def to_web(gdf, cols, precision=COORD_PRECISION, simplify=None):
    """Lean GeoJSON dict for the HTML: optional simplification (metres), rounded WGS84 coordinates, no bbox."""
    out = gdf[cols + ["geometry"]]
    if simplify:
        out = out.set_geometry(out.to_crs(METRIC_CRS).simplify(simplify, preserve_topology=True))
    out = out.to_crs(WEB_CRS)
    out["geometry"] = shapely.set_precision(out.geometry.values, precision, mode="pointwise")
    return json.loads(out[~out.is_empty].to_json(drop_id=True))


# --------------------------------------------------------------------------- 6. HTML panels
CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root { --ink:#1f2933; --muted:#5f6b7a; --line:#e3e7ec; --accent:#1d5fa8; }
  .leaflet-container, .panel, .leaflet-control-layers, .leaflet-tooltip { font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }
  .panel, .leaflet-control-layers-expanded {
    background: rgba(255,255,255,.95); color: var(--ink); border: none !important;
    border-radius: 10px; box-shadow: 0 2px 14px rgba(15,23,42,.18); padding: 12px 14px; font-size: 12.5px; line-height: 1.45;
  }
  .leaflet-control-layers-expanded { padding: 10px 12px; }
  .leaflet-control-layers-base label, .leaflet-control-layers-overlays label { margin: 2px 0; }
  .leaflet-control-layers-separator { border-top-color: var(--line) !important; }
  .panel h1 { font-size: 16px; margin: 0 0 2px; font-weight: 700; letter-spacing: -.01em; }
  .panel .sub { color: var(--muted); margin: 0 0 8px; max-width: 300px; }
  .panel .date { display:inline-block; background:#eef4fb; color:var(--accent); font-weight:600; border-radius: 999px; padding: 1px 9px; font-size: 11.5px; }
  .panel h3 { font-size: 12px; margin: 10px 0 4px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
  .panel h3:first-child { margin-top: 0; }
  .zoom-btns { display:flex; gap:6px; margin-top: 10px; }
  .zoom-btns button { font: 600 12px Inter, system-ui, sans-serif; border:1px solid var(--line); background:#fff; color:var(--ink);
    border-radius: 7px; padding: 4px 10px; cursor:pointer; }
  .zoom-btns button:hover { border-color: var(--accent); color: var(--accent); }
  table.kf { border-collapse: collapse; margin-top: 8px; font-size: 12px; font-variant-numeric: tabular-nums; }
  table.kf th { font-weight: 600; color: var(--muted); text-align: right; padding: 0 0 2px 10px; }
  table.kf td { text-align: right; padding: 1px 0 1px 10px; }
  table.kf td:first-child, table.kf th:first-child { text-align: left; padding-left: 0; }
  table.kf tr.total td { border-top: 1px solid var(--line); font-weight: 600; }
  .note { color: var(--muted); font-size: 11px; margin-top: 6px; max-width: 300px; }
  .legend { min-width: 200px; max-width: 270px; max-height: calc(100vh - 470px); overflow-y: auto; }
  .legend .row { display:flex; align-items:center; gap:8px; margin: 1px 0; font-variant-numeric: tabular-nums; }
  .legend .sw { width: 18px; height: 12px; border-radius: 3px; flex: none; }
  .legend .unit { color: var(--muted); font-size: 11px; margin: -2px 0 4px; }
  .legend .aoi { width: 18px; height: 0; border-top: 2px dashed #6b7280; flex:none; }
  .seg { display:flex; border:1px solid var(--line); border-radius: 7px; overflow:hidden; margin: 2px 0 5px; }
  .seg label { flex:1; text-align:center; cursor:pointer; padding: 2px 6px; font-size: 11.5px; }
  .seg input { display:none; }
  .seg input:checked + span { color: var(--accent); font-weight: 600; }
  .seg label:has(input:checked) { background: #eef4fb; }
  details.limits { max-width: 330px; }
  details.limits summary { cursor:pointer; font-weight: 600; list-style: none; }
  details.limits summary::before { content: "ⓘ  "; color: var(--accent); }
  details.limits ul { margin: 6px 0 4px; padding-left: 16px; }
  details.limits li { margin-bottom: 4px; }
  .leaflet-tooltip.tt { border:none; border-radius: 8px; box-shadow: 0 2px 10px rgba(15,23,42,.2); padding: 8px 10px; font-size: 12px; }
  .leaflet-tooltip.tt table td, .leaflet-tooltip.tt table th { padding: 1px 4px; }
  .leaflet-tooltip.tt th { color: var(--muted); font-weight: 500; text-align: left; }
  .efas-pop .leaflet-popup-content-wrapper { border-radius: 8px; font: 12.5px/1.45 Inter, system-ui, sans-serif; }
  .efas-pop .muted { color: var(--muted); font-size: 11.5px; }
  .leaflet-control-layers-group-name { font-weight: 600; display: block; margin-bottom: 2px; }
  .leaflet-control-scale-line { font-family: Inter, system-ui, sans-serif; border-radius: 0 0 4px 4px; }
  /* candidate shelters: colour = facility type only; red "!" = inside observed extent; dashed ring + "?" = unresolved */
  .shel-ic { background: none; border: none; }
  .shel { display:inline-flex; flex:none; vertical-align:middle; align-items:center; justify-content:center; width:16px; height:16px;
    box-sizing:border-box; border:1.5px solid #fff; color:#fff; font: 700 9.5px/1 Inter, system-ui, sans-serif;
    box-shadow: 0 0 0 1px rgba(0,0,0,.35); position:relative; max-width:none; padding:0; }  /* max-width/padding: beat Bootstrap .row > * */
  .shel.t-school { background:#0f766e; border-radius: 3px; }
  .shel.t-sports_hall { background:#b45309; border-radius: 50%; }
  .shel.t-none { background:#d1d5db; border-color:#fff; border-radius: 3px; }
  .shel.t-community_centre { background:#475569; border-radius: 3px; transform: rotate(45deg); }
  .shel.t-community_centre b { transform: rotate(-45deg); }
  .shel.f-inside_observed { box-shadow: 0 0 0 2.5px #dc2626, 0 0 0 4px #fff; }
  .shel.f-boundary_unresolved { outline: 2px dashed #111827; outline-offset: 1px; }
  .shel.f-inside_observed::after, .shel.f-boundary_unresolved::after { position:absolute; top:-9px; right:-9px; width:11px; height:11px;
    border-radius:50%; color:#fff; font: 700 9px/11px Inter, sans-serif; text-align:center; }
  .shel.f-inside_observed::after { content:"!"; background:#dc2626; }
  .shel.f-boundary_unresolved::after { content:"?"; background:#111827; }
  .shel.t-community_centre::after { transform: rotate(-45deg); }
  .scl-ic { background: none; border: none; }
  .scl { width:100%; height:100%; box-sizing:border-box; border-radius:50%; background:#fff; border:2px solid #374151; color:#111827;
    display:flex; align-items:center; justify-content:center; font: 700 12px/1 Inter, system-ui, sans-serif;
    box-shadow: 0 1px 5px rgba(15,23,42,.35); position:relative; font-variant-numeric: tabular-nums; }
  .scl-in { position:absolute; top:-8px; right:-10px; background:#dc2626; color:#fff; border:1.5px solid #fff; border-radius:9px;
    padding:0 4px; font: 700 10px/15px Inter, sans-serif; }
  .shel-pop .leaflet-popup-content-wrapper { border-radius: 8px; font: 12.5px/1.45 Inter, system-ui, sans-serif; }
  .shel-pop .leaflet-popup-content { margin: 10px 12px; max-width: 290px; }
  .shel-pop .muted { color: var(--muted); font-size: 11.5px; }
  .shel-pop .scr { margin: 6px 0 2px; padding: 3px 7px; border-radius: 6px; background:#f1f5f9; font-weight:600; }
  .shel-pop .scr.inside_observed { background:#fee2e2; color:#991b1b; }
  .shel-pop .scr.boundary_unresolved { background:#e5e7eb; color:#111827; border: 1px dashed #111827; }
  /* left column: title panel with the scene buttons + the active scene panel, both 330 px wide */
  .title-panel, .scene-panel { width: 330px; box-sizing: border-box; }
  .title-panel { padding: 9px 12px; }
  .title-panel .demo-note { font-size: 10.5px; color: var(--muted); margin-top: 3px; }
  .scene-panel { overflow-y: auto; padding: 10px 14px; }
  .shel-panel.off .flt { opacity: .45; }
  .shel-panel .warn { background:#fff7ed; border-left: 3px solid #c2410c; padding: 5px 8px; border-radius: 4px; margin: 4px 0 8px; font-size: 12px; }
  .shel-panel .showing { font-variant-numeric: tabular-nums; margin-bottom: 4px; }
  .shel-panel .fl { display:grid; grid-template-columns: 16px 22px 1fr auto; align-items:center; column-gap: 4px; margin: 2px 0;
    font-size: 12px; cursor: pointer; font-variant-numeric: tabular-nums; }
  .shel-panel .fl input { margin: 0; }
  .shel-panel .fl .n { text-align: right; white-space: nowrap; }
  .shel-panel .fl .of { color: var(--muted); font-size: 11px; }
  .shel-panel .colhead { display:flex; justify-content:space-between; color: var(--muted); font-size: 11px; margin: 8px 0 1px;
    text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }
  .shel-panel .sym { display:inline-flex; width:22px; justify-content:center; }
  .shel-panel .sym .shel { width:13px; height:13px; font-size: 8px; }
  .shel-panel .sym .shel::after { top:-6px; right:-7px; width:10px; height:10px; font-size: 8px; line-height: 10px; }
  .shel-panel .fl.flag { margin: 5px 0; }
  .shel-panel .sym .scl { width:18px; height:18px; font-size: 9px; border-width: 1.5px; }
  .shel-panel .btns { display:flex; flex-wrap: wrap; gap:5px; margin: 6px 0 2px; }
  .shel-panel .btns button { font: 600 11.5px Inter, system-ui, sans-serif; border:1px solid var(--line); background:#fff; color:var(--ink);
    border-radius: 7px; padding: 3px 8px; cursor:pointer; }
  .shel-panel .btns button:hover { border-color: var(--accent); color: var(--accent); }
  .shel-panel .btns button.on { background:#eef4fb; border-color: var(--accent); color: var(--accent); }
  .shel-panel .btns button.flag { border-color:#fca5a5; }
  .shel-panel .layer-off { display:none; color:#92400e; font-size: 11.5px; margin-top: 4px; }
  .shel-panel.off .layer-off { display:block; }
  details.limits .limits-body { max-height: 45vh; overflow-y: auto; }
</style>
"""

LIMITS_HTML = """
<details class="limits panel"><summary>Data limits &amp; sources</summary><div class="limits-body">
<ul>
  <li><b>Flooded areas (Copernicus EMS)</b> are satellite snapshots taken when the satellite passed, not the flood peak.
      Only the requested areas (dashed outline) were mapped: <b>outside them, "not mapped" ≠ "not flooded"</b>.
      All delineation (first image + monitoring) and grading products were merged into one maximum observed extent.
      <b>Flood traces</b> mark areas already dry on the image but visibly flooded before.
      Normal water (rivers, lakes) is excluded from the flooded areas, so they show the overflow only (checked: 0.1 % overlap).
      Satellite delineation misses water between buildings, so <b>counts in towns are a lower bound</b>.
      Dates shown are map production dates; image acquisition times are on the EMSR517/518/520 activation pages.
      EMS gives extent only, <b>no water depth</b>: the blue shade is the exposure inside each polygon, not water intensity.</li>
  <li><b>Buildings (GHS-OBAT)</b> are footprint centroids (points, not footprints) from Overture Maps;
      "residential" may include mixed use. <b>Belgium is undercounted.</b></li>
  <li><b>Population (GHS-POP 2020)</b> is a modelled estimate of residents (not workers or visitors) on a ~1 km grid,
      partly derived from the same built-up data as OBAT, so the two layers are not independent.</li>
  <li><b>Residents in flood polygons</b> = each cell's residents shared equally among its residential buildings,
      summed for the buildings inside the polygon (area share if a cell has none). An estimate, not a count.</li>
  <li><b>Modelled hazard (EFAS)</b> is a model, not an observation: water depth for floods with a 10 %, 1 % or 0.2 %
      chance per year. Small rivers (upstream catchment &lt; 500 km²) are not modelled, so <b>empty means "not modelled",
      not "safe"</b>. The 500-year map is the ceiling and is built on 1990–2016 data: <b>the 2021 flood exceeded it in places</b>
      (e.g. the Ahr). Depths include the river channel itself.</li>
  <li><b>Candidate shelters (OpenStreetMap)</b> are schools, sports halls and community centres that <i>could</i> be assessed
      as emergency accommodation. None is verified as operating today, designated as a shelter, or suitable, and no capacity
      is known yet. "Outside the mapped flood extent" is <b>not "safe"</b>: the 2021 observation is incomplete and says
      nothing about today's flood risk, access routes or the building itself.</li>
  <li><b>Exposed residents per hexagon</b> are the residents inside the mapped extent (above), split onto a fixed 400 m grid:
      the same demand the shelter scenario allocates. 400 m is the aggregation grid, not the accuracy of the estimate.</li>
  <li><b>Scenario-based planning priority</b> combines exposure and the share left unassigned by the current, user-entered
      shelter scenario. It is not a flood probability, a validated vulnerability index or a definitive ranking of need.
      Because Belgium and towns are under-observed, it does not support comparisons between countries.</li>
  <li><b>Vulnerable facilities and critical infrastructure (OpenStreetMap, present-day)</b> are context. Their asset screening
      scores rank assets within their own group and are not comparable with the area priority. A facility's presence does
      not establish its occupancy or anyone's vulnerability.</li>
</ul>
<div class="note">Sources: Copernicus Emergency Management Service (© European Union, 2021), EMSR517/518/520;
Copernicus EMS – European Flood Awareness System (EFAS) flood hazard maps; JRC Global Human Settlement Layer: GHS-OBAT R2024A, GHS-POP R2023A. Candidate shelters, facilities and infrastructure © OpenStreetMap contributors (ODbL). Basemaps: Esri Canvas, © OpenStreetMap contributors.</div>
</div></details>
"""


def legend_rows(colors, labels, opacity):
    return "".join(f'<div class="row"><span class="sw" style="background:{c};opacity:{opacity}"></span>{l}</div>'
                   for c, l in zip(colors, labels))


SCENES = [(1, "What happened?"), (2, "Who was exposed?"), (3, "Where could they go?"), (4, "Where to start?")]


def header_html():
    """Top-left: title, the four scene buttons, country zoom and demo view (the same in every scene)."""
    scenes = "".join(f'<button data-scene="{k}"><b>{k}</b> {t}</button>' for k, t in SCENES)
    buttons = "".join(f'<button onclick="zoomTo(\'{k}\')">{k}</button>' for k in ["All", "BE", "DE", "NL"])
    return f"""
<div class="panel title-panel">
  <h1>July 2021 floods: from exposure to planning</h1>
  <span class="date">Event: 13–16 July 2021</span> <span class="of">BE · DE · NL</span>
  <div class="scenes">{scenes}</div>
  <div class="zoom-btns">{buttons}<span class="sep"></span><button id="demo-save" title="Remember the current map centre and zoom">Save demo view</button>
    <button id="demo-go" title="Return to the saved map centre and zoom (the scenario is not changed)" disabled>Go to demo</button></div>
  <div class="demo-note" id="demo-note" hidden></div>
</div>"""


def scene1_html(flood, comparison, origins=None):
    """Scene 1: observed extent totals (inside the mapped extent only), coverage limits, activation and EFAS tables."""
    by = flood.groupby("country").agg(area=("area_ha", "sum"), bldg=("n_bldg", "sum"), res=("residents", "sum"))
    act = {c: a for a, c in ACTIVATION_COUNTRY.items()}
    rows = "".join(f"<tr><td>{a} <span class=\"of\">requested by {COUNTRY_NAME[c]}</span></td><td>{r.area:,.0f}</td><td>{r.bldg:,.0f}</td><td>{approx(r.res)}</td></tr>"
                   for c, r in by.loc[[c for c in ["BEL", "DEU", "NLD"] if c in by.index]].iterrows() for a in [act[c]])
    tot = by.sum()
    rows += f'<tr class="total"><td>Total</td><td>{tot.area:,.0f}</td><td>{tot.bldg:,.0f}</td><td>{approx(tot.res)}</td></tr>'
    kind = flood.groupby("kind")["area_ha"].sum()
    cmp_rows = "".join(
        f'<tr{" class=total" if k == "Total" else ""}><td>{COUNTRY_NAME.get(k, k)}</td><td>{c["in100"]:.0%}</td>'
        f'<td>{c["only500"]:.0%}</td><td>{c["outside"]:.0%}</td></tr>' for k, c in comparison.items())
    return f"""
<div class="panel scene-panel" id="scene-1" data-scene="1">
  <h3>1 · What happened? <span class="k k-hist">Observed July 2021</span></h3>
  <div class="note" style="margin-top:0">Inside the <b>mapped observed flood extent</b> (Copernicus EMS flooded areas + flood traces):</div>
  <div class="kpis">
    <div><b>{tot.area / 100:,.0f} km²</b><span>mapped flooded area<br>({kind.get("flooded", 0) / 100:,.0f} flooded + {kind.get("trace", 0) / 100:,.0f} traces)</span></div>
    <div><b>{tot.bldg:,.0f}</b><span>buildings inside the mapped extent</span></div>
    <div><b>{approx(tot.res)}</b><span>estimated exposed residents (2020)</span></div>
  </div>
  <div class="scn-warn">Not all affected areas: EMS mapped only the requested areas (dashed outline; not mapped ≠ not flooded),
    satellites miss water between buildings (urban flooding), and Belgian observations are incomplete (no flood traces;
    flooded towns such as Verviers and Pepinster mostly not delineated). These totals are lower bounds.</div>
  <details><summary>Totals by EMS activation (not by country)</summary>
    <table class="kf">
      <tr><th>EMS activation</th><th>ha</th><th>buildings</th><th>residents</th></tr>{rows}
    </table>
    <div class="note">Rows are EMS activations, named after the requesting country; EMSR518 (Belgium) also mapped the Dutch Meuse.
    Geographic split:{location_note(origins)} Residents are modelled estimates; buildings in Belgium are undercounted.</div>
  </details>
  <details><summary>Observed vs modelled hazard (EFAS context)</summary>
    <table class="kf">
      <tr><th>Share of observed flood area</th><th>in 100-yr</th><th>500-yr only</th><th>outside</th></tr>{cmp_rows}
    </table>
    <div class="note">EMS flooded areas + traces vs EFAS hazard zones (rows by EMS activation country). "Outside" includes small rivers EFAS does not model.
    EFAS maps are under “Modelled hazard” in the layer controls (top right).</div>
  </details>
  <div class="note">Flood colour = buildings or residents inside each polygon (switch in the legend), not water depth. Full limits: “Data limits &amp; sources” (bottom left).</div>
</div>"""


def location_note(origins):
    """Estimated residents by actual location (country of the 400 m hexagon's OBAT buildings), from the demand split."""
    if origins is None:
        return ""
    by = origins.groupby(origins["country"].replace("", "-"))["residents"].sum()
    parts = [f"{COUNTRY_NAME[c]} {approx(by[c])}" for c in ["BEL", "DEU", "NLD"] if c in by.index]
    return f" by location (country of the 400 m hexagon), residents are {', '.join(parts)}" + (f" ({approx(by['-'])} not attributed)." if "-" in by.index else ".")


# --------------------------------------------------------------------------- 6b. candidate shelters
SHELTER_TYPES = {"school": ("S", "School"), "sports_hall": ("H", "Sports hall"), "community_centre": ("C", "Community centre")}
SHELTER_CATS = [("inside_observed", "Inside observed flood extent"), ("boundary_unresolved", "Edge / unresolved"),
                ("outside_extent_in_ems", "Outside extent, in EMS area"), ("outside_ems_coverage", "Not mapped by EMS")]
SHELTER_NOTE = ("Candidate facilities require verification. Being outside the mapped 2021 flood extent does not establish "
                "safety, accessibility or availability.")
CLUSTER_ICON_JS = """function(cluster) {
  var ms = cluster.getAllChildMarkers(), n = ms.length, k = 0;
  ms.forEach(function(m) { if (m.options.cat === 'inside_observed') k++; });
  var size = n < 10 ? 28 : n < 100 ? 34 : n < 1000 ? 40 : 46;
  var tip = n + ' candidate facilities' + (k ? ', ' + k + ' inside the observed flood extent' : '') + ': zoom in to see them';
  return L.divIcon({className: 'scl-ic', iconSize: [size, size], html: '<div class="scl" title="' + tip + '">' +
    n.toLocaleString('en') + (k ? '<span class="scl-in">!' + k + '</span>' : '') + '</div>'});
}"""


def shelter_icon(ftype, cat=""):
    return f'<span class="shel t-{ftype} f-{cat}"><b>{SHELTER_TYPES[ftype][0]}</b></span>'


def shelter_panel(inv, meta):
    """Left panel: required note, focus buttons, type / screening filters with 'shown / full inventory' counts, key."""
    if inv is None:
        return f"""<div class="panel shel-panel scene-panel" data-scene="3" hidden><h3>3 · Where could they go?</h3><div class="warn">{SHELTER_NOTE}</div>
    <div class="note">Layer not shown: no cached inventory was found. Run <code>python shelters.py</code> to build it.
    No facilities are invented in its absence.</div></div>"""
    n = len(inv)
    n_in = int((inv["screen_category"] == "inside_observed").sum())
    n_flag = int(inv["screen_category"].isin(["inside_observed", "boundary_unresolved"]).sum())
    row = lambda kind, key, sym, label, total: (
        f'<label class="fl{" flag" if key in ("inside_observed", "boundary_unresolved") else ""}"><input type="checkbox" data-{kind}="{key}" checked><span class="sym">{sym}</span>'
        f'<span>{label}</span><span class="n"><b data-n-{kind}="{key}">{total:,}</b> <span class="of">/ {total:,}</span></span></label>')
    types = "".join(row("t", t, shelter_icon(t), lab, int((inv["facility_type"] == t).sum())) for t, (_, lab) in SHELTER_TYPES.items())
    sym = {c: f'<span class="shel t-none f-{c}"></span>' for c in ("inside_observed", "boundary_unresolved")}
    cats = "".join(row("c", c, sym.get(c, ""), lab, int((inv["screen_category"] == c).sum())) for c, lab in SHELTER_CATS)
    date = (meta.get("osm_base_to") or "")[:10]
    gaps = f" {len(meta['tiles_missing'])} tiles could not be retrieved: facilities there are missing." if meta.get("tiles_missing") else ""
    return f"""<div class="panel shel-panel scene-panel" id="shel-panel" data-scene="3" hidden>
    <h3>3 · Where could they go? <span class="k k-cand">Candidates</span></h3>
    <div class="warn">{SHELTER_NOTE}</div>
    <div class="shel-tabs"><button data-tab="scenario" class="on">Planning scenario</button><button data-tab="candidates">Candidate filters</button></div>
    <div id="cand-tab" hidden>
    <div class="showing">Showing <b id="shel-shown">{n:,}</b> of <b>{n:,}</b> candidates <span class="of">(full inventory)</span></div>
    <div class="btns flt">
      <button data-focus="all" class="on">All candidates</button>
      <button data-focus="inside" class="flag">Inside flood extent ({n_in})</button>
      <button data-focus="flagged">Inside + unresolved ({n_flag})</button>
    </div>
    <div class="flt">
      <div class="colhead"><span>Facility type</span><span>shown / inventory</span></div>{types}
      <div class="colhead"><span>2021 flood screening</span><span>shown / inventory</span></div>{cats}
    </div>
    <div class="layer-off">The layer is switched off: tick “Candidate shelters” in the layer list, or use a button above.</div>
    <div class="note" style="max-width:none"><span class="sym"><span class="scl" style="display:inline-flex">12</span></span>
    group of 12 candidates (zoom in to see them); a red <b style="color:#dc2626">!n</b> counts those inside the observed extent.
    Colour and shape show the facility type only. Counts cover our inventory within the EMS mapped areas + 1 km, not all
    facilities in the region. OSM data as of {date}.{gaps}</div>
    </div>
    <div id="scn-tab"></div>
  </div>"""


def shelter_points(inv):
    """Compact per-candidate records for the browser: one list per candidate (keys in SHELTER_FIELDS)."""
    country = inv["country"].map(lambda c: COUNTRY_NAME.get(c, c or "country not identified (outside BE/DE/NL?)"))
    cols = {"lon": inv["lon"], "lat": inv["lat"], "t": inv["facility_type"], "c": inv["screen_category"],
            "name": inv["name"], "sub": inv["facility_subtype"].fillna(""), "muni": inv["municipality"].fillna(""),
            "ctry": country, "url": inv["source_url"], "id": inv["candidate_id"],
            "got": inv["retrieved_at"].str[:10], "osm": inv["osm_data_timestamp"].fillna("").str[:10],
            "why": inv["screen_reason"], "kind": inv["flood_kind"], "chk": inv["osm_check_date"],
            "stale": inv["cache_stale"].astype(int)}
    xy = inv.geometry.to_crs(METRIC_CRS)
    cols.update({"x": xy.x.round(1), "y": xy.y.round(1), "cc": inv["country"].fillna(""),
                 "dcap": inv["shelter_capacity"].astype(object).where(inv["shelter_capacity"].notna(), None),
                 "dsrc": inv["capacity_source"].fillna(""), "ddate": ""})   # no documented capacity source yet
    return list(cols), pd.DataFrame(cols).astype(object).where(pd.DataFrame(cols).notna(), None).values.tolist()


# --------------------------------------------------------------------------- 7. map
def scene_data(origins, hexes):
    """Fixed 400 m hexagon summary of the demand origins for scenes 2 and 4 (columnar, rings in WGS84 lat/lon)."""
    hx, origin_hex = planning_demand.hex_summary(origins, hexes, hex_index, hex_polygons)
    problems = planning_demand.check_hex_summary(hx, origin_hex, origins)
    assert not problems, problems
    rings = shapely.get_coordinates(hx.to_crs(WEB_CRS).exterior).reshape(len(hx), 7, 2)[:, :6]
    return {"hex": {"id": hx["hex_id"].tolist(), "P": hx["residents"].round(9).tolist(), "cc": hx["country"].tolist(),
                    "lon": hx["lon"].tolist(), "lat": hx["lat"].tolist(), "no": hx["n_origins"].tolist(),
                    "nfb": hx["n_fallback"].astype(int).tolist(),
                    "ring": [[[round(y, 6), round(x, 6)] for x, y in r] for r in rings]},
            "originHex": origin_hex.tolist(), "p99": planning_demand.exposure_reference(hx),
            "reference": "GHS-POP E2020 R2023A residents (reference year 2020) shared over residential GHS-OBAT buildings, "
                         "inside the mapped observed July 2021 flood extent (Copernicus EMS)",
            "weights": PRIORITY_WEIGHTS, "hexZoom": HEX_ZOOM, "expoBreaks": EXPO_BREAKS, "expoColors": EXPO_COLORS,
            "prioBreaks": PRIO_BREAKS, "prioColors": PRIO_COLORS}


def asset_data():
    """Vulnerable facilities and critical infrastructure (priority_map.py records), or None if no OSM cache exists."""
    import priority_map   # imports this module: deferred to avoid a circular import
    a = priority_map.assets_for_map()
    if a is not None:
        a["colors"] = ASSET_COLORS
    return a


def build_map(d, efas, hydro, shel=(None, None), assets=None):
    flood, aoi, hexes, pop = d["flood"], d["aoi"], d["hexes"], d["pop"]
    comparison = efas_comparison(flood, efas)
    origins = planning_demand.build_demand(flood, hexes)   # estimated exposed residents, split onto the 400 m hexagons
    problems = planning_demand.check_demand(origins, flood)
    assert not problems, problems
    scenes = scene_data(origins, hexes)

    # ---- attributes for display (pre-formatted strings for tooltips, colours precomputed)
    flood["c_b"] = classify(flood["n_bldg"], FLOOD_BLDG_BREAKS, FLOOD_BLDG_COLORS)
    flood["c_r"] = classify(flood["residents"], FLOOD_RES_BREAKS, FLOOD_RES_COLORS)
    flood["t_country"] = flood["country"].map(COUNTRY_NAME) + " · " + flood["activation"]
    flood["t_area"] = flood["area_ha"].map(lambda v: f"{v:,.1f} ha")
    flood["t_bldg"] = flood.apply(lambda r: f"{r.n_bldg:,.0f} ({r.n_res_bldg:,.0f} residential)", axis=1)
    flood["t_res"] = flood["residents"].map(approx)
    hexes["color"] = classify(hexes["n_bldg"], BLDG_BREAKS, BLDG_COLORS)
    hexes["t_country"] = hexes["country"].map(COUNTRY_NAME)
    hexes["t_bldg"] = hexes["n_bldg"].map("{:,}".format)
    hexes["t_res"] = hexes.apply(lambda r: f"{r.n_res:,} ({100 * r.n_res / r.n_bldg:.0f} %)", axis=1)
    pop["color"] = classify(pop["pop"], POP_BREAKS, POP_COLORS)
    pop["t_country"] = pop["country"].map(COUNTRY_NAME).fillna("–")
    pop["t_pop"] = pop["pop"].map(approx)

    flood["t_kind"] = flood["kind"].map({"flooded": "Flooded area (water on image)", "trace": "Flood trace (water receded)"})
    flood_w = to_web(flood, ["kind", "c_b", "c_r", "t_kind", "t_country", "t_area", "t_bldg", "t_res", "sources"],
                     simplify=SIMPLIFY_TOL)
    hex_w = to_web(hexes, ["color", "t_country", "t_bldg", "t_res"], GRID_PRECISION)
    pop_w = to_web(pop, ["color", "t_country", "t_pop"], GRID_PRECISION)
    aoi_w = to_web(aoi, ["activation"])

    # zoom targets: flood extent per country
    fb = flood.to_crs(WEB_CRS)
    bounds = {"All": fb.total_bounds}
    for iso, k in [("BEL", "BE"), ("DEU", "DE"), ("NLD", "NL")]:
        bounds[k] = fb[fb["country"] == iso].total_bounds
    bounds = {k: [[b[1], b[0]], [b[3], b[2]]] for k, b in bounds.items()}

    m = folium.Map(location=[50.6, 6.4], zoom_start=8, tiles=None, prefer_canvas=True, control_scale=True)
    # Muted keyless basemaps (CARTO tiles now require an API key). Esri canvas labels are drawn in a
    # pane above the data so place names stay readable; they follow the chosen basemap (see JS below).
    folium.TileLayer(ESRI.format("Light_Gray_Base"), attr=ESRI_ATTR, name="Light gray (Esri)", max_native_zoom=16).add_to(m)
    folium.TileLayer(ESRI.format("Dark_Gray_Base"), attr=ESRI_ATTR, name="Dark gray (Esri)", max_native_zoom=16,
                     show=False).add_to(m)
    folium.TileLayer("openstreetmap", name="OpenStreetMap", show=False).add_to(m)
    folium.map.CustomPane("labels", z_index=650, pointer_events=False).add_to(m)
    labels = folium.TileLayer(ESRI.format("Light_Gray_Reference"), attr=ESRI_ATTR, pane="labels",
                              control=False, max_native_zoom=16).add_to(m)

    tip_style = "background:#fff;"
    LAYER_POP, LAYER_BLDG, LAYER_AOI = "Population (all residents 2020)", "Buildings (all, per 400 m hexagon)", "EMS mapped areas"
    LAYER_FLOOD = {"flooded": "Flooded areas (water on image)", "trace": "Flood traces (water receded)"}

    # 4. modelled hazard (EFAS): PNG images in a pane below every vector layer; one radio option per return period
    folium.map.CustomPane("efas", z_index=350).add_to(m)
    fg_efas, efas_img, efas_meta = {}, {}, {}
    for rp in (10, 100, 500):
        uri, img_bounds, efas_meta[rp] = efas_png(*efas[rp])
        fg_efas[rp] = folium.FeatureGroup(f"{rp}-year ({ {10: '10 %', 100: '1 %', 500: '0.2 %'}[rp]} per year)",
                                          show=False, control=False).add_to(m)
        efas_img[rp] = folium.raster_layers.ImageOverlay(uri, img_bounds, opacity=0.8, pane="efas",
                                                         interactive=False).add_to(fg_efas[rp])
    # Off by default: the initial view is the shelter review (observed flooding + candidates); EFAS is one click away
    fg_efas_off = folium.FeatureGroup("Off", show=True, control=False).add_to(m)

    # 3. population: bottom of the vector stack
    fg_pop = folium.FeatureGroup(LAYER_POP, show=False).add_to(m)
    folium.GeoJson(
        pop_w, name=LAYER_POP,
        style_function=lambda f: {"fillColor": f["properties"]["color"], "fillOpacity": 0.5, "weight": 0},
        highlight_function=lambda f: {"weight": 1.5, "color": "#111827", "fillOpacity": 0.85},
        tooltip=folium.GeoJsonTooltip(["t_pop", "t_country"], ["Residents (2020)", "Country"],
                                      class_name="tt", style=tip_style, sticky=True),
    ).add_to(fg_pop)

    # 2. buildings
    fg_bldg = folium.FeatureGroup(LAYER_BLDG, show=False).add_to(m)
    folium.GeoJson(
        hex_w, name=LAYER_BLDG,
        style_function=lambda f: {"fillColor": f["properties"]["color"], "fillOpacity": 0.6, "weight": 0},
        highlight_function=lambda f: {"weight": 1.5, "color": "#14532d", "fillOpacity": 0.85},
        tooltip=folium.GeoJsonTooltip(["t_bldg", "t_res", "t_country"], ["Buildings", "of which residential", "Country"],
                                      class_name="tt", style=tip_style, sticky=True),
    ).add_to(fg_bldg)

    # 1. flooded areas and flood traces: on top. Same colour scale; traces get a dashed outline and lighter fill.
    fg_flood, flood_gj = {}, {}
    for kind, fill_opacity, dash in [("trace", 0.55, "3 3"), ("flooded", 0.75, None)]:
        fg_flood[kind] = folium.FeatureGroup(LAYER_FLOOD[kind], show=True).add_to(m)
        flood_gj[kind] = folium.GeoJson(
            {"type": "FeatureCollection", "features": [f for f in flood_w["features"] if f["properties"]["kind"] == kind]},
            name=LAYER_FLOOD[kind],
            style_function=lambda f, o=fill_opacity, d=dash: {"fillColor": f["properties"]["c_b"], "fillOpacity": o,
                                                              "color": "#08224a", "weight": 1.4, "opacity": 1, "dashArray": d},
            highlight_function=lambda f: {"weight": 2.5, "color": "#f59e0b", "fillOpacity": 0.9},
            tooltip=folium.GeoJsonTooltip(
                ["t_kind", "t_country", "t_area", "t_bldg", "t_res", "sources"],
                ["Type", "Activation", "Area", "Buildings inside", "Est. residents inside", "EMS products (map date)"],
                class_name="tt", style=tip_style, sticky=True),
        ).add_to(fg_flood[kind])

    # Normal water (reference): above the flood layers, in a pane that lets the mouse through to the floods below
    folium.map.CustomPane("water", z_index=450, pointer_events=False).add_to(m)
    fg_water = folium.FeatureGroup("Normal water (reference)", show=True).add_to(m)
    bodies = hydro[hydro["kind"] == "body"].dissolve()
    folium.GeoJson(to_web(bodies, ["kind"], simplify=HYDRO_SIMPLIFY), interactive=False, pane="water",
                   style_function=lambda f: {"fillColor": WATER_COLOR, "fillOpacity": 0.8, "weight": 0}).add_to(fg_water)
    folium.GeoJson(to_web(hydro[hydro["kind"] == "line"], ["kind"], simplify=HYDRO_SIMPLIFY), interactive=False, pane="water",
                   style_function=lambda f: {"color": WATER_COLOR, "weight": 1.2, "opacity": 0.9}).add_to(fg_water)

    fg_aoi = folium.FeatureGroup(LAYER_AOI, show=True).add_to(m)
    folium.GeoJson(aoi_w, name=LAYER_AOI, interactive=False,
                   style_function=lambda f: {"fill": False, "color": "#6b7280", "weight": 1.5, "dashArray": "6 5"},
                   ).add_to(fg_aoi)

    # Candidate shelters: a marker cluster layer; markers are created in the browser from compact records (see JS below)
    inv, shel_meta = shel
    fg_shel = None if inv is None else plugins.MarkerCluster(
        name="Candidate shelters (unverified)", show=False, icon_create_function=CLUSTER_ICON_JS,
        options={"maxClusterRadius": 50, "disableClusteringAtZoom": 15, "showCoverageOnHover": False,
                 "spiderfyOnMaxZoom": False}).add_to(m)   # no chunkedLoading: scene switches may remove it mid-load

    lc = folium.LayerControl(position="topright", collapsed=True).add_to(m)   # advanced: the scenes set the defaults
    efas_control = plugins.GroupedLayerControl(
        {"Modelled hazard (EFAS)": [fg_efas[10], fg_efas[100], fg_efas[500], fg_efas_off]},
        exclusive_groups=True, collapsed=True, position="topright")
    efas_control.layers_untoggle.discard(fg_efas_off.get_name())  # folium keeps only the 1st radio; "Off" is the default
    efas_control.add_to(m)
    plugins.Fullscreen(position="topright").add_to(m)
    minimap_tiles = folium.TileLayer(ESRI.format("Light_Gray_Base"), attr=ESRI_ATTR)
    plugins.MiniMap(tile_layer=minimap_tiles, position="bottomleft", toggle_display=True,
                    zoom_level_offset=-5, width=140, height=110, minimized=True).add_to(m)

    # ---- legend (one block per layer, shown only when its layer is on)
    legend = f"""
<div class="panel legend">
  <div id="leg-flood">
    <h3>Observed (Copernicus EMS, July 2021)</h3>
    <div class="seg">
      <label><input type="radio" name="fm" value="c_b" checked onchange="setFloodMetric(this.value)"><span>Buildings</span></label>
      <label><input type="radio" name="fm" value="c_r" onchange="setFloodMetric(this.value)"><span>Residents</span></label>
    </div>
    <div class="unit" id="unit-flood">buildings inside each flood polygon</div>
    <div id="leg-flood-b">{legend_rows(FLOOD_BLDG_COLORS, class_labels(FLOOD_BLDG_BREAKS), 0.75)}</div>
    <div id="leg-flood-r" hidden>{legend_rows(FLOOD_RES_COLORS, class_labels(FLOOD_RES_BREAKS), 0.75)}</div>
    <div class="row flood-compact"><span class="sw" style="background:#6baed6;opacity:.35;border:2px solid #08224a"></span><span>observed flood extent (light fill)</span></div>
    <div class="row" style="margin-top:6px"><span class="sw" style="background:#6baed6;border:2px solid #08224a"></span>water on image</div>
    <div class="row"><span class="sw" style="background:#6baed6;opacity:.6;border:2px dashed #08224a"></span>flood trace (receded)</div>
    <div class="unit" style="margin-top:4px">no water depth: shade = exposure, not intensity</div>
  </div>
  <div id="leg-water">
    <h3>Normal water (reference)</h3>
    <div class="row"><span class="sw" style="background:{WATER_COLOR};opacity:.8"></span>lakes, reservoirs, wide rivers</div>
    <div class="row"><span class="sw" style="height:0;border-top:1.5px solid {WATER_COLOR}"></span>rivers and streams</div>
    <div class="unit" style="margin-top:3px">EMS reference layer; observed flooding excludes it.
    <span id="water-zoom">Zoom in to see it.</span></div>
  </div>
  <div id="leg-efas">
    <h3>Modelled (EFAS)</h3>
    <div class="unit">water depth, <span id="efas-rp">100-year</span> flood · click map for depth</div>
    {legend_rows(EFAS_COLORS, EFAS_LABELS, 0.8)}
  </div>
  <div id="leg-aoi"><div class="row" style="margin-top:6px"><span class="aoi"></span>EMS mapped area</div></div>
  <div id="leg-expo" hidden>
    <h3>Exposed residents <span class="k k-hist">2020 est.</span></h3>
    <div class="unit">estimated residents inside the mapped extent, per fixed 400 m hexagon (from zoom {HEX_ZOOM})</div>
    {legend_rows(EXPO_COLORS, EXPO_LABELS, 0.75)}
    <div class="row" style="margin-top:4px"><span class="ecl" style="width:24px;height:24px;font-size:9px;flex:none">120</span><span>overview circles: <b>sum</b> of residents of the grouped hexagons</span></div>
  </div>
  <div id="leg-prio" hidden>
    <h3>Planning priority (areas) <span class="k k-res">Calculated</span></h3>
    <div class="unit">scenario-based score S (0–100) per fixed hexagon; dots below zoom {HEX_ZOOM}</div>
    {legend_rows(PRIO_COLORS, PRIO_LABELS, 0.85)}
    <div class="row"><span class="sw" style="background:#c9ced6"></span>no score (both weights 0)</div>
  </div>
  <div id="leg-people" hidden>
    <h3>Vulnerable facilities (OSM)</h3><div class="unit">dot colour = asset screening score, not area priority; hollow = outside EMS coverage, not ranked</div>
    {legend_rows(ASSET_COLORS["people"], PRIO_LABELS, 1).replace('class="sw"', 'class="sw dot"')}
  </div>
  <div id="leg-infra" hidden>
    <h3>Critical infrastructure (OSM)</h3><div class="unit">dot colour = asset screening score, not area priority; bridges / tunnels as lines from zoom 13</div>
    {legend_rows(ASSET_COLORS["infra"], PRIO_LABELS, 1).replace('class="sw"', 'class="sw dot"')}
  </div>
  <div id="leg-bldg">
    <h3>Buildings (context)</h3><div class="unit">all buildings per 400 m hexagon, not flooded buildings</div>
    {legend_rows(BLDG_COLORS, class_labels(BLDG_BREAKS), 0.6)}
  </div>
  <div id="leg-pop">
    <h3>Population (all residents)</h3><div class="unit">residents per ~1 km cell (30″), not only exposed</div>
    {legend_rows(POP_COLORS, class_labels(POP_BREAKS), 0.5)}
  </div>
</div>"""
    shel_fields, shel_rows = shelter_points(inv) if inv is not None else ([], [])
    scenario_data = {
        "origins": origins[["origin_id", "x", "y", "lon", "lat"]].assign(res=origins["residents"].round(9), cc=origins["country"]).values.tolist(),
        "reference": planning_demand.REFERENCE,
        "defaultKm": SCENARIO_DEFAULT_KM, "nDocumented": int(inv["shelter_capacity"].notna().sum()) if inv is not None else 0}
    # data build id: changes whenever the demand origins or the candidate inventory (ids, screening) change, so a saved
    # scenario can be checked against the map it is restored into
    build_src = json.dumps([scenario_data["origins"], sorted(zip(inv["candidate_id"], inv["screen_category"])) if inv is not None else []])
    scenario_data["build"] = hashlib.sha1(build_src.encode()).hexdigest()[:10]
    scenario_data["osmDate"] = (shel_meta or {}).get("osm_base_to", "")[:10] if inv is not None else ""
    shel_js = "" if inv is None else f"""
  // Candidate shelters: one divIcon per facility; flags (inside / edge) are CSS rings, popups built on click
  var SF = {json.dumps(shel_fields)}, SR = {json.dumps(shel_rows, ensure_ascii=False)};
  var CAT = {json.dumps(shelters.CATEGORIES)}, TYPE = {json.dumps({k: v for k, v in SHELTER_TYPES.items()})};
  function esc(s) {{ return String(s).replace(/[&<>"]/g, function(c) {{ return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]; }}); }}
  function shelPopup(r) {{
    var t = TYPE[r.t][1] + (r.sub ? ' · ' + esc(r.sub) : ''), place = [r.muni, r.ctry].filter(Boolean).map(esc).join(', ');
    var note = r.c === 'inside_observed' ? 'Flagged: kept as a candidate for review, not removed.'
             : r.c === 'boundary_unresolved' ? 'Needs a manual check.'
             : 'Not flooded on the 2021 map does <b>not</b> mean safe.';
    return '<b>' + (r.name ? esc(r.name) : '(no name in OSM)') + '</b><br><span class="muted">' + t + '</span><br>' + place +
      '<div class="scr ' + r.c + '">' + CAT[r.c] + (r.kind ? ' (' + r.kind.replace('flooded', 'flooded area').replace('trace', 'flood trace') + ')' : '') + '</div>' +
      '<span class="muted">' + esc(r.why) + '. ' + note + '</span>' +
      '<div style="margin-top:6px"><b>Verification:</b> mapped in OpenStreetMap; not checked as operating today, ' +
      'not verified as a designated emergency shelter. <b>Capacity:</b> unknown.</div>' +
      '<div class="muted" style="margin-top:4px">Source: <a href="' + r.url + '" target="_blank" rel="noopener">' + esc(r.id) + '</a> · retrieved ' +
      r.got + (r.stale ? ' (older cached copy)' : '') + (r.chk ? ' · last OSM survey date ' + esc(r.chk) : '') + '</div>' +
      (window.ScenarioUI ? ScenarioUI.popupHtml(r) : '');
  }}
  var fgShel = {fg_shel.get_name() if fg_shel is not None else "null"};
  function shelIcon(r) {{   // a white badge shows the scenario capacity (assumed or documented) once there is one
    var cap = window.ScenarioUI ? ScenarioUI.capacity(r) : null;
    var b = cap && cap.v != null ? '<span class="capb">' + cap.v.toLocaleString('en') + '</span>' : '';
    return L.divIcon({{className: 'shel-ic', iconSize: [16, 16],
      html: '<span class="shel t-' + r.t + ' f-' + r.c + '"><b>' + TYPE[r.t][0] + '</b>' + b + '</span>'}});
  }}
  var markers = SR.map(function(a) {{
    var r = {{}}; SF.forEach(function(k, i) {{ r[k] = a[i]; }});
    var mk = L.marker([r.lat, r.lon], {{icon: shelIcon(r), title: r.name || TYPE[r.t][1], cat: r.c,
      zIndexOffset: r.c === 'inside_observed' ? 1000 : r.c === 'boundary_unresolved' ? 500 : 0}})
      .bindPopup(function() {{ return shelPopup(r); }}, {{className: 'shel-pop', maxWidth: 310,
        autoPanPaddingTopLeft: L.point(330, 20), autoPanPaddingBottomRight: L.point(300, 20)}});  // clear of the side panels
    mk.r = r;
    return mk;
  }});

  // Filters: facility type x screening category. Counts: shown (after filters) / full inventory.
  var sp = document.getElementById('shel-panel');
  var typeOn = {{}}, catOn = {{}};
  sp.querySelectorAll('input[data-t]').forEach(function(i) {{ typeOn[i.dataset.t] = true; }});
  sp.querySelectorAll('input[data-c]').forEach(function(i) {{ catOn[i.dataset.c] = true; }});
  var FOCUS = {{all: null, inside: ['inside_observed'], flagged: ['inside_observed', 'boundary_unresolved']}};
  function applyFilter(fit) {{
    var keep = markers.filter(function(m) {{ return typeOn[m.r.t] && catOn[m.r.c]; }});
    fgShel.clearLayers(); fgShel.addLayers(keep);
    document.getElementById('shel-shown').textContent = keep.length.toLocaleString('en');
    sp.querySelectorAll('[data-n-t]').forEach(function(e) {{ var k = e.dataset.nT;
      e.textContent = markers.filter(function(m) {{ return m.r.t === k && catOn[m.r.c]; }}).length.toLocaleString('en'); }});
    sp.querySelectorAll('[data-n-c]').forEach(function(e) {{ var k = e.dataset.nC;
      e.textContent = markers.filter(function(m) {{ return m.r.c === k && typeOn[m.r.t]; }}).length.toLocaleString('en'); }});
    sp.querySelectorAll('input[data-t]').forEach(function(i) {{ i.checked = typeOn[i.dataset.t]; }});
    sp.querySelectorAll('input[data-c]').forEach(function(i) {{ i.checked = catOn[i.dataset.c]; }});
    var allT = Object.values(typeOn).every(Boolean);
    sp.querySelectorAll('button[data-focus]').forEach(function(b) {{
      var f = FOCUS[b.dataset.focus];
      b.classList.toggle('on', allT && Object.keys(catOn).every(function(c) {{ return catOn[c] === (!f || f.indexOf(c) >= 0); }}));
    }});
    if (fit && keep.length) fitView(L.latLngBounds(keep.map(function(m) {{ return m.getLatLng(); }})), 13);
  }}
  sp.querySelectorAll('input[data-t], input[data-c]').forEach(function(i) {{
    i.addEventListener('change', function() {{ (i.dataset.t ? typeOn : catOn)[i.dataset.t || i.dataset.c] = i.checked; applyFilter(false); }});
  }});
  sp.querySelectorAll('button[data-focus]').forEach(function(b) {{
    b.addEventListener('click', function() {{
      var f = FOCUS[b.dataset.focus];
      Object.keys(typeOn).forEach(function(t) {{ typeOn[t] = true; }});
      Object.keys(catOn).forEach(function(c) {{ catOn[c] = !f || f.indexOf(c) >= 0; }});
      if (!map.hasLayer(fgShel)) fgShel.addTo(map);
      applyFilter(!!f); if (!f) zoomTo('All');
    }});
  }});
  function shelLayerState() {{ sp.classList.toggle('off', !map.hasLayer(fgShel)); }}
  map.on('overlayadd overlayremove', shelLayerState);
  applyFilter(false); shelLayerState();
  window.shelFilter = {{types: typeOn, cats: catOn, apply: applyFilter, markers: markers, layer: fgShel}};  // for tests

  // Planning scenario (planning/alloc.js + planning/ui.js)
  window.SHELTER_APP = {{map: map, markers: markers, cluster: fgShel, layerControl: {lc.get_name()}, icon: shelIcon}};
  window.SCENARIO_DATA = {json.dumps(scenario_data)};
  window.SHELTER_APP.onRecalc = [];
{(PLANNING / "alloc.js").read_text()}
{(PLANNING / "ui.js").read_text()}
  // Context assets and the four scenes (planning/scenes.js)
  window.ASSET_APP = {{map: map}};
  window.ASSET_DATA = {json.dumps(assets, separators=(",", ":")) if assets else "null"};
  if (window.ASSET_DATA) {{
{(HERE / "priority" / "assets.js").read_text()}
  }}
  window.SCENE_APP = {{map: map, layerControl: {lc.get_name()}, legendGroups: groups, onRecalc: window.SHELTER_APP.onRecalc,
    layout: function() {{ requestAnimationFrame(layout); }}, setFloodLight: setFloodLight, efasOff: efasOff,
    layers: {{flooded: {fg_flood["flooded"].get_name()}, trace: {fg_flood["trace"].get_name()}, aoi: {fg_aoi.get_name()},
              water: {fg_water.get_name()}, bldg: {fg_bldg.get_name()}, pop: {fg_pop.get_name()}, shel: fgShel}}}};
  window.SCENE_DATA = {json.dumps(scenes, separators=(",", ":"))};
{(PLANNING / "priority.js").read_text()}
{(PLANNING / "scenes.js").read_text()}
"""

    js = f"""
document.addEventListener('DOMContentLoaded', function() {{  // run after folium has created the map
  var map = {m.get_name()};
  var floods = [{flood_gj["trace"].get_name()}, {flood_gj["flooded"].get_name()}];
  var floodGroups = [{fg_flood["trace"].get_name()}, {fg_flood["flooded"].get_name()}];
  map.zoomControl.setPosition('topright');

  function panel(html, pos) {{
    var c = L.control({{position: pos}});
    c.onAdd = function() {{
      var d = L.DomUtil.create('div'); d.innerHTML = html;
      L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
      return d.firstElementChild;
    }};
    c.addTo(map);
  }}
  panel({json.dumps(header_html())}, 'topleft');
  panel({json.dumps(scene1_html(flood, comparison, origins))}, 'topleft');
  panel('<div class="panel scene-panel" id="scene-2" data-scene="2" hidden></div>', 'topleft');
  panel({json.dumps(shelter_panel(inv, shel_meta))}, 'topleft');
  panel('<div class="panel scene-panel" id="scene-4" data-scene="4" hidden></div>', 'topleft');
  panel({json.dumps(legend)}, 'topright');
  panel({json.dumps(LIMITS_HTML)}, 'bottomleft');

  var B = {json.dumps(bounds)};
  // Fit bounds into the map area left free by the side panels
  function fitView(b, maxZoom) {{
    var r = map.getContainer().getBoundingClientRect();
    var left = document.querySelector('.leaflet-top.leaflet-left').getBoundingClientRect().right - r.left;
    var right = r.right - document.querySelector('.leaflet-top.leaflet-right').getBoundingClientRect().left;
    if (left + right > r.width - 200) {{ left = right = 20; }}   // narrow screen: panels overlap the map anyway
    map.fitBounds(b, {{paddingTopLeft: [left + 20, 20], paddingBottomRight: [right + 20, 20], maxZoom: maxZoom || 18}});
  }}
  window.zoomTo = function(k) {{ fitView(B[k]); }};
  // Keep the shelter panel and the legend inside the viewport, above the bottom controls and attribution
  function layout() {{
    var r = map.getContainer().getBoundingClientRect();
    var sp = document.querySelector('.scene-panel:not([hidden])'), lg = document.querySelector('.legend');
    var bl = document.querySelector('.leaflet-bottom.leaflet-left').getBoundingClientRect();
    var br = document.querySelector('.leaflet-bottom.leaflet-right').getBoundingClientRect();
    if (sp) sp.style.maxHeight = Math.max(90, bl.top - sp.getBoundingClientRect().top - 10) + 'px';
    if (lg) lg.style.maxHeight = Math.max(90, br.top - lg.getBoundingClientRect().top - 10) + 'px';
  }}
  window.addEventListener('resize', layout);
  document.querySelectorAll('details').forEach(function(d) {{ d.addEventListener('toggle', layout); }});
  map.on('overlayadd overlayremove baselayerchange', function() {{ requestAnimationFrame(layout); }});
  setTimeout(layout, 0);

  // Switch the metric that drives the flood colour (resetStyle on mouseout keeps the choice)
  floods.forEach(function(g) {{ g._baseStyle = g.options.style; }});
  var units = {{c_b: 'buildings inside each flood polygon', c_r: 'estimated residents inside each flood polygon'}};
  // When EFAS is shown underneath, observed polygons switch to a light fill (bold outline kept) so both stay readable
  var floodKey = 'c_b', efasOn = false, floodLight = false;
  function applyFloodStyle() {{
    floods.forEach(function(g) {{
      g.options.style = function(f) {{
        var s = Object.assign({{}}, g._baseStyle(f)); s.fillColor = f.properties[floodKey];
        if (efasOn || floodLight) s.fillOpacity = floodLight ? 0.2 : 0.3;
        return s;
      }};
      g.setStyle(g.options.style);
    }});
  }}
  function setFloodLight(on) {{
    if (on !== floodLight) {{ floodLight = on; applyFloodStyle(); }}
    document.querySelector('.legend').classList.toggle('compact-flood', on);   // scenes 2 and 4: one row for the extent
  }}
  window.setFloodMetric = function(key) {{
    floodKey = key; applyFloodStyle();
    document.getElementById('leg-flood-b').hidden = key !== 'c_b';
    document.getElementById('leg-flood-r').hidden = key !== 'c_r';
    document.getElementById('unit-flood').textContent = units[key];
  }};

  // Legend blocks follow the layer checkboxes
  var efasGroups = {{10: {fg_efas[10].get_name()}, 100: {fg_efas[100].get_name()}, 500: {fg_efas[500].get_name()}}};
  var efasImg = {{10: {efas_img[10].get_name()}, 100: {efas_img[100].get_name()}, 500: {efas_img[500].get_name()}}};
  var EF = {json.dumps(efas_meta)};
  var efasOffGroup = {fg_efas_off.get_name()};
  function efasOff() {{   // scenes hide modelled hazard by default; it stays one click away in the layer controls
    [10, 100, 500].forEach(function(r) {{ if (map.hasLayer(efasGroups[r])) map.removeLayer(efasGroups[r]); }});
    if (!map.hasLayer(efasOffGroup)) efasOffGroup.addTo(map);
  }}
  function activeRp() {{ return [10, 100, 500].find(function(r) {{ return map.hasLayer(efasGroups[r]); }}); }}
  var groups = {{'leg-bldg': [{fg_bldg.get_name()}], 'leg-pop': [{fg_pop.get_name()}],
                'leg-aoi': [{fg_aoi.get_name()}], 'leg-flood': floodGroups, 'leg-water': [{fg_water.get_name()}],
                'leg-efas': [efasGroups[10], efasGroups[100], efasGroups[500]]}};
{shel_js}
  function sync() {{
    for (var id in groups) document.getElementById(id).hidden = !groups[id].some(function(g) {{ return map.hasLayer(g); }});
    var rp = activeRp(); if (rp) document.getElementById('efas-rp').textContent = rp + '-year';
    if (!!rp !== efasOn) {{ efasOn = !!rp; applyFloodStyle(); }}
  }}
  // the grouped (radio) control fires layeradd/layerremove, not overlayadd: debounce to one sync per frame
  var pending = false;
  map.on('overlayadd overlayremove layeradd layerremove', function() {{
    if (!pending) {{ pending = true; requestAnimationFrame(function() {{ pending = false; sync(); }}); }}
  }});
  sync();

  // Click: read the modelled depth back from the active EFAS image (index hidden in the colour's low bits)
  var canvases = {{}};
  function pixel(rp, x, y) {{
    if (!canvases[rp]) {{
      var im = efasImg[rp].getElement(), c = document.createElement('canvas');
      c.width = im.naturalWidth; c.height = im.naturalHeight;
      var ctx = c.getContext('2d', {{willReadFrequently: true}}); ctx.drawImage(im, 0, 0); canvases[rp] = ctx;
    }}
    return canvases[rp].getImageData(x, y, 1, 1).data;
  }}
  var chance = {{10: '10 %', 100: '1 %', 500: '0.2 %'}};
  map.on('click', function(e) {{
    var rp = activeRp(); if (!rp) return;
    var m = EF[rp], pt = L.CRS.EPSG3857.project(e.latlng);
    var x = Math.floor((pt.x - m.x0) / m.res), y = Math.floor((m.y0 - pt.y) / m.res), txt;
    if (x < 0 || y < 0 || x >= m.w || y >= m.h) {{ txt = 'Outside the area shown.'; }}
    else {{
      var v = pixel(rp, x, y);
      if (v[3] === 0) txt = 'No modelled flooding here at this return period.<br><span class="muted">Rivers with a catchment &lt; 500 km² are not modelled: empty ≠ safe.</span>';
      else {{ var i = (v[0] & 7) | ((v[1] & 7) << 3) | ((v[2] & 3) << 6);
             txt = 'Water depth: <b>' + (i === 255 ? '≥ 25.5' : (i * 0.1).toFixed(1)) + ' m</b>'; }}
    }}
    L.popup({{className: 'efas-pop'}}).setLatLng(e.latlng)
      .setContent('<b>Modelled (EFAS) · ' + rp + '-year flood</b><br><span class="muted">' + chance[rp] + ' chance per year</span><br>' + txt)
      .openOn(map);
  }});
  // Keep the flood polygons above the context layers whatever the toggle order
  map.on('overlayadd', function() {{ floods.forEach(function(g) {{ if (map.hasLayer(g)) g.bringToFront(); }}); }});
  // Normal water: drawn only from zoom {WATER_MIN_ZOOM} (keeps the checkbox state; the pane is just hidden)
  function waterZoom() {{
    var show = map.getZoom() >= {WATER_MIN_ZOOM};
    map.getPane('water').style.display = show ? '' : 'none';
    document.getElementById('water-zoom').hidden = show;
    document.getElementById('leg-water').classList.toggle('far', !show);   // legend only where the water is drawn
  }}
  map.on('zoomend', waterZoom); waterZoom();

  // Basemap labels: light or dark Esri reference layer, none on OpenStreetMap (has its own)
  var labels = {labels.get_name()};
  map.on('baselayerchange', function(e) {{
    if (/OpenStreetMap/.test(e.name)) {{ map.removeLayer(labels); return; }}
    labels.setUrl({json.dumps(ESRI)}.replace('{{}}', /Dark/.test(e.name) ? 'Dark_Gray_Reference' : 'Light_Gray_Reference'));
    if (!map.hasLayer(labels)) labels.addTo(map);
  }});
  // Demo view: map centre and zoom only (kept in this browser when possible); never touches the scenario or filters
  var demoKey = 'floodmap-demo-view', demo = null;
  try {{ demo = JSON.parse(localStorage.getItem(demoKey) || 'null'); }} catch (e) {{ demo = null; }}
  var demoGo = document.getElementById('demo-go'), demoNote = document.getElementById('demo-note');
  function demoLabel() {{ demoGo.disabled = !demo; }}
  document.getElementById('demo-save').onclick = function() {{
    var c = map.getCenter();
    demo = {{lat: +c.lat.toFixed(5), lng: +c.lng.toFixed(5), zoom: map.getZoom()}};
    try {{ localStorage.setItem(demoKey, JSON.stringify(demo)); }} catch (e) {{}}
    demoNote.textContent = 'Demo view saved (zoom ' + demo.zoom + '): map view only; scenario results still cover the whole analysis area.';
    demoNote.hidden = false;
    demoLabel();
  }};
  demoGo.onclick = function() {{ if (demo) map.setView([demo.lat, demo.lng], demo.zoom); }};
  demoLabel();
  window.demoView = {{get: function() {{ return demo; }}}};   // for tests
  var ctls = document.querySelectorAll('.leaflet-top.leaflet-right .leaflet-control-layers');
  if (ctls[0]) {{ ctls[0].classList.add('ctl-all'); ctls[0].title = 'All layers (advanced): the scene buttons set the defaults'; }}
  if (ctls[1]) {{ ctls[1].classList.add('ctl-efas'); ctls[1].title = 'Modelled hazard (EFAS), optional context'; }}
  layout(); zoomTo('All');
}});
"""
    extra = "".join((HERE / f).read_text() for f in ["planning/ui.css", "planning/scenes.css", "priority/assets.css"])
    m.get_root().header.add_child(folium.Element(CSS.replace("</style>", extra + "</style>")))
    m.get_root().script.add_child(folium.Element(js))
    m.get_root().title = "July 2021 floods – exposure and planning map"
    m.save(OUT_HTML)
    print(f"Saved {OUT_HTML} ({OUT_HTML.stat().st_size / 1e6:.1f} MB): "
          f"{len(flood_w['features']):,} flood polygons, {len(hex_w['features']):,} hexagons, "
          f"{len(pop_w['features']):,} population cells, "
          + (f"{len(inv):,} candidate shelters" if inv is not None else "no candidate shelter inventory (run shelters.py)"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-read all data from GCS")
    ap.add_argument("--stats", action="store_true", help="print value distributions and stop")
    args = ap.parse_args()
    d = prepare(args.refresh)
    print("Reading EFAS hazard windows ...")
    efas = {rp: load_efas(rp, efas_region(d["aoi"]), args.refresh) for rp in EFAS}
    hydro = load_hydro(args.refresh)
    if args.stats:
        q = [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1]
        for name, col in [("flood", "n_bldg"), ("flood", "residents"), ("flood", "area_ha"),
                          ("hexes", "n_bldg"), ("pop", "pop")]:
            s = d[name][col]
            print(f"{name}.{col}: n={len(s):,} zeros={int((s == 0).sum()):,} sum={s.sum():,.0f}",
                  dict(zip(q, s.quantile(q).round(1))))
        print(d["flood"].groupby("country")[["n_bldg", "n_res_bldg", "residents", "area_ha"]].sum().round(0))
    else:
        build_map(d, efas, hydro, shelters.load_cached(), asset_data())
