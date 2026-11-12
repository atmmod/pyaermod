"""The browser GUI as published: Pyodide in a Web Worker and AERMOD's WebAssembly build.

Needs a site built by scripts/wasm/build_lite_site.sh (its ``app`` folder)
named by ``PYAERMOD_APP_SITE``, and network access to the jsDelivr CDN for
Pyodide; .github/workflows/wasm_aermod.yml provides both. Skipped
elsewhere: test_b01_browser_app.py drives the same page against CPython.
"""

from __future__ import annotations

import functools
import json
import os
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("PYAERMOD_APP_SITE"),
                       reason="PYAERMOD_APP_SITE names no built browser GUI"),
]

REPO = Path(__file__).resolve().parents[2]
RECORDING = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings" / "albany_success"
MET = REPO / "tests" / "fixtures" / "epa_official"
# Loading Pyodide, numpy, pandas and matplotlib from the CDN, cold.
START = 180_000


@pytest.fixture
def app(browser):
    site = Path(os.environ["PYAERMOD_APP_SITE"])
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{server.server_port}/")
    page.wait_for_selector("#app:not([hidden])", timeout=START)
    yield page
    context.close()
    server.shutdown()
    assert errors == [], errors


def step(page, name):
    page.locator("#steps").get_by_role("button", name=re.compile(name)).click()
    page.wait_for_selector(f"main h1:has-text('{name}')")


def import_albany(page):
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Import deck...").click()
    chooser.value.set_files([RECORDING / "aermod.inp", MET / "AERMET2.SFC", MET / "AERMET2.PFL"])
    page.wait_for_selector("text=Imported aermod.inp")


def run_and_wait(page):
    step(page, "Review & Run")
    page.get_by_role("button", name="Run AERMOD").click()
    page.wait_for_selector("main h1:has-text('Results')", timeout=120_000)


def test_b02_the_webassembly_aermod_gives_the_native_binarys_maxima(app):
    import_albany(app)
    run_and_wait(app)
    rows = app.locator("table[aria-label='Maximum for each averaging period'] tbody tr")
    got = {r.split("\t")[0].replace("-", ""): r.split("\t") for r in rows.all_inner_texts()}
    want = json.loads((RECORDING / "manifest.json").read_text())["maxima"]
    assert len(got) == len(want)
    for period, w in want.items():
        cells = got[period]
        assert float(cells[1]) == pytest.approx(w["value"], rel=1e-4)
        assert (float(cells[3]), float(cells[4])) == (w["x"], w["y"])
    assert app.locator("img.map").count() >= 1


def test_b02_cancel_ends_the_run_and_the_next_run_still_works(app):
    import_albany(app)
    step(app, "Review & Run")
    app.get_by_role("button", name="Run AERMOD").click()
    app.get_by_role("button", name="Cancel").click()
    # A new worker loads Pyodide again (from the browser's cache now).
    app.wait_for_selector("text=The run was cancelled.", timeout=START)
    # The uploaded met files were put back into the new worker.
    run_and_wait(app)
    assert app.locator("table[aria-label='Maximum for each averaging period'] tbody tr").count() == 4
