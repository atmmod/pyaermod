"""The "Albany stack" reference scenario of PLAN-gui.md, as a user enters it.

``scripts/record_aermod_fixtures.py`` builds the same scenario with the
library; the fake AERMOD checks that what the GUI writes from these UI
inputs is the deck that was recorded. The two definitions are kept
separate on purpose, so each checks the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .harness import EPA_FIXTURES, RECORDINGS

SURFACE_FILE = EPA_FIXTURES / "AERMET2.SFC"
PROFILE_FILE = EPA_FIXTURES / "AERMET2.PFL"

TITLE = "Albany stack reference scenario"
TITLE_TWO = "Entered through the GUI by the end-to-end journeys"
POLLUTANT = "SO2"
AVERAGING_PERIODS = ("1", "3", "24", "PERIOD")
# The GUI's default averaging periods. With four days of met data AERMOD
# aborts ANNUAL with fatal error E480 (recording albany_e480).
E480_AVERAGING_PERIODS = ("1", "ANNUAL")

STACK = dict(id="STACK1", x=0, y=0, stack_height=65, stack_temp=425,
             exit_velocity=18, stack_diameter=3, emission_rate=100)
# The reference grid is the GUI's default polar grid: centred on the
# origin, 10 rings from 100 m in 100 m steps and 36 radials from 0 degrees
# in 10 degree steps. The user adds it and checks its shape in the table;
# the fake AERMOD (T2) and the maxima (T3) confirm the rest.
GRID = dict(name="GRID1")
GRID_SHAPE = dict(rings=10, directions=36)
STATIONS = dict(surface_station_id=14735, upper_air_station_id=14735,
                data_start_year=1988)

# Reproduced from AERMOD v26135 (gfortran -O2) on 2026-09-28; see
# tests/fixtures/gui/aermod_recordings/albany_success/manifest.json.
MAXIMA = {"1HR": 76.07952, "3HR": 59.57654, "24HR": 16.85665, "PERIOD": 5.40459}
MAX_LOCATION = (519.62, -300.00)

AERTEST_RECORDING = RECORDINGS / "aertest"


def enter_reference_scenario(gui, step: Optional[Callable[[str], object]] = None,
                             *, surface_file: Path = SURFACE_FILE) -> None:
    """Enter everything but the averaging periods, one step at a time.

    The current GUI cannot set averaging periods (WP-G3), so journeys call
    ``gui.project.set_averaging_periods`` themselves, inside a known gap
    when they need anything but the default ``1 ANNUAL``.
    """
    shot = step or (lambda _name: None)
    gui.project.set_titles(TITLE, TITLE_TWO)
    gui.project.set_pollutant(POLLUTANT)
    shot("project")
    gui.sources.add_point_source(**STACK)
    gui.sources.expect_ids([STACK["id"]])
    shot("sources")
    gui.receptors.add_polar_grid(**GRID)
    gui.receptors.expect_names([GRID["name"]])
    gui.receptors.expect_polar_grid(GRID["name"], **GRID_SHAPE)
    shot("receptors")
    gui.meteorology.set_met_files(surface_file, PROFILE_FILE)
    gui.meteorology.set_stations(**STATIONS)
    shot("meteorology")
