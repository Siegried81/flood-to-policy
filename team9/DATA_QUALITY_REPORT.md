# Data quality report: asset screening scores

> **Stage 4 (30 Oct 2026):** these are the asset-screening quality numbers, now optional context layers of
> `flood_map.html` (scenes 2 and 4); the separate `priority_map.html` is retired. `priority_map.py --summary`
> still prints them.

The numbers below come from `python priority_map.py --offline --summary` (build of 2026-10-29). Categories used:

| Term | Meaning |
|---|---|
| **Missing** | Should exist but is absent from a dataset |
| **Unavailable** | Never collected in any dataset used |
| **Incomplete** | Present but partial |
| **Outside coverage** | Not observed |

## 1. Acquisition status

| Source | Status |
|---|---|
| Copernicus EMS, GHS-POP, GHS-OBAT, EFAS | Reused from the `map.py` cache (read from the challenge GCS bucket). |
| OpenStreetMap (Overpass API) | 40/40 tiles OK (20 facilities, 20 infrastructure), retrieved 2026-10-29, OSM database state 2026-10-29. No failed or outdated tile. The public servers often answered 502/504; these were recovered by retries with backoff and the mail.ru mirror. A full download takes ≈ 40 min. |

If a tile ever fails or is not downloaded, the map lists it in the sidebar and draws it as a red hatched box. An empty
area is never shown as "no assets".

## 2. Variables

| Variable | Source | Resolution | Time | Expected completeness | Known limitations | Missing-value treatment | Effect on score |
|---|---|---|---|---|---|---|---|
| Residents (P) | GHS-POP E2020 R2023A | 30″ (≈ 0.55 km²) → 400 m hexagons by area, summed over ≈ 1 km² | 2020 | Complete (modelled) | Model, residents only (no workers, pupils or patients); partly derived from built-up data | None needed | Full weight Wp |
| Buildings (B) | GHS-OBAT R2024A | Points → hexagons | ≈ 2020 | **Incomplete**, patchy | Belgium is known to be undercounted, but the aggregate ratio does not show it (buildings per resident: BE 0.59, DE 0.43, NL 0.71), so the gaps are local. 324 hexagon neighbourhoods have ≥ 100 residents and 0 buildings | Those neighbourhoods: **B missing**, excluded and renormalised (P is a correlated proxy), range shown | 9 facilities and 33 infrastructure assets flagged `B_gap` (quality Low) |
| Observed flooding (F) | Copernicus EMS EMSR517/518/520, flooded areas + flood traces | Vector polygons | July 2021 snapshots | **Outside coverage** beyond the mapped areas; under-detected in towns | 17,418 of 82,162 hexagons (21 %) are less than half mapped: BE 3,806, DE 11,831, NL 1,781. Belgium has no flood-trace products | **Unknown, never 0.** Areas grey. Assets unranked by default ("insufficient historical evidence") with an F = 0…1 range | 1,109 facilities and 1,746 infrastructure assets `F_unmapped`. Belgian "dry/near": 1,115 + 1,498 flagged `BE_detection` |
| Facility presence and type | OSM | Feature | 2026 | **Incomplete**, varies by country | 8,157 facilities (DE 6,657, BE 1,231, NL 269). 455 unnamed. 419 social facilities without sub-type | Sub-type unknown → factor mid value, flag `type_assumed`. Missing facilities: not invented; their area remains in the hexagon layer | M only |
| Hospital beds / care-home residents / pupils | OSM `capacity`, `beds` | — | — | **Unavailable**: 306 of 8,157 facilities have a tag, unverified | — | **Not used**, shown as "Unknown" | None |
| Infrastructure presence and class | OSM | Feature | 2026 | Incomplete | 11,156 assets. 3,109 with assumed sub-type (mostly substations without voltage) | Flag `type_assumed`, conservative factor 0.6 | M only |
| Bridge condition, capacity, detours, dependencies, service areas | — | — | — | **Unavailable** | — | Not used, not invented; shown as "Data unavailable" | None |
| 2021 vs today | OSM `start_date` | — | — | Rarely tagged | 39 facilities and 38 infrastructure assets may postdate July 2021. Rebuilt Ahr bridges usually carry no date | Flag `post_2021` | None on the score |
| EFAS hazard | CEMS EFAS | 3″ | Modelled return periods | Rivers > 500 km² catchment only | Model, not observation | Context layer only | None |

## 3. De-duplication (OSM)

| Group | Classified elements (all tiles) | After de-duplication | Inside study area |
|---|---|---|---|
| Facilities | 19,167 | 18,060 (nodes inside a same-category polygon, nested polygons) | 8,157 |
| Infrastructure | 44,715 | 26,059 (bridge and tunnel ways merged into structures, outlines used for grouping, points inside polygons) | 11,156: 4,339 bridges (1,516 crossing mapped water), 372 tunnels, 3,654 substations, 957 fire, 301 police, 129 ambulance stations, 514 wastewater, 281 water works, 204 pumping stations, 135 water towers, 270 power plants |

Elements in two tiles are counted once (by OSM type and id).

## 4. Flooding status of assets

| | flooded | trace | near | dry (mapped) | unmapped |
|---|---|---|---|---|---|
| Facilities | 29 | 65 | 958 | 5,996 | 1,109 |
| Infrastructure | 262 | 113 | 1,947 | 7,088 | 1,746 |

Evidence quality:
* **Facilities:** High 5,585, Medium 1,414, Low 1,158.
* **Infrastructure:** High 5,625, Medium 3,459, Low 2,072.

Weight sensitivity (36 weight sets, top 25): 7 facilities and 6 infrastructure assets stay in the top 25 under every weight set.
21 and 34, respectively, enter it in fewer than half of the sets. These are the ones whose priority depends on the assumptions.

## 5. Resolution mismatch

* EMS polygons are metre-scale, buildings are points, hexagons are 400 m, and population is ≈ 750 m.
* All scoring uses the ≈ 1 km² neighbourhood so that P is not read at a finer resolution than it has.
* Only the direct flood test uses the asset geometry (25 m tolerance).
* Display simplifies flood polygons by 20 m. The analysis uses the unsimplified `map.py` polygons (10 m simplification only at display).

## 6. Observations from the results (not tested hypotheses)

* At the default weights, dense urban assets near the Rhine/Ruhr floodplain (e.g. Düsseldorf Rhine-bank tunnels) top the
  infrastructure ranking alongside Ahr-valley assets. This reflects the 70 % weight on correlated density indicators (§8 of the
  methodology). Raising the flooding weight, or filtering "observed at the asset", shifts the ranking towards assets reached by the water. With flooding at 100 %, the facility top 5 were in the Prüm valley (checked), but this was not checked systematically for infrastructure.
* Belgian results are the least reliable for "no flooding detected": the Vesdre towns are known to have flooded but are largely absent from the EMS polygons.
