"""
AERSURFACE input-deck generation.

EPA's AERSURFACE binary derives surface-characteristic tables (albedo,
Bowen ratio, surface roughness) from NLCD land-cover rasters for use in
AERMET Stage 3. This module is the deck-builder; binary dispatch lives
in :mod:`pyaermod.aersurface_runner`.

The deck format is the pathway-and-keyword layout AERSURFACE has used
since v19: a ``CO`` (control) pathway and an ``OU`` (output) pathway,
each bracketed by ``STARTING`` / ``FINISHED``. It is verified against
the real binary -- :mod:`tests.test_real_aersurface` reproduces EPA's
own RDU test case through this class and compares the resulting surface
characteristics to EPA's shipped reference file.

Typical usage::

    cfg = AERSURFACEConfig(
        title="RDU - Met Tower, 2021 NLCD",
        site_id="RDU",
        latitude=35.8923, longitude=-78.7819,
        land_cover_file="RDU_2021_NLCD_LC.tiff",
        nlcd_year=2021,
        canopy_file="RDU_2021_NLCD_Can.tiff",
        impervious_file="RDU_2021_NLCD_Imp.tiff",
        frequency="MONTHLY",
        sectors=[(30.0, 60.0, "NONAP"), (60.0, 225.0, "AP"),
                 (225.0, 30.0, "NONAP")],
        sfcchar_file="rdu_sfc.txt",
    )
    deck_text = cfg.to_aersurface_input()
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------
# Migration from the pre-2026-08 field names
# ---------------------------------------------------------------------
#
# The deck this class used to emit was not in any AERSURFACE format:
# it used keywords (TITLE, LOCATION, NLCDFILE, SNOW_TEMPER, OUTPATH...)
# that AERSURFACE has never accepted, and the real binary aborted in its
# control-file parser. Correcting the format meant changing the fields.
#
# A dataclass would reject the old names with a bare "unexpected keyword
# argument", which says nothing about what to use instead. These two
# tables turn that into an answer. They are deliberately not a silent
# translation layer: three of the old fields describe nothing AERSURFACE
# has, so accepting and dropping them would turn code that never worked
# into code that still does not work, quietly.

#: Old field name -> new field name, where the meaning carries over.
_RENAMED_FIELDS: Dict[str, str] = {
    "nlcd_file": "land_cover_file",
    "radius_roughness_km": "zo_radius_km",
}

#: Old field name -> why there is no direct replacement.
_REMOVED_FIELDS: Dict[str, str] = {
    "utc_offset": (
        "AERSURFACE has no UTC-offset keyword; it derives nothing from "
        "the time zone. Drop it."
    ),
    "snow_regime": (
        "AERSURFACE has no snow *temperature* regime. Use snow=True/False "
        "for the CLIMATE keyword, and put months with continuous snow "
        "cover in the WINTERWS season via seasons=."
    ),
    "moisture_per_month": (
        "AERSURFACE takes one surface-moisture setting on CLIMATE, not "
        "twelve. Use moisture='AVERAGE' | 'WET' | 'DRY'."
    ),
    "snow_cover_per_month": (
        "Express continuous snow cover by assigning those months to the "
        "WINTERWS season, e.g. seasons={'WINTERWS': (1,), 'WINTERNS': "
        "(12, 2, 3), ...}."
    ),
    "radius_albedo_bowen_km": (
        "AERSURFACE averages over the single ZORADIUS; there is no "
        "separate albedo/Bowen radius. Use zo_radius_km."
    ),
    "output_dir": (
        "Name the output file itself: sfcchar_file='path/to/sfc.txt' "
        "(and land_cover_grid_file / canopy_grid_file / "
        "impervious_grid_file for the optional grid outputs)."
    ),
    "extra_lines": (
        "The deck has two pathways now, so say which one the lines "
        "belong to: extra_co_lines= or extra_ou_lines=."
    ),
}


def _reject_legacy_kwargs(kwargs: Dict[str, Any]) -> None:
    """Raise a TypeError naming the replacement for an old field name."""
    for old, new in _RENAMED_FIELDS.items():
        if old in kwargs:
            raise TypeError(
                f"AERSURFACEConfig has no field {old!r}; it is now {new!r}. "
                "The old field names built a deck AERSURFACE rejects -- see "
                "the CHANGELOG upgrade notes."
            )
    for old, why in _REMOVED_FIELDS.items():
        if old in kwargs:
            raise TypeError(
                f"AERSURFACEConfig has no field {old!r}. {why}"
            )

#: NLCD release years AERSURFACE accepts for the land-cover raster.
_VALID_NLCD_YEARS = {1992, 2001, 2006, 2011, 2013, 2016, 2019, 2021}

#: Years for which AERSURFACE accepts canopy / impervious rasters. The
#: 1992 and 2013 land-cover releases have no matching ancillary product.
_VALID_ANCILLARY_YEARS = {2001, 2006, 2011, 2016, 2019, 2021}

_VALID_MOISTURE = {"AVERAGE", "DRY", "WET"}
_VALID_FREQUENCY = {"ANNUAL", "SEASONAL", "MONTHLY"}
_VALID_ZO_METHOD = {"ZORAD", "ZOEFF"}
_VALID_SITE_TYPE = {"PRIMARY", "SECONDARY"}
_VALID_DATUM = {"NAD27", "NAD83"}
_VALID_AP = {"AP", "NONAP"}

#: AERSURFACE's season names. ``WINTERNS`` is winter without continuous
#: snow cover, ``WINTERWS`` winter with it -- the distinction the older
#: per-month ``snow_cover`` flag stood in for.
SEASON_NAMES = ("WINTERNS", "WINTERWS", "SPRING", "SUMMER", "AUTUMN")

#: Months assigned to each season when ``seasons`` is not given. This is
#: AERSURFACE's own default mapping for a site with no continuous snow.
DEFAULT_SEASONS: Dict[str, Tuple[int, ...]] = {
    "WINTERNS": (12, 1, 2),
    "SPRING": (3, 4, 5),
    "SUMMER": (6, 7, 8),
    "AUTUMN": (9, 10, 11),
}


@dataclass
class AERSURFACEConfig:
    """Configuration for one AERSURFACE run.

    Parameters
    ----------
    title, title_two
        Deck ``TITLEONE`` / ``TITLETWO`` lines.
    site_id
        Short station identifier. Not written to the deck (AERSURFACE
        has no such keyword); kept for labelling outputs.
    latitude, longitude
        Site location in decimal degrees, written as ``CENTERLL``.
    datum
        ``"NAD83"`` (default) or ``"NAD27"``.
    land_cover_file
        NLCD land-cover raster (GeoTIFF), written as ``DATAFILE
        NLCD<year>``.
    nlcd_year
        NLCD release year of ``land_cover_file``.
    canopy_file, impervious_file
        Optional percent-tree-canopy and percent-impervious rasters.
        ``canopy_year`` / ``impervious_year`` default to ``nlcd_year``.
    site_type
        ``"PRIMARY"`` (default) or ``"SECONDARY"``, the ``OPTIONS``
        keyword's first parameter.
    zo_method
        ``"ZORAD"`` (default, inverse-distance-weighted within a radius)
        or ``"ZOEFF"``.
    zo_radius_km
        Roughness-averaging radius in km, written as ``ZORADIUS``.
        EPA default 1.0.
    moisture
        ``"AVERAGE"`` (default), ``"WET"`` or ``"DRY"`` -- the surface
        moisture regime for the ``CLIMATE`` keyword.
    snow
        True (default) if snow is possible at the site, giving
        ``CLIMATE ... SNOW``; False gives ``NOSNOW``.
    arid
        True for arid/semi-arid regions.
    frequency
        ``"ANNUAL"``, ``"SEASONAL"`` or ``"MONTHLY"`` (default) --
        how often surface characteristics vary.
    sectors
        Wind sectors as ``(start_deg, end_deg, "AP" | "NONAP")``
        triples, clockwise from north; the last may wrap past 360. None
        (default) means one sector covering the compass, using
        ``airport``.
    airport
        Designation for the single default sector when ``sectors`` is
        None.
    seasons
        Map of season name to the months (1-12) assigned to it.
        Defaults to :data:`DEFAULT_SEASONS`. Use ``WINTERWS`` for months
        with continuous snow cover.
    sfcchar_file
        Output path for the surface-characteristics table AERMET Stage 3
        consumes. Written as ``SFCCHAR``.
    land_cover_grid_file, canopy_grid_file, impervious_grid_file
        Optional gridded-value debug outputs (``NLCDGRID``,
        ``CNPYGRID``, ``MPRVGRID``).
    debug_options
        Values for ``DEBUGOPT``, e.g. ``["GRID", "TIFF"]``.
    run
        False writes ``RUNORNOT NOT`` so AERSURFACE checks the deck
        without processing rasters.
    extra_co_lines, extra_ou_lines
        Free-form lines appended verbatim inside the CO / OU pathways,
        for keywords not modelled here.
    """

    title: str
    site_id: str
    latitude: float
    longitude: float
    land_cover_file: str
    nlcd_year: int

    title_two: str = ""
    datum: str = "NAD83"
    canopy_file: Optional[str] = None
    canopy_year: Optional[int] = None
    impervious_file: Optional[str] = None
    impervious_year: Optional[int] = None

    site_type: str = "PRIMARY"
    zo_method: str = "ZORAD"
    zo_radius_km: float = 1.0

    moisture: str = "AVERAGE"
    snow: bool = True
    arid: bool = False

    frequency: str = "MONTHLY"
    sectors: Optional[Sequence[Tuple[float, float, str]]] = None
    airport: bool = False
    seasons: Optional[Dict[str, Sequence[int]]] = None

    sfcchar_file: str = "aersurface_sfc.txt"
    land_cover_grid_file: Optional[str] = None
    canopy_grid_file: Optional[str] = None
    impervious_grid_file: Optional[str] = None
    debug_options: List[str] = field(default_factory=list)
    run: bool = True

    extra_co_lines: List[str] = field(default_factory=list)
    extra_ou_lines: List[str] = field(default_factory=list)

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
        self.datum = self.datum.upper()
        if self.datum not in _VALID_DATUM:
            raise ValueError(
                f"datum must be one of {sorted(_VALID_DATUM)}; "
                f"got {self.datum!r}"
            )
        self.moisture = self.moisture.upper()
        if self.moisture not in _VALID_MOISTURE:
            raise ValueError(
                f"moisture must be one of {sorted(_VALID_MOISTURE)}; "
                f"got {self.moisture!r}"
            )
        self.frequency = self.frequency.upper()
        if self.frequency not in _VALID_FREQUENCY:
            raise ValueError(
                f"frequency must be one of {sorted(_VALID_FREQUENCY)}; "
                f"got {self.frequency!r}"
            )
        self.zo_method = self.zo_method.upper()
        if self.zo_method not in _VALID_ZO_METHOD:
            raise ValueError(
                f"zo_method must be one of {sorted(_VALID_ZO_METHOD)}; "
                f"got {self.zo_method!r}"
            )
        self.site_type = self.site_type.upper()
        if self.site_type not in _VALID_SITE_TYPE:
            raise ValueError(
                f"site_type must be one of {sorted(_VALID_SITE_TYPE)}; "
                f"got {self.site_type!r}"
            )
        if self.zo_radius_km <= 0:
            raise ValueError("zo_radius_km must be > 0")

        for label, path, year in (
            ("canopy", self.canopy_file, self.canopy_year),
            ("impervious", self.impervious_file, self.impervious_year),
        ):
            if path is None:
                continue
            resolved = year if year is not None else self.nlcd_year
            if resolved not in _VALID_ANCILLARY_YEARS:
                raise ValueError(
                    f"{label}_year must be one of "
                    f"{sorted(_VALID_ANCILLARY_YEARS)}; got {resolved}"
                )

        if self.sectors is not None:
            if not self.sectors:
                raise ValueError("sectors must be non-empty when given")
            if any(isinstance(s, (int, float)) for s in self.sectors):
                # The old shape was a flat list of boundary angles.
                raise ValueError(
                    "sectors is now a list of (start, end, 'AP'|'NONAP') "
                    "triples, not boundary angles: AERSURFACE's SECTOR "
                    "keyword names both ends and the airport designation. "
                    "Convert [30, 60, 225] to [(30, 60, 'NONAP'), "
                    "(60, 225, 'AP'), (225, 30, 'NONAP')]."
                )
            for start, end, kind in self.sectors:
                for ang in (start, end):
                    if not (0 <= ang <= 360):
                        raise ValueError(
                            f"sector angles must be in [0, 360]; got {ang}"
                        )
                if kind.upper() not in _VALID_AP:
                    raise ValueError(
                        f"sector type must be one of {sorted(_VALID_AP)}; "
                        f"got {kind!r}"
                    )

        if self.seasons is not None:
            bad = set(self.seasons) - set(SEASON_NAMES)
            if bad:
                raise ValueError(
                    f"season names must be in {SEASON_NAMES}; "
                    f"saw {sorted(bad)}"
                )
            months = [m for ms in self.seasons.values() for m in ms]
            if sorted(months) != list(range(1, 13)):
                raise ValueError(
                    "seasons must assign each month 1-12 exactly once; got "
                    f"{sorted(months)}"
                )

    # ------------------------------------------------------------------
    def _sector_lines(self) -> List[str]:
        sectors = self.sectors
        if sectors is None:
            kind = "AP" if self.airport else "NONAP"
            sectors = [(0.0, 360.0, kind)]
        lines = [
            f"   FREQ_SECT  {self.frequency}  {len(sectors)}  VARYAP"
        ]
        for i, (start, end, kind) in enumerate(sectors, start=1):
            lines.append(
                f"   SECTOR  {i}  {start:.2f}  {end:.2f}  {kind.upper()}"
            )
        return lines

    def _season_lines(self) -> List[str]:
        if self.frequency == "ANNUAL":
            return []
        seasons = self.seasons if self.seasons is not None else DEFAULT_SEASONS
        lines = []
        for name in SEASON_NAMES:
            months = seasons.get(name)
            if not months:
                continue
            month_str = " ".join(str(m) for m in months)
            lines.append(f"   SEASON  {name}  {month_str}")
        return lines

    def to_aersurface_input(self) -> str:
        """Render the AERSURFACE control file as a string.

        The layout matches EPA's own example decks: a ``CO`` pathway
        carrying the site, rasters and climate, then an ``OU`` pathway
        naming the outputs.
        """
        co: List[str] = ["CO STARTING", f"   TITLEONE  {self.title}"]
        if self.title_two:
            co.append(f"   TITLETWO  {self.title_two}")
        co.append(f"   OPTIONS   {self.site_type}  {self.zo_method}")
        if self.debug_options:
            co.append(f"   DEBUGOPT  {'  '.join(self.debug_options)}")
        co.append(
            f"   CENTERLL  {self.latitude:.6f}  {self.longitude:.6f}  "
            f"{self.datum}"
        )
        co.append(
            f'   DATAFILE  NLCD{self.nlcd_year}  "{self.land_cover_file}"'
        )
        if self.canopy_file:
            year = self.canopy_year or self.nlcd_year
            co.append(f'   DATAFILE  CNPY{year}  "{self.canopy_file}"')
        if self.impervious_file:
            year = self.impervious_year or self.nlcd_year
            co.append(f'   DATAFILE  MPRV{year}  "{self.impervious_file}"')
        co.append(f"   ZORADIUS  {self.zo_radius_km:g}")
        co.append(
            f"   CLIMATE   {self.moisture}  "
            f"{'SNOW' if self.snow else 'NOSNOW'}  "
            f"{'ARID' if self.arid else 'NONARID'}"
        )
        co.extend(self._sector_lines())
        co.extend(self._season_lines())
        co.append(f"   RUNORNOT  {'RUN' if self.run else 'NOT'}")
        co.extend(self.extra_co_lines)
        co.append("CO FINISHED")

        ou: List[str] = ["OU STARTING", f'   SFCCHAR    "{self.sfcchar_file}"']
        for keyword, path in (
            ("NLCDGRID", self.land_cover_grid_file),
            ("CNPYGRID", self.canopy_grid_file),
            ("MPRVGRID", self.impervious_grid_file),
        ):
            if path:
                ou.append(f'   {keyword}   "{path}"')
        ou.extend(self.extra_ou_lines)
        ou.append("OU FINISHED")

        return "\n".join([*co, "", *ou]) + "\n"


# The dataclass generates __init__, so the legacy-name check has to wrap
# it rather than live in __post_init__ (which never sees an unexpected
# keyword -- __init__ has already raised by then).
_generated_init = AERSURFACEConfig.__init__


@functools.wraps(_generated_init)
def _init_with_legacy_check(self: AERSURFACEConfig, *args: Any, **kwargs: Any) -> None:
    _reject_legacy_kwargs(kwargs)
    _generated_init(self, *args, **kwargs)


AERSURFACEConfig.__init__ = _init_with_legacy_check  # type: ignore[method-assign]


__all__ = [
    "DEFAULT_SEASONS",
    "SEASON_NAMES",
    "AERSURFACEConfig",
]
