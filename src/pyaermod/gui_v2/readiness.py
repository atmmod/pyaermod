"""
The Review & Run checklist, with no UI.

:func:`review` says what blocks a run of a session's project and what the
user should know first. The NiceGUI Review & Run step
(:mod:`pyaermod.gui_v2.pages.run`) and the browser GUI
(:mod:`pyaermod.browser`) both show it, so the two cannot disagree on
when a project is ready.

Everything the checklist knows comes from the library:
:class:`~pyaermod.validator.Validator`,
:func:`~pyaermod.validator_advanced.check_annual_met_coverage` (ANNUAL
with less than a year of met data, which AERMOD aborts with E480) and
:meth:`Session.deck_text`, whose output files must be in folders that
exist where AERMOD runs (it does not create them, and stops with E500).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .session import DeckError, Session
from .steps import STEP_IDS as _STEP_IDS
from .steps import STEPS as _STEPS
from .steps import step_of

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..aermet import SurfaceFilePeriod
    from ..validator import ValidationError

#: The GUI's steps, in order (the shell's, :data:`..steps.STEP_IDS`).
#: ``goto`` callbacks receive one of these.
STEP_IDS = _STEP_IDS

#: What the user reads for each step, as the step list names it.
STEP_TITLES = {step.id: step.label for step in _STEPS}

#: The common-errors page of the documentation site.
COMMON_ERRORS_URL = "https://atmmod.github.io/pyaermod/common-errors/"

#: AERMOD message code -> its anchor on the common-errors page
#: (``docs/common-errors.md``; a test checks each anchor exists there).
COMMON_ERRORS = {
    "E101": "e101",
    "E480": "e480",
    "E500": "e500",
}

NO_BINARY = "No 'aermod' binary on PATH. Install AERMOD and re-launch."


def aermod_available() -> bool:
    """Whether a run would find AERMOD
    (:func:`pyaermod.runner.find_aermod_executable`)."""
    from ..runner import find_aermod_executable

    try:
        find_aermod_executable()
    except (FileNotFoundError, OSError):
        return False
    return True

# ----------------------------------------------------------------------
# The review: what blocks a run, and what the user should know first
# ----------------------------------------------------------------------

@dataclass
class ChecklistItem:
    """The problems one step has, in the order they were found."""

    step: str
    problems: List[str] = field(default_factory=list)
    # Other steps where the problems can also be fixed (ANNUAL with short
    # met data: longer met files, or other averaging periods on Project).
    also: List[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return STEP_TITLES.get(self.step, self.step)

    @property
    def links(self) -> List[str]:
        """The steps its links open, its own first (Review & Run has none)."""
        return [s for s in [self.step, *self.also] if s != "run"]


@dataclass
class Review:
    """Everything the step shows before a run."""

    blocking: List[ChecklistItem]
    warnings: List[ChecklistItem]
    deck: Optional[str]
    met_file: Optional[Path] = None
    met_summary: Optional[str] = None

    @property
    def ready(self) -> bool:
        return not self.blocking


def _step_for_pathway(pathway: str) -> str:
    """The step that edits what a :class:`ValidationError` names.

    The step badges' mapping (:func:`~pyaermod.gui_v2.steps.step_of`), so a
    badge and the checklist name the same step; what no step edits is the
    Project step's.
    """
    step = step_of(pathway)
    return "project" if step == "run" else step


_PROJECT_PARTS = {"control": "project", "sources": "sources", "receptors": "receptors",
                  "meteorology": "meteorology", "output": "output"}


def _step_for_deck_error(message: str) -> str:
    """The step a :class:`DeckError` points at ("project.meteorology.start_year ...")."""
    head = message.split(None, 1)[0] if message else ""
    parts = head.split(".")
    if len(parts) > 1 and parts[0] == "project":
        return _PROJECT_PARTS.get(parts[1].split("[")[0], "project")
    return "project"


def _problem_text(error: Any) -> str:
    """One validator finding as a sentence: "surface file must not be empty"."""
    name = error.field.replace("_", " ")
    subject = f"{error.pathway.replace('(', ' ').rstrip(')')} " if "(" in error.pathway else ""
    if "/" in name:                     # "grids/receptors": the message says it all
        return f"{subject}{error.message}"
    return f"{subject}{name} {error.message}".strip()


def _add(items: Dict[str, ChecklistItem], step: str, problem: str) -> None:
    item = items.setdefault(step, ChecklistItem(step))
    if problem not in item.problems:
        item.problems.append(problem)


def _ordered(items: Dict[str, ChecklistItem]) -> List[ChecklistItem]:
    return sorted(items.values(), key=lambda i: STEP_IDS.index(i.step)
                  if i.step in STEP_IDS else len(STEP_IDS))


#: A relative met file with a blank working directory. AERMOD opens a
#: relative path from its working directory, and a blank one is a new,
#: empty temporary folder, so the run would fail with E500.
RELATIVE_MET = ("{label} {name} is a relative path, which AERMOD looks for in its working "
                "directory, and a blank working directory is a new, empty folder: give the "
                "file's full path, or set the working directory below")


#: The deck keywords whose lines name files AERMOD writes (coset.f and
#: ouset.f, v26135). DEBUGOPT and MULTYEAR also name files it reads,
#: whose folders must exist as well.
OUTPUT_KEYWORDS = frozenset({
    "CO ERRORFIL", "CO SAVEFILE", "CO EVENTFIL", "CO DEBUGOPT", "CO MULTYEAR",
    "OU SUMMFILE", "OU PLOTFILE", "OU POSTFILE", "OU MAXIFILE", "OU RANKFILE",
    "OU SEASONHR", "OU EVALFILE", "OU TOXXFILE", "OU MAXDAILY", "OU MXDYBYYR",
    "OU MAXDCONT",
})

#: An output file in a folder, with a blank working directory: the run
#: goes to a new, empty folder, where no folder of the deck exists.
RELATIVE_OUTPUT = ("{keyword} {name} is in a folder, {folder}, which a blank working "
                   "directory (a new, empty folder) does not have, and AERMOD does not "
                   "create folders: set the working directory below to a folder that has "
                   "{folder}{hint}")

#: An output file whose folder does not exist where AERMOD will run.
MISSING_OUTPUT_FOLDER = ("{keyword} {name} is in a folder that does not exist, {where}, and "
                         "AERMOD does not create folders: create it, or set the working "
                         "directory below to a folder that has {folder}{hint}")


def output_folders(deck: str) -> List[Tuple[str, str, str]]:
    """``[(keyword, path as written, folder)]`` for every file the deck has
    AERMOD write in a folder (any field of an :data:`OUTPUT_KEYWORDS` line
    that names one); a bare file name goes in the working directory itself."""
    from .run_results import deck_lines

    found = []
    for keyword, fields in deck_lines(deck):
        if keyword not in OUTPUT_KEYWORDS:
            continue
        for value in fields:
            folder = Path(value).parent
            if str(folder) not in ("", "."):
                found.append((keyword, value, str(folder)))
    return found


def _missing_output_folders(session: Session, deck: str, working_dir: str
                            ) -> List[Tuple[str, str]]:
    """``[(step, problem)]`` for each output file whose folder AERMOD will not find."""
    base = Path(working_dir).expanduser() if working_dir else None
    imported = session.last_import.path if session.last_import is not None else None
    deck_dir = imported.parent if imported is not None else None
    found = []
    for keyword, name, folder in output_folders(deck):
        path = Path(name)
        if path.is_absolute():
            target = path.parent
        elif base is None:
            target = None
        else:
            # Lexically: the run creates the working directory itself.
            target = Path(os.path.normpath(base / path)).parent
        if target is not None and target.is_dir():
            continue
        hint = ""
        if (not path.is_absolute() and deck_dir is not None and base != deck_dir
                and (deck_dir / path).parent.is_dir()):
            hint = f", such as the deck's own folder, {deck_dir}"
        step = "output" if keyword.startswith("OU ") else "run"
        if target is None:
            found.append((step, RELATIVE_OUTPUT.format(keyword=keyword, name=name,
                                                       folder=folder, hint=hint)))
        else:
            found.append((step, MISSING_OUTPUT_FOLDER.format(
                keyword=keyword, name=name, folder=folder, where=target, hint=hint)))
    return found


#: A met file whose path starts with ``~``. AERMOD does not expand ``~``:
#: it would look for a folder named ``~`` in its working directory (E500).
HOME_MET = ("{label} {name} starts with ~, which AERMOD does not expand to your home "
            "folder: give the file's full path")


def _met_files(met: Any) -> List[Tuple[str, str]]:
    """``[(label, path)]`` for the met files ``met`` names."""
    found = []
    for label, attr in (("surface file", "surface_file"), ("profile file", "profile_file")):
        name = str(getattr(met, attr, "") or "").strip().strip('"')
        if name:
            found.append((label, name))
    return found


def _home_met_files(met: Any) -> List[Tuple[str, str]]:
    """``[(label, path)]`` for the met files ``met`` names by a path starting with ``~``."""
    return [(label, name) for label, name in _met_files(met) if name.startswith("~")]


def _relative_met_files(met: Any) -> List[Tuple[str, str]]:
    """``[(label, path)]`` for the met files ``met`` names by a relative path.

    A path starting with ``~`` is left to :func:`_home_met_files`.
    """
    return [(label, name) for label, name in _met_files(met)
            if not name.startswith("~") and not Path(name).is_absolute()]


def _met_file_text(label: str, problem: str) -> str:
    """``problem`` ("surface file X does not exist") without its leading label.

    Findings carry the field (``surface_file``) and the rest of the
    sentence, which :func:`_problem_text` puts back together.
    """
    return problem[len(label) + 1:] if problem.startswith(f"{label} ") else problem


def met_file_findings(met: Any, working_dir: str) -> List[ValidationError]:
    """The met files AERMOD would not find, as validator findings (errors).

    A path starting with ``~`` (:data:`HOME_MET`), a relative path with a
    blank working directory (:data:`RELATIVE_MET`), and a file that is not
    there where AERMOD opens it: a relative path in ``working_dir``. An
    empty field is the validator's ("must not be empty").
    """
    from ..validator import ValidationError

    found = []
    for label, name in _met_files(met):
        attr = label.replace(" ", "_")
        path = Path(name)
        if name.startswith("~"):
            problem = HOME_MET.format(label=label, name=name)
        elif not path.is_absolute() and not working_dir:
            problem = RELATIVE_MET.format(label=label, name=name)
        else:
            if not path.is_absolute():
                path = Path(working_dir).expanduser() / path
            if path.is_file():
                continue
            what = "is a folder, not a file" if path.is_dir() else "does not exist"
            problem = f"{label} {path} {what}"
        found.append(ValidationError("MeteorologyPathway", attr,
                                     _met_file_text(label, problem)))
    return found


def met_header_findings(met: Any, period: Optional[SurfaceFilePeriod]) -> List[ValidationError]:
    """Warnings for station IDs and a first year that differ from the surface file's header.

    AERMOD compares the SURFDATA and UAIRDATA station IDs with the IDs in
    the surface file's header, as integers, and warns (W530) when they
    differ (``meset.f``).
    """
    from ..validator import ValidationError

    if period is None:
        return []
    found = []
    for attr, header, what in (("surface_station_id", period.surface_station, "surface"),
                               ("upper_air_station_id", period.upper_air_station, "upper-air")):
        text = str(header or "").strip()
        value = getattr(met, attr, None)
        if text.isdigit() and value != int(text):
            found.append(ValidationError(
                "MeteorologyPathway", attr,
                f"is {value}, but the surface file's header names {what} station {text}",
                severity="warning"))
    year = getattr(met, "data_start_year", None)
    if year != period.first_year:
        found.append(ValidationError(
            "MeteorologyPathway", "data_start_year",
            f"is {year}, but the surface file's data start in {period.first_year}",
            severity="warning"))
    return found


def project_findings(session: Session) -> List[ValidationError]:
    """Everything the checks find in the session's project, as the next run would see it.

    The validator's findings, the met files AERMOD would not find
    (:func:`met_file_findings`), ANNUAL with less than a year of met data
    and station IDs or a year that differ from the surface file's header
    (:func:`met_header_findings`). The header's readiness line and the
    step badges (``Session.validate(check_files=True)``) and the Review &
    Run checklist (:func:`review`) are all made from this, so they agree.
    """
    import logging

    from ..validator import Validator

    project = session.project
    findings = list(Validator.validate(project).errors)
    working_dir = str(session.run_options.working_dir or "").strip()
    findings += met_file_findings(project.meteorology, working_dir)
    try:
        coverage = session.met_coverage()
    except Exception:                   # a surface file the reader trips on
        logging.getLogger(__name__).exception("checking the met data's coverage raised")
        return findings
    findings += coverage.warnings
    findings += met_header_findings(project.meteorology, coverage.period)
    return findings


def item_findings(project: Any, draft: Any) -> List[str]:
    """The validator's findings for one source or receptor, as sentences.

    The draft is checked alone, in a shallow copy of ``project`` (its
    control options apply), so a large project costs nothing extra.
    """
    import copy

    from ..input_generator import ReceptorPathway, SourcePathway
    from ..validator import Validator

    probe = copy.copy(project)
    if hasattr(draft, "source_id"):
        probe.sources = SourcePathway(sources=[draft])
        probe.receptors = ReceptorPathway()
    else:
        probe.sources = SourcePathway(sources=[])
        probe.receptors = ReceptorPathway()
        attr = {"CartesianGrid": "cartesian_grids", "PolarGrid": "polar_grids",
                "DiscreteReceptor": "discrete_receptors"}.get(type(draft).__name__)
        if attr is not None:
            getattr(probe.receptors, attr).append(draft)
    names = (type(draft).__name__, "BuoyLineSegment")
    found: List[str] = []
    try:
        errors = Validator.validate(probe, advanced=False).errors
    except Exception as exc:            # a value the validator cannot compare, say
        return [f"it could not be checked: {exc}"]
    for finding in errors:
        if finding.severity == "error" and str(finding.pathway).startswith(names):
            text = _problem_text(finding)
            if text not in found:
                found.append(text)
    return found


def review(session: Session, *, have_binary: bool = True) -> Review:
    """Review the session's project for a run. Emits nothing.

    Validator errors, a deck the project cannot be written as, a met file
    named by a relative path while the working directory is blank, a met
    file whose path starts with ``~`` (which AERMOD does not expand), an
    output file in a folder that will not exist where AERMOD runs
    (:func:`output_folders`; an imported deck's ``../Outputs/X.SUM``), and a
    missing AERMOD binary block the run; validator warnings, a surface
    file that cannot be read, and ANNUAL with less than a year of met
    data (:func:`~pyaermod.validator_advanced.check_annual_met_coverage`)
    do not.
    """

    blocking: Dict[str, ChecklistItem] = {}
    warnings: Dict[str, ChecklistItem] = {}

    # Not read from the server's own directory with a blank working
    # directory, nor from the home folder: AERMOD would see neither.
    coverage = session.met_coverage()
    annual = {f.message for f in coverage.warnings}
    try:
        findings = project_findings(session)
    except Exception as exc:  # a value the validator cannot compare, say
        findings = []
        _add(blocking, "project", f"the project could not be checked: {exc}")
    for finding in findings:
        if finding.message in annual:
            continue                    # below, with its link to Project
        target = blocking if finding.severity == "error" else warnings
        _add(target, _step_for_pathway(finding.pathway), _problem_text(finding))

    deck: Optional[str] = None
    try:
        deck = session.deck_text()
    except DeckError as exc:
        _add(blocking, _step_for_deck_error(str(exc)), f"the deck cannot be written: {exc}")

    if not have_binary:
        _add(blocking, "run", NO_BINARY)

    working_dir = str(session.run_options.working_dir or "").strip()
    if deck is not None:
        for step, missing in _missing_output_folders(session, deck, working_dir):
            _add(blocking, step, missing)

    path, period, problem = coverage.path, coverage.period, coverage.problem
    summary = None
    if problem is not None and path is not None and path.is_file():
        # A missing file is a blocking finding already.
        _add(warnings, "meteorology", f"surface file {problem}")
    elif period is not None:
        summary = f"{path.name if path else 'The surface file'} holds {period.describe()}."
        for finding in coverage.warnings:
            step = _step_for_pathway(finding.pathway)
            _add(warnings, step, finding.message)
            # The other fix: averaging periods without ANNUAL.
            if "project" not in warnings[step].also and step != "project":
                warnings[step].also.append("project")

    return Review(blocking=_ordered(blocking), warnings=_ordered(warnings), deck=deck,
                  met_file=path, met_summary=summary)


__all__ = [
    "COMMON_ERRORS",
    "COMMON_ERRORS_URL",
    "HOME_MET",
    "MISSING_OUTPUT_FOLDER",
    "NO_BINARY",
    "OUTPUT_KEYWORDS",
    "RELATIVE_MET",
    "RELATIVE_OUTPUT",
    "STEP_IDS",
    "STEP_TITLES",
    "ChecklistItem",
    "Review",
    "aermod_available",
    "item_findings",
    "met_file_findings",
    "met_header_findings",
    "output_folders",
    "project_findings",
    "review",
]
