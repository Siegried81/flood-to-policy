"""Build the frozen exposure table both UIs read: data/processed/exposure.parquet.

One row per NUTS3 region x return period, over the whole European extent.

A script rather than a notebook cell because the table has to be rebuilt
identically after any change to `src/exposure.py`, and because the UIs refuse to
compute it on demand: a continental zonal-statistics pass is minutes of work, so
it is frozen to parquet once and read from there (`api/main.py`,
`app/streamlit_app.py`).

Parquet, not CSV, because a NUTS code is a string whose leading zeros CSV loses.

Three things to know before changing anything here:

* **The build runs in windows, and the window is cut on the POPULATION grid.**
  A single pass cannot fit: each `Europe_RP*_filled_depth.tif` is
  51,992 x 110,162 cells, so in fraction mode the band and its two derived masks
  are ~64 GiB of float32 before any destination grid, and on a 63 GiB machine
  that does not fail cleanly - it thrashes until it is killed. So the run is cut
  into pieces, and WHICH raster is cut decides whether the answer is right.

  Cutting the population grid makes the sum exact, because a population cell then
  belongs to exactly one window and nothing is written twice. Cutting the hazard
  raster instead cannot: a population cell lying across two hazard pieces is
  written by both, and `Resampling.average` renormalises over whatever source
  area each piece holds, so both report near-full coverage for the same cell.
  Measured on hazard stripes, the continental RP100 total moved by 0.25% with
  the stripe count. `tests/test_stripes.py` pins the invariant.

* **`exposed_pop` is NOT the figure to accumulate.** It carries the per-unit
  extrapolation onto unobserved ground, so adding it once per window would apply
  that extrapolation N times. What is summed here is `exposed_pop_observed`,
  which has no extrapolation in it, together with `cells_counted` and
  `hazard_coverage * cells_counted`; the division happens once at the end.

* **A unit outside the current window comes back as `None`, and one `None`
  poisons a running sum.** Every window's contribution is passed through
  `fillna(0.0)` before it is added, and a unit whose accumulated coverage is
  still 0 across every window is restored to `None` at the end — "not measured"
  has to stay distinguishable from a measured dry zero.

* **The CRS is checked, not assumed.** A `pyproj` that fails to load leaves
  geopandas importable but strips its CRS support: `read_file` then returns
  `crs=None` with a warning only, and every zonal statistic would be computed
  against unreprojected polygons - the whole analysis landing in the wrong
  place, silently, with the test suite still green. So the boundaries' CRS is
  asserted before any raster is opened.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import zipfile
from contextlib import ExitStack
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.io import MemoryFile
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window
from rasterstats import zonal_stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import demographics  # noqa: E402
from src.exposure import exposed_population  # noqa: E402

HAZARD_DIR = ROOT / "data" / "raw" / "download" / "jrc_flood_hazard"
POP_ZIP = ROOT / "data" / "raw" / "download" / "ghsl_pop_europe.zip"
BOUNDARIES = ROOT / "data" / "raw" / "download" / "gisco_nuts3.geojson"
OUT = ROOT / "data" / "processed" / "exposure.parquet"
PROTECTION_ZIP = ROOT / "data" / "raw" / "download" / "jrc_flood_protection_standards.zip"
#: The residual table never overwrites the undefended one: they answer two
#: different questions, and `exposure.parquet` is what every UI and the brief
#: quote. `scripts/build_context.py` carries the residual figures from here.
PROTECTED_OUT = ROOT / "data" / "processed" / "exposure_protected.parquet"

#: One finished return period, parked on disk before the next one starts.
#:
#: Holding every period in memory and writing once at the end means an
#: interruption costs the whole run. Measured: the Linux OOM killer took such a
#: process during RP100 - 15.7 GB resident against a 16 GB WSL cap - after seven
#: periods had completed, and every one of them was lost. A continental pass is
#: about eight minutes, so that is an hour of compute thrown away by a design
#: choice, not by the crash.
#:
#: Each period is written as it finishes and read back at assembly, so a
#: rerun skips what is already there and an interruption costs ONE period. The
#: parts are keyed by the parameters that change the numbers, because a part
#: built at a different depth threshold or in a different mode is not the same
#: measurement and silently reusing it would be the worst kind of resume.
PARTS = ROOT / "data" / "processed" / "exposure_parts"


def _part_path(
    return_period: int, *, mode: str, min_depth_m: float, masks: list[str],
    protected: bool = False,
) -> Path:
    """Where one finished return period is parked. Named by what it measures.

    One mask alone names WHICH one, because keeping the permanent water and
    keeping the spurious areas are two measurements with the same mask count.
    Both masks and none keep the bare count, the names the parts on disk were
    built under, so a rerun still finds them. A run behind the flood
    protection standards is tagged `_prot`: the same return period, a different
    figure, and the two must never be assembled into one table.
    """
    masks_tag = f"m{len(masks)}" if len(masks) != 1 else f"m1-{Path(masks[0]).stem}"
    tag = f"rp{return_period}_{mode}_d{min_depth_m}_{masks_tag}" + ("_prot" if protected else "")
    return PARTS / f"{tag}.parquet"

#: `Europe_RP100_filled_depth.tif` -> 100. The directory also holds the two
#: masks below, which are flags rather than scenarios and must not become return
#: periods.
_RETURN_PERIOD_RE = re.compile(r"Europe_RP(\d+)_filled_depth\.tif$", re.IGNORECASE)

#: The JRC ships two masks on the same grid as the depth rasters, flagging cells
#: with 1.0 and leaving the rest NaN. Both are applied by default, because a
#: count that includes them is not a count of people at risk:
#:
#: * **Permanent water bodies** are the river channel, the lakes and the sea -
#:   already water before any flood. They are patched into the depth rasters at
#:   exactly 1.00 m, so they survive every threshold up to and including the
#:   0.5 m damage threshold. Measured on the Benelux at RP10 they are **21.3% of
#:   all wet cells**; removing them at RP100 moves BE/NL/LU from 5,065,526 to
#:   4,344,955 people (-14.2%).
#: * **Spurious depth areas** are the publisher's own flag for cells where the
#:   modelled depth is an artefact. Keeping them means presenting the JRC's
#:   known-bad values as findings.
#:
#: `--keep-permanent-water` and `--keep-spurious-areas` restore the unmasked
#: reading; they change what the number means, so they say so on the tin.
PERMANENT_WATER = "Europe_permanent_water_bodies.tif"
SPURIOUS_AREAS = "Europe_spurious_depth_areas.tif"

#: Depth above which a cell counts as flooded, in metres.
#:
#: 0.5 m, not 0.0, and this is a deliberate choice about what is being measured.
#: At 0.0 the figure is "anyone standing on ground the model puts any water on",
#: which includes a centimetre of sheet flow across a field. 0.5 m is the usual
#: threshold for damage to buildings, and it is the depth at which a ground floor
#: becomes uninhabitable and an adult cannot walk. The difference is not small:
#: BE/NL/LU at RP100 is 5,065,526 people at any water and 3,949,210 at >= 0.5 m
#: (78%), 2,610,894 at >= 1.0 m (52%). Pass `--min-depth-m 0` for the upper
#: bound, and present the two together rather than either alone.
DEFAULT_MIN_DEPTH_M = 0.5

#: The boundaries are published in this CRS. Asserted rather than trusted, so a
#: silently CRS-less geopandas stops the run instead of mislocating every unit.
EXPECTED_BOUNDARY_CRS = "EPSG:3035"

#: Row windows over the POPULATION grid per return period, not over the hazard
#: raster - see the module docstring for why that distinction is a correctness
#: one. Ten divides the global 1 km grid into bands that each read a hazard
#: region comfortably inside memory on a 63 GiB machine; measured, a
#: nine-period build at this setting completes without swapping. Raising it
#: lowers the peak further and cannot change the result.
DEFAULT_STRIPES = 10

#: Eurostat country codes to names, for the 37 countries in the NUTS 2024 file.
#: Carried here rather than looked up because GISCO publishes country names in a
#: separate NUTS level-0 file this project does not download, and because a table
#: that says "NL" to a jury is barely better than one that says "NL366".
#: Two traps worth knowing: Eurostat writes Greece **EL**, not GR, and there is
#: no UK in the 2024 vintage.
COUNTRY_NAMES = {
    "AL": "Albania", "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria",
    "CH": "Switzerland", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "EE": "Estonia", "EL": "Greece", "ES": "Spain",
    "FI": "Finland", "FR": "France", "HR": "Croatia", "HU": "Hungary",
    "IE": "Ireland", "IS": "Iceland", "IT": "Italy", "LI": "Liechtenstein",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "ME": "Montenegro",
    "MK": "North Macedonia", "MT": "Malta", "NL": "Netherlands", "NO": "Norway",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "RS": "Serbia",
    "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia", "TR": "Türkiye",
    "XK": "Kosovo",
}


def hazard_paths() -> dict[int, str]:
    """The `{return_period: path}` map for the nine EFAS/JRC depth rasters."""
    found: dict[int, str] = {}
    for path in sorted(HAZARD_DIR.glob("*.tif")):
        match = _RETURN_PERIOD_RE.search(path.name)
        if match:
            found[int(match.group(1))] = str(path)
    if not found:
        raise SystemExit(f"No Europe_RP*_filled_depth.tif under {HAZARD_DIR}")
    return found


def population_path() -> str:
    """A GDAL `zip://` URI for the 1 km GHS-POP raster, read without unpacking.

    The archive also carries a `.ovr` pyramid and two documents; only the single
    `.tif` is the population grid.

    Left zipped, but not for free. Measured on the one pass that reads it per polygon rather than per window:
    `total_population` sends `zonal_stats` 1,345 separate polygon windows, each a
    random seek into a compressed stream, and the process read **85.8 GB** from
    disk over about fourteen minutes to produce 1,345 sums. Reading windows out
    of a zip is cheap when the windows are a handful of full-width row bands, and
    very expensive when they are a thousand small boxes.
    """
    with zipfile.ZipFile(POP_ZIP) as archive:
        tifs = [n for n in archive.namelist() if n.lower().endswith(".tif")]
    if len(tifs) != 1:
        raise SystemExit(f"Expected exactly one .tif in {POP_ZIP.name}, found {tifs}")
    return f"zip://{POP_ZIP.as_posix()}!/{tifs[0]}"


def boundaries() -> gpd.GeoDataFrame:
    """NUTS3 units, with the columns the UIs label rows by.

    `NAME_LATN` is preferred over `NUTS_NAME` because it is the Latin-script
    spelling for every country, including those that publish Cyrillic or Greek
    names - the UIs and the LLM prompt both need one script.
    """
    admin = gpd.read_file(BOUNDARIES)
    if admin.crs is None:
        raise SystemExit(
            "The boundaries loaded with crs=None. geopandas is importable but has "
            "lost its CRS engine (see the pyproj note in requirements.txt): every "
            "zonal statistic would be computed against unreprojected polygons. "
            "Fix the pyproj install before trusting any figure from this run."
        )
    if admin.crs.to_string() != EXPECTED_BOUNDARY_CRS:
        raise SystemExit(
            f"Boundaries are {admin.crs.to_string()}, expected {EXPECTED_BOUNDARY_CRS}"
        )
    return admin.rename(
        columns={"NUTS_ID": "nuts_id", "NAME_LATN": "region", "CNTR_CODE": "country"}
    )[["nuts_id", "region", "country", "geometry"]]


def total_population(pop_path: str, admin: gpd.GeoDataFrame) -> pd.Series:
    """Residents per unit, the denominator for any "share exposed" figure.

    `exposed_population` does not return it - it answers how many people are in
    the flood zone, not how many there are - but a count without its denominator
    cannot be compared between a city and a rural arrondissement, which is the
    comparison a European ranking is for. Computed once here, since it does not
    depend on the return period.

    `zonal_stats` is given the path rather than an array so it reads one window
    per polygon instead of holding the global 4.84 GiB grid.

    Cached, for the same reason the return periods are: it does not depend on the
    return period, so building the nine periods as nine processes - which is how
    a 16 GB machine survives the heavy ones - would otherwise repeat this pass
    nine times for an identical answer.

    The cache is named after the raster it summed. One fixed
    `total_pop.parquet` lets the first caller to fill it answer for every
    raster after it: measured 2026-10-24, the 2010 epoch run read the 2025
    totals back and reported exactly 446,267,469 EU-27 residents for both
    years. The default 2025 grid keeps the plain `total_pop.parquet` name, so
    the parts already on disk are still found.
    """
    stem = Path(pop_path.split("!")[-1]).stem
    default_stem = Path(population_path().split("!")[-1]).stem if POP_ZIP.exists() else None
    name = "total_pop.parquet" if stem == default_stem else f"total_pop_{stem}.parquet"
    cache = PARTS / name
    if cache.exists():
        parked = pd.read_parquet(cache)["total_pop"]
        if len(parked) == len(admin):
            return pd.Series(parked.to_numpy(), index=admin.index, name="total_pop")

    with rasterio.open(pop_path) as pop:
        polygons = admin.to_crs(pop.crs)
        nodata = pop.nodata
    stats = zonal_stats(polygons, pop_path, stats=["sum"], nodata=nodata, all_touched=False)
    totals = pd.Series(
        [s["sum"] or 0.0 for s in stats], index=admin.index, name="total_pop"
    )
    PARTS.mkdir(parents=True, exist_ok=True)
    totals.to_frame().to_parquet(cache, index=False)
    return totals


# The one correctness claim of the striped build: stripes are cut on the
# population grid, so every person is counted in exactly one stripe and the
# totals do not depend on how many stripes are used.
def _stripes(path: str, count: int) -> list[Window]:
    """Row windows over the POPULATION grid, covering it exactly once.

    The population grid, not the hazard raster, and that is the whole point. A
    population cell belongs to exactly one of these windows, so the per-unit sums
    below are additive by construction and the answer cannot depend on `count`.

    Striping the hazard raster instead cannot have that property. A population cell lying across two hazard stripes is
    written by both, and `Resampling.average` renormalises over whatever source
    area each piece happens to hold, so both report a coverage near 1 for the
    same cell. Measured on hazard stripes: summed coverage reached 1.08 at two stripes and
    1.17 at three, and the continental total moved by 0.25% between 3 and 13.
    """
    with rasterio.open(path) as src:
        height, width = src.height, src.width
    step = -(-height // count)  # ceil, so the last window is the short one
    return [
        Window(0, top, width, min(step, height - top))
        for top in range(0, height, step)
    ]


#: Hazard cells of margin around the region read for one population window. The
#: warp needs source cells slightly beyond a destination cell to fill it, and a
#: destination cell filled from a truncated source is exactly the error this
#: rewrite removes. Two cells is ample at 3 arc-seconds against 1 km.
_HAZARD_MARGIN_CELLS = 2


def _hazard_window(haz, pop, pop_window: Window):
    """The hazard rows covering one population window, at full width.

    **Rows only, and every column.** The population window is a row band of a
    Mollweide grid, and in Mollweide the y coordinate depends on latitude alone -
    so the band's latitude range is exact and transforms faithfully. Its
    LONGITUDE range does not: a row band of the global grid spans the whole
    ellipse, and `transform_bounds` under-reports it badly.

    Measured against the real rasters, brute-forced over 16M sample
    points: for one window of ten, `transform_bounds` gives -163.0..163.0 where
    the truth is -180..180, missing 17 degrees on each side. For a single window
    it returns left == right == 0.0, because the global raster's own bounding box
    is about 900 m wider than the projection's valid domain and pyproj answers
    `inf` at the corners, which `transform_bounds` silently drops. Trusting it
    made `--stripes 1` read a FOUR-pixel strip on the Greenwich meridian out of
    110,162 columns, and write a parquet without complaining.

    Taking all columns costs I/O on a raster that is read per window anyway, and
    it removes the whole class of failure. Only the latitude bound is narrowed,
    which is the one that makes the window small enough to hold in memory.
    """
    bounds = rasterio.windows.bounds(pop_window, pop.transform)
    # Only the vertical bounds are transformed, and only through the centre
    # meridian where Mollweide's y-to-latitude mapping is the whole story.
    centre_x = (bounds[0] + bounds[2]) / 2.0
    _, bottom, _, top = transform_bounds(
        pop.crs, haz.crs, centre_x, bounds[1], centre_x, bounds[3]
    )
    if not (bottom < top):
        return None
    full = rasterio.windows.from_bounds(
        haz.bounds.left, bottom, haz.bounds.right, top, haz.transform
    )
    margin = _HAZARD_MARGIN_CELLS
    window = Window(
        0,
        full.row_off - margin,
        haz.width,
        full.height + 2 * margin,
    )
    whole = Window(0, 0, haz.width, haz.height)
    try:
        return window.intersection(whole).round_offsets().round_lengths()
    except rasterio.errors.WindowError:
        return None


def _population_only(pop, pop_window: Window, admin: gpd.GeoDataFrame):
    """Cells and people per unit inside one window, with no hazard involved.

    For the windows the hazard does not reach. Those cells carry no exposure,
    but they are still part of their units, and they belong in BOTH denominators
    the figure is built on: `cells_counted`, which divides the coverage, and the
    unit's total population, which divides the extrapolation. Dropping them made
    both depend on the window count - measured at a 3x spread on the headline
    figure before this existed.

    What a skipped window does NOT contribute is `pop_observed`: nothing was
    looked at there, which is exactly what makes the coverage below 1.
    """
    people = pop.read(1, masked=True, window=pop_window).filled(0)
    stats = zonal_stats(
        admin.to_crs(pop.crs),
        people.astype("float64"),
        affine=pop.window_transform(pop_window),
        stats=["count", "sum"],
        nodata=-1.0,
        all_touched=False,
    )
    counts = pd.Series(
        [s["count"] or 0 for s in stats], index=admin.index, dtype="float64"
    )
    totals = pd.Series(
        [s["sum"] or 0.0 for s in stats], index=admin.index, dtype="float64"
    )
    return counts, totals


def protection_path() -> str:
    """A GDAL `zip://` URI for the JRC flood protection standards raster."""
    if not PROTECTION_ZIP.exists():
        raise SystemExit(
            f"{PROTECTION_ZIP.relative_to(ROOT)} is missing: fetch the "
            "`jrc_flood_protection_standards` entry of config/sources.yaml "
            "with src.fetch.fetch_source."
        )
    with zipfile.ZipFile(PROTECTION_ZIP) as archive:
        tifs = [n for n in archive.namelist() if n.lower().endswith(".tif")]
    if len(tifs) != 1:
        raise SystemExit(f"Expected exactly one .tif in {PROTECTION_ZIP.name}, found {tifs}")
    return f"zip://{PROTECTION_ZIP.as_posix()}!/{tifs[0]}"


def protected_cells(band_shape, band_transform, band_crs, protection, return_period: int):
    """Hazard cells the local defences hold at this return period.

    The JRC protection standard of a cell is the return period its defences are
    designed for, so in a 1-in-`return_period` flood the cell stays dry when
    that standard is at least `return_period`. The 500 m standards are read onto
    the hazard window by NEAREST neighbour: a standard is a category of the
    place, and averaging a 1-in-50 cell with a 1-in-1000 one invents a dyke
    nobody built. Cells the standards raster does not cover read -1 and are
    never protected, which leaves the figure an upper bound there.
    """
    standards = np.full(band_shape, -1.0, dtype="float32")
    reproject(
        source=rasterio.band(protection, 1),
        destination=standards,
        src_transform=protection.transform,
        src_crs=protection.crs,
        src_nodata=protection.nodata,
        dst_transform=band_transform,
        dst_crs=band_crs,
        dst_nodata=-1.0,
        resampling=Resampling.nearest,
    )
    return standards >= return_period


def _exposure_one_period(
    hazard_path: str,
    pop_path: str,
    admin: gpd.GeoDataFrame,
    *,
    stripes: int,
    min_depth_m: float,
    mode: str,
    masks: list[str],
    protection: str | None = None,
    return_period: int | None = None,
) -> pd.DataFrame:
    """`exposed_pop`, `hazard_coverage` and `cells_counted` for one return period.

    Accumulated over windows of the population grid. Three running totals, and
    which one is summed matters:

    * `exposed` sums `exposed_pop_observed`, the figure with no extrapolation in
      it. Summing `exposed_pop` instead applies the extrapolation once per
      window, which is the bug this replaced.
    * `cells` sums `cells_counted`, because the windows are disjoint. It was a
      running maximum when the hazard was striped, since every stripe then saw
      every population cell.
    * `covered` sums `hazard_coverage * cells_counted`, so a unit's coverage is
      the cell-weighted mean over its windows rather than a mean of means, which
      would weight a window holding three cells like one holding three thousand.

    `masks` are rasters on the hazard grid flagging cells with 1.0; a flagged
    cell is set to the hazard's own nodata before being measured, so it leaves
    both the exposed count and the coverage denominator. Read per window, never
    whole: each mask is the same 5.7-billion-cell grid.

    `protection`, when given, is the flood protection standards raster: every
    cell its defences hold at `return_period` is set to the hazard's nodata,
    which this layer reads as dry - observed, nobody exposed - so the coverage
    does not move and only the exposed count does.
    """
    if protection is not None and return_period is None:
        raise ValueError("a protected run needs the return period it is masked at")
    windows = _stripes(pop_path, stripes)
    exposed = pd.Series(0.0, index=admin.index)
    covered = pd.Series(0.0, index=admin.index)
    cells = pd.Series(0.0, index=admin.index)
    looked_at = pd.Series(0.0, index=admin.index)
    everyone = pd.Series(0.0, index=admin.index)

    with ExitStack() as stack:
        src = stack.enter_context(rasterio.open(hazard_path))
        pop = stack.enter_context(rasterio.open(pop_path))
        nodata = src.nodata
        mask_sources = [stack.enter_context(rasterio.open(HAZARD_DIR / m)) for m in masks]
        protection_src = (
            stack.enter_context(rasterio.open(protection)) if protection else None
        )
        for mask_src in mask_sources:
            if mask_src.shape != src.shape or mask_src.transform != src.transform:
                raise SystemExit(
                    f"{Path(mask_src.name).name} is not on the hazard grid "
                    f"({mask_src.shape} vs {src.shape}); masking it per window "
                    "would misalign every cell."
                )
        for n, window in enumerate(windows, start=1):
            haz_window = _hazard_window(src, pop, window)
            if haz_window is None or haz_window.width < 1 or haz_window.height < 1:
                # The window's population cells still BELONG to their units, and
                # `cells` is the denominator of `coverage` below. Skipping them
                # entirely made a unit split between a covered and an uncovered
                # window report a coverage of 0.75 where the truth was 0.25, and
                # made the headline figure depend on the window count - measured
                # at a 3x spread before this.
                skipped_cells, skipped_people = _population_only(pop, window, admin)
                cells = cells.add(skipped_cells)
                everyone = everyone.add(skipped_people)
                print(f"    window {n}/{len(windows)} - no hazard here", flush=True)
                continue
            band = src.read(1, window=haz_window)
            for mask_src in mask_sources:
                flagged = mask_src.read(1, window=haz_window)
                band[np.isfinite(flagged) & (flagged == 1.0)] = nodata
                del flagged
            if protection_src is not None:
                held = protected_cells(
                    band.shape, src.window_transform(haz_window), src.crs,
                    protection_src, return_period,
                )
                band[held] = nodata
                del held
            profile = dict(src.profile)
            profile.update(
                height=band.shape[0],
                width=band.shape[1],
                transform=src.window_transform(haz_window),
            )
            # The piece lives in GDAL's in-memory filesystem rather than on disk:
            # `exposed_population` takes a path, and writing temporary GeoTIFFs
            # for a nine-period build is pure I/O for no gain.
            with MemoryFile() as memfile:
                with memfile.open(**profile) as dst:
                    dst.write(band, 1)
                del band
                part = exposed_population(
                    memfile.name,
                    pop_path,
                    admin,
                    min_depth_m=min_depth_m,
                    mode=mode,
                    pop_window=window,
                )
            part_cells = pd.Series(part["cells_counted"].values, index=admin.index).fillna(0.0)
            exposed = exposed.add(
                pd.Series(part["exposed_pop_observed"].values, index=admin.index).fillna(0.0)
            )
            covered = covered.add(
                pd.Series(part["hazard_coverage"].values, index=admin.index).fillna(0.0)
                * part_cells
            )
            cells = cells.add(part_cells)
            looked_at = looked_at.add(
                pd.Series(part["pop_observed"].values, index=admin.index).fillna(0.0)
            )
            everyone = everyone.add(
                pd.Series(part["pop_total"].values, index=admin.index).fillna(0.0)
            )
            print(f"    window {n}/{len(windows)}", flush=True)

    coverage = covered.divide(cells.where(cells > 0))
    # Binary mode is NOT divided, exactly as `exposed_population` refuses to
    # divide it: it counts whole population cells and has never extrapolated.
    # Dividing it here made `--mode binary` through this script produce a figure
    # that was neither the binary number nor anything documented.
    if mode == "fraction":
        # The extrapolation onto unobserved ground, applied ONCE over the whole
        # unit, and weighted by PEOPLE rather than by cells - see
        # `exposed_population`. Where every populated cell was looked at this is
        # the identity, which is almost everywhere on a pan-European run.
        scaled = exposed.multiply(everyone).divide(looked_at.where(looked_at > 0))
    else:
        scaled = exposed
    frame = pd.DataFrame(
        {
            "cells_counted": cells.astype("int64"),
            "hazard_coverage": coverage,
            "exposed_pop": scaled,
        }
    )
    # A unit no window ever covered is NOT a measured zero.
    unmeasured = frame["hazard_coverage"].isna() | (frame["hazard_coverage"] <= 0)
    frame.loc[unmeasured, "exposed_pop"] = np.nan
    frame.loc[frame["cells_counted"] == 0, "hazard_coverage"] = np.nan
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-depth-m",
        type=float,
        default=DEFAULT_MIN_DEPTH_M,
        help=f"Depth above which a cell counts as flooded (default "
             f"{DEFAULT_MIN_DEPTH_M} m, the usual threshold for damage to "
             f"buildings). Pass 0 for the any-water upper bound.",
    )
    parser.add_argument(
        "--keep-permanent-water",
        action="store_true",
        help="Count the river channel, lakes and sea as flooded. They are patched "
             "into the depth rasters at 1.00 m, so they clear every threshold up "
             "to 0.5 m and inflate the count by ~14%% on the Benelux.",
    )
    parser.add_argument(
        "--keep-spurious-areas",
        action="store_true",
        help="Count the cells the JRC itself flags as modelling artefacts.",
    )
    parser.add_argument(
        "--mode",
        default="fraction",
        choices=("fraction", "binary"),
        help="How a partly flooded population cell is counted. 'fraction' is right "
             "at 1 km, where each population cell holds ~185 hazard cells.",
    )
    parser.add_argument(
        "--stripes",
        type=int,
        default=DEFAULT_STRIPES,
        help=f"Population-grid row windows per return period (default "
             f"{DEFAULT_STRIPES}). Raise it if the machine has less memory: the "
             "windows are disjoint, so the result does not depend on it.",
    )
    parser.add_argument(
        "--return-period",
        type=int,
        action="append",
        help="Build only this return period. Repeatable. Default: all nine.",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Recompute return periods already parked under data/processed/"
             "exposure_parts/ instead of reusing them.",
    )
    parser.add_argument(
        "--protection",
        action="store_true",
        help="Mask every cell the JRC flood protection standards hold at each "
             "return period and write the RESIDUAL exposure to "
             "data/processed/exposure_protected.parquet, never over exposure.parquet.",
    )
    parser.add_argument(
        "--no-indicators",
        dest="indicators",
        action="store_false",
        help="Skip the Eurostat join. The table then carries one vulnerability "
             "indicator, and a weighted mean of one column is that column.",
    )
    args = parser.parse_args()

    paths = hazard_paths()
    if args.return_period:
        missing = sorted(set(args.return_period) - set(paths))
        if missing:
            raise SystemExit(f"No raster for return period(s) {missing}; have {sorted(paths)}")
        paths = {rp: paths[rp] for rp in args.return_period}

    admin = boundaries()
    pop_path = population_path()
    print(f"{len(admin)} NUTS3 units in {EXPECTED_BOUNDARY_CRS}")
    print(f"return periods: {sorted(paths)}")
    masks = []
    if not args.keep_permanent_water:
        masks.append(PERMANENT_WATER)
    if not args.keep_spurious_areas:
        masks.append(SPURIOUS_AREAS)
    print(f"mode={args.mode} min_depth_m={args.min_depth_m} stripes={args.stripes}")
    print(f"masked out: {', '.join(masks) if masks else 'nothing'}")

    protection = protection_path() if args.protection else None
    out = PROTECTED_OUT if protection else OUT
    print(f"flood protection standards: {'applied' if protection else 'not applied'} -> {out.name}")

    print("counting residents per unit...", flush=True)
    totals = total_population(pop_path, admin)

    PARTS.mkdir(parents=True, exist_ok=True)
    frames = []
    for return_period in sorted(paths):
        parked = _part_path(
            return_period, mode=args.mode, min_depth_m=args.min_depth_m, masks=masks,
            protected=protection is not None,
        )
        if parked.exists() and not args.rebuild:
            frames.append(pd.read_parquet(parked))
            print(f"  RP{return_period} already built, reusing {parked.name}", flush=True)
            continue
        started = time.monotonic()
        print(f"  RP{return_period}", flush=True)
        part = _exposure_one_period(
            paths[return_period], pop_path, admin,
            stripes=args.stripes, min_depth_m=args.min_depth_m, mode=args.mode,
            masks=masks, protection=protection, return_period=return_period,
        )
        frame = pd.DataFrame({
            "nuts_id": admin["nuts_id"].values,
            "region": admin["region"].values,
            "country": admin["country"].values,
            # The code stays for joins; the name is what a reader needs. An
            # unmapped code falls back to itself rather than to an empty cell.
            "country_name": [
                COUNTRY_NAMES.get(c, c) for c in admin["country"].values
            ],
            "total_pop": totals.values,
            "cells_counted": part["cells_counted"].values,
            "hazard_coverage": part["hazard_coverage"].values,
            "exposed_pop": part["exposed_pop"].values,
            "return_period": return_period,
            # Annual exceedance probability: a 100-year flood has a 1% chance per
            # year. Carried per row so nobody has to remember the inversion.
            "annual_probability": 1.0 / return_period,
        })
        # Parked BEFORE the next period starts: that is the whole point.
        frame.to_parquet(parked, index=False)
        frames.append(frame)
        print(
            f"  RP{return_period} done in {time.monotonic() - started:.0f} s "
            f"-> {parked.name}",
            flush=True,
        )

    # Assembled from every part parked under THESE parameters, not only from the
    # periods this run was asked for. `--return-period` narrows what gets
    # computed; it must not narrow the frozen table, or a targeted rebuild of one
    # period would silently replace a nine-period table with a one-period one that
    # looks complete to every reader of `exposure.parquet`.
    tag = _part_path(
        0, mode=args.mode, min_depth_m=args.min_depth_m, masks=masks,
        protected=protection is not None,
    ).name
    suffix = tag.split("_", 1)[1]
    parked = sorted(
        PARTS.glob(f"rp*_{suffix}"),
        key=lambda path: int(path.name.split("_", 1)[0][2:]),
    )
    frames = [pd.read_parquet(path) for path in parked]
    if not frames:
        raise SystemExit(f"No parts under {PARTS.relative_to(ROOT)} to assemble.")
    print(
        f"assembling {len(frames)} return period(s): "
        f"{[int(f['return_period'].iloc[0]) for f in frames]}"
    )
    table = pd.concat(frames, ignore_index=True)

    # Joined once onto the finished table rather than inside the return-period
    # loop: these are properties of the PEOPLE in a region and do not move with
    # the flood, so computing them per period would repeat one lookup nine times
    # and put nine identical copies in front of anyone tempted to average them.
    #
    # Not optional in spirit. Without it the table carries exactly one column
    # `vulnerability_indicators` will offer, the composite index is a weighted
    # mean of one thing, and `sensitivity` certifies every region "robust"
    # because rescaling a single term never reorders it. `demographics` raises rather than returning an empty frame, so
    # an unreachable Eurostat stops the build instead of producing a ranking
    # built on fewer axes than the brief will claim.
    if args.indicators:
        print("joining Eurostat vulnerability indicators...", flush=True)
        extra = demographics.vulnerability_indicators(admin["nuts_id"].values)
        table = table.merge(
            extra.reset_index(), on="nuts_id", how="left", validate="many_to_one"
        )
        for column in ("share_over_65", "poverty_rate_pct"):
            print(f"  {column}: {int(table[column].notna().sum())} of {len(table)} rows")
    else:
        print("indicators: SKIPPED (--no-indicators), one indicator in the table")

    out.parent.mkdir(parents=True, exist_ok=True)
    # Written beside the target and renamed, so a crash mid-write cannot leave
    # the UIs reading half a table.
    partial = out.with_suffix(".parquet.part")
    table.to_parquet(partial, index=False)
    partial.replace(out)

    print(f"\n{len(table)} rows -> {out.relative_to(ROOT)} ({out.stat().st_size:,} B)")
    cov = table["hazard_coverage"]
    print(
        f"hazard_coverage: min {cov.min():.3f}, mean {cov.mean():.3f}, "
        f"{int((cov < 0.999).sum())} of {len(table)} rows below 0.999"
    )
    print(f"exposed_pop unmeasured (no hazard coverage at all): {int(table['exposed_pop'].isna().sum())} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
