"""Headless smoke tests for the NiceGUI GUI (``pyaermod.gui_v2``).

Drives the real app shell through ``nicegui.testing.User`` — an in-process
ASGI client with a simulated browser session. No server socket, no
browser, no selenium. Each test:

1. resets NiceGUI's globals (``nicegui.testing.user_simulation``),
2. registers the app's pages via :func:`pyaermod.gui_v2.app.build_app`,
3. opens ``/`` and interacts with the rendered elements.

The per-session :class:`~pyaermod.gui_v2.state.AppState` is created
inside the page function; the ``gui`` fixture captures it by patching
the ``AppState`` symbol that ``build_app`` looks up, so tests can assert
on the project tree the UI mutated.

Requires the ``[gui]`` extra (nicegui) and ``pytest-asyncio``.
"""

from __future__ import annotations

import os
import platform
import textwrap
from pathlib import Path

import pytest

# The ``user_simulation`` context manager / ``ElementFilter(local_scope=)``
# used below are NiceGUI 3.x APIs; the app itself only needs the 2.0 floor.
pytest.importorskip("nicegui", minversion="3.0")
pytest_asyncio = pytest.importorskip("pytest_asyncio")

from nicegui import Client, ElementFilter, ui  # noqa: E402
from nicegui.testing import User  # noqa: E402
from nicegui.testing.user_interaction import UserInteraction  # noqa: E402
from nicegui.testing.user_simulation import user_simulation  # noqa: E402

from pyaermod.gui_v2 import app as app_module  # noqa: E402
from pyaermod.gui_v2.pages import project as project_page  # noqa: E402
from pyaermod.gui_v2.pages import results as results_page  # noqa: E402
from pyaermod.gui_v2.project_io import load_project, save_project  # noqa: E402
from pyaermod.gui_v2.state import AppState  # noqa: E402
from pyaermod.input_generator import (  # noqa: E402
    AreaPolySource,
    CartesianGrid,
    PointSource,
    PollutantType,
)

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows", reason="fake AERMOD shims are POSIX shell scripts",
)

# Minimal AERMOD .OUT that the output parser turns into run_info,
# one source, two receptors and one ANNUAL concentration table.
FAKE_AERMOD_OUT = textwrap.dedent("""\
    *** AERMOD - VERSION 24142 ***

    Jobname: GUI_SMOKE
    Run Date: 01-15-26
    Run Time: 10:30:00

    ** Model Setup Options Selected **

    *** SOURCE LOCATIONS ***

       SOURCE   TYPE       X-COORD      Y-COORD    BASE_ELEV
       STK1     POINT      0.00         0.00        10.00

    *** RECEPTOR LOCATIONS ***

       X-COORD      Y-COORD
       100.00       200.00
       300.00       400.00

    *** ANNUAL RESULTS ***

       100.00    200.00    5.432
       300.00    400.00    2.876
""")


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

class GuiSession:
    """A simulated user plus a handle on the page's AppState."""

    def __init__(self, user: User) -> None:
        self.user = user
        self.state: AppState | None = None

    async def open(self) -> AppState:
        await self.user.open("/")
        assert self.state is not None, "index() did not create an AppState"
        return self.state


@pytest_asyncio.fixture
async def gui(monkeypatch):
    """Register the app's pages on a fresh NiceGUI and yield a GuiSession."""
    session_box: dict = {}

    def _capturing_state() -> AppState:
        st = AppState()
        session_box["session"].state = st
        return st

    # build_app() looks ``AppState`` up on its own module at call time.
    monkeypatch.setattr(app_module, "AppState", _capturing_state)

    async with user_simulation(root=None) as user:
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
        session = GuiSession(user)
        session_box["session"] = session
        yield session


@pytest.fixture
def fake_aermod_on_path(fake_aermod_exe, monkeypatch):
    """Put the repo's no-op fake AERMOD (exit 0, no output) first on PATH."""
    monkeypatch.setenv("PATH", f"{fake_aermod_exe.parent}{os.pathsep}{os.environ.get('PATH', '')}")
    return fake_aermod_exe


@pytest.fixture
def fake_aermod_with_output(tmp_path, monkeypatch):
    """A fake AERMOD that writes a parseable ``aermod.out`` then exits 0."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    exe = bindir / "aermod"
    exe.write_text(
        "#!/bin/bash\ncat > aermod.out <<'EOF'\n" + FAKE_AERMOD_OUT + "EOF\nexit 0\n"
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return exe


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _by_id(elements, *, newest: bool = False):
    """Pick the oldest (default) or newest element of a ``find()`` result."""
    pick = max if newest else min
    return pick(elements, key=lambda e: e.id)


def _click(gui: GuiSession, element) -> None:
    UserInteraction(gui.user, {element}, None).click()


def _sources_table(gui: GuiSession) -> ui.table:
    """The Sources tab table (rendered before the Receptors one)."""
    return _by_id(gui.user.find(kind=ui.table).elements)


def _sources_type_select(gui: GuiSession) -> ui.select:
    return _by_id(gui.user.find(kind=ui.select, content="Type").elements)


def _receptors_type_select(gui: GuiSession) -> ui.select:
    return _by_id(gui.user.find(kind=ui.select, content="Type").elements, newest=True)


def _in_newest_dialog(gui: GuiSession, kind, content: str) -> UserInteraction:
    """Select ``kind``/``content`` inside the most recently opened dialog.

    ``user.scope(kind=ui.dialog)`` insists on exactly one dialog; closed
    dialogs stay in the element tree, so multi-dialog flows need this.
    """
    dialog = _by_id(gui.user.find(kind=ui.dialog).elements, newest=True)
    with gui.user:
        found = set(ElementFilter(kind=kind, content=content, local_scope=False).within(instance=dialog))
    assert found, f"no {kind.__name__} with content {content!r} in newest dialog"
    return UserInteraction(gui.user, found, content)


def _render_results(gui: GuiSession) -> None:
    """Re-render the Results tab against the current state.

    The shell renders every tab once when the page is opened, so after a
    run the Results panel still shows the pre-run placeholder until the
    page is rebuilt; rendering into the live client is how a rebuild is
    exercised without losing the per-session state.
    """
    with gui.user:
        results_page.render(gui.state)


async def _fill_minimal_project(gui: GuiSession) -> AppState:
    """Title + one point source + one receptor grid + met file names."""
    state = await gui.open()
    gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("GUI smoke")
    # one point source via the Sources tab editor
    gui.user.find(kind=ui.button, content="Add").click()
    with gui.user.scope(kind=ui.dialog):
        gui.user.find(kind=ui.input, content="source id").clear().type("STK1")
        gui.user.find(kind=ui.button, content="Save").click()
    # one receptor grid via state (the Receptors "Add" button is covered
    # in TestReceptorsPage)
    state.project.receptors.cartesian_grids.append(
        CartesianGrid(grid_name="GRID1", x_init=-500, y_init=-500,
                      x_num=11, y_num=11, x_delta=100, y_delta=100),
    )
    # met file names via the Meteorology tab
    gui.user.find(kind=ui.input, content="surface file").type("met.sfc")
    gui.user.find(kind=ui.input, content="profile file").type("met.pfl")
    return state


# ---------------------------------------------------------------------
# Shell + entry points
# ---------------------------------------------------------------------

class TestShell:
    @pytest.mark.asyncio
    async def test_index_renders_header_tabs_footer(self, gui):
        state = await gui.open()
        await gui.user.should_see("PyAERMOD")
        await gui.user.should_see(kind=ui.tab, content="Project")
        for name in ("Sources", "Receptors", "Meteorology", "Output", "Run", "Results"):
            await gui.user.should_see(kind=ui.tab, content=name)
        await gui.user.should_see("PyAERMOD GUI v2 (NiceGUI)")
        # header binds to state.title
        assert state.title.startswith("PyAERMOD — Untitled")
        await gui.user.should_see("PyAERMOD — Untitled")

    @pytest.mark.asyncio
    async def test_each_tab_is_clickable(self, gui):
        await gui.open()
        for name in ("Sources", "Receptors", "Meteorology", "Output", "Run", "Results", "Project"):
            gui.user.find(kind=ui.tab, content=name).click()
            tabs = _by_id(gui.user.find(kind=ui.tabs).elements)
            assert tabs.value == name


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
        state = await gui.open()
        # meteorology.render() stamps the state dirty at render time (see
        # the comment there), so start from a clean slate explicitly.
        state.mark_clean()
        assert not state.dirty
        gui.user.find(kind=ui.input, content="Title (line 1)").clear().type("Smoke run")
        assert state.project.control.title_one == "Smoke run"
        # Setting .value programmatically does not fire the client->server
        # update event the dirty handler listens on; fire it as a browser
        # would (nicegui stores listener types camel-cased).
        gui.user.find(kind=ui.input, content="Title (line 1)").trigger("update:modelValue")
        assert state.dirty
        await gui.user.should_see("PyAERMOD — Untitled (modified)")

    @pytest.mark.asyncio
    async def test_pollutant_select_updates_state(self, gui):
        state = await gui.open()
        target = next(p for p in PollutantType if p != state.project.control.pollutant_id)
        select = _by_id(gui.user.find(kind=ui.select, content="Pollutant").elements)
        _click(gui, select)                       # open the popup
        gui.user.find(target.value).click()       # choose an option
        assert select.value == target.value
        assert state.project.control.pollutant_id == target
        assert state.dirty

    @pytest.mark.asyncio
    async def test_new_resets_project(self, gui):
        state = await gui.open()
        state.project.control.title_one = "Something else"
        state.mark_dirty()
        gui.user.find(kind=ui.button, content="New").click()
        assert state.project.control.title_one == "Untitled run"
        assert not state.dirty
        await gui.user.should_see("New project")

    @pytest.mark.asyncio
    async def test_save_as_dialog_saves_through_project_io(self, gui, tmp_path, monkeypatch):
        saved: dict = {}

        def _fake_save(project, target):
            # keep the test off /tmp: redirect the write into tmp_path
            saved["path"] = save_project(project, tmp_path / Path(target).name)
            return saved["path"]

        monkeypatch.setattr(project_page, "save_project", _fake_save)
        state = await gui.open()
        gui.user.find(kind=ui.button, content="Save as...").click()
        await gui.user.should_see("Save project as")
        with gui.user.scope(kind=ui.dialog):
            gui.user.find(kind=ui.input, content="Filename").clear().type("smoke.json")
            gui.user.find(kind=ui.button, content="Save").click()
        await gui.user.should_see("Saved smoke.json")
        assert saved["path"].exists()
        assert state.project_path is not None and state.project_path.name == "smoke.json"
        assert not state.dirty
        assert load_project(saved["path"]).control.title_one == state.project.control.title_one

    @pytest.mark.asyncio
    async def test_save_with_existing_path_saves_directly(self, gui, tmp_path, monkeypatch):
        calls = []

        def _fake_save(project, target):
            calls.append(Path(target))
            return save_project(project, tmp_path / Path(target).name)

        monkeypatch.setattr(project_page, "save_project", _fake_save)
        state = await gui.open()
        state.project_path = tmp_path / "existing.json"
        state.mark_dirty()
        # "Save" also substring-matches "Save as..."; click() takes the
        # lowest id, which is the plain Save button.
        gui.user.find(kind=ui.button, content="Save").click()
        assert calls == [tmp_path / "existing.json"]
        assert not state.dirty
        await gui.user.should_see("Saved existing.json")

    @pytest.mark.asyncio
    async def test_save_without_path_falls_back_to_save_as(self, gui):
        state = await gui.open()
        assert state.project_path is None
        gui.user.find(kind=ui.button, content="Save").click()
        await gui.user.should_see("Save project as")

    @pytest.mark.asyncio
    async def test_open_dialog_appears(self, gui):
        await gui.open()
        gui.user.find(kind=ui.button, content="Open...").click()
        await gui.user.should_see("Select project JSON", retries=10)
        await gui.user.should_see(kind=ui.upload)


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
        await gui.user.should_see(kind=ui.table)

    @pytest.mark.asyncio
    async def test_add_point_source_through_editor(self, gui):
        state = await gui.open()
        gui.user.find(kind=ui.button, content="Add").click()
        assert len(state.project.sources.sources) == 1
        src = state.project.sources.sources[0]
        assert isinstance(src, PointSource)
        await gui.user.should_see("Edit PointSource")
        with gui.user.scope(kind=ui.dialog):
            gui.user.find(kind=ui.input, content="source id").clear().type("STK1")
            gui.user.find(kind=ui.number, content="stack height").clear().type("35")
            gui.user.find(kind=ui.button, content="Save").click()
        assert src.source_id == "STK1"
        assert src.stack_height == 35.0
        assert state.dirty
        # table refreshed with the new row
        assert [r["id"] for r in _sources_table(gui).rows] == ["STK1"]

    @pytest.mark.asyncio
    async def test_edit_and_delete_events(self, gui):
        """The per-row edit/delete buttons emit table events; drive those."""
        state = await gui.open()
        gui.user.find(kind=ui.button, content="Add").click()
        with gui.user.scope(kind=ui.dialog):
            gui.user.find(kind=ui.button, content="Close").click()
        sid = state.project.sources.sources[0].source_id
        table = _sources_table(gui)
        UserInteraction(gui.user, {table}, None).trigger("edit", sid)
        assert len(gui.user.find(kind=ui.dialog).elements) == 2   # a second editor opened
        await gui.user.should_see(f"Edit PointSource — {sid}")
        UserInteraction(gui.user, {table}, None).trigger("delete", sid)
        assert state.project.sources.sources == []
        assert table.rows == []
        await gui.user.should_see(f"Deleted {sid}")

    @pytest.mark.asyncio
    async def test_polygon_and_buoyant_line_summaries(self, gui):
        """Sources without x_coord summarise from vertices / segments."""
        state = await gui.open()
        for type_name in ("AreaPolySource", "BuoyLineSource"):
            _click(gui, _sources_type_select(gui))       # open the popup
            gui.user.find(type_name).click()             # pick the option
            assert _sources_type_select(gui).value == type_name
            gui.user.find(kind=ui.button, content="Add").click()
            _in_newest_dialog(gui, ui.button, "Close").click()
        rows = _sources_table(gui).rows
        assert [r["type"] for r in rows] == ["AreaPolySource", "BuoyLineSource"]
        assert (rows[0]["x"], rows[0]["y"]) == (0.0, 0.0)   # first vertex
        assert (rows[1]["x"], rows[1]["y"]) == (0.0, 0.0)   # first segment start
        assert isinstance(state.project.sources.sources[0], AreaPolySource)

    @pytest.mark.asyncio
    async def test_vertices_textarea_parses_pairs(self, gui):
        state = await gui.open()
        _click(gui, _sources_type_select(gui))
        gui.user.find("AreaPolySource").click()
        gui.user.find(kind=ui.button, content="Add").click()
        src = state.project.sources.sources[0]
        with gui.user.scope(kind=ui.dialog):
            ta = _by_id(gui.user.find(kind=ui.textarea, content="vertices").elements)
            with gui.user:
                ta.value = "0, 0\n50; 0\n\n50, 50\nnot a pair\n0, 50"
            UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        assert src.vertices == [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)]


# ---------------------------------------------------------------------
# Receptors tab
# ---------------------------------------------------------------------

class TestReceptorsPage:
    @pytest.mark.asyncio
    async def test_add_cartesian_grid(self, gui):
        state = await gui.open()
        gui.user.find(kind=ui.tab, content="Receptors").click()
        await gui.user.should_see("No receptors yet. Add one above.")
        # Two "Add" buttons exist (Sources, Receptors); ``find().click()``
        # picks the lowest id, so target the Receptors one explicitly.
        add_buttons = gui.user.find(kind=ui.button, content="Add").elements
        assert len(add_buttons) == 2
        _click(gui, _by_id(add_buttons, newest=True))
        assert len(state.project.receptors.cartesian_grids) == 1
        grid = state.project.receptors.cartesian_grids[0]
        assert isinstance(grid, CartesianGrid)
        await gui.user.should_see("Edit CartesianGrid")
        with gui.user.scope(kind=ui.dialog):
            gui.user.find(kind=ui.number, content="x num").clear().type("11")
            gui.user.find(kind=ui.button, content="Save").click()
        assert grid.x_num == 11

    @pytest.mark.asyncio
    async def test_edit_and_delete_events(self, gui):
        state = await gui.open()
        _click(gui, _by_id(gui.user.find(kind=ui.button, content="Add").elements, newest=True))
        _in_newest_dialog(gui, ui.button, "Close").click()
        assert len(state.project.receptors.cartesian_grids) == 1
        table = _by_id(gui.user.find(kind=ui.table).elements, newest=True)   # receptors table
        assert [r["kind"] for r in table.rows] == ["CartesianGrid"]
        UserInteraction(gui.user, {table}, None).trigger("edit", "CartesianGrid:0")
        assert len(gui.user.find(kind=ui.dialog).elements) == 2
        UserInteraction(gui.user, {table}, None).trigger("delete", "CartesianGrid:0")
        assert state.project.receptors.cartesian_grids == []
        assert table.rows == []
        await gui.user.should_see("Deleted CartesianGrid[0]")

    @pytest.mark.asyncio
    async def test_polar_and_discrete(self, gui):
        state = await gui.open()
        for name in ("PolarGrid", "DiscreteReceptor"):
            _click(gui, _receptors_type_select(gui))
            gui.user.find(name).click()
            assert _receptors_type_select(gui).value == name
            _click(gui, _by_id(gui.user.find(kind=ui.button, content="Add").elements, newest=True))
            _in_newest_dialog(gui, ui.button, "Close").click()
        table = _by_id(gui.user.find(kind=ui.table).elements, newest=True)
        assert [r["kind"] for r in table.rows] == ["PolarGrid", "DiscreteReceptor"]
        assert len(state.project.receptors.polar_grids) == 1
        assert len(state.project.receptors.discrete_receptors) == 1


# ---------------------------------------------------------------------
# Meteorology / Output tabs + shared form helper
# ---------------------------------------------------------------------

class TestMeteorologyAndOutputPages:
    @pytest.mark.asyncio
    async def test_met_file_inputs_bind_to_state(self, gui):
        state = await gui.open()
        gui.user.find(kind=ui.input, content="surface file").type("met.sfc")
        gui.user.find(kind=ui.input, content="profile file").type("met.pfl")
        assert state.project.meteorology.surface_file == "met.sfc"
        assert state.project.meteorology.profile_file == "met.pfl"
        await gui.user.should_see(kind=ui.expansion, content="Advanced")

    @pytest.mark.asyncio
    async def test_output_page_renders_primary_fields(self, gui):
        state = await gui.open()
        await gui.user.should_see("Files + format")
        # Optional[str] fields are editable text inputs
        gui.user.find(kind=ui.input, content="summary file").type("run.sum")
        assert state.project.output.summary_file == "run.sum"

    @pytest.mark.asyncio
    async def test_list_of_str_textarea(self, gui):
        state = await gui.open()
        ta = _by_id(gui.user.find(kind=ui.textarea, content="plot file groups").elements)
        with gui.user:
            ta.value = "ALL\n\n GRP1 "
        UserInteraction(gui.user, {ta}, None).trigger("update:modelValue")
        assert state.project.output.plot_file_groups == ["ALL", "GRP1"]

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
        gui.user.find(kind=ui.number, content="stack height").clear().type("12")
        assert src.stack_height == 12.0


# ---------------------------------------------------------------------
# End-to-end: fill a minimal project, round-trip it, run it
# ---------------------------------------------------------------------

class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_save_load_round_trip(self, gui, tmp_path):
        state = await _fill_minimal_project(gui)
        path = save_project(state.project, tmp_path / "smoke.json")
        loaded = load_project(path)
        assert loaded.control.title_one == "GUI smoke"
        assert [s.source_id for s in loaded.sources.sources] == ["STK1"]
        assert len(loaded.receptors.cartesian_grids) == 1
        assert loaded.meteorology.surface_file == "met.sfc"
        assert loaded.meteorology.profile_file == "met.pfl"
        assert loaded.to_aermod_input(validate=False) == state.project.to_aermod_input(validate=False)

    @pytest.mark.asyncio
    async def test_run_with_noop_fake_aermod_reports_failure(self, gui, fake_aermod_on_path, tmp_path):
        """The repo's no-op fake exits 0 but writes no .OUT -> runner says failed."""
        state = await _fill_minimal_project(gui)
        await gui.user.should_not_see("No 'aermod' binary on PATH")
        workdir = tmp_path / "run"
        gui.user.find(kind=ui.input, content="Working directory").type(str(workdir))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("AERMOD started")
        await gui.user.should_see("Run reported FATAL or non-zero exit")
        assert state.last_run_dir == workdir
        # The deck is written under its own name; the runner points the
        # fixed aermod.inp symlink at it (a deck *named* aermod.inp would
        # be unlinked and replaced by a self-referencing symlink).
        deck = workdir / "pyaermod_gui.inp"
        assert deck.exists() and "STK1" in deck.read_text()
        _render_results(gui)
        await gui.user.should_see(f"Last run directory: {workdir}")
        await gui.user.should_see("(no .OUT file found in working directory)")

    @pytest.mark.asyncio
    async def test_run_with_output_renders_results_tab(self, gui, fake_aermod_with_output, tmp_path):
        state = await _fill_minimal_project(gui)
        workdir = tmp_path / "run"
        gui.user.find(kind=ui.input, content="Working directory").type(str(workdir))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Run succeeded")
        assert state.last_run_dir == workdir
        # runner renames AERMOD's aermod.out to <deck stem>.out
        assert (workdir / "pyaermod_gui.out").exists()
        _render_results(gui)
        await gui.user.should_see("Output file: pyaermod_gui.out")
        await gui.user.should_see("GUI_SMOKE")          # jobname from run_info
        await gui.user.should_see("Max concentrations")
        conc_table = _by_id(gui.user.find(kind=ui.table).elements, newest=True)
        assert [r["period"] for r in conc_table.rows] == ["ANNUAL"]
        assert conc_table.rows[0]["value"] == "5.432"
        assert (conc_table.rows[0]["x"], conc_table.rows[0]["y"]) == (100.0, 200.0)

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
        state = await gui.open()

        def _boom(self, **kwargs):
            raise ValueError("boom")

        monkeypatch.setattr(type(state.project), "to_aermod_input", _boom)
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Could not generate deck: boom")
        assert state.last_run_dir is None

    @pytest.mark.asyncio
    async def test_runner_exception_is_reported(self, gui, fake_aermod_on_path, monkeypatch, tmp_path):
        state = await _fill_minimal_project(gui)
        # binary was on PATH at render time but is gone when Run is clicked
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        gui.user.find(kind=ui.input, content="Working directory").type(str(tmp_path / "run"))
        gui.user.find(kind=ui.button, content="Run AERMOD").click()
        await gui.user.should_see("Run failed:")
        assert state.last_run_dir is None


class TestResultsPageMore:
    @pytest.mark.asyncio
    async def test_postfiles_listed(self, gui, tmp_path):
        state = await gui.open()
        wd = tmp_path / "run"
        (wd / "postfiles").mkdir(parents=True)
        (wd / "x.out").write_text(FAKE_AERMOD_OUT)
        (wd / "RUN1.PST").write_text("x" * 2048)
        (wd / "postfiles" / "RUN2.PST").write_text("y")
        state.last_run_dir = wd
        _render_results(gui)
        await gui.user.should_see("Output file: x.out")
        await gui.user.should_see("POSTFILE outputs")
        await gui.user.should_see("RUN1.PST  (2.0 KiB)")
        await gui.user.should_see("RUN2.PST")

    @pytest.mark.asyncio
    async def test_parse_failure_is_reported(self, gui, tmp_path, monkeypatch):
        import pyaermod.output_parser as op

        class _Boom:
            def __init__(self, path):
                raise RuntimeError("boom")

        monkeypatch.setattr(op, "AERMODOutputParser", _Boom)
        state = await gui.open()
        wd = tmp_path / "run"
        wd.mkdir()
        (wd / "x.out").write_text("")
        state.last_run_dir = wd
        _render_results(gui)
        await gui.user.should_see("Could not parse x.out: boom")

    def test_ensure_path_helper(self):
        assert results_page._ensure_path("a/b") == Path("a/b")
        p = Path("c")
        assert results_page._ensure_path(p) is p
