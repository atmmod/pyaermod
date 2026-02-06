"""
PyAERMOD AERMET Input Generator

Generates AERMET input files for meteorological data preprocessing.
AERMET is the EPA's meteorological preprocessor for AERMOD.

Processing stages:
1. Stage 1: Extract and QA/QC observational data
2. Stage 2: Merge surface and upper air data
3. Stage 3: Calculate boundary layer parameters
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class AERMETStation:
    """Surface meteorological station information"""
    station_id: str
    station_name: str
    latitude: float  # decimal degrees
    longitude: float  # decimal degrees
    time_zone: int  # UTC offset (e.g., -5 for EST)

    # Optional parameters
    elevation: Optional[float] = None  # meters
    anemometer_height: float = 10.0  # meters


@dataclass
class UpperAirStation:
    """Upper air (radiosonde) station information"""
    station_id: str
    station_name: str
    latitude: float
    longitude: float


@dataclass
class AERMETStage1:
    """
    AERMET Stage 1: Extract and QA/QC observational data

    Reads raw meteorological data and performs quality assurance.
    """

    # Job control
    job_id: str = "STAGE1"
    messages: int = 2  # Message level (1=few, 2=normal, 3=verbose)

    # Surface data
    surface_station: Optional[AERMETStation] = None
    surface_data_file: Optional[str] = None
    surface_format: str = "ISHD"  # or "HUSWO", "SCRAM", "SAMSON"

    # Upper air data
    upper_air_station: Optional[UpperAirStation] = None
    upper_air_data_file: Optional[str] = None

    # Date range
    start_date: str = "2020/01/01"  # YYYY/MM/DD
    end_date: str = "2020/12/31"

    # Output
    output_file: str = "stage1.out"
    extract_file: str = "stage1.ext"
    qa_file: str = "stage1.qa"

    def to_aermet_input(self) -> str:
        """Generate AERMET Stage 1 input file"""
        lines = []

        # Header
        lines.append("** AERMET Stage 1 Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway
        lines.append("JOB")
        lines.append(f"   REPORT     {self.output_file}")
        lines.append(f"   MESSAGES   {self.messages}")
        lines.append("")

        # UPPERAIR pathway
        if self.upper_air_station and self.upper_air_data_file:
            lines.append("UPPERAIR")
            lines.append(f"   DATA       {self.upper_air_data_file} FSL")
            lines.append(f"   EXTRACT    {self.extract_file.replace('.ext', '_ua.ext')}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
            lines.append("")

        # SURFACE pathway
        if self.surface_station and self.surface_data_file:
            lines.append("SURFACE")
            lines.append(f"   DATA       {self.surface_data_file} {self.surface_format}")
            lines.append(f"   EXTRACT    {self.extract_file}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")

            # Station parameters
            if self.surface_station.anemometer_height:
                lines.append(f"   ANEMHGT    {self.surface_station.anemometer_height:.1f}")

            lines.append(f"   LOCATION   {self.surface_station.station_id} " +
                        f"{self.surface_station.latitude:.4f} " +
                        f"{self.surface_station.longitude:.4f} {self.surface_station.time_zone}")

            if self.surface_station.elevation:
                lines.append(f"   ELEVATION  {self.surface_station.elevation:.1f}")

            lines.append("")

        return "\n".join(lines)


@dataclass
class AERMETStage2:
    """
    AERMET Stage 2: Merge surface and upper air data

    Combines Stage 1 outputs into merged file.
    """

    # Job control
    job_id: str = "STAGE2"
    messages: int = 2

    # Input files from Stage 1
    surface_extract: str = "stage1.ext"
    upper_air_extract: Optional[str] = None

    # Date range
    start_date: str = "2020/01/01"
    end_date: str = "2020/12/31"

    # Output
    output_file: str = "stage2.out"
    merge_file: str = "stage2.mrg"

    def to_aermet_input(self) -> str:
        """Generate AERMET Stage 2 input file"""
        lines = []

        # Header
        lines.append("** AERMET Stage 2 Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway
        lines.append("JOB")
        lines.append(f"   REPORT     {self.output_file}")
        lines.append(f"   MESSAGES   {self.messages}")
        lines.append("")

        # UPPERAIR pathway
        if self.upper_air_extract:
            lines.append("UPPERAIR")
            lines.append(f"   INPUT      {self.upper_air_extract}")
            lines.append("")

        # SURFACE pathway
        lines.append("SURFACE")
        lines.append(f"   INPUT      {self.surface_extract}")
        lines.append("")

        # MERGE pathway
        lines.append("MERGE")
        lines.append(f"   OUTPUT     {self.merge_file}")
        lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
        lines.append("")

        return "\n".join(lines)


@dataclass
class AERMETStage3:
    """
    AERMET Stage 3: Calculate boundary layer parameters

    Produces final AERMOD-ready meteorology files (.sfc and .pfl).
    """

    # Job control
    job_id: str = "STAGE3"
    messages: int = 2

    # Input from Stage 2
    merge_file: str = "stage2.mrg"

    # Site characteristics
    station: Optional[AERMETStation] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    time_zone: Optional[int] = None

    # Surface characteristics
    freq_sect: List[float] = field(default_factory=lambda: [0.0])  # Wind direction sectors
    site_char: List[str] = field(default_factory=list)  # Monthly surface characteristics

    # Albedo, Bowen ratio, roughness length (12 months)
    albedo: List[float] = field(default_factory=lambda: [0.15] * 12)
    bowen: List[float] = field(default_factory=lambda: [1.0] * 12)
    roughness: List[float] = field(default_factory=lambda: [0.1] * 12)

    # Date range
    start_date: str = "2020/01/01"
    end_date: str = "2020/12/31"

    # Output files
    output_file: str = "stage3.out"
    surface_file: str = "aermod.sfc"
    profile_file: str = "aermod.pfl"

    def to_aermet_input(self) -> str:
        """Generate AERMET Stage 3 input file"""
        lines = []

        # Header
        lines.append("** AERMET Stage 3 Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway
        lines.append("JOB")
        lines.append(f"   REPORT     {self.output_file}")
        lines.append(f"   MESSAGES   {self.messages}")
        lines.append("")

        # SURFACE pathway
        lines.append("SURFACE")
        lines.append(f"   INPUT      {self.merge_file}")
        lines.append("")

        # METPREP pathway
        lines.append("METPREP")
        lines.append(f"   OUTPUT     {self.surface_file}")
        lines.append(f"   PROFILE    {self.profile_file}")
        lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")

        # Location
        if self.station:
            lines.append(f"   LOCATION   {self.station.station_id} " +
                        f"{self.station.latitude:.4f} " +
                        f"{self.station.longitude:.4f} {self.station.time_zone}")
        elif self.latitude and self.longitude and self.time_zone:
            lines.append(f"   LOCATION   SITE {self.latitude:.4f} " +
                        f"{self.longitude:.4f} {self.time_zone}")

        # Surface characteristics
        if self.freq_sect:
            freq_str = " ".join(f"{f:.1f}" for f in self.freq_sect)
            lines.append(f"   FREQ_SECT  {freq_str}")

        # Monthly parameters (Albedo, Bowen, Roughness)
        if len(self.albedo) == 12:
            albedo_str = " ".join(f"{a:.2f}" for a in self.albedo)
            lines.append(f"   ALBEDO     {albedo_str}")

        if len(self.bowen) == 12:
            bowen_str = " ".join(f"{b:.2f}" for b in self.bowen)
            lines.append(f"   BOWEN      {bowen_str}")

        if len(self.roughness) == 12:
            rough_str = " ".join(f"{r:.3f}" for r in self.roughness)
            lines.append(f"   ROUGHNESS  {rough_str}")

        lines.append("")

        return "\n".join(lines)


def write_aermet_runfile(stage: int, input_file: str, output_path: str = "."):
    """
    Create a simple AERMET run script

    Args:
        stage: AERMET stage (1, 2, or 3)
        input_file: Path to input file
        output_path: Directory for outputs
    """
    script = f"""#!/bin/bash
# AERMET Stage {stage} Run Script

# Set paths
AERMET_EXE="aermet"
INPUT_FILE="{input_file}"
OUTPUT_PATH="{output_path}"

# Create output directory
mkdir -p $OUTPUT_PATH

# Run AERMET
cd $OUTPUT_PATH
$AERMET_EXE < ../$INPUT_FILE

echo "AERMET Stage {stage} complete"
"""

    script_file = f"run_aermet_stage{stage}.sh"
    with open(script_file, 'w') as f:
        f.write(script)

    # Make executable
    import os
    os.chmod(script_file, 0o755)

    return script_file


# Example usage
if __name__ == "__main__":
    print("PyAERMOD AERMET Input Generator")
    print("=" * 70)
    print()

    # Example: Create Stage 3 input (most common use case)
    station = AERMETStation(
        station_id="KORD",
        station_name="Chicago O'Hare",
        latitude=41.98,
        longitude=-87.90,
        time_zone=-6,
        elevation=200.0,
        anemometer_height=10.0
    )

    # Typical values for mixed urban/suburban area
    stage3 = AERMETStage3(
        job_id="EXAMPLE_STAGE3",
        merge_file="stage2.mrg",
        station=station,
        # Seasonal surface characteristics
        albedo=[0.50, 0.50, 0.40, 0.20, 0.15, 0.15, 0.15, 0.15, 0.20, 0.30, 0.40, 0.50],
        bowen=[1.50, 1.50, 1.00, 0.80, 0.70, 0.70, 0.70, 0.70, 0.80, 1.00, 1.50, 1.50],
        roughness=[0.50, 0.50, 0.50, 0.40, 0.30, 0.25, 0.25, 0.25, 0.30, 0.40, 0.50, 0.50],
        start_date="2020/01/01",
        end_date="2020/12/31"
    )

    # Generate input file
    with open("aermet_stage3.inp", "w") as f:
        f.write(stage3.to_aermet_input())

    print("✓ Created: aermet_stage3.inp")
    print()
    print("To run AERMET Stage 3:")
    print("  aermet < aermet_stage3.inp")
    print()
    print("Output files:")
    print("  - aermod.sfc (surface parameters)")
    print("  - aermod.pfl (profile data)")
    print()
