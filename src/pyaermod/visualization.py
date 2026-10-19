"""
PyAERMOD Visualization Tools

Create publication-ready plots and interactive maps for AERMOD results.
"""

import logging
import warnings
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# Optional back-ends. Importing this module must stay silent on stdout /
# stderr: a missing optional dependency is recorded at DEBUG level only,
# and the user-facing signal is the ImportError (with an install hint)
# raised by the first feature that actually needs the package.
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.debug("matplotlib not installed; static plotting unavailable (pip install 'pyaermod[viz]')")

try:
    import folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False
    logger.debug("folium not installed; interactive maps unavailable (pip install 'pyaermod[viz]')")


def plotfile_frame(plotfile: Any):
    """A PLOTFILE's values at every receptor as ``x``, ``y``, ``concentration``.

    ``plotfile`` is a path to an AERMOD PLOTFILE, the result of
    :func:`pyaermod.aermod_outputs.read_plotfile`, or a DataFrame with
    ``x``/``y``/``concentration`` (or the PLOTFILE's ``X``/``Y`` and
    concentration column) already in it.
    """
    import pandas as pd

    from .aermod_outputs import AERMODAuxResult, read_plotfile

    if isinstance(plotfile, (str, Path)):
        plotfile = read_plotfile(plotfile)
    if isinstance(plotfile, AERMODAuxResult):
        column = plotfile.concentration_column
        if column is None:
            raise ValueError("the PLOTFILE has no concentration column")
        df = plotfile.to_dataframe().rename(
            columns={"X": "x", "Y": "y", column: "concentration"})
    elif isinstance(plotfile, pd.DataFrame):
        df = plotfile.rename(columns={"X": "x", "Y": "y"})
        if "concentration" not in df:
            conc = next((c for c in df.columns
                         if c.upper() in ("CONC", "AVERAGE_CONC")), None)
            if conc is None:
                raise ValueError("the DataFrame has no concentration column")
            df = df.rename(columns={conc: "concentration"})
    else:
        raise TypeError(
            "plotfile must be a path, a read_plotfile() result or a DataFrame, "
            f"not {type(plotfile).__name__}")
    df = df[["x", "y", "concentration"]].copy()
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().reset_index(drop=True)


class AERMODVisualizer:
    """
    Visualization tools for AERMOD results

    Creates contour plots, interactive maps, and publication-ready figures.
    """

    def __init__(self, results):
        """
        Initialize visualizer with AERMOD results

        Args:
            results: AERMODResults object from pyaermod.output_parser
        """
        self.results = results

    def plot_contours(self,
                     averaging_period: str = 'ANNUAL',
                     levels: Optional[List[float]] = None,
                     colormap: str = 'YlOrRd',
                     show_sources: bool = True,
                     show_max: bool = True,
                     title: Optional[str] = None,
                     units: str = 'ug/m³',
                     figsize: Tuple[int, int] = (12, 10),
                     save_path: Optional[Union[str, Path]] = None,
                     dpi: int = 300,
                     plotfile: Any = None) -> 'matplotlib.figure.Figure':  # noqa: F821
        """
        Create concentration contour plot

        :meth:`AERMODResults.get_concentrations` returns the rows of AERMOD's
        summary tables (the top ten or so receptors of each period), too few
        points to contour a grid. Pass the period's PLOTFILE as ``plotfile``
        to contour the value at every receptor; without it the plot is drawn
        from the summary rows, with a warning when they cover fewer
        receptors than the run has.

        Args:
            averaging_period: Averaging period to plot
            levels: Contour levels (auto-generated if None)
            colormap: Matplotlib colormap name
            show_sources: Whether to show source locations
            show_max: Whether to mark maximum concentration
            title: Plot title (auto-generated if None)
            units: Concentration units for label
            figsize: Figure size (width, height)
            save_path: Path to save figure (optional)
            dpi: Resolution for saved figure
            plotfile: The period's PLOTFILE (a path, a
                :func:`~pyaermod.aermod_outputs.read_plotfile` result or a
                DataFrame); its values at every receptor are contoured.

        Returns:
            matplotlib Figure object
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required for static plots. Install with: pip install matplotlib")

        # Get concentration data
        if plotfile is not None:
            df = plotfile_frame(plotfile)
        else:
            df = self.results.get_concentrations(averaging_period)
        if df is None or df.empty:
            fig, ax = plt.subplots(figsize=figsize)
            ax.text(0.5, 0.5, "No concentration data available",
                    ha="center", va="center", transform=ax.transAxes)
            return fig
        run_info = getattr(self.results, "run_info", None)
        n_receptors = getattr(run_info, "num_receptors", 0) or 0
        if plotfile is None and len(df) < n_receptors:
            warnings.warn(
                f"contouring the {len(df)} rows of the .out file's "
                f"{averaging_period} summary table, not the run's {n_receptors} "
                "receptors; pass "
                "the period's PLOTFILE as plotfile= to contour the full grid",
                UserWarning, stacklevel=2)
        if plotfile is None:
            max_info = self.results.get_max_concentration(averaging_period)
        else:
            peak = df.loc[df["concentration"].idxmax()]
            max_info = {"value": float(peak["concentration"]),
                        "x": float(peak["x"]), "y": float(peak["y"])}

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Prepare data for contouring
        x = df['x'].values
        y = df['y'].values
        conc = df['concentration'].values

        # Guard: need at least 4 non-collinear points for cubic interpolation
        if len(x) < 4:
            ax.scatter(x, y, c=conc, cmap=colormap, s=20)
            ax.set_title(title or f"{averaging_period} Concentration")
            return fig

        # Create grid for interpolation
        xi = np.linspace(x.min(), x.max(), 200)
        yi = np.linspace(y.min(), y.max(), 200)
        Xi, Yi = np.meshgrid(xi, yi)

        # Interpolate to regular grid
        from scipy.interpolate import griddata
        Zi = griddata((x, y), conc, (Xi, Yi), method='cubic')

        # Generate contour levels if not provided
        if levels is None:
            max_conc = conc.max()
            if max_conc <= 0:
                # All-zero or negative — fall back to scatter plot
                ax.scatter(x, y, c=conc, cmap=colormap, s=20)
                ax.set_title(title or f"{averaging_period} Concentration (all zero)")
                return fig
            levels = np.linspace(0, max_conc, 11)

        # Create filled contour plot
        contourf = ax.contourf(Xi, Yi, Zi, levels=levels, cmap=colormap, extend='max')

        # Add contour lines
        contour = ax.contour(Xi, Yi, Zi, levels=levels, colors='black', linewidths=0.5, alpha=0.3)
        ax.clabel(contour, inline=True, fontsize=8, fmt='%.1f')

        # Add colorbar
        plt.colorbar(contourf, ax=ax, label=f'Concentration ({units})')

        # Show source locations
        if show_sources and self.results.sources:
            sources_df = self.results.get_sources_dataframe()
            ax.scatter(sources_df['x'], sources_df['y'],
                      c='red', s=200, marker='^',
                      edgecolors='black', linewidths=2,
                      label='Sources', zorder=5)

            # Label sources
            for _, source in sources_df.iterrows():
                ax.annotate(source['source_id'],
                          xy=(source['x'], source['y']),
                          xytext=(10, 10), textcoords='offset points',
                          bbox=dict(boxstyle='round,pad=0.5', fc='white', alpha=0.8),
                          fontsize=9, fontweight='bold')

        # Mark maximum concentration
        if show_max:
            ax.plot(max_info['x'], max_info['y'],
                   'r*', markersize=30, markeredgecolor='black',
                   markeredgewidth=2, label='Maximum', zorder=6)

            ax.annotate(f"Max: {max_info['value']:.2f} {units}",
                       xy=(max_info['x'], max_info['y']),
                       xytext=(20, 20), textcoords='offset points',
                       bbox=dict(boxstyle='round,pad=0.7', fc='yellow', alpha=0.9),
                       fontsize=11, fontweight='bold',
                       arrowprops=dict(arrowstyle='->', lw=2))

        # Labels and title
        ax.set_xlabel('X Coordinate (m)', fontsize=12)
        ax.set_ylabel('Y Coordinate (m)', fontsize=12)

        if title is None:
            title = f'{averaging_period} Average Concentration\n{self.results.run_info.jobname}'
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

        # Grid
        ax.grid(True, alpha=0.3, linestyle='--')

        # Legend
        if show_sources or show_max:
            ax.legend(loc='best', fontsize=10, framealpha=0.9)

        # Aspect ratio
        ax.set_aspect('equal')

        plt.tight_layout()

        # Save if requested
        if save_path:
            plt.savefig(save_path, dpi=dpi, bbox_inches='tight')
            logger.info("Figure saved to: %s", save_path)

        return fig

    def create_interactive_map(self,
                              averaging_period: str = 'ANNUAL',
                              center: Optional[Tuple[float, float]] = None,
                              zoom_start: int = 13,
                              colormap: str = 'YlOrRd',
                              opacity: float = 0.6,
                              show_sources: bool = True,
                              show_max: bool = True,
                              basemap: str = 'OpenStreetMap',
                              save_path: Optional[Union[str, Path]] = None) -> 'folium.Map':
        """
        Create interactive Leaflet map

        Args:
            averaging_period: Averaging period to plot
            center: Map center (lat, lon) or None for auto
            zoom_start: Initial zoom level
            colormap: Colormap name
            opacity: Overlay opacity (0-1)
            show_sources: Show source markers
            show_max: Show maximum concentration marker
            basemap: Base map style
            save_path: Path to save HTML file

        Returns:
            folium.Map object
        """
        if not HAS_FOLIUM:
            raise ImportError("folium required for interactive maps. Install with: pip install folium")

        # Get concentration data
        df = self.results.get_concentrations(averaging_period)
        max_info = self.results.get_max_concentration(averaging_period)

        # Determine map center
        if center is None:
            center_x = (df['x'].min() + df['x'].max()) / 2
            center_y = (df['y'].min() + df['y'].max()) / 2
            center = (center_y, center_x)  # folium uses (lat, lon)

        # Create map
        m = folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles=basemap
        )

        # Add heat map
        heat_data = [[row['y'], row['x'], row['concentration']]
                    for _, row in df.iterrows()]

        from folium.plugins import HeatMap
        HeatMap(heat_data,
               min_opacity=opacity,
               max_val=df['concentration'].max(),
               radius=15,
               blur=25,
               gradient={0.0: 'blue', 0.5: 'yellow', 1.0: 'red'}
               ).add_to(m)

        # Add source markers
        if show_sources and self.results.sources:
            for source in self.results.sources:
                popup_parts = [
                    f"<b>{source.source_id}</b>",
                    f"Type: {source.source_type}",
                ]
                if source.stack_height is not None:
                    popup_parts.append(f"Height: {source.stack_height:.1f}m")
                if source.emission_rate is not None:
                    popup_parts.append(f"Rate: {source.emission_rate:.2f} g/s")
                folium.Marker(
                    location=[source.y_coord, source.x_coord],
                    popup="<br>".join(popup_parts),
                    icon=folium.Icon(color='red', icon='industry', prefix='fa'),
                    tooltip=source.source_id
                ).add_to(m)

        # Add maximum concentration marker
        if show_max:
            folium.Marker(
                location=[max_info['y'], max_info['x']],
                popup=f"<b>Maximum Concentration</b><br>"
                      f"{max_info['value']:.4f} {max_info['units']}<br>"
                      f"Period: {averaging_period}",
                icon=folium.Icon(color='purple', icon='star', prefix='fa'),
                tooltip=f"Max: {max_info['value']:.2f}"
            ).add_to(m)

        # Add layer control
        folium.LayerControl().add_to(m)

        # Save if requested
        if save_path:
            m.save(str(save_path))
            logger.info("Interactive map saved to: %s", save_path)

        return m

    def plot_time_series(self,
                        receptor_location: Tuple[float, float],
                        averaging_periods: Optional[List[str]] = None,
                        title: Optional[str] = None,
                        figsize: Tuple[int, int] = (12, 6),
                        save_path: Optional[Union[str, Path]] = None) -> 'matplotlib.figure.Figure':  # noqa: F821
        """
        Plot concentration time series at a specific receptor

        Args:
            receptor_location: (x, y) coordinates
            averaging_periods: List of periods to plot
            title: Plot title
            figsize: Figure size
            save_path: Path to save figure

        Returns:
            matplotlib Figure object
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required. Install with: pip install matplotlib")

        fig, ax = plt.subplots(figsize=figsize)

        x, y = receptor_location

        if averaging_periods is None:
            averaging_periods = list(self.results.concentrations.keys())

        concentrations = []
        labels = []

        for period in averaging_periods:
            conc = self.results.get_concentration_at_point(x, y, period, tolerance=10.0)
            if conc is not None:
                concentrations.append(conc)
                labels.append(period)

        # Create bar plot
        ax.bar(range(len(labels)), concentrations, color='steelblue', edgecolor='black')
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)

        ax.set_xlabel('Averaging Period', fontsize=12)
        ax.set_ylabel('Concentration (ug/m³)', fontsize=12)

        if title is None:
            title = f'Concentrations at ({x:.0f}, {y:.0f})'
        ax.set_title(title, fontsize=14, fontweight='bold')

        ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        return fig

    def plot_comparison(self,
                       results_list: List,
                       labels: List[str],
                       averaging_period: str = 'ANNUAL',
                       metric: str = 'max',
                       title: Optional[str] = None,
                       figsize: Tuple[int, int] = (10, 6),
                       save_path: Optional[Union[str, Path]] = None) -> 'matplotlib.figure.Figure':  # noqa: F821
        """
        Compare multiple AERMOD runs

        Args:
            results_list: List of AERMODResults objects
            labels: Labels for each run
            averaging_period: Averaging period to compare
            metric: 'max', 'mean', or 'median'
            title: Plot title
            figsize: Figure size
            save_path: Path to save figure

        Returns:
            matplotlib Figure object
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required. Install with: pip install matplotlib")

        fig, ax = plt.subplots(figsize=figsize)

        values = []

        for results in results_list:
            df = results.get_concentrations(averaging_period)

            if metric == 'max':
                value = df['concentration'].max()
            elif metric == 'mean':
                value = df['concentration'].mean()
            elif metric == 'median':
                value = df['concentration'].median()
            else:
                raise ValueError(f"Unknown metric: {metric}")

            values.append(value)

        # Create bar plot
        bars = ax.bar(range(len(labels)), values, color='skyblue', edgecolor='black', linewidth=1.5)

        # Color the highest bar differently
        max_idx = values.index(max(values))
        bars[max_idx].set_color('coral')

        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right')

        ax.set_ylabel(f'{metric.capitalize()} Concentration (ug/m³)', fontsize=12)

        if title is None:
            title = f'Scenario Comparison - {averaging_period} {metric.capitalize()}'
        ax.set_title(title, fontsize=14, fontweight='bold')

        ax.grid(True, alpha=0.3, axis='y')

        # Add value labels on bars
        for _i, (bar, value) in enumerate(zip(bars, values)):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{value:.2f}',
                   ha='center', va='bottom', fontweight='bold')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        return fig


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def quick_plot(results,
              averaging_period: str = 'ANNUAL',
              save_path: Optional[str] = None,
              plotfile: Any = None) -> 'matplotlib.figure.Figure':  # noqa: F821
    """
    Quick contour plot with default settings

    Args:
        results: AERMODResults object
        averaging_period: Averaging period to plot
        save_path: Optional save path
        plotfile: The period's PLOTFILE, contoured at every receptor (see
            :meth:`AERMODVisualizer.plot_contours`)

    Returns:
        matplotlib Figure object
    """
    viz = AERMODVisualizer(results)
    return viz.plot_contours(averaging_period=averaging_period, save_path=save_path,
                             plotfile=plotfile)


def quick_map(results,
             averaging_period: str = 'ANNUAL',
             save_path: Optional[str] = None) -> 'folium.Map':
    """
    Quick interactive map with default settings

    Args:
        results: AERMODResults object
        averaging_period: Averaging period to plot
        save_path: Optional save path (HTML)

    Returns:
        folium.Map object
    """
    viz = AERMODVisualizer(results)
    return viz.create_interactive_map(averaging_period=averaging_period, save_path=save_path)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    from pyaermod.output_parser import parse_aermod_output

    if len(sys.argv) > 1:
        output_file = sys.argv[1]

        print(f"Creating visualizations for: {output_file}\n")

        # Parse results
        results = parse_aermod_output(output_file)

        # Create visualizer
        viz = AERMODVisualizer(results)

        # Create contour plot
        print("Creating contour plot...")
        fig = viz.plot_contours(save_path="concentrations_contour.png")
        print("  ✓ Saved: concentrations_contour.png")

        # Create interactive map
        if HAS_FOLIUM:
            print("\nCreating interactive map...")
            m = viz.create_interactive_map(save_path="concentrations_map.html")
            print("  ✓ Saved: concentrations_map.html")
        else:
            print("\nSkipping interactive map (folium not installed)")

        print("\nVisualizations complete!")

    else:
        print("PyAERMOD Visualization Tools")
        print("\nUsage:")
        print("  python -m pyaermod.visualization <output_file.out>")
        print("\nOr import and use:")
        print("  from pyaermod.visualization import AERMODVisualizer")
        print("  viz = AERMODVisualizer(results)")
        print("  viz.plot_contours(save_path='plot.png')")
        print("  viz.create_interactive_map(save_path='map.html')")
