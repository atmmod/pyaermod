"""The browser GUI (webapp/) keeps the user's work and says what its results are.

From the 2026-11-18 review (gui-live): a reload kept the project but forgot
that it had unsaved changes, so New, Open and Import then discarded them
without asking (live-G3); closing the tab never asked (live-G2); Results
did not say when the project had changed since the run it shows (live-G5);
the editor saved a duplicate or unreadable source ID and invalid values in
silence (live-G4, live-G8); the NAAQS verdict said "Below the NAAQS" for four
days of data (live-G6).
"""

from __future__ import annotations

import re

import pytest

from .test_b01_browser_app import MET, RECORDINGS, app, step

pytestmark = pytest.mark.e2e


def _type(page, label, value):
    field = page.get_by_label(label)
    field.fill(str(value))
    field.dispatch_event("change")


def _header(page) -> str:
    return page.locator("#project-title").inner_text()


def test_b03_a_reload_keeps_the_unsaved_flag_and_new_still_asks(app):  # noqa: F811
    step(app, "Project")
    _type(app, re.compile("^Title one"), "UNSAVED TITLE")
    app.wait_for_function("() => document.querySelector('#project-title')"
                          ".textContent.includes('(modified)')")
    app.wait_for_timeout(800)                   # the checked document is kept
    app.reload()
    app.wait_for_selector("#app:not([hidden])", timeout=20000)
    assert _header(app) == "UNSAVED TITLE (modified)"

    asked = []

    def answer(dialog):
        asked.append((dialog.type, dialog.message))
        dialog.dismiss()                         # keep the work

    app.on("dialog", answer)
    step(app, "Project")
    app.get_by_role("button", name="New", exact=True).click()
    app.wait_for_timeout(300)
    assert asked and asked[0][0] == "confirm" and "not saved" in asked[0][1]
    assert app.get_by_label(re.compile("^Title one")).input_value() == "UNSAVED TITLE"

    # Closing (or reloading) the tab asks too.
    asked.clear()
    app.close(run_before_unload=True)
    app.wait_for_timeout(500)
    assert [kind for kind, _ in asked] == ["beforeunload"]
    assert not app.is_closed()


def test_b03_the_editor_refuses_ids_aermod_cannot_read_and_shows_its_problems(app):  # noqa: F811
    step(app, "Sources")
    app.get_by_role("button", name="Add source").click()
    _type(app, "Source id", "STACK1")
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_selector("td:has-text('STACK1')")

    app.get_by_role("button", name="Add source").click()
    _type(app, "Source id", "A B")
    app.wait_for_selector("text=No blanks")
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_selector("#error:has-text('Not saved: correct Source id')")

    _type(app, "Source id", "STACK1")
    _type(app, re.compile("^Stack height"), "-5")
    # Shown in the editor as it is edited, not only on Review & Run.
    app.wait_for_selector("#editor-findings:has-text('stack height must be >= 0')")
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_selector("#error:has-text('another source is called STACK1')")
    assert app.locator("tbody td", has_text="STACK1").count() == 1


def test_b03_results_say_when_the_project_has_changed_since_the_run(app):  # noqa: F811
    with app.expect_file_chooser() as chooser:
        app.get_by_role("button", name="Import deck...").click()
    chooser.value.set_files([RECORDINGS / "albany_success" / "aermod.inp",
                             MET / "AERMET2.SFC", MET / "AERMET2.PFL"])
    app.wait_for_selector("text=Imported aermod.inp")
    step(app, "Review & Run")
    app.get_by_role("button", name="Run AERMOD").click()
    app.wait_for_selector("main h1:has-text('Results')", timeout=30000)
    changed = app.get_by_text(re.compile(r"The project has changed since run 1"))
    assert changed.count() == 0
    verdict = app.locator("table[aria-label='Comparison with the NAAQS'] tbody td").nth(1)
    assert verdict.inner_text().startswith("Not a design value")

    step(app, "Sources")
    app.get_by_role("button", name="Edit STACK1").click()
    _type(app, re.compile("^Emission rate"), "999")
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_timeout(800)                   # the checklist follows the edit
    step(app, "Results")
    app.wait_for_selector("text=The project has changed since run 1")
