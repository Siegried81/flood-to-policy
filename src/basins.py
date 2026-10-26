"""River basin districts: who is exposed in a basin they do not control.

NUTS3 answers "who is exposed". It cannot answer the question `docs/strategy.md`
names as the one most teams will not ask: the Meuse rises in France, floods
Belgium and reaches the Netherlands, so a warning issued nationally arrives late
downstream. That is the argument for action at EU level rather than national
level, and it needs the unit water obeys rather than the unit administrations are
drawn on.

The source is `eea_river_basin_districts` in `config/sources.yaml`: the districts
reported under the Water Framework Directive, served live from the EEA's ArcGIS
REST endpoint. Queried rather than mirrored because the EEA's bulk download is
the whole WISE package as one 3.4 GB share with no per-layer URL - and cached to
disk on first use, like `src/rdh.py`, so the day of the event needs no network.

**What this module does NOT claim.** It says nothing about *upstream*. Saying
that Wallonia's water comes from France needs a flow network, and the WFD
districts carry none - they are catchment boundaries, not topology. What is
defensible from these polygons alone is that a region's basin is **shared**: that
the ground draining into the same water body lies in more than one country, so no
single authority holds all the levers. That is weaker than "upstream" and it is
still the whole argument, because the policy conclusion - coordinate at basin
level - follows from sharing, not from direction.

**A district is not an aggregate of NUTS3 regions.** Districts cross national
borders AND cut regions in half, so every figure here is built by intersecting
areas in EPSG:3035. Summing the NUTS3 rows that "belong" to a basin would
double-count every region a boundary crosses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
import yaml

from src.data_io import WORKING_CRS

DATA = Path(__file__).resolve().parents[1] / "data"
CACHE = DATA / "processed" / "basins_cache" / "wfd2016_river_basin_districts.geojson"

SERVICE = (
    "https://water.discomap.eea.europa.eu/arcgis/rest/services/WISE_WFD/"
    "WFD2016_RiverBasinDistrict_WM/MapServer/0/query"
)

#: Three minutes, which is absurd for one HTTP call and is what this service
#: needs. Measured 2026-10-06: 25 districts come back in about 40 s and 50 in
#: 59-75 s. A 60 s timeout cut a request that was working.
TIMEOUT_S = 180

#: Paging is by offset, and ArcGIS says there is more with `exceededTransferLimit`.
#:
#: 25, not the service's advertised `maxRecordCount` of 2000. The districts are
#: detailed polygons and the endpoint falls over well below its own cap: measured
#: 2026-10-06, 10 records take ~25 s, 25 take ~40 s, 50 take 59-75 s, and 100 and
#: 200 both answer **HTTP 500** - a server-side timeout, not a rejection, so there
#: is no error message to read. 25 sits with a margin under the break point. The
#: whole layer is 196 districts, so that is 8 pages and about five minutes, once,
#: and then the cache answers.
PAGE_SIZE = 25
MAX_PAGES = 50

#: Requested by name, never as `outFields=*`. The layer carries an attribute
#: literally called `geometry` beside its real geometry, and asking for every
#: field in GeoJSON makes the two collide: the service answers HTTP 500, with no
#: hint as to why. Measured 2026-10-06. These five are what a brief needs - the
#: WFD code, the international and local names, the INSPIRE id, and the reporting
#: country, which is what `check_crosswalk` validates the crosswalk against.
OUT_FIELDS = (
    "thematicIdIdentifier",
    "nameTextInternational",
    "nameText",
    "inspireIdLocalId",
    "countryCode",
)

#: The district's own code, and the key `config/international_basins.yaml` uses.
CODE_COLUMN = "thematicIdIdentifier"

#: The layer's own reporting country, as opposed to the countries its geometry
#: covers. Used only to validate the crosswalk, never to produce a figure: a
#: district's reporting country says who filled the form, and the question here
#: is which ground the water crosses.
SERVICE_COUNTRY_COLUMN = "countryCode"

#: The declared grouping of national portions into international basins. The
#: service has no such field - see the file's own header for why it has to exist
#: and how to falsify it.
CROSSWALK = Path(__file__).resolve().parents[1] / "config" / "international_basins.yaml"

#: The admin frame's country column, in order of preference. `boundaries()` in
#: `scripts/build_exposure.py` renames GISCO's `CNTR_CODE` to `country`, and that
#: frame is what every caller here passes; a frame read straight from the GISCO
#: shapefile keeps the original name. Both are accepted, because requiring one of
#: them meant this module raised on the kit's own boundaries and the figure was
#: never produced at all. Required rather than inferred from the id prefix: a
#: crosswalked or renamed id would make that inference quietly wrong.
COUNTRY_COLUMNS = ("country", "CNTR_CODE")

#: Below this, a country's presence in a district is a border sliver, not a share
#: of the basin.
#:
#: The districts and the NUTS3 regions are independent renderings of the same
#: borders, so their edges disagree by a few hundred metres everywhere and every
#: district along one picks up a thin strip of its neighbour. Measured 2026-10-06
#: on the 196 real districts against the 1,345 NUTS3 regions: by raw
#: intersection, 109 of the 182 districts the frame reaches touch two or more
#: countries and one touches eight; with this threshold, exactly one does -
#: DE2000 Hochrhein, which really is in three. Without it, `is_shared` was true for
#: more than half the layer, and that number was topology rather than hydrology.
#:
#: 50 km2 is two orders of magnitude above the sliver scale and well below the
#: district that is genuinely in two countries, so the figure does not turn on
#: where in that gap the line is drawn.
MIN_COUNTRY_AREA_M2 = 50e6


def _country_column(frame: gpd.GeoDataFrame) -> str:
    """Whichever of `COUNTRY_COLUMNS` the frame carries."""
    for name in COUNTRY_COLUMNS:
        if name in frame.columns:
            return name
    raise ValueError(
        f"The admin frame has no country column - looked for "
        f"{' or '.join(repr(c) for c in COUNTRY_COLUMNS)} - so there is no way "
        f"to tell which countries a basin is shared between. Columns: "
        f"{sorted(frame.columns)}."
    )


class BasinsUnavailable(RuntimeError):
    """The districts could not be obtained, with the reason in the message.

    Its own type so a caller can tell "the EEA is down" from "the geometry is
    wrong", and so a UI can say which rather than showing a traceback.
    """


def international_basins(path: Path | str = CROSSWALK) -> dict[str, str]:
    """District code -> international basin id, from the declared crosswalk.

    A plain mapping rather than a frame, because it is consulted per district and
    never joined. A district the file does not mention is absent from the result
    and is treated downstream as its own basin, which is the honest default: not
    being in the crosswalk means nobody has established that it is shared.
    """
    path = Path(path)
    if not path.exists():
        raise BasinsUnavailable(
            f"{path} is missing. Without it a district is its own basin, and "
            f"every international basin in Europe reports as unshared - see the "
            f"file's header."
        )
    declared = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for basin_id, body in (declared.get("basins") or {}).items():
        for code in body.get("districts") or []:
            if code in out:
                raise ValueError(
                    f"{path.name}: district {code} is claimed by both "
                    f"`{out[code]}` and `{basin_id}`. A district drains into one "
                    f"basin; two groups sharing it would double-count its area."
                )
            out[code] = basin_id
    if not out:
        raise ValueError(f"{path.name} declares no districts at all.")
    return out


def basin_names(path: Path | str = CROSSWALK) -> dict[str, str]:
    """International basin id -> the name a reader knows it by ("Danube").

    Read from the same declared file as the grouping, so a basin's name cannot
    disagree with the districts it groups. Empty when the file is missing: a
    name is a label, and its absence must not stop the shares being computed.
    """
    path = Path(path)
    if not path.exists():
        return {}
    declared = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        basin_id: body.get("name") or basin_id
        for basin_id, body in (declared.get("basins") or {}).items()
    }


def check_crosswalk(
    districts: gpd.GeoDataFrame, path: Path | str = CROSSWALK
) -> pd.DataFrame:
    """Test the crosswalk against the layer it claims to group. One row per basin.

    The crosswalk is the one thing in this module that is asserted rather than
    measured, so it gets the strongest check available. Three of them:

    - every declared code exists in the layer, so a typo or a retired district
      cannot sit in the file looking authoritative;
    - a basin spans at least two reporting countries, which is what makes it
      international in the first place;
    - the portions are CONTIGUOUS - every district reaches the same piece of
      ground. A real basin's national parts meet along the border, so a wrong
      grouping shows up as districts that never touch. Tolerated to 1 km, because
      the two sides are drawn from different national datasets and their edges do
      not match.

    Contiguity is "every district is in the LARGEST piece", not "the union is one
    piece". Measured 2026-10-06, the stricter form failed on two correct
    groupings: the Rhine's six districts all sit in one body of 168,166 km2
    alongside six fragments of 0 km2 left by the geometry repair, and the
    Nemunas' two sit in one of 54,014 km2 beside a detached 720 km2 outlier that
    contains no district at all. Islands, lagoons and repair slivers are not
    evidence about a basin.

    Returns the report rather than raising, so a caller can print it: the answer
    to "is the Adriatic one basin or two" is a table, not an exception.
    """
    crosswalk = international_basins(path)
    if CODE_COLUMN not in districts.columns:
        raise ValueError(
            f"The districts frame has no `{CODE_COLUMN}` column, so there is "
            f"nothing to match the crosswalk against. Columns: "
            f"{sorted(districts.columns)}."
        )
    missing = sorted(set(crosswalk) - set(districts[CODE_COLUMN]))
    if missing:
        raise ValueError(
            f"{Path(path).name} declares districts the layer does not have: "
            f"{missing}. The layer is a reporting vintage: a code can be retired."
        )
    metric = repair(districts.to_crs(WORKING_CRS), "the WFD districts")
    rows = []
    for basin_id in sorted(set(crosswalk.values())):
        codes = [c for c, b in crosswalk.items() if b == basin_id]
        part = metric[metric[CODE_COLUMN].isin(codes)]
        merged = part.geometry.buffer(1_000).union_all()
        pieces = sorted(getattr(merged, "geoms", [merged]), key=lambda g: -g.area)
        body = pieces[0]
        detached = int(
            (~part.geometry.representative_point().within(body)).sum()
        )
        countries = (
            sorted(set(part[SERVICE_COUNTRY_COLUMN].dropna()))
            if SERVICE_COUNTRY_COLUMN in part.columns
            else []
        )
        rows.append(
            {
                "basin": basin_id,
                "districts": len(part),
                "countries": countries,
                "n_countries": len(countries),
                "contiguous": detached == 0,
                "detached": detached,
                "km2": float(part.geometry.area.sum() / 1e6),
            }
        )
    report = pd.DataFrame(rows).set_index("basin")
    return report


def _page(url: str, offset: int) -> dict[str, Any]:
    """One page of the layer as GeoJSON."""
    params = {
        "where": "1=1",
        "outFields": ",".join(OUT_FIELDS),
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        # Degrees: the join below reprojects to EPSG:3035 itself, and asking the
        # service for a projected CRS it may or may not support is a way to get
        # silently reprojected data.
        "outSR": 4326,
    }
    response = requests.get(url, params=params, timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()


def districts(
    *, url: str = SERVICE, use_cache: bool = True, cache: Path = CACHE
) -> gpd.GeoDataFrame:
    """Every WFD river basin district, from cache when there is one.

    Cached as one GeoJSON file rather than per page: the pages are an artefact of
    the service's record cap, not of the data, and a half-written cache of pages
    would be indistinguishable from a complete one.
    """
    cache = Path(cache)
    if use_cache and cache.exists():
        return gpd.read_file(cache)

    features: list[dict[str, Any]] = []
    try:
        for _ in range(MAX_PAGES):
            payload = _page(url, len(features))
            batch = payload.get("features") or []
            features.extend(batch)
            if not payload.get("exceededTransferLimit") or not batch:
                break
        else:
            raise BasinsUnavailable(
                f"{url} still reported more records after {MAX_PAGES} pages of "
                f"{PAGE_SIZE}, which is {MAX_PAGES * PAGE_SIZE} districts against "
                f"the 196 the layer held on 2026-10-06. The offset is almost "
                f"certainly being ignored; check the service by hand."
            )
    except requests.RequestException as exc:
        raise BasinsUnavailable(
            f"Could not reach the EEA WISE service ({exc}). It is an `access: api` "
            f"source, so there is no mirrored copy: cache it before the event."
        ) from exc

    if not features:
        raise BasinsUnavailable(f"{url} returned no districts at all.")

    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}),
            encoding="utf-8",
        )
    return frame


def repair(
    frame: gpd.GeoDataFrame, what: str, *, method: str = "linework"
) -> gpd.GeoDataFrame:
    """Make every geometry valid, loudly.

    A self-intersecting polygon does not raise in `gpd.overlay` - it produces a
    plausible-looking area. Measured on a bowtie district: an area share of 0.5
    where the intended polygon covered the whole region, with no warning. So the
    repair is unconditional and the count is printed, because a layer that needs
    repairing is a layer worth knowing about.

    Public because `src/apsfr.py` overlays a second reported layer against the
    same admin frame and needs exactly this guarantee; `what` carries the caller's
    own name so the message says which layer was repaired.

    `method` defaults to shapely's "linework" repair, which is what every figure
    in this module was measured with. "structure" is the stronger one: it
    guarantees polygonal output for polygonal input, where linework can return a
    collection mixing lines and polygons that a later overlay rejects. It is
    opt-in rather than the default precisely so that changing it cannot silently
    move a basin share that was published under the other one.
    """
    invalid = ~frame.geometry.is_valid
    if invalid.any():
        print(
            f"repaired {int(invalid.sum())} invalid geometr"
            f"{'y' if invalid.sum() == 1 else 'ies'} in {what}",
            flush=True,
        )
        frame = frame.assign(
            geometry=frame.geometry.make_valid(
                method=method, keep_collapsed=method != "structure"
            )
        )
    return frame


def _overlay(admin: gpd.GeoDataFrame, basins: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Region-by-district pieces, with the area of each, in EPSG:3035.

    Metric CRS because every figure downstream is an area share, and an area
    computed in degrees is wrong by a factor that varies with latitude.

    Pieces are NOT merged by basin here, and the shares downstream are the area
    of their union rather than the sum of their areas. The WFD layer publishes
    one row per member state per basin, but those rows are disjoint national
    portions - measured 2026-10-06, the three Scheldt rows overlap by 0 km2 - so
    there is nothing to merge, and no field in the layer to merge them on.
    Overlap is still possible in a frame assembled by hand, and the union handles
    that without needing to know where the frame came from.
    """
    country = _country_column(admin)
    left = repair(admin.to_crs(WORKING_CRS), "the admin frame").reset_index(
        names="_region"
    )
    right = repair(basins.to_crs(WORKING_CRS), "the WFD districts").reset_index(
        names="_basin"
    )
    try:
        pieces = gpd.overlay(
            left[["_region", country, "geometry"]],
            right[["_basin", "geometry"]],
            how="intersection",
            keep_geom_type=True,
        )
    except Exception as exc:  # GEOSException and friends are not a sane API
        raise BasinsUnavailable(
            f"The region/district intersection failed ({type(exc).__name__}: "
            f"{exc}). This is a geometry problem, not a service one: check the "
            f"two frames with `.geometry.is_valid`."
        ) from exc
    pieces["piece_area_m2"] = pieces.geometry.area
    return pieces


def _check_reference(admin: gpd.GeoDataFrame) -> None:
    """Refuse a frame that cannot answer the question.

    Whether a basin is shared is read off the countries present in the admin
    frame, so a Belgium-only frame reports the Meuse as NOT shared - the exact
    opposite of the truth, as `0.0`, which this module's own comments treat as a
    finding rather than an absence. Measured: `shared_basin_share` 1.0 with a
    pan-European frame and 0.0 with a Belgian one, for the same district.

    There is no way to detect this from the geometry, so the one case that is
    certainly wrong is refused outright, and the docstrings say the rest.
    """
    countries = set(admin[_country_column(admin)].dropna().unique())
    if len(countries) < 2:
        raise ValueError(
            f"The admin frame holds {sorted(countries) or 'no countries'}, so "
            f"every basin in it looks unshared by construction - which is the "
            f"opposite of this module's answer for any international basin. "
            f"Pass a frame covering every country the districts touch (the full "
            f"GISCO NUTS3 layer), then filter the RESULT to the regions you want."
        )


def _group_key(
    basins: gpd.GeoDataFrame, crosswalk: dict[str, str] | None
) -> pd.Series:
    """Per district row, the basin it is a portion of - itself when none.

    Falling back to the row is what makes a missing crosswalk entry read as "not
    established", rather than quietly merging a district into a neighbour.
    """
    rows = pd.Series(basins.index, index=basins.index)
    if not crosswalk or CODE_COLUMN not in basins.columns:
        return rows.astype("object")
    mapped = basins[CODE_COLUMN].map(crosswalk)
    return mapped.where(mapped.notna(), "district:" + rows.astype("str")).astype(
        "object"
    )


def basin_countries(
    admin: gpd.GeoDataFrame,
    basins: gpd.GeoDataFrame,
    crosswalk: dict[str, str] | None = None,
    pieces: gpd.GeoDataFrame | None = None,
) -> pd.DataFrame:
    """Per district: which countries it covers, and how many.

    Derived from the admin frame's own country codes rather than from the
    service's attributes, so that the answer is consistent with the exposure
    table, which is built on these same polygons.

    A country counts only once its pieces of the district reach
    `MIN_COUNTRY_AREA_M2`. Two independent renderings of the same border never
    agree to the metre, so without that floor every district along one collects a
    sliver of its neighbour and reports itself international: 109 of the 182 real
    districts the NUTS3 frame reaches, against the one that genuinely is.

    The countries are those of the whole INTERNATIONAL BASIN the district is a
    portion of, not of the district polygon alone. The WFD publishes one polygon
    per member state per basin, each inside one country, so the polygon's own
    country list answers the wrong question: measured 2026-10-06, grouping by
    polygon reported every international basin in Europe as unshared. The
    grouping comes from `config/international_basins.yaml`, which is declared
    because the service carries no field for it, and is validated by
    `check_crosswalk`. A district the crosswalk does not mention stays its own
    basin, so "not established" never reads as "shared".
    """
    _check_reference(admin)
    country = _country_column(admin)
    if crosswalk is None:
        crosswalk = international_basins()
    # `pieces` is an escape hatch for a caller that has already paid for the
    # intersection. It is the expensive step by a wide margin - about two minutes
    # over 196 districts and 1,345 regions - and `shared_basin_exposure` needs the
    # same pieces, so computing them twice doubled the only slow part of the build.
    if pieces is None:
        pieces = _overlay(admin, basins)
    # Area per (district, country), thresholded before anything is counted, then
    # pooled over the basin's portions.
    area = pieces.groupby(["_basin", country])["piece_area_m2"].sum()
    kept = area[area >= MIN_COUNTRY_AREA_M2].reset_index()
    group = _group_key(basins, crosswalk)
    kept["_group"] = kept["_basin"].map(group)
    per_group = kept.groupby("_group")[country].apply(lambda s: sorted(set(s)))
    pooled = group.map(per_group)
    out = pd.DataFrame(
        {
            "basin_id": group,
            "countries": pooled,
            "n_countries": pooled.apply(lambda v: len(v) if isinstance(v, list) else 0),
        }
    ).reindex(basins.index)
    out["countries"] = out["countries"].apply(lambda v: v if isinstance(v, list) else [])
    out["n_countries"] = out["n_countries"].fillna(0).astype("int64")
    out["is_shared"] = out["n_countries"] > 1
    return out


def _shared_basin_names(pieces: gpd.GeoDataFrame, labels: dict) -> pd.Series:
    """Per region, the names of its SHARED basins, largest share of it first.

    Restricted to `is_shared` for the reason `_others` gives: these names stand
    beside `shared_with`, and a basin listed there must be one the countries
    were counted on. Ordered by area so the first name is the basin that
    matters most to the region, not the alphabetically first. `labels` maps a
    basin id to its name; an id it lacks is shown as is rather than dropped.
    """
    shared = pieces[pieces["is_shared"]]
    if shared.empty:
        return pd.Series(dtype="object")
    names = labels
    area = shared.groupby(["_region", "basin_id"])["piece_area_m2"].sum()
    ordered = area.reset_index().sort_values(
        ["_region", "piece_area_m2"], ascending=[True, False]
    )
    ordered["name"] = ordered["basin_id"].map(lambda b: names.get(b, str(b)))
    return ordered.groupby("_region")["name"].apply(list)


def shared_basin_exposure(
    admin: gpd.GeoDataFrame,
    basins: gpd.GeoDataFrame,
    crosswalk: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Per region: how much of it drains into a basin it shares with others.

    Five columns:

    - `shared_basin_share` - the share of the region's area, in [0, 1], lying in
      a district that also covers another country. The figure to rank on: a
      region at 1.0 controls none of the ground its flood comes from.
    - `shared_with` - the other countries, sorted, of the region's SHARED basins
      only. What turns the number into a sentence a decision-maker can act on -
      which is why it is read off the same basins as `shared_basin_share`: a
      partner listed beside a share of 0.0 states the opposite of the share.
    - `shared_basins` - the names of those same shared basins, the one holding
      most of the region first. "Shared with SK" says who to call; "Danube" says
      about what, and is the word the policy text uses.
    - `basin_countries_max` - the most countries any single one of the region's
      basins spans. A region in one basin shared with five countries is a harder
      coordination problem than one in five bilateral basins.
    - `basin_area_share` - how much of the region any district covers at all.
      Below 1.0 the three figures above describe only that part, and coastal
      regions draining straight to sea are legitimately below it.

    Shares, never counts: a region's area in square metres would rank by how big
    it is, which nobody needs a model to find out.

    **`admin` must cover every country the districts touch.** Whether a basin is
    shared is derived from the country codes present in this frame, so a
    single-country frame would report every international basin as unshared.
    Pass the full NUTS3 layer and filter the RESULT; a frame with fewer than two
    countries is refused rather than answered wrongly.

    **The basin, not the polygon.** The WFD publishes one polygon per member
    state per basin - the Meuse arrives as a French, a Walloon, a Flemish, a
    Luxembourgish and a Dutch district, each lying inside one country - so a
    region's own district polygon can never say whether its water crosses a
    border. Measured 2026-10-06: by polygon, exactly one of the 196 districts
    spans more than one country, which reported essentially all of Europe as
    drained by water it governs. The grouping into international basins is
    declared in `config/international_basins.yaml`, because the service carries
    no field for it.

    **Still a floor, for two reasons.** Switzerland, Belarus, Ukraine, Serbia and
    the other non-reporting states hold large shares of the Rhine, the Danube,
    the Vistula and the Daugava; and the districts that cannot be grouped from
    this layer are listed as `unresolved` in that file rather than silently
    counted as national.
    """
    _check_reference(admin)
    country = _country_column(admin)
    # Repaired once here and handed to the overlay, rather than repaired by each
    # step that needs it: the message it prints is a fact about the data, and
    # printing it three times makes it look like three different problems.
    metric = repair(admin.to_crs(WORKING_CRS), "the admin frame")
    pieces = _overlay(metric, basins)
    empty = pd.DataFrame(
        {
            "shared_basin_share": pd.Series(float("nan"), index=admin.index),
            "basin_area_share": pd.Series(float("nan"), index=admin.index),
            "basin_countries_max": pd.Series(0, index=admin.index, dtype="int64"),
            "shared_with": pd.Series([[] for _ in admin.index], index=admin.index),
            "shared_basins": pd.Series([[] for _ in admin.index], index=admin.index),
        }
    )
    # An overlay with nothing in it is a real case - a frame of coastal regions
    # draining straight to sea, or a districts frame clipped to another country -
    # and it has to return the same four columns rather than raise. Taken early
    # because `groupby().apply()` on an empty frame returns an empty DataFrame
    # where a Series is expected, and pandas fails with a buffer-dimension error
    # that says nothing about basins.
    if pieces.empty:
        return empty

    countries = basin_countries(admin, basins, crosswalk, pieces=pieces)
    pieces = pieces.join(countries, on="_basin")

    region_area = metric.geometry.area
    by_region = pieces.groupby("_region")

    def _union_area(frame: gpd.GeoDataFrame) -> pd.Series:
        """Area of the UNION of a region's pieces, not the sum of their areas.

        Districts can overlap each other - the layer is reported per member
        state and the pieces are not guaranteed disjoint - and summing areas
        then counts the same ground twice. Measured on two overlapping
        districts before this: a share of 1.2 on a figure documented as a share.
        """
        if frame.empty:
            return pd.Series(dtype="float64")
        return frame.dissolve(by="_region").geometry.area

    shared = _union_area(pieces[pieces["is_shared"]])
    covered = _union_area(pieces)

    def _others(frame: pd.DataFrame) -> list[str]:
        """The partner countries of the region's SHARED basins only.

        Restricted to `is_shared` because the country lists it reads were built
        behind `MIN_COUNTRY_AREA_M2`, and the pieces it reads were not. A region
        overlapping a neighbour's district by a sliver therefore collected that
        neighbour here while the same sliver was correctly discarded when the
        basin's countries were counted - so the region read "shares with EL"
        beside a `shared_basin_share` of 0.0, which is the opposite sentence.
        """
        own = set(frame[country])
        every = {
            c for row in frame.loc[frame["is_shared"], "countries"] for c in row
        }
        return sorted(every - own)

    out = pd.DataFrame(
        {
            "shared_basin_share": shared.reindex(admin.index).fillna(0.0)
            / region_area.where(region_area > 0),
            "basin_area_share": covered.reindex(admin.index).fillna(0.0)
            / region_area.where(region_area > 0),
            "basin_countries_max": by_region["n_countries"].max().reindex(admin.index),
            "shared_with": pieces.groupby("_region")[
                [country, "countries", "is_shared"]
            ]
            .apply(_others)
            .reindex(admin.index),
        }
    )
    # A basin the crosswalk does not group is one district, and is labelled by
    # the district's own code - never by its row number, which means nothing.
    labels = {
        **dict(zip(countries["basin_id"], basins.get(CODE_COLUMN, countries["basin_id"]))),
        **basin_names(),
    }
    out["shared_basins"] = _shared_basin_names(pieces, labels).reindex(admin.index)
    # The union of a region's pieces cannot exceed the region, but its area is
    # computed from different vertices than the region's own and lands a few
    # 1e-15 above it: measured on the real layer, 153 regions read
    # 1.0000000000000022 for a figure documented as a share in [0, 1].
    for column in ("shared_basin_share", "basin_area_share"):
        out[column] = out[column].clip(upper=1.0)
    out["basin_countries_max"] = out["basin_countries_max"].fillna(0).astype("int64")
    for column in ("shared_with", "shared_basins"):
        out[column] = out[column].apply(lambda v: v if isinstance(v, list) else [])
    # A region no district covers has no share to report. 0.0 would read as
    # "drains nowhere shared", which is a finding; this is an absence.
    uncovered = out["basin_area_share"] <= 0
    out.loc[uncovered, ["shared_basin_share", "basin_area_share"]] = float("nan")
    return out
