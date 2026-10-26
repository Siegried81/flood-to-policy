"""Fetch the C3S ECDE heavy-precipitation and flood-recurrence indicators.

Dataset `sis-ecde-aggregated-climate-indicators` on the Climate Data Store
(`c3s_ecde_climate_indicators` in config/sources.yaml). Two requests, each one
the finest the catalogue accepts:

* `precipitation` - maximum consecutive five-day precipitation, extreme
  precipitation total and frequency of extreme precipitation, yearly, product
  `gwl_relative_change_quantiles`, at the finest regional layer the
  constraints accept. NUTS3 is tried first and NUTS2 is the fallback; on
  2026-10-24 the constraints and the costing endpoint accept only NUTS2 for
  these three variables.
* `flood_recurrence` - the 5 and 50-year return values of annual maximum
  discharge (the two the kit's discharge members cover), for BOTH E-HYPE and
  VIC-WUR, same product. Gridded: on 2026-10-24 this variable has no regional
  layer at all.

**Every request is checked against the live public constraints file before it
is sent** (`--check` does only that, with no key). The form shows every option
any variable has - NUTS3 is listed because snowfall has it - so a request built
by reading the form alone is rejected with "Request has not produced a valid
combination of values" and nothing else.

**Credentials.** `CDSAPI_URL` / `CDSAPI_KEY` from the environment or the repo's
`.env`, else `~/.cdsapirc`. The key is never printed, logged or cached. The
CC-BY licence must be accepted once on the dataset page; a refusal for that
reason is reported as such.

Run:

    python scripts/fetch_c3s_ecde.py --check            # validate, fetch nothing
    python scripts/fetch_c3s_ecde.py                    # both requests
    python scripts/fetch_c3s_ecde.py --what precipitation
"""

from __future__ import annotations

import argparse
import itertools
import os
import shutil
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pluvial import ECDE_DIR, PRECIP_VARIABLES  # noqa: E402

DATASET = "sis-ecde-aggregated-climate-indicators"
CATALOGUE = f"https://cds.climate.copernicus.eu/api/catalogue/v1/collections/{DATASET}"
DATASET_PAGE = f"https://cds.climate.copernicus.eu/datasets/{DATASET}?tab=download"
DEFAULT_URL = "https://cds.climate.copernicus.eu/api"

#: Finest first. Read off the form's `regional_layer` widget, 2026-10-24.
REGIONAL_LAYERS = ("nuts_level_3", "nuts_level_2")
#: The return periods the kit's discharge members already cover.
FLOOD_RETURN_PERIODS = ("1_in_5_year", "1_in_50_year")
HYDROLOGICAL_MODELS = ("e_hype", "vic_wur")


def precipitation_request(layer: str) -> dict:
    """The heavy-precipitation request at one regional layer."""
    return {
        "variable": sorted(PRECIP_VARIABLES),
        "origin": "projections",
        "product": ["gwl_relative_change_quantiles"],
        "spatial_aggregation": "regional_layer",
        "regional_layer": [layer],
        "temporal_aggregation": ["yearly"],
        "version": "v2_0",
    }


def flood_request(return_period: str) -> dict:
    """The flood-recurrence request for one return period and both models.

    One return period per request so each file is named after it and the
    reader never has to guess which return value a field holds.
    """
    return {
        "variable": ["flood_recurrence"],
        "origin": "projections",
        "hydrological_model": list(HYDROLOGICAL_MODELS),
        "other_parameters": [return_period],
        "product": ["gwl_relative_change_quantiles"],
        "spatial_aggregation": "gridded",
        "temporal_aggregation": ["yearly"],
        "version": "v2_0",
    }


def load_constraints(session=requests) -> list[dict]:
    """The live constraints file, found through the public catalogue entry."""
    collection = session.get(CATALOGUE, timeout=60)
    collection.raise_for_status()
    link = next(l["href"] for l in collection.json()["links"] if l.get("rel") == "constraints")
    response = session.get(link, timeout=60)
    response.raise_for_status()
    return response.json()


def is_valid(request: dict, constraints: list[dict]) -> bool:
    """Whether every combination of the request's values is allowed.

    A constraints entry allows the Cartesian product of its lists; a request is
    valid when each of its combinations falls inside at least one entry. Keys
    no entry mentions (none here) are not constrained.
    """
    constrained = set().union(*(c.keys() for c in constraints)) if constraints else set()
    keys = [k for k in request if k in constrained]
    lists = [request[k] if isinstance(request[k], list) else [request[k]] for k in keys]
    for combination in itertools.product(*lists):
        if not any(
            all(k in entry and v in entry[k] for k, v in zip(keys, combination))
            for entry in constraints
        ):
            return False
    return True


def plan(constraints: list[dict], what: tuple[str, ...]) -> list[tuple[str, dict]]:
    """`(file stem, request)` for every request to send, finest valid layer first."""
    jobs = []
    if "precipitation" in what:
        layer = next((l for l in REGIONAL_LAYERS if is_valid(precipitation_request(l), constraints)), None)
        if layer is None:
            raise SystemExit("No regional layer is valid for the precipitation indicators any more; "
                             "read the constraints file again.")
        jobs.append((f"ecde_precipitation_{layer}", precipitation_request(layer)))
    if "flood_recurrence" in what:
        for rp in FLOOD_RETURN_PERIODS:
            request = flood_request(rp)
            if not is_valid(request, constraints):
                raise SystemExit(f"flood_recurrence {rp} for {HYDROLOGICAL_MODELS} is no longer valid.")
            jobs.append((f"ecde_flood_recurrence_{rp}", request))
    return jobs


def credentials() -> dict | None:
    """`{url, key}` from the environment or `.env`, `{}` for ~/.cdsapirc, None if neither.

    Returns the key only to hand it to the client; it is never printed.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    if os.environ.get("CDSAPI_KEY"):
        return {"url": os.environ.get("CDSAPI_URL", DEFAULT_URL), "key": os.environ["CDSAPI_KEY"]}
    if (Path.home() / ".cdsapirc").exists():
        return {}
    return None


def _unpack(download: Path, out_dir: Path, stem: str) -> list[str]:
    """Move the NetCDF(s) of one download into `out_dir`, named after `stem`."""
    with open(download, "rb") as fh:
        magic = fh.read(4)
    if magic[:2] == b"PK":
        staging = out_dir / f".staging_{stem}"
        shutil.rmtree(staging, ignore_errors=True)
        try:
            with zipfile.ZipFile(download) as zf:
                zf.extractall(staging)
            members = sorted(staging.rglob("*.nc"))
            if not members:
                raise SystemExit(f"{download.name} holds no .nc file")
            names = []
            for member in members:
                target = out_dir / (f"{stem}.nc" if len(members) == 1 else f"{stem}__{member.name}")
                shutil.move(str(member), target)
                names.append(target.name)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            download.unlink(missing_ok=True)
        return names
    if magic[:3] == b"CDF" or magic == b"\x89HDF":
        target = out_dir / f"{stem}.nc"
        download.replace(target)
        return [target.name]
    raise SystemExit(f"{download.name} is neither a ZIP nor a NetCDF (starts {magic!r})")


def fetch(client, jobs, out_dir: Path = ECDE_DIR) -> list[str]:
    """Retrieve every job into `out_dir`; a licence refusal says what to click."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for stem, request in jobs:
        download = out_dir / f"{stem}.download"
        try:
            client.retrieve(DATASET, request, str(download))
        except Exception as exc:  # cdsapi raises bare HTTP errors
            text = str(exc).lower()
            if "licen" in text or "terms" in text:
                raise SystemExit(f"The CDS refused {stem}: the dataset licence is not accepted. "
                                 f"Accept the CC-BY licence once at {DATASET_PAGE}") from None
            raise
        written += _unpack(download, out_dir, stem)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--what", action="append", choices=("precipitation", "flood_recurrence"))
    parser.add_argument("--check", action="store_true",
                        help="Validate the requests against the live constraints and exit. No key needed.")
    args = parser.parse_args()
    what = tuple(args.what or ("precipitation", "flood_recurrence"))

    jobs = plan(load_constraints(), what)
    for stem, request in jobs:
        print(f"{stem}: {request}")
    if args.check:
        return 0
    found = credentials()
    if found is None:
        raise SystemExit("No CDS key: set CDSAPI_URL and CDSAPI_KEY in .env or the environment, "
                         "or write ~/.cdsapirc (https://cds.climate.copernicus.eu/how-to-api).")
    import cdsapi

    client = cdsapi.Client(**found) if found else cdsapi.Client()
    for name in fetch(client, jobs):
        print(f"  -> {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
