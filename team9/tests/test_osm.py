"""OSM parsing, classification and de-duplication on small hand-made Overpass responses (no network)."""
import json

import pytest
import shapely

from priority import osm


def node(i, lon, lat, **tags):
    return {"type": "node", "id": i, "lon": lon, "lat": lat, "tags": tags}


def way(i, coords, **tags):
    return {"type": "way", "id": i, "geometry": [{"lon": x, "lat": y} for x, y in coords], "tags": tags}


SQUARE = [(7.000, 50.500), (7.002, 50.500), (7.002, 50.502), (7.000, 50.502), (7.000, 50.500)]


# --------------------------------------------------------------------------- classification
@pytest.mark.parametrize("tags, cat", [
    ({"amenity": "hospital"}, "hospital"),
    ({"healthcare": "hospital"}, "hospital"),
    ({"amenity": "social_facility", "social_facility": "nursing_home"}, "nursing_home"),
    ({"amenity": "nursing_home"}, "nursing_home"),
    ({"amenity": "kindergarten"}, "kindergarten"),
    ({"amenity": "school"}, "school"),
    ({"healthcare": "centre"}, "clinic"),
    ({"amenity": "social_facility"}, "social_other"),
    ({"amenity": "social_facility", "social_facility": "food_bank"}, None),
    ({"amenity": "doctors"}, None),
])
def test_classify_facility(tags, cat):
    r = osm.classify_facility(tags)
    assert (r and r["category"]) == cat


def test_facility_dependency_from_tags():
    r = osm.classify_facility({"social_facility": "group_home", "social_facility:for": "disabled"})
    assert r["dependency"] == 1.0 and r["overnight"] == 1
    assert osm.classify_facility({"amenity": "social_facility"})["dependency"] is None   # unknown, not invented


@pytest.mark.parametrize("tags, cat, imp", [
    ({"highway": "motorway", "bridge": "yes"}, "bridge", 1.0),
    ({"highway": "tertiary", "bridge": "viaduct"}, "bridge", 0.55),
    ({"railway": "rail", "bridge": "yes"}, "bridge", 1.0),
    ({"highway": "primary_link", "tunnel": "yes"}, "tunnel", 0.85),
    ({"power": "substation", "voltage": "110000;20000"}, "substation", 1.0),
    ({"power": "substation", "substation": "distribution"}, "substation", 0.7),
    ({"amenity": "fire_station"}, "fire_station", 1.0),
    ({"man_made": "wastewater_plant"}, "wastewater_plant", 0.8),
])
def test_classify_infra(tags, cat, imp):
    r = osm.classify_infra(tags)
    assert r["category"] == cat and r["importance"] == imp


@pytest.mark.parametrize("tags", [
    {"highway": "primary"},                                   # ordinary road segment: not critical by default
    {"highway": "residential", "bridge": "yes"},              # minor road bridges excluded
    {"highway": "primary", "bridge": "no"},
    {"highway": "primary", "tunnel": "building_passage"},
    {"power": "substation", "substation": "minor_distribution"},
    {"building": "yes"},                                      # a bridge is never an ordinary building and vice versa
])
def test_infra_excluded(tags):
    assert osm.classify_infra(tags) is None


# --------------------------------------------------------------------------- geometry
def test_element_geometry_types():
    assert osm.element_geometry(node(1, 7, 50)).geom_type == "Point"
    assert osm.element_geometry(way(2, SQUARE, amenity="school")).geom_type == "Polygon"
    assert osm.element_geometry(way(3, SQUARE[:3], highway="primary")).geom_type == "LineString"
    assert osm.element_geometry(way(4, SQUARE, highway="primary", bridge="yes")).geom_type == "LineString"  # closed road stays a line


def test_relation_multipolygon():
    rel = {"type": "relation", "id": 5, "tags": {"amenity": "hospital", "type": "multipolygon"},
           "members": [{"type": "way", "ref": 1, "role": "outer", "geometry": [{"lon": x, "lat": y} for x, y in SQUARE[:3]]},
                       {"type": "way", "ref": 2, "role": "outer", "geometry": [{"lon": x, "lat": y} for x, y in SQUARE[2:]]}]}
    g = osm.element_geometry(rel)
    assert g.geom_type == "Polygon" and g.is_valid and g.area > 0


def test_output_crs_is_metric():
    df = osm.to_frame([node(1, 7.001, 50.501, amenity="school")], osm.classify_facility)
    assert df.crs.to_epsg() == 3035


# --------------------------------------------------------------------------- de-duplication
def test_node_inside_polygon_same_category_dropped():
    els = [way(10, SQUARE, amenity="hospital"), node(11, 7.001, 50.501, amenity="hospital", name="St. Marien"),
           node(12, 7.001, 50.5011, amenity="school", name="Grundschule")]          # other category: kept
    df, stats = osm.facilities(els)
    assert stats == {"raw": 3, "after_dedup": 2}
    hosp = df[df["category"] == "hospital"].iloc[0]
    assert hosp["osm_type"] == "way" and hosp["tags"]["name"] == "St. Marien"       # name carried over


def test_bridge_carriageways_merged():
    # two parallel carriageways ~7 m apart + one separate bridge ~1.4 km away
    els = [way(1, [(7.0, 50.5), (7.001, 50.5)], highway="motorway", bridge="yes", ref="A 61"),
           way(2, [(7.0, 50.50006), (7.001, 50.50006)], highway="motorway", bridge="yes", ref="A 61"),
           way(3, [(7.02, 50.5), (7.021, 50.5)], highway="tertiary", bridge="yes")]
    df, stats = osm.infrastructure(els)
    assert stats["raw"] == 3 and stats["after_dedup"] == 2
    a61 = df[df["importance"] == 1.0].iloc[0]
    assert len(a61["osm_ids"]) == 2 and a61["tags"]["name"] == "A 61"


def test_bridge_outline_groups_ways_and_is_not_an_asset():
    outline = way(9, [(6.9999, 50.4999), (7.0011, 50.4999), (7.0011, 50.5004), (6.9999, 50.5004), (6.9999, 50.4999)],
                  man_made="bridge")
    els = [outline, way(1, [(7.0, 50.5), (7.001, 50.5)], highway="primary", bridge="yes"),
           way(2, [(7.0, 50.5003), (7.001, 50.5003)], railway="rail", bridge="yes")]   # 33 m apart, same structure
    df, _ = osm.infrastructure(els)
    assert len(df) == 1 and df.iloc[0]["importance"] == 1.0 and "bridge_outline" not in set(df["category"])


def test_duplicates_across_tiles(tmp_path):
    el = node(1, 7, 50, amenity="school")
    manifest = {}
    for k in ("facilities_a", "facilities_b"):
        (tmp_path / f"{k}.json").write_text(json.dumps({"elements": [el]}))
        manifest[k] = {"group": "facilities"}
    assert len(osm.read_cached(tmp_path, manifest, "facilities")) == 1


def test_tiles_cover_region():
    region = shapely.box(4.97, 49.54, 7.73, 51.48)
    t = osm.tiles(region)
    cover = shapely.union_all([shapely.box(w, s, e, n) for s, w, n, e in t])
    assert cover.contains(region.buffer(-1e-9))
    assert all(n - s <= osm.TILE_DEG + 1e-9 and e - w <= osm.TILE_DEG + 1e-9 for s, w, n, e in t)
