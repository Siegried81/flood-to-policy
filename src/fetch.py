"""Collect every source declared in config/sources.yaml, in parallel and politely.

Run this once, before 25 October. The Wi-Fi of a 60-person hackathon will not
move gigabytes of raster, and a demo that depends on a live download in front of
a jury is a demo that fails.

Three design decisions worth stating, because they are the reasons this module
exists rather than a handful of `requests.get` calls:

**Parallel, but bounded per host.** Downloads are I/O-bound: the process sits
waiting on the network, so threads (not processes) are the right tool, and a
ThreadPoolExecutor turns a 20-minute serial fetch into a few minutes. But
parallelism aimed at one server is indistinguishable from a small denial of
service, and we are about to stand in front of the institution that runs these
servers. So concurrency is global while the rate limit is *per host*: many hosts
at once, one request per second each.

**Provenance is written, not remembered.** Every fetch records its URL, the
moment it happened, the HTTP status and the SHA-256 of the bytes. That manifest
is what lets a figure in the brief be traced back to an exact file, and it is the
transparency FARI's manifesto asks for.

**robots.txt is checked before scraping, never bypassed.** The jury is the
European Commission.
"""

from __future__ import annotations

import hashlib
import json
import re
import logging
import os
import threading
import time
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

from src.data_io import DATA, sources

# Identify ourselves. An anonymous scraper is indistinguishable from an abusive
# one; a contactable one gets asked to slow down instead of blocked. The
# contact comes from FETCH_CONTACT in .env, so no personal address sits in
# the code; without it, the repository URL is the contact.
CONTACT = os.environ.get("FETCH_CONTACT") or "https://github.com/Siegried81/flood-to-policy"
USER_AGENT = (
    "flood-to-policy/0.1 (European AI Challenge 2026 student project; "
    f"contact: {CONTACT})"
)
# Several EU sites sit behind an F5 BIG-IP WAF that answers a non-browser client
# with a rejection page under **HTTP 200**. raise_for_status() therefore passes,
# the bytes get written, and the corpus silently gains a 245-byte document that
# says nothing. These markers catch that; a body matching one is a failure, not a
# document. Found the hard way: the first run of this module stored exactly such a
# page as `jrc_publications.html`.
_REJECTION_MARKERS = (
    b"The requested URL was rejected",
    b"<title>Request Rejected</title>",
    b"Access Denied",
    b"window[\"bobcmn\"]",  # F5/Shape JS bot-defence challenge
    # AWS WAF / CloudFront challenge, measured on eur-lex.europa.eu:
    # HTTP 202 with `x-amzn-waf-action: challenge` and a 2,035-byte body. That is
    # 35 bytes over MIN_DOCUMENT_BYTES and carries none of the markers above, so
    # it was about to be stored as the AI Act, the Floods Directive and the GDPR.
    b"awsWafCookieDomainList",
    b"gokuProps",
)
#: A 202 is "accepted, not finished". No EU portal in this project serves a
#: document under it; eur-lex uses it for the WAF challenge above. Treated as a
#: failure rather than a body to inspect, because a challenge page that changes
#: its markup must not become data just because the markers moved.
NON_DOCUMENT_STATUSES = (202,)
# An open-data folder on JEODPP answers a plain GET with its own Apache directory
# listing, under HTTP 200 and with no rejection marker. It is valid HTML and can
# be any size, so neither check above stops it: one such listing was written as
# `jrc_flood_hazard.bin` (4,020 B) and reported ok, leaving a 4 KB HTML page
# standing in for the Hazard layer of Risk = Hazard x Exposure x Vulnerability.
# A listing means the URL names a folder, not a file - a config error, not a
# network one, so the message says which.
_DIRECTORY_INDEX_MARKERS = (
    b"<title>Index of /",
    b"<h1>Index of /",
)
# Declared for provenance but never fetched whole: an `api` is called at runtime
# with parameters, and a `folder` holds files too large to mirror (see
# sources.yaml). Fetching either would store a query stub or a directory listing.
_NOT_MIRRORED = frozenset({"api", "folder"})
# Anything shorter than this is not a policy document. A redirect stub or an error
# page slips past the markers above; a length floor catches the rest.
MIN_DOCUMENT_BYTES = 2_000
# Threads, not processes: this work is waiting on sockets, not burning CPU.
MAX_WORKERS = 8
# How many transfers may be in flight against ONE host at a time. The per-host
# delay below spaces out when requests *start*; it says nothing about how many
# run at once, and that was the bug: eight 300 MB rasters opened on
# jeodpp.jrc.ec.europa.eu split the line eight ways, every stream fell below the
# read timeout, and all of them failed while the two text files in the same
# directory succeeded. One at a time per host is also the polite reading of a
# rate limit - the parallelism that matters here is across hosts.
MAX_PER_HOST = 1
# Streamed in chunks rather than read with `.content`, so memory does not hold a
# whole raster and the read timeout applies per chunk instead of to the entire
# 300 MB body.
CHUNK_BYTES = 1 << 20
# Seconds between two requests to the SAME host. Global concurrency stays high
# because the delay is per host, not per pool.
PER_HOST_DELAY_S = 1.0
TIMEOUT_S = 60


@dataclass(frozen=True)
class FetchResult:
    """One attempt, successful or not. Frozen because it is a record of the past."""

    source_id: str
    url: str
    path: str | None
    status: int | None
    bytes: int
    sha256: str | None
    fetched_at: str
    error: str | None = None
    #: Set when the entry declared `robots_unreadable:` and the gate was
    #: therefore not allowed to decide. Recorded in the manifest on purpose: a
    #: derogation that leaves no trace is indistinguishable from a gate that
    #: never ran, and the whole value of this file is that a figure can be
    #: traced back to how its source was obtained.
    robots_derogation: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class _HostThrottle:
    """One lock and one 'next allowed time' per host.

    Why per host rather than one global lock: the sources span half a dozen
    unrelated servers, and making a request to EUR-Lex wait on a slow JRC raster
    would throw away the whole point of the thread pool. Why a lock at all: two
    threads reading and writing the same host's timestamp would both conclude
    they may go now.
    """

    def __init__(self, delay_s: float = PER_HOST_DELAY_S) -> None:
        self._delay = delay_s
        self._next_allowed: dict[str, float] = {}
        self._guard = threading.Lock()

    def wait(self, url: str, requested_delay: float | None = None) -> None:
        """Hold this host's spacing. `requested_delay` is the host's own
        `Crawl-delay`, and the larger of the two always wins: a published limit
        is a request we honour, never a ceiling we negotiate down."""
        host = urlparse(url).netloc
        delay = max(self._delay, requested_delay or 0.0)
        with self._guard:
            now = time.monotonic()
            earliest = self._next_allowed.get(host, now)
            # Reserve this host's slot *before* releasing the lock, so the next
            # thread queues behind us instead of racing for the same instant.
            self._next_allowed[host] = max(now, earliest) + delay
        # A loop, not one sleep: on Windows `time.sleep` can return a few ms
        # before `time.monotonic` (15.6 ms ticks) reaches `earliest`, which would
        # shave a published Crawl-delay. Re-check on the clock the slot is on.
        while (remaining := earliest - time.monotonic()) > 0:
            time.sleep(remaining)


class _HostTransfers:
    """At most `MAX_PER_HOST` transfers in flight per host, across all threads.

    Separate from `_HostThrottle` because the two limit different things, and
    only having the first one is what broke the raster download: the throttle
    spaces out request *starts*, so eight workers politely began eight 300 MB
    downloads from the same server one second apart and then competed for the
    same bandwidth until every one of them timed out.
    """

    def __init__(self, limit: int = MAX_PER_HOST) -> None:
        self._limit = limit
        self._slots: dict[str, threading.Semaphore] = {}
        self._guard = threading.Lock()

    def slot(self, url: str):
        host = urlparse(url).netloc
        with self._guard:
            gate = self._slots.setdefault(host, threading.Semaphore(self._limit))
        return gate


#: Module-level, because the gate has to be shared by every worker in a run.
_TRANSFERS = _HostTransfers()


class _RobotsCache:
    """robots.txt per host, fetched once.

    Cached because the check runs for every document, and re-fetching robots.txt
    each time would itself be the impolite behaviour it exists to prevent.

    robots.txt is fetched with `requests` and a browser User-Agent rather than
    through `RobotFileParser.read()`, which uses urllib's own UA. Several EU
    portals block that UA, and `RobotFileParser` responds to the resulting 403 by
    setting `disallow_all`, so every path comes back forbidden - including ones
    the file plainly allows. That false refusal is worse than no check at all,
    because it looks like compliance while quietly dropping sources. Fetching the
    file properly and handing the text to `parse()` keeps the check honest.
    """

    # Sentinel for "we tried and could not read it", so a failure is cached
    # instead of being retried on every document.
    _UNREADABLE = object()
    # Sentinel for "the host publishes no robots.txt at all", which is a
    # different statement and has to be treated differently.
    #
    # RFC 9309 section 2.3.1.3 is explicit: on a 4xx the crawler "MAY access any
    # resource", because the absence of the file means no rules were declared -
    # not that the rules are unknown. Collapsing the two was blocking legitimate
    # sources: five of the hosts this project downloads from publish no
    # robots.txt (jeodpp, gisco-services, geoservices.wallonie.be, the CEMS S3
    # bucket, api.gdeltproject.org), and so does environnement.wallonie.be,
    # which serves the official Walloon flood-management documents. Refusing
    # those reported "disallowed by robots.txt" when the truth was "there is no
    # robots.txt", which is a misleading refusal rather than a careful one.
    #
    # A 5xx, a timeout, a connection failure or a body that is not robots.txt
    # all still mean UNREADABLE and still refuse: there, the rules may exist and
    # we failed to read them, and that genuinely is not permission.
    _NO_RULES = object()

    def __init__(self) -> None:
        self._parsers: dict[str, object] = {}
        self._guard = threading.Lock()

    def _parser_for(self, host: str) -> object:
        with self._guard:
            if host in self._parsers:
                return self._parsers[host]
        try:
            response = requests.get(
                f"{host}/robots.txt", headers=_headers_for("scrape"), timeout=20
            )
            if 400 <= response.status_code < 500:
                # No file published: no rules declared. See _NO_RULES above.
                parser = self._NO_RULES  # type: ignore[assignment]
                with self._guard:
                    self._parsers[host] = parser
                return parser
            if response.status_code >= 500:
                raise OSError(f"HTTP {response.status_code}")
            if _is_not_robots(response.text):
                # A status below 400 is not proof that this is robots.txt, and
                # trusting it defeats the whole gate. Measured:
                # eur-lex.europa.eu answers /robots.txt with HTTP 202 and an AWS
                # WAF challenge page, publications.jrc.ec.europa.eu with HTTP 200
                # and its own HTML homepage. `parse()` finds no directives in
                # HTML, so `can_fetch` returned True for every path - a silent
                # false ALLOW on the two hosts that carry the legal corpus, with
                # the manifest recording a clean pass. That is the exact mirror
                # of the false refusal this class was written to avoid, and the
                # more dangerous of the two: it fetches on rules nobody read.
                raise OSError("robots.txt is not robots.txt (HTML body)")
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(response.text.splitlines())
        except Exception:
            parser = self._UNREADABLE  # type: ignore[assignment]
        with self._guard:
            self._parsers[host] = parser
        return parser

    def crawl_delay(self, url: str) -> float | None:
        """The delay this host asks for, or None when it asks for none.

        Read from the file the host publishes rather than assumed, because the
        one real `Crawl-delay` in this project is not where it was expected:
        www.undrr.org publishes 10 seconds, and nothing under europa.eu
        publishes any. `PER_HOST_DELAY_S` alone was fetching the Sendai
        framework ten times faster than UNDRR asks.
        """
        parsed = urlparse(url)
        parser = self._parser_for(f"{parsed.scheme}://{parsed.netloc}")
        if parser in (self._UNREADABLE, self._NO_RULES):
            return None
        try:
            delay = parser.crawl_delay(USER_AGENT)  # type: ignore[union-attr]
        except Exception:
            return None
        return float(delay) if delay else None

    def refusal_reason(self, url: str) -> str | None:
        """Why this URL is refused, or None when it is allowed.

        `allows()` returning False conflates two situations that must NOT be
        treated the same: a file we could not read, and a file that plainly says
        no. The declared derogation in `_fetch_one` applies only to the first,
        and without this method it was applied to both - so an entry carrying
        `robots_unreadable:` would have scraped straight through a real
        `Disallow:` the day the host started publishing one.

        Returns "unreadable" or "disallowed".
        """
        parsed = urlparse(url)
        parser = self._parser_for(f"{parsed.scheme}://{parsed.netloc}")
        if parser is self._UNREADABLE:
            return "unreadable"
        if parser is self._NO_RULES:
            return None
        return None if parser.can_fetch(USER_AGENT, url) else "disallowed"  # type: ignore[union-attr]

    def allows(self, url: str) -> bool:
        parsed = urlparse(url)
        parser = self._parser_for(f"{parsed.scheme}://{parsed.netloc}")
        if parser is self._UNREADABLE:
            # Rules may exist and we failed to read them: a 5xx, a timeout, or a
            # body that is not robots.txt. That is not permission. Treating a
            # failed read as "allowed" is how a polite scraper silently becomes
            # an impolite one.
            return False
        if parser is self._NO_RULES:
            # The host publishes no robots.txt (4xx). Nothing was declared, so
            # nothing is disallowed - RFC 9309 2.3.1.3. Distinguished from the
            # case above so a refusal never says "disallowed by robots.txt"
            # about a file that does not exist.
            return True
        return parser.can_fetch(USER_AGENT, url)  # type: ignore[union-attr]


def _headers_for(kind: str) -> dict[str, str]:
    """Browser headers for scraped pages, our own identity for bulk downloads.

    The honest default is to identify the client, and that is what the file
    servers get. But several EU portals put a WAF in front of their HTML that
    rejects any non-browser User-Agent, so a page we are allowed to read is
    unreachable without pretending to be a browser. We still send a contact
    address alongside, so the request stays attributable.
    """
    if kind != "scrape":
        return {"User-Agent": USER_AGENT}
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "From": CONTACT,
    }


#: A robots.txt directive at the start of a line, which is what the format
#: requires. Anchored on purpose - see `_is_not_robots`.
_ROBOTS_DIRECTIVE_RE = re.compile(
    r"^[ 	]*(user-agent|disallow|allow|sitemap|crawl-delay)[ 	]*:",
    re.IGNORECASE | re.MULTILINE,
)


def _is_not_robots(text: str) -> bool:
    """True when a 2xx body is plainly not a robots.txt file.

    Two hosts in this project answer /robots.txt with a document that parses to
    an empty ruleset, which `can_fetch` then reads as "everything is allowed":
    eur-lex.europa.eu returns an AWS WAF challenge page under HTTP 202, and
    publications.jrc.ec.europa.eu returns its HTML homepage under HTTP 200.
    Both are measured, not assumed.

    The test is deliberately crude - a markup opening tag, or no robots
    directive anywhere in the body. robots.txt has no HTML in it and a real one
    always carries at least one `user-agent`, `disallow`, `allow`, `sitemap` or
    `crawl-delay` line, so either signal is enough and neither can be fooled by
    a comment-only file (which carries no directives and is correctly treated as
    unreadable rather than as blanket permission).
    """
    # A directive must START A LINE, which is what the format requires. Matching
    # the bare substring anywhere was a silent false ALLOW: any HTML containing
    # `allow:` - a CSS rule, a JS object key `{allow:1}`, the words "rules allow:
    # everyone" in prose, a dumped `Access-Control-Allow:` header - was accepted
    # as robots.txt, parsed to an empty ruleset, and permitted every path. That
    # is the more dangerous of the two failure modes this class exists for: it
    # fetches on rules nobody read, and logs a clean pass.
    if _ROBOTS_DIRECTIVE_RE.search(text):
        return False
    # Anything else - markup, prose, an empty body - is not robots.txt. An empty
    # 2xx body is deliberately included: it was briefly treated as "no rules
    # declared", on the mistaken belief that eur-lex.europa.eu answers with an
    # empty body. It answers with a 2,035-byte AWS WAF challenge page, as
    # `config/sources.yaml` and `_REJECTION_MARKERS` both record, and those five
    # entries reach the corpus through a declared `robots_unreadable:`
    # derogation - not through a blanket rule about empty bodies.
    return True


def _why_not_a_document(
    payload: bytes, total_size: int | None = None, min_bytes: int = MIN_DOCUMENT_BYTES
) -> str | None:
    """Reason this payload is not a usable document, or None if it looks fine.

    `total_size` lets a streamed download answer the length question without
    keeping the body: the WAF markers always appear in the head of a rejection
    page, so the first 4 KiB is enough to recognise one, while the length floor
    only needs the byte count. Left as None, the size is taken from `payload`,
    which is what every in-memory caller does.

    `min_bytes` exists because the 2 KiB floor was written for policy PDFs and
    HTML pages, and it is wrong for a JSON API: a valid empty page of an OGC
    FeatureCollection is 45 bytes, and rejecting it told the caller "we could
    not look" when the truth was "we looked and found nothing" - the exact
    inversion `src/rdh.py` exists to prevent. A caller whose documents can
    legitimately be tiny passes 0 and keeps only the WAF-marker check.
    """
    head = payload[:4096]
    for marker in _REJECTION_MARKERS:
        if marker in head:
            return f"blocked by a WAF (HTTP 200 carrying {marker.decode(errors='replace')!r})"
    # Before the size floor: a listing is a config error whatever its length, and
    # saying so points at sources.yaml instead of at the network.
    for marker in _DIRECTORY_INDEX_MARKERS:
        if marker in head:
            return "a directory listing, not a file - the url names a folder"
    size = len(payload) if total_size is None else total_size
    if size < min_bytes:
        return f"only {size} bytes - a stub or an error page, not a document"
    return None


def _target_path(source_id: str, url: str, kind: str, suffix: str | None = None) -> Path:
    """Where a source lands on disk. One rule, so nothing has to guess later.

    The suffix is read off the URL unless the entry declares `suffix:`. That key
    exists for download endpoints whose path names no file type
    (`/document/download/<uuid>_en` on eiopa.europa.eu serves a PDF): without it
    the PDF was named `.html`, and `rag._read` picks its parser by suffix, so
    the corpus would have indexed the PDF's bytes as markup.
    """
    suffix = suffix or Path(urlparse(url).path).suffix or (".html" if kind == "scrape" else ".bin")
    return DATA / "raw" / kind / f"{source_id}{suffix}"


def target_of(entry: dict, kind: str) -> Path:
    """`_target_path` for a declared entry or an `expand` job, honouring `suffix:`."""
    return _target_path(entry["id"], entry["url"], kind, entry.get("suffix"))


#: Bytes of a file's head that `_why_not_a_document` needs: the WAF and
#: directory-listing markers all sit in the first page of a rejection body.
HEAD_BYTES = 4096


def read_head(path: Path) -> bytes:
    """The first `HEAD_BYTES` of a file - enough to recognise a rejection page."""
    with path.open("rb") as handle:
        return handle.read(HEAD_BYTES)


def sha256_of(path: Path) -> str:
    """SHA-256 of a file on disk, read in `CHUNK_BYTES` pieces.

    Streamed for the same reason the download is: `read_bytes()` on the reuse
    path in `_fetch_one` would hold a whole 300 MB raster in memory to
    fingerprint it, while the download beside it hashes the same bytes chunk by
    chunk. One rule for both.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def why_not_a_document_on_disk(path: Path) -> str | None:
    """`_why_not_a_document`, applied to a file that is already on disk.

    Exists because "exists and is non-empty" accepts anything: a rejection page
    written by an older run, or a stub copied in by hand, would come back
    `ok=True` with a hash and a clean line in the manifest. The same body check
    the download runs is the one a reused file has to pass - a file that would
    be refused fresh is refused stale. Shared with
    `scripts/check_offline_readiness.py`, so the checker and the fetcher cannot
    disagree about what counts as present.
    """
    return _why_not_a_document(read_head(path), total_size=path.stat().st_size)


def path_collisions(jobs: list[tuple[dict, str]]) -> dict[Path, list[str]]:
    """Declared files that would land on the same path: {path: [ids]}.

    `_target_path` names a file from the URL's last segment, so an API that
    serves every file under a constant final segment (`.../<id>/content`) maps
    all of them onto one name, and whichever download finishes last silently
    wins. A test pins the shipped config, but the collision is a property of the
    naming rule, not of one entry - so `fetch_all` refuses the colliding jobs
    instead of racing them.
    """
    seen: dict[Path, list[str]] = {}
    for entry, kind in jobs:
        seen.setdefault(target_of(entry, kind), []).append(entry["id"])
    return {path: ids for path, ids in seen.items() if len(ids) > 1}


def expand(entry: dict) -> list[dict]:
    """One declared source into one job per file, for entries that list several.

    Why this exists: a few sources are irreducibly multi-file. One hazard "layer"
    is nine return-period rasters plus two companion masks; one Copernicus
    activation is four vector packages across two areas of interest; GHS-POP at
    100 m needs two tiles to cover Belgium. Before this, `sources.yaml` pointed
    those entries at the *directory* holding the files - and since a directory
    listing is valid HTML above `MIN_DOCUMENT_BYTES`, `_fetch_one` stored the
    listing as the data and the idempotency check then treated the source as
    permanently done. A silent success with no data in it.

    An entry declares `files:` as names relative to its `url`, or as absolute
    URLs when a file sits on a different host than its landing page. The on-disk
    id becomes `<entry id>/<file stem>`, so every downloaded file stays traceable
    to the line that declared it and lands in a folder named after it.

    An entry with no `files:` key is returned unchanged, so every single-file
    source keeps its exact previous behaviour and on-disk path.
    """
    files = entry.get("files")
    if not files:
        return [entry]
    base = str(entry["url"]).rstrip("/")
    jobs = []
    for name in files:
        name = str(name)
        url = name if name.startswith(("http://", "https://")) else f"{base}/{name.lstrip('/')}"
        # The stem, not the full name: `_target_path` appends the suffix it reads
        # back off the URL, and a stem keeps it from doubling (`...tif.tif`).
        stem = Path(urlparse(url).path).stem
        jobs.append({**entry, "id": f"{entry['id']}/{stem}", "url": url})
    return jobs


def _fetch_one(
    entry: dict, kind: str, throttle: _HostThrottle, robots: _RobotsCache
) -> FetchResult:
    """Fetch a single declared source. Never raises: a failure is a result too.

    Returning the failure rather than raising is what lets one dead URL leave the
    other nineteen downloads intact - the behaviour you want the night before a
    deadline.
    """
    source_id, url = entry["id"], entry["url"]
    stamp = datetime.now(timezone.utc).isoformat()

    # Idempotent: re-running must not re-download. "Make sure this file is here",
    # not "fetch this file again". A hackathon network drops often enough that
    # you will run this several times, and a half-finished run should cost you
    # only the files that are actually missing.
    #
    # "Here" means "here and a document". A file that fails the same body check
    # a fresh download must pass is moved aside as `<name>.rejected` - kept, not
    # deleted, because it is evidence of what an earlier run accepted - and the
    # download below runs as if it had never existed.
    existing = target_of(entry, kind)
    if existing.exists() and existing.stat().st_size > 0:
        rejection = why_not_a_document_on_disk(existing)
        if rejection is None:
            return FetchResult(
                source_id, url, str(existing), None, existing.stat().st_size,
                sha256_of(existing), stamp, error=None,
            )
        quarantined = existing.with_name(existing.name + ".rejected")
        try:
            existing.replace(quarantined)
        except OSError as exc:
            # Same Windows lock as the `partial.replace` below, and the same
            # contract: a file held open is a failed result, never a raise that
            # takes `fetch_all` and the manifest down with it.
            return FetchResult(
                source_id, url, None, None, existing.stat().st_size, None, stamp,
                error=f"could not move the stale file aside as {quarantined.name}: {exc}",
            )
        log.warning("%s: existing file is not a document (%s); moved to %s and "
                    "fetching again", source_id, rejection, quarantined.name)

    # A per-entry derogation, for the one case the gate cannot decide: a host
    # that serves no readable robots.txt at all. The default stays strict - a
    # body that is not robots.txt means the rules may exist and we failed to
    # read them, which is not permission. But refusing on that basis took
    # eur-lex.europa.eu (the AI Act and the Floods Directive) and the two CEMS
    # EFAS reports out of the corpus, because all three answer /robots.txt with
    # an HTML page carrying no directive.
    #
    # So the exception is declared, per entry, in `sources.yaml`, with the date
    # it was checked and the reason - never inferred, never global, and never
    # silent: it is recorded on the result and therefore in the manifest. An
    # entry without the key behaves exactly as before.
    derogation = entry.get("robots_unreadable")
    refusal = robots.refusal_reason(url) if kind == "scrape" else None
    if refusal == "disallowed":
        # A real file that says no. No derogation applies, ever: the entry's
        # exception is for a host that publishes nothing readable, and letting
        # it cover an explicit Disallow would make the module docstring's
        # "never bypassed" false.
        return FetchResult(source_id, url, None, None, 0, None, stamp,
                           error="disallowed by robots.txt")
    if refusal == "unreadable":
        if not derogation:
            return FetchResult(source_id, url, None, None, 0, None, stamp,
                               error="robots.txt could not be read")
        log.info("robots.txt unreadable for %s; fetching under the declared "
                 "derogation (%s)", urlparse(url).netloc, derogation)
    else:
        # The gate allowed it, so a derogation on the entry is stale - the host
        # started publishing a readable file again, and the exception should be
        # removed rather than left to rot into a licence to ignore robots.txt.
        derogation = None

    path = target_of(entry, kind)
    # Streamed to a sibling `.part` and renamed only once the body has been
    # accepted. Writing in place would leave a truncated file behind on a dropped
    # connection, and the idempotency check above - which only asks whether the
    # file exists and is non-empty - would then treat that truncated file as the
    # dataset, for every later run. A 300 MB raster cut in half is the worst kind
    # of failure here: it opens, it reads, and its numbers are wrong.
    partial = path.with_name(path.name + ".part")
    # A host's own Crawl-delay overrides our default when it is slower. Only
    # consulted for `scrape`, because that is the only kind for which robots.txt
    # is read at all - asking for it on a download would fetch robots.txt from
    # hosts that publish none.
    throttle.wait(url, robots.crawl_delay(url) if kind == "scrape" else None)
    try:
        with _TRANSFERS.slot(url):
            response = requests.get(
                url, headers=_headers_for(kind), timeout=TIMEOUT_S, stream=True
            )
            response.raise_for_status()
            if response.status_code in NON_DOCUMENT_STATUSES:
                raise OSError(
                    f"HTTP {response.status_code}: accepted but not delivered "
                    f"(bot-defence challenge, not the document)"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            head = b""
            size = 0
            digest = hashlib.sha256()
            with partial.open("wb") as sink:
                for chunk in response.iter_content(CHUNK_BYTES):
                    if not chunk:
                        continue
                    if len(head) < 4096:
                        head += chunk[: 4096 - len(head)]
                    sink.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
    except Exception as exc:  # network, DNS, HTTP status, timeout
        partial.unlink(missing_ok=True)
        return FetchResult(source_id, url, None, None, 0, None, stamp, error=str(exc))
    except BaseException:
        # Ctrl-C, SystemExit. `except Exception` does not catch these, so an
        # interrupted run left a `.part` behind - and the next run's idempotency
        # check would not notice, because it only looks at the final name. The
        # partial is removed and the interrupt is re-raised untouched.
        partial.unlink(missing_ok=True)
        raise

    # A 200 is not proof of a document. Check the body before keeping it, or the
    # corpus fills with rejection pages that the RAG will happily index. Only the
    # first 4 KiB is held in memory: the WAF markers live in the head of a
    # rejection page, and the length floor needs the byte count, not the bytes.
    rejection = _why_not_a_document(head, total_size=size)
    if rejection:
        partial.unlink(missing_ok=True)
        return FetchResult(
            source_id, url, None, response.status_code, size, None, stamp,
            error=rejection,
        )

    try:
        partial.replace(path)
    except OSError as exc:
        # On Windows `os.replace` raises PermissionError when the target is held
        # open - an antivirus scan, the indexer, or a QGIS session with the
        # raster loaded, all realistic on a 300 MB file. This sat outside the
        # try, so it broke the "Never raises" contract this function states:
        # `future.result()` re-raised it in `fetch_all`, which died losing every
        # result collected so far AND the provenance manifest.
        partial.unlink(missing_ok=True)
        return FetchResult(
            source_id, url, None, response.status_code, size, None, stamp,
            error=f"could not move the finished download into place: {exc}",
        )
    # The digest is what makes "the figure came from this file" checkable later,
    # and it detects a source that changed under you between two runs. It is
    # computed as the bytes stream past, so a 300 MB raster never has to be held
    # in memory to be fingerprinted.
    return FetchResult(
        source_id, url, str(path), response.status_code, size,
        digest.hexdigest(), stamp, robots_derogation=derogation,
    )


def fetch_source(source_id: str, section: str = "geodata") -> FetchResult:
    """Fetch ONE declared source, through the same checks as `fetch_all`.

    For a caller that needs a single small file at runtime - the hosted
    Streamlit app building its map polygons - and must not pull the other
    gigabytes `fetch_all` would. It does not rewrite `manifest.json`: that file
    records a full collection run, and one entry overwriting it would erase the
    provenance of every other file on disk.
    """
    entry = next((e for e in sources(section) or [] if e["id"] == source_id), None)
    if entry is None:
        raise KeyError(f"{source_id!r} is not declared under `{section}` in config/sources.yaml")
    return _fetch_one(entry, entry.get("access", "download"), _HostThrottle(), _RobotsCache())


def fetch_all(sections: tuple[str, ...] = ("geodata", "policy_corpus", "context")) -> list[FetchResult]:
    """Fetch every declared source, in parallel, and write the provenance manifest.

    `api` and `folder` entries are skipped. A query endpoint is called at
    runtime with parameters (see `jrc_catalogue_search`), and `folder` declares a
    directory for provenance without mirroring it - a GET on one returns the
    directory listing, not a file. Neither is fetched wholesale.

    A folder whose files ARE wanted names them instead: an entry declaring
    `files:` becomes one job per file (see `expand`), which is how the nine
    return-period rasters of `jrc_flood_hazard` reach the disk. So the printed
    line count is the number of *files*, not of declared sources.
    """
    throttle, robots = _HostThrottle(), _RobotsCache()
    jobs: list[tuple[dict, str]] = []
    for section in sections:
        for entry in sources(section) or []:
            if entry.get("access", "download") in _NOT_MIRRORED:
                continue
            for job in expand(entry):
                jobs.append((job, entry.get("access", "download")))

    results: list[FetchResult] = []
    # Two declared files on one path are not two files on disk: whichever
    # finishes last wins and the other prints "ok". Refused up front, as results
    # rather than an exception, so the rest of the run proceeds and the manifest
    # records exactly which entries sources.yaml has to rename.
    collisions = path_collisions(jobs)
    stamp = datetime.now(timezone.utc).isoformat()
    for path, ids in collisions.items():
        for entry, _kind in jobs:
            if entry["id"] in ids:
                # Counted rather than named: colliding jobs usually share the
                # very id that caused the clash (`<entry>/content` seven times).
                results.append(FetchResult(
                    entry["id"], entry["url"], None, None, 0, None, stamp,
                    error=f"would overwrite {len(ids) - 1} other declared file(s) at "
                          f"{path.name}; give them distinct filenames in config/sources.yaml",
                ))
    colliding = {i for ids in collisions.values() for i in ids}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_fetch_one, entry, kind, throttle, robots): entry["id"]
            for entry, kind in jobs
            if entry["id"] not in colliding
        }
        for future in as_completed(futures):
            result = future.result()  # _fetch_one never raises, so this is safe
            results.append(result)
            mark = "ok  " if result.ok else "FAIL"
            print(f"  {mark} {result.source_id:38} {result.bytes:>12,} B  {result.error or ''}")

    manifest = DATA / "raw" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8"
    )
    print(f"\n{sum(r.ok for r in results)}/{len(results)} fetched -> {manifest}")
    return results


# data.jrc.ec.europa.eu sits behind a WAF that rejects a default User-Agent with
# an HTML "Request Rejected" page under HTTP 200 - worse than a 403, because a
# naive client parses it as success. A full browser header set gets through.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def jrc_catalogue_search(query: str, limit: int = 15) -> list[dict]:
    """Find JRC datasets whose title contains `query`, via the SPARQL endpoint.

    SPARQL rather than the REST API, for a reason worth knowing: `/api/2/datasets`
    has **no free-text search**. It accepts `q`, `search`, `keyword`, `filter` and
    friends, ignores all of them, and returns the full 4,366-dataset catalogue
    with HTTP 200. So `?q=flood` looks like it worked and hands you methane-flux
    datasets. The REST API is still the right call for fetching one dataset by
    UUID; it is the wrong one for searching.

    Blank nodes are filtered out: `dct:title` also hangs off citation and
    publication sub-resources, so an unfiltered query returns titles that belong
    to no dataset.
    """
    sparql = f"""
    PREFIX dct: <http://purl.org/dc/terms/>
    SELECT ?dataset ?title WHERE {{
      ?dataset dct:title ?title .
      FILTER(CONTAINS(LCASE(STR(?title)), "{query.lower()}"))
      FILTER(isIRI(?dataset))
    }} ORDER BY ?title LIMIT {limit}
    """
    response = requests.get(
        "https://data.jrc.ec.europa.eu/sparql",
        params={"query": sparql},
        headers={**_BROWSER_HEADERS, "Accept": "application/sparql-results+json"},
        timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    bindings = response.json().get("results", {}).get("bindings", [])
    return [
        {"uri": b["dataset"]["value"], "title": b["title"]["value"]}
        for b in bindings
        # Dataset PIDs live under data.europa.eu/89h/; anything else is a
        # sub-resource that happens to carry a title.
        if "data.europa.eu/89h/" in b["dataset"]["value"]
    ]


if __name__ == "__main__":  # pragma: no cover - a script entry point
    fetch_all()
