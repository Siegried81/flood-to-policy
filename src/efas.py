"""July 2021 as a return period: the EFAS reanalysis peak against EFAS's own levels.

The kit's hazard maps say what a 1-in-100 flood would cover; they do not say
whether July 2021 WAS one. This module answers that with the JRC's own model:
the EFAS v5 reanalysis discharge for 1-31 July 2021 over a box around the Meuse,
the Vesdre and the Ahr (`efas_historical_july_2021` in config/sources.yaml),
read against the nine EFAS v5.1 return-level thresholds (`efas_flood_thresholds`,
1-in-1.5 to 1-in-500). Per river cell: the highest return level the July peak
went past. Per NUTS3 region: the highest level any of its river cells reached,
and how many went past the 1-in-100 level.

Four properties of the data decide the design.

**Every land cell has a threshold, so "has a threshold" is not "is a river".**
Measured 2026-10-24 on `flood_threshold_efas_v5.1_rl_2.0.nc`: 5,203,310 finite
cells on the 4530 x 2970 grid, a median 2-year flow of 0.27 m3/s and 73% of cells
under 1 m3/s - hillslopes and ditches, every one of which LISFLOOD routes. A
region's count of "cells over RP100" would be dominated by them. River cells are
therefore the cells whose upstream area reaches `MIN_UPSTREAM_KM2` (150 km2, the
catchment size the JRC river hazard maps start at), read from the EFAS static
`upstream_area` field fetched alongside the discharge.

**The peak is the maximum of 6-hourly means.** EWDS serves
`river_discharge_in_the_last_6_hours`, a mean over the preceding six hours, and
no maximum product. The July maximum of it sits slightly below the
instantaneous peak, so a return level read off it is, if anything, an
understatement.

**The two grids are matched by coordinate, never by shape.** The thresholds
cover the whole EFAS domain and the discharge a box the EWDS may adjust "slightly
such that the returned file will fully encompass the selection". Each discharge
cell is looked up at its own latitude and longitude in the thresholds and the
match must fall within half a cell, or the run stops: a one-row offset would put
every threshold one cell off the river.

**Outside the box is not measured, so it is NaN.** A region is measured only when
at least `MIN_BOX_SHARE` of its area lies inside the downloaded grid. A region
the box cuts in half would otherwise report half its rivers and read as a
calmer place than it was.

Caveat carried into every note: the thresholds are fitted to the EFAS v5.1 long
run, the reanalysis on EWDS is `version_5_0`. The CEMS wiki gives no fitting
period for EFAS v5.1; check it before quoting a return period in a brief.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

DATA = Path(__file__).resolve().parents[1] / "data"
THRESHOLD_DIR = DATA / "raw" / "download" / "efas_flood_thresholds"
JULY_DIR = DATA / "raw" / "download" / "efas_historical_july_2021"
DISCHARGE_FILE = "efas_v5_dis06_2021-07_meuse_ahr.nc"
UPSTREAM_FILE = "efas_v5_upstream_area.nc"

#: The nine return levels of `efas_flood_thresholds`, in years.
RETURN_LEVELS = (1.5, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0)

#: The EFAS v5 grid step, 1 arcmin. Half of it is the alignment tolerance.
CELL_DEG = 1.0 / 60.0

#: Smallest catchment counted as a river, km2. The JRC river flood hazard maps
#: start at 150 km2, so a river cell here is a river the hazard maps also draw.
MIN_UPSTREAM_KM2 = 150.0

#: Share of a region's area that must lie inside the downloaded box for the
#: region to be measured at all.
MIN_BOX_SHARE = 0.99

#: The admin polygons are reprojected nowhere; the cell centres, in degrees,
#: are reprojected to the admin frame's CRS before the join.
POINT_CRS = "EPSG:4326"

COLUMNS = (
    "efas_2021_max_rp_exceeded",
    "efas_2021_cells_over_rp100",
    "efas_2021_river_cells",
)

_LAT_NAMES = ("lat", "latitude", "y")
_LON_NAMES = ("lon", "longitude", "x")


def threshold_path(level: float, directory: Path | None = None) -> Path:
    """Where the threshold file for one return level is, by the CEMS file name."""
    directory = THRESHOLD_DIR if directory is None else Path(directory)
    return directory / f"flood_threshold_efas_v5.1_rl_{level:.1f}.nc"


def _spatial_dims(da) -> tuple[str, str]:
    """The (latitude, longitude) dimension names of a 2-D-or-more DataArray.

    Accepts the spellings the EFAS files use (`lat`/`lon` in the thresholds,
    `latitude`/`longitude` in an EWDS NetCDF conversion). A grid with 2-D
    coordinates - the EFAS v4 Lambert grid - has neither and is refused, because
    matching it to the 1 arcmin thresholds would be a reprojection, not a lookup.
    """
    lat = next((d for d in da.dims if d in _LAT_NAMES), None)
    lon = next((d for d in da.dims if d in _LON_NAMES), None)
    if lat is None or lon is None:
        raise ValueError(
            f"`{da.name}` has dimensions {da.dims}; expected a regular latitude/"
            f"longitude grid (one of {_LAT_NAMES} and one of {_LON_NAMES})."
        )
    return lat, lon


def _variable(ds, name: str | None = None):
    """The one data variable laid out on the lat/lon grid, or `name` if given.

    Picked by layout rather than by name, because the threshold files name it
    after the level (`rl_2.0`, `rl_100.0`: one float32 `(lat, lon)` variable per
    file, NaN as nodata, no CRS attribute - degrees on the EFAS grid, measured
    2026-10-24) and the EWDS conversion after the GRIB short name (`dis06`,
    unverified until the first real download).
    """
    if name is not None:
        return ds[name]
    gridded = []
    for key, da in ds.data_vars.items():
        try:
            _spatial_dims(da)
        except ValueError:
            continue
        gridded.append(key)
    if len(gridded) != 1:
        raise ValueError(
            f"Expected exactly one gridded variable, found {gridded} among "
            f"{list(ds.data_vars)}. Pass the variable name."
        )
    return ds[gridded[0]]


def peak_discharge(path: str | Path, variable: str | None = None):
    """The maximum over every time step of one discharge file, as a (lat, lon) array.

    Reduces over whatever is not latitude or longitude - `time`, `valid_time`,
    `step` - so the read does not depend on how the GRIB-to-NetCDF conversion
    laid out the time axis. The box is about 30 MB for all of July, so it is
    loaded whole.
    """
    import xarray as xr

    with xr.open_dataset(path) as ds:
        da = _variable(ds, variable)
        lat, lon = _spatial_dims(da)
        others = [d for d in da.dims if d not in (lat, lon)]
        peak = da.max(dim=others, skipna=True) if others else da
        peak = peak.transpose(lat, lon).rename({lat: "lat", lon: "lon"}).load()
    return peak.astype("float64")


def values_on(grid, path: str | Path, variable: str | None = None) -> np.ndarray:
    """The values of a full-domain file at the cells of `grid`, as a 2-D array.

    `grid` is a DataArray with `lat` and `lon` coordinates (the discharge peak).
    Each grid coordinate is matched to the nearest coordinate in the file and the
    match must lie within half a cell, or this raises: the box and the domain
    are matched by position on the Earth, never by array shape. Only the subset
    is read, so a 54 MB threshold file costs a few hundred kilobytes of memory.
    """
    import xarray as xr

    with xr.open_dataset(path) as ds:
        da = _variable(ds, variable)
        lat, lon = _spatial_dims(da)
        picked = da.sel(
            {lat: grid["lat"].values, lon: grid["lon"].values}, method="nearest"
        )
        for name, want in ((lat, grid["lat"].values), (lon, grid["lon"].values)):
            offset = np.abs(picked[name].values.astype("float64") - want.astype("float64"))
            if offset.size and offset.max() > CELL_DEG / 2 + 1e-9:
                raise ValueError(
                    f"{Path(path).name}: the grid is {offset.max():.5f} deg off the "
                    f"discharge grid along `{name}` (tolerance half a cell, "
                    f"{CELL_DEG / 2:.5f} deg). The files are not on one grid."
                )
        return picked.transpose(lat, lon).values.astype("float64")


def upstream_km2(path: str | Path, grid, variable: str | None = None) -> np.ndarray:
    """The upstream area at the cells of `grid`, in km2.

    LISFLOOD stores upstream area in m2. The unit is taken from the variable's
    `units` attribute when there is one; without it, a field whose largest value
    exceeds ten million is read as m2, because no European catchment reaches
    ten million km2 (the Volga is 1.4 million) while every large river exceeds
    ten million m2.
    """
    import xarray as xr

    values = values_on(grid, path, variable)
    with xr.open_dataset(path) as ds:
        units = str(_variable(ds, variable).attrs.get("units", "")).lower().replace(" ", "")
    if units in ("km2", "km**2", "km^2", "km-2"):
        return values
    if units in ("m2", "m**2", "m^2") or (
        not units and np.nanmax(values, initial=0.0) > 1e7
    ):
        return values / 1e6
    if not units:
        return values
    raise ValueError(f"Unknown upstream-area unit {units!r} in {Path(path).name}.")


def highest_level_exceeded(
    peak: np.ndarray, thresholds: dict[float, np.ndarray]
) -> np.ndarray:
    """Per cell, the highest return level whose threshold the peak went past.

    Strictly past: a peak equal to its 1-in-100 discharge has reached that level,
    not exceeded it. 0 where the peak stayed under even the 1-in-1.5 level - a
    measured result, the river did not flood. NaN where the peak or any threshold
    is missing, because a cell with a gap in its levels cannot say which was the
    highest.

    Also NaN where the levels do not rise from one return period to the next.
    Measured 2026-10-24 on the real files: thresholds never decrease with the
    return period, but 3,825 cells carry the same discharge at two consecutive
    levels - fits on a flow of zero or nearly so. On such a cell any trickle
    "exceeds the 1-in-500 level", which says nothing about a flood.
    """
    peak = np.asarray(peak, dtype="float64")
    out = np.zeros(peak.shape, dtype="float64")
    known = np.isfinite(peak)
    previous = None
    for level in sorted(thresholds):
        threshold = np.asarray(thresholds[level], dtype="float64")
        known &= np.isfinite(threshold)
        if previous is not None:
            known &= threshold > previous
        out = np.where(peak > threshold, np.maximum(out, level), out)
        previous = threshold
    out[~known] = np.nan
    return out


def grid_footprint(grid):
    """The area the downloaded grid covers, out to the cell edges, in degrees."""
    lat = grid["lat"].values.astype("float64")
    lon = grid["lon"].values.astype("float64")
    half = CELL_DEG / 2
    return box(lon.min() - half, lat.min() - half, lon.max() + half, lat.max() + half)


def box_share(admin: gpd.GeoDataFrame, footprint) -> pd.Series:
    """The share of each region's area inside `footprint`, indexed like admin.

    The footprint is densified before it is reprojected, so its edges follow the
    meridians and parallels in the admin CRS instead of cutting straight across.
    """
    frame = gpd.GeoSeries([footprint], crs=POINT_CRS).segmentize(CELL_DEG).to_crs(admin.crs)
    inside = admin.geometry.intersection(frame.iloc[0]).area
    area = admin.geometry.area
    return (inside / area.where(area > 0)).fillna(0.0)


def cells_by_region(
    admin: gpd.GeoDataFrame,
    grid,
    level: np.ndarray,
    river: np.ndarray,
    *,
    min_box_share: float = MIN_BOX_SHARE,
) -> pd.DataFrame:
    """The three per-region columns from per-cell levels, indexed like admin.

    Each river cell is assigned to the region containing its centre. Then:

    - `efas_2021_max_rp_exceeded` - the highest level reached by any of the
      region's river cells (years). NaN when the region holds no river cell.
    - `efas_2021_cells_over_rp100` - river cells past the 1-in-100 level.
    - `efas_2021_river_cells` - river cells counted, the denominator.

    All three are NaN for a region less than `min_box_share` inside the grid.
    A region fully inside with no river cell reads 0 cells and a NaN level: it
    was measured, it has no river to measure.
    """
    if admin.crs is None:
        raise ValueError("admin has crs=None; refusing to guess.")
    lon2d, lat2d = np.meshgrid(grid["lon"].values, grid["lat"].values)
    keep = np.asarray(river, dtype=bool) & np.isfinite(level)
    points = gpd.GeoDataFrame(
        {"level": level[keep]},
        geometry=gpd.points_from_xy(lon2d[keep], lat2d[keep]),
        crs=POINT_CRS,
    ).to_crs(admin.crs)
    joined = gpd.sjoin(points, admin[["geometry"]], how="inner", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    grouped = joined.groupby("index_right")["level"]
    out = pd.DataFrame(
        {
            "efas_2021_max_rp_exceeded": grouped.max(),
            "efas_2021_cells_over_rp100": grouped.apply(lambda s: int((s >= 100.0).sum())),
            "efas_2021_river_cells": grouped.size(),
        }
    ).reindex(admin.index)
    for column in ("efas_2021_cells_over_rp100", "efas_2021_river_cells"):
        out[column] = out[column].fillna(0.0).astype("float64")
    outside = box_share(admin, grid_footprint(grid)) < min_box_share
    out.loc[outside.to_numpy(), list(COLUMNS)] = np.nan
    return out


def by_region(
    admin: gpd.GeoDataFrame,
    *,
    discharge_path: str | Path | None = None,
    upstream_path: str | Path | None = None,
    threshold_dir: str | Path | None = None,
    min_upstream_km2: float = MIN_UPSTREAM_KM2,
    min_box_share: float = MIN_BOX_SHARE,
) -> tuple[pd.DataFrame | None, str]:
    """The July 2021 return-level columns per region, or None and the reason.

    Returns `(frame, note)` with `frame` indexed like `admin`, the shape of the
    `_built`/`_natura` helpers in scripts/build_context.py: a missing input is a
    reason in the notes, not a traceback, because the other layers do not depend
    on this one.
    """
    discharge_path = Path(discharge_path or JULY_DIR / DISCHARGE_FILE)
    # The EWDS field when it was fetched with the discharge, otherwise the open
    # LISFLOOD static map of the same grid (efas_upstream_area), which needs no
    # account.
    if upstream_path is None:
        fetched = JULY_DIR / UPSTREAM_FILE
        upstream_path = fetched if fetched.exists() else (
            DATA / "raw" / "download" / "efas_upstream_area.nc")
    upstream_path = Path(upstream_path)
    paths = {level: threshold_path(level, threshold_dir) for level in RETURN_LEVELS}
    missing = [p for p in (discharge_path, upstream_path, *paths.values()) if not p.exists()]
    if missing:
        names = ", ".join(p.name for p in missing)
        return None, (
            f"missing {names}; run scripts/fetch_efas_july2021.py and fetch "
            f"efas_flood_thresholds"
        )
    try:
        import xarray  # noqa: F401
    except ImportError:
        return None, "xarray is not installed (pip install -r requirements.txt)"

    peak = peak_discharge(discharge_path)
    thresholds = {level: values_on(peak, path) for level, path in paths.items()}
    level = highest_level_exceeded(peak.values, thresholds)
    upstream = upstream_km2(upstream_path, peak)
    river = np.nan_to_num(upstream, nan=0.0) >= min_upstream_km2
    frame = cells_by_region(admin, peak, level, river, min_box_share=min_box_share)

    measured = int(frame["efas_2021_river_cells"].notna().sum())
    over = int((frame["efas_2021_cells_over_rp100"] > 0).sum())
    footprint = grid_footprint(peak).bounds
    note = (
        f"{int((river & np.isfinite(level)).sum()):,} river cells "
        f"(upstream >= {min_upstream_km2:g} km2) in box "
        f"W{footprint[0]:.2f} S{footprint[1]:.2f} E{footprint[2]:.2f} N{footprint[3]:.2f}; "
        f"{measured} regions measured, {over} with a cell past RP100; "
        f"thresholds EFAS v5.1 on reanalysis version_5_0"
    )
    return frame, note
