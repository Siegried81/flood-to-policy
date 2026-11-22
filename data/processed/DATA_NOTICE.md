# Data notice: `data/processed/`

The MIT licence of this repository covers the **code only**. The data files committed
here (`exposure.parquet`, `context.parquet`, `event_2021_web.json`) are derived from
third-party datasets and remain subject to their licences. They have been modified:
aggregated per NUTS3 region, reprojected, thresholded, with NUTS2 figures applied to
NUTS3 children; the July 2021 export is measured per Copernicus EMS product and per
country. None of the original publishers is responsible for these results.

`regions.geojson` is deliberately **not** committed: it is a simplified copy of the
GISCO NUTS geometry, whose terms allow non-commercial use only, which a public MIT
repository cannot pass on. `python scripts/build_geometry.py` rebuilds it from the
boundary file `python -m src.fetch` downloads. The static Europe view draws its map from
GISCO's own NUTS file, downloaded by the viewer's browser; neither the repository nor the
published site holds a copy. `event_2021_web.json` carries no GISCO line: its locator map
uses Natural Earth borders; `scripts/export_event_web.py --full` writes a richer local
copy (`event_2021_web.full.json`, git-ignored). `web/public/event_2021_web.json` is a
build copy of the committed file (`npm run build` makes it).

## Sources and required credits

- **Region codes and names (NUTS 2024)**: Source: Eurostat/GISCO. Any map drawn from the
  boundaries must show: "© EuroGeographics for the administrative boundaries"
  (non-commercial use; commercial use needs a EuroGeographics licence).
- **Country borders on the July 2021 locator map**: Natural Earth 1:10m admin-0 countries
  v5.1, public domain; credit given as a courtesy.
- **Observed flood extent and damage grading, July 2021**: Copernicus Emergency Management
  Service Rapid Mapping, EMSR517 (Germany), EMSR518 (Belgium), EMSR520 (Netherlands),
  © European Union. Free use with attribution.
- **Buildings and population, July 2021**: JRC GHSL GHS-OBAT R2024A (epoch 2020) and
  GHS-POP R2023A (E2020, 30 arc-seconds). © European Union, CC BY 4.0.
- **Flood hazard**: JRC / Copernicus Emergency Management Service, river flood hazard maps
  for Europe v3.1.1, doi:10.2905/1D128B6C-A4EE-4858-9E34-6210707F3C81. © European Union,
  CC BY 4.0.
- **Population and built-up surface**: JRC Global Human Settlement Layer, GHS-POP and
  GHS-BUILT-S R2023A, epoch 2025 at 1 km (and E2010 for the 2010 epoch). © European Union,
  CC BY 4.0.
- **Natura 2000 and WFD river basin districts**: © European Environment Agency, CC BY 4.0
  (Natura 2000 doi:10.2909/91357f39-7866-41ce-b447-43905c364ec8).
- **Floods Directive areas of potential significant flood risk (APSFR)**: Source:
  European Environment Agency, reported by the Member States. Licence **not verified**:
  the service publishes none; the EEA default (CC BY 4.0 unless otherwise indicated) is
  assumed.
- **Climate projections**: Contains modified Copernicus Climate Change Service information
  2026 (doi:10.24381/cds.73237ad6), CC BY 4.0. Neither the European Commission nor ECMWF
  is responsible for any use that may be made of the Copernicus information or data it
  contains. The same wording applies to the heavy-precipitation and flood-recurrence
  indicators (European Climate Data Explorer, doi:10.24381/accabcec).
- **Flood protection standards**: JRC PESETA IV (Bianchi et al. 2022),
  `floodProtection_v2019_paper`. © European Union, CC BY 4.0.
- **Hospitals and education sites**: Source: Eurostat - GISCO, from Member States'
  official sources; definitions vary by country. Only counts per region are published.
- **EFAS reanalysis and return levels**: Contains modified Copernicus Emergency Management
  Service information 2026 (EFAS historical v5.0, doi:10.24381/cds.e3458969; v5.1 flood
  thresholds). CEMS-FLOODS licence. Not a flood warning.
- **Sealed soil and observed discharge trend**: HERA sealed fraction and HERA v2 river
  discharge reanalysis 1991-2020 (JRC / CEMS), © European Union, CC BY 4.0.
- **Imperviousness and land cover**: Generated using European Union's Copernicus Land
  Monitoring Service information (HRL Imperviousness Density 2018,
  doi:10.2909/524fa72f-61d7-4364-801e-3e271d7b10bc; CORINE Land Cover 2018), CC BY 4.0.
- **Demographic and economic indicators**: Source: Eurostat (demo_r_pjangrp3, ilc_li41,
  nama_10r_3gdp, demo_r_d3dens, nama_10r_2hhinc). Values were reshaped, and NUTS2 figures
  applied to their NUTS3 children. Eurostat bears no responsibility for these derived
  figures.

## One legacy column name

`exposure.parquet` was frozen before the poverty rate gained its unit in its name: it
carries `poverty_rate*`, the current build writes `poverty_rate_pct*`. The UIs and API read
it through `src.demographics.with_current_names`; a rebuild writes the new names.
