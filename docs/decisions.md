# Decisions

One entry per decision that still holds, oldest first: date, what was decided,
why, and the figures before and after when a number changed. Code comments say
how a measurement is defined; this file says when it changed, so a figure
quoted from an older run can be placed.

### 2026-10-23: Draft prompt, hosted map boundaries, shared basins
- `/api/draft` sends one return period, ranked by `exposed_share` within the 11,000-character budget. The old prompt was 29,613 characters, so every React draft got 413 from Groq. Now 10,898 (68 regions at RP500).
- Without `regions.geojson`, `load_geometry` builds it through `scripts/build_geometry.py::ensure` from `gisco_nuts3`, because GISCO terms keep the polygons out of git.
- `shared_basins` names each region's shared basins; `shared_basin_share` and `basin_area_share` are clipped to 1.0 (153 and 290 regions read 1.0000000000000022 and above). No ranking moves.

### 2026-10-24: Residual exposure behind defences; 2010 epoch
- `build_exposure.py --protection` writes `exposure_protected.parquet` and `residual_exposed_pop_rp*`, because the JRC hazard maps ignore local dykes. `src/facilities.py` counts hospitals and schools in the footprint.
- EU-27 RP100: 25,737,004 people undefended, 7,252,724 residual (72 % held), 207,308 a year; 355 hospitals (62 residual).
- The `total_population` cache returned the 2025 totals for 2010 (446,267,469 both years). Fixed: EU-27 footprint built-up 2,917 to 3,340 km2, people 25,126,201 to 25,737,004. Facilities use `>` 0.5 m like every other figure.

### 2026-10-25: Climate ensemble and HERA trends
- The ensemble has 16 members. `ensemble_robust_on_sign_<period>` is true when at least 80 % of members agree on the sign; size-uncertain spread is the IQR beyond two members. Rules built for two chains had put 20 to 239 regions in "unanimous". Robust: 353 / 728 / 846 regions; median +9.5 / +19.9 / +27.0 %.
- HERA covers 1991 to 2020 (210,574 river cells in 1,220 regions). The flood-day trend is last third minus first third, per decade, because the Sen slope was 0 in 99.4 % of cells.
- Peak timing is read on a circle (signed distance from the cell's circular mean date; NaN below a resultant length of 0.5), because a fixed 1 October cut flipped the sign of 382 regional medians. EU-27 median shift +4.2 days a decade.
- The climate map splits its classes at zero (`choropleth_svg(centre=0.0)`): 550 positive regions had been painted blue.

### 2026-10-25: Land cover and missing values
- CLMS imperviousness and CORINE 2018 are measured over the EU-27 RP100 footprint (148,003 km2): 2.9 % sealed, 72.4 % farmland. The 100 m CORINE raster holds class positions, not CLC codes; `landcover.to_codes` maps them.
- A hospital without a bed figure is unknown, not 0 beds. A bed total is NaN in any region where one summed hospital lacks `cap_beds`: regions with a total fell from 382 to 350, the EU-27 sum from 682,683 to 658,868.
- July 2021 EMO-1 rainfall is its own table, `rainfall_jul2021.parquet` (12 to 16 July, 581 regions), not context columns.

### 2026-10-25: Validation of the hazard map
- `validate.score_event` reads the observed layer with nodata 65535, not the declared 0. Before, every dry cell was dropped, so false alarms were 0 by construction. Belgian window RP100: FAR 0.0 to 0.978, IoU 0.869 to 0.021, hit rate 0.869 unchanged.
- No model domain is read off the hazard raster: its nodata marks every dry cell, so 97 % of a window read as "never modelled". `agreement_by_unit(in_model_domain=)` takes only an independent domain (for example EFAS upstream area of 150 km2 or more).
- `scripts/validate_2021.py` scores JRC RP10/100/500 and the Walloon hazard map against four 2021 truths, because the truths differ by a factor of 3 to 5 on the same map. RP100 hit rate: 0.605 against Walloon depth, 0.183 against Walloon extent, 0.437 against EMSR518, 0.869 against JRC observed.
- Residents inside the Walloon extent but outside RP100: 40.5 to 50.7 % with GHS-POP E2025, 40.1 to 50.4 % with `--epoch 2020`. "Four to five in ten" stands.

### 2026-10-25: LLM guards
- `rag.verify` checks each number against the passages (`unsupported_numbers`) and each sentence for a citation (`uncited_sentences`); `src/translate.py::check` also checks negation. Sentence-level grounding alone let unsupported numbers and flipped negations through.
- Where the passages do not support a claim, the model must write exactly "I DON'T KNOW: I can't answer that with the information I have." A hedge in other words cannot be told from a claim; the fixed phrase can be found (`rag.unknown_claims`) and is not counted as uncited.
- The translation check reads a French "ne" as restrictive only when "que" follows it, and accepts either count of a paired negation ("ni ... ni"). It had refused a faithful translation of recommendation 3. A translation that drops a "not" still fails.

### 2026-10-26: July 2021 event figures
- `scripts/event_2021.py` counts residents in each EMS observed extent with GHS-POP E2020 30" (the challenge asks for E2020 for a 2021 event; E2025 stays the Europe grid). Each cell is weighted by its flooded share on a 20 m EPSG:3035 grid, and nothing outside a product's `areaOfInterestA` is measured: that is "not mapped", never "dry".
- Residents in the observed extent, first products / all passes: BE 1,994 / 3,920, DE 32,562 / 47,306, NL 2,449.
- `scripts/event_2021_infrastructure.py` adds road and rail km, power lines, dams and essential services in the observed water. Line facilities are measured in km, never counted. The radar-drawn Liege extent stops at kerbs and walls, so `near` (within 25 m) is written beside "in".
- Groundsource: 1,791 of 3,716 floods reported 12 to 20 July 2021 in BE/DE/NL (48 %) touch no wet RP100 cell, about the 2018-2024 share (40 %). It backs the map's blind spot in general, not the July 2021 figure.

### 2026-10-26: Headlines and lists read on the EU-27 at RP100
- The React Europe view, the Streamlit app and the policy tool open on RP100 and on the EU-27 (1,165 regions), with all 37 countries as a second choice. `/api/exposure` rows carry `eu27`. The brief and the Floods Directive speak of Member States and RP100: at RP100, 25,737,004 people in 27 countries against 29,727,887 in 37.
- The policy tool's Europe map and the two planning lists take the top decile among the EU-27 regions (undefended list 80 to 69 regions, residual list 77 to 68). "193 of 1,338 European regions" became "171 of 1,159 EU-27 regions".
- The brief's climate sentence counts the EU-27: 666 regions with a robust rise, of the 1,041 with projections; median +20.7 %.
- The policy tool names its two population grids (E2020 for July 2021, E2025 1 km for Europe) and says design standards are not guarantees (Ahrweiler: 0 residual at RP100, yet flooded).

### 2026-10-26: Public demo
- The `VITE_STATIC=1` build of `web/` is served as a static Hugging Face Space under a team organisation. A static page costs nothing, holds no secret and cannot spend a model quota. `HOSTED=1` makes model and write routes answer 403. The July 2021 view and the Europe view are public; Ask and Draft stay local.
- `scripts/export_event_web.py` builds the public JSON with Natural Earth country borders (public domain). `--full` adds GISCO borders and NUTS3 lines and writes `event_2021_web.full.json`, which git ignores and the API serves first unless `HOSTED=1`.
- `scripts/export_europe_web.py` freezes the real API's answers into `web/public/europe/` (gitignored, about 19 MB). The static map fetches the 1:20 million GISCO polygons in the browser, which keeps GISCO geometry out of the repository.
- The committed web build and the policy tool are the Liege-Limburg-Aachen view, Eschweiler first, with a satellite basemap and a PNG fallback (`--no-satellite`). `HERO_AOI` in `src/policy_tool.py` stays the Ahr.

### 2026-10-26: Power BI report
- `scripts/build_bi_report.py` writes the PBIR report (12 pages, including a cover, a tooltip page and two drill-through pages) and `scripts/validate_bi_report.py` checks it. The Power BI Desktop save is the source: the test checks the same pages against the schema, and `visualContainer/2.14.0` is validated as 2.13.0 because that schema is unpublished.
- `scripts/export_bi.py` falls back to `residual_exposed_pop_rp*` in `context.parquet` when `exposure_protected.parquet` is absent, so a fresh clone shows the 7.25 million residual tile.
- The export writes every named context column, empty if its layer has not run, because Power Query fails on a missing one. `Share over 65` and `Poverty rate` are weighted by population.

### 2026-10-29: Shelters (Q3) and the three recommendations
- The people needing shelter are the residents the 2021 water reached, as Q1 counts them. Shelters are the GHS-OBAT non-residential buildings (use 2) outside both the 2021 water and the 1-in-100 map, read from the Belgian, German and Dutch files for every area (Liege runs to the Dutch border). Capacity is footprint x floors / 3.5 m2 per person.
- Share of residents with a shelter within 500 m: Liege 37 % (501 of 1,356, median 1,086 m, 419 reach one big enough), Venlo-Roermond 60 % (1,479 of 2,449), Eschweiler 91 % (1,099 of 1,213).
- Resident counts are printed to the whole person everywhere (`fmt_people`), so the tool, the Space, the brief and the notebook quote one figure (Eschweiler 1,107 of 1,213).
- The brief, tool, Space and notebook share three recommendations: warn before the water, with escalation, triggered by the EFAS notification; tell every street where to go (the nearest dry building in the alert); one border, one picture, before the 22 Dec 2027 plan review (Floods Directive Article 8(2)). The tool carries a "Before the water" timeline (`BEFORE_THE_WATER`) and states that its maps are scenarios, not a 5 to 10 h forecast.
- Liege's Q1 and Q3 figures are a floor: neither EMSR518 map shows water in Verviers or Pepinster. The brief quotes Thieken et al. (2026): 58 % of the 224 deaths occurred outside officially mapped flood hazard zones.

### 2026-11-03: Team 9 map
- `web/public/team9/flood_map.html` is Team 9's single page with four scenes (What happened, Who was exposed, Where could they go, Where to start). The separate `priority_map.html` is retired. The source is vendored under `team9/` and is Team 9's measurement, not this kit's.

### 2026-11-08: Two fixes in the question and approval paths
- `src/nlquery.py::execute` counts a row in `null_excluded` only when the null is what dropped it. At RP100, "Belgian regions with exposed_pop > 0" went from 7 to 0; a question with no other filter is unchanged.
- `web/src/api.js::approve` sends the draft's `passages` and `table_text` back, as the Streamlit tab does. Without them `/api/approve` could not check numbers or the citation range, and "4,812,000 residents [S4]" after a three-passage draft was accepted. Now 422.

### 2026-11-18: The Risk Data Hub cache is dated
- `src/rdh.py` writes the fetch date, URL, parameters and row count of each cached answer to `data/processed/rdh_cache/_meta/` (`rdh.cache_meta()`). `tests/test_rdh_cache_snapshot.py` re-measures the figures quoted in `docs/datasets.md` and `src/losses.py` on the real cache and skips when it is absent. The cache is still the v3.2 answer; RDH v3.3 may have renumbered event codes.

### 2026-11-22: Approve, tracked HTML, requirements
- `/api/approve` without a token accepts only loopback callers, plus private addresses when `/.dockerenv` exists (behind Docker's port-forward every caller arrives from the bridge gateway, and compose publishes the port on 127.0.0.1 only). `HOSTED=1` always answers 403.
- Only two generated HTML pages stay in git, latest version only, because the README links them: `web/public/vesdre_3d.html` and `web/public/team9/flood_map.html` (Git LFS, so older versions stay on the server). `web/public/event_2021_web.json` is copied from `data/processed/` by `npm run prebuild`; `team9/shelter_candidates.geojson` is a gitignored output.
- Requirements are split into runtime (`requirements.txt`), test (`requirements-test.txt`) and dev (`requirements-dev.txt`). The Docker `test` target installs the test file. `team9/tests` joins `testpaths`, so a bare `pytest` also runs Team 9's suite.
