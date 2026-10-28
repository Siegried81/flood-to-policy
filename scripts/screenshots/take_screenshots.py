"""Headless screenshots of every Streamlit tab, and of the React app's July 2021 view.

Assumes the three servers are already up (take_screenshots.ps1 starts them):
Streamlit on 8599, FastAPI on 8099, Vite dev on 5199 proxying /api to 8099.
Streamlit is filled over a websocket and its tabs only exist by clicking, so a
plain `chrome --screenshot` captures a skeleton; Playwright waits in real time.
No tab action here calls a model: Ask/Draft/Translate are left on their empty
state. The React app is captured for its scope, July 2021: the opening view,
then one story map per named place (Ahr, Liege on the Meuse and the Vesdre,
...), then a single Europe tab, the exposure map, for context.

Usage: python take_screenshots.py [out_dir] [streamlit_url] [react_url] [dark|light]

Dark by default, matching docs/screenshots/*.png; both UIs follow the
browser colour scheme. Files are suffixed _light for the light theme.
"""
import re
import sys
import unicodedata
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "docs" / "screenshots")
ST_URL = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8599/"
REACT_URL = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:5199/"
THEME = sys.argv[4] if len(sys.argv) > 4 else "dark"
SUFFIX = "" if THEME == "dark" else f"_{THEME}"
VIEWPORT = {"width": 1440, "height": 1000}

STREAMLIT_TABS = [
    ("Exposure", "streamlit_exposure"),
    ("What qualifies it", "streamlit_context"),
    ("Who is most vulnerable", "streamlit_vulnerability"),
    ("Ask the table", "streamlit_ask"),
    ("Draft a brief section", "streamlit_draft"),
    ("Translation", "streamlit_translation"),
    ("AI usage log", "streamlit_ai_log"),
]
REACT_TABS = [
    ("Exposure", "react_map", None),
]


def slug(label):
    """A file-name-safe form of a place label: "Liège (Meuse–Vesdre)" -> "liege_meuse_vesdre"."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", label) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")


def full_height_shot(page, name, scroller=None):
    """Screenshot the whole page. Streamlit scrolls inside its main container,
    not the document, so the viewport is grown to that container's height first."""
    if scroller:
        h = page.evaluate(f"document.querySelector('{scroller}')?.scrollHeight || 1000")
        page.set_viewport_size({"width": VIEWPORT["width"], "height": int(min(max(h, 1000), 6000))})
        page.wait_for_timeout(2500)  # let charts re-layout to the new height
    page.screenshot(path=str(OUT / f"{name}{SUFFIX}.png"), full_page=True)
    page.set_viewport_size(VIEWPORT)
    print(f"  {name}{SUFFIX}.png")


def streamlit_idle(page, timeout=120_000):
    """Wait until the script run is over: no skeleton, no running indicator."""
    page.wait_for_selector("[data-testid=stTab]", timeout=timeout)
    page.wait_for_function(
        "!document.querySelector('[data-testid=stSkeleton]') && "
        "!document.querySelector('[data-testid=stStatusWidgetRunningIcon]')",
        timeout=timeout)
    page.wait_for_timeout(5000)  # maps and Vega charts draw after the run ends


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, color_scheme=THEME)
        page.on("console", lambda m: m.type in ("error", "warning") and errors.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

        print(ST_URL)
        page.goto(ST_URL)
        streamlit_idle(page)
        for label, name in STREAMLIT_TABS:
            page.locator("[data-testid=stTab]", has_text=label).first.click()
            streamlit_idle(page)
            full_height_shot(page, name, scroller="[data-testid=stMain]")

        print(REACT_URL)
        page.goto(REACT_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("svg path", timeout=60_000)
        # The app opens on the July 2021 view; the Europe tabs sit behind "Europe".
        page.wait_for_timeout(2000)
        full_height_shot(page, "react_july2021")
        # One shot per named place: the story map, its legend and its facts.
        places = page.locator("[aria-label='Choose a place'] button")
        for i in range(places.count()):
            button = places.nth(i)
            label = button.inner_text().strip()
            button.click()
            page.wait_for_timeout(1500)
            name = "react_story_" + slug(label)
            page.locator(".ev-story").screenshot(path=str(OUT / f"{name}{SUFFIX}.png"))
            print(f"  {name}{SUFFIX}.png")
        page.get_by_role("tab", name="Europe", exact=True).click()
        page.wait_for_load_state("networkidle")
        for label, name, button in REACT_TABS:
            tab = page.get_by_role("button", name=label, exact=True).or_(
                page.get_by_role("tab", name=label, exact=True)).first
            # With HOSTED=1 the model tabs are greyed out: there is nothing to capture.
            if tab.is_disabled():
                print(f"  {name}{SUFFIX}.png skipped: tab disabled (hosted mode)")
                continue
            tab.click()
            page.wait_for_load_state("networkidle")
            if button:
                page.get_by_role("button", name=button, exact=True).click()
                page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            full_height_shot(page, name)
        browser.close()

    if errors:
        print("console errors/warnings:")
        for line in dict.fromkeys(errors):
            print("  ", line[:400])


if __name__ == "__main__":
    main()
