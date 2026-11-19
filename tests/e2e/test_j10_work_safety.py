"""J10: the GUI never loses the user's work and never overstates its results.

From the 2026-11-18 review (gui-live live-G*, gui-code code-G*):

Lost work
- an imported deck asks before it replaces unsaved changes, as New and
  Open do (code-G1, live-G1);
- closing the tab asks while the project has unsaved changes (live-G2);
- the source editor is not closed by Esc or a click outside (code-G6);
- the vertex editor reads AERMOD's own ``x y`` pairs and names a line it
  cannot read (code-G5); an emptied number box says so and is not saved
  (live-G9); a source ID AERMOD cannot read is refused at the field
  (live-G4).

Misleading output
- Results says when the project has changed since the run it shows (live-G5);
- the NAAQS verdict for four days of data says it is no design value, and
  that no background was added, where it can be read at 1280 and 390 px
  (live-G6, code-G10);
- the header and Review & Run agree that a missing met file blocks the run
  (code-G3);
- Meteorology flags station IDs that differ from the surface file's header,
  and offers the file's values (live-G7).
"""

from __future__ import annotations

import re
import shutil

import pytest
from playwright.sync_api import expect

from .harness import EPA_FIXTURES
from .reference import (
    AVERAGING_PERIODS,
    PROFILE_FILE,
    STACK,
    SURFACE_FILE,
    enter_reference_scenario,
)

pytestmark = pytest.mark.e2e

_DISCARD = re.compile(r"Discard unsaved changes\?")


def _editor(gui):
    return gui.dialog().filter(has_text=re.compile(r"^Edit "))


# ----------------------------------------------------------------------
# Lost work
# ----------------------------------------------------------------------

def test_j10_importing_a_deck_asks_before_discarding_unsaved_changes(gui, step, tmp_path):
    deck = tmp_path / "aertest.inp"
    shutil.copy(EPA_FIXTURES / "aertest.inp", deck)
    gui.open()
    gui.project.set_titles("My unsaved work")
    gui.expect_unsaved_changes()

    gui.project.set_field("Deck file path", deck)
    gui.project.panel.get_by_role("button", name="Read deck").click()
    question = gui.dialog().filter(has_text=_DISCARD)
    expect(question).to_be_visible()
    expect(question).to_contain_text("Importing aertest.inp replaces the project")
    step("asked")
    question.get_by_role("button", name="Cancel").click()
    expect(question).to_be_hidden()
    gui.project.expect_title("My unsaved work")

    gui.project.panel.get_by_role("button", name="Read deck").click()
    gui.dialog().filter(has_text=_DISCARD).get_by_role("button", name="Discard changes").click()
    gui.expect_notification("Imported aertest.inp")
    gui.project.expect_title("A Simple Example Problem for the AERMOD Model with PRIME")


def test_j10_closing_the_tab_asks_while_changes_are_unsaved(gui, journey):
    page = journey.page
    gui.open()
    assert page.evaluate("window.__pyaermodUnsaved") is False
    gui.project.set_titles("Not saved yet")
    gui.expect_unsaved_changes()
    page.wait_for_function("() => window.__pyaermodUnsaved === true")
    asked = []

    def answer(dialog):
        asked.append(dialog.type)
        dialog.dismiss()                    # stay on the page

    page.on("dialog", answer)
    page.close(run_before_unload=True)
    page.wait_for_timeout(500)
    assert asked == ["beforeunload"]
    assert not page.is_closed()


def test_j10_the_source_editor_survives_esc_and_says_what_it_cannot_read(gui, step):
    gui.open()
    sources = gui.sources
    sources.open()
    sources._choose_type("AreaPolySource")
    sources.panel.get_by_role("button", name="Add", exact=True).click()
    editor = _editor(gui)
    expect(editor).to_be_visible()

    # Esc (or a click outside) used to close the editor and lose the draft.
    editor.get_by_label(re.compile(r"^Source ID", re.I)).fill("POLY1")
    gui.page.keyboard.press("Escape")
    expect(editor).to_be_visible()
    expect(editor.get_by_label(re.compile(r"^Source ID", re.I))).to_have_value("POLY1")

    # AERMOD's own "x y" pairs are read; a line that is not a pair is named.
    vertices = editor.get_by_label(re.compile(r"^Vertices", re.I))
    vertices.fill("0 0\n100 0\n100 100\nhalf a pair")
    vertices.press("Tab")
    expect(editor).to_contain_text("Line 4 could not be read")
    editor.get_by_role("button", name="Save", exact=True).click()
    expect(editor).to_contain_text("Not saved: correct these first.")
    expect(editor).to_contain_text("Line 4 could not be read")
    step("unread_line")
    vertices.fill("0 0\n100 0\n100 100\n0 100")
    vertices.press("Tab")
    expect(editor.get_by_text(re.compile(r"^Line 4 could not be read"))).to_have_count(0)

    # An emptied number is an error, not the old value kept in silence.
    rate = editor.get_by_label(re.compile(r"^Emission rate", re.I))
    rate.fill("")
    rate.press("Tab")
    expect(editor).to_contain_text("Enter a number")      # at the field, at once
    gui.page.wait_for_timeout(500)
    expect(rate).to_have_value("")          # and the old value does not come back
    editor.get_by_role("button", name="Save", exact=True).click()
    expect(editor).to_contain_text(re.compile(r"Emission rate.*: Enter a number"))
    rate.fill("0.5")
    rate.press("Tab")
    expect(editor.get_by_text("Enter a number", exact=True)).to_have_count(0)

    # An ID AERMOD would cut at its blank is refused at the field.
    sid = editor.get_by_label(re.compile(r"^Source ID", re.I))
    sid.fill("POLY 1")
    sid.press("Tab")
    expect(editor).to_contain_text("No blanks")
    editor.get_by_role("button", name="Save", exact=True).click()
    expect(editor).to_contain_text(re.compile(r"Source ID: No blanks"))
    sid.fill("POLY1")
    sid.press("Tab")
    expect(editor.get_by_text(re.compile(r"^No blanks"))).to_have_count(0)
    editor.get_by_role("button", name="Save", exact=True).click()
    expect(editor).to_be_hidden()
    sources.expect_ids(["POLY1"])

    # A second source of the same ID is refused, with the reason.
    sources._choose_type("PointSource")
    sources.panel.get_by_role("button", name="Add", exact=True).click()
    editor = _editor(gui)
    editor.get_by_label(re.compile(r"^Source ID", re.I)).fill("POLY1")
    editor.get_by_label(re.compile(r"^Source ID", re.I)).press("Tab")
    editor.get_by_label(re.compile(r"^Stack height", re.I)).fill("-5")
    editor.get_by_label(re.compile(r"^Stack height", re.I)).press("Tab")
    # The editor lists the checks' findings for the source as it is edited.
    expect(editor).to_contain_text("stack height must be >= 0")
    editor.get_by_role("button", name="Save", exact=True).click()
    expect(editor).to_contain_text("another source is called POLY1")
    step("duplicate_id")
    editor.get_by_role("button", name="Cancel", exact=True).click()
    expect(editor).to_be_hidden()
    sources.expect_ids(["POLY1"])


# ----------------------------------------------------------------------
# Misleading output
# ----------------------------------------------------------------------

@pytest.mark.aermod_recording("albany_success")
def test_j10_results_say_what_they_are_and_are_not(gui, step, run_dir):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    gui.run.reports_success()

    results = gui.results.panel
    verdict = results.get_by_text(re.compile(r"^SO2 1-hour .*: Not a design value: 4 days"))
    expect(verdict).to_be_visible()
    expect(verdict).to_contain_text("the NAAQS form needs 3 years")
    expect(verdict).to_contain_text("the run added no background concentration")
    for width, height in ((1280, 900), (390, 844)):
        gui.page.set_viewport_size({"width": width, "height": height})
        gui.results.open()          # the step again, through the drawer on a phone
        verdict.scroll_into_view_if_needed()
        box = verdict.bounding_box()
        assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= width, (
            f"the NAAQS verdict is outside a {width} px window: {box}")
        step(f"naaqs_{width}")
    gui.page.set_viewport_size({"width": 1280, "height": 900})
    expect(results.get_by_text("The project has changed since run 1")).to_have_count(0)

    # The project changes: Results says its numbers are for the project as it was.
    gui.sources.edit_source(STACK["id"], emission_rate=200)
    changed = gui.results.panel.get_by_text(re.compile(r"The project has changed since run 1"))
    expect(changed).to_be_visible()
    step("changed_since")
    gui.sources.edit_source(STACK["id"], emission_rate=STACK["emission_rate"])
    expect(gui.results.panel.get_by_text(
        re.compile(r"The project has changed since run 1"))).to_have_count(0)


def test_j10_a_missing_met_file_blocks_in_the_header_and_the_checklist(gui, tmp_path):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*AVERAGING_PERIODS)
    missing = tmp_path / "MISSING.PFL"
    gui.meteorology.set_met_files(SURFACE_FILE, missing)
    expect(gui.header).to_contain_text("Not ready to run: 1 problem in Meteorology")
    gui.expect_step_status("Meteorology", "error")
    gui.run.open()
    gui.run.expect_checklist_names(f"Profile file {missing} does not exist")
    gui.run.expect_run_blocked()
    gui.meteorology.set_met_files(SURFACE_FILE, PROFILE_FILE)
    expect(gui.header).to_contain_text(re.compile(r"Ready to run"))
    gui.run.open()
    gui.run.expect_run_allowed()


def test_j10_meteorology_offers_the_surface_files_stations(gui, step):
    gui.open()
    gui.project.set_averaging_periods(*AVERAGING_PERIODS)    # no ANNUAL warning
    gui.meteorology.set_met_files(SURFACE_FILE, PROFILE_FILE)
    panel = gui.meteorology.panel
    expect(panel).to_contain_text("differ from the file's header")
    gui.expect_step_status("Meteorology", "warning")
    step("stations_differ")
    panel.get_by_role("button", name="Use the file's values").click()
    gui.meteorology.expect_station_ids("14735", "14735", "1988")
    expect(panel.get_by_text("differ from the file's header")).to_have_count(0)
    gui.expect_step_status("Meteorology", "complete")
