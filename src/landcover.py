"""What the flood footprint covers: CORINE Land Cover 2018 inside the RP100 zone.

The kit counts people and built-up square metres; neither tells a flooded
housing estate from a flooded industrial park or a flooded meadow, and the
Floods Directive asks the risk maps for both "the type of economic activity"
and the environmental consequence (Article 6(5)). CORINE answers it: per
region, the share of the flood footprint under each kind of land.

Same footprint as every other figure (depth strictly above 0.5 m, permanent
water and spurious areas masked, `sealing.Footprint`), read on the CORINE 100 m
grid tile by tile with the footprint reprojected by nearest neighbour - the
machinery of `src/sealing.py`, so the two layers agree cell for cell.

The CORINE classes are grouped into what a decision differs on, not into the
44 classes: homes, industry and commerce, transport, other artificial land,
agriculture, natural land (forests, semi-natural, wetlands) and water. Shares
are fractions of the footprint's classified area; a region with no footprint
cell is NaN, never 0.
"""

from __future__ import annotations

import zipfile
from contextlib import ExitStack
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from shapely.geometry import box

from src.data_io import DATA
from src.sealing import DEFAULT_TILE, Footprint, _footprint_on

CORINE_DIR = DATA / "raw" / "download" / "clms_corine_2018"

#: CORINE codes grouped into the land uses a flood decision differs on.
#: Inclusive ranges of the three-digit CLC code.
GROUPS = {
    "homes": (111, 112),
    "industry_commerce": (121, 121),
    "transport": (122, 124),
    "other_artificial": (131, 142),
    "agriculture": (211, 244),
    "natural": (311, 423),
    "water": (511, 523),
}

#: The 44 CLC codes in the order the 100 m raster numbers them. The raster does
#: NOT hold the codes: measured on the real file (2026-10-25), it is int8 with
#: values 1..44 and 48 for no data, and its attribute table (`.tif.vat.dbf`,
#: columns Value / CODE_18) maps Value 1 -> 111 ... Value 44 -> 523. The first
#: version read the values as codes and measured 0 regions.
CLC_CODES = np.array([
    111, 112, 121, 122, 123, 124, 131, 132, 133, 141, 142,
    211, 212, 213, 221, 222, 223, 231, 241, 242, 243, 244,
    311, 312, 313, 321, 322, 323, 324, 331, 332, 333, 334, 335,
    411, 412, 421, 422, 423, 511, 512, 521, 522, 523,
])


def to_codes(values: np.ndarray) -> np.ndarray:
    """Raster values as CLC codes: 1..44 through `CLC_CODES`, three-digit codes as
    they are (a raster that already carries them), anything else 0 (no data)."""
    values = values.astype("int32")
    codes = np.zeros(values.shape, dtype="int32")
    indexed = (values >= 1) & (values <= len(CLC_CODES))
    codes[indexed] = CLC_CODES[values[indexed] - 1]
    direct = (values >= 111) & (values <= 523)
    codes[direct] = values[direct]
    return codes


def corine_path(directory: Path | str = CORINE_DIR) -> str | None:
    """A GDAL path to the CORINE 2018 100 m GeoTIFF (packed or not), or None."""
    directory = Path(directory)
    if not directory.exists():
        return None
    tifs = sorted(p for p in directory.rglob("U2018_CLC2018_*.tif") if "French_DOMs" not in str(p))
    if tifs:
        return str(tifs[0])
    for archive in sorted(directory.glob("*.zip")):
        with zipfile.ZipFile(archive) as zf:
            inside = [n for n in zf.namelist()
                      if n.lower().endswith(".tif") and "U2018_CLC2018" in n and "French_DOMs" not in n]
        if inside:
            return f"zip://{archive.as_posix()}!/{inside[0]}"
    return None


def group_of(codes: np.ndarray) -> np.ndarray:
    """The group index (1-based, in `GROUPS` order) of each CORINE code, 0 for none."""
    out = np.zeros(codes.shape, dtype="int16")
    for i, (low, high) in enumerate(GROUPS.values(), start=1):
        out[(codes >= low) & (codes <= high)] = i
    return out


def landcover_by_region(
    clc_path: str,
    admin: gpd.GeoDataFrame,
    footprint: Footprint,
    *,
    tile: int = DEFAULT_TILE,
) -> pd.DataFrame:
    """Share of each region's flood footprint under each land-use group.

    Columns on `admin.index`: `corine_rp<N>_footprint_km2` (classified CORINE
    area in the footprint) and `corine_rp<N>_share_<group>` for every group.
    Each 100 m cell belongs to the region containing its centre and to exactly
    one tile, so the sums do not depend on the tile size.
    """
    n, k = len(admin), len(GROUPS)
    counts = np.zeros((n, k))
    with ExitStack() as stack:
        clc = stack.enter_context(rasterio.open(clc_path))
        if clc.crs is None or not clc.crs.is_projected:
            raise ValueError(f"{clc_path} is {clc.crs}, expected EPSG:3035")
        hazard = stack.enter_context(rasterio.open(footprint.hazard_path))
        masks = [stack.enter_context(rasterio.open(m)) for m in footprint.masks]
        cell_km2 = abs(clc.transform.a * clc.transform.e) / 1e6
        units = admin.to_crs(clc.crs).geometry.reset_index(drop=True)
        index = units.sindex
        for row0 in range(0, clc.height, tile):
            for col0 in range(0, clc.width, tile):
                window = Window(col0, row0, min(tile, clc.width - col0), min(tile, clc.height - row0))
                hits = index.query(box(*rasterio.windows.bounds(window, clc.transform)), predicate="intersects")
                if len(hits) == 0:
                    continue
                transform = clc.window_transform(window)
                shape = (int(window.height), int(window.width))
                region = rasterize(((units.iloc[i], int(i) + 1) for i in hits),
                                   out_shape=shape, transform=transform, fill=0, dtype="int32")
                if not (region > 0).any():
                    continue
                groups = group_of(to_codes(clc.read(1, window=window)))
                keep = (region > 0) & (groups > 0)
                if not keep.any():
                    continue
                wet = keep & _footprint_on(transform, shape, clc.crs, hazard, masks, footprint)
                if not wet.any():
                    continue
                pairs = (region[wet] - 1) * k + (groups[wet] - 1)
                counts += np.bincount(pairs, minlength=n * k).reshape(n, k)

    rp = footprint.return_period
    total = counts.sum(axis=1)
    out = pd.DataFrame({f"corine_rp{rp}_footprint_km2": np.where(total > 0, total * cell_km2, np.nan)},
                       index=admin.index)
    with np.errstate(invalid="ignore", divide="ignore"):
        for j, name in enumerate(GROUPS):
            out[f"corine_rp{rp}_share_{name}"] = np.where(total > 0, counts[:, j] / total, np.nan)
    return out


def by_region(admin: gpd.GeoDataFrame, footprint: Footprint | None = None, *,
              directory: Path | str = CORINE_DIR, tile: int = DEFAULT_TILE):
    """The CORINE columns of `context.parquet`, or `(None, reason)`."""
    footprint = footprint or Footprint()
    path = corine_path(directory)
    if path is None:
        return None, (f"no U2018_CLC2018 GeoTIFF or ZIP in {directory}: download "
                      "'u2018_clc2018_v2020_20u1_raster100m' from land.copernicus.eu (EU Login)")
    frame = landcover_by_region(path, admin, footprint, tile=tile)
    measured = int(frame[f"corine_rp{footprint.return_period}_footprint_km2"].notna().sum())
    return frame, f"CORINE 2018 100 m in the RP{footprint.return_period} footprint; {measured} regions measured"
