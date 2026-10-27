"""Tests for the static Europe view's frozen API answers (`scripts/export_europe_web.py`).

The export is a contract with `web/src/api.js`: the file names, the subset keys
and the fixed vulnerability settings must be the ones the client looks up. The
API is replaced by a fake client with canned answers, so these tests run no
Monte Carlo and need no tables. No network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import fastapi.testclient
import pytest

from scripts import export_europe_web as X

ROOT = Path(__file__).resolve().parents[1]

META = {
    "key": "nuts_id", "rows": 4, "regions": 2, "return_periods": [10, 100],
    "indicators": ["exposed_pop", "share_over_65", "poverty_rate_pct"],
    "frozen_at": "2026-10-26T00:00:00+00:00", "has_geometry": False,
    "has_context": True, "corpus_passages": 3, "approve_token_required": True,
}
CONTEXT_ROW = {
    "nuts_id": "BE335", "change_pct_ensemble_median_2041_2070": 12.0,
    "change_pct_ensemble_member_07_2041_2070": 9.0, "ensemble_robust_on_sign_2041_2070": True,
    "ensemble_size_uncertain_2041_2070": False, "built_share_exposed_rp100": 0.1,
    "exposed_built_m2_rp100": 5.0, "built_total_m2": 50.0, "apsfr_share": 0.2,
    "shared_basins": "Meuse", "basin_countries_max": 3, "natura_share_rp100": 0.4,
}


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return json.loads(json.dumps(self._body))


class FakeClient:
    """Answers the four routes the export reads, and records every POST."""

    posts: list[dict] = []

    def __init__(self, app) -> None:
        FakeClient.posts = []

    def get(self, path: str) -> FakeResponse:
        if path == "/api/meta":
            return FakeResponse(META)
        if path.startswith("/api/exposure?return_period="):
            period = int(path.rsplit("=", 1)[1])
            return FakeResponse({"key": "nuts_id", "return_period": period, "rows": []})
        if path == "/api/context":
            return FakeResponse({"key": "nuts_id", "rows": [CONTEXT_ROW], "climate_periods": []})
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path: str, json: dict) -> FakeResponse:
        assert path == "/api/vulnerability"
        FakeClient.posts.append(json)
        return FakeResponse({"return_period": json["return_period"], "rows": [],
                             "indicators": json["indicators"]})


@pytest.fixture
def exported(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(fastapi.testclient, "TestClient", FakeClient)
    X.export(tmp_path)
    return tmp_path


def test_subset_key_ignores_click_order():
    assert X.subset_key(["share_over_65", "exposed_pop"]) == "exposed_pop+share_over_65"
    assert X.subset_key(["exposed_pop", "share_over_65"]) == "exposed_pop+share_over_65"


def test_writes_one_exposure_and_one_vulnerability_file_per_period(exported):
    names = {p.name for p in exported.iterdir()}
    assert names == {"meta.json", "context.json", "exposure_rp10.json", "exposure_rp100.json",
                     "vulnerability_rp10.json", "vulnerability_rp100.json"}


def test_no_geometry_is_written(exported):
    # GISCO polygons stay out of the repository and the Space; the browser
    # fetches them from GISCO (web/src/api.js).
    for path in exported.iterdir():
        assert "FeatureCollection" not in path.read_text(encoding="utf-8")


def test_meta_says_static_and_asks_for_no_token(exported):
    meta = json.loads((exported / "meta.json").read_text(encoding="utf-8"))
    assert meta["static"] is True
    assert meta["approve_token_required"] is False
    assert meta["corpus_passages"] == 3


def test_meta_says_the_build_hosts_no_geometry(exported):
    # The static files carry no polygons; the view keys the GISCO fetch on
    # `static`, so the map still draws (EuropeView.jsx).
    meta = json.loads((exported / "meta.json").read_text(encoding="utf-8"))
    assert meta["has_geometry"] is False
    view = (ROOT / "web" / "src" / "EuropeView.jsx").read_text(encoding="utf-8")
    assert "m.has_geometry || m.static" in view


# Credits the Europe view must show, each as worded in DATA_NOTICE.md. The
# Copernicus Climate Change Service sentence and disclaimer are licence terms
# and must appear verbatim.
REQUIRED_CREDITS = (
    "© EuroGeographics for the administrative boundaries",
    "river flood hazard maps for",
    "doi:10.2905/1D128B6C-A4EE-4858-9E34-6210707F3C81",
    "GHS-POP and",
    "GHS-BUILT-S R2023A, epoch 2025 at 1 km",
    "Source: Eurostat",
    "Eurostat bears no responsibility for these derived figures",
    "WFD river basin districts",
    "Source: European Environment Agency, reported by the Member States",
    "Contains modified Copernicus Climate Change Service information 2026",
    "(doi:10.24381/cds.73237ad6), CC BY 4.0",
    "Neither the European Commission nor ECMWF is responsible for any use that may be "
    "made of the Copernicus information or data it contains.",
)


def _flat(text: str) -> str:
    """Collapse line breaks and JS string concatenation, so a phrase wrapped
    differently in the notice and in the view still compares equal."""
    text = re.sub(r'"\s*\+\s*"', "", text)
    return re.sub(r"\s+", " ", text)


def test_europe_view_shows_the_credits_of_the_data_notice():
    notice = _flat((ROOT / "data" / "processed" / "DATA_NOTICE.md").read_text(encoding="utf-8"))
    view = _flat((ROOT / "web" / "src" / "EuropeView.jsx").read_text(encoding="utf-8"))
    for credit in REQUIRED_CREDITS:
        assert credit in notice, f"not in DATA_NOTICE.md: {credit}"
        assert credit in view, f"not in EuropeView.jsx: {credit}"
    # Rendered outside every tab and every STATIC_BUILD branch, so both builds show it.
    assert "EUROPE_SOURCES.map" in view


def test_local_client_asks_the_api_for_the_2021_story_first():
    # Locally /api/event2021 serves the --full build; the public file is the
    # fallback, and the only source of a static build.
    api = (ROOT / "web" / "src" / "api.js").read_text(encoding="utf-8")
    body = api[api.index("export async function getEvent2021"):]
    assert body.index('request("/api/event2021")') < body.index("event_2021_web.json")
    assert "if (!STATIC_BUILD)" in body


def test_context_keeps_only_the_columns_the_panel_draws(exported):
    row = json.loads((exported / "context.json").read_text(encoding="utf-8"))["rows"][0]
    assert "change_pct_ensemble_member_07_2041_2070" not in row
    assert "natura_share_rp100" not in row
    for kept in ("nuts_id", "change_pct_ensemble_median_2041_2070",
                 "ensemble_robust_on_sign_2041_2070", "ensemble_size_uncertain_2041_2070",
                 "built_share_exposed_rp100", "exposed_built_m2_rp100", "built_total_m2",
                 "apsfr_share", "shared_basins", "basin_countries_max"):
        assert kept in row, kept


def test_every_indicator_subset_is_ranked_at_the_panel_defaults(exported):
    frozen = json.loads((exported / "vulnerability_rp100.json").read_text(encoding="utf-8"))
    assert frozen["perturbation"] == 0.3 and frozen["top_n"] == 10
    assert len(frozen["answers"]) == 7  # 2**3 - 1 non-empty subsets
    assert "exposed_pop+poverty_rate_pct+share_over_65" in frozen["answers"]
    assert {p["perturbation"] for p in FakeClient.posts} == {X.PERTURBATION}
    assert {p["top_n"] for p in FakeClient.posts} == {X.TOP_N}
    assert len(FakeClient.posts) == 14  # 7 subsets x 2 periods


def test_client_defaults_match_the_frozen_settings():
    # api.js refuses any other setting, so the panel must open on these.
    panel = (ROOT / "web" / "src" / "components" / "VulnerabilityPanel.jsx").read_text(encoding="utf-8")
    assert f"useState({X.PERTURBATION})" in panel
    assert f"useState({X.TOP_N})" in panel


def test_static_client_reads_the_exported_names_and_gisco():
    api = (ROOT / "web" / "src" / "api.js").read_text(encoding="utf-8")
    for name in ("meta.json", "context.json", "exposure_rp${period}.json",
                 "vulnerability_rp${period}.json"):
        assert name in api, name
    assert "gisco-services.ec.europa.eu" in api
    assert 'join("+")' in api
