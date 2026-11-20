"""
PyAERMOD POSTFILE Parser

Parses AERMOD POSTFILE output files containing concentration grids
for each averaging period and source group.

Supports both formatted (PLOT) and unformatted (UNFORM/binary) POSTFILE output.

AERMOD formatted POSTFILE (PLOT):
    - Header lines start with '*' and contain metadata such as AERMOD version,
      AVERTIME, POLLUTID, and SRCGROUP.
    - Data lines contain columns: X, Y, one value per output type, ZELEV,
      ZHILL, ZFLAG, AVE, GRP, DATE (YYMMDDHH), NET ID.
    - Concentrations may use scientific notation (e.g. 1.23456E+01).

AERMOD unformatted POSTFILE (UNFORM):
    - Fortran unformatted sequential records.
    - Each record contains: KURDAT (int32), IANHRS (int32), GRPID (char*8),
      then one block of num_receptors float64 values per output type.
    - IANHRS is the hours in a short-term record's averaging period, the
      number of hours in the run for a PERIOD record and the number of
      years (NUMYRS) for an ANNUAL one, so it does not always say which
      kind of record it is (see :class:`UnformattedPostfileParser`).
    - Receptor coordinates are NOT stored in the binary file; they must be
      supplied externally or default to index-based values.

Output types. A run writes one value per receptor for each output type on
its MODELOPT line (CONC, DEPOS, DDEP, WDEP; NUMTYP of them). AERMOD always
orders them CONC, DEPOS, DDEP, WDEP, whatever the keyword order on MODELOPT
(``MODOPT`` in coset.f), and writes them in that order in every POSTFILE
and PLOTFILE row (``POSTFL`` in calc2.f, ``PSTANN`` and ``PLOTFL`` in
output.f). A text file names them in its column-label header line
(``AVERAGE CONC``, ``TOTAL DEPO``, ``DRY DEPO``, ``WET DEPO``); a binary
file does not, so a binary file from a run with more than one output type
needs the types from the caller.

Based on AERMOD version 26135 POSTFILE specifications (validated against 26135
and 24142; see :mod:`pyaermod.versions`).
"""

import re
import struct
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

import pandas as pd

from ._fortran import fortran_float
from .pathways import SHORT_TERM_HOURS

#: AERMOD's output types, in the order AERMOD writes them.
OUTPUT_TYPES: Tuple[str, ...] = ("CONC", "DEPOS", "DDEP", "WDEP")

# DataFrame column for each output type when a file holds more than one.
# A file with one output type keeps its values in ``concentration``,
# whatever the type (see PostfileResult.column_for).
_TYPE_COLUMNS = {
    "CONC": "concentration",
    "DEPOS": "total_depo",
    "DDEP": "dry_depo",
    "WDEP": "wet_depo",
}

# Column labels AERMOD writes for each output type (CHIDEP(1:3,ITYP) in
# coset.f), as they appear in the column-label header line.
_LABEL_PATTERN = re.compile(r"AVERAGE\s+CONC|TOTAL\s+DEPO|DRY\s+DEPO|WET\s+DEPO")
_LABEL_TYPES = {
    "AVERAGE CONC": "CONC",
    "TOTAL DEPO": "DEPOS",
    "DRY DEPO": "DDEP",
    "WET DEPO": "WDEP",
}

# Header lines that read "<KEY>: value", and the PostfileHeader field of each.
_HEADER_FIELDS = tuple(
    (re.compile(key + r":\s*(.*)", re.IGNORECASE), name)
    for key, name in (
        (r"MODELING\s+OPTIONS\s+USED", "model_options"),
        ("AVERTIME", "averaging_period"),
        ("POLLUTID", "pollutant_id"),
        ("SRCGROUP", "source_group"),
    )
)

OutputTypesArg = Union[str, Iterable[str], None]

#: KAVE for a MONTH average (``AVETIM`` in coset.f), which a binary record
#: holds where a short-term one holds its hours.
_MONTH_HOURS = 720

#: NUMYRS counts years of met data, so an ANNUAL record's count is small;
#: a count from here up can only be the hours of a PERIOD run.
_PERIOD_ONLY_HOURS = 100


def label_hours(label: str) -> Optional[int]:
    """N of a POSTFILE ``AVE`` label ``"N-HR"`` (upper case, any N), else *None*.

    The one reader of the label: whether N is an averaging period AERMOD
    has (:data:`SHORT_TERM_HOURS`) is the caller's to judge.
    """
    match = re.fullmatch(r"(\d+)-HR", label, re.ASCII)
    return int(match.group(1)) if match else None


def _normalize_averaging_period(period: Union[str, int, None]) -> Optional[str]:
    """
    Return *period* as AERMOD's AVE column writes it, or *None*.

    Accepts an AVERTIME keyword (``"1"``, ``"24"``, ``"MONTH"``,
    ``"PERIOD"``, ``"ANNUAL"``), its POSTFILE label (``"1-HR"``) or a
    number of hours, in any case; returns ``"1-HR"`` ... ``"24-HR"``,
    ``"MONTH"``, ``"PERIOD"`` or ``"ANNUAL"``.
    """
    if period is None:
        return None
    text = "" if isinstance(period, bool) else str(period).strip().upper()
    if text in ("MONTH", "PERIOD", "ANNUAL"):
        return text
    hours = int(text) if text.isascii() and text.isdigit() else label_hours(text)
    if hours in SHORT_TERM_HOURS:
        return f"{hours}-HR"
    raise ValueError(
        f"averaging_period={period!r} is not an averaging period AERMOD "
        "writes: 1, 2, 3, 4, 6, 8, 12 or 24 (hours, or '1-HR' ... '24-HR'), "
        "'MONTH', 'PERIOD' or 'ANNUAL'"
    )


def _normalize_output_types(output_types: OutputTypesArg) -> Optional[Tuple[str, ...]]:
    """
    Return *output_types* as a tuple in AERMOD's order, or *None*.

    A string is read like a MODELOPT line: its words that are output types
    are kept and every other word (``DFAULT``, ``FLAT`` ...) is ignored, and
    a line with none of them means CONC, as AERMOD assumes (warning W205).
    Any other iterable must hold only output-type names.
    """
    if output_types is None:
        return None
    if isinstance(output_types, str):
        words = {w.upper() for w in output_types.split()}
        found = tuple(t for t in OUTPUT_TYPES if t in words)
        return found or ("CONC",)
    names = [str(t).strip().upper() for t in output_types]
    unknown = [n for n in names if n not in OUTPUT_TYPES]
    if unknown:
        raise ValueError(
            f"Unknown output type(s) {unknown}; expected some of {list(OUTPUT_TYPES)}"
        )
    if not names:
        raise ValueError("output_types is empty")
    return tuple(t for t in OUTPUT_TYPES if t in names)


HOURLY_MEAN_LIMITATION = (
    "an hourly POSTFILE has a row for every hour but no calm or missing flag, so "
    "a 24-hour or PERIOD/ANNUAL mean computed from it divides by the number of "
    "rows; AERMOD divides by the hours that were neither calm nor missing (with "
    "a 75% floor for a short-term average), so the two differ for any period "
    "with calm or missing hours. For AERMOD's own value, have AERMOD write it "
    "(POSTFILE 24 or PERIOD, or the summary tables)."
)


def warn_hourly_mean_limitation(what: str, stacklevel: int = 3) -> None:
    """Warn that ``what`` is a mean computed from an hourly POSTFILE.

    For the functions that average hourly POSTFILE rows (24-hour,
    PERIOD or ANNUAL means): the file cannot say which hours were calm or
    missing (``HOURLY_MEAN_LIMITATION``), so the mean can differ from the
    one AERMOD prints. No number is changed. ``stacklevel`` counts from
    the function that calls this one (3 names that function's caller).
    """
    warnings.warn(f"{what}: {HOURLY_MEAN_LIMITATION}", UserWarning, stacklevel=stacklevel)


def _number_or_nan(token: str, parser: "PostfileParser") -> float:
    """``token`` as a float; an overflowed field (``*****``) as NaN.

    Fortran prints a field of asterisks when the value does not fit its
    width (F13.5 holds up to 9,999,999.99999). The row is kept with NaN
    in that field, and the parser warns once, rather than dropping it.
    """
    if token and set(token) == {"*"}:
        parser._overflowed += 1
        return float("nan")
    return fortran_float(token)


def _value_columns(output_types: Optional[Tuple[str, ...]], numtyp: int = 1) -> List[str]:
    """DataFrame columns for the per-type values of a row."""
    if numtyp == 1:
        return ["concentration"]
    assert output_types is not None and len(output_types) == numtyp
    return [_TYPE_COLUMNS[t] for t in output_types]


@dataclass
class PostfileHeader:
    """
    Metadata parsed from POSTFILE header lines.

    Each field corresponds to a '*'-prefixed header line in the POSTFILE.
    ``output_types`` is the file's output types in AERMOD's order (for
    example ``("CONC", "DDEP")``), read from the column labels of a text
    file or given by the caller for a binary one; it is *None* when
    neither says.
    """
    version: Optional[str] = None
    title: Optional[str] = None
    model_options: Optional[str] = None
    averaging_period: Optional[str] = None
    pollutant_id: Optional[str] = None
    source_group: Optional[str] = None
    output_types: Optional[Tuple[str, ...]] = None


@dataclass
class PostfileResult:
    """
    Parsed data for a single POSTFILE (one source group / averaging period).

    Attributes
    ----------
    header : PostfileHeader
        Metadata extracted from the file header.
    data : pd.DataFrame
        One row per receptor and time step, with columns x, y, the values,
        zelev, zhill, zflag, ave, grp, date (plus rank in a PLOTFILE of
        high values). A file with one output type holds its values in
        ``concentration``, whatever the type. A file with several holds
        one column per type: ``concentration`` (CONC), ``total_depo``
        (DEPOS), ``dry_depo`` (DDEP) and ``wet_depo`` (WDEP).
        :meth:`column_for` names the column of a given type.
    """
    header: PostfileHeader
    data: pd.DataFrame

    # Limitation: an hourly POSTFILE carries no calm/missing flag, so a mean
    # of its rows (24-hour, PERIOD, ANNUAL) can differ from AERMOD's own;
    # see HOURLY_MEAN_LIMITATION.

    @property
    def output_types(self) -> Optional[Tuple[str, ...]]:
        """The file's output types in AERMOD's order, or *None* if unknown."""
        return self.header.output_types

    def column_for(self, output_type: str) -> str:
        """
        Return the name of the column that holds *output_type*.

        Parameters
        ----------
        output_type : str
            ``"CONC"``, ``"DEPOS"``, ``"DDEP"`` or ``"WDEP"``.

        Raises
        ------
        KeyError
            If the file does not hold that output type.
        """
        wanted = str(output_type).strip().upper()
        if wanted not in OUTPUT_TYPES:
            raise ValueError(
                f"Unknown output type {output_type!r}; expected one of {list(OUTPUT_TYPES)}"
            )
        types = self.output_types
        if types is not None:
            if wanted not in types:
                raise KeyError(f"{wanted} is not in this file, which holds {list(types)}")
            return _value_columns(types, len(types))[types.index(wanted)]
        column = _TYPE_COLUMNS[wanted]
        if column in self.data.columns:
            return column
        raise KeyError(f"No column for {wanted}; the file does not name its output types")

    @property
    def _primary_column(self) -> str:
        """Column of the file's first output type (``concentration`` if present)."""
        if "concentration" in self.data.columns or not self.output_types:
            return "concentration"
        return self.column_for(self.output_types[0])

    @property
    def max_concentration(self) -> float:
        """
        Return the maximum value of the file's first output type.

        That is the concentration whenever the file holds CONC; for a file
        without CONC it is the first of its deposition types.
        """
        if self.data.empty:
            return 0.0
        return float(self.data[self._primary_column].max())

    @property
    def max_location(self) -> Tuple[float, float]:
        """Return (x, y) coordinates of the maximum of the first output type."""
        if self.data.empty:
            return (0.0, 0.0)
        idx = self.data[self._primary_column].idxmax()
        return (float(self.data.loc[idx, "x"]),
                float(self.data.loc[idx, "y"]))

    def get_timestep(self, date: str) -> pd.DataFrame:
        """
        Get all data rows for a specific date/time.

        Parameters
        ----------
        date : str
            Date string in YYMMDDHH format (e.g. '26010101').

        Returns
        -------
        pd.DataFrame
            Subset of data matching the requested date.
        """
        return self.data[self.data["date"] == date].copy()

    @property
    def flagpole_heights(self) -> List[float]:
        """The distinct flagpole heights (``zflag``) in the file, ascending."""
        if self.data.empty or "zflag" not in self.data.columns:
            return []
        return [float(z) for z in sorted(self.data["zflag"].dropna().unique())]

    def get_receptor(
        self,
        x: float,
        y: float,
        tolerance: float = 1.0,
        zflag: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Get all data rows for a specific receptor location.

        A flagpole run (``CO FLAGPOLE`` with one network per height) has
        several receptors at the same (x, y), one per ``zflag``. Pass
        ``zflag`` to pick one height.

        Parameters
        ----------
        x : float
            X coordinate of the receptor.
        y : float
            Y coordinate of the receptor.
        tolerance : float
            Distance tolerance for matching receptor coordinates, and for
            matching ``zflag`` when it is given.
        zflag : float, optional
            Flagpole height of the receptor. When it is *None* and the rows
            found span several heights, all of them are returned, as before,
            with a :class:`UserWarning` naming the heights.

        Returns
        -------
        pd.DataFrame
            Subset of data within *tolerance* of the requested location.
        """
        mask = (
            (self.data["x"] - x).abs() <= tolerance
        ) & (
            (self.data["y"] - y).abs() <= tolerance
        )
        if zflag is not None and "zflag" in self.data.columns:
            mask &= (self.data["zflag"] - zflag).abs() <= tolerance
        found = self.data[mask].copy()
        if zflag is None and "zflag" in found.columns:
            heights = sorted(found["zflag"].dropna().unique())
            if len(heights) > 1:
                warnings.warn(
                    f"the receptor at ({x}, {y}) has rows at several flagpole "
                    f"heights ({', '.join(str(float(z)) for z in heights)}); "
                    "pass zflag= to choose one",
                    UserWarning, stacklevel=2)
        return found

    def get_max_by_receptor(self) -> pd.DataFrame:
        """
        Get the maximum of the first output type at each receptor.

        A receptor is an (x, y) location, or an (x, y, zflag) location when
        the file holds more than one flagpole height (``CO FLAGPOLE`` with a
        network per height): receptors at the same (x, y) but different
        heights stay separate rows.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns x, y and the first output type's column
            (``concentration`` whenever the file holds CONC). With several
            flagpole heights it also has ``zflag``, ``zelev`` and ``zhill``.
        """
        column = self._primary_column
        if self.data.empty:
            return pd.DataFrame(columns=["x", "y", column])
        if len(self.flagpole_heights) > 1:
            keys = ["x", "y", "zflag"]
            extra = {c: "first" for c in ("zelev", "zhill") if c in self.data.columns}
            return (
                self.data.groupby(keys, dropna=False)
                .agg({**extra, column: "max"})
                .reset_index()
                [keys + list(extra) + [column]]
            )
        return (
            self.data.groupby(["x", "y"])[column]
            .max()
            .reset_index()
        )

    def to_dataframe(self) -> pd.DataFrame:
        """
        Return a copy of the full data DataFrame.

        Returns
        -------
        pd.DataFrame
            Copy of the concentration data.
        """
        return self.data.copy()


class PostfileParser:
    """
    Parser for AERMOD POSTFILE output files.

    Also reads AERMOD's text PLOTFILEs, whose rows have the same layout
    plus a RANK column.

    Parameters
    ----------
    filepath : str or Path
        Path to the POSTFILE to parse.
    output_types : str or iterable of str, optional
        The run's output types, as a MODELOPT line (``"CONC DDEP FLAT"``)
        or as names (``["CONC", "DDEP"]``). Needed only for a file whose
        header does not name its columns, such as one written with
        ``OU NOHEADER`` that has two or three value columns; when the
        header does, the header is used and a different *output_types*
        raises ``ValueError``.

    Raises
    ------
    FileNotFoundError
        If the specified file does not exist.
    """

    def __init__(
        self,
        filepath: Union[str, Path],
        output_types: OutputTypesArg = None,
    ):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"POSTFILE not found: {self.filepath}"
            )
        self._requested_types = _normalize_output_types(output_types)
        # Format flags set during header parsing
        self._is_deposition = False
        self._is_plotfile = False
        # What the header says about the output types
        self._label_types: Optional[Tuple[str, ...]] = None
        self._format_numtyp: Optional[int] = None
        # Row layout, fixed once the header has been read
        self._value_cols: Optional[List[str]] = None
        self._saw_header = False
        # Rows with an overflowed (all-asterisk) field, and the number of
        # years of a "MAX DAILY ... AVERAGED OVER n YEARS" PLOTFILE
        self._overflowed = 0
        self._years: Optional[int] = None

    def parse(self) -> PostfileResult:
        """
        Read and parse the POSTFILE.

        Returns
        -------
        PostfileResult
            Parsed header metadata and concentration data.

        Raises
        ------
        ValueError
            If the header, or the rows of a file without one, disagree
            with the caller's *output_types*, or if the file has two or
            three value columns and neither the header nor the caller says
            which output types they are.
        """
        header = PostfileHeader()
        data_rows = []

        with open(self.filepath, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("*"):
                    self._saw_header = True
                    self._parse_header_line(line, header)
                    continue
                if self._value_cols is None:
                    if not self._saw_header and line.strip():
                        self._infer_headerless_layout(line)
                    self._resolve_layout(header)
                row = self._parse_data_line(line)
                if row is not None:
                    data_rows.append(row)

        if self._value_cols is None:
            self._resolve_layout(header)
        assert self._value_cols is not None

        if self._overflowed:
            warnings.warn(
                f"{self.filepath.name}: {self._overflowed} numeric field(s) were "
                "printed as asterisks (the value did not fit its field); those "
                "values are NaN",
                stacklevel=2,
            )

        if data_rows:
            df = pd.DataFrame(data_rows)
        else:
            # Build default columns based on detected format
            cols = ["x", "y", *self._value_cols]
            cols.extend(["zelev", "zhill", "zflag", "ave", "grp"])
            if self._is_plotfile:
                cols.append("rank")
            cols.append("date")
            for year in range(1, (self._years or 0) + 1):
                cols += [f"yr{year}_value", f"yr{year}_date"]
            df = pd.DataFrame(columns=cols)

        return PostfileResult(header=header, data=df)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _header_types(self, header: PostfileHeader) -> Optional[Tuple[str, ...]]:
        """
        Output types the header states, or *None*.

        The column labels decide. Without them, the MODELING OPTIONS line
        is used when it agrees with the number of value columns in the
        FORMAT line (or when there is no FORMAT line).
        """
        if self._label_types is not None:
            return self._label_types
        if header.model_options is None:
            return None
        words = set(header.model_options.upper().split())
        options = tuple(t for t in OUTPUT_TYPES if t in words)
        if not options:
            return None
        if self._format_numtyp is None or self._format_numtyp == len(options):
            return options
        return None

    def _infer_headerless_layout(self, line: str) -> None:
        """
        Read the number of value columns, and whether the file is a
        PLOTFILE of high values, from the first row of a file written
        without a header (``OU NOHEADER``).

        X, Y, the values, ZELEV, ZHILL and ZFLAG are numbers; AVE
        (``1-HR``, ``PERIOD`` ...) is the first field that is not, so it
        sits at index 5 + NUMTYP. A PLOTFILE of highs has the rank
        (``1ST``, ``2ND`` ...) after GRP where a POSTFILE has the date.
        """
        parts = line.split()
        for idx in range(2, len(parts)):
            try:
                fortran_float(parts[idx])
            except ValueError:
                break
        else:
            return
        numtyp = idx - 5
        if numtyp < 1:
            return
        self._format_numtyp = numtyp
        if len(parts) > idx + 2 and re.fullmatch(r"\d+(ST|ND|RD|TH)", parts[idx + 2]):
            self._is_plotfile = True

    def _resolve_layout(self, header: PostfileHeader) -> None:
        """Fix the output types and the value columns of every data row."""
        types = self._header_types(header)
        requested = self._requested_types
        if types is not None and requested is not None and types != requested:
            raise ValueError(
                f"{self.filepath.name}: the header names output types "
                f"{list(types)} but output_types={list(requested)} was given"
            )
        where = "the FORMAT line has" if self._saw_header else "the rows (no header) have"
        numtyp = self._format_numtyp
        if types is None:
            types = requested
            if types is not None and numtyp is not None and len(types) != numtyp:
                raise ValueError(
                    f"{self.filepath.name}: output_types={list(types)} names "
                    f"{len(types)} output types but {where} {numtyp} value columns"
                )
        if types is None and numtyp is not None:
            # A column count but nothing naming the types: the count alone
            # identifies one type (kept in ``concentration``) or all four.
            # Two or three columns could be several sets of types.
            if numtyp == 4:
                types = OUTPUT_TYPES
            elif numtyp in (2, 3):
                raise ValueError(
                    f"{self.filepath.name}: {where} {numtyp} value columns "
                    "but nothing says which output types they are; pass "
                    "output_types (the run's MODELOPT line)"
                )
        header.output_types = types
        numtyp = len(types) if types is not None else 1
        self._value_cols = _value_columns(types, numtyp)
        self._is_deposition = numtyp > 1

    def _parse_header_line(self, line: str, header: PostfileHeader) -> None:
        """
        Extract metadata from a single header line.

        Recognized patterns (case-insensitive):
            * AERMOD ( <version> )   -> header.version, header.title
            * MODELING OPTIONS USED: -> header.model_options
            * AVERTIME:              -> header.averaging_period
            * POLLUTID:              -> header.pollutant_id
            * SRCGROUP:              -> header.source_group

        EPA format patterns (also recognized):
            * POST/PLOT FILE OF CONCURRENT <period> VALUES FOR SOURCE GROUP: <grp>
            * PLOT FILE OF  HIGH <rank> <period> VALUES FOR SOURCE GROUP: <grp>
            * FORMAT: (6(1X,F13.5)...  -> number of value columns
            * X  Y  AVERAGE CONC  DRY DEPO ... -> the output types

        Parameters
        ----------
        line : str
            A header line (starts with '*').
        header : PostfileHeader
            Header object to populate.
        """
        # Strip the leading '*' and whitespace
        text = line.lstrip("*").strip()

        # AERMOD version and title
        version_match = re.match(
            r"AERMOD\s*\(\s*(\S+)\s*\)\s*:\s*(.*)", text, re.IGNORECASE
        )
        if version_match:
            header.version = version_match.group(1)
            title = version_match.group(2).strip()
            if title:
                header.title = title
            return

        # "<KEY>: value" lines: the model options, and the averaging period,
        # pollutant and source group of the pyaermod synthetic format
        for pattern, name in _HEADER_FIELDS:
            field_match = pattern.match(text)
            if field_match:
                setattr(header, name, field_match.group(1).strip())
                return

        # EPA format: POST/PLOT FILE OF CONCURRENT <period> VALUES
        # Also: PLOT FILE OF  HIGH <rank> <period> VALUES
        epa_pst_match = re.match(
            r"(?:POST/?PLOT|POST|PLOT)\s+FILE\s+OF\s+.*?"
            r"\b(\d+-HR|PERIOD|ANNUAL|MONTH)\b\s+VALUES"
            r"(?:\s+AVERAGED\s+OVER\s+(\d+)\s+YEARS)?"
            r"(?:\s+FOR\s+SOURCE\s+GROUP:\s*(\S+))?",
            text, re.IGNORECASE,
        )
        if epa_pst_match:
            if header.averaging_period is None:
                header.averaging_period = epa_pst_match.group(1).strip()
            if epa_pst_match.group(3) and header.source_group is None:
                header.source_group = epa_pst_match.group(3).strip()
            # Detect plotfile vs postfile. A "1ST-HIGHEST MAX DAILY ... AVERAGED
            # OVER n YEARS" PLOTFILE (PM25AVE, NO2AVE, SO2AVE; output.f FORMAT
            # 9009) has the PLOTFILE columns and n (value, date) pairs after them.
            if re.match(r"PLOT\s+FILE\s+OF\s+HIGH", text, re.IGNORECASE):
                self._is_plotfile = True
            elif re.match(
                r"PLOT\s+FILE\s+OF\s+\d+(?:ST|ND|RD|TH)-HIGHEST\s+MAX\s+DAILY",
                text, re.IGNORECASE,
            ):
                self._is_plotfile = True
                if epa_pst_match.group(2):
                    self._years = int(epa_pst_match.group(2))
            return

        # Number of value columns from the FORMAT line. AERMOD writes the
        # row format as NUMTYP+2 wide float fields (X, Y and one value per
        # output type, F13.5 or E13.6) before the three F8.2 fields
        # (ZELEV, ZHILL, ZFLAG). Examples:
        #   (3(1X,F13.5),3(1X,F8.2),...)             -> 1 value column
        #   (6(1X,F13.5),3(1X,F8.2),...)             -> 4 value columns
        #   (2(1X,F13.5),3(1X,E13.6),3(1X,F8.2),...) -> 3 value columns
        #   (2(1X,F13.5),1X,E13.6,3(1X,F8.2),...)    -> 1 value column
        fmt_match = re.match(r"FORMAT:\s*\(", text, re.IGNORECASE)
        if fmt_match:
            # Match repeated groups like N(1X,F13.5) or N(1X,E13.6)
            wide_groups = re.findall(r"(\d+)\(1X,[FE]13", text)
            # Match standalone specs like 1X,E13.6 (implicit count of 1)
            standalone = re.findall(r"(?<!\d\()1X,[FE]13", text)
            num_wide_cols = sum(int(g) for g in wide_groups) + len(standalone)
            if num_wide_cols >= 3:
                self._format_numtyp = num_wide_cols - 2
            return

        # Column labels: "X  Y  AVERAGE CONC  TOTAL DEPO ...  ZELEV ..."
        if re.match(r"X\s+Y\s", text):
            labels = [
                _LABEL_TYPES[" ".join(m.split())]
                for m in _LABEL_PATTERN.findall(text.upper())
            ]
            if labels:
                self._label_types = tuple(labels)
            return

    def _parse_data_line(self, line: str) -> Optional[dict]:
        """
        Parse a single data line from the POSTFILE.

        With k output types (k value columns), a row reads::

            POSTFILE:           X Y V1..Vk ZELEV ZHILL ZFLAG AVE GRP DATE [NETID]
            PLOTFILE of highs:  X Y V1..Vk ZELEV ZHILL ZFLAG AVE GRP RANK [NETID] DATE

        NETID is blank for discrete receptors, so the PLOTFILE date is the
        last field; it is written without leading zeros (``I8``) and is
        padded here to the POSTFILE's eight digits. A PERIOD or ANNUAL
        PLOTFILE has the POSTFILE layout, with the number of hours (or
        years) where the date would be.

        Parameters
        ----------
        line : str
            A non-header line from the POSTFILE.

        Returns
        -------
        dict or None
            Dictionary with keys matching DataFrame columns, or None if
            the line cannot be parsed as valid data.
        """
        assert self._value_cols is not None
        value_cols = self._value_cols
        k = len(value_cols)
        parts = line.split()
        years = self._years or 0
        needed = 9 + k if self._is_plotfile else 8 + k
        if years:
            needed = 8 + k + 2 * years  # NET ID, before the pairs, may be blank
        if len(parts) < max(needed, 9):
            return None

        try:
            row: dict = {
                "x": _number_or_nan(parts[0], self),
                "y": _number_or_nan(parts[1], self),
            }
            for i, column in enumerate(value_cols):
                row[column] = _number_or_nan(parts[2 + i], self)
            row.update({
                "zelev": _number_or_nan(parts[2 + k], self),
                "zhill": _number_or_nan(parts[3 + k], self),
                "zflag": _number_or_nan(parts[4 + k], self),
                "ave": parts[5 + k],
                "grp": parts[6 + k],
            })
            if years:
                # PLOTFL writes the n ranked yearly values and their dates
                # last (FORMAT 10(F13.5,2X,I8.8,2X:)); a blank NET ID before
                # them is absent from the split, so count from the end.
                row["rank"] = parts[7 + k]
                tail = parts[-2 * years:]
                # The averaged value is in the value column; the date column
                # carries the number of years, as an ANNUAL POSTFILE's does.
                row["date"] = f"{years:08d}"
                for year in range(1, years + 1):
                    row[f"yr{year}_value"] = _number_or_nan(tail[2 * year - 2], self)
                    row[f"yr{year}_date"] = tail[2 * year - 1]
            elif self._is_plotfile:
                row["rank"] = parts[7 + k]
                # PLOTFL writes the date as I8, not I8.8 as a POSTFILE
                # does, so a year below 10 loses its leading zero.
                date = parts[-1]
                row["date"] = date.zfill(8) if date.isdigit() else date
            else:
                row["date"] = parts[7 + k]
            return row
        except (ValueError, IndexError):
            return None


# ============================================================================
# UNFORMATTED (BINARY) POSTFILE PARSER
# ============================================================================

class UnformattedPostfileParser:
    """
    Parser for AERMOD unformatted (binary) POSTFILE output files.

    AERMOD writes unformatted POSTFILE records using Fortran sequential
    unformatted I/O.  Each record has the layout::

        [4-byte record-length marker]
        KURDAT    — int32    (date in YYMMDDHH format)
        IANHRS    — int32    (hours in averaging period, or NUMYRS for ANNUAL)
        GRPID     — char*8   (source group ID, space-padded)
        AVEVAL()  — float64 × num_receptors × NUMTYP
        [4-byte record-length marker]

    A short-term record (``POSTFL`` in calc2.f) holds the hour its block
    average ends and ``KAVE``, the hours in its averaging period (1, 2, 3,
    4, 6, 8, 12 or 24, or 720 for MONTH). A PERIOD or ANNUAL record
    (``PSTANN`` in output.f) holds the run's last hour and, in the same
    field, the number of hours in the run (PERIOD) or of years (ANNUAL,
    NUMYRS). The text POSTFILE labels these rows ``PERIOD`` or ``ANNUAL``
    and writes the count where the date would be (``I8.8``, so five years
    read ``00000005``); this parser gives a binary file the same ``ave`` and
    ``date``.

    The record does not say which kind it is, so *averaging_period* names
    it. Without it each record is read as:

    - ``N-HR`` (or ``MONTH`` for 720) when IANHRS is a short-term period
      and KURDAT is an hour that period's blocks end on (a 3-HR block ends
      at hour 3, 6, ... 24; a MONTH at hour 24). An ANNUAL file over 1, 2,
      3, 4, 6, 8, 12 or 24 years, or a PERIOD file of that many hours ending
      on such an hour, reads this way too, so when every source group has
      just one record, as in an ANNUAL or PERIOD file, a ``UserWarning``
      asks for *averaging_period*.
    - ``PERIOD`` when IANHRS is 100 or more: no run has that many years.
    - Otherwise ``ValueError``: the record is ANNUAL or PERIOD, and only
      the caller knows which.

    The values come in one block of num_receptors per output type, in
    AERMOD's order CONC, DEPOS, DDEP, WDEP (``POSTFL`` in calc2.f writes
    ``((AVEVAL(IREC,IGRP,IAVE,ITYP),IREC=1,NUMREC),ITYP=1,NUMTYP)``). The
    file says neither how many receptors nor which types, so a file from a
    run with more than one output type needs *output_types* (or, for the
    unambiguous cases, *num_receptors*).

    Parameters
    ----------
    filepath : str or Path
        Path to the unformatted POSTFILE.
    num_receptors : int, optional
        Number of receptors.  If *None*, inferred from the first record size
        and the number of output types.
    receptor_coords : list of (float, float), optional
        ``(x, y)`` coordinate pairs, one per receptor.  Its length is the
        receptor count when *num_receptors* is not given, and must equal
        *num_receptors* when it is.  If *None*, receptors are assigned
        index-based coordinates ``(i, 0)``.
    has_deposition : bool, optional
        Shorthand for ``output_types=("CONC", "DDEP", "WDEP")``: *True*
        reads three blocks as concentration, dry and wet deposition.  If
        *None* (default) and *output_types* is not given, the types are
        inferred from *num_receptors* where the record size allows only one
        reading (see *output_types*).  If *False*, deposition columns are
        never produced.
    output_types : str or iterable of str, optional
        The run's output types, as its MODELOPT line (``"CONC DDEP FLAT"``)
        or as names (``["CONC", "DDEP"]``); order does not matter.  Without
        it, a record holding one block of values per receptor is read as
        concentration and four blocks as all four types; two or three
        blocks could be several sets of types and raise ``ValueError``
        (pass *has_deposition=True* for CONC DDEP WDEP).  The receptor
        count comes from *num_receptors* or *receptor_coords*; with
        neither, every value is read as a concentration at its own
        receptor, which is wrong for a run with more than one output
        type.  With *output_types*, a receptor count that disagrees with
        the record catches a wrong set of types that still divides the
        record evenly.
    averaging_period : str or int, optional
        The file's averaging period, as on the POSTFILE keyword: ``"1"``
        ... ``"24"`` (or ``"1-HR"`` ... ``"24-HR"``), ``"MONTH"``,
        ``"PERIOD"`` or ``"ANNUAL"``.  ``"PERIOD"`` and ``"ANNUAL"`` label
        every record so and put its IANHRS (hours, or NUMYRS) in ``date``
        as the text POSTFILE does; a short-term period or MONTH must match
        every record's IANHRS.  Without it the period is read from each
        record as described above.

    Raises
    ------
    FileNotFoundError
        If the specified file does not exist.
    """

    def __init__(
        self,
        filepath: Union[str, Path],
        num_receptors: Optional[int] = None,
        receptor_coords: Optional[List[Tuple[float, float]]] = None,
        has_deposition: Optional[bool] = None,
        output_types: OutputTypesArg = None,
        averaging_period: Union[str, int, None] = None,
    ):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"POSTFILE not found: {self.filepath}"
            )
        self.averaging_period = _normalize_averaging_period(averaging_period)
        self.num_receptors = num_receptors
        self.receptor_coords = receptor_coords
        self.has_deposition = has_deposition
        self.output_types = _normalize_output_types(output_types)
        if has_deposition is True and self.output_types not in (
            None, ("CONC", "DDEP", "WDEP"),
        ):
            raise ValueError(
                "has_deposition=True means CONC DDEP WDEP but output_types="
                f"{list(self.output_types or ())}; pass only output_types"
            )
        if has_deposition is False and self.output_types is not None and len(self.output_types) > 1:
            raise ValueError(
                f"has_deposition=False contradicts output_types={list(self.output_types)}"
            )
        if (
            receptor_coords is not None
            and num_receptors is not None
            and len(receptor_coords) != num_receptors
        ):
            raise ValueError(
                f"receptor_coords has {len(receptor_coords)} receptors but "
                f"num_receptors={num_receptors}"
            )

    def _resolve_types(self, num_floats: int) -> Optional[Tuple[str, ...]]:
        """
        Fix the output types and the receptor count from the first record.

        Returns the output types, or *None* for a single-type file whose
        type the caller did not give (its values go in ``concentration``).
        """
        types = self.output_types
        if types is None and self.has_deposition is True:
            types = ("CONC", "DDEP", "WDEP")

        # The receptor count, if the caller gave one
        if self.num_receptors is None and self.receptor_coords is not None:
            self.num_receptors = len(self.receptor_coords)
        if self.receptor_coords is not None:
            given = f"receptor_coords has {self.num_receptors} receptors"
        else:
            given = f"num_receptors={self.num_receptors}"

        if types is not None:
            numtyp = len(types)
            if num_floats % numtyp != 0:
                raise ValueError(
                    f"Record holds {num_floats} values, not divisible by "
                    f"{numtyp} (the output types {list(types)})"
                )
            inferred_nr = num_floats // numtyp
            if self.num_receptors is None:
                self.num_receptors = inferred_nr
            elif self.num_receptors != inferred_nr:
                # Too few or too many output types can still divide the
                # record evenly (12 values: 4 types x 3 receptors or 3 x 4);
                # the receptor count is the check the record cannot give.
                raise ValueError(
                    f"{given} but the record holds {inferred_nr} receptors "
                    f"({num_floats} values / {numtyp} output types "
                    f"{list(types)}); check output_types"
                )
            return types

        if self.num_receptors is None:
            # Concentration only — infer num_receptors
            self.num_receptors = num_floats
            return None

        n = self.num_receptors
        if self.has_deposition is None and n > 0 and num_floats % n == 0:
            blocks = num_floats // n
            if blocks == 4:
                return OUTPUT_TYPES
            if blocks in (2, 3):
                raise ValueError(
                    f"Record holds {num_floats} values for {n} receptors: "
                    f"{blocks} output types, which could be several sets of "
                    "CONC DEPOS DDEP WDEP; pass output_types (the run's "
                    "MODELOPT line)"
                )
        if num_floats != n:
            raise ValueError(
                f"Expected {n} values but record contains {num_floats} "
                f"({given}; not one to four blocks of that many)"
            )
        return None

    def parse(self) -> PostfileResult:
        """
        Read all records from the unformatted POSTFILE.

        Returns
        -------
        PostfileResult
            Parsed header metadata and concentration data.  Header fields
            are populated from the first record's source group and averaging
            info; ``version``, ``title``, ``model_options``, and
            ``pollutant_id`` are set to *None* (not present in binary format).
            ``output_types`` is set when the caller gave the types or the
            record size settled them.  ``ave`` and ``date`` are as the
            text POSTFILE writes them (see the class notes on PERIOD and
            ANNUAL records); ``header.averaging_period`` is the first
            record's ``ave``.

            A file with more than one output type has one column per type
            (``concentration``, ``total_depo``, ``dry_depo``,
            ``wet_depo``); a file with one keeps it in ``concentration``.
        """
        return self._parse(stacklevel=2)

    def _parse(self, stacklevel: int) -> PostfileResult:
        """:meth:`parse`, warning ``stacklevel`` frames up from its caller.

        ``stacklevel`` counts from the frame that called this, as
        :func:`warnings.warn` counts from its own caller: 1 is that frame,
        2 its caller. The warning that a file may be ANNUAL or PERIOD names
        the line in the user's code that asked for the file, so Python's
        default filter shows it for every such call, not once a session.
        """
        data_rows: list = []
        header = PostfileHeader(averaging_period=self.averaging_period)
        types: Optional[Tuple[str, ...]] = None
        value_cols: Optional[List[str]] = None
        # Records per source group, and the labels read from IANHRS
        records: Dict[str, int] = {}
        inferred: Set[Tuple[str, int]] = set()
        # IANHRS values seen per group, the IANHRS of each row's record, and
        # the groups found to be multi-year ANNUAL (see below)
        seen_ianhrs: Dict[str, Set[int]] = {}
        row_ianhrs: List[int] = []
        annual_groups: Set[str] = set()

        with open(self.filepath, "rb") as f:
            while True:
                record = self._read_record(f)
                if record is None:
                    break

                kurdat_int = record["kurdat"]
                ianhrs = record["ianhrs"]
                grpid = record["grpid"]
                values = record["values"]

                if self.averaging_period is None:
                    # KAVE is the same in every record of a short-term file,
                    # but PSTANN writes the running NUMYRS, so an ANNUAL
                    # file over several years holds IANHRS = 1, 2, ..., N.
                    # More than one IANHRS in a group can only be that.
                    seen_ianhrs.setdefault(grpid, set()).add(ianhrs)
                    if len(seen_ianhrs[grpid]) > 1:
                        annual_groups.add(grpid)
                if grpid in annual_groups:
                    ave, date_str = "ANNUAL", f"{ianhrs:08d}"
                else:
                    ave, date_str = self._label(kurdat_int, ianhrs)
                records[grpid] = records.get(grpid, 0) + 1
                if self.averaging_period is None:
                    inferred.add((ave, ianhrs))

                # --- Layout from the first record ------------------------
                if value_cols is None:
                    header.source_group = grpid
                    header.averaging_period = ave
                    types = self._resolve_types(len(values))
                    header.output_types = types
                    value_cols = _value_columns(types, len(types) if types else 1)

                # --- Validate every record's size ------------------------
                assert self.num_receptors is not None
                n = self.num_receptors
                expected = n * len(value_cols)
                if len(values) != expected:
                    raise ValueError(
                        f"Expected {expected} floats per record but "
                        f"got {len(values)}"
                    )

                # Resolve receptor coordinates (_resolve_types has checked
                # that a caller's list has one pair per receptor)
                if self.receptor_coords is not None:
                    coords = self.receptor_coords
                else:
                    coords = [(float(i), 0.0) for i in range(n)]

                for i in range(n):
                    x, y = coords[i]
                    row = {"x": x, "y": y}
                    for j, column in enumerate(value_cols):
                        row[column] = values[j * n + i]
                    row.update({
                        "zelev": 0.0,
                        "zhill": 0.0,
                        "zflag": 0.0,
                        "ave": ave,
                        "grp": grpid,
                        "date": date_str,
                    })
                    data_rows.append(row)
                    row_ianhrs.append(ianhrs)

        if annual_groups:
            # The records read before a second IANHRS showed up were labelled
            # as short-term ones: relabel them, keeping each year's values.
            for row, ianhrs in zip(data_rows, row_ianhrs):
                if row["grp"] in annual_groups:
                    row["ave"], row["date"] = "ANNUAL", f"{ianhrs:08d}"
            header.averaging_period = data_rows[0]["ave"]

        if records and all(n == 1 for n in records.values()):
            self._warn_one_record(inferred, stacklevel + 2)

        if data_rows:
            df = pd.DataFrame(data_rows)
        else:
            # Build empty DataFrame with the columns the caller's types imply
            types = self.output_types
            if types is None and self.has_deposition is True:
                types = ("CONC", "DDEP", "WDEP")
            header.output_types = types
            cols = ["x", "y", *_value_columns(types, len(types) if types else 1)]
            cols += ["zelev", "zhill", "zflag", "ave", "grp", "date"]
            df = pd.DataFrame(columns=cols)

        return PostfileResult(header=header, data=df)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _label(self, kurdat: int, ianhrs: int) -> Tuple[str, str]:
        """
        The ``ave`` and ``date`` of a record, as the text POSTFILE has them.

        PERIOD and ANNUAL rows have the record's IANHRS (hours, or NUMYRS)
        where a short-term row has its date, written as ``I8.8``.
        """
        given = self.averaging_period
        if given in ("PERIOD", "ANNUAL"):
            return given, f"{ianhrs:08d}"
        date = self._kurdat_to_str(kurdat)
        if given is not None:
            hours = _MONTH_HOURS if given == "MONTH" else int(given.split("-")[0])
            if ianhrs != hours:
                raise ValueError(
                    f"averaging_period={given!r} but the record at {date} holds "
                    f"IANHRS={ianhrs}, where a {given} record holds {hours}; "
                    "a PERIOD or ANNUAL record holds the run's hours or years"
                )
            return given, date
        hour = kurdat % 100
        if ianhrs in SHORT_TERM_HOURS and hour % ianhrs == 0:
            return f"{ianhrs}-HR", date
        if ianhrs == _MONTH_HOURS and hour % 24 == 0:
            return "MONTH", date
        if ianhrs >= _PERIOD_ONLY_HOURS:
            return "PERIOD", f"{ianhrs:08d}"
        raise ValueError(
            f"{self.filepath.name}: the record at {date} holds IANHRS={ianhrs}, "
            "which is not a short-term averaging period ending at that hour "
            "(1, 2, 3, 4, 6, 8, 12 or 24 hours, or 720 for MONTH). It is an "
            "ANNUAL record (IANHRS is NUMYRS, the years averaged) or a PERIOD "
            "one (the hours in the run), and a binary POSTFILE does not say "
            "which; pass averaging_period='ANNUAL' or averaging_period='PERIOD'"
        )

    def _warn_one_record(self, inferred: Set[Tuple[str, int]], stacklevel: int) -> None:
        """Warn that a file of one record per group may be ANNUAL or PERIOD.

        ``stacklevel`` is :func:`warnings.warn`'s, counted from here.
        """
        short = sorted((ianhrs, ave) for ave, ianhrs in inferred if ave != "PERIOD")
        if not short:
            return
        ianhrs, ave = short[0]
        plural = "" if ianhrs == 1 else "s"
        warnings.warn(
            f"{self.filepath.name} holds one record per source group, as an "
            f"ANNUAL or PERIOD POSTFILE does, and its IANHRS of {ianhrs} was "
            f"read as {ave}; an ANNUAL file over {ianhrs} year{plural}, or a "
            f"PERIOD of {ianhrs} hour{plural}, holds the same. Pass "
            f"averaging_period ('{ave}', 'ANNUAL' or 'PERIOD') to say which.",
            stacklevel=stacklevel,
        )

    def _read_record(self, f) -> Optional[dict]:
        """
        Read a single Fortran unformatted sequential record.

        Parameters
        ----------
        f : binary file object
            Open file positioned at the start of a record.

        Returns
        -------
        dict or None
            Dictionary with keys ``kurdat``, ``ianhrs``, ``grpid``,
            ``values`` (raw float list); or *None* at end-of-file.
        """
        # Leading 4-byte record-length marker
        marker_bytes = f.read(4)
        if len(marker_bytes) < 4:
            return None  # EOF

        rec_len = struct.unpack("<i", marker_bytes)[0]

        # Read the full record payload
        payload = f.read(rec_len)
        if len(payload) < rec_len:
            return None  # truncated file

        # Trailing record-length marker (should match)
        trail = f.read(4)
        if len(trail) < 4:
            return None
        trail_len = struct.unpack("<i", trail)[0]
        if trail_len != rec_len:
            raise ValueError(
                f"Record length mismatch: leading={rec_len}, "
                f"trailing={trail_len}"
            )

        # Parse payload:
        #   KURDAT  int32  (4 bytes)
        #   IANHRS  int32  (4 bytes)
        #   GRPID   char*8 (8 bytes)
        #   ANNVAL  float64 × N (remaining bytes)
        if len(payload) < 16:
            return None

        kurdat = struct.unpack("<i", payload[0:4])[0]
        ianhrs = struct.unpack("<i", payload[4:8])[0]
        grpid = payload[8:16].decode("ascii", errors="replace").strip()

        val_bytes = payload[16:]
        num_floats = len(val_bytes) // 8
        values = list(struct.unpack(f"<{num_floats}d", val_bytes))

        return {
            "kurdat": kurdat,
            "ianhrs": ianhrs,
            "grpid": grpid,
            "values": values,
        }

    @staticmethod
    def _kurdat_to_str(kurdat: int) -> str:
        """
        Convert KURDAT integer to YYMMDDHH date string.

        Parameters
        ----------
        kurdat : int
            Date integer in YYMMDDHH format (e.g. 26010101 for
            2026-01-01 hour 01).

        Returns
        -------
        str
            Zero-padded 8-character date string.
        """
        return f"{kurdat:08d}"


# ============================================================================
# FORMAT AUTO-DETECTION
# ============================================================================

def _is_text_postfile(filepath: Union[str, Path]) -> bool:
    """
    Detect whether a POSTFILE is in text (PLOT) or binary (UNFORM) format.

    A text file begins with ``*``, the first character of its header, or,
    when written with ``OU NOHEADER``, with a data row: printable ASCII.
    A binary file begins with a 4-byte little-endian record length, whose
    high bytes are zero for any record under 16 MB.

    Parameters
    ----------
    filepath : str or Path
        Path to the POSTFILE.

    Returns
    -------
    bool
        *True* if the file appears to be a formatted (text) POSTFILE.
    """
    with open(filepath, "rb") as f:
        chunk = f.read(512)
    if not chunk:
        return True  # empty file — treat as text
    if chunk[:1] == b"*":
        return True
    return all(b in b"\t\n\r" or 0x20 <= b < 0x7F for b in chunk)


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def read_postfile(
    filepath: Union[str, Path],
    *,
    num_receptors: Optional[int] = None,
    receptor_coords: Optional[List[Tuple[float, float]]] = None,
    has_deposition: Optional[bool] = None,
    output_types: OutputTypesArg = None,
    averaging_period: Union[str, int, None] = None,
) -> PostfileResult:
    """
    Parse an AERMOD POSTFILE and return the result.

    Automatically detects whether the file is in formatted (PLOT/text) or
    unformatted (UNFORM/binary) format.  Also reads text PLOTFILEs, and
    text files written without a header (``OU NOHEADER``).

    Parameters
    ----------
    filepath : str or Path
        Path to the POSTFILE.
    num_receptors : int, optional
        Number of receptors (binary files only).  Ignored for text files.
        If *None*, taken from *receptor_coords*, else inferred from the
        first record.
    receptor_coords : list of (float, float), optional
        Receptor ``(x, y)`` coordinates, one pair per receptor (binary
        files only).  Ignored for text files.
    has_deposition : bool, optional
        Binary files only: *True* is shorthand for
        ``output_types=("CONC", "DDEP", "WDEP")``.  Ignored for text files.
    output_types : str or iterable of str, optional
        The run's output types, as its MODELOPT line
        (``"CONC DDEP WDEP FLAT"``) or as names (``["CONC", "DDEP"]``).
        A binary file from a run with more than one output type needs it
        (except for all four types with a known receptor count), and so
        does a text file written without a header that has two or three
        value columns.  A text file with a header names its types there,
        and a different *output_types* raises ``ValueError``.
    averaging_period : str or int, optional
        Binary files only: the file's averaging period, as on its POSTFILE
        keyword (``"1"`` ... ``"24"``, ``"MONTH"``, ``"PERIOD"``,
        ``"ANNUAL"``).  A binary record holds the hours of a short-term
        period, the hours of a PERIOD run or the years of an ANNUAL one in
        the same field, so an ANNUAL or PERIOD file needs it to be labelled
        as its text POSTFILE is (see :class:`UnformattedPostfileParser`).
        Ignored for text files, which name the period in every row.

    Notes
    -----
    An hourly POSTFILE has a row for every hour, calm and missing hours
    included, and nothing in a row says which hours those were. A 24-hour
    or PERIOD/ANNUAL mean computed from its rows therefore divides by the
    number of rows, where AERMOD divides by the hours that were neither calm
    nor missing; the two differ for any period that has such hours. Have
    AERMOD write the averaged value (``POSTFILE 24``, ``PERIOD``) when it is
    the number that matters.

    Returns
    -------
    PostfileResult
        Parsed header metadata and data.  ``result.output_types`` gives the
        file's output types and ``result.column_for("DDEP")`` the column
        that holds one of them.
    """
    return _read_postfile(
        filepath, num_receptors=num_receptors, receptor_coords=receptor_coords,
        has_deposition=has_deposition, output_types=output_types,
        averaging_period=averaging_period, stacklevel=2,
    )


def _read_postfile(
    filepath: Union[str, Path],
    *,
    num_receptors: Optional[int] = None,
    receptor_coords: Optional[List[Tuple[float, float]]] = None,
    has_deposition: Optional[bool] = None,
    output_types: OutputTypesArg = None,
    averaging_period: Union[str, int, None] = None,
    stacklevel: int,
) -> PostfileResult:
    """:func:`read_postfile`, its warnings ``stacklevel`` frames up from its caller.

    ``stacklevel`` counts as :meth:`UnformattedPostfileParser._parse`'s
    does: 2 names the line that called this function's caller. pyaermod's
    own readers of a POSTFILE (:mod:`pyaermod.regulatory_parity`) call
    this with the frames between them and the user added, so a warning
    names the user's line.
    """
    filepath = Path(filepath)
    parser: Union[PostfileParser, UnformattedPostfileParser]
    if _is_text_postfile(filepath):
        parser = PostfileParser(filepath, output_types=output_types)
    else:
        parser = UnformattedPostfileParser(
            filepath,
            num_receptors=num_receptors,
            receptor_coords=receptor_coords,
            has_deposition=has_deposition,
            output_types=output_types,
            averaging_period=averaging_period,
        )
        return parser._parse(stacklevel=stacklevel + 1)
    return parser.parse()
