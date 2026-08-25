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
followed by fixed-width numeric rows.  AERMOD prints the Fortran
FORMAT statement it used in the header (``* FORMAT: (3(1X,F13.5),...)``);
when that line is present the rows are sliced by those field widths,
which is the only way to read a record whose trailing NET ID column is
blank (discrete receptors) without shifting every column after it.
Files without a FORMAT line fall back to whitespace splitting.

The readers here return either a pandas DataFrame (preferred) or a
list of dicts.
"""

from __future__ import annotations

import contextlib
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
    record_format: Optional[str] = None     # Fortran FORMAT printed by AERMOD
    field_widths: List[int] = field(default_factory=list)  # data-field widths
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

# "MODELING OPTIONS USED: NonDFAULT CONC DDEP WDEP ..." -- an options
# list, never a file-type declaration.
_OPTIONS_RE = re.compile(r"MODEL\w*\s+OPTIONS", re.IGNORECASE)
# "PLOT FILE OF HIGH 1ST HIGH 1-HR VALUES FOR SOURCE GROUP: ALL"
_FILE_OF_RE = re.compile(r"FILE\s+OF\b", re.IGNORECASE)

_AVG_RE = re.compile(
    r"(?:Averaging\s+Period|AVERAGE|\bOF\b)\s*[:\s]\s*"
    r"(ANNUAL|PERIOD|\d+\s*-?\s*HR|\d+-hr|\d+HR)",
    re.IGNORECASE,
)
_GRP_RE = re.compile(r"Source\s+Group:\s*(\S+)", re.IGNORECASE)
_RANK_RE = re.compile(r"(HIGH|H)[- ]?(\d+)(?:ST|ND|RD|TH)?", re.IGNORECASE)
_VER_RE = re.compile(r"AERMOD[^\d]*(\d{5}|\d{2}\d{3})")


_FORMAT_RE = re.compile(r"FORMAT:\s*(\(.*)$", re.IGNORECASE)

# One edit descriptor: optional repeat count, letter code, width, decimals.
_EDIT_RE = re.compile(
    r"(?P<rep>\d+)?(?P<code>[IFEDGALX])(?P<w>\d+)?(?:\.(?P<d>\d+))?",
    re.IGNORECASE,
)


def parse_fortran_format(spec: str) -> List[Tuple[str, int]]:
    """Expand a Fortran FORMAT statement into a flat list of ``(kind, width)``.

    ``kind`` is ``"skip"`` for ``nX`` positional descriptors and ``"data"``
    for value-carrying descriptors (I/F/E/D/G/A/L). Group repeats
    (``3(1X,F13.5)``) and the colon terminator are handled; everything
    else -- string literals, ``T``/``P`` edit descriptors -- is not used
    by AERMOD's auxiliary-file writers and raises ``ValueError``.

    AERMOD prints the exact FORMAT it wrote each file with, so these
    widths are authoritative: they are what makes a blank trailing
    column (an unset NET ID on discrete receptors) parse as blank
    rather than shifting every later column left by one.
    """
    text = spec.strip()
    if not text.startswith("("):
        raise ValueError(f"not a Fortran FORMAT statement: {spec!r}")

    # Trim anything after the FORMAT's own closing paren (AERMOD pads the
    # header line with trailing blanks).
    depth = 0
    end = None
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise ValueError(f"unbalanced parentheses in FORMAT: {spec!r}")
    body = text[1:end]

    def _expand(src: str) -> List[Tuple[str, int]]:
        out: List[Tuple[str, int]] = []
        i = 0
        n = len(src)
        while i < n:
            ch = src[i]
            if ch in ", :":
                i += 1
                continue
            # Repeat count, possibly introducing a nested group.
            j = i
            while j < n and src[j].isdigit():
                j += 1
            rep_text, rest_at = src[i:j], j
            if rest_at < n and src[rest_at] == "(":
                depth2 = 0
                k = rest_at
                while k < n:
                    if src[k] == "(":
                        depth2 += 1
                    elif src[k] == ")":
                        depth2 -= 1
                        if depth2 == 0:
                            break
                    k += 1
                if depth2 != 0:
                    raise ValueError(f"unbalanced group in FORMAT: {spec!r}")
                inner = _expand(src[rest_at + 1:k])
                out.extend(inner * int(rep_text or 1))
                i = k + 1
                continue
            m = _EDIT_RE.match(src, i)
            if not m or m.end() == i:
                raise ValueError(
                    f"unsupported edit descriptor at {src[i:i + 8]!r} in {spec!r}"
                )
            rep = int(m.group("rep") or 1)
            code = m.group("code").upper()
            width = int(m.group("w") or 1)
            out.extend([("skip" if code == "X" else "data", width)] * rep)
            i = m.end()
        return out

    return _expand(body)


def _format_field_slices(spec: str) -> List[Tuple[int, int]]:
    """``(start, stop)`` column offsets of the data fields in ``spec``."""
    slices: List[Tuple[int, int]] = []
    pos = 0
    for kind, width in parse_fortran_format(spec):
        if kind == "data":
            slices.append((pos, pos + width))
        pos += width
    return slices


def _split_column_labels(line: str) -> List[str]:
    """Split an AERMOD column-header line into labels.

    AERMOD separates columns by two or more spaces and uses single
    spaces *inside* a label (``AVERAGE CONC``, ``NET ID``). Splitting on
    any whitespace therefore invents extra columns and shifts every
    label after the first multi-word one.
    """
    return [
        re.sub(r"\s+", "_", part.strip()).upper()
        for part in re.split(r"\s{2,}", line.strip())
        if part.strip()
    ]


def parse_aermod_header(lines: List[str]) -> AERMODFileHeader:
    """Parse the comment-header block of any AERMOD auxiliary file."""
    h = AERMODFileHeader(raw_lines=list(lines))
    fallback_type: Optional[str] = None
    for raw in lines:
        stripped = raw.lstrip("*").strip()
        if not stripped:
            continue
        if h.file_type is None and not _OPTIONS_RE.search(stripped):
            # The "MODELING OPTIONS USED: ... CONC DDEP WDEP ..." line names
            # deposition options, not a file type; a deposition run's
            # PLOTFILE would otherwise be read as a DDEP file. Only the
            # line that declares "<kind> FILE OF ..." is authoritative;
            # anything else is a fallback for headers that lack one.
            m = _TYPE_RE.search(stripped)
            if m:
                raw_type = re.sub(r"\s+", " ", m.group(1).upper())
                found = _TYPE_NORMALIZE.get(raw_type, raw_type)
                if _FILE_OF_RE.search(stripped):
                    h.file_type = found
                elif fallback_type is None:
                    fallback_type = found
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
                with contextlib.suppress(ValueError):
                    h.rank = int(m.group(2))
        if h.model_version is None:
            m = _VER_RE.search(stripped)
            if m:
                h.model_version = m.group(1)
        if h.record_format is None:
            m = _FORMAT_RE.search(stripped)
            if m:
                with contextlib.suppress(ValueError):
                    widths = _format_field_slices(m.group(1))
                    h.record_format = m.group(1).strip()
                    h.field_widths = [stop - start for start, stop in widths]
        # Column-name hint: many AERMOD outputs have a header line like
        # "*        X              Y       CONC        DATE"
        # Require at least TWO column-ish tokens to avoid picking up
        # "MODELING OPTIONS USED: ... CONC ..." lines that happen to
        # mention one of them. Take the *last* matching comment line so
        # column headers closer to the data rows win.
        labels = _split_column_labels(stripped)
        column_hints = {lbl.split("_")[0] for lbl in labels} & {
            "X", "Y", "CONC", "AVERAGE", "RANK", "DATE",
        }
        if len(column_hints) >= 2:
            h.column_names = labels
    if h.file_type is None:
        h.file_type = fallback_type
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


def _coerce(tok: str) -> Any:
    try:
        if "." in tok or "e" in tok.lower():
            return float(tok)
        return int(tok)
    except ValueError:
        return tok


def _split_row(raw: str, slices: Optional[List[Tuple[int, int]]]) -> List[str]:
    """Split one data row into field strings.

    With the file's own Fortran FORMAT (``slices``) the row is cut at
    fixed offsets, so a blank field stays blank instead of vanishing and
    pulling every later column one place to the left. Rows shorter than
    the format (AERMOD right-trims trailing blanks) keep only the fields
    that are actually present.
    """
    if not slices:
        return raw.split()
    fields = [raw[start:stop].strip() for start, stop in slices]
    while fields and fields[-1] == "":
        fields.pop()
    return fields


def _rows_to_records(
    rows: List[str],
    column_names: List[str],
    slices: Optional[List[Tuple[int, int]]] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not rows:
        return out
    for raw in rows:
        toks = _split_row(raw, slices)
        if not toks:
            continue
        # Try numeric conversion for each column
        rec: Dict[str, Any] = {}
        for i, tok in enumerate(toks):
            key = column_names[i] if i < len(column_names) else f"COL{i + 1}"
            rec[key] = _coerce(tok) if tok else ""
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
        names = ["X", "Y", *slots]
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

    @property
    def concentration_column(self) -> Optional[str]:
        """Name of the column holding the concentration, if identifiable.

        AERMOD labels it ``AVERAGE CONC`` in most files (parsed here as
        ``AVERAGE_CONC``) and plain ``CONC`` in others, so callers should
        ask rather than guess a spelling.
        """
        names = self.column_names
        for candidate in ("CONC", "AVERAGE_CONC", "AVERAGE", "VALUE"):
            if candidate in names:
                return candidate
        return next(
            (n for n in names if n.startswith("AVERAGE") or "CONC" in n), None
        )

    def values(self, column: Optional[str] = None) -> List[float]:
        """Numeric values of ``column`` (default: the concentration)."""
        col = column or self.concentration_column
        if col is None:
            return []
        return [
            float(r[col]) for r in self.records
            if isinstance(r.get(col), (int, float))
        ]

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
    slices = (
        _format_field_slices(header.record_format) if header.record_format else None
    )
    col_names = header.column_names
    if not col_names and rows:
        col_names = _infer_columns(
            len(_split_row(rows[0], slices)), header.file_type
        )
        header.column_names = col_names
    records = _rows_to_records(rows, col_names, slices)
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
    "AERMODAuxResult",
    "AERMODFileHeader",
    "parse_aermod_header",
    "parse_fortran_format",
    "read_aermod_aux_file",
    "read_deposition",
    "read_maxifile",
    "read_plotfile",
    "read_rankfile",
    "read_seasonhr",
    "read_toxxfile",
]
