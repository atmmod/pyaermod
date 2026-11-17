#!/usr/bin/env python3
"""Take the screenshots the documentation shows, from the GUIs themselves.

    python scripts/docs_screenshots.py [--only gui|app]

``pyaermod-app`` is driven through the GUI journeys' own harness and page
objects (``tests/e2e``): a fresh server, the Albany reference scenario
entered step by step, and AERMOD replayed from the recording
``albany_success``, so no AERMOD binary is needed. The browser app
(``webapp/``) is served by ``scripts/wasm/app_dev_server.py`` against
CPython, with the same recording. The images go to ``docs/images/gui/``
and ``docs/images/app/``, cropped to the part of the window each page of
the docs describes and reduced to a palette to keep them small.

Run it again after a change to either GUI that the docs' pictures show;
``tests/test_docs_images.py`` checks that every image a page names exists.

Needs ``pip install -e ".[dev,gui,e2e]"`` and Playwright's Chromium
(``python -m playwright install chromium``), or ``PYAERMOD_E2E_CHROMIUM``
naming a Chromium executable.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUI_DIR = REPO / "docs" / "images" / "gui"
APP_DIR = REPO / "docs" / "images" / "app"
RECORDINGS = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings"
MET = REPO / "tests" / "fixtures" / "epa_official"

sys.path.insert(0, str(REPO))

#: The window the screenshots are taken in: a laptop screen.
VIEWPORT = {"width": 1280, "height": 860}


#: Hidden while a part of the page is photographed: the header is fixed,
#: so a picture of a long panel would show it across the middle.
HIDE_HEADER = ("header, .q-header { visibility: hidden !important; } "
               ".q-notifications { display: none !important; }")


def trim(image, margin: int = 12):
    """``image`` without the blank rows above and below its content (kept: ``margin``)."""
    from PIL import ImageChops

    background = image.getpixel((image.width - 1, image.height - 1))
    from PIL import Image

    diff = ImageChops.difference(image, Image.new(image.mode, image.size, background))
    box = diff.convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
    if box is None:
        return image
    top = max(box[1] - margin, 0)
    bottom = min(box[3] + margin, image.height)
    return image.crop((0, top, image.width, bottom))


def save(shot: bytes, path: Path, *, trimmed: bool = True) -> None:
    """Write ``shot`` (PNG bytes) as a palette PNG: UI pictures lose nothing visible."""
    from PIL import Image

    image = Image.open(io.BytesIO(shot)).convert("RGB")
    if trimmed:
        image = trim(image)
    image = image.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    print(f"  {path.relative_to(REPO)}  {image.width}x{image.height}  "
          f"{path.stat().st_size // 1024} kB")


def top_of(locator, height: int) -> bytes:
    """A screenshot of ``locator``'s first ``height`` pixels (the rest of a long panel is cut)."""
    box = locator.bounding_box()
    page = locator.page
    return page.screenshot(full_page=True, style=HIDE_HEADER, clip={
        "x": box["x"], "y": box["y"], "width": box["width"],
        "height": min(box["height"], height)})


def whole(locator) -> bytes:
    """A screenshot of ``locator`` with the fixed header out of the way."""
    return locator.screenshot(style=HIDE_HEADER)


def gui_shots(browser, root: Path) -> None:
    """``pyaermod-app``: the layout, each step of the reference scenario, Review & Run and Results."""
    from tests.e2e.conftest import NO_ANIMATIONS
    from tests.e2e.harness import GuiServer
    from tests.e2e.pages import App
    from tests.e2e.reference import AVERAGING_PERIODS, enter_reference_scenario

    server = GuiServer(root / "gui_server", recording="albany_success", delay=0.0).start()
    try:
        context = browser.new_context(viewport=VIEWPORT, accept_downloads=True)
        context.add_init_script(NO_ANIMATIONS)
        page = context.new_page()
        gui = App(page, server.url).open()

        save(page.screenshot(), GUI_DIR / "layout.png", trimmed=False)
        save(whole(gui.open_step("Review & Run")), GUI_DIR / "review-checklist.png")

        def shot(name: str) -> None:
            if name in ("sources", "receptors", "meteorology"):
                save(whole(gui.open_step(name.capitalize())), GUI_DIR / f"{name}.png")

        gui.open_step("Project")
        enter_reference_scenario(gui, shot)
        gui.project.set_averaging_periods(*AVERAGING_PERIODS)
        save(whole(gui.open_step("Project")), GUI_DIR / "project.png")
        save(whole(gui.open_step("Output")), GUI_DIR / "output.png")

        run_dir = root / "run"
        run_dir.mkdir()
        gui.run.set_working_directory(run_dir)
        save(top_of(gui.open_step("Review & Run"), 900), GUI_DIR / "review-ready.png")
        gui.run.start()
        gui.run.wait_until_finished()
        save(top_of(gui.open_step("Review & Run"), 700), GUI_DIR / "run-finished.png")

        gui.results.open()
        panel = gui.open_step("Results")
        page.wait_for_timeout(1500)                # the map is drawn after the tables
        save(top_of(panel, 1300), GUI_DIR / "results.png")
        figure = panel.locator("img").first
        figure.scroll_into_view_if_needed()
        save(whole(figure), GUI_DIR / "results-map.png", trimmed=False)
        context.close()
    finally:
        server.stop()


def app_shots(browser, root: Path) -> None:
    """The browser app: its layout with the Albany sample, and Results after a run."""
    from pyaermod import browser as api

    spec = importlib.util.spec_from_file_location(
        "app_dev_server", REPO / "scripts" / "wasm" / "app_dev_server.py")
    dev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dev)
    os.environ["PYAERMOD_E2E_RECORDING"] = "albany_success"
    server = dev.serve(0, replay="albany_success", work_dir=root / "app_work")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        context = browser.new_context(viewport=VIEWPORT, accept_downloads=True)
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{server.server_port}/")
        page.wait_for_selector("#app:not([hidden])", timeout=30000)

        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name="Import deck...").click()
        chooser.value.set_files([RECORDINGS / "albany_success" / "aermod.inp",
                                 MET / "AERMET2.SFC", MET / "AERMET2.PFL"])
        page.wait_for_selector("text=Imported aermod.inp")
        page.locator("#steps").get_by_role("button", name="Sources").click()
        page.wait_for_selector("#plan svg")
        save(page.screenshot(), APP_DIR / "sources.png", trimmed=False)

        page.locator("#steps").get_by_role("button", name="Review & Run").click()
        page.get_by_role("button", name="Run AERMOD").click()
        page.wait_for_selector("main h1:has-text('Results')", timeout=60000)
        page.wait_for_selector("img.map")
        save(top_of(page.locator("main"), 1300), APP_DIR / "results.png")
        context.close()
    finally:
        server.shutdown()
        api.RUNNER_FACTORY = None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", choices=("gui", "app"))
    args = parser.parse_args(argv)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw, tempfile.TemporaryDirectory(prefix="pyaermod_shots_") as tmp:
        browser = pw.chromium.launch(
            executable_path=os.environ.get("PYAERMOD_E2E_CHROMIUM") or None)
        with contextlib.ExitStack():
            if args.only in (None, "gui"):
                print("pyaermod-app")
                gui_shots(browser, Path(tmp))
            if args.only in (None, "app"):
                print("browser app")
                app_shots(browser, Path(tmp))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
