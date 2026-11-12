"""
Review & Run step.

Before a run the step reviews the project: a readiness checklist of the
problems that block a run (one item per step that needs attention, each
linking to that step), the warnings that do not, and a read-only preview
of the deck with Copy and Download. The Run button stays disabled while
the checklist has items.

The run itself happens in the background
(:meth:`Session.start_run(background=True) <pyaermod.gui_v2.session.Session.start_run>`):
a progress bar follows AERMOD's "Now Processing Data For Day No." lines,
the elapsed time ticks, and Cancel stops AERMOD. Every other step, and
every other browser tab, stays usable meanwhile. When the run ends the
step shows AERMOD's verdict (read from the ``.out`` file by
:class:`~pyaermod.runner.AERMODRunner`), the counts of AERMOD's messages
and a table of them, each linking to ``docs/common-errors.md`` where
that page has an entry.

Everything the checklist knows comes from the library:
:class:`~pyaermod.validator.Validator`,
:func:`~pyaermod.validator_advanced.check_annual_met_coverage` (ANNUAL
with less than a year of met data, which AERMOD aborts with E480) and
:meth:`Session.deck_text`, whose output files must be in folders that
exist where AERMOD runs (it does not create them, and stops with E500).

Runs, New and Open: replacing the project stops its run (see
:meth:`Session.new`); a second Run while one is in progress is ignored.

Pages owned by other packages decide where a checklist link goes: the
shell passes ``goto(step_id)`` (step ids in :data:`STEP_IDS`).
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from typing import Any, Callable, List, Optional

from .._live import live
from ..readiness import (  # noqa: F401 - re-exported: this step's checklist
    COMMON_ERRORS,
    COMMON_ERRORS_URL,
    HOME_MET,
    MISSING_OUTPUT_FOLDER,
    NO_BINARY,
    OUTPUT_KEYWORDS,
    RELATIVE_MET,
    RELATIVE_OUTPUT,
    STEP_IDS,
    STEP_TITLES,
    ChecklistItem,
    Review,
    _add,
    _home_met_files,
    _met_files,
    _missing_output_folders,
    _ordered,
    _problem_text,
    _relative_met_files,
    _step_for_deck_error,
    _step_for_pathway,
    output_folders,
    review,
)
from ..session import (
    DECK_NAME,
    Change,
    DeckError,
    RunInProgressError,
    RunRecord,
    Session,
    SessionEvent,
)

Goto = Callable[[str], None]


def _aermod_available() -> bool:
    return shutil.which("aermod") is not None


# ----------------------------------------------------------------------
# A run as the step shows it
# ----------------------------------------------------------------------

def _seconds(record: RunRecord) -> float:
    r = record.result
    if r is not None and r.runtime_seconds is not None:
        return float(r.runtime_seconds)
    end = record.finished_at
    return (end - record.started_at).total_seconds() if end is not None else 0.0


def run_status_text(record: Optional[RunRecord]) -> str:
    """The one-line status of ``record`` (a placeholder when there is no run).

    The first word is the status: "Running", "Succeeded", "Failed" or
    "Cancelled".
    """
    if record is None:
        return "AERMOD has not been run for this project yet."
    status = record.status
    if status == "Running":
        return f"Running AERMOD in {record.work_dir} ..."
    if status == "Succeeded":
        return f"Succeeded in {_seconds(record):.1f} s. See the Results step."
    if status == "Cancelled":
        return f"Cancelled after {_seconds(record):.1f} s."
    reason = record.error
    if reason is None and record.result is not None:
        reason = record.result.error_message or f"exit code {record.result.return_code}"
    return f"Failed: {reason}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def message_counts_text(record: Optional[RunRecord]) -> str:
    """"0 fatal errors, 6 warnings, 1 informational message" ("" before a result)."""
    if record is None or record.result is None or record.cancelled:
        return ""
    r = record.result
    if not (r.finished_successfully or r.messages or r.message_counts):
        return ""
    return (f"AERMOD reported {_plural(r.fatal_count, 'fatal error')}, "
            f"{_plural(r.warning_count, 'warning')} and "
            f"{_plural(r.informational_count, 'informational message')}.")


def progress_text(record: Optional[RunRecord]) -> str:
    """What AERMOD last said it is doing: "Day 62 of 1988 (2 of 4 days)"."""
    if record is None:
        return ""
    p = record.progress
    if p is None:
        return "Starting AERMOD ..." if record.in_progress else ""
    if p.stage == "setup":
        return "Reading the deck (setup) ..." if record.in_progress else "Stopped during setup"
    if not p.days_processed:
        return "Writing the results ..." if p.stage == "output" else ""
    text = f"Day {p.day} of {p.year}"
    if record.expected_days:
        text += f" ({p.days_processed} of {_plural(record.expected_days, 'day')})"
    else:
        text += f" ({_plural(p.days_processed, 'day')} processed)"
    if p.stage == "output":
        text += ", writing the results"
    return text


#: Seconds after which Cancel is offered even if AERMOD has printed nothing.
CANCEL_WITHOUT_OUTPUT_S = 10.0


def can_cancel(record: Optional[RunRecord], now: Optional[datetime] = None) -> bool:
    """Whether Cancel is offered for ``record``.

    Once AERMOD has printed its first line (it does so as it starts), or
    :data:`CANCEL_WITHOUT_OUTPUT_S` after the start for a build that
    prints nothing: before that there is no AERMOD to stop yet.
    """
    if record is None or not record.in_progress:
        return False
    if record.progress is not None:
        return True
    return ((now or datetime.now()) - record.started_at).total_seconds() >= CANCEL_WITHOUT_OUTPUT_S


def elapsed_text(seconds: float) -> str:
    whole = max(0, int(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def run_log_text(record: Optional[RunRecord]) -> str:
    """The tail of AERMOD's stdout and stderr for the Run log."""
    if record is None or record.result is None:
        return "" if record is None or record.error is None else f"{record.error}\n"
    res = record.result
    tail = (res.stdout or "")[-4000:]
    return (
        f"return_code={res.return_code}, "
        f"runtime={res.runtime_seconds or 0:.1f} s\n"
        f"--- stdout tail ---\n{tail}\n"
        f"--- stderr tail ---\n{(res.stderr or '')[-2000:]}\n"
    )


def help_url(code: str) -> Optional[str]:
    """The common-errors entry for an AERMOD message code, if the page has one."""
    anchor = COMMON_ERRORS.get(code.upper())
    return f"{COMMON_ERRORS_URL}#{anchor}" if anchor else None


_SEVERITY = {"E": "Fatal error", "W": "Warning", "I": "Informational"}


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------

def _stay_here(step: str) -> None:
    """The default ``goto``: say where to go (the shell passes real navigation)."""
    from nicegui import ui

    ui.notify(f"Open the {STEP_TITLES.get(step, step)} step to fix this.")


def _loop_dispatcher() -> Optional[Callable[[Callable[[], object]], Any]]:
    """``call_soon_threadsafe`` of the loop this page is built on, if any."""
    try:
        return asyncio.get_running_loop().call_soon_threadsafe
    except RuntimeError:
        return None


def render(session: Session, *, dialogs: Any = None, goto: Optional[Goto] = None) -> None:
    """Build the Review & Run step.

    ``goto(step_id)`` shows another step; checklist items call it with one
    of :data:`STEP_IDS`. Without it a link only says which step to open.
    """
    from nicegui import ui

    go = goto or _stay_here
    # Background runs report from their own threads; their events must be
    # handled on the loop that serves the page.
    dispatcher = _loop_dispatcher()
    if dispatcher is not None:
        session.dispatch = dispatcher

    ui.label("Review & Run").classes("text-h6")

    def _start() -> None:
        if session.run_in_progress is not None:
            return                          # a second click of one double-click
        if not _aermod_available():
            ui.notify("No AERMOD binary; cannot run.", color="negative")
            return
        opts = session.run_options
        try:
            record = session.start_run(working_dir=opts.working_dir,
                                       timeout=int(opts.timeout_s or 600), background=True)
        except RunInProgressError:
            return
        except DeckError as exc:
            ui.notify(f"Could not generate deck: {exc}", color="negative")
            return
        except OSError as exc:
            ui.notify(f"Could not write the deck: {exc}", color="negative")
            return
        if record.in_progress:
            ui.notify("AERMOD started", color="info")

    def _cancel() -> None:
        if session.cancel_run():
            ui.notify("Stopping AERMOD ...", color="warning")

    # The Run button lives outside the review section, which only enables
    # or disables it: a button rebuilt under the pointer would lose a click.
    readiness = {"ready": False}
    run_button: List[Any] = []

    def _sync_run_button() -> None:
        if run_button:
            run_button[0].set_enabled(readiness["ready"] and session.run_in_progress is None)

    # ---- review: checklist, warnings and deck preview -----------------
    @live(session, SessionEvent.PROJECT_CHANGED, SessionEvent.RUN_STARTED,
          SessionEvent.RUN_FINISHED)
    def _review() -> None:
        found = review(session, have_binary=_aermod_available())
        readiness["ready"] = found.ready
        _sync_run_button()

        ui.label("Readiness checklist").classes("text-subtitle1 q-mt-md")
        with ui.element("ul").props('aria-label="Readiness checklist"').classes(
                "q-pl-none q-my-sm").style("list-style: none"):
            for item in found.blocking:
                _checklist_item(ui, item, go, color="text-negative", icon="error")
        if found.ready:
            ui.label("Nothing blocks the run.").classes("text-positive")

        if found.warnings:
            ui.label("Before you run").classes("text-subtitle1 q-mt-md")
            with ui.element("ul").props('aria-label="Warnings before the run"').classes(
                    "q-pl-none q-my-sm").style("list-style: none"):
                for item in found.warnings:
                    _checklist_item(ui, item, go, color="text-warning", icon="warning")
        if found.met_summary:
            ui.label(found.met_summary).classes("text-caption text-grey-8")

        ui.label("Deck preview").classes("text-subtitle1 q-mt-md")
        if found.deck is None:
            ui.label("The deck cannot be written until the checklist item above is fixed."
                     ).classes("text-grey-8")
        else:
            deck = found.deck
            ui.textarea(label="Deck preview", value=deck).props(
                "readonly outlined rows=14 input-style=\"font-family: monospace\"",
            ).classes("w-full")
            with ui.row().classes("q-gutter-sm"):
                ui.button("Copy deck", icon="content_copy",
                          on_click=lambda: _copy(ui, deck)).props("outline")
                ui.button("Download deck", icon="download",
                          on_click=lambda: ui.download(deck.encode("utf-8"), DECK_NAME,
                                                       "text/plain")).props("outline")

    run_button.append(ui.button("Run AERMOD", on_click=_start).props("color=primary").classes(
        "q-mt-md"))
    _sync_run_button()

    # ---- run options (not part of the project) ------------------------
    with ui.row().classes("items-center q-gutter-md q-mt-md w-full"):
        workdir = ui.input(
            "Working directory (blank = temp)",
        ).classes("w-96").bind_value(session.run_options, "working_dir")
        ui.number("Timeout (s)", format="%d").bind_value(session.run_options, "timeout_s")
    # A relative met file is read from the working directory, and needs
    # one: the review follows the directory when the field loses focus,
    # and the Run button at once when the field becomes blank or not.
    workdir.on("blur", lambda: _review.refresh())
    was_blank = [not str(session.run_options.working_dir or "").strip()]

    def _workdir_changed(_event: Any) -> None:
        blank = not str(session.run_options.working_dir or "").strip()
        if blank == was_blank[0]:
            return
        was_blank[0] = blank
        # The rebuild runs in a task of its own; a click that follows the
        # typing at once must meet a button that already agrees.
        readiness["ready"] = review(session, have_binary=_aermod_available()).ready
        _sync_run_button()
        _review.refresh()

    workdir.on_value_change(_workdir_changed)

    # ---- progress: updated in place as AERMOD reports each day --------
    with ui.column().classes("w-full q-mt-sm") as progress_box:
        bar = ui.linear_progress(value=0, show_value=False).props(
            'aria-label="Run progress"').classes("w-full")
        with ui.row().classes("items-center q-gutter-md"):
            day = ui.label()
            elapsed = ui.label()
            cancel = ui.button("Cancel", on_click=_cancel).props("color=negative outline")

    def _show_progress() -> None:
        record = session.run_in_progress or session.last_run
        shown = record is not None and (record.in_progress or record.progress is not None)
        progress_box.set_visibility(shown)
        if record is None or not shown:
            cancel.set_visibility(False)
            return
        fraction = record.fraction_done
        if fraction is None and record.in_progress:
            bar.props("indeterminate")      # the met period is unknown
        else:
            bar.props(remove="indeterminate")
            bar.value = fraction if fraction is not None else 1.0
        day.text = progress_text(record)
        seconds = ((_now() - record.started_at).total_seconds() if record.in_progress
                   else _seconds(record))
        elapsed.text = f"Elapsed {elapsed_text(seconds)}"
        cancel.set_visibility(record.in_progress)
        cancel.set_enabled(can_cancel(record))

    _show_progress()
    ui.timer(0.5, lambda: _show_progress() if session.run_in_progress is not None else None)

    def _on_run_event(change: Change) -> None:
        _show_progress()
        _sync_run_button()
        if change.event is SessionEvent.RUN_FINISHED and change.run is not None:
            with progress_box:
                _notify_finished(ui, change.run)

    # PROJECT_REPLACED too: New or Open stops the run without a
    # RUN_FINISHED, and its progress must not stay on the page.
    ui.context.client.on_delete(session.subscribe(
        (SessionEvent.RUN_STARTED, SessionEvent.RUN_PROGRESS, SessionEvent.RUN_FINISHED,
         SessionEvent.PROJECT_REPLACED),
        _on_run_event))

    # ---- outcome: status, messages, log --------------------------------
    @live(session, SessionEvent.RUN_STARTED, SessionEvent.RUN_FINISHED)
    def _outcome() -> None:
        record = session.run_in_progress or session.last_run
        # Exactly one status element: the journeys find the status by its
        # wording.
        ui.label(run_status_text(record)).props('role=status aria-live=polite').classes(
            "text-body1 q-mt-sm")
        counts = message_counts_text(record)
        if counts:
            ui.label(counts).classes("text-body2")
        if record is not None and record.result is not None and record.result.messages:
            _message_table(ui, record)
        ui.textarea(
            label="Run log", value=run_log_text(record),
        ).classes("w-full").props("readonly rows=12")


def _now() -> datetime:
    return datetime.now()


def _checklist_item(ui: Any, item: ChecklistItem, go: Goto, *, color: str, icon: str) -> None:
    with ui.element("li").classes("q-mb-sm"), ui.row().classes("items-start no-wrap q-gutter-sm"):
        ui.icon(icon).classes(color)
        with ui.column().classes("q-gutter-none"):
            ui.label(item.title).classes("text-weight-medium")
            for problem in item.problems:
                ui.label(problem[:1].upper() + problem[1:]).classes("text-body2")
        with ui.column().classes("q-gutter-none"):
            for step in item.links:
                ui.link(f"Go to {STEP_TITLES.get(step, step)}", f"#{step}").on(
                    "click", lambda step=step: go(step))


def _copy(ui: Any, text: str) -> None:
    ui.clipboard.write(text)
    ui.notify("Deck copied")


def _notify_finished(ui: Any, record: RunRecord) -> None:
    color = {"Succeeded": "positive", "Cancelled": "warning"}.get(record.status, "negative")
    words = {"Succeeded": "AERMOD finished", "Cancelled": "AERMOD run stopped"}
    ui.notify(words.get(record.status, "Run failed; see log"), color=color)


def _message_table(ui: Any, record: RunRecord) -> None:
    """AERMOD's messages: severity, pathway, code, line, text, and help where there is some."""
    assert record.result is not None
    ui.label("AERMOD messages").classes("text-subtitle1 q-mt-md")
    # Its own scroll container: on a phone a wide table must not widen the
    # whole step. Focusable, so the keyboard can scroll it too.
    scroller = ui.element("div").props("tabindex=0").style("overflow-x: auto; max-width: 100%")
    with scroller, ui.element("table").props('aria-label="AERMOD messages"').classes(
            "q-table q-table--dense q-table--horizontal-separator"):
        with ui.element("thead"), ui.element("tr"):
            for heading in ("Severity", "Pathway", "Code", "Line", "Message", "Help"):
                with ui.element("th").classes("text-left"):
                    ui.label(heading)
        with ui.element("tbody"):
            for m in record.result.messages:
                with ui.element("tr"):
                    for value in (_SEVERITY.get(m.severity, m.severity), m.pathway, m.code,
                                  m.line, f"{m.text} {m.detail}".strip()):
                        with ui.element("td"):
                            ui.label(value)
                    with ui.element("td"):
                        url = help_url(m.code)
                        if url:
                            ui.link(f"About {m.code}", url, new_tab=True)


__all__ = [
    "CANCEL_WITHOUT_OUTPUT_S",
    "COMMON_ERRORS",
    "OUTPUT_KEYWORDS",
    "STEP_IDS",
    "STEP_TITLES",
    "ChecklistItem",
    "Review",
    "can_cancel",
    "elapsed_text",
    "help_url",
    "message_counts_text",
    "output_folders",
    "progress_text",
    "render",
    "review",
    "run_log_text",
    "run_status_text",
]
