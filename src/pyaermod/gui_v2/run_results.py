"""
What the Results step shows about one run, read from the files it left.

UI-free, like :mod:`pyaermod.gui_v2.session`. :func:`view_of` turns a
:class:`~pyaermod.gui_v2.session.RunRecord` into a :class:`RunView`: the
run's verdict, AERMOD's summary tables (through
:class:`~pyaermod.output_parser.AERMODOutputParser`), its plot files
(through :func:`~pyaermod.aermod_outputs.read_plotfile`), a comparison with
the NAAQS (through :mod:`pyaermod.naaqs` and :mod:`pyaermod.design_values`)
and the files a user can download. Nothing here parses AERMOD's output
itself; every number comes from the library's readers.

A view is built once per run, when the run finishes (:func:`watch`
subscribes to ``RUN_FINISHED``), and kept for as long as the run record
lives. So an earlier run can still be shown after a later run in the same
working directory has overwritten its files; the files themselves are
checked against the checksum taken at that moment before they are offered
for download (:meth:`RunFile.read`).

A failed run's view carries no results: AERMOD stopped before its tables
were complete, and the Results step must not present them as valid.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import math
import threading
import warnings
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple

from .session import Change, RunRecord, Session, SessionEvent

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..naaqs import NAAQSStandard
    from ..output_parser import AERMODResults, ConcentrationResult

logger = logging.getLogger(__name__)

#: AERMOD's calm/missing flags, as the Results step explains them.
FLAG_MEANINGS = {
    "c": "includes calm hours",
    "m": "includes missing hours",
    "b": "includes calm and missing hours",
}

#: The order the Results step lists averaging periods in.
_PERIOD_ORDER = ("1HR", "2HR", "3HR", "4HR", "6HR", "8HR", "12HR", "24HR",
                 "MONTH", "PERIOD", "ANNUAL")

#: Mtime slack when deciding whether a file was written by this run (s).
_MTIME_SLACK_S = 2.0


class StaleFileError(RuntimeError):
    """A run's file changed on disk after the run finished."""


def period_label(key: str) -> str:
    """AERMOD's name for a period key: ``"1HR"`` -> ``"1-HR"``."""
    if key.endswith("HR") and key[:-2].isdigit():
        return f"{key[:-2]}-HR"
    return key


def period_sort_key(key: str) -> Tuple[int, str]:
    try:
        return _PERIOD_ORDER.index(key), key
    except ValueError:
        return len(_PERIOD_ORDER), key


def _period_key(ave: Any) -> Optional[str]:
    """``"1-HR"`` (a plot file's AVE column) -> ``"1HR"``."""
    text = str(ave or "").strip().upper()
    if text.endswith("-HR") and text[:-3].strip().isdigit():
        return f"{int(text[:-3])}HR"
    return text or None


# ----------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class RunFile:
    """One file of a run, as it was when the run finished."""

    label: str
    path: Path
    size: int
    sha256: str
    run_number: int

    @classmethod
    def of(cls, label: str, path: Path, run_number: int) -> Optional[RunFile]:
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return cls(label, path, len(data), hashlib.sha256(data).hexdigest(), run_number)

    @property
    def name(self) -> str:
        return self.path.name

    def read(self) -> bytes:
        """The file's bytes; :class:`StaleFileError` if it changed since."""
        try:
            data = self.path.read_bytes()
        except OSError as exc:
            raise StaleFileError(
                f"{self.name} of run {self.run_number} can no longer be read: {exc}") from exc
        if hashlib.sha256(data).hexdigest() != self.sha256:
            raise StaleFileError(
                f"{self.name} has changed since run {self.run_number} finished "
                f"(a later run in {self.path.parent} wrote it again)")
        return data


@dataclass(frozen=True)
class PlotField:
    """A plot file's values, one per receptor, as AERMOD wrote them."""

    file: RunFile
    period: str                 # "1HR", "PERIOD", ...
    group: str
    rank: Optional[str]         # "1ST"; None for PERIOD/ANNUAL
    x: Tuple[float, ...]
    y: Tuple[float, ...]
    values: Tuple[float, ...]

    @property
    def title(self) -> str:
        what = f"{self.rank} highest {period_label(self.period)}" if self.rank else (
            f"{period_label(self.period)} average")
        return f"{what} values, source group {self.group}"

    @property
    def peak(self) -> Tuple[float, float, float]:
        i = max(range(len(self.values)), key=self.values.__getitem__)
        return self.x[i], self.y[i], self.values[i]


def _plot_field(path: Path, run_number: int) -> Optional[PlotField]:
    from ..aermod_outputs import read_plotfile

    try:
        plot = read_plotfile(path)
    except (OSError, ValueError) as exc:
        logger.info("not a plot file: %s (%s)", path, exc)
        return None
    column = plot.concentration_column
    if not column:
        return None
    records = [r for r in plot.records
               if isinstance(r.get(column), (int, float))
               and isinstance(r.get("X"), (int, float)) and isinstance(r.get("Y"), (int, float))]
    if not records:
        return None
    first = records[0]
    period = _period_key(first.get("AVE") or plot.header.averaging_period)
    file = RunFile.of(f"Plot file {path.name}", path, run_number)
    if period is None or file is None:
        return None
    rank = first.get("RANK")
    return PlotField(
        file=file, period=period, group=str(first.get("GRP") or plot.header.source_group or ""),
        rank=str(rank).strip() if rank else None,
        x=tuple(float(r["X"]) for r in records),
        y=tuple(float(r["Y"]) for r in records),
        values=tuple(float(r[column]) for r in records),
    )


def _written_by(record: RunRecord, pattern_suffixes: Sequence[str]) -> List[Path]:
    """Files in the run's directory with these suffixes that the run wrote."""
    since = record.started_at.timestamp() - _MTIME_SLACK_S
    found = []
    try:
        entries = sorted(record.work_dir.iterdir())
    except OSError:
        return []
    for path in entries:
        if path.suffix.upper() not in pattern_suffixes or not path.is_file():
            continue
        try:
            if path.stat().st_mtime >= since:
                found.append(path)
        except OSError:
            continue
    return found


# ----------------------------------------------------------------------
# NAAQS
# ----------------------------------------------------------------------

#: AERMOD POLLUTID -> the pollutant's key in pyaermod.naaqs.NAAQS_TABLE.
_POLLUTANTS = {"SO2": "SO2", "NO2": "NO2", "CO": "CO", "PM25": "PM2.5",
               "PM2.5": "PM2.5", "PM-2.5": "PM2.5", "PM10": "PM10", "PM-10": "PM10",
               "LEAD": "Pb", "PB": "Pb", "O3": "O3", "OZONE": "O3"}

#: A NAAQS averaging period -> AERMOD's.
_NAAQS_PERIODS = {"1-hour": "1HR", "8-hour": "8HR", "24-hour": "24HR", "annual": "ANNUAL"}


@dataclass(frozen=True)
class NaaqsCheck:
    """One NAAQS and how this run's values compare with it."""

    standard: NAAQSStandard
    period: Optional[str]          # AERMOD's period key, or None
    level_ugm3: float
    value: Optional[float]         # µg/m³
    location: Optional[Tuple[float, float]]
    basis: str                     # "design value", "screening" or "not compared"
    how: str                       # where the value comes from
    verdict: str

    @property
    def label(self) -> str:
        s = self.standard
        return f"{s.pollutant} {s.averaging_period} ({s.form})"

    @property
    def level_text(self) -> str:
        s = self.standard
        if s.units == "ug/m3":
            return f"{s.level:g} µg/m³"
        return f"{self.level_ugm3:.1f} µg/m³ ({s.level:g} {s.units})"


def _years_in(title: str) -> Optional[int]:
    import re
    m = re.search(r"AVERAGED OVER\s+(\d+)\s+YEARS", title or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def _design_table(results: AERMODResults, period: str, rank: int) -> Optional[ConcentrationResult]:
    """AERMOD's own NAAQS table for ``period`` at ``rank`` (SO2AVE and kin)."""
    import re
    want = re.compile(rf"\b{rank}(?:ST|ND|RD|TH)-HIGHEST\b", re.IGNORECASE)
    for s in results.summaries:
        if s.output_type == "CONC" and s.averaging_period == period and s.title \
                and want.search(s.title) and "AVERAGED OVER" in s.title.upper():
            return s
    return None


def _postfile_design_value(postfiles: Sequence[Path], pollutant: str, period: str
                           ) -> Optional[Tuple[float, Tuple[float, float], str]]:
    """A design value from a text POSTFILE of ``period``, via design_values."""
    from ..design_values import naaqs_compliance_report
    from ..postfile import read_postfile

    for path in postfiles:
        try:
            post = read_postfile(path)
        except Exception as exc:          # not a POSTFILE we can read
            logger.info("could not read %s as a POSTFILE: %s", path, exc)
            continue
        df = post.data
        if df.empty or "ave" not in df:
            continue
        aves = {_period_key(a) for a in df["ave"].unique()}
        if aves != {period}:
            continue
        days = df["date"].astype(str).str[:6].nunique()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            report = naaqs_compliance_report(pollutant, df, n_years=1)
        if report.empty:
            continue
        best = report.loc[report["design_value"].idxmax()]
        how = (f"design value computed by pyaermod from {path.name} "
               f"({days} days of hourly values"
               + ("; the NAAQS form needs 3 years)" if days < 365 * 3 else ")"))
        return float(best["design_value"]), (float(best["x"]), float(best["y"])), how
    return None


def naaqs_checks(results: AERMODResults, postfiles: Sequence[Path] = ()) -> List[NaaqsCheck]:
    """Compare a successful run's concentrations with the NAAQS for its pollutant.

    For each standard, the value compared is, in this order: AERMOD's own
    design-value table (1-hour SO2 and NO2, 24-hour PM2.5, and ANNUAL
    averages for the annual standards); a design value computed with
    :func:`pyaermod.design_values.naaqs_compliance_report` from a POSTFILE
    of the standard's averaging period; or, as a screen, the highest value
    of that period, which no design value (a lower-ranked or averaged
    value) can exceed. Empty when the pollutant has no NAAQS or the
    concentrations are not in µg/m³.
    """
    from ..naaqs import NAAQS_TABLE

    info = results.run_info
    key = _POLLUTANTS.get(str(info.pollutant_id or "").strip().upper()) if info else None
    if key is None:
        return []
    checks = []
    for standard in NAAQS_TABLE.get(key, []):
        period = _NAAQS_PERIODS.get(standard.averaging_period.lower())
        level = standard.level_ugm3
        if period is None:
            checks.append(NaaqsCheck(standard, None, level, None, None, "not compared",
                                     f"AERMOD has no {standard.averaging_period} average",
                                     "Not compared"))
            continue
        top = results.concentrations.get(period)
        if top is not None and top.units != "ug/m^3":
            checks.append(NaaqsCheck(standard, period, level, None, None, "not compared",
                                     f"the run's values are in {top.units}", "Not compared"))
            continue
        found = _design_value(results, standard, period, key, postfiles)
        if found is None:
            where = ("no ANNUAL average in this run" if period == "ANNUAL"
                     else f"no {period_label(period)} average in this run")
            checks.append(NaaqsCheck(standard, period, level, None, None, "not compared",
                                     where, "Not compared"))
            continue
        value, location, basis, how = found
        if basis == "design value":
            verdict = "Above the NAAQS" if value > level else "Below the NAAQS"
        elif value <= level:
            verdict = "Below the NAAQS (so is any design value)"
        else:
            verdict = "Highest value above the NAAQS; a design value is needed"
        checks.append(NaaqsCheck(standard, period, level, value, location, basis, how, verdict))
    return checks


def _design_value(results: AERMODResults, standard: NAAQSStandard, period: str,
                  pollutant: str, postfiles: Sequence[Path]):
    if standard.percentile is not None:
        table = _design_table(results, period, standard.design_rank())
        if table is not None:
            years = _years_in(table.title or "")
            return (float(table.max_value), tuple(table.max_location), "design value",
                    f"AERMOD's table \"{table.title}\""
                    + (f" ({years} year{'s' if years != 1 else ''} of met data)" if years else ""))
        if pollutant in ("SO2", "NO2", "PM2.5"):
            computed = _postfile_design_value(postfiles, pollutant, period)
            if computed is not None:
                return computed[0], computed[1], "design value", computed[2]
    top = results.concentrations.get(period)
    if top is None or math.isnan(float(top.max_value)):
        return None
    if period == "ANNUAL" and standard.form.lower() == "annual mean":
        years = _years_in(top.title or "")
        return (float(top.max_value), tuple(top.max_location), "design value",
                f"AERMOD's table \"{top.title}\""
                + (f" ({years} year{'s' if years != 1 else ''} of met data)" if years else ""))
    return (float(top.max_value), tuple(top.max_location), "screening",
            f"the highest {period_label(period)} value in AERMOD's summary table")


# ----------------------------------------------------------------------
# The view of a run
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class RunView:
    """Everything the Results step shows about one run."""

    number: int
    work_dir: Path
    succeeded: bool
    status: str                        # "succeeded" or "failed"
    headline: str                      # "Run 2 succeeded"
    detail: str                        # one sentence on AERMOD's verdict
    fatal: Tuple[str, ...] = ()
    deck: Optional[RunFile] = None
    out: Optional[RunFile] = None
    plots: Tuple[PlotField, ...] = ()
    postfiles: Tuple[RunFile, ...] = ()
    results: Optional[AERMODResults] = None
    naaqs: Tuple[NaaqsCheck, ...] = ()
    notes: Tuple[str, ...] = ()
    record: Optional[RunRecord] = field(default=None, compare=False, repr=False)

    @property
    def files(self) -> Tuple[RunFile, ...]:
        """The files offered for download, deck first."""
        head = tuple(f for f in (self.deck, self.out) if f is not None)
        if not self.succeeded:
            return head
        return head + tuple(p.file for p in self.plots) + self.postfiles

    def concentration_tables(self) -> List[ConcentrationResult]:
        if self.results is None:
            return []
        return [self.results.concentrations[k]
                for k in sorted(self.results.concentrations, key=period_sort_key)]

    def deposition_tables(self) -> List[ConcentrationResult]:
        if self.results is None:
            return []
        return [table for kind in sorted(self.results.deposition)
                for _, table in sorted(self.results.deposition[kind].items(),
                                       key=lambda kv: period_sort_key(kv[0]))]


def build_view(record: RunRecord) -> RunView:
    """Read ``record``'s files and build its view (see :func:`view_of`)."""
    number, wd = record.number, record.work_dir
    deck = RunFile.of("Deck", record.deck_path, number)
    result = record.result
    if result is None:
        return RunView(number, wd, False, "failed", f"Run {number} failed",
                       f"AERMOD could not be run: {record.error}", deck=deck, record=record)

    out = None
    if result.output_file:
        out = RunFile.of("AERMOD output (.out)", Path(result.output_file), number)
    counts = (f"{result.fatal_count} fatal error{'s' if result.fatal_count != 1 else ''} "
              f"and {result.warning_count} warning{'s' if result.warning_count != 1 else ''}")
    if not result.success:
        fatal = tuple(str(m) for m in result.fatal_messages)
        if result.output_file is None:
            detail = result.error_message or "AERMOD wrote no .out file."
        elif result.fatal_count:
            detail = f"AERMOD stopped with {counts}."
        else:
            detail = result.error_message or "AERMOD did not report finishing successfully."
        return RunView(number, wd, False, "failed", f"Run {number} failed", detail,
                       fatal=fatal, deck=deck, out=out, record=record)

    notes: List[str] = []
    results = None
    try:
        from ..output_parser import AERMODOutputParser

        assert result.output_file is not None
        results = AERMODOutputParser(result.output_file).parse()
    except Exception as exc:
        logger.warning("could not read the .out file of run %d: %s", number, exc)
        notes.append(f"Could not parse {Path(result.output_file or '').name}: {exc}")

    plots = []
    for path in _written_by(record, (".PLT",)):
        plot = _plot_field(path, number)
        if plot is not None:
            plots.append(plot)
    plots.sort(key=lambda p: (period_sort_key(p.period), p.group, p.file.name))

    postfiles = _written_by(record, (".PST",))
    posts = tuple(f for f in (RunFile.of(f"POSTFILE {p.name}", p, number) for p in postfiles)
                  if f is not None)
    checks: Tuple[NaaqsCheck, ...] = ()
    if results is not None:
        try:
            checks = tuple(naaqs_checks(results, postfiles))
        except Exception as exc:
            logger.warning("could not compare run %d with the NAAQS: %s", number, exc)
            notes.append(f"Could not compare with the NAAQS: {exc}")
    return RunView(number, wd, True, "succeeded", f"Run {number} succeeded",
                   f"AERMOD finished successfully with {counts}.",
                   deck=deck, out=out, plots=tuple(plots), postfiles=posts, results=results,
                   naaqs=checks, notes=tuple(notes), record=record)


_LOCK = threading.Lock()
# id(record) -> (weak reference to the record, its view)
_VIEWS: Dict[int, Tuple[Any, RunView]] = {}


def view_of(record: RunRecord) -> RunView:
    """The view of ``record``, built when first asked for and then kept."""
    with _LOCK:
        entry = _VIEWS.get(id(record))
        if entry is not None and entry[0]() is record:
            return entry[1]
    view = build_view(record)
    with _LOCK:
        entry = _VIEWS.get(id(record))
        if entry is not None and entry[0]() is record:
            return entry[1]
        key = id(record)
        _VIEWS[key] = (weakref.ref(record, functools.partial(_forget, key)), view)
    return view


def _forget(key: int, _ref: Any) -> None:
    """Drop a collected record's view (called by its weak reference)."""
    views = _VIEWS          # None once the interpreter is shutting down
    if views is not None:
        views.pop(key, None)


def watch(session: Session) -> Callable[[], None]:
    """Build each run's view as soon as it finishes; return the unsubscribe.

    Then a later run in the same working directory cannot overwrite what
    an earlier run's view shows. Every page showing results subscribes
    (views are built once however many do) and unsubscribes when it goes.
    """
    def on_finished(change: Change) -> None:
        if change.run is not None:
            view_of(change.run)

    return session.subscribe(SessionEvent.RUN_FINISHED, on_finished)


def completed_runs(session: Session) -> List[RunRecord]:
    """The runs Results can show (AERMOD ran), newest first."""
    return [r for r in reversed(session.runs) if r.result is not None]


def overwritten_by(session: Session, record: RunRecord) -> Optional[RunRecord]:
    """The later run of ``session`` that wrote into ``record``'s directory."""
    def same(a: Path, b: Path) -> bool:
        try:
            return a.resolve() == b.resolve()
        except OSError:
            return a == b

    for later in session.runs:
        if later.number > record.number and same(later.work_dir, record.work_dir):
            return later
    return None


__all__ = [
    "FLAG_MEANINGS",
    "NaaqsCheck",
    "PlotField",
    "RunFile",
    "RunView",
    "StaleFileError",
    "build_view",
    "completed_runs",
    "naaqs_checks",
    "overwritten_by",
    "period_label",
    "period_sort_key",
    "view_of",
    "watch",
]
