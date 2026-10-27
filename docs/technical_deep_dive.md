# Technical deep dive

The README answers *what this is and how to run it*. This answers *how it works
and why it is built this way* — the questions a technical juror asks after the
three minutes are up, and the questions you will ask yourself at 02:00 when a
number looks wrong.

Everything here is re-derived from the code and the config as they stand on
27 October 2026. Where a figure comes from a measurement rather than from the
repository, it says so, with the date it was measured. `docs/decisions.md` carries the dated record of every
change to what a number means; this file describes the current state only.

---

## 1. The pipeline, end to end

```
config/sources.yaml          one file owns every URL
        │
        ▼
python -m src.fetch          85 files, idempotent, robots-aware
        │
        ├───────────────────────┬───────────────────────┐
        ▼                       ▼                       ▼
build_exposure.py          build_context.py          build_geometry.py
 hazard × population        built-up, Natura,         boundaries →
 per NUTS3 × RP             basins, future            simplified polygons
 + Eurostat indicators      discharge, declared
 --protection: the same     areas, GDP, density,
 pass behind the JRC        income, residual
 protection standards       exposure, hospitals and
        │                   schools, the 2010 epoch
        ▼                       │                       │
exposure.parquet                ▼                       ▼
exposure_protected.parquet  context.parquet         regions.geojson
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
                  api/main.py             14 JSON routes over src/
                        │
        ┌───────────────┼──────────────────────────┐
        ▼               ▼                          ▼
   web/ (React)    app/streamlit_app.py      scripts/export_bi.py
   2 views: July   7 tabs, reads the          → bi/data/*.csv
   2021, Europe    parquets directly          → bi/FloodPolicyKit.pbip
   (5 tabs, SVG                                 (Power BI, docs/power_bi.md)
   choropleth)
```

The July 2021 event has its own chain, beside this one, from the organisers'
bucket to the policy tool and the React app's first view (§5, "The July 2021
pipeline").

Two properties of this shape are deliberate.

**The two derived files are separate.** The exposure table is a multi-hour
continental pass over 300 MB rasters; the geometry is seconds over one 25 MB
boundary file. Re-running the slow one to redraw a map would be absurd, and
coupling them would guarantee it happened.

**Both UIs read the same frozen table.** They cannot disagree about a number,
because there is only one number - `app/streamlit_app.py` reads the parquet
directly rather than going through the API, which is why it needs neither the
server nor `npm`. They do NOT show the same views. React has two views
(`VIEWS` in `web/src/App.jsx`): "July 2021", which opens first and reads the
event JSON (§5), and "Europe", which holds five tabs (Exposure, Context,
Vulnerability, Draft, Translation) and draws the choropleth inside the first.
Streamlit has seven tabs, adding "Ask the table" and the AI usage log. The
React UI is the one to demo.

**A static build needs no API.** `VITE_STATIC=1` builds a React app that reads
files shipped in `dist/` instead of calling the server: the July 2021 JSON
written by `scripts/export_event_web.py`, and the Europe view's API answers
frozen into `web/public/europe/` by `scripts/export_europe_web.py`. Draft and
Translation call a language model, so they are switched off there. The public
demo is that build, served as a static Hugging Face Space (README, "Live demo").

---

## 2. Five coordinate systems, and which one does what

This is the section to read before touching anything. The most expensive
geospatial bug is silent: a layer in the wrong CRS still plots, still joins, and
still produces a number. It is just the wrong number.

| CRS | Where | Used for |
|---|---|---|
| **EPSG:3035** (ETRS89-LAEA) | `data_io.WORKING_CRS` | every area, distance and zonal computation |
| **EPSG:4326** | JRC hazard rasters; `data_io.WEB_CRS` | the hazard's own grid; the last step before display |
| **ESRI:54009** (World Mollweide) | GHS-POP | the population grid, and the grid exposure is computed on |
| **EPSG:27704** (Equi7 Europe) | JRC observed flood depth | the validation layer's own grid |
| **EPSG:31370** (Belgian Lambert 72) | the Walloon *aléa* and July 2021 layers | Belgium only; reprojected before any European join |

Three rules follow. The first is enforced in `src/data_io.py`; the second is
enforced where it matters rather than centrally - `scripts/build_exposure.py`
asserts the boundary CRS before opening a raster, and `exposed_population`
reprojects the polygons to the population grid itself. `data_io.check_alignment`
exists for the third-party case and is currently called by nothing, which is
worth knowing before relying on it.

- **A file with no CRS raises.** Guessing one is how a whole analysis lands
  silently in the wrong place. `load_vector` refuses rather than assuming 4326.
- **Reproject the polygons to the raster, never the raster to the polygons.**
  Reprojecting a raster of *counts* moves people between cells. `check_alignment`
  fails loudly when the two disagree, because `rasterstats` will otherwise return
  zeros for every polygon — a result that reads as "nobody is exposed" rather
  than as an error.
- **A tolerance is a distance, so it is applied in a metric CRS.** A degree is
  not a distance: 0.01° is about 1.1 km north–south everywhere but ~700 m
  east–west at Belgian latitudes and under 500 m in northern Finland.
  `build_geometry.py` therefore simplifies in 3035 and converts to 4326
  afterwards.

The hazard rasters are 3 arc-seconds — about **92 m north–south but 60 m
east–west** at Belgian latitudes. The cells are not square, so any area computed
in 4326 is wrong. `docs/geospatial_crash_course.md` works this through.

---

## 3. Exposure: what the number means

`Risk = Hazard × Exposure × Vulnerability`. This repository computes the middle
term and gives the third its own module; the first arrives as data.

### 3.1 The two modes

`src/exposure.py` offers `fraction` and `binary`, and they answer different
questions.

- **`fraction`** (default) thresholds the hazard at its own resolution, then
  averages the 0/1 wet mask over each population cell. A cell 30% flooded
  contributes 30% of its people. Right at 1 km, where one population cell holds
  roughly 185 hazard cells at Belgian latitudes.
- **`binary`** counts a population cell's whole population as soon as any part of
  it is flooded. Coarser, and an over-estimate by construction.

The order matters in `fraction` mode: **threshold first, average second.**
Averaging depths and thresholding afterwards answers "is the *mean* depth above
the threshold?", which systematically under-reports small deep floods.

### 3.2 `nodata_means_dry`, the argument that decides what the figure means

The JRC hazard maps are sparse: they store a depth **only** where there is
inundation. Measured on RP100 over a 1,468,800-cell window of Belgian land,
4.85% of cells carry a value and 100% of those are deeper than 0 m. On such a
layer the valid mask **is** the flood footprint.

- `nodata_means_dry=True` (default) — nodata is ground the layer looked at and
  found dry. The flooded share is the wet mask over the **whole** cell.
- `nodata_means_dry=False` — nodata is ground nobody looked at, which is what an
  AOI-clipped delineation (Copernicus EMSR, the Walloon 2021 layers) gives you.
  The share is measured over the observed part and extrapolated onto the unit.

Passing `False` for a sparse layer collapses the two: every cell holding any
water reads as wholly flooded, and the "fractional" figure becomes the binary
over-estimate under another name — **13,771,935 people against 5,065,526** over
BE/NL/LU at RP100, bit-identical to what `mode="binary"` returns. Passing `True`
for an AOI-clipped layer reports unobserved ground as dry. Neither is recoverable
from the output, so neither is inferred.

### 3.3 Four columns, and why `None` is not `0.0`

| Column | Meaning |
|---|---|
| `exposed_pop` | people on flood-prone ground, extrapolated onto the whole unit where the layer covered only part of it, or `None` when nothing was measured |
| `exposed_pop_observed` | the same count with **no extrapolation in it**. This is the one that is additive over disjoint windows, so a windowed build sums this and divides once at the end |
| `cells_counted` | population cells whose **centre** falls in the unit |
| `hazard_coverage` | the share of the unit, in [0, 1], the hazard layer covers |

A unit the population grid covers but the hazard raster does not would otherwise
report a measured `0.0`. That is the one error that must never reach a brief,
because it reads as reassurance. `None` means "not measured"; `0.0` with a
positive coverage means "measured, nobody exposed", which is a real finding.

`all_touched=False` on the zonal statistics: a cell belongs to the unit
containing its centre. `True` would count every boundary cell in *both*
neighbours, so the sum over all units would exceed the national total.

**Report `hazard_coverage` next to `exposed_pop`.** Below 1.0 the figure is an
extrapolation from the observed part onto the whole unit, and the reader is
entitled to know that.

### 3.4 Windowing: the population grid, not the hazard raster

A continental pass over one return period needs ~64 GiB if done in one go —
51,992 x 110,162 cells is 21.3 GiB per float32 array, and the band plus its
two derived masks are three of them. It is
therefore cut into pieces — and **which raster gets cut is a correctness
question, not a performance one.**

`scripts/build_exposure.py` takes row windows over the **population grid** and
reads whatever hazard region covers each one, with a two-cell margin so the warp
is never short of source. A population cell belongs to exactly one window by
construction, so nothing is written twice and the per-unit sums are additive
whatever the window count.

Cutting the hazard raster instead cannot have that property, and this repository
shipped that version until 6 October 2026. A population cell lying across two
hazard stripes is written by both, and `Resampling.average` renormalises over
whatever source area each piece happens to hold — so both pieces reported a
coverage near 1 for the same cell instead of roughly a half each. Summed coverage
reached **1.08 at two stripes and 1.17 at three**, when it must be 1, and the
continental RP100 total moved by **0.25% between 3 and 13 stripes**: 29,808,232
against 29,732,746 people, with 215 of 1,345 regions disagreeing and the worst
(PL514) by 14.7%. `tests/test_stripes.py` pins the invariant at 1, 2, 3, 5, 7 and
13 windows. See `docs/decisions.md` for the dated record.

Three running totals are accumulated, and which one is summed matters:

- `exposed_pop_observed` — the figure with **no extrapolation in it**. Summing
  `exposed_pop` instead would apply the extrapolation once per window.
- `cells_counted` — summed, because the windows are disjoint.
- `hazard_coverage × cells_counted` — so a unit's coverage is the cell-weighted
  mean over its windows, not a mean of means that would weight a window holding
  three cells like one holding three thousand.

The extrapolation onto unobserved ground then happens **once**, over the whole
unit. Under `nodata_means_dry` coverage is 1 everywhere but the layer's own edge,
so for a pan-European run it is the identity.

### 3.5 What is masked out, and why

Two companion rasters ship on the same grid as the depths, and both are applied
by default:

- **Permanent water bodies** — the river channel, the lakes and the sea, already
  water before any flood. They are patched into the depth rasters at exactly
  1.00 m, so they survive every threshold up to and including 0.5 m. Measured on
  the Benelux at RP10 they are 21.3% of wet cells; masking them moves the RP100
  figure by **−14.2%**.
- **Spurious depth areas** — cells the JRC itself flags as modelling artefacts.

`--min-depth-m` defaults to **0.5 m**, the usual threshold for damage to
buildings. Pass `0` for the any-water upper bound, and say which you used.

### 3.6 Undefended and residual: the dykes the maps leave out

The JRC maps "do not account for the influence of local flood defences, in
particular dyke systems" (Dottori et al. 2022, in the corpus as
`jrc_hazard_maps_validation_essd_2022`). Every figure in `exposure.parquet` is
therefore **undefended**: the people the water reaches if no defence holds.
The JRC's own headline - about 160,000 people exposed each year in the EU+UK -
is defended and probability-weighted, which is why the two differ by two
orders of magnitude.

`build_exposure.py --protection` reruns the same pass behind the PESETA IV
flood protection standards (`jrc_flood_protection_standards`, 500 m, EPSG:3035,
design return periods 2 to 10,000). In every hazard window, each cell whose
standard is at least the scenario's return period is set to the hazard's
nodata, which this layer reads as dry: observed, nobody exposed. Three choices
decide what the residual figure means:

- **Nearest neighbour, never an average.** A standard is a property of a
  place; averaging a 1-in-50 cell with a 1-in-1,000 one invents a dyke nobody
  built. `protected_cells` reprojects the 500 m standards onto the ~90 m hazard
  window with `Resampling.nearest`.
- **Unknown is unprotected.** A cell with no standard (nodata -1, or outside
  the raster) is never masked, so where the standards are silent the residual
  figure stays at the undefended one - an upper bound, not a guess.
- **Never over the undefended table.** The parts are parked as
  `rp*_..._m2_prot.parquet` and the table is written to
  `exposure_protected.parquet`; `build_context.py` carries it into
  `context.parquet` as `residual_exposed_pop_rp*`. A second headcount in
  `exposure.parquet` would be scanned into the vulnerability index (§4.3).

The value 10,000 is real, not a fill: all 22,572 such cells are in the
Netherlands, whose coastal dyke rings are built for it. The standards date from
2019 and were derived for an older generation of the hazard maps than v3.1.1;
quote the residual figure as "behind the design standards", never as "after
protection".

---

## 4. The derived files, and the UI contract

### 4.1 `exposure.parquet`

One row per region × return period. Long rather than wide because every consumer
wants it that way — plotting, the LLM prompt, and the expected-annual-damage
integration, which needs the probability attached to each row.

**Return-period extents are nested**: the 100-year zone contains the 10-year one.
These rows must never be added together — RP10 + RP100 + RP500 triple-counts the
core floodplain. Report each separately, or integrate over probability with
`expected_annual_exposure`. `/api/exposure` enforces this by narrowing to one
period server-side and saying so in `defaulted_return_period`.

### 4.2 `regions.geojson`

`scripts/build_geometry.py` simplifies the 1,345 GISCO NUTS3 polygons at
**1 km** in EPSG:3035, converts to 4326, keeps two properties and rounds
coordinates to four decimals. 25 MB becomes 2.8 MB. It is not committed (GISCO
terms), so a hosted Streamlit app with no `data/raw/` calls `ensure()`, which
downloads the layer from GISCO and builds the file on first use.

Two choices are load-bearing and both fail silently if got wrong:

- **The property names are the join key.** `Choropleth.jsx` reads
  `feature.properties[idKey]`, where `idKey` is whatever `/api/exposure` reports —
  `nuts_id` for a NUTS3 run, `lau_id` for a LAU zoom. GISCO's own spelling is
  `NUTS_ID`. Shipping that draws all 1,345 regions in the "not measured" grey,
  because the join finds nothing and nothing errors.
- **All 1,345 polygons are kept**, EU-27 or not. Dropping regions changes the map
  twice over: the missing regions, and the colour of every other one, because the
  legend's classes are quantiles over whatever is present.

### 4.3 `context.parquet`, and the layers that can be rebuilt alone

One row per region, everything `exposure.parquet` must not hold: a numeric
column there is picked up by `api/main.py::vulnerability_indicators` and enters
a min-max-scaled weighted mean. Three layers were added on 24 October 2026:

- **Residual exposure** - `residual_exposed_pop_rp*`, read from
  `exposure_protected.parquet` (§3.6). A region missing from that run reads
  NaN, never 0: 0 would say the defences hold everyone there.
- **Hospitals and schools** - `src/facilities.py` reads each GISCO point at its
  own location in the RP10, RP100 and RP500 rasters, with the same 0.5 m
  threshold and the same two masks as the people count, undefended and behind
  the protection standards (`hospitals_flooded_rp100`,
  `schools_flooded_residual_rp100`, ...). **A country the layer does not cover
  is NaN, not 0**: GISCO holds no German hospital, and a 0 there read as a
  measured all-clear for the most populous Member State. The same rule applies
  to hospital beds, which most countries do not report, and down to the
  hospital: a bed column is NaN in a region where any hospital it would sum
  has no bed figure, and `hospitals_cap_beds_known` counts the hospitals that
  carry one (3,600 of 13,988).
- **The 2010 epoch** - `exposed_pop_2010_rp100` and
  `exposed_built_m2_2010_rp100` with their totals: today's footprint over the
  2010 GHSL grids, through the same `_exposure_one_period` as the 2025 figures,
  so the difference is what moved into the floodplain, not how it was counted.

`build_context.py --only <layer>` recomputes one of these (`residual`,
`facilities`, `epoch2010`), or another of the layers in its `LAYERS` (`climate`,
`sealing`, `imperviousness`, `pluvial`, `flood_recurrence`, `efas2021`,
`hera_trend`, `landcover`), into the existing table and keeps every other column byte for byte. It refuses
a table whose rows are not in boundary order, because the join is positional.

### 4.4 The fourteen routes

`/api/health`, `/api/config`, `/api/event2021`, `/api/meta`, `/api/exposure`,
`/api/context`, `/api/geometry`, `/api/vulnerability`, `/api/search`,
`/api/draft`, `/api/languages`, `/api/translate`, `/api/approve`, `/api/ask`.

`/api/config` tells the UI what the deployment allows, so it greys out what the
server would refuse: with `HOSTED=1` every route that calls a model or writes
answers 403 before any provider is reached. `/api/event2021` serves the July
2021 JSON written by `scripts/export_event_web.py` byte for byte; locally the
`--full` build wins when present, the hosted demo always serves the public one.

`/api/ask` takes either a `question` or a query `spec`. A question costs one
model call that writes the spec and nothing else; `src/nlquery.py` validates it
against a whitelist of defined columns and operators and pandas runs it, so the
answer can hold no figure the frozen table does not. Exactly one return period
per answer, rows and never aggregates, and the definition of every column used
travels with the rows. A refused spec is **422** with the rule it broke; no
reachable model is **502**, and the `spec` form keeps working without one.

`/api/context` serves the second frozen table, and it is a separate route rather
than extra columns on `/api/exposure` for a reason that is structural:
`vulnerability_indicators` picks the composite index's inputs by scanning numeric
columns, so a climate percentage or a basin share arriving on an exposure row
would be one selection away from becoming a min-max-scaled term in a weighted
mean — "this region's rivers rise faster, therefore its residents are more
vulnerable". The two tables are loaded separately and never merged server-side.
Its `climate_periods` block carries `single_member`, which is the field that
separates "one model chain, so nothing was compared" from "the chains disagree":
both read as zero regions agreeing on the sign. It reports both sign counts,
`regions_robust_on_sign` (at least 80 % of members) and `regions_agreeing_on_sign`
(all of them).
It also carries `regions_size_uncertain`: regions whose members lie more than
100 points apart — the full range at two members, the interquartile range above
two — which neither UI ranks (see `docs/decisions.md`, 2026-10-13 and
2026-10-25).

`/api/approve` is the only route that writes. `/api/translate` is the only one
that can refuse its own output: a translation that changed a figure or moved a
citation comes back as **422**, not as 200 with a warning field, so no client can
render it by ignoring a flag. The choropleth is drawn as **SVG
from GeoJSON** — no tile provider, no API key — so the map still renders with the
network unplugged. That is why there is no Google Maps layer here and never will
be: a Static Maps call needs a billed key and its terms forbid redistributing the
imagery in a document that circulates.

---

## 5. Validation: the credibility half

`src/validate.py` is the part that answers "why should we believe your map?". It
scores the modelled hazard against the **observed** July 2021 flood extent and
returns three numbers, every one of them `None` rather than `0.0` when its
denominator is empty:

| Metric | Reads as |
|---|---|
| `hit_rate` | of the water that really came, how much did the model find? |
| `false_alarm_ratio` | of the water the model claims, how much was not there? |
| `iou` | the two together, in one number |

Everything is resampled onto **EPSG:3035 at 20 m**, the finer of the two inputs.
Coarsening the observed layer to ~90 m instead would erase exactly the narrow
urban strips the 2021 event is remembered for. `MIN_OBSERVED_CELLS = 25` is the
floor below which a unit is not scored at all — 25 cells at 20 m is one hectare,
and a hit rate computed on three pixels is noise with a decimal point.

On this laptop Belgium is the one place with observed extent from more than one
source, so the kit's validation runs there. The case itself is the July 2021
flood in Belgium, Germany and the Netherlands, and the organisers' bucket holds
Copernicus EMS extents for all three (Annex 2: 4 Belgian, 22 German and 1 Dutch
products); the EU-wide NUTS3 work is the context around that core.

**What the ground truths on disk can and cannot score.** The EMSR517 package
`config/sources.yaml` declares for the kit's own validation is AOI01, the
Trier/Mosel area south of the Ahr, with about 0.28 km² observed, and the JRC
observed-depth file, whose footprint does reach the Ahr, flags only about
0.35 km² flooded there. So `scripts/validate_2021.py`, which reads those files,
scores Belgium only. The event pipeline below closes that gap from the
organisers' bucket: it measures all 27 EMS products (4 Belgian, 22 German,
1 Dutch), with the hit rate, false alarm ratio and CSI per product and per
return period in `event_2021_hazard.parquet`. The Ahr place the policy tool
leads with is `EMSR517_AOI15`, Bad Neuenahr-Ahrweiler (AOI03, Hönningen, also
covers the Ahr; country totals count the overlap once). Inside Wallonia the choice of truth
moves the score on its own: the IDW depth raster (about 77 km² with depth > 0)
and the extent layer (about 521 km², of which only about 53 km² carry a `SCENARIO` zone name) give hit rates about
2.1× apart for the same *aléa* mask (0.728 against 0.343) and 3.3× apart for
JRC RP100 (0.605 against 0.183), and the Walloon *aléa* map carries a fourth
class, 101/201/301 *très faible*, that a class mask either includes or not. Each
hit rate is quoted with the truth it was scored against and the classes in the
mask (see `docs/datasets.md`).

`scripts/validate_2021.py` is the run that does this, with windowed reads only:
a 20 m EPSG:3035 grid over the Walloon depth raster's footprint (4.18–6.06 °E,
50.10–50.75 °N) and one over the Ahr, where only the JRC observed layer reaches.
It scores JRC RP10/RP100/RP500 and the *aléa* map (once with *très faible*, once
without) against all four truths — JRC observed, Walloon depth, Walloon extent,
EMSR518 inside its AOIs — and the truths against each other, each pair over the
truth's domain and the map's coverage only, permanent water dropped. It writes
`data/processed/validation_2021.parquet`, one row per (window, model, truth) with
the matrix, hit rate, false alarm ratio and CSI, and
`data/processed/validation_2021_population.parquet`: GHSL 2025 people (100 m
tiles, summed onto 5 × 5 scoring cells) inside each observed extent and outside
each map, in a conservative variant (a 100 m cell is inside the map when any
20 m sub-cell is wet) and an upper one (only when its centre sub-cell is).

`validate.py` derives no model domain from the hazard raster: its nodata is
every dry cell, so "not nodata" is the wet footprint. `agreement_by_unit` takes
`in_model_domain` only from an independent layer such as the EFAS upstream area.

### The July 2021 pipeline

The event is measured product by product, from the Copernicus EMS Rapid Mapping
products in the organisers' bucket (EMSR518 Belgium, EMSR517 Germany, EMSR520
Netherlands), each against the JRC hazard maps, GHS-POP E2020 and GHS-OBAT.

| Step | Writes | What it does |
|---|---|---|
| `scripts/event_2021.py` with `src/event2021.py` | `data/processed/event_2021_{products,hazard,buildings,damage,countries}.parquet` | Per EMS product, inside its AOI only: observed flooded area, hit rate / false alarm ratio / CSI per return period (`validate.agreement` on the 20 m EPSG:3035 grid), residents in the water and outside each hazard map, buildings by use, epoch and height, damage grades; then per country on the union of products, deduplicated cell by cell and building by building |
| `scripts/event_2021_infrastructure.py` | `data/processed/event_2021_infrastructure.parquet` | Roads and railways (km by class), power lines and dams (km), schools, hospitals, fire stations and power plants (counts), each in the whole AOI, inside the observed water and within 25 m of it; country rows merge lines and features so an overlap counts once |
| `scripts/build_policy_tool.py` with `src/policy_tool.py` | `docs/perso/policy_tool/policy_tool.html` and PNG snapshots (gitignored: the page carries GISCO geometry) | The challenge policy tool: one self-contained HTML file that opens offline and calls no AI service; story maps rasterised on the same 20 m grid the figures were counted on |
| `scripts/export_event_web.py` | `data/processed/event_2021_web.json` and `web/public/event_2021_web.json` | The React "July 2021" view's data, built with `src/policy_tool.py`'s figures and the policy tool's maps; public borders from Natural Earth; `--full` draws GISCO borders and NUTS3 lines into the gitignored `event_2021_web.full.json` only |
| `scripts/export_europe_web.py` | `web/public/europe/` (gitignored) | The static Europe view: the API's own answers to `/api/meta`, `/api/exposure`, `/api/context` and `/api/vulnerability`, frozen in-process; no geometry |

Three rules carry the figures. **The unit is one EMS product**, one AOI at one
date: a first delineation and its monitoring pass are separate rows, never
merged, since neither is the peak. **Outside an AOI nothing was mapped**, so a
cell there is unknown, not dry, and is never scored. **Residents are weighted by
the flooded share of each cell**: a 1 km cell 30 % under water contributes 30 %
of its people. The bucket is read once and cached under
`data/raw/challenge_2021/`, so a re-run with `--offline` needs no network.

---

## 6. The LLM layer: a workflow, not an agent

`src/workflow.py` is a LangGraph graph with **five nodes** — retrieve, refuse,
draft, verify, approve — and a human gate before anything is written.

| Guard | Value | Prevents |
|---|---|---|
| `RECURSION_LIMIT` | 8 | a graph that loops |
| `MAX_REDRAFTS` | 0 | more than one model call per run: a weak draft goes to the human flagged |
| `MIN_GROUNDING` | 0.7 | a draft that cites nothing |

**Verification is not an LLM call.** `src/rag.py` grounds every claim in the
policy corpus and refuses rather than inventing; the grounding score is computed
arithmetically over content words, not asked of a model. A model that marks its
own homework is not a check.

**Questions about the table are not answered by the model either.**
`src/nlquery.py` asks it for a JSON query spec in one call, refuses any column
or operator outside its whitelist, and lets pandas compute the rows. The model
never writes SQL or code that runs, and a spec that breaks a rule is refused
rather than retried.

The distinction from an agent is the point, and it is the one `docs/workflow.md`
argues at length: fixed nodes, fixed order, a bounded number of calls, and a
human who approves. Nothing here decides to do something that was not written
down in advance.

---

## 7. The test suite

**<!-- numbers:tests_collected -->1,095<!-- /numbers --> tests, offline**: no network, no model, no key. On 27 October 2026 the
full suite passed on Windows and in WSL2, nothing deselected.

The platform history matters more than any one run. On 12 October 2026, in WSL2,
every test then collected passed, while the same day Windows blocked `rasterio`
again. Re-run on 14 October 2026: still blocked on Windows
(the five raster modules, 59 tests, do not collect), and in WSL2 all 702 pass
once `test_climate.py`'s dry-run test stopped reading the CDS files already in
`data/` (`fetch_cds_member.py` now resolves `OUT_DIR` at call time). Re-run on
23 October 2026: rasterio imports on Windows again and every test collects and
passes there. Do not quote either as a property of the platform — Smart App Control moved to enforcement on 7 October
2026 and refused rasterio's unsigned DLLs, which left 433 collectable and 431
passing on Windows while WSL2 ran the lot; by the next morning it allowed the
same wheel again with nothing reinstalled. **The policy moves both ways, so
re-measure instead of citing either state**, and keep the WSL2 venv for the
mornings it flips back — see the note in `requirements.txt`. The suite mocks the network
away, which is exactly what hides a missing 300 MB raster — so
`scripts/check_offline_readiness.py` answers the question `pytest` cannot, in
byte counts, and exits 1 when the demo would still need a connection.

The count above is not typed: it sits in a `<!-- numbers:tests_collected -->`
block that `scripts/docs_numbers.py --write` fills from `pytest --collect-only`,
and `tests/test_docs_numbers.py` fails the suite when any marked block in the
docs disagrees with the repository. Edit the prose, never the digit.

Per-file counts measured 27 October 2026 with
`pytest --collect-only -q -p no:cacheprovider | grep '::' | cut -d: -f1 | sort | uniq -c`;
they sum to the marked total above. Forty-nine files. Typed counts go stale:
an earlier table listed twenty-two files summing to 473, and the next one
forty-three summing to 989 while the suite held 1,090.

| File | Tests | Guards |
|---|---|---|
| `test_nlquery.py` | 60 | natural-language questions over the table: the spec whitelist, unknown columns and operators refused, one period, nulls counted as not measured, one model call and no retry |
| `test_offline_readiness.py` | 56 | the demo runs with the Wi-Fi off: the three verdicts, `--strict`, a rejected file is not present, the two caches `src.fetch` does not fill |
| `test_validate.py` | 54 | the scoring grid, the three metrics, `None` vs `0.0`, no model domain read off the hazard raster's nodata |
| `test_validate_2021.py` | 15 | the windowed 2021 validation script: a pair scored over truth domain and map coverage only, the très faible choice made at the call, cell-centre rasterisation, the two population variants in order, population resampling that keeps its total |
| `test_api.py` | 82 | the routes, the 404s that name their builder, the JSX guards, a table frozen before the units rename, the approve token and the bounds on `k` |
| `test_streamlit_app.py` | 67 | the fallback UI, a ranked chart ordered by its value, the translation and ask-the-table tabs, the climate and coverage caveats, the density, income and Natura 2000 sections, a rebuilt table replacing the cached one, a table frozen before the units rename |
| `test_fetch.py` | 62 | robots, idempotency, a single declared source for the hosted app, multi-file expansion, a stale rejection page is quarantined, colliding paths are refused, the cited policy sources are declared and every corpus file lands in a format the index reads |
| `test_rag.py` | 80 | cite-or-refuse, and a fence no spelling of the closing tag escapes |
| `test_losses.py` | 29 | the RDH euro vintages and the levelling |
| `test_basins.py` | 31 | the shared-basin layer: the declared crosswalk, the sliver floor, the basin names, shares that stop at 1.0 |
| `test_exposure.py` | 25 | the two modes, `nodata_means_dry`, the masks, the build checkpoint |
| `test_workflow.py` | 27 | the five nodes, the guards, the human gate |
| `test_climate.py` | 33 | the future layer: provenance, the median, the ensemble and its quartiles, a member per simulation, the fetcher against a mocked CDS |
| `test_vulnerability.py` | 21 | the composite index, its sensitivity, and what one indicator cannot prove |
| `test_rdh.py` | 16 | the paged client and its cache |
| `test_toon_io.py` | 15 | the compact table encoding for prompts, and a tokenizer that cannot fetch its table says so |
| `test_mcp_server.py` | 12 | the three intent-based MCP tools and their flat TOON answers |
| `test_apsfr.py` | 13 | the two reporting cycles, the dissolve, the claim it must not make |
| `test_svgmap.py` | 22 | the offline choropleth: quantile classes, signed classes anchored on zero, holes kept, the outermost regions out of the extent, a hatch whose label names the sign rule that drew it, a legend that names its sixths and stays inside the viewBox |
| `test_demographics.py` | 21 | the sparse cube, the overlapping age buckets, the NUTS2 caveat, the unit in the name and the legacy names, a thinly published newest year, density and income pinned to their units |
| `test_translate.py` | 34 | a translated figure never moves |
| `test_events.py` | 11 | the coverage blind-spot probe |
| `test_stripes.py` | 9 | the figure does not depend on the window count |
| `test_environment.py` | 17 | Natura 2000 on flood-prone ground: the union not the sum, true cell areas, the masks, window-size invariance, not measured is not zero |
| `test_assets.py` | 8 | the built-up surface: the archive, the unit, the share |
| `test_docs_numbers.py` | 10 | a number typed in a doc that no longer matches the code fails the suite |
| `test_legislation.py` | 7 | every legal citation has a CELEX and a URL, and `policy_answer.md` cites no article the registry lacks |
| `test_build_context.py` | 7 | the context build does not fail after writing its table; residual columns per return period, NaN not 0; `--only` replaces one layer and keeps the rest; a reordered table is refused |
| `test_protection.py` | 6 | the residual reading: held up to the design standard and not beyond, unknown is never protected, parked and written apart from the undefended table |
| `test_facilities.py` | 7 | hospitals and schools: the 0.5 m threshold, the masks, unknown protection never holds, one region per facility, an uncovered country is not measured |
| `test_build_geometry.py` | 9 | the join key, the projection, the simplification, the hosted app's download-and-build |
| `test_export_bi.py` | 28 | the Power BI export and report: the EU-27 headline unchanged, the TMDL columns equal to the CSV, no sum across return periods, every field a PBIR file names exists in the model, every project JSON file valid against Microsoft's schema, the drill-down hierarchy and the drillthrough binding |
| `test_hera.py` | 25 | the HERA peak-discharge trend: the streamed annual maximum, Sen's slope and Mann-Kendall, an incomplete year never cached, no river cells is NaN not 0, peak timing read on a circle (no jump where the year is cut, NaN when peaks fall in any season), a resumable download |
| `test_pluvial.py` | 18 | the ECDE heavy-precipitation and flood-recurrence layers: a NUTS2 figure is not a NUTS3 one, unmatched is not "no change", no ensemble mean, the CDS key never printed |
| `test_sealing.py` | 13 | sealed soil, HERA 1 arcmin and CLMS 100 m: true cell areas, off the grid is not unsealed, a percentage is not a fraction, tile-size invariance, 254 is unclassifiable |
| `test_efas.py` | 13 | the July 2021 return levels: the exact level picked, the river-cell filter, NaN outside the box, a fetch without a key or licence fails clearly |
| `test_cems_activations.py` | 5 | the CEMS activation summary: a wildfire is not a flood, a multi-country activation counted once, pagination, the cache |
| `test_landcover.py` | 3 | CORINE in the flood footprint: the class groups, footprint cells only, masked water out, NaN not 0 |
| `test_data_io.py` | 3 | the CRS engine is alive |
| `test_sources_ground_truths.py` | 8 | the catalogue's July 2021 ground-truth claims: EMSR517 AOI01 is Trier/Mosel, not the Ahr; the cross-border claim stops at Belgium; the *très faible* class is declared; the two Walloon truths state their areas and disagreement |
| `test_rainfall.py` | 8 | the July 2021 EMO-1 event rainfall: only the window is summed, a gap is refused, a cell missing a day is NaN not drier, a region holding no cell centre is NaN not 0 mm |
| `test_docs_citations.py` | 6 | every docstring a doc cites by name exists in the cited module |
| `test_climate_rules.py` | 5 | the two climate reading rules: the 80 % sign column when present, the interquartile spread at sixteen members and the full range at two, both sign counts in the period summary |
| `test_event2021.py` | 18 | the July 2021 products on synthetic data: which bucket folders count as products, half a flooded cell is half its people, permanent water out of the score but not the headcount, an overlapping product counted once per country, one product end to end |
| `test_event2021_infrastructure.py` | 13 | the July 2021 roads, networks and services: a class from the EMS `info` code, km on the ground and once per segment, a feature counted once with its most severe grade, nothing outside the AOI |
| `test_export_event_web.py` | 16 | the React app's July 2021 JSON: the contract keys, every number the policy tool's, missing is null never zero, no GISCO line in the committed file, `--full` goes to an ignored file only |
| `test_export_europe_web.py` | 11 | the static Europe view's frozen answers: the file names and subset keys the client looks up, no geometry written, every indicator subset ranked at the panel defaults |
| `test_hosted.py` | 16 | the hosted-demo switch: every model or write route answers 403 before any provider is reached, the spec form still answers, `/api/config` reports the mode, `/api/event2021` serves the file as is and never the full build when hosted |
| `test_policy_tool.py` | 20 | the single-file policy tool: no network reference, no external script or AI call, hero and place numbers equal to the tables, NaN printed "n/a" never 0, honest rounding, no names beyond "Team N" |

**Screenshots are a script, not a chore.**
`scripts/screenshots/take_screenshots.ps1` starts Streamlit, the API and the
React dev server on their own ports (8599, 8099, 5199, so a demo already
running is never touched), drives every tab of both UIs with Playwright in
headless Chromium, writes `docs/screenshots/*.png` and stops what it started -
about two minutes. Headless because it is reproducible: re-run it after any
change to the UI instead of re-taking screenshots by hand. Draft, Ask and
Translate are captured empty on purpose, since filling them calls a model.

`test_data_io.py` earns its three tests: a dead `pyproj` is the silent failure in
this stack. `geopandas` still imports, `GeoDataFrame(..., crs=...)` still returns
an object, and only a `UserWarning` says the CRS was dropped — after which every
zonal statistic is the right arithmetic on the wrong piece of Europe. Measured on
6 October 2026, the whole suite passed with `pyproj` stubbed out. Now it does not.

---

## 8. Where the numbers in this file come from

| Claim | Source |
|---|---|
| <!-- numbers:tests_collected -->1,095<!-- /numbers --> tests | `scripts/docs_numbers.py --write`, which runs `pytest --collect-only` and rewrites the marked blocks; the per-file counts are typed by hand |
| 85 files | `src.fetch.expand()` over the mirrored entries of `config/sources.yaml` (57 geodata, 25 policy_corpus, 3 context), 27 October 2026 |
| ≈6.96 GiB on disk | measured 25 October 2026 with the 84 files then declared all present; not re-measurable on a machine without the full download |
| <!-- numbers:sources_declared -->79<!-- /numbers --> declared inputs, <!-- numbers:sources_verified -->71<!-- /numbers --> with a verification date, <!-- numbers:sources_licensed -->39<!-- /numbers --> with an explicit `licence:` | `scripts/docs_numbers.py` over `config/sources.yaml`: entries with an `id`; `verified` not null; `licence` non-empty |
| 1,345 NUTS3 polygons | the GISCO NUTS 2024 file itself |
| the 0.25% stripe discrepancy | two continental RP100 builds, 6 October 2026 |
| 4.85% of cells carry a value | a 1,468,800-cell window of Belgian land, RP100 |
| the permanent-water figures | the Benelux at RP10 and RP100 |

**One caveat on the Benelux figures.** 5,065,526, 4,344,955, 13,771,935 and the
ratios drawn from them were all measured **before** the windowing fix of
6 October 2026, on a build whose answer depended on its stripe count. They are
kept because the comparisons they support — sparse-vs-AOI, masked-vs-unmasked —
are ratios between two runs of the same code, and those survive. The absolute
counts do not: re-derive any of them before putting it in a brief.

Re-derive rather than quoting this table. Every number above is a reading of the
repository at a moment, and the repository moves.
