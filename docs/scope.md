# Scope: a funnel, from July 2021 to Europe

The scope is a **funnel**. At its core is the **July 2021 flood in Belgium,
Germany and the Netherlands**: the organisers' data (Annex 2) is about that
event, and the data questions Q1 and Q3 will be answered on it. Around it sits
the kit's **EU-wide** work, which answers the question a jury asks next, *is
this a one-off?*, and gives the recommendation its scale and its named actor:
25.7 million EU-27 residents in the undefended 1-in-100 footprint, risk-area
declarations that cannot be compared between Member States, and the climate
projections ([`policy_answer.md`](policy_answer.md)). The European work is not
dropped; it moves from the centre to the context, which is also where a
comparison between countries earns its place.

This page is the design that follows from that, and it is the reason the data
choices differ from an obvious Belgian pipeline.

## The unit of analysis: NUTS3

| Level | Count (EU) | Use it for |
|---|---|---|
| NUTS0 | 27 | A headline for the brief's first line |
| NUTS2 | ~240 | Where Eurostat income and poverty data lives |
| **NUTS3** | **1,165** (1,345 in the GISCO file, incl. EFTA + candidates) | **The working unit: provinces/arrondissements** |
| LAU | **95,066** (97,987 in the GISCO file, incl. EFTA + candidates) | Only for a zoom-in on one named valley |

**NUTS3 is the right default.** It is fine enough to rank and to map
meaningfully, coarse enough that a pan-European run finishes in minutes, and it
is the level EU regional policy actually operates on — a jury of JRC staff thinks
in NUTS.

Drop to LAU only for the worked example (one valley, one country). Stay at NUTS3
for anything you present as a European finding.

## What the NUTS3 choice produces on disk

Three files, all derived. Since 2026-10-23 both frozen tables are committed, so a
fresh checkout has the frozen figures; the geometry is not (its GISCO boundaries
carry their own terms, see `data/processed/DATA_NOTICE.md`) and is built in
seconds from the fetched boundary file. Until it exists the React choropleth
renders nothing while reporting no error at all.

| File | Built by | Holds |
|---|---|---|
| `data/processed/exposure.parquet` | `python scripts/build_exposure.py` | one row per region x return period |
| `data/processed/context.parquet` | `python scripts/build_context.py` | one row per region: every layer that is not exposure |
| `data/processed/regions.geojson` | `python scripts/build_geometry.py` | the polygons the choropleth draws |

They are separate on purpose: the exposure table is a multi-hour continental run
over the hazard rasters, the geometry is seconds over one 25 MB boundary file,
and re-running the slow one to redraw the map would be absurd. They join on the
region identifier — `nuts_id` here, `lau_id` for a LAU zoom — which is why
`build_geometry.py` renames GISCO's `NUTS_ID` rather than passing it through.

The geometry is simplified to 1 km, in EPSG:3035 so that the tolerance is a real
distance. That is below one screen pixel at a continental viewport, and it takes
the file from 25 MB to under 3 MB. Lower it for a single-country zoom, where the
viewport is roughly twenty times tighter.

## What this changes about the data

### Population: 1 km, not 100 m

`GHS_POP_E2025_GLOBE_R2023A_54009_1000_V1_0.zip` — **323 MB, one global file,
verified downloadable**. At NUTS3, where a region is hundreds of km², 1 km
population is entirely adequate, and it removes the whole tile-mosaicking problem
(Europe spans roughly two dozen 100 m tiles, with the trap that the row boundary
cuts through countries).

Keep the 100 m tiles only for the zoom-in.

### Boundaries: GISCO NUTS, not national sources

`NUTS_RG_01M_2024_3035_LEVL_3.geojson` (25,247,626 B) or the same layer as a
shapefile, `NUTS_RG_01M_2024_3035_LEVL_3.shp.zip` (7,324,754 B) — both measured
by `Content-Length` on 6 October 2026. The GeoJSON is what `sources.yaml`
declares, and it is the larger of the two by a factor of three: that is the
format's text encoding, not more detail. EPSG:3035, one file, every country, one
vintage. Statbel, the Walloon geoportal
and their equivalents are national: useful for validating one country, useless
for comparing twenty-seven.

**Pin the vintage and say which.** NUTS 2021 and NUTS 2024 are different
geometries *and* different code sets.

### Demographics: Eurostat, not Statbel

The equity lens has to work in every country, so it has to come from one
harmonised source:

| Need | Eurostat dataset | Level | State |
|---|---|---|---|
| Population by age | `demo_r_pjangrp3` | NUTS3 | Declared and read; checked live 2026-10-06 (BE332 total = 637,220). `share_over_65` in `exposure.parquet` |
| At-risk-of-poverty rate | `ilc_li41` | NUTS2 | Declared and read; checked live 2026-10-06 (BE33 = 14.6). `poverty_rate` in `exposure.parquet` |
| GDP | `nama_10r_3gdp` | NUTS3 | Declared and read; checked live 2026-10-06 (BE332 = 26,435.29 MIO_EUR, flagged provisional). `gdp_meur` in `context.parquet`, read from 2023 by the coverage rule below (BE332 = 25,450.93) |
| Population density | `demo_r_d3dens` | NUTS3 | Declared and read; checked live 2026-10-12 (BE332 = 808.5 per km2, 2024). In `context.parquet` |
| Disposable household income | `nama_10r_2hhinc` | NUTS2 | Declared and read; checked live 2026-10-12 (BE33 = 21,300 PPS per inhabitant, 2023). In `context.parquet` |

On the GDP endpoint, **pin the unit**: `MIO_EUR`, `MIO_PPS` and `EUR_HAB` are
three different numbers, mixing them is silent, and recent years carry a
provisional flag that has to be read rather than dropped. The income cube is
worse - five units and thirteen national-accounts items under one code - so
`src/demographics.py` pins `B6N`, `BAL` and `PPS_EU27_2020_HAB`, and the unit is
in the column name. Density and income are **context, not indicators**: they
qualify a region without making a resident more vulnerable, so they live in
`context.parquet` where the index cannot scan them, and adding either to the
index is a weighting decision for a human.

Each column is read from ONE year: the newest one Eurostat has substantially
published (at least 90 % of the regions the year before it covers). The newest
year with any value is often a fraction of the map - GDP 2024 covers 536 NUTS3
regions, 2023 covers 1,307.

Income and poverty are published at NUTS2, not NUTS3. So a vulnerability index
mixing both levels must **say** that the income component is NUTS2 applied to its
NUTS3 children — an assumption that is defensible and must be stated, not hidden.

Access through the Eurostat API (`ec.europa.eu/eurostat/api/dissemination/...`),
which is open and needs no credentials.

### Hazard: unchanged

The JRC maps already cover Europe — that is what they are. Nine return periods,
272–350 MB each, measured 2026-10-06. Downloading all nine is **2.61 GiB**, and
the whole `geodata` section — 51 entries, 111 jobs once the multi-file ones are
expanded: 57 files to download, 19 runtime API calls, and 35 files under six
`folder` entries that `src.fetch` skips (30 HERA files that
`scripts/fetch_hera.py` fetches, and the five `challenge_*` folders of the
organisers' bucket that `scripts/event_2021.py` reads) — and the full fetch
including the policy corpus (25) and context (3) is **85 files**. The 84 then
declared measured ≈6.96 GiB on disk on 25 October, all fetched that day; the
85th, `natural_earth_countries` (4.9 MB), came on 26 October. The counts come
from `src.fetch.expand()` over `sources.yaml` as it stood on 27 October 2026,
so re-derive them rather than quoting this paragraph.

**At European scale the whole-file download is not a convenience, it is the only
option.** The files are tiled and range-readable, so `/vsicurl/` looks like it
should save the download. Measured on RP100: a Belgium window is 220 tiles and
2.4 MiB over the wire, but the EU27+EFTA bbox is 35,525 tiles and 172 MiB — 56%
of the file, in tens of thousands of requests, which at one request per second
per host is hours per return period. So `/vsicurl/` belongs to the Belgian
rehearsal; the European run reads local files.

## The alignment problem, and the honest way through it

The hazard is 3 arc-sec in EPSG:4326. Population is 1 km in Mollweide. Different
CRS, different resolution, different grid origin.

**The rule does not change: never resample the population counts.** So:

1. Threshold the hazard into a 0/1 wet mask **first**, at its own resolution.
2. Resample that mask onto the population grid with `average`, which gives the
   **fraction of each 1 km cell that is flooded** — a number in [0, 1].
3. `exposed = population × fraction_flooded`.
4. Zonal-sum per NUTS3 region.

Thresholding before averaging matters: averaging depths and thresholding after
answers a different question (*is the mean depth above the threshold?*) and
systematically under-reports small deep floods.

At 1 km with a 3 arc-sec input there are roughly **185** hazard cells per
population cell at Belgian latitudes, so the fraction is well resolved. The
figure is latitude-dependent, because a 3 arc-sec cell keeps its ~92.6 m
north-south height but its east-west width is 111,320 m × cos(latitude) / 1,200:
~58 m at 51°N for 5,407 m² and 185 cells per km², falling to ~142 cells at 35°N
and rising to ~275 at 65°N. Even the coarsest European case resolves the
fraction to better than a percent, which is the point; the exact number is not a
constant and should not be quoted as one. This is the step to explain if the jury
asks how you combined two incompatible grids.

## What a European scope buys you in the brief

A finding on the July 2021 event alone describes one flood. The European context
around it supports a comparison, and comparison is what a Commission audience
acts on:

- **Which regions carry the most exposure per inhabitant**, not in absolute
  terms — absolute counts just rank by population and tell you nothing.
- **Where exposure and vulnerability coincide**, which is not where either is
  highest alone. This is the equity reading FARI's common-good remit points to
  (the call itself asks for exposed populations, not equity), and it is a genuinely
  European question.
- **Cross-border river basins**: the Meuse runs through France, Belgium and the
  Netherlands. A flood does not stop at NUTS boundaries, and pointing that out
  is an argument for EU-level action rather than national action — exactly the
  kind of conclusion this jury exists to hear.
- **Who is already covered by insurance and who is not** — the protection gap
  varies enormously across the EU, and that variation is a policy lever.

## Belgium: the validation inside the core

Use the Vesdre valley and EMSR518 to check the model first: it is the
only place where the **observed** flood extent on disk comes from more than one
source (see below), so the ground truth can be checked before the modelled
hazard is scored against it. It is not the only observed extent on disk: the
JRC satellite depth map of the July 2021 event flags about 148 km² in the
Netherlands and 85 km² in Germany against 23 km² in Belgium (counted against the
NUTS3 polygons), but only about 0.35 km² over the Ahr, and the one German
Copernicus package `src.fetch` downloads, EMSR517 AOI01, covers the Mosel with
about 0.28 km² observed, not the Ahr. The organisers' bucket carries the rest:
`scripts/event_2021.py` measures all 27 Copernicus EMS products of the event
(Belgium 4, Germany 22, Netherlands 1; the Ahr is EMSR517 AOI15), inside their
areas of interest only. At RP100 the JRC extent contains 0.84 of the observed
water on the Belgian first maps, 0.57 on the German ones and 0.93 on the Dutch
one, and 0.62 on the Ahr's first map, where 51 % of the 3,739 residents reached
lived outside it (`data/processed/event_2021_countries.parquet` and
`event_2021_products.parquet`, built 26 October). That is the methods result to
carry into the analysis — "we checked the model against the 2021 observations
and it misses X" — with its limits in
[`limitations.md`](limitations.md#1-what-the-figures-cant-say).

Belgium is also the one place on disk with **two independent observations** of the same
flood: Copernicus EMSR518 (four packages — a first delineation *and* a monitoring
pass per AOI, so the largest extent rather than the earliest) and the Walloon
administration's own July 2021 layers, one extent and one IDW-interpolated depth.
Scoring the two observations against each other first gives the uncertainty of
the ground truth, which is what makes "the model misses X%" a defensible number
instead of an artefact of one delineation.

One conversion to get right before any of that: the satellite-derived depth maps
are in **centimetres** and the hazard maps in **metres**. The validation is a
depth comparison, so this is exactly where a factor-100 error would hide behind a
plausible result.
