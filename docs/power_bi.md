# Power BI — the same figures, in the tool a ministry already has

`bi/FloodPolicyKit.pbip` is a Power BI **project** (the text format: a
semantic model in TMDL and a report in PBIR, one JSON file per page and per
visual), so it lives in git and a change shows up as a diff. Save it as
`.pbix` from Power BI Desktop to hand it on.

It computes nothing of its own. Every number comes from
`scripts/export_bi.py`, which reads the two frozen parquets with the app's
own helpers; `tests/test_export_bi.py` checks that the EU-27 headline comes
out unchanged (25,737,004 people at RP100) and that the model declares
exactly the columns the export writes.

## Open it — five minutes

1. Export the data (again after any rebuild of the frozen tables):
   `.venv\Scripts\python.exe scripts\export_bi.py`
   This writes `bi/data/regions.csv`, `bi/data/exposure.csv` and, when
   `data/processed/regions.geojson` exists, `bi/data/regions.topojson`.
   `bi/data/` is not committed.
2. Open `bi/FloodPolicyKit.pbip` in Power BI Desktop (a 2026 release: the
   report is in PBIR).
3. If the repository is not at `C:\flood-to-policy`:
   **Transform data → Edit parameters → DataFolder**, set it to the full path
   of `bi\data\`, ending with a backslash. Then **Refresh**.
4. To share: **File → Save as → .pbix**.

## The story, page by page

Twelve pages, 221 visuals, 1280 × 720: a cover, eight story pages, two
drillthrough pages (region and country) and a tooltip page. Each story page opens with the same
navigation bar, a claim as its title and a "what to look at" line under it,
and ends with a source line that carries the EuroGeographics credit. The
cover and the eight story pages carry a page filter **EU-27 = True**, because
the brief quotes the EU-27 - clear it in the Filters pane to see all 37
countries. The return-period tiles are one slicer synced across pages 1-4:
pick one and the others follow; none picked means 1-in-100.

| Page (links to a screenshot) | Title (the claim) | Visuals |
|---|---|---|
| [Overview (cover)](screenshots/power_bi_00_overview.png) | Europe's flood exposure at a glance | six tiles, each a big figure with a context line and a button to the page behind it - people exposed (25.7 M), still exposed behind the defences (7.25 M), people a year behind the defences (207,308, a lower bound - the JRC's own estimate is about 160,000), share in a shared basin (63.3 %), built-up added since 2010 (423 km²), farmland share of the footprint (72 %); a chart "from 25.7 million to 7.3 million" (no defences, held, still exposed); a panel with Liège, July 2021, the declared areas and how to explore |
| [1. Headline](screenshots/power_bi_01_headline.png) | 25.7 million people in the EU-27 live where a 1-in-100-year river flood reaches | return-period tiles, the return period shown, four cards (people exposed, share exposed, share in a shared basin, expected annual exposure), people exposed by return period on the BuPu ramp - the tiles do not filter this chart, so it always shows the nesting - and the "undefended figures" note |
| [2. Behind the defences](screenshots/power_bi_02_defences.png) | Behind the dykes, 7.3 million still live where the 1-in-100 flood reaches | tiles, the share held by the design standards, five cards (exposed without defences, still exposed behind them, residual people a year, hospitals and schools still in the footprint), undefended against residual by return period, the share held by country (ranked, coloured on the BuPu ramp), and a stacked bar of where the 7.3 million sit - bar length = no defences, dark = still exposed, light = held - with drill-down to regions |
| [3. Where](screenshots/power_bi_03_where.png) | Four countries hold three in five of the EU's exposed - the highest shares are elsewhere | tiles, a bar chart on the Geography hierarchy (length = people, colour = share exposed on the BuPu ramp), a matrix of countries opening into regions, the Shape map placeholder, the EuroGeographics credit |
| [4. Downstream of someone else](screenshots/power_bi_04_downstream.png) | Nearly two in three of the EU's exposed live in a river basin shared with another country | tiles, three cards, people exposed in shared basins by main basin (drills to regions), a decomposition tree (basin, country, region, in the order the reader picks), a matrix of basins and their partner countries |
| [5. What is at stake](screenshots/power_bi_05_at_stake.png) | What the water covers - and 423 km² more built in the floodplain since 2010 | five cards (built-up added since 2010, its growth +14.5 %, footprint under homes 5,438 km², under industry and commerce 2,044 km², footprint area 148,003 km²), the footprint's land use (CORINE 2018), the regions whose floodplain is sealed more than the region around it (Arr. Liège 46.5 % against 14.1 %), and July 2021 in the EFAS reanalysis by region |
| [6. Who is exposed](screenshots/power_bi_06_who.png) | Older and poorer regions are not more exposed - the link is weak, and if anything the other way | two scatters, one dot per region sized by people exposed: share exposed against the over-65 share, and against the poverty rate; a caption on what regional averages cannot say |
| [7. Declared vs exposed](screenshots/power_bi_07_declared.png) | Declared areas do not follow exposure: Belgium declares almost all its land, Germany and Spain almost none | the median region's declared share by country (drills to regions), a scatter of declared share against share exposed, a caption on why declarations are not comparable |
| [8. Rivers changing](screenshots/power_bi_08_rivers.png) | 1991-2020: river peaks did not grow in most EU regions - they came later in the year | five cards (annual peak trend, river cells with a significant rise, share of years peaking in winter, peak date shift, flood days trend), winter against summer peak trends by country (drills to regions), a matrix of countries opening into regions with every HERA figure, a caption on what a 30-year model reanalysis can say. Blank, never zero, on a machine where the HERA layer has not run |
| [Region detail](screenshots/power_bi_09_region_detail.png) | (drillthrough) | back button, the region's name, five cards, undefended against residual across the nine return periods, its profile (age, poverty, declared share, main shared basin, partners) and its 2041-2070 climate signal (median, quartiles, whether at least 80 % of the 16 simulations agree) |
| Country detail | (drillthrough) | the same layout for a whole country: its name, the five cards and the return-period chart over all its regions, a profile that reads over several regions (number of regions, over-65 share and poverty rate weighted by population, the median region's declared share, share exposed in a shared basin, share held by the defences) and the climate signal as "n of m regions" agreeing |
| [Tooltip: place](screenshots/power_bi_10_tooltip.png) | (tooltip, 320 × 240) | the place hovered, people exposed, share exposed, still exposed behind the defences, share held |

The titles and figures are true at 1-in-100 for the EU-27, measured on
2026-10-25 from the export: 59 % of the exposed live in Germany, France, Italy
and the Netherlands, while the highest national shares are the Netherlands
(14.8 %), Latvia and Hungary; 7,252,724 people are still exposed behind the
design standards, 207,308 a year once weighted by probability (a lower bound: the band
stops at 1-in-500); the defences
hold 99 % or more in the Netherlands, Hungary, Austria, Belgium, Slovakia,
Slovenia and Luxembourg, 26 % in
Poland, 24 % in Romania and 12 % in Spain; 63.3 % of the EU-27's exposed live
in a shared basin (57.0 % over all 37 countries, whose non-EU members report
no basins); built-up surface in the footprint grew from 2,917 km² to 3,340 km²
(+423 km², +14.5 %); 72.4 % of the footprint is farmland; Ahrweiler passed its
1-in-500-year discharge, with 44 of its 55 river cells past 1-in-100; the
regional rank correlation of share exposed is -0.13 with the over-65 share and
-0.16 with the poverty rate; the median Belgian NUTS3 region declares 99.99 % of its
area (the brief's "99.9 % of its territory" is another measure: the area of
Belgium's declared polygons over the national territory, 99.908 %), the median German one 0.03 %, the median Spanish one 0.004 %. A title is
static text: pick another return period and the cards move, the title does
not.

## Navigate, drill down, drill through, hover

- **Navigation bar** (the cover and every story page, top). One pill-shaped
  button per page, the cover included; the page on screen is filled dark purple. In Power BI Desktop a
  button needs **Ctrl+click** while editing; in the service or in reading
  view a plain click works. The cover's tile buttons do the same.
- **Drill down** (inside one chart). The bar charts of pages 2, 3, 7 and 8 sit
  on the `Regions[Geography]` hierarchy, Country then Region; page 4's on
  basin then region. Use the arrows in the chart's header: the single down
  arrow turns on drill-on-click - then click a country to open its regions -
  the double arrow opens every country one level down, the up arrow goes back.
  The matrices of pages 3, 4 and 8 show the same drill as +/- buttons, always
  visible.
- **Decomposition tree** (page 4). It opens on the total alone; click the +
  on a bar and pick Basin, Country or Region for the next split.
- **Hover** (tooltip page). Hovering a bar of pages 2, 3, 4, 7 and 8, or a dot
  of pages 6 and 7, shows "Tooltip: place" instead of the default box: the
  place (region and country, the country, or the number of regions), people
  exposed, share exposed, still exposed behind the defences, share held.
- **Drill through** (to another page). Right-click a region - a bar at the
  Region level, a table row, a scatter dot - then **Drill through → Region
  detail**; right-click a country bar or a country row for **Drill through →
  Country detail** (a region offers both). The page shows that region alone; its back button (top left;
  Ctrl+click while editing in Desktop) returns to where you came from. The
  page is bound to `Regions[region]` and hidden from the tabs in view mode.
  It does not take the source page's other filters
  (`acceptsFilterContext: None`), so its chart shows all nine return periods
  whatever the tiles said. One name covers two regions, Jura (CH025 and
  FRC22): drilling through on it shows both added up, and the region card
  says so.

## The model

| Table | Grain | What it holds |
|---|---|---|
| `Regions` | one row per NUTS3 region (1,345) | names, country, `is_eu27`, population, over-65 share, poverty rate, expected annual exposure, shared basins (`shared_basin_share`, `shared_with`, `shared_basins`, `main_shared_basin`), declared risk area (`apsfr_*`), GDP, density, income, climate change in reference discharge (median, quartiles, sign agreement both unanimous and at least 80 % of members, three horizons), hospitals and schools in the RP100 footprint (undefended and residual), people and built-up in the footprint in 2010 and 2025, EFAS July 2021 exceedance, river peaks 1991-2020 (HERA: trend, season, timing, flood days), sealed soil (HERA 2010/2020, CLMS 2018), the footprint's land use (CORINE 2018), heavy rain and flood recurrence at +2 C (C3S); the hierarchy `Geography` (Country → Region) |
| `Exposure` | one row per region and return period (12,105) | `return_period`, `annual_probability`, `exposed_pop`, `hazard_coverage`, `residual_exposed_pop` (behind the PESETA IV design standards; read from the local residual run, or from the committed `context.parquet` on a fresh clone) |

One relationship, `Exposure[nuts_id]` → `Regions[nuts_id]`, many to one,
filtering from `Regions` to `Exposure`. Lists are joined with `"; "` because a
basin name can carry a comma.

## The measures

58 measures, all on `Exposure`.

| Measure | Use it for | The rule it enforces |
|---|---|---|
| `Exposed population` | every headcount | **One return period at a time: the one selected, RP100 when none is, blank when several are.** The extents are nested, so a sum over return periods counts the same people several times. `exposed_pop` has no default summarisation for the same reason. |
| `Population` | denominators | residents of the regions in the filter |
| `Share exposed` | maps, rankings | one return period |
| `Exposed in shared basins` / `Share in shared basins` / `Regions in shared basins` | the cross-border argument | a floor: non-EU states do not report basins |
| `Expected annual exposure` | the headline card | the sampled band RP10-RP500 only: a lower bound, never called an expected annual damage |
| `Regions measured` | tooltips | the regions in the filter |
| `Share over 65` / `Poverty rate` | page 6, the region profile | weighted by population, regions without the figure left out of both sides. **Regional** figures, not the age or income of the exposed: the kit has no population grid by age, so a "share of the exposed over 65" is deliberately not computed |
| `Declared share of area` | the region scatter, the profile | one region only - blank above, because the export carries no region areas to weight with |
| `Median declared share` | the country bars | the median region; blank, not zero, for Ireland, in no cycle of the EEA layer, and Lithuania, in the 2010 cycle only |
| `Regions with a declared risk area` | tooltips | declarations are not comparable across countries |
| `Median change in discharge 2041-2070`, `Lower quartile …`, `Upper quartile …` | the climate card | medians and quartiles only, never a mean |
| `Regions where simulations agree 2041-2070` / `Simulations agree on direction 2041-2070` | the climate card | read the robust column (at least 80 % of members agree, IPCC AR6); "No data" where the layer has no value, never "No" |
| `Selected return period` / `Return period label` | titles and cards | RP100 when none is selected |
| `Region shown` | the drillthrough page | names the region, or says when a name covers two |
| `Residual exposed` / `Held by defences` / `Held by defences (people)` | the cover, page 2, the tooltip | the same one-return-period rule as `Exposed population`; a design standard, not a guarantee |
| `Residual expected annual exposure` | the cover, page 2 | the trapezoid of `Regions[expected_annual_exposure]` over RP10-RP500, applied to the residual headcount and written as a weighted sum (each return period weighs half the gap between its neighbouring probabilities); ignores the return-period tiles; a lower bound. `test_the_residual_annual_measure_is_the_trapezoid_of_the_regional_column` checks those weights give back the frozen undefended column |
| `Place shown` | the tooltip page | the region and its country, the country, or the number of regions - whichever level was hovered |
| `Hospitals …` / `Schools …` (in footprint, behind defences) | page 2 | RP100 only; blank where GISCO does not cover a country (no German hospitals) |
| `Built-up in footprint 2010/2025`, `Built-up added since 2010`, `Built-up growth since 2010`, `People in footprint 2010` | the cover, page 5 | today's footprint over both GHSL epochs: the change is what moved in, not a change in the hazard |
| `Footprint area`, `Footprint: …` (seven land uses), `Footprint under homes (km²)`, `Footprint under industry (km²)`, `Footprint sealed share` | the cover, page 5 | weighted by footprint area, never a mean of regional shares |
| `River peak trend per decade`, `Winter …` / `Summer peak trend per decade`, `Winter peak share`, `Peak timing shift per decade`, `Flood days per year`, `Flood days trend per decade`, `HERA years` | page 8 | the median region, each region already a median over its river cells; blank where the HERA layer has not run (it needs the 69 GB of raw HERA files), never zero |
| `River cells with rising peaks` | page 8 | pooled by river cells, not a mean of regional shares |
| `Region sealed share` / `Floodplain sealed above region` | page 5 | one region only (no region areas to weight with); the gap is in percentage points, footprint minus whole region |

## The theme

`bi/FloodPolicyKit.Report/StaticResources/RegisteredResources/FloodPolicyKit.json`,
registered in `definition/report.json` as the custom theme
(`themeCollection.customTheme` and a `RegisteredResources` resource package).
Light grey page, white cards with a thin border, rounded corners and a faint
drop shadow, Segoe UI; exposure in the
ColorBrewer BuPu ramp (light blue to purple: colourblind-safe, readable in
greyscale, read as water), purple `#8856A7` for a headcount, the darkest step `#810F7C` for what the
defences do not hold (and the current page in the navigation bar), one accent - sea
green `#1B9E77` - for the cross-border figures,
grey for the declared areas. No orange anywhere: a test scans the theme and
every report file for one. If Desktop opens the report without it (no grey
page), apply it once by hand: **View → Themes → Browse for themes →** that
file.

## Add the map — the one thing done by hand

Page 3 (Where) keeps a labelled box for it. Insert a **Shape map**: Location
`Regions[nuts_id]`, Color saturation `Share exposed`, then **Format → Map
settings → Custom map →** `bi/data/regions.topojson`, and resize it over the
note. In Desktop the Shape map may need **Options → Preview features → Shape
map visual**. It is not generated because the Shape map stores the TopoJSON
inside the report, and the boundaries are not committed (GISCO terms, see
`data/processed/DATA_NOTICE.md`). The page already carries the credit
"© EuroGeographics for the administrative boundaries".

## How the report is built and checked

- `scripts/build_bi_report.py` writes every PBIR file, the theme and
  `definition.pbir` from one grid and one palette. The report has since been
  edited and saved in Desktop, so the saved files are the source: running the
  script again overwrites them (port a Desktop change into the script first).
  `test_the_generator_still_writes_a_report_that_validates` only checks that
  the script still writes a valid report with the same pages, not that it
  matches the committed files.
- `scripts/validate_bi_report.py` checks every JSON file of the project
  against the schema its `$schema` names - `version.json`: versionMetadata
  1.0.0; `report.json`: report 3.3.0; `pages.json`: pagesMetadata 1.1.0; each
  `page.json`: page 2.1.0; each `visual.json`: visualContainer 2.13.0 (the
  visuals Desktop saved as 2.14.0, not yet published, are read against
  2.13.0); the theme: the report theme schema of Desktop 2.159. Desktop
  rewrites the `.pbip`, `definition.pbism`, `definition.pbir` and
  `diagramLayout.json` without a `$schema`, so those are skipped - and each
  visual's formatting names and values
  against that theme schema, offline. The schemas are vendored in
  `bi/schemas/` from microsoft/json-schemas and
  microsoft/powerbi-desktop-samples, both MIT; the licences are beside them.
- What no schema checks: the data roles a visual uses (`Category`, `Y`, `X`,
  `Size`, `Values`, `Tooltips`, the matrices' `Rows`, and the decomposition tree's `Analyze` and
  `ExplainBy`) and how a page looks. Those need Desktop.
- `tests/test_export_bi.py` also checks that the cover is the first page and
  links to story pages, that every story page carries the full navigation bar
  pointing at pages that exist, that the tooltip page is of type Tooltip and
  wired to the charts, that every page but the tooltip names its sources and
  credits EuroGeographics, that no field shows a default name, and that no
  orange hex is left in the theme or the report.

## Before showing it to anyone

- **Credit on every map page:** "© EuroGeographics for the administrative
  boundaries" (GISCO terms) - on every page's source line, and beside the
  map on page 3.
- **Never show a figure "for all return periods".** Every headcount is blank
  when several are selected; the tiles are single-select.
- **Prefer the Shape map to the Map / Filled map visuals:** those two send the
  data to Bing / Azure Maps and need the network; the Shape map draws the
  local TopoJSON.
- **Publish to web is public.** These are public data, but a published report
  is outside the team's control; share the `.pbix` instead.

## What to check on first open

The owner has opened and saved this version in Desktop once; these are the
points the schemas cannot vouch for, in the order to look at them.

1. **The cover** should open first (`pages.json` names `overview` as the
   active page), with six tiles: the big figures should read
   25.7M, 7.25M, 207,308, 63.3%, 423 and 72%. If the third reads anything
   else, the `Residual expected annual exposure` measure is wrong.
2. **The navigation bar**: nine pills on every story page, the current one
   filled. Ctrl+click one in Desktop to check it jumps to the right page.
3. **Page 4's decomposition tree** shows one bar (about 16.3M) with a + on
   it; if it shows an error instead, its data roles are the culprit.
4. **The tooltip**: hover a country bar on page 3 - the box should be the
   small "Tooltip: place" page with the country's name, not the default list.
   If the default box shows, set Format → Tooltips → Type: Report page, Page:
   Tooltip: place on that chart.
5. **Page 2's stacked bar** (where the 7.3 million sit): dark segment first,
   longest for Poland, Spain, Romania; the ranked "share held" chart should
   run from Luxembourg and Austria (100 %) down to the Baltic states,
   Bulgaria and Greece (0 %).
6. **Text that wraps**: page titles are 16 pt on one line and the cover tiles
   hold two short lines above their button; a title cut off or a tile line
   under the button means a size to shrink.

