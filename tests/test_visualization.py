"""
Unit tests for PyAERMOD visualization modules

Tests class instantiation, parameter validation, and basic method calls
using mock/synthetic data (no real AERMOD output required).
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import matplotlib
import numpy as np
import pandas as pd
import pytest

# We need to construct a mock AERMODResults for the visualizer
from pyaermod.output_parser import (
    AERMODResults,
    ConcentrationResult,
    ModelRunInfo,
    SourceSummary,
)

matplotlib.use("Agg")  # Non-interactive backend for testing

from pyaermod.advanced_viz import AdvancedVisualizer
from pyaermod.visualization import AERMODVisualizer, quick_map, quick_plot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_concentration_df():
    """Create a regular grid of synthetic concentrations"""
    xs = np.linspace(-500, 500, 21)
    ys = np.linspace(-500, 500, 21)
    X, Y = np.meshgrid(xs, ys)
    dist = np.sqrt(X**2 + Y**2) + 1
    conc = 10.0 / dist * 100
    return pd.DataFrame({
        "x": X.flatten(),
        "y": Y.flatten(),
        "concentration": conc.flatten(),
    })


@pytest.fixture
def sample_results(sample_concentration_df):
    """Create an AERMODResults with synthetic data"""
    df = sample_concentration_df
    max_idx = df["concentration"].idxmax()

    conc_result = ConcentrationResult(
        averaging_period="ANNUAL",
        data=df,
        max_value=df.loc[max_idx, "concentration"],
        max_location=(df.loc[max_idx, "x"], df.loc[max_idx, "y"]),
    )

    sources = [
        SourceSummary("STACK1", "POINT", 0.0, 0.0, 10.0,
                       stack_height=50.0, emission_rate=1.5),
    ]

    return AERMODResults(
        run_info=ModelRunInfo("24142", "VIZ_TEST"),
        sources=sources,
        receptors=[],
        concentrations={"ANNUAL": conc_result},
        output_file="test.out",
    )


@pytest.fixture
def advanced_viz_df():
    """DataFrame with X, Y, CONC columns for AdvancedVisualizer"""
    xs = np.linspace(-500, 500, 21)
    ys = np.linspace(-500, 500, 21)
    X, Y = np.meshgrid(xs, ys)
    dist = np.sqrt(X**2 + Y**2) + 1
    conc = 10.0 / dist * 100
    return pd.DataFrame({
        "X": X.flatten(),
        "Y": Y.flatten(),
        "CONC": conc.flatten(),
    })


# ---------------------------------------------------------------------------
# AERMODVisualizer tests
# ---------------------------------------------------------------------------

class TestAERMODVisualizerInit:
    """Test AERMODVisualizer instantiation"""

    def test_init(self, sample_results):
        viz = AERMODVisualizer(sample_results)
        assert viz.results is sample_results

    def test_init_stores_results(self, sample_results):
        viz = AERMODVisualizer(sample_results)
        assert viz.results.run_info.jobname == "VIZ_TEST"


class TestPlotContours:
    """Test contour plotting"""

    def test_plot_contours_returns_figure(self, sample_results):
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_contours(averaging_period="ANNUAL")
        assert fig is not None
        plt.close(fig)

    def test_plot_contours_custom_params(self, sample_results):
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_contours(
            averaging_period="ANNUAL",
            colormap="viridis",
            show_sources=True,
            show_max=True,
            title="Custom Title",
            units="ppb",
            figsize=(8, 6),
        )
        assert fig is not None
        plt.close(fig)

    def test_plot_contours_save(self, sample_results, tmp_path):
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        save_file = str(tmp_path / "contour.png")
        fig = viz.plot_contours(save_path=save_file)
        assert os.path.exists(save_file)
        plt.close(fig)

    def test_plot_contours_no_sources(self, sample_results):
        """Test plotting without source markers"""
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_contours(show_sources=False, show_max=False)
        assert fig is not None
        plt.close(fig)


class TestPlotComparison:
    """Test scenario comparison plotting"""

    def test_plot_comparison(self, sample_results):
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)

        # Create a second results set with different concentrations
        df2 = sample_results.get_concentrations("ANNUAL").copy()
        df2["concentration"] *= 0.5
        max_idx = df2["concentration"].idxmax()

        results2 = AERMODResults(
            run_info=ModelRunInfo("24142", "VIZ_TEST_2"),
            sources=sample_results.sources,
            receptors=[],
            concentrations={
                "ANNUAL": ConcentrationResult(
                    "ANNUAL", df2,
                    df2.loc[max_idx, "concentration"],
                    (df2.loc[max_idx, "x"], df2.loc[max_idx, "y"]),
                )
            },
            output_file="test2.out",
        )

        fig = viz.plot_comparison(
            results_list=[sample_results, results2],
            labels=["Scenario A", "Scenario B"],
            averaging_period="ANNUAL",
            metric="max",
        )
        assert fig is not None
        plt.close(fig)

    def test_plot_comparison_mean_metric(self, sample_results):
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_comparison(
            results_list=[sample_results],
            labels=["Baseline"],
            metric="mean",
        )
        assert fig is not None
        plt.close(fig)

    def test_plot_comparison_invalid_metric(self, sample_results):
        viz = AERMODVisualizer(sample_results)
        with pytest.raises(ValueError, match="Unknown metric"):
            viz.plot_comparison(
                results_list=[sample_results],
                labels=["Baseline"],
                metric="invalid",
            )


# ---------------------------------------------------------------------------
# AdvancedVisualizer tests
# ---------------------------------------------------------------------------

class TestAdvancedVisualizer3D:
    """Test 3D surface plotting"""

    def test_plot_3d_surface(self, advanced_viz_df):
        import matplotlib.pyplot as plt
        fig = AdvancedVisualizer.plot_3d_surface(advanced_viz_df)
        assert fig is not None
        plt.close(fig)

    def test_plot_3d_surface_custom_params(self, advanced_viz_df):
        import matplotlib.pyplot as plt
        fig = AdvancedVisualizer.plot_3d_surface(
            advanced_viz_df,
            title="Custom 3D",
            units="ppb",
            colormap="viridis",
            elevation_angle=45,
            azimuth_angle=60,
        )
        assert fig is not None
        plt.close(fig)

    def test_plot_3d_surface_save(self, advanced_viz_df, tmp_path):
        import matplotlib.pyplot as plt
        save_file = str(tmp_path / "surface3d.png")
        fig = AdvancedVisualizer.plot_3d_surface(
            advanced_viz_df, save_path=save_file
        )
        assert os.path.exists(save_file)
        plt.close(fig)


class TestAdvancedVisualizerWindRose:
    """Test wind rose plotting"""

    def test_plot_wind_rose(self):
        import matplotlib.pyplot as plt
        np.random.seed(42)
        speeds = np.random.gamma(3, 2, 500)
        directions = np.random.normal(180, 60, 500) % 360

        fig = AdvancedVisualizer.plot_wind_rose(speeds, directions)
        assert fig is not None
        plt.close(fig)

    def test_plot_wind_rose_custom_bins(self):
        import matplotlib.pyplot as plt
        np.random.seed(42)
        speeds = np.random.gamma(3, 2, 500)
        directions = np.random.uniform(0, 360, 500)

        fig = AdvancedVisualizer.plot_wind_rose(speeds, directions, bins=8)
        assert fig is not None
        plt.close(fig)


class TestAdvancedVisualizerProfile:
    """Test concentration profile plotting"""

    def test_plot_profile_x(self, advanced_viz_df):
        import matplotlib.pyplot as plt
        fig = AdvancedVisualizer.plot_concentration_profile(
            advanced_viz_df, direction="x", cross_coord=0.0
        )
        assert fig is not None
        plt.close(fig)

    def test_plot_profile_y(self, advanced_viz_df):
        import matplotlib.pyplot as plt
        fig = AdvancedVisualizer.plot_concentration_profile(
            advanced_viz_df, direction="y", cross_coord=0.0
        )
        assert fig is not None
        plt.close(fig)

    def test_plot_profile_invalid_coord(self, advanced_viz_df):
        """Profile at a coordinate with no data should raise ValueError"""
        with pytest.raises(ValueError, match="No data found"):
            AdvancedVisualizer.plot_concentration_profile(
                advanced_viz_df, direction="x", cross_coord=99999.0
            )


class TestAdvancedVisualizerComparison:
    """Test comparison grid"""

    def test_create_comparison_grid(self, advanced_viz_df):
        import matplotlib.pyplot as plt
        df2 = advanced_viz_df.copy()
        df2["CONC"] *= 0.5

        scenarios = {"Baseline": advanced_viz_df, "Reduced": df2}
        fig = AdvancedVisualizer.create_comparison_grid(scenarios)
        assert fig is not None
        plt.close(fig)

    def test_create_comparison_single(self, advanced_viz_df):
        import matplotlib.pyplot as plt
        scenarios = {"Only": advanced_viz_df}
        fig = AdvancedVisualizer.create_comparison_grid(scenarios)
        assert fig is not None
        plt.close(fig)


# ---------------------------------------------------------------------------
# Interactive map tests (folium)
# ---------------------------------------------------------------------------

class TestCreateInteractiveMap:
    """Test create_interactive_map() (visualization.py lines 194-259)."""

    def test_returns_map(self, sample_results):
        """create_interactive_map returns a folium Map object."""
        folium = pytest.importorskip("folium")
        viz = AERMODVisualizer(sample_results)
        m = viz.create_interactive_map(averaging_period="ANNUAL")
        assert isinstance(m, folium.Map)

    def test_custom_center(self, sample_results):
        """Explicit center/zoom_start are respected."""
        pytest.importorskip("folium")
        viz = AERMODVisualizer(sample_results)
        m = viz.create_interactive_map(
            averaging_period="ANNUAL",
            center=(40.0, -74.0),
            zoom_start=10,
        )
        assert m is not None

    def test_no_sources_no_max(self, sample_results):
        """Map can be created without source/max markers."""
        pytest.importorskip("folium")
        viz = AERMODVisualizer(sample_results)
        m = viz.create_interactive_map(
            averaging_period="ANNUAL",
            show_sources=False,
            show_max=False,
        )
        assert m is not None

    def test_save_html(self, sample_results, tmp_path):
        """save_path writes an HTML file."""
        pytest.importorskip("folium")
        viz = AERMODVisualizer(sample_results)
        save_file = tmp_path / "map.html"
        m = viz.create_interactive_map(
            averaging_period="ANNUAL",
            save_path=str(save_file),
        )
        assert save_file.exists()
        assert save_file.stat().st_size > 100


# ---------------------------------------------------------------------------
# Time series tests
# ---------------------------------------------------------------------------

class TestPlotTimeSeries:
    """Test plot_time_series() (visualization.py lines 280-318)."""

    def test_returns_figure(self, sample_results):
        """plot_time_series returns a matplotlib Figure."""
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_time_series(receptor_location=(0.0, 0.0))
        assert fig is not None
        plt.close(fig)

    def test_custom_title(self, sample_results):
        """Custom title parameter is accepted."""
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_time_series(
            receptor_location=(0.0, 0.0),
            title="My Custom Title",
        )
        assert fig is not None
        plt.close(fig)

    def test_save(self, sample_results, tmp_path):
        """save_path writes a PNG file."""
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        save_file = str(tmp_path / "timeseries.png")
        fig = viz.plot_time_series(
            receptor_location=(0.0, 0.0),
            save_path=save_file,
        )
        assert os.path.exists(save_file)
        assert os.path.getsize(save_file) > 100
        plt.close(fig)


# ---------------------------------------------------------------------------
# Comparison metric + save tests
# ---------------------------------------------------------------------------

class TestPlotComparisonExtended:
    """Additional plot_comparison tests (median metric, save_path)."""

    def test_plot_comparison_median_metric(self, sample_results):
        """metric='median' computes median concentration."""
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_comparison(
            results_list=[sample_results],
            labels=["Baseline"],
            averaging_period="ANNUAL",
            metric="median",
        )
        assert fig is not None
        plt.close(fig)

    def test_plot_comparison_save(self, sample_results, tmp_path):
        """save_path writes a file."""
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        save_file = str(tmp_path / "comparison.png")
        fig = viz.plot_comparison(
            results_list=[sample_results],
            labels=["Baseline"],
            save_path=save_file,
        )
        assert os.path.exists(save_file)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Quick map convenience function tests
# ---------------------------------------------------------------------------

class TestQuickMap:
    """Test the quick_map() convenience function."""

    def test_quick_map_returns_map(self, sample_results):
        """quick_map returns a folium Map."""
        folium = pytest.importorskip("folium")
        m = quick_map(sample_results, averaging_period="ANNUAL")
        assert isinstance(m, folium.Map)

    def test_quick_map_save(self, sample_results, tmp_path):
        """quick_map with save_path writes HTML file."""
        pytest.importorskip("folium")
        save_file = tmp_path / "quick_map.html"
        m = quick_map(
            sample_results,
            averaging_period="ANNUAL",
            save_path=str(save_file),
        )
        assert save_file.exists()


# ---------------------------------------------------------------------------
# Animation tests (advanced_viz.py)
# ---------------------------------------------------------------------------

class TestAdvancedVisualizerAnimation:
    """Test plot_time_series_animation (advanced_viz.py lines 320-391)."""

    def test_animation_creation(self, advanced_viz_df):
        """Two DataFrames + timestamps creates animation object."""
        import matplotlib.pyplot as plt
        df2 = advanced_viz_df.copy()
        df2["CONC"] *= 1.5

        anim = AdvancedVisualizer.plot_time_series_animation(
            dataframes=[advanced_viz_df, df2],
            timestamps=["T1", "T2"],
            interval=200,
        )
        assert anim is not None
        plt.close("all")

    def test_animation_save_gif(self, advanced_viz_df, tmp_path):
        """save_path produces a GIF file (requires pillow)."""
        pytest.importorskip("PIL")
        import matplotlib.pyplot as plt
        df2 = advanced_viz_df.copy()
        df2["CONC"] *= 1.5

        save_file = str(tmp_path / "anim.gif")
        anim = AdvancedVisualizer.plot_time_series_animation(
            dataframes=[advanced_viz_df, df2],
            timestamps=["T1", "T2"],
            save_path=save_file,
        )
        assert os.path.exists(save_file)
        assert os.path.getsize(save_file) > 100
        plt.close("all")

    def test_animation_mismatched_lengths(self, advanced_viz_df):
        """ValueError when len(dataframes) != len(timestamps)."""
        with pytest.raises(ValueError, match="timestamps"):
            AdvancedVisualizer.plot_time_series_animation(
                dataframes=[advanced_viz_df],
                timestamps=["T1", "T2"],
            )

    def test_comparison_grid_save(self, advanced_viz_df, tmp_path):
        """Comparison grid with save_path writes a file."""
        import matplotlib.pyplot as plt
        save_file = str(tmp_path / "grid.png")
        scenarios = {"A": advanced_viz_df}
        fig = AdvancedVisualizer.create_comparison_grid(
            scenarios, save_path=save_file
        )
        assert os.path.exists(save_file)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Additional coverage tests — quick_plot, plot_contours save to file
# ---------------------------------------------------------------------------


class TestQuickPlot:
    """Test the quick_plot() convenience function."""

    def test_quick_plot_returns_figure(self, sample_results):
        import matplotlib.pyplot as plt
        fig = quick_plot(sample_results, averaging_period="ANNUAL")
        assert fig is not None
        assert hasattr(fig, "savefig")  # It is a matplotlib Figure
        plt.close(fig)

    def test_quick_plot_save_to_file(self, sample_results, tmp_path):
        import matplotlib.pyplot as plt
        save_file = str(tmp_path / "quick_plot_output.png")
        fig = quick_plot(sample_results, averaging_period="ANNUAL", save_path=save_file)
        assert os.path.exists(save_file)
        assert os.path.getsize(save_file) > 0
        plt.close(fig)


class TestPlotContoursSaveFile:
    """Test plot_contours saving to various file formats via tmp_path."""

    def test_plot_contours_save_png(self, sample_results, tmp_path):
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        save_file = str(tmp_path / "contour_test.png")
        fig = viz.plot_contours(averaging_period="ANNUAL", save_path=save_file)
        assert os.path.exists(save_file)
        assert os.path.getsize(save_file) > 100  # non-trivial file
        plt.close(fig)

    def test_plot_contours_save_pdf(self, sample_results, tmp_path):
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        save_file = str(tmp_path / "contour_test.pdf")
        fig = viz.plot_contours(averaging_period="ANNUAL", save_path=save_file, dpi=72)
        assert os.path.exists(save_file)
        plt.close(fig)

    def test_plot_contours_custom_levels(self, sample_results):
        """Test with explicit contour levels."""
        import matplotlib.pyplot as plt
        viz = AERMODVisualizer(sample_results)
        fig = viz.plot_contours(averaging_period="ANNUAL", levels=[0, 50, 100, 200, 500, 1000])
        assert fig is not None
        plt.close(fig)
