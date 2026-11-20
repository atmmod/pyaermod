"""
What the GUIs offer, with no UI: the source and receptor types and the
values a new one starts with, the fields the editors put under
"Advanced", and the option tables and field groups of the steps.

The NiceGUI pages (:mod:`pyaermod.gui_v2.pages`) and the browser GUI
(:mod:`pyaermod.browser`, which runs under Pyodide without NiceGUI) both
read these, so the two offer the same things.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Type

from ..input_generator import (
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    DiscreteReceptor,
    LineSource,
    OpenPitSource,
    PointCapSource,
    PointHorSource,
    PointSource,
    PolarGrid,
    RLineExtSource,
    RLineSource,
    SidewashPointSource,
    TerrainType,
    VolumeSource,
)
from ..validator import VALID_AVERAGING_PERIODS

# ---------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------

SOURCE_TYPES: Dict[str, Type] = {
    "PointSource":      PointSource,
    "VolumeSource":     VolumeSource,
    "AreaSource":       AreaSource,
    "AreaCircSource":   AreaCircSource,
    "AreaPolySource":   AreaPolySource,
    "LineSource":       LineSource,
    "RLineSource":      RLineSource,
    "RLineExtSource":   RLineExtSource,
    "BuoyLineSource":   BuoyLineSource,
    "OpenPitSource":    OpenPitSource,
    "PointCapSource":  PointCapSource,
    "PointHorSource":  PointHorSource,
    "SidewashPointSource": SidewashPointSource,
}


# Required-field placeholder values for new-source instantiation.
# Each value should pass __post_init__ validation so the dialog can
# open without errors; the user is expected to override before save.
SOURCE_DEFAULTS: Dict[str, Any] = {
    "source_id":       "NEW_SRC",
    "x_coord":         0.0,
    "y_coord":         0.0,
    "x_start":         0.0,
    "y_start":         0.0,
    "x_end":           100.0,
    "y_end":           0.0,
    "stack_height":    10.0,
    "release_height":  2.0,
    "stack_temp":      400.0,
    "exit_velocity":   10.0,
    "stack_diameter":  1.0,
    "emission_rate":   1.0,
    "x_length":        100.0,
    "y_length":        100.0,
    "radius":          50.0,
    "vertices":        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
    "initial_lateral_dimension":  10.0,
    "initial_vertical_dimension": 5.0,
    "init_sigma_y":               5.0,
    "init_sigma_z":               2.0,
    "pit_volume":                 1000.0,
    "pit_height":                 10.0,
    "depth":                      2.0,
    "width_top":                  20.0,
    "width_bottom":               10.0,
    "line_segments":              [
        BuoyLineSegment(
            source_id="BL_SEG1",
            x_start=0.0, y_start=0.0, x_end=100.0, y_end=0.0,
            emission_rate=1.0, release_height=2.0,
        ),
    ],
    # RLineExtSource z coords (per-endpoint elevations)
    "z_start":  0.0,
    "z_end":    0.0,
    # BuoyLineSource per-line meteorological parameters
    "avg_line_length":           100.0,
    "avg_line_width":             10.0,
    "avg_buoyancy_parameter":      5.0,
    "avg_building_height":         5.0,
    "avg_building_width":         10.0,
    "avg_building_separation":    10.0,
}


def new_source(type_name: str) -> Any:
    """Construct a default instance of ``type_name`` for editing.

    Pulls from ``SOURCE_DEFAULTS`` for every field listed there, even if the
    underlying dataclass has its own default: the GUI's defaults are
    intentionally sensible (10 m stack, 1 g/s emission) where the
    dataclass defaults to 0.
    """
    cls = SOURCE_TYPES[type_name]
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name in SOURCE_DEFAULTS:
            kwargs[f.name] = SOURCE_DEFAULTS[f.name]
    return cls(**kwargs)


# ---------------------------------------------------------------------
# Receptors
# ---------------------------------------------------------------------

RECEPTOR_TYPES: Dict[str, Type] = {
    "CartesianGrid":     CartesianGrid,
    "PolarGrid":         PolarGrid,
    "DiscreteReceptor":  DiscreteReceptor,
}


# Sensible defaults for new receptors. Only required fields (no
# default / default_factory) need entries; the rest fall back to the
# dataclass's own defaults.
RECEPTOR_DEFAULTS: Dict[str, Any] = {
    "grid_name":   "GRID1",
    "x_origin":    0.0,
    "y_origin":    0.0,
    "x_init":      -1000.0,
    "y_init":      -1000.0,
    "x_num":       21,
    "y_num":       21,
    "x_delta":     100.0,
    "y_delta":     100.0,
    "dist_init":   100.0,
    "dist_num":    10,
    "dist_delta":  100.0,
    "dir_init":    0.0,
    "dir_num":     36,
    "dir_delta":   10.0,
    "x_coord":     0.0,
    "y_coord":     0.0,
}


def new_receptor(type_name: str) -> Any:
    """Construct a default-filled receptor of ``type_name``."""
    cls = RECEPTOR_TYPES[type_name]
    kwargs = {f.name: RECEPTOR_DEFAULTS[f.name]
              for f in dataclasses.fields(cls) if f.name in RECEPTOR_DEFAULTS}
    return cls(**kwargs)


#: Fields the editor puts under "Advanced": everything AERMOD does not need
#: on the LOCATION and SRCPARAM cards. Shared with the Receptors step.
ADVANCED_FIELDS = frozenset({
    "base_elevation", "flat_source",
    "building_height", "building_width", "building_length",
    "building_x_offset", "building_y_offset",
    "source_groups", "is_urban", "urban_area_name", "no2_ratio",
    "gas_deposition", "particle_deposition", "deposition_method", "method_2",
    "platform", "street_canyon", "vegetative_barriers",
    "barrier_height_1", "barrier_dcl_1", "barrier_height_2", "barrier_dcl_2",
    "depression_depth", "depression_wtop", "depression_wbottom", "num_vertices",
    "depth_hint",
    # receptors
    "z_elev", "z_hill", "z_flag", "grid_elevations", "grid_hills", "grid_flags",
    "x_points", "y_points", "distances", "directions", "origin_source_id",
    "elevations", "hills", "flags",
})

# ---------------------------------------------------------------------
# The steps' options and field groups
# ---------------------------------------------------------------------

#: AERMOD's averaging periods, in the order AVERTIME lists them.
AVERAGING_PERIODS: List[str] = sorted(
    VALID_AVERAGING_PERIODS,
    key=lambda p: (0, int(p)) if p.isdigit() else (1, ["MONTH", "PERIOD", "ANNUAL"].index(p)),
)

#: The terrain choices, as MODELOPT spells them.
TERRAIN_CHOICES = {
    TerrainType.FLAT.value: "Flat (FLAT)",
    TerrainType.ELEVATED.value: "Elevated (ELEV)",
    TerrainType.FLATSRCS.value: "Elevated, some sources flat (FLAT ELEV)",
}

#: What AERMOD computes (MODELOPT), as the check boxes read.
OUTPUT_OPTIONS = (
    ("calculate_concentration", "Concentration (CONC)"),
    ("calculate_deposition", "Total deposition (DEPOS)"),
    ("calculate_dry_deposition", "Dry deposition (DDEP)"),
    ("calculate_wet_deposition", "Wet deposition (WDEP)"),
)

#: The groups of the Meteorology step, in order; every other field goes under "Advanced".
MET_GROUPS = (
    ("Met files", "The surface and profile files AERMET wrote for the site.",
     ("surface_file", "profile_file")),
    ("Stations", "SURFDATA, UAIRDATA and PROFBASE: AERMOD checks these against the files.",
     ("surface_station_id", "upper_air_station_id", "data_start_year", "profile_base_elevation")),
    ("Period to model", "STARTEND: leave blank to model every hour of the files.",
     ("start_year", "start_month", "start_day", "start_hour",
      "end_year", "end_month", "end_day", "end_hour")),
)

#: The Output step's groups of OutputPathway fields.
TABLE_FIELDS = ("receptor_table", "receptor_table_rank", "max_table", "max_table_rank",
                "day_table")
FILE_FIELDS = ("summary_file", "plot_file", "plot_file_averaging", "postfile",
               "postfile_averaging", "postfile_source_group", "postfile_format", "file_format")
#: Shown by the "Files for the Results step" group, not as text boxes.
RESULTS_FIELDS = ("period_plot_files", "period_postfiles")
#: Kept for older projects; the model options decide what AERMOD computes.
HIDDEN_FIELDS = ("output_type",)

#: AERMOD's unit labels, as the Results step shows them.
UNITS = {"ug/m^3": "µg/m³", "g/m^2": "g/m²", "g/m^2/yr": "g/m²/yr"}

__all__ = [
    "ADVANCED_FIELDS",
    "AVERAGING_PERIODS",
    "FILE_FIELDS",
    "HIDDEN_FIELDS",
    "MET_GROUPS",
    "OUTPUT_OPTIONS",
    "RECEPTOR_DEFAULTS",
    "RECEPTOR_TYPES",
    "RESULTS_FIELDS",
    "SOURCE_DEFAULTS",
    "SOURCE_TYPES",
    "TABLE_FIELDS",
    "TERRAIN_CHOICES",
    "UNITS",
    "new_receptor",
    "new_source",
]
