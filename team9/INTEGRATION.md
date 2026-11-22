# How this folder fits the repository

`team9/` is Team 9's own tool (FARI hackathon 2026), vendored as source; the rest of the
repository is not theirs. What the tool does and how to build it: [`README.md`](README.md).
Vendored from the `demo-scenarios` branch of `github.com/YkSalma/fari-hackathon-2026`
(commit "Unify maps into four presentation scenes").

**The map is the one generated HTML kept in git.** `map.py` writes a 37 MB `flood_map.html`;
only the latest build is kept, at `web/public/team9/flood_map.html`, in Git LFS (`git lfs pull`
after cloning). Replace that file when the map is rebuilt; older builds are not kept. Regenerating needs the challenge data caches (EMS, OBAT,
GHS-POP, EFAS; several GB) that `map.py --refresh` reads from Google Cloud Storage. The small
exports are kept: `priority_ranking.csv`, `shelter_candidates.csv`, `evidence/register.json`
(`shelter_candidates.geojson` is a gitignored output of `shelters.py`).

**Tests.** `team9/tests/` is part of the root suite (`testpaths` in `pytest.ini`). Browser
tests skip without a built `flood_map.html` and playwright; tests that need Google Cloud
skip without credentials; the allocation check needs scipy (`requirements-test.txt`).
