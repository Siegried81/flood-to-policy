"""The offline guard is what makes "the suite needs no network" true.

If a pytest or monkeypatch change ever broke the autouse fixture, every test
that quietly calls a real service would go green again with no warning, so the
guard gets a test of its own.
"""

from __future__ import annotations

import socket

import pytest

from tests.network_guard import NetworkAccessError


def test_a_dns_lookup_for_a_remote_host_is_refused():
    with pytest.raises(NetworkAccessError):
        socket.getaddrinfo("example.com", 80)


def test_a_connection_to_a_remote_address_is_refused():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        with pytest.raises(NetworkAccessError):
            sock.connect(("93.184.216.34", 80))


def test_loopback_stays_open_for_test_clients():
    """TestClient, anyio and the local Playwright helpers need it."""
    assert socket.getaddrinfo("127.0.0.1", 80)
