"""Measure the facts the docs quote, and keep every marked copy of them current.

    .venv/Scripts/python.exe scripts/docs_numbers.py --json             # measure
    .venv/Scripts/python.exe scripts/docs_numbers.py --write [files]    # rewrite
    .venv/Scripts/python.exe scripts/docs_numbers.py --check [files]    # CI gate

Why this is a script and not a habit. The test count was corrected by hand seven
times in one day across four files, and one stale copy survived for hours. A
number typed into a doc is a copy, and copies rot; a number DERIVED from the
artefact at write time cannot. So each fact below is a function that reads the
artefact itself - never another doc - and the docs carry the value inside a
marked block that only this script edits:

    <!-- numbers:tests_collected -->513<!-- /numbers -->

`--write` replaces the text between the markers and leaves every other byte
alone, so a doc owner keeps the prose and gives up only the digit. `--check`
exits 1 and names each stale block, which is what makes the suite (and CI) fail
the next time someone types a number again. Files with no markers pass vacuously.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "config" / "sources.yaml"
EXPOSURE = ROOT / "data" / "processed" / "exposure.parquet"
DEFAULT_FILES = ("README.md", "requirements.txt", "docs/technical_deep_dive.md",
                 "docs/policy_answer.md")
BLOCK = re.compile(r"(<!-- numbers:(\w+) -->)(.*?)(<!-- /numbers -->)")


def parse_collected(output):
    """Return N from pytest's final 'N tests collected' line, or raise.

    `--collect-only -q` prints one node id per line and then the summary; only
    the summary is trusted, so a stray 'collected' in a test name cannot count.
    """
    found = re.findall(r"(\d+) tests? collected", output)
    if not found:
        raise RuntimeError("pytest printed no 'N tests collected' line")
    return int(found[-1])


def tests_collected():
    """Collect the suite with the interpreter running this script, without running it.

    sys.executable rather than 'python' because the ambient interpreter cannot
    import rasterio and would collect fewer tests - that is one of the ways a
    doc figure went wrong before.
    """
    proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                           "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    return parse_collected(proc.stdout)


def count_sources(doc):
    """Count declared / verified / licensed entries in a parsed sources.yaml.

    The file is top-level groups (geodata:, documents:, ...) each a list of
    entries. An entry is declared when it has an `id`; verified when `verified`
    is anything but null - the file uses `verified: null` as the explicit "not
    checked" marker, which is why a key count overstates it; licensed when
    `licence` holds a non-empty string. Counts are of entries, not of the files
    they expand to.
    """
    entries = [e for group in doc.values() if isinstance(group, list)
               for e in group if isinstance(e, dict) and "id" in e]
    return {
        "sources_declared": len(entries),
        "sources_verified": sum(e.get("verified") is not None for e in entries),
        "sources_licensed": sum(bool(str(e.get("licence") or "").strip()) for e in entries),
    }


def nuts3_regions():
    """Distinct NUTS3 ids in the frozen exposure table, or 'unbuilt' without one.

    Distinct ids rather than rows / 9: the return-period count is an input, and
    the region count must not inherit an assumption about it.
    """
    if not EXPOSURE.exists():
        return "unbuilt"
    import pandas as pd
    return int(pd.read_parquet(EXPOSURE, columns=["nuts_id"])["nuts_id"].nunique())


def measure():
    """Every fact, each re-derived from its artefact now."""
    facts = {"tests_collected": tests_collected()}
    facts.update(count_sources(yaml.safe_load(SOURCES.read_text(encoding="utf-8"))))
    facts["nuts3_regions"] = nuts3_regions()
    return facts


def render(value):
    """How a fact is written into prose: thousands-separated, as the docs already do."""
    return f"{value:,}" if isinstance(value, int) else str(value)


UNMEASURABLE = "unbuilt"


def rewrite(text, facts):
    """Return (new_text, stale) for one document: stale lists (key, old, new) per block.

    An unknown key is reported as stale and left untouched rather than erased,
    so a typo in a marker is loud instead of silently blanked.

    A fact that could not be measured here - `nuts3_regions` reads
    `data/processed/exposure.parquet`, and a checkout can lack it - is neither stale
    nor writable: the block is left as written and not reported. "Cannot check
    on this machine" and "wrong" are different claims, and the first run on the
    runner conflated them: `--check` called the doc's 1,345 stale against
    'unbuilt' and failed the suite on every machine without the frozen table.
    """
    stale = []

    def sub(m):
        key, old = m.group(2), m.group(3)
        if key not in facts:
            stale.append((key, old, "<unknown key>"))
            return m.group(0)
        if facts[key] == UNMEASURABLE:
            return m.group(0)
        new = render(facts[key])
        if old != new:
            stale.append((key, old, new))
        return f"{m.group(1)}{new}{m.group(4)}"

    return BLOCK.sub(sub, text), stale


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    mode = args[0] if args else "--json"
    files = [ROOT / f for f in (args[1:] or DEFAULT_FILES)]
    facts = measure()
    if mode == "--json":
        print(json.dumps(facts, indent=2))
        return 0
    if mode not in ("--write", "--check"):
        print(__doc__.split("\n\n")[0])
        return 2
    exit_code = 0
    for key, value in facts.items():
        if value == UNMEASURABLE:
            print(f"numbers: {key} not measurable here (artefact absent); "
                  "marked blocks left as written", file=sys.stderr)
    for path in files:
        raw = path.read_bytes()
        new, stale = rewrite(raw.decode("utf-8"), facts)
        for key, old, now in stale:
            print(f"{path.relative_to(ROOT)}: numbers:{key} says {old!r}, measured {now!r}")
        if stale and mode == "--write" and "<unknown key>" not in {s[2] for s in stale}:
            path.write_bytes(new.encode("utf-8"))
        elif stale:
            exit_code = 1
    print("numbers: clean" if exit_code == 0 else "numbers: stale", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
