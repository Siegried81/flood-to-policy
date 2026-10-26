"""Tests for the legislation registry.

The one that matters is the drift test: every article of Directive 2007/60/EC
that `docs/policy_answer.md` cites must be listed in the registry, with its
paragraph where the doc gives one. The doc is the brief's spine and the
registry is where its citations get a CELEX and a URL; either moving without
the other is how a brief ends up citing an article nobody can look up.

The parse assumes every "Article N" in that doc is an article of the Floods
Directive, which is true today - the doc names no other instrument by article.
If that changes, scope the regex rather than loosening the assertion.

No network: the registry is a file, and `verified` is a recorded date, not a
live check.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from src import legislation
from src.legislation import TYPES, cite, load

ROOT = Path(__file__).resolve().parents[1]
POLICY_ANSWER = ROOT / "docs" / "policy_answer.md"

CELEX = re.compile(r"^[0-9]{5}[A-Z]{1,2}[0-9]{4}(\([0-9]+\))?$")
STATUSES = {"in_force", "in_force_amended", "non_binding", "proposal"}

#: "Article 14(4)", "Art. 8(5)", "Articles 14 to 16" (the first number only),
#: "Article 5". The paragraph is optional and kept when present.
ARTICLE = re.compile(r"\bArt(?:icle|\.)s?\s+(\d+)(?:\((\d+)\))?")

#: The calendar table cites "14(1)" as a bare cell under an "Article" column,
#: which the prose regex cannot see; this reads such a cell on its own.
CELL = re.compile(r"^\s*(\d+)(?:\((\d+)\))?\s*$")


def cited_articles(text: str) -> set[str]:
    """Every article the doc cites, in prose or in a table with an Article column."""
    found = {f"{n}({p})" if p else n for n, p in ARTICLE.findall(text)}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if "Article" not in cells:
            continue
        col = cells.index("Article")
        for row in lines[i + 2:]:
            if not row.startswith("|"):
                break
            m = CELL.match(row.strip().strip("|").split("|")[col])
            if m:
                found.add(f"{m[1]}({m[2]})" if m[2] else m[1])
    return found


@pytest.fixture(scope="module")
def registry():
    return load()


def test_the_registry_loads_with_every_field_well_formed(registry):
    assert registry, "empty registry"
    for abbr, inst in registry.items():
        assert inst.abbreviation == abbr
        assert CELEX.match(inst.celex), f"{abbr}: celex {inst.celex!r}"
        assert inst.eurlex_url.startswith("https://eur-lex.europa.eu/"), abbr
        assert inst.type in TYPES, f"{abbr}: type {inst.type!r}"
        assert inst.status in STATUSES, f"{abbr}: status {inst.status!r}"
        assert isinstance(inst.enacted, date), f"{abbr}: enacted {inst.enacted!r}"
        assert inst.in_force is None or isinstance(inst.in_force, date), abbr
        assert inst.verified is None or isinstance(inst.verified, date), abbr
        assert inst.short and inst.title, abbr
        for key, note in inst.articles.items():
            assert isinstance(key, str) and note.strip(), f"{abbr}: article {key!r}"


def test_a_binding_act_in_force_has_a_date_and_a_non_binding_one_has_none(registry):
    for abbr, inst in registry.items():
        if inst.status.startswith("in_force"):
            assert inst.in_force is not None, abbr
        else:
            assert inst.in_force is None, abbr


def test_every_floods_directive_article_the_answer_cites_is_in_the_registry(registry):
    text = POLICY_ANSWER.read_text(encoding="utf-8")
    cited = cited_articles(text)
    assert {"14(1)", "14(2)", "14(3)"} <= cited, "the calendar table was not read"
    missing = sorted(cited - set(registry["FD"].articles), key=lambda s: (int(s.split("(")[0]), s))
    assert not missing, f"cited in policy_answer.md but not in legislation.yaml: {missing}"


def test_the_article_14_deadlines_are_the_directive_s_own_words(registry):
    arts = registry["FD"].articles
    assert "22 December 2018 and every six years thereafter" in arts["14(1)"]
    assert "22 December 2019 and every six years thereafter" in arts["14(2)"]
    assert "22 December 2021 and every six years thereafter" in arts["14(3)"]


def test_cite_renders_the_short_name_the_article_and_the_eli_url(registry):
    assert cite("FD", "14(3)", registry) == (
        "Directive 2007/60/EC, Art. 14(3) — https://eur-lex.europa.eu/eli/dir/2007/60/oj"
    )
    assert cite("FD", registry=registry) == (
        "Directive 2007/60/EC — https://eur-lex.europa.eu/eli/dir/2007/60/oj"
    )


def test_cite_refuses_an_article_or_an_instrument_the_registry_lacks(registry):
    with pytest.raises(KeyError):
        cite("FD", "99", registry)
    with pytest.raises(KeyError):
        cite("NOPE", registry=registry)


def test_cite_without_a_registry_reads_the_file_on_disk(monkeypatch):
    calls = []
    real = legislation.load
    monkeypatch.setattr(legislation, "load", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert cite("FD", "8(5)").startswith("Directive 2007/60/EC, Art. 8(5)")
    assert calls == [1]
