"""Hospitals and schools inside the flood footprint, per region.

Article 6(5) of the Floods Directive asks the flood risk maps to show the
consequences for, among others, hospitals and schools. The kit counts people
and built-up surface; this module counts the two kinds of facility a crisis
plan names first, from the Eurostat GISCO layers built out of Member States'
official sources (`gisco_healthcare`, `gisco_education` in config/sources.yaml).

Points, not areas, so the method is a lookup rather than a zonal statistic:
each facility is read at its own location in the hazard raster. Three choices
keep "flooded" meaning the same thing as in the population figures:

* **The same threshold and the same masks.** A facility counts as flooded when
  the modelled depth at its point reaches `min_depth_m` (0.5 m by default, the
  exposure table's), and never on a cell the JRC flags as permanent water or as
  a spurious depth. A hospital sited on a river bank is not "in the flood"
  because the channel next to it is wet.
* **Residual as well as undefended.** The hazard maps draw the water as if no
  dyke stood; `residual` also drops every facility whose local flood protection
  standard (`jrc_flood_protection_standards`) is at least the return period.
* **Read in sorted order.** 333,844 schools sampled in raster order let GDAL
  reuse each decompressed block instead of seeking back and forth across a
  5.7-billion-cell file.

A facility is assigned to the NUTS3 region its point falls in. A point in no
region (offshore by a geocoding error) is counted nowhere and reported, never
snapped to the nearest region.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

WORKING_CRS = "EPSG:3035"


def load(path: str | Path) -> gpd.GeoDataFrame:
    """The facility points with the columns the counts need, in EPSG:4326."""
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError(f"{Path(path).name} loaded with crs=None; refusing to guess.")
    keep = [c for c in ("id", "cntr_id", "cap_beds") if c in frame.columns]
    frame = frame[keep + ["geometry"]].to_crs("EPSG:4326")
    return frame[frame.geometry.notna() & ~frame.geometry.is_empty].reset_index(drop=True)


def sample(points: gpd.GeoDataFrame, raster_path: str) -> np.ndarray:
    """The raster's value at every point, NaN where nodata or off the raster.

    Points are visited in raster row order and the values put back in the
    caller's order, so a large layer reads each compressed block once.
    """
    with rasterio.open(raster_path) as src:
        xy = points.to_crs(src.crs).geometry
        xs, ys = xy.x.to_numpy(), xy.y.to_numpy()
        order = np.lexsort((xs, -ys))
        values = np.full(len(points), np.nan, dtype="float64")
        sampled = src.sample(zip(xs[order], ys[order]), indexes=1, masked=True)
        for position, value in zip(order, sampled):
            if not np.ma.is_masked(value[0]):
                values[position] = float(value[0])
    return values


def flooded(
    points: gpd.GeoDataFrame,
    hazard_path: str,
    *,
    min_depth_m: float,
    masks: list[str] = (),
) -> np.ndarray:
    """True where the point is deeper than `min_depth_m` and on no masked cell.

    Strictly deeper, as `src/exposure.py` and `src/environment.py` compare:
    "flooded" has to mean one thing across every figure in the context table.
    """
    depth = sample(points, hazard_path)
    wet = np.nan_to_num(depth, nan=0.0) > min_depth_m
    for mask in masks:
        wet &= ~(sample(points, mask) == 1.0)
    return wet


def held(points: gpd.GeoDataFrame, protection_path: str, return_period: int) -> np.ndarray:
    """True where the local flood protection standard holds this return period.

    An unknown standard (nodata, or off the raster) never holds, so the
    residual count stays an upper bound there - the same rule as the residual
    population in `scripts/build_exposure.py`.
    """
    standards = sample(points, protection_path)
    return np.nan_to_num(standards, nan=-1.0) >= return_period


def region_of(points: gpd.GeoDataFrame, admin: gpd.GeoDataFrame, key: str = "nuts_id") -> pd.Series:
    """The `key` of the region each point lies in, NaN for a point in none."""
    regions = admin[[key, "geometry"]].to_crs(WORKING_CRS)
    located = gpd.sjoin(
        points.to_crs(WORKING_CRS), regions, how="left", predicate="within"
    )
    # A point exactly on a shared border matches twice; it belongs to one.
    located = located[~located.index.duplicated(keep="first")]
    return located[key].reindex(points.index)


def counts_by_region(
    points: gpd.GeoDataFrame,
    admin: gpd.GeoDataFrame,
    flags: dict[str, np.ndarray],
    *,
    prefix: str,
    key: str = "nuts_id",
    weight: str | None = None,
    country: str | None = "country",
) -> pd.DataFrame:
    """Per region: the total, and the count behind every flag in `flags`.

    `flags` maps a column suffix (`flooded_rp100`) to a boolean array aligned
    with `points`. `weight`, when given, also sums that column (hospital beds)
    for each flag, as `<prefix>_<weight>_<suffix>`, and counts the facilities
    that carry it, as `<prefix>_<weight>_known`.

    **A facility without the weight is unknown, not 0.** In Switzerland 354 of
    581 hospitals have no bed figure; summed as 0 they made every Swiss bed
    total look complete. A weighted column is NaN wherever a facility it would
    sum lacks the weight: the total where `_known` < `_total`, a flag column
    where one of its flagged facilities does. `_known` says how far the
    figure reaches.

    **A country the layer does not cover is NaN, not 0.** Measured 2026-10-24:
    the GISCO hospital layer holds no German facility at all, so every German
    region read "0 hospitals, 0 flooded" - a measured all-clear for the most
    populous Member State. A region reads 0 only when its country has at least
    one facility in the layer; `country`, when given, is the admin column that
    says which country a region is in.
    """
    where = region_of(points, admin, key)
    frame = pd.DataFrame({key: where.to_numpy()})
    frame[f"{prefix}_total"] = 1
    for suffix, flag in flags.items():
        frame[f"{prefix}_{suffix}"] = np.asarray(flag, dtype="int64")
    weighted = weight is not None and weight in points.columns
    if weighted:
        raw = pd.to_numeric(points[weight], errors="coerce").to_numpy()
        unknown = np.isnan(raw)
        values = np.where(unknown, 0.0, raw)
        frame[f"{prefix}_{weight}_known"] = (~unknown).astype("int64")
        frame[f"{prefix}_{weight}_total"] = values
        for suffix, flag in flags.items():
            frame[f"{prefix}_{weight}_{suffix}"] = values * np.asarray(flag)
            # Scratch column: flagged facilities without the weight, dropped below.
            frame[f"_unknown_{suffix}"] = (unknown & np.asarray(flag, dtype=bool)).astype("int64")
    summed = frame.dropna(subset=[key]).groupby(key).sum(numeric_only=True)
    out = summed.reindex(admin[key]).fillna(0)
    out.index = admin.index
    if weighted:
        partial = out[f"{prefix}_{weight}_known"] < out[f"{prefix}_total"]
        out.loc[partial, f"{prefix}_{weight}_total"] = np.nan
        for suffix in flags:
            out.loc[out[f"_unknown_{suffix}"] > 0, f"{prefix}_{weight}_{suffix}"] = np.nan
        out = out.drop(columns=[f"_unknown_{suffix}" for suffix in flags])
    if country is not None and country in admin.columns:
        covered = set(admin.loc[out[f"{prefix}_total"].to_numpy() > 0, country])
        out.loc[~admin[country].isin(covered).to_numpy()] = np.nan
        # The same rule for the weight: a country whose facilities report no
        # beds at all did not report beds, it did not report empty hospitals.
        if weight is not None and f"{prefix}_{weight}_total" in out.columns:
            # `_known` stays: 0 hospitals with a bed figure is a measured count.
            weight_columns = [c for c in out.columns if c.startswith(f"{prefix}_{weight}_")
                              and c != f"{prefix}_{weight}_known"]
            reported = set(admin.loc[out[f"{prefix}_{weight}_known"].fillna(0).to_numpy() > 0, country])
            out.loc[~admin[country].isin(reported).to_numpy(), weight_columns] = np.nan
    return out
