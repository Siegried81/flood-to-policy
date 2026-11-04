"""
osm.py - OpenStreetMap facilities and infrastructure for the EMS study region (Overpass API).

Acquisition: the region is split into 0.5° tiles and each tile is queried once per feature group.
Raw Overpass JSON is cached per tile in cache/osm/ with a provenance manifest (endpoint, query,
retrieval time, OSM database timestamp). If a refresh fails, the cached tile is kept and marked stale.

Parsing: nodes -> points, closed area-like ways -> polygons, relations -> polygons from their outer
members. Duplicates are removed (same element in two tiles; a node inside a polygon of the same
category; bridge carriageways of one structure merged into one asset).

Data © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright).
"""
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]  # public mirror, used as fallback
USER_AGENT = "floodmap-priority/0.1 (European AI Challenge 2026 hackathon; contact via FARI)"
TILE_DEG = 0.5
TIMEOUT_S = 240          # server-side query timeout; the HTTP timeout is a bit longer
MAX_TRIES = 5
PAUSE_S = 3              # courtesy pause between requests (public servers allow ~2 parallel slots)
WGS = "EPSG:4326"
METRIC = "EPSG:3035"

# Verified against the OSM wiki (Key:amenity, Key:healthcare, Key:social_facility, Key:bridge, Key:power, Key:man_made).
QUERIES = {
    "facilities": """
  nwr["amenity"~"^(hospital|clinic|school|kindergarten|childcare|nursing_home|social_facility)$"];
  nwr["healthcare"~"^(hospital|clinic|centre|nursing_home|rehabilitation)$"];
  nwr["social_facility"~"^(nursing_home|assisted_living|group_home|day_care|shelter)$"];""",
    "infrastructure": """
  way["bridge"]["bridge"!="no"]["highway"~"^(motorway|trunk|primary|secondary|tertiary)(_link)?$"];
  way["bridge"]["bridge"!="no"]["railway"~"^(rail|light_rail)$"];
  wr["man_made"="bridge"];
  way["tunnel"]["tunnel"!~"^(no|building_passage)$"]["highway"~"^(motorway|trunk|primary|secondary)(_link)?$"];
  way["tunnel"]["tunnel"!~"^(no|building_passage)$"]["railway"~"^(rail|light_rail)$"];
  nwr["power"~"^(substation|plant)$"];
  nwr["man_made"~"^(wastewater_plant|water_works|pumping_station|water_tower)$"];
  nwr["amenity"~"^(fire_station|police)$"];
  nwr["emergency"="ambulance_station"];""",
}


# --------------------------------------------------------------------------- acquisition
def tiles(region_wgs, step=TILE_DEG):
    """0.5° tiles (s, w, n, e) covering the region, clipped to its envelope, keeping only those touching it."""
    minx, miny, maxx, maxy = region_wgs.bounds
    out = []
    for x in np.arange(np.floor(minx / step) * step, maxx, step):
        for y in np.arange(np.floor(miny / step) * step, maxy, step):
            box = shapely.box(max(x, minx), max(y, miny), min(x + step, maxx), min(y + step, maxy))
            if box.intersects(region_wgs):
                w, s, e, n = (round(v, 5) for v in box.bounds)
                out.append((s, w, n, e))
    return out


def build_query(group, bbox, queries=QUERIES):
    s, w, n, e = bbox
    return f"[out:json][timeout:{TIMEOUT_S}][bbox:{s},{w},{n},{e}];\n({queries[group]}\n);\nout geom;"


def cache_key(group, bbox, queries=QUERIES):
    return f"{group}_{hashlib.sha1(build_query(group, bbox, queries).encode()).hexdigest()[:10]}"


def overpass(query, log=print):
    """POST a query with retries: exponential backoff, Retry-After on 429, fallback mirror. Returns (json, endpoint)."""
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(MAX_TRIES):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S + 30) as r:
                js = json.load(r)
            if "remark" in js and "runtime error" in js["remark"]:  # server-side timeout / memory: partial result
                raise RuntimeError(js["remark"])
            return js, url
        except urllib.error.HTTPError as e:
            last = e
            wait = int(e.headers.get("Retry-After") or 0) if e.code == 429 else 0
            e.close()  # release the socket (otherwise left in CLOSE-WAIT)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            last, wait = e, 0
        wait = max(wait, 10 * 2 ** attempt)
        log(f"    {url.split('/')[2]}: {str(last)[:120]} -> retry in {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {MAX_TRIES} tries: {last}")


def fetch(region_wgs, cache_dir, refresh=False, log=print, queries=QUERIES):
    """Download (or reuse) every tile of each query group. Returns the provenance manifest (dict)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    mf = cache_dir / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {}
    tl, keys = tiles(region_wgs), []
    for group in queries:
        for i, bbox in enumerate(tl):
            q = build_query(group, bbox, queries)
            key = cache_key(group, bbox, queries)
            f = cache_dir / f"{key}.json"
            keys.append(key)
            if f.exists() and not refresh:
                continue
            log(f"  OSM {group} tile {i + 1}/{len(tl)} {bbox} ...")
            try:
                js, url = overpass(q, log)
            except RuntimeError as e:
                if f.exists():
                    manifest[key]["stale"] = True
                    log(f"    failed, keeping cached copy from {manifest[key]['retrieved_at']} (marked stale)")
                else:
                    manifest[key] = {"group": group, "bbox": bbox, "status": "failed", "error": str(e)}
                    log("    FAILED, no cached copy: this tile has no OSM data")
                mf.write_text(json.dumps(manifest, indent=1))
                continue
            f.write_text(json.dumps(js))
            manifest[key] = {"group": group, "bbox": bbox, "status": "ok", "stale": False, "endpoint": url,
                             "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "osm_base": js.get("osm3s", {}).get("timestamp_osm_base"),
                             "n_elements": len(js.get("elements", [])), "query": q}
            mf.write_text(json.dumps(manifest, indent=1))
            time.sleep(PAUSE_S)
    return {k: manifest[k] for k in keys if k in manifest}


def read_cached(cache_dir, manifest, group):
    """All cached elements of a group, de-duplicated across tiles by (type, id)."""
    seen, out = set(), []
    for key, m in manifest.items():
        f = Path(cache_dir) / f"{key}.json"
        if m.get("group") != group or not f.exists():
            continue
        for el in json.loads(f.read_text())["elements"]:
            k = (el["type"], el["id"])
            if k not in seen:
                seen.add(k)
                out.append(el)
    return out


# --------------------------------------------------------------------------- geometry
AREA_KEYS = {"amenity", "building", "man_made", "power", "healthcare", "social_facility", "emergency", "landuse", "area"}


def _coords(geom):
    return [(p["lon"], p["lat"]) for p in geom if p is not None]


def element_geometry(el):
    """Shapely geometry (WGS84) for an Overpass `out geom` element, or None."""
    t = el.get("tags", {})
    if el["type"] == "node":
        return shapely.Point(el["lon"], el["lat"])
    if el["type"] == "way":
        c = _coords(el.get("geometry", []))
        if len(c) < 2:
            return None
        linear = "highway" in t or "railway" in t
        if len(c) >= 4 and c[0] == c[-1] and not linear and (AREA_KEYS & t.keys()):
            return shapely.make_valid(shapely.Polygon(c))
        return shapely.LineString(c)
    if el["type"] == "relation":
        lines = [shapely.LineString(_coords(m["geometry"])) for m in el.get("members", [])
                 if m.get("type") == "way" and m.get("role", "outer") in ("outer", "") and len(m.get("geometry") or []) >= 2]
        if not lines:
            return None
        polys = shapely.get_parts(shapely.polygonize(shapely.get_parts(shapely.line_merge(shapely.union_all(lines)))))
        if len(polys):
            return shapely.make_valid(shapely.union_all(polys))
        return shapely.union_all(lines)
    return None


def to_frame(elements, classify):
    """GeoDataFrame (EPSG:3035) of classified elements; unclassified ones are dropped."""
    rows = []
    for el in elements:
        t = el.get("tags", {})
        cls = classify(t)
        if cls is None:
            continue
        g = element_geometry(el)
        if g is None or g.is_empty:
            continue
        rows.append({"osm_type": el["type"], "osm_id": el["id"], **cls, "tags": t, "geometry": g})
    if not rows:
        cols = ["osm_type", "osm_id", "category", "label", "importance", "dependency", "overnight", "carried", "tags", "geometry"]
        return gpd.GeoDataFrame(columns=cols, geometry="geometry", crs=METRIC)
    return gpd.GeoDataFrame(rows, crs=WGS).to_crs(METRIC)


# --------------------------------------------------------------------------- classification: vulnerable facilities
# Factor inputs (expert assumptions, see methodology): D = dependency on assistance to evacuate (0, 0.5, 1),
# O = overnight occupancy (0 or 1). None = unknown -> mid value 0.5 and flagged.
FACILITY_TYPES = {
    "hospital":        ("Hospital", 1.0, 1),
    "nursing_home":    ("Nursing / elderly care home", 1.0, 1),
    "assisted_living": ("Assisted living", 0.5, 1),
    "group_home":      ("Group home (care)", 0.5, 1),
    "shelter":         ("Shelter", 0.5, 1),
    "day_care":        ("Adult day care", 1.0, 0),
    "kindergarten":    ("Kindergarten / childcare", 1.0, 0),
    "school":          ("School", 0.5, 0),
    "clinic":          ("Clinic / health centre", 0.5, 0),
    "social_other":    ("Other social facility", None, None),
}
SOCIAL_EXCLUDED = {"food_bank", "soup_kitchen", "outreach", "clothing_bank", "dairy_kitchen", "workshop", "ambulatory_care"}


def classify_facility(t):
    a, h, sf = t.get("amenity"), t.get("healthcare"), t.get("social_facility")
    who = t.get("social_facility:for", "")
    if a == "hospital" or h == "hospital":
        cat = "hospital"
    elif a == "nursing_home" or h == "nursing_home" or sf == "nursing_home":
        cat = "nursing_home"
    elif sf in ("assisted_living", "group_home", "shelter", "day_care"):
        cat = sf
    elif a in ("kindergarten", "childcare"):
        cat = "kindergarten"
    elif a == "school":
        cat = "school"
    elif a == "clinic" or h in ("clinic", "centre", "rehabilitation"):
        cat = "clinic"
    elif a == "social_facility" and sf not in SOCIAL_EXCLUDED:
        cat = "social_other"
    else:
        return None
    label, d, o = FACILITY_TYPES[cat]
    # Residents explicitly tagged as seniors / disabled people raise dependency (evidence from the OSM tag)
    if cat in ("assisted_living", "group_home") and any(w in who for w in ("senior", "disabled", "mental_health")):
        d = 1.0
    return {"category": cat, "label": label, "dependency": d, "overnight": o}


# --------------------------------------------------------------------------- classification: critical infrastructure
ROAD_CLASS = {"motorway": 1.0, "trunk": 1.0, "primary": 0.85, "secondary": 0.7, "tertiary": 0.55}
RAIL_CLASS = {"rail": 1.0, "light_rail": 0.7}
INFRA_LABELS = {
    "bridge": "Bridge", "tunnel": "Tunnel / underpass", "substation": "Electrical substation", "power_plant": "Power plant",
    "water_works": "Drinking-water works", "wastewater_plant": "Wastewater treatment", "pumping_station": "Pumping station",
    "water_tower": "Water tower", "fire_station": "Fire station", "ambulance_station": "Ambulance station", "police": "Police station",
}
INFRA_IMPORTANCE = {  # function importance I in [0, 1] (expert assumption); bridges/tunnels use the carried-line class
    "power_plant": 0.8, "water_works": 1.0, "wastewater_plant": 0.8, "pumping_station": 0.6, "water_tower": 0.6,
    "fire_station": 1.0, "ambulance_station": 1.0, "police": 0.8,
}


def _max_voltage(t):
    try:
        return max(float(v) for v in str(t.get("voltage", "")).split(";") if v.strip())
    except ValueError:
        return None


def line_class(t):
    """(carried line description, importance) for a highway/railway way, or None."""
    hw = t.get("highway", "").removesuffix("_link")
    if hw in ROAD_CLASS:
        return f"{hw} road", ROAD_CLASS[hw]
    if t.get("railway") in RAIL_CLASS:
        return t["railway"].replace("_", " "), RAIL_CLASS[t["railway"]]
    return None


def classify_infra(t):
    lc = line_class(t)
    if lc and t.get("bridge", "no") != "no":
        return {"category": "bridge", "label": INFRA_LABELS["bridge"], "carried": lc[0], "importance": lc[1]}
    if lc and t.get("tunnel", "no") not in ("no", "building_passage"):
        return {"category": "tunnel", "label": INFRA_LABELS["tunnel"], "carried": lc[0], "importance": lc[1]}
    if t.get("man_made") == "bridge":
        return {"category": "bridge_outline", "label": "Bridge outline", "importance": None}
    if t.get("power") == "substation":
        sub, v = t.get("substation"), _max_voltage(t)
        if sub == "minor_distribution":
            return None  # street transformer kiosks: too numerous and too local to rank
        if sub == "transmission" or (v or 0) >= 110_000:
            return {"category": "substation", "label": "High-voltage substation", "importance": 1.0}
        if sub == "distribution" or (v or 0) >= 10_000:
            return {"category": "substation", "label": "Distribution substation", "importance": 0.7}
        return {"category": "substation", "label": "Substation (voltage unknown)", "importance": 0.6, "assumed": True}
    if t.get("power") == "plant":
        cat = "power_plant"
    elif t.get("man_made") in ("wastewater_plant", "water_works", "pumping_station", "water_tower"):
        cat = t["man_made"]
    elif t.get("amenity") in ("fire_station", "police"):
        cat = t["amenity"]
    elif t.get("emergency") == "ambulance_station":
        cat = "ambulance_station"
    else:
        return None
    return {"category": cat, "label": INFRA_LABELS[cat], "importance": INFRA_IMPORTANCE[cat]}


# --------------------------------------------------------------------------- de-duplication
def _components(n, pairs):
    """Connected components (union-find) for n items and an iterable of (i, j) pairs."""
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    return np.array([find(i) for i in range(n)])


def drop_contained(gdf, group_col="category"):
    """Remove features whose representative point lies inside another polygon of the same group
    (e.g. a hospital node inside the hospital site, a school building inside the school grounds).
    A name missing on the kept polygon is taken from the dropped feature."""
    gdf = gdf.reset_index(drop=True)
    polys = gdf[gdf.geom_type.isin(["Polygon", "MultiPolygon"])]
    pts = gdf.set_geometry(gdf.representative_point())
    j = gpd.sjoin(pts[[group_col, "geometry"]], polys[[group_col, "geometry"]], predicate="within")
    j = j[(j[f"{group_col}_left"] == j[f"{group_col}_right"]) & (j.index != j["index_right"])]
    # keep the largest polygon of a nested chain: drop i if it sits in a polygon j with larger area
    area = gdf.area
    j = j[area.loc[j.index].to_numpy() < area.loc[j["index_right"]].to_numpy()]
    for i, k in zip(j.index, j["index_right"]):
        if not gdf.at[k, "tags"].get("name") and gdf.at[i, "tags"].get("name"):
            gdf.at[k, "tags"] = {**gdf.at[k, "tags"], "name": gdf.at[i, "tags"]["name"]}
    return gdf.drop(index=j.index.unique()).reset_index(drop=True)


def merge_linear(gdf, outlines, tol=15):
    """Group bridge (or tunnel) ways into structures: ways within `tol` m of each other, or inside the same
    man_made=bridge outline, form one asset (dual carriageways, segmented viaducts). Importance = max of the
    carried lines. Outlines carrying none of the selected lines are dropped."""
    if gdf.empty:
        return gdf
    gdf = gdf.reset_index(drop=True)
    shapes = pd.concat([gdf[["geometry"]], outlines[["geometry"]]], ignore_index=True)
    buf = gpd.GeoDataFrame(geometry=shapes.buffer(tol / 2), crs=gdf.crs)
    j = gpd.sjoin(buf, buf, predicate="intersects")
    comp = _components(len(shapes), zip(j.index, j["index_right"]))[: len(gdf)]
    rows = []
    for c, g in gdf.groupby(comp):
        best = g.loc[g["importance"].idxmax()]
        names = sorted({n for n in (t.get("name") or t.get("ref") for t in g["tags"]) if n})
        rows.append({"osm_type": best.osm_type, "osm_id": best.osm_id, "osm_ids": [f"{a}/{b}" for a, b in zip(g.osm_type, g.osm_id)],
                     "category": best.category, "label": best.label, "carried": ", ".join(sorted(set(g["carried"]))),
                     "importance": g["importance"].max(),
                     "tags": {**best.tags, **({"name": " / ".join(names[:3])} if names else {})},
                     "geometry": shapely.line_merge(shapely.union_all(g.geometry.values))})
    return gpd.GeoDataFrame(rows, crs=gdf.crs)


def facilities(elements):
    df = to_frame(elements, classify_facility)
    n0 = len(df)
    df = drop_contained(df)
    return df, {"raw": n0, "after_dedup": len(df)}


def infrastructure(elements):
    df = to_frame(elements, classify_infra)
    n0 = len(df)
    outlines = df[(df["category"] == "bridge_outline") & df.geom_type.isin(["Polygon", "MultiPolygon"])]
    linear = [merge_linear(df[df["category"] == c], outlines if c == "bridge" else outlines.iloc[:0]) for c in ("bridge", "tunnel")]
    sites = drop_contained(df[~df["category"].isin(["bridge", "tunnel", "bridge_outline"])])
    out = pd.concat([*linear, sites], ignore_index=True)
    return gpd.GeoDataFrame(out, crs=df.crs), {"raw": n0, "after_dedup": len(out)}
