"""The docs cite docstrings by name; every cited name must exist.

Why this file exists. `docs/limitations.md` sends the reader to a docstring as
its evidence ("[`src/svgmap.py`](../src/svgmap.py) `render` docstring"), and a
rename in the code leaves the citation pointing at nothing without any test
noticing. This walks every such citation in `docs/*.md`, parses the cited
module with `ast` (no import, so no heavy dependency loads) and asserts the
function or class is defined there.

No network, no data files: only the repository's own Markdown and Python.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# A Markdown link to a source file, then a backticked name, then "docstring".
# Whitespace between the parts may include a line break, as the docs wrap.
CITATION = re.compile(
    r"\]\(\.\./(?P<path>(?:src|api|app|scripts)/[\w/]+\.py)\)\s+`(?P<name>\w+)`\s+docstring"
)


def citations(text: str) -> list[tuple[str, str]]:
    """Every (source path, cited name) pair in one Markdown text."""
    return [(m["path"], m["name"]) for m in CITATION.finditer(text)]


def defined_names(path: Path) -> set[str]:
    """Names of every function and class defined anywhere in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return {node.name for node in ast.walk(tree) if isinstance(node, kinds)}


def all_doc_citations() -> list[tuple[str, str, str]]:
    """(doc file, source path, name) for every docstring citation in docs/."""
    found = []
    for doc in sorted((ROOT / "docs").glob("*.md")):
        for path, name in citations(doc.read_text(encoding="utf-8")):
            found.append((doc.name, path, name))
    return found


def test_citation_regex_reads_a_wrapped_citation():
    text = "see\n  [`src/svgmap.py`](../src/svgmap.py) `choropleth_svg`\n  docstring,"
    assert citations(text) == [("src/svgmap.py", "choropleth_svg")]


def test_citation_regex_ignores_a_module_docstring_citation():
    text = "[`src/basins.py`](../src/basins.py)\n  module docstring."
    assert citations(text) == []


def test_the_docs_cite_at_least_one_docstring():
    """Guards the regex: zero matches would make the test below pass vacuously."""
    assert all_doc_citations()


@pytest.mark.parametrize("doc,path,name", all_doc_citations())
def test_every_cited_docstring_exists(doc, path, name):
    source = ROOT / path
    assert source.is_file(), f"{doc} cites {path}, which does not exist"
    assert name in defined_names(source), f"{doc} cites `{name}` in {path}, which defines no such name"
