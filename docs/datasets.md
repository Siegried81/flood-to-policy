# Datasets

`config/sources.yaml` is the single source of truth for every URL, CRS, unit, licence
and verification date; if this page disagrees with it, the YAML is right. This page is
the reading of it: what each source is for and the trap it carries. Licence credits
are in [`data/processed/DATA_NOTICE.md`](../data/processed/DATA_NOTICE.md).

## Facts that break a naive pipeline

1. The JRC hazard maps are EPSG:4326 at 3 arc-seconds, not 100 m in EPSG:3035 (that is
   the retired v2.x).
2. Observed depth maps are in centimetres, hazard maps in metres: a factor-100 error
   that returns a plausible number. Convert before comparing.
3. Belgium needs two GHS-POP 100 m tiles (`R3_C19` and `R4_C19`; the boundary is at
   51.214 N and cuts through Antwerp).
4. Belgian communes: 581 or 565 depending on the vintage (mergers of 2025-01-01). Pick
   one and build the crosswalk before joining.
5. Statbel files are UTF-8 with a BOM (`encoding="utf-8-sig"`); forcing latin-1 produces
   the mojibake.

## Sources

| Source | What for | Notes and traps |
|---|---|---|
| **JRC river flood hazard maps** v3.1.1 | the hazard | nine return periods (10-500); depth in metres; Float32, nodata -9999, sparse (nodata means dry); EPSG:4326; 272-350 MB each; CC-BY 4.0 |
| **JRC satellite-derived flood depth** 2015-2025 | observed validation layer, 20 m | centimetres; uint16, nodata 0, 9999 = permanent or seasonal water; EPSG:27704 |
| **GHSL GHS-POP E2025** | population (Europe) | 1 km Mollweide file (323 MB, nodata -200); 100 m tiles for zooms |
| **GHSL GHS-POP E2020** | population (July 2021 event) | the grid Annex 2 of the challenge asks for |
| **GHSL GHS-BUILT-S** | built-up surface | same grid as GHS-POP byte for byte, so cells divide without resampling; footprint, not value |
| **Copernicus EMS** EMSR517 (DE), EMSR518 (BE), EMSR520 (NL) | observed July 2021 flood, 27 products | read from the organisers' public bucket and the S3 bucket of EMS; delineation vs grading products; first map and monitoring passes are separate; EMSR518 has two delineations per AOI |
| **Wallonia aléa d'inondation** (SPW) | official hazard map | EPSG:31370; one dataset with a `CLASSEMENT` class code; CC-BY 4.0, attribution verbatim |
| **Wallonia observed July 2021** (SPW) | second ground truth | extent layer reachable; the depth layer's URL is single-use and expired (404), so a by-hand copy is on disk and only read as an extent |
| **GISCO NUTS 2024, LAU 2024** | boundaries | NUTS3 file: 1,345 polygons over 37 countries (1,165 in the EU-27, the rest EFTA and candidates), EPSG:3035; terms forbid redistributing the polygons |
| **Eurostat** `demo_r_pjangrp3`, `ilc_li41`, `nama_10r_3gdp`, `demo_r_d3dens`, `nama_10r_2hhinc` | age, poverty, GDP, density, income | poverty and household income are NUTS2 only; density sits on NUTS 2021 codes (some 2024 regions blank); pin GDP's unit |
| **JRC Risk Data Hub** (OGC API) | historical losses, published vulnerability | EU Login bearer token valid 10 h; rows repeat per administrative level and average several sources, so never sum unfiltered; cached under `data/processed/rdh_cache/` |
| **HANZE v3.0.1** (Zenodo) | flood impacts 1870-2025 | traces a loss to a named event; NUTS 2024 vintage; deflate and convert currency before comparing |
| **EEA WISE river basin districts** | cross-border basins | REST service, 196 districts, no bulk file, answers HTTP 500 to some pages; a district is a national portion, so grouping uses `config/international_basins.yaml` |
| **EEA Floods Directive APSFR** | what Member States declared (Art. 5) | cached as GeoParquet; 2010 and 2018 cycles must not be overlaid; Ireland and Lithuania absent from 2018 |
| **Natura 2000, CORINE land cover** | environment on flood-prone ground | 1.27 GB GeoPackage; area, not harm; EU-27 only |
| **PESETA IV flood protection standards** | residual exposure behind dykes | 500 m, EPSG:3035; nearest neighbour only; unknown means unprotected |
| **Copernicus CDS hydrology projections** (EURO-CORDEX, E-HYPEgrid, VIC-WUR) | future discharge | one member per request via `scripts/fetch_cds_member.py`; the dataset is unsupported |
| **C3S ECDE**, **EFAS**, **HERA** | climate indicators, flood thresholds, 1991-2020 discharge | own fetch scripts (`fetch_c3s_ecde.py`, `fetch_efas_july2021.py`, `fetch_hera.py`) |
| **EMO-1 precipitation 2021** | July 2021 event rain | 1 arcmin daily NetCDF (about 39 GB decoded): only a time window and bounding box are loaded (`src/rainfall.py`) |
| **JRC catalogue API** | dataset discovery | has no free-text search (every parameter ignored, full catalogue returned); a WAF answers a default User-Agent with an HTML rejection under HTTP 200; use the SPARQL endpoint `https://data.jrc.ec.europa.eu/sparql` |
| **Policy corpus** (Directive 2007/60/EC, WFD, AI Act, EU strategies, ...) | the RAG corpus | declared under `policy_corpus` in `sources.yaml`; EU acts come from the Publications Office CELLAR because eur-lex answers scripts with a WAF challenge |

## What the download costs

`python -m src.fetch` expands the entries of `sources.yaml` into one job per file
(about 7 GiB; the nine return periods alone are about 2.6 GiB) and is idempotent.
Entries with `access: api` are queried at run time and `access: folder` entries (HERA,
the organisers' bucket) are read by their own scripts, so `fetch` lands nothing for
them. Entries point at files, never at a directory listing, which would be stored as
data and treated as done. Re-count with `src.fetch.expand()` rather than quoting this
page.

## Before you trust any raster

```python
import rasterio
with rasterio.open(path) as src:
    print(src.crs, src.crs.to_epsg())         # None is NOT 4326
    print(src.res, src.dtypes[0], src.nodata)  # degrees or metres? nodata None is a red flag
    a = src.read(1, masked=True)
    print(a.min(), a.max(), a.sum())           # metres or cm? population: compare to the published total
```

An undeclared nodata sentinel (often -9999, -200 or 0) gets summed as a measurement;
declare it yourself.
