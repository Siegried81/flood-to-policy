"""JSON API over the flood-exposure kit, consumed by the React UI in web/.

It serialises what `src/` already computes and decides nothing of its own: the
exposure figures, the vulnerability ranking with its sensitivity, and the
grounded retrieval. Keeping the decisions in `src/` means the Streamlit app and
this API cannot drift into disagreeing about a number — which matters, because
both are shown to the same jury. The three presentation decisions `src/` has no
opinion on — which columns may be weighted into the vulnerability index, which
return period a figure belongs to, and what a climate period's figures are
allowed to claim — live here as `vulnerability_indicators`, `_one_return_period`
and `climate_periods`, and `app/streamlit_app.py` imports the first and the
third rather than restating them.

Two things it deliberately does NOT do:

- **It does not approve anything.** `POST /api/draft` returns a draft together
  with its offline checks: the grounding score, any invalid citation, every
  number found in no passage and not in the table, and every claim sentence
  with no citation. Approval is a separate call that a human triggers, only that
  call writes to the brief, and it re-runs the checks on the text it is given.
  The draft route calls `rag.complete` directly; the LangGraph pipeline in
  `src/workflow.py`, with its `interrupt` gate, is not on this path.
- **It does not fetch map tiles.** The choropleth is served as GeoJSON and drawn
  as SVG in the browser. No tile provider, no API key, nothing to fail on a
  hackathon network — and the map still works with the Wi-Fi unplugged.

With `HOSTED=1` (the public demo) every route that would call a model or write
the brief answers 403 before touching a provider; `GET /api/config` tells the UI.

Run with `uvicorn api.main:app --port 8010`.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import nlquery, rag, translate  # noqa: E402
from src.toon_io import fit_rows, flatten, to_toon, token_report  # noqa: E402
from src.demographics import LEGACY_COLUMNS, with_current_names  # noqa: E402
from src.vulnerability import sensitivity  # noqa: E402
from src.policy_tool import EU27  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger(__name__)
EXPOSURE = ROOT / "data" / "processed" / "exposure.parquet"
CONTEXT = ROOT / "data" / "processed" / "context.parquet"
GEOMETRY = ROOT / "data" / "processed" / "regions.geojson"
APPROVED = ROOT / "data" / "processed" / "approved.md"
EVENT_WEB = ROOT / "data" / "processed" / "event_2021_web.json"
#: The local build with GISCO borders and NUTS3 lines (`export_event_web.py --full`):
#: git ignores it, so it exists only on a machine holding the raw boundaries.
EVENT_WEB_FULL = ROOT / "data" / "processed" / "event_2021_web.full.json"
WEB_DIST = ROOT / "web" / "dist"
DEV_ORIGINS = ["http://localhost:5190", "http://127.0.0.1:5190"]

# Numeric columns that describe the SCENARIO rather than the people living in it,
# and so are never offered as vulnerability indicators. `annual_probability` is
# the one that matters: picked as an indicator it reads as "a more frequent flood
# makes residents more vulnerable", which is not a claim about vulnerability at
# all. `app/streamlit_app.py` imports the helper below rather than restating this
# set, because the composite index is a weighted mean over whatever is selected -
# so one extra column in one UI gives the same region two different scores from
# the same frozen table.
#
# `cells_counted` and `hazard_coverage` are excluded for a second reason: they
# describe how well the rasters cover the unit, not the people in it. They sit
# before `exposed_pop` in the table, so leaving them in made them the first
# entries of this list - and the default selection is its first three, which
# would have built the index out of raster bookkeeping. `hazard_coverage`
# belongs next to a figure as its qualifier, never inside one.
#: Numeric columns of the exposure table that are NOT vulnerability indicators.
#:
#: The index is a weighted mean of min-max scaled columns, so anything numeric
#: left out of this set joins it silently. `total_pop` is the trap that proved
#: it: added to the table as a denominator, it is offered as an indicator unless
#: listed here - which ranks a region as vulnerable for being populous, not for
#: being flooded. Any column added to the parquet has to be judged against this
#: list in the same pass.
#:
#: The Eurostat columns `share_over_65` and
#: `poverty_rate_pct` ARE indicators and stay out of this set - they are properties
#: of the people, which is what the index is supposed to weigh, and they are the
#: reason it has more than one axis at all. Their `_year` and `_level` companions
#: are stored as TEXT rather than numbers, so they are excluded by dtype and
#: cannot drift into the index if someone forgets this list. `gdp_meur` is a
#: denominator and never reaches this table: it is written to
#: `context.parquet` instead.
NON_INDICATOR_COLUMNS = frozenset({
    "return_period", "annual_probability", "cells_counted", "hazard_coverage",
    "total_pop",
})

app = FastAPI(title="Flood exposure API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Approve-Token"],
)


def _table() -> pd.DataFrame:
    """The frozen exposure table, or a 404 explaining how to build one."""
    if not EXPOSURE.exists():
        raise HTTPException(
            status_code=404,
            detail="No exposure table. Build one with `python scripts/build_exposure.py`, "
                   "which writes data/processed/exposure.parquet. It needs the rasters "
                   "`python -m src.fetch` downloads. The frozen table is committed, so a "
                   "checkout without it is older than that commit; the rasters never are.",
        )
    # Under the current column names whichever build froze it: a table from
    # before the units rename still says `poverty_rate`. See `LEGACY_COLUMNS`.
    return with_current_names(pd.read_parquet(EXPOSURE))


def _region_key(df: pd.DataFrame) -> str:
    """Whichever identifier column this run used. NUTS3 for Europe, LAU for a zoom.

    The rule itself lives in `nlquery.region_key`; this wrapper only turns its
    error into the HTTP status a route returns.
    """
    try:
        return nlquery.region_key(df)
    except nlquery.SpecError:
        raise HTTPException(status_code=500,
                            detail="No region identifier column in the table.") from None


def vulnerability_indicators(df: pd.DataFrame) -> list[str]:
    """Numeric columns that may be weighted into the vulnerability index, in table order.

    Exported so `app/streamlit_app.py` can offer exactly this list: the index is a
    weighted mean of min-max scaled columns, so a UI that offers one column the
    other does not reports a different composite score for the same region.
    """
    return [
        c for c in df.columns
        if df[c].dtype.kind in "if" and c not in NON_INDICATOR_COLUMNS
    ]


_return_periods = nlquery.return_periods


def _one_return_period(
    df: pd.DataFrame, requested: int | None
) -> tuple[pd.DataFrame, int | None, bool]:
    """Narrow the table to exactly one return period, and say which one.

    Return-period extents are NESTED - the 100-year zone contains the 10-year one
    - so there is no "all periods" reading of this table: any figure summed across
    periods counts the core floodplain once per period, and any ranking taken
    across them is really a ranking of whichever period the rows happened to be
    concatenated in first. Naming no period therefore selects the rarest one, the
    same default both UIs show, rather than quietly meaning "all of them".

    Returns the narrowed frame, the period it is for (None when the table carries
    no return period at all), and whether the server picked it.
    """
    periods = _return_periods(df)
    if not periods:
        # No return_period column: one row per region already, nothing to narrow.
        return df, None, False
    if requested is None:
        chosen = periods[-1]
        return df[df["return_period"] == chosen], chosen, True
    if requested not in periods:
        # An empty selection would otherwise report total_exposed 0.0, which reads
        # as "measured, nobody exposed" for a scenario that was never computed.
        raise HTTPException(
            status_code=400,
            detail=f"No return period {requested} in the table. Available: {periods}.",
        )
    return df[df["return_period"] == requested], requested, False


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


#: The message every model or write route returns in the hosted demo.
HOSTED_REFUSAL = ("{what} is disabled in the hosted demo: it would call a language model "
                  "or write files on a shared server. Run the kit locally to use it.")


def hosted() -> bool:
    """True when the env says this is the public demo (`HOSTED=1`).

    Read on every request rather than at import, so a test (or an operator)
    flips it without reloading the app. Anything but "1"/"true"/"yes" is off,
    so an unset variable keeps the local behaviour.
    """
    return os.environ.get("HOSTED", "").strip().lower() in {"1", "true", "yes"}


def _refuse_if_hosted(what: str) -> None:
    """403 before any provider is touched, when running as the hosted demo.

    A public demo with a model behind it spends the owner's quota for every
    visitor and lets anyone write to the brief, so those routes are switched
    off rather than rate-limited. 403, not 404: the route exists, this
    deployment refuses it, and the UI can say so.
    """
    if hosted():
        raise HTTPException(status_code=403, detail=HOSTED_REFUSAL.format(what=what))


@app.get("/api/config")
def config() -> dict:
    """What this deployment allows, so the UI greys out what it would refuse."""
    on = not hosted()
    return {"hosted": not on, "llm_enabled": on, "approve_enabled": on,
            "event2021_available": EVENT_WEB.exists() or (on and EVENT_WEB_FULL.exists())}


@app.get("/api/event2021")
def event2021() -> Response:
    """The precomputed July 2021 story (`scripts/export_event_web.py`), as is.

    Served byte for byte: the file is already compact JSON, and re-parsing a
    few hundred kB of map data on every request would only cost time. Locally
    the `--full` build wins when present; the hosted demo always serves the
    public one, whose geometry may be redistributed.
    """
    if not hosted() and EVENT_WEB_FULL.exists():
        return Response(content=EVENT_WEB_FULL.read_bytes(), media_type="application/json")
    if not EVENT_WEB.exists():
        raise HTTPException(
            status_code=404,
            detail="event_2021_web.json is missing. Build it with "
                   "`python scripts/export_event_web.py` (needs the raw EMS layers "
                   "and hazard rasters).",
        )
    return Response(content=EVENT_WEB.read_bytes(), media_type="application/json")


@app.get("/api/meta")
def meta() -> dict:
    """What run is on screen, so the UI can say it out loud.

    The freeze is the discipline that keeps the map, the brief and the pitch
    agreeing; naming the run is how a reader checks they are looking at it.
    """
    df = _table()
    key = _region_key(df)
    return {
        "key": key,
        "rows": len(df),
        "regions": int(df[key].nunique()),
        "return_periods": _return_periods(df),
        "indicators": vulnerability_indicators(df),
        "frozen_at": datetime.fromtimestamp(EXPOSURE.stat().st_mtime, timezone.utc).isoformat(),
        "has_geometry": GEOMETRY.exists(),
        "has_context": CONTEXT.exists(),
        "corpus_passages": len(rag.load_index().passages),
        # Whether, never what: the UI shows a token field only when approve
        # will ask for one, and the secret stays in the approver's head.
        "approve_token_required": bool(os.environ.get("FLOOD_APPROVE_TOKEN")),
    }


@app.get("/api/exposure")
def exposure(return_period: int | None = None) -> dict:
    """Exposure per region for exactly ONE return period.

    `exposed_share` is computed here rather than client-side because it is the
    figure that should be ranked: an absolute count ranks by population and tells
    a decision-maker nothing they did not already know.

    Naming no return period does not mean "every period": the extents are nested,
    so `total_exposed` over several of them counts the core floodplain once per
    period. The server narrows to the rarest period instead and sets
    `defaulted_return_period`, so a caller that never chose can tell that the
    figures belong to one scenario the server picked.
    """
    df = _table()
    key = _region_key(df)
    df, period, defaulted = _one_return_period(df, return_period)
    if {"exposed_pop", "total_pop"} <= set(df.columns):
        df = df.assign(exposed_share=df["exposed_pop"] / df["total_pop"])

    # Membership travels on each row so a UI can show the EU-27, which every
    # EU-level figure in the brief is quoted on, without dropping the other ten
    # countries of the GISCO file. Added to the answer only, never to the table,
    # so it cannot be offered as a vulnerability indicator.
    if "country" in df.columns:
        df = df.assign(eu27=df["country"].isin(EU27))
    records = json.loads(df.to_json(orient="records"))  # NaN -> null, which JSON can carry
    # null rather than 0 when the column is absent: "we did not measure this" and
    # "we measured nobody" must not arrive in the same shape.
    measured = "exposed_pop" in df.columns
    return {
        "key": key,
        "return_period": period,
        "defaulted_return_period": defaulted,
        "rows": records,
        # Surfaced, never folded into the totals: a region the raster does not
        # cover is not a region with nobody exposed.
        "unmeasured": int(df["exposed_pop"].isna().sum()) if measured else None,
        "total_exposed": float(df["exposed_pop"].sum(skipna=True)) if measured else None,
    }


@app.get("/api/geometry")
def geometry() -> dict:
    """Simplified region polygons for the choropleth.

    Served as GeoJSON and drawn as SVG in the browser: no tile provider, no key,
    and the map still renders with the network unplugged.
    """
    if not GEOMETRY.exists():
        raise HTTPException(
            status_code=404,
            detail="No regions.geojson. Build it with `python scripts/build_geometry.py`, "
                   "which simplifies the GISCO boundaries `python -m src.fetch` downloads. "
                   "Without it this endpoint 404s and the choropleth renders nothing.",
        )
    return json.loads(GEOMETRY.read_text(encoding="utf-8"))


# The per-region context table is loaded SEPARATELY from the exposure table, and
# the two are never merged server-side. `vulnerability_indicators` picks the
# index's inputs by scanning numeric columns, so a climate percentage or a
# built-up share joined onto the exposure frame would silently become a
# min-max-scaled term in a weighted mean - "this region's rivers rise faster,
# therefore its residents are more vulnerable". Context qualifies an exposure
# figure; it is not an ingredient of one.


def _context() -> pd.DataFrame:
    """The frozen context table, or a 404 explaining how to build one."""
    if not CONTEXT.exists():
        raise HTTPException(
            status_code=404,
            detail="No context table. Build one with `python scripts/build_context.py`, "
                   "which writes data/processed/context.parquet. It needs the hazard "
                   "rasters and the CDS NetCDFs `python -m src.fetch` downloads. The frozen "
                   "table is committed, so a checkout without it is older than that "
                   "commit; the rasters never are.",
        )
    return pd.read_parquet(CONTEXT)


#: Percentage points of spread between members above which a region's median
#: is a size nobody can quote. Set on a two-chain build of context.parquet,
#: 2071-2100: the two top regions of Europe, DE94H (+253%) and DK014 (+210%),
#: rested on chains 322 and 240 points apart, one reading +92% and the other
#: +414%. The median of two chains is their mean, so it hides that.
MODEL_SPREAD_PP = 100.0


def with_size_uncertain(df: pd.DataFrame) -> pd.DataFrame:
    """Add `ensemble_size_uncertain_<period>` for every period the table carries.

    True where the members, agreeing on the direction or not, lie more than
    `MODEL_SPREAD_PP` points apart: ranking regions by such a median puts model
    disagreement at the top of the list. A region with no measurement is False,
    not True: there is nothing to be uncertain about.

    The spread is the interquartile range (p75 - p25) of the members' medians
    once a region has more than two members, and the full range (max - min) at
    two. With sixteen members the full range is the gap between the two most
    extreme models, and it removed 666 of 1,198 regions from the 2071-2100
    ranking; at two members the quartiles sit inside the range and would hide
    exactly the split the flag exists to show.
    """
    out = df.copy()
    prefix = "ensemble_members_"
    for column in df.columns:
        if not column.startswith(prefix):
            continue
        suffix = column[len(prefix):]
        low = df.get(f"change_pct_ensemble_min_{suffix}")
        high = df.get(f"change_pct_ensemble_max_{suffix}")
        if low is None or high is None:
            continue
        spread = high - low
        p25 = df.get(f"change_pct_ensemble_p25_{suffix}")
        p75 = df.get(f"change_pct_ensemble_p75_{suffix}")
        if p25 is not None and p75 is not None:
            spread = spread.where(df[column] <= 2, p75 - p25)
        out[f"ensemble_size_uncertain_{suffix}"] = spread > MODEL_SPREAD_PP
    return out


def sign_column(df: pd.DataFrame, suffix: str) -> tuple[str, str]:
    """`(column, wording)` for the direction test a UI should apply to a period.

    The robust column (at least 80 % of members, IPCC AR6) where the table has
    it, the unanimous one otherwise: a table built before the robust column
    existed still reads, and says which rule it is reading.
    """
    robust = f"ensemble_robust_on_sign_{suffix}"
    if robust in df.columns:
        return robust, "at least 80 % of the members agree"
    return f"ensemble_agrees_on_sign_{suffix}", "every chain agrees"


def climate_periods(df: pd.DataFrame) -> list[dict]:
    """One summary per CDS period present, with what licenses a sentence about it.

    `scripts/build_context.py` suffixes every climate column with its period, so
    the periods on offer are read off the column names rather than hardcoded: a
    period added to the build appears here without this file being touched.

    The figures travel together because none of them is readable alone:

    - `median_change_pct` is the median OF the per-region ensemble medians, so it
      is a direction and a size, never a projected discharge. A relative change
      against a near-zero reference discharge is unbounded, which is why this is
      a median and not a mean.
    - `members` is how many model chains the period actually has, read off the
      table rather than assumed. Measured on `data/processed/context.parquet`
      2026-10-25: all three periods carry **16** chains (eight simulations
      through two hydrological models) on the 1,198 regions that were measured
      at all, and 0 on the other 147. The fixture in `tests/test_api.py` that
      uses one chain for 2071-2100 exercises the branch below; it does not
      describe the archive.
    - `regions_agreeing_on_sign` is the count a reader must see before writing
      "river discharge increases here". At one member it is 0 by construction -
      `src.climate.ensemble_change_by_region` refuses to call a single member
      agreement with itself - so `single_member` says WHY it is zero. Without it
      a one-member period reads as a period where the models disagree, which is
      a different and wrong claim.
    - `regions_robust_on_sign` counts the regions where at least 80 % of the
      members point the same way (`src.climate.ROBUST_SHARE`, the IPCC AR6
      convention). With sixteen members unanimity is a far stricter test than
      with two, so this is the count the docs quote and the unanimous one
      travels beside it.
    - `regions_size_uncertain` counts the regions whose members lie more than
      `model_spread_pp` points apart (see `with_size_uncertain`): agreeing on the
      direction, not on how much. Both UIs leave them out of the ranking.
    """
    periods: list[dict] = []
    flagged = with_size_uncertain(df)
    prefix = "ensemble_members_"
    for column in df.columns:
        if not column.startswith(prefix):
            continue
        suffix = column[len(prefix):]
        median = df.get(f"change_pct_ensemble_median_{suffix}")
        agrees = df.get(f"ensemble_agrees_on_sign_{suffix}")
        robust = df.get(f"ensemble_robust_on_sign_{suffix}")
        measured = median.notna() if median is not None else pd.Series([], dtype=bool)
        members = int(df[column].max()) if len(df) else 0
        periods.append({
            "period": suffix.replace("_", "-"),
            "members": members,
            "single_member": members <= 1,
            "regions_measured": int(measured.sum()),
            "median_change_pct": (
                float(median[measured].median()) if bool(measured.any()) else None
            ),
            "regions_agreeing_on_sign": int(agrees.sum()) if agrees is not None else 0,
            "regions_robust_on_sign": int(robust.sum()) if robust is not None else 0,
            "regions_size_uncertain": int(
                flagged.get(f"ensemble_size_uncertain_{suffix}", pd.Series([], dtype=bool)).sum()
            ),
            "model_spread_pp": MODEL_SPREAD_PP,
        })
    return sorted(periods, key=lambda entry: entry["period"])


@app.get("/api/context")
def context() -> dict:
    """Per-region context: future climate, exposed built-up surface, shared basins.

    Everything served here qualifies an exposure figure without being one - see
    the note above `_context` for why it is a separate table and not extra
    columns on the exposure frame.

    The climate block is the only forward-looking layer in the kit and the one a
    reader will over-read, so `climate_periods` travels with every response
    instead of being something a caller has to think to ask for.
    """
    df = with_size_uncertain(_context())
    key = _region_key(df)
    records = json.loads(df.to_json(orient="records"))  # NaN -> null, which JSON can carry
    # The built-up figures are measured at ONE return period, which the column
    # names it in. Serving the number without the period invites it to be read
    # against a different scenario's exposure count.
    built_prefix = "built_share_exposed_rp"
    built_rp = next(
        (int(c[len(built_prefix):]) for c in df.columns if c.startswith(built_prefix)),
        None,
    )
    return {
        "key": key,
        "regions": int(df[key].nunique()),
        "rows": records,
        "climate_periods": climate_periods(df),
        "built_up_return_period": built_rp,
        "frozen_at": datetime.fromtimestamp(CONTEXT.stat().st_mtime, timezone.utc).isoformat(),
    }


class VulnerabilityRequest(BaseModel):
    indicators: list[str] = Field(min_length=1)
    perturbation: float = Field(default=0.3, ge=0.0, le=0.9)
    top_n: int = Field(default=10, ge=1, le=100)
    # Which scenario the ranking is built on. Omitted means "the server picks the
    # rarest period and says so", never "all of them" - see `_one_return_period`.
    return_period: int | None = None


@app.post("/api/vulnerability")
def vulnerability(req: VulnerabilityRequest) -> dict:
    """Composite index plus the sensitivity that says which ranks survive it.

    The sensitivity is not optional here. A composite index is a value judgement
    wearing a number, and a rank that moves when the weights move is an artefact,
    not a finding.

    The ranking is built on ONE return period, and the response names it. The
    table holds one row per region per period, so narrowing has to happen before
    the index is computed: `exposed_pop` is usually one of the weighted
    indicators, it is min-max scaled across the rows present, and the order of the
    top rows does change between periods. An unstated period is therefore a silent
    answer to "who do we help first".
    """
    df = _table()
    key = _region_key(df)
    # A client written before the units rename still sends `poverty_rate`. It is
    # answered under the current name and told so in `renamed`, for one release,
    # rather than refused as an unknown indicator.
    renamed = {c: LEGACY_COLUMNS[c] for c in req.indicators if c in LEGACY_COLUMNS}
    req = req.model_copy(update={
        "indicators": list(dict.fromkeys(renamed.get(c, c) for c in req.indicators))
    })
    missing = [c for c in req.indicators if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown indicators: {missing}")
    scenario = [c for c in req.indicators if c in NON_INDICATOR_COLUMNS]
    if scenario:
        raise HTTPException(
            status_code=400,
            detail=f"Not vulnerability indicators: {scenario}. These describe the "
                   "flood scenario, not the people exposed to it.",
        )
    # The accept list is the offer list: a key or a text column cannot be
    # min-max scaled, and one stored as a string ranked every region at zero.
    offered = vulnerability_indicators(df)
    not_numeric = [c for c in req.indicators if c not in offered]
    if not_numeric:
        raise HTTPException(
            status_code=400,
            detail=f"Not numeric indicators: {not_numeric}. Pick from {offered}.",
        )

    df, period, defaulted = _one_return_period(df, req.return_period)
    ranked = sensitivity(
        # Within one period the table already holds one row per region, so this is
        # a guard against a table that repeats a region for some other reason. It
        # cannot decide which return period the ranking is built on, as it would
        # silently if the whole table were passed: it keeps the first row per
        # region, and the periods are concatenated rarest-last.
        df.drop_duplicates(subset=[key]),
        {c: 1.0 for c in req.indicators},
        perturbation=req.perturbation,
        top_n=req.top_n,
    )
    columns = [c for c in (key, *req.indicators, "vulnerability", "top_n_frequency", "confidence")
               if c in ranked.columns]
    body = {
        "key": key,
        "return_period": period,
        "defaulted_return_period": defaulted,
        "rows": json.loads(ranked[columns].to_json(orient="records")),
        "robust": int((ranked["confidence"] == "robust").sum()),
        "total": len(ranked),
    }
    if renamed:
        body["renamed"] = renamed
    return body


@app.get("/api/search")
def search(q: str, k: int = Query(default=5, ge=1, le=rag.MAX_PASSAGES)) -> dict:
    """Retrieve supporting passages, or report the refusal.

    An empty `passages` with `refused: true` is a result, not an error: the corpus
    being silent is the honest answer, and the UI shows it as such.
    """
    passages = rag.search(q, k=k)
    return {"question": q, "passages": passages, "refused": not passages}


def _upstream_failure(exc: Exception) -> str:
    """The 502 detail for a model call that failed, with the exception logged here.

    Only the exception's class reaches the client. Its message is written by the
    provider SDK or the HTTP stack and can carry a URL, a local path or part of a
    request, so it goes to the server log, where whoever runs the service reads it.
    """
    log.warning("model call failed", exc_info=exc)
    return (f"No model reachable ({type(exc).__name__}). Retry, or check the "
            "provider; the server log has the details.")


def _public_token_report(df: pd.DataFrame) -> dict:
    """`token_report` for an HTTP response: the unavailable reason stays server-side.

    The reason quotes tiktoken's exception, which names the cache path under the
    system temp dir or the URL it failed to fetch. The local UI shows it as is;
    a client of the API only needs to know that nothing was measured.

    The response is a new dict built from the count keys, not the report with
    its reason overwritten, so the exception text has no path to the client at
    all - which is also what lets CodeQL (py/stack-trace-exposure) see it.
    """
    report = token_report(df, "exposure")
    public = {k: report[k] for k in ("toon_tokens", "json_tokens", "saving_pct", "available")}
    if not report["available"]:
        log.warning("token report unavailable: %s", report["reason"])
        public["reason"] = "tiktoken unavailable; the server log has the details."
    return public


class DraftRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # An upper bound: the prompt budget usually cuts the table shorter.
    rows: int = Field(default=200, ge=1, le=2000)
    return_period: int | None = None


@app.post("/api/draft")
def draft(req: DraftRequest) -> dict:
    """One LLM call over the frozen table and the retrieved passages.

    Returns the draft **with its verification**, never on its own: the grounding
    score, any invalid citation, the numbers no source holds and the sentences
    citing nothing travel with the text, so the human deciding whether to
    approve it is deciding informed. The table note and the table are a source
    for numbers - the model was handed them - but the question is not: a figure
    that only the asker typed is not evidence.
    """
    _refuse_if_hosted("Drafting")
    passages = rag.search(req.question, k=5)
    if not passages:
        return {"refused": True, "draft": None, "passages": []}

    # One scenario, the same rule as every other route: the periods are nested,
    # so a table mixing them is no reading the brief can quote. Then ranked by
    # share, because the rows have to be chosen by something and file order
    # (Albania to Germany at the 10-year period) is not a criterion.
    df, period, _ = _one_return_period(_table(), req.return_period)
    key = _region_key(df)
    regions = df[key].nunique()
    # Without a population there is no share, so the rows keep file order and the
    # note below must not claim a ranking it did not make.
    ranked = {"exposed_pop", "total_pop"} <= set(df.columns)
    if ranked:
        df = df.assign(exposed_share=df["exposed_pop"] / df["total_pop"]).sort_values(
            "exposed_share", ascending=False
        )
    # flatten() before encoding, because it is the only thing that drops
    # `geometry` - and the frozen table is saved from a GeoDataFrame, so the
    # column is there. A polygon is thousands of tokens of coordinates the model
    # can do nothing with, times `rows`, and it would be the bulk of the prompt.
    #
    # Then cut to the provider's per-minute budget, which `rag` owns: past it
    # Groq answers 413 and every draft falls to the small local model.
    fenced = rag.fence(passages)
    note = (
        (f"TABLE NOTE: the most exposed of {regions} regions" if ranked
         else f"TABLE NOTE: rows from {regions} regions, in file order")
        + (f" at the 1-in-{period} year return period" if period else "")
        + (", ranked by the share of their own population exposed" if ranked else "")
        + ". This is an extract, not the whole table: do not state a European total "
        "or a count of regions from it."
    )
    head = f"QUESTION: {req.question}\n\n{note}\nTABLE:\n"
    budget = rag.PROMPT_CHAR_BUDGET - len(rag.SYSTEM_PROMPT) - len(head) - len(fenced) - 2
    df = fit_rows(flatten(df.head(req.rows)), "exposure", max(budget, 0))
    table = to_toon(df, "exposure")
    prompt = rag.draft_prompt(req.question, f"{note}\nTABLE:\n{table}", fenced)
    try:
        text = rag.complete(prompt)
    except Exception as exc:
        # 502, not 500: the failure is upstream, and the status code is the only
        # thing telling the client it is the model that is unreachable rather
        # than this service that is broken.
        raise HTTPException(status_code=502, detail=_upstream_failure(exc)) from exc
    if text is None:
        # The provider can answer with message.content: null, which `rag.complete`
        # passes straight through. Verification below runs regexes over the text,
        # so a None would resurface as a TypeError out of grounding_score and
        # reach the client as a 500 - our bug, for the provider's empty turn.
        raise HTTPException(
            status_code=502,
            detail="The model returned an empty completion. Nothing was drafted, so "
                   "there is nothing to verify: retry, or check the provider.",
        )

    reference = f"{note}\n{table}"
    check = rag.verify(text, passages, reference)
    return {
        "refused": False,
        "draft": text,
        "passages": passages,
        "grounding": check["grounding"],
        "invalid_citations": check["invalid_citations"],
        "unsupported_numbers": check["unsupported_numbers"],
        "uncited_sentences": check["uncited_sentences"],
        # What /api/approve needs to re-check an edit against the same sources:
        # a client sends it back with the passages and the edited text.
        "table_text": reference,
        "tokens": _public_token_report(df),
        "return_period": period,
        "prompt_rows": len(df),
        "ranked": ranked,
    }


class AskRequest(BaseModel):
    #: Exactly one of the two. `spec` is the route with no model behind it, so the
    #: table stays queryable with no key and no local model running.
    question: str | None = Field(default=None, min_length=1, max_length=nlquery.MAX_QUESTION_CHARS)
    spec: dict | None = None


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    """A question about the exposure table, answered by pandas from a validated spec.

    The model only translates the question into a query spec - columns, filters,
    one sort key, a limit, one return period - and `src.nlquery` refuses any
    column or operator outside its whitelist before pandas runs it. So every
    figure in the answer is a value of the frozen table, and the definitions of
    the columns used travel with the rows.

    A spec that breaks a rule comes back as **422** with the rule and the spec,
    not as an empty 200: "no region matches" and "the question was not
    understood" must not look alike.
    """
    if (req.question is None) == (req.spec is None):
        raise HTTPException(status_code=400, detail="Send exactly one of `question` or `spec`.")
    if req.question is not None:
        # Only the free-text form calls a model; a `spec` runs on pandas alone
        # and stays available in the hosted demo.
        _refuse_if_hosted("Asking in free text")
    df = _table()
    try:
        if req.spec is not None:
            answer = nlquery.execute(df, req.spec)
        else:
            answer = nlquery.ask(req.question, df)
    except nlquery.SpecError as exc:
        raise HTTPException(status_code=422, detail=f"Query refused: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=_upstream_failure(exc) + " A query `spec` can still be sent without a model.",
        ) from exc
    return {"question": req.question, **answer.as_dict()}


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    #: A key of `translate.LANGUAGES`, validated there rather than here so the
    #: refusal message names the languages that exist.
    language: str = Field(min_length=2, max_length=5)


@app.post("/api/translate")
def translate_section(req: TranslateRequest) -> dict:
    """One section into one language, with the figures checked against the source.

    The check is the reason this is a route rather than a prompt. A translation
    may change every word and may not change a single number, and a model asked
    for French will localise `29,727,887` to `29 727 887` - correct - as readily
    as it will write `29,7 millions`, round `16.9%` or move a `[S2]`. None of
    that looks wrong on the page.

    A translation that failed the check comes back as **422, not 200 with a
    warning**: the client must not be able to render it by ignoring a field. The
    English section is unaffected either way - it stays the record, because it is
    the text whose figures were checked against the table.
    """
    _refuse_if_hosted("Translation")
    try:
        result = translate.translate(req.text, req.language)
    except ValueError as exc:
        # A language nobody offers, or nothing to translate. The client sent a bad
        # request; 400 rather than 422 so it is distinguishable from a translation
        # that was produced and rejected.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except translate.TranslationFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Upstream, like `/api/draft`: the model is unreachable, not this service.
        raise HTTPException(status_code=502, detail=_upstream_failure(exc)) from exc
    return {
        "text": result.text,
        "language": result.language,
        "language_name": translate.LANGUAGES[result.language],
        "numbers_checked": result.numbers,
        "citations_checked": result.citations,
    }


@app.get("/api/languages")
def languages() -> dict:
    """The target languages, so the UI never hardcodes a list that can drift.

    English is absent on purpose: it is the source, and offering it invites a
    round trip, which is how a figure quietly changes.
    """
    return {"languages": [
        {"code": code, "name": name}
        for code, name in sorted(translate.LANGUAGES.items())
    ]}


# Cap on one approved section: generous for a brief, but a client cannot fill the
# disk with a single request.
MAX_APPROVED_CHARS = 50_000


class ApproveRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_APPROVED_CHARS)
    #: The passages and table text the draft was written from, as `/api/draft`
    #: returned them. Optional, so a client that sends text alone still
    #: approves; without them only the citation range and the uncited
    #: sentences can be checked, and the record says so.
    passages: list[dict] | None = Field(default=None, max_length=rag.MAX_PASSAGES)
    table_text: str = Field(default="", max_length=rag.PROMPT_CHAR_BUDGET)


def _check_approver(token: str | None) -> None:
    """Refuse an approval without the configured token.

    Approve is the only route that writes, so it is the one worth guarding.
    With FLOOD_APPROVE_TOKEN set, the caller must send it in X-Approve-Token
    (compared in constant time, so timing does not leak it). Without it, any
    caller that reaches the API may approve: the compose file publishes the API
    on 127.0.0.1 only, so that is this machine. The client address is not
    checked, because behind Docker's port-forward every caller, the React UI
    on the host included, arrives from the bridge gateway and not from loopback.
    """
    expected = os.environ.get("FLOOD_APPROVE_TOKEN")
    if expected and (not token or not secrets.compare_digest(token.encode(), expected.encode())):
        raise HTTPException(status_code=403, detail="Invalid or missing X-Approve-Token.")


@app.post("/api/approve")
def approve(
    req: ApproveRequest,
    x_approve_token: str | None = Header(default=None),
) -> dict:
    """Append approved text to the brief. The only route that writes to it.

    The text is stored exactly as the human left it. It is deliberately not sent
    back to the model for polishing, because that hands the last word to the
    machine on a document a public authority may act on.

    The checks run again on THIS text, not on the model's draft: the human may
    have edited a figure or a marker in, and what is written is what has to be
    verified. One finding refuses (**422**) - a citation marker outside the
    sources, which points the reader at a passage that does not exist and is
    never right. The others (numbers no source holds, sentences citing nothing)
    can be a reasonable human edit, so they are written into the record beside
    the text and returned, and the decision stays the human's.
    """
    _refuse_if_hosted("Approving")
    _check_approver(x_approve_token)
    passages = None
    if req.passages is not None:
        passages = [{"text": str(p.get("text", ""))} for p in req.passages]
    check = rag.verify(req.text, passages, req.table_text)
    if check["invalid_citations"]:
        markers = ", ".join(f"[S{n}]" for n in check["invalid_citations"])
        scope = (f"{len(passages)} passages were supplied" if passages is not None
                 else f"no draft is ever given more than {rag.MAX_PASSAGES} passages")
        raise HTTPException(
            status_code=422,
            detail=f"Not approved: {markers} cites no source ({scope}). Fix or "
                   "remove the marker, then approve again.",
        )
    APPROVED.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    with APPROVED.open("a", encoding="utf-8") as handle:
        handle.write(f"\n\n<!-- approved {stamp}; {rag.verdict_line(check)} -->\n{req.text}\n")
    return {"written_to": APPROVED.name, "approved_at": stamp, "verification": check}


# Single-process production mode, mounted last so /api/* always wins.
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
