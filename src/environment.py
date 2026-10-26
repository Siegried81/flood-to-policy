"""Protected nature in the water: Natura 2000 area on flood-prone ground, per region.

Article 6(5) of the Floods Directive asks flood risk maps to show the potential
adverse consequences for the ENVIRONMENT, not only for people and economic
activity. The kit measured residents and built-up surface and nothing else; this
module adds the first environmental figure, as context rather than exposure.

**Why it is measured on the hazard grid, and not through `exposure.py`.**
People and built-up surface arrive as counts on a 1 km grid, so the hazard is
averaged onto that grid and each cell's count is weighted by its wet share. A
Natura 2000 site is a polygon, not a count. Pushing it through the 1 km pipeline
would mean rasterising it to 1 km first and then assuming that, inside a cell,
the protected part and the flooded part are independent - and for a riverine
site, which is exactly the kind a flood reaches, they are not. So the sites are
rasterised onto the hazard raster's own 3 arc-second grid and intersected with
the wet mask cell by cell, with no resampling at all.

**Why windows on the HAZARD grid are exact here.** The rule in
`scripts/build_exposure.py` - cut windows on the population grid, never on the
hazard raster - exists because `Resampling.average` renormalises over whatever
source area a window holds, so a population cell straddling two hazard windows
is written twice. Nothing is resampled in this module: every hazard cell is
read once, in exactly one row band, and its area is added to exactly one
region. The windows are disjoint and the sums are additive by construction,
which `tests/test_environment.py` pins at several window sizes. The bands are
full width for the same reason the exposure build's hazard windows are.

**Overlapping sites are counted once.** A site designated under both directives
is one row in the GeoPackage, but two different sites can overlap on the ground
(an SPA drawn over an SAC). Every polygon is burnt into one 0/1 mask, so a cell
is protected or not and the area is the area of the UNION - never a sum of site
areas, which would count the overlap twice.

**Area is the true area of each cell.** A 3 arc-second cell is about 92 m
north-south everywhere but its east-west width shrinks with the cosine of the
latitude, so a cell count is not an area. Each row's cell area is computed on
the WGS84 ellipsoid with `pyproj.Geod`, once per row.

**What "flooded" means** is exactly what it means in the exposure table: depth
above `min_depth_m` (0.5 m by default) on the masked hazard raster, permanent
water bodies and the JRC's spurious-depth areas removed. A lake inside a Natura
site is therefore not "flooded nature"; it was water before the flood.

**Not measured is not zero.** The GeoPackage covers the EU-27 only. A region in a
country with no site at all in the file (Switzerland, Norway, Turkiye...) gets
None, not 0 km2: the network does not exist there, which is not the same as a
region with no protected nature.
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pyproj import Geod
from rasterio.features import rasterize
from rasterio.windows import Window
from shapely.geometry import box

from src.data_io import DATA, WORKING_CRS

NATURA_GPKG = DATA / "raw" / "download" / "eea_natura2000_gpkg.gpkg"

#: The one spatial layer in the GeoPackage; the other ten are the standard data
#: forms as tables. Named rather than detected, because the file declares its
#: geometry type as "Unknown" (polygons and multipolygons mixed), measured
#: 2026-10-12 on the end-2024 release: 27,173 sites, EPSG:3035.
SITE_LAYER = "NaturaSite_polygon"

#: Hazard rows read per window. Memory only: the windows are disjoint and the
#: result does not depend on it. 1,024 full-width rows of the continental grid
#: are 113M cells, about 2 GB with the depth band, both masks and the two
#: rasterised layers.
DEFAULT_WINDOW_ROWS = 1024

_GEOD = Geod(ellps="WGS84")


class NaturaUnavailable(RuntimeError):
    """The Natura 2000 GeoPackage is not on disk. Raised, never an empty frame."""


def sites(path: Path | str = NATURA_GPKG) -> gpd.GeoDataFrame:
    """Every Natura 2000 site polygon in the end-2024 release, with its country.

    Only the geometry and the Member State are kept: the figure is an area of
    the union, so neither the site type nor the site code changes it.
    """
    path = Path(path)
    if not path.exists():
        raise NaturaUnavailable(
            f"{path} is missing. Run `python -m src.fetch`: it is declared as "
            "`eea_natura2000_gpkg` in config/sources.yaml (1.36 GB)."
        )
    layers = set(gpd.list_layers(path)["name"])
    if SITE_LAYER not in layers:
        raise NaturaUnavailable(
            f"{path.name} has no `{SITE_LAYER}` layer; it holds {sorted(layers)}"
        )
    frame = gpd.read_file(path, layer=SITE_LAYER, columns=["MS"])
    if frame.crs is None:
        raise NaturaUnavailable(f"{path.name} loaded with crs=None")
    return frame.rename(columns={"MS": "country"})[["country", "geometry"]]


def row_cell_areas_km2(transform, rows: range, width_deg: float) -> np.ndarray:
    """True area, km2, of one cell in each of `rows` of a geographic grid.

    Exact on the WGS84 ellipsoid rather than `cos(lat)` on a sphere; the cost is
    one small polygon per row.
    """
    out = np.empty(len(rows), dtype="float64")
    for i, row in enumerate(rows):
        top = transform.f + row * transform.e
        bottom = top + transform.e
        lons = [0.0, width_deg, width_deg, 0.0]
        lats = [bottom, bottom, top, top]
        area, _ = _GEOD.polygon_area_perimeter(lons, lats)
        out[i] = abs(area) / 1e6
    return out


def flooded_protected_area(
    hazard_path: str,
    protected: gpd.GeoDataFrame,
    admin: gpd.GeoDataFrame,
    *,
    min_depth_m: float = 0.5,
    masks: list[str] | None = None,
    window_rows: int = DEFAULT_WINDOW_ROWS,
) -> pd.DataFrame:
    """Protected area and flooded protected area, km2, per unit of `admin`.

    Returns a frame on `admin.index` with:

    - `protected_km2` - the union of the protected polygons inside the unit,
      measured on the hazard grid;
    - `protected_flooded_km2` - the part of it deeper than `min_depth_m` once
      `masks` are removed;
    - `grid_coverage` - the share of the unit's area that lies on the hazard
      grid at all, in [0, 1]. Below 1 the unit runs off the raster (the Canaries
      sit on its southern edge) and both areas are measured on the covered part
      only; at 0 they are None.

    A cell belongs to the unit containing its centre and to the protected mask
    when its centre is inside a site (`all_touched=False` on both), so the two
    rasterisations agree with each other and no cell is counted twice.
    """
    masks = masks or []
    n = len(admin)
    protected_km2 = np.zeros(n)
    flooded_km2 = np.zeros(n)
    on_grid_km2 = np.zeros(n)

    with ExitStack() as stack:
        haz = stack.enter_context(rasterio.open(hazard_path))
        mask_sources = [stack.enter_context(rasterio.open(m)) for m in masks]
        for mask_src in mask_sources:
            if mask_src.shape != haz.shape or mask_src.transform != haz.transform:
                raise ValueError(
                    f"{Path(mask_src.name).name} is not on the hazard grid"
                )
        # Polygons to the raster, never the raster to the polygons.
        units = admin.to_crs(haz.crs).geometry.reset_index(drop=True)
        nature = protected.to_crs(haz.crs).geometry.reset_index(drop=True)
        nature = nature[~nature.is_empty & nature.notna()]
        nature_index = nature.sindex
        units_index = units.sindex
        cell_width = abs(haz.transform.a)

        for top in range(0, haz.height, window_rows):
            window = Window(0, top, haz.width, min(window_rows, haz.height - top))
            transform = haz.window_transform(window)
            shape = (int(window.height), int(window.width))
            bounds = box(*rasterio.windows.bounds(window, haz.transform))

            hits = units_index.query(bounds, predicate="intersects")
            if len(hits) == 0:
                continue
            # Unit ids start at 1 so that 0 means "no unit".
            region = rasterize(
                ((units.iloc[i], int(i) + 1) for i in hits),
                out_shape=shape, transform=transform, fill=0, dtype="int32",
                all_touched=False,
            )
            areas = row_cell_areas_km2(
                haz.transform, range(top, top + shape[0]), cell_width
            )[:, None]
            on_grid_km2 += np.bincount(
                region.ravel(),
                weights=np.broadcast_to(areas, shape).ravel(),
                minlength=n + 1,
            )[1:]

            site_hits = nature_index.query(bounds, predicate="intersects")
            if len(site_hits) == 0:
                continue
            inside = rasterize(
                ((nature.iloc[i], 1) for i in site_hits),
                out_shape=shape, transform=transform, fill=0, dtype="uint8",
                all_touched=False,
            ).astype(bool) & (region > 0)
            if not inside.any():
                continue

            band = haz.read(1, window=window, masked=True)
            wet = np.ma.filled(band > min_depth_m, False)
            del band
            for mask_src in mask_sources:
                flagged = mask_src.read(1, window=window)
                wet &= ~(np.isfinite(flagged) & (flagged == 1.0))
                del flagged

            cell_area = np.broadcast_to(areas, shape)
            protected_km2 += np.bincount(
                region[inside], weights=cell_area[inside], minlength=n + 1
            )[1:]
            flooded = inside & wet
            flooded_km2 += np.bincount(
                region[flooded], weights=cell_area[flooded], minlength=n + 1
            )[1:]

    true_km2 = admin.to_crs(WORKING_CRS).area.to_numpy() / 1e6
    coverage = np.clip(
        np.divide(on_grid_km2, true_km2, out=np.zeros(n), where=true_km2 > 0),
        0.0, 1.0,
    )
    frame = pd.DataFrame(
        {
            "protected_km2": protected_km2,
            "protected_flooded_km2": flooded_km2,
            "grid_coverage": coverage,
        },
        index=admin.index,
    )
    frame.loc[coverage <= 0, ["protected_km2", "protected_flooded_km2"]] = np.nan
    return frame


def natura_by_region(
    hazard_path: str,
    admin: gpd.GeoDataFrame,
    *,
    return_period: int,
    min_depth_m: float = 0.5,
    masks: list[str] | None = None,
    window_rows: int = DEFAULT_WINDOW_ROWS,
    protected: gpd.GeoDataFrame | None = None,
) -> pd.DataFrame:
    """The Natura 2000 columns of `context.parquet`, named after their period.

    `admin` must carry a `country` column (`scripts.build_exposure.boundaries`
    does). A region in a country with no site in the file is None throughout:
    the network does not exist there, which is not a measured zero.

    The share uses the two areas measured on the same grid cells, so it is in
    [0, 1] by construction; it is None where there is no protected area to
    divide by, because 0 % of nothing would rank as the safest region.
    """
    protected = sites() if protected is None else protected
    measured = flooded_protected_area(
        hazard_path, protected, admin,
        min_depth_m=min_depth_m, masks=masks, window_rows=window_rows,
    )
    # Eurostat and GISCO write Greece "EL"; ISO and some EEA files write "GR".
    countries = {("EL" if c == "GR" else c) for c in protected["country"].dropna()}
    reported = admin["country"].isin(countries)
    rp = return_period
    out = pd.DataFrame(index=admin.index)
    out["natura2000_km2"] = measured["protected_km2"].where(reported)
    out[f"natura2000_flooded_km2_rp{rp}"] = measured["protected_flooded_km2"].where(
        reported
    )
    total = out["natura2000_km2"]
    out[f"natura2000_flooded_share_rp{rp}"] = out[
        f"natura2000_flooded_km2_rp{rp}"
    ].divide(total.where(total > 0))
    out["natura2000_grid_coverage"] = measured["grid_coverage"].where(reported)
    return out
