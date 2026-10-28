# Copernicus review: 7 browser tabs and the flood datasets behind them

Read on 2026-10-24, for the JRC x FARI hackathon (29-30 Oct 2026). Everything
must be downloaded before the event, because the kit runs offline at the venue.
This review does not repeat `docs/tab_review.md`. "In the kit" means listed in
`config/sources.yaml`.

**Status.** All seven ranked items are now in `sources.yaml` and on disk under `data/raw/download/`: the nine
EFAS v5.1 return-level files (not `_mu`/`_sigma`), the July 2021 EFAS window
and the EWDS upstream-area field, `IMD_2018_100m_eu_03035_v020.zip`, the HERA
sealed fraction for 2010 and 2020, HERA v2 discharge for 1991-2020 (30 files),
the CORINE 2018 100 m raster, the ECDE files (three NUTS2 precipitation
indicators, four gridded `flood_recurrence` files), and the activation list
cached as `data/processed/cems_activations.json`; they are built into
`context.parquet` (`hera_*`, `sealed_*`, `imperviousness_*`, `corine_rp100_*`,
`pluvial_*`/`ecde_*`, `efas_2021_*`). The sentences below that say
"no file" or "not downloaded" describe 2026-10-24.

**How the pages were read.**

- The 7 tabs (5 distinct pages, because "Access to data" and the services
  catalogue are each open twice) were read with the Chrome extension.
- The services catalogue was crawled with `curl`: all 22 result pages, 380
  items. Its full-text search parameter does not filter anything, and its
  EMERGENCY facet returns **0 items**. So no CEMS flood product is listed
  there at all.
- Everything else was read through machine-readable endpoints, all of which
  answered without a login:
  - the EWDS and CDS catalogue APIs (`/api/catalogue/v1/collections/<id>`,
    plus each collection's form and constraints JSON);
  - the EWDS and CDS **costing** endpoints
    (`/api/retrieve/v1/processes/<id>/costing`). These return a request's cost
    and its limit without submitting a job;
  - the CLMS catalogue API (`https://land.copernicus.eu/api/@search`);
  - the JRC FTP directory listings;
  - the CEMS rapid-mapping public dashboard API;
  - the GFM API's swagger file.

**What was not done.** No data file was downloaded (only `HEAD` requests for
sizes). No login was used, no account was created and no job was submitted.
The one cookie banner met (the GloFAS/GFM React page) was left untouched, and
that page was read through its swagger file instead.

**One thing to know about your own tab.** The EWDS "CDSAPI setup" tab shows a
personal key in its black box. That means you are already logged in to an
ECMWF account in that browser. The key is not reproduced here or anywhere else.

---

## Ranked: what to add before 29 Oct

Hours include download, a script, a test and the `sources.yaml` entry. They
assume the kit's existing raster and zonal code (`scripts/build_exposure.py`,
`src/climate.py`) is reused.

| # | What | Policy question it answers | Account | Effort |
|---|------|----------------------------|---------|--------|
| 1 | **EFAS v5.1 return-level thresholds** (RP 1.5 to 500, one NetCDF per RP, about 54 MB each), plus an **EFAS historical window for July 2021** (Meuse, Vesdre, Ahr) | Which river cells in July 2021 went past their 1-in-100 (or 1-in-500) level. This turns "July 2021" into a return period, with the JRC's own model. | Thresholds: **none** (open Confluence attachment, HEAD 200). July 2021 window: **ECMWF account** (you have one) and the CEMS-FLOODS licence accepted on the efas-historical page | 4-6 h |
| 2 | **HRL Imperviousness Density 2018, 100 m, Europe** (one 66 MB GeoTIFF, EPSG:3035) | Share of sealed soil per NUTS3 region and **inside the RP100 footprint**. This is a surface-runoff (pluvial) proxy, and it speaks directly to the brief's own limitation: "Surface runoff - much of what hit Wallonia in 2021 - is not in the hazard maps". | **EU Login** (CLMS). 2021 and 2024 are served through **WEkEO** only (a second, free account) | 3-4 h |
| 3 | **HERA sealed fraction, yearly 1950-2020** (`fracsealed_European_01min_YYYY.nc`, 9.5-13 MB each) | Sealing trend per NUTS3 for 2010 against 2020, the same epochs as the kit's GHSL 2010/2025 comparison. It is a no-account fallback for item 2, but coarser (1 arcmin, about 1.8 km). | **none** (JRC FTP, CC BY 4.0) | 2-3 h |
| 4 | **HERA river discharge v2, 1951-2020** (70 yearly NetCDF files of about 2.3 GiB each, 6-hourly, 1 arcmin; about 161 GiB in all, or about 69.5 GiB (74.6 GB, 30 files) for 1991-2020, measured on disk 2026-10-27) | **Observed trend in annual peak discharge per basin** over 70 years: whether today's 1-in-100 flood was a 1-in-100 flood in 1960. This is the "heavier source" for your ~15 h budget. | **none** (JRC FTP, CC BY 4.0) | 12-15 h (download is most of it) |
| 5 | **CORINE Land Cover 2018, 100 m raster** (125 MB) | What the flooded ground is: industrial, agricultural, urban. It is already declared in `sources.yaml` (`copernicus_corine_land_cover`) with no file. This review supplies the file name and size. | **EU Login** (CLMS) | 3 h |
| 6 | **C3S ECDE aggregated climate indicators**: maximum 5-day precipitation, extreme precipitation total and frequency of extreme precipitation, at **NUTS2** (not NUTS3; see the mini-report) | Projected change in heavy precipitation per region, by global warming level. This is the pluvial counterpart to the discharge projections the kit already has. | The **ECMWF account** (CDS) the kit already uses, plus the CC BY licence accepted once | 2 h |
| 7 | **CEMS rapid-mapping public activations list** (anonymous JSON) | "53 EU flood activations from March 2023 to October 2026" by country. It is context for the brief and costs one GET. | **none** | 1 h |

Not recommended before the 29th:

- **GFM** (Global Flood Monitoring). The kit's `jrc_observed_flood_depth` is
  already built on GFM extents.
- **EFAS historical for a Europe-wide trend.** One full-domain field is about
  54 MB, so 34 years at 6-hourly steps is terabytes. HERA covers this instead.
- **GloFAS historical, the EFAS forecasts and reforecasts, the seasonal
  products and the rapid impact assessments.** They are operational, global,
  or for EFAS partners only.
- **Riparian Zones** (5 GB for Europe) and **EU-Hydro** (2-4 GB). They are
  heavy, and the kit already has basins from the WFD layer.
- **Urban Atlas.** It covers cities only (per functional urban area), not
  every NUTS3 region.

**Combined path:** items 1 + 2 + 3 + 6 + 7 is about 12-16 h with no new heavy
download. Item 4 replaces items 3 and 6 if you would rather spend the 15 h on
one strong trend figure.

---

## The 7 tabs

### 1. Copernicus — "Access to data" (open twice, tabs 595428095 and 595428148)
- What it is: a map of the portals. Sentinel data goes through CDSE, a subset of the service products through WEkEO, and each service has its own portal (CLMS `land.copernicus.eu`, C3S, CAMS, CMEMS). CEMS has separate portals: rapid mapping, EFAS, GloFAS, EFFIS, EDO and GDO.
- Verdict: **USEFUL as a map, no data itself.** Two facts matter here. First, the page says the public can see rapid-mapping maps "only … from historic requests", so new activations cannot be ordered. Second, EFAS products are listed as a separate portal from the data store.
- Still drawable: the access route per service, used throughout this review.

### 2. Copernicus — services catalogue (open twice, tabs 595428094 and 595428144; both are the unfiltered first page)
- What it is: 380 items across 6 service filters. 115 match flood-related keywords. Of those, 33 are Imperviousness products, 18 CORINE and 13 Urban Atlas; the rest include Riparian Zones, EU-Hydro, the water and wetness layers, and the C3S hydrology and precipitation sets.
- The EMERGENCY filter returns **0 items**, so EFAS, GloFAS, GFM and rapid mapping are not catalogued here. They live on EWDS, on the JRC FTP and on the CEMS portals.
- The catalogue lags behind CLMS: Imperviousness Density **2024** and Change 2021-2024 are in the CLMS API but not here.
- Verdict: **USEFUL as an index.** Every item worth following is reported below.

### 3. Copernicus — "Copyright and licences" (tab 595428145)
- What it is: despite the title, only the **Copernicus trade mark and logo licence**. Using the logo needs the registration form ("I accept"). You must acknowledge EU ownership and that the Commission is programme manager, and must not imply EU endorsement. The licence runs until 30 Nov 2032.
- It says **nothing about data**. Data terms come from Delegated Regulation (EU) 1159/2013 (free, full and open) and from each service's own licence (see Licences below).
- Verdict: **USEFUL as a warning.** Do not put the Copernicus logo on the brief or in the app; text credits need no registration.

### 4. ECMWF wiki — "How to install and use CDS API on Windows" (tab 595428150, modified 6 May 2026)
- Steps, in short: an account, Python on PATH, then the 2-line `url:` / `key:` block from the how-to page saved to `%USERPROFILE%\.cdsapirc`, then `pip install cdsapi`. Accept each dataset's terms on its web form.
- It covers CDS and ADS only. **EWDS works the same way with a different URL** (tab 5).
- Verdict: **USEFUL.** It is consolidated into the Windows section below.

### 5. EWDS — "CDSAPI setup" (tab 595428149, `https://ewds.climate.copernicus.eu/how-to-api`)
- The URL for `.cdsapirc` is `https://ewds.climate.copernicus.eu/api` and the recommended client is `cdsapi>=0.7.7`, which the kit already pins. Terms must be accepted manually per dataset. `ecmwf-datastores-client` is offered as an "Incubating" alternative.
- **The page's example request is stale.** Run through the costing endpoint it is rejected ("Request has not produced a valid combination of values"). The live `cems-glofas-historical` form uses `year`/`month`/`day`, `average_river_discharge_in_the_last_24_hours`, `timespan` and `version_4_0`/`version_5_0`, not `hyear`/`hmonth`/`hday`, `mean_discharge_in_the_last_24_hours` and `version_2_1`. Build every request from the form JSON, as `fetch_cds_member.py` already does.
- Verdict: **USEFUL.**

---

## Datasets followed from the tabs

### EFAS historical reanalysis — `efas-historical` (EWDS, DOI 10.24381/cds.e3458969)
- **Variables** (`variable`): `river_discharge_in_the_last_6_hours`, `runoff_water_equivalent`, `snow_depth_water_equivalent`, `soil_wetness_index` and `volumetric_soil_moisture` (`soil_level` 1-3). There are also static fields: `upstream_area`, `elevation`, `soil_depth`, `field_capacity` and `wilting_point`. The 24-hour discharge exists **only in system versions 2.0, 3.0 and 3.5** (5 km grid).
- **System version 5.0** (operational): 1 arcmin (about 1.5 km), 6-hourly (`time` 00/06/12/18), years **1992-2026**. Near-real time lags 6 days, and real time is for EFAS partners only. Version 4.0 covers 1991-2024. The extent is stated as 1991-01-01 to 2026-10-21.
- **There is no annual-maximum product and no aggregation option.** You get raw 6-hourly fields and compute maxima locally. The "6 hours" variable is a mean over the preceding 6 h, so an annual maximum of it sits slightly below the instantaneous peak.
- **Spatial subset: yes.** The `area` field is [N, W, S, E] at a 0.001° step, inside N 72 / E 74 / S 24 / W -35. **Single years such as 2021: yes**, through `hyear`/`hmonth`/`hday`/`time`.
- **Limits (measured with the costing endpoint).** The cost is the number of fields (days × times × variables), and the limit is **1,500 per request**. The area does **not** lower the cost.
  - July 2021, every day and time step: 124 fields.
  - 10-20 July 2021: 44 fields.
  - All of 2021: 1,488 fields, which just fits.
  - So it is **one request per year per variable**.
- **File sizes (estimated).** One full-domain field is about 54 MB uncompressed. The EFAS v5.1 threshold NetCDF, a single full-domain float field, is 53,845,923 B, which matches a 4530 × 2970 float32 grid; that grid size is confirmed on the RP100 file on disk (`lon` 4530 × `lat` 2970). So a full-domain year of 6-hourly discharge is roughly 78 GB uncompressed.
  - A Meuse/Ahr box such as `[52, 3, 49, 8]` is about 0.2 MB per field, so all of July is about 30 MB uncompressed. The July file fetched on 2026-10-24 (124 × 180 × 300, zlib) is 10,788,324 B.
- **Policy questions.**
  - July 2021 peaks against return levels (see item 1): feasible, small.
  - A Europe-wide peak-discharge trend since 1992: **not feasible offline** from EWDS. Use HERA. A trend for a handful of basin boxes is feasible: 34 requests each.
- **Licence:** CEMS-FLOODS datasets licence (below). The catalogue's own message says to check the EFAS known-issues wiki before downloading.

Exact request body (cost 44 of 1,500, measured):

```python
import cdsapi
client = cdsapi.Client(url="https://ewds.climate.copernicus.eu/api", key=EWDS_KEY)  # see Windows section
client.retrieve("efas-historical", {
    "system_version": ["version_5_0"],
    "variable": ["river_discharge_in_the_last_6_hours"],
    "model_levels": "surface_level",
    "hyear": ["2021"],
    "hmonth": ["07"],
    "hday": [f"{d:02d}" for d in range(10, 21)],
    "time": ["00:00", "06:00", "12:00", "18:00"],
    "data_format": "netcdf",
    "download_format": "unarchived",
    "area": [52, 3, 49, 8],          # N, W, S, E
}, "efas_v5_dis06_2021-07-10_20_meuse_ahr.nc")
```

For the static field, which needs no time keys and has cost 1, send
`{"system_version": ["version_5_0"], "variable": ["upstream_area"], "model_levels": "surface_level", "data_format": "netcdf", "download_format": "unarchived"}`.
NetCDF is the only format offered for it. Use it to keep only river cells
(for example, upstream area > 150 km², to match the hazard maps).

### EFAS / GloFAS flood thresholds (CEMS wiki, "Auxiliary Data" page)
- Files: `flood_threshold_efas_v5.1_rl_{1.5,2.0,5.0,10.0,20.0,50.0,100.0,200.0,500.0}.nc`, plus `_mu.nc` and `_sigma.nc` (the Gumbel parameters, fitted with L-moments). The links are `https://confluence.ecmwf.int/download/attachments/242067380/<file>`. HEAD on RP100 returned 200 with no login, 53,845,923 B.
- Verdict: **USEFUL, no account.** With the July 2021 window, they answer "was it a 100-year flood, and where".
- **Resolved since** (see `docs/cems_flood_wiki_review.md`, Q1):
  - The fitting period is 1992-01-01 to 2022-12-31. The EFAS v5.1 release page states it as the "Reference climatology (for thresholds/anomalies)" (<https://confluence.ecmwf.int/spaces/CEMS/pages/435948254/EFAS+v5.1>).
  - v5.1 thresholds match the `version_5_0` reanalysis: the same page says "This upgrade of EFAS has no impact on the EFAS modelling results".

### HERA — Hydrological European ReAnalysis (JRC FTP, `CEMS-EFAS/HERA/`)
- **v2.0** (2025-07-29): `VER2-0/Data/NetCDF/river_discharge/dis.HERA_v2_{1951..2020}.nc`, 70 files of about 2.3 GiB each (2020: 2,490,256,518 B). The server sends `Accept-Ranges: bytes`. v2 changes how groundwater return flow is modelled, which removes spurious discharge increases, so use v2 rather than v1.
- **v1.0 README:**
  - 1 arcmin; 6-hourly discharge for rivers with more than 100 km² upstream; 1950-2020.
  - Domain: EU27, UK, CH, IS, NO and the Western Balkans.
  - Forcing: downscaled, bias-corrected ERA5-Land, with **dynamic** land use, water demand and reservoirs.
  - v1 also ships the climate inputs, land use (including `fracsealed`) and reservoirs.
  - Reference paper: Tilloy et al., "HERA: a high-resolution pan-European hydrological reanalysis (1950-2020)". The journal and DOI are **not verified** here.
- **Policy questions:**
  - observed change in annual maximum discharge per river cell, then per NUTS3 or per basin, over 1951-2020 or 1991-2020;
  - whether the 1-in-100 level shifted.
  - It is the observed counterpart to the kit's projected discharge change.
- **Licence:** CC BY 4.0, "(c) European Union, 1995-2026" (`CEMS-EFAS/copyright.txt`). No account is needed.
- **Caveats:**
  - It stops at 2020, so 2021 needs EFAS.
  - It is a model forced by reanalysis, not gauges.
  - A per-file annual maximum still means reading all 2.3 GiB once. The files are chunked `[1 time step, 14 rows, all 4530 columns]` with zlib level 4 (read on `dis.HERA_v2_2020.nc` on disk), so even a small box reads full-width row bands at every one of the 1,464 time steps.
  - The RAM rule in our working rules applies: one year at a time.
- **HERA sealed fraction** (`VER1-0/Data/NetCDF/socioeconomic_maps/landuse/fracsealed_European_01min_{1950..2020}.nc`, 71 files of 9.5-13 MB): the cheapest sealing trend available, with no account.

### CLMS Imperviousness (HRL Imperviousness Density and Change)
- **2018** (10 m and 100 m, EPSG:3035): prepackaged Europe files `IMD_2018_100m_eu_03035_v020` (**66 MB**) and `IMD_2018_010m_eu_03035_v020` (3 GB). Source "EEA", downloaded from the CLMS site after logging in with **EU Login**.
  - The same layer is also an **anonymous** EEA ImageServer: `https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic/HRL_ImperviousnessDensity_2018/ImageServer` (U8, 10 m, maximum export 15000 × 4100 px).
  - Exporting a European mosaic from it is possible in principle, but **not tested** and not recommended over the 66 MB file.
- **2021 and 2024**, and the **Change** layers for 2018-2021 and 2021-2024: `full_source: WEKEO`, `datasetId EO:EEA:DAT:HRL:IMP`. So they need a **WEkEO** account and its HDA API.
- **2006-2015** (20 m / 100 m): prepackaged through CLMS.
- Values are 0-100 % sealed. Coverage: EEA38 + UK.
- **No NUTS3 aggregate is published.** You compute it with the kit's zonal code, which is feasible because both grids are EPSG:3035 (unlike GHSL).
- The CLMS download API can **clip to a NUTS code** (`"NUTS"` in `@datarequest_post`, **NUTS 2021** codes, NUTS 0-3). Results are delivered by email and through a task ID. That is too slow for 1,345 regions; take the Europe file.
- **What it adds:** sealed share per region and sealed share inside the RP100 footprint, as a pluvial and runoff proxy. Licence: CC BY 4.0 (stated on the record).

### CORINE Land Cover 2018 (CLMS)
- Prepackaged files: `u2018_clc2018_v2020_20u1_raster100m` (**125 MB** GeoTIFF), GPKG (4 GB) and FGDB (5 GB). EPSG:3035, EEA39. Downloaded after **EU Login**.
- Verdict: **USEFUL.** It fills the `copernicus_corine_land_cover` entry that is declared but has no file. Take the 100 m raster. The vectors are too heavy for the venue.

### Urban Atlas (2006, 2012, 2018, 2021; change layers; building height; street trees)
- Delivered per functional urban area, as FlatGeobuf for 2018. Examples: BE001 Brussels 57.3 MB, BE005 Liège 27.8 MB.
- Several editions (2018, 2021, and the change layers for 2018-2021) are not offered as one full-dataset file (`downloadable_full_dataset: False`).
- Verdict: **NOT USEFUL for NUTS3 Europe.** Cities only. It is worth a single Liège or Namur zoom at most.

### Riparian Zones LC/LU 2012 and 2018, and change 2012-2018 (CLMS)
- A buffer around EU-Hydro rivers with detailed land cover: `RZ_2018_eu` is a **5 GB** shapefile, or one file per delineation unit at 11-311 MB each.
- Verdict: **MAYBE, post-hackathon.** It would answer "how much floodplain was built over between 2012 and 2018", but the hazard maps plus GHSL already approximate this.

### EU-Hydro River Network Database (CLMS)
- Prepackaged files: `EU_hydro_fgdb_eu.zip` (2 GB) and `EU_hydro_gpkg_eu.zip` (4 GB), or one file per basin (Danube GPKG 534 MB, Elbe 100 MB).
- Verdict: **NOT USEFUL now.** Basin membership already comes from the WFD layer (`src/basins.py`).

### Water and wetness, Water Cover Duration, Water/Ice Cover (CLMS HRL)
- Probability of water and wetness at 10, 20 or 100 m, and yearly water cover duration from 2016, in UTM tiles.
- Verdict: **NOT USEFUL.** It shows permanent and seasonal water, not flood events. The kit's permanent-water mask comes with the hazard maps.

### C3S ECDE aggregated climate indicators — `sis-ecde-aggregated-climate-indicators` (CDS, DOI 10.24381/accabcec, CC BY 4.0)
- **Wet variables:** `maximum_consecutive_five_day_precipitation`, `extreme_precipitation_total`, `frequency_of_extreme_precipitation`, `flood_recurrence` (1-in-2, 5, 10 and 50 years) and `mean_river_discharge`.
- **Products:** 30-year statistics, global-warming-level changes and quantiles, anomalies and time series.
- **Regional layers:** NUTS 0-3, transnational regions, EU27/EEA38.
- **Caveat, read from the constraints file.** The heavy-precipitation indicators are aggregated only down to **NUTS2**. NUTS3 exists only for `snowfall_amount`, and `flood_recurrence` and `mean_river_discharge` are **gridded only**. The kit's NUTS3 regions would inherit their NUTS2 parent's value; say so in the brief.
- Cost: 6 of 1,000 for three variables × two products at NUTS2. Small.
- Same CDS account as `fetch_cds_member.py`.

### C3S extreme precipitation risk indicators — `sis-european-risk-extreme-precipitation-indicators` (CDS, DOI 10.24381/cds.3a9c4f89, CC BY 4.0)
- Europe-wide grids from E-OBS (1950-2019) and ERA5 (1979-2019):
  - annual and monthly maximum 1-day and 5-day precipitation, and days above 20 mm;
  - precipitation **at return periods of 5, 10, 25, 50 and 100 years** (1989-2018).
- 2 km city grids for 20 cities, including **Brussels, Antwerp and Cologne**. They are pluvial-specific.
- Cost: 60 of 1,000 for two variables over 30 years.
- Verdict: **MAYBE.** It is a good observed pluvial counterpart, but item 6 is already regional, and this one needs a zonal pass.

### C3S hydrology projections — `sis-hydrology-variables-derived-projections`
- **Already in the kit.** Its licence on the catalogue is now listed as "CC-BY licence".

### Other EWDS collections (12 in all)
- `efas-forecast`, `efas-reforecast`, `efas-seasonal`, `efas-seasonal-reforecast`, `cems-glofas-forecast`, `cems-glofas-reforecast`, `cems-glofas-seasonal`, `cems-glofas-seasonal-reforecast` and the two fire sets: **NOT USEFUL**. They are operational forecasts or forecast-skill research.
- `cems-glofas-historical` (0.05°, daily, 1979-2026; cost 365 per year against a limit of **500**): **NOT USEFUL for Europe**. EFAS and HERA are finer and European.

### CEMS rapid mapping — public dashboard API
- `https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/?limit=1000` answers **anonymously**: 268 activations, EMSR656-EMSR935. Of these, 90 are floods and 53 are floods in EU countries (2023-03-30 to 2026-10-19). The per-activation endpoint (`public-activations/?code=`) needs credentials.
- Older activations such as the kit's EMSR517 and EMSR518 stay on the public S3 path already in `sources.yaml`.
- Verdict: **USEFUL, cheap.** It gives counts by country and year for the brief.

### CEMS Global Flood Monitoring (GFM) — API `https://api.gfm.eodc.eu/v2/` (swagger "GFM JRC API" 24.01)
- Free registration (`/auth/register`), then `/auth/login` for a bearer token. You create an AOI (`/aoi/create`), then order `/download/max_flood_extent/{aoi_id}/{start_date}/{end_date}`, or ask for an archive download through `/support/archive_download`.
- Verdict: **NOT USEFUL now.** The kit's `jrc_observed_flood_depth` (2015-2025, 20 m) is FLEXTH applied to these same GFM extents. GFM's archive start date and limits are **not verified**: the documentation page sits behind a cookie banner that was not accepted.

### EFAS rapid impact assessments, EFAS real-time data
- For EFAS partners only. The efas-historical description says so of real time, and `tab_review.md` records "authorisation required" for the EFAS WMS-T.
- Verdict: **NOT ACCESSIBLE in real time.** Corrected by `docs/cems_flood_wiki_review.md` (Q5): forecasts older than 30 days, RIA included, are public through the anonymous EFAS WMS-T; `sources.yaml` declares this as `efas_rapid_impact_archive`.

---

## Licences: what to print and what may be published

| Source | Terms | Credit line to print |
|---|---|---|
| EFAS / GloFAS (EWDS, thresholds) | CEMS-FLOODS licence. Reproduction, distribution, communication to the public and adaptation are all allowed. Not a flood warning. | Derived numbers: *"Contains modified Copernicus Emergency Management Service information 2026"*. Unmodified data: *"Generated using Copernicus Emergency Management Service information 2026"*. |
| HERA, JRC FTP | CC BY 4.0, © European Union | "JRC HERA v2.0, © European Union, CC BY 4.0; modified" |
| CLMS (Imperviousness, CORINE…) | Free, full, open; CC BY 4.0 on the record | *"Generated using European Union's Copernicus Land Monitoring Service information"* + DOI. IMD 2018 100 m: 10.2909/... (take it from the record). IMD 2024: 10 m `10.2909/f0bcb6f0-d775-4218-bec1-13adea01ff8f`, 100 m `10.2909/982010c7-1efa-441f-a758-7ecb20bdaac4`. |
| C3S (ECDE, extreme precipitation, hydrology projections) | CC BY 4.0 | "Copernicus Climate Change Service (C3S), <dataset title>, DOI …; modified" |
| Copernicus trade mark | Logo licence with a registration form | **Do not use the logo.** Text credits need nothing. Do not imply EU endorsement. |

**Public repo:** derived NUTS3 numbers are fine under all of the above, with
the notice and a "modified" statement. The CEMS licence lists distribution and
communication to the public explicitly, and CC BY 4.0 allows it. Unlike GISCO
boundaries, nothing here bars a public repo. Even so, keep raw rasters out of
git for size.

---

## Setting up the APIs on Windows

**How the kit reads credentials today.**

- `scripts/fetch_cds_member.py` calls `cdsapi.Client()` with no arguments.
- `cdsapi` takes `CDSAPI_URL` and `CDSAPI_KEY` from the environment first, and
  falls back to `%USERPROFILE%\.cdsapirc`.
- The script imports `src`, and `src/__init__.py` loads `.env`
  (`override=False`).
- `.env.example` ships `CDSAPI_URL=https://cds.climate.copernicus.eu/api` with
  an empty `CDSAPI_KEY`.

On this machine `.env` sets `CDSAPI_URL`, `CDSAPI_KEY` and `EWDS_API_KEY`;
there is no `~/.cdsapirc`. A `.env` copied from the example pins the URL to the
CDS.

1. **One ECMWF account for CDS, ADS and EWDS.** You appear to have one already;
   see the note at the top. Register at
   `https://cds.climate.copernicus.eu` or `https://ewds.climate.copernicus.eu`.
   **Not verified:** whether the personal access token is identical on both
   portals. Compare the `key:` shown on `https://cds.climate.copernicus.eu/how-to-api`
   with the one on `https://ewds.climate.copernicus.eu/how-to-api` before
   relying on one key for both.
2. **Accept the licences on the web, once per dataset.** On the EWDS
   `efas-historical` download page, accept "CEMS-FLOODS datasets licence"
   (bottom of the form). On the CDS, accept "CC-BY licence" on
   `sis-ecde-aggregated-climate-indicators`. Without this, every request
   returns a licence error.
3. **Client:** `.venv\Scripts\python.exe -m pip install "cdsapi>=0.7.7"`.
   It is already in `requirements.txt`.
4. **Keep the CDS setup as it is, and pass EWDS explicitly.**
   - `%USERPROFILE%\.cdsapirc` (or `.env`) keeps the **CDS** pair:
     ```
     url: https://cds.climate.copernicus.eu/api
     key: <CDS personal access token>
     ```
     To create the dotfile in PowerShell, run `notepad "$env:USERPROFILE\.cdsapirc"`,
     paste the two lines and save. Notepad must not add `.txt`; choose "All files".
   - For EWDS, do not edit the rc file. Put the key in `.env` under a separate
     name (`EWDS_API_KEY=`, which `scripts/fetch_efas_july2021.py` reads;
     not in `.env.example`) and build the client with explicit arguments, which override both the environment
     and the rc file:
     ```python
     cdsapi.Client(url="https://ewds.climate.copernicus.eu/api", key=os.environ["EWDS_API_KEY"])
     ```
     A second rc file selected through `CDSAPI_RC` would **not** work while
     `.env` sets `CDSAPI_URL`: the environment URL wins, and the request would
     go to the CDS with the EWDS key.
   - **Checked on the installed `cdsapi` 0.7.7:** if `.env` contains
     `CDSAPI_KEY=` empty, python-dotenv sets an empty string.
     `credentials_present()` then reports `~/.cdsapirc` (when that file
     exists), but the client takes the empty key and never reads the rc file:
     it falls back to the rc file only when the variable is absent. Either
     fill `CDSAPI_KEY` or delete the empty line.
5. **Limits measured today:**
   - EWDS `efas-historical`: 1,500 fields per request.
   - EWDS `cems-glofas-historical`: 500.
   - CDS ECDE and extreme precipitation: 1,000.
   - Requests are queued, and minutes is normal.
   - **Not verified:** the number of concurrent jobs per user.
6. **CLMS (EU Login).**
   - Simplest: log in at `https://land.copernicus.eu`, open the dataset page
     and download the prepackaged Europe file. That is `IMD_2018_100m_eu_03035_v020`
     (66 MB) for imperviousness and `u2018_clc2018_v2020_20u1_raster100m`
     (125 MB) for CORINE.
   - For scripting: profile → **API Tokens** → *Create new Token*. The service
     key JSON (`client_id`, `key_id`, `private_key`, `token_uri`, `user_id`)
     is shown **once**. Save it outside the repo, for example in
     `%USERPROFILE%\.clms\service_key.json`.
   - Then sign an RS256 JWT, POST it to `https://land.copernicus.eu/@@oauth2-token`
     (`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`) and use the
     1-hour bearer token on `/api/@get-download-file-urls` or
     `/api/@datarequest_post`. This needs `PyJWT` and `cryptography`.
     Delivery is asynchronous, by email.
7. **WEkEO (only for Imperviousness 2021/2024 and the change layers).** Create
   a free account at `https://www.wekeo.eu` and install the `hda` client.
   **Not verified:** the exact name and format of the `hda` credentials file.
   Read the WEkEO HDA documentation before setting it up. Enter the password
   yourself; it never goes in the repo.
8. **No account at all:**
   - HERA and the sealed fraction (JRC FTP);
   - the EFAS/GloFAS thresholds (Confluence attachments);
   - the rapid-mapping activation list;
   - the EEA ImageServer.

**Accounts you must create (or already have).** You create them yourself; this
review created none.

- **ECMWF account**, which covers both CDS and EWDS. You appear to have one.
  Still to do: accept 2 licences.
- **EU Login**, for CLMS (Imperviousness 2018, CORINE 2018).
- **WEkEO**: optional, only for Imperviousness 2021/2024.
- **GFM**: not needed.

---

## Counts

- Tabs read: 7 of 7 (5 distinct pages).
- Follow-up sources read:
  - services catalogue: 22 pages, 380 items, 115 flood-related, 0 under EMERGENCY;
  - EWDS catalogue: 12 collections, 2 forms and constraints read in full, 6 costing calls;
  - CDS catalogue: 145 collections listed, 3 read;
  - CLMS API: 13 dataset records;
  - JRC FTP: 6 folders;
  - rapid-mapping API, GFM swagger, CEMS Auxiliary Data wiki page, CLMS API docs and data policy.
- Verdicts on the 20 datasets or services reported above:
  - USEFUL 8: EFAS historical (July 2021 window only), EFAS thresholds, HERA discharge, HERA sealed fraction, IMD 2018, CORINE 2018, ECDE aggregated, rapid-mapping list;
  - MAYBE 2: Riparian Zones, C3S extreme precipitation;
  - NOT USEFUL or not accessible 9: Urban Atlas, EU-Hydro, water/wetness layers, the other EWDS forecast collections (counted once), GloFAS historical, GFM, EFAS RIA/real time, IMD 2021/2024 for now (WEkEO only), the trade-mark page as a data source;
  - already in the kit 1: C3S hydrology projections.

## Not verified (check before quoting)

Resolved items (threshold fitting period, grid size, HERA chunking, empty
`CDSAPI_KEY`, RIA access) are stated in the sections above.

- The HERA paper's DOI.
- Whether the CDS and EWDS personal access tokens are the same.
- The GFM archive start date and limits.
- The WEkEO `hda` credentials file.
- Anonymous `exportImage` on the EEA ImageServer (not called).
- The DOI of IMD 2018 (only the 2024 DOIs were read).
