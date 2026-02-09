"""
PyAERMOD POSTFILE Parser

Parses AERMOD POSTFILE output files containing concentration grids
for each averaging period and source group.

AERMOD POSTFILE format:
    - Header lines start with '*' and contain metadata such as AERMOD version,
      AVERTIME, POLLUTID, and SRCGROUP.
    - Data lines contain columns: X, Y, CONC, ZELEV, ZHILL, ZFLAG, AVE, GRP,
      DATE (YYMMDDHH).
    - Concentrations may use scientific notation (e.g. 1.23456E+01).

Based on AERMOD version 24142 POSTFILE specifications.
"""

import re
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, Tuple, Union
from pathlib import Path


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

        with open(self.filepath, "r", encoding="utf-8", errors="ignore") as f:
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
# CONVENIENCE FUNCTION
# ============================================================================

def read_postfile(filepath: Union[str, Path]) -> PostfileResult:
    """
    Parse an AERMOD POSTFILE and return the result.

    This is a convenience wrapper around ``PostfileParser``.

    Parameters
    ----------
    filepath : str or Path
        Path to the POSTFILE.

    Returns
    -------
    PostfileResult
        Parsed header metadata and concentration data.
    """
    parser = PostfileParser(filepath)
    return parser.parse()
