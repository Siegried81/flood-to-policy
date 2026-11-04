"""
indicators.py - Raw exposure indicators on the 400 m hexagonal grid (EPSG:3035) and per asset.

Per hexagon (same axial grid as map.py):
  pop      residents (GHS-POP 2020), area-weighted from the 30" cells
  bldg     GHS-OBAT building points (from the cached map.py aggregation)
  a_flood  observed 'Flooded area' inside the hexagon (m²), a_trace = 'Flood trace' (m²), traces minus flooded
  a_mapped area inside the EMS areas of interest (m²): where the absence of flooding is an observation

Neighbourhood = the hexagon and its 6 neighbours (≈ 0.97 km², the GHS-POP resolution). All three indicators
are summed over it, so P, B and F of an asset are those of its hexagon's neighbourhood.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

import map as basemap

HEX_AREA = 3 * np.sqrt(3) / 2 * (basemap.HEX_WIDTH / np.sqrt(3)) ** 2   # m², ≈ 138,564
RING1 = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]
MIN_MAPPED_SHARE = 0.5   # below this share of the neighbourhood inside EMS coverage, flood share is 'unknown'
SITE_BUFFER = 25         # m: asset geometry buffer for the direct flood test (point vs footprint, positional error,
                         # and EMS flood polygons exclude the normal river channel under bridges)
B_GAP_POP = 100          # residents in a neighbourhood with 0 OBAT buildings -> buildings treated as missing


def region_hexes(region_3035):
    """All hexagons of the grid intersecting the region."""
    minx, miny, maxx, maxy = region_3035.bounds
    size = basemap.HEX_WIDTH / np.sqrt(3)
    r = np.arange(np.floor(miny / (1.5 * size)) - 1, np.ceil(maxy / (1.5 * size)) + 2).astype(np.int64)
    qmin = int(np.floor(minx / basemap.HEX_WIDTH - r.max() / 2)) - 1
    qmax = int(np.ceil(maxx / basemap.HEX_WIDTH - r.min() / 2)) + 1
    q, rr = np.meshgrid(np.arange(qmin, qmax + 1), r)
    q, rr = q.ravel(), rr.ravel()
    cx = size * np.sqrt(3) * (q + rr / 2)
    cy = size * 1.5 * rr
    keep = (cx > minx - size) & (cx < maxx + size) & (cy > miny - size) & (cy < maxy + size)
    q, rr = q[keep], rr[keep]
    geom = basemap.hex_polygons(q, rr)
    shapely.prepare(region_3035)
    keep = shapely.intersects(geom, region_3035)
    return gpd.GeoDataFrame({"q": q[keep], "r": rr[keep]}, geometry=geom[keep], crs=basemap.METRIC_CRS)


def area_by_hex(hexes, polys):
    """Intersection area (m²) of each hexagon with a (multi)polygon geometry."""
    shapely.prepare(polys)
    cand = shapely.intersects(hexes.geometry.values, polys)
    out = np.zeros(len(hexes))
    out[cand] = shapely.area(shapely.intersection(hexes.geometry.values[cand], polys))
    return out


def pop_by_hex(hexes, cells):
    """Area-weighted GHS-POP residents per hexagon (cells keep their total; nothing is created or lost inside the region)."""
    c = cells[["pop", "geometry"]].to_crs(basemap.METRIC_CRS)
    c["cell_m2"] = c.area
    j = gpd.sjoin(hexes[["geometry"]], c, predicate="intersects")
    inter = shapely.area(shapely.intersection(hexes.geometry.values[j.index.to_numpy()],
                                              c.geometry.values[j["index_right"].to_numpy()]))
    contrib = j["pop"].to_numpy() * inter / j["cell_m2"].to_numpy()
    return pd.Series(contrib, index=j.index).groupby(level=0).sum().reindex(hexes.index, fill_value=0).to_numpy()


def flood_union(flood):
    """Non-overlapping observed extents: flooded = union of all flooded polygons, trace = union of traces minus flooded
    (activations can overlap at AOI borders; this prevents counting an area twice)."""
    wet = shapely.union_all(flood.loc[flood["kind"] == "flooded", "geometry"].values)
    trace = shapely.difference(shapely.union_all(flood.loc[flood["kind"] == "trace", "geometry"].values), wet)
    return wet, trace


def hex_indicators(region_3035, cells, bldg_hexes, flood, aoi):
    """Raw hexagon indicators and their 7-hex neighbourhood sums."""
    hx = region_hexes(region_3035)
    wet, trace = flood_union(flood)
    mapped = shapely.union_all(aoi.to_crs(basemap.METRIC_CRS).geometry.values)
    hx["pop"] = pop_by_hex(hx, cells)
    hx = hx.merge(bldg_hexes[["q", "r", "n_bldg", "country"]], on=["q", "r"], how="left").rename(columns={"n_bldg": "bldg"})
    hx["bldg"] = hx["bldg"].fillna(0)
    # Country = majority OBAT country of the hexagon; hexagons without buildings take the nearest one's
    # (no administrative boundaries in the challenge data; used for filtering only)
    known = hx[hx["country"].notna()]
    near = gpd.sjoin_nearest(hx.loc[hx["country"].isna(), ["geometry"]], known[["country", "geometry"]])
    hx.loc[near.index, "country"] = near.groupby(level=0)["country"].first()
    hx["a_flood"] = area_by_hex(hx, wet)
    hx["a_trace"] = area_by_hex(hx, trace)
    hx["a_mapped"] = area_by_hex(hx, mapped)
    hx["a_hex"] = HEX_AREA
    return neighbourhood(hx)


def neighbourhood(hx, cols=("pop", "bldg", "a_flood", "a_trace", "a_mapped", "a_hex")):
    """Sum of each column over the hexagon and its 6 neighbours (hexagons missing from the grid add nothing)."""
    base = hx.set_index(["q", "r"])[list(cols)]
    tot = pd.DataFrame(0.0, index=base.index, columns=list(cols))
    for dq, dr in RING1:
        shifted = base.copy()
        shifted.index = pd.MultiIndex.from_arrays([base.index.get_level_values(0) - dq, base.index.get_level_values(1) - dr])
        tot = tot.add(shifted.reindex(base.index), fill_value=0)
    for c in cols:
        hx[f"n_{c}"] = tot[c].to_numpy()
    mapped_share = hx["n_a_mapped"] / hx["n_a_hex"]
    hx["mapped_share"] = mapped_share
    flooded = hx["n_a_flood"] + hx["n_a_trace"]
    hx["flood_share_mapped"] = np.where(hx["n_a_mapped"] > 0, flooded / hx["n_a_mapped"].clip(lower=1), np.nan)
    hx["flood_share"] = np.where(mapped_share >= MIN_MAPPED_SHARE, hx["flood_share_mapped"], np.nan)
    hx["trace_share"] = np.where(mapped_share >= MIN_MAPPED_SHARE, hx["n_a_trace"] / hx["n_a_mapped"].clip(lower=1), np.nan)
    hx["b_gap"] = (hx["n_bldg"] == 0) & (hx["n_pop"] >= B_GAP_POP)
    return hx


def asset_indicators(assets, hx, flood, aoi):
    """Attach neighbourhood indicators (hexagon of the representative point) and the direct flood test."""
    a = assets.copy()
    rp = a.representative_point()
    a["q"], a["r"] = basemap.hex_index(rp.x.to_numpy(), rp.y.to_numpy())
    cols = ["n_pop", "n_bldg", "flood_share", "flood_share_mapped", "trace_share", "mapped_share", "b_gap", "country"]
    a = a.merge(hx[["q", "r"] + cols], on=["q", "r"], how="left")
    a = gpd.GeoDataFrame(a, geometry="geometry", crs=assets.crs)
    wet, trace = flood_union(flood)
    buf = a.buffer(SITE_BUFFER).values
    shapely.prepare(wet), shapely.prepare(trace)
    a["hit_flooded"] = shapely.intersects(buf, wet)
    a["hit_trace"] = shapely.intersects(buf, trace) & ~a["hit_flooded"]
    mapped = shapely.union_all(aoi.to_crs(basemap.METRIC_CRS).geometry.values)
    a["in_mapped"] = shapely.intersects(rp.values, mapped)
    return a
