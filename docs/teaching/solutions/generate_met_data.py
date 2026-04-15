"""
Generate Synthetic Meteorological Data for Tutorials
=====================================================

Creates realistic synthetic .sfc and .pfl files for use with the PyAERMOD
tutorials. The data mimics Houston-area climatology (Gulf Coast, subtropical)
with diurnal and seasonal cycles, but is NOT real observational data.

Usage:
    python generate_met_data.py [--output-dir DIR] [--year YEAR] [--station LABEL]

Outputs:
    met_data.sfc  — AERMOD-format surface meteorological file (1 year, hourly)
    met_data.pfl  — AERMOD-format profile meteorological file (1 year, hourly)

These files can be copied into any tutorial working directory for use with
AERMOD.  They are synthetic and should NEVER be used for regulatory work.
"""

import argparse
import calendar
import math
import random
from datetime import datetime, timedelta
from pathlib import Path


# ─── Houston-area climatology parameters ────────────────────────────────────

# Monthly average temperature (K)
MONTHLY_TEMP_K = [
    283.2, 285.0, 288.7, 293.2, 297.6, 301.0,
    302.5, 302.6, 300.0, 295.0, 289.5, 284.5,
]

# Diurnal temperature range (K) by month
MONTHLY_DTR = [
    9.0, 9.5, 10.0, 10.5, 9.5, 9.0,
    9.0, 9.5, 10.0, 11.0, 10.0, 9.0,
]

# Monthly prevailing wind direction (degrees) — Houston: SE-S in summer, N-NW in winter
MONTHLY_WIND_DIR = [
    350.0, 360.0, 170.0, 170.0, 170.0, 170.0,
    180.0, 180.0, 170.0, 360.0, 350.0, 350.0,
]

# Monthly mean wind speed (m/s) at 10 m
MONTHLY_WIND_SPEED = [
    4.0, 4.3, 4.5, 4.5, 4.2, 3.8,
    3.5, 3.3, 3.5, 3.8, 4.0, 3.9,
]

# Monthly average relative humidity (%)
MONTHLY_RH = [
    75.0, 73.0, 72.0, 73.0, 76.0, 77.0,
    78.0, 78.0, 77.0, 74.0, 75.0, 76.0,
]

# Monthly mean cloud cover (tenths, 0-10)
MONTHLY_CCVR = [6, 6, 5, 5, 5, 4, 4, 4, 5, 4, 5, 6]

# Monthly albedo, Bowen ratio, and roughness (Houston suburban/industrial)
MONTHLY_ALBEDO = [
    0.18, 0.18, 0.16, 0.14, 0.14, 0.14,
    0.14, 0.14, 0.15, 0.16, 0.17, 0.18,
]
MONTHLY_BOWEN = [
    0.8, 0.7, 0.5, 0.4, 0.3, 0.3,
    0.3, 0.3, 0.4, 0.5, 0.7, 0.8,
]
MONTHLY_ROUGHNESS = [
    0.40, 0.40, 0.50, 0.60, 0.60, 0.60,
    0.60, 0.60, 0.60, 0.50, 0.45, 0.40,
]

# Station pressure (mb) — Houston near sea level
STATION_PRESSURE = 1013.0

# Latitude for solar calculation
STATION_LAT = 29.65


def _solar_elevation(jday: int, hour: int, lat_deg: float) -> float:
    """Approximate solar elevation angle (degrees). Negative = nighttime."""
    lat = math.radians(lat_deg)
    decl = math.radians(23.45 * math.sin(math.radians(360 / 365 * (jday - 81))))
    # Hour angle: 12 = solar noon
    ha = math.radians(15.0 * (hour - 12))
    sin_elev = (math.sin(lat) * math.sin(decl) +
                math.cos(lat) * math.cos(decl) * math.cos(ha))
    return math.degrees(math.asin(max(-1, min(1, sin_elev))))


def _compute_boundary_layer(solar_elev: float, wind_speed: float,
                            cloud_cover: int, roughness: float,
                            temp_k: float) -> dict:
    """Compute simplified boundary layer parameters for one hour."""
    is_daytime = solar_elev > 0
    ws = max(wind_speed, 0.5)  # floor wind speed

    # Friction velocity (m/s) — simple log-law estimate
    ustar = 0.4 * ws / math.log(10.0 / roughness)
    ustar = max(ustar, 0.05)

    if is_daytime:
        # Convective conditions
        # Sensible heat flux scales with solar elevation and inversely with cloud
        cloud_factor = 1.0 - 0.6 * (cloud_cover / 10.0)
        max_H = 300.0 * math.sin(math.radians(max(solar_elev, 5))) * cloud_factor
        H = max(5.0, max_H * random.uniform(0.7, 1.0))

        # Convective velocity scale
        zi = 200.0 + 800.0 * math.sin(math.radians(max(solar_elev, 5)))
        zi = max(200.0, min(3000.0, zi * random.uniform(0.8, 1.2)))
        wstar = (9.81 * H * zi / (temp_k * 1004.0)) ** (1.0 / 3.0)
        wstar = max(0.1, min(3.0, wstar))

        # Monin-Obukhov length (negative = unstable)
        L = -(temp_k * ustar ** 3) / (0.4 * 9.81 * max(H / 1004.0, 0.01))
        L = max(-9999.0, min(-1.0, L))

        zic = zi       # convective mixing height
        zim = -999.0   # mechanical not applicable in strong convection
        vptg = 0.005 + random.uniform(0, 0.005)  # weak lapse above PBL
    else:
        # Stable / neutral nighttime
        H = -random.uniform(5.0, 30.0)
        wstar = -9.0  # missing for stable
        zic = -999.0   # no convective mixing height

        # Mechanical mixing height (stable boundary layer is shallow)
        zim = 50.0 + 200.0 * (ws / 5.0) * random.uniform(0.6, 1.0)
        zim = max(50.0, min(800.0, zim))

        # Monin-Obukhov length (positive = stable)
        L = 10.0 + 100.0 * (ws / 3.0) ** 2 * random.uniform(0.5, 1.5)
        L = max(5.0, min(10000.0, L))

        vptg = -9.0  # missing

    return {
        "H": H, "ustar": ustar, "wstar": wstar, "vptg": vptg,
        "zic": zic, "zim": zim, "L": L,
    }


def generate_met_data(year: int, seed: int = 42):
    """Generate one year of synthetic hourly met data. Returns (sfc_lines, pfl_lines)."""
    random.seed(seed)

    sfc_lines = []
    pfl_lines = []

    start = datetime(year, 1, 1, 1)  # AERMOD hours are 1-24
    # Determine total hours
    days_in_year = 366 if calendar.isleap(year) else 365
    total_hours = days_in_year * 24

    dt = start
    for _ in range(total_hours):
        month = dt.month
        day = dt.day
        hour = dt.hour if dt.hour != 0 else 24
        jday = dt.timetuple().tm_yday
        mi = month - 1  # 0-indexed month

        # --- Temperature with diurnal cycle ---
        # Minimum near hour 6, maximum near hour 15
        diurnal_phase = math.cos(math.radians(15 * (hour - 15)))
        temp_k = (MONTHLY_TEMP_K[mi]
                  + 0.5 * MONTHLY_DTR[mi] * diurnal_phase
                  + random.gauss(0, 1.5))

        # --- Wind ---
        wind_dir = (MONTHLY_WIND_DIR[mi]
                    + random.gauss(0, 40)) % 360
        wind_speed = max(0.5, MONTHLY_WIND_SPEED[mi]
                         + random.gauss(0, 1.5)
                         + 0.5 * math.sin(math.radians(15 * (hour - 14))))

        # --- Cloud cover ---
        ccvr = max(0, min(10, int(MONTHLY_CCVR[mi]
                                   + random.gauss(0, 2))))

        # --- Relative humidity ---
        rh = max(20.0, min(100.0,
                           MONTHLY_RH[mi]
                           + random.gauss(0, 8)
                           - 10 * diurnal_phase))

        # --- Surface parameters for this month ---
        albedo = MONTHLY_ALBEDO[mi]
        bowen = MONTHLY_BOWEN[mi]
        z0 = MONTHLY_ROUGHNESS[mi]

        # --- Solar and boundary layer ---
        solar_elev = _solar_elevation(jday, hour, STATION_LAT)
        bl = _compute_boundary_layer(solar_elev, wind_speed, ccvr, z0, temp_k)

        # --- Precipitation (occasional) ---
        ipcode = 0
        pamt = 0.0
        if random.random() < 0.03 and ccvr >= 7:
            ipcode = 1
            pamt = round(random.uniform(0.5, 5.0), 2)

        # --- Format SFC line ---
        # Columns: yr mo dy jd hr  H ustar wstar vptg zic zim L z0 bowen albedo
        #          ws wd zref_w  temp zref_t  ipcode pamt rh pres ccvr method subs
        yr2 = year % 100
        sfc_line = (
            f"{yr2:2d} {month:2d} {day:2d} {jday:3d} {hour:2d}"
            f" {bl['H']:7.1f}"
            f" {bl['ustar']:6.3f}"
            f" {bl['wstar']:6.3f}"
            f" {bl['vptg']:6.3f}"
            f" {bl['zic']:5.0f}."
            f" {bl['zim']:5.0f}."
            f" {bl['L']:9.1f}"
            f"  {z0:.4f}"
            f"   {bowen:.2f}"
            f"   {albedo:.2f}"
            f"    {wind_speed:.2f}"
            f"  {wind_dir:.1f}"
            f"   {10.0:.1f}"
            f"  {temp_k:.1f}"
            f"   {10.0:.1f}"
            f"  {ipcode:4d}"
            f"   {pamt:.2f}"
            f"   {rh:3.0f}."
            f"   {STATION_PRESSURE:.0f}."
            f"    {ccvr:2d}"
            f" NAD     NoSubs"
        )
        sfc_lines.append(sfc_line)

        # --- Format PFL line ---
        # Single measurement height at 10m (simplified, one level per hour)
        # Columns: yr mo dy hr  height top_flag wind_dir wind_speed temp sigma_theta sigma_w
        sigma_theta = max(3.0, min(30.0, 10.0 + random.gauss(0, 5)))
        sigma_w = 99.00  # missing (not measured at most stations)
        pfl_line = (
            f"{yr2:2d} {month:2d} {day:2d} {hour:2d}"
            f"    {10.0:.1f}"
            f" 1"
            f"   {wind_dir:.1f}"
            f"     {wind_speed:.2f}"
            f"     {temp_k - 273.15:.2f}"
            f"    {sigma_theta:.2f}"
            f"    {sigma_w:.2f}"
        )
        pfl_lines.append(pfl_line)

        # Advance to next hour
        dt += timedelta(hours=1)

    return sfc_lines, pfl_lines


def main(output_dir: str = ".", year: int = 2020,
         station_label: str = "HOUSTON") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Generating synthetic met data for {station_label}, year {year}...")

    sfc_lines, pfl_lines = generate_met_data(year)

    # --- SFC header ---
    sfc_header = (
        f"   {STATION_LAT:.3f}N   95.280W"
        f"          UA_ID: 72240"
        f"     SF_ID: KHOU"
        f"     OS_ID: KHOU"
        f"         VERSION: 24142"
        f"    CCVR_Sub"
    )

    sfc_path = out / "met_data.sfc"
    with open(sfc_path, "w") as f:
        f.write(sfc_header + "\n")
        for line in sfc_lines:
            f.write(line + "\n")
    print(f"  Surface file:  {sfc_path}")
    print(f"    {len(sfc_lines)} hourly records ({year})")

    pfl_path = out / "met_data.pfl"
    with open(pfl_path, "w") as f:
        for line in pfl_lines:
            f.write(line + "\n")
    print(f"  Profile file:  {pfl_path}")
    print(f"    {len(pfl_lines)} hourly records ({year})")

    # --- Quick summary ---
    print(f"\n--- Data Summary ---")
    print(f"  Station:   {station_label} (synthetic)")
    print(f"  Latitude:  {STATION_LAT:.3f}°N")
    print(f"  Longitude: 95.280°W")
    print(f"  Year:      {year}")
    print(f"  Hours:     {len(sfc_lines)}")
    print(f"  Pressure:  {STATION_PRESSURE:.0f} mb (near sea level)")
    print()
    print("  Monthly mean temperature (°C):")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, m in enumerate(months):
        print(f"    {m}: {MONTHLY_TEMP_K[i] - 273.15:.1f}")

    print()
    print("  ⚠  These are SYNTHETIC data for educational use only.")
    print("     Do NOT use for regulatory or real-world modeling.")
    print()
    print("  To use with tutorials, copy both files to the tutorial")
    print("  working directory (the same folder as the .inp file).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic met data for PyAERMOD tutorials")
    parser.add_argument("--output-dir", default=".",
                        help="Directory for output files (default: current)")
    parser.add_argument("--year", type=int, default=2020,
                        help="Year for the met data (default: 2020)")
    parser.add_argument("--station", default="HOUSTON",
                        help="Station label (default: HOUSTON)")
    args = parser.parse_args()
    main(args.output_dir, args.year, args.station)
