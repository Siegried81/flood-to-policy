"""Tests for the shared-basin layer.

Two halves, tested apart. The fetch is mocked everywhere - no test in this suite
touches the network, and this service in particular takes about five minutes and
answers HTTP 500 to a page it dislikes, so a live test would be slow AND flaky.
The geometry half runs on squares small enough to check by hand.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pytest
import requests
from shapely.geometry import Polygon, box, mapping

from src import basins


class _Response:
    """Just enough of `requests.Response` for `_page`."""

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _feature(code: str, geom) -> dict:
    return {
        "type": "Feature",
        "properties": {"thematicIdIdentifier": code, "nameTextInternational": code},
        "geometry": mapping(geom),
    }


def _payload(codes, geoms, *, more: bool) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [_feature(c, g) for c, g in zip(codes, geoms)],
        "exceededTransferLimit": more,
    }


# --- the fetch ------------------------------------------------------------------

def test_a_cached_file_is_read_without_touching_the_network(tmp_path):
    """The point of the cache: the morning of the event has no network budget for
    a service that needs five minutes."""
    cache = tmp_path / "districts.geojson"
    cache.write_text(
        json.dumps({"type": "FeatureCollection",
                    "features": [_feature("A", box(0, 0, 1, 1))]}),
        encoding="utf-8",
    )
    with patch.object(basins.requests, "get", side_effect=AssertionError("network")):
        frame = basins.districts(cache=cache)
    assert len(frame) == 1
    assert frame["thematicIdIdentifier"].iat[0] == "A"


def test_paging_continues_until_the_service_stops_asking(tmp_path):
    """`exceededTransferLimit` is the only signal that there is more, and the
    layer is 196 districts against a page of 25 - so a fetch that reads one page
    and stops would silently return an eighth of Europe."""
    pages = [
        _payload(["A"], [box(0, 0, 1, 1)], more=True),
        _payload(["B"], [box(1, 0, 2, 1)], more=True),
        _payload(["C"], [box(2, 0, 3, 1)], more=False),
    ]
    with patch.object(basins.requests, "get", side_effect=[_Response(p) for p in pages]):
        frame = basins.districts(cache=tmp_path / "c.geojson")
    assert sorted(frame["thematicIdIdentifier"]) == ["A", "B", "C"]


def test_the_fetch_is_cached_for_next_time(tmp_path):
    cache = tmp_path / "nested" / "districts.geojson"
    page = _payload(["A"], [box(0, 0, 1, 1)], more=False)
    with patch.object(basins.requests, "get", return_value=_Response(page)):
        basins.districts(cache=cache)
    assert cache.exists()
    assert json.loads(cache.read_text(encoding="utf-8"))["features"]


def test_an_unreachable_service_says_so_and_says_what_to_do(tmp_path):
    """An `access: api` source has no mirrored copy, so the message has to say
    that caching it in advance is the fix - not just that a GET failed."""
    with patch.object(
        basins.requests, "get", side_effect=requests.ConnectionError("down")
    ):
        with pytest.raises(basins.BasinsUnavailable, match="cache it before the event"):
            basins.districts(cache=tmp_path / "c.geojson")


def test_a_service_that_never_stops_paging_is_given_up_on(tmp_path):
    """`exceededTransferLimit` forever means the offset is being ignored, which
    would otherwise be an infinite loop against someone else's server."""
    page = _payload(["A"], [box(0, 0, 1, 1)], more=True)
    with patch.object(basins.requests, "get", return_value=_Response(page)):
        with pytest.raises(basins.BasinsUnavailable, match="pages"):
            basins.districts(cache=tmp_path / "c.geojson")


def test_an_empty_answer_is_an_error_not_an_empty_map(tmp_path):
    page = {"type": "FeatureCollection", "features": [], "exceededTransferLimit": False}
    with patch.object(basins.requests, "get", return_value=_Response(page)):
        with pytest.raises(basins.BasinsUnavailable, match="no districts"):
            basins.districts(cache=tmp_path / "c.geojson")


# --- the geometry ---------------------------------------------------------------

#: Fixture squares are kilometres across, not metres. `basins` drops a country
#: whose pieces of a district total less than `MIN_COUNTRY_AREA_M2`, so a fixture
#: in bare units is below the threshold everywhere and every assertion about a
#: shared basin passes or fails for the wrong reason.
KM = 1000.0


@pytest.fixture
def two_countries():
    """Three regions in two countries; basin A straddles the border, B does not.

    BE-shared and FR-shared sit side by side inside basin A. BE-own sits above,
    alone in basin B. Every square is 10 x 10 km in EPSG:3035, so the shares are
    exact fractions.
    """
    admin = gpd.GeoDataFrame(
        {"CNTR_CODE": ["BE", "BE", "FR"], "id": ["be-shared", "be-own", "fr-shared"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(0, 10 * KM, 10 * KM, 20 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["A", "B"]},
        geometry=[box(0, 0, 20 * KM, 10 * KM), box(0, 10 * KM, 10 * KM, 20 * KM)],
        crs="EPSG:3035",
    )
    return admin, districts


def test_an_admin_frame_without_country_codes_is_refused(two_countries):
    """Without them there is nothing to compare, and the whole module answers a
    question about countries."""
    admin, districts = two_countries
    with pytest.raises(ValueError, match="no country column"):
        basins.basin_countries(admin.drop(columns=["CNTR_CODE"]), districts)


def test_a_basin_knows_which_countries_it_covers(two_countries):
    admin, districts = two_countries
    out = basins.basin_countries(admin, districts)
    assert out["countries"].iloc[0] == ["BE", "FR"]
    assert out["n_countries"].iloc[0] == 2
    assert bool(out["is_shared"].iloc[0]) is True
    assert out["countries"].iloc[1] == ["BE"]
    assert bool(out["is_shared"].iloc[1]) is False


def test_the_share_names_the_other_countries_not_its_own(two_countries):
    """"Shared with BE" on a Belgian region is noise; the useful sentence names
    whoever else holds the levers."""
    admin, districts = two_countries
    out = basins.shared_basin_exposure(admin, districts)
    assert out["shared_with"].iloc[0] == ["FR"]
    assert out["shared_with"].iloc[1] == []
    assert out["shared_with"].iloc[2] == ["BE"]


def test_a_region_wholly_inside_a_shared_basin_scores_one(two_countries):
    admin, districts = two_countries
    out = basins.shared_basin_exposure(admin, districts)
    assert out["shared_basin_share"].iloc[0] == pytest.approx(1.0)
    assert out["shared_basin_share"].iloc[1] == pytest.approx(0.0)
    assert out["basin_countries_max"].iloc[0] == 2
    assert out["basin_countries_max"].iloc[1] == 1


def test_the_shared_share_never_exceeds_the_covered_share(two_countries):
    """A region cannot have more of itself in shared basins than in basins at
    all. If it does, the pieces are being counted twice."""
    admin, districts = two_countries
    out = basins.shared_basin_exposure(admin, districts)
    covered = out["basin_area_share"].to_numpy(dtype="float64")
    shared = out["shared_basin_share"].to_numpy(dtype="float64")
    assert np.all(shared <= covered + 1e-12)
    assert np.all(covered <= 1.0 + 1e-12)


def test_a_region_split_between_a_shared_and_an_unshared_basin():
    """The arithmetic the module exists for: half the region drains into water it
    shares with France, half into water it keeps, so the figure is 0.5 - not 0
    and not 1. A region is rarely wholly one or the other, and rounding it to
    either end is what makes the indicator useless."""
    admin = gpd.GeoDataFrame(
        {"CNTR_CODE": ["BE", "FR"], "id": ["split", "fr"]},
        geometry=[box(0, 0, 10 * KM, 20 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["shared", "own"]},
        # `shared` reaches east across the border; `own` stops at it.
        geometry=[box(0, 0, 20 * KM, 10 * KM), box(0, 10 * KM, 10 * KM, 20 * KM)],
        crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(admin, districts)
    assert out["shared_basin_share"].iloc[0] == pytest.approx(0.5)
    assert out["basin_area_share"].iloc[0] == pytest.approx(1.0)
    assert out["shared_with"].iloc[0] == ["FR"]


def test_a_region_no_district_covers_has_no_share(two_countries):
    """None, not 0.0. "Drains into nothing shared" is a finding; "no district
    reaches here" is an absence, and coastal regions draining straight to sea
    are legitimately in the second group."""
    admin, districts = two_countries
    # Two countries, because a single-country frame is refused outright - see
    # `test_a_single_country_frame_is_refused`. Neither region meets a district.
    far = gpd.GeoDataFrame(
        {"CNTR_CODE": ["XX", "YY"], "id": ["elsewhere", "also-elsewhere"]},
        geometry=[box(100 * KM, 100 * KM, 110 * KM, 110 * KM), box(200 * KM, 200 * KM, 210 * KM, 210 * KM)],
        crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(far, districts)
    assert np.isnan(out["shared_basin_share"].iloc[0])
    assert np.isnan(out["basin_area_share"].iloc[0])
    assert out["shared_with"].iloc[0] == []


def test_a_single_country_frame_is_refused(two_countries):
    """Whether a basin is shared is read off the countries in the admin frame,
    so a Belgium-only frame reports the Meuse as NOT shared - this module's
    entire argument, inverted, and delivered as 0.0, which its own comments
    treat as a finding rather than an absence."""
    admin, districts = two_countries
    belgium = admin[admin["CNTR_CODE"] == "BE"]
    with pytest.raises(ValueError, match="looks unshared by construction"):
        basins.shared_basin_exposure(belgium, districts)


def test_a_district_reported_twice_is_not_counted_twice():
    """The WFD layer reports a district once per member state, so the Scheldt
    arrives several times. Intersecting each copy and summing gave a share of
    2.0 on a column documented as being in [0, 1]."""
    admin = gpd.GeoDataFrame(
        {"CNTR_CODE": ["BE", "FR"], "id": ["be", "fr"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)], crs="EPSG:3035",
    )
    twice = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["A", "A"]},
        geometry=[box(0, 0, 20 * KM, 10 * KM), box(0, 0, 20 * KM, 10 * KM)], crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(admin, twice)
    assert out["basin_area_share"].iloc[0] == pytest.approx(1.0)
    assert out["shared_basin_share"].iloc[0] == pytest.approx(1.0)


def test_overlapping_districts_do_not_push_the_share_over_one():
    """The pieces are not guaranteed disjoint, so the shares are the area of
    their UNION, not the sum of their areas."""
    admin = gpd.GeoDataFrame(
        {"CNTR_CODE": ["BE", "FR"], "id": ["be", "fr"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)], crs="EPSG:3035",
    )
    overlapping = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["A", "B"]},
        # Both reach across the border, and they overlap each other by 2 units.
        geometry=[box(0, 0, 20 * KM, 10 * KM), box(8 * KM, 0, 20 * KM, 10 * KM)], crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(admin, overlapping)
    assert out["basin_area_share"].iloc[0] <= 1.0 + 1e-12
    assert out["shared_basin_share"].iloc[0] <= 1.0 + 1e-12


def test_a_self_intersecting_district_is_repaired_not_believed():
    """A bowtie polygon does not raise in `gpd.overlay`; it produces a
    plausible-looking area. Measured before the repair: a share of 0.5 where the
    intended polygon covered the whole region."""
    from shapely.geometry import Polygon

    admin = gpd.GeoDataFrame(
        {"CNTR_CODE": ["BE", "FR"], "id": ["be", "fr"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)], crs="EPSG:3035",
    )
    bowtie = Polygon([(0, 0), (20, 10), (20, 0), (0, 10)])
    assert not bowtie.is_valid, "the fixture has to be broken to be a test"
    broken = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["A"]}, geometry=[bowtie], crs="EPSG:3035"
    )
    out = basins.shared_basin_exposure(admin, broken)
    assert out["basin_area_share"].iloc[0] <= 1.0 + 1e-12
    assert not np.isnan(out["basin_area_share"].iloc[0])


# --- the column name, and the border slivers -----------------------------------

def test_either_country_column_is_accepted(two_countries):
    """`boundaries()` renames GISCO's `CNTR_CODE` to `country`, and that frame is
    what the build script passes. Requiring one name meant every real call raised
    `ValueError` and the basin half of `context.parquet` was reported as a missing
    dataset rather than as a bug."""
    admin, districts = two_countries
    renamed = admin.rename(columns={"CNTR_CODE": "country"})
    assert basins._country_column(renamed) == "country"
    assert basins._country_column(admin) == "CNTR_CODE"
    one = basins.basin_countries(admin, districts)
    other = basins.basin_countries(renamed, districts)
    assert one["countries"].tolist() == other["countries"].tolist()
    assert one["n_countries"].tolist() == other["n_countries"].tolist()


def test_a_border_sliver_does_not_make_a_basin_international(two_countries):
    """The districts and the NUTS3 regions are independent renderings of the same
    borders, so they disagree by a few hundred metres everywhere and every
    district picks up a strip of its neighbour.

    Measured on the real layer before the threshold: 109 of the 182 districts the
    NUTS3 frame reaches reported two or more countries and one reported eight,
    where exactly one spans a border by area. Here basin B is Belgian but overhangs 10 km x 1 km of
    France - 10 km2, under the 50 km2 floor - so it stays Belgian.
    """
    admin, districts = two_countries
    overhanging = districts.copy()
    overhanging.loc[1, "geometry"] = box(0, 10 * KM, 10 * KM, 20 * KM).union(
        box(10 * KM, 10 * KM, 20 * KM, 11 * KM)
    )
    out = basins.basin_countries(admin, overhanging)
    assert out["countries"].iloc[1] == ["BE"]
    assert bool(out["is_shared"].iloc[1]) is False


def test_a_real_second_country_still_counts(two_countries):
    """The other side of the threshold: the same overhang at 10 km x 10 km is
    100 km2 and the basin is shared. Without this, a fix for the slivers could
    silently be "report nothing is ever shared"."""
    admin, districts = two_countries
    admin = admin.copy()
    admin.loc[2, "geometry"] = box(10 * KM, 0, 20 * KM, 20 * KM)
    overhanging = districts.copy()
    overhanging.loc[1, "geometry"] = box(0, 10 * KM, 20 * KM, 20 * KM)
    out = basins.basin_countries(admin, overhanging)
    assert out["countries"].iloc[1] == ["BE", "FR"]
    assert bool(out["is_shared"].iloc[1]) is True


# --- the declared crosswalk ------------------------------------------------------

def test_two_disjoint_national_portions_are_one_shared_basin():
    """The defect this whole crosswalk exists for.

    The WFD publishes one polygon per member state per basin, and those polygons
    are disjoint - measured 2026-10-06, the three Scheldt rows overlap by 0 km2.
    So each polygon lies in exactly one country and grouping by polygon reported
    every international basin in Europe as unshared, as `0.0` rather than as an
    absence. Here two side-by-side portions in two countries have to come back as
    one basin that both countries are in.
    """
    admin = gpd.GeoDataFrame(
        {"country": ["BE", "NL"], "id": ["be", "nl"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["BESCHELDE_VL", "NLSC"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    crosswalk = {"BESCHELDE_VL": "scheldt", "NLSC": "scheldt"}

    alone = basins.basin_countries(admin, districts, crosswalk={})
    assert alone["countries"].tolist() == [["BE"], ["NL"]]
    assert alone["is_shared"].tolist() == [False, False]

    pooled = basins.basin_countries(admin, districts, crosswalk=crosswalk)
    assert pooled["countries"].tolist() == [["BE", "NL"], ["BE", "NL"]]
    assert pooled["is_shared"].tolist() == [True, True]
    assert pooled["basin_id"].tolist() == ["scheldt", "scheldt"]


def test_a_region_is_told_which_other_countries_share_its_basin():
    """The sentence the layer is here for: not "0.3 of this region is shared" but
    "shared with NL"."""
    admin = gpd.GeoDataFrame(
        {"country": ["BE", "NL"], "id": ["be", "nl"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["BESCHELDE_VL", "NLSC"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(
        admin, districts, crosswalk={"BESCHELDE_VL": "scheldt", "NLSC": "scheldt"}
    )
    assert out["shared_basin_share"].iloc[0] == pytest.approx(1.0)
    assert out["shared_with"].iloc[0] == ["NL"]
    assert out["shared_with"].iloc[1] == ["BE"]


def test_a_sliver_does_not_name_a_partner_the_share_denies():
    """`shared_with` is read off the SHARED basins, like the share beside it.

    The country lists are built behind `MIN_COUNTRY_AREA_M2`; the pieces are not.
    So a region overhanging a neighbour's district by less than the floor used to
    collect that neighbour as a partner while the very same sliver was discarded
    when the basin's countries were counted - a region reading "shared with FR"
    next to `shared_basin_share` 0.0.

    Here the French district overhangs 1 km x 10 km of Belgium: 10 km2, under the
    50 km2 floor, so the basin stays French and the Belgian region has no partner.
    Measured on the real layer before this: 58 of 1,345 regions carried a list
    their own share contradicted.
    """
    admin = gpd.GeoDataFrame(
        {"country": ["BE", "FR"], "id": ["be", "fr"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["FRD"]},
        geometry=[box(9 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    counted = basins.basin_countries(admin, districts)
    assert counted["countries"].iloc[0] == ["FR"], "the sliver must not add BE"
    assert bool(counted["is_shared"].iloc[0]) is False

    out = basins.shared_basin_exposure(admin, districts)
    assert out["shared_basin_share"].iloc[0] == pytest.approx(0.0)
    assert out["shared_with"].iloc[0] == [], (
        "a partner named beside a share of 0.0 states the opposite of the share"
    )


def test_a_district_the_crosswalk_does_not_mention_stays_its_own_basin():
    """"Not established" must not read as "shared". A district nobody has grouped
    is one country's until someone says otherwise, in the file, with evidence."""
    admin = gpd.GeoDataFrame(
        {"country": ["BE", "NL"], "id": ["be", "nl"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["BESCHELDE_VL", "SOMETHING_ELSE"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    out = basins.basin_countries(
        admin, districts, crosswalk={"BESCHELDE_VL": "scheldt"}
    )
    assert out["countries"].tolist() == [["BE"], ["NL"]]
    assert out["is_shared"].tolist() == [False, False]


def test_a_district_in_two_basins_is_refused(tmp_path):
    """Its area would be counted into both, and the two shares would each look
    like a plain share of the region."""
    path = tmp_path / "crosswalk.yaml"
    path.write_text(
        "basins:\n"
        "  meuse:\n    districts: [NLMS, NLSC]\n"
        "  scheldt:\n    districts: [NLSC]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="claimed by both"):
        basins.international_basins(path)


def test_the_shipped_crosswalk_groups_the_meuse_and_the_scheldt():
    """A real-file test, no network: the two basins the Belgian brief turns on.

    Pinned because the file is the one assertion in this module that is declared
    rather than measured, so a careless edit has to break a test.
    """
    crosswalk = basins.international_basins()
    meuse = {c for c, b in crosswalk.items() if b == "meuse"}
    scheldt = {c for c, b in crosswalk.items() if b == "scheldt"}
    assert {"BEMEUSE_RW", "BEMAAS_VL", "NLMS", "FRB1", "LU001", "DE7000"} <= meuse
    assert {"BEESCAUT_RW", "BESCHELDE_VL", "NLSC", "FRA"} <= scheldt
    assert not meuse & scheldt


def test_check_crosswalk_refuses_a_code_the_layer_does_not_have():
    """A retired or mistyped district would sit in the file looking authoritative
    and silently group nothing."""
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["NLSC"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM)], crs="EPSG:3035",
    )
    with pytest.raises(ValueError, match="does not have"):
        basins.check_crosswalk(districts)


def test_a_region_is_told_the_name_of_the_basin_it_shares():
    """"Shared with NL" says who to call; the basin's name says about what. The
    name is the crosswalk's own `name`, never the id, and it sits beside the
    partner list on the same shared basins."""
    admin = gpd.GeoDataFrame(
        {"country": ["BE", "NL"], "id": ["be", "nl"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["BESCHELDE_VL", "NLSC"]},
        geometry=[box(0, 0, 10 * KM, 10 * KM), box(10 * KM, 0, 20 * KM, 10 * KM)],
        crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(
        admin, districts, crosswalk={"BESCHELDE_VL": "scheldt", "NLSC": "scheldt"}
    )
    assert out["shared_basins"].tolist() == [["Scheldt"], ["Scheldt"]]


def test_an_unshared_basin_is_not_named_as_shared(two_countries):
    """Basin B lies in Belgium alone: naming it beside `shared_with` would say
    the region shares a basin it governs entirely."""
    admin, districts = two_countries
    out = basins.shared_basin_exposure(admin, districts, crosswalk={})
    assert out["shared_basins"].iloc[1] == []
    assert out["shared_basins"].iloc[0] == ["A"], "no declared name: the id, not nothing"


def test_the_basin_holding_most_of_the_region_is_named_first():
    """A region in two shared basins lists the one that matters most to it
    first, not the alphabetically first."""
    admin = gpd.GeoDataFrame(
        {"country": ["BE", "NL"], "id": ["be", "nl"]},
        geometry=[box(0, 0, 20 * KM, 20 * KM), box(20 * KM, 0, 40 * KM, 20 * KM)],
        crs="EPSG:3035",
    )
    # Meuse covers 14 km of the 20 km Belgian square, Scheldt 6 km - both above
    # the 50 km2 floor in each country, so both are shared.
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["S", "M"]},
        geometry=[box(0, 0, 40 * KM, 6 * KM), box(0, 6 * KM, 40 * KM, 20 * KM)],
        crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(
        admin, districts, crosswalk={"S": "scheldt", "M": "meuse"}
    )
    assert out["shared_basins"].iloc[0] == ["Meuse", "Scheldt"]


def test_the_shares_never_read_above_one():
    """The union of a region's pieces and the region are areas of different
    vertex lists, and on the real layer 153 regions read 1.0000000000000022 for
    a share. Clipped, so a region wholly inside reads exactly 1.0."""
    admin = gpd.GeoDataFrame(
        {"country": ["BE", "NL"], "id": ["be", "nl"]},
        # A pentagon found by search: its overlay with a district enclosing it
        # comes back 2e-16 larger than itself, the same noise as on the real layer.
        geometry=[
            Polygon([(13108.986, 23207.161), (6157.302, 40661.085), (33114.48, 44367.175),
                     (39623.469, 33378.079), (36686.759, 28192.198)]),
            box(100 * KM, 0, 110 * KM, 10 * KM),
        ],
        crs="EPSG:3035",
    )
    districts = gpd.GeoDataFrame(
        {"thematicIdIdentifier": ["X"]},
        geometry=[box(-100 * KM, -100 * KM, 300 * KM, 300 * KM)],
        crs="EPSG:3035",
    )
    out = basins.shared_basin_exposure(admin, districts, crosswalk={})
    for column in ("shared_basin_share", "basin_area_share"):
        assert (out[column] <= 1.0).all(), out[column].tolist()
        assert np.allclose(out[column], 1.0)
