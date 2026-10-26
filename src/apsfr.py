"""Areas of Potential Significant Flood Risk, as the Member States declared them.

**Why this layer and not another hazard map.** Everything else in this kit
measures what the water does. This measures what a government *said* about it:
under Article 5 of the Floods Directive, each Member State designates the areas
where a significant flood risk exists, and reports them to the Commission. The
kit already carries the Directive's text in the RAG corpus; this is the reporting
data behind it.

Crossed with the modelled hazard and the exposure figures, it turns a map into a
question a policy jury can act on: **where does modelled risk fall outside the
area the State itself declared?** That is a compliance gap, not a colour ramp,
and it is the one sentence this dataset exists to let a brief write.

What it is NOT: evidence that an undeclared area is wrongly undeclared. A State
may have assessed an area under Article 4 and concluded the risk is not
significant, which is a decision the Directive allows. The defensible claim is
"the modelled exposure here sits outside the declared area", with the figure
beside it, and the conclusion left to a human.

**The declared AREA is not comparable between Member States.** `apsfr_share` is
a defensible figure *within* one country and a trap across two, because the
Directive sets what must be designated and leaves the geometry convention
national. Measured 2026-10-08 on the 2018 cycle: the share of national territory
declared runs from 99.908% (BE, essentially one polygon over the whole country)
to 0.004% (ES, CY), a factor of 23,095. The shape index - perimeter over that of
an equal-area circle - separates the two conventions: 1.5 for Belgium and 1.5 for
Croatia against 51 for Germany and 74 for Luxembourg, which is a river reach
reported as a ribbon rather than a zone. Germany's 648 polygons total 76 km2;
Belgium's 28 total 30,695 km2. So rank `apsfr_declared` across countries if you
must, never `apsfr_share`, and say which convention a national figure follows.

**Two further traps, both measured 2026-10-07 on the live service.**

*The layer carries two reporting cycles.* `cYear` is 2010 for 496 polygons across
5 countries and 2018 for 12,173 across 25. AT, DE, ES and FR appear in BOTH, so a
query that does not pin the cycle overlays two declarations of the same ground and
an area share can exceed 1. `LATEST_CYCLE` is the default, and `cycles()` is there
because the trade-off is real: Lithuania reported in 2010 and not in 2018, so
pinning the current cycle drops it entirely rather than showing a stale figure as
if it were current.

*The geometries are too detailed to fetch whole, and generalising too hard
destroys them.* Ungeneralised, the service answers 50 polygons in 18.7 MB and
refuses any query carrying the `cYear` filter with HTTP 500. But these are small
features - the median polygon is about 0.001 km2 - so a coarse tolerance does not
simplify them, it deletes them: at 110 m, 44% of the Italian polygons collapse to
zero width, and Germany, Spain and France come back having apparently declared
nothing. `MAX_ALLOWABLE_OFFSET` carries the measured table.

*The service publishes in Web Mercator.* EPSG:3857 inflates area by roughly
1/cos squared of the latitude - about 2.4x at 50 degrees North, and unevenly
between Crete and Lapland, so even a RATIO of two Mercator areas taken at
different latitudes is wrong. Every area here is computed in EPSG:3035, like the
rest of the kit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests

from src.basins import repair
from src.data_io import DATA, WORKING_CRS

CACHE_DIR = DATA / "processed" / "apsfr_cache"

SERVICE = (
    "https://water.discomap.eea.europa.eu/arcgis/rest/services/FloodsDirective/"
    "FloodsDirective_AreasOfPotentialSignificantFloodRisk_WM/MapServer/3/query"
)

#: The current reporting cycle in this layer. See the module docstring: pinning
#: it is what stops two declarations of the same ground being overlaid.
LATEST_CYCLE = "2018"

TIMEOUT_S = 180

#: Server-side generalisation, in the units of `outSR` - so degrees, and 0.0001
#: is about 11 m at these latitudes.
#:
#: Not a nicety: without it this service refuses any query carrying the `cYear`
#: filter with HTTP 500 (and, under `f=json`, a 200 whose body is a 500), which
#: is a server-side timeout on geometry volume rather than a rejection of the
#: query. Ungeneralised it answers 50 polygons in 18.7 MB, so the current cycle
#: would be some 4.5 GB.
#:
#: The VALUE is measured, not chosen for round numbers. These are small features:
#: the median polygon is about 0.001 km2, a hundred metres across, and several
#: countries report narrow river corridors. Tested on Italy, the largest
#: contributor, 300 polygons per tolerance, 2026-10-07:
#:
#:     tolerance        payload   survive a structure repair   median area
#:     0.001  (~110 m)  1.35 MB   169 of 300                   0.0008 km2
#:     0.0001 (~11 m)   5.51 MB   300 of 300                   0.0010 km2
#:     0.00002 (~2 m)   15.7 MB   300 of 300                   0.0011 km2
#:     none             HTTP 500  -                            -
#:
#: At 110 m, 44% of the layer collapses to zero width and is dropped - which
#: would have reported Germany, Spain and France as having declared nothing at
#: all. At 11 m nothing is lost and the median area is within 10% of the
#: near-exact value. The whole cycle is then about 224 MB, roughly 15 minutes,
#: once, and the cache answers afterwards.
MAX_ALLOWABLE_OFFSET = 0.0001

#: 300 generalised polygons come back in 5.5 MB in about 22 s, well inside the
#: timeout. The current cycle is then about 41 pages.
PAGE_SIZE = 300
MAX_PAGES = 200

#: There is deliberately NO vertex-thinning knob here, and that is a measured
#: decision rather than an omission.
#:
#: Thinning the repaired polygons with `simplify(25 m, preserve_topology=True)`
#: before the overlay looks obviously right - the overlay against 1,345 regions
#: should be dominated by vertex count, and 25 m against regions kilometres
#: across should be free. Measured end to end on the real layer, 2026-10-07, it
#: is wrong twice over:
#:
#:     exact geometry      1,071 s
#:     thinned at 25 m     4,683 s     <- 4.4x SLOWER
#:
#: and the shares move: a maximum deviation of 0.004 with 44 of 1,147 regions
#: past 0.001, against a prediction of a fourth-decimal effect. `simplify` on
#: 12,173 detailed polygons costs more than the overlay it was meant to cheapen,
#: and it can re-introduce self-intersections into geometry that was just
#: repaired, which makes the overlay slower still.
#:
#: So the overlay runs on the exact geometry and takes about eighteen minutes,
#: once, for a frozen table. Do not re-add this without measuring it end to end.

#: Requested by name rather than `outFields=*`: the sibling WFD layer carries an
#: attribute called `geometry` beside its real geometry and answers HTTP 500 when
#: asked for every field in GeoJSON. These four are what a brief needs - the
#: reporting country, the cycle, the APSFR's own identifier and the unit of
#: management it belongs to.
OUT_FIELDS = ("countryCode", "cYear", "inspireIdLocalId", "relatedZoneIdentifier")


class ApsfrUnavailable(RuntimeError):
    """The service did not answer with data.

    Raised rather than returning an empty frame: an empty APSFR layer makes every
    region look undeclared, which is the strongest claim this module can make and
    exactly the one it must never make by accident.
    """


def _cache_path(cycle: str) -> Path:
    """GeoParquet, not GeoJSON.

    The layer is 12,173 polygons at this tolerance and some single features are
    enormous: written as GeoJSON the cache is 253 MB and GDAL then refuses to
    read it back - "GeoJSON object too complex/large", which needs
    `OGR_GEOJSON_MAX_OBJ_SIZE` raised just to reopen a file this code wrote.
    GeoParquet has no such limit, round-trips the geometry exactly, and is the
    format the rest of the kit already freezes tables in.
    """
    return CACHE_DIR / f"apsfr_polygons_{cycle}.parquet"


def _page(offset: int, cycle: str) -> dict[str, Any]:
    """One page of the polygon layer as GeoJSON, in degrees."""
    params = {
        "where": f"cYear='{cycle}'",
        "outFields": ",".join(OUT_FIELDS),
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        # Degrees: `declared_by_region` reprojects to EPSG:3035 itself, and asking
        # the service for a projected CRS it may or may not honour is a way to get
        # silently reprojected data.
        "outSR": 4326,
        # See MAX_ALLOWABLE_OFFSET: without it this query is HTTP 500.
        "maxAllowableOffset": MAX_ALLOWABLE_OFFSET,
    }
    try:
        response = requests.get(SERVICE, params=params, timeout=TIMEOUT_S)
    except Exception as exc:  # network, DNS, timeout
        raise ApsfrUnavailable(f"APSFR page at offset {offset}: {exc}") from exc
    if response.status_code >= 400:
        raise ApsfrUnavailable(f"APSFR: HTTP {response.status_code} at offset {offset}")
    try:
        return response.json()
    except ValueError as exc:
        raise ApsfrUnavailable("APSFR: response was not JSON") from exc


def polygons(
    *, cycle: str = LATEST_CYCLE, use_cache: bool = True
) -> gpd.GeoDataFrame:
    """Every declared APSFR polygon for one reporting cycle, from cache when there is one.

    One cycle, never a mix: see the module docstring for what overlaying 2010 on
    2018 does to an area share.
    """
    cache = _cache_path(cycle)
    if use_cache and cache.exists():
        return gpd.read_parquet(cache)

    features: list[dict] = []
    for page in range(MAX_PAGES):
        payload = _page(page * PAGE_SIZE, cycle)
        batch = payload.get("features", [])
        features.extend(batch)
        if not batch or not payload.get("properties", {}).get("exceededTransferLimit"):
            break
    else:
        raise ApsfrUnavailable(
            f"APSFR: still paging after {MAX_PAGES} pages; the service is not "
            "terminating and a truncated layer would understate every declaration."
        )

    if not features:
        raise ApsfrUnavailable(
            f"APSFR: cycle {cycle!r} returned no polygons. An empty layer would "
            "report every region as undeclared."
        )

    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(cache)
    return frame


def cycles(*, use_cache: bool = True) -> pd.DataFrame:
    """Which countries reported in which cycle, so a gap can be told from a silence.

    A country absent from `LATEST_CYCLE` has not necessarily stopped designating
    areas - measured 2026-10-07, Lithuania appears in the 2010 cycle of this
    service and not in the 2018 one. Reporting "LT declared nothing" off the
    current cycle alone would be false, so the brief needs this table beside the
    shares.
    """
    rows = []
    for cycle in ("2010", LATEST_CYCLE):
        try:
            frame = polygons(cycle=cycle, use_cache=use_cache)
        except ApsfrUnavailable:
            continue
        for country, count in frame["countryCode"].value_counts().items():
            rows.append({"country": country, "cycle": cycle, "polygons": int(count)})
    return pd.DataFrame(rows).sort_values(["country", "cycle"]).reset_index(drop=True)


def declared_by_region(
    admin: gpd.GeoDataFrame,
    *,
    cycle: str = LATEST_CYCLE,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Per region: how much of it the State declared at risk, and whether it declared any.

    Returns, indexed like `admin`:

    - `apsfr_share` - the share of the region's area inside a declared APSFR, in
      [0, 1]. The area of the UNION of the polygons touching the region, not the
      sum of their areas: APSFRs under different units of management overlap, and
      summing them puts a share above 1 on the Rhine delta.
    - `apsfr_declared` - whether the region intersects any APSFR at all. The
      column a brief actually quotes, because "this region has people exposed and
      no declared area" is a sentence and "0.03" is not.
    - `apsfr_cycle` - the reporting cycle the figure comes from, as TEXT. It is a
      vintage like NUTS, it has to travel with the number, and text cannot drift
      into the vulnerability index the way a number would.

    - `apsfr_country_reported` - whether this region's country appears in the
      layer at all. Present only when `admin` carries a `country` column, and the
      column that stops a false accusation: the layer holds 26 country codes
      across both cycles and Ireland is not among them, so an Irish region reads
      as "not declared" for a reason that has nothing to do with Ireland. Where
      this is False, `apsfr_share` is NaN rather than 0.0, because nothing was
      measured.

    Where the country IS covered, a region intersecting no polygon gets
    `apsfr_share` 0.0 and `apsfr_declared` False, and there the zero is a
    measurement: the layer reaches that country and the region sits outside every
    designated area.

    Note that a region can intersect a NEIGHBOUR's declared area - rivers are
    shared - so a country absent from the current cycle can still show declared
    regions along its borders. That is geometrically honest and worth saying in a
    caption.
    """
    declared = polygons(cycle=cycle, use_cache=use_cache)

    left = repair(admin.to_crs(WORKING_CRS), "the admin frame")
    # `method="structure"` rather than the default linework repair: generalising
    # at MAX_ALLOWABLE_OFFSET leaves 5,909 of the 12,173 polygons self-
    # intersecting, and the linework repair turns some of those into geometry
    # collections mixing lines with polygons, which the next overlay rejects
    # outright ("Overlay input is mixed-dimension"). The structure method returns
    # polygonal output for polygonal input, and `keep_collapsed=False` drops the
    # slivers that generalisation flattened to zero width rather than carrying
    # them as lines of no area.
    right = repair(
        declared.to_crs(WORKING_CRS),
        f"the APSFR polygons ({cycle})",
        method="structure",
    )
    right = right[~right.geometry.is_empty & right.geometry.notna()]

    # Overlay, then dissolve - NOT a global union of 12,173 detailed polygons,
    # which is the obvious implementation and does not finish: the pairwise work
    # is unbounded, while the overlay is spatially indexed and the dissolve only
    # unions the handful of pieces that landed in one region.
    #
    # Dissolve rather than sum: APSFRs reported under different units of
    # management overlap, so adding the piece areas counts the overlap once per
    # polygon and puts a share above 1 on a delta.
    pieces = gpd.overlay(
        left[["geometry"]].assign(_region=range(len(left))),
        right[["geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    if pieces.empty:
        covered = pd.Series(0.0, index=range(len(left)))
    else:
        covered = pieces.dissolve(by="_region").geometry.area

    region_area = pd.Series(left.geometry.area.to_numpy())
    share = covered.reindex(range(len(left))).fillna(0.0).to_numpy()

    out = pd.DataFrame(index=admin.index)
    out["apsfr_share"] = (share / region_area.where(region_area > 0).to_numpy())
    out["apsfr_share"] = out["apsfr_share"].fillna(0.0)
    # A share cannot exceed 1. Five regions came back at 1 + 1e-7 on the real
    # layer: the admin frame is repaired before its area is taken and the overlay
    # inputs are repaired too, so the two areas differ in the last bits. Clamped
    # rather than left to print as 100.00001%, and the tolerance is tight enough
    # that a structural overcount - which is what a sum instead of a dissolve
    # would produce - still shows up as a share far above 1 and is not hidden.
    exceeded = out["apsfr_share"] > 1.0 + 1e-6
    if exceeded.any():
        raise ValueError(
            f"{int(exceeded.sum())} regions have a declared share above 1 "
            f"(max {out['apsfr_share'].max():.4f}). That is not float noise: the "
            "overlapping designations were summed somewhere instead of dissolved."
        )
    out["apsfr_share"] = out["apsfr_share"].clip(upper=1.0)
    out["apsfr_declared"] = out["apsfr_share"] > 0
    out["apsfr_cycle"] = cycle

    # The column that stops a false accusation.
    #
    # The layer does not cover every Member State. Measured 2026-10-07 against
    # the service: it holds 26 country codes across BOTH cycles, and IRELAND is
    # not one of them - zero polygons, for a State that certainly designates
    # areas under Article 5. So `apsfr_declared == False` has two completely
    # different causes, and only one of them is about the State: either it
    # designated nothing here, or this dataset never carried its reporting.
    # Without this column a brief would read the second as the first.
    if "country" in admin.columns:
        reported = set(declared["countryCode"].dropna().unique())
        out["apsfr_country_reported"] = admin["country"].isin(reported).to_numpy()
        # Not measured is not zero: an uncovered country has no share at all.
        out.loc[~out["apsfr_country_reported"], "apsfr_share"] = float("nan")
        out.loc[~out["apsfr_country_reported"], "apsfr_declared"] = False
    return out
