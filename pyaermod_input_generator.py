"""
PyAERMOD Input File Generator

Generates AERMOD-compatible input files from Python objects.
Based on AERMOD version 24142 keyword specifications.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union, Tuple
from pathlib import Path
from enum import Enum


class TerrainType(Enum):
    """AERMOD terrain types"""
    FLAT = "FLAT"
    ELEVATED = "ELEVATED"
    FLATSRCS = "FLATSRCS"


class PollutantType(Enum):
    """Common pollutant types"""
    OTHER = "OTHER"
    PM25 = "PM25"
    PM10 = "PM10"
    NO2 = "NO2"
    SO2 = "SO2"
    CO = "CO"
    O3 = "O3"


class SourceType(Enum):
    """AERMOD source types"""
    POINT = "POINT"
    VOLUME = "VOLUME"
    AREA = "AREA"
    AREACIRC = "AREACIRC"
    AREAPOLY = "AREAPOLY"
    OPENPIT = "OPENPIT"
    LINE = "LINE"
    RLINE = "RLINE"
    RLINEXT = "RLINEXT"
    BUOYLINE = "BUOYLINE"


# ============================================================================
# CONTROL PATHWAY
# ============================================================================

@dataclass
class ControlPathway:
    """
    AERMOD Control (CO) pathway configuration

    Defines overall model behavior, pollutant type, averaging periods,
    and other global settings.
    """
    title_one: str
    title_two: Optional[str] = None
    pollutant_id: Union[str, PollutantType] = PollutantType.OTHER
    averaging_periods: List[str] = field(default_factory=lambda: ["ANNUAL"])
    terrain_type: Union[str, TerrainType] = TerrainType.FLAT

    # Model options
    calculate_concentration: bool = True
    calculate_deposition: bool = False
    calculate_dry_deposition: bool = False
    calculate_wet_deposition: bool = False

    # Optional settings
    elevation_units: str = "METERS"  # or "FEET"
    flag_pole_height: Optional[float] = None
    half_life: Optional[float] = None  # hours, for decay
    decay_coefficient: Optional[float] = None  # 1/seconds

    # Urban/rural
    urban_option: Optional[str] = None  # Urban area name if urban

    # Low wind options
    low_wind_option: Optional[str] = None  # e.g., "LOWWIND3"

    def to_aermod_input(self) -> str:
        """Generate AERMOD CO pathway text"""
        lines = ["CO STARTING"]

        # Titles
        lines.append(f"   TITLEONE  {self.title_one}")
        if self.title_two:
            lines.append(f"   TITLETWO  {self.title_two}")

        # Model options
        model_opts = []
        if self.calculate_concentration:
            model_opts.append("CONC")
        if self.calculate_deposition:
            model_opts.append("DEPOS")
        if self.calculate_dry_deposition:
            model_opts.append("DDEP")
        if self.calculate_wet_deposition:
            model_opts.append("WDEP")

        # Add terrain type
        terrain = self.terrain_type.value if isinstance(self.terrain_type, TerrainType) else self.terrain_type
        model_opts.append(terrain)

        lines.append(f"   MODELOPT  {' '.join(model_opts)}")

        # Averaging periods
        lines.append(f"   AVERTIME  {' '.join(self.averaging_periods)}")

        # Pollutant ID
        pollutant = self.pollutant_id.value if isinstance(self.pollutant_id, PollutantType) else self.pollutant_id
        lines.append(f"   POLLUTID  {pollutant}")

        # Optional parameters
        if self.half_life is not None:
            lines.append(f"   HALFLIFE  {self.half_life:.4f}")

        if self.decay_coefficient is not None:
            lines.append(f"   DCAYCOEF  {self.decay_coefficient:.6e}")

        if self.elevation_units != "METERS":
            lines.append(f"   ELEVUNIT  {self.elevation_units}")

        if self.flag_pole_height is not None:
            lines.append(f"   FLAGPOLE  {self.flag_pole_height:.2f}")

        if self.urban_option:
            lines.append(f"   URBANOPT  {self.urban_option}")

        if self.low_wind_option:
            lines.append(f"   LOW_WIND  {self.low_wind_option}")

        # Run command
        lines.append("   RUNORNOT  RUN")
        lines.append("CO FINISHED")

        return "\n".join(lines)


# ============================================================================
# SOURCE PATHWAY
# ============================================================================

@dataclass
class PointSource:
    """
    AERMOD point source (stack)

    Represents an elevated point source with emission parameters.
    """
    source_id: str
    x_coord: float
    y_coord: float
    base_elevation: float = 0.0

    # Stack parameters
    stack_height: float = 0.0  # meters above base
    stack_temp: float = 293.15  # Kelvin (default 20°C)
    exit_velocity: float = 0.0  # m/s
    stack_diameter: float = 0.0  # meters

    # Emission parameters
    emission_rate: float = 1.0  # g/s

    # Building downwash (optional)
    building_height: Optional[float] = None
    building_width: Optional[float] = None
    building_length: Optional[float] = None
    building_x_offset: Optional[float] = None
    building_y_offset: Optional[float] = None

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} POINT  "
            f"{self.x_coord:12.4f} {self.y_coord:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.stack_height:8.2f} "
            f"{self.stack_temp:8.2f} {self.exit_velocity:8.2f} {self.stack_diameter:8.2f}"
        )

        # Building downwash parameters
        if self.building_height is not None:
            lines.append(f"   BUILDHGT  {self.source_id:<8} {self.building_height:8.2f}")

        if self.building_width is not None:
            lines.append(f"   BUILDWID  {self.source_id:<8} {self.building_width:8.2f}")

        if self.building_length is not None:
            lines.append(f"   BUILDLEN  {self.source_id:<8} {self.building_length:8.2f}")

        if self.building_x_offset is not None:
            lines.append(f"   XBADJ     {self.source_id:<8} {self.building_x_offset:8.2f}")

        if self.building_y_offset is not None:
            lines.append(f"   YBADJ     {self.source_id:<8} {self.building_y_offset:8.2f}")

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class AreaSource:
    """
    AERMOD area source (rectangular)

    Represents a rectangular area source with uniform emissions.
    """
    source_id: str
    x_coord: float
    y_coord: float
    base_elevation: float = 0.0

    # Area parameters
    release_height: float = 0.0  # meters above ground
    initial_lateral_dimension: float = 10.0  # meters (half-width in y-direction)
    initial_vertical_dimension: float = 10.0  # meters (half-width in x-direction)

    # Emission parameters
    emission_rate: float = 1.0  # g/s/m^2

    # Orientation
    angle: float = 0.0  # degrees from north (optional)

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREA    "
            f"{self.x_coord:12.4f} {self.y_coord:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{self.initial_lateral_dimension:8.2f} {self.initial_vertical_dimension:8.2f}"
        )

        # Optional angle
        if self.angle != 0.0:
            lines.append(f"   AREAVERT  {self.source_id:<8}  {self.angle:8.2f}")

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class AreaCircSource:
    """
    AERMOD circular area source

    Represents a circular area source with uniform emissions.
    """
    source_id: str
    x_coord: float
    y_coord: float
    base_elevation: float = 0.0

    # Area parameters
    release_height: float = 0.0  # meters above ground
    radius: float = 100.0  # meters

    # Emission parameters
    emission_rate: float = 1.0  # g/s/m^2

    # Discretization
    num_vertices: int = 20  # Number of vertices for approximation

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREACIRC "
            f"{self.x_coord:12.4f} {self.y_coord:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{self.radius:8.2f} {self.num_vertices:3d}"
        )

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class AreaPolySource:
    """
    AERMOD polygonal area source

    Represents an irregular polygonal area source defined by vertices.
    """
    source_id: str
    vertices: List[Tuple[float, float]]  # List of (x, y) coordinates
    base_elevation: float = 0.0

    # Area parameters
    release_height: float = 0.0  # meters above ground

    # Emission parameters
    emission_rate: float = 1.0  # g/s/m^2

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # Calculate center point (approximate)
        x_center = sum(v[0] for v in self.vertices) / len(self.vertices)
        y_center = sum(v[1] for v in self.vertices) / len(self.vertices)

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREAPOLY "
            f"{x_center:12.4f} {y_center:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f}"
        )

        # AREAVERT keyword - vertices
        # Format: 6 coordinate pairs per line maximum
        coords_per_line = 6
        for i in range(0, len(self.vertices), coords_per_line):
            chunk = self.vertices[i:i+coords_per_line]
            coord_str = "  ".join(f"{x:12.4f} {y:12.4f}" for x, y in chunk)
            lines.append(f"   AREAVERT  {self.source_id:<8} {coord_str}")

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class VolumeSource:
    """
    AERMOD volume source

    Represents a three-dimensional volume with initial dispersion.
    Useful for modeling emissions from buildings, structures, or areas
    with significant initial mixing.
    """
    source_id: str
    x_coord: float
    y_coord: float
    base_elevation: float = 0.0

    # Volume parameters
    release_height: float = 0.0  # meters above ground (centroid height)
    initial_lateral_dimension: float = 10.0  # meters (initial sigma_y)
    initial_vertical_dimension: float = 10.0  # meters (initial sigma_z)

    # Emission parameters
    emission_rate: float = 1.0  # g/s

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} VOLUME  "
            f"{self.x_coord:12.4f} {self.y_coord:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{self.initial_lateral_dimension:8.2f} {self.initial_vertical_dimension:8.2f}"
        )

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class LineSource:
    """
    AERMOD line source

    Represents a linear source with uniform emissions per unit length.
    Useful for modeling roads, conveyor belts, pipelines, or any
    linear emission feature.
    """
    source_id: str
    x_start: float
    y_start: float
    x_end: float
    y_end: float
    base_elevation: float = 0.0

    # Line parameters
    release_height: float = 0.0  # meters above ground
    initial_lateral_dimension: float = 1.0  # meters (initial sigma_y perpendicular to line)

    # Emission parameters
    emission_rate: float = 1.0  # g/s/m (per unit length)

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword - LINE sources need two coordinate pairs
        lines.append(
            f"   LOCATION  {self.source_id:<8} LINE    "
            f"{self.x_start:12.4f} {self.y_start:12.4f} {self.base_elevation:8.2f}"
        )

        # Second coordinate pair for end point
        lines.append(
            f"   LOCATION  {self.source_id:<8} LINE    "
            f"{self.x_end:12.4f} {self.y_end:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{self.initial_lateral_dimension:8.2f}"
        )

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class RLineSource:
    """
    AERMOD RLINE source (roadway source)

    Specialized source for modeling mobile emissions on roadways.
    More sophisticated than basic LINE source with road-specific parameters.
    """
    source_id: str
    x_start: float
    y_start: float
    x_end: float
    y_end: float
    base_elevation: float = 0.0

    # Roadway parameters
    release_height: float = 0.0  # meters above ground (typically vehicle exhaust height)
    initial_lateral_dimension: float = 3.0  # meters (lane width / 2)
    initial_vertical_dimension: float = 1.5  # meters (initial mixing height)

    # Emission parameters
    emission_rate: float = 1.0  # g/s/m (per unit length)

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword - RLINE sources need two coordinate pairs
        lines.append(
            f"   LOCATION  {self.source_id:<8} RLINE   "
            f"{self.x_start:12.4f} {self.y_start:12.4f} {self.base_elevation:8.2f}"
        )

        # Second coordinate pair for end point
        lines.append(
            f"   LOCATION  {self.source_id:<8} RLINE   "
            f"{self.x_end:12.4f} {self.y_end:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword - RLINE has different parameters than LINE
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{self.initial_lateral_dimension:8.2f} {self.initial_vertical_dimension:8.2f}"
        )

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class SourcePathway:
    """Collection of sources"""
    sources: List[Union[PointSource, AreaSource, AreaCircSource, AreaPolySource, VolumeSource, LineSource, RLineSource]] = field(default_factory=list)

    def add_source(self, source: Union[PointSource, AreaSource, AreaCircSource, AreaPolySource, VolumeSource, LineSource, RLineSource]):
        """Add a source to the pathway"""
        self.sources.append(source)

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text"""
        lines = ["SO STARTING"]

        for source in self.sources:
            lines.append(source.to_aermod_input())

        lines.append("SO FINISHED")
        return "\n".join(lines)


# ============================================================================
# RECEPTOR PATHWAY
# ============================================================================

@dataclass
class CartesianGrid:
    """
    AERMOD Cartesian receptor grid (GRIDCART)

    Creates a regular rectangular grid of receptors.
    """
    grid_name: str = "GRID1"

    # X-axis definition
    x_init: float = 0.0
    x_num: int = 10
    x_delta: float = 100.0

    # Y-axis definition
    y_init: float = 0.0
    y_num: int = 10
    y_delta: float = 100.0

    # Elevation (optional)
    z_elev: float = 0.0
    z_hill: float = 0.0
    z_flag: float = 0.0

    @classmethod
    def from_bounds(cls, x_min: float, x_max: float, y_min: float, y_max: float,
                   spacing: float = 100.0, grid_name: str = "GRID1") -> 'CartesianGrid':
        """Create grid from bounding box and spacing"""
        x_num = int((x_max - x_min) / spacing) + 1
        y_num = int((y_max - y_min) / spacing) + 1

        return cls(
            grid_name=grid_name,
            x_init=x_min,
            x_num=x_num,
            x_delta=spacing,
            y_init=y_min,
            y_num=y_num,
            y_delta=spacing
        )

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text"""
        return (
            f"   GRIDCART  {self.grid_name:<8} XYINC  "
            f"{self.x_init:10.2f} {self.x_num:5d} {self.x_delta:8.2f}  "
            f"{self.y_init:10.2f} {self.y_num:5d} {self.y_delta:8.2f}"
        )


@dataclass
class PolarGrid:
    """
    AERMOD polar receptor grid (GRIDPOLR)

    Creates receptors in polar coordinates (distance and direction from origin).
    """
    grid_name: str = "GRID1"

    # Origin
    x_origin: float = 0.0
    y_origin: float = 0.0

    # Distance (radial)
    dist_init: float = 100.0
    dist_num: int = 10
    dist_delta: float = 100.0

    # Direction (degrees from north, clockwise)
    dir_init: float = 0.0
    dir_num: int = 36
    dir_delta: float = 10.0

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text"""
        lines = []
        lines.append(
            f"   GRIDPOLR  {self.grid_name:<8} ORIG  "
            f"{self.x_origin:10.2f} {self.y_origin:10.2f}"
        )
        lines.append(
            f"   GRIDPOLR  {self.grid_name:<8} DIST  "
            f"{self.dist_init:10.2f} {self.dist_num:5d} {self.dist_delta:8.2f}"
        )
        lines.append(
            f"   GRIDPOLR  {self.grid_name:<8} GDIR  "
            f"{self.dir_init:6.1f} {self.dir_num:5d} {self.dir_delta:6.1f}"
        )
        return "\n".join(lines)


@dataclass
class DiscreteReceptor:
    """Individual receptor at specific location"""
    x_coord: float
    y_coord: float
    z_elev: float = 0.0
    z_hill: float = 0.0
    z_flag: float = 0.0

    def to_aermod_input(self) -> str:
        """Generate AERMOD DISCCART line"""
        return (
            f"   DISCCART  {self.x_coord:12.4f} {self.y_coord:12.4f} "
            f"{self.z_elev:8.2f} {self.z_hill:8.2f} {self.z_flag:8.2f}"
        )


@dataclass
class ReceptorPathway:
    """Collection of receptor grids and discrete receptors"""
    cartesian_grids: List[CartesianGrid] = field(default_factory=list)
    polar_grids: List[PolarGrid] = field(default_factory=list)
    discrete_receptors: List[DiscreteReceptor] = field(default_factory=list)
    elevation_units: str = "METERS"

    def add_cartesian_grid(self, grid: CartesianGrid):
        """Add Cartesian grid"""
        self.cartesian_grids.append(grid)

    def add_polar_grid(self, grid: PolarGrid):
        """Add polar grid"""
        self.polar_grids.append(grid)

    def add_discrete_receptor(self, receptor: DiscreteReceptor):
        """Add discrete receptor"""
        self.discrete_receptors.append(receptor)

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text"""
        lines = ["RE STARTING"]

        # Elevation units (if not default)
        if self.elevation_units != "METERS":
            lines.append(f"   ELEVUNIT  {self.elevation_units}")

        # Cartesian grids
        for grid in self.cartesian_grids:
            lines.append(grid.to_aermod_input())

        # Polar grids
        for grid in self.polar_grids:
            lines.append(grid.to_aermod_input())

        # Discrete receptors
        for receptor in self.discrete_receptors:
            lines.append(receptor.to_aermod_input())

        lines.append("RE FINISHED")
        return "\n".join(lines)


# ============================================================================
# METEOROLOGY PATHWAY
# ============================================================================

@dataclass
class MeteorologyPathway:
    """
    AERMOD Meteorology (ME) pathway

    Defines meteorological data files and processing options.
    """
    surface_file: str
    profile_file: str

    # Optional parameters
    start_year: Optional[int] = None
    start_month: Optional[int] = None
    start_day: Optional[int] = None
    end_year: Optional[int] = None
    end_month: Optional[int] = None
    end_day: Optional[int] = None

    # Wind direction rotation
    wind_rotation: Optional[float] = None  # degrees

    def to_aermod_input(self) -> str:
        """Generate AERMOD ME pathway text"""
        lines = ["ME STARTING"]

        # Surface and profile files
        lines.append(f"   SURFFILE  {self.surface_file}")
        lines.append(f"   PROFFILE  {self.profile_file}")

        # Data processing
        lines.append("   SURFDATA  ")
        lines.append("   UAIRDATA  ")

        # Date range (if specified)
        if all(x is not None for x in [self.start_year, self.start_month, self.start_day,
                                        self.end_year, self.end_month, self.end_day]):
            lines.append(
                f"   STARTEND  {self.start_year:4d} {self.start_month:2d} {self.start_day:2d}  "
                f"{self.end_year:4d} {self.end_month:2d} {self.end_day:2d}"
            )

        # Wind rotation
        if self.wind_rotation is not None:
            lines.append(f"   WDROTATE  {self.wind_rotation:.2f}")

        lines.append("ME FINISHED")
        return "\n".join(lines)


# ============================================================================
# OUTPUT PATHWAY
# ============================================================================

@dataclass
class OutputPathway:
    """
    AERMOD Output (OU) pathway

    Controls output file generation and formats.
    """
    # Table outputs
    receptor_table: bool = True
    receptor_table_rank: int = 10  # Number of high values to include

    max_table: bool = True
    max_table_rank: int = 10

    day_table: bool = False

    # File outputs
    summary_file: Optional[str] = None
    max_file: Optional[str] = None
    plot_file: Optional[str] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD OU pathway text"""
        lines = ["OU STARTING"]

        # Receptor table
        if self.receptor_table:
            lines.append(f"   RECTABLE  ALLAVE  {self.receptor_table_rank}")

        # Max table
        if self.max_table:
            lines.append(f"   MAXTABLE  ALLAVE  {self.max_table_rank}")

        # Day table
        if self.day_table:
            lines.append("   DAYTABLE  ALLAVE")

        # Summary file
        if self.summary_file:
            lines.append(f"   SUMMFILE  {self.summary_file}")

        # Max file
        if self.max_file:
            lines.append(f"   MAXIFILE  {self.max_file}")

        # Plot file
        if self.plot_file:
            lines.append(f"   PLOTFILE  ANNUAL  ALL  FIRST  {self.plot_file}")

        lines.append("OU FINISHED")
        return "\n".join(lines)


# ============================================================================
# MAIN PROJECT CLASS
# ============================================================================

@dataclass
class AERMODProject:
    """
    Complete AERMOD project

    Combines all pathways into a single input file.
    """
    control: ControlPathway
    sources: SourcePathway
    receptors: ReceptorPathway
    meteorology: MeteorologyPathway
    output: OutputPathway

    def to_aermod_input(self) -> str:
        """Generate complete AERMOD input file"""
        sections = [
            self.control.to_aermod_input(),
            "",
            self.sources.to_aermod_input(),
            "",
            self.receptors.to_aermod_input(),
            "",
            self.meteorology.to_aermod_input(),
            "",
            self.output.to_aermod_input()
        ]
        return "\n".join(sections)

    def write(self, filename: Union[str, Path]):
        """Write input file to disk"""
        output_path = Path(filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            f.write(self.to_aermod_input())

        return output_path


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

def create_example_project() -> AERMODProject:
    """Create an example AERMOD project"""

    # Control pathway
    control = ControlPathway(
        title_one="Example AERMOD Project",
        title_two="Generated by pyaermod",
        pollutant_id=PollutantType.PM25,
        averaging_periods=["ANNUAL", "24", "1"],
        terrain_type=TerrainType.FLAT
    )

    # Sources
    sources = SourcePathway()

    stack1 = PointSource(
        source_id="STACK1",
        x_coord=500.0,
        y_coord=500.0,
        base_elevation=10.0,
        stack_height=50.0,
        stack_temp=400.0,  # Kelvin
        exit_velocity=15.0,  # m/s
        stack_diameter=2.0,  # m
        emission_rate=1.5,  # g/s
        source_groups=["ALL"]
    )
    sources.add_source(stack1)

    # Receptors - Cartesian grid
    receptors = ReceptorPathway()

    grid = CartesianGrid.from_bounds(
        x_min=0.0,
        x_max=2000.0,
        y_min=0.0,
        y_max=2000.0,
        spacing=100.0
    )
    receptors.add_cartesian_grid(grid)

    # Meteorology
    meteorology = MeteorologyPathway(
        surface_file="example.sfc",
        profile_file="example.pfl",
        start_year=2023,
        start_month=1,
        start_day=1,
        end_year=2023,
        end_month=12,
        end_day=31
    )

    # Output
    output = OutputPathway(
        receptor_table=True,
        receptor_table_rank=10,
        max_table=True,
        summary_file="example.sum"
    )

    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output
    )


if __name__ == "__main__":
    # Create example project
    project = create_example_project()

    # Print to console
    print(project.to_aermod_input())

    # Or write to file
    # project.write("example.inp")
