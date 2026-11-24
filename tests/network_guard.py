"""Offline guard shared by tests/conftest.py and team9/tests/conftest.py.

The suite is meant to pass with no network (CI has none for the tests that matter,
and a developer machine has one, which is exactly how a test that quietly calls a
real service stays green). This makes any non-loopback connection or DNS lookup
raise `NetworkAccessError` instead. Loopback (127.0.0.0/8, ::1, localhost) and
AF_UNIX / socketpair stay open because TestClient, anyio and the local Streamlit
and Playwright helpers use them. A test that really needs the network is marked
`@pytest.mark.network`. The error subclasses OSError so code that already
degrades on a network failure (the tiktoken table download, for instance) takes
its normal unavailable path and the test skips or falls back instead of erroring.
"""

from __future__ import annotations

import socket

import pytest

_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1", "", None}


class NetworkAccessError(OSError):
    """Raised when a test tries to reach a non-loopback host."""


def _is_loopback(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host in _LOOPBACK_NAMES or (isinstance(host, str) and host.startswith("127.")):
        return True
    return False


def _blocked(what: str, host) -> NetworkAccessError:
    return NetworkAccessError(
        f"tests are offline: refused {what} {host!r}. Mock the call, or mark the test "
        "with @pytest.mark.network if it really needs the network."
    )


def register_marker(config) -> None:
    config.addinivalue_line("markers", "network: the test may use the real network (opts out of the offline guard)")


@pytest.fixture(autouse=True)
def offline_guard(request, monkeypatch):
    """Patch socket connect and DNS resolution unless the test is marked `network`."""
    if request.node.get_closest_marker("network"):
        return
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def _target(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple):
            return address[0]
        return None  # AF_UNIX and friends are local

    def connect(self, address):
        host = _target(self, address)
        if host is not None and not _is_loopback(host):
            raise _blocked("connection to", host)
        return real_connect(self, address)

    def connect_ex(self, address):
        host = _target(self, address)
        if host is not None and not _is_loopback(host):
            raise _blocked("connection to", host)
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            raise _blocked("DNS lookup of", host)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    def gethostbyname(host):
        if not _is_loopback(host):
            raise _blocked("DNS lookup of", host)
        return "127.0.0.1"

    monkeypatch.setattr(socket, "gethostbyname", gethostbyname)
