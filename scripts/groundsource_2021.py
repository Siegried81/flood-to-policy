"""Groundsource news-reported floods of July 2021 against the JRC 1-in-100 map.

An independent corroboration of the EMS finding in `scripts/event_2021.py`
(many residents the water reached lived outside the JRC 1-in-100-year map).
Groundsource (Google Research 2026, CC BY 4.0, doi:10.5281/zenodo.18647053) is
2.6 million flood events that Gemini extracted from news reports and mapped to
place polygons. It is model-extracted, not observed: the authors report 60 % of
events right in both place and date, 82 % right to the district or within a
day. A count from it corroborates; it is never a headline on its own.

What the file holds, and what this script derives because the file lacks it:

    uuid, area_km2, geometry (WKB polygons, WGS 84), start_date, end_date
    (ISO strings). Rows are sorted by start_date. There is NO country code
    and NO place name, so both come from the GISCO LAU 2024 municipality that
    contains the polygon's representative point (a point guaranteed inside
    the polygon, unlike the centroid of a crescent or a multipolygon).

The rules, and why each is the one that does not flatter the finding:

**Date.** An event is kept when its own `start_date` falls in 12-20 July 2021,
both ends included. Events that started earlier and were still running in the
window are counted on the side (`overlaps_only`) and left out, so a long
June-to-August entry cannot pad the July count.

**Wet or dry.** The JRC RP100 depth raster (EPSG:4326, 3 arc seconds, about
90 m; dry cells are nodata) is read in a window around each polygon only. A
cell is wet when its depth is strictly above 0 m, through
`validate.modelled_flood_mask`. A cell belongs to the polygon when the polygon
TOUCHES it (`all_touched=True`), not only when it covers the cell centre. The
event is `rp100_dry` when not a single such cell is wet: the map expects no
water anywhere in the reported place. That is deliberately strict: the
permanent rivers are patched into the JRC depth, so a town that merely borders
its river counts as "the map expects water here", and a district-sized polygon
almost always does. A dry verdict therefore says more than a wet one, and the
share is a floor for "reported where the map expects nothing".

**Polygon size.** Groundsource polygons run from a street to a 5,000 km²
region, and a large polygon cannot be dry by the rule above. Each event gets a
size class from the dataset's own `area_km2` (`SIZE_CLASSES`), the summary
reports their distribution, and the dry share is reported again for "town
scale or finer" (up to 100 km², about a Belgian or German municipality).

**EMS areas of interest.** The union of `areaOfInterestA` over every cached
Copernicus EMS product of July 2021 (data/raw/challenge_2021/ems/*.gpkg:
EMSR517 Germany, EMSR518 Belgium, EMSR520 Netherlands). An event is
`in_ems_aoi` when its polygon intersects that union at all; `outside_ems_aoi`
means EMS never mapped any part of the reported place. Only the cached
products count, so "outside" is outside what this repo holds of EMS.

Writes data/processed/groundsource_2021.parquet (GeoParquet, with polygons)
and .csv (no polygons, representative point as lon/lat), and prints a summary
per country.

Run:

    python scripts/groundsource_2021.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import pyogrio  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from rasterio.features import geometry_mask  # noqa: E402
from rasterio.windows import Window  # noqa: E402

from src import validate as V  # noqa: E402

RAW = ROOT / "data" / "raw" / "download"
GROUNDSOURCE = RAW / "groundsource_flood_events.parquet"
RP100 = RAW / "jrc_flood_hazard" / "Europe_RP100_filled_depth.tif"
LAU = RAW / "gisco_lau.zip"
LAU_LAYER = "LAU_RG_01M_2024_3035.shp"
EMS_DIR = ROOT / "data" / "raw" / "challenge_2021" / "ems"
OUT = ROOT / "data" / "processed" / "groundsource_2021"

SOURCE_ID = "groundsource_flood_events"
COUNTRIES = ("BE", "DE", "NL")
WINDOW = ("2021-07-12", "2021-07-20")
# Lon/lat box around BE, DE and NL: a cheap prefilter before the LAU join.
BBOX = (2.5, 47.2, 15.1, 55.1)
# Upper bound in km² (inclusive) and label. 100 km² is about one municipality.
SIZE_CLASSES = ((1.0, "site <=1 km2"), (100.0, "town <=100 km2"),
                (1000.0, "district <=1000 km2"), (np.inf, "region >1000 km2"))
TOWN_SCALE_KM2 = 100.0


def date_rule(start: pd.Series, end: pd.Series, lo: str = WINDOW[0],
              hi: str = WINDOW[1]) -> pd.Series:
    """'in_window' when the event starts in [lo, hi], 'overlaps_only' when it
    started earlier but was still running at `lo`, else 'outside'.

    ISO date strings compare correctly as text, so no parsing is needed; the
    first ten characters are taken in case a time part is ever appended.
    """
    s, e = start.astype(str).str[:10], end.astype(str).str[:10]
    out = pd.Series("outside", index=start.index, dtype=object)
    out[(s < lo) & (e >= lo)] = "overlaps_only"
    out[(s >= lo) & (s <= hi)] = "in_window"
    return out


def size_class(area_km2: pd.Series) -> pd.Series:
    """The `SIZE_CLASSES` label for each area, upper bounds inclusive."""
    bounds = [0.0] + [b for b, _ in SIZE_CLASSES]
    return pd.cut(area_km2, bounds, labels=[name for _, name in SIZE_CLASSES],
                  include_lowest=True).astype(str)


def read_events(path: Path = GROUNDSOURCE, lo: str = "2021-06-01",
                hi: str = WINDOW[1], bbox=BBOX) -> gpd.GeoDataFrame:
    """Events starting in [lo, hi] whose polygon meets `bbox`, as WGS 84 polygons.

    The date filter is pushed down to the parquet reader, so only the matching
    rows of one row group are decoded instead of 2.6 million polygons. `lo` is
    earlier than the window so `date_rule` can count the events that overlap
    it without starting in it.
    """
    table = pq.read_table(path, columns=["uuid", "area_km2", "geometry", "start_date", "end_date"],
                          filters=[("start_date", ">=", lo), ("start_date", "<=", hi)])
    df = table.to_pandas()
    geom = shapely.from_wkb(df.pop("geometry").to_numpy())
    events = gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")
    return events[events.intersects(shapely.box(*bbox))].reset_index(drop=True)


def read_lau(path: Path = LAU, countries=COUNTRIES) -> gpd.GeoDataFrame:
    """GISCO LAU 2024 municipalities of `countries`, in WGS 84."""
    codes = ", ".join(f"'{c}'" for c in countries)
    lau = pyogrio.read_dataframe(f"/vsizip/{path.as_posix()}/{LAU_LAYER}",
                                 columns=["GISCO_ID", "CNTR_CODE", "LAU_NAME"],
                                 where=f"CNTR_CODE IN ({codes})")
    return lau.to_crs("EPSG:4326")


def assign_place(events: gpd.GeoDataFrame, lau: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Country and municipality of the LAU holding each polygon's representative point.

    Events whose point lies in no LAU of `lau` (another country, the sea) get
    no country and are dropped by the caller.
    """
    pts = gpd.GeoDataFrame({"_i": np.arange(len(events))},
                           geometry=events.geometry.representative_point(), crs=events.crs)
    hit = gpd.sjoin(pts, lau, how="left", predicate="within").drop_duplicates("_i").sort_values("_i")
    out = events.copy()
    out["country"] = hit["CNTR_CODE"].to_numpy()
    out["lau_id"] = hit["GISCO_ID"].to_numpy()
    out["lau_name"] = hit["LAU_NAME"].to_numpy()
    out["lon"], out["lat"] = pts.geometry.x.to_numpy(), pts.geometry.y.to_numpy()
    return out


def rp100_cells(geom, src) -> tuple[int, int]:
    """(cells the polygon touches, of which wet in the RP100 map), from one window.

    The window is the polygon's bounds snapped outward to whole cells, read
    `boundless` so a polygon on the raster edge reads nodata rather than
    failing. `geom` must be in the raster's CRS, a north-up grid like the JRC one.
    """
    minx, miny, maxx, maxy = geom.bounds
    t = src.transform
    c0, c1 = int(np.floor((minx - t.c) / t.a)), int(np.ceil((maxx - t.c) / t.a))
    r0, r1 = int(np.floor((maxy - t.f) / t.e)), int(np.ceil((miny - t.f) / t.e))
    c1, r1 = max(c1, c0 + 1), max(r1, r0 + 1)
    win = Window(c0, r0, c1 - c0, r1 - r0)
    depth = src.read(1, window=win, boundless=True, fill_value=src.nodata)
    inside = geometry_mask([geom], out_shape=depth.shape, transform=src.window_transform(win),
                           all_touched=True, invert=True)
    wet = V.modelled_flood_mask(depth, min_depth_m=0.0, nodata_m=src.nodata) & inside
    return int(inside.sum()), int(wet.sum())


def add_rp100(events: gpd.GeoDataFrame, raster: Path = RP100) -> gpd.GeoDataFrame:
    """`rp100_cells`, `rp100_wet_cells` and `rp100_dry` for every event."""
    out = events.copy()
    with rasterio.open(raster) as src:
        geoms = out.geometry.to_crs(src.crs) if out.crs != src.crs else out.geometry
        counts = [rp100_cells(g, src) for g in geoms]
    out["rp100_cells"] = [c for c, _ in counts]
    out["rp100_wet_cells"] = [w for _, w in counts]
    out["rp100_dry"] = out["rp100_wet_cells"] == 0
    return out


def read_aoi(ems_dir: Path = EMS_DIR):
    """Union of `areaOfInterestA` over every cached EMS GeoPackage, in WGS 84."""
    parts = [pyogrio.read_dataframe(p, layer="areaOfInterestA").to_crs("EPSG:4326").geometry
             for p in sorted(ems_dir.glob("*.gpkg"))]
    if not parts:
        raise FileNotFoundError(f"no EMS GeoPackage under {ems_dir}")
    return shapely.union_all(pd.concat(parts).to_numpy())


def add_ems_flag(events: gpd.GeoDataFrame, aoi) -> gpd.GeoDataFrame:
    """`in_ems_aoi` (polygon intersects the AOI union) and its complement."""
    out = events.copy()
    out["in_ems_aoi"] = out.geometry.intersects(aoi)
    out["outside_ems_aoi"] = ~out["in_ems_aoi"]
    return out


def summarise(events: gpd.GeoDataFrame) -> pd.DataFrame:
    """One row per country plus a total: counts, dry shares and size classes."""
    def row(d: pd.DataFrame) -> dict:
        small = d[d["area_km2"] <= TOWN_SCALE_KM2]
        r = {
            "events": len(d),
            # Several articles can map to one place: the same polygon, many rows.
            "distinct_polygons": d.geometry.to_wkb().nunique(),
            "rp100_dry": int(d["rp100_dry"].sum()),
            "rp100_dry_share": d["rp100_dry"].mean() if len(d) else np.nan,
            "town_scale_events": len(small),
            "town_scale_rp100_dry": int(small["rp100_dry"].sum()),
            "town_scale_dry_share": small["rp100_dry"].mean() if len(small) else np.nan,
            "in_ems_aoi": int(d["in_ems_aoi"].sum()),
            "outside_ems_aoi": int(d["outside_ems_aoi"].sum()),
            "dry_and_outside_aoi": int((d["rp100_dry"] & d["outside_ems_aoi"]).sum()),
            "area_km2_median": d["area_km2"].median(),
        }
        for _, name in SIZE_CLASSES:
            r[name] = int((d["size_class"] == name).sum())
        return r

    rows = {c: row(d) for c, d in events.groupby("country")}
    rows["total"] = row(events)
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("country").reset_index()


def ensure_groundsource(path: Path = GROUNDSOURCE) -> Path:
    """The parquet on disk, fetched through `src.fetch` if it is missing."""
    if path.exists():
        return path
    from src.fetch import fetch_source
    res = fetch_source(SOURCE_ID)
    if res.error or not res.path:
        raise SystemExit(f"{SOURCE_ID}: {res.error or 'not fetched'}")
    return Path(res.path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT, help="Output path without suffix.")
    args = parser.parse_args(argv)

    events = read_events(ensure_groundsource())
    events["date_rule"] = date_rule(events["start_date"], events["end_date"])
    events = assign_place(events, read_lau())
    events = events[events["country"].isin(COUNTRIES)]
    overlaps = events[events["date_rule"] == "overlaps_only"]
    events = events[events["date_rule"] == "in_window"].reset_index(drop=True)
    events["size_class"] = size_class(events["area_km2"])
    events = add_ems_flag(add_rp100(events), read_aoi())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(args.out.with_suffix(".parquet"))
    pd.DataFrame(events.drop(columns="geometry")).to_csv(args.out.with_suffix(".csv"), index=False)

    table = summarise(events)
    print(f"Groundsource events in {', '.join(COUNTRIES)} starting {WINDOW[0]}..{WINDOW[1]}: "
          f"{len(events)} ({len(overlaps)} more started earlier and overlap the window; "
          "left out). Model-extracted from news: corroboration only.")
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(table.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(f"-> {args.out.with_suffix('.parquet')} and .csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
