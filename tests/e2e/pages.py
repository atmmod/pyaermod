"""Page objects for the GUI journeys: one class per step, plus the App.

Journeys call methods that say what the user does or expects
(``gui.sources.add_point_source(...)``, ``gui.run.reports_failure()``), so
a layout change edits this file, not the journeys (PLAN-gui.md, WP-G3
owns it). Elements are located by role and accessible name. Where the
current GUI gives an element no accessible name, the fallback is marked
``# A11Y-GAP (WP-G3): ...`` (or the package that will fix it) so the
work that adds the name can re-point it.

Methods that look for controls the current GUI does not have yet (the
averaging-period editor, the readiness checklist, the progress bar) are
written against the planned design. Today they time out, which journeys
wrap in ``known_gap``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import Locator, Page, expect

from .harness import Journey

RUN_TIMEOUT_MS = 180_000

# How the run status reads today ("Run succeeded (0.1 s). See Results tab.",
# "Run reported FATAL or non-zero exit (rc=0).", "Run failed: ...") and in
# the planned design ("Succeeded", "Failed", "Cancelled").
_STATUS = re.compile(r"\b(succeeded|failed|reported FATAL|cancell?ed)\b", re.I)
_SUCCESS = re.compile(r"\bsucceeded\b", re.I)
_FAILURE = re.compile(r"\bfail(ed|ure)?\b|\bFATAL\b", re.I)
_CANCELLED = re.compile(r"\bcancell?ed\b", re.I)


def _text(value) -> str:
    return str(value)


def _fill(field: Locator, value) -> None:
    """Type a value and leave the field, which is when NiceGUI commits it."""
    field.fill(_text(value))
    field.press("Tab")


def _choose(page: Page, combobox: Locator, option: str) -> None:
    combobox.click()
    page.get_by_role("option", name=option, exact=True).click()
    # A Quasar select's combobox is a read-only input holding the choice.
    expect(combobox).to_have_value(option)


def _period_key(label: str) -> str:
    """"1-HR", "1HR", "1-hour" -> "1HR"; "Period" -> "PERIOD"."""
    m = re.match(r"^\s*(\d+)\s*-?\s*(HR|HOUR)", label, re.I)
    return f"{m.group(1)}HR" if m else label.strip().upper()


def _agrees(shown: str, expected: float) -> bool:
    """True if ``shown`` is ``expected`` rounded to the digits it displays."""
    s = shown.strip().replace(",", "")
    try:
        value = float(s)
    except ValueError:
        return False
    mantissa, _, exponent = s.lower().partition("e")
    decimals = len(mantissa.partition(".")[2])
    scale = 10 ** (int(exponent) if exponent else 0)
    return abs(value - expected) <= 0.5 * 10 ** -decimals * scale * (1 + 1e-9)


class App:
    """The whole application: navigation, header and notifications."""

    def __init__(self, page: Page, url: str, journey: Optional[Journey] = None):
        self.page = page
        self.url = url
        self.journey = journey
        self.project = ProjectPage(self)
        self.sources = SourcesPage(self)
        self.receptors = ReceptorsPage(self)
        self.meteorology = MeteorologyPage(self)
        self.output = OutputPage(self)
        self.run = RunPage(self)
        self.results = ResultsPage(self)

    # -- navigation -------------------------------------------------------
    def open(self) -> App:
        self.page.goto(self.url)
        self._wait_ready()
        return self

    def reload(self) -> None:
        self.page.reload()
        self._wait_ready()

    def _wait_ready(self) -> None:
        expect(self.page.get_by_role("tab", name="Project", exact=True)).to_be_visible()
        expect(self._panels()).to_have_count(1)
        # Events sent before NiceGUI's websocket handshake are not delivered.
        self.page.wait_for_function("() => window.did_handshake === true")

    def step_tab(self, name: str) -> Locator:
        return self.page.get_by_role("tab", name=name, exact=True)

    def open_step(self, name: str) -> Locator:
        """Show a step and return its panel."""
        tab = self.step_tab(name)
        if tab.get_attribute("aria-selected") != "true":
            tab.click()
            expect(tab).to_have_attribute("aria-selected", "true")
            # During the switch the old and new panels are both present.
            expect(self._panels()).to_have_count(1)
        return self._panels()

    def _panels(self) -> Locator:
        # A11Y-GAP (WP-G3): tab panels have no accessible name
        # (aria-labelledby); the shown step is the one nested tabpanel left.
        return self.page.get_by_role("tabpanel").get_by_role("tabpanel")

    def expect_current_step(self, name: str) -> None:
        expect(self.step_tab(name)).to_have_attribute("aria-selected", "true")

    def expect_step_status(self, step: str, status: str) -> None:
        """A step's badge, read from its accessible name (planned, WP-G3)."""
        expect(self.step_tab(step)).to_have_accessible_name(
            re.compile(rf"\b{re.escape(status)}\b", re.I))

    # -- header -----------------------------------------------------------
    @property
    def header(self) -> Locator:
        return self.page.get_by_role("banner")

    def expect_unsaved_changes(self, unsaved: bool = True) -> None:
        # The current header appends " (modified)" to the project name.
        if unsaved:
            expect(self.header).to_contain_text("(modified)")
        else:
            expect(self.header).not_to_contain_text("(modified)")

    def expect_header_names(self, file_name: str) -> None:
        expect(self.header).to_contain_text(file_name)

    # -- notifications and dialogs ---------------------------------------
    def expect_notification(self, text) -> None:
        expect(self.page.get_by_role("alert").filter(has_text=text).first).to_be_visible()

    def dialog(self) -> Locator:
        return self.page.get_by_role("dialog")

    # -- the server, for errors a user cannot see ------------------------
    def expect_server_log_clean(self) -> None:
        assert self.journey is not None
        tracebacks = self.journey.server.tracebacks()
        assert not tracebacks, f"server log has tracebacks: {tracebacks}"


class _Step:
    NAME = ""

    def __init__(self, app: App):
        self.app = app
        self.page = app.page

    def open(self):
        self.app.open_step(self.NAME)
        return self

    @property
    def panel(self) -> Locator:
        return self.app.open_step(self.NAME)

    def field(self, label: str) -> Locator:
        return self.panel.get_by_label(label, exact=True)

    def set_field(self, label: str, value) -> None:
        _fill(self.field(label), value)

    def expect_field(self, label: str, value) -> None:
        expect(self.field(label)).to_have_value(_text(value))


class ProjectPage(_Step):
    NAME = "Project"

    def set_titles(self, line_one: str, line_two: Optional[str] = None) -> None:
        self.set_field("Title (line 1)", line_one)
        if line_two is not None:
            self.set_field("Title (line 2)", line_two)

    def title(self) -> str:
        return self.field("Title (line 1)").input_value()

    def expect_title(self, text: str) -> None:
        self.expect_field("Title (line 1)", text)

    def set_pollutant(self, pollutant: str) -> None:
        _choose(self.page, self.panel.get_by_role("combobox", name="Pollutant"),
                pollutant)

    def expect_pollutant(self, pollutant: str) -> None:
        expect(self.panel.get_by_role("combobox", name="Pollutant")).to_have_value(
            pollutant)

    def averaging_periods_control(self) -> Locator:
        return self.panel.get_by_role("combobox", name="Averaging periods")

    def set_averaging_periods(self, *periods: str) -> None:
        """Choose the averaging periods (planned multi-select, WP-G3).

        The current GUI has no such control and always writes its default,
        ``1 ANNUAL``. Asking for exactly that default is therefore already
        satisfied (the fake AERMOD's deck check confirms it whenever the
        journey runs); asking for anything else waits for the control and
        times out, which journeys wrap in ``known_gap("WP-G3", ...)``.
        """
        control = self.averaging_periods_control()
        if control.count() == 0 and list(periods) == ["1", "ANNUAL"]:
            return
        expect(control).to_be_visible()
        control.click()
        for period in periods:
            self.page.get_by_role("option", name=period, exact=True).click()
        self.page.keyboard.press("Escape")
        for period in periods:
            expect(control).to_contain_text(period)

    def new(self) -> None:
        self.panel.get_by_role("button", name="New", exact=True).click()
        self.app.expect_notification("New project")

    def save(self) -> None:
        self.panel.get_by_role("button", name="Save", exact=True).click()

    def save_as(self, file_name: str) -> Path:
        """Save As under ``file_name``; return the file the browser received."""
        self.panel.get_by_role("button", name="Save as...").click()
        dialog = self.app.dialog()
        _fill(dialog.get_by_label("Filename", exact=True), file_name)
        with self.page.expect_download() as download:
            dialog.get_by_role("button", name="Save", exact=True).click()
        expect(dialog).to_be_hidden()
        assert self.app.journey is not None
        target = self.app.journey.downloads / download.value.suggested_filename
        download.value.save_as(target)
        # The current Save As also writes the file to a hard-coded /tmp on
        # the server (PLAN-gui.md, WP-G2); the fixture removes it afterwards.
        self.app.journey.server_side_files.append(Path("/tmp") / file_name)
        return target

    def open_file(self, path: Path) -> None:
        """Open a saved project through the upload control."""
        self.panel.get_by_role("button", name="Open...").click()
        dialog = self.app.dialog()
        with self.page.expect_file_chooser() as chooser:
            dialog.get_by_role("button", name="Choose File").first.click()
        chooser.value.set_files(str(path))
        # A11Y-GAP (WP-G2): without auto_upload the file is only sent by the
        # uploader's header button, which has no accessible name.
        send = dialog.get_by_role("button").filter(has_text="cloud_upload")
        if send.count():
            send.click()
        expect(dialog).to_be_hidden()
        self.app.expect_notification(path.name)

    def import_deck(self, path: Path) -> None:
        """Import an AERMOD .inp deck (planned, WP-G6)."""
        button = self.panel.get_by_role("button", name=re.compile(r"^Import", re.I))
        expect(button).to_be_visible()
        with self.page.expect_file_chooser() as chooser:
            button.click()
        chooser.value.set_files(str(path))
        self.app.expect_notification(path.name)


class _TableStep(_Step):
    """Shared behaviour of the Sources and Receptors steps."""

    ADD_DIALOG = "Edit {kind}"
    EMPTY = ""

    def _choose_type(self, kind: str) -> None:
        _choose(self.page, self.panel.get_by_role("combobox", name="Type"), kind)

    def _add(self, kind: str, fields: Dict[str, object]) -> None:
        self._choose_type(kind)
        self.panel.get_by_role("button", name="Add", exact=True).click()
        self._edit_dialog(kind, fields)

    def _edit_dialog(self, kind: str, fields: Dict[str, object]) -> None:
        dialog = self.app.dialog()
        expect(dialog).to_contain_text(self.ADD_DIALOG.format(kind=kind))
        for label, value in fields.items():
            if value is not None:
                _fill(dialog.get_by_label(label, exact=True), value)
        dialog.get_by_role("button", name="Save", exact=True).click()
        expect(dialog).to_be_hidden()

    def rows(self) -> Locator:
        # Data rows have cells; the header row has column headers.
        return self.panel.get_by_role("row").filter(has=self.page.get_by_role("cell"))

    def row(self, name: str) -> Locator:
        # A11Y-GAP (WP-G3): rows are found through the first cell, whose
        # accessible name is the item's name only because its buttons are
        # unnamed.
        return self.rows().filter(
            has=self.page.get_by_role("cell", name=name, exact=True))

    def table(self) -> List[List[str]]:
        # A11Y-GAP (WP-G3): the name cell also renders the "edit" and
        # "delete" icon ligatures as text; the item's name is its last line.
        return [[(c.strip().splitlines() or [""])[-1].strip()
                 for c in row.get_by_role("cell").all_inner_texts()]
                for row in self.rows().all()]

    def names(self) -> List[str]:
        return [cells[0] for cells in self.table()]

    def expect_names(self, names: List[str]) -> None:
        expect(self.rows()).to_have_count(len(names))
        assert self.names() == list(names), f"{self.NAME} table: {self.table()}"

    def _row_button(self, name: str, icon: str) -> Locator:
        # A11Y-GAP (WP-G3): the row's edit and delete buttons have no
        # accessible name; they are found by their Material icon ligature.
        return self.row(name).get_by_role("button").filter(
            has_text=re.compile(rf"^\s*{icon}\s*$"))

    def _open_editor(self, name: str) -> Locator:
        self._row_button(name, "edit").click()
        dialog = self.app.dialog()
        expect(dialog).to_be_visible()
        return dialog

    def _edit(self, name: str, kind: str, fields: Dict[str, object]) -> None:
        self._open_editor(name)
        self._edit_dialog(kind, fields)

    def editor_value(self, name: str, label: str) -> str:
        """Open the editor for ``name``, read one field and close it."""
        dialog = self._open_editor(name)
        value = dialog.get_by_label(label, exact=True).input_value()
        dialog.get_by_role("button", name="Close", exact=True).click()
        expect(dialog).to_be_hidden()
        return value

    def _delete(self, name: str) -> None:
        before = self.rows().count()
        self._row_button(name, "delete").click()
        expect(self.rows()).to_have_count(before - 1)

    def expect_empty_state(self, shown: bool) -> None:
        message = self.panel.get_by_text(self.EMPTY)
        if shown:
            expect(message).to_be_visible()
        else:
            expect(message).to_have_count(0)

    def expect_plan_view_shows(self, *names: str) -> None:
        """The plan-view plot names every item (planned, WP-G3)."""
        plot = self.panel.get_by_role("img", name=re.compile("plan view", re.I))
        expect(plot).to_be_visible()
        for name in names:
            expect(plot).to_contain_text(name)


class SourcesPage(_TableStep):
    NAME = "Sources"
    EMPTY = "No sources yet"

    def add_point_source(self, *, id: str, x=None, y=None, stack_height=None,
                         stack_temp=None, exit_velocity=None,
                         stack_diameter=None, emission_rate=None) -> None:
        self._add("PointSource", {
            "source id": id, "x coord": x, "y coord": y,
            "stack height": stack_height, "stack temp": stack_temp,
            "exit velocity": exit_velocity, "stack diameter": stack_diameter,
            "emission rate": emission_rate,
        })
        expect(self.row(id)).to_be_visible()

    def add_volume_source(self, *, id: str, x=None, y=None, release_height=None,
                          emission_rate=None, lateral_dimension=None,
                          vertical_dimension=None) -> None:
        self._add("VolumeSource", {
            "source id": id, "x coord": x, "y coord": y,
            "release height": release_height, "emission rate": emission_rate,
            "initial lateral dimension": lateral_dimension,
            "initial vertical dimension": vertical_dimension,
        })
        expect(self.row(id)).to_be_visible()

    def edit_source(self, id: str, kind: str = "PointSource", **fields) -> None:
        """Change fields of a source, named as the editor labels them."""
        self._edit(id, kind, {k.replace("_", " "): v for k, v in fields.items()})

    def delete_source(self, id: str) -> None:
        self._delete(id)

    def expect_ids(self, ids: List[str]) -> None:
        self.expect_names(ids)

    def expect_row(self, id: str, *, kind: Optional[str] = None,
                   x=None, y=None, emission_rate=None) -> None:
        cells = self.row(id).get_by_role("cell")
        for index, value in ((1, kind), (2, x), (3, y), (4, emission_rate)):
            if value is not None:
                expect(cells.nth(index)).to_have_text(_text(value))


class ReceptorsPage(_TableStep):
    NAME = "Receptors"
    EMPTY = "No receptors yet"

    _POLAR = ("grid name", "x origin", "y origin", "dist init", "dist num",
              "dist delta", "dir init", "dir num", "dir delta")
    _CARTESIAN = ("grid name", "x init", "x num", "x delta", "y init",
                  "y num", "y delta")

    def add_polar_grid(self, *, name: str, x=None, y=None, dist_init=None,
                       dist_num=None, dist_delta=None, dir_init=None,
                       dir_num=None, dir_delta=None) -> None:
        values = (name, x, y, dist_init, dist_num, dist_delta, dir_init,
                  dir_num, dir_delta)
        self._add("PolarGrid", dict(zip(self._POLAR, values)))

    def add_cartesian_grid(self, *, name: str, x_init=None, x_num=None,
                           x_delta=None, y_init=None, y_num=None,
                           y_delta=None) -> None:
        values = (name, x_init, x_num, x_delta, y_init, y_num, y_delta)
        self._add("CartesianGrid", dict(zip(self._CARTESIAN, values)))

    def add_discrete_receptor(self, *, x, y) -> None:
        self._add("DiscreteReceptor", {"x coord": x, "y coord": y})

    def edit_receptor(self, name: str, kind: str, **fields) -> None:
        self._edit(name, kind, {k.replace("_", " "): v for k, v in fields.items()})

    def delete_receptor(self, name: str) -> None:
        self._delete(name)

    def expect_count(self, count: int) -> None:
        expect(self.rows()).to_have_count(count)

    def _expect_row(self, name: str, kind: str, counts: Tuple[int, int]) -> None:
        # The current table summarises a grid as "10 dist x 36 dir" or
        # "11 x 11"; counts typed into it read "11.0" (the integer-field
        # gap, pinned by J7's own test), so they are compared as numbers.
        cells = self.row(name).get_by_role("cell")
        expect(cells.nth(-2)).to_have_text(kind)
        number = r"(\d+(?:\.0+)?)"
        pattern = rf"^\s*{number}\D+{number}\D*$"
        summary = cells.nth(-1)
        expect(summary).to_have_text(re.compile(pattern))
        shown = re.match(pattern, summary.inner_text())
        assert shown and tuple(float(g) for g in shown.groups()) == counts, (
            f"{name} summary reads {summary.inner_text()!r}, expected {counts}")

    def expect_polar_grid(self, name: str, *, rings: int, directions: int) -> None:
        self._expect_row(name, "PolarGrid", (rings, directions))

    def expect_cartesian_grid(self, name: str, *, nx: int, ny: int) -> None:
        self._expect_row(name, "CartesianGrid", (nx, ny))

    def expect_discrete_receptor(self, *, x: float, y: float) -> None:
        # Discrete receptors have no name of their own; the current table
        # labels them DISC<n> and summarises their coordinates.
        row = self.rows().filter(has_text=f"({x:.1f}, {y:.1f})")
        expect(row).to_have_count(1)
        expect(row.get_by_role("cell").nth(-2)).to_have_text("DiscreteReceptor")

    def table(self) -> List[List[str]]:
        # Drop the hidden key column the current table carries.
        return [cells[-3:] for cells in super().table()]


class MeteorologyPage(_Step):
    NAME = "Meteorology"

    def set_met_files(self, surface, profile) -> None:
        self.set_field("surface file", surface)
        self.set_field("profile file", profile)

    def expect_met_files(self, surface: str, profile: str) -> None:
        self.expect_field("surface file", surface)
        self.expect_field("profile file", profile)

    def show_advanced(self) -> Locator:
        panel = self.panel
        expand = panel.get_by_role("button", name='Expand "Advanced"')
        if expand.count():
            expand.click()
        expect(panel.get_by_role("button", name='Collapse "Advanced"')).to_be_visible()
        return panel

    def set_stations(self, *, surface_station_id, upper_air_station_id,
                     data_start_year) -> None:
        panel = self.show_advanced()
        _fill(panel.get_by_label("surface station id", exact=True), surface_station_id)
        _fill(panel.get_by_label("upper air station id", exact=True),
              upper_air_station_id)
        _fill(panel.get_by_label("data start year", exact=True), data_start_year)

    def expect_station_ids(self, surface: str, upper_air: str, year: str) -> None:
        panel = self.show_advanced()
        expect(panel.get_by_label("surface station id", exact=True)).to_have_value(surface)
        expect(panel.get_by_label("upper air station id", exact=True)).to_have_value(
            upper_air)
        expect(panel.get_by_label("data start year", exact=True)).to_have_value(year)


class OutputPage(_Step):
    NAME = "Output"

    def expect_output_type(self, output_type: str) -> None:
        self.expect_field("output type", output_type)


class RunPage(_Step):
    NAME = "Run"

    def set_working_directory(self, path) -> None:
        self.set_field("Working directory (blank = temp)", path)

    def set_timeout(self, seconds: int) -> None:
        self.set_field("Timeout (s)", seconds)

    def run_button(self) -> Locator:
        return self.panel.get_by_role("button", name="Run AERMOD")

    def start(self) -> None:
        self.run_button().click()

    def status(self) -> Locator:
        # A11Y-GAP (WP-G4): the run status is a plain label, not a
        # role="status" live region, so it is found by its wording.
        return self.panel.get_by_text(_STATUS)

    def wait_until_finished(self, timeout_ms: int = RUN_TIMEOUT_MS) -> None:
        expect(self.status()).to_be_visible(timeout=timeout_ms)

    def expect_last_run_shown(self) -> None:
        """The outcome of the last run is on the page (no waiting for a run)."""
        expect(self.status()).to_be_visible()

    def reports_success(self) -> None:
        expect(self.status()).to_have_text(_SUCCESS)
        expect(self.status()).not_to_have_text(_FAILURE)

    def reports_failure(self) -> None:
        expect(self.status()).to_have_text(_FAILURE)

    def reports_cancelled(self) -> None:
        expect(self.status()).to_have_text(_CANCELLED)

    def log(self) -> str:
        return self.panel.get_by_label("Run log", exact=True).input_value()

    # -- planned (WP-G4) --------------------------------------------------
    def messages(self) -> Locator:
        return self.panel.get_by_role("table", name=re.compile("messages", re.I))

    def expect_message(self, code: str, text: Optional[str] = None) -> None:
        """The message table lists AERMOD's message ``code`` (and its text)."""
        row = self.messages().get_by_role("row").filter(has_text=code)
        expect(row).to_be_visible()
        if text:
            expect(row).to_contain_text(text)

    def expect_message_counts(self, *, fatal: int, warnings: Optional[int] = None) -> None:
        expect(self.panel.get_by_text(
            re.compile(rf"\b{fatal} fatal", re.I))).to_be_visible()
        if warnings is not None:
            expect(self.panel.get_by_text(
                re.compile(rf"\b{warnings} warning", re.I))).to_be_visible()

    def expect_warning(self, pattern: re.Pattern[str]) -> None:
        expect(self.panel.get_by_text(pattern).first).to_be_visible()

    def expect_run_blocked(self) -> None:
        expect(self.run_button()).to_be_disabled()

    def expect_run_allowed(self) -> None:
        expect(self.run_button()).to_be_enabled()

    def checklist(self) -> Locator:
        return self.panel.get_by_role("list", name=re.compile("checklist|readiness", re.I))

    def expect_checklist_names(self, *problems: re.Pattern[str] | str) -> None:
        for problem in problems:
            expect(self.checklist().get_by_role("listitem").filter(
                has_text=problem)).to_be_visible()

    def expect_checklist_clear_of(self, problem) -> None:
        expect(self.checklist().get_by_role("listitem").filter(
            has_text=problem)).to_have_count(0)

    def follow_checklist_item(self, problem) -> None:
        self.checklist().get_by_role("listitem").filter(has_text=problem).get_by_role(
            "link").click()

    def expect_progress_day(self, day: int) -> None:
        bar = self.panel.get_by_role("progressbar")
        expect(bar).to_be_visible()
        expect(self.panel.get_by_text(re.compile(rf"\bday\b\D*\b{day}\b", re.I))
               ).to_be_visible()

    def cancel(self) -> None:
        self.panel.get_by_role("button", name="Cancel", exact=True).click()


class ResultsPage(_Step):
    NAME = "Results"

    _NO_RUN = re.compile(r"\bno run\b", re.I)

    def expect_no_run(self) -> None:
        expect(self.panel.get_by_text(self._NO_RUN)).to_be_visible()

    def expect_showing_run(self, run_dir: Path) -> None:
        """Results shows the latest run rather than the empty state."""
        panel = self.panel
        expect(panel.get_by_text(self._NO_RUN)).to_have_count(0)
        expect(panel).to_contain_text(re.compile(
            rf"{re.escape(str(run_dir))}|\.out\b", re.I))

    def maxima(self) -> Dict[str, Tuple[str, str, str]]:
        """{period: (value, x, y)} as displayed, keyed like "1HR"."""
        table = self.panel.get_by_role("table").filter(
            has=self.page.get_by_role("columnheader", name="Max", exact=True))
        expect(table).to_be_visible()
        shown = {}
        for row in table.get_by_role("row").filter(
                has=self.page.get_by_role("cell")).all():
            period, value, x, y = [c.strip() for c in
                                   row.get_by_role("cell").all_inner_texts()[:4]]
            shown[_period_key(period)] = (value, x, y)
        return shown

    def expect_maxima(self, expected: Dict[str, float],
                      location: Tuple[float, float]) -> None:
        """Each period's maximum and its location, to the digits shown."""
        shown = self.maxima()
        for period, value in expected.items():
            assert period in shown, f"no {period} maximum on Results: {shown}"
            v, x, y = shown[period]
            assert _agrees(v, value), f"{period} maximum shows {v}, expected {value}"
            assert _agrees(x, location[0]) and _agrees(y, location[1]), (
                f"{period} maximum located at ({x}, {y}), expected {location}")

    def expect_map(self) -> None:
        expect(self.panel.get_by_role(
            "img", name=re.compile("concentration map", re.I))).to_be_visible()

    def download_deck(self) -> Path:
        name = re.compile(r"\bdeck\b", re.I)
        control = self.panel.get_by_role("button", name=name).or_(
            self.panel.get_by_role("link", name=name))
        with self.page.expect_download() as download:
            control.first.click()
        assert self.app.journey is not None
        target = self.app.journey.downloads / download.value.suggested_filename
        download.value.save_as(target)
        return target

    def expect_failed_run_without_valid_results(self) -> None:
        """The run is labelled failed and no maxima are offered as valid."""
        panel = self.panel
        expect(panel.get_by_text(_FAILURE).first).to_be_visible()
        expect(panel.get_by_role("table").filter(
            has=self.page.get_by_role("columnheader", name="Max", exact=True))
        ).to_have_count(0)
