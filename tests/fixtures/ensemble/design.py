"""The small design that tests/test_ensemble.py runs through run_design.

One OPENPIT source with a single particle size (MASSFRAX 1.0), the
Albany met of ``tests/fixtures/epa_official/`` (96 hours), 72 polar
receptors, and two PLOTFILEs whose names deliberately point outside the
run directory (``../shared/pit.plt`` and an absolute path), which
run_design must rewrite. The ``extras`` row adds what the model holds
only as lines kept verbatim (``AERMODProject.unparsed_lines``): an
hourly emission file (``HOUREMIS``), a second POSTFILE and a
second-highest PLOTFILE, beside a POSTFILE the model does hold.
``regenerate.py`` runs these rows with a real AERMOD and records the
results; the tests replay them.
"""

from __future__ import annotations

from pathlib import Path

from pyaermod.input_generator import (
    AERMODProject,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    ParticleDepositionParams,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    TerrainType,
)
from pyaermod.receptors import PolarGrid
from pyaermod.sources import OpenPitSource
from pyaermod.unparsed import UnparsedLine

HERE = Path(__file__).resolve().parent
MET = HERE.parent / "epa_official"

#: The hourly emission file of the ``extras`` row (``SO HOUREMIS``),
#: read when build() is called; a test may point it at a copy.
HOUREMIS = HERE / "houremis.dat"

#: The four runs of the design: two sizes by two densities.
ROWS = [
    {"case": "d2p5_rho1", "diameter_um": 2.5, "density": 1.0},
    {"case": "d10_rho1", "diameter_um": 10.0, "density": 1.0},
    {"case": "d2p5_rho2p65", "diameter_um": 2.5, "density": 2.65},
    {"case": "d10_rho2p65", "diameter_um": 10.0, "density": 2.65},
]

#: A run that fails: ANNUAL averages on four days of met are E480.
FAILING_ROW = {"case": "annual_e480", "diameter_um": 10.0, "density": 1.0,
               "average": "ANNUAL"}

#: A run with HOUREMIS, two POSTFILEs and a 2ND-highest PLOTFILE.
EXTRAS_ROW = {"case": "extras", "diameter_um": 10.0, "density": 1.0, "extras": True}

#: Every recorded case, by its "case" factor.
RECORDED_ROWS = [*ROWS, FAILING_ROW, EXTRAS_ROW]

#: Output names as build() gives them, before run_design rewrites them.
PLOT_PERIOD = "../shared/pit.plt"
PLOT_1HR = "/nonexistent-pyaermod-dir/pit_1h.plt"
POST_PERIOD = "../shared/pit_per.pst"          # the extras row's modelled POSTFILE
POST_1HR = "/nonexistent-pyaermod-dir/pit_1h.bin"  # its second POSTFILE, kept verbatim
PLOT_1HR_2ND = "../shared/pit_1h_2nd.plt"      # its 2ND PLOTFILE, kept verbatim


def houremis_lines(scale: float = 1.0) -> str:
    """The text of an hourly emission file for the 96 hours of the met:
    a daily cycle between 0.5 and 1.5 times 1e-5 g/s/m2, times ``scale``."""
    return "".join(
        f"SO HOUREMIS  88 03 {day:02d} {hour:02d} PIT {scale * 1e-5 * (0.5 + hour / 24):.4E}\n"
        for day in range(1, 5) for hour in range(1, 25)
    )


def build(factors: dict) -> AERMODProject:
    average = factors.get("average", "PERIOD")
    control = ControlPathway(
        title_one=f"run_design test {factors['case']}",
        pollutant_id=PollutantType.OTHER,
        averaging_periods=["1", average],
        terrain_type=TerrainType.FLAT,
        regulatory_default=False,
        calculate_concentration=True,
        calculate_dry_deposition=True,
    )
    sources = SourcePathway()
    sources.add_source(OpenPitSource(
        "PIT", -300.0, -200.0, emission_rate=1e-5, x_dimension=600.0,
        y_dimension=400.0, pit_volume=2.4e7,
        particle_deposition=ParticleDepositionParams(
            [factors["diameter_um"]], [1.0], [factors["density"]]),
    ))
    receptors = ReceptorPathway()
    receptors.add_polar_grid(PolarGrid(
        grid_name="POL", dist_init=1000.0, dist_num=2, dist_delta=1000.0,
        dir_init=10.0, dir_num=36, dir_delta=10.0,
    ))
    met = MeteorologyPathway(
        surface_file=str(MET / "AERMET2.SFC"), profile_file=str(MET / "AERMET2.PFL"),
        surface_station_id=14735, upper_air_station_id=14735, data_start_year=1988,
    )
    output = OutputPathway(
        receptor_table=True, receptor_table_rank=1, max_table=False,
        plot_file=PLOT_PERIOD, plot_file_averaging=average,
        plot_file_groups=[("1", "ALL", PLOT_1HR)],
    )
    project = AERMODProject(control, sources, receptors, met, output)
    if factors.get("extras"):
        # A 2ND-highest PLOTFILE needs RECTABLE to reach the second rank
        output.receptor_table_rank = 2
        output.postfile = POST_PERIOD
        output.postfile_averaging = "PERIOD"
        project.unparsed_lines = [
            UnparsedLine("SO", "HOUREMIS", [str(HOUREMIS), "PIT"]),
            UnparsedLine("OU", "POSTFILE", ["1", "ALL", "UNFORM", POST_1HR]),
            UnparsedLine("OU", "PLOTFILE", ["1", "ALL", "2ND", PLOT_1HR_2ND]),
        ]
    return project
