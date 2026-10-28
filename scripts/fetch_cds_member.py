"""Fetch CDS ensemble members, and prove each one is the one asked for.

**Why this exists.** The dataset offers eight climate simulations (a GCM, a
regional model and a realisation each) routed through two gridded hydrological
models, so sixteen members per period under one emissions pathway. Two were
fetched by hand - EC-EARTH r12i1p1 / CCLM4-8-17 through E-HYPEgrid and VIC-WUR -
and on those alone every regional figure is two model chains' opinion of one
world. `--all-missing` requests the other fourteen per period, one request each, and a
request that lives in the repo is reproducible where a form filled in on a
Tuesday is not.

**Credentials.** The CDS needs an API key: register at
<https://cds.climate.copernicus.eu>, accept the dataset's licence on its download
page, then put the key in `~/.cdsapirc` or the `CDSAPI_KEY` environment variable
(with `CDSAPI_URL=https://cds.climate.copernicus.eu/api`). The script checks that
one of the two exists before it builds a client, says which is missing, and
never reads, caches or prints the key itself.

**The cost cap is a PRODUCT, not a sum.** The form refuses a request whose
selections multiply past 1,000. So this script requests ONE period, ONE
hydrological model and ONE simulation per call, which is also what makes the
result checkable: every file that comes back must describe exactly what was
asked for.

**It verifies rather than trusts.** The CDS returns a ZIP whose member filenames
carry the whole request, and `src/climate.py::describe` already parses that
grammar. Every extracted file is parsed and compared field by field against the
request - hydrological model, period, realisation, GCM and regional model - and
a mismatch is an error, because the failure that matters is not an empty
download, it is a download of the *wrong member* landing in the directory the
ensemble is built from, where it would silently become a second opinion from the
same world.

Run:

    python scripts/fetch_cds_member.py --dry-run --all-missing   # list, fetch nothing
    python scripts/fetch_cds_member.py --all-missing             # every missing member
    python scripts/fetch_cds_member.py --model vic_wur --period 2071_2100 \\
        --gcm hadgem2_es --rcm rca4 --member r1i1p1               # one member
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import climate  # noqa: E402

DATASET = "sis-hydrology-variables-derived-projections"
OUT_DIR = ROOT / "data" / "raw" / "download" / "cds_hydrology_projections"

#: Every value below was read off the live request form and its constraints file
#: (`links.form` and `links.constraints` on the collection), for the models
#: and for the simulations, not recalled: the API spells
#: the models `vic_wur` and `e_hypegrid`, the periods `2071_2100`, and the
#: relative change `relative_change_from_reference_period`. Guessing any of them
#: produces a request the server rejects with no useful message.
MODELS = {"vic_wur": "VIC-WUR-EUR-11", "e_hypegrid": "E-HYPEgrid-EUR-11"}

PERIODS = ("2011_2040", "2041_2070", "2071_2100")

#: The eight simulations the constraints file offers for both gridded models
#: under RCP 8.5, as (gcm, rcm, realisation). The E-HYPEcatch members are left
#: out on purpose: they are per catchment and need a catchment join, not the
#: area join onto NUTS3 that `src/climate.py` does.
SIMULATIONS = (
    ("ec_earth", "cclm4_8_17", "r12i1p1"),
    ("ec_earth", "racmo22e", "r12i1p1"),
    ("ec_earth", "rca4", "r12i1p1"),
    ("hadgem2_es", "racmo22e", "r1i1p1"),
    ("hadgem2_es", "rca4", "r1i1p1"),
    ("mpi_esm_lr", "csc_remo2009", "r1i1p1"),
    ("mpi_esm_lr", "csc_remo2009", "r2i1p1"),
    ("mpi_esm_lr", "rca4", "r1i1p1"),
)
DEFAULT_SIMULATION = SIMULATIONS[0]

#: The two return periods the files on disk cover, so every new member matches
#: its siblings. The 2 and 10 year variables exist and are deliberately not
#: requested: an ensemble varies the model chain, not the question, and a member
#: that covers different return periods than the one it is compared with cannot
#: be aggregated with it.
VARIABLES = [
    "flood_recurrence_5_years_return_period",
    "flood_recurrence_50_years_return_period",
]
#: The filename prefixes those two variables come back under.
FILE_VARIABLES = ("rdisreturnmax5", "rdisreturnmax50")


def request(model: str, period: str, simulation=DEFAULT_SIMULATION) -> dict:
    """The CDS request for one model chain, one simulation and one period."""
    gcm, rcm, member = simulation
    return {
        "product_type": "climate_impact_indicators",
        "variable": VARIABLES,
        "variable_type": "relative_change_from_reference_period",
        "time_aggregation": "annual_mean",
        "experiment": ["rcp_8_5"],
        "hydrological_model": [model],
        "rcm": rcm,
        "gcm": gcm,
        "ensemble_member": [member],
        "period": [period],
    }


def _token(text: str) -> str:
    """Lower case, letters and digits only: `cclm4_8_17` and
    `CLMcom-CCLM4-8-17-v1` both reduce to something holding `cclm4817`."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def matches(fields: dict, model: str, period: str, simulation) -> dict:
    """The fields of a parsed filename that disagree with a request: {k: (got, want)}.

    The API's identifiers and the filename's are spelled differently
    (`hadgem2_es` against `MOHC-HadGEM2-ES`, `csc_remo2009` against
    `MPI-CSC-REMO2009-v1`), so the GCM and the regional model are compared on
    their letters and digits: the request's spelling must appear inside the
    file's. The hydrological model, period and realisation are compared exactly.
    """
    gcm, rcm, member = simulation
    expected = {
        "hydro_model": MODELS[model],
        "period": period.replace("_", "-"),
        "member": member,
        "kind": "rel",
    }
    wrong = {k: (fields[k], v) for k, v in expected.items() if fields[k] != v}
    for key, want in (("gcm", gcm), ("rcm", rcm)):
        if _token(want) not in _token(fields[key]):
            wrong[key] = (fields[key], want)
    return wrong


def check(path: Path, model: str, period: str, simulation=DEFAULT_SIMULATION) -> dict:
    """Parse one downloaded file's name and prove it is what was requested.

    The grammar is `src/climate.py`'s, not a second copy: a file this script
    accepts has to be a file the ensemble aggregation will also accept.
    """
    fields = climate.describe(path)
    wrong = matches(fields, model, period, simulation)
    if wrong:
        raise SystemExit(
            f"{path.name} is not what was requested: "
            + ", ".join(f"{k} is {got!r}, expected {want!r}" for k, (got, want) in wrong.items())
            + ". Nothing has been added to the ensemble directory."
        )
    return fields


def on_disk(model: str, period: str, simulation, out_dir: Path | None = None) -> list[str]:
    """The files already present for exactly this member, by every field.

    `out_dir` defaults to OUT_DIR read at call time, not at import: a default
    bound in the signature would ignore a patched or reconfigured OUT_DIR and
    read the real data directory.

    Matching on the hydrological model and the period alone - which was enough
    while one simulation existed - would report HadGEM2 through E-HYPEgrid as
    "already on disk" because EC-EARTH through E-HYPEgrid is.
    """
    out_dir = OUT_DIR if out_dir is None else out_dir
    if not out_dir.exists():
        return []
    found = []
    for path in sorted(out_dir.glob("*.nc")):
        try:
            fields = climate.describe(path)
        except ValueError:
            continue
        if fields["variable"] in FILE_VARIABLES and not matches(
            fields, model, period, simulation
        ):
            found.append(path.name)
    return found


def missing(out_dir: Path | None = None) -> list[tuple[str, str, tuple]]:
    """Every (model, period, simulation) without both of its variables on disk."""
    out_dir = OUT_DIR if out_dir is None else out_dir
    plan = []
    for simulation in SIMULATIONS:
        for model in MODELS:
            for period in PERIODS:
                have = on_disk(model, period, simulation, out_dir)
                if len({climate.describe(n)["variable"] for n in have}) < len(FILE_VARIABLES):
                    plan.append((model, period, simulation))
    return plan


def credentials_present() -> str | None:
    """Where the CDS key would be read from, or None. Never reads the key itself."""
    if os.environ.get("CDSAPI_KEY"):
        return "CDSAPI_KEY"
    if (Path.home() / ".cdsapirc").exists():
        return "~/.cdsapirc"
    return None


def fetch(client, model: str, period: str, simulation, out_dir: Path | None = None) -> list[str]:
    """Retrieve one member, verify every file, then move them into `out_dir`.

    Extracted to a staging directory first: a wrong member must never land in
    the directory `scripts/build_context.py` globs for ensemble files, because
    nothing downstream would question it.
    """
    out_dir = OUT_DIR if out_dir is None else out_dir
    gcm, rcm, member = simulation
    tag = f"{model}_{period}_{gcm}_{rcm}_{member}"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"cds_request_{tag}.zip"
    client.retrieve(DATASET, request(model, period, simulation), str(archive))

    staging = out_dir / f".staging_{tag}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staging)
        members = sorted(staging.glob("*.nc"))
        if not members:
            raise SystemExit(f"{archive.name} holds no .nc file. Nothing was added.")
        for path in members:
            check(path, model, period, simulation)
        names = []
        for path in members:
            shutil.move(str(path), out_dir / path.name)
            names.append(path.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="vic_wur", choices=sorted(MODELS))
    parser.add_argument("--period", default="2071_2100", choices=PERIODS)
    parser.add_argument("--gcm", default=DEFAULT_SIMULATION[0])
    parser.add_argument("--rcm", default=DEFAULT_SIMULATION[1])
    parser.add_argument("--member", default=DEFAULT_SIMULATION[2])
    parser.add_argument(
        "--all-missing", action="store_true",
        help="Every (model, period, simulation) whose two files are not on disk, "
             "one request each.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be requested and exit. Needs no credentials.",
    )
    args = parser.parse_args()

    if args.all_missing:
        plan = missing()
    else:
        simulation = (args.gcm, args.rcm, args.member)
        if simulation not in SIMULATIONS:
            raise SystemExit(
                f"{simulation} is not one of the dataset's simulations: {SIMULATIONS}"
            )
        already = on_disk(args.model, args.period, simulation)
        if len(already) >= len(FILE_VARIABLES):
            print("Already on disk, nothing to do:")
            for name in already:
                print(f"  {name}")
            return 0
        plan = [(args.model, args.period, simulation)]

    print(f"dataset: {DATASET}")
    print(f"{len(plan)} request(s):")
    for model, period, (gcm, rcm, member) in plan:
        print(f"  {MODELS[model]:18} {period}  {gcm} / {rcm} / {member}")
    if args.dry_run or not plan:
        print("\n--dry-run: nothing fetched." if args.dry_run else "\nNothing missing.")
        return 0

    source = credentials_present()
    if source is None:
        raise SystemExit(
            "No CDS credentials: neither CDSAPI_KEY nor ~/.cdsapirc is set. "
            "Create an account at https://cds.climate.copernicus.eu, accept the "
            "licence on the dataset's download page, then copy the key from your "
            "profile page into ~/.cdsapirc (url and key lines) or export "
            "CDSAPI_URL and CDSAPI_KEY."
        )
    try:
        import cdsapi
    except ImportError:
        raise SystemExit(
            "cdsapi is not installed. `pip install cdsapi`, then rerun. The "
            "dataset's licence also has to be accepted once, on its download "
            "page, or every request comes back as a licence error."
        )

    print(f"\ncredentials: {source}. The CDS queues each request; minutes is normal.")
    client = cdsapi.Client()
    added = 0
    for model, period, simulation in plan:
        names = fetch(client, model, period, simulation)
        for name in names:
            print(f"  verified {name}")
        added += len(names)

    print(f"\n{added} file(s) added to {OUT_DIR.relative_to(ROOT)}")
    print("Rebuild the context table to pick them up:")
    print("  python scripts/build_context.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
