"""Tests for scripts/check_offline_readiness.py.

Every check is exercised against a temporary data tree rather than the real one,
because the real one changes under us: `src.fetch` is downloading into it while
this suite runs, so a test that asserted "11 files present" would be wrong by
lunchtime. The declared-source list still comes from the actual
`config/sources.yaml` - that is the point of the re-rooting in
`declared_targets`, and it keeps the test honest about the naming rule the
fetcher really uses.

No HTTP, anywhere: the only network call the script can make is the Ollama probe,
and `_ollama_tags` is replaced in every test that reaches it. A test that let that
call through would pass or fail depending on whether Ollama happened to be
running, which is exactly the ambiguity the script exists to remove.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_offline_readiness as readiness  # noqa: E402


# --- helpers ----------------------------------------------------------------


def _write(path: Path, payload: str = "x" * 10) -> Path:
    """Create a file and the folders above it, so a test reads as one line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _manifest(data_dir: Path, entries: list[dict]) -> Path:
    return _write(data_dir / "raw" / "manifest.json", json.dumps(entries))


# --- sizes and path re-rooting ----------------------------------------------


@pytest.mark.parametrize(
    "size, expected",
    [(0, "0 B"), (512, "512 B"), (1536, "1.5 KiB"), (5 * 1024**2, "5.0 MiB"),
     (2 * 1024**3, "2.0 GiB")],
)
def test_human_sizes(size, expected):
    assert readiness._human(size) == expected


def test_relocate_accepts_the_three_roots_this_tree_lives_under():
    """A Windows path, the WSL mount that ran the download, and the container path.

    All three describe the same file; the check has to recognise it from whichever
    one of them it is standing in.
    """
    target = Path("/tmp/kit/data")
    for recorded in (
        r"D:\Users\x\flood-policy-kit\data\raw\scrape\ai_act.html",
        "/mnt/d/Users/x/flood-policy-kit/data/raw/scrape/ai_act.html",
        "/app/data/raw/scrape/ai_act.html",
    ):
        assert readiness._relocate(recorded, target) == target / "raw/scrape/ai_act.html"


def test_relocate_returns_none_when_there_is_no_data_segment():
    assert readiness._relocate("/somewhere/else/ai_act.html", Path("/tmp/kit/data")) is None


# --- declared files ---------------------------------------------------------


def test_declared_targets_follow_the_fetcher_naming_rule(tmp_path):
    """Paths must be <data>/raw/<access>/<id><suffix>, as `fetch._target_path` says."""
    targets = readiness.declared_targets(tmp_path)
    assert targets, "config/sources.yaml declared nothing fetchable"
    for source_id, access, path in targets:
        assert access in {"download", "scrape"}
        assert path.is_relative_to(tmp_path / "raw" / access)
    ids = {source_id for source_id, _, _ in targets}
    assert "ai_act" in ids  # a scraped policy source
    assert any(i.startswith("jrc_flood_hazard/") for i in ids)  # a multi-file entry


def test_empty_tree_fails_and_names_what_is_absent(tmp_path):
    rows, checks = readiness.check_declared_files(tmp_path)
    disk = next(c for c in checks if c.name == "declared files on disk")
    assert disk.status == "FAIL"
    assert f"0/{len(rows)} present" in disk.detail
    assert disk.fix  # a failure with no next action is not actionable


def test_present_file_is_sized_and_counted(tmp_path):
    source_id, _, path = next(
        t for t in readiness.declared_targets(tmp_path) if t[0] == "ai_act"
    )
    _write(path, "y" * 2048)
    rows, checks = readiness.check_declared_files(tmp_path)
    row = next(r for r in rows if r["id"] == source_id)
    assert row["size"] == 2048
    assert "2.0 KiB" in next(c for c in checks if c.name == "declared files on disk").detail


def test_zero_byte_file_counts_as_missing(tmp_path):
    """`fetch._fetch_one` skips any non-empty file, so an empty one is invisible to a re-run."""
    _, _, path = next(t for t in readiness.declared_targets(tmp_path) if t[0] == "ai_act")
    _write(path, "")
    _, checks = readiness.check_declared_files(tmp_path)
    disk = next(c for c in checks if c.name == "declared files on disk")
    assert disk.status == "FAIL"
    assert "1 empty" in disk.detail


def test_a_rejection_page_on_disk_is_not_present(tmp_path):
    """"Non-empty" is satisfied by a WAF page. The checker applies the fetcher's
    own body check, so the row says why and the verdict is a FAIL with the same
    fix as a missing file."""
    source_id, _, path = next(
        t for t in readiness.declared_targets(tmp_path) if t[0] == "ai_act"
    )
    _write(path, "<title>Request Rejected</title>")
    rows, checks = readiness.check_declared_files(tmp_path)
    row = next(r for r in rows if r["id"] == source_id)
    assert "WAF" in row["rejected"]
    disk = next(c for c in checks if c.name == "declared files on disk")
    assert disk.status == "FAIL"
    assert "1 rejected" in disk.detail
    assert "src.fetch" in disk.fix


def test_the_restated_cache_paths_match_the_modules_that_own_them():
    """The two paths are restated so this script never imports geopandas (see
    the comment on BASINS_CACHE_REL). This is the price: a move in either module
    has to fail here, or the checker certifies a folder nobody reads."""
    from src import basins, climate

    assert readiness.DATA / readiness.BASINS_CACHE_REL == basins.CACHE
    assert readiness.DATA / readiness.CLIMATE_DIR_REL == climate.CLIMATE_DIR


def test_absent_basins_cache_warns_with_the_warm_up_command(tmp_path):
    check = readiness.check_basins_cache(tmp_path)
    assert check.status == "WARN"
    assert "basins.load()" in check.fix


def test_present_basins_cache_is_ok_and_sized(tmp_path):
    _write(tmp_path / readiness.BASINS_CACHE_REL, "{}" * 1024)
    check = readiness.check_basins_cache(tmp_path)
    assert check.status == "OK" and "2.0 KiB" in check.detail


def test_climate_folder_without_nc_files_warns(tmp_path):
    (tmp_path / readiness.CLIMATE_DIR_REL).mkdir(parents=True)
    _write(tmp_path / readiness.CLIMATE_DIR_REL / "notes.txt")   # not a projection
    check = readiness.check_climate_files(tmp_path)
    assert check.status == "WARN" and "CDS form" in check.fix


def test_climate_folder_with_nc_files_is_ok_and_counted(tmp_path):
    for i in range(3):
        _write(tmp_path / readiness.CLIMATE_DIR_REL / f"member_{i}.nc", "x" * 100)
    check = readiness.check_climate_files(tmp_path)
    assert check.status == "OK" and "3 .nc file(s)" in check.detail


def test_path_collisions_are_reported(tmp_path):
    """`hanze_flood_impacts` declares seven URLs that all end in /content.

    They collapse onto one `content.bin`, so six declared files silently
    overwrite the first. The check warns instead of hiding it; if sources.yaml is
    ever fixed, this test is the thing that says so.
    """
    _, checks = readiness.check_declared_files(tmp_path)
    collision = [c for c in checks if c.name == "declared path collisions"]
    if collision:
        assert collision[0].status == "WARN"
        assert "content.bin" in collision[0].detail
    else:
        paths = [t[2] for t in readiness.declared_targets(tmp_path)]
        assert len(paths) == len(set(paths))


# --- interrupted downloads --------------------------------------------------


def test_no_part_files_is_clean(tmp_path):
    (tmp_path / "raw").mkdir(parents=True)
    assert readiness.check_partial_downloads(tmp_path).status == "OK"


def test_a_growing_part_file_warns_rather_than_telling_you_to_delete_it(tmp_path):
    """A live transfer must not be reported as something to remove.

    This is the one place where wrong advice is destructive: deleting a `.part`
    that `src.fetch` is still writing throws away a partial 300 MB raster.
    """
    part = _write(tmp_path / "raw" / "download" / "big.tif.part")
    check = readiness.check_partial_downloads(tmp_path, now=part.stat().st_mtime + 1)
    assert check.status == "WARN"
    assert "still growing" in check.detail
    assert "delete" not in check.fix.lower() or "rather than deleting" in check.fix


def test_an_abandoned_part_file_fails(tmp_path):
    part = _write(tmp_path / "raw" / "download" / "big.tif.part")
    stale = time.time() - readiness.LIVE_PART_WINDOW_S - 60
    os.utime(part, (stale, stale))
    check = readiness.check_partial_downloads(tmp_path)
    assert check.status == "FAIL"
    assert "big.tif.part" in check.detail


# --- manifest ---------------------------------------------------------------


def test_missing_manifest_fails(tmp_path):
    check = readiness.check_manifest(tmp_path)
    assert check.status == "FAIL"
    assert "absent" in check.detail


def test_unreadable_manifest_fails(tmp_path):
    _write(tmp_path / "raw" / "manifest.json", "{not json")
    assert readiness.check_manifest(tmp_path).status == "FAIL"


def test_manifest_entry_whose_file_is_gone_fails(tmp_path):
    _manifest(tmp_path, [{"source_id": "ai_act", "path": "/app/data/raw/scrape/ai_act.html",
                          "bytes": 10, "error": None}])
    check = readiness.check_manifest(tmp_path)
    assert check.status == "FAIL"
    assert "absent" in check.detail


def test_manifest_size_mismatch_fails(tmp_path):
    _write(tmp_path / "raw" / "scrape" / "ai_act.html", "y" * 99)
    _manifest(tmp_path, [{"source_id": "ai_act", "path": "/app/data/raw/scrape/ai_act.html",
                          "bytes": 10, "error": None}])
    check = readiness.check_manifest(tmp_path)
    assert check.status == "FAIL"
    assert "mismatch" in check.detail


def test_manifest_matching_disk_is_ok(tmp_path):
    _write(tmp_path / "raw" / "scrape" / "ai_act.html", "y" * 10)
    _manifest(tmp_path, [{"source_id": "ai_act", "path": "/app/data/raw/scrape/ai_act.html",
                          "bytes": 10, "error": None}])
    assert readiness.check_manifest(tmp_path).status == "OK"


def test_recorded_failures_are_not_treated_as_missing_files(tmp_path):
    """An entry with an error carries no path: it is a recorded refusal, not data."""
    _manifest(tmp_path, [{"source_id": "efas", "path": None, "bytes": 0,
                          "error": "disallowed by robots.txt"}])
    assert readiness.check_manifest(tmp_path).status == "OK"


def test_manifest_thinner_than_the_corpus_warns(tmp_path):
    """A partial run leaves a manifest that describes less than what is on disk."""
    _, _, path = next(t for t in readiness.declared_targets(tmp_path) if t[0] == "ai_act")
    _write(path, "y" * 10)
    _manifest(tmp_path, [])
    check = readiness.check_manifest(tmp_path)
    assert check.status == "WARN"
    assert "under-reports" in check.fix


# --- RDH cache --------------------------------------------------------------


def test_empty_rdh_cache_fails_and_mentions_the_token(tmp_path):
    check = readiness.check_rdh_cache(tmp_path / "rdh_cache")
    assert check.status == "FAIL"
    assert "10 hours" in check.fix


def test_rdh_cache_names_its_collections_and_row_counts(tmp_path):
    cache = tmp_path / "rdh_cache"
    _write(cache / "hazard.json", json.dumps([{"a": 1}] * 77))
    _write(cache / "losses__admin_unit_country_code-BE.json", json.dumps([{"b": 2}] * 1297))
    check = readiness.check_rdh_cache(cache)
    assert check.status == "OK"
    assert "hazard (77 rows)" in check.detail
    assert "losses (1,297 rows)" in check.detail


def test_rdh_cache_without_losses_warns(tmp_path):
    """The losses collection is the whole reason the RDH is in the kit."""
    cache = tmp_path / "rdh_cache"
    _write(cache / "hazard.json", json.dumps([{"a": 1}]))
    check = readiness.check_rdh_cache(cache)
    assert check.status == "WARN"
    assert "losses" in check.fix


def test_truncated_rdh_cache_file_fails(tmp_path):
    cache = tmp_path / "rdh_cache"
    _write(cache / "losses.json", '[{"a": 1},')
    check = readiness.check_rdh_cache(cache)
    assert check.status == "FAIL"
    assert "UNREADABLE" in check.detail


# --- Ollama -----------------------------------------------------------------


def test_offbox_ollama_url_is_not_probed(monkeypatch):
    """An off-box model server is a network dependency, so it is never dialled."""
    monkeypatch.setattr(
        readiness, "_ollama_tags", lambda url: pytest.fail("probed a remote host")
    )
    check = readiness.check_ollama(url="http://10.0.0.5:11434", model="llama3.1")
    assert check.status == "WARN"
    assert "not probed" in check.detail


def test_unreachable_ollama_fails_with_the_pull_command(monkeypatch):
    def boom(url):
        raise OSError("connection refused")

    monkeypatch.setattr(readiness, "_ollama_tags", boom)
    check = readiness.check_ollama(url="http://localhost:11434", model="llama3.1")
    assert check.status == "FAIL"
    assert "ollama pull llama3.1" in check.fix


def test_the_code_default_being_pulled_is_clean(monkeypatch):
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: ["llama3.1:latest"])
    check = readiness.check_ollama(url="http://localhost:11434", model="llama3.1")
    assert check.status == "OK"


def test_a_different_model_is_ok_but_the_mismatch_is_stated(monkeypatch):
    """OLLAMA_MODEL names a model other than the one src/rag.py defaults to.

    It works, and it stops working the moment .env is absent - which is exactly
    what happens in a fresh container, so the caveat is part of the answer.
    """
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: ["qwen2.5:3b"])
    check = readiness.check_ollama(url="http://localhost:11434", model="qwen2.5:3b")
    assert check.status == "OK"
    assert readiness.RAG_DEFAULT_OLLAMA_MODEL in check.detail


def test_the_code_default_matches_what_rag_py_asks_for():
    """A drift between the two is a check that certifies the wrong model, so the
    check imports rag's constant and rag's call reads that same constant."""
    from src import rag

    assert readiness.RAG_DEFAULT_OLLAMA_MODEL is rag.OLLAMA_DEFAULT_MODEL
    source = (ROOT / "src" / "rag.py").read_text(encoding="utf-8")
    assert 'os.getenv("OLLAMA_MODEL", "").strip() or OLLAMA_DEFAULT_MODEL' in source


def test_wrong_tag_in_the_same_family_suggests_the_one_word_fix(monkeypatch):
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: ["llama3.1:8b"])
    check = readiness.check_ollama(url="http://localhost:11434", model="llama3.1")
    assert check.status == "FAIL"
    assert "OLLAMA_MODEL=llama3.1:8b" in check.fix


def test_reachable_ollama_with_no_models_fails(monkeypatch):
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: [])
    check = readiness.check_ollama(url="http://localhost:11434", model="llama3.1")
    assert check.status == "FAIL"
    assert "no models" in check.detail


def test_the_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: ["qwen2.5-coder:latest"])
    assert readiness.check_ollama(url="http://localhost:11434").status == "OK"


# --- generation provider ----------------------------------------------------


def test_a_groq_key_warns_that_the_demo_is_online_again():
    check = readiness.check_generation_key({"GROQ_API_KEY": "gsk_x"})
    assert check.status == "WARN"
    assert "Groq" in check.detail


def test_no_groq_key_means_the_local_model_answers():
    check = readiness.check_generation_key({"OLLAMA_MODEL": "llama3.2:3b"})
    assert check.status == "OK"
    assert "llama3.2:3b" in check.detail


def test_a_blank_groq_key_is_not_a_key():
    """.env.example ships `GROQ_API_KEY=`, and an empty value must read as unset."""
    assert readiness.check_generation_key({"GROQ_API_KEY": "   "}).status == "OK"


def test_a_claude_key_warns_that_the_demo_is_online_again():
    """Claude is asked first, so its key routes the demo online even with no Groq key."""
    check = readiness.check_generation_key({"ANTHROPIC_API_KEY": "sk-ant-x"})
    assert check.status == "WARN"
    assert "Claude" in check.detail
    assert "ANTHROPIC_API_KEY" in check.fix


@pytest.mark.parametrize("name", ["GROQ_API_KEY_2", "GROQ_API_KEY_5"])
def test_a_secondary_groq_key_routes_the_demo_online_too(name):
    """`rag.groq_keys()` rotates over GROQ_API_KEY and GROQ_API_KEY_2.._5, so
    commenting out the first one alone still sends the demo to Groq."""
    check = readiness.check_generation_key({name: "gsk_x"})
    assert check.status == "WARN"
    assert name in check.detail


def test_a_blank_claude_key_is_not_a_key():
    assert readiness.check_generation_key({"ANTHROPIC_API_KEY": " "}).status == "OK"


# --- the whole run ----------------------------------------------------------


def test_run_checks_covers_every_promised_check(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: ["llama3.1:latest"])
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    _rows, checks = readiness.run_checks(tmp_path)
    names = {c.name for c in checks}
    assert {"declared files on disk", "interrupted downloads", "manifest",
            "RDH cache", "basins cache", "climate projections", "Ollama",
            "generation provider"} <= names


# --- the three verdicts -----------------------------------------------------
#
# Two states say "runs offline" over a WARN that the Groq key routes every
# answer through the venue Wi-Fi: true of the code, false of the demo. The third
# state is what makes the green signal trustworthy.


def _ok():
    return readiness.Check("declared files on disk", "OK", "52/52 present")


def _warn():
    return readiness.Check("generation provider", "WARN", "GROQ_API_KEY is set", fix="unset it")


def _fail():
    return readiness.Check("RDH cache", "FAIL", "empty", fix="fetch it")


def test_all_ok_is_ready_and_exits_zero():
    line, code = readiness.verdict([_ok()])
    assert line.startswith("READY -") and code == 0


def test_a_warn_alone_is_ready_with_caveats_and_names_them():
    line, code = readiness.verdict([_ok(), _warn()])
    assert code == 0
    assert "CAVEATS" in line and "generation provider" in line and "--strict" in line


def test_strict_turns_a_warn_into_a_block():
    line, code = readiness.verdict([_ok(), _warn()], strict=True)
    assert code == 1 and line.startswith("BLOCKED") and "generation provider" in line


def test_a_fail_blocks_whatever_the_mode():
    for strict in (False, True):
        line, code = readiness.verdict([_ok(), _warn(), _fail()], strict=strict)
        assert code == 1 and "NOT survive" in line


def test_main_reads_strict_from_its_arguments(monkeypatch, capsys):
    monkeypatch.setattr(readiness, "run_checks", lambda: ([], [_ok(), _warn()]))
    assert readiness.main([]) == 0
    assert "READY WITH CAVEATS" in capsys.readouterr().out
    assert readiness.main(["--strict"]) == 1
    assert "(strict)" in capsys.readouterr().out


def test_an_empty_tree_is_reported_as_not_demo_ready(tmp_path, monkeypatch):
    """The contract the script is for: a FAIL anywhere means a non-zero exit."""
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: ["llama3.1:latest"])
    _rows, checks = readiness.run_checks(tmp_path)
    assert any(c.status == "FAIL" for c in checks)


def test_main_exits_non_zero_when_the_demo_would_not_work(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "_ollama_tags", lambda url: ["llama3.1:latest"])
    # Bound before patching, or the replacement would call itself.
    real_run_checks = readiness.run_checks
    monkeypatch.setattr(readiness, "run_checks", lambda: real_run_checks(tmp_path))
    assert readiness.main() == 1
    assert "would NOT survive" in capsys.readouterr().out


def test_main_exits_zero_when_every_check_is_clean(monkeypatch, capsys):
    clean = [readiness.Check("declared files on disk", "OK", "46/46 present")]
    monkeypatch.setattr(readiness, "run_checks", lambda: ([], clean))
    assert readiness.main() == 0
    assert "READY - the demo runs offline" in capsys.readouterr().out
