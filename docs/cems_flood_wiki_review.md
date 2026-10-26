# CEMS-Flood wiki review: what the ECMWF Confluence tree holds for the kit

Read on 2026-10-24. The whole `CEMS-Flood` tree on
`confluence.ecmwf.int` (root page 239344446) was read through the anonymous
REST API (`/rest/api/content/<id>?expand=body.view`, then `/child/page` and
`/child/attachment`). The crawl was breadth-first, one request at a time, at
least 0.5 s apart. No login and no cookies were used.

- **Pages read: 333 of 333 reachable, 0 failed.** Pages that anonymous users
  cannot see do not appear in the child listings, so their number is unknown.
  Several pages show "Unable to load page tree" for anonymous users. This only
  affects the page-tree widget; the REST child listing still returned every
  page.
- **Attachments listed: 2,151** (5.03 GB in total). 2,086 of them are images.
  None was downloaded except the 53 KB CEMS-FLOODS licence PDF linked from the
  EWDS catalogue. Sizes come from the API's `fileSize`.
- **Verdicts: 25 USEFUL, 29 MAYBE, 279 NOT.** Most NOT pages are GloFAS-only,
  forecast-operations or navigation pages.
- **Outside the wiki** (small read-only checks, named where they are used):
  - the anonymous EFAS WMS `GetCapabilities` (212 KB), five `GetFeatureInfo`
    calls (three refused for their format) and two empty `GetMap` calls;
  - the EWDS catalogue record and licence PDF for `efas-historical`;
  - two JRC Data Catalogue records;
  - 13 JRC FTP directory listings;
  - the `efas.eu` terms page, which is only a React shell;
  - the kit's own local `jrc_flood_hazard/README.txt` and `CHANGELOG.txt`.

This file does not repeat `docs/copernicus_review.md`. Section 2 corrects it.

---

## 1. The six questions

### Q1. Fitting period of the EFAS v5.x thresholds, and do v5.1 thresholds match the `version_5_0` reanalysis on EWDS?

**Fitting period: 1992-01-01 to 2022-12-31 (31 years).**

- The EFAS FAQ says: "The modelled long-term discharge series (e.g.
  1992-2022 in the case of EFASv5) is used to calculate return period
  thresholds ... based on the Gumbel extreme value distribution."
  <https://confluence.ecmwf.int/spaces/CEMS/pages/293701841/7+FAQ+in+EFAS>
- Every v5.x release page states "Reference climatology (for thresholds/
  anomalies): 1992-01-01 to 2022-12-31". See v5.0
  <https://confluence.ecmwf.int/spaces/CEMS/pages/388511564/EFAS+v5.0>, v5.1
  <https://confluence.ecmwf.int/spaces/CEMS/pages/435948254/EFAS+v5.1> and the
  current v5.6
  <https://confluence.ecmwf.int/spaces/CEMS/pages/265028277/Latest+operational+EFAS+release>.
- The method is a Gumbel fit by L-moments. The code is
  `ec-jrc/lisflood-utilities` (thresholds), and `mu`/`sigma` are published.
  <https://confluence.ecmwf.int/spaces/CEMS/pages/242067380/Auxiliary+Data>
- For comparison, EFAS v4 used 1991-2017 (5 km)
  <https://confluence.ecmwf.int/spaces/CEMS/pages/265028202/EFAS+v4.0>, and
  GloFAS v4 used 1979-2022 (Auxiliary Data page).

**Consistency with `version_5_0`: yes, same model run.**

- v5.1 (2024-03-21) is a *minor* release. The versioning rules say only a
  major release changes "the LISFLOOD model output" and "is always followed by
  a new release of the historical simulations".
  <https://confluence.ecmwf.int/spaces/CEMS/pages/265028159/EFAS+versioning+system>
- The v5.1 page says "This upgrade of EFAS has no impact on the EFAS modelling
  results" and keeps internal number 20, the same as v5.0. Its threshold items
  are "EFAS flood threshold made available on wiki" and "Bug fixes to flood
  threshold calculation".
- So "v5.1" names the *threshold product release*. The thresholds are fitted
  to the v5.0 hydrological run, which EWDS serves as `version_5_0` (there is
  no `version_5_1` historical).

**Caveats to carry into the kit:**

- **Use the v5.1 files, not the older v5 files.** The Auxiliary Data page also
  holds 11 *unlinked* `flood_threshold_efas_v5_*.nc` attachments of the same
  size. They are most likely the pre-fix set. Use only the linked `v5.1`
  files, as the kit already does.
- **2021 is inside the fitting window.** The July 2021 annual maximum is one of
  the 31 values the Gumbel was fitted on (an in-sample estimate). At a cell
  where July 2021 is the record, this pulls the fitted return levels towards
  it, so the event's return period is somewhat understated. Say "against
  EFAS v5 return levels fitted on 1992-2022, which include 2021".
- **The calibration window (1990-2021) also includes July 2021.**
  <https://confluence.ecmwf.int/spaces/CEMS/pages/340784754/EFAS+v5.0+-+Calibration+Data>
- **Re-issued data after 2022 does not affect the fit.** Known Issues: v5
  historical data from 2023-01-01 was wrong until the hotfix of 29 May 2024
  and had to be re-downloaded. This is outside 1992-2022, so the thresholds
  are untouched.
  <https://confluence.ecmwf.int/spaces/CEMS/pages/265028278/EFAS+-+Known+Issues>
- **Unverified:** whether the annual maxima are taken from the 6-hourly series
  or from daily means. The wiki does not say for EFAS. GloFAS v5 says "annual
  maxima" of daily data.

### Q2. The EFAS v5 grid: resolution, projection, domain, upstream-area floor

**Grid: 1 arcmin (0.0166667°, "~1.4 km"), regular lat/lon on WGS84
(EPSG:4326).** It is not ETRS89-LAEA and not 1 km.

- Model Output, "EFAS Horizontal Resolution and Projection": "Since EFAS v5.0
  ... 1 arcmin/ 0.0166667 degrees resolution (~1.4km) ... World Geodetic
  System 1984 (EPSG 4326)".
  <https://confluence.ecmwf.int/spaces/CEMS/pages/242067364/Model+Output>
- ETRS89-LAEA (EPSG:3035) was the **5 km** grid of EFAS v4.0 and earlier:
  1000 × 950 cells, origin (2,500,000; 5,500,000) m.
  <https://confluence.ecmwf.int/spaces/CEMS/pages/242067380/Auxiliary+Data>,
  <https://confluence.ecmwf.int/spaces/CEMS/pages/242067397/Data+Structure+and+Formats>.
  No EFAS version ever used 1 km LAEA.

**Size and domain (now verified, previously inferred from a file size):**

- **4530 columns × 2970 rows.** Source: the LDD v5 metadata (`lon = 4530`,
  `lat = 2970`, `GeoTransform = "-25.25 0.01666666666666666 0 72.25 0
  -0.01666666666666666"`) and the threshold metadata.
- The outer edges are **lon -25.25 to 50.25, lat 22.75 to 72.25**. Cell
  centres run from -25.24167 to 50.24167 and from 72.24167 to 22.75833.
- The domain was "enlarged to match the river catchments" in v5.0, "from
  northern Africa beyond the northern tip of Scandinavia ... far into the
  Atlantic ... as far as to the Caspian Sea".

**The upstream-area floor is not one number:**

- **150 km²** is the working floor. "most of our products/layers use 150 km2
  as a threshold" (Model Output). It is also the floor of the flood inundation
  (hazard) maps from EFAS v5
  <https://confluence.ecmwf.int/spaces/CEMS/pages/340774762/CEMS-Flood+flood+inundation+maps>,
  of the calibration stations (v5 calibration methodology, 340784760) and of
  the recommended point extractions (FTP page).
- **50 km²** is the floor below which EFAS is "not recommended". Flood
  probability / reporting-point signals are computed for upstream > 50 km² and
  only where the 1.5-year return level > 1 m³/s
  <https://confluence.ecmwf.int/spaces/CEMS/pages/514313079>.
- **150-1,000 km²** is the band for ERIC flash-flood points.
- For the kit, **keep 150 km²**. It matches both the hazard maps and the
  thresholds' intended use.
- **Where to get v5 upstream area:** the wiki's v5 upstream-area metadata
  still reads "TBD". The file comes from EWDS (`upstream_area`,
  `version_5_0`), or without an account from the JRC FTP (see section 3,
  item 3).

### Q3. EFAS historical/reanalysis: variables, time steps, discharge definition, known issues, versions

Source unless stated: Model Output
<https://confluence.ecmwf.int/spaces/CEMS/pages/242067364/Model+Output>.

- **Variables from v5.1:**
  - river discharge (`dis06`, param 240023);
  - soil wetness index, root zone (`swir`);
  - runoff water equivalent, surface plus subsurface (`rowe`, accumulated);
  - snow depth water equivalent (`sd`, instantaneous).
  - Volumetric soil moisture (3 layers) was **withdrawn on 2024-03-20**. It is
    still served for the reanalysis only up to that date.
  - Static fields (upstream area, elevation, soil depth, field capacity,
    wilting point) are on EWDS.
- **Time step: 6-hourly from v4.0 onwards** (24-hourly up to v3.5).
  - Internally, LISFLOOD runs 6-hourly for all processes and **hourly for
    river routing**
    <https://confluence.ecmwf.int/spaces/CEMS/pages/340784752/EFAS+v5.0+-+Hydrological+Model>.
  - Coverage of v5.0: 1992-01-01 to near real time with a 6-day lag. Real time
    is partner-only.
- **Discharge definition: a mean over the model step, not an instantaneous
  value.** GRIB name "Mean discharge in the last 6 hours", `stepType=avg`. The
  definition reads: "averaged over a time step through a cross-section". An
  annual maximum of `dis06` therefore sits below the instantaneous peak; this
  matters most on small, flashy rivers such as the Vesdre.
- **The wiki contradicts itself on the time stamp. Unresolved; check
  `valid_time` in the file.**
  - Model Output: the time stamp is the "date and time of end of averaging
    period".
  - Known Issues (Aug-Sept 2023 entry): "in MARS, data is archived at the
    beginning of the timestep", so "the 12:00 timestep represents average
    discharge over the following 6 hours (i.e. from 12:00 to 18:00)".
  - This shifts the timing of a peak by 6 h. It does not change its size.
  - Measured on the kit's July 2021 file (`efas_v5_dis06_2021-07_meuse_ahr.nc`,
    requested for 1-31 July at 00/06/12/18): its `valid_time` runs from
    2021-07-01 06:00 to 2021-08-01 00:00 UTC, i.e. each field is stamped 6 h
    after the requested time, at the end of its averaging window.
- **Known issues relevant to the kit**
  <https://confluence.ecmwf.int/spaces/CEMS/pages/265028278/EFAS+-+Known+Issues>:
  - v5 historical data from 2023-01-01 was wrong until 29 May 2024
    (re-download). It does not affect July 2021.
  - v5.0 historical was shifted by 6 h when first archived; fixed by
    2023-09-13.
  - EFAS NetCDF from the CDS was corrupt on 19-21 March 2024.
  - Precipitation over Poland was too low in July-September 2025.
  - Area extraction was broken for **EFAS v4 and older**: it was removed
    there, and the extraction software was updated on 2025-12-03. v5 cropping
    works. The "Extract subset" page still says "removed", which is stale.
  - From 2026-09-02 the water balance uses Hargreaves instead of
    Penman-Monteith (no effect on 2021).
- **Versions:**
  - v5.0 is the only v5 historical run. Minor releases 5.1-5.6 share it.
  - v4.0 ran on the 5 km LAEA grid, 1991 onwards, with thresholds on
    1991-2017. **The system operational in July 2021 was v4.2.**
  - Forcing for v5: the **EMO-1** 1 arcmin observation grids (SPHEREMAP
    interpolation, Penman-Monteith ET0), 1990 onwards
    <https://confluence.ecmwf.int/spaces/CEMS/pages/333803146/EFAS+v5.0+meteorological+forcing>.
  - Calibration used 1,903 stations of at least 150 km² (43.4 % of the
    domain); the rest is regionalised. The median KGE' is **0.694**
    <https://confluence.ecmwf.int/spaces/CEMS/pages/340784732/EFAS+v5.0+-+Hydrological+Model+Performances>.
- **Archive size:** "EFAS climatology" (the historical dataset, all variables)
  is **817 GB** on MARS
  <https://confluence.ecmwf.int/spaces/CEMS/pages/242067425/EWDS+-+Best+Practices>.

### Q4. How the JRC hazard maps v3.1.1 relate to EFAS, and what EFAS does with flood protection

**Same chain.** The v3.x hazard maps are the CEMS-Flood inundation catalogue
built from the **EFAS v5.0 reanalysis**.

- The kit's local `README.txt` for v3.1.1 lists "EFAS v5.0 hydrological
  reanalysis" among its inputs (R03), cites the efas-historical v5.0 DOI
  (R02), and links the wiki method page from the CHANGELOG.
- EFAS v5.0 release notes: "new flood hazard maps, generated using
  LISFLOOD-FP at 90m resolution and MERIT hydro DM and EFAS v5.0 reference
  dataset" (v5.0 page).

**Method**
<https://confluence.ecmwf.int/spaces/CEMS/pages/340774762/CEMS-Flood+flood+inundation+maps>:

- In every cell above 150 km², a Gumbel fit to the reanalysis annual maxima
  gives the peak for each return period.
- A synthetic hydrograph is built from the Giandotti time of concentration.
- **The 1.5-year discharge is subtracted** as a stand-in for bankfull channel
  flow (channel depth is set to 0).
- LISFLOOD-FP is run on MERIT-DEM at 3 arcsec, one domain every 5 km of
  channel, with Manning's n taken from CGLS land cover.
- Domains are mosaicked by maximum depth.

**Differences to note:**

- The wiki page (Sept 2023) lists **7** return periods (10/20/50/75/100/200/
  500). The kit's v3.1.1 has **9** (it adds 30 and 40). The page predates
  v3.0 (2024-03-08), so it is stale on that point.
- The README's recommended citation for v3.x is **Baugh, Colonese, D'Angelo,
  Dottori, Neal, Prudhomme, Salamon (2024), "An updated dataset of global and
  European flood hazard maps", manuscript in preparation**. It is **not**
  Dottori et al., ESSD 2022, which documents v2.0.0 (see section 4).

**Flood protection in EFAS.**

- **Static layer "Flood Protection Levels"**: "the estimated design return
  period of flood defences ... It is assumed that any flood event above the
  protection level will cause flooding."
  <https://confluence.ecmwf.int/spaces/CEMS/pages/265028366/Static+Layers+Overview>
  - The source is "Bianchi et al., 2022" within the EU, at sub-catchment
    scale. The link points to the JRC dataset 1019a72f, "Flood impacts and
    adaptation strategies under future scenarios" (PESETA IV collection,
    released 2022-09-16).
  - Outside the EU the source is FLOPROS, at the second administrative level.
  - It was updated in **v5.2 (13 Aug 2024)** "using new information
    doi:10.1038/s41558-022-01540-0" (Dottori et al. 2023, NCC)
    <https://confluence.ecmwf.int/spaces/CEMS/pages/462906834/EFAS+v5.2>.
- **The same layer as the kit's? Very likely.** The kit's
  `floodProtection_v2019_paper.zip` sits in the JRC FTP folder
  `PESETAIV/Paper_floods/`. That folder was released in September 2022 and
  holds the inputs of that same paper (listing checked).
  - **Unverified:** that EFAS uses this exact raster. Its layer is described
    as "sub-catchment scale", which matches.
  - If confirmed, the brief can say: *"the same protection standards EFAS uses
    operationally in its rapid impact assessment"*.
- **Rapid impact assessment (RIA) method**
  <https://confluence.ecmwf.int/spaces/CEMS/pages/333791664/CEMS-Flood+flood+impact+forecasting>,
  <https://confluence.ecmwf.int/spaces/CEMS/pages/265028472/EFAS+Rapid+Flood+Mapping+and+Rapid+Impact+Assessment>:
  - River cells where the forecast median exceeds the 10-year return level
    pick the inundation map at the next lower return period. The maps are
    mosaicked, and depth ≥ **0.099 m** counts as "flooded".
  - This gives the **unprotected** scenario.
  - The **protected** scenario drops every river cell whose forecast return
    period does not exceed the local protection level, then re-maps.
  - Both are overlaid on **GHS-POP R2023A 2020, 3 arcsec**, then on land cover
    and OSM critical infrastructure. Results are summed per NUTS (or GADM)
    region, "typically level 1 or 2".
  - The pop-up shows both columns, PROTECTED and UNPROTECTED.
  - This is the **same undefended-versus-residual contrast the brief makes**,
    done operationally by EFAS. The granularity differs: EFAS removes whole
    river cells upstream, while the kit masks the hazard cells where the
    standard ≥ RP.
- **Stated limitations that support the brief's caveats** (same page):
  - "The 3 arc second (~90 m) spatial resolution ... will be insufficient to
    represent local topographic features such as levees";
  - "generated assuming natural river flows" (no diversion or dam retention);
  - riverine only, with no pluvial or coastal flooding;
  - biased wherever the reanalysis is biased;
  - FLOPROS "does not give the precise location and protection level of
    individual assets".
- History: until v4.6 (Oct 2022) the Rapid Flood Mapping layer showed the
  *protected* extent. Since then it shows the unprotected one
  <https://confluence.ecmwf.int/spaces/CEMS/pages/311138753/EFAS+v4.6>.

### Q5. Any EFAS/GloFAS product with impacts (population affected), and is it public?

**Yes: the Rapid Impact Assessment (EFAS and GloFAS)** gives population,
roads, land cover and critical infrastructure per admin region, for both the
protected and unprotected scenarios (Q4 pages).

**Access: real time is partner-only; the archive is public after a 30-day
embargo.**

- "All real-time EFAS forecasts and products are restricted ... the restricted
  EFAS real-time forecasts are released publicly after an embargo of 30 days"
  <https://confluence.ecmwf.int/spaces/CEMS/pages/293701137/2+EFAS+products+overview>.
- Flood Summary layers (RIA among them) "become publicly available for any
  date older than the embargo period"
  <https://confluence.ecmwf.int/spaces/CEMS/pages/293701358/3.2.2+Layer+categories+explained>.
- "The EFAS WMS-T is freely accessible for non authenticated users ... (only
  forecasts older than 30 days)"
  <https://confluence.ecmwf.int/spaces/CEMS/pages/247897113>.

**Verified today without login:**

- The anonymous WMS `GetCapabilities` lists the following layers:
  - `mapserver:RapidImpactAssessment`, queryable, time
    `2019-10-07T00:00/2026-09-24T12:00/PT12H`, so the default is today minus
    30 days;
  - `mapserver:RapidFloodMapping`;
  - `mapserver:FloodProtectionLevels` (`public=true`);
  - `mapserver:Europe_combined_flood_scenarios`;
  - `mapserver:gfm_affected_population`.
- `GetFeatureInfo` with `INFO_FORMAT=application/json` returns the RIA pop-up
  table. `text/plain` and `gml` are refused.
- Two calls were made at a point near Liège (50.62 N, 5.55 E).

| Forecast | Population affected, protected | Population affected, unprotected | Mean RP | Protection level |
|---|---|---|---|---|
| 2021-07-13 12 UTC | 170,300 | 259,600 | 200 yr | 143 yr |
| 2021-07-14 12 UTC | 249,800 | 264,000 | 200 yr | 143 yr |

Both forecasts placed the region in the "high likelihood / high impact"
matrix cell.

**Caveats on these numbers:**

- They are *forecasts* from EFAS **v4.2**: 5 km, the older 100 m maps and the
  pre-2024 protection layer. The layer abstract says "100m resolution flood
  hazard".
- The admin unit is **not identified** in the response. It is probably the
  merged NUTS2/3 Liège unit: **unverified**.
- The figure is people inside the forecast flood extent, not people harmed.

**Other impact products:**

- GloFAS RIA as shapefiles (`CostPopEst{date}.shp`) on the GloFAS FTP, with a
  password on request
  <https://confluence.ecmwf.int/spaces/CEMS/pages/242067469/FTP>.
- GFM "affected population" layers in the same WMS. GFM is partner-only in the
  viewer.
- Experimental radar flash-flood impact layers (GHSL + HARCI-EU exposure).
  These are hourly, recent-only and not useful for 2021.

### Q6. Recommended citation and licence wording for EFAS data

The wiki itself has **no EFAS citation text**. It points to the licence
(`efas.eu/en/terms-and-conditions`, a React page) and to the EWDS DOIs. The
binding text is the **CEMS-FLOODS datasets licence**. It is linked from the
EWDS `efas-historical` record as
`https://object-store.os-api.cci2.ecmwf.int/.../cems-floods_428a6e10....pdf`
(53 KB, read in full).

- **Allowed:** reproduction, distribution, communication to the public,
  adaptation/modification/combination, and any combination of these. Some
  data is restricted under Art. 12 of Delegated Regulation 1159/2013; that is
  the real-time data.
- **Notice for unmodified data:** *"Generated using Copernicus Emergency
  Management Service information [Year]"*.
- **Notice for adapted data:** *"Contains modified Copernicus Emergency
  Management Service information [Year]"*.
- **Disclaimer to repeat:** the data "does not constitute in any way a flood
  warning for which only national/regional institutions are authorized".
- **Dataset citations:**
  - **EFAS historical v5.0**, as cited by the hazard-map README (R02):
    *Mazzetti, C., Carton de Wiart, C., Gomes, G., Russo, C., Decremer, D.,
    Ramos, A., Grimaldi, S., Disperati, J., Ziese, M., Schweim, C., Sanchez
    Garcia, R., Jacobson, T., Salamon, P., Prudhomme, C. (2023): River
    discharge and related historical data from the European Flood Awareness
    System, v5.0. European Commission, Joint Research Centre (JRC).
    doi:10.24381/cds.e3458969.*
  - **Thresholds:** no formal citation. Cite the Auxiliary Data page and the
    `lisflood-utilities` code.
  - **Hazard maps v3.1.1:** DOI 10.2905/1D128B6C-A4EE-4858-9E34-6210707F3C81,
    plus Baugh et al. (2024, in prep.).
  - **EFAS static maps:** Choulga et al. (2026), "LISFLOOD static and
    parameter maps for Europe", doi:10.2905/JRC.1YHPHC8.
  - **EMO-1:** Gomes et al. (2020), doi:10.2905/0BD84BE4-CEC8-4180-97A6-8B3ADAAC4D26.
- The previous review's credit lines are correct (verified against the
  licence PDF).

---

## 2. Corrections to `docs/copernicus_review.md`

| Where | It said | The wiki says | Fix |
|---|---|---|---|
| EFAS historical, sizes | "One full-domain field is about 54 MB ... a full-domain year ... roughly 78 GB"; "Not recommended: EFAS historical for a Europe-wide trend ... 34 years at 6-hourly steps is terabytes" | The *whole* EFAS historical dataset (all variables, all versions) is **817 GB** on MARS, and the documented request size is ~450 MB per 1,000 fields in GRIB2 (EWDS Best Practices, 242067425). 54 MB is the uncompressed float32 NetCDF size; packed GRIB2 fields are far smaller. | "Terabytes" is wrong. A 1992-2022 discharge-only pull is tens to a few hundred GB (**inference**: the 450 MB per 1,000 fields figure may predate the 1 arcmin grid). HERA is still the better trend source (1951-2020, no queue). |
| EFAS historical, limits | 1,500 fields per request (measured) | The wiki table says 1,000 for "EFAS climatology" | Keep the **measured 1,500**; the wiki table is stale. Add: no more than 10 parallel requests, and MARS sessions on Wednesdays slow the queue. |
| EFAS historical, discharge | "a mean over the preceding 6 h" | Model Output: the time stamp marks the end of the averaging period. Known Issues: MARS archives at the start of the step, so 12:00 means 12:00-18:00. | Mark the time stamp as **conflicting in the source**; check `valid_time` in the file before quoting peak *times*. |
| Thresholds, "Unverified" | fitting period unknown (GloFAS v4: 1979-2022) | **1992-2022** for EFAS v5 (FAQ; release tables) | Resolved: see Q1. |
| Thresholds, "Unverified" | whether v5.1 matches `version_5_0` | Same model run; v5.1 is a minor release with "no impact on the EFAS modelling results" | Resolved: see Q1. |
| Grid, "Unverified" | 4530 × 2970, inferred from a file size | Stated in the LDD v5 and threshold metadata | Resolved: see Q2. |
| EFAS RIA / WMS | "NOT ACCESSIBLE"; `tab_review.md`: "authorisation required" for the EFAS WMS-T | Anonymous WMS-T exists for a subset of layers and for forecasts older than 30 days; RIA is among them | Wrong for archived dates. RIA for July 2021 is public (Q5). |
| Static field note | "upstream area > 150 km², to match the hazard maps" | Confirmed (inundation-maps page; Model Output) | No change. |
| EWDS API keys | `hyear/hmonth/hday` for efas-historical | The official example still uses `hyear` for EFAS (EWDS API page). The renaming to `year/month/day` + `timespan` is documented for **GloFAS historical v5** only (699325478). | Fine today. **Unverified:** whether EFAS will follow; build requests from the live form, as the review advised. |

---

## 3. Ranked: what to add to the kit

**Status on 2026-10-26:** items 2-4 are done (the `efas_flood_thresholds` caveat;
`efas_upstream_area.nc`, read by `src/efas.py` as a fallback; EMO-1 through
`src/rainfall.py` into `rainfall_jul2021.parquet`, as four-day event rain per
NUTS3 rather than 1-day and 3-day maxima). Item 5 sits in the
`efas_rapid_impact_archive` caveat. Item 1 is declared but not cached; item 7
is not used.

| # | What | Why it matters for the brief | Access | Effort |
|---|---|---|---|---|
| 1 | **EFAS's own July 2021 rapid impact assessment**, archived. Anonymous WMS `GetFeatureInfo` (JSON) on `mapserver:RapidImpactAssessment`, one point per affected NUTS region (BE, DE, NL), forecasts 12-15 July 2021. | An official, operational **protected vs unprotected** headcount from the same JRC/CEMS family. It shows the undefended/residual contrast is how EFAS itself reasons. It also gives the real-time view of what was expected before the flood. | None, but needs the network: run it before the event, cache the JSON, and respect the one-request-per-second rule. | 2-3 h |
| 2 | **Quote the threshold facts correctly**: fitted on 1992-2022, which includes 2021; same run as `version_5_0`; Gumbel L-moments; use only the `v5.1` files; calibration 1990-2021. | Removes the open "check the wiki" caveat in `sources.yaml` (`efas_flood_thresholds`), and adds the in-sample caveat. | - | 0.5 h |
| 3 | **EFAS v5 upstream area without an account**: `upArea_European_01min.nc`, 51 MB, JRC FTP `CEMS-EFAS/LISFLOOD_static_and_parameter_maps_for_EFAS/v1.1.2_OS-LISFLOOD-v4.x/Catchments_morphology_and_river_network/` (the static maps released for EFAS v5, with `EFASv5.0_calibrated_parameters` beside them). | Masks the July 2021 discharge and thresholds to river cells ≥ 150 km² without the EWDS step. | None (JRC FTP). **Checked 2026-10-25:** identical to the EWDS `upstream_area` v5.0 field fetched by the kit (same 4530 × 2970 grid, all 7,446,075 valid cells equal). Do not use the newer `v.2.0.0_OS-LISFLOOD-v5.x` folder: it is labelled EFAS **v6.0**. | 1 h |
| 4 | **EMO-1 observed precipitation, 2021**: `EMO-1arcmin-pr_2021.nc` (daily, 335 MB) or `pr6_2021.nc` (6-hourly, 777 MB), JRC FTP `CEMS-EFAS/meteorological_forcings/EMO-1arcmin/` (the daily file sits in its `pr/` subfolder). | The *observed* rainfall that forced EFAS. Maximum 1-day and 3-day July 2021 rain per NUTS3 is the pluvial/surface-runoff counterpart that `limitations.md` says the hazard maps lack. | None. One 335 MB year file; RAM is fine for a July slice. | 3-4 h |
| 5 | **EFAS's flooded-depth cut-off: depth ≥ 0.099 m** (CEMS-Flood impact forecasting). | An official point of comparison for the kit's 0.5 m depth threshold, which `limitations.md` names as a choice that moves the headline. Cite it in the sensitivity note. | - | 0.5 h |
| 6 | **Protection-layer provenance**: EFAS's EU "Flood Protection Levels" = Bianchi et al. 2022 / PESETA IV (JRC 1019a72f), in use since v5.2. | Strengthens the residual figure: same family as the layer EFAS uses operationally. Also note EFAS's simplifying assumption that "any flood event above the protection level will cause flooding". | Optional check: one `GetFeatureInfo` on `FloodProtectionLevels` at 3-4 points, compared with the kit's raster. | 1 h |
| 7 | **Model skill line**: EFAS v5 median KGE' 0.694 over 1,903 calibration stations; only 43.4 % of the domain gauged. | A one-line credibility and uncertainty statement for the July 2021 return periods. | - | 0.2 h |
| 8 | **Live WMS overlays** (`FloodProtectionLevels`, `Europe_combined_flood_scenarios`) in the app. | Visual cross-check only. | Needs the network at the venue, so **not recommended** for the offline kit. | - |

---

## 4. Things in the kit's documents that this review touches (not edited)

Status on 2026-10-25: the `brief_draft.md` sources line and the
`efas_flood_thresholds` caveat in `sources.yaml` have since taken in the first
and third points below; the v4.2 note sits in the `efas_flood_thresholds`
caveat rather than in `efas_historical_july_2021`.

- `flood-policy-kit/docs/brief_draft.md`, section 5 ("Sources"): "JRC
  river-flood hazard maps (9 return periods) and their validation (Dottori et
  al., ESSD 2022)". The maps used are **v3.1.1**. Their method is the EFAS v5
  chain above and their reference is **Baugh et al. (2024, in prep.)**.
  Dottori et al. 2022 validates v2.0.0. `sources.yaml` already has this
  caveat (`jrc_hazard_maps_validation_essd_2022`), but the brief does not.
  Suggested wording: "JRC/CEMS river-flood hazard maps v3.1.1 (method: CEMS
  wiki, built on the EFAS v5 reanalysis; validation of the previous
  generation: Dottori et al., ESSD 2022)".
- `brief_draft.md` key messages: "the JRC's own '160,000 exposed annually'".
  The CEMS Data FAQ quotes PESETA IV as **"170,000 people"** a year in the
  EU + UK at present
  (<https://confluence.ecmwf.int/spaces/CEMS/pages/242067503/FAQs>). Check
  which figure and which scope (EU-27 or EU + UK) the brief's source uses.
- `config/sources.yaml` `efas_flood_thresholds` caveat ("Check the CEMS wiki
  for the fitting period before quoting") can now be answered. Its comment
  `crs: EPSG:4326 # EFAS v5 grid, 1 arcmin` is correct.
- `efas_historical_july_2021`: add that EFAS operational in July 2021 was
  **v4.2** (5 km). The data being fetched is the later v5.0 re-run, not what
  forecasters saw at the time.
- `limitations.md`: the EFAS wiki states that the maps are "generated assuming
  natural river flows" and cannot resolve levees at 90 m. This is a citable
  source for the "undefended" reading of v3.1.1 that does not rely on the 2022
  paper.

---

## 5. Not verified (check before quoting)

- Whether the EFAS v5 annual maxima for the thresholds come from 6-hourly or
  daily discharge.
- The source's discharge time-stamp convention (end of step, per Model Output;
  start of step in MARS, per Known Issues). The kit's July 2021 file stamps each
  field at the end of its 6 h window (measured, Q3).
- That EFAS's EU protection layer is byte-for-byte the kit's
  `floodProtection_v2019_paper` raster.
- The admin unit behind the two RIA readings near Liège, and the RIA's
  behaviour at other points and times. Only 2 forecast times at 1 point were
  queried.
- ~~That the JRC FTP `upArea_European_01min.nc` (static maps v1.1.2) equals the
  EWDS `upstream_area` for `version_5_0`.~~ Checked on the two files on disk:
  every valid cell is equal.
- Whether the EWDS `efas-historical` request keys will change the way GloFAS
  historical v5 keys did.
- The per-field GRIB2 size on the 1 arcmin grid. The "450 MB per 1,000 fields"
  figure may predate v5.

---

## 6. Attachments worth having

Of 2,151 attachments, 65 are not images. Those that matter:

| Attachment | Size | URL | Note |
|---|---|---|---|
| `flood_threshold_efas_v5.1_rl_{1.5,2.0,5.0,10.0,20.0,50.0,100.0,200.0,500.0}.nc` | 53,845,923 B each | `https://confluence.ecmwf.int/download/attachments/242067380/<file>` | Already in the kit. |
| `flood_threshold_efas_v5.1_mu.nc`, `_sigma.nc` | 53,845,923 B each | same | Gumbel parameters: they give the return period of *any* discharge, `T = 1/(1-exp(-exp(-(Q-mu)/sigma)))`, instead of bracketing between 9 levels. **Recommended** for the July 2021 analysis. |
| `ldd_efas_5.0.nc` | 13,538,740 B | `https://confluence.ecmwf.int/download/attachments/242067380/ldd_efas_5.0.nc` | v5 flow directions; only needed to trace up and downstream of a cell. |
| `flood_threshold_efas_v5_*.nc` (11 files) | 53,845,923 B each | same folder, **not linked** on the page | Probably the pre-fix set from before v5.1. **Do not use.** |
| `ec_upArea4.0.nc`, `upArea3.5.nc`, `ldd_efas.nc` | 7.6 MB, 3.8 MB, 0.98 MB | same folder | EFAS v4/v3.5 5 km LAEA; not for v5 data. |
| GloFAS thresholds/upstream/elevation (v3, v4) | 21-173 MB each | same folder | Global 0.05° / 0.1°; not needed. |
| `Recalculating the ERIC Display and Warning Thresholds v3.docx`, `ERIC_newLISVAP_results.docx` | 3.9 MB, 0.8 MB | pages 265028274, 265028159 | Flash-flood internals; not needed. |
| `Screen Recording 2025-02-19 at 17.12.40.mov`, `GrimaldiStefania_..._GloFASv5_FIGSwikipptx.xps` | 49.6 MB, 6.2 MB | pages 488284453, 673567683 | Not needed. |

---

## 7. Page-by-page index (333 pages, tree order)

Verdicts: USEFUL = take something into the kit or the brief; MAYBE =
background or a caveat worth knowing; NOT = nothing for the kit. GloFAS-only
pages are one-liners unless they hold something for Europe.

| Page | Link | Verdict | What to take |
|---|---|---|---|
| CEMS-Flood | [239344446](https://confluence.ecmwf.int/spaces/CEMS/pages/239344446/CEMS-Flood) | NOT | Root: navigation, links to EFAS/GloFAS portals. |
| &nbsp;&nbsp;CEMS-Flood Development and Outreach | [255087732](https://confluence.ecmwf.int/spaces/CEMS/pages/255087732/CEMS-Flood+Development+and+Outreach) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Webinars | [261063660](https://confluence.ecmwf.int/spaces/CEMS/pages/261063660/CEMS-Flood+Webinars) | NOT | Webinar index. |
| &nbsp;&nbsp;CEMS-Flood general information | [333803125](https://confluence.ecmwf.int/spaces/CEMS/pages/333803125/CEMS-Flood+general+information) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood models and procedures | [333791586](https://confluence.ecmwf.int/spaces/CEMS/pages/333791586/CEMS-Flood+models+and+procedures) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood meteorological forcing and land surface data | [333791587](https://confluence.ecmwf.int/spaces/CEMS/pages/333791587/CEMS-Flood+meteorological+forcing+and+land+surface+data) | MAYBE | Historical forcing is used both to calibrate and to define thresholds. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood land surface data | [333791588](https://confluence.ecmwf.int/spaces/CEMS/pages/333791588/CEMS-Flood+land+surface+data) | NOT | Static maps overview. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood surface field dataset | [333803131](https://confluence.ecmwf.int/spaces/CEMS/pages/333803131/CEMS-Flood+surface+field+dataset) | MAYBE | CEMS_SurfaceFields_2022 1 arcmin Europe on JRC Data Catalogue. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Meteorological forcing | [333791603](https://confluence.ecmwf.int/spaces/CEMS/pages/333791603/CEMS-Flood+Meteorological+forcing) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood meteorological forcing - preparation | [340761244](https://confluence.ecmwf.int/spaces/CEMS/pages/340761244/CEMS-Flood+meteorological+forcing+-+preparation) | NOT | Forcing pre-processing. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood meteorological observation maps | [333791599](https://confluence.ecmwf.int/spaces/CEMS/pages/333791599/CEMS-Flood+meteorological+observation+maps) | NOT | Observation maps. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood hydrological forecasting chain | [333791604](https://confluence.ecmwf.int/spaces/CEMS/pages/333791604/CEMS-Flood+hydrological+forecasting+chain) | NOT | Chain overview. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood hydrological models | [333791606](https://confluence.ecmwf.int/spaces/CEMS/pages/333791606/CEMS-Flood+hydrological+models) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD* | [333803411](https://confluence.ecmwf.int/spaces/CEMS/pages/333803411/LISFLOOD) | NOT | LISFLOOD summary. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood LISFLOOD calibration parameters | [333791621](https://confluence.ecmwf.int/spaces/CEMS/pages/333791621/CEMS-Flood+LISFLOOD+calibration+parameters) | NOT | 14 calibrated parameters. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood LISFLOOD model setup | [333803476](https://confluence.ecmwf.int/spaces/CEMS/pages/333803476/CEMS-Flood+LISFLOOD+model+setup) | NOT | LISFLOOD processes (no dyke or floodplain-defence module). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;HTESSEL* - Until GloFAS version 2 | [333803409](https://confluence.ecmwf.int/spaces/CEMS/pages/333803409/HTESSEL+-+Until+GloFAS+version+2) | NOT | GloFAS legacy. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD - channel routing* - Until GloFAS version 2 | [333803410](https://confluence.ecmwf.int/spaces/CEMS/pages/333803410/LISFLOOD+-+channel+routing+-+Until+GloFAS+version+2) | NOT | GloFAS legacy. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood hydrological model calibration method | [333791619](https://confluence.ecmwf.int/spaces/CEMS/pages/333791619/CEMS-Flood+hydrological+model+calibration+method) | NOT | Calibration algorithm. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood medium to extended range forecasting | [333791663](https://confluence.ecmwf.int/spaces/CEMS/pages/333791663/CEMS-Flood+medium+to+extended+range+forecasting) | MAYBE | Thresholds come from the observation-forced long run, per grid cell. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood flood impact forecasting | [333791664](https://confluence.ecmwf.int/spaces/CEMS/pages/333791664/CEMS-Flood+flood+impact+forecasting) | USEFUL | Rapid flood mapping + impact method: unprotected vs protected scenarios, GHS-POP 2020 3 arcsec exposure, NUTS aggregation, limitations (levees not resolved at 90 m, no pluvial/coastal). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Post-processing | [333791666](https://confluence.ecmwf.int/spaces/CEMS/pages/333791666/CEMS-Flood+Post-processing) | NOT | Post-processing (MCP/EMOS) for stations. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood reforecasts | [348808608](https://confluence.ecmwf.int/spaces/CEMS/pages/348808608/CEMS-Flood+reforecasts) | NOT | Reforecast configuration. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood evaluation | [333791679](https://confluence.ecmwf.int/spaces/CEMS/pages/333791679/CEMS-Flood+evaluation) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood hydrological model performance | [333791680](https://confluence.ecmwf.int/spaces/CEMS/pages/333791680/CEMS-Flood+hydrological+model+performance) | MAYBE | KGE' definition; long-term run concept. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood medium-range forecast skill | [333791688](https://confluence.ecmwf.int/spaces/CEMS/pages/333791688/CEMS-Flood+medium-range+forecast+skill) | NOT | Forecast skill method. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood flash flood forecast skill | [333791692](https://confluence.ecmwf.int/spaces/CEMS/pages/333791692/CEMS-Flood+flash+flood+forecast+skill) | NOT | Flash-flood skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood seasonal forecast skill | [340758764](https://confluence.ecmwf.int/spaces/CEMS/pages/340758764/CEMS-Flood+seasonal+forecast+skill) | NOT | Seasonal skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood flood inundation maps | [340774762](https://confluence.ecmwf.int/spaces/CEMS/pages/340774762/CEMS-Flood+flood+inundation+maps) | USEFUL | The hazard-map method: Gumbel on reanalysis annual maxima, hydrograph, LISFLOOD-FP on MERIT 3 arcsec, rivers > 150 km2 (EFAS v5), RP1.5 bankfull subtracted, depth max mosaic. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood sub-seasonal and seasonal forecasting | [474819097](https://confluence.ecmwf.int/spaces/CEMS/pages/474819097/CEMS-Flood+sub-seasonal+and+seasonal+forecasting) | NOT | Sub-seasonal/seasonal design. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-flood sub-seasonal and seasonal basins and representative stations | [473851999](https://confluence.ecmwf.int/spaces/CEMS/pages/473851999/CEMS-flood+sub-seasonal+and+seasonal+basins+and+representative+stations) | NOT | Outlook basins. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-flood sub-seasonal and seasonal forecast anomaly and uncertainty computation methodology | [473842463](https://confluence.ecmwf.int/spaces/CEMS/pages/473842463/CEMS-flood+sub-seasonal+and+seasonal+forecast+anomaly+and+uncertainty+computation+methodology) | NOT | Anomaly method. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description of the real time forecasts, reforecasts and climatologies as components of the CEMS-flood sub-seasonal and seasonal forecasts | [483297828](https://confluence.ecmwf.int/spaces/CEMS/pages/483297828/Description+of+the+real+time+forecasts+reforecasts+and+climatologies+as+components+of+the+CEMS-flood+sub-seasonal+and+seasonal+forecasts) | NOT | Outlook components. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Sub-seasonal and seasonal forecast products | [474828722](https://confluence.ecmwf.int/spaces/CEMS/pages/474828722/Sub-seasonal+and+seasonal+forecast+products) | NOT | Outlook products. |
| &nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood web reporting points | [514313066](https://confluence.ecmwf.int/spaces/CEMS/pages/514313066/CEMS-Flood+web+reporting+points) | NOT | Reporting point categories. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood reporting points and dynamic point generation algorithm | [514313079](https://confluence.ecmwf.int/spaces/CEMS/pages/514313079/CEMS-Flood+reporting+points+and+dynamic+point+generation+algorithm) | MAYBE | Flood signal only where upstream > 50 km2 and RP1.5 > 1 m3/s. |
| &nbsp;&nbsp;CEMS-Flood User Guide Corner | [288346124](https://confluence.ecmwf.int/spaces/CEMS/pages/288346124/CEMS-Flood+User+Guide+Corner) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;Background on Copernicus Emergency Management Services - CEMS | [293700322](https://confluence.ecmwf.int/spaces/CEMS/pages/293700322/Background+on+Copernicus+Emergency+Management+Services+-+CEMS) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;The Copernicus Emergency Management Service (CEMS) | [293700324](https://confluence.ecmwf.int/spaces/CEMS/pages/293700324/The+Copernicus+Emergency+Management+Service+CEMS) | NOT | CEMS intro. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Floods at a glance | [293700326](https://confluence.ecmwf.int/spaces/CEMS/pages/293700326/CEMS-Floods+at+a+glance) | NOT | CEMS-Floods intro. |
| &nbsp;&nbsp;&nbsp;&nbsp;EFAS User Guide | [288346311](https://confluence.ecmwf.int/spaces/CEMS/pages/288346311/EFAS+User+Guide) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;1 EFAS user community | [293700328](https://confluence.ecmwf.int/spaces/CEMS/pages/293700328/1+EFAS+user+community) | MAYBE | Why real-time is partner-only: Member States' exclusive warning mandate (quotable). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;2 EFAS products overview | [293701137](https://confluence.ecmwf.int/spaces/CEMS/pages/293701137/2+EFAS+products+overview) | USEFUL | Real-time EFAS products restricted; public after a 30-day embargo. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3 EFAS-IS interface | [293701346](https://confluence.ecmwf.int/spaces/CEMS/pages/293701346/3+EFAS-IS+interface) | NOT | Interface. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.1 EFAS homepage | [293701348](https://confluence.ecmwf.int/spaces/CEMS/pages/293701348/3.1+EFAS+homepage) | NOT | Homepage. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2 EFAS Map Viewer | [293701352](https://confluence.ecmwf.int/spaces/CEMS/pages/293701352/3.2+EFAS+Map+Viewer) | NOT | Viewer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2.1 Functionalities explained | [293701355](https://confluence.ecmwf.int/spaces/CEMS/pages/293701355/3.2.1+Functionalities+explained) | NOT | Viewer functions. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2.2 Layer categories explained | [293701358](https://confluence.ecmwf.int/spaces/CEMS/pages/293701358/3.2.2+Layer+categories+explained) | USEFUL | Per-category access rule: Flood Summary layers (incl. RIA) partner-only in real time, public for dates older than the embargo. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2.3 Customizing your view | [621023076](https://confluence.ecmwf.int/spaces/CEMS/pages/621023076/3.2.3+Customizing+your+view) | NOT | Viewer settings. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2.4 Timeline for Animated layers | [639210183](https://confluence.ecmwf.int/spaces/CEMS/pages/639210183/3.2.4+Timeline+for+Animated+layers) | NOT | Animation timeline. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4 Hands-on guide for EFAS partners | [293701795](https://confluence.ecmwf.int/spaces/CEMS/pages/293701795/4+Hands-on+guide+for+EFAS+partners) | NOT | Partner guide. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.1 Overview of services provided to EFAS partners | [293701798](https://confluence.ecmwf.int/spaces/CEMS/pages/293701798/4.1+Overview+of+services+provided+to+EFAS+partners) | NOT | Partner services. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.1.1 Flood notification service | [293701800](https://confluence.ecmwf.int/spaces/CEMS/pages/293701800/4.1.1+Flood+notification+service) | NOT | Notifications. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.1.2 EFAS partner trainings | [293701802](https://confluence.ecmwf.int/spaces/CEMS/pages/293701802/4.1.2+EFAS+partner+trainings) | NOT | Trainings. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.1.3 EFAS annual meetings | [293701804](https://confluence.ecmwf.int/spaces/CEMS/pages/293701804/4.1.3+EFAS+annual+meetings) | NOT | Annual meetings. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.1.4 User support service | [293701806](https://confluence.ecmwf.int/spaces/CEMS/pages/293701806/4.1.4+User+support+service) | NOT | Support. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.2 EFAS notifications explained | [293701808](https://confluence.ecmwf.int/spaces/CEMS/pages/293701808/4.2+EFAS+notifications+explained) | NOT | Notifications. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.2.1 EFAS Formal Flood Notification | [293701810](https://confluence.ecmwf.int/spaces/CEMS/pages/293701810/4.2.1+EFAS+Formal+Flood+Notification) | MAYBE | Formal notification = >= 50 % total probability of the 5-year RP, 48 h - 7 d ahead (context for the 2021 story). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.2.2 EFAS Informal Flood Notification | [293701812](https://confluence.ecmwf.int/spaces/CEMS/pages/293701812/4.2.2+EFAS+Informal+Flood+Notification) | NOT | Informal notification. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.2.3 EFAS Flash Flood Notification | [293701814](https://confluence.ecmwf.int/spaces/CEMS/pages/293701814/4.2.3+EFAS+Flash+Flood+Notification) | NOT | Flash-flood notification. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.3 What to do when you receive an EFAS Notification? | [293701816](https://confluence.ecmwf.int/spaces/CEMS/pages/293701816/4.3+What+to+do+when+you+receive+an+EFAS+Notification) | NOT | Partner procedure. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.4 Pre-Tasking explained | [540563481](https://confluence.ecmwf.int/spaces/CEMS/pages/540563481/4.4+Pre-Tasking+explained) | NOT | Pre-tasking. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.4.1 EFAS conditions that trigger a Pre-Tasking | [540563532](https://confluence.ecmwf.int/spaces/CEMS/pages/540563532/4.4.1+EFAS+conditions+that+trigger+a+Pre-Tasking) | NOT | Pre-tasking criteria. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.4.2 EFAS Pre-Tasking emails | [540563542](https://confluence.ecmwf.int/spaces/CEMS/pages/540563542/4.4.2+EFAS+Pre-Tasking+emails) | NOT | Pre-tasking e-mails. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.5 What to do when you receive a Pre-Tasking email? | [540563519](https://confluence.ecmwf.int/spaces/CEMS/pages/540563519/4.5+What+to+do+when+you+receive+a+Pre-Tasking+email) | NOT | Pre-tasking steps. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.5.1 Summary of the key steps for EFAS partners | [540563553](https://confluence.ecmwf.int/spaces/CEMS/pages/540563553/4.5.1+Summary+of+the+key+steps+for+EFAS+partners) | NOT | Pre-tasking steps. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.6 How to provide feedback | [293701818](https://confluence.ecmwf.int/spaces/CEMS/pages/293701818/4.6+How+to+provide+feedback) | NOT | Feedback. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5 EFAS resources | [293701826](https://confluence.ecmwf.int/spaces/CEMS/pages/293701826/5+EFAS+resources) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5.1 How to stay up-to-date | [293701828](https://confluence.ecmwf.int/spaces/CEMS/pages/293701828/5.1+How+to+stay+up-to-date) | MAYBE | Links to bulletins/annual reports (already used for 2021). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5.2 Training material: webinars | [293701830](https://confluence.ecmwf.int/spaces/CEMS/pages/293701830/5.2+Training+material+webinars) | NOT | Webinars. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5.3 Archived data | [293701833](https://confluence.ecmwf.int/spaces/CEMS/pages/293701833/5.3+Archived+data) | NOT | Notification archive needs login. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;6 Contributing to EFAS | [293701839](https://confluence.ecmwf.int/spaces/CEMS/pages/293701839/6+Contributing+to+EFAS) | NOT | Data contribution. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;7 FAQ in EFAS | [293701841](https://confluence.ecmwf.int/spaces/CEMS/pages/293701841/7+FAQ+in+EFAS) | USEFUL | Thresholds = Gumbel on the modelled long run, 1992-2022 for EFAS v5. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;8 EFAS Glossary | [293701843](https://confluence.ecmwf.int/spaces/CEMS/pages/293701843/8+EFAS+Glossary) | NOT | Glossary. |
| &nbsp;&nbsp;&nbsp;&nbsp;GloFAS User Guide | [288346314](https://confluence.ecmwf.int/spaces/CEMS/pages/288346314/GloFAS+User+Guide) | NOT | GloFAS user guide navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;1 Introduction to the services | [315563794](https://confluence.ecmwf.int/spaces/CEMS/pages/315563794/1+Introduction+to+the+services) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;1.1 GloFAS and GFM at a glance | [315563805](https://confluence.ecmwf.int/spaces/CEMS/pages/315563805/1.1+GloFAS+and+GFM+at+a+glance) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;1.2 How to access the service | [315563811](https://confluence.ecmwf.int/spaces/CEMS/pages/315563811/1.2+How+to+access+the+service) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;2 GloFAS products (brief overview) | [315562957](https://confluence.ecmwf.int/spaces/CEMS/pages/315562957/2+GloFAS+products+brief+overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3 GloFAS interface (GloFAS-IS) | [315560388](https://confluence.ecmwf.int/spaces/CEMS/pages/315560388/3+GloFAS+interface+GloFAS-IS) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.1 GloFAS homepage | [315561239](https://confluence.ecmwf.int/spaces/CEMS/pages/315561239/3.1+GloFAS+homepage) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2 GloFAS Map Viewer | [315561244](https://confluence.ecmwf.int/spaces/CEMS/pages/315561244/3.2+GloFAS+Map+Viewer) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2.1 GloFAS Map Viewer - Functionalities explained | [315561273](https://confluence.ecmwf.int/spaces/CEMS/pages/315561273/3.2.1+GloFAS+Map+Viewer+-+Functionalities+explained) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2.2 GloFAS Map Viewer - Layer categories explained | [315561489](https://confluence.ecmwf.int/spaces/CEMS/pages/315561489/3.2.2+GloFAS+Map+Viewer+-+Layer+categories+explained) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;3.2.3 Getting started using GloFAS | [315561737](https://confluence.ecmwf.int/spaces/CEMS/pages/315561737/3.2.3+Getting+started+using+GloFAS) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4 GloFAS resources | [315561742](https://confluence.ecmwf.int/spaces/CEMS/pages/315561742/4+GloFAS+resources) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.1 How to stay up-to-date | [315561746](https://confluence.ecmwf.int/spaces/CEMS/pages/315561746/4.1+How+to+stay+up-to-date) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;4.2 CEMS Global Flood Forecasting and Monitoring meetings and webinars | [315561757](https://confluence.ecmwf.int/spaces/CEMS/pages/315561757/4.2+CEMS+Global+Flood+Forecasting+and+Monitoring+meetings+and+webinars) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5 Contributing to GloFAS | [315561767](https://confluence.ecmwf.int/spaces/CEMS/pages/315561767/5+Contributing+to+GloFAS) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5.1 Request a fixed reporting point | [315561769](https://confluence.ecmwf.int/spaces/CEMS/pages/315561769/5.1+Request+a+fixed+reporting+point) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5.2 Share in situ discharge data | [315561823](https://confluence.ecmwf.int/spaces/CEMS/pages/315561823/5.2+Share+in+situ+discharge+data) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5.3 Share a Case Study | [315561826](https://confluence.ecmwf.int/spaces/CEMS/pages/315561826/5.3+Share+a+Case+Study) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;5.4 Providing feedback | [315561833](https://confluence.ecmwf.int/spaces/CEMS/pages/315561833/5.4+Providing+feedback) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;6 FAQ in GloFAS | [315563119](https://confluence.ecmwf.int/spaces/CEMS/pages/315563119/6+FAQ+in+GloFAS) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;7 GloFAS Glossary | [315564094](https://confluence.ecmwf.int/spaces/CEMS/pages/315564094/7+GloFAS+Glossary) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Data User Guide | [242067350](https://confluence.ecmwf.int/spaces/CEMS/pages/242067350/CEMS-Flood+Data+User+Guide) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Terminology | [242067355](https://confluence.ecmwf.int/spaces/CEMS/pages/242067355/CEMS-Flood+Terminology) | NOT | Terminology (analysis, reanalysis, reference dataset). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Data Catalogue | [242067360](https://confluence.ecmwf.int/spaces/CEMS/pages/242067360/Data+Catalogue) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Model Output | [242067364](https://confluence.ecmwf.int/spaces/CEMS/pages/242067364/Model+Output) | USEFUL | efas-historical definition: 1 arcmin, 6-hourly, 1992-01-01 to NRT-6 d; dis06 = mean over the 6 h step; DOI 10.24381/cds.e3458969; not recommended < 50 km2, products use 150 km2. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Soil wetness index (root zone) | [435947605](https://confluence.ecmwf.int/spaces/CEMS/pages/435947605/Soil+wetness+index+root+zone) | NOT | Soil wetness index definition. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Web Layers | [242067378](https://confluence.ecmwf.int/spaces/CEMS/pages/242067378/Web+Layers) | MAYBE | WMS layer names (mapserver:FloodProtectionLevels, RapidImpactAssessment, RapidFloodMapping). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Auxiliary Data | [242067380](https://confluence.ecmwf.int/spaces/CEMS/pages/242067380/Auxiliary+Data) | USEFUL | EFAS v5.1 thresholds (Gumbel, L-moments, 9 RPs + mu/sigma); v5 grid metadata 4530x2970, 1/60 deg, WGS84; LDD v5 attachment; v5 upstream-area metadata 'TBD'. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Data Structure and Formats | [242067397](https://confluence.ecmwf.int/spaces/CEMS/pages/242067397/Data+Structure+and+Formats) | MAYBE | dis06 GRIB stepType=avg; its grid table is stale (EFAS v4 5 km only). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GRIB | [242067412](https://confluence.ecmwf.int/spaces/CEMS/pages/242067412/GRIB) | NOT | GRIB primer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Data Access | [242067416](https://confluence.ecmwf.int/spaces/CEMS/pages/242067416/Data+Access) | USEFUL | Real-time = EFAS partners only; archived data (forecasts > 30 days, historical, seasonal, reforecasts) open to all under the licence. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EWDS | [242067419](https://confluence.ecmwf.int/spaces/CEMS/pages/242067419/EWDS) | MAYBE | List of the 10 EWDS datasets and update times. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EWDS - How to Download | [242067437](https://confluence.ecmwf.int/spaces/CEMS/pages/242067437/EWDS+-+How+to+Download) | MAYBE | EWDS form; area cropping only for time-variant variables; ECMWF account needed to accept licences. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EWDS - Best Practices | [242067425](https://confluence.ecmwf.int/spaces/CEMS/pages/242067425/EWDS+-+Best+Practices) | USEFUL | EFAS historical on MARS = 817 GB in all; documented limit 1,000 fields/request (measured 1,500 - page stale); max 10 parallel requests; Wednesday MARS sessions slow queues. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EWDS API | [242067432](https://confluence.ecmwf.int/spaces/CEMS/pages/242067432/EWDS+API) | USEFUL | Official efas-historical request example (version_5_0, hyear/hmonth/hday, netcdf). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Changes to the EWDS API Request to download GloFAS Historical | [699325478](https://confluence.ecmwf.int/spaces/CEMS/pages/699325478/Changes+to+the+EWDS+API+Request+to+download+GloFAS+Historical) | MAYBE | GloFAS historical v5 renamed keys (year/month/day, timespan); EFAS keys not stated - check the live form. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;MARS | [242067439](https://confluence.ecmwf.int/spaces/CEMS/pages/242067439/MARS) | NOT | MARS needs an ECMWF archive account. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;MARS - Best Practices | [242067441](https://confluence.ecmwf.int/spaces/CEMS/pages/242067441/MARS+-+Best+Practices) | NOT | MARS tips (GloFAS grid alignment). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Structure of CEMS-Flood data in MARS | [278537793](https://confluence.ecmwf.int/spaces/CEMS/pages/278537793/Structure+of+CEMS-Flood+data+in+MARS) | MAYBE | MARS stream efcl / type sfo = the EFAS historical run. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;MARS Web | [242067462](https://confluence.ecmwf.int/spaces/CEMS/pages/242067462/MARS+Web) | NOT | MARS catalogue walkthrough (stale dates). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;MARS ecCodes and API | [242067464](https://confluence.ecmwf.int/spaces/CEMS/pages/242067464/MARS+ecCodes+and+API) | NOT | ecCodes tools. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;MARS - How to Download | [242067466](https://confluence.ecmwf.int/spaces/CEMS/pages/242067466/MARS+-+How+to+Download) | NOT | MARS download routes. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;FTP | [242067469](https://confluence.ecmwf.int/spaces/CEMS/pages/242067469/FTP) | MAYBE | Real-time FTP partner-only; GloFAS FTP carries RFM/RIA shapefiles (FloodMaskMerged, CostPopEst) - password on request. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Web Services | [242067472](https://confluence.ecmwf.int/spaces/CEMS/pages/242067472/Web+Services) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Sensor Observation Service (SOS) | [247897101](https://confluence.ecmwf.int/spaces/CEMS/pages/247897101/CEMS-Flood+Sensor+Observation+Service+SOS) | NOT | SOS for post-processed forecasts, partner credentials. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Web Map Service (WMS) - General Information | [247897113](https://confluence.ecmwf.int/spaces/CEMS/pages/247897113/CEMS-Flood+Web+Map+Service+WMS+-+General+Information) | USEFUL | EFAS WMS-T is open to non-authenticated users for a subset of layers and forecasts older than 30 days. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Accessing CEMS-Flood WMS via web browser | [247897119](https://confluence.ecmwf.int/spaces/CEMS/pages/247897119/Accessing+CEMS-Flood+WMS+via+web+browser) | USEFUL | Anonymous GetCapabilities URL; TIME syntax for archived layers. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Using QGIS for CEMS-Flood WMS-T | [247897142](https://confluence.ecmwf.int/spaces/CEMS/pages/247897142/Using+QGIS+for+CEMS-Flood+WMS-T) | NOT | QGIS how-to. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Using ESRI ArcMap for CEMS-Flood WMS-T | [247897148](https://confluence.ecmwf.int/spaces/CEMS/pages/247897148/Using+ESRI+ArcMap+for+CEMS-Flood+WMS-T) | NOT | ArcMap how-to. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Working with CEMS-Flood Data | [242067479](https://confluence.ecmwf.int/spaces/CEMS/pages/242067479/Working+with+CEMS-Flood+Data) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Open CEMS-Flood Data | [242067481](https://confluence.ecmwf.int/spaces/CEMS/pages/242067481/Open+CEMS-Flood+Data) | NOT | Opening GRIB/NetCDF with xarray. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GRIB to NetCDF conversion | [242067483](https://confluence.ecmwf.int/spaces/CEMS/pages/242067483/GRIB+to+NetCDF+conversion) | NOT | GRIB to NetCDF. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Visualising CEMS-Flood Data | [272332633](https://confluence.ecmwf.int/spaces/CEMS/pages/272332633/Visualising+CEMS-Flood+Data) | NOT | Viewer tools. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Extract subset of CEMS-Flood Data | [242067493](https://confluence.ecmwf.int/spaces/CEMS/pages/242067493/Extract+subset+of+CEMS-Flood+Data) | MAYBE | Says EFAS subsetting was removed - true only for v4 and older (Known Issues); v5 'area' works. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Plot CEMS-Flood Data | [242067485](https://confluence.ecmwf.int/spaces/CEMS/pages/242067485/Plot+CEMS-Flood+Data) | NOT | Plotting recipes. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Mapping locations onto CEMS-Flood river networks | [242067529](https://confluence.ecmwf.int/spaces/CEMS/pages/242067529/Mapping+locations+onto+CEMS-Flood+river+networks) | MAYBE | Protocol to snap a gauge to the model river network (upstream-area match). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;FAQs | [242067503](https://confluence.ecmwf.int/spaces/CEMS/pages/242067503/FAQs) | USEFUL | EFAS gives river flow, not extent; estimate ignores protection; Rapid Mapping pre-tasking 14 Jul (Rhine) and 15 Jul 2021 (Meuse); PESETA IV 170,000 people/yr EU+UK. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Request GloFAS web reporting points | [264536095](https://confluence.ecmwf.int/spaces/CEMS/pages/264536095/Request+GloFAS+web+reporting+points) | NOT | GloFAS reporting-point requests. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Share your data with GloFAS | [264536097](https://confluence.ecmwf.int/spaces/CEMS/pages/264536097/Share+your+data+with+GloFAS) | NOT | Share data with GloFAS. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CEMS-Flood Data Support | [250033886](https://confluence.ecmwf.int/spaces/CEMS/pages/250033886/CEMS-Flood+Data+Support) | NOT | Support portal how-to. |
| &nbsp;&nbsp;European Flood Awareness System | [265028037](https://confluence.ecmwf.int/spaces/CEMS/pages/265028037/European+Flood+Awareness+System) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;EFAS models and procedures | [265028039](https://confluence.ecmwf.int/spaces/CEMS/pages/265028039/EFAS+models+and+procedures) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS meterological forcing and land surface data | [265028040](https://confluence.ecmwf.int/spaces/CEMS/pages/265028040/EFAS+meterological+forcing+and+land+surface+data) | NOT | Forcing overview. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS land surface data | [265028041](https://confluence.ecmwf.int/spaces/CEMS/pages/265028041/EFAS+land+surface+data) | MAYBE | Static maps on JRC Data Catalogue; v4 LAEA 5 km extents. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Meteorological observation maps | [265028052](https://confluence.ecmwf.int/spaces/CEMS/pages/265028052/EFAS+Meteorological+observation+maps) | NOT | Observation maps. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 meteorological forcing | [333803146](https://confluence.ecmwf.int/spaces/CEMS/pages/333803146/EFAS+v5.0+meteorological+forcing) | USEFUL | Forcing = EMO-1 (1 arcmin, 6-hourly) from 1990; published on JRC FTP - an observed-rainfall source for July 2021. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 meteorological forcing | [265028053](https://confluence.ecmwf.int/spaces/CEMS/pages/265028053/EFAS+v4.0+meteorological+forcing) | NOT | v4 forcing. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Meteorological forecasts | [265028056](https://confluence.ecmwf.int/spaces/CEMS/pages/265028056/EFAS+Meteorological+forecasts) | NOT | NWP inputs. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS hydrological forecasting chain | [265028057](https://confluence.ecmwf.int/spaces/CEMS/pages/265028057/EFAS+hydrological+forecasting+chain) | NOT | Chain overview. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS hydrological model | [265028059](https://confluence.ecmwf.int/spaces/CEMS/pages/265028059/EFAS+hydrological+model) | NOT | LISFLOOD summary. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Flash Flood indicators | [265028082](https://confluence.ecmwf.int/spaces/CEMS/pages/265028082/EFAS+Flash+Flood+indicators) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ERIC flash flood forecasting | [265028083](https://confluence.ecmwf.int/spaces/CEMS/pages/265028083/ERIC+flash+flood+forecasting) | NOT | ERIC method (< 1,000 km2). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;TAMIR flash flood nowcasting | [402629494](https://confluence.ecmwf.int/spaces/CEMS/pages/402629494/TAMIR+flash+flood+nowcasting) | NOT | TAMIR nowcasting. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ERICHA flash flood nowcasting | [265028087](https://confluence.ecmwf.int/spaces/CEMS/pages/265028087/ERICHA+flash+flood+nowcasting) | NOT | ERICHA retired. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS medium-range forecasting | [265028096](https://confluence.ecmwf.int/spaces/CEMS/pages/265028096/EFAS+medium-range+forecasting) | MAYBE | Thresholds per grid cell from the observation-forced run. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS flood impact forecasting | [265028097](https://confluence.ecmwf.int/spaces/CEMS/pages/265028097/EFAS+flood+impact+forecasting) | MAYBE | Short version of the impact method. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Hydrological Post-processing | [265028099](https://confluence.ecmwf.int/spaces/CEMS/pages/265028099/EFAS+Hydrological+Post-processing) | NOT | Post-processing. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS sub-seasonal and seasonal forecasting | [265028103](https://confluence.ecmwf.int/spaces/CEMS/pages/265028103/EFAS+sub-seasonal+and+seasonal+forecasting) | NOT | Outlooks. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS evaluation | [265028105](https://confluence.ecmwf.int/spaces/CEMS/pages/265028105/EFAS+evaluation) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS hydrological model performance | [265028106](https://confluence.ecmwf.int/spaces/CEMS/pages/265028106/EFAS+hydrological+model+performance) | NOT | v4 performance method. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS medium-range forecast skill | [265028114](https://confluence.ecmwf.int/spaces/CEMS/pages/265028114/EFAS+medium-range+forecast+skill) | NOT | Forecast skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ERIC flash flood forecast skill | [265028118](https://confluence.ecmwf.int/spaces/CEMS/pages/265028118/ERIC+flash+flood+forecast+skill) | NOT | ERIC skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;EFAS operational system | [265028151](https://confluence.ecmwf.int/spaces/CEMS/pages/265028151/EFAS+operational+system) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS contributors | [265028152](https://confluence.ecmwf.int/spaces/CEMS/pages/265028152/EFAS+contributors) | NOT | Contributors. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS input data | [265028154](https://confluence.ecmwf.int/spaces/CEMS/pages/265028154/EFAS+input+data) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS meteorological forecasts model versions | [265028155](https://confluence.ecmwf.int/spaces/CEMS/pages/265028155/EFAS+meteorological+forecasts+model+versions) | NOT | NWP versions. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS static data | [265028158](https://confluence.ecmwf.int/spaces/CEMS/pages/265028158/EFAS+static+data) | NOT | Static data pointer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS versioning system | [265028159](https://confluence.ecmwf.int/spaces/CEMS/pages/265028159/EFAS+versioning+system) | USEFUL | Major vs minor releases: a minor release never changes model output; v5.1.0 = 2024-03-21; v4.2 was operational in July 2021. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.5 | [620418789](https://confluence.ecmwf.int/spaces/CEMS/pages/620418789/EFAS+v5.5) | MAYBE | v5.5: AIFS; ref. climatology 1992-2022. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.5 - Hydrological Post-Processing Evaluation | [567152808](https://confluence.ecmwf.int/spaces/CEMS/pages/567152808/EFAS+v5.5+-+Hydrological+Post-Processing+Evaluation) | NOT | Post-processing evaluation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.4 | [567156689](https://confluence.ecmwf.int/spaces/CEMS/pages/567156689/EFAS+v5.4) | MAYBE | v5.4 added the 'Flood inundation scenarios' static layer (RP10/50/100/500). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.3 | [505095942](https://confluence.ecmwf.int/spaces/CEMS/pages/505095942/EFAS+v5.3) | NOT | v5.3 post-processing, reporting points. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.3 - Hydrological Post-Processing Calibration Evaluation | [462907376](https://confluence.ecmwf.int/spaces/CEMS/pages/462907376/EFAS+v5.3+-+Hydrological+Post-Processing+Calibration+Evaluation) | NOT | Post-processing evaluation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.2 | [462906834](https://confluence.ecmwf.int/spaces/CEMS/pages/462906834/EFAS+v5.2) | USEFUL | v5.2 (13 Aug 2024): flood protection levels layer updated from doi:10.1038/s41558-022-01540-0 (PESETA IV / JRC). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.2 - Changes in notification criteria | [430702687](https://confluence.ecmwf.int/spaces/CEMS/pages/430702687/EFAS+v5.2+-+Changes+in+notification+criteria) | NOT | Notification criteria. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.1 | [435948254](https://confluence.ecmwf.int/spaces/CEMS/pages/435948254/EFAS+v5.1) | USEFUL | v5.1: thresholds published on the wiki with 'bug fixes to flood threshold calculation'; 'no impact on the EFAS modelling results'; ref. climatology 1992-2022. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.1 - Hydrological Post-Processing Calibration Evaluation | [435948257](https://confluence.ecmwf.int/spaces/CEMS/pages/435948257/EFAS+v5.1+-+Hydrological+Post-Processing+Calibration+Evaluation) | NOT | Post-processing evaluation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 | [388511564](https://confluence.ecmwf.int/spaces/CEMS/pages/388511564/EFAS+v5.0) | USEFUL | v5.0: 1 arcmin EPSG:4326, enlarged domain, thresholds on 1992-2022, new LISFLOOD-FP 90 m hazard maps from the v5.0 reference run. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Hydrological Model | [340784752](https://confluence.ecmwf.int/spaces/CEMS/pages/340784752/EFAS+v5.0+-+Hydrological+Model) | MAYBE | 6-hourly processes, hourly routing, LISFLOOD OS 4.1.3. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Calibration Data | [340784754](https://confluence.ecmwf.int/spaces/CEMS/pages/340784754/EFAS+v5.0+-+Calibration+Data) | USEFUL | Calibration window 1990-2021 (July 2021 is inside it). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Calibration Methodology and Data | [340784760](https://confluence.ecmwf.int/spaces/CEMS/pages/340784760/EFAS+v5.0+-+Calibration+Methodology+and+Data) | USEFUL | 1,903 stations >= 150 km2, 43.4 % of domain gauged, the rest regionalised. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Dynamic Reporting Points | [340784767](https://confluence.ecmwf.int/spaces/CEMS/pages/340784767/EFAS+v5.0+-+Dynamic+Reporting+Points) | NOT | Dynamic points. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Hydrological Model Performances | [340784732](https://confluence.ecmwf.int/spaces/CEMS/pages/340784732/EFAS+v5.0+-+Hydrological+Model+Performances) | USEFUL | Long run 1990-2021; median KGE' 0.694 - quotable model skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Flash Flood Skill Assessment | [355337616](https://confluence.ecmwf.int/spaces/CEMS/pages/355337616/EFAS+v5.0+-+Flash+Flood+Skill+Assessment) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Flash Flood Skill Assessment - Data | [347605249](https://confluence.ecmwf.int/spaces/CEMS/pages/347605249/EFAS+v5.0+-+Flash+Flood+Skill+Assessment+-+Data) | NOT | Flash-flood skill data. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Flash Flood Skill Assessment - Results | [340784798](https://confluence.ecmwf.int/spaces/CEMS/pages/340784798/EFAS+v5.0+-+Flash+Flood+Skill+Assessment+-+Results) | NOT | Flash-flood skill results. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v5.0 - Hydrological Post-Processing Calibration | [348807866](https://confluence.ecmwf.int/spaces/CEMS/pages/348807866/EFAS+v5.0+-+Hydrological+Post-Processing+Calibration) | NOT | Post-processing. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.8 | [340783473](https://confluence.ecmwf.int/spaces/CEMS/pages/340783473/EFAS+v4.8) | NOT | v4.8 NWP change. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.7 | [333795776](https://confluence.ecmwf.int/spaces/CEMS/pages/333795776/EFAS+v4.7) | NOT | v4.7 GFM display. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.6 | [311138753](https://confluence.ecmwf.int/spaces/CEMS/pages/311138753/EFAS+v4.6) | MAYBE | v4.6 (Oct 2022): RFM layer switched to the unprotected scenario; before, it showed the protected one. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.5 | [293723878](https://confluence.ecmwf.int/spaces/CEMS/pages/293723878/EFAS+v4.5) | NOT | v4.5. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.4 | [288346336](https://confluence.ecmwf.int/spaces/CEMS/pages/288346336/EFAS+v4.4) | NOT | v4.4. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.3 | [272332221](https://confluence.ecmwf.int/spaces/CEMS/pages/272332221/EFAS+v4.3) | NOT | v4.3. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.2 | [265028161](https://confluence.ecmwf.int/spaces/CEMS/pages/265028161/EFAS+v4.2) | MAYBE | v4.2 - the version running in July 2021. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.1 | [265028162](https://confluence.ecmwf.int/spaces/CEMS/pages/265028162/EFAS+v4.1) | NOT | v4.1. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.1 ERIC flash flood forecast skill | [265028163](https://confluence.ecmwf.int/spaces/CEMS/pages/265028163/EFAS+v4.1+ERIC+flash+flood+forecast+skill) | NOT | ERIC skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 | [265028202](https://confluence.ecmwf.int/spaces/CEMS/pages/265028202/EFAS+v4.0) | MAYBE | v4.0: 5 km LAEA, thresholds on 1991-2017 - what EFAS used in July 2021. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 hydrological modelling upgrade | [333791609](https://confluence.ecmwf.int/spaces/CEMS/pages/333791609/EFAS+v4.0+hydrological+modelling+upgrade) | NOT | v4 upgrade. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 calibration discharge data | [265028063](https://confluence.ecmwf.int/spaces/CEMS/pages/265028063/EFAS+v4.0+calibration+discharge+data) | NOT | v4 calibration data. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 calibration stations | [265028075](https://confluence.ecmwf.int/spaces/CEMS/pages/265028075/EFAS+v4.0+calibration+stations) | NOT | v4 stations. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 calibration implementation | [265028072](https://confluence.ecmwf.int/spaces/CEMS/pages/265028072/EFAS+v4.0+calibration+implementation) | NOT | v4 calibration. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 calibration parameters | [265028074](https://confluence.ecmwf.int/spaces/CEMS/pages/265028074/EFAS+v4.0+calibration+parameters) | NOT | v4 parameters. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 hydrological model performance | [265028209](https://confluence.ecmwf.int/spaces/CEMS/pages/265028209/EFAS+v4.0+hydrological+model+performance) | NOT | v4 performance. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 medium range forecast skill | [265028229](https://confluence.ecmwf.int/spaces/CEMS/pages/265028229/EFAS+v4.0+medium+range+forecast+skill) | NOT | v4 skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v4.0 ERIC flash flood forecast skill | [265028235](https://confluence.ecmwf.int/spaces/CEMS/pages/265028235/EFAS+v4.0+ERIC+flash+flood+forecast+skill) | NOT | v4 ERIC skill. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v3.5 | [265028265](https://confluence.ecmwf.int/spaces/CEMS/pages/265028265/EFAS+v3.5) | NOT | v3.5. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v3.0 | [265028272](https://confluence.ecmwf.int/spaces/CEMS/pages/265028272/EFAS+v3.0) | NOT | v3.0. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v2.0 | [265028274](https://confluence.ecmwf.int/spaces/CEMS/pages/265028274/EFAS+v2.0) | NOT | v2.0 (MARS archive starts; data > 30 days public). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS v1.0 | [265028276](https://confluence.ecmwf.int/spaces/CEMS/pages/265028276/EFAS+v1.0) | NOT | v1.0. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Latest operational EFAS release | [265028277](https://confluence.ecmwf.int/spaces/CEMS/pages/265028277/Latest+operational+EFAS+release) | USEFUL | Current v5.6: ref. climatology 1992-01-01 to 2022-12-31; 0.01667 deg EPSG:4326; 6-hourly. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS - Known Issues | [265028278](https://confluence.ecmwf.int/spaces/CEMS/pages/265028278/EFAS+-+Known+Issues) | USEFUL | Known issues: v5 historical from 2023-01-01 re-issued (May 2024); 6 h timestamp shift fixed Sept 2023; Poland Jul-Sep 2025; CDS NetCDF 19-21 Mar 2024; EFAS <= v4 subsetting broken. |
| &nbsp;&nbsp;&nbsp;&nbsp;EFAS products | [265028282](https://confluence.ecmwf.int/spaces/CEMS/pages/265028282/EFAS+products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Overall EFAS Products Summary | [265028317](https://confluence.ecmwf.int/spaces/CEMS/pages/265028317/Overall+EFAS+Products+Summary) | NOT | Products use the release's reference climatology. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Flood Summary Products Overview | [265028318](https://confluence.ecmwf.int/spaces/CEMS/pages/265028318/Flood+Summary+Products+Overview) | MAYBE | RFM/RIA layer descriptions; flood signal > 50 km2. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Hydrological Products Overview | [265028328](https://confluence.ecmwf.int/spaces/CEMS/pages/265028328/Hydrological+Products+Overview) | NOT | Hydrological layers. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Initial Conditions Products Overview | [265028338](https://confluence.ecmwf.int/spaces/CEMS/pages/265028338/Initial+Conditions+Products+Overview) | NOT | Initial conditions. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Flash Flood Products Overview | [265028359](https://confluence.ecmwf.int/spaces/CEMS/pages/265028359/Flash+Flood+Products+Overview) | NOT | Flash-flood layers. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Static Layers Overview | [265028366](https://confluence.ecmwf.int/spaces/CEMS/pages/265028366/Static+Layers+Overview) | USEFUL | 'Flood Protection Levels' static layer: design return period; Bianchi et al. 2022 (JRC) in the EU, FLOPROS outside; also 'Flood Inundation Scenarios'. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Evaluation Products Overview | [265028379](https://confluence.ecmwf.int/spaces/CEMS/pages/265028379/Evaluation+Products+Overview) | NOT | Evaluation layers. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Meteorological Products Overview | [265028386](https://confluence.ecmwf.int/spaces/CEMS/pages/265028386/Meteorological+Products+Overview) | NOT | Meteorological layers. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Notification Products Overview | [265028394](https://confluence.ecmwf.int/spaces/CEMS/pages/265028394/Notification+Products+Overview) | NOT | Notifications (registered only). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Global Flood Monitoring Products Overview | [288347684](https://confluence.ecmwf.int/spaces/CEMS/pages/288347684/EFAS+Global+Flood+Monitoring+Products+Overview) | NOT | GFM in EFAS (kit already has GFM-based depth). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Evaluation Products | [265028399](https://confluence.ecmwf.int/spaces/CEMS/pages/265028399/EFAS+Evaluation+Products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS hydrological model performance products | [265028401](https://confluence.ecmwf.int/spaces/CEMS/pages/265028401/EFAS+hydrological+model+performance+products) | NOT | Performance layer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS medium-range forecast skill product | [265028425](https://confluence.ecmwf.int/spaces/CEMS/pages/265028425/EFAS+medium-range+forecast+skill+product) | NOT | Skill layer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS flash flood forecast products | [265028437](https://confluence.ecmwf.int/spaces/CEMS/pages/265028437/EFAS+flash+flood+forecast+products) | NOT | Flash-flood products. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Flash Flood Notifications | [266579162](https://confluence.ecmwf.int/spaces/CEMS/pages/266579162/EFAS+Flash+Flood+Notifications) | NOT | Flash-flood notifications (regions = NUTS2/3 + GADM). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ERIC Affected Area | [265028440](https://confluence.ecmwf.int/spaces/CEMS/pages/265028440/ERIC+Affected+Area) | NOT | ERIC area. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ERIC reporting points | [265028455](https://confluence.ecmwf.int/spaces/CEMS/pages/265028455/ERIC+reporting+points) | NOT | ERIC points 150-1,000 km2. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based Flash Flood Products (experimental) | [439590056](https://confluence.ecmwf.int/spaces/CEMS/pages/439590056/Radar-based+Flash+Flood+Products+experimental) | NOT | Experimental radar products. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar Coverage | [505386222](https://confluence.ecmwf.int/spaces/CEMS/pages/505386222/Radar+Coverage) | NOT | Radar coverage. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based Rainfall Forecast Products | [488284447](https://confluence.ecmwf.int/spaces/CEMS/pages/488284447/Radar-based+Rainfall+Forecast+Products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based Accumulated Precipitation 80th Percentile | [488284495](https://confluence.ecmwf.int/spaces/CEMS/pages/488284495/Radar-based+Accumulated+Precipitation+80th+Percentile) | NOT | Radar precipitation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based Previous 24-h Accumulated Precipitation | [488284491](https://confluence.ecmwf.int/spaces/CEMS/pages/488284491/Radar-based+Previous+24-h+Accumulated+Precipitation) | NOT | Radar precipitation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based River Flash Flood Products | [439590094](https://confluence.ecmwf.int/spaces/CEMS/pages/439590094/Radar-based+River+Flash+Flood+Products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based River Flash Flood Impact | [488284466](https://confluence.ecmwf.int/spaces/CEMS/pages/488284466/Radar-based+River+Flash+Flood+Impact) | MAYBE | Flash-flood impact matrix with GHSL + HARCI-EU exposure (a pluvial/flash angle). |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based River Flash Flood Impact Catchment Summaries (0-120h) | [488284453](https://confluence.ecmwf.int/spaces/CEMS/pages/488284453/Radar-based+River+Flash+Flood+Impact+Catchment+Summaries+0-120h) | NOT | Catchment summaries. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Urban Flash Flood Forecast Products | [488284449](https://confluence.ecmwf.int/spaces/CEMS/pages/488284449/Urban+Flash+Flood+Forecast+Products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based Intense Precipitation Hazard Forecasts | [488284478](https://confluence.ecmwf.int/spaces/CEMS/pages/488284478/Radar-based+Intense+Precipitation+Hazard+Forecasts) | NOT | Radar hazard. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Radar-based Urban Flash Flood Hazard forecasts | [488284476](https://confluence.ecmwf.int/spaces/CEMS/pages/488284476/Radar-based+Urban+Flash+Flood+Hazard+forecasts) | NOT | Urban flash-flood hazard. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Project Background Information - Flash Flood Products | [505386216](https://confluence.ecmwf.int/spaces/CEMS/pages/505386216/Project+Background+Information+-+Flash+Flood+Products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EDERA Project Background | [439590090](https://confluence.ecmwf.int/spaces/CEMS/pages/439590090/EDERA+Project+Background) | NOT | EDERA project. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;TAMIR Project Background | [488286714](https://confluence.ecmwf.int/spaces/CEMS/pages/488286714/TAMIR+Project+Background) | NOT | TAMIR project. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Legacy Radar-based Flash Flood Products | [505386220](https://confluence.ecmwf.int/spaces/CEMS/pages/505386220/Legacy+Radar-based+Flash+Flood+Products) | NOT | Legacy. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS medium-range forecast products | [265028462](https://confluence.ecmwf.int/spaces/CEMS/pages/265028462/EFAS+medium-range+forecast+products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS 5-year exceedance probability | [265028467](https://confluence.ecmwf.int/spaces/CEMS/pages/265028467/EFAS+5-year+exceedance+probability) | NOT | 5-year exceedance layers. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Flood Probability | [272334663](https://confluence.ecmwf.int/spaces/CEMS/pages/272334663/EFAS+Flood+Probability) | NOT | Flood probability layer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Rapid Flood Mapping and Rapid Impact Assessment | [265028472](https://confluence.ecmwf.int/spaces/CEMS/pages/265028472/EFAS+Rapid+Flood+Mapping+and+Rapid+Impact+Assessment) | USEFUL | RIA table: population (GHSL), protection Bianchi 2022 (EU) / FLOPROS, roads OSM, CORINE 2012; grey = return period below protection. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Reporting Points | [265028485](https://confluence.ecmwf.int/spaces/CEMS/pages/265028485/EFAS+Reporting+Points) | NOT | Reporting points pop-up. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Threshold Level Exceedance | [265028495](https://confluence.ecmwf.int/spaces/CEMS/pages/265028495/EFAS+Threshold+Level+Exceedance) | NOT | Threshold exceedance layer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS sub-seasonal and seasonal forecast products | [293713233](https://confluence.ecmwf.int/spaces/CEMS/pages/293713233/EFAS+sub-seasonal+and+seasonal+forecast+products) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Seasonal outlook | [293713277](https://confluence.ecmwf.int/spaces/CEMS/pages/293713277/EFAS+Seasonal+outlook) | NOT | Seasonal outlook. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;EFAS Sub-seasonal outlook | [293713358](https://confluence.ecmwf.int/spaces/CEMS/pages/293713358/EFAS+Sub-seasonal+outlook) | NOT | Sub-seasonal outlook. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD model layers | [265028500](https://confluence.ecmwf.int/spaces/CEMS/pages/265028500/LISFLOOD+model+layers) | NOT | Navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD Drainage Network | [265028501](https://confluence.ecmwf.int/spaces/CEMS/pages/265028501/LISFLOOD+Drainage+Network) | NOT | Drainage network layer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD Fixed Reporting Points | [265028504](https://confluence.ecmwf.int/spaces/CEMS/pages/265028504/LISFLOOD+Fixed+Reporting+Points) | NOT | Fixed points layer. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD Reservoirs and Lakes | [265028507](https://confluence.ecmwf.int/spaces/CEMS/pages/265028507/LISFLOOD+Reservoirs+and+Lakes) | NOT | Reservoirs layer. |
| &nbsp;&nbsp;Global Flood Awareness System | [265028594](https://confluence.ecmwf.int/spaces/CEMS/pages/265028594/Global+Flood+Awareness+System) | NOT | GloFAS navigation. |
| &nbsp;&nbsp;&nbsp;&nbsp;GloFAS models and procedures | [265028595](https://confluence.ecmwf.int/spaces/CEMS/pages/265028595/GloFAS+models+and+procedures) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS meteorological forcings | [265028597](https://confluence.ecmwf.int/spaces/CEMS/pages/265028597/GloFAS+meteorological+forcings) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS meteorological forecasts | [265028598](https://confluence.ecmwf.int/spaces/CEMS/pages/265028598/GloFAS+meteorological+forecasts) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS hydrological models | [265028599](https://confluence.ecmwf.int/spaces/CEMS/pages/265028599/GloFAS+hydrological+models) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD - from GloFAS v3 | [265028602](https://confluence.ecmwf.int/spaces/CEMS/pages/265028602/LISFLOOD+-+from+GloFAS+v3) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;HTESSEL - until GloFAS v2 | [265028600](https://confluence.ecmwf.int/spaces/CEMS/pages/265028600/HTESSEL+-+until+GloFAS+v2) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LISFLOOD - channel routing - until GloFAS v2 | [265028601](https://confluence.ecmwf.int/spaces/CEMS/pages/265028601/LISFLOOD+-+channel+routing+-+until+GloFAS+v2) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS medium-range forecasting | [265028605](https://confluence.ecmwf.int/spaces/CEMS/pages/265028605/GloFAS+medium-range+forecasting) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS flood impact forecasting | [265028606](https://confluence.ecmwf.int/spaces/CEMS/pages/265028606/GloFAS+flood+impact+forecasting) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS sub-seasonal and seasonal forecasting | [462540470](https://confluence.ecmwf.int/spaces/CEMS/pages/462540470/GloFAS+sub-seasonal+and+seasonal+forecasting) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS evaluation | [265028608](https://confluence.ecmwf.int/spaces/CEMS/pages/265028608/GloFAS+evaluation) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS hydrological performance verification methodology | [265028609](https://confluence.ecmwf.int/spaces/CEMS/pages/265028609/GloFAS+hydrological+performance+verification+methodology) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS forecast skill | [265028616](https://confluence.ecmwf.int/spaces/CEMS/pages/265028616/GloFAS+forecast+skill) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS seasonal forecast skill | [265028618](https://confluence.ecmwf.int/spaces/CEMS/pages/265028618/GloFAS+seasonal+forecast+skill) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS web reporting points | [304219074](https://confluence.ecmwf.int/spaces/CEMS/pages/304219074/GloFAS+web+reporting+points) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;GloFAS operational system | [265028622](https://confluence.ecmwf.int/spaces/CEMS/pages/265028622/GloFAS+operational+system) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS contributors | [265028623](https://confluence.ecmwf.int/spaces/CEMS/pages/265028623/GloFAS+contributors) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS versioning system | [265028624](https://confluence.ecmwf.int/spaces/CEMS/pages/265028624/GloFAS+versioning+system) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4.4 | [650382085](https://confluence.ecmwf.int/spaces/CEMS/pages/650382085/GloFAS+v4.4) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4.3 | [560487704](https://confluence.ecmwf.int/spaces/CEMS/pages/560487704/GloFAS+v4.3) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4.2 | [528431688](https://confluence.ecmwf.int/spaces/CEMS/pages/528431688/GloFAS+v4.2) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4.1 | [473828729](https://confluence.ecmwf.int/spaces/CEMS/pages/473828729/GloFAS+v4.1) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4.0 | [388505179](https://confluence.ecmwf.int/spaces/CEMS/pages/388505179/GloFAS+v4.0) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 hydrological model | [340755422](https://confluence.ecmwf.int/spaces/CEMS/pages/340755422/GloFAS+v4+hydrological+model) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 calibration data | [340755424](https://confluence.ecmwf.int/spaces/CEMS/pages/340755424/GloFAS+v4+calibration+data) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 verification data | [340779445](https://confluence.ecmwf.int/spaces/CEMS/pages/340779445/GloFAS+v4+verification+data) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 calibration methodology and parameters | [340755426](https://confluence.ecmwf.int/spaces/CEMS/pages/340755426/GloFAS+v4+calibration+methodology+and+parameters) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 calibration hydrological model performance | [340755428](https://confluence.ecmwf.int/spaces/CEMS/pages/340755428/GloFAS+v4+calibration+hydrological+model+performance) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 dynamic points | [340774757](https://confluence.ecmwf.int/spaces/CEMS/pages/340774757/GloFAS+v4+dynamic+points) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 forecast skill | [450756955](https://confluence.ecmwf.int/spaces/CEMS/pages/450756955/GloFAS+v4+forecast+skill) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v4 general hydrological model performance | [340778958](https://confluence.ecmwf.int/spaces/CEMS/pages/340778958/GloFAS+v4+general+hydrological+model+performance) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.5 | [340762597](https://confluence.ecmwf.int/spaces/CEMS/pages/340762597/GloFAS+v3.5) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.4 | [333795738](https://confluence.ecmwf.int/spaces/CEMS/pages/333795738/GloFAS+v3.4) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.3 | [298945436](https://confluence.ecmwf.int/spaces/CEMS/pages/298945436/GloFAS+v3.3) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.2 | [293723918](https://confluence.ecmwf.int/spaces/CEMS/pages/293723918/GloFAS+v3.2) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.1 | [265028625](https://confluence.ecmwf.int/spaces/CEMS/pages/265028625/GloFAS+v3.1) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.1 hydrological performance | [265028627](https://confluence.ecmwf.int/spaces/CEMS/pages/265028627/GloFAS+v3.1+hydrological+performance) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.1 hydrological performance comparison with GloFAS v2.1 | [265028671](https://confluence.ecmwf.int/spaces/CEMS/pages/265028671/GloFAS+v3.1+hydrological+performance+comparison+with+GloFAS+v2.1) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.1 flood thresholds and comparison with GloFAS 2.1 | [265028721](https://confluence.ecmwf.int/spaces/CEMS/pages/265028721/GloFAS+v3.1+flood+thresholds+and+comparison+with+GloFAS+2.1) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v3.1 forecast skill | [265028734](https://confluence.ecmwf.int/spaces/CEMS/pages/265028734/GloFAS+v3.1+forecast+skill) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Seasonal v3.1 forecast skill | [265028742](https://confluence.ecmwf.int/spaces/CEMS/pages/265028742/GloFAS+Seasonal+v3.1+forecast+skill) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v2.2 | [265028745](https://confluence.ecmwf.int/spaces/CEMS/pages/265028745/GloFAS+v2.2) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v2.2 forecast skill | [265028747](https://confluence.ecmwf.int/spaces/CEMS/pages/265028747/GloFAS+v2.2+forecast+skill) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v2.1 | [265028752](https://confluence.ecmwf.int/spaces/CEMS/pages/265028752/GloFAS+v2.1) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v2.1 Hydrological reanalysis evaluation | [265028753](https://confluence.ecmwf.int/spaces/CEMS/pages/265028753/GloFAS+v2.1+Hydrological+reanalysis+evaluation) | NOT | GloFAS-ERA5 citation (Harrigan et al.); global. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v2.1 forecast skill | [265028775](https://confluence.ecmwf.int/spaces/CEMS/pages/265028775/GloFAS+v2.1+forecast+skill) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v2.1 and v2.0 flood threshold comparison | [265028785](https://confluence.ecmwf.int/spaces/CEMS/pages/265028785/GloFAS+v2.1+and+v2.0+flood+threshold+comparison) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v2.0 | [265028793](https://confluence.ecmwf.int/spaces/CEMS/pages/265028793/GloFAS+v2.0) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Calibration of Lisflood routing components | [265028794](https://confluence.ecmwf.int/spaces/CEMS/pages/265028794/Calibration+of+Lisflood+routing+components) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v1.0 | [265028795](https://confluence.ecmwf.int/spaces/CEMS/pages/265028795/GloFAS+v1.0) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Latest operational GloFAS release | [265028796](https://confluence.ecmwf.int/spaces/CEMS/pages/265028796/Latest+operational+GloFAS+release) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Upcoming GloFAS release (v5) | [554157279](https://confluence.ecmwf.int/spaces/CEMS/pages/554157279/Upcoming+GloFAS+release+v5) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v5 hydrological model | [673567675](https://confluence.ecmwf.int/spaces/CEMS/pages/673567675/GloFAS+v5+hydrological+model) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v5 calibration data | [673567677](https://confluence.ecmwf.int/spaces/CEMS/pages/673567677/GloFAS+v5+calibration+data) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v5 calibration methodology and parameters | [673567680](https://confluence.ecmwf.int/spaces/CEMS/pages/673567680/GloFAS+v5+calibration+methodology+and+parameters) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v5 calibration hydrological model performance | [673567683](https://confluence.ecmwf.int/spaces/CEMS/pages/673567683/GloFAS+v5+calibration+hydrological+model+performance) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS v5 reanalysis | [690294321](https://confluence.ecmwf.int/spaces/CEMS/pages/690294321/GloFAS+v5+reanalysis) | MAYBE | GloFAS v5 reanalysis 1980-2025, 0.05 deg; thresholds on annual maxima 1980-2025; reservoirs fixed at 2026 layout - a design choice to contrast with HERA's dynamic reservoirs. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS - Known Issues | [348807401](https://confluence.ecmwf.int/spaces/CEMS/pages/348807401/GloFAS+-+Known+Issues) | NOT | GloFAS known issues (longitude fix in subsets). |
| &nbsp;&nbsp;&nbsp;&nbsp;GloFAS products | [265028799](https://confluence.ecmwf.int/spaces/CEMS/pages/265028799/GloFAS+products) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Overall GloFAS products summary | [265028800](https://confluence.ecmwf.int/spaces/CEMS/pages/265028800/Overall+GloFAS+products+summary) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Initial Conditions Products Overview | [265028803](https://confluence.ecmwf.int/spaces/CEMS/pages/265028803/GloFAS+Initial+Conditions+Products+Overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Meteorological Products Overview | [265028824](https://confluence.ecmwf.int/spaces/CEMS/pages/265028824/GloFAS+Meteorological+Products+Overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Hydrological Products Overview | [265028831](https://confluence.ecmwf.int/spaces/CEMS/pages/265028831/GloFAS+Hydrological+Products+Overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Flood Risk Products Overview | [265028839](https://confluence.ecmwf.int/spaces/CEMS/pages/265028839/GloFAS+Flood+Risk+Products+Overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Evaluation Products Overview | [265028854](https://confluence.ecmwf.int/spaces/CEMS/pages/265028854/GloFAS+Evaluation+Products+Overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Static Layers Overview | [265028843](https://confluence.ecmwf.int/spaces/CEMS/pages/265028843/GloFAS+Static+Layers+Overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Global Flood Monitoring Products Overview | [272332281](https://confluence.ecmwf.int/spaces/CEMS/pages/272332281/GloFAS+Global+Flood+Monitoring+Products+Overview) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS evaluation products | [265028858](https://confluence.ecmwf.int/spaces/CEMS/pages/265028858/GloFAS+evaluation+products) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS hydrological model performance web product | [265028859](https://confluence.ecmwf.int/spaces/CEMS/pages/265028859/GloFAS+hydrological+model+performance+web+product) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS forecast skill product | [265028868](https://confluence.ecmwf.int/spaces/CEMS/pages/265028868/GloFAS+forecast+skill+product) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Seasonal forecast skill product | [265028874](https://confluence.ecmwf.int/spaces/CEMS/pages/265028874/GloFAS+Seasonal+forecast+skill+product) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS medium-range forecast products | [265028878](https://confluence.ecmwf.int/spaces/CEMS/pages/265028878/GloFAS+medium-range+forecast+products) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS AIFS Single | [560482933](https://confluence.ecmwf.int/spaces/CEMS/pages/560482933/GloFAS+AIFS+Single) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Flood Summary | [265028883](https://confluence.ecmwf.int/spaces/CEMS/pages/265028883/GloFAS+Flood+Summary) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Rapid Flood Mapping and Rapid Impact Assessment | [265028889](https://confluence.ecmwf.int/spaces/CEMS/pages/265028889/GloFAS+Rapid+Flood+Mapping+and+Rapid+Impact+Assessment) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Reporting Points | [265028905](https://confluence.ecmwf.int/spaces/CEMS/pages/265028905/GloFAS+Reporting+Points) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS threshold level exceedance probabilities | [265028918](https://confluence.ecmwf.int/spaces/CEMS/pages/265028918/GloFAS+threshold+level+exceedance+probabilities) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS sub-seasonal and seasonal forecast products | [514311861](https://confluence.ecmwf.int/spaces/CEMS/pages/514311861/GloFAS+sub-seasonal+and+seasonal+forecast+products) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS seasonal outlook | [514766419](https://confluence.ecmwf.int/spaces/CEMS/pages/514766419/GloFAS+seasonal+outlook) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS sub-seasonal outlook | [514766414](https://confluence.ecmwf.int/spaces/CEMS/pages/514766414/GloFAS+sub-seasonal+outlook) | NOT | GloFAS-only; nothing for Europe. |
| &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;GloFAS Social Media Activity Analysis (SMAA) | [272332258](https://confluence.ecmwf.int/spaces/CEMS/pages/272332258/GloFAS+Social+Media+Activity+Analysis+SMAA) | NOT | GloFAS-only; nothing for Europe. |
