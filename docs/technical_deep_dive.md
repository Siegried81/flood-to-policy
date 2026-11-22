# Technical deep dive

How it works and why. Commands live in the [README](../README.md); the dated record of
changes to what a figure means is [decisions.md](decisions.md). Figures here are measured on the frozen tables; re-derive
them rather than quoting this page.

## 1. Pipeline

```
config/sources.yaml            one file owns every URL
python -m src.fetch            idempotent, robots-aware download into data/raw/
   |-- scripts/build_exposure.py   hazard x population per NUTS3 x return period (+ --protection)
   |-- scripts/build_context.py    built-up, Natura, basins, climate, residual exposure, facilities
   `-- scripts/build_geometry.py   boundaries -> simplified regions.geojson
data/processed/{exposure,context}.parquet, regions.geojson
   -> api/main.py (JSON routes over src/) -> web/ (React), scripts/export_bi.py (Power BI)
   -> app/streamlit_app.py reads the parquets directly (no server, no npm)
```

The July 2021 event has its own chain (section 5). The exposure table is a multi-hour
continental pass; the geometry takes seconds, so they are separate files. Both UIs
read the same frozen tables and cannot disagree on a number. React has three views
(`VIEWS` in `web/src/App.jsx`: Team 9 map, July 2021, Europe); Streamlit shows the
same content in tabs.

A static build (`VITE_STATIC=1`) needs no API: it reads `event_2021_web.json` and the
Europe answers frozen into `web/public/europe/` by `scripts/export_europe_web.py`.
Draft and Translation call a model and stay off there.

## 2. Coordinate systems

A layer in the wrong CRS still plots, joins and produces a number, just the wrong one.

| CRS | Used for |
|---|---|
| EPSG:3035 (ETRS89-LAEA), `data_io.WORKING_CRS` | every area, distance and zonal computation |
| EPSG:4326, `data_io.WEB_CRS` | the JRC hazard rasters' own grid; display |
| ESRI:54009 (Mollweide) | GHS-POP, the grid exposure is computed on |
| EPSG:27704 (Equi7 Europe) | JRC observed flood depth |
| EPSG:31370 (Belgian Lambert 72) | Walloon layers; reprojected before any European join |

- A file with no CRS raises (`load_vector`); never assume 4326.
- Reproject the polygons to the raster, never a raster of counts to the polygons (it
  moves people between cells). `scripts/build_exposure.py` asserts the boundary CRS
  before opening a raster; `pyproj` is pinned because without it geopandas silently
  returns `crs=None`.
- A tolerance is a distance, so apply it in a metric CRS (`build_geometry.py`
  simplifies in 3035, then converts).
- Hazard cells are 3 arc-seconds, about 92 m north-south by 60 m east-west at Belgian
  latitudes: not square, so never compute an area in 4326.

## 3. What the exposure number means

`Risk = Hazard x Exposure x Vulnerability`. Hazard arrives as data (JRC river flood
maps); this repository computes exposure (GHS-POP, OSM infrastructure) and gives
vulnerability (age, income, building type) its own module. Stopping at exposure
answers "how many got wet"; vulnerability answers "who needs help first".

- **Modes** (`src/exposure.py`): `fraction` (default) thresholds the hazard first and
  then averages the 0/1 wet mask over each population cell; `binary` counts a whole
  cell as soon as any part floods (an over-estimate). Threshold first, average second.
- **`nodata_means_dry`**: JRC maps store depth only where there is water, so nodata is
  dry (`True`, default). For an AOI-clipped layer (Copernicus EMS, Walloon 2021) nodata
  is "not looked at" (`False`): the share is measured over the observed part and
  extrapolated. Using `False` on a sparse layer silently turns `fraction` into `binary`.
- **Four columns**: `exposed_pop` (extrapolated where the layer covers part of the
  unit, `None` when nothing was measured), `exposed_pop_observed` (no extrapolation,
  additive over windows), `cells_counted`, `hazard_coverage`. `None` is not `0.0`:
  a unit the hazard raster does not cover must never read as a measured all-clear.
  Report `hazard_coverage` next to the count. Zonal statistics use
  `all_touched=False` so a boundary cell is counted once.
- **Windowing**: the build cuts the population grid, never the hazard raster; a
  population cell then belongs to exactly one window and the sums are additive whatever
  the window count (`tests/test_stripes.py`). `--stripes` only sets memory.
- **Masks**: permanent water bodies and the JRC's spurious-depth areas are removed;
  `--min-depth-m` defaults to 0.5 m (pass 0 for the any-water upper bound and say so).
- **Undefended and residual**: the JRC maps ignore dykes, so `exposure.parquet` is
  undefended. `build_exposure.py --protection` reruns the pass behind the PESETA IV
  protection standards (nearest neighbour; unknown standard counts as unprotected) into
  `exposure_protected.parquet`, carried into `context.parquet` as
  `residual_exposed_pop_rp*`. Quote it as "behind the design standards", never "after
  protection". The parts of a run are parked in `data/processed/exposure_parts/`.
- **Return periods are nested**: the 100-year extent contains the 10-year one, so
  periods are never added. A 100-year flood has a 1 % chance each year and about 63 %
  over a century; it is not "once a century". Quote the period with every headcount.
  `/api/exposure` narrows to one period and says so in `defaulted_return_period`.

## 4. Derived files and the API

- `exposure.parquet`: one row per region x return period (long on purpose). Nothing
  numeric may be added to it that is not an exposure: `vulnerability_indicators` scans
  its numeric columns into a weighted index.
- `context.parquet`: one row per region, everything else (climate, basins, residual
  exposure, hospitals and schools, 2010 epoch). A country a layer does not cover is NaN,
  never 0. `build_context.py --only <layer>` rebuilds one layer and keeps the rest.
- `regions.geojson`: simplified at 1 km in 3035, not committed (GISCO terms); the
  property names are the join key (`nuts_id`, not GISCO's `NUTS_ID`) and all polygons are
  kept so legend quantiles do not move.
- Routes: `/api/{health,config,event2021,meta,exposure,context,geometry,vulnerability,
  search,draft,languages,translate,approve,ask}`. `HOSTED=1` makes every model or write
  route answer 403. `POST /api/approve` is the only writer: with `FLOOD_APPROVE_TOKEN`
  set it needs `X-Approve-Token`; unset, only a loopback caller (or, inside Docker, the
  bridge gateway) may approve. `/api/translate` answers 422 when a translation changes
  a figure or moves a citation. `/api/ask` takes a question or a query spec, validated
  against a whitelist by `src/nlquery.py`; the answer holds only table values.
- The choropleth is SVG from GeoJSON: no tile provider, no API key, works offline.

## 5. Validation and the July 2021 chain

`src/validate.py` scores the modelled hazard against the observed extent (hit rate,
false alarm ratio, IoU) and returns `None`, never `0.0`, when a denominator is empty.
The observed snapshot is not the flood peak, so the false alarm ratio bounds nothing.
`scripts/event_2021.py` reads the organisers' bucket (27 Copernicus EMS products:
EMSR517 DE, EMSR518 BE, EMSR520 NL) inside their areas of interest and writes
`data/processed/event_2021_*.parquet`; the infrastructure, rainfall and web-JSON
scripts read those tables. Event figures use GHS-POP E2020; Europe uses E2025 at 1 km,
and the two never enter one sum. What each figure cannot say is in
[limitations.md](limitations.md).

## 6. The LLM layer

A LangGraph workflow (`src/workflow.py`), not an agent: retrieve passages from the
policy corpus (`src/rag.py`, BM25 over `data/raw/`), draft with a model (Anthropic,
Groq or a local Ollama), check the draft (numbers must exist in the sources, every
sentence cites a passage, negations survive translation) and stop at a human approval
gate. Details in [workflow.md](workflow.md). MCP access (`api/mcp_server.py`) exposes
three question-shaped tools (`rank_regions`, `profile_regions`,
`find_policy_evidence`); approval is deliberately not a tool.

## 7. Tests

`python -m pytest -q` runs `tests/` and `team9/tests` (see `pytest.ini`), offline: the
network is mocked, so `scripts/check_offline_readiness.py` is what tells whether the
demo needs the network. Doc figures are held to the code by
`scripts/docs_numbers.py`; docstring citations by `tests/test_docs_citations.py`.

| Fact | Where it comes from |
|---|---|
| <!-- numbers:tests_collected -->1,150<!-- /numbers --> tests in `tests/` | `scripts/docs_numbers.py --write` (`pytest tests --collect-only`) |
| <!-- numbers:sources_declared -->93<!-- /numbers --> declared inputs, <!-- numbers:sources_verified -->74<!-- /numbers --> verified, <!-- numbers:sources_licensed -->43<!-- /numbers --> licensed | `config/sources.yaml` entries |

## 8. Repository layout

| Path | Holds |
|---|---|
| `src/` | exposure, vulnerability, validation, climate, basins, rag, workflow, policy tool |
| `scripts/` | `build_*` (frozen tables), `fetch_*`, `export_*` (BI, web), `event_2021*.py`, `check_offline_readiness.py`, `docs_numbers.py` |
| `api/` | `main.py` (FastAPI), `mcp_server.py` |
| `app/` | Streamlit app |
| `web/` | React + Vite UI; `npm run build` copies `data/processed/event_2021_web.json` into `public/` |
| `team9/` | Team 9's map tool (source of `web/public/team9/flood_map.html`, kept in Git LFS) |
| `bi/` | Power BI project (PBIR); `bi/data/` is regenerated |
| `config/` | `sources.yaml`, `legislation.yaml`, `international_basins.yaml` |
| `tests/` | offline pytest suite |
| `k8s/`, `.devcontainer/`, `docker-compose*.yml` | deployment and dev environments |

## 9. Running it

- **Why Docker on Windows**: an application-control policy (Smart App Control) can
  block the native DLLs of rasterio, pyogrio, rasterstats and tiktoken, on some days and
  not others. Re-measure before believing either state; the WSL2 venv or the image is
  the route that does not depend on it. `pyogrio` and `pyproj` are capped for the same
  reason (`.github/dependabot.yml` ignores them). CI runs Python 3.12 like the image;
  the local venv is cp314.
- **Targets** (`Dockerfile`): `app` (code, small data files), `test` (+ pytest),
  `portable` (+ the whole `data/`, for an offline laptop).
- **Memory**: the default `--stripes` is enough on a workstation; 72 peaks near 7.5 GB
  in a 16 GB WSL VM. An interrupted build resumes from the parked return periods.
- **Data `src.fetch` does not cover**: JRC Risk Data Hub (EU Login bearer token valid
  10 h; responses cached), EEA river basin districts (slow REST, cached in
  `data/processed/basins_cache/`), CDS hydrology projections
  (`scripts/fetch_cds_member.py`). HERA, EFAS 2021 and C3S ECDE have their own scripts.
  `scripts/check_offline_readiness.py` exits 1 when a file the demo needs is missing.
- **Static demo** (Hugging Face Space): `python scripts/export_europe_web.py`, then in
  `web/` `VITE_STATIC=1 VITE_BASE=/ npm run build` (prefix `MSYS_NO_PATHCONV=1` in Git
  Bash) and upload `web/dist/` without `team9/`.
- **Team 9 map**: `web/public/team9/flood_map.html` (37 MB) is built by `team9/map.py`
  from Google Cloud Storage and OSM. Only the latest build is kept, in Git LFS
  (`git lfs pull`); replace it when you rebuild.
- **MCP**: `python -m api.mcp_server` (stdio), `claude mcp add flood-kit -- python -m
  api.mcp_server`, or `docker compose --profile agent run --rm -T mcp`.
- **Ask the table**: `curl -s localhost:8001/api/ask -H 'Content-Type: application/json'
  -d '{"spec": {"columns": ["region","exposed_share"], "return_period": 100, "limit": 5}}'`
  needs no model; a `question` field costs one model call that writes the spec.

## 10. What each figure means

The dated reasons are in [decisions.md](decisions.md).

- Event numbers are inside the products' areas of interest only: outside is "not
  mapped", not dry. Say "buildings graded destroyed", not "homes destroyed".
- Europe numbers are NUTS3 zonal statistics over the JRC river hazard maps: a screening
  view, never the statutory map (Member States' maps under Article 6).
- Both UIs open on the 1-in-100-year flood and on the EU-27 (1,165 of the 1,345 NUTS3
  polygons of the GISCO 2024 file; the rest are EFTA and candidate countries).
- `poverty_rate_pct` is a percentage at NUTS2 applied to NUTS3; `share_over_65` is a
  fraction. Older frozen tables still call the former `poverty_rate`.
- Population grids: E2020 for the event, E2025 at 1 km for Europe.
- Climate figures are medians and quartiles of 16 chains under one pathway (RCP 8.5);
  "robust" means at least 80 % of members agree on the sign.
- Hospitals or beds without a figure are unknown, not 0; grey on a map is "not
  measured", never zero.
