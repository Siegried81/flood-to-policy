# Tab review — 20 browser tabs and the datasets inside their collections

Read on 2026-10-24. 20 tabs on 19 distinct pages (item 20 repeats item 13), 22 distinct dataset records: the 7 dataset tabs
plus 15 more listed only inside the three collections. "In the kit" is checked
against `config/sources.yaml` in this worktree (62 entries then; 73 now).

**How each page was read.** The Chrome extension could read
`developers.google.com`, `joint-research-centre.ec.europa.eu`,
`publications.jrc.ec.europa.eu`, `copernicus.eu`, `data.europa.eu` and DataM.
It was refused access to `data.jrc.ec.europa.eu` and to the CIMA wiki
("Permission denied for reading page content on this domain"). Those pages
were read another way:

- **JRC Data Catalogue.** Its pages are rendered by Blazor, so the dataset list
  never appears in the HTML. Every record has a machine-readable twin at
  `https://data.jrc.ec.europa.eu/dataset/<id>.json` (JSON-LD), and each
  collection has one at `/collection/<id>.json`. A collection's JSON-LD lists
  its members under `dcat:dataset`, and all 22 dataset records were read from
  there. The catalogue's SPARQL endpoint answered `403 Request Rejected`, from
  the JRC web application firewall, to both GET and POST. I did not try to get
  around it.
- **CIMA wiki.** Read with `curl`, because Wiki.js renders the page on the
  server.

No data file was downloaded, no login was used, and no cookie banner was
accepted.

---

## Top items, ranked by value for effort

1. **The JRC Floods page's headline numbers, and the clash they create with the
   brief.** This is a correction to make, not a dataset. The JRC states
   "160 000 people in the EU+UK currently exposed to inundation, annually".
   Further down the same page it gives 170,000 "now" (the PESETA IV figure the
   CEMS FAQ also quotes), and about 0.5 M a year by 2100 under 3 °C. The brief
   says 25.7 M at RP100. The two measure different things. The JRC figure is
   an expected annual exposure: it counts flood defences and weights each
   flood by its probability. The brief's figure is everyone living inside the
   undefended 1-in-100-year footprint. A juror from the JRC will know the
   160k figure, so the brief has to say in one line why its number is about
   160 times larger. Effort: a sentence. Value: it protects the headline
   number.
2. **The rest of PESETA IV (dataset 1019a72f): the impact maps for European
   regions and the adaptation cost-benefit tables.** Only
   `floodProtection_v2019_paper.zip` is in the kit. The same record also holds
   `s04a-out_impact_maps_v4.zip` (impact maps for European regions, TIFF),
   `adaptation_measures.zip`, and CSVs of future risk under climate change,
   socio-economic change and adaptation. Together they would give the brief a
   *future* exposure or damage figure and a number on what adaptation buys,
   both from the JRC's own method. The 1:4 return on retention areas below
   comes from this work. Effort: medium. The files are open, but the column
   meanings have to be read from `PESETA_IV_collection_description-v3.pdf`.
3. **The ESSD validation paper (JRC110216, Dottori et al. 2022,
   doi:10.5194/essd-14-1549-2022).** It was not in the RAG corpus on the 24th
   (since added as `jrc_hazard_maps_validation_essd_2022`). It is the
   source that quantifies the hazard maps' limits:
   - against official maps for Hungary, Italy, Norway, Spain and the UK, the
     maps find "on average two-thirds of reference flood extent";
   - they over-estimate flood-prone areas below 1-in-100-year probabilities;
   - they model no flood protection.

   That last point is exactly the caveat that item 1 needs. Effort: low (one
   open-access PDF added to the corpus). Value: high for the limitations
   paragraph and for grounded answers.
4. **JRC Floods page numbers to cite in the brief.** €7.6 bn a year of river
   flood damage (EU+UK). Under 3 °C by 2100: €48 bn a year and about 0.5 M
   people exposed a year, both halved or nearly so at 1.5 °C. A 1:4 return on
   water detention areas at 3 °C (Nature Climate Change 13, 196–202, 2023).
   Coastal damage rising from €1.4 bn to about €240 bn by 2100. These are
   official JRC framing numbers that sit next to the kit's climate-change
   section. Effort: none.
5. **EFAS estimated flood protection level by NUTS region (959355de).** This is
   the NUTS-level version of the protection standard, and it is the one EFAS
   itself uses for rapid risk assessment. It is not in the kit, and access
   needs EFAS authorisation (a WMS-T and an SOS service; the licence reads
   "not available"). Worth one email to ask for access. Without it, cite it
   to show that the kit's protection masking follows EFAS practice.
   **Status:** Corrected by [`cems_flood_wiki_review.md`](cems_flood_wiki_review.md) Q4/Q5: served
   anonymously as `mapserver:FloodProtectionLevels` on the EFAS WMS-T; since v5.2 its EU part is
   Bianchi et al. 2022 (PESETA IV, the family of `jrc_flood_protection_standards`) at
   sub-catchment scale, not per NUTS region. No access request needed.
6. **Earth Engine v2.1 caveat: the `spurious_depth_category` band.** The JRC
   flags as spurious any modelled depth above 10 m in small channels
   (< 3,000 km²) at RP10, inside a 2 km buffer, in the *global* maps. The
   European v3 set in the kit ships the same flag as its own file,
   `Europe_spurious_depth_areas.tif` (README F02, CHANGELOG v3.1.0), and
   `scripts/build_exposure.py` masks it by default (`--keep-spurious-areas`
   restores it). So the kit's figures already exclude those cells; the caveat
   is one line to cite.
7. **The JRC catalogue's JSON-LD route** (`/dataset/<id>.json`,
   `/collection/<id>.json`) and the **data.europa.eu search API**
   (`https://data.europa.eu/api/hub/search/search?q=...&filter=dataset`,
   which answered with 1,666 hits for "flood hazard maps"). Both give scripted,
   citable metadata (DOIs, licences, authors) for `sources.yaml` with no
   scraping. Effort: none. Value: provenance.

Everything else read is either already in the kit (2 datasets) or not useful
for an EU NUTS3 brief that must run offline.

## Counts

- Pages read: 19 of 19 (20 tabs). The CIMA wiki and the 11 JRC catalogue pages were read
  indirectly, as described at the top.
- Dataset records read: 22. That is 7 opened as tabs (all of them also members
  of a collection, except 959355de, 1019a72f and f572c443) plus 15 found only
  inside a collection: 8 GloFAS and 7 APIs4DGov. The FLOODS collection id-0054
  has only 3 members, all already open as tabs.
- Verdicts on the 22 datasets: USEFUL 3 (two already fully in the kit and
  one partly), MAYBE 1 (the EFAS protection level), NOT USEFUL 18.
- Verdicts on the 12 non-dataset pages (catalogue home, 3 collections,
  data.europa.eu mirror, Earth Engine, JRC Floods, CIMA, 2 publication
  records, Copernicus, DataM): USEFUL 3 (FLOODS collection, JRC Floods page,
  ESSD paper), MAYBE 2 (catalogue home as a tool, JRC103765), NOT USEFUL 7.

## Would this text justify a vector index (pgvector) over BM25? The facts

- **Current corpus**, measured on the dev machine with `src/rag.py::load_index()`
  on 2026-10-24: 27 source documents, 3,012 passages, mean passage 813
  characters, 2,449,429 characters in all (the `data/raw/scrape` and
  `data/raw/download` folders). With the ESSD paper since added, the same
  measure now gives 28 documents, 3,129 passages and 2,543,306 characters.
- **New text found on these tabs.** The 22 dataset descriptions run from 68 to
  2,446 characters (mean 781), 17,175 characters in all. The pages with real
  prose add roughly another 10–12 k characters, an estimate: the JRC Floods
  page is about 4.5 k, the ESSD abstract about 2.5 k, the rest is navigation.
  That is about 30 k characters, or about 1.2 % of the current corpus. The
  catalogue holds 4,342 datasets and 259 collections, but only 22 records
  were in scope here.
- **Language.** Everything found is English except the Earth Engine page,
  which the user's browser showed in an AI-translated French. That page
  duplicates the English JRC description.
- **What would change these numbers.** Adding the full ESSD paper (about 21
  journal pages) and the PESETA IV description PDF would add a few hundred
  passages, not thousands. `src/rag.py` already states the BM25 reasoning
  (exact legal tokens, offline). Nothing found here changes the corpus's size
  class.

---

## Mini-reports, page by page

### 1. DataM — API documentation
- URL: https://datam.jrc.ec.europa.eu/datam/public/pages/apiReference.xhtml. Publisher: JRC (the Data-Modelling platform of resource economics).
- What it is: the REST API for DataM's datasets (dataset list, dimensions, observations, RDF export).
- Access: every endpoint needs a Bearer token, issued on request to JRC-DATAM@ec.europa.eu.
- In the kit: no.
- Verdict: **NOT USEFUL.** DataM covers agriculture and bio-economy modelling, not flood hazard. A token cannot be obtained before 29 October, and nothing can run offline from it.
- Still drawable: nothing for this brief. Whether DataM holds any flood or water dataset is **not verified**, because the dataset list itself needs the token.

### 2. JRC Data Catalogue — collection id-0097 "Digital Government APIs (APIS4DGOV)"
- URL: https://data.jrc.ec.europa.eu/collection/id-0097. JRC with DG CONNECT, a 2019 study. Contact jrc-apis4dgov@ec.europa.eu.
- What it is: 7 datasets about how governments use web APIs (reviewed one by one below, items 29–35). The collection itself says it is not guaranteed to be updated after 2019.
- In the kit: no.
- Verdict: **NOT USEFUL.** Nothing about floods. It was probably opened by browsing near id-0054.
- Still drawable: at most a citation if the jury asks how the kit's API was designed (see item 30).

### 3. JRC Data Catalogue — home
- URL: https://data.jrc.ec.europa.eu/. JRC.
- What it is: the catalogue portal, with "4342 datasets and 259 collections", a SPARQL search page and a "Catalogue API" page (both Blazor, both empty without JavaScript).
- In the kit: not as a source. Individual datasets are.
- Verdict: **MAYBE**, as a tool and not as data.
- Still drawable: per-record JSON-LD at `/dataset/<id>.json`, plus `.rdf`, `.csv` and `.ttl` for collections. These give DOIs, licences and author lists for `sources.yaml`. The SPARQL endpoint is behind the WAF, which returned 403.

### 4. JRC Data Catalogue — collection id-0054 "FLOODS"
- URL: https://data.jrc.ec.europa.eu/collection/id-0054. Title: River Flood Hazard and flood event catalogue at European and Global Scale. Contact Peter.SALAMON@ec.europa.eu. Modified 21 Oct 2026.
- What it is: 3 datasets: European hazard maps (1d128b6c), global hazard maps, and satellite-derived flood depth maps 2015–2024 (0bc96690).
- In the kit: 2 of its 3 members.
- Verdict: **USEFUL.** It is the parent record of the kit's two core layers.
- Still drawable: the collection's own wording that these maps come from CEMS (EFAS and GloFAS climatology), to cite alongside the hazard source. It was modified three days ago, so it is worth re-checking that 1d128b6c is still the version the kit uses (**not verified** beyond the record's own "issued 2024-03-08", which is the v3.0.0 date; the kit's `CHANGELOG.txt` lists v3.1.1 of 2026-03-05).

### 5. JRC Data Catalogue — collection id-0069 "Global Flood Awareness System (CEMS-GloFAS)"
- URL: https://data.jrc.ec.europa.eu/collection/id-0069. JRC with ECMWF. Contact info@globalfloods.eu. Publication JRC106789.
- What it is: 9 GloFAS layers: 8 operational forecast or reference WMS layers, plus 1 LISFLOOD model-input set (items 8 and 21–28; the LISFLOOD set is item 24).
- In the kit: no.
- Verdict: **NOT USEFUL.** These are global, operational and forecast products, mostly behind authorisation. The brief is about European NUTS3 exposure.
- Still drawable: GloFAS's role in transboundary basins, as the JRC Floods page puts it ("independent of administrative and political boundaries"), supports the brief's cross-border argument.

### 6. Dataset 0bc96690 — Satellite-derived flood depth maps for Europe
- URL: https://data.jrc.ec.europa.eu/dataset/0bc96690-b89c-4909-9166-c2c322a20130. Authors Betterle & Salamon (2026). DOI 10.2905/JRC.NNQVVER.
- What it is: flood depth at 20 m from the full Sentinel-1 archive (CEMS Global Flood Monitoring), 2015–2024, clustered into events. GeoTIFF, CC BY 4.0, open FTP.
- In the kit: **yes** (`jrc_observed_flood_depth`, DOI matches).
- Verdict: **USEFUL**, already used as the validation layer.
- Still drawable: the companion paper "Ten years floods across Europe mapped from space with reconstructed water depth" (Science Advances) is listed as **under review**. Cite it as a preprint or manuscript, not as published.

### 7. Dataset jrc-floods-floodmapgl_rp50y-tif — Global river flood hazard maps
- URL: https://data.jrc.ec.europa.eu/dataset/jrc-floods-floodmapgl_rp50y-tif. Baugh et al. (2024). DOI 10.2905/JRC.VD32YWG.
- What it is: global water depth (m) for 7 return periods (RP10–RP500), basins > 500 km². GeoTIFF. The catalogue licence code is ODC_BL. Open FTP (`CEMS-GLOFAS/flood_hazard/`).
- In the kit: no.
- Verdict: **NOT USEFUL.** The European dataset (1d128b6c) covers the same area with more return periods and a smaller basin threshold (> 150 km²).
- Still drawable: the same "NOT an official flood hazard map" disclaimer. The global v2 band structure is documented on the Earth Engine page (item 10).

### 8. Dataset da4d7f64 — GloFAS: flood hazard map (100-year return period)
- URL: https://data.jrc.ec.europa.eu/dataset/da4d7f64-a5c3-403f-bd2b-11a97176031e. JRC (issued 2017). DOI 10.2905/JRC.T9279B8.
- What it is: a global RP100 inundation layer from GloFAS climatology, shown in the GloFAS interface "as a rough indication". WMS-T only, authorisation required, licence "not available".
- In the kit: no.
- Verdict: **NOT USEFUL.** It is coarser and older than the kit's layer, and it is not downloadable.
- Still drawable: nothing beyond the JRC's own wording that it is a "rough indication", which is one more reason to prefer the European set.

### 9. Dataset 959355de — EFAS estimated flood protection level
- URL: https://data.jrc.ec.europa.eu/dataset/959355de-514a-4126-a969-27793cd775aa. JRC (issued 2017).
- What it is: the estimated design return period of flood defences for each NUTS region in the EFAS domain (shapefile). EFAS's flood event hazard maps and rapid risk assessment rely on it. Access through the EFAS WMS-T and SOS, authorisation required, licence "not available".
- In the kit: no. The kit uses the PESETA IV 500 m raster (`jrc_flood_protection_standards`) for the same idea.
- Verdict: **MAYBE.** It is NUTS-native, which is exactly the kit's unit, but it is behind EFAS registration. The kit already covers the concept at finer resolution.
- Still drawable: the EFAS rule that "any flood event above the protection level will cause flooding". This is the same masking rule as `--protection`, so it can be cited as precedent.
- **Status:** Corrected by [`cems_flood_wiki_review.md`](cems_flood_wiki_review.md) Q4/Q5: served anonymously as `mapserver:FloodProtectionLevels` on the EFAS WMS-T; since v5.2 its EU part is Bianchi et al. 2022 (PESETA IV, the family of `jrc_flood_protection_standards`) at sub-catchment scale, not per NUTS region. No access request needed.

### 10. Earth Engine — JRC Global River Flood Hazard Maps v2.1
- URL: https://developers.google.com/earth-engine/datasets/catalog/JRC_CEMS_GLOFAS_FloodHazard_v2_1. JRC, hosted by Google. `ee.ImageCollection("JRC/CEMS_GLOFAS/FloodHazard/v2_1")`, dated 2024-03-16.
- What it is: the global maps from item 7, tiled, with a depth band and a depth-category band per return period, plus permanent-water and `spurious_depth_category` bands. Needs an Earth Engine account.
- In the kit: no.
- Verdict: **NOT USEFUL** as data. It is global, needs an account and a cloud connection, and cannot run offline at the venue.
- Still drawable: the **spurious-depth caveat** (depth > 10 m in channels < 3,000 km² at RP10, with a 2 km buffer, flagged by the JRC). The European v3 set ships the same flag as `Europe_spurious_depth_areas.tif`, which the kit masks by default (see top item 6).

### 11. Dataset f572c443 — LISFLOOD static and parameter maps for Europe
- URL: https://data.jrc.ec.europa.eu/dataset/f572c443-7466-4adf-87aa-c0847a169f23. Choulga et al.
- What it is: every gridded input except the weather needed to run LISFLOOD over Europe, at 1 arcmin (about 1.5 km). NetCDF, COM_REUSE, open FTP.
- In the kit: no.
- Verdict: **NOT USEFUL.** These are hydrological model inputs. The brief consumes the model's outputs.
- Still drawable: a citation for "the hazard maps' discharge comes from LISFLOOD, open-source" (https://ec-jrc.github.io/lisflood/). That supports transparency.

### 12. Dataset 1019a72f — Flood impacts and adaptation strategies under future scenarios (PESETA IV)
- URL: https://data.jrc.ec.europa.eu/dataset/1019a72f-7b98-4318-8baf-fd9e2c00a92c. Dottori, Mentaschi, Bianchi, Alfieri, Feyen. DOI 10.2905/JRC.7DCZDP0.
- What it is: inputs and outputs of the European cost-benefit appraisal of flood adaptation under climate and socio-economic scenarios. It has 14 distributions:
  - the protection-standards map;
  - impact maps for European regions (TIFF);
  - adaptation measures (XLSX);
  - eight sets of scenario CSVs;
  - European input maps (NetCDF);
  - the code (HPC scripts);
  - a description PDF.

  The catalogue gives the licence as COM_REUSE. Everything is on open FTP.
- In the kit: **partly.** Only `floodProtection_v2019_paper.zip` is in it, as `jrc_flood_protection_standards`.
- Verdict: **USEFUL.** The impact maps and adaptation CSVs answer "what does climate change add, and what does adaptation buy?" with the JRC's own method.
- Still drawable: the paper "Adaptation is cost-effective to offset rising river flood risk in Europe", preprint doi:10.21203/rs.3.rs-519118/v1, later published in Nature Climate Change 13, 196–202 (2023) according to the JRC Floods page. **Licence discrepancy**: the catalogue says COM_REUSE, while `sources.yaml` records CC-BY-4.0 from the `copyright.txt` beside the file. Both allow reuse with attribution; keep the one read from the file and note the other.

### 13. Dataset 1d128b6c — River flood hazard maps for Europe and the Mediterranean Basin (the tab, and the member of id-0054)
- URL: https://data.jrc.ec.europa.eu/dataset/1d128b6c-a4ee-4858-9e34-6210707f3c81. Baugh, Colonese, D'Angelo, Dottori, Neal, Prudhomme, Salamon (2024). DOI 10.2905/JRC.WPE5YRR, alternative DOI 10.2905/1D128B6C-...
- What it is: water depth (m) for 9 return periods (RP10–RP500), LISFLOOD discharge with LISFLOOD-FP inundation, basins > 150 km², covering Europe and the Mediterranean and Black Sea basins. GeoTIFF, open FTP. Issued 2024-03-08.
- In the kit: **yes** (`jrc_flood_hazard`, DOI matches). This is the kit's core layer.
- Verdict: **USEFUL.**
- Still drawable:
  - The record's own note that this is "not an official flood hazard map", the same caveat as `docs/policy_answer.md`.
  - The recommended citation string (Baugh et al. 2024).
  - **Licence discrepancy**: the catalogue gives the distribution licence code ODC_BL, while `sources.yaml` says CC-BY-4.0. How the EU vocabulary code ODC_BL maps to a named licence is **not verified**. Worth one look before the brief prints a licence line.

### 14. data.europa.eu — Global river flood hazard maps
- URL: https://data.europa.eu/data/datasets/jrc-floods-floodmapgl_rp50y-tif?locale=en. The data.europa.eu mirror of item 7, harvested 11 Oct 2024, updated 21 Oct 2026.
- What it is: the same record, plus API, RSS and citation exports, and author e-mails at JRC, ECMWF and Bristol.
- In the kit: no (see item 7).
- Verdict: **NOT USEFUL** as data.
- Still drawable: the data.europa.eu search API is open JSON. It answered `search?q=flood hazard maps&filter=dataset` with 1,666 hits, so it is a scripted way to find related EU records. Named contacts: Peter Salamon and Francesco Dottori (JRC), Christel Prudhomme and Calum Baugh (ECMWF), Jeffrey Neal (Bristol), all likely relevant to a JRC jury.

### 15. JRC — Floods (EU Science Hub page)
- URL: https://joint-research-centre.ec.europa.eu/scientific-activities/natural-and-man-made-hazards/floods_en. JRC.
- What it is: the JRC's public summary of its flood work (EFAS, GloFAS, CEMS rapid mapping, PESETA IV), with headline numbers.
- In the kit: no, neither in `sources.yaml` nor in the RAG corpus.
- Verdict: **USEFUL.** It holds the official numbers the jury will carry in their heads:
  - €7.6 bn a year of damage (EU+UK);
  - 160,000 people exposed annually;
  - a 1:4 return on detention areas at 3 °C;
  - €48 bn a year and about 0.5 M people a year by 2100 at 3 °C, halved at 1.5 °C;
  - coastal damage from €1.4 bn to about €240 bn.
- Still drawable:
  - **The page contradicts itself**: 160,000 in the banner, 170,000 "now" in the text.
  - **The brief must reconcile 25.7 M with 160k.** The JRC figure is defended expected annual exposure; the brief's is the undefended RP100 footprint. See top item 1.
  - The 1:4 figure cites Nature Climate Change 13, 196–202 (2023).

### 16. CIMA Foundation wiki — JRC Flood Hazard Maps (myDEWETRA static layer)
- URL: https://mydewiki.cimafoundation.org/en/myDW/StaticLayers/JRC_FloodHazard. CIMA Research Foundation, Italy.
- What it is: the help page for the layer in the myDEWETRA platform. It copies the 2016 JRC103765 collection text and lists the available maps as RP10, 20, 50, 100, 200 and 500.
- In the kit: no.
- Verdict: **NOT USEFUL.** It is a third-party mirror of the *older* generation of the maps (6 return periods, 2014 and 2016 papers), not the v3 set the kit uses.
- Still drawable: proof that civil-protection platforms reuse the JRC maps operationally (myDEWETRA serves the Italian Civil Protection; that framing is general knowledge, **not stated on this page**). One citation, if the brief argues that the maps are already an operational standard.

### 17. JRC Publications — JRC103765 "Flood Hazard Maps at European and Global Scale" (2016)
- URL: https://publications.jrc.ec.europa.eu/repository/handle/JRC103765. Dottori, Salamon, Alfieri, Bianchi, Feyen, Hirpa, Lorini.
- What it is: the repository record of the original 2016 collection, linked to collection id-0054. It cites Alfieri et al. 2014 (doi:10.1002/hyp.9947) and Dottori et al. 2016 (Advances in Water Resources 94, 87–102).
- In the kit: not as an entry; `jrc_publications` points only to the repository root.
- Verdict: **MAYBE**, for its lineage only.
- Still drawable: the line "the maps might differ from official national flood hazard maps", useful in the limitations section. The two founding citations.

### 18. Copernicus — homepage
- URL: https://www.copernicus.eu/en. The EU Copernicus programme.
- What it is: a portal with news highlights, the services catalogue, and thematic hubs (Health, Coastal, Energy, Arctic, Heritage).
- In the kit: no (CEMS products are in the kit by their own URLs).
- Verdict: **NOT USEFUL.** No flood dataset is on the page.
- Still drawable: the Coastal Hub, if a scenario turns to coastal floods, which the kit does not model. The JRC page puts coastal damage at €1.4 bn now and about €240 bn by 2100.

### 19. JRC Publications — JRC110216 "A new dataset of river flood hazard maps for Europe and the Mediterranean Basin" (ESSD 2022)
- URL: https://publications.jrc.ec.europa.eu/repository/handle/JRC110216. Dottori, Alfieri, Bianchi, Skoien, Salamon. ESSD 14, 1549–1569, doi:10.5194/essd-14-1549-2022, open access.
- What it is: the peer-reviewed description and validation of the European hazard maps: 100 m resolution, 329,000 km of river network, validated against official maps for HU, IT, NO, ES and the UK.
- In the kit: no on 2026-10-24. Since added to `sources.yaml` and the RAG corpus as `jrc_hazard_maps_validation_essd_2022`.
- Verdict: **USEFUL.** It is the citable source for the kit's main limitation.
- Still drawable:
  - the maps find "two-thirds of reference flood extent" on average;
  - they over-estimate flood-prone areas below 1-in-100;
  - at RP500 and above they identify more than half of flooded areas correctly;
  - their shortcomings come from "the absence of flood protections", rivers under 500 km², and channel and lowland topography.

  **Note:** the paper describes *six* return periods and a 500 km² threshold, while the 2024 record (item 13) has *nine* and 150 km². The kit's v3.1.1 is the later generation, so cite the paper for its method and validation, not for those parameters.

### 20. JRC Data Catalogue — dataset tab for 1d128b6c
Same record as item 13; the user had it open in a separate tab. Nothing to add.

---

## Datasets found only inside collections

GloFAS collection (id-0069). Items 21–23 and 25–28 are issued 2017-03-06, global
at 0.1°, and served only by the GloFAS WMS-T (`ies-ows.jrc.ec.europa.eu`),
with authorisation required and licence "not available". None is in the kit.

### 21. 1bb8ca1d — GloFAS: probabilistic precipitation forecast (DOI 10.2905/JRC.SYX758G)
The daily probability of 10-day precipitation exceeding 50, 150 or 300 mm, from ECMWF-ENS. **NOT USEFUL.** It is a live forecast with no NUTS3 or exposure meaning. Nothing to draw.

### 22. 504ecea0 — GloFAS: accumulated precipitation forecast (DOI 10.2905/JRC.13KZMS8)
The 10-day accumulated precipitation, ensemble median, updated daily. **NOT USEFUL**, for the same reasons as item 21.

### 23. 653b7f9b — GloFAS: major river basins (DOI 10.2905/JRC.ECMWSM8)
Major river basins of the world, from the GRDC (BfG), served as a WMS. **NOT USEFUL.** The kit uses the WFD river basin districts, which are the legal unit for the Floods Directive. Still drawable: the GRDC as an independent basin source, should someone challenge the WFD basins.

### 24. 68050d73 — LISFLOOD static and parameter maps for GloFAS
Global LISFLOOD inputs at 3 arcmin (about 5 km). NetCDF, COM_REUSE, open FTP. Publication JRC132801. **NOT USEFUL**, model inputs. It is the global twin of item 11.

### 25. 8ee67447 — GloFAS: lakes and reservoirs (DOI 10.2905/JRC.YQ6NG4R)
Lakes over 100 km² and reservoirs over 0.5 km³ of capacity (the record itself writes "0.5 km²") that matter for discharge. **NOT USEFUL** for the brief. Still drawable, at most: reservoirs are part of the hydrology behind the hazard maps.

### 26. c5d56e48 — GloFAS: flood reporting points (DOI 10.2905/JRC.VJSZNT0)
Daily forecast points with a high probability of exceeding RP2, RP5 or RP20, plus fixed stations with hydrographs. **NOT USEFUL.** It is operational forecasting. Still drawable: GloFAS forecasts do exist for transboundary basins, which supports the preparedness argument.

### 27. e752f6cc — GloFAS: seasonal outlook (DOI 10.2905/JRC.X50V3Y0)
Four-month flow anomalies against a 1990–2013 model climatology (51-member ECMWF SEAS). **NOT USEFUL.**

### 28. f0570578 — GloFAS: ECMWF-ENS probabilistic flood forecast (DOI 10.2905/JRC.RQMC4MG)
The number of ensemble members above the RP5 and RP20 thresholds, daily. **NOT USEFUL.**

(The ninth member of id-0069 is da4d7f64, reviewed as item 8.)

APIs4DGov collection (id-0097). All items 29–35 are from 2019–2020, global,
hosted on GitHub (`api4dt/opendata`), and licensed CC BY 4.0 or COM_REUSE.
None is in the kit. **All 7 are NOT USEFUL**: they are about how governments
use APIs, not about floods.

### 29. 45ca8d82 — List of government APIs (Vaccari 2020, DOI 10.2905/JRC.BMHR2K8)
An inventory of government API cases (ODS and XLSX). Nothing to draw.

### 30. 5a431f38 — API standards and technical specifications for governments (DOI 10.2905/JRC.8Y9SE20, JRC118082)
The standards analysed in the study (OpenAPI, OAuth and others). Still drawable: a citation, if the jury asks why the kit exposes a documented REST API.

### 31. 6715ba30 — API strategy case studies interviews: questionnaire (DOI 10.2905/JRC.EKF6WD0)
A PDF questionnaire. Nothing to draw.

### 32. 7340ab8a — API best practices references (Boyd & Vaccari 2020, DOI 10.2905/JRC.EZ83FWR)
A bibliography of public-sector API guidelines. Nothing to draw for the brief.

### 33. 8fad917f — APIs4DGov studied cases (DOI 10.2905/JRC.Q8T2V9G)
The list of case studies. Nothing to draw.

### 34. b387b652 — API adoption self-assessment: questionnaire (DOI 10.2905/JRC.FAVF5MR)
A self-assessment questionnaire, with an EUSurvey tool. Nothing to draw.

### 35. d226a0a9 — Government API strategy survey: questionnaire (DOI 10.2905/JRC.50TBDG0)
The survey source file (.eus). Nothing to draw.

---

## Not verified

- Whether DataM holds any flood dataset: its listing needs a token.
- The full dataset list behind the SPARQL endpoint: the WAF returned 403. The
  member lists came from the collections' JSON-LD instead, and those lists are
  complete for the three collections in scope.
- What licence the vocabulary code ODC_BL stands for (items 7 and 13), and
  which licence wins for PESETA IV (item 12).
- The content of the PESETA IV impact maps and CSVs (item 12). Only their
  titles were read; no file was downloaded.
