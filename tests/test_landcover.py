"""Tests for `src/landcover.py`: what land the flood footprint covers.

Synthetic rasters only. Pinned: the CORINE codes fall into the right groups,
only footprint cells count, masked permanent water is out, the shares sum to
one, and a region with no footprint is NaN rather than 0.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from src import landcover
from src.sealing import Footprint


def _tif(path, data, crs, transform, nodata=None, dtype="float32"):
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1],
                       count=1, dtype=dtype, crs=crs, transform=transform, nodata=nodata) as dst:
        dst.write(data.astype(dtype), 1)
    return str(path)


def test_codes_fall_into_their_groups():
    codes = np.array([111, 112, 121, 122, 133, 211, 311, 412, 512, 999])
    names = list(landcover.GROUPS)
    got = [names[g - 1] if g else None for g in landcover.group_of(codes)]
    assert got == ["homes", "homes", "industry_commerce", "transport", "other_artificial",
                   "agriculture", "natural", "natural", "water", None]


def test_shares_count_only_the_footprint_and_sum_to_one(tmp_path):
    """Left half homes, right half agriculture; the flood covers the left three
    quarters, minus a masked permanent-water column."""
    clc = np.full((10, 10), 211)
    clc[:, :5] = 112
    origin = from_origin(4_000_000, 3_001_000, 100, 100)
    clc_path = _tif(tmp_path / "clc.tif", clc, "EPSG:3035", origin, nodata=999, dtype="int16")
    depth = np.zeros((10, 10))
    depth[:, :8] = 1.0
    water = np.full((10, 10), np.nan)
    water[:, 0] = 1.0
    hazard = _tif(tmp_path / "rp100.tif", depth, "EPSG:3035", origin, nodata=-9999)
    mask = _tif(tmp_path / "water.tif", water, "EPSG:3035", origin)
    admin = gpd.GeoDataFrame({"nuts_id": ["A", "DRY"]},
                             geometry=[box(4_000_000, 3_000_000, 4_001_000, 3_001_000),
                                       box(5_000_000, 3_000_000, 5_001_000, 3_001_000)],
                             crs="EPSG:3035")
    out = landcover.landcover_by_region(clc_path, admin, Footprint(hazard_path=hazard, masks=(mask,)))
    row = out.iloc[0]
    # 7 footprint columns x 10 rows: 4 columns of homes (col 0 masked), 3 of agriculture.
    assert row["corine_rp100_footprint_km2"] == np.float64(70 * 0.01)
    assert row["corine_rp100_share_homes"] == np.float64(4 / 7)
    assert row["corine_rp100_share_agriculture"] == np.float64(3 / 7)
    shares = [c for c in out.columns if "_share_" in c]
    assert np.isclose(row[shares].sum(), 1.0)
    assert np.isnan(out.iloc[1]["corine_rp100_footprint_km2"]), "no footprint: not measured, not 0"


def test_the_real_raster_numbers_its_classes_1_to_44():
    """The 100 m raster holds positions 1..44 (and 48 for no data), not CLC codes:
    read as codes, nothing matched and the first run measured 0 regions."""
    assert landcover.to_codes(np.array([1, 2, 3, 12, 23, 40, 44, 48, -128])).tolist() == (
        [111, 112, 121, 211, 311, 511, 523, 0, 0]
    )
    assert landcover.to_codes(np.array([112, 999])).tolist() == [112, 0]
    assert len(landcover.CLC_CODES) == 44
