"""Planning scenario in the real page: complete save / restore (CSV and JSON), A/B comparison, demo view, layout.
Needs a built flood_map.html and `playwright install chromium`; skipped otherwise. Loading the page takes ~30 s."""
import json
from pathlib import Path

import pytest

HTML = Path(__file__).resolve().parents[1] / "flood_map.html"
playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not HTML.exists(), reason="run map.py first")


@pytest.fixture(scope="module")
def page():
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # browser not installed
            pytest.skip(str(e))
        pg = browser.new_page(viewport={"width": 1366, "height": 768}, accept_downloads=True)
        errors = []
        pg.on("pageerror", lambda e: errors.append(f"{e} @ {(e.stack or '')[:500]}"))
        pg.goto(HTML.as_uri(), wait_until="load", timeout=180_000)
        pg.wait_for_function("window.ScenarioUI !== undefined", timeout=60_000)
        pg.click("button[data-scene='3']")
        pg.click("button[data-tab=scenario]")
        pg.errors = errors
        # eligible candidates nearest to the origin with the most residents (so assignments are non-zero)
        pg.ids = pg.evaluate("""() => { var g = ScenarioUI.get(), o = g.origins.slice().sort((a, b) => b.demand - a.demand)[0];
          return shelFilter.markers.filter(m => m.r.c === 'outside_extent_in_ems')
            .sort((a, b) => Math.hypot(a.r.x - o.x, a.r.y - o.y) - Math.hypot(b.r.x - o.x, b.r.y - o.y)).slice(0, 5).map(m => m.r.id); }""")
        yield pg
        browser.close()


def state(pg):
    return pg.evaluate("() => { var g = ScenarioUI.get(); return {km: g.state.km, ex: g.state.exploratory, a: g.state.assumed, "
                       "u: g.state.unavailable, total: g.result.total, demand: g.demandTotal}; }")


def set_state(pg, km, ex, assumed, unavailable=()):
    pg.evaluate("([km, ex, a, u]) => { var s = ScenarioUI.get().state; s.km = km; s.exploratory = ex; "
                "Object.keys(s.assumed).forEach(k => delete s.assumed[k]); Object.keys(s.unavailable).forEach(k => delete s.unavailable[k]); "
                "Object.assign(s.assumed, a); u.forEach(k => s.unavailable[k] = true); ScenarioUI.recalc(); }", [km, ex, assumed, list(unavailable)])


def download(pg, button):
    with pg.expect_download() as d:
        pg.click(button)
    return Path(d.value.path()).read_text()


def restore(pg, text, name):
    pg.set_input_files("#scn-file", files=[{"name": name, "mimeType": "text/plain", "buffer": text.encode()}])
    pg.wait_for_function("document.getElementById('scn-msg').textContent.length > 0 && !/^Exported|^Saved/.test(document.getElementById('scn-msg').textContent)")
    return pg.inner_text("#scn-msg")


def reset(pg):
    pg.click("#scn-reset")


@pytest.fixture()
def scenario(page):
    i = page.ids
    set_state(page, 21, True, {i[0]: 150, i[1]: 0, i[2]: 80}, [i[3]])
    return state(page)


@pytest.mark.parametrize("button, name", [("#scn-exp-in", "in.csv"), ("#scn-save", "s.json")])
def test_export_reset_restore_returns_everything(page, scenario, button, name):
    text = download(page, button)
    assert scenario["total"] > 0
    reset(page)
    assert state(page)["km"] == 5 and not state(page)["a"]
    m = restore(page, text, name)
    assert state(page) == scenario, m          # 21 km, exploratory, zero capacity, unavailable facility, same result
    assert "replaced" in m and "Not in this file" not in m


@pytest.mark.parametrize("button, name", [("#scn-exp-in", "in.csv"), ("#scn-save", "s.json")])
def test_restore_replaces_instead_of_merging(page, scenario, button, name):
    text = download(page, button)
    page.evaluate("id => { ScenarioUI.get().state.assumed[id] = 999; ScenarioUI.recalc(); }", page.ids[4])
    restore(page, text, name)
    assert page.ids[4] not in state(page)["a"] and state(page) == scenario


@pytest.mark.parametrize("button, name", [("#scn-exp-in", "in.csv"), ("#scn-save", "s.json")])
def test_empty_scenario_keeps_settings(page, button, name):
    set_state(page, 17, True, {})
    text = download(page, button)
    reset(page)
    restore(page, text, name)
    s = state(page)
    assert (s["km"], s["ex"], s["a"], s["u"]) == (17, True, {}, {})


def test_legacy_csv_discloses_missing_settings(page, scenario):
    i = page.ids
    legacy = f"candidate_id,assumed_capacity,available\n{i[0]},40,yes\n{i[3]},,no\n"
    m = restore(page, legacy, "old.csv")
    s = state(page)
    assert (s["km"], s["ex"], s["a"], s["u"]) == (5, False, {i[0]: 40}, {i[3]: True})
    assert "Not in this file" in m and "max. distance and exploratory option" in m


@pytest.mark.parametrize("text, expect", [
    ("candidate_id,assumed_capacity,available,max_distance_m\n{0},-3,yes,5000\n", "invalid assumed_capacity"),
    ("candidate_id,assumed_capacity,available,max_distance_m\n{0},10,yes,5000\n{1},10,yes,8000\n", "conflicting max_distance_m"),
    ("candidate_id,assumed_capacity,available,max_distance_m\n{0},10,maybe,5000\n", "invalid available"),
    ("candidate_id,assumed_capacity,available,max_distance_m\n{0},10,yes,30000\n", "invalid max_distance_m"),
    ("candidate_id,assumed_capacity,available\n{0},10,yes\n{0},20,yes\n", "appears twice"),
    ('{{"format": "floodmap-shelter-scenario", "version": 9}}', "unsupported version"),
    ('{{"format": "floodmap-shelter-scenario", "version": 1, "settings": {{"max_distance_m": 5000, "exploratory_outside_ems": "yes"}}, "facilities": []}}',
     "exploratory_outside_ems must be true or false"),
])
def test_invalid_files_abort_and_keep_the_scenario(page, scenario, text, expect):
    m = restore(page, text.format(*page.ids), "bad.csv")
    assert "Restore aborted" in m and expect in m
    assert state(page) == scenario


def test_unknown_and_ineligible_ids_are_reported(page, scenario):
    inside = page.evaluate("shelFilter.markers.find(m => m.r.c === 'inside_observed').r.id")
    m = restore(page, f"candidate_id,assumed_capacity,available,max_distance_m,exploratory_outside_ems\n"
                      f"{page.ids[0]},30,yes,6000,no\nosm:node/0,10,yes,6000,no\n{inside},10,yes,6000,no\n", "partial.csv")
    assert state(page)["a"] == {page.ids[0]: 30} and state(page)["km"] == 6
    assert "Partial restore" in m and "osm:node/0" in m and inside in m


def test_ab_comparison(page, scenario):
    page.click("#scn-capA")
    a = page.evaluate("ScenarioUI.get().A")
    # B: one facility unavailable
    page.evaluate("id => { ScenarioUI.get().state.unavailable[id] = true; ScenarioUI.recalc(); }", page.ids[0])
    b = state(page)
    assert page.evaluate("ScenarioUI.get().A.state.unavailable") == a["state"]["unavailable"]   # A not mutated
    assert a["sum"]["demand"] == b["demand"]
    txt = page.inner_text(".scn-cmp")
    diff = b["total"] - a["sum"]["assigned"]
    assert diff < 0 and f"−{round(-diff):,}" in txt
    assert "Assumptions changed A → B (1)" in txt and "available → unavailable" in txt
    assert "cannot be attributed" not in txt
    page.evaluate("ScenarioUI.get().state.km = 9; ScenarioUI.recalc()")
    assert "cannot be attributed" in page.inner_text(".scn-cmp")
    page.click("#scn-resA")
    s = state(page)
    assert abs(s["total"] - a["sum"]["assigned"]) < 1e-9 and s["u"] == scenario["u"] and s["km"] == 21
    assert "same result" in page.inner_text("#scn-msg")
    page.click("#scn-clrA")
    assert page.evaluate("ScenarioUI.get().A") is None


def test_wording_and_percentages(page, scenario):
    assert page.evaluate("ScenarioUI.pct(78, 29130)") == "0.27 %"
    assert page.evaluate("ScenarioUI.pct(0.01, 29130)") == "< 0.1 %"
    txt = page.inner_text("#scn-tab").lower()
    for bad in ["saved", "safe evacuation", "verified shortage", "people saved"]:
        assert bad not in txt.replace("save scenario", "").replace("saved with", ""), bad
    assert "straight-line connections are not verified routes" in txt


def test_demo_view_does_not_touch_the_scenario(page, scenario):
    page.click("#demo-save")
    view = page.evaluate("demoView.get()")
    page.evaluate("zoomTo('NL')"); page.wait_for_timeout(600)
    before = state(page)
    page.click("#demo-go"); page.wait_for_timeout(600)
    c = page.evaluate(f"(() => {{ var m = SHELTER_APP.map, c = m.getCenter(); return [c.lat, c.lng, m.getZoom()]; }})()")
    assert abs(c[0] - view["lat"]) < 1e-4 and abs(c[1] - view["lng"]) < 1e-4 and c[2] == view["zoom"]
    assert state(page) == before


def test_filters_change_display_not_allocation(page, scenario):
    page.click("button[data-tab=candidates]")
    page.click("button[data-focus=inside]")
    assert page.inner_text("#shel-shown") == "39"
    page.evaluate("ScenarioUI.recalc()")
    assert state(page)["total"] == scenario["total"]
    page.click("button[data-focus=all]")
    page.click("button[data-tab=scenario]")


def test_layout_and_no_errors(page, scenario):
    page.click("#scn-capA")
    page.evaluate("document.querySelectorAll('#scn-tab details').forEach(d => d.open = true)")
    page.evaluate("window.dispatchEvent(new Event('resize'))"); page.wait_for_timeout(300)
    sp = page.evaluate("(() => { var e = document.querySelector('.shel-panel'); return [e.scrollWidth, e.clientWidth]; })()")
    assert sp[0] <= sp[1], "horizontal scroll in the shelter panel"
    boxes = page.evaluate("""['.title-panel', '.shel-panel', '.legend', '.leaflet-control-layers', '.leaflet-control-attribution']
      .map(s => { var r = document.querySelector(s).getBoundingClientRect(); return [s, r.left, r.top, r.right, r.bottom]; })""")
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[3] <= b[1] or b[3] <= a[1] or a[4] <= b[2] or b[4] <= a[2], f"{a[0]} overlaps {b[0]}"
    page.click("#scn-clrA")
    assert page.errors == []
