"""
register.py - Evidence register (evidence/register.json): the team's research file on recovery since 2021.

Not shown on the map (presented orally and in the policy brief). The register is edited by hand. This module
validates it and adds, per locality, what OUR data says there
(municipality outline from the cached OSM boundaries, candidate shelters, estimated 2020 residents inside the observed
2021 extent). It never moves, shrinks or re-scores the 2021 footprint, and attaches no record to a map position: records
are linked to their municipality only.
"""
import json
import re
from pathlib import Path

import geopandas as gpd
import shapely

HERE = Path(__file__).resolve().parent
REGISTER = HERE / "register.json"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RECORD_FIELDS = ["id", "locality", "scope", "measure", "category", "status", "status_as_of", "description", "source",
                 "event_date", "completion_date", "checked", "establishes", "unverified"]
SOURCE_FIELDS = ["title", "publisher", "url", "published"]
ACTION_FIELDS = ["id", "locality", "kind", "finding", "basis", "action", "actor", "info_needed"]
DATA_KEYS = {"candidates", "documented_capacity", "exposure", "no_official_shelter_list", "not_mapped_note"}
OUTLINE_TOL = 25   # m, simplification of the municipality outline drawn on the map


def load(path=REGISTER):
    return json.loads(Path(path).read_text())


def _check_source(s, where):
    out = [f"{where}: source missing '{k}'" for k in SOURCE_FIELDS if k not in s]
    if not str(s.get("url", "")).startswith("https://"):
        out.append(f"{where}: source url must start with https://")
    if s.get("published") and not DATE.match(s["published"]):
        out.append(f"{where}: published must be YYYY-MM-DD or null")
    return out


def check(reg):
    """List of problems (empty = valid). Run on every build, so a bad edit stops map.py with a clear message."""
    out = []
    locs = {l["id"] for l in reg.get("localities", [])}
    ids = [r.get("id") for r in reg.get("records", [])] + [a.get("id") for a in reg.get("actions", [])]
    out += [f"duplicate id {i}" for i in {i for i in ids if ids.count(i) > 1}]
    for r in reg.get("records", []):
        w = r.get("id", "?")
        out += [f"{w}: missing '{k}'" for k in RECORD_FIELDS if k not in r]
        if r.get("locality") not in locs:
            out.append(f"{w}: unknown locality {r.get('locality')}")
        if r.get("status") not in reg["status_values"]:
            out.append(f"{w}: status must be one of {reg['status_values']}")
        if r.get("category") not in reg["category_values"]:
            out.append(f"{w}: category must be one of {reg['category_values']}")
        if not DATE.match(str(r.get("checked", ""))):
            out.append(f"{w}: checked must be YYYY-MM-DD")
        if r.get("status") == "completed" and not r.get("completion_date"):
            out.append(f"{w}: 'completed' needs a completion_date supported by the source")
        for s in [r.get("source", {})] + r.get("additional_sources", []):
            out += _check_source(s, w)
    recs = {r.get("id"): r.get("locality") for r in reg.get("records", [])}
    for a in reg.get("actions", []):
        w = a.get("id", "?")
        out += [f"{w}: missing '{k}'" for k in ACTION_FIELDS if k not in a]
        if a.get("locality") not in locs:
            out.append(f"{w}: unknown locality {a.get('locality')}")
        if a.get("kind") not in ("finding", "gap"):
            out.append(f"{w}: kind must be 'finding' or 'gap'")
        for b in a.get("basis", []):
            if "source" in b and recs.get(b["source"]) != a.get("locality"):
                out.append(f"{w}: basis source {b['source']} is not a record of locality {a.get('locality')}")
            if "data" in b and b["data"] not in DATA_KEYS:
                out.append(f"{w}: unknown data key {b['data']} (one of {sorted(DATA_KEYS)})")
            if not {"source", "data", "scenario"} & set(b):
                out.append(f"{w}: each basis item needs 'source', 'data' or 'scenario'")
    return out


def locality_facts(reg, admin, inv, origins, flood, aoi, web_crs="EPSG:4326"):
    """Per locality: outline (WGS84 GeoJSON, simplified) and our own figures inside the municipality boundary.
    `admin` = municipality polygons (EPSG:3035, shelters.admin_frame); a locality whose name is not found gets no
    map link (reported in 'problems')."""
    out, problems = {}, []
    pts = None if origins is None else gpd.GeoSeries(gpd.points_from_xy(origins["x"], origins["y"]), crs=admin.crs)
    aoi_u = aoi.union_all()
    for l in reg["localities"]:
        a = admin[admin["municipality"] == l["municipality"]] if admin is not None else []
        f = {"name": l["municipality"], "country": l["country"], "why": l.get("why_selected", ""), "outline": None}
        if len(a) != 1:
            problems.append(f"{l['id']}: {len(a)} OSM boundaries named {l['municipality']!r}: no map link")
            out[l["id"]] = f
            continue
        g = a.geometry.iloc[0]
        f["outline"] = json.loads(gpd.GeoSeries([g.simplify(OUTLINE_TOL)], crs=admin.crs).to_crs(web_crs).to_json())
        f["municipality_code"] = a["municipality_code"].iloc[0]
        f["ems_cover"] = round(shapely.intersection(aoi_u, g).area / g.area, 3)
        c = flood.clip(g)
        f["flood_ha"] = {k: round(float(v) / 1e4, 1) for k, v in c.area.groupby(c["kind"]).sum().items()}
        f["activations"] = sorted(c["activation"].unique().tolist()) if "activation" in c else []
        if pts is not None:
            w = pts.within(g).to_numpy()
            f["residents"] = round(float(origins.loc[w, "residents"].sum()), 1)
        if inv is not None:
            s = inv[inv["municipality"] == l["municipality"]]
            f["candidates"] = {k: int(v) for k, v in s["screen_category"].value_counts().items()}
            f["documented_capacity"] = int(s["shelter_capacity"].notna().sum())
            f["candidate_ids"] = s["candidate_id"].tolist()
        out[l["id"]] = f
    return out, problems

