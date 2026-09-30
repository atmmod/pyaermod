"""
The AERMET deck writers and runner against the real AERMET binary.

Skips if ``aermet`` isn't on PATH (``make test-binaries`` puts ``bin/``
there; build it with ``scripts/build_aermod.sh aermet``). Parallel to
test_real_aermod.py and test_real_aermap.py.

* The recorded runs in ``tests/fixtures/aermet/runs/`` (the offline
  counterpart, ``tests/test_aermet_status.py``) are repeated on this
  binary: the same verdict and the same error codes.
* Check V12 of the demonstration study: pyaermod's decks for EPA's
  Cordero test case (upper air, ISHD surface and on-site data) reproduce
  EPA's ``CORDERO_FULL.SFC`` and ``.PFL`` field by field. The reference
  files are AERMET 24142's, so the comparison with them runs on a 24142
  binary; on any version the output is compared with what EPA's own
  Cordero decks produce on the same binary. Needs EPA's AERMET test cases
  (``aermet_test_cases/``, not committed).
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

from pyaermod.aermet import (
    AERMETStage1,
    AERMETStage3,
    AERMETStation,
    OnsiteData,
    UpperAirStation,
)
from pyaermod.aermet_runner import AERMETRunner, run_aermet_pipeline

pytestmark = pytest.mark.skipif(
    shutil.which("aermet") is None,
    reason="AERMET binary not found on PATH",
)

FIXTURES = Path(__file__).parent / "fixtures" / "aermet"
RUNS = FIXTURES / "runs"
TEST_CASES = (
    Path(__file__).resolve().parent.parent / "aermet_test_cases" / "aermet_def_testcases_24142"
)
CORDERO = TEST_CASES / "cordero"
needs_cordero = pytest.mark.skipif(
    not (CORDERO / "CORD_ST1.INP").exists(),
    reason=f"EPA's Cordero AERMET test case not found: {CORDERO}",
)


def _ex01_stages():
    spec = importlib.util.spec_from_file_location("ex01_decks", FIXTURES / "ex01_decks.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ex01_stages()


def _normalized(path: Path) -> list:
    """Lines of an SFC/PFL file with blanks collapsed (the V12 comparison)."""
    return [" ".join(line.split()) for line in path.read_text().replace("\r", "").splitlines()]


def _placeholder_stage1(tmp_path: Path) -> AERMETStage1:
    sfc = tmp_path / "surface.isd"
    sfc.write_text("placeholder\n")
    ua = tmp_path / "upper.fsl"
    ua.write_text("placeholder\n")
    return AERMETStage1(
        job_id="SMOKE",
        surface_station=AERMETStation(
            station_id="94847", station_name="TEST_SFC",
            latitude=42.36, longitude=-71.01, time_zone=-5,
            anemometer_height=10.0, elevation=20.0,
        ),
        surface_data_file=sfc.name,
        upper_air_station=UpperAirStation(
            station_id="74494", station_name="TEST_UA",
            latitude=42.36, longitude=-71.01, elevation=20.0,
        ),
        upper_air_data_file=ua.name,
        start_date="2020/01/01",
        end_date="2020/01/02",
    )


def test_aermet_runner_executable_introspection():
    """Runner finds the binary and exposes its path."""
    runner = AERMETRunner()
    assert runner.executable is not None
    assert runner.executable.exists()


def test_placeholder_data_is_reported_as_a_failure(tmp_path):
    """AERMET exits 0 on data it cannot read; the runner still says it failed."""
    deck_path = tmp_path / "stage1.inp"
    deck_path.write_text(_placeholder_stage1(tmp_path).to_aermet_input(), encoding="utf-8")
    result = AERMETRunner().run_stage(1, deck_path, working_dir=tmp_path, timeout=60)
    assert result.return_code is not None
    assert result.success is False
    assert result.finished_successfully is False
    assert result.error_count >= 1
    assert result.error_message


@pytest.mark.parametrize("case", sorted(p.name for p in RUNS.iterdir() if p.is_dir()))
def test_recorded_runs_repeat_on_this_binary(tmp_path, case):
    """Each recorded run gets the same verdict and error codes here."""
    recording = RUNS / case
    for data in ("14735-88.UA", "S1473588.144"):
        shutil.copy(FIXTURES / "ex01" / data, tmp_path / data)
    runner = AERMETRunner(log_level="WARNING")
    if case == "metprep_success":
        stage1, _ = _ex01_stages()
        (tmp_path / "pre.inp").write_text(stage1.to_aermet_input())
        assert runner.run_stage(1, tmp_path / "pre.inp", working_dir=tmp_path).success
    shutil.copy(recording / "deck.inp", tmp_path / "deck.inp")
    result = runner.run_stage(1, tmp_path / "deck.inp", working_dir=tmp_path, timeout=120)

    recorded_out = (recording / "stdout.txt").read_text()
    assert result.success is ("AERMET FINISHED SUCCESSFULLY" in recorded_out)
    if "AERMET FINISHED" not in (result.stdout or ""):
        # AERMET 24142 crashes on METPREP without Stage 1's files (gfortran
        # "End of file" reading the empty QAOUT file) instead of listing E70;
        # the run is still reported as failed, which is what matters.
        assert not result.success and result.return_code != 0
        return
    msg_names = [p.name for p in recording.iterdir() if p.name in ("stage1.msg", "stage3.msg", "2")]
    recorded_codes = sorted(set(re.findall(r"^ .{10} (E\d\d) ", (recording / msg_names[0]).read_text(),
                                           re.MULTILINE)))
    assert sorted({m.code for m in result.errors}) == recorded_codes


def test_ex01_pipeline(tmp_path):
    for data in ("14735-88.UA", "S1473588.144"):
        shutil.copy(FIXTURES / "ex01" / data, tmp_path / data)
    stage1, stage3 = _ex01_stages()
    results = run_aermet_pipeline(stage1, None, stage3, working_dir=tmp_path, timeout=120)
    assert [(r.stage, r.success) for r in results] == [(1, True), (3, True)], [
        r.error_message for r in results]
    ours = [line.split() for line in _normalized(tmp_path / "EX01_MP.SFC")[1:]]
    epa = [line.split() for line in _normalized(FIXTURES / "ex01" / "EX01_MP.SFC")[1:]]
    for row in ours + epa:
        row[0] = str(int(row[0]) % 100)
    assert ours == epa


def cordero_stages():
    """EPA's Cordero decks (CORD_ST1.INP, CORD_ST2.INP) written with pyaermod."""
    # SURFACE LOCATION 24090 44.050N 103.07W 7 965. (ISHD, GMT) and
    # UPPERAIR LOCATION 24090 44.050N 103.08W 7 966.0 (FSL, GMT).
    surface = AERMETStation("24090", "RAPID_CITY", 44.05, -103.07, time_zone=-7,
                            elevation=965.0, anemometer_height=10.0)
    upper_air = UpperAirStation("24090", "RAPID_CITY", 44.05, -103.08, elevation=966.0)
    # ONSITE LOCATION CORDERO 105.5W 44.2N 0, read with EPA's READ/FORMAT.
    onsite = OnsiteData(
        "CORDERO", 44.2, -105.5, "imldata3.met",
        read_records=[["OSYR", "OSMO", "OSDY", "OSHR", "HT01", "WS01", "WD01", "SA01", "TT01",
                       "PAMT"]],
        format_records=["(4i2,f4.0,f6.2,f5.0,f4.0,f6.1,f8.2)"],
        threshold=0.5, audit=["WS01", "WD01", "SA01", "TT01"],
    )
    stage1 = AERMETStage1(
        surface_station=surface, surface_data_file="726620-24090-1993.ish", surface_format="ISHD",
        upper_air_station=upper_air, upper_air_data_file="rapidcity_fsl.dat",
        upper_air_format="FSL", start_date="1993/5/19", end_date="1993/7/18",
        upper_air_audit=["UAPR", "UAHT", "UATT", "UATD", "UAWD", "UAWS"], onsite=onsite,
    )
    stage3 = AERMETStage3(
        station=surface, start_date="1993/5/19", end_date="1993/7/18",
        methods=[("REFLEVEL", "SUBNWS"), ("WIND_DIR", "NORAND")],
        site_char=[(1, 1, 0.2, 3.0, 0.1)], secondary_site_char=[(1, 1, 0.2, 3.0, 0.1)],
        surface_file="CORDERO_FULL.SFC", profile_file="CORDERO_FULL.PFL",
    )
    return stage1, stage3


_CORDERO_DATA = ("726620-24090-1993.ish", "imldata3.met", "rapidcity_fsl.dat",
                 "ISHD_discard.txt", "ISHD_replace.txt")


def _cordero_dir(tmp_path: Path, name: str) -> Path:
    work = tmp_path / name
    work.mkdir()
    for data in _CORDERO_DATA:
        shutil.copy(CORDERO / data, work / data)
    return work


@needs_cordero
def test_v12_cordero_reproduces_epa_output(tmp_path):
    """V12: pyaermod's Cordero decks give EPA's SFC and PFL, field by field."""
    ours = _cordero_dir(tmp_path, "pyaermod")
    stage1, stage3 = cordero_stages()
    results = run_aermet_pipeline(stage1, None, stage3, working_dir=ours, timeout=600)
    assert [(r.stage, r.success) for r in results] == [(1, True), (3, True)], [
        r.error_message for r in results]

    # EPA's own decks on the same binary.
    epa = _cordero_dir(tmp_path, "epa")
    runner = AERMETRunner(log_level="WARNING")
    # CORD_ST1.INP names the on-site file in capitals.
    shutil.copy(CORDERO / "imldata3.met", epa / "IMLDATA3.MET")
    for deck in ("CORD_ST1.INP", "CORD_ST2.INP"):
        shutil.copy(CORDERO / deck, epa / deck)
        assert runner.run_stage(1, epa / deck, working_dir=epa, timeout=600).success, deck

    header = _normalized(ours / "CORDERO_FULL.SFC")[0]
    for name in ("CORDERO_FULL.SFC", "CORDERO_FULL.PFL"):
        assert _normalized(ours / name) == _normalized(epa / name), name
        if "VERSION: 24142" in header:
            assert _normalized(ours / name) == _normalized(CORDERO / name), name
