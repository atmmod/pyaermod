"""The receptor elevation fields AERMOD reads under each terrain and
flagpole option.

From AERMOD v26135: reset.f RECART (GRIDCART ELEV / HILL / FLAG rows;
W214, E218, W216), reset.f DISCAR (DISCCART fields; W228, W229) and
coset.f FLAGDF (a bare FLAGPOLE). The same decks run on the binary in
tests/test_receptor_deck_acceptance.py.
"""

from __future__ import annotations

import logging

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    MeteorologyPathway,
    OutputPathway,
    SourcePathway,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.pathways import ControlPathway, TerrainType
from pyaermod.receptors import CartesianGrid, DiscreteReceptor, ReceptorPathway
from pyaermod.sources import PointSource

from .test_control_debug_depletion import _ctl, _deck, _lines

GRID = dict(x_init=-500.0, x_num=3, x_delta=500.0, y_init=-500.0, y_num=2, y_delta=500.0)


def _project(control: ControlPathway, receptors: ReceptorPathway) -> AERMODProject:
    return AERMODProject(
        control=control,
        sources=SourcePathway(sources=[PointSource("S1", 0.0, 0.0, stack_height=20.0)]),
        receptors=receptors,
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )



# ---------------------------------------------------------------------------
# GRIDCART ELEV / HILL / FLAG rows
# ---------------------------------------------------------------------------

class TestCartesianGridRows:
    def test_elevated_grid_gets_elev_and_hill_rows(self):
        text = CartesianGrid(**GRID, z_elev=12.5, z_hill=40.25).to_aermod_input(elevated=True)
        assert _lines(text, "GRIDCART")[1:5] == [
            "GRID1    ELEV      1  3*12.5",
            "GRID1    ELEV      2  3*12.5",
            "GRID1    HILL      1  3*40.25",
            "GRID1    HILL      2  3*40.25",
        ]

    def test_default_grid_gets_zero_rows(self):
        text = CartesianGrid(**GRID).to_aermod_input(elevated=True)
        assert "GRID1    ELEV      1  3*0" in text and "GRID1    HILL      2  3*0" in text

    def test_one_given_set_is_not_completed_from_the_grid_wide_value(self):
        # ELEV rows without HILL rows are RECART's E218 on the original
        # deck; filling HILL with z_hill made the rewrite run with every
        # hill height 0 (review case g1_elev_only_rows).
        elevations = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        text = CartesianGrid(**GRID, z_hill=7.0, grid_elevations=elevations).to_aermod_input(elevated=True)
        assert "GRID1    ELEV      1       1.0      2.0      3.0" in text
        assert "HILL" not in text
        text = CartesianGrid(**GRID, z_elev=7.0, grid_hills=elevations).to_aermod_input(elevated=True)
        assert "HILL" in text and "ELEV" not in text

    def test_elev_rows_without_hill_rows_read_back_without_hill_rows(self):
        re_block = ("   GRIDCART  G1 STA\n      XYINC  0.0 3 100.0  0.0 1 100.0\n"
                    "   GRIDCART  G1 ELEV 1 50.0 120.0 200.0\n   GRIDCART  G1 END\n")
        project = parse_aermod_input(_deck(modelopt="CONC ELEV", re=re_block))
        rewritten = project.to_aermod_input(validate=False)
        assert [ln for ln in rewritten.splitlines() if " ELEV " in ln]
        assert not [ln for ln in rewritten.splitlines() if " HILL " in ln]

    @pytest.mark.parametrize(("value", "literal"), [
        (1e-05, "0.00001"),              # .10g gave 1e-05: STODBL E208
        (1e-12, "0.000000000001"),
        (2e10, "20000000000"),
        (1.5e15, "1500000000000000"),
        (123.456789012345, "123.456789012345"),  # .10g cut it to 123.456789
        (-3.25, "-3.25"),
        (10.0, "10"),
    ])
    def test_uniform_row_literal_is_fixed_point_and_exact(self, value, literal):
        text = CartesianGrid(**GRID, z_elev=value).to_aermod_input(elevated=True)
        assert f"GRID1    ELEV      1  3*{literal}" in text
        assert float(literal) == value

    def test_coordinate_lists_have_no_exponent_and_ten_digits(self):
        grid = CartesianGrid(x_points=[1e-05, 2e10, 0.30000000000000004, 500000.123456789], y_points=[0.0])
        assert _lines(grid.to_aermod_input(), "GRIDCART")[1] == (
            "GRID1    XPNTS  0.00001  20000000000  0.3  500000.1235")

    @pytest.mark.parametrize("elevated", [False, None])
    def test_flat_or_unknown_writes_only_given_rows(self, elevated):
        text = CartesianGrid(**GRID, z_elev=5.0, z_hill=9.0).to_aermod_input(elevated=elevated)
        assert "ELEV" not in text and "HILL" not in text

    def test_flag_rows_from_a_nonzero_z_flag_with_flagpole(self):
        text = CartesianGrid(**GRID, z_flag=2.0).to_aermod_input(elevated=False, flagpole=1.5)
        assert "GRID1    FLAG      1  3*2" in text

    def test_zero_z_flag_leaves_the_flagpole_default(self):
        # AERMOD gives every receptor the FLAGPOLE height (W216), and
        # EPA's FLAGPOLE decks read back unchanged.
        assert "FLAG" not in CartesianGrid(**GRID).to_aermod_input(elevated=False, flagpole=1.5)
        assert "FLAG" not in CartesianGrid(**GRID, z_flag=2.0).to_aermod_input(elevated=False)

    def test_uniform_rows_read_back_to_the_same_values(self):
        grid = CartesianGrid(**GRID, z_elev=123.456, z_hill=0.5)
        project = _project(_ctl(), ReceptorPathway(cartesian_grids=[grid]))
        back = parse_aermod_input(project.to_aermod_input(validate=False)).receptors.cartesian_grids[0]
        assert back.grid_elevations == [[123.456] * 3] * 2
        assert back.grid_hills == [[0.5] * 3] * 2


# ---------------------------------------------------------------------------
# DISCCART fields
# ---------------------------------------------------------------------------

def _disc(receptor: DiscreteReceptor, **context) -> list[str]:
    return receptor.to_aermod_input(**context).split()[1:]


class TestDiscreteReceptorFields:
    def test_elevated_writes_a_zero_hill_height(self):
        # "x y zelev" under ELEV was W228.
        assert _disc(DiscreteReceptor(1000.0, 0.0), elevated=True) == [
            "1000.0000", "0.0000", "0.00", "0.00"]

    def test_elevated_with_flagpole_writes_all_three(self):
        assert _disc(DiscreteReceptor(1.0, 2.0, 5.0, 30.0, 4.0), elevated=True, flagpole=1.5)[2:] == [
            "5.00", "30.00", "4.00"]

    def test_zero_z_flag_is_the_flagpole_height(self):
        assert _disc(DiscreteReceptor(1.0, 2.0, 5.0), elevated=True, flagpole=1.5)[2:] == [
            "5.00", "0.00", "1.50"]

    def test_flat_with_flagpole_puts_z_flag_where_aermod_reads_it(self):
        # DISCAR reads "x y zflag" under FLAT with FLAGPOLE: the old
        # "x y zelev" gave the receptor its elevation as flagpole height.
        assert _disc(DiscreteReceptor(1.0, 2.0, 100.0), elevated=False, flagpole=2.0)[2:] == ["2.00"]
        assert _disc(DiscreteReceptor(1.0, 2.0, 100.0, 0.0, 3.5), elevated=False, flagpole=2.0)[2:] == ["3.50"]

    @pytest.mark.parametrize("elevated", [False, None])
    def test_flat_or_unknown_keeps_the_old_line(self, elevated):
        assert _disc(DiscreteReceptor(1.0, 2.0, 5.0), elevated=elevated)[2:] == ["5.00"]
        assert _disc(DiscreteReceptor(1.0, 2.0, 5.0, 3.0), elevated=elevated)[2:] == ["5.00", "3.00", "0.00"]


class TestProjectContext:
    """AERMODProject hands the run's options to the RE writer."""

    def test_elevated_deck(self):
        control = _ctl(terrain_type=TerrainType.FLAT, regulatory_default=True)
        receptors = ReceptorPathway(cartesian_grids=[CartesianGrid(**GRID)],
                                    discrete_receptors=[DiscreteReceptor(1000.0, 0.0)])
        text = _project(control, receptors).to_aermod_input(validate=False)
        assert "GRID1    ELEV      2  3*0" in text and "GRID1    HILL      2  3*0" in text
        assert _lines(text, "DISCCART") == ["1000.0000       0.0000     0.00     0.00"]

    def test_flat_flagpole_deck_reads_back(self):
        control = _ctl(terrain_type=TerrainType.FLAT, regulatory_default=False,
                                 flag_pole_height=2.0)
        receptors = ReceptorPathway(discrete_receptors=[DiscreteReceptor(10.0, 20.0, z_flag=3.5)])
        back = parse_aermod_input(_project(control, receptors).to_aermod_input(validate=False))
        assert back.receptors.discrete_receptors[0].z_flag == 3.5
        assert back.receptors.discrete_receptors[0].z_elev == 0.0


class TestReaderFlagpole:
    def test_bare_flagpole_is_height_zero(self, caplog):
        # coset.f FLAGDF: a bare FLAGPOLE sets FLGPOL with height 0
        # (W205); dropping it moved the flagpole field of every DISCCART.
        with caplog.at_level(logging.WARNING):
            project = parse_aermod_input(_deck(co="   FLAGPOLE\n", re="   DISCCART  300.0  0.0  3.4\n"))
        assert project.control.flag_pole_height == 0.0
        receptor = project.receptors.discrete_receptors[0]
        assert (receptor.z_elev, receptor.z_flag) == (0.0, 3.4)
        rewritten = project.to_aermod_input(validate=False)
        assert _lines(rewritten, "FLAGPOLE") == ["0.00"]
        assert _lines(rewritten, "DISCCART") == ["300.0000       0.0000     3.40"]

    def test_flat_without_flagpole_third_field_is_elevation(self):
        project = parse_aermod_input(_deck(re="   DISCCART  300.0  0.0  3.4\n"))
        receptor = project.receptors.discrete_receptors[0]
        assert (receptor.z_elev, receptor.z_flag) == (3.4, 0.0)
