# Limitations: what the kit does not claim

Each bullet names the bounding fact and where the evidence lives (module docstrings are
checked by `tests/test_docs_citations.py`). Re-derive numbers from the tables, not from
here. Findings are in [policy_answer.md](policy_answer.md), the pipeline in
[technical_deep_dive.md](technical_deep_dive.md), the dated record of
changes to what a figure means in [decisions.md](decisions.md).

## 1. What the figures cannot say

**July 2021 (Copernicus EMS)**

- **A snapshot, not the peak.** Each product is the water visible on one image, often
  a day after the crest; the first map and each monitoring pass are separate rows,
  never merged ([`src/event2021.py`](../src/event2021.py) module docstring).
- **Outside an area of interest is "not mapped", not dry.**
- **Radar delineations stop at walls**, so the Belgian building count is a floor
  (`buildings_within_25m_of_observed` travels beside it). Say "buildings graded
  destroyed", never "homes destroyed": the residential classes differ between passes.
  Only the German grading products carry damage grades.
- **Infrastructure "in the water" means crossing the observed polygons**
  ([`scripts/event_2021_infrastructure.py`](../scripts/event_2021_infrastructure.py)
  module docstring).
- **Two population grids**: E2020 for the event, E2025 at 1 km for Europe; they never
  enter one sum.

**The hazard and the exposure count**

- **River flooding only**, basins above about 150 km2, no surface runoff, which was a
  large part of July 2021 in Wallonia ([`src/events.py`](../src/events.py) module
  docstring). Dottori et al. 2022 find the maps reproduce about two thirds of the
  reference extent and over-estimate below RP100.
- **No dykes in the water**: every headcount in `exposure.parquet` is undefended; quote
  it with the residual figure behind the design standards (`context.parquet`).
- **Nine scenarios, never a sum**: return periods are nested extents. They are nested
  in intent only: each depth raster is a separate model run, so a rarer period can be
  shallower in places and 4 regions (FRG01, FRD22, DE927, RS211) lose people from one
  period to the next.
- **The depth threshold (0.5 m) and the masks move the headline**; so do the
  vulnerability weights. Both are value judgements the AI was not allowed to make.
- **`exposed_pop` carries an extrapolation, `exposed_pop_observed` does not**; a handful
  of regions have no measured figure or `hazard_coverage` below 1.0
  ([`src/exposure.py`](../src/exposure.py) `exposed_population` docstring). A unit
  the hazard layer covers below half (`MIN_HAZARD_COVERAGE`) is not measured either:
  that is ES703 (El Hierro), covered at 13 %. In the EU-27 seven regions have no
  figure (the five French outermost regions, the Azores and El Hierro, about 2.6
  million people), and their footprint columns in `context.parquet` (flooded
  hospitals, residual exposure, built-up) are empty too, not 0. They still sit in
  the population the 5.8 % divides by; over the measured regions only it is 5.80 %
  instead of 5.77 %.
- **A population cell is wholly in or out of a region**: the error scales with
  perimeter over area, a few percent for a commune, far more for a statistical sector.
  Nothing smaller than a commune should be read off this pipeline.
- **Which Europe**: the GISCO NUTS 2024 file holds 1,345 NUTS3 polygons (1,165 EU-27,
  the rest EFTA and candidates); every headline says which denominator it uses.
- **Built-up surface is footprint area, not value**; monetising needs damage curves
  ([`src/assets.py`](../src/assets.py) module docstring).

**Declarations and borders**

- **`apsfr_share` is comparable within a country, never between two**: the Directive
  leaves the geometry convention national ([`src/apsfr.py`](../src/apsfr.py) module
  docstring). An undeclared area is not an under-declared one. Ireland and Lithuania are
  absent from the 2018 layer.
- **"Shared" is not "upstream"**: WFD districts are catchments without flow topology
  ([`src/basins.py`](../src/basins.py) module docstring). The shared-basin share is a
  floor: non-EU riparian States do not report, and ungroupable districts stay national.

**The future layer**

- **Medians and quartiles, never a mean or a maximum**: a relative change against a
  near-zero discharge is unbounded ([`src/climate.py`](../src/climate.py) module
  docstring).
- **Sixteen chains, one pathway (RCP 8.5)**: eight simulations the dataset offers, each
  run through two hydrological models, so the 16 members are 8 independent simulations
  and the 80 % agreement rule means about 7 of 8. Not a designed sample, and the dataset
  is no longer maintained. Regions without a robust
  sign are hatched on the map, "measured, direction unsupported"
  ([`src/climate.py`](../src/climate.py) `ensemble_change_by_region` docstring,
  [`src/svgmap.py`](../src/svgmap.py) `choropleth_svg` docstring).
- **The observed record (HERA v2, 1991-2020) does not yet show the rise**; HERA is a
  reanalysis, not gauged flow, and 30 years is short.
- **It is discharge, not depth, and not a headcount**: no future exposed-population
  figure exists in this kit.

**Who is vulnerable**

- **The index is a value judgement wearing a number**: equal weights by default, never
  reported without its sensitivity ([`src/vulnerability.py`](../src/vulnerability.py)
  module docstring).
- **The sensitivity test moves the weights, nothing else.** The top ten hold up to a
  ±20 % change in weights (9 of 10 stay at RP100), but not to a change of scaling or of
  indicators: with percentile ranks instead of min-max only 1 of 10 stays, and dropping
  one indicator keeps 4 to 6. Under min-max, `exposed_pop` (median about 8,800, maximum
  610,216) barely moves the score, so a region with 15 exposed people can rank in the
  top ten. Read a "robust" label as "robust to the weights".
- **Rows scored on fewer indicators rank beside complete ones.** The index averages
  over the indicators a region has: at RP100 the French outermost regions (FRY10 to
  FRY40) rank 1, 3, 4 and 5 on age and poverty alone, with no exposure figure. Read
  `indicator_coverage` next to every rank.
- **Poverty is NUTS2 applied to NUTS3**, a percentage; `share_over_65` is a fraction.
  The Eurostat at-risk-of-poverty threshold is relative to each country's median, so
  the rate compares regions within a country, not across countries.
- **Who is not in the data**: undocumented residents, temporary housing and seasonal
  workers are absent from a residential grid. The gap is stated, not estimated.

**Losses, validation and blind spots**

- **No casualty or loss figure is official**: Risk Data Hub rows are repeated per
  administrative level and averaged across sources
  ([`src/losses.py`](../src/losses.py) module docstring).
- **Validation is one event, extent only**: `src/validate.py` and
  `scripts/event_2021.py` score the model against the 27 EMS products inside their areas
  of interest, and `scripts/validate_2021.py` against four truths in Wallonia and the
  Ahr. Every truth is read as wet or dry, the Walloon depth layer included, so modelled
  depth is never compared with observed depth, and nothing validates the model for any
  other event.
  - It checks the footprint, not the headline: the model counts as wet any depth above
    0, while the 25.7 million counts people under more than 0.5 m.
  - The truth decides the score: the RP100 hit rate in Wallonia is 0.18, 0.44, 0.61 or
    0.87 depending on the observed map (`decisions.md`, 2026-10-25). Quote the range,
    and say that the 0.87 is on the JRC observed layer, a 5.7 km² cluster holding 116
    residents (1.8 % of the 320.8 km² Wallonia recorded).
  - Hit rate alone rewards a bigger map, and it barely moves from RP10 (0.84) to RP500
    (0.88) against the JRC observed layer, so it does not show July 2021 was a
    100-year event. Report it with the false alarm ratio and the CSI.
  - The false alarm ratio runs from 0.70 to 0.98 depending on the truth (0.70 against
    the extent Wallonia recorded, 0.98 against the JRC observed layer). Against the
    satellite maps it is high partly because a snapshot is not the peak.
- **Reported events are a probe, never evidence**: news coverage is biased by attention
  and language; nothing from `src/events.py` enters a ranking.

**The map and the text**

- **Colour classes are quantiles of what is present**; the legend prints them. Grey is
  "not measured", never zero. Outermost regions are drawn but do not set the viewport.
- **The retrieval layer cites only what it holds**: a source enters the index once
  `python -m src.fetch` has run, and a few acts stay unciteable (the Belgian Insurance
  Act, whose ELI robots.txt disallows). A draft passes only above a 0.7 lexical grounding
  score, and then only to a human ([workflow.md](workflow.md)).

## 2. Designed and not built

- Cultural heritage (no source declared; Natura 2000 and CORINE are built).
- Depth-against-depth validation (modelled against observed depth values, not two
  wet/dry masks); a model-versus-observation map for other events.
- Three further components of "unpreparedness": insurance protection gap (EIOPA),
  Solidarity Fund allocation against modelled risk, the uncounted population.
- Monetised exposure (needs damage curves).
- A dress rehearsal on an unprepared region (Valencia 2024, Emilia-Romagna 2023).
- Natural-language access ([`src/nlquery.py`](../src/nlquery.py)) is built but returns
  rows only, queries the exposure table only, and can misread a question into a valid
  spec: the spec is shown with every answer.

## 3. What an authority would still have to do

Re-derive every figure from the current build; decide the depth threshold and the
vulnerability weights; check the declaration gap against its Article 4 assessments;
reconcile the layer with national data (R2); table a geometry convention before the 2027
review (R1); lodge an Article 8(5) report on one basin (R3, only a Member State can);
run the climate review on the full ensemble (no magnitude for planning); replace the
averaged loss figures with official ones before printing a casualty or damage number.

## 4. Risks accepted for a short build

Shortcuts taken to ship, each visible in the code or the tests: loose lower-bound
requirement pins; a screening statistic stood in for the statutory maps; one model
provider chain with a lexical grounding check rather than semantic retrieval; Windows
native wheels that an application-control policy may block (the container and WSL2 are
the stable routes).
