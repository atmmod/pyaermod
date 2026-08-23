"""Download and unpack the full EPA AERMOD test-case archive.

Usage::

    python tests/fixtures/epa_official/download_all.py [--force]

Fetches
<https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_test_cases.zip>
(~489 MB zipped, ~10.6 GB unpacked: three reference sets,
aermet24142_aermod24142 / aermet24142_aermod26135 / aermet26135_aermod26135)
and unpacks it under tests/fixtures/epa_official/full/. Tests locate the
set to use via ``pyaermod.epa_testcases.find_epa_testcase_set``.

Tests that need the full archive skip cleanly if that directory is
absent, so this is a one-time opt-in for developers who want the full
regression coverage.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = (
    "https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/"
    "aermod_test_cases.zip"
)


def main() -> int:
    here = Path(__file__).parent
    full_dir = here / "full"
    zip_path = here / "aermod_test_cases.zip"

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download and re-extract even if files exist",
    )
    args = parser.parse_args()

    if full_dir.exists() and not args.force:
        print(f"{full_dir} already exists; pass --force to re-download.")
        return 0

    if not zip_path.exists() or args.force:
        print(f"Downloading {URL} ...")
        with urllib.request.urlopen(URL) as resp, open(zip_path, "wb") as out:
            total = 0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                total += len(chunk)
                print(f"  {total / 1e6:6.1f} MB", end="\r")
        print()

    print(f"Unpacking to {full_dir} ...")
    full_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(full_dir)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
