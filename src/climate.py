"""Future flood hazard, per region - the one layer in this kit that is not today.

Everything else here measures present-day risk, which is a description. A region
crossing from "not a priority" to "priority" is a decision, and it is the only
thing in a brief a planner can act on years ahead.

The source is `cds_hydrology_projections` in `config/sources.yaml`: Copernicus
C3S / SMHI indicators from eight bias-adjusted EURO-CORDEX simulations forcing
E-HYPE. The variable this module is built for is the **relative change in the
N-year return value of annual maximum river discharge** between a future period
and the 1971-2000 reference, in percent.

Three properties of that data decide every design choice below.

**It is discharge, not depth.** A 50-year flow in m3/s cannot be subtracted from
or layered onto the JRC inundation maps. What travels is the direction and the
size of the change, applied to the present-day exposure computed elsewhere in
this kit. A future headcount quoted as if it had been measured is not defensible.

**A relative change has no upper bound.** Where the 1971-2000 reference discharge
is near zero - intermittent rivers, arid basins - the ratio explodes. Measured
2026-10-06 on the 50-year recurrence, 2041-2070 against 1971-2000, RCP 8.5,
E-HYPEgrid: median +16.9%, minimum -100%, maximum **+16,452,833%**. So this
module reports the MEDIAN and the quartiles and never a mean or a maximum. A mean
belongs entirely to that tail, and a maximum is a sentence that ends a pitch.

**The grid is curvilinear.** The file carries no affine transform: `lon` and `lat`
are their own 950x1000 arrays beside the variable. Resampling onto another grid
would mean interpolating a ratio, which is the same error as averaging one. The
aggregation here is therefore point-in-polygon on the real coordinates: each grid
cell contributes its own value to whichever region contains its centre, and the
region's figure is a quantile over those values.
"""

from __future__ import annotations

import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
CLIMATE_DIR = DATA / "raw" / "download" / "cds_hydrology_projections"

#: EPSG:4326. The `lon`/`lat` arrays are degrees, so the points start there and
#: are reprojected to the admin frame's own CRS before the join - polygons are
#: never reprojected to meet them, because a NUTS3 boundary in degrees is a
#: different shape.
POINT_CRS = "EPSG:4326"

#: Below this many grid cells, a quantile is not a summary of anything. At 5 km a
#: NUTS3 region holds hundreds; a region with fewer is a city district or an
#: island, and reporting its median beside Bavaria's would be dishonest.
MIN_POINTS = 10

#: Share of members that must point the same way for a direction to be called
#: robust: the IPCC AR6 convention (at least 80 % of models agree on the sign).
#: Thirteen of sixteen, both of two.
ROBUST_SHARE = 0.8

#: The CDS filename carries the whole request. Parsed rather than trusted from a
#: sidecar, because the sidecar is what goes missing when files are moved by hand.
_NAME = re.compile(
    r"^(?P<variable>[a-z0-9]+)_(?P<aggregation>[a-z]+)_(?P<kind>rel|abs|value)_"
    r"(?P<hydro_model>[A-Za-z0-9\-]+)_(?P<gcm>[A-Za-z0-9\-]+)_"
    r"(?P<experiment>[a-z0-9]+)_(?P<member>r\d+i\d+p\d+)_"
    r"(?P<rcm>[A-Za-z0-9\-\.]+)_(?P<period>\d{4}-\d{4})_"
    r"(?P<reference>\d{4}-\d{4})_(?P<grid>[a-z0-9]+)_v(?P<version>\d+)\.nc$"
)


def describe(filename: str | Path) -> dict[str, str]:
    """What one CDS file is, from its name.

    Every field matters in a brief: the period and the reference say what the
    percentage is a change *between*, and the model, GCM, RCM and member say
    which plausible world it belongs to. A figure quoted without them is not
    reproducible, and a jury that asks "which scenario?" is entitled to an answer
    shorter than a paragraph.
    """
    name = Path(filename).name
    match = _NAME.match(name)
    if not match:
        raise ValueError(
            f"{name} does not look like a CDS hydrology-projections file. Expected "
            f"<variable>_<aggregation>_<rel|abs|value>_<model>_<gcm>_<experiment>_"
            f"<member>_<rcm>_<period>_<reference>_<grid>_v<n>.nc"
        )
    return match.groupdict()


def change_points(
    lon: np.ndarray, lat: np.ndarray, values: np.ndarray
) -> gpd.GeoDataFrame:
    """One point per valid grid cell, carrying its value.

    Takes arrays rather than a path so the aggregation can be tested without
    building a NetCDF, and so a caller that already has the data in memory does
    not read it twice.

    Masked and non-finite cells are dropped here rather than filtered later: a
    nodata sentinel of 1e20 surviving into a quantile would put every region's
    median at the top of the ranking.
    """
    if not (lon.shape == lat.shape == values.shape):
        raise ValueError(
            f"lon {lon.shape}, lat {lat.shape} and values {values.shape} must be "
            f"the same shape: they are three readings of one curvilinear grid."
        )
    flat_lon = np.ma.filled(np.ma.asarray(lon), np.nan).ravel()
    flat_lat = np.ma.filled(np.ma.asarray(lat), np.nan).ravel()
    flat_val = np.ma.filled(np.ma.asarray(values, dtype="float64"), np.nan).ravel()
    keep = np.isfinite(flat_lon) & np.isfinite(flat_lat) & np.isfinite(flat_val)
    return gpd.GeoDataFrame(
        {"change_pct": flat_val[keep]},
        geometry=gpd.points_from_xy(flat_lon[keep], flat_lat[keep]),
        crs=POINT_CRS,
    )


def change_by_region(
    admin: gpd.GeoDataFrame,
    lon: np.ndarray,
    lat: np.ndarray,
    values: np.ndarray,
    *,
    min_points: int = MIN_POINTS,
) -> pd.DataFrame:
    """Median and quartiles of the relative change, per administrative unit.

    Returns four columns, and the fourth is not optional in a brief:

    - `change_pct_median` - the figure to rank and to quote.
    - `change_pct_p25`, `change_pct_p75` - the spread WITHIN the region. Not the
      ensemble spread, which needs several files; this says whether a region
      changes uniformly or holds one catchment doing something else entirely.
    - `change_points` - how many grid cells the median is over. Below
      `min_points` every figure is None rather than a number computed from three
      cells, because a quantile over three cells is the cells, not a summary.

    No mean and no maximum, deliberately: see the module docstring. A region with
    one intermittent river would otherwise lead the ranking on a division by
    nearly zero.
    """
    points = change_points(lon, lat, values)
    joined = gpd.sjoin(
        points.to_crs(admin.crs), admin[["geometry"]], how="inner", predicate="within"
    )
    grouped = joined.groupby("index_right")["change_pct"]
    out = pd.DataFrame(
        {
            "change_pct_median": grouped.median(),
            "change_pct_p25": grouped.quantile(0.25),
            "change_pct_p75": grouped.quantile(0.75),
            "change_points": grouped.size(),
        }
    ).reindex(admin.index)
    out["change_points"] = out["change_points"].fillna(0).astype("int64")
    thin = out["change_points"] < min_points
    out.loc[thin, ["change_pct_median", "change_pct_p25", "change_pct_p75"]] = np.nan
    return out


def ensemble_change_by_region(
    admin: gpd.GeoDataFrame,
    paths,
    *,
    min_points: int = MIN_POINTS,
) -> pd.DataFrame:
    """Agree across ensemble members, and say where they do not.

    `change_by_region` summarises ONE member - one hydrological model forced by
    one GCM/RCM pair and one realisation. Its quartiles describe the spread
    WITHIN a region, which is a different thing from the spread between
    plausible worlds, and it is the second one that decides whether a regional
    figure can be quoted at all.

    Measured on the real files, 2026-10-06: on the single member
    E-HYPEgrid/EC-EARTH/r12i1p1 under RCP 8.5, BE213 (Turnhout) reads +14% for
    2011-2040, +202% for 2041-2070 and +41% for 2071-2100. That is not a
    trajectory, it is one member moving around. BE256 (Roeselare) reads +55%,
    +57%, +66% on the same member and is a signal. Nothing in a single-member
    table distinguishes the two.

    Returns, per unit:

    - `change_pct_ensemble_median` - the median OF the members' medians. The
      figure to quote, and only with the member count beside it.
    - `change_pct_ensemble_min`, `change_pct_ensemble_max` - the range across
      members. Each end is a median of one member, never a cell maximum, so it
      is bounded; but with many members it is one model's outlier.
    - `change_pct_ensemble_p25`, `change_pct_ensemble_p75` - the quartiles of
      the members' medians, linearly interpolated. The interval to quote once
      the ensemble holds more than two chains. With two members they sit a
      quarter of the way in from each end of the range and add nothing to it.
    - `ensemble_members` - how many members contributed a figure for this unit.
    - `ensemble_agrees_on_sign` - True when every member points the same way.
      The one column that licenses a sentence: "flood discharge increases here"
      is defensible where this is True and is not where it is False, whatever
      the median says.
    - `ensemble_robust_on_sign` - True when at least `ROBUST_SHARE` of the
      members point the same way: the IPCC AR6 "robust" convention. Unanimity
      among sixteen members is a stricter test than among two, and one outlier
      chain should not un-license a direction fifteen others agree on. With two
      members it equals `ensemble_agrees_on_sign`; it never licenses a single
      member either.

    All the files must describe the same variable, the same kind of change, the
    same period and the same emissions scenario - members differ in the model
    chain and in nothing else. Mixing 2041-2070 with 2071-2100, or RCP4.5 with
    RCP8.5, would produce a median of two different questions, so it raises
    instead.
    """
    paths = [Path(p) for p in paths]
    if not paths:
        raise ValueError("No files given: an ensemble of nothing has no median.")

    fields = [describe(p) for p in paths]
    for key in ("variable", "kind", "experiment", "period", "reference"):
        values = {f[key] for f in fields}
        if len(values) > 1:
            raise ValueError(
                f"The files disagree on `{key}`: {sorted(values)}. An ensemble "
                f"varies the model chain, not the question - aggregating these "
                f"would take the median of two different quantities."
            )

    # Each member's own label, so a caller can see which ones contributed.
    # Every field that tells two simulations apart is in it, the regional model
    # included: EC-EARTH r12i1p1 drives three RCMs in this dataset, and a label
    # without the RCM gave all three the same key, so each new chain silently
    # replaced the last and the ensemble shrank without a word.
    tags = [
        "_".join(f[k] for k in ("hydro_model", "gcm", "rcm", "member"))
        for f in fields
    ]
    duplicated = sorted({t for t in tags if tags.count(t) > 1})
    if duplicated:
        raise ValueError(
            f"Two files describe the same simulation ({duplicated}). A duplicate "
            f"is not a second opinion; remove one before aggregating."
        )

    medians = {}
    for path, tag in zip(paths, tags):
        lon, lat, values = read_change(path)
        member = change_by_region(admin, lon, lat, values, min_points=min_points)
        medians[tag] = member["change_pct_median"]

    frame = pd.DataFrame(medians)
    positive = frame.gt(0).sum(axis=1)
    negative = frame.lt(0).sum(axis=1)
    counted = frame.notna().sum(axis=1)
    out = pd.DataFrame(
        {
            "change_pct_ensemble_median": frame.median(axis=1, skipna=True),
            "change_pct_ensemble_min": frame.min(axis=1, skipna=True),
            "change_pct_ensemble_max": frame.max(axis=1, skipna=True),
            # The interquartile range of the members' medians: the spread to
            # quote once the ensemble is more than two chains, because the
            # extremes of sixteen members are each one model's outlier.
            "change_pct_ensemble_p25": frame.quantile(0.25, axis=1),
            "change_pct_ensemble_p75": frame.quantile(0.75, axis=1),
            "ensemble_members": counted.astype("int64"),
            # A single member trivially "agrees with itself". Saying True there
            # would licence exactly the sentence this column exists to stop, so
            # one member means unknown, not agreement.
            "ensemble_agrees_on_sign": (
                (counted > 1) & ((positive == counted) | (negative == counted))
            ),
            "ensemble_robust_on_sign": (
                (counted > 1)
                & (positive.combine(negative, max) >= ROBUST_SHARE * counted)
            ),
        },
        index=admin.index,
    )
    out.loc[counted == 0, ["ensemble_agrees_on_sign", "ensemble_robust_on_sign"]] = False
    return out


def read_change(path: str | Path, variable: str | None = None):
    """`(lon, lat, values)` from one CDS NetCDF, as masked arrays.

    `rasterio` is imported inside because GDAL is the heaviest import in this
    stack and the aggregation above does not need it - the same reason the raster
    reads in `src/validate.py` are lazy.

    The variable is derived from the FILENAME rather than guessed from the
    subdatasets. Measured 2026-10-06: the CDS does not ship a uniform layout -
    some files carry `lon`, `lat` and the indicator, and others carry `time_bnds`
    alongside, at which point "the one that is not lon or lat" is two candidates
    and the read fails on a file that is perfectly good. The name already states
    the variable, `describe` already parses it, and the coordinate-bounds arrays
    are recognisable, so both are used: the filename first, the `_bnds` filter as
    the fallback for a file whose name does not parse.
    """
    import rasterio

    path = Path(path)
    with rasterio.open(path) as container:
        subdatasets = container.subdatasets
    names = {s.rsplit(":", 1)[-1]: s for s in subdatasets}
    if variable is None:
        try:
            declared = describe(path)["variable"]
        except ValueError:
            declared = None
        # The CDS appends `_tmean` (or another statistic) to the variable in the
        # subdataset name but not in the filename's first field, so match on the
        # prefix rather than on equality.
        matching = [n for n in names if declared and n.startswith(declared)]
        candidates = matching or [
            n for n in names
            if n not in ("lon", "lat") and not n.endswith("_bnds")
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"{path.name} holds {sorted(names)}; expected lon, lat and exactly "
                f"one indicator, got candidates {candidates}. Pass `variable=`."
            )
        variable = candidates[0]
    for required in ("lon", "lat", variable):
        if required not in names:
            raise ValueError(f"{path.name} has no `{required}` subdataset.")

    def _read(name: str):
        with rasterio.open(names[name]) as src:
            return src.read(1, masked=True)

    return _read("lon"), _read("lat"), _read(variable)
