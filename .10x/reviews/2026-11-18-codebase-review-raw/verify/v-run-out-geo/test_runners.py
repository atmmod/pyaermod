"""Verifier tests for slice-d findings D1, D3, D4, D5 (fail at HEAD)."""

from __future__ import annotations

import os
import platform
import signal
import stat
import time
from pathlib import Path

import pytest

from pyaermod import AERSCREENConfig, AERSCREENRunner, AERSCREENSourceType
from pyaermod import AERSURFACEConfig, AERSURFACERunner
from pyaermod.runner import AERMODRunner

posix_only = pytest.mark.skipif(platform.system() == "Windows", reason="POSIX stand-ins")


def _exe(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _lock_is_free(lock_path: Path) -> bool:
    import fcntl
    with open(lock_path, "w") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return True


# ---------------------------------------------------------------- D1
@posix_only
@pytest.mark.parametrize("blocker", ["a.out", "a.subproc.stdout"])
def test_d1_failed_stage_or_capture_leaves_no_lock_or_link(tmp_path, tmp_path_factory, blocker):
    """run() must not leave the work-dir lock held, nor aermod.inp behind,
    when staging or output capture fails -- even while the caller keeps the
    exception (which keeps the traceback frames, and so the lock handle, alive)."""
    deck = tmp_path / "a.inp"
    deck.write_text("CO STARTING\nCO FINISHED\n")
    (tmp_path / blocker).mkdir()          # cannot be unlinked / opened for writing
    runner = AERMODRunner(executable_path=_exe(tmp_path_factory.mktemp('bin') / 'aermod', '#!/bin/bash\nexit 0\n'), log_level="WARNING")

    held = None
    try:
        runner.run(str(deck), working_dir=str(tmp_path), timeout=10)
    except Exception as exc:              # a GUI or batch loop that collects errors
        held = exc
    assert held is None or held.__traceback__ is not None  # keep it alive on purpose

    assert _lock_is_free(tmp_path / ".pyaermod.lock"), "flock still held after a failed run"
    assert not (tmp_path / "aermod.inp").exists() and not (tmp_path / "aermod.inp").is_symlink()


# ---------------------------------------------------------------- D3
FAKE_OUTPUT = """\
 AERSCREEN 21112 / AERMOD 26135                                      01/01/26
 TITLE: UnitTest
 **********************  AERSCREEN MAXIMUM IMPACT SUMMARY  *********************
 FLAT TERRAIN        1.913       1.913       1.722       1.148      0.1913
 DISTANCE FROM SOURCE       1610.00 meters
"""


@posix_only
def test_d3_aerscreen_does_not_report_success_from_a_previous_runs_files(tmp_path):
    cfg = AERSCREENConfig(
        title="UnitTest", source_type=AERSCREENSourceType.POINT, emission_rate=5.0,
        stack_height=10.0, stack_diameter=1.0, stack_temp=400.0, exit_velocity=10.0,
        albedo=0.16, bowen_ratio=0.8, roughness_length=0.1,
    )
    helpers = {n: _exe(tmp_path / f"fake_{n}", "#!/bin/sh\nexit 0\n")
               for n in ("aermod", "makemet", "bpipprm", "aermap")}

    def runner(exe):
        return AERSCREENRunner(executable_path=exe, aermod_path=helpers["aermod"],
                               makemet_path=helpers["makemet"], bpipprm_path=helpers["bpipprm"],
                               aermap_path=helpers["aermap"])

    good = _exe(tmp_path / "good", (
        "#!/bin/bash\ncat > /dev/null\n"
        f"cat > AERSCREEN.OUT <<'EOF'\n{FAKE_OUTPUT}EOF\n"
        "printf 'banner\\nAERSCREEN Finished Successfully\\n' > aerscreen.log\nexit 0\n"))
    bad = _exe(tmp_path / "bad", "#!/bin/bash\ncat > /dev/null\necho 'ERROR: bad input'\nexit 0\n")

    work = tmp_path / "work"
    assert runner(good).run(cfg, working_dir=work, timeout=20).success
    second = runner(bad).run(cfg, working_dir=work, timeout=20)
    assert not second.success, "second run wrote nothing and printed an error, yet success=True"
    assert second.summary is None


# ---------------------------------------------------------------- D4
@posix_only
def test_d4_aersurface_run_that_writes_no_sfcchar_file_is_not_success(tmp_path):
    nlcd = tmp_path / "stub.img"
    nlcd.write_bytes(b"x")
    cfg = AERSURFACEConfig(title="T", site_id="S", latitude=44.0, longitude=-123.0,
                           land_cover_file=str(nlcd), nlcd_year=2019)
    # exits 0, complains in words other than FATAL, writes nothing
    exe = _exe(tmp_path / "fake_aersurface",
               "#!/bin/bash\necho 'ERROR: cannot open raster'\nexit 0\n")
    result = AERSURFACERunner(executable_path=exe).run(cfg, working_dir=tmp_path / "wd", timeout=10)
    assert not (tmp_path / "wd" / cfg.sfcchar_file).exists()
    assert not result.success


# ---------------------------------------------------------------- D5
def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@posix_only
def test_d5_aerscreen_timeout_kills_the_childs_children(tmp_path):
    cfg = AERSCREENConfig(
        title="UnitTest", source_type=AERSCREENSourceType.POINT, emission_rate=5.0,
        stack_height=10.0, stack_diameter=1.0, stack_temp=400.0, exit_velocity=10.0,
        albedo=0.16, bowen_ratio=0.8, roughness_length=0.1,
    )
    helpers = {n: _exe(tmp_path / f"fake_{n}", "#!/bin/sh\nexit 0\n")
               for n in ("aermod", "makemet", "bpipprm", "aermap")}
    pidfile = tmp_path / "grandchild.pid"
    parent = _exe(tmp_path / "fake_aerscreen",
                  f"#!/bin/bash\nsleep 60 &\necho $! > {pidfile}\nwait\n")
    runner = AERSCREENRunner(executable_path=parent, aermod_path=helpers["aermod"],
                             makemet_path=helpers["makemet"], bpipprm_path=helpers["bpipprm"],
                             aermap_path=helpers["aermap"])
    pid = None
    try:
        result = runner.run(cfg, working_dir=tmp_path / "work", timeout=1)
        assert not result.success and "timed out" in result.error_message
        pid = int(pidfile.read_text())
        time.sleep(0.5)
        assert not _alive(pid), "grandchild (stand-in for AERMOD) outlived the timeout"
    finally:
        if pid is None and pidfile.exists():
            pid = int(pidfile.read_text())
        if pid and _alive(pid):
            os.kill(pid, signal.SIGKILL)
