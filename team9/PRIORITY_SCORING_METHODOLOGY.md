# Priority scoring methodology (asset screening scores)

These scores rank **vulnerable facilities** and **critical infrastructure** for flood
preparedness, using the exposure observed in July 2021 (BE, DE, NL). They are optional
context layers of `flood_map.html` (scenes 2 and 4) and are a **different score** from the
scenario-based planning priority of scene 4: the two are never combined or compared. A
score says where to look first, not what will happen: it is not a forecast, a probability
or an operational instruction. Code: `priority/scoring.py` (formulas),
`priority/indicators.py`, `priority/osm.py` (assets), `priority/assets.js` (the same formulas
in the browser). Tests: `tests/`.

## 1. Scope

The EMS areas of interest (EMSR517 DE, EMSR518 BE, EMSR520 NL) plus 1 km, on the 400 m
hexagon grid of `map.py` (EPSG:3035). An asset takes the indicators of its hexagon and its
6 neighbours (about 0.97 km2, matching GHS-POP's 30 arc-second cells), plus a direct flood
test on its own geometry. Scores are comparable within one ranking (facilities or
infrastructure) and within the study area; the references are fixed study-wide, so filters
never change a score.

## 2. Indicators and normalisation (0-1)

| Indicator | Raw value | Transform and fixed reference |
|---|---|---|
| P population | GHS-POP E2020 residents in the neighbourhood, cells shared by intersection area (conserved) | `min(1, ln(1+x)/ln(1+ref))`, ref = 99th percentile of positive values |
| B buildings | GHS-OBAT R2024A points (de-duplicated by id) | same |
| F July 2021 flooding | EMS flooded areas plus traces merged into one non-overlapping extent; areas: flooded share of the mapped part of the neighbourhood; assets: 1 if the geometry buffered by 25 m meets the extent | `min(1, x/ref)`, ref = 99th percentile of positive shares |

The log keeps city centres from flattening everything else; no log for F because tiny
shares are the least reliable part of a satellite delineation. F is unknown (not 0) when
under half the neighbourhood was mapped or the asset lies outside EMS coverage. Asset status:
`flooded`, `trace`, `near`, `dry`, `unmapped`. A score of 100 is the highest exposure seen in
the study area on every weighted indicator for the most sensitive asset type; it is relative,
and 60 is not twice as risky as 30.

## 3. Weights

`S_base = (Wp*P + Wb*B + Wf*F) / (Wp + Wb + Wf)`; three sliders, rescaled to sum to 1, all
zero falls back to equal weights, negatives are rejected. The default 40/30/30 is an
illustrative starting point, not an optimum: changing it changes assumptions, not evidence.

## 4. Score A: vulnerable population and essential services

`S_people = 100 * M_type * S_base`, `M_type = 0.5 + 0.5 * (D + O) / 2`, with D the dependency
on assistance to evacuate (0 / 0.5 / 1) and O overnight occupancy (0 / 1). Examples:
hospital and nursing home D=1, O=1, M=1.00; assisted living M=0.875; kindergarten and
day care M=0.75; school and clinic M=0.625; unknown social facility mid values (0.5) and
flag `type_assumed`. Food banks, outreach, practices and pharmacies are excluded. D and O are
expert assumptions shown in every popup. M has a floor of 0.5: type can at most halve a
score and never creates priority without exposure. Capacity, beds and enrolment are never
used (OSM rarely holds them, and using them would reward the tagged ones); a tag is shown as
"OSM tag, unverified, not used". Hexagon shading uses `100 * S_base`: an area without OSM
facilities is not an area without vulnerable people.

## 5. Score B: critical infrastructure

`S_infrastructure = 100 * M_func * S_base`, `M_func = 0.5 + 0.5 * I_func`, with F measured on
the asset's own geometry. I_func: bridge on a motorway, trunk road or mainline railway 1.0
(primary 0.85, secondary 0.7, tertiary 0.55, light rail 0.7; times 0.8 if it does not touch
the EMS reference water layer), tunnels likewise; transmission substation 1.0, distribution
0.7, unknown voltage 0.6 (`type_assumed`); power plant 0.8; water works / wastewater plant /
pumping station / tower 1.0 / 0.8 / 0.6 / 0.6; fire station 1.0, ambulance and police 0.8.
Bridges are structures: ways within 15 m or inside one `man_made=bridge` outline merge into
one asset. Road or rail class is the only network signal: no connectivity, detour or
service-area analysis, so the tool never claims a bridge is essential for access or that a
substation supplies an area ("Data unavailable" in the popup). A hospital is scored only in
Score A.

## 6. Missing data

| Missing | Treatment |
|---|---|
| F outside EMS coverage | excluded; status "insufficient historical evidence", not ranked by default (opt-in); bounded range for F = 0 to 1 |
| F in Belgium where nothing was detected (no traces, urban water missed) | kept, flag `BE_detection` |
| B = 0 although at least 100 residents | likely OBAT gap: B excluded, weights renormalised, flag `B_gap`, quality Low |
| Facility sub-type unknown | mid value 0.5, flag `type_assumed` |
| Capacity, occupancy, condition, dependencies | not used, shown as unknown |
| OSM asset newer than July 2021 | kept, flag `post_2021` |
| OSM tile failed | cached copy kept and marked stale; nothing invented |

Unranked-by-default for unknown F matters: with F excluded a dense city outside coverage
reaches P = B = 1 and a score of 100 (an earlier build ranked such assets first), which is
missing data inflating priority. The bounded range `[score with missing = 0, score with
missing = 1]` is exact, not statistical; no other intervals are produced. Evidence quality:
High (no flag), Medium (one minor flag), Low (F unknown, B gap or two or more flags), shown
beside the rank.

## 7. Dependencies, sensitivity, time

- P and B are correlated (r = 0.88 on the log values; GHS-POP derives partly from built-up
  data), so at default weights about 70 % of the score is settlement density; raise the
  flooding weight or use the "flooding observed at or near the asset" filter for event impact.
- Nothing is counted twice: OBAT by id, flood polygons merged, OSM by (type, id), nested
  same-category polygons keep the largest, carriageways merged, one row per asset.
- Sensitivity: each ranked asset is rescored under 36 weight sets (10 % grid, each weight at
  least 10 %); the popup gives best and worst rank and the share of sets in the top 25.
- Time frames: flooding July 2021 EMS snapshots (not the peak); population and buildings
  epoch 2020; facilities and infrastructure OpenStreetMap at download (2026), not a 2021
  inventory; EFAS is context only, not in the scores.

## 8. Limitations

EMS under-detects flooding in towns, narrow valleys and Belgium, so F is a lower bound and
"dry" weak evidence; P and B are about 1 km2 measures, not who is in a building; type
factors, road classes and the bridge water factor are expert assumptions (`priority/osm.py`);
OSM completeness varies; there is no network, condition or capacity analysis; the score is a
relative screening index with no external validation (the German `builtUpP` damage grades
would allow one).
