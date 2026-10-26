"""Projected heavy rain and flood discharge per region, by global warming level.

The C3S European Climate Data Explorer indicators (`c3s_ecde_climate_indicators`
in config/sources.yaml; CDS dataset `sis-ecde-aggregated-climate-indicators`)
give two things the kit lacks:

* **The pluvial side.** Maximum consecutive five-day precipitation, the
  extreme precipitation total (rain above the 1991-2020 95th percentile) and
  the number of such days. The river maps and the discharge projections say
  nothing about a cloudburst over a sealed town; these do. `by_region`.
* **A second hydrological model for flood discharge.** The ECDE flood
  recurrence indicator is published for E-HYPE AND VIC-WUR side by side, so
  "the models agree" becomes a statement about two models rather than one.
  `flood_recurrence_by_region`.

**What the catalogue actually offers, measured 2026-10-24** on the public
constraints file and the costing endpoint (`scripts/fetch_c3s_ecde.py`):

* the three precipitation indicators exist as regional aggregates down to
  **NUTS2** and no finer: a request at `nuts_level_3` is rejected ("Request has
  not produced a valid combination of values"), and so is a gridded one. The
  form's regional-layer list shows NUTS3 because one variable (snowfall) has it.
* flood recurrence exists **gridded only** (no regional layer), for `e_hype`,
  `vic_wur` and `combined`, at the 2, 5, 10 and 50-year return periods.

So a NUTS3 region takes its own value when the file has one and its NUTS2
parent's otherwise (a NUTS3 code's first four characters), and the per-row
`pluvial_level` column says which, exactly like `household_income_level` in
`src/demographics.py`. The gridded discharge is aggregated point-in-polygon
with `climate.change_by_region`, the same rule as the existing discharge
columns.

**Ensemble statistics: the published quantiles, never the mean.** The product
`gwl_relative_change_quantiles` gives, per warming level (+1.5, +2, +3, +4 C),
the 17th, 50th and 83rd percentiles of the ensemble's relative change against
the reference period. The 50th is the figure to quote and 17-83 is the IPCC
"likely" range. The product also ships an ensemble MEAN, and it is not read: a
relative change has no upper bound (our climate rule) and a mean of one
belongs to its tail. For the gridded discharge each region's figure is the
spatial MEDIAN over its cells of the ensemble quantile, never a mean or a
maximum over cells.

The NetCDF files are read with xarray, imported lazily: GDAL's classic netCDF
driver cannot read the string region identifiers of the regional files. Every
step after `open_long` is plain pandas and is tested without xarray.
"""

from __future__ import annotations

import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src import climate
from src.data_io import DATA

ECDE_DIR = DATA / "raw" / "download" / "c3s_ecde_climate_indicators"

#: The only reference period the ECDE flood-recurrence files carry (measured
#: on the first download, 2026-10-24); the precipitation files carry 1981-2010
#: and 1991-2020, and DEFAULT_REF_PERIOD picks the latter for them.
FLOOD_REF_PERIOD = "1971-2000"

#: CDS variable -> short column stem. Short because each one multiplies into
#: warming levels x quantiles columns.
PRECIP_VARIABLES = {
    "maximum_consecutive_five_day_precipitation": "rx5day",
    "extreme_precipitation_total": "extreme_precip_total",
    "frequency_of_extreme_precipitation": "extreme_precip_days",
}
#: Quantiles kept, as integer percent: the ensemble median and the likely range.
QUANTILES = (17, 50, 83)
DEFAULT_REF_PERIOD = "1991-2020"
LEVEL_OWN = "NUTS3"
LEVEL_PARENT = "NUTS2, applied to its NUTS3 children"

#: Dimensions the ECDE product user guide names (section 2.4.3). Any other
#: dimension of a regional file is the region dimension.
_KNOWN_DIMS = {"gwl", "ref_period", "quantile", "scenario", "avg_period", "time",
               "month", "clim_period", "stat", "lat", "lon", "latitude", "longitude",
               "hydrological_model", "model", "bnds", "nv"}
_NUTS = re.compile(r"^[A-Z]{2}[0-9A-Z]{0,3}$")


class EcdeUnavailable(RuntimeError):
    """The ECDE files are not on disk, or xarray is not installed."""


def gwl_label(value) -> str:
    """`1.5`, `"1.5"`, `"+1.5C"` or `"gwl_1.5"` -> `"1p5"`; `2.0` -> `"2"`."""
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if not match:
        raise ValueError(f"unreadable warming level {value!r}")
    number = float(match.group(1))
    return (f"{number:g}").replace(".", "p")


def quantile_percent(value) -> int:
    """`0.5`, `50`, `"50"`, `"q50"` or `"50th"` -> 50."""
    match = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if not match:
        raise ValueError(f"unreadable quantile {value!r}")
    number = float(match.group(1))
    return int(round(number * 100 if number <= 1.0 else number))


def _period_label(value) -> str:
    """A reference period as "1991-2020", whatever form the file gives it.

    The real ECDE files carry it as the period's START date (1991-01-01), not
    as a "1991-2020" string - measured on the first download, 2026-10-24 - and
    a 30-year climate normal is the convention the product names in its
    metadata. A string with two years is taken as it stands.
    """
    # Real years only: as text, an xarray datetime ends in ".000000000", and a
    # bare four-digit pattern read its nanoseconds as a second year ("1971-0000").
    years = re.findall(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)", str(value))
    if len(years) >= 2:
        return "-".join(years[:2])
    if len(years) == 1:
        start = int(years[0])
        return f"{start}-{start + 29}"
    return str(value)


def tidy(long: pd.DataFrame, value: str) -> pd.DataFrame:
    """A file's long frame -> columns `region, gwl, quantile, ref_period, value`.

    `long` is what `xarray.Dataset.to_dataframe().reset_index()` gives for one
    data variable. The region column is found by its content - the one column
    whose values all look like NUTS codes - because the user guide names every
    other dimension but not that one. Rows with no value are dropped here, so
    an unmeasured region stays absent and ends up NaN, never 0.
    """
    frame = long.copy()
    region = [c for c in frame.columns if c not in (value, "gwl", "quantile", "ref_period")
              and (frame[c].dtype == object or pd.api.types.is_string_dtype(frame[c]))
              and frame[c].dropna().astype(str).str.strip().str.match(_NUTS).all()
              and frame[c].notna().any()]
    if len(region) != 1:
        raise ValueError(f"cannot tell the region column among {list(frame.columns)}: {region}")
    for required in ("gwl", "quantile"):
        if required not in frame.columns:
            raise ValueError(f"no `{required}` column in {list(frame.columns)}")
    out = pd.DataFrame({
        "region": frame[region[0]].astype(str).str.strip(),
        "gwl": frame["gwl"].map(gwl_label),
        "quantile": frame["quantile"].map(quantile_percent),
        "ref_period": frame["ref_period"].map(_period_label) if "ref_period" in frame else DEFAULT_REF_PERIOD,
        "value": pd.to_numeric(frame[value], errors="coerce"),
    })
    return out[np.isfinite(out["value"])]


def wide(tidied: dict[str, pd.DataFrame], *, ref_period: str = DEFAULT_REF_PERIOD,
         quantiles: tuple[int, ...] = QUANTILES) -> pd.DataFrame:
    """One row per region, `pluvial_<stem>_change_pct_gwl<g>_p<q>` columns.

    `tidied` maps a column stem (`rx5day`) to a `tidy` frame. Only the chosen
    reference period and quantiles are kept; a file offering neither is an
    error rather than an empty table.
    """
    pieces = []
    for stem, frame in tidied.items():
        frame = frame[(frame["ref_period"] == ref_period) & frame["quantile"].isin(quantiles)]
        if frame.empty:
            raise ValueError(f"{stem}: no row for reference period {ref_period} and quantiles {quantiles}")
        frame = frame.assign(column=f"pluvial_{stem}_change_pct_gwl" + frame["gwl"]
                             + "_p" + frame["quantile"].astype(str))
        pieces.append(frame.pivot_table(index="region", columns="column", values="value",
                                        aggfunc="first"))
    out = pd.concat(pieces, axis=1)
    return out[sorted(out.columns)]


def inherit(nuts3: pd.Series | list[str], regional: pd.DataFrame) -> pd.DataFrame:
    """Each NUTS3 code's own row if `regional` has one, else its NUTS2 parent's.

    Returns a frame aligned with `nuts3` plus `pluvial_level`, which says per
    row which of the two it is - a NUTS2 figure applied to a NUTS3 region is a
    statement about the larger region, and the row must say so. A code with
    neither is NaN throughout, `pluvial_level` included.
    """
    codes = pd.Series(list(nuts3), dtype=object)
    own = regional.reindex(codes.values)
    parent = regional.reindex(codes.str[:4].values)
    has_own = own.notna().any(axis=1).to_numpy()
    has_parent = parent.notna().any(axis=1).to_numpy()
    values = np.where(has_own[:, None], own.to_numpy(), parent.to_numpy())
    out = pd.DataFrame(values, columns=regional.columns)
    out["pluvial_level"] = pd.Series(
        [LEVEL_OWN if o else LEVEL_PARENT if p else None for o, p in zip(has_own, has_parent)],
        dtype=object,
    )
    return out


def open_long(path: str | Path) -> dict[str, pd.DataFrame]:
    """Every data variable of one ECDE NetCDF as a long frame, keyed by name.

    The ensemble MEAN, when a file carries it as its own variable, is skipped
    by name: see the module docstring.
    """
    try:
        import xarray as xr
    except ImportError as exc:
        raise EcdeUnavailable(
            "xarray (with netCDF4 or h5netcdf) is needed to read the ECDE NetCDF "
            "files and is not installed in this environment."
        ) from exc
    out = {}
    with xr.open_dataset(path) as ds:
        for name, array in ds.data_vars.items():
            if "mean" in name.lower() or not ({"gwl", "quantile"} <= set(array.dims)):
                continue
            out[name] = array.to_dataframe(name=name).reset_index()
    return out


def _variable_of(path: Path, name: str) -> str | None:
    """Which precipitation indicator a file or data variable is, by its names."""
    text = f"{path.name} {name}".lower()
    hints = {
        "maximum_consecutive_five_day_precipitation": ("five_day", "rx5", "5day", "max5"),
        "frequency_of_extreme_precipitation": ("frequency", "r95d", "days"),
        "extreme_precipitation_total": ("extreme_precipitation_total", "r95ptot", "total"),
    }
    for variable, keys in hints.items():
        if any(k in text for k in keys):
            return variable
    return None


def by_region(
    admin: gpd.GeoDataFrame,
    *,
    directory: Path | str = ECDE_DIR,
    key: str = "nuts_id",
    ref_period: str = DEFAULT_REF_PERIOD,
) -> tuple[pd.DataFrame | None, str]:
    """The heavy-precipitation columns of `context.parquet`, or `(None, reason)`.

    Columns: `pluvial_<stem>_change_pct_gwl<g>_p<q>` for every indicator,
    warming level and quantile found, `pluvial_level` and `pluvial_ref_period`.
    Values are the ensemble's relative change in percent.
    """
    directory = Path(directory)
    files = sorted(directory.glob("*.nc")) if directory.exists() else []
    files = [f for f in files if "flood_recurrence" not in f.name]
    if not files:
        return None, (f"no ECDE precipitation .nc in {directory} - run "
                      "scripts/fetch_c3s_ecde.py --what precipitation")
    tidied: dict[str, pd.DataFrame] = {}
    try:
        for path in files:
            for name, long in open_long(path).items():
                variable = _variable_of(path, name)
                if variable is None:
                    continue
                stem = PRECIP_VARIABLES[variable]
                frame = tidy(long, name)
                tidied[stem] = pd.concat([tidied[stem], frame]) if stem in tidied else frame
    except EcdeUnavailable as exc:
        return None, str(exc)
    if not tidied:
        return None, f"no precipitation indicator recognised in {[f.name for f in files]}"
    regional = wide(tidied, ref_period=ref_period)
    frame = inherit(admin[key], regional)
    frame.index = admin.index
    frame["pluvial_ref_period"] = ref_period
    levels = frame["pluvial_level"].value_counts()
    return frame, (
        f"ECDE GWL relative change quantiles vs {ref_period}, {sorted(tidied)}; "
        f"{int(levels.get(LEVEL_OWN, 0))} units at NUTS3, "
        f"{int(levels.get(LEVEL_PARENT, 0))} inherited from NUTS2, "
        f"{int(frame['pluvial_level'].isna().sum())} unmatched"
    )


def _model_label(value) -> str:
    """`e_hype`, `E-HYPE` -> `ehype`; `vic_wur`, `VIC-WUR` -> `vicwur`."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def gridded_change_by_region(
    admin: gpd.GeoDataFrame,
    slices: list[tuple[dict, np.ndarray, np.ndarray, np.ndarray]],
    *,
    return_period: int,
    min_points: int = climate.MIN_POINTS,
) -> pd.DataFrame:
    """Per region, the spatial median of each (model, warming level, quantile) field.

    `slices` holds `(labels, lon, lat, values)` with `labels` carrying `model`,
    `gwl` (already `gwl_label`led) and `quantile` (integer percent). Columns are
    `ecde_flood_rp<N>_change_pct_<model>_gwl<g>_p<q>` - the median over the
    region's cells of the ensemble's q-th percentile - and, per model and
    level, `..._points`. Then, wherever two or more models are present,
    `ecde_flood_rp<N>_models_agree_gwl<g>`: True when every model's p50 points
    the same way, False when they do not, NaN when one of them is not measured.
    """
    out = pd.DataFrame(index=admin.index)
    for labels, lon, lat, values in slices:
        stem = f"ecde_flood_rp{return_period}_change_pct_{labels['model']}_gwl{labels['gwl']}"
        measured = climate.change_by_region(admin, lon, lat, values, min_points=min_points)
        out[f"{stem}_p{labels['quantile']}"] = measured["change_pct_median"]
        out[f"{stem}_points"] = measured["change_points"]
    models = sorted({lab["model"] for lab, *_ in slices})
    for gwl in sorted({lab["gwl"] for lab, *_ in slices}):
        columns = [f"ecde_flood_rp{return_period}_change_pct_{m}_gwl{gwl}_p50" for m in models]
        columns = [c for c in columns if c in out]
        if len(columns) < 2:
            continue
        signs = np.sign(out[columns])
        agree = (signs.nunique(axis=1) == 1) & (signs.iloc[:, 0] != 0)
        out[f"ecde_flood_rp{return_period}_models_agree_gwl{gwl}"] = agree.where(
            signs.notna().all(axis=1)
        )
    return out[sorted(out.columns)]


def _gridded_slices(path: Path, ref_period: str, quantiles) -> tuple[int, list]:
    """`(return_period, slices)` from one gridded ECDE flood-recurrence file."""
    try:
        import xarray as xr
    except ImportError as exc:
        raise EcdeUnavailable("xarray is needed to read the ECDE NetCDF files") from exc
    match = re.search(r"1_in_(\d+)_year|rp(\d+)", path.name)
    slices = []
    with xr.open_dataset(path) as ds:
        names = [n for n, a in ds.data_vars.items()
                 if "mean" not in n.lower() and {"gwl", "quantile"} <= set(a.dims)]
        if len(names) != 1:
            raise ValueError(f"{path.name}: expected one quantile variable, found {names}")
        array = ds[names[0]]
        lat_name = "lat" if "lat" in array.dims else "latitude"
        lon_name = "lon" if "lon" in array.dims else "longitude"
        if "ref_period" in array.dims:
            wanted = [v for v in array["ref_period"].values if _period_label(v) == ref_period]
            if not wanted:
                raise ValueError(f"{path.name}: no reference period {ref_period}")
            array = array.sel(ref_period=wanted[0])
        # The real files carry a one-value `month` dimension (month 12 for a
        # yearly indicator, measured 2026-10-24) that the user guide does not
        # mention; any dimension of length one carries no choice, so it goes.
        single = [d for d in array.dims if array.sizes[d] == 1
                  and d not in (lat_name, lon_name, "gwl", "quantile")]
        if single:
            array = array.squeeze(single, drop=True)
        model_dim = next((d for d in ("hydrological_model", "model") if d in array.dims), None)
        file_model = _model_label(next((m for m in ("e_hype", "vic_wur", "combined")
                                        if m.replace("_", "") in path.name.lower().replace("-", "").replace("_", "")), "unknown"))
        models = array[model_dim].values if model_dim else [None]
        lon, lat = np.meshgrid(array[lon_name].values, array[lat_name].values)
        for model in models:
            per_model = array.sel({model_dim: model}) if model_dim else array
            for gwl in per_model["gwl"].values:
                for q in per_model["quantile"].values:
                    if quantile_percent(q) not in quantiles:
                        continue
                    field = per_model.sel(gwl=gwl, quantile=q).transpose(lat_name, lon_name).values
                    labels = {"model": _model_label(model) if model is not None else file_model,
                              "gwl": gwl_label(gwl), "quantile": quantile_percent(q)}
                    slices.append((labels, lon, lat, np.asarray(field, dtype="float64")))
    return (int(next(g for g in match.groups() if g)) if match else 0), slices


def flood_recurrence_by_region(
    admin: gpd.GeoDataFrame,
    *,
    directory: Path | str = ECDE_DIR,
    ref_period: str = FLOOD_REF_PERIOD,
    quantiles: tuple[int, ...] = QUANTILES,
) -> tuple[pd.DataFrame | None, str]:
    """The two-model flood-discharge columns of `context.parquet`, or `(None, reason)`.

    Against 1971-2000, not the 1991-2020 of the precipitation indicators:
    measured on the real files (2026-10-24), flood recurrence is published
    against that single reference period, at three warming levels (+1.5, +2,
    +3 C). The two are therefore never compared in one sentence.

    One file per return period (`*flood_recurrence*1_in_<N>_year*.nc`, as
    `scripts/fetch_c3s_ecde.py` names them). The admin frame must be in a
    projected or geographic CRS geopandas can join points against;
    `climate.change_by_region` reprojects the points, never the polygons.
    """
    directory = Path(directory)
    files = sorted(directory.glob("*flood_recurrence*.nc")) if directory.exists() else []
    if not files:
        return None, (f"no ECDE flood-recurrence .nc in {directory} - run "
                      "scripts/fetch_c3s_ecde.py --what flood_recurrence")
    frames = []
    try:
        for path in files:
            rp, slices = _gridded_slices(path, ref_period, quantiles)
            frames.append(gridded_change_by_region(admin, slices, return_period=rp))
    except EcdeUnavailable as exc:
        return None, str(exc)
    frame = pd.concat(frames, axis=1)
    return frame, f"ECDE flood recurrence, {len(files)} file(s), vs {ref_period}, gridded -> spatial median"
