"""Built-up surface exposed to flooding - the asset half of the exposure term.

`exposure.py` answers "how many people are in the water". This answers "how much
is built there", which is the question behind every recommendation about where
building is still permitted. A brief that reaches only the first number can say
who to warn; it cannot say where to stop pouring concrete.

**Why this module is thin on purpose.** `exposure.exposed_population` sums
whatever per-cell quantity it is handed, over whatever grid that raster is on.
GHS-BUILT-S is on exactly the same 1 km Mollweide grid, same epoch and same cell
size as GHS-POP, so handing it the built-up raster is not a trick - it is the
same arithmetic on a different summable quantity, and duplicating the windowing,
the masking and the coverage bookkeeping to say "m2" instead of "people" would be
two implementations of one measurement, drifting apart from the first bug fixed
in only one of them.

**The unit is square metres of footprint.** Not a share, not a value, not a
building count. A warehouse and a hospital of the same size are the same number
here. This ranks what is physically at stake and says nothing about what it
costs - state that, because a jury will ask, and the honest answer is that
monetising it needs damage curves this kit does not carry.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterstats import zonal_stats

from src.exposure import exposed_population

DATA = Path(__file__).resolve().parents[1] / "data"
BUILT_ZIP = DATA / "raw" / "download" / "ghsl_built_europe.zip"

def built_path(archive: Path | str = BUILT_ZIP) -> str:
    """A GDAL path into the single GeoTIFF inside the GHS-BUILT archive.

    Mirrors `scripts.build_exposure.population_path`: the fetcher stores the
    archive as it was published rather than unpacking it, so that a re-run can
    tell a complete download from a partial one by its size alone.
    """
    archive = Path(archive)
    if not archive.exists():
        raise SystemExit(
            f"{archive} is missing. Run `python -m src.fetch` first: it is "
            f"declared as `ghsl_built_europe` in config/sources.yaml and "
            f"`data/raw/` is not committed."
        )
    with zipfile.ZipFile(archive) as zf:
        tifs = [n for n in zf.namelist() if n.lower().endswith(".tif")]
    if len(tifs) != 1:
        raise SystemExit(
            f"Expected exactly one .tif in {archive.name}, found {tifs}. "
            f"GHS-BUILT ships one raster per archive; more than one means the "
            f"wrong product was downloaded."
        )
    return f"zip://{archive.as_posix()}!/{tifs[0]}"


def total_built_surface(path: str, admin: gpd.GeoDataFrame) -> pd.Series:
    """Built-up square metres per unit, flooded or not - the denominator.

    Separate from the exposed figure because the two answer different questions
    and because a share needs both: 40,000 m2 exposed is alarming in a village
    and invisible in Rotterdam. `all_touched=False` to match the exposed side
    exactly; a cell counted in one and not the other makes a share above 1.
    """
    with rasterio.open(path) as src:
        nodata = src.nodata
        # Polygons to the raster, never the raster to the polygons: reprojecting
        # a raster of quantities moves surface between cells.
        polygons = admin.to_crs(src.crs)
    stats = zonal_stats(
        polygons, path, stats=["sum"], nodata=nodata, all_touched=False
    )
    return pd.Series(
        [s["sum"] if s["sum"] is not None else None for s in stats],
        index=admin.index,
        dtype="float64",
    )


def exposed_built_surface(
    hazard_path: str,
    path: str,
    admin: gpd.GeoDataFrame,
    **kwargs,
) -> gpd.GeoDataFrame:
    """Built-up square metres on flood-prone ground, per unit.

    Every keyword goes straight to `exposure.exposed_population`, so `mode`,
    `min_depth_m`, `nodata_means_dry` and `pop_window` mean exactly what they
    mean there - including the default `min_depth_m=0.0`, which is "any water".
    Pass 0.5 to match the exposure table's own default, or the two halves of the
    same brief disagree about what counts as flooded.

    The columns are renamed because `exposed_pop` would be a lie about the unit:
    `exposed_built_m2` is a surface. `cells_counted` and `hazard_coverage` keep
    their names and their meaning, and `hazard_coverage` must still be reported
    beside the figure - below 1.0 it is an extrapolation.

    **The hazard path is taken as given, masks and all.** `scripts/build_exposure.py`
    patches out permanent water bodies and the JRC's own spurious-area flags
    before measuring population, which moves the Benelux RP100 figure by -14.2%.
    Nothing here does that. A built-up figure from a raw raster is therefore NOT
    comparable with `exposed_pop` from the frozen table: it counts the river
    channel and the lakes as flooded ground. Hand this function a hazard raster
    masked the same way, or say in the brief that the two halves were measured
    differently.
    """
    out = exposed_population(hazard_path, path, admin, **kwargs)
    return out.rename(
        columns={"exposed_pop": "exposed_built_m2",
                 "exposed_pop_observed": "exposed_built_m2_observed"}
    )


def built_exposure(
    hazard_path: str,
    path: str,
    admin: gpd.GeoDataFrame,
    **kwargs,
) -> gpd.GeoDataFrame:
    """The exposed surface, the total, and the share of the built-up that floods.

    `built_share_exposed` is the figure to rank on. An absolute surface ranks by
    how built-up a region is, which a decision-maker already knows; the share
    ranks by how much of what exists is in the way of the water, which is the
    thing they can act on.

    None rather than 0.0 wherever the denominator is absent or zero: a region
    with no built-up surface at all has no share, and calling that 0% would put
    it at the safe end of a ranking it does not belong in.

    **The share uses the OBSERVED numerator, not the reported one.**
    `exposed_built_m2` carries the extrapolation onto the part of the unit the
    hazard layer did not reach; `built_total_m2` is a plain sum over the whole
    unit and carries none. Dividing one by the other mixes two different
    denominators and reached **2.0** on a unit whose unobserved half was empty
    ground - 200% of the built-up surface "exposed", on the figure this function
    calls the one to rank on. The observed numerator is in range by
    construction, and `hazard_coverage` beside it says how much of the unit the
    pair describes.
    """
    out = exposed_built_surface(hazard_path, path, admin, **kwargs)
    out["built_total_m2"] = total_built_surface(path, admin)
    # to_numeric: `exposed_population` returns Python None for "not measured",
    # which makes the column object dtype as soon as one unit is unmeasured, and
    # object dtype will not divide.
    observed = pd.to_numeric(out["exposed_built_m2_observed"], errors="coerce")
    total = pd.to_numeric(out["built_total_m2"], errors="coerce")
    out["exposed_built_m2"] = pd.to_numeric(out["exposed_built_m2"], errors="coerce")
    out["built_share_exposed"] = observed.divide(total.where(total > 0))
    return out
