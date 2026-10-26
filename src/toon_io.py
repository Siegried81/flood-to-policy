"""Flatten tables and encode them as TOON (tabular form) for LLM prompts.

Why not a TOON library: for flat, uniform tables the tabular syntax is a few
lines. Fewer dependencies, and behaviour we control and can test - which matters
when the output feeds a prompt whose correctness we have to defend to a jury.

Why TOON at all: a 300-row exposure table costs roughly half the tokens of the
same table as JSON. On the day that is headroom for more context; in the brief it
is a concrete, measurable claim for the "efficient and responsible AI" section.
"""

from __future__ import annotations

import json
import numbers
import re

import pandas as pd

# tiktoken is imported lazily, inside `token_report`, and deliberately NOT here.
#
# It is this module's only compiled dependency and exactly one function needs it,
# but importing it at module scope made it a hard requirement of the whole file -
# and therefore of both entry points, because `app/streamlit_app.py` and
# `api/main.py` each import `to_toon` from here. On a machine whose Windows
# application-control policy refuses to load `_tiktoken.pyd`, that single import
# meant neither UI could start at all: the failure was an ImportError at launch,
# raised over a token count nobody had asked for yet.
#
# Encoding a table does not need a tokenizer; counting tokens does. Keeping the
# import where the need is lets the app run without it, and lets the count say it
# is unavailable instead of taking the app down with it.

# Strings needing quotes: a TOON delimiter or special char, edge whitespace, or empty.
_SPECIAL = re.compile(r'[,:"\n\\\[\]{}]|^\s|\s$|^$')
# Strings a reader would take for a number/bool/null. The Belgian NIS commune code
# "62063" is exactly this case: unquoted it becomes an integer, loses its leading
# zeros elsewhere in the set, and the brief can no longer be traced to a commune.
_AMBIGUOUS = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$|^(true|false|null)$")


def flatten(data: pd.DataFrame | list[dict]) -> pd.DataFrame:
    """Nested dicts to flat columns (risk.pop -> risk_pop).

    Geometry is dropped: a polygon is thousands of tokens of coordinates that an
    LLM can do nothing useful with.
    """
    if isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data.drop(columns="geometry", errors="ignore")).to_dict("records")
    df = pd.json_normalize(data, sep="_")
    # Fail fast: a list in a cell breaks the uniform-table assumption the format
    # rests on. Exploding it is a caller decision, not something to guess here.
    if df.map(lambda v: isinstance(v, list)).any().any():
        raise ValueError("List values found: explode them before encoding to TOON.")
    return df


def _cell(value) -> str:
    """Render one value as a TOON token. Shared by headers and rows."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "null"
    if isinstance(value, bool) or str(type(value)).endswith("bool_'>"):
        return "true" if bool(value) else "false"
    if isinstance(value, numbers.Number):
        as_float = float(value)
        # No "1234.0" for a population count, and no float noise at the 12th decimal.
        return str(int(as_float)) if as_float.is_integer() else str(round(as_float, 4))
    text = str(value)
    # json.dumps gives correct escaping; ensure_ascii=False keeps "Liege" readable
    # and costs fewer tokens than an escape sequence.
    if _SPECIAL.search(text) or _AMBIGUOUS.match(text):
        return json.dumps(text, ensure_ascii=False)
    return text


def to_toon(df: pd.DataFrame, name: str) -> str:
    """Encode a flat DataFrame as a TOON tabular array.

    Shape: `name[N]{col,col}:` then one indented row per record. The row count in
    the header is what lets the model notice a truncated table.
    """
    header = f"{name}[{len(df)}]{{{','.join(_cell(c) for c in df.columns)}}}:"
    rows = ("  " + ",".join(_cell(v) for v in row) for row in df.itertuples(index=False, name=None))
    return "\n".join([header, *rows])


def token_report(df: pd.DataFrame, name: str, encoding: str = "o200k_base") -> dict:
    """Compare TOON against JSON in tokens.

    tiktoken is OpenAI's tokenizer, so this is a proxy for any other model's count
    rather than an exact figure - but the ratio between the two encodings holds,
    and the ratio is the claim being made.

    When tiktoken cannot be loaded, every count comes back None with
    `available: False` and the reason, rather than an estimate. A chars-divided-by-
    four guess would land in the same keys and be quoted in the brief as a
    measured saving, which is precisely the kind of silent substitution this
    repo refuses elsewhere: "we could not measure" and "we measured" must not
    share a shape. Callers render the unavailable case; they do not crash on it.
    """
    try:
        import tiktoken

        # Inside the try on purpose. `get_encoding` downloads the BPE table from
        # OpenAI's blob storage the first time it is asked for, and caches it
        # under the system temp dir. On a fresh machine with the network
        # unplugged - the exact situation this kit is rehearsed for - the import
        # succeeds and THIS call raises, which would take the draft tab and
        # `/api/draft` down with an OSError over a count nobody asked for.
        enc = tiktoken.get_encoding(encoding)
    except Exception as exc:  # extension blocked, not installed, or BPE table not fetchable
        return {
            "toon_tokens": None,
            "json_tokens": None,
            "saving_pct": None,
            "available": False,
            "reason": f"tiktoken unavailable: {exc}",
        }
    toon_tokens = len(enc.encode(to_toon(df, name)))
    json_tokens = len(enc.encode(df.to_json(orient="records", force_ascii=False)))
    return {
        "toon_tokens": toon_tokens,
        "json_tokens": json_tokens,
        "saving_pct": round(100 * (1 - toon_tokens / json_tokens), 1),
        "available": True,
    }


def fit_rows(df: pd.DataFrame, name: str, max_chars: int) -> pd.DataFrame:
    """The longest head of `df` whose TOON encoding stays under `max_chars`.

    **Characters, not tokens, and deliberately.** `token_report` needs tiktoken,
    which Windows Smart App Control blocks on the development machine, so a
    token-budgeted prompt would be correct only where the tokenizer loads - and
    silently unbudgeted on the laptop that runs the demo. Measured 2026-10-08 on
    the real exposure table, TOON encodes at about 2.05 characters per token, so
    a character budget is a stable proxy and it is one that always works.

    **Why a budget exists at all.** The provider's ceiling is per minute, not per
    context: Groq answers HTTP 413 above 8,000 tokens per request for
    `openai/gpt-oss-120b` on the on-demand tier, while the model's own context is
    131k. A row count cannot respect that - a column added to the table moves the
    size and the cap stops holding - so the caller passes the budget it has left
    after the retrieved passages and the system prompt.

    Rows are taken in the order given, so the CALLER decides what matters: pass a
    frame already sorted by whatever the question is about. An empty frame, or a
    budget too small for even the header, comes back empty rather than raising -
    the prompt is then a question with no table, which is a worse answer and not
    a crash.
    """
    if df.empty:
        return df
    if len(to_toon(df, name)) <= max_chars:
        return df
    low, high = 0, len(df)
    while low < high:
        middle = (low + high + 1) // 2
        if len(to_toon(df.head(middle), name)) <= max_chars:
            low = middle
        else:
            high = middle - 1
    return df.head(low)
