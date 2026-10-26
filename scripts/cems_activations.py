"""Summarise CEMS rapid-mapping flood activations by country and year.

One anonymous GET to the public dashboard API (url in config/sources.yaml,
`cems_rapid_mapping_activations`), cached to data/processed/cems_activations.json
so a re-run and the venue need no network. Writes
data/processed/cems_activations_by_country.csv and prints the table. The logic
is in `src/activations.py`; this script only wires it to disk and the terminal.

Run:

    python scripts/cems_activations.py            # use the cache when present
    python scripts/cems_activations.py --refresh  # fetch again
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import activations  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Ignore the cache and fetch again.")
    parser.add_argument("--out", type=Path, default=activations.SUMMARY)
    parser.add_argument("--cache", type=Path, default=activations.CACHE)
    args = parser.parse_args(argv)

    listed = activations.fetch(cache=args.cache, use_cache=not args.refresh)
    rows = activations.floods(listed)
    table = activations.by_country_year(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out, index=False)

    head = activations.headline(rows)
    print(f"{len(listed)} activations listed, {head['flood_activations']} floods "
          f"({head['eu27_flood_activations']} touching the EU-27), "
          f"{head['first_year']}-{head['last_year']}. Older activations "
          "(before EMSR656, March 2023) are not in the dashboard list.")
    print(table.to_string(index=False))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
