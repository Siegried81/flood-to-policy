# Decisions

The short, dated record of every change to **what a number means**, oldest
first: one entry per decision, with what changed, why, and the figures before
and after. Code comments say why a measurement is defined the way it is; this
file says when it changed, so a figure quoted from an older run can be placed.
Each entry keeps the same four-line shape: date, decision, why, effect.

---

### 2026-10-06 — Raw population is not a vulnerability indicator
- **Decision:** `total_pop` added to `NON_INDICATOR_COLUMNS`, so it is no longer offered as a vulnerability indicator.
- **Why:** The rebuild put `total_pop` first in the offer list, so both UIs' default index ranked regions as vulnerable for being populous.
- **Effect:** Offer list `["total_pop", "exposed_pop"]` → `total_pop` excluded; no exposure figure changed.

### 2026-10-06 — Shared-basin share measured by basin, not polygon
- **Decision:** `src/basins.py` accepts `CNTR_CODE` or `country`, needs 50 km² per country, and groups districts via `config/international_basins.yaml` (68 districts, 22 basins).
- **Why:** It could not run (`ValueError`), border slivers made 109 of 182 districts look international, and per-state WFD polygons showed every shared basin as unshared.
- **Effect:** Regions with any cross-border share 224 → 810; wholly inside a shared basin 124 → 603; shares above 1.0 stay 0. All 22 basins pass `check_crosswalk()`.

### 2026-10-06 — NUTS3 denominator: say which one
- **Decision:** Docs now give the GISCO 2024 count and say whether a figure is EU-only or the whole file.
- **Why:** "~1,166" was an EU-only NUTS 2021 count applied to a file that also holds EFTA and candidate countries.
- **Effect:** ~1,166 → 1,345 polygons (1,165 EU-27, 46 EFTA, 134 candidates); DE 401 → 400 after `DEG0P` was absorbed.

### 2026-10-06 — `cells_counted` and `hazard_coverage` are not indicators
- **Decision:** `cells_counted` and `hazard_coverage` excluded from vulnerability indicators in `api/main.py` and `app/streamlit_app.py`.
- **Why:** Both numeric bookkeeping columns led the offered list, so the default index was built from raster bookkeeping, not people.
- **Effect:** Default `indicators[:3]` becomes `total_pop, exposed_pop, share_over_65`; no exposure figure changed.

### 2026-10-06 — Fraction mode treats nodata as dry (`nodata_means_dry`)
- **Decision:** New `nodata_means_dry: bool = True` in `src/exposure.py`: on sparse JRC rasters nodata counts as observed dry ground.
- **Why:** Sparse rasters made "looked at" equal the flood footprint, so fraction mode returned 1.0 per covered cell, the same as binary.
- **Effect:** BE/NL/LU RP100 13,771,935 → 5,065,526 (2.72x); `NL363` 265,014 → 26,452 (10.0x); max diff 0 vs independent reimplementation.

### 2026-10-06 — Mask permanent water and spurious areas; 0.5 m default depth
- **Decision:** `scripts/build_exposure.py` masks permanent water bodies and spurious-depth areas, and `--min-depth-m` defaults to 0.5 instead of 0.0.
- **Why:** Permanent water is patched in at 1.00 m (21.3% of Benelux RP10 wet cells), spurious cells are known artefacts, and 0 m counts sheet flow.
- **Effect:** BE/NL/LU RP100 5,065,526 → 4,344,955 (−14.2%) from water mask; 5,065,526 at any water, 3,949,210 at ≥0.5 m, 2,610,894 at ≥1.0 m.

### 2026-10-06 — Choropleth polygons built and simplified at 1 km
- **Decision:** New `scripts/build_geometry.py` writes `regions.geojson`, simplified at 1 km in EPSG:3035, keeping all 1,345 polygons.
- **Why:** Nothing produced the file, so `/api/geometry` returned 404 and the map rendered nothing with no error on a clean checkout.
- **Effect:** File size 25 MB → 2.8 MB; no figure changed.

### 2026-10-06 — Extrapolate per unit; window on the population grid
- **Decision:** Fraction mode sums the observed figure and divides once per unit (new `exposed_pop_observed`), and windows are cut on the population grid.
- **Why:** Per-cell extrapolation double-counted cells straddling hazard stripes, so totals depended on the stripe count.
- **Effect:** Before: 29,808,232 (13 stripes) vs 29,732,746 (3), 75,486 apart, PL514 off 14.7%. After: 29,727,889.31 at both 13 and 3 windows.

### 2026-10-06 — Extrapolation weighted by people; three windowing bugs fixed
- **Decision:** `exposed_pop` divides by `pop_observed / pop_total`; hazard window narrowed in rows only; edge windows kept; binary not divided by coverage.
- **Why:** Unweighted coverage doubled edge units (1,000 → 2,000), `--stripes 1` read 4 of 110,162 columns, and dropped windows gave a 3x spread.
- **Effect:** Fixture 36,000–144,000 spread removed; `built_share_exposed` max 2.0 → in range; 29,727,889 must be re-derived before quoting.

### 2026-10-07 — Context table reaches the UIs; one-member period flagged
- **Decision:** `context.parquet` served on `GET /api/context` with Streamlit and React tabs; `climate_periods` reports `single_member` and hides direction.
- **Why:** The table was built since 6 October and read by nothing, and 0 agreeing regions for 2071–2100 meant "never compared", not disagreement.
- **Effect:** No figure changed; 2071–2100 shown as +25.6%, 1 chain, 0 agreeing. Tests 426 → 439.

### 2026-10-07 — One indicator is no longer labelled robust
- **Decision:** `sensitivity` gets a sixth `confidence` label, `single_indicator`, between `no_discrimination` and `robust`.
- **Why:** With one indicator weight perturbation cannot reorder anything, so every region was certified "robust" by construction.
- **Effect:** One indicator, p=0.9: 1,338 `robust` → 1,338 `single_indicator`. Tests 439 → 441.

### 2026-10-07 — Eurostat age and poverty indicators added
- **Decision:** `src/demographics.py` fetches Eurostat data and joins `share_over_65` and `poverty_rate`; `gdp_meur` goes to `context.parquet`.
- **Why:** The index had one indicator; also, summing `Y85-89`, `Y_GE85`, `Y_GE90` double-counts over-85s (22.76% vs true 20.01%).
- **Effect:** Confidence at p=0.3, RP100: 1,338 `single_indicator` → 6 `robust`, 1,332 `indicative`. Tests 441 → 452.

### 2026-10-07 — APSFR designations added beside modelled exposure
- **Decision:** `src/apsfr.py` adds Floods Directive APSFRs (current cycle, tolerance 0.0001, exact overlay); `basins` `_repair` becomes `repair(method)`.
- **Why:** 110 m tolerance dropped 44% and showed DE/ES/FR as declaring nothing; Ireland is absent, so `apsfr_country_reported` and NaN share.
- **Effect:** 25 m thinning dropped: 1,071 s → 4,683 s and 44 of 1,147 regions moved past 0.001; no basin share changed.

### 2026-10-07 — Write each finished return period before the next
- **Decision:** `scripts/build_exposure.py` parks each period in `data/processed/exposure_parts/`, named with its parameters, and reuses it unless `--rebuild`.
- **Why:** The OOM killer stopped the build during RP100 at 15.7 GB of a 16 GB cap, losing six finished periods kept only in memory.
- **Effect:** No figure changed; rebuild runs at `--stripes 72`. Tests 452 → 473.

### 2026-10-07 — Nine return periods for expected annual exposure
- **Decision:** `exposure.parquet` now covers nine return periods (RP10–RP500), 12,105 rows, not RP100 and RP500 only.
- **Why:** Two points spanned only 0.8% of the probability axis (0.002–0.01) and missed the frequent floods that dominate the integral.
- **Effect:** Total `expected_annual_exposure` 260,849 → 2,335,501 (~89% understated); NL364 14th → 6th; RP100 29,727,887.

### 2026-10-07 — Far-future period gets its second model chain *(superseded 2026-10-25)*
- **Decision:** `VIC-WUR-EUR-11` fetched for 2071–2100 via `scripts/fetch_cds_member.py`, and `context.parquet` rebuilt with 2 members.
- **Why:** 2071–2100 ran on `E-HYPEgrid-EUR-11` alone, so its median came from one chain and sign agreement was 0 by construction.
- **Effect:** 2071–2100 median +25.6% → +20.3%; agreeing regions 0 → 943 (78.7%), with median +26.3% among them.

### 2026-10-08 — `shared_with` now read from shared basins only
- **Decision:** `_others` reads partner countries from the region's shared basins only, so `shared_with` and `shared_basin_share` come from the same basins.
- **Why:** Border slivers under `MIN_COUNTRY_AREA_M2` (50 km²) still added partners: 58 of 1,345 regions had a partner list their own share (0.0) denied.
- **Effect:** 34 regions changed (33 lost a sliver-only list, BG413 lost `EL`); on rebuild, non-empty `shared_with` 810 = `shared_basin_share > 0` 810, contradictions 0. Tests 432 passed / 2 failed.

### 2026-10-08 — Two vulnerability indicators keep their published units
- **Decision:** Units left as published, now written in the `poverty_rate` docstring and pinned by `test_the_two_indicators_keep_their_published_units`; `apsfr_share` limits and the IE gap are written down.
- **Why:** `poverty_rate` spans 1.4–50.7 (%) and `share_over_65` 0.027–0.372 (fraction), with no unit in either name; `apsfr_share` spans 99.908 % (BE) to 0.004 % (ES, CY).
- **Effect:** No figure changed (min-max index is unaffected); cross-country ranking of `apsfr_share` ruled out; Ireland missing from both EEA cycles. Tests 433 passed / 2 failed.

### 2026-10-08 — Offline SVG choropleth added: the app had no map
- **Decision:** New `src/svgmap.py` draws an inline SVG choropleth (EPSG:3035, quantile classes, outermost regions drawn but left out of the frame, no-data in grey); `regions.geojson` keyed in `_frozen()`.
- **Why:** The map tab drew a bar chart and a table; `folium` was declared but never imported, and Leaflet tiles need network access the offline demo forbids.
- **Effect:** Extent 12,850 × 9,486 km → 4,680 × 4,029 km; 7 grey regions at RP100 (first given as 8). Tests 433 passed / 2 failed → 449 passed / 2 failed.

### 2026-10-08 — Draft tab fixed: 413 fallback, ranked prompt, Groq key rotation
- **Decision:** A 413 now falls back to the local model, the prompt is built from the selected `view`, ranked and trimmed by `toon_io.fit_rows`, and `_groq` rotates the five keys on 429/401/403.
- **Why:** The Groq 8,000 TPM limit (`Requested 14931`) was treated as a config error, and the prompt was `exposure.head(200)`: AL011–DE132 at RP10, 29,718 chars.
- **Effect:** Prompt 29,718 → 10,913 chars (~5,323 tokens), live call succeeds with 68% grounding; tests 449 → 508 passed, 0 failed.

### 2026-10-08 — Map rendered in an iframe; discharge-by-horizon layer added *(superseded 2026-10-25)*
- **Decision:** SVG rendered with `st.components.v1.html` instead of `st.html`; added a discharge-change layer by horizon with hatching where the models disagree on the sign; display/column period key bug fixed.
- **Why:** `st.html` runs DOMPurify, which stripped the SVG, so the DOM had no map while the caption reported "1,338 regions coloured, 7 grey"; `2041-2070` raised `KeyError` as a column key.
- **Effect:** 1,345 paths, 1088 x 749 px; at 2041-2070: 1,198 coloured, 147 grey, 204 hatched (later 728 robust, 470 hatched, 147 grey). Tests 508 passed, 0 failed.

### 2026-10-08 — `measured` name collision crashed the draft tab
- **Decision:** A single `has_exposure` flag is defined beside `view`, the context tab's frame is renamed `with_share`, untracked modules are staged, and the budget lives in `rag.PROMPT_CHAR_BUDGET`.
- **Why:** The context tab rebound `measured` to a DataFrame, so any draft question raised `ValueError: The truth value of a DataFrame is ambiguous` wherever `context.parquet` existed.
- **Effect:** Tests 511 passed, 0 failed (one new test that failed before the repair).

### 2026-10-08 — Horizon radio, unlinked doc links, log rows added inside the table
- **Decision:** `st.select_slider` replaced by a horizontal `st.radio`; `usage_log.unlink_relative_docs` drops relative links; `usage_log.append_row` inserts after the last table row.
- **Why:** The 12 × 12 px handle sat below the fold (y = 633 in a 639 px viewport), relative links reopened the app, and new entries landed after the table as plain text.
- **Effect:** Tests 511 passed, 0 failed (three new); 43 passed on the module both with and without the tables.

### 2026-10-08 — Loaders cached "no table" forever
- **Decision:** Each loader is split: an uncached `_build_state(path)` returns the mtime or `None`, and the cached half is keyed on that mtime; the test `Path.stat` stub now raises for absent artefacts.
- **Why:** `@st.cache_data` cached a `None` return, so a page that once ran without `exposure.parquet` (12,105 rows on disk) kept saying "No exposure table yet".
- **Effect:** Tests 513 passed, 0 failed.

### 2026-10-08 — `st.iframe` with content height; map legend now visible
- **Decision:** Deprecated `st.components.v1.html` replaced by `st.iframe` with `height="content"`; a new test reads the iframe `srcdoc` and counts one `<title>` per region.
- **Why:** The call was past its 2026-06-01 removal date, and a fixed `height=640` clipped the 739px SVG, putting all legend labels at y=718 out of view.
- **Effect:** Frame 755px for a 739px SVG, 0 clipped labels (1,345 paths; 1,549 with 204 hatched at 2041-2070). Tests 513 passed, 0 failed.

### 2026-10-08 — Directive Art. 6(3) scenarios and statutory-map caveat added *(superseded 2026-10-23)*
- **Decision:** Captions now place the selected return period against Art. 6(3) of 2007/60/EC and state that the statutory maps are the Member States' own (EEA viewer); `CITATION.cff` 0.1.0 added, with no licence.
- **Why:** The app offered RP10–RP500 without saying how any of them maps to the Directive's low/medium/high probability scenarios, or that it is not the statutory map.
- **Effect:** No number changed meaning; tests 45 → 47 in `tests/test_streamlit_app.py`, 47 passed with artefacts hidden. Licence later set to MIT.

### 2026-10-08 — Legal citations registry with CELEX, URL and test
- **Decision:** `config/legislation.yaml` holds 15 instruments and `src/legislation.py::cite` renders citations; a test checks every Article cited in `docs/policy_answer.md` against the registry.
- **Why:** CELEX numbers and URLs lived only in `docs/policy_context.md`; eur-lex returns 202 to scripts, so they were checked via Cellar SPARQL instead (SWD(2021) 305 has no CELEX).
- **Effect:** No figure changed; 7 new tests in `tests/test_legislation.py`.

### 2026-10-08 — `docs/` index and consolidated limitations page
- **Decision:** Added `docs/README.md` (reading order, size per file) and `docs/limitations.md` (25 limitations, 12 not built, 10 authority tasks, 11 accepted risks).
- **Why:** 15 files (356.6 KB) with no index, and limitations scattered across docs, docstrings and this file.
- **Effect:** No figure changed; grey count corrected 8 → 7, §7 test table rebuilt (473 over 22 files → 25 files); 132 links, 0 broken.

### 2026-10-08 — `scripts/docs_numbers.py` writes measured numbers into the docs
- **Decision:** Numbers are measured from their artefacts and written into `<!-- numbers:KEY -->` blocks; `tests/test_docs_numbers.py` runs `--check`; "verified" now excludes `verified: null`.
- **Why:** The suite count was hand-edited seven times (441→…→513), and a stale 473 survived for hours in one doc.
- **Effect:** Verified sources 36 → 34; 8 new tests.

### 2026-10-08 — Unmeasurable facts skipped by `--check`, not flagged stale
- **Decision:** A fact that cannot be measured on this machine is left as written and reported once on stderr, never treated as stale; two tests added.
- **Why:** CI has no `data/`, so `nuts3_regions` came back `'unbuilt'` and failed the suite: `1 failed, 529 passed` on the runner.
- **Effect:** Tests 532 passed, 0 failed; §7 row 8 → 10.

### 2026-10-09 — React map no longer framed on overseas regions
- **Decision:** `web/src/components/Choropleth.jsx` mirrors `OUTERMOST`: the 16 outermost regions are still drawn but no longer set the viewBox, and the caption counts them.
- **Why:** The viewBox covered every feature, which shrank continental Europe to a strip.
- **Effect:** Extent 119.0 × 102.2 → 69.3 × 36.6 degrees (4.8× area); no measurement changed; `npm run build` passes.

### 2026-10-10 — Offline check gets three verdicts; reused files must pass body check
- **Decision:** Readiness verdicts are now `READY`/`READY WITH CAVEATS`/`BLOCKED`; `why_not_a_document_on_disk` checks reused files; colliding paths are refused; tiktoken is guarded; CI docker job; legend shows class rank.
- **Why:** The check said "runs offline" while a Groq key needed Wi-Fi, a 31-byte WAF page was reused as `ok=True`, and a tokenizer fetch failure broke 12 tests.
- **Effect:** No figure changed; legend reads "6/6 · 10.6% to 75.5%".

### 2026-10-10 — Ollama default set to `llama3.2:3b`
- **Decision:** `src/rag.py` falls back to `llama3.2:3b` instead of `llama3.1`; `.env.example`, the checker and `docs/limitations.md` follow, pinned by a test.
- **Why:** The container reads no `.env`, so it asked for `llama3.1`, which was not pulled: "model not found" in the image only.
- **Effect:** No figure changed.

### 2026-10-11 — Docker image installs `libexpat1`
- **Decision:** `apt-get install --no-install-recommends libexpat1` added before the pip layer of the `app` stage.
- **Why:** `python:3.12-slim` lacks libexpat, so the import step failed with `ImportError: libexpat.so.1` on the first CI docker run.
- **Effect:** Build completes, the four imports load, and readiness reports `BLOCKED - 4 blocking` (exit 1); test count re-dated (551 passed).

### 2026-10-12 — Plain-language questions over the exposure table (`/api/ask`)
- **Decision:** New `src/nlquery.py` and `POST /api/ask` turn a question into a validated JSON query spec that pandas runs; nothing the model writes is evaluated.
- **Why:** `limitations.md` §2 listed plain-word querying as designed but not built, for people who do not write pandas (`roles.md` hat 3).
- **Effect:** no figure changed (39 fixed API requests byte-identical before/after); tests 569 → 623.

### 2026-10-12 — Twelve cited policy sources declared; arXiv PDF now indexed
- **Decision:** Twelve of thirteen sources cited in `policy_context.md` declared in `config/sources.yaml` (EU acts via CELLAR), and an entry may now declare `suffix:`.
- **Why:** Undeclared sources could not be cited back, and `nist_robust_ai_alignment_limits` was stored as `.10100`, which `rag._read` does not parse.
- **Effect:** that paper 0 characters/0 passages → 25,592 characters/32 passages; corpus 13 → 24 entries; declared inputs 42 → 54; files 52 → 64; tests 569 → 586.

### 2026-10-12 — `poverty_rate` renamed `poverty_rate_pct`
- **Decision:** `poverty_rate` and companions renamed `poverty_rate_pct`, `poverty_rate_pct_year`, `poverty_rate_pct_level`; legacy names read via `with_current_names` for one release.
- **Why:** A table showing 14.0 beside 0.19 did not say which one was the percentage (item left open on 2026-10-08).
- **Effect:** no figure changed (39 requests identical after mapping 51,110 legacy keys); tests 569 → 579.

### 2026-10-12 — Density and income added to context; GDP year rule fixed
- **Decision:** `pop_density_per_km2` and `household_income_pps_per_hab` added to `context.parquet`; `demographics._latest` takes the first year covering >= 90 % of the prior year's regions.
- **Why:** The old "most recent year with any value" rule picked GDP 2024 with 536 regions published, against 1,307 for 2023.
- **Effect:** `gdp_meur` 524 regions (2024) → 1,292 regions (2023); density 1,279 of 1,345 regions, income 1,165; tests 569 → 577.

### 2026-10-12 — Natura 2000 flooded area: first environmental figure
- **Decision:** Four Natura 2000 columns added to `context.parquet`, measured on the hazard raster's own 3 arc-second grid by `src/environment.py`.
- **Why:** Floods Directive Art. 6(5) asks for adverse environmental consequences; the kit measured only people and buildings.
- **Effect:** 1,159 regions measured; 769,990 km2 of Natura land, 38,246 km2 (5.0 %) flooded at RP100; grid vs vector within 0.3 %; tests 569 → 586.

### 2026-10-12 — Ensemble members keyed by regional model; quartiles added
- **Decision:** `ensemble_change_by_region` labels members by regional model too, refuses duplicate simulations, and adds `change_pct_ensemble_p25/p75_<period>`.
- **Why:** Three regional models driven by the same EC-EARTH run shared one label and silently overwrote each other.
- **Effect:** synthetic test 1 member, median +30 % → 3 members, +20 %; no existing column moved; 42 of 48 CDS requests missing; tests 569 → 579.

### 2026-10-12 — Three data layers merged onto one context table
- **Decision:** Eurostat, Natura 2000 and CDS-ensemble branches merged; `build_context.py --stripes 72` written to `context.data-layers-12-10.parquet`.
- **Why:** Bring the three new data layers into one table while leaving the frozen `context.parquet` and `exposure.parquet` untouched.
- **Effect:** 29 → 46 columns; `gdp_meur` differs in 1,292 rows (year change); built-up columns differ by at most 5.0e-10 relative; tests 650 → 685.

### 2026-10-13 — Far-apart chains dropped from the increase ranking *(superseded 2026-10-25)*
- **Decision:** `ensemble_size_uncertain_<period>` flags regions whose chains' medians lie over `MODEL_SPREAD_PP` = 100 points apart; both UIs drop them from "largest increases".
- **Why:** DE94H (+253.2%) and DK014 (+210.0%) topped the ranking as the mean of two disagreeing hydrological models (e.g. +92% vs +414%).
- **Effect:** left out 3 of 976 (2011-2040), 13 of 994 (2041-2070), 47 of 943 (2071-2100); 2071-2100 top becomes BE233 (+183.8%); medians unchanged.

### 2026-10-14 — `fetch_cds_member.py` resolves `OUT_DIR` at call time
- **Decision:** `on_disk`, `missing` and `fetch` default `out_dir` to `None` and read `OUT_DIR` when called.
- **Why:** The import-bound default ignored the test's patch, so with CDS files on disk the dry-run test counted 42 missing instead of 48 and failed.
- **Effect:** WSL2 suite 701 passed / 1 failed → 702 passed; no analysis figure changed.

### 2026-10-16 — Two CodeQL alerts closed; fetch throttle fixed
- **Decision:** `nlquery.parse` drops its fence regex, `_public_token_report` builds a fresh dict, and `_HostThrottle.wait` sleeps in a loop until its slot.
- **Why:** The regex was quadratic (0.564 s at 20,000 spaces), the overwritten dict left a possible stack-trace path, and one `time.sleep` returned early on Windows.
- **Effect:** throttle test failed 7 runs in 10 → 0 in 10; no figure changed.

### 2026-10-19 — Linux test warnings cut from 1,141 to 0
- **Decision:** New `pytest.ini` ignores one `rasterstats.io` `PendingDeprecationWarning`; a regex in `tests/test_offline_readiness.py` becomes a raw string.
- **Why:** 1,140 third-party warnings buried one invalid escape sequence of ours, which raises `SyntaxError` under `-W error`.
- **Effect:** Linux 703 passed / 1,141 warnings → 703 passed / 0 warnings; no figure changed.

### 2026-10-19 — Docker image carries `docs/`, `README.md` and `pytest.ini`
- **Decision:** The `app` stage of the `Dockerfile` copies `docs/`, `README.md` and `pytest.ini`.
- **Why:** `usage_log.append_row` raised `FileNotFoundError` in the container, and 4 tests failed reading `README.md` and `docs/`.
- **Effect:** `docker compose run test` 699 passed / 4 failed / 1,140 warnings → 703 passed / 0 failed / 0 warnings; no figure changed.

### 2026-10-20 — Claude asked first when `ANTHROPIC_API_KEY` is set
- **Decision:** `rag.complete_with_provider` calls Claude via the `anthropic` SDK before Groq then Ollama, default `claude-haiku-5-5`; 429, 5xx and connection errors fall back.
- **Why:** The project had paid Anthropic API credit and no code path could reach it.
- **Effect:** no figure changed (the Haiku default was replaced by `claude-opus-5-5` on 2026-10-23).

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
