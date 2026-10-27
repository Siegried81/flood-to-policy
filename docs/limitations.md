# Limitations: what the kit does not claim

The kit is a ten-day build on open data. Three dates are in play:
`exposure.parquet` was last built on 2026-10-07 (nine return periods; see
[`data/processed/DATA_NOTICE.md`](../data/processed/DATA_NOTICE.md)), the European
figures were read off it as the measured base of 2026-10-08
([`policy_answer.md` §3](policy_answer.md#3-the-measured-base-2026-10-08)), and
`context.parquet` has been rebuilt layer by layer since (the full climate ensemble
on 2026-10-25); the July 2021 tables were built on 2026-10-26, and their infrastructure table (`event_2021_infrastructure.parquet`) on 2026-10-27. This page gathers
in one place what its figures cannot support, what was designed and not built,
what a public authority would still have to do before acting on it, and the
shortcuts accepted to ship it. Every bullet points at the file that holds the
reasoning and the measurement; this page quotes the bounding number and nothing
more, so re-derive from the source rather than from here when the parquets are
rebuilt. The findings and recommendations themselves are in
[`policy_answer.md`](policy_answer.md).

## 1. What the figures can't say

**The July 2021 Copernicus figures**

The core of the case: water, residents, buildings and infrastructure per
Copernicus EMS Rapid Mapping product (EMSR517 Germany, EMSR518 Belgium, EMSR520
Netherlands; 27 products, 4 Belgian, 22 German, 1 Dutch).

- **A snapshot, not the peak.** Each product is the water visible on one image, often a day or more after the crest. The first map
  (`PRODUCT`) and each monitoring pass (`MONIT01`) are separate rows, never merged
  into one extent; the true extent was larger than either.
  [`src/event2021.py`](../src/event2021.py) module docstring.
- **Outside an AOI is "not mapped", not dry.** Every figure is computed inside the
  product's area of interest only; whole flooded valleys lie outside them, and a
  cell outside is unknown, never a false alarm for the hazard map.
- **Radar delineations stop at walls, so the Belgian building count is a floor.**
  The delineation (`DEL`) products are drawn semi-automatically from radar and
  miss the water between houses; the grading (`GRA`) products, photo-interpreted,
  carry it through the streets. Belgium has delineations only: on EMSR518 AOI01
  (Liège) 138 GHS-OBAT buildings lie inside the first map's water and 369 within
  25 m of it, so `buildings_within_25m_of_observed` travels beside the count.
- **Two population grids.** The event is counted on GHS-POP E2020 (30 arc-seconds,
  as Annex 2 of the challenge asks); the European figures on GHS-POP E2025 at 1 km.
  The two never enter one sum.
- **Never say "homes destroyed".** Copernicus's building classes
  (`11-Residential` / `12-Non-residential`) are not consistent between passes: on
  the Ahr's first map (EMSR517 AOI15) 273 of the 336 buildings graded destroyed
  are classed non-residential, against 15 of 753 on its monitoring pass. Say
  "buildings graded destroyed", and only for the German grading products.
- **Infrastructure "in the water" means crossing the observed polygons.**
  `scripts/event_2021_infrastructure.py` reads the products' road, railway,
  network and service layers; for a delineation those layers are the AOI's
  reference map, not a damage statement, so a road counts only where its line
  crosses the observed water (a 25 m scope is kept beside it, for the same walls).
  A grading product's per-feature damage grade is the analysts' own statement.
  [`scripts/event_2021_infrastructure.py`](../scripts/event_2021_infrastructure.py)
  module docstring.

**The hazard**

- **River flooding only.** The JRC maps model fluvial flooding for basins above
  about 150 km2 and contain no surface runoff, which was a large part of what
  happened in Wallonia in July 2021. A region the model ranks low may still have
  flooded. The organisers' Data Catalogue says 500 km², which describes an older
  edition; in the v3.1.1 files RP500 depth appears in about 98 % of river cells
  at 150-500 km² upstream area against 12-20 % below 150 km² (checked 26 October
  2026). [`policy_answer.md` §9](policy_answer.md#9-what-this-document-does-not-claim),
  [`src/events.py`](../src/events.py) module docstring.
- **No dykes in the water.** The JRC maps leave out local flood defences, so
  every headcount in `exposure.parquet` is UNDEFENDED, two orders of magnitude
  above the JRC's defended, probability-weighted "about 160,000 people exposed
  each year". Quote it with the residual figure behind the design standards,
  `residual_exposed_pop_rp*` in `context.parquet`: how both are built is in
  [`technical_deep_dive.md` §3.6](technical_deep_dive.md#36-undefended-and-residual-the-dykes-the-maps-leave-out).
  Dottori et al. 2022 (`jrc_hazard_maps_validation_essd_2022` in the corpus)
  find the maps reproduce about two-thirds of the reference flood extent and over-estimate it below RP100.
- **Nine scenarios, never a sum.** The return periods are nested extents: EU-27
  exposed population reads 16,704,818 at RP10, 25,737,004 at RP100 and
  30,730,197 at RP500. A headcount quoted without its return period is not a
  number. [`policy_answer.md` §3](policy_answer.md#3-the-measured-base-2026-10-08),
  [`geospatial_crash_course.md`](geospatial_crash_course.md#return-period-what-a-100-year-flood-is-not).
- **Nested in intent, not cell by cell.** Each JRC depth raster is a separate
  model run, so a rarer period can be shallower in places. Measured 2026-10-23
  on the frozen table: 8 of the 10,704 measured period-to-period steps (1,345
  regions x 8, less the steps where a period has no figure) lose people, in 4 regions. FRG01 (Loire-Atlantique) reads 96,027 at
  RP100, 81,171 at RP200 and 75,408 at RP500; FRD22, DE927 and RS211 also dip.
  Totals at EU scale still grow with the period; never claim that every
  region's does.
- **The depth threshold is a choice, and it moves the headline.** The build
  counts a cell as flooded above 0.5 m, and masks permanent water bodies and the
  JRC's own spurious-depth areas; on the Benelux the water-body mask alone moves
  the RP100 figure by -14.2 %. The threshold is one of the four things the AI
  was not allowed to decide.
  [`technical_deep_dive.md` §3.5](technical_deep_dive.md#35-what-is-masked-out-and-why),
  [`responsible_ai.md`](responsible_ai.md#say-what-ai-must-not-decide).

**The exposure count**

- **`exposed_pop` carries an extrapolation; `exposed_pop_observed` does not.**
  Where the hazard layer covers only part of a region, the figure is scaled onto
  the whole unit by people (`x pop_total / pop_observed`), never by a cell-mean
  of coverage. At RP100, 7 of 1,345 regions carry no measured figure at all and
  11 have `hazard_coverage` below 1.0; report that column beside every count.
  `exposed_pop_observed` is what the build sums; the frozen table keeps only
  `exposed_pop`.
  [`technical_deep_dive.md` §3.3-3.4](technical_deep_dive.md#33-four-columns-and-why-none-is-not-00),
  [`src/exposure.py`](../src/exposure.py) `exposed_population` docstring,
  [`policy_answer.md` §3](policy_answer.md#3-the-measured-base-2026-10-08).
- **A population cell is wholly in or wholly out of a region.** The induced
  error scales with perimeter over area: around 1-3 % for a commune and 30-50 %
  for a Belgian statistical sector. Nothing smaller than a commune should be
  read off this pipeline. [`src/exposure.py`](../src/exposure.py) module
  docstring.
- **Which Europe.** The GISCO NUTS 2024 file holds 1,345 NUTS3 polygons, of
  which 1,165 are EU-27, 46 EFTA and 134 candidate countries. The usual "1,166"
  is the NUTS 2021 count. Every headline says which denominator it uses.
  [`scope.md`](scope.md#the-unit-of-analysis-nuts3), root
  [`README.md`](../README.md).
- **Built-up surface is square metres of footprint, not value.** A warehouse
  and a hospital of the same size are the same number; monetising it needs
  damage curves the kit does not carry. [`src/assets.py`](../src/assets.py)
  module docstring.

**The Member States' own declaration**

- **`apsfr_share` is comparable within one country and never between two.**
  The Floods Directive leaves the geometry convention national: the declared
  share of territory runs from 99.908 % (BE) to 0.004 % (ES, CY), a factor of
  23,095, and the shape index separates zones (1.5 for BE and HR) from river
  reaches drawn as ribbons (51 for DE, 74 for LU). Any cross-country ranking of
  the share ranks reporting styles. [`src/apsfr.py`](../src/apsfr.py) module
  docstring, [`policy_answer.md` §4.1](policy_answer.md#41-the-member-states-own-risk-declaration-is-not-comparable-between-them).
- **An undeclared area is not an under-declared one.** A State may have
  assessed an area under Article 4 and found the risk not significant, which the
  Directive permits; the kit shows the gap and leaves the conclusion to a human.
  [`src/apsfr.py`](../src/apsfr.py), [`policy_answer.md` §9](policy_answer.md#9-what-this-document-does-not-claim).
- **Two EU-27 Member States are absent from the layer.** Pinning the 2018 cycle
  (12,173 polygons, 25 countries) drops Lithuania, which reported in 2010 only;
  Ireland appears in neither cycle. Any pan-European APSFR statistic silently
  omits both. [`policy_answer.md` §4.2](policy_answer.md#42-two-eu-27-member-states-are-absent-from-the-commissions-own-layer),
  [`datasets.md`](datasets.md#eea-floods-directive--areas-of-potential-significant-flood-risk--verified-live--and-three-traps).

**The cross-border figure**

- **"Shared" is not "upstream".** The WFD districts are catchment boundaries
  with no flow topology, so the kit can say a region's basin lies in more than
  one country and nothing about direction. [`src/basins.py`](../src/basins.py)
  module docstring.
- **57.0 % of exposed people in a shared basin (63 % over the EU-27) is a
  floor, twice over**: non-EU riparian States do not report under the WFD, and
  districts the crosswalk cannot group
  stay national. [`policy_answer.md` §4.3](policy_answer.md#43-most-of-europes-exposed-population-is-downstream-of-someone-else),
  [`datasets.md`](datasets.md#the-limit-that-matters-a-district-is-a-national-portion),
  [`config/international_basins.yaml`](../config/international_basins.yaml).

**The future layer**

- **Medians and quartiles, never a mean or a maximum.** A relative change
  against a near-zero reference discharge is unbounded: on the real file the
  maximum is +16,452,833 % against a median of +16.9 %.
  [`src/climate.py`](../src/climate.py) module docstring.
- **Sixteen model chains, one emissions pathway.** The frozen `context.parquet`
  is built from the eight simulations the CDS dataset offers under RCP 8.5,
  each through E-HYPEgrid and VIC-WUR (16 members, since 2026-10-25). RCP 4.5
  is not in the ensemble, and neither is any warming-level period; the
  warming-level columns beside it (`ecde_flood_*`, `pluvial_*`) come from the
  separate C3S ECDE dataset. At least 80 % of the members
  agree on the sign (the IPCC AR6 "robust" rule) in 353, 728 and 846 of 1,345
  regions for the three horizons; all 16 agree in only 20, 145 and 239. The
  first count is the one quoted, the second travels beside it, and one member
  never counts as agreement with itself. Eight simulations are what the dataset
  offers, not a designed sample of climate models, and the dataset is no longer
  maintained. Regions without a robust sign keep their colour on the map and
  are hatched, which is a third statement: measured, direction unsupported.
  [`datasets.md`](datasets.md#copernicus-cds--hydrology-projections--verified--and-unsupported),
  [`src/climate.py`](../src/climate.py) `ensemble_change_by_region` docstring,
  [`src/svgmap.py`](../src/svgmap.py) `choropleth_svg` docstring,
  [`policy_answer.md` §4.4](policy_answer.md#44-the-reference-discharge-is-rising-where-people-already-live-in-the-way).
- **The observed record does not yet show the projected rise.** In HERA v2
  (1991-2020), annual peak discharge fell in 727 of the 1,220 regions it
  covers (median −1.4 % a decade, EU-27 −1.8 %), in 428 of the 709 regions with
  river cells and a robust projected rise by 2041-2070, and in 42 of the 69 regions of the
  EU-27 planning list (47 of 80 over 37 countries); only 4.7 % of the 210,574 river cells rise significantly
  (Mann-Kendall, 5 %), and the rank correlation with the projected 2041-2070
  change is −0.01. HERA is a reanalysis forced by ERA5-Land, with reservoirs in
  it, not gauged flow, and 30 years is short. Say it as: the projection is a
  future RCP 8.5 signal that the last 30 years neither confirm nor contradict.
  [`src/hera.py`](../src/hera.py) module docstring,
  [`policy_answer.md` §4.4](policy_answer.md#44-the-reference-discharge-is-rising-where-people-already-live-in-the-way).
- **The planning list is read on undefended exposure.** Its 69 EU-27 regions
  hold 6,545,666 people exposed at RP100 if no dyke held but 865,518 behind the
  PESETA IV design standards; the same rule on the residual share gives 68
  regions with 2,634,226, and only 13 regions are on both lists. Quote both.
  Over all 37 countries the lists are 80 and 77 regions, 17 on both.
  [`policy_answer.md` §4.4](policy_answer.md#44-the-reference-discharge-is-rising-where-people-already-live-in-the-way).
- **It is discharge, not depth, and not a headcount.** A change in a 50-year
  flow cannot be layered onto the inundation maps; what travels is the direction
  and the size of the change. No future exposed-population figure exists in this
  kit. [`src/climate.py`](../src/climate.py) module docstring.

**Who is vulnerable**

- **The index is a value judgement wearing a number.** Weights are equal by
  default so that any other weighting is argued out loud; the ranking is never
  reported without its sensitivity under perturbed weights. Who gets protected
  first is a political choice the AI was not allowed to make.
  [`src/vulnerability.py`](../src/vulnerability.py) module docstring,
  [`responsible_ai.md`](responsible_ai.md#say-what-ai-must-not-decide).
- **Two indicators, two scales, and NUTS2 applied to NUTS3.** `poverty_rate_pct`
  is a Eurostat percentage (1.4 to 50.7) published at NUTS2 and applied to each
  NUTS3 child; `share_over_65` is a fraction (0.027 to 0.372). Since 2026-10-12
  the percentage says so in its name; an export from an older build, the frozen
  `exposure.parquet` included, still calls it `poverty_rate`. [`decisions.md`, 2026-10-08 "two indicators, two scales"](decisions.md#2026-10-08--two-vulnerability-indicators-keep-their-published-units),
  [`scope.md`](scope.md#demographics-eurostat-not-statbel).
- **Who is not in the data.** Undocumented residents, people in temporary
  housing and seasonal workers are absent from a residential population grid.
  The gap is stated, not estimated. [`strategy.md`](strategy.md#the-question-most-teams-will-not-ask),
  [`responsible_ai.md`](responsible_ai.md#what-to-write-under-each-concretely).

**Losses, validation and the model's blind spots**

- **No casualty or loss figure is official.** Risk Data Hub rows arrive once
  per administrative level, so an unfiltered sum of the July 2021 casualties
  reads 114.01 against 29.67 at any one level; the values are averages across
  DFO, EM-DAT and HANZE; and NUTS3 rows cover 84.3 % of the national total.
  [`src/losses.py`](../src/losses.py) module docstring,
  [`policy_answer.md` §9](policy_answer.md#9-what-this-document-does-not-claim).
- **Validation is one event, three countries, extent only.** `src/validate.py`
  scores the model against the observed July 2021 extent in Belgium at 20 m,
  refusing units under 25 observed cells, and `scripts/event_2021.py` scores it
  against all 27 Copernicus EMS products of the organisers' bucket, inside their
  areas of interest only (Belgium 4, Germany 22, Netherlands 1; the Ahr is
  EMSR517 AOI15, which AOI03 overlaps). At RP100 the share of the first maps'
  observed water that the model's extent contains (`hit_rate_rp100` in
  `event_2021_countries.parquet`) is 0.84 in Belgium, 0.57 in Germany and 0.93
  in the Netherlands (0.59 and 0.51 with the monitoring passes), and 0.62 on the
  Ahr's first map, where 51 % of the 3,739 residents reached lived outside the
  RP100 zone. The false alarm ratio is 0.89 to 0.94: a snapshot is not the peak,
  so it bounds nothing. The Walloon depth layer that would
  allow a depth-against-depth check is on disk only as a by-hand download (its
  declared URL answers HTTP 404 "Download Dataset Expired"), and
  `scripts/validate_2021.py` reads it only as an extent (depth > 0); no
  depth-against-depth check is built.
  Nothing validates the model outside those mapped areas, or for any other event.
  [`technical_deep_dive.md` §5](technical_deep_dive.md#5-validation-the-credibility-half),
  [`datasets.md`](datasets.md#wallonia-observed-july-2021--the-second-ground-truth--one-layer-verified-one-dead).
- **Reported events are a probe, never evidence.** News coverage is biased by
  attention, language and population; nothing from `src/events.py` enters a
  ranking or a headline. [`src/events.py`](../src/events.py) module docstring.

**The map and the text**

- **The colour classes are quantiles of what is present.** At RP100 the six
  bounds of the exposed share are 0.86, 1.95, 3.52, 5.66, 9.33 and 70.82 % over
  the EU-27 (1,159 regions with a figure; the UIs open on it) and 0.84, 1.90,
  3.39, 5.61, 9.22 and 70.82 % over all 37 countries (1,338); the legend prints
  them so the reader sees the classes are relative. Grey is "not measured", never zero.
  [`src/svgmap.py`](../src/svgmap.py) module docstring,
  the team's AI log.
- **Sixteen regions are off the viewport.** The outermost regions (prefixes
  `FRY`, `PT20`, `PT30`, `ES70`, `NO0B`) are drawn but do not set the extent,
  which would otherwise grow 6.5-fold in area; the caption names them.
  [`src/svgmap.py`](../src/svgmap.py) `OUTERMOST`,
  [`decisions.md`, 2026-10-08 "there was no map"](decisions.md#2026-10-08--offline-svg-choropleth-added-the-app-had-no-map).
- **The retrieval layer cites only what it holds.** Of the thirteen documents
  `policy_context.md` cited without a declaration on 6 October 2026, twelve are
  declared since 12 October and enter the index only once `python -m src.fetch`
  has run. Still unciteable by the kit: the Belgian Insurance Act of 4 April
  2014 (its official ELI is disallowed by the host's robots.txt), the SWD(2025)
  assessments other than Spain's, and the full EUCRA report (its landing page
  only). A draft is passed only above a 0.7 lexical grounding score and
  then only to a human. [`policy_context.md`](policy_context.md),
  [`workflow.md`](workflow.md#the-four-guards-and-what-each-prevents).

## 2. Designed and not built

Each item names where its design lives, so that finishing it starts from a
written intent rather than from memory.

- **Cultural heritage.** Natura 2000 and CORINE land cover are built (below,
  and `src/landcover.py` since 2026-10-25); no heritage source is declared at
  all. Design: [`datasets.md`](datasets.md#environment-natura-2000-and-corine-land-cover-measured).
- **Depth-against-depth validation.** The Walloon IDW depth layer is on disk (a
  by-hand download of 10 October, its declared URL dead); no code compares it
  with the model yet. Design: [`datasets.md`](datasets.md#wallonia-observed-july-2021--the-second-ground-truth--one-layer-verified-one-dead).
- **The model-versus-observation map for Europe.** The satellite-derived flood
  depth series covers 2015-2025; only the July 2021 file is declared and
  fetched. The July 2021 comparison now runs on the 27 Copernicus EMS products
  in Belgium, Germany and the Netherlands (`scripts/event_2021.py`), inside their
  mapped areas only; no map of "where is the model blind" exists for any other
  event or country.
  Design: [`strategy.md`](strategy.md#the-find-that-changes-the-plan).
- **Three further components of "unpreparedness".** The insurance protection
  gap (EIOPA), Solidarity Fund allocation against modelled risk, and the
  uncounted population are argued as findings and have no module behind them.
  Design: [`strategy.md`](strategy.md#the-out-of-the-box-framing),
  [`policy_context.md` §5](policy_context.md).
- **Monetised built-up exposure.** Needs damage curves. Design:
  [`src/assets.py`](../src/assets.py) module docstring.
- **The `portable` Docker image.** The `app` image was built and run on
  2026-10-12 (the geospatial stack imports in it; see the root
  [`README.md`](../README.md)); the `portable` image, the one that carries the
  data for the event, has not been built yet.
- **The dress rehearsal on an unprepared region.** Scheduled for 26-28 October
  on Valencia 2024 or Emilia-Romagna 2023, precisely to find what is secretly
  hard-coded. Design: [`plan.md`](plan.md#week-4-why-the-dress-rehearsal-matters-most).

**Built after the freeze.** Items that left this list, with what still bounds them.

- **Natural-language access to the exposure table** (2026-10-12). One model
  call writes a whitelisted query spec, pandas answers it, and every answer
  names its return period and the definition of each column used. It returns
  rows, never sums or means, and only columns defined in `src/nlquery.py`
  `COLUMNS` are queryable; the context table is not. The model can misread a
  question into a valid spec that answers a different one, so the spec is shown
  with every answer. [`src/nlquery.py`](../src/nlquery.py),
  [`decisions.md`, 2026-10-12](decisions.md#2026-10-12--plain-language-questions-over-the-exposure-table-apiask).
- **The undeclared policy sources** (2026-10-12). Twelve of the thirteen are
  declared in `config/sources.yaml`, eleven in the retrieval corpus and the
  EIOPA input spreadsheet as `context`; the six EU acts come from the
  Publications Office's CELLAR because eur-lex answers every script with a WAF
  challenge. Not declared: the Belgian Insurance Act (robots.txt disallows its
  ELI), the SWD(2025) series beyond Spain's (CELEX numbers never recorded); the
  EUCRA entry is its landing page, not the report.
  [`decisions.md`, 2026-10-12](decisions.md#2026-10-12--twelve-cited-policy-sources-declared-arxiv-pdf-now-indexed).
- **Units in column names** (2026-10-12). `poverty_rate` is `poverty_rate_pct`,
  its companions `poverty_rate_pct_year` and `poverty_rate_pct_level`; values
  unchanged. A table frozen before the rename is read under the new names by the
  API, Streamlit and the MCP tools, and `/api/vulnerability` still accepts
  `poverty_rate` with a `renamed` notice, for one release. CSV exports made
  before the rename keep the old header. `share_over_65` keeps its name:
  "share" already says fraction.
  [`decisions.md`, 2026-10-12](decisions.md#2026-10-12--poverty_rate-renamed-poverty_rate_pct).
- **Population density and household income** (2026-10-12). Context, and one
  of them is NUTS2.
  `pop_density_per_km2` (`demo_r_d3dens`, 2024) and
  `household_income_pps_per_hab` (`nama_10r_2hhinc`, net disposable income in
  PPS per inhabitant, 2023) sit in `context.parquet`, outside the index; adding
  either to it is a weighting decision. Income is NUTS2 applied to its NUTS3
  children and covers the EU-27 only (1,165 of 1,345 regions); density is
  published on NUTS 2021 codes and leaves 66 NUTS 2024 regions blank.
  [`src/demographics.py`](../src/demographics.py) `context_indicators`.
  `gdp_meur` is read from the newest substantially published year since the
  same day (2023, 1,292 regions).
  [`decisions.md`, 2026-10-12](decisions.md#2026-10-12--density-and-income-added-to-context-gdp-year-rule-fixed).
- **Natura 2000 on flood-prone ground** (2026-10-12). Measured as area, and
  only in the EU-27. Article 6(5)(c) asks flood risk maps to show the protected areas
  potentially affected, and Article 2(2) counts the environment and cultural
  heritage among the consequences that make up flood risk. Since 2026-10-12 `context.parquet` carries the Natura 2000
  area on flood-prone ground (RP100, >= 0.5 m, masked like the exposure table):
  38,246 km2 of 769,990 km2 of Natura land, 5.0 %. It is an area, not a harm -
  a floodplain forest is meant to flood - and it says nothing about which
  habitat. Regions outside the EU-27 have no figure, five French outermost
  regions and the Azores lie off the hazard grid, and the Canaries' ES703 is
  measured on 13 % of its area (`natura2000_grid_coverage`). Cultural heritage
  is still not measured (§2).
  [`src/environment.py`](../src/environment.py),
  [`datasets.md`](datasets.md#environment-natura-2000-and-corine-land-cover-measured).
- **The full CDS ensemble: the code** (2026-10-12) **and the files** (2026-10-25).
  `scripts/fetch_cds_member.py --all-missing` requests every one of the eight
  simulations through both gridded models for the three periods (48 requests,
  42 of them missing on 2026-10-12, one member each) and verifies the GCM, the regional
  model, the realisation, the model and the period of every file before it
  enters the ensemble directory; the ensemble reports the quartiles of its
  members' medians. It is tested with a mocked CDS client, and was run with a
  CDS key on 2026-10-25: all 48 members (98 files) are on disk and in
  `context.parquet` (`scripts/build_context.py --only climate`, the same day).
  [`scripts/fetch_cds_member.py`](../scripts/fetch_cds_member.py),
  [`decisions.md`, 2026-10-12](decisions.md#2026-10-12--ensemble-members-keyed-by-regional-model-quartiles-added).

## 3. What a Member State or the Commission would still have to do

The three recommendations in [`policy_answer.md` §6](policy_answer.md#6-the-measures-what-where-by-whom-how-by-when)
name an instrument, an addressee and a date. Acting on them, or on any figure
here, still needs the following from the authority itself.

- **Re-derive every figure from the current build.** The parquets are rebuilt
  and the counts move; the page that quotes them says so in its first paragraph.
  [`policy_answer.md`](policy_answer.md), [`decisions.md`](decisions.md).
- **Decide the depth threshold and the vulnerability weights.** Both change the
  headline, both are value judgements, and the kit deliberately ships defaults
  (0.5 m, equal weights) rather than a position.
  [`responsible_ai.md`](responsible_ai.md#say-what-ai-must-not-decide),
  [`src/vulnerability.py`](../src/vulnerability.py).
- **Check the declaration gap against the Article 4 assessments.** Only the
  State knows whether an exposed, undeclared region was assessed and found not
  significant. [`src/apsfr.py`](../src/apsfr.py).
- **Reconcile the published layer with national data.** Ireland runs the CFRAM
  programme and is absent from the EEA service; Lithuania reported in 2010 only.
  R2 asks the EEA and the two national reporters to close that.
  [`policy_answer.md` §4.2 and R2](policy_answer.md#42-two-eu-27-member-states-are-absent-from-the-commissions-own-layer).
- **Table a geometry convention through the Working Group on Floods** before
  the 22 December 2027 review of the flood risk management plans (R1), and
  publish the declared share of territory beside each submission.
  [`policy_answer.md` R1](policy_answer.md#r1--make-the-article-5-declaration-comparable-before-the-2027-review).
- **Lodge an Article 8(5) report on one named shared basin** (R3). Only a
  Member State can; the Commission then owes an answer within six months.
  [`policy_answer.md` R3](policy_answer.md#r3--use-article-85-on-one-named-shared-basin-as-a-test-case).
- **Run the climate review on the full ensemble.** Article 14(4) requires the
  likely impact of climate change to be taken into account; sixteen chains under
  one pathway support a robust direction in 728 regions by 2041-2070 and no
  magnitude for planning.
  [`policy_answer.md` §4.4](policy_answer.md#44-the-reference-discharge-is-rising-where-people-already-live-in-the-way).
- **Replace the averaged loss figures with official ones** before any casualty
  or damage number is printed. [`src/losses.py`](../src/losses.py).
- **Verify the dates and the legal texts** the brief relies on: the third-cycle
  deadlines are Article 14 arithmetic corroborated by national sources, and the
  AI Act articles were read through a mirror.
  [`policy_context.md`, open items 1 and 8](policy_context.md#open-items-and-flags).
- **Settle the AI Act classification by reading Annex III**, rather than
  asserting it; the kit's framing is a decision-support tool for a public
  authority to which the transparency and oversight expectations were applied
  anyway. [`policy_answer.md` §8](policy_answer.md#8-the-responsible-ai-layer-and-the-live-legislation),
  [`policy_context.md` §7](policy_context.md).

## 4. Risks accepted for a ten-day build

Only what the repository shows.

- **Only the frozen tables and the public July 2021 export are committed.**
  Since 2026-10-23, `data/processed/exposure.parquet` and `context.parquet` are
  in git (about 1.5 MB), and since 2026-10-26 `event_2021_web.json` (about
  0.5 MB, Natural Earth borders, no GISCO line), with
  `data/processed/DATA_NOTICE.md` for their sources; everything else under
  `data/` - the July 2021 parquets and CSVs, the ~80 GiB under `data/raw/`, the
  caches, the backups - is ignored. So a fresh clone answers with the frozen figures at once, but
  rebuilding them still means fetching the rasters and a multi-hour
  continental build. CI now has the tables too, which means a test that strays
  outside the frozen harness passes there as well: hide the parquet and re-run
  to check a test honestly.
  [`.gitignore`](../.gitignore), [`scope.md`](scope.md#what-the-nuts3-choice-produces-on-disk),
  [`decisions.md`, 2026-10-08 "cached there is no table"](decisions.md#2026-10-08--loaders-cached-no-table-forever).
- **The offline check fails today.** Run 2026-10-08: 51 of 52 declared files
  present (3.8 GiB), `wallonia_observed_water_depth_2021` missing behind a dead
  URL (a one-off download job of the Walloon geoportal, to be requested again);
  `GROQ_API_KEY` set, so the draft tab goes over the network. Exit code 1.
  `src/rag.py` now defaults to `llama3.2:3b`, the model the demo laptop has
  pulled, so a container started without `.env` asks for the same name. The
  check skips every `access: api` source, so the Risk Data Hub is covered only
  through its cache check, and the basin districts and the CDS files through
  their own WARN checks. Since 2026-10-12, 65 files are declared: the twelve
  policy documents added that day are missing until the next fetch, and the
  arXiv paper is now expected as `nist_robust_ai_alignment_limits.pdf`, so the
  check stays BLOCKED until `python -m src.fetch` has run once more. Run
  2026-10-23: that fetch has run, the Walloon depth layer is the by-hand
  download of 10 October under its declared name (see its `sources.yaml`
  entry), and 65 of 65 files are present (5.6 GiB). It still blocks on one
  thing: Ollama answers on the owner's PC with no model pulled. Run
  2026-10-25: 84 of 84 declared files present (7.0 GiB), the manifest records
  65 of them (WARN), and it blocks on Ollama alone, not running;
  `ANTHROPIC_API_KEY` is set, so the draft tab goes over the network (WARN).
  [`scripts/check_offline_readiness.py`](../scripts/check_offline_readiness.py),
  root [`README.md`](../README.md).
- **Dead configuration keys.** `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` and
  `LLM_PROVIDER` are no longer in `.env` or `.env.example` and are read by no
  code; `folium` and `streamlit-folium` are still pinned in `requirements.txt`
  and imported nowhere. Both were recorded as decisions rather than removed in
  the same pass as a feature. [`decisions.md`, 2026-10-08 "the draft tab could never have worked"](decisions.md#2026-10-08--draft-tab-fixed-413-fallback-ranked-prompt-groq-key-rotation),
  [`decisions.md`, 2026-10-08 "there was no map"](decisions.md#2026-10-08--offline-svg-choropleth-added-the-app-had-no-map),
  [`requirements.txt`](../requirements.txt).
- **Per-file test counts are typed by hand.** The total in
  `technical_deep_dive.md` §7 is filled by `scripts/docs_numbers.py`; the
  per-file rows are not, and they drift: the table of 10 October had three
  wrong or missing rows by 12 October, and two more (`test_api.py`, `test_rag.py`)
  by 14 October. Re-measured on 27 October: 49 files, summing to the
  <!-- numbers:tests_collected -->1,090<!-- /numbers --> collected; re-measure the
  file count after any test change (the total is filled by the script). [`technical_deep_dive.md` §7](technical_deep_dive.md#7-the-test-suite).
- **Whether the suite runs on Windows depends on a policy that has changed
  state four times on record.** Smart App Control blocked `rasterio`'s DLL on
  2026-10-07, allowed it again the next morning with nothing reinstalled,
  blocked it again by 2026-10-12 (still on 2026-10-14) and allowed it again by
  2026-10-23; the WSL2 venv is the route that does not depend on it. Root [`README.md`](../README.md),
  [`technical_deep_dive.md` §7](technical_deep_dive.md#7-the-test-suite).
- **Six downloaded data inputs carry no `licence:`** (nor do 22 of the 28 scraped policy and context documents, or 13 of the 19 `access: api` sources). `gisco_nuts3`, `gisco_lau`,
  `statbel_income`, `cems_emsr517_germany_2021`, `cems_emsr518_belgium_2021`,
  and `natural_earth_countries` (added 2026-10-26; Natural Earth is public
  domain, but the entry does not say so);
  the honest claim is "every input is traceable to a URL and a purpose", not
  "a licence on every input". [`responsible_ai.md`](responsible_ai.md#what-to-write-under-each-concretely).
- **The prompt budget is in characters, not tokens.** Groq refuses above 8,000
  tokens per minute; the budget is `rag.PROMPT_CHAR_BUDGET` because `tiktoken`
  does not load everywhere, at a measured 2.05 characters per token on the real
  table. [`decisions.md`, 2026-10-08 "the draft tab could never have worked"](decisions.md#2026-10-08--draft-tab-fixed-413-fallback-ranked-prompt-groq-key-rotation).
- **Tracing, when on, sends prompts off the machine.** LangSmith traces leave
  for LangChain's servers; acceptable here because the corpus is public and the
  table is open data, and said so rather than hidden.
  [`responsible_ai.md`](responsible_ai.md#tracing-let-the-tool-keep-the-log).
- **Some documented absolute figures predate the windowing fix.** The Benelux
  counts in `technical_deep_dive.md` §8 were measured before 2026-10-06 on a
  build whose answer depended on its stripe count; the ratios survive, the
  absolutes do not. [`technical_deep_dive.md` §8](technical_deep_dive.md#8-where-the-numbers-in-this-file-come-from).
- **The map's visible height is a browser check, not a test.** The iframe
  height is not among the assertable element fields, so legend clipping is
  guarded by a written measurement rather than by the suite.
  [`decisions.md`, 2026-10-08 "the legend was off-screen"](decisions.md#2026-10-08--stiframe-with-content-height-map-legend-now-visible).
- **The two UIs show different views of the same table.** The React app is the
  one to demo: run live it needs the API and a Vite build, while its static build
  (`VITE_STATIC=1`) needs no API, reads the API's answers frozen into
  `web/public/europe/` by `scripts/export_europe_web.py`, and is the public
  Hugging Face Space (root [`README.md`](../README.md), "Live demo"); Draft and
  Translation stay local. The Streamlit app needs neither and reads the parquets
  directly. They cannot disagree on a number and
  do not show the same tabs. [`technical_deep_dive.md` §1](technical_deep_dive.md#1-the-pipeline-end-to-end).
