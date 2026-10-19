"""Edge-case tests for visualization.py — fallback paths + ImportError guards.

The main test_visualization.py exercises the happy path when matplotlib
+ folium are installed. These tests cover:

- ImportError branches when HAS_MATPLOTLIB / HAS_FOLIUM are False
- Scatter-plot fallbacks for <4-point data + all-zero concentrations
- Empty-data placeholder figures
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from pyaermod import visualization as viz
from pyaermod.visualization import AERMODVisualizer


class _FakeResults:
    """Minimal stand-in for AERMODResults so we can control get_concentrations()."""

    def __init__(self, df):
        self._df = df

    def get_concentrations(self, period):
        return self._df

    def get_max_concentration(self, period):
        if self._df is None or self._df.empty:
            return None
        idx = self._df["concentration"].idxmax()
        row = self._df.loc[idx]
        return {"x": row["x"], "y": row["y"], "value": row["concentration"]}


# ---------------------------------------------------------------------------
# ImportError guards
# ---------------------------------------------------------------------------

class TestMatplotlibMissing:
    def test_contour_raises_when_matplotlib_missing(self):
        v = AERMODVisualizer(_FakeResults(pd.DataFrame({
            "x": [0], "y": [0], "concentration": [1.0],
        })))
        with patch.object(viz, "HAS_MATPLOTLIB", False), pytest.raises(ImportError, match="matplotlib"):
            v.plot_contours(averaging_period="ANNUAL")

    def test_time_series_raises_when_matplotlib_missing(self):
        v = AERMODVisualizer(_FakeResults(pd.DataFrame({
            "x": [0], "y": [0], "concentration": [1.0],
        })))
        with patch.object(viz, "HAS_MATPLOTLIB", False), pytest.raises(ImportError, match="matplotlib"):
            v.plot_time_series(receptor_location=(0, 0))

    def test_comparison_raises_when_matplotlib_missing(self):
        v = AERMODVisualizer(_FakeResults(pd.DataFrame({
            "x": [0], "y": [0], "concentration": [1.0],
        })))
        with patch.object(viz, "HAS_MATPLOTLIB", False), pytest.raises(ImportError, match="matplotlib"):
            v.plot_comparison(
                results_list=[], labels=[], averaging_period="ANNUAL",
            )


class TestFoliumMissing:
    def test_interactive_map_raises_when_folium_missing(self):
        v = AERMODVisualizer(_FakeResults(pd.DataFrame({
            "x": [0], "y": [0], "concentration": [1.0],
        })))
        with patch.object(viz, "HAS_FOLIUM", False), pytest.raises(ImportError, match="folium"):
            v.create_interactive_map(averaging_period="ANNUAL")


# ---------------------------------------------------------------------------
# Fallback paths when input data is degenerate
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not viz.HAS_MATPLOTLIB, reason="matplotlib not installed")
class TestDegenerateData:
    def test_empty_dataframe_returns_placeholder_figure(self):
        v = AERMODVisualizer(_FakeResults(pd.DataFrame(columns=["x", "y", "concentration"])))
        fig = v.plot_contours(averaging_period="ANNUAL")
        assert fig is not None
        # The placeholder figure contains the "No concentration data" text
        texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert any("No concentration data" in t for t in texts)

    def test_none_dataframe_returns_placeholder_figure(self):
        v = AERMODVisualizer(_FakeResults(None))
        fig = v.plot_contours(averaging_period="ANNUAL")
        assert fig is not None

    def test_sparse_points_fall_back_to_scatter(self):
        # 3 points — below the 4-point threshold for cubic interpolation
        v = AERMODVisualizer(_FakeResults(pd.DataFrame({
            "x": [0, 100, 200],
            "y": [0, 100, 200],
            "concentration": [1.0, 2.0, 3.0],
        })))
        fig = v.plot_contours(averaging_period="ANNUAL")
        assert fig is not None
        # Scatter produces a PathCollection on the axes
        ax = fig.axes[0]
        assert len(ax.collections) >= 1

    def test_all_zero_concentrations_fall_back_to_scatter(self):
        # Non-collinear 2D arrangement so scipy.griddata can triangulate;
        # all-zero concentrations trigger the scatter-fallback branch.
        v = AERMODVisualizer(_FakeResults(pd.DataFrame({
            "x": [0, 100, 200, 0, 100, 200],
            "y": [0, 0, 0, 100, 100, 100],
            "concentration": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        })))
        fig = v.plot_contours(averaging_period="ANNUAL")
        assert fig is not None
        # Title should reflect the all-zero condition
        title = fig.axes[0].get_title()
        assert "zero" in title.lower() or "ANNUAL" in title


# ---------------------------------------------------------------------------
# Contours from a PLOTFILE, not the .out summary rows
# ---------------------------------------------------------------------------

_PLOTFILE_HEADER = """\
* AERMOD (26135 ):  test                                                                  10/15/26
* AERMET ( 24142):                                                                          12:44:36
* MODELING OPTIONS USED:   NonDFAULT  CONC  FLAT  RURAL
*         PLOT FILE OF  ANNUAL VALUES AVERAGED ACROSS     1 YEARS FOR SOURCE GROUP: ALL
*         FOR A TOTAL OF    25 RECEPTORS.
*         FORMAT: (3(1X,F13.5),3(1X,F8.2),3X,A5,2X,A8,2X,A10,A8)
*        X             Y      AVERAGE CONC    ZELEV    ZHILL    ZFLAG    AVE     GRP       NUM YRS  NET ID
* ____________  ____________  ____________   ______   ______   ______  ______  ________  ________  ________
"""


def _write_plotfile(path):
    lines = [_PLOTFILE_HEADER]
    for y in range(-200, 201, 100):
        for x in range(-200, 201, 100):
            conc = 10.0 if (x, y) == (100, 0) else 1.0 + 0.001 * (x + y + 400)
            lines.append(f" {x:13.5f} {y:13.5f} {conc:13.5f} {0:8.2f} {0:8.2f} {0:8.2f}"
                         f"   ANNUAL  ALL              1  GRID1   \n")
    path.write_text("".join(lines))
    return path


class TestContourFromPlotfile:
    """plot_contours contoured the ~10 summary-table rows of the .out file."""

    def test_plotfile_values_are_contoured(self, tmp_path):
        plt = pytest.importorskip("matplotlib.pyplot")
        path = _write_plotfile(tmp_path / "an.plt")
        summary = pd.DataFrame({"x": [0.0], "y": [0.0], "concentration": [99.0]})
        v = AERMODVisualizer(_FakeResults(summary))
        v.results.sources = []
        v.results.run_info = None
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")   # no summary-rows warning
            fig = v.plot_contours(plotfile=path, show_sources=False, title="t")
        ax = fig.axes[0]
        # the maximum is the PLOTFILE's, not the summary table's
        star = next(ln for ln in ax.lines if ln.get_marker() == "*")
        assert (star.get_xdata()[0], star.get_ydata()[0]) == (100.0, 0.0)
        plt.close(fig)

    def test_plotfile_frame_accepts_reader_result_and_frame(self, tmp_path):
        from pyaermod.aermod_outputs import read_plotfile
        path = _write_plotfile(tmp_path / "an.plt")
        a = viz.plotfile_frame(path)
        b = viz.plotfile_frame(read_plotfile(path))
        c = viz.plotfile_frame(read_plotfile(path).to_dataframe())
        assert len(a) == 25
        assert list(a.columns) == ["x", "y", "concentration"]
        pd.testing.assert_frame_equal(a, b)
        pd.testing.assert_frame_equal(a, c)
        with pytest.raises(TypeError):
            viz.plotfile_frame(42)

    def test_summary_rows_warn(self):
        pytest.importorskip("matplotlib.pyplot")
        df = pd.DataFrame({"x": [0.0, 100, 0, 100, 50], "y": [0.0, 0, 100, 100, 50],
                           "concentration": [1.0, 2, 3, 4, 5]})
        v = AERMODVisualizer(_FakeResults(df))
        v.results.sources = []
        v.results.run_info = type("Info", (), {"num_receptors": 1681})()
        with pytest.warns(UserWarning, match="not the run's 1681 receptors"):
            v.plot_contours(show_sources=False, title="t")
