"""Tests for the choropleth's geometry file.

The map is the deliverable the jury looks at first, and it failed silently in
two ways that no exception reports: a file keyed on GISCO's own `NUTS_ID` joins
to nothing and draws 1,345 grey polygons, and a file left in EPSG:3035 is drawn
by `Choropleth.jsx` as metres-as-degrees, which puts Europe somewhere off the
coast of Antarctica at a scale of thousands. Both render "successfully". These
tests pin the two properties that make the file usable rather than merely valid.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from scripts.build_geometry import FIELDS, build


def _gisco_like(tmp_path, n: int = 3):
    """A miniature stand-in for the GISCO layer: EPSG:3035, GISCO's column names.

    Squares of 50 km with a notched edge, so simplification has something to
    remove and the vertex count is a meaningful assertion.
    """
    rows = []
    for i in range(n):
        x0, y0 = 4_000_000 + i * 100_000, 3_000_000
        notch = [(x0 + 25_000 + j * 500, y0 + (j % 2) * 400) for j in range(40)]
        rows.append(
            {
                "NUTS_ID": f"XX{i:03d}",
                "NAME_LATN": f"Region {i}",
                "CNTR_CODE": "XX",
                "geometry": Polygon(
                    [(x0, y0), *notch, (x0 + 50_000, y0),
                     (x0 + 50_000, y0 + 50_000), (x0, y0 + 50_000)]
                ),
            }
        )
    path = tmp_path / "gisco_like.geojson"
    gpd.GeoDataFrame(rows, crs="EPSG:3035").to_file(path, driver="GeoJSON")
    return path


def test_the_properties_carry_the_key_the_api_joins_on(tmp_path) -> None:
    """`Choropleth.jsx` reads `feature.properties[idKey]`, and `idKey` is what
    `/api/exposure` reports - `nuts_id`, from `api.main._region_key`. GISCO's own
    spelling is `NUTS_ID`, and a case mismatch joins to nothing without erroring."""
    collection = build(_gisco_like(tmp_path))
    properties = collection["features"][0]["properties"]
    assert set(properties) == {"nuts_id", "name"}
    assert properties["nuts_id"] == "XX000"
    assert "NUTS_ID" not in properties
    assert FIELDS["NUTS_ID"] == "nuts_id", "the join key must match api.main._region_key"


def test_the_output_is_degrees_not_metres(tmp_path) -> None:
    """The component projects lon/lat linearly onto the viewport. Metres reach
    seven digits, so a file left in EPSG:3035 draws off-screen rather than failing."""
    collection = build(_gisco_like(tmp_path))
    for feature in collection["features"]:
        for ring in feature["geometry"]["coordinates"]:
            for lon, lat in ring:
                assert -180 <= lon <= 180, f"{lon} is not a longitude"
                assert -90 <= lat <= 90, f"{lat} is not a latitude"


def test_simplification_drops_vertices_and_keeps_every_region(tmp_path) -> None:
    """Simplifying is what makes the file small enough to ship to a browser, but
    losing a region would silently remove it from the map AND from the legend's
    quantile breaks, which would move every other region's colour."""
    source = _gisco_like(tmp_path)
    detailed = build(source, tolerance_m=0.0)
    coarse = build(source, tolerance_m=5_000.0)

    assert len(coarse["features"]) == len(detailed["features"]) == 3

    def vertices(collection):
        return sum(
            len(ring)
            for feature in collection["features"]
            for ring in feature["geometry"]["coordinates"]
        )

    assert vertices(coarse) < vertices(detailed)


def test_coordinates_are_rounded_to_the_requested_precision(tmp_path) -> None:
    """Every digit past the simplification tolerance is noise the browser still
    downloads on each page load."""
    collection = build(_gisco_like(tmp_path), decimals=2)
    for feature in collection["features"]:
        for ring in feature["geometry"]["coordinates"]:
            for value in (c for point in ring for c in point):
                assert round(value, 2) == value


def test_a_layer_without_the_gisco_columns_fails_loudly(tmp_path) -> None:
    """Silently writing a file with no join key is the failure this whole module
    exists to prevent, so the wrong input has to stop the build."""
    path = tmp_path / "wrong.geojson"
    gpd.GeoDataFrame(
        [{"id": "XX000", "geometry": Polygon([(0, 0), (1, 0), (1, 1)])}],
        crs="EPSG:3035",
    ).to_file(path, driver="GeoJSON")

    with pytest.raises(SystemExit, match="NAME_LATN"):
        build(path)


def test_a_relative_out_path_does_not_crash_after_writing(tmp_path, monkeypatch, capsys) -> None:
    """`--out` is usually typed relative to the working directory, and
    `relative_to(ROOT)` raises on it - after the file is written, so the run
    exited 1 and never printed its summary."""
    from scripts import build_geometry

    source = _gisco_like(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["build_geometry.py", "--source", str(source), "--out", "regions.geojson"]
    )
    assert build_geometry.main() == 0
    assert (tmp_path / "regions.geojson").exists()
    assert "regions.geojson: 3 regions" in capsys.readouterr().out


def test_ensure_never_touches_the_network_when_the_file_exists(tmp_path, monkeypatch) -> None:
    """The venue demo runs with the Wi-Fi off. A machine that already built the
    geometry must not try GISCO at all, or every page load waits on a timeout."""
    from scripts import build_geometry
    from src import fetch

    out = tmp_path / "regions.geojson"
    out.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(fetch, "fetch_source", lambda *a, **k: pytest.fail("fetched"))
    assert build_geometry.ensure(out, tmp_path / "absent.geojson") is None


def test_ensure_reports_a_failed_download_and_writes_nothing(tmp_path, monkeypatch) -> None:
    """The hosted app shows this text on the page, so it must say what failed,
    and a failure must not leave a file that a later run would trust."""
    from scripts import build_geometry
    from src import fetch

    failed = fetch.FetchResult(
        "gisco_nuts3", "https://example.invalid", None, None, 0, None, "now",
        error="ConnectionError: offline",
    )
    monkeypatch.setattr(fetch, "fetch_source", lambda *a, **k: failed)
    out = tmp_path / "regions.geojson"
    reason = build_geometry.ensure(out, tmp_path / "absent.geojson")
    assert "GISCO" in reason and "offline" in reason
    assert not out.exists()


def test_ensure_builds_the_join_keyed_file_once_the_source_is_there(tmp_path, monkeypatch) -> None:
    """The success path the hosted app relies on: download, then the same build
    the CLI runs, keyed on `nuts_id`, written whole."""
    import json

    from scripts import build_geometry
    from src import fetch

    source = tmp_path / "gisco_nuts3.geojson"
    fixture = _gisco_like(tmp_path)

    def download(source_id, *a, **k):
        assert source_id == "gisco_nuts3"
        source.write_bytes(fixture.read_bytes())
        return fetch.FetchResult(source_id, "u", str(source), 200, 1, "h", "now", error=None)

    monkeypatch.setattr(fetch, "fetch_source", download)
    out = tmp_path / "processed" / "regions.geojson"
    assert build_geometry.ensure(out, source) is None
    features = json.loads(out.read_text(encoding="utf-8"))["features"]
    assert [f["properties"]["nuts_id"] for f in features] == ["XX000", "XX001", "XX002"]
    assert not (out.parent / "regions.geojson.part").exists()
