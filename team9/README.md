# July 2021 floods: exposure map (BE / DE / NL)

Team 9's tool (FARI hackathon 2026), vendored here as source. `map.py` builds
`flood_map.html`: one self-contained page with four presentation scenes (what happened,
who was exposed, where could they go, where to start). It needs internet access for the
basemap tiles, uses no API key and sends no data to any AI service.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python map.py --refresh   # read EMS / OBAT / GHS-POP / EFAS from Google Cloud Storage, cache in ./cache, write the HTML
.venv/bin/python map.py             # normal workflow: rebuild flood_map.html from the caches
.venv/bin/python map.py --stats     # distributions used to choose the class breaks
.venv/bin/python screenshot.py      # optional PNGs (needs `playwright install chromium`)
.venv/bin/python -m pytest          # team9/tests; also collected by the root `python -m pytest`
```

**Only the latest map is kept** (about 37 MB), at `web/public/team9/flood_map.html` in
Git LFS: run `git lfs pull` after cloning, and replace that file when you rebuild.
`cache/` and `shelter_candidates.geojson` are gitignored. The Streamlit tab says so when
the file is missing or still an LFS pointer. Its inputs (EMS, OBAT, GHS-POP, EFAS)
are several GB and are fetched by `--refresh`; they are not vendored. Upstream:
`github.com/YkSalma/fari-hackathon-2026` (branch `demo-scenarios`). Method of the asset
scores: [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md); data gaps:
[DATA_QUALITY_REPORT.md](DATA_QUALITY_REPORT.md); how this folder fits the repository:
[INTEGRATION.md](INTEGRATION.md).

## Layers

| Layer | Source | Shows |
|---|---|---|
| Flooded areas / flood traces | Copernicus EMS EMSR517/518/520 `observedEventA` | water on the image / already receded (German grading products) |
| Buildings | GHS-OBAT R2024A points | count per 400 m hexagon (EPSG:3035); residential share in the tooltip |
| Population | GHS-POP E2020 R2023A, 30 arc-seconds | residents per cell; zero cells transparent |
| Modelled hazard | CEMS-EFAS flood hazard maps, RP10 / 100 / 500 | modelled depth (m), 100-year by default; click for exact depth |
| Normal water | EMS `hydrographyA` / `hydrographyL` | pre-event rivers and water bodies, drawn above the flood layers |
| Candidate shelters | OpenStreetMap | schools, sports halls, community centres worth assessing (not confirmed shelters) |
| Context | OpenStreetMap | vulnerable facilities and critical infrastructure with 0-100 asset screening scores |

Flood colour is exposure, not water: EMS gives extent only. The blue shade counts either
OBAT buildings or estimated residents inside each polygon (switch in the legend).

## Method

1. EMS: all 27 `observedEvent` layers are dissolved into one maximum observed extent per
   activation (nothing counted twice); slivers under 500 m2 dropped; display geometry
   simplified at 10 m; counts use the unsimplified geometry.
2. OBAT is read AOI by AOI (plus 1 km) from the three country files and de-duplicated by
   building id; GHS-POP is one raster window over the AOIs.
3. Residents in a flood polygon: each population cell's residents are shared equally among
   the residential OBAT buildings in the cell (by area where none), then summed inside the
   polygon. Estimate, 2020 residents, a lower bound in towns.
4. EFAS: one window per return period, reprojected (nearest neighbour) to Web Mercator and
   embedded as a PNG whose palette also stores the depth in 0.1 m steps.
5. Observed vs modelled: EMS polygons rasterised on the EFAS grid, cells weighted by true
   area. Share of observed flood area inside the 100-year zone is roughly 62 % overall (BE
   64 %, DE 58 %, NL 94 %); about 35 % lies outside both zones, mixing flooding beyond the
   modelled hazard with rivers EFAS does not model (catchment under 500 km2).
6. Everything is computed in EPSG:3035 and reprojected to EPSG:4326 for display.

EMS figures are per activation, named after the requesting country: EMSR518 (Belgium) also
mapped the Dutch Meuse, so counts by location differ.

## Limits

- EMS is a snapshot, not the peak; outside the mapped areas "not mapped" is not "not flooded".
- Satellite delineation misses water between buildings: town counts are a lower bound, and
  Belgium (no flood traces) must not be compared with Germany.
- OBAT gives centroids, not footprints; GHS-POP counts residents only and is partly derived
  from the same built-up data as OBAT, so the two are not independent evidence.
- EMS flooded areas exclude normal water, whereas EFAS depths include the river channel.
- EFAS is a model: an empty cell means "not modelled", not "safe"; rivers under 500 km2 of
  catchment are absent, and the 2021 flood exceeded the 500-year map in places (the Ahr).
- Keyless Esri Canvas basemaps replace CARTO, which now demands a key.

## Candidate shelters (stage 1)

`shelters.py` builds an inventory of schools, sports halls and community centres from
OpenStreetMap inside the EMS areas plus 1 km (not whole municipalities): selection rules
(outdoor sites, buildings under 100 m2 and lifecycle-tagged elements excluded),
de-duplication, municipality and country from admin boundaries, and a screening in
EPSG:3035 against the unsimplified flood extent (inside, within 25 m of the edge or
unresolved, outside but in an EMS area, outside EMS coverage). Exports
`shelter_candidates.csv` (versioned) and `.geojson` (not). Being listed means "worth
assessing": accessibility, capacity, heating, operator consent and availability are not
checked, and no capacity is inferred.

```bash
.venv/bin/python shelters.py            # download missing OSM tiles (Overpass, about 1 h first time), build, export
.venv/bin/python shelters.py --offline  # rebuild from the cache only; never contacts Overpass
```

## Planning scenario (stage 2 and 3)

In the shelter panel a user enters assumed capacities, availability and a maximum
straight-line distance (1-25 km, default 5 km, an assumption). A maximum flow
(`planning/alloc.js`, runs in the browser; verified against a linear program in
`tests/test_planning.py`) assigns exposed residents to facility places and reports why
residents stay unassigned (capacity used, unknown capacity, unavailable, too far). Demand
is the estimate above spread over 400 m hexagons (`planning/demand.py`, total conserved
exactly). It states no one is safe, adds no recommendation and infers no capacity: with
nothing entered, nothing is assigned. A scenario can be saved, restored and compared
against a baseline (A/B), and results exported as CSV.

## Scenes and priority (stage 4)

- Scene 2 ranks the fixed 400 m hexagons by estimated exposed residents.
- Scene 4 shows the scenario-based planning priority per hexagon,
  `S = wE * E + wG * G` with `E = 100 * min(1, ln(1+P) / ln(1+P99))` (P99 fixed at build
  time) and `G = 100 * unassigned / P`; weights default to 50/50, an illustrative
  assumption. It is not a probability or a validated vulnerability index and does not
  support comparison between countries. Missing information is listed beside the score,
  never folded into it.
- The asset screening scores (facilities, infrastructure) stay separate and are never
  combined or ranked with the area priority.

## Recovery evidence register

`evidence/register.json` is a small dated register of what changed since 2021 in three
localities, with team-proposed actions, validated on every build by `evidence/register.py`
(`python -m pytest tests/test_evidence.py`). It feeds the brief, not the map. Sourced facts,
our data, scenario assumptions and team proposals are kept apart in the file.

## Sources

Copernicus Emergency Management Service (© European Union, 2021), EMSR517, EMSR518,
EMSR520; CEMS EFAS flood hazard maps; European Commission JRC, GHS-OBAT R2024A and
GHS-POP R2023A; basemaps Esri Canvas and © OpenStreetMap contributors (ODbL).
