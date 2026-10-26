"""Write the July 2021 four-day event rainfall per NUTS3 region, from EMO-1.

Reads data/raw/download/emo1_precipitation_2021.nc (`emo1_precipitation_2021`
in config/sources.yaml) over the NUTS3 regions of Belgium, Germany, the
Netherlands, Luxembourg and France whose bounds meet the EMO-1 grid - so the
French outermost regions drop out - and writes
data/processed/rainfall_jul2021.parquet, one row per region. Only the event
window and the five countries' bounding box are read, never the whole cube.

A separate file on purpose: context.parquet is not touched and no
build_context run is needed (docs/decisions.md, 2026-10-25). The logic is in
`src/rainfall.py`; this script only wires it to disk and the terminal.

Run:

    python scripts/rainfall_jul2021.py
    python scripts/rainfall_jul2021.py --start 2021-07-14 --end 2021-07-15
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402

from src import rainfall  # noqa: E402
from src.efas import CELL_DEG  # noqa: E402

COUNTRIES = ("BE", "DE", "NL", "LU", "FR")
REGIONS = ROOT / "data" / "processed" / "regions.geojson"


def _grid_bounds(nc_path: Path) -> tuple[float, float, float, float]:
    """(west, south, east, north) of the whole EMO-1 grid, from its coordinates only."""
    import xarray as xr

    with xr.open_dataset(nc_path) as ds:
        lat, lon = ds["lat"].values, ds["lon"].values
    half = CELL_DEG / 2
    return lon.min() - half, lat.min() - half, lon.max() + half, lat.max() + half


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nc", type=Path, default=rainfall.EMO1_FILE)
    parser.add_argument("--regions", type=Path, default=REGIONS)
    parser.add_argument("--start", default=rainfall.EVENT_START)
    parser.add_argument("--end", default=rainfall.EVENT_END)
    parser.add_argument("--out", type=Path, default=rainfall.OUT_FILE)
    args = parser.parse_args(argv)

    for path in (args.nc, args.regions):
        if not path.exists():
            print(f"missing {path}; fetch emo1_precipitation_2021 / run "
                  "scripts/build_geometry.py", file=sys.stderr)
            return 1

    regions = gpd.read_file(args.regions)
    regions = regions[regions["nuts_id"].str[:2].isin(COUNTRIES)]
    west, south, east, north = _grid_bounds(args.nc)
    b = regions.to_crs("EPSG:4326").geometry.bounds
    on_grid = ((b["maxx"] >= west) & (b["minx"] <= east)
               & (b["maxy"] >= south) & (b["miny"] <= north))
    regions = regions[on_grid.to_numpy()]
    minx, miny, maxx, maxy = regions.to_crs("EPSG:4326").total_bounds
    bbox = (minx - CELL_DEG, miny - CELL_DEG, maxx + CELL_DEG, maxy + CELL_DEG)

    t0 = time.perf_counter()
    total = rainfall.event_total(args.nc, args.start, args.end, bbox=bbox)
    t1 = time.perf_counter()
    table = rainfall.zonal_stats(total, regions)
    t2 = time.perf_counter()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out, index=False)

    measured = int((table["cells"] > 0).sum())
    print(f"{total.attrs['days']} days ending {args.start}..{args.end} 06:00, "
          f"grid window {total.sizes['lat']} x {total.sizes['lon']} "
          f"(read {t1 - t0:.1f} s, zonal {t2 - t1:.1f} s); "
          f"{len(table)} regions, {measured} with cells.")
    top = table.sort_values(f"{rainfall.PREFIX}_max_mm", ascending=False).head(10)
    print(top.to_string(index=False, float_format=lambda v: f"{v:.1f}"))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
