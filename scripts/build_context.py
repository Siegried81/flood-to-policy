"""Freeze the per-region context table: data/processed/context.parquet.

One row per region, holding what `exposure.parquet` deliberately does not: the
built-up surface in the way of the water, the protected Natura 2000 area under
it, how much of a region drains into a basin it shares with another country, how
the flood discharge moves under a climate scenario, how much of it lies in the
member state's own areas of potential significant flood risk, and the Eurostat
denominators that qualify a region without describing its residents'
vulnerability (GDP, population density, household income). `src/assets.py`,
`src/environment.py`, `src/basins.py`, `src/climate.py`, `src/apsfr.py` and
`src/demographics.py` compute these; this script is what turns them into
something both UIs and the brief can read.

**A second table, not more columns on the first.** Two reasons, and the second
is the load-bearing one.

* **Different grain.** `exposure.parquet` is one row per region x return period.
  Basin sharing and climate change are per region: putting them in the long
  table repeats each value once per period and invites someone to average them.

* **`api/main.py` picks the vulnerability index's indicators by looking for
  numeric columns** (`vulnerability_indicators`, minus `NON_INDICATOR_COLUMNS`).
  A climate percentage or an area share landing in a min-max-scaled weighted
  mean by accident would be a wrong number nobody would see. Keeping them out of
  that table keeps it from happening by construction rather than by remembering.

The join key is the region identifier, the same one `/api/exposure` reports.

**What this table is NOT.** It is not comparable, column to column, with the
exposure table's `exposed_pop`:

* the built-up figures are measured at ONE return period, named in the output,
  not at every one;
* they are measured on the hazard raster **as masked**, the same way the
  exposure table is, so that at least is like for like;
* the climate columns are a change in river DISCHARGE, not in depth or extent -
  the direction and size of a change, never a future headcount.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_exposure import (  # noqa: E402
    DEFAULT_MIN_DEPTH_M,
    DEFAULT_STRIPES,
    HAZARD_DIR,
    PERMANENT_WATER,
    PROTECTED_OUT,
    SPURIOUS_AREAS,
    _exposure_one_period,
    boundaries,
    hazard_paths,
    protection_path,
    total_population,
)
from src import (  # noqa: E402
    apsfr, assets, basins, climate, demographics, efas, environment, facilities,
    hera, landcover, pluvial, sealing,
)

OUT = ROOT / "data" / "processed" / "context.parquet"
DOWNLOAD = ROOT / "data" / "raw" / "download"

#: The return periods the facility counts are given at: frequent, the planning
#: standard, and the extreme. Three, not nine - each is a column per facility
#: type and per reading (undefended, residual).
FACILITY_RETURN_PERIODS = (10, 100, 500)

#: Layers `--only` can recompute into an existing table without the rest.
LAYERS = (
    "climate", "residual", "facilities", "epoch2010", "sealing", "imperviousness",
    "pluvial", "flood_recurrence", "efas2021", "hera_trend", "landcover",
)

#: The optional layers below, each `(name, function)` returning `(frame, note)`
#: or `(None, reason)`. Every one of them reads files a human fetched on purpose
#: (an account, a 69 GB download), so a missing input is a note, never a crash.
OPTIONAL_LAYERS = {
    "sealing": lambda admin: sealing.hera_by_region(admin),
    "imperviousness": lambda admin: sealing.clms_by_region(admin),
    "pluvial": lambda admin: pluvial.by_region(admin),
    "flood_recurrence": lambda admin: pluvial.flood_recurrence_by_region(admin),
    "efas2021": lambda admin: efas.by_region(admin),
    "hera_trend": lambda admin: hera.by_region(admin, build=False),
    "landcover": lambda admin: landcover.by_region(admin),
}
CLIMATE_DIR = ROOT / "data" / "raw" / "download" / "cds_hydrology_projections"

#: The return period the built-up figures are measured at. 100 years because it
#: is the planning standard and the one every measured figure in this repo uses;
#: named in the output so a reader cannot mistake it for all of them.
DEFAULT_RETURN_PERIOD = 100


def _built(admin: gpd.GeoDataFrame, return_period: int, min_depth_m: float,
           stripes: int):
    """Built-up surface exposed at one return period, or a reason it is absent.

    Measured through `_exposure_one_period`, the same function that measures
    population, with the built-up raster in the population slot. That is not a
    trick: GHS-BUILT-S is on exactly the same 1 km Mollweide grid as GHS-POP and
    square metres are as summable as people. What it buys is parity - the same
    windowing, the same masking of permanent water and spurious areas, and the
    same extrapolation - so `exposed_built_m2` and `exposed_pop` can appear in
    one sentence. `assets.built_exposure` on a raw raster cannot, because it
    would count the river channel as flooded ground.

    Returns `(frame, note)`. A missing archive is not fatal: the basin and
    climate halves are independent of it, and a partial table that says what is
    missing is more useful on a hackathon morning than a traceback.
    """
    try:
        path = assets.built_path()
    except SystemExit as exc:
        return None, str(exc)
    periods = hazard_paths()
    if return_period not in periods:
        return None, (
            f"no hazard raster for RP{return_period}; have {sorted(periods)}"
        )
    measured = _exposure_one_period(
        periods[return_period], path, admin,
        stripes=stripes, min_depth_m=min_depth_m, mode="fraction",
        masks=[PERMANENT_WATER, SPURIOUS_AREAS],
    )
    total = assets.total_built_surface(path, admin)
    observed = pd.to_numeric(measured["exposed_pop"], errors="coerce")
    frame = pd.DataFrame(
        {
            f"exposed_built_m2_rp{return_period}": observed,
            "built_total_m2": pd.to_numeric(total, errors="coerce"),
        },
        index=admin.index,
    )
    denominator = frame["built_total_m2"]
    frame[f"built_share_exposed_rp{return_period}"] = observed.divide(
        denominator.where(denominator > 0)
    ).clip(upper=1.0)
    return frame, None


def _natura(admin: gpd.GeoDataFrame, return_period: int, min_depth_m: float):
    """Natura 2000 area on flood-prone ground, or a reason it is absent.

    Same return period, same depth threshold and same two masks as the built-up
    figures, so "flooded" means one thing across the table. Measured on the
    hazard grid itself - see `src/environment.py` for why that is exact here
    while the population figures must be windowed on the population grid.
    """
    periods = hazard_paths()
    if return_period not in periods:
        return None, f"no hazard raster for RP{return_period}; have {sorted(periods)}"
    try:
        frame = environment.natura_by_region(
            periods[return_period], admin,
            return_period=return_period, min_depth_m=min_depth_m,
            masks=[str(HAZARD_DIR / PERMANENT_WATER), str(HAZARD_DIR / SPURIOUS_AREAS)],
        )
    except environment.NaturaUnavailable as exc:
        return None, str(exc)
    return frame, None


def _basins(admin: gpd.GeoDataFrame):
    """Shared-basin shares, or a reason they are absent.

    The districts come from a cached EEA service; an uncached miss takes about
    two minutes and needs the network, so a failure here is reported rather than
    raised - see `config/sources.yaml` for why it cannot be pre-fetched by
    `src.fetch`.
    """
    try:
        districts = basins.districts()
    except basins.BasinsUnavailable as exc:
        return None, str(exc)
    return basins.shared_basin_exposure(admin, districts), None


def _climate(admin: gpd.GeoDataFrame, variable: str, period: str):
    """Ensemble change for one variable and period, or a reason it is absent.

    Every file in `CLIMATE_DIR` matching the variable and period is treated as
    an ensemble member, which is the point: a single member's regional figure
    moves by hundreds of percent between periods and says nothing.
    """
    if not CLIMATE_DIR.exists():
        return None, f"{CLIMATE_DIR.relative_to(ROOT)} is absent"
    members = []
    for path in sorted(CLIMATE_DIR.glob("*.nc")):
        try:
            fields = climate.describe(path)
        except ValueError:
            continue
        if fields["variable"] == variable and fields["period"] == period:
            members.append(path)
    if not members:
        return None, (
            f"no {variable} file for {period} in "
            f"{CLIMATE_DIR.relative_to(ROOT)} - fetch it with scripts/fetch_cds_member.py or the CDS form"
        )
    frame = climate.ensemble_change_by_region(admin, members)
    frame.columns = [f"{c}_{period.replace('-', '_')}" for c in frame.columns]
    return frame, f"{len(members)} member(s) for {period}"


def _zip_tif(path: Path) -> str:
    """A GDAL `zip://` URI for the single GeoTIFF inside a GHSL archive."""
    with zipfile.ZipFile(path) as archive:
        tifs = [n for n in archive.namelist() if n.lower().endswith(".tif")]
    if len(tifs) != 1:
        raise SystemExit(f"Expected exactly one .tif in {path.name}, found {tifs}")
    return f"zip://{path.as_posix()}!/{tifs[0]}"


def _residual(admin: gpd.GeoDataFrame, key: str):
    """Residual exposure per return period, or a reason it is absent.

    Read from `exposure_protected.parquet`, which `build_exposure.py
    --protection` writes with the same windows, masks and threshold as the
    exposure table - so `residual_exposed_pop_rp100` and the exposure table's
    RP100 `exposed_pop` differ by the people the defences hold and by nothing
    else. Kept here rather than in the exposure table because a second
    headcount there would be scanned into the vulnerability index.
    """
    if not PROTECTED_OUT.exists():
        return None, (
            f"{_shown(PROTECTED_OUT)} is absent - run "
            "scripts/build_exposure.py --protection first"
        )
    protected = pd.read_parquet(PROTECTED_OUT)
    wide = protected.pivot(index=key, columns="return_period", values="exposed_pop")
    wide.columns = [f"residual_exposed_pop_rp{rp}" for rp in wide.columns]
    frame = wide.reindex(admin[key].values)
    frame.index = admin.index
    return frame, f"{len(wide.columns)} return periods from {_shown(PROTECTED_OUT)}"


def _facilities(admin: gpd.GeoDataFrame, min_depth_m: float):
    """Hospitals and schools in the flood footprint, or a reason they are absent.

    Same depth threshold and masks as every other figure here, at
    `FACILITY_RETURN_PERIODS`, undefended and residual. A region in a country
    the GISCO layer does not cover reads NaN, and so does a bed figure that
    misses any of the hospitals it would sum (`hospitals_cap_beds_known` says
    how many carry one); `config/sources.yaml` says the definitions vary by
    country.
    """
    periods = hazard_paths()
    masks = [str(HAZARD_DIR / PERMANENT_WATER), str(HAZARD_DIR / SPURIOUS_AREAS)]
    try:
        protection = protection_path()
    except SystemExit:
        protection = None
    frames, notes = [], []
    for source_id, prefix, weight in (
        ("gisco_healthcare", "hospitals", "cap_beds"),
        ("gisco_education", "schools", None),
    ):
        path = DOWNLOAD / f"{source_id}.gpkg"
        if not path.exists():
            notes.append(f"{prefix}: {path.name} absent")
            continue
        points = facilities.load(path)
        flags = {}
        for rp in FACILITY_RETURN_PERIODS:
            if rp not in periods:
                continue
            wet = facilities.flooded(points, periods[rp], min_depth_m=min_depth_m, masks=masks)
            flags[f"flooded_rp{rp}"] = wet
            if protection is not None:
                flags[f"flooded_residual_rp{rp}"] = wet & ~facilities.held(points, protection, rp)
        frames.append(facilities.counts_by_region(points, admin, flags, prefix=prefix, weight=weight))
        notes.append(f"{prefix}: {len(points):,} points")
    if not frames:
        return None, "; ".join(notes)
    return pd.concat(frames, axis=1), "; ".join(notes)


def _epoch_2010(admin: gpd.GeoDataFrame, return_period: int, min_depth_m: float,
                stripes: int):
    """People and built-up surface in the footprint in 2010, or a reason not.

    The same function, windows, masks and threshold as the 2025 figures, with
    the 2010 GHSL epochs in the population slot - the only thing that changes
    between the two readings is the year of the grid, so the difference is the
    change in what stands in the floodplain, not in how it was measured. The
    footprint itself is today's hazard map in both readings.
    """
    pop_zip = DOWNLOAD / "ghsl_pop_europe_2010.zip"
    built_zip = DOWNLOAD / "ghsl_built_europe_2010.zip"
    missing = [p.name for p in (pop_zip, built_zip) if not p.exists()]
    if missing:
        return None, f"{', '.join(missing)} absent"
    periods = hazard_paths()
    if return_period not in periods:
        return None, f"no hazard raster for RP{return_period}"
    masks = [PERMANENT_WATER, SPURIOUS_AREAS]
    pop_path, built_path = _zip_tif(pop_zip), _zip_tif(built_zip)
    people = _exposure_one_period(
        periods[return_period], pop_path, admin, stripes=stripes,
        min_depth_m=min_depth_m, mode="fraction", masks=masks,
    )
    built = _exposure_one_period(
        periods[return_period], built_path, admin, stripes=stripes,
        min_depth_m=min_depth_m, mode="fraction", masks=masks,
    )
    frame = pd.DataFrame(
        {
            f"exposed_pop_2010_rp{return_period}": pd.to_numeric(people["exposed_pop"], errors="coerce"),
            "pop_total_2010": total_population(pop_path, admin).values,
            f"exposed_built_m2_2010_rp{return_period}": pd.to_numeric(built["exposed_pop"], errors="coerce"),
            "built_total_m2_2010": pd.to_numeric(
                assets.total_built_surface(built_path, admin), errors="coerce"
            ),
        },
        index=admin.index,
    )
    return frame, f"GHSL 2010 epoch at RP{return_period}"


def _new_layers(admin, key, args, only):
    """The layers `--only` can name, computed in a fixed order; (frames, notes)."""
    frames, notes = [], []
    if "climate" in only:
        periods = args.climate_period
        if not periods:
            periods = sorted({
                climate.describe(p)["period"]
                for p in CLIMATE_DIR.glob("*.nc")
                if _parses(p)
            }) if CLIMATE_DIR.exists() else []
        if not periods:
            notes.append("climate: SKIPPED - no readable .nc files")
        for period in periods:
            frame, why = _climate(admin, args.climate_variable, period)
            notes.append(f"climate {period}: {'SKIPPED - ' if frame is None else ''}{why}")
            frames.append(frame)
    if "residual" in only:
        frame, why = _residual(admin, key)
        notes.append(f"residual: {'SKIPPED - ' if frame is None else ''}{why}")
        frames.append(frame)
    if "facilities" in only:
        frame, why = _facilities(admin, args.min_depth_m)
        notes.append(f"facilities: {'SKIPPED - ' if frame is None else ''}{why}")
        frames.append(frame)
    if "epoch2010" in only:
        frame, why = _epoch_2010(admin, args.return_period, args.min_depth_m, args.stripes)
        notes.append(f"2010 epoch: {'SKIPPED - ' if frame is None else ''}{why}")
        frames.append(frame)
    for name, layer in OPTIONAL_LAYERS.items():
        if name in only:
            frame, why = layer(admin)
            notes.append(f"{name}: {'SKIPPED - ' if frame is None else ''}{why}")
            frames.append(frame)
    return [f for f in frames if f is not None], notes


def _update(admin, key, args) -> int:
    """`--only`: recompute the named layers into the existing table.

    The full build is an afternoon of rasters and services; adding hospitals
    should not mean re-reading the climate ensemble. Every column the named
    layers produce is replaced, every other column is kept byte for byte.
    """
    if not args.out.exists():
        raise SystemExit(f"{_shown(args.out)} does not exist; run the full build first.")
    table = pd.read_parquet(args.out)
    if list(table[key]) != list(admin[key]):
        raise SystemExit(f"{_shown(args.out)} rows are not in boundary order; run the full build.")
    table.index = admin.index
    order = list(table.columns)
    frames, notes = _new_layers(admin, key, args, args.only)
    for frame in frames:
        table = table.drop(columns=[c for c in frame.columns if c in table.columns]).join(frame)
    # A replaced column keeps its place, so a diff of the table shows values, not a shuffle.
    table = table[[c for c in order if c in table.columns]
                  + [c for c in table.columns if c not in order]]
    partial = args.out.with_suffix(".parquet.part")
    table.to_parquet(partial, index=False)
    partial.replace(args.out)
    print(f"{len(table)} rows -> {_shown(args.out)}, {len(table.columns)} columns (updated: {', '.join(args.only)})")
    for note in notes:
        print(f"  {note}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--return-period", type=int, default=DEFAULT_RETURN_PERIOD,
        help=f"Return period for the built-up figures (default "
             f"{DEFAULT_RETURN_PERIOD}). One, not all nine: the columns are named "
             f"after it so the table cannot be read as covering every scenario.",
    )
    parser.add_argument(
        "--min-depth-m", type=float, default=DEFAULT_MIN_DEPTH_M,
        help=f"Depth above which a cell counts as flooded (default "
             f"{DEFAULT_MIN_DEPTH_M}). Keep it equal to the exposure table's, or "
             f"the two halves of a brief disagree about what flooded means.",
    )
    parser.add_argument(
        "--climate-variable", default="rdisreturnmax50",
        help="CDS variable to aggregate (default rdisreturnmax50, the 50-year "
             "return value of annual maximum river discharge).",
    )
    parser.add_argument(
        "--climate-period", action="append",
        help="CDS period, repeatable. Default: every period present on disk.",
    )
    parser.add_argument(
        "--stripes", type=int, default=DEFAULT_STRIPES,
        help=f"Population-grid row windows for the built-up pass (default "
             f"{DEFAULT_STRIPES}). Memory only; the result does not depend on it.",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--only", action="append", choices=LAYERS,
        help="Recompute only this layer into the existing table, keeping every "
             "other column. Repeatable.",
    )
    args = parser.parse_args()

    admin = boundaries()
    # `boundaries()` renames GISCO's fields to `nuts_id`, `region`, `country`.
    key = "nuts_id"
    if args.only:
        return _update(admin, key, args)
    table = pd.DataFrame({key: admin[key].values}, index=admin.index)
    notes: list[str] = []

    built, why = _built(
        admin, args.return_period, args.min_depth_m, args.stripes
    )
    if built is None:
        notes.append(f"built-up: SKIPPED - {why}")
    else:
        table = table.join(built)
        notes.append(
            f"built-up: RP{args.return_period} at >= {args.min_depth_m} m, "
            f"masked like the exposure table "
            f"({PERMANENT_WATER}, {SPURIOUS_AREAS})"
        )

    natura, why = _natura(admin, args.return_period, args.min_depth_m)
    if natura is None:
        notes.append(f"natura 2000: SKIPPED - {why}")
    else:
        table = table.join(natura)
        notes.append(
            f"natura 2000: RP{args.return_period} at >= {args.min_depth_m} m on the "
            f"hazard grid, masked like the exposure table; "
            f"{int(natura['natura2000_km2'].notna().sum())} of {len(admin)} units "
            "in a country the network covers"
        )

    shared, why = _basins(admin)
    if shared is None:
        notes.append(f"basins: SKIPPED - {why}")
    else:
        table = table.join(shared)
        notes.append("basins: WFD districts, area shares in EPSG:3035")

    # What the Member State itself declared under Article 5 of the Floods
    # Directive, as opposed to what the hazard model shows. The pair is the
    # point: a region with exposed residents and no declared area is a
    # compliance question, which is a different kind of finding from a high
    # exposure count. It is NOT proof the designation is wrong - a State may have
    # assessed the area and concluded the risk is not significant, which the
    # Directive allows - so the column says what was declared and leaves the
    # conclusion to a human.
    try:
        declared = apsfr.declared_by_region(admin)
        table = table.join(declared)
        notes.append(
            f"apsfr: cycle {declared['apsfr_cycle'].iloc[0]}, "
            f"{int(declared['apsfr_declared'].sum())} of {len(admin)} units "
            "intersect a declared area"
        )
    except apsfr.ApsfrUnavailable as exc:
        notes.append(f"apsfr: SKIPPED - {exc}")

    # GDP is a DENOMINATOR, not an indicator: a region is not vulnerable for
    # being rich, and `api/main.py::vulnerability_indicators` would weight it as
    # one the moment it appeared on an exposure row. So it lives here, where it
    # turns an absolute loss into a share of regional wealth - the comparison a
    # European brief needs, because 100 MEUR means different things in Hainaut
    # and in Oberbayern. The year is the newest one Eurostat has substantially
    # published (`demographics._latest`), and a unit missing from it stays
    # missing.
    try:
        gdp = demographics.gdp_meur().reindex(admin[key].values)
        gdp.index = admin.index
        table = table.join(gdp)
        measured = int(gdp["gdp_meur"].notna().sum())
        notes.append(
            f"gdp: {measured} of {len(admin)} units, "
            f"MIO_EUR {gdp['gdp_meur_year'].dropna().iloc[0]}"
        )
    except demographics.EurostatUnavailable as exc:
        notes.append(f"gdp: SKIPPED - {exc}")

    # Density and household income qualify a region the way GDP does, and for
    # the same reason live here: on an exposure row they would be scanned into
    # the vulnerability index as numeric columns.
    try:
        indicators = demographics.context_indicators(admin[key].values)
        indicators.index = admin.index
        table = table.join(indicators)
        notes.append(
            f"density: {int(indicators['pop_density_per_km2'].notna().sum())} of "
            f"{len(admin)} units, PER_KM2 "
            f"{indicators['pop_density_year'].dropna().iloc[0]}; household income: "
            f"{int(indicators['household_income_pps_per_hab'].notna().sum())} of "
            f"{len(admin)} units, PPS per inhabitant "
            f"{indicators['household_income_year'].dropna().iloc[0]} (NUTS2)"
        )
    except demographics.EurostatUnavailable as exc:
        notes.append(f"density and household income: SKIPPED - {exc}")

    frames, layer_notes = _new_layers(admin, key, args, LAYERS)
    for frame in frames:
        table = table.join(frame)
    notes.extend(layer_notes)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out, index=False)
    print(f"{len(table)} rows -> {_shown(args.out)} "
          f"({args.out.stat().st_size:,} B), {len(table.columns)} columns")
    for note in notes:
        print(f"  {note}")
    return 0


def _shown(path: Path) -> Path:
    """`path` relative to the repository when it lies inside it, else as given.

    `--out` is usually typed relative to the working directory, and
    `relative_to(ROOT)` raises on a relative path - AFTER the table has been
    written, so the run reported failure, exited 1 and never printed its notes.
    """
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _parses(path: Path) -> bool:
    """Whether a filename is a CDS member name. Keeps the archive out."""
    try:
        climate.describe(path)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
