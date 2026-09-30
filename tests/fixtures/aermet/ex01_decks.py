"""EPA's AERMET test case EX01 (Albany, NY, March 1988) written with pyaermod.

The station metadata, dates, options and surface characteristics are
those of EPA's own decks, ``ex01/EX01_S1.INP`` and ``ex01/EX01_S2.INP``.
Tests import :func:`ex01_stages`; ``regenerate.sh`` runs this file to
write the decks it records::

    python tests/fixtures/aermet/ex01_decks.py OUTDIR
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple

from pyaermod.aermet import AERMETStage1, AERMETStage3, AERMETStation, UpperAirStation


def ex01_stages() -> Tuple[AERMETStage1, AERMETStage3]:
    """Stage 1 and METPREP for EX01, as EPA's EX01_S1.INP and EX01_S2.INP set them."""
    # SURFACE LOCATION 14735 42.75N 73.8W 0 83.8 (CD144 is in LST, hence 0);
    # NWS_HGT WIND 6.1.
    surface = AERMETStation(
        station_id="14735", station_name="ALBANY COUNTY AP",
        latitude=42.75, longitude=-73.8, time_zone=-5,
        elevation=83.8, anemometer_height=6.1,
    )
    # UPPERAIR LOCATION 00014735 73.80W 42.75N 5 83.8 (TD-6201 is in GMT).
    upper_air = UpperAirStation(
        station_id="00014735", station_name="ALBANY",
        latitude=42.75, longitude=-73.80, elevation=83.8,
    )
    stage1 = AERMETStage1(
        surface_station=surface, surface_data_file="S1473588.144", surface_format="CD144",
        upper_air_station=upper_air, upper_air_data_file="14735-88.UA",
        upper_air_format="6201FB",
        start_date="1988/3/1", end_date="1988/3/10",
        upper_air_audit=["UATT", "UAWS", "UALR"],
    )
    stage3 = AERMETStage3(
        station=surface,
        start_date="1988/03/01", end_date="1988/03/4",
        methods=[("REFLEVEL", "SUBNWS"), ("WIND_DIR", "RANDOM")],
        site_char=[(1, 1, 0.15, 2.0, 0.12)],
        surface_file="EX01_MP.SFC", profile_file="EX01_MP.PFL",
    )
    return stage1, stage3.with_inputs_from(stage1)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    s1, s3 = ex01_stages()
    (out / "stage1.inp").write_text(s1.to_aermet_input())
    (out / "stage3.inp").write_text(s3.to_aermet_input())
