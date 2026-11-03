"""Screenshots of flood_map.html for a visual check: default view and a zoomed-in view (Ahr valley)."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
html = (HERE / "flood_map.html").as_uri()
out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE

with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1440, "height": 900})
    page.goto(html, wait_until="networkidle", timeout=180_000)
    page.wait_for_timeout(3000)
    page.screenshot(path=out / "shot_default.png")
    map_var = page.evaluate("Object.keys(window).find(k => k.startsWith('map_'))")
    page.evaluate(f"{map_var}.setView([50.535, 7.08], 14); null")  # Bad Neuenahr-Ahrweiler
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    page.screenshot(path=out / "shot_zoom.png")
    print("saved", out / "shot_default.png", out / "shot_zoom.png")
