"""
PyAERMOD auxiliary output-file parsers.

AERMOD emits several text-format auxiliary files in addition to the
main `.OUT` log and the `POSTFILE` binary (handled by postfile.py):

- PLOTFILE     one value per receptor for a given averaging period
- MAXIFILE     ranked top-N values at every receptor
- RANKFILE     overall top-N values across receptors, with dates
- SEASONHR     seasonal-hourly-average grid (4 seasons * 24 hours)
- TOXXFILE     top-N concentrations for toxics post-processing
- deposition   DDEP / WDEP / TOTDEP (same layout as PLOTFILE)

All share a common structure: comment header lines starting with '*'
followed by whitespace-delimited numeric rows.  The readers here
return either a pandas DataFrame (preferred) or a list of dicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ._optional import optional_import, require

pd = optional_import("pandas")
HAS_PANDAS = pd is not None


# ---------------------------------------------------------------------------
# Common header parsing
# ---------------------------------------------------------------------------

@dataclass
class AERMODFileHeader:
    """Parsed comment-header info common to all AERMOD text outputs."""

    file_type: Optional[str] = None         # PLOTFILE / MAXIFILE / RANKFILE / SEASONHR / TOXXFILE / DDEP / WDEP / TOTDEP
    averaging_period: Optional[str] = None  # '1-HR', '24-HR', 'ANNUAL', etc.
    source_group: Optional[str] = None      # 'ALL', 'GRP1', ...
    rank: Optional[int] = None              # for MAXI/RANK files (HIGH-n)
    column_names: List[str] = field(default_factory=list)
    model_version: Optional[str] = None
    raw_lines: List[str] = field(default_factory=list)


_TYPE_RE = re.compile(
    r"\b(PLOT\s*FILE|PLOTFILE|MAXI\s*FILE|MAXIFILE|RANK\s*FILE|RANKFILE|"
    r"SEASONHR|TOXX\s*FILE|TOXXFILE|DDEP|WDEP|TOTDEP)\b",
    re.IGNORECASE,
)

# Map possibly-spaced variants to canonical single-word forms.
_TYPE_NORMALIZE = {
    "PLOT FILE": "PLOTFILE",
    "MAXI FILE": "MAXIFILE",
    "RANK FILE": "RANKFILE",
    "TOXX FILE": "TOXXFILE",
}

_AVG_RE = re.compile(
    r"(?:Averaging\s+Period|AVERAGE|\bOF\b)\s*[:\s]\s*"
    r"(ANNUAL|PERIOD|\d+\s*-?\s*HR|\d+-hr|\d+HR)",
    re.IGNORECASE,
)
_GRP_RE = re.compile(r"Source\s+Group:\s*(\S+)", re.IGNORECASE)
_RANK_RE = re.compile(r"(HIGH|H)[- ]?(\d+)(?:ST|ND|RD|TH)?", re.IGNORECASE)
_VER_RE = re.compile(r"AERMOD[^\d]*(\d{5}|\d{2}\d{3})")


def parse_aermod_header(lines: List[str]) -> AERMODFileHeader:
    """Parse the comment-header block of any AERMOD auxiliary file."""
    h = AERMODFileHeader(raw_lines=list(lines))
    for raw in lines:
        stripped = raw.lstrip("*").strip()
        if not stripped:
            continue
        if h.file_type is None:
            m = _TYPE_RE.search(stripped)
            if m:
                raw_type = re.sub(r"\s+", " ", m.group(1).upper())
                h.file_type = _TYPE_NORMALIZE.get(raw_type, raw_type)
        if h.averaging_period is None:
            m = _AVG_RE.search(stripped)
            if m:
                h.averaging_period = m.group(1).upper()
        if h.source_group is None:
            m = _GRP_RE.search(stripped)
            if m:
                h.source_group = m.group(1).upper()
        if h.rank is None:
            m = _RANK_RE.search(stripped)
            if m:
                try:
                    h.rank = int(m.group(2))
                except ValueError:
                    pass
        if h.model_version is None:
            m = _VER_RE.search(stripped)
            if m:
                h.model_version = m.group(1)
        # Column-name hint: many AERMOD outputs have a header line like
        # "*        X              Y       CONC        DATE"
        # Require at least TWO column-ish tokens to avoid picking up
        # "MODELING OPTIONS USED: ... CONC ..." lines that happen to
        # mention one of them. Take the *last* matching comment line so
        # column headers closer to the data rows win.
        tokens = set(stripped.split())
        column_hints = tokens & {"X", "Y", "CONC", "RANK", "DATE"}
        if len(column_hints) >= 2:
            h.column_names = [c.upper() for c in stripped.split()]
    return h


def _split_header_and_rows(text: str) -> Tuple[List[str], List[str]]:
    header: List[str] = []
    rows: List[str] = []
    for ln in text.splitlines():
        if ln.startswith("*") or not ln.strip():
            header.append(ln)
        else:
            rows.append(ln)
    return header, rows


def _rows_to_records(rows: List[str], column_names: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not rows:
        return out
    for raw in rows:
        toks = raw.split()
        if not toks:
            continue
        # Try numeric conversion for each column
        rec: Dict[str, Any] = {}
        for i, tok in enumerate(toks):
            key = column_names[i] if i < len(column_names) else f"COL{i + 1}"
            try:
                if "." in tok or "e" in tok.lower():
                    rec[key] = float(tok)
                else:
                    rec[key] = int(tok)
            except ValueError:
                rec[key] = tok
        out.append(rec)
    return out


def _infer_columns(n_tokens: int, file_type: Optional[str]) -> List[str]:
    """Guess column names from token count when header didn't name them."""
    ft = (file_type or "").upper()
    if ft in {"PLOTFILE", "DDEP", "WDEP", "TOTDEP"}:
        names = ["X", "Y", "CONC"]
    elif ft in {"MAXIFILE", "RANKFILE", "TOXXFILE"}:
        names = ["RANK", "X", "Y", "CONC", "DATE"]
    elif ft == "SEASONHR":
        # X, Y + 96 seasonal-hour slots
        slots = [f"{s}_{h:02d}" for s in ("WIN", "SPR", "SUM", "FAL") for h in range(1, 25)]
        names = ["X", "Y"] + slots
    else:
        names = [f"COL{i + 1}" for i in range(n_tokens)]
    # Pad or trim to match tokens
    while len(names) < n_tokens:
        names.append(f"COL{len(names) + 1}")
    return names[:n_tokens]


# ---------------------------------------------------------------------------
# Public readers
# ---------------------------------------------------------------------------

@dataclass
class AERMODAuxResult:
    """Unified result for any AERMOD auxiliary output file."""
    header: AERMODFileHeader
    records: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def n_records(self) -> int:
        return len(self.records)

    @property
    def column_names(self) -> List[str]:
        if self.records:
            return list(self.records[0].keys())
        return self.header.column_names

    def to_dataframe(self):
        require(pd, "pandas")
        return pd.DataFrame(self.records)


def read_aermod_aux_file(filepath: Union[str, Path]) -> AERMODAuxResult:
    """Read any AERMOD text auxiliary output file.

    Auto-detects the file type (PLOTFILE, MAXIFILE, RANKFILE, SEASONHR,
    TOXXFILE, DDEP, WDEP, TOTDEP) from the header comments and infers
    columns when the header doesn't label them.
    """
    path = Path(filepath)
    text = path.read_text(encoding="latin-1", errors="replace")
    header_lines, rows = _split_header_and_rows(text)
    header = parse_aermod_header(header_lines)
    col_names = header.column_names
    if not col_names and rows:
        col_names = _infer_columns(len(rows[0].split()), header.file_type)
        header.column_names = col_names
    records = _rows_to_records(rows, col_names)
    return AERMODAuxResult(header=header, records=records)


# Thin wrappers with clearer names. Each verifies the file type matches
# to catch accidentally-crossed file paths.

def _read_expecting(filepath: Union[str, Path], expected_types: Tuple[str, ...]) -> AERMODAuxResult:
    res = read_aermod_aux_file(filepath)
    ft = (res.header.file_type or "").upper()
    if ft and ft not in expected_types:
        raise ValueError(
            f"file {filepath} looks like {ft!r}, expected one of {expected_types}"
        )
    return res


def read_plotfile(filepath: Union[str, Path]) -> AERMODAuxResult:
    """Read a PLOTFILE (one concentration value per receptor)."""
    return _read_expecting(filepath, ("PLOTFILE",))


def read_maxifile(filepath: Union[str, Path]) -> AERMODAuxResult:
    """Read a MAXIFILE (top-N values at each receptor)."""
    return _read_expecting(filepath, ("MAXIFILE",))


def read_rankfile(filepath: Union[str, Path]) -> AERMODAuxResult:
    """Read a RANKFILE (overall top-N values across receptors)."""
    return _read_expecting(filepath, ("RANKFILE",))


def read_seasonhr(filepath: Union[str, Path]) -> AERMODAuxResult:
    """Read a SEASONHR file (seasonal-hourly averages)."""
    return _read_expecting(filepath, ("SEASONHR",))


def read_toxxfile(filepath: Union[str, Path]) -> AERMODAuxResult:
    """Read a TOXXFILE (toxics post-processing top-N)."""
    return _read_expecting(filepath, ("TOXXFILE",))


def read_deposition(filepath: Union[str, Path]) -> AERMODAuxResult:
    """Read a deposition output file (DDEP, WDEP, or TOTDEP)."""
    return _read_expecting(filepath, ("DDEP", "WDEP", "TOTDEP"))


__all__ = [
    "AERMODFileHeader",
    "AERMODAuxResult",
    "parse_aermod_header",
    "read_aermod_aux_file",
    "read_plotfile",
    "read_maxifile",
    "read_rankfile",
    "read_seasonhr",
    "read_toxxfile",
    "read_deposition",
]
