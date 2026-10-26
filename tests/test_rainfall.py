"""Tests for the July 2021 event rainfall per region (EMO-1).

Everything runs on a small synthetic NetCDF laid out like the real file - one
`pr` (time, lat, lon) variable in mm/day, latitude descending at a 1 arcmin
step, each time stamp marking the END of a 24 h accumulation at 06:00 - and on
square regions drawn in degrees. What is pinned: only the days inside the
window are summed, a cell with a missing day is missing rather than drier, the
per-region mean/max/p95 are computed on the cells whose centre falls inside,
and a region holding no cell centre reads NaN, not 0 mm.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from shapely.geometry import box

from src import rainfall

STEP = 1.0 / 60.0
NROWS, NCOLS = 12, 24
LAT0, LON0 = 50.5, 5.5  # centre of the first (north-west) cell


def _coords():
    lat = LAT0 - np.arange(NROWS) * STEP
    lon = LON0 + np.arange(NCOLS) * STEP
    return lat, lon


def _write_emo(path, *, days=("2021-07-12", "2021-07-13", "2021-07-14",
                              "2021-07-15", "2021-07-16", "2021-07-17")):
    """One file of daily rain where day k (0-based, in `days`) rains 2**k times a column ramp.

    Each day carries a distinct power of two times a per-column ramp, so a sum
    over the wrong days cannot land on the right total by accident.
    """
    lat, lon = _coords()
    times = pd.to_datetime([f"{d}T06:00" for d in days])
    ramp = np.tile(np.arange(1, NCOLS + 1, dtype="float64"), (NROWS, 1))
    data = np.stack([ramp * (2.0 ** k) for k in range(len(times))])
    ds = xr.Dataset(
        {"pr": (("time", "lat", "lon"), data, {"units": "mm"})},
        coords={"time": times, "lat": lat, "lon": lon},
    )
    ds.to_netcdf(path)
    return ramp


def _regions() -> gpd.GeoDataFrame:
    """Two squares that split the grid west/east, plus a sliver between centres."""
    lat, lon = _coords()
    half = STEP / 2
    north, south = lat[0] + half, lat[-1] - half
    west, east = lon[0] - half, lon[-1] + half
    mid = lon[NCOLS // 2] - half  # the edge between column 11 and column 12
    # A thin box sitting between two rows of cell centres: inside the grid,
    # holding no centre at all.
    sliver_lat = lat[3] - half
    sliver = box(lon[2], sliver_lat - STEP * 0.1, lon[4], sliver_lat + STEP * 0.1)
    return gpd.GeoDataFrame(
        {"nuts_id": ["WEST1", "EAST1", "SLIV1", "FAR01"]},
        geometry=[
            box(west, south, mid, north),
            box(mid, south, east, north),
            sliver,
            box(20.0, 40.0, 21.0, 41.0),  # nowhere near the grid
        ],
        crs="EPSG:4326",
    )


def test_event_total_sums_only_the_window(tmp_path):
    path = tmp_path / "emo.nc"
    ramp = _write_emo(path)
    total = rainfall.event_total(path, start="2021-07-13", end="2021-07-16")
    # Days ending 13, 14, 15 and 16 July at 06:00 are k = 1..4: 2+4+8+16 = 30.
    np.testing.assert_allclose(total.values, ramp * 30.0)
    assert total.attrs["days"] == 4
    assert total.attrs["units"] == "mm"


def test_event_total_bbox_reads_a_window_only(tmp_path):
    path = tmp_path / "emo.nc"
    _write_emo(path)
    lat, lon = _coords()
    total = rainfall.event_total(path, bbox=(lon[2], lat[5], lon[6], lat[1]))
    assert total.sizes["lat"] == 5 and total.sizes["lon"] == 5


def test_event_total_refuses_a_gap_in_the_window(tmp_path):
    path = tmp_path / "emo.nc"
    _write_emo(path, days=("2021-07-13", "2021-07-14", "2021-07-16"))
    with pytest.raises(ValueError, match="3 of 4"):
        rainfall.event_total(path)


def test_event_total_refuses_an_end_before_the_start(tmp_path):
    """A reversed window selects no step; summed, it would be 0 mm everywhere."""
    path = tmp_path / "emo.nc"
    _write_emo(path)
    with pytest.raises(ValueError, match="before start"):
        rainfall.event_total(path, start="2021-07-16", end="2021-07-13")


def test_cell_missing_one_day_is_nan_not_drier(tmp_path):
    path = tmp_path / "emo.nc"
    _write_emo(path)
    with xr.open_dataset(path) as ds:
        ds = ds.load()
    ds["pr"][2, 0, 0] = np.nan  # day ending 14 July, north-west cell
    patched = tmp_path / "patched.nc"
    ds.to_netcdf(patched)
    total = rainfall.event_total(patched)
    assert np.isnan(total.values[0, 0])
    assert np.isfinite(total.values[0, 1])


def test_zonal_stats_mean_max_per_region(tmp_path):
    path = tmp_path / "emo.nc"
    ramp = _write_emo(path)
    total = rainfall.event_total(path)
    out = rainfall.zonal_stats(total, _regions()).set_index("nuts_id")

    assert list(rainfall.COLUMNS) == [
        "nuts_id",
        "rain_4d_jul2021_mean_mm",
        "rain_4d_jul2021_max_mm",
        "rain_4d_jul2021_p95_mm",
        "cells",
    ]
    west = ramp[:, : NCOLS // 2] * 30.0
    east = ramp[:, NCOLS // 2:] * 30.0
    assert out.loc["WEST1", "cells"] == west.size
    assert out.loc["EAST1", "cells"] == east.size
    assert out.loc["WEST1", "rain_4d_jul2021_mean_mm"] == pytest.approx(west.mean())
    assert out.loc["EAST1", "rain_4d_jul2021_max_mm"] == pytest.approx(east.max())
    assert out.loc["EAST1", "rain_4d_jul2021_p95_mm"] == pytest.approx(
        np.percentile(east, 95))
    # A region whose bounds miss the grid is left out, not reported as dry.
    assert "FAR01" not in out.index


def test_region_without_cells_is_nan_not_zero(tmp_path):
    path = tmp_path / "emo.nc"
    _write_emo(path)
    out = rainfall.zonal_stats(rainfall.event_total(path), _regions()).set_index("nuts_id")
    assert out.loc["SLIV1", "cells"] == 0
    for column in ("rain_4d_jul2021_mean_mm", "rain_4d_jul2021_max_mm",
                   "rain_4d_jul2021_p95_mm"):
        assert np.isnan(out.loc["SLIV1", column])


def test_zonal_stats_reprojects_points_to_the_region_crs(tmp_path):
    path = tmp_path / "emo.nc"
    _write_emo(path)
    total = rainfall.event_total(path)
    in_degrees = rainfall.zonal_stats(total, _regions()).set_index("nuts_id")
    in_metres = rainfall.zonal_stats(total, _regions().to_crs("EPSG:3035")).set_index("nuts_id")
    assert in_metres.loc["WEST1", "cells"] == in_degrees.loc["WEST1", "cells"]
