"""
Run tab.

Renders the project to an AERMOD input deck, dispatches it through
:meth:`pyaermod.gui_v2.session.Session.start_run`, and shows the outcome
of the session's latest run: its status and the tail of AERMOD's output.
The status and log are a live section rebuilt when a run starts or
finishes, and on every page build, so a reload shows the last run again.

The run is synchronous (AERMOD runs typically take seconds to minutes;
users wait). WP-G4 moves it to the background with progress and Cancel.
"""

from __future__ import annotations

import shutil
from typing import Any, Optional

from .._live import live
from ..session import DeckError, RunRecord, Session, SessionEvent


def _aermod_available() -> bool:
    return shutil.which("aermod") is not None


def run_status_text(record: Optional[RunRecord]) -> str:
    """The one-line status of ``record`` (empty when there is no run)."""
    if record is None:
        return ""
    if record.in_progress:
        return f"Running AERMOD in {record.work_dir} ..."
    if record.error is not None:
        return f"Run failed: {record.error}"
    r = record.result
    assert r is not None
    if r.success:
        return f"Run succeeded ({r.runtime_seconds or 0:.1f} s). See Results tab."
    return f"Run reported FATAL or non-zero exit (rc={r.return_code})."


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


def render(session: Session, *, dialogs: Any = None) -> None:
    from nicegui import ui

    ui.label("Run AERMOD").classes("text-h6")

    # Checked when the page is built, as before; WP-G4 decides whether the
    # button checks again when it is clicked.
    have_binary = _aermod_available()
    if not have_binary:
        ui.label(
            "No 'aermod' binary on PATH. Install AERMOD and re-launch.",
        ).classes("text-negative q-mt-sm")

    with ui.row().classes("items-center q-gutter-md q-mt-md"):
        ui.input(
            "Working directory (blank = temp)",
        ).classes("w-96").bind_value(session.run_options, "working_dir")
        ui.number("Timeout (s)", format="%d").bind_value(session.run_options, "timeout_s")

    @live(session, SessionEvent.RUN_STARTED, SessionEvent.RUN_FINISHED)
    def _outcome() -> None:
        record = session.run_in_progress or session.last_run
        # Exactly one status element: the journeys find the status by its
        # wording.
        ui.label(run_status_text(record)).classes("text-body1 q-mt-sm")
        ui.textarea(
            label="Run log", value=run_log_text(record),
        ).classes("w-full").props("readonly rows=20")

    def _do_run() -> None:
        if not have_binary:
            ui.notify("No AERMOD binary; cannot run.", color="negative")
            return
        ui.notify("AERMOD started", color="info")
        opts = session.run_options
        try:
            record = session.start_run(
                working_dir=opts.working_dir, timeout=int(opts.timeout_s or 600),
            )
        except DeckError as exc:
            ui.notify(f"Could not generate deck: {exc}", color="negative")
            return
        except OSError as exc:
            ui.notify(f"Could not write the deck: {exc}", color="negative")
            return
        if record.success:
            ui.notify("Run succeeded", color="positive")
        else:
            ui.notify("Run failed; see log", color="negative")

    ui.button("Run AERMOD", on_click=_do_run).props("color=primary")


__all__ = ["render", "run_log_text", "run_status_text"]
