"""Fetch the EFAS reanalysis for July 2021 over the Meuse/Vesdre/Ahr box, and the river map.

Two requests to the CEMS Early Warning Data Store (EWDS), dataset
`efas-historical`, both read by `src/efas.py`:

1. **River discharge, 1-31 July 2021**, every 6-hourly step, system
   `version_5_0`, box N52 W3 S49 E8, NetCDF. Cost measured on the costing
   endpoint 2026-10-24: 124 fields of a 1,500 limit (31 days x 4 steps).
2. **The static `upstream_area` field**, which is what tells a river cell from a
   hillslope cell (every land cell carries a return-level threshold). Cost 1.
   It is requested for the whole domain because the form says "area
   sub-selection is not yet available for the time-invariant fields"; that is
   one 54 MB field.

**The request is built from the live form, not from the how-to page.** Every
key and value below was read off `form.json` and `constraints.json` linked from
https://ewds.climate.copernicus.eu/api/catalogue/v1/collections/efas-historical
on 2026-10-24: `hyear`/`hmonth`/`hday`, `time` in `HH:MM`, `model_levels` set
to `surface_level`, `area` as [N, W, S, E]. The page's own example is rejected
by the costing endpoint.

**Credentials.** `EWDS_API_KEY` from `.env` (loaded by `src/__init__.py`) or the
shell: the personal access token from your profile on
https://ewds.climate.copernicus.eu. The CEMS-FLOODS licence must be accepted
once on the dataset's download page, or every request is refused. The script
never prints, logs or writes the key, and scrubs it from any error it relays.

Run:

    python scripts/fetch_efas_july2021.py --dry-run   # print both requests, fetch nothing
    python scripts/fetch_efas_july2021.py             # fetch what is missing
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import efas  # noqa: E402  (also loads .env through src/__init__.py)

URL = "https://ewds.climate.copernicus.eu/api"
DATASET = "efas-historical"
DATASET_PAGE = "https://ewds.climate.copernicus.eu/datasets/efas-historical?tab=download"
OUT_DIR = efas.JULY_DIR

#: [N, W, S, E], the box of `efas_historical_july_2021` in config/sources.yaml.
AREA = [52, 3, 49, 8]


def discharge_request() -> dict:
    """The EWDS request for every 6-hourly discharge field of July 2021 in the box."""
    return {
        "system_version": ["version_5_0"],
        "variable": ["river_discharge_in_the_last_6_hours"],
        "model_levels": "surface_level",
        "hyear": ["2021"],
        "hmonth": ["07"],
        "hday": [f"{d:02d}" for d in range(1, 32)],
        "time": ["00:00", "06:00", "12:00", "18:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": AREA,
    }


def upstream_request() -> dict:
    """The EWDS request for the static upstream-area field, whole domain."""
    return {
        "system_version": ["version_5_0"],
        "variable": ["upstream_area"],
        "model_levels": "surface_level",
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


REQUESTS = {
    efas.DISCHARGE_FILE: discharge_request,
    efas.UPSTREAM_FILE: upstream_request,
}


def api_key() -> str:
    """The EWDS key from the environment, or a SystemExit saying how to get one."""
    key = os.environ.get("EWDS_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "EWDS_API_KEY is not set. Log in at https://ewds.climate.copernicus.eu, "
            "copy the API token from your profile page into .env as "
            "EWDS_API_KEY=..., and accept the CEMS-FLOODS licence on "
            f"{DATASET_PAGE}."
        )
    return key


def make_client(key: str):
    """A cdsapi client pointed at the EWDS, not at the CDS default."""
    try:
        import cdsapi
    except ImportError:
        raise SystemExit("cdsapi is not installed: pip install -r requirements.txt")
    return cdsapi.Client(url=URL, key=key)


def _is_netcdf(path: Path) -> bool:
    """True for a NetCDF-3 (`CDF`) or NetCDF-4/HDF5 (`\\x89HDF`) file."""
    with open(path, "rb") as fh:
        head = fh.read(8)
    return head.startswith(b"CDF") or head.startswith(b"\x89HDF")


def retrieve(client, name: str, request: dict, out_dir: Path, key: str = "") -> Path:
    """Run one request into `out_dir/name`, through a `.part` file, and prove it is NetCDF.

    "unarchived" still comes back zipped when the conversion yields several
    files, so a ZIP is opened and its single .nc taken; more than one is an
    error rather than a guess. A licence refusal becomes a message that says
    where to accept it, and the key is scrubbed from anything relayed.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / name
    partial = out_dir / (name + ".part")
    try:
        client.retrieve(DATASET, request, str(partial))
    except Exception as exc:  # cdsapi raises plain HTTP/requests errors
        message = str(exc).replace(key, "***") if key else str(exc)
        if "licen" in message.lower():
            raise SystemExit(
                f"EWDS refused the request for a licence: accept the CEMS-FLOODS "
                f"licence on {DATASET_PAGE}, then rerun. Server said: {message}"
            )
        raise SystemExit(f"EWDS request for {name} failed: {message}")
    if zipfile.is_zipfile(partial):
        with zipfile.ZipFile(partial) as zf:
            members = [m for m in zf.namelist() if m.endswith(".nc")]
            if len(members) != 1:
                raise SystemExit(f"{name}: the archive holds {members}, expected one .nc.")
            with zf.open(members[0]) as src, open(target.with_suffix(".tmp"), "wb") as dst:
                shutil.copyfileobj(src, dst)
        partial.unlink()
        target.with_suffix(".tmp").replace(partial)
    if not _is_netcdf(partial):
        raise SystemExit(f"{partial.name} is not a NetCDF file; left in place for a look.")
    partial.replace(target)
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="Print the requests, fetch nothing.")
    parser.add_argument("--force", action="store_true", help="Refetch files already on disk.")
    args = parser.parse_args(argv)

    plan = [n for n in REQUESTS if args.force or not (OUT_DIR / n).exists()]
    print(f"dataset: {DATASET} at {URL}")
    for name in REQUESTS:
        state = "to fetch" if name in plan else "on disk"
        print(f"  {name} ({state})")
        if args.dry_run:
            print("    " + json.dumps(REQUESTS[name]()))
    if args.dry_run or not plan:
        print("--dry-run: nothing fetched." if args.dry_run else "Nothing missing.")
        return 0

    key = api_key()
    client = make_client(key)
    for name in plan:
        print(f"requesting {name}; the EWDS queues requests, minutes is normal")
        path = retrieve(client, name, REQUESTS[name](), OUT_DIR, key)
        print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size:,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
