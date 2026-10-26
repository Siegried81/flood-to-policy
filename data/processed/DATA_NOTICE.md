# Data notice — `data/processed/`

The MIT licence of this repository covers the **code only**. The two tables
committed here, `exposure.parquet` and `context.parquet`, are derived from
third-party datasets and remain subject to their licences. They have been
modified: aggregated per NUTS3 region, reprojected, thresholded, and in places
NUTS2 figures applied to NUTS3 children. None of the original publishers is
responsible for these results.

`regions.geojson` is deliberately **not** committed. It is a simplified copy of
the GISCO NUTS geometry, whose terms grant a non-transferable right to use and
process for non-commercial purposes only, which a public MIT repository cannot
pass on. `python scripts/build_geometry.py` rebuilds it in seconds from the
boundary file `python -m src.fetch` downloads, and a hosted Streamlit app that
has neither downloads that file from GISCO and builds it on first use.

## Sources and required credits

- **Region codes and names (NUTS 2024)** — Source: Eurostat/GISCO. Any map drawn
  from the boundaries must show: "© EuroGeographics for the administrative
  boundaries" (non-commercial use; commercial use needs a EuroGeographics
  licence). <https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units>
- **Flood hazard** — JRC / Copernicus Emergency Management Service, river flood
  hazard maps for Europe v3.1.1, doi:10.2905/1D128B6C-A4EE-4858-9E34-6210707F3C81.
  © European Union, CC BY 4.0.
- **Population and built-up surface** — JRC Global Human Settlement Layer,
  GHS-POP and GHS-BUILT-S R2023A. © European Union, CC BY 4.0.
- **Natura 2000 and WFD river basin districts** — © European Environment Agency,
  CC BY 4.0 (Natura 2000 doi:10.2909/91357f39-7866-41ce-b447-43905c364ec8).
- **Floods Directive areas of potential significant flood risk (APSFR)** —
  Source: European Environment Agency, reported by the Member States. Licence
  **not verified**: the service publishes none, and the EEA default (CC BY 4.0
  unless otherwise indicated) is assumed.
- **Climate projections** — Contains modified Copernicus Climate Change Service
  information 2026 (doi:10.24381/cds.73237ad6), CC BY 4.0. Neither the European
  Commission nor ECMWF is responsible for any use that may be made of the
  Copernicus information or data it contains.
- **Flood protection standards** — JRC PESETA IV (Bianchi et al. 2022),
  `floodProtection_v2019_paper`. © European Union, CC BY 4.0. Used to mask the
  cells whose design standard holds a scenario (`residual_exposed_pop_rp*`).
- **Population and built-up surface, 2010 epoch** — JRC GHSL GHS-POP and
  GHS-BUILT-S E2010 R2023A. © European Union, CC BY 4.0.
- **Hospitals and education sites** — Source: Eurostat - GISCO (healthcare
  2023_v2025_11, education 2023_2026_01), from Member States' official
  sources. GISCO terms of use; definitions vary by country. Only counts per
  region are published here, never the points.
- **EFAS reanalysis and return levels** — Contains modified Copernicus
  Emergency Management Service information 2026 (EFAS historical v5.0,
  doi:10.24381/cds.e3458969; v5.1 flood thresholds; LISFLOOD static maps).
  CEMS-FLOODS licence. Not a flood warning.
- **Sealed soil and observed discharge trend** — HERA sealed fraction and HERA
  v2 river discharge reanalysis 1991-2020 (JRC / CEMS), © European Union,
  CC BY 4.0.
- **Heavy precipitation and flood recurrence** — Contains modified Copernicus
  Climate Change Service information 2026 (European Climate Data Explorer,
  sis-ecde-aggregated-climate-indicators, doi:10.24381/accabcec), CC BY 4.0.
  Neither the European Commission nor ECMWF is responsible for any use that may
  be made of the Copernicus information or data it contains.
- **Imperviousness and land cover** — Generated using European Union's
  Copernicus Land Monitoring Service information (HRL Imperviousness Density
  2018, doi:10.2909/524fa72f-61d7-4364-801e-3e271d7b10bc; CORINE Land Cover
  2018), CC BY 4.0.
- **Demographic and economic indicators** — Source: Eurostat (demo_r_pjangrp3,
  ilc_li41, nama_10r_3gdp, accessed 2026-10-07; demo_r_d3dens, nama_10r_2hhinc,
  accessed 2026-10-12). Values were reshaped, and NUTS2 figures applied to their
  NUTS3 children. Eurostat bears no responsibility for these derived figures.

## One legacy column name

`exposure.parquet` was frozen on 2026-10-07, before the poverty rate gained its
unit in its name. It carries `poverty_rate`, `poverty_rate_year` and
`poverty_rate_level`; the current build writes `poverty_rate_pct*`. Both UIs and
the API read it through `src.demographics.with_current_names`, so the figures are
the same. A rebuild writes the new names.
