"""Tests for the HERA peak-discharge trend layer and its resumable download.

Synthetic NetCDFs in tmp_path, a fake HTTP session, no network. What is pinned:
the streamed annual maximum equals the in-memory one whatever the block plan,
Sen's slope and Mann-Kendall recover a known trend and not a trend in noise,
an incomplete year is never cached, a region without river cells is NaN and not
0, and a download resumes from its `.part` file and skips a finished one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import requests
import xarray as xr
from shapely.geometry import box

from src import hera

ROOT = Path(__file__).resolve().parents[1]
STEP = 1.0 / 60.0


def _coords(nrows=4, ncols=5):
    lat = (50.0 - np.arange(nrows) * STEP).astype("float32")
    lon = (5.0 + np.arange(ncols) * STEP).astype("float32")
    return lat, lon


def _write_year(path: Path, values: np.ndarray, chunks=None) -> None:
    lat, lon = _coords(values.shape[1], values.shape[2])
    encoding = {"dis": {"chunksizes": chunks}} if chunks else {}
    xr.Dataset(
        {"dis": (("time", "lat", "lon"), values.astype("float32"), {"units": "m3/s"})},
        coords={"time": np.arange(values.shape[0]), "lat": lat, "lon": lon},
    ).to_netcdf(path, encoding=encoding)


# --- streaming the annual extremes -------------------------------------------

def test_block_plans_stay_chunk_aligned_and_under_budget():
    # Contiguous: whole planes, as many steps as the budget allows.
    assert hera.plan_blocks((100, 10, 10), None, 4, budget=4 * 100 * 7) == (7, 10, 10)
    # Chunked (10, 4, 5) on (100, 8, 20), budget of two chunks: tile, never a
    # partial chunk.
    steps, rows, cols = hera.plan_blocks((100, 8, 20), (10, 4, 5), 4, budget=4 * 10 * 4 * 5 * 2)
    assert steps == 10 and rows % 4 == 0 and cols % 5 == 0
    assert steps * rows * cols * 4 <= 4 * 10 * 4 * 5 * 2


@pytest.mark.parametrize("chunks, budget", [(None, 10**9), (None, 4 * 20 * 3), ((7, 2, 3), 4 * 7 * 2 * 3)])
def test_the_streamed_annual_max_and_mean_equal_the_in_memory_ones(tmp_path, chunks, budget):
    rng = np.random.default_rng(0)
    values = rng.gamma(2.0, 5.0, size=(30, 4, 5))
    values[:, 0, 0] = np.nan          # outside the domain
    values[3, 1, 1] = np.nan          # one missing step
    path = tmp_path / "dis.HERA_v2_2001.nc"
    _write_year(path, values, chunks)
    got = hera.annual_extremes(path, budget=budget)
    expect = values.astype("float32")
    # Rows 1+ hold no all-NaN cell, so numpy's own nan-reductions are the reference.
    np.testing.assert_allclose(got["annual_max"].values[1:, :], np.nanmax(expect[:, 1:, :], axis=0))
    np.testing.assert_allclose(got["annual_mean"].values[1:, :], np.nanmean(expect[:, 1:, :], axis=0), rtol=1e-6)
    assert np.isnan(got["annual_max"].values[0, 0]) and np.isnan(got["annual_mean"].values[0, 0])
    assert got.attrs["time_steps"] == 30


def test_the_seasonal_fields_follow_the_peak_and_the_threshold(tmp_path):
    # A bare step index is read as 6-hourly from 1 January of a common year.
    nt = hera.expected_steps(2001)
    values = np.full((nt, 1, 3), 1.0)
    jan15, jul19 = 14 * 4, 199 * 4                 # day of year 15 and 200
    values[jan15, 0, 0], values[jul19, 0, 0] = 9.0, 5.0   # winter peak
    values[jan15, 0, 1], values[jul19, 0, 1] = 5.0, 9.0   # summer peak
    values[jul19:jul19 + 8, 0, 2] = 7.0                    # two days above 6
    path = tmp_path / "dis.HERA_v2_2001.nc"
    _write_year(path, values)
    threshold = np.array([[6.0, 6.0, 6.0]], dtype="float32")
    # A budget of 100 steps per block: the peaks fall in different blocks.
    got = hera.annual_extremes(path, budget=4 * 3 * 100, threshold=threshold)
    assert list(got["peak_doy"].values[0]) == [15, 200, 200]
    np.testing.assert_allclose(got["winter_max"].values[0], [9.0, 5.0, 1.0])
    np.testing.assert_allclose(got["summer_max"].values[0], [5.0, 9.0, 7.0])
    np.testing.assert_allclose(got["days_above_threshold"].values[0], [0.25, 0.25, 2.0])
    assert got.attrs["schema"] == hera.CACHE_SCHEMA
    # No return level at a cell: not measured, not zero days.
    threshold[0, 1] = np.nan
    got = hera.annual_extremes(path, threshold=threshold)
    assert np.isnan(got["days_above_threshold"].values[0, 1])
    # No threshold at all: the whole field is NaN.
    assert np.isnan(hera.annual_extremes(path)["days_above_threshold"].values).all()


def test_a_cache_in_the_old_layout_is_recomputed(tmp_path, monkeypatch):
    monkeypatch.setattr(hera, "flood_threshold", lambda *a, **k: None)
    path = tmp_path / "dis.HERA_v2_2001.nc"
    _write_year(path, np.ones((hera.expected_steps(2001), 2, 2)))
    cache = tmp_path / "cache"
    target = hera.cache_year(path, cache)
    with xr.open_dataset(target) as ds:
        old = ds[["annual_max", "annual_mean"]].load()
        old.attrs = {"source_bytes": ds.attrs["source_bytes"]}   # schema 1: no seasonal fields
    old.to_netcdf(target)
    hera.cache_year(path, cache)
    with xr.open_dataset(target) as ds:
        assert "peak_doy" in ds and int(ds.attrs["schema"]) == hera.CACHE_SCHEMA


def test_an_incomplete_year_is_never_cached(tmp_path):
    path = tmp_path / "dis.HERA_v2_2001.nc"
    _write_year(path, np.ones((100, 2, 2)))
    with pytest.raises(ValueError, match="Incomplete"):
        hera.cache_year(path, tmp_path / "cache")
    assert not hera.cache_path(2001, tmp_path / "cache").exists()


def test_a_full_year_is_cached_once_and_recomputed_when_the_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "dis.HERA_v2_2001.nc"
    _write_year(path, np.ones((hera.expected_steps(2001), 2, 2)))
    cache = tmp_path / "cache"
    target = hera.cache_year(path, cache)
    assert target.exists()
    calls = []
    real = hera.annual_extremes
    monkeypatch.setattr(hera, "annual_extremes", lambda *a, **k: calls.append(1) or real(*a, **k))
    hera.cache_year(path, cache)
    assert calls == []                 # same source size: skipped
    _write_year(path, np.full((hera.expected_steps(2001), 2, 2), 2.0), chunks=(73, 1, 1))
    hera.cache_year(path, cache)
    assert calls == [1]                # different file: recomputed


def test_leap_years_have_four_more_steps():
    assert hera.expected_steps(2020) == 1464 and hera.expected_steps(2019) == 1460
    assert hera.expected_steps(1900) == 1460


def test_an_unreadable_file_is_skipped_with_a_note(tmp_path):
    (tmp_path / "dis.HERA_v2_1995.nc").write_bytes(b"\x89HDF truncated")
    notes = hera.build_cache(tmp_path, tmp_path / "cache", years=[1995], progress=None)
    assert len(notes) == 1 and "dis.HERA_v2_1995.nc skipped" in notes[0]


# --- Sen's slope and Mann-Kendall ----------------------------------------------

def _naive_sen_and_s(y, x):
    slopes, s = [], 0
    for i in range(len(y)):
        for j in range(i + 1, len(y)):
            slopes.append((y[j] - y[i]) / (x[j] - x[i]))
            s += np.sign(y[j] - y[i])
    return np.median(slopes), s


def test_a_known_trend_is_recovered_and_significant():
    years = np.arange(1991, 2021)
    rng = np.random.default_rng(1)
    trend = 100.0 + 2.0 * (years - 1991) + rng.normal(0, 1.0, years.size)
    noise = 100.0 + rng.normal(0, 10.0, years.size)
    stack = np.stack([trend, noise], axis=1).astype("float32")
    slope = hera.sen_slope(stack, years)
    z = hera.mann_kendall_z(stack)
    assert slope[0] == pytest.approx(2.0, abs=0.15)
    assert z[0] > hera.MK_Z_5PCT
    # Against a naive double loop, on both columns.
    n = years.size
    var = n * (n - 1) * (2 * n + 5) / 18
    for col in range(2):
        expect_slope, s = _naive_sen_and_s(stack[:, col].astype("float64"), years)
        assert slope[col] == pytest.approx(expect_slope)
        assert z[col] == pytest.approx((s - np.sign(s)) / np.sqrt(var))
    assert abs(z[1]) < hera.MK_Z_5PCT  # this noise draw carries no trend


def test_gaps_in_the_record_use_the_real_years():
    years = [1991, 1992, 2000, 2001]
    stack = np.array([[0.0], [1.0], [9.0], [10.0]], dtype="float32")
    assert hera.sen_slope(stack, years)[0] == pytest.approx(1.0)


# --- river cells and the region aggregation -------------------------------------

def _write_cache(cache: Path, years, peaks, means):
    lat, lon = _coords(*peaks(years[0]).shape)
    cache.mkdir(parents=True, exist_ok=True)
    for year in years:
        xr.Dataset(
            {"annual_max": (("lat", "lon"), peaks(year).astype("float32")),
             "annual_mean": (("lat", "lon"), means(year).astype("float32"))},
            coords={"lat": lat, "lon": lon},
        ).to_netcdf(hera.cache_path(year, cache))


def _admin_over(lat, lon):
    """Region A over columns 0-2, region B over columns 3-4, C far away."""
    edge = lambda c: float(lon[0]) + (c - 0.5) * STEP  # noqa: E731
    north, south = float(lat[0]) + STEP / 2, float(lat[-1]) - STEP / 2
    frame = gpd.GeoDataFrame(
        {"nuts_id": ["A", "B", "C"]},
        geometry=[box(edge(0), south, edge(3), north), box(edge(3), south, edge(5), north),
                  box(20.0, 60.0, 20.5, 60.5)],
        crs="EPSG:4326",
    ).to_crs("EPSG:3035")
    frame.index = [7, 8, 9]
    return frame


def test_regions_get_the_median_trend_and_nan_without_river_cells(tmp_path):
    years = list(range(1991, 2021))
    shape = (4, 5)

    def peaks(year):
        out = np.full(shape, 50.0)
        out[:, :3] = 100.0 + (year - 1991)          # A: +1 m3/s a year
        return out

    def means(year):
        out = np.full(shape, 0.2)                    # B: under the river threshold
        out[:, :3] = 5.0
        out[0, 0] = np.nan if year == 2000 else 5.0  # a gap: dropped as a river cell
        return out

    cache = tmp_path / "cache"
    _write_cache(cache, years, peaks, means)
    used, stack, lat, lon = hera.river_stack(years, cache)
    assert used == years and stack.shape == (30, 11)  # 12 river cells minus the gappy one
    admin = _admin_over(*_coords(*shape))
    frame = hera.trends_by_region(admin, lat, lon, stack, used)
    assert list(frame.index) == [7, 8, 9] and list(frame.columns) == list(hera.COLUMNS)
    a = frame.loc[7]
    # Sen slope 1 per year over a median annual max of 114.5: 1/114.5 x 1000.
    assert a["hera_peak_trend_pct_per_decade"] == pytest.approx(1000 / 114.5)
    assert a["hera_cells_increasing_share"] == 1.0
    assert a["hera_years"] == 30 and a["hera_river_cells"] == 11
    # B has cells but no river, C is outside the grid: both NaN, never 0.
    assert frame.loc[8].isna().all() and frame.loc[9].isna().all()
    # A cache without the seasonal fields leaves their columns NaN.
    assert a[["hera_winter_peak_share", "hera_flood_days_per_year"]].isna().all()


def test_the_seasonal_columns_recover_known_shifts(tmp_path):
    years = list(range(1991, 2021))
    shape = (4, 5)
    lat, lon = _coords(*shape)
    cache = tmp_path / "cache"
    cache.mkdir()
    for year in years:
        k = year - 1991
        peak = np.full(shape, 100.0 + k)
        winter = peak.copy()
        winter[:, 1] = 50.0                            # column 1 always peaks in summer
        xr.Dataset(
            {"annual_max": (("lat", "lon"), peak.astype("float32")),
             "annual_mean": (("lat", "lon"), np.full(shape, 5.0, "float32")),
             # 25 December in 1991, one day later each year: it crosses
             # New Year, which on the circle is still +1 a year.
             "peak_doy": (("lat", "lon"), np.full(shape, (359 + k - 1) % 365 + 1, "int16")),
             "winter_max": (("lat", "lon"), winter.astype("float32")),
             "summer_max": (("lat", "lon"), np.full(shape, 50.0 - 0.5 * k, "float32")),
             "days_above_threshold": (("lat", "lon"), np.full(shape, 2.0 + 0.5 * k, "float32"))},
            coords={"lat": lat, "lon": lon},
        ).to_netcdf(hera.cache_path(year, cache))
    used, fields, plat, plon = hera.river_fields(years, cache)
    assert set(fields) == set(hera.FIELDS)
    frame = hera.trends_by_region(_admin_over(lat, lon), plat, plon, fields["annual_max"], used, fields)
    a = frame.loc[7]
    # Columns 0 and 2 always peak in winter, column 1 never: the median cell, 1.
    assert a["hera_winter_peak_share"] == 1.0
    assert a["hera_peak_timing_shift_days_per_decade"] == pytest.approx(10.0)
    # Summer max falls 0.5 a year from a median of 42.75.
    assert a["hera_summer_peak_trend_pct_per_decade"] == pytest.approx(-5 / 42.75 * 100)
    assert a["hera_flood_days_per_year"] == pytest.approx(2.0 + 0.5 * 14.5)
    assert a["hera_flood_days_trend_per_decade"] == pytest.approx(5.0)
    assert frame.loc[9].isna().all()


def _timing_frame(peak_doy, years):
    """trends_by_region on one row of river cells in region A with these peak days."""
    lat, lon = _coords(1, peak_doy.shape[1])
    stack = np.full(peak_doy.shape, 100.0)
    return hera.trends_by_region(_admin_over(lat, lon), np.full(lon.size, lat[0]), lon,
                                 stack, years, {"peak_doy": peak_doy}).loc[7]


def test_peak_timing_does_not_jump_where_the_year_is_cut():
    years = list(range(1991, 2021))
    k = np.arange(30)
    # Peaks drifting 2 days a decade from 27 September, across 1 October: a
    # date read from a fixed cut point jumps by a year there.
    doy = np.round(270 + 0.2 * k).astype("int16")[:, None].repeat(3, axis=1)
    shift = _timing_frame(doy, years)["hera_peak_timing_shift_days_per_decade"]
    assert shift == pytest.approx(2.0, abs=0.1)


def test_peak_timing_is_nan_where_peaks_fall_in_any_season():
    years = list(range(1991, 2021))
    # Peaks spread over the whole year: resultant length near 0, no timing.
    doy = (1 + (np.arange(30) * 137) % 365).astype("int16")[:, None].repeat(3, axis=1)
    assert np.isnan(_timing_frame(doy, years)["hera_peak_timing_shift_days_per_decade"])


def test_by_region_needs_enough_years(tmp_path):
    cache = tmp_path / "cache"
    _write_cache(cache, [2001, 2002], lambda y: np.full((2, 2), 10.0), lambda y: np.full((2, 2), 5.0))
    frame, why = hera.by_region(_admin_over(*_coords(2, 2)), hera_dir=tmp_path,
                                cache_dir=cache, years=[2001, 2002], min_years=10)
    assert frame is None and "2 cached HERA year(s)" in why


def test_by_region_returns_a_frame_and_a_note(tmp_path):
    years = list(range(2001, 2013))
    cache = tmp_path / "cache"
    _write_cache(cache, years, lambda y: np.full((2, 2), 10.0 + y - 2001), lambda y: np.full((2, 2), 5.0))
    admin = _admin_over(*_coords(2, 2))
    frame, note = hera.by_region(admin, hera_dir=tmp_path, cache_dir=cache, years=years)
    assert frame is not None and frame.index.equals(admin.index)
    assert "2001-2012 (12 years)" in note


# --- the resumable download, with HTTP faked ------------------------------------

def _fetch():
    spec = importlib.util.spec_from_file_location("fetch_hera", ROOT / "scripts" / "fetch_hera.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PAYLOAD = b"\x89HDF" + bytes(range(256)) * 40


class _Response:
    def __init__(self, status, body=b"", headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, size):
        for i in range(0, len(self.body), 1000):
            yield self.body[i:i + 1000]


class _Session:
    """Serves PAYLOAD, honouring Range unless told not to; can fail N times first."""

    def __init__(self, payload=PAYLOAD, honour_range=True, failures=0):
        self.payload, self.honour_range, self.failures = payload, honour_range, failures
        self.ranges = []

    def head(self, url, **kw):
        return _Response(200, headers={"Content-Length": str(len(self.payload))})

    def get(self, url, headers=None, **kw):
        if self.failures:
            self.failures -= 1
            raise requests.ConnectionError("dropped")
        wanted = (headers or {}).get("Range")
        self.ranges.append(wanted)
        if wanted and self.honour_range:
            start = int(wanted.split("=")[1].rstrip("-"))
            return _Response(206, self.payload[start:])
        return _Response(200, self.payload)


def test_a_partial_file_is_resumed_with_a_range_request(tmp_path):
    fetch = _fetch()
    target = tmp_path / "dis.HERA_v2_2001.nc"
    (tmp_path / "dis.HERA_v2_2001.nc.part").write_bytes(PAYLOAD[:3000])
    session = _Session()
    assert fetch.download(session, "u", target, progress=None) == "downloaded"
    assert session.ranges == ["bytes=3000-"]
    assert target.read_bytes() == PAYLOAD and not (tmp_path / "dis.HERA_v2_2001.nc.part").exists()


def test_a_complete_file_is_skipped_without_a_get(tmp_path):
    fetch = _fetch()
    target = tmp_path / "f.nc"
    target.write_bytes(PAYLOAD)
    session = _Session()
    assert fetch.download(session, "u", target, progress=None) == "skipped"
    assert session.ranges == []


def test_a_server_ignoring_range_restarts_the_file_cleanly(tmp_path):
    fetch = _fetch()
    target = tmp_path / "f.nc"
    (tmp_path / "f.nc.part").write_bytes(PAYLOAD[:500])
    fetch.download(_Session(honour_range=False), "u", target, progress=None)
    assert target.read_bytes() == PAYLOAD


def test_a_dropped_connection_is_retried_with_backoff(tmp_path):
    fetch = _fetch()
    waits = []
    target = tmp_path / "f.nc"
    fetch.download(_Session(failures=2), "u", target, sleep=waits.append, progress=None)
    assert target.read_bytes() == PAYLOAD and waits == [5.0, 10.0]


def test_too_many_failures_give_up(tmp_path):
    fetch = _fetch()
    with pytest.raises(RuntimeError, match="gave up"):
        fetch.download(_Session(failures=10), "u", tmp_path / "f.nc", retries=2,
                       sleep=lambda s: None, progress=None)


def test_an_html_body_is_not_renamed_into_place(tmp_path):
    fetch = _fetch()
    target = tmp_path / "f.nc"
    with pytest.raises(RuntimeError, match="not an HDF5"):
        fetch.download(_Session(payload=b"<html>listing</html>"), "u", target, progress=None)
    assert not target.exists()


def test_flood_days_trend_is_read_off_sparse_counts():
    # Flood days are 0 in most years: a Sen slope says 0, the thirds do not.
    years = list(range(1991, 2021))
    days = np.zeros((30, 1))
    days[[2, 5], 0] = 1.0                      # two flood days in 1991-2000
    days[[21, 24, 26, 28], 0] = 1.0            # four in 2011-2020
    assert hera.sen_slope(days, np.array(years))[0] == 0
    change = hera._third_change_per_decade(days, years)[0]
    assert change == pytest.approx((0.4 - 0.2) / 20 * 10)
