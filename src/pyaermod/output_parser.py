"""
PyAERMOD Output File Parser

Parses AERMOD output files (.out) and converts results to pandas DataFrames.
Based on AERMOD version 26135 output format specifications (validated against
26135 and 24142; see :mod:`pyaermod.versions`).
"""

import logging
import math
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ._fortran import fortran_float
from .versions import VALIDATED_AERMOD_VERSIONS, is_validated_aermod_version

logger = logging.getLogger(__name__)


@dataclass
class ModelRunInfo:
    """Metadata about the AERMOD run"""
    version: str
    jobname: str
    #: The deck's TITLEONE, from the page banner AERMOD prints.
    title: Optional[str] = None
    run_date: Optional[str] = None
    run_time: Optional[str] = None
    model_options: List[str] = field(default_factory=list)
    pollutant_id: Optional[str] = None
    averaging_periods: List[str] = field(default_factory=list)
    terrain_type: Optional[str] = None
    urban_option: Optional[str] = None

    # Date range
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    # Number of sources/receptors
    num_sources: int = 0
    num_receptors: int = 0


@dataclass
class SourceSummary:
    """Summary information for a source"""
    source_id: str
    source_type: str
    x_coord: float
    y_coord: float
    base_elevation: float

    # Stack parameters (for point sources)
    stack_height: Optional[float] = None
    stack_temp: Optional[float] = None
    exit_velocity: Optional[float] = None
    stack_diameter: Optional[float] = None
    emission_rate: Optional[float] = None


@dataclass
class ReceptorInfo:
    """Information about a receptor"""
    x_coord: float
    y_coord: float
    z_elev: float = 0.0
    z_hill: float = 0.0
    z_flag: float = 0.0
    receptor_id: Optional[str] = None


@dataclass
class ConcentrationResult:
    """Results for one averaging period, as one of AERMOD's summary tables.

    ``output_type`` says what the values are: ``"CONC"`` (concentration)
    or, for a deposition run, ``"DEPOS"`` (total), ``"DDEP"`` (dry) or
    ``"WDEP"`` (wet deposition). ``units`` is the unit AERMOD printed
    over the table (``MICROGRAMS/M**3`` is given as ``ug/m^3`` and
    ``GRAMS/M**2`` as ``g/m^2``). ``title`` is the table's own heading,
    for example ``THE SUMMARY OF HIGHEST  1-HR RESULTS``.

    Rows read from AERMOD's summary tables carry, besides ``x``, ``y``
    and ``concentration``, the ``rank``, the source ``group``, the
    ``date`` (YYMMDDHH, short-term averages only), ``zelev``, ``zhill``
    and ``zflag``, the ``receptor_type`` and ``grid_id``, the value as
    AERMOD printed it (``value_text``) and its calm/missing ``flag``:
    ``"c"`` when the average included calm hours, ``"m"`` missing hours,
    ``"b"`` both, and ``""`` for neither.
    """
    averaging_period: str
    data: pd.DataFrame  # Contains x, y, concentration, rank, etc.
    max_value: float
    max_location: Tuple[float, float]
    units: str = "ug/m^3"
    output_type: str = "CONC"
    title: Optional[str] = None

    @property
    def max_row(self) -> Optional[Dict]:
        """The row of the maximum, as a dict, or None for an empty table."""
        i = _max_index(self.data)
        return None if i is None else self.data.loc[i].to_dict()


def _max_index(df: pd.DataFrame):
    """Index label of the highest ``concentration``, or None when the table
    is empty or holds no number."""
    if df.empty or "concentration" not in df:
        return None
    values = pd.to_numeric(df["concentration"], errors="coerce")
    return None if values.isna().all() else values.idxmax()


#: Unit labels AERMOD prints over its tables, as pyaermod reports them.
_UNIT_LABELS = {
    "MICROGRAMS/M**3": "ug/m^3",
    "GRAMS/M**2": "g/m^2",
    "GRAMS/M**2/YR": "g/m^2/yr",
}

#: The value column's heading in a summary table (CHIDEP in coset.f)
#: -> the output type it holds.
_OUTPUT_TYPE_HEADINGS = (
    (re.compile(r"\bAVERAGE\s+CONC\b"), "CONC"),
    (re.compile(r"\bTOTAL\s+DEPO\b"), "DEPOS"),
    (re.compile(r"\bDRY\s+DEPO\b"), "DDEP"),
    (re.compile(r"\bWET\s+DEPO\b"), "WDEP"),
)

# FORMAT 9011 of output.f PRTSUM: "** CONC OF SO2      IN MICROGRAMS/M**3  **".
_UNITS_LINE = re.compile(
    r"^\s*\*\*\s+(CONC|DEPO)\s+OF\s+(\S*)\s+IN\s+(.+?)\s+\*\*\s*$")

# FORMATs 9020-9031 and 9091/99091 of output.f: every summary table AERMOD
# prints starts with one of these headings.
_RANKED_HEADING = re.compile(r"\b(\d+)(?:ST|ND|RD|TH)-HIGHEST\b", re.IGNORECASE)
_YEARS_HEADING = re.compile(r"AVERAGED\s+OVER\s+(\d+)\s+YEARS", re.IGNORECASE)


def _is_maximum_table(title: Optional[str]) -> bool:
    """Whether a summary table's heading is that of the highest values:
    ``HIGHEST 1-HR``, ``MAXIMUM PERIOD``, ``MAXIMUM ANNUAL``, or a
    1ST-highest design-value table of one year; not an Nth-highest one or
    a multi-year average of ranked values."""
    rank = _RANKED_HEADING.search(title or "")
    if rank is None:
        return True
    years = _YEARS_HEADING.search(title or "")
    return int(rank.group(1)) == 1 and (years is None or int(years.group(1)) == 1)


_SUMMARY_HEADING = re.compile(
    r"\*\*\*\s*(THE\s+SUMMARY\s+OF\s+(?:HIGHEST|MAXIMUM)\b.*?\bRESULTS\b.*?)\s*\*\*\*",
    re.IGNORECASE)
_MULTIYEAR_LINE = re.compile(
    r"^\s*\*\*\*\s*(ACROSS\s+\d+\s+YEARS\s+WITH\s+THE\s+MULTYEAR\s+OPTION)\s*\*\*\*\s*$",
    re.IGNORECASE)
_PAGE_HEADER = re.compile(r"\*\*\*\s*AER(?:MOD|MET)\s+-\s+VERSION|\*\*\*\s*MODELOPTs",
                          re.IGNORECASE)

# One row of a summary table (FORMATs 1002-1005 and 1012-1015 of PRTSUM).
# A short-term value is F14.5 or E14.6 followed by A1, a calm/missing flag
# that is blank, "c", "m" or "b" and touches the number; so the value is
# every non-blank character up to the flag.
_SUMMARY_ROW = re.compile(
    r"^(?P<prefix>.*?)(?P<rank>\d+(?:ST|ND|RD|TH))\s+HIGH(?:EST)?\s+VALUE\s+IS\s*"
    r"(?P<value>\S+?)(?P<flag>[cmb])?\s+(?:ON\s+(?P<date>\d+)\s*:\s*)?"
    r"AT\s*\(\s*(?P<coords>[^)]*)\)\s*(?P<rtype>[A-Z]{2})?\s*(?P<grid>\S+)?",
    re.IGNORECASE)


def _float_or_nan(text: str) -> float:
    try:
        return fortran_float(text)
    except ValueError:
        return float("nan")


def _summary_period(title: str) -> Optional[str]:
    """The averaging period a summary heading is about: "1HR", "PERIOD", ..."""
    upper = title.upper()
    for word in ("PERIOD", "ANNUAL", "MONTH"):
        if re.search(rf"\b{word}\b", upper):
            return word
    hours = re.findall(r"(?<![0-9])(\d{1,2})\s*-?\s*(?:HR|HOUR)S?\b", upper)
    return f"{int(hours[-1])}HR" if hours else None


class AERMODOutputParser:
    """
    Parser for AERMOD output files

    Extracts run information, source data, receptor data, and concentration results.
    """

    # Maximum file size we'll load into memory as a single string. AERMOD
    # .OUT logs for 5-year 1-hour runs with dense receptors can exceed
    # several hundred MB. Beyond this cap we load only the HEAD + TAIL
    # sections — enough for header metadata and summary/concentration
    # tables but not receptor-by-hour diagnostics. Users who need the
    # full middle can stream the file themselves.
    MAX_SLURP_BYTES = 500 * 1024 * 1024   # 500 MB
    HEAD_BYTES = 2 * 1024 * 1024          # 2 MB of start
    TAIL_BYTES = 64 * 1024 * 1024         # 64 MB of end

    def __init__(
        self,
        output_file: Union[str, Path],
        max_slurp_bytes: Optional[int] = None,
    ):
        """
        Initialize parser with output file

        Args:
            output_file: Path to AERMOD .out file
            max_slurp_bytes: File-size threshold above which the parser
                reads only the head + tail of the file instead of the
                full contents. Defaults to ``AERMODOutputParser.MAX_SLURP_BYTES``
                (500 MB). Set to 0 to force head+tail mode regardless of
                file size; set to a very large number to force a full
                slurp (caution: risks OOM on multi-GB files).
        """
        self.output_file = Path(output_file)

        if not self.output_file.exists():
            raise FileNotFoundError(f"Output file not found: {output_file}")

        cap = self.MAX_SLURP_BYTES if max_slurp_bytes is None else max_slurp_bytes
        size = self.output_file.stat().st_size
        self.truncated = size > cap > 0 or cap == 0

        if not self.truncated:
            # Small/typical case: read the whole file as before
            with open(self.output_file, encoding='utf-8', errors='ignore') as f:
                self.content = f.read()
        else:
            # Large file: read HEAD + marker + TAIL so we keep header
            # metadata + end-of-run summary without loading gigabytes.
            with open(self.output_file, encoding='utf-8', errors='ignore') as f:
                head = f.read(min(self.HEAD_BYTES, size))
                if size > self.HEAD_BYTES + self.TAIL_BYTES:
                    f.seek(size - self.TAIL_BYTES)
                    tail = f.read()
                    omitted = size - self.HEAD_BYTES - self.TAIL_BYTES
                    self.content = (
                        head
                        + f"\n\n[...pyaermod: truncated {omitted:,} bytes; "
                        f"file size {size:,} > {cap:,} byte cap...]\n\n"
                        + tail
                    )
                else:
                    # File just fits in head+tail
                    f.seek(self.HEAD_BYTES)
                    self.content = head + f.read()

        # Parsed data
        self.run_info: Optional[ModelRunInfo] = None
        self.sources: List[SourceSummary] = []
        self.receptors: List[ReceptorInfo] = []
        self.concentrations: Dict[str, ConcentrationResult] = {}
        self.deposition: Dict[str, Dict[str, ConcentrationResult]] = {}
        self.summaries: List[ConcentrationResult] = []

    def parse(self) -> 'AERMODResults':
        """
        Parse the output file and return results object

        Returns:
            AERMODResults object with all parsed data
        """
        run_info = self._parse_header()
        self._parse_sources()
        self._parse_receptors()
        self._parse_concentration_results()

        if not (self.sources or self.receptors or self.concentrations
                or self.deposition or self.summaries):
            what = ("an AERMOD run that stopped before it wrote them, for example "
                    "on a setup error"
                    if run_info.version != "Unknown" else
                    "not an AERMOD main output (.out) file, or not in the layout "
                    "AERMOD writes")
            warnings.warn(
                f"{self.output_file}: no source, receptor or result table was "
                f"found, so the results are empty. This is {what}.",
                UserWarning, stacklevel=4,
            )

        return AERMODResults(
            run_info=run_info,
            sources=self.sources,
            receptors=self.receptors,
            concentrations=self.concentrations,
            output_file=str(self.output_file),
            deposition=self.deposition,
            summaries=self.summaries,
        )

    def _parse_header(self) -> ModelRunInfo:
        """Extract run information from header, store it in ``run_info`` and return it"""
        run_info = ModelRunInfo(
            version="Unknown",
            jobname="Unknown"
        )

        # AERMOD version
        version_match = re.search(r'AERMOD\s*-\s*VERSION\s*[:\s]*(\d+)', self.content)
        if version_match:
            run_info.version = version_match.group(1)
            if not is_validated_aermod_version(run_info.version):
                # One warning per parse: the format may still read fine,
                # but nothing in the test suite has checked this release.
                logger.warning(
                    "AERMOD output %s was produced by version %s, which pyaermod "
                    "has not been validated against (validated: %s); parsed "
                    "results may need checking.",
                    self.output_file, run_info.version,
                    ", ".join(VALIDATED_AERMOD_VERSIONS),
                )

        # TITLEONE, from the page banner (FORMAT 9028 of output.f HEADER):
        # " *** AERMOD - VERSION 26135  ***   ***  title  ***  10/15/26"
        title_match = re.search(
            r'\*\*\*\s*AERMOD\s*-\s*VERSION\s*\S+\s*\*\*\*\s*\*\*\*(.*?)\*\*\*',
            self.content)
        if title_match and title_match.group(1).strip():
            run_info.title = title_match.group(1).strip()

        # Pollutant ID: "* The User Specified a Pollutant Type of: SO2"
        pollutant_match = re.search(r'Pollutant\s+Type\s+of:\s*(\S+)', self.content)
        if pollutant_match:
            run_info.pollutant_id = pollutant_match.group(1).strip()

        self._parse_banner_and_setup(run_info)

        # The page banner's MODELOPTs line (" *** MODELOPTs:  NonDFAULT  CONC
        # FLAT  RURAL"), which every AERMOD .out carries
        modelopt_match = re.search(r'\*\*\*\s*MODELOPTs:\s*(.+)', self.content)
        if modelopt_match:
            run_info.model_options = modelopt_match.group(1).split()

        # Terrain type
        if 'FLAT' in run_info.model_options:
            run_info.terrain_type = 'FLAT'
        elif {'ELEVATED', 'ELEV'} & set(run_info.model_options):
            run_info.terrain_type = 'ELEVATED'
        elif re.search(r'Receptors\s+on\s+FLAT\s+Terrain', self.content):
            run_info.terrain_type = 'FLAT'
        elif re.search(r'Receptors\s+on\s+ELEV', self.content, re.IGNORECASE):
            run_info.terrain_type = 'ELEVATED'

        for word in ('URBAN', 'RURAL'):
            if word in run_info.model_options:
                run_info.urban_option = word
                break

        # EPA SUM format: source/receptor counts from summary line
        # "This Run Includes: 1 Source(s); 1 Source Group(s); and 144 Receptor(s)"
        counts_match = re.search(
            r'This\s+Run\s+Includes:\s*(\d+)\s+Source\(s\).*?'
            r'and\s+(\d+)\s+Receptor\(s\)',
            self.content, re.DOTALL
        )
        if counts_match:
            run_info.num_sources = int(counts_match.group(1))
            run_info.num_receptors = int(counts_match.group(2))

        self.run_info = run_info
        return run_info

    def _parse_banner_and_setup(self, run_info: "ModelRunInfo") -> None:
        """Fill the run date, run time, averaging periods and met-data dates
        from what a real AERMOD ``.out`` prints.

        * The page banner (FORMAT 9028 of output.f HEADER) ends with the run
          date, ``MM/DD/YY``; the AERMET banner line ends with the run time.
        * inpsum.f FORMAT 9042/9043/9045/9143: ``**Model Calculates  3 Short
          Term Average(s) of:   1-HR   3-HR  24-HR`` and ``and Calculates
          PERIOD Averages`` (or ANNUAL, or ``PERIOD Averages Only``).
        * inpsum.f FORMAT 9038: ``METEOROLOGICAL DATA PROCESSED BETWEEN START
          DATE: 1993   5 21 20`` / ``AND END DATE: ...`` (year, month, day,
          hour). The dates are reported as ``YYYY/MM/DD``; the hour is
          not kept.

        AERMOD prints no job name, so ``jobname`` stays ``"Unknown"``.
        """
        date_match = re.search(
            r'\*\*\*\s*AERMOD\s*-\s*VERSION\s*\S+\s*\*\*\*.*?\*\*\*\s*(\d{2}/\d{2}/\d{2,4})\s*$',
            self.content, re.MULTILINE)
        if date_match:
            run_info.run_date = date_match.group(1)
        time_match = re.search(
            r'\*\*\*\s*AERMET\s*-\s*VERSION\s*\S+\s*\*\*\*.*?\*\*\*\s*(\d{2}:\d{2}:\d{2})\s*$',
            self.content, re.MULTILINE)
        if time_match:
            run_info.run_time = time_match.group(1)

        short = re.search(
            r'\*\*Model Calculates\s+\d+\s+Short Term Average\(s\)\s+of:(.*)', self.content)
        periods = short.group(1).split() if short else []
        long_term = re.search(
            r'(?:and\s+)?Calculates\s+(PERIOD|ANNUAL)\s+Averages', self.content)
        if long_term:
            periods.append(long_term.group(1))
        if periods:
            run_info.averaging_periods = periods

        dates = re.search(
            r'START DATE:\s*(\d{4})\s+(\d+)\s+(\d+)\s+(\d+)\s*\n\s*AND END DATE:\s*'
            r'(\d{4})\s+(\d+)\s+(\d+)\s+(\d+)', self.content)
        if dates:
            y1, m1, d1, _, y2, m2, d2, _ = (int(v) for v in dates.groups())
            run_info.start_date = f"{y1:04d}/{m1:02d}/{d1:02d}"
            run_info.end_date = f"{y2:04d}/{m2:02d}/{d2:02d}"

    def _parse_sources(self):
        """Extract source information from AERMOD's per-type sections
        (``*** POINT SOURCE DATA ***``, ``*** VOLUME SOURCE DATA ***``, ...),
        with columns: ID  NPART  EMISSION  X  Y  ELEV  [type-specific...]
        """
        self._parse_sources_epa()

        if self.run_info and self.sources:
            # Keep the larger count: a row that did not parse must not shrink
            # the "This Run Includes" figure.
            self.run_info.num_sources = max(len(self.sources), self.run_info.num_sources)

    def _parse_sources_epa(self):
        """Parse sources from EPA .out per-type sections.

        Each section header looks like ``*** POINT SOURCE DATA ***`` and
        has a table with column layout that varies by source type.  The
        common prefix columns are:
            SOURCE_ID  NPART  EMISSION_RATE  X  Y  BASE_ELEV  ...

        The source type is inferred from the section header.
        """
        # Map section header keywords to AERMOD source type names
        type_map = [
            (r'POINT SOURCE DATA', 'POINT'),
            (r'VOLUME SOURCE DATA', 'VOLUME'),
            (r'(?:AREA|AREAPOLY|AREACIRC) SOURCE DATA', 'AREA'),
            (r'LINE SOURCE DATA', 'LINE'),
            (r'RLINE/RLINEXT SOURCE DATA', 'RLINE'),
            (r'OPENPIT SOURCE DATA', 'OPENPIT'),
            (r'BUOYANT LINE SOURCE DATA', 'BUOYLINE'),
        ]

        for pattern, src_type in type_map:
            for match in re.finditer(
                rf'\*\*\*\s*{pattern}\s*\*\*\*(.*?)(?:\*\*\*|\Z)',
                self.content, re.DOTALL
            ):
                self._parse_epa_source_section(match.group(1), src_type)

    def _parse_epa_source_section(self, section_text: str, source_type: str):
        """Parse one EPA source data section.

        Data lines have the format::
            ID  NPART  EMISSION  X  Y  BASE_ELEV  [type-specific columns...]

        The separator line ``- - - -`` marks end of headers.
        """
        lines = section_text.strip().split('\n')
        data_started = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Separator line marks start of data
            if stripped.startswith('- - -'):
                data_started = True
                continue
            if not data_started:
                continue
            # Skip page header lines that appear mid-section
            if '*** AERMOD' in stripped or '*** AERMET' in stripped:
                break
            if 'MODELOPTs' in stripped or 'PAGE' in stripped:
                continue

            parts = stripped.split()
            if len(parts) < 6:
                continue

            try:
                source_id = parts[0]
                # parts[1] = NPART (number of particle categories)
                emission_str = parts[2]
                x = float(parts[3])
                y = float(parts[4])
                # inpsum.f writes "FLAT" for a source flagged FLAT in a
                # mixed FLAT/ELEV run.
                base_elev = 0.0 if parts[5].upper() == 'FLAT' else float(parts[5])

                source = SourceSummary(
                    source_id=source_id,
                    source_type=source_type,
                    x_coord=x,
                    y_coord=y,
                    base_elevation=base_elev,
                    emission_rate=fortran_float(emission_str),
                )

                # POINT sources have stack params after base_elev
                if source_type == 'POINT' and len(parts) >= 10:
                    source.stack_height = float(parts[6])
                    source.stack_temp = float(parts[7])
                    source.exit_velocity = float(parts[8])
                    source.stack_diameter = float(parts[9])

                self.sources.append(source)
            except (ValueError, IndexError):
                continue

    def _parse_receptors(self):
        """Extract receptor locations.

        AERMOD prints ``*** DISCRETE CARTESIAN RECEPTORS ***`` with
        parenthesized tuples ``( x, y, zelev, zhill, zflag );`` and
        ``*** GRIDDED RECEPTOR NETWORK SUMMARY ***`` sections (grid
        definitions, not individual receptors; the count comes from the
        header instead).
        """
        self._parse_receptors_epa()

        if self.run_info and self.receptors:
            self.run_info.num_receptors = max(
                len(self.receptors), self.run_info.num_receptors
            )

    def _parse_receptors_epa(self):
        """Parse receptors from EPA .out discrete receptor sections.

        EPA format uses parenthesized tuples, two per line::

            (   3500.0,  67750.0,  237.5,  239.3,    0.0);  (  3600.0, ...)

        Multiple section types are supported:
        - ``*** DISCRETE CARTESIAN RECEPTORS ***``
        - ``*** DISCRETE POLAR RECEPTORS ***``
        """
        # Match all discrete receptor sections
        for match in re.finditer(
            r'\*\*\*\s*DISCRETE\s+(CARTESIAN|POLAR)\s+RECEPTORS\s*\*\*\*'
            r'(.*?)(?:\*\*\*|\Z)',
            self.content, re.DOTALL
        ):
            section = match.group(2)
            if match.group(1).upper() == 'POLAR':
                self._parse_polar_receptors(section)
                continue
            # Extract parenthesized tuples: ( x, y, zelev, zhill, zflag )
            for tmatch in re.finditer(
                r'\(\s*([^)]+)\)', section
            ):
                values = tmatch.group(1).split(',')
                if len(values) >= 2:
                    try:
                        receptor = ReceptorInfo(
                            x_coord=float(values[0]),
                            y_coord=float(values[1]),
                            z_elev=float(values[2]) if len(values) > 2 else 0.0,
                            z_hill=float(values[3]) if len(values) > 3 else 0.0,
                            z_flag=float(values[4]) if len(values) > 4 else 0.0
                        )
                        self.receptors.append(receptor)
                    except (ValueError, IndexError):
                        continue

    def _parse_polar_receptors(self, section: str) -> None:
        """Discrete polar receptors, as absolute coordinates.

        inpsum.f (FORMAT 9047) prints each as ``SRCID: (range, radial,
        ZELEV, ZHILL, ZFLAG)`` relative to the origin source SRCID, the
        radial in degrees clockwise from north (DATAN2(XRMS, YRMS)). They
        are converted with that source's coordinates; one whose origin is
        not among the parsed sources cannot be, and is skipped with a
        warning.
        """
        origins = {s.source_id: s for s in self.sources}
        skipped = 0
        for tmatch in re.finditer(r'(\S+?)\s*:\s*\(\s*([^)]+)\)', section):
            values = tmatch.group(2).split(',')
            try:
                rng, radial = float(values[0]), float(values[1])
                rest = [float(v) for v in values[2:5]]
            except ValueError:
                continue  # the column-heading lines also look like this
            origin = origins.get(tmatch.group(1))
            if origin is None:
                skipped += 1
                continue
            angle = math.radians(radial)
            z_elev, z_hill, z_flag = [*rest, 0.0, 0.0, 0.0][:3]
            self.receptors.append(ReceptorInfo(
                x_coord=origin.x_coord + rng * math.sin(angle),
                y_coord=origin.y_coord + rng * math.cos(angle),
                z_elev=z_elev, z_hill=z_hill, z_flag=z_flag,
            ))
        if skipped:
            logger.warning(
                "%d discrete polar receptor(s) in %s name an origin source that "
                "was not parsed from the output; they are not listed.",
                skipped, self.output_file)

    def _parse_concentration_results(self):
        """Parse the results for every averaging period.

        An AERMOD ``.out`` file ends with its summary tables ("THE SUMMARY
        OF HIGHEST 1-HR RESULTS", "THE SUMMARY OF MAXIMUM PERIOD ( 96 HRS)
        RESULTS", ...), which are read by :meth:`_parse_summary_tables`.
        Concentration tables fill :attr:`concentrations`; deposition tables
        fill :attr:`deposition` instead. A file without summary tables has
        no results.
        """
        self._parse_summary_tables()

    def _parse_summary_tables(self) -> bool:
        """Read every summary table AERMOD printed; False if there are none.

        The tables are PRTSUM's and PRTPM25SUM's in AERMOD's output.f. Each
        starts with a heading (the averaging period), then a units line
        (FORMAT 9011: what is tabulated, of which pollutant, in which
        units) and a column heading that names the output type (``AVERAGE
        CONC``, ``TOTAL DEPO``, ``DRY DEPO`` or ``WET DEPO``). A table for
        several source groups can continue on the next page under the same
        heading; its rows are joined. The group ID is printed on a group's
        first row only.

        Short-term values carry AERMOD's calm/missing flag, which the
        earlier reading took for part of the number: the row was dropped,
        so maxima were wrong and a period whose values were all flagged
        disappeared.
        """
        sections: List[dict] = []
        current: Optional[dict] = None
        for line in self.content.splitlines():
            heading = _SUMMARY_HEADING.search(line)
            if heading:
                current = {"title": " ".join(heading.group(1).split()), "rows": [],
                           "type": None, "units": None, "group": None}
                current["period"] = _summary_period(current["title"])
                sections.append(current)
                continue
            if current is None:
                continue
            multiyear = _MULTIYEAR_LINE.match(line)
            if multiyear and not current["rows"]:
                current["title"] += "; " + " ".join(multiyear.group(1).split())
                continue
            units = _UNITS_LINE.match(line)
            if units:
                current["units"] = units.group(3).strip()
                if units.group(1) == "CONC":
                    current["type"] = "CONC"
                continue
            if current["type"] in (None, "CONC") and "GROUP ID" in line.upper():
                for pattern, kind in _OUTPUT_TYPE_HEADINGS:
                    if pattern.search(line.upper()):
                        current["type"] = kind
                        break
                continue
            if "VALUE IS" in line.upper():
                row = self._summary_row(line, current)
                if row is not None:
                    current["rows"].append(row)
                continue
            if "***" in line and not _PAGE_HEADER.search(line):
                # "*** RECEPTOR TYPES", the message summary, a new section.
                current = None

        if not sections:
            return False

        # A table continued on a later page repeats its heading.
        merged: Dict[tuple, dict] = {}
        for sec in sections:
            if sec["period"] is None:
                continue
            key = (sec["type"] or "CONC", sec["period"], sec["title"])
            if key in merged:
                merged[key]["rows"].extend(sec["rows"])
            else:
                merged[key] = sec
        for (kind, period, title), sec in merged.items():
            if not sec["rows"]:
                continue
            result = self._summary_result(sec["rows"], period, kind, title, sec["units"])
            self.summaries.append(result)
            by_period = (self.concentrations if kind == "CONC"
                         else self.deposition.setdefault(kind, {}))
            # A period's entry is its table of highest values. AERMOD's
            # design-value tables (the 8TH-HIGHEST 24-HR PM2.5 average over
            # N years, say) are used only for a period that has no other
            # table, when RECTABLE asked for that rank alone.
            kept = by_period.get(period)
            if kept is None or (not _is_maximum_table(kept.title)
                                and _is_maximum_table(title)):
                by_period[period] = result
        return True

    @staticmethod
    def _summary_row(line: str, section: dict) -> Optional[dict]:
        match = _SUMMARY_ROW.search(line)
        if match is None:
            return None
        value_text = match.group("value")
        value = _float_or_nan(value_text)
        # A value AERMOD could not fit in its field prints as asterisks;
        # anything else that is not a number is not a value.
        if value != value and not set(value_text) <= {"*"}:
            return None
        coords = [c.strip() for c in match.group("coords").split(",")]
        if len(coords) < 2:
            return None
        x, y = _float_or_nan(coords[0]), _float_or_nan(coords[1])
        if x != x or y != y:
            return None
        extra = [_float_or_nan(c) for c in coords[2:5]] + [0.0] * 3
        prefix = [t for t in match.group("prefix").split() if t.upper() not in ("HIGH", "THE")]
        if prefix:
            section["group"] = prefix[0]
        date = match.group("date")
        return {
            "group": section["group"],
            "rank": int(match.group("rank")[:-2]),
            "concentration": value,
            "value_text": value_text,
            "flag": (match.group("flag") or "").lower(),
            "date": date,
            "x": x,
            "y": y,
            "zelev": extra[0],
            "zhill": extra[1],
            "zflag": extra[2],
            "receptor_type": match.group("rtype"),
            "grid_id": match.group("grid"),
        }

    @staticmethod
    def _summary_result(rows: List[dict], period: str, kind: str, title: str,
                        units: Optional[str]) -> ConcentrationResult:
        df = pd.DataFrame(rows)
        i = _max_index(df)
        if i is None:
            max_value, max_location = float("nan"), (float("nan"), float("nan"))
        else:
            max_value = df.loc[i, "concentration"]
            max_location = (df.loc[i, "x"], df.loc[i, "y"])
        if units is None:
            label = "ug/m^3" if kind == "CONC" else "g/m^2"
        else:
            label = _UNIT_LABELS.get(units.upper(), units)
        return ConcentrationResult(
            averaging_period=period, data=df, max_value=max_value,
            max_location=max_location, units=label, output_type=kind, title=title,
        )

@dataclass
class AERMODResults:
    """
    Complete AERMOD results

    Contains all parsed information from an AERMOD output file.
    """
    run_info: ModelRunInfo
    sources: List[SourceSummary]
    receptors: List[ReceptorInfo]
    concentrations: Dict[str, ConcentrationResult]
    output_file: str
    #: Deposition tables of a DEPOS/DDEP/WDEP run, by output type and period.
    deposition: Dict[str, Dict[str, ConcentrationResult]] = field(default_factory=dict)
    #: Every summary table AERMOD printed, in the order of the file.
    summaries: List[ConcentrationResult] = field(default_factory=list)

    @classmethod
    def from_file(cls, output_file: Union[str, Path]) -> 'AERMODResults':
        """
        Parse AERMOD output file

        Args:
            output_file: Path to AERMOD .out file

        Returns:
            AERMODResults object
        """
        parser = AERMODOutputParser(output_file)
        return parser.parse()

    def get_concentrations(self, averaging_period: str = 'ANNUAL') -> Optional[pd.DataFrame]:
        """
        Get the summary-table rows for one averaging period

        These are the rows of AERMOD's summary tables in the .out file (the
        highest values, typically ten receptors), not the value at every
        receptor. For a map or contour of the whole grid, request a PLOTFILE
        (``OutputPathway.period_plot_files``) and read it with
        :func:`pyaermod.aermod_outputs.read_plotfile`, or pass it to
        :meth:`pyaermod.visualization.AERMODVisualizer.plot_contours` as
        ``plotfile``.

        Args:
            averaging_period: Averaging period (e.g., 'ANNUAL', '24HR', '1HR')

        Returns:
            DataFrame with x, y, concentration columns, or None if period
            not found.
        """
        if averaging_period not in self.concentrations:
            return None

        return self.concentrations[averaging_period].data.copy()

    def get_max_concentration(self, averaging_period: str = 'ANNUAL') -> Optional[Dict]:
        """
        Get maximum concentration and its location

        Args:
            averaging_period: Averaging period

        Returns:
            Dictionary with 'value', 'x', 'y', 'units', or None if period
            not found.
        """
        if averaging_period not in self.concentrations:
            return None

        result = self.concentrations[averaging_period]
        return {
            'value': result.max_value,
            'x': result.max_location[0],
            'y': result.max_location[1],
            'units': result.units,
            'averaging_period': averaging_period
        }

    def get_concentration_at_point(self, x: float, y: float,
                                   averaging_period: str = 'ANNUAL',
                                   tolerance: float = 1.0,
                                   zflag: Optional[float] = None) -> Optional[float]:
        """
        Get concentration at specific point (within tolerance)

        A flagpole run (``CO FLAGPOLE`` with one network per height) has
        several receptors at the same (x, y), one per flagpole height. Pass
        ``zflag`` to pick one height.

        Args:
            x: X coordinate
            y: Y coordinate
            averaging_period: Averaging period
            tolerance: Distance tolerance for matching receptors, and for
                matching ``zflag`` when it is given
            zflag: Flagpole height of the receptor. When it is None and
                receptors at several heights lie within ``tolerance``, the
                first match is returned, as before, with a
                :class:`UserWarning` naming the heights.

        Returns:
            Concentration value or None if no receptor found
        """
        df = self.get_concentrations(averaging_period)
        if df is None:
            return None

        has_heights = 'zflag' in df.columns
        if zflag is not None and has_heights:
            df = df[(df['zflag'] - zflag).abs() <= tolerance]
            if df.empty:
                return None

        # Find closest receptor
        distances = np.sqrt((df['x'] - x)**2 + (df['y'] - y)**2)
        if distances.empty:
            return None
        min_dist_idx = distances.idxmin()

        if distances[min_dist_idx] <= tolerance:
            if zflag is None and has_heights:
                heights = sorted(df.loc[distances <= tolerance, 'zflag'].dropna().unique())
                if len(heights) > 1:
                    warnings.warn(
                        f"the receptor near ({x}, {y}) has values at several flagpole "
                        f"heights ({', '.join(str(float(z)) for z in heights)}); "
                        "pass zflag= to choose one",
                        UserWarning, stacklevel=2)
            return df.loc[min_dist_idx, 'concentration']

        return None

    def get_sources_dataframe(self) -> pd.DataFrame:
        """Get sources as DataFrame"""
        if not self.sources:
            return pd.DataFrame()

        data = []
        for source in self.sources:
            row = {
                'source_id': source.source_id,
                'source_type': source.source_type,
                'x': source.x_coord,
                'y': source.y_coord,
                'base_elevation': source.base_elevation
            }

            if source.stack_height is not None:
                row['stack_height'] = source.stack_height
            if source.emission_rate is not None:
                row['emission_rate'] = source.emission_rate

            data.append(row)

        return pd.DataFrame(data)

    def get_receptors_dataframe(self) -> pd.DataFrame:
        """Get receptors as DataFrame"""
        if not self.receptors:
            return pd.DataFrame()

        data = [{
            'x': r.x_coord,
            'y': r.y_coord,
            'z_elev': r.z_elev,
            'z_hill': r.z_hill,
            'z_flag': r.z_flag
        } for r in self.receptors]

        return pd.DataFrame(data)

    def summary(self) -> str:
        """Generate a text summary of results"""
        lines = []
        lines.append("=" * 70)
        lines.append("AERMOD Results Summary")
        lines.append("=" * 70)
        lines.append(f"Version: {self.run_info.version}")
        if self.run_info.jobname != "Unknown" or not self.run_info.title:
            lines.append(f"Job: {self.run_info.jobname}")
        if self.run_info.title:
            lines.append(f"Title: {self.run_info.title}")

        if self.run_info.run_date:
            lines.append(f"Run Date: {self.run_info.run_date}")

        lines.append(f"Pollutant: {self.run_info.pollutant_id or 'Unknown'}")
        lines.append(f"Terrain: {self.run_info.terrain_type or 'Unknown'}")
        lines.append("")
        # AERMOD's .out lists receptors only with RE pathway echo tables;
        # the "This Run Includes" counts are always there.
        lines.append(f"Sources: {len(self.sources) or self.run_info.num_sources}")
        lines.append(f"Receptors: {len(self.receptors) or self.run_info.num_receptors}")
        lines.append("")
        lines.append("Concentration Results:")

        for period in sorted(self.concentrations.keys()):
            result = self.concentrations[period]
            lines.append(f"  {period}:")
            lines.append(f"    Maximum: {result.max_value:.4f} {result.units}")
            lines.append(f"    Location: ({result.max_location[0]:.2f}, {result.max_location[1]:.2f})")
            lines.append(f"    Summary rows: {len(result.data)}")

        lines.append("=" * 70)
        return "\n".join(lines)

    def export_to_csv(self, output_dir: Union[str, Path], prefix: str = "aermod"):
        """
        Export all results to CSV files

        Args:
            output_dir: Directory for output files
            prefix: Prefix for filenames
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Export sources
        if self.sources:
            sources_df = self.get_sources_dataframe()
            sources_df.to_csv(output_path / f"{prefix}_sources.csv", index=False)

        # Export receptors
        if self.receptors:
            receptors_df = self.get_receptors_dataframe()
            receptors_df.to_csv(output_path / f"{prefix}_receptors.csv", index=False)

        # Export concentrations for each period
        for period, result in self.concentrations.items():
            filename = f"{prefix}_concentrations_{period}.csv"
            result.data.to_csv(output_path / filename, index=False)

        logger.info("Exported results to %s", output_path)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def parse_aermod_output(output_file: Union[str, Path]) -> AERMODResults:
    """
    Parse an AERMOD output file

    Args:
        output_file: Path to .out file

    Returns:
        AERMODResults object
    """
    return AERMODResults.from_file(output_file)


def quick_summary(output_file: Union[str, Path]) -> str:
    """
    Quick summary of AERMOD results

    Args:
        output_file: Path to .out file

    Returns:
        Text summary
    """
    results = parse_aermod_output(output_file)
    return results.summary()
