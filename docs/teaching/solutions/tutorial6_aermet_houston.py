"""
Tutorial 6 Solution — AERMET for Houston, Texas
=================================================

This script generates the three AERMET stage input files for the Houston
Ship Channel area, as described in Tutorial 6 of the refinery assignments.

Usage:
    python tutorial6_aermet_houston.py [--output-dir DIR]

Outputs:
    aermet_houston_s1.inp  — Stage 1: Extract & QA/QC
    aermet_houston_s2.inp  — Stage 2: Merge
    aermet_houston_s3.inp  — Stage 3: Boundary layer parameters

No external data files are needed to generate the input files.
Running AERMET itself requires the raw surface/upper-air data files.
"""

import argparse
from pathlib import Path

from pyaermod.aermet import (
    AERMETStation,
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,
    UpperAirStation,
)


def create_houston_surface_station() -> AERMETStation:
    """Houston Hobby Airport (KHOU) surface station."""
    return AERMETStation(
        station_id="KHOU",
        station_name="Houston Hobby Airport",
        latitude=29.6454,
        longitude=-95.2789,
        time_zone=-6,
        elevation=14.0,
        anemometer_height=10.0,
    )


def create_lake_charles_upper_air() -> UpperAirStation:
    """Lake Charles, LA upper air (radiosonde) station."""
    return UpperAirStation(
        station_id="72240",
        station_name="Lake Charles LA",
        latitude=30.1200,
        longitude=-93.2200,
    )


# --- Houston Ship Channel monthly surface parameters ---
# Lower albedo (dark industrial + green vegetation), low Bowen ratio
# (Gulf moisture), higher roughness (industrial structures).
HOUSTON_ALBEDO = [0.18, 0.18, 0.16, 0.14, 0.14, 0.14,
                  0.14, 0.14, 0.15, 0.16, 0.17, 0.18]

HOUSTON_BOWEN = [0.8, 0.7, 0.5, 0.4, 0.3, 0.3,
                 0.3, 0.3, 0.4, 0.5, 0.7, 0.8]

HOUSTON_ROUGHNESS = [0.40, 0.40, 0.50, 0.60, 0.60, 0.60,
                     0.60, 0.60, 0.60, 0.50, 0.45, 0.40]


def build_stage1(station: AERMETStation,
                 upper_air: UpperAirStation) -> AERMETStage1:
    """Stage 1: Extract and QA/QC raw weather data."""
    return AERMETStage1(
        surface_station=station,
        surface_data_file="khou_2023.dat",
        surface_format="ISHD",
        upper_air_station=upper_air,
        upper_air_data_file="72240_2023.dat",
        start_date="2023/01/01",
        end_date="2023/12/31",
        extract_file="khou_extract.sfc",
        qa_file="khou_qa.out",
        output_file="aermet_s1.out",
    )


def build_stage2() -> AERMETStage2:
    """Stage 2: Merge surface and upper air extracted data."""
    return AERMETStage2(
        surface_extract="khou_extract.sfc",
        upper_air_extract="lch_extract.ua",
        start_date="2023/01/01",
        end_date="2023/12/31",
        merge_file="houston_merged.mrg",
        output_file="aermet_s2.out",
    )


def build_stage3(station: AERMETStation) -> AERMETStage3:
    """Stage 3: Compute boundary layer parameters with Houston-specific
    surface characteristics."""
    return AERMETStage3(
        merge_file="houston_merged.mrg",
        station=station,
        albedo=HOUSTON_ALBEDO,
        bowen=HOUSTON_BOWEN,
        roughness=HOUSTON_ROUGHNESS,
        start_date="2023/01/01",
        end_date="2023/12/31",
        surface_file="houston_2023.sfc",
        profile_file="houston_2023.pfl",
        output_file="aermet_s3.out",
    )


def main(output_dir: str = ".") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    station = create_houston_surface_station()
    upper_air = create_lake_charles_upper_air()

    # --- Stage 1 ---
    stage1 = build_stage1(station, upper_air)
    s1_text = stage1.to_aermet_input()
    s1_path = out / "aermet_houston_s1.inp"
    s1_path.write_text(s1_text)
    print(f"  Stage 1 written to {s1_path}")

    # --- Stage 2 ---
    stage2 = build_stage2()
    s2_text = stage2.to_aermet_input()
    s2_path = out / "aermet_houston_s2.inp"
    s2_path.write_text(s2_text)
    print(f"  Stage 2 written to {s2_path}")

    # --- Stage 3 ---
    stage3 = build_stage3(station)
    s3_text = stage3.to_aermet_input()
    s3_path = out / "aermet_houston_s3.inp"
    s3_path.write_text(s3_text)
    print(f"  Stage 3 written to {s3_path}")

    # --- Verification ---
    print("\n--- Verification ---")

    # Stage 1 checks
    assert "KHOU" in s1_text, "Surface station ID missing"
    assert "72240" in s1_text, "Upper air station ID missing"
    assert "ISHD" in s1_text, "Surface format missing"
    assert "2023/01/01" in s1_text, "Start date missing"
    assert "2023/12/31" in s1_text, "End date missing"
    assert "khou_2023.dat" in s1_text, "Surface data file missing"
    print("  Stage 1: all checks passed")

    # Stage 2 checks
    assert "khou_extract.sfc" in s2_text, "Surface extract file missing"
    assert "houston_merged.mrg" in s2_text, "Merge output file missing"
    print("  Stage 2: all checks passed")

    # Stage 3 checks
    assert "houston_merged.mrg" in s3_text, "Merge file missing"
    assert "houston_2023.sfc" in s3_text, "SFC output missing"
    assert "houston_2023.pfl" in s3_text, "PFL output missing"
    # Verify Houston-specific surface parameters appear in the output
    assert "0.14" in s3_text, "Summer albedo (0.14) missing"
    assert "0.3" in s3_text, "Summer Bowen ratio (0.3) missing"
    assert "0.6" in s3_text, "Summer roughness (0.6) missing"
    print("  Stage 3: all checks passed")

    # Print a summary of the monthly parameters
    print("\n--- Houston Monthly Surface Parameters ---")
    print(f"  {'Month':<6} {'Albedo':<8} {'Bowen':<8} {'Rough (m)':<10}")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, m in enumerate(months):
        print(f"  {m:<6} {HOUSTON_ALBEDO[i]:<8.2f} "
              f"{HOUSTON_BOWEN[i]:<8.1f} {HOUSTON_ROUGHNESS[i]:<10.2f}")

    print("\nTutorial 6 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 6 Solution: AERMET for Houston, TX")
    parser.add_argument("--output-dir", default="tutorial6_output",
                        help="Directory for generated files")
    args = parser.parse_args()
    main(args.output_dir)
