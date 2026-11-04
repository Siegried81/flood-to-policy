"""Build a one-page 3D terrain view of the Vesdre valley, July 2021.

A storytelling scene, not an analysis map: the relief of the narrow Vesdre gorge
with the water Copernicus saw in July 2021 draped on it, so the "small steep
valley, warn — don't build a river dyke" point lands physically. Everything is
keyless: MapLibre GL draws a terrarium DEM (AWS open elevation tiles) with Esri
imagery as the texture, and the observed flood outline (EMSR518 AOI01, WGS84) is
a fill layer that MapLibre drapes on the terrain. No EFAS depth is extruded: its
"filled depth" includes the river channel, so a volume would make the big rivers
look worst and bury the message. Output: web/public/vesdre_3d.html (self-contained
but for the two CDN/tile hosts), linked from the README.

    python scripts/build_vesdre_3d.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOOD = ROOT / "web" / "public" / "interactive" / "EMSR518_AOI01" / "flood.geojson"
OUT = ROOT / "web" / "public" / "vesdre_3d.html"

MAPLIBRE = "4.7.1"  # pinned; terrain + hillshade are stable here

# A few towns along the Meuse and the Vesdre, west to east, for orientation.
TOWNS = [
    ("Liège", 5.5797, 50.6326),
    ("Chaudfontaine", 5.6333, 50.5833),
    ("Trooz", 5.6917, 50.5667),
    ("Pepinster", 5.8083, 50.5667),
    ("Verviers", 5.8622, 50.5897),
    ("Eupen", 6.0369, 50.6286),
]


def feature_collection(geojson: dict) -> dict:
    """The AOI file is a single Feature; MapLibre is happiest with a collection."""
    if geojson.get("type") == "FeatureCollection":
        return geojson
    return {"type": "FeatureCollection", "features": [geojson]}


def main() -> None:
    flood = feature_collection(json.loads(FLOOD.read_text(encoding="utf-8")))
    flood_json = json.dumps(flood, separators=(",", ":"))
    towns_json = json.dumps(
        {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
             "properties": {"name": name}} for name, lon, lat in TOWNS]},
        separators=(",", ":"))

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Vesdre valley in 3D — July 2021</title>
<link href="https://unpkg.com/maplibre-gl@{MAPLIBRE}/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://unpkg.com/maplibre-gl@{MAPLIBRE}/dist/maplibre-gl.js"></script>
<style>
  html, body {{ margin: 0; height: 100%; background: #0b0f14; }}
  #map {{ position: absolute; inset: 0; }}
  .card {{ position: absolute; top: 12px; left: 12px; max-width: 360px; z-index: 2;
    background: rgba(12,16,20,.82); color: #eef2f6; padding: 12px 14px; border-radius: 8px;
    font: 14px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  .card h1 {{ font-size: 1.05rem; margin: 0 0 .3rem; }}
  .card p {{ margin: .35rem 0; }}
  .card .note {{ font-size: .8rem; color: #aebbc7; }}
  .town {{ font: 600 12px system-ui, sans-serif; color: #fff; text-shadow: 0 0 3px #000, 0 0 3px #000;
    pointer-events: none; white-space: nowrap; }}
  .town::before {{ content: "● "; color: #ffd166; }}
  .maplibregl-ctrl-attrib {{ font-size: 10px; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="card">
  <h1>The Vesdre valley, July 2021 — in 3D</h1>
  <p>The relief of the valley, with the water Copernicus mapped in July 2021 draped on it.
  A small, steep river that rises in hours; the European flood map doesn't even model it.</p>
  <p class="note">Illustrative, not an analysis map. Terrain: AWS open DEM (Terrarium). Imagery © Esri.
  Observed flood © European Union, Copernicus EMS (EMSR518). No modelled depth is extruded.
  Drag to orbit · scroll to zoom.</p>
</div>
<script>
const FLOOD = {flood_json};
const TOWNS = {towns_json};

const map = new maplibregl.Map({{
  container: 'map',
  maxPitch: 82,
  center: [5.74, 50.565], zoom: 11.3, pitch: 73, bearing: -26,
  style: {{
    version: 8,
    glyphs: 'https://demotiles.maplibre.org/font/{{fontstack}}/{{range}}.pbf',
    sources: {{
      esri: {{ type: 'raster', tileSize: 256,
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'],
        attribution: 'Imagery © Esri, Maxar, Earthstar Geographics' }},
      dem: {{ type: 'raster-dem', tileSize: 256, maxzoom: 14, encoding: 'terrarium',
        tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{{z}}/{{x}}/{{y}}.png'],
        attribution: 'Elevation: AWS Terrain Tiles (SRTM, public domain)' }},
      flood: {{ type: 'geojson', data: FLOOD }}
    }},
    layers: [
      {{ id: 'esri', type: 'raster', source: 'esri' }},
      {{ id: 'hillshade', type: 'hillshade', source: 'dem',
        paint: {{ 'hillshade-exaggeration': 0.5 }} }},
      {{ id: 'flood-fill', type: 'fill', source: 'flood',
        paint: {{ 'fill-color': '#29a3ff', 'fill-opacity': 0.72 }} }},
      {{ id: 'flood-line', type: 'line', source: 'flood',
        paint: {{ 'line-color': '#eaf6ff', 'line-width': 1.8 }} }}
    ],
    sky: {{ 'sky-color': '#9ec6ff', 'horizon-color': '#dfeeff', 'fog-color': '#eef4fb', 'fog-ground-blend': 0.5 }}
  }}
}});

map.addControl(new maplibregl.NavigationControl({{ visualizePitch: true }}), 'top-right');

map.on('load', () => {{
  map.setTerrain({{ source: 'dem', exaggeration: 2.0 }});
  for (const f of TOWNS.features) {{
    const el = document.createElement('div');
    el.className = 'town';
    el.textContent = f.properties.name;
    new maplibregl.Marker({{ element: el, anchor: 'left' }})
      .setLngLat(f.geometry.coordinates).addTo(map);
  }}
}});
</script>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
