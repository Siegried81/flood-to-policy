"""Tests for the July 2021 roads, networks and services (`scripts/event_2021_infrastructure.py`).

Synthetic EPSG:3035 geometry only: no bucket, no cache. They pin the rules a
reader of the table relies on: a class from the EMS `info` code, km measured
on the ground and once per segment, a feature counted once with its most
severe grade, and nothing outside the AOI.
"""

from __future__ import annotations

import pytest

shapely = pytest.importorskip("shapely")
gpd = pytest.importorskip("geopandas")

from scripts import event_2021_infrastructure as X  # noqa: E402
from src import event2021 as E  # noqa: E402

AOI = shapely.box(0, 0, 10_000, 10_000)
WATER = shapely.box(0, 0, 4_000, 10_000)


def _frame(rows):
    cats, grades, geoms = zip(*rows) if rows else ((), (), ())
    return gpd.GeoDataFrame({"category": list(cats), "grade": list(grades)}, geometry=list(geoms),
                            crs="EPSG:3035")


def _value(rows, **match):
    hits = [r["value"] for r in rows if all(r[k] == v for k, v in match.items())]
    assert len(hits) == 1, (match, hits)
    return hits[0]


@pytest.mark.parametrize("info,expected", [
    ("21120-Primary Road", "primary_road"), ("21122-Local Road", "local_road"),
    ("2111-Highways", "motorway"), ("2121-Long-distance railways", "railway"),
    ("2141-Bridges and elevated highways", "bridge"), ("21199-Something", "other"),
])
def test_road_class_takes_the_longest_code_prefix(info, expected):
    assert E.info_class(info, E.ROAD_CLASSES) == expected


def test_unlisted_services_are_dropped_not_lumped():
    assert E.info_class("1263-School, university and research buildings", E.FACILITY_CLASSES) == "school_university"
    assert E.info_class("2411-Sports grounds", E.FACILITY_CLASSES, default=None) is None
    assert E.info_class("997-Not Applicable", E.FACILITY_CLASSES, default=None) is None


def test_km_in_the_water_and_a_duplicate_segment_counted_once():
    road = shapely.LineString([(0, 5_000), (10_000, 5_000)])  # 10 km, 4 km under water
    rows = X.line_rows(_frame([("local_road", None, road), ("local_road", None, road)]), AOI, WATER)
    assert _value(rows, category="local_road", scope="aoi", damage_grade="all") == pytest.approx(10)
    assert _value(rows, category="local_road", scope="observed", damage_grade="all") == pytest.approx(4)
    assert _value(rows, category="local_road", scope="near", damage_grade="all") == pytest.approx(4.025)


def test_line_outside_the_aoi_measures_nothing():
    road = shapely.LineString([(20_000, 0), (30_000, 0)])
    rows = X.line_rows(_frame([("motorway", None, road)]), AOI, WATER)
    assert all(r["value"] == 0 for r in rows)


def test_graded_km_never_count_a_segment_under_two_grades():
    road = shapely.LineString([(0, 1_000), (2_000, 1_000)])
    rows = X.line_rows(_frame([("railway", "Destroyed", road), ("railway", "Damaged", road)]), AOI, WATER)
    assert _value(rows, category="railway", damage_grade="Destroyed") == pytest.approx(2)
    assert _value(rows, category="railway", damage_grade="Damaged") == pytest.approx(0)


def test_service_counted_once_with_its_most_severe_grade():
    school = shapely.box(1_000, 1_000, 1_050, 1_050)
    dry_school = shapely.box(8_000, 8_000, 8_050, 8_050)
    rows = X.facility_rows(_frame([("school_university", "Possibly damaged", school),
                                   ("school_university", "Destroyed", school),
                                   ("school_university", None, dry_school)]), AOI, WATER)
    assert _value(rows, category="school_university", scope="aoi", damage_grade="all") == 2
    assert _value(rows, category="school_university", scope="observed", damage_grade="all") == 1
    assert _value(rows, category="school_university", damage_grade="Destroyed") == 1
    assert not [r for r in rows if r["damage_grade"] == "Possibly damaged"]


def test_a_service_beside_the_water_is_near_not_in():
    clinic = shapely.Point(4_010, 5_000)
    rows = X.facility_rows(_frame([("hospital_care", None, clinic)]), AOI, WATER)
    assert _value(rows, category="hospital_care", scope="observed", damage_grade="all") == 0
    assert _value(rows, category="hospital_care", scope="near", damage_grade="all") == 1


def test_measure_keeps_lines_and_counts_apart():
    power = shapely.LineString([(0, 2_000), (6_000, 2_000)])
    rows = X.measure(_frame([("local_road", None, shapely.LineString([(0, 0), (1, 0)]))]),
                     _frame([("power_line", None, power)]), _frame([]), AOI, WATER)
    assert _value(rows, theme="networks", category="power_line", scope="observed",
                  damage_grade="all") == pytest.approx(4)
    assert {r["unit"] for r in rows if r["theme"] == "networks"} == {"km"}
