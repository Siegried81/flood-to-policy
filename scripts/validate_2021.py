"""Score the hazard maps against every July 2021 ground truth on disk, in Wallonia.

Four modelled footprints - the JRC 10-, 100- and 500-year depth maps and the
official Walloon *aléa* map - are scored against four independent observations
of the July 2021 flood:

    jrc_observed_2021      JRC satellite-derived depth, WD_MERGE cluster 159
    wallonia_depth_2021    Walloon IDW water-depth raster (1 m, depth > 0)
    wallonia_extent_2021   Walloon recorded flooded areas (vector)
    cems_emsr518_2021      Copernicus EMS EMSR518 observedEventA, inside its AOIs

with `src.validate.agreement`: hit rate, false alarm ratio and CSI (the
module's `iou`), per (model, truth). The truths are also scored against one
another, because where they disagree is the uncertainty of the ground truth
itself; the printed table and the file carry every truth, and no single one is
picked as "the" answer.

Windowed reads only, on two fixed EPSG:3035 20 m windows: the Walloon depth
raster's own footprint (4.18-6.06 E, 50.10-50.75 N, the Vesdre, Ourthe and
Amblève) and the Ahr (6.70-7.30 E, 50.30-50.60 N), where only the JRC
observed layer reaches. `validate.scoring_grid` is not used because the
intersection of a European hazard map and the European WD_MERGE tile is about
2.7e9 cells.

Choices that move a figure, each also written on every row:

- "flooded" is depth > 0 in every layer (`validate.DEFAULT_MIN_DEPTH_M`).
- the *aléa* map is scored twice, including and excluding the very-low class
  101/201/301 (*très faible*), because the class choice alone moves its hit
  rate; neither variant is the default.
- Walloon truths and the *aléa* map are scored inside Wallonia only (NUTS 2024
  BE3 regions rasterised by cell centre), since neither says anything outside
  it; EMSR518 inside the union of its AOIs; the JRC observed layer inside its
  footprint, minus its 9999 permanent-water code.
- JRC permanent water bodies are dropped from every matrix (a river is not a
  flood).
- EMSR518 is the union of all four packages (AOI01/AOI02, delineation and
  monitoring), i.e. the maximum observed extent.

Then the population living inside each observed extent but outside each map,
from the GHSL 100 m tiles (`ghsl_pop_100m_tiles`, epoch 2025 - the nearest
GHSL epoch, not a 2021 count) summed onto a 100 m EPSG:3035 grid of 5 x 5
scoring cells. A 100 m cell is in an observed extent when its centre 20 m
cell is. Two hazard rules give two figures:

    conservative   a cell is inside the map when ANY of its 25 sub-cells is
                   wet, so the fewest people are counted outside the map
    upper          a cell is inside the map only when its CENTRE sub-cell is

Writes data/processed/validation_2021.parquet (scores) and
data/processed/validation_2021_population.parquet (population), and prints both.

Run:

    python scripts/validate_2021.py
    python scripts/validate_2021.py --windows ahr
"""

from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import validate as V  # noqa: E402

RAW = ROOT / "data" / "raw" / "download"
HAZARD = RAW / "jrc_flood_hazard" / "Europe_RP{rp}_filled_depth.tif"
PERMANENT_WATER = RAW / "jrc_flood_hazard" / "Europe_permanent_water_bodies.tif"
JRC_OBSERVED = (
    RAW / "jrc_observed_flood_depth"
    / "WD_MERGE_2021-07-12---2021-08-02_duration_21_days_cluster_159_A0_000619"
      "_A_000852_lat_04942_lon_00499_size_0246.tif"
)
WALLONIA_DEPTH = (
    f"zip://{(RAW / 'wallonia_observed_water_depth_2021.zip').as_posix()}"
    "!ZONES_INONDEES_2021_IDW450_HEAU.tif"
)
ALEA = (
    "zip://" + (RAW / "wallonia_flood_hazard_official"
                / "ALEA_INOND_2020__ALEA_MAP_GEOTIFF_31370.zip").as_posix()
    + "!ALEA_INOND_2020__ALEA_MAP.tif"
)
WALLONIA_EXTENT = (
    "zip://" + (RAW / "wallonia_observed_flooded_areas_2021"
                / "ZONES_INONDEES_202107_GEOPACKAGE_31370.zip").as_posix()
    + "!ZONES_INONDEES_202107.gpkg"
)
CEMS_DIR = RAW / "cems_emsr518_belgium_2021"
CEMS_PACKAGES = ("AOI01_DEL_PRODUCT", "AOI01_DEL_MONIT01",
                 "AOI02_DEL_PRODUCT", "AOI02_DEL_MONIT01")
GHSL_TILES = tuple(
    RAW / "ghsl_pop_100m_tiles" / f"GHS_POP_E2025_GLOBE_R2023A_54009_100_V1_0_{t}.zip"
    for t in ("R3_C19", "R4_C19")
)
NUTS3 = RAW / "gisco_nuts3.geojson"
WALLONIA_NUTS_PREFIX = "BE3"

OUT = ROOT / "data" / "processed" / "validation_2021.parquet"
OUT_POPULATION = ROOT / "data" / "processed" / "validation_2021_population.parquet"

# (west, south, east, north) in degrees, and the truths each window can score.
WINDOWS = {
    "wallonia": ((4.18, 50.10, 6.06, 50.75),
                 ("jrc_observed_2021", "wallonia_depth_2021",
                  "wallonia_extent_2021", "cems_emsr518_2021")),
    "ahr": ((6.70, 50.30, 7.30, 50.60), ("jrc_observed_2021",)),
}
RETURN_PERIODS = (10, 100, 500)
# 5 x 20 m = 100 m, the GHSL resolution; odd, so one sub-cell holds the centre.
POPULATION_BLOCK = 5
CELL_KM2 = (V.SCORING_RESOLUTION_M / 1000.0) ** 2

# Walloon aléa CLASSEMENT: hundreds digit = origin (1 overflow, 2 runoff, 3
# both), remainder = level (01 very low "très faible", 10 low, 20 medium, 30 high).
ALEA_ORIGINS = (1, 2, 3)
ALEA_LEVELS = (1, 10, 20, 30)
ALEA_TRES_FAIBLE = 1

TRUTH_DEFINITIONS = {
    "jrc_observed_2021": "WD_MERGE cluster 159 depth > 0 cm, inside its footprint, 9999 excluded",
    "wallonia_depth_2021": "Walloon IDW depth raster > 0, inside Wallonia (NUTS BE3)",
    "wallonia_extent_2021": "Walloon recorded flooded polygons, cell-centre rasterised, inside Wallonia",
    "cems_emsr518_2021": "EMSR518 observedEventA, union of 4 packages, inside the union of their AOIs",
}
MODEL_DEFINITIONS = {
    **{f"jrc_rp{rp}": f"JRC RP{rp} depth > 0 m, nodata read as dry" for rp in RETURN_PERIODS},
    "alea_incl_tres_faible": "Walloon aléa, every class incl. très faible 101/201/301, inside Wallonia",
    "alea_excl_tres_faible": "Walloon aléa, classes x10/x20/x30 only (très faible excluded), inside Wallonia",
}


def window_grid(bounds_lonlat: tuple[float, float, float, float], *,
                resolution_m: float = V.SCORING_RESOLUTION_M,
                block: int = POPULATION_BLOCK) -> V.Grid:
    """The EPSG:3035 scoring grid covering a lon/lat box, in whole population blocks.

    Snapped outward to multiples of `block` cells so the 100 m population grid
    is an exact 5 x 5 aggregation of the 20 m scoring grid and no scoring cell
    belongs to two population cells.
    """
    from rasterio.warp import transform_bounds

    left, bottom, right, top = transform_bounds(
        "EPSG:4326", V.SCORING_CRS, *bounds_lonlat, densify_pts=21)
    step = resolution_m * block
    left = np.floor(left / step) * step
    top = np.ceil(top / step) * step
    width = int(np.ceil((right - left) / step)) * block
    height = int(np.ceil((top - bottom) / step)) * block
    return V.Grid(left=float(left), top=float(top), width=width, height=height,
                  resolution_m=resolution_m)


def rasterize_on_grid(geometries, grid: V.Grid) -> np.ndarray:
    """Polygons (already in the grid CRS) to a boolean mask, by cell centre.

    Cell centre (`all_touched=False`) rather than any touch, so a polygon's
    rasterised area is unbiased against its true area instead of inflated by
    every boundary cell; the rule is named on every row as the truth's
    definition.
    """
    from rasterio.features import rasterize

    shapes = [(g, 1) for g in geometries if g is not None and not g.is_empty]
    if not shapes:
        return np.zeros(grid.shape, dtype=bool)
    return rasterize(shapes, out_shape=grid.shape, transform=grid.transform(),
                     fill=0, dtype="uint8", all_touched=False).astype(bool)


def alea_mask(codes: np.ndarray, *, include_tres_faible: bool) -> np.ndarray:
    """Walloon aléa CLASSEMENT codes to a hazard mask.

    Only the twelve declared codes count; nodata (read as NaN) and anything else
    is outside the map. `include_tres_faible` is keyword-only and has no
    default because the very-low class 101/201/301 is a choice that moves the
    score, and it has to be made visibly at the call.
    """
    c = np.nan_to_num(np.asarray(codes, dtype="float64"), nan=0.0).astype("int64")
    level = c % 100
    mask = np.isin(c // 100, ALEA_ORIGINS) & np.isin(level, ALEA_LEVELS)
    if not include_tres_faible:
        mask &= level != ALEA_TRES_FAIBLE
    return mask


def score_table(models: dict[str, tuple[np.ndarray, np.ndarray | None]],
                truths: dict[str, tuple[np.ndarray, np.ndarray]], *,
                exclude: np.ndarray | None = None, window: str = "",
                kind: str = "model_vs_truth",
                definitions: dict[str, str] | None = None) -> pd.DataFrame:
    """One row per (model, truth): the confusion matrix, areas and three scores.

    `models` maps a name to (wet mask, coverage), coverage None meaning the
    model speaks for the whole window; `truths` maps a name to (flooded mask,
    domain). A pair is scored over domain AND coverage AND NOT `exclude`, so a
    map is never charged with misses where it says nothing and a truth never
    with absences where it did not look. A pair with no scorable cell is left
    out rather than written as zeros. Below `V.MIN_OBSERVED_CELLS` observed
    cells the ratios are NaN, as in `agreement_by_unit`.
    """
    definitions = {**TRUTH_DEFINITIONS, **MODEL_DEFINITIONS, **(definitions or {})}
    rows = []
    for model, (wet, coverage) in models.items():
        for truth, (flooded, domain) in truths.items():
            if model == truth:
                continue
            keep = np.asarray(domain, dtype=bool)
            if coverage is not None:
                keep = keep & coverage
            if exclude is not None:
                keep = keep & ~exclude
            if not keep.any():
                continue
            a = V.agreement(wet, flooded, scorable=keep)
            thin = a.observed_flood_cells < V.MIN_OBSERVED_CELLS
            rows.append({
                "window": window, "kind": kind, "model": model, "truth": truth,
                "true_positive": a.true_positive, "false_positive": a.false_positive,
                "false_negative": a.false_negative, "true_negative": a.true_negative,
                "scored_cells": a.scored_cells,
                "observed_km2": a.observed_flood_cells * CELL_KM2,
                "modelled_km2": a.modelled_flood_cells * CELL_KM2,
                "hit_rate": np.nan if thin or a.hit_rate is None else a.hit_rate,
                "false_alarm_ratio": (np.nan if thin or a.false_alarm_ratio is None
                                      else a.false_alarm_ratio),
                "csi": np.nan if thin or a.iou is None else a.iou,
                "model_definition": definitions.get(model, model),
                "truth_definition": definitions.get(truth, truth),
                "caveat": V.CAVEAT if kind == "model_vs_truth" else V.ABSENCE_CAVEAT,
            })
    return pd.DataFrame(rows)


def truth_pairs(truths: dict[str, tuple[np.ndarray, np.ndarray]], *,
                exclude: np.ndarray | None = None, window: str = "") -> pd.DataFrame:
    """Each pair of truths scored once, the first standing in for the model.

    One ordering per pair is enough: CSI is symmetric, and the reverse hit rate
    is one minus this row's false alarm ratio. The domain of the "model" truth
    is its coverage, so only the area both truths looked at is compared.
    """
    names = list(truths)
    frames = [
        score_table({a: truths[a]}, {b: truths[b]}, exclude=exclude,
                    window=window, kind="truth_vs_truth")
        for i, a in enumerate(names) for b in names[i + 1:]
    ]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def block_any(mask: np.ndarray, block: int) -> np.ndarray:
    """True where any cell of each `block` x `block` tile is true."""
    h, w = mask.shape
    return mask.reshape(h // block, block, w // block, block).any(axis=(1, 3))


def block_centre(mask: np.ndarray, block: int) -> np.ndarray:
    """The centre cell of each `block` x `block` tile (block must be odd)."""
    if block % 2 == 0:
        raise ValueError("block must be odd so that one cell holds the tile centre")
    return mask[block // 2::block, block // 2::block]


def population_outside(population: np.ndarray,
                       models: dict[str, tuple[np.ndarray, np.ndarray | None]],
                       truths: dict[str, tuple[np.ndarray, np.ndarray]], *,
                       block: int = POPULATION_BLOCK, window: str = "") -> pd.DataFrame:
    """People inside each observed extent, split by inside / outside each map.

    `population` is on the block grid, the masks on the scoring grid. A
    population cell is in a truth when its centre sub-cell is flooded and in
    the truth's domain (and in the model's coverage, so the *aléa* rows count
    Wallonia only). Two rows per pair: `conservative` puts a cell inside the
    map when any sub-cell is wet - the lower bound on people outside - and
    `upper` only when the centre sub-cell is.
    """
    pop = np.nan_to_num(np.asarray(population, dtype="float64"))
    rows = []
    for truth, (flooded, domain) in truths.items():
        for model, (wet, coverage) in models.items():
            inside_truth = block_centre(flooded & domain, block)
            if coverage is not None:
                inside_truth = inside_truth & block_centre(coverage, block)
            if not inside_truth.any():
                continue
            for variant, rule, model_cells in (
                ("conservative", "any_20m_subcell", block_any(wet, block)),
                ("upper", "centre_20m_subcell", block_centre(wet, block)),
            ):
                total = float(pop[inside_truth].sum())
                outside = float(pop[inside_truth & ~model_cells].sum())
                rows.append({
                    "window": window, "truth": truth, "model": model,
                    "variant": variant, "hazard_rule": rule,
                    "pop_in_truth": total,
                    "pop_in_truth_inside_model": total - outside,
                    "pop_in_truth_outside_model": outside,
                    "share_outside_model": outside / total if total else np.nan,
                    "pop_inside_model_in_window": float(pop[model_cells].sum()),
                    "pop_in_window": float(pop.sum()),
                    "truth_definition": TRUTH_DEFINITIONS.get(truth, truth),
                    "model_definition": MODEL_DEFINITIONS.get(model, model),
                })
    return pd.DataFrame(rows)


def population_grid(grid: V.Grid, block: int = POPULATION_BLOCK) -> V.Grid:
    """The 100 m grid whose cells are exact `block` x `block` tiles of `grid`."""
    return V.Grid(left=grid.left, top=grid.top, width=grid.width // block,
                  height=grid.height // block,
                  resolution_m=grid.resolution_m * block, crs=grid.crs)


def read_population_on_grid(tile_paths, grid: V.Grid) -> np.ndarray:
    """GHSL people per cell of `grid`, summed from every tile that reaches it.

    `Resampling.sum` weights each source cell by the share of it that falls in
    the destination cell, so people are moved, not counted twice; the tiles
    are summed because a destination cell on a tile edge takes part of its
    people from each. Nodata (-200) contributes nothing.
    """
    rio = V._require_rasterio()
    from rasterio.warp import Resampling, reproject

    total = np.zeros(grid.shape, dtype="float64")
    for path in tile_paths:
        with rio.open(path) as src:
            part = np.full(grid.shape, np.nan, dtype="float32")
            reproject(source=rio.band(src, 1), destination=part,
                      src_crs=src.crs, src_transform=src.transform,
                      src_nodata=src.nodata, dst_crs=grid.crs,
                      dst_transform=grid.transform(), dst_nodata=np.nan,
                      resampling=Resampling.sum)
            total += np.nan_to_num(part)
    return total


def native_population_in_grid(tile_paths, grid: V.Grid) -> float:
    """People in source cells whose centres fall inside `grid`, read natively.

    The check on `read_population_on_grid`: no resampling at all, so the two
    totals should agree to within the edge cells of the window.
    """
    rio = V._require_rasterio()
    from pyproj import Transformer
    from rasterio.errors import WindowError
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window, from_bounds

    right = grid.left + grid.width * grid.resolution_m
    bottom = grid.top - grid.height * grid.resolution_m
    people = 0.0
    for path in tile_paths:
        with rio.open(path) as src:
            box = transform_bounds(grid.crs, src.crs, grid.left, bottom, right,
                                   grid.top, densify_pts=21)
            window = from_bounds(*box, transform=src.transform).round_offsets().round_lengths()
            try:
                window = window.intersection(Window(0, 0, src.width, src.height))
            except WindowError:
                continue
            values = src.read(1, window=window).astype("float64")
            values[values == src.nodata] = 0.0
            rows, cols = np.nonzero(values)
            t = src.window_transform(window)
            xs = t.c + (cols + 0.5) * t.a
            ys = t.f + (rows + 0.5) * t.e
            x3035, y3035 = Transformer.from_crs(src.crs, grid.crs, always_xy=True).transform(xs, ys)
            inside = ((x3035 >= grid.left) & (x3035 < right)
                      & (y3035 <= grid.top) & (y3035 > bottom))
            people += float(values[rows, cols][inside].sum())
    return people


def _read(path, grid, **kwargs) -> np.ndarray:
    """`validate.read_depth_on_grid` with a timing line, for a long run."""
    t0 = time.perf_counter()
    out = V.read_depth_on_grid(str(path), grid, **kwargs)
    print(f"  read {Path(str(path).split('!')[-1]).name} ({time.perf_counter() - t0:.0f} s)",
          flush=True)
    return out


def _vector(path: str):
    """A vector file in EPSG:3035."""
    import geopandas as gpd

    return gpd.read_file(path).to_crs(V.SCORING_CRS)


def _cems(kind: str):
    """EMSR518 `observedEventA` or `areaOfInterestA`, all four packages."""
    frames = []
    for pkg in CEMS_PACKAGES:
        z = CEMS_DIR / f"EMSR518_{pkg}_r1_VECTORS_v1_vector.zip"
        frames.append(_vector(f"zip://{z.as_posix()}!EMSR518_{pkg}_{kind}_r1_v1.shp"))
    return pd.concat(frames, ignore_index=True)


def _ghsl_paths() -> list[str]:
    """The GDAL paths of the GHSL GeoTIFFs inside their zips."""
    paths = []
    for z in GHSL_TILES:
        name = next(n for n in zipfile.ZipFile(z).namelist() if n.endswith(".tif"))
        paths.append(f"zip://{z.as_posix()}!{name}")
    return paths


def build_window(name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every score and population row for one window, from the files on disk."""
    import geopandas as gpd

    bounds, truth_names = WINDOWS[name]
    grid = window_grid(bounds)
    print(f"{name}: {grid.height} x {grid.width} cells at {grid.resolution_m:g} m", flush=True)
    exclude = np.nan_to_num(_read(PERMANENT_WATER, grid)) != 0

    nuts = gpd.read_file(NUTS3)
    wallonia = rasterize_on_grid(
        nuts.loc[nuts["NUTS_ID"].str.startswith(WALLONIA_NUTS_PREFIX)].to_crs(V.SCORING_CRS).geometry,
        grid)

    truths: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if "jrc_observed_2021" in truth_names:
        obs = _read(JRC_OBSERVED, grid, declared_crs=V.observed_crs(),
                    nodata=V.OBSERVED_READ_NODATA)
        truths["jrc_observed_2021"] = (V.observed_flood_mask(obs),
                                       V.observed_scorable_mask(obs))
        del obs
    if "wallonia_depth_2021" in truth_names:
        depth = _read(WALLONIA_DEPTH, grid)
        truths["wallonia_depth_2021"] = (np.isfinite(depth) & (depth > 0), wallonia)
        del depth
    if "wallonia_extent_2021" in truth_names:
        extent = _vector(WALLONIA_EXTENT)
        truths["wallonia_extent_2021"] = (rasterize_on_grid(extent.geometry, grid), wallonia)
        right = grid.left + grid.width * grid.resolution_m
        bottom = grid.top - grid.height * grid.resolution_m
        inside = extent.clip((grid.left, bottom, right, grid.top)).area.sum()
        print(f"  Walloon extent polygons: {extent.area.sum() / 1e6:.1f} km2 in all "
              f"(overlaps counted), {inside / 1e6:.1f} km2 inside the window", flush=True)
        del extent
    if "cems_emsr518_2021" in truth_names:
        truths["cems_emsr518_2021"] = (rasterize_on_grid(_cems("observedEventA").geometry, grid),
                                       rasterize_on_grid(_cems("areaOfInterestA").geometry, grid))

    models: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
    for rp in RETURN_PERIODS:
        models[f"jrc_rp{rp}"] = (V.modelled_flood_mask(_read(str(HAZARD).format(rp=rp), grid)),
                                 None)
    if wallonia.any():
        codes = _read(ALEA, grid)
        models["alea_incl_tres_faible"] = (alea_mask(codes, include_tres_faible=True), wallonia)
        models["alea_excl_tres_faible"] = (alea_mask(codes, include_tres_faible=False), wallonia)
        del codes

    scores = pd.concat(
        [score_table(models, truths, exclude=exclude, window=name),
         truth_pairs(truths, exclude=exclude, window=name)], ignore_index=True)

    population = pd.DataFrame()
    if name == "wallonia":
        pgrid = population_grid(grid)
        paths = _ghsl_paths()
        pop = read_population_on_grid(paths, pgrid)
        native = native_population_in_grid(paths, pgrid)
        print(f"  population on the 100 m grid {pop.sum():,.0f}; native cell centres "
              f"inside it {native:,.0f} ({pop.sum() / native - 1:+.3%})", flush=True)
        population = population_outside(pop, models, truths, window=name)
    return scores, population


def _print(scores: pd.DataFrame, population: pd.DataFrame) -> None:
    """The two tables, then each model's hit rate against every truth on one line."""
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 500)
    cols = ["window", "kind", "model", "truth", "observed_km2", "modelled_km2",
            "hit_rate", "false_alarm_ratio", "csi"]
    print(scores[cols].round(3).to_string(index=False))
    print("\nHit rate of each model against each truth (the truths disagree; quote all):")
    for (window, model), g in scores[scores["kind"] == "model_vs_truth"].groupby(
            ["window", "model"], sort=False):
        parts = ", ".join(f"{r.truth} {r.hit_rate:.3f}" for r in g.itertuples())
        print(f"  {window} {model}: {parts}")
    if not population.empty:
        pcols = ["truth", "model", "variant", "pop_in_truth", "pop_in_truth_outside_model",
                 "share_outside_model", "pop_inside_model_in_window"]
        print("\nPopulation (GHSL 2025, 100 m) inside each observed extent, outside each map:")
        print(population[pcols].round(3).to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--windows", nargs="+", choices=list(WINDOWS), default=list(WINDOWS))
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--out-population", type=Path, default=OUT_POPULATION)
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    results = [build_window(w) for w in args.windows]
    scores = pd.concat([r[0] for r in results], ignore_index=True)
    population = pd.concat([r[1] for r in results], ignore_index=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(args.out, index=False)
    if not population.empty:
        population.to_parquet(args.out_population, index=False)
    _print(scores, population)
    print(f"\nwrote {args.out} ({len(scores)} rows)"
          + (f" and {args.out_population} ({len(population)} rows)" if not population.empty else "")
          + f" in {time.perf_counter() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
