"""Water, residents and buildings for every EMS product of the July 2021 flood.

For each Copernicus EMS Rapid Mapping product in the challenge bucket (EMSR518
Belgium, EMSR517 Germany, EMSR520 Netherlands; first products and monitoring
passes as separate rows) this measures, inside the product's AOI:

    observed flooded area             observedEventA, "Flooded area" + "Flood trace"
    agreement with the JRC maps       hit rate / false alarm ratio / CSI per
                                      return period, `src.validate.agreement`
    residents in the observed extent  GHS-POP E2020, weighted by flooded cell share
    ... and outside each hazard map
    buildings in the observed extent  GHS-OBAT by use, epoch and height class,
                                      with footprint totals
    damage grades                     GRA products' builtUpP points

then the same per country on the union of products, deduplicated cell by cell
and building by building. Rules and their reasons are in `src/event2021.py`.

The bucket is read once and cached under `data/raw/challenge_2021/` (EMS
layers as GeoPackages, OBAT points per AOI as parquet, one GHS-POP window), so
a re-run - and the event day - needs no network. Hazard maps come from the
local `data/raw/download/jrc_flood_hazard/` copies, MD5-identical to the
bucket's `cems-efas/` files. Products are processed one at a time to bound RAM.

Writes data/processed/event_2021_{products,hazard,buildings,damage,countries}
as .parquet and .csv.

Run:

    python scripts/event_2021.py              # fetch what is missing, then compute
    python scripts/event_2021.py --offline    # never touch the bucket
    python scripts/event_2021.py --only EMSR517_AOI15
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from scripts.validate_2021 import (
    HAZARD,
    PERMANENT_WATER,
    rasterize_on_grid,
    window_grid,
)
from src import event2021 as E
from src import validate as V

CACHE = ROOT / "data" / "raw" / "challenge_2021"
OUT_DIR = ROOT / "data" / "processed"
TABLES = ("products", "hazard", "buildings", "damage", "countries")
OBAT_COLUMNS = ["id", "height", "use", "epoch", "area"]
# Padding around the AOIs for the population window, in degrees: two 30"
# cells, so a cell on the AOI edge is never cut.
POP_PAD_DEG = 0.02
OBAT_JOBS = 6
BASES = {"product": ("PRODUCT",), "product_and_monit": None}


def _vsigs(path: str) -> str:
    """A bucket-relative path as a GDAL path, read anonymously."""
    os.environ.setdefault("GS_NO_SIGN_REQUEST", "YES")
    return f"/vsigs/{E.BUCKET}/{path}"


def _gpkg(cache: Path, product: E.Product) -> Path:
    """Cached EMS layers of one product."""
    return cache / "ems" / f"{product.product_id}.gpkg"


def _obat(cache: Path, product: E.Product) -> Path:
    """One OBAT cache per AOI: a product and its monitoring pass share it."""
    return cache / "obat" / f"{product.emsr}_AOI{product.aoi}.parquet"


def _pop(cache: Path) -> Path:
    """Cached GHS-POP E2020 window over every AOI."""
    return cache / "ghs_pop_e2020_window.tif"


def load_products(cache: Path, *, offline: bool) -> tuple[list[E.Product], set[str]]:
    """The product list and the ids of graded products, from the manifest or the bucket.

    One bucket listing, written to `products.json`, so later runs and the
    event day never list the bucket again.
    """
    manifest = cache / "products.json"
    if not manifest.exists():
        if offline:
            raise SystemExit(f"{manifest} missing and --offline set: run once with network.")
        names = [n for folder in E.EMS_FOLDERS.values()
                 for n in E.bucket_objects(f"{E.BUCKET_ROOT}/{folder}/")]
        products = E.products_from_names(names)
        listed = set(names)
        graded = [p.product_id for p in products if p.layer_path("builtUpP") in listed]
        cache.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"products": [p.__dict__ for p in products],
                                        "graded": graded}, indent=1))
    data = json.loads(manifest.read_text())
    return [E.Product(**p) for p in data["products"]], set(data["graded"])


def fetch_product(cache: Path, product: E.Product, *, graded: bool) -> None:
    """EMS layers of one product into a GeoPackage: extent, AOI, damage points."""
    import pyogrio

    target = _gpkg(cache, product)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp.gpkg")
    tmp.unlink(missing_ok=True)
    layers = ["observedEventA", "areaOfInterestA"]
    if graded:
        layers.append("builtUpP")
    for layer in layers:
        frame = pyogrio.read_dataframe(_vsigs(product.layer_path(layer)))
        pyogrio.write_dataframe(frame, tmp, layer=layer, driver="GPKG")
    tmp.replace(target)


def aoi_bounds(cache: Path, products: list[E.Product]) -> dict[str, tuple]:
    """Lon/lat bounds per AOI key, the union over that AOI's products."""
    import pyogrio

    out: dict[str, tuple] = {}
    for p in products:
        b = pyogrio.read_dataframe(_gpkg(cache, p), layer="areaOfInterestA").total_bounds
        key = _obat(cache, p).stem
        old = out.get(key, (np.inf, np.inf, -np.inf, -np.inf))
        out[key] = (min(old[0], b[0]), min(old[1], b[1]), max(old[2], b[2]), max(old[3], b[3]))
    return out


def fetch_obat(target: Path, bounds: tuple) -> None:
    """Every OBAT point in a lon/lat box, from all three country files.

    All three, because an AOI near a border (EMSR520 Venlo, EMSR517 Aachen)
    holds buildings of the neighbour, and the country of a building is not the
    country of the activation. The bbox read uses the GeoPackage's spatial
    index, so the 8.6 GB German file is never read whole.
    """
    import pyogrio

    if target.exists():
        return
    frames = []
    for path in E.OBAT_FILES.values():
        f = pyogrio.read_dataframe(_vsigs(f"{E.BUCKET_ROOT}/{path}"), bbox=tuple(bounds),
                                   columns=OBAT_COLUMNS)
        if len(f):
            frames.append(pd.DataFrame({**{c: f[c].to_numpy() for c in OBAT_COLUMNS},
                                        "lon": f.geometry.x.to_numpy(),
                                        "lat": f.geometry.y.to_numpy()}))
    out = pd.concat(frames, ignore_index=True).drop_duplicates("id")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    out.to_parquet(tmp, index=False)
    tmp.replace(target)


def _timed_obat(target: Path, bounds: tuple) -> tuple[str, float]:
    """`fetch_obat` with its wall time, for the progress line."""
    t0 = time.perf_counter()
    fetch_obat(target, bounds)
    return target.stem, time.perf_counter() - t0


def fetch_all_obat(cache: Path, bounds: dict[str, tuple], *, jobs: int = 1) -> None:
    """Cache the OBAT points of every AOI not yet cached, `jobs` AOIs at a time.

    A bbox read over /vsigs/ is bound by request latency, not bandwidth or CPU
    (about 1,000 points a second; the Liege box alone holds 1.6 million), so
    separate processes reading separate AOIs divide the wall time almost by
    their number.
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    todo = {key: box for key, box in bounds.items()
            if not (cache / "obat" / f"{key}.parquet").exists()}
    if not todo:
        return
    with ProcessPoolExecutor(max_workers=max(1, min(jobs, len(todo)))) as pool:
        futures = [pool.submit(_timed_obat, cache / "obat" / f"{key}.parquet", box)
                   for key, box in todo.items()]
        for future in as_completed(futures):
            key, seconds = future.result()
            print(f"  OBAT {key} cached ({seconds:.0f} s)", flush=True)


def fetch_population(target: Path, bounds: list[tuple]) -> None:
    """The GHS-POP E2020 window covering every AOI, written as a small GeoTIFF.

    An existing window is reused only if it covers every AOI asked for: one
    cached for a single AOI would otherwise read as zero residents elsewhere.
    """
    import rasterio
    from rasterio.windows import from_bounds

    west = min(b[0] for b in bounds) - POP_PAD_DEG
    south = min(b[1] for b in bounds) - POP_PAD_DEG
    east = max(b[2] for b in bounds) + POP_PAD_DEG
    north = max(b[3] for b in bounds) + POP_PAD_DEG
    if target.exists():
        with rasterio.open(target) as cached:
            c = cached.bounds
        if c.left <= west and c.bottom <= south and c.right >= east and c.top >= north:
            return
    with rasterio.open(_vsigs(f"{E.BUCKET_ROOT}/{E.POP_E2020}")) as src:
        window = from_bounds(west, south, east, north, src.transform).round_offsets().round_lengths()
        values = src.read(1, window=window)
        profile = {"driver": "GTiff", "height": values.shape[0], "width": values.shape[1],
                   "count": 1, "dtype": values.dtype, "crs": src.crs,
                   "transform": src.window_transform(window), "compress": "deflate"}
    target.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(target, "w", **profile) as dst:
        dst.write(values, 1)


def read_population(path: Path):
    """(counts, transform) of the cached population window."""
    import rasterio

    with rasterio.open(path) as src:
        return src.read(1).astype("float64"), src.transform


def people_on_grid(pop: np.ndarray, transform, grid: V.Grid) -> np.ndarray:
    """Residents per 20 m cell: the cell's density times 400 m2, nearest neighbour.

    The density is per m2 of the 30" cell (`event2021.population_density`), so
    summing it over the flooded 20 m cells of one population cell gives that
    cell's count times its flooded share: the area weighting Annex 2 asks for.
    """
    from rasterio.warp import Resampling, reproject

    density = E.population_density(pop, transform)
    out = np.zeros(grid.shape, dtype="float32")
    reproject(source=density.astype("float32"), destination=out, src_transform=transform,
              src_crs="EPSG:4326", dst_transform=grid.transform(), dst_crs=grid.crs,
              resampling=Resampling.nearest, dst_nodata=0.0)
    return out * np.float32(E.CELL_M2)


def _union(geoms):
    """The polygonal union of `geoms`, or None. Lines and points from a repair
    or an intersection are dropped: they have no area and break rasterising."""
    import shapely

    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return None
    merged = shapely.union_all(shapely.make_valid(np.array(geoms, dtype=object)))
    parts = [g for g in shapely.get_parts(merged) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else None


def _km2(geom) -> float:
    """Area of a lon/lat geometry in km2, measured in equal-area EPSG:3035."""
    import geopandas as gpd

    if geom is None or geom.is_empty:
        return 0.0
    return float(gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(V.SCORING_CRS).area.iloc[0]) / 1e6


def _to_grid_crs(geom):
    """A lon/lat geometry as a one-row GeoSeries in the scoring CRS."""
    import geopandas as gpd

    return gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(V.SCORING_CRS).geometry


def _near(geom, lon, lat, metres: float) -> np.ndarray:
    """Points within `metres` of a lon/lat polygon, measured in EPSG:3035."""
    import shapely
    from pyproj import Transformer

    if geom is None or geom.is_empty or len(lon) == 0:
        return np.zeros(len(lon), dtype=bool)
    x, y = Transformer.from_crs("EPSG:4326", V.SCORING_CRS, always_xy=True).transform(
        np.asarray(lon), np.asarray(lat))
    zone = _to_grid_crs(geom).iloc[0].buffer(metres)
    shapely.prepare(zone)
    return shapely.contains_xy(zone, x, y)


def _cells_of_points(grid: V.Grid, lon, lat) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(row, col, inside) of lon/lat points on `grid`."""
    from pyproj import Transformer

    x, y = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True).transform(
        np.asarray(lon), np.asarray(lat))
    col = np.floor((x - grid.left) / grid.resolution_m).astype("int64")
    row = np.floor((grid.top - y) / grid.resolution_m).astype("int64")
    inside = (row >= 0) & (row < grid.height) & (col >= 0) & (col < grid.width)
    return np.clip(row, 0, grid.height - 1), np.clip(col, 0, grid.width - 1), inside


def analyse_product(product: E.Product, *, cache: Path, pop, hazard=str(HAZARD),
                    permanent_water=PERMANENT_WATER,
                    return_periods=E.RETURN_PERIODS) -> dict:
    """Every figure for one product, plus what the country union needs from it.

    Returns a dict with the product row, its hazard / building / damage rows,
    and the union material: observed cell keys with their residents and wet
    flags, modelled-wet cell keys per headline return period, the AOI and
    observed geometries, the in-AOI buildings and the graded points.
    """
    import pyogrio
    import shapely

    t0 = time.perf_counter()
    gpkg = _gpkg(cache, product)
    aoi_frame = pyogrio.read_dataframe(gpkg, layer="areaOfInterestA")
    events = pyogrio.read_dataframe(gpkg, layer="observedEventA")
    aoi = _union(aoi_frame.geometry)
    kept = events[events["notation"].isin(E.OBSERVED_NOTATIONS)]
    observed = _union(kept.geometry)
    observed = _union([observed.intersection(aoi)]) if observed is not None else None
    observed = observed if observed is not None else shapely.Polygon()
    trace = _union(kept.loc[kept["notation"] == E.FLOOD_TRACE].geometry)
    trace = _union([trace.intersection(aoi)]) if trace is not None else None

    grid = window_grid(tuple(aoi.bounds))
    aoi_mask = rasterize_on_grid(_to_grid_crs(aoi), grid)
    obs_mask = rasterize_on_grid(_to_grid_crs(observed), grid) & aoi_mask
    scorable = aoi_mask & ~(np.nan_to_num(V.read_depth_on_grid(str(permanent_water), grid)) != 0)
    counts, transform = pop
    people = people_on_grid(counts, transform, grid)

    wet_by_rp = {rp: V.modelled_flood_mask(V.read_depth_on_grid(hazard.format(rp=rp), grid))
                 for rp in return_periods}
    hazard_rows = E.hazard_rows(obs_mask, scorable, people, wet_by_rp)
    flooded = obs_mask
    headline = [rp for rp in E.HEADLINE_RETURN_PERIODS if rp in wet_by_rp]

    union = {
        "obs_keys": E.cell_keys(grid, flooded),
        "obs_people": people[flooded].astype("float64"),
        "obs_wet": {rp: wet_by_rp[rp][flooded] for rp in headline},
        "obs_scorable": scorable[flooded],
        "wet_keys": {rp: E.cell_keys(grid, wet_by_rp[rp] & scorable) for rp in headline},
        "aoi": aoi, "observed": observed, "trace": trace,
    }

    # Buildings: OBAT points in the AOI, flagged by the observed polygons and by
    # the hazard cell they fall in.
    obat = pd.read_parquet(_obat(cache, product))
    in_aoi = shapely.contains_xy(aoi, obat["lon"].to_numpy(), obat["lat"].to_numpy())
    b = E.classify_buildings(obat.loc[in_aoi].reset_index(drop=True))
    b["in_observed"] = shapely.contains_xy(observed, b["lon"].to_numpy(), b["lat"].to_numpy())
    b["near_observed"] = _near(observed, b["lon"], b["lat"], E.NEAR_OBSERVED_M)
    row_i, col_i, inside = _cells_of_points(grid, b["lon"], b["lat"])
    for rp in headline:
        b[f"wet_rp{rp}"] = wet_by_rp[rp][row_i, col_i] & inside
    del wet_by_rp
    union["buildings"] = b
    obs_b = b[b["in_observed"]]

    damage = pd.DataFrame()
    if "builtUpP" in pyogrio.list_layers(gpkg)[:, 0]:
        pts = pyogrio.read_dataframe(gpkg, layer="builtUpP")
        damage = pd.DataFrame({
            "lon": pts.geometry.x.to_numpy(), "lat": pts.geometry.y.to_numpy(),
            "damage_grade": pts["damage_gra"].to_numpy(), "obj_type": pts["obj_type"].to_numpy(),
            "in_observed": shapely.contains_xy(observed, pts.geometry.x.to_numpy(),
                                               pts.geometry.y.to_numpy()),
        })
    union["damage"] = damage

    residents_observed = float(people[flooded].sum())
    residents_aoi = E.people_in_polygon(counts, transform, aoi)
    row = {
        **_ids(product),
        "locality": str(aoi_frame["locality"].iloc[0]) if "locality" in aoi_frame else "",
        "aoi_km2": _km2(aoi),
        "observed_km2": _km2(observed),
        "flood_trace_km2": _km2(trace),
        "observed_km2_grid": float(flooded.sum()) * E.CELL_M2 / 1e6,
        "permanent_water_km2_in_observed": float((flooded & aoi_mask & ~scorable).sum()) * E.CELL_M2 / 1e6,
        "observed_polygons_dropped": int(len(events) - len(kept)),
        "detection_method": ";".join(sorted(kept["det_method"].astype(str).unique()))
        if "det_method" in kept else "",
        "residents_aoi": residents_aoi,
        "residents_aoi_grid": float(people[aoi_mask].sum()),
        "residents_observed": residents_observed,
        "residents_observed_vector": E.people_in_polygon(counts, transform, observed),
    }
    for h in hazard_rows:
        if h["return_period"] in headline:
            rp = h["return_period"]
            row[f"hit_rate_rp{rp}"] = h["hit_rate"]
            row[f"false_alarm_ratio_rp{rp}"] = h["false_alarm_ratio"]
            row[f"residents_outside_rp{rp}"] = h["residents_outside_map"]
            row[f"share_residents_outside_rp{rp}"] = h["share_residents_outside_map"]
    row.update(_building_summary(b, residents_aoi, residents_observed, headline))
    row.update(_damage_summary(damage, graded=not damage.empty))
    row["runtime_s"] = time.perf_counter() - t0

    hazard_frame = pd.DataFrame([{**_ids(product), **h} for h in hazard_rows])
    buildings_frame = pd.concat([E.building_breakdown(b, scope="aoi"),
                                 E.building_breakdown(obs_b, scope="observed")], ignore_index=True)
    buildings_frame = _label(buildings_frame, product)
    damage_frame = _label(E.damage_breakdown(damage), product)
    return {"row": row, "hazard": hazard_frame, "buildings": buildings_frame,
            "damage": damage_frame, "union": union}


def _ids(product: E.Product) -> dict:
    """The identifying columns every product-level row starts with."""
    return {"country": product.country, "product_id": product.product_id,
            "emsr": product.emsr, "aoi": f"AOI{product.aoi}", "product_type": product.type,
            "product_kind": product.kind, "version": int(product.version)}


def _label(frame: pd.DataFrame, product: E.Product | None, *, country: str = "",
           basis: str = "single_product") -> pd.DataFrame:
    """Prefix a breakdown with its level, country, basis and product id."""
    lead = {"level": "product" if product else "country",
            "country": product.country if product else country,
            "extent_basis": basis,
            "product_id": product.product_id if product else ""}
    return pd.concat([pd.DataFrame({k: [v] * len(frame) for k, v in lead.items()}),
                      frame.reset_index(drop=True)], axis=1)


def _building_summary(b: pd.DataFrame, residents_aoi: float, residents_observed: float,
                      headline) -> dict:
    """Building counts and the buildings-per-resident ratios for one scope set."""
    obs = b[b["in_observed"]]
    out = {
        "buildings_aoi": len(b),
        "residential_buildings_aoi": int((b["use_class"] == "residential").sum()),
        "buildings_observed": len(obs),
        f"buildings_within_{int(E.NEAR_OBSERVED_M)}m_of_observed": int(b["near_observed"].sum()),
        "residential_buildings_observed": int((obs["use_class"] == "residential").sum()),
        "non_residential_buildings_observed": int((obs["use_class"] == "non_residential").sum()),
        "footprint_m2_observed": float(obs["area"].sum()),
        "residential_footprint_m2_observed": float(obs.loc[obs["use_class"] == "residential", "area"].sum()),
        "buildings_per_resident_aoi": E.ratio(len(b), residents_aoi),
        "residential_buildings_per_resident_aoi": E.ratio((b["use_class"] == "residential").sum(),
                                                          residents_aoi),
        "buildings_per_resident_observed": E.ratio(len(obs), residents_observed),
    }
    for rp in headline:
        out[f"buildings_observed_outside_rp{rp}"] = int((~obs[f"wet_rp{rp}"]).sum())
    return out


def _damage_summary(damage: pd.DataFrame, *, graded: bool) -> dict:
    """Graded buildings per grade, NaN for a product that grades nothing."""
    out = {"graded_buildings": len(damage) if graded else np.nan}
    for grade in E.DAMAGE_GRADES:
        key = "graded_" + grade.lower().replace(" ", "_")
        out[key] = int((damage["damage_grade"] == grade).sum()) if graded else np.nan
    return out


def country_rows(results: list[tuple[E.Product, dict]], pop) -> tuple[list, list, list]:
    """Per country and extent basis: the union of products, deduplicated.

    Cells by global key (`event2021.cell_keys`), buildings by OBAT id (in the
    observed extent if any product saw them flooded), graded points by
    position, the later pass winning. `product` takes first products only,
    `product_and_monit` every pass: the largest extent ever mapped.
    """
    counts, transform = pop
    rows, buildings, damages = [], [], []
    for country in sorted({p.country for p, _ in results}):
        for basis, kinds in BASES.items():
            chosen = [(p, r["union"]) for p, r in results
                      if p.country == country and (kinds is None or p.kind in kinds)]
            if not chosen:
                continue
            keys = np.concatenate([u["obs_keys"] for _, u in chosen])
            uniq, first = np.unique(keys, return_index=True)
            people = np.concatenate([u["obs_people"] for _, u in chosen])[first]
            residents = float(people.sum())
            aoi = _union([u["aoi"] for _, u in chosen])
            observed = _union([u["observed"] for _, u in chosen])
            trace = _union([u["trace"] for _, u in chosen])
            residents_aoi = E.people_in_polygon(counts, transform, aoi)
            row = {"country": country, "extent_basis": basis, "n_products": len(chosen),
                   "products": ";".join(p.product_id for p, _ in chosen),
                   "aoi_km2": _km2(aoi), "observed_km2": _km2(observed),
                   "flood_trace_km2": _km2(trace),
                   "observed_km2_grid": uniq.size * E.CELL_M2 / 1e6,
                   "residents_aoi": residents_aoi, "residents_observed": residents}
            scorable = np.concatenate([u["obs_scorable"] for _, u in chosen])[first]
            for rp in chosen[0][1]["wet_keys"]:
                wet = np.concatenate([u["obs_wet"][rp] for _, u in chosen])[first]
                wet_cells = np.unique(np.concatenate([u["wet_keys"][rp] for _, u in chosen])).size
                hits = int((wet & scorable).sum())
                outside = float(people[~wet].sum())
                row[f"hit_rate_rp{rp}"] = E.ratio(hits, int(scorable.sum()))
                row[f"false_alarm_ratio_rp{rp}"] = E.ratio(wet_cells - hits, wet_cells)
                row[f"residents_outside_rp{rp}"] = outside
                row[f"share_residents_outside_rp{rp}"] = E.ratio(outside, residents)
            b = pd.concat([u["buildings"] for _, u in chosen], ignore_index=True)
            flags = ["in_observed", "near_observed"] + [c for c in b.columns
                                                        if c.startswith("wet_rp")]
            agg = b.groupby("id")[flags].max()
            b = b.drop_duplicates("id").drop(columns=flags).join(agg, on="id")
            row.update(_building_summary(b, residents_aoi, residents,
                                         [int(c[6:]) for c in flags[2:]]))
            graded = [u["damage"].assign(kind=p.kind) for p, u in chosen if not u["damage"].empty]
            if graded:
                d = pd.concat(graded, ignore_index=True)
                d["pos"] = list(zip(d["lon"].round(6), d["lat"].round(6)))
                d = d.sort_values("kind", key=lambda s: s != "PRODUCT", kind="stable")
                d = d.drop_duplicates("pos", keep="last")
            else:
                d = pd.DataFrame()
            row.update(_damage_summary(d, graded=bool(graded)))
            rows.append(row)
            obs_b = b[b["in_observed"]]
            buildings.append(_label(pd.concat([E.building_breakdown(b, scope="aoi"),
                                               E.building_breakdown(obs_b, scope="observed")],
                                              ignore_index=True), None,
                                    country=country, basis=basis))
            damages.append(_label(E.damage_breakdown(d), None, country=country, basis=basis))
    return rows, buildings, damages


def write_tables(tables: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    """Each table as event_2021_<name>.parquet and .csv; returns the parquet paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, frame in tables.items():
        path = out_dir / f"event_2021_{name}.parquet"
        frame.to_parquet(path, index=False)
        frame.to_csv(path.with_suffix(".csv"), index=False)
        paths.append(path)
    return paths


def _print(products: pd.DataFrame, countries: pd.DataFrame) -> None:
    """The headline columns of the product and country tables."""
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    cols = ["product_id", "locality", "observed_km2", "residents_observed",
            "hit_rate_rp100", "share_residents_outside_rp100", "buildings_observed",
            "residential_buildings_observed", "buildings_per_resident_aoi", "runtime_s"]
    print(products[[c for c in cols if c in products]].round(3).to_string(index=False))
    ccols = ["country", "extent_basis", "observed_km2", "residents_observed",
             "hit_rate_rp10", "hit_rate_rp100", "hit_rate_rp500", "residents_outside_rp100",
             "buildings_observed", "buildings_per_resident_aoi", "graded_buildings"]
    print()
    print(countries[[c for c in ccols if c in countries]].round(3).to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    """Fetch what the cache lacks (unless --offline), analyse each product, write the tables."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    parser.add_argument("--only", nargs="*", default=None,
                        help="product id prefixes to keep, e.g. EMSR517_AOI15")
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--jobs", type=int, default=OBAT_JOBS,
                        help="parallel OBAT downloads (one process per AOI)")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    products, graded = load_products(args.cache, offline=args.offline)
    if not args.offline:
        # Every product's layers (a few MB) and one population window over all
        # of them, whatever --only says, so the cached window is never partial.
        for p in products:
            fetch_product(args.cache, p, graded=p.product_id in graded)
        fetch_population(_pop(args.cache), list(aoi_bounds(args.cache, products).values()))
    if args.only:
        products = [p for p in products if any(p.product_id.startswith(o) for o in args.only)]
    if not args.offline:
        fetch_all_obat(args.cache, aoi_bounds(args.cache, products), jobs=args.jobs)
    pop = read_population(_pop(args.cache))

    results = []
    for p in products:
        r = analyse_product(p, cache=args.cache, pop=pop)
        print(f"{p.product_id}: {r['row']['observed_km2']:.2f} km2, "
              f"{r['row']['residents_observed']:,.0f} residents, "
              f"{r['row']['buildings_observed']:,} buildings ({r['row']['runtime_s']:.0f} s)",
              flush=True)
        results.append((p, r))

    country, cbuild, cdamage = country_rows(results, pop)
    tables = {
        "products": pd.DataFrame([r["row"] for _, r in results]),
        "hazard": pd.concat([r["hazard"] for _, r in results], ignore_index=True),
        "buildings": pd.concat([r["buildings"] for _, r in results] + cbuild, ignore_index=True),
        "damage": pd.concat([r["damage"] for _, r in results] + cdamage, ignore_index=True),
        "countries": pd.DataFrame(country),
    }
    paths = write_tables(tables, args.out_dir)
    _print(tables["products"], tables["countries"])
    for path in paths:
        print(f"wrote {path} ({len(pd.read_parquet(path))} rows)")
    print(f"total {time.perf_counter() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
