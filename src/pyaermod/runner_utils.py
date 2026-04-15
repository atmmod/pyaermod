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
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Union

try:
    from tqdm import tqdm  # type: ignore
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


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
        if not HAS_TQDM:
            raise ImportError("tqdm is not installed; install with `pip install tqdm`")
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

def _output_is_valid(out_path: Path) -> bool:
    """Heuristic: treat an .OUT file as valid if it exists AND ends
    with the 'AERMOD Finishes Successfully' marker."""
    if not out_path.exists() or out_path.stat().st_size == 0:
        return False
    # Read the tail
    tail = tail_output(out_path, n_lines=50)
    joined = "\n".join(tail).upper()
    return "FINISHES SUCCESSFULLY" in joined or "RUN SUCCESSFULLY" in joined


def resume_batch(
    input_files: Sequence[Union[str, Path]],
    output_dir: Union[str, Path],
) -> Dict[str, List[Path]]:
    """Partition `input_files` into 'done' and 'todo' lists.

    An input is 'done' if a sibling `.out` in `output_dir` has the
    AERMOD success marker.
    """
    out_dir = Path(output_dir)
    done: List[Path] = []
    todo: List[Path] = []
    for inp in input_files:
        inp_path = Path(inp)
        out_path = out_dir / f"{inp_path.stem}.out"
        (done if _output_is_valid(out_path) else todo).append(inp_path)
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
    def load(cls, path: Union[str, Path]) -> "RunManifest":
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
    "ERRMSGInfo",
    "extract_errmsg",
    "tail_output",
    "summarize_failure",
    "ProgressReporter",
    "NoOpProgress",
    "LoggingProgress",
    "TqdmProgress",
    "HAS_TQDM",
    "resume_batch",
    "RunManifest",
    "RunManifestEntry",
    "SLURM_TEMPLATE",
    "generate_slurm_script",
]
