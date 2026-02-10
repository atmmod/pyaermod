"""
PyAERMOD Advanced Visualization Tools

Advanced plotting capabilities including 3D visualizations, wind roses,
animations, and publication-quality figure generation.
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Tuple, Dict
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from matplotlib import cm
    from mpl_toolkits.mplot3d import Axes3D
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    from matplotlib.animation import FuncAnimation, PillowWriter
    HAS_ANIMATION = True
except ImportError:
    HAS_ANIMATION = False


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

        # Extract data
        x = df['X'].values
        y = df['Y'].values
        conc = df['CONC'].values

        # Create grid
        x_unique = np.unique(x)
        y_unique = np.unique(y)
        X, Y = np.meshgrid(x_unique, y_unique)
        Z = conc.reshape(len(y_unique), len(x_unique))

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
        speed_bins = [0, 2, 4, 6, 8, 12, 100]  # m/s
        speed_labels = ['0-2', '2-4', '4-6', '6-8', '8-12', '>12']
        colors = plt.cm.viridis(np.linspace(0, 0.9, len(speed_bins)-1))

        # Direction bins
        dir_bins = np.linspace(0, 360, bins+1)
        dir_centers = (dir_bins[:-1] + dir_bins[1:]) / 2
        dir_width = 2 * np.pi / bins

        # Calculate frequencies
        for i, (speed_min, speed_max) in enumerate(zip(speed_bins[:-1], speed_bins[1:])):
            # Filter by speed
            mask = (wind_speeds >= speed_min) & (wind_speeds < speed_max)
            directions_subset = wind_directions[mask]

            # Count in each direction bin
            counts, _ = np.histogram(directions_subset, bins=dir_bins)
            frequencies = 100 * counts / len(wind_directions)

            # Plot
            ax.bar(np.radians(dir_centers), frequencies, width=dir_width,
                  bottom=np.sum([100 * np.histogram(wind_directions[(wind_speeds >= speed_bins[j]) &
                                                                     (wind_speeds < speed_bins[j+1])],
                                                    bins=dir_bins)[0] / len(wind_directions)
                                for j in range(i)], axis=0) if i > 0 else 0,
                  color=colors[i], label=f'{speed_labels[i]} m/s',
                  edgecolor='white', linewidth=0.5)

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
                                   save_path: Optional[str] = None):
        """
        Plot concentration profile along a line

        Args:
            df: DataFrame with X, Y, CONC columns
            direction: 'x' or 'y' for profile direction
            cross_coord: Coordinate value in perpendicular direction
            title: Plot title
            figsize: Figure size
            save_path: Optional save path
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
        ax.axvline(0, color='red', linestyle='--', linewidth=2, alpha=0.7, label='Source')

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
                              save_path: Optional[str] = None):
        """
        Create grid comparison of multiple scenarios

        Args:
            scenarios: Dict of scenario_name -> DataFrame
            title: Overall title
            colormap: Matplotlib colormap
            figsize: Figure size (auto if None)
            save_path: Optional save path
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
            x = df['X'].values
            y = df['Y'].values
            conc = df['CONC'].values

            x_unique = np.unique(x)
            y_unique = np.unique(y)
            X, Y = np.meshgrid(x_unique, y_unique)
            Z = conc.reshape(len(y_unique), len(x_unique))

            # Plot
            im = ax.contourf(X, Y, Z, levels=15, cmap=colormap,
                            norm=mcolors.LogNorm(vmin=vmin, vmax=vmax))
            ax.contour(X, Y, Z, levels=10, colors='black',
                      linewidths=0.3, alpha=0.3)

            # Source marker
            ax.plot(0, 0, 'k^', markersize=12, markeredgewidth=1.5,
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
                                   save_path: Optional[str] = None):
        """
        Create animated time series of concentrations

        Args:
            dataframes: List of DataFrames (one per time step)
            timestamps: List of timestamp labels
            title: Animation title
            interval: Milliseconds between frames
            save_path: Path to save GIF (requires pillow)
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
        vmin, vmax = np.min(all_conc[all_conc > 0]), np.max(all_conc)

        # Get first frame data
        df = dataframes[0]
        x_unique = np.unique(df['X'].values)
        y_unique = np.unique(df['Y'].values)
        X, Y = np.meshgrid(x_unique, y_unique)

        def update(frame):
            ax.clear()
            df = dataframes[frame]

            # Grid data
            Z = df['CONC'].values.reshape(len(y_unique), len(x_unique))

            # Plot
            im = ax.contourf(X, Y, Z, levels=15, cmap='YlOrRd',
                            norm=mcolors.LogNorm(vmin=vmin, vmax=vmax))
            ax.contour(X, Y, Z, levels=10, colors='black',
                      linewidths=0.3, alpha=0.3)

            # Source
            ax.plot(0, 0, 'k^', markersize=15, markeredgewidth=2,
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
            writer = PillowWriter(fps=1000//interval)
            anim.save(save_path, writer=writer)

        return anim


# Example usage and demonstrations
if __name__ == "__main__":
    print("PyAERMOD Advanced Visualization Tools")
    print("=" * 70)
    print()

    print("Available visualization functions:")
    print("  1. plot_3d_surface()       - 3D surface plots of concentration")
    print("  2. plot_wind_rose()        - Wind rose diagrams")
    print("  3. plot_concentration_profile() - Cross-section profiles")
    print("  4. create_comparison_grid() - Side-by-side scenario comparison")
    print("  5. plot_time_series_animation() - Animated time series")
    print()

    # Generate sample data for demonstration
    print("Generating sample data...")

    x = np.linspace(-1000, 1000, 41)
    y = np.linspace(-1000, 1000, 41)
    X, Y = np.meshgrid(x, y)

    # Gaussian plume approximation
    distance = np.sqrt(X**2 + Y**2)
    conc = 10 * np.exp(-distance/500) + 0.1

    df_sample = pd.DataFrame({
        'X': X.flatten(),
        'Y': Y.flatten(),
        'CONC': conc.flatten()
    })

    print("✓ Sample data created")
    print()

    # Example: 3D plot
    print("Example 1: Creating 3D surface plot...")
    viz = AdvancedVisualizer()
    fig = viz.plot_3d_surface(
        df_sample,
        title="Example 3D Concentration Surface",
        save_path="example_3d_surface.png"
    )
    print("✓ Saved: example_3d_surface.png")
    plt.close(fig)
    print()

    # Example: Wind rose (with synthetic data)
    print("Example 2: Creating wind rose...")
    np.random.seed(42)
    wind_speeds = np.random.gamma(3, 2, 1000)  # Realistic speed distribution
    wind_directions = np.random.normal(180, 60, 1000) % 360  # Predominantly from S

    fig = viz.plot_wind_rose(
        wind_speeds,
        wind_directions,
        title="Example Wind Rose (Synthetic Data)",
        save_path="example_wind_rose.png"
    )
    print("✓ Saved: example_wind_rose.png")
    plt.close(fig)
    print()

    # Example: Profile plot
    print("Example 3: Creating concentration profile...")
    fig = viz.plot_concentration_profile(
        df_sample,
        direction='x',
        cross_coord=0.0,
        save_path="example_profile.png"
    )
    print("✓ Saved: example_profile.png")
    plt.close(fig)
    print()

    print("=" * 70)
    print("Advanced visualization examples completed!")
    print()
    print("Integration with AERMOD results:")
    print("  from pyaermod.advanced_viz import AdvancedVisualizer")
    print("  viz = AdvancedVisualizer()")
    print("  fig = viz.plot_3d_surface(concentration_df)")
    print()
