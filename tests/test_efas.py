"""Tests for the July 2021 return-level layer and its EWDS fetch.

Everything runs on small synthetic NetCDFs laid out like the real files - one
`rl_<level>` float32 `(lat, lon)` variable per threshold file, latitude
descending at a 1 arcmin step - and on a mocked cdsapi client. What is pinned:
the exact return level picked, the river-cell filter, NaN for a region the box
does not cover, and that the fetch fails clearly without a key or a licence.
"""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import xarray as xr
from shapely.geometry import box

from src import efas

ROOT = Path(__file__).resolve().parents[1]
STEP = 1.0 / 60.0
NROWS, NCOLS = 20, 30
LAT0, LON0 = 51.0, 4.0
ROWS, COLS = slice(5, 15), slice(5, 25)  # the discharge box inside the domain


def _domain_coords():
    lat = (LAT0 - np.arange(NROWS) * STEP).astype("float32")
    lon = (LON0 + np.arange(NCOLS) * STEP).astype("float32")
    return lat, lon


def _write_thresholds(directory: Path) -> None:
    """Nine threshold files with RL = 10 x the return period, everywhere."""
    lat, lon = _domain_coords()
    directory.mkdir(parents=True, exist_ok=True)
    for level in efas.RETURN_LEVELS:
        values = np.full((NROWS, NCOLS), 10.0 * level, dtype="float32")
        name = f"rl_{level:.1f}"
        xr.Dataset({name: (("lat", "lon"), values)}, coords={"lat": lat, "lon": lon}).to_netcdf(
            efas.threshold_path(level, directory)
        )


def _write_upstream(path: Path) -> None:
    """Upstream area in m2: 200 km2 (a river) left of column 17, 50 km2 right of it."""
    lat, lon = _domain_coords()
    values = np.where(np.arange(NCOLS)[None, :] < 17, 200e6, 50e6) * np.ones((NROWS, 1))
    da = xr.DataArray(values.astype("float32"), dims=("latitude", "longitude"),
                      coords={"latitude": lat, "longitude": lon}, attrs={"units": "m**2"})
    xr.Dataset({"uparea": da}).to_netcdf(path)


def _write_discharge(path: Path, peaks: dict[tuple[int, int], float]) -> None:
    """Three time steps over the box, 1 m3/s everywhere, `peaks` at step 1."""
    lat, lon = _domain_coords()
    values = np.ones((3, NROWS, NCOLS), dtype="float32")
    for (r, c), value in peaks.items():
        values[1, r, c] = value
    values = values[:, ROWS, COLS]
    xr.Dataset(
        {"dis06": (("valid_time", "latitude", "longitude"), values)},
        coords={"valid_time": np.arange(3), "latitude": lat[ROWS], "longitude": lon[COLS]},
    ).to_netcdf(path)


def _cell_box(r: int, c: int):
    """A small polygon around the centre of domain cell (r, c), in degrees."""
    lat, lon = _domain_coords()
    return box(lon[c] - 0.3 * STEP, lat[r] - 0.3 * STEP, lon[c] + 0.3 * STEP, lat[r] + 0.3 * STEP)


def _admin():
    lat, lon = _domain_coords()
    edge = lambda c: float(lon[c]) - STEP / 2  # noqa: E731
    top = lambda r: float(lat[r]) + STEP / 2  # noqa: E731
    shapes = {
        # Fully in the box, river columns 6-12, rows 6-12.
        "A": box(edge(6), top(13), edge(13), top(6)),
        # Fully in the box, only non-river columns 18-23.
        "B": box(edge(18), top(13), edge(24), top(6)),
        # Entirely outside the box (rows 0-3).
        "C": box(edge(6), top(4), edge(12), top(0)),
        # Half in, half out of the box along its eastern edge.
        "D": box(edge(20), top(13), edge(29), top(10)),
    }
    frame = gpd.GeoDataFrame({"nuts_id": list(shapes)}, geometry=list(shapes.values()),
                             crs="EPSG:4326").to_crs("EPSG:3035")
    frame.index = [10, 11, 12, 13]  # not a RangeIndex, so alignment is tested
    return frame


@pytest.fixture
def files(tmp_path):
    thresholds = tmp_path / "thresholds"
    _write_thresholds(thresholds)
    upstream = tmp_path / "up.nc"
    _write_upstream(upstream)
    discharge = tmp_path / "dis.nc"
    _write_discharge(discharge, {
        (8, 8): 1500.0,     # river, between RL100 (1000) and RL200 (2000)
        (9, 10): 1000.0,    # river, exactly RL100: reached, not exceeded -> 50
        (8, 20): 99999.0,   # NOT a river (50 km2): must not count
    })
    return {"discharge_path": discharge, "upstream_path": upstream, "threshold_dir": thresholds}


# --- the exceedance logic -----------------------------------------------------

def test_the_highest_level_exceeded_is_picked_exactly():
    thresholds = {lv: np.array([10.0 * lv] * 6) for lv in efas.RETURN_LEVELS}
    thresholds[2.0] = thresholds[2.0].copy()
    thresholds[2.0][4] = np.nan
    peak = np.array([1500.0, 1000.0, 5.0, 6000.0, 1500.0, np.nan])
    got = efas.highest_level_exceeded(peak, thresholds)
    assert got[0] == 100.0           # past RL100, under RL200
    assert got[1] == 50.0            # equal to RL100 is not past it
    assert got[2] == 0.0             # under the 1-in-1.5 level: measured, no flood
    assert got[3] == 500.0           # past everything
    assert np.isnan(got[4])          # a gap in the levels
    assert np.isnan(got[5])          # no discharge


def test_levels_that_do_not_rise_make_the_cell_unknown():
    """The real files hold 3,825 cells with equal thresholds at two levels:
    a trickle there would otherwise read as a 1-in-500 flood."""
    flat = {lv: np.array([0.0]) for lv in efas.RETURN_LEVELS}
    assert np.isnan(efas.highest_level_exceeded(np.array([0.01]), flat)[0])


def test_thresholds_are_read_at_the_discharge_cells_by_coordinate(files):
    peak = efas.peak_discharge(files["discharge_path"])
    assert peak.shape == (10, 20)
    assert float(peak.values[8 - 5, 8 - 5]) == 1500.0  # max over time
    got = efas.values_on(peak, efas.threshold_path(100.0, files["threshold_dir"]))
    assert got.shape == peak.shape and np.all(got == 1000.0)


def test_a_grid_off_by_more_than_half_a_cell_is_refused(files):
    """A box reaching past the domain edge: `nearest` would silently snap its
    cells to the edge row, so every one of them would read the wrong level."""
    peak = efas.peak_discharge(files["discharge_path"])
    shifted = peak.assign_coords(lat=peak["lat"] + 10 * STEP)
    with pytest.raises(ValueError, match="not on one grid"):
        efas.values_on(shifted, efas.threshold_path(2.0, files["threshold_dir"]))


def test_upstream_area_is_converted_to_km2(files):
    peak = efas.peak_discharge(files["discharge_path"])
    km2 = efas.upstream_km2(files["upstream_path"], peak)
    assert km2.max() == pytest.approx(200.0) and km2.min() == pytest.approx(50.0)


# --- the region aggregation ---------------------------------------------------

def test_by_region_counts_river_cells_and_leaves_the_unmeasured_nan(files):
    admin = _admin()
    frame, note = efas.by_region(admin, **files)
    assert list(frame.columns) == list(efas.COLUMNS)
    assert list(frame.index) == list(admin.index)
    a, b, c, d = (frame.loc[i] for i in admin.index)
    # A: 7 x 7 river cells, the highest past RL100, one cell past it.
    assert a["efas_2021_river_cells"] == 49
    assert a["efas_2021_max_rp_exceeded"] == 100.0
    assert a["efas_2021_cells_over_rp100"] == 1
    # B: inside the box but no river - measured zero, and no level to report.
    # Its 99,999 m3/s non-river cell is not counted.
    assert b["efas_2021_river_cells"] == 0
    assert b["efas_2021_cells_over_rp100"] == 0
    assert np.isnan(b["efas_2021_max_rp_exceeded"])
    # C outside the box, D half outside: not measured, never 0.
    assert c.isna().all() and d.isna().all()
    assert "river cells" in note and "version_5_0" in note


def test_a_missing_input_is_a_reason_not_a_traceback(tmp_path, files):
    frame, why = efas.by_region(_admin(), discharge_path=tmp_path / "absent.nc",
                                upstream_path=files["upstream_path"],
                                threshold_dir=files["threshold_dir"])
    assert frame is None and "absent.nc" in why


# --- the fetch script, with cdsapi mocked ------------------------------------

def _script():
    spec = importlib.util.spec_from_file_location(
        "fetch_efas_july2021", ROOT / "scripts" / "fetch_efas_july2021.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_request_matches_the_live_form():
    fetch = _script()
    req = fetch.discharge_request()
    assert req["hyear"] == ["2021"] and req["hmonth"] == ["07"]
    assert len(req["hday"]) * len(req["time"]) == 124  # the measured cost
    assert req["area"] == [52, 3, 49, 8] and req["system_version"] == ["version_5_0"]
    assert "area" not in fetch.upstream_request()  # static fields take no area


def test_a_missing_key_fails_with_instructions(monkeypatch):
    fetch = _script()
    monkeypatch.delenv("EWDS_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="EWDS_API_KEY is not set"):
        fetch.api_key()


class _Client:
    def __init__(self, write=None, error=None):
        self.write, self.error, self.calls = write, error, []

    def retrieve(self, dataset, request, target):
        self.calls.append((dataset, request))
        if self.error:
            raise self.error
        self.write(Path(target))


def test_retrieve_writes_the_netcdf_under_its_final_name(tmp_path):
    fetch = _script()
    source = tmp_path / "src.nc"
    xr.Dataset({"x": ("a", [1.0])}).to_netcdf(source)
    client = _Client(write=lambda t: t.write_bytes(source.read_bytes()))
    out = fetch.retrieve(client, "out.nc", {"k": 1}, tmp_path / "dir")
    assert out.exists() and not (tmp_path / "dir" / "out.nc.part").exists()
    assert client.calls[0][0] == "efas-historical"


def test_a_zipped_answer_is_unpacked(tmp_path):
    fetch = _script()
    source = tmp_path / "src.nc"
    xr.Dataset({"x": ("a", [1.0])}).to_netcdf(source)

    def write(target):
        with zipfile.ZipFile(target, "w") as zf:
            zf.write(source, "data_0.nc")

    out = fetch.retrieve(_Client(write=write), "out.nc", {}, tmp_path / "dir")
    assert out.read_bytes() == source.read_bytes()


def test_a_licence_refusal_says_where_to_accept_it_and_hides_the_key(tmp_path):
    fetch = _script()
    error = RuntimeError("403 Client Error: required licences not accepted for key s3cr3t")
    with pytest.raises(SystemExit) as raised:
        fetch.retrieve(_Client(error=error), "out.nc", {}, tmp_path, key="s3cr3t")
    message = str(raised.value)
    assert "CEMS-FLOODS licence" in message and "s3cr3t" not in message


def test_an_html_answer_is_not_accepted_as_data(tmp_path):
    fetch = _script()
    client = _Client(write=lambda t: t.write_bytes(b"<html>login</html>"))
    with pytest.raises(SystemExit, match="not a NetCDF"):
        fetch.retrieve(client, "out.nc", {}, tmp_path)
    assert not (tmp_path / "out.nc").exists()
