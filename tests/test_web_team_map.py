"""The React app links Team 9's map, and the file it links is the real map.

The map sat in web/public/team9/ and therefore in every dist/ and Docker image,
but no view pointed at it, so the only way to see it in the container was to
type /team9/flood_map.html by hand. These tests read the sources (the repo has
no JS test runner) and pin both halves: the view exists and names the file, and
the file is the 37 MB map rather than a Git LFS pointer.

The CI test job checks out without LFS (37 MB a run would spend the free LFS
bandwidth in about 27 runs), so there the file IS a pointer and the size check
is skipped, saying why. It runs on any machine that has done `git lfs pull`,
and the publish workflow checks out with `lfs: true`.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
TEAM_MAP = WEB / "public" / "team9" / "flood_map.html"


def team_map_is_pointer() -> bool:
    """True when the checkout holds the Git LFS pointer instead of the map."""
    return TEAM_MAP.read_bytes()[:40].startswith(b"version https://git-lfs")


needs_team_map = pytest.mark.skipif(
    team_map_is_pointer(), reason="Team 9 map is a Git LFS pointer here; run `git lfs pull`"
)


def test_app_has_a_team_map_view():
    app = (WEB / "src" / "App.jsx").read_text(encoding="utf-8")
    views = re.search(r"const VIEWS = \[(.*?)\];", app).group(1)
    # First, so the app opens on the team's map.
    assert views.split(",")[0].strip() == '"Team 9 map"'
    assert '{view === "Team 9 map" && <TeamMap />}' in app


def test_team_map_points_at_the_public_file():
    src = (WEB / "src" / "components" / "TeamMap.jsx").read_text(encoding="utf-8")
    rel = re.search(r"\}(team9/[\w./-]+\.html)`", src).group(1)
    # BASE_URL keeps the link right under a sub-path build (VITE_BASE).
    assert "import.meta.env.BASE_URL" in src
    assert (WEB / "public" / rel).is_file()


@needs_team_map
def test_team_map_file_is_the_full_map():
    assert TEAM_MAP.stat().st_size > 1_000_000
