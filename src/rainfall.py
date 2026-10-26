"""July 2021 event rainfall per NUTS3 region, from the EMO-1 observation grid.

The kit's hazard layers are river-only: the JRC maps start at a 150 km2
catchment and EFAS reads river discharge. What fell on the hillslopes, the
small tributaries and the towns in between is in neither - and in July 2021
that is where much of the damage started. EMO-1 (`emo1_precipitation_2021` in
config/sources.yaml) is the observed daily precipitation that forced EFAS, at
1 arcmin over the whole EFAS domain, so it gives ONE observed driver read the
same way across Belgium, Germany, the Netherlands, Luxembourg and France, and
it shows rain where the river map is silent.

Three properties of the file decide the design.

**A time stamp marks the end of a 24 h accumulation, at 06:00.** The file's
`comment` says so and the steps run `2021-01-02T06:00` ... `2022-01-01T06:00`.
So the default window `2021-07-13` to `2021-07-16` sums the four days ending
13, 14, 15 and 16 July at 06:00: rain from 12 July 06:00 to 16 July 06:00,
which holds the 14-15 July peak. A gap in the window is refused rather than
summed, because a missing day would read as a drier event.

**The file is a 365-step continental cube.** `pr` is float64, 365 x 2970 x
4530, about 39 GB once decoded (351 MB compressed on disk). `event_total`
slices time and, given a bounding box, space before anything is loaded, so a
five-country read is a few tens of megabytes.

**A cell belongs to the region holding its centre**, the rule of
`src/efas.py::cells_by_region`, with the centres reprojected to the regions'
CRS. A region too small to hold any centre was not measured, so its statistics
are NaN with `cells` 0 - never 0 mm, which would claim it stayed dry. A cell
with no value (sea, outside the interpolation domain) is dropped, not counted
as zero.

Caveat carried with the figures: EMO-1 is interpolated from station
observations, not radar, and daily; the peak hour is not in it, and a
convective cell between stations is smoothed out.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from src.efas import CELL_DEG, POINT_CRS, _spatial_dims

DATA = Path(__file__).resolve().parents[1] / "data"
EMO1_FILE = DATA / "raw" / "download" / "emo1_precipitation_2021.nc"
OUT_FILE = DATA / "processed" / "rainfall_jul2021.parquet"

#: First and last day-end (06:00) of the July 2021 event window, inclusive.
EVENT_START = "2021-07-13"
EVENT_END = "2021-07-16"

PREFIX = "rain_4d_jul2021"
COLUMNS = (
    "nuts_id",
    f"{PREFIX}_mean_mm",
    f"{PREFIX}_max_mm",
    f"{PREFIX}_p95_mm",
    "cells",
)


def _descending(values) -> bool:
    """Whether a 1-D coordinate runs from high to low (EMO-1 latitude does)."""
    return len(values) > 1 and values[0] > values[-1]


def event_total(
    nc_path: str | Path,
    start: str = EVENT_START,
    end: str = EVENT_END,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    variable: str = "pr",
):
    """The rain summed over the daily steps ending (at 06:00) from `start` to `end`.

    Returns a (lat, lon) DataArray in mm with `start`, `end` and `days` in its
    attributes. `bbox` = (west, south, east, north) in degrees cuts the grid
    before it is read, so only that window is ever loaded. A cell missing on
    any day of the window is NaN, not the sum of the days it has, and a window
    with a missing day raises: both would understate the event.
    """
    import xarray as xr

    expected = len(pd.date_range(start, end, freq="D"))
    if expected == 0:
        # An end before the start selects no step, and a sum over nothing is
        # 0 mm everywhere: a dry map, not an error, unless refused here.
        raise ValueError(f"end {end} is before start {start}; no day to sum.")
    with xr.open_dataset(nc_path) as ds:
        da = ds[variable]
        lat, lon = _spatial_dims(da)
        da = da.sel(time=slice(start, end))
        if bbox is not None:
            west, south, east, north = bbox
            lats = da[lat].values
            da = da.sel({
                lat: slice(north, south) if _descending(lats) else slice(south, north),
                lon: slice(west, east),
            })
        days = int(da.sizes["time"])
        if days != expected:
            raise ValueError(
                f"{days} of {expected} daily steps found between {start} and {end} "
                f"in {Path(nc_path).name}; refusing to sum a window with a gap."
            )
        total = da.load().sum("time", min_count=days)
    total = total.rename({lat: "lat", lon: "lon"})
    total.name = f"{PREFIX}_mm"
    total.attrs = {"units": "mm", "start": start, "end": end, "days": days}
    return total


def footprint(total):
    """The area the grid covers out to the cell edges, in degrees."""
    lat = total["lat"].values.astype("float64")
    lon = total["lon"].values.astype("float64")
    half = CELL_DEG / 2
    return box(lon.min() - half, lat.min() - half, lon.max() + half, lat.max() + half)


def zonal_stats(total, regions_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Mean, max and 95th percentile of the event rain per region, and the cell count.

    Only regions whose bounds intersect the grid are returned - a region the
    grid never reaches is not a measurement. Each finite cell counts for the
    region holding its centre; a returned region with no centre inside reads
    NaN for the three statistics and 0 cells. Columns are `COLUMNS`.
    """
    if regions_gdf.crs is None:
        raise ValueError("regions_gdf has crs=None; refusing to guess.")
    grid_box = gpd.GeoSeries([footprint(total)], crs=POINT_CRS)
    # Compare in degrees: the regions' bounds there against the grid's box.
    in_degrees = regions_gdf.to_crs(POINT_CRS)
    bounds = in_degrees.geometry.bounds
    g = grid_box.iloc[0].bounds
    hits = ((bounds["maxx"] >= g[0]) & (bounds["minx"] <= g[2])
            & (bounds["maxy"] >= g[1]) & (bounds["miny"] <= g[3]))
    regions = regions_gdf.loc[hits.to_numpy(), ["nuts_id", "geometry"]].reset_index(drop=True)

    values = total.values
    lon2d, lat2d = np.meshgrid(total["lon"].values, total["lat"].values)
    keep = np.isfinite(values)
    points = gpd.GeoDataFrame(
        {"rain": values[keep]},
        geometry=gpd.points_from_xy(lon2d[keep], lat2d[keep]),
        crs=POINT_CRS,
    ).to_crs(regions.crs)
    joined = gpd.sjoin(points, regions[["geometry"]], how="inner", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    grouped = joined.groupby("index_right")["rain"]
    out = pd.DataFrame(
        {
            f"{PREFIX}_mean_mm": grouped.mean(),
            f"{PREFIX}_max_mm": grouped.max(),
            f"{PREFIX}_p95_mm": grouped.quantile(0.95),
            "cells": grouped.size(),
        }
    ).reindex(regions.index)
    out["cells"] = out["cells"].fillna(0).astype("int64")
    out.insert(0, "nuts_id", regions["nuts_id"].to_numpy())
    return out[list(COLUMNS)].reset_index(drop=True)
