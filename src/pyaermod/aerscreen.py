"""
AERSCREEN input-deck generation.

EPA's AERSCREEN is the single-source screening front-end to AERMOD.
It runs AERMOD with conservative screening met assumptions to produce
worst-case 1-hour, 8-hour, and 24-hour impacts from one source — used
at the start of every permit project to decide whether full AERMOD
modeling is even required.

This module is the deck-builder; binary dispatch lives in
:mod:`pyaermod.aerscreen_runner`.

.. warning::

   **The deck this module writes has never been accepted by AERSCREEN,
   and its format does not match what AERSCREEN reads.** The
   ``KEY: value`` layout below is not an AERSCREEN format. EPA's
   AERSCREEN is interactive: it takes an ordered sequence of answers on
   stdin, and can reload a previous run from the ``**``-prefixed header
   its output file carries (that file is otherwise an AERMOD runstream
   AERSCREEN generates -- see EPA's ``aerscreen_test_cases.zip``, e.g.
   ``point_horiz/AERSCREEN_FLAT_NODW.inp``).

   This is the same defect that :mod:`pyaermod.aersurface` had before it
   was checked against the real binary, and it was found the same way --
   by comparing against EPA's own reference files. Unlike AERSURFACE it
   is not yet fixed: EPA's ``AERSCREEN.FOR`` does not compile under
   gfortran without patching (a missing continuation comma at line 7995
   swallows FORMAT label 5001, and the source uses an Intel format
   extension, needing ``-fdec -std=legacy``), so there is no reference
   implementation wired up to validate against yet.

   Treat :class:`AERSCREENConfig` as a parameter container, not as
   something that will drive AERSCREEN. Do not rely on
   :meth:`AERSCREENConfig.to_aerscreen_input`.

Typical usage::

    from pyaermod import AERSCREENConfig, AERSCREENSourceType

    cfg = AERSCREENConfig(
        title="SO2 stack screening",
        source_type=AERSCREENSourceType.POINT,
        emission_rate=10.0,           # g/s
        stack_height=30.0,            # m
        stack_diameter=2.0,           # m
        stack_temp=425.0,             # K (or set to None for ambient)
        exit_velocity=15.0,           # m/s
        urban=False,
        anemometer_height=10.0,
    )
    deck_text = cfg.to_aerscreen_input()

Forward-compatibility for new AERSCREEN keywords is via
``extra_lines``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import List, Optional


class AERSCREENSourceType(StrEnum):
    """Source-type keywords accepted by AERSCREEN v24."""
    POINT = "POINT"
    FLARE = "FLARE"
    AREA = "AREA"
    VOLUME = "VOLUME"
    CAPPED = "CAPPED"        # capped vertical stack
    HORIZONTAL = "HORIZONTAL"  # horizontally-discharging stack


@dataclass
class AERSCREENConfig:
    """Configuration for one AERSCREEN run.

    Parameters
    ----------
    title
        Free-form run title.
    source_type
        One of :class:`AERSCREENSourceType`. Required.
    emission_rate
        Emission rate in grams per second.
    stack_height
        Stack / release height in meters. Required for all source types
        except AREA where it is the release height of the area source.
    stack_diameter
        Stack inner diameter in meters. Required for POINT, CAPPED,
        HORIZONTAL, FLARE; ignored for AREA / VOLUME.
    stack_temp
        Stack exit temperature in Kelvin. ``None`` to flag ambient
        temperature (AERSCREEN keyword AMBIENT).
    exit_velocity
        Stack exit velocity in m/s. Required for POINT / CAPPED /
        HORIZONTAL; ignored for AREA / VOLUME / FLARE.
    flare_heat_release
        Total heat release for FLARE sources in cal/s. Required for
        FLARE; ignored otherwise.
    area_length, area_width
        Length and width of an AREA source in meters. Required for
        source_type=AREA.
    initial_sigma_z, lateral_dim, vertical_dim
        VOLUME source dimensions in meters. Required for source_type=VOLUME.
    urban
        True for urban dispersion option (URBANOPT). False for rural.
    population
        Surrounding population — used for urban dispersion. Default
        100,000 (a typical screening default). Ignored when ``urban=False``.
    dominant_landuse
        Auer land-use category code (1-12). Optional; AERSCREEN derives
        a default from urban/rural otherwise.
    temp_min_k, temp_max_k
        Climatological annual min / max ambient temperature in Kelvin.
        AERSCREEN uses these to bracket buoyancy effects.
    anemometer_height
        Height of the assumed anemometer in meters. Default 10.
    use_adju
        Whether to apply the AERMOD ADJ_U* low-wind beta option.
        Defaults to False (matching EPA's regulatory default).
    downwash
        True to enable building downwash.
    building_height, building_length, building_width, building_angle
        Building dimensions (m) and orientation (degrees from north).
        Required when ``downwash=True``.
    terrain
        True to model elevated terrain. When True, supply ``lat`` /
        ``lon`` and either ``terrain_file`` or rely on the binary's
        autoextract (DEM-required) flow.
    lat, lon
        Site location in decimal degrees. Required when
        ``terrain=True`` or when AERSCREEN's terrain processing is invoked.
    terrain_file
        Path to a pre-generated DEM file (typical: AERMAP-extracted
        elevations). Optional when ``terrain=True``.
    fumigation
        True to enable shoreline fumigation calculations.
    distances
        Either the literal string ``"AUTO"`` (AERSCREEN's default 1.5 km
        downwind grid) or an explicit list of downwind distances in
        meters.
    extra_lines
        Free-form keyword/value lines appended verbatim. Use for
        forward-compatibility with AERSCREEN keywords not modeled here.
    """

    title: str
    source_type: AERSCREENSourceType
    emission_rate: float

    # Stack-like geometry (POINT / CAPPED / HORIZONTAL / FLARE)
    stack_height: Optional[float] = None
    stack_diameter: Optional[float] = None
    stack_temp: Optional[float] = None       # None => ambient
    exit_velocity: Optional[float] = None
    flare_heat_release: Optional[float] = None

    # AREA geometry
    area_length: Optional[float] = None
    area_width: Optional[float] = None

    # VOLUME geometry
    initial_sigma_z: Optional[float] = None
    lateral_dim: Optional[float] = None
    vertical_dim: Optional[float] = None

    # Met / dispersion
    urban: bool = False
    population: int = 100_000
    dominant_landuse: Optional[int] = None
    temp_min_k: float = 250.0  # ~ -23 C
    temp_max_k: float = 310.0  # ~ +37 C
    anemometer_height: float = 10.0
    use_adju: bool = False

    # Downwash
    downwash: bool = False
    building_height: Optional[float] = None
    building_length: Optional[float] = None
    building_width: Optional[float] = None
    building_angle: Optional[float] = None

    # Terrain
    terrain: bool = False
    lat: Optional[float] = None
    lon: Optional[float] = None
    terrain_file: Optional[str] = None

    # Fumigation
    fumigation: bool = False

    # Receptor scheme
    distances: object = "AUTO"  # str "AUTO" or List[float]

    extra_lines: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        if self.emission_rate <= 0:
            raise ValueError("emission_rate must be > 0 g/s")

        st = self.source_type
        # Keep the enum form even if caller passed a string
        if isinstance(st, str):
            self.source_type = AERSCREENSourceType(st.upper())
            st = self.source_type

        if st in (
            AERSCREENSourceType.POINT,
            AERSCREENSourceType.CAPPED,
            AERSCREENSourceType.HORIZONTAL,
            AERSCREENSourceType.FLARE,
        ):
            if self.stack_height is None or self.stack_height <= 0:
                raise ValueError(f"{st.value} sources require stack_height > 0")
            if st != AERSCREENSourceType.FLARE:
                if self.stack_diameter is None or self.stack_diameter <= 0:
                    raise ValueError(
                        f"{st.value} sources require stack_diameter > 0"
                    )
                if self.exit_velocity is None or self.exit_velocity <= 0:
                    raise ValueError(
                        f"{st.value} sources require exit_velocity > 0"
                    )
            else:
                if (self.flare_heat_release is None
                        or self.flare_heat_release <= 0):
                    raise ValueError(
                        "FLARE sources require flare_heat_release > 0 (cal/s)"
                    )

        if st == AERSCREENSourceType.AREA:
            if self.area_length is None or self.area_length <= 0:
                raise ValueError("AREA sources require area_length > 0")
            if self.area_width is None or self.area_width <= 0:
                raise ValueError("AREA sources require area_width > 0")

        if st == AERSCREENSourceType.VOLUME:
            for fname in ("initial_sigma_z", "lateral_dim", "vertical_dim"):
                v = getattr(self, fname)
                if v is None or v <= 0:
                    raise ValueError(f"VOLUME sources require {fname} > 0")

        if self.temp_min_k >= self.temp_max_k:
            raise ValueError("temp_min_k must be < temp_max_k")

        if self.anemometer_height <= 0:
            raise ValueError("anemometer_height must be > 0")

        if (self.dominant_landuse is not None
                and not (1 <= self.dominant_landuse <= 12)):
            raise ValueError(
                "dominant_landuse must be an Auer code in [1, 12]"
            )

        if self.downwash:
            for fname in ("building_height", "building_length",
                          "building_width", "building_angle"):
                v = getattr(self, fname)
                if v is None:
                    raise ValueError(
                        f"downwash=True requires {fname}"
                    )
            if self.building_angle is not None and not (
                0 <= self.building_angle < 360
            ):
                raise ValueError(
                    "building_angle must be in [0, 360) degrees"
                )

        if self.terrain:
            if self.lat is None or self.lon is None:
                raise ValueError("terrain=True requires lat and lon")
            if not (-90 <= self.lat <= 90):
                raise ValueError("lat must be in [-90, 90]")
            if not (-180 <= self.lon <= 180):
                raise ValueError("lon must be in [-180, 180]")

        if not isinstance(self.distances, str):
            try:
                dlist = list(self.distances)
            except TypeError as e:
                raise ValueError(
                    "distances must be 'AUTO' or an iterable of meters"
                ) from e
            if not dlist:
                raise ValueError("distances list cannot be empty")
            if any(d <= 0 for d in dlist):
                raise ValueError("all distances must be > 0 m")
        elif self.distances.upper() != "AUTO":
            raise ValueError("distances string must be 'AUTO'")

    # ------------------------------------------------------------------
    def to_aerscreen_input(self) -> str:
        """Render the AERSCREEN input deck as a string."""
        lines: List[str] = []
        lines.append(f"TITLE: {self.title}")
        lines.append(f"SOURCE_TYPE: {self.source_type.value}")
        lines.append(f"EMISSION_RATE: {self.emission_rate}")

        st = self.source_type
        if st == AERSCREENSourceType.FLARE:
            lines.append(f"STACK_HEIGHT: {self.stack_height}")
            lines.append(f"FLARE_HEAT_RELEASE: {self.flare_heat_release}")
        elif st in (AERSCREENSourceType.POINT,
                    AERSCREENSourceType.CAPPED,
                    AERSCREENSourceType.HORIZONTAL):
            lines.append(f"STACK_HEIGHT: {self.stack_height}")
            lines.append(f"STACK_DIAMETER: {self.stack_diameter}")
            if self.stack_temp is None:
                lines.append("STACK_TEMP: AMBIENT")
            else:
                lines.append(f"STACK_TEMP: {self.stack_temp}")
            lines.append(f"EXIT_VELOCITY: {self.exit_velocity}")
        elif st == AERSCREENSourceType.AREA:
            lines.append(f"RELEASE_HEIGHT: {self.stack_height or 0.0}")
            lines.append(f"AREA_LENGTH: {self.area_length}")
            lines.append(f"AREA_WIDTH: {self.area_width}")
        elif st == AERSCREENSourceType.VOLUME:
            lines.append(f"RELEASE_HEIGHT: {self.stack_height or 0.0}")
            lines.append(f"INITIAL_SIGMA_Z: {self.initial_sigma_z}")
            lines.append(f"LATERAL_DIM: {self.lateral_dim}")
            lines.append(f"VERTICAL_DIM: {self.vertical_dim}")

        lines.append(f"URBAN_RURAL: {'U' if self.urban else 'R'}")
        if self.urban:
            lines.append(f"POPULATION: {self.population}")
        if self.dominant_landuse is not None:
            lines.append(f"DOMINANT_LU: {self.dominant_landuse}")
        lines.append(f"TEMP_MIN_K: {self.temp_min_k}")
        lines.append(f"TEMP_MAX_K: {self.temp_max_k}")
        lines.append(f"ANEMOMETER_HEIGHT: {self.anemometer_height}")
        lines.append(f"USE_ADJU: {'Y' if self.use_adju else 'N'}")

        lines.append(f"DOWNWASH: {'Y' if self.downwash else 'N'}")
        if self.downwash:
            lines.append(f"BUILDING_HEIGHT: {self.building_height}")
            lines.append(f"BUILDING_LENGTH: {self.building_length}")
            lines.append(f"BUILDING_WIDTH: {self.building_width}")
            lines.append(f"BUILDING_ANGLE: {self.building_angle}")

        lines.append(f"TERRAIN: {'Y' if self.terrain else 'N'}")
        if self.terrain:
            lines.append(f"LAT: {self.lat}")
            lines.append(f"LON: {self.lon}")
            if self.terrain_file:
                lines.append(f"TERRAIN_FILE: {self.terrain_file}")

        lines.append(f"FUMIGATION: {'Y' if self.fumigation else 'N'}")

        if isinstance(self.distances, str):
            lines.append("DISTANCES: AUTO")
        else:
            d_str = " ".join(f"{d:g}" for d in self.distances)
            lines.append(f"DISTANCES: {d_str}")

        lines.extend(self.extra_lines)
        return "\n".join(lines) + "\n"


__all__ = [
    "AERSCREENConfig",
    "AERSCREENSourceType",
]
