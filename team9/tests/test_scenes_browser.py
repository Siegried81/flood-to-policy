"""The four presentation scenes of flood_map.html: state preservation, reconciliation of totals, fixed Top 10 lists,
area priority scores (checked against an independent Python calculation), zoom independence, layout at 1366×768.
Needs a built flood_map.html and `playwright install chromium`; skipped otherwise. Loading the page takes ~30 s."""
import math
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
        pg = browser.new_page(viewport={"width": 1366, "height": 768})
        errors = []
        pg.on("pageerror", lambda e: errors.append(f"{e} @ {(e.stack or '')[:500]}"))
        pg.goto(HTML.as_uri(), wait_until="load", timeout=180_000)
        pg.wait_for_function("window.Scenes !== undefined", timeout=60_000)
        pg.errors = errors
        pg.ids = pg.evaluate("""() => { var g = ScenarioUI.get(), o = g.origins.slice().sort((a, b) => b.demand - a.demand)[0];
          return shelFilter.markers.filter(m => m.r.c === 'outside_extent_in_ems')
            .sort((a, b) => Math.hypot(a.r.x - o.x, a.r.y - o.y) - Math.hypot(b.r.x - o.x, b.r.y - o.y)).slice(0, 4).map(m => m.r.id); }""")
        yield pg
        browser.close()


def set_state(pg, km, ex, assumed, unavailable=()):
    pg.evaluate("([km, ex, a, u]) => { var s = ScenarioUI.get().state; s.km = km; s.exploratory = ex; "
                "Object.keys(s.assumed).forEach(k => delete s.assumed[k]); Object.keys(s.unavailable).forEach(k => delete s.unavailable[k]); "
                "Object.assign(s.assumed, a); u.forEach(k => s.unavailable[k] = true); ScenarioUI.recalc(); }", [km, ex, assumed, list(unavailable)])


def snapshot(pg):
    return pg.evaluate("() => { var g = ScenarioUI.get(); return JSON.stringify([g.state, g.result.total, g.A && g.A.state, g.A && g.A.sum]); }")


def py_scores(pg):
    """Independent recomputation of E, G, S from the page's inputs (P, origins, allocation) in Python."""
    d = pg.evaluate("""() => { var g = ScenarioUI.get(), S = Scenes;
      return {P: S.hex.P, oh: S.originHex, dem: g.origins.map(o => o.demand), by: Array.from(g.result.byOrigin),
              p99: SCENE_DATA.p99, w: S.priority().w}; }""")
    U = [0.0] * len(d["P"])
    for h, dem, by in zip(d["oh"], d["dem"], d["by"]):
        U[h] += max(0.0, dem - by)
    out = []
    for p, u in zip(d["P"], U):
        u = min(max(u, 0), p)
        E = 100 * min(1, math.log1p(p) / math.log1p(d["p99"]))
        G = 100 * u / p
        out.append((E, G, d["w"]["E"] * E + d["w"]["G"] * G))
    return out


def test_no_page_errors_and_scene_1_default(page):
    assert page.errors == []
    assert page.evaluate("Scenes.current()") == 1
    txt = page.inner_text("#scene-1")
    assert "mapped observed flood extent" in txt and "km²" in txt and "Belgian observations are incomplete" in txt
    assert page.evaluate("map => SHELTER_APP.map.hasLayer(SHELTER_APP.cluster)", None) is False   # shelters hidden
    assert page.evaluate("SHELTER_APP.map.hasLayer(Scenes.layers.expo)") is False


def test_population_reconciles(page):
    r = page.evaluate("""() => { var g = ScenarioUI.get(), H = Scenes.hex, s = 0, cnt = 0;
      H.P.forEach(p => s += p); H.no.forEach(c => cnt += c);
      return {hex: s, origins: g.demandTotal, nOrigins: g.origins.length, cnt: cnt, oh: Scenes.originHex.length,
              ids: new Set(H.id).size, n: H.id.length}; }""")
    assert r["hex"] == pytest.approx(r["origins"], abs=1e-6)
    assert r["cnt"] == r["nOrigins"] == r["oh"] and r["ids"] == r["n"]


def test_overview_circles_sum_residents(page):
    page.click("button[data-scene='2']")
    page.evaluate("zoomTo('All')"); page.wait_for_timeout(1500)
    r = page.evaluate("""() => { var c = Scenes.layers.cluster, s = 0, n = 0, bad = 0;
      c._featureGroup.eachLayer(l => { var v = l.getAllChildMarkers ? l.getAllChildMarkers().reduce((t, m) => t + m.options.res, 0) : l.options.res;
        s += v; n++; var lab = l._icon && l._icon.querySelector('.ecl'); if (lab && Math.abs(+lab.dataset.sum - v) > 1e-6) bad++; });
      return {s: s, n: n, bad: bad, total: Scenes.total}; }""")
    assert r["n"] > 1 and r["bad"] == 0
    assert r["s"] == pytest.approx(r["total"], abs=1e-6)               # each hexagon counted once across circles


def test_top10_exposed_fixed_and_explicit(page):
    page.click("button[data-scene='2']")
    rows = page.eval_on_selector_all("#scene-2 tr[data-hex]", "els => els.map(e => +e.dataset.hex)")
    assert len(rows) == 10 and len(set(rows)) == 10
    P = page.evaluate("Scenes.hex.P")
    assert [P[i] for i in rows] == sorted(P, reverse=True)[:10]
    txt = page.inner_text("#scene-2")
    assert "Top 10 hold" in txt and "in all 1,595 hexagons" in txt and "not the accuracy" in txt
    page.evaluate("void SHELTER_APP.map.setZoom(14)"); page.wait_for_timeout(500)
    assert page.eval_on_selector_all("#scene-2 tr[data-hex]", "els => els.map(e => +e.dataset.hex)") == rows


def test_no_capacity_gives_exposure_ranking(page):
    set_state(page, 5, False, {})
    page.click("button[data-scene='4']")
    txt = page.inner_text("#scene-4")
    assert "No usable capacity entered" in txt and "exposure ranking" in txt
    assert "no documented shelter-capacity baseline" in txt
    assert "verified shortage" not in txt.replace("not a verified shortage", "")
    order = page.evaluate("Scenes.priority().order.slice(0, 10)")
    assert order == page.evaluate("Scenes.byP.slice(0, 10)")


def test_scores_match_python_and_follow_the_scenario(page):
    i = page.ids
    page.click("button[data-scene='4']")
    before = page.evaluate("Scenes.priority().order")
    set_state(page, 5, False, {i[0]: 400, i[1]: 300})
    r = page.evaluate("Scenes.priority().rows")
    for js, py in zip(r, py_scores(page)):
        assert js["E"] == pytest.approx(py[0], abs=1e-6) and js["G"] == pytest.approx(py[1], abs=1e-6) and js["S"] == pytest.approx(py[2], abs=1e-6)
    after = page.evaluate("Scenes.priority().order")
    assert after != before                                               # capacity changes the ranking
    assert page.evaluate("Scenes.priority().rows.some(r => r && r.G < 100)")
    top = page.eval_on_selector_all("#scene-4 tr[data-hex]", "els => els.map(e => +e.dataset.hex)")
    assert top == after[:10] and len(set(top)) == 10
    after = after[:10]
    # distance and exploratory inclusion recalculate too
    page.evaluate(f"() => {{ var s = ScenarioUI.get().state; s.km = 1; ScenarioUI.recalc(); }}")
    assert page.evaluate("Scenes.priority().order.slice(0, 10)") != after or page.evaluate("Scenes.priority().rows.some(r => r && r.G < 100)")
    for js, py in zip(page.evaluate("Scenes.priority().rows"), py_scores(page)):
        assert js["S"] == pytest.approx(py[2], abs=1e-6)


def test_weights_reset_and_zero(page):
    page.click("button[data-scene='4']")
    page.evaluate("Scenes.weights(0, 0)")
    assert "Both weights are 0" in page.inner_text("#scene-4") and page.evaluate("Scenes.priority().order.length") == 0
    page.evaluate("Scenes.weights(100, 0)")
    assert page.evaluate("Scenes.priority().order.slice(0, 10)") == page.evaluate("Scenes.byP.slice(0, 10)")
    page.click("#w-reset")
    assert page.evaluate("Scenes.priority().w") == {"E": 0.5, "G": 0.5, "zero": False}


def test_zoom_does_not_change_scores(page):
    page.click("button[data-scene='4']")
    a = page.evaluate("JSON.stringify([SCENE_DATA.p99, Scenes.priority().order, Scenes.priority().rows])")
    page.evaluate("zoomTo('DE')"); page.wait_for_timeout(600)
    page.evaluate("void SHELTER_APP.map.setZoom(15)"); page.wait_for_timeout(600)
    assert page.evaluate("JSON.stringify([SCENE_DATA.p99, Scenes.priority().order, Scenes.priority().rows])") == a


def test_scene_switching_preserves_scenario_A_and_demo_view(page):
    i = page.ids
    set_state(page, 9, True, {i[0]: 120, i[1]: 0}, [i[2]])
    page.click("button[data-scene='3']")
    page.click("#scn-capA")
    page.evaluate("zoomTo('BE')"); page.wait_for_timeout(600)
    page.click("#demo-save")
    demo = page.evaluate("JSON.stringify(demoView.get())")
    snap = snapshot(page)
    for k in "12431":
        page.click(f"button[data-scene='{k}']")
        assert snapshot(page) == snap and page.evaluate("JSON.stringify(demoView.get())") == demo
    page.click("button[data-scene='3']")
    assert "a/b comparison" in page.inner_text("#scn-tab").lower() and "B − A" in page.inner_text("#scn-tab")
    page.click("#scn-clrA")


@pytest.mark.parametrize("scene, legends", [(1, ["leg-flood"]), (2, ["leg-expo"]), (3, ["leg-flood"]), (4, ["leg-prio"])])
def test_legend_and_layout_per_scene(page, scene, legends):
    page.click(f"button[data-scene='{scene}']")
    page.wait_for_timeout(300)
    for lg in legends:
        assert page.evaluate(f"!document.getElementById('{lg}').hidden"), lg
    hidden = {1: ["leg-expo", "leg-prio", "leg-efas"], 2: ["leg-prio"], 3: ["leg-expo", "leg-prio"], 4: ["leg-expo"]}[scene]
    for lg in hidden:
        assert page.evaluate(f"document.getElementById('{lg}').hidden"), lg
    page.evaluate("document.querySelectorAll('.scene-panel:not([hidden]) details').forEach(d => d.open = true)")
    page.evaluate("window.dispatchEvent(new Event('resize'))"); page.wait_for_timeout(300)
    sp = page.evaluate("(() => { var e = document.querySelector('.scene-panel:not([hidden])'); return [e.scrollWidth, e.clientWidth, e.getBoundingClientRect().bottom]; })()")
    assert sp[0] <= sp[1], "horizontal scroll in the scene panel"
    assert sp[2] <= 768
    boxes = page.evaluate("""['.title-panel', '.scene-panel:not([hidden])', '.legend', '.leaflet-control-layers', '.leaflet-control-attribution', 'details.limits']
      .map(s => { var r = document.querySelector(s).getBoundingClientRect(); return [s, r.left, r.top, r.right, r.bottom]; })""")
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[3] <= b[1] or b[3] <= a[1] or a[4] <= b[2] or b[4] <= a[2], f"{a[0]} overlaps {b[0]}"
    page.evaluate("document.querySelectorAll('.scene-panel details').forEach(d => d.open = false)")


def test_small_percentages_and_no_errors(page):
    assert page.evaluate("ScenarioUI.pct(78, 29130)") == "0.27 %"
    assert page.errors == []
