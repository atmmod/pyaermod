"""Tests for the AERSCREEN runner, against a scripted stand-in binary.

The stand-in records what it was fed on stdin and what its PATH was,
then produces the files a real run leaves behind, so the staging and
the verdict logic are exercised without EPA's programs. The real
programs are exercised in ``test_real_aerscreen.py``.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pyaermod import AERSCREENConfig, AERSCREENRunner, AERSCREENSourceType
from pyaermod.aerscreen import DISCRETE_RECEPTOR_FILE

FAKE_OUTPUT = """\
 AERSCREEN 21112 / AERMOD 26135                                      01/01/26
                                                                     00:00:00

 TITLE: UnitTest

 **********************  AERSCREEN MAXIMUM IMPACT SUMMARY  *********************
 FLAT TERRAIN        1.913       1.913       1.722       1.148      0.1913

 DISTANCE FROM SOURCE       1610.00 meters
"""


@pytest.fixture
def cfg():
    return AERSCREENConfig(
        title="UnitTest",
        source_type=AERSCREENSourceType.POINT,
        emission_rate=5.0,
        stack_height=10.0,
        stack_diameter=1.0,
        stack_temp=400.0,
        exit_velocity=10.0,
        albedo=0.16, bowen_ratio=0.8, roughness_length=0.1,
    )


def _executable(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def fake_aerscreen(tmp_path, *, exit_code=0, finish=True, output="AERSCREEN.OUT",
                   sleep=0):
    """A stand-in that behaves like AERSCREEN's file side."""
    stem = output[:-4]
    default = output.upper() == "AERSCREEN.OUT"
    log = "aerscreen.log" if default else f"{stem}.log"
    max_conc = "max_conc_distance.txt" if default else f"{stem}_max_conc_distance.txt"
    verdict = "AERSCREEN Finished Successfully" if finish else "Stopping AERSCREEN"
    return _executable(tmp_path / "fake_aerscreen", (
        "#!/bin/bash\n"
        f"sleep {sleep}\n"
        "cat > stdin.txt\n"
        'printf "%s" "$PATH" > path.txt\n'
        f"cat > {output} <<'EOF'\n{FAKE_OUTPUT}EOF\n"
        f"printf 'banner\\n{verdict}\\n' > {log}\n"
        f"touch {max_conc}\n"
        f"exit {exit_code}\n"
    ))


def fake_helper(tmp_path, name):
    return _executable(tmp_path / f"fake_{name}", "#!/bin/sh\nexit 0\n")


@pytest.fixture
def runner(tmp_path):
    def make(**kw):
        exe = fake_aerscreen(tmp_path, **kw)
        return AERSCREENRunner(
            executable_path=exe,
            aermod_path=fake_helper(tmp_path, "aermod"),
            makemet_path=fake_helper(tmp_path, "makemet"),
            bpipprm_path=fake_helper(tmp_path, "bpipprm"),
            aermap_path=fake_helper(tmp_path, "aermap"),
        )
    return make


class TestExecutableDiscovery:
    def test_explicit_path_must_exist(self):
        with pytest.raises(FileNotFoundError):
            AERSCREENRunner(executable_path="/nonexistent/aerscreen")

    def test_path_search_raises_when_missing(self, monkeypatch):
        monkeypatch.setattr(os, "environ", {"PATH": "/nonexistent"})
        with pytest.raises(FileNotFoundError, match="No AERSCREEN executable"):
            AERSCREENRunner()

    def test_explicit_paths_used(self, tmp_path):
        exe = fake_aerscreen(tmp_path)
        aermod = fake_helper(tmp_path, "aermod")
        r = AERSCREENRunner(executable_path=exe, aermod_path=aermod)
        assert r.executable == exe.resolve()
        assert r.helpers["aermod"] == aermod.resolve()

    def test_helper_path_must_exist(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="makemet"):
            AERSCREENRunner(executable_path=fake_aerscreen(tmp_path),
                            makemet_path="/nonexistent/makemet")

    def test_helpers_found_on_path(self, tmp_path, monkeypatch):
        exe = fake_aerscreen(tmp_path)
        bindir = tmp_path / "bin"
        bindir.mkdir()
        for name in ("aermod", "makemet"):
            _executable(bindir / name, "#!/bin/sh\n")
        monkeypatch.setenv("PATH", str(bindir))
        r = AERSCREENRunner(executable_path=exe)
        assert r.helpers["aermod"] == (bindir / "aermod").resolve()
        assert r.helpers["bpipprm"] is None


class TestStaging:
    def test_required_helpers_follow_the_configuration(self, runner, cfg):
        r = runner()
        assert r.required_helpers(cfg) == ["aermod", "makemet"]
        cfg.downwash, cfg.bpip_file = True, "b.inp"
        assert r.required_helpers(cfg) == ["aermod", "makemet", "bpipprm"]
        cfg.terrain, cfg.lat, cfg.lon = True, 40.0, -80.0
        assert r.required_helpers(cfg) == ["aermod", "makemet", "bpipprm", "aermap"]
        cfg.downwash = cfg.terrain = False
        cfg.fumigation, cfg.run_aermod = True, False
        assert r.required_helpers(cfg) == ["makemet"]

    def test_missing_helper_is_named(self, tmp_path, cfg):
        r = AERSCREENRunner(executable_path=fake_aerscreen(tmp_path),
                            makemet_path=fake_helper(tmp_path, "makemet"))
        r.helpers["aermod"] = None
        with pytest.raises(FileNotFoundError, match="aermod"):
            r.stage(cfg, tmp_path / "wd", "prompts")

    def test_helpers_and_markers_are_staged(self, runner, cfg, tmp_path):
        r = runner()
        work = tmp_path / "wd"
        r.stage(cfg, work, "prompts")
        for name, marker in (("aermod", "AERMOD.EXE"), ("makemet", "MAKEMET.EXE"),
                             ("aermap", "AERMAP.EXE")):
            assert (work / name).resolve() == r.helpers[name]
            assert (work / marker).resolve() == r.helpers[name]
        wrapper = (work / "bpipprm").read_text()
        assert str(r.helpers["bpipprm"]) in wrapper
        assert "fort.10" in wrapper and "fort.12" in wrapper
        assert os.access(work / "bpipprm", os.X_OK)
        assert (work / "BPIPPRM.EXE").resolve() == (work / "bpipprm").resolve()

    def test_prompt_mode_writes_answers_and_removes_stale_restart(self, runner, cfg, tmp_path):
        work = tmp_path / "wd"
        work.mkdir()
        (work / "aerscreen.inp").write_text("stale")
        answers = runner().stage(cfg, work, "prompts")
        assert answers.name == "aerscreen_answers.txt"
        assert answers.read_text() == "\n".join(cfg.to_stdin_answers()) + "\n"
        assert not (work / "aerscreen.inp").exists()

    def test_restart_mode_writes_the_restart_file(self, runner, cfg, tmp_path):
        work = tmp_path / "wd"
        restart = runner().stage(cfg, work, "restart")
        assert restart == work / "aerscreen.inp"
        assert restart.read_text() == cfg.to_aerscreen_input()

    def test_unknown_mode(self, runner, cfg, tmp_path):
        with pytest.raises(ValueError, match="mode"):
            runner().stage(cfg, tmp_path / "wd", "interactive")

    def test_auxiliary_inputs_are_copied(self, runner, cfg, tmp_path):
        sc = tmp_path / "inputs" / "season_3.out"
        sc.parent.mkdir()
        sc.write_text("FREQ_SECT SEASONAL 1\n")
        cfg.albedo = cfg.bowen_ratio = cfg.roughness_length = None
        cfg.surface_file = str(sc)
        cfg.discrete_receptors = (100.0, 250.5)
        work = tmp_path / "wd"
        runner().stage(cfg, work, "prompts")
        assert (work / "season_3.out").read_text() == "FREQ_SECT SEASONAL 1\n"
        assert (work / DISCRETE_RECEPTOR_FILE).read_text() == "units: meters\n100\n250.5\n"

    def test_missing_auxiliary_input_is_an_error(self, runner, cfg, tmp_path):
        cfg.downwash, cfg.bpip_file = True, str(tmp_path / "nowhere.inp")
        with pytest.raises(FileNotFoundError, match=r"nowhere\.inp"):
            runner().stage(cfg, tmp_path / "wd", "prompts")

    def test_terrain_staging(self, runner, cfg, tmp_path):
        dem = tmp_path / "ned" / "tile.tif"
        dem.parent.mkdir()
        dem.write_bytes(b"II*\0")
        grids = tmp_path / "grids"
        grids.mkdir()
        for name in ("conus.las", "conus.los"):
            (grids / name).write_bytes(b"grid")
        cfg.terrain, cfg.lat, cfg.lon = True, 40.0, -80.0
        cfg.dem_files, cfg.nad_grid_dir = [str(dem)], str(grids)
        cfg.aermap_elevation = True
        work = tmp_path / "wd"
        runner().stage(cfg, work, "prompts")
        assert (work / "tile.tif").is_file()
        assert (work / "conus.las").is_file() and (work / "conus.los").is_file()
        assert (work / "DEMlist.txt").read_text() == "NED\nNADGRIDS: ./\ntile.tif\n"

    def test_terrain_needs_dems_and_grids(self, runner, cfg, tmp_path):
        cfg.terrain, cfg.lat, cfg.lon = True, 40.0, -80.0
        with pytest.raises(ValueError, match="dem_files"):
            runner().stage(cfg, tmp_path / "wd", "prompts")
        dem = tmp_path / "tile.tif"
        dem.write_bytes(b"x")
        cfg.dem_files = [str(dem)]
        with pytest.raises(FileNotFoundError, match="NADCON"):
            runner().stage(cfg, tmp_path / "wd2", "prompts")
        empty = tmp_path / "nogrids"
        empty.mkdir()
        cfg.nad_grid_dir = str(empty)
        with pytest.raises(FileNotFoundError, match="las"):
            runner().stage(cfg, tmp_path / "wd3", "prompts")


class TestRun:
    def test_prompt_run_feeds_the_answers(self, runner, cfg, tmp_path):
        work = tmp_path / "wd"
        result = runner().run(cfg, working_dir=work, timeout=10)
        assert result.success, result.error_message
        assert (work / "stdin.txt").read_text() == "\n".join(cfg.to_stdin_answers()) + "\n"
        # The working directory leads PATH, so "aermod" resolves to the staged link.
        assert (work / "path.txt").read_text().split(os.pathsep)[0] == str(work)
        assert result.output_file == str(work / "AERSCREEN.OUT")
        assert result.log_file == str(work / "aerscreen.log")
        assert result.max_conc_file == str(work / "max_conc_distance.txt")
        assert result.summary is not None
        assert result.summary.maximum.conc_1hr == 1.913
        assert "AERSCREEN.OUT" in [os.path.basename(p) for p in result.output_files]

    def test_restart_run_feeds_the_restart_reply(self, runner, cfg, tmp_path):
        work = tmp_path / "wd"
        result = runner().run(cfg, working_dir=work, timeout=10, mode="restart")
        assert result.success
        assert (work / "stdin.txt").read_text() == "Y\n\n"
        assert result.restart_file == str(work / "aerscreen.inp")

    def test_named_output_and_its_log(self, runner, tmp_path, cfg):
        cfg.output_file = "SiteA.out"
        work = tmp_path / "wd"
        result = runner(output="SiteA.out").run(cfg, working_dir=work, timeout=10)
        assert result.success
        assert result.log_file == str(work / "SiteA.log")
        assert result.max_conc_file == str(work / "SiteA_max_conc_distance.txt")

    def test_nonzero_exit_marks_failure(self, runner, cfg, tmp_path):
        result = runner(exit_code=1).run(cfg, working_dir=tmp_path / "wd", timeout=10)
        assert not result.success
        assert result.return_code == 1
        assert "code 1" in result.error_message

    def test_unfinished_log_marks_failure(self, runner, cfg, tmp_path):
        """AERSCREEN exits 0 after a validation stop; the log is the verdict."""
        result = runner(finish=False).run(cfg, working_dir=tmp_path / "wd", timeout=10)
        assert not result.success
        assert result.return_code == 0
        assert "did not finish" in result.error_message
        assert result.summary is None

    def test_timeout(self, runner, cfg, tmp_path):
        result = runner(sleep=5).run(cfg, working_dir=tmp_path / "wd", timeout=1)
        assert not result.success
        assert "timed out" in result.error_message
        assert result.return_code is None

    def test_stdout_stderr_captured(self, tmp_path, cfg):
        exe = _executable(tmp_path / "chatty", (
            "#!/bin/bash\ncat > /dev/null\necho processed\necho 'cls: not found' >&2\n"
            "printf 'AERSCREEN Finished Successfully\\n' > aerscreen.log\n"
            f"cat > AERSCREEN.OUT <<'EOF'\n{FAKE_OUTPUT}EOF\n"
        ))
        r = AERSCREENRunner(executable_path=exe,
                            aermod_path=fake_helper(tmp_path, "aermod"),
                            makemet_path=fake_helper(tmp_path, "makemet"))
        result = r.run(cfg, working_dir=tmp_path / "wd", timeout=10)
        assert result.success
        assert "processed" in result.stdout
        assert "cls: not found" in result.stderr
