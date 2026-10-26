"""Tests for the declared-flood-risk layer.

The failure modes pinned here are the ones that would make the kit assert
something about a government: an empty layer read as "nothing was declared", two
reporting cycles overlaid as if they were one, and overlapping designations
summed into a share above 1. The strongest claim this module can make is "the
State declared nothing here", so every path that could produce it by accident has
a test.

No network: `_page` is monkeypatched everywhere.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from src import apsfr
from src.data_io import WORKING_CRS


#: Test coordinates are given in kilometres and scaled to metres here.
#:
#: Not cosmetic. EPSG:3035 is metres, and a box written as (0, 0, 10, 10) is a
#: region ten metres across - a doorway, not an arrondissement. Fixtures at that
#: scale pass or fail on tolerances rather than on the code, which is how a
#: vertex-thinning step that the real layer later disproved looked correct here.
KM = 1_000.0


def _admin(*boxes) -> gpd.GeoDataFrame:
    """A NUTS3-shaped frame in EPSG:3035, one row per box, boxes in km."""
    return gpd.GeoDataFrame(
        {"nuts_id": [f"XX{i}" for i in range(len(boxes))]},
        geometry=[box(*(c * KM for c in b)) for b in boxes],
        crs=WORKING_CRS,
    )


def _geojson(*boxes, country="BE", cycle="2018", exceeded=False) -> dict:
    """An ArcGIS GeoJSON page, with boxes given in EPSG:3035 and reprojected to
    4326 the way the service would return them."""
    frame = gpd.GeoDataFrame(
        {"countryCode": [country] * len(boxes), "cYear": [cycle] * len(boxes)},
        geometry=[box(*(c * KM for c in b)) for b in boxes],
        crs=WORKING_CRS,
    ).to_crs("EPSG:4326")
    payload = frame.__geo_interface__
    return {
        "type": "FeatureCollection",
        "features": list(payload["features"]),
        "properties": {"exceededTransferLimit": exceeded},
    }


@pytest.fixture
def no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(apsfr, "CACHE_DIR", tmp_path)
    return tmp_path


# --- the claim this module must never make by accident --------------------------

def test_an_empty_layer_raises_rather_than_reporting_every_region_undeclared(
    no_cache, monkeypatch
):
    """"The State declared nothing here" is the strongest sentence this layer can
    produce, and an empty response would produce it for every region in Europe at
    once. It has to be an error, not a result."""
    monkeypatch.setattr(apsfr, "_page", lambda offset, cycle: {"features": []})
    with pytest.raises(apsfr.ApsfrUnavailable, match="no polygons"):
        apsfr.polygons(cycle="2018")


def test_an_unreachable_service_raises(no_cache, monkeypatch):
    def boom(offset, cycle):
        raise apsfr.ApsfrUnavailable("HTTP 500 at offset 0")

    monkeypatch.setattr(apsfr, "_page", boom)
    with pytest.raises(apsfr.ApsfrUnavailable, match="500"):
        apsfr.polygons(cycle="2018")


def test_a_layer_that_never_stops_paging_raises_rather_than_truncating(
    no_cache, monkeypatch
):
    """A truncated layer understates every declaration, which is the same wrong
    direction as an empty one - just quieter."""
    monkeypatch.setattr(apsfr, "MAX_PAGES", 3)
    monkeypatch.setattr(
        apsfr, "_page",
        lambda offset, cycle: _geojson((0, 0, 10, 10), exceeded=True),
    )
    with pytest.raises(apsfr.ApsfrUnavailable, match="still paging"):
        apsfr.polygons(cycle="2018")


# --- the two reporting cycles ---------------------------------------------------

def test_only_one_reporting_cycle_is_ever_requested(no_cache, monkeypatch):
    """Measured on the live service 2026-10-07: `cYear` is 2010 for 496 polygons
    across 5 countries and 2018 for 12,173 across 25, and AT, DE, ES and FR are in
    BOTH. Overlaying them designates the same ground twice."""
    seen = []

    def page(offset, cycle):
        seen.append(cycle)
        return _geojson((0, 0, 10, 10), cycle=cycle)

    monkeypatch.setattr(apsfr, "_page", page)
    apsfr.polygons(cycle="2018")
    assert seen == ["2018"]


def test_the_cycle_is_in_the_where_clause_and_the_offset_in_the_request(monkeypatch):
    """A source-level check on `_page`, because the filter is the thing that
    stops the cycles mixing and `maxAllowableOffset` is the thing without which
    the request is HTTP 500."""
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"features": []}

    def get(url, params=None, timeout=None):
        captured.update(params)
        return _Resp()

    monkeypatch.setattr(apsfr.requests, "get", get)
    apsfr._page(600, "2018")
    assert captured["where"] == "cYear='2018'"
    assert captured["resultOffset"] == 600
    assert captured["outSR"] == 4326
    assert captured["maxAllowableOffset"] == apsfr.MAX_ALLOWABLE_OFFSET


# --- the share ------------------------------------------------------------------

def test_overlapping_designations_are_dissolved_not_summed(no_cache, monkeypatch):
    """APSFRs reported under different units of management overlap. Summing the
    intersected pieces counts the overlap once per polygon and puts a share above
    1 on a delta, which is not a number any share can take."""
    # One region 10 x 10. Two APSFRs covering the same left half.
    monkeypatch.setattr(
        apsfr, "_page",
        lambda offset, cycle: _geojson((0, 0, 5, 10), (0, 0, 5, 10)),
    )
    out = apsfr.declared_by_region(_admin((0, 0, 10, 10)))
    assert out["apsfr_share"].iloc[0] == pytest.approx(0.5, abs=0.01)
    assert out["apsfr_declared"].iloc[0]


def test_a_region_outside_every_polygon_is_measured_as_undeclared(
    no_cache, monkeypatch
):
    """Here a zero IS a measurement: the layer is continental, so a region that
    intersects nothing really was not designated."""
    monkeypatch.setattr(
        apsfr, "_page", lambda offset, cycle: _geojson((0, 0, 5, 5))
    )
    out = apsfr.declared_by_region(_admin((1_000, 1_000, 1_010, 1_010)))
    assert out["apsfr_share"].iloc[0] == 0.0
    assert not out["apsfr_declared"].iloc[0]


def test_a_fully_designated_region_reads_one(no_cache, monkeypatch):
    monkeypatch.setattr(
        apsfr, "_page", lambda offset, cycle: _geojson((-10, -10, 20, 20))
    )
    out = apsfr.declared_by_region(_admin((0, 0, 10, 10)))
    assert out["apsfr_share"].iloc[0] == pytest.approx(1.0, abs=0.01)


def test_no_share_can_exceed_one(no_cache, monkeypatch):
    """Three mutually overlapping designations over the whole region: summed they
    would read 3.0."""
    monkeypatch.setattr(
        apsfr, "_page",
        lambda offset, cycle: _geojson(
            (-1, -1, 11, 11), (-2, -2, 12, 12), (0, 0, 10, 10)
        ),
    )
    out = apsfr.declared_by_region(_admin((0, 0, 10, 10)))
    assert out["apsfr_share"].max() <= 1.0 + 1e-9


def test_the_cycle_travels_with_the_figure_as_text(no_cache, monkeypatch):
    """A reporting vintage, like NUTS. Text rather than a number so it cannot
    drift into a weighted mean the way a year stored as an integer would."""
    monkeypatch.setattr(
        apsfr, "_page", lambda offset, cycle: _geojson((0, 0, 5, 5), cycle=cycle)
    )
    out = apsfr.declared_by_region(_admin((0, 0, 10, 10)), cycle="2018")
    assert out["apsfr_cycle"].iloc[0] == "2018"
    assert out["apsfr_cycle"].dtype.kind not in "if"


def test_the_figures_are_computed_in_a_metric_crs(no_cache, monkeypatch):
    """The service publishes in Web Mercator, which inflates area by roughly
    1/cos^2(latitude) - about 2.4x at 50 degrees North and unevenly across Europe,
    so even a ratio taken at two latitudes is wrong. A half-covered region must
    read 0.5 wherever it sits."""
    monkeypatch.setattr(
        apsfr, "_page", lambda offset, cycle: _geojson((0, 0, 5, 10), (0, 3_000, 5, 3_010))
    )
    # Two identical-sized regions, one far north of the other in EPSG:3035.
    admin = _admin((0, 0, 10, 10), (0, 3_000, 10, 3_010))
    out = apsfr.declared_by_region(admin)
    assert out["apsfr_share"].iloc[0] == pytest.approx(0.5, abs=0.01)
    assert out["apsfr_share"].iloc[1] == pytest.approx(0.5, abs=0.01)


def test_a_country_the_layer_never_covered_is_not_reported_as_undeclared(
    no_cache, monkeypatch
):
    """The false accusation this column exists to prevent.

    Measured against the service 2026-10-07: the layer holds 26 country codes
    across BOTH reporting cycles and Ireland is not one of them - zero polygons,
    for a Member State that certainly designates areas under Article 5. So
    `apsfr_declared == False` has two causes that look identical, and only one of
    them is about the State. Where the country was never covered the share is NaN,
    because nothing was measured, and 0.0 would read as a finding.
    """
    monkeypatch.setattr(
        apsfr, "_page", lambda offset, cycle: _geojson((0, 0, 5, 10), country="BE")
    )
    admin = _admin((0, 0, 10, 10), (0, 0, 10, 10), (50, 50, 60, 60))
    admin["country"] = ["BE", "IE", "BE"]

    out = apsfr.declared_by_region(admin)

    # Belgium is covered: a measured share, and a measured zero further away.
    assert out["apsfr_country_reported"].tolist() == [True, False, True]
    assert out["apsfr_share"].iloc[0] == pytest.approx(0.5, abs=0.01)
    assert out["apsfr_share"].iloc[2] == 0.0
    assert out["apsfr_declared"].iloc[2] is False or not out["apsfr_declared"].iloc[2]

    # Ireland is not: not measured, not a zero.
    assert pd.isna(out["apsfr_share"].iloc[1])


def test_a_structural_overcount_raises_instead_of_being_clipped(no_cache, monkeypatch):
    """The clamp on float noise must not become a mask for a real bug. If the
    pieces were ever summed instead of dissolved the share would be far above 1,
    and that has to stop the build rather than print as 100%."""
    monkeypatch.setattr(
        apsfr, "_page", lambda offset, cycle: _geojson((0, 0, 10, 10))
    )
    admin = _admin((0, 0, 10, 10))
    out = apsfr.declared_by_region(admin)
    assert out["apsfr_share"].iloc[0] == pytest.approx(1.0, abs=1e-6)
