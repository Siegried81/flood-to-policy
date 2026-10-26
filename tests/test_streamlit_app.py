"""Tests for the Streamlit UI, driven through `streamlit.testing.v1.AppTest`.

The app is a script, not a library, so it is exercised by running it: AppTest
executes `app/streamlit_app.py` in-process and exposes the widgets and the text
it produced. That is what makes the failures worth pinning testable at all -
every one of them was a wrong *label* or a wrong *subset*, visible only in the
rendered page.

The frozen table is injected by patching `pandas.read_parquet` plus the two
`Path` calls the app makes about the cache file, rather than by writing into
`data/processed/`: the real table is another agent's output and a test must not
touch it. Nothing here reaches the network - `src.rag` is patched wherever the
draft tab would call a model.
"""

from __future__ import annotations

import os
import pathlib
import time
from contextlib import contextmanager
from unittest.mock import patch

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from scripts import build_geometry
from src import rag, svgmap, usage_log
from tests.test_api import _context_table, _nested_table

#: What the patched download answers, so a test can check the page relays it.
OFFLINE = "could not download the GISCO boundaries: offline in this test"

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "streamlit_app.py"
CACHE = (ROOT / "data" / "processed" / "exposure.parquet").resolve()
CONTEXT = (ROOT / "data" / "processed" / "context.parquet").resolve()
GEOMETRY = (ROOT / "data" / "processed" / "regions.geojson").resolve()


def _key(path) -> str:
    """A comparable form of a path that touches neither the filesystem nor
    `pathlib`.

    Both matter. `Path.exists` and `Path.stat` are patched below, so anything
    these replacements call must not route back through a `Path` method:
    `self.resolve()` did, and the recursion was invisible on Python 3.14 while
    blowing the stack on 3.12 - a green suite locally and 22 failures in CI.
    `os.path.abspath` is pure string work against the cwd, and `normcase` makes
    the comparison hold on a case-insensitive filesystem.
    """
    return os.path.normcase(os.path.abspath(os.fspath(path)))


_CACHE_KEY = _key(CACHE)
_CONTEXT_KEY = _key(CONTEXT)
_GEOMETRY_KEY = _key(GEOMETRY)

_real_exists = pathlib.Path.exists
_real_stat = pathlib.Path.stat


class _Stat:
    """Just enough of a stat result for the freeze banner's mtime."""

    st_mtime = time.time()


@contextmanager
def _frozen(
    table: pd.DataFrame | None,
    context: pd.DataFrame | None = None,
    geometry: list[dict] | None = None,
):
    """Run the app against `table`, or against no table at all when None.

    `context` is the second frozen table, and it defaults to absent for a reason
    that is not tidiness. The app reads two parquets now, and the patch below
    replaces `pd.read_parquet` for the whole process: a replacement that ignored
    the path would hand the exposure table to `load_context`, and the context tab
    would render exposure columns under climate headings. Worse, `Path.exists`
    falls through to the real filesystem for any path it does not recognise, so
    on the dev machine - where `data/processed/context.parquet` exists and CI's
    does not - the default would be "present" locally and "absent" on the runner,
    which is the shape of bug this harness exists to prevent. Both paths are
    therefore keyed explicitly, and `read_parquet` dispatches on which one it was
    asked for.

    `geometry` is the third artefact and defaults to absent for exactly the same
    reason: `data/processed/regions.geojson` exists on the dev machine and not on
    the runner, so a test that let `Path.exists` fall through to the real disk
    would draw a real choropleth of Europe locally and take the "nothing to
    draw" branch in CI. It is a list of GeoJSON features, not a frame, because
    that is what `svgmap.load_features` returns and what the app holds.
    """
    present = table is not None
    context_present = context is not None
    geometry_present = geometry is not None
    _ABSENT_WHEN = {
        _CACHE_KEY: lambda: present,
        _CONTEXT_KEY: lambda: context_present,
        _GEOMETRY_KEY: lambda: geometry_present,
    }

    def exists(self, *args, **kwargs):
        key = _key(self)
        if key == _CACHE_KEY:
            return present
        if key == _CONTEXT_KEY:
            return context_present
        if key == _GEOMETRY_KEY:
            return geometry_present
        return _real_exists(self, *args, **kwargs)

    def stat(self, *args, **kwargs):
        """Raises for an artefact this run declares absent, as the real one does.

        Not cosmetic. The loaders test for presence with `stat`, not `exists`,
        because `@st.cache_data` memoises a return value and a loader that
        checked `exists` itself cached the *absence*. A stand-in that answered
        every `stat` with a result reported all three artefacts present however
        the test had been set up.
        """
        key = _key(self)
        if key in _ABSENT_WHEN:
            if not _ABSENT_WHEN[key]():
                raise FileNotFoundError(2, "No such file or directory", str(self))
            return _Stat()
        return _real_stat(self, *args, **kwargs)

    def read_parquet(path, *args, **kwargs):
        return context if _key(path) == _CONTEXT_KEY else table

    def load_features(path, *args, **kwargs):
        return geometry if geometry is not None else []

    # load_exposure and load_context are both @st.cache_data with no arguments,
    # so their keys are constant across runs: without this the second test in a
    # session reads the first test's tables.
    # The app downloads the boundaries when the geometry is absent. Patched to a
    # failure so no test reaches GISCO, and so "absent" stays absent instead of
    # writing a real regions.geojson into data/processed/. cache_resource holds
    # that outcome for ten minutes, so it is cleared like cache_data.
    st.cache_data.clear()
    st.cache_resource.clear()
    with (
        patch.object(pathlib.Path, "exists", exists),
        patch.object(pathlib.Path, "stat", stat),
        patch.object(pd, "read_parquet", read_parquet),
        patch.object(svgmap, "load_features", load_features),
        patch.object(build_geometry, "ensure", lambda *a, **k: OFFLINE),
    ):
        yield


def _run(table, timeout: float = 60, context=None, geometry=None):
    with _frozen(table, context, geometry):
        return AppTest.from_file(str(APP), default_timeout=timeout).run()


def _texts(app_test) -> str:
    """Everything the page said, as one string, for "did it say so?" assertions."""
    parts = []
    for block in (app_test.info, app_test.caption, app_test.warning, app_test.error,
                  app_test.markdown, app_test.subheader):
        parts.extend(str(element.value) for element in block)
    return "\n".join(parts)


# --- no region identifier -------------------------------------------------------

def test_a_table_without_an_identifier_says_so_instead_of_raising():
    """The defect: the selectbox options list was empty, so `key` was None and the
    first `view[key]` raised a bare KeyError in the middle of the page.

    Every figure here is per region, so there is nothing to show - but that is a
    sentence, not a traceback.
    """
    table = _nested_table().drop(columns=["nuts_id"])
    app_test = _run(table)

    assert app_test.exception == []
    assert "No region identifier column" in _texts(app_test)
    # Stopped before the tabs: nothing downstream can read a key that is not there.
    assert app_test.tabs == []


def test_an_absent_table_still_explains_how_to_build_one():
    app_test = _run(None)
    assert app_test.exception == []
    assert "No exposure table yet" in _texts(app_test)


def test_an_absent_table_names_the_script_and_why_it_is_missing():
    """The warning named `exposure_by_return_period`, a library call. The frozen
    table is committed, so the machine that hits this is an old checkout or a
    container without the bind mount: say so, then name the script."""
    texts = _texts(_run(None))
    assert "scripts/build_exposure.py" in texts
    assert "git pull" in texts and "./data" in texts
    assert "exposure_by_return_period" not in texts


def test_either_identifier_spelling_is_accepted():
    """NUTS3 for Europe, LAU for a zoom: the column name differs by run.

    With one identifier present it is stated, not offered: a selectbox holding a
    single option asks the reader to choose and then gives them no choice.
    """
    table = _nested_table().rename(columns={"nuts_id": "lau_id"})
    app_test = _run(table)
    assert app_test.exception == []
    assert "`lau_id`" in _texts(app_test)
    assert not [b for b in app_test.selectbox if b.label == "Region identifier"]


def test_two_identifiers_are_offered_as_a_choice():
    """The other half: the selector has to come back when the table really does
    carry both, or a LAU zoom could never be read at NUTS3."""
    table = _nested_table()
    table["lau_id"] = table["nuts_id"] + "_01"
    app_test = _run(table)
    assert app_test.exception == []
    offered = [b for b in app_test.selectbox if b.label == "Region identifier"]
    assert offered and offered[0].options == ["nuts_id", "lau_id"]


# --- one indicator list, shared with the API ------------------------------------

def test_the_scenario_columns_are_not_offered_as_indicators():
    """The defect: this app excluded only `return_period`, so its default index
    weighted `annual_probability` in as a vulnerability indicator - "a more
    frequent flood makes residents more vulnerable" - while the API did not. Same
    frozen table, two different composite scores for the same region.
    """
    app_test = _run(_nested_table())
    offered = app_test.multiselect[0].options
    assert "annual_probability" not in offered
    assert "return_period" not in offered


def test_the_offered_indicators_are_exactly_the_api_offer_list():
    from api.main import vulnerability_indicators

    app_test = _run(_nested_table())
    assert app_test.multiselect[0].options == vulnerability_indicators(_nested_table())


def test_the_default_selection_matches_the_react_default():
    """Both UIs default to the head of the same list, so the first number a
    reader sees is the same number in either."""
    app_test = _run(_nested_table())
    assert app_test.multiselect[0].value == ["exposed_pop", "share_over_65"]


# --- the ranking's return period ------------------------------------------------

def test_the_ranking_is_built_on_the_selected_period_and_names_it():
    """The defect: `drop_duplicates` over the whole table kept the first row per
    region, and the periods are concatenated shortest-first, so the ranking was
    always RP10's - whatever the slider said - and nothing on the page mentioned a
    period at all.
    """
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        app_test.select_slider[0].set_value(500).run()
    said = _texts(app_test)
    assert "1-in-500 year" in said
    ranking = app_test.dataframe[-1].value
    assert ranking["nuts_id"].tolist() == ["BE31", "BE33", "BE32"]


def test_the_slider_opens_on_the_1_in_100_year_flood():
    """The brief and the pitch quote RP100, so the page opens on it, like the
    React UI; the rarest period is one move away, never the first figure seen."""
    app_test = _run(_nested_table())
    assert app_test.select_slider[0].value == 100
    assert "1-in-100 year" in _texts(app_test)


def test_a_table_without_rp100_opens_on_its_rarest_period():
    table = _nested_table()
    app_test = _run(table[table["return_period"] != 100])
    assert app_test.select_slider[0].value == 500


def test_moving_the_slider_moves_the_ranking():
    """The second-ranked region flips between RP10 and RP500 in this table, which
    is the whole reason the period has to be deliberate."""
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        app_test.select_slider[0].set_value(10).run()

    assert app_test.exception == []
    assert "1-in-10 year" in _texts(app_test)
    assert app_test.dataframe[-1].value["nuts_id"].tolist() == ["BE31", "BE32", "BE33"]


def test_the_map_and_the_ranking_read_the_same_period():
    """One control above the tabs, so a ranking cannot describe a different flood
    from the map on screen."""
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        app_test.select_slider[0].set_value(100).run()

    said = _texts(app_test)
    # The choropleth and the ranking carry the period in their own headings, so
    # a screenshot of either one states which flood it is.
    assert "Where the danger is — 1-in-100 year flood" in said
    assert "Ranked: share of residents exposed, 1-in-100 year flood" in said
    assert "Ranked on the **1-in-100 year** scenario" in said


def test_the_return_period_is_placed_in_the_directives_own_classes():
    """Article 6(3) of Directive 2007/60/EC names three scenarios and puts a
    number on one of them - (b) "medium probability (likely return period
    >= 100 years)". The page offered RP10 to RP500 and never said which class a
    period falls in, so a brief could call the 1-in-500 year flood whatever it
    liked. The caption has to quote the Article, carry the one figure it fixes,
    and say that the high and low classes are the kit's reading, not the law's.
    """
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        said = _texts(app_test)
        assert app_test.exception == []
        assert "Article 6(3)" in said
        assert "likely return period ≥ 100 years" in said
        # The default is RP100, the one class the Directive puts a number on.
        assert "RP100 is 'medium probability'" in said
        assert "the one class the Directive puts a number on" in said
        assert "is this kit's, not the Directive's" in said
        assert "fixes no return period for either class" in said
        # The fixture's periods, read off the table rather than restated.
        assert "Reading RP10 as 'high probability' (6(3)(c))" in said
        assert "RP500 as 'low probability / extreme' (6(3)(a))" in said

        app_test.select_slider[0].set_value(500).run()
        said = _texts(app_test)
        assert "RP500 is 'low probability / extreme'" in said

        app_test.select_slider[0].set_value(10).run()
        said = _texts(app_test)
        assert "RP10 is 'high probability'" in said
        assert "the kit's reading: the Directive fixes no return period" in said

    assert app_test.exception == []


def test_the_map_points_at_the_statutory_viewer():
    """The kit screens; the Member States' Floods Directive maps bind. The page
    has to say so under the map and name where the statutory maps are served -
    whether or not the polygons were built, because the claim it limits is the
    exposure figure and not the drawing."""
    features = [
        {"type": "Feature", "properties": {"nuts_id": code},
         "geometry": {"type": "Polygon", "coordinates": [[
             [lon, 50.0], [lon + 1, 50.0], [lon + 1, 51.0], [lon, 51.0], [lon, 50.0],
         ]]}}
        for lon, code in enumerate(_nested_table()["nuts_id"].unique(), start=4)
    ]
    for geometry in (None, features):  # absent as in CI, then drawn
        app_test = _run(_nested_table(), geometry=geometry)
        said = _texts(app_test)
        assert app_test.exception == []
        assert "never the statutory map" in said
        assert "https://discomap.eea.europa.eu/floodsviewer/" in said
        assert "WISE-Freshwater" in said


def test_the_map_says_how_to_build_geometry_it_does_not_have():
    """`scripts/build_geometry.py` is a third build, and `data/` is not
    committed. With no polygons the first scored deliverable is missing, so the
    page has to name the command rather than render an empty box."""
    app_test = _run(_nested_table())  # geometry defaults to absent, as in CI
    said = _texts(app_test)
    assert app_test.exception == []
    assert "scripts/build_geometry.py" in said
    # The download was tried and why it failed is on the page, not swallowed.
    assert "offline in this test" in said
    # And the ranking still works without it.
    assert "Ranked: share of residents exposed" in said


def test_the_choropleth_colours_the_regions_and_greys_the_unmeasured():
    """The deliverable itself. A region the raster never covered must not be
    painted the colour of zero - `_nested_table` carries one with no figure."""
    features = [
        {"type": "Feature", "properties": {"nuts_id": code},
         "geometry": {"type": "Polygon", "coordinates": [[
             [lon, 50.0], [lon + 1, 50.0], [lon + 1, 51.0], [lon, 51.0], [lon, 50.0],
         ]]}}
        for lon, code in enumerate(_nested_table()["nuts_id"].unique(), start=4)
    ]
    with _frozen(_nested_table(), geometry=features):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()

    said = _texts(app_test)
    assert app_test.exception == []
    assert "scripts/build_geometry.py" not in said
    assert "regions coloured" in said
    assert "not measured, never a measured zero" in said.replace("*", "")
    assert "EPSG:3035" in said, "the reader is told it is equal-area"


def test_the_svg_actually_reaches_the_page_not_just_the_caption():
    """The hole the rest of this section left open.

    Every other map test asserts on the caption, and a caption is written
    whatever happened to the markup. `st.html` sanitises its body with DOMPurify
    and silently dropped the entire <svg> while the page went on reporting
    "1,338 regions coloured" underneath the empty space. Reading the iframe's
    srcdoc is the only assertion here that can tell a drawn map from a
    confident sentence about one.

    A titled `<path>`, not a fill colour and not a bare `<title>`: the legend
    swatches carry a fill and, since they name their quantile rank, a tooltip of
    their own - so counting either counts the legend too, a mistake this test
    was written around twice.
    """
    table = _nested_table()
    features = [
        {"type": "Feature", "properties": {"nuts_id": code},
         "geometry": {"type": "Polygon", "coordinates": [[
             [lon, 50.0], [lon + 1, 50.0], [lon + 1, 51.0], [lon, 51.0], [lon, 50.0],
         ]]}}
        for lon, code in enumerate(table["nuts_id"].unique(), start=4)
    ]
    with _frozen(table, geometry=features):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()

    assert app_test.exception == []
    frames = app_test.get("iframe")
    assert len(frames) == 1, f"{len(frames)} iframes; the map is the only one"
    markup = frames[0].srcdoc
    assert "<svg" in markup, "the map was enqueued as something other than SVG"
    import re

    titled_paths = len(re.findall(r"<path [^>]*><title>", markup))
    assert titled_paths == len(features), (
        f"{titled_paths} titled paths for {len(features)} regions"
    )
    # And every region is reachable by name, which is what the hover promises.
    for feature in features:
        assert feature["properties"]["nuts_id"] in markup


def test_the_map_can_be_coloured_by_climate_horizon(monkeypatch):
    """The second layer, and the one caveat that has to travel with it: the
    climate columns are a change in river DISCHARGE, so the map must never be
    read as a future headcount. A horizon with the chains disagreeing on the
    sign is hatched rather than painted flat or greyed - measured and
    directionless is a third state, not an absence."""
    table = _nested_table()
    context = _context_table()
    features = [
        {"type": "Feature", "properties": {"nuts_id": code},
         "geometry": {"type": "Polygon", "coordinates": [[
             [lon, 50.0], [lon + 1, 50.0], [lon + 1, 51.0], [lon, 51.0], [lon, 50.0],
         ]]}}
        for lon, code in enumerate(context["nuts_id"], start=4)
    ]
    with _frozen(table, context=context, geometry=features):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        layer = next(r for r in app_test.radio if "Colour the map by" in r.label)
        layer.set_value("Change in river discharge, by horizon").run()
        horizon = next(r for r in app_test.radio if r.label == "Horizon")
        horizon.set_value("2041-2070").run()

    said = _texts(app_test)
    assert app_test.exception == []
    assert "change in discharge, not in depth or extent" in said.lower()
    assert "never a future headcount" in said
    # The fixture's 2041-2070 horizon has one of three regions disagreeing, and
    # carries no robust column, so the caption names the unanimous fallback.
    assert "**2 regions** agreeing" in said
    assert "**1** hatched (measured, not unanimous)" in said
    assert "robust" not in said.split("model chain(s)")[1].split("grey")[0]
    assert "**0** grey (not measured)" in said
    assert "every chain agrees" in said
    assert "model chain(s)" in said


def test_the_climate_caption_counts_robust_hatched_and_unmeasured(monkeypatch):
    """With the robust column present, the caption names the 80 % rule and
    splits the regions three ways: robust, hatched, grey. The three counts add
    up to the regions on the map, so "the rest" no longer hides the unmeasured
    ones inside the hatched."""
    table = _nested_table()
    context = _context_table()
    context["ensemble_robust_on_sign_2041_2070"] = [True, False, False]
    context.loc[2, "change_pct_ensemble_median_2041_2070"] = None
    features = [
        {"type": "Feature", "properties": {"nuts_id": code},
         "geometry": {"type": "Polygon", "coordinates": [[
             [lon, 50.0], [lon + 1, 50.0], [lon + 1, 51.0], [lon, 51.0], [lon, 50.0],
         ]]}}
        for lon, code in enumerate(context["nuts_id"], start=4)
    ]
    with _frozen(table, context=context, geometry=features):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        layer = next(r for r in app_test.radio if "Colour the map by" in r.label)
        layer.set_value("Change in river discharge, by horizon").run()
        horizon = next(r for r in app_test.radio if r.label == "Horizon")
        horizon.set_value("2041-2070").run()

    said = _texts(app_test)
    assert app_test.exception == []
    assert "**1 regions** robust" in said
    assert "**1** hatched (measured, not robust)" in said
    assert "**1** grey (not measured)" in said
    assert "at least 80 % of the members agree" in said


def test_the_climate_layer_is_absent_without_a_context_table():
    """It is a second build. With only the exposure table there is no horizon to
    offer, and offering one that colours nothing would be worse than not
    offering it."""
    features = [
        {"type": "Feature", "properties": {"nuts_id": code},
         "geometry": {"type": "Polygon", "coordinates": [[
             [4.0, 50.0], [5.0, 50.0], [5.0, 51.0], [4.0, 51.0], [4.0, 50.0],
         ]]}}
        for code in _nested_table()["nuts_id"].unique()
    ]
    app_test = _run(_nested_table(), geometry=features)  # context absent, as in CI
    assert app_test.exception == []
    assert not [r for r in app_test.radio if "Colour the map by" in r.label]


def test_the_total_is_one_period_not_the_sum_of_all_three():
    """1500 + 6000 + 14000 = 21500 is the core floodplain counted three times.

    The page opens on RP100, so the total is that period's 6,000 alone."""
    app_test = _run(_nested_table())
    totals = {m.label: m.value for m in app_test.metric}
    assert totals["Exposed, total"] == "6,000"
    assert totals["Regions covered"] == "3"


def test_a_missing_exposure_column_shows_a_dash_not_a_zero():
    """Another agent owns the exposure columns. An absent `exposed_pop` must not
    render as a measured zero."""
    app_test = _run(_nested_table().drop(columns=["exposed_pop"]))
    assert app_test.exception == []
    totals = {m.label: m.value for m in app_test.metric}
    assert totals["Exposed, total"] == "—"
    assert totals["Not measured"] == "—"


def test_an_unknown_column_rides_along_without_changing_a_figure():
    """A numeric column this UI has never heard of is offered, and no total moves.

    The page must not have to be edited every time src/exposure.py grows a
    column: anything numeric and not excluded is offered as an indicator, and
    the exposure figures are read by name so an extra column cannot move them.
    """
    table = _nested_table()
    table["share_without_a_car"] = 0.42
    app_test = _run(table)
    assert app_test.exception == []
    assert "share_without_a_car" in app_test.multiselect[0].options
    assert {m.label: m.value for m in app_test.metric}["Exposed, total"] == "6,000"


def test_the_raster_coverage_columns_are_not_offered_as_vulnerability_indicators():
    """`hazard_coverage` and `cells_counted` qualify a figure; they are not one.

    Both are numeric and both sit before `exposed_pop` in the table, so while
    they were merely "unknown columns" they led the offered list - and the
    default selection is its first three, which built the composite index out
    of raster bookkeeping instead of out of the people living there.
    """
    table = _nested_table()
    table["cells_counted"] = 4
    table["hazard_coverage"] = 0.42
    app_test = _run(table)
    assert app_test.exception == []
    offered = app_test.multiselect[0].options
    assert "cells_counted" not in offered
    assert "hazard_coverage" not in offered
    assert {m.label: m.value for m in app_test.metric}["Exposed, total"] == "6,000"


def test_a_table_without_periods_still_renders():
    """One row per region already, so there is no slider and nothing to narrow."""
    table = _nested_table().query("return_period == 100").drop(
        columns=["return_period", "annual_probability"]
    )
    app_test = _run(table)
    assert app_test.exception == []
    assert app_test.select_slider == []
    assert {m.label: m.value for m in app_test.metric}["Exposed, total"] == "6,000"


# --- the draft tab ---------------------------------------------------------------

@contextmanager
def _stubbed_model(monkeypatch, reply):
    """A retrieval hit and a captured prompt, with no network call."""
    seen = {}

    def complete(prompt, *args, **kwargs):
        seen["prompt"] = prompt
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(
        rag, "search",
        lambda q, k=5: [
            {"text": "Flood risk management plans.", "source": "dir.html", "score": 9.0}
        ],
    )
    monkeypatch.setattr(rag, "complete", complete)
    yield seen


def _ask(table, question="flood risk plans?"):
    """Type the question and press Draft, returning the finished AppTest."""
    app_test = AppTest.from_file(str(APP), default_timeout=60).run()
    box = next(t for t in app_test.text_input if "decision-maker" in t.label)
    box.set_value(question).run()
    next(b for b in app_test.button if b.label == "Draft this section").click().run()
    return app_test


def test_geometry_never_reaches_the_prompt(monkeypatch):
    """The defect: `to_toon` was called straight on the frozen table, and
    `flatten` is the only thing that drops `geometry`. A polygon is thousands of
    tokens of coordinates the model can do nothing with, times 200 rows.
    """
    table = _nested_table()
    table["geometry"] = [b"\x01\x06\x00\x00" * 100] * len(table)

    with _frozen(table), _stubbed_model(monkeypatch, "A sentence [S1].") as seen:
        app_test = _ask(table)

    assert app_test.exception == []
    block = seen["prompt"].split("exposure[", 1)[1].split("\n\n", 1)[0]
    assert "geometry" not in block
    assert "\\x01" not in block


def test_the_prompt_table_is_the_selected_scenario_only(monkeypatch):
    """The defect: this tab sent `exposure.head(200)` — the whole nine-period
    table in FILE order, so Albania through Germany at the 10-year period
    whatever the reader had selected above. The page's own contract is one
    scenario everywhere, and a brief drafted against a different flood from the
    map beside it is the failure the freeze exists to prevent."""
    table = _nested_table()
    with _frozen(table), _stubbed_model(monkeypatch, "A sentence [S1].") as seen:
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        app_test.select_slider[0].set_value(100).run()
        box = next(t for t in app_test.text_input if "decision-maker" in t.label)
        box.set_value("flood risk plans?").run()
        next(b for b in app_test.button if b.label == "Draft this section").click().run()

    assert app_test.exception == []
    prompt = seen["prompt"]
    assert "1-in-100 year return period" in prompt
    # The column index is read off the TOON header rather than guessed: the
    # header is `exposure[N]{col,col,...}:` and the row order is the frame's.
    encoded = prompt.split("exposure[", 1)[1]
    columns = encoded.split("{", 1)[1].split("}", 1)[0].split(",")
    at = columns.index("return_period")
    periods = {
        row.strip().split(",")[at]
        for row in encoded.splitlines()[1:]
        if row.startswith("  ")
    }
    assert periods == {"100"}, f"one period only, got {periods}"


def test_the_prompt_says_the_table_is_a_ranked_extract(monkeypatch):
    """A model handed forty rows with no label quotes a European total from them.
    The row count in the TOON header says forty; only the sentence beside it says
    forty OF how many, and ranked by what."""
    table = _nested_table()
    with _frozen(table), _stubbed_model(monkeypatch, "A sentence [S1].") as seen:
        _ask(table)

    prompt = seen["prompt"]
    assert "ranked extract" in prompt
    assert "do not state a European total" in prompt
    assert "ranked by the share of their own" in prompt


def test_the_prompt_stays_inside_the_provider_token_budget(monkeypatch):
    """The bug a jury would have seen: Groq caps `openai/gpt-oss-120b` at 8,000
    tokens per MINUTE on the on-demand tier and answers HTTP 413 above it, while
    the model's context is 131k. Measured on the real table, `head(200)` built a
    29,718-character prompt — about 14,900 tokens — so the draft tab could never
    succeed on that tier. TOON runs about 2.05 characters per token."""
    table = _nested_table()
    with _frozen(table), _stubbed_model(monkeypatch, "A sentence [S1].") as seen:
        _ask(table)

    assert len(seen["prompt"]) <= rag.PROMPT_CHAR_BUDGET, (
        f"{len(seen['prompt'])} chars is about {len(seen['prompt']) / 2.05:.0f} "
        "tokens, and the completion still needs room under 8,000"
    )


def test_the_draft_survives_a_context_table_being_present(monkeypatch):
    """The defect: one module-level name, `measured`, written twice.

    The map tab set it to a bool, the context tab rebound the SAME name to a
    frame of the regions carrying a declared share, and the draft tab tested it
    for truth. Streamlit re-runs the script top to bottom and `with tab:` opens
    no scope, so the context tab always ran first: with a context table
    carrying `apsfr_share` - the normal case on any machine that has run the
    pipeline - pressing Draft raised `ValueError: The truth value of a DataFrame
    is ambiguous` instead of drafting.

    Every other test in this section passes `context` absent, which is exactly
    how the whole tab could break while they stayed green.
    """
    table = _nested_table()
    with (
        _frozen(table, context=_context_table()),
        _stubbed_model(monkeypatch, "A sentence [S1].") as seen,
    ):
        app_test = _ask(table)

    assert app_test.exception == [], [str(e.value) for e in app_test.exception]
    # And still the ranked extract, not the unranked table: the name collision
    # must be fixed by renaming, not by dropping the condition.
    assert "ranked extract" in seen["prompt"]


def test_an_empty_completion_is_reported_rather_than_verified(monkeypatch):
    """The defect: `rag.complete` returns None when the model answers with
    message.content: null, and the call was outside any try. `grounding_score`
    then raised TypeError from inside a regex and the page showed a traceback.

    The root cause is in `src/rag.py`, which another agent owns; this is the call
    site refusing to store a None and verify it.
    """
    table = _nested_table()
    with _frozen(table), _stubbed_model(monkeypatch, None):
        app_test = _ask(table)

    assert app_test.exception == []
    assert "empty completion" in _texts(app_test)
    # Nothing to approve, because nothing was drafted.
    assert not [b for b in app_test.button if b.label == "Approve for the brief"]


def test_an_unreachable_provider_is_named_not_traced(monkeypatch):
    """A dead venue network is the realistic failure; a stack trace in front of a
    jury reads as a broken deliverable rather than a broken Wi-Fi."""
    table = _nested_table()
    with _frozen(table), _stubbed_model(monkeypatch, RuntimeError("connection refused")):
        app_test = _ask(table)

    assert app_test.exception == []
    said = _texts(app_test)
    assert "No model reachable" in said
    assert "connection refused" in said


def test_a_real_answer_is_shown_with_its_verification(monkeypatch):
    """The draft never appears without the grounding score and any invalid
    citation beside it, so pressing approve is an informed act."""
    table = _nested_table()
    with _frozen(table), _stubbed_model(monkeypatch, "Flood risk plans matter [S1][S4]."):
        app_test = _ask(table)

    assert app_test.exception == []
    labels = {m.label for m in app_test.metric}
    assert "Lexical grounding" in labels
    assert "Invalid citations" in labels
    assert "[S4]" in _texts(app_test)
    assert [b for b in app_test.button if b.label == "Approve for the brief"]


APPROVED_KEY = _key(ROOT / "data" / "processed" / "approved.md")
_real_open = pathlib.Path.open


@contextmanager
def _approved_into(target: pathlib.Path):
    """Send every open of `data/processed/approved.md` to `target` instead.

    The app writes the brief to a fixed path, the real file. A test that presses
    Approve must not append to it, so the open is redirected - reads too, since
    the translation tab pre-fills from the same file.
    """
    target.touch()

    def open_(self, *args, **kwargs):
        if _key(self) == APPROVED_KEY:
            return _real_open(target, *args, **kwargs)
        return _real_open(self, *args, **kwargs)

    with patch.object(pathlib.Path, "open", open_):
        yield


def _approve(app_test, text):
    box = next(t for t in app_test.text_area if t.label == "Draft — edit freely")
    box.set_value(text).run()
    next(b for b in app_test.button if b.label == "Approve for the brief").click().run()
    return app_test


def test_the_edited_text_is_verified_before_it_is_appended(monkeypatch, tmp_path):
    """The approval wrote whatever the text area held, and the checks shown
    above it were the MODEL's draft's. An edit that brings in [S9] - one
    passage was retrieved - is refused, and nothing reaches the brief."""
    target = tmp_path / "approved.md"
    table = _nested_table()
    with (
        _frozen(table), _approved_into(target),
        _stubbed_model(monkeypatch, "Flood risk management plans [S1]."),
    ):
        app_test = _approve(_ask(table), "Flood risk management plans [S1][S9].")

    assert app_test.exception == []
    assert "Not appended: [S9] cites no source" in _texts(app_test)
    assert target.read_text(encoding="utf-8") == ""


def test_an_approved_edit_is_written_with_its_verdict(monkeypatch, tmp_path):
    """A figure no source holds can be the human's correct edit, so it is
    written - with the verdict beside it in the record."""
    target = tmp_path / "approved.md"
    table = _nested_table()
    with (
        _frozen(table), _approved_into(target),
        _stubbed_model(monkeypatch, "Flood risk management plans [S1]."),
    ):
        app_test = _approve(_ask(table), "Flood risk management plans cover 4,812,000 people [S1].")

    assert app_test.exception == []
    written = target.read_text(encoding="utf-8")
    assert "Flood risk management plans cover 4,812,000 people [S1]." in written
    assert "unsupported numbers 4,812,000" in written


def test_the_draft_shows_the_numbers_and_sentences_no_source_backs(monkeypatch):
    table = _nested_table()
    with _frozen(table), _stubbed_model(
        monkeypatch,
        "Flood risk management plans cover 97% of basins [S1]. "
        "Every region must publish flood risk management plans.",
    ):
        app_test = _ask(table)

    assert app_test.exception == []
    labels = {m.label for m in app_test.metric}
    assert {"Numbers in no source", "Uncited sentences"} <= labels
    said = _texts(app_test)
    assert "check each one: 97" in said
    assert "Every region must publish flood risk management plans." in said


def test_a_silent_corpus_refuses_before_any_model_call(monkeypatch):
    called = []
    table = _nested_table()
    monkeypatch.setattr(rag, "search", lambda q, k=5: [])
    monkeypatch.setattr(rag, "complete", lambda *a, **k: called.append(1))

    with _frozen(table):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        box = next(t for t in app_test.text_input if "decision-maker" in t.label)
        box.set_value("capital gains tax in Portugal?").run()

    assert app_test.exception == []
    assert "Refused" in _texts(app_test)
    assert not called


def test_the_token_saving_is_never_shown_as_a_number_it_does_not_have(monkeypatch):
    """When tiktoken cannot be loaded every count is None. The page must say the
    saving was not measured rather than print one, because an unmeasured saving
    quoted in the brief as a measured one is the exact substitution this kit
    refuses everywhere else.
    """
    import src.toon_io as toon_io

    table = _nested_table()
    monkeypatch.setattr(
        toon_io, "token_report",
        lambda *a, **k: {
            "toon_tokens": None, "json_tokens": None, "saving_pct": None,
            "available": False, "reason": "tiktoken unavailable: DLL load failed",
        },
    )
    with _frozen(table), _stubbed_model(monkeypatch, "A sentence [S1]."):
        app_test = _ask(table)

    said = _texts(app_test)
    assert "NOT measured" in said
    assert "DLL load failed" in said
    # The measured wording, and the shape a None would have printed in it.
    assert "% smaller" not in said
    assert "None" not in said


@pytest.mark.parametrize("missing", ["total_pop", "share_over_65"])
def test_dropping_one_indicator_column_does_not_break_the_page(missing):
    """Columns come and go between runs; an absent one narrows what is offered
    rather than taking the page down."""
    app_test = _run(_nested_table().drop(columns=[missing]))
    assert app_test.exception == []
    assert missing not in app_test.multiselect[0].options


# --- the translation tab --------------------------------------------------------

def test_the_translation_tab_is_offered_in_the_three_belgian_languages():
    """The brief is drafted in English and acted on in French, Dutch or German."""
    app_test = _run(_nested_table())
    assert "Translation" in [tab.label for tab in app_test.tabs]
    into = [radio for radio in app_test.radio if radio.label == "Into"][0]
    # The labels, not the codes: `format_func` is what the user reads, and
    # offering `nl` rather than `Dutch` is how a civil servant picks the wrong one.
    assert sorted(into.options) == ["Dutch", "French", "German"]
    assert "English" not in into.options, "the source language is not a target"


def test_the_english_section_stays_the_record():
    """The translation sits beside the English rather than replacing it, because
    the English is the text whose figures were checked against the table."""
    app_test = _run(_nested_table())
    assert any(area.label == "English section" for area in app_test.text_area)
    assert "stays the record" in _texts(app_test)


def test_a_translation_that_moved_a_figure_is_not_rendered():
    """The failure this tab exists for: a paragraph that reads perfectly and
    quotes a number the table does not contain. It has to surface as an error,
    with the figure named, and the text must not appear on the page.

    Every interaction stays INSIDE `_frozen`. A `.run()` after the context exits
    unpatches `Path.stat`, and the app then reads the real
    `data/processed/exposure.parquet` - which exists on a developer's machine and
    not in CI, so the test passed locally and failed on the runner with a
    FileNotFoundError and no Translate button to click.
    """
    from src import translate as translate_module

    moved = "Pour une periode de retour de 100 ans, 29,7 millions d'habitants [S1]."
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        section = [a for a in app_test.text_area if a.label == "English section"][0]
        section.set_value(
            "At the 100-year return period, 29,727,887 residents are exposed [S1]."
        ).run()
        with patch.object(translate_module, "complete", lambda *a, **k: moved):
            next(b for b in app_test.button if b.label == "Translate").click().run()

    page = _texts(app_test)
    assert app_test.exception == []
    assert "Not shown" in page
    assert "29,7 millions" not in page


# --- the context tab ------------------------------------------------------------

def test_the_context_tab_says_how_to_build_a_table_it_does_not_have():
    """`scripts/build_context.py` is a separate build from the exposure one, so
    the app has to open with only the first of them run. The tab is the only
    place a reader learns the second exists."""
    app_test = _run(_nested_table())  # context defaults to absent, as in CI
    said = _texts(app_test)
    assert app_test.exception == []
    assert "scripts/build_context.py" in said
    # And the rest of the page is unaffected: the map is the deliverable.
    assert "residents exposed" in said.lower()


def test_a_single_member_period_is_not_reported_as_model_disagreement():
    """The caveat the whole tab exists for.

    A one-chain period shows zero regions agreeing on the sign, and that zero is
    indistinguishable from "the chains point different ways" unless the page says
    which. It has to name the missing member too, because "add a second model" is
    the action, and `VIC-WUR-EUR-11` is the one the CDS archive offers.
    """
    app_test = _run(_nested_table(), context=_context_table())
    said = _texts(app_test)
    assert app_test.exception == []
    assert "one model chain" in said
    assert "VIC-WUR-EUR-11" in said
    # The selectbox opens on the LAST period, which is the far-future one: the
    # period a reader is most likely to quote is the period carrying the caveat.
    assert "2071-2100" in said


def test_a_two_member_period_ranks_only_the_regions_that_agree():
    """With more than one chain the direction is readable, but only where the
    chains agree. The regions left out are not regions with no change, so the
    count of included ones is stated rather than implied by a table length."""
    with _frozen(_nested_table(), _context_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        period = [s for s in app_test.selectbox if s.label == "Period"][0]
        period.set_value("2041-2070").run()

    said = _texts(app_test)
    assert app_test.exception == []
    assert "one model chain" not in said, "two chains: the caveat does not apply"
    # BE31 and BE32 agree, BE33 does not - so two of three, said out loud.
    assert "2 regions where every chain agrees" in said


def test_context_columns_never_reach_the_indicator_picker():
    """The trap the separate table exists to avoid: the vulnerability index is a
    weighted mean over whatever numeric columns it is offered, so a climate
    percentage in that list would make "this region's rivers rise faster" a term
    in a vulnerability score."""
    app_test = _run(_nested_table(), context=_context_table())
    offered = [s for s in app_test.multiselect if s.label == "Indicators"][0].options
    assert offered == ["exposed_pop", "share_over_65"]
    for leaked in ("change_pct_ensemble_median_2071_2100", "built_share_exposed_rp100",
                   "shared_basin_share"):
        assert leaked not in offered


def test_the_tab_does_not_report_an_uncovered_country_as_undeclared():
    """The layer carries 26 country codes across both reporting cycles and
    Ireland is not one of them, so a blank has two causes that look identical.
    The page has to say which, and must not count an uncovered region among the
    regions that declared nothing."""
    app_test = _run(_nested_table(), context=_context_table())
    said = _texts(app_test)
    assert app_test.exception == []
    assert "never covered" in said
    # One region is uncovered and one of the two covered ones has no declared
    # area, so the headline is 1 of 2 - not 2 of 3. Read off the metric rather
    # than the page text: `_texts` collects prose, and a metric is neither.
    headline = [
        m for m in app_test.metric
        if "no declared area" in (m.label or "")
    ]
    assert headline, "the undeclared count is not on the page"
    assert headline[0].value == "1 of 2"


def test_the_tab_frames_the_gap_as_a_question_not_a_verdict():
    """A State may have assessed an area under Article 4 and concluded the risk
    is not significant, which the Directive allows. The page says so beside the
    count, because the count alone reads as an accusation."""
    app_test = _run(_nested_table(), context=_context_table())
    helps = " ".join(m.help or "" for m in app_test.metric)
    assert "not significant" in helps, (
        "the count reads as an accusation without the Directive's own allowance "
        "beside it"
    )


def test_the_tab_lists_the_regions_with_no_declared_area():
    """The section asks where modelled risk sits outside the designation, so the
    table has to show the gap. Ranked by declared share it showed the regions a
    State had covered entirely - true, and the opposite of the question."""
    app_test = _run(_nested_table(), context=_context_table())
    assert app_test.exception == []
    shown = [d for d in app_test.dataframe if "apsfr_share" in getattr(d.value, "columns", [])]
    assert shown, "no APSFR table on the page"
    table = shown[0].value
    assert not table["apsfr_declared"].any(), (
        "the table lists declared regions; it should list the ones with no "
        "declared area"
    )


def _context_with_people_and_natura() -> pd.DataFrame:
    """The context fixture plus the density, income and Natura 2000 columns.

    BE33 stands for a region outside the EU-27: no Natura figure at all, which
    must stay out of both sums rather than count as a protected area of zero.
    """
    return _context_table().assign(
        pop_density_per_km2=[800.0, 50.0, 300.0],
        pop_density_year=["2024", "2024", "2024"],
        household_income_pps_per_hab=[21_300.0, 18_000.0, None],
        household_income_year=["2023", "2023", None],
        household_income_level=["NUTS2, applied to its NUTS3 children"] * 2 + [None],
        natura2000_km2=[100.0, 300.0, None],
        natura2000_flooded_km2_rp100=[10.0, 30.0, None],
        natura2000_flooded_share_rp100=[0.1, 0.1, None],
        natura2000_grid_coverage=[1.0, 1.0, None],
    )


def test_the_tab_shows_natura_2000_as_an_area_on_flood_prone_ground():
    """Natura 2000 reached `context.parquet` with nothing on the page to read it.
    The headline sums the two areas over the regions that carry both, so a
    region outside the network adds nothing rather than a zero denominator."""
    app_test = _run(_nested_table(), context=_context_with_people_and_natura())
    assert app_test.exception == []
    assert "not a harm" in _texts(app_test)
    headline = [m for m in app_test.metric if "Natura 2000" in (m.label or "")]
    assert headline, "no Natura 2000 headline on the page"
    assert headline[0].value == "40 of 400 km² (10.0%)"
    shown = [d for d in app_test.dataframe
             if "natura2000_flooded_km2_rp100" in getattr(d.value, "columns", [])]
    assert shown, "no Natura 2000 table on the page"
    assert list(shown[0].value["nuts_id"])[:2] == ["BE32", "BE31"]


def test_the_tab_shows_density_and_income_with_the_nuts2_caveat():
    """Density and income are context, not indicators: the page shows them in the
    context tab, says income is NUTS2 repeated on its children, and the indicator
    picker still never offers them."""
    app_test = _run(_nested_table(), context=_context_with_people_and_natura())
    assert app_test.exception == []
    said = _texts(app_test)
    assert "NUTS2" in said and "weighting decision" in said
    shown = [d for d in app_test.dataframe
             if "pop_density_per_km2" in getattr(d.value, "columns", [])]
    assert shown, "no density and income table on the page"
    table = shown[0].value
    assert list(table["nuts_id"]) == ["BE31", "BE33", "BE32"]
    assert "household_income_pps_per_hab" in table.columns
    offered = [s for s in app_test.multiselect if s.label == "Indicators"][0].options
    for leaked in ("pop_density_per_km2", "household_income_pps_per_hab",
                   "natura2000_flooded_share_rp100"):
        assert leaked not in offered


def test_the_people_and_natura_sections_wait_for_their_columns():
    """A context table built before these layers has none of their columns; the
    page must open on it without either section, not raise a KeyError."""
    app_test = _run(_nested_table(), context=_context_table())
    assert app_test.exception == []
    said = _texts(app_test)
    assert "Natura 2000 on flood-prone ground" not in said
    assert "Population density and household income" not in said


def test_the_first_entry_creates_a_missing_log_with_its_header(tmp_path):
    """The log is not committed, so a fresh clone has none; the first entry
    must create it as a table instead of raising FileNotFoundError."""
    log = tmp_path / "docs" / "ai_usage_log.md"
    usage_log.append_row(log, usage_log.table_row(["09:00", "a", "b", "c", "accepted"]))
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[2] == usage_log.table_row(usage_log.LOG_COLUMNS).rstrip("\n")
    assert lines[3] == "|---|---|---|---|---|"
    assert lines[4] == "| 09:00 | a | b | c | accepted |"


def test_a_logged_entry_lands_inside_the_table_not_under_the_prose(tmp_path):
    """The defect: the form appended to the end of the FILE, and the log ends
    with prose. A new entry landed below the closing section, outside the table,
    where Markdown renders it as a paragraph with pipe characters in it.
    """
    log = tmp_path / "ai_usage_log.md"
    log.write_text(
        "| Time | Tool | Outcome |\n|---|---|---|\n| 09:00 | a | accepted |\n"
        "\n**Three rows.** Closing prose.\n\n## What the AI was not allowed to decide\n"
        "Nothing here is a table.\n",
        encoding="utf-8",
    )
    usage_log.append_row(log, "| 10:00 | b | rejected |\n")
    lines = log.read_text(encoding="utf-8").splitlines()
    table = [i for i, line in enumerate(lines) if line.startswith("|")]
    assert lines[max(table)] == "| 10:00 | b | rejected |"
    assert max(table) < next(
        i for i, line in enumerate(lines) if line.startswith("## ")
    ), "the new row must sit above the closing section, not below it"



def test_a_pipe_typed_in_a_log_field_stays_in_its_cell():
    """`|` ends a Markdown cell, so "Claude | Haiku" typed as the tool shifted
    every later field one column right; a newline ended the row itself."""
    row = usage_log.table_row(["Thu 10:00", "Claude | Haiku", "two\nlines", "ok"])
    assert row == "| Thu 10:00 | Claude \\| Haiku | two lines | ok |\n"
    assert row.count(" | ") == 3


def test_the_log_does_not_offer_links_the_app_cannot_serve():
    """The defect: `[`docs/decisions.md`](decisions.md)` is right in the repo and
    wrong in the app, where it resolves against the app's own origin and the dev
    server answers an unknown path with the app shell - so the link opened a
    second copy of the whole app in a new tab. An absolute GitHub URL is not the
    fix either: the kit has to run with the Wi-Fi off.
    """
    text = (
        "see [`docs/decisions.md`](decisions.md) and "
        "[`docs/responsible_ai.md`](../docs/responsible_ai.md#limits) and "
        "[the directive](https://eur-lex.europa.eu/eli/dir/2007/60/oj)"
    )
    out = usage_log.unlink_relative_docs(text)
    assert "](decisions.md)" not in out
    assert "responsible_ai.md#limits)" not in out
    assert "`docs/decisions.md`" in out and "`docs/responsible_ai.md`" in out
    # A link a reader WITH a network can follow is left alone.
    assert "](https://eur-lex.europa.eu/eli/dir/2007/60/oj)" in out


def test_a_build_that_finishes_while_the_page_is_open_is_picked_up():
    """The defect, and the one the reader actually hit: `load_exposure` was
    `@st.cache_data` and did its own `exists()` check, so the *absence* was
    cached. Once the page had run while the table was missing it kept answering
    "No exposure table yet" for the life of the process - telling the reader to
    run a build whose output it would then refuse to read. Reproduced here by
    running twice in one session with no cache clear in between, which is what a
    rerun is.
    """
    table = _nested_table()
    live = {"present": False}

    # Only the three artefacts are answered here, and everything else falls
    # through to the real filesystem. The first version of this test raised
    # FileNotFoundError for every other path, which is the trap our working rules name:
    # `Path.exists()` reaches `Path.stat()` on Python 3.12 and not on 3.14, so a
    # blanket raise made `AppTest.from_file` unable to find the app script - green
    # on this machine, `FileNotFoundError: AppTest script not found` on the runner.
    def exists(self, *args, **kwargs):
        key = _key(self)
        if key == _CACHE_KEY:
            return live["present"]
        if key in (_CONTEXT_KEY, _GEOMETRY_KEY):
            return False
        return _real_exists(self, *args, **kwargs)

    def stat(self, *args, **kwargs):
        key = _key(self)
        if key in (_CACHE_KEY, _CONTEXT_KEY, _GEOMETRY_KEY):
            if key != _CACHE_KEY or not live["present"]:
                raise FileNotFoundError(2, "No such file or directory", str(self))
            return _Stat()
        return _real_stat(self, *args, **kwargs)

    st.cache_data.clear()
    with (
        patch.object(pathlib.Path, "exists", exists),
        patch.object(pathlib.Path, "stat", stat),
        patch.object(pd, "read_parquet", lambda *a, **k: table),
        patch.object(svgmap, "load_features", lambda *a, **k: []),
    ):
        before = AppTest.from_file(str(APP), default_timeout=60).run()
        assert "No exposure table yet" in _texts(before)

        live["present"] = True  # the build finishes; nothing else changes
        after = AppTest.from_file(str(APP), default_timeout=60).run()

    assert after.exception == [], after.exception
    assert "No exposure table yet" not in _texts(after), (
        "the absence was cached: the page still refuses a table that now exists"
    )
    assert f"{len(table):,} rows" in _texts(after)


def test_a_table_rebuilt_while_the_page_is_open_replaces_the_old_one():
    """The mtime is the cache key so a rebuild is a cache miss. It was passed as
    `_state`, and `st.cache_data` does not hash a parameter whose name starts
    with an underscore: every mtime hit the first table read, and a rebuilt
    exposure table stayed invisible until the server restarted."""
    old, new = _nested_table(), _nested_table().head(3)
    live = {"table": old, "mtime": 1.0}

    class _Moving:
        @property
        def st_mtime(self):
            return live["mtime"]

    def exists(self, *args, **kwargs):
        key = _key(self)
        if key == _CACHE_KEY:
            return True
        if key in (_CONTEXT_KEY, _GEOMETRY_KEY):
            return False
        return _real_exists(self, *args, **kwargs)

    def stat(self, *args, **kwargs):
        key = _key(self)
        if key == _CACHE_KEY:
            return _Moving()
        if key in (_CONTEXT_KEY, _GEOMETRY_KEY):
            raise FileNotFoundError(2, "No such file or directory", str(self))
        return _real_stat(self, *args, **kwargs)

    st.cache_data.clear()
    with (
        patch.object(pathlib.Path, "exists", exists),
        patch.object(pathlib.Path, "stat", stat),
        patch.object(pd, "read_parquet", lambda *a, **k: live["table"]),
        patch.object(svgmap, "load_features", lambda *a, **k: []),
    ):
        before = AppTest.from_file(str(APP), default_timeout=60).run()
        assert f"{len(old):,} rows" in _texts(before)

        live.update(table=new, mtime=2.0)  # the build rewrites the file
        after = AppTest.from_file(str(APP), default_timeout=60).run()

    assert after.exception == [], after.exception
    assert f"{len(new):,} rows" in _texts(after), (
        "the cache ignored the new mtime and served the table read before the rebuild"
    )


def test_a_table_frozen_before_the_units_rename_offers_the_current_name():
    """Both UIs read through `with_current_names`, so they offer one list."""
    table = _nested_table()
    table["poverty_rate"] = [14.6, 22.0, 9.1] * 3
    with _frozen(table):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        offered = app_test.multiselect[0].options

    assert app_test.exception == [], app_test.exception
    assert offered == ["exposed_pop", "share_over_65", "poverty_rate_pct"]


# --- the ask-the-table tab -------------------------------------------------------
#
# Every interaction stays inside `_frozen`: a `.run()` outside it unpatches
# `Path.stat`, reads the real data/ on a dev machine and nothing at all on the
# runner, so the test would pass locally and fail in CI.

def test_a_typed_spec_is_answered_with_no_model(monkeypatch):
    def unreachable(*args, **kwargs):
        raise AssertionError("the spec route must not call a model")
    monkeypatch.setattr(rag, "complete_with_provider", unreachable)
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        box = next(t for t in app_test.text_area if t.label == "Query spec (JSON)")
        box.set_value(
            '{"columns": ["exposed_pop"], "sort": {"column": "exposed_pop", '
            '"descending": true}, "limit": 1}'
        ).run()
        next(b for b in app_test.button if b.label == "Run this spec").click().run()

    assert app_test.exception == [], app_test.exception
    answer = app_test.dataframe[-2].value
    # Answered for the period selected on the page (the default, RP100), with
    # the identifier added although the spec did not ask for it.
    assert list(answer["nuts_id"]) == ["BE31"]
    assert list(answer["exposed_pop"]) == [3000.0]
    assert "1-in-100 year" in _texts(app_test)
    definitions = app_test.dataframe[-1].value
    assert "exposed_pop" in list(definitions["column"])


def test_a_question_goes_through_one_model_call(monkeypatch):
    calls = []

    def model(prompt, system):
        calls.append(prompt)
        return rag.Completion(
            '{"columns": ["exposed_pop"], "sort": {"column": "exposed_pop", '
            '"descending": false}, "limit": 1, "return_period": 10}', "groq")
    monkeypatch.setattr(rag, "complete_with_provider", model)
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        box = next(t for t in app_test.text_input if t.label == "Question about the table")
        box.set_value("Least exposed region at the 10-year flood?").run()
        next(b for b in app_test.button if b.label == "Ask").click().run()

    assert app_test.exception == [], app_test.exception
    assert len(calls) == 1
    assert list(app_test.dataframe[-2].value["nuts_id"]) == ["BE33"]
    assert "1-in-10 year" in _texts(app_test)
    assert "Spec written by groq" in _texts(app_test)


def test_a_spec_outside_the_whitelist_is_shown_as_a_refusal(monkeypatch):
    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        box = next(t for t in app_test.text_area if t.label == "Query spec (JSON)")
        box.set_value('{"columns": ["__import__"]}').run()
        next(b for b in app_test.button if b.label == "Run this spec").click().run()

    assert app_test.exception == [], app_test.exception
    assert "Query refused" in _texts(app_test)
    assert "unknown column '__import__'" in _texts(app_test)


def test_the_ranked_chart_is_ordered_by_its_value_not_by_region_code():
    """`st.bar_chart` orders bars by label unless told otherwise, so the
    "ranked" chart ran alphabetically by NUTS code and the table under it was
    sorted by absolute count right below a caption saying not to."""
    import json

    with _frozen(_nested_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        chart = app_test.get("vega_lite_chart")[0]
        table = app_test.dataframe[0].value
    spec = json.loads(chart.proto.spec)
    encoding = spec.get("encoding") or spec["layer"][0]["encoding"]
    assert encoding["x"]["sort"] == {"field": "exposed_share", "order": "descending"}
    shares = table["exposed_share"].dropna().tolist()
    assert shares == sorted(shares, reverse=True)


def test_the_page_opens_on_the_eu27_and_offers_the_rest():
    from tests.test_api import _two_scope_table
    app_test = _run(_two_scope_table())
    assert app_test.exception == []
    assert app_test.radio[0].value == "EU-27"
    assert {m.label: m.value for m in app_test.metric}["Exposed, total"] == "3,400"
    with _frozen(_two_scope_table()):
        app_test = AppTest.from_file(str(APP), default_timeout=60).run()
        app_test.radio[0].set_value(app_test.radio[0].options[1]).run()
    assert {m.label: m.value for m in app_test.metric}["Exposed, total"] == "8,400"


def test_an_eu_only_table_offers_no_country_choice():
    from tests.test_api import _two_scope_table
    table = _two_scope_table()
    app_test = _run(table[table["country"] == "BE"])
    assert app_test.exception == []
    assert not any(r.label == "Countries" for r in app_test.radio)
