"""
PyAERMOD runner UX helpers.

Additions on top of `runner.py` / `BatchRunner`:

- `extract_errmsg` / `tail_output` / `summarize_failure`: pull useful
  diagnostics from AERMOD's ERRMSG.TMP and .OUT files when a run fails.
- `ProgressReporter` protocol with `TqdmProgress` (if tqdm is installed)
  and `LoggingProgress` / `NoOpProgress` fallbacks.
- `resume_batch`: given a list of input files and an output dir, return
  which already have valid `.out` files and which still need to run.
- `RunManifest`: JSON-backed batch state for resume / inspection.
- `generate_slurm_script`: produce a SLURM job-array template for a
  directory of .inp files.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Protocol, Sequence, Union

from ._optional import optional_import, require
from .runner import _read_message_summary, _severity_count

_tqdm_mod = optional_import("tqdm")
HAS_TQDM = _tqdm_mod is not None
tqdm = getattr(_tqdm_mod, "tqdm", None) if _tqdm_mod else None


# ---------------------------------------------------------------------------
# Failure diagnostics
# ---------------------------------------------------------------------------

_AERMOD_FATAL = re.compile(r"^\s*\*?\*?\s*(ERROR|FATAL|ABORT)", re.MULTILINE | re.IGNORECASE)
_AERMET_ERR_LINE = re.compile(r"\bE\d{3}\b")


@dataclass
class ERRMSGInfo:
    """Parsed contents of AERMOD's ERRMSG.TMP (or equivalent)."""
    path: Path
    messages: List[str] = field(default_factory=list)
    error_codes: List[str] = field(default_factory=list)

    @property
    def has_fatal(self) -> bool:
        return any("FATAL" in m.upper() or "ERROR" in m.upper() for m in self.messages)


def extract_errmsg(path: Union[str, Path]) -> Optional[ERRMSGInfo]:
    """Parse an AERMOD ERRMSG.TMP-style file.

    Returns None if the file doesn't exist.
    """
    p = Path(path)
    if not p.exists():
        return None
    text = p.read_text(encoding="latin-1", errors="replace")
    messages = [ln.strip() for ln in text.splitlines() if ln.strip()]
    codes = _AERMET_ERR_LINE.findall(text)
    return ERRMSGInfo(path=p, messages=messages, error_codes=codes)


def tail_output(path: Union[str, Path], n_lines: int = 40) -> List[str]:
    """Return the last `n_lines` of a file as a list of strings."""
    p = Path(path)
    if not p.exists():
        return []
    # Read whole file; AERMOD .OUT files are typically < 10 MB.
    text = p.read_text(encoding="latin-1", errors="replace").splitlines()
    return text[-n_lines:]


def summarize_failure(
    input_file: Union[str, Path],
    working_dir: Union[str, Path],
) -> str:
    """Return a human-readable failure summary.

    Gathers ERRMSG.TMP content plus the tail of the .OUT file.
    """
    wd = Path(working_dir)
    stem = Path(input_file).stem
    lines: List[str] = []
    lines.append(f"AERMOD run failed: {input_file}")
    lines.append(f"Working dir: {wd}")

    for err_name in ("ERRMSG.TMP", "errmsg.tmp", f"{stem}.err"):
        info = extract_errmsg(wd / err_name)
        if info is not None:
            lines.append(f"-- {err_name} ({len(info.messages)} lines) --")
            lines.extend(info.messages[:20])
            if info.error_codes:
                lines.append(f"Error codes: {', '.join(info.error_codes[:10])}")
            break

    out_path = wd / f"{stem}.out"
    if out_path.exists():
        tail = tail_output(out_path, n_lines=20)
        lines.append(f"-- tail of {out_path.name} --")
        lines.extend(tail)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------

class ProgressReporter(Protocol):
    def start(self, total: int, description: str = "") -> None: ...
    def update(self, n: int = 1, message: str = "") -> None: ...
    def finish(self) -> None: ...


class NoOpProgress:
    """Silent progress reporter."""
    def start(self, total: int, description: str = "") -> None: pass
    def update(self, n: int = 1, message: str = "") -> None: pass
    def finish(self) -> None: pass


class LoggingProgress:
    """Progress reporter that emits `INFO`-level log lines."""
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.total = 0
        self.count = 0

    def start(self, total: int, description: str = "") -> None:
        self.total = total
        self.count = 0
        self.logger.info(f"{description or 'Progress'}: 0/{total}")

    def update(self, n: int = 1, message: str = "") -> None:
        self.count += n
        pct = (self.count / self.total * 100) if self.total else 0.0
        msg = f" ({message})" if message else ""
        self.logger.info(f"Progress: {self.count}/{self.total} ({pct:.1f}%){msg}")

    def finish(self) -> None:
        self.logger.info(f"Progress: {self.count}/{self.total} done")


class TqdmProgress:
    """Progress reporter using `tqdm`. Only works if tqdm is installed."""
    def __init__(self) -> None:
        require(tqdm, "tqdm", pip_extra="hpc")
        self.bar = None

    def start(self, total: int, description: str = "") -> None:
        self.bar = tqdm(total=total, desc=description or "AERMOD")

    def update(self, n: int = 1, message: str = "") -> None:
        if self.bar is not None:
            if message:
                self.bar.set_postfix_str(message)
            self.bar.update(n)

    def finish(self) -> None:
        if self.bar is not None:
            self.bar.close()


# ---------------------------------------------------------------------------
# Resume / skip-completed
# ---------------------------------------------------------------------------

# AERMOD reads each runstream record into a CHARACTER*ISTRG buffer (ISTRG
# = 512 in modules.f), so a longer line is cut there, echo included.
_RUNSTREAM_RECORD_LEN = 512
_PATHWAYS = ("CO", "SO", "RE", "ME", "OU", "**")


class _RunstreamEcho(NamedTuple):
    lines: Optional[List[str]]  # None after NO ECHO: AERMOD stops echoing
    included: List[str]         # files named on INCLUDED records


def _runstream_echo(deck_text: str) -> _RunstreamEcho:
    """The lines AERMOD echoes at the top of the ``.out`` for this deck.

    Mirrors ``SETUP`` in AERMOD's setup.f (v26135): every record up to
    and including ``OU FINISHED`` is written back with trailing blanks
    trimmed, a blank record as an empty line, and the ``OU FINISHED``
    record only up to column 10 + its start column, so a trailing
    comment on it is dropped. The pathway and keyword fields sit at
    fixed columns, set by where the first record starts (a shift of up
    to 3 columns is allowed), and a record with a blank pathway field
    continues the previous pathway.

    ``NO ECHO`` turns the echo off, so ``lines`` is then None. The
    records of an ``INCLUDED`` file are never echoed (``INCLUD`` reads
    them without writing them), so the echo shows only the
    ``INCLUDED`` record; ``included`` names those files.
    """
    lines = deck_text.splitlines()
    first = lines[0][:_RUNSTREAM_RECORD_LEN] if lines else ""
    start = next((i for i in range(4) if first[i:i + 1].strip(" ")), 0)
    echo: Optional[List[str]] = []
    included: List[str] = []
    previous_path = ""
    for line in lines:
        record = line[:_RUNSTREAM_RECORD_LEN]
        if not record.strip(" "):
            if echo is not None:
                echo.append("")
            continue
        upper = record.upper()
        field1 = upper[start:start + 2].strip(" ")
        field2 = upper[start + 3:start + 11].strip(" ")
        if echo is not None:
            if (field1, field2) == ("OU", "FINISHED"):
                echo.append(record[:start + 11].rstrip())
            else:
                echo.append(record.rstrip())
        if (field1, field2) == ("NO", "ECHO"):
            echo = None
            continue
        if field1 == "**":
            continue
        if field2 == "INCLUDED":
            rest = record[start + 11:].strip()
            name = rest[1:].split('"', 1)[0] if rest.startswith('"') else rest.split(" ", 1)[0]
            if name:
                included.append(name)
        path = field1 if field1 in _PATHWAYS else previous_path
        if path == "OU" and field2 == "FINISHED":
            break
        previous_path = path
    return _RunstreamEcho(echo, included)


def _out_echoes_deck(out_path: Path, echo: Sequence[str]) -> bool:
    """Whether ``out_path`` opens with exactly the runstream echo ``echo``."""
    with open(out_path, encoding="utf-8", errors="replace") as fh:
        for expected in echo:
            line = fh.readline()
            if not line or line.rstrip() != expected.rstrip():
                return False
    return True


def _output_is_valid(out_path: Path, input_path: Optional[Path] = None) -> bool:
    """Whether ``out_path`` records a finished, successful run of ``input_path``.

    The test is the runner's own (``AERMODRunner.run``): the final
    message summary ends with ``*** AERMOD Finishes Successfully ***``
    and lists no fatal error. Searching the end of the file for
    "FINISHES SUCCESSFULLY", as this check used to, also accepts
    ``*** SETUP Finishes Successfully ***``, which AERMOD prints before
    every run that gets past setup, including runs that fail or are
    killed afterwards.

    When ``input_path`` is given and exists, the ``.out`` must also come
    from this version of the deck. AERMOD copies the runstream to the
    top of the ``.out``, so the ``.out`` is current when that copy
    matches the deck's text, whatever the two files' modification times
    say: a deck written again with the same content still counts as
    done, and an edited deck does not. Two things the copy cannot show
    fall back to modification times, and an ``.out`` older than them is
    stale: a deck with ``NO ECHO``, after which AERMOD copies nothing,
    and the files a deck names on ``INCLUDED`` records (found relative
    to the deck's directory), whose records AERMOD never copies.
    """
    if not out_path.exists() or out_path.stat().st_size == 0:
        return False
    if input_path is not None and input_path.exists():
        try:
            echo = _runstream_echo(
                input_path.read_text(encoding="utf-8", errors="replace"))
            out_time = out_path.stat().st_mtime
            if echo.lines is None:
                if out_time < input_path.stat().st_mtime:
                    return False
            elif not _out_echoes_deck(out_path, echo.lines):
                return False
            for name in echo.included:
                inc = input_path.parent / name
                if inc.exists() and out_time < inc.stat().st_mtime:
                    return False
        except OSError:
            return False
    try:
        summary = _read_message_summary(out_path)
    except OSError:
        return False
    return (
        summary.finished_successfully
        and _severity_count(summary.messages, summary.counts, "E") == 0
    )


def resume_batch(
    input_files: Sequence[Union[str, Path]],
    output_dir: Union[str, Path],
) -> Dict[str, List[Path]]:
    """Partition `input_files` into 'done' and 'todo' lists.

    An input is 'done' when its ``<stem>.out`` in `output_dir` records a
    successful run by the rule ``AERMODRunner.run`` applies (AERMOD's
    ``*** AERMOD Finishes Successfully ***`` line and no fatal errors in
    its final message summary), and that ``.out`` came from the deck as
    it is now: the runstream AERMOD copies to the top of the ``.out``
    must match the deck's text. Everything else is 'todo': no ``.out``,
    a run that failed or was cut off (killed, timed out), and an
    ``.out`` from before the deck was edited.

    Because the check reads content, a script may write every deck again
    before it resumes: a deck rewritten with the same text stays 'done',
    whatever the file times say. File times decide only what the copy
    cannot show. A deck with ``NO ECHO`` is 'todo' when it is newer than
    its ``.out``, and so is a deck whose ``INCLUDED`` file (looked up
    relative to the deck's directory) is newer than its ``.out``. The
    met files and other inputs a deck names are not checked.
    """
    out_dir = Path(output_dir)
    done: List[Path] = []
    todo: List[Path] = []
    for inp in input_files:
        inp_path = Path(inp)
        out_path = out_dir / f"{inp_path.stem}.out"
        (done if _output_is_valid(out_path, inp_path) else todo).append(inp_path)
    return {"done": done, "todo": todo}


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

@dataclass
class RunManifestEntry:
    input_file: str
    status: str = "pending"  # pending / running / success / failed
    runtime_seconds: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class RunManifest:
    """Tracks a batch's per-run state in a JSON file.

    Use-cases:
    - Persist partial batch progress across restarts
    - Post-hoc inspection of which inputs succeeded / failed
    """
    path: Path
    entries: Dict[str, RunManifestEntry] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Union[str, Path]) -> RunManifest:
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(
            path=p,
            entries={k: RunManifestEntry(**v) for k, v in data.items()},
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({k: asdict(v) for k, v in self.entries.items()}, indent=2),
            encoding="utf-8",
        )

    def mark(self, input_file: str, status: str, **kw: Any) -> None:
        e = self.entries.get(input_file) or RunManifestEntry(input_file=input_file)
        e.status = status
        for k, v in kw.items():
            setattr(e, k, v)
        self.entries[input_file] = e
        self.save()

    def pending(self) -> List[str]:
        return [k for k, v in self.entries.items() if v.status in ("pending", "failed")]

    def summary(self) -> Dict[str, int]:
        s = {"pending": 0, "running": 0, "success": 0, "failed": 0}
        for v in self.entries.values():
            s[v.status] = s.get(v.status, 0) + 1
        return s


# ---------------------------------------------------------------------------
# SLURM job-array template
# ---------------------------------------------------------------------------

SLURM_TEMPLATE = """\
#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --output={log_dir}/%A_%a.out
#SBATCH --error={log_dir}/%A_%a.err
#SBATCH --array=0-{array_max}{throttle}
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}
#SBATCH --time={wallclock}
#SBATCH --partition={partition}

# Input files list (one per line)
INPUT_LIST={input_list}

INP=$(sed -n "$((SLURM_ARRAY_TASK_ID+1))p" "$INPUT_LIST")
if [ -z "$INP" ]; then
    echo "No input file at index $SLURM_ARRAY_TASK_ID"
    exit 1
fi

WORK=$(mktemp -d)
cp "$INP" "$WORK/aermod.inp"

cd "$WORK" && {aermod_exe}

BASE=$(basename "$INP" .inp)
cp aermod.out  "{output_dir}/${{BASE}}.out" 2>/dev/null || true
cp aermod.err  "{output_dir}/${{BASE}}.err" 2>/dev/null || true
cp aermod.sum  "{output_dir}/${{BASE}}.sum" 2>/dev/null || true
rm -rf "$WORK"
"""


def generate_slurm_script(
    input_files: Sequence[Union[str, Path]],
    output_dir: Union[str, Path],
    script_path: Union[str, Path],
    input_list_path: Union[str, Path],
    *,
    aermod_exe: str = "aermod",
    job_name: str = "pyaermod",
    log_dir: str = "logs",
    partition: str = "general",
    cpus: int = 1,
    mem: str = "4G",
    wallclock: str = "02:00:00",
    max_concurrent: Optional[int] = None,
) -> Path:
    """Write a SLURM job-array script + input-list file for a batch.

    Returns the path to the generated script.
    """
    inputs = [str(Path(p).absolute()) for p in input_files]
    n = len(inputs)
    if n == 0:
        raise ValueError("input_files is empty")

    input_list_path = Path(input_list_path).absolute()
    input_list_path.parent.mkdir(parents=True, exist_ok=True)
    input_list_path.write_text("\n".join(inputs) + "\n", encoding="utf-8")

    throttle = f"%{max_concurrent}" if max_concurrent else ""
    script = SLURM_TEMPLATE.format(
        job_name=job_name,
        log_dir=log_dir,
        array_max=n - 1,
        throttle=throttle,
        cpus=cpus,
        mem=mem,
        wallclock=wallclock,
        partition=partition,
        input_list=str(input_list_path),
        output_dir=str(Path(output_dir).absolute()),
        aermod_exe=aermod_exe,
    )
    script_path = Path(script_path).absolute()
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    os.chmod(script_path, 0o755)
    return script_path


__all__ = [
    "HAS_TQDM",
    "SLURM_TEMPLATE",
    "ERRMSGInfo",
    "LoggingProgress",
    "NoOpProgress",
    "ProgressReporter",
    "RunManifest",
    "RunManifestEntry",
    "TqdmProgress",
    "extract_errmsg",
    "generate_slurm_script",
    "resume_batch",
    "summarize_failure",
    "tail_output",
]
