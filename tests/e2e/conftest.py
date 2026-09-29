"""Fixtures for the GUI's end-to-end journeys (PLAN-gui.md, tiers T2 and T3).

Every journey gets a fresh GUI server on a free port, started from this
checkout's ``src`` with its own home, temp and working directories, and a
fresh browser context in a Chromium shared by the session. When the journey
ends it fails if anything went wrong that the page did not show: a browser
``pageerror`` or console error, a Python traceback in the server log, or a
deck the fake AERMOD did not recognise. The check runs again after the
server stops, for anything its shutdown adds.

Journeys use these fixtures:

``gui``        the :class:`pages.App` page objects, bound to this server
``step``       ``step("name")`` saves ``test-artifacts/gui/<test>/NN_name.png``
``known_gap``  ``with known_gap("D2", "..."):`` around a step the current GUI
               cannot do (see :class:`harness.KnownGap`)
``run_dir``    an empty directory to type into the Run step as its working
               directory, so the test can read what the run left there
``journey``    the :class:`harness.Journey` behind them, for the rare check
               that needs the server itself (J9 looks for leftover processes)

Choose the AERMOD a journey meets with ``@pytest.mark.aermod_recording``:
``aermod_recording("albany_e480", delay=0.5)`` makes the fake replay that
recording, pausing between stdout lines. The marker is ignored in tier T3
(``PYAERMOD_E2E_REAL=1``), where the real ``aermod`` on ``PATH`` runs.

Browser: ``PYAERMOD_E2E_CHROMIUM`` names a Chromium executable to launch
instead of Playwright's pinned build (for containers that ship their own).
"""

from __future__ import annotations

import contextlib
import os
import shutil
from typing import Dict, Optional, Tuple

import pytest

from .harness import REAL_AERMOD, RECORDINGS, TIER, GuiServer, Journey

try:
    import playwright.sync_api
except ImportError:
    # The journeys need Playwright (pip install -e ".[e2e]"). The default
    # suite deselects them anyway, so without it they are not collected.
    collect_ignore_glob = ["test_*.py"]


# Quasar animates tab switches, dialogs and expansions. Zero-length CSS
# transitions end at once (Vue's <Transition> reads the computed duration),
# which saves seconds per journey without changing what the pages do.
NO_ANIMATIONS = """
document.addEventListener("DOMContentLoaded", () => {
  const style = document.createElement("style");
  style.textContent = `*, *::before, *::after {
    transition-duration: 0s !important; transition-delay: 0s !important;
    animation-duration: 0s !important; animation-delay: 0s !important; }`;
  document.head.appendChild(style);
});
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "aermod_recording(name, delay=0.0): the AERMOD recording the fake "
        "binary replays for this journey in tier T2",
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Fail the journey itself for errors the page did not show.

    Checked when the test body ends, while the server still runs; the
    fixture's teardown checks again for anything the shutdown adds.
    A journey stopped by a known gap is checked up to that gap.
    """
    journey = getattr(item, "funcargs", {}).get("journey")
    try:
        result = yield
    except pytest.xfail.Exception:
        _fail_on_hidden_problems(journey)
        raise
    _fail_on_hidden_problems(journey)
    return result


def _fail_on_hidden_problems(journey) -> None:
    if journey is None:
        return
    problems = [p for p in journey.hidden_problems() if p not in journey.reported]
    journey.reported.update(problems)
    if problems:
        log = journey.server.log_text()
        pytest.fail(
            "hidden errors during the journey:\n- " + "\n- ".join(problems)
            + f"\n\n--- GUI server log ({journey.server.log_path}) ---\n"
            + log[-20000:],
            pytrace=False,
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.e2e_call_report = report


# Each journey gets a server process of its own, but the process for the
# next journey is launched while the current one runs, so its start-up
# (about two seconds of imports) is off the critical path.
_PRELAUNCHED: Dict[str, GuiServer] = {}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    item.e2e_next_item = nextitem
    yield


def pytest_sessionfinish(session):
    while _PRELAUNCHED:
        _PRELAUNCHED.popitem()[1].stop()


def _server_settings(item) -> Tuple[Optional[str], float]:
    marker = item.get_closest_marker("aermod_recording")
    if marker is None:
        return None, 0.0
    return marker.args[0], float(marker.kwargs.get("delay", 0.0))


def _new_server(item, tmp_path_factory) -> GuiServer:
    recording, delay = _server_settings(item)
    return GuiServer(tmp_path_factory.mktemp("gui_server"),
                     recording=recording, delay=delay).launch()


def _prelaunch(item, tmp_path_factory) -> None:
    if item is None or "journey" not in getattr(item, "fixturenames", ()):
        return
    if REAL_AERMOD and shutil.which("aermod") is None:
        return
    if item.nodeid not in _PRELAUNCHED:
        _PRELAUNCHED[item.nodeid] = _new_server(item, tmp_path_factory)


def pytest_report_header(config):
    aermod = "real aermod on PATH" if REAL_AERMOD else "recordings replayed by fake_aermod.py"
    return f"GUI journeys: tier {TIER} ({aermod})"


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        chromium = pw.chromium.launch(
            executable_path=os.environ.get("PYAERMOD_E2E_CHROMIUM") or None,
            # The journeys talk only to 127.0.0.1; keep Chromium from
            # phoning home for component updates and the like.
            args=["--disable-background-networking", "--disable-component-update"],
        )
        yield chromium
        chromium.close()


@pytest.fixture
def journey(request, browser, tmp_path, tmp_path_factory):
    if REAL_AERMOD and shutil.which("aermod") is None:
        pytest.skip("PYAERMOD_E2E_REAL=1 but no aermod binary on PATH")
    recording, _delay = _server_settings(request.node)
    if recording and not (RECORDINGS / recording / "manifest.json").exists():
        pytest.fail(f"no AERMOD recording {recording!r} in {RECORDINGS}")

    server = (_PRELAUNCHED.pop(request.node.nodeid, None)
              or _new_server(request.node, tmp_path_factory))
    server.wait_ready()
    _prelaunch(getattr(request.node, "e2e_next_item", None), tmp_path_factory)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900}, accept_downloads=True,
    )
    context.add_init_script(NO_ANIMATIONS)
    journey = Journey(name=request.node.name, server=server,
                      page=context.new_page(), root=tmp_path)
    try:
        yield journey
    finally:
        report = getattr(request.node, "e2e_call_report", None)
        if report is not None and report.failed:
            journey.step("failure")
        with contextlib.suppress(Exception):
            context.close()
        server.stop()
        for path in journey.server_side_files:
            with contextlib.suppress(OSError):
                path.unlink()

    # Anything the shutdown added (the call phase reported the rest).
    _fail_on_hidden_problems(journey)


@pytest.fixture
def gui(journey):
    from .pages import App

    return App(journey.page, journey.server.url, journey=journey)


@pytest.fixture
def step(journey):
    return journey.step


@pytest.fixture
def known_gap(journey):
    return journey.known_gap


@pytest.fixture
def run_dir(journey):
    path = journey.root / "run"
    path.mkdir()
    return path
