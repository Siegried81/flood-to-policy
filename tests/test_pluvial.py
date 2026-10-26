"""Tests for the ECDE heavy-precipitation and flood-recurrence layers, and their fetcher.

Pinned failure modes: a NUTS2 figure passed off as a NUTS3 measurement, an
unmatched region read as "no change", the ensemble mean sneaking in, two
models said to agree when one is missing, a request built from the form that
the constraints reject, and the CDS key reaching the terminal.

No network: the constraints and the CDS client are fakes. The NetCDF readers
need xarray, which is not a dependency of the kit yet, so the tests that write
a real NetCDF skip without it; every step after reading is plain pandas and is
tested here regardless.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from scripts import fetch_c3s_ecde as fetcher
from src import pluvial


def _long(region_values: dict[str, float], name="rx5"):
    """A long frame as `to_dataframe().reset_index()` gives it."""
    rows = []
    for region, base in region_values.items():
        for gwl in (1.5, 2.0):
            for q in (17, 50, 83):
                for ref in ("1981-2010", "1991-2020"):
                    rows.append({"nuts_id": region, "gwl": gwl, "quantile": q,
                                 "ref_period": ref, name: base + gwl * 10 + q / 100})
    return pd.DataFrame(rows)


def test_labels_are_normalised():
    assert pluvial.gwl_label(1.5) == "1p5"
    assert pluvial.gwl_label("+2.0C") == "2"
    assert pluvial.gwl_label("gwl_3") == "3"
    assert pluvial.quantile_percent(0.17) == 17
    assert pluvial.quantile_percent("q83") == 83
    assert pluvial.quantile_percent(50) == 50


def test_wide_keeps_the_chosen_reference_period_and_quantiles():
    tidied = {"rx5day": pluvial.tidy(_long({"BE33": 1.0}), "rx5")}
    frame = pluvial.wide(tidied)
    assert "pluvial_rx5day_change_pct_gwl1p5_p50" in frame.columns
    assert "pluvial_rx5day_change_pct_gwl2_p83" in frame.columns
    assert len(frame.columns) == 6  # 2 levels x 3 quantiles, one reference period
    assert frame.loc["BE33", "pluvial_rx5day_change_pct_gwl2_p50"] == pytest.approx(1 + 20 + 0.5)


def test_tidy_refuses_a_frame_without_region_codes():
    frame = _long({"BE33": 1.0}).rename(columns={"nuts_id": "x"})
    frame["x"] = 3
    with pytest.raises(ValueError, match="region column"):
        pluvial.tidy(frame, "rx5")


def test_nuts3_inherits_its_parent_and_says_so():
    regional = pd.DataFrame({"v": [1.0, 2.0]}, index=["BE33", "BE332"])
    out = pluvial.inherit(["BE332", "BE331", "XX111"], regional)
    assert out["v"].tolist()[:2] == [2.0, 1.0]
    assert out.loc[0, "pluvial_level"] == pluvial.LEVEL_OWN
    assert out.loc[1, "pluvial_level"] == "NUTS2, applied to its NUTS3 children"
    # No parent either: NaN, never 0 % change.
    assert np.isnan(out.loc[2, "v"]) and out.loc[2, "pluvial_level"] is None


def test_by_region_without_files_gives_a_reason(tmp_path):
    admin = gpd.GeoDataFrame({"nuts_id": ["BE331"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    frame, why = pluvial.by_region(admin, directory=tmp_path)
    assert frame is None and "fetch_c3s_ecde.py" in why


def _admin():
    return gpd.GeoDataFrame(
        {"nuts_id": ["A", "B"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:4326",
    )


def _field(left, right):
    lon, lat = np.meshgrid(np.arange(0.05, 2.0, 0.1), np.arange(0.05, 1.0, 0.1))
    return lon, lat, np.where(lon < 1.0, left, right).astype("float64")


def test_gridded_median_per_model_and_agreement():
    slices = []
    for model, (left, right) in {"ehype": (10.0, 5.0), "vicwur": (20.0, -5.0)}.items():
        for q, shift in ((17, -3.0), (50, 0.0), (83, 3.0)):
            lon, lat, values = _field(left + shift, right + shift)
            slices.append(({"model": model, "gwl": "2", "quantile": q}, lon, lat, values))
    out = pluvial.gridded_change_by_region(_admin(), slices, return_period=50)
    assert out.loc[0, "ecde_flood_rp50_change_pct_ehype_gwl2_p50"] == 10.0
    assert out.loc[0, "ecde_flood_rp50_change_pct_vicwur_gwl2_p83"] == 23.0
    assert out.loc[0, "ecde_flood_rp50_change_pct_ehype_gwl2_points"] == 100
    assert out.loc[0, "ecde_flood_rp50_models_agree_gwl2"] == True  # noqa: E712
    assert out.loc[1, "ecde_flood_rp50_models_agree_gwl2"] == False  # noqa: E712


def test_agreement_is_unknown_when_one_model_is_not_measured():
    lon, lat, values = _field(10.0, 10.0)
    missing = values.copy()
    missing[lon >= 1.0] = np.nan
    slices = [({"model": "ehype", "gwl": "2", "quantile": 50}, lon, lat, values),
              ({"model": "vicwur", "gwl": "2", "quantile": 50}, lon, lat, missing)]
    out = pluvial.gridded_change_by_region(_admin(), slices, return_period=5)
    assert out.loc[0, "ecde_flood_rp5_models_agree_gwl2"] == True  # noqa: E712
    assert pd.isna(out.loc[1, "ecde_flood_rp5_models_agree_gwl2"])


def test_by_region_reads_a_real_netcdf(tmp_path):
    xr = pytest.importorskip("xarray")
    pytest.importorskip("netCDF4")
    long = _long({"BE33": 1.0, "BE34": 2.0}).set_index(["nuts_id", "gwl", "quantile", "ref_period"])
    ds = xr.Dataset.from_dataframe(long)
    ds["rx5_mean"] = ds["rx5"] * 1000  # an ensemble mean must never be read
    ds.to_netcdf(tmp_path / "ecde_precipitation_nuts_level_2__rx5day.nc")
    admin = gpd.GeoDataFrame({"nuts_id": ["BE331", "BE341"]},
                             geometry=[box(0, 0, 1, 1)] * 2, crs="EPSG:4326")
    frame, note = pluvial.by_region(admin, directory=tmp_path)
    assert frame.loc[0, "pluvial_rx5day_change_pct_gwl2_p50"] == pytest.approx(21.5)
    assert frame["pluvial_level"].tolist() == [pluvial.LEVEL_PARENT] * 2
    assert "2 inherited" in note


# --- fetcher ----------------------------------------------------------------

#: The three constraint entries that matter, as read on 2026-10-24 (abridged).
CONSTRAINTS = [
    {"origin": ["projections"], "product": ["gwl_relative_change_quantiles"],
     "regional_layer": ["nuts_level_0", "nuts_level_1", "nuts_level_2"],
     "spatial_aggregation": ["regional_layer"], "temporal_aggregation": ["yearly"],
     "variable": sorted(pluvial.PRECIP_VARIABLES), "version": ["v2_0"]},
    {"origin": ["projections"], "other_parameters": ["0m"], "product": ["gwl_relative_change_quantiles"],
     "regional_layer": ["nuts_level_3"], "spatial_aggregation": ["regional_layer"],
     "temporal_aggregation": ["yearly"], "variable": ["snowfall_amount"], "version": ["v2_0"]},
    {"hydrological_model": ["combined", "e_hype", "vic_wur"], "origin": ["projections"],
     "other_parameters": ["1_in_10_year", "1_in_2_year", "1_in_50_year", "1_in_5_year"],
     "product": ["gwl_relative_change_quantiles"], "spatial_aggregation": ["gridded"],
     "temporal_aggregation": ["yearly"], "variable": ["flood_recurrence"], "version": ["v2_0"]},
]


def test_nuts3_is_rejected_for_precipitation_and_nuts2_chosen():
    assert not fetcher.is_valid(fetcher.precipitation_request("nuts_level_3"), CONSTRAINTS)
    jobs = fetcher.plan(CONSTRAINTS, ("precipitation",))
    assert jobs[0][1]["regional_layer"] == ["nuts_level_2"]


def test_nuts3_is_taken_the_day_the_catalogue_offers_it():
    widened = [dict(CONSTRAINTS[0], regional_layer=["nuts_level_2", "nuts_level_3"])] + CONSTRAINTS[1:]
    assert fetcher.plan(widened, ("precipitation",))[0][1]["regional_layer"] == ["nuts_level_3"]


def test_flood_recurrence_is_gridded_with_both_models():
    jobs = fetcher.plan(CONSTRAINTS, ("flood_recurrence",))
    assert [s for s, _ in jobs] == ["ecde_flood_recurrence_1_in_5_year", "ecde_flood_recurrence_1_in_50_year"]
    assert jobs[0][1]["hydrological_model"] == ["e_hype", "vic_wur"]
    regional = dict(jobs[0][1], spatial_aggregation="regional_layer", regional_layer=["nuts_level_2"])
    assert not fetcher.is_valid(regional, CONSTRAINTS)


def test_constraints_are_found_through_the_catalogue():
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class Session:
        def __init__(self):
            self.urls = []

        def get(self, url, timeout):
            self.urls.append(url)
            if url == fetcher.CATALOGUE:
                return Response({"links": [{"rel": "constraints", "href": "https://x/c.json"}]})
            return Response(CONSTRAINTS)

    session = Session()
    assert fetcher.load_constraints(session) == CONSTRAINTS
    assert session.urls == [fetcher.CATALOGUE, "https://x/c.json"]


def test_fetch_unpacks_a_zip_and_names_files_after_the_request(tmp_path):
    import zipfile

    class Client:
        def retrieve(self, name, request, target):
            assert name == fetcher.DATASET
            with zipfile.ZipFile(target, "w") as zf:
                zf.writestr("whatever_the_cds_calls_it.nc", b"CDF\x01")

    names = fetcher.fetch(Client(), [("ecde_flood_recurrence_1_in_5_year", {})], out_dir=tmp_path)
    assert names == ["ecde_flood_recurrence_1_in_5_year.nc"]
    assert not list(tmp_path.glob("*.download"))


def test_licence_refusal_says_what_to_click(tmp_path):
    class Client:
        def retrieve(self, *args):
            raise RuntimeError("403 Client Error: required licences not accepted")

    with pytest.raises(SystemExit, match="Accept the CC-BY licence"):
        fetcher.fetch(Client(), [("x", {})], out_dir=tmp_path)


def test_credentials_never_print_the_key(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    monkeypatch.setenv("CDSAPI_KEY", "secret-key-123")
    monkeypatch.delenv("CDSAPI_URL", raising=False)
    found = fetcher.credentials()
    assert found == {"url": fetcher.DEFAULT_URL, "key": "secret-key-123"}
    assert "secret-key-123" not in capsys.readouterr().out


def test_no_credentials_is_none(monkeypatch, tmp_path):
    monkeypatch.setattr(fetcher, "ROOT", tmp_path)
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.setattr(fetcher.Path, "home", classmethod(lambda cls: tmp_path))
    assert fetcher.credentials() is None


def test_flood_recurrence_reads_a_gridded_netcdf(tmp_path):
    xr = pytest.importorskip("xarray")
    pytest.importorskip("netCDF4")
    lon = np.arange(0.05, 2.0, 0.1)
    lat = np.arange(0.05, 1.0, 0.1)
    values = np.zeros((2, 1, 3, 1, lat.size, lon.size))
    values[0] = 10.0   # e_hype: +10 % everywhere
    values[1] = -4.0   # vic_wur: -4 % everywhere
    ds = xr.Dataset(
        {"flood_recurrence": (("hydrological_model", "gwl", "quantile", "ref_period", "lat", "lon"), values),
         "flood_recurrence_mean": (("hydrological_model", "gwl", "ref_period", "lat", "lon"),
                                   np.full((2, 1, 1, lat.size, lon.size), 999.0))},
        coords={"hydrological_model": ["e_hype", "vic_wur"], "gwl": [2.0], "quantile": [17, 50, 83],
                "ref_period": [np.datetime64("1971-01-01T00:00:00.000000000", "ns")], "lat": lat, "lon": lon},
    )
    ds.to_netcdf(tmp_path / "ecde_flood_recurrence_1_in_50_year.nc")
    frame, note = pluvial.flood_recurrence_by_region(_admin(), directory=tmp_path)
    assert frame.loc[0, "ecde_flood_rp50_change_pct_ehype_gwl2_p50"] == 10.0
    assert frame.loc[1, "ecde_flood_rp50_change_pct_vicwur_gwl2_p17"] == -4.0
    assert (frame["ecde_flood_rp50_models_agree_gwl2"] == False).all()  # noqa: E712
    assert not any("999" in str(v) for v in frame.to_numpy().ravel())
    assert "1 file(s)" in note


def test_a_reference_period_given_as_its_start_date_reads_as_its_normal():
    """The real files carry `ref_period` as 1991-01-01, not "1991-2020": read
    as a date, no row matched and the whole layer failed on the first fetch."""
    import numpy as np

    assert pluvial._period_label(np.datetime64("1991-01-01")) == "1991-2020"
    # What xarray's values print as: the nanoseconds are not a second year.
    assert pluvial._period_label(np.datetime64("1971-01-01T00:00:00.000000000", "ns")) == "1971-2000"
    assert pluvial._period_label("1981-01-01T00:00:00") == "1981-2010"
    assert pluvial._period_label("1991-2020") == "1991-2020"
