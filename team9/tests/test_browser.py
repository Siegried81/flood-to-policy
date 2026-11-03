"""Asset screening scores in flood_map.html (context layers ported from the retired priority_map.html): the browser
recomputes them like scoring.py and reacts to the asset sliders (needs a built flood_map.html and
`playwright install chromium`; skipped otherwise)."""
import numpy as np
import pytest

from priority import scoring as sc

HTML = __import__("pathlib").Path(__file__).resolve().parents[1] / "flood_map.html"
playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not HTML.exists(), reason="run map.py first")


@pytest.fixture(scope="module")
def page():
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # browser not installed
            pytest.skip(str(e))
        pg = browser.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(HTML.as_uri(), wait_until="load", timeout=180_000)
        pg.wait_for_function("window.AssetContext !== undefined && window.Scenes !== undefined", timeout=60_000)
        pg.errors = errors
        yield pg
        browser.close()


def test_no_page_errors(page):
    assert page.errors == []


@pytest.mark.parametrize("w", [[0.4, 0.3, 0.3], [0.1, 0.8, 0.1], [0, 0, 1], [0.2, 0.2, 0.6]])
def test_js_matches_python(page, w):
    items = [[0.9, 0.5, 0.8, 1.0], [0.5, 0.9, 0.1, 0.625], [0.9, 0.5, None, 0.75], [0.2, None, 1.0, 0.875]]
    js = page.evaluate("([items, w]) => items.map(o => AssetContext.score({P: o[0], B: o[1], F: o[2], M: o[3]}, {P: w[0], B: w[1], F: w[2]}))",
                       [items, list(sc.normalize_weights(w))])
    X = np.array([[np.nan if v is None else v for v in o[:3]] for o in items], float)
    py = sc.score(X, w, np.array([o[3] for o in items]))
    for i, r in enumerate(js):
        s = np.nan if r["s"] is None else r["s"]   # no available indicator with weight > 0: undefined in both
        assert s == pytest.approx(py["score"][i], nan_ok=True)
        assert r["lo"] == pytest.approx(py["lo"][i]) and r["hi"] == pytest.approx(py["hi"][i])


def test_sliders_change_scores_and_ranking(page):
    first = "() => ['people','infra'].map(g => AssetContext.GROUP[g].data.filter(o => o.rank).slice(0, 10).map(o => o.id).join())"
    area = "() => Scenes.priority().order.slice(0, 10).join()"
    a0 = page.evaluate(area)
    page.evaluate("AssetContext.setWeights(100, 0, 0)")
    a = page.evaluate(first)
    page.evaluate("AssetContext.setWeights(0, 0, 100)")
    b = page.evaluate(first)
    assert page.evaluate(area) == a0                     # asset weights never change the area priority
    page.evaluate("AssetContext.setWeights(40, 30, 30)")
    assert a[0] != b[0]                                  # facility ranking changes


def test_default_scores_match_python_export(page):
    """Scores shown at default weights equal those computed in Python (and written to priority_ranking.csv)."""
    rows = page.evaluate("() => AssetContext.GROUP.people.data.slice(0, 50).map(o => [o.P ?? null, o.B ?? null, o.F ?? null, o.M, o.cur.s])")
    X = np.array([[np.nan if v is None else v for v in r[:3]] for r in rows], float)
    py = sc.score(X, sc.DEFAULT_WEIGHTS, np.array([r[3] for r in rows]))["score"]
    assert np.allclose(py, [r[4] for r in rows], atol=0.3)   # inputs rounded to 3 decimals in the page
