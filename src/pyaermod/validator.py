"""
PyAERMOD Configuration Validator

Validates AERMOD input parameters before generating .inp files.
Catches errors early with clear Python-side messages instead of
letting invalid parameters silently produce bad input files that
AERMOD rejects at runtime.
"""

import itertools
import math
import numbers
import operator
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ._fortran import fortran_float
from .pathways import (
    BACKGROUND_UNITS,
    EVENT_NAME_LENGTH,
    EVENT_OUTPUT_OPTIONS,
    NO2STACK_METHODS,
    NOHEADER_FILE_TYPES,
    SHORT_TERM_HOURS,
    TEMPORAL_FLAG_COUNTS,
    TURBULENCE_OPTIONS,
    WIND_CATEGORY_COUNT,
    dayrange_field_is_valid,
    unquote_path,
    value_list,
)

# Valid AERMOD averaging periods
VALID_AVERAGING_PERIODS = {
    *(str(hours) for hours in SHORT_TERM_HOURS), "MONTH", "ANNUAL", "PERIOD",
}

# Valid AERMOD pollutant IDs
VALID_POLLUTANT_IDS = {"OTHER", "PM25", "PM10", "NO2", "SO2", "CO", "O3"}

# Valid elevation units
VALID_ELEVATION_UNITS = {"METERS", "FEET"}


def _is_number(value) -> bool:
    """A real number, not a bool (``True < 0`` works but is no concentration)
    and not a string from a hand-edited project file."""
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _is_finite_number(value) -> bool:
    """A number (:func:`_is_number`) that is neither NaN nor infinite: the
    writer would emit ``nan``/``inf``, which AERMOD cannot read, and NaN
    slips past every ``<``/``>`` range check."""
    return _is_number(value) and math.isfinite(value)


#: RE keywords that define receptors (aermod.f RECSIZ counts them, and
#: PREINCLUD those in an INCLUDED file).
_RECEPTOR_KEYWORDS = ("INCLUDED", "EVALCART", "DISCCART", "DISCPOLR", "GRIDCART", "GRIDPOLR")


def _kept_lines(unparsed_lines, pathway: str, keywords) -> list:
    """The verbatim lines of ``pathway`` whose keyword is one of ``keywords``."""
    return [ln for ln in unparsed_lines or []
            if str(ln.pathway).upper() == pathway
            and str(ln.keyword).upper() in keywords]


@dataclass
class ValidationError:
    """A single validation error with context."""
    pathway: str        # e.g. "ControlPathway", "PointSource(STACK1)"
    field: str          # e.g. "stack_height"
    message: str        # e.g. "must be > 0, got -5.0"
    severity: str = "error"  # "error" or "warning"

    def __str__(self):
        tag = "WARNING" if self.severity == "warning" else "ERROR"
        return f"[{tag}] {self.pathway}.{self.field}: {self.message}"


@dataclass
class ValidationResult:
    """Collection of validation errors and warnings."""
    errors: List[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(e.severity == "error" for e in self.errors)

    @property
    def warnings(self) -> List[ValidationError]:
        return [e for e in self.errors if e.severity == "warning"]

    @property
    def error_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == "warning")

    def __str__(self):
        if not self.errors:
            return "Validation passed: no errors or warnings."
        lines = [f"Validation: {self.error_count} error(s), {self.warning_count} warning(s)"]
        for e in self.errors:
            lines.append(f"  {e}")
        return "\n".join(lines)


class Validator:
    """
    Validates an AERMODProject configuration.

    Usage::

        from pyaermod.validator import Validator
        result = Validator.validate(project)
        if not result.is_valid:
            print(result)
            raise ValueError(str(result))
    """

    @classmethod
    def validate(cls, project, check_files: bool = False,
                 advanced: bool = True, *,
                 preserve_unparsed: bool = True) -> ValidationResult:
        """
        Validate an entire AERMODProject.

        Parameters
        ----------
        project : AERMODProject
            The project to validate.
        check_files : bool
            If True, verify that meteorology files exist on disk.
        advanced : bool
            If True (default), also run the cross-field checks from
            :mod:`validator_advanced` (stack-parameter consistency,
            receptor-domain extent, DFAULT consistency, STARTEND range
            under ANNUAL). Pass ``advanced=False`` to restrict output to
            only the base per-field checks.
        preserve_unparsed : bool
            Whether the deck will carry :attr:`AERMODProject.unparsed_lines`
            (``to_aermod_input(preserve_unparsed=...)``). True (default)
            also checks those lines against the modelled project; False
            skips the checks that only matter when they are written.

        Returns
        -------
        ValidationResult
        """
        result = ValidationResult()
        event_run = bool(getattr(project, "event_processing", False))
        cls._validate_control(project.control, result)
        kept = list(getattr(project, "unparsed_lines", None) or []) if preserve_unparsed else []
        cls._validate_sources(project.sources, project.control, result,
                              unparsed_lines=kept)
        if preserve_unparsed:
            cls._validate_background_verbatim(project, result)
        if not event_run:
            # An EVENT deck has no RE pathway; its receptors are the
            # EVENTLOC cards.
            cls._validate_receptors(project.receptors, result, unparsed_lines=kept)
            cls._validate_openpit_receptors(project.sources, project.receptors, result)
        cls._validate_meteorology(project.meteorology, result, check_files,
                                  project.control)
        cls._validate_output(project.output, result, project.control, project.sources)
        events = getattr(project, "events", None)
        if event_run and events is None:
            result.errors.append(ValidationError(
                "EventPathway", "events",
                "event_processing is set but the project has no events"
            ))
        if events is not None:
            cls._validate_events(events, project.control, project.sources,
                                 project.output, result, event_run)

        cls._validate_card_length(project, result, preserve_unparsed)

        if advanced:
            # Lazy import to avoid circulars: validator_advanced uses
            # ValidationError from this module.
            from .validator_advanced import advanced_validate
            # The advanced DFAULT check repeats the base one; keep one copy.
            seen = {(e.pathway, e.field, e.message, e.severity) for e in result.errors}
            result.errors.extend(
                e for e in advanced_validate(project)
                if (e.pathway, e.field, e.message, e.severity) not in seen)
        return result

    #: Longest runstream card AERMOD reads (modules.f ISTRG; setup.f reads
    #: each record as A512 and drops the rest of the line).
    MAX_CARD_LENGTH = 512

    @classmethod
    def _validate_card_length(cls, project, result: ValidationResult,
                              preserve_unparsed: bool = True):
        """Cards the writer would make longer than AERMOD reads.

        A card past 512 characters is cut without a message: a cut at a
        blank silently loses the fields after it (a SRCGROUP loses
        members), a cut inside a field gives an unrelated error. The
        deck is written once, unvalidated, to measure its lines; a
        project the writer cannot write is left to the other checks.
        """
        write = getattr(project, "to_aermod_input", None)
        if not callable(write):
            return
        try:
            deck = write(validate=False, preserve_unparsed=preserve_unparsed)
        except Exception:  # the writer's own errors are reported elsewhere
            return
        if not isinstance(deck, str):
            return
        for lineno, line in enumerate(deck.splitlines(), start=1):
            if len(line) > cls.MAX_CARD_LENGTH:
                card = " ".join(line.split()[:2])
                result.errors.append(ValidationError(
                    "AERMODProject", "deck",
                    f"line {lineno} ({card} ...) is {len(line)} characters; AERMOD reads "
                    f"only the first {cls.MAX_CARD_LENGTH} of a card (ISTRG) and drops the "
                    "rest without a message. Shorten it: for a source group, name the "
                    "members with an ID range (e.g. STK1-STK99) or put them in the "
                    "sources' own source_groups, which are written ten to a card"
                ))

    # ------------------------------------------------------------------
    # Control pathway
    # ------------------------------------------------------------------

    @classmethod
    def _validate_control(cls, control, result: ValidationResult):
        pathway = "ControlPathway"

        # Title
        if not control.title_one or not control.title_one.strip():
            result.errors.append(ValidationError(
                pathway, "title_one", "must not be empty"
            ))

        cls._validate_dfault_terrain(control, result)
        cls._validate_dfault_options(control, result)
        cls._validate_low_wind(control, result)
        cls._validate_restart_options(control, result)
        cls._validate_gas_deposition_defaults(control, result)
        cls._validate_downwash_and_arm2_options(control, result)

        # Chemistry options
        if getattr(control, "chemistry", None) is not None:
            cls._validate_chemistry(control.chemistry, control, result)

        # Averaging periods
        if not control.averaging_periods:
            result.errors.append(ValidationError(
                pathway, "averaging_periods", "must specify at least one averaging period"
            ))
        else:
            for period in control.averaging_periods:
                if period not in VALID_AVERAGING_PERIODS:
                    result.errors.append(ValidationError(
                        pathway, "averaging_periods",
                        f"invalid averaging period '{period}'; "
                        f"valid values: {sorted(VALID_AVERAGING_PERIODS)}"
                    ))

        # Pollutant ID
        pollutant = (
            control.pollutant_id.value
            if hasattr(control.pollutant_id, "value")
            else control.pollutant_id
        )
        # coset.f POLLID takes any name (only NO2, SO2 and the PM2.5
        # spellings get special processing); POLLUT is CHARACTER*8.
        pollutant = "" if pollutant is None else str(pollutant)
        if not pollutant.strip() or any(c.isspace() for c in pollutant):
            result.errors.append(ValidationError(
                pathway, "pollutant_id",
                f"must be one word with no blanks, got {pollutant!r}: AERMOD reads "
                "POLLUTID from one field"
            ))
        elif len(pollutant) > 8:
            result.errors.append(ValidationError(
                pathway, "pollutant_id",
                f"'{pollutant}' is longer than 8 characters; AERMOD keeps only "
                f"'{pollutant[:8]}' (POLLUT is CHARACTER*8), so the output files and "
                "any pollutant-specific processing see the shortened name",
                severity="warning",
            ))

        # Elevation units
        if control.elevation_units not in VALID_ELEVATION_UNITS:
            result.errors.append(ValidationError(
                pathway, "elevation_units",
                f"must be 'METERS' or 'FEET', got '{control.elevation_units}'"
            ))

        cls._validate_urban_option(control, result)

        # Half-life and decay coefficient (mutually exclusive in AERMOD)
        if control.half_life is not None and control.decay_coefficient is not None:
            result.errors.append(ValidationError(
                pathway, "half_life/decay_coefficient",
                "cannot specify both half_life and decay_coefficient"
            ))

        if control.half_life is not None and control.half_life <= 0:
            result.errors.append(ValidationError(
                pathway, "half_life", f"must be > 0, got {control.half_life}"
            ))

        if control.decay_coefficient is not None and control.decay_coefficient < 0:
            result.errors.append(ValidationError(
                pathway, "decay_coefficient",
                f"must be >= 0, got {control.decay_coefficient}"
            ))

    @classmethod
    def _validate_urban_option(cls, control, result: ValidationResult):
        """The single-area URBANOPT fields: ``population [name [roughness]]``.

        ``coset.f`` URBOPT reads the population from the first field, so a
        name or a roughness without one would be written with a made-up
        population, and the roughness is the third field, so it needs the
        name before it. ``urban_areas``, when set, is what the deck gets.
        A population below 100 is E203 (URBOPT 4851-4854, 4917-4920).
        """
        pathway = "ControlPathway"
        areas = getattr(control, "urban_areas", None)
        populations = ([(f"urban_areas[{i}].population", a.population)
                        for i, a in enumerate(areas)] if areas
                       else [("urban_population", control.urban_population)])
        for field_name, population in populations:
            if _is_number(population) and population < 100:
                result.errors.append(ValidationError(
                    pathway, field_name,
                    f"must be >= 100, got {population}: AERMOD refuses a smaller "
                    "urban population (E203)"
                ))
        if areas:
            return
        if control.urban_roughness is not None and not control.urban_option:
            result.errors.append(ValidationError(
                pathway, "urban_roughness",
                "needs urban_option (the urban area name): AERMOD reads the "
                "roughness from the third URBANOPT field, after the name"
            ))
        if control.urban_population is None and (
                control.urban_option or control.urban_roughness is not None):
            result.errors.append(ValidationError(
                pathway, "urban_population",
                "must be set when urban_option or urban_roughness is: URBANOPT "
                "starts with the urban population"
            ))

    #: MODELOPT tokens AERMOD refuses beside DFAULT (coset.f MODOPT,
    #: v24142: "Non-DEFAULT Option Conflict", E204).
    DFAULT_FATAL_OPTIONS = ("ALPHA", "BETA", "PSDCREDIT", "FASTAREA", "FASTALL", "SCIM",
                            "NOURBTRAN", "AREADPLT", "HBP", "TTRM2")
    #: MODELOPT tokens DFAULT overrides: AERMOD warns (W206), drops the
    #: option and runs the regulatory default. FLAT is reported by
    #: :meth:`_validate_dfault_terrain`.
    DFAULT_OVERRIDDEN_OPTIONS = ("NOSTD", "NOCHKD", "SCREEN")

    @classmethod
    def _validate_dfault_options(cls, control, result: ValidationResult):
        """Non-DFAULT MODELOPT options written beside DFAULT.

        coset.f MODOPT stops with E204 for ALPHA (1868-1872), BETA
        (1880-1885), PSDCREDIT (1852-1861), FASTAREA, FASTALL, SCIM,
        NOURBTRAN, AREADPLT, HBP and TTRM2, and drops NOSTD, NOCHKD and
        SCREEN with W206. The tokens are the ones the writer puts on
        MODELOPT (``ControlPathway._model_options``).
        """
        if not getattr(control, "regulatory_default", False):
            return
        model_options = getattr(control, "_model_options", None)
        tokens = [str(t).upper() for t in model_options()] if callable(model_options) else []
        for token in cls.DFAULT_FATAL_OPTIONS:
            if token in tokens:
                result.errors.append(ValidationError(
                    "ControlPathway", "regulatory_default",
                    f"MODELOPT {token} is a non-DFAULT option and AERMOD stops when it is "
                    "written beside DFAULT (E204); set regulatory_default=False for a "
                    f"non-regulatory run, or remove {token}"
                ))
        for token in cls.DFAULT_OVERRIDDEN_OPTIONS:
            if token in tokens:
                result.errors.append(ValidationError(
                    "ControlPathway", "regulatory_default",
                    f"MODELOPT {token} is ignored under DFAULT: AERMOD drops it (W206) "
                    "and runs the regulatory default; set regulatory_default=False "
                    f"to use {token}",
                    severity="warning",
                ))

    #: The numeric fields of CO LOW_WIND in order, with the range coset.f
    #: LOW_WND accepts (v23132, v24142 and v26135 are identical; outside
    #: it is E380). The User's Guide (3.2.3) gives 1.0 as the upper limit
    #: of SVmin and WSmin; the code accepts up to 1.001.
    LOW_WIND_FIELDS = (
        ("SVmin", 0.01, 1.001), ("WSmin", 0.01, 1.001), ("FRANmax", 0.0, 1.0),
        ("SWmin", 0.0, 3.0), ("BigT", 0.5, 48.0), ("FRANmin", 0.0, 1.0),
    )

    @classmethod
    def _validate_low_wind(cls, control, result: ValidationResult):
        """``CO LOW_WIND SVmin [WSmin [FRANmax [SWmin [BigT [FRANmin [PBAL]]]]]]``.

        coset.f (v24142): the card needs MODELOPT ALPHA (E133, dispatch
        at 374-386), and ALPHA is refused beside DFAULT (E204), so no
        regulatory run can carry it. LOW_WND (6779-7014) reads up to six
        numbers and the word PBAL: a field that is not a number is E208,
        one outside its range E380, FRANmin above FRANmax E426, more
        than seven fields E202.
        """
        text = getattr(control, "low_wind_option", None)
        if not text:
            return

        def error(message: str) -> None:
            result.errors.append(ValidationError("ControlPathway", "low_wind_option", message))

        if getattr(control, "regulatory_default", False):
            error("CO LOW_WIND is an ALPHA option, and AERMOD refuses ALPHA beside "
                  "DFAULT (E204): set regulatory_default=False and alpha=True, or "
                  "remove low_wind_option")
        elif not getattr(control, "alpha", False):
            error("CO LOW_WIND needs MODELOPT ALPHA (E133): set alpha=True")

        tokens = str(text).split()
        if len(tokens) > len(cls.LOW_WIND_FIELDS) + 1:
            error(f"has {len(tokens)} fields; CO LOW_WIND takes at most six numbers "
                  "and PBAL (E202)")
            return
        values = {}
        for i, token in enumerate(tokens):
            if i == len(cls.LOW_WIND_FIELDS):
                if token.upper() not in ("PBAL", "PBALANCE"):
                    error(f"the seventh field must be PBAL or PBALANCE, got '{token}' (E203)")
                continue
            name, low, high = cls.LOW_WIND_FIELDS[i]
            try:
                value = fortran_float(token, strict=True)
            except ValueError:
                error(f"{name} must be a number, got '{token}' (E208). The fields are "
                      "SVmin [WSmin [FRANmax [SWmin [BigT [FRANmin [PBAL]]]]]]; a name "
                      "such as LOWWIND3 is not one (those options left AERMOD in v18081)")
                continue
            values[name] = value
            if not low <= value <= high:
                error(f"{name} = {token} is outside {low} to {high} (E380)")
        # An unreadable FRANmax (E208) leaves AERMOD's default, 1.0, in force
        # (coset.f 1557), which FRANmin cannot exceed once it is in range.
        franmax = values.get("FRANmax", 1.0)
        if "FRANmin" in values and values["FRANmin"] > franmax:
            error(f"FRANmin ({values['FRANmin']}) is above FRANmax "
                  f"({franmax}) (E426)")

    @classmethod
    def _validate_dfault_terrain(cls, control, result: ValidationResult):
        """DFAULT with FLAT (coset.f MODOPT, v26135 lines 1622-1683).

        DFAULT forces ELEV and clears FLAT and FLATSRCS before the other
        options are read, then warns W206 for a FLAT token and runs the
        deck in elevated terrain. ``terrain_type`` FLAT and FLATSRCS both
        write FLAT, so the run pyaermod asked for is not the one AERMOD
        makes: receptor and source elevations are used.
        """
        if not getattr(control, "regulatory_default", False):
            return
        terrain = str(getattr(control.terrain_type, "value", control.terrain_type)).upper()
        extra = {str(o).upper() for o in getattr(control, "extra_model_options", []) or []}
        if terrain in ("FLAT", "FLATSRCS") or "FLAT" in extra:
            result.errors.append(ValidationError(
                "ControlPathway", "terrain_type",
                f"terrain_type={terrain} with regulatory_default=True: pyaermod "
                "writes FLAT with DFAULT on MODELOPT, and AERMOD drops FLAT under "
                "DFAULT (AERMOD W206) and runs in elevated terrain, using the "
                "receptor and source elevations; set regulatory_default=False "
                "for a flat-terrain run, or terrain_type=ELEVATED to say what "
                "AERMOD will do",
                severity="warning",
            ))

    # ------------------------------------------------------------------
    # Source pathway
    # ------------------------------------------------------------------

    @classmethod
    def _validate_sources(cls, sources, control, result: ValidationResult,
                          *, unparsed_lines=()):
        if not sources.sources:
            # Sources defined in an SO INCLUDED file are read by AERMOD
            # (aermod.f PREINCLUD); the validator cannot see them.
            if not _kept_lines(unparsed_lines, "SO", ("INCLUDED",)):
                result.errors.append(ValidationError(
                    "SourcePathway", "sources", "must contain at least one source"
                ))
            cls._validate_background_in_groups(sources, unparsed_lines, result)
            return

        cls._validate_source_ids(sources, result)

        has_urban_source = False
        several_urban_areas = len(getattr(control, "urban_areas", None) or []) > 1
        for source in sources.sources:
            # soset.f URBANS: with more than one URBANOPT card (L_MULTURB)
            # URBANSRC names the urban area before the sources.
            if (several_urban_areas and getattr(source, "is_urban", False)
                    and not getattr(source, "urban_area_name", None)):
                result.errors.append(ValidationError(
                    f"{type(source).__name__}({source.source_id})", "urban_area_name",
                    "is_urban=True but urban_area_name is not set, and the project "
                    f"has {len(control.urban_areas)} urban areas: with several "
                    "URBANOPT cards AERMOD reads the area's ID on URBANSRC before "
                    "the sources. Set urban_area_name to one of the urban_id values"
                ))
            cls._validate_source(source, control, result)
            if (getattr(source, "method_2", None) is not None
                    or getattr(source, "platform", None) is not None
                    or getattr(source, "location_type", None) == "SWPOINT"):
                cls._validate_source_options(source, control, result)
            if getattr(source, "is_urban", False):
                has_urban_source = True
        cls._validate_source_flags(sources, control, result)

        # Cross-field: urban sources need a URBANOPT card, which the writer
        # emits for urban_areas, urban_option or urban_population (coset.f
        # URBOPT takes a population alone).
        has_urbanopt = bool(getattr(control, "urban_areas", None)
                            or control.urban_option
                            or control.urban_population is not None)
        if has_urban_source and not has_urbanopt:
            result.errors.append(ValidationError(
                "SourcePathway/ControlPathway", "urban_option",
                "one or more sources have is_urban=True but the project has no URBANOPT: "
                "set ControlPathway.urban_population (or urban_areas)"
            ))

        # Validate background concentration if present
        if sources.background is not None:
            cls._validate_background(sources.background, result)

        # Validate centralized source group definitions
        if sources.group_definitions:
            cls._validate_source_groups(sources, result, unparsed_lines=unparsed_lines)
        cls._validate_background_in_groups(sources, unparsed_lines, result)

        cls._validate_psd_groups(sources, control, result)
        cls._validate_unit_conversions(sources, control, result)
        cls._validate_solid_barriers(sources, control, result)
        cls._validate_line_deposition(sources, control, result)

    #: Source IDs AERMOD keeps for the background pseudo-source (soset.f
    #: SOLOCA E285; SRCGRP accepts them as a group member).
    RESERVED_SOURCE_IDS = frozenset({"BACKGROUND", "BACKGRND"})

    #: Longest source ID AERMOD takes on LOCATION (soset.f SOLOCA E230).
    SOURCE_ID_LENGTH = 12

    @classmethod
    def _validate_source_ids(cls, sources, result: ValidationResult):
        """Source IDs as soset.f SOLOCA reads them (v24142, 2063-2076).

        An ID is one field of at most 12 characters (E230) and not
        BACKGROUND or BACKGRND (E285). AERMOD upper-cases the runstream,
        so ``s1`` and ``S1`` are the same source (E310 duplicate
        LOCATION). Each BUOYLINE segment is a source of its own on
        LOCATION; the BuoyLineSource ID names its BLPGROUP.
        """
        from pyaermod.input_generator import BuoyLineSource

        located: List[tuple] = []  # (pathway, source ID as written on LOCATION)
        blp_groups: List[str] = []
        for src in sources.sources:
            name = f"{type(src).__name__}({src.source_id})"
            if isinstance(src, BuoyLineSource):
                blp_groups.append(src.source_id)
                located.extend((name, seg.source_id) for seg in src.line_segments)
            else:
                located.append((name, src.source_id))

        seen = set()
        for name, sid in located:
            text = "" if sid is None else str(sid)
            if not text.strip():
                result.errors.append(ValidationError(
                    name, "source_id", "must not be blank"))
                continue
            if any(c.isspace() for c in text):
                result.errors.append(ValidationError(
                    name, "source_id",
                    f"'{text}' contains a blank: AERMOD reads the source ID from one "
                    "field, so the rest of the ID shifts every later field"))
            if len(text) > cls.SOURCE_ID_LENGTH:
                result.errors.append(ValidationError(
                    name, "source_id",
                    f"'{text}' is {len(text)} characters; AERMOD takes at most "
                    f"{cls.SOURCE_ID_LENGTH} (E230)"))
            if text.upper() in cls.RESERVED_SOURCE_IDS:
                result.errors.append(ValidationError(
                    name, "source_id",
                    f"'{text}' is reserved for the background concentration (AERMOD E285)"))
            if text.upper() in seen:
                result.errors.append(ValidationError(
                    "SourcePathway", "source_id",
                    f"duplicate source ID '{text}' (AERMOD reads IDs in upper case, "
                    "so IDs differing only in case collide: E310)"))
            seen.add(text.upper())

        seen_groups = set()
        for gid in blp_groups:
            key = str(gid).upper()
            if key in seen_groups:
                result.errors.append(ValidationError(
                    "SourcePathway", "source_id",
                    f"duplicate buoyant line group ID '{gid}'"))
            seen_groups.add(key)

    @classmethod
    def _validate_line_deposition(cls, sources, control, result: ValidationResult):
        """Deposition with RLINE, RLINEXT or BUOYLINE is E251.

        soset.f SRCQA (v24142, lines 1660-1669): with DEPOS, DDEP or WDEP
        set, a deck with any BUOYLINE source, or else any RLINE or
        RLINEXT source, is refused with E251 "Deposition (DEPOS, DDEP,
        WDEP) incompatible with" BUOYLINE or RLINE/RLINEXT. The source
        dataclasses carry the deposition fields, so the error is reported
        here, on every such source, before AERMOD runs. LINE, AREA and
        VOLUME sources take deposition.
        """
        from pyaermod.input_generator import BuoyLineSource, RLineExtSource, RLineSource

        if not (control.calculate_deposition or control.calculate_dry_deposition
                or control.calculate_wet_deposition):
            return
        for src in sources.sources:
            if isinstance(src, BuoyLineSource):
                kind = "BUOYLINE"
            elif isinstance(src, (RLineSource, RLineExtSource)):
                kind = "RLINE/RLINEXT"
            else:
                continue
            result.errors.append(ValidationError(
                f"{type(src).__name__}({src.source_id})", "deposition",
                f"AERMOD refuses deposition (DEPOS, DDEP or WDEP in MODELOPT) with a {kind} "
                "source (AERMOD E251, soset.f SRCQA); turn deposition off or model the "
                "source as LINE, AREA or VOLUME",
            ))

    @classmethod
    def _validate_background(cls, background, result: ValidationResult):
        pathway = "BackgroundConcentration"

        # The writer emits one mode (sectors, else period_values, else
        # uniform_value) and drops the others without a word.
        modes = [name for name, is_set in (
            ("uniform_value", background.uniform_value is not None),
            ("period_values", bool(background.period_values)),
            ("sectors/sector_values",
             bool(background.sectors) or bool(background.sector_values)),
        ) if is_set]
        if len(modes) > 1:
            result.errors.append(ValidationError(
                pathway, modes[0],
                f"{' and '.join(modes)} are {'both' if len(modes) == 2 else 'all'} set; "
                "give one of the three background modes (uniform_value, period_values, "
                "sectors/sector_values): the deck holds only one (AERMOD takes one "
                "flag per sector or for the whole domain, E165), so the writer writes "
                "one of them and drops the others"
            ))

        if background.uniform_value is not None:
            if not _is_number(background.uniform_value):
                result.errors.append(ValidationError(
                    pathway, "uniform_value",
                    f"must be a number, got {background.uniform_value!r}"
                ))
            elif not math.isfinite(background.uniform_value):
                result.errors.append(ValidationError(
                    pathway, "uniform_value",
                    f"must be a finite number, got {background.uniform_value!r}: "
                    "the writer would write it as nan/inf, which AERMOD cannot read"
                ))
            elif background.uniform_value < 0:
                result.errors.append(ValidationError(
                    pathway, "uniform_value",
                    f"must be >= 0, got {background.uniform_value}"
                ))

        if background.period_values:
            for flag, values in background.period_values.items():
                cls._validate_background_profile(
                    pathway, "period_values", str(flag), values, result)
            if len(background.period_values) > 1:
                result.errors.append(ValidationError(
                    pathway, "period_values",
                    "BACKGRND takes one temporal flag, got "
                    f"{', '.join(map(str, background.period_values))} (AERMOD E165)"
                ))

        # Sector ids other than 1..N are one error; the per-sector checks
        # below (E238, an undefined sector_id) would only repeat it in
        # other words, so they wait until the ids are right.
        sector_ids_ok = not background.sectors or sorted(
            s.sector_id for s in background.sectors) == list(
                range(1, len(background.sectors) + 1))

        if background.sectors:
            # soset.f BGSECTOR: 2 to 6 directions, ascending, sectors at
            # least 30 degrees wide (E222/E227), as O3SECTOR and NOXSECTR.
            cls._validate_sectors(
                "sectors",
                [s.start_direction for s in sorted(background.sectors,
                                                   key=lambda s: s.sector_id)],
                pathway, result)
            # AERMOD numbers the sectors by their position on BGSECTOR, and
            # the writer emits SECT{sector_id} in sector_id order, so the
            # ids must be exactly 1..N; SECTk with k > N is E203.
            ids = sorted(s.sector_id for s in background.sectors)
            if not sector_ids_ok:
                result.errors.append(ValidationError(
                    pathway, "sectors",
                    f"sector ids must be 1..{len(ids)}, one per sector, got {ids}: "
                    "AERMOD numbers sectors by their order on BGSECTOR and stops "
                    "on any other SECTn (E203 BGSECTOR ID)"
                ))
            # soset.f SRCQA: every sector needs a non-HOURLY profile (E238).
            with_values = {sid for sid, _flag in (background.sector_values or {})}
            for sid in ids if sector_ids_ok else []:
                if sid not in with_values:
                    result.errors.append(ValidationError(
                        pathway, "sector_values",
                        f"sector {sid} has no BACKGRND values: AERMOD stops with "
                        f"E238 (Not Enough BACKGRND Concentration Values, SECT{sid})"
                    ))

        if background.sector_values and not background.sectors:
            # The writer emits BACKGRND SECTn lines only beside BGSECTOR
            # sectors, so these values would leave no trace in the deck;
            # AERMOD itself rejects SECTn without BGSECTOR (E171).
            result.errors.append(ValidationError(
                pathway, "sector_values",
                "sector_values are set without sectors: the writer writes no "
                "BACKGRND SECTn line without BGSECTOR sectors, so the background "
                "would be left out of the deck (AERMOD rejects SECTn without "
                "BGSECTOR, E171); give sectors, or use period_values for one "
                "whole-domain profile"
            ))

        if background.sectors and background.sector_values:
            valid_ids = {s.sector_id for s in background.sectors}
            for (sid, flag), values in background.sector_values.items():
                if sector_ids_ok and sid not in valid_ids:
                    result.errors.append(ValidationError(
                        pathway, "sector_values",
                        f"sector_id {sid} not defined in sectors list"
                    ))
                cls._validate_background_profile(
                    pathway, "sector_values", str(flag), values, result,
                    where=f" for sector {sid}")
            flags: dict = {}
            for sid, flag in background.sector_values:
                flags.setdefault(sid, []).append(str(flag))
            for sid, names in sorted(flags.items()):
                if len(names) > 1:
                    result.errors.append(ValidationError(
                        pathway, "sector_values",
                        f"BACKGRND takes one temporal flag for sector {sid}, got "
                        f"{', '.join(names)} (AERMOD E165)"
                    ))

    @classmethod
    def _validate_background_verbatim(cls, project, result: ValidationResult):
        """A modelled background beside BACKGRND/BGSECTOR lines kept verbatim.

        A deck with a sector HOURLY file is kept whole in ``unparsed_lines``
        and ``sources.background`` is None. A modelled background set on
        top writes a second set of cards and AERMOD stops (probe 33c:
        E203). A modelled whole-domain background beside a verbatim
        whole-domain BACKGRND line that is not HOURLY (a second flag, or a
        value with none) is two value options for the domain (E165, or
        E201 for the bare value). A whole-domain ``BACKGRND HOURLY file``
        kept verbatim beside a whole-domain flag is a valid pair (probe
        32d).
        """
        background = getattr(project.sources, "background", None)
        if background is None:
            return
        kept = [ln for ln in getattr(project, "unparsed_lines", None) or []
                if str(ln.pathway).upper() == "SO"
                and str(ln.keyword).upper() in ("BACKGRND", "BGSECTOR")]
        if not kept:
            return
        if background.sectors:
            conflicting = kept
            modelled = "a sector background (sectors)"
        elif background.uniform_value is not None or background.period_values:
            # Every verbatim line but a whole-domain HOURLY file: the
            # sector form (BGSECTOR, SECTn), or a second whole-domain
            # value line.
            conflicting = [
                ln for ln in kept
                if not (str(ln.keyword).upper() == "BACKGRND" and ln.fields
                        and str(ln.fields[0]).upper() == "HOURLY")]
            modelled = "a whole-domain background (uniform_value/period_values)"
        else:
            return
        if not conflicting:
            return
        shown = "; ".join(f"line {ln.lineno}: {ln.keyword} {' '.join(ln.fields)}".strip()
                          for ln in conflicting[:3])
        more = f" and {len(conflicting) - 3} more" if len(conflicting) > 3 else ""
        result.errors.append(ValidationError(
            "BackgroundConcentration", "unparsed_lines",
            f"{modelled} is set, and the project also keeps SO BACKGRND/BGSECTOR "
            f"lines verbatim from the source deck ({shown}{more}); both are written "
            "and AERMOD stops (E203 for a second sector form, E165 for a second "
            "whole-domain flag, E201 for a value without one). Remove those lines from "
            "project.unparsed_lines, or remove the modelled background "
            "(sources.background = None)"
        ))

    @classmethod
    def _check_temporal_values(cls, flag, values, *, where: str = "",
                               non_negative: bool = False) -> List[str]:
        """Problems with one temporal-variation profile, as soset.f reads
        BACKGRND, O3VALUES and NOX_VALS: a flag of EMISFACT's table
        (:data:`TEMPORAL_FLAG_COUNTS`), exactly its number of values, and
        every value a finite number (and, with ``non_negative``, none below
        0); NaN and +/-inf would be written as ``nan``/``inf``, which
        AERMOD cannot read.
        ``values`` may be a single value or a list, tuple, range, numpy
        array or pandas Series of values; a string is one value, and not
        a number. Any other iterable (a one-shot iterator such as a map
        or a generator, which the writer would then find empty) is one
        problem asking for a list, and nothing is taken from it."""
        try:
            values = value_list(values)
        except TypeError as exc:
            return [f"values for {flag!r}{where}: {exc}"]
        problems: List[str] = []
        expected = TEMPORAL_FLAG_COUNTS.get(str(flag).upper())
        if expected is None:
            problems.append(
                f"unknown temporal flag {flag!r}{where}; AERMOD accepts "
                f"{', '.join(TEMPORAL_FLAG_COUNTS)} (a temporal-variation flag, "
                "not an averaging period)")
        elif len(values) != expected:
            problems.append(
                f"{flag}{where} needs {expected} value{'s' if expected != 1 else ''}, "
                f"got {len(values)}")
        bad = [v for v in values if not _is_number(v)]
        if bad:
            problems.append(
                f"values for {flag!r}{where} must be numbers, got "
                f"{', '.join(repr(v) for v in bad[:4])}")
        non_finite = [v for v in values if _is_number(v) and not math.isfinite(v)]
        if non_finite:
            problems.append(
                f"values for {flag!r}{where} must be finite numbers, got "
                f"{', '.join(repr(v) for v in non_finite[:4])} (written as nan/inf, "
                "which AERMOD cannot read)")
        if non_negative and any(_is_finite_number(v) and v < 0 for v in values):
            problems.append(f"values for '{flag}'{where} must be >= 0")
        return problems

    @classmethod
    def _validate_background_profile(cls, pathway, field_name, flag, values, result,
                                     *, where=""):
        """One BACKGRND flag and its values, as soset.f reads them: a
        flag of EMISFACT's table and exactly its number of values, none
        of them negative."""
        for message in cls._check_temporal_values(flag, values, where=where,
                                                  non_negative=True):
            result.errors.append(ValidationError(pathway, field_name, message))

    @classmethod
    def _validate_source_options(cls, source, control, result: ValidationResult):
        """METHOD_2, PLATFORM and SWPOINT as soset.f METH_2, PLATFM and
        SRCSIZ/SWPARM check them (probe decks 21-23b)."""
        method_2 = getattr(source, "method_2", None)
        platform = getattr(source, "platform", None)
        sidewash = getattr(source, "location_type", None) == "SWPOINT"
        name = f"{type(source).__name__}({source.source_id})"
        alpha = bool(getattr(control, "alpha", False))
        dfault = bool(getattr(control, "regulatory_default", False))

        if method_2 is not None:
            if not alpha:
                result.errors.append(ValidationError(
                    name, "method_2", "METHOD_2 needs the ALPHA option (E198)"
                ))
            if dfault:
                result.errors.append(ValidationError(
                    name, "method_2", "METHOD_2 is a non-DFAULT option (E197)"
                ))
            if not 0.0 <= method_2.fine_mass_fraction <= 1.0:
                result.errors.append(ValidationError(
                    name, "method_2.fine_mass_fraction",
                    f"must be 0-1, got {method_2.fine_mass_fraction} (E332)"
                ))
            if getattr(source, "particle_deposition", None) is not None:
                result.errors.append(ValidationError(
                    name, "method_2",
                    "a source has either METHOD_2 or PARTDIAM/MASSFRAX/PARTDENS (E386)"
                ))

        if platform is not None:
            from pyaermod.input_generator import PointSource

            if not isinstance(source, PointSource):
                result.errors.append(ValidationError(
                    name, "platform", "PLATFORM applies to POINT, POINTCAP and POINTHOR only (E631)"
                ))
            if not alpha:
                result.errors.append(ValidationError(
                    name, "platform", "PLATFORM needs the ALPHA option (E198)"
                ))

        if sidewash:
            if not alpha:
                result.errors.append(ValidationError(
                    name, "type", "SWPOINT needs the ALPHA option (E198)"
                ))
            cls._check_ranges(name, source, result, (("release_height", ">=", 0, " (E209)"),))

    @classmethod
    def _validate_source_flags(cls, sources, control, result: ValidationResult):
        """ARCFTSRC and HBPSRCID (soset.f AIRCRAFT, HBPSOURCE; probe deck 25)."""
        pathway = "SourcePathway"
        extra = {str(o).upper() for o in getattr(control, "extra_model_options", []) or []}
        alpha = bool(getattr(control, "alpha", False))
        if getattr(sources, "aircraft_sources", None):
            if not getattr(control, "aircraft_option", False):
                result.errors.append(ValidationError(
                    pathway, "aircraft_sources",
                    "ARCFTSRC needs CO ARCFTOPT (ControlPathway.aircraft_option, E821)"
                ))
            result.errors.append(ValidationError(
                pathway, "aircraft_sources",
                "aircraft sources need an HOUREMIS file with the aircraft record for "
                "every hour (E823); pyaermod keeps HOUREMIS lines in unparsed_lines",
                severity="warning",
            ))
        if getattr(sources, "hbp_sources", None):
            if "HBP" not in extra:
                result.errors.append(ValidationError(
                    pathway, "hbp_sources", "HBPSRCID needs MODELOPT HBP (E130)"
                ))
            if not alpha:
                result.errors.append(ValidationError(
                    pathway, "hbp_sources", "HBPSRCID needs the ALPHA option (E198)"
                ))

    @classmethod
    def _validate_source(cls, source, control, result: ValidationResult):
        from pyaermod.input_generator import (
            AreaCircSource,
            AreaPolySource,
            AreaSource,
            BuoyLineSource,
            LineSource,
            OpenPitSource,
            PointSource,
            RLineExtSource,
            RLineSource,
            VolumeSource,
        )

        if isinstance(source, PointSource):
            cls._validate_point_source(source, result)
        elif isinstance(source, AreaSource):
            cls._validate_area_source(source, result)
        elif isinstance(source, AreaCircSource):
            cls._validate_area_circ_source(source, result)
        elif isinstance(source, AreaPolySource):
            cls._validate_area_poly_source(source, result)
        elif isinstance(source, VolumeSource):
            cls._validate_volume_source(source, result)
        elif isinstance(source, (LineSource, RLineSource)):
            cls._validate_line_source(source, result)
        elif isinstance(source, RLineExtSource):
            cls._validate_rline_ext_source(source, result)
        elif isinstance(source, BuoyLineSource):
            cls._validate_buoyline_source(source, result)
        elif isinstance(source, OpenPitSource):
            cls._validate_openpit_source(source, result)

        # Deposition validation for all source types
        cls._validate_deposition_params(source, control, result)

        if isinstance(source, AreaSource):
            cls._validate_area_depth_hint(source, control, result)

        # Per-source NO2/NOx ratio (NO2RATIO applies to any source type;
        # soset.f NO2RAT rejects values outside 0-1 with E336)
        ratio = getattr(source, "no2_ratio", None)
        if ratio is not None and not (0 <= ratio <= 1):
            result.errors.append(ValidationError(
                f"{type(source).__name__}({source.source_id})", "no2_ratio",
                f"must be between 0 and 1, got {ratio}"
            ))

        # soset.f SRCQA: with OLM, PVMRM, GRSM or TTRM a source that has
        # neither NO2STACK nor its own NO2RATIO is E336; AERMOD has no
        # default in-stack ratio.
        chemistry = getattr(control, "chemistry", None)
        if (chemistry is not None and ratio is None
                and chemistry.default_no2_ratio is None
                and getattr(chemistry.method, "value", chemistry.method) in NO2STACK_METHODS):
            method = getattr(chemistry.method, "value", chemistry.method)
            result.errors.append(ValidationError(
                f"{type(source).__name__}({source.source_id})", "no2_ratio",
                f"no in-stack NO2/NOx ratio: {method} needs one for every source and "
                "AERMOD has no default (E336). Set the source's no2_ratio or "
                "ChemistryOptions.default_no2_ratio (NO2STACK)"
            ))

        if isinstance(source, RLineExtSource):
            cls._validate_rline_configuration(source, control, result)

    @classmethod
    def _validate_deposition_params(cls, source, control, result: ValidationResult):
        name = f"{type(source).__name__}({source.source_id})"
        gas_dep = getattr(source, "gas_deposition", None)
        particle_dep = getattr(source, "particle_deposition", None)

        dep_enabled = (control.calculate_deposition or
                       control.calculate_dry_deposition or
                       control.calculate_wet_deposition)
        # METHOD_2 gives the source its particle category (soset.f METH_2
        # sets INPD = 1), which satisfies SRCQA's E242 test.
        has_dep = gas_dep is not None or particle_dep is not None
        has_category = has_dep or getattr(source, "method_2", None) is not None

        if gas_dep is not None and particle_dep is not None:
            # soset.f SRCQA 1187-1191: particle categories on a gas source
            result.errors.append(ValidationError(
                name, "deposition",
                "a source takes either gas_deposition (GASDEPOS) or "
                "particle_deposition (PARTDIAM/MASSFRAX/PARTDENS), not both (AERMOD E289)",
            ))

        if has_dep and not dep_enabled:
            result.errors.append(ValidationError(
                name, "deposition",
                "deposition parameters specified but DEPOS/DDEP/WDEP not enabled in MODELOPT",
                severity="warning",
            ))
        elif (dep_enabled and not has_category
              and getattr(control, "gas_deposition_velocity", None) is None):
            # soset.f SRCQA: a source with no particle categories and no gas
            # deposition parameters under DEPOS/DDEP/WDEP is E242 (GASDEPVD
            # supplies a gas's dry deposition velocity for every source).
            result.errors.append(ValidationError(
                name, "deposition",
                "DEPOS/DDEP/WDEP is enabled in MODELOPT but the source has no "
                "gas_deposition or particle_deposition parameters (AERMOD E242)",
            ))

        if gas_dep:
            cls._validate_gas_deposition(name, gas_dep, control, result)

        if particle_dep:
            cls._validate_particle_deposition(name, particle_dep, result)

    @classmethod
    def _validate_particle_deposition(cls, name, particle_dep, result: ValidationResult):
        """PARTDIAM / MASSFRAX / PARTDENS (Method 1) as AERMOD v26135 checks
        them.

        The number of categories has no fixed limit: soset.f allocates the
        arrays to the deck's own count (NPDMAX), and a 25-category OPENPIT
        deck runs to completion. soset.f INPPDM refuses a diameter <= 0.001
        or > 1000 microns (E335, lines 4920-4922), INPPHI a mass fraction
        outside 0-1 (E332, lines 5048-5050), and INPPDN a density <= 0
        (E334) while warning at <= 0.1 g/cm^3 (W334, lines 5168-5173).
        SRCQA requires the three counts to agree (E240, lines 1216-1219)
        and warns when the fractions sum outside 0.98-1.02 (W330, lines
        1221-1231).

        The ranges are checked on the values as the deck will carry them,
        because those are what AERMOD reads: the writer rounds PARTDIAM and
        PARTDENS to 4 significant figures and MASSFRAX to 6 decimals, so a
        1000.4 um diameter is written, and accepted, as 1000.
        """
        diameters, fractions, densities = cls._particle_values_as_written(particle_dep)

        def add(field_name, message, severity="error"):
            result.errors.append(ValidationError(name, field_name, message, severity=severity))

        if len(diameters) != len(fractions):
            add("particle_deposition",
                "diameters and mass_fractions must have same length (AERMOD E240)")
        if len(diameters) != len(densities):
            add("particle_deposition",
                "diameters and densities must have same length (AERMOD E240)")

        bad = [d for d in diameters if d <= 0.001 or d > 1000.0]
        if bad:
            add("particle_deposition.diameters",
                f"diameters must each be > 0.001 and <= 1000 microns, got {bad} (AERMOD E335)")

        bad = [f for f in fractions if f < 0.0 or f > 1.0]
        if bad:
            add("particle_deposition.mass_fractions",
                f"mass fractions must each be 0-1, got {bad} (AERMOD E332)")
        if fractions:
            total = 0.0
            for f in fractions:  # summed in order, as SRCQA does
                total += f
            if total < 0.98 or total > 1.02:
                add("particle_deposition.mass_fractions",
                    f"sum to {total:.4f}, outside 1.0 +/- 2% (AERMOD W330)", "warning")

        bad = [r for r in densities if r <= 0.0]
        if bad:
            add("particle_deposition.densities",
                f"densities must each be > 0 g/cm^3, got {bad} (AERMOD E334)")
        low = [r for r in densities if 0.0 < r <= 0.1]
        if low:
            add("particle_deposition.densities",
                f"densities {low} are <= 0.1 g/cm^3, which AERMOD flags as possibly "
                "out of range (AERMOD W334)", "warning")

        # soset.f VDP1 settles each category by Stokes' law from PARTDIAM
        # and PARTDENS together, so PARTDIAM is the physical diameter of a
        # particle of PARTDENS. Aerodynamic diameters (emission factors,
        # impactors) only settle as intended beside a density of 1; beside
        # a higher density AERMOD settles every category that many times
        # too fast. AERMOD itself cannot tell the two apart, so there is
        # no message code; the convention is known only when
        # SizeDistribution.to_deposition_params recorded it.
        convention = getattr(particle_dep, "diameter_convention", None)
        if convention not in (None, "aerodynamic", "stokes"):
            add("particle_deposition.diameter_convention",
                f"must be 'aerodynamic', 'stokes' or None, got {convention!r}")
        elif convention == "aerodynamic":
            heavy = sorted({r for r in densities if r != 1.0})
            if heavy:
                add("particle_deposition.diameters",
                    f"the diameters are aerodynamic but the densities include {heavy} g/cm^3: "
                    "AERMOD reads PARTDIAM as the Stokes diameter of a particle of PARTDENS, "
                    "so these categories settle about that many times faster than their "
                    "aerodynamic size says. Convert them with pyaermod.psd.aerodynamic_to_stokes "
                    "(SizeDistribution.to_deposition_params does by default) or use a density "
                    "of 1.0", "warning")

    @staticmethod
    def _particle_values_as_written(particle_dep):
        """PARTDIAM, MASSFRAX and PARTDENS read back from the lines the
        writer produces for them, so the checks see AERMOD's numbers."""
        from pyaermod.sources import _deposition_to_aermod_lines

        written = {}
        for line in _deposition_to_aermod_lines("SRC", None, particle_dep):
            keyword, _, *values = line.split()
            written[keyword] = [float(v) for v in values]
        return written["PARTDIAM"], written["MASSFRAX"], written["PARTDENS"]

    #: Pollutants for which soset.f GASDEP substitutes a built-in value
    #: when a GASDEPOS field is 0 (warning W473); any other zero is E380.
    GASDEPOS_LOOKUP_POLLUTANTS = frozenset({"HG0", "HGII", "TCDD", "BAP", "SO2", "NO2"})

    @classmethod
    def _validate_gas_deposition(cls, name, gas_dep, control, result: ValidationResult):
        """GASDEPOS as soset.f GASDEP reads it: ``Da Dw rcl Henry``.

        Every field must be positive (E380) unless it is 0 for a
        pollutant AERMOD has a built-in value for; the keyword needs the
        ALPHA option (E198) and is refused alongside GASDEPVD (E195).
        """
        pollutant = getattr(control.pollutant_id, "value", control.pollutant_id)
        zero_ok = str(pollutant).upper() in cls.GASDEPOS_LOOKUP_POLLUTANTS
        for field_name, label in (("diffusivity", "Da"),
                                  ("diffusivity_water", "Dw"),
                                  ("cuticular_resistance", "rcl"),
                                  ("henry_constant", "Henry")):
            value = getattr(gas_dep, field_name)
            if value < 0 or (value == 0 and not zero_ok):
                result.errors.append(ValidationError(
                    name, f"gas_deposition.{field_name}",
                    f"must be > 0 ({label} in GASDEPOS; AERMOD E380), got {value}"
                    + ("" if zero_ok else
                       "; 0 selects AERMOD's built-in value only for "
                       "HG0, HGII, TCDD, BAP, SO2 and NO2")
                ))
        if not getattr(control, "alpha", False):
            result.errors.append(ValidationError(
                name, "gas_deposition",
                "GASDEPOS needs ControlPathway.alpha=True: AERMOD requires "
                "the non-DFAULT ALPHA option for gas deposition (E198)"
            ))
        if getattr(control, "gas_deposition_velocity", None) is not None:
            result.errors.append(ValidationError(
                name, "gas_deposition",
                "cannot be combined with ControlPathway.gas_deposition_velocity: "
                "AERMOD rejects GASDEPOS with GASDEPVD (E195)"
            ))

    #: The comparison that breaks each kind of bound in a range row.
    _BOUND_BROKEN = {">=": operator.lt, ">": operator.le, "<=": operator.gt}

    @classmethod
    def _check_ranges(cls, name, obj, result: ValidationResult, rows, *, optional=False):
        """Report each ``(field, bound, limit[, note])`` row that ``obj`` breaks.

        ``("stack_height", ">=", 0, " (AERMOD E209)")`` gives "must be >= 0,
        got -5.0 (AERMOD E209)". Rows run in order; a dotted field reads a
        nested object; ``optional`` skips a field that is None.
        """
        for field_name, bound, limit, *note in rows:
            value = operator.attrgetter(field_name)(obj)
            if optional and value is None:
                continue
            if cls._BOUND_BROKEN[bound](value, limit):
                result.errors.append(ValidationError(
                    name, field_name,
                    f"must be {bound} {limit}, got {value}{''.join(note)}"
                ))

    @staticmethod
    def _check_building_arrays(name, src, result: ValidationResult):
        """Building downwash array lengths."""
        for field_name in ("building_height", "building_width", "building_length",
                           "building_x_offset", "building_y_offset"):
            val = getattr(src, field_name, None)
            if val is not None and isinstance(val, list) and len(val) != 36:
                result.errors.append(ValidationError(
                    name, field_name,
                    f"must have exactly 36 values (one per 10° sector), got {len(val)}"
                ))

    @staticmethod
    def _check_zero_length(name, line, result: ValidationResult):
        if (line.x_start == line.x_end and line.y_start == line.y_end):
            result.errors.append(ValidationError(
                name, "coordinates",
                "start and end points are identical (zero-length line)"
            ))

    @classmethod
    def _validate_point_source(cls, src, result: ValidationResult):
        name = f"PointSource({src.source_id})"

        # soset.f PPARM (v24142, 2713-2818): a negative height or diameter
        # is E209; a zero diameter is reset to 1e-5 m and a zero height
        # is a ground-level release, both accepted.
        cls._check_ranges(name, src, result, (
            ("stack_height", ">=", 0, " (AERMOD E209)"),
            ("stack_diameter", ">=", 0, " (AERMOD E209)"),
        ))

        # PPARM 2770-2781: Ts == 0 is a release at ambient temperature and
        # Ts < 0 a fixed Ts - Ta offset of |Ts| (calc1.f FLUXES); only
        # 0 < Ts < 200 K is refused (E320).
        if 0 < src.stack_temp < 200:
            result.errors.append(ValidationError(
                name, "stack_temp",
                f"{src.stack_temp} K is out of range: AERMOD refuses a stack "
                "temperature between 0 and 200 K (E320). Use 0 for a release at "
                "ambient temperature, or a negative value -dT for Ts = Ta + dT"
            ))

        # PPARM 2784-2788: Vs < 0 is W325; AERMOD sets it to 1e-5 m/s and
        # runs. 0 <= Vs < 1e-5 is reset the same way without a message.
        if src.exit_velocity < 0:
            result.errors.append(ValidationError(
                name, "exit_velocity",
                f"{src.exit_velocity} m/s is negative: AERMOD warns (W325), sets "
                "the exit velocity to 1.0E-5 m/s and runs",
                severity="warning",
            ))

        cls._check_ranges(name, src, result, (("emission_rate", ">=", 0),))
        cls._check_building_arrays(name, src, result)

        # Cross-field: building height < stack height for downwash to be meaningful
        bh = src.building_height
        if bh is not None:
            max_bh = max(bh) if isinstance(bh, list) else bh
            if src.stack_height > 0 and max_bh >= src.stack_height:
                result.errors.append(ValidationError(
                    name, "building_height",
                    f"building height ({max_bh}) >= stack height ({src.stack_height}); "
                    f"downwash requires building height < stack height",
                    severity="warning",
                ))

    @classmethod
    def _validate_area_source(cls, src, result: ValidationResult):
        name = f"AreaSource({src.source_id})"
        cls._check_ranges(name, src, result, (
            ("initial_lateral_dimension", ">", 0),
            ("initial_vertical_dimension", ">", 0),
            ("emission_rate", ">=", 0),
            ("release_height", ">=", 0),
        ))
        cls._check_building_arrays(name, src, result)

    @classmethod
    def _validate_area_depth_hint(cls, src, control, result: ValidationResult):
        """An AREA source that stands in for a pit (``depth_hint`` set).

        AERMOD's OPENPIT algorithm does three things an AREA release
        cannot (v24142): ESCAPE (pitarea.f 1175-1210) lets each particle
        category out of the pit with the fraction
        ``1 / (1 + Vg / (0.029 Uref))``, the rest settling inside, and
        OCALC runs it whenever the source has particle categories
        (calc1.f 4921-4935), deposition on or not; OPARM releases the
        plume with ``sigma-z0 = depth / 4.3`` (soset.f 3558-3561) from an
        effective area on the upwind side sized by the relative depth
        (PDEPTH, PTFRAC, PITEFF); and PITCALC skips receptors inside the
        pit. The hint is written nowhere: AREA has no depth.
        """
        hint = src.depth_hint
        if hint is None:
            return
        name = f"AreaSource({src.source_id})"
        if not (isinstance(hint, (int, float)) and math.isfinite(hint) and hint > 0):
            result.errors.append(ValidationError(
                name, "depth_hint", f"must be above 0 m, got {hint!r}"))
            return
        dep_enabled = (control.calculate_deposition or control.calculate_dry_deposition
                       or control.calculate_wet_deposition)
        particles = (getattr(src, "particle_deposition", None) is not None
                     or getattr(src, "method_2", None) is not None)
        if not (dep_enabled or particles):
            return
        why = "deposition on" if dep_enabled else "particle categories"
        result.errors.append(ValidationError(
            name, "depth_hint",
            f"stands in for a pit {hint:g} m deep with {why}: an AREA source releases "
            "at the surface and nothing settles inside the pit. AERMOD's OPENPIT source "
            "adds the escape fraction 1 / (1 + Vg / (0.029 Uref)) per particle category "
            "(pitarea.f ESCAPE), a release with sigma-z0 = depth / 4.3 from an effective "
            "area on the upwind side (soset.f OPARM, pitarea.f PITEFF) and skips receptors "
            "inside the pit (calc1.f PITCALC). Build one with "
            f"OpenPitSource.from_area(source, depth={hint:g})",
            severity="warning",
        ))

    @classmethod
    def _validate_area_circ_source(cls, src, result: ValidationResult):
        cls._check_ranges(f"AreaCircSource({src.source_id})", src, result, (
            ("radius", ">", 0),
            ("emission_rate", ">=", 0),
            ("release_height", ">=", 0),
            ("num_vertices", ">=", 3),
        ))

    @classmethod
    def _validate_area_poly_source(cls, src, result: ValidationResult):
        name = f"AreaPolySource({src.source_id})"

        if len(src.vertices) < 3:
            result.errors.append(ValidationError(
                name, "vertices",
                f"must have at least 3 vertices, got {len(src.vertices)}"
            ))

        cls._check_ranges(name, src, result, (
            ("emission_rate", ">=", 0),
            ("release_height", ">=", 0),
        ))

    @classmethod
    def _validate_volume_source(cls, src, result: ValidationResult):
        name = f"VolumeSource({src.source_id})"
        cls._check_ranges(name, src, result, (
            ("initial_lateral_dimension", ">", 0),
            ("initial_vertical_dimension", ">", 0),
            ("emission_rate", ">=", 0),
            ("release_height", ">=", 0),
        ))
        cls._check_building_arrays(name, src, result)

    #: Range rows for a source's ``street_canyon``.
    _STREET_CANYON_RANGES = (
        ("street_canyon.building_height", ">", 0),
        ("street_canyon.street_width", ">", 0),
    )

    @classmethod
    def _validate_line_source(cls, src, result: ValidationResult):
        from pyaermod.input_generator import RLineSource
        src_type = "RLineSource" if isinstance(src, RLineSource) else "LineSource"
        name = f"{src_type}({src.source_id})"

        cls._check_ranges(name, src, result, (
            ("emission_rate", ">=", 0),
            ("release_height", ">=", 0),
            ("initial_lateral_dimension", ">", 0),
        ))
        cls._check_zero_length(name, src, result)

        # Street canyon validation (RLineSource only; LineSource has no canyon)
        if isinstance(src, RLineSource) and src.street_canyon is not None:
            cls._check_ranges(name, src, result, cls._STREET_CANYON_RANGES)

    @classmethod
    def _validate_rline_ext_source(cls, src, result: ValidationResult):
        name = f"RLineExtSource({src.source_id})"

        cls._check_ranges(name, src, result, (
            ("emission_rate", ">=", 0),
            ("road_width", ">", 0),
            ("init_sigma_z", ">=", 0),
        ))
        cls._check_zero_length(name, src, result)

        # Barrier validation
        cls._check_ranges(name, src, result, (
            ("barrier_height_1", ">=", 0),
            ("barrier_height_2", ">=", 0),
        ), optional=True)

        # Depression validation
        if src.depression_depth is not None and src.depression_depth > 0:
            result.errors.append(ValidationError(
                name, "depression_depth",
                f"must be <= 0 (negative depth), got {src.depression_depth}"
            ))
        cls._check_ranges(name, src, result, (
            ("depression_wtop", ">=", 0),
            ("depression_wbottom", ">=", 0),
        ), optional=True)
        if (src.depression_wbottom is not None and src.depression_wtop is not None
                and src.depression_wbottom > src.depression_wtop):
            result.errors.append(ValidationError(
                name, "depression_wbottom",
                f"must be <= depression_wtop ({src.depression_wtop}), got {src.depression_wbottom}"
            ))

        # Street canyon validation
        if src.street_canyon is not None:
            cls._check_ranges(name, src, result, cls._STREET_CANYON_RANGES)

    @classmethod
    def _validate_buoyline_source(cls, src, result: ValidationResult):
        name = f"BuoyLineSource({src.source_id})"

        cls._check_ranges(name, src, result, (
            ("avg_buoyancy_parameter", ">", 0),
            ("avg_line_length", ">", 0),
            ("avg_building_height", ">", 0),
        ))

        if not src.line_segments:
            result.errors.append(ValidationError(
                name, "line_segments",
                "must have at least one line segment"
            ))

        for seg in src.line_segments:
            seg_name = f"BuoyLineSegment({seg.source_id})"
            cls._check_ranges(seg_name, seg, result, (
                ("emission_rate", ">=", 0),
                ("release_height", ">=", 0),
                ("release_height", "<=", 3000),
            ))
            cls._check_zero_length(seg_name, seg, result)

    #: soset.f OPARM substitutes this for an XINIT or YINIT below it (W320)
    #: "to avoid zero-divide and underflow", then uses it in the depth and
    #: aspect-ratio checks.
    OPENPIT_MIN_DIMENSION = 1.0e-5

    @classmethod
    def _openpit_dimensions(cls, src):
        """XINIT and YINIT as OPARM leaves them: a value below 1e-5 m is
        raised to 1e-5 m (soset.f 3549-3553, 3562-3566); a negative one
        is E209 and left alone."""
        return tuple(
            cls.OPENPIT_MIN_DIMENSION if 0.0 <= d < cls.OPENPIT_MIN_DIMENSION else d
            for d in (src.x_dimension, src.y_dimension)
        )

    @classmethod
    def _validate_openpit_source(cls, src, result: ValidationResult):
        """SRCPARAM as soset.f OPARM checks it (v26135, lines 3530-3595).

        ``Qemis Hs Xinit Yinit Volume [Angle]``: W320 for a zero emission
        rate, Hs > 200 m, Xinit/Yinit below 1e-5 m or above 2000 m, and
        |Angle| > 180; E209 for a negative Hs, Xinit, Yinit or a volume
        <= 0; W392 for an aspect ratio above 10; E322 when Hs exceeds the
        effective depth Volume / (Xinit * Yinit).
        """
        name = f"OpenPitSource({src.source_id})"

        def add(field_name, message, severity="error"):
            result.errors.append(ValidationError(name, field_name, message, severity=severity))

        if src.emission_rate < 0:
            add("emission_rate", f"must be >= 0, got {src.emission_rate}")
        elif src.emission_rate == 0:
            add("emission_rate", "is 0 (AERMOD W320)", "warning")

        if src.release_height < 0:
            add("release_height", f"must be >= 0, got {src.release_height} (AERMOD E209)")
        elif src.release_height > 200.0:
            add("release_height",
                f"{src.release_height} m is above 200 m (AERMOD W320)", "warning")

        for field_name, value in (("x_dimension", src.x_dimension),
                                  ("y_dimension", src.y_dimension)):
            if value < 0:
                add(field_name, f"must be >= 0, got {value} (AERMOD E209)")
            elif value < cls.OPENPIT_MIN_DIMENSION:
                add(field_name,
                    f"{value} m is below 1e-5 m, so AERMOD uses 1e-5 m "
                    "instead (AERMOD W320)", "warning")
            elif value > 2000.0:
                add(field_name, f"{value} m is above 2000 m (AERMOD W320)", "warning")

        if abs(src.angle) > 180.0:
            add("angle", f"|{src.angle}| is above 180 degrees (AERMOD W320)", "warning")

        if src.pit_volume <= 0:
            add("pit_volume", f"must be > 0, got {src.pit_volume} (AERMOD E209)")

        if src.x_dimension < 0 or src.y_dimension < 0:
            return
        x_dim, y_dim = cls._openpit_dimensions(src)
        ratio = max(x_dim / y_dim, y_dim / x_dim)
        if ratio > 10:
            add("x_dimension/y_dimension",
                f"aspect ratio > 10 ({ratio:.1f}) (AERMOD W392)", "warning")

        if src.pit_volume > 0:
            eff_depth = src.pit_volume / (x_dim * y_dim)
            if src.release_height > eff_depth:
                add("release_height",
                    f"{src.release_height} m exceeds the effective pit depth "
                    f"volume / (x_dimension * y_dimension) = {eff_depth:.2f} m, "
                    "which AERMOD refuses (AERMOD E322)")

    @classmethod
    def _openpit_vertices(cls, src):
        """The pit's corners as soset.f OPARM places them (lines 3604-3623):
        from the SW corner along the rotated Y side, then the X side."""
        x_dim, y_dim = cls._openpit_dimensions(src)
        rad = math.radians(src.angle)
        sin_a, cos_a = math.sin(rad), math.cos(rad)
        x1, y1 = src.x_coord, src.y_coord
        x2, y2 = x1 + y_dim * sin_a, y1 + y_dim * cos_a
        x3, y3 = x2 + x_dim * cos_a, y2 - x_dim * sin_a
        x4, y4 = x3 - y_dim * sin_a, y3 - y_dim * cos_a
        return [(x1, y1), (x2, y2), (x3, y3), (x4, y4)]

    @staticmethod
    def _strictly_inside(px, py, vertices) -> bool:
        """True when (px, py) is inside the convex polygon and not on its
        boundary, as PNPOLY's INOUT > 0 (aermod.f 3898)."""
        sign = 0
        n = len(vertices)
        for i in range(n):
            xi, yi = vertices[i]
            xj, yj = vertices[(i + 1) % n]
            cross = (xj - xi) * (py - yi) - (yj - yi) * (px - xi)
            if cross == 0:
                return False
            s = 1 if cross > 0 else -1
            if sign == 0:
                sign = s
            elif s != sign:
                return False
        return True

    @classmethod
    def _receptors_in_box(cls, receptors, sources, box):
        """Yield every receptor (x, y) that falls in the (xmin, ymin, xmax,
        ymax) box. Cartesian grid axes are filtered before they are
        crossed, so a large grid far from the pit costs one pass per axis."""
        from .validator_advanced import _cart_values, _polar_directions, _polar_distances

        xmin, ymin, xmax, ymax = box
        for grid in receptors.cartesian_grids:
            xs = [x for x in _cart_values(grid, "x") if xmin <= x <= xmax]
            if not xs:
                continue
            ys = [y for y in _cart_values(grid, "y") if ymin <= y <= ymax]
            for x in xs:
                for y in ys:
                    yield x, y
        by_id = {s.source_id: s for s in sources.sources}
        for grid in receptors.polar_grids:
            x0, y0 = grid.x_origin, grid.y_origin
            origin_id = getattr(grid, "origin_source_id", None)
            if origin_id:
                # GRIDPOLR ORIG srcid centres the grid on the source's
                # LOCATION, for OPENPIT its SW corner (reset.f 1147-1148).
                if origin_id not in by_id:
                    continue
                x0, y0 = by_id[origin_id].x_coord, by_id[origin_id].y_coord
            distances = _polar_distances(grid)
            for direction in _polar_directions(grid):
                rad = math.radians(direction)  # reset.f 1485-1486
                for dist in distances:
                    x, y = x0 + dist * math.sin(rad), y0 + dist * math.cos(rad)
                    if xmin <= x <= xmax and ymin <= y <= ymax:
                        yield x, y
        for rec in receptors.discrete_receptors:
            if xmin <= rec.x_coord <= xmax and ymin <= rec.y_coord <= ymax:
                yield rec.x_coord, rec.y_coord

    @classmethod
    def _validate_openpit_receptors(cls, sources, receptors, result: ValidationResult):
        """Warn about receptors inside an open pit.

        calc1.f PITCALC (v26135, lines 4859-4892) tests every receptor
        with PNPOLY against the pit's corners and skips one that lies
        strictly inside, leaving 0 for that source there. AERMOD raises no
        message code for it; inpsum.f CHKREC (lines 3994-4007) only lists
        the receptor, marked OPENPIT, in the input summary's "calculations
        may not be performed" table. A receptor on the pit's edge is
        modelled.
        """
        from pyaermod.input_generator import OpenPitSource

        for src in sources.sources:
            if not isinstance(src, OpenPitSource):
                continue
            if src.x_dimension < 0 or src.y_dimension < 0:
                continue
            vertices = cls._openpit_vertices(src)
            box = (min(v[0] for v in vertices), min(v[1] for v in vertices),
                   max(v[0] for v in vertices), max(v[1] for v in vertices))
            inside = [p for p in cls._receptors_in_box(receptors, sources, box)
                      if cls._strictly_inside(p[0], p[1], vertices)]
            if inside:
                shown = ", ".join(f"({x:.1f}, {y:.1f})" for x, y in inside[:3])
                more = f" and {len(inside) - 3} more" if len(inside) > 3 else ""
                result.errors.append(ValidationError(
                    f"OpenPitSource({src.source_id})", "receptors",
                    f"{len(inside)} receptor(s) lie inside the pit: {shown}{more}; "
                    "AERMOD skips them for this source and reports 0 there "
                    "(calc1.f PITCALC)",
                    severity="warning",
                ))

    # ------------------------------------------------------------------
    # Source groups
    # ------------------------------------------------------------------

    #: The only PSDGROUP IDs soset.f PSDGRP accepts (E287 otherwise).
    PSD_GROUP_IDS = ("INCRCONS", "RETRBASE", "NONRBASE")

    @staticmethod
    def _is_flat_terrain(control) -> bool:
        terrain = getattr(control.terrain_type, "value", control.terrain_type)
        return str(terrain).upper() == "FLAT"

    @classmethod
    def _validate_psd_groups(cls, sources, control, result: ValidationResult):
        """PSDGROUP needs PSDCREDIT (E146), which in turn forbids SRCGROUP
        (E105) and accepts only three group IDs (E287)."""
        psd_credit = getattr(control, "psd_credit", False)
        groups = getattr(sources, "psd_groups", [])
        if groups and not psd_credit:
            result.errors.append(ValidationError(
                "SourcePathway", "psd_groups",
                "PSDGROUP needs ControlPathway.psd_credit=True (AERMOD E146)"
            ))
        if psd_credit and sources.group_definitions:
            result.errors.append(ValidationError(
                "SourcePathway", "group_definitions",
                "SRCGROUP is not allowed with the PSDCREDIT option (AERMOD "
                "E105); use psd_groups (INCRCONS / RETRBASE / NONRBASE)"
            ))
        if psd_credit and not groups:
            result.errors.append(ValidationError(
                "SourcePathway", "psd_groups",
                "the PSDCREDIT option needs at least one PSDGROUP"
            ))
        for group in groups:
            if group.group_name.upper() not in cls.PSD_GROUP_IDS:
                result.errors.append(ValidationError(
                    "SourcePathway", "psd_groups",
                    f"PSDGROUP ID must be one of {cls.PSD_GROUP_IDS} "
                    f"(AERMOD E287), got '{group.group_name}'"
                ))
            if not group.member_source_ids:
                result.errors.append(ValidationError(
                    "SourcePathway", "psd_groups",
                    f"PSDGROUP {group.group_name} lists no sources (ALL is not "
                    "valid for PSDGROUP; AERMOD E201)"
                ))

    @classmethod
    def _validate_unit_conversions(cls, sources, control, result: ValidationResult):
        """EMISUNIT conflicts with CONCUNIT/DEPOUNIT (E159) and needs a
        single output type (E158); every factor must be positive."""
        emis = getattr(sources, "emission_units", None)
        conc = getattr(sources, "concentration_units", None)
        depo = getattr(sources, "deposition_units", None)
        for field_name, units in (("emission_units", emis),
                                  ("concentration_units", conc),
                                  ("deposition_units", depo)):
            if units is not None and units.factor <= 0:
                result.errors.append(ValidationError(
                    "SourcePathway", f"{field_name}.factor",
                    f"must be > 0, got {units.factor}"
                ))
        if emis is not None and (conc is not None or depo is not None):
            result.errors.append(ValidationError(
                "SourcePathway", "emission_units",
                "EMISUNIT cannot be combined with CONCUNIT or DEPOUNIT (AERMOD E159)"
            ))
        n_types = sum(bool(getattr(control, attr, False)) for attr in (
            "calculate_concentration", "calculate_deposition",
            "calculate_dry_deposition", "calculate_wet_deposition"))
        if emis is not None and n_types > 1:
            result.errors.append(ValidationError(
                "SourcePathway", "emission_units",
                "EMISUNIT applies to a run with one output type; with CONC and "
                "deposition together use concentration_units and "
                "deposition_units (AERMOD E158)"
            ))

    @classmethod
    def _validate_solid_barriers(cls, sources, control, result: ValidationResult):
        barriers = getattr(sources, "solid_barriers", [])
        if not barriers:
            return
        cls._require_alpha_and_flat("SourcePathway", "solid_barriers", "SBARRIER",
                                    control, result)
        for barrier in barriers:
            name = f"SolidBarrier({barrier.barrier_id})"
            if not 1 <= len(barrier.segments) <= 50:
                result.errors.append(ValidationError(
                    name, "segments",
                    f"must have 1-50 segments (AERMOD E320), got {len(barrier.segments)}"
                ))
            for i, seg in enumerate(barrier.segments, start=1):
                if not 2.0 < seg.height <= 12.0:
                    result.errors.append(ValidationError(
                        name, f"segments[{i}].height",
                        f"must be > 2 and <= 12 m (AERMOD E320), got {seg.height}"
                    ))

    @classmethod
    def _require_alpha_and_flat(cls, pathway, field_name, keyword, control,
                                result: ValidationResult):
        if not getattr(control, "alpha", False):
            result.errors.append(ValidationError(
                pathway, field_name,
                f"{keyword} needs ControlPathway.alpha=True: AERMOD requires "
                "the non-DFAULT ALPHA option (E198)"
            ))
        if not cls._is_flat_terrain(control):
            result.errors.append(ValidationError(
                pathway, field_name,
                f"{keyword} needs terrain_type=FLAT: AERMOD rejects RLINE "
                "barriers and depressions in ELEV runs (E713)"
            ))

    @classmethod
    def _validate_rline_configuration(cls, src, control, result: ValidationResult):
        """RBARRIER / RDEPRESS / VBARRIER gates and ranges from soset.f."""
        name = f"RLineExtSource({src.source_id})"
        has_barrier = src.barrier_height_1 is not None and src.barrier_dcl_1 is not None
        has_depress = (src.depression_depth is not None
                       and src.depression_wtop is not None
                       and src.depression_wbottom is not None)
        veg = list(getattr(src, "vegetative_barriers", []) or [])
        if has_barrier:
            cls._require_alpha_and_flat(name, "barrier_height_1", "RBARRIER", control, result)
        if has_depress:
            cls._require_alpha_and_flat(name, "depression_depth", "RDEPRESS", control, result)
        if veg:
            cls._require_alpha_and_flat(name, "vegetative_barriers", "VBARRIER", control, result)
            if len(veg) > 2:
                result.errors.append(ValidationError(
                    name, "vegetative_barriers",
                    f"VBARRIER takes at most two barriers, got {len(veg)}"
                ))
            for i, b in enumerate(veg[:2], start=1):
                for attr, lo, hi, code in (("height", 2.0, 10.0, "E371"),
                                           ("width", 2.5, 13.0, "E372"),
                                           ("leaf_area_index", 4.0, 10.92, "E373"),
                                           ("mixing_length", 0.55, 3.75, "E374")):
                    value = getattr(b, attr)
                    if not lo <= value <= hi:
                        result.errors.append(ValidationError(
                            name, f"vegetative_barriers[{i}].{attr}",
                            f"must be within {lo}-{hi} (AERMOD {code}), got {value}"
                        ))

    @classmethod
    def _validate_source_groups(cls, sources, result: ValidationResult,
                                *, unparsed_lines=()):
        """Validate centralized source group definitions.

        Members as soset.f SRCGRP (v24142, 5905-5960) reads them:
        BACKGROUND/BACKGRND names the background concentration (E323
        when the project has none), a field with ``-`` is a range of
        source IDs (E203 when its upper end is below its lower), and any
        other field must be a defined source ID (E224). Sources from an
        SO INCLUDED file are invisible here, so an unknown member is then
        only a warning.
        """
        from pyaermod.input_generator import BuoyLineSource
        from pyaermod.input_reader import _id_parts

        all_source_ids = set()
        for source in sources.sources:
            if isinstance(source, BuoyLineSource):
                for seg in source.line_segments:
                    all_source_ids.add(str(seg.source_id).upper())
            else:
                all_source_ids.add(str(source.source_id).upper())
        has_background = cls._has_background(sources, unparsed_lines)
        included = bool(_kept_lines(unparsed_lines, "SO", ("INCLUDED",)))

        seen_names = set()
        for group in sources.group_definitions:
            # Group name length
            if len(group.group_name) > 8:
                result.errors.append(ValidationError(
                    "SourceGroupDefinition", "group_name",
                    f"'{group.group_name}' exceeds 8 characters (AERMOD limit)"
                ))

            # Duplicate group names
            if group.group_name in seen_names:
                result.errors.append(ValidationError(
                    "SourceGroupDefinition", "group_name",
                    f"duplicate group name '{group.group_name}'"
                ))
            seen_names.add(group.group_name)

            # Member IDs reference existing sources
            where = f"SourceGroupDefinition({group.group_name})"
            for member_id in group.member_source_ids:
                member = str(member_id).upper()
                if member in cls.RESERVED_SOURCE_IDS:
                    if not has_background:
                        result.errors.append(ValidationError(
                            where, "member_source_ids",
                            f"'{member_id}' adds the background concentration to the "
                            "group, but the project has none (AERMOD E323)"
                        ))
                    continue
                if "-" in member:
                    low, _, high = member.partition("-")
                    lo, hi = _id_parts(low), _id_parts(high)
                    if hi[0] < lo[0] or hi[1] < lo[1] or hi[2] < lo[2]:
                        result.errors.append(ValidationError(
                            where, "member_source_ids",
                            f"source ID range '{member_id}' ends below its start "
                            "(AERMOD E203 SRCRANGE)"
                        ))
                    continue
                if member not in all_source_ids:
                    result.errors.append(ValidationError(
                        where, "member_source_ids",
                        f"source ID '{member_id}' not found in project sources"
                        + (" (it may be defined in the SO INCLUDED file)" if included
                           else " (AERMOD E224)"),
                        severity="warning" if included else "error",
                    ))

    @staticmethod
    def _has_background(sources, unparsed_lines) -> bool:
        """Background concentrations: modelled, or SO BACKGRND lines kept
        verbatim (AERMOD's L_BACKGRND)."""
        return (getattr(sources, "background", None) is not None
                or bool(_kept_lines(unparsed_lines, "SO", ("BACKGRND",))))

    @classmethod
    def _validate_background_in_groups(cls, sources, unparsed_lines,
                                       result: ValidationResult):
        """Background concentrations that no source group includes.

        AERMOD adds BACKGRND values only to the groups that name
        BACKGROUND (soset.f SRCGRP 5866-5867: "BACKGRND is NOT
        automatically included in source group ALL"), so with none the
        background is read and left out of every result.
        """
        if not cls._has_background(sources, unparsed_lines):
            return
        named = [m for g in getattr(sources, "group_definitions", None) or []
                 for m in g.member_source_ids]
        named += [f for ln in _kept_lines(unparsed_lines, "SO", ("SRCGROUP",))
                  for f in ln.fields[1:]]
        if any(str(m).upper() in cls.RESERVED_SOURCE_IDS for m in named):
            return
        result.errors.append(ValidationError(
            "SourcePathway", "background",
            "the project has background concentrations, but no source group "
            "includes them: AERMOD adds BACKGRND only to groups that name BACKGROUND "
            "(it is not part of ALL unless the ALL card says so), so every result "
            "leaves the background out. Add 'BACKGROUND' to a group's "
            "member_source_ids, e.g. SourceGroupDefinition('ALL', ['BACKGROUND'])",
            severity="warning",
        ))

    # ------------------------------------------------------------------
    # Chemistry options
    # ------------------------------------------------------------------

    @classmethod
    def _validate_restart_options(cls, control, result: ValidationResult):
        """CO SAVEFILE / INITFILE / MULTYEAR: AERMOD's own exclusions.

        ``coset.f`` refuses MULTYEAR alongside either restart keyword
        (E150 in MYEAR, SAVEFL and INITFL) and accepts MULTYEAR only for
        the pollutants it can chain (PM10, PM2.5, NO2, SO2, LEAD, OTHER).
        """
        pathway = "ControlPathway"
        my = getattr(control, "multiyear", None)
        if my is None:
            return
        for attr in ("save_file", "init_file"):
            if getattr(control, attr, None) is not None:
                result.errors.append(ValidationError(
                    pathway, attr,
                    f"{attr} cannot be combined with multiyear: AERMOD "
                    "rejects SAVEFILE/INITFILE together with MULTYEAR (E150)"
                ))
        pollutant = control.pollutant_id
        name = pollutant.value if hasattr(pollutant, "value") else str(pollutant)
        allowed = {"PM10", "PM-10", "NO2", "SO2", "LEAD", "OTHER",
                   "PM25", "PM-2.5", "PM-25", "PM2.5"}
        if name.upper() not in allowed:
            result.errors.append(ValidationError(
                pathway, "multiyear",
                f"AERMOD accepts MULTYEAR only for {sorted(allowed)}, "
                f"not POLLUTID {name} (E150)"
            ))
        if not my.save_file:
            result.errors.append(ValidationError(
                pathway, "multiyear.save_file", "must not be empty"
            ))

    @classmethod
    def _validate_gas_deposition_defaults(cls, control, result: ValidationResult):
        """CO GASDEPDF / GASDEPVD / GDSEASON / GDLANUSE.

        All four need the ALPHA option (E198); GASDEPVD excludes GDSEASON
        and GDLANUSE (E195); GDSEASON is 12 categories in 1..5 and
        GDLANUSE 36 categories in 1..9 (``coset.f`` GDSEAS / GDLAND).
        """
        pathway = "ControlPathway"
        fields = {
            "gas_deposition_defaults": control.gas_deposition_defaults,
            "gas_deposition_velocity": control.gas_deposition_velocity,
            "gas_deposition_seasons": control.gas_deposition_seasons,
            "gas_deposition_land_use": control.gas_deposition_land_use,
        }
        present = [name for name, value in fields.items() if value is not None]
        if not present:
            return
        if not getattr(control, "alpha", False):
            result.errors.append(ValidationError(
                pathway, present[0],
                "gas deposition defaults need ControlPathway.alpha=True: "
                "AERMOD requires the non-DFAULT ALPHA option for "
                f"{', '.join(present)} (E198)"
            ))
        if control.gas_deposition_velocity is not None:
            for name in ("gas_deposition_seasons", "gas_deposition_land_use"):
                if fields[name] is not None:
                    result.errors.append(ValidationError(
                        pathway, name,
                        "cannot be combined with gas_deposition_velocity: "
                        "AERMOD rejects GDSEASON/GDLANUSE with GASDEPVD (E195)"
                    ))
            if control.gas_deposition_velocity <= 0:
                result.errors.append(ValidationError(
                    pathway, "gas_deposition_velocity",
                    f"must be > 0 m/s, got {control.gas_deposition_velocity}"
                ))
        for name, count, hi in (("gas_deposition_seasons", 12, 5),
                                ("gas_deposition_land_use", 36, 9)):
            values = fields[name]
            if values is None:
                continue
            if len(values) != count:
                result.errors.append(ValidationError(
                    pathway, name, f"needs exactly {count} values, got {len(values)}"
                ))
            bad = [v for v in values if not 1 <= int(v) <= hi]
            if bad:
                result.errors.append(ValidationError(
                    pathway, name, f"categories must be 1..{hi}, got {bad[:4]}"
                ))

    @classmethod
    def _validate_background_spec(cls, label, spec, pathway, result,
                                  *, n_sectors: int, sector=None):
        """Checks shared by the ozone and NOx background specifications."""
        where = f"{label}.by_sector[{sector}]" if sector is not None else label
        if sector is not None and not n_sectors:
            result.errors.append(ValidationError(
                pathway, where,
                "sector form used without sectors: AERMOD rejects SECTn "
                "without O3SECTOR/NOXSECTR (E171)"
            ))
        elif sector is not None and not 1 <= sector <= n_sectors:
            result.errors.append(ValidationError(
                pathway, where,
                f"sector {sector} is not one of the {n_sectors} sectors declared"
            ))
        if spec.value is not None and spec.varying is not None:
            result.errors.append(ValidationError(
                pathway, where,
                "a constant value and a temporal profile cannot both be given "
                "(AERMOD E605 for NOXVALUE + NOX_VALS)"
            ))
        for units in (spec.value_units, spec.file_units):
            if units is not None and units.upper() not in BACKGROUND_UNITS:
                result.errors.append(ValidationError(
                    pathway, where,
                    f"units must be one of {BACKGROUND_UNITS}, got {units!r}"
                ))
        if spec.varying is not None:
            for message in cls._check_temporal_values(spec.varying.flag,
                                                      spec.varying.values):
                result.errors.append(ValidationError(pathway, where, message))

    @classmethod
    def _validate_sectors(cls, label, sectors, pathway, result):
        """BGSECTOR / O3SECTOR / NOXSECTR: 2..6 ascending directions,
        >= 30 deg apart. A direction that is no finite number (a string
        from a hand-edited project file, NaN, inf) is an error of its own,
        and the range and order checks, which need numbers, are skipped."""
        if not sectors:
            return
        if not 2 <= len(sectors) <= 6:
            result.errors.append(ValidationError(
                pathway, label, f"needs 2 to 6 sector start directions, got {len(sectors)}"
            ))
        bad = [d for d in sectors if not _is_finite_number(d)]
        if bad:
            result.errors.append(ValidationError(
                pathway, label,
                "sector start directions must be finite numbers (degrees), got "
                f"{', '.join(repr(d) for d in bad[:4])}"
            ))
            return
        if any(not 0 <= d <= 360 for d in sectors):
            result.errors.append(ValidationError(
                pathway, label, "sector start directions must be within 0..360 degrees"
            ))
        widths = [b - a for a, b in itertools.pairwise(sectors)]
        if len(sectors) >= 2:
            widths.append(sectors[0] + 360.0 - sectors[-1])
        if any(w < 30 for w in widths):
            result.errors.append(ValidationError(
                pathway, label,
                "sectors must be in ascending order and at least 30 degrees "
                "wide (AERMOD E222/E227)"
            ))

    @classmethod
    def _validate_chemistry(cls, chemistry, control, result: ValidationResult):
        """Validate NO2 chemistry options."""
        from pyaermod.input_generator import ChemistryMethod

        pathway = "ChemistryOptions"

        # Pollutant must be NO2
        pollutant = (
            control.pollutant_id.value
            if hasattr(control.pollutant_id, "value")
            else control.pollutant_id
        )
        if pollutant != "NO2":
            result.errors.append(ValidationError(
                pathway, "pollutant_id",
                f"chemistry options require pollutant_id=NO2, got '{pollutant}'"
            ))

        # Default NO2 ratio in [0, 1]. None means the deck has no NO2STACK
        # card (each source then needs its own NO2RATIO).
        if chemistry.default_no2_ratio is not None and not (0 <= chemistry.default_no2_ratio <= 1):
            result.errors.append(ValidationError(
                pathway, "default_no2_ratio",
                f"must be between 0 and 1, got {chemistry.default_no2_ratio}"
            ))

        # coset.f 554-570: OLM, PVMRM, GRSM, TTRM and TTRM2 need an
        # OZONEVAL, OZONEFIL or O3VALUES card (E283). An OzoneData with
        # nothing set writes none.
        oz = chemistry.ozone_data
        writes_ozone = oz is not None and (
            not oz.spec().is_empty()
            or any(not spec.is_empty() for spec in oz.by_sector.values())
            or bool(oz.sector_values))
        if chemistry.method.value in NO2STACK_METHODS and not writes_ozone:
            result.errors.append(ValidationError(
                pathway, "ozone_data",
                f"ozone data required for {chemistry.method.value} method: AERMOD "
                "needs OZONEVAL, OZONEFIL or O3VALUES (E283); set "
                "ozone_data.uniform_value, ozone_file or varying"
            ))

        # coset.f MODOPT 1810-1824: TTRM and TTRM2 need ALPHA (E198)
        if (chemistry.method in (ChemistryMethod.TTRM, ChemistryMethod.TTRM2)
                and not getattr(control, "alpha", False)):
            result.errors.append(ValidationError(
                pathway, "method",
                f"{chemistry.method.value} needs the ALPHA option "
                "(ControlPathway.alpha=True; AERMOD E198)"
            ))

        # The ozone keywords (OZONEVAL, OZONEFIL, O3VALUES, ...) are read
        # only under OLM, PVMRM, GRSM or TTRM; with ARM2 coset.f stops
        # with E600.
        if (chemistry.ozone_data is not None
                and chemistry.method.value not in NO2STACK_METHODS):
            result.errors.append(ValidationError(
                pathway, "ozone_data",
                f"{chemistry.method.value} takes no ozone data; AERMOD reads "
                "OZONEVAL/OZONEFIL/O3VALUES only with OLM, PVMRM, GRSM or TTRM "
                "and stops with E600 (set ozone_data=None)"
            ))

        # Validate ozone data values
        if chemistry.ozone_data is not None:
            oz = chemistry.ozone_data
            if oz.uniform_value is not None and oz.uniform_value < 0:
                result.errors.append(ValidationError(
                    pathway, "ozone_data.uniform_value",
                    f"must be >= 0, got {oz.uniform_value}"
                ))
            if oz.sector_values:
                for sector_id, value in oz.sector_values.items():
                    if value < 0:
                        result.errors.append(ValidationError(
                            pathway, "ozone_data.sector_values",
                            f"sector {sector_id} value must be >= 0, got {value}"
                        ))

        # Ozone sector forms and units
        if chemistry.ozone_data is not None:
            oz = chemistry.ozone_data
            cls._validate_sectors("ozone_data.sectors", oz.sectors, pathway, result)
            cls._validate_background_spec(
                "ozone_data", oz.spec(), pathway, result, n_sectors=len(oz.sectors))
            for sector, spec in sorted(oz.by_sector.items()):
                cls._validate_background_spec(
                    "ozone_data", spec, pathway, result,
                    n_sectors=len(oz.sectors), sector=sector)
            if oz.sector_values and not oz.sectors:
                result.errors.append(ValidationError(
                    pathway, "ozone_data.sector_values",
                    "sector values need ozone_data.sectors (O3SECTOR); AERMOD "
                    "rejects SECTn without it (E171)"
                ))
            if oz.units is not None and oz.units.upper() not in BACKGROUND_UNITS:
                result.errors.append(ValidationError(
                    pathway, "ozone_data.units",
                    f"must be one of {BACKGROUND_UNITS}, got {oz.units!r}"
                ))

        # NOx background: GRSM needs one, and only GRSM accepts one
        nox = chemistry.effective_nox_background()
        if chemistry.method == ChemistryMethod.GRSM and (nox is None or nox.is_empty()):
            result.errors.append(ValidationError(
                pathway, "nox_background",
                "NOx background (NOXVALUE, NOX_FILE or NOX_VALS) required "
                "for GRSM method",
                severity="warning",
            ))
        if nox is not None and chemistry.method != ChemistryMethod.GRSM:
            result.errors.append(ValidationError(
                pathway, "nox_background",
                f"AERMOD accepts the NOx background keywords only with GRSM, "
                f"not {chemistry.method.value} (E602)"
            ))
        if nox is not None:
            cls._validate_sectors("nox_background.sectors", nox.sectors, pathway, result)
            cls._validate_background_spec(
                "nox_background", nox, pathway, result, n_sectors=len(nox.sectors))
            for sector, spec in sorted(nox.by_sector.items()):
                cls._validate_background_spec(
                    "nox_background", spec, pathway, result,
                    n_sectors=len(nox.sectors), sector=sector)
            if nox.units is not None and nox.units.upper() not in BACKGROUND_UNITS:
                result.errors.append(ValidationError(
                    pathway, "nox_background.units",
                    f"must be one of {BACKGROUND_UNITS}, got {nox.units!r}"
                ))

        # OLM groups: OLMGROUP is only accepted with the OLM option (E144)
        if chemistry.olm_groups and chemistry.method != ChemistryMethod.OLM:
            result.errors.append(ValidationError(
                pathway, "olm_groups",
                f"OLMGROUP needs method=OLM (AERMOD E144), got {chemistry.method.value}"
            ))
        for olm_group in chemistry.olm_groups:
            if len(olm_group.group_name) > 8:
                result.errors.append(ValidationError(
                    f"OLMGroup({olm_group.group_name})", "group_name",
                    "exceeds 8 characters (AERMOD limit)"
                ))

    # ------------------------------------------------------------------
    # Receptor pathway
    # ------------------------------------------------------------------

    @classmethod
    def _validate_receptors(cls, receptors, result: ValidationResult,
                            *, unparsed_lines=()):
        pathway = "ReceptorPathway"

        total = (len(receptors.cartesian_grids)
                 + len(receptors.polar_grids)
                 + len(receptors.discrete_receptors))
        # aermod.f RECSIZ also counts receptors on RE lines the project
        # keeps verbatim (EVALCART, DISCPOLR, ...) and in an INCLUDED file.
        if total == 0 and not _kept_lines(unparsed_lines, "RE", _RECEPTOR_KEYWORDS):
            result.errors.append(ValidationError(
                pathway, "grids/receptors",
                "must have at least one receptor grid or discrete receptor"
            ))

        if receptors.elevation_units not in VALID_ELEVATION_UNITS:
            result.errors.append(ValidationError(
                pathway, "elevation_units",
                f"must be 'METERS' or 'FEET', got '{receptors.elevation_units}'"
            ))

        for grid in receptors.cartesian_grids:
            cls._validate_cartesian_grid(grid, result)

        for grid in receptors.polar_grids:
            cls._validate_polar_grid(grid, result)

    @classmethod
    def _validate_cartesian_grid(cls, grid, result: ValidationResult):
        name = f"CartesianGrid({grid.grid_name})"

        # Explicit XPNTS/YPNTS lists replace the generator on that axis.
        x_points = getattr(grid, "x_points", None)
        y_points = getattr(grid, "y_points", None)
        if x_points is not None and not x_points:
            result.errors.append(ValidationError(
                name, "x_points", "explicit XPNTS list must not be empty"
            ))
        if y_points is not None and not y_points:
            result.errors.append(ValidationError(
                name, "y_points", "explicit YPNTS list must not be empty"
            ))
        if x_points is not None and y_points is not None:
            return

        if x_points is None and grid.x_num <= 0:
            result.errors.append(ValidationError(
                name, "x_num", f"must be > 0, got {grid.x_num}"
            ))
        if y_points is None and grid.y_num <= 0:
            result.errors.append(ValidationError(
                name, "y_num", f"must be > 0, got {grid.y_num}"
            ))
        if x_points is None and grid.x_delta <= 0:
            result.errors.append(ValidationError(
                name, "x_delta", f"must be > 0, got {grid.x_delta}"
            ))
        if y_points is None and grid.y_delta <= 0:
            result.errors.append(ValidationError(
                name, "y_delta", f"must be > 0, got {grid.y_delta}"
            ))

    @classmethod
    def _validate_polar_grid(cls, grid, result: ValidationResult):
        name = f"PolarGrid({grid.grid_name})"

        # An explicit DIST / DDIR list replaces the generator it stands for.
        distances = getattr(grid, "distances", None)
        directions = getattr(grid, "directions", None)
        if distances is not None:
            if not distances:
                result.errors.append(ValidationError(
                    name, "distances", "explicit DIST list must not be empty"
                ))
            elif min(distances) <= 0:
                result.errors.append(ValidationError(
                    name, "distances", "ring distances must be > 0"
                ))
        else:
            if grid.dist_num <= 0:
                result.errors.append(ValidationError(
                    name, "dist_num", f"must be > 0, got {grid.dist_num}"
                ))
            if grid.dist_delta <= 0:
                result.errors.append(ValidationError(
                    name, "dist_delta", f"must be > 0, got {grid.dist_delta}"
                ))
        if directions is not None:
            if not directions:
                result.errors.append(ValidationError(
                    name, "directions", "explicit DDIR list must not be empty"
                ))
        else:
            if grid.dir_num <= 0:
                result.errors.append(ValidationError(
                    name, "dir_num", f"must be > 0, got {grid.dir_num}"
                ))
            if grid.dir_delta <= 0:
                result.errors.append(ValidationError(
                    name, "dir_delta", f"must be > 0, got {grid.dir_delta}"
                ))

    # ------------------------------------------------------------------
    # Meteorology pathway
    # ------------------------------------------------------------------

    @classmethod
    def _validate_meteorology(cls, met, result: ValidationResult, check_files: bool,
                              control=None):
        pathway = "MeteorologyPathway"

        if not met.surface_file or not met.surface_file.strip():
            result.errors.append(ValidationError(
                pathway, "surface_file", "must not be empty"
            ))

        if not met.profile_file or not met.profile_file.strip():
            result.errors.append(ValidationError(
                pathway, "profile_file", "must not be empty"
            ))

        if check_files:
            if met.surface_file and not Path(unquote_path(met.surface_file)).exists():
                result.errors.append(ValidationError(
                    pathway, "surface_file",
                    f"file not found: '{met.surface_file}'"
                ))
            if met.profile_file and not Path(unquote_path(met.profile_file)).exists():
                result.errors.append(ValidationError(
                    pathway, "profile_file",
                    f"file not found: '{met.profile_file}'"
                ))

        # PROFBASE: written with one_decimal_or_exact, so NaN or an
        # infinity would be ``nan``/``inf``, which AERMOD's STODBL does not
        # read (E208), and text or None would not be written at all.
        base = met.profile_base_elevation
        if not _is_finite_number(base):
            result.errors.append(ValidationError(
                pathway, "profile_base_elevation",
                f"must be a finite number (metres above sea level), got {base!r}: "
                "PROFBASE would be written as AERMOD cannot read it (E208)"
            ))

        # Date range: if any date field is set, all must be set
        date_fields = [met.start_year, met.start_month, met.start_day,
                       met.end_year, met.end_month, met.end_day]
        set_count = sum(1 for f in date_fields if f is not None)
        if 0 < set_count < 6:
            result.errors.append(ValidationError(
                pathway, "start/end dates",
                f"partial date range: {set_count} of 6 date fields set; "
                "set all or none"
            ))

        cls._validate_met_options(met, result, control)

    @classmethod
    def _validate_met_options(cls, met, result: ValidationResult, control=None):
        """DAYRANGE, NUMYEARS, WINDCATS, SCIMBYHR and the turbulence keyword
        as meset.f DAYRNG / NUMYR / WSCATS / SCIMIT / TURBOPT check them."""
        pathway = "MeteorologyPathway"
        extra = {str(o).upper() for o in getattr(control, "extra_model_options", [])} if control else set()
        scim_option = "SCIM" in extra

        for token in getattr(met, "day_ranges", []) or []:
            if not dayrange_field_is_valid(str(token)):
                result.errors.append(ValidationError(
                    pathway, "day_ranges",
                    f"'{token}' is not a Julian day, a Julian range, a month/day or "
                    "a month/day range (E203/E208)"
                ))
        if getattr(met, "day_ranges", None) and scim_option:
            result.errors.append(ValidationError(
                pathway, "day_ranges", "DAYRANGE cannot be used with the SCIM option (E154)"
            ))

        num_years = getattr(met, "num_years", None)
        if num_years is not None and (int(num_years) != num_years or int(num_years) < 1):
            result.errors.append(ValidationError(
                pathway, "num_years", f"must be a positive integer, got {num_years!r} (E208)"
            ))

        cats = getattr(met, "wind_speed_categories", None)
        if cats is not None:
            if len(cats) != WIND_CATEGORY_COUNT:
                result.errors.append(ValidationError(
                    pathway, "wind_speed_categories",
                    f"WINDCATS takes exactly {WIND_CATEGORY_COUNT} upper bounds, got {len(cats)} (E200)"
                ))
            if any(not 1.0 <= float(c) <= 20.0 for c in cats):
                result.errors.append(ValidationError(
                    pathway, "wind_speed_categories", "each bound must be in 1-20 m/s (E380)"
                ))
            if any(float(b) <= float(a) for a, b in itertools.pairwise(cats)):
                result.errors.append(ValidationError(
                    pathway, "wind_speed_categories", "bounds must increase (E203)"
                ))

        scim = getattr(met, "scim", None)
        if scim is not None:
            if not scim_option:
                result.errors.append(ValidationError(
                    pathway, "scim",
                    "SCIMBYHR is read only with MODELOPT SCIM "
                    "(ControlPathway.extra_model_options)"
                ))
            if not 1 <= int(scim.start_hour) <= 24:
                result.errors.append(ValidationError(
                    pathway, "scim.start_hour", f"must be 1-24, got {scim.start_hour} (E380)"
                ))
            if int(scim.interval) < 1:
                result.errors.append(ValidationError(
                    pathway, "scim.interval", f"must be at least 1, got {scim.interval} (E380)"
                ))

        turb = getattr(met, "turbulence_option", None)
        if turb is not None and str(turb).upper() not in TURBULENCE_OPTIONS:
            result.errors.append(ValidationError(
                pathway, "turbulence_option",
                f"'{turb}' is not one of {TURBULENCE_OPTIONS}"
            ))

    # ------------------------------------------------------------------
    # Output pathway
    # ------------------------------------------------------------------

    @staticmethod
    def naaqs_processing(control) -> Optional[str]:
        """Which NAAQS special processing AERMOD would run for ``control``.

        Returns ``"1-hour"`` for NO2/SO2 with 1-hour as the only short-term
        average, ``"24-hour"`` for PM2.5 with 24-hour as the only
        short-term average and no PERIOD, else ``None``. This is the
        condition under which AERMOD accepts MAXDAILY, MXDYBYYR and
        MAXDCONT (``coset.f`` sets NO2AVE/SO2AVE/PM25AVE; ``ouset.f``
        raises E162/E163 otherwise).
        """
        pollutant = control.pollutant_id
        name = (pollutant.value if hasattr(pollutant, "value") else str(pollutant)).upper()
        periods = [str(p).upper() for p in control.averaging_periods]
        short = {p for p in periods if p not in ("PERIOD", "ANNUAL", "MONTH")}
        if name in ("NO2", "SO2") and short == {"1"}:
            return "1-hour"
        if name in ("PM25", "PM-2.5", "PM-25", "PM2.5") and short == {"24"} \
                and "PERIOD" not in periods:
            return "24-hour"
        return None

    @classmethod
    def _validate_design_value_outputs(cls, output, control, result):
        """OU MAXDAILY / MXDYBYYR / MAXDCONT / FILEFORM against ouset.f."""
        pathway = "OutputPathway"
        if output.file_format is not None and output.file_format.upper()[:3] not in ("FIX", "EXP"):
            result.errors.append(ValidationError(
                pathway, "file_format",
                f"FILEFORM must be FIX or EXP, got {output.file_format!r} (E203)"
            ))
        requested = (output.max_daily_files or output.max_daily_by_year_files
                     or output.max_daily_contributions)
        if not requested:
            return
        if control is not None and cls.naaqs_processing(control) is None:
            result.errors.append(ValidationError(
                pathway, "max_daily_files",
                "MAXDAILY/MXDYBYYR/MAXDCONT apply only to the 1-hour NO2/SO2 "
                "and 24-hour PM2.5 NAAQS processing: POLLUTID NO2 or SO2 with "
                "1 as the only short-term average, or PM25 with 24 (E162/E163)"
            ))
        if not output.max_daily_contributions:
            return
        for attr in ("multiyear", "save_file", "init_file"):
            if control is not None and getattr(control, attr, None) is not None:
                result.errors.append(ValidationError(
                    pathway, "max_daily_contributions",
                    f"MAXDCONT cannot be combined with ControlPathway.{attr} "
                    "(AERMOD E153)"
                ))
        n_ranks = output.receptor_table_rank if output.receptor_table else 0
        pollutant = control.pollutant_id if control is not None else ""
        name = (pollutant.value if hasattr(pollutant, "value") else str(pollutant)).upper()
        thresh_floor = 8 if name == "SO2" else 12
        for mdc in output.max_daily_contributions:
            where = f"max_daily_contributions[{mdc.source_group}]"
            if mdc.upper_rank > n_ranks:
                result.errors.append(ValidationError(
                    pathway, where,
                    f"upper_rank {mdc.upper_rank} exceeds the RECTABLE range "
                    f"({n_ranks}); raise receptor_table_rank (AERMOD E290)"
                ))
            if mdc.lower_rank is not None:
                if mdc.lower_rank > n_ranks:
                    result.errors.append(ValidationError(
                        pathway, where,
                        f"lower_rank {mdc.lower_rank} exceeds the RECTABLE range "
                        f"({n_ranks}) (AERMOD E290)"
                    ))
                if mdc.lower_rank < mdc.upper_rank:
                    result.errors.append(ValidationError(
                        pathway, where,
                        f"lower_rank {mdc.lower_rank} is above upper_rank "
                        f"{mdc.upper_rank} (AERMOD E272)"
                    ))
            elif n_ranks <= thresh_floor:
                result.errors.append(ValidationError(
                    pathway, where,
                    f"the THRESH form needs a RECTABLE range beyond rank "
                    f"{thresh_floor} for {name or 'this pollutant'}, got "
                    f"{n_ranks} (AERMOD E273)"
                ))

    @classmethod
    def _validate_output(cls, output, result: ValidationResult, control=None, sources=None):
        pathway = "OutputPathway"
        cls._validate_design_value_outputs(output, control, result)

        if output.receptor_table and output.receptor_table_rank <= 0:
            result.errors.append(ValidationError(
                pathway, "receptor_table_rank",
                f"must be > 0, got {output.receptor_table_rank}"
            ))

        if output.max_table and output.max_table_rank <= 0:
            result.errors.append(ValidationError(
                pathway, "max_table_rank",
                f"must be > 0, got {output.max_table_rank}"
            ))

        valid_output_types = {"CONC", "DEPOS", "DDEP", "WDEP", "DETH"}
        if hasattr(output, "output_type") and output.output_type not in valid_output_types:
            result.errors.append(ValidationError(
                pathway, "output_type",
                f"must be one of {valid_output_types}, got '{output.output_type}'"
            ))

        cls._validate_plot_file_ranks(output, result, control)
        cls._validate_output_files(output, result, control, sources)

    @classmethod
    def _validate_plot_file_ranks(cls, output, result: ValidationResult, control=None):
        """A short-term PLOTFILE asks for a high value RECTABLE prints.

        ouset.f OUPLOT takes the rank (FIRST, 2ND, ...) only if RECTABLE
        asked for it for that period (NHIAVE); without a RECTABLE, or past
        its range, AERMOD stops with E203 HIVALU. The period forms (PERIOD,
        ANNUAL) take no rank and need no RECTABLE.
        """
        from .pathways import _is_period_average, plot_file_group_fields, plot_rank_number

        pathway = "OutputPathway"
        entries = []
        if output.plot_file:
            entries.append(("plot_file_rank", output.plot_file_averaging,
                            output.plot_file_rank))
        for entry in output.plot_file_groups:
            try:
                avg, grp, _name, rank = plot_file_group_fields(entry)
            except ValueError as exc:
                result.errors.append(ValidationError(pathway, "plot_file_groups", str(exc)))
                continue
            entries.append((f"plot_file_groups[{grp}/{avg}]", avg, rank))
        periods = list(getattr(control, "averaging_periods", None) or [])
        for ave in output.period_plot_file_names(periods):
            entries.append(("plot_file_rank", ave, output.plot_file_rank))

        n_ranks = output.receptor_table_rank if output.receptor_table else 0
        reported = set()
        for where, avg, rank in entries:
            if _is_period_average(avg):
                continue
            try:
                number = plot_rank_number(rank)
            except ValueError as exc:
                key = (where, "invalid")
                if key not in reported:
                    reported.add(key)
                    result.errors.append(ValidationError(pathway, where, str(exc)))
                continue
            if not output.receptor_table:
                message = (f"a PLOTFILE for the {avg}-hour average needs RECTABLE "
                           "(receptor_table=True) to rank its high values; AERMOD "
                           "stops with E203 HIVALU")
            elif number > n_ranks:
                message = (f"the {avg}-hour PLOTFILE asks for rank {number}, past "
                           f"the RECTABLE range (1-{n_ranks}); raise "
                           "receptor_table_rank (AERMOD E203 HIVALU)")
            else:
                continue
            if (where, message) not in reported:
                reported.add((where, message))
                result.errors.append(ValidationError(pathway, where, message))

    @classmethod
    def _validate_output_files(cls, output, result: ValidationResult, control=None,
                               sources=None):
        """NOHEADER, RANKFILE, SEASONHR, EVALFILE and TOXXFILE as ouset.f
        NOHEADER / OURANK / OUSEAS / OUEVAL / OUTOXX and OUTQA check them."""
        if not (output.no_header or output.rank_files or output.season_hour_files
                or output.eval_files or output.toxx_files):
            return

        pathway = "OutputPathway"
        periods = {str(p).upper() for p in control.averaging_periods} if control else None
        in_use = {
            "MAXIFILE": bool(output.maxi_files),
            "POSTFILE": bool(output.postfile or (output.period_postfiles and periods)),
            "PLOTFILE": bool(output.plot_file or output.plot_file_groups
                             or (output.period_plot_files and periods)),
            "SEASONHR": bool(output.season_hour_files),
            "RANKFILE": bool(output.rank_files),
            "MAXDAILY": bool(output.max_daily_files),
            "MXDYBYYR": bool(output.max_daily_by_year_files),
            "MAXDCONT": bool(output.max_daily_contributions),
        }
        for token in output.no_header:
            name = str(token).upper()
            if name == "ALL":
                continue
            if name not in NOHEADER_FILE_TYPES:
                result.errors.append(ValidationError(
                    pathway, "no_header", f"'{token}' is not an output file type (E203)"
                ))
            elif not in_use[name]:
                result.errors.append(ValidationError(
                    pathway, "no_header",
                    f"NOHEADER names {name} but the pathway writes no {name} (E164)"
                ))

        seen_rank = set()
        for rf in output.rank_files:
            period = str(rf.averaging_period).upper()
            if periods is not None and period not in periods:
                result.errors.append(ValidationError(
                    pathway, "rank_files",
                    f"RANKFILE period {rf.averaging_period!r} is not on AVERTIME (E203)"
                ))
            if period in seen_rank:
                result.errors.append(ValidationError(
                    pathway, "rank_files", f"two RANKFILE cards for period {period} (E211)"
                ))
            seen_rank.add(period)
            if int(rf.rank) < 1:
                result.errors.append(ValidationError(
                    pathway, "rank_files", f"RANKFILE rank must be positive, got {rf.rank}"
                ))

        groups = None
        if sources is not None:
            groups = {"ALL"} | {g.group_name.upper() for g in sources.group_definitions}
            groups |= {g.group_name.upper() for g in getattr(sources, "psd_groups", [])}
        seen_groups = set()
        for sh in output.season_hour_files:
            gid = sh.source_group.upper()
            if groups is not None and gid not in groups:
                result.errors.append(ValidationError(
                    pathway, "season_hour_files",
                    f"SEASONHR group '{sh.source_group}' is not defined (E203)"
                ))
            if gid in seen_groups:
                result.errors.append(ValidationError(
                    pathway, "season_hour_files", f"two SEASONHR cards for group {gid} (E211)"
                ))
            seen_groups.add(gid)
        extra = {str(o).upper() for o in getattr(control, "extra_model_options", [])} if control else set()
        if output.season_hour_files and "SCIM" in extra:
            result.errors.append(ValidationError(
                pathway, "season_hour_files", "SEASONHR cannot be used with the SCIM option (E154)"
            ))

        if sources is not None:
            ids = set()
            for src in sources.sources:
                ids.add(src.source_id.upper())
                for seg in getattr(src, "line_segments", []) or []:
                    ids.add(seg.source_id.upper())
            for ef in output.eval_files:
                if ef.source_id.upper() not in ids:
                    result.errors.append(ValidationError(
                        pathway, "eval_files",
                        f"EVALFILE source '{ef.source_id}' is not defined (E203)"
                    ))

        seen_toxx = set()
        for tf in output.toxx_files:
            period = str(tf.averaging_period).upper()
            if periods is not None and period not in periods:
                result.errors.append(ValidationError(
                    pathway, "toxx_files",
                    f"TOXXFILE period {tf.averaging_period!r} is not on AVERTIME (E203)"
                ))
            if period in seen_toxx:
                result.errors.append(ValidationError(
                    pathway, "toxx_files", f"two TOXXFILE cards for period {period} (E211)"
                ))
            seen_toxx.add(period)
            if period != "1":
                result.errors.append(ValidationError(
                    pathway, "toxx_files",
                    f"TOXXFILE is meant for 1-hour averages; AERMOD warns for {period} (W296)",
                    severity="warning",
                ))

    # ------------------------------------------------------------------
    # CO research options (coset.f ARM2_Ratios, AWMA_DOWNWASH, ORD_DOWNWASH)
    # ------------------------------------------------------------------

    _AWMA_OPTIONS = ("STREAMLINE", "STREAMLINED", "AWMAUEFF", "AWMAUTURB",
                     "AWMAUTURBHX", "AWMAENTRAIN")
    _ORD_OPTIONS = ("ORDCAV", "ORDUEFF", "ORDTURB")

    @classmethod
    def _validate_downwash_and_arm2_options(cls, control, result: ValidationResult):
        pathway = "ControlPathway"
        alpha = bool(getattr(control, "alpha", False))
        dfault = bool(getattr(control, "regulatory_default", False))

        ratios = getattr(control, "arm2_ratios", None)
        if ratios is not None:
            chem = getattr(control, "chemistry", None)
            method = getattr(getattr(chem, "method", None), "value", None)
            if method != "ARM2":
                result.errors.append(ValidationError(
                    pathway, "arm2_ratios", "ARMRATIO needs the ARM2 option (E145)"
                ))
            lo, hi = float(ratios[0]), float(ratios[1])
            if not (0.0 < lo <= 1.0 and 0.0 < hi <= 1.0):
                result.errors.append(ValidationError(
                    pathway, "arm2_ratios", f"ratios must be in (0, 1], got {ratios} (E380)"
                ))
            elif hi < lo:
                result.errors.append(ValidationError(
                    pathway, "arm2_ratios", f"maximum ratio below minimum: {ratios} (E380)"
                ))
            elif dfault and not (0.5 <= lo <= 0.9 and 0.5 <= hi <= 0.9):
                result.errors.append(ValidationError(
                    pathway, "arm2_ratios",
                    f"under DFAULT the ARM2 ratios must lie in 0.5-0.9, got {ratios} (E380)"
                ))

        awma = [str(o).upper() for o in getattr(control, "awma_downwash", []) or []]
        ord_ = [str(o).upper() for o in getattr(control, "ord_downwash", []) or []]
        if awma:
            if not alpha:
                result.errors.append(ValidationError(
                    pathway, "awma_downwash", "AWMADWNW needs the ALPHA option (E122)"
                ))
            if len(awma) > 5:
                result.errors.append(ValidationError(
                    pathway, "awma_downwash", "AWMADWNW takes at most five options (E202)"
                ))
            for opt in awma:
                if opt not in cls._AWMA_OPTIONS:
                    result.errors.append(ValidationError(
                        pathway, "awma_downwash", f"'{opt}' is not an AWMADWNW option (E203)"
                    ))
            if len(set(awma)) != len(awma):
                result.errors.append(ValidationError(
                    pathway, "awma_downwash", "duplicate AWMADWNW option (E121)"
                ))
            if ({"STREAMLINE", "STREAMLINED"} & set(awma)
                    and not {"AWMAUTURB", "AWMAUTURBHX"} & set(awma)):
                result.errors.append(ValidationError(
                    pathway, "awma_downwash",
                    "STREAMLINE requires AWMAUTURB or AWMAUTURBHX (E126)"
                ))
        if ord_:
            if not alpha:
                result.errors.append(ValidationError(
                    pathway, "ord_downwash", "ORD_DWNW needs the ALPHA option (E123)"
                ))
            if len(ord_) > 3:
                result.errors.append(ValidationError(
                    pathway, "ord_downwash", "ORD_DWNW takes at most three options (E202)"
                ))
            for opt in ord_:
                if opt not in cls._ORD_OPTIONS:
                    result.errors.append(ValidationError(
                        pathway, "ord_downwash", f"'{opt}' is not an ORD_DWNW option (E203)"
                    ))
            if len(set(ord_)) != len(ord_):
                result.errors.append(ValidationError(
                    pathway, "ord_downwash", "duplicate ORD_DWNW option (E121)"
                ))
        if "AWMAUEFF" in awma and "ORDUEFF" in ord_:
            result.errors.append(ValidationError(
                pathway, "awma_downwash/ord_downwash",
                "AWMAUEFF and ORDUEFF conflict (E124)"
            ))

    # ------------------------------------------------------------------
    # Event pathway
    # ------------------------------------------------------------------

    @classmethod
    def _validate_events(cls, events, control, sources, output,
                         result: ValidationResult, event_run: bool = False):
        """The EV pathway as evset.f checks it (EVPER, EVLOC, OEVENT, EVCARD)."""
        pathway = "EventPathway"

        if not events.events:
            result.errors.append(ValidationError(
                pathway, "events", "event pathway has no event periods"
            ))
            return

        periods = {str(p).upper() for p in control.averaging_periods}
        groups = {"ALL"} | {g.group_name.upper() for g in sources.group_definitions}
        groups |= {g.group_name.upper() for g in getattr(sources, "psd_groups", [])}
        seen_names = set()
        for event in events.events:
            name = event.event_name
            if len(name) > EVENT_NAME_LENGTH:
                result.errors.append(ValidationError(
                    pathway, "event_name",
                    f"'{name}' exceeds {EVENT_NAME_LENGTH} characters (AERMOD's EVNAME)"
                ))
            if name in seen_names:
                result.errors.append(ValidationError(
                    pathway, "event_name", f"duplicate event name '{name}' (E313)"
                ))
            seen_names.add(name)

            try:
                hours = int(event.averaging_period)
            except (TypeError, ValueError):
                hours = -1
            if str(hours) not in periods:
                result.errors.append(ValidationError(
                    pathway, "averaging_period",
                    f"event '{name}': {event.averaging_period!r} is not on AVERTIME (E203)"
                ))
            if hours > 24:
                result.errors.append(ValidationError(
                    pathway, "averaging_period",
                    f"event '{name}': averaging period must be 24 hours or less (E297)"
                ))

            date = str(event.date)
            if not (len(date) == 8 and date.isdigit()):
                result.errors.append(ValidationError(
                    pathway, "date",
                    f"event '{name}': must be YYMMDDHH (8 digits), got '{date}'"
                ))

            if event.source_group.upper() not in groups:
                result.errors.append(ValidationError(
                    pathway, "source_group",
                    f"event '{name}': source group '{event.source_group}' is not defined (E203)"
                ))

            if event.location is None:
                result.errors.append(ValidationError(
                    pathway, "location",
                    f"event '{name}' has no EVENTLOC receptor (E130)"
                ))

        option = output.event_output or control.eventfil_option
        if option is not None and option.upper() not in EVENT_OUTPUT_OPTIONS:
            result.errors.append(ValidationError(
                "OutputPathway", "event_output",
                f"EVENTOUT must be one of {EVENT_OUTPUT_OPTIONS}, got '{option}' (E203)"
            ))

        if not event_run and not control.eventfil:
            result.errors.append(ValidationError(
                pathway, "eventfil",
                "events defined but ControlPathway.eventfil not set",
                severity="warning",
            ))
