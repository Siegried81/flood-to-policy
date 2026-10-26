# Datasets

Verified against the live sources on **2026-10-06** — headers parsed, sizes
measured with HEAD requests, endpoints called with a real token. Anything marked
*to verify* is still open; never on the day.

`config/sources.yaml` is the single source of truth for every URL, CRS, unit and
licence. This page is the reading of it: if a figure here ever disagrees with the
YAML, the YAML is right.

## Read this first: five facts that break a naive pipeline

1. **The hazard maps are EPSG:4326 at 3 arc-seconds, not 100 m in EPSG:3035.**
   The "100 m / ETRS89-LAEA" figure is all over the literature and belongs to the
   **retired v2.x**. Build on it and everything misaligns.
2. **The observed depth maps are in CENTIMETRES; the hazard maps are in METRES.**
   Comparing the two without converting is a factor-100 error — and it does not
   crash, it returns a plausible number. Convert first, then compare.
3. **Belgium needs two GHS-POP tiles, not one.** The tile row boundary falls at
   51.2140 °N, which cuts through the country.
4. **581 communes vs 565.** Belgian mergers took effect 2025-01-01. Pick one
   vintage and build the crosswalk before joining anything.
5. **The Statbel files are UTF-8 with a BOM, not ISO-8859-1.** Read them with
   `encoding="utf-8-sig"`. Forcing latin-1 is what *produces* the mojibake.

## What the whole download costs

The `geodata` section declares **45 entries**, which expand to **105 jobs**; **56**
of those are files to download (**≈6.89 GiB**, of which the Natura 2000 GeoPackage is 1.27) and the other **49** are
`access: api` endpoints queried at runtime or an `access: folder` listing (the 30
`hera_river_discharge` files), so `src.fetch` lands nothing on disk for them.
With the `policy_corpus` (**25** entries) and `context` (**3**) sections, every one
of them a `scrape`, the whole fetch is **84 files** and **≈6.96 GiB**. **Six** entries
resolve to several downloaded files each — `jrc_flood_hazard` 13 (nine return periods,
two companion masks, the README and the CHANGELOG), `efas_flood_thresholds` 9,
`hanze_flood_impacts` 7, `cems_emsr518_belgium_2021` 4, `hera_sealed_fraction` 2 and
`ghsl_pop_100m_tiles` 2 — so `src.fetch.expand()` turns one declared entry into one
job per file, and the count `fetch_all` prints is the number of *files*, not of
declared sources.

**Eleven** entries declare a `files:` key, not six: one more is the
`hera_river_discharge` folder, and the other four name exactly one
file, which is how a single named archive inside a download portal gets pinned. So
`files:` present and "expands to more than one job" are different questions, and
the second is the one that moves the printed count.

Five entries used to point at the directory holding the files instead, and a
directory listing is valid HTML well above the minimum document size: `fetch`
stored the listing as the data, and the idempotency check then treated the source
as permanently done. A silent success with nothing in it. The resolved URLs now
live in `sources.yaml`, with the human-readable portal page kept beside them as
`landing:` for provenance.

Nine return periods alone are **2.61 GiB**. All 84 files were on disk on
2026-10-25; re-run `python -m src.fetch` only after changing `sources.yaml`.

Those counts are `src.fetch.expand()` over `sources.yaml` as it stood on
2026-10-25 and the byte totals are the declared files measured on disk the
same day, not a property of the repo: every entry added later moves them. Re-count
rather than quoting this paragraph.

## JRC river flood hazard maps ✅ verified

<https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-EFAS/flood_hazard/>

| | |
|---|---|
| Version | 3.1.1 |
| Return periods | **nine**: RP10, 20, 30, 40, 50, 75, 100, 200, 500 |
| Band | river inundation **water depth in metres**, single band |
| Type | Float32, **nodata −9999**, tiled 256×256 Deflate, 53% of tiles empty |
| Size | 110,162 × 51,992 px; **272–350 MB** per return period, **2.61 GiB** for all nine |
| CRS | **EPSG:4326**, pixel 0.000833333° = exactly 3 arc-sec |
| Licence | CC-BY 4.0 · DOI `10.2905/1D128B6C-A4EE-4858-9E34-6210707F3C81` |

The URL above is a **directory listing**, not a file. `sources.yaml` declares the
thirteen members by name: the nine return periods, the two companion masks, and
`README.txt` / `CHANGELOG.txt` — both small, and worth having on disk when the
jury asks what the version number means.

**Cells are not square.** 3 arc-sec is ~92 m north–south but only ~60 m east–west
at 50 °N. Any area or distance computed in 4326 is wrong, and the error differs
by axis.

**`/vsicurl/` is for a country window, and the wrong tool for the European run.**
The files are tiled and the server honours HTTP range requests, so a windowed
read pulls only the tiles it touches. Measured on RP100, 2026-10-06: a Belgium
window is **220 tiles and 2.4 MiB over the wire — 0.76% of the file**. The
EU27+EFTA bbox is **35,525 tiles and 172 MiB — 56% of the file, fetched in tens
of thousands of requests**, which at this repo's own one-request-per-second-per-host
rate is hours per return period. So download the whole file for the pan-European
zonal run, and keep `/vsicurl/` for a country window such as Belgium.

**Two companion rasters matter:**
- `Europe_spurious_depth_areas.tif` (74,730,820 B) — flags where depth > 10 m is
  predicted in small channels. The README says to treat those values with
  caution. Mask them, or flag the affected regions in the brief.
- `Europe_permanent_water_bodies.tif` (112,287,284 B) — the layer used to patch
  the depth maps.

**The caveats to put in your brief**, in the catalogue's own words: this is *not*
an official flood hazard map. It models **river flooding only** — surface runoff,
a large part of what destroyed the Vesdre valley in 2021, is absent — and only
basins **> 150 km²** are mapped, so many Walloon tributaries are missing
entirely. Naming the regions your analysis therefore cannot speak for is worth
more than a number that covers them badly.

The organisers' Data Catalogue (Annex 2) says **500 km²**, which describes an
older edition of the maps. In the v3.1.1 files, the ones in the challenge
bucket too, RP500 depth appears in about 98 % of river cells at 150-500 km²
upstream area against 12-20 % below 150 km² (checked 26 October 2026). Quote
150 km², and give that reason if asked.

## JRC European Satellite-Derived Flood Depth Maps ✅ verified

<https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-EFAS/European_Satellite-Derived_Flood_Depth_Maps/>

The validation layer, and the reason `docs/strategy.md` picks the question it
picks: **observed** flood depth across Europe, 2015-01-01 → 2025-12-31, at 20 m —
four times finer than the hazard maps. Estimated from Sentinel-1 SAR extent
(Copernicus Global Flood Monitoring) plus terrain, via FLEXTH.

| | |
|---|---|
| Band | flood depth in **CENTIMETRES** |
| Type | **uint16, nodata 0**, and **9999 = permanent or seasonal water** |
| Storage | one-row strips (60,000 of them), **not tiled** |
| CRS | **Equi7Grid Europe**, azimuthal equidistant. The file declares a user-defined projection (`ProjectedCSTypeGeoKey` 32767) and names no code, so pass the proj4 string. `pyproj` does resolve its WKT to **EPSG:27704** (measured 2026-10-06), which is useful to know and is not what the file says |
| Licence | CC-BY 4.0 · DOI `10.2905/0bc96690-b89c-4909-9166-c2c322a20130` |

**Centimetres against the hazard maps' metres.** This is fact 2 above, and it is
the most expensive mistake available in this kit, because getting it wrong
produces a number rather than an error.

**9999 is not a 99-metre flood.** It marks permanent and seasonal water. Mask it
before any statistic, exactly as `nodata 0` is masked for a depth statistic.
Scoring is the exception for the 0: there it stays in the matrix as "dry or
unseen", because it is the denominator of the false alarm ratio, and
`validate.score_event` reads the layer with `OBSERVED_READ_NODATA` (65535) so
GDAL does not turn it into NaN.

**The CRS has to be passed by hand.** The file declares `ProjectedCSTypeGeoKey
32767` (user-defined) with only an ESRI citation string, so the file names no
code of its own — though `pyproj` does resolve its WKT to **EPSG:27704**
("WGS 84 / Equi7 Europe"), whose proj4 is the string below. Its own
`ProjCenterLong` is 24.0 and `ProjCenterLat` 53.0, the right way round (checked
2026-10-06). Passing the proj4 string is still the safe move, because the file
itself claims no code:

```
+proj=aeqd +lat_0=53 +lon_0=24 +x_0=5837287.81977 +y_0=2121415.69617 +datum=WGS84 +units=m
```

**Finding the right file.** The root holds only `README.txt`, `copyright.txt` and
`maps/`; the rasters sit in one folder per year, and 2021 alone holds 352 of them.
The file name encodes the event — start and end date, duration, cluster id,
extent in km², centroid lat/lon ×100 — so the Belgian July 2021 event is
selectable from the name alone. That one file is what `sources.yaml` declares:
`WD_MERGE_2021-07-12---2021-08-02_duration_21_days_cluster_159_…`, 38,156,787 B,
45,000 × 60,000 px, covering lat 44.48–57.05 and lon −6.76–10.43 — a footprint
that takes in Belgium **and** the German Ahr valley.

**Footprint is not detection.** Over the Ahr (6.75–7.30 °E, 50.35–50.60 °N) only
about **0.35 km²** is flagged flooded — consistent with a flash flood in a
narrow wooded valley that drained between Sentinel-1 passes, though that cause
is a reading, not a measurement. So the cross-border validation this file supports is
**limited to Belgium**; it cannot score the model on the German side.

**An absence here is weaker evidence than a presence.** Sentinel-1 sees extent
through cloud but not under dense canopy or in narrow urban streets, and a
revisit gap can miss a flash flood that drained in hours. Say that before
concluding a region did not flood. The one-row-strip layout also means a windowed
read is not cheap here — but the file is 38 MB, so just download it.

## GHSL GHS-POP ✅ verified

**For the European run: the 1 km global file.**
`GHS_POP_E2025_GLOBE_R2023A_54009_1000_V1_0.zip`, 323 MB, one file, **nodata
−200**. At NUTS3, where a region is hundreds of km², 1 km is ample — and one file
removes the tile-mosaicking problem entirely.

**For a zoom-in on one valley: the 100 m tiles.**
`https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/GHS_POP_E2025_GLOBE_R2023A_54009_100/V1-0/tiles/`

**Belgium = tiles `R3_C19` (41,973,700 B) + `R4_C19` (95,509,568 B).** Both. The
R3/R4 boundary is at 51.2140 °N: Brussels and Liège are in R4, but **Antwerp
(51.22 °N) and the whole northern border strip are in R3**. Taking only R4
silently truncates northern Flanders — and the national total will still look
plausible.

| | |
|---|---|
| Band | **residents per cell** — a count, so summable |
| Type | Float64, **nodata −200**, BigTIFF, LZW |
| Grid (100 m tiles) | 10,000 × 10,000 px, exactly 100 × 100 m |
| CRS | **World Mollweide**, written `ESRI:54009` |
| Epochs | 1975–2030 in 5-year steps |

**`EPSG:54009` is not a valid code.** The file carries only an ESRI WKT string
and no EPSG projected code, so some tools report an unnamed CRS. Pass the full
WKT or `+proj=moll +lon_0=0 +datum=WGS84 +units=m`.

**Never average it, never multiply by cell area.** It is people, not density.

## GHSL GHS-BUILT-S ✅ verified

`GHS_BUILT_S_E2025_GLOBE_R2023A_54009_1000_V1_0.zip`, 153,290,977 B, one file.
The asset half of exposure: GHS-POP says how many people are in the water, this
says how much is built there, which is the question behind every recommendation
about where building is still allowed.

**The same grid as GHS-POP, byte for byte.** Verified by comparison, not assumed:
same affine transform, same 36,082 x 18,000 shape, same CRS WKT, same 2025 epoch.
So the two divide cell by cell with no reprojection and no resampling, and that
is the whole reason for taking the 1 km Mollweide version rather than the 100 m
tiles.

| | |
|---|---|
| Band | **square metres of built-up surface per cell** — a count, so summable |
| Type | **UInt32**, **nodata 4,294,967,295** (2³²−1), LZW |
| Grid | 36,082 × 18,000 px, exactly 1,000 × 1,000 m |
| CRS | **World Mollweide**, written `ESRI:54009` |
| Epoch | 2025, matching the population file |

**The nodata value is the trap, and it is a different trap from GHS-POP's.**
GHS-POP uses −200, which a naive sum makes conspicuously negative. Here the
sentinel is 4,294,967,295 — a positive number in a field of positive numbers. One
unmasked nodata cell adds four thousand square kilometres of imaginary buildings
to a region whose real total is a few hundred. Nothing looks wrong; the number is
just enormous.

**The sanity check is the cell itself.** A 1 km cell cannot hold more than
1,000,000 m² of footprint, so `max() <= 1e6` catches the sentinel, a unit mix-up
and a wrong product in one line. Measured over a European sample: max 421,158 m².

**It is surface, not value and not a building count.** A warehouse and a hospital
of the same footprint are the same number. It ranks what is physically at stake
and says nothing about what it costs; monetising it needs damage curves this kit
does not carry — say that rather than letting a jury infer euros.

**Mask it exactly like the population raster.** `scripts/build_context.py`
measures it through `_exposure_one_period`, the same function that measures
people, with the built-up raster in the population slot: same windowing, same
permanent-water and spurious-area masks, same extrapolation. Measured on a raw
raster instead, the river channel itself counts as flooded built-up ground, and
the two halves of a brief stop being in the same unit of measurement.

## Copernicus EMS EMSR518 — Belgium, July 2021 ✅ verified

Products: `cems-mapping-website.s3.eu-west-1.amazonaws.com/static/activations/EMSR518/`
· Activation page: <https://mapping.emergency.copernicus.eu/activations/EMSR518/>

Triggered by the Belgian National Crisis Center, 2021-07-14. Two AOIs: **AOI01
Liège**, **AOI02 Rochefort**. The products sit in a public S3 bucket that answers
anonymously — verified 2026-10-06 with no credentials and a default User-Agent;
the portal's login link does not gate that path.

**Two delineations per AOI, not one — four packages in total:**

| File | What | Size |
|---|---|---|
| `EMSR518_AOI01_DEL_PRODUCT_r1_VECTORS_v1_vector.zip` | Liège, first delineation | 34,180,203 B |
| `EMSR518_AOI01_DEL_MONIT01_r1_VECTORS_v1_vector.zip` | Liège, monitoring pass | 23,520,959 B |
| `EMSR518_AOI02_DEL_PRODUCT_r1_VECTORS_v1_vector.zip` | Rochefort, first delineation | 66,152,047 B |
| `EMSR518_AOI02_DEL_MONIT01_r1_VECTORS_v1_vector.zip` | Rochefort, monitoring pass | 55,827,584 B |

Take all four. `DEL_PRODUCT` alone is the flood **as first mapped**, not how far
it had spread days later — and the largest extent is the one the hazard maps
should be scored against. Scoring against the first pass understates the flood,
and therefore flatters the model.

**Delineation products only — no grading, no reference.** If your plan assumes a
damage-severity layer for the Belgian 2021 floods, it does not exist here.

The flood extent is the **`observedEventA`** layer, polygons tagged
`Flooded area`, CRS WGS84, shipped as SHP + GeoJSON + KMZ. Opened on disk:
AOI01 holds **151** polygons in `DEL_PRODUCT` and 390 in `DEL_MONIT01`; AOI02
holds 284 and 1,195.

**EMSR517 is the German side of the same event**, and `sources.yaml` declares
one package of it (`cems_emsr517_germany_2021`, AOI01 only, 7,136,350 B, verified
2026-10-06). **AOI01 is not the Ahr.** Its locality is *Moselle*: the
Trier/Mosel area, `areaOfInterestA` bounds 6.345–7.588 °E, 49.543–50.375 °N,
south of the Ahr valley. Its `observedEventA` layer is 8 polygons totalling about
**0.28 km²**, so it scores the model on the Mosel, not on the German flood the
event is remembered for. The Ahr **cannot be validated with the data on disk**,
and which other EMSR517 AOI covers it is unverified: the AOIs and monitoring
passes beyond AOI01 were **not** enumerated. Check the landing page and declare
that package before any claim about the Ahr. Keep the two activations labelled —
a German polygon counted as Belgian is a silent error.

## Wallonia: the official hazard map (*aléa d'inondation*) ✅ verified

Download: `geoservices.wallonie.be/geotraitement/spwdatadownload/results/68cfc9ff-…/`
· Catalogue record: `metawal.wallonie.be/geonetwork/…/14084108-2c7b-4091-b62d-ff0fc235213a`

The official Walloon hazard map, revision 2024-10-14, EPSG:**31370** (Belgian
Lambert 72 — not 3035, not 4326), CC-BY 4.0. The raster package declared in
`sources.yaml` is `ALEA_INOND_2020__ALEA_MAP_GEOTIFF_31370.zip`, 98,181,933 B.
Reproduce the attribution verbatim: *Source : Service public de Wallonie (SPW) –
Cartographie de l'aléa d'inondation (en vigueur) – Série (2021-03-24)*.

**It is ONE dataset carrying a class code, not three.** Field `CLASSEMENT`:

| Code | Meaning |
|---|---|
| 110 / 120 / 130 | low / medium / high hazard by **overflow** (*débordement*) |
| 210 / 220 / 230 | low / medium / high hazard by **runoff** (*ruissellement*) |
| 310 / 320 / 330 | low / medium / high hazard by **both** |
| 101 / 201 / 301 | **very low** (*aléa très faible*) by overflow / runoff / both |

**The fourth class.** The raster's own `.vat.dbf` lists 101/201/301 as *Aléa très
faible* (`CODEALEA` 1), beside the x10/x20/x30 codes (`CODEALEA` 10/20/30). It is
not marginal: 101 alone is about 477 km² of 2 m pixels, against about 846 km² for
110. So any "any-class" or "2xx/3xx" mask must say whether it includes *très
faible*: selecting by the hundreds digit includes it, selecting x10–x30 does not,
and the two give different hit rates.

So the runoff argument — the gap in the JRC maps, which model river flooding only
— is made by selecting `2xx` and `3xx`. No second dataset is needed, and looking
for one is how an afternoon disappears. Other attributes: `LOCALID`, `TYPEALEA`,
`CODEALEA`, `VALEUR`, `STATUS`, `DECISION`, `MILLESIME`.

**LICENCE TRAP — and this repo goes public.** The *aléa* records are CC-BY 4.0
and redistributable. The neighbouring **"Zones inondables – Scénario de période
de retour {25, 50, 100, extrême}"** records are **not**: they carry **CPU Type A
SPW**, under which the user *"ne peut pas redistribuer la donnée à un tiers"*,
with printing capped at 1:10,000. Publishing a map made from them is allowed;
shipping the data is not. Use the CC-BY *aléa* records for anything that ends up
in the repository or in an annex.

**Getting the vector.** There is no WFS. Besides the raster, the series offers
vector through its ATOM feed: `ALEA_GEOPACKAGE_31370.zip` (448,277,133 B),
`ALEA_FILEGDB_31370.zip` (154,813,592 B), or SHAPE split per province (Liège
68,992,948 B, Namur 61,534,486 B). An ArcGIS REST endpoint also answers GeoJSON
at `/arcgis/rest/services/EAU/ALEA_INOND/MapServer`, with `maxRecordCount` 2000,
so it **must** be paginated — a count of `CLASSEMENT=130` returns 7,947 polygons,
and a client that ignores paging gets 2,000 of them with no warning.

**The discovery feed is kept on disk.** `data/raw/wallonia_alea_atom_service.xml`
is the saved INSPIRE ATOM *service* feed for the series (uuid `14084108-…`): it
is the entry point to `atom_dataset.xml`, and therefore the only place the vector
file names can be read off without re-querying the geoportal. Keeping it means
the Walloon file names stay resolvable offline, on the day.

**Do not use the obsolete records.** The *débordement*-only product (uuid
`a3fa00be…`, Version 2007) is superseded, as are the 2016 and 2020 records the
catalogue itself tags *"donnée obsolète"*.

## Wallonia: observed July 2021 — the second ground truth ✅/❌ one layer verified, one dead

Two layers from the region itself, both EPSG:31370 and CC-BY 4.0, downloaded the
same way as the hazard series. Only the **extent** layer is actually reachable:
the depth layer's download URL answers HTTP 404 with *"Download Dataset
Expired"* (checked 6 October 2026), because the SPW geoportal mints
single-use result URLs rather than permanent ones. A by-hand download of the
same record, made 10 October 2026, is on disk under the declared name (see the
entry's `verified:` note in `sources.yaml`). `scripts/validate_2021.py` reads it
as an extent (depth > 0) alongside the extent layer, the JRC observed layer and
EMSR518, and writes `data/processed/validation_2021.parquet`; the depth-vs-depth
check is still not built, so do not plan the validation around it. They matter because they are **independent of Copernicus**: two observations that overlap are what turns "the model captures
X% of the flood" into a defensible result rather than an artefact of one
delineation. Where EMSR518 and these disagree is the uncertainty of the ground
truth itself, and that belongs in the brief.

- **`wallonia_observed_flooded_areas_2021`** — *Cartographie des zones inondées –
  juillet 2021*, the extent the Walloon administration recorded.
  `ZONES_INONDEES_202107_GEOPACKAGE_31370.zip`, 49,548,426 B. **208,012 polygons**
  dissolving to about **521 km²** (533 km² before dissolve: polygons overlap).
  Only **30,670** of them (about 53 km²) carry one of the **17 named `SCENARIO`
  zones** — the Vesdre, Ourthe, Meuse, Lesse, Lhomme, Wamme, Hoegne, Eau d'Heure,
  Mehaigne and Limbourg, but also the **Dyle, Senne and Grande/Petite Gette**;
  `SCENARIO` is empty on the other 177,342 (about 480 km²), so it is not a zone
  key for the layer. The polygons whose `IDW_SCENARIO` is set
  (*Interpolation*/*Extrapolation*, about 78 km²) are what the IDW depth raster
  tracks.
- **`wallonia_observed_water_depth_2021`** — *Zones inondées IDW – Hauteur d'eau –
  juillet 2021*, observed water **depth**. The only Belgian layer directly
  comparable to the hazard maps' depth band, so it supports a depth-vs-depth
  check rather than the weaker extent-vs-extent one. It is **IDW-interpolated**
  between observed points: a surface fitted to measurements, not a measurement
  everywhere — say so before quoting a per-commune depth. **❌ Not downloadable
  as declared:** the result URL in `sources.yaml` returns HTTP 404 *"Download
  Dataset Expired"*; the copy on disk (`wallonia_observed_water_depth_2021.zip`,
  500,736,096 B, `ZONES_INONDEES_2021_IDW450_HEAU.tif` inside) is the by-hand
  download of 10 October. To refresh it, re-mint
  the download from the catalogue record and discover the names through
  `atom_service.xml` → `atom_dataset.xml` under the record's uuid.

**The two Walloon truths disagree, by a lot.** The IDW raster has depth > 0 on
about **77 km²**; the extent layer covers about **521 km²**. Scored by
`scripts/validate_2021.py` on one 20 m EPSG:3035 grid over the Wallonia window
(4.18–6.06 °E, 50.10–50.75 °N, inside Wallonia only, polygons rasterised by cell
centre, permanent water dropped), the Walloon *aléa* x10–x30 classes catch
**72.8 %** of the depth raster's cells but **34.3 %** of the extent's — 88.4 %
against 41.2 % with *très faible* — so the hit rate moves by about **2.1×** with
the choice of truth alone; the JRC RP100 map moves 3.3× (60.5 % against
18.3 %). The depth raster covers the polygons whose
`IDW_SCENARIO` is set, not the flood's full recorded extent. Name the truth beside every hit rate, and never pool
the two.

## Boundaries and demographics ✅ verified

| Source | File / endpoint | Note |
|---|---|---|
| GISCO NUTS3 2024 | `NUTS_RG_01M_2024_3035_LEVL_3.geojson`, 25 MB | **The working unit**: 1,345 NUTS3 polygons in the file (1,165 EU-27, 46 EFTA, 134 candidate and potential-candidate), EPSG:3035, one file, one vintage |
| GISCO LAU 2024 | `LAU_RG_01M_2024_3035.shp.zip`, 39 MB | Pan-European; filter `CNTR_CODE == "BE"` → **581** communes. `GISCO_ID` = `BE_<NIS5>` |
| Eurostat population by age | `demo_r_pjangrp3` | NUTS3, every country. Checked live 2026-10-06: BE332, sex=T, age=TOTAL → 637,220 |
| Eurostat at-risk-of-poverty | `ilc_li41` | **NUTS2 only.** Checked live 2026-10-06: BE33 → 14.6 — `BE33` being a NUTS2 code is that caveat confirmed, not assumed |
| Eurostat GDP | `nama_10r_3gdp` | NUTS3. Checked live 2026-10-06: BE332 = 26,435.29 MIO_EUR for 2024, status `p` (provisional); the table holds 2023 = 25,450.93. **Pin the unit** — `MIO_EUR`, `MIO_PPS` and `EUR_HAB` are three different numbers, and mixing them is silent. Read from 2023 since 2026-10-12: 2024 is published for 536 NUTS3 units only |
| Eurostat population density | `demo_r_d3dens` | NUTS3, `PER_KM2`. Checked live 2026-10-12: BE332 = 808.5 (2024). 2024 sits on NUTS 2021 codes, so 66 of the 1,345 NUTS 2024 regions are blank (8 new Belgian codes, ITG2D-H, HR, EE, NO, RS, XK) - a vintage mismatch, not an empty region. Context, not an indicator |
| Eurostat household income | `nama_10r_2hhinc` | **NUTS2 only.** Pinned `na_item=B6N`, `direct=BAL`, `unit=PPS_EU27_2020_HAB`. Checked live 2026-10-12: BE33 = 21,300 PPS per inhabitant (2023; 2024 covers 63 of 296 NUTS2 regions). EU-27 only. Context, not an indicator |
| Statbel population | `TF_SOC_POP_STRUCT_2026` | **565** communes, 11,867,634 people at 2026-01-01, single years of age 0–100 |
| Statbel income | `TF_PSNL_INC_TAX_MUNTY` | 2005–**2023** only, on the **pre-merger** 581 geography |

**Pin the NUTS vintage and say which.** NUTS 2021 and NUTS 2024 are different
geometries *and* different code sets, and a file with no year in its name is a
trap.

**Both Statbel files are pipe-delimited and encoded UTF-8 WITH A BOM** (`EF BB
BF`) — read them with `encoding="utf-8-sig"`. This page previously said
ISO-8859-1, which was wrong in the dangerous direction: the mojibake that warning
was trying to prevent is exactly what *forcing* latin-1 produces ("Région
flamande" → "RÃ©gion flamande"). Verified byte by byte on 2026-10-06. Plain
`encoding="utf-8"` is not enough either — the BOM stays glued to the first column
name, so a lookup on `CD_REFNIS` fails on a key that looks right on screen.

The population file is a **fully crossed long table** (commune × sex ×
nationality × marital status × age): the zip is 2,566,901 B, the member
`TF_SOC_POP_STRUCT_2026.txt` is 104,151,550 B with 21 columns and 467,615 data
rows, and its 565 distinct `CD_REFNIS` sum to 11,867,634 people. `GROUP BY`
before use or you will count people many times over.

**The join trap:** GISCO LAU 2024 has 581 communes, Statbel 2026 has 565, and the
income file is on the old 581. GISCO has no LAU 2025+. For current geometry use
Statbel's statistical sectors (EPSG:31370 or 3812) instead. Build the crosswalk
before you join anything — otherwise communes vanish silently and the national
total still looks fine.

The Statbel rows are Belgium-only: they are for the Belgian part of the July
2021 core and for validating the model against the observed 2021 extents. The
European context comes from the GISCO and Eurostat rows above.

## JRC Risk Data Hub ✅ verified live — with two traps

`https://drmkc.jrc.ec.europa.eu/risk-data-hub-api/risk-data-hub-service`

OGC API – Features: `/losses/losses/items` (historical losses),
`/risks/vulnerability/items` (the published vulnerability index), and
`/admin/{asset,division,hazard,metric}/items`. Queried through `src/rdh.py`,
which caches every response under `data/processed/rdh_cache/`; `src/losses.py`
turns those rows into a table joinable to the NUTS3 analysis, and enforces the
two traps below rather than trusting a reader to remember them.

Called for real on 2026-10-06: **77 hazards**, and **1,297 loss rows for
Belgium** spanning **1983–2024**, including the July 2021 flood (EU event code
`FLEU202107120015`, national code `FLBE202107130001`, 67 rows). This is the layer
nothing else in the kit has: what a flood actually *cost* — economic loss, people
affected, casualties — per administrative unit and per event. It is what turns a
modelled ranking into a validated one, and its published vulnerability index is a
free cross-check on the one `src/vulnerability.py` builds.

**Trap 1 — the rows are NESTED. Filter on `admin_unit_level` before any sum.**
The same event is reported at Country, NUTS1, NUTS2 *and* NUTS3 level, so a naive
`sum()` counts it about four times over. Measured on the July 2021 event: summing
every casualty row gives **114**, while the figure is **29.67** at Country,
NUTS1 and NUTS2 — and **25.00** at NUTS3. Pick one level, say which, and do the arithmetic there — in
`src/losses.py` the level is a required argument, so an unlevelled sum is not
expressible. Working at NUTS3 costs about **16%** of the recorded casualties
(25.0 against 29.67), because not every death is attributed to an arrondissement
— so a NUTS3 total is a *lower bound* and the brief has to say so. Nothing
redistributes that gap: inventing an allocation would be a claim about where
people died. Instead each total carries its coverage ratio, and that overall
0.843 hides both directions — Brabant wallon (BE31) has 3.33 casualties and no
NUTS3 row at all, while Liège's arrondissements sum to 16.5 against 13.67 at the
province.

**Trap 2 — the values are averages, not an official toll.** Each row's value is
an average across the sources named in `data_source_list` (DFO, EM-DAT, HANZE),
which is why casualty counts carry decimals. Cite it as "the Risk Data Hub's
averaged estimate across DFO, EM-DAT and HANZE", never as the death toll. A jury
that knows the Hub will know this. `src/losses.py` names the column
`value_inter_source_average` precisely so the basis cannot be separated from the
number on its way into a CSV or a slide.

**And pick a euro vintage.** `value_2015_event_src_average` and
`value_event_src_average` differ only for monetary rows, by a flat ratio of 1.16
across the whole Belgian response — so the second is one rebase of the first, not
a per-year deflator. The default here is the 2015 series, because its field name
states its base year and a table can therefore say "EUR, constant 2015 prices"
and be checked. Mixing the two is a silent 16% error.

**Two more things that bite:**
- **HTTP 200 is not success.** An absent or expired token does not return 401 —
  the host answers with an F5/Shape JavaScript challenge *under status 200*, so
  the body has to be inspected. `src/rdh.py` reuses
  `fetch._why_not_a_document` for that rather than re-implementing it: one
  definition in this repo of "this response is not the thing I asked for".
- **Paging is mandatory.** The server's default `limit` is 10 and its maximum is
  10000. A caller who relies on the default silently gets 10 of 1,297 rows.
  `items()` always sends an explicit limit and follows `numberMatched` to the end.

**Credentials:** an EU Login account and a bearer token that **expires after 10
hours**, read from `RDH_BEARER_TOKEN` at call time. So the token has to be
refreshed on the morning of the event — it is on the day-of checklist — while the
*responses* are cached the day before. No token raises `RdhUnavailable` rather
than returning an empty list: "we did not look" and "we looked and found nothing"
must not collapse into the same number in a policy brief. Everything else on this
page is open and needs no credentials.

**The server-side hazard filter does not apply.** A Belgian request made with
`admin_hazard_type="Flood"` came back with 793 flood rows out of 1,297 — the rest
are Storm, Extreme temperature and Earthquake. The cache on disk now holds the
request without that filter (`losses__admin_unit_country_code-BE.json`), and it
returns the same 1,297 rows and the same 793 flood rows. So hazard is
filtered on the rows, in `src/losses.py`, and every per-unit total lists the
hazard codes actually behind it, which makes an earthquake in a table labelled
"flood" visible in the table itself. Pass `nat-hyd-flo-riv` for any comparison
against the JRC rasters, which model river flooding only.

One join caveat: the RDH rows declare no NUTS vintage of their own. The Belgian
NUTS3 codes include `BE32A`–`BE32D`, the post-2021 Hainaut split, so they are
NUTS 2021 or later — check for unmatched codes after merging onto GISCO rather
than assuming the vintages agree.

## HANZE v3.0.1 — historical flood impacts, 1870–2025 ✅ verified

Zenodo record `10.5281/zenodo.20478847`, CC-BY 4.0, seven files, 14.47 MB in all.
The long observational record behind part of the Risk Data Hub's numbers — and
taking it directly is what lets a loss figure be traced to a **named event and a
named reference** (`HANZE_references`) instead of to an average. Its regions are
published on the **NUTS 2024** vintage, so it joins `gisco_nuts3` with no
crosswalk: the only dataset here that does.

`S4_currency_conversion_rates.csv` and `S5_GDP_deflators_by_country.csv` are not
optional for any euro figure: a 1993 loss and a 2021 loss are not comparable
until both are deflated and converted.

**It is not independent of the Risk Data Hub.** The Hub lists HANZE among its own
sources, so agreement between the two is not corroboration — and summing them is
double counting. Two more things to say out loud: the version is tagged *v3.0.1
beta* by its author, so write "beta" rather than implying a settled dataset; and
it records **reported** impacts, whose coverage improves over time, so a rising
trend in the early decades is partly better reporting and not only more flooding.

## EEA WISE — WFD river basin districts ✅ verified live — and one hard limit

`https://water.discomap.eea.europa.eu/arcgis/rest/services/WISE_WFD/WFD2016_RiverBasinDistrict_WM/MapServer/0`

River basin districts as reported under the Water Framework Directive: the unit
water obeys, as opposed to the unit administrations are drawn on. NUTS3 answers
"who is exposed"; this is meant to answer "who is exposed by water they do not
govern", which is the argument for acting at EU level rather than nationally.

**196 districts, EPSG:4326, no bulk file.** The EEA's bulk option is the entire
WISE WFD package as one 3.4 GB Nextcloud share with no per-layer URL, so this is
an `access: api` source. `src/basins.py` caches the answer to
`data/processed/basins_cache/`, which is **288 MiB** for 196 polygons — the
geometry is served unsimplified. `src.fetch` does not fill it; the offline
readiness check (`scripts/check_offline_readiness.py`) only warns when it is
absent, so **fetch it before the event**.

### Three ways this service answers HTTP 500

All measured 2026-10-06, all with no error message to read.

- **`outFields=*`** — the layer carries an attribute literally named `geometry`
  beside its real geometry, and in GeoJSON the two collide. Name the fields.
- **A large page.** 10 records take ~25 s, 25 take ~40 s, 50 take 59–75 s, and
  100 and 200 both answer 500: a server-side timeout, not a rejection. The client
  pages at 25, which is 8 pages and about two minutes for the whole layer.
- **A 60 s timeout** cuts requests that were working. `TIMEOUT_S = 180`.

**But the paging is the geometry alone.** `returnGeometry=false` returns all 196
rows with their attributes in **one request, under a second**. For anything that
needs the names and codes rather than the shapes — which includes building and
checking the crosswalk below — ask for the attributes and skip the 288 MiB
entirely.

### The limit that matters: a district is a national portion

**The layer has no field that says which polygons belong to the same basin.** All
25 fields were listed; there is a `countryCode`, an INSPIRE id and two name
fields, and no international-basin key.

And the polygons are national portions, not basins. Measured:

| district | | km² |
|---|---|---|
| `BEESCAUT_RW` | Scheldt, Wallonia | 3,773 |
| `BESCHELDE_VL` | Scheldt, Flanders | 12,025 |
| `NLSC` | Schelde, Netherlands | 3,164 |
| | **mutual overlap** | **0** |

So grouping by row — all the service supports — reports **every international
basin in Europe as unshared**, which is the exact opposite of the truth and is
delivered as a number rather than as an absence. Grouping by name does not
rescue it either: `MEUSE`, `MAAS`, `LA MEUSE` and `INTERNATIONAL RIVER BASIN
DISTRICT OF THE MEUSE` are one basin under four strings, and the field holds 180
distinct values for 196 rows.

`config/international_basins.yaml` is the answer: a declared crosswalk of 68
districts into 22 international basins, each justified by the layer's own
`nameTextInternational`, with the districts it deliberately does not group listed
alongside the reason. `src.basins.check_crosswalk()` refuses a code the layer
does not have, a district claimed twice, a basin inside one country, and a basin
whose portions are not contiguous — a real basin's national parts meet at the
border, so a wrong grouping shows up as a union in two pieces.

### And a threshold, because borders are drawn twice

The districts and the NUTS3 regions are independent renderings of the same
borders, so their edges disagree by a few hundred metres everywhere. Measured
against the 1,345 NUTS3 regions: by raw intersection **109 of the 182 districts
the frame reaches touch two or more countries**, and one touches eight. Requiring
50 km² before a country counts leaves **exactly one** — `DE2000`, the German
Rhine district, which really does reach into Switzerland and Austria. Without
that floor, half the layer reported itself international on slivers.

**Other things to say out loud.** A district is not an aggregate of NUTS3
regions: districts cross borders *and* cut regions in half, so a figure per
district has to be built by intersecting areas in EPSG:3035 — summing the NUTS3
rows that "belong" to a basin double-counts every region the boundary crosses.
And the geometry is the **2016** reporting round, a vintage like NUTS: name it
beside any number.

## EEA Floods Directive — Areas of Potential Significant Flood Risk ✅ verified live — and three traps

`FloodsDirective_AreasOfPotentialSignificantFloodRisk_WM`, layer 3 (polygons), on
the same EEA ArcGIS host as the WFD districts. Queried anonymously, cached to
`data/processed/apsfr_cache/` as **GeoParquet**, not GeoJSON — the layer is large
enough that GDAL refuses to read back the GeoJSON this code wrote
("GeoJSON object too complex/large").

**Why it is here.** Every other hazard layer measures what the water does. This
measures what a *government said* about it: the areas each Member State
designated under Article 5 and reported to the Commission. The corpus already
carried the Directive's text without the reporting behind it. Crossed with the
modelled hazard it supports the question a policy audience can act on — where
does modelled risk fall outside the declared area? — and that is a compliance gap
rather than a colour ramp.

It is **not** evidence that an undeclared area is wrongly undeclared: see
[`limitations.md`](limitations.md#1-what-the-figures-cant-say).

**Trap 1 — two reporting cycles in one layer.** Measured 2026-10-07: `cYear` is
2010 for 496 polygons across 5 countries (AT, DE, ES, FR, LT) and 2018 for 12,173
across 25. AT, DE, ES and FR are in **both**, so a query that does not pin the
cycle designates the same ground twice and an area share can exceed 1.
`src/apsfr.py` defaults to 2018 and refuses to mix. The cost is real and belongs
in a caption: Lithuania reported in 2010 and not in 2018.

**Trap 2 — generalisation is mandatory, and a coarse tolerance deletes the
layer.** Ungeneralised the service answers 50 polygons in 18.7 MB and refuses any
`cYear` query with HTTP 500 — under `f=json`, a 200 whose body *is* a 500. But
the features are small, a median of about 0.001 km², so a coarse tolerance does
not simplify them, it removes them. Measured on 300 Italian polygons:

| `maxAllowableOffset` | payload | survive a structure repair | median area |
|---|---|---|---|
| 0.001 (~110 m) | 1.35 MB | 169 of 300 | 0.0008 km² |
| **0.0001 (~11 m)** | 5.51 MB | **300 of 300** | 0.0010 km² |
| 0.00002 (~2 m) | 15.7 MB | 300 of 300 | 0.0011 km² |
| none | HTTP 500 | — | — |

At 110 m the first run of this code reported **Germany, Spain and France as
having declared nothing** — the strongest claim the module can make, produced
entirely by a tolerance. The kit uses 0.0001; the cycle is then ~224 MB over ~41
pages, about 15 minutes, once.

**Trap 3 — it does not cover every Member State.** 26 country codes across both
cycles, and **Ireland is not one of them**: zero polygons, for a State that
certainly designates areas. So "no declared area" has two causes that are
identical in the data and opposite in meaning. `declared_by_region` returns
`apsfr_country_reported` and leaves the share **NaN** where the country was never
covered. Never quote an undeclared region without it.

Served in **Web Mercator** (EPSG:3857), like everything on this host; the client
asks for EPSG:4326 (`outSR`), which is what the cache holds, and areas are
computed in EPSG:3035. About 48% of the generalised polygons self-intersect, and
shapely's default *linework* repair returns collections mixing lines with polygons
that the overlay rejects outright; `src/basins.py::repair` takes a `method` and
this layer passes `"structure"`. `basins` still uses linework, so no basin share
moved.

Like the WFD layer, it must be fetched once **before** the event: nothing in
`src.fetch` or the offline readiness check knows about it.

## Environment: Natura 2000 and CORINE Land Cover measured

Article 6(5) of the Floods Directive asks flood risk maps to show the potential
adverse consequences for the **environment** and for **cultural heritage**.
Since 2026-10-12 the kit measures Natura 2000, and since 2026-10-25 CORINE land
cover; cultural heritage is still not measured, and no heritage source is declared.

- **Natura 2000** ✅ — `eea_natura2000_gpkg`, the end-2024 release as one
  GeoPackage (1,360,171,008 B, SHA-256 `fc947b01…964f42`, EPSG:3035, CC-BY-4.0,
  DOI 10.2909/91357f39-7866-41ce-b447-43905c364ec8), from the EEA datashare's
  anonymous WebDAV path. Its one spatial layer, `NaturaSite_polygon`, holds
  27,173 sites: 21,539 type B (Habitats), 3,374 type A (Birds), 2,260 type C
  (both), so each site appears once - the MapServer's layers 0 and 1 overlap by
  those 2,260, which is why the service is not summed. Two different sites can
  still overlap on the ground; `src/environment.py` burns every polygon into one
  mask, so areas are of the union. EU-27 only, and it writes Greece `GR` where
  GISCO writes `EL`. Read into `context.parquet` as
  `natura2000_km2`, `natura2000_flooded_km2_rp100`,
  `natura2000_flooded_share_rp100` and `natura2000_grid_coverage`, measured on
  the hazard raster's own 3 arc-second grid (see the module docstring for why
  windows on the hazard grid are exact here). Checked against an exact vector
  intersection on five regions (BE341, DE21H, HU110, NL230, RO213): within
  0.3 %. The MapServer (`eea_natura2000_sites`) stays declared for provenance.
- **CORINE Land Cover** ✅ — what the flooded ground actually *is*: industrial,
  agricultural, urban fabric. The only source here that is not anonymously
  downloadable: the product page answers 200, but the download goes through the
  Copernicus Land Monitoring Service and needs a registered account and an
  accepted licence, so it was fetched by hand. The CLC 2018 status raster at
  100 m (`u2018_clc2018_v2020_20u1_raster100m`) sits under
  `data/raw/download/clms_corine_2018/`, and since 2026-10-25 `src/landcover.py`
  reads it into `context.parquet` as `corine_rp100_footprint_km2` and the
  `corine_rp100_share_*` columns: the share of the RP100 footprint (same 0.5 m
  threshold and masks) under homes, industry and commerce, transport, other
  artificial land, agriculture, natural land and water, for 1,295 of the 1,345
  regions. Found 2026-10-12 and not used: the EEA datashare serves
  the CLC 2018 *accounting layer* (`CLC2018ACC_V2018_20.tif`, 215,355,481 B,
  100 m, EPSG:3035) anonymously, under
  `eea_r_3035_100_m_clc-2018-acc_p_2017-2018_v01_r00`. It is a variant built for
  change accounting, not the status layer the kit uses.

## Copernicus CDS — hydrology projections ✅ verified — and unsupported

`sis-hydrology-variables-derived-projections`, DOI `10.24381/cds.73237ad6`.
Copernicus C3S / SMHI indicators from bias-adjusted EURO-CORDEX EUR-11
simulations forcing the E-HYPE hydrological model. The one future layer in this
kit: everything else here measures present-day risk, which is a description,
while risk that *moves* is a decision.

**On disk**: two hand-made request archives (91,492,658 B and 45,730,014 B,
12 NetCDF files) plus the two VIC-WUR 2071–2100 files of a third, whose
22,881,344 B archive is no longer on disk — **14 NetCDF files** for the
EC-EARTH/CCLM4-8-17 chain — plus 42 one-member archives
fetched on 2026-10-25 by `scripts/fetch_cds_member.py`, each holding RP5 and
RP50 — **98 NetCDF files**, all 48 members (eight simulations × two models ×
three periods) — return values of annual maximum river discharge at 2, 5, 10
and 50 years, for 2011–2040, 2041–2070 and 2071–2100, each against the 1971–2000
reference, as a **relative change in percent**.

**What the two hand-fetched chains put on disk**, re-derived from the filenames 2026-10-07 — the
names carry the whole request, which is why `src/climate.py` parses them rather
than trusting a sidecar:

| period | `E-HYPEgrid-EUR-11` | `VIC-WUR-EUR-11` |
|---|---|---|
| 2011–2040 | RP5, RP50 | RP5, RP50 |
| 2041–2070 | RP5, RP50 | RP5, RP50 |
| 2071–2100 | RP2, RP5, RP10, RP50 | RP5, RP50 |

All of it RCP 8.5, member `r12i1p1`, against the 1971–2000 reference, and **two
model chains on every period** since the VIC-WUR 2071–2100 files landed on
7 October 2026. Until they did, the far-future period had one chain, and a single
member cannot agree with itself: `ensemble_agrees_on_sign_2071_2100` was False
for all 1,345 regions, so the +25.6% median showed and licensed no sentence about
the direction of the change. With the second chain the median is **+20.3%** —
the lone member was overstating it by 5.3 points — and **943 of 1,198 regions**
now agree on the sign, the lowest agreement of the three periods, which is where
anyone would expect the chains to diverge most. The gap was never a missing
period — the time coverage was always complete — it was one empty cell of the
model-by-period grid, which is a different thing and much easier to miss.
(Those are the two-chain figures. Since 2026-10-25 every period holds 16
members; the current figures are in
[`policy_answer.md` §4.4](policy_answer.md#44-the-reference-discharge-is-rising-where-people-already-live-in-the-way).)

`scripts/fetch_cds_member.py` makes that request reproducibly, and verifies every
downloaded filename against what was asked before anything enters this
directory: the failure that matters is not an empty download, it is the *wrong
member* landing where the ensemble is computed. Since 2026-10-12 it knows the
dataset's eight simulations (read off the CDS constraints file: EC-EARTH r12i1p1
with CCLM4-8-17, RACMO22E and RCA4; HadGEM2-ES r1i1p1 with RACMO22E and RCA4;
MPI-ESM-LR r1i1p1 and r2i1p1 with REMO2009, r1i1p1 with RCA4), checks the GCM
and the regional model as well as the model, period and realisation, and
`--all-missing` plans every gap: **42 requests** against the hand-fetched
archive, all run on 2026-10-25, so it now plans none. It needs a CDS key; its
tests use a mocked client.

Note also that RP2 and RP10 exist **only** for 2071–2100, so they cannot carry a
trajectory across periods: the other two periods have no counterpart to compare
them with.

**Eight climate simulations, two hydrological models.** Since 2026-10-25 the
frozen `context.parquet` is built from all eight simulations the dataset offers
under RCP 8.5, each routed through **two** hydrological models —
`E-HYPEgrid-EUR-11` and `VIC-WUR-EUR-11` — so the 50-year return value has
**16 members on all three periods**. Until then it was `ICHEC-EC-EARTH`
`r12i1p1` driving `CLMcom-CCLM4-8-17-v1` alone: two hydrological opinions of one
climate, which sample no climate uncertainty at all.
`climate.ensemble_change_by_region` reports the spread across whatever members
are present - the range and, since 2026-10-12, the quartiles of the members'
medians - and two sign columns: `ensemble_agrees_on_sign` (every member) and,
since 2026-10-25, `ensemble_robust_on_sign` (at least 80 % of members, the
IPCC AR6 "robust" rule), which is the one the UIs read. Neither claims
agreement from a single member — where only one file exists both are `False`
by construction, which is the honest answer and not a bug. That is what
2071–2100 looked like until its VIC-WUR files arrived, and it is still what any
period reduced to one chain will look like.

**The two models do not ship the same subdatasets.** The E-HYPE files hold `lon`,
`lat` and the indicator; the VIC-WUR files hold `time_bnds` as well. So "the
subdataset that is not lon or lat" is two candidates, and a reader that guesses
fails on half the archive. `src.climate.read_change` takes the variable from the
filename, which states it, and falls back to ignoring `*_bnds`.

**The request form has a cost cap of 1,000**, counted as the *product* of the
selections, not the sum. Four variables × three periods × eight models is 96, but
add the percentile and statistic axes and it refuses. Request one period at a
time.

| | |
|---|---|
| Variable | `rdisreturnmax{2,5,10,50}_tmean`, relative change, **percent** |
| Grid | **950 × 1,000, curvilinear** — `lon` and `lat` are their own subdatasets |
| Type | Float32; **626,772 of 950,000 cells are fill** (66%: sea and no river) |
| Reference | 1971–2000, named in every filename |

**There is no affine transform.** The file carries `lon` and `lat` as full
950 × 1,000 arrays beside the variable, so `rasterio` opens it as three
subdatasets and `src.transform` is meaningless. Resampling onto another grid
would mean interpolating a ratio, which is the same error as averaging one, so
the aggregation is point-in-polygon on the real coordinates: each cell
contributes its value to whichever region contains its centre.

**Never a mean, never a maximum.** A relative change has no upper bound where the
1971–2000 reference discharge is near zero — intermittent rivers, arid basins.
Measured on the 50-year return value, 2041–2070 vs 1971–2000, on one member
(`E-HYPEgrid-EUR-11`, EC-EARTH r12i1p1 / CCLM4-8-17):

| median | p25 | p75 | min | **mean** | **max** |
|---|---|---|---|---|---|
| **+16.9 %** | −4.3 % | +43.3 % | −100 % | **+138 %** | **+16,452,833 %** |

The mean is eight times the median and belongs entirely to that tail; the maximum
is a sentence that ends a pitch. `src/climate.py` reports the median and the
quartiles and offers neither, and a region with fewer than 10 cells gets no
figure at all.

**It is discharge, not depth and not extent.** A 50-year flow in m³/s cannot be
subtracted from or layered onto the JRC inundation maps. What travels is the
direction and size of the change, applied to the present-day exposure measured
elsewhere in this kit. A future headcount quoted as if it had been measured is
not defensible.

**The filename is the provenance.** `src.climate.describe()` parses the variable,
the kind, the hydrological model, the GCM, the RCP, the member, the two periods
and the resolution out of it, and refuses a file it cannot parse — a renamed file
is how a brief ends up quoting RCP 4.5 as RCP 8.5.

**NO LONGER SUPPORTED by the data providers**, notice dated 2025-01-29. The data
and documentation stand as they are and nobody is fixing them. Say so rather than
letting a juror find it.

## EMO-1 observed precipitation, 2021 ✅ read

`emo1_precipitation_2021` (`data/raw/download/emo1_precipitation_2021.nc`) is now
read by `src/rainfall.py` and `scripts/rainfall_jul2021.py`, which write
`data/processed/rainfall_jul2021.parquet`: the four-day July 2021 event rain
(days ending 13-16 July at 06:00) per NUTS3 region, mean, max, 95th percentile
and cell count, for Belgium, Germany, the Netherlands, Luxembourg and France.
Measured layout: one `pr` variable (mm, `cell_methods: time: sum`), 365 daily
steps from `2021-01-02T06:00`, 2970 x 4530 cells at 1 arcmin, latitude
descending, float64 once decoded (about 39 GB) - so only the time window and a
bounding box are ever loaded. Each time stamp marks the END of its 24 h
accumulation. A cell counts for the region holding its centre and sea cells are
dropped: 581 NUTS3 regions are measured (the overseas `FRY` regions lie off the
grid), with Verviers (BE335) at a maximum of 290.4 mm and a mean of 167.3 mm over
518 cells.

## The JRC catalogue API — one real trap

`/api/2/datasets` has **no free-text search**. It accepts `q`, `search`,
`keyword`, `filter` and every other plausible parameter, **ignores all of them**,
and returns the full 4,366-dataset catalogue with HTTP 200. So `?q=flood` looks
like it worked and hands you a methane-flux dataset.

Worse, the site sits behind a WAF that answers a default `curl` User-Agent with
an HTML "Request Rejected" page **under HTTP 200** — a naive client parses that
as success.

Keyword search works through the **SPARQL endpoint** instead,
`https://data.jrc.ec.europa.eu/sparql` (not `/api/sparql`, which 404s).
`src.fetch.jrc_catalogue_search` does this correctly, with browser headers and
blank-node filtering; it was tested live and returns real flood datasets.

Use the REST API only for fetching one dataset by UUID.

## Before you trust any raster

```python
import rasterio
with rasterio.open(path) as src:
    print("crs     :", src.crs, "| epsg:", src.crs.to_epsg())  # None is NOT 4326
    print("res     :", src.res)                                 # degrees or metres?
    print("dtype   :", src.dtypes[0], "| nodata:", src.nodata)  # None is a red flag
    a = src.read(1, masked=True)
    print("range   :", a.min(), a.max())   # depth in m, or cm?
    print("total   :", a.sum())            # population: compare to the published figure
```

The `range` line is the one that catches the factor-100: a hazard map tops out at
a handful of metres, the satellite depth map at thousands of centimetres plus the
9999 water flag. If `src.nodata is None`, find out what sentinel the file uses
(often `-9999`, `-200` or `0`) and declare it yourself. An undeclared sentinel
gets summed as a measurement. See `docs/geospatial_crash_course.md` for the rest.
