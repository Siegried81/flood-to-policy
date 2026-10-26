"""Sealed soil per region: the runoff side of flood risk the river maps leave out.

The JRC hazard maps model rivers leaving their banks. Water that never reaches a
river - rain falling on concrete and running down the street, much of what hit
Wallonia in July 2021 - is not in them. How much of a region is sealed is the
first-order proxy for that surface runoff, and its change over a decade says
whether a region is making it worse. Two sources, two readings:

* **HERA sealed fraction** (`hera_sealed_fraction` in config/sources.yaml), the
  JRC's yearly 1 arcmin layer, no account needed. Read for 2010 and 2020, the
  epochs of the GHSL comparison. `hera_by_region`.
* **CLMS Imperviousness Density 2018** (`clms_imperviousness_2018`), 100 m,
  behind EU Login. Fine enough to read the sealing INSIDE the RP100 flood
  footprint, which says whether the flood plain itself is paved. `clms_by_region`.

**A fraction is averaged by area, never summed.** Both layers hold a sealed
share per cell, so a region's figure is the area-weighted mean of its cells.
What "area" means differs between the two grids:

* HERA is a geographic grid. A 1 arcmin cell is about 1.85 km north-south
  everywhere, but its east-west width shrinks with the cosine of the latitude:
  a cell at 70 N covers about half the ground of a cell at 37 N. A plain mean of
  cells would overweight the north of every region and Scandinavia against the
  Mediterranean. Each row's true cell area is computed on the WGS84 ellipsoid
  (`environment.row_cell_areas_km2`, the same helper as the Natura figures).
* CLMS is on EPSG:3035, an equal-area projection: every 100 m cell is the same
  0.01 km2, so the plain mean of the cells already IS the area-weighted mean.

**Shares are in [0, 1], changes in percentage points.** The HERA file stores a
fraction (measured 2026-10-24 on both epochs: `Band1`, min 0.0, max 0.99999);
the CLMS layer stores whole percent and is divided by 100 here, so the two
sources share one unit and match every other `*_share_*` column of
`context.parquet`. A change between two shares is reported in percentage
points (`sealed_change_pp_2010_2020`), never as a percent change: a region going
from 1 % to 2 % sealed has not "doubled its risk".

**Not measured is NaN, never 0.** A region with no valid cell (off the HERA
domain, or entirely unclassifiable in CLMS) reads NaN; a region too small to
hold one cell centre of the 1 arcmin grid reads NaN too, not "unsealed". The
`*_coverage` columns give the share of each region's cells that carried a value,
so a figure measured on half a region can be read as such.
"""

from __future__ import annotations

import zipfile
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window
from shapely.geometry import box

from src.data_io import DATA
from src.environment import row_cell_areas_km2

DOWNLOAD = DATA / "raw" / "download"
HERA_DIR = DOWNLOAD / "hera_sealed_fraction"
HERA_NAME = "fracsealed_European_01min_{year}.nc"
HERA_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-EFAS/HERA/VER1-0/"
    "Data/NetCDF/socioeconomic_maps/landuse/"
)
HERA_YEARS = (2010, 2020)

#: The HERA files carry no CRS (GDAL reports `crs=None`), only `lat`/`lon`
#: coordinate variables in degrees. Measured 2026-10-24 on both epochs. The
#: grid is the EFAS 1 arcmin grid, which config/sources.yaml declares as
#: EPSG:4326; it is assigned only after the units confirm degrees.
HERA_CRS = "EPSG:4326"

CLMS_DIR = DOWNLOAD / "clms_imperviousness_2018"
CLMS_URL = (
    "https://land.copernicus.eu/en/products/high-resolution-layer-imperviousness/"
    "imperviousness-density-2018"
)
#: Pixel codes of the IMD 2018 layers, from Table 7 of the product user manual
#: ("HRL Imperviousness 2018 user manual", CLMS technical library): 0-100 is
#: the sealed percentage, 254 "unclassifiable (no satellite image available, or
#: clouds, shadows, or snow)", 255 "outside area". 254 is NOT zero sealing: it is
#: a cell nobody could see, and it is left out of both the mean and coverage.
CLMS_MAX_VALUE = 100
CLMS_UNCLASSIFIABLE = 254
CLMS_OUTSIDE = 255

HAZARD_DIR = DOWNLOAD / "jrc_flood_hazard"

#: CLMS cells per tile side. Memory only: tiles are disjoint and every 100 m
#: cell is read once. 2,048 x 2,048 cells is a 205 km square; the hazard window
#: under it is a few million 3 arc-second cells, well under 1 GB with the masks.
DEFAULT_TILE = 2048


def _hera_path(year: int, directory: Path) -> Path:
    return Path(directory) / HERA_NAME.format(year=year)


def read_hera(path: str | Path) -> tuple[np.ma.MaskedArray, rasterio.Affine]:
    """One HERA sealed-fraction grid as a masked float64 array, and its transform.

    The whole 2,970 x 4,530 grid is about 108 MB in float64, so it is read at
    once rather than windowed. Refuses a file whose coordinates are not degrees,
    whose values leave [0, 1] (a percentage layer would be read as 100 times
    too sealed), that GDAL could not georeference (it then returns the
    identity transform and every cell would sit near 0 N, 0 E), or that
    carries more than one band (a multi-year file would
    silently be read as its first year).
    """
    with rasterio.open(path) as src:
        if src.count != 1:
            raise ValueError(f"{Path(path).name} has {src.count} bands, expected 1")
        if src.crs is None:
            tags = src.tags()
            if tags.get("lat#units") != "degrees_north" or tags.get("lon#units") != "degrees_east":
                raise ValueError(
                    f"{Path(path).name} has no CRS and its lat/lon are not in degrees; "
                    "refusing to guess."
                )
        elif not src.crs.is_geographic:
            raise ValueError(f"{Path(path).name} is {src.crs}, expected a lat/lon grid")
        if src.transform.is_identity:
            raise ValueError(
                f"{Path(path).name} loaded with no geotransform; its lat/lon "
                "coordinates could not be read as a regular grid."
            )
        values = src.read(1, masked=True).astype("float64")
        transform = src.transform
    values = np.ma.masked_invalid(values)
    if values.count() and (values.min() < 0.0 or values.max() > 1.0 + 1e-6):
        raise ValueError(
            f"{Path(path).name} holds values in [{values.min()}, {values.max()}]; "
            "a sealed FRACTION in [0, 1] was expected."
        )
    return values, transform


def hera_shares(
    grids: dict[int, tuple[np.ma.MaskedArray, rasterio.Affine]],
    admin: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Area-weighted sealed share per region and year, on cells valid in EVERY year.

    `grids` maps a year to `(values, transform)` from `read_hera`; all must share
    one grid. Returns a frame on `admin.index` with `sealed_share_<year>` per
    year and `sealed_hera_coverage`, the share of the region's on-grid area that
    carried a value in every year.

    One common mask for all years, so the change between two years is the
    change in sealing and not a change in which cells were measured. A cell
    belongs to the region containing its centre (`all_touched=False`), so no
    cell is counted in two regions.
    """
    years = sorted(grids)
    first_values, transform = grids[years[0]]
    shape = first_values.shape
    for year in years[1:]:
        values, other = grids[year]
        if values.shape != shape or other != transform:
            raise ValueError(f"HERA {year} is not on the {years[0]} grid")

    n = len(admin)
    units = admin.to_crs(HERA_CRS).geometry.reset_index(drop=True)
    # Unit ids start at 1 so that 0 means "no unit".
    region = rasterize(
        ((geom, i + 1) for i, geom in enumerate(units) if geom is not None and not geom.is_empty),
        out_shape=shape, transform=transform, fill=0, dtype="int32", all_touched=False,
    )
    areas = np.broadcast_to(
        row_cell_areas_km2(transform, range(shape[0]), abs(transform.a))[:, None], shape
    )
    valid = region > 0
    on_grid = np.bincount(region[valid], weights=areas[valid], minlength=n + 1)[1:]
    for year in years:
        valid &= ~np.ma.getmaskarray(grids[year][0])
    measured = np.bincount(region[valid], weights=areas[valid], minlength=n + 1)[1:]

    out = pd.DataFrame(index=admin.index)
    with np.errstate(invalid="ignore", divide="ignore"):
        for year in years:
            values = np.ma.getdata(grids[year][0])
            sealed = np.bincount(
                region[valid], weights=(values * areas)[valid], minlength=n + 1
            )[1:]
            out[f"sealed_share_{year}"] = np.where(measured > 0, sealed / measured, np.nan)
        out["sealed_hera_coverage"] = np.where(on_grid > 0, measured / on_grid, np.nan)
    return out


def hera_by_region(
    admin: gpd.GeoDataFrame,
    *,
    years: tuple[int, int] = HERA_YEARS,
    directory: Path | str = HERA_DIR,
) -> tuple[pd.DataFrame | None, str]:
    """The HERA sealing columns of `context.parquet`, or `(None, reason)`.

    Columns: `sealed_share_<y0>`, `sealed_share_<y1>` (fractions in [0, 1]),
    `sealed_change_pp_<y0>_<y1>` (percentage points) and `sealed_hera_coverage`.
    """
    directory = Path(directory)
    missing = [p.name for p in (_hera_path(y, directory) for y in years) if not p.exists()]
    if missing:
        return None, (
            f"{', '.join(missing)} absent from {directory} - run `python -m src.fetch` "
            f"(`hera_sealed_fraction` in config/sources.yaml) or download from {HERA_URL}"
        )
    grids = {y: read_hera(_hera_path(y, directory)) for y in years}
    frame = hera_shares(grids, admin)
    y0, y1 = years
    frame[f"sealed_change_pp_{y0}_{y1}"] = (
        frame[f"sealed_share_{y1}"] - frame[f"sealed_share_{y0}"]
    ) * 100.0
    frame = frame[[f"sealed_share_{y0}", f"sealed_share_{y1}",
                   f"sealed_change_pp_{y0}_{y1}", "sealed_hera_coverage"]]
    measured = int(frame[f"sealed_share_{y1}"].notna().sum())
    return frame, (
        f"HERA 1 arcmin, {y0} and {y1}, area-weighted on the WGS84 ellipsoid; "
        f"{measured} of {len(admin)} units measured"
    )


@dataclass(frozen=True)
class Footprint:
    """What "inside the flood footprint" means: the exposure table's definition.

    A cell is in the footprint when the modelled depth is above `min_depth_m`
    and neither mask flags it. Strictly above, as in `src/exposure.py`, so the
    footprint is the one the exposure figures are counted on.
    """

    hazard_path: str = str(HAZARD_DIR / "Europe_RP100_filled_depth.tif")
    masks: tuple[str, ...] = field(default_factory=lambda: (
        str(HAZARD_DIR / "Europe_permanent_water_bodies.tif"),
        str(HAZARD_DIR / "Europe_spurious_depth_areas.tif"),
    ))
    min_depth_m: float = 0.5
    return_period: int = 100


def clms_path(directory: Path | str = CLMS_DIR) -> str | None:
    """A GDAL path to the IMD 2018 100 m GeoTIFF, or None if it is not there.

    The CLMS download is a ZIP (`IMD_2018_100m_eu_03035_v020.zip`, 66 MB); it is
    read in place through `zip://` if left packed, so the user can drop either
    the archive or the unpacked .tif in the folder.
    """
    directory = Path(directory)
    if not directory.exists():
        return None
    tifs = sorted(p for p in directory.rglob("*.tif") if "IMD_2018_100m" in p.name)
    if tifs:
        return str(tifs[0])
    for archive in sorted(directory.glob("*.zip")):
        with zipfile.ZipFile(archive) as zf:
            inside = [n for n in zf.namelist()
                      if n.lower().endswith(".tif") and "IMD_2018_100m" in n]
        if inside:
            return f"zip://{archive.as_posix()}!/{inside[0]}"
    return None


def _footprint_on(
    tile_transform, shape, tile_crs, hazard, masks, footprint: Footprint
) -> np.ndarray:
    """The flood footprint resampled onto one CLMS tile, as a boolean array.

    Nearest neighbour, never an average: a 100 m cell takes the depth of the
    3 arc-second hazard cell under its centre, so the footprint stays a yes/no
    reading of the same depths the exposure table thresholds. Only the hazard
    rows and columns under the tile are read (plus a two-cell margin), never the
    full width: a CLMS tile is a square in EPSG:3035, which in degrees is a
    bounded quadrilateral, so `transform_bounds` with densified edges is safe
    here - unlike the global Mollweide row bands of the exposure build.
    """
    left, bottom, right, top = rasterio.transform.array_bounds(*shape, tile_transform)
    w, s, e, n = transform_bounds(tile_crs, hazard.crs, left, bottom, right, top, densify_pts=21)
    inv = ~hazard.transform
    c0, r0 = inv @ (w, n)
    c1, r1 = inv @ (e, s)
    col0, col1 = max(int(np.floor(min(c0, c1))) - 2, 0), min(int(np.ceil(max(c0, c1))) + 2, hazard.width)
    row0, row1 = max(int(np.floor(min(r0, r1))) - 2, 0), min(int(np.ceil(max(r0, r1))) + 2, hazard.height)
    if col1 <= col0 or row1 <= row0:
        return np.zeros(shape, dtype=bool)
    window = Window(col0, row0, col1 - col0, row1 - row0)
    src_transform = hazard.window_transform(window)

    def _onto_tile(src, dtype="float32"):
        data = src.read(1, window=window, out_dtype=dtype)
        out = np.full(shape, np.nan, dtype=dtype)
        reproject(
            data, out, src_transform=src_transform, src_crs=src.crs, src_nodata=src.nodata,
            dst_transform=tile_transform, dst_crs=tile_crs, dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
        return out

    depth = _onto_tile(hazard)
    wet = np.nan_to_num(depth, nan=0.0) > footprint.min_depth_m
    del depth
    for mask in masks:
        wet &= ~(_onto_tile(mask) == 1.0)
    return wet


def imperviousness_by_region(
    imd_path: str,
    admin: gpd.GeoDataFrame,
    footprint: Footprint,
    *,
    tile: int = DEFAULT_TILE,
) -> pd.DataFrame:
    """Mean sealed share per region, overall and inside the flood footprint.

    Read tile by tile on the CLMS grid: each 100 m cell is in exactly one tile
    and belongs to the region containing its centre, so the sums are additive
    whatever the tile size (`tests/test_sealing.py` pins two sizes). Only tiles
    that touch a region are read; the European mosaic is mostly sea and
    "outside area".

    Returns, on `admin.index`, as fractions in [0, 1]:
    `imperviousness_share_2018`, `imperviousness_share_in_rp<N>_2018`,
    `imperviousness_rp<N>_footprint_km2` (valid CLMS cells in the footprint,
    km2, so a share read over three cells can be told from one read over three
    thousand) and `imperviousness_coverage_2018` (share of the region's cells
    with a classified value).
    """
    n = len(admin)
    region_cells = np.zeros(n)
    valid_cells = np.zeros(n)
    sealed_sum = np.zeros(n)
    wet_cells = np.zeros(n)
    wet_sealed_sum = np.zeros(n)

    with ExitStack() as stack:
        imd = stack.enter_context(rasterio.open(imd_path))
        if imd.crs is None or not imd.crs.is_projected:
            raise ValueError(f"{imd_path} is {imd.crs}, expected EPSG:3035")
        hazard = stack.enter_context(rasterio.open(footprint.hazard_path))
        masks = [stack.enter_context(rasterio.open(m)) for m in footprint.masks]
        for mask in masks:
            if mask.shape != hazard.shape or mask.transform != hazard.transform:
                raise ValueError(f"{Path(mask.name).name} is not on the hazard grid")
        cell_km2 = abs(imd.transform.a * imd.transform.e) / 1e6
        units = admin.to_crs(imd.crs).geometry.reset_index(drop=True)
        index = units.sindex

        for row0 in range(0, imd.height, tile):
            for col0 in range(0, imd.width, tile):
                window = Window(col0, row0, min(tile, imd.width - col0), min(tile, imd.height - row0))
                transform = imd.window_transform(window)
                shape = (int(window.height), int(window.width))
                hits = index.query(box(*rasterio.windows.bounds(window, imd.transform)),
                                   predicate="intersects")
                if len(hits) == 0:
                    continue
                region = rasterize(
                    ((units.iloc[i], int(i) + 1) for i in hits),
                    out_shape=shape, transform=transform, fill=0, dtype="int32",
                    all_touched=False,
                )
                inside = region > 0
                if not inside.any():
                    continue
                region_cells += np.bincount(region[inside], minlength=n + 1)[1:]
                values = imd.read(1, window=window)
                valid = inside & (values <= CLMS_MAX_VALUE)
                if not valid.any():
                    continue
                share = values.astype("float64") / 100.0
                valid_cells += np.bincount(region[valid], minlength=n + 1)[1:]
                sealed_sum += np.bincount(region[valid], weights=share[valid], minlength=n + 1)[1:]
                wet = valid & _footprint_on(transform, shape, imd.crs, hazard, masks, footprint)
                if wet.any():
                    wet_cells += np.bincount(region[wet], minlength=n + 1)[1:]
                    wet_sealed_sum += np.bincount(region[wet], weights=share[wet], minlength=n + 1)[1:]

    rp = footprint.return_period
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.DataFrame(
            {
                "imperviousness_share_2018": np.where(valid_cells > 0, sealed_sum / valid_cells, np.nan),
                f"imperviousness_share_in_rp{rp}_2018": np.where(
                    wet_cells > 0, wet_sealed_sum / wet_cells, np.nan
                ),
                f"imperviousness_rp{rp}_footprint_km2": np.where(
                    valid_cells > 0, wet_cells * cell_km2, np.nan
                ),
                "imperviousness_coverage_2018": np.where(
                    region_cells > 0, valid_cells / region_cells, np.nan
                ),
            },
            index=admin.index,
        )


def clms_by_region(
    admin: gpd.GeoDataFrame,
    footprint: Footprint | None = None,
    *,
    directory: Path | str = CLMS_DIR,
    tile: int = DEFAULT_TILE,
) -> tuple[pd.DataFrame | None, str]:
    """The CLMS imperviousness columns of `context.parquet`, or `(None, reason)`.

    `imperviousness_share_in_rp100_2018` is NaN for a region with no footprint
    cell: the mean sealing of nothing is not "unsealed". A region whose
    footprint lies only where the hazard maps do not reach is also NaN there -
    the maps cover the river network, not every street.
    """
    footprint = footprint or Footprint()
    path = clms_path(directory)
    if path is None:
        return None, (
            f"no IMD_2018_100m GeoTIFF or ZIP in {directory}. Download it by hand "
            f"(EU Login): {CLMS_URL} -> Download -> 'IMD_2018_100m_eu_03035_v020' "
            "(Europe, 100 m, GeoTIFF, 66 MB), and put the ZIP or the unpacked .tif "
            "in that folder."
        )
    missing = [p for p in (footprint.hazard_path, *footprint.masks) if not Path(p).exists()]
    if missing:
        return None, f"hazard layers absent: {', '.join(Path(p).name for p in missing)}"
    frame = imperviousness_by_region(path, admin, footprint, tile=tile)
    rp = footprint.return_period
    return frame, (
        f"CLMS IMD 2018 100 m, EPSG:3035; RP{rp} footprint at > {footprint.min_depth_m} m "
        "resampled nearest onto the 100 m grid, permanent water and spurious areas "
        f"removed; {int(frame['imperviousness_share_2018'].notna().sum())} of "
        f"{len(admin)} units measured"
    )
