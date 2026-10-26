"""Tests for the sealed-soil layers: HERA 1 arcmin and CLMS 100 m.

Each test pins a way the figure could come out plausible and wrong: a cell
count passed off as an area at high latitude, a region off the grid read as
unsealed, a percentage file read as a fraction, a river channel counted as
sealed flood plain, an answer that depends on the tile size, and 254
"unclassifiable" read as 254 % sealed.

No network and no real data: synthetic NetCDF and GeoTIFF files in tmp_path.
The NetCDF is written with GDAL's own netCDF CreateCopy, which produces
exactly the layout of the real HERA files (`Band1`, no CRS, lat/lon in
degrees, `_FillValue` -999999).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import rasterio.shutil
from rasterio.transform import from_origin
from shapely.geometry import box

from src import sealing
from src.environment import row_cell_areas_km2

FILL = -999999.0


def _hera(path, array, transform):
    """A HERA-like NetCDF: GTiff first, then GDAL's netCDF CreateCopy."""
    tif = path.with_suffix(".tif")
    with rasterio.open(tif, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
                       count=1, dtype="float64", transform=transform, nodata=FILL) as dst:
        dst.write(array.astype("float64"), 1)
    rasterio.shutil.copy(tif, path, driver="netCDF")
    tif.unlink()
    return path


def test_synthetic_file_has_the_real_layout(tmp_path):
    """The fixture must look like the real file, or the tests prove nothing."""
    path = _hera(tmp_path / "x.nc", np.zeros((2, 2)), from_origin(0, 60, 1, 1))
    with rasterio.open(path) as src:
        assert src.crs is None
        assert src.tags(1)["NETCDF_VARNAME"] == "Band1"
        assert src.tags()["lat#units"] == "degrees_north"


@pytest.fixture
def tall(tmp_path):
    """Two columns of 1-degree cells from 70 N down to 30 N; 2010 empty, 2020 sealed in the north.

    Two columns, not one: GDAL cannot infer a cell width from a single
    longitude, and the file would load with no geotransform.
    """
    transform = from_origin(10.0, 70.0, 1.0, 1.0)
    y2010 = np.zeros((40, 2))
    y2020 = np.zeros((40, 2))
    y2020[:20] = 1.0  # 70-50 N fully sealed, 50-30 N not at all
    directory = tmp_path / "hera"
    directory.mkdir()
    _hera(directory / "fracsealed_European_01min_2010.nc", y2010, transform)
    _hera(directory / "fracsealed_European_01min_2020.nc", y2020, transform)
    admin = gpd.GeoDataFrame(
        {"nuts_id": ["COL", "OFF"]},
        geometry=[box(10.0, 30.0, 12.0, 70.0), box(50.0, 0.0, 51.0, 1.0)],
        crs="EPSG:4326",
    ).to_crs("EPSG:3035")
    return directory, transform, admin


def test_hera_is_weighted_by_true_cell_area_not_cell_count(tall):
    directory, transform, admin = tall
    frame, note = sealing.hera_by_region(admin, directory=directory)
    areas = row_cell_areas_km2(transform, range(40), 1.0)
    expected = areas[:20].sum() / areas.sum()
    share = frame.loc[0, "sealed_share_2020"]
    assert share == pytest.approx(expected, rel=1e-9)
    # A cell count would say exactly half; the northern cells are smaller.
    assert share < 0.45
    # And close to the cos(latitude) answer, which the ellipsoid refines.
    lats = 70.0 - 0.5 - np.arange(40)
    cos = np.cos(np.radians(lats))
    assert share == pytest.approx(cos[:20].sum() / cos.sum(), rel=5e-3)
    assert frame.loc[0, "sealed_share_2010"] == 0.0
    assert frame.loc[0, "sealed_change_pp_2010_2020"] == pytest.approx(share * 100)
    assert "1 of 2 units" in note


def test_hera_region_off_the_grid_is_nan_not_zero(tall):
    directory, _, admin = tall
    frame, _ = sealing.hera_by_region(admin, directory=directory)
    assert frame.loc[1].isna().all()


def test_hera_nodata_cells_are_left_out_and_reported(tmp_path):
    transform = from_origin(0.0, 50.0, 1.0, 1.0)
    values = np.array([[0.5, FILL], [0.5, FILL]])
    directory = tmp_path / "h"
    directory.mkdir()
    for year in (2010, 2020):
        _hera(directory / f"fracsealed_European_01min_{year}.nc", values, transform)
    admin = gpd.GeoDataFrame({"nuts_id": ["A"]}, geometry=[box(0, 48, 2, 50)], crs="EPSG:4326")
    frame, _ = sealing.hera_by_region(admin, directory=directory)
    assert frame.loc[0, "sealed_share_2020"] == pytest.approx(0.5)
    assert frame.loc[0, "sealed_hera_coverage"] == pytest.approx(0.5, rel=1e-3)


def test_hera_refuses_a_percentage_file(tmp_path):
    path = _hera(tmp_path / "p.nc", np.full((2, 2), 45.0), from_origin(0, 50, 1, 1))
    with pytest.raises(ValueError, match="FRACTION"):
        sealing.read_hera(path)


@pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")
def test_hera_refuses_a_file_with_no_geotransform(tmp_path):
    path = _hera(tmp_path / "g.nc", np.zeros((3, 1)), from_origin(0, 50, 1, 1))
    with pytest.raises(ValueError, match="geotransform"):
        sealing.read_hera(path)


def test_hera_missing_files_return_a_reason(tmp_path):
    admin = gpd.GeoDataFrame({"nuts_id": ["A"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    frame, why = sealing.hera_by_region(admin, directory=tmp_path)
    assert frame is None and "src.fetch" in why and "fracsealed_European_01min_2010.nc" in why


# --- CLMS --------------------------------------------------------------------

#: A 40 x 40 grid of 100 m cells in EPSG:3035, near Liege.
IMD_ORIGIN = (4_000_000.0, 3_000_000.0)


def _tif(path, array, transform, crs, dtype, nodata):
    with rasterio.open(path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
                       count=1, dtype=dtype, crs=crs, transform=transform, nodata=nodata) as dst:
        dst.write(array.astype(dtype), 1)
    return str(path)


@pytest.fixture
def clms(tmp_path):
    """IMD: left half 80 % sealed, right half 20 %; a 254 strip; hazard over the left quarter.

    The hazard is a fine 4326 grid covering the whole tile. The left 10 IMD
    columns are 1 m deep; within them, the top 10 rows are permanent water.
    """
    imd_t = from_origin(*IMD_ORIGIN, 100.0, 100.0)
    imd = np.full((40, 40), 20, dtype="uint8")
    imd[:, :20] = 80
    imd[:, 39] = sealing.CLMS_UNCLASSIFIABLE
    directory = tmp_path / "clms"
    directory.mkdir()
    imd_path = _tif(directory / "IMD_2018_100m_eu_03035_v020.tif", imd, imd_t, "EPSG:3035",
                    "uint8", sealing.CLMS_OUTSIDE)

    from rasterio.warp import transform_bounds
    w, s, e, n = transform_bounds("EPSG:3035", "EPSG:4326",
                                  IMD_ORIGIN[0] - 2000, IMD_ORIGIN[1] - 6000,
                                  IMD_ORIGIN[0] + 6000, IMD_ORIGIN[1] + 2000)
    step = 1 / 1200
    width, height = int((e - w) / step) + 1, int((n - s) / step) + 1
    haz_t = from_origin(w, n, step, step)
    # Depth decided per hazard cell by where its centre falls on the IMD grid.
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    lon, lat = haz_t @ (cols + 0.5, rows + 0.5)
    from pyproj import Transformer
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True).transform(lon, lat)
    icol = np.floor((x - IMD_ORIGIN[0]) / 100.0)
    irow = np.floor((IMD_ORIGIN[1] - y) / 100.0)
    depth = np.where((icol >= 0) & (icol < 10) & (irow >= 0) & (irow < 40), 1.0, -9999.0)
    water = np.where((icol >= 0) & (icol < 10) & (irow >= 0) & (irow < 10), 1.0, 0.0)
    hazard = _tif(tmp_path / "haz.tif", depth, haz_t, "EPSG:4326", "float32", -9999.0)
    pw = _tif(tmp_path / "pw.tif", water, haz_t, "EPSG:4326", "float64", -9999.0)
    sp = _tif(tmp_path / "sp.tif", np.zeros_like(water), haz_t, "EPSG:4326", "float64", -9999.0)
    footprint = sealing.Footprint(hazard_path=hazard, masks=(pw, sp))
    x0, y0 = IMD_ORIGIN
    admin = gpd.GeoDataFrame(
        {"nuts_id": ["LEFT", "RIGHT", "FAR"]},
        geometry=[box(x0, y0 - 4000, x0 + 2000, y0), box(x0 + 2000, y0 - 4000, x0 + 4000, y0),
                  box(x0 + 50_000, y0, x0 + 51_000, y0 + 1000)],
        crs="EPSG:3035",
    )
    return directory, imd_path, footprint, admin


def test_clms_shares_footprint_and_masks(clms):
    directory, _, footprint, admin = clms
    frame, note = sealing.clms_by_region(admin.iloc[:2], footprint, directory=directory, tile=16)
    assert frame.loc[0, "imperviousness_share_2018"] == pytest.approx(0.8)
    assert frame.loc[0, "imperviousness_coverage_2018"] == 1.0
    # 254 is left out of the right half: 19 columns at 0.2, never 254 %.
    assert frame.loc[1, "imperviousness_share_2018"] == pytest.approx(0.2)
    assert frame.loc[1, "imperviousness_coverage_2018"] == pytest.approx(19 / 20)
    # Footprint: left 10 columns, rows 10-39 (top 10 are permanent water) -> 300 cells at 80 %.
    assert frame.loc[0, "imperviousness_rp100_footprint_km2"] == pytest.approx(300 * 0.01, rel=0.02)
    assert frame.loc[0, "imperviousness_share_in_rp100_2018"] == pytest.approx(0.8)
    # The right half has no footprint: NaN, not "unsealed flood plain".
    assert np.isnan(frame.loc[1, "imperviousness_share_in_rp100_2018"])
    assert "RP100" in note


def test_clms_permanent_water_is_excluded_from_the_footprint(clms):
    directory, _, footprint, admin = clms
    unmasked = sealing.Footprint(hazard_path=footprint.hazard_path, masks=())
    with_masks, _ = sealing.clms_by_region(admin.iloc[:1], footprint, directory=directory)
    without, _ = sealing.clms_by_region(admin.iloc[:1], unmasked, directory=directory)
    a = with_masks.loc[0, "imperviousness_rp100_footprint_km2"]
    b = without.loc[0, "imperviousness_rp100_footprint_km2"]
    assert b == pytest.approx(4.0, rel=0.02) and a == pytest.approx(3.0, rel=0.02)


def test_clms_result_does_not_depend_on_tile_size(clms):
    directory, _, footprint, admin = clms
    small, _ = sealing.clms_by_region(admin.iloc[:2], footprint, directory=directory, tile=7)
    large, _ = sealing.clms_by_region(admin.iloc[:2], footprint, directory=directory, tile=4096)
    assert np.allclose(small.to_numpy(), large.to_numpy(), equal_nan=True)


def test_clms_region_off_the_raster_is_nan(clms):
    directory, _, footprint, admin = clms
    frame, _ = sealing.clms_by_region(admin, footprint, directory=directory)
    assert frame.loc[2].isna().all()


def test_clms_reads_the_tif_inside_the_zip(clms, tmp_path):
    import zipfile
    _, imd_path, _, _ = clms
    zdir = tmp_path / "zipped"
    zdir.mkdir()
    with zipfile.ZipFile(zdir / "IMD_2018_100m_eu_03035_v020.zip", "w") as zf:
        zf.write(imd_path, "IMD_2018_100m_eu_03035_v020/IMD_2018_100m_eu_03035_v020.tif")
    path = sealing.clms_path(zdir)
    assert path.startswith("zip://")
    with rasterio.open(path) as src:
        assert src.shape == (40, 40)


def test_clms_absent_gives_download_instructions(tmp_path):
    admin = gpd.GeoDataFrame({"nuts_id": ["A"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:3035")
    frame, why = sealing.clms_by_region(admin, directory=tmp_path / "nothing")
    assert frame is None
    assert "EU Login" in why and "IMD_2018_100m_eu_03035_v020" in why
