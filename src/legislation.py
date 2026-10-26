"""The legal instruments the kit cites, read from `config/legislation.yaml`.

What it does: loads the registry into one `Instrument` per abbreviation and
renders a citation with the article and the EUR-Lex URL attached, e.g.
`cite("FD", "14(3)")` -> "Directive 2007/60/EC, Art. 14(3) —
https://eur-lex.europa.eu/eli/dir/2007/60/oj".

Why it exists: the brief's authority is a handful of articles, and until now
each one was prose in a doc with its CELEX and URL living somewhere else. The
registry gives every instrument one record; this module is the only reader, so
a doc, a slide or the app cite from the same place. `cite` refuses an article
the registry does not list, on purpose: a citation the registry cannot back is
exactly the drift the registry exists to prevent, and `tests/test_legislation.py`
holds `docs/policy_answer.md` to the same rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

REGISTRY = Path(__file__).resolve().parents[1] / "config" / "legislation.yaml"

#: The act types the registry may declare. "proposal" is there for a text the
#: docs cite that is not adopted yet (the Cloud and AI Development Act).
TYPES = frozenset(
    {"directive", "regulation", "decision", "recommendation", "communication",
     "staff-working-document", "proposal"}
)


@dataclass(frozen=True)
class Instrument:
    """One registry record. `articles` maps "14(3)" to its one-line note."""

    abbreviation: str
    short: str
    title: str
    celex: str
    type: str
    enacted: date | None
    in_force: date | None
    eurlex_url: str
    status: str
    verified: date | None
    articles: dict[str, str]


def load(path: Path = REGISTRY) -> dict[str, Instrument]:
    """Read the registry, keyed by abbreviation.

    Article keys are coerced to `str` because a bare `4:` in YAML is an int,
    and the docs cite "Article 4" - one key type keeps `cite` a plain lookup.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["instruments"]
    return {
        abbr: Instrument(
            abbreviation=abbr,
            articles={str(k): v for k, v in (rec.get("articles") or {}).items()},
            **{k: v for k, v in rec.items() if k != "articles"},
        )
        for abbr, rec in raw.items()
    }


def cite(abbr: str, article: str | None = None,
         registry: dict[str, Instrument] | None = None) -> str:
    """Render "<short>, Art. <article> — <eurlex_url>", or without the article.

    Raises `KeyError` for an instrument or an article the registry does not
    hold, rather than printing a citation nobody checked.
    """
    inst = (registry if registry is not None else load())[abbr]
    if article is None:
        return f"{inst.short} — {inst.eurlex_url}"
    if article not in inst.articles:
        raise KeyError(f"{abbr} Art. {article} is not in {REGISTRY.name}")
    return f"{inst.short}, Art. {article} — {inst.eurlex_url}"
