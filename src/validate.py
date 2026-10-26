"""Scoring the MODELLED hazard maps against OBSERVED flood extent, per unit.

This is the project's credibility result, and it is deliberately unflattering: it
measures how much of the July 2021 flood the JRC hazard layer actually contains,
in front of the people who publish that layer. The output sentence is
`headline()`: *the modelled 100-year hazard layer captures X% of what was
actually flooded in July 2021.*

Three metrics on a confusion matrix over two boolean masks:

    hit rate (probability of detection)  TP / (TP + FN)   share of real flooding caught
    false alarm ratio                    FP / (TP + FP)   share of the map that stayed dry
    IoU (critical success index)         TP / (TP+FP+FN)  overall overlap, 0..1

Every one of them is **None when its denominator is zero**, never 0.0. "We could
not measure" and "the score is zero" are different statements, and collapsing
them is the error the whole kit is built to avoid - the same rule as
`events.EventSignal.unavailable` and `losses._parent_coverage_ratio`. In the
per-unit frame the undefined ratio is NaN, pandas' own missing marker, which is
likewise not 0.0; the scalar API returns None.

Four properties of the real data each turn a careless comparison into a plausible
wrong number, so each is handled by the shape of the code and not only by a
warning. All four are recorded in `config/sources.yaml`.

**1. Four CRSs, one grid.** The hazard maps are EPSG:4326 at 3 arc-seconds, the
observed depth maps are Equi7Grid Europe (azimuthal equidistant, user-defined, no
EPSG code), the Walloon layers are EPSG:31370, and the kit works in EPSG:3035.
Everything is resampled onto **EPSG:3035 at 20 m** - `data_io.WORKING_CRS` at the
observed layer's native resolution - because:

  - these metrics are pixel counts standing in for ground area, and only an
    equal-area projection makes a pixel count proportional to area. In EPSG:4326
    a 3-arc-second cell is ~92 m north-south but ~60 m east-west at Belgian
    latitudes and the ratio moves with latitude, so counting cells there weights
    the north differently from the south. Equi7Grid is equidistant, not
    equal-area, and Belgium sits ~1,300 km from its centre (lon_0=24).
  - 20 m is the finer of the two inputs. Replicating the coarse hazard cells onto
    a finer grid adds no information but loses none either, whereas averaging the
    observed 20 m layer down to ~90 m would erase exactly the narrow urban strips
    that the 2021 flood ran through.
  - nearest neighbour everywhere. Bilinear invents intermediate depths that mean
    nothing for a yes/no mask; nearest resampling of a depth raster commutes with
    thresholding, so the result is identical to nearest-resampling the mask.

Structurally: `agreement()` refuses arrays of different shape, and the only way
to get arrays into it from files is `read_depth_on_grid()` called with one shared
`Grid`. There is no code path that compares two rasters without putting them on
one grid first.

**2. Metres against centimetres.** Hazard depth is METRES, Float32, nodata -9999.
Observed depth is CENTIMETRES, uint16, nodata 0 - and 9999 marks permanent or
seasonal water, not a 99 m flood. A comparison that skips the conversion is a
factor-100 error that returns a believable percentage. Structurally: there is no
generic threshold argument anywhere in this module. `modelled_flood_mask` takes
`min_depth_m`, `observed_flood_mask` takes `min_depth_cm`, and
`score_event`/`agreement` derive the second from the first through
`matching_threshold_cm()` unless the caller overrides it, so the two thresholds
cannot drift apart by a typo. Both values are carried on the result.

**3. An absence is weaker evidence than a presence.** Sentinel-1 sees extent
under cloud but not under dense canopy or in narrow urban streets, and a revisit
gap can miss a flash flood that drained in hours. So a "false alarm" may be a
miss by the satellite: the hit rate is a LOWER bound and the false alarm ratio an
UPPER bound. Structurally: `caveat` is a field of `Agreement`, a column of every
row of `agreement_by_unit`, and part of the `headline` sentence - the same reason
`events.blind_spots` puts a caveat in every row and `losses.total_by_unit`
repeats its coverage ratio on every row. A column survives a copy-paste into a
slide; a footnote does not.

**4. The hazard maps' two documented blind spots: river flooding only, and
basins above 150 km2 only.** So a miss is *expected* where the water came from
surface runoff - a large part of what destroyed the Vesdre valley - and a low hit
rate there is a finding about scope, not about accuracy. Structurally: pass
`runoff` (from `runoff_mask_from_classement`, the Walloon CLASSEMENT 2xx/3xx
codes) and the result splits the misses into `false_negative_in_runoff_area` and
`false_negative_outside_runoff_area` and reports
`hit_rate_outside_runoff_area` - the score over the flooding the model claims to
cover. Hazard nodata counts as *dry* and not as *excluded*, on purpose:
excluding it would make the basin-size blind spot invisible by construction,
which is the opposite of the point. It also means the hazard raster cannot say
where the model was looking: the JRC maps are sparse, nodata is simply "dry",
so "not nodata" is the wet footprint and nothing more. A model domain has to
come from an independent layer (for example the EFAS upstream-area map at
150 km2 or more) and be passed to `agreement_by_unit` as `in_model_domain`;
nothing in this module derives one from the depth raster.

**Why the arithmetic is pure numpy.** rasterio, pyogrio and rasterstats cannot
load their native libraries on the Windows machine this was written on (an
application-control policy blocks the DLLs, the same failure `toon_io` describes
for `_tiktoken.pyd`), and the rasters themselves are still downloading. So the
scoring is numpy over boolean arrays and the raster reading is a thin layer on
top that imports rasterio lazily, inside the three functions that need it. The
arithmetic is therefore testable here with hand-built arrays, the IO is
exercisable later under WSL, and `import src.validate` works either way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data_io import WORKING_CRS, sources

# Equal-area, so a pixel count is proportional to ground area - see point 1 above.
SCORING_CRS = WORKING_CRS
# The observed layer's native resolution, i.e. the finer of the two inputs.
SCORING_RESOLUTION_M = 20.0

CM_PER_M = 100.0

# Hazard maps: water depth in METRES, Float32, nodata -9999.
HAZARD_NODATA_M = -9999.0
# Observed depth maps: CENTIMETRES, uint16, nodata 0, and 9999 is permanent or
# seasonal water rather than a 99 m flood. A river is not a flood, so these cells
# are excluded from the confusion matrix entirely instead of being scored as wet.
OBSERVED_PERMANENT_WATER_CM = 9999
OBSERVED_NODATA_CM = 0
# What `score_event` tells the reprojection to treat as nodata in the observed
# layer, instead of the 0 the file declares. Read with nodata=0, every dry cell
# becomes NaN and leaves the matrix, so FP is 0 by construction. 65535 is the
# uint16 maximum, which a depth in centimetres never takes, so no real cell is
# dropped; 0 stays "dry or unseen" inside the footprint, and cells outside it
# stay NaN because the destination array starts as NaN.
OBSERVED_READ_NODATA = 65535

# "Any water at all". 0.5 m is the usual threshold for damage to buildings, and
# the difference between the two is worth showing a jury because it moves the
# headline figure with no change of data - the same argument as
# `exposure.exposed_population`.
DEFAULT_MIN_DEPTH_M = 0.0

# The observed rasters declare ProjectedCSTypeGeoKey 32767 (user-defined) with
# only an ESRI citation string, though pyproj resolves its WKT to EPSG:27704 ("WGS 84 / Equi7 Europe") and the file's own
# ProjCenter keys are the right way round (Long 24.0, Lat 53.0): the CRS has to be supplied by hand.
# config/sources.yaml records that in prose inside the entry's `caveat`, where it
# cannot be read as a field, so the string is transcribed here and the
# transcription is checked against the entry on every call - see `observed_crs`.
OBSERVED_SOURCE_ID = "jrc_observed_flood_depth"
OBSERVED_DECLARED_CRS = "Equi7Grid Europe"
OBSERVED_PROJ4 = (
    "+proj=aeqd +lat_0=53 +lon_0=24 +x_0=5837287.81977 +y_0=2121415.69617 "
    "+datum=WGS84 +units=m"
)

# Walloon CLASSEMENT: 110/120/130 = low/medium/high by OVERFLOW, 210/220/230 = by
# RUNOFF, 310/320/330 = both, and 101/201/301 = very low ("alea tres faible") for
# each. The JRC maps model river flooding only, so 2xx and 3xx are the classes a
# miss is expected in; selecting by hundreds digit includes the very-low 201/301.
RUNOFF_CLASSEMENT_HUNDREDS = (2, 3)

ABSENCE_CAVEAT = (
    "Sentinel-1 sees flood extent under cloud but not under dense canopy or in "
    "narrow urban streets, and a revisit gap can miss a flash flood that drained "
    "in hours, so an absence in the observed layer is weaker evidence than a "
    "presence: a false alarm here may be a miss by the satellite, which makes the "
    "hit rate a lower bound and the false alarm ratio an upper bound."
)
SCOPE_CAVEAT = (
    "The hazard maps model river flooding only, in basins above 150 km2, so a "
    "miss where the water came from surface runoff is a limit of scope rather "
    "than of accuracy."
)
CAVEAT = f"{ABSENCE_CAVEAT} {SCOPE_CAVEAT}"

# 25 cells is one hectare on the 20 m scoring grid. Below that, a ratio is three
# or four pixels of satellite noise with two decimal places printed after it, so
# the ratios come back undefined instead - the raw counts are reported either way.
MIN_OBSERVED_CELLS = 25


class RasterBackendUnavailable(RuntimeError):
    """rasterio could not be loaded, with the reason and the fallback in the message.

    A distinct type rather than a bare ImportError, because the caller is about to
    put a validation figure in a policy brief: a missing raster backend must stop
    the pipeline and say so, not degrade into a number measured on nothing.
    """


@dataclass(frozen=True)
class Agreement:
    """One confusion matrix between a modelled and an observed flood mask.

    Every field that is a ratio is None when its denominator is zero. The depth
    thresholds and the caveat are fields rather than documentation, so the basis
    of the number travels with the number into any table, slide or JSON dump -
    the same reason `losses.VALUE_COLUMN` is called
    `value_inter_source_average`.
    """

    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    scored_cells: int
    excluded_cells: int
    min_depth_m: float
    min_depth_cm: float
    hit_rate: float | None
    false_alarm_ratio: float | None
    iou: float | None
    caveat: str = CAVEAT

    @property
    def observed_flood_cells(self) -> int:
        """Cells observed flooded and scorable: the hit rate's denominator."""
        return self.true_positive + self.false_negative

    @property
    def modelled_flood_cells(self) -> int:
        """Cells the hazard layer calls flooded: the false alarm ratio's denominator."""
        return self.true_positive + self.false_positive


@dataclass(frozen=True)
class Grid:
    """The one grid both rasters are put on before a single pixel is compared.

    Deliberately holds plain numbers and not a rasterio `Affine`, so a `Grid` can
    be built, inspected and tested on a machine where rasterio will not load;
    `transform()` materialises the Affine only when a read actually happens.
    """

    left: float
    top: float
    width: int
    height: int
    resolution_m: float = SCORING_RESOLUTION_M
    crs: str = SCORING_CRS

    @property
    def shape(self) -> tuple[int, int]:
        """(rows, cols), i.e. the shape every mask in this module must have."""
        return (self.height, self.width)

    def transform(self):
        """The north-up affine transform, for rasterio.warp.reproject."""
        from affine import Affine

        return Affine(self.resolution_m, 0.0, self.left, 0.0, -self.resolution_m, self.top)


def observed_crs(source_id: str = OBSERVED_SOURCE_ID) -> str:
    """The proj4 string to pass for the observed depth maps, checked against sources.yaml.

    The rasters carry no usable CRS of their own (see the comment on
    `OBSERVED_PROJ4`), so this string cannot be read off the file and cannot be
    read as a field of `config/sources.yaml` either - the catalogue holds it in
    prose. It is therefore transcribed in this module, and every call verifies
    that the entry still declares the CRS the transcription belongs to. If the
    catalogue ever gains a real code, this raises instead of quietly reprojecting
    through a definition that no longer matches.
    """
    for entry in sources("geodata"):
        if entry["id"] == source_id:
            declared = str(entry.get("crs", "")).strip()
            if declared != OBSERVED_DECLARED_CRS:
                raise ValueError(
                    f"config/sources.yaml now declares crs {declared!r} for "
                    f"{source_id!r}, not {OBSERVED_DECLARED_CRS!r}. OBSERVED_PROJ4 "
                    "in src/validate.py was transcribed for the latter; check "
                    "which is right before reprojecting anything through it."
                )
            return OBSERVED_PROJ4
    raise ValueError(
        f"no {source_id!r} entry in config/sources.yaml - declare the source "
        "before scoring against it"
    )


def matching_threshold_cm(min_depth_m: float) -> float:
    """The same depth, in centimetres, for the observed layer.

    The one place in the kit where the metres/centimetres factor is written down.
    `agreement` and `score_event` call it to derive the observed threshold from
    the modelled one, so the two cannot drift apart by a typo - which is the
    factor-100 error that returns a plausible percentage.
    """
    return float(min_depth_m) * CM_PER_M


def _finite(array: np.ndarray) -> np.ndarray:
    """Where `array` holds a real value, for integer and floating rasters alike.

    A read through `read_depth_on_grid` marks everything the source did not cover
    with NaN, so the masks below have to exclude non-finite cells; hand-built
    uint16 test arrays have no NaN to exclude and `np.isfinite` on an integer
    dtype is a needless full-size temporary. Hence the dtype check.
    """
    if np.issubdtype(array.dtype, np.floating):
        return np.isfinite(array)
    return np.ones(array.shape, dtype=bool)


def modelled_flood_mask(
    depth_m: np.ndarray,
    *,
    min_depth_m: float = DEFAULT_MIN_DEPTH_M,
    nodata_m: float = HAZARD_NODATA_M,
) -> np.ndarray:
    """Hazard depth in METRES to a flooded/not-flooded mask.

    How "flooded" is measured: strictly deeper than `min_depth_m`, with the
    hazard layer's own nodata excluded first. The threshold argument carries its
    unit in its name on purpose - a bare `threshold` here is how a centimetre
    value ends up applied to metres.

    Nodata becomes *not flooded* rather than *not comparable*. That is a
    measurement decision, not a convenience: the hazard maps cover river basins
    above 150 km2 only, so observed water where the layer has nothing to say is a
    genuine miss and belongs in the denominator of the hit rate. Excluding it
    would hide the documented blind spot by construction. The same fact means
    nodata cannot be read as "outside the model domain" either: on these sparse
    maps it marks every dry cell, so a domain taken from it is this mask again.
    """
    depth = np.asarray(depth_m)
    return (depth > float(min_depth_m)) & (depth != nodata_m) & _finite(depth)


def observed_flood_mask(
    depth_cm: np.ndarray,
    *,
    min_depth_cm: float = matching_threshold_cm(DEFAULT_MIN_DEPTH_M),
    permanent_water_cm: int = OBSERVED_PERMANENT_WATER_CM,
) -> np.ndarray:
    """Observed depth in CENTIMETRES to a flooded/not-flooded mask.

    How "flooded" is measured: strictly deeper than `min_depth_cm`, excluding the
    permanent-water sentinel. Unit in the argument name, same reason as above.

    Nodata is 0 in this product, so it falls below any threshold and reads as not
    flooded - which is right, and is also exactly the asymmetry in `CAVEAT`: a 0
    is "dry or unseen" and the two cannot be told apart.
    """
    depth = np.asarray(depth_cm)
    return (
        (depth > float(min_depth_cm)) & (depth != permanent_water_cm) & _finite(depth)
    )


def observed_scorable_mask(
    depth_cm: np.ndarray, *, permanent_water_cm: int = OBSERVED_PERMANENT_WATER_CM
) -> np.ndarray:
    """Where the observed layer supports a comparison at all.

    False on the permanent/seasonal water sentinel 9999 - a river is not a flood,
    and scoring it would hand the model free true positives along every
    watercourse in the window - and false where a read found no coverage (NaN).
    Everything else is scorable, including the 0s, because treating "dry or
    unseen" as unscorable would delete the honest denominator of the hit rate.
    """
    depth = np.asarray(depth_cm)
    return (depth != permanent_water_cm) & _finite(depth)


def runoff_mask_from_classement(classement: np.ndarray) -> np.ndarray:
    """Walloon hazard classes attributed to surface RUNOFF rather than overflow.

    CLASSEMENT codes 110/120/130 are low/medium/high hazard by overflow
    (debordement), 210/220/230 by runoff (ruissellement) and 310/320/330 by both;
    101/201/301 are the very-low class ("alea tres faible") of each, and this
    selection by hundreds digit includes 201 and 301, so a figure built on it
    must say it counts tres faible.
    The JRC maps model river flooding only, so 2xx and 3xx mark the area where a
    miss is a limit of scope. Pass the result as `runoff` to `agreement_by_unit`;
    0 and any other fill value fall outside the selection and read as "not
    runoff", which is the conservative direction - it leaves a miss counted
    against the model.
    """
    codes = np.asarray(classement)
    return np.isin(codes // 100, RUNOFF_CLASSEMENT_HUNDREDS)


def _ratio(numerator: int, denominator: int) -> float | None:
    """`numerator / denominator`, or None when there is nothing to divide by.

    None and never 0.0: a zero denominator means the question could not be asked,
    and a 0.0 in its place is a claim that the model caught nothing.
    """
    return float(numerator) / denominator if denominator else None


def _check_shapes(**arrays: np.ndarray | None) -> tuple[int, int]:
    """Every mask must be on one grid. Returns the shared shape.

    This is the structural half of the CRS problem: two rasters in different CRSs
    reprojected onto one `Grid` have the same shape, and two rasters that were
    never aligned almost never do. Raising here is what stops a pixel-by-pixel
    comparison between layers that describe different places - a comparison that
    completes, prints and maps, and is simply about somewhere else.
    """
    shapes = {name: np.shape(a) for name, a in arrays.items() if a is not None}
    distinct = set(shapes.values())
    if len(distinct) != 1:
        raise ValueError(
            f"Masks are on different grids: {shapes}. Put both rasters on one "
            f"{SCORING_CRS} grid with read_depth_on_grid() and a single Grid "
            "before comparing a single pixel."
        )
    return distinct.pop()


def agreement(
    modelled_flooded: np.ndarray,
    observed_flooded: np.ndarray,
    *,
    scorable: np.ndarray | None = None,
    min_depth_m: float = DEFAULT_MIN_DEPTH_M,
    min_depth_cm: float | None = None,
    caveat: str = CAVEAT,
) -> Agreement:
    """The confusion matrix and the three scores, over one pair of boolean masks.

    Pure numpy, so this is the half of the module that can be tested on a machine
    with no working raster backend - and the half where a wrong number would be
    invisible, because a wrong percentage prints exactly like a right one.

    How each score is measured, over the cells `scorable` keeps:

        hit rate           TP / (TP + FN)    of the flooding actually observed,
                                             the share the hazard layer contains
        false alarm ratio  FP / (TP + FP)    of the area the hazard layer calls
                                             flooded, the share that stayed dry
        IoU                TP / (TP+FP+FN)   overlap of the two extents, 0..1

    Each is None when its denominator is zero. `scorable` is where the observed
    layer supports a comparison, normally from `observed_scorable_mask`:
    permanent water and uncovered cells are dropped from the matrix entirely
    rather than being scored as dry, because a river counted as agreement is free
    credit for the model.

    `min_depth_cm` defaults to `matching_threshold_cm(min_depth_m)` so that the
    two thresholds recorded on the result cannot disagree unless a caller says so
    explicitly. They are recorded, not assumed: nothing here re-reads the depth
    rasters, so these are the caller's claim about which masks were passed in.
    """
    modelled = np.asarray(modelled_flooded, dtype=bool)
    observed = np.asarray(observed_flooded, dtype=bool)
    _check_shapes(modelled=modelled, observed=observed, scorable=scorable)

    if scorable is None:
        keep = np.ones(modelled.shape, dtype=bool)
    else:
        keep = np.asarray(scorable, dtype=bool)

    wet_model = modelled & keep
    wet_truth = observed & keep
    true_positive = int(np.count_nonzero(wet_model & wet_truth))
    false_positive = int(np.count_nonzero(wet_model & ~wet_truth))
    false_negative = int(np.count_nonzero(~modelled & wet_truth))
    scored = int(np.count_nonzero(keep))
    true_negative = scored - true_positive - false_positive - false_negative

    return Agreement(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        true_negative=true_negative,
        scored_cells=scored,
        excluded_cells=int(keep.size - scored),
        min_depth_m=float(min_depth_m),
        min_depth_cm=(
            matching_threshold_cm(min_depth_m) if min_depth_cm is None else float(min_depth_cm)
        ),
        hit_rate=_ratio(true_positive, true_positive + false_negative),
        false_alarm_ratio=_ratio(false_positive, true_positive + false_positive),
        iou=_ratio(true_positive, true_positive + false_positive + false_negative),
        caveat=caveat,
    )


def agreement_by_unit(
    modelled_flooded: np.ndarray,
    observed_flooded: np.ndarray,
    unit_codes: np.ndarray,
    *,
    scorable: np.ndarray | None = None,
    runoff: np.ndarray | None = None,
    in_model_domain: np.ndarray | None = None,
    code_column: str = "NUTS_ID",
    background=0,
    min_depth_m: float = DEFAULT_MIN_DEPTH_M,
    min_depth_cm: float | None = None,
    min_observed_cells: int = MIN_OBSERVED_CELLS,
    caveat: str = CAVEAT,
) -> pd.DataFrame:
    """The same three scores per administrative unit, one row each.

    The brief asks which regions the model misses, and one European number cannot
    answer that. `unit_codes` is the administrative layer rasterised onto the same
    grid as the masks - one code per cell, `background` where no unit covers the
    cell. `background` has to match the type of the fill actually used: numpy
    compares a string code array against the default 0 as unequal everywhere, so
    a layer rasterised with an empty-string fill needs `background=""` or the
    uncovered cells become a unit of their own named "".
    `code_column` names the output column so the frame merges straight onto
    `gisco_nuts3` (`NUTS_ID`, NUTS 2024) or onto Belgian communes (`GISCO_ID`,
    or `CD_REFNIS` for the Statbel vintage) without a lookup. Pin the vintage:
    NUTS 2021 and NUTS 2024 are different geometries AND different codes.

    **Can two units be compared?** The scores are ratios within a unit, so they
    carry no unit-size term and a small commune and a large province are on the
    same 0..1 scale. Their *precision* is not comparable: the hit rate's
    denominator is the observed flooded area, which spans orders of magnitude
    across units, so 1.00 over 30 flooded cells and 0.62 over 400,000 are not the
    same kind of statement. Hence `observed_flood_cells` on every row, and
    `min_observed_cells` (default 25, one hectare at 20 m) below which the ratios
    come back NaN instead of a figure measured on satellite noise. Rank units by
    score only among those that clear it, and never read an undefined ratio as a
    zero.

    Optional columns, each of which exists so a limit of the data shows up as a
    number in the table rather than as a sentence underneath it:

    - `runoff`: cells attributed to surface runoff, from
      `runoff_mask_from_classement`. Splits the misses into
      `false_negative_in_runoff_area` / `..._outside_runoff_area` and adds
      `hit_rate_outside_runoff_area`, measured over the overflow-attributed area
      only - the flooding the hazard maps claim to model. A unit whose overall hit
      rate is poor and whose outside-runoff hit rate is good is a scope finding,
      not an accuracy finding, and that is the distinction the brief needs.
    - `in_model_domain`: where the hazard model claims to look, from a layer
      independent of the hazard depths - for instance the EFAS upstream-area
      map thresholded at 150 km2 and put on the same grid. Adds
      `modelled_outside_domain_cells`, i.e. how much of the unit lies outside
      that domain - the basins-above-150-km2 blind spot, per region. Never
      build it from the hazard raster's nodata: the JRC maps write nodata for
      every dry cell, so that "domain" is the wet footprint and would report
      every dry cell as never modelled.

    `caveat` is repeated on every row for the reason given in the module
    docstring: a column survives the copy-paste into a slide that drops a
    footnote.
    """
    modelled = np.asarray(modelled_flooded, dtype=bool)
    observed = np.asarray(observed_flooded, dtype=bool)
    codes = np.asarray(unit_codes)
    _check_shapes(
        modelled=modelled,
        observed=observed,
        unit_codes=codes,
        scorable=scorable,
        runoff=runoff,
        in_model_domain=in_model_domain,
    )

    keep = codes != background
    if scorable is not None:
        keep = keep & np.asarray(scorable, dtype=bool)

    labels, units = pd.factorize(codes[keep])
    n = len(units)
    if n == 0:
        raise ValueError(
            "No cell belongs to any administrative unit and is scorable at the "
            f"same time (background={background!r}). Raising rather than returning "
            "an empty frame: an empty frame of scores reads as a model that caught "
            "nothing, when the real problem is that the unit raster and the masks "
            "are not on the same grid or the codes are not the ones expected."
        )
    wet_model = modelled[keep]
    wet_truth = observed[keep]

    def per_unit(selection: np.ndarray) -> np.ndarray:
        """Cells per unit satisfying `selection`, aligned to `units`."""
        return np.bincount(labels[selection], minlength=n)

    true_positive = per_unit(wet_model & wet_truth)
    false_positive = per_unit(wet_model & ~wet_truth)
    false_negative = per_unit(~wet_model & wet_truth)
    scored = per_unit(np.ones(labels.shape, dtype=bool))

    out = pd.DataFrame(
        {
            code_column: units,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "scored_cells": scored,
        }
    )
    out["observed_flood_cells"] = true_positive + false_negative
    out["modelled_flood_cells"] = true_positive + false_positive
    out["hit_rate"] = _ratio_column(true_positive, true_positive + false_negative)
    out["false_alarm_ratio"] = _ratio_column(
        false_positive, true_positive + false_positive
    )
    out["iou"] = _ratio_column(
        true_positive, true_positive + false_positive + false_negative
    )

    if runoff is not None:
        is_runoff = np.asarray(runoff, dtype=bool)[keep]
        fn_in = per_unit(~wet_model & wet_truth & is_runoff)
        tp_out = per_unit(wet_model & wet_truth & ~is_runoff)
        fn_out = per_unit(~wet_model & wet_truth & ~is_runoff)
        out["false_negative_in_runoff_area"] = fn_in
        out["false_negative_outside_runoff_area"] = fn_out
        # Both terms restricted to the overflow-attributed area, so this is the
        # score over what the model is for - not the overall score with the
        # inconvenient misses dropped from one side of the fraction only.
        out["hit_rate_outside_runoff_area"] = _ratio_column(tp_out, tp_out + fn_out)

    if in_model_domain is not None:
        inside = np.asarray(in_model_domain, dtype=bool)[keep]
        out["modelled_outside_domain_cells"] = scored - per_unit(inside)

    # Too few observed cells to divide by: see the docstring. The counts stay, so
    # a reader can see exactly how thin the evidence was.
    thin = out["observed_flood_cells"] < min_observed_cells
    for column in out.columns:
        if column.startswith(("hit_rate", "false_alarm_ratio", "iou")):
            out.loc[thin, column] = np.nan

    out["min_depth_m"] = float(min_depth_m)
    out["min_depth_cm"] = (
        matching_threshold_cm(min_depth_m) if min_depth_cm is None else float(min_depth_cm)
    )
    out["min_observed_cells"] = int(min_observed_cells)
    out["caveat"] = caveat
    return out.sort_values(
        "observed_flood_cells", ascending=False, ignore_index=True
    )


def _ratio_column(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Element-wise ratio, NaN where the denominator is zero.

    NaN rather than 0.0, for the reason given throughout this module. It is
    pandas' own missing marker, so it survives a merge, a CSV round-trip and a
    `.mean()` as "no value" instead of being averaged in as a nought.
    """
    numerator = np.asarray(numerator, dtype="float64")
    denominator = np.asarray(denominator, dtype="float64")
    return np.divide(
        numerator,
        denominator,
        out=np.full(numerator.shape, np.nan),
        where=denominator > 0,
    )


def headline(
    scores: Agreement, *, return_period_years: int, event: str = "July 2021"
) -> str:
    """The sentence this module exists to produce, with its caveat attached.

    *The modelled 100-year hazard layer captures X% of what was actually flooded
    in July 2021.* When the hit rate is undefined the sentence says it could not
    be measured and gives the reason - it does not say 0%, which would be a
    finding rather than a gap.
    """
    if scores.hit_rate is None:
        return (
            f"The modelled {return_period_years}-year hazard layer could not be "
            f"scored against {event}: no scorable observed flooding in the compared "
            f"area ({scores.scored_cells:,} cells scored, "
            f"{scores.excluded_cells:,} excluded as permanent water or uncovered). "
            f"{scores.caveat}"
        )
    pieces = [
        f"The modelled {return_period_years}-year hazard layer captures "
        f"{scores.hit_rate * 100:.0f}% of what was actually flooded in {event}",
        f"measured above {scores.min_depth_m:g} m modelled depth and "
        f"{scores.min_depth_cm:g} cm observed depth",
        f"over {scores.scored_cells:,} cells on a {SCORING_RESOLUTION_M:g} m "
        f"{SCORING_CRS} grid",
    ]
    if scores.false_alarm_ratio is not None:
        pieces.append(f"false alarm ratio {scores.false_alarm_ratio:.2f}")
    if scores.iou is not None:
        pieces.append(f"IoU {scores.iou:.2f}")
    return f"{', '.join(pieces)}. {scores.caveat}"


# ---------------------------------------------------------------------------
# Raster IO. rasterio is imported inside each function below, never at module
# scope: it is this module's only compiled dependency, exactly three functions
# need it, and on a machine whose application-control policy blocks its DLLs a
# module-scope import would take the whole scoring layer - and the test suite -
# down with it over a file nobody has opened yet. Same reasoning as `toon_io`.
# ---------------------------------------------------------------------------


def _require_rasterio():
    """The rasterio module, or a refusal naming the WSL fallback.

    Raises `RasterBackendUnavailable` rather than letting an ImportError surface,
    so the message can say what to do about it instead of naming a DLL.
    """
    try:
        import rasterio

        return rasterio
    except Exception as exc:  # compiled extension blocked, or GDAL not on PATH
        raise RasterBackendUnavailable(
            f"rasterio could not be loaded ({exc}). On this Windows machine the "
            "application-control policy blocks the GDAL DLLs behind rasterio, "
            "pyogrio and rasterstats, so the raster half of this module cannot "
            "run here. Run it under WSL instead: python3 -m venv .venv && "
            ".venv/bin/pip install -r requirements.txt, then "
            ".venv/bin/python -m pytest -q. The pure-numpy scoring in this module "
            "(agreement, agreement_by_unit) needs none of this and works either "
            "way."
        ) from exc


def scoring_grid(
    rasters: list[tuple[str, str | None]], *, resolution_m: float = SCORING_RESOLUTION_M
) -> Grid:
    """The common grid for a list of (path, declared_crs) pairs.

    The intersection of every footprint, in EPSG:3035 at 20 m, snapped to whole
    cells. Why this grid and not either input's own: see point 1 of the module
    docstring - these metrics are pixel counts standing in for ground area, and
    EPSG:3035 is the only one of the four CRSs involved that is equal-area.

    The intersection, not the union: a cell no raster covers is not a true
    negative, it is a cell nobody looked at, and padding the grid with those
    would inflate the one count in the matrix nothing else depends on.

    `declared_crs` overrides what the file says, which is not optional for the
    observed depth maps - they declare a user-defined CRS and their own
    projection-centre keys are the right way round, so pass `observed_crs()`.
    """
    rio = _require_rasterio()
    from rasterio.warp import transform_bounds

    lefts, bottoms, rights, tops = [], [], [], []
    for path, declared in rasters:
        with rio.open(path) as src:
            crs = declared or src.crs
            if crs is None:
                raise ValueError(
                    f"{path} declares no CRS and none was passed. Find out what it "
                    "is - do not assume 4326."
                )
            # densify_pts: the footprint edge is a curve in the target CRS, so a
            # four-corner transform clips the bounds. 21 points per edge is
            # rasterio's own default for this reason.
            left, bottom, right, top = transform_bounds(
                crs, SCORING_CRS, *src.bounds, densify_pts=21
            )
        lefts.append(left)
        bottoms.append(bottom)
        rights.append(right)
        tops.append(top)

    left = math.floor(max(lefts) / resolution_m) * resolution_m
    bottom = math.floor(max(bottoms) / resolution_m) * resolution_m
    right = math.ceil(min(rights) / resolution_m) * resolution_m
    top = math.ceil(min(tops) / resolution_m) * resolution_m
    if right <= left or top <= bottom:
        raise ValueError(
            "The rasters' footprints do not overlap in "
            f"{SCORING_CRS}: x {left}..{right}, y {bottom}..{top}. An empty "
            "intersection scores 0 cells, which reads as a model that caught "
            "nothing rather than as two layers describing different places."
        )
    return Grid(
        left=left,
        top=top,
        width=int(round((right - left) / resolution_m)),
        height=int(round((top - bottom) / resolution_m)),
        resolution_m=resolution_m,
    )


def read_depth_on_grid(
    path: str,
    grid: Grid,
    *,
    declared_crs: str | None = None,
    nodata: float | None = None,
) -> np.ndarray:
    """Band 1 of `path` resampled onto `grid`, as float32 with nodata as NaN.

    **Nearest neighbour, always.** Bilinear would average the depths of adjacent
    cells and invent values that no model produced and no satellite saw, which is
    meaningless for a yes/no flooded mask. Nearest resampling of a depth raster
    also commutes with thresholding, so this is exactly equivalent to
    nearest-resampling the boolean mask - and reading the depth lets the
    threshold still be chosen afterwards.

    Nodata, and anything outside the source footprint, comes back NaN rather than
    0: a 0 would be a depth, and in the observed layer 0 is already the code for
    "dry or unseen". The mask builders in this module treat NaN as not flooded and
    `observed_scorable_mask` drops it from the matrix.

    The returned array is in whatever unit the file uses - METRES for the hazard
    maps, CENTIMETRES for the observed ones. Nothing is converted here; the
    conversion lives in `matching_threshold_cm` and is applied to the threshold,
    not to the raster, so a 45,000 x 60,000 uint16 raster is never multiplied
    cell by cell for no reason.
    """
    rio = _require_rasterio()
    from rasterio.warp import Resampling, reproject

    with rio.open(path) as src:
        crs = declared_crs or src.crs
        if crs is None:
            raise ValueError(
                f"{path} declares no CRS and none was passed. Find out what it is "
                "- do not assume 4326."
            )
        destination = np.full(grid.shape, np.nan, dtype="float32")
        reproject(
            source=rio.band(src, 1),
            destination=destination,
            src_crs=crs,
            src_transform=src.transform,
            src_nodata=src.nodata if nodata is None else nodata,
            dst_crs=grid.crs,
            dst_transform=grid.transform(),
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
    return destination


def score_event(
    modelled_path: str,
    observed_path: str,
    *,
    min_depth_m: float = DEFAULT_MIN_DEPTH_M,
    min_depth_cm: float | None = None,
    modelled_crs: str | None = None,
    observed_declared_crs: str | None = None,
    exclude_paths: tuple[str, ...] = (),
    resolution_m: float = SCORING_RESOLUTION_M,
) -> tuple[Agreement, dict[str, np.ndarray]]:
    """Score one hazard return period against one observed event, end to end.

    The one-call path, and the reason the CRS harmonisation cannot be skipped:
    both rasters are read through a single `Grid` built by `scoring_grid`, so
    there is no argument order that compares EPSG:4326 cells with Equi7Grid
    cells. `observed_declared_crs` defaults to `observed_crs()` because the
    observed files cannot supply their own.

    The observed file's declared nodata of 0 is deliberately overridden with
    `OBSERVED_READ_NODATA`. In that layer 0 means "dry or unseen": a Sentinel-1
    pass that saw no water, which is weak evidence of dryness (vegetation,
    buildings and timing all hide water from radar) but still the denominator
    of the false alarm ratio. Honouring nodata=0 would drop every such cell, so
    no modelled-wet cell could ever be scored as a false alarm, FAR would read
    0 and IoU would equal the hit rate. Cells outside the observed footprint
    still come back NaN and unscored, and 9999 is still excluded as permanent
    water.

    `min_depth_cm` defaults to `matching_threshold_cm(min_depth_m)`, so one
    threshold is given once and applied in both units. That default is the whole
    defence against the factor-100 error: the metres value never reaches the
    centimetre raster and the centimetre value never reaches the metres raster.

    `exclude_paths` are extra masks dropped from the confusion matrix wherever
    they are non-zero, on top of the observed layer's own permanent-water
    sentinel: pass `Europe_permanent_water_bodies.tif` (a river is not a flood)
    and `Europe_spurious_depth_areas.tif`, which the JRC README says flags
    predicted depths over 10 m in small channels and asks to be treated with
    caution.

    Returns the `Agreement` and the masks it was computed from
    (`modelled_flooded`, `observed_flooded`, `scorable`), so the per-unit
    breakdown can be taken with `agreement_by_unit` without reading 2.6 GiB of
    raster twice. No model-domain mask is among them: the hazard raster cannot
    supply one (see point 4 of the module docstring).
    """
    observed_declared_crs = (
        observed_crs() if observed_declared_crs is None else observed_declared_crs
    )
    grid = scoring_grid(
        [(modelled_path, modelled_crs), (observed_path, observed_declared_crs)],
        resolution_m=resolution_m,
    )
    modelled_depth_m = read_depth_on_grid(modelled_path, grid, declared_crs=modelled_crs)
    observed_depth_cm = read_depth_on_grid(
        observed_path,
        grid,
        declared_crs=observed_declared_crs,
        nodata=OBSERVED_READ_NODATA,
    )

    threshold_cm = (
        matching_threshold_cm(min_depth_m) if min_depth_cm is None else min_depth_cm
    )
    masks = {
        "modelled_flooded": modelled_flood_mask(modelled_depth_m, min_depth_m=min_depth_m),
        "observed_flooded": observed_flood_mask(
            observed_depth_cm, min_depth_cm=threshold_cm
        ),
        "scorable": observed_scorable_mask(observed_depth_cm),
    }
    for extra in exclude_paths:
        values = read_depth_on_grid(extra, grid)
        masks["scorable"] = masks["scorable"] & ~(np.nan_to_num(values) != 0)

    scores = agreement(
        masks["modelled_flooded"],
        masks["observed_flooded"],
        scorable=masks["scorable"],
        min_depth_m=min_depth_m,
        min_depth_cm=threshold_cm,
    )
    return scores, masks
