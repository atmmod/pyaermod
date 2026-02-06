"""
Example: Downloading Meteorology Data with PyAERMOD

This script demonstrates how to use the meteorology data fetcher to automatically
download and process met data from NOAA for use with AERMOD.
"""

from pyaermod_met_fetcher import MeteorologyFetcher
import sys


def example_1_search_stations():
    """Example 1: Search for weather stations near a location"""
    print("=" * 70)
    print("Example 1: Search for Weather Stations")
    print("=" * 70)
    print()

    # Create fetcher
    fetcher = MeteorologyFetcher(cache_dir="./met_cache")

    # Search for stations near a facility
    # Example: Near Denver, CO
    facility_lat = 39.7392
    facility_lon = -104.9903

    print(f"Searching for stations near Denver, CO")
    print(f"Location: ({facility_lat}, {facility_lon})")
    print(f"Search radius: 50 km")
    print()

    try:
        stations = fetcher.search_stations(
            lat=facility_lat,
            lon=facility_lon,
            radius_km=50,
            country="US"
        )

        print(f"Found {len(stations)} stations:")
        for i, station in enumerate(stations[:10], 1):
            distance = fetcher._haversine_distance(
                facility_lat, facility_lon,
                station.latitude, station.longitude
            )
            print(f"\n{i}. {station}")
            print(f"   Distance: {distance:.1f} km")
            print(f"   Elevation: {station.elevation:.0f} m")

        return stations

    except Exception as e:
        print(f"Error: {e}")
        print("\nNote: This requires internet connection to access NOAA data.")
        return []


def example_2_download_for_location():
    """Example 2: Automatic download for a location"""
    print("\n" + "=" * 70)
    print("Example 2: Automatic Download (finds nearest station)")
    print("=" * 70)
    print()

    fetcher = MeteorologyFetcher()

    # Your facility location
    facility_lat = 41.98   # Chicago
    facility_lon = -87.90
    year = 2023

    print(f"Fetching meteorology data for:")
    print(f"  Location: ({facility_lat}, {facility_lon})")
    print(f"  Year: {year}")
    print()

    try:
        # This automatically finds nearest station and downloads data
        met_data = fetcher.fetch_for_location(
            lat=facility_lat,
            lon=facility_lon,
            year=year,
            radius_km=100
        )

        print("\n✓ Data downloaded successfully!")
        print("\nSummary:")
        summary = met_data.summary()
        for key, value in summary.items():
            print(f"  {key}: {value}")

        print("\nSample hourly data:")
        print(met_data.surface_data.head(10))

        return met_data

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def example_3_download_specific_station():
    """Example 3: Download for a specific station"""
    print("\n" + "=" * 70)
    print("Example 3: Download for Specific Station")
    print("=" * 70)
    print()

    fetcher = MeteorologyFetcher()

    # Use a known station ID
    # Example: KORD = Chicago O'Hare
    station_id = "725300"  # O'Hare USAF ID
    year = 2023

    print(f"Fetching data for station: {station_id}")
    print(f"Year: {year}")
    print()

    try:
        met_data = fetcher.fetch_for_station(station_id, year)

        print("✓ Data downloaded!")
        print(f"\nStation: {met_data.station}")
        print(f"Data points: {len(met_data.surface_data)}")
        print(f"Completeness: {100 * len(met_data.surface_data) / met_data.expected_hours():.1f}%")

        return met_data

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def example_4_create_aermod_files():
    """Example 4: Create AERMOD-ready meteorology files"""
    print("\n" + "=" * 70)
    print("Example 4: Create AERMOD Meteorology Files")
    print("=" * 70)
    print()

    # First, download data (or use from previous example)
    fetcher = MeteorologyFetcher()

    print("This example assumes you've already downloaded met data.")
    print("It will process that data and create AERMOD-ready files.")
    print()

    # In practice, you'd use met_data from example 2 or 3
    # met_data = fetcher.fetch_for_location(lat=41.98, lon=-87.90, year=2023)

    print("Steps this would perform:")
    print("  1. Process raw NOAA data")
    print("  2. Format for AERMET input")
    print("  3. Create AERMET Stage 3 input file")
    print("  4. Run AERMET (if installed)")
    print("  5. Generate final .sfc and .pfl files")
    print()

    print("Example code:")
    print("""
    # Download data
    met_data = fetcher.fetch_for_location(
        lat=41.98, lon=-87.90, year=2023
    )

    # Create AERMOD files
    files = fetcher.create_aermet_files(
        met_data,
        output_dir="./aermod_met",
        aermet_path="aermet"  # or None if not installed
    )

    # Use in AERMOD
    print(f"Surface file: {files['aermod_sfc']}")
    print(f"Profile file: {files['aermod_pfl']}")
    """)


def example_5_complete_workflow():
    """Example 5: Complete workflow from location to AERMOD files"""
    print("\n" + "=" * 70)
    print("Example 5: Complete Automated Workflow")
    print("=" * 70)
    print()

    print("This demonstrates the complete workflow:")
    print("  Facility location → Download met data → Create AERMOD files")
    print()

    # Configuration
    FACILITY_LAT = 40.7128  # New York City
    FACILITY_LON = -74.0060
    YEAR = 2023
    OUTPUT_DIR = "./aermod_met_nyc"

    print("Configuration:")
    print(f"  Facility: ({FACILITY_LAT}, {FACILITY_LON})")
    print(f"  Year: {YEAR}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    print("Workflow:")
    print("""
    # Initialize
    from pyaermod_met_fetcher import MeteorologyFetcher
    fetcher = MeteorologyFetcher()

    # Step 1: Download (finds nearest station automatically)
    print("Downloading meteorology data...")
    met_data = fetcher.fetch_for_location(
        lat={lat},
        lon={lon},
        year={year}
    )

    # Step 2: Create AERMOD files
    print("Creating AERMOD met files...")
    files = fetcher.create_aermet_files(
        met_data,
        output_dir="{output_dir}",
        aermet_path="aermet"
    )

    # Step 3: Use in your AERMOD model
    from pyaermod_input_generator import MeteorologyPathway

    meteorology = MeteorologyPathway(
        surface_file=files['aermod_sfc'],
        profile_file=files['aermod_pfl']
    )

    # Now use in your AERMOD project!
    """.format(lat=FACILITY_LAT, lon=FACILITY_LON,
               year=YEAR, output_dir=OUTPUT_DIR))


def main():
    """Run all examples"""
    print()
    print("*" * 70)
    print("*" + " " * 68 + "*")
    print("*" + " " * 15 + "PyAERMOD Meteorology Data Fetcher" + " " * 20 + "*")
    print("*" + " " * 68 + "*")
    print("*" * 70)
    print()

    print("This script demonstrates automatic meteorology data download")
    print("from NOAA for use with AERMOD.")
    print()

    # Run examples
    try:
        # Example 1: Search for stations
        stations = example_1_search_stations()

        # Example 2: Auto download
        met_data = example_2_download_for_location()

        # Example 3: Specific station
        # met_data = example_3_download_specific_station()

        # Example 4: Create AERMOD files
        example_4_create_aermod_files()

        # Example 5: Complete workflow
        example_5_complete_workflow()

        print("\n" + "=" * 70)
        print("Examples Complete!")
        print("=" * 70)
        print()

        print("Key Benefits:")
        print("  ✓ Automatic station selection")
        print("  ✓ Direct download from NOAA")
        print("  ✓ Data validation and quality checks")
        print("  ✓ AERMET integration")
        print("  ✓ Ready-to-use AERMOD .sfc/.pfl files")
        print()

        print("Time Savings:")
        print("  Manual process: 2-4 hours")
        print("  With PyAERMOD:  5-10 minutes")
        print()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError running examples: {e}")
        print("\nNote: These examples require:")
        print("  - Internet connection")
        print("  - Access to NOAA servers")
        print("  - AERMET executable (optional)")
        sys.exit(1)


if __name__ == "__main__":
    main()
