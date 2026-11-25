# Flood to policy

[![tests](https://github.com/Siegried81/flood-to-policy/actions/workflows/ci.yml/badge.svg)](https://github.com/Siegried81/flood-to-policy/actions/workflows/ci.yml)

**What it is.** A data pipeline and two apps that lay the Copernicus maps of the July 2021
floods over the European flood hazard map, count who the water reached outside the mapped
zone, and turn those counts into a policy brief that a person approves before it goes out.

**The question.** Can AI help Europe see flood risk early, and use it responsibly?

**What it found.** In Eschweiler, 91 % of the 1,213 residents the July 2021 water reached
lived outside the 1-in-100-year flood zone: the town sits on a river smaller than the
European map covers, so the map never looked there. Across the EU-27, about 25.7 million
people (5.8 %) live in the undefended 1-in-100-year river flood zone (JRC hazard maps,
GHS-POP E2025).

**What it asks.** Three changes for the Floods Directive review, none needing a new law:
make the Article 5 flood-risk declaration comparable across States (DG Environment, R1),
get Ireland and Lithuania into the published layer and show a missing report as missing
(EEA, R2), and test Article 8(5) on the Meuse: one State reports what it can't resolve
with its neighbours, and the Commission has six months to answer (R3).

**Built with.** Python (rasterio, GeoPandas, pandas) over about 7 GiB of open data,
FastAPI, an MCP server for agents, Streamlit and React front ends, LLM drafting with
offline citation and number checks, Docker, Kubernetes manifests, GitHub Actions and an
offline pytest suite.

Built for the European AI Challenge 2026 (JRC x FARI). Two answers come out of it: a
regional brief for the Liège-Limburg-Aachen crisis coordinator
([`docs/hackathon/`](docs/hackathon/)), and the EU-wide reading behind it, with three
recommendations for the Floods Directive review ([`docs/policy_answer.md`](docs/policy_answer.md)).

**Live demo (no install):** https://huggingface.co/spaces/flood-to-policy-team/flood-to-policy-team9
(the hosted demo runs with `HOSTED=1`, so drafting and translation are switched off there).
To run it all locally, `docker compose up --build` and open http://localhost:8501. No API
key is needed for the maps and tables.

[![Warn-order, the shelter gap and who to call across the border](docs/screenshots/react_anna_decision.png)](docs/screenshots/react_anna_decision.png)

The interactive map is Team 9's work ([`team9/`](team9/), [live](https://warn-before-the-water.surge.sh/team9/));
a [3D view of the Meuse at Liège](https://warn-before-the-water.surge.sh/vesdre_3d.html) is built by `scripts/build_vesdre_3d.py`.

## Key figures

| | |
|---|---|
| **91 %** | of the 1,213 residents the July 2021 water reached in Eschweiler lived outside the European 1-in-100-year flood zone (Ahr valley: 51 %). |
| **25.7 million** | EU-27 residents live in the undefended 1-in-100-year river flood zone. |
| **22 Dec 2027** | review deadline for the flood risk management plans (Directive 2007/60/EC, Art. 14(3)). |

### How well the hazard map matched July 2021

The 1-in-100-year map scored against the first Copernicus EMS flood maps of each country
(`data/processed/event_2021_countries.parquet`):

| Country | EMS maps | Water seen (km²) | Hit rate | False alarm ratio | Residents reached outside the zone |
|---|---|---|---|---|---|
| Belgium | 2 | 15.8 | 0.84 | 0.94 | 12 % |
| Germany | 16 | 65.7 | 0.57 | 0.92 | 38 % |
| Netherlands | 1 | 12.0 | 0.93 | 0.90 | 12 % |

Read the hit rate first. It's the share of the water seen that the map had. The false
alarm ratio (the share of the mapped zone that looked dry) is high by construction: the
map is built for 1-in-100-year planning, not to match one event, and a satellite image
comes after the peak and misses water under trees and in narrow streets. So it doesn't
prove the map is too wide. This is one event, scored on where the map puts any water,
not on the 0.5 m depth behind the 25.7 million.

The truth you score against matters too. In Wallonia the hit rate runs from 0.18 to 0.87
depending on the observed map, and the 0.87 comes from a 5.7 km² cluster holding 116
residents ([`limitations.md`](docs/limitations.md)). The Belgian 12 % is a floor: radar maps stop
at walls and miss streets, and against the extent Wallonia recorded on the ground, 40 to
51 % of the residents reached were outside the zone.

> **A screening view, not the statutory map.** Figures are NUTS3 statistics over the JRC
> river hazard maps, to decide where to look first. The maps that bind are the Member
> States' own (Article 6; EEA Flood Risk Areas Viewer). Say which of the two a figure is.

## Quick start

With Docker (the image holds the code, the built React UI and four small data files):

```bash
docker compose up --build                  # Streamlit on http://localhost:8501
docker compose --profile api up --build    # + React UI and JSON API on http://localhost:8001
```

From source (Linux/WSL2; on the Windows venv read `.venv\Scripts\python.exe`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/streamlit_app.py            # no build step
.venv/bin/uvicorn api.main:app --port 8001              # API
cd web && npm ci && npm run dev                         # React UI on http://localhost:5190
```

Rebuilding the tables needs the raw data (`python -m src.fetch`, about 7 GiB; steps in
[`docs/technical_deep_dive.md`](docs/technical_deep_dive.md)). `python scripts/check_offline_readiness.py`
exits 1 if the demo would need the network.

## Configuration

Copy `.env.example` to `.env` (never committed).

| Setting | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OLLAMA_URL` | language model for Draft, Translation and Ask; none set means those features are unavailable |
| `FLOOD_APPROVE_TOKEN` | secret `POST /api/approve` requires as `X-Approve-Token`; unset, only local callers may approve (under Kubernetes it is required) |
| `HOSTED=1` | public-demo mode: every model or write route answers 403, and the Streamlit tabs that need a model are disabled |

Ports: Streamlit 8501, API and built React UI 8001, Vite dev server 5190.

## Structure

| Path | Holds |
|---|---|
| `config/`, `src/`, `scripts/` | source registry (`sources.yaml`), the analysis, the builders and fetchers |
| `api/`, `app/`, `web/` | JSON API and MCP tools; Streamlit app; React + Vite UI (`npm run build` copies `data/processed/event_2021_web.json` into `public/`) |
| `team9/` | Team 9's map tool (its `flood_map.html` is kept in Git LFS, see its README) |
| `bi/`, `k8s/` | Power BI project; Kubernetes port of `docker-compose.yml` |
| `docs/`, `tests/` | written work; offline pytest suite |

## Tests and CI

```bash
pip install -r requirements-test.txt      # runtime + pytest
python -m pytest -q                       # tests/ and team9/tests, offline
cd web && npm ci && npm run build         # front end
```

CI runs the suite on Python 3.12 (the Docker image's version, and the one that gates a
release) and on 3.14 (the local Windows venv's) as a warning, then builds `web/` and the image. `requirements-dev.txt` adds local tools (cdsapi, debugpy, ipykernel). Playwright is in
`requirements-test.txt`: CI installs Chromium and runs the Team 9 browser tests on the LFS map.

## Docs

[`policy_answer.md`](docs/policy_answer.md) (findings, recommendations), [`technical_deep_dive.md`](docs/technical_deep_dive.md),
[`datasets.md`](docs/datasets.md), [`limitations.md`](docs/limitations.md), [`responsible_ai.md`](docs/responsible_ai.md),
[`workflow.md`](docs/workflow.md), [`power_bi.md`](docs/power_bi.md), [`legal_quotes.md`](docs/legal_quotes.md),
[`decisions.md`](docs/decisions.md) (dated record of what each figure means).

## Licence and data credits

Code: MIT ([`LICENSE`](LICENSE)). The data keeps its sources' licences, with the exact
credits in [`data/processed/DATA_NOTICE.md`](data/processed/DATA_NOTICE.md): © EuroGeographics
for the administrative boundaries (Eurostat/GISCO, NUTS 2024, non-commercial use); flood
hazard and population/built-up © European Union, JRC (CC BY 4.0); observed flood
© European Union, Copernicus Emergency Management Service (EMSR517, EMSR518, EMSR520);
Natura 2000 and river basin districts © European Environment Agency (CC BY 4.0);
contains modified Copernicus Climate Change Service information 2026; country borders
Natural Earth (public domain); indicators: Source: Eurostat. Region polygons are not
committed: the GISCO terms do not allow it.
