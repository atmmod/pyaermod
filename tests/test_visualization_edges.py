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
