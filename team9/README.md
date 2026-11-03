# July 2021 floods: exposure map (BE / DE / NL)

`flood_map.html` is the **only map to open**: one self-contained page with four presentation scenes (see
[Presentation scenes](#presentation-scenes-stage-4-one-map)). It needs internet access for the basemap tiles.
`map.py` rebuilds it from the caches; the former second map (`priority_map.html`) is retired and its useful content
(vulnerable facilities, critical infrastructure, asset scores) is inside `flood_map.html` as optional context.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python map.py --refresh   # read data from GCS (a few minutes), cache in ./cache, write the HTML
.venv/bin/python map.py             # normal workflow: rebuild flood_map.html from the caches
.venv/bin/python map.py --stats     # print value distributions used to choose the class breaks
.venv/bin/python screenshot.py      # optional: PNG screenshots (needs `playwright install chromium`)
```

No API key is used and no data is sent to any AI service.

## Layers

| Layer | Source | What it shows | Colours |
|---|---|---|---|
| Flooded areas (water on image) | Copernicus EMS EMSR517/518/520, `observedEventA`, notation "Flooded area" | Water visible on the satellite image | Blues, solid outline |
| Flood traces (water receded) | Same, notation "Flood trace" (DE grading products) | Visibly flooded earlier but already dry on the image (e.g. Ahr valley, Erftstadt) | Same blues, dashed outline, lighter fill |
| Buildings | GHS-OBAT R2024A points | Building count per 400 m hexagon (EPSG:3035); the tooltip gives the residential share (`use = 1`) | Greens, 7 classes: 1–4, 5–19, 20–49, 50–99, 100–199, 200–399, ≥ 400 |
| Population | GHS-POP E2020 R2023A, 30″ | Residents per cell (about 0.55 km²); zero cells are transparent | Magma (light yellow → purple), 7 classes: 1–9, 10–49, 50–199, 200–499, 500–999, 1,000–2,499, ≥ 2,500 |
| Modelled hazard (EFAS) | CEMS-EFAS flood hazard maps, `Europe_RP{10,100,500}_filled_depth.tif` | Modelled river flood water depth (m) for the 10-, 100- and 500-year flood (10 %, 1 %, 0.2 % chance per year). Radio buttons, 100-year by default. **Click** the map to read the depth (0.1 m precision) | Purples, 6 classes, the same for all return periods: 0.1–0.5, 0.5–1, 1–2, 2–4, 4–8, ≥ 8 m |
| Normal water (reference) | EMS `hydrographyA` (lake, reservoir, river, stream) and `hydrographyL` (river, stream) | Pre-event rivers and water bodies, drawn **above** the flood layers. Shown from zoom 11 (town scale); in the overview the 29 k streams would swamp the floods. Not interactive, so tooltips and clicks reach the layers below | Dark navy: fill 0.8, lines 1.2 px |
| EMS mapped areas | EMS `areaOfInterestA` | The areas EMS was asked to map (dashed grey) | Outline only |

**Flood colour = exposure, not water.** EMS gives extent only, with no depth. The blue shade shows either the
**OBAT buildings** inside each flood polygon (classes 0, 1–9, 10–49, 50–199, 200–999, ≥ 1,000) or the
**estimated residents** inside it (0, 1–24, 25–99, 100–499, 500–1,999, ≥ 2,000). Switch between the two in the legend.

**Observed vs modelled:** EFAS is drawn underneath every vector layer. While an EFAS layer is on, the EMS polygons
switch to a light fill and keep their bold dark outline, so both stay readable. The legend labels them
"Observed (Copernicus EMS, July 2021)" and "Modelled (EFAS)".

**Normal water vs flooding:** the flood blue scale stops at mid-blue, so it never reaches the navy used for normal
water. The overflow therefore reads as lighter blue around dark river and lake shapes.

**Why these colours:** each layer uses a different hue family (warm for people, green for buildings, blue for observed water, purple for modelled water),
so all three stay distinct when overlaid. All are sequential, perceptually ordered and colourblind-safe. The class
breaks are rounded numbers chosen from the observed distributions (roughly quantile-based) and are easy to read aloud.

## Method

1. **EMS:** all 27 observedEvent layers are used (delineation first image + monitoring, plus grading). For each
   activation, they are dissolved into one maximum observed extent, so no area or building is counted twice. Flood
   traces that overlap a flooded area are removed from the traces. Slivers under 500 m² are dropped, and polygons
   are simplified at 10 m for display.
2. **OBAT:** read directly from GCS, AOI by AOI (each AOI plus a 1 km buffer), from all three country files, because
   AOIs cross borders. Overlapping AOIs are de-duplicated by building `id`. About 5.0 M buildings are read, not the
   62 M in the full files.
3. **GHS-POP:** a single raster window over the AOIs. Cells with zero residents are not drawn.
4. **Residents in flood polygons (estimate):** each population cell's residents are shared equally among the
   residential OBAT buildings in that cell, then summed for the buildings inside each flood polygon. Cells with
   residents but no residential building are shared by area instead (this concerns ≈ 110 people).
5. **EFAS:** a single raster window per return period over the same region (AOIs plus 1 km); cells outside it are
   set to empty. Each map is reprojected (nearest neighbour) to Web Mercator at about 57 m ground resolution and
   embedded as a transparent PNG. The palette index stores the depth in 0.1 m steps, hidden in the colours' lowest
   bits (invisible), so a click can read the exact depth back. This was checked against the raster at 0.3, 1.5 and
   5.0 m.
6. **Observed vs modelled comparison:** the EMS polygons (flooded areas + traces) are rasterised on the EFAS grid
   (3″), and each cell is weighted by its true area (cos latitude). The result is the share of observed flood area
   inside the 100-year zone, inside the 500-year zone only, or outside both.
7. **Normal water:** reference polygons from all products are merged (union), ponds under 0.5 ha are dropped, and
   duplicate river and stream lines (repeated between products) are removed. Everything is simplified at 20 m and
   packed into two features (about 2.6 MB).
8. All areas, counts and hexagons are computed in EPSG:3035 and reprojected to EPSG:4326 for display.

**Headline (inside the mapped flood extent, flooded areas + traces):** 13,956 buildings and about 29,100 estimated
residents. Of these, Germany accounts for 13,501 buildings (about 28,500 residents), Belgium 239 (about 390) and the
Netherlands 216 (about 210).

> **Correction (stage 2 audit):** these per-country figures are per **EMS activation**, named after the requesting
> country. EMSR518 (Belgium) also mapped the Dutch Meuse: 785 ha of its flood area lie in the Netherlands, and about 70
> of its ≈ 390 estimated residents live there. By location (country of the OBAT buildings in each 400 m hexagon), the
> estimated residents are ≈ 310 in Belgium, ≈ 28,510 in Germany and ≈ 280 in the Netherlands (≈ 27 not attributed).
> The map's table is now labelled by activation and shows this split; building counts by location were not recomputed.
> EMSR517 also covers 15 ha in Luxembourg (≈ 2 residents).

**Observed vs modelled (share of observed flood area):**

| | Inside 100-year zone | 500-year zone only | Outside both |
|---|---|---|---|
| Belgium | 64 % | 0 % | 35 % |
| Germany | 58 % | 3 % | 40 % |
| Netherlands | 94 % | 1 % | 4 % |
| **Total** | **62 %** | **2 %** | **35 %** |

For flood traces alone (water already receded on the image, mostly the hardest-hit German valleys), 50 % of the area
lies outside both zones. "Outside" mixes two things: flooding that went beyond the modelled hazard, and rivers EFAS does
not model (catchment < 500 km²). The table cannot separate the two.

## Limits

- **EMS is a snapshot** taken when the satellite passed, not at the flood peak. Only the requested AOIs were mapped,
  so outside them **"not mapped" ≠ "not flooded"**.
- **Satellite delineation misses water between buildings**, so building and resident counts in towns are a
  **lower bound**. Belgium's products contain no flood traces, so towns such as Pepinster and Verviers are largely
  missing. The Belgian figures should not be compared with Germany's.
- **Dates:** the vector packages only carry the map production date (shown in tooltips). Image acquisition times
  are on the EMSR517/518/520 activation pages.
- **OBAT** gives building centroids, not footprints. "Residential" can include mixed use. Belgium is undercounted.
- **GHS-POP** counts residents only, not workers or visitors. It is a modelled estimate on a grid of about 1 km and
  is partly derived from the same built-up data as OBAT, so the two layers are not independent evidence.
- **EMS flooded areas exclude normal water.** This was checked per product against the EMS reference water layer:
  flood polygons cover 35.6 ha of 38,751 ha of permanent water (**0.09 %**), and 2–57 % of water polygons share an
  edge with a flood polygon. The flood polygons therefore show the overflow only. EFAS depths, by contrast, include
  the river channel. Excluding the channel does not inflate the "outside the modelled zone" share, because the
  channel area is simply absent from the EMS polygons. "Land subject to inundation" (`BH090`) is not treated as
  normal water.
- **EFAS is a model, not an observation.** Rivers with an upstream catchment under 500 km² are not modelled, so an
  empty cell means **"not modelled", not "safe"**. The 500-year map is the ceiling and is built on 1990–2016 data;
  the 2021 flood exceeded it in places (e.g. the Ahr). The "filled depth" includes the river channel, which is why
  large rivers (Rhine, Moselle, Meuse) fall into the ≥ 8 m class. Depth units are not stored in the files: we use
  metres as documented by EFAS/JRC (please check against Annex 2).
- Buildings, population and EFAS are shown only within the EMS mapped areas (plus 1 km).

## Deviations from the brief

- **Basemaps:** CARTO Positron and Dark Matter now return an "API key required" watermark on every request, so the
  map uses the keyless **Esri Light Gray / Dark Gray Canvas** instead, plus OpenStreetMap. Place-name labels are
  drawn above the data layers.
- **EFAS depth classes** add a 4–8 m / ≥ 8 m split to the suggested breaks, because the depth includes the river
  channels and 31–37 % of wet cells are deeper than 4 m.
- **Default view (shelter review):** observed flooding + candidate shelters, EFAS **off** (one click on 100-year turns it
  on). Buildings and population start off to avoid clutter. The exposure panel starts collapsed to a one-line summary.
- **Flood traces** are included as their own layer. Without them, the hardest-hit towns (Ahr, Erftstadt) would
  appear almost dry: 1,479 buildings in total instead of 13,956.

## EMS layers available vs used

| Layer | Geometry | Used |
|---|---|---|
| `observedEventA` (flooded area, flood trace) | Polygon | Yes: flooded areas, flood traces |
| `areaOfInterestA` | Polygon | Yes: mapped-area outline |
| `hydrographyA`, `hydrographyL` | Polygon, line | Yes: normal water (reference) |
| `builtUpP` (damage-graded buildings, DE grading products) | Point | No (proposed) |
| `transportationL` / `A` / `P` (roads, rail, bridges; damage grade in grading products) | Line, polygon, point | No (proposed) |
| `facilitiesA` / `L` / `P` (civil works, industry, waterworks, power lines) | Polygon, line, point | No |
| `builtUpA` (built-up blocks, reference) | Polygon | No (OBAT is used for buildings) |
| `naturalLandUseA`, `physiographyL`, `imageFootprintA` | Polygon, line | No |

## Sources

Copernicus Emergency Management Service (© European Union, 2021), activations EMSR517, EMSR518 and EMSR520;
CEMS European Flood Awareness System (EFAS) flood hazard maps (10-, 100- and 500-year return periods).
European Commission, JRC: GHS-OBAT R2024A, GHS-POP R2023A (Global Human Settlement Layer).
Basemaps: Esri Canvas (Esri, HERE, Garmin), © OpenStreetMap contributors.

---

# Asset screening scores (formerly `priority_map.html`)

Vulnerable facilities (hospitals, care homes, schools, …) and critical infrastructure (bridges, tunnels, substations,
water, emergency services) from OpenStreetMap, each with a 0–100 **asset** screening score built from population,
buildings and the flooding observed in July 2021. Since stage 4 they are optional context layers of `flood_map.html`
(scenes 2 and 4) with their own ranking list and weight sliders; the separate page is no longer built. The former P/B/F
**area** shading is not shown: the area view is now the scenario-based planning priority (scene 4), and the two kinds
of score are never combined, ranked together or compared numerically.

```bash
.venv/bin/python priority_map.py --offline # cached OSM tiles only: writes cache/priority/assets.json + priority_ranking.csv
.venv/bin/python priority_map.py           # downloads missing OSM tiles first (Overpass, ~1 h the first time)
.venv/bin/python priority_map.py --summary # also print the numbers used in DATA_QUALITY_REPORT.md
```

`map.py` reads `cache/priority/assets.json`; if it is missing, `map.py` computes it once from the cached OSM tiles.
Code: `priority/osm.py` (OSM acquisition and cleaning), `priority/indicators.py` (indicators), `priority/scoring.py`
(formulas, missing data, sensitivity), `priority/assets.js|css` (browser layers, ported from the retired page).
Method: [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md). Gaps: [DATA_QUALITY_REPORT.md](DATA_QUALITY_REPORT.md).
Facilities and infrastructure © OpenStreetMap contributors (ODbL).

---

# Candidate shelters (stage 1: inventory)

`flood_map.html` has a new layer, **Candidate shelters (unverified)**. It shows schools, sports halls and community
centres from OpenStreetMap that *could* be assessed as emergency accommodation. They are **not** confirmed shelters.

**Using the map:** markers are grouped when zoomed out; the number on a grey circle is the number of candidate facilities
in the group, and a red **!n** badge counts those inside the observed flood extent. Groups split as you zoom in (single
markers from zoom 15). The left panel filters by facility type and by 2021 flood screening, with quick buttons for
*All candidates*, *Inside flood extent* and *Inside + unresolved*; each row shows *shown / full inventory*. Colour and
shape identify the facility type only (school: teal square, sports hall: brown circle, community centre: slate
diamond); a red ring with **!** marks a candidate inside the observed extent, a dashed ring with **?** an unresolved one.
The same inventory is exported for team review and the later capacity stage: `shelter_candidates.csv` and
`shelter_candidates.geojson` (WGS84 points, one row per candidate).

```bash
.venv/bin/python map.py                 # once: EMS / OBAT caches (if not built yet)
.venv/bin/python shelters.py            # download missing OSM tiles (Overpass, ~1 h the first time), build, check, export
.venv/bin/python shelters.py --offline  # rebuild from the cache only (~10 s), never contacts Overpass
.venv/bin/python map.py                 # rebuild flood_map.html; reads cache/shelters only (no network for this layer)
.venv/bin/python -m pytest tests/test_shelters.py
```

If the inventory cache is missing, `map.py` still builds and says in the legend that the layer is unavailable.
If a tile download fails, the previous cached copy is kept and flagged as stale (the retrieval date is in every
record and popup); with no cached copy, the tile is reported as a gap and no facility is invented for it.

## Analysis area

The inventory uses the **same area as the rest of the map**: the Copernicus EMS areas of interest of EMSR517 (DE),
EMSR518 (BE) and EMSR520 (NL) plus 1 km (about 10,960 km²). A facility is in the inventory if its reference point
(the OSM node, or a point inside the OSM outline) lies in that area. It does **not** cover whole municipalities,
provinces or the three countries, so the counts are not regional totals. See *Discrepancies* below.

## Selection rules

| Rule | What it does |
|---|---|
| Types | `amenity=school` → School. `leisure=sports_hall`, `building=sports_hall` / `sports_centre` → Sports hall. `amenity=community_centre` → Community centre |
| R1 | Reference point outside the analysis area → excluded |
| R3 | `leisure=sports_centre` kept only if it is a building (`building=*`) or tagged `indoor=yes`; outdoor sport sites are excluded (halls inside them are captured by their own building tag) |
| R4 | Building outlines smaller than 100 m² (huts, kiosks) → excluded. School grounds are sites, not buildings, so the rule does not apply to them |
| R5 | Lifecycle tags (`disused`, `abandoned`, `construction`, `disused:*`, `was:*` …) → excluded |
| R6 | No usable geometry → excluded. Closed outlines are treated as areas |
| Not selected | Kindergartens, universities, homeless shelters (`social_facility=shelter`), churches, sports pitches, stadiums |

Being selected means only "worth assessing". The rules do not check accessibility, sanitation, heating, step-free
access, structural state, the operator's consent or availability during school terms.

**De-duplication**: (1) the same OSM element read from two tiles or two sources; (1b) same-type outlines with the same
shape (intersection over union ≥ 0.95, e.g. a school multipolygon and its outer way; the way is kept); (2) a node or outline inside a larger
outline of the same type (e.g. a school node inside the school grounds), kept as the larger outline; (3) same type and
same name within 50 m (a node next to its building), kept as the outline. Dropped ids are listed in `merged_ids`. A
sports hall inside school grounds is kept as a separate candidate.

## Fields

| Group | Fields |
|---|---|
| Identity | `candidate_id` (`osm:node/…`, `osm:way/…`, stable as long as the OSM element exists), `name`, `facility_type`, `facility_subtype` (OSM `school` / `isced:level`, `sport` or `community_centre` value), `lon`, `lat`, `osm_geometry` (point / outline), `footprint_m2` (outline area: grounds for most schools, building for halls) |
| Place | `municipality`, `municipality_code`, `municipality_level`, `country`, `admin_note`, `country_check`, `in_challenge_countries` |
| Source evidence | `source`, `source_url` (OSM page), `source_endpoint`, `osm_data_timestamp` (OSM database state), `retrieved_at`, `cache_stale`, `osm_check_date`, `osm_start_date`, `osm_operator`, `osm_building_levels`, `osm_capacity_tag`, `merged_ids` |
| Verification | `existence_status` = `mapped_in_osm_not_field_verified`, `designation_status` = `not_verified`, `verification_note` |
| Capacity | `shelter_capacity` and `capacity_source`: empty for every candidate. `osm_capacity_tag` is the raw OSM `capacity` value where mapped; its meaning varies (seats, pupils), so it is **not** shelter capacity |
| Spatial screening | `screen_category`, `screen_reason`, `flood_kind` (flooded / trace), `flood_edge_dist_m` (negative = inside), `ems_activation`, `aoi_edge_dist_m` (negative = inside) |

**Municipality and country** come from OSM administrative boundaries (admin_level 8, which is the municipality in
all three countries; for German *kreisfreie Städte* such as Köln, the admin_level 6 unit with an 8-digit
Gemeindeschlüssel). The country comes from the national municipality code on that boundary
(`de:amtlicher_gemeindeschluessel` → DEU, `ref:INS` → BEL, `ref:gemeentecode` → NLD). `country_check` compares it with
the majority country of the OBAT buildings in the same 400 m hexagon (challenge data) as an independent check.

## Spatial screening

Computed in EPSG:3035 (metres) against the **unsimplified** cached EMS geometry (`cache/flood.parquet`: flooded areas +
flood traces, merged over all products; the 10 m simplification is applied to the display only). The reference point
is classified in this order:

| Category | Rule |
|---|---|
| On the boundary / unresolved | invalid coordinates; or within 25 m of the observed flood edge; or the site/building outline overlaps the extent while the point is outside; or within 25 m of an EMS mapped-area edge |
| Inside the observed extent | more than 25 m inside the flooded areas + traces |
| Outside the extent, within an EMS mapped area | more than 25 m outside the extent and more than 25 m inside an EMS area |
| Outside EMS mapped coverage | more than 25 m outside every EMS area (only the 1 km buffer ring) |

The 25 m tolerance is our assumption for the combined position error of OSM points and the EMS delineation; it is
not an official accuracy figure. Candidates inside the extent stay in the inventory and are flagged in red on the map.

**"Outside the mapped extent" never means "safe".** EMS mapped a snapshot, missed water between buildings, did not map
flood traces in Belgium, and says nothing about today's flood risk (see EFAS), access roads or the building itself.

## Result (OSM database state 29 Oct 2026, 15:28–21:39 UTC; 60/60 tiles, none stale)

Counts within our inventory and analysis coverage, not regional totals:

| | Inside observed extent | Edge / unresolved | Outside extent, in EMS area | Outside EMS coverage | Total |
|---|---|---|---|---|---|
| School | 16 | 31 | 2,390 | 359 | 2,796 |
| Sports hall | 14 | 27 | 1,410 | 244 | 1,695 |
| Community centre | 9 | 20 | 1,368 | 254 | 1,651 |
| **Total** | **39** | **78** | **5,168** | **857** | **6,142** |

15,401 selected OSM features were read; 8,926 lie outside the analysis area (tiles are rectangles), 3,416 outdoor sports
sites (R3), 338 small buildings (R4), 78 lifecycle-tagged (R5) and 3 without geometry (R6) were excluded; 333 duplicates
were merged (1 identical outline, 296 contained, 35 same name nearby, 1 read from both sources). Country: DEU 4,328,
BEL 1,445, NLD 350, not identified 19. Country agrees with the OBAT building country for 6,118 candidates, differs for 1 (Herzogenrath, on the DE/NL border), 23 have no OBAT hexagon. 1,002 candidates have no
name in OSM; 23 carry an OSM `capacity` tag (not used as shelter capacity).

All 39 "inside" candidates are in Germany. This reflects the EMS data (Belgium: no flood traces, towns largely not
delineated), **not** a lower exposure of Belgian facilities.

## Discrepancies and limitations

- **Luxembourg is inside our coverage.** EMSR517 mapped the Moselle/Sauer border, so the analysis area (and the
  existing map) includes parts of Luxembourg. 19 candidates lie in Luxembourg communes (Mertert, Grevenmacher,
  Wormeldange, Lenningen, Stadtbredimus …; identified by commune name, as their OSM boundaries carry no BE/DE/NL code).
  They are kept, with `country` empty and `in_challenge_countries = False`, rather than silently dropped. The team
  should decide whether they stay in scope. We could not compare the coverage with the official challenge boundary
  because the annexes are not in this repository: please check against Annex 2.
- **Coverage is EMS-driven**, not administrative: whole flooded municipalities are only partly covered, and facilities
  just outside the 1 km buffer (possibly the nearest dry option) are absent. Later stages may need a wider search radius.
- **OSM completeness varies** by country and municipality, and OSM tagging is volunteered. A missing facility is not
  evidence that none exists; a mapped one may have closed (`osm_check_date` shows a recent survey where present).
- **Schools** come from the priority map's OSM cache (retrieved 29 Oct 2026, 15:29–15:55 UTC); sports halls, community
  centres and boundaries from a new query the same evening. Both are snapshots of the OSM database at `osm_data_timestamp`.
- **Sports halls inside sports sites**: halls mapped only as an untagged `building=yes` inside an outdoor sports site
  are missed by R3.
- **School outlines are usually grounds**, so `footprint_m2` is not floor area and must not be used as capacity.
- **Flood geometry**: the EMS cache drops flood slivers under 500 m² (built by `map.py`); a candidate in such a sliver
  would be classed outside. EFAS modelled hazard is not yet part of the screening.
- **Not done in this stage**: official shelter lists (municipal emergency plans, e.g. German *Notfalltreffpunkte*),
  capacity, accessibility, allocation of residents, policy comparisons.

## AI-assisted changes (for the AI sheet)

Made with Claude Code (Claude Opus 5.5) on 29 Oct 2026, from the team's written brief. What the AI did:

- Wrote `shelters.py` (acquisition, selection rules, de-duplication, municipality/country, screening, checks, export),
  `tests/test_shelters.py` (23 tests), the shelter layer, legend and popups in `map.py`, and this section.
- Changed `priority/osm.py` minimally: `fetch`, `build_query` and `cache_key` accept a query set (default unchanged, so
  the priority map's cache keys are identical; its tests still pass).
- Probed Overpass on one tile first to choose rules (found: Köln is a level-6 unit; 242 of 412 sports centres in the
  probe were outdoor sites).
- Bugs found by its own checks and fixed: closed `leisure=*` outlines were parsed as lines (2 real sports halls lost);
  same-name de-duplication measured from the site centre instead of the outline; legend icons distorted by Bootstrap CSS.

Checks actually run: 89/89 tests pass (66 existing + 23 new: selection rules, de-duplication, all four screening
categories including edge, shared flooded/trace edge, footprint overlap, invalid coordinates and wrong CRS). The
integrity check in `shelters.py` (duplicate ids, invalid or out-of-area coordinates, unknown categories, capacity without
source, identical records) passes on the full inventory. The map was loaded in headless Chromium: 6,143 markers, 39
flags, popup content, layer toggle, no console errors; the map also builds without an inventory and says so.

Not checked by a human yet / assumptions to validate: the 25 m edge tolerance; the 100 m² minimum building size; the
selection of types (e.g. whether to add community halls run by churches, universities); a sample of candidates against
reality (Street View, municipal websites); the Luxembourg scope decision. The AI did not verify any facility.

**Interface pass (same day, presentation only; inventory and calculations unchanged):** the AI added marker clustering,
type / screening filters with *shown / full inventory* counts, a collapsible exposure panel, a viewport-aware layout and
EFAS off by default. Checked in headless Chromium at 1280×720, 1366×768, 1440×900 and 1920×1080: no overlapping panels,
controls or attribution (also with the details and limits panels open); no horizontal scroll in the shelter panel; every
cluster label equals its candidate count and red badges equal the inside-extent candidates they hold; filter results
match the CSV (39 inside, 117 inside + unresolved, combined type/category filters); all existing layers, the EFAS
radios and the EFAS depth popup still work; no console errors. Not checked: touch devices, screens below 1280×720.

---

# Shelter planning scenario (stage 2: exploratory capacity and allocation)

The **Planning scenario** tab of the shelter panel answers one question, as a planning exercise that requires
verification:

> Under these stated capacity, availability and distance assumptions, how many estimated exposed residents could be
> assigned a shelter place, and where would gaps remain?

It never states that anyone is safe or has been evacuated, and it adds no recommendation or ranking.

```bash
.venv/bin/python map.py                       # builds the demand origins and embeds the scenario (no network)
.venv/bin/python -m pytest tests/test_planning.py   # needs node (alloc.js) and scipy (independent LP check)
```

## What is fact and what is assumption

| | Source | In the scenario |
|---|---|---|
| **Documented capacity** | none: no source in our inventory documents shelter capacity (the 23 OSM `capacity` tags count seats or pupils) | would be used if present, with source; the panel therefore says **"Our inventory contains no documented shelter-capacity baseline."** (stage 4 wording) |
| **Assumed capacity** | entered by the user, per facility, in its popup (or imported from CSV) | the only quantified places; labelled as an assumption everywhere, exported with that note |
| **Unknown capacity** | everything else | stays visible on the map, contributes **no** places. This is missing data, not zero real capacity: it limits the assessment |
| Available yes/no | user (default yes) | an unavailable facility contributes nothing |
| Max. straight-line distance | user, 1–25 km, default 5 km (our assumption, not a standard) | origin and facility must be within it |
| Exploratory option | user, default off | adds candidates outside EMS coverage, labelled "Exploratory scenario" |

No capacity is ever inferred from facility type, footprint, height or building points, and no default capacity is
given to any group of facilities. With no assumption entered, nothing is assigned.

**Eligibility:** candidates inside the observed 2021 extent or with unresolved screening are excluded (no capacity input
in their popup). Candidates outside EMS coverage take part only in the exploratory scenario. All others take part only
when a user enters places for them; their popup repeats that being outside the mapped extent does not establish safety
or availability.

## Demand (estimated exposed residents)

The existing estimate is reused, not re-estimated: **GHS-POP E2020 R2023A residents (reference year 2020)** shared
equally over the residential GHS-OBAT R2024A buildings of each 30″ cell and summed per flood polygon (flooded areas +
traces, EMSR517/518/520), ≈ 29,130 residents. It is a modelled 2020 estimate, not today's population, and a lower bound
in towns (see *Limits*).

To keep its spatial distribution (one Ahr trace polygon alone holds ≈ 12,000 residents over 290 ha), each polygon's
residents are spread over its parts in the 400 m hexagons, in proportion to *residential buildings of the hexagon ×
share of the hexagon covered by the part*, then summed per hexagon (`planning/demand.py`). Assumption: residential
buildings are evenly spread inside a hexagon. Polygons whose parts hold no residential building (343 small ones,
≈ 27 residents) keep their residents at an inside point. Result: **1,672 origins; total conserved exactly**
(29,129.546 in and out), every origin point inside the flood extent (checked on every build).

## Allocation method

A **maximum flow** (Dinic's algorithm, `planning/alloc.js`, runs in the browser): source → origin (its residents) →
facility (only if the straight-line distance ≤ the limit) → sink (its places). This maximises the total assigned while
respecting each origin's residents, each facility's places and the distance limit; an origin can never send more than
its own residents, so nothing is counted twice. Fractions of residents are allowed (the inputs are estimates). Among
equally large solutions, nearer facilities are tried first, but the result does **not** minimise total distance, and
which origin uses which facility is one of several equally valid answers. Distances are straight lines in EPSG:3035:
not routes, travel times or proof of access (roads may have been cut in 2021).

**Why residents remain unassigned** (per origin, after the maximum flow):

| Gap | Meaning |
|---|---|
| reachable entered places are all used | insufficient entered capacity |
| only candidates with unknown capacity in range | missing information |
| only unavailable / excluded candidates in range | scenario choices or 2021 screening |
| no candidate facility within the distance | distance threshold |

Gaps are drawn as yellow circles (size ≈ unassigned residents, outline style = reason) in the layer *Scenario:
unassigned residents*; the layer *Scenario: straight-line assignments* shows who is assigned where. The panel also
reports residents assigned across a national border.

**Exports** (browser downloads): *inputs* (facilities with an assumption: assumed capacity, availability, state,
assigned estimate, distance, exploratory flag) and *results* (one row per origin with residents, assigned, unassigned
and gap reason, plus one row per origin–facility assignment). Nothing is stored in the browser: **Reset** or reloading the page clears the
scenario. Saving and restoring a complete scenario is described in *Demonstration flow* below.


# Recovery evidence register (research file, not shown on the map)

A small, dated register of what changed since 2021 in **three selected localities (case studies, not regional
coverage)**, with next actions proposed by our team. It supports the presentation and the policy brief (Q2: what has
changed since 2021? Q4: what next?) and is **not shown in the map interface** (an "Evidence & actions" tab existed
briefly on 30 Oct 2026 and was removed so the demo focuses on the map and the scenario).

Statements are of four kinds, kept apart in the file: **sourced facts** (records), **our data** (2021 EMS observation,
2020 residents, 2026 OSM candidates), **scenario assumptions** and **team proposals** (actions; not commitments of any
authority).

```bash
# edit evidence/register.json, then
.venv/bin/python -m pytest tests/test_evidence.py   # validates the register (fails on a bad edit)
```

## The register (`evidence/register.json`)

One editable JSON file feeds the tab. `evidence/register.py` validates it on every build and adds our own figures per
locality. **Records** store: id, locality, geographic scope, measure, category, status (`proposed`, `planned`,
`in_progress`, `completed`, `unclear`) **as of** a stated date, short description, source (title, publisher, URL,
publication date or `null`), additional sources, event/works date and completion date separately, date checked,
*what the source establishes* and *what remains unverified*. **Actions** store: finding or gap, its basis (record ids,
our-data keys, scenario note), proposed action, responsible actor or role, information needed first.
The validator rejects: unknown status or category, `completed` without a completion date, non-https or badly dated
sources, duplicate ids, an action citing a record of another locality, unknown data keys. The tab can export the
whole register as CSV for review.

## Research done (30 Oct 2026)

No research from the team was in the repository, so we searched the web. Localities were chosen from our own data:
**Bad Neuenahr-Ahrweiler** (DE; 20 of its 30 candidates inside the observed extent), **Erftstadt** (DE; Blessem breach)
and **Valkenburg aan de Geul** (NL). Every source below was downloaded and its text read (PDF text extraction or the
HTML page), not taken from search snippets or summaries.

| Id | Locality | Measure | Status (as of) | Source |
|---|---|---|---|---|
| BNAW-01 | Bad Neuenahr-Ahrweiler, Lohrsdorfer Aue | partial clearance of Ahr deposits | in progress (1 Apr 2026) | [Kreisverwaltung Ahrweiler, Notmaßnahmen list](https://kreis-ahrweiler.de/wp-content/uploads/2026/04/20260401_GWH_Liste_Notmassnahmen.pdf) |
| BNAW-02 | Bad Neuenahr-Ahrweiler, Walporzheim | floodplain lowering; public-land part finished, private-land part in preparation | in progress (1 Apr 2026) | same |
| ERF-01 | Erftstadt-Blessem | "Sekundäraue", south wall, pit flood protection | planned; completion **expected** 2025, not confirmed (page undated) | [Bezirksregierung Arnsberg](https://www.bra.nrw.de/energie-bergbau/rohstoffgewinnung/gefahrenabwehr-im-erosionsbereich-zwischen-tagebau-blessem-ortschaft-blessem-und-fluss-erft) + [FAQ](https://www.bra.nrw.de/-3515) |
| VAL-01 | Valkenburg aan de Geul, Schin op Geul | 850 m quay walls + 110 m barrier | in progress (22 Oct 2026; planned to mid-2028) | [Waterschap Limburg project](https://www.waterschaplimburg.nl/projecten/herstel-kademuur-schin-op-geul/) + [news](https://www.waterschaplimburg.nl/actueel/nieuws/2026/werkzaamheden-kademuren-schin-geul-gaan-verder/) |
| VAL-02 | Limburg tributaries (regional) | early-warning system | in progress (20 Mar 2024) | [Gemeente Valkenburg, Q&A 20 Mar 2024](https://www.valkenburg.nl/data/downloadables/1/8/5/8/vraag-en-antwoord-infobijeenkomst-water-schin-op-geul-20032024.pdf) |
| VAL-03 | Geul catchment (regional) | WRL catchment plan; no preferred package chosen | proposed (20 Mar 2024) | same |

Points to note:
- **BNAW-01/02** were triggered by the **January 2025** high water (named in the list), within the Ahr restoration
  programme; they are not July 2021 measures as such.
- **ERF-01**: "completion expected in 2025" is a forecast on an undated page. We found no completion notice, so the
  status stays *planned* and an action asks for confirmation.
- **VAL-02/03** come from a March 2024 document: their status is 2.5 years old.
- Opened but **not used**: Waterschap Limburg's Leeuwterrein high-water channel in Valkenburg (completed June 2021,
  *before* the flood, damaged in July 2021), so it is not a change since 2021. A 2024 Bad Neuenahr-Ahrweiler
  presentation returned 404.
- **Searched without a verified result:** official lists of designated shelters / emergency meeting points
  (*Notfalltreffpunkte*, *opvanglocaties*) for all three municipalities. This is recorded in the register as a gap of
  our search, not as evidence that no list exists.

## Locality figures (for the brief; computed by `evidence/register.py`, not shown on the map)

Each locality is matched by name to its OSM municipality boundary (cached by `shelters.py`, no network). Inside the
boundary: estimated 2020 residents inside the observed 2021 extent (demand origins of stage 2, ± 400 m), flooded area
and traces, share of the municipality covered by the EMS mapped area, candidates by screening category and documented
capacity. **Records get no map position**: the sources describe sites in words only, and regional records (VAL-02,
VAL-03) are labelled as regional.

| Locality | Est. residents in observed extent | Flooded / traces (ha) | EMS covers | Candidates (inside / edge / outside) | Documented capacity |
|---|---|---|---|---|---|
| Bad Neuenahr-Ahrweiler | ≈ 14,850 | 42 / 464 | 70 % | 20 / 2 / 8 | 0 |
| Erftstadt | ≈ 2,300 | 172 / 894 | 100 % | 3 / 0 / 27 | 0 |
| Valkenburg aan de Geul | 0 | 2 / 0 | 86 % | 0 / 0 / 16 | 0 |

**Valkenburg** is the clearest data gap: the EMS footprint shows 2 ha and no residents, although an official source
documents July 2021 flood damage along the Geul there. Its exposure is likely under-detected (see *Limits*), and action
VAL-A1 says not to use our estimate there. The rows are **not a ranking** and must not be compared: EMS coverage and
detection differ by place.

## Analytical honesty rules applied

- The 2021 footprint, exposure figures and scenario are unchanged by any record.
- No country comparison is added: the per-country headline had a country-label discrepancy (activation vs location,
  stage 2), and coverage differs, so countries and municipalities are not ranked.
- Unknown capacity stays a data gap ("not a shortage"); no shortage, budget, deadline, commitment or readiness is
  stated. Actors are named only where the source names them; otherwise a role is given with "contact to be identified".
- A locality without a record means "no verified evidence has been added for this area", not that nothing was done.

## AI-assisted changes, register (for the AI sheet)

Made with Claude Code (Claude Opus 5.5) on 30 Oct 2026. The AI chose the localities from our data, ran the web
searches, downloaded and read each source, and wrote `evidence/register.json` (6 records, 7 actions, 1 search gap),
`evidence/register.py`, `tests/test_evidence.py` (14 tests) and this section. It corrected its own draft twice: an
action cited VAL-01 as showing the Geul "overflowing" (the source documents damage), and it had referred to a water-board
flood analysis it had not opened (removed). Checks: the 14 tests (valid register, every bad-edit type rejected, locality
figures on a toy example); every register URL returned HTTP 200 on 30 Oct 2026.

Not checked by a human yet: the choice of localities; the status labels (e.g. BNAW-02 *in progress* although the
public-land part is finished); the wording of the actions and actors.

## Limitations

- Three localities, six records: selected case studies, not regional coverage.
- Statuses are as of the source date (March 2024 – October 2026); anything later is unknown.
- Search was in German, Dutch and English on public websites; documents behind council information systems or not
  indexed may exist.
- Belgium has no case study: its towns were mostly not delineated by EMS, so our data could not support a local link.

---

# Demonstration flow (stage 3: complete scenario restore, A/B comparison, demo view)

The presentation tells the story; the map shows the evidence and how changing one planning assumption changes the
result. Stage 3 changed only the interface and the scenario's save / restore. The exposure map, inventory, allocation
algorithm (`planning/alloc.js`, unchanged), filters, priority map and both CSV exports stay as they were.

## What changed

- **Recovery-evidence tab removed** from the map (no empty tab left: the shelter panel has its two original tabs). The
  research stays in `evidence/` (see above).
- **Planning scenario panel, reorganised.** Four kinds of information are labelled: *2020 est.* (historical exposure
  estimate), *Candidate facilities (OSM)*, *User-entered* (scenario assumptions) and *Calculated* (allocation result).
  Two warnings stay visible: straight-line connections are not verified routes; entered capacity is an assumption unless
  a documented source supports it. Details are collapsible and stay open across recalculations: *Why residents remain
  unassigned*, *Facility inputs*, *Data behind this scenario* (exposure reference year and EMS limits, candidate counts,
  documented vs unknown capacity) and *Method and limits*.
- **Scope is explicit.** The results always cover the whole analysis area (all EMS mapped areas + 1 km). Map zoom and the
  candidate type / screening filters change the display only, not the allocation (tested). No locality-level figure
  was added.
- **Percentages** keep precision for small shares: 78 of ≈ 29,130 shows "0.27 %", under 0.1 % shows "< 0.1 %".

## Complete save and restore

Before stage 3, importing read only `candidate_id`, `assumed_capacity` and `available`. It ignored the exported
`max_distance_m` and `exploratory_outside_ems`, and it **merged** the file into the current scenario. An empty
scenario exported no rows, so its settings were lost. All three issues were confirmed in the code and are fixed.

- **Save scenario (JSON)**: a versioned file (`format: floodmap-shelter-scenario`, `version: 1`) with the settings,
  every facility input (capacity, including 0, or `null`; available true/false), the data build id, the demand total
  and the result.
- **Export inputs (CSV)**: same columns as before. An empty scenario now writes one `settings_only` row so the distance
  and the exploratory option survive.
- **Restore from file** (JSON or CSV) **replaces** the scenario and recalculates it with the existing allocation engine.
  - The restore is aborted, leaving the current scenario unchanged, on: an invalid capacity (negative, decimal, text);
    an invalid `available` value; a distance outside 1–25 km or not a whole km; conflicting distance or exploratory
    values across rows; the same id twice with different values; an unknown JSON format or version.
  - Ids not in this map's inventory, and candidates inside the 2021 extent or unresolved, are skipped. The message
    lists them as a *partial restore*.
  - A legacy CSV without the settings columns restores its facility inputs and says which settings were missing and set
    to the defaults (5 km, off).
  - A JSON file from a different data build (demand or inventory changed) is restored with a warning.

## Baseline / current comparison (A/B)

**Capture as Scenario A** stores an independent copy of the assumptions and their result, so later edits cannot change
it. The current scenario is B. The comparison shows, for A, B and B − A:
- the settings (distance, exploratory option);
- estimated exposed residents (always identical: same demand data, checked with the build id);
- facilities with places and the places entered at them;
- residents assigned and unassigned;
- **Additional residents assigned under these assumptions (B − A)**.

It also lists every changed assumption (capacity, availability, distance, exploratory option). When more than one
changed, it states that the difference cannot be attributed to any one of them. **Restore A** puts A's assumptions back,
recalculates and confirms the same result. **Capture B as new A** and **Clear comparison** are also available.

## Demo view

**Save demo view** / **Return to demo view** (title panel) store the map centre and zoom only, in this browser when
local storage is available. They never touch the scenario, filters or layers, and the message after saving repeats
that results still cover the whole analysis area.

## How to demonstrate a baseline and one unavailable facility

1. Zoom to the area to show (e.g. the Ahr valley) and click **Save demo view**.
2. Open **Planning scenario**. Click a few candidates outside the observed extent and enter an *assumed* number of
   places in their popup (say clearly that these are illustrative assumptions, not real capacities).
3. Click **Capture as Scenario A**. Optionally **Save scenario (JSON)** as a backup before presenting.
4. Open one of those facilities' popups and untick **Available in this scenario**.
5. The comparison shows B − A for assigned residents, the one changed assumption ("available → unavailable") and the
   yellow gap circles on the map. Phrase it as "fewer residents can be assigned a place *under these assumptions*".
6. Click **Restore A** to return to the baseline (same result), and **Return to demo view** if the map moved.

## Checks actually run (30 Oct 2026)

- **Full suite:** 139/139 tests pass: 119 earlier tests plus 20 new browser tests (`tests/test_scenario_browser.py`,
  headless Chromium, the real page, real CSV/JSON downloads and file uploads).
- **Export and restore:** at 21 km with the exploratory option on, with a zero capacity and an unavailable facility,
  exported as CSV and as JSON, reset, restored: the distance, the option, every input and the result return exactly.
- **Replace, not merge:** after restoring, an extra assumption added after the export is gone (CSV and JSON).
- **Empty scenario:** 17 km with the exploratory option on and no inputs survives saving and restoring (CSV and JSON).
- **Legacy CSV:** inputs are restored and the missing settings are named in the message.
- **Bad files:** 7 invalid or conflicting files abort with the right message and leave the scenario unchanged; unknown
  and ineligible ids are reported as a partial restore.
- **A/B:** A is not mutated by later edits; the demand totals match; the shown B − A equals the computed difference;
  one change gives no attribution warning, two changes do; Restore A reproduces A's result exactly.
- **Demo view:** returning restores the centre and zoom; the scenario state is identical before and after.
- **Filters:** the "inside" filter still shows 39 candidates, and the allocation result is the same with filters applied.
- **Wording and layout:** 78 / 29,130 → "0.27 %"; no "saved", "safe evacuation", "people saved" or "verified shortage"
  wording in the panel; at 1366×768 no horizontal scroll in the shelter panel and no overlap between the title panel,
  shelter panel, legend, layer list and attribution (all sections open); no page errors.
- **Screenshots** checked by eye at 1366×768 and 1280×720: the panel scrolls; the comparison is readable.

## Limitations

- At 1280×720 and 1366×768 the shelter panel must be scrolled to reach the comparison; there is no separate
  presentation mode.
- The demo view is kept only in this browser (local storage); it is not part of the saved scenario file.
- Scenario A lives in the page only. Reloading clears it; save A as JSON if it must survive.
- **Restore A** depends on the same page build; a JSON file from another build gives a warning, not a guarantee.
- Not checked: other browsers, touch devices, CSV files re-saved by Excel (separator and encoding), screens below 1280×720.
- The intermittent page error seen once during the earlier evidence-tab checks ("reading 'lat'") did not occur in these
  runs; its origin remains unidentified.

## AI-assisted changes, stage 3 (for the AI sheet)

Made with Claude Code (Claude Opus 5.5) on 30 Oct 2026, from the team's written brief. The AI:
- inspected `planning/ui.js` and confirmed the restore bugs;
- removed the evidence tab (reverting its wiring in `map.py` and `planning/ui.js`; the deleted `evidence/ui.js` /
  `ui.css` were never committed);
- rewrote the scenario panel, import / export and comparison in `planning/ui.js` and added styles in `planning/ui.css`;
- added the data build id and the demo-view controls in `map.py`;
- wrote `tests/test_scenario_browser.py` and this section.

Found by its own checks and fixed: the list of changed assumptions was hidden inside a closed section; the panel was too
tall at 1366×768 (settings merged into one row, demo note shown only after saving). The allocation algorithm and the
demand data were not modified.

Not validated by a human yet: the panel wording; whether 0.27 % style precision is wanted everywhere; the decision to
reset legacy settings to defaults rather than keep the current ones.

---

# Presentation scenes (stage 4: one map)

`flood_map.html` now combines the exposure map and the former priority map in **one page with four scene buttons**.
The team tells the story orally; each scene only switches layers, the result panel and the legend. The map view,
the scenario inputs, Scenario A and the demo view are never changed by a scene switch (tested). The numbering below is
our presentation order, not the hackathon's question numbering. Research on changes since 2021 stays in the
presentation and policy brief (`evidence/`), not on the map.

| Scene | Shown by default | Result panel |
|---|---|---|
| **1 What happened?** | Observed EMS flooded areas + traces, EMS mapped areas, normal water | Mapped flooded area (131 km²: 103 flooded + 28 traces), 13,956 buildings and ≈ 29,130 estimated residents **inside the mapped observed flood extent**; coverage warning (not mapped ≠ not flooded, urban flooding missed, Belgian observations incomplete); totals **by EMS activation** kept apart from the geographic split; EMS vs EFAS table |
| **2 Who was exposed?** | Exposed residents per fixed 400 m hexagon (light flood fill underneath) | Total, Top 10 exposed hexagons (click: highlight + zoom), Top 10 share with explicit denominator; optional context: buildings (all, not flooded), vulnerable facilities |
| **3 Where could they go?** | Candidate shelters, unassigned-demand circles | The existing planning scenario (capacity, availability, distance, exploratory option, gaps, assignment lines, save / restore, exports), A/B comparison directly under the result; candidate filters in the second tab |
| **4 Where to start?** | Scenario-based planning priority per hexagon | Status, Top 10 areas with P, U, E, G, S, totals (exposed / assigned / unassigned), weight sliders + reset, missing-information notes, method; optional context: critical infrastructure, vulnerable facilities and their separate asset lists |

Advanced controls are collapsed: **Layers ▾** (every layer, including the assignment lines, population and buildings) and
**EFAS hazard ▾** (modelled 10/100/500-year depth, click for depth). Scene switches turn EFAS off; it is context only, and
no historical total or shelter result is presented as an EFAS-scenario result. There is no fifth analytical scene.

## Exposed residents per fixed hexagon (scene 2)

The demand origins of the allocation model (1,672 origins: 1,329 hexagon origins and 343 fallback origins from flood
polygons without residential buildings) are summed on the **same fixed 400 m grid** as `map.py` (EPSG:3035, axial
index `h{q}_{r}`, a stable id). Fallback origins go to the hexagon containing their point. Every origin is counted once:
**1,595 hexagons, total 29,129.5 estimated residents, identical to the origins and to the flood-polygon total**
(`planning/demand.py: hex_summary`, checked at every build by `check_hex_summary`). Country = majority country of the
hexagon's OBAT buildings (238 hexagons without buildings: "not attributed"); municipality is not reliably available
and not shown. Reference: GHS-POP E2020 R2023A (2020) residents shared over residential GHS-OBAT buildings, inside the
mapped observed extent. 400 m is the aggregation grid, not the accuracy of the estimate.

Below zoom 12 the hexagons are grouped into circles labelled with the **sum of estimated residents** of the grouped
hexagons (not the number of points or hexagons); the circles regroup with zoom, the sum does not change. From zoom 12
each hexagon is shaded (warm colours, 6 classes: < 1, 1–9, 10–49, 50–149, 150–399, ≥ 400). Rankings always use the
fixed hexagons, never the circles.

## Scenario-based planning priority (scene 4)

For each fixed hexagon with estimated exposed residents P_i > 0 (hexagons without exposed residents are excluded):

- U_i = residents of the hexagon left unassigned by the **current** shelter scenario (sum over its origins of demand − assigned)
- E_i = 100 × min(1, ln(1 + P_i) / ln(1 + P99)); **P99 = 409.7 residents**, the 99th percentile (numpy linear
  interpolation) of P over all 1,595 hexagons, fixed at build time: zoom and filters never change it
- G_i = 100 × U_i / P_i
- S_i = wE × E_i + wG × G_i, weights ≥ 0 normalised to sum to 1. **50 / 50 is an illustrative starting assumption.**
  Both weights 0: no score and no ranking, with a message (no hidden fallback).

Ties (e.g. E capped at 100 for the ≈ 16 hexagons at or above P99) are ordered by P, then by hexagon. The score is
recalculated whenever capacity, availability, distance or the exploratory option changes (same event as the allocation).
With no usable capacity entered, G = 100 everywhere and the panel says this is the exposure ranking, with no
capacity-based differentiation; if G is identical everywhere for another reason, the panel says it does not change the
ranking. Uncertainty is **not** a score component: missing information (unknown capacity, no candidate in range,
observation gaps, Belgium, unmodelled vulnerability) is listed separately, per hexagon in the popup and in the panel.
Unknown capacity is described as missing data, never as a verified shortage. It is labelled "Scenario-based planning
priority": not a flood probability, a validated vulnerability index or a definitive ranking of actual need, and it does
not support comparisons between countries (observation coverage differs).

**Asset scores stay separate.** Vulnerable facilities and critical infrastructure keep their own 0–100 asset screening
scores (P/B/F × type factor, `priority/scoring.py`) in their own lists and popups, labelled as asset scores. They are
never combined with the area priority, never in the same Top 10, and the legend says their values are not comparable.

## What else changed

- Single entry point: `priority_map.html` and its page code (`priority/map.js`, `map.css`, `sidebar.html`) are retired;
  `priority_map.py` now writes `cache/priority/assets.json` (read by `map.py`) and `priority_ranking.csv` (unchanged,
  byte-identical after the rewrite). Its P/B/F **area** shading is replaced by the scenario-based area priority.
- Removed duplicates: one title panel (scene buttons, country zoom, demo view), one result panel per scene, one legend
  whose blocks follow the visible layers (the flood legend shrinks to one row in scenes 2 and 4), layer lists collapsed.
- Scenario panel: wording "Our inventory contains no documented shelter-capacity baseline."; A/B comparison moved
  directly under the result; it opens on the planning scenario tab.
- No recovery-evidence cards were on the map any more (removed in stage 3); `evidence/` is untouched.
- The flood map is larger: ≈ 37 MB (was ≈ 30 MB), mostly the 19,313 OSM asset records.

## Checks actually run (30 Oct 2026, stage 4)

- **Full suite: 163/163 pass, twice in a row** (headless Chromium, 1366×768, the real page): 24 new tests
  (`tests/test_area_priority.py` 10, `tests/test_scenes_browser.py` 14), `tests/test_browser.py` retargeted to the asset
  layers of `flood_map.html`, and every earlier test, including the 20 scenario save / restore / A/B tests.
- **Totals reconcile:** origins (1,672) → fixed hexagons (1,595) → overview circles all give 29,129.5 residents; every
  origin is in exactly one hexagon; hexagon ids are unique; at the "All" view the circle labels sum to the total.
- **Top 10 lists:** 10 unique fixed hexagons, identical before and after zooming; scene 2 states "Top 10 hold 27 % …
  (≈ 7,940 of ≈ 29,130 in all 1,595 hexagons)".
- **Scores:** `planning/priority.js` matches a hand calculation (worked example P = 100, U = 30, P99 = 409.7 →
  E = 76.69, G = 30, S = 53.35) and an independent Python recomputation of E, G and S for every hexagon from the page's
  own allocation result, after capacity and distance changes. All-zero weights give no score; negative weights are
  rejected; with constant G the order equals the exposure order.
- **Zoom independence:** P99, the full order and every score are identical after zooming to Germany at zoom 15.
- **Scenario link:** entering capacities changes the ranking; distance changes recalculate; with no capacity the
  panel shows the exposure-ranking message and no "verified shortage" wording.
- **State preservation:** switching through all scenes leaves the scenario inputs (9 km, exploratory on, a zero
  capacity, an unavailable facility), Scenario A and the demo view unchanged.
- **Legends and layout:** per scene, the expected legend blocks are visible and the others hidden; with every section
  open, no horizontal scroll and no overlap between title panel, scene panel, legend, layer controls, limits and attribution.
- **Asset scores:** browser scores equal `priority/scoring.py` at default weights; asset weights change the asset
  rankings but never the area priority. `priority_ranking.csv` is byte-identical after the rewrite of `priority_map.py`.
- **Stress:** rapid scene switching (3 page loads × 30 switches, plus zoom) gives no page error.
- **Screenshots** of each scene, a Top 10 click (zoom + highlight + popup) and scene 4 with capacities, checked by eye at 1366×768.

## Limitations (stage 4)

- The area priority depends entirely on user-entered capacities; with none, it is an exposure ranking.
- **U and G per area are not unique.** The allocation (maximum flow) maximises the total assigned; which origins receive
  the places is one of several equally valid answers (stated since stage 2). Example run: 6 facilities × 300 assumed places
  near the most exposed origins assigned ≈ 1,800 residents, but the top hexagons kept U = P because the places went to
  other origins within 5 km. Read G as a scenario-level signal, not a per-area verdict. Changing this would need an
  allocation rule (e.g. nearest-first or proportional), which is a team decision and was not made here.
- P counts estimated residents inside the **mapped** extent only; urban and Belgian flooding is under-observed, so areas
  there are likely under-ranked. Hexagons with only fallback (area-share) residents carry tiny values.
- Straight-line distances only; no routes, travel times, or individual vulnerability (age, health, mobility).
- Overview circles (scene 2) are a display aggregation by screen distance; their grouping changes with zoom.
- Asset scores are recomputed in the browser only for the weights; asset sensitivity ranges are those of the default run.
- Not checked: browsers other than headless Chromium, touch devices, screens below 1366×768 for the new panels.

## AI-assisted changes, stage 4 (for the AI sheet)

Made with Claude Code (Claude Opus 5.5) on 30 Oct 2026, from the team's written brief. The AI inspected the two maps
and their modules, then wrote `planning/scenes.js|css`, `planning/priority.js`, `priority/assets.js|css` (ported from
`priority/map.js`), `hex_summary` / `exposure_reference` / `check_hex_summary` in `planning/demand.py`, the scene
panels and wiring in `map.py`, the asset export in `priority_map.py`, small hooks in `planning/ui.js`, the tests
`tests/test_area_priority.py` and `tests/test_scenes_browser.py` (and retargeted `tests/test_browser.py`), and this
section. The allocation algorithm (`planning/alloc.js`), the demand estimate and the asset scoring formulas were not
modified.

Found by its own checks and fixed: (1) the page's hexagon totals were rounded to 4 decimals while the allocation
used other values, so G came out at 99.9999 instead of 100 and the most exposed hexagon dropped out of the exposure
ranking; (2) the allocation received residents rounded to 3 decimals, which set 125 tiny fallback origins (0.006
residents in total) to zero, so 108 hexagons would have had no demand. Both now use the unrounded demand (9 decimals).
**Side effect: the data build id changed**, so scenario JSON files saved before stage 4 restore with the existing
"different data build" warning; (3) a race in the marker-cluster library (layers removed by a scene switch while still
loading) caused an intermittent page error; chunked loading is off and candidate shelters start hidden.

Not validated by a human yet: the 50 / 50 starting weights; the log scaling with P99 as cap; the scene wording; the
decision to drop the former P/B/F area shading; the colour choices (area priority orange-red, vulnerable facilities pink).
