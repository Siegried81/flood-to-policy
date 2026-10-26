"""Tests for the TOON encoder.

The encoder feeds an LLM prompt whose output goes into a policy brief, so the
failure mode that matters is a value silently changing meaning between the table
and the prompt - a commune code read as a number, a comma splitting a row.
"""

import pandas as pd
import pytest

import builtins
from unittest.mock import patch

from src.toon_io import fit_rows, flatten, to_toon, token_report


def test_quotes_ambiguous_and_special_strings():
    """A NIS code must stay text, and a comma in a name must not split the row."""
    df = pd.DataFrame(
        {"nis_code": ["62063"], "commune": ["Liege, Ville"], "exposed_pop": [1234.0]}
    )
    assert to_toon(df, "t") == 't[1]{nis_code,commune,exposed_pop}:\n  "62063","Liege, Ville",1234'


def test_integers_do_not_gain_a_decimal_point():
    """A population count written as 1234.0 reads as a measurement, not a count."""
    df = pd.DataFrame({"pop": [1234.0], "share": [0.333333333]})
    assert to_toon(df, "t").endswith("1234,0.3333")


def test_null_and_bool_render_as_bare_tokens():
    df = pd.DataFrame({"a": [None], "b": [True]})
    assert to_toon(df, "t") == "t[1]{a,b}:\n  null,true"


def test_header_carries_the_row_count():
    """The count is what lets the model notice a truncated table."""
    df = pd.DataFrame({"a": [1, 2, 3]})
    assert to_toon(df, "exposure").startswith("exposure[3]{a}:")


def test_flatten_nested_and_drops_geometry():
    out = flatten([{"id": 1, "risk": {"pop": 10, "infra": 2}}])
    assert list(out.columns) == ["id", "risk_pop", "risk_infra"]


def test_flatten_rejects_lists():
    """A list breaks the uniform-table assumption; exploding it is the caller's call."""
    with pytest.raises(ValueError, match="explode"):
        flatten([{"id": 1, "tags": ["a", "b"]}])


def test_toon_is_smaller_than_json_on_a_realistic_table():
    """The saving is the claim made to the jury, so it is pinned by a test."""
    df = pd.DataFrame(
        {
            "nis_code": [f"6206{i}" for i in range(50)],
            "commune": [f"Commune {i}" for i in range(50)],
            "return_period": [100] * 50,
            "exposed_pop": list(range(50)),
        }
    )
    report = token_report(df, "exposure")
    if not report.get("available", True):
        # tiktoken is this module's only compiled dependency and it cannot load
        # under every application-control policy. The ratio claim is what the
        # test exists for, so it is skipped rather than weakened - and the
        # unavailable shape is asserted by its own test below.
        pytest.skip(report["reason"])
    assert report["saving_pct"] > 25
    assert report["toon_tokens"] < report["json_tokens"]


def test_an_unavailable_tokenizer_reports_itself_instead_of_estimating():
    """The whole point of the lazy import: a missing tokenizer must not take the
    app down, and must not quietly hand back a guess that reads as a measurement.

    A chars/4 estimate would arrive in the same keys and be quoted in the brief
    as a measured saving, so the counts come back None with a reason instead.
    """
    import src.toon_io as T

    df = pd.DataFrame({"commune": ["Liege"], "exposed_pop": [1]})
    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name == "tiktoken":
            raise ImportError("DLL load failed while importing _tiktoken")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", _blocked):
        report = T.token_report(df, "exposure")

    assert report["available"] is False
    assert report["toon_tokens"] is None
    assert report["json_tokens"] is None
    assert report["saving_pct"] is None
    assert "tiktoken" in report["reason"]


def test_a_tokenizer_that_cannot_fetch_its_table_reports_itself_too():
    """`tiktoken.get_encoding` downloads the BPE table on first use. On a clean
    machine with the network unplugged the import succeeds and that call raises,
    which took `/api/draft` and the draft tab down while every offline check was
    green - measured 2026-10-10, 12 tests failing through this one line. Same
    unavailable shape as a blocked import, same reason key."""
    import src.toon_io as T

    df = pd.DataFrame({"commune": ["Liege"], "exposed_pop": [1]})
    tiktoken = pytest.importorskip("tiktoken")
    with patch.object(tiktoken, "get_encoding", side_effect=OSError("Tunnel connection failed: 403")):
        report = T.token_report(df, "exposure")
    assert report["available"] is False
    assert report["toon_tokens"] is None and report["saving_pct"] is None
    assert "403" in report["reason"]


def test_encoding_a_table_never_needs_the_tokenizer():
    """`to_toon` is what both entry points import; it must not depend on a
    compiled extension, or neither UI can start."""
    import src.toon_io as T

    df = pd.DataFrame({"commune": ["Liege"], "exposed_pop": [1]})
    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name == "tiktoken":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", _blocked):
        assert "exposure" in T.to_toon(df, "exposure")


# --- the prompt budget ----------------------------------------------------------

def test_fit_rows_returns_the_whole_frame_when_it_already_fits():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    assert len(fit_rows(df, "t", 10_000)) == 2


def test_fit_rows_trims_to_the_budget_and_keeps_the_order():
    """The caller sorts, so the head has to stay the head: trimming from the
    middle would silently drop the regions the ranking put second."""
    df = pd.DataFrame({"nuts_id": [f"X{i:04d}" for i in range(500)], "v": range(500)})
    out = fit_rows(df, "exposure", 400)
    assert 0 < len(out) < 500
    assert len(to_toon(out, "exposure")) <= 400
    assert out["nuts_id"].tolist() == df["nuts_id"].tolist()[: len(out)]
    # And one more row would not have fitted - the trim is maximal, not timid.
    assert len(to_toon(df.head(len(out) + 1), "exposure")) > 400


def test_fit_rows_is_measured_on_the_encoding_not_on_a_row_count():
    """A row count cannot hold a budget: add a column and the same number of rows
    encodes larger. This is why the exposure prompt broke when the table grew."""
    narrow = pd.DataFrame({"a": range(200)})
    wide = pd.DataFrame({f"c{i}": range(200) for i in range(12)})
    assert len(fit_rows(narrow, "t", 600)) > len(fit_rows(wide, "t", 600))


def test_a_budget_too_small_for_the_header_returns_nothing_rather_than_raising():
    """The prompt is then a question with no table, which is a worse answer and
    not a crash - and the caller is the one that knows whether to go on."""
    df = pd.DataFrame({"nuts_id": ["AA", "BB"], "value": [1, 2]})
    assert fit_rows(df, "exposure", 5).empty


def test_an_empty_frame_comes_back_empty():
    assert fit_rows(pd.DataFrame(), "t", 1000).empty
