"""Observed trend in annual peak river discharge, per region, from HERA v2.

The kit's climate layer says how flood discharge is PROJECTED to change; this
one says how it HAS changed. The source is `hera_river_discharge` in
config/sources.yaml: the JRC Hydrological European ReAnalysis v2, LISFLOOD
forced by downscaled ERA5-Land with dynamic land use and reservoirs, 6-hourly
discharge on the 1 arcmin EFAS grid, one 2.3 GB NetCDF per year. The kit reads
1991-2020, the last thirty years the reanalysis covers.

Per river cell: the annual maximum of each year, then Sen's slope (the median of
every pairwise slope) and the Mann-Kendall test over the years available. Per
NUTS3 region: the median trend over its river cells as percent per decade, the
share of river cells with a significant upward trend, and how many years and
cells that rests on.

The design follows from four properties of the data.

**A year is 78 GB once decompressed.** 1,460 time steps of a 2970 x 4530 float32
field. So no year is ever loaded: `annual_extremes` walks the file in blocks
aligned to its own chunks, each chunk read once, under `BLOCK_BYTES` per read,
and keeps only a running maximum, sum and count per cell. The result - an annual
maximum and an annual mean per cell, float32 - goes to a small cache in
`data/processed/hera_cache/`, so the trend never reopens a 2.3 GB file.

**River cells are chosen by flow, not by "has a value".** HERA publishes
discharge for rivers over 100 km2 upstream; a cell counts as a river here when
its long-term mean discharge reaches `MIN_MEAN_DISCHARGE` (1 m3/s). That is
roughly what a 100 km2 temperate catchment yields - 300 mm of runoff a year over
100 km2 is 0.95 m3/s - so the filter keeps the rivers the reanalysis is built
for and drops the ditches and intermittent channels where a relative trend is a
division by almost nothing.

**A trend in percent of the cell's own peak.** A slope in m3/s per year ranks
the Rhine above every tributary whatever happens to them. Each cell's Sen slope
is divided by its median annual maximum before any aggregation, so the regional
median compares like with like: a river whose peak rises 10% a decade counts the
same whether it carries 20 or 2,000 m3/s.

**Medians, never means.** The same rule as `src/climate.py`: a relative change on
a small river is unbounded, and a mean would belong to it.

**Seasonality, kept because the timing of floods is moving in Europe.** Beside
the annual maximum, each year's cache keeps the day of that maximum, the
largest flow of the winter half (October-March) and of the summer half
(April-September), and the number of days above the cell's 1-in-2-year flow
(the EFAS v5.1 return level, on the same 1 arcmin grid - about bankfull). Per
region that gives: the share of years whose peak falls in winter, the shift of
the peak's date in days per decade, the trends of the winter and summer peaks separately, and the trend
in flood days. All are medians over the region's river cells, as above.

**Peak timing on a circle.** A date has no start: whichever day the year is cut
at, a river whose peaks straddle it jumps by 365 days and its slope is an
artefact. Each cell's peaks are read as angles; their circular mean is the
cell's typical date, and each year counts as its signed distance from that
date, within half a year. The Sen slope is taken on those distances. The
resultant length R (1 when every peak falls on one day, near 0 when they are
spread over the year) must reach `MIN_TIMING_CONCENTRATION`; below it the cell
has no typical date to drift from and its timing trend is NaN, not 0.

Caveat: HERA is a model forced by a reanalysis, not gauged flow. The trend is
the model's, and 30 years of annual maxima detect a trend only where it is
strong - a non-significant cell is not a cell without change.
"""

from __future__ import annotations

import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
HERA_DIR = DATA / "raw" / "download" / "hera_river_discharge"
CACHE_DIR = DATA / "processed" / "hera_cache"

YEARS = tuple(range(1991, 2021))
FILE_NAME = "dis.HERA_v2_{year}.nc"
_YEAR = re.compile(r"^dis\.HERA_v2_(\d{4})\.nc$")

#: Long-term mean discharge a cell needs to count as a river, m3/s. See the
#: module docstring for why 1 m3/s stands for HERA's 100 km2 upstream rule.
MIN_MEAN_DISCHARGE = 1.0

#: Fewer years than this and there is no trend to speak of: the Mann-Kendall
#: test cannot reach 5% significance below about eight points at all.
MIN_YEARS = 10

#: Upper bound on one read, bytes. A block is a whole number of the file's own
#: chunks, so each compressed chunk is decompressed once; 512 MiB keeps a whole
#: year's pass far under the 4 GB this machine can spare beside a continental run.
BLOCK_BYTES = 512 * 2**20

#: Two-sided 5% critical value of the standard normal.
MK_Z_5PCT = 1.959963984540054

#: Resultant length of a cell's peak dates below which its timing trend is NaN.
#: 0.5 is a circular standard deviation of about 69 days: peaks spread wider
#: than a season have no date to drift from.
MIN_TIMING_CONCENTRATION = 0.5

#: Cells per block in the pairwise trend computation; 435 pairs for 30 years.
TREND_BLOCK = 50_000

POINT_CRS = "EPSG:4326"

COLUMNS = (
    "hera_peak_trend_pct_per_decade",
    "hera_cells_increasing_share",
    "hera_years",
    "hera_river_cells",
    "hera_winter_peak_share",
    "hera_peak_timing_shift_days_per_decade",
    "hera_winter_peak_trend_pct_per_decade",
    "hera_summer_peak_trend_pct_per_decade",
    "hera_flood_days_per_year",
    "hera_flood_days_trend_per_decade",
)

#: Months of the winter half-year; the rest is summer. October to March is the
#: hydrological winter used across European flood-seasonality studies.
WINTER_MONTHS = (10, 11, 12, 1, 2, 3)

#: The cache layout version: caches without it predate the seasonal fields and
#: are recomputed rather than read with fields missing.
CACHE_SCHEMA = 2

#: The 1-in-2-year return level used as the flood-day threshold.
THRESHOLD_FILE = DATA / "raw" / "download" / "efas_flood_thresholds" / "flood_threshold_efas_v5.1_rl_2.0.nc"

_LAT_NAMES = ("lat", "latitude", "y")
_LON_NAMES = ("lon", "longitude", "x")


def year_of(path: str | Path) -> int:
    """The year a HERA discharge file covers, from its name."""
    match = _YEAR.match(Path(path).name)
    if not match:
        raise ValueError(f"{Path(path).name} is not a dis.HERA_v2_YYYY.nc file.")
    return int(match.group(1))


def discharge_variable(ds, name: str | None = None):
    """The discharge DataArray: `name` if given, `dis` if present, else the one 3-D variable.

    `dis` is what the file name says the variable is; the fallback is there
    because the name inside the file is unverified until a full year is on disk.
    """
    if name is not None:
        return ds[name]
    if "dis" in ds.data_vars:
        return ds["dis"]
    three_d = [k for k, v in ds.data_vars.items() if v.ndim == 3]
    if len(three_d) != 1:
        raise ValueError(
            f"Expected `dis` or one 3-D variable, found {list(ds.data_vars)}. "
            f"Pass the variable name."
        )
    return ds[three_d[0]]


def _dims(da) -> tuple[str, str, str]:
    """(time, lat, lon) dimension names of a 3-D discharge array."""
    lat = next((d for d in da.dims if d in _LAT_NAMES), None)
    lon = next((d for d in da.dims if d in _LON_NAMES), None)
    others = [d for d in da.dims if d not in (lat, lon)]
    if lat is None or lon is None or len(others) != 1:
        raise ValueError(f"`{da.name}` has dimensions {da.dims}; expected (time, lat, lon).")
    return others[0], lat, lon


def plan_blocks(
    shape: tuple[int, int, int],
    chunks: tuple[int, int, int] | None,
    itemsize: int,
    budget: int = BLOCK_BYTES,
) -> tuple[int, int, int]:
    """Block size (time steps, rows, columns) for a chunk-aligned walk under `budget`.

    Every block is a whole number of chunks along each axis, so no chunk is
    decompressed twice. The spatial tile is widened first (full rows, then full
    plane), and only a full plane is stacked over several time chunks: with a
    tile, the walk loops over time inside it, which reads each chunk once
    anyway. A contiguous variable (`chunks` None) is treated as chunked one time
    step at a time, its natural layout. One chunk is the minimum, even above
    the budget, because nothing smaller can be read without decompressing it.
    """
    nt, nr, nc = shape
    ct, cr, cc = chunks if chunks else (1, nr, nc)
    ct, cr, cc = min(ct, nt), min(cr, nr), min(cc, nc)
    per_row = ct * cr * itemsize
    cols = nc if per_row * nc <= budget else cc * max(1, budget // (per_row * cc))
    cols = min(cols, nc)
    rows = cr * max(1, budget // (ct * cr * cols * itemsize))
    rows = min(rows, nr)
    steps = ct
    if rows == nr and cols == nc:
        steps = min(nt, ct * max(1, budget // (ct * nr * nc * itemsize)))
    return steps, rows, cols


def _calendar(times, nt: int):
    """(month, day of year) of each time step.

    Real HERA files carry datetimes; a file with a bare step index (the test
    fixtures) is read as 6-hourly steps from 1 January of a non-leap year.
    """
    values = np.asarray(times)
    if np.issubdtype(values.dtype, np.datetime64):
        stamps = pd.DatetimeIndex(values)
    else:
        stamps = pd.Timestamp("2001-01-01") + pd.to_timedelta(np.arange(nt) * 6, unit="h")
    return stamps.month.to_numpy(), stamps.dayofyear.to_numpy()


def flood_threshold(lat, lon, path=THRESHOLD_FILE):
    """The 1-in-2-year return level on the HERA grid, or None if absent or misaligned.

    Aligned to within half a cell or not used at all: a threshold one cell off
    would compare a river with its neighbour's bank.
    """
    import xarray as xr

    path = Path(path)
    if not path.exists():
        return None
    with xr.open_dataset(path) as ds:
        da = ds[next(iter(ds.data_vars))]
        tlat = da[next(d for d in da.dims if d in _LAT_NAMES)].values
        tlon = da[next(d for d in da.dims if d in _LON_NAMES)].values
        if tlat.shape != np.shape(lat) or tlon.shape != np.shape(lon):
            return None
        if np.max(np.abs(tlat - lat)) > 1 / 120 or np.max(np.abs(tlon - lon)) > 1 / 120:
            return None
        return np.asarray(da.values, dtype="float32")


def annual_extremes(
    path: str | Path,
    *,
    variable: str | None = None,
    budget: int = BLOCK_BYTES,
    progress=None,
    threshold: np.ndarray | None = None,
):
    """The annual maximum and annual mean of one year's discharge, per cell.

    Returns an `xarray.Dataset` on `(lat, lon)` with float32 `annual_max`,
    `annual_mean`, `winter_max` and `summer_max`, int16 `peak_doy` (day of year
    of the annual maximum, 0 where none) and float32 `days_above_threshold`
    (6-hourly steps above `threshold`, divided by 4; NaN without a threshold),
    and the number of time steps read in `attrs["time_steps"]`.

    Streams: the file is opened lazily (no dask needed: xarray's lazy indexing
    reads only the requested slice) and walked in chunk-aligned blocks from
    `plan_blocks`. Memory is one block plus three full-grid accumulators, about
    0.75 GB on the full EFAS grid. A cell that is NaN at every step stays NaN in
    both outputs - outside the domain is not a river with no flow.
    """
    import xarray as xr

    with xr.open_dataset(path, mask_and_scale=True, cache=False) as ds:
        da = discharge_variable(ds, variable)
        tdim, ldim, cdim = _dims(da)
        # `chunksizes` follows the on-disk dimension order, so it is read
        # against `da.dims` before the transpose puts time first.
        stored = da.encoding.get("chunksizes")
        chunks = None
        if stored is not None:
            by_dim = dict(zip(da.dims, (int(c) for c in stored)))
            chunks = (by_dim[tdim], by_dim[ldim], by_dim[cdim])
        da = da.transpose(tdim, ldim, cdim)
        nt, nr, nc = da.shape
        steps, rows, cols = plan_blocks((nt, nr, nc), chunks, 4, budget)
        month, doy = _calendar(ds[tdim].values, nt)
        winter = np.isin(month, WINTER_MONTHS)
        peak_doy = np.zeros((nr, nc), dtype="int16")
        winter_max = np.full((nr, nc), np.nan, dtype="float32")
        summer_max = np.full((nr, nc), np.nan, dtype="float32")
        above = np.zeros((nr, nc), dtype="int32")
        peak = np.full((nr, nc), np.nan, dtype="float32")
        total = np.zeros((nr, nc), dtype="float64")
        count = np.zeros((nr, nc), dtype="int32")
        tiles = [(r, c) for r in range(0, nr, rows) for c in range(0, nc, cols)]
        done = 0
        for r0, c0 in tiles:
            rs, cs = slice(r0, r0 + rows), slice(c0, c0 + cols)
            for t0 in range(0, nt, steps):
                block = np.asarray(
                    da.isel({tdim: slice(t0, t0 + steps), ldim: rs, cdim: cs}).values,
                    dtype="float32",
                )
                filled = np.where(np.isfinite(block), block, -np.inf)
                block_peak = filled.max(axis=0)
                block_when = doy[t0 + filled.argmax(axis=0)].astype("int16")
                newer = block_peak > np.nan_to_num(peak[rs, cs], nan=-np.inf)
                peak[rs, cs] = np.where(newer, block_peak, peak[rs, cs])
                peak_doy[rs, cs] = np.where(newer, block_when, peak_doy[rs, cs])
                in_winter = winter[t0:t0 + block.shape[0]]
                if in_winter.any():
                    winter_max[rs, cs] = np.fmax(winter_max[rs, cs],
                                                 np.fmax.reduce(block[in_winter], axis=0))
                if (~in_winter).any():
                    summer_max[rs, cs] = np.fmax(summer_max[rs, cs],
                                                 np.fmax.reduce(block[~in_winter], axis=0))
                if threshold is not None:
                    above[rs, cs] += (block > threshold[rs, cs]).sum(axis=0, dtype="int32")
                finite = np.isfinite(block)
                total[rs, cs] += np.where(finite, block, 0.0).sum(axis=0, dtype="float64")
                count[rs, cs] += finite.sum(axis=0, dtype="int32")
                done += 1
                if progress is not None:
                    progress(done, len(tiles) * -(-nt // steps))
        mean = np.where(count > 0, total / np.maximum(count, 1), np.nan).astype("float32")
        if threshold is not None:
            days = (above / 4.0).astype("float32")
        else:
            days = np.full((nr, nc), np.nan, dtype="float32")
        days[~np.isfinite(peak)] = np.nan
        if threshold is not None:
            # No return level at a cell is "not measured", not zero flood days.
            days[~np.isfinite(threshold)] = np.nan
        out = xr.Dataset(
            {
                "annual_max": (("lat", "lon"), peak),
                "annual_mean": (("lat", "lon"), mean),
                "peak_doy": (("lat", "lon"), peak_doy),
                "winter_max": (("lat", "lon"), winter_max),
                "summer_max": (("lat", "lon"), summer_max),
                "days_above_threshold": (("lat", "lon"), days),
            },
            coords={"lat": ds[ldim].values, "lon": ds[cdim].values},
            attrs={"time_steps": int(nt), "units": str(da.attrs.get("units", "")),
                   "schema": CACHE_SCHEMA,
                   "threshold": "efas_v5.1_rl_2.0" if threshold is not None else ""},
        )
    return out


def expected_steps(year: int) -> int:
    """6-hourly steps in a full calendar year: 1,460, or 1,464 in a leap year."""
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 4 * (366 if leap else 365)


def cache_path(year: int, cache_dir: str | Path | None = None) -> Path:
    """Where one year's annual maximum and mean are cached."""
    return Path(CACHE_DIR if cache_dir is None else cache_dir) / f"annual_{year}.nc"


def cache_year(
    path: str | Path,
    cache_dir: str | Path | None = None,
    *,
    variable: str | None = None,
    budget: int = BLOCK_BYTES,
    progress=None,
) -> Path:
    """Compute one year's extremes and write them to the cache; skip if current.

    The cache records the source file's size and refuses to be reused against a
    different one, so a year re-downloaded after a truncated transfer is
    recomputed rather than served from the truncated version. A file whose time
    axis is shorter than the calendar year raises instead of being cached: a
    still-downloading file that happens to open would otherwise be a year of
    maxima missing its autumn.
    """
    import xarray as xr

    path = Path(path)
    year = year_of(path)
    target = cache_path(year, cache_dir)
    size = path.stat().st_size
    if target.exists():
        with xr.open_dataset(target) as cached:
            if (int(cached.attrs.get("source_bytes", -1)) == size
                    and int(cached.attrs.get("schema", 1)) >= CACHE_SCHEMA):
                return target
    with xr.open_dataset(path) as ds:
        steps = discharge_variable(ds, variable).sizes[_dims(discharge_variable(ds, variable))[0]]
    if steps < expected_steps(year):
        raise ValueError(
            f"{path.name} holds {steps} time steps, a full {year} has "
            f"{expected_steps(year)}. Incomplete file; not cached."
        )
    with xr.open_dataset(path) as ds:
        da = discharge_variable(ds, variable)
        _, ldim, cdim = _dims(da)
        threshold = flood_threshold(ds[ldim].values, ds[cdim].values)
    extremes = annual_extremes(path, variable=variable, budget=budget, progress=progress,
                               threshold=threshold)
    extremes.attrs.update(source=path.name, source_bytes=int(size), year=int(year))
    target.parent.mkdir(parents=True, exist_ok=True)
    encoding = {v: {"zlib": True, "complevel": 4} for v in extremes.data_vars}
    partial = target.with_name(target.name + ".part")
    extremes.to_netcdf(partial, encoding=encoding)
    partial.replace(target)
    return target


def _cached(years, cache_dir):
    """The years whose cache exists, and their shared (lat, lon)."""
    import xarray as xr

    present, lat, lon = [], None, None
    for year in years:
        target = cache_path(year, cache_dir)
        if not target.exists():
            continue
        with xr.open_dataset(target) as ds:
            if lat is None:
                lat, lon = ds["lat"].values, ds["lon"].values
            elif not (np.array_equal(ds["lat"].values, lat) and np.array_equal(ds["lon"].values, lon)):
                raise ValueError(f"{target.name} is on a different grid from the other years.")
        present.append(year)
    return present, lat, lon


FIELDS = ("annual_max", "peak_doy", "winter_max", "summer_max", "days_above_threshold")


def river_fields(years, cache_dir=None, *, min_mean_discharge: float = MIN_MEAN_DISCHARGE):
    """Every cached field of the river cells: `(years, {field: (n_years, n_cells)}, lat, lon)`.

    Two passes over the cache, one year in memory at a time. The first averages
    the annual means into a long-term mean and picks the river cells; the
    second keeps only those cells of each field. A cell missing in any year is
    dropped: a trend over the years a cell happens to have is a trend over a
    different period from its neighbours'. A field absent from any year's cache
    (an older schema) is left out of the dict, so its columns come out NaN
    rather than the run failing or mixing two layouts.
    """
    import xarray as xr

    years, lat, lon = _cached(years, cache_dir)
    if not years:
        return [], {"annual_max": np.empty((0, 0), "float32")}, np.empty(0), np.empty(0)
    total = np.zeros((lat.size, lon.size), dtype="float64")
    complete = np.ones((lat.size, lon.size), dtype=bool)
    present = set(FIELDS)
    for year in years:
        with xr.open_dataset(cache_path(year, cache_dir)) as ds:
            mean = ds["annual_mean"].values
            peak = ds["annual_max"].values
            present &= set(ds.data_vars)
        complete &= np.isfinite(mean) & np.isfinite(peak)
        total += np.nan_to_num(mean, nan=0.0)
    river = complete & (total / len(years) >= min_mean_discharge)
    rows, cols = np.nonzero(river)
    names = [name for name in FIELDS if name in present]
    fields = {name: np.empty((len(years), rows.size), dtype="float32") for name in names}
    for i, year in enumerate(years):
        with xr.open_dataset(cache_path(year, cache_dir)) as ds:
            for name in names:
                fields[name][i] = ds[name].values[rows, cols]
    return years, fields, lat[rows], lon[cols]


def river_stack(years, cache_dir=None, *, min_mean_discharge: float = MIN_MEAN_DISCHARGE):
    """The annual maxima of the river cells, `(n_years, n_cells)`, and where they are.

    The annual-maximum slice of `river_fields`, kept for callers that need only it.
    """
    years, fields, lat, lon = river_fields(years, cache_dir, min_mean_discharge=min_mean_discharge)
    return years, fields["annual_max"], lat, lon


def sen_slope(stack: np.ndarray, years) -> np.ndarray:
    """Per column of `stack`, the median of every pairwise slope (Sen, 1968).

    Uses the actual years as x, so a gap in the record is a longer interval and
    not a missing point that shifts every later year by one.
    """
    x = np.asarray(years, dtype="float64")
    i, j = np.triu_indices(x.size, k=1)
    dx = (x[j] - x[i])[:, None]
    out = np.empty(stack.shape[1], dtype="float64")
    for start in range(0, stack.shape[1], TREND_BLOCK):
        block = stack[:, start:start + TREND_BLOCK].astype("float64")
        out[start:start + TREND_BLOCK] = np.median((block[j] - block[i]) / dx, axis=0)
    return out


def mann_kendall_z(stack: np.ndarray) -> np.ndarray:
    """Per column, the Mann-Kendall Z statistic with the continuity correction.

    The variance is the no-ties formula n(n-1)(2n+5)/18. Annual maxima of a
    river with at least 1 m3/s mean flow are continuous values and tie with
    probability nil, so the tie correction would change nothing measurable here.
    """
    n = stack.shape[0]
    i, j = np.triu_indices(n, k=1)
    var = n * (n - 1) * (2 * n + 5) / 18.0
    out = np.empty(stack.shape[1], dtype="float64")
    for start in range(0, stack.shape[1], TREND_BLOCK):
        block = stack[:, start:start + TREND_BLOCK].astype("float64")
        s = np.sign(block[j] - block[i]).sum(axis=0)
        out[start:start + TREND_BLOCK] = (s - np.sign(s)) / np.sqrt(var)
    return out


def _pct_per_decade(stack: np.ndarray, years, slope: np.ndarray | None = None) -> np.ndarray:
    """Sen slope as % of the cell's median per decade; NaN where the median is not positive."""
    if slope is None:
        slope = sen_slope(stack, years)
    typical = np.median(stack, axis=0).astype("float64")
    usable = typical > 0
    return np.where(usable, slope / np.where(usable, typical, 1.0) * 10 * 100, np.nan)


def _timing_shift_per_decade(peak_doy: np.ndarray, years,
                              min_concentration: float = MIN_TIMING_CONCENTRATION) -> np.ndarray:
    """Per cell, the Sen slope of the peak's date in days per decade, read on a circle.

    Each year is its signed distance in days from the cell's circular mean
    date, in [-182.5, 182.5), so no cut point of the year enters the slope.
    NaN where the resultant length of the dates is below `min_concentration`.
    The 365-day circle leaves day 366 of a leap year on 1 January, a day of
    slack far below the shifts this measures.
    """
    doy = peak_doy.astype("float64")
    angle = 2 * np.pi * doy / 365
    sin, cos = np.sin(angle).mean(axis=0), np.cos(angle).mean(axis=0)
    concentration = np.hypot(sin, cos)
    mean_doy = np.arctan2(sin, cos) * 365 / (2 * np.pi)
    deviation = (doy - mean_doy + 182.5) % 365 - 182.5
    slope = sen_slope(deviation, years) * 10
    return np.where(concentration >= min_concentration, slope, np.nan)


def _third_change_per_decade(stack: np.ndarray, years) -> np.ndarray:
    """Per cell, mean of the last third of `years` minus the first, per decade.

    For counts that are 0 in most years, where a Sen slope is 0 by
    construction; on a linear series it equals the slope x 10.
    """
    years = np.asarray(years, dtype="float64")
    n = max(len(years) // 3, 1)
    gap = years[-n:].mean() - years[:n].mean()
    if gap <= 0:
        return np.full(stack.shape[1:], np.nan)
    return (stack[-n:].mean(axis=0) - stack[:n].mean(axis=0)) / gap * 10


def trends_by_region(
    admin: gpd.GeoDataFrame,
    lat: np.ndarray,
    lon: np.ndarray,
    stack: np.ndarray,
    years,
    fields: dict | None = None,
) -> pd.DataFrame:
    """The HERA columns per region, from river-cell annual maxima and `fields`.

    - `hera_peak_trend_pct_per_decade` - median over the region's river cells of
      Sen slope / median annual maximum x 10 x 100.
    - `hera_cells_increasing_share` - share of its river cells whose
      Mann-Kendall Z exceeds the two-sided 5% value with a positive slope.
    - `hera_years` - years the trend rests on.
    - `hera_river_cells` - river cells counted.

    From `fields` (the dict of `river_fields`), each left NaN when its field is
    absent:

    - `hera_winter_peak_share` - per cell, the share of years whose maximum
      fell in October-March (`winter_max == annual_max`, exact, no calendar
      round trip); region median.
    - `hera_peak_timing_shift_days_per_decade` - Sen slope of the peak's day
      as a distance from the cell's circular mean date, x 10; NaN for a cell
      whose dates have a resultant length below `MIN_TIMING_CONCENTRATION`, so
      a region whose cells are all spread over the year is NaN. A positive
      value is a later peak.
    - `hera_winter_peak_trend_pct_per_decade`, `hera_summer_peak_trend_pct_per_decade`
      - as the annual trend, on each half-year's maximum.
    - `hera_flood_days_per_year` - mean days above the 1-in-2-year flow;
      `hera_flood_days_trend_per_decade` - mean of the last third of the years
      minus the first third, per decade between their centres. Not a Sen
      slope: a river cell has no flood day in most years, so the median of its
      pairwise slopes is 0 in 99.4% of cells and every region read 0.

    All NaN for a region holding no river cell, whether it lies outside the
    HERA domain or inside it with no river over the threshold: telling the two
    apart would mean placing every land cell of the grid, and either way there
    is no river trend to report, which is not a trend of 0.
    """
    if admin.crs is None:
        raise ValueError("admin has crs=None; refusing to guess.")
    out = pd.DataFrame(np.nan, index=admin.index, columns=list(COLUMNS))
    if stack.size == 0:
        return out
    slope = sen_slope(stack, years)
    z = mann_kendall_z(stack)
    values = {
        "hera_peak_trend_pct_per_decade": _pct_per_decade(stack, years, slope),
        "hera_cells_increasing_share": ((z > MK_Z_5PCT) & (slope > 0)).astype("float64"),
    }
    fields = fields or {}
    if "winter_max" in fields:
        values["hera_winter_peak_share"] = (fields["winter_max"] >= stack).mean(axis=0)
        values["hera_winter_peak_trend_pct_per_decade"] = _pct_per_decade(fields["winter_max"], years)
    if "summer_max" in fields:
        values["hera_summer_peak_trend_pct_per_decade"] = _pct_per_decade(fields["summer_max"], years)
    if "peak_doy" in fields:
        values["hera_peak_timing_shift_days_per_decade"] = _timing_shift_per_decade(
            fields["peak_doy"], years)
    if "days_above_threshold" in fields:
        days = fields["days_above_threshold"].astype("float64")
        measured = np.isfinite(days).all(axis=0)
        values["hera_flood_days_per_year"] = np.where(measured, days.mean(axis=0), np.nan)
        values["hera_flood_days_trend_per_decade"] = np.where(
            measured, _third_change_per_decade(np.nan_to_num(days), years), np.nan)
    points = gpd.GeoDataFrame(
        values, geometry=gpd.points_from_xy(lon, lat), crs=POINT_CRS,
    ).to_crs(admin.crs)
    joined = gpd.sjoin(points, admin[["geometry"]], how="inner", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    grouped = joined.groupby("index_right")
    for column in values:
        if column == "hera_cells_increasing_share":
            out[column] = grouped[column].mean().reindex(admin.index)
        else:
            out[column] = grouped[column].median().reindex(admin.index)
    cells = grouped.size().reindex(admin.index)
    out["hera_river_cells"] = cells.astype("float64")
    out.loc[cells.notna().to_numpy(), "hera_years"] = float(len(years))
    return out


def downloaded(hera_dir: str | Path | None = None, years=YEARS) -> list[Path]:
    """The discharge files on disk for `years`, by their final name only."""
    directory = Path(HERA_DIR if hera_dir is None else hera_dir)
    return [directory / FILE_NAME.format(year=y) for y in years
            if (directory / FILE_NAME.format(year=y)).exists()]


def build_cache(hera_dir=None, cache_dir=None, years=YEARS, *, progress=print) -> list[str]:
    """Cache every downloaded year that is not cached yet; notes on what was skipped.

    A file that does not open, or opens with a short time axis, is skipped with
    a note: it is most likely still downloading.
    """
    notes = []
    for path in downloaded(hera_dir, years):
        try:
            cache_year(path, cache_dir)
        except Exception as exc:  # truncated HDF5, short year, unreadable file
            notes.append(f"{path.name} skipped ({type(exc).__name__}: {exc})")
            continue
        if progress is not None:
            progress(f"  cached {path.name}")
    return notes


def by_region(
    admin: gpd.GeoDataFrame,
    *,
    hera_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    years=YEARS,
    build: bool = True,
    min_years: int = MIN_YEARS,
    min_mean_discharge: float = MIN_MEAN_DISCHARGE,
) -> tuple[pd.DataFrame | None, str]:
    """The HERA trend columns per region, or None and the reason.

    Returns `(frame, note)` with `frame` indexed like `admin`, the shape of the
    `_built`/`_natura` helpers in scripts/build_context.py. With `build`, any
    downloaded year missing from the cache is cached first - about one full
    read of 2.3 GB per year; `python -m src.hera` does the same ahead of time.
    """
    try:
        import xarray  # noqa: F401
    except ImportError:
        return None, "xarray is not installed (pip install -r requirements.txt)"
    skipped = build_cache(hera_dir, cache_dir, years, progress=None) if build else []
    used, fields, lat, lon = river_fields(years, cache_dir, min_mean_discharge=min_mean_discharge)
    stack = fields["annual_max"]
    if len(used) < min_years:
        reason = f"{len(used)} cached HERA year(s), need at least {min_years}"
        return None, "; ".join([reason, *skipped])
    frame = trends_by_region(admin, lat, lon, stack, used, fields)
    measured = int(frame["hera_river_cells"].notna().sum())
    note = (
        f"HERA v2 {used[0]}-{used[-1]} ({len(used)} years), {stack.shape[1]:,} river "
        f"cells (mean >= {min_mean_discharge:g} m3/s), {measured} regions measured"
    )
    return frame, "; ".join([note, *skipped])


def main(argv=None) -> int:
    """Build the per-year cache from the files on disk: `python -m src.hera`."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--years", nargs="*", type=int, default=list(YEARS))
    args = parser.parse_args(argv)
    for note in build_cache(years=args.years):
        print(f"  {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
