"""
Receptors that share (x, y) at several flagpole heights (CO FLAGPOLE with one
GRIDCART network per height).

The writer, AERMOD and the file readers keep the heights; the (x, y)-keyed
convenience methods used to merge them without a word.
"""

import shutil
import warnings

import pandas as pd
import pytest

from pyaermod import visualization as viz
from pyaermod.output_parser import AERMODResults, ConcentrationResult, ModelRunInfo
from pyaermod.postfile import PostfileParser

HEIGHTS = (0.0, 10.0, 25.0)
XS = (0.0, 100.0, 200.0)

_POSTFILE_HEADER = """\
* AERMOD ( 24142 ): Flagpole POSTFILE Run
* MODELING OPTIONS USED: CONC FLAT
* AVERTIME: ANNUAL
* POLLUTID: SO2
* SRCGROUP: ALL
* POSTFILE OUTPUT FOR SOURCE GROUP: ALL
*         X             Y      AVERAGE CONC   ZELEV  ZHILL  ZFLAG    AVE     GRP       DATE
"""

_PLOTFILE_HEADER = """\
* AERMOD ( 24142 ): Flagpole PLOTFILE Run
* AERMET ( 24142):                                                                          12:44:36
* MODELING OPTIONS USED:   NonDFAULT  CONC  FLAT  RURAL
*         PLOT FILE OF  ANNUAL VALUES AVERAGED ACROSS     1 YEARS FOR SOURCE GROUP: ALL
*         FOR A TOTAL OF     9 RECEPTORS.
*         FORMAT: (3(1X,F13.5),3(1X,F8.2),3X,A5,2X,A8,2X,A10,A8)
*        X             Y      AVERAGE CONC    ZELEV    ZHILL    ZFLAG    AVE     GRP       NUM YRS  NET ID
* ____________  ____________  ____________   ______   ______   ______  ______  ________  ________  ________
"""


def _conc(x, y, z):
    """Different at every (x, y, height) so a merge shows."""
    return 1.0 + x / 100.0 + y / 1000.0 + z


def _postfile_text():
    rows = []
    for z in HEIGHTS:
        for x in XS:
            rows.append(f"   {x:8.2f}   {0.0:8.2f}   {_conc(x, 0.0, z):.5E}   0.00   0.00 {z:7.2f}"
                        "   ANNUAL    ALL    26010101\n")
    return _POSTFILE_HEADER + "".join(rows)


def _plotfile_text(heights=HEIGHTS):
    rows = []
    for z in heights:
        for x in XS:
            rows.append(f" {x:13.5f} {0.0:13.5f} {_conc(x, 0.0, z):13.5f} {0:8.2f} {0:8.2f} "
                        f"{z:8.2f}   ANNUAL  ALL              1  GRID1   \n")
    return _PLOTFILE_HEADER + "".join(rows)


@pytest.fixture
def postfile(tmp_path):
    path = tmp_path / "flag.pst"
    path.write_text(_postfile_text())
    return PostfileParser(path).parse()


@pytest.fixture
def plotfile(tmp_path):
    path = tmp_path / "flag.plt"
    path.write_text(_plotfile_text())
    return path


def _results_with(rows):
    df = pd.DataFrame(rows, columns=["x", "y", "concentration", "zflag"])
    return AERMODResults(
        run_info=ModelRunInfo("24142", "TEST"),
        sources=[], receptors=[], output_file="t.out",
        concentrations={"ANNUAL": ConcentrationResult(
            averaging_period="ANNUAL", data=df, max_value=float(df["concentration"].max()),
            max_location=(0.0, 0.0))})


# ---------------------------------------------------------------------------
# PostfileResult
# ---------------------------------------------------------------------------

class TestPostfileMaxByReceptor:
    def test_keeps_one_row_per_receptor_and_height(self, postfile):
        out = postfile.get_max_by_receptor()
        assert len(out) == len(XS) * len(HEIGHTS)
        assert {"x", "y", "zflag", "zelev", "zhill", "concentration"} <= set(out.columns)
        row = out[(out["x"] == 100.0) & (out["zflag"] == 10.0)].iloc[0]
        assert row["concentration"] == pytest.approx(_conc(100.0, 0.0, 10.0))

    def test_one_height_is_unchanged(self, tmp_path):
        path = tmp_path / "one.pst"
        path.write_text(_POSTFILE_HEADER + "".join(
            f"   {x:8.2f}   0.00   {x + 1.0:.5E}   0.00   0.00    0.00   ANNUAL    ALL    26010101\n"
            for x in XS))
        out = PostfileParser(path).parse().get_max_by_receptor()
        assert list(out.columns) == ["x", "y", "concentration"]
        assert len(out) == len(XS)

    def test_a_single_nonzero_height_is_still_one_row_per_receptor(self, tmp_path):
        path = tmp_path / "one.pst"
        path.write_text(_POSTFILE_HEADER + "".join(
            f"   {x:8.2f}   0.00   {x + 1.0:.5E}   0.00   0.00   10.00   ANNUAL    ALL    26010101\n"
            for x in XS))
        out = PostfileParser(path).parse().get_max_by_receptor()
        assert len(out) == len(XS)


class TestPostfileGetReceptor:
    def test_zflag_selects_one_height(self, postfile):
        rec = postfile.get_receptor(100.0, 0.0, zflag=25.0)
        assert list(rec["zflag"]) == [25.0]
        assert rec["concentration"].iloc[0] == pytest.approx(_conc(100.0, 0.0, 25.0))

    def test_zflag_tolerance(self, postfile):
        assert len(postfile.get_receptor(100.0, 0.0, zflag=10.3, tolerance=0.5)) == 1
        assert postfile.get_receptor(100.0, 0.0, zflag=12.0).empty

    def test_several_heights_without_zflag_warn_and_still_return_all(self, postfile):
        with pytest.warns(UserWarning, match=r"0\.0.*10\.0.*25\.0"):
            rec = postfile.get_receptor(100.0, 0.0)
        assert len(rec) == len(HEIGHTS)

    def test_one_height_does_not_warn(self, postfile):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert len(postfile.get_receptor(100.0, 0.0, zflag=0.0)) == 1


# ---------------------------------------------------------------------------
# AERMODResults.get_concentration_at_point
# ---------------------------------------------------------------------------

class TestConcentrationAtPoint:
    ROWS = [(0.0, 0.0, 5.0, 0.0), (0.0, 0.0, 3.0, 10.0), (0.0, 0.0, 1.0, 25.0)]

    def test_zflag_picks_the_height(self):
        r = _results_with(self.ROWS)
        assert r.get_concentration_at_point(0.0, 0.0, "ANNUAL", zflag=10.0) == 3.0
        assert r.get_concentration_at_point(0.0, 0.0, "ANNUAL", zflag=25.0) == 1.0

    def test_zflag_with_no_such_height_is_none(self):
        r = _results_with(self.ROWS)
        assert r.get_concentration_at_point(0.0, 0.0, "ANNUAL", zflag=99.0) is None

    def test_several_heights_without_zflag_warn(self):
        r = _results_with(self.ROWS)
        with pytest.warns(UserWarning, match=r"0\.0.*10\.0.*25\.0"):
            value = r.get_concentration_at_point(0.0, 0.0, "ANNUAL")
        assert value == 5.0   # unchanged: the first match

    def test_one_height_does_not_warn(self):
        r = _results_with(self.ROWS[:1])
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert r.get_concentration_at_point(0.0, 0.0, "ANNUAL") == 5.0

    def test_frame_without_zflag_column_still_works(self):
        df = pd.DataFrame({"x": [0.0], "y": [0.0], "concentration": [2.0]})
        r = _results_with([(0.0, 0.0, 2.0, 0.0)])
        r.concentrations["ANNUAL"].data = df
        assert r.get_concentration_at_point(0.0, 0.0, "ANNUAL") == 2.0
        assert r.get_concentration_at_point(0.0, 0.0, "ANNUAL", zflag=0.0) == 2.0


# ---------------------------------------------------------------------------
# plotfile_frame / plot_contours / quick_plot
# ---------------------------------------------------------------------------

class TestPlotfileFrame:
    def test_several_heights_need_zflag(self, plotfile):
        with pytest.raises(ValueError, match="zflag="):
            viz.plotfile_frame(plotfile)

    def test_zflag_selects_one_height(self, plotfile):
        df = viz.plotfile_frame(plotfile, zflag=10.0)
        assert list(df.columns) == ["x", "y", "concentration"]
        assert len(df) == len(XS)
        assert list(df["concentration"]) == pytest.approx([_conc(x, 0.0, 10.0) for x in XS])

    def test_zflag_not_in_file_is_an_error_naming_the_heights(self, plotfile):
        with pytest.raises(ValueError, match=r"25\.0"):
            viz.plotfile_frame(plotfile, zflag=99.0)

    def test_one_height_needs_no_zflag(self, tmp_path):
        path = tmp_path / "one.plt"
        path.write_text(_plotfile_text(heights=(10.0,)))
        assert len(viz.plotfile_frame(path)) == len(XS)

    def test_frame_without_zflag_column_is_accepted(self):
        df = pd.DataFrame({"x": [0.0, 1.0], "y": [0.0, 0.0], "concentration": [1.0, 2.0]})
        assert len(viz.plotfile_frame(df)) == 2

    def test_dataframe_with_heights(self, plotfile):
        from pyaermod.aermod_outputs import read_plotfile
        frame = read_plotfile(plotfile).to_dataframe()
        with pytest.raises(ValueError, match="zflag="):
            viz.plotfile_frame(frame)
        assert len(viz.plotfile_frame(frame, zflag=0.0)) == len(XS)


class TestContourPlotfileHeights:
    def _viz(self):
        class _R:
            sources = []
            run_info = None

            def get_concentrations(self, period):
                return None
        return viz.AERMODVisualizer(_R())

    def test_plot_contours_threads_zflag(self, tmp_path):
        plt = pytest.importorskip("matplotlib.pyplot")
        path = tmp_path / "flag.plt"
        # a 3x3 grid at two heights
        rows = []
        for z in (0.0, 10.0):
            for y in XS:
                for x in XS:
                    rows.append(f" {x:13.5f} {y:13.5f} {_conc(x, y, z):13.5f} {0:8.2f} {0:8.2f} "
                                f"{z:8.2f}   ANNUAL  ALL              1  GRID1   \n")
        path.write_text(_PLOTFILE_HEADER + "".join(rows))
        v = self._viz()
        with pytest.raises(ValueError, match="zflag="):
            v.plot_contours(plotfile=path, show_sources=False, title="t")
        fig = v.plot_contours(plotfile=path, zflag=10.0, show_sources=False, title="t")
        star = next(ln for ln in fig.axes[0].lines if ln.get_marker() == "*")
        assert star.get_ydata()[0] == 200.0
        plt.close(fig)

    def test_quick_plot_threads_zflag(self, tmp_path):
        plt = pytest.importorskip("matplotlib.pyplot")
        path = tmp_path / "flag.plt"
        rows = [f" {x:13.5f} {y:13.5f} {_conc(x, y, z):13.5f} {0:8.2f} {0:8.2f} "
                f"{z:8.2f}   ANNUAL  ALL              1  GRID1   \n"
                for z in (0.0, 10.0) for y in XS for x in XS]
        path.write_text(_PLOTFILE_HEADER + "".join(rows))

        class _R:
            sources = []
            run_info = type("Info", (), {"jobname": "t", "num_receptors": 0})()

            def get_concentrations(self, period):
                return None
        with pytest.raises(ValueError, match="zflag="):
            viz.quick_plot(_R(), plotfile=path)
        fig = viz.quick_plot(_R(), plotfile=path, zflag=0.0)
        assert fig is not None
        plt.close(fig)


# ---------------------------------------------------------------------------
# A real AERMOD run: CO FLAGPOLE with one GRIDCART per height
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("aermod") is None, reason="aermod not on PATH")
class TestRealFlagpoleRun:
    def test_plotfile_keeps_heights_and_lookups_respect_them(self, tmp_path):
        from pathlib import Path

        from pyaermod import (
            AERMODProject,
            CartesianGrid,
            ControlPathway,
            MeteorologyPathway,
            OutputPathway,
            PointSource,
            PollutantType,
            ReceptorPathway,
            SourcePathway,
            TerrainType,
            run_aermod,
        )
        from pyaermod.aermod_outputs import read_plotfile

        met = Path(__file__).parent / "fixtures" / "epa_official"
        control = ControlPathway(
            title_one="flagpole heights", pollutant_id=PollutantType.SO2,
            averaging_periods=["PERIOD"], terrain_type=TerrainType.FLAT,
            regulatory_default=False, flag_pole_height=0.0)
        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STACK1", x_coord=0.0, y_coord=0.0, stack_height=20.0,
            stack_temp=400.0, exit_velocity=10.0, stack_diameter=1.0, emission_rate=1.0))
        receptors = ReceptorPathway()
        for name, z in (("LOW", 0.0), ("HIGH", 30.0)):
            receptors.add_cartesian_grid(CartesianGrid(
                grid_name=name, x_init=100.0, x_num=3, x_delta=100.0,
                y_init=-100.0, y_num=3, y_delta=100.0, z_flag=z))
        meteorology = MeteorologyPathway(
            surface_file=str(met / "AERMET2.SFC"), profile_file=str(met / "AERMET2.PFL"),
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988, profile_base_elevation=1.8)
        output = OutputPathway(period_plot_files="flag")
        project = AERMODProject(control=control, sources=sources, receptors=receptors,
                                meteorology=meteorology, output=output)
        inp = project.write(tmp_path / "flag.inp")
        result = run_aermod(inp)
        assert result.success, result.error_message

        plot = tmp_path / output.period_plot_file_names(control.averaging_periods)["PERIOD"]
        frame = read_plotfile(plot).to_dataframe()
        assert sorted(frame["ZFLAG"].unique()) == [0.0, 30.0]
        assert len(frame) == 18

        with pytest.raises(ValueError, match="zflag="):
            viz.plotfile_frame(plot)
        low = viz.plotfile_frame(plot, zflag=0.0)
        high = viz.plotfile_frame(plot, zflag=30.0)
        assert len(low) == len(high) == 9
        # a stack of 20 m puts different values 0 m and 30 m above ground
        assert not low["concentration"].reset_index(drop=True).equals(
            high["concentration"].reset_index(drop=True))
