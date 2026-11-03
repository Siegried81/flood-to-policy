"""
demand.py - Demand origins for the shelter planning scenario.

Reuses the existing estimate of residents inside the mapped 2021 flood extent (map.py, step 4): GHS-POP E2020
(R2023A, reference year 2020) residents shared equally among the residential GHS-OBAT buildings of each 30" cell,
summed per flood polygon (area share where a cell has no residential building). Nothing is re-estimated here.

Spatial split: a single flood polygon can hold > 12,000 residents over several kilometres, so each polygon's
residents are spread over its parts in the 400 m hexagons of map.py, in proportion to
    residential buildings of the hexagon x share of the hexagon area covered by the polygon part
(assumption: residential buildings evenly spread inside a hexagon). If no part has residential buildings, the
polygon's residents go to its representative point. Each polygon's total is kept exactly, so the overall total is
unchanged. Parts are then summed per hexagon: one origin per hexagon, placed at a point inside its flooded part.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

METRIC_CRS = "EPSG:3035"
WEB_CRS = "EPSG:4326"
REFERENCE = ("GHS-POP E2020 R2023A (reference year 2020) residents, shared over residential GHS-OBAT R2024A buildings, "
             "inside the mapped observed flood extent (Copernicus EMS EMSR517/518/520, flooded areas + traces)")


def build_demand(flood, hexes):
    """Origins (EPSG:3035 points) with estimated exposed residents. `flood`, `hexes`: map.py caches (EPSG:3035)."""
    assert flood.crs == hexes.crs == METRIC_CRS
    f = flood[flood["residents"] > 0].reset_index(drop=True)
    hx = hexes[["q", "r", "n_res", "country", "geometry"]].reset_index(drop=True)
    i, j = shapely.STRtree(hx.geometry.values).query(f.geometry.values, predicate="intersects")
    part = shapely.intersection(f.geometry.values[i], hx.geometry.values[j])
    a_part = shapely.area(part)
    p = pd.DataFrame({"poly": i, "hex": j, "w": hx["n_res"].to_numpy()[j] * a_part / shapely.area(hx.geometry.values[j]),
                      "a": a_part})
    p["geometry"] = part
    p = p[p["a"] > 0]
    wsum = p.groupby("poly")["w"].transform("sum")
    p = p[wsum > 0]
    p["res"] = f["residents"].to_numpy()[p["poly"]] * p["w"] / p.groupby("poly")["w"].transform("sum")
    p = p[p["res"] > 0]

    g = p.groupby("hex")
    origins = gpd.GeoDataFrame({
        "origin_id": [f"h{hx.at[h, 'q']}_{hx.at[h, 'r']}" for h in g.groups],
        "country": [hx.at[h, "country"] for h in g.groups],
        "residents": g["res"].sum().to_numpy(),
        "n_flood_polygons": g["poly"].nunique().to_numpy(),
    }, geometry=[shapely.union_all(s.to_numpy()).representative_point() for _, s in g["geometry"]], crs=METRIC_CRS)

    # polygons with residents but no residential building in any part (area-share residents): one origin each
    lost = np.setdiff1d(np.arange(len(f)), p["poly"].unique())
    if len(lost):
        extra = gpd.GeoDataFrame({"origin_id": [f"p{k}" for k in lost], "country": "",
                                  "residents": f["residents"].to_numpy()[lost], "n_flood_polygons": 1},
                                 geometry=shapely.point_on_surface(f.geometry.values[lost]), crs=METRIC_CRS)
        origins = pd.concat([origins, extra], ignore_index=True)
    origins["x"], origins["y"] = origins.geometry.x.round(1), origins.geometry.y.round(1)
    ll = origins.to_crs(WEB_CRS)
    origins["lon"], origins["lat"] = ll.geometry.x.round(6), ll.geometry.y.round(6)
    return origins.sort_values("origin_id").reset_index(drop=True)


EXPOSURE_QUANTILE = 0.99   # P99 reference of the area priority exposure component (fixed, study-wide)


def hex_summary(origins, hexes, hex_index, hex_polygons):
    """Fixed 400 m hexagon summary of the demand origins (one row per hexagon with exposed residents).

    Hexagon origins ('h{q}_{r}') keep their own hexagon; fallback origins ('p{k}', polygons without residential
    buildings) are assigned to the hexagon containing their point, with the same grid functions as map.py.
    Every origin goes to exactly one hexagon, so the residents total is unchanged. Returns (hexagons in EPSG:3035,
    hexagon index of every origin in `origins` order). Country = majority country of the hexagon's OBAT buildings,
    empty where the hexagon has none (no municipality: not reliably available in our data)."""
    q = np.empty(len(origins), np.int64)
    r = np.empty(len(origins), np.int64)
    own = origins["origin_id"].str.match(r"^h-?\d+_-?\d+$").to_numpy()
    qr = origins.loc[own, "origin_id"].str[1:].str.split("_", expand=True).astype(np.int64)
    q[own], r[own] = qr[0].to_numpy(), qr[1].to_numpy()
    q[~own], r[~own] = hex_index(origins["x"].to_numpy()[~own], origins["y"].to_numpy()[~own])
    o = pd.DataFrame({"q": q, "r": r, "res": origins["residents"].to_numpy(), "fallback": ~own})
    g = o.groupby(["q", "r"], sort=True)
    hx = g.agg(residents=("res", "sum"), n_origins=("res", "size"), n_fallback=("fallback", "sum")).reset_index()
    hx["hex_id"] = "h" + hx["q"].astype(str) + "_" + hx["r"].astype(str)
    country = hexes.set_index(hexes["q"].astype(str) + "_" + hexes["r"].astype(str))["country"]
    hx["country"] = (hx["q"].astype(str) + "_" + hx["r"].astype(str)).map(country).fillna("")
    hx = gpd.GeoDataFrame(hx, geometry=hex_polygons(hx["q"].to_numpy(), hx["r"].to_numpy()), crs=METRIC_CRS)
    c = hx.geometry.centroid.to_crs(WEB_CRS)
    hx["lon"], hx["lat"] = c.x.round(6), c.y.round(6)
    pos = {k: i for i, k in enumerate(zip(hx["q"], hx["r"]))}
    origin_hex = np.array([pos[k] for k in zip(q, r)])
    return hx, origin_hex


def exposure_reference(hx, q=EXPOSURE_QUANTILE):
    """P99: q-quantile (numpy linear interpolation) of the positive exposed-resident values of the fixed hexagons."""
    v = hx["residents"].to_numpy(float)
    return float(np.quantile(v[v > 0], q))


def check_hex_summary(hx, origin_hex, origins, tol=1e-6):
    """Problems (empty = ok): total conserved, every origin counted once, unique hexagon ids, positive residents."""
    p = []
    if abs(hx["residents"].sum() - origins["residents"].sum()) > tol * max(1, origins["residents"].sum()):
        p.append(f"hexagon total {hx['residents'].sum():.3f} != origin total {origins['residents'].sum():.3f}")
    if len(origin_hex) != len(origins) or hx["n_origins"].sum() != len(origins):
        p.append("origins not counted exactly once")
    per_hex = np.bincount(origin_hex, weights=origins["residents"].to_numpy(), minlength=len(hx))
    if not np.allclose(per_hex, hx["residents"].to_numpy(), rtol=0, atol=1e-9):
        p.append("origin-to-hexagon index does not reproduce the hexagon totals")
    if hx["hex_id"].duplicated().any():
        p.append("duplicate hexagon ids")
    if (hx["residents"] <= 0).any():
        p.append("hexagon without positive residents")
    return p


def check_demand(origins, flood, tol=1e-6):
    """Problems (empty = ok): conservation of the residents total, no negative / missing values, unique ids,
    every origin point inside the flood extent."""
    p = []
    if abs(origins["residents"].sum() - flood["residents"].sum()) > tol * max(1, flood["residents"].sum()):
        p.append(f"residents not conserved: {origins['residents'].sum():.3f} vs {flood['residents'].sum():.3f}")
    if (origins["residents"] <= 0).any() or origins["residents"].isna().any():
        p.append("non-positive or missing residents")
    if origins["origin_id"].duplicated().any():
        p.append("duplicate origin ids")
    ext = shapely.union_all(flood.geometry.values)
    if not shapely.intersects(origins.geometry.values, ext).all():
        p.append("origin outside the flood extent")
    return p
