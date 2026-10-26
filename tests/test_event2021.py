"""Tests for src/event2021.py and scripts/event_2021.py on synthetic data. No network.

The real inputs are a public bucket and 3 GB of local hazard rasters that CI
does not have, so these tests pin the rules that move a figure: which bucket
folders count as products, area-weighted residents (half a flooded cell is
half its people), the permanent-water split between the agreement and the
resident count, cell and building deduplication across overlapping products,
and one end-to-end product on a 1 km synthetic AOI.
"""

from __future__ import annotations

import io
import json
from functools import partial

import numpy as np
import pandas as pd
import pytest
import shapely
from affine import Affine

from scripts import event_2021 as S
from src import event2021 as E
from src import validate as V

ROOT = E.BUCKET_ROOT


def _names(folder: str, country_dir: str, layers=("observedEventA", "areaOfInterestA")):
    m = E.PRODUCT_RE.match(folder)
    stem = f"{m['emsr']}_AOI{m['aoi']}_{m['type']}_{m['kind']}"
    return [f"{ROOT}/{country_dir}/{folder}/{stem}_{layer}_r1_v{m['version']}.shp"
            for layer in layers]


# --------------------------------------------------------------------------
# Product discovery
# --------------------------------------------------------------------------

def test_products_are_parsed_from_folder_names_with_their_version():
    names = (_names("EMSR517_AOI15_GRA_MONIT01_r1_RTP01_v3_vector", "ems_de")
             + _names("EMSR517_AOI15_GRA_PRODUCT_r1_RTP01_v1_vector", "ems_de")
             + _names("EMSR518_AOI01_DEL_PRODUCT_r1_VECTORS_v1_vector", "ems_be")
             + [f"{ROOT}/ghs_pop/x.tif", f"{ROOT}/ems_de/README.txt"])
    products = E.products_from_names(names)
    assert [p.product_id for p in products] == [
        "EMSR518_AOI01_DEL_PRODUCT_v1",
        "EMSR517_AOI15_GRA_PRODUCT_v1",
        "EMSR517_AOI15_GRA_MONIT01_v3",
    ]
    monit = products[2]
    assert monit.country == "DE" and monit.version == "3"
    assert monit.layer_path("builtUpP").endswith("EMSR517_AOI15_GRA_MONIT01_builtUpP_r1_v3.shp")


def test_a_folder_without_its_aoi_layer_is_not_a_product():
    """Without the AOI, "not flooded" and "not mapped" cannot be told apart."""
    names = _names("EMSR520_AOI01_DEL_PRODUCT_r1_RTP01_v1_vector", "ems_nl",
                   layers=("observedEventA",))
    assert E.products_from_names(names) == []


def test_bucket_listing_follows_every_page():
    pages = [{"items": [{"name": "a"}, {"name": "b"}], "nextPageToken": "t1"},
             {"items": [{"name": "c"}]}]
    urls = []

    def opener(url):
        urls.append(url)
        return io.BytesIO(json.dumps(pages[len(urls) - 1]).encode())

    assert E.bucket_objects("working_data/ems_be/", opener=opener) == ["a", "b", "c"]
    assert "pageToken=t1" in urls[1] and "pageToken" not in urls[0]


# --------------------------------------------------------------------------
# Classes and ratios
# --------------------------------------------------------------------------

def test_height_classes_and_unknown():
    got = E.height_class([0.0, 3.0, 6.0, 11.99, 12.0, 30.0, np.nan, -1.0])
    assert list(got) == ["unknown", "lt_6m", "6_12m", "6_12m", "12_24m", "ge_24m",
                         "unknown", "unknown"]


def test_ratio_is_nan_not_zero_on_an_empty_denominator():
    assert np.isnan(E.ratio(5, 0))
    assert E.ratio(1, 4) == 0.25


def test_building_breakdown_writes_every_category_even_when_empty():
    frame = E.classify_buildings(pd.DataFrame({
        "use": [1, 1, 2, 0], "epoch": [1, 5, 1, 0], "height": [4.0, 15.0, np.nan, 0.0],
        "area": [100.0, 50.0, 10.0, 1.0]}))
    out = E.building_breakdown(frame, scope="observed")
    use = out[out["dimension"] == "use"].set_index("category")
    assert use.loc["residential", "buildings"] == 2
    assert use.loc["residential", "footprint_m2"] == 150.0
    assert use.loc["unknown", "buildings"] == 0
    height = out[out["dimension"] == "height"].set_index("category")
    assert height.loc["unknown", "buildings"] == 2
    assert out.groupby("dimension")["buildings"].sum().unique().tolist() == [4]
    empty = E.building_breakdown(frame.iloc[:0], scope="aoi")
    assert len(empty) == len(out) and empty["buildings"].sum() == 0


# --------------------------------------------------------------------------
# Population: area weighting
# --------------------------------------------------------------------------

POP_T = Affine(30 / 3600, 0.0, 7.0, 0.0, -30 / 3600, 50.0)


def test_cell_area_matches_the_ground_size_of_a_30_arcsecond_cell():
    """About 0.596 km x 0.927 km just below 50 N."""
    area = E.pop_cell_area_m2(POP_T, 2)
    expected = (6371008.8 * np.radians(30 / 3600)) ** 2 * np.cos(np.radians(50 - 15 / 3600))
    assert area[0] == pytest.approx(expected, rel=0.01)
    assert area[1] > area[0], "cells grow towards the equator"


def test_density_times_area_gives_back_the_counts():
    pop = np.array([[100.0, -200.0], [np.nan, 40.0]])
    density = E.population_density(pop, POP_T)
    back = density * E.pop_cell_area_m2(POP_T, 2)[:, None]
    np.testing.assert_allclose(back, [[100.0, 0.0], [0.0, 40.0]])


def test_half_a_cell_inside_the_polygon_is_half_its_people():
    pop = np.array([[100.0, 60.0]])
    step = 30 / 3600
    left_half = shapely.box(7.0, 50.0 - step, 7.0 + step / 2, 50.0)
    assert E.people_in_polygon(pop, POP_T, left_half) == pytest.approx(50.0)
    both = shapely.box(7.0, 50.0 - step, 7.0 + 2 * step, 50.0)
    assert E.people_in_polygon(pop, POP_T, both) == pytest.approx(160.0)
    assert E.people_in_polygon(pop, POP_T, shapely.Polygon()) == 0.0


def test_people_on_the_20m_grid_are_area_weighted():
    """The grid route and the exact-polygon route agree, and conserve people."""
    pop = np.full((3, 3), 900.0)
    t = Affine(30 / 3600, 0.0, 7.0, 0.0, -30 / 3600, 50.025)
    inner = (7.0 + 30 / 3600, 50.025 - 60 / 3600, 7.0 + 60 / 3600, 50.025 - 30 / 3600)
    grid = S.window_grid(inner)
    people = S.people_on_grid(pop, t, grid)
    cell = shapely.box(*inner)
    half = shapely.box(inner[0], inner[1], (inner[0] + inner[2]) / 2, inner[3])
    on_grid = S.rasterize_on_grid(S._to_grid_crs(cell), grid)
    on_half = S.rasterize_on_grid(S._to_grid_crs(half), grid)
    assert people[on_grid].sum() == pytest.approx(900.0, rel=0.02)
    assert people[on_half].sum() == pytest.approx(450.0, rel=0.03)
    assert E.people_in_polygon(pop, t, half) == pytest.approx(450.0, rel=1e-6)


# --------------------------------------------------------------------------
# Grid keys and hazard rows
# --------------------------------------------------------------------------

def test_cell_keys_name_the_same_ground_cell_from_two_grids():
    a = V.Grid(left=4_000_000.0, top=3_000_000.0, width=10, height=10)
    b = V.Grid(left=4_000_100.0, top=2_999_900.0, width=10, height=10)
    ma = np.zeros(a.shape, bool)
    ma[5, 5] = True
    mb = np.zeros(b.shape, bool)
    mb[0, 0] = True  # 100 m right and down of `a`'s origin: a's cell (5, 5)
    assert E.cell_keys(a, ma).tolist() == E.cell_keys(b, mb).tolist()


def test_hazard_rows_drop_permanent_water_from_the_score_but_not_the_people():
    observed = np.array([[True, True, True, True, False, False]])
    water = np.array([[True, False, False, False, False, False]])
    wet = np.array([[True, True, False, False, True, False]])
    scorable = ~water
    people = np.array([[10.0, 1.0, 2.0, 3.0, 50.0, 50.0]])
    (row,) = E.hazard_rows(observed, scorable, people, {100: wet})
    assert row["true_positive"] == 1 and row["false_negative"] == 2
    assert row["false_positive"] == 1
    assert np.isnan(row["hit_rate"]), "3 observed cells are below MIN_OBSERVED_CELLS"
    assert row["residents_observed"] == 16.0
    assert row["residents_outside_map"] == 5.0


def test_hazard_rows_score_above_the_thin_threshold():
    n = V.MIN_OBSERVED_CELLS * 2
    observed = np.ones((1, n), bool)
    wet = np.zeros((1, n), bool)
    wet[0, : n // 2] = True
    (row,) = E.hazard_rows(observed, np.ones((1, n), bool), np.ones((1, n)), {10: wet})
    assert row["hit_rate"] == pytest.approx(0.5)
    assert row["false_alarm_ratio"] == 0.0
    assert row["share_residents_outside_map"] == pytest.approx(0.5)


# --------------------------------------------------------------------------
# End to end on a synthetic 1 km AOI
# --------------------------------------------------------------------------

AOI = (7.000, 50.000, 7.012, 50.008)
MID = 7.006


def _tif(path, values, transform, nodata=None):
    import rasterio

    with rasterio.open(path, "w", driver="GTiff", height=values.shape[0],
                       width=values.shape[1], count=1, dtype=values.dtype,
                       crs="EPSG:4326", transform=transform, nodata=nodata) as dst:
        dst.write(values, 1)
    return path


@pytest.fixture
def synthetic(tmp_path):
    """A cache with one graded product, its OBAT points, population and hazard."""
    import geopandas as gpd
    import pyogrio

    cache = tmp_path / "cache"
    product = E.Product(country="DE", folder="EMSR517_AOI99_GRA_PRODUCT_r1_RTP01_v1_vector",
                        emsr="EMSR517", aoi="99", type="GRA", kind="PRODUCT", version="1")
    gpkg = S._gpkg(cache, product)
    gpkg.parent.mkdir(parents=True)
    west, south, east, north = AOI
    aoi = gpd.GeoDataFrame({"locality": ["Testdorf"]}, geometry=[shapely.box(*AOI)],
                           crs="EPSG:4326")
    events = gpd.GeoDataFrame(
        {"notation": ["Flooded area", "Flood trace", "Not Applicable"]},
        geometry=[shapely.box(west, south, MID, (south + north) / 2),
                  shapely.box(west, (south + north) / 2, MID, north),
                  shapely.box(MID, south, east, north)], crs="EPSG:4326")
    damage = gpd.GeoDataFrame(
        {"damage_gra": ["Destroyed", "Damaged", "Possibly damaged"],
         "obj_type": ["11-Residential Buildings"] * 3},
        geometry=shapely.points([[7.002, 50.002], [7.003, 50.006], [7.010, 50.004]]),
        crs="EPSG:4326")
    pyogrio.write_dataframe(aoi, gpkg, layer="areaOfInterestA")
    pyogrio.write_dataframe(events, gpkg, layer="observedEventA")
    pyogrio.write_dataframe(damage, gpkg, layer="builtUpP")

    obat = pd.DataFrame({
        "id": ["a", "b", "c", "d"], "height": [5.0, 14.0, 8.0, 3.0],
        "use": [1, 2, 1, 1], "epoch": [1, 3, 5, 1], "area": [100.0, 400.0, 80.0, 60.0],
        "lon": [7.002, 7.004, 7.010, 7.050], "lat": [50.002, 50.006, 50.004, 50.004]})
    S._obat(cache, product).parent.mkdir(parents=True)
    obat.to_parquet(S._obat(cache, product), index=False)

    step = 30 / 3600
    pop_t = Affine(step, 0.0, 6.99, 0.0, -step, 50.02)
    pop_path = _tif(tmp_path / "pop.tif", np.full((4, 4), 500.0), pop_t)

    h_step = 3 / 3600
    h_t = Affine(h_step, 0.0, 6.99, 0.0, -h_step, 50.02)
    cols = 6.99 + (np.arange(40) + 0.5) * h_step
    depth = np.where(cols < MID, 1.0, -9999.0).astype("float32")
    hazard = str(tmp_path / "Europe_RP{rp}_filled_depth.tif")
    for rp in (10, 100):
        _tif(hazard.format(rp=rp), np.tile(depth, (40, 1)), h_t, nodata=-9999.0)
    water = _tif(tmp_path / "water.tif", np.zeros((40, 40), "uint8"), h_t)

    cache.joinpath("products.json").write_text(json.dumps(
        {"products": [product.__dict__], "graded": [product.product_id]}))
    _tif(S._pop(cache), np.full((4, 4), 500.0), pop_t)
    return {"cache": cache, "product": product, "pop": S.read_population(pop_path),
            "hazard": hazard, "water": water}


def _analyse(f):
    return S.analyse_product(f["product"], cache=f["cache"], pop=f["pop"], hazard=f["hazard"],
                             permanent_water=f["water"], return_periods=(10, 100))


def test_one_product_end_to_end(synthetic):
    r = _analyse(synthetic)
    row = r["row"]
    assert row["locality"] == "Testdorf"
    assert row["observed_polygons_dropped"] == 1, "the 'Not Applicable' polygon"
    assert row["observed_km2"] == pytest.approx(row["aoi_km2"] / 2, rel=0.01)
    assert row["flood_trace_km2"] == pytest.approx(row["observed_km2"] / 2, rel=0.01)
    assert row["observed_km2_grid"] == pytest.approx(row["observed_km2"], rel=0.05)
    assert row["hit_rate_rp100"] == pytest.approx(1.0, abs=0.05)
    assert row["false_alarm_ratio_rp100"] == pytest.approx(0.0, abs=0.05)
    assert row["residents_observed"] == pytest.approx(row["residents_aoi"] / 2, rel=0.05)
    assert row["residents_observed"] == pytest.approx(row["residents_observed_vector"], rel=0.03)
    assert row["residents_aoi_grid"] == pytest.approx(row["residents_aoi"], rel=0.02)
    assert row["buildings_aoi"] == 3, "point d is outside the AOI"
    assert row["buildings_observed"] == 2
    assert row["buildings_within_25m_of_observed"] == 2, "c is ~280 m east of the extent"
    assert row["detection_method"] == ""
    assert row["residential_buildings_observed"] == 1
    assert row["footprint_m2_observed"] == 500.0
    assert row["buildings_observed_outside_rp100"] == 0
    assert row["graded_buildings"] == 3 and row["graded_destroyed"] == 1
    assert set(r["hazard"]["return_period"]) == {10, 100}
    dmg = r["damage"].set_index("damage_grade")
    assert dmg.loc["Possibly damaged", "in_observed"] == np.False_


def test_country_union_counts_an_overlapping_product_once(synthetic):
    """The same product twice (as PRODUCT and MONIT01) must not double anything."""
    first = _analyse(synthetic)
    monit = E.Product(**{**synthetic["product"].__dict__, "kind": "MONIT01", "version": "2"})
    second = _analyse(synthetic)
    rows, buildings, _damage = S.country_rows(
        [(synthetic["product"], first), (monit, second)], synthetic["pop"])
    by_basis = {r["extent_basis"]: r for r in rows}
    single, both = by_basis["product"], by_basis["product_and_monit"]
    assert both["n_products"] == 2
    assert both["residents_observed"] == pytest.approx(single["residents_observed"])
    assert both["observed_km2"] == pytest.approx(single["observed_km2"])
    assert both["buildings_observed"] == single["buildings_observed"] == 2
    assert both["graded_buildings"] == 3
    assert both["hit_rate_rp100"] == pytest.approx(first["row"]["hit_rate_rp100"])
    assert both["false_alarm_ratio_rp100"] == pytest.approx(
        first["row"]["false_alarm_ratio_rp100"])
    assert set(buildings[0]["level"]) == {"country"}


def test_main_offline_writes_every_table(synthetic, tmp_path, monkeypatch):
    monkeypatch.setattr(S, "analyse_product", partial(
        S.analyse_product, hazard=synthetic["hazard"], permanent_water=synthetic["water"],
        return_periods=(10, 100)))
    out = tmp_path / "out"
    assert S.main(["--offline", "--cache", str(synthetic["cache"]), "--out-dir", str(out)]) == 0
    for name in S.TABLES:
        frame = pd.read_parquet(out / f"event_2021_{name}.parquet")
        assert len(frame), name
        assert (out / f"event_2021_{name}.csv").exists()
    countries = pd.read_parquet(out / "event_2021_countries.parquet")
    assert set(countries["extent_basis"]) == {"product", "product_and_monit"}


def test_a_cached_population_window_too_small_for_the_aois_is_refetched(tmp_path, monkeypatch):
    """A window cached for one AOI would read as zero residents everywhere else."""
    import rasterio

    step = 30 / 3600
    world = _tif(tmp_path / "world.tif", np.ones((240, 240)), Affine(step, 0, 6.0, 0, -step, 51.0))
    monkeypatch.setattr(S, "_vsigs", lambda path: str(world))
    target = tmp_path / "window.tif"
    S.fetch_population(target, [(6.5, 50.5, 6.6, 50.6)])
    with rasterio.open(target) as small:
        assert small.bounds.right < 6.7
    S.fetch_population(target, [(6.5, 50.5, 6.6, 50.6), (7.0, 49.5, 7.2, 49.7)])
    with rasterio.open(target) as big:
        assert big.bounds.right >= 7.2 and big.bounds.bottom <= 49.5


def test_obat_fetch_skips_aois_already_cached(tmp_path, monkeypatch):
    (tmp_path / "obat").mkdir()
    (tmp_path / "obat" / "EMSR520_AOI01.parquet").write_bytes(b"cached")
    monkeypatch.setattr(S, "fetch_obat", lambda *a: pytest.fail("fetched a cached AOI"))
    S.fetch_all_obat(tmp_path, {"EMSR520_AOI01": (5.8, 51.1, 6.2, 51.5)}, jobs=4)
