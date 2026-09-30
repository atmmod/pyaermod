"""
Project step: the project file, the titles and pollutant, the averaging
periods and the model options.

The file operations (New, Open, Save, Save As) are a :class:`FileActions`
built once per page, because the header's Save button uses them too. New
and Open ask before they discard unsaved changes. The editable fields are
live sections rebuilt whenever the project is replaced, so they always
show the project the session holds.

Files never pass through the server's disk in the browser: Open reads the
uploaded file's text, and Save As hands the browser a download. In
``pyaermod-desktop`` Save As asks where to save through a native dialog
and Save writes back to that file.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from ...input_generator import PollutantType, TerrainType
from ...naaqs import naaqs_averaging_periods
from ...validator import VALID_AVERAGING_PERIODS
from .. import _native, files
from .._layout import Goto, confirm, section, step_page
from .._live import live
from ..session import ProjectFileError, Session

#: AERMOD's averaging periods, in the order AVERTIME lists them.
AVERAGING_PERIODS: List[str] = sorted(
    VALID_AVERAGING_PERIODS,
    key=lambda p: (0, int(p)) if p.isdigit() else (1, ["MONTH", "PERIOD", "ANNUAL"].index(p)),
)

#: The terrain choices, as MODELOPT spells them.
TERRAIN_CHOICES = {
    TerrainType.FLAT.value: "Flat (FLAT)",
    TerrainType.ELEVATED.value: "Elevated (ELEV)",
    TerrainType.FLATSRCS.value: "Elevated, some sources flat (FLAT ELEV)",
}

#: What AERMOD computes (MODELOPT), as the check boxes read.
OUTPUT_OPTIONS = (
    ("calculate_concentration", "Concentration (CONC)"),
    ("calculate_deposition", "Total deposition (DEPOS)"),
    ("calculate_dry_deposition", "Dry deposition (DDEP)"),
    ("calculate_wet_deposition", "Wet deposition (WDEP)"),
)

#: Beside the deposition check boxes, until a step edits deposition parameters.
DEPOSITION_NOTE = ("Deposition also needs each source's deposition parameters, which the "
                   "GUI cannot enter yet: they come only from an opened or imported project.")

#: What a save can raise: the disk (OSError), or a project holding a value
#: its file could not be reopened with (ValueError, TypeError).
_SAVE_ERRORS = (OSError, ValueError, TypeError)


def sort_periods(periods: List[str]) -> List[str]:
    """Averaging periods in AVERTIME's order; unknown ones keep their place at the end."""
    known = [p for p in AVERAGING_PERIODS if p in periods]
    return known + [p for p in periods if p not in AVERAGING_PERIODS]


class FileActions:
    """New, Open, Save and Save As for one page, and the dialogs they use.

    Built once per page in the page's static dialog container
    (``dialogs``): the Open and Save As dialogs live as long as the page.
    """

    def __init__(self, session: Session, *, dialogs: Any):
        from nicegui import ui

        self.session = session
        self.dialogs = dialogs

        with dialogs, ui.dialog().mark("open-dialog") as self.open_dialog, ui.card():
            ui.label("Open a project file").classes("text-h6")
            # auto_upload sends the file as soon as it is chosen; the
            # header's upload button (an unnamed icon) is hidden. No
            # ``accept`` filter: QUploader drops a file it filters out
            # without a word, and a project whose name lost its .json must
            # still open. Every file reaches _on_upload, which refuses a
            # non-project by name.
            self.uploader = ui.upload(
                label="Project file (.json)", auto_upload=True, max_files=1,
                on_upload=self._on_upload,
            ).props("hide-upload-btn")
            ui.button("Cancel", on_click=self.open_dialog.close).props("flat")

        with dialogs, ui.dialog().mark("save-as-dialog") as self.save_as_dialog, ui.card():
            ui.label("Save project as").classes("text-h6")
            self.name_input = ui.input("Filename", value=session.suggested_file_name())
            with ui.row():
                ui.button("Cancel", on_click=self.save_as_dialog.close).props("flat")
                ui.button("Save", on_click=self._do_save).props("color=primary")

    # ----- New ----------------------------------------------------------
    def _asked_before_replacing(self, what: str, on_yes: Callable[[], Any]) -> bool:
        """Ask before ``what`` (New, or opening a file) replaces the project,
        when that loses unsaved changes or stops a run in progress; return
        whether the question was asked (``on_yes`` then does the rest)."""
        session = self.session
        running = session.run_in_progress
        if not session.dirty and running is None:
            return False
        stop = (f" Run {running.number}, still in progress, is stopped."
                if running is not None else "")
        if session.dirty:
            confirm(self.dialogs, question="Discard unsaved changes?",
                    detail=f"{what}; the changes you have not saved, and the runs of this "
                           f"project, are lost.{stop}",
                    yes="Discard changes", on_yes=on_yes)
        else:
            confirm(self.dialogs, question="Stop the run in progress?",
                    detail=f"{what}; the runs of this project are lost.{stop}",
                    yes="Stop the run", on_yes=on_yes)
        return True

    def new(self) -> None:
        if not self._asked_before_replacing("New starts a blank project", self._new):
            self._new()

    def _new(self) -> None:
        self.session.new()
        _notify(f"New project. Title: {self.session.project.control.title_one!r}")

    # ----- Open ---------------------------------------------------------
    def open(self) -> None:
        self.open_dialog.open()

    async def _on_upload(self, e) -> None:
        name = e.file.name
        try:
            # Read inside the handler: an upload over 1 MiB is a temporary
            # file that goes away with the event. Bytes, so that a file that
            # is not UTF-8 text is refused with its name like any other.
            data = await e.file.read()
            # Checked on a scratch session first: a file that cannot be
            # opened is refused (and the dialog stays open) before anything
            # asks about the project it would have replaced.
            Session().open_json(data, name=name)
        except ProjectFileError as exc:
            _notify(f"Load failed: {exc}", color="negative")
            return                                  # the dialog stays open
        finally:
            # Always, so choosing the same file again sends it again.
            self.uploader.reset()
        self.open_dialog.close()
        # Asked once the file has arrived, so that closing the Open dialog
        # (or cancelling a slow upload) never asks anything.
        if not self._asked_before_replacing(f"Opening {name} replaces the project",
                                            lambda: self._open(data, name)):
            self._open(data, name)

    def _open(self, data: bytes, name: str) -> None:
        try:
            self.session.open_json(data, name=name)
        except ProjectFileError as exc:            # pragma: no cover - checked above
            _notify(f"Load failed: {exc}", color="negative")
            return
        _notify(f"Loaded {name}")

    # ----- Save ---------------------------------------------------------
    async def save(self) -> None:
        session = self.session
        if session.project_path is not None:
            try:
                session.save()
            except _SAVE_ERRORS as exc:
                _notify(f"Save failed: {exc}", color="negative")
                return
            _notify(f"Saved {session.project_path.name}")
        else:
            # Browser: the dialog opens pre-filled, never a silent second
            # download (the browser would save it as "name (1).json").
            await self.save_as()

    async def save_as(self) -> None:
        # async: NiceGUI awaits the handler inside its slot, so the UI calls
        # after the await (notify, open) still know their page.
        if _native.native_window() is not None:
            await self._native_save_as()
            return
        self.name_input.value = self.session.suggested_file_name()
        self.save_as_dialog.open()

    async def _native_save_as(self) -> None:
        from nicegui import run

        path = await run.io_bound(_native.ask_save_path, self.session.suggested_file_name())
        if path is None:
            return                                  # the user cancelled
        try:
            self.session.save_as(path)
        except _SAVE_ERRORS as exc:
            _notify(f"Save failed: {exc}", color="negative")
            return
        _notify(f"Saved {path.name}")

    def _do_save(self) -> None:
        from nicegui import ui

        try:
            data = self.session.save_as_download(self.name_input.value)
        except _SAVE_ERRORS as exc:
            self.save_as_dialog.close()
            _notify(f"Save failed: {exc}", color="negative")
            return
        # Bytes, and looked up on ``ui`` at call time (the T1 harness
        # replaces ui.download).
        ui.download(data, self.session.file_name, "application/json")
        _notify(f"Saved {self.session.file_name}")
        self.save_as_dialog.close()


def render(session: Session, *, dialogs: Any, goto: Optional[Goto] = None,
           actions: Optional[FileActions] = None) -> None:
    """Render the Project step into the current NiceGUI container.

    ``actions`` are the page's file operations (the shell builds them once
    and shares them with the header); without them the step builds its own.
    ``goto`` is the shell's navigation, which WP-G6's deck-import notice
    uses to link to the Meteorology step.
    """
    from nicegui import ui

    if actions is None:
        actions = FileActions(session, dialogs=dialogs)

    with step_page("Project", "Name the run, choose the pollutant and how AERMOD models it. "
                   "The steps can be done in any order."):
        with section("Project file"), ui.row().classes("items-center gap-2 flex-wrap"):
            ui.button("New", icon="note_add", on_click=actions.new).props("outline").mark(
                "project-new")
            ui.button("Open...", icon="folder_open", on_click=actions.open).props(
                "outline").mark("project-open")
            ui.button("Save", icon="save", on_click=actions.save).props("outline").mark(
                "project-save")
            ui.button("Save as...", on_click=actions.save_as).props("outline").mark(
                "project-save-as")
        # WP-G6's deck import, below the file buttons and outside any live
        # section: its uploader and subscription live as long as the page.
        files.import_controls(session, dialogs=dialogs, goto=goto)

        @live(session)
        def _settings() -> None:
            # One section, so the pollutant choice can update the
            # averaging-period hint directly.
            pollutant_chosen = _titles_and_pollutant(session)
            pollutant_chosen.append(_averaging_periods(session))
            _model_options(session)


def _titles_and_pollutant(session: Session) -> List[Any]:
    """Build the titles and the pollutant; return the list of pollutant-change callbacks."""
    from nicegui import ui

    control = session.project.control
    listeners: List[Any] = []

    def pollutant_changed(e) -> None:
        session.set_control(pollutant_id=_pollutant_value(e.value))
        for listener in listeners:
            listener()

    with section("Titles and pollutant"):
        with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2 w-full"):
            ui.input(
                "Title (line 1)", value=control.title_one,
                on_change=lambda e: session.set_control(title_one=e.value),
            ).classes("w-full").props('hint="TITLEONE: printed at the top of every table"')
            ui.input(
                "Title (line 2)", value=control.title_two or "",
                on_change=lambda e: session.set_control(title_two=e.value or None),
            ).classes("w-full").props('hint="TITLETWO: optional"')
        current = _pollutant_name(control.pollutant_id)
        options = [p.value for p in PollutantType]
        if current not in options:
            # A pollutant AERMOD accepts but the enum does not list (TSP,
            # PB, NOX ... from an imported deck or a saved file) stays a
            # choice, so the select can show it.
            options.append(current)
        ui.select(options=options, label="Pollutant", value=current,
                  on_change=pollutant_changed).classes("w-full sm:w-64").props('hint="POLLUTID"')
    return listeners


#: The periods AERMOD averages over whole years of met data, by pollutant:
#: ANNUAL for every pollutant, and the NAAQS design values AERMOD computes
#: itself (``coset.f``: SO2AVE and NO2AVE for the 1-hour period, PM25AVE for
#: the 24-hour one). On less than a year of met data each ends the run (E480).
_WHOLE_YEAR_PERIODS = {
    "SO2": "The 1-hour period and ANNUAL need",
    "NO2": "The 1-hour period and ANNUAL need",
    "PM25": "The 24-hour period and ANNUAL need",
}


def _naaqs_hint(pollutant: Any) -> str:
    name = _pollutant_name(pollutant)
    periods = naaqs_averaging_periods(name)
    whole_years = _WHOLE_YEAR_PERIODS.get(name.upper().replace(".", "").replace("-", ""),
                                          "ANNUAL needs")
    rule = f"{whole_years} complete years of met data; PERIOD averages the whole met file."
    if not periods:
        return f"{name} has no NAAQS in pyaermod's table; choose the periods you need. {rule}"
    return f"NAAQS periods for {name}: {', '.join(periods)}. {rule}"


def _averaging_periods(session: Session) -> Any:
    """Build the averaging-period select; return what to call when the pollutant changes."""
    from nicegui import ui

    control = session.project.control
    current = [str(p) for p in control.averaging_periods]
    options = AVERAGING_PERIODS + [p for p in current if p not in AVERAGING_PERIODS]

    def changed(e) -> None:
        periods = sort_periods([str(p) for p in (e.value or [])])
        session.set_control(averaging_periods=periods)
        if list(e.value or []) != periods:
            select.value = periods             # show them in AVERTIME's order

    def naaqs_periods() -> List[str]:
        return naaqs_averaging_periods(_pollutant_name(session.project.control.pollutant_id))

    def use_naaqs() -> None:
        if naaqs_periods():
            select.value = naaqs_periods()

    with section("Averaging periods", "AVERTIME: the periods AERMOD averages over. "
                 "Hours are 1 to 24; MONTH, PERIOD (the whole met file) and ANNUAL."):
        with ui.row().classes("items-start gap-4 w-full flex-wrap"):
            select = ui.select(options=options, value=sort_periods(current), multiple=True,
                               label="Averaging periods", on_change=changed,
                               ).classes("w-full sm:w-80")
            button = ui.button("Use the NAAQS periods", on_click=use_naaqs).props("flat")
        hint = ui.label().classes("text-body2 text-grey-8")

    def pollutant_changed() -> None:
        hint.set_text(_naaqs_hint(session.project.control.pollutant_id))
        button.set_enabled(bool(naaqs_periods()))

    pollutant_changed()
    return pollutant_changed


def _model_options(session: Session) -> None:
    from nicegui import ui

    control = session.project.control
    with section("Model options", "MODELOPT: what AERMOD computes and how it treats terrain."):
        with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 w-full"):
            with ui.column().classes("gap-0"):
                ui.label("Output").classes("text-caption text-grey-8")
                for attr, label in OUTPUT_OPTIONS:
                    ui.checkbox(label, value=bool(getattr(control, attr)),
                                on_change=lambda e, a=attr: session.set_control(**{a: e.value}))
                # No step edits a source's deposition parameters yet; the
                # validator reports a source without them (AERMOD E242).
                ui.label(DEPOSITION_NOTE).classes("text-caption text-grey-8")
            with ui.column().classes("gap-2 w-full"):
                terrain = _terrain_name(control.terrain_type)
                choices = dict(TERRAIN_CHOICES)
                if terrain not in choices:
                    choices[terrain] = terrain
                ui.select(choices, label="Terrain", value=terrain,
                          on_change=lambda e: session.set_control(
                              terrain_type=_terrain_value(e.value)),
                          ).classes("w-full sm:w-80")
                ui.checkbox("Regulatory default options (DFAULT)",
                            value=bool(control.regulatory_default),
                            on_change=lambda e: session.set_control(regulatory_default=e.value))
        with ui.expansion("Urban dispersion (URBANOPT)", icon="location_city").classes("w-full"):
            ui.label("Set the urban population to model the sources marked urban on the "
                     "Sources step with urban dispersion.").classes("text-body2 text-grey-8")
            with ui.element("div").classes(
                    "grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-2 w-full"):
                ui.number("Urban population", value=control.urban_population, min=0,
                          on_change=lambda e: session.set_control(urban_population=e.value),
                          ).props("clearable").classes("w-full")
                def roughness_allowed() -> None:
                    # URBANOPT's third field needs the name before it; a
                    # roughness already set stays editable, so it can be cleared.
                    c = session.project.control
                    roughness.set_enabled(bool(c.urban_option) or c.urban_roughness is not None)

                def name_changed(e) -> None:
                    session.set_control(urban_option=e.value or None)
                    roughness_allowed()

                def roughness_changed(e) -> None:
                    session.set_control(urban_roughness=e.value)
                    roughness_allowed()

                ui.input("Urban area name", value=control.urban_option or "",
                         on_change=name_changed).classes("w-full")
                roughness = ui.number(
                    "Urban roughness (m)", value=control.urban_roughness, min=0,
                    on_change=roughness_changed,
                ).props('clearable hint="Needs the urban area name"').classes("w-full")
                roughness_allowed()


def _pollutant_name(pollutant: Any) -> str:
    """What the Pollutant select shows for ``control.pollutant_id``."""
    return pollutant.value if isinstance(pollutant, PollutantType) else str(pollutant)


def _pollutant_value(name: str) -> Any:
    """The ``pollutant_id`` for a choice: the enum member, or the text itself."""
    try:
        return PollutantType(name)
    except ValueError:
        return name


def _terrain_name(terrain: Any) -> str:
    return terrain.value if isinstance(terrain, TerrainType) else str(terrain)


def _terrain_value(name: str) -> Any:
    try:
        return TerrainType(name)
    except ValueError:
        return name


def _notify(msg: str, *, color: str = "positive") -> None:
    """Wrapper around ``ui.notify`` so unit tests can monkeypatch it."""
    from nicegui import ui
    ui.notify(msg, color=color)


__all__ = ["AVERAGING_PERIODS", "FileActions", "render", "sort_periods"]
