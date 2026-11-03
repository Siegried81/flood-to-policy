"""
shelters.py - Candidate shelter inventory (stage 1): schools, sports halls and community centres from
OpenStreetMap inside the existing analysis area (EMS areas of interest + 1 km), screened against the
observed July 2021 flood extent.

These are CANDIDATE facilities only: an OSM record shows a facility was mapped, not that it operates
today, is designated as an emergency shelter, or is suitable. Capacity is left unknown unless a
documented source gives it (none is used yet).

Sources
  Schools                       existing cache/osm "facilities" tiles (priority map); missing tiles fetched
  Sports halls, community ctrs  Overpass, 0.5° tiles, cached in cache/shelters/osm (+ provenance manifest)
  Municipality / country        OSM administrative boundaries (admin_level 8; 6 for German kreisfreie Städte)
  Flood extent, EMS coverage    cache/flood.parquet, cache/aoi.parquet from map.py (unsimplified, EPSG:3035)

Usage:  python shelters.py            # fetch missing tiles, build inventory, run checks, export
        python shelters.py --offline  # cached tiles only (never contacts Overpass)
        python shelters.py --refresh  # re-download all shelter / boundary tiles (keeps stale copies on failure)
Output: shelter_candidates.csv, shelter_candidates.geojson, cache/shelters/inventory.parquet (read by map.py)
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from priority import osm

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
SCACHE = CACHE / "shelters"
OSM_CACHE = CACHE / "osm"                   # shared with priority_map.py (schools)
SOSM_CACHE = SCACHE / "osm"
INVENTORY = SCACHE / "inventory.parquet"
META = SCACHE / "inventory_meta.json"
OUT_CSV = HERE / "shelter_candidates.csv"
OUT_GEOJSON = HERE / "shelter_candidates.geojson"

METRIC_CRS = "EPSG:3035"
WEB_CRS = "EPSG:4326"
AOI_BUFFER = 1000          # m, same analysis area as map.py / priority_map.py
EDGE_TOL = 25              # m, assumption: combined positional uncertainty of OSM points and EMS delineation
MIN_BUILDING_M2 = 100      # m², building footprints smaller than this are treated as huts / kiosks and excluded

SHELTER_QUERIES = {
    "shelters": """
  nwr["amenity"="community_centre"];
  nwr["leisure"~"^(sports_hall|sports_centre)$"];
  way["building"~"^(sports_hall|sports_centre)$"];""",
    "admin": """
  rel["boundary"="administrative"]["admin_level"~"^(6|8)$"];""",
}
SCHOOL_QUERIES = {"facilities": osm.QUERIES["facilities"]}   # identical text -> identical cache keys as priority_map.py


# --------------------------------------------------------------------------- acquisition
def region_from_cache():
    aoi = gpd.read_parquet(CACHE / "aoi.parquet")
    return aoi, aoi.buffer(AOI_BUFFER).union_all()


def to_wgs(geom):
    return gpd.GeoSeries([geom], crs=METRIC_CRS).to_crs(WEB_CRS).iloc[0]


def offline_manifest(cache_dir, region_wgs, queries):
    """Manifest entries for the region's tiles from the cache only; tiles never downloaded are marked missing."""
    mf = Path(cache_dir) / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {}
    out = {}
    for g in queries:
        for b in osm.tiles(region_wgs):
            k = osm.cache_key(g, b, queries)
            out[k] = manifest.get(k, {"group": g, "bbox": list(b), "status": "missing"})
    return out


def acquire(region_wgs, offline=False, refresh=False):
    """Manifests for the school tiles (shared cache) and the shelter / boundary tiles."""
    if offline:
        return offline_manifest(OSM_CACHE, region_wgs, SCHOOL_QUERIES), offline_manifest(SOSM_CACHE, region_wgs, SHELTER_QUERIES)
    schools = osm.fetch(region_wgs, OSM_CACHE, queries=SCHOOL_QUERIES)    # never refreshed here: owned by priority_map.py
    return schools, osm.fetch(region_wgs, SOSM_CACHE, refresh=refresh, queries=SHELTER_QUERIES)


def read_with_provenance(cache_dir, manifest, group):
    """Cached elements of a group, de-duplicated across tiles by (type, id), each with the provenance of the
    first tile it was read from (retrieval time, OSM database timestamp, endpoint, stale flag)."""
    seen, out = set(), []
    for key in sorted(manifest):
        m = manifest[key]
        f = Path(cache_dir) / f"{key}.json"
        if m.get("group") != group or not f.exists():
            continue
        prov = {k: m.get(k) for k in ("retrieved_at", "osm_base", "endpoint")} | {"stale": bool(m.get("stale"))}
        for el in json.loads(f.read_text())["elements"]:
            k = (el["type"], el["id"])
            if k not in seen:
                seen.add(k)
                out.append((el, prov))
    return out


# --------------------------------------------------------------------------- selection rules
TYPE_LABELS = {"school": "School", "sports_hall": "Sports hall", "community_centre": "Community centre"}
LIFECYCLE_PREFIXES = ("disused:", "abandoned:", "demolished:", "razed:", "removed:", "was:", "construction:")


def classify(t):
    """(facility_type, subtype) for a candidate, or (None, exclusion reason). Rules R1-R6 in the README."""
    if t.get("disused") == "yes" or t.get("abandoned") == "yes" or "construction" in t \
            or any(k.startswith(LIFECYCLE_PREFIXES) for k in t):
        return None, "R5 lifecycle tag (disused / abandoned / under construction)"
    if t.get("amenity") == "school":
        ftype, sub = "school", t.get("school") or t.get("isced:level") or ""
    elif t.get("amenity") == "community_centre":
        ftype, sub = "community_centre", t.get("community_centre") or ""
    elif t.get("leisure") == "sports_hall" or t.get("building") in ("sports_hall", "sports_centre"):
        ftype, sub = "sports_hall", t.get("sport", "")
    elif t.get("leisure") == "sports_centre":
        if t.get("building", "no") == "no" and t.get("indoor") != "yes":
            return None, "R3 sports centre without an indoor building (outdoor site)"
        ftype, sub = "sports_hall", "sports centre (building)"
    else:
        return None, "not a selected facility type"
    return (ftype, sub.replace(";", ", ")), None


def candidate_frame(items, source):
    """GeoDataFrame (EPSG:3035) of classified OSM elements + an exclusion log. `items` = [(element, provenance)]."""
    rows, excluded = [], []
    for el, prov in items:
        t = el.get("tags", {})
        g = osm.element_geometry(el)
        rid = f"{el['type']}/{el['id']}"
        if g is None or g.is_empty:
            excluded.append((rid, "R6 no usable geometry"))
            continue
        if g.geom_type == "LineString" and g.is_closed and len(g.coords) >= 4:   # osm.py ignores leisure=* areas
            g = shapely.make_valid(shapely.Polygon(g.coords))
        is_poly = g.geom_type in ("Polygon", "MultiPolygon")
        if not is_poly and g.geom_type != "Point":
            excluded.append((rid, "R6 open line, not a site or building"))
            continue
        res, why = classify(t)
        if res is None:
            if why != "not a selected facility type":
                excluded.append((rid, why))
            continue
        ftype, sub = res
        rows.append({"osm_type": el["type"], "osm_id": el["id"], "facility_type": ftype, "facility_subtype": sub,
                     "tags": t, "source": source, **prov, "geometry": g})
    if not rows:
        return gpd.GeoDataFrame(columns=["osm_type", "osm_id", "facility_type", "tags", "geometry"],
                                geometry="geometry", crs=METRIC_CRS), excluded
    gdf = gpd.GeoDataFrame(rows, crs=WEB_CRS).to_crs(METRIC_CRS)
    poly = gdf.geom_type.isin(["Polygon", "MultiPolygon"])
    small = poly & gdf["tags"].map(lambda t: t.get("building", "no") != "no") & (gdf.area < MIN_BUILDING_M2)
    excluded += [(f"{r.osm_type}/{r.osm_id}", f"R4 building footprint < {MIN_BUILDING_M2} m²") for r in gdf[small].itertuples()]
    return gdf[~small].reset_index(drop=True), excluded


def norm_name(t):
    return " ".join(str(t.get("name", "")).lower().split())


SAME_OUTLINE_IOU = 0.95   # same-type outlines overlapping this much are one facility (e.g. a multipolygon + its outer way)
OSM_TYPE_PREF = {"way": 0, "relation": 1, "node": 2}


def drop_same_outline(gdf, iou=SAME_OUTLINE_IOU):
    """Indices of same-type outlines that duplicate another one (intersection over union >= `iou`).
    osm.drop_contained misses these because neither outline is strictly larger. The way is kept over the relation."""
    polys = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
    i, j = shapely.STRtree(polys.geometry.values).query(polys.geometry.values, predicate="intersects")
    keep = i < j
    a, b = polys.index[i[keep]], polys.index[j[keep]]
    ga, gb = gdf.geometry.loc[a].values, gdf.geometry.loc[b].values
    same = (gdf["facility_type"].loc[a].to_numpy() == gdf["facility_type"].loc[b].to_numpy()) & \
        (shapely.area(shapely.intersection(ga, gb)) >= iou * shapely.area(shapely.union(ga, gb)))
    drop = {}
    for x, y in zip(a[same], b[same]):
        lose, win = sorted([x, y], key=lambda k: (OSM_TYPE_PREF[gdf.at[k, "osm_type"]], k))[::-1]
        drop.setdefault(lose, win)
    return drop


def deduplicate(gdf, name_dist=50):
    """1. same OSM element in two sources (by type/id); 2. same-type outlines that are the same shape (IoU >= 0.95);
    3. a node or polygon inside a larger polygon of the same facility type (osm.drop_contained); 4. same type + same
    non-empty name within `name_dist` m (node next to its building or site outline). The polygon (or the first record)
    is kept; the dropped ids are listed in `merged_ids`."""
    gdf = gdf.drop_duplicates(["osm_type", "osm_id"]).reset_index(drop=True)
    gdf["cid"] = gdf["osm_type"] + "/" + gdf["osm_id"].astype(str)
    n0 = len(gdf)
    same_outline = drop_same_outline(gdf)
    pre_merged = {}
    for lose, win in same_outline.items():
        pre_merged.setdefault(gdf.at[win, "cid"], []).append(gdf.at[lose, "cid"])
    gdf = gdf.drop(index=list(same_outline)).reset_index(drop=True)
    before = set(gdf["cid"])
    gdf = osm.drop_contained(gdf, group_col="facility_type")
    contained = before - set(gdf["cid"])
    named = gdf.assign(nm=gdf["tags"].map(norm_name))
    named = named[named["nm"] != ""]                      # distance between outlines / points, not centres
    j = gpd.sjoin(named[["facility_type", "nm", "geometry"]], named[["facility_type", "nm", "geometry"]],
                  predicate="dwithin", distance=name_dist)
    j = j[(j.index < j["index_right"]) & (j["facility_type_left"] == j["facility_type_right"]) & (j["nm_left"] == j["nm_right"])]
    is_poly = gdf.geom_type.isin(["Polygon", "MultiPolygon"]).to_numpy()
    drop, merged = set(), {}
    for a, b in zip(j.index, j["index_right"]):
        keep, lose = (b, a) if (is_poly[b] and not is_poly[a]) else (a, b)
        if keep in drop or lose in drop:
            continue
        drop.add(lose)
        merged.setdefault(keep, []).append(gdf.at[lose, "cid"])
    gdf["merged_ids"] = [", ".join(pre_merged.get(c, []) + merged.get(i, [])) for i, c in enumerate(gdf["cid"])]
    gdf = gdf.drop(index=sorted(drop)).reset_index(drop=True)
    return gdf, {"after_source_dedup": n0, "dropped_same_outline": len(same_outline), "dropped_contained": len(contained),
                 "dropped_same_name_nearby": len(drop)}


# --------------------------------------------------------------------------- municipality and country
# Country from the national municipality code carried by the OSM boundary (checked on the cached boundaries).
# Boundaries without one of these keys (e.g. Luxembourg communes: only ref:lau2) keep an empty country, flagged.
COUNTRY_CODE_KEYS = [("de:amtlicher_gemeindeschluessel", "DEU"), ("ref:INS", "BEL"), ("ref:gemeentecode", "NLD")]


def admin_frame(items):
    """Municipality polygons (EPSG:3035): admin_level 8, plus German admin_level 6 units that are municipalities
    themselves (kreisfreie Städte: 8-digit Gemeindeschlüssel)."""
    rows = []
    for el, _ in items:
        t = el.get("tags", {})
        ags = t.get("de:amtlicher_gemeindeschluessel", "")
        lvl = t.get("admin_level")
        if el["type"] != "relation" or not (lvl == "8" or (lvl == "6" and len(ags) == 8)):
            continue
        g = osm.element_geometry(el)
        if g is None or g.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        code, iso = "", ""
        for k, c in COUNTRY_CODE_KEYS:
            if t.get(k):
                code, iso = t[k], c
                break
        rows.append({"rel_id": el["id"], "municipality": t.get("name", ""), "municipality_code": code,
                     "municipality_level": int(lvl), "country": iso, "geometry": g})
    return gpd.GeoDataFrame(rows, crs=WEB_CRS).to_crs(METRIC_CRS) if rows else None


def assign_admin(pts, admin, hexes=None):
    """Municipality and country of each reference point. Several matches (overlapping boundaries) -> the smallest
    unit, flagged; none -> empty. If OBAT hexagons are given, their majority building country is a cross-check."""
    out = pd.DataFrame({"municipality": "", "municipality_code": "", "municipality_level": pd.NA, "country": "",
                        "admin_note": ""}, index=pts.index)
    if admin is not None:
        admin = admin.assign(a=admin.area)
        j = gpd.sjoin(pts[["geometry"]], admin, predicate="within").sort_values("a")
        n = j.groupby(level=0).size()
        first = j[~j.index.duplicated()]
        for c in ["municipality", "municipality_code", "municipality_level", "country"]:
            out.loc[first.index, c] = first[c]
        out.loc[n[n > 1].index, "admin_note"] = "several boundaries overlap: smallest used"
    out.loc[(out["municipality"] != "") & (out["country"] == ""), "admin_note"] = \
        "boundary has no BE/DE/NL municipality code: outside the challenge countries?"
    out.loc[out["municipality"] == "", "admin_note"] = "no municipality boundary found"
    out["country_check"] = ""
    if hexes is not None:
        h = gpd.sjoin(pts[["geometry"]], hexes[["country", "geometry"]], predicate="within")
        h = h[~h.index.duplicated()]["country"]
        chk = pd.Series("no OBAT hexagon", index=pts.index)
        both = h.index[(out.loc[h.index, "country"] != "").to_numpy()]
        chk.loc[both] = np.where(out.loc[both, "country"] == h.loc[both], "agrees with OBAT", "differs from OBAT ("
                                 + h.loc[both] + ")")
        chk.loc[h.index.difference(both)] = "OBAT only: " + h.loc[h.index.difference(both)]
        out["country_check"] = chk
    return out


# --------------------------------------------------------------------------- spatial screening
CATEGORIES = {
    "inside_observed": "Inside the mapped observed flood extent (July 2021)",
    "outside_extent_in_ems": "Outside the mapped flood extent, within an EMS mapped area",
    "outside_ems_coverage": "Outside EMS mapped coverage (flooding there was not mapped)",
    "boundary_unresolved": "On the boundary / unresolved",
}


def join_labels(pts, geoms, labels, sep):
    """For each point, the sorted distinct labels of the geometries it intersects, joined with `sep` ('' if none)."""
    out = np.full(len(pts), "", dtype=object)
    i, j = shapely.STRtree(geoms).query(pts, predicate="intersects")
    if len(i):
        s = pd.Series(labels[j], index=i).groupby(level=0).agg(lambda v: sep.join(sorted(set(v))))
        out[s.index] = s.to_numpy()
    return out


def screen(points, footprints, flood, aoi, tol=EDGE_TOL):
    """Screening category of each reference point against the observed flood extent (flooded areas + traces,
    unsimplified) and the EMS mapped areas. All geometry in EPSG:3035 (metres). Rules, in order:
      invalid point                                   -> boundary_unresolved
      inside the extent, more than `tol` from its edge -> inside_observed
      within `tol` of the extent edge                  -> boundary_unresolved
      footprint (site / building) overlaps the extent  -> boundary_unresolved (reference point outside)
      inside an EMS area, more than `tol` from its edge -> outside_extent_in_ems
      outside every EMS area, more than `tol` away      -> outside_ems_coverage
      otherwise (within `tol` of an EMS area edge)      -> boundary_unresolved"""
    assert flood.crs == aoi.crs == points.crs == METRIC_CRS
    pts = np.asarray(points.values)
    n = len(pts)
    extent = shapely.get_parts(shapely.union_all(shapely.make_valid(flood.geometry.values)))
    extent = extent[shapely.get_type_id(extent) == 3]           # polygons only (drop any collapsed slivers)
    rings = shapely.boundary(extent)
    ok = ~shapely.is_empty(pts) & shapely.is_valid(pts) & np.isfinite(shapely.get_coordinates(pts)).all(axis=1) \
        if n else np.zeros(0, bool)
    inside = np.zeros(n, bool)
    i, _ = shapely.STRtree(extent).query(pts, predicate="within")
    inside[i] = True
    d_edge = np.full(n, np.nan)
    i, j = shapely.STRtree(rings).query_nearest(pts, all_matches=False)
    d_edge[i] = shapely.distance(pts[i], rings[j])
    fp_hit = np.zeros(n, bool)
    fp = np.asarray(footprints.values)
    i, _ = shapely.STRtree(extent).query(fp, predicate="intersects")
    fp_hit[i] = True
    kinds = join_labels(pts, flood.geometry.values, flood["kind"].to_numpy(), "+")
    aoi_u = shapely.union_all(aoi.geometry.values)
    in_aoi = shapely.within(pts, aoi_u)
    d_aoi = shapely.distance(pts, shapely.boundary(aoi_u))
    act = join_labels(pts, aoi.geometry.values, aoi["activation"].to_numpy(), ", ")

    cat = np.select(
        [~ok, inside & (d_edge > tol), d_edge <= tol, fp_hit, in_aoi & (d_aoi > tol), ~in_aoi & (d_aoi > tol)],
        ["boundary_unresolved", "inside_observed", "boundary_unresolved", "boundary_unresolved",
         "outside_extent_in_ems", "outside_ems_coverage"], "boundary_unresolved")
    reason = np.select(
        [~ok, inside & (d_edge > tol), d_edge <= tol, fp_hit, in_aoi & (d_aoi > tol), ~in_aoi & (d_aoi > tol)],
        ["invalid or empty coordinates", f"more than {tol} m inside the observed extent",
         f"within {tol} m of the observed flood edge", "site or building outline overlaps the observed extent",
         f"outside the observed extent, more than {tol} m inside an EMS mapped area",
         f"more than {tol} m outside every EMS mapped area"],
        f"within {tol} m of an EMS mapped-area edge")
    return pd.DataFrame({"screen_category": cat, "screen_reason": reason,
                         "flood_kind": np.where(inside | (d_edge <= tol), kinds, ""),
                         "flood_edge_dist_m": np.round(np.where(inside, -d_edge, d_edge), 1),
                         "ems_activation": act,
                         "aoi_edge_dist_m": np.round(np.where(in_aoi, -d_aoi, d_aoi), 1)}, index=points.index)


# --------------------------------------------------------------------------- inventory
def tag(t, *keys):
    return next((str(t[k]) for k in keys if t.get(k)), "")


def build_inventory(offline=False, refresh=False, log=print):
    aoi, region = region_from_cache()
    flood = gpd.read_parquet(CACHE / "flood.parquet")
    hexes = gpd.read_parquet(CACHE / "hexes.parquet")
    region_wgs = to_wgs(region)
    m_school, m_shel = acquire(region_wgs, offline, refresh)

    schools, ex1 = candidate_frame([(e, p) for e, p in read_with_provenance(OSM_CACHE, m_school, "facilities")
                                    if e.get("tags", {}).get("amenity") == "school"], "osm_facilities_cache")
    others, ex2 = candidate_frame(read_with_provenance(SOSM_CACHE, m_shel, "shelters"), "osm_shelter_query")
    gdf = pd.concat([schools, others], ignore_index=True)
    n_raw = len(gdf)
    pts = gdf.representative_point()
    in_region = shapely.intersects(pts.values, region)
    excluded = ex1 + ex2 + [(f"{r.osm_type}/{r.osm_id}", "R1 outside the analysis area") for r in gdf[~in_region].itertuples()]
    gdf, dedup = deduplicate(gpd.GeoDataFrame(gdf[in_region], crs=METRIC_CRS))
    log(f"  {n_raw:,} selected OSM features, {int(in_region.sum()):,} in the analysis area, {len(gdf):,} after de-duplication")

    ref = gpd.GeoSeries(gdf.representative_point(), crs=METRIC_CRS)
    admin = admin_frame(read_with_provenance(SOSM_CACHE, m_shel, "admin"))
    adm = assign_admin(gpd.GeoDataFrame(geometry=ref), admin, hexes)
    scr = screen(ref, gdf.geometry, flood, aoi)
    ll = ref.to_crs(WEB_CRS)
    t = gdf["tags"]
    is_poly = gdf.geom_type.isin(["Polygon", "MultiPolygon"])
    inv = pd.DataFrame({
        "candidate_id": "osm:" + gdf["cid"],
        "name": t.map(lambda x: tag(x, "name", "official_name", "short_name")),
        "facility_type": gdf["facility_type"], "facility_subtype": gdf["facility_subtype"],
        "lon": ll.x.round(6), "lat": ll.y.round(6),
        "osm_geometry": np.where(is_poly, "outline", "point"),
        "footprint_m2": np.where(is_poly, gdf.area.round(0), np.nan),
        **{c: adm[c].to_numpy() for c in ["municipality", "municipality_code", "municipality_level", "country", "admin_note",
                                          "country_check"]},
        "source": "OpenStreetMap via Overpass API",
        "source_url": "https://www.openstreetmap.org/" + gdf["cid"],
        "source_endpoint": gdf["endpoint"], "osm_data_timestamp": gdf["osm_base"], "retrieved_at": gdf["retrieved_at"],
        "cache_stale": gdf["stale"],
        "osm_check_date": t.map(lambda x: tag(x, "check_date", "survey:date")),
        "osm_start_date": t.map(lambda x: tag(x, "start_date")),
        "osm_operator": t.map(lambda x: tag(x, "operator")),
        "osm_building_levels": t.map(lambda x: tag(x, "building:levels")),
        "existence_status": "mapped_in_osm_not_field_verified",
        "designation_status": "not_verified",
        "verification_note": "OSM record retrieved; current operation, emergency-shelter designation and suitability not checked",
        "shelter_capacity": pd.array([pd.NA] * len(gdf), dtype="Int64"),
        "capacity_source": "",
        "osm_capacity_tag": t.map(lambda x: tag(x, "capacity")),
        **{c: scr[c].to_numpy() for c in scr.columns},
        "merged_ids": gdf["merged_ids"],
        "footprint_wkt": gpd.GeoSeries(gdf.geometry.values, crs=METRIC_CRS).to_crs(WEB_CRS).set_precision(1e-6).to_wkt(),
    })
    inv["in_challenge_countries"] = inv["country"].isin(["BEL", "DEU", "NLD"])
    inv = gpd.GeoDataFrame(inv, geometry=ll.values, crs=WEB_CRS).sort_values("candidate_id").reset_index(drop=True)

    tiles = list(m_school.values()) + list(m_shel.values())
    ok = [m for m in tiles if m.get("status") == "ok"]
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "analysis_area": f"Copernicus EMS areas of interest (EMSR517/518/520) + {AOI_BUFFER} m buffer",
        "analysis_area_km2": round(region.area / 1e6),
        "edge_tolerance_m": EDGE_TOL,
        "retrieved_from": min((m["retrieved_at"] for m in ok), default=None),
        "retrieved_to": max((m["retrieved_at"] for m in ok), default=None),
        "osm_base_from": min((m["osm_base"] for m in ok if m.get("osm_base")), default=None),
        "osm_base_to": max((m["osm_base"] for m in ok if m.get("osm_base")), default=None),
        "tiles": len(tiles), "tiles_ok": len(ok),
        "tiles_stale": [m["bbox"] for m in tiles if m.get("stale")],
        "tiles_missing": [[m["group"], m["bbox"]] for m in tiles if m.get("status") != "ok"],
        "n_selected_raw": n_raw, "dedup": dedup, "n_candidates": len(inv),
        "excluded": pd.Series([r for _, r in excluded]).value_counts().to_dict(),
        "counts": inv.groupby(["facility_type", "screen_category"]).size().unstack(fill_value=0).to_dict("index"),
        "countries": inv["country"].replace("", "unknown").value_counts().to_dict(),
    }
    return inv, meta


# --------------------------------------------------------------------------- checks and export
def check(inv, meta):
    """Integrity checks; returns a list of problems (empty = all passed)."""
    p = []
    if inv["candidate_id"].duplicated().any():
        p.append(f"duplicate candidate ids: {inv.loc[inv['candidate_id'].duplicated(), 'candidate_id'].tolist()[:5]}")
    if not (inv["lon"].between(-180, 180) & inv["lat"].between(-90, 90)).all() or inv[["lon", "lat"]].isna().any().any():
        p.append("invalid coordinates")
    x0, y0, x1, y1 = to_wgs(region_from_cache()[1]).bounds
    if not (inv["lon"].between(x0, x1) & inv["lat"].between(y0, y1)).all():
        p.append("coordinates outside the analysis area envelope")
    if not inv["screen_category"].isin(list(CATEGORIES)).all():
        p.append("unknown screening category")
    if (inv["screen_category"] == "inside_observed").any() and (inv.loc[inv["screen_category"] == "inside_observed",
                                                                         "flood_edge_dist_m"] >= -EDGE_TOL).any():
        p.append("inside_observed candidate within the edge tolerance")
    if inv["shelter_capacity"].notna().any() and (inv["capacity_source"] == "").any():
        p.append("capacity without a documented source")
    if inv["name"].eq("").all() or inv["retrieved_at"].isna().any():
        p.append("missing names or retrieval dates")
    fp = gpd.GeoDataFrame({"facility_type": inv["facility_type"], "osm_type": inv["candidate_id"].str.split("[:/]").str[1]},
                          geometry=shapely.from_wkt(inv["footprint_wkt"]), crs=WEB_CRS).to_crs(METRIC_CRS)
    if drop_same_outline(fp):
        p.append(f"{len(drop_same_outline(fp))} same-type outlines duplicate another (IoU >= {SAME_OUTLINE_IOU})")
    tp = inv.assign(nm=inv["name"].str.lower().str.strip())
    same = tp[tp["nm"] != ""].duplicated(["facility_type", "nm", "lon", "lat"])
    if same.any():
        p.append(f"{int(same.sum())} records with identical type, name and coordinates")
    return p


def export(inv, meta):
    SCACHE.mkdir(parents=True, exist_ok=True)
    inv.to_parquet(INVENTORY)
    META.write_text(json.dumps(meta, indent=1, default=str))
    flat = inv.drop(columns=["geometry", "footprint_wkt"])
    flat.to_csv(OUT_CSV, index=False)
    inv.drop(columns=["footprint_wkt"]).to_file(OUT_GEOJSON, driver="GeoJSON")


def load_cached():
    """(inventory, meta) from the local cache for map.py, or (None, None). Never contacts a server."""
    if not (INVENTORY.exists() and META.exists()):
        return None, None
    return gpd.read_parquet(INVENTORY), json.loads(META.read_text())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cached tiles only")
    ap.add_argument("--refresh", action="store_true", help="re-download shelter and boundary tiles")
    ap.add_argument("--fetch-only", action="store_true", help="download missing tiles and stop")
    args = ap.parse_args()
    if args.fetch_only:
        acquire(to_wgs(region_from_cache()[1]), refresh=args.refresh)
        raise SystemExit
    print("Building candidate shelter inventory ...")
    try:
        inv, meta = build_inventory(args.offline, args.refresh)
    except Exception as e:
        old = load_cached()[1]
        print(f"FAILED: {e}\n" + (f"Keeping the cached inventory built {old['built_at']}." if old else "No cached inventory exists."))
        raise SystemExit(1)
    problems = check(inv, meta)
    for q in problems:
        print("  CHECK FAILED:", q)
    export(inv, meta)
    print(f"  {meta['n_candidates']:,} candidates; OSM data {meta['osm_base_from']} – {meta['osm_base_to']}; "
          f"{meta['tiles_ok']}/{meta['tiles']} tiles ok, {len(meta['tiles_stale'])} stale")
    print(pd.DataFrame(meta["counts"]).T.to_string())
    print("  excluded:", meta["excluded"])
    print("  country:", meta["countries"])
    print(f"Saved {OUT_CSV.name}, {OUT_GEOJSON.name}, {INVENTORY.relative_to(HERE)}" + ("" if not problems else " (with check failures)"))
    raise SystemExit(1 if problems else 0)
