"""The July 2021 flood, product by product: water, people and buildings per EMS map.

The European AI Challenge ships four datasets for the 2021 event in Belgium,
Germany and the Netherlands (`config/sources.yaml`, ids `challenge_*`): the
Copernicus EMS Rapid Mapping products (where the water was seen), the JRC
hazard maps (where a model expected it), GHS-POP E2020 (who lived there) and
GHS-OBAT (which buildings stood there). This module holds the rules that turn
one EMS product into figures; `scripts/event_2021.py` reads the files and
writes the tables.

How each figure is measured, and why:

- **The unit is one EMS product**, i.e. one AOI at one date: the first
  delineation or grading (`PRODUCT`) and each later monitoring pass
  (`MONIT01`) are separate rows, never merged into one extent, because they
  are snapshots of the water at different times and neither is the peak.
  Country totals are taken on the union of products, deduplicated cell by cell
  and building by building, so two AOIs over the same valley (EMSR517 AOI03 and
  AOI15 both cover the Ahr) are not counted twice.
- **Outside an AOI nothing was mapped.** Every grid figure is computed inside
  the product's `areaOfInterestA` only. A cell outside it is not "dry", it is
  unknown, and scoring it would hand the hazard map false alarms nobody
  observed.
- **The observed extent is `observedEventA` with notation "Flooded area" or
  "Flood trace"**: the water seen on the image and the marks it left after
  receding. Both are evidence of flooding at that place; the trace share is
  kept as its own column so a reader can drop it. Other notations are left out.
- **Hazard agreement reuses `validate.agreement`** on a 20 m EPSG:3035 grid
  (equal-area, so a cell count is an area), with JRC permanent water dropped
  from the matrix: hit rate = share of the observed extent inside the map,
  false alarm ratio = share of the mapped hazard inside the AOI that stayed
  dry on that date. Residents and buildings are NOT cut by that water mask
  (see `hazard_rows`).
- **Residents are GHS-POP E2020, weighted by the flooded share of each cell**
  (Annex 2 of the challenge). The 30 arc-second count is turned into a density
  per m2 of its own cell, put on the 20 m grid by nearest neighbour and summed
  over flooded cells, so a 1 km cell 30 % under water contributes 30 % of its
  residents, on the assumption that they are spread evenly within the cell. The
  AOI total is also computed exactly from polygon areas as a check
  (`residents_aoi` vs `residents_aoi_grid`).
- **Buildings are GHS-OBAT points inside the observed polygons.** A point is
  one building; its `area` field is the footprint in m2. For delineations
  drawn by semi-automatic radar extraction this is a floor: the polygons stop
  at the buildings (on EMSR518 AOI01 2.7 times as many points lie within
  25 m), so `buildings_within_25m_of_observed` is written beside it. Photo-
  interpreted grading products draw the water through the streets. `epoch` is a 100 m
  majority value, not the building's own construction date, so the epoch
  split describes the neighbourhood.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import validate as V

BUCKET = "datasets_challenge"
BUCKET_ROOT = "working_data"
LIST_URL = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"
EMS_FOLDERS = {"BE": "ems_be", "DE": "ems_de", "NL": "ems_nl"}
OBAT_FILES = {
    iso: f"obat_{iso.lower()}/GHS_OBAT_GPKG_{iso3}_E2020_R2024A_V1_0/"
         f"GHS_OBAT_GPKG_{iso3}_E2020_R2024A_V1_0.gpkg"
    for iso, iso3 in (("BE", "BEL"), ("DE", "DEU"), ("NL", "NLD"))
}
POP_E2020 = ("ghs_pop/GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0/"
             "GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0.tif")

RETURN_PERIODS = (10, 20, 30, 40, 50, 75, 100, 200, 500)
HEADLINE_RETURN_PERIODS = (10, 100, 500)
OBSERVED_NOTATIONS = ("Flooded area", "Flood trace")
FLOOD_TRACE = "Flood trace"
CELL_M2 = V.SCORING_RESOLUTION_M ** 2

USE_LABELS = {0: "outside_builtup", 1: "residential", 2: "non_residential"}
EPOCH_LABELS = {0: "outside_builtup", 1: "before_1980", 2: "1980_1990",
                3: "1990_2000", 4: "2000_2010", 5: "2010_2020"}
# Storeys at about 3 m each: 1-2, 3-4, 5-8, 9 and more. A missing or
# non-positive height is "unknown", never the lowest class.
HEIGHT_BREAKS_M = (6.0, 12.0, 24.0)
HEIGHT_LABELS = ("lt_6m", "6_12m", "12_24m", "ge_24m")
HEIGHT_UNKNOWN = "unknown"
# Sensitivity distance for buildings beside the observed extent. Semi-automatic
# (radar) delineations stop at building walls - water between houses is not
# seen - so a point-in-polygon count is a floor there; the count within this
# distance shows how much of the floor is the method.
NEAR_OBSERVED_M = 25.0
DAMAGE_GRADES = ("Destroyed", "Damaged", "Possibly damaged")

PRODUCT_RE = re.compile(
    r"(?P<emsr>EMSR\d+)_AOI(?P<aoi>\d+)_(?P<type>DEL|GRA)_(?P<kind>PRODUCT|MONIT\d+)"
    r"_r1_(?:RTP01|VECTORS)_v(?P<version>\d+)_vector$")


@dataclass(frozen=True)
class Product:
    """One EMS Rapid Mapping product folder in the challenge bucket.

    Parsed from the folder name rather than from a hand-kept list, because the
    bucket's naming carries a version (`v1`, `v2`, `v3`) that the layer file
    names repeat, and a hand-typed `v1` silently misses AOI15's monitoring pass.
    """

    country: str
    folder: str
    emsr: str
    aoi: str
    type: str
    kind: str
    version: str

    @property
    def product_id(self) -> str:
        """Stable short id, e.g. `EMSR517_AOI15_GRA_MONIT01_v3`."""
        return f"{self.emsr}_AOI{self.aoi}_{self.type}_{self.kind}_v{self.version}"

    def layer_path(self, layer: str) -> str:
        """Bucket-relative path of one shapefile layer of this product."""
        name = f"{self.emsr}_AOI{self.aoi}_{self.type}_{self.kind}_{layer}_r1_v{self.version}.shp"
        return f"{BUCKET_ROOT}/{EMS_FOLDERS[self.country]}/{self.folder}/{name}"


def bucket_objects(prefix: str, *, opener=urllib.request.urlopen) -> list[str]:
    """Every object name under `prefix`, through the anonymous JSON API, all pages.

    `opener` is injectable so the tests never touch the network. The listing is
    paged at 1,000 objects and ems_be alone holds more, so a single request
    would silently drop products.
    """
    names: list[str] = []
    token = None
    while True:
        query = {"prefix": prefix, "fields": "items(name),nextPageToken", "maxResults": "1000"}
        if token:
            query["pageToken"] = token
        with opener(f"{LIST_URL}?{urllib.parse.urlencode(query)}") as response:
            page = json.load(response)
        names += [item["name"] for item in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            return names


def products_from_names(names: list[str]) -> list[Product]:
    """The EMS products present in a bucket listing, sorted, one per folder.

    A folder counts only when its `observedEventA` and `areaOfInterestA`
    shapefiles are both listed: without the AOI there is no way to tell
    "not flooded" from "not mapped".
    """
    found: dict[str, set[str]] = {}
    meta: dict[str, tuple[str, re.Match]] = {}
    for name in names:
        parts = name.split("/")
        if len(parts) < 4 or parts[0] != BUCKET_ROOT:
            continue
        country = next((c for c, f in EMS_FOLDERS.items() if f == parts[1]), None)
        match = PRODUCT_RE.match(parts[2])
        if country is None or match is None:
            continue
        meta[parts[2]] = (country, match)
        found.setdefault(parts[2], set()).add(parts[3])
    products = []
    for folder, (country, m) in meta.items():
        product = Product(country=country, folder=folder, emsr=m["emsr"], aoi=m["aoi"],
                          type=m["type"], kind=m["kind"], version=m["version"])
        needed = {product.layer_path(layer).split("/")[-1]
                  for layer in ("observedEventA", "areaOfInterestA")}
        if needed <= found[folder]:
            products.append(product)
    return sorted(products, key=lambda p: (p.country, p.emsr, p.aoi, p.kind != "PRODUCT", p.kind))


def height_class(height_m) -> np.ndarray:
    """OBAT height in metres to one of `HEIGHT_LABELS`, or `HEIGHT_UNKNOWN`."""
    h = np.asarray(height_m, dtype="float64")
    out = np.array(HEIGHT_LABELS, dtype=object)[np.searchsorted(HEIGHT_BREAKS_M, np.nan_to_num(h), side="right")]
    out[~np.isfinite(h) | (h <= 0)] = HEIGHT_UNKNOWN
    return out


def pop_cell_area_m2(transform, height: int) -> np.ndarray:
    """Ground area of each ROW of a lon/lat grid, in m2, via EPSG:3035.

    A 30 arc-second cell is about 0.93 x 0.59 km at 50 N and shrinks with
    latitude, so a count per cell is only a density once divided by this. The
    corners are projected to EPSG:3035, which is equal-area, so the polygon
    area there is the cell's ground area.
    """
    from pyproj import Transformer

    to_laea = Transformer.from_crs("EPSG:4326", V.SCORING_CRS, always_xy=True)
    left, width_deg = transform.c, transform.a
    tops = transform.f + np.arange(height) * transform.e
    bottoms = tops + transform.e
    xs = np.stack([np.full(height, left), np.full(height, left + width_deg),
                   np.full(height, left + width_deg), np.full(height, left)], axis=1)
    ys = np.stack([tops, tops, bottoms, bottoms], axis=1)
    px, py = to_laea.transform(xs, ys)
    # Shoelace formula on each row's quadrilateral.
    return 0.5 * np.abs(np.sum(px * np.roll(py, -1, axis=1) - np.roll(px, -1, axis=1) * py, axis=1))


def population_density(pop: np.ndarray, transform) -> np.ndarray:
    """Residents per m2 for a lon/lat population window; negatives and NaN to 0."""
    counts = np.nan_to_num(np.asarray(pop, dtype="float64"), nan=0.0)
    counts[counts < 0] = 0.0
    return counts / pop_cell_area_m2(transform, counts.shape[0])[:, None]


def people_in_polygon(pop: np.ndarray, transform, polygon) -> float:
    """Residents inside a lon/lat polygon, each cell weighted by its share inside.

    Exact geometry rather than a grid: every population cell touching the
    polygon is intersected with it and contributes `count x area share`. The
    share is taken in degrees, which inside one 30 arc-second cell differs from
    the ground share by far less than the population model's own error.
    """
    import shapely

    if polygon is None or polygon.is_empty:
        return 0.0
    counts = np.nan_to_num(np.asarray(pop, dtype="float64"), nan=0.0)
    counts[counts < 0] = 0.0
    rows, cols = np.nonzero(counts)
    if rows.size == 0:
        return 0.0
    x0 = transform.c + cols * transform.a
    y0 = transform.f + rows * transform.e
    cells = shapely.box(x0, y0 + transform.e, x0 + transform.a, y0)
    tree = shapely.STRtree(cells)
    hit = tree.query(polygon, predicate="intersects")
    if hit.size == 0:
        return 0.0
    shapely.prepare(polygon)
    share = shapely.area(shapely.intersection(cells[hit], polygon)) / shapely.area(cells[hit])
    return float(np.sum(counts[rows[hit], cols[hit]] * share))


def cell_keys(grid: V.Grid, mask: np.ndarray) -> np.ndarray:
    """Global int64 keys of the true cells of `mask` on `grid`'s 20 m lattice.

    Every product grid is snapped to the same EPSG:3035 lattice (whole 100 m
    blocks from the origin), so a key names one ground cell whatever product
    it came from, and the union over products is `np.unique` on keys: a cell
    two AOIs both mapped is counted once.
    """
    rows, cols = np.nonzero(mask)
    row0 = round(-grid.top / grid.resolution_m)
    col0 = round(grid.left / grid.resolution_m)
    return (row0 + rows.astype("int64")) * 10_000_000 + (col0 + cols.astype("int64"))


def hazard_rows(observed: np.ndarray, scorable: np.ndarray, people: np.ndarray,
                wet_by_rp: dict[int, np.ndarray]) -> list[dict]:
    """One row per return period: agreement inside the AOI and residents outside.

    `observed` is the flooded mask already cut to the AOI, `scorable` the AOI
    minus JRC permanent water, `people` the residents per 20 m cell.

    Two denominators on purpose. The agreement is scored over `scorable` only,
    because every permanent-water cell is wet in every hazard map and would be
    a free hit (on the Ahr the coarse water mask covers 27 % of the observed
    extent). Residents are counted over the whole observed extent, because a
    coarse river mask is not a reason to drop the people beside the river;
    those cells are inside every map, so they never add to the "outside" count.
    The ratios go through `validate.agreement`, so a zero denominator is NaN,
    never 0, and below `validate.MIN_OBSERVED_CELLS` observed cells they are NaN
    too, as in `validate.agreement_by_unit`.
    """
    residents = float(people[observed].sum())
    rows = []
    for rp, wet in wet_by_rp.items():
        a = V.agreement(wet, observed, scorable=scorable)
        thin = a.observed_flood_cells < V.MIN_OBSERVED_CELLS
        outside = float(people[observed & ~wet].sum())
        rows.append({
            "return_period": rp,
            "true_positive": a.true_positive, "false_positive": a.false_positive,
            "false_negative": a.false_negative, "scored_cells": a.scored_cells,
            "scored_observed_km2": a.observed_flood_cells * CELL_M2 / 1e6,
            "modelled_km2_in_aoi": a.modelled_flood_cells * CELL_M2 / 1e6,
            "hit_rate": np.nan if thin or a.hit_rate is None else a.hit_rate,
            "false_alarm_ratio": (np.nan if thin or a.false_alarm_ratio is None
                                  else a.false_alarm_ratio),
            "csi": np.nan if thin or a.iou is None else a.iou,
            "residents_observed": residents,
            "residents_outside_map": outside,
            "share_residents_outside_map": outside / residents if residents else np.nan,
        })
    return rows


def classify_buildings(buildings: pd.DataFrame) -> pd.DataFrame:
    """OBAT rows with `use_class`, `epoch_class` and `height_class` labels added."""
    out = buildings.copy()
    out["use_class"] = out["use"].map(USE_LABELS).fillna("unknown")
    out["epoch_class"] = out["epoch"].map(EPOCH_LABELS).fillna("unknown")
    out["height_class"] = height_class(out["height"])
    return out


def building_breakdown(buildings: pd.DataFrame, *, scope: str) -> pd.DataFrame:
    """Long table: buildings and footprint per (dimension, category) for one scope.

    `buildings` is already restricted to the scope (inside the AOI, or inside
    the observed extent) and classified. Every category of every dimension is
    written, with 0 where none, so a missing row never has to be read as zero.
    """
    rows = []
    for dimension, labels in (("use", list(USE_LABELS.values()) + ["unknown"]),
                              ("epoch", list(EPOCH_LABELS.values()) + ["unknown"]),
                              ("height", list(HEIGHT_LABELS) + [HEIGHT_UNKNOWN])):
        column = f"{dimension}_class"
        counts = buildings.groupby(column).size() if len(buildings) else pd.Series(dtype=int)
        areas = buildings.groupby(column)["area"].sum() if len(buildings) else pd.Series(dtype=float)
        for label in labels:
            rows.append({"scope": scope, "dimension": dimension, "category": label,
                         "buildings": int(counts.get(label, 0)),
                         "footprint_m2": float(areas.get(label, 0.0))})
    return pd.DataFrame(rows)


def damage_breakdown(points: pd.DataFrame) -> pd.DataFrame:
    """GRA building points per (damage grade, object type), inside the observed extent or not.

    The grading is the analysts' own per-building statement inside the AOI,
    so every point counts, not only those inside the flood polygons;
    `in_observed` says which ones are.
    """
    if points.empty:
        return pd.DataFrame(columns=["damage_grade", "obj_type", "in_observed", "buildings"])
    return (points.groupby(["damage_grade", "obj_type", "in_observed"]).size()
            .rename("buildings").reset_index())


def ratio(numerator: float, denominator: float) -> float:
    """`numerator / denominator`, NaN when the denominator is 0 (never 0.0)."""
    return float(numerator) / denominator if denominator else np.nan
