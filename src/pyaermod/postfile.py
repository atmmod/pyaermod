"""
PyAERMOD POSTFILE Parser

Parses AERMOD POSTFILE output files containing concentration grids
for each averaging period and source group.

Supports both formatted (PLOT) and unformatted (UNFORM/binary) POSTFILE output.

AERMOD formatted POSTFILE (PLOT):
    - Header lines start with '*' and contain metadata such as AERMOD version,
      AVERTIME, POLLUTID, and SRCGROUP.
    - Data lines contain columns: X, Y, CONC, ZELEV, ZHILL, ZFLAG, AVE, GRP,
      DATE (YYMMDDHH).
    - Concentrations may use scientific notation (e.g. 1.23456E+01).

AERMOD unformatted POSTFILE (UNFORM):
    - Fortran unformatted sequential records.
    - Each record contains: KURDAT (int32), IANHRS (int32), GRPID (char*8),
      ANNVAL (float64 x num_receptors).
    - Receptor coordinates are NOT stored in the binary file; they must be
      supplied externally or default to index-based values.

Based on AERMOD version 24142 POSTFILE specifications.
"""

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

import pandas as pd


@dataclass
class PostfileHeader:
    """
    Metadata parsed from POSTFILE header lines.

    Each field corresponds to a '*'-prefixed header line in the POSTFILE.
    """
    version: Optional[str] = None
    title: Optional[str] = None
    model_options: Optional[str] = None
    averaging_period: Optional[str] = None
    pollutant_id: Optional[str] = None
    source_group: Optional[str] = None


@dataclass
class PostfileResult:
    """
    Parsed data for a single POSTFILE (one source group / averaging period).

    Attributes
    ----------
    header : PostfileHeader
        Metadata extracted from the file header.
    data : pd.DataFrame
        Concentration data with columns: x, y, concentration, zelev,
        zhill, zflag, ave, grp, date.
    """
    header: PostfileHeader
    data: pd.DataFrame

    @property
    def max_concentration(self) -> float:
        """Return the maximum concentration value in the dataset."""
        if self.data.empty:
            return 0.0
        return float(self.data["concentration"].max())

    @property
    def max_location(self) -> Tuple[float, float]:
        """Return (x, y) coordinates of the maximum concentration."""
        if self.data.empty:
            return (0.0, 0.0)
        idx = self.data["concentration"].idxmax()
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
        Get the maximum concentration at each unique receptor location.

        Returns
        -------
        pd.DataFrame
            DataFrame with columns x, y, concentration (max at each receptor).
        """
        if self.data.empty:
            return pd.DataFrame(columns=["x", "y", "concentration"])
        return (
            self.data.groupby(["x", "y"])["concentration"]
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

    Parameters
    ----------
    filepath : str or Path
        Path to the POSTFILE to parse.

    Raises
    ------
    FileNotFoundError
        If the specified file does not exist.
    """

    def __init__(self, filepath: Union[str, Path]):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"POSTFILE not found: {self.filepath}"
            )

    def parse(self) -> PostfileResult:
        """
        Read and parse the POSTFILE.

        Returns
        -------
        PostfileResult
            Parsed header metadata and concentration data.
        """
        header = PostfileHeader()
        data_rows = []

        with open(self.filepath, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("*"):
                    self._parse_header_line(line, header)
                else:
                    row = self._parse_data_line(line)
                    if row is not None:
                        data_rows.append(row)

        if data_rows:
            df = pd.DataFrame(data_rows)
        else:
            df = pd.DataFrame(
                columns=[
                    "x", "y", "concentration", "zelev",
                    "zhill", "zflag", "ave", "grp", "date",
                ]
            )

        return PostfileResult(header=header, data=df)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_header_line(self, line: str, header: PostfileHeader) -> None:
        """
        Extract metadata from a single header line.

        Recognized patterns (case-insensitive):
            * AERMOD ( <version> )   -> header.version, header.title
            * MODELING OPTIONS USED: -> header.model_options
            * AVERTIME:              -> header.averaging_period
            * POLLUTID:              -> header.pollutant_id
            * SRCGROUP:              -> header.source_group

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

        # Averaging period
        ave_match = re.match(r"AVERTIME:\s*(.*)", text, re.IGNORECASE)
        if ave_match:
            header.averaging_period = ave_match.group(1).strip()
            return

        # Pollutant ID
        poll_match = re.match(r"POLLUTID:\s*(.*)", text, re.IGNORECASE)
        if poll_match:
            header.pollutant_id = poll_match.group(1).strip()
            return

        # Source group
        src_match = re.match(r"SRCGROUP:\s*(.*)", text, re.IGNORECASE)
        if src_match:
            header.source_group = src_match.group(1).strip()
            return

    @staticmethod
    def _parse_data_line(line: str) -> Optional[dict]:
        """
        Parse a single data line from the POSTFILE.

        Expected column order:
            X  Y  CONC  ZELEV  ZHILL  ZFLAG  AVE  GRP  DATE

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
        parts = line.split()
        if len(parts) < 9:
            return None

        try:
            return {
                "x": float(parts[0]),
                "y": float(parts[1]),
                "concentration": float(parts[2]),
                "zelev": float(parts[3]),
                "zhill": float(parts[4]),
                "zflag": float(parts[5]),
                "ave": parts[6],
                "grp": parts[7],
                "date": parts[8],
            }
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
        ANNVAL()  — float64 × num_receptors  (concentration per receptor)
        [4-byte record-length marker]

    Parameters
    ----------
    filepath : str or Path
        Path to the unformatted POSTFILE.
    num_receptors : int, optional
        Number of receptors.  If *None*, inferred from the first record size.
    receptor_coords : list of (float, float), optional
        ``(x, y)`` coordinate pairs for each receptor index.  If *None*,
        receptors are assigned index-based coordinates ``(i, 0)``.

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
    ):
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"POSTFILE not found: {self.filepath}"
            )
        self.num_receptors = num_receptors
        self.receptor_coords = receptor_coords

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
        """
        data_rows: list = []
        header = PostfileHeader()

        with open(self.filepath, "rb") as f:
            first_record = True
            while True:
                record = self._read_record(f)
                if record is None:
                    break

                kurdat_int = record["kurdat"]
                ianhrs = record["ianhrs"]
                grpid = record["grpid"]
                concentrations = record["concentrations"]

                # Populate header from first record
                if first_record:
                    header.source_group = grpid
                    if ianhrs == 1:
                        header.averaging_period = "1-HR"
                    elif ianhrs == 24:
                        header.averaging_period = "24-HR"
                    else:
                        header.averaging_period = f"{ianhrs}-HR"
                    first_record = False

                date_str = self._kurdat_to_str(kurdat_int)
                num_rec = len(concentrations)

                # Resolve receptor coordinates
                if self.receptor_coords is not None:
                    coords = self.receptor_coords
                else:
                    coords = [(float(i), 0.0) for i in range(num_rec)]

                for i, conc in enumerate(concentrations):
                    x, y = coords[i] if i < len(coords) else (float(i), 0.0)
                    data_rows.append({
                        "x": x,
                        "y": y,
                        "concentration": conc,
                        "zelev": 0.0,
                        "zhill": 0.0,
                        "zflag": 0.0,
                        "ave": header.averaging_period or "1-HR",
                        "grp": grpid,
                        "date": date_str,
                    })

        if data_rows:
            df = pd.DataFrame(data_rows)
        else:
            df = pd.DataFrame(
                columns=[
                    "x", "y", "concentration", "zelev",
                    "zhill", "zflag", "ave", "grp", "date",
                ]
            )

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
            ``concentrations``; or *None* at end-of-file.
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

        conc_bytes = payload[16:]
        num_rec = len(conc_bytes) // 8

        # Infer or validate num_receptors from first record
        if self.num_receptors is None:
            self.num_receptors = num_rec
        elif num_rec != self.num_receptors:
            raise ValueError(
                f"Expected {self.num_receptors} receptors but record "
                f"contains {num_rec}"
            )

        concentrations = list(struct.unpack(f"<{num_rec}d", conc_bytes))

        return {
            "kurdat": kurdat,
            "ianhrs": ianhrs,
            "grpid": grpid,
            "concentrations": concentrations,
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

    Reads the first byte of the file: text POSTFILEs always begin with
    ``*`` (0x2A) as the first character of the header.

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
        first_byte = f.read(1)
        if not first_byte:
            return True  # empty file — treat as text
        return first_byte == b"*"


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def read_postfile(
    filepath: Union[str, Path],
    *,
    num_receptors: Optional[int] = None,
    receptor_coords: Optional[List[Tuple[float, float]]] = None,
) -> PostfileResult:
    """
    Parse an AERMOD POSTFILE and return the result.

    Automatically detects whether the file is in formatted (PLOT/text) or
    unformatted (UNFORM/binary) format.

    Parameters
    ----------
    filepath : str or Path
        Path to the POSTFILE.
    num_receptors : int, optional
        Number of receptors (binary files only).  Ignored for text files.
        If *None*, inferred from the first record.
    receptor_coords : list of (float, float), optional
        Receptor ``(x, y)`` coordinates (binary files only).  Ignored for
        text files.

    Returns
    -------
    PostfileResult
        Parsed header metadata and concentration data.
    """
    filepath = Path(filepath)
    if _is_text_postfile(filepath):
        parser = PostfileParser(filepath)
    else:
        parser = UnformattedPostfileParser(
            filepath,
            num_receptors=num_receptors,
            receptor_coords=receptor_coords,
        )
    return parser.parse()
