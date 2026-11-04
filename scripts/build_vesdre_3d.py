"""Build a one-page 3D terrain view of the Meuse at Liège, July 2021.

A storytelling scene, not an analysis map: the Meuse valley through Liège and
north toward the Dutch border, with the water Copernicus saw in July 2021 draped
on it — the stretch where the flood spread widest. (Upstream the steep Vesdre
barely shows: EMS under-maps urban flooding, the water hiding between buildings.)
Everything is keyless: MapLibre GL draws a terrarium DEM (AWS open elevation tiles) with Esri
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

# Towns along the Meuse, south to north, for orientation.
TOWNS = [
    ("Seraing", 5.5011, 50.5869),
    ("Liège", 5.5797, 50.6326),
    ("Herstal", 5.6333, 50.6639),
    ("Visé", 5.6986, 50.7378),
    ("Maastricht", 5.6909, 50.8514),
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
<title>The Meuse at Liège in 3D — July 2021</title>
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
  .card .legend {{ display: flex; align-items: center; gap: 8px; margin: .55rem 0; font-size: .85rem; }}
  .card .legend .sw {{ width: 22px; height: 12px; border-radius: 2px; flex: none;
    background: #17b2ff; box-shadow: inset 0 0 0 1.5px #f2fbff, 0 0 7px #8fe3ff; }}
  .card .note {{ font-size: .8rem; color: #aebbc7; }}
  .town {{ font: 600 13px system-ui, sans-serif; color: #fff; white-space: nowrap; pointer-events: none;
    text-shadow: 0 0 3px #000, 0 0 5px #000; background: rgba(12,16,20,.45); padding: 1px 7px; border-radius: 11px; }}
  .town::before {{ content: "● "; color: #ffd166; }}
  .maplibregl-ctrl-attrib {{ font-size: 10px; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="card">
  <h1>The Meuse at Liège, July 2021 — in 3D</h1>
  <p>The Meuse through Liège and north toward the Dutch border, with the water Copernicus
  mapped in July 2021 draped on the valley — the stretch where the flood spread widest.
  Upstream, the steep Vesdre that tore through Verviers barely shows: the satellites miss
  urban flooding, the water hiding between buildings.</p>
  <div class="legend"><span class="sw"></span> Observed flood — Copernicus EMS, July 2021</div>
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
  center: [5.63, 50.675], zoom: 11.4, pitch: 50, bearing: -16,
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
      {{ id: 'esri', type: 'raster', source: 'esri',
        paint: {{ 'raster-saturation': -0.4, 'raster-contrast': 0.08, 'raster-brightness-max': 0.92 }} }},
      {{ id: 'hillshade', type: 'hillshade', source: 'dem',
        paint: {{ 'hillshade-exaggeration': 0.5 }} }},
      {{ id: 'flood-fill', type: 'fill', source: 'flood',
        paint: {{ 'fill-color': '#17b2ff', 'fill-opacity': 0.82 }} }},
      {{ id: 'flood-glow', type: 'line', source: 'flood',
        paint: {{ 'line-color': '#8fe3ff', 'line-width': 7, 'line-blur': 5, 'line-opacity': 0.55 }} }},
      {{ id: 'flood-line', type: 'line', source: 'flood',
        paint: {{ 'line-color': '#f2fbff', 'line-width': 1.8, 'line-opacity': 0.95 }} }}
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
