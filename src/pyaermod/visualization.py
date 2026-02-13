"""
PyAERMOD Visualization Tools

Create publication-ready plots and interactive maps for AERMOD results.
"""

from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not installed. Static plotting unavailable.")

try:
    import folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False
    print("Warning: folium not installed. Interactive maps unavailable.")


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
                     dpi: int = 300) -> 'matplotlib.figure.Figure':  # noqa: F821
        """
        Create concentration contour plot

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

        Returns:
            matplotlib Figure object
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required for static plots. Install with: pip install matplotlib")

        # Get concentration data
        df = self.results.get_concentrations(averaging_period)
        max_info = self.results.get_max_concentration(averaging_period)

        # Create figure
        fig, ax = plt.subplots(figsize=figsize)

        # Prepare data for contouring
        x = df['x'].values
        y = df['y'].values
        conc = df['concentration'].values

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
            print(f"Figure saved to: {save_path}")

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
                folium.Marker(
                    location=[source.y_coord, source.x_coord],
                    popup=f"<b>{source.source_id}</b><br>"
                          f"Type: {source.source_type}<br>"
                          f"Height: {source.stack_height:.1f}m<br>"
                          f"Rate: {source.emission_rate:.2f} g/s",
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
            print(f"Interactive map saved to: {save_path}")

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
              save_path: Optional[str] = None) -> 'matplotlib.figure.Figure':  # noqa: F821
    """
    Quick contour plot with default settings

    Args:
        results: AERMODResults object
        averaging_period: Averaging period to plot
        save_path: Optional save path

    Returns:
        matplotlib Figure object
    """
    viz = AERMODVisualizer(results)
    return viz.plot_contours(averaging_period=averaging_period, save_path=save_path)


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
