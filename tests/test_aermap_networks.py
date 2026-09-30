"""
Reading AERMAP's receptor and source files back into an AERMOD project.

The files are the real AERMAP 24142 output recorded in
tests/fixtures/aermap_runner/networks/ (see its README): one discrete
receptor, two Cartesian grids (XYINC and XPNTS/YPNTS), two polar grids
(GDIR, and DDIR around a source) and a source of every AERMAP type but
POINTHOR, on the planar DEM z = 100 + 2 i + 3 j at node (i, j), nodes
100 m apart from (500000, 4000000).
"""

import math
from pathlib import Path

import pandas as pd
import pytest

from pyaermod.input_generator import (
    AERMODProject,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    RLineSource,
    SourcePathway,
)
from pyaermod.receptors import PolarGrid
from pyaermod.terrain import AERMAPOutputParser, TerrainProcessor

NETWORKS = Path(__file__).parent / "fixtures" / "aermap_runner" / "networks"


def _plane(x: float, y: float) -> float:
    return 100.0 + 2.0 * (x - 500000.0) / 100.0 + 3.0 * (y - 4000000.0) / 100.0


def _polar_xy(x0, y0, dist, direction):
    return x0 + dist * math.sin(math.radians(direction)), y0 + dist * math.cos(math.radians(direction))


@pytest.fixture(scope="module")
def receptors():
    return AERMAPOutputParser.parse_receptor_output(NETWORKS / "aermap_receptors.out")


class TestReceptorFile:
    def test_every_network_is_read_under_its_id(self, receptors):
        counts = receptors.groupby(receptors["network"].fillna("<discrete>")).size().to_dict()
        assert counts == {"<discrete>": 1, "G1": 6, "G2": 6, "P1": 8, "P2": 6}

    def test_every_receptor_sits_on_the_plane(self, receptors):
        # AERMAP writes grid elevations as F8.1, discrete ones as F10.2.
        for r in receptors.itertuples():
            assert r.zelev == pytest.approx(_plane(r.x, r.y), abs=0.051), r
            assert r.zhill >= r.zelev

    def test_cartesian_rows_are_y_values(self, receptors):
        g2 = receptors[receptors["network"] == "G2"].sort_values(["row", "col"])
        assert list(zip(g2["row"], g2["col"], g2["x"], g2["y"])) == [
            (0, 0, 500150.0, 4000150.0), (0, 1, 500250.0, 4000150.0), (0, 2, 500450.0, 4000150.0),
            (1, 0, 500150.0, 4000350.0), (1, 1, 500250.0, 4000350.0), (1, 2, 500450.0, 4000350.0),
        ]

    def test_polar_rows_are_directions(self, receptors):
        p1 = receptors[receptors["network"] == "P1"]
        # Row 0 is due north (GDIR 4 0 90), column 1 the 200 m ring.
        north = p1[(p1["row"] == 0) & (p1["col"] == 1)].iloc[0]
        assert (north.x, north.y) == pytest.approx((500300.0, 4000500.0))
        assert north.zelev == 121.0
        p2 = receptors[receptors["network"] == "P2"]
        # DDIR 45 135 225 around STK (500200, 4000300); row 2 is 225 degrees.
        sw = p2[(p2["row"] == 2) & (p2["col"] == 1)].iloc[0]
        assert (sw.x, sw.y) == pytest.approx(_polar_xy(500200.0, 4000300.0, 150.0, 225.0))

    def test_a_polar_grid_centred_on_a_source_id_has_no_coordinates(self, tmp_path):
        """ORIG srcid (a hand-written deck): the file does not say where the source is."""
        out = tmp_path / "rec.out"
        out.write_text(
            "   GRIDPOLR  P2       STA\n"
            "   GRIDPOLR  P2       ORIG  STK\n"
            "   GRIDPOLR  P2       DIST  100 200\n"
            "   GRIDPOLR  P2       DDIR  45\n"
            "   GRIDPOLR P2       ELEV    1    203.5    207.1\n"
            "   GRIDPOLR P2       HILL    1    203.5    207.1\n"
            "   GRIDPOLR  P2       END\n"
        )
        df = AERMAPOutputParser.parse_receptor_output(out)
        assert df["zelev"].tolist() == [203.5, 207.1]
        assert df["x"].isna().all() and df["y"].isna().all()

    def test_rows_past_the_network_and_bad_fields_are_skipped(self, tmp_path):
        out = tmp_path / "rec.out"
        out.write_text(
            "RE ELEVUNIT METERS\n"
            "RE\n"
            "   DISCCART  1.0\n"
            "   DISCCART  1.0 2.0 x\n"
            "   GRIDCART\n"
            "   GRIDCART  G  XYINC  0 2 10 0 1 10\n"
            "   GRIDCART  G  ELEV   1  5.0 6.0 7.0\n"
            "   GRIDCART  G  ELEV   2  8.0\n"
            "   GRIDCART  G  ELEV   x  9.0\n"
            "   GRIDPOLR  P  ORIG   0 0\n"
            "   GRIDPOLR  P  DIST   10\n"
            "   GRIDPOLR  P  GDIR   1 0 90\n"
            "   GRIDPOLR  P  ELEV   1  1.0 2.0\n"
            "   GRIDPOLR  P  ELEV   2  3.0\n"
        )
        df = AERMAPOutputParser.parse_receptor_output(out)
        # G is 2 x 1 and P 1 x 1: the extra values and rows are dropped,
        # and a missing HILL row reads as 0.
        assert list(zip(df["network"], df["zelev"], df["zhill"])) == [
            ("G", 5.0, 0.0), ("G", 6.0, 0.0), ("P", 1.0, 0.0),
        ]


class TestSourceFile:
    def test_the_elevation_is_the_last_field(self):
        src = AERMAPOutputParser.parse_source_output(NETWORKS / "aermap_sources.out")
        zelev = dict(zip(src["source_id"], src["zelev"]))
        assert zelev == {
            "STK": 113.0, "CAP": 112.0, "VOL": 114.0, "AR": 117.0, "AC": 112.5, "AP": 120.5,
            "PIT": 113.5,
            # SOLOCA: the LINE at the south-west corner of its equivalent
            # area, 5 m north of its start; RLINE and BUOYLINE at the midpoint.
            "LN": _plane(500100.0, 4000405.0), "RL": _plane(500200.0, 4000200.0),
            "BL1": _plane(500250.0, 4000500.0),
        }
        # x and y are the first point.
        assert src[src["source_id"] == "LN"][["x", "y"]].values.tolist() == [[500100.0, 4000400.0]]


def _project():
    """The AERMOD side of the networks recording."""
    project = AERMODProject(
        control=ControlPathway(title_one="networks"),
        sources=SourcePathway(),
        receptors=ReceptorPathway(
            cartesian_grids=[
                CartesianGrid(grid_name="G1", x_init=500100.0, x_num=3, x_delta=100.0,
                              y_init=4000200.0, y_num=2, y_delta=100.0),
                CartesianGrid(grid_name="G2", x_points=[500150.0, 500250.0, 500450.0],
                              y_points=[4000150.0, 4000350.0]),
            ],
            polar_grids=[
                PolarGrid(grid_name="P1", x_origin=500300.0, y_origin=4000300.0,
                          dist_init=100.0, dist_num=2, dist_delta=100.0,
                          dir_init=0.0, dir_num=4, dir_delta=90.0),
                PolarGrid(grid_name="P2", origin_source_id="STK", distances=[50.0, 150.0],
                          directions=[45.0, 135.0, 225.0]),
            ],
            discrete_receptors=[DiscreteReceptor(500100.0, 4000100.0)],
        ),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )
    project.sources.add_source(PointSource("STK", 500200.0, 4000300.0))
    project.sources.add_source(LineSource("LN", 500100.0, 4000400.0, 500400.0, 4000400.0,
                                          initial_lateral_dimension=10.0))
    project.sources.add_source(RLineSource("RL", 500100.0, 4000100.0, 500300.0, 4000300.0))
    project.sources.add_source(BuoyLineSource(
        "BLG", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        line_segments=[BuoyLineSegment("BL1", 500200.0, 4000500.0, 500300.0, 4000500.0),
                       BuoyLineSegment("NOTRUN", 0.0, 0.0, 1.0, 1.0)],
    ))
    return project


class TestFillingInTheProject:
    def test_every_grid_gets_its_own_rows(self, receptors):
        project = _project()
        processor = TerrainProcessor()
        processor._update_receptor_elevations(project, receptors)
        processor._update_grid_receptor_elevations(project, receptors)
        processor._update_polar_grid_elevations(project, receptors)

        assert project.receptors.discrete_receptors[0].z_elev == 105.0
        for grid in project.receptors.cartesian_grids:
            expected = [[_plane(x, y) for x in grid.x_values()] for y in grid.y_values()]
            for row, want in zip(grid.grid_elevations, expected):
                assert row == pytest.approx(want, abs=0.051)
            assert grid.grid_hills == grid.grid_elevations
        origins = {"P1": (500300.0, 4000300.0), "P2": (500200.0, 4000300.0)}
        for grid in project.receptors.polar_grids:
            x0, y0 = origins[grid.grid_name]
            expected = [[_plane(*_polar_xy(x0, y0, d, a)) for d in grid.ring_distances()]
                        for a in grid.direction_angles()]
            for row, want in zip(grid.elevations, expected):
                assert row == pytest.approx(want, abs=0.051)
        # The written AERMOD deck carries them (one ELEV row per direction).
        assert "GRIDPOLR  P2       ELEV      3     111.2    107.7" in project.receptors.to_aermod_input()

    def test_a_grid_aermap_did_not_report_is_left_alone(self, receptors):
        project = _project()
        extra = CartesianGrid(grid_name="G9")
        project.receptors.cartesian_grids.append(extra)
        project.receptors.polar_grids.append(PolarGrid(grid_name="P9"))
        processor = TerrainProcessor()
        processor._update_grid_receptor_elevations(project, receptors)
        processor._update_polar_grid_elevations(project, receptors)
        assert extra.grid_elevations is None
        assert project.receptors.polar_grids[-1].elevations is None

    def test_a_frame_without_networks_leaves_polar_grids_alone(self):
        project = _project()
        TerrainProcessor()._update_polar_grid_elevations(
            project, pd.DataFrame([{"x": 0.0, "y": 0.0, "zelev": 1.0, "zhill": 1.0}]),
        )
        assert all(g.elevations is None for g in project.receptors.polar_grids)

    def test_every_source_and_buoyline_segment_gets_its_elevation(self):
        project = _project()
        src = AERMAPOutputParser.parse_source_output(NETWORKS / "aermap_sources.out")
        TerrainProcessor()._update_source_elevations(project, src)
        by_id = {s.source_id: s for s in project.sources.sources}
        assert by_id["STK"].base_elevation == 113.0
        assert by_id["LN"].base_elevation == pytest.approx(114.15)
        assert by_id["RL"].base_elevation == 110.0
        seg, missing = by_id["BLG"].line_segments
        assert seg.base_elevation == 120.0
        assert missing.base_elevation is None
        assert by_id["BLG"].base_elevation == 120.0
