"""
PyAERMOD Configuration Validator

Validates AERMOD input parameters before generating .inp files.
Catches errors early with clear Python-side messages instead of
letting invalid parameters silently produce bad input files that
AERMOD rejects at runtime.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


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
    def validate(cls, project, check_files: bool = False) -> ValidationResult:
        """
        Validate an entire AERMODProject.

        Parameters
        ----------
        project : AERMODProject
            The project to validate.
        check_files : bool
            If True, verify that meteorology files exist on disk.

        Returns
        -------
        ValidationResult
        """
        result = ValidationResult()
        cls._validate_control(project.control, result)
        cls._validate_sources(project.sources, project.control, result)
        cls._validate_receptors(project.receptors, result)
        cls._validate_meteorology(project.meteorology, result, check_files)
        cls._validate_output(project.output, result)
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

    @classmethod
    def _validate_source(cls, source, control, result: ValidationResult):
        from pyaermod.input_generator import (
            PointSource, AreaSource, AreaCircSource, AreaPolySource,
            VolumeSource, LineSource, RLineSource,
            RLineExtSource, BuoyLineSource, OpenPitSource,
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
        if src.barrier_height_1 is not None:
            if src.barrier_height_1 < 0:
                result.errors.append(ValidationError(
                    name, "barrier_height_1",
                    f"must be >= 0, got {src.barrier_height_1}"
                ))
        if src.barrier_height_2 is not None:
            if src.barrier_height_2 < 0:
                result.errors.append(ValidationError(
                    name, "barrier_height_2",
                    f"must be >= 0, got {src.barrier_height_2}"
                ))

        # Depression validation
        if src.depression_depth is not None:
            if src.depression_depth > 0:
                result.errors.append(ValidationError(
                    name, "depression_depth",
                    f"must be <= 0 (negative depth), got {src.depression_depth}"
                ))
        if src.depression_wtop is not None:
            if src.depression_wtop < 0:
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

        for i, seg in enumerate(src.line_segments):
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

        if grid.x_num <= 0:
            result.errors.append(ValidationError(
                name, "x_num", f"must be > 0, got {grid.x_num}"
            ))
        if grid.y_num <= 0:
            result.errors.append(ValidationError(
                name, "y_num", f"must be > 0, got {grid.y_num}"
            ))
        if grid.x_delta <= 0:
            result.errors.append(ValidationError(
                name, "x_delta", f"must be > 0, got {grid.x_delta}"
            ))
        if grid.y_delta <= 0:
            result.errors.append(ValidationError(
                name, "y_delta", f"must be > 0, got {grid.y_delta}"
            ))

    @classmethod
    def _validate_polar_grid(cls, grid, result: ValidationResult):
        name = f"PolarGrid({grid.grid_name})"

        if grid.dist_num <= 0:
            result.errors.append(ValidationError(
                name, "dist_num", f"must be > 0, got {grid.dist_num}"
            ))
        if grid.dist_delta <= 0:
            result.errors.append(ValidationError(
                name, "dist_delta", f"must be > 0, got {grid.dist_delta}"
            ))
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

    @classmethod
    def _validate_output(cls, output, result: ValidationResult):
        pathway = "OutputPathway"

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
