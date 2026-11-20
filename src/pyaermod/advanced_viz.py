"""
PyAERMOD Advanced Visualization Tools

Advanced plotting capabilities including 3D visualizations, wind roses,
animations, and publication-quality figure generation.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers 3d projection
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    from matplotlib.animation import FuncAnimation, PillowWriter
    HAS_ANIMATION = True
except ImportError:
    HAS_ANIMATION = False


def _grid_from_xy(df: pd.DataFrame, x_unique=None, y_unique=None):
    """Lay ``CONC`` out on the grid of its X and Y values.

    Each value goes to the cell of its own (X, Y), whatever order the rows
    come in (x-major, y-major, shuffled); a receptor the table lacks leaves
    NaN. ``x_unique``/``y_unique`` fix the axes (default: the table's own
    sorted X and Y values). Returns ``(x_unique, y_unique, Z)`` with ``Z``
    shaped ``(len(y_unique), len(x_unique))``.
    """
    x = df['X'].values
    y = df['Y'].values
    if x_unique is None:
        x_unique = np.unique(x)
    if y_unique is None:
        y_unique = np.unique(y)
    Z = np.full((len(y_unique), len(x_unique)), np.nan)
    Z[np.searchsorted(y_unique, y), np.searchsorted(x_unique, x)] = df['CONC'].values
    return x_unique, y_unique, Z


class AdvancedVisualizer:
    """
    Advanced visualization tools for AERMOD results

    Provides 3D plotting, wind roses, animations, and advanced analysis plots.
    """

    @staticmethod
    def plot_3d_surface(df: pd.DataFrame,
                       title: str = "3D Concentration Surface",
                       units: str = "μg/m³",
                       colormap: str = 'plasma',
                       figsize: Tuple[int, int] = (14, 10),
                       elevation_angle: int = 30,
                       azimuth_angle: int = 45,
                       save_path: Optional[str] = None):
        """
        Create 3D surface plot of concentration field

        Args:
            df: DataFrame with X, Y, CONC columns
            title: Plot title
            units: Concentration units
            colormap: Matplotlib colormap
            figsize: Figure size
            elevation_angle: Viewing elevation (degrees)
            azimuth_angle: Viewing azimuth (degrees)
            save_path: Optional save path
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required. Install with: pip install matplotlib")

        # Create grid
        x_unique, y_unique, Z = _grid_from_xy(df)
        X, Y = np.meshgrid(x_unique, y_unique)

        # Create figure
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111, projection='3d')

        # Surface plot
        surf = ax.plot_surface(X, Y, Z, cmap=colormap,
                              linewidth=0, antialiased=True,
                              alpha=0.9, edgecolor='none')

        # Add contour lines at base
        ax.contour(X, Y, Z, zdir='z', offset=Z.min(),
                  cmap='Greys', alpha=0.5, linewidths=0.5)

        # Colorbar
        cbar = fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10, pad=0.1)
        cbar.set_label(f'Concentration ({units})', fontsize=11, fontweight='bold')

        # Labels and title
        ax.set_xlabel('Easting (m)', fontsize=11, fontweight='bold', labelpad=10)
        ax.set_ylabel('Northing (m)', fontsize=11, fontweight='bold', labelpad=10)
        ax.set_zlabel(f'Concentration ({units})', fontsize=11, fontweight='bold', labelpad=10)
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

        # Set viewing angle
        ax.view_init(elev=elevation_angle, azim=azimuth_angle)

        # Grid
        ax.grid(True, alpha=0.3)

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        return fig

    @staticmethod
    def plot_wind_rose(wind_speeds: np.ndarray,
                      wind_directions: np.ndarray,
                      title: str = "Wind Rose",
                      bins: int = 16,
                      figsize: Tuple[int, int] = (10, 10),
                      save_path: Optional[str] = None):
        """
        Create wind rose diagram

        Args:
            wind_speeds: Array of wind speeds (m/s)
            wind_directions: Array of wind directions (degrees from N)
            title: Plot title
            bins: Number of direction bins
            figsize: Figure size
            save_path: Optional save path
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required")

        # Create figure with polar projection
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111, projection='polar')

        # Define speed bins
        speed_bins = [0, 2, 4, 6, 8, 12, np.inf]  # m/s
        speed_labels = ['0-2', '2-4', '4-6', '6-8', '8-12', '>12']
        colors = plt.cm.viridis(np.linspace(0, 0.9, len(speed_bins)-1))

        # Direction bins, centred on the compass points (N is -11.25 to
        # 11.25 degrees for 16 bins), so a wind due north is one bar.
        wind_speeds = np.asarray(wind_speeds, dtype=float)
        wind_directions = np.asarray(wind_directions, dtype=float)
        valid = ~(np.isnan(wind_speeds) | np.isnan(wind_directions))
        wind_speeds, wind_directions = wind_speeds[valid], wind_directions[valid]
        half = 180.0 / bins
        dir_bins = np.linspace(0, 360, bins + 1)
        dir_centers = (dir_bins[:-1] + dir_bins[1:]) / 2 - half
        dir_width = 2 * np.pi / bins
        shifted = (wind_directions + half) % 360

        # Calculate frequencies (percent of all valid observations)
        bottom = np.zeros(bins)
        for i, (speed_min, speed_max) in enumerate(zip(speed_bins[:-1], speed_bins[1:])):  # noqa: RUF007
            mask = (wind_speeds >= speed_min) & (wind_speeds < speed_max)
            counts, _ = np.histogram(shifted[mask], bins=dir_bins)
            frequencies = 100 * counts / max(len(wind_directions), 1)

            ax.bar(np.radians(dir_centers), frequencies, width=dir_width,
                  bottom=bottom,
                  color=colors[i], label=f'{speed_labels[i]} m/s',
                  edgecolor='white', linewidth=0.5)
            bottom = bottom + frequencies

        # Formatting
        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)  # Clockwise
        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.legend(loc='upper left', bbox_to_anchor=(1.1, 1.0), title='Wind Speed')
        ax.set_ylabel('Frequency (%)', fontsize=11)

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        return fig

    @staticmethod
    def plot_concentration_profile(df: pd.DataFrame,
                                   direction: str = 'x',
                                   cross_coord: float = 0.0,
                                   title: Optional[str] = None,
                                   figsize: Tuple[int, int] = (12, 6),
                                   save_path: Optional[str] = None,
                                   source_xy: Tuple[float, float] = (0.0, 0.0)):
        """
        Plot concentration profile along a line

        Args:
            df: DataFrame with X, Y, CONC columns
            direction: 'x' or 'y' for profile direction
            cross_coord: Coordinate value in perpendicular direction
            title: Plot title
            figsize: Figure size
            save_path: Optional save path
            source_xy: (x, y) of the source, where the "Source" line is
                drawn. The default (0, 0) assumes the coordinates are
                relative to the source; give the source's UTM position
                for absolute coordinates.
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required")

        # Extract profile
        if direction.lower() == 'x':
            profile = df[df['Y'] == cross_coord].sort_values('X')
            x_data = profile['X']
            xlabel = 'Easting (m)'
        else:
            profile = df[df['X'] == cross_coord].sort_values('Y')
            x_data = profile['Y']
            xlabel = 'Northing (m)'

        if profile.empty:
            raise ValueError(f"No data found at {direction.upper()}={cross_coord}")

        # Create plot
        fig, ax = plt.subplots(figsize=figsize)

        ax.plot(x_data, profile['CONC'], linewidth=2.5, marker='o',
               markersize=6, color='steelblue', markerfacecolor='white',
               markeredgewidth=1.5)

        # Mark maximum
        max_idx = profile['CONC'].idxmax()
        max_x = profile.loc[max_idx, 'X' if direction.lower() == 'x' else 'Y']
        max_conc = profile.loc[max_idx, 'CONC']
        ax.plot(max_x, max_conc, 'r*', markersize=20, label=f'Max: {max_conc:.3f}')

        # Source location
        ax.axvline(source_xy[0] if direction.lower() == 'x' else source_xy[1],
                   color='red', linestyle='--', linewidth=2, alpha=0.7, label='Source')

        # Labels
        ax.set_xlabel(xlabel, fontsize=12, fontweight='bold')
        ax.set_ylabel('Concentration (μg/m³)', fontsize=12, fontweight='bold')
        if title is None:
            title = f'Concentration Profile along {direction.upper()}-axis'
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=10)

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        return fig

    @staticmethod
    def create_comparison_grid(scenarios: Dict[str, pd.DataFrame],
                              title: str = "Scenario Comparison",
                              colormap: str = 'YlOrRd',
                              figsize: Optional[Tuple[int, int]] = None,
                              save_path: Optional[str] = None,
                              source_xy: Tuple[float, float] = (0.0, 0.0)):
        """
        Create grid comparison of multiple scenarios

        Args:
            scenarios: Dict of scenario_name -> DataFrame
            title: Overall title
            colormap: Matplotlib colormap
            figsize: Figure size (auto if None)
            save_path: Optional save path
            source_xy: (x, y) of the source marker. The default (0, 0)
                assumes coordinates relative to the source.
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required")

        n_scenarios = len(scenarios)
        ncols = min(3, n_scenarios)
        nrows = (n_scenarios + ncols - 1) // ncols

        if figsize is None:
            figsize = (6 * ncols, 5 * nrows)

        fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
        if n_scenarios == 1:
            axes = [axes]
        else:
            axes = axes.flatten()

        # Find global min/max for consistent scale
        all_conc = np.concatenate([df['CONC'].values for df in scenarios.values()])
        vmin, vmax = np.min(all_conc[all_conc > 0]), np.max(all_conc)

        for idx, (name, df) in enumerate(scenarios.items()):
            ax = axes[idx]

            # Extract and grid data
            x_unique, y_unique, Z = _grid_from_xy(df)
            X, Y = np.meshgrid(x_unique, y_unique)

            # Plot
            im = ax.contourf(X, Y, Z, levels=15, cmap=colormap,
                            norm=mcolors.LogNorm(vmin=vmin, vmax=vmax))
            ax.contour(X, Y, Z, levels=10, colors='black',
                      linewidths=0.3, alpha=0.3)

            # Source marker
            ax.plot(*source_xy, 'k^', markersize=12, markeredgewidth=1.5,
                   markerfacecolor='white')

            # Labels
            ax.set_xlabel('Easting (m)', fontsize=10)
            ax.set_ylabel('Northing (m)', fontsize=10)
            ax.set_title(name, fontsize=12, fontweight='bold')
            ax.set_aspect('equal')
            ax.grid(True, alpha=0.2)

        # Hide empty subplots
        for idx in range(n_scenarios, len(axes)):
            axes[idx].axis('off')

        # Colorbar
        fig.subplots_adjust(right=0.9)
        cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
        cbar = fig.colorbar(im, cax=cbar_ax)
        cbar.set_label('Concentration (μg/m³)', fontsize=11, fontweight='bold')

        fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0, 0.9, 0.96])

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        return fig

    @staticmethod
    def plot_time_series_animation(dataframes: List[pd.DataFrame],
                                   timestamps: List[str],
                                   title: str = "Concentration Animation",
                                   interval: int = 500,
                                   save_path: Optional[str] = None,
                                   source_xy: Tuple[float, float] = (0.0, 0.0)):
        """
        Create animated time series of concentrations

        Args:
            dataframes: List of DataFrames (one per time step)
            timestamps: List of timestamp labels
            title: Animation title
            interval: Milliseconds between frames
            save_path: Path to save GIF (requires pillow)
            source_xy: (x, y) of the source marker. The default (0, 0)
                assumes coordinates relative to the source.
        """
        if not HAS_MATPLOTLIB:
            raise ImportError("matplotlib required")
        if not HAS_ANIMATION:
            raise ImportError("matplotlib.animation required")

        if len(dataframes) != len(timestamps):
            raise ValueError("Number of dataframes must match number of timestamps")

        # Setup figure
        fig, ax = plt.subplots(figsize=(10, 8))

        # Find global bounds
        all_conc = np.concatenate([df['CONC'].values for df in dataframes])
        positive = all_conc[all_conc > 0]
        if len(positive) == 0:
            vmin, vmax = 0.0, 1.0  # fallback for all-zero data
        else:
            vmin, vmax = np.min(positive), np.max(all_conc)

        # One grid for every frame: the X and Y values of all of them
        x_unique = np.unique(np.concatenate([d['X'].values for d in dataframes]))
        y_unique = np.unique(np.concatenate([d['Y'].values for d in dataframes]))
        X, Y = np.meshgrid(x_unique, y_unique)

        def update(frame):
            ax.clear()
            df = dataframes[frame]

            # Grid data
            _, _, Z = _grid_from_xy(df, x_unique, y_unique)

            # Plot. A frame with no positive value has no level on a log
            # scale: draw it flat on a linear one, in the lowest colour.
            if (Z > 0).any():
                norm = mcolors.LogNorm(vmin=vmin, vmax=vmax)
            else:
                norm = mcolors.Normalize(vmin=0.0, vmax=vmax)
            im = ax.contourf(X, Y, Z, levels=15, cmap='YlOrRd', norm=norm)
            ax.contour(X, Y, Z, levels=10, colors='black',
                      linewidths=0.3, alpha=0.3)

            # Source
            ax.plot(*source_xy, 'k^', markersize=15, markeredgewidth=2,
                   markerfacecolor='white')

            # Labels
            ax.set_xlabel('Easting (m)', fontsize=12, fontweight='bold')
            ax.set_ylabel('Northing (m)', fontsize=12, fontweight='bold')
            ax.set_title(f'{title} - {timestamps[frame]}',
                        fontsize=14, fontweight='bold')
            ax.set_aspect('equal')
            ax.grid(True, alpha=0.3)

            return im,

        # Create animation
        anim = FuncAnimation(fig, update, frames=len(dataframes),
                           interval=interval, blit=False)

        if save_path:
            writer = PillowWriter(fps=max(1, round(1000 / interval)))
            anim.save(save_path, writer=writer)

        return anim
