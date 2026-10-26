"""Freeze the Europe view's API answers into files a static build can serve.

The React Europe view reads `/api/meta`, `/api/exposure`, `/api/context` and
`/api/vulnerability`. A static Hugging Face Space has no Python behind it, so
this script asks the real API (in-process, through FastAPI's test client) and
writes its answers to `web/public/europe/`. The page then reads the same JSON it
would have received from the server: one code path computes every figure, and
the static demo cannot drift from the local app.

Three choices here are load-bearing:

* **Every answer is the API's own.** Nothing is recomputed here; a change to a
  route shows up in the static build at the next export.
* **The context table is cut to the columns the Context tab draws.** The full
  answer is 12.5 MB, most of it per-member climate columns no panel shows.
* **The vulnerability index is precomputed for every indicator subset, every
  return period, at the panel's default perturbation (0.3) and top 10.** The
  index needs the Monte Carlo sensitivity in `src/vulnerability.py`; porting it
  to JavaScript would be a second implementation to keep in step. Three
  indicators make seven subsets, so the table is small. Other settings answer
  with a message that says to run the app locally.

No geometry is written: the region polygons are GISCO's, which a public
repository cannot pass on (`data/processed/DATA_NOTICE.md`). The static page
fetches them from GISCO in the viewer's browser instead (`web/src/api.js`).
The output folder is gitignored and rebuilt before every static build.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "web" / "public" / "europe"

#: Defaults of `VulnerabilityPanel.jsx`; the static build answers these only.
PERTURBATION = 0.3
TOP_N = 10

#: Context columns the Context tab reads (`ContextPanel.jsx`), as patterns so a
#: new climate period or built-up return period is kept without editing this.
CONTEXT_KEEP = re.compile(
    r"^(nuts_id|lau_id"
    r"|change_pct_ensemble_(median|min|max)_.+"
    r"|ensemble_(robust_on_sign|agrees_on_sign|size_uncertain)_.+"
    r"|built_share_exposed_rp\d+|exposed_built_m2_rp\d+|built_total_m2"
    r"|apsfr_.+|shared_.+|basin_countries_max)$"
)


def subset_key(indicators) -> str:
    """The lookup key of one indicator subset, independent of click order."""
    return "+".join(sorted(indicators))


def _get(client, path: str) -> dict:
    resp = client.get(path)
    resp.raise_for_status()
    return resp.json()


def export(out: Path = OUT) -> dict[str, int]:
    """Write every file the static Europe view reads; return bytes per file."""
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, object] = {}

    meta = _get(client, "/api/meta")
    # The static page draws the map from GISCO directly, and approving needs a
    # server that does not exist here.
    meta.update(has_geometry=True, approve_token_required=False, static=True)
    files["meta.json"] = meta

    for period in meta["return_periods"]:
        files[f"exposure_rp{period}.json"] = _get(client, f"/api/exposure?return_period={period}")

    context = _get(client, "/api/context")
    context["rows"] = [
        {k: v for k, v in row.items() if CONTEXT_KEEP.match(k)} for row in context["rows"]
    ]
    files["context.json"] = context

    indicators = meta["indicators"]
    subsets = [
        list(combo)
        for size in range(1, len(indicators) + 1)
        for combo in itertools.combinations(indicators, size)
    ]
    for period in meta["return_periods"]:
        answers = {}
        for chosen in subsets:
            resp = client.post("/api/vulnerability", json={
                "indicators": chosen,
                "perturbation": PERTURBATION,
                "top_n": TOP_N,
                "return_period": period,
            })
            resp.raise_for_status()
            answers[subset_key(chosen)] = resp.json()
        files[f"vulnerability_rp{period}.json"] = {
            "perturbation": PERTURBATION, "top_n": TOP_N, "answers": answers,
        }

    sizes = {}
    for name, body in files.items():
        path = out / name
        path.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")
        sizes[name] = path.stat().st_size
    return sizes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    sizes = export(args.out)
    total = sum(sizes.values())
    print(f"{args.out}: {len(sizes)} files, {total / 1e6:.1f} MB")
    for name, size in sorted(sizes.items()):
        print(f"  {name}: {size / 1e3:.0f} kB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
