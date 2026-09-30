"""
The GUI's seven steps and how far along each one is.

The step list in the shell (:mod:`pyaermod.gui_v2.app`) shows one badge
per step, and the header a one-line readiness summary; both are computed
here from the session's latest :class:`~pyaermod.validator.ValidationResult`
and its runs, with no UI, so they can be tested alone. Pages that send the
user to another step (a checklist item that links to Sources) name it by
its id in :data:`STEP_IDS`.

A step's status is one of :class:`StepStatus`:

- *not started*: nothing has been entered yet (no sources, no receptors,
  no met files; no run for Review & Run and Results);
- *error*: the validator reports an error for a part of the project the
  step edits (or, for Review & Run and Results, the latest run failed;
  a cancelled run is no result, so the run before it decides);
- *warning*: only warnings;
- *complete*: neither.

Which step a validator message belongs to follows the ``pathway`` it
names (:func:`step_of`): ``ControlPathway`` is the Project step,
``PointSource(STACK1)`` the Sources step, ``PolarGrid(GRID1)`` the
Receptors step, and so on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..input_generator import AERMODProject
    from ..validator import ValidationError, ValidationResult
    from .session import RunRecord


@dataclass(frozen=True)
class Step:
    """One step of the workflow: its id (for navigation) and its label."""

    id: str
    label: str


#: The steps in the order the step list shows them.
STEPS: Sequence[Step] = (
    Step("project", "Project"),
    Step("sources", "Sources"),
    Step("receptors", "Receptors"),
    Step("meteorology", "Meteorology"),
    Step("output", "Output"),
    Step("run", "Review & Run"),
    Step("results", "Results"),
)

STEP_IDS = tuple(s.id for s in STEPS)
LABELS: Dict[str, str] = {s.id: s.label for s in STEPS}


class StepStatus(StrEnum):
    """A step's badge. The value is how the badge reads."""

    NOT_STARTED = "not started"
    COMPLETE = "complete"
    WARNING = "warning"
    ERROR = "error"


#: Validator pathway names (the part before any "(id)") -> step id.
_PATHWAY_STEPS = {
    "ControlPathway": "project",
    "ChemistryOptions": "project",
    "EventPathway": "project",
    "SourcePathway": "sources",
    "BuoyLineSegment": "sources",
    "SolidBarrier": "sources",
    "SourceGroupDefinition": "sources",
    "OLMGroup": "sources",
    "BackgroundConcentration": "sources",
    "ReceptorPathway": "receptors",
    "CartesianGrid": "receptors",
    "PolarGrid": "receptors",
    "DiscreteReceptor": "receptors",
    "MeteorologyPathway": "meteorology",
    "OutputPathway": "output",
}


def step_of(pathway: str) -> str:
    """The step that edits what a validator message names.

    ``"PointSource(STACK1)"`` and every other ``<Type>Source(...)`` is
    ``"sources"``; a name this table does not know is ``"run"``, where
    Review & Run lists every message.
    """
    head = str(pathway).split("(", 1)[0].strip()
    if head in _PATHWAY_STEPS:
        return _PATHWAY_STEPS[head]
    if head.endswith("Source"):
        return "sources"
    return "run"


def problems_by_step(validation: Optional[ValidationResult]) -> Dict[str, List[ValidationError]]:
    """Every validator message, grouped by :func:`step_of`, in the validator's order."""
    grouped: Dict[str, List[Any]] = {s.id: [] for s in STEPS}
    if validation is not None:
        for problem in validation.errors:
            grouped[step_of(problem.pathway)].append(problem)
    return grouped


def _not_started(project: AERMODProject) -> Dict[str, bool]:
    receptors = project.receptors
    met = project.meteorology
    return {
        "sources": not project.sources.sources,
        "receptors": not (receptors.cartesian_grids or receptors.polar_grids
                          or receptors.discrete_receptors),
        "meteorology": not ((met.surface_file or "").strip() or (met.profile_file or "").strip()),
    }


def _from_problems(problems: Sequence[Any]) -> StepStatus:
    if any(p.severity != "warning" for p in problems):
        return StepStatus.ERROR
    if problems:
        return StepStatus.WARNING
    return StepStatus.COMPLETE


def _from_run(record: Optional[RunRecord]) -> StepStatus:
    if record is None:
        return StepStatus.NOT_STARTED
    return StepStatus.COMPLETE if record.success else StepStatus.ERROR


def step_statuses(project: AERMODProject, validation: Optional[ValidationResult],
                  runs: Sequence[RunRecord] = ()) -> Dict[str, StepStatus]:
    """The badge of every step, keyed by step id.

    ``validation`` is the session's latest result (None: not validated,
    which shows the editing steps as complete unless they are empty);
    ``runs`` its finished runs, oldest first. Review & Run and Results
    both follow the latest run that was not cancelled, which is the run
    the Results step shows (:func:`~pyaermod.gui_v2.run_results.completed_runs`):
    a cancel is no result (WP-G4), so it neither marks the steps as
    failed nor hides the run before it.
    """
    grouped = problems_by_step(validation)
    empty = _not_started(project)
    statuses: Dict[str, StepStatus] = {}
    for step in ("project", "sources", "receptors", "meteorology", "output"):
        if empty.get(step, False):
            statuses[step] = StepStatus.NOT_STARTED
        else:
            statuses[step] = _from_problems(grouped[step])
    shown = [r for r in runs if not r.in_progress and not r.cancelled]
    statuses["run"] = statuses["results"] = _from_run(shown[-1] if shown else None)
    return statuses


def readiness(validation: Optional[ValidationResult]) -> str:
    """The header's one-line summary of whether the project can run."""
    if validation is None:
        return "Not checked yet"
    grouped = problems_by_step(validation)
    errors = {step: [p for p in problems if p.severity != "warning"]
              for step, problems in grouped.items()}
    blocked = [LABELS[step] for step, found in errors.items() if found]
    n_errors = sum(len(found) for found in errors.values())
    n_warnings = validation.warning_count
    if blocked:
        noun = "problem" if n_errors == 1 else "problems"
        return f"Not ready to run: {n_errors} {noun} in {', '.join(blocked)}"
    if n_warnings:
        noun = "warning" if n_warnings == 1 else "warnings"
        return f"Ready to run, with {n_warnings} {noun}"
    return "Ready to run"


def step_accessible_name(step: Step, status: StepStatus) -> str:
    """What a screen reader (and the journeys) hear for a step: ``"Sources, complete"``."""
    return f"{step.label}, {status.value}"


__all__ = [
    "LABELS",
    "STEPS",
    "STEP_IDS",
    "Step",
    "StepStatus",
    "problems_by_step",
    "readiness",
    "step_accessible_name",
    "step_of",
    "step_statuses",
]
