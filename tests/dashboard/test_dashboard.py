"""Smoke test of the static dashboard in a headless browser.

Serves a site folder (default web/, override with DASHBOARD_DIR) over HTTP and checks that the
page loads its data/*.json without a JavaScript error and draws its main pieces. Run it on the
committed snapshot, or on freshly exported data before publishing.

    pip install pytest playwright && playwright install chromium
    pytest tests/dashboard
"""

from __future__ import annotations

import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SITE = Path(os.environ.get("DASHBOARD_DIR", ROOT / "web")).resolve()


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def page():
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.errors = []
        page.on("pageerror", lambda err: page.errors.append(str(err)))
        page.on("console", lambda msg: msg.type == "error" and page.errors.append(msg.text))
        # map tiles come from a third-party server: their failures say nothing about the page
        page.route("**/*tile*/**", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/", wait_until="networkidle")
        page.wait_for_selector("#kpis > *", timeout=15_000)
        yield page
        browser.close()
    server.shutdown()


def regions_in_data() -> set[str]:
    episodes = json.loads((SITE / "data" / "dim_episodes.json").read_text())
    return {e["region_id"] for e in episodes}


def test_no_javascript_error(page):
    tile_errors = [e for e in page.errors if "ERR_FAILED" in e or "net::" in e]
    assert [e for e in page.errors if e not in tile_errors] == []


def test_one_button_per_region(page):
    buttons = page.locator("#region-picker button")
    assert {buttons.nth(i).get_attribute("data-region") for i in range(buttons.count())} == regions_in_data()


def test_map_draws_cells(page):
    # the map draws on a canvas (preferCanvas): count the hexagons on the Leaflet layer instead
    assert page.locator("#map canvas").count() > 0
    assert page.evaluate("cellLayer.getLayers().length") > 0


def test_charts_render(page):
    for chart in ("#chart-timeline", "#chart-fire", "#chart-slope-obs", "#chart-mix"):
        assert page.locator(f"{chart} svg").count() > 0, chart
    assert page.locator("#verdict-card").inner_text().strip()


def test_every_region_opens(page):
    buttons = page.locator("#region-picker button")
    for i in range(buttons.count()):
        buttons.nth(i).click()
        assert page.locator("#fire-title").inner_text().strip()
    assert page.errors == [] or all("net::" in e for e in page.errors)
