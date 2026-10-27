"""Roads, railways and essential services in the July 2021 water, per EMS product.

`scripts/event_2021.py` counts people and buildings; this adds what the same
EMS products say about infrastructure, from the layers that script leaves in
the bucket:

    roads and railways   transportationL, km by class (motorway ... railway, bridge)
    networks             facilitiesL lines, km (power lines, dams)
    essential services   builtUpA / builtUpP `info` (schools, hospitals, fire
                         stations, stations) and facilitiesA/P (power plants,
                         substations), counted

Each is measured in three scopes, inside the product's AOI only (outside it
nothing was mapped): the whole AOI, inside the observed water (`observedEventA`,
"Flooded area" + "Flood trace", the same extent as every other 2021 figure),
and within 25 m of it, because radar delineations stop at walls and kerbs. A
grading product (GRA) also states a damage grade per feature; those are kept
as the analysts' own statement, every feature in the AOI, as for buildings.

A delineation's transport and facility layers are the reference map of the
AOI, not a damage statement: a road is "in the water" only where its line
crosses the observed polygons. Lengths and counts are taken in EPSG:3035, so a
length is metres on the ground.

Country rows take the union of products, as `event_2021.py` does: lines are
merged per class before measuring, so a road mapped by a first product and its
monitoring pass, or by two overlapping AOIs, is counted once; features are
deduplicated by position and class, the most severe grade winning.

The layers are read once from the bucket into `data/raw/challenge_2021/ems_infra/`.
Writes data/processed/event_2021_infrastructure.parquet and .csv (long format).

Run:

    python scripts/event_2021_infrastructure.py            # fetch what is missing, then measure
    python scripts/event_2021_infrastructure.py --offline  # cache only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from scripts.event_2021 import BASES, CACHE, OUT_DIR, _gpkg, _union, _vsigs, load_products
from src import event2021 as E
from src import validate as V

LAYERS = ("transportationL", "builtUpA", "builtUpP", "facilitiesA", "facilitiesL", "facilitiesP")
KEEP = ["obj_type", "info", "name", "damage_gra"]
#: Grades from most to least severe; the first one met wins in a union.
SEVERITY = E.DAMAGE_GRADES
COLUMNS = ["level", "country", "extent_basis", "product_id", "theme", "category",
           "scope", "damage_grade", "value", "unit"]


def _infra(cache: Path, product: E.Product) -> Path:
    """Cached infrastructure layers of one product."""
    return cache / "ems_infra" / f"{product.product_id}.gpkg"


def layer_manifest(cache: Path, products: list[E.Product], *, offline: bool) -> dict[str, list[str]]:
    """Which of LAYERS each product has, from one bucket listing kept in `layers.json`."""
    manifest = cache / "ems_infra" / "layers.json"
    if not manifest.exists():
        if offline:
            raise SystemExit(f"{manifest} missing and --offline set: run once with network.")
        listed = {n for folder in E.EMS_FOLDERS.values()
                  for n in E.bucket_objects(f"{E.BUCKET_ROOT}/{folder}/")}
        found = {p.product_id: [l for l in LAYERS if p.layer_path(l) in listed] for p in products}
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(found, indent=1))
    return json.loads(manifest.read_text())


def fetch_infra(cache: Path, product: E.Product, layers: list[str]) -> None:
    """The product's infrastructure layers into one GeoPackage, the columns we read only."""
    import pyogrio

    target = _infra(cache, product)
    if target.exists() or not layers:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp.gpkg")
    tmp.unlink(missing_ok=True)
    for layer in layers:
        frame = pyogrio.read_dataframe(_vsigs(product.layer_path(layer)))
        frame = frame[[c for c in KEEP if c in frame] + ["geometry"]]
        pyogrio.write_dataframe(frame, tmp, layer=layer, driver="GPKG")
    tmp.replace(target)


def extent(cache: Path, product: E.Product):
    """(AOI, observed water) of a product in EPSG:3035, by the rules of `event_2021.py`."""
    import geopandas as gpd
    import pyogrio
    import shapely

    gpkg = _gpkg(cache, product)
    aoi = _union(pyogrio.read_dataframe(gpkg, layer="areaOfInterestA").geometry)
    events = pyogrio.read_dataframe(gpkg, layer="observedEventA")
    observed = _union(events.loc[events["notation"].isin(E.OBSERVED_NOTATIONS)].geometry)
    observed = _union([observed.intersection(aoi)]) if observed is not None else None
    out = gpd.GeoSeries([aoi, observed if observed is not None else shapely.Polygon()],
                        crs="EPSG:4326").to_crs(V.SCORING_CRS)
    return out.iloc[0], out.iloc[1]


def read_features(cache: Path, product: E.Product, layers: list[str]):
    """(roads, networks, facilities) of one product in EPSG:3035, classed, with their grade.

    A facility drawn as a line (a power line, a dam) is measured in km with the
    roads, never counted: a count of line segments depends on how the analyst
    split the line, not on the ground.
    """
    import geopandas as gpd
    import pyogrio

    roads, networks, facilities = [], [], []
    for layer in layers:
        f = pyogrio.read_dataframe(_infra(cache, product), layer=layer).to_crs(V.SCORING_CRS)
        grade = f["damage_gra"] if "damage_gra" in f else pd.Series([None] * len(f), index=f.index)
        if layer == "transportationL":
            f["category"] = [E.info_class(i, E.ROAD_CLASSES) for i in f["info"]]
            roads.append(f.assign(grade=grade)[["category", "grade", "geometry"]])
        else:
            f["category"] = [E.info_class(i, E.FACILITY_CLASSES, default=None) for i in f["info"]]
            f = f.assign(grade=grade).dropna(subset=["category"])[["category", "grade", "geometry"]]
            lines = f.geometry.geom_type.isin(["LineString", "MultiLineString"])
            networks.append(f[lines])
            facilities.append(f[~lines])
    empty = gpd.GeoDataFrame({"category": [], "grade": []}, geometry=[], crs=V.SCORING_CRS)
    cat = lambda parts: pd.concat(parts, ignore_index=True) if parts else empty  # noqa: E731
    return cat(roads), cat(networks), cat(facilities)


def line_rows(lines, aoi, observed, theme: str = "roads") -> list[dict]:
    """km of each line class per scope, and per damage grade over the AOI.

    Lines are merged per class first, so a segment drawn twice (two passes,
    two overlapping AOIs) is measured once.
    """
    import shapely

    zones = {"aoi": aoi, "observed": observed,
             "near": observed.buffer(E.NEAR_OBSERVED_M).intersection(aoi)}
    rows = []
    for category, group in lines.groupby("category"):
        line = shapely.union_all(group.geometry.values)
        for scope, zone in zones.items():
            rows.append({"theme": theme, "category": category, "scope": scope,
                         "damage_grade": "all", "value": line.intersection(zone).length / 1000,
                         "unit": "km"})
        seen = None
        for grade in SEVERITY:
            graded = group.loc[group["grade"] == grade]
            if graded.empty:
                continue
            part = shapely.union_all(graded.geometry.values)
            part = part.difference(seen) if seen is not None else part
            seen = part if seen is None else shapely.union_all([seen, part])
            rows.append({"theme": theme, "category": category, "scope": "aoi",
                         "damage_grade": grade, "value": part.intersection(aoi).length / 1000,
                         "unit": "km"})
    return rows


def facility_rows(facilities, aoi, observed) -> list[dict]:
    """Count of each service class per scope, and per damage grade over the AOI.

    A feature counts once per position and class (the most severe grade kept),
    and is in a scope when its geometry touches it: a school whose block the
    water reaches is a school in the water.
    """
    import shapely

    if facilities.empty:
        return []
    f = facilities.copy()
    p = f.geometry.representative_point()
    f["pos"] = list(zip(p.x.round(0), p.y.round(0)))
    f["rank"] = f["grade"].map({g: i for i, g in enumerate(SEVERITY)}).fillna(len(SEVERITY))
    f = f.sort_values("rank", kind="stable").drop_duplicates(["pos", "category"])
    near = observed.buffer(E.NEAR_OBSERVED_M)
    for zone in (aoi, observed, near):
        shapely.prepare(zone)
    f = f[shapely.intersects(aoi, f.geometry.values)]
    flags = {"aoi": np.ones(len(f), dtype=bool),
             "observed": shapely.intersects(observed, f.geometry.values),
             "near": shapely.intersects(near, f.geometry.values)}
    rows = []
    for category in sorted(f["category"].unique()):
        mine = (f["category"] == category).to_numpy()
        for scope, flag in flags.items():
            rows.append({"theme": "facilities", "category": category, "scope": scope,
                         "damage_grade": "all", "value": int((mine & flag).sum()), "unit": "count"})
        for grade in SEVERITY:
            n = int((mine & (f["grade"] == grade).to_numpy()).sum())
            if n:
                rows.append({"theme": "facilities", "category": category, "scope": "aoi",
                             "damage_grade": grade, "value": n, "unit": "count"})
    return rows


def measure(roads, networks, facilities, aoi, observed) -> list[dict]:
    """Every infrastructure row for one extent: one product, or a country union."""
    return (line_rows(roads, aoi, observed) + line_rows(networks, aoi, observed, "networks")
            + facility_rows(facilities, aoi, observed))


def _lead(level: str, country: str, basis: str, product_id: str) -> dict:
    return {"level": level, "country": country, "extent_basis": basis, "product_id": product_id}


def main(argv: list[str] | None = None) -> int:
    """Fetch the missing layers (unless --offline), measure every product and country, write."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="use the cache only")
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    products, _ = load_products(args.cache, offline=args.offline)
    layers = layer_manifest(args.cache, products, offline=args.offline)
    if not args.offline:
        for p in products:
            fetch_infra(args.cache, p, layers.get(p.product_id, []))

    rows, kept = [], []
    for p in products:
        aoi, observed = extent(args.cache, p)
        roads, networks, facilities = read_features(args.cache, p, layers.get(p.product_id, []))
        kept.append((p, aoi, observed, roads, networks, facilities))
        rows += [{**_lead("product", p.country, "single_product", p.product_id), **r}
                 for r in measure(roads, networks, facilities, aoi, observed)]
        print(f"{p.product_id}: {len(roads):,} road segments, {len(facilities):,} services", flush=True)

    import shapely

    for country in sorted({p.country for p, *_ in kept}):
        for basis, kinds in BASES.items():
            chosen = [k for k in kept if k[0].country == country and (kinds is None or k[0].kind in kinds)]
            if not chosen:
                continue
            aoi = shapely.union_all([k[1] for k in chosen])
            observed = shapely.union_all([k[2] for k in chosen])
            frames = [pd.concat([k[i] for k in chosen], ignore_index=True) for i in (3, 4, 5)]
            rows += [{**_lead("country", country, basis, ""), **r}
                     for r in measure(*frames, aoi, observed)]

    table = pd.DataFrame(rows, columns=COLUMNS)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "event_2021_infrastructure.parquet"
    table.to_parquet(path, index=False)
    table.to_csv(path.with_suffix(".csv"), index=False)
    print(f"wrote {path} ({len(table)} rows) in {time.perf_counter() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
