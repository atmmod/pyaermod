"""
PyAERMOD Configuration Validator

Validates AERMOD input parameters before generating .inp files.
Catches errors early with clear Python-side messages instead of
letting invalid parameters silently produce bad input files that
AERMOD rejects at runtime.
"""

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .pathways import (
    EVENT_NAME_LENGTH,
    EVENT_OUTPUT_OPTIONS,
    NOHEADER_FILE_TYPES,
    TURBULENCE_OPTIONS,
    WIND_CATEGORY_COUNT,
    dayrange_field_is_valid,
)

# Valid AERMOD averaging periods
VALID_AVERAGING_PERIODS = {
    "1", "2", "3", "4", "6", "8", "12", "24", "MONTH", "ANNUAL", "PERIOD",
}

# Valid AERMOD pollutant IDs
VALID_POLLUTANT_IDS = {"OTHER", "PM25", "PM10", "NO2", "SO2", "CO", "O3"}

# Valid elevation units
VALID_ELEVATION_UNITS = {"METERS", "FEET"}


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
                 advanced: bool = True) -> ValidationResult:
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
            receptor-domain extent, DFAULT consistency, ANNUAL met
            coverage). Pass ``advanced=False`` to restrict output to
            only the base per-field checks.

        Returns
        -------
        ValidationResult
        """
        result = ValidationResult()
        event_run = bool(getattr(project, "event_processing", False))
        cls._validate_control(project.control, result)
        cls._validate_sources(project.sources, project.control, result)
        if not event_run:
            # An EVENT deck has no RE pathway; its receptors are the
            # EVENTLOC cards.
            cls._validate_receptors(project.receptors, result)
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

        if advanced:
            # Lazy import to avoid circulars: validator_advanced uses
            # ValidationError from this module.
            from .validator_advanced import advanced_validate
            result.errors.extend(advanced_validate(project))
        return result

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
        if pollutant not in VALID_POLLUTANT_IDS:
            result.errors.append(ValidationError(
                pathway, "pollutant_id",
                f"invalid pollutant '{pollutant}'; "
                f"valid values: {sorted(VALID_POLLUTANT_IDS)}"
            ))

        # Elevation units
        if control.elevation_units not in VALID_ELEVATION_UNITS:
            result.errors.append(ValidationError(
                pathway, "elevation_units",
                f"must be 'METERS' or 'FEET', got '{control.elevation_units}'"
            ))

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

    # ------------------------------------------------------------------
    # Source pathway
    # ------------------------------------------------------------------

    @classmethod
    def _validate_sources(cls, sources, control, result: ValidationResult):
        if not sources.sources:
            result.errors.append(ValidationError(
                "SourcePathway", "sources", "must contain at least one source"
            ))
            return

        # Check for duplicate source IDs
        ids = [s.source_id for s in sources.sources]
        seen = set()
        for sid in ids:
            if sid in seen:
                result.errors.append(ValidationError(
                    "SourcePathway", "source_id",
                    f"duplicate source ID '{sid}'"
                ))
            seen.add(sid)

        has_urban_source = False
        for source in sources.sources:
            cls._validate_source(source, control, result)
            if (getattr(source, "method_2", None) is not None
                    or getattr(source, "platform", None) is not None
                    or getattr(source, "location_type", None) == "SWPOINT"):
                cls._validate_source_options(source, control, result)
            if getattr(source, "is_urban", False):
                has_urban_source = True
        cls._validate_source_flags(sources, control, result)

        # Cross-field: urban sources need URBANOPT in control
        if has_urban_source and not control.urban_option:
            result.errors.append(ValidationError(
                "SourcePathway/ControlPathway", "urban_option",
                "one or more sources have is_urban=True but ControlPathway.urban_option is not set"
            ))

        # Validate background concentration if present
        if sources.background is not None:
            cls._validate_background(sources.background, result)

        # Validate centralized source group definitions
        if sources.group_definitions:
            cls._validate_source_groups(sources, result)

        cls._validate_psd_groups(sources, control, result)
        cls._validate_unit_conversions(sources, control, result)
        cls._validate_solid_barriers(sources, control, result)

    @classmethod
    def _validate_background(cls, background, result: ValidationResult):
        pathway = "BackgroundConcentration"

        if background.uniform_value is not None and background.uniform_value < 0:
            result.errors.append(ValidationError(
                pathway, "uniform_value",
                f"must be >= 0, got {background.uniform_value}"
            ))

        if background.period_values:
            for period, value in background.period_values.items():
                if period not in VALID_AVERAGING_PERIODS:
                    result.errors.append(ValidationError(
                        pathway, "period_values",
                        f"invalid averaging period '{period}'"
                    ))
                if value < 0:
                    result.errors.append(ValidationError(
                        pathway, "period_values",
                        f"value for period '{period}' must be >= 0, got {value}"
                    ))

        if background.sectors:
            if len(background.sectors) > 12:
                result.errors.append(ValidationError(
                    pathway, "sectors",
                    f"AERMOD supports max 12 background sectors, got {len(background.sectors)}"
                ))
            for s in background.sectors:
                if not (0 <= s.start_direction <= 360):
                    result.errors.append(ValidationError(
                        pathway, "sectors",
                        f"sector {s.sector_id} start_direction must be 0-360"
                    ))

        if background.sectors and background.sector_values:
            valid_ids = {s.sector_id for s in background.sectors}
            for (sid, period), val in background.sector_values.items():
                if sid not in valid_ids:
                    result.errors.append(ValidationError(
                        pathway, "sector_values",
                        f"sector_id {sid} not defined in sectors list"
                    ))
                if period not in VALID_AVERAGING_PERIODS:
                    result.errors.append(ValidationError(
                        pathway, "sector_values",
                        f"invalid averaging period '{period}' for sector {sid}"
                    ))
                if val < 0:
                    result.errors.append(ValidationError(
                        pathway, "sector_values",
                        f"value for sector {sid} period '{period}' must be >= 0"
                    ))

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
            if source.release_height < 0:
                result.errors.append(ValidationError(
                    name, "release_height", f"must be >= 0, got {source.release_height} (E209)"
                ))

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

        # Per-source NO2/NOx ratio (NO2RATIO applies to any source type;
        # soset.f NO2RAT rejects values outside 0-1 with E336)
        ratio = getattr(source, "no2_ratio", None)
        if ratio is not None and not (0 <= ratio <= 1):
            result.errors.append(ValidationError(
                f"{type(source).__name__}({source.source_id})", "no2_ratio",
                f"must be between 0 and 1, got {ratio}"
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
        has_dep = gas_dep is not None or particle_dep is not None

        if has_dep and not dep_enabled:
            result.errors.append(ValidationError(
                name, "deposition",
                "deposition parameters specified but DEPOS/DDEP/WDEP not enabled in MODELOPT",
                severity="warning",
            ))

        if gas_dep:
            cls._validate_gas_deposition(name, gas_dep, control, result)

        if particle_dep:
            if len(particle_dep.diameters) != len(particle_dep.mass_fractions):
                result.errors.append(ValidationError(
                    name, "particle_deposition",
                    "diameters and mass_fractions must have same length"
                ))
            if len(particle_dep.diameters) != len(particle_dep.densities):
                result.errors.append(ValidationError(
                    name, "particle_deposition",
                    "diameters and densities must have same length"
                ))
            if len(particle_dep.diameters) > 20:
                result.errors.append(ValidationError(
                    name, "particle_deposition.diameters",
                    "max 20 size categories"
                ))
            if particle_dep.mass_fractions:
                frac_sum = sum(particle_dep.mass_fractions)
                if abs(frac_sum - 1.0) > 0.01:
                    result.errors.append(ValidationError(
                        name, "particle_deposition.mass_fractions",
                        f"must sum to 1.0, got {frac_sum:.4f}",
                        severity="warning",
                    ))
            if any(d <= 0 for d in particle_dep.diameters):
                result.errors.append(ValidationError(
                    name, "particle_deposition.diameters",
                    "all diameters must be > 0"
                ))
            if any(r <= 0 for r in particle_dep.densities):
                result.errors.append(ValidationError(
                    name, "particle_deposition.densities",
                    "all densities must be > 0"
                ))

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

    @classmethod
    def _validate_point_source(cls, src, result: ValidationResult):
        name = f"PointSource({src.source_id})"

        if src.stack_height <= 0:
            result.errors.append(ValidationError(
                name, "stack_height",
                f"must be > 0, got {src.stack_height}"
            ))

        if src.stack_diameter <= 0:
            result.errors.append(ValidationError(
                name, "stack_diameter",
                f"must be > 0, got {src.stack_diameter}"
            ))

        if src.stack_temp <= 0:
            result.errors.append(ValidationError(
                name, "stack_temp",
                f"must be > 0 K, got {src.stack_temp}"
            ))

        if src.exit_velocity < 0:
            result.errors.append(ValidationError(
                name, "exit_velocity",
                f"must be >= 0, got {src.exit_velocity}"
            ))

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        # Building downwash array lengths
        for field_name in ("building_height", "building_width", "building_length",
                           "building_x_offset", "building_y_offset"):
            val = getattr(src, field_name, None)
            if val is not None and isinstance(val, list) and len(val) != 36:
                result.errors.append(ValidationError(
                    name, field_name,
                    f"must have exactly 36 values (one per 10° sector), got {len(val)}"
                ))

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

        if src.initial_lateral_dimension <= 0:
            result.errors.append(ValidationError(
                name, "initial_lateral_dimension",
                f"must be > 0, got {src.initial_lateral_dimension}"
            ))

        if src.initial_vertical_dimension <= 0:
            result.errors.append(ValidationError(
                name, "initial_vertical_dimension",
                f"must be > 0, got {src.initial_vertical_dimension}"
            ))

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        if src.release_height < 0:
            result.errors.append(ValidationError(
                name, "release_height",
                f"must be >= 0, got {src.release_height}"
            ))

        # Building downwash array lengths
        for field_name in ("building_height", "building_width", "building_length",
                           "building_x_offset", "building_y_offset"):
            val = getattr(src, field_name, None)
            if val is not None and isinstance(val, list) and len(val) != 36:
                result.errors.append(ValidationError(
                    name, field_name,
                    f"must have exactly 36 values (one per 10° sector), got {len(val)}"
                ))

    @classmethod
    def _validate_area_circ_source(cls, src, result: ValidationResult):
        name = f"AreaCircSource({src.source_id})"

        if src.radius <= 0:
            result.errors.append(ValidationError(
                name, "radius",
                f"must be > 0, got {src.radius}"
            ))

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        if src.release_height < 0:
            result.errors.append(ValidationError(
                name, "release_height",
                f"must be >= 0, got {src.release_height}"
            ))

        if src.num_vertices < 3:
            result.errors.append(ValidationError(
                name, "num_vertices",
                f"must be >= 3, got {src.num_vertices}"
            ))

    @classmethod
    def _validate_area_poly_source(cls, src, result: ValidationResult):
        name = f"AreaPolySource({src.source_id})"

        if len(src.vertices) < 3:
            result.errors.append(ValidationError(
                name, "vertices",
                f"must have at least 3 vertices, got {len(src.vertices)}"
            ))

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        if src.release_height < 0:
            result.errors.append(ValidationError(
                name, "release_height",
                f"must be >= 0, got {src.release_height}"
            ))

    @classmethod
    def _validate_volume_source(cls, src, result: ValidationResult):
        name = f"VolumeSource({src.source_id})"

        if src.initial_lateral_dimension <= 0:
            result.errors.append(ValidationError(
                name, "initial_lateral_dimension",
                f"must be > 0, got {src.initial_lateral_dimension}"
            ))

        if src.initial_vertical_dimension <= 0:
            result.errors.append(ValidationError(
                name, "initial_vertical_dimension",
                f"must be > 0, got {src.initial_vertical_dimension}"
            ))

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        if src.release_height < 0:
            result.errors.append(ValidationError(
                name, "release_height",
                f"must be >= 0, got {src.release_height}"
            ))

        # Building downwash array lengths
        for field_name in ("building_height", "building_width", "building_length",
                           "building_x_offset", "building_y_offset"):
            val = getattr(src, field_name, None)
            if val is not None and isinstance(val, list) and len(val) != 36:
                result.errors.append(ValidationError(
                    name, field_name,
                    f"must have exactly 36 values (one per 10° sector), got {len(val)}"
                ))

    @classmethod
    def _validate_line_source(cls, src, result: ValidationResult):
        from pyaermod.input_generator import RLineSource
        src_type = "RLineSource" if isinstance(src, RLineSource) else "LineSource"
        name = f"{src_type}({src.source_id})"

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        if src.release_height < 0:
            result.errors.append(ValidationError(
                name, "release_height",
                f"must be >= 0, got {src.release_height}"
            ))

        if src.initial_lateral_dimension <= 0:
            result.errors.append(ValidationError(
                name, "initial_lateral_dimension",
                f"must be > 0, got {src.initial_lateral_dimension}"
            ))

        # Zero-length line
        if (src.x_start == src.x_end and src.y_start == src.y_end):
            result.errors.append(ValidationError(
                name, "coordinates",
                "start and end points are identical (zero-length line)"
            ))

        # Street canyon validation (RLineSource only — LineSource has no canyon)
        if isinstance(src, RLineSource) and src.street_canyon is not None:
            cls._validate_street_canyon(name, src.street_canyon, result)

    @classmethod
    def _validate_street_canyon(cls, name: str, canyon, result: ValidationResult):
        if canyon.building_height <= 0:
            result.errors.append(ValidationError(
                name, "street_canyon.building_height",
                f"must be > 0, got {canyon.building_height}"
            ))
        if canyon.street_width <= 0:
            result.errors.append(ValidationError(
                name, "street_canyon.street_width",
                f"must be > 0, got {canyon.street_width}"
            ))

    @classmethod
    def _validate_rline_ext_source(cls, src, result: ValidationResult):
        name = f"RLineExtSource({src.source_id})"

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        if src.road_width <= 0:
            result.errors.append(ValidationError(
                name, "road_width",
                f"must be > 0, got {src.road_width}"
            ))

        if src.init_sigma_z < 0:
            result.errors.append(ValidationError(
                name, "init_sigma_z",
                f"must be >= 0, got {src.init_sigma_z}"
            ))

        # Zero-length line
        if (src.x_start == src.x_end and src.y_start == src.y_end):
            result.errors.append(ValidationError(
                name, "coordinates",
                "start and end points are identical (zero-length line)"
            ))

        # Barrier validation
        if src.barrier_height_1 is not None and src.barrier_height_1 < 0:
            result.errors.append(ValidationError(
                name, "barrier_height_1",
                f"must be >= 0, got {src.barrier_height_1}"
            ))
        if src.barrier_height_2 is not None and src.barrier_height_2 < 0:
            result.errors.append(ValidationError(
                name, "barrier_height_2",
                f"must be >= 0, got {src.barrier_height_2}"
            ))

        # Depression validation
        if src.depression_depth is not None and src.depression_depth > 0:
            result.errors.append(ValidationError(
                name, "depression_depth",
                f"must be <= 0 (negative depth), got {src.depression_depth}"
            ))
        if src.depression_wtop is not None and src.depression_wtop < 0:
            result.errors.append(ValidationError(
                name, "depression_wtop",
                f"must be >= 0, got {src.depression_wtop}"
            ))
        if src.depression_wbottom is not None:
            if src.depression_wbottom < 0:
                result.errors.append(ValidationError(
                    name, "depression_wbottom",
                    f"must be >= 0, got {src.depression_wbottom}"
                ))
            if src.depression_wtop is not None and src.depression_wbottom > src.depression_wtop:
                result.errors.append(ValidationError(
                    name, "depression_wbottom",
                    f"must be <= depression_wtop ({src.depression_wtop}), got {src.depression_wbottom}"
                ))

        # Street canyon validation
        if src.street_canyon is not None:
            cls._validate_street_canyon(name, src.street_canyon, result)

    @classmethod
    def _validate_buoyline_source(cls, src, result: ValidationResult):
        name = f"BuoyLineSource({src.source_id})"

        if src.avg_buoyancy_parameter <= 0:
            result.errors.append(ValidationError(
                name, "avg_buoyancy_parameter",
                f"must be > 0, got {src.avg_buoyancy_parameter}"
            ))

        if src.avg_line_length <= 0:
            result.errors.append(ValidationError(
                name, "avg_line_length",
                f"must be > 0, got {src.avg_line_length}"
            ))

        if src.avg_building_height <= 0:
            result.errors.append(ValidationError(
                name, "avg_building_height",
                f"must be > 0, got {src.avg_building_height}"
            ))

        if not src.line_segments:
            result.errors.append(ValidationError(
                name, "line_segments",
                "must have at least one line segment"
            ))

        for _i, seg in enumerate(src.line_segments):
            seg_name = f"BuoyLineSegment({seg.source_id})"
            if seg.emission_rate < 0:
                result.errors.append(ValidationError(
                    seg_name, "emission_rate",
                    f"must be >= 0, got {seg.emission_rate}"
                ))
            if seg.release_height < 0:
                result.errors.append(ValidationError(
                    seg_name, "release_height",
                    f"must be >= 0, got {seg.release_height}"
                ))
            if seg.release_height > 3000:
                result.errors.append(ValidationError(
                    seg_name, "release_height",
                    f"must be <= 3000, got {seg.release_height}"
                ))
            if (seg.x_start == seg.x_end and seg.y_start == seg.y_end):
                result.errors.append(ValidationError(
                    seg_name, "coordinates",
                    "start and end points are identical (zero-length line)"
                ))

    @classmethod
    def _validate_openpit_source(cls, src, result: ValidationResult):
        name = f"OpenPitSource({src.source_id})"

        if src.emission_rate < 0:
            result.errors.append(ValidationError(
                name, "emission_rate",
                f"must be >= 0, got {src.emission_rate}"
            ))

        if src.release_height < 0:
            result.errors.append(ValidationError(
                name, "release_height",
                f"must be >= 0, got {src.release_height}"
            ))

        if src.x_dimension <= 0:
            result.errors.append(ValidationError(
                name, "x_dimension",
                f"must be > 0, got {src.x_dimension}"
            ))

        if src.y_dimension <= 0:
            result.errors.append(ValidationError(
                name, "y_dimension",
                f"must be > 0, got {src.y_dimension}"
            ))

        if src.pit_volume <= 0:
            result.errors.append(ValidationError(
                name, "pit_volume",
                f"must be > 0, got {src.pit_volume}"
            ))

        # Warning: release height exceeds effective pit depth
        if src.x_dimension > 0 and src.y_dimension > 0 and src.pit_volume > 0:
            eff_depth = src.effective_depth
            if src.release_height > eff_depth:
                result.errors.append(ValidationError(
                    name, "release_height",
                    f"exceeds effective pit depth ({eff_depth:.2f}m), got {src.release_height}",
                    severity="warning"
                ))

        # Warning: aspect ratio > 10
        if src.x_dimension > 0 and src.y_dimension > 0:
            ratio = max(src.x_dimension / src.y_dimension, src.y_dimension / src.x_dimension)
            if ratio > 10:
                result.errors.append(ValidationError(
                    name, "x_dimension/y_dimension",
                    f"aspect ratio > 10 ({ratio:.1f})",
                    severity="warning"
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
    def _validate_source_groups(cls, sources, result: ValidationResult):
        """Validate centralized source group definitions."""
        all_source_ids = set()
        from pyaermod.input_generator import BuoyLineSource

        for source in sources.sources:
            if isinstance(source, BuoyLineSource):
                for seg in source.line_segments:
                    all_source_ids.add(seg.source_id)
            else:
                all_source_ids.add(source.source_id)

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
            for member_id in group.member_source_ids:
                if member_id not in all_source_ids:
                    result.errors.append(ValidationError(
                        f"SourceGroupDefinition({group.group_name})",
                        "member_source_ids",
                        f"source ID '{member_id}' not found in project sources"
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
        from .pathways import BACKGROUND_UNITS, TEMPORAL_FLAG_COUNTS
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
            expected = TEMPORAL_FLAG_COUNTS.get(spec.varying.flag.upper())
            if expected is None:
                result.errors.append(ValidationError(
                    pathway, where,
                    f"unknown temporal flag {spec.varying.flag!r}; AERMOD "
                    f"accepts {sorted(TEMPORAL_FLAG_COUNTS)}"
                ))
            elif len(spec.varying.values) != expected:
                result.errors.append(ValidationError(
                    pathway, where,
                    f"{spec.varying.flag} needs {expected} values, "
                    f"got {len(spec.varying.values)}"
                ))

    @classmethod
    def _validate_sectors(cls, label, sectors, pathway, result):
        """O3SECTOR / NOXSECTR: 2..6 ascending directions, >= 30 deg apart."""
        if not sectors:
            return
        if not 2 <= len(sectors) <= 6:
            result.errors.append(ValidationError(
                pathway, label, f"needs 2 to 6 sector start directions, got {len(sectors)}"
            ))
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

        # Default NO2 ratio in [0, 1]
        if not (0 <= chemistry.default_no2_ratio <= 1):
            result.errors.append(ValidationError(
                pathway, "default_no2_ratio",
                f"must be between 0 and 1, got {chemistry.default_no2_ratio}"
            ))

        # Ozone data required for OLM, PVMRM, GRSM
        if (chemistry.method in (ChemistryMethod.OLM, ChemistryMethod.PVMRM,
                                 ChemistryMethod.GRSM) and chemistry.ozone_data is None):
            result.errors.append(ValidationError(
                pathway, "ozone_data",
                f"ozone data required for {chemistry.method.value} method"
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
            from .pathways import BACKGROUND_UNITS
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
            from .pathways import BACKGROUND_UNITS
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
    def _validate_receptors(cls, receptors, result: ValidationResult):
        pathway = "ReceptorPathway"

        total = (len(receptors.cartesian_grids)
                 + len(receptors.polar_grids)
                 + len(receptors.discrete_receptors))
        if total == 0:
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
            if met.surface_file and not Path(met.surface_file).exists():
                result.errors.append(ValidationError(
                    pathway, "surface_file",
                    f"file not found: '{met.surface_file}'"
                ))
            if met.profile_file and not Path(met.profile_file).exists():
                result.errors.append(ValidationError(
                    pathway, "profile_file",
                    f"file not found: '{met.profile_file}'"
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

        cls._validate_output_files(output, result, control, sources)

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
            "POSTFILE": bool(output.postfile),
            "PLOTFILE": bool(output.plot_file or output.plot_file_groups),
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
