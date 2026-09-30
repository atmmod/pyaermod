"""The step list's badges and the header's readiness line, with no UI (tier T0).

``pyaermod.gui_v2.steps`` turns the session's validation and runs into a
status per step; the shell shows them, and the journeys read them from
the steps' accessible names (J7).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pyaermod.gui_v2.session import RunRecord
from pyaermod.gui_v2.state import _empty_project
from pyaermod.gui_v2.steps import (
    LABELS,
    STEP_IDS,
    STEPS,
    StepStatus,
    problems_by_step,
    readiness,
    step_accessible_name,
    step_of,
    step_statuses,
)
from pyaermod.input_generator import PointSource, PolarGrid
from pyaermod.validator import ValidationError, ValidationResult, Validator

NOT_STARTED, COMPLETE, WARNING, ERROR = (StepStatus.NOT_STARTED, StepStatus.COMPLETE,
                                         StepStatus.WARNING, StepStatus.ERROR)


def _stack() -> PointSource:
    return PointSource("STACK1", 0.0, 0.0, stack_height=65.0, stack_temp=425.0,
                       exit_velocity=18.0, stack_diameter=3.0, emission_rate=100.0)


def _run(success: bool, *, raised: bool = False, cancelled: bool = False) -> RunRecord:
    class _Result:
        def __init__(self, ok):
            self.success = ok
            self.cancelled = cancelled

    return RunRecord(number=1, work_dir=Path("run"), deck_path=Path("run/x.inp"),
                     started_at=datetime(2026, 9, 29), finished_at=datetime(2026, 9, 29),
                     result=None if raised else _Result(success),
                     error="boom" if raised else None)


def test_seven_steps_in_order():
    assert STEP_IDS == ("project", "sources", "receptors", "meteorology", "output", "run",
                        "results")
    assert [s.label for s in STEPS] == ["Project", "Sources", "Receptors", "Meteorology",
                                        "Output", "Review & Run", "Results"]
    assert LABELS["run"] == "Review & Run"


@pytest.mark.parametrize(("pathway", "step"), [
    ("ControlPathway", "project"),
    ("ChemistryOptions", "project"),
    ("SourcePathway", "sources"),
    ("PointSource(STACK1)", "sources"),
    ("RLineExtSource(R1)", "sources"),
    ("BuoyLineSegment(B1)", "sources"),
    ("SourceGroupDefinition(G1)", "sources"),
    ("ReceptorPathway", "receptors"),
    ("PolarGrid(GRID1)", "receptors"),
    ("MeteorologyPathway", "meteorology"),
    ("OutputPathway", "output"),
    ("SomethingNew", "run"),
])
def test_messages_belong_to_the_step_that_edits_them(pathway, step):
    assert step_of(pathway) == step


def test_blank_project():
    project = _empty_project()
    validation = Validator.validate(project, check_files=True)
    statuses = step_statuses(project, validation)
    assert statuses == {"project": COMPLETE, "sources": NOT_STARTED, "receptors": NOT_STARTED,
                        "meteorology": NOT_STARTED, "output": COMPLETE, "run": NOT_STARTED,
                        "results": NOT_STARTED}
    assert readiness(validation) == (
        "Not ready to run: 4 problems in Sources, Receptors, Meteorology")


def test_a_source_completes_its_step_and_removing_it_resets_it():
    project = _empty_project()
    project.sources.sources.append(_stack())
    assert step_statuses(project, Validator.validate(project))["sources"] is COMPLETE
    project.sources.sources.clear()
    assert step_statuses(project, Validator.validate(project))["sources"] is NOT_STARTED


def test_errors_and_warnings():
    project = _empty_project()
    project.sources.sources.append(_stack())
    project.receptors.polar_grids.append(PolarGrid())
    project.meteorology.surface_file = "missing.sfc"
    validation = ValidationResult([
        ValidationError("PointSource(STACK1)", "stack_height", "odd", severity="warning"),
        ValidationError("MeteorologyPathway", "surface_file", "does not exist"),
    ])
    statuses = step_statuses(project, validation)
    assert statuses["sources"] is WARNING
    assert statuses["receptors"] is COMPLETE
    assert statuses["meteorology"] is ERROR
    assert readiness(validation) == "Not ready to run: 1 problem in Meteorology"
    only_warning = ValidationResult(validation.errors[:1])
    assert readiness(only_warning) == "Ready to run, with 1 warning"
    assert readiness(ValidationResult()) == "Ready to run"
    assert readiness(None) == "Not checked yet"


def test_runs():
    project = _empty_project()
    assert step_statuses(project, None, [_run(True)])["run"] is COMPLETE
    assert step_statuses(project, None, [_run(True)])["results"] is COMPLETE
    assert step_statuses(project, None, [_run(False)])["run"] is ERROR
    # A run whose runner raised is the latest run on both steps: Results
    # shows it, as failed, with the runner's reason.
    statuses = step_statuses(project, None, [_run(True), _run(False, raised=True)])
    assert statuses["run"] is ERROR and statuses["results"] is ERROR


def test_a_cancelled_run_is_no_result():
    """Results skips a cancelled run, and so do the badges (WP-G4's rule)."""
    project = _empty_project()
    only = step_statuses(project, None, [_run(False, cancelled=True)])
    assert only["run"] is NOT_STARTED and only["results"] is NOT_STARTED
    after = step_statuses(project, None, [_run(True), _run(False, cancelled=True)])
    assert after["run"] is COMPLETE and after["results"] is COMPLETE
    failed = step_statuses(project, None, [_run(False), _run(False, cancelled=True)])
    assert failed["run"] is ERROR and failed["results"] is ERROR


def test_problems_by_step_keeps_every_step():
    grouped = problems_by_step(None)
    assert set(grouped) == set(STEP_IDS) and not any(grouped.values())


def test_accessible_name():
    assert step_accessible_name(STEPS[1], NOT_STARTED) == "Sources, not started"
    assert step_accessible_name(STEPS[5], COMPLETE) == "Review & Run, complete"
