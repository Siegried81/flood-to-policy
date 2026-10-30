"""The case notebook reproduces the pipeline, checked automatically.

The notebook (`docs/perso/case_notebook_v2.ipynb`) re-applies the July 2021
method live on the data bucket and freezes its three border places' figures to
`outputs/frozen_numbers.csv`. The pipeline (`src/event2021.py`) writes the same
figures to `event_2021_hazard`. This test asserts the two coincide, so the
tool's "reproduced independently in the case notebook" claim is kept honest.

Both files are gitignored build outputs (one reads the bucket, the other reads
3 GB of local rasters), so the test runs where they are built and skips on the
data-less CI. No network: it only reads two local CSVs.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "docs" / "perso" / "outputs" / "frozen_numbers.csv"
HAZARD = ROOT / "data" / "processed" / "event_2021_hazard.csv"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.skipif(not (FROZEN.exists() and HAZARD.exists()),
                    reason="frozen_numbers.csv or event_2021_hazard.csv not built here")
def test_notebook_frozen_numbers_match_the_pipeline():
    """Every frozen row must equal the pipeline's row for the same product and return period."""
    frozen = _rows(FROZEN)
    assert frozen, "frozen_numbers.csv is empty"
    pipeline = {(r["product_id"], int(float(r["return_period"]))): r for r in _rows(HAZARD)}
    for row in frozen:
        key = (row["product_id"], int(float(row["return_period"])))
        assert key in pipeline, f"{key} is frozen in the notebook but missing from the pipeline table"
        p = pipeline[key]
        # Residents reached and residents outside the map, to the whole person.
        assert round(float(row["residents_reached"])) == round(float(p["residents_observed"]))
        assert round(float(row["residents_outside_map"])) == round(float(p["residents_outside_map"]))
        # The share the hero quotes, to six decimals.
        assert abs(float(row["share_outside_map"]) - float(p["share_residents_outside_map"])) < 1e-6
