"""`scripts/docs_numbers.py`: the docs' numbers are derived, never typed.

Why this file exists. The test count was corrected by hand seven times in one
day and a stale copy still survived for hours. The one test here that matters is
`test_no_marked_block_in_the_repo_is_stale`: it runs the script's `--check`
against the real docs, so the suite goes red the next time a number is typed
instead of written by the script. The others pin the parsers on small fixtures
so a failure of the first one points at a doc and not at a regex.

No network anywhere: the facts come from a subprocess `pytest --collect-only`,
a YAML file and a parquet on disk.
"""

import pytest

from scripts import docs_numbers as dn


@pytest.fixture(scope="module")
def facts():
    """Measured once per module: the collect-only subprocess costs a second or two."""
    return dn.measure()


def test_parse_collected_trusts_only_the_summary_line():
    out = "tests/test_x.py::test_collected_once\n\n513 tests collected in 1.09s\n"
    assert dn.parse_collected(out) == 513
    assert dn.parse_collected("1 test collected in 0.01s") == 1
    with pytest.raises(RuntimeError):
        dn.parse_collected("no tests ran")


def test_count_sources_counts_entries_not_keys():
    doc = {
        "geodata": [
            {"id": "a", "url": "u", "verified": "2026-10-06", "licence": "CC-BY-4.0"},
            {"id": "b", "url": "u", "verified": None},             # explicit null
            {"id": "c", "url": "u", "verified": "2026-10-06 (landing page only)",
             "licence": ""},                                        # empty licence
        ],
        "documents": [{"id": "d", "url": "u"}, {"url": "no id, not declared"}],
        "notes": "a scalar group is ignored",
    }
    assert dn.count_sources(doc) == {
        "sources_declared": 4, "sources_verified": 2, "sources_licensed": 1}


def test_rewrite_replaces_only_the_block_and_reports_unknown_keys():
    f = {"tests_collected": 1345, "sources_declared": 42}
    text = ("keep <!-- numbers:tests_collected -->0<!-- /numbers --> this\r\n"
            "and <!-- numbers:sources_declared -->42<!-- /numbers --> too\n"
            "and <!-- numbers:nope -->7<!-- /numbers --> untouched\n")
    new, stale = dn.rewrite(text, f)
    assert new == ("keep <!-- numbers:tests_collected -->1,345<!-- /numbers --> this\r\n"
                   "and <!-- numbers:sources_declared -->42<!-- /numbers --> too\n"
                   "and <!-- numbers:nope -->7<!-- /numbers --> untouched\n")
    assert stale == [("tests_collected", "0", "1,345"), ("nope", "7", "<unknown key>")]
    assert dn.rewrite("no markers at all", f) == ("no markers at all", [])


def test_measured_facts_have_the_expected_shape(facts):
    assert set(facts) == {"tests_collected", "sources_declared", "sources_verified",
                          "sources_licensed", "nuts3_regions"}
    assert facts["tests_collected"] > 0
    assert (facts["sources_declared"] >= facts["sources_verified"]
            >= 0 and facts["sources_declared"] >= facts["sources_licensed"])
    assert facts["nuts3_regions"] == "unbuilt" or facts["nuts3_regions"] > 0


def test_no_marked_block_in_the_repo_is_stale(facts, capsys):
    """The guard: a hand-typed number in any default file fails the suite here.

    Repair is `scripts/docs_numbers.py --write`, never editing the digit.
    """
    for name in dn.DEFAULT_FILES:
        path = dn.ROOT / name
        assert path.exists(), name
        _, stale = dn.rewrite(path.read_bytes().decode("utf-8"), facts)
        assert stale == [], f"{name} is stale; run scripts/docs_numbers.py --write"


def test_the_two_files_this_script_owns_carry_a_marker():
    """Without a marker the guard above passes vacuously, which is not a guard."""
    for name in ("requirements.txt", "docs/technical_deep_dive.md"):
        assert "<!-- numbers:tests_collected -->" in (dn.ROOT / name).read_text(encoding="utf-8")


def test_write_is_idempotent_and_check_catches_a_stale_copy(facts, tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    doc.write_bytes(b"n = <!-- numbers:tests_collected -->0<!-- /numbers -->\nend\n")
    monkeypatch.setattr(dn, "ROOT", tmp_path)
    monkeypatch.setattr(dn, "measure", lambda: facts)
    assert dn.main(["--check", "doc.md"]) == 1
    assert dn.main(["--write", "doc.md"]) == 0
    once = doc.read_bytes()
    assert once == f"n = <!-- numbers:tests_collected -->{dn.render(facts['tests_collected'])}<!-- /numbers -->\nend\n".encode()
    assert dn.main(["--write", "doc.md"]) == 0
    assert doc.read_bytes() == once
    assert dn.main(["--check", "doc.md"]) == 0


def test_json_mode_prints_the_facts(facts, monkeypatch, capsys):
    monkeypatch.setattr(dn, "measure", lambda: facts)
    assert dn.main(["--json"]) == 0
    assert '"tests_collected"' in capsys.readouterr().out


def test_an_unmeasurable_fact_is_left_as_written_not_called_stale():
    """The CI failure: `nuts3_regions` reads the frozen exposure table, the runner
    has no `data/`, so the fact came back 'unbuilt' and `--check` called the
    doc's 1,345 stale against it. Not measurable here is not wrong; the block
    stays as written and is not reported.
    """
    text = "x <!-- numbers:nuts3_regions -->1,345<!-- /numbers --> y"
    out, stale = dn.rewrite(text, {"nuts3_regions": dn.UNMEASURABLE})
    assert out == text
    assert stale == []


def test_check_passes_on_the_real_docs_without_the_frozen_table(monkeypatch, tmp_path, capsys):
    """The same, end to end, in the shape the runner sees: the exposure table
    absent. `--check` over the default files must exit 0 and say why the one
    fact was skipped, rather than fail the suite."""
    monkeypatch.setattr(dn, "EXPOSURE", tmp_path / "absent.parquet")
    assert dn.main(["--check"]) == 0
    err = capsys.readouterr().err
    assert "nuts3_regions not measurable here" in err
    assert "numbers: clean" in err
