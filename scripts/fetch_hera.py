"""Download the HERA v2 river discharge files, 1991-2020, resumably and one at a time.

Thirty NetCDF files of about 2.3 GB each from the JRC open-data FTP
(`hera_river_discharge` in config/sources.yaml), about 69 GB in all. At the
0.7 MB/s measured on this connection that is a day, so the download has to
survive being interrupted:

- **Resumable.** Bytes land in `<name>.part`; a rerun asks the server for the
  rest with an HTTP `Range` header (the server sends `Accept-Ranges: bytes`)
  and appends. The `.part` file is renamed only once it has exactly the size the
  server announced, so a file under its final name is a complete file - which
  is what `src/hera.py` relies on.
- **Skips what is done.** A final file whose size matches the server's
  `Content-Length` is not touched.
- **Retries with backoff** on a dropped connection or a 5xx, resuming from
  wherever the bytes stopped.
- **Polite.** One connection, one file at a time, and the kit's identifying
  User-Agent from `src/fetch.py`.
- **Checked.** A finished file must start with the HDF5 signature: the JEODPP
  server answers some requests with an HTML directory listing under HTTP 200.

Run:

    python scripts/fetch_hera.py --dry-run            # list, fetch nothing
    python scripts/fetch_hera.py                      # 1991-2020
    python scripts/fetch_hera.py --years 2019 2020    # some years only
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import hera  # noqa: E402
from src.data_io import sources  # noqa: E402
from src.fetch import USER_AGENT  # noqa: E402

CHUNK = 8 * 2**20
RETRIES = 6
BACKOFF_S = 5.0
TIMEOUT = (30, 120)  # connect, read per chunk


def base_url() -> str:
    """The folder URL of `hera_river_discharge`, from config/sources.yaml."""
    for section in sources().values():
        if isinstance(section, list):
            for entry in section:
                if isinstance(entry, dict) and entry.get("id") == "hera_river_discharge":
                    return entry["url"].rstrip("/") + "/"
    raise SystemExit("config/sources.yaml declares no hera_river_discharge source.")


def remote_size(session, url: str) -> int | None:
    """The size the server announces for `url`, or None if it does not say."""
    response = session.head(url, allow_redirects=True, timeout=TIMEOUT)
    response.raise_for_status()
    if "text/html" in response.headers.get("Content-Type", ""):
        raise RuntimeError(f"{url} answers with HTML, not a file.")
    length = response.headers.get("Content-Length")
    return int(length) if length else None


def download(
    session,
    url: str,
    target: Path,
    *,
    retries: int = RETRIES,
    backoff_s: float = BACKOFF_S,
    sleep=time.sleep,
    progress=print,
) -> str:
    """Bring `target` to the server's full size; returns "skipped" or "downloaded".

    `session` is a `requests.Session` (or anything with its `head`/`get`), so the
    logic is testable without a network. A failure that brought no new bytes
    counts against `retries`; one that did resets the count, because a link that
    drops every 500 MB is slow, not broken.
    """
    size = remote_size(session, url)
    if target.exists() and size is not None and target.stat().st_size == size:
        return "skipped"
    partial = target.with_name(target.name + ".part")
    if target.exists():
        # Under its final name but the wrong size: an older, interrupted copy.
        target.replace(partial)
    failures = 0
    while True:
        have = partial.stat().st_size if partial.exists() else 0
        if size is not None and have > size:
            partial.unlink()
            have = 0
        if size is not None and have == size:
            break
        headers = {"User-Agent": USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        before = have
        try:
            with session.get(url, headers=headers, stream=True, timeout=TIMEOUT) as response:
                if response.status_code == 416:
                    # Nothing left to send for this range: either complete or stale.
                    if size is None or have == size:
                        break
                    partial.unlink()
                    continue
                response.raise_for_status()
                if have and response.status_code != 206:
                    have = 0  # the server ignored the range and sends it all
                mode = "ab" if have else "wb"
                with open(partial, mode) as fh:
                    last = time.monotonic()
                    for chunk in response.iter_content(CHUNK):
                        fh.write(chunk)
                        have += len(chunk)
                        if progress is not None and time.monotonic() - last > 30:
                            share = f"{have / size:.1%}" if size else f"{have:,} B"
                            progress(f"    {target.name}: {share}")
                            last = time.monotonic()
            if size is None:
                break
            if have < size:
                # The server closed the stream early without an error: resume.
                raise requests.ConnectionError(f"stream ended at {have:,} of {size:,} B")
        except (requests.RequestException, OSError) as exc:
            have = partial.stat().st_size if partial.exists() else 0
            failures = 0 if have > before else failures + 1
            if failures > retries:
                raise RuntimeError(f"{target.name}: gave up after {retries} retries ({exc})")
            wait = backoff_s * 2 ** max(failures - 1, 0)
            if progress is not None:
                progress(f"    {target.name}: {type(exc).__name__}, retrying in {wait:.0f} s")
            sleep(wait)
    with open(partial, "rb") as fh:
        if not fh.read(4) == b"\x89HDF":
            raise RuntimeError(f"{partial.name} is not an HDF5/NetCDF-4 file; left in place.")
    partial.replace(target)
    return "downloaded"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", nargs="*", type=int, default=list(hera.YEARS))
    parser.add_argument("--dry-run", action="store_true", help="List the files, fetch nothing.")
    args = parser.parse_args(argv)

    url = base_url()
    names = [hera.FILE_NAME.format(year=y) for y in args.years]
    print(f"{len(names)} file(s) from {url} into {hera.HERA_DIR.relative_to(ROOT)}")
    if args.dry_run:
        for name in names:
            state = "on disk" if (hera.HERA_DIR / name).exists() else "missing"
            print(f"  {name} ({state})")
        print("--dry-run: nothing fetched.")
        return 0
    hera.HERA_DIR.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        for i, name in enumerate(names, 1):
            print(f"[{i}/{len(names)}] {name}")
            state = download(session, url + name, hera.HERA_DIR / name)
            print(f"  {state}")
    print("Then cache the annual maxima: python -m src.hera")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
