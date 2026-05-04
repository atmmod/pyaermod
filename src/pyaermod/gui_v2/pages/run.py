"""
Run tab.

Renders the project to an AERMOD input deck, dispatches to
:class:`pyaermod.runner.AERMODRunner`, and surfaces success / failure
+ stdout tail. Result is cached on :class:`AppState.last_run_dir` so
the Results tab can pick it up.

The actual subprocess call is synchronous (AERMOD runs typically
take seconds-to-minutes; users wait). Future work: hand off to a
background thread + stream progress through a NiceGUI ``ui.timer``
poll loop.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ..state import AppState


def _aermod_available() -> bool:
    return shutil.which("aermod") is not None


def render(state: AppState) -> None:
    from nicegui import ui

    ui.label("Run AERMOD").classes("text-h6")

    have_binary = _aermod_available()
    if not have_binary:
        ui.label(
            "No 'aermod' binary on PATH. Install AERMOD and re-launch.",
        ).classes("text-negative q-mt-sm")

    with ui.row().classes("items-center q-gutter-md q-mt-md"):
        workdir_input = ui.input(
            "Working directory (blank = temp)", value="",
        ).classes("w-96")
        timeout_input = ui.number("Timeout (s)", value=600, format="%d")

    status = ui.label("").classes("text-body1 q-mt-sm")
    log = ui.textarea(label="Run log").classes("w-full").props("readonly rows=20")

    def _do_run():
        from ..._optional import HAS_TERRAIN  # noqa: F401  (import-time checks)
        from ...runner import AERMODRunner

        if not have_binary:
            ui.notify("No AERMOD binary; cannot run.", color="negative")
            return

        # Resolve workdir + write the deck.
        wd = (
            Path(workdir_input.value).expanduser()
            if workdir_input.value.strip()
            else Path(tempfile.mkdtemp(prefix="pyaermod_"))
        )
        wd.mkdir(parents=True, exist_ok=True)
        deck_path = wd / "aermod.inp"
        try:
            deck_text = state.project.to_aermod_input(validate=False)
        except Exception as exc:
            ui.notify(f"Could not generate deck: {exc}", color="negative")
            return
        deck_path.write_text(deck_text, encoding="utf-8")

        status.text = f"Running AERMOD in {wd} ..."
        ui.notify("AERMOD started", color="info")
        try:
            runner = AERMODRunner(log_level="WARNING")
            res = runner.run(
                input_file=deck_path,
                working_dir=wd,
                timeout=int(timeout_input.value or 600),
            )
        except Exception as exc:
            status.text = f"Run failed: {exc}"
            ui.notify(f"Run failed: {exc}", color="negative")
            return

        state.last_run_dir = wd
        tail = (res.stdout or "")[-4000:]
        log.value = (
            f"return_code={res.return_code}, "
            f"runtime={res.runtime_seconds:.1f} s\n"
            f"--- stdout tail ---\n{tail}\n"
            f"--- stderr tail ---\n{(res.stderr or '')[-2000:]}\n"
        )
        if res.success:
            status.text = (
                f"Run succeeded ({res.runtime_seconds:.1f} s). "
                f"See Results tab."
            )
            ui.notify("Run succeeded", color="positive")
        else:
            status.text = (
                f"Run reported FATAL or non-zero exit "
                f"(rc={res.return_code})."
            )
            ui.notify("Run failed; see log", color="negative")

    ui.button("Run AERMOD", on_click=_do_run).props("color=primary")


__all__ = ["render"]
