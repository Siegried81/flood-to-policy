# Priority scoring methodology

> **Stage 4 (30 Oct 2026):** these asset scores are now optional context layers of `flood_map.html` (scenes 2 and 4);
> the separate `priority_map.html` is retired and its P/B/F **area** shading is no longer shown. The area view in
> `flood_map.html` is the *scenario-based planning priority* (README, "Presentation scenes"), a different score that is
> never combined or compared with the asset scores below.

The asset screening scores rank **vulnerable facilities** and **critical infrastructure** for flood preparedness, using the
exposure observed during the July 2021 floods (Belgium, Germany, Netherlands). It is a **historical,
exposure-informed screening tool**. It is not a flood forecast, an estimate of probabilities or casualties, or an
operational emergency instruction. A score tells you *where to look first*, not *what will happen*.

Code: `priority/scoring.py` (formulas), `priority/indicators.py` (spatial indicators), `priority/osm.py` (assets),
`priority/assets.js` (the same formulas in the browser, in `flood_map.html`). Tests: `tests/`.

## 1. Scoring scope and units

| Item | Definition |
|---|---|
| Study area | The Copernicus EMS areas of interest (EMSR517 DE, EMSR518 BE, EMSR520 NL) plus 1 km, the same read region as `map.py` (≈ 11,400 km², 82,162 hexagons). Scores are not defined outside it. |
| Analysis grid | 400 m hexagons in EPSG:3035 (equal-area, metres), the same axial grid as `map.py` (≈ 0.139 km² each). |
| Neighbourhood | A hexagon and its 6 neighbours (≈ 0.97 km²). This matches the resolution of GHS-POP (30″ ≈ 0.55 km² cells) and avoids implying building-level precision for population. |
| Assets | Individual OSM features (never aggregated away). An asset takes the indicators of its own hexagon's neighbourhood, plus a direct flood test on its own geometry. |
| Comparability | Scores are comparable **within one ranking** (facilities *or* infrastructure) and within the study area. The references are fixed study-wide, so filters (country, view, category) never change a score. |

## 2. The three common indicators

### P: population exposure
Raw value: residents (GHS-POP E2020, R2023A) in the neighbourhood. Each 30″ cell is shared among the hexagons
by **intersection area**, so the cell totals are conserved (tested). Areal weighting is used on purpose: it keeps P
independent of OBAT at this step.

### B: building exposure
Raw value: GHS-OBAT R2024A building points in the neighbourhood. These come from the `map.py` cache, where buildings were
already de-duplicated by `id` across overlapping AOIs. Each building is a point, so it is counted in exactly one hexagon.

### F: July 2021 historical flood exposure
EMS `observedEventA` polygons are merged into **one non-overlapping extent**: union of all "Flooded area" polygons,
plus the union of "Flood trace" polygons minus the flooded areas. Activations overlapping at AOI borders are therefore counted once (tested).
Both kinds count as observed flooding. They stay distinguishable in the map, the popups (`flooded` vs `trace`
status) and the code (`a_flood`, `a_trace`).

* **Areas (hexagons):** `flood_share = (flooded + trace area) / mapped area` in the neighbourhood, where the mapped area is
  the area inside the EMS areas of interest. If less than 50 % of the neighbourhood was mapped, F is **unknown**
  (NaN), never 0.
* **Assets:** F = 1 if the asset geometry, buffered by 25 m, intersects the observed extent. The buffer covers
  point-vs-footprint offsets, positional error, and the river channel under bridges, which EMS excludes from flood polygons.
  Otherwise F = the normalised flooded share of the mapped part of the neighbourhood. If the asset lies outside the
  EMS mapped area and was not hit, F is **unknown**.

Status per asset: `flooded`, `trace`, `near` (flooding in the neighbourhood), `dry` (mapped, no flooding detected) and
`unmapped` (unknown).

## 3. Normalisation (0–1)

| Indicator | Transform | Reference (fixed, whole study area) | Why |
|---|---|---|---|
| P | `min(1, ln(1+x) / ln(1+ref))` | ref = 99th percentile of positive neighbourhood values = **5,281 residents** | Heavy-tailed counts. The log stops city centres from flattening all other places. The 99th-percentile cap removes the influence of single outliers (tested). This is the approach of the JRC INFORM Risk Index (log transform + min-max). |
| B | same | ref = **2,170 buildings** | same |
| F (area share) | `min(1, x / ref)` | ref = 99th percentile of positive shares = **0.434** | Already a bounded proportion with a direct meaning. A log would inflate tiny shares, which are the least reliable part of a satellite delineation (edge slivers). |

Reading the scale: P = 0.28 / 0.54 / 0.81 for 10 / 100 / 1,000 residents. B = 0.31 / 0.60 / 0.90 for 10 / 100 / 1,000 buildings.

**Meaning of 0–100:** 100 = the highest exposure observed in the study area on every indicator that carries
weight, for the most sensitive asset type. 0 = no residents, no buildings and no observed flooding. The score is
*relative* to this study area. It is not a probability, and 60 is not "twice as risky" as 30.

## 4. Weights

`S_base = (Wp·P + Wb·B + Wf·F) / (Wp + Wb + Wf)`. The weights come from three 0–100 % sliders and are always rescaled to sum to 1.
The page shows the effective percentages. All zero falls back to equal weights. Negative values are rejected (tested).

**Default 40 / 30 / 30 (population / buildings / flooding):** an illustrative starting point, **not** a
scientifically established optimum. Changing the weights changes the prioritisation *assumptions*, not the evidence.

## 5. Score A: vulnerable population and essential services (`S_people`)

`S_people = 100 × M_type × S_base`, with `M_type = 0.5 + 0.5 × I` and `I = (D + O) / 2`.

* **D: dependency on assistance to evacuate** (0 / 0.5 / 1)
* **O: overnight occupancy** (0 / 1)

| OSM category (tags) | D | O | M |
|---|---|---|---|
| Hospital (`amenity=hospital`, `healthcare=hospital`) | 1 | 1 | 1.00 |
| Nursing / elderly care home (`social_facility=nursing_home`, `amenity=nursing_home`, `healthcare=nursing_home`) | 1 | 1 | 1.00 |
| Assisted living, group home (`social_facility=assisted_living / group_home`) | 0.5 (1 if `social_facility:for` = senior / disabled / mental_health) | 1 | 0.875 (1.00) |
| Shelter (`social_facility=shelter`) | 0.5 | 1 | 0.875 |
| Adult day care (`social_facility=day_care`) | 1 | 0 | 0.75 |
| Kindergarten / childcare (`amenity=kindergarten / childcare`) | 1 | 0 | 0.75 |
| School (`amenity=school`) | 0.5 | 0 | 0.625 |
| Clinic / health centre (`amenity=clinic`, `healthcare=clinic / centre / rehabilitation`) | 0.5 | 0 | 0.625 |
| Other social facility (`amenity=social_facility`, sub-type unknown) | unknown → 0.5 | unknown → 0.5 | 0.75, flagged `type_assumed` |

Excluded: food banks, soup kitchens, outreach, doctors' practices and pharmacies (no residential or dependent occupancy).

* The D and O values are **expert assumptions**, not observations. Every popup shows them.
* M is multiplicative and has a floor of 0.5. The type can at most halve a score, and it **never creates priority without
  exposure** (zero exposure stays zero, tested). A nursing home and a school in the same place therefore differ, and a nursing
  home in an unexposed place still scores low.
* **Occupancy is never used.** OSM rarely holds beds, residents or pupils. When a `capacity`/`beds` tag exists it is shown
  as "OSM tag, unverified, not used". Using it would reward only the facilities that happen to be tagged.
* Four concepts are kept apart:
  1. Population exposure (P, from GHS-POP).
  2. Presence of a potentially vulnerable facility (OSM category).
  3. Confirmed capacity (unknown, shown as unknown).
  4. Estimated vulnerability (M, an assumption).

**Areas:** the hexagon shading uses `100 × S_base` (no type factor). It answers "where were people and buildings
exposed?", independently of whether OSM lists a facility there. **An area without OSM facilities is not an area
without vulnerable people.**

## 6. Score B: critical infrastructure (`S_infrastructure`)

`S_infrastructure = 100 × M_func × S_base`, with `M_func = 0.5 + 0.5 × I_func`. It differs from Score A in two ways:
F is measured on the asset's own geometry (the bridge line, the substation polygon), and the factor describes function, not occupants.

| Category (OSM tags) | I_func |
|---|---|
| Bridge carrying a motorway or trunk road, or a mainline railway (`bridge=*` on `highway=motorway/trunk(_link)`, `railway=rail`) | 1.0 |
| Bridge on a primary / secondary / tertiary road, or light rail | 0.85 / 0.7 / 0.55 / 0.7 |
| … × 0.8 if the bridge does not touch the EMS reference water layer (+10 m), e.g. an overpass over a road: less exposed to flood flow (assumption) | |
| Road tunnel / underpass (motorway–secondary), rail tunnel (`tunnel=*` except `building_passage`) | same road and rail classes |
| High-voltage substation (`substation=transmission` or ≥ 110 kV) | 1.0 |
| Distribution substation (`substation=distribution` or ≥ 10 kV) | 0.7 |
| Substation, voltage unknown | 0.6, flagged `type_assumed` |
| Power plant | 0.8 |
| Drinking-water works / wastewater plant / pumping station / water tower | 1.0 / 0.8 / 0.6 / 0.6 |
| Fire station, ambulance station / police | 1.0 / 0.8 |

Excluded on purpose: ordinary road segments, residential and unclassified road bridges, and street transformer kiosks
(`substation=minor_distribution`).

* **Bridges are structures, not buildings.** Ways from the same structure are merged into one asset: ways within 15 m of each other (dual
  carriageways, segmented viaducts), or ways inside the same `man_made=bridge` outline. The importance is that of the most
  important carried line. Outlines carrying none of the selected lines are dropped (tested).
* **Network importance:** the road or rail class is the only network signal used. It is an explainable proxy for
  traffic function. **No** connectivity, detour, redundancy or service-area analysis was done. The tool never claims that a bridge
  is essential for emergency access, or that a substation supplies a given area. Those dependencies are not in the data, so the
  popups show "Data unavailable".

## 7. Missing data: one treatment per meaning

| Missing item | Meaning | Treatment | Effect shown to the user |
|---|---|---|---|
| F outside EMS coverage | Not observed ≠ not flooded | Excluded from the score. Weights renormalised over P and B. **Status "insufficient historical evidence": not ranked by default** (opt-in checkbox). Bounded range given for F = 0 … 1 | Hollow marker, grey hexagon, "not ranked", range in the popup |
| F in Belgium where nothing was detected | EMS BE products have no flood traces and miss urban water (e.g. Pepinster, Verviers) | Value kept (it was mapped) | Flag `BE_detection`: weak evidence of absence |
| B = 0 although the neighbourhood has ≥ 100 residents (324 hexagons) | Likely OBAT gap, not "no buildings" | B excluded, weights renormalised (P is a correlated proxy, see §8) and bounded range shown | Flag `B_gap`, quality Low |
| Facility sub-type (D or O) unknown | Unknown vulnerability | Mid value 0.5, never 0 or 1 | Flag `type_assumed` |
| Capacity, occupancy, enrolment | Not in the data | Not used, not estimated | "Unknown (not in OSM)" |
| Bridge condition, dependencies, service areas | Not in the data | Not used | "Data unavailable" |
| OSM asset newer than July 2021 (`start_date`) | May not have existed during the event | Kept and scored on its location | Flag `post_2021` |
| OSM tile failed or outdated | Facilities may be missing | Cached copy kept and marked stale. Never replaced by invented features | Warning in the sidebar |

**Why F-unknown assets are not ranked:** with F excluded, a dense city outside EMS coverage reaches P = B = 1 and a score
of 100. An earlier build of this tool did exactly that: its first three ranks were all outside coverage. That is
missing data inflating priority, the mirror image of treating it as safe. A renormalised score without the
event-specific indicator is not comparable with one that has it. Renormalisation is still used for B, because P is a strongly correlated stand-in for it.

**Bounded range:** a missing normalised indicator lies in [0, 1] by definition. The range `[score with missing = 0,
score with missing = 1]` is therefore exact, not a statistical interval. No other uncertainty intervals are produced, because
there is no statistical basis for them.

**Evidence quality** (kept separate from the score): **High** = no flag. **Medium** = one minor flag. **Low** = F
unknown, B gap, or two or more flags. A high score with Low quality is shown as such in the ranking (coloured dot) and in the popup.

## 8. Dependencies and double counting

* **P and B are correlated** (r = 0.88 between ln(1+P) and ln(1+B) over all hexagons). GHS-POP is itself partly derived
  from built-up data (GHSL), so the two are **not independent evidence**. At the default weights, 70 % of the score is
  effectively "settlement density". Users who want the event to dominate should raise the flooding weight. The "July 2021 flooding:
  observed at or near the asset" filter answers "which exposed facilities were actually reached by the water?".
* **No feature is counted twice:**
  * OBAT buildings are de-duplicated by id.
  * Flood polygons are merged into one non-overlapping extent.
  * OSM elements are de-duplicated by (type, id) across tiles.
  * A node inside a polygon of the same category is dropped (its name is kept).
  * Nested same-category polygons keep the largest.
  * Bridge carriageways are merged.
  * Each asset joins exactly one hexagon (tested: one output row per asset).
* A hospital is scored only in the vulnerable-population ranking, not also as infrastructure.

## 9. Sensitivity analysis

For each ranked asset, the score is recomputed under 36 weight sets: every combination on a 10 % grid with each weight ≥ 10 %.
The popup reports the best and worst rank and the share of weight sets in which the asset is in the top 25.
`top_share = 100 %` means it is a priority **whatever the weights**. A wide rank range means its position depends on the
assumptions. This is computed in Python at build time, for all countries.

## 10. Temporal frame

| Layer | Time reference |
|---|---|
| Observed flooding | Copernicus EMS activations EMSR517/518/520, July 2021 (satellite snapshots, not necessarily the peak; acquisition times on the activation pages) |
| Population | GHS-POP epoch 2020 |
| Buildings | GHS-OBAT R2024A, epoch 2020 |
| Facilities and infrastructure | OpenStreetMap at download time (2026). They are **not** a 2021 inventory: destroyed bridges may now appear rebuilt, and new schools may not have existed |
| EFAS hazard | Modelled 10-, 100- and 500-year return periods (context only, **not used in the scores**) |

## 11. Main limitations

1. EMS under-detects flooding in towns and narrow valleys, and in Belgium in particular. F is therefore a lower bound, and "dry" is weak evidence.
2. P and B are about 1 km² neighbourhood measures. They do not describe who is inside a given building.
3. Type factors, road classes and the bridge water factor are expert assumptions, editable in `priority/osm.py`.
4. OSM completeness varies by country and category. Missing facilities do not appear in the rankings, but their area does
   appear in the hexagon layer.
5. There is no network, dependency, condition or capacity analysis.
6. The score is a relative screening index inside one study area, with no external validation against damage data.
   A natural next step would be to validate against the EMS grading products (`builtUpP` damage grades), which exist only in Germany.
