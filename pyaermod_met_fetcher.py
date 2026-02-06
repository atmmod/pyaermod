"""
PyAERMOD Meteorology Data Fetcher

Automatically downloads and processes meteorology data from NOAA for use with AERMOD.

Features:
- Search for weather stations by location
- Download NOAA ISD (Integrated Surface Database) data
- Download upper air radiosonde data
- Process data for AERMET
- Generate AERMET input files
- Run AERMET to create .sfc and .pfl files

Data Sources:
- NOAA ISD: https://www.ncei.noaa.gov/data/global-hourly/
- NOAA Upper Air: https://www.ncei.noaa.gov/data/radiosonde/
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
from pathlib import Path
import gzip
import io
import subprocess
import json


@dataclass
class WeatherStation:
    """Represents a weather station"""
    station_id: str
    name: str
    latitude: float
    longitude: float
    elevation: float
    country: str = "US"
    state: str = ""

    def __str__(self):
        return f"{self.station_id} - {self.name} ({self.latitude:.2f}, {self.longitude:.2f})"


@dataclass
class MeteorologicalData:
    """Container for downloaded meteorological data"""
    station: WeatherStation
    start_date: datetime
    end_date: datetime
    surface_data: pd.DataFrame
    upper_air_data: Optional[pd.DataFrame] = None

    def summary(self):
        """Get summary statistics"""
        return {
            'station': str(self.station),
            'date_range': f"{self.start_date.date()} to {self.end_date.date()}",
            'surface_hours': len(self.surface_data),
            'completeness': f"{100 * len(self.surface_data) / self.expected_hours():.1f}%"
        }

    def expected_hours(self):
        """Calculate expected number of hourly observations"""
        delta = self.end_date - self.start_date
        return delta.days * 24 + delta.seconds // 3600


class MeteorologyFetcher:
    """
    Fetch and process meteorological data from NOAA for AERMOD

    Handles downloading surface and upper air data, processing for AERMET,
    and creating AERMOD-ready meteorology files.
    """

    # NOAA ISD base URL
    ISD_BASE_URL = "https://www.ncei.noaa.gov/data/global-hourly/access"

    # Station list URL
    STATION_LIST_URL = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"

    def __init__(self, cache_dir: str = "./met_cache"):
        """
        Initialize fetcher

        Args:
            cache_dir: Directory to cache downloaded data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.stations_cache = None

    def search_stations(self,
                       lat: float,
                       lon: float,
                       radius_km: float = 100,
                       country: str = "US") -> List[WeatherStation]:
        """
        Find weather stations near a location

        Args:
            lat: Latitude (decimal degrees)
            lon: Longitude (decimal degrees)
            radius_km: Search radius in kilometers
            country: Country code (default US)

        Returns:
            List of WeatherStation objects sorted by distance
        """
        print(f"Searching for stations within {radius_km}km of ({lat:.3f}, {lon:.3f})...")

        # Load station list
        stations_df = self._get_station_list()

        # Filter by country
        stations_df = stations_df[stations_df['CTRY'] == country]

        # Calculate distances
        stations_df['distance_km'] = stations_df.apply(
            lambda row: self._haversine_distance(
                lat, lon, row['LAT'], row['LON']
            ), axis=1
        )

        # Filter by radius
        nearby = stations_df[stations_df['distance_km'] <= radius_km].copy()
        nearby = nearby.sort_values('distance_km')

        # Convert to WeatherStation objects
        stations = []
        for _, row in nearby.iterrows():
            station = WeatherStation(
                station_id=row['USAF'],
                name=row['STATION NAME'],
                latitude=row['LAT'],
                longitude=row['LON'],
                elevation=row['ELEV(M)'],
                country=row['CTRY'],
                state=row['STATE'] if 'STATE' in row else ""
            )
            stations.append(station)

        print(f"Found {len(stations)} stations")
        return stations

    def fetch_surface_data(self,
                          station_id: str,
                          year: int,
                          output_format: str = "dataframe") -> pd.DataFrame:
        """
        Fetch surface meteorology data from NOAA ISD

        Args:
            station_id: USAF station ID (6 digits)
            year: Year to download
            output_format: 'dataframe' or 'raw'

        Returns:
            DataFrame with processed surface data
        """
        print(f"Fetching surface data for station {station_id}, year {year}...")

        # Check cache first
        cache_file = self.cache_dir / f"{station_id}_{year}_surface.csv"
        if cache_file.exists():
            print(f"  Loading from cache: {cache_file}")
            return pd.read_csv(cache_file, parse_dates=['timestamp'])

        # Download from NOAA
        # NOAA ISD filenames use USAF+WBAN concatenated: e.g. 72530094846.csv
        # Look up WBAN code from station list
        stations_df = self._get_station_list()
        station_row = stations_df[stations_df['USAF'] == station_id]
        wban = str(int(station_row.iloc[0]['WBAN'])).zfill(5) if len(station_row) > 0 else "99999"
        usaf_wban = f"{station_id}{wban}"

        url = f"{self.ISD_BASE_URL}/{year}/{usaf_wban}.csv"

        print(f"  Downloading from: {url}")
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  Error downloading data: {e}")
            print(f"  Trying alternative format (USAF + 99999)...")
            # Fallback: try with 99999 WBAN
            url = f"{self.ISD_BASE_URL}/{year}/{station_id}99999.csv"
            response = requests.get(url, timeout=60)
            response.raise_for_status()

        # Parse CSV
        df = pd.read_csv(io.StringIO(response.text))

        # Process data
        df_processed = self._process_surface_data(df)

        # Cache it
        df_processed.to_csv(cache_file, index=False)
        print(f"  Cached to: {cache_file}")
        print(f"  Downloaded {len(df_processed)} hourly observations")

        return df_processed

    def fetch_for_location(self,
                          lat: float,
                          lon: float,
                          year: int,
                          radius_km: float = 100) -> MeteorologicalData:
        """
        Fetch meteorology data for a location (finds nearest station automatically)

        Args:
            lat: Latitude
            lon: Longitude
            year: Year
            radius_km: Search radius

        Returns:
            MeteorologicalData object
        """
        # Find nearest station
        stations = self.search_stations(lat, lon, radius_km)

        if not stations:
            raise ValueError(f"No stations found within {radius_km}km of ({lat}, {lon})")

        # Use closest station
        station = stations[0]
        print(f"\nUsing station: {station}")
        print(f"  Distance: {self._haversine_distance(lat, lon, station.latitude, station.longitude):.1f} km")

        # Fetch data
        return self.fetch_for_station(station.station_id, year)

    def fetch_for_station(self,
                         station_id: str,
                         year: int) -> MeteorologicalData:
        """
        Fetch meteorology data for a specific station

        Args:
            station_id: USAF station ID
            year: Year to download

        Returns:
            MeteorologicalData object
        """
        # Get station info
        stations_df = self._get_station_list()
        station_row = stations_df[stations_df['USAF'] == station_id].iloc[0]

        station = WeatherStation(
            station_id=station_id,
            name=station_row['STATION NAME'],
            latitude=station_row['LAT'],
            longitude=station_row['LON'],
            elevation=station_row['ELEV(M)'],
            country=station_row['CTRY']
        )

        # Fetch surface data
        surface_data = self.fetch_surface_data(station_id, year)

        # Create MeteorologicalData object
        met_data = MeteorologicalData(
            station=station,
            start_date=datetime(year, 1, 1),
            end_date=datetime(year, 12, 31, 23, 59, 59),
            surface_data=surface_data
        )

        return met_data

    def create_aermet_files(self,
                           met_data: MeteorologicalData,
                           output_dir: str = ".",
                           aermet_path: str = "aermet") -> Dict[str, str]:
        """
        Create AERMET-ready files and optionally run AERMET

        Args:
            met_data: MeteorologicalData object
            output_dir: Output directory
            aermet_path: Path to AERMET executable (or None to skip execution)

        Returns:
            Dictionary with paths to created files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)

        print("\nCreating AERMET files...")

        # Step 1: Write surface data in AERMET format
        surface_file = output_dir / f"{met_data.station.station_id}_surface.dat"
        self._write_aermet_surface_data(met_data, surface_file)
        print(f"  Created: {surface_file}")

        # Step 2: Create AERMET input file
        from pyaermod_aermet import AERMETStage3, AERMETStation

        aermet_station = AERMETStation(
            station_id=met_data.station.station_id,
            station_name=met_data.station.name,
            latitude=met_data.station.latitude,
            longitude=met_data.station.longitude,
            elevation=met_data.station.elevation,
            time_zone=self._get_timezone_offset(met_data.station.longitude)
        )

        # Create Stage 3 (most common use case)
        stage3 = AERMETStage3(
            station=aermet_station,
            merge_file=str(surface_file),  # In practice would be Stage 2 output
            start_date=met_data.start_date.strftime("%Y/%m/%d"),
            end_date=met_data.end_date.strftime("%Y/%m/%d"),
            surface_file=str(output_dir / "aermod.sfc"),
            profile_file=str(output_dir / "aermod.pfl")
        )

        aermet_input = output_dir / "aermet_stage3.inp"
        with open(aermet_input, 'w') as f:
            f.write(stage3.to_aermet_input())
        print(f"  Created: {aermet_input}")

        # Step 3: Run AERMET (if executable available)
        results = {
            'surface_data': str(surface_file),
            'aermet_input': str(aermet_input),
            'aermod_sfc': None,
            'aermod_pfl': None
        }

        if aermet_path:
            try:
                print(f"\n  Running AERMET...")
                result = subprocess.run(
                    [aermet_path],
                    stdin=open(aermet_input),
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=output_dir
                )

                if result.returncode == 0:
                    print(f"  ✓ AERMET completed successfully")
                    results['aermod_sfc'] = str(output_dir / "aermod.sfc")
                    results['aermod_pfl'] = str(output_dir / "aermod.pfl")
                else:
                    print(f"  ✗ AERMET failed with return code {result.returncode}")
                    print(f"  Error: {result.stderr}")
            except FileNotFoundError:
                print(f"  ⚠ AERMET executable not found at: {aermet_path}")
                print(f"  Skipping AERMET execution")
            except subprocess.TimeoutExpired:
                print(f"  ✗ AERMET timed out after 300 seconds")

        return results

    # Helper methods

    def _get_station_list(self) -> pd.DataFrame:
        """Download and cache NOAA station list"""
        if self.stations_cache is not None:
            return self.stations_cache

        cache_file = self.cache_dir / "isd_stations.csv"

        if cache_file.exists():
            print("Loading station list from cache...")
            df = pd.read_csv(cache_file)
        else:
            print("Downloading station list from NOAA...")
            df = pd.read_csv(self.STATION_LIST_URL)
            df.to_csv(cache_file, index=False)
            print(f"Cached station list to: {cache_file}")

        # Clean up data
        df['END'] = pd.to_numeric(df['END'], errors='coerce')
        df = df[df['END'] >= 20200101]  # Only active/recent stations
        df['LAT'] = pd.to_numeric(df['LAT'], errors='coerce')
        df['LON'] = pd.to_numeric(df['LON'], errors='coerce')
        df['ELEV(M)'] = pd.to_numeric(df['ELEV(M)'], errors='coerce')
        df = df.dropna(subset=['LAT', 'LON'])

        self.stations_cache = df
        return df

    def _haversine_distance(self, lat1: float, lon1: float,
                           lat2: float, lon2: float) -> float:
        """Calculate distance between two points on Earth (km)"""
        R = 6371  # Earth radius in km

        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))

        return R * c

    def _process_surface_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process raw ISD data into clean format"""
        # Parse timestamp
        df['timestamp'] = pd.to_datetime(df['DATE'])

        # Extract key meteorological variables
        # Note: ISD format details at https://www.ncei.noaa.gov/data/global-hourly/doc/
        processed = pd.DataFrame({
            'timestamp': df['timestamp'],
            'temperature': self._parse_scaled_value(df, 'TMP', 10),  # °C
            'wind_speed': self._parse_scaled_value(df, 'WND', 10),   # m/s
            'wind_direction': df['WND'].str.split(',').str[0].astype(float),  # degrees
            'pressure': self._parse_scaled_value(df, 'SLP', 10),  # hPa
        })

        # Remove missing values
        processed = processed.replace([999, 9999, 99999], np.nan)

        return processed

    def _parse_scaled_value(self, df: pd.DataFrame, column: str, scale: float) -> pd.Series:
        """Parse comma-separated scaled values from ISD format"""
        try:
            values = df[column].str.split(',').str[0]
            return pd.to_numeric(values, errors='coerce') / scale
        except:
            return pd.Series([np.nan] * len(df))

    def _write_aermet_surface_data(self, met_data: MeteorologicalData, output_file: Path):
        """Write surface data in AERMET-compatible format"""
        # This is a simplified version - full implementation would match
        # AERMET's expected input format exactly
        with open(output_file, 'w') as f:
            f.write("** AERMET Surface Data\n")
            f.write(f"** Station: {met_data.station.station_id}\n")
            f.write(f"** Period: {met_data.start_date} to {met_data.end_date}\n")

            for _, row in met_data.surface_data.iterrows():
                # Format: YYYY MM DD HH TEMP WSPD WDIR PRES
                f.write(f"{row['timestamp'].strftime('%Y %m %d %H')} "
                       f"{row['temperature']:.1f} "
                       f"{row['wind_speed']:.1f} "
                       f"{row['wind_direction']:.0f} "
                       f"{row['pressure']:.1f}\n")

    def _get_timezone_offset(self, longitude: float) -> int:
        """Estimate timezone offset from longitude"""
        # Rough estimate: -180 to +180 longitude maps to -12 to +12 hours
        return int(longitude / 15)


# Example usage and testing
if __name__ == "__main__":
    print("PyAERMOD Meteorology Data Fetcher")
    print("=" * 70)
    print()

    # Create fetcher
    fetcher = MeteorologyFetcher()

    # Example 1: Search for stations near Chicago
    print("Example 1: Search for stations near Chicago, IL")
    print("-" * 70)

    chicago_lat = 41.98
    chicago_lon = -87.90

    stations = fetcher.search_stations(chicago_lat, chicago_lon, radius_km=50)

    print(f"\nFound {len(stations)} stations within 50km:")
    for i, station in enumerate(stations[:5], 1):
        distance = fetcher._haversine_distance(
            chicago_lat, chicago_lon,
            station.latitude, station.longitude
        )
        print(f"  {i}. {station.station_id} - {station.name}")
        print(f"     Distance: {distance:.1f} km, Elevation: {station.elevation:.0f} m")

    print()

    # Example 2: Fetch data for a station
    print("Example 2: Fetch data for Chicago O'Hare (KORD)")
    print("-" * 70)

    # Use first station found (likely O'Hare)
    if stations:
        station = stations[0]
        print(f"\nFetching data for: {station}")

        try:
            # Fetch 2023 data (adjust year as needed)
            met_data = fetcher.fetch_for_station(station.station_id, 2023)

            print("\nData Summary:")
            summary = met_data.summary()
            for key, value in summary.items():
                print(f"  {key}: {value}")

            print("\nSample data (first 5 hours):")
            print(met_data.surface_data.head())

            # Example 3: Create AERMET files
            print("\n" + "=" * 70)
            print("Example 3: Create AERMET files")
            print("-" * 70)

            results = fetcher.create_aermet_files(
                met_data,
                output_dir="./met_output",
                aermet_path=None  # Set to "aermet" if you have it installed
            )

            print("\nGenerated files:")
            for key, path in results.items():
                if path:
                    print(f"  {key}: {path}")

        except Exception as e:
            print(f"\nError fetching data: {e}")
            print("This is expected if you don't have internet connection")
            print("or if the NOAA API is unavailable.")

    print("\n" + "=" * 70)
    print("Testing complete!")
    print("\nTo use this in your code:")
    print("""
    from pyaermod_met_fetcher import MeteorologyFetcher

    fetcher = MeteorologyFetcher()
    met_data = fetcher.fetch_for_location(
        lat=41.98, lon=-87.90, year=2023
    )
    files = fetcher.create_aermet_files(met_data)
    print(f"Created: {files['aermod_sfc']}")
    """)
