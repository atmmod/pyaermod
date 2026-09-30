"""How AERMAPRunner decides whether an AERMAP run succeeded.

AERMAP exits with code 0 even after fatal errors, so the runner has to
read AERMAP's own verdict from its message file, ``<input stem>.out``:
the ``*** AERMAP Finishes Successfully ***`` line and the final message
summary. These tests pin that rule against real AERMAP 24142 runs
recorded in ``tests/fixtures/aermap_runner/`` (see its README):

* ``success/``: the deck the writer produces, 0 fatal errors;
* ``domain_error_e310/``: a domain past the DEM, four fatal E310 errors,
  exit code 0 and empty receptor and source files left behind;
* ``old_writer_setup_errors/``: the deck the writer produced before it
  was fixed, 11 fatal setup errors and exit code 0.

The fake ``aermap`` below replays those recordings. The same checks
against the real binary live in ``tests/test_real_aermap.py``.
"""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

import pytest

from pyaermod.terrain import AERMAPRunner, TerrainProcessor, _read_aermap_verdict

RECORDINGS = Path(__file__).parent / "fixtures" / "aermap_runner"
SUCCESS = RECORDINGS / "success"
E310 = RECORDINGS / "domain_error_e310"
OLD_WRITER = RECORDINGS / "old_writer_setup_errors"

E310_FIRST = (
    "OU E310 line 29 CHKEXT: Domain Coordinate is NOT Inside a DEM File. Pt.= 1"
)

posix_only = pytest.mark.skipif(
    platform.system() == "Windows", reason="the replaying fake aermap is a bash script",
)


# ---------------------------------------------------------------------------
# The recordings themselves
# ---------------------------------------------------------------------------


class TestRecordings:

    @pytest.mark.parametrize("case", [SUCCESS, E310, OLD_WRITER])
    def test_aermap_exits_zero_in_every_case(self, case):
        assert (case / "exit_code.txt").read_text().strip() == "0"

    def test_synth_dem_is_the_planar_test_dem(self, tmp_path):
        from tests.test_real_aermap import _write_synthetic_dem

        _write_synthetic_dem(tmp_path / "synth.dem")
        assert (tmp_path / "synth.dem").read_bytes() == (RECORDINGS / "synth.dem").read_bytes()

    def test_failed_run_leaves_empty_output_files(self):
        """Why the presence of the RECEPTOR file cannot be the success test."""
        assert (E310 / "aermap_receptors.out").exists()
        assert (E310 / "aermap_receptors.out").stat().st_size == 0


# ---------------------------------------------------------------------------
# _read_aermap_verdict
# ---------------------------------------------------------------------------


class TestReadVerdict:

    def test_success(self):
        v = _read_aermap_verdict(SUCCESS / "aermap.out")
        assert v.finished_successfully is True
        assert v.fatal_count == 0
        assert v.warning_count == 0
        assert v.fatal_errors == []

    def test_domain_error(self):
        v = _read_aermap_verdict(E310 / "aermap.out")
        assert v.finished_successfully is False
        assert v.fatal_count == 4
        assert v.fatal_errors[0] == E310_FIRST
        assert [e.split()[1] for e in v.fatal_errors] == ["E310"] * 4

    def test_old_writer_errors_are_listed_in_order(self):
        v = _read_aermap_verdict(OLD_WRITER / "aermap.out")
        assert v.finished_successfully is False
        assert v.fatal_count == 11
        assert v.warning_count == 3
        codes = [e.split()[1] for e in v.fatal_errors]
        assert codes == ["E203", "E200", "E130", "E130", "E208", "E200",
                         "E105", "E120", "E105", "E105", "E194"]
        assert v.fatal_errors[0] == (
            "CO E203 line 8 TERRHT: Invalid Parameter Specified.  "
            "Troubled Parameter: TERRHGTS"
        )
        # A routine name shorter than six characters is right-justified.
        assert "RE E105 line 19 SETUP: Invalid Keyword" in v.fatal_errors[6]

    def test_run_that_stopped_after_its_setup_summary(self, tmp_path):
        """A setup summary and its SETUP line are not AERMAP's verdict."""
        text = (E310 / "aermap.out").read_text(encoding="latin-1")
        head, _sep, _tail = text.rpartition(" *** Message Summary For AERMAP Execution ***")
        assert "SETUP Finishes UN-successfully" in head
        truncated = tmp_path / "aermap.out"
        # Keep the setup summary only: the run stopped before its final one.
        truncated.write_text(head, encoding="latin-1")
        v = _read_aermap_verdict(truncated)
        assert v.finished_successfully is False

    def test_missing_banner_is_not_success(self, tmp_path):
        text = (SUCCESS / "aermap.out").read_text(encoding="latin-1")
        cut = tmp_path / "aermap.out"
        cut.write_text(text.replace("*** AERMAP Finishes Successfully ***", ""), encoding="latin-1")
        v = _read_aermap_verdict(cut)
        assert v.finished_successfully is False
        assert v.fatal_count == 0

    @pytest.mark.parametrize(("case", "finished"), [(SUCCESS, True), (E310, False)])
    def test_crlf_line_ends(self, tmp_path, case, finished):
        crlf = tmp_path / "aermap.out"
        crlf.write_bytes((case / "aermap.out").read_bytes().replace(b"\n", b"\r\n"))
        v = _read_aermap_verdict(crlf)
        assert v.finished_successfully is finished
        assert v.fatal_count == (0 if finished else 4)

    def test_file_without_a_summary(self, tmp_path):
        empty = tmp_path / "aermap.out"
        empty.write_text("")
        v = _read_aermap_verdict(empty)
        assert v.finished_successfully is False
        assert v.fatal_count is None
        assert v.fatal_errors == []


# ---------------------------------------------------------------------------
# AERMAPRunner.run against a fake aermap that replays the recordings
# ---------------------------------------------------------------------------

# AERMAP called as ``aermap run.inp`` writes its messages to ``run.out``.
_REPLAY = """#!/bin/bash
# Replay the recorded AERMAP run whose deck matches the input file.
out="${{1%.*}}.out"
for case in "{recordings}"/*/; do
    if cmp -s "$1" "$case/aermap.inp"; then
        cat "$case/stdout.txt"
        cp "$case/aermap.out" "$out"
        for f in aermap_receptors.out aermap_sources.out; do
            if [ -e "$case/$f" ]; then cp "$case/$f" .; fi
        done
        exit "$(cat "$case/exit_code.txt")"
    fi
done
echo "no recording for this deck" >&2
exit 99
"""


def _fake(tmp_path: Path, script: str) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "aermap"
    exe.write_text(script)
    exe.chmod(0o755)
    return exe


@pytest.fixture()
def replay_exe(tmp_path):
    """A fake ``aermap`` that replays the recording whose deck it is given."""
    return _fake(tmp_path, _REPLAY.format(recordings=RECORDINGS))


def _stage(case: Path, work: Path, name: str = "run") -> Path:
    work.mkdir(parents=True, exist_ok=True)
    inp = work / f"{name}.inp"
    shutil.copy(case / "aermap.inp", inp)
    return inp


def _run(case: Path, exe: Path, work: Path, name: str = "run"):
    runner = AERMAPRunner(executable_path=exe, log_level="CRITICAL")
    return runner.run(_stage(case, work, name), working_dir=work)


@posix_only
class TestRunnerVerdict:

    def test_success(self, replay_exe, tmp_path):
        result = _run(SUCCESS, replay_exe, tmp_path / "w")
        assert result.success is True
        assert result.return_code == 0
        assert result.finished_successfully is True
        assert result.fatal_count == 0
        assert result.warning_count == 0
        assert result.fatal_errors == []
        assert result.error_message is None
        assert result.message_file == str(tmp_path / "w" / "run.out")

    def test_domain_error_with_exit_code_zero_is_a_failure(self, replay_exe, tmp_path):
        """The E310 run exits 0 and leaves output files; the old rule called it a success."""
        result = _run(E310, replay_exe, tmp_path / "w")
        assert result.return_code == 0
        assert (tmp_path / "w" / "aermap_receptors.out").exists()
        assert result.success is False
        assert result.finished_successfully is False
        assert result.fatal_count == 4
        assert result.error_message == E310_FIRST + " (and 3 more fatal error(s))"

    def test_old_writer_deck_is_a_failure(self, replay_exe, tmp_path):
        result = _run(OLD_WRITER, replay_exe, tmp_path / "w")
        assert result.return_code == 0
        assert result.success is False
        assert result.fatal_count == 11
        assert result.error_message.startswith("CO E203 line 8 TERRHT: Invalid Parameter")
        assert result.error_message.endswith("(and 10 more fatal error(s))")

    def test_message_file_follows_the_input_name(self, replay_exe, tmp_path):
        result = _run(SUCCESS, replay_exe, tmp_path / "w", name="site.v2")
        assert result.success is True
        assert result.message_file == str(tmp_path / "w" / "site.v2.out")

    def test_nonzero_exit_fails_even_with_a_good_out_file(self, tmp_path):
        exe = _fake(tmp_path, (
            "#!/bin/bash\n"
            f'cp "{SUCCESS}/aermap.out" "${{1%.*}}.out"\n'
            "exit 3\n"
        ))
        result = _run(SUCCESS, exe, tmp_path / "w")
        assert result.success is False
        assert result.finished_successfully is True
        assert result.error_message == "AERMAP exited with code 3"

    def test_no_message_file_fails(self, tmp_path):
        exe = _fake(tmp_path, "#!/bin/bash\nexit 0\n")
        result = _run(SUCCESS, exe, tmp_path / "w")
        assert result.success is False
        assert result.message_file is None
        assert result.finished_successfully is None
        assert result.error_message == "AERMAP wrote no message file run.out"

    def test_crash_without_a_message_file_gives_the_exit_code(self, tmp_path):
        exe = _fake(tmp_path, "#!/bin/bash\nexit 2\n")
        result = _run(SUCCESS, exe, tmp_path / "w")
        assert result.success is False
        assert result.return_code == 2
        assert result.error_message == "AERMAP wrote no message file run.out; exit code 2"

    def test_stale_message_file_is_not_this_runs_verdict(self, tmp_path):
        """A success .out from an earlier run must not vouch for a run that wrote none."""
        work = tmp_path / "w"
        work.mkdir()
        shutil.copy(SUCCESS / "aermap.out", work / "run.out")
        exe = _fake(tmp_path, "#!/bin/bash\nexit 0\n")
        result = _run(SUCCESS, exe, work)
        assert result.success is False
        assert "wrote no message file" in result.error_message

    def test_message_file_without_the_banner_fails(self, tmp_path):
        cut = tmp_path / "cut.out"
        cut.write_text(
            (SUCCESS / "aermap.out").read_text(encoding="latin-1")
            .replace("*** AERMAP Finishes Successfully ***", ""),
            encoding="latin-1",
        )
        exe = _fake(tmp_path, f'#!/bin/bash\ncp "{cut}" "${{1%.*}}.out"\nexit 0\n')
        result = _run(SUCCESS, exe, tmp_path / "w")
        assert result.success is False
        assert "lacks AERMAP's '*** AERMAP Finishes Successfully ***' line" in result.error_message

    def test_fatal_total_without_a_listed_message_fails(self, tmp_path):
        """AERMAP's own total counts even when no message line can be read."""
        text = (SUCCESS / "aermap.out").read_text(encoding="latin-1")
        forged = tmp_path / "forged.out"
        forged.write_text(
            text.replace("A Total of          0 Fatal Error", "A Total of          2 Fatal Error"),
            encoding="latin-1",
        )
        exe = _fake(tmp_path, f'#!/bin/bash\ncp "{forged}" "${{1%.*}}.out"\nexit 0\n')
        result = _run(SUCCESS, exe, tmp_path / "w")
        assert result.success is False
        assert result.error_message == "AERMAP reported 2 fatal error(s) in run.out"

    def test_unreadable_message_file_fails_and_says_why(self, replay_exe, tmp_path, monkeypatch):
        from pyaermod import terrain

        def _unreadable(path):
            raise PermissionError("permission denied")

        monkeypatch.setattr(terrain, "_read_aermap_verdict", _unreadable)
        result = _run(SUCCESS, replay_exe, tmp_path / "w")
        assert result.success is False
        assert result.error_message.startswith("AERMAP's verdict is unknown: could not read")
        assert "permission denied" in result.error_message


@posix_only
class TestTerrainProcessorStopsOnAERMAPErrors:

    def test_domain_error_raises_instead_of_returning_no_elevations(self, tmp_path):
        """TerrainProcessor.process used to go on to parse the empty files and return."""
        from pyaermod.input_generator import (
            AERMODProject,
            ControlPathway,
            DiscreteReceptor,
            MeteorologyPathway,
            OutputPathway,
            PointSource,
            ReceptorPathway,
            SourcePathway,
        )

        exe = _fake(tmp_path, (
            "#!/bin/bash\n"
            f'cp "{E310}/aermap.out" "${{1%.*}}.out"\n'
            f'cp "{E310}/aermap_receptors.out" "{E310}/aermap_sources.out" .\n'
            "exit 0\n"
        ))
        project = AERMODProject(
            control=ControlPathway(title_one="t"),
            sources=SourcePathway(),
            receptors=ReceptorPathway(discrete_receptors=[
                DiscreteReceptor(x_coord=500100.0, y_coord=4000100.0),
            ]),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )
        project.sources.add_source(PointSource(
            source_id="STACK1", x_coord=500200.0, y_coord=4000300.0,
            stack_height=50.0, emission_rate=1.0,
        ))
        with pytest.raises(RuntimeError, match="AERMAP failed: OU E310"):
            TerrainProcessor().process(
                project, bounds=(0, 0, 0, 0), aermap_exe=exe,
                working_dir=tmp_path / "w", utm_zone=13, datum="NAD27",
                skip_download=True, dem_files=["synth.dem"],
            )
