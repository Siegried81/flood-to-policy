# Flood to policy

> **About this repository.** I prepared it for the European AI Challenge 2026
> hackathon, where I worked in a team of six. Nearly all of it is my own work,
> up to the last day. Two parts are the team's: the policy brief in
> [`docs/hackathon/`](docs/hackathon/), which I adapted, and the interactive map
> under [`web/public/team9/`](web/public/team9/) with its source in
> [`team9/`](team9/), which is Team 9's (live at
> https://warn-before-the-water.surge.sh/team9/). Next to the brief sit my AI
> sheet, my case notebook (run on the organisers' data), its outputs and the Q2
> sources it cites.

From flood maps to a policy recommendation: the July 2021 floods in Belgium,
Germany and the Netherlands, read against the European flood hazard map, and
what the next round of the Floods Directive should change. Built for the
**European AI Challenge 2026: From Data to Policy** (JRC × FARI, Brussels,
29–30 October 2026). At the event the case became **Anna's**: a cross-border
crisis coordinator for Liège, Limburg and the Aachen region, with a flood
warning on the table. My tool and the team's brief answer her four questions.

**Start here.** A Python tool turns the July 2021 flood maps into three
recommendations for the next Floods Directive round
([`docs/policy_answer.md`](docs/policy_answer.md)). A React app puts the July
2021 and Europe views in the browser. The full index of the written work is
[`docs/README.md`](docs/README.md).

**Live demo (July 2021 and Europe views, no install):**
https://huggingface.co/spaces/flood-to-policy-team/flood-to-policy-team9

[![Warn-order, the shelter gap and who to call across the border](docs/screenshots/react_anna_decision.png)](docs/screenshots/react_anna_decision.png)

*What I added to the July 2021 view in my React app: who to warn first, the shelter gap per valley, and who decides across the border.*

[![July 2021 floods: from exposure to planning, Team 9's four-scene map](docs/screenshots/team9_super_map.jpg)](https://warn-before-the-water.surge.sh/team9/)

*Team 9's interactive map: four scenes, from what the satellites saw to where to act first ([live](https://warn-before-the-water.surge.sh/team9/)).*

There's also a one-page [3D view of the Meuse at Liège](https://warn-before-the-water.surge.sh/vesdre_3d.html)
(`scripts/build_vesdre_3d.py`): the July 2021 water Copernicus mapped, draped on
the valley where the flood spread widest. Upstream, the steep Vesdre barely
shows: satellites miss the water hiding between buildings. It's a story scene,
not an analysis map, so no modelled depth is extruded.

[![The Meuse at Liège in 3D, the July 2021 flood draped on the valley](docs/screenshots/vesdre_3d.jpg)](https://warn-before-the-water.surge.sh/vesdre_3d.html)

Every story map and every Power BI page is in
[`docs/screenshots/`](docs/screenshots/) (the pages are described in
[`docs/power_bi.md`](docs/power_bi.md)). Data credits are at the
[end of this page](#licence-and-data-credits).

| | What the data says |
|---|---|
| **91 %** | of the 1,213 residents the July 2021 water reached in Eschweiler (Aachen region) lived *outside* the European 1-in-100-year flood zone: 1,107 people (Copernicus EMS first map, GHS-POP 2020). In the Ahr valley: 1,889 of 3,739 (51 %). |
| **375** | buildings graded destroyed in Germany on the first maps (792 with the later maps of the same areas). The water reached 32,562 residents there, 12,238 of them outside the 1-in-100-year zone. |
| **25.7 million** | EU-27 residents live inside the undefended 1-in-100-year river flood zone. July 2021 was not a one-off risk. |
| **22 Dec 2027** | the deadline for every Member State to review its flood risk management plans (Directive 2007/60/EC, Art. 14(3)): the next window to act. |

The organisers asked for three deliverables (Annex 4): a **policy tool** (any
file: html, pptx, png), the **policy brief** in the Annex 6 template and the
**AI sheet** in the Annex 7 template, sent by 13:30 on Day 2 and followed by a
**five-minute live demo**. The jury weighed four criteria equally: evidence and
soundness, policy usefulness (a named actor), clarity (tool and brief tell one
story) and responsible AI use. This repository is my evidence behind them.

> **Scope is a funnel: July 2021 at the core, Europe as the context.** The
> challenge data and its questions (Q1, Q3) are about the July 2021 floods, so
> that event is the core of the brief. The EU-wide work answers the next
> question, *is this a one-off?*, and gives the recommendation its scale and its
> named actor. It is checked against the *observed* flood extent on all 27
> Copernicus EMS products of July 2021 (4 in Belgium, 22 in Germany, 1 in the
> Netherlands). See [`docs/scope.md`](docs/scope.md).
>
> The working unit is **NUTS3**, and "European" here means the continent, not
> the Union: the GISCO NUTS 2024 file holds **1,345** polygons, 1,165 in the
> EU-27, 46 in EFTA and 134 in the candidate countries, which is why Turkish
> regions show up in the ranking. Filter on `EU_STAT == "T"` for an EU-only
> figure. The 1,166 often quoted is the NUTS 2021 count; in 2024 `DEG0P`
> (Eisenach) was merged into the Wartburgkreis.

> **A screening view, never the statutory map.** Every figure here is a NUTS3
> zonal statistic over the JRC river flood hazard maps, built to decide where to
> look first. The maps that bind under Directive 2007/60/EC are the Member
> States' own (Article 6), reported under Article 15 and served by the EEA Flood
> Risk Areas Viewer (https://discomap.eea.europa.eu/floodsviewer/). Quote those
> for a statutory statement about a place. Quote this kit for a comparison
> between regions, and say which of the two a figure is.

## Why this exists

The challenge was **not** a coding contest. It rewarded three clear, costed,
actionable recommendations for a public decision-maker, not the cleverest
model. The hard part sits in the middle: turning a raster into a sentence a
minister can act on. This repo is built for that middle step.

## The one equation everything hangs on

```
Risk = Hazard × Exposure × Vulnerability
```

- **Hazard**: where the water goes, and how deep, for a given return period
  (JRC river flood hazard maps).
- **Exposure**: who and what is in that water (GHS-POP population grid,
  OpenStreetMap critical infrastructure).
- **Vulnerability**: who suffers most from the same water (age, income,
  building type, insurance coverage).

A result that stops at exposure answers "how many people got wet". One that
reaches vulnerability answers "who needs help first", which is the question a
decision-maker actually has.

## Layout

```
flood-to-policy/
├── config/        # sources.yaml (every dataset + document, with provenance) and legislation.yaml
├── src/           # the analysis: exposure, vulnerability, validation, the July 2021 event, the policy tool
├── scripts/       # builders that freeze the tables in data/processed/ and fetch the raw data
├── api/           # JSON API over src/ (main.py) and 3 intent-based MCP tools (mcp_server.py)
├── web/           # React + Vite UI: the July 2021 story and the Europe view
├── app/           # Streamlit: the same, no build step
├── team9/         # Team 9's FARI tool, source of the interactive map under web/public/team9/
├── k8s/           # learning port of docker-compose.yml to Kubernetes, see k8s/README.md
├── docs/          # the written work, indexed in docs/README.md
└── tests/         # pytest, offline, no network
```

The full tree, file by file, is in
[`docs/technical_deep_dive.md`](docs/technical_deep_dive.md#9-repository-layout-file-by-file).
Two files are worth knowing first. `src/validate.py` scores the modelled hazard
against the observed July 2021 extent (hit rate, false alarm ratio, IoU), and
returns `None` rather than `0.0` when a denominator is empty.
`scripts/check_offline_readiness.py` checks the data files in bytes and exits 1
when the demo would still need the network, which `pytest` can't tell you since
it mocks the network away.

## Running it

### With Docker

The image is published on every push to `main`, on Docker Hub
(`siegried/flood-to-policy`) and GitHub Container Registry. It holds the code,
the built React UI and the four data files committed here, so it runs with
nothing cloned:

```bash
docker run --rm -p 127.0.0.1:8010:8010 siegried/flood-to-policy \
  python -m uvicorn api.main:app --host 0.0.0.0 --port 8010    # http://localhost:8010
```

From a clone with the full `data/`, compose mounts it:

```bash
docker compose pull
docker compose --profile api up -d    # Streamlit on http://localhost:8501, React + API on http://localhost:8010
```

Add `--env-file .env` for an LLM key. Why Docker matters on this Windows
machine, the dev container and the self-contained `portable` image are in
[§10 of the deep dive](docs/technical_deep_dive.md#10-running-it-windows-docker-and-deployment).

### From source

Written for Linux/WSL2. On the Windows venv, read `.venv\Scripts\python.exe`
for `.venv/bin/python`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q           # <!-- numbers:tests_collected -->1,130<!-- /numbers --> tests, offline: no network, no model
.venv/bin/python -m src.fetch           # 99 files, about 7 GiB (re-run only to fill gaps)
.venv/bin/python scripts/build_exposure.py --stripes 72 # -> data/processed/exposure.parquet
.venv/bin/python scripts/build_context.py  --stripes 72 # -> data/processed/context.parquet
.venv/bin/python scripts/build_geometry.py             # -> data/processed/regions.geojson
.venv/bin/python scripts/export_bi.py                  # -> bi/data/, read by bi/FloodToPolicy.pbip (docs/power_bi.md)
.venv/bin/python scripts/check_offline_readiness.py   # exits 1 if the demo needs the network
.venv/bin/python scripts/docs_numbers.py --check      # exits 1 if a doc's number no longer matches the code

# July 2021: event_2021.py first, every step below reads its tables.
.venv/bin/python scripts/event_2021.py                # organisers' public bucket (cached in data/raw/challenge_2021/) -> data/processed/event_2021_*.parquet
.venv/bin/python scripts/event_2021_infrastructure.py # -> data/processed/event_2021_infrastructure.parquet
.venv/bin/python scripts/build_policy_tool.py         # -> docs/perso/policy_tool_anna/ (gitignored: GISCO geometry)
.venv/bin/python scripts/export_event_web.py          # -> data/processed/event_2021_web.json + web/public/ copy

# Either UI. Both read the same frozen table, so they can't disagree on a number.
.venv/bin/streamlit run app/streamlit_app.py            # no build step
.venv/bin/uvicorn api.main:app --port 8010              # + the React dev server, below
cd web && npm ci && npm run dev                         # open http://localhost:5190
```

The React UI is the one to demo. It draws the map as SVG from GeoJSON, with no
tile provider and no API key, so it still works with the network unplugged.
Streamlit is the fallback that needs no `npm`.

`--stripes` only sets memory use, not the result: 72 peaks around 7.5 GB, which
fits a 16 GB WSL VM. The raw data is not committed (`data/` is ignored), except
`exposure.parquet`, `context.parquet`, `event_2021_web.json` and
`DATA_NOTICE.md` in `data/processed/`. What `src.fetch` downloads, and the three
sources it doesn't (Risk Data Hub, EEA river basins, CDS projections), are in
[`docs/datasets.md`](docs/datasets.md#what-the-whole-download-costs) and §10 of
the deep dive.

The deep dive also covers the static build behind the live demo, the API's
`HOSTED=1` and `FLOOD_APPROVE_TOKEN` switches, the three MCP tools for agents,
and *Ask the table*, where a model turns a plain question into a whitelisted
pandas query.

## Docs, in reading order

[`docs/README.md`](docs/README.md) is the index: the twenty-minute read, one
sentence per file, and the full reading order. Start with
[`docs/policy_answer.md`](docs/policy_answer.md), the spine: the question as the
organisers asked it, four findings with their figures, three recommendations
with the article, authority and date behind each.
[`docs/decisions.md`](docs/decisions.md) is the dated record of every change to
what a number means; read it before quoting a figure from an older run.

## Licence and data credits

The code is MIT ([`LICENSE`](LICENSE)). The data is not: the files committed
under `data/processed/` keep their sources' licences, listed with the exact
credit each requires in
[`data/processed/DATA_NOTICE.md`](data/processed/DATA_NOTICE.md). In short:
© EuroGeographics for the administrative boundaries (Eurostat/GISCO, NUTS 2024,
non-commercial use); flood hazard and population/built-up © European Union, JRC
(CC BY 4.0); observed flood © European Union, Copernicus Emergency Management
Service (EMSR517, EMSR518, EMSR520); Natura 2000 and river basin districts
© European Environment Agency (CC BY 4.0); contains modified Copernicus Climate
Change Service information 2026; country borders Natural Earth (public domain);
indicators: Source: Eurostat. The region polygons themselves are not committed,
because the GISCO terms don't let this repository pass them on.
