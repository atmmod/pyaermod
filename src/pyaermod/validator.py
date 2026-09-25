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
        cls._validate_control(project.control, result)
        cls._validate_sources(project.sources, project.control, result)
        cls._validate_receptors(project.receptors, result)
        cls._validate_meteorology(project.meteorology, result, check_files)
        cls._validate_output(project.output, result, project.control)
        if getattr(project, "events", None) is not None:
            cls._validate_events(project.events, project.control, result)

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
            if getattr(source, "is_urban", False):
                has_urban_source = True

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
            if gas_dep.diffusivity <= 0:
                result.errors.append(ValidationError(
                    name, "gas_deposition.diffusivity", "must be > 0"
                ))
            if not (0 <= gas_dep.reactivity <= 1):
                result.errors.append(ValidationError(
                    name, "gas_deposition.reactivity", "must be between 0 and 1"
                ))
            if gas_dep.henry_constant is None and gas_dep.dry_dep_velocity is None:
                result.errors.append(ValidationError(
                    name, "gas_deposition",
                    "either henry_constant or dry_dep_velocity must be set"
                ))

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

        # Per-source NO2/NOx ratio
        if getattr(src, "no2_ratio", None) is not None and not (0 <= src.no2_ratio <= 1):
            result.errors.append(ValidationError(
                name, "no2_ratio",
                f"must be between 0 and 1, got {src.no2_ratio}"
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

        # OLM groups: validate member IDs
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
    def _validate_meteorology(cls, met, result: ValidationResult, check_files: bool):
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
    def _validate_output(cls, output, result: ValidationResult, control=None):
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

    # ------------------------------------------------------------------
    # Event pathway
    # ------------------------------------------------------------------

    @classmethod
    def _validate_events(cls, events, control, result: ValidationResult):
        pathway = "EventPathway"

        if not events.events:
            result.errors.append(ValidationError(
                pathway, "events", "event pathway has no event periods"
            ))
            return

        seen_names = set()
        for event in events.events:
            if len(event.event_name) > 8:
                result.errors.append(ValidationError(
                    pathway, "event_name",
                    f"'{event.event_name}' exceeds 8 characters"
                ))

            if event.event_name in seen_names:
                result.errors.append(ValidationError(
                    pathway, "event_name",
                    f"duplicate event name '{event.event_name}'"
                ))
            seen_names.add(event.event_name)

            for date_str, field_name in [
                (event.start_date, "start_date"),
                (event.end_date, "end_date"),
            ]:
                if len(date_str) != 8 or not date_str.isdigit():
                    result.errors.append(ValidationError(
                        pathway, field_name,
                        f"must be YYMMDDHH format (8 digits), got '{date_str}'"
                    ))

        if events.events and not control.eventfil:
            result.errors.append(ValidationError(
                pathway, "eventfil",
                "events defined but ControlPathway.eventfil not set",
                severity="warning",
            ))
