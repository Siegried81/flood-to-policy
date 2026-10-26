"""Tests for the collection layer. No network: every HTTP call is mocked.

What matters here is not that a download works - it is that the politeness and
idempotency guarantees hold, because those are the ones that fail silently and
the ones we claim to the jury.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from src import fetch as F


class _Response:
    def __init__(self, content=b"payload" * 400, status=200, chunk=8):
        # Default body is comfortably past MIN_DOCUMENT_BYTES, so a test that is
        # not about the size floor does not trip it.
        self.content, self.status_code = content, status
        # Deliberately tiny, so every body arrives in many chunks: a
        # single-chunk double would hide a bug in how the download accumulates
        # the head, the byte count and the digest across iterations.
        self._chunk = chunk

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def iter_content(self, chunk_size=None):
        """Downloads are streamed to disk, so the double has to stream too."""
        for i in range(0, len(self.content), self._chunk):
            yield self.content[i:i + self._chunk]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _AllowAllRobots(F._RobotsCache):
    """A robots cache that permits everything, for tests about the BODY check.

    Needed since the gate stopped trusting a 2xx whose body is not robots.txt:
    the same `_Response` double otherwise serves as both the robots file and the
    document, and a WAF page now correctly fails at the robots step - masking the
    body check the test is actually about. Separating them is the point.
    """

    def allows(self, url: str) -> bool:
        return True

    def crawl_delay(self, url: str) -> float | None:
        return None

    def refusal_reason(self, url: str) -> str | None:
        """`_fetch_one` asks this, not `allows`, since the derogation has to
        tell an unreadable file from an explicit Disallow. A double that
        overrides only `allows` falls through to the real implementation and
        makes a live network call."""
        return None


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "DATA", tmp_path)
    return tmp_path


def _entry(i=1):
    return {"id": f"src{i}", "url": f"https://example.org/{i}.tif"}


def test_second_run_does_not_refetch(workspace):
    """Idempotency: 'make sure the file is here', not 'fetch it again'. A dropped
    hackathon network means this runs several times."""
    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response()) as get:
        first = F._fetch_one(_entry(), "download", throttle, robots)
        second = F._fetch_one(_entry(), "download", throttle, robots)
    assert get.call_count == 1  # the second call never hit the network
    assert first.sha256 == second.sha256
    assert second.ok


def test_a_stale_rejection_page_on_disk_is_quarantined_and_refetched(workspace):
    """"Exists and is non-empty" lets a WAF page stored by an older run come back
    ok=True with a hash and a clean manifest line. A reused file has to pass the
    same body check as a fresh download; one that fails is moved aside as
    `.rejected` (kept as evidence, never deleted) and the download runs as if it
    had never existed."""
    target = F._target_path("src1", "https://example.org/1.tif", "download")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"<title>Request Rejected</title>")
    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response()) as get:
        result = F._fetch_one(_entry(), "download", throttle, robots)
    assert get.call_count == 1, "the stale page must not count as the file"
    assert result.ok and result.bytes == len(b"payload" * 400)
    assert target.with_name(target.name + ".rejected").read_bytes().startswith(b"<title>")
    assert target.read_bytes() == b"payload" * 400


def test_a_locked_stale_file_is_a_failed_result_not_a_crash(workspace, monkeypatch):
    """Moving the stale file aside can raise PermissionError on Windows when
    something holds it open. Escaping `_fetch_one` would kill `fetch_all` and
    lose the manifest, so it has to come back as a failed result like any other."""
    from pathlib import Path

    target = F._target_path("src1", "https://example.org/1.tif", "download")
    target.parent.mkdir(parents=True)
    target.write_bytes(b"<title>Request Rejected</title>")

    def locked(self, other):
        raise PermissionError("[WinError 32] file in use")

    monkeypatch.setattr(Path, "replace", locked)
    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response()) as get:
        result = F._fetch_one(_entry(), "download", throttle, robots)
    assert get.call_count == 0, "a file that cannot be moved aside is not refetched over"
    assert not result.ok
    assert "could not move" in result.error
    assert target.read_bytes().startswith(b"<title>"), "the evidence stays where it was"


def test_a_reused_file_is_fingerprinted_in_chunks_not_read_whole(workspace):
    """The reuse path held a whole raster in memory to hash it while the download
    beside it streamed. `sha256_of` reads CHUNK_BYTES at a time; the digest has
    to match what `read_bytes` would give, or the manifest fingerprint changes
    between a first run and a re-run of the same file."""
    import hashlib
    body = bytes(range(256)) * 40
    target = F._target_path("src1", "https://example.org/1.tif", "download")
    target.parent.mkdir(parents=True)
    target.write_bytes(body)
    with patch.object(F, "CHUNK_BYTES", 1000):          # many chunks, uneven tail
        assert F.sha256_of(target) == hashlib.sha256(body).hexdigest()
    with patch.object(F.requests, "get") as get:
        result = F._fetch_one(_entry(), "download", F._HostThrottle(0), F._RobotsCache())
    get.assert_not_called()
    assert result.ok and result.sha256 == hashlib.sha256(body).hexdigest()


def test_colliding_declared_paths_are_refused_not_raced(workspace):
    """Two files on one path are not two files: whichever finished last won and
    both printed ok. `fetch_all` now refuses both as results that name each other
    and the fix, and still fetches everything else in the same run."""
    entry = {"id": "api_like", "url": "https://example.org/records/1/files/",
             "access": "download", "files": ["a.csv/content", "b.zip/content", "c.csv"]}
    with patch.object(F, "sources", return_value=[entry]):
        with patch.object(F.requests, "get", return_value=_Response()) as get:
            results = F.fetch_all(sections=("geodata",))
    assert get.call_count == 1                       # only c.csv was fetched
    assert [r.source_id for r in results if r.ok] == ["api_like/c"]
    refused = [r for r in results if not r.ok]
    assert len(refused) == 2 and all("sources.yaml" in r.error for r in refused)
    assert "would overwrite 1 other" in refused[0].error


def test_a_failure_is_returned_not_raised(workspace):
    """One dead URL must leave the other downloads intact - the behaviour you
    want the night before a deadline."""
    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    with patch.object(F.requests, "get", side_effect=RuntimeError("DNS failure")):
        result = F._fetch_one(_entry(), "download", throttle, robots)
    assert not result.ok
    assert "DNS failure" in result.error
    assert result.path is None


def test_scraping_stops_at_robots_txt(workspace):
    """The jury is the European Commission. A disallowed URL is not fetched."""
    throttle = F._HostThrottle(0)

    class _DenyAll:
        """A host whose robots.txt says no. Distinct from one we could not read:
        a declared `robots_unreadable:` derogation covers the second and must
        never cover this one."""

        def allows(self, url):
            return False

        def refusal_reason(self, url):
            return "disallowed"

    with patch.object(F.requests, "get") as get:
        result = F._fetch_one(_entry(), "scrape", throttle, _DenyAll())
    get.assert_not_called()
    assert "robots.txt" in result.error


def test_unreachable_robots_txt_is_not_permission():
    """A failed read must not be read as 'allowed' - that is how a polite scraper
    silently becomes an impolite one."""
    robots = F._RobotsCache()
    with patch.object(F.urllib.robotparser.RobotFileParser, "read", side_effect=OSError):
        assert robots.allows("https://nowhere.example/page") is False


def test_throttle_spaces_requests_to_one_host():
    throttle = F._HostThrottle(delay_s=0.05)
    start = time.monotonic()
    for _ in range(3):
        throttle.wait("https://example.org/a")
    assert time.monotonic() - start >= 0.10  # two gaps between three requests


def test_throttle_does_not_make_one_host_wait_for_another():
    """Per host, not global: a slow raster server must not hold up EUR-Lex, or the
    thread pool buys nothing."""
    throttle = F._HostThrottle(delay_s=0.3)
    throttle.wait("https://slow.example/a")
    start = time.monotonic()
    throttle.wait("https://other.example/b")
    assert time.monotonic() - start < 0.05


def test_api_entries_are_not_mirrored(workspace, monkeypatch):
    """A query endpoint is called with parameters at runtime, not downloaded whole."""
    monkeypatch.setattr(
        F, "sources",
        lambda section: [{"id": "an_api", "url": "https://example.org/q", "access": "api"}]
        if section == "geodata" else [],
    )
    with patch.object(F.requests, "get") as get:
        results = F.fetch_all(sections=("geodata",))
    get.assert_not_called()
    assert results == []


def test_a_waf_rejection_page_is_a_failure_not_a_document(workspace):
    """Several EU portals answer a non-browser client with a rejection page under
    HTTP 200, so raise_for_status passes and the bytes get written. The first real
    run of this module stored exactly such a page as jrc_publications.html."""
    body = (
        b"<html><head><title>Request Rejected</title></head><body>"
        b"The requested URL was rejected. Please consult with your administrator."
        b"</body></html>"
    )
    throttle, robots = F._HostThrottle(0), _AllowAllRobots()
    with patch.object(F.requests, "get", return_value=_Response(body)):
        result = F._fetch_one(_entry(), "scrape", throttle, robots)
    assert not result.ok
    assert "WAF" in result.error
    assert result.path is None  # nothing written, so the corpus stays clean


def test_a_stub_too_short_to_be_a_document_is_rejected(workspace):
    throttle, robots = F._HostThrottle(0), _AllowAllRobots()
    with patch.object(F.requests, "get", return_value=_Response(b"redirecting...")):
        result = F._fetch_one(_entry(), "scrape", throttle, robots)
    assert not result.ok and "not a document" in result.error


def test_robots_is_read_with_browser_headers(workspace):
    """RobotFileParser.read() uses urllib's own User-Agent, which several EU sites
    block; it then answers the 403 by setting disallow_all, so every path comes
    back forbidden. That false refusal looks like compliance while silently
    dropping sources - it is why robots.txt is fetched through requests here."""
    robots = F._RobotsCache()
    allow_all = _Response(b"User-agent: *\nDisallow: /admin/\n")
    with patch.object(F.requests, "get", return_value=allow_all) as get:
        assert robots.allows("https://example.org/publication/thing") is True
        assert robots.allows("https://example.org/admin/secret") is False
    # One fetch for both checks: the parser is cached per host.
    assert get.call_count == 1
    assert "Mozilla" in get.call_args.kwargs["headers"]["User-Agent"]


# --- multi-file entries (src.fetch.expand) ---------------------------------
#
# These exist because the failure they guard against is silent: an entry whose
# url is a directory used to store the HTML listing as the data, pass the
# document check (a listing is well over MIN_DOCUMENT_BYTES), and then be
# treated as permanently fetched by the idempotency rule.


def test_an_entry_without_files_is_untouched():
    """Every single-file source must keep its exact previous behaviour."""
    entry = {"id": "gisco_nuts3", "url": "https://example.org/n.geojson"}
    assert F.expand(entry) == [entry]


def test_files_are_joined_to_the_directory_url():
    entry = {"id": "hz", "url": "https://example.org/flood_hazard/",
             "files": ["Europe_RP100_filled_depth.tif", "README.txt"]}
    jobs = F.expand(entry)
    assert [j["url"] for j in jobs] == [
        "https://example.org/flood_hazard/Europe_RP100_filled_depth.tif",
        "https://example.org/flood_hazard/README.txt",
    ]


def test_each_file_lands_on_its_own_path_under_a_folder_named_for_the_entry():
    """The id carries the entry, so a downloaded file stays traceable to the line
    that declared it - and the stem avoids a doubled suffix (`...tif.tif`)."""
    entry = {"id": "hz", "url": "https://example.org/d/",
             "files": ["Europe_RP100_filled_depth.tif"]}
    job = F.expand(entry)[0]
    path = F._target_path(job["id"], job["url"], "download")
    assert path.name == "Europe_RP100_filled_depth.tif"
    assert path.parent.name == "hz"


def test_an_absolute_file_url_overrides_the_entry_url():
    """Some landing pages live on a different host than the file they describe."""
    entry = {"id": "pop", "url": "https://example.org/landing-page",
             "files": ["https://files.example.net/a/TF_2026.zip"]}
    assert F.expand(entry)[0]["url"] == "https://files.example.net/a/TF_2026.zip"


def test_the_other_entry_keys_survive_expansion():
    entry = {"id": "hz", "url": "https://example.org/d/", "files": ["a.tif"],
             "crs": "EPSG:4326", "licence": "CC-BY-4.0"}
    job = F.expand(entry)[0]
    assert job["crs"] == "EPSG:4326" and job["licence"] == "CC-BY-4.0"


def test_fetch_all_queues_one_job_per_declared_file(workspace):
    """The real regression: nine return periods from one entry, not one listing."""
    entry = {"id": "hz", "url": "https://example.org/d/", "access": "download",
             "files": ["a.tif", "b.tif", "c.tif"]}
    with patch.object(F, "sources", return_value=[entry]):
        with patch.object(F.requests, "get", return_value=_Response()) as get:
            results = F.fetch_all(sections=("geodata",))
    assert get.call_count == 3
    assert sorted(r.source_id for r in results) == ["hz/a", "hz/b", "hz/c"]


def test_an_api_entry_is_still_skipped_even_if_it_lists_files(workspace):
    entry = {"id": "rdh", "url": "https://example.org/", "access": "api",
             "files": ["a.json"]}
    with patch.object(F, "sources", return_value=[entry]):
        with patch.object(F.requests, "get") as get:
            results = F.fetch_all(sections=("geodata",))
    assert get.call_count == 0 and results == []


# --- streaming downloads (the raster bug) ----------------------------------
#
# Eight 300 MB rasters were opened on one host at once, every stream fell under
# the read timeout, and all of them failed while the two small text files in the
# same directory succeeded. The fixes were: stream to disk instead of holding
# the body in memory, cap concurrent transfers per host, and write through a
# `.part` file so a dropped connection cannot leave a truncated raster that the
# idempotency check would then accept forever.


def test_a_dropped_connection_leaves_no_file_behind(workspace):
    """The dangerous failure: a truncated 300 MB raster opens and reads fine, and
    its numbers are wrong. It must not survive the failure."""
    class _Dies(_Response):
        def iter_content(self, chunk_size=None):
            yield b"x" * 5000
            raise OSError("connection reset")

    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Dies()):
        result = F._fetch_one(_entry(), "download", throttle, robots)
    assert not result.ok and "connection reset" in result.error
    target = F._target_path("src1", "https://example.org/1.tif", "download")
    assert not target.exists()
    assert not target.with_name(target.name + ".part").exists()


def test_a_rejected_body_leaves_no_file_behind(workspace):
    """Same for a WAF page: it must not be renamed into place."""
    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    body = b'<html><script>window["bobcmn"] = "1"</script>' + b"x" * 5000
    with patch.object(F.requests, "get", return_value=_Response(body)):
        result = F._fetch_one(_entry(), "download", throttle, robots)
    assert not result.ok
    target = F._target_path("src1", "https://example.org/1.tif", "download")
    assert not target.exists()
    assert not target.with_name(target.name + ".part").exists()


def test_the_digest_and_size_are_computed_over_the_whole_stream(workspace):
    """Both are accumulated chunk by chunk, so an off-by-one in the loop would
    silently change the fingerprint that makes a figure traceable to a file."""
    import hashlib
    body = bytes(range(256)) * 40          # 10,240 B, many chunks of 8
    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(body)):
        result = F._fetch_one(_entry(), "download", throttle, robots)
    assert result.ok
    assert result.bytes == len(body)
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert F._target_path("src1", "https://example.org/1.tif", "download").read_bytes() == body


def test_the_length_floor_uses_the_streamed_size_not_the_head(workspace):
    """_why_not_a_document only sees the first 4 KiB now, so the byte count has
    to be passed in or every large file would read as a stub."""
    assert F._why_not_a_document(b"tiny", total_size=10_000_000) is None
    assert "not a document" in F._why_not_a_document(b"x" * 4096, total_size=12)
    # Unchanged for in-memory callers that pass the whole body.
    assert "not a document" in F._why_not_a_document(b"short")


def test_only_one_transfer_per_host_runs_at_a_time(workspace):
    """The actual cause of the raster failures: the delay spaced out when
    requests started, not how many ran at once."""
    import threading
    live, peak = 0, 0
    lock = threading.Lock()

    class _Slow(_Response):
        def iter_content(self, chunk_size=None):
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            try:
                time.sleep(0.05)
                yield self.content
            finally:
                with lock:
                    live -= 1

    entry = {"id": "hz", "url": "https://one-host.example.org/d/", "access": "download",
             "files": [f"{i}.tif" for i in range(4)]}
    with patch.object(F, "sources", return_value=[entry]):
        with patch.object(F, "PER_HOST_DELAY_S", 0):
            with patch.object(F.requests, "get", return_value=_Slow()):
                results = F.fetch_all(sections=("geodata",))
    assert all(r.ok for r in results)
    assert peak == 1, f"{peak} transfers ran at once against one host"


# --- the robots gate's own principle ---------------------------------------
#
# "An unreachable robots.txt is not permission" was the stated rule, and a 2xx
# carrying something other than robots.txt defeated it. Measured 2026-10-06:
# eur-lex.europa.eu answers /robots.txt with HTTP 202 and an AWS WAF challenge
# page, publications.jrc.ec.europa.eu with HTTP 200 and its HTML homepage. Both
# parsed to an empty ruleset, so every path was allowed - on the two hosts that
# carry the legal corpus.


def test_an_html_body_under_200_is_not_permission(workspace):
    """The silent false ALLOW. Worse than the false refusal the class was written
    to prevent, because it fetches on rules nobody read and logs a clean pass."""
    page = _Response(b"<!DOCTYPE html><html><head><title>Home</title></head></html>")
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=page):
        assert robots.allows("https://example.org/anything") is False


def test_a_comment_only_body_is_not_permission(workspace):
    """No directives at all means nothing was declared, which is not consent."""
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(b"# nothing here\n")):
        assert robots.allows("https://example.org/anything") is False


def test_a_real_robots_file_is_still_honoured(workspace):
    """The fix must not turn into a blanket refusal: a genuine file still rules."""
    body = b"User-agent: *\nDisallow: /private/\n"
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(body)):
        assert robots.allows("https://example.org/public/doc") is True
        assert robots.allows("https://example.org/private/doc") is False


def test_is_not_robots_recognises_both_shapes():
    assert F._is_not_robots("<!DOCTYPE html><html>") is True
    assert F._is_not_robots('<html lang="en">') is True
    assert F._is_not_robots("# only a comment") is True
    assert F._is_not_robots("User-agent: *\nDisallow: /x") is False
    assert F._is_not_robots("Sitemap: https://example.org/s.xml") is False


def test_a_published_crawl_delay_is_honoured(workspace):
    """www.undrr.org asks for 10 seconds and the throttle used 1. The Sendai
    framework was being fetched ten times faster than its host asks."""
    body = b"User-agent: *\nCrawl-delay: 10\nDisallow: /private/\n"
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(body)):
        assert robots.crawl_delay("https://example.org/doc") == 10.0


def test_the_larger_of_the_two_delays_wins(workspace):
    """A published limit is a request we honour, not a ceiling we negotiate."""
    throttle = F._HostThrottle(1.0)
    start = time.monotonic()
    throttle.wait("https://example.org/a")          # first call never sleeps
    throttle.wait("https://example.org/b", 0.2)     # ours (1.0) is larger
    waited_default = time.monotonic() - start
    assert waited_default >= 1.0

    # The delay a call applies is the one it RESERVES for the next call, so the
    # host's own delay has to be passed on the first request too - which is what
    # `_fetch_one` does, since it reads the Crawl-delay before every scrape.
    throttle2 = F._HostThrottle(0.0)
    start = time.monotonic()
    throttle2.wait("https://other.example.org/a", 0.3)   # theirs is larger
    throttle2.wait("https://other.example.org/b", 0.3)
    assert time.monotonic() - start >= 0.3


def test_no_robots_request_is_made_for_a_download(workspace):
    """robots.txt is only read for `scrape`. Asking for it on a download would
    fetch it from the five hosts here that publish none."""
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response()) as get:
        F._fetch_one(_entry(), "download", F._HostThrottle(0), robots)
    # One call only: the file itself, never /robots.txt.
    assert get.call_count == 1
    assert "robots.txt" not in get.call_args.args[0]


def test_a_host_with_no_robots_file_is_allowed_not_refused(workspace):
    """A 4xx means no rules were declared, which RFC 9309 2.3.1.3 treats as
    permission. Six hosts in this project publish no robots.txt, including the
    one serving the official Walloon flood-management documents; refusing them
    reported "disallowed by robots.txt" about a file that does not exist."""
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(b"not found", status=404)):
        assert robots.allows("https://example.org/doc.pdf") is True
        assert robots.crawl_delay("https://example.org/doc.pdf") is None


def test_a_server_error_is_still_not_permission(workspace):
    """The distinction that matters: on a 5xx the rules may exist and we failed
    to read them, so the refusal stands."""
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(b"boom", status=503)):
        assert robots.allows("https://example.org/doc.pdf") is False


def test_robots_is_fetched_once_per_host_whatever_the_outcome(workspace):
    """Caching covers the no-rules case too, or a host without robots.txt would
    be asked for it again on every single document."""
    robots = F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(b"nf", status=404)) as get:
        robots.allows("https://example.org/a.pdf")
        robots.allows("https://example.org/b.pdf")
        robots.crawl_delay("https://example.org/c.pdf")
    assert get.call_count == 1


def test_no_two_declared_files_land_on_the_same_path():
    """Against the real config/sources.yaml, because the bug this pins was a
    silent one: HANZE declared seven files whose URLs all ended in `/content`,
    `expand` named each from the URL's last path segment, and all seven resolved
    to `content.bin`. Six of seven were lost while a clean "ok" printed for each.
    Any future entry whose URLs share a last segment fails here instead."""
    from src.data_io import sources

    paths = []
    for section in ("geodata", "policy_corpus", "context"):
        for entry in sources(section) or []:
            if entry.get("access") == "api":
                continue
            kind = entry.get("access", "download")
            for job in F.expand(entry):
                paths.append(str(F.target_of(job, kind)))

    duplicates = {p for p in paths if paths.count(p) > 1}
    assert not duplicates, f"these declared files overwrite each other: {duplicates}"
    assert len(paths) > 40, "the config should declare dozens of files; did it load?"


def test_a_url_ending_in_a_constant_segment_is_caught():
    """The shape of the HANZE bug, in isolation: an API that serves every file
    under the same final path segment."""
    entry = {"id": "api_like", "url": "https://example.org/records/1/files/",
             "files": ["a.csv/content", "b.zip/content"]}
    names = [
        F._target_path(j["id"], j["url"], "download").name for j in F.expand(entry)
    ]
    assert names[0] == names[1], "this is the collision the config test guards against"


def test_a_derogation_never_covers_an_explicit_disallow(workspace):
    """The hole this distinction closes. `robots.allows()` returns False for two
    reasons - a file we could not read, and a file that plainly says no - and the
    declared derogation applies only to the first. Applying it to both would have
    let the five entries carrying `robots_unreadable:` scrape straight through a
    real Disallow the day their host started publishing one, which makes the
    module docstring's "never bypassed" false."""
    throttle = F._HostThrottle(0)
    entry = {**_entry(), "robots_unreadable": "2026-10-06"}

    class _DenyAll:
        def refusal_reason(self, url):
            return "disallowed"

    with patch.object(F.requests, "get") as get:
        result = F._fetch_one(entry, "scrape", throttle, _DenyAll())
    get.assert_not_called()
    assert not result.ok
    assert "disallowed by robots.txt" in result.error


def test_a_derogation_does_cover_an_unreadable_robots_txt(workspace):
    """And it must still work for the case it was declared for, or the AI Act,
    the Floods Directive and the two EFAS reports leave the corpus."""
    throttle = F._HostThrottle(0)
    entry = {**_entry(), "robots_unreadable": "2026-10-06"}

    class _Unreadable:
        def refusal_reason(self, url):
            return "unreadable"

        def crawl_delay(self, url):
            return None

    with patch.object(F.requests, "get", return_value=_Response()):
        result = F._fetch_one(entry, "scrape", throttle, _Unreadable())
    assert result.ok
    assert result.robots_derogation == "2026-10-06", "the exception must be recorded"


def test_an_unreadable_robots_txt_without_a_derogation_is_still_refused(workspace):
    throttle = F._HostThrottle(0)

    class _Unreadable:
        def refusal_reason(self, url):
            return "unreadable"

    with patch.object(F.requests, "get") as get:
        result = F._fetch_one(_entry(), "scrape", throttle, _Unreadable())
    get.assert_not_called()
    assert not result.ok and "could not be read" in result.error
def test_a_directory_listing_is_a_failure_not_a_document(workspace):
    """A JEODPP folder url returns its Apache listing under HTTP 200. It carries no
    rejection marker and is comfortably past the size floor, so it used to be
    written as the raster it stood in for: 4,020 bytes of HTML saved as
    jrc_flood_hazard.bin and reported ok. The body here is padded well past
    MIN_DOCUMENT_BYTES on purpose, so this proves the listing check and not the
    floor is what rejects it."""
    body = (
        b"<html><head><title>Index of /ftp/jrc-opendata/CEMS-EFAS/flood_hazard"
        b"</title></head><body><h1>Index of /ftp/jrc-opendata</h1><table>"
        + b"<tr><td><a href=\"Europe_RP100_filled_depth.tif\">tif</a></td></tr>" * 60
        + b"</table></body></html>"
    )
    assert len(body) > F.MIN_DOCUMENT_BYTES
    throttle, robots = F._HostThrottle(0), F._RobotsCache()
    with patch.object(F.requests, "get", return_value=_Response(body)):
        result = F._fetch_one(_entry(), "download", throttle, robots)
    assert not result.ok
    assert "directory listing" in result.error
    assert result.path is None  # nothing written, so no HTML masquerading as a raster


def test_folder_entries_are_not_mirrored(workspace, monkeypatch):
    """A `folder` holds rasters of 260-334 MB each, read as a window through
    /vsicurl/ at runtime. Fetching the url would only store the directory listing,
    which is exactly the failure this mode exists to prevent."""
    monkeypatch.setattr(
        F, "sources",
        lambda section: [{
            "id": "jrc_flood_hazard",
            "url": "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-EFAS/flood_hazard/",
            "access": "folder",
        }] if section == "geodata" else [],
    )
    with patch.object(F.requests, "get") as get:
        results = F.fetch_all(sections=("geodata",))
    get.assert_not_called()
    assert results == []


# --- the policy sources docs/policy_context.md cited and nothing declared ----------

#: The twelve entries added for the thirteen documents `policy_context.md` cited
#: without a declaration. The thirteenth, the Belgian Insurance Act of 4 April
#: 2014, is not declared: its ELI on www.ejustice.just.fgov.be is disallowed by
#: that host's robots.txt (measured 2026-10-12), and a declared file the fetcher
#: must refuse would hold the offline check at BLOCKED for good.
UNDECLARED_UNTIL_2026_10_12 = {
    "policy_corpus": [
        "union_disaster_resilience_goals", "ucpm_decision",
        "eu_adaptation_strategy_2021", "water_resilience_strategy_2025",
        "floods_directive_assessment_swd_2025_24", "ai_act_digital_omnibus_2026",
        "eea_eucra_2024", "eea_economic_losses_indicator",
        "eiopa_protection_gap_nutshell_2025", "wallonia_floods_review_2022",
        "assuralia_floods_update_2023",
    ],
    "context": ["eiopa_protection_gap_dashboard_data"],
}


def _declared(section):
    from src.data_io import sources
    return {e["id"]: e for e in sources(section) or []}


@pytest.mark.parametrize("section, source_id", [
    (section, source_id)
    for section, ids in UNDECLARED_UNTIL_2026_10_12.items() for source_id in ids
])
def test_each_cited_policy_source_is_declared_with_its_provenance(section, source_id):
    entry = _declared(section).get(source_id)
    assert entry is not None, f"{source_id} is not declared in {section}"
    assert entry["access"] == "scrape"
    assert entry["url"].startswith("https://")
    assert str(entry.get("purpose") or "").strip()
    assert entry.get("verified"), "a declared URL carries the date it was checked"


def test_no_new_eu_act_is_declared_on_the_waf_host():
    """eur-lex answers every scripted GET with a 202 WAF challenge, so an act
    declared there is an entry that can never be fetched. The six EU acts come
    from CELLAR instead; eur-lex stays only as the human-readable `landing`."""
    corpus = _declared("policy_corpus")
    for source_id in UNDECLARED_UNTIL_2026_10_12["policy_corpus"][:6]:
        assert corpus[source_id]["url"].startswith(
            "https://publications.europa.eu/resource/celex/"), source_id
        assert "eur-lex.europa.eu" in corpus[source_id]["landing"]
        assert "robots_unreadable" not in corpus[source_id], (
            "CELLAR's robots.txt is readable; a derogation here would be stale")


def test_a_declared_suffix_names_the_file_when_the_url_does_not(workspace):
    """eiopa.europa.eu serves a PDF at `/document/download/<uuid>_en`. Named from
    the URL it became `.html`, and `rag._read` picks its parser by suffix."""
    entry = {"id": "nutshell", "url": "https://example.org/document/download/ab-cd_en",
             "suffix": ".pdf"}
    assert F.target_of(entry, "scrape").name == "nutshell.pdf"
    assert F.target_of({**entry, "suffix": None}, "scrape").name == "nutshell.html"
    assert F.target_of(_entry(), "download") == F._target_path("src1", _entry()["url"], "download")


def test_a_suffixed_entry_is_fetched_to_its_declared_name(workspace):
    entry = {"id": "nutshell", "url": "https://example.org/document/download/ab-cd_en",
             "suffix": ".pdf"}
    body = b"%PDF-1.7\n" + b"x" * 3000
    with patch.object(F.requests, "get", return_value=_Response(body)) as get:
        result = F._fetch_one(entry, "scrape", F._HostThrottle(0), _AllowAllRobots())
        again = F._fetch_one(entry, "scrape", F._HostThrottle(0), _AllowAllRobots())
    assert result.ok and result.path.endswith("nutshell.pdf")
    assert (workspace / "raw" / "scrape" / "nutshell.pdf").read_bytes() == body
    assert get.call_count == 1, "the re-run must find the file under the same name"
    assert again.ok


def test_every_declared_suffix_is_a_plain_extension():
    from src.data_io import sources
    import re
    for section in ("geodata", "policy_corpus", "context"):
        for entry in sources(section) or []:
            if "suffix" in entry:
                assert re.fullmatch(r"\.[a-z0-9]{1,5}", str(entry["suffix"])), entry["id"]


def test_every_corpus_document_lands_in_a_format_the_retrieval_layer_reads():
    """A corpus file `rag._read` cannot parse is declared, fetched and then
    silently absent from the index - unciteable while looking present."""
    readable = {".pdf", ".txt", ".md", ".html", ".htm"}
    for entry in _declared("policy_corpus").values():
        for job in F.expand(entry):
            assert F.target_of(job, "scrape").suffix in readable, job["id"]


def test_fetch_source_runs_one_declared_entry_through_the_same_checks(monkeypatch):
    """The hosted app fetches the map boundaries alone. It must go through
    `_fetch_one` - quarantine, body checks, robots - with the entry exactly as
    declared, and must not rewrite the manifest of a full run."""
    seen = []
    monkeypatch.setattr(F, "_fetch_one", lambda entry, kind, *a: seen.append((entry, kind)) or "r")
    monkeypatch.setattr(F, "fetch_all", lambda *a, **k: pytest.fail("fetched everything"))

    assert F.fetch_source("gisco_nuts3") == "r"
    (entry, kind), = seen
    assert entry["id"] == "gisco_nuts3" and kind == "download"
    assert entry["url"].endswith("NUTS_RG_01M_2024_3035_LEVL_3.geojson")


def test_fetch_source_refuses_an_undeclared_id():
    """Only `config/sources.yaml` decides what gets fetched."""
    with pytest.raises(KeyError, match="not declared"):
        F.fetch_source("not_a_source")
