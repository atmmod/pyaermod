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
from typing import ClassVar, Dict, List, Optional, Tuple, Union

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
    """Gas dry-deposition parameters for the ``GASDEPOS`` keyword.

    The four fields are, in AERMOD's order (``soset.f``, subroutine
    ``GASDEP``): ``GASDEPOS srcid Da Dw rcl Henry``. All four are
    required by AERMOD (E201/E202 otherwise) and must be positive
    (E380), except that a ``0`` in any field selects AERMOD's built-in
    value for the pollutants it knows (HG0, HGII, TCDD, BAP, SO2, NO2;
    warning W473). GASDEPOS is an ALPHA-option keyword (E198) and is
    rejected when ``GASDEPVD`` is also given (E195).

    Earlier pyaermod releases named the second and third fields
    ``alpha_r`` and ``reactivity`` and validated the third as a 0-1
    fraction; EPA's own ``testgas`` deck (``0.08962 1.04E-5 2.51E4
    557.0``) was rejected by that validator. The values themselves
    always went through unchanged.

    Parameters
    ----------
    diffusivity : float
        Molecular diffusivity in air, ``Da`` (cm^2/s).
    diffusivity_water : float
        Molecular diffusivity in water, ``Dw`` (cm^2/s).
    cuticular_resistance : float
        Lipid cuticle resistance for individual leaves, ``rcl`` (s/cm).
    henry_constant : float
        Henry's law constant (Pa m^3/mol).
    """
    diffusivity: float
    diffusivity_water: float
    cuticular_resistance: float
    henry_constant: float


@dataclass
class ParticleDepositionParams:
    """Particle deposition parameters for PARTDIAM/MASSFRAX/PARTDENS keywords."""
    diameters: List[float] = field(default_factory=list)
    mass_fractions: List[float] = field(default_factory=list)
    densities: List[float] = field(default_factory=list)


@dataclass
class Method2Params:
    """``SO METHOD_2 srcid finemass dg``: Method 2 particle deposition.

    soset.f METH_2 reads exactly two values -- the fine-mass fraction
    (the fraction of the mass below 2.5 microns, 0-1, E332) and the mass
    mean diameter in microns -- and builds a single particle category
    from them, so a source has either this or the PARTDIAM/MASSFRAX/
    PARTDENS arrays (E386). METHOD_2 is an ALPHA-only, non-DFAULT
    keyword (E198/E197; probe decks 21 and 21b). EPA's testpart, testprt2
    and openpits decks use it. A ``0`` in either field selects AERMOD's
    built-in value for the pollutants AR, CD, PB, HG and POC (W473).

    Parameters
    ----------
    fine_mass_fraction : float
        Fraction of particle mass finer than 2.5 microns.
    mass_mean_diameter : float
        Representative particle diameter (microns).
    """
    fine_mass_fraction: float
    mass_mean_diameter: float


@dataclass
class PlatformParams:
    """``SO PLATFORM srcid elev hb wb``: an offshore platform under a stack.

    soset.f PLATFM reads the platform base elevation above sea level, the
    height of the platform's building above that base and its width;
    downwash is applied only when both are above zero. POINT, POINTCAP
    and POINTHOR sources only (E631), one card per source (E632), ALPHA
    required (E198; probe deck 22).

    Parameters
    ----------
    base_elevation : float
        Platform base elevation above sea level (m).
    building_height : float
        Platform building height above the base (m).
    building_width : float
        Platform building width (m).
    """
    base_elevation: float
    building_height: float
    building_width: float


def _fx(value: float, spec: str) -> str:
    """A fixed-decimal field that never rounds a value away.

    The writers lay SRCPARAM and LOCATION out in fixed columns
    (``8.2f``, ``10.6f``, ``12.4f``); a value with more decimals than the
    column holds -- EPA's capped deck gives its Implementation-Guide stacks
    an exit velocity of 0.001 m/s, which ``8.2f`` turns into 0.00 -- is
    written instead with :func:`_aermod_number`, right-aligned to the same
    width, so the column layout survives and so does the value.
    """
    text = format(value, spec)
    if float(text) == float(value):
        return text
    width = int(spec.split(".")[0]) if spec[0].isdigit() else 0
    return f"{_aermod_number(value):>{width}}"


def _loc_elev(source) -> str:
    """The LOCATION elevation field: the base elevation, or the literal
    ``FLAT`` for a source flagged flat in a FLATSRCS run (EPA's flatelev
    deck: ``LOCATION FLAT_STK POINT 5510. 67960. FLAT``)."""
    if getattr(source, "flat_source", False):
        return "    FLAT"
    return _fx(source.base_elevation, '8.2f')


def _aermod_number(value: float) -> str:
    """A numeric field AERMOD's STODBL accepts.

    ``.6g`` is compact but writes ``1e+06``; STODBL reads an exponent
    only after a mantissa with a decimal point (``1.0e+06`` and ``1.e6``
    pass, ``1e6`` and ``1E6`` are E208), so one is inserted when needed.
    """
    text = f"{value:.6g}"
    mantissa, sep, exponent = text.partition("e")
    if sep and "." not in mantissa:
        mantissa += ".0"
    return mantissa + sep + exponent


def _deposition_to_aermod_lines(
    source_id: str,
    gas_deposition: Optional[GasDepositionParams],
    particle_deposition: Optional[ParticleDepositionParams],
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None,
    method_2: Optional[Method2Params] = None,
) -> List[str]:
    """Generate AERMOD deposition keyword lines for a source.

    ``deposition_method`` is accepted for compatibility and writes
    nothing: the ``METHOD srcid option value`` line earlier releases
    emitted for it is not an AERMOD keyword (there is no METHOD in
    modules.f; SO E105, probe deck 20). Method 2 deposition is the
    ``METHOD_2`` card, from ``method_2``.
    """
    lines = []
    if gas_deposition:
        gd = gas_deposition
        lines.append(
            f"   GASDEPOS  {source_id:<8} "
            f"{_aermod_number(gd.diffusivity)}  {_aermod_number(gd.diffusivity_water)}  "
            f"{_aermod_number(gd.cuticular_resistance)}  {_aermod_number(gd.henry_constant)}"
        )
    if particle_deposition:
        pd = particle_deposition
        d_vals = "  ".join(f"{d:.4g}" for d in pd.diameters)
        lines.append(f"   PARTDIAM  {source_id:<8} {d_vals}")
        f_vals = "  ".join(f"{f:.6f}" for f in pd.mass_fractions)
        lines.append(f"   MASSFRAX  {source_id:<8} {f_vals}")
        r_vals = "  ".join(f"{r:.4g}" for r in pd.densities)
        lines.append(f"   PARTDENS  {source_id:<8} {r_vals}")
    if method_2 is not None:
        lines.append(
            f"   METHOD_2  {source_id:<8} {_aermod_number(method_2.fine_mass_fraction)}  "
            f"{_aermod_number(method_2.mass_mean_diameter)}"
        )
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
        return [f"   {kw} {source_id:<8} {_fx(values, '8.2f')}"]

    if len(values) != 36:
        raise ValueError(
            f"{keyword} requires exactly 36 values for direction-dependent "
            f"downwash, got {len(values)}"
        )

    lines = []
    for row_start in range(0, 36, 10):
        chunk = values[row_start : row_start + 10]
        val_str = " ".join(f"{_fx(v, '8.2f')}" for v in chunk)
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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

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
    method_2: Optional[Method2Params] = None

    # PLATFORM srcid elev hb wb (offshore platform downwash; ALPHA)
    platform: Optional[PlatformParams] = None

    #: The LOCATION source type; POINTCAP and POINTHOR are subclasses.
    location_type: ClassVar[str] = "POINT"

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

        # LOCATION keyword (POINT, or POINTCAP / POINTHOR for the subclasses)
        lines.append(
            f"   LOCATION  {self.source_id:<8} {self.location_type}  "
            f"{_fx(self.x_coord, '12.4f')} {_fx(self.y_coord, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(self.emission_rate, '10.6f')} {_fx(self.stack_height, '8.2f')} "
            f"{_fx(self.stack_temp, '8.2f')} {_fx(self.exit_velocity, '8.2f')} {_fx(self.stack_diameter, '8.2f')}"
        )

        # Building downwash parameters (scalar or 36-value direction-dependent)
        lines.extend(_building_downwash_lines(self.source_id, self))

        # Offshore platform (soset.f PLATFM: elev hb wb)
        if self.platform is not None:
            pf = self.platform
            lines.append(
                f"   PLATFORM  {self.source_id:<8} {_aermod_number(pf.base_elevation)}  "
                f"{_aermod_number(pf.building_height)}  {_aermod_number(pf.building_width)}"
            )

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

        return "\n".join(lines)


@dataclass
class PointCapSource(PointSource):
    """``LOCATION srcid POINTCAP ...``: a point source with a rain cap.

    Same SRCPARAM layout as POINT (soset.f PPARM); AERMOD doubles the
    initial plume diameter for the PRIME algorithm (ADSFACT = 2) and, with
    the BETA option, models the capped release directly (EPA's capped
    deck). Every PointSource field applies.
    """
    location_type: ClassVar[str] = "POINTCAP"


@dataclass
class PointHorSource(PointSource):
    """``LOCATION srcid POINTHOR ...``: a horizontally discharging stack.

    Same SRCPARAM layout as POINT (soset.f PPARM); the exit velocity is
    the horizontal release velocity.
    """
    location_type: ClassVar[str] = "POINTHOR"


@dataclass
class SidewashPointSource:
    """``LOCATION srcid SWPOINT x y [zelev]`` with
    ``SRCPARAM srcid emis hs bw bl bh ba``: a sidewash point source.

    A stack on a building whose wake is modelled by the sidewash
    algorithm (soset.f SWPARM, v26135): the six SRCPARAM values are the
    emission rate, the release height, and the building's width, length,
    height and orientation angle (degrees; AERMOD folds it into 0-360).
    ALPHA is required (E198, probe deck 23b). A building dimension of
    zero or less is reset to 1 m by AERMOD.
    """
    source_id: str
    x_coord: float
    y_coord: float
    base_elevation: float = 0.0
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

    emission_rate: float = 1.0  # g/s
    release_height: float = 0.0  # m
    building_width: float = 1.0  # m
    building_length: float = 1.0  # m
    building_height: float = 1.0  # m
    building_angle: float = 0.0  # degrees

    source_groups: List[str] = field(default_factory=list)
    is_urban: bool = False
    urban_area_name: Optional[str] = None
    no2_ratio: Optional[float] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = [
            f"   LOCATION  {self.source_id:<8} SWPOINT  "
            f"{_fx(self.x_coord, '12.4f')} {_fx(self.y_coord, '12.4f')} {_loc_elev(self)}",
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
            f"{_fx(self.building_width, '8.2f')} {_fx(self.building_length, '8.2f')} "
            f"{_fx(self.building_height, '8.2f')} {_fx(self.building_angle, '8.2f')}",
        ]
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")
        for group in self.source_groups:
            lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")
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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

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

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

    def set_building_from_bpip(self, building) -> None:
        """Populate building downwash fields from a Building object."""
        _set_building_from_bpip(self, self.x_coord, self.y_coord, building)

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREA    "
            f"{_fx(self.x_coord, '12.4f')} {_fx(self.y_coord, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM keyword -- angle is optional 5th parameter for AREA sources
        srcparam = (
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
            f"{_fx(self.initial_lateral_dimension, '8.2f')} {_fx(self.initial_vertical_dimension, '8.2f')}"
        )
        if self.angle != 0.0:
            srcparam += f" {_fx(self.angle, '8.2f')}"
        lines.append(srcparam)

        # Building downwash parameters
        lines.extend(_building_downwash_lines(self.source_id, self))

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

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

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREACIRC "
            f"{_fx(self.x_coord, '12.4f')} {_fx(self.y_coord, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
            f"{_fx(self.radius, '8.2f')} {self.num_vertices:3d}"
        )

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

    # Area parameters
    release_height: float = 0.0  # meters above ground
    # Optional initial vertical dimension (SRCPARAM field 4, ``szinit``,
    # metres). ``None`` writes the three-field form; AERMOD then uses 0.
    initial_vertical_dimension: Optional[float] = None

    # Emission parameters
    emission_rate: float = 1.0  # g/s/m^2

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION must be the polygon's FIRST vertex, not its centroid:
        # AERMOD cross-checks the two and rejects the deck with
        # "ARVERT: First Vertex Does Not Match LOCATION for AREAPOLY".
        x_first, y_first = self.vertices[0]
        lines.append(
            f"   LOCATION  {self.source_id:<8} AREAPOLY "
            f"{_fx(x_first, '12.4f')} {_fx(y_first, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM for AREAPOLY is (emission rate, release height,
        # number of vertices) -- see APPARM in AERMOD's soset.f. Omitting
        # the vertex count is a fatal "Not Enough Parameters" error, and
        # then every AREAVERT line is counted against an unset limit.
        srcparam = (
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
            f"{len(self.vertices):8d}"
        )
        if self.initial_vertical_dimension is not None:
            srcparam += f" {_fx(self.initial_vertical_dimension, '8.2f')}"
        lines.append(srcparam)

        # AREAVERT keyword - vertices
        # Format: 6 coordinate pairs per line maximum
        coords_per_line = 6
        for i in range(0, len(self.vertices), coords_per_line):
            chunk = self.vertices[i:i+coords_per_line]
            coord_str = "  ".join(f"{_fx(x, '12.4f')} {_fx(y, '12.4f')}" for x, y in chunk)
            lines.append(f"   AREAVERT  {self.source_id:<8} {coord_str}")

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

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

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

    def set_building_from_bpip(self, building) -> None:
        """Populate building downwash fields from a Building object."""
        _set_building_from_bpip(self, self.x_coord, self.y_coord, building)

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword
        lines.append(
            f"   LOCATION  {self.source_id:<8} VOLUME  "
            f"{_fx(self.x_coord, '12.4f')} {_fx(self.y_coord, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM keyword
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
            f"{_fx(self.initial_lateral_dimension, '8.2f')} {_fx(self.initial_vertical_dimension, '8.2f')}"
        )

        # Building downwash parameters
        lines.extend(_building_downwash_lines(self.source_id, self))

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

    # Line parameters
    release_height: float = 0.0  # meters above ground
    initial_lateral_dimension: float = 1.0  # meters (initial sigma_y perpendicular to line)
    # Optional initial vertical dimension (SRCPARAM field 4, ``szinit``,
    # metres; soset.f LPARM). ``None`` writes the three-field form.
    initial_vertical_dimension: Optional[float] = None

    # Emission parameters
    emission_rate: float = 1.0  # g/s/m (per unit length)

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD SO pathway text for this source"""
        lines = []

        # LOCATION keyword -- LINE: srcid LINE X1 Y1 X2 Y2 [Zelev]
        lines.append(
            f"   LOCATION  {self.source_id:<8} LINE    "
            f"{_fx(self.x_start, '12.4f')} {_fx(self.y_start, '12.4f')} "
            f"{_fx(self.x_end, '12.4f')} {_fx(self.y_end, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM keyword: emission relhgt width [szinit] (soset.f LPARM)
        srcparam = (
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
            f"{_fx(self.initial_lateral_dimension, '8.2f')}"
        )
        if self.initial_vertical_dimension is not None:
            srcparam += f" {_fx(self.initial_vertical_dimension, '8.2f')}"
        lines.append(srcparam)

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

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

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

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
            f"{_fx(self.x_start, '12.4f')} {_fx(self.y_start, '12.4f')} "
            f"{_fx(self.x_end, '12.4f')} {_fx(self.y_end, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM keyword - RLINE has different parameters than LINE
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(erate, '10.6f')} {_fx(self.release_height, '8.2f')} "
            f"{_fx(self.initial_lateral_dimension, '8.2f')} {_fx(vert_dim, '8.2f')}"
        )

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

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

    # Vegetative barriers (VBARRIER, v26135; at most two, requires
    # ALPHA + FLAT). AERMOD keeps only the barrier nearer the road when
    # both lie on the same side (warning W375).
    vegetative_barriers: List[VegetativeBarrier] = field(default_factory=list)

    # Street canyon (optional)
    street_canyon: Optional[StreetCanyon] = None

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

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
        # [Zelev]. ZSB/ZSE are the release heights at each endpoint; the
        # optional eleventh field is the base elevation, read by soset.f
        # SOLOCA since RLINEXT gained terrain (2022). It is always written
        # so an ELEV run never falls back to ZS = 0.0 with warning W205.
        lines.append(
            f"   LOCATION  {self.source_id:<8} RLINEXT "
            f"{_fx(self.x_start, '12.4f')} {_fx(self.y_start, '12.4f')} {_fx(self.z_start, '8.2f')} "
            f"{_fx(self.x_end, '12.4f')} {_fx(self.y_end, '12.4f')} {_fx(self.z_end, '8.2f')} "
            f"{_loc_elev(self)}"
        )

        # SRCPARAM keyword: Qemis DCL Width InitSigmaZ
        lines.append(
            f"   SRCPARAM  {self.source_id:<8} "
            f"{_fx(erate, '10.6f')} {_fx(self.dcl, '8.2f')} "
            f"{_fx(self.road_width, '8.2f')} {_fx(sigma_z, '8.2f')}"
        )

        # Optional RBARRIER
        if self.barrier_height_1 is not None and self.barrier_dcl_1 is not None:
            if self.barrier_height_2 is not None and self.barrier_dcl_2 is not None:
                lines.append(
                    f"   RBARRIER  {self.source_id:<8} "
                    f"{_fx(self.barrier_height_1, '8.2f')} {_fx(self.barrier_dcl_1, '8.2f')} "
                    f"{_fx(self.barrier_height_2, '8.2f')} {_fx(self.barrier_dcl_2, '8.2f')}"
                )
            else:
                lines.append(
                    f"   RBARRIER  {self.source_id:<8} "
                    f"{_fx(self.barrier_height_1, '8.2f')} {_fx(self.barrier_dcl_1, '8.2f')}"
                )

        # Optional RDEPRESS
        if self.depression_depth is not None and self.depression_wtop is not None and self.depression_wbottom is not None:
            lines.append(
                f"   RDEPRESS  {self.source_id:<8} "
                f"{_fx(self.depression_depth, '8.2f')} {_fx(self.depression_wtop, '8.2f')} "
                f"{_fx(self.depression_wbottom, '8.2f')}"
            )

        # Optional VBARRIER: one barrier is 5 values, two are 10
        # (VBARRIER_INPUTS accepts 8 or 13 fields, nothing in between).
        if self.vegetative_barriers:
            vals = " ".join(
                f"{_fx(b.height, '8.2f')} {_fx(b.width, '8.2f')} {_fx(b.dcl, '8.2f')} "
                f"{_fx(b.leaf_area_index, '8.2f')} {_fx(b.mixing_length, '8.2f')}"
                for b in self.vegetative_barriers[:2]
            )
            lines.append(f"   VBARRIER  {self.source_id:<8} {vals}")

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
    # Base elevation on this segment's LOCATION line; ``None`` uses the
    # group's :attr:`BuoyLineSource.base_elevation`.
    base_elevation: Optional[float] = None


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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

    # Source groups
    source_groups: List[str] = field(default_factory=list)

    # Urban source
    is_urban: bool = False
    urban_area_name: Optional[str] = None

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

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
            elev = (seg.base_elevation if seg.base_elevation is not None
                    else self.base_elevation)
            lines.append(
                f"   LOCATION  {seg.source_id:<8} BUOYLINE "
                f"{_fx(seg.x_start, '12.4f')} {_fx(seg.y_start, '12.4f')} "
                f"{_fx(seg.x_end, '12.4f')} {_fx(seg.y_end, '12.4f')} {'    FLAT' if self.flat_source else _fx(elev, '8.2f')}"
            )
            lines.append(
                f"   SRCPARAM  {seg.source_id:<8} "
                f"{_fx(seg.emission_rate, '10.6f')} {_fx(seg.release_height, '8.2f')}"
            )

        # BLPINPUT - average plume rise parameters. soset.f BL_AVGINP
        # takes two forms: nine fields with a group ID, or eight without,
        # in which case AERMOD files the parameters under the implicit
        # group "ALL" and, when no BLPGROUP follows, puts every BUOYLINE
        # source in it (the pre-2020 single-line-source syntax; EPA's
        # baldwin and allsrcs decks). A group named "ALL" therefore
        # writes the eight-field form and no BLPGROUP; any other group
        # ID is written on both keywords, since a BLPGROUP whose ID has
        # no BLPINPUT record is E502.
        avg = (
            f"{_fx(self.avg_line_length, '8.2f')} {_fx(self.avg_building_height, '8.2f')} "
            f"{_fx(self.avg_building_width, '8.2f')} {_fx(self.avg_line_width, '8.2f')} "
            f"{_fx(self.avg_building_separation, '8.2f')} {_fx(self.avg_buoyancy_parameter, '10.6f')}"
        )
        if self.source_id.upper() == "ALL":
            lines.append(f"   BLPINPUT  {avg}")
        else:
            lines.append(f"   BLPINPUT  {self.source_id:<8} {avg}")
            seg_ids = " ".join(seg.source_id for seg in self.line_segments)
            lines.append(f"   BLPGROUP  {self.source_id:<8} {seg_ids}")

        # Per-source NO2/NOx ratio (NO2RATIO names sources, not groups)
        if self.no2_ratio is not None:
            for seg in self.line_segments:
                lines.append(f"   NO2RATIO  {seg.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                for seg in self.line_segments:
                    lines.append(f"   SRCGROUP  {group:<8} {seg.source_id}")

        # Urban source
        if self.is_urban:
            for seg in self.line_segments:
                lines.append(f"   URBANSRC  {seg.source_id}")

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
    # LOCATION's elevation field written as the literal FLAT: the source
    # sits in flat terrain in a FLAT ELEV (FLATSRCS) run (soset.f SOLOCA).
    flat_source: bool = False

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

    # Per-source in-stack NO2/NOx ratio (NO2RATIO; OLM/PVMRM/GRSM/TTRM)
    no2_ratio: Optional[float] = None

    # Deposition parameters (optional)
    gas_deposition: Optional[GasDepositionParams] = None
    particle_deposition: Optional[ParticleDepositionParams] = None
    deposition_method: Optional[Tuple[DepositionMethod, float]] = None
    method_2: Optional[Method2Params] = None

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
            f"{_fx(self.x_coord, '12.4f')} {_fx(self.y_coord, '12.4f')} {_loc_elev(self)}"
        )

        # SRCPARAM keyword: Qemis Hs Xinit Yinit Volume [Angle]
        if self.angle != 0.0:
            lines.append(
                f"   SRCPARAM  {self.source_id:<8} "
                f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
                f"{_fx(self.x_dimension, '8.2f')} {_fx(self.y_dimension, '8.2f')} "
                f"{_fx(self.pit_volume, '12.2f')} {_fx(self.angle, '8.2f')}"
            )
        else:
            lines.append(
                f"   SRCPARAM  {self.source_id:<8} "
                f"{_fx(self.emission_rate, '10.6f')} {_fx(self.release_height, '8.2f')} "
                f"{_fx(self.x_dimension, '8.2f')} {_fx(self.y_dimension, '8.2f')} "
                f"{_fx(self.pit_volume, '12.2f')}"
            )

        # Per-source NO2/NOx ratio
        if self.no2_ratio is not None:
            lines.append(f"   NO2RATIO  {self.source_id:<8} {self.no2_ratio:.4f}")

        # Deposition parameters
        lines.extend(_deposition_to_aermod_lines(
            self.source_id, self.gas_deposition,
            self.particle_deposition, self.deposition_method, self.method_2,
        ))

        # Source groups
        if self.source_groups:
            for group in self.source_groups:
                lines.append(f"   SRCGROUP  {group:<8} {self.source_id}")

        # Urban source
        if self.is_urban:
            lines.append(f"   URBANSRC  {self.source_id}")

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
class VegetativeBarrier:
    """One vegetative barrier beside an RLINEXT road (``VBARRIER``, v26135).

    ``VBARRIER srcid ht wt dcl lai lm [ht2 wt2 dcl2 lai2 lm2]`` in
    ``soset.f`` (VBARRIER_INPUTS): eight fields for one barrier, thirteen
    for two, nothing in between (E201). AERMOD range-checks every field:
    height 2-10 m (E371), width 2.5-13 m (E372), leaf area index
    4-10.92 (E373), mixing length 0.55-3.75 m (E374). ``dcl`` is the
    signed distance from the road centreline; a second barrier on the
    same side as the first is discarded with warning W375. Requires the
    ALPHA and FLAT options (E198 / E713).
    """
    height: float
    width: float
    dcl: float
    leaf_area_index: float
    mixing_length: float


@dataclass
class SolidBarrierSegment:
    """One straight piece of a solid barrier (``SBARRIER`` segment line)."""
    x_start: float
    y_start: float
    x_end: float
    y_end: float
    height: float              # metres; AERMOD accepts 2 < ht <= 12 (E320)
    elevation: float = 0.0     # metres; currently ignored by AERMOD (W326 if non-zero)


@dataclass
class SolidBarrier:
    """A free-standing solid barrier for RLINE modelling (``SBARRIER``, v26135).

    Written as AERMOD's SBARRIER_INPUTS reads it: an opening
    ``SBARRIER barid STA nseg`` line, one ``SBARRIER barid xbb ybb xbe
    ybe ht z`` line per segment (1-50 segments, E320), and a closing
    ``SBARRIER barid END`` line whose segment count must match (E306).
    AERMOD re-orders a segment's endpoints west-to-east (or north-to-south
    for vertical segments) on read, so the coordinates may come back
    swapped. Requires the ALPHA and FLAT options (E198 / E713).
    """
    barrier_id: str
    segments: List[SolidBarrierSegment] = field(default_factory=list)

    def to_aermod_input(self) -> str:
        lines = [f"   SBARRIER  {self.barrier_id:<8} STA  {len(self.segments)}"]
        for seg in self.segments:
            lines.append(
                f"   SBARRIER  {self.barrier_id:<8} "
                f"{_fx(seg.x_start, '12.4f')} {_fx(seg.y_start, '12.4f')} "
                f"{_fx(seg.x_end, '12.4f')} {_fx(seg.y_end, '12.4f')} "
                f"{_fx(seg.height, '8.2f')} {_fx(seg.elevation, '8.2f')}"
            )
        lines.append(f"   SBARRIER  {self.barrier_id:<8} END")
        return "\n".join(lines)


@dataclass
class EmissionUnits:
    """Emission-rate unit conversion (``EMISUNIT``, ``CONCUNIT``, ``DEPOUNIT``).

    All three keywords take exactly ``factor emission_label output_label``
    (``soset.f`` EMUNIT / COUNIT / DPUNIT; E201/E202 otherwise). The factor
    multiplies the model's g/s output into the output units; the labels
    are printed in the output headers. EMISUNIT applies to a run with a
    single output type and conflicts with CONCUNIT or DEPOUNIT (E158,
    E159); CONCUNIT and DEPOUNIT set the concentration and deposition
    units separately when both are calculated.
    """
    factor: float
    emission_label: str
    output_label: str

    def to_aermod_input(self, keyword: str) -> str:
        return (f"   {keyword}  {_aermod_number(self.factor)}  "
                f"{self.emission_label}  {self.output_label}")


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


def _group_lines(keyword: str, group: SourceGroupDefinition,
                 allow_bare_all: bool = False) -> List[str]:
    """One ``<keyword> grpid members...`` line, or the bare ``ALL`` form.

    Member tokens are written as given, so an AERMOD range such as
    ``STK1-STK9`` survives a round trip.
    """
    if group.member_source_ids:
        return [f"   {keyword}  {group.group_name:<8} "
                f"{' '.join(group.member_source_ids)}"]
    if allow_bare_all and group.group_name.upper() == "ALL":
        return [f"   {keyword}  ALL"]
    return []


@dataclass
class SourcePathway:
    """Collection of sources"""
    sources: List[Union[PointSource, AreaSource, AreaCircSource, AreaPolySource,
                        VolumeSource, LineSource, RLineSource,
                        RLineExtSource, BuoyLineSource, OpenPitSource,
                        SidewashPointSource]] = field(default_factory=list)
    background: Optional[BackgroundConcentration] = None
    group_definitions: List[SourceGroupDefinition] = field(default_factory=list)

    #: PSDGROUP definitions for a PSDCREDIT run. AERMOD accepts only the
    #: group IDs INCRCONS, RETRBASE and NONRBASE (E287), requires the
    #: PSDCREDIT option (E146) and then forbids SRCGROUP (E105), so the
    #: writer emits these *instead of* SRCGROUP when
    #: ``ControlPathway.psd_credit`` is set.
    psd_groups: List[SourceGroupDefinition] = field(default_factory=list)

    #: EMISUNIT / CONCUNIT / DEPOUNIT (see :class:`EmissionUnits`).
    emission_units: Optional[EmissionUnits] = None
    concentration_units: Optional[EmissionUnits] = None
    deposition_units: Optional[EmissionUnits] = None

    #: RLEMCONV: RLINE emissions are in MOVES units (g/hr/link) and AERMOD
    #: converts them. A bare, non-repeatable keyword (E135 / E202).
    rline_moves_units: bool = False

    #: SBARRIER solid barriers (v26135).
    solid_barriers: List[SolidBarrier] = field(default_factory=list)

    #: ARCFTSRC: the sources modelled with the aircraft plume-rise
    #: algorithms, as the member tokens of the card (IDs, ranges, or
    #: ``ALL``; soset.f AIRCRAFT). Needs ``ControlPathway.aircraft_option``
    #: (E821) and an HOUREMIS file carrying the aircraft record for each
    #: (E823); AERMOD accepts VOLUME and AREA sources only (E833, probe
    #: deck 25b). Kept as written and written back on one card.
    aircraft_sources: List[str] = field(default_factory=list)

    #: HBPSRCID: the point sources treated as highly buoyant plumes
    #: (soset.f HBPSOURCE), as the member tokens of the card (IDs, ranges,
    #: ``ALL``). Needs ``MODELOPT HBP`` (E130) with ALPHA (E198).
    hbp_sources: List[str] = field(default_factory=list)

    #: The bare ``SRCGROUP ALL`` line: None writes it whenever the pathway
    #: has sources (the default for a project built in Python), True
    #: always (a deck that had the line, even with its sources brought in
    #: by INCLUDED), False never (a deck that grouped its sources without
    #: it). The reader sets it from the deck.
    include_all_group: Optional[bool] = None

    def add_source(self, source: Union[PointSource, AreaSource, AreaCircSource, AreaPolySource,
                                       VolumeSource, LineSource, RLineSource,
                                       RLineExtSource, BuoyLineSource, OpenPitSource,
                                       SidewashPointSource]):
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

    def to_aermod_input(self, chemistry: Optional[ChemistryOptions] = None,
                        psd_credit: bool = False) -> str:
        """Generate AERMOD SO pathway text.

        Parameters
        ----------
        chemistry : ChemistryOptions, optional
            Chemistry options from ControlPathway for OLM group emission.
        psd_credit : bool
            The PSDCREDIT option is on (``ControlPathway.psd_credit``):
            write :attr:`psd_groups` and no SRCGROUP lines, as AERMOD
            requires (E105).
        """
        lines = ["SO STARTING"]

        # RLEMCONV precedes the source cards it applies to; like every
        # other SO keyword it must come before SRCGROUP (E140).
        if self.rline_moves_units:
            lines.append("   RLEMCONV")

        for source in self.sources:
            lines.append(source.to_aermod_input())

        # Per-source flags whose card names several sources; both must
        # come before the group keywords (E140).
        if self.aircraft_sources:
            lines.append("   ARCFTSRC  " + "  ".join(self.aircraft_sources))
        if self.hbp_sources:
            lines.append("   HBPSRCID  " + "  ".join(self.hbp_sources))

        for keyword, units in (("EMISUNIT", self.emission_units),
                               ("CONCUNIT", self.concentration_units),
                               ("DEPOUNIT", self.deposition_units)):
            if units is not None:
                lines.append(units.to_aermod_input(keyword))

        if self.background:
            lines.append(self.background.to_aermod_input())

        for barrier in self.solid_barriers:
            lines.append(barrier.to_aermod_input())

        # OLM groups (from chemistry options). ``OLMGROUP ALL`` is the
        # bare form soset.f OLMGRP accepts with no member list.
        if chemistry is not None and chemistry.olm_groups:
            for olm_group in chemistry.olm_groups:
                lines.extend(_group_lines("OLMGROUP", olm_group, allow_bare_all=True))

        if psd_credit:
            for group in self.psd_groups:
                lines.extend(_group_lines("PSDGROUP", group))
        else:
            # SRCGROUP ALL -- AERMOD includes every source itself; the
            # only members it reads from the ALL card are the BACKGROUND
            # / NOBACKGROUND flags (soset.f SOGRP), and only from the
            # card that defines the group: a later "SRCGROUP ALL
            # BACKGROUND" is a continuation, and SOGRP files a
            # continuation under the *last* group defined, whichever ID
            # it names. So a definition named ALL is written on the ALL
            # card, and every group's lines are written together.
            all_ids = self._collect_all_source_ids()
            by_name: Dict[str, List[SourceGroupDefinition]] = {}
            for group in self.group_definitions:
                by_name.setdefault(group.group_name, []).append(group)
            write_all = (bool(all_ids) or any(n.upper() == "ALL" for n in by_name)
                         if self.include_all_group is None else self.include_all_group)
            if write_all:
                all_members = [m for n, defs in by_name.items() if n.upper() == "ALL"
                               for g in defs for m in g.member_source_ids]
                lines.append("   SRCGROUP  ALL" + ("  " + " ".join(all_members)
                                                   if all_members else ""))
            for name, defs in by_name.items():
                if name.upper() == "ALL":
                    continue
                for group in defs:
                    lines.extend(_group_lines("SRCGROUP", group))

        lines.append("SO FINISHED")
        return "\n".join(lines)
