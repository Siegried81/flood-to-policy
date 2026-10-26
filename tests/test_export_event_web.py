"""Tests for the React app's July 2021 artefact (`scripts/export_event_web.py`).

The artefact is what a hosted or static app shows with no raw data at all, so
its shape is a contract with `web/src/components/Event2021.jsx`, and every
number in it must be the single-file tool's number, not a re-derivation. The
payload is built from the same synthetic tables as `test_policy_tool.py`; the
committed file, when present, is checked for size and shape only. No network,
no rasters.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from scripts import export_event_web as X
from src import policy_tool as P
from src import story_maps
from tests.test_policy_tool import _countries, _exposure, _layer, _products

ROOT = Path(__file__).resolve().parents[1]
TOP_KEYS = {"schema", "built", "team", "hero", "strip", "chart", "raster_classes", "places",
            "locator", "how_we_counted", "limits", "sources", "attribution"}


def _web_layer() -> dict:
    return {**_layer(), "bounds_3035": (0.0, 0.0, 8000.0, 6000.0),
            "outline_geojson": {"type": "MultiPolygon", "coordinates": [[[[0, 0], [10, 0], [10, 10], [0, 0]]]]},
            "observed_geojson": None}


@pytest.fixture(scope="module")
def payload() -> dict:
    return X.build_payload(
        _products(), _countries(), _exposure(), {"EMSR517_AOI15": _web_layer()},
        {"width": 600, "height": 400, "borders": "M0 0L1 1", "nuts": "M0 0L2 2",
         "labels": [("GERMANY", 10.0, 20.0)], "aoi": {"EMSR517_AOI15": "M0 0L5 0L5 5Z"}},
        built="2026-10-26")


def test_payload_has_the_contract_keys(payload):
    assert set(payload) == TOP_KEYS
    assert payload["schema"] == X.SCHEMA_VERSION
    assert payload["team"] == "Team N"
    assert [h["id"] for h in payload["hero"]] == ["missed", "harm", "europe", "when"]
    assert [s["country"] for s in payload["strip"]] == ["BE", "DE", "NL"]
    assert payload["chart"]["return_periods"] == [10, 100, 500]
    assert len(payload["raster_classes"]) == 5


def test_hero_is_the_policy_tool_hero(payload):
    expected = P.hero(_products(), _countries(), _exposure())
    for got, want in zip(payload["hero"], expected):
        assert got["big"] == want["big"]
        assert got["line"] == want["line"]
        if want["raw"] is None:
            assert got["raw"] is None
        else:
            assert math.isclose(got["raw"], want["raw"], rel_tol=1e-6)


def test_places_keep_selector_order_and_carry_their_map(payload):
    keys = [p["key"] for p in payload["places"]]
    assert keys[:2] == ["EMSR517_AOI15", "EMSR518_AOI01"]
    ahr = payload["places"][0]
    assert ahr["label"] == "Ahr valley" and ahr["named"] is True
    assert ahr["map"]["png"].startswith("data:image/png;base64,")
    assert ahr["map"]["towns"][0] == {"label": "Altenahr (Ahr)", "x": 390.0, "y": 20.0}
    assert ahr["map"]["outline"]["type"] == "MultiPolygon"
    liege = payload["places"][1]
    assert liege["label"] == "Liège (Meuse–Vesdre)"
    assert liege["map"] is None   # no layer: numbers only, the app says so


def test_missing_is_null_never_zero(payload):
    nl = next(r for r in payload["chart"]["rows"] if r["country"] == "NL")
    assert nl["shares"]["500"] is None and nl["shown"]["500"] == "n/a"
    liege = payload["places"][1]
    assert liege["figures"]["destroyed"] == "n/a" and liege["destroyed"] is None


def test_payload_is_strict_json(payload, tmp_path):
    size = X.write(payload, (tmp_path / "a.json", tmp_path / "b.json"))
    a, b = (tmp_path / "a.json").read_bytes(), (tmp_path / "b.json").read_bytes()
    assert a == b and len(a) == size
    json.loads(a, parse_constant=lambda c: pytest.fail(f"non-standard JSON constant {c}"))


def test_locator_lines_carry_the_boundary_credit(payload):
    assert payload["locator"]["nuts_d"]
    assert "EuroGeographics" in payload["attribution"]


def test_geojson_pixels_maps_and_drops_slivers():
    shapely = pytest.importorskip("shapely")
    square = shapely.geometry.box(0, 0, 100, 100)
    out = story_maps.geojson_pixels(square, lambda x, y: (x / 10, (100 - y) / 10))
    ring = out["coordinates"][0][0]
    assert ring[0] == ring[-1] and {tuple(p) for p in ring} == {(0, 0), (10, 0), (10, 10), (0, 10)}
    sliver = shapely.geometry.box(0, 0, 1, 1)
    assert story_maps.geojson_pixels(sliver, lambda x, y: (x / 1000, y / 1000)) is None
    assert story_maps.geojson_pixels(None, lambda x, y: (x, y)) is None


def test_png_palette_is_the_raster_classes():
    from PIL import Image
    import base64
    import io

    uri = story_maps.png_data_uri(np.array([[0, 3], [4, 1]], dtype=np.uint8))
    image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    rgb = image.convert("RGB")
    assert "#%02x%02x%02x" % rgb.getpixel((1, 0)) == story_maps.RASTER_CLASSES[3][0]
    assert "#%02x%02x%02x" % rgb.getpixel((0, 1)) == story_maps.RASTER_CLASSES[4][0]


@pytest.mark.parametrize("path", [X.OUT, X.WEB_OUT], ids=["data", "web-public"])
def test_the_built_artefact_is_compact_and_well_formed(path):
    if not path.exists():
        pytest.skip(f"{path.name} not built here")
    assert path.stat().st_size <= X.MAX_BYTES
    data = json.loads(path.read_text(encoding="utf-8"))
    assert TOP_KEYS <= set(data)
    assert data["places"][0]["key"] == P.HERO_AOI
    for place in data["places"]:
        if place["map"]:
            assert place["map"]["png"].startswith("data:image/png;base64,")
