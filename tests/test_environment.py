"""Tests for the Natura 2000 layer: protected area on flood-prone ground.

Each test pins a way the figure could come out plausible and wrong: an overlap
counted twice, a cell count passed off as an area, a lake counted as flooded
nature, an answer that depends on the window size, and a country outside the
network reported as having no protected land.

No network and no real data: a 10 x 10 geographic raster written to tmp_path.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from src import environment

#: 0.01 degree cells from 4.00 E / 51.00 N, ten by ten.
TRANSFORM = from_origin(4.0, 51.0, 0.01, 0.01)


def _tif(path, array, nodata=-9999.0):
    with rasterio.open(
        path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1],
        count=1, dtype="float32", crs="EPSG:4326", transform=TRANSFORM,
        nodata=nodata,
    ) as dst:
        dst.write(array.astype("float32"), 1)
    return str(path)


def _cells(col0, row0, col1, row1):
    """The box covering whole cells [col0, col1) x [row0, row1) of the grid."""
    return box(4.0 + col0 * 0.01, 51.0 - row1 * 0.01,
               4.0 + col1 * 0.01, 51.0 - row0 * 0.01)


@pytest.fixture
def scene(tmp_path):
    """Two regions side by side; the left five columns are 1 m deep."""
    depth = np.full((10, 10), -9999.0)
    depth[:, :5] = 1.0
    hazard = _tif(tmp_path / "haz.tif", depth)
    admin = gpd.GeoDataFrame(
        {"nuts_id": ["W", "E"], "country": ["BE", "BE"]},
        geometry=[_cells(0, 0, 5, 10), _cells(5, 0, 10, 10)],
        crs="EPSG:4326",
    )
    return tmp_path, hazard, admin


def _sites(*geoms, country="BE"):
    return gpd.GeoDataFrame(
        {"country": [country] * len(geoms)}, geometry=list(geoms), crs="EPSG:4326"
    )


def _cell_km2(row):
    return environment.row_cell_areas_km2(TRANSFORM, range(row, row + 1), 0.01)[0]


def test_overlapping_sites_are_counted_once(scene):
    """An SPA drawn over an SAC is one piece of ground. Summing site areas would
    report the overlap twice; the mask is a union."""
    _, hazard, admin = scene
    one = _sites(_cells(0, 0, 2, 2))
    two = _sites(_cells(0, 0, 2, 2), _cells(0, 0, 2, 2), _cells(1, 1, 2, 2))
    a = environment.flooded_protected_area(hazard, one, admin)
    b = environment.flooded_protected_area(hazard, two, admin)
    assert b.loc[0, "protected_km2"] == pytest.approx(a.loc[0, "protected_km2"])


def test_the_area_is_an_area_not_a_cell_count(scene):
    """A degree cell shrinks east-west with latitude; the figure is km2 from the
    ellipsoid, row by row."""
    _, hazard, admin = scene
    out = environment.flooded_protected_area(hazard, _sites(_cells(0, 0, 2, 2)), admin)
    expected = 2 * _cell_km2(0) + 2 * _cell_km2(1)
    assert out.loc[0, "protected_km2"] == pytest.approx(expected)
    # About 1.11 km north-south by 0.70 km east-west at 51 N.
    assert 0.7 < _cell_km2(0) < 0.8


def test_cell_areas_follow_the_latitude():
    """Close to cos(latitude), and not exactly: on the ellipsoid a degree of
    latitude is about 1 % longer at 60 N than at the equator, so the ratio is
    0.505 where the sphere says 0.500."""
    north = environment.row_cell_areas_km2(from_origin(0, 60.01, 0.01, 0.01), range(1), 0.01)
    equator = environment.row_cell_areas_km2(from_origin(0, 0.01, 0.01, 0.01), range(1), 0.01)
    assert north[0] / equator[0] == pytest.approx(np.cos(np.radians(60.005)), rel=0.02)


def test_flooded_needs_water_deeper_than_the_threshold(scene):
    tmp_path, _, admin = scene
    depth = np.full((10, 10), -9999.0)
    depth[0, 0] = 0.3
    depth[0, 1] = 0.8
    hazard = _tif(tmp_path / "shallow.tif", depth)
    out = environment.flooded_protected_area(
        hazard, _sites(_cells(0, 0, 2, 1)), admin, min_depth_m=0.5
    )
    assert out.loc[0, "protected_flooded_km2"] == pytest.approx(_cell_km2(0))
    assert out.loc[0, "protected_km2"] == pytest.approx(2 * _cell_km2(0))


def test_a_lake_inside_a_site_is_not_flooded_nature(scene):
    """Permanent water is patched into the depth rasters at 1.00 m; masked, as in
    the exposure table, it leaves the flooded figure but stays protected area."""
    tmp_path, hazard, admin = scene
    lake = np.full((10, 10), np.nan)
    lake[0, 0] = 1.0
    mask = _tif(tmp_path / "lake.tif", lake, nodata=None)
    site = _sites(_cells(0, 0, 2, 1))
    kept = environment.flooded_protected_area(hazard, site, admin)
    masked = environment.flooded_protected_area(hazard, site, admin, masks=[mask])
    assert kept.loc[0, "protected_flooded_km2"] == pytest.approx(2 * _cell_km2(0))
    assert masked.loc[0, "protected_flooded_km2"] == pytest.approx(_cell_km2(0))
    assert masked.loc[0, "protected_km2"] == pytest.approx(kept.loc[0, "protected_km2"])


@pytest.mark.parametrize("rows", [1, 2, 3, 7, 10, 64])
def test_the_answer_does_not_depend_on_the_window(scene, rows):
    """Hazard-grid windows are exact here because nothing is resampled: each cell
    is read once and added to one region."""
    _, hazard, admin = scene
    site = _sites(_cells(1, 1, 8, 9), _cells(3, 0, 6, 4))
    reference = environment.flooded_protected_area(hazard, site, admin, window_rows=10)
    out = environment.flooded_protected_area(hazard, site, admin, window_rows=rows)
    np.testing.assert_allclose(out.to_numpy(), reference.to_numpy())


def test_a_region_off_the_grid_is_not_measured(scene):
    _, hazard, admin = scene
    far = gpd.GeoDataFrame(
        {"nuts_id": ["X"], "country": ["BE"]}, geometry=[box(20, 20, 21, 21)],
        crs="EPSG:4326",
    )
    out = environment.flooded_protected_area(hazard, _sites(_cells(0, 0, 1, 1)), far)
    assert out.loc[0, "grid_coverage"] == 0.0
    assert np.isnan(out.loc[0, "protected_km2"])


def test_a_country_outside_the_network_is_none_not_zero(scene):
    """The GeoPackage covers the EU-27. A Swiss region has no Natura site because
    the network does not exist there, which is not 0 km2 of protected land."""
    _, hazard, admin = scene
    admin = admin.assign(country=["BE", "CH"])
    out = environment.natura_by_region(
        hazard, admin, return_period=100, protected=_sites(_cells(0, 0, 2, 2)),
    )
    assert out.loc[0, "natura2000_km2"] > 0
    assert np.isnan(out.loc[1, "natura2000_km2"])
    assert np.isnan(out.loc[1, "natura2000_flooded_share_rp100"])


def test_the_share_is_none_where_there_is_nothing_to_share(scene):
    """A region with no protected area has no share: 0 % of nothing would rank
    it as the region whose nature is safest."""
    _, hazard, admin = scene
    out = environment.natura_by_region(
        hazard, admin, return_period=100, protected=_sites(_cells(0, 0, 2, 2)),
    )
    assert out.loc[0, "natura2000_flooded_share_rp100"] == pytest.approx(1.0)
    assert out.loc[1, "natura2000_km2"] == 0.0
    assert np.isnan(out.loc[1, "natura2000_flooded_share_rp100"])


def test_greece_is_el_in_both_files(scene):
    """GISCO writes Greece EL and the end-2024 GeoPackage writes GR (446 sites,
    measured 2026-10-12); compared raw, every Greek region would fall outside
    the network."""
    _, hazard, admin = scene
    admin = admin.assign(country=["EL", "EL"])
    out = environment.natura_by_region(
        hazard, admin, return_period=100,
        protected=_sites(_cells(0, 0, 2, 2), country="GR"),
    )
    assert out.loc[0, "natura2000_km2"] > 0


def test_a_missing_geopackage_says_how_to_get_it(tmp_path):
    with pytest.raises(environment.NaturaUnavailable, match="eea_natura2000_gpkg"):
        environment.sites(tmp_path / "absent.gpkg")


def test_the_site_layer_is_read_by_name(tmp_path):
    """The release declares its geometry type "Unknown", so the layer is named,
    and a file without it is refused rather than read from the wrong table."""
    path = tmp_path / "n2k.gpkg"
    _sites(_cells(0, 0, 1, 1)).rename(columns={"country": "MS"}).to_file(
        path, layer=environment.SITE_LAYER, driver="GPKG"
    )
    frame = environment.sites(path)
    assert list(frame.columns) == ["country", "geometry"]
    assert frame["country"].iat[0] == "BE"

    other = tmp_path / "other.gpkg"
    _sites(_cells(0, 0, 1, 1)).to_file(other, layer="something_else", driver="GPKG")
    with pytest.raises(environment.NaturaUnavailable, match="NaturaSite_polygon"):
        environment.sites(other)
