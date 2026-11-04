"""
priority_map.py - Asset screening scores (July 2021 floods, BE / DE / NL) for the optional context layers of
flood_map.html (built by map.py; the separate priority_map.html is retired).

Two asset screening scores, recomputed in the browser when the user moves the asset weight sliders:
  S_people          vulnerable facilities (hospitals, care homes, schools, ...) from OpenStreetMap
  S_infrastructure  bridges, tunnels, substations, water, emergency services from OpenStreetMap
Both combine P (residents), B (buildings) and F (observed July 2021 flooding) with user weights and a
documented type factor. These are scores of individual ASSETS; they are not the area planning priority of
flood_map.html (scene 4) and their values are not comparable with it. The former P/B/F area shading is not shown.

Reuses the map.py caches (EMS, OBAT hexagons, GHS-POP) and adds cache/osm (Overpass) and
cache/priority (indicators, asset records). See PRIORITY_SCORING_METHODOLOGY.md and DATA_QUALITY_REPORT.md.

Usage:  python priority_map.py --offline     # cached OSM tiles only: rewrite cache/priority/assets.json + CSV
        python priority_map.py               # fetch missing OSM tiles first (Overpass is slow)
        python priority_map.py --refresh-osm # re-download every OSM tile
        python priority_map.py --recompute   # recompute hexagon indicators (≈ 2-3 min)
Output: cache/priority/assets.json (read by map.py), priority_ranking.csv
"""
import argparse
import json
import re
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

import map as basemap
from priority import indicators as ind
from priority import osm
from priority import scoring as sc

PCACHE = basemap.CACHE / "priority"
OSM_CACHE = basemap.CACHE / "osm"
OUT_CSV = basemap.HERE / "priority_ranking.csv"
ASSET_CACHE = PCACHE / "assets.json"
WATER_BUFFER = 10         # m, a bridge touching the EMS reference water layer (+10 m) "crosses water"
NOT_WATER_FACTOR = 0.8    # bridges not crossing mapped water (e.g. over roads): flood flow exposure lower (assumption)


# --------------------------------------------------------------------------- data
def load_hexes(d, region, recompute=False):
    f = PCACHE / "hexes.parquet"
    if f.exists() and not recompute:
        return gpd.read_parquet(f)
    print("Computing hexagon indicators (population, buildings, flooded and mapped area) ...")
    hx = ind.hex_indicators(region, d["pop"], d["hexes"], d["flood"], d["aoi"])
    PCACHE.mkdir(parents=True, exist_ok=True)
    hx.to_parquet(f)
    return hx


def load_osm(region, offline=False, refresh=False):
    region_wgs = gpd.GeoSeries([region], crs=basemap.METRIC_CRS).to_crs(basemap.WEB_CRS).iloc[0]
    if offline:
        mf = OSM_CACHE / "manifest.json"
        manifest = json.loads(mf.read_text()) if mf.exists() else {}
        keys = {osm.cache_key(g, b) for g in osm.QUERIES for b in osm.tiles(region_wgs)}
        manifest = {k: v for k, v in manifest.items() if k in keys}
        # Tiles never downloaded are recorded as missing, so their area is reported, not shown as empty
        for g in osm.QUERIES:
            for b in osm.tiles(region_wgs):
                manifest.setdefault(osm.cache_key(g, b), {"group": g, "bbox": list(b), "status": "missing"})
    else:
        manifest = osm.fetch(region_wgs, OSM_CACHE, refresh=refresh)
    fac, fac_stats = osm.facilities(osm.read_cached(OSM_CACHE, manifest, "facilities"))
    inf, inf_stats = osm.infrastructure(osm.read_cached(OSM_CACHE, manifest, "infrastructure"))
    inside = lambda g: g[shapely.intersects(g.representative_point().values, region)].reset_index(drop=True)
    return inside(fac), inside(inf), manifest, {"facilities": fac_stats, "infrastructure": inf_stats}


def post_2021(tags):
    """True if OSM start_date says the asset may postdate the July 2021 event (year 2021 alone is ambiguous -> True)."""
    m = re.match(r"~?(\d{4})(?:-(\d{2}))?", str(tags.get("start_date", "")))
    if not m:
        return False
    y, mo = int(m.group(1)), int(m.group(2) or 0)
    return y > 2021 or (y == 2021 and (mo == 0 or mo >= 7))


def crosses_water(geoms, hydro):
    water = shapely.union_all(hydro.geometry.values)
    shapely.prepare(water)
    return shapely.intersects(shapely.buffer(geoms, WATER_BUFFER), water)


def score_assets(a, refs, kind):
    """Default-weight scores, bounded range, quality flags and weight sensitivity for one asset group."""
    X, status = sc.asset_PBF(a, refs)
    if kind == "people":
        a["dependency"] = pd.to_numeric(a["dependency"])
        a["overnight"] = pd.to_numeric(a["overnight"])
        imp = sc.facility_importance(a["dependency"], a["overnight"])
        a["assumed"] = a["dependency"].isna() | a["overnight"].isna()
    else:
        imp = a["importance"].to_numpy(float)
        a["assumed"] = a["assumed"].eq(True) if "assumed" in a else False
    a["I"] = imp
    a["M"] = sc.type_factor(imp)
    a["P"], a["B"], a["F"] = X.T
    a["f_status"] = status
    s = sc.score(X, sc.DEFAULT_WEIGHTS, a["M"].to_numpy())
    a["score"], a["lo"], a["hi"] = s["score"], s["lo"], s["hi"]
    a["post_2021"] = a["tags"].map(post_2021)
    a["flags"], a["quality"] = sc.quality(a, status)
    a["best_rank"], a["worst_rank"], a["top_share"] = sc.sensitivity(X, a["M"].to_numpy())
    return a


def prepare_all(args):
    d = basemap.prepare()
    region = d["aoi"].buffer(basemap.AOI_BUFFER).union_all()
    hx = load_hexes(d, region, args.recompute)
    fac, inf, manifest, dedup = load_osm(region, args.offline, args.refresh_osm)
    if fac.empty and inf.empty:
        raise SystemExit("No OSM data cached and Overpass not reachable: run without --offline when online.")
    hydro = basemap.load_hydro()
    br = inf["category"] == "bridge"
    inf["crosses_water"] = False
    inf.loc[br, "crosses_water"] = crosses_water(inf.loc[br].geometry.values, hydro)
    inf.loc[br & ~inf["crosses_water"], "importance"] *= NOT_WATER_FACTOR

    refs = {"pop": sc.reference(hx["n_pop"]), "bldg": sc.reference(hx["n_bldg"]),
            "flood_share": sc.reference(hx["flood_share"])}
    fac = score_assets(ind.asset_indicators(fac, hx, d["flood"], d["aoi"]), refs, "people")
    inf = score_assets(ind.asset_indicators(inf, hx, d["flood"], d["aoi"]), refs, "infra")
    X = sc.hex_PBF(hx, refs)
    hx["P"], hx["B"], hx["F"] = X.T
    return d, hx, fac, inf, refs, manifest, dedup


# --------------------------------------------------------------------------- export for the browser
def r3(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 3)


def locality(t):
    return t.get("addr:city") or t.get("addr:place") or t.get("addr:suburb") or t.get("is_in:city")


def asset_records(a, kind):
    pts = gpd.GeoSeries(a.representative_point(), crs=a.crs).to_crs(basemap.WEB_CRS)
    lines = None
    if kind == "infra":
        lin = a.geometry.where(a["category"].isin(["bridge", "tunnel"]))
        lines = gpd.GeoSeries(lin.simplify(5), crs=a.crs).to_crs(basemap.WEB_CRS)
    out = []
    for i, r in enumerate(a.itertuples()):
        t = r.tags
        rec = {"id": f"{r.osm_type}/{r.osm_id}", "cat": r.category, "label": r.label, "name": t.get("name"),
               "country": r.country, "place": locality(t), "lat": round(pts.iloc[i].y, 5), "lon": round(pts.iloc[i].x, 5),
               "P": r3(r.P), "B": r3(r.B), "F": r3(r.F), "M": round(r.M, 3), "I": round(r.I, 3),
               "pop": round(r.n_pop), "bldg": int(r.n_bldg), "share": r3(r.flood_share_mapped), "fs": r.f_status,
               "q": r.quality, "flags": r.flags, "top": r3(r.top_share),
               "rk": [int(r.best_rank), int(r.worst_rank)] if np.isfinite(r.best_rank) else None,
               "post": bool(r.post_2021), "start": t.get("start_date")}
        if kind == "people":
            rec.update(D=r.dependency if np.isfinite(r.dependency) else None, O=r.overnight if np.isfinite(r.overnight) else None,
                       cap=t.get("capacity") or t.get("beds") or t.get("capacity:persons"),
                       who=t.get("social_facility:for"), op=t.get("operator"))
        else:
            rec.update(carried=getattr(r, "carried", None) if isinstance(getattr(r, "carried", None), str) else None,
                       water=bool(r.crosses_water), n_ways=len(r.osm_ids) if isinstance(r.osm_ids, list) else 1,
                       volt=t.get("voltage"), op=t.get("operator"))
            g = lines.iloc[i]
            if g is not None and not g.is_empty:
                parts = shapely.get_parts(g)
                rec["line"] = [[[round(y, 5), round(x, 5)] for x, y in shapely.get_coordinates(p)] for p in parts]
        out.append({k: v for k, v in rec.items() if v is not None})
    return out


def provenance(manifest):
    ok = [m for m in manifest.values() if m.get("status") == "ok"]
    times = sorted(m["retrieved_at"] for m in ok)
    bases = sorted(m["osm_base"] for m in ok if m.get("osm_base"))
    gaps = [{"group": m["group"], "bbox": m["bbox"], "status": "outdated" if m.get("stale") else m["status"]}
            for m in manifest.values() if m.get("status") != "ok" or m.get("stale")]
    return {"tiles": len(manifest), "ok": len(ok), "gaps": gaps,
            "failed": sum(m.get("status") in ("failed", "missing") for m in manifest.values()),
            "stale": sum(bool(m.get("stale")) for m in manifest.values()),
            "retrieved": [times[0][:10], times[-1][:10]] if times else None,
            "osm_base": [bases[0][:10], bases[-1][:10]] if bases else None}


# --------------------------------------------------------------------------- records for flood_map.html
def write_assets(fac, inf, refs, manifest, dedup):
    data = {"people": asset_records(fac, "people"), "infra": asset_records(inf, "infra"), "refs": refs,
            "weights": sc.DEFAULT_WEIGHTS, "topN": sc.TOP_N, "factStatus": sc.F_STATUS, "prov": provenance(manifest),
            "dedup": dedup, "built": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    ASSET_CACHE.write_text(json.dumps(data, separators=(",", ":")))
    print(f"Saved {ASSET_CACHE}: {len(data['people']):,} facilities, {len(data['infra']):,} infrastructure assets")
    return data


def assets_for_map(refresh=False):
    """Asset records for map.py: the cache if present, else computed offline from the cached OSM tiles (None if none)."""
    if ASSET_CACHE.exists() and not refresh:
        return json.loads(ASSET_CACHE.read_text())
    try:
        d, hx, fac, inf, refs, manifest, dedup = prepare_all(argparse.Namespace(offline=True, refresh_osm=False, recompute=False))
    except SystemExit as e:
        print(f"  no asset context layers: {e}")
        return None
    return write_assets(fac, inf, refs, manifest, dedup)


def export_csv(fac, inf):
    cols = ["group", "rank", "score", "lo", "hi", "label", "name", "country", "place", "f_status", "quality", "flags",
            "P", "B", "F", "M", "n_pop", "n_bldg", "top_share", "best_rank", "worst_rank", "osm"]
    parts = []
    for g, a in [("vulnerable_facility", fac), ("critical_infrastructure", inf)]:
        a = a.sort_values(["f_status", "score"], key=lambda s: s.eq("unmapped") if s.name == "f_status" else -s).reset_index(drop=True)
        a["group"] = g
        a["rank"] = pd.Series(np.arange(1, len(a) + 1)).where(a["f_status"] != "unmapped")  # not ranked: insufficient evidence
        a["name"] = a["tags"].map(lambda t: t.get("name"))
        a["place"] = a["tags"].map(locality)
        a["osm"] = "https://www.openstreetmap.org/" + a["osm_type"] + "/" + a["osm_id"].astype(str)
        a["flags"] = a["flags"].map(";".join)
        parts.append(a[cols])
    out = pd.concat(parts).round(3)
    out.to_csv(OUT_CSV, index=False)
    print(f"Saved {OUT_CSV} (default weights {sc.DEFAULT_WEIGHTS}; OSM data © OpenStreetMap contributors, ODbL)")


def summary(hx, fac, inf, refs, manifest, dedup):
    """Numbers used in DATA_QUALITY_REPORT.md (printed and saved to cache/priority/summary.json)."""
    s = {"refs": refs, "provenance": provenance(manifest), "dedup": dedup,
         "hexes": {"n": len(hx), "F_unknown": int(hx["flood_share"].isna().sum()), "B_gap": int(hx["b_gap"].sum()),
                   "F_unknown_by_country": hx[hx["flood_share"].isna()].groupby("country").size().to_dict(),
                   "n_by_country": hx.groupby("country").size().to_dict()}}
    for name, a in [("people", fac), ("infra", inf)]:
        flags = pd.Series([f for fl in a["flags"] for f in fl]).value_counts().to_dict()
        s[name] = {"n": len(a), "by_category": a["category"].value_counts().to_dict(),
                   "by_country": a["country"].value_counts().to_dict(),
                   "f_status": a["f_status"].value_counts().to_dict(), "quality": a["quality"].value_counts().to_dict(),
                   "flags": flags, "named": int(a["tags"].map(lambda t: "name" in t).sum()),
                   "post_2021": int(a["post_2021"].sum()), "robust_top": int((a["top_share"] == 1).sum()),
                   "unstable_top": int(((a["top_share"] > 0) & (a["top_share"] < 0.5)).sum())}
    s["people"]["capacity_tagged"] = int(fac["tags"].map(lambda t: any(k in t for k in ("capacity", "beds", "capacity:persons"))).sum())
    s["infra"]["crosses_water"] = int(inf["crosses_water"].sum())
    (PCACHE / "summary.json").write_text(json.dumps(s, indent=1, default=str))
    print(json.dumps(s, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use cached OSM tiles only")
    ap.add_argument("--refresh-osm", action="store_true", help="re-download all OSM tiles")
    ap.add_argument("--recompute", action="store_true", help="recompute hexagon indicators")
    ap.add_argument("--summary", action="store_true", help="print data-quality numbers")
    args = ap.parse_args()
    d, hx, fac, inf, refs, manifest, dedup = prepare_all(args)
    if args.summary:
        summary(hx, fac, inf, refs, manifest, dedup)
    export_csv(fac, inf)
    write_assets(fac, inf, refs, manifest, dedup)
