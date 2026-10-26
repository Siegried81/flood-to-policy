"""Export the frozen tables as the flat files the Power BI project reads.

`bi/FloodPolicyKit.pbip` is a third front end beside Streamlit and React, and a
third front end is a third place where a figure can drift. So it computes
nothing: every number it shows is written here, from the same two frozen
parquets and the same helpers the app uses, and `tests/test_export_bi.py`
checks the totals against them.

Three shapes are chosen for Power BI, not for Python:

* **Two tables, one direction.** `regions.csv` holds one row per NUTS3 region
  with everything that is a property of the region - names, population,
  demographics, the context layers, the expected annual exposure.
  `exposure.csv` holds one row per region and return period. A star with one
  fact and one dimension needs no bidirectional relationship, which is where
  Power BI models start answering a different question than the one asked.
* **Lists become text.** `shared_with` and `shared_basins` are lists in the
  parquet; Power Query reads a list cell as an error. They are joined with
  "; " - not ", ", because a basin name can hold a comma ("Teno, Naatamo and
  Paatsjoki") and would split in two - and the first basin - the one holding most of the region - also gets
  its own column, so a slicer can filter on it.
* **CSV, UTF-8, dot decimals.** Read the same way whatever the locale of the
  machine Power BI runs on; a Belgian locale would otherwise read 0.5 as 5.

The polygons are optional: when `data/processed/regions.geojson` exists,
`regions.topojson` is written for the Shape map visual, which reads TopoJSON
only. Like the GeoJSON it is not committed (GISCO terms,
`data/processed/DATA_NOTICE.md`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.demographics import with_current_names  # noqa: E402
from src.exposure import expected_annual_exposure  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "bi" / "data"

#: Eurostat country codes of the EU-27, Greece as EL. The kit's table holds 37
#: countries, and every EU-level figure in the brief is quoted on these 27: a
#: flag column rather than a filtered file, so the other ten stay visible.
EU27 = frozenset(
    "AT BE BG CY CZ DE DK EE EL ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split()
)

#: Per-region columns of `exposure.parquet` - identical on every return period.
REGION_COLUMNS = [
    "nuts_id", "region", "country", "country_name", "total_pop",
    "share_over_65", "poverty_rate_pct",
]

#: Per-scenario columns, one row per region and return period. The residual
#: reading (behind the JRC protection standards) sits beside the undefended one
#: on the same row, so one return-period filter drives both.
EXPOSURE_COLUMNS = [
    "nuts_id", "return_period", "annual_probability", "exposed_pop", "hazard_coverage",
    "residual_exposed_pop",
]

#: Context columns carried into the region table. Named, not "everything": a
#: column added to `context.parquet` later should be a decision to show it here.
CONTEXT_COLUMNS = [
    "shared_basin_share", "basin_area_share", "basin_countries_max",
    "apsfr_share", "apsfr_declared", "apsfr_country_reported",
    "built_share_exposed_rp100", "natura2000_flooded_share_rp100",
    "gdp_meur", "pop_density_per_km2", "household_income_pps_per_hab",
    # Hospitals and schools in the RP100 footprint, undefended and residual.
    "hospitals_total", "hospitals_flooded_rp100", "hospitals_flooded_residual_rp100",
    "schools_total", "schools_flooded_rp100", "schools_flooded_residual_rp100",
    # What moved into the floodplain: today's footprint over 2010 and 2025.
    "exposed_pop_2010_rp100", "pop_total_2010",
    "exposed_built_m2_2010_rp100", "built_total_m2_2010",
    "exposed_built_m2_rp100", "built_total_m2",
    # July 2021 in the EFAS reanalysis (river cells past their return levels).
    "efas_2021_max_rp_exceeded", "efas_2021_cells_over_rp100", "efas_2021_river_cells",
    # Sealed soil (HERA 2010/2020, CLMS 2018) and what the footprint covers (CORINE).
    "sealed_share_2010", "sealed_share_2020",
    "imperviousness_share_2018", "imperviousness_share_in_rp100_2018",
    "imperviousness_rp100_footprint_km2",
    "corine_rp100_footprint_km2",
    "corine_rp100_share_homes", "corine_rp100_share_industry_commerce",
    "corine_rp100_share_transport", "corine_rp100_share_other_artificial",
    "corine_rp100_share_agriculture", "corine_rp100_share_natural",
    "corine_rp100_share_water",
    # Heavy rain and flood recurrence at +2 C (C3S ECDE), ensemble medians.
    "pluvial_rx5day_change_pct_gwl2_p50", "pluvial_level",
    "ecde_flood_rp50_change_pct_ehype_gwl2_p50", "ecde_flood_rp50_change_pct_vicwur_gwl2_p50",
    # River peaks 1991-2020 in the HERA reanalysis: size, season, timing, flood days.
    "hera_peak_trend_pct_per_decade", "hera_cells_increasing_share", "hera_years", "hera_river_cells",
    "hera_winter_peak_share", "hera_peak_timing_shift_days_per_decade",
    "hera_winter_peak_trend_pct_per_decade", "hera_summer_peak_trend_pct_per_decade",
    "hera_flood_days_per_year", "hera_flood_days_trend_per_decade",
] + [
    f"{stat}_{horizon}"
    for horizon in ("2011_2040", "2041_2070", "2071_2100")
    for stat in (
        "change_pct_ensemble_median", "change_pct_ensemble_p25",
        "change_pct_ensemble_p75", "ensemble_agrees_on_sign", "ensemble_robust_on_sign",
    )
]


def _joined(value) -> str:
    """A list cell as "; "-separated text; anything else as an empty string."""
    try:
        return "; ".join(str(v) for v in value)
    except TypeError:
        return ""


def _first(value) -> str:
    """The first item of a list cell - for `shared_basins`, the largest basin."""
    try:
        return str(next(iter(value)))
    except (TypeError, StopIteration):
        return ""


def tables(processed: Path = PROCESSED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The region table and the exposure table, as Power BI will read them.

    Returned rather than written, so a test can compare them with the frozen
    tables without touching the filesystem.
    """
    exposure = with_current_names(pd.read_parquet(processed / "exposure.parquet"))

    regions = exposure[REGION_COLUMNS].drop_duplicates("nuts_id").reset_index(drop=True)
    regions["is_eu27"] = regions["country"].isin(EU27)
    eae = expected_annual_exposure(exposure, key="nuts_id")[
        ["nuts_id", "expected_annual_exposure", "expected_annual_exposure_closed"]
    ]
    regions = regions.merge(eae, on="nuts_id", how="left")

    context_path = processed / "context.parquet"
    if context_path.exists():
        context = pd.read_parquet(context_path)
        # Every named column, empty when its layer has not run here (HERA needs
        # 69 GB of local files): the model's columns never depend on what is on disk.
        kept = context[["nuts_id"]].join(context.reindex(columns=CONTEXT_COLUMNS))
        for column in ("shared_with", "shared_basins"):
            if column in context.columns:
                kept[column] = context[column].map(_joined)
        if "shared_basins" in context.columns:
            kept["main_shared_basin"] = context["shared_basins"].map(_first)
        regions = regions.merge(kept, on="nuts_id", how="left")

    # The residual run itself is local, but build_context.py copies it into the
    # committed context.parquet as residual_exposed_pop_rp*, so a fresh clone
    # still has it. The run is read first because it is the newer of the two.
    protected_path = processed / "exposure_protected.parquet"
    residual = None
    if protected_path.exists():
        residual = pd.read_parquet(protected_path)[["nuts_id", "return_period", "exposed_pop"]]
        residual = residual.rename(columns={"exposed_pop": "residual_exposed_pop"})
    elif context_path.exists():
        context = pd.read_parquet(context_path)
        columns = [c for c in context.columns if c.startswith("residual_exposed_pop_rp")]
        if columns:
            residual = context.melt(id_vars="nuts_id", value_vars=columns,
                                    var_name="return_period", value_name="residual_exposed_pop")
            residual["return_period"] = (residual["return_period"]
                                         .str.removeprefix("residual_exposed_pop_rp").astype(int))
    if residual is not None:
        exposure = exposure.merge(residual, on=["nuts_id", "return_period"], how="left")
    else:
        # Neither on disk: an empty column, so the model's columns never depend
        # on what is on disk.
        exposure = exposure.assign(residual_exposed_pop=float("nan"))
    return regions, exposure[EXPOSURE_COLUMNS].reset_index(drop=True)


def topojson(geojson: dict) -> dict:
    """GeoJSON polygons as TopoJSON, which is all the Shape map visual reads.

    Each ring becomes its own arc, unquantized: no shared borders, so the file is
    larger than a real topology would be, but it needs no library and the
    coordinates are exactly the GeoJSON's. `nuts_id` and `name` are kept as
    properties - the Shape map joins on `nuts_id`.
    """
    arcs: list = []
    geometries = []

    def ring_ids(rings):
        ids = []
        for ring in rings:
            arcs.append(ring)
            ids.append(len(arcs) - 1)
        return ids

    for feature in geojson["features"]:
        geometry = feature["geometry"]
        if geometry["type"] == "Polygon":
            shape = {"type": "Polygon", "arcs": ring_ids(geometry["coordinates"])}
        elif geometry["type"] == "MultiPolygon":
            shape = {"type": "MultiPolygon",
                     "arcs": [ring_ids(polygon) for polygon in geometry["coordinates"]]}
        else:
            continue
        shape["properties"] = feature.get("properties", {})
        geometries.append(shape)
    return {
        "type": "Topology",
        "objects": {"regions": {"type": "GeometryCollection", "geometries": geometries}},
        "arcs": arcs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, default=PROCESSED)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    regions, exposure = tables(args.processed)
    args.out.mkdir(parents=True, exist_ok=True)
    regions.to_csv(args.out / "regions.csv", index=False, encoding="utf-8")
    exposure.to_csv(args.out / "exposure.csv", index=False, encoding="utf-8")
    print(f"{args.out / 'regions.csv'}: {len(regions)} regions, {regions.shape[1]} columns")
    print(f"{args.out / 'exposure.csv'}: {len(exposure)} rows")

    geometry = args.processed / "regions.geojson"
    if geometry.exists():
        shapes = topojson(json.loads(geometry.read_text(encoding="utf-8")))
        (args.out / "regions.topojson").write_text(
            json.dumps(shapes, separators=(",", ":")), encoding="utf-8"
        )
        print(f"{args.out / 'regions.topojson'}: "
              f"{len(shapes['objects']['regions']['geometries'])} regions")
    else:
        print("no regions.geojson: run scripts/build_geometry.py for the Shape map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
