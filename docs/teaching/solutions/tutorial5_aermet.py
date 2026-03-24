"""
Tutorial 5 Solution — Processing Meteorological Data with AERMET
=================================================================

This script generates the three AERMET stage input files using the Atlanta,
GA example from the student guide: KATL surface station with Peachtree City
(72215) upper air data, suburban default surface parameters.

Usage:
    python tutorial5_aermet.py [--output-dir DIR]

Outputs:
    aermet_stage1.inp  — Stage 1: Extract & QA/QC
    aermet_stage2.inp  — Stage 2: Merge
    aermet_stage3.inp  — Stage 3: Boundary layer parameters
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


def create_atlanta_surface_station() -> AERMETStation:
    """Atlanta Hartsfield-Jackson Airport (KATL) surface station."""
    return AERMETStation(
        station_id="KATL",
        station_name="Atlanta Hartsfield",
        latitude=33.6300,
        longitude=-84.4400,
        time_zone=-5,
        elevation=315.0,
        anemometer_height=10.0,
    )


def create_peachtree_upper_air() -> UpperAirStation:
    """Peachtree City, GA upper air (radiosonde) station."""
    return UpperAirStation(
        station_id="72215",
        station_name="Peachtree City",
        latitude=33.3600,
        longitude=-84.5700,
    )


# --- Suburban default monthly surface parameters ---
# From the student guide Table (Section 8, Step 4).
# These are reasonable for moderate suburban development with scattered trees.
SUBURBAN_ALBEDO = [0.35, 0.35, 0.25, 0.18, 0.15, 0.15,
                   0.15, 0.15, 0.18, 0.25, 0.35, 0.35]

SUBURBAN_BOWEN = [1.5, 1.5, 1.0, 0.8, 0.6, 0.5,
                  0.5, 0.5, 0.6, 0.8, 1.0, 1.5]

SUBURBAN_ROUGHNESS = [0.30, 0.30, 0.30, 0.30, 0.50, 0.50,
                      0.50, 0.50, 0.50, 0.30, 0.30, 0.30]


def build_stage1(station: AERMETStation,
                 upper_air: UpperAirStation) -> AERMETStage1:
    """Stage 1: Extract and QA/QC raw weather data."""
    return AERMETStage1(
        surface_station=station,
        surface_data_file="72219013874.dat",
        surface_format="ISHD",
        upper_air_station=upper_air,
        upper_air_data_file="72215.dat",
        start_date="2020/01/01",
        end_date="2020/12/31",
        extract_file="stage1.ext",
        qa_file="stage1_qa.out",
        output_file="aermet_s1.out",
    )


def build_stage2() -> AERMETStage2:
    """Stage 2: Merge surface and upper air extracted data."""
    return AERMETStage2(
        surface_extract="stage1.ext",
        upper_air_extract="stage1_ua.ext",
        start_date="2020/01/01",
        end_date="2020/12/31",
        merge_file="stage2.mrg",
        output_file="aermet_s2.out",
    )


def build_stage3(station: AERMETStation) -> AERMETStage3:
    """Stage 3: Compute boundary layer parameters with suburban defaults."""
    return AERMETStage3(
        merge_file="stage2.mrg",
        station=station,
        albedo=SUBURBAN_ALBEDO,
        bowen=SUBURBAN_BOWEN,
        roughness=SUBURBAN_ROUGHNESS,
        start_date="2020/01/01",
        end_date="2020/12/31",
        surface_file="aermod.sfc",
        profile_file="aermod.pfl",
        output_file="aermet_s3.out",
    )


def main(output_dir: str = ".") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    station = create_atlanta_surface_station()
    upper_air = create_peachtree_upper_air()

    # --- Stage 1 ---
    stage1 = build_stage1(station, upper_air)
    s1_text = stage1.to_aermet_input()
    s1_path = out / "aermet_stage1.inp"
    s1_path.write_text(s1_text)
    print(f"  Stage 1 written to {s1_path}")

    # --- Stage 2 ---
    stage2 = build_stage2()
    s2_text = stage2.to_aermet_input()
    s2_path = out / "aermet_stage2.inp"
    s2_path.write_text(s2_text)
    print(f"  Stage 2 written to {s2_path}")

    # --- Stage 3 ---
    stage3 = build_stage3(station)
    s3_text = stage3.to_aermet_input()
    s3_path = out / "aermet_stage3.inp"
    s3_path.write_text(s3_text)
    print(f"  Stage 3 written to {s3_path}")

    # --- Verification ---
    print("\n--- Verification ---")

    # Stage 1 checks
    assert "KATL" in s1_text, "Surface station ID KATL missing"
    assert "72215" in s1_text, "Upper air station ID 72215 missing"
    assert "ISHD" in s1_text, "Surface format ISHD missing"
    assert "2020/01/01" in s1_text, "Start date missing"
    assert "2020/12/31" in s1_text, "End date missing"
    assert "72219013874.dat" in s1_text, "Surface data file missing"
    assert "72215.dat" in s1_text, "Upper air data file missing"
    print("  Stage 1: all checks passed")
    print("    Surface: KATL (Atlanta Hartsfield, 33.63N 84.44W, 315m)")
    print("    Upper Air: 72215 (Peachtree City, 33.36N 84.57W)")
    print("    Period: 2020/01/01 - 2020/12/31, Format: ISHD")

    # Stage 2 checks
    assert "stage1.ext" in s2_text, "Surface extract file missing"
    assert "stage2.mrg" in s2_text, "Merge output file missing"
    print("  Stage 2: all checks passed")
    print("    Merge: stage1.ext + stage1_ua.ext -> stage2.mrg")

    # Stage 3 checks
    assert "stage2.mrg" in s3_text, "Merge file reference missing"
    assert "aermod.sfc" in s3_text, "SFC output file missing"
    assert "aermod.pfl" in s3_text, "PFL output file missing"
    # Verify suburban surface parameters
    assert "0.15" in s3_text, "Summer albedo (0.15) missing"
    assert "0.5" in s3_text, "Summer Bowen ratio (0.5) missing"
    print("  Stage 3: all checks passed")
    print("    Output: aermod.sfc / aermod.pfl")

    # Print monthly surface parameters
    print("\n--- Suburban Default Monthly Parameters ---")
    print(f"  {'Month':<6} {'Albedo':<8} {'Bowen':<8} {'Rough (m)':<10}")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, m in enumerate(months):
        print(f"  {m:<6} {SUBURBAN_ALBEDO[i]:<8.2f} "
              f"{SUBURBAN_BOWEN[i]:<8.1f} {SUBURBAN_ROUGHNESS[i]:<10.2f}")

    # Compare to Houston values (Tutorial 6)
    print("\n--- Key Differences vs. Houston (Tutorial 6) ---")
    print("  Atlanta suburban has higher albedo in winter (0.35 vs 0.18)")
    print("  Atlanta suburban has higher Bowen ratio (drier, less Gulf moisture)")
    print("  Atlanta suburban has lower roughness (residential vs industrial)")

    print("\nTutorial 5 solution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tutorial 5 Solution: Processing Meteorological Data with AERMET")
    parser.add_argument("--output-dir", default="tutorial5_output",
                        help="Directory for generated files")
    args = parser.parse_args()
    main(args.output_dir)
