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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

import pandas as pd

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

OutputTypesArg = Union[str, Iterable[str], None]


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

    def get_receptor(
        self, x: float, y: float, tolerance: float = 1.0
    ) -> pd.DataFrame:
        """
        Get all data rows for a specific receptor location.

        Parameters
        ----------
        x : float
            X coordinate of the receptor.
        y : float
            Y coordinate of the receptor.
        tolerance : float
            Distance tolerance for matching receptor coordinates.

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
        return self.data[mask].copy()

    def get_max_by_receptor(self) -> pd.DataFrame:
        """
        Get the maximum of the first output type at each receptor location.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns x, y and the first output type's column
            (``concentration`` whenever the file holds CONC).
        """
        column = self._primary_column
        if self.data.empty:
            return pd.DataFrame(columns=["x", "y", column])
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

        if data_rows:
            df = pd.DataFrame(data_rows)
        else:
            # Build default columns based on detected format
            cols = ["x", "y", *self._value_cols]
            cols.extend(["zelev", "zhill", "zflag", "ave", "grp"])
            if self._is_plotfile:
                cols.append("rank")
            cols.append("date")
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
                float(parts[idx])
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

        # Model options
        options_match = re.match(
            r"MODELING\s+OPTIONS\s+USED:\s*(.*)", text, re.IGNORECASE
        )
        if options_match:
            header.model_options = options_match.group(1).strip()
            return

        # Averaging period — pyaermod synthetic format
        ave_match = re.match(r"AVERTIME:\s*(.*)", text, re.IGNORECASE)
        if ave_match:
            header.averaging_period = ave_match.group(1).strip()
            return

        # EPA format: POST/PLOT FILE OF CONCURRENT <period> VALUES
        # Also: PLOT FILE OF  HIGH <rank> <period> VALUES
        epa_pst_match = re.match(
            r"(?:POST/?PLOT|POST|PLOT)\s+FILE\s+OF\s+.*?"
            r"\b(\d+-HR|PERIOD|ANNUAL|MONTH)\b\s+VALUES"
            r"(?:\s+FOR\s+SOURCE\s+GROUP:\s*(\S+))?",
            text, re.IGNORECASE,
        )
        if epa_pst_match:
            if header.averaging_period is None:
                header.averaging_period = epa_pst_match.group(1).strip()
            if epa_pst_match.group(2) and header.source_group is None:
                header.source_group = epa_pst_match.group(2).strip()
            # Detect plotfile vs postfile
            if re.match(r"PLOT\s+FILE\s+OF\s+HIGH", text, re.IGNORECASE):
                self._is_plotfile = True
            return

        # Pollutant ID — pyaermod synthetic format
        poll_match = re.match(r"POLLUTID:\s*(.*)", text, re.IGNORECASE)
        if poll_match:
            header.pollutant_id = poll_match.group(1).strip()
            return

        # Source group — pyaermod synthetic format
        src_match = re.match(r"SRCGROUP:\s*(.*)", text, re.IGNORECASE)
        if src_match:
            header.source_group = src_match.group(1).strip()
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
        needed = 9 + k if self._is_plotfile else 8 + k
        if len(parts) < max(needed, 9):
            return None

        try:
            row: dict = {"x": float(parts[0]), "y": float(parts[1])}
            for i, column in enumerate(value_cols):
                row[column] = float(parts[2 + i])
            row.update({
                "zelev": float(parts[2 + k]),
                "zhill": float(parts[3 + k]),
                "zflag": float(parts[4 + k]),
                "ave": parts[5 + k],
                "grp": parts[6 + k],
            })
            if self._is_plotfile:
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
    ):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"POSTFILE not found: {self.filepath}"
            )
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
            record size settled them.

            A file with more than one output type has one column per type
            (``concentration``, ``total_depo``, ``dry_depo``,
            ``wet_depo``); a file with one keeps it in ``concentration``.
        """
        data_rows: list = []
        header = PostfileHeader()
        types: Optional[Tuple[str, ...]] = None
        value_cols: Optional[List[str]] = None

        with open(self.filepath, "rb") as f:
            while True:
                record = self._read_record(f)
                if record is None:
                    break

                kurdat_int = record["kurdat"]
                ianhrs = record["ianhrs"]
                grpid = record["grpid"]
                values = record["values"]

                # --- Layout from the first record ------------------------
                if value_cols is None:
                    header.source_group = grpid
                    if ianhrs == 1:
                        header.averaging_period = "1-HR"
                    elif ianhrs == 24:
                        header.averaging_period = "24-HR"
                    else:
                        header.averaging_period = f"{ianhrs}-HR"
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

                date_str = self._kurdat_to_str(kurdat_int)

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
                        "ave": header.averaging_period or "1-HR",
                        "grp": grpid,
                        "date": date_str,
                    })
                    data_rows.append(row)

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

    Returns
    -------
    PostfileResult
        Parsed header metadata and data.  ``result.output_types`` gives the
        file's output types and ``result.column_for("DDEP")`` the column
        that holds one of them.
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
        )
    return parser.parse()
