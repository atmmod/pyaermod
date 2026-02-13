"""
PyAERMOD Output File Parser

Parses AERMOD output files (.out) and converts results to pandas DataFrames.
Based on AERMOD version 24142 output format specifications.
"""

import contextlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


@dataclass
class ModelRunInfo:
    """Metadata about the AERMOD run"""
    version: str
    jobname: str
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
    """Concentration results for a specific averaging period"""
    averaging_period: str
    data: pd.DataFrame  # Contains x, y, concentration, rank, etc.
    max_value: float
    max_location: Tuple[float, float]
    units: str = "ug/m^3"


class AERMODOutputParser:
    """
    Parser for AERMOD output files

    Extracts run information, source data, receptor data, and concentration results.
    """

    def __init__(self, output_file: Union[str, Path]):
        """
        Initialize parser with output file

        Args:
            output_file: Path to AERMOD .out file
        """
        self.output_file = Path(output_file)

        if not self.output_file.exists():
            raise FileNotFoundError(f"Output file not found: {output_file}")

        # Read entire file
        with open(self.output_file, encoding='utf-8', errors='ignore') as f:
            self.content = f.read()

        # Parsed data
        self.run_info: Optional[ModelRunInfo] = None
        self.sources: List[SourceSummary] = []
        self.receptors: List[ReceptorInfo] = []
        self.concentrations: Dict[str, ConcentrationResult] = {}

    def parse(self) -> 'AERMODResults':
        """
        Parse the output file and return results object

        Returns:
            AERMODResults object with all parsed data
        """
        self._parse_header()
        self._parse_sources()
        self._parse_receptors()
        self._parse_concentration_results()

        return AERMODResults(
            run_info=self.run_info,
            sources=self.sources,
            receptors=self.receptors,
            concentrations=self.concentrations,
            output_file=str(self.output_file)
        )

    def _parse_header(self):
        """Extract run information from header"""
        run_info = ModelRunInfo(
            version="Unknown",
            jobname="Unknown"
        )

        # AERMOD version
        version_match = re.search(r'AERMOD\s*-\s*VERSION\s*[:\s]*(\d+)', self.content)
        if version_match:
            run_info.version = version_match.group(1)

        # Job name
        jobname_match = re.search(r'Jobname:\s*(.+)', self.content)
        if jobname_match:
            run_info.jobname = jobname_match.group(1).strip()

        # Run date and time
        date_match = re.search(r'Run Date:\s*(\d{2}-\d{2}-\d{2})', self.content)
        if date_match:
            run_info.run_date = date_match.group(1)

        time_match = re.search(r'Run Time:\s*(\d{2}:\d{2}:\d{2})', self.content)
        if time_match:
            run_info.run_time = time_match.group(1)

        # Model options
        options_section = re.search(
            r'\*\*\s*Model Setup Options Selected\s*\*\*(.*?)\n\n',
            self.content,
            re.DOTALL
        )
        if options_section and options_section.group(1):
            option_lines = options_section.group(1).strip().split('\n')
            for line in option_lines:
                if '--' in line:
                    option = line.split('--')[0].strip()
                    run_info.model_options.append(option)

        # Pollutant ID — try standard format first, then EPA SUM format
        pollutant_match = re.search(r'Pollutant/Gas ID:\s*(\w+)', self.content)
        if pollutant_match:
            run_info.pollutant_id = pollutant_match.group(1)
        else:
            epa_poll_match = re.search(
                r'Pollutant\s+Type\s+of:\s*(\S+)', self.content
            )
            if epa_poll_match:
                run_info.pollutant_id = epa_poll_match.group(1).strip()

        # Averaging periods
        avertime_match = re.search(r'Averaging Time Period.*?:\s*(.+)', self.content)
        if avertime_match:
            periods_str = avertime_match.group(1).strip()
            # Parse periods like "1-HR", "24-HR", "ANNUAL"
            run_info.averaging_periods = [p.strip() for p in periods_str.split()]

        # Terrain type
        if 'FLAT' in run_info.model_options:
            run_info.terrain_type = 'FLAT'
        elif 'ELEVATED' in run_info.model_options:
            run_info.terrain_type = 'ELEVATED'

        # Modeling period
        period_match = re.search(
            r'STARTING DATE:\s*(\d{2}/\d{2}/\d{2,4}).*?ENDING DATE:\s*(\d{2}/\d{2}/\d{2,4})',
            self.content,
            re.DOTALL
        )
        if period_match:
            run_info.start_date = period_match.group(1)
            run_info.end_date = period_match.group(2)

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

    def _parse_sources(self):
        """Extract source information"""
        # Find source summary section
        sources_section = re.search(
            r'\*\*\*\s*SOURCE LOCATIONS\s*\*\*\*(.*?)(?:\*\*\*|\Z)',
            self.content,
            re.DOTALL
        )

        if not sources_section or not sources_section.group(1):
            return

        lines = sources_section.group(1).strip().split('\n')

        # Skip header lines
        data_started = False
        for line in lines:
            if not line.strip():
                continue

            # Look for data lines (typically start with source ID)
            if not data_started:
                if 'SOURCE' in line and 'TYPE' in line:
                    data_started = True
                continue

            # Parse source line
            parts = line.split()
            if len(parts) >= 5:
                try:
                    source = SourceSummary(
                        source_id=parts[0],
                        source_type=parts[1],
                        x_coord=float(parts[2]),
                        y_coord=float(parts[3]),
                        base_elevation=float(parts[4])
                    )

                    # Additional parameters if available
                    if len(parts) > 5 and parts[1] == 'POINT' and len(parts) >= 10:
                        source.stack_height = float(parts[5])
                        source.stack_temp = float(parts[6])
                        source.exit_velocity = float(parts[7])
                        source.stack_diameter = float(parts[8])
                        source.emission_rate = float(parts[9])

                    self.sources.append(source)
                except (ValueError, IndexError):
                    continue

        if self.run_info:
            self.run_info.num_sources = len(self.sources)

    def _parse_receptors(self):
        """Extract receptor locations"""
        # Find receptor section
        receptor_section = re.search(
            r'\*\*\*\s*RECEPTOR LOCATIONS\s*\*\*\*(.*?)(?:\*\*\*|\Z)',
            self.content,
            re.DOTALL
        )

        if not receptor_section or not receptor_section.group(1):
            return

        lines = receptor_section.group(1).strip().split('\n')

        # Skip header
        data_started = False
        for line in lines:
            if not line.strip():
                continue

            if not data_started:
                if 'X-COORD' in line or 'RECEPTOR' in line:
                    data_started = True
                continue

            # Parse receptor line
            parts = line.split()
            if len(parts) >= 2:
                try:
                    receptor = ReceptorInfo(
                        x_coord=float(parts[0]),
                        y_coord=float(parts[1]),
                        z_elev=float(parts[2]) if len(parts) > 2 else 0.0,
                        z_hill=float(parts[3]) if len(parts) > 3 else 0.0,
                        z_flag=float(parts[4]) if len(parts) > 4 else 0.0
                    )
                    self.receptors.append(receptor)
                except (ValueError, IndexError):
                    continue

        if self.run_info:
            self.run_info.num_receptors = len(self.receptors)

    def _parse_concentration_results(self):
        """Parse concentration results for all averaging periods"""

        # Common averaging period patterns — matches both standard format
        # (*** ANNUAL RESULTS ***) and EPA SUM format
        # (*** THE SUMMARY OF HIGHEST 1-HR RESULTS ***)
        # (*** THE SUMMARY OF MAXIMUM PERIOD ( 96 HRS) RESULTS ***)
        period_patterns = [
            (r'ANNUAL', 'ANNUAL'),
            (r'24-HOUR|24HR|24-HR', '24HR'),
            (r'1-HOUR|1HR|1-HR', '1HR'),
            (r'3-HOUR|3HR|3-HR', '3HR'),
            (r'8-HOUR|8HR|8-HR', '8HR'),
            (r'MONTH', 'MONTH'),
            (r'PERIOD', 'PERIOD')
        ]

        for pattern, period_name in period_patterns:
            result = self._parse_concentration_table(pattern, period_name)
            if result is not None:
                self.concentrations[period_name] = result

    def _parse_concentration_table(self, pattern: str, period_name: str) -> Optional[ConcentrationResult]:
        """Parse concentration table for specific averaging period"""

        # Find the results section — try two section header formats:
        # Standard: *** ANNUAL RESULTS ***
        # EPA SUM:  *** THE SUMMARY OF HIGHEST 1-HR RESULTS ***
        #           *** THE SUMMARY OF MAXIMUM PERIOD ( 96 HRS) RESULTS ***
        #
        # For EPA SUM, the section header is on one line, so we match
        # [^\n]* instead of .*? to avoid spanning across *** boundaries.
        section_patterns = [
            rf'\*\*\*[^\n]*{pattern}[^\n]*RESULTS[^\n]*\*\*\*(.*?)(?:\*\*\*|\Z)',
            rf'\*\*\*.*?{pattern}.*?RESULTS.*?\*\*\*(.*?)(?:\*\*\*|\Z)',
        ]

        table_text = None
        for sp in section_patterns:
            section_match = re.search(sp, self.content, re.DOTALL | re.IGNORECASE)
            if section_match and section_match.group(1) and len(section_match.group(1).strip()) > 10:
                table_text = section_match.group(1)
                break

        if table_text is None:
            return None

        # Try EPA SUM "VALUE IS X AT (x, y, ...)" format first
        epa_result = self._parse_epa_value_is_format(table_text, period_name)
        if epa_result is not None:
            return epa_result

        # Fall back to standard tabular format (x y concentration rows)
        data_rows = []
        lines = table_text.split('\n')

        # Look for data rows (typically have numeric coordinates)
        for line in lines:
            if not line.strip():
                continue

            parts = line.split()

            # Check if line looks like data (starts with coordinate)
            if len(parts) >= 3:
                try:
                    x = float(parts[0])
                    y = float(parts[1])
                    conc = float(parts[2])

                    row = {
                        'x': x,
                        'y': y,
                        'concentration': conc
                    }

                    # Additional fields if available
                    if len(parts) > 3:
                        # Might include rank, contributing sources, etc.
                        with contextlib.suppress(ValueError):
                            row['rank'] = int(parts[3])

                    data_rows.append(row)

                except (ValueError, IndexError):
                    continue

        if not data_rows:
            return None

        # Create DataFrame
        df = pd.DataFrame(data_rows)

        # Find maximum value
        max_idx = df['concentration'].idxmax()
        max_value = df.loc[max_idx, 'concentration']
        max_x = df.loc[max_idx, 'x']
        max_y = df.loc[max_idx, 'y']

        return ConcentrationResult(
            averaging_period=period_name,
            data=df,
            max_value=max_value,
            max_location=(max_x, max_y)
        )

    @staticmethod
    def _parse_epa_value_is_format(
        table_text: str, period_name: str
    ) -> Optional[ConcentrationResult]:
        """
        Parse EPA SUM format concentration tables.

        EPA SUM files list results in two formats::

            PERIOD results:
              ALL   1ST HIGHEST VALUE IS  24.85173 AT (  433.01,  -250.00,  0.00,  0.00,  0.00)

            Short-term (1-HR, etc.) results:
              ALL   HIGH  1ST HIGH VALUE IS  753.65603  ON 88030111: AT (  303.11,  -175.00, ...)

        Parameters
        ----------
        table_text : str
            Text of the concentration results section.
        period_name : str
            Name for the averaging period.

        Returns
        -------
        ConcentrationResult or None
            Parsed result, or *None* if no "VALUE IS" entries found.
        """
        # Match both formats: "VALUE IS <conc> AT (...)" and
        # "VALUE IS <conc> ON <date>: AT (...)"
        value_pattern = re.compile(
            r'VALUE\s+IS\s+(\S+)\s+(?:ON\s+\S+:\s+)?AT\s*\(\s*'
            r'([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)'
        )

        data_rows = []
        for match in value_pattern.finditer(table_text):
            try:
                conc = float(match.group(1))
                x = float(match.group(2).strip())
                y = float(match.group(3).strip())
                data_rows.append({
                    'x': x,
                    'y': y,
                    'concentration': conc,
                })
            except ValueError:
                continue

        if not data_rows:
            return None

        df = pd.DataFrame(data_rows)
        max_idx = df['concentration'].idxmax()
        max_value = df.loc[max_idx, 'concentration']
        max_x = df.loc[max_idx, 'x']
        max_y = df.loc[max_idx, 'y']

        return ConcentrationResult(
            averaging_period=period_name,
            data=df,
            max_value=max_value,
            max_location=(max_x, max_y)
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

    def get_concentrations(self, averaging_period: str = 'ANNUAL') -> pd.DataFrame:
        """
        Get concentration DataFrame for specific averaging period

        Args:
            averaging_period: Averaging period (e.g., 'ANNUAL', '24HR', '1HR')

        Returns:
            DataFrame with x, y, concentration columns
        """
        if averaging_period not in self.concentrations:
            available = ', '.join(self.concentrations.keys())
            raise ValueError(
                f"Averaging period '{averaging_period}' not found. "
                f"Available periods: {available}"
            )

        return self.concentrations[averaging_period].data.copy()

    def get_max_concentration(self, averaging_period: str = 'ANNUAL') -> Dict:
        """
        Get maximum concentration and its location

        Args:
            averaging_period: Averaging period

        Returns:
            Dictionary with 'value', 'x', 'y', 'units'
        """
        if averaging_period not in self.concentrations:
            raise ValueError(f"Averaging period '{averaging_period}' not found")

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
                                   tolerance: float = 1.0) -> Optional[float]:
        """
        Get concentration at specific point (within tolerance)

        Args:
            x: X coordinate
            y: Y coordinate
            averaging_period: Averaging period
            tolerance: Distance tolerance for matching receptors

        Returns:
            Concentration value or None if no receptor found
        """
        df = self.get_concentrations(averaging_period)

        # Find closest receptor
        distances = np.sqrt((df['x'] - x)**2 + (df['y'] - y)**2)
        min_dist_idx = distances.idxmin()

        if distances[min_dist_idx] <= tolerance:
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
        lines.append(f"Job: {self.run_info.jobname}")

        if self.run_info.run_date:
            lines.append(f"Run Date: {self.run_info.run_date}")

        lines.append(f"Pollutant: {self.run_info.pollutant_id or 'Unknown'}")
        lines.append(f"Terrain: {self.run_info.terrain_type or 'Unknown'}")
        lines.append("")
        lines.append(f"Sources: {len(self.sources)}")
        lines.append(f"Receptors: {len(self.receptors)}")
        lines.append("")
        lines.append("Concentration Results:")

        for period in sorted(self.concentrations.keys()):
            result = self.concentrations[period]
            lines.append(f"  {period}:")
            lines.append(f"    Maximum: {result.max_value:.4f} {result.units}")
            lines.append(f"    Location: ({result.max_location[0]:.2f}, {result.max_location[1]:.2f})")
            lines.append(f"    Points: {len(result.data)}")

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

        print(f"Exported results to {output_path}")


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


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Parse file from command line
        output_file = sys.argv[1]

        print(f"Parsing: {output_file}\n")

        results = parse_aermod_output(output_file)
        print(results.summary())

        # Show first few concentration values
        if results.concentrations:
            period = next(iter(results.concentrations.keys()))
            df = results.get_concentrations(period)
            print(f"\nFirst 10 {period} concentrations:")
            print(df.head(10))
    else:
        print("PyAERMOD Output Parser")
        print("Usage: python -m pyaermod.output_parser <output_file.out>")
        print("\nOr import and use:")
        print("  from pyaermod.output_parser import parse_aermod_output")
        print("  results = parse_aermod_output('myrun.out')")
        print("  df = results.get_concentrations('ANNUAL')")
