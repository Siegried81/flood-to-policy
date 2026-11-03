# How this folder fits the repository

`team9/` is Team 9's own tool (FARI hackathon 2026), vendored here as source. It
is not my work; the rest of this repository is. See the team's own
[`README.md`](README.md) for what the tool does and how to build it.

**State vendored:** the `demo-scenarios` branch, commit *"Unify maps into four
presentation scenes"* — the version that merges the old exposure and priority
maps into one page with four scenes. Upstream:
`https://github.com/YkSalma/fari-hackathon-2026.git`.

**The generated map is not here.** `map.py` writes a ~37 MB self-contained
`flood_map.html`. The one that ships is deployed at
[`web/public/team9/flood_map.html`](../web/public/team9/flood_map.html); it is the
only file the website serves. Rebuild it from this source with:

```bash
cd team9
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python map.py            # rebuild flood_map.html from the caches
```

Regenerating needs the challenge data caches (EMS / OBAT / GHS-POP / EFAS, several
GB) that `map.py --refresh` downloads; those are not vendored. The small data
outputs the tool exports (`priority_ranking.csv`, `shelter_candidates.csv` and
`.geojson`, `evidence/register.json`) are kept.

**Tests.** Team 9's suite lives in `team9/tests/` and needs node, scipy and a
headless browser (some tests reach the network). Run it from inside `team9/`:
`python -m pytest`. This kit's own `pytest.ini` sets `testpaths = tests`, so a
bare `pytest` at the repository root does not collect it.
