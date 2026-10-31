# Contributing (Team 9)

Short guide for teammates improving the flood-to-policy tool during the
hackathon. See the live result first:
https://huggingface.co/spaces/flood-to-policy-team/flood-to-policy-team9

## Setup

```bash
git clone https://github.com/Siegried81/flood-to-policy
cd flood-to-policy
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux:        source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q            # must end in "passed", with no failure
```

The full test suite is offline (all network calls are mocked), so it runs
without the data bucket.

## Rebuild the deliverables

Offline tool (self-contained HTML page):

```bash
python scripts/build_policy_tool.py --satellite \
  --hero-aoi EMSR517_AOI09 --hero-place "Eschweiler, in the Aachen region" \
  --front-aois "EMSR517_AOI09,EMSR518_AOI01,EMSR520_AOI01" \
  --no-png --out docs/perso/policy_tool_anna
# open docs/perso/policy_tool_anna/policy_tool.html
```

Web app (React, what the Hugging Face Space serves):

```bash
python scripts/export_event_web.py --satellite --hero-aoi EMSR517_AOI09 \
  --front-aois "EMSR517_AOI09,EMSR518_AOI01,EMSR520_AOI01"
cd web && VITE_STATIC=1 npm install && npm run build   # output in web/dist
```

## Where to work

| You want to change... | Edit |
|---|---|
| The offline HTML tool (figures, text, decision cards, priority scores) | `src/policy_tool.py` |
| The React app / the Space | `web/src/components/Event2021.jsx`, `web/src/App.jsx` |
| The builders (`--satellite`, `--front-aois`, `--hero-*`) | `scripts/build_policy_tool.py`, `scripts/export_event_web.py` |
| The numbers | `data/processed/event_2021_*.parquet` (output of `src/event2021.py`) |

The tool and the web app share `src/policy_tool.py` for every figure and
formatted string, so a fix there lands in both.

## Rules (from CLAUDE.md)

- Run `python -m pytest -q` after any change; it must stay green. A numbers
  guard checks that every figure in the docs matches the code/artifacts.
- All code, comments and commit messages in English.
- Prove a bug before fixing it; measure before and after.
- No secrets in the repo (only in a gitignored `.env`). Do not commit
  `docs/perso/`, `.env`, or GISCO geometry.
- Branch off `main`; do not commit straight to `main`.

## Do NOT put in the jury submission

The GitHub link, the personal Hugging Face link, and any real name — the
submitted files say "Team 9" only.
