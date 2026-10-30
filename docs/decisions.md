# Decisions

The short, dated record of every change to **what a number means**, oldest
first: one entry per decision, with what changed, why, and the figures before
and after. Code comments say why a measurement is defined the way it is; this
file says when it changed, so a figure quoted from an older run can be placed.
Each entry keeps the same four-line shape: date, decision, why, effect.

---

### 2026-10-23 — Pre-hackathon audit: draft prompt, fallbacks, defaults
- **Decision:** `/api/draft` sends one return period ranked by `exposed_share` within budget; empty Claude balance falls back; Claude defaults to `claude-opus-5-5`; frozen tables committed.
- **Why:** `_table().head(rows)` sent 200 file-order rows, 29,613 characters against the 11,000 budget, so every React draft got 413 from Groq and fell to the 3B model.
- **Effect:** draft prompt 29,613 → 10,898 characters (68 regions at RP500); no frozen figure changed; 8 of 10,760 period steps found to lose people.

### 2026-10-23 — Hosted Streamlit app downloads its map boundaries
- **Decision:** Without `regions.geojson`, `load_geometry` calls `scripts/build_geometry.py::ensure` to fetch `gisco_nuts3` via `src.fetch.fetch_source` and build it.
- **Why:** A hosted clone lacks the polygons (GISCO terms keep them out of git), so the map could never render there.
- **Effect:** no figure changed; 1,345 regions, 2.8 MB, built in 3.1 s from the 25 MB layer.

### 2026-10-23 — Shared basins named; basin shares clipped to 1.0
- **Decision:** New `shared_basins` context column names each region's shared basins; `shared_basin_share` and `basin_area_share` are clipped to 1.0.
- **Why:** `shared_with` named partners but not the water; 153 and 290 regions read up to 1.0000000000000022 and 1.0000000000000056 (float noise).
- **Effect:** 810 regions carry a name, 189 more than one; largest change 1.2e-13; no ranking moves.

### 2026-10-24 — Residual exposure behind defences; hospitals and schools
- **Decision:** `build_exposure.py --protection` writes `exposure_protected.parquet` and `residual_exposed_pop_rp*`; `src/facilities.py` counts hospitals and schools in the footprint.
- **Why:** JRC hazard maps ignore local dykes; the brief also quoted the 37-country shared-basin share, and the Streamlit "Ranked" chart ran alphabetically.
- **Effect:** EU-27 RP100: 25,737,004 undefended → 7,252,724 residual (72 % held), 207,308 a year; 355 hospitals (62 residual); shared-basin 57.0 % → 63.3 %.

### 2026-10-24 — 2010 epoch, new Copernicus layers, four repairs
- **Decision:** Added the GHSL 2010 epoch and EFAS/HERA/sealing/pluvial/activations layers; fixed `total_population` cache, facilities threshold, offline check, Groq rotation.
- **Why:** The cache returned the 2025 totals for 2010 (446,267,469 both years), and facilities used `>=` 0.5 m where every other figure used `>`.
- **Effect:** EU-27 footprint built-up 2,917 → 3,340 km2 (+14.5 %), people 25,126,201 → 25,737,004 (+2.4 %); schools 9,491 → 9,488, residual 2,849 → 2,848.

### 2026-10-24 — Power BI report rewritten as a six-page PBIR story
- **Decision:** `scripts/build_bi_report.py` writes PBIR, checked by `scripts/validate_bi_report.py`; 12 measures added, `Share over 65` and `Poverty rate` weighted by population.
- **Why:** The previous four pages told nothing and had no working drill-down; legacy `report.json` deleted, `definition.pbir` 1.0 → 4.0.
- **Effect:** No existing measure changes meaning; `tests/test_export_bi.py` 8 → 15 tests (768 passed before).

### 2026-10-25 — CLMS imperviousness and CORINE land cover in footprint
- **Decision:** CLMS Imperviousness 2018 and CORINE 2018 (100 m) measured over the same EU-27 RP100 footprint (148,003 km2); 12 new context columns.
- **Why:** The 100 m CORINE raster holds class positions, not CLC codes; read as codes it gave 0 regions, so `landcover.to_codes` maps them.
- **Effect:** No existing figure changed; footprint 2.9 % sealed (median 3.2 %), more sealed in 544 of 1,119 regions; 72.4 % farmland, 3.7 % homes (5,438 km2).

### 2026-10-25 — HERA seasonality: peak timing, half-year maxima, flood days
- **Decision:** HERA cache layout 2 (`attrs["schema"] = 2`) keeps peak day, half-year maxima and flood days; six new `hera_*` columns go to `context.parquet`.
- **Why:** The annual-maximum trend says whether floods grow, not whether they move within the year.
- **Effect:** No existing figure changed; 1991-1996: only 18-35 % of river cells pass the 1-in-2-year level a year, against about 50 % expected.

### 2026-10-25 — Power BI gets a cover, navigation and a tooltip page
- **Decision:** Cover with six tiles, seven story pages, drill-through and tooltip page (179 visuals); new measure `Residual expected annual exposure`.
- **Why:** The report needed navigation and headline figures; the brief carried wrong Ahrweiler, school and Liège (BE332, the arrondissement) statements.
- **Effect:** New measure 207,308 a year behind defences (EU-27); brief now schools 2,848 / 9,488, Ahrweiler 44 of 55 cells past 1-in-100.

### 2026-10-25 — HERA in Power BI; empty columns for unrun layers
- **Decision:** Page 8 "Rivers changing" with nine measures over the `hera_*` columns; the export writes every named context column, empty if its layer has not run.
- **Why:** A column missing from `context.parquet` was dropped from `regions.csv` while the model declared it, and Power Query fails on that.
- **Effect:** No figure changed; story-page cap 8 → 9, navigation pills about 125 → 111 px.

### 2026-10-25 — HERA over 30 years; flood-day trend read off thirds
- **Decision:** HERA rests on 1991-2020 (225,978 river cells on the grid, 210,574 of them assigned to 1,220 regions); `hera_flood_days_trend_per_decade` = last third minus first third, / 20 years, x 10.
- **Why:** The Sen slope was 0 in 99.4% of cells (no flood day in a median 77% of years), so the column read 0 in all 1,220 regions.
- **Effect:** Non-zero regions 0 → 92.9%; EU-27 medians: annual peak -1.8% a decade, peak 5.0 days later, 0.43 flood days a year, -0.02 a decade.

### 2026-10-25 — 16-member ensemble; robust sign at 80 %, IQR spread
- **Decision:** Climate ensemble at 16 members; new `ensemble_robust_on_sign_<period>` (80 % rule) read by UIs; size-uncertain spread is the IQR beyond two members.
- **Why:** Rules built for two chains broke: unanimous regions 976 / 994 / 943 → 20 / 145 / 239, size-uncertain 3 / 13 / 47 → 276 / 435 / 666.
- **Effect:** Robust 353 / 728 / 846; size-uncertain 1 / 4 / 9; median +12.2 / +19.9 / +20.3 → +9.5 % / +19.9 % / +27.0 %; top-decile rising 87 → 80.

### 2026-10-25 — LLM guards check numbers, per-sentence citations, negation
- **Decision:** `src/rag.py` `verify` adds `unsupported_numbers`, `uncited_sentences`; `POST /api/approve` checks edited text; `src/translate.py::check` and `src/nlquery.py` tightened.
- **Why:** An adversarial review passed 18 lies through every guard, e.g. an invented "97%" scored grounding 1.0 and "1.5" → "15" passed translation.
- **Effect:** No figure changed.

### 2026-10-25 — Power BI Desktop save is the report source
- **Decision:** Desktop's saved report is the source; the byte-identity test becomes a schema-valid same-pages test; `visualContainer/2.14.0` validated as 2.13.0.
- **Why:** The owner's Desktop save rewrote 227 files and failed the byte-identical test; the 2.14.0 schema is unpublished (404).
- **Effect:** No figure changed; all 44 `visualContainer/2.14.0` files pass validation.

### 2026-10-25 — Observed flood layer read with nodata 65535
- **Decision:** `validate.score_event` reads WD_MERGE with `nodata=OBSERVED_READ_NODATA` (65535) instead of the declared 0.
- **Why:** Every observed-dry cell became NaN and was dropped, so FP was 0 by construction, FAR always 0 and IoU equal to the hit rate.
- **Effect:** Belgian window RP100: FAR 0.0 → 0.978, IoU 0.869 → 0.021, hit rate 0.869 unchanged; no published figure used the old values.

### 2026-10-25 — Diverging climate map anchored on zero
- **Decision:** `svgmap.signed_breaks` and `choropleth_svg(centre=0.0)` with `PALETTE_DIVERGING_SIGNED` split quantile classes at zero on the climate map.
- **Why:** Zero fell inside the first class (-18% to +9%), so 550 of the 1,149 regions with a positive median were painted blue.
- **Effect:** Wrong-hue regions 550 → 0 (0 of 49 negatives); no figure changed; renders without `centre` byte-identical.

### 2026-10-25 — July 2021 EMO-1 rainfall as a separate parquet
- **Decision:** `src/rainfall.py` and `scripts/rainfall_jul2021.py` write `data/processed/rainfall_jul2021.parquet` (12-16 July 2021, 581 regions), not context columns.
- **Why:** `emo1_precipitation_2021` was downloaded but read by nothing; a standalone table avoids a `build_context` run.
- **Effect:** No existing figure changed; BE335 max 290.4 mm (mean 167.3 mm), BE336 max 242.1 mm, DEB12 max 175.5 mm.

### 2026-10-25 — Hospitals without a bed figure are unknown, not 0 beds
- **Decision:** `facilities.counts_by_region` adds `hospitals_cap_beds_known` and sets a bed column to NaN in a region where any hospital it sums has no `cap_beds`.
- **Why:** Missing beds were filled with 0, so 32 regions (CH 354, LU 12, LV 11, AT 2 hospitals without a figure) showed complete bed totals and 14 flooded Swiss hospitals added 0 flooded beds.
- **Effect:** Regions with a bed total 382 → 350 (EU-27 331 → 324, EU-27 sum 682,683 → 658,868); EU-27 flooded beds unchanged (RP100 10,921 undefended, 3,008 residual; RP500 residual 17,326), all-region RP100 undefended 11,094 → 11,056 over 374 regions.

### 2026-10-25 — HERA peak timing is read on a circle
- **Decision:** `hera_peak_timing_shift_days_per_decade` is the Sen slope of each year's peak date as a signed distance from the cell's circular mean date, and NaN for a cell whose dates have a resultant length below 0.5 (`MIN_TIMING_CONCENTRATION`).
- **Why:** Dates counted from a fixed 1 October jumped by 365 days where a river's peaks straddle it, so moving the cut to 1 April flipped the sign of 382 regional medians, and a cell peaking in any season has no date to drift from.
- **Effect:** EU-27 median shift +5.0 → +4.2 days/decade; EU-27 regions with river cells but NaN timing 0 of 1,122 → 214 (19.1%), all regions measured 1,220 → 997; range -53.6/+47.3 → -24.4/+38.8; 283 sign flips among regions measured both times (SE214 -53.6 → NaN, NL325 +37.6 → -21.8, BE32C +40.9 → NaN).

### 2026-10-25 — No model domain read off the hazard raster
- **Decision:** `validate.modelled_domain_mask` is removed and `score_event` no longer returns `in_model_domain`; `agreement_by_unit(in_model_domain=)` now takes only an independent domain (e.g. EFAS upstream area ≥ 150 km2).
- **Why:** JRC hazard nodata marks every dry cell, so "not nodata" was the wet footprint: on the RP100 Vesdre/Ourthe window 11,933 domain cells = 11,933 wet cells, and 97.0 % of the window read as "never modelled".
- **Effect:** No published figure used the column; `modelled_outside_domain_cells` 97.0 % of the window → not produced unless a real domain is passed.

### 2026-10-25 — 2021 validation scored against four truths, population outside the maps
- **Decision:** `scripts/validate_2021.py` scores JRC RP10/100/500 and the Walloon aléa (incl. and excl. très faible) against four 2021 truths on a 20 m EPSG:3035 Wallonia window, and counts GHSL 2025 people inside each observed extent but outside each map (conservative = any 20 m sub-cell wet, upper = centre sub-cell).
- **Why:** The truths disagree by a factor of 3 to 5 on the same map, so a single hit rate would be a choice of truth, not a measurement.
- **Effect:** New figures (none before): RP100 hit rate 0.605 vs Walloon depth, 0.183 vs Walloon extent, 0.437 vs EMSR518, 0.869 vs JRC observed; aléa 0.884 / 0.412 incl. très faible, 0.728 / 0.343 excl.; Walloon-extent people outside RP100 48,383 of 119,456 (40.5 %) conservative, 60,556 (50.7 %) upper; outside aléa incl. très faible 22,116 (18.5 %) / 38,479 (32.2 %).

### 2026-10-26 — Power BI residual read from context.parquet on a fresh clone
- **Decision:** `scripts/export_bi.py` falls back to `context.parquet`'s `residual_exposed_pop_rp*` when `exposure_protected.parquet` is absent.
- **Why:** Only the local run was read, so a clone with just the committed tables exported an empty residual column: page 2 and the 7.25 M cover tile were blank.
- **Effect:** Fresh-clone export: residual non-null 0 → same table as the dev machine (RP100 all countries 10,066,281); tests 988 → 989.

### 2026-10-26 — Country detail drillthrough page
- **Decision:** A second drillthrough page, `country_detail`, bound to `Regions[country_name]`; written in place beside the Desktop-saved pages and added to `build_bi_report.py` (`detail(level)`).
- **Why:** Drill through is offered only where the visual carries the bound column, so the country bars of pages 2, 3, 7 and 8 offered none until drilled down to regions.
- **Effect:** 11 → 12 pages, 208 → 221 visuals; no measure changed; tests 989 (drillthrough test now checks both bindings).

### 2026-10-26 — July 2021 event figures: GHS-POP E2020, area-weighted, inside AOIs only
- **Decision:** `scripts/event_2021.py` counts residents in each EMS observed extent with GHS-POP E2020 30" (not the E2025 used for the EU layer), each cell weighted by its flooded share on a 20 m EPSG:3035 grid, and measures nothing outside a product's `areaOfInterestA` ("not mapped", never "dry").
- **Why:** Annex 2 of the challenge asks for E2020 for a 2021 event (E2025 is a projection) and for area weighting; an unweighted 1 km cell would count a whole village for a flooded meadow, and scoring outside an AOI would charge the hazard map with false alarms nobody observed.
- **Effect:** New figures (none before): residents in the observed extent, first products / all passes, BE 1,994 / 3,920, DE 32,562 / 47,306, NL 2,449; outside RP100 BE 12.4 % / 37.0 %, DE 37.6 % / 43.0 %, NL 11.7 %; grid vs exact-polygon residents within 1 % (AOI15 3,739 vs 3,754).

### 2026-10-26 — Unsupported claims answered with one fixed phrase
- **Decision:** `rag.SYSTEM_PROMPT` and the workflow prompt ask for exactly "I DON'T KNOW: I can't answer that with the information I have." where the passages do not support a claim; `rag.unknown_claims` lists those sentences, `verify` returns them and `verdict_line` counts them.
- **Why:** "say so" let the model hedge in free words that no check could tell from a claim; one phrase can be found, and an honest unknown is not counted as an uncited sentence.
- **Effect:** `verify` gains `unknown_claims`; `uncited_sentences` skips sentences with the phrase ("I don't know" or "I can't answer ... with the info(rmation) I have"); a hedge in other words is still listed as uncited.

### 2026-10-26 — July 2021 view in the React app, hosted and static modes
- **Decision:** The React app opens on a "July 2021" view read from `data/processed/event_2021_web.json` (`scripts/export_event_web.py`, same code as the policy tool; also copied to `web/public/`). `HOSTED=1` makes the model and write routes answer 403; `VITE_STATIC=1` builds an API-free variant with the July 2021 view only.
- **Why:** A hosted clone has no raw data, and a public demo must not spend a model quota or write to the brief.
- **Effect:** No figure changed (hero 51 %, 375 / 792, 25.7 million, 22 Dec 2027); EMSR518 AOI01 is labelled "Liège (Meuse–Vesdre)". The committed JSON is built with `--no-nuts`, so it carries no GISCO-derived geometry (see `data/processed/DATA_NOTICE.md`); the locator map shows the mapped areas without borders.

### 2026-10-26 — Public demo as a static Hugging Face Space
- **Decision:** The `VITE_STATIC=1` build of `web/` is served as a static Space under a team organisation, not a person; the API and the model routes are not hosted.
- **Why:** A static page costs nothing, needs no secret, cannot spend a model quota and shows only figures already in the policy tool; the jury can open it without installing anything.
- **Effect:** The July 2021 view is public; Europe, Ask and Draft stay local (`uvicorn` + `npm run dev`). A rebuild is uploaded by hand (see README, "Live demo").

### 2026-10-26 — Planning lists read on the EU-27
- **Decision:** The two planning lists in `policy_answer.md` and `limitations.md` take the top decile among the 1,165 EU-27 regions; the 37-country lists stay beside them as context.
- **Why:** The brief and every headline figure are EU-27 and the Floods Directive binds only Member States, yet the lists ranked all 1,345 regions and named Serbian and Albanian regions among their leaders.
- **Effect:** Undefended list 80 → 69 regions (11 → 8 unanimous; 7,321,480 → 6,545,666 people; 1,008,369 → 865,518 residual); residual list 77 → 68 (15 → 13 unanimous; 2,771,048 → 2,634,226); on both 17 → 13; HERA peaks fell in 47 of 80 → 42 of 69. Hamburg leaves the list (EU-27 decile threshold 12.6 % → 12.8 %). No code or table changed.

### 2026-10-26 — July 2021 locator borders from Natural Earth in the public build
- **Decision:** `scripts/export_event_web.py` builds the public artefact by default, with country borders from Natural Earth (public domain, `natural_earth_countries` in `config/sources.yaml`); `--full` (replacing `--no-nuts`) adds the GISCO borders and NUTS3 lines and writes `event_2021_web.full.json` only, which git ignores and the API serves first unless `HOSTED=1`.
- **Why:** The `--no-nuts` build left the locator with no border and no country name, so the public map no longer showed Belgium or Germany; and a plain run wrote GISCO geometry into the tracked files.
- **Effect:** Public locator: borders 0 → 5,814 path characters, labels BELGIUM and GERMANY, credit "Natural Earth (public domain)"; no figure changed (only `locator` and `attribution` differ in the JSON); tests 1,052 → 1,059.

### 2026-10-26 — Europe view in the static demo
- **Decision:** The static build offers the Europe view too. `scripts/export_europe_web.py` asks the real API in-process and writes its answers to `web/public/europe/` (gitignored): meta, exposure for each of the nine return periods, the context table cut to the columns the Context tab draws, and the vulnerability ranking for all seven indicator subsets at each period, at ±30 % and top 10. The map is drawn from GISCO's 1:20 million NUTS 2024 file, fetched by the viewer's browser from GISCO.
- **Why:** The public demo showed July 2021 only, without the return-period selector, the map or the rankings. Freezing the API's answers keeps one code path for every figure, and fetching the polygons from GISCO keeps its geometry out of the repository and the Space (`data/processed/DATA_NOTICE.md`).
- **Effect:** No figure changed. The static map uses 1:20 million boundaries instead of the local 1,000 m simplification; perturbation and top N are fixed in the static Vulnerability tab; Draft and Translation stay local. The export is ~19 MB in 20 files.

### 2026-10-26 — Both UIs open on the 1-in-100 year flood
- **Decision:** The React Europe view and the Streamlit app open on RP100 instead of the rarest period (RP500); a table without RP100 still opens on its rarest one. The React total chip names how many countries it covers.
- **Why:** The brief, the pitch and the Directive's medium-probability maps (Art. 6(3)(b)) all quote RP100, yet the page a juror opens first showed 35.5 million at RP500; and its 29.7 million at RP100 covers all 37 countries, while the brief's 25.7 million is the EU-27.
- **Effect:** No figure changed; only which period is on screen first. The chip reads "29,727,887 exposed in 37 countries" at RP100.

### 2026-10-26 — Both UIs open on the EU-27
- **Decision:** `/api/exposure` rows carry `eu27` (membership from `src/policy_tool.EU27`, added to the answer, never to the table). The React Europe view and the Streamlit app open on the EU-27 and offer all 37 countries of the GISCO file as a second choice; the React map draws only the regions in scope.
- **Why:** The brief, the pitch and the Floods Directive speak of the Member States, yet the first total on screen covered EU-27, EFTA and the candidate countries (29.7 million at RP100 against the brief's 25.7 million).
- **Effect:** No figure changed. At RP100 the page now opens on 25,737,004 people in 27 countries (1,165 regions); "All 37" shows the previous 29,727,887. The Vulnerability and Context tabs of the React view still rank all 37 countries.

### 2026-10-26 — The policy tool's Europe map read on the EU-27
- **Decision:** `policy_tool.europe_shares` keeps the EU-27 regions only when the table names countries, and `europe_svg` draws only the regions it counted; the text says "EU-27 regions".
- **Why:** The page's hero quotes 25.7 million EU-27 residents, while its Europe map ranked and drew all 37 countries of the GISCO file, Turkey included, so the July 2021 places were ranked against another denominator than the headline.
- **Effect:** "193 of 1,338 European regions" → "171 of 1,159 EU-27 regions" with at least one resident in ten in the zone (6 not measured); Ahrweiler 11 %, 178 → 158 regions rank higher; Verviers 2 %, 925 → 810. No share changed.

### 2026-10-27 — July 2021 roads, networks and essential services
- **Decision:** New `scripts/event_2021_infrastructure.py` reads the EMS `transportationL`, `builtUpA/P` and `facilitiesA/L/P` layers of the 27 products and writes `event_2021_infrastructure.parquet`: km of road and rail by class, km of power lines and dams, and counts of schools, hospitals, fire and police stations, stations and power sites, each in the AOI, in the observed water and within 25 m of it, plus the GRA damage grades.
- **Why:** The bucket ships these layers and only water, AOI and graded buildings were read; Q3-type impact questions need what the water cut, not only who it reached.
- **Effect:** New figures, none changed. First products, inside the observed water: Germany 239.7 km of road and rail (23.3 km of railway, 1.0 km of bridges; 9.2 km graded destroyed, 78.9 km damaged), 8 schools, 3 hospitals or care homes, 3 fire stations; Belgium 3.8 km, 1 school; Netherlands 24.1 km. A delineation's layers are the AOI's reference map, so "in the water" there is a line crossing the observed polygons; the radar-drawn Liège extent stops at kerbs and walls, which is why `near` is written beside it. Line facilities are measured in km, never counted. Tests 1,077 → 1,090.

### 2026-10-27 — Audit fixes: population grids named, credits on the Europe view, EU-27 climate figures
- **Decision:** After a five-part audit, (1) the policy tool names its two population grids (E2020 for July 2021, E2025 1 km for Europe) and adds a "design standards are not guarantees" limit (Ahrweiler: 0 residual at RP100, yet flooded); (2) the Europe view shows every data credit DATA_NOTICE.md requires, including the C3S sentence and disclaimer; (3) the static `europe/meta.json` says `has_geometry: false` and the view fetches GISCO in the browser when `static`; (4) the local React app asks `/api/event2021` first, so a `--full` build reaches it; (5) Power BI titles say 7.3 million, 16 ensemble members, Ireland in no cycle and Lithuania in 2010 only.
- **Why:** The tool said E2020 beside a figure built on E2025; the Space showed C3S-derived columns without the credit the licence requires; the docs and the Power BI text disagreed with each other and with the tables.
- **Effect:** No measured value changed, except the brief's climate sentence, which moves from all 37 countries (728 regions robust in either direction, of 1,198) to the EU-27 it claims (666 regions with a robust RISE, of the 1,041 EU-27 regions with projections; median +20.7 %). Tests 1,090 → 1,095.

### 2026-10-27 — Walloon validation on GHS-POP 2020; Ireland, Lithuania, Groundsource
- **Decision:** `scripts/validate_2021.py --epoch 2020` reads the E2020 tiles and writes its own file (2025 stays the default). New sources: `ghsl_pop_100m_tiles_2020`, `opw_ireland_afa`, `groundsource_flood_events`, read by the new `scripts/groundsource_2021.py`.
- **Why:** The organisers ask for E2020 for a 2021 event (Annex 2); the brief needs to know whether Ireland's and Lithuania's risk areas exist outside the EEA layer; Groundsource is an independent check on July 2021.
- **Effect:** Walloon extent, residents outside RP100: 40.5-50.7 % (E2025) → 40.1-50.4 % (E2020); "four to five in ten" stands. Ireland publishes 199 second-cycle APSFRs (2.37 % of the State), Lithuania designated 129 (SWD(2025) 28); the EEA 2018 cycle still lacks both (25 of 27). Groundsource: 1,791 of 3,716 floods reported 12-20 July 2021 in BE/DE/NL (48 %) touch no wet RP100 cell, about the 2018-2024 share (40 %), so it backs the map's blind spot in general, not the July 2021 figure. The Zenodo URL named the concept record (404 on files); it now names version 18647054. Tests 1,095 → 1,112.

### 2026-10-28 — Return-period bar in the Europe view; paired negations in the translation check
- **Decision:** The Europe view picks the return period on a bar from 10 to 500 years (one notch per period, still opening on 100) instead of a drop-down. The translation check reads a French "ne" as restrictive ("ne ... que", "only") only when the "que" comes after it, and accepts a negation count that matches under either reading of a paired negation ("ni ... ni", "neither ... nor" counted once or once per half).
- **Why:** The bar shows the nesting of the periods left to right, as the Streamlit view always did. The check refused a faithful French translation of recommendation 3: "it cannot solve alone" became "qu'ils ne peuvent résoudre seuls", and the "qu'" before the "ne" cancelled the negation (3 in English, 2 counted in French). A paired "ni ... ni" for "no ..., no ..." would have failed the same way.
- **Effect:** No figure changed. A translation that drops a "not" still fails under both readings (test added). Tests 1,115 → 1,119.

### 2026-10-29 — The committed web/tool build is Anna's border-area view (local matches the Space)
- **Decision:** The CLI defaults of `scripts/export_event_web.py` and `scripts/build_policy_tool.py` now build Anna's deliverable (the Liege-Limburg-Aachen border area, Eschweiler opening the story, the three border places first, the Degey decision block, satellite basemap on by default with an automatic PNG fallback and a `--no-satellite` escape). The Ahr / generic Europe-context view is still reachable by passing the old values back. `src/policy_tool.py`'s `HERO_AOI` and the function-level defaults stay the Ahr, so the unit tests that pin them are unchanged.
- **Why:** The committed artefact was the generic Ahr/PNG default while the deployed Space was the Anna build, so a local run and the Space showed different stories; a plain rebuild now reproduces what is deployed.
- **Effect:** No measured value changed. The committed `event_2021_web.json` (data/processed and web/public) is now the Eschweiler-first satellite build (2.39 MB, under the 3 MB budget). `test_the_built_artefact_is_compact_and_well_formed` was relaxed to accept the satellite JPEG and a non-Ahr first place. No net test added here (suite stays 1,121 after the parallel session's test).

### 2026-10-29 — Q3 counts the residents Q1 counts; per-place cards corrected
- **Decision:** The shelter analysis (Q3, case notebook) takes as the people needing shelter the residents the 2021 water reached, as Q1 counts them, and as shelters the GHS-OBAT non-residential buildings (use 2) outside both the 2021 water and the 1-in-100 map. It reports people with and without a shelter within 250 m / 500 m / 1 km, whether each person's nearest shelter is big enough for everyone sent there (footprint x floors / 3.5 m2 per person), and the EMS-mapped schools and hospitals inside the zone. The tool's first recommendation now carries its instrument (`--instrument`); Liège's card no longer claims "the most people reached" (Venlo–Roermond has more on the first maps); Eschweiler's "since 2021" line keeps only what a source confirms; the footer says which texts are copied rather than computed.
- **Why:** A first notebook version counted everyone in the 2021 water or the 1-in-100 zone (238,449 in Liège, against Q1's 1,356) and every building as a shelter; the case defines the group needing shelter as Q1's. The tool showed the literal "[INSTRUMENT, COST]" placeholder and unsourced amounts (~€31 M, ~€685 M).
- **Effect:** The published shares are unchanged and now reproducible from the notebook: 37 % Liège (501 of 1,356, median 1,086 m), 60 % Venlo–Roermond (1,479 of 2,449, 722 m), 91 % Eschweiler (1,099 of 1,213, 416 m); new: 419 of Liège's 1,356 reach a shelter big enough, 45 schools and 2 hospitals or care homes in Liège's 1-in-100 zone. Tests 1,124 → 1,125.

### 2026-10-29 — Residents printed exactly; the three recommendations answer the case's Q4
- **Decision:** Resident counts are printed to the whole person everywhere (`fmt_people`), no longer to three significant figures: the tool, the Space, the brief and the notebook now quote the same figure (Eschweiler 1,107 of 1,213, not 1,110 of 1,210). The tool's, the Space's and the brief's recommendations are one set, written from the case's Q4 (the places still exposed and Anna's first actions, using Q1-Q3), with the mayor of Verviers' feedback folded in but not leading: (1) warn before the water, with escalation, naming who; (2) open dry shelters where people have none, Liège first, and plan the move of the schools and hospitals inside the zone; (3) the lever each place needs, on one shared cross-border picture (Article 8(5)). The earlier EU-level pair (comparable risk areas, DG ENV; Article 8(5) by the Netherlands) moved to the brief's annex; the tool also states that its maps are scenarios, not a 5-10 h forecast.
- **Why:** Two roundings of one figure on screen and on paper read as two different numbers to a jury. The EU-level recommendations were not actions Anna can take and did not use the shelter analysis the case asks for.
- **Effect:** No measured value changed; only how residents are printed (the population grid is a model, as the limits say). Tests 1,125 → 1,125 (the rounding test now pins whole people).

### 2026-10-29 — Shelters are counted from all three countries' building files
- **Decision:** The case notebook's Q3 reads the GHS-OBAT files of Belgium, Germany and the Netherlands for every area, not only the file of the product's country. Liège: 501 of the 1,356 residents the water reached within 500 m of a public building on safe ground (37 %), 855 without, median 1,086 m, 419 reaching one big enough. Venlo–Roermond (60 %) and Eschweiler (91 %) are unchanged.
- **Why:** The first Colab run read only the Belgian file and gave Liège 23 % (314 of 1,356, median 1,497 m): Liège's area runs to the Dutch border at Visé, and dry buildings across the border were left out. The data are the same either way (the bucket and the local cache hold identical points in a test box; the cache, built by `scripts/event_2021.py`, reads all three files). For a cross-border coordinator a dry building across the border is a real shelter.
- **Effect:** The published 37 % stands and is reproducible once the notebook is re-run with the three-file read. Each file holds only its own country, so no building is counted twice.

### 2026-10-30 — What to do before the water; Liège read as a floor
- **Decision:** The tool and the Space carry a "Before the water" timeline (`BEFORE_THE_WATER`): from the EFAS notification (about four days ahead) to the Cell Broadcast 5 to 10 hours ahead, then the hand-over to the emergency services; the first next step names who triggers (Anna) and who sends (civil protection). The recommendations heading reads "two before the rain, one by the 22 Dec 2027 plan review", and the date card is "the plan deadline", not "the window to act". Liège's Q1 and Q3 figures are stated as a floor: neither EMSR518 map shows water in Verviers or Pepinster. The brief's references are numbered alphabetically by author, as in the Annex 6 example.
- **Why:** A jury review found the tool led with 2027 while the recommendations say "before the rain", and the trigger to act was never defined. Measured on the local EMSR518 files: the first map's area of interest stops about 4 km from Verviers and 7 km from Pepinster; the monitoring map covers both, but its nearest mapped water is about 15 and 11 km away.
- **Effect:** No measured value changed. Two tests added (the timeline renders in order before the maps; the Space block matches the tool): tests 1,125 → 1,127.

### 2026-10-30 — Article 8(2) for recommendation 3; Thieken 2026 quoted from its abstract; one headline
- **Decision:** Recommendation 3's instrument is Floods Directive Article 8(2) (one coordinated flood risk management plan for an international river basin district that lies within the EU, as the Meuse does), with Article 8(5) (reporting an unresolved issue to the Commission) as the fallback. Recommendation 2 no longer asks to move the schools and hospitals inside Liège's flood zone; they are warned first and buses serve those beyond walking reach. The brief quotes Thieken et al. (2026) as "58 % of the 224 deaths in Germany and Belgium occurred outside officially mapped flood hazard zones". The brief, the tool, the Space and the notebook share one headline: "Warn before the water, shelter where people have none".
- **Why:** The quoted text of Article 8 (`config/legislation.yaml`) shows 8(5) is an escalation route, not the coordination the recommendation asks for. Moving schools and hospitals is not feasible this week. The 58 % is in the paper's abstract (public Crossref record, checked 30 Oct); the regional split quoted before (half in North Rhine-Westphalia, three in four in Rhineland-Palatinate) is not, and stays in the annex flagged as read from the article body.
- **Effect:** No measured value changed. Tests 1,127 → 1,127.
- **Later the same day:** recommendation 3 became "Close the blind spots, then spend on the right lever": map the small rivers the European map leaves out (below ~150 km²) in the Article 14 review, then choose the lever per place; recommendation 1 is triggered by the EFAS notification. The brief's limits box is headed "Blind spots". The shared headline was shortened to "Warn before the water, shelter where people have none".
- **Later still (30 Oct):** recommendation 2 became "Tell every street where to go" (the nearest dry building named as the meeting point in the alert), replacing "open dry shelters" with the schools; recommendation 3 became the cross-border one, "One border, one picture, before 2027": the decision-makers and the reports differ in the three countries. Still three recommendations, all addressed to Anna.
