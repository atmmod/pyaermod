"""
Per-session app state for the NiceGUI GUI.

A single :class:`AppState` instance is created per browser session by
:func:`pyaermod.gui_v2.app.build_and_run`. Each page receives the same
instance and mutates it directly — there is no analogue of Streamlit's
``st.session_state`` because NiceGUI elements bind to plain Python
attributes through ``ui.bind_*`` helpers.

The design intent is "fat state, dumb pages": the project tree lives
on the state object, and pages are pure functions of state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..input_generator import (
    AERMODProject,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)


def _empty_project() -> AERMODProject:
    """Return a blank AERMODProject suitable as a starting point."""
    return AERMODProject(
        control=ControlPathway(
            title_one="Untitled run",
            pollutant_id=PollutantType.SO2,
            averaging_periods=["1", "ANNUAL"],
        ),
        sources=SourcePathway(sources=[]),
        receptors=ReceptorPathway(),
        meteorology=MeteorologyPathway(
            surface_file="", profile_file="",
        ),
        output=OutputPathway(),
    )


@dataclass
class AppState:
    """Per-session state for the GUI.

    Attributes
    ----------
    project
        The full AERMODProject under edit.
    project_path
        Path to the on-disk JSON file backing this project, or None
        if the project has never been saved.
    dirty
        True if the in-memory project has unsaved changes.
    last_run_dir
        Working directory of the most recent AERMOD run (drives the
        Results page).
    """

    project: AERMODProject = field(default_factory=_empty_project)
    project_path: Optional[Path] = None
    dirty: bool = False
    last_run_dir: Optional[Path] = None

    # ------------------------------------------------------------------
    @property
    def title(self) -> str:
        """Window title for the GUI shell."""
        name = self.project_path.name if self.project_path else "Untitled"
        suffix = " (modified)" if self.dirty else ""
        return f"PyAERMOD — {name}{suffix}"

    def mark_clean(self) -> None:
        self.dirty = False

    def mark_dirty(self) -> None:
        self.dirty = True

    def reset(self) -> None:
        """Discard the current project and start fresh."""
        self.project = _empty_project()
        self.project_path = None
        self.dirty = False
        self.last_run_dir = None


__all__ = ["AppState", "_empty_project"]
