"""
AERSURFACE input-deck generation.

EPA's AERSURFACE binary derives monthly surface-characteristic tables
(albedo, Bowen ratio, surface roughness) from NLCD land-use rasters
for use in AERMET Stage 3. This module is the deck-builder; binary
dispatch lives in :mod:`pyaermod.aersurface_runner`.

The deck format follows the EPA AERSURFACE v24 User's Guide. Common
keywords are exposed as :class:`AERSURFACEConfig` fields; uncommon /
forward-compatibility keywords can be passed via the ``extra_lines``
escape hatch.

Typical usage::

    cfg = AERSURFACEConfig(
        title="Salem AERSURFACE run",
        site_id="SALEM",
        latitude=44.92, longitude=-123.04, utc_offset=-8,
        nlcd_file="/data/nlcd/NLCD_2019.img",
        nlcd_year=2019,
        snow_regime="CONTINENTAL_WARM",
        moisture_per_month=["AVERAGE"] * 12,
        snow_cover_per_month=["N"] * 12,
        output_dir=".",
    )
    deck_text = cfg.to_aersurface_input()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Valid NLCD release years (Multi-Resolution Land Characteristics Consortium).
_VALID_NLCD_YEARS = {1992, 2001, 2006, 2011, 2013, 2016, 2019, 2021}

# Snow temperature regimes per EPA AERSURFACE Users Guide.
_VALID_SNOW_REGIMES = {
    "CONTINENTAL_WARM",
    "CONTINENTAL_COOL",
    "MARITIME_WARM",
    "MARITIME_COOL",
    "POLAR",
}

_VALID_MOISTURE = {"AVERAGE", "DRY", "WET"}


@dataclass
class AERSURFACEConfig:
    """Configuration for one AERSURFACE run.

    Parameters
    ----------
    title
        Free-form run title written as the deck's TITLE keyword.
    site_id
        Short station identifier (<=8 characters recommended).
    latitude, longitude
        Site location in decimal degrees (WGS84).
    utc_offset
        UTC offset hours, e.g. -8 for PST.
    nlcd_file
        Path to the NLCD raster (.img / .tif) covering the site
        and the surrounding sample radii.
    nlcd_year
        NLCD release year. Must be one of: 1992, 2001, 2006, 2011,
        2013, 2016, 2019, 2021.
    arid
        Set to True for arid/semi-arid regions (alters Bowen ratio).
    airport
        Set to True for airport-style assumptions (mowed grass dominant).
    snow_regime
        Snow temperature regime; one of CONTINENTAL_WARM, CONTINENTAL_COOL,
        MARITIME_WARM, MARITIME_COOL, POLAR.
    moisture_per_month
        12-element list of "AVERAGE" | "DRY" | "WET" per Jan..Dec.
    snow_cover_per_month
        12-element list of "Y" | "N" per Jan..Dec.
    sectors
        List of sector boundary angles in degrees (clockwise from north),
        or None for a single uniform sector.
    radius_roughness_km
        Sample radius for surface-roughness averaging (km). EPA default 1.0.
    radius_albedo_bowen_km
        Sample radius for albedo + Bowen-ratio averaging (km). EPA default 10.0.
    output_dir
        Directory for AERSURFACE output files (the .out summary + the
        12-month .sfc characteristic table consumed by AERMET Stage 3).
    extra_lines
        Free-form lines appended verbatim after the standard keywords.
        Use for forward-compatibility with new AERSURFACE keywords or
        site-specific overrides not yet modelled here.
    """

    title: str
    site_id: str
    latitude: float
    longitude: float
    utc_offset: int
    nlcd_file: str
    nlcd_year: int

    arid: bool = False
    airport: bool = False
    snow_regime: str = "CONTINENTAL_WARM"
    moisture_per_month: List[str] = field(
        default_factory=lambda: ["AVERAGE"] * 12
    )
    snow_cover_per_month: List[str] = field(
        default_factory=lambda: ["N"] * 12
    )
    sectors: Optional[List[float]] = None
    radius_roughness_km: float = 1.0
    radius_albedo_bowen_km: float = 10.0
    output_dir: str = "."
    extra_lines: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (-90 <= self.latitude <= 90):
            raise ValueError(
                f"latitude must be in [-90, 90]; got {self.latitude}"
            )
        if not (-180 <= self.longitude <= 180):
            raise ValueError(
                f"longitude must be in [-180, 180]; got {self.longitude}"
            )
        if self.nlcd_year not in _VALID_NLCD_YEARS:
            raise ValueError(
                f"nlcd_year must be one of {sorted(_VALID_NLCD_YEARS)}; "
                f"got {self.nlcd_year}"
            )
        if self.snow_regime not in _VALID_SNOW_REGIMES:
            raise ValueError(
                f"snow_regime must be one of {sorted(_VALID_SNOW_REGIMES)}; "
                f"got {self.snow_regime!r}"
            )
        if len(self.moisture_per_month) != 12:
            raise ValueError("moisture_per_month must have length 12")
        bad = set(m.upper() for m in self.moisture_per_month) - _VALID_MOISTURE
        if bad:
            raise ValueError(
                f"moisture_per_month entries must be in {_VALID_MOISTURE}; "
                f"saw {sorted(bad)}"
            )
        if len(self.snow_cover_per_month) != 12:
            raise ValueError("snow_cover_per_month must have length 12")
        if any(s.upper() not in {"Y", "N"} for s in self.snow_cover_per_month):
            raise ValueError("snow_cover_per_month entries must be 'Y' or 'N'")
        if self.radius_roughness_km <= 0:
            raise ValueError("radius_roughness_km must be > 0")
        if self.radius_albedo_bowen_km <= 0:
            raise ValueError("radius_albedo_bowen_km must be > 0")
        if self.sectors is not None:
            for ang in self.sectors:
                if not (0 <= ang < 360):
                    raise ValueError(
                        f"sector angles must be in [0, 360); got {ang}"
                    )

    # ------------------------------------------------------------------
    def to_aersurface_input(self) -> str:
        """Render the AERSURFACE input deck as a string."""
        lines: List[str] = []
        lines.append(f"TITLE  {self.title}")
        lines.append(
            f"LOCATION  {self.site_id}  {self.latitude:.5f}  "
            f"{self.longitude:.5f}  {self.utc_offset}"
        )
        lines.append(f"NLCDFILE  {self.nlcd_file}")
        lines.append(f"NLCDYEAR  {self.nlcd_year}")
        lines.append(f"ARID  {'Y' if self.arid else 'N'}")
        lines.append(f"AIRPORT  {'Y' if self.airport else 'N'}")
        lines.append(f"SNOW_TEMPER  {self.snow_regime}")
        lines.append(f"RADIUS_ROUGHNESS  {self.radius_roughness_km}")
        lines.append(f"RADIUS_ALBEDO_BOWEN  {self.radius_albedo_bowen_km}")
        if self.sectors is None:
            lines.append("SECTORS_LIST  UNIFORM")
        else:
            sec_str = " ".join(f"{a:g}" for a in self.sectors)
            lines.append(f"SECTORS_LIST  {sec_str}")
        # Per-month rows for moisture and snow cover.
        moist = "  ".join(m.upper() for m in self.moisture_per_month)
        lines.append(f"MOISTURE  {moist}")
        snow = "  ".join(s.upper() for s in self.snow_cover_per_month)
        lines.append(f"SNOW_COVER  {snow}")
        lines.append(f"OUTPATH  {self.output_dir}")
        lines.extend(self.extra_lines)
        return "\n".join(lines) + "\n"


__all__ = [
    "AERSURFACEConfig",
]
