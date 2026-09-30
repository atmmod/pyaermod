"""How AERMODRunner decides whether an AERMOD run succeeded.

AERMOD exits with code 0 even when a fatal error stops the run, so the
runner has to read AERMOD's own verdict from the ``.out`` file: the
``*** AERMOD Finishes Successfully ***`` banner and the message summary.
These tests pin that rule against real AERMOD v26135 runs recorded in
``tests/fixtures/runner/`` (see its README):

* ``success/``: completes with 0 fatal errors and 6 warnings;
* ``runtime_error_e480/``: exits 0 after fatal error E480 (ANNUAL
  averages with four days of met data), the GUI's "Run succeeded" bug;
* ``setup_error_e500/``: exits 0 after fatal error E500 (a missing
  surface file) during setup;
* ``setup_error_e322_openpit/`` and ``setup_error_e140_srcgroup/``: the
  2026-09-29 audit's OPENPIT deck with its release height above the
  pit's effective depth (E322) and its two-pit deck with SRCGROUP inside
  the source blocks (E140), both fatal at setup with exit code 0;
* ``killed_sigterm/``: a run stopped with SIGTERM part way through, which
  the fake replays by killing itself with the same signal.

The fake ``aermod`` below replays those recordings: it finds the
recording whose deck matches ``aermod.inp`` and writes back its stdout,
``aermod.out`` and exit code. The same checks against the real binary
live in ``tests/test_real_aermod.py``.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

import pyaermod
from pyaermod import cli
from pyaermod.runner import (
    AERMODMessage,
    AERMODRunner,
    BatchRunner,
    _read_message_summary,
    parse_aermod_messages,
)

RECORDINGS = Path(__file__).parent / "fixtures" / "runner"
SUCCESS = RECORDINGS / "success"
E480 = RECORDINGS / "runtime_error_e480"
E500 = RECORDINGS / "setup_error_e500"
E322 = RECORDINGS / "setup_error_e322_openpit"
E140 = RECORDINGS / "setup_error_e140_srcgroup"
KILLED = RECORDINGS / "killed_sigterm"

SUCCESS_WARNINGS = ["W206", "W361", "W362", "W362", "W214", "W403"]
E480_TEXT = "Less than 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave"

posix_only = pytest.mark.skipif(
    platform.system() == "Windows", reason="the replaying fake aermod is a bash script",
)


def _out_text(case: Path) -> str:
    return (case / "aermod.out").read_text(encoding="latin-1")


# ---------------------------------------------------------------------------
# Reading the recordings
# ---------------------------------------------------------------------------

class TestRecordings:
    """The recordings show what the rule is built on."""

    @pytest.mark.parametrize("case", [SUCCESS, E480, E500, E322, E140], ids=lambda p: p.name)
    def test_aermod_exits_zero_in_every_case(self, case):
        assert (case / "exit_code.txt").read_text().strip() == "0"

    def test_killed_run_just_stops(self):
        """SIGTERM leaves the setup banner and nothing that says the run failed."""
        assert (KILLED / "exit_code.txt").read_text().strip() == "143"
        text = _out_text(KILLED)
        assert "*** SETUP Finishes Successfully ***" in text
        assert "AERMOD Finishes" not in text
        assert "Message Summary : AERMOD Model Execution" not in text
        # Only the setup summary is there, and it lists no fatal error.
        summary = _read_message_summary(KILLED / "aermod.out")
        assert summary.finished_successfully is False
        assert summary.counts["E"] == 0
        assert {m.severity for m in summary.messages} == {"W"}

    def test_failed_run_still_prints_the_setup_success_banner(self):
        """Why "FINISHES SUCCESSFULLY" anywhere in the file is not a success test."""
        text = _out_text(E480)
        assert "*** SETUP Finishes Successfully ***" in text
        assert "*** AERMOD Finishes UN-successfully ***" in text
        assert "AERMOD FINISHES SUCCESSFULLY" not in text.upper()


class TestParseAermodMessages:

    def test_success_has_warnings_and_no_fatal_errors(self):
        messages = parse_aermod_messages(SUCCESS / "aermod.out")
        assert [m.code for m in messages] == SUCCESS_WARNINGS
        assert {m.severity for m in messages} == {"W"}
        assert messages[0] == AERMODMessage(
            severity="W", pathway="CO", code="W206", line="4", module="MODOPT",
            text="Regulatory DFAULT Overrides Non-DFAULT Option For", detail="FLAT",
        )
        # A detail field with a blank inside it stays whole.
        assert messages[-1].detail == "SigA & SigW"
        assert messages[-1].pathway == "MX"

    def test_e480_is_listed_with_its_text(self):
        messages = parse_aermod_messages(E480 / "aermod.out")
        assert messages[0] == AERMODMessage(
            severity="E", pathway="MX", code="E480", line="97", module="MAIN",
            text=E480_TEXT, detail="NUMYRS=0",
        )
        assert str(messages[0]) == f"E480 MAIN: {E480_TEXT} NUMYRS=0"

    def test_only_the_final_summary_is_read(self):
        """The E480 run lists its 4 setup warnings twice; each is kept once."""
        text = _out_text(E480)
        assert text.count("MODOPT: Regulatory DFAULT Overrides") == 2
        codes = [m.code for m in parse_aermod_messages(E480 / "aermod.out")]
        assert codes == ["E480", "W206", "W361", "W214", "W403", "W481"]

    def test_setup_error_e500(self):
        messages = parse_aermod_messages(E500 / "aermod.out")
        assert messages[0] == AERMODMessage(
            severity="E", pathway="ME", code="E500", line="30", module="MEOPEN",
            text="Fatal Error Occurs Opening the Data File of", detail="SURFFILE",
        )
        assert [m.code for m in messages[1:]] == SUCCESS_WARNINGS

    def test_totals_and_banner(self):
        success = _read_message_summary(SUCCESS / "aermod.out")
        assert success.counts == {"E": 0, "W": 6, "I": 0}
        assert success.finished_successfully is True
        e480 = _read_message_summary(E480 / "aermod.out")
        assert e480.counts == {"E": 1, "W": 5, "I": 0}
        assert e480.finished_successfully is False
        e500 = _read_message_summary(E500 / "aermod.out")
        assert e500.counts == {"E": 1, "W": 6, "I": 0}
        assert e500.finished_successfully is False

    def test_banner_text_in_a_title_does_not_count(self, tmp_path):
        """The banner must be a line of its own, not text echoed from the deck."""
        text = _out_text(E480).replace(
            "   TITLEONE  GUI demo: 65 m stack, Albany NY met",
            "   TITLEONE  *** AERMOD Finishes Successfully ***", 1,
        )
        out = tmp_path / "aermod.out"
        out.write_text(text, encoding="latin-1")
        assert _read_message_summary(out).finished_successfully is False

    @pytest.mark.parametrize("case,finished", [(SUCCESS, True), (E480, False)],
                             ids=["success", "e480"])
    def test_crlf_line_ends(self, tmp_path, case, finished):
        """Windows builds end lines with CRLF, as EPA's reference outputs do."""
        out = tmp_path / "aermod.out"
        out.write_bytes((case / "aermod.out").read_bytes().replace(b"\n", b"\r\n"))
        summary = _read_message_summary(out)
        assert summary.finished_successfully is finished
        assert summary == _read_message_summary(case / "aermod.out")

    def test_large_file_reads_the_tail(self, tmp_path, monkeypatch):
        """Past the tail size only the end of the file is read."""
        import pyaermod.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_SUMMARY_TAIL_BYTES", 5000)
        summary = _read_message_summary(SUCCESS / "aermod.out")
        assert summary.finished_successfully is True
        assert [m.code for m in summary.messages] == SUCCESS_WARNINGS

    def test_run_that_stopped_before_its_final_summary(self, tmp_path, monkeypatch):
        """A crash mid-run leaves only the setup summary and no banner.

        The file is the E480 recording cut off after its input summary
        pages, so the tail holds no summary and the whole file is read.
        """
        import pyaermod.runner as runner_mod

        monkeypatch.setattr(runner_mod, "_SUMMARY_TAIL_BYTES", 5000)
        text = _out_text(E480)
        cut = text.index(" *** Message Summary : AERMOD Model Execution ***")
        out = tmp_path / "aermod.out"
        out.write_text(text[:cut], encoding="latin-1")
        assert out.stat().st_size > 5000
        summary = _read_message_summary(out)
        assert summary.finished_successfully is False
        assert [m.code for m in summary.messages] == ["W206", "W361", "W214", "W403"]
        assert summary.counts == {"E": 0, "W": 4, "I": 0}

    def test_file_without_a_summary(self, tmp_path):
        text = _out_text(SUCCESS)
        out = tmp_path / "aermod.out"
        out.write_text(text[:text.index("*** Message Summary")], encoding="latin-1")
        assert parse_aermod_messages(out) == []
        assert _read_message_summary(out) == ([], {}, False)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_aermod_messages(tmp_path / "nope.out")


# ---------------------------------------------------------------------------
# AERMODRunner.run against a fake aermod that replays the recordings
# ---------------------------------------------------------------------------

_REPLAY = """#!/bin/bash
# Replay the recorded AERMOD run whose deck matches aermod.inp.
for case in "{recordings}"/*/; do
    if cmp -s aermod.inp "$case/aermod.inp"; then
        cat "$case/stdout.txt"
        cp "$case/aermod.out" aermod.out
        code="$(cat "$case/exit_code.txt")"
        # The shell reports death by signal N as 128 + N: die the same way.
        if [ "$code" -gt 128 ]; then kill -"$((code - 128))" $$; fi
        exit "$code"
    fi
done
echo "no recording for this deck" >&2
exit 99
"""


@pytest.fixture()
def replay_bin(tmp_path):
    """A directory holding ``aermod``, a fake that replays the recordings."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "aermod"
    exe.write_text(_REPLAY.format(recordings=RECORDINGS))
    exe.chmod(0o755)
    return bindir


@pytest.fixture()
def e480_bin(tmp_path):
    """A fake ``aermod`` that answers every deck with the E480 recording."""
    bindir = tmp_path / "e480bin"
    bindir.mkdir()
    exe = bindir / "aermod"
    exe.write_text(
        "#!/bin/bash\n"
        f'cat "{E480}/stdout.txt"\n'
        f'cp "{E480}/aermod.out" aermod.out\n'
        f'exit "$(cat "{E480}/exit_code.txt")"\n'
    )
    exe.chmod(0o755)
    return bindir


def _stage(case: Path, work: Path, name: str = "run") -> Path:
    """Copy a recording's deck into ``work`` as ``<name>.inp``."""
    work.mkdir(parents=True, exist_ok=True)
    inp = work / f"{name}.inp"
    shutil.copy(case / "aermod.inp", inp)
    return inp


def _stage_readable(case: Path, work: Path, name: str = "run") -> Path:
    """Like ``_stage``, with the station IDs written as integers.

    The recorded decks carry the GUI's ``SURFDATA 14735.0 1988.0``, which
    AERMOD accepts but ``read_aermod_input`` does not yet read. Callers
    that parse the deck first (the CLI, a sweep) get integers instead.
    """
    inp = _stage(case, work, name)
    inp.write_text(inp.read_text().replace("14735.0  1988.0", "14735  1988"))
    return inp


def _run(case: Path, replay_bin: Path, work: Path):
    runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
    return runner.run(_stage(case, work), working_dir=work)


@posix_only
class TestRunnerVerdict:

    def test_success(self, replay_bin, tmp_path):
        result = _run(SUCCESS, replay_bin, tmp_path / "w")
        assert result.success is True
        assert result.return_code == 0
        assert result.finished_successfully is True
        assert result.fatal_count == 0
        assert result.fatal_messages == []
        assert result.warning_count == 6
        assert [m.code for m in result.warning_messages] == SUCCESS_WARNINGS
        assert result.informational_count == 0
        assert result.error_message is None
        assert result.output_file == str(tmp_path / "w" / "run.out")

    def test_e480_with_exit_code_zero_is_a_failure(self, replay_bin, tmp_path):
        """Defect D1: exit code 0 and a complete .out, but AERMOD stopped."""
        result = _run(E480, replay_bin, tmp_path / "w")
        assert result.return_code == 0
        assert result.output_file is not None
        assert result.success is False
        assert result.finished_successfully is False
        assert result.fatal_count == 1
        (fatal,) = result.fatal_messages
        assert (fatal.code, fatal.pathway, fatal.text) == ("E480", "MX", E480_TEXT)
        assert result.warning_count == 5
        assert result.error_message == f"E480 MAIN: {E480_TEXT} NUMYRS=0"
        assert "Fatal Error Occurred During Runtime Phase" in result.stdout

    def test_setup_error_e500(self, replay_bin, tmp_path):
        result = _run(E500, replay_bin, tmp_path / "w")
        assert result.return_code == 0
        assert result.success is False
        assert [m.code for m in result.fatal_messages] == ["E500"]
        assert [m.code for m in result.warning_messages] == SUCCESS_WARNINGS
        assert result.error_message == (
            "E500 MEOPEN: Fatal Error Occurs Opening the Data File of SURFFILE"
        )

    def test_nonzero_exit_fails_even_with_a_good_out_file(self, replay_bin, tmp_path):
        exe = replay_bin / "aermod"
        replay = exe.read_text()
        assert 'exit "$code"' in replay
        exe.write_text(replay.replace('exit "$code"', "exit 3"))
        result = _run(SUCCESS, replay_bin, tmp_path / "w")
        assert result.finished_successfully is True
        assert result.fatal_count == 0
        assert result.success is False
        assert result.error_message == "AERMOD failed with return code 3"

    def test_out_file_without_the_banner_fails(self, replay_bin, tmp_path):
        """An .out cut short (AERMOD killed mid-run) is not a success."""
        recordings = tmp_path / "recordings"
        truncated = recordings / "truncated"
        truncated.mkdir(parents=True)
        shutil.copy(SUCCESS / "aermod.inp", truncated / "aermod.inp")
        (truncated / "stdout.txt").write_text("")
        (truncated / "exit_code.txt").write_text("0\n")
        text = _out_text(SUCCESS)
        (truncated / "aermod.out").write_text(
            text[:text.index(" *** Message Summary : AERMOD Model Execution ***")],
            encoding="latin-1",
        )
        exe = replay_bin / "aermod"
        exe.write_text(exe.read_text().replace(str(RECORDINGS), str(recordings)))

        result = _run(SUCCESS, replay_bin, tmp_path / "w")
        assert result.return_code == 0
        assert result.fatal_count == 0
        assert result.success is False
        assert "no '*** AERMOD Finishes Successfully ***' line in run.out" in result.error_message

    def test_unreadable_out_file_fails_and_says_why(self, replay_bin, tmp_path,
                                                     monkeypatch, caplog):
        import pyaermod.runner as runner_mod

        def _unreadable(path):
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(runner_mod, "_read_message_summary", _unreadable)
        with caplog.at_level("WARNING", logger="pyaermod.runner"):
            result = _run(SUCCESS, replay_bin, tmp_path / "w")
        assert result.success is False
        assert result.finished_successfully is False
        assert result.messages == []
        assert any("Could not read AERMOD output file" in r.getMessage()
                   for r in caplog.records)

    def test_exit_zero_without_an_out_file_fails(self, tmp_path):
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        exe.chmod(0o755)
        work = tmp_path / "w"
        runner = AERMODRunner(executable_path=exe, log_level="WARNING")
        result = runner.run(_stage(SUCCESS, work), working_dir=work)
        assert result.success is False
        assert result.output_file is None
        assert result.error_message == "AERMOD exited with code 0 but wrote no run.out"

    @pytest.mark.parametrize(("case", "codes"), [
        (E322, ["E322"]),
        (E140, ["E140", "E140"]),
    ], ids=["e322_openpit", "e140_srcgroup"])
    def test_audit_setup_errors_fail(self, replay_bin, tmp_path, case, codes):
        """The audit's E322 and E140 decks: exit code 0, fatal at setup."""
        result = _run(case, replay_bin, tmp_path / "w")
        assert result.return_code == 0
        assert result.success is False
        assert result.finished_successfully is False
        assert [m.code for m in result.fatal_messages] == codes
        assert result.error_message.startswith(f"{codes[0]} ")

    def test_sigterm_reports_the_signal(self, replay_bin, tmp_path):
        """A killed run says it was killed, not that a banner is missing."""
        result = _run(KILLED, replay_bin, tmp_path / "w")
        assert result.return_code == -15
        assert result.success is False
        assert result.output_file == str(tmp_path / "w" / "run.out")
        assert result.error_message == (
            "AERMOD was stopped by SIGTERM (signal 15) before it finished; "
            "its output ends where the run was cut off"
        )

    def test_earlier_out_does_not_stand_in_for_this_run(self, replay_bin, tmp_path):
        """A run that writes no .out must not be judged by the last run's."""
        work = tmp_path / "w"
        first = _run(SUCCESS, replay_bin, work)
        assert first.success is True
        exe = replay_bin / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        result = AERMODRunner(executable_path=exe, log_level="WARNING").run(
            work / "run.inp", working_dir=work)
        assert result.success is False
        assert result.output_file is None
        assert result.error_message == "AERMOD exited with code 0 but wrote no run.out"
        assert not (work / "run.out").exists()

    def test_leftover_aermod_out_is_not_adopted(self, tmp_path):
        """An aermod.out left by an interrupted run is not this run's output."""
        work = tmp_path / "w"
        inp = _stage(SUCCESS, work)
        shutil.copy(SUCCESS / "aermod.out", work / "aermod.out")
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        exe.chmod(0o755)
        result = AERMODRunner(executable_path=exe, log_level="WARNING").run(inp, working_dir=work)
        assert result.success is False
        assert result.output_file is None
        assert not (work / "aermod.out").exists()

    def test_timeout_keeps_this_runs_partial_out(self, tmp_path):
        """The .out a timed-out run leaves is its own, not the last run's."""
        work = tmp_path / "w"
        inp = _stage(SUCCESS, work)
        shutil.copy(SUCCESS / "aermod.out", work / "run.out")  # an earlier run
        exe = tmp_path / "aermod"
        exe.write_text(
            "#!/bin/bash\n"
            f'cp "{KILLED}/aermod.out" aermod.out\n'
            "exec sleep 60\n"
        )
        exe.chmod(0o755)
        result = AERMODRunner(executable_path=exe, log_level="WARNING").run(
            inp, working_dir=work, timeout=5)
        assert result.success is False
        assert result.error_message == (
            "Execution timed out after 5 seconds; AERMOD was stopped before it finished"
        )
        assert result.output_file == str(work / "run.out")
        assert (work / "run.out").read_bytes() == (KILLED / "aermod.out").read_bytes()
        assert not (work / "aermod.out").exists()

    def test_deck_named_aermod_inp_runs_in_place(self, replay_bin, tmp_path):
        """EPA's default deck name: the runner used to delete the deck.

        It replaced ``<work_dir>/aermod.inp`` with a link to the deck,
        which was ``aermod.inp`` itself, so the deck was deleted and the
        link pointed to itself; AERMOD then found no input.
        """
        work = tmp_path / "w"
        inp = _stage(SUCCESS, work, "aermod")
        deck = inp.read_bytes()
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        result = runner.run(inp)
        assert result.success is True, result.error_message
        assert result.output_file == str(work / "aermod.out")
        assert not inp.is_symlink()
        assert inp.read_bytes() == deck

    def test_a_sibling_deck_leaves_aermod_inp_and_its_results(self, replay_bin, tmp_path):
        """A base deck named aermod.inp beside a variant survives the variant's run.

        The runner used to delete ``<work_dir>/aermod.inp`` to link the
        variant in its place, and to remove ``aermod.out``, the base
        deck's results, as a leftover.
        """
        work = tmp_path / "w"
        base = _stage(SUCCESS, work, "aermod")
        variant = _stage(SUCCESS, work, "case2")
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        assert runner.run(base).success is True
        deck = base.read_bytes()
        results = (work / "aermod.out").read_bytes()

        result = runner.run(variant)
        assert result.success is False
        assert "already holds another deck named aermod.inp" in result.error_message
        assert result.input_file == str(variant)
        assert not base.is_symlink()
        assert base.read_bytes() == deck
        assert (work / "aermod.out").read_bytes() == results
        assert not (work / "case2.out").exists()

        # The same variant runs in a working directory of its own.
        apart = runner.run(variant, working_dir=tmp_path / "apart")
        assert apart.success is True, apart.error_message

    def test_run_batch_beside_aermod_inp_keeps_it(self, replay_bin, tmp_path):
        work = tmp_path / "w"
        base = _stage(SUCCESS, work, "aermod")
        variant = _stage(SUCCESS, work, "case2")
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        results = runner.run_batch([base, variant], n_workers=1)
        assert [r.success for r in results] == [True, False]
        assert "named aermod.inp" in results[1].error_message
        assert base.read_bytes() == (SUCCESS / "aermod.inp").read_bytes()
        assert (work / "aermod.out").exists()

    @pytest.mark.parametrize("given", ["link", "target"])
    def test_a_link_named_aermod_inp_to_the_deck_stays(self, replay_bin, tmp_path, given):
        """``aermod.inp -> real.inp`` runs in place whichever name is given.

        The runner replaced the link with its own, then removed it after
        the run.
        """
        work = tmp_path / "w"
        real = _stage(SUCCESS, work, "real")
        link = work / "aermod.inp"
        link.symlink_to("real.inp")
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        result = runner.run(link if given == "link" else real)
        assert result.success is True, result.error_message
        # The deck is named by the file the link resolves to.
        assert result.output_file == str(work / "real.out")
        assert link.is_symlink()
        assert os.readlink(link) == "real.inp"
        assert real.read_bytes() == (SUCCESS / "aermod.inp").read_bytes()

    def test_a_link_named_aermod_inp_to_another_deck_is_replaced(self, replay_bin, tmp_path):
        """A link is this runner's to replace; the deck it pointed to is untouched."""
        work = tmp_path / "w"
        other = _stage(E480, work, "other")
        inp = _stage(SUCCESS, work, "run")
        (work / "aermod.inp").symlink_to("other.inp")
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        result = runner.run(inp)
        assert result.success is True, result.error_message
        assert not (work / "aermod.inp").is_symlink()
        assert not (work / "aermod.inp").exists()
        assert other.read_bytes() == (E480 / "aermod.inp").read_bytes()

    @staticmethod
    def _no_links(monkeypatch):
        """Make symbolic links fail, as on Windows without the privilege."""
        def _refuse(self, *args, **kwargs):
            raise OSError("symbolic link privilege not held")
        monkeypatch.setattr(Path, "symlink_to", _refuse)

    def test_the_copy_fallback_cleans_up(self, replay_bin, tmp_path, monkeypatch):
        self._no_links(monkeypatch)
        work = tmp_path / "w"
        result = _run(SUCCESS, replay_bin, work)
        assert result.success is True, result.error_message
        assert not (work / "aermod.inp").exists()
        assert not (work / ".pyaermod-aermod-inp.sha256").exists()

    @pytest.mark.parametrize("next_deck", ["same", "other"])
    def test_a_copy_left_by_a_killed_runner_is_replaced(self, replay_bin, tmp_path,
                                                        monkeypatch, next_deck):
        """The copy fallback's aermod.inp, left when Python is killed mid-run.

        The runner took that copy for another deck named aermod.inp and
        refused every later run in the directory, this deck's included.
        Here the fake AERMOD SIGKILLs the Python process that started it,
        so the runner's cleanup never runs.
        """
        work = tmp_path / "w"
        # The killed run's deck: this one, or another deck (other bytes).
        first = _stage(SUCCESS if next_deck == "same" else E480, work, "case1")
        killer = tmp_path / "kill_parent"
        killer.write_text("#!/bin/bash\nkill -9 $PPID\n")
        killer.chmod(0o755)
        child = (
            "from pathlib import Path\n"
            "def _refuse(self, *a, **k):\n"
            "    raise OSError('symbolic link privilege not held')\n"
            "Path.symlink_to = _refuse\n"
            "from pyaermod.runner import AERMODRunner\n"
            f"AERMODRunner(executable_path={str(killer)!r}, log_level='CRITICAL')"
            f".run({str(first)!r})\n"
        )
        env = {**os.environ, "PYTHONPATH": str(Path(pyaermod.__file__).parents[1])}
        killed = subprocess.run([sys.executable, "-c", child], env=env, timeout=60)
        assert killed.returncode == -9
        left = work / "aermod.inp"
        assert left.is_file() and not left.is_symlink()
        assert left.read_bytes() == first.read_bytes()

        self._no_links(monkeypatch)
        deck = first if next_deck == "same" else _stage(SUCCESS, work, "case2")
        assert (deck.read_bytes() == left.read_bytes()) == (next_deck == "same")
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        result = runner.run(deck)
        assert result.success is True, result.error_message
        assert result.output_file == str(work / f"{deck.stem}.out")
        assert not left.exists()
        assert not (work / ".pyaermod-aermod-inp.sha256").exists()

    def test_an_unmarked_copy_of_the_deck_is_kept(self, replay_bin, tmp_path, monkeypatch):
        """Matching bytes alone do not make aermod.inp the runner's copy.

        A variant copied from a base deck kept as aermod.inp, and not yet
        edited, has the base deck's bytes; the base deck is still a deck.
        """
        self._no_links(monkeypatch)
        work = tmp_path / "w"
        inp = _stage(SUCCESS, work)
        shutil.copy2(inp, work / "aermod.inp")
        result = _run(SUCCESS, replay_bin, work)
        assert result.success is False
        assert "already holds another deck named aermod.inp" in result.error_message
        assert (work / "aermod.inp").read_bytes() == inp.read_bytes()

    def test_a_marker_does_not_cover_a_deck_put_in_the_copys_place(self, replay_bin, tmp_path):
        """The marker names the copy's bytes, so a deck written over it is kept."""
        work = tmp_path / "w"
        base = _stage(E480, work, "aermod")
        (work / ".pyaermod-aermod-inp.sha256").write_text("0" * 64 + "\n")
        variant = _stage(SUCCESS, work, "case2")
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        result = runner.run(variant)
        assert result.success is False
        assert "already holds another deck named aermod.inp" in result.error_message
        assert base.read_bytes() == (E480 / "aermod.inp").read_bytes()

    @pytest.mark.parametrize("name", ["run", "aermod"])
    def test_working_dir_apart_from_the_deck(self, replay_bin, tmp_path, name):
        """The aermod.inp link reaches a deck in another directory."""
        inp = _stage(SUCCESS, tmp_path / "decks", name)
        work = tmp_path / "w"
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        result = runner.run(inp, working_dir=work)
        assert result.success is True, result.error_message
        assert result.output_file == str(work / f"{name}.out")
        assert not (work / "aermod.inp").exists()
        assert inp.read_bytes() == (SUCCESS / "aermod.inp").read_bytes()

    def test_run_batch_inherits_the_verdict(self, replay_bin, tmp_path):
        work = tmp_path / "batch"
        inputs = [_stage(SUCCESS, work, "ok"), _stage(E480, work, "annual")]
        runner = AERMODRunner(executable_path=replay_bin / "aermod", log_level="WARNING")
        # One working directory per deck would not change the verdict; the
        # runner's directory lock serializes the two runs here.
        results = {Path(r.input_file).stem: r for r in runner.run_batch(inputs, n_workers=1)}
        assert results["ok"].success is True
        assert results["annual"].success is False
        assert [m.code for m in results["annual"].fatal_messages] == ["E480"]

    def test_parameter_sweep_inherits_the_verdict(self, e480_bin, tmp_path):
        """BatchRunner writes its own decks; each one answered with E480 fails."""
        from pyaermod.input_reader import read_aermod_input

        project = read_aermod_input(_stage_readable(E480, tmp_path / "deck"))
        runner = AERMODRunner(executable_path=e480_bin / "aermod", log_level="WARNING")
        results = BatchRunner(runner).parameter_sweep(
            project, "emission_rate", [50.0, 100.0], tmp_path / "sweep", n_workers=1,
        )
        assert set(results) == {50.0, 100.0}
        for result in results.values():
            assert result.return_code == 0
            assert result.success is False
            assert result.error_message.startswith("E480 MAIN:")


class TestExtractErrorMessage:
    """``_extract_error_message`` puts AERMOD's own fatal error first."""

    def _runner(self, tmp_path):
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        exe.chmod(0o755)
        return AERMODRunner(executable_path=exe, log_level="WARNING")

    def test_counts_further_fatal_errors(self, tmp_path):
        first = AERMODMessage("E", "ME", "E500", "30", "MEOPEN",
                              "Fatal Error Occurs Opening the Data File of", "SURFFILE")
        second = AERMODMessage("E", "ME", "E500", "31", "MEOPEN",
                               "Fatal Error Occurs Opening the Data File of", "PROFFILE")
        proc = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        files = {"error": tmp_path / "run.err", "output": E500 / "aermod.out"}
        msg = self._runner(tmp_path)._extract_error_message(
            proc, files, messages=[first, second], finished_successfully=False,
        )
        assert msg == (
            "E500 MEOPEN: Fatal Error Occurs Opening the Data File of SURFFILE "
            "(and 1 more fatal error(s))"
        )

    def test_signal_without_a_name(self, tmp_path):
        proc = CompletedProcess(args=[], returncode=-200, stdout="", stderr="")
        files = {"error": tmp_path / "run.err", "output": KILLED / "aermod.out"}
        msg = self._runner(tmp_path)._extract_error_message(
            proc, files, messages=[], finished_successfully=False,
        )
        assert msg.startswith("AERMOD was stopped by signal 200 before it finished")

    def test_summary_heading_is_not_taken_for_an_error(self, tmp_path):
        """Without parsed messages the .out scan skips AERMOD's section heading."""
        text = _out_text(SUCCESS)
        out = tmp_path / "run.out"
        out.write_text(text[:text.index(" *** Message Summary : AERMOD Model Execution ***")],
                       encoding="latin-1")
        proc = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        files = {"error": tmp_path / "run.err", "output": out}
        msg = self._runner(tmp_path)._extract_error_message(
            proc, files, messages=[], finished_successfully=False,
        )
        assert "FATAL ERROR MESSAGES" not in msg
        assert msg == (
            "AERMOD did not report success: no '*** AERMOD Finishes "
            "Successfully ***' line in run.out"
        )


# ---------------------------------------------------------------------------
# The command-line paths inherit the verdict
# ---------------------------------------------------------------------------

@posix_only
class TestCommandLine:

    def test_pyaermod_run_exits_nonzero_on_e480(self, e480_bin, tmp_path, capsys):
        work = tmp_path / "w"
        inp = _stage_readable(E480, work)
        code = cli.main(["run", str(inp), "--executable", str(e480_bin / "aermod"),
                         "--working-dir", str(work), "--force"])
        out = capsys.readouterr().out
        assert code == 1
        assert "AERMOD failed (return_code=0)" in out
        assert "Success" not in out

    def test_python_m_runner_reports_the_fatal_error(self, replay_bin, tmp_path):
        work = tmp_path / "w"
        inp = _stage(E480, work)
        src = str(Path(pyaermod.__file__).resolve().parent.parent)
        env = dict(os.environ)
        env["PATH"] = f"{replay_bin}{os.pathsep}{env.get('PATH', '')}"
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (src, env.get("PYTHONPATH")) if p
        )
        proc = subprocess.run(
            [sys.executable, "-m", "pyaermod.runner", str(inp)],
            capture_output=True, text=True, env=env, timeout=120, check=False,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "Status: FAILED" in proc.stdout
        assert "Messages: 1 fatal error(s), 5 warning(s)" in proc.stdout
        assert f"MX E480 MAIN: {E480_TEXT} NUMYRS=0" in proc.stdout
