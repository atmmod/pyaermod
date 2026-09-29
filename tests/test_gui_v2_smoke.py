"""Headless tests for the NiceGUI GUI (``pyaermod.gui_v2``), tier T1.

Drives the real app shell through ``nicegui.testing.User`` — an in-process
ASGI client with a simulated browser session. No server socket, no
browser, no selenium. Each test:

1. resets NiceGUI's globals (``nicegui.testing.user_simulation``),
2. registers the app's pages via :func:`pyaermod.gui_v2.app.build_app`,
3. opens ``/`` and interacts with the rendered elements.

Tests assert what the user sees: widget values, table rows, labels,
notifications and the header (PLAN-gui.md, "Rules for every GUI test").
The browser tab's :class:`~pyaermod.gui_v2.session.Session` is captured by
wrapping ``app._session_for``, and assertions on it only supplement the
visible ones. A second ``gui.open()`` on the same simulated user is a
reload of the same browser tab.

The ``gui`` fixture fails a test that leaves an ERROR log record from
``pyaermod`` or ``nicegui`` behind (an observer that raised, a live
section that failed to rebuild, a handler traceback): those are the
errors a user would never see on the page.

Requires the ``[gui]`` extra (nicegui) and ``pytest-asyncio``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import gc
import logging
import os
import platform
import re
from pathlib import Path
from typing import Any, List

import pytest

# The ``user_simulation`` context manager and ``ElementFilter(local_scope=)``
# used below both landed in NiceGUI 3.4.0 -- ``nicegui.testing.user_simulation``
# does not exist in 3.0-3.3.1. The *library* needs neither (nothing under
# src/ imports nicegui.testing), so the package floor stays at >=3.0 and this
# module skips instead: a bare minversion="3.0" guard let the min-deps leg
# past it and then died importing the missing module at collection time.
pytest.importorskip("nicegui", minversion="3.4.0")
pytest.importorskip(
    "nicegui.testing.user_simulation",
    reason="NiceGUI >=3.4.0 provides the user_simulation test harness",
)
pytest_asyncio = pytest.importorskip("pytest_asyncio")

from nicegui import Client, ElementFilter, binding, core, ui  # noqa: E402
from nicegui.testing import User  # noqa: E402
from nicegui.testing.user_interaction import UserInteraction  # noqa: E402
from nicegui.testing.user_simulation import user_simulation  # noqa: E402

from pyaermod.gui_v2 import app as app_module  # noqa: E402
from pyaermod.gui_v2 import session as session_module  # noqa: E402
from pyaermod.gui_v2.pages import results as results_page  # noqa: E402
from pyaermod.gui_v2.project_io import load_project, save_project  # noqa: E402
from pyaermod.gui_v2.session import Session  # noqa: E402
from pyaermod.input_generator import (  # noqa: E402
    AreaPolySource,
    OpenPitSource,
    PointSource,
    PollutantType,
)
from tests.e2e.harness import RECORDINGS, install_fake_aermod  # noqa: E402
from tests.e2e.reference import MAX_LOCATION, MAXIMA  # noqa: E402

from .test_gui_v2_session import _albany_project  # noqa: E402

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows", reason="fake AERMOD shims are POSIX shell scripts",
)

FOOTER = "PyAERMOD GUI v2 (NiceGUI)"


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

class GuiSession:
    """A simulated user plus the sessions its page loads resolved."""

    def __init__(self, user: User) -> None:
        self.user = user
        self.sessions: List[Session] = []
        self.expected_errors: List[re.Pattern] = []

    @property
    def session(self) -> Session:
        assert self.sessions, "no page was opened"
        return self.sessions[-1]

    async def open(self) -> Session:
        """Open ``/``; on the same user a second call is a reload of the tab."""
        await self.user.open("/")
        # The page is async: what it builds after the socket connects
        # arrives a moment later. The footer is built last.
        await self.user.should_see(FOOTER, retries=50)
        return self.session

    def expect_error_log(self, pattern: str) -> None:
        """Allow ERROR log records matching ``pattern`` in this test."""
        self.expected_errors.append(re.compile(pattern))


@pytest.fixture(scope="module", autouse=True)
def _cheap_garbage_collection():
    """Keep NiceGUI's per-test ``gc.collect()`` from walking every module.

    ``user_simulation`` collects garbage on exit, and with pyaermod, pandas
    and matplotlib loaded that walk costs about 0.1 s per test. Freezing
    the objects that exist now (imports, mostly) leaves them out of it.
    """
    gc.collect()
    gc.freeze()
    yield
    gc.unfreeze()


#: How often the fast ``should_see`` / ``should_not_see`` look again (s).
_POLL_S = 0.01


def _poll_faster(user: User) -> None:
    """Make ``user.should_see`` / ``should_not_see`` look every 10 ms.

    NiceGUI's versions look every 100 ms (50 ms for should_not_see), so
    every element that appears a moment late costs a tenth of a second.
    These wait just as long in total before failing, and fail with
    NiceGUI's own message.
    """
    if not hasattr(user, "_sees"):              # a NiceGUI without the private helper
        return
    original_see, original_not_see = user.should_see, user.should_not_see

    async def should_see(target=None, *, kind=None, marker=None, content=None, retries=3):
        deadline = asyncio.get_running_loop().time() + retries * 0.1
        while asyncio.get_running_loop().time() < deadline:
            if user._sees(target, kind, marker, content):
                return
            await asyncio.sleep(_POLL_S)
        await original_see(target, kind=kind, marker=marker, content=content, retries=1)

    async def should_not_see(target=None, *, kind=None, marker=None, content=None, retries=3):
        deadline = asyncio.get_running_loop().time() + retries * 0.05
        while asyncio.get_running_loop().time() < deadline:
            if not user._sees(target, kind, marker, content):
                return
            await asyncio.sleep(_POLL_S)
        await original_not_see(target, kind=kind, marker=marker, content=content, retries=1)

    user.should_see = should_see            # type: ignore[method-assign]
    user.should_not_see = should_not_see    # type: ignore[method-assign]


@pytest_asyncio.fixture
async def gui(monkeypatch, caplog):
    """Register the app's pages on a fresh NiceGUI and yield a GuiSession."""
    box: dict = {}
    original = app_module._session_for

    def _capturing(client):
        s = original(client)
        box["gui"].sessions.append(s)
        return s

    # index() looks ``_session_for`` up on its module at call time.
    monkeypatch.setattr(app_module, "_session_for", _capturing)
    caplog.set_level(logging.INFO)

    async with user_simulation(root=None) as user:
        # Bindings are polled; poll them ten times as often as NiceGUI's
        # default, so a test waits 10 ms rather than 100 ms for one.
        core.app.config.binding_refresh_interval = _POLL_S
        _poll_faster(user)
        app_module.build_app()
        # Why relabel ``__module__``: ``nicegui/testing/general.py``
        # (``nicegui_reset_globals``, the ``finally`` block) pops every
        # ``sys.modules`` entry for the module — and all its parent packages —
        # of each function in ``Client.page_routes`` whose ``__module__`` does
        # not start with ``tests.``. Our page function lives in
        # ``pyaermod.gui_v2.app``, so without this the first GUI test would
        # evict ``pyaermod``, ``pyaermod.gui_v2`` and ``pyaermod.gui_v2.app``
        # from ``sys.modules`` for the rest of the session. If a NiceGUI
        # upgrade changes that eviction rule, this is where it will show up.
        for func in list(Client.page_routes):
            if not func.__module__.startswith("tests."):
                func.__module__ = f"tests.{func.__module__}"
        g = GuiSession(user)
        box["gui"] = g
        yield g
        await asyncio.sleep(0.01)       # let pending refreshes run and log

    formatter = logging.Formatter()
    unexpected = []
    for record in caplog.get_records("setup") + caplog.get_records("call"):
        if record.levelno < logging.ERROR:
            continue
        if record.name.split(".")[0] not in ("pyaermod", "nicegui"):
            continue
        text = formatter.format(record)
        if not any(p.search(text) for p in g.expected_errors):
            unexpected.append(text)
    if unexpected:
        pytest.fail("ERROR log records a user would not see:\n" + "\n---\n".join(unexpected),
                    pytrace=False)


@pytest.fixture
def fake_aermod_on_path(fake_aermod_exe, monkeypatch):
    """Put the repo's no-op fake AERMOD (exit 0, no output) first on PATH."""
    monkeypatch.setenv("PATH", f"{fake_aermod_exe.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    return fake_aermod_exe


@pytest.fixture
def recorded_aermod(tmp_path, monkeypatch):
    """The end-to-end fake AERMOD on PATH, replaying a recording of the real one."""
    exe = install_fake_aermod(tmp_path / "fakebin")
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.delenv("PYAERMOD_E2E_DELAY", raising=False)
    monkeypatch.delenv("PYAERMOD_E2E_FAKE_LOG", raising=False)

    def use(recording: str) -> Path:
        monkeypatch.setenv("PYAERMOD_E2E_RECORDING", str(RECORDINGS / recording))
        return exe

    return use


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _by_id(elements, *, newest: bool = False):
    """Pick the oldest (default) or newest element of a ``find()`` result."""
    pick = max if newest else min
    return pick(elements, key=lambda e: e.id)


def _click(gui: GuiSession, element) -> None:
    UserInteraction(gui.user, {element}, None).click()


def _one(gui: GuiSession, **kw):
    return _by_id(gui.user.find(**kw).elements, newest=True)


def _sources_table(gui: GuiSession) -> ui.table:
    return _one(gui, kind=ui.table, marker="sources-table")


def _receptors_table(gui: GuiSession) -> ui.table:
    return _one(gui, kind=ui.table, marker="receptors-table")


def _sources_type_select(gui: GuiSession) -> ui.select:
    return _by_id(gui.user.find(kind=ui.select, content="Type").elements)


def _receptors_type_select(gui: GuiSession) -> ui.select:
    return _by_id(gui.user.find(kind=ui.select, content="Type").elements, newest=True)


def _choose(gui: GuiSession, select: ui.select, option: str) -> None:
    _click(gui, select)                  # open the popup
    gui.user.find(option).click()        # choose an option
    assert select.value == option


def _open_dialog(gui: GuiSession, marker: str) -> ui.dialog:
    with gui.user:
        dialogs = [d for d in ElementFilter(kind=ui.dialog, marker=marker, local_scope=False)
                   if d.value]
    assert len(dialogs) == 1, f"expected one open {marker!r}, found {len(dialogs)}"
    return dialogs[0]


def _in_dialog(gui: GuiSession, marker: str, kind, content: str) -> UserInteraction:
    """Select ``kind``/``content`` inside the one open dialog carrying ``marker``."""
    dialog = _open_dialog(gui, marker)
    with gui.user:
        found = set(ElementFilter(kind=kind, content=content, local_scope=False)
                    .within(instance=dialog))
    assert found, f"no {kind.__name__} with content {content!r} in the open {marker!r}"
    return UserInteraction(gui.user, found, content)


async def _dialog_opens(gui: GuiSession, marker: str) -> None:
    """Wait for the dialog carrying ``marker`` to open (async handlers open it later).

    The Open and Save As dialogs always exist, closed, so their text is
    on the page whether or not they are open.
    """
    for _ in range(200):
        if _open_dialogs(gui, marker):
            return
        await asyncio.sleep(_POLL_S)
    raise AssertionError(f"the {marker!r} did not open")


def _open_dialogs(gui: GuiSession, marker: str) -> list:
    with gui.user:
        return [d for d in ElementFilter(kind=ui.dialog, marker=marker, local_scope=False)
                if d.value]


def _editor_save(gui: GuiSession) -> None:
    _in_dialog(gui, "editor-dialog", ui.button, "Save").click()


def _editor_close(gui: GuiSession) -> None:
    _in_dialog(gui, "editor-dialog", ui.button, "Close").click()


def _add_source(gui: GuiSession) -> None:
    """Click the Sources "Add" (the older of the two Add buttons)."""
    _click(gui, _by_id(gui.user.find(kind=ui.button, content="Add").elements))


def _add_receptor(gui: GuiSession) -> None:
    _click(gui, _by_id(gui.user.find(kind=ui.button, content="Add").elements, newest=True))


def _interact(gui: GuiSession, element) -> UserInteraction:
    return UserInteraction(gui.user, {element}, None)


def _title_input(gui: GuiSession) -> ui.input:
    return _one(gui, kind=ui.input, content="Title (line 1)")


async def _settle(gui: GuiSession) -> None:
    """Let deferred refreshes and the 0.1 s binding poll run.

    Call it before asserting that something is *not* shown (such as the
    "(modified)" marker), after the rebuilt widgets already show their
    expected values.
    """
    for _ in range(3):
        await asyncio.sleep(0)
    await asyncio.sleep(3 * _POLL_S)


async def _rows_become(gui: GuiSession, table_of, key: str, expected: list) -> list:
    """Wait for a (possibly rebuilt) table to show ``expected`` in column ``key``."""
    for _ in range(150):
        rows = [r[key] for r in table_of(gui).rows]
        if rows == expected:
            return rows
        await asyncio.sleep(_POLL_S)
    raise AssertionError(f"table shows {rows}, expected {expected}")


async def _value_becomes(get, expected) -> None:
    for _ in range(150):
        if get() == expected:
            return
        await asyncio.sleep(_POLL_S)
    raise AssertionError(f"shows {get()!r}, expected {expected!r}")


async def _add_point_source(gui: GuiSession, sid: str, **numbers: float) -> None:
    _add_source(gui)
    await gui.user.should_see("Edit PointSource")
    _in_dialog(gui, "editor-dialog", ui.input, "source id").clear().type(sid)
    for label, value in numbers.items():
        _in_dialog(gui, "editor-dialog", ui.number, label.replace("_", " ")).clear().type(str(value))
    _editor_save(gui)
    await gui.user.should_see(kind=ui.table, marker="sources-table")


async def _fill_minimal_project(gui: GuiSession) -> Session:
    """Title + one point source + one receptor grid + met file names, via the UI."""
    session = await gui.open()
    gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("GUI smoke")
    await _add_point_source(gui, "STK1")
    await _rows_become(gui, _sources_table, "id", ["STK1"])
    _add_receptor(gui)
    await gui.user.should_see("Edit CartesianGrid")
    _editor_save(gui)
    await _rows_become(gui, _receptors_table, "kind", ["CartesianGrid"])
    gui.user.find(kind=ui.input, content="surface file").type("met.sfc")
    gui.user.find(kind=ui.input, content="profile file").type("met.pfl")
    return session


# ---------------------------------------------------------------------
# Shell + entry points
# ---------------------------------------------------------------------

class TestShell:
    @pytest.mark.asyncio
    async def test_index_renders_header_tabs_footer(self, gui):
        await gui.open()
        await gui.user.should_see("PyAERMOD")
        await gui.user.should_see(kind=ui.tab, content="Project")
        for name in ("Sources", "Receptors", "Meteorology", "Output", "Run", "Results"):
            await gui.user.should_see(kind=ui.tab, content=name)
        await gui.user.should_see(FOOTER)
        await gui.user.should_see("PyAERMOD — Untitled")

    @pytest.mark.asyncio
    async def test_each_tab_is_clickable(self, gui):
        await gui.open()
        for name in ("Sources", "Receptors", "Meteorology", "Output", "Run", "Results", "Project"):
            gui.user.find(kind=ui.tab, content=name).click()
            tabs = _by_id(gui.user.find(kind=ui.tabs).elements)
            assert tabs.value == name

    @pytest.mark.asyncio
    async def test_live_sections_cannot_nest(self, gui):
        from pyaermod.gui_v2._live import live
        session = await gui.open()
        with gui.user:
            @live(session)
            def _outer():
                with pytest.raises(RuntimeError, match="cannot be nested"):
                    live(session)(lambda: None)
                ui.label("outer built")
        await gui.user.should_see("outer built")


class TestEntryPoints:
    def test_main_calls_build_and_run(self, monkeypatch):
        from pyaermod import gui_v2
        called = {}
        monkeypatch.setattr(app_module, "build_and_run", lambda **kw: called.setdefault("called", True))
        gui_v2.main()
        assert called["called"]

    def test_build_and_run_forwards_options_to_ui_run(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(ui, "run", lambda **kw: captured.update(kw))
        monkeypatch.setattr(app_module, "build_app", lambda: captured.setdefault("built", True))
        app_module.build_and_run(host="0.0.0.0", port=9999, show=False, title="T", reload=False)
        assert captured["built"]
        assert captured["host"] == "0.0.0.0"
        assert captured["port"] == 9999
        assert captured["show"] is False
        assert captured["title"] == "T"
        assert captured["reload"] is False

    def test_build_and_run_default_title(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(ui, "run", lambda **kw: captured.update(kw))
        monkeypatch.setattr(app_module, "build_app", lambda: None)
        app_module.build_and_run()
        assert captured["title"] == "PyAERMOD"

    def test_redis_tab_storage_is_warned_about(self, monkeypatch, caplog):
        from nicegui.storage import Storage
        monkeypatch.setattr(Storage, "redis_url", "redis://example")
        with caplog.at_level(logging.WARNING, logger="pyaermod.gui_v2.app"):
            app_module._warn_if_redis()
        assert "NICEGUI_REDIS_URL" in caplog.text


# ---------------------------------------------------------------------
# One session per browser tab
# ---------------------------------------------------------------------

class TestSessionPerTab:
    @pytest.mark.asyncio
    async def test_reload_restores_project_and_marker(self, gui):
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Survives a reload")
        await _add_point_source(gui, "STACK1")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        first = gui.session

        await gui.open()                                   # reload, same tab
        assert gui.session is first
        assert _title_input(gui).value == "Survives a reload"
        assert [r["id"] for r in _sources_table(gui).rows] == ["STACK1"]
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        # The reloaded page edits the same session.
        _interact(gui, _title_input(gui)).clear().type("Edited after reload")
        assert first.project.control.title_one == "Edited after reload"

    @pytest.mark.asyncio
    async def test_reload_restores_last_run_status(self, gui, fake_aermod_on_path, tmp_path):
        gui.expect_error_log("AERMOD run failed: AERMOD exited with code 0 but wrote no")
        await gui.open()
        gui.user.find(kind=ui.input, content="Working directory").type(str(tmp_path / "run"))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Run reported FATAL or non-zero exit")
        await gui.open()                                   # reload
        await gui.user.should_see("Run reported FATAL or non-zero exit")
        await gui.user.should_see(f"Last run directory: {tmp_path / 'run'}")
        assert _one(gui, kind=ui.input, content="Working directory").value == str(tmp_path / "run")

    @pytest.mark.asyncio
    async def test_second_tab_gets_its_own_session(self, gui):
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Tab one")
        first = gui.session

        other = User(gui.user.http_client)                 # another browser tab
        await other.open("/")
        await other.should_see(FOOTER, retries=50)
        assert gui.session is not first
        assert _by_id(other.find(kind=ui.input, content="Title (line 1)").elements).value == "Untitled run"
        await other.should_not_see("(modified)")
        assert first.project.control.title_one == "Tab one"


# ---------------------------------------------------------------------
# Project tab
# ---------------------------------------------------------------------

class TestProjectPage:
    @pytest.mark.asyncio
    async def test_metadata_controls_render(self, gui):
        await gui.open()
        for label in ("New", "Open...", "Save", "Save as..."):
            await gui.user.should_see(kind=ui.button, content=label)
        await gui.user.should_see(kind=ui.input, content="Title (line 1)")
        await gui.user.should_see(kind=ui.input, content="Title (line 2)")
        await gui.user.should_see(kind=ui.select, content="Pollutant")

    @pytest.mark.asyncio
    async def test_typing_title_marks_dirty(self, gui):
        await gui.open()
        await _settle(gui)
        # Nothing marks a freshly opened project modified (the Meteorology
        # page used to, when it was built).
        await gui.user.should_not_see("(modified)")
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Smoke run")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        assert _title_input(gui).value == "Smoke run"
        assert gui.session.project.control.title_one == "Smoke run"

    @pytest.mark.asyncio
    async def test_title_two_blank_is_none(self, gui):
        from pyaermod.gui_v2.project_io import project_from_json
        await gui.open()
        line_two = _one(gui, kind=ui.input, content="Title (line 2)")
        UserInteraction(gui.user, {line_two}, None).type("Second")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        saved = project_from_json(await _save_as_download(gui, "two.json"))
        assert saved.control.title_two == "Second"
        assert "TITLETWO  Second" in saved.to_aermod_input(validate=False)

        # Emptying the box leaves no second title in the file or the deck.
        UserInteraction(gui.user, {_one(gui, kind=ui.input, content="Title (line 2)")},
                        None).clear()
        await gui.user.should_see("PyAERMOD — two.json (modified)")
        saved = project_from_json(await _save_as_download(gui, "two.json"))
        assert saved.control.title_two is None
        assert "TITLETWO" not in saved.to_aermod_input(validate=False)
        assert gui.session.project.control.title_two is None

    @pytest.mark.asyncio
    async def test_pollutant_select_updates_state(self, gui):
        await gui.open()
        target = next(p for p in PollutantType if p != PollutantType.SO2)
        select = _by_id(gui.user.find(kind=ui.select, content="Pollutant").elements)
        _choose(gui, select, target.value)
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        assert gui.session.project.control.pollutant_id == target

    @pytest.mark.asyncio
    async def test_new_resets_project(self, gui, tmp_path):
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Something else")
        await _add_point_source(gui, "OLD1")
        gui.user.find(kind=ui.input, content="surface file").type("old.sfc")
        await gui.user.should_see("(modified)")

        gui.user.find(kind=ui.button, marker="project-new").click()
        await gui.user.should_see("New project")
        await _value_becomes(lambda: _title_input(gui).value, "Untitled run")
        await _settle(gui)
        assert _sources_table(gui).rows == []
        await gui.user.should_see("No sources yet. Add one above.")
        assert _one(gui, kind=ui.input, content="surface file").value == ""
        await gui.user.should_see("No run yet. Use the Run tab to dispatch AERMOD.")
        await gui.user.should_not_see("(modified)")

    @pytest.mark.asyncio
    async def test_edits_after_new_reach_the_saved_file(self, gui, tmp_path):
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Project A")
        gui.user.find(kind=ui.button, marker="project-new").click()
        await _value_becomes(lambda: _title_input(gui).value, "Untitled run")
        _interact(gui, _title_input(gui)).clear().type("Project B")
        await _add_point_source(gui, "STACK1")
        await _rows_become(gui, _sources_table, "id", ["STACK1"])
        data = await _save_as_download(gui, "after_new.json")
        saved = tmp_path / "after_new.json"
        saved.write_bytes(data)
        project = load_project(saved)
        assert project.control.title_one == "Project B"
        assert [s.source_id for s in project.sources.sources] == ["STACK1"]

    @pytest.mark.asyncio
    async def test_no_widget_keeps_the_replaced_project(self, gui):
        """After New, nothing on the page may still reach the old project.

        This pins NiceGUI 3.x internals on purpose, as an architectural
        guard: it walks the binding tables and every element's event
        handlers (closures, bound methods and partials) looking for any
        object of the replaced project.
        """
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Old title")
        await _add_point_source(gui, "OLDSRC")
        _add_receptor(gui)
        await gui.user.should_see("Edit CartesianGrid")
        _editor_save(gui)
        await _rows_become(gui, _receptors_table, "kind", ["CartesianGrid"])
        gui.user.find(kind=ui.input, content="surface file").type("old.sfc")
        gui.user.find(kind=ui.input, content="summary file").type("old.sum")

        old_project = gui.session.project        # keep it alive: ids stay unique
        old_ids = _reachable_ids(old_project)

        gui.user.find(kind=ui.button, marker="project-new").click()
        await _value_becomes(lambda: _title_input(gui).value, "Untitled run")
        await _settle(gui)

        for link in binding.active_links:
            assert id(link[0]) not in old_ids and id(link[2]) not in old_ids, link
        for links in binding.bindings.values():
            for source, target, name, _transform in links:
                assert id(source) not in old_ids and id(target) not in old_ids, (target, name)
        client = gui.user.client
        assert client is not None
        for element in client.elements.values():
            handlers = [lst.handler for lst in element._event_listeners.values()]
            handlers += list(getattr(element, "_change_handlers", []))
            for handler in handlers:
                hit = _reaches(handler, old_ids)
                assert hit is None, f"{type(element).__name__} handler still holds {hit!r}"
        assert old_project.control.title_one == "Old title"


def _reachable_ids(root: Any) -> set:
    """ids of every dataclass, list and dict reachable from ``root``."""
    seen: set = set()
    stack = [root]
    while stack:
        obj = stack.pop()
        if id(obj) in seen:
            continue
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            seen.add(id(obj))
            stack.extend(getattr(obj, f.name) for f in dataclasses.fields(obj))
        elif isinstance(obj, (list, tuple)):
            if isinstance(obj, list):
                seen.add(id(obj))
            stack.extend(obj)
        elif isinstance(obj, dict):
            seen.add(id(obj))
            stack.extend(obj.values())
    return seen


def _reaches(handler: Any, old_ids: set, _visited: set | None = None) -> Any:
    """The first object of ``old_ids`` a callable's closure reaches, else None."""
    visited = _visited if _visited is not None else set()
    if handler is None or id(handler) in visited:
        return None
    visited.add(id(handler))
    if id(handler) in old_ids:
        return handler
    inner: list = []
    if isinstance(handler, functools.partial):
        inner = [handler.func, *handler.args, *handler.keywords.values()]
    elif hasattr(handler, "__self__") and hasattr(handler, "__func__"):
        inner = [handler.__self__, handler.__func__]
    elif getattr(handler, "__closure__", None):
        for cell in handler.__closure__:
            try:
                inner.append(cell.cell_contents)
            except ValueError:       # an empty cell
                continue
    for obj in inner:
        if id(obj) in old_ids:
            return obj
        if callable(obj):
            hit = _reaches(obj, old_ids, visited)
            if hit is not None:
                return hit
    return None


def _saved_with(path: tuple, value) -> bytes:
    """The Albany scenario as saved, with the value at ``project.<path>`` replaced."""
    import json

    from pyaermod.gui_v2.project_io import project_to_json

    doc = json.loads(project_to_json(_albany_project(["1", "ANNUAL"], "a.sfc")))
    node = doc["project"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return json.dumps(doc).encode("utf-8")


async def _save_as_download(gui: GuiSession, name: str) -> bytes:
    """Save As through the dialog; return the bytes the browser receives."""
    gui.user.find(kind=ui.button, marker="project-save-as").click()
    await _dialog_opens(gui, "save-as-dialog")
    _in_dialog(gui, "save-as-dialog", ui.input, "Filename").clear().type(name)
    _in_dialog(gui, "save-as-dialog", ui.button, "Save").click()
    response = await gui.user.download.next()
    return response.content


# ---------------------------------------------------------------------
# Project files: Open, Save, Save As
# ---------------------------------------------------------------------

class TestProjectFiles:
    @pytest.mark.asyncio
    async def test_save_as_dialog_saves_through_project_io(self, gui, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        before_tmp = set(Path("/tmp").glob("smoke*.json"))
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Saved title")
        data = await _save_as_download(gui, "smoke.json")
        await gui.user.should_see("Saved smoke.json")
        await gui.user.should_see("PyAERMOD — smoke.json")
        from pyaermod.gui_v2.project_io import project_from_json
        assert project_from_json(data).control.title_one == "Saved title"
        await _settle(gui)
        await gui.user.should_not_see("(modified)")
        assert _open_dialogs(gui, "save-as-dialog") == []
        # Nothing was written on the server: not in its working directory,
        # not in /tmp.
        assert list(tmp_path.iterdir()) == []
        assert set(Path("/tmp").glob("smoke*.json")) == before_tmp

    @pytest.mark.asyncio
    async def test_save_with_existing_path_saves_directly(self, gui, tmp_path):
        existing = save_project(_albany_project(["1", "ANNUAL"], "a.sfc"), tmp_path / "existing.json")
        session = await gui.open()
        session.open_json(existing)            # a saved project fixture
        await _value_becomes(lambda: _title_input(gui).value, "Albany stack reference scenario")
        _interact(gui, _title_input(gui)).clear().type("Changed")
        await gui.user.should_see("PyAERMOD — existing.json (modified)")
        gui.user.find(kind=ui.button, marker="project-save").click()
        await gui.user.should_see("Saved existing.json")
        assert load_project(existing).control.title_one == "Changed"
        await _settle(gui)
        await gui.user.should_not_see("(modified)")

    @pytest.mark.asyncio
    async def test_save_without_a_file_opens_save_as(self, gui):
        await gui.open()
        gui.user.find(kind=ui.button, marker="project-save").click()
        await _dialog_opens(gui, "save-as-dialog")
        assert _in_dialog(gui, "save-as-dialog", ui.input, "Filename").elements.pop().value == \
            "project.json"
        await _save_as_download_in_open_dialog(gui, "first.json")
        # Save again: the browser path has no file on disk, so the dialog
        # opens pre-filled and nothing is downloaded until it is confirmed.
        _interact(gui, _title_input(gui)).clear().type("Changed")
        gui.user.find(kind=ui.button, marker="project-save").click()
        await _dialog_opens(gui, "save-as-dialog")
        name = _in_dialog(gui, "save-as-dialog", ui.input, "Filename").elements.pop()
        assert name.value == "first.json"
        downloads_before = len(gui.user.download.http_responses)
        await _settle(gui)
        assert len(gui.user.download.http_responses) == downloads_before
        _in_dialog(gui, "save-as-dialog", ui.button, "Save").click()
        response = await gui.user.download.next()
        from pyaermod.gui_v2.project_io import project_from_json
        assert project_from_json(response.content).control.title_one == "Changed"

    @pytest.mark.asyncio
    async def test_native_save_as_writes_the_chosen_path_and_notifies(self, gui, tmp_path, monkeypatch):
        from pyaermod.gui_v2 import _native
        chosen = tmp_path / "n.json"
        asked: list = []
        monkeypatch.setattr(_native, "native_window", lambda: object())
        monkeypatch.setattr(_native, "ask_save_path", lambda name: asked.append(name) or chosen)
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Native")
        gui.user.find(kind=ui.button, marker="project-save-as").click()
        await gui.user.should_see("Saved n.json")
        await gui.user.should_see("PyAERMOD — n.json")
        assert asked == ["project.json"]
        assert load_project(chosen).control.title_one == "Native"
        assert _open_dialogs(gui, "save-as-dialog") == []
        # Save now writes back to that file without asking.
        _interact(gui, _title_input(gui)).clear().type("Native again")
        await gui.user.should_see("PyAERMOD — n.json (modified)")
        gui.user.find(kind=ui.button, marker="project-save").click()
        await _value_becomes(lambda: load_project(chosen).control.title_one, "Native again")
        await gui.user.should_not_see("(modified)")
        assert asked == ["project.json"]

    @pytest.mark.asyncio
    async def test_native_save_as_cancelled_does_nothing(self, gui, tmp_path, monkeypatch):
        from pyaermod.gui_v2 import _native
        monkeypatch.setattr(_native, "native_window", lambda: object())
        monkeypatch.setattr(_native, "ask_save_path", lambda name: None)
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Unsaved")
        gui.user.find(kind=ui.button, marker="project-save").click()
        await _settle(gui)
        await gui.user.should_not_see("Saved")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        assert _open_dialogs(gui, "save-as-dialog") == []

    @pytest.mark.asyncio
    async def test_native_save_as_write_failure_is_reported(self, gui, tmp_path, monkeypatch):
        from pyaermod.gui_v2 import _native
        blocker = tmp_path / "file"
        blocker.write_text("not a directory")
        monkeypatch.setattr(_native, "native_window", lambda: object())
        monkeypatch.setattr(_native, "ask_save_path", lambda name: blocker / "p.json")
        await gui.open()
        gui.user.find(kind=ui.button, marker="project-save-as").click()
        await gui.user.should_see("Save failed:")

    @pytest.mark.asyncio
    async def test_open_uploads_and_restores_project(self, gui, tmp_path):
        from nicegui.elements.upload_files import SmallFileUpload
        project = _albany_project(["1", "ANNUAL"], "AERMET2.SFC")
        project.control.title_one = "Uploaded"
        data = save_project(project, tmp_path / "saved.json").read_bytes()
        await gui.open()
        gui.user.find(kind=ui.button, marker="project-open").click()
        await _dialog_opens(gui, "open-dialog")
        await _upload(gui, SmallFileUpload("saved.json", "application/json", data))
        await gui.user.should_see("Loaded saved.json")
        await _value_becomes(lambda: _title_input(gui).value, "Uploaded")
        await _rows_become(gui, _sources_table, "id", ["STACK1"])
        await _rows_become(gui, _receptors_table, "label", ["GRID1"])
        await gui.user.should_see("PyAERMOD — saved.json")
        assert _open_dialogs(gui, "open-dialog") == []
        await _settle(gui)
        await gui.user.should_not_see("(modified)")

    @pytest.mark.parametrize("payload, reason", [
        (b"{not json", "not valid JSON"),
        (b'{"project": []}', "project must be a JSON object"),
        (b"\xff\xfe\x00{", "not a UTF-8 text file"),
        (_saved_with(("sources", "sources", 0, "_type"), "PointSorce"),
         "project.sources.sources[0]: unknown type 'PointSorce'"),
        (_saved_with(("sources", "sources", 0, "stack_height"), "tall"),
         "project.sources.sources[0].stack_height must be a number, not text 'tall'"),
        (_saved_with(("control", "pollutant_id"), {"_enum": "PollutantType.NOPE"}),
         "project.control.pollutant_id: unknown PollutantType member 'NOPE'"),
        (_saved_with(("sources", "sources", 0, "x_coord"), float("nan")),
         "project.sources.sources[0].x_coord must be a finite number, not nan"),
        (_saved_with(("sources", "sources", 0, "emission_rate"), float("inf")),
         "project.sources.sources[0].emission_rate must be a finite number, not inf"),
    ], ids=["invalid-json", "project-list", "undecodable", "unknown-source-type",
            "text-for-a-number", "unknown-pollutant", "nan-coordinate", "infinite-rate"])
    @pytest.mark.asyncio
    async def test_open_bad_file_reports_and_keeps_project(self, gui, tmp_path, payload, reason):
        from nicegui.elements.upload_files import SmallFileUpload
        await gui.open()
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Keep me")
        gui.user.find(kind=ui.button, marker="project-open").click()
        await _upload(gui, SmallFileUpload("bad.json", "application/json", payload))
        await gui.user.should_see(f"Load failed: bad.json: {reason}")
        assert len(_open_dialogs(gui, "open-dialog")) == 1       # still open
        assert _title_input(gui).value == "Keep me"
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        # The uploader was reset: a good file chosen next is sent.
        good = save_project(_albany_project(["1", "ANNUAL"], "a.sfc"), tmp_path / "good.json")
        await _upload(gui, SmallFileUpload("good.json", "application/json", good.read_bytes()))
        await gui.user.should_see("Loaded good.json")
        assert _open_dialogs(gui, "open-dialog") == []


    @pytest.mark.asyncio
    async def test_open_takes_any_file_name_and_refuses_a_non_project_by_name(self, gui, tmp_path):
        """The chooser does not filter by extension: QUploader drops a file its
        ``accept`` filters out without a word, and a project whose name lost
        its .json (an e-mail attachment, a renamed download) must open."""
        from nicegui.elements.upload_files import SmallFileUpload
        await gui.open()
        gui.user.find(kind=ui.button, marker="project-open").click()
        await _dialog_opens(gui, "open-dialog")
        with gui.user:
            uploader = next(iter(ElementFilter(kind=ui.upload, local_scope=False)))
        assert "accept" not in uploader.props
        await _upload(gui, SmallFileUpload("notes.txt", "text/plain", b"shopping list"))
        await gui.user.should_see("Load failed: notes.txt: not valid JSON")
        good = save_project(_albany_project(["1", "ANNUAL"], "a.sfc"), tmp_path / "p.json")
        await _upload(gui, SmallFileUpload("pit_project", "", good.read_bytes()))
        await gui.user.should_see("Loaded pit_project")
        await gui.user.should_see("PyAERMOD — pit_project")

    @pytest.mark.asyncio
    async def test_save_as_refuses_a_project_its_file_could_not_reopen(self, gui):
        """An emptied number box leaves no number; saving says which field,
        delivers no file and leaves the project marked modified."""
        await gui.open()
        _add_source(gui)
        await gui.user.should_see("Edit PointSource")
        _in_dialog(gui, "editor-dialog", ui.number, "emission rate").clear()
        _editor_save(gui)
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        downloads_before = len(gui.user.download.http_responses)
        gui.user.find(kind=ui.button, marker="project-save-as").click()
        await _dialog_opens(gui, "save-as-dialog")
        _in_dialog(gui, "save-as-dialog", ui.input, "Filename").clear().type("broken.json")
        _in_dialog(gui, "save-as-dialog", ui.button, "Save").click()
        await gui.user.should_see(
            "Save failed: cannot save the project: "
            "project.sources.sources[0].emission_rate must be a number, not null")
        await _settle(gui)
        assert len(gui.user.download.http_responses) == downloads_before
        assert _open_dialogs(gui, "save-as-dialog") == []
        await gui.user.should_see("PyAERMOD — Untitled (modified)")

    @pytest.mark.asyncio
    async def test_save_failure_is_reported(self, gui, tmp_path):
        existing = save_project(_albany_project(["1", "ANNUAL"], "a.sfc"), tmp_path / "gone.json")
        session = await gui.open()
        session.open_json(existing)             # a saved project fixture
        await _value_becomes(lambda: _title_input(gui).value, "Albany stack reference scenario")
        _interact(gui, _title_input(gui)).clear().type("Changed")
        existing.unlink()
        existing.mkdir()                        # the file's place is taken: writing fails
        gui.user.find(kind=ui.button, marker="project-save").click()
        await gui.user.should_see("Save failed:")
        await gui.user.should_see("PyAERMOD — gone.json (modified)")

    @pytest.mark.asyncio
    async def test_a_pollutant_outside_the_list_is_shown_kept_and_survives_a_reload(self, gui):
        from nicegui.elements.upload_files import SmallFileUpload

        from pyaermod.gui_v2.project_io import project_from_json
        await gui.open()
        gui.user.find(kind=ui.button, marker="project-open").click()
        await _dialog_opens(gui, "open-dialog")
        data = _saved_with(("control", "pollutant_id"), "TSP")     # fugitive dust
        await _upload(gui, SmallFileUpload("dust.json", "application/json", data))
        await gui.user.should_see("Loaded dust.json")
        pollutant = lambda: _one(gui, kind=ui.select, content="Pollutant").value  # noqa: E731
        await _value_becomes(pollutant, "TSP")

        await gui.open()                        # reload: the page builds in full
        await _value_becomes(pollutant, "TSP")
        await gui.user.should_see(kind=ui.button, content="Run AERMOD")
        saved = project_from_json(await _save_as_download(gui, "dust.json"))
        assert saved.control.pollutant_id == "TSP"
        assert "POLLUTID  TSP" in saved.to_aermod_input(validate=False)

        _choose(gui, _one(gui, kind=ui.select, content="Pollutant"), "PM10")
        await gui.user.should_see("PyAERMOD — dust.json (modified)")
        assert gui.session.project.control.pollutant_id == PollutantType.PM10

    @pytest.mark.asyncio
    async def test_a_section_that_fails_does_not_stop_the_page(self, gui, monkeypatch):
        """A section that cannot show the project says so; the rest of the
        page is built, and so is the section once the project changes."""
        from pyaermod.gui_v2._live import SECTION_FAILED
        from pyaermod.gui_v2.pages import sources as sources_page
        gui.expect_error_log("could not build the _table section")
        await gui.open()
        await _add_point_source(gui, "STK1")
        await _rows_become(gui, _sources_table, "id", ["STK1"])

        def broken(src):
            raise ValueError("cannot summarise this source")

        monkeypatch.setattr(sources_page, "_summary_row", broken)
        await gui.open()                        # reload: Sources cannot be shown
        await gui.user.should_see(f"{SECTION_FAILED}: cannot summarise this source")
        await gui.user.should_see(kind=ui.button, content="Run AERMOD")      # later steps
        await gui.user.should_see("No run yet. Use the Run tab to dispatch AERMOD.")
        gui.user.find(kind=ui.button, marker="project-new").click()
        await gui.user.should_see("No sources yet. Add one above.")         # rebuilt
        await gui.user.should_not_see(SECTION_FAILED)

    @pytest.mark.asyncio
    async def test_deleted_pages_leave_no_subscriptions_behind(self, gui):
        session = await gui.open()
        per_page = len(session._observers)
        assert per_page > 0
        first_client = gui.user.client
        await gui.open()                        # two reloads of the same tab
        second_client = gui.user.client
        await gui.open()
        assert gui.session is session
        assert len(session._observers) == 3 * per_page
        with gui.user:
            first_client.delete()
            second_client.delete()
        assert len(session._observers) == per_page
        assert app_module._OWNERS[id(session)] == {gui.user.client}


async def _save_as_download_in_open_dialog(gui: GuiSession, name: str) -> bytes:
    _in_dialog(gui, "save-as-dialog", ui.input, "Filename").clear().type(name)
    _in_dialog(gui, "save-as-dialog", ui.button, "Save").click()
    return (await gui.user.download.next()).content


async def _upload(gui: GuiSession, upload) -> None:
    """Send ``upload`` through the Open dialog's uploader, as the browser would."""
    dialog = _open_dialog(gui, "open-dialog")
    with gui.user:
        uploader = next(iter(ElementFilter(kind=ui.upload, local_scope=False).within(instance=dialog)))
        await uploader.handle_uploads([upload])
    for _ in range(5):
        await asyncio.sleep(0)


# ---------------------------------------------------------------------
# Sources tab
# ---------------------------------------------------------------------

class TestSourcesPage:
    @pytest.mark.asyncio
    async def test_empty_state_and_controls(self, gui):
        await gui.open()
        await gui.user.should_see("No sources yet. Add one above.")
        await gui.user.should_see(kind=ui.select, content="Type")
        await gui.user.should_see(kind=ui.button, content="Add")
        await gui.user.should_see(kind=ui.table, marker="sources-table")

    @pytest.mark.asyncio
    async def test_add_point_source_through_editor(self, gui):
        await gui.open()
        _add_source(gui)
        await gui.user.should_see("Edit PointSource")
        # Add only adds on Save: the open editor holds a draft.
        assert _sources_table(gui).rows == []
        _in_dialog(gui, "editor-dialog", ui.input, "source id").clear().type("STK1")
        _in_dialog(gui, "editor-dialog", ui.number, "stack height").clear().type("35")
        _editor_save(gui)
        await _rows_become(gui, _sources_table, "id", ["STK1"])
        await gui.user.should_not_see("No sources yet")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        assert _open_dialogs(gui, "editor-dialog") == []
        src = gui.session.project.sources.sources[0]
        assert isinstance(src, PointSource) and src.stack_height == 35.0

    @pytest.mark.asyncio
    async def test_close_after_add_adds_nothing(self, gui):
        await gui.open()
        _add_source(gui)
        await gui.user.should_see("Edit PointSource")
        _editor_close(gui)
        await _settle(gui)
        assert _sources_table(gui).rows == []
        await gui.user.should_see("No sources yet. Add one above.")
        await gui.user.should_not_see("(modified)")

    @pytest.mark.asyncio
    async def test_edit_and_delete_events(self, gui):
        """The per-row edit/delete buttons emit table events; drive those."""
        await gui.open()
        await _add_point_source(gui, "STK1", emission_rate=5)
        await _rows_become(gui, _sources_table, "id", ["STK1"])
        key = _sources_table(gui).rows[0]["key"]

        # Close after an edit discards it.
        UserInteraction(gui.user, {_sources_table(gui)}, None).trigger("edit", key)
        await gui.user.should_see("Edit PointSource — STK1")
        _in_dialog(gui, "editor-dialog", ui.number, "emission rate").clear().type("99")
        _editor_close(gui)
        await _settle(gui)
        assert _sources_table(gui).rows[0]["Q (g/s)"] == 5.0

        # Save updates the row.
        UserInteraction(gui.user, {_sources_table(gui)}, None).trigger("edit", key)
        _in_dialog(gui, "editor-dialog", ui.number, "emission rate").clear().type("150")
        _editor_save(gui)
        await _rows_become(gui, _sources_table, "Q (g/s)", [150.0])

        # Delete shows the empty state; a second delete of the same row
        # (a stale event) does nothing.
        table = _sources_table(gui)
        UserInteraction(gui.user, {table}, None).trigger("delete", key)
        await gui.user.should_see("Deleted STK1")
        await _rows_become(gui, _sources_table, "id", [])
        await gui.user.should_see("No sources yet. Add one above.")
        UserInteraction(gui.user, {_sources_table(gui)}, None).trigger("delete", key)
        UserInteraction(gui.user, {_sources_table(gui)}, None).trigger("edit", key)
        await _settle(gui)
        assert _open_dialogs(gui, "editor-dialog") == []
        assert gui.session.project.sources.sources == []

    @pytest.mark.asyncio
    async def test_polygon_and_buoyant_line_summaries(self, gui):
        """Sources without x_coord summarise from vertices / segments."""
        await gui.open()
        for type_name in ("AreaPolySource", "BuoyLineSource"):
            _choose(gui, _sources_type_select(gui), type_name)
            _add_source(gui)
            await gui.user.should_see(f"Edit {type_name}")
            _editor_save(gui)
            await _settle(gui)
        rows = _sources_table(gui).rows
        assert [r["type"] for r in rows] == ["AreaPolySource", "BuoyLineSource"]
        assert (rows[0]["x"], rows[0]["y"]) == (0.0, 0.0)   # first vertex
        assert (rows[1]["x"], rows[1]["y"]) == (0.0, 0.0)   # first segment start

    @pytest.mark.asyncio
    async def test_vertices_textarea_parses_pairs(self, gui):
        await gui.open()
        _choose(gui, _sources_type_select(gui), "AreaPolySource")
        _add_source(gui)
        await gui.user.should_see("Edit AreaPolySource")
        ta = _by_id(_in_dialog(gui, "editor-dialog", ui.textarea, "vertices").elements)
        with gui.user:
            ta.value = "10, 20\n50; 0\n\n50, 50\nnot a pair\n0, 50"
        UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        _editor_save(gui)
        await _rows_become(gui, _sources_table, "x", [10.0])
        # Reopening the editor shows the parsed vertices.
        key = _sources_table(gui).rows[0]["key"]
        UserInteraction(gui.user, {_sources_table(gui)}, None).trigger("edit", key)
        ta = _by_id(_in_dialog(gui, "editor-dialog", ui.textarea, "vertices").elements)
        assert ta.value.splitlines() == ["10, 20", "50, 0", "50, 50", "0, 50"]


# ---------------------------------------------------------------------
# Receptors tab
# ---------------------------------------------------------------------

class TestReceptorsPage:
    @pytest.mark.asyncio
    async def test_add_cartesian_grid(self, gui):
        await gui.open()
        gui.user.find(kind=ui.tab, content="Receptors").click()
        await gui.user.should_see("No receptors yet. Add one above.")
        # Two "Add" buttons exist (Sources, Receptors).
        assert len(gui.user.find(kind=ui.button, content="Add").elements) == 2
        _add_receptor(gui)
        await gui.user.should_see("Edit CartesianGrid")
        _in_dialog(gui, "editor-dialog", ui.number, "x num").clear().type("11")
        _editor_save(gui)
        await _rows_become(gui, _receptors_table, "summary", ["11.0 x 21"])
        await gui.user.should_not_see("No receptors yet")
        assert [r["label"] for r in _receptors_table(gui).rows] == ["GRID1"]

    @pytest.mark.asyncio
    async def test_edit_and_delete_events(self, gui):
        await gui.open()
        _add_receptor(gui)
        await gui.user.should_see("Edit CartesianGrid")
        _editor_save(gui)
        await _rows_become(gui, _receptors_table, "kind", ["CartesianGrid"])
        key = _receptors_table(gui).rows[0]["key"]

        UserInteraction(gui.user, {_receptors_table(gui)}, None).trigger("edit", key)
        _in_dialog(gui, "editor-dialog", ui.input, "grid name").clear().type("CLOSED")
        _editor_close(gui)
        await _settle(gui)
        assert [r["label"] for r in _receptors_table(gui).rows] == ["GRID1"]

        UserInteraction(gui.user, {_receptors_table(gui)}, None).trigger("edit", key)
        _in_dialog(gui, "editor-dialog", ui.input, "grid name").clear().type("SAVED")
        _editor_save(gui)
        await _rows_become(gui, _receptors_table, "label", ["SAVED"])

        UserInteraction(gui.user, {_receptors_table(gui)}, None).trigger("delete", key)
        await gui.user.should_see("Deleted CartesianGrid[0]")
        await _rows_become(gui, _receptors_table, "kind", [])
        await gui.user.should_see("No receptors yet. Add one above.")
        UserInteraction(gui.user, {_receptors_table(gui)}, None).trigger("delete", key)
        await _settle(gui)
        assert gui.session.project.receptors.cartesian_grids == []

    @pytest.mark.asyncio
    async def test_polar_and_discrete(self, gui):
        await gui.open()
        for name in ("PolarGrid", "DiscreteReceptor"):
            _choose(gui, _receptors_type_select(gui), name)
            _add_receptor(gui)
            await gui.user.should_see(f"Edit {name}")
            _editor_save(gui)
            await _settle(gui)
        rows = _receptors_table(gui).rows
        assert [r["kind"] for r in rows] == ["PolarGrid", "DiscreteReceptor"]
        assert [r["summary"] for r in rows] == ["10 dist x 36 dir", "(0.0, 0.0)"]


# ---------------------------------------------------------------------
# Meteorology / Output tabs + shared form helper
# ---------------------------------------------------------------------

class TestMeteorologyAndOutputPages:
    @pytest.mark.asyncio
    async def test_met_file_inputs_bind_to_state(self, gui):
        await gui.open()
        await _settle(gui)
        await gui.user.should_not_see("(modified)")
        gui.user.find(kind=ui.input, content="surface file").type("met.sfc")
        gui.user.find(kind=ui.input, content="profile file").type("met.pfl")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        assert _one(gui, kind=ui.input, content="surface file").value == "met.sfc"
        assert gui.session.project.meteorology.surface_file == "met.sfc"
        assert gui.session.project.meteorology.profile_file == "met.pfl"
        await gui.user.should_see(kind=ui.expansion, content="Advanced")

    @pytest.mark.asyncio
    async def test_output_page_renders_primary_fields(self, gui):
        await gui.open()
        await gui.user.should_see("Files + format")
        # Optional[str] fields are editable text inputs
        gui.user.find(kind=ui.input, content="summary file").type("run.sum")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        assert _one(gui, kind=ui.input, content="summary file").value == "run.sum"
        assert gui.session.project.output.summary_file == "run.sum"

    @pytest.mark.asyncio
    async def test_list_of_str_textarea(self, gui):
        await gui.open()
        ta = _by_id(gui.user.find(kind=ui.textarea, content="plot file groups").elements)
        with gui.user:
            ta.value = "ALL\n\n GRP1 "
        UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        await gui.user.should_see("PyAERMOD — Untitled (modified)")
        assert gui.session.project.output.plot_file_groups == ["ALL", "GRP1"]

    @pytest.mark.asyncio
    async def test_leaving_a_number_field_keeps_its_exact_value(self, gui, tmp_path):
        """Tabbing through a field changes nothing: an open-pit emission rate
        of 1.5e-6 g/s/m^2 once became 0.0 when the field lost focus."""
        from pyaermod.gui_v2.project_io import project_from_json
        project = _albany_project(["1", "ANNUAL"], "a.sfc")
        project.meteorology.profile_base_elevation = 10.123456
        project.sources.sources = [OpenPitSource(source_id="PIT1", x_coord=0.0, y_coord=0.0,
                                                 emission_rate=1.5e-6)]
        path = save_project(project, tmp_path / "precise.json")
        session = await gui.open()
        session.open_json(path)                 # a saved project fixture
        field = "profile base elevation"
        await _value_becomes(lambda: _one(gui, kind=ui.number, content=field).value, 10.123456)
        number = _one(gui, kind=ui.number, content=field)
        with gui.user:
            number.sanitize()                   # what ui.number does on blur
        assert number.value == 10.123456

        await _rows_become(gui, _sources_table, "id", ["PIT1"])
        UserInteraction(gui.user, {_sources_table(gui)}, None).trigger(
            "edit", _sources_table(gui).rows[0]["key"])
        await gui.user.should_see("Edit OpenPitSource — PIT1")
        rate = next(iter(_in_dialog(gui, "editor-dialog", ui.number, "emission rate").elements))
        with gui.user:
            rate.sanitize()
        assert rate.value == 1.5e-6
        _editor_save(gui)
        await _settle(gui)
        await gui.user.should_see("PyAERMOD — precise.json (modified)")   # Save was clicked
        saved = project_from_json(await _save_as_download(gui, "precise.json"))
        assert saved.sources.sources[0].emission_rate == 1.5e-6
        assert saved.meteorology.profile_base_elevation == 10.123456

    @pytest.mark.asyncio
    async def test_number_blur_without_edit_does_not_mark_dirty(self, gui, tmp_path):
        project = _albany_project(["1", "ANNUAL"], "a.sfc")
        project.meteorology.profile_base_elevation = 10.123456
        session = await gui.open()
        session.open_json(save_project(project, tmp_path / "precise.json"))
        field = "profile base elevation"
        await _value_becomes(lambda: _one(gui, kind=ui.number, content=field).value, 10.123456)
        number = _one(gui, kind=ui.number, content=field)
        with gui.user:
            number.sanitize()
        await _settle(gui)
        await gui.user.should_not_see("(modified)")
        # A real edit does mark it.
        UserInteraction(gui.user, {number}, None).clear().type("12")
        await gui.user.should_see("PyAERMOD — precise.json (modified)")

    @pytest.mark.asyncio
    async def test_emit_form_subset_and_unknown_field(self, gui):
        from pyaermod.gui_v2._form import emit_form
        await gui.open()
        src = PointSource(
            source_id="F1", x_coord=1.0, y_coord=2.0, stack_height=10.0,
            stack_diameter=1.0, stack_temp=400.0, exit_velocity=10.0, emission_rate=1.0,
        )
        with gui.user:
            emit_form(ui.column(), src, fields=["source_id", "stack_height", "no_such_field"])
        gui.user.find(kind=ui.input, content="source id").clear().type("F2")
        assert src.source_id == "F2"
        _one(gui, kind=ui.number, content="stack height").value = 12
        assert src.stack_height == 12.0


class TestFormChangeHook:
    """``emit_field(on_change=...)``: the hook the pages mark the project dirty with."""

    @staticmethod
    def _point() -> PointSource:
        return PointSource(
            source_id="H1", x_coord=0.0, y_coord=0.0, stack_height=10.0,
            stack_diameter=1.0, stack_temp=400.0, exit_velocity=10.0,
            emission_rate=1.0, building_height=[1.0] * 36,
        )

    @pytest.mark.asyncio
    async def test_on_change_follows_real_edits_only(self, gui):
        from pyaermod.gui_v2._form import emit_form
        await gui.open()
        src = self._point()
        calls: list = []
        with gui.user:
            emit_form(ui.column(), src, on_change=lambda: calls.append(1),
                      fields=["source_id", "stack_height", "is_urban", "building_height"])
        assert calls == []                              # not called while building
        gui.user.find(kind=ui.input, content="source id").type("X")
        assert len(calls) == 1
        number = _one(gui, kind=ui.number, content="stack height")
        with gui.user:
            number.sanitize()                           # leaving the field: no edit
        assert len(calls) == 1
        number.value = 10.00001                         # every change is kept, and is an edit
        assert len(calls) == 2 and src.stack_height == 10.00001
        number.value = None                             # cleared: an edit
        assert len(calls) == 3
        _one(gui, kind=ui.checkbox, content="is urban").value = True
        assert len(calls) == 4
        ta = _one(gui, kind=ui.textarea, content="building height")
        with gui.user:
            ta.value = "2\n" * 36
        UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        assert len(calls) == 5 and src.building_height == [2.0] * 36


class TestBuildingDimensionWidgets:
    """``Optional[Union[float, List[float]]]`` must stay *editable*.

    The five building-downwash dimensions take either one value for all
    directions or 36, one per 10-degree wind sector. Tightening
    ``is_numeric`` to reject unions containing a list correctly excluded
    them from the number branch — and dropped them into the read-only-label
    escape hatch, so a building height could no longer be typed at all.
    ``emit_field`` now dispatches on the *current* value: number box for a
    scalar or an unset field, list editor once the field holds a vector.
    """

    @staticmethod
    def _point() -> PointSource:
        return PointSource(
            source_id="B1", x_coord=0.0, y_coord=0.0, stack_height=10.0,
            stack_diameter=1.0, stack_temp=400.0, exit_velocity=10.0,
            emission_rate=1.0,
        )

    @pytest.mark.asyncio
    async def test_unset_dimension_is_an_editable_number_box(self, gui):
        from pyaermod.gui_v2._form import emit_form
        await gui.open()
        src = self._point()
        assert src.building_height is None
        with gui.user:
            emit_form(ui.column(), src, fields=["building_height"])
        # The regression rendered this as ``ui.label("building height: None")``.
        with pytest.raises(AssertionError):
            gui.user.find(kind=ui.label, content="building height")
        num = _by_id(gui.user.find(kind=ui.number, content="building height").elements)
        assert num.value is None            # unset stays unset, not 0.0
        gui.user.find(kind=ui.number, content="building height").type("25")
        assert src.building_height == 25.0

    @pytest.mark.asyncio
    async def test_scalar_dimension_shows_its_value_and_clears_to_none(self, gui):
        from pyaermod.gui_v2._form import emit_form
        await gui.open()
        src = self._point()
        src.building_width = 12.5
        with gui.user:
            emit_form(ui.column(), src, fields=["building_width"])
        num = _by_id(gui.user.find(kind=ui.number, content="building width").elements)
        assert num.value == 12.5
        # ``clearable`` is the only way back to None from the UI, and None
        # is the only value the writer omits -- without the prop a typed-in
        # dimension could never be taken back out of the deck.
        assert num._props.get("clearable") is True
        # Clearing must store None, not 0.0: _building_downwash_lines()
        # emits BUILDWID for anything that is not None.
        gui.user.find(kind=ui.number, content="building width").clear()
        assert src.building_width is None

    @pytest.mark.asyncio
    async def test_list_dimension_gets_the_list_editor(self, gui):
        from pyaermod.gui_v2._form import emit_form
        await gui.open()
        src = self._point()
        src.building_length = [float(i) for i in range(36)]
        with gui.user:
            emit_form(ui.column(), src, fields=["building_length"])
        # A number box here would collapse the 36-sector vector to one value.
        ta = _by_id(gui.user.find(kind=ui.textarea, content="building length").elements)
        assert ta.value.splitlines()[:3] == ["0", "1", "2"]
        assert src.building_length == [float(i) for i in range(36)]   # render is read-only
        with gui.user:
            ta.value = "\n".join(str(2 * i) for i in range(36)) + "\nnot a number\n"
        UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        assert src.building_length == [float(2 * i) for i in range(36)]

    @pytest.mark.asyncio
    async def test_emptied_list_editor_stores_none_not_empty_list(self, gui):
        from pyaermod.gui_v2._form import emit_form
        await gui.open()
        src = self._point()
        src.building_y_offset = [1.0] * 36
        with gui.user:
            emit_form(ui.column(), src, fields=["building_y_offset"])
        ta = _by_id(gui.user.find(kind=ui.textarea, content="building y offset").elements)
        with gui.user:
            ta.value = "  \n\n"
        UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        # [] would make _format_building_keyword raise "requires exactly 36
        # values"; None is the field's real "no building" state.
        assert src.building_y_offset is None

    @pytest.mark.asyncio
    async def test_polygon_vertices_still_get_the_vertex_textarea(self, gui):
        """The new branch must not steal ``List[Tuple[float, float]]``.

        Handing polygon vertices to ``ui.number`` once crashed the editor.
        """
        from pyaermod.gui_v2._form import emit_form
        await gui.open()
        poly = AreaPolySource(
            source_id="P1", vertices=[(0.0, 0.0), (50.0, 0.0), (50.0, 50.0)],
        )
        with gui.user:
            emit_form(ui.column(), poly, fields=["vertices"])
        with pytest.raises(AssertionError):
            gui.user.find(kind=ui.number, content="vertices")
        ta = _by_id(gui.user.find(kind=ui.textarea, content="vertices").elements)
        assert ta.value.splitlines() == ["0, 0", "50, 0", "50, 50"]
        with gui.user:
            ta.value = "1, 2\n3, 4\n5, 6"
        UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        assert poly.vertices == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]


# ---------------------------------------------------------------------
# End-to-end: fill a minimal project, round-trip it, run it
# ---------------------------------------------------------------------

def _agrees(shown: str, expected: float) -> bool:
    """True if ``shown`` is ``expected`` rounded to the digits it displays."""
    value = float(shown)
    mantissa, _, exponent = shown.lower().partition("e")
    decimals = len(mantissa.partition(".")[2])
    scale = 10 ** (int(exponent) if exponent else 0)
    return abs(value - expected) <= 0.5 * 10 ** -decimals * scale * (1 + 1e-9)


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_save_load_round_trip(self, gui, tmp_path):
        session = await _fill_minimal_project(gui)
        data = await _save_as_download(gui, "smoke.json")
        (tmp_path / "smoke.json").write_bytes(data)
        loaded = load_project(tmp_path / "smoke.json")
        assert loaded.control.title_one == "GUI smoke"
        assert [s.source_id for s in loaded.sources.sources] == ["STK1"]
        assert len(loaded.receptors.cartesian_grids) == 1
        assert loaded.meteorology.surface_file == "met.sfc"
        assert loaded.meteorology.profile_file == "met.pfl"
        assert loaded.to_aermod_input(validate=False) == session.project.to_aermod_input(validate=False)

    @pytest.mark.asyncio
    async def test_run_with_noop_fake_aermod_reports_failure(self, gui, fake_aermod_on_path, tmp_path):
        """The repo's no-op fake exits 0 but writes no .OUT -> runner says failed."""
        gui.expect_error_log("AERMOD run failed: AERMOD exited with code 0 but wrote no")
        await _fill_minimal_project(gui)
        await gui.user.should_not_see("No 'aermod' binary on PATH")
        workdir = tmp_path / "run"
        gui.user.find(kind=ui.input, content="Working directory").type(str(workdir))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("AERMOD started")
        await gui.user.should_see("Run reported FATAL or non-zero exit")
        # The deck is written under its own name; the runner points the
        # fixed aermod.inp symlink at it (a deck *named* aermod.inp would
        # be unlinked and replaced by a self-referencing symlink).
        deck = workdir / "pyaermod_gui.inp"
        assert deck.exists() and "STK1" in deck.read_text()
        # Results follows the run by itself (defect D2).
        gui.user.find(kind=ui.tab, content="Results").click()
        await gui.user.should_see(f"Last run directory: {workdir}")
        await gui.user.should_see("(no .OUT file found in working directory)")
        await gui.user.should_not_see("No run yet")

    @pytest.mark.asyncio
    async def test_results_follow_a_recorded_run(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        path = save_project(_albany_project(["1", "3", "24", "PERIOD"], "AERMET2.SFC"),
                            tmp_path / "albany.json")
        session = await gui.open()
        session.open_json(path)
        await _value_becomes(lambda: _title_input(gui).value, "Albany stack reference scenario")
        workdir = tmp_path / "run"
        gui.user.find(kind=ui.input, content="Working directory").type(str(workdir))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        # A deck the recording does not match makes the fake exit 2: it
        # would show here as a failure.
        await gui.user.should_see("Run succeeded")
        await gui.user.should_see("Output file: pyaermod_gui.out")
        await gui.user.should_see("Max concentrations")
        tables = gui.user.find(kind=ui.table).elements
        maxima = next(t for t in tables if any(c["label"] == "Max" for c in t.columns))
        shown = {r["period"]: r for r in maxima.rows}
        for period, value in MAXIMA.items():
            row = shown[period]
            assert _agrees(row["value"], value), (period, row)
            assert (float(row["x"]), float(row["y"])) == pytest.approx(MAX_LOCATION)
        sources = next(t for t in tables if any(c["label"] == "Q (g/s)" for c in t.columns)
                       and t is not _sources_table(gui))
        assert [(r["id"], r["type"]) for r in sources.rows] == [("STACK1", "POINT")]

    @pytest.mark.asyncio
    async def test_results_placeholder_before_any_run(self, gui):
        await gui.open()
        await gui.user.should_see("No run yet. Use the Run tab to dispatch AERMOD.")

    @pytest.mark.asyncio
    async def test_run_page_warns_without_binary(self, gui, monkeypatch, tmp_path):
        monkeypatch.setenv("PATH", str(tmp_path))  # nothing on PATH
        await gui.open()
        await gui.user.should_see("No 'aermod' binary on PATH. Install AERMOD and re-launch.")
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("No AERMOD binary; cannot run.")


class TestRunPageFailurePaths:
    @pytest.mark.asyncio
    async def test_deck_generation_failure_is_reported(self, gui, fake_aermod_on_path, monkeypatch):
        session = await gui.open()

        def _boom(self, **kwargs):
            raise ValueError("boom")

        monkeypatch.setattr(type(session.project), "to_aermod_input", _boom)
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Could not generate deck: boom")
        await gui.user.should_see("No run yet. Use the Run tab to dispatch AERMOD.")

    @pytest.mark.asyncio
    async def test_deck_write_failure_is_reported(self, gui, fake_aermod_on_path, tmp_path):
        await gui.open()
        blocker = tmp_path / "file"
        blocker.write_text("not a directory")
        gui.user.find(kind=ui.input, content="Working directory").type(str(blocker))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Could not write the deck:")

    @pytest.mark.asyncio
    async def test_runner_exception_is_reported(self, gui, fake_aermod_on_path, monkeypatch, tmp_path):
        await _fill_minimal_project(gui)
        # binary was on PATH at render time but is gone when Run is clicked
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        gui.user.find(kind=ui.input, content="Working directory").type(str(tmp_path / "run"))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Run failed:")
        await gui.user.should_see("Run failed; see log")
        # A run that never started leaves Results as it was.
        await gui.user.should_see("No run yet. Use the Run tab to dispatch AERMOD.")


class TestResultsPageMore:
    @pytest.mark.asyncio
    async def test_postfiles_listed(self, gui, recorded_aermod, tmp_path):
        recorded_aermod("albany_success")
        path = save_project(_albany_project(["1", "3", "24", "PERIOD"], "AERMET2.SFC"),
                            tmp_path / "albany.json")
        wd = tmp_path / "run"
        (wd / "postfiles").mkdir(parents=True)
        # Input fixtures already in the working directory, not fake output.
        (wd / "RUN1.PST").write_text("x" * 2048)
        (wd / "postfiles" / "RUN2.PST").write_text("y")
        session = await gui.open()
        session.open_json(path)
        await _value_becomes(lambda: _title_input(gui).value, "Albany stack reference scenario")
        gui.user.find(kind=ui.input, content="Working directory").type(str(wd))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Run succeeded")
        await gui.user.should_see("Output file: pyaermod_gui.out")
        await gui.user.should_see("POSTFILE outputs")
        await gui.user.should_see("RUN1.PST  (2.0 KiB)")
        await gui.user.should_see("RUN2.PST")

    @pytest.mark.asyncio
    async def test_parse_failure_is_reported(self, gui, recorded_aermod, tmp_path, monkeypatch):
        import pyaermod.output_parser as op

        class _Boom:
            def __init__(self, path):
                raise RuntimeError("boom")

        recorded_aermod("albany_success")
        path = save_project(_albany_project(["1", "3", "24", "PERIOD"], "AERMET2.SFC"),
                            tmp_path / "albany.json")
        monkeypatch.setattr(op, "AERMODOutputParser", _Boom)
        session = await gui.open()
        session.open_json(path)
        await _value_becomes(lambda: _title_input(gui).value, "Albany stack reference scenario")
        gui.user.find(kind=ui.input, content="Working directory").type(str(tmp_path / "run"))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Run succeeded")
        await gui.user.should_see("Could not parse pyaermod_gui.out: boom")

    def test_ensure_path_helper(self):
        assert results_page._ensure_path("a/b") == Path("a/b")
        p = Path("c")
        assert results_page._ensure_path(p) is p
