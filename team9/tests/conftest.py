import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# The repo root, so the offline guard shared with tests/ imports when team9/tests runs alone.
sys.path.insert(1, str(Path(__file__).resolve().parents[2]))

from tests.network_guard import offline_guard, register_marker  # noqa: E402,F401  (autouse fixture)


def pytest_configure(config):
    register_marker(config)
