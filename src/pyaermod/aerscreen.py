"""
AERSCREEN configuration: the prompt answers and the restart file.

EPA's AERSCREEN is the single-source screening front-end to AERMOD. It
generates screening meteorology with MAKEMET, runs AERMOD over it (and
BPIP-PRIME and AERMAP when asked to), and reports worst-case 1-hour
impacts with the scaled 3-, 8-, 24-hour and annual values -- the first
step of a permit analysis, deciding whether refined modelling is needed.

AERSCREEN has no keyword input deck. It is **interactive**: it asks an
ordered sequence of questions on stdin (title, units, source type, the
source parameters, downwash, terrain, meteorology, fumigation, debug,
output file name, then a validation page whose ``<Enter>`` starts the
run). It can also **restart** from a previous run: if ``aerscreen.inp``
exists in the working directory, it parses the ``**``-prefixed header
that its own runs leave at the top of that file (the rest of the file
is the AERMOD runstream of the last refinement stage), shows the title,
and asks whether to continue with it. Both were read off
``AERSCREEN.FOR`` (subroutines ``initprompts``, ``stacks``, ``downwash``,
``getDEMs``, ``metdata``, ``fuminp``, ``setdebug``, ``getoutfil``,
``validate`` for the prompts; ``readinp`` and ``makeinput`` for the
header) and checked against every deck in EPA's
``aerscreen_test_cases.zip``.

This module is the parameter container for one run and produces both
forms:

* :meth:`AERSCREENConfig.to_stdin_answers` -- the answers, one per
  prompt, in the order AERSCREEN asks them (metric units throughout).
* :meth:`AERSCREENConfig.to_aerscreen_input` -- the restart file: the
  ``**`` header in AERSCREEN's own column layout, byte for byte, plus
  the ``CO`` pathway it also reads (title, BPIP file, NO2 chemistry).
* :meth:`AERSCREENConfig.from_aerscreen_input` -- the parser for that
  header, so an EPA-published or previously generated deck round-trips.

Binary dispatch lives in :mod:`pyaermod.aerscreen_runner`, which feeds
either form to a locally built AERSCREEN (``scripts/build_aerscreen.sh``)
and stages the programs it spawns.

Typical usage::

    from pyaermod import AERSCREENConfig, AERSCREENSourceType

    cfg = AERSCREENConfig(
        title="SO2 stack screening",
        source_type=AERSCREENSourceType.POINT,
        emission_rate=10.0,           # g/s
        stack_height=30.0,            # m
        stack_diameter=2.0,           # m
        stack_temp=425.0,             # K (None for ambient)
        exit_velocity=15.0,           # m/s
        albedo=0.16, bowen_ratio=0.8, roughness_length=0.1,
    )
    answers = cfg.to_stdin_answers()      # what the runner types
    deck = cfg.to_aerscreen_input()       # or the restart file

The earlier release of this module wrote a ``KEY: value`` deck that
AERSCREEN never reads; the fields that described things AERSCREEN has no
notion of were renamed or dropped, and passing an old name raises a
:class:`TypeError` naming its replacement.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# ---------------------------------------------------------------------------
# Source types
# ---------------------------------------------------------------------------

class AERSCREENSourceType(StrEnum):
    """The seven source types AERSCREEN's opening prompt offers.

    ``CAPPED`` and ``HORIZONTAL`` are aliases kept from the previous
    release; their values are AERSCREEN's own keywords.
    """
    POINT = "POINT"
    VOLUME = "VOLUME"
    AREA = "AREA"
    AREACIRC = "AREACIRC"
    FLARE = "FLARE"
    POINTCAP = "POINTCAP"
    POINTHOR = "POINTHOR"
    CAPPED = "POINTCAP"
    HORIZONTAL = "POINTHOR"

    @property
    def prompt_letter(self) -> str:
        """The letter the source-type prompt takes (P, V, A, C, F, S, H)."""
        return _PROMPT_LETTER[self]

    @property
    def header_keyword(self) -> str:
        """The ``** ... DATA`` keyword of the restart-file source block."""
        return _HEADER_KEYWORD[self]

    @property
    def is_stack(self) -> bool:
        """POINT, POINTCAP or POINTHOR: a stack with diameter and velocity."""
        return self in (AERSCREENSourceType.POINT,
                        AERSCREENSourceType.POINTCAP,
                        AERSCREENSourceType.POINTHOR)

    @property
    def is_elevated_release(self) -> bool:
        """Stack-like sources: the ones downwash and fumigation apply to."""
        return self.is_stack or self is AERSCREENSourceType.FLARE


_PROMPT_LETTER = {
    AERSCREENSourceType.POINT: "P",
    AERSCREENSourceType.VOLUME: "V",
    AERSCREENSourceType.AREA: "A",
    AERSCREENSourceType.AREACIRC: "C",
    AERSCREENSourceType.FLARE: "F",
    AERSCREENSourceType.POINTCAP: "S",
    AERSCREENSourceType.POINTHOR: "H",
}

_HEADER_KEYWORD = {
    AERSCREENSourceType.POINT: "STACK DATA",
    AERSCREENSourceType.VOLUME: "VOLUME DATA",
    AERSCREENSourceType.AREA: "AREA DATA",
    AERSCREENSourceType.AREACIRC: "AREACIRC DATA",
    AERSCREENSourceType.FLARE: "FLARE DATA",
    AERSCREENSourceType.POINTCAP: "POINTCAP DATA",
    AERSCREENSourceType.POINTHOR: "POINTHOR DATA",
}

#: AERMET's eight land-use categories, for ``land_use`` (the surface
#: characteristics prompt's option 2 takes one of these plus a climate).
AERMET_LAND_USE: Dict[int, str] = {
    1: "Water", 2: "Deciduous Forest", 3: "Coniferous Forest", 4: "Swamp",
    5: "Cultivated Land", 6: "Grassland", 7: "Urban", 8: "Desert Shrubland",
}

#: The three moisture climates that go with ``land_use``.
AERMET_CLIMATE: Dict[int, str] = {
    1: "Average Moisture", 2: "Wet Conditions", 3: "Dry Conditions",
}

_OZONE_UNITS = ("UG/M3", "PPM", "PPB")
_NO2_METHODS = ("OLM", "PVMRM")
_DATUM_CODE = {"NAD27": 1, "NAD83": 4}
_CODE_DATUM = {1: "NAD27", 4: "NAD83"}
_DEM_TYPES = ("DEM", "NED")

#: Name the runner gives the discrete-receptor file it writes from
#: ``discrete_receptors`` when no ``discrete_receptor_file`` is named.
DISCRETE_RECEPTOR_FILE = "aerscreen_discrete.txt"

#: AERSCREEN's ceiling on discrete receptors (``maxdisc``).
MAX_DISCRETE_RECEPTORS = 10


# ---------------------------------------------------------------------------
# Old field names
# ---------------------------------------------------------------------------

#: Old field name -> new field name.
_RENAMED_FIELDS: Dict[str, str] = {
    "lateral_dim": "lateral_dimension",
    "vertical_dim": "vertical_dimension",
    "initial_sigma_z": "vertical_dimension",
    "dominant_landuse": "land_use",
    "terrain_file": "dem_files",
    "distances": "discrete_receptors",
}

#: Old field name -> why there is no direct replacement.
_REMOVED_FIELDS: Dict[str, str] = {
    "extra_lines": (
        "AERSCREEN takes a fixed sequence of prompt answers, not free "
        "keyword lines. There is nothing to append them to."
    ),
}


def _reject_legacy_kwargs(kwargs: Dict[str, Any]) -> None:
    """Raise a TypeError naming the replacement for an old field name."""
    for old, new in _RENAMED_FIELDS.items():
        if old in kwargs:
            raise TypeError(
                f"AERSCREENConfig has no field {old!r}; it is now {new!r}. "
                "The old fields described a KEY: value deck AERSCREEN never "
                "read -- see the CHANGELOG upgrade notes."
            )
    for old, why in _REMOVED_FIELDS.items():
        if old in kwargs:
            raise TypeError(f"AERSCREENConfig has no field {old!r}. {why}")


# ---------------------------------------------------------------------------
# Fortran edit descriptors
# ---------------------------------------------------------------------------
# The restart header is written by AERSCREEN's makeinput with fixed
# FORMATs; these reproduce the Fw.d, Ew.d and Iw editing so the header
# pyaermod writes is the header AERSCREEN writes, byte for byte.

def _f(value: float, width: int, decimals: int) -> str:
    """Fortran ``Fw.d``."""
    text = f"{value:.{decimals}f}"
    if decimals == 0:
        text += "."
    if text.startswith("-") and float(text) == 0.0:
        text = text[1:]
    if len(text) > width:
        return "*" * width
    return text.rjust(width)


def _e(value: float, width: int, decimals: int) -> str:
    """Fortran ``Ew.d``: ``0.dddd`` mantissa and a two-digit exponent."""
    if value == 0.0:
        text = "0." + "0" * decimals + "E+00"
    else:
        exponent = math.floor(math.log10(abs(value))) + 1
        mantissa = f"{abs(value) / 10 ** exponent:.{decimals}f}"
        if mantissa.startswith("1."):        # rounded up to 1.0000
            exponent += 1
            mantissa = f"{abs(value) / 10 ** exponent:.{decimals}f}"
        sign = "-" if value < 0 else ""
        text = f"{sign}{mantissa}E{exponent:+03d}"
    if len(text) > width:
        return "*" * width
    return text.rjust(width)


def _i(value: int, width: int) -> str:
    """Fortran ``Iw``."""
    text = str(int(value))
    if len(text) > width:
        return "*" * width
    return text.rjust(width)


def _stack_flow_rate(velocity: float, diameter: float) -> float:
    """Stack flow in ACFM, as AERSCREEN computes it (``stacks``)."""
    return velocity * diameter ** 2 / 0.0006009


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class AERSCREENConfig:
    """Everything AERSCREEN asks for one run, in metric units.

    Parameters
    ----------
    title
        Run title (AERSCREEN keeps 60 characters).
    source_type
        One of :class:`AERSCREENSourceType`; a string is coerced.
    emission_rate
        Emission rate in g/s.
    stack_height
        Release height in metres: the stack height of POINT / POINTCAP /
        POINTHOR, the flare stack height of FLARE, the centre height of
        VOLUME, the release height of AREA / AREACIRC. Required.
    stack_diameter, exit_velocity
        Stack inner diameter (m) and exit velocity (m/s). Required for
        the three stack types.
    stack_temp
        Stack exit temperature in K. ``None`` or ``0`` means ambient;
        a negative value is a temperature difference above ambient.
    flare_heat_release, flare_heat_loss
        FLARE total heat release (cal/s) and radiative heat-loss
        fraction (AERSCREEN's default 0.55).
    lateral_dimension, vertical_dimension
        VOLUME initial lateral and vertical dimensions (m). The vertical
        dimension is also asked of AREA and AREACIRC.
    area_length, area_width
        AREA long and short sides (m). AERSCREEN swaps them if given the
        other way round.
    radius
        AREACIRC radius (m).
    urban, population
        Urban dispersion and the urban population (> 100), required when
        ``urban=True``.
    ambient_distance
        Minimum distance to ambient air (m). ``None`` takes AERSCREEN's
        default: 1 m, or ``2.15 * lateral_dimension + 1`` for VOLUME.
    no2_method, no2_stack_ratio, ozone_concentration, ozone_units
        NO2 chemistry: ``None`` (none), ``"OLM"`` or ``"PVMRM"``, with the
        in-stack NO2/NOx ratio (0-1) and the background ozone in
        ``"UG/M3"``, ``"PPM"`` or ``"PPB"``.
    downwash
        Building downwash (stack types and FLARE only). Either name a
        pre-existing BPIP-PRIME input file in ``bpip_file`` or give the
        single building: ``building_height``, ``building_length`` (max
        horizontal dimension), ``building_width`` (min), ``building_angle``
        (orientation of the long side from north, 0-179),
        ``stack_direction`` (direction of the stack from the building
        centre, 0-360) and ``stack_distance`` (m).
    terrain
        Include terrain heights (AERMAP is run). Needs the source
        location -- ``lat``/``lon`` or ``utm_easting``/``utm_northing``
        with ``utm_zone`` -- ``datum`` (``"NAD83"`` or ``"NAD27"``),
        ``dem_files`` of type ``dem_type`` (``"NED"`` or ``"DEM"``) and
        the NADCON grid files in ``nad_grid_dir``. Not for AREA.
    probe_distance
        Maximum distance to probe (m); ``None`` takes AERSCREEN's default
        of 5000 m, or 10000 m with terrain. AERSCREEN rounds it up to a
        multiple of 25 m.
    discrete_receptors, discrete_receptor_file
        Up to ten discrete receptor distances (m), or a file already in
        AERSCREEN's format (``units: meters`` then one distance per line).
    flagpole_height
        Flagpole receptor height (m); ``None`` for none.
    source_elevation, aermap_elevation
        Source base elevation (m). ``None`` means 0 m, or the
        AERMAP-derived elevation when ``terrain=True``; ``aermap_elevation``
        says so explicitly (AERSCREEN keeps the elevation AERMAP found in
        the restart file next to that flag).
    temp_min_k, temp_max_k, min_wind_speed, anemometer_height
        MAKEMET meteorology: ambient temperature range (K), minimum wind
        speed (m/s) and anemometer height (m). AERSCREEN's defaults.
    albedo, bowen_ratio, roughness_length
        Single user-specified surface characteristics.
    land_use, climate
        AERMET seasonal tables instead: :data:`AERMET_LAND_USE` code and
        :data:`AERMET_CLIMATE` code.
    surface_file
        An AERSURFACE output file (``FREQ_SECT`` / ``SECTOR`` /
        ``SITE_CHAR`` lines) instead. Exactly one of the three surface
        options must be given.
    use_adju
        Apply the ADJ_U* low-wind adjustment in MAKEMET.
    fumigation, shoreline_fumigation, shoreline_distance, shoreline_direction
        Inversion break-up and shoreline fumigation (stack types and
        FLARE with a release height of at least 10 m). Shoreline needs
        the minimum distance to the shoreline (m, at most 3000) and an
        optional direction (degrees; ``None`` for none).
    run_aermod
        ``False`` skips the AERMOD screening and keeps only the
        fumigation calculations (AERSCREEN's "Run AERSCREEN: N").
    debug
        Write the per-receptor concentration debug file.
    output_file
        Output file name; must end in ``.out`` / ``.OUT``. AERSCREEN
        derives the log, restart and maximum-concentration file names
        from it.
    """

    title: str
    source_type: AERSCREENSourceType
    emission_rate: float

    # Release geometry
    stack_height: Optional[float] = None
    stack_diameter: Optional[float] = None
    stack_temp: Optional[float] = None
    exit_velocity: Optional[float] = None
    flare_heat_release: Optional[float] = None
    flare_heat_loss: float = 0.55
    lateral_dimension: Optional[float] = None
    vertical_dimension: Optional[float] = None
    area_length: Optional[float] = None
    area_width: Optional[float] = None
    radius: Optional[float] = None

    # Dispersion environment
    urban: bool = False
    population: Optional[float] = None
    ambient_distance: Optional[float] = None

    # NO2 chemistry
    no2_method: Optional[str] = None
    no2_stack_ratio: Optional[float] = None
    ozone_concentration: Optional[float] = None
    ozone_units: str = "PPB"

    # Building downwash
    downwash: bool = False
    bpip_file: Optional[str] = None
    building_height: Optional[float] = None
    building_length: Optional[float] = None
    building_width: Optional[float] = None
    building_angle: Optional[float] = None
    stack_direction: Optional[float] = None
    stack_distance: Optional[float] = None

    # Terrain and receptors
    terrain: bool = False
    probe_distance: Optional[float] = None
    discrete_receptors: Sequence[float] = ()
    discrete_receptor_file: Optional[str] = None
    flagpole_height: Optional[float] = None
    source_elevation: Optional[float] = None
    aermap_elevation: Optional[bool] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    utm_easting: Optional[float] = None
    utm_northing: Optional[float] = None
    utm_zone: Optional[int] = None
    datum: Optional[str] = None
    dem_files: Sequence[str] = ()
    dem_type: str = "NED"
    nad_grid_dir: Optional[str] = None

    # MAKEMET meteorology
    temp_min_k: float = 250.0
    temp_max_k: float = 310.0
    min_wind_speed: float = 0.5
    anemometer_height: float = 10.0
    albedo: Optional[float] = None
    bowen_ratio: Optional[float] = None
    roughness_length: Optional[float] = None
    land_use: Optional[int] = None
    climate: Optional[int] = None
    surface_file: Optional[str] = None
    use_adju: bool = False

    # Fumigation
    fumigation: bool = False
    shoreline_fumigation: bool = False
    shoreline_distance: Optional[float] = None
    shoreline_direction: Optional[float] = None
    run_aermod: bool = True

    # Output
    debug: bool = False
    output_file: str = "AERSCREEN.OUT"

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        if isinstance(self.source_type, str) and not isinstance(
            self.source_type, AERSCREENSourceType
        ):
            try:
                self.source_type = AERSCREENSourceType(
                    self.source_type.upper()
                )
            except ValueError:
                raise ValueError(
                    f"source_type {self.source_type!r} is not one of "
                    f"{[t.value for t in AERSCREENSourceType]}"
                ) from None
        st = self.source_type

        if self.emission_rate <= 0:
            raise ValueError("emission_rate must be > 0 g/s")
        if self.stack_height is None or self.stack_height < 0:
            raise ValueError(
                f"{st.value} sources require stack_height >= 0 m "
                "(the release height)"
            )

        if st.is_stack:
            if self.stack_diameter is None or self.stack_diameter <= 0:
                raise ValueError(f"{st.value} sources require stack_diameter > 0")
            if self.exit_velocity is None or self.exit_velocity < 0:
                raise ValueError(
                    f"{st.value} sources require exit_velocity >= 0"
                )
        elif st is AERSCREENSourceType.FLARE:
            if self.flare_heat_release is None or self.flare_heat_release <= 0:
                raise ValueError(
                    "FLARE sources require flare_heat_release > 0 (cal/s)"
                )
            if not 0.0 <= self.flare_heat_loss <= 1.0:
                raise ValueError("flare_heat_loss must be in [0, 1]")
        elif st is AERSCREENSourceType.VOLUME:
            for fname in ("lateral_dimension", "vertical_dimension"):
                v = getattr(self, fname)
                if v is None or v < 0:
                    raise ValueError(f"VOLUME sources require {fname} >= 0")
        elif st is AERSCREENSourceType.AREA:
            if self.area_length is None or self.area_length <= 0:
                raise ValueError("AREA sources require area_length > 0")
            if self.area_width is None or self.area_width <= 0:
                raise ValueError("AREA sources require area_width > 0")
            if self.vertical_dimension is None:
                self.vertical_dimension = 0.0
            if self.area_width > self.area_length:
                # AERSCREEN swaps them and says so; do it here so the
                # header and the answers agree with what it will use.
                self.area_length, self.area_width = (
                    self.area_width, self.area_length
                )
        elif st is AERSCREENSourceType.AREACIRC:
            if self.radius is None or self.radius <= 0:
                raise ValueError("AREACIRC sources require radius > 0")
            if self.vertical_dimension is None:
                self.vertical_dimension = 0.0

        if self.urban and (self.population is None or self.population <= 100):
            raise ValueError(
                "urban=True requires population > 100 (AERSCREEN's floor)"
            )
        if self.ambient_distance is not None and self.ambient_distance <= 0:
            raise ValueError("ambient_distance must be > 0 m")

        if self.no2_method is not None:
            self.no2_method = self.no2_method.upper()
            if self.no2_method not in _NO2_METHODS:
                raise ValueError(f"no2_method must be one of {_NO2_METHODS}")
            if (self.no2_stack_ratio is None
                    or not 0.0 <= self.no2_stack_ratio <= 1.0):
                raise ValueError(
                    f"no2_method={self.no2_method} requires no2_stack_ratio "
                    "in [0, 1]"
                )
            if self.ozone_concentration is None or self.ozone_concentration < 0:
                raise ValueError(
                    f"no2_method={self.no2_method} requires "
                    "ozone_concentration >= 0"
                )
            self.ozone_units = self.ozone_units.upper()
            if self.ozone_units not in _OZONE_UNITS:
                raise ValueError(f"ozone_units must be one of {_OZONE_UNITS}")

        if self.downwash:
            if not st.is_elevated_release:
                raise ValueError(
                    f"{st.value} sources have no building downwash in AERSCREEN"
                )
            if self.bpip_file is None:
                for fname in ("building_height", "building_length",
                              "building_width", "building_angle",
                              "stack_direction", "stack_distance"):
                    if getattr(self, fname) is None:
                        raise ValueError(
                            f"downwash=True requires {fname} (or bpip_file)"
                        )
                assert self.building_length is not None
                assert self.building_width is not None
                assert self.building_angle is not None
                assert self.stack_direction is not None
                assert self.stack_distance is not None
                if self.building_height is None or self.building_height <= 0:
                    raise ValueError("building_height must be > 0")
                if self.building_width <= 0 or self.building_length <= 0:
                    raise ValueError("building dimensions must be > 0")
                if self.building_width > self.building_length:
                    raise ValueError(
                        "building_width (minimum horizontal dimension) cannot "
                        "exceed building_length (maximum)"
                    )
                if not 0 <= self.building_angle <= 179:
                    raise ValueError("building_angle must be in [0, 179] degrees")
                if not 0 <= self.stack_direction <= 360:
                    raise ValueError("stack_direction must be in [0, 360] degrees")
                if self.stack_distance < 0:
                    raise ValueError("stack_distance must be >= 0 m")

        if self.terrain:
            if st is AERSCREENSourceType.AREA:
                raise ValueError(
                    "AERSCREEN does not model terrain for rectangular AREA sources"
                )
            has_latlon = self.lat is not None and self.lon is not None
            has_utm = (self.utm_easting is not None
                       and self.utm_northing is not None
                       and self.utm_zone is not None)
            if not (has_latlon or has_utm):
                raise ValueError(
                    "terrain=True requires lat and lon, or utm_easting, "
                    "utm_northing and utm_zone"
                )
            if has_latlon:
                assert self.lat is not None and self.lon is not None
                if not -90 <= self.lat <= 90:
                    raise ValueError("lat must be in [-90, 90]")
                if not -180 <= self.lon <= 180:
                    raise ValueError("lon must be in [-180, 180]")
            if self.datum is None:
                self.datum = "NAD83"
        if self.aermap_elevation is None:
            self.aermap_elevation = self.terrain and self.source_elevation is None
        elif self.aermap_elevation and not self.terrain:
            raise ValueError("aermap_elevation=True needs terrain=True")
        if self.datum is not None:
            self.datum = self.datum.upper()
            if self.datum not in _DATUM_CODE:
                raise ValueError("datum must be 'NAD83' or 'NAD27'")
        self.dem_type = self.dem_type.upper()
        if self.dem_type not in _DEM_TYPES:
            raise ValueError("dem_type must be 'NED' or 'DEM'")
        if self.utm_zone is not None and self.utm_zone <= 0:
            raise ValueError("utm_zone must be > 0")

        if self.probe_distance is not None and self.probe_distance <= 0:
            raise ValueError("probe_distance must be > 0 m")
        self.discrete_receptors = tuple(float(d) for d in self.discrete_receptors)
        if len(self.discrete_receptors) > MAX_DISCRETE_RECEPTORS:
            raise ValueError(
                f"AERSCREEN takes at most {MAX_DISCRETE_RECEPTORS} discrete receptors"
            )
        if any(d <= 0 for d in self.discrete_receptors):
            raise ValueError("all discrete_receptors must be > 0 m")
        if self.flagpole_height is not None and self.flagpole_height < 0:
            raise ValueError("flagpole_height must be >= 0 m")

        if self.temp_min_k >= self.temp_max_k:
            raise ValueError("temp_min_k must be < temp_max_k")
        if self.min_wind_speed <= 0:
            raise ValueError("min_wind_speed must be > 0 m/s")
        if self.anemometer_height < 0:
            raise ValueError("anemometer_height must be >= 0 m")

        user_sc = any(v is not None for v in
                      (self.albedo, self.bowen_ratio, self.roughness_length))
        n_options = sum(
            (self.surface_file is not None, self.land_use is not None, user_sc)
        )
        if n_options != 1:
            raise ValueError(
                "give exactly one surface-characteristics option: "
                "albedo/bowen_ratio/roughness_length, land_use (+climate), "
                "or surface_file"
            )
        if self.land_use is not None:
            if self.land_use not in AERMET_LAND_USE:
                raise ValueError(
                    f"land_use must be an AERMET code in {sorted(AERMET_LAND_USE)}"
                )
            if self.climate is None:
                self.climate = 1
            if self.climate not in AERMET_CLIMATE:
                raise ValueError(
                    f"climate must be an AERMET code in {sorted(AERMET_CLIMATE)}"
                )
        if user_sc:
            for fname in ("albedo", "bowen_ratio", "roughness_length"):
                if getattr(self, fname) is None:
                    raise ValueError(
                        "user-specified surface characteristics need all of "
                        "albedo, bowen_ratio and roughness_length"
                    )
            assert self.albedo is not None and self.roughness_length is not None
            if not 0.0 <= self.albedo <= 1.0:
                raise ValueError("albedo must be in [0, 1]")
            if self.roughness_length < 0:
                raise ValueError("roughness_length must be >= 0 m")

        if (self.fumigation or self.shoreline_fumigation) and not self.fumigation_allowed:
            raise ValueError(
                "AERSCREEN applies fumigation only to POINT, POINTCAP, "
                "POINTHOR and FLARE sources with a release height of at "
                "least 10 m"
            )
        if self.shoreline_fumigation:
            if (self.shoreline_distance is None
                    or not 0.0 <= self.shoreline_distance <= 3000.0):
                raise ValueError(
                    "shoreline_fumigation=True requires shoreline_distance in "
                    "[0, 3000] m"
                )
            if (self.shoreline_direction is not None
                    and not 0.0 <= self.shoreline_direction <= 360.0):
                raise ValueError("shoreline_direction must be in [0, 360] degrees")
        if not self.run_aermod and not (self.fumigation or self.shoreline_fumigation):
            raise ValueError(
                "run_aermod=False leaves nothing to compute without "
                "fumigation or shoreline_fumigation"
            )

        if not self.output_file.upper().endswith(".OUT"):
            raise ValueError("output_file must end in .out or .OUT")

    # ------------------------------------------------------------------
    # Derived quantities
    # ------------------------------------------------------------------
    @property
    def effective_release_height(self) -> float:
        """The height AERSCREEN's fumigation eligibility test looks at.

        For FLARE that is the effective stack height it computes from the
        heat release (``stacks``, label 201), not the flare tip.
        """
        assert self.stack_height is not None
        if self.source_type is AERSCREENSourceType.FLARE:
            assert self.flare_heat_release is not None
            return self.stack_height + 4.56e-3 * self.flare_heat_release ** 0.478
        return self.stack_height

    @property
    def fumigation_allowed(self) -> bool:
        """Whether AERSCREEN would offer the fumigation prompts at all."""
        return (self.source_type.is_elevated_release
                and self.effective_release_height >= 10.0)

    @property
    def surface_code(self) -> int:
        """AERSCREEN's ``isurf``: 0 user values, 1-8 AERMET land use, 9 file."""
        if self.surface_file is not None:
            return 9
        if self.land_use is not None:
            return self.land_use
        return 0

    @property
    def discrete_receptor_filename(self) -> Optional[str]:
        """Basename of the discrete-receptor file the header names."""
        if self.discrete_receptor_file is not None:
            return Path(self.discrete_receptor_file).name
        if self.discrete_receptors:
            return DISCRETE_RECEPTOR_FILE
        return None

    @property
    def staged_input_files(self) -> List[str]:
        """Files the run needs beside it: the runner copies these in."""
        files: List[str] = []
        for name in (self.surface_file, self.discrete_receptor_file,
                     self.bpip_file):
            if name is not None:
                files.append(name)
        files.extend(self.dem_files)
        return files

    # ------------------------------------------------------------------
    # Prompt answers
    # ------------------------------------------------------------------
    def to_stdin_answers(self) -> List[str]:
        """The answers, one per prompt, in the order AERSCREEN asks.

        This is the data-entry pass of ``AERSCREEN.FOR`` with no
        ``aerscreen.inp`` present: ``initprompts``, ``stacks(0)``,
        ``downwash(0)``, ``getDEMs(0)``, ``metdata(0)``, ``fuminp(0)``,
        ``setdebug(0)``, ``getoutfil``, then ``validate``. An empty
        string is a bare ``<Enter>``, which takes AERSCREEN's default
        where one is offered.
        """
        st = self.source_type
        a: List[str] = [self.title, "M", st.prompt_letter]

        # stacks(0): emission rate, then the geometry of the type
        a.append(_num(self.emission_rate))
        assert self.stack_height is not None
        if st.is_stack:
            assert self.stack_diameter is not None
            assert self.exit_velocity is not None
            a += [_num(self.stack_height), _num(self.stack_diameter),
                  _num(self.stack_temp or 0.0),
                  "1",                              # option 1: velocity in m/s
                  _num(self.exit_velocity)]
        elif st is AERSCREENSourceType.FLARE:
            assert self.flare_heat_release is not None
            a += [_num(self.stack_height), _num(self.flare_heat_release),
                  _num(self.flare_heat_loss)]
        elif st is AERSCREENSourceType.VOLUME:
            assert self.lateral_dimension is not None
            assert self.vertical_dimension is not None
            a += [_num(self.stack_height), _num(self.lateral_dimension),
                  _num(self.vertical_dimension)]
        elif st is AERSCREENSourceType.AREA:
            assert self.area_length is not None and self.area_width is not None
            assert self.vertical_dimension is not None
            a += [_num(self.stack_height), _num(self.area_length),
                  _num(self.area_width), _num(self.vertical_dimension)]
        else:  # AREACIRC
            assert self.radius is not None and self.vertical_dimension is not None
            a += [_num(self.stack_height), _num(self.radius),
                  _num(self.vertical_dimension)]
        # rural/urban, ambient distance, NO2 chemistry
        if self.urban:
            assert self.population is not None
            a += ["U", _num(self.population)]
        else:
            a.append("R")
        a.append("" if self.ambient_distance is None else _num(self.ambient_distance))
        if self.no2_method is None:
            a.append("1")
        else:
            assert self.no2_stack_ratio is not None
            assert self.ozone_concentration is not None
            a += ["2" if self.no2_method == "OLM" else "3",
                  _num(self.no2_stack_ratio),
                  str(_OZONE_UNITS.index(self.ozone_units) + 1),
                  _num(self.ozone_concentration)]

        # downwash(0): only for the elevated releases
        if st.is_elevated_release:
            if not self.downwash:
                a.append("N")
            elif self.bpip_file is not None:
                a += ["Y", "Y", _quoted_if_needed(Path(self.bpip_file).name)]
            else:
                assert self.building_height is not None
                assert self.building_length is not None
                assert self.building_width is not None
                assert self.building_angle is not None
                assert self.stack_direction is not None
                assert self.stack_distance is not None
                a += ["Y", "N", _num(self.building_height),
                      _num(self.building_length), _num(self.building_width),
                      _num(self.building_angle), _num(self.stack_direction),
                      _num(self.stack_distance)]

        # getDEMs(0)
        if st is not AERSCREENSourceType.AREA:
            a.append("Y" if self.terrain else "N")
        a.append("" if self.probe_distance is None else _num(self.probe_distance))
        disc = self.discrete_receptor_filename
        if disc is None:
            a.append("N")
        else:
            a += ["Y", _quoted_if_needed(disc)]
        if self.flagpole_height is None:
            a.append("N")
        else:
            a += ["Y", _num(self.flagpole_height)]
        if self.aermap_elevation or self.source_elevation is None:
            a.append("")
        else:
            a.append(_num(self.source_elevation))
        if self.terrain:
            if self.lat is not None and self.lon is not None:
                a += ["LATLON", _num(self.lat), _num(self.lon)]
            else:
                assert self.utm_easting is not None
                assert self.utm_northing is not None
                assert self.utm_zone is not None
                a += ["UTM", _num(self.utm_easting), _num(self.utm_northing),
                      str(self.utm_zone)]
            a.append(str(_DATUM_CODE[self.datum or "NAD83"]))

        # metdata(0)
        if (self.temp_min_k, self.temp_max_k) == (250.0, 310.0):
            a.append("")
        else:
            a += [_num(self.temp_min_k), _num(self.temp_max_k)]
        a.append("" if self.min_wind_speed == 0.5 else _num(self.min_wind_speed))
        a.append("" if self.anemometer_height == 10.0 else _num(self.anemometer_height))
        code = self.surface_code
        if code == 0:
            assert self.albedo is not None and self.bowen_ratio is not None
            assert self.roughness_length is not None
            a += ["1", _num(self.albedo), _num(self.bowen_ratio),
                  _num(self.roughness_length)]
        elif code == 9:
            assert self.surface_file is not None
            a += ["3", _quoted_if_needed(Path(self.surface_file).name)]
        else:
            assert self.climate is not None
            a += ["2", str(self.land_use), str(self.climate)]
        a.append("Y" if self.use_adju else "N")

        # fuminp(0): offered only where fumigation can apply
        if self.fumigation_allowed:
            a.append("Y" if self.fumigation else "N")
            a.append("Y" if self.shoreline_fumigation else "N")
            if self.shoreline_fumigation:
                assert self.shoreline_distance is not None
                a.append(_num(self.shoreline_distance))
                a.append("" if self.shoreline_direction is None
                         else _num(self.shoreline_direction))

        # setdebug(0), getoutfil
        a.append("Y" if self.debug else "")
        a.append("" if self.output_file.upper() == "AERSCREEN.OUT"
                 else _quoted_if_needed(self.output_file))

        # validate: the data-entry pass never asks "Run AERSCREEN?", so
        # switching AERMOD off goes through the fumigation menu (option
        # 5 on the validation page), whose "Do not run AERSCREEN" entry
        # is numbered by which fumigation options are on.
        if not self.run_aermod:
            option = "3" if (self.fumigation and not self.shoreline_fumigation) else "5"
            a += ["5", option, ""]
        a.append("")                                  # <Enter> to start
        return a

    # ------------------------------------------------------------------
    # Restart file
    # ------------------------------------------------------------------
    def to_aerscreen_input(self) -> str:
        """The restart file AERSCREEN reads from ``aerscreen.inp``.

        The ``**`` header uses the exact column layout of AERSCREEN's
        ``makeinput`` FORMATs, followed by the ``CO`` pathway keywords
        ``readinp`` also reads. Values AERSCREEN fills in from a run
        (stack flow rate, the surface characteristics of the dominant
        sector) are computed or carried through so a parsed EPA deck
        writes back identically.

        One quirk of the reader on the other side: it keeps the title
        only up to its first comma, upper-cased (the whole line is
        upper-cased before the keyword is matched). A run restarted from
        this file reports that shortened title; the answers of
        :meth:`to_stdin_answers` keep it whole.
        """
        st = self.source_type
        lines: List[str] = []
        assert self.stack_height is not None
        rate = _e(self.emission_rate, 12, 4)
        if st.is_stack:
            assert self.stack_diameter is not None
            assert self.exit_velocity is not None
            flow = _stack_flow_rate(self.exit_velocity, self.stack_diameter)
            lines += [
                f"** {st.header_keyword:<19}Rate    Height     Temp.  Velocity"
                "     Diam.     Flow",
                "**            " + rate + _f(self.stack_height, 10, 4)
                + _f(self.stack_temp or 0.0, 10, 4)
                + _f(self.exit_velocity, 10, 4) + _f(self.stack_diameter, 10, 4)
                + _f(flow, 10, 0),
            ]
        elif st is AERSCREENSourceType.FLARE:
            assert self.flare_heat_release is not None
            lines += [
                "** FLARE DATA         Rate    Height        Heat  HeatLoss",
                "**            " + rate + _f(self.stack_height, 10, 4)
                + _e(self.flare_heat_release, 12, 4) + _f(self.flare_heat_loss, 10, 3),
            ]
        elif st is AERSCREENSourceType.AREA:
            assert self.area_length is not None and self.area_width is not None
            assert self.vertical_dimension is not None
            lines += [
                "** AREA DATA          Rate    Height    Length     Width   Angle"
                "     Szinit",
                "**            " + rate + _f(self.stack_height, 10, 4)
                + _f(self.area_length, 10, 4) + _f(self.area_width, 10, 4)
                + "     0.0 " + _f(self.vertical_dimension, 10, 2),
            ]
        elif st is AERSCREENSourceType.AREACIRC:
            assert self.radius is not None and self.vertical_dimension is not None
            lines += [
                "** AREACIRC DATA      Rate    Height    Radius  NVerts      Szinit",
                "**            " + rate + _f(self.stack_height, 10, 4)
                + _f(self.radius, 10, 4) + "      20  "
                + _f(self.vertical_dimension, 10, 2),
            ]
        else:  # VOLUME
            assert self.lateral_dimension is not None
            assert self.vertical_dimension is not None
            lines += [
                "** VOLUME DATA        Rate    Height    Syinit    Szinit",
                "**            " + rate + _f(self.stack_height, 10, 4)
                + _f(self.lateral_dimension, 10, 4)
                + _f(self.vertical_dimension, 10, 4),
            ]

        bpip = "Y" if self.downwash else "N"
        lines += [
            "",
            "** BUILDING DATA   BPIP    Height  Max dim.  Min dim.   Orient."
            "   Direct.    Offset",
            "**                  " + bpip + "  "
            + "".join(_f(v or 0.0, 10, 4) for v in (
                self.building_height, self.building_length, self.building_width,
                self.building_angle, self.stack_direction, self.stack_distance)),
        ]

        code = self.surface_code
        sc_file = Path(self.surface_file).name if self.surface_file else "NA"
        # The header's albedo / Bowen / roughness columns are the user's
        # values for the user-specified option and AERSCREEN's own (the
        # dominant sector's) for the other two; keep the latter if a
        # parsed deck supplied them.
        if code != 0 and self._carried_surface is not None:
            albedo, bowen, zo = self._carried_surface
        else:
            albedo = self.albedo or 0.0
            bowen = self.bowen_ratio or 0.0
            zo = self.roughness_length or 0.0
        lines += [
            "",
            "** MAKEMET DATA    MinT    MaxT Speed   AnemHt Surf Clim  Albedo"
            "   Bowen  Length  SC FILE",
            "**             " + _f(self.temp_min_k, 8, 2) + _f(self.temp_max_k, 8, 2)
            + _f(self.min_wind_speed, 6, 1) + _f(self.anemometer_height, 9, 3)
            + _i(code, 5) + _i(self.climate or 0, 5)
            + _f(albedo, 9, 4) + _f(bowen, 9, 4) + _f(zo, 9, 4)
            + '  "' + sc_file + '"',
            "",
            "** ADJUST U*      " + ("Y" if self.use_adju else "N"),
        ]

        terrain = "Y" if self.terrain else "N"
        aermap = "Y" if self.aermap_elevation else "N"
        probe = self.probe_distance
        if probe is None:
            probe = 10000.0 if self.terrain else 5000.0
        lines += [
            "",
            "** TERRAIN DATA   Terrain    UTM East   UTM North  Zone  Nada"
            "     Probe     PROFBASE  Use AERMAP elev",
            "**                   " + terrain + "   "
            + _f(self.utm_easting or 0.0, 12, 1) + _f(self.utm_northing or 0.0, 12, 1)
            + _i(self.utm_zone or 0, 6)
            + _i(_DATUM_CODE[self.datum] if self.datum else 0, 6)
            + "     " + _f(probe, 8, 1) + "      "
            + _f(self.source_elevation or 0.0, 9, 2) + "         " + aermap,
        ]

        disc = self.discrete_receptor_filename
        lines += [
            "",
            "** DISCRETE RECEPTORS  Discflag   Receptor file",
            "**                      " + ("Y" if disc else "N") + "        "
            + '"' + (disc or "NA") + '"',
        ]

        flag = "Y" if self.flagpole_height is not None else "N"
        lines += [
            "",
            "** UNITS/POPULATION   Units   R/U  Population      Amb. dist."
            "   Flagpole    Flagpole height",
            "**                 " + "     M" + "     " + ("U" if self.urban else "R")
            + "  " + _f(self.population or 0.0, 12, 0) + "      "
            + _f(self.ambient_distance if self.ambient_distance is not None
                 else self._default_ambient_distance(), 10, 3)
            + "       " + flag + "    " + _f(self.flagpole_height or 0.0, 9, 2),
        ]

        direction = self.shoreline_direction
        if direction is None:
            direction = -9.0 if self.shoreline_fumigation else 0.0
        lines += [
            "",
            "** FUMIGATION        Inversion Break-up  Shoreline  Distance"
            "    Direct  Run AERSCREEN",
            "**                         " + ("Y" if self.fumigation else "N")
            + " " * 18 + ("Y" if self.shoreline_fumigation else "N") + " " * 6
            + _f(self.shoreline_distance or 0.0, 7, 2) + "  " + _f(direction, 7, 1)
            + "     " + ("Y" if self.run_aermod else "N"),
            "",
            "** DEBUG OPTION      Debug",
            "**                     " + ("Y" if self.debug else "N"),
            "",
            '** OUTPUT FILE "' + self.output_file + '"',
            "",
        ]

        # The CO pathway, as makeinput writes it (the stage comment and
        # the pathways after CO are the last AERMOD run's and are not
        # read back).
        options = "MODELOPT CONC SCREEN" + " " + "" + " " \
            + ("" if self.terrain else "FLAT") + " " \
            + ("FASTAREA" if st in (AERSCREENSourceType.AREA,
                                    AERSCREENSourceType.AREACIRC) else "") \
            + " " + (self.no2_method or "")
        co = ["CO STARTING", "   TITLEONE " + self.title[:60]]
        if self.bpip_file is not None:
            co.append('   TITLETWO "' + Path(self.bpip_file).name + '"')
        co.append("   " + options.strip())
        co.append("   AVERTIME 1")
        if self.urban:
            assert self.population is not None
            co.append("   URBANOPT" + _f(self.population, 10, 0))
        co.append("   POLLUTID " + ("NO2" if self.no2_method else "OTHER"))
        if self.no2_method:
            assert self.no2_stack_ratio is not None
            assert self.ozone_concentration is not None
            co.append("   NO2STACK " + _f(self.no2_stack_ratio, 6, 4))
            co.append("   OZONEVAL " + _f(self.ozone_concentration, 11, 4)
                      + " " + self.ozone_units)
        if self.flagpole_height is not None:
            co.append("   FLAGPOLE" + _f(self.flagpole_height, 9, 2))
        co += ["   RUNORNOT RUN", "CO FINISHED"]
        return "\n".join(lines + co) + "\n"

    def _default_ambient_distance(self) -> float:
        if self.source_type is AERSCREENSourceType.VOLUME:
            assert self.lateral_dimension is not None
            return max(2.15 * self.lateral_dimension + 1.0, 1.0)
        return 1.0

    # ------------------------------------------------------------------
    @classmethod
    def from_aerscreen_input(cls, text: str) -> AERSCREENConfig:
        """Parse a restart file (an ``aerscreen.inp`` header) back.

        Reads what ``readinp`` reads: the ``**`` data blocks with
        list-directed parsing (whitespace-separated, quoted file names),
        plus ``TITLEONE``, ``TITLETWO``, ``MODELOPT``, ``POLLUTID``,
        ``NO2STACK`` and ``OZONEVAL`` from the CO pathway.
        """
        blocks: Dict[str, List[str]] = {}
        title = ""
        bpip_file: Optional[str] = None
        no2_method: Optional[str] = None
        no2_ratio: Optional[float] = None
        ozone: Optional[float] = None
        ozone_units = "PPB"
        source_key: Optional[str] = None

        lines = text.replace("\r\n", "\n").split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            upper = line.upper()
            head = upper[:12]
            if head in _SOURCE_KEYS:
                source_key = head
                blocks["SOURCE"] = _tokens(lines[i + 1])[1:]
                i += 2
                continue
            for key in ("** BUILDING ", "** MAKEMET D", "** TERRAIN D",
                        "** DISCRETE ", "** UNITS/POP", "** FUMIGATIO",
                        "** DEBUG OPT"):
                if head == key:
                    blocks[key] = _tokens(lines[i + 1])[1:]
                    i += 2
                    break
            else:
                if "** ADJUST U*" in upper:
                    blocks["** ADJUST U*"] = _tokens(line[upper.index("** ADJUST U*") + 12:])
                elif "** OUTPUT FI" in upper:
                    blocks["** OUTPUT FI"] = _tokens(line[upper.index("** OUTPUT FILE") + 14:])
                elif head == "   TITLEONE ":
                    title = line[12:72].rstrip()
                elif head == "   TITLETWO ":
                    bpip_file = _tokens(line[12:])[0]
                elif head == "   MODELOPT ":
                    if " PVMRM" in upper + " ":
                        no2_method = "PVMRM"
                    elif " OLM" in upper + " ":
                        no2_method = "OLM"
                elif head == "   NO2STACK ":
                    no2_ratio = float(_tokens(line[12:])[0])
                elif head == "   OZONEVAL ":
                    toks = _tokens(line[12:])
                    ozone = float(toks[0])
                    if len(toks) > 1:
                        ozone_units = toks[1].upper()
                elif head == "CO FINISHED ":
                    break
                i += 1

        if source_key is None or "SOURCE" not in blocks:
            raise ValueError("no ** source data block found in the AERSCREEN input")
        st = _SOURCE_KEYS[source_key]
        src = [float(v) for v in blocks["SOURCE"]]
        kw: Dict[str, Any] = dict(title=title, source_type=st,
                                  emission_rate=src[0], stack_height=src[1])
        if st.is_stack:
            kw.update(stack_temp=src[2] or None, exit_velocity=src[3],
                      stack_diameter=src[4])
        elif st is AERSCREENSourceType.FLARE:
            kw.update(flare_heat_release=src[2], flare_heat_loss=src[3])
        elif st is AERSCREENSourceType.VOLUME:
            kw.update(lateral_dimension=src[2], vertical_dimension=src[3])
        elif st is AERSCREENSourceType.AREA:
            kw.update(area_length=src[2], area_width=src[3],
                      vertical_dimension=src[5])
        else:
            kw.update(radius=src[2], vertical_dimension=src[4])

        b = blocks.get("** BUILDING ")
        if b:
            dims = [float(v) for v in b[1:7]]
            kw.update(downwash=b[0].upper() == "Y" and st.is_elevated_release,
                      building_height=dims[0], building_length=dims[1],
                      building_width=dims[2], building_angle=dims[3],
                      stack_direction=dims[4], stack_distance=dims[5])
            if kw["downwash"] and bpip_file is None and dims[0] <= 0:
                # A restart file with BPIP=Y and no building at all is
                # AERSCREEN's "run BPIP on TITLETWO's file" case; without
                # a TITLETWO it cannot run, so treat it as off.
                kw["downwash"] = False
            kw["bpip_file"] = bpip_file

        m = blocks.get("** MAKEMET D")
        if m:
            isurf, iclim = int(m[4]), int(m[5])
            kw.update(temp_min_k=float(m[0]), temp_max_k=float(m[1]),
                      min_wind_speed=float(m[2]), anemometer_height=float(m[3]),
                      albedo=float(m[6]), bowen_ratio=float(m[7]),
                      roughness_length=float(m[8]))
            if isurf == 9:
                kw.update(surface_file=m[9], albedo=None, bowen_ratio=None,
                          roughness_length=None, _carried_sc=(
                              float(m[6]), float(m[7]), float(m[8])))
            elif 1 <= isurf <= 8:
                kw.update(land_use=isurf, climate=iclim, albedo=None,
                          bowen_ratio=None, roughness_length=None,
                          _carried_sc=(float(m[6]), float(m[7]), float(m[8])))
        u = blocks.get("** ADJUST U*")
        if u:
            kw["use_adju"] = u[0].upper() == "Y"

        t = blocks.get("** TERRAIN D")
        if t:
            nada = int(t[4])
            kw.update(terrain=t[0].upper() == "Y",
                      utm_easting=float(t[1]), utm_northing=float(t[2]),
                      utm_zone=int(t[3]) or None,
                      datum=_CODE_DATUM.get(nada),
                      probe_distance=float(t[5]),
                      source_elevation=float(t[6]))
            if kw["terrain"] and t[7].upper() == "Y":
                kw["aermap_elevation"] = True
            if kw["terrain"] and st is AERSCREENSourceType.AREA:
                kw["terrain"] = False

        d = blocks.get("** DISCRETE ")
        if d and d[0].upper() == "Y":
            kw["discrete_receptor_file"] = d[1]

        p = blocks.get("** UNITS/POP")
        if p:
            urban = p[1].upper() == "U"
            kw.update(urban=urban, population=float(p[2]) if urban else None,
                      ambient_distance=float(p[3]))
            if p[4].upper() == "Y":
                kw["flagpole_height"] = float(p[5])

        f = blocks.get("** FUMIGATIO")
        if f:
            kw.update(fumigation=f[0].upper() == "Y",
                      shoreline_fumigation=f[1].upper() == "Y",
                      shoreline_distance=float(f[2]),
                      shoreline_direction=float(f[3]),
                      run_aermod=f[4].upper() != "N")
        g = blocks.get("** DEBUG OPT")
        if g:
            kw["debug"] = g[0].upper() == "Y"
        o = blocks.get("** OUTPUT FI")
        if o:
            kw["output_file"] = o[0]
        if no2_method:
            kw.update(no2_method=no2_method, no2_stack_ratio=no2_ratio,
                      ozone_concentration=ozone, ozone_units=ozone_units)

        carried = kw.pop("_carried_sc", None)
        cfg = cls(**kw)
        if carried is not None:
            # The header carries the dominant sector's values for the
            # AERMET-table and AERSURFACE-file options; keep them so the
            # deck writes back unchanged.
            cfg._carried_surface = carried
        # Terrain restart files need their DEMs supplied again; the
        # header does not record them.
        return cfg

    #: Surface characteristics carried through from a parsed header when
    #: they are AERSCREEN's, not the user's (see ``from_aerscreen_input``).
    _carried_surface: Optional[Tuple[float, float, float]] = field(
        default=None, init=False, repr=False, compare=False
    )


_SOURCE_KEYS = {
    "** STACK DAT": AERSCREENSourceType.POINT,
    "** POINTCAP ": AERSCREENSourceType.POINTCAP,
    "** POINTHOR ": AERSCREENSourceType.POINTHOR,
    "** FLARE DAT": AERSCREENSourceType.FLARE,
    "** VOLUME DA": AERSCREENSourceType.VOLUME,
    "** AREA DATA": AERSCREENSourceType.AREA,
    "** AREACIRC ": AERSCREENSourceType.AREACIRC,
}


def _tokens(line: str) -> List[str]:
    """Split a line the way a Fortran list-directed READ would."""
    out: List[str] = []
    for m in re.finditer(r'"([^"]*)"|\'([^\']*)\'|([^\s,]+)', line):
        out.append(next(g for g in m.groups() if g is not None))
    return out


def _num(value: float) -> str:
    """A number the way a prompt answer takes it (AERSCREEN's ``checkanswer``
    accepts digits, sign, decimal point and an exponent)."""
    text = repr(float(value))
    if "e" in text or "E" in text:
        text = f"{float(value):.6E}"
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _quoted_if_needed(name: str) -> str:
    """Prompt answers holding file names take quotes when spaces are in them."""
    return f'"{name}"' if " " in name else name


# The dataclass generates __init__, so the legacy-name check has to wrap
# it rather than live in __post_init__ (which never sees an unexpected
# keyword -- __init__ has already raised by then).
_generated_init = AERSCREENConfig.__init__


@functools.wraps(_generated_init)
def _init_with_legacy_check(self: AERSCREENConfig, *args: Any, **kwargs: Any) -> None:
    _reject_legacy_kwargs(kwargs)
    _generated_init(self, *args, **kwargs)


AERSCREENConfig.__init__ = _init_with_legacy_check  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Output file
# ---------------------------------------------------------------------------

@dataclass
class AERSCREENImpact:
    """One row of the ``AERSCREEN MAXIMUM IMPACT SUMMARY`` table.

    ``conc_annual`` is ``None`` where AERSCREEN prints ``N/A`` (area
    sources, whose scaled values all equal the 1-hour value).
    """
    conc_1hr: float
    conc_3hr: float
    conc_8hr: float
    conc_24hr: float
    conc_annual: Optional[float]
    distance: float


@dataclass
class AERSCREENSummary:
    """What an AERSCREEN ``.OUT`` file concludes.

    Attributes
    ----------
    version
        ``"AERSCREEN 21112 / AERMOD 26135"`` as the banner states it.
    title
        The run title.
    maximum
        The overall maximum impact (``FLAT TERRAIN`` or ``TERRAIN`` row).
    ambient_boundary
        The impact at the ambient boundary, if AERSCREEN reported it.
    distances, concentrations
        The ``OVERALL MAXIMUM CONCENTRATIONS BY DISTANCE`` table, in
        metres and ug/m3, in the order printed.
    """
    version: str
    title: str
    maximum: AERSCREENImpact
    ambient_boundary: Optional[AERSCREENImpact]
    distances: List[float]
    concentrations: List[float]


_ROW_LABELS = {
    "FLAT TERRAIN": "maximum",
    "ELEVATED TERRAIN": "maximum",
    "AMBIENT BOUNDARY": "ambient_boundary",
}

#: A number as AERSCREEN prints it: F editing may leave no digits after
#: the point (``4885.``), G editing may carry an exponent (``0.5736E-01``).
_NUMBER = r"[-+]?(?:\d+\.\d*|\.\d+)(?:E[-+]\d+)?"


def parse_aerscreen_output(source: Union[str, Path]) -> AERSCREENSummary:
    """Parse an AERSCREEN ``.OUT`` file (a path or its text)."""
    if isinstance(source, Path) or (
        isinstance(source, str) and "\n" not in source and Path(source).is_file()
    ):
        text = Path(source).read_text(encoding="latin-1")
    else:
        text = str(source)
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]

    version = ""
    title = ""
    for ln in lines[:10]:
        if "AERSCREEN" in ln and "AERMOD" in ln and not version:
            version = ln.strip().split("  ")[0].strip()
        if ln.strip().startswith("TITLE:"):
            title = ln.strip()[6:].strip()

    distances: List[float] = []
    concentrations: List[float] = []
    in_table = False
    for ln in lines:
        if "MAXIMUM CONCENTRATIONS BY DISTANCE" in ln:
            in_table = True
            continue
        if in_table:
            if "MAXIMUM IMPACT SUMMARY" in ln:
                break
            if not re.fullmatch(r"\s*(?:" + _NUMBER + r"\s*)+", ln):
                continue
            vals = [float(v) for v in re.findall(_NUMBER, ln)]
            # Two columns of (distance, concentration), each with a
            # receptor height as well in terrain runs; the right-hand
            # column is absent on the last line of an odd table.
            per_side = 3 if len(vals) in (3, 6) else 2
            if len(vals) not in (per_side, 2 * per_side):
                continue
            for k in range(0, len(vals), per_side):
                distances.append(vals[k])
                concentrations.append(vals[k + 1])
    # The table is printed in two columns, left column first; restore
    # the single ascending order.
    if distances:
        order = sorted(range(len(distances)), key=lambda k: distances[k])
        distances = [distances[k] for k in order]
        concentrations = [concentrations[k] for k in order]

    rows: Dict[str, AERSCREENImpact] = {}
    pending: Optional[Tuple[str, List[float]]] = None
    for ln in lines:
        stripped = ln.strip()
        for label, attr in _ROW_LABELS.items():
            if stripped.startswith(label) and attr not in rows:
                rest = stripped[len(label):]
                vals = [float(v) for v in re.findall(_NUMBER, rest)]
                if len(vals) == 4 and rest.split()[-1] == "N/A":
                    vals.append(None)  # type: ignore[arg-type]
                if len(vals) == 5:
                    pending = (attr, vals)
                break
        if pending and stripped.startswith("DISTANCE FROM SOURCE"):
            attr, vals = pending
            dist = float(re.findall(_NUMBER, stripped)[0])
            rows[attr] = AERSCREENImpact(vals[0], vals[1], vals[2], vals[3],
                                         vals[4], dist)
            pending = None
    if "maximum" not in rows:
        raise ValueError("no AERSCREEN MAXIMUM IMPACT SUMMARY found")
    return AERSCREENSummary(
        version=version, title=title, maximum=rows["maximum"],
        ambient_boundary=rows.get("ambient_boundary"),
        distances=distances, concentrations=concentrations,
    )


__all__ = [
    "AERMET_CLIMATE",
    "AERMET_LAND_USE",
    "DISCRETE_RECEPTOR_FILE",
    "MAX_DISCRETE_RECEPTORS",
    "AERSCREENConfig",
    "AERSCREENImpact",
    "AERSCREENSourceType",
    "AERSCREENSummary",
    "parse_aerscreen_output",
]
