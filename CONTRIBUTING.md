# Contributing

## Setup

```bash
git clone https://github.com/Siegried81/flood-to-policy
cd flood-to-policy
python -m venv .venv && source .venv/bin/activate     # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt                   # runtime + pytest + local tools
python -m pytest -q                                   # tests/ and team9/tests, offline
cd web && npm ci && npm run build                     # front end
```

`requirements.txt` is runtime only (it is what the Docker image installs),
`requirements-test.txt` adds pytest, `requirements-dev.txt` adds cdsapi, debugpy,
playwright. The suite mocks the network, so it runs without the data bucket.

## Rebuild the deliverables

```bash
# Offline policy tool (one self-contained HTML page; output is gitignored: GISCO geometry)
python scripts/build_policy_tool.py --satellite --hero-aoi EMSR517_AOI09 \
  --hero-place "Eschweiler, in the Aachen region" \
  --front-aois "EMSR517_AOI09,EMSR518_AOI01,EMSR520_AOI01" --no-png --out _build/policy_tool

# Web app (what the Hugging Face Space serves)
python scripts/export_event_web.py --satellite --hero-aoi EMSR517_AOI09 \
  --front-aois "EMSR517_AOI09,EMSR518_AOI01,EMSR520_AOI01"
cd web && npm ci && VITE_STATIC=1 npm run build      # output in web/dist
```

## Where to work

| To change | Edit |
|---|---|
| Figures, text, decision cards of the HTML tool and the web app | `src/policy_tool.py` (shared by both) |
| React app | `web/src/` |
| Builders | `scripts/build_policy_tool.py`, `scripts/export_event_web.py` |
| The numbers | `data/processed/event_2021_*.parquet`, written by `scripts/event_2021.py` with the logic in `src/event2021.py` |

## Rules

- Keep `python -m pytest -q` green; doc figures are checked against the code
  (`scripts/docs_numbers.py --check`).
- Code, comments and commit messages in English; comments say why, not history.
- Prove a bug before fixing it; measure before and after.
- No secrets in the repo (only the gitignored `.env`), and no GISCO geometry.
- Two generated HTML pages are kept, latest build only, because the README links them:
  `web/public/vesdre_3d.html` (rebuild with `scripts/build_vesdre_3d.py`) and Team 9's
  `web/public/team9/flood_map.html` (Git LFS: run `git lfs pull`). Overwrite them when you
  rebuild; commit no other generated HTML.
- Branch off `main`; do not commit straight to `main`.
