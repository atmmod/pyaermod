"""
PyAERMOD Source dataclasses and helpers.

Contains all AERMOD source types (PointSource, AreaSource, VolumeSource,
LineSource, etc.), deposition parameter dataclasses, building-downwash
helpers, background concentration, source groups, and the SourcePathway
collection.

This module is an internal implementation detail.  Public imports should go
through :mod:`pyaermod.input_generator` (the backwards-compatible facade)
or :mod:`pyaermod.api`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Union

from .pathways import ChemistryOptions

# ============================================================================
# DEPOSITION PARAMETERS
# ============================================================================

class DepositionMethod(Enum):
    """AERMOD deposition method types for the METHOD keyword."""
    GASDEPVD = "GASDEPVD"
    GASDEPDF = "GASDEPDF"
    DRYDPLT = "DRYDPLT"
    WETDPLT = "WETDPLT"


@dataclass
class GasDepositionParams:
    """Gas deposition parameters for the GASDEPOS keyword."""
    diffusivity: float
    alpha_r: float
    reactivity: float
    henry_constant: Optional[float] = None
    dry_dep_velocity: Optional[float] = None


@dataclass
class ParticleDepositionParams:
    """Particle deposition parameters for PARTDIAM/MASSFRAX/PARTDENS keywords."""
    diameters: List[float] = field(default_factory=list)
    mass_fractions: List[float] = field(default_factory=list)
    densities: List[float] = field(default_factory=list)


def _deposition_to_aermod_lines(
    source_id: str,
    gas_deposition: Optional[GasDepositionParams],
    particle_deposition: Optional[ParticleDepositionParams],
    deposition_method: Optional[Tuple[DepositionMethod, float]],
) -> List[str]:
    """Generate AERMOD deposition keyword lines for a source."""
    lines = []
    if gas_deposition:
        gd = gas_deposition
        last_val = gd.henry_constant if gd.henry_constant is not None else gd.dry_dep_velocity
        if last_val is not None:
            lines.append(
                f"   GASDEPOS  {source_id:<8} "
                f"{gd.diffusivity:.4g}  {gd.alpha_r:.4g}  "
                f"{gd.reactivity:.4g}  {last_val:.4g}"
            )
    if particle_deposition:
        pd = particle_deposition
        d_vals = "  ".join(f"{d:.4g}" for d in pd.diameters)
        lines.append(f"   PARTDIAM  {source_id:<8} {d_vals}")
        f_vals = "  ".join(f"{f:.6f}" for f in pd.mass_fractions)
        lines.append(f"   MASSFRAX  {source_id:<8} {f_vals}")
        r_vals = "  ".join(f"{r:.4g}" for r in pd.densities)
        lines.append(f"   PARTDENS  {source_id:<8} {r_vals}")
    if deposition_method:
        method, value = deposition_method
        lines.append(f"   METHOD    {source_id:<8} {method.value}  {value:.6g}")
    return lines


# ============================================================================
# BUILDING DOWNWASH HELPERS
# ============================================================================

def _format_building_keyword(
    source_id: str, keyword: str, values: Union[float, List[float]]
) -> List[str]:
    """
    Format a building downwash keyword for AERMOD input.

    Parameters
    ----------
    source_id : str
        Source identifier.
    keyword : str
        AERMOD keyword (BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ).
    values : float or list of float
        Scalar (single value for all directions) or 36-value list
        (one per 10-degree wind sector).

    Returns
    -------
    list of str
        Formatted AERMOD input lines.

    Raises
    ------
    ValueError
        If values is a list with length other than 36.
    """
    kw = f"{keyword:<9}"

    if isinstance(values, (int, float)):
        return [f"   {kw} {source_id:<8} {values:8.2f}"]

    if len(values) != 36:
        raise ValueError(
            f"{keyword} requires exactly 36 values for direction-dependent "
            f"downwash, got {len(values)}"
        )

    lines = []
    for row_start in range(0, 36, 10):
        chunk = values[row_start : row_start + 10]
        val_str = " ".join(f"{v:8.2f}" for v in chunk)
        lines.append(f"   {kw} {source_id:<8} {val_str}")
    return lines


def _building_downwash_lines(source_id: str, source) -> List[str]:
    """Generate building downwash keyword lines for a source.

    Reads building_height, building_width, building_length,
    building_x_offset, building_y_offset from the source and
    emits the corresponding AERMOD keywords.
    """
    lines = []
    mapping = [
        ("building_height", "BUILDHGT"),
        ("building_width", "BUILDWID"),
        ("building_length", "BUILDLEN"),
        ("building_x_offset", "XBADJ"),
        ("building_y_offset", "YBADJ"),
    ]
    for attr, keyword in mapping:
        val = getattr(source, attr, None)
        if val is not None:
            lines.extend(_format_building_keyword(source_id, keyword, val))
    return lines


def _set_building_from_bpip(source, x_coord: float, y_coord: float, building) -> None:
    """
    Populate building downwash fields from a Building object.

    Runs BPIPCalculator to compute 36 direction-dependent values
    and stores them in the building_* fields.

    Parameters
    ----------
    source : PointSource, AreaSource, or VolumeSource
        The source to populate building fields on.
    x_coord : float
        Source x-coordinate.
    y_coord : float
        Source y-coordinate.
    building : pyaermod.bpip.Building
        Building geometry to use for downwash calculations.
    """
    from pyaermod.bpip import BPIPCalculator

    calc = BPIPCalculator(building, x_coord, y_coord)
    result = calc.calculate_all()

    source.building_height = result.buildhgt
    source.building_width = result.buildwid
    source.building_length = result.buildlen
    source.building_x_offset = result.xbadj
    source.building_y_offset = result.ybadj


# ============================================================================
# SOURCE DATACLASSES
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
    stack_temp: float = 293.15  # Kelvin (default 20C)
    exit_velocity: float = 0.0  # m/s
    stack_diameter: float = 0.0  # meters

    # Emission parameters
    emission_rate: float = 1.0  # g/s

    # Building downwash (optional)
    # Accepts either a single float (scalar, same for all directions) or
    # a list of 36 floats (one per 10-degree wind sector, BPIP output).
    building_height: Optional[Union[float, List[float]]] = None
    building_width: Optional[Union[float, List[float]]] = None
    building_length: Optional[Union[float, List[float]]] = None
    building_x_offset: Optional[Union[float, List[float]]] = None
    building_y_offset: Optional[Union[float, List[float]]] = None

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Per-source NO2/NOx ratio (optional, overrides default)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    def _format_building_keyword(
        self, keyword: str, values: Union[float, List[float]]
    ) -> List[str]:
        """Thin wrapper around module-level helper for backward compat."""
        return _format_building_keyword(self.source_id, keyword, values)

    def set_building_from_bpip(self, building) -> None:
        """
        Populate building downwash fields from a Building object.

        Runs BPIPCalculator to compute 36 direction-dependent values
        and stores them in the building_* fields.

        Parameters
        ----------
        building : pyaermod.bpip.Building
            Building geometry to use for downwash calculations.
        """
        _set_building_from_bpip(self, self.x_coord, self.y_coord, building)

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

        # Building downwash parameters (scalar or 36-value direction-dependent)
        lines.extend(_building_downwash_lines(self.source_id, self))

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

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

    # Building downwash (optional)
    building_height: Optional[Union[float, List[float]]] = None
    building_width: Optional[Union[float, List[float]]] = None
    building_length: Optional[Union[float, List[float]]] = None
    building_x_offset: Optional[Union[float, List[float]]] = None
    building_y_offset: Optional[Union[float, List[float]]] = None

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    def set_building_from_bpip(self, building) -> None:
        """Populate building downwash fields from a Building object."""
        _set_building_from_bpip(self, self.x_coord, self.y_coord, building)

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREA    "
            f"{self.x_coord:12.4f} {self.y_coord:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword -- angle is optional 5th parameter for AREA sources
        srcparam = (
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{self.initial_lateral_dimension:8.2f} {self.initial_vertical_dimension:8.2f}"
        )
        if self.angle != 0.0:
            srcparam += f" {self.angle:8.2f}"
        lines.append(srcparam)

        # Building downwash parameters
        lines.extend(_building_downwash_lines(self.source_id, self))

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

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

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

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

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

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

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION must be the polygon's FIRST vertex, not its centroid:
        # AERMOD cross-checks the two and rejects the deck with
        # "ARVERT: First Vertex Does Not Match LOCATION for AREAPOLY".
        x_first, y_first = self.vertices[0]
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREAPOLY "
            f"{x_first:12.4f} {y_first:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM for AREAPOLY is (emission rate, release height,
        # number of vertices) -- see APPARM in AERMOD's soset.f. Omitting
        # the vertex count is a fatal "Not Enough Parameters" error, and
        # then every AREAVERT line is counted against an unset limit.
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{len(self.vertices):8d}"
        )

        # AREAVERT keyword - vertices
        # Format: 6 coordinate pairs per line maximum
        coords_per_line = 6
        for i in range(0, len(self.vertices), coords_per_line):
            chunk = self.vertices[i:i+coords_per_line]
            coord_str = "  ".join(f"{x:12.4f} {y:12.4f}" for x, y in chunk)
            lines.append(f"   AREAVERT  {self.source_id:<8} {coord_str}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

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

    # Building downwash (optional)
    building_height: Optional[Union[float, List[float]]] = None
    building_width: Optional[Union[float, List[float]]] = None
    building_length: Optional[Union[float, List[float]]] = None
    building_x_offset: Optional[Union[float, List[float]]] = None
    building_y_offset: Optional[Union[float, List[float]]] = None

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    def set_building_from_bpip(self, building) -> None:
        """Populate building downwash fields from a Building object."""
        _set_building_from_bpip(self, self.x_coord, self.y_coord, building)

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

        # Building downwash parameters
        lines.extend(_building_downwash_lines(self.source_id, self))

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

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

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword -- LINE: srcid LINE X1 Y1 X2 Y2 [Zelev]
        lines.append(
            f"   LOCATION  {self.source_id:<8} LINE    "
            f"{self.x_start:12.4f} {self.y_start:12.4f} "
            f"{self.x_end:12.4f} {self.y_end:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
            f"{self.initial_lateral_dimension:8.2f}"
        )

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class StreetCanyon:
    """Street canyon geometry for RLINE/RLINEXT sources.

    Approximates canyon effects by adjusting initial vertical dispersion
    and applying a concentration scaling factor based on the canyon
    aspect ratio (building_height / street_width).

    The approach uses three flow regimes (Oke, 1988):
      - AR < 0.65: isolated roughness -- minimal canyon trapping
      - 0.65 <= AR < 1.5: wake interference / skimming flow
      - AR >= 1.5: deep canyon with persistent vortex

    The adjusted sigma-z reflects reduced ventilation inside the canyon,
    and the concentration factor accounts for pollutant trapping that
    cannot be captured by sigma-z alone.
    """
    building_height: float       # average building height flanking the road (m)
    street_width: float          # wall-to-wall street width (m)

    @property
    def aspect_ratio(self) -> float:
        """Canyon aspect ratio H/W."""
        if self.street_width <= 0:
            return 0.0
        return self.building_height / self.street_width

    def adjusted_sigma_z(self, base_sigma_z: float) -> float:
        """Return sigma-z adjusted for canyon trapping.

        In the recirculation zone the effective mixing height is limited
        to the canyon depth, which increases initial sigma-z (more
        vertical mixing within the confined space).
        """
        ar = self.aspect_ratio
        if ar < 0.65:
            # Isolated roughness -- minimal effect
            return base_sigma_z
        # Recirculation zone height ~ min(H, W) (Johnson & Hunter, 1999)
        recirc_height = min(self.building_height, self.street_width)
        # Scale sigma-z: the canyon traps pollutants within recirc_height.
        # Use sqrt(base^2 + (f*recirc_height)^2) so the effect layers on.
        # f increases with aspect ratio: 0.3 at AR=0.65 -> ~0.7 for deep canyons
        f = min(0.3 + 0.25 * (ar - 0.65), 0.7)
        return (base_sigma_z**2 + (f * recirc_height) ** 2) ** 0.5

    def concentration_factor(self) -> float:
        """Multiplicative factor on emission rate to represent canyon trapping.

        Derived from the OSPM box-model concept: reduced ventilation in
        the canyon raises concentrations relative to open-road dispersion.
        The factor equals 1.0 (no effect) for isolated roughness and
        increases with aspect ratio up to a cap of 3.0 for deep canyons.
        """
        ar = self.aspect_ratio
        if ar < 0.65:
            return 1.0
        # Linear ramp: factor = 1 + slope*(AR - 0.65), capped at 3.0
        return min(1.0 + 1.5 * (ar - 0.65), 3.0)


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

    # Street canyon (optional)
    street_canyon: Optional[StreetCanyon] = None

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # Apply street canyon adjustments
        erate = self.emission_rate
        vert_dim = self.initial_vertical_dimension
        if self.street_canyon is not None:
            erate *= self.street_canyon.concentration_factor()
            vert_dim = self.street_canyon.adjusted_sigma_z(vert_dim)

        # LOCATION keyword -- RLINE: srcid RLINE XSB YSB XSE YSE [Zelev]
        lines.append(
            f"   LOCATION  {self.source_id:<8} RLINE   "
            f"{self.x_start:12.4f} {self.y_start:12.4f} "
            f"{self.x_end:12.4f} {self.y_end:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword - RLINE has different parameters than LINE
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{erate:10.6f} {self.release_height:8.2f} "
            f"{self.initial_lateral_dimension:8.2f} {vert_dim:8.2f}"
        )

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class RLineExtSource:
    """
    AERMOD RLINEXT source (extended roadway source)

    Extension of RLINE with per-endpoint heights, noise barrier support,
    and depressed roadway modeling. Requires ALPHA model option for
    barrier/depression features.
    """
    source_id: str
    x_start: float
    y_start: float
    z_start: float  # source height at start endpoint (meters)
    x_end: float
    y_end: float
    z_end: float    # source height at end endpoint (meters)
    base_elevation: float = 0.0

    # SRCPARAM fields
    emission_rate: float = 1.0           # g/(m*s) per unit length of road
    dcl: float = 0.0                     # offset distance from centerline (meters)
    road_width: float = 30.0             # width of roadway (meters)
    init_sigma_z: float = 1.5            # initial vertical dispersion (meters)

    # Barrier fields (optional, requires ALPHA + FLAT)
    barrier_height_1: Optional[float] = None   # height of barrier 1 (meters, >= 0)
    barrier_dcl_1: Optional[float] = None      # barrier 1 distance from centerline (meters)
    barrier_height_2: Optional[float] = None   # height of barrier 2 (meters, >= 0)
    barrier_dcl_2: Optional[float] = None      # barrier 2 distance from centerline (meters)

    # Depression fields (optional, requires ALPHA + FLAT)
    depression_depth: Optional[float] = None   # depth of depression (meters, <= 0)
    depression_wtop: Optional[float] = None    # top width of depression (meters, >= 0)
    depression_wbottom: Optional[float] = None  # bottom width of depression (meters, [0, wtop])

    # Street canyon (optional)
    street_canyon: Optional[StreetCanyon] = None

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # Apply street canyon adjustments
        erate = self.emission_rate
        sigma_z = self.init_sigma_z
        if self.street_canyon is not None:
            erate *= self.street_canyon.concentration_factor()
            sigma_z = self.street_canyon.adjusted_sigma_z(sigma_z)

        # LOCATION keyword -- RLINEXT: srcid RLINEXT XSB YSB ZSB XSE YSE ZSE
        # (no base_elevation -- ZSB/ZSE are the heights at each endpoint)
        lines.append(
            f"   LOCATION  {self.source_id:<8} RLINEXT "
            f"{self.x_start:12.4f} {self.y_start:12.4f} {self.z_start:8.2f} "
            f"{self.x_end:12.4f} {self.y_end:12.4f} {self.z_end:8.2f}"
        )

        # SRCPARAM keyword: Qemis DCL Width InitSigmaZ
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{erate:10.6f} {self.dcl:8.2f} "
            f"{self.road_width:8.2f} {sigma_z:8.2f}"
        )

        # Optional RBARRIER
        if self.barrier_height_1 is not None and self.barrier_dcl_1 is not None:
            if self.barrier_height_2 is not None and self.barrier_dcl_2 is not None:
                lines.append(
                    f"   RBARRIER  {self.source_id:<8} "
                    f"{self.barrier_height_1:8.2f} {self.barrier_dcl_1:8.2f} "
                    f"{self.barrier_height_2:8.2f} {self.barrier_dcl_2:8.2f}"
                )
            else:
                lines.append(
                    f"   RBARRIER  {self.source_id:<8} "
                    f"{self.barrier_height_1:8.2f} {self.barrier_dcl_1:8.2f}"
                )

        # Optional RDEPRESS
        if self.depression_depth is not None and self.depression_wtop is not None and self.depression_wbottom is not None:
            lines.append(
                f"   RDEPRESS  {self.source_id:<8} "
                f"{self.depression_depth:8.2f} {self.depression_wtop:8.2f} "
                f"{self.depression_wbottom:8.2f}"
            )

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class BuoyLineSegment:
    """A single line segment within a BUOYLINE source group."""
    source_id: str
    x_start: float
    y_start: float
    x_end: float
    y_end: float
    emission_rate: float = 1.0       # g/s (average emission release rate)
    release_height: float = 10.0     # meters


@dataclass
class BuoyLineSource:
    """
    AERMOD BUOYLINE source (buoyant line source)

    Models buoyant line sources such as aluminum reduction plant
    potroom roof vents. Consists of multiple line segments sharing
    common plume rise parameters defined via BLPINPUT.
    """
    source_id: str  # Group identifier for BLPGROUP

    # Average plume rise parameters (BLPINPUT)
    avg_line_length: float           # meters
    avg_building_height: float       # meters
    avg_building_width: float        # meters
    avg_line_width: float            # meters
    avg_building_separation: float   # meters
    avg_buoyancy_parameter: float    # m^4/s^3

    # Line segments
    line_segments: List[BuoyLineSegment] = field(default_factory=list)

    base_elevation: float = 0.0

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    @property
    def emission_rate(self) -> float:
        """Total emission rate across all segments."""
        if self.line_segments:
            return sum(seg.emission_rate for seg in self.line_segments)
        return 0.0

    @property
    def number_of_lines(self) -> int:
        return len(self.line_segments)

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION and SRCPARAM for each line segment
        for seg in self.line_segments:
            lines.append(
                f"   LOCATION  {seg.source_id:<8} BUOYLINE "
                f"{seg.x_start:12.4f} {seg.y_start:12.4f} "
                f"{seg.x_end:12.4f} {seg.y_end:12.4f} {self.base_elevation:8.2f}"
            )
            lines.append(
                f"   SRCPARAM  {seg.source_id:<8} "
                f"{seg.emission_rate:10.6f} {seg.release_height:8.2f}"
            )

        # BLPINPUT - average plume rise parameters. The group ID is
        # required whenever a BLPGROUP names one: without it AERMOD
        # registers the parameters under the implicit group "ALL" and
        # then fails with "No BLPINPUT record for BLPGROUP ID".
        lines.append(
            f"   BLPINPUT  {self.source_id:<8} "
            f"{self.avg_line_length:8.2f} {self.avg_building_height:8.2f} "
            f"{self.avg_building_width:8.2f} {self.avg_line_width:8.2f} "
            f"{self.avg_building_separation:8.2f} {self.avg_buoyancy_parameter:10.6f}"
        )

        # BLPGROUP - associate all segments
        seg_ids = " ".join(seg.source_id for seg in self.line_segments)
        lines.append(f"   BLPGROUP  {self.source_id:<8} {seg_ids}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                for seg in self.line_segments:
                    lines.append(f"   SRCGROUP  {group:<8} {seg.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            for seg in self.line_segments:
                lines.append(f"   URBANSRC  {seg.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


@dataclass
class OpenPitSource:
    """
    AERMOD OPENPIT source (open pit mine/quarry)

    Models fugitive emissions from open pit sources. The escape fraction
    is computed internally by AERMOD based on pit geometry and wind speed.
    Coordinates specify the SW corner of the pit.
    """
    source_id: str
    x_coord: float        # SW corner x-coordinate
    y_coord: float        # SW corner y-coordinate
    base_elevation: float = 0.0

    # SRCPARAM fields
    emission_rate: float = 1.0       # g/(s*m^2)
    release_height: float = 0.0      # meters above pit base
    x_dimension: float = 100.0       # meters (pit length in x-direction)
    y_dimension: float = 100.0       # meters (pit width in y-direction)
    pit_volume: float = 100000.0     # m^3 (must be > 0)
    angle: float = 0.0               # rotation angle from north (degrees)

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None

    @property
    def effective_depth(self) -> float:
        """Effective pit depth computed from volume and dimensions."""
        if self.x_dimension > 0 and self.y_dimension > 0:
            return self.pit_volume / (self.x_dimension * self.y_dimension)
        return 0.0

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} OPENPIT "
            f"{self.x_coord:12.4f} {self.y_coord:12.4f} {self.base_elevation:8.2f}"
        )

        # SRCPARAM keyword: Qemis Hs Xinit Yinit Volume [Angle]
        if self.angle != 0.0:
            lines.append(
                f"   SRCPARAM  {self.source_id:<8} "
                f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
                f"{self.x_dimension:8.2f} {self.y_dimension:8.2f} "
                f"{self.pit_volume:12.2f} {self.angle:8.2f}"
            )
        else:
            lines.append(
                f"   SRCPARAM  {self.source_id:<8} "
                f"{self.emission_rate:10.6f} {self.release_height:8.2f} "
                f"{self.x_dimension:8.2f} {self.y_dimension:8.2f} "
                f"{self.pit_volume:12.2f}"
            )

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban and self.urban_area_name:
            lines.append(f"   URBANSRC  {self.source_id:<8} {self.urban_area_name}")

        return "\n".join(lines)


# ============================================================================
# BACKGROUND & SOURCE GROUPS
# ============================================================================

@dataclass
class BackgroundSector:
    """A wind direction sector for direction-dependent background concentrations.

    Each sector is defined by its starting direction (degrees clockwise from
    north). AERMOD allows up to 6 sectors. The ending direction is implicitly
    the starting direction of the next sector (or the first sector for wrap-around).
    """
    sector_id: int
    start_direction: float


@dataclass
class BackgroundConcentration:
    """
    AERMOD background concentration configuration (SO BACKGRND / BGSECTOR).

    Supports three modes:
    1. Uniform: single value for all hours/directions
    2. Period-specific: mapping of averaging period to value
    3. Sector-dependent: sectors + per-sector, per-period values
    """
    uniform_value: Optional[float] = None
    period_values: Optional[dict] = None
    sectors: Optional[List[BackgroundSector]] = None
    sector_values: Optional[dict] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD BACKGRND / BGSECTOR keywords."""
        lines = []
        if self.sectors and self.sector_values:
            # BGSECTOR takes starting directions only (up to 6)
            sorted_sectors = sorted(self.sectors, key=lambda s: s.sector_id)
            dir_parts = [f"{s.start_direction:.1f}" for s in sorted_sectors]
            lines.append(f"   BGSECTOR  {' '.join(dir_parts)}")
            # BACKGRND with sectors: BACKGRND SECTn period value
            for (sid, period), value in sorted(self.sector_values.items()):
                lines.append(f"   BACKGRND  SECT{sid}  {period}  {value:.6g}")
        elif self.period_values:
            for period, value in self.period_values.items():
                lines.append(f"   BACKGRND  {period}  {value:.6g}")
        elif self.uniform_value is not None:
            lines.append(f"   BACKGRND  {self.uniform_value:.6g}")
        return "\n".join(lines)


@dataclass
class SourceGroupDefinition:
    """
    Centralized source group definition.

    Allows defining named groups of sources for AERMOD's SRCGROUP keyword,
    enabling per-group output files and chemistry associations.

    Parameters
    ----------
    group_name : str
        Group identifier (max 8 characters, AERMOD limitation).
    member_source_ids : list of str
        Source IDs belonging to this group.
    description : str
        Optional description for documentation purposes.
    """
    group_name: str
    member_source_ids: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class SourcePathway:
    """Collection of sources"""
    sources: List[Union[PointSource, AreaSource, AreaCircSource, AreaPolySource,
                        VolumeSource, LineSource, RLineSource,
                        RLineExtSource, BuoyLineSource, OpenPitSource]] = field(default_factory=list)
    background: Optional[BackgroundConcentration] = None
    group_definitions: List[SourceGroupDefinition] = field(default_factory=list)

    def add_source(self, source: Union[PointSource, AreaSource, AreaCircSource, AreaPolySource,
                                       VolumeSource, LineSource, RLineSource,
                                       RLineExtSource, BuoyLineSource, OpenPitSource]):
        """Add a source to the pathway"""
        self.sources.append(source)

    def add_group(self, group: SourceGroupDefinition):
        """Add a source group definition."""
        self.group_definitions.append(group)

    def _collect_all_source_ids(self) -> List[str]:
        """Collect all source IDs, including BUOYLINE segment IDs."""
        ids = []
        for source in self.sources:
            if isinstance(source, BuoyLineSource):
                for seg in source.line_segments:
                    ids.append(seg.source_id)
            else:
                ids.append(source.source_id)
        return ids

    def to_aermod_input(self, chemistry: Optional[ChemistryOptions] = None) -> str:
        """Generate AERMOD SO pathway text.

        Parameters
        ----------
        chemistry : ChemistryOptions, optional
            Chemistry options from ControlPathway for OLM group emission.
        """
        lines = ["SO STARTING"]

        for source in self.sources:
            lines.append(source.to_aermod_input())

        if self.background:
            lines.append(self.background.to_aermod_input())

        # OLM groups (from chemistry options)
        if chemistry is not None and chemistry.olm_groups:
            for olm_group in chemistry.olm_groups:
                if olm_group.member_source_ids:
                    lines.append(
                        f"   OLMGROUP  {olm_group.group_name:<8} "
                        f"{' '.join(olm_group.member_source_ids)}"
                    )

        # Centralized SRCGROUP definitions
        all_ids = self._collect_all_source_ids()
        if all_ids:
            # SRCGROUP ALL -- AERMOD auto-includes all sources; no IDs listed
            lines.append("   SRCGROUP  ALL")

        # Custom group definitions
        for group in self.group_definitions:
            if group.member_source_ids:
                lines.append(
                    f"   SRCGROUP  {group.group_name:<8} "
                    f"{' '.join(group.member_source_ids)}"
                )

        lines.append("SO FINISHED")
        return "\n".join(lines)
