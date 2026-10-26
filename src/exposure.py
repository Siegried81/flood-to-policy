"""Hazard x population: how many people sit in the water, per administrative unit.

This is the first number the jury will hear, so it is the one that must be right.
Two rasters are involved - a flood hazard map and a population grid - and they
almost never share a CRS, a resolution or a grid origin. The whole module exists
to make that alignment explicit instead of accidental.

The deliberate choice here: reproject the HAZARD onto the POPULATION grid, never
the other way round. Population cells carry counts of people; resampling them
moves people between cells and silently invents or destroys population. A hazard
mask carries a depth, and resampling it with `max` is a defensible, conservative
reading ("this cell is flooded if any part of it is flooded").

A known limit of `zonal_stats`: a cell is either wholly in a polygon or wholly
out. The induced error scales with perimeter/area, so it is around 1-3% for a
commune (~5,000 cells) and 30-50% for a Belgian statistical sector (tens of
cells). If the scenario asks for anything smaller than a commune, switch to
`exactextract`, which weights each cell by the fraction actually covered. See
docs/geospatial_crash_course.md.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject, transform_geom
from rasterstats import zonal_stats
from shapely.geometry import box, mapping

# The two readings of a partly flooded population cell. Checked rather than
# matched with an `else`: a misspelled mode used to fall through to the binary
# branch, so `mode="fracton"` quietly returned the conservative over-estimate
# (1000 people where "fraction" gives 250) under a name that asked for the other
# number.
MODES = ("fraction", "binary")


def _onto_pop_grid(source, pop, resampling, extra, window=None) -> np.ndarray:
    """Warp one hazard-side array onto the population grid, NaN where unwritten.

    `window` restricts the DESTINATION to part of the population grid. It exists
    so a continental build can be cut into pieces without the pieces interfering:
    a population cell belongs to exactly one window, so nothing is written twice.
    Cutting the hazard raster instead - the obvious way round, and the way this
    was first built - cannot have that property, because a population cell lying
    across two hazard pieces is written by both.

    NaN, not 0, is the destination sentinel. With dst_nodata=0 GDAL refuses to let
    a genuine depth of 0 collide with the sentinel and silently rewrites it to
    1.4e-45 - a positive number, so `> 0` then matches every dry cell and the
    whole study area reads as flooded. NaN cannot collide with a depth, and
    `NaN > threshold` is False.

    It also leaves "the hazard layer never reached this cell" readable afterwards
    with `np.isfinite`, which is what the coverage column is built from: a cell
    the hazard does not cover must not be reported as a measured dry cell.
    """
    shape = (int(window.height), int(window.width)) if window is not None else pop.shape
    transform = pop.window_transform(window) if window is not None else pop.transform
    destination = np.full(shape, np.nan, dtype="float32")
    reproject(
        source=source,
        destination=destination,
        dst_transform=transform,
        dst_crs=pop.crs,
        **extra,
        dst_nodata=np.nan,
        resampling=resampling,
    )
    return destination


def exposed_population(
    hazard_path: str,
    pop_path: str,
    admin: gpd.GeoDataFrame,
    *,
    min_depth_m: float = 0.0,
    mode: str = "fraction",
    nodata_means_dry: bool = True,
    pop_window=None,
) -> gpd.GeoDataFrame:
    """People living in flood-prone cells, summed per administrative unit.

    `min_depth_m` is the depth above which a cell counts as flooded. 0.0 means
    "any water at all"; raising it to 0.5 is the usual threshold for damage to
    buildings, and the difference between the two is worth showing the jury
    because it changes the headline number without any change of data.

    `mode` decides how a population cell that is only partly flooded is counted:

    - **"fraction"** (default) thresholds the hazard into a wet/dry mask at its
      own resolution, then averages that mask onto the population grid. The
      average of a 0/1 mask *is* the share of the cell that is flooded, so
      `people x share` is the expected exposure. Use this whenever the population
      grid is coarser than the hazard - which is the whole European case, where
      1 km population cells each contain roughly 185 hazard cells at Belgian
      latitudes - 164 at 45 deg and 232 at 60 deg, because the cells are not
      square (see `docs/geospatial_crash_course.md`).
    - **"binary"** streams the reprojection and takes `max`, so a cell counts as
      fully flooded if any part of it is. Conservative by construction and it
      never loads the hazard into memory, which is what you want on a continental
      raster you have not windowed yet. At 1 km it over-estimates badly.

    The order matters in "fraction" mode: threshold first, average second.
    Averaging depths and thresholding afterwards answers a different question -
    "is the *mean* depth above the threshold?" - and systematically under-reports
    small deep floods.

    The threshold is compared in the BAND's own units. The hazard maps are metres,
    but the JRC observed layer is uint16 centimetres and the Walloon CLASSEMENT is
    class codes (see `src/validate.py`), so passing such a raster here means
    passing a threshold in those units too.

    `nodata_means_dry` says what the hazard raster's nodata cells are. It decides
    what the figure MEANS, so it is the one argument to get right:

    - **True** (default) - nodata is ground the layer looked at and found dry. The
      pan-European EFAS/JRC `Europe_RP*_filled_depth.tif` maps are like this: they
      are sparse, storing a depth only where there is inundation. Measured on
      RP100 over a 1,468,800-cell window of Belgian land, 4.85% of cells carry a
      value and 100% of those are deeper than 0 - the valid mask IS the flood
      footprint. So the flooded share of a population cell is the wet mask
      averaged over the WHOLE cell, and `hazard_coverage` is the share of the unit
      inside the layer's footprint, which is 1 everywhere but the domain edge.
    - **False** - nodata is ground nobody looked at, which is what an AOI-clipped
      delineation (Copernicus EMSR, the Walloon 2021 layers) gives you. The
      flooded share is then measured over the observed part of the cell only and
      applied to all of the cell's people, and `hazard_coverage` is how much of
      the unit that part was.

    Passing False for a sparse layer collapses the two into the same number: the
    observed mask equals the wet mask, every cell with any water reads as wholly
    flooded, and the figure becomes the "binary" over-estimate under the
    "fraction" name - 2.7x the correct count over BE/NL/LU at RP100, up to 10x in
    one NUTS3 region. Passing True for an AOI-clipped layer reports unobserved
    ground as dry. Neither is recoverable from the output, so it is not inferred.

    Returns `admin`, in the admin frame's own CRS, with four columns:

    - `exposed_pop` - people on flood-prone ground, extrapolated onto the whole
      unit when the layer covered only part of it, or None when nothing was
      measured. None has two causes, both of them "not measured": the unit
      overlaps no population cell (`cells_counted == 0`), or the hazard layer does
      not cover the unit at all (`hazard_coverage == 0`). A measured zero, which
      is a real finding, is `0.0` with a positive coverage.
    - `exposed_pop_observed` - the same count with NO extrapolation in it: people
      on flood-prone ground the layer actually looked at. This is the figure that
      is additive over disjoint pieces of one raster, so a caller measuring a
      raster in windows sums THIS and divides once at the end;
      `scripts/build_exposure.py` does exactly that. Summing `exposed_pop` would
      apply the extrapolation once per window.
    - `cells_counted` - population-grid cells whose centre falls in the unit.
    - `hazard_coverage` - the share of the unit, in [0, 1], the hazard layer
      covers. **Report it next to `exposed_pop`.** Under `nodata_means_dry` that
      is the layer's footprint; otherwise it is the observed part, and below 1.0
      the figure is then an extrapolation from that part onto the whole unit. In
      "fraction" mode coverage is sub-cell exact; in "binary" mode it is per
      population cell (1 if any part of the cell is covered).
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}.")

    with rasterio.open(pop_path) as pop, rasterio.open(hazard_path) as haz:
        # Put the hazard map on the population grid so the two match cell by cell.
        if mode == "fraction":
            band = haz.read(1, masked=True)
            # Threshold at the hazard's OWN resolution, so the mask is built from
            # real depths before anything is averaged away. Averaging a 0/1 mask
            # then yields the share of each population cell that is flooded.
            #
            # Compare first, fill second. `band > min_depth_m` is already boolean,
            # so the fill value is False and never has to be cast into the band's
            # dtype. Filling the DEPTHS with -inf instead raised
            # `TypeError: Cannot convert fill_value -inf to dtype int16` on any
            # integer band, and integer bands are the normal case: depth in
            # centimetres and class codes are both int.
            wet = np.ma.filled(band > min_depth_m, False).astype("float32")
            # What the hazard layer LOOKED AT, warped with exactly the same
            # weighting as `wet`. It becomes `hazard_coverage`, and the per-unit
            # mean of it is the denominator of the extrapolation further down.
            #
            # Under `nodata_means_dry` every cell of the band was looked at, so
            # this is all-ones inside the domain and falls off only at its edge.
            # Reading the valid mask instead would equate "looked at" with "wet"
            # on a sparse layer, and a unit holding any water at all would then
            # report full coverage.
            observed = (
                np.ones(band.shape, dtype="float32")
                if nodata_means_dry
                else (~np.ma.getmaskarray(band)).astype("float32")
            )
            extra = {
                "src_transform": haz.transform, "src_crs": haz.crs, "src_nodata": None,
            }
            on_pop_grid = _onto_pop_grid(wet, pop, Resampling.average, extra, pop_window)
            coverage = np.nan_to_num(
                _onto_pop_grid(observed, pop, Resampling.average, extra, pop_window),
                nan=0.0,
            ).clip(0.0, 1.0)
        else:
            # Streams from the band: never materialises a continental raster, at
            # the cost of over-estimating on a coarse target grid.
            on_pop_grid = _onto_pop_grid(
                rasterio.band(haz, 1), pop, Resampling.max,
                {"src_nodata": haz.nodata}, pop_window,
            )
            # A destination cell whose sources were all nodata keeps the NaN
            # sentinel, so finiteness is the coverage flag here. Coarser than
            # fraction mode - 0 or 1 per population cell - same meaning.
            #
            # Under `nodata_means_dry` that flag would mean "wet", not "covered",
            # and a dry unit would come back as not measured. Every cell of the
            # band was looked at in that reading, so the footprint is the raster's
            # own extent, rasterised onto the population grid - which never reads
            # the band at all, the one property this mode exists for. `segmentize`
            # first because the extent is a rectangle in the HAZARD's CRS and a
            # straight edge there is a curve on the population grid.
            coverage = (
                rasterize(
                    [transform_geom(
                        haz.crs, pop.crs,
                        mapping(box(*haz.bounds).segmentize(min(haz.res) * 8)),
                    )],
                    out_shape=on_pop_grid.shape,
                    transform=(
                        pop.window_transform(pop_window)
                        if pop_window is not None
                        else pop.transform
                    ),
                    dtype="float32",
                )
                if nodata_means_dry
                else np.isfinite(on_pop_grid).astype("float32")
            )

        # masked=True then filled(0): a nodata population cell is 0 people, not NaN.
        # Without this the sums below silently become NaN for whole communes.
        people = pop.read(1, masked=True, window=pop_window).filled(0)
        # Dry cells must stay a real 0 ("measured, nobody exposed"), so the nodata
        # sentinel passed to zonal_stats below has to be a value population can
        # never take. Using 0 here would mark every dry cell as "not measured" and
        # silently shrink the denominator.
        if mode == "fraction":
            # `wet_share` is the wet mask averaged over the WHOLE population cell:
            # a part the layer did not look at contributes 0 to the numerator, not
            # a missing value. So this is the flooded fraction of the whole cell,
            # and it is ADDITIVE over disjoint pieces of the same raster, which is
            # what lets a windowed build sum to the same answer as a single pass.
            #
            # It is deliberately NOT divided by `coverage` here. That division is
            # the extrapolation onto unobserved ground, and it belongs to the unit
            # rather than to the cell - see the `exposed_pop` assignment below.
            wet_share = np.nan_to_num(on_pop_grid, nan=0.0).clip(0.0, 1.0)
            exposed = (people * wet_share).astype("float64")
        else:
            exposed = np.where(on_pop_grid > min_depth_m, people, 0.0).astype("float64")

        # Polygons must be in the raster's CRS, not the other way round: zonal_stats
        # reads the array as-is and only uses the affine transform.
        polygons = admin.to_crs(pop.crs)
        # -1 is impossible for a population count or for a 0-1 coverage share, so
        # nothing real is excluded by it. The obvious choice, 0, would be wrong: it
        # marks every dry cell as "not measured", so `count` stops meaning "cells
        # covered" and a wholly dry commune becomes indistinguishable from one off
        # the map.
        #
        # all_touched=False: a cell belongs to the unit containing its centre. True
        # would count every boundary cell in BOTH neighbours, so the sum over all
        # communes would exceed the national total. Use True only for "does this
        # touch the flood zone at all?" questions.
        zonal = {
            "affine": (
                pop.window_transform(pop_window) if pop_window is not None
                else pop.transform
            ),
            "nodata": -1.0,
            "all_touched": False,
        }
        stats = zonal_stats(polygons, exposed, stats=["sum", "count"], **zonal)
        # The mean of the 0-1 observation mask over a unit's cells IS the share of
        # the unit the hazard layer covers. Same array shape and same sentinel as
        # above, so `count` is identical and the two lists line up row for row.
        covered = zonal_stats(polygons, coverage, stats=["mean"], **zonal)
        # The extrapolation's real denominator. `coverage` averaged over CELLS
        # says what share of the unit's GROUND the layer looked at; what the
        # figure needs is the share of its PEOPLE, because it is people that are
        # being extrapolated. The two differ wherever population and coverage
        # are not independent - which is exactly the domain edge, where the
        # uncovered part is sea or another continent and holds nobody.
        looked_at = zonal_stats(polygons, people * coverage, stats=["sum"], **zonal)
        everyone = zonal_stats(polygons, people.astype("float64"), stats=["sum"], **zonal)

    out = admin.copy()
    # count == 0 means the polygon overlaps no cell at all - outside the raster,
    # or smaller than a cell. numpy sums an empty selection to 0.0, which reads as
    # "nobody is exposed" instead of "not measured", and that difference decides
    # whether a commune belongs in the brief. Keep it missing.
    out["cells_counted"] = [s["count"] or 0 for s in stats]
    out["hazard_coverage"] = [
        (c["mean"] if s["count"] else None) for s, c in zip(stats, covered)
    ]
    # The coverage guard is the one that matters: without it, a unit the
    # POPULATION grid covers but the HAZARD raster does not reports a measured
    # 0.0. In fraction mode its uncovered cells flatten to dry; in binary mode
    # `NaN > min_depth` is False. Either way the answer reads as "nobody is
    # exposed here" about a unit nobody looked at, which is the one error that
    # must never reach a brief, because it reads as reassurance.
    # The additive figure: people on flooded ground the layer actually looked at,
    # with no extrapolation in it. `scripts/build_exposure.py` sums this across
    # stripes and divides once at the end, which is the only way a striped build
    # can agree with an unstriped one.
    out["exposed_pop_observed"] = [
        (s["sum"] if s["count"] else None) for s in stats
    ]
    # The two halves of the extrapolation's denominator, kept so a windowed
    # build can sum them and divide once. Both are additive over disjoint
    # windows; the ratio of their sums is not the sum of their ratios.
    out["pop_observed"] = [(l["sum"] if s["count"] else None)
                           for s, l in zip(stats, looked_at)]
    out["pop_total"] = [(e["sum"] if s["count"] else None)
                        for s, e in zip(stats, everyone)]
    # ...and the reported figure, which carries the observed count onto the
    # unit's whole population. Weighted by PEOPLE, not by cells: dividing by the
    # unweighted cell mean treats a square kilometre of empty sea as if it held
    # the unit's average population, and so doubled the figure for a coastal
    # unit whose unobserved half is water. Where every populated cell was looked
    # at - a pan-European run, almost everywhere - `pop_observed` equals
    # `pop_total` and this is the identity.
    # Binary mode is untouched: it counts whole population cells and has never
    # extrapolated, so dividing there would be a silent change to a second figure.
    out["exposed_pop"] = [
        (
            (s["sum"] * e["sum"] / l["sum"] if mode == "fraction" else s["sum"])
            if s["count"] and (l["sum"] or 0.0) > 0 and (e["sum"] or 0.0) > 0
            else None
        )
        for s, l, e in zip(stats, looked_at, everyone)
    ]
    return out


def exposure_by_return_period(
    hazard_paths: dict[int, str],
    pop_path: str,
    admin: gpd.GeoDataFrame,
    **kwargs,
) -> gpd.GeoDataFrame:
    """One long table: one row per administrative unit x return period.

    Long rather than wide because every downstream consumer wants it that way -
    plotting, the LLM prompt (see `toon_io`), and the expected-annual-damage
    calculation, which needs the probability attached to each row.

    Return-period extents are NESTED in intent: the 100-year flood zone contains
    the 10-year one. So these rows must never be added together - summing RP10 +
    RP100 + RP500 triple counts the core floodplain. Report each separately, or
    integrate over probability with `expected_annual_exposure`. They are not
    nested cell by cell, though: each JRC raster is its own model run, and a few
    regions count fewer people at a rarer period. So never assert that the
    figure only grows with the return period either.
    """
    frames = []
    for return_period, path in sorted(hazard_paths.items()):
        frame = exposed_population(path, pop_path, admin, **kwargs)
        frame["return_period"] = return_period
        # Annual exceedance probability: a 100-year flood has a 1% chance per year.
        # Carried here so nobody has to remember the inversion downstream.
        frame["annual_probability"] = 1.0 / return_period
        frames.append(frame)
    import pandas as pd

    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=admin.crs)


# Exposure is closed to zero at annual probability 1.0 when the frequent tail is
# integrated: ground that floods every single year has been protected, abandoned
# or built differently, so nobody is left in it. An assumption, not a measurement,
# which is why it is named here and reported in its own column rather than folded
# into the headline figure.
CERTAIN_PROBABILITY = 1.0


def expected_annual_exposure(table: gpd.GeoDataFrame, key: str = "lau_id") -> "gpd.GeoDataFrame":
    """Probability-weighted exposure per unit, the entry point to cost-benefit.

    Integrates exposure over the probability of each scenario, which is how the
    `Expected Annual Damage` used in flood economics is built. It lets a single
    number be compared against the annual cost of a measure - the comparison a
    decision-maker actually needs, and the one that distinguishes a policy answer
    from a map.

    **What `expected_annual_exposure` is.** The trapezoidal integral over the
    SAMPLED probability band only, from the rarest return period in the table to
    the most frequent one - nothing else. It is not an EAD and it is not an
    estimate of one; it is a lower bound, and the columns beside it say by how
    much. Each row carries:

    - `probability_band_low` / `probability_band_high` - the band actually
      integrated. With RP {10, 100, 500} that is p in [0.002, 0.1], which is 10%
      of the probability mass. The 90% above it is NOT in the figure.
    - `frequent_tail_exposure` - what closing p in [`probability_band_high`, 1.0]
      costs, under the stated assumption that exposure falls linearly to zero at
      p = 1 (`CERTAIN_PROBABILITY`). For exposure {100, 500, 900} at p {0.1, 0.01,
      0.002} the sampled band integrates to 32.6 and this tail is 45 - larger than
      the headline figure, which is why it is a column and not a footnote.
    - `expected_annual_exposure_closed` - the two added: the integral to p = 1
      under that assumption. Quote this one only with the assumption attached.
    - Nothing below `probability_band_low` is integrated or estimated. That tail
      is unbounded without a distributional assumption this module does not make.
    - `n_return_periods` and `status` - what the unit was given and what was done
      with it. `status` is "integrated", or:
      - "insufficient_return_periods" - fewer than two scenarios. A single sample
        trapezoid-integrates to 0.0, i.e. "nobody is ever exposed", which is the
        most dangerous possible answer to "we only ran one return period". The
        figure is NaN instead.
      - "missing_exposure" - at least one scenario has no measured `exposed_pop`
        (see `exposed_population`: a unit the hazard layer does not cover). The
        figure is NaN, as before, but now it says why. Integrating the remaining
        scenarios would be worse: it would narrow the band silently and present
        the result as if the full set had been used.

    Proper EAD integrates a damage curve over the full probability range, not
    three sampled return periods, and the trapezoid between two samples assumes
    exposure ramps linearly in probability between them. Say so in the brief.
    """
    import pandas as pd

    ordered = table.sort_values("annual_probability")
    rows = []
    for unit, group in ordered.groupby(key, sort=False):
        # Trapezoidal integration of exposure against annual probability.
        probability = group["annual_probability"].to_numpy(dtype="float64")
        # dtype float64 so a None exposed_pop becomes NaN and is caught below
        # rather than raising deep inside np.trapezoid.
        exposure = group["exposed_pop"].to_numpy(dtype="float64")
        row = {
            key: unit,
            "n_return_periods": int(len(probability)),
            "expected_annual_exposure": float("nan"),
            "frequent_tail_exposure": float("nan"),
            "expected_annual_exposure_closed": float("nan"),
            "probability_band_low": float("nan"),
            "probability_band_high": float("nan"),
            "status": "integrated",
        }
        if np.isnan(exposure).any():
            row["status"] = "missing_exposure"
        elif len(probability) < 2:
            row["status"] = "insufficient_return_periods"
        else:
            row["probability_band_low"] = float(probability[0])
            row["probability_band_high"] = float(probability[-1])
            row["expected_annual_exposure"] = float(np.trapezoid(exposure, probability))
            # One trapezoid from the most frequent sampled event down to zero
            # exposure at p = 1. `max(..., 0.0)` in case a caller hands in a
            # scenario with p >= 1, which has no tail left to close.
            row["frequent_tail_exposure"] = float(
                0.5 * exposure[-1] * max(CERTAIN_PROBABILITY - probability[-1], 0.0)
            )
            row["expected_annual_exposure_closed"] = (
                row["expected_annual_exposure"] + row["frequent_tail_exposure"]
            )
        rows.append(row)
    return pd.DataFrame(rows)
