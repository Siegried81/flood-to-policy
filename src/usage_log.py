"""Reading and writing the local AI log (`docs/ai_usage_log.md`, kept out of the repository) - the running note the Annex 7 AI sheet is compiled from.

Two small operations that both exist because this one file has **two readers**
with different capabilities, and code that treats it as a plain Markdown blob
gets each of them wrong:

- In the repository it is a document with a table and closing prose, and its
  relative links to its sibling docs are correct.
- Served by the Streamlit app it is a rendered string on an HTTP origin that has
  no `.md` files behind it, and the table is something a form appends to while
  the app is running.

They live here rather than in `app/streamlit_app.py` so a test can exercise them
without executing the app: importing the script runs the whole page, which reads
the real `data/processed/` tables - green on a machine that has them and red
on one that does not.
"""

from __future__ import annotations

import re
from pathlib import Path

#: `[text](something.md)` and `[text](../docs/something.md#anchor)`, but never an
#: `http(s)` target, which a reader with a network can follow.
_RELATIVE_DOC_LINK = re.compile(r"\[([^\]]+)\]\((?!https?:)[^)]*\.md[^)]*\)")


#: The columns the Streamlit log form writes, in order.
LOG_COLUMNS = ["Time", "Tool / model", "Task", "What a human checked", "Outcome"]


def table_row(cells: list[str]) -> str:
    """One Markdown table row from free-text cells typed into the log form.

    A `|` ends a cell and a newline ends the row, so either one typed into a
    field ("Claude | Haiku") shifted every later field or broke the table. The
    pipe is escaped and line breaks become spaces, so what was typed is what
    the row shows.
    """
    cleaned = [" ".join(str(c).split()).replace("|", "\\|") for c in cells]
    return "| " + " | ".join(cleaned) + " |\n"


def append_row(path: Path, row: str) -> None:
    """Insert `row` after the LAST table row, not at the end of the file.

    The log ends with prose - the closing section naming what the AI was not
    allowed to decide - so appending to the file put the new entry below it,
    outside the table, where Markdown renders it as a paragraph of text with
    pipe characters in it rather than as a row of the log.

    The log is kept out of the repository, so a fresh clone has none: the first
    entry creates it with the form's header instead of failing on a missing file.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# AI usage log\n\n" + table_row(LOG_COLUMNS)
                        + "|" + "---|" * len(LOG_COLUMNS) + "\n", encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    last = max(
        (i for i, line in enumerate(lines) if line.lstrip().startswith("|")),
        default=len(lines) - 1,
    )
    if not lines[last].endswith("\n"):
        lines[last] += "\n"
    lines.insert(last + 1, row)
    path.write_text("".join(lines), encoding="utf-8")


def unlink_relative_docs(text: str) -> str:
    """Drop Markdown links whose target is a sibling `.md` file, keeping the text.

    In the repository `[`docs/decisions.md`](decisions.md)` is right. Served by
    Streamlit the same link resolves against the app's own origin, and the dev
    server answers an unknown path with the app shell - so clicking it opened a
    second copy of the whole app in a new tab. Rewriting the targets to absolute
    GitHub URLs is not the fix either: the kit has to work with the Wi-Fi off,
    and a dead link is not better than no link. The link text in this log already
    names the file, so dropping the link loses nothing a reader needs.
    """
    return _RELATIVE_DOC_LINK.sub(r"\1", text)
