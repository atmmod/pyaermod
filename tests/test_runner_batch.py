"""Batch runs: what ``resume_batch`` counts as done.

``resume_batch`` used to count a deck as done when the last 50
lines of its ``.out`` mentioned "FINISHES SUCCESSFULLY", which the
``*** SETUP Finishes Successfully ***`` line of a failed or killed run
also satisfies, and it took the ``.out`` of an earlier run, or of an
earlier version of the deck, for the current one.

The ``.out`` files are the real AERMOD recordings in
``tests/fixtures/runner/`` (see its README).
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

import pytest

from pyaermod.runner import AERMODRunner
from pyaermod.runner_utils import _output_is_valid, resume_batch

RECORDINGS = Path(__file__).parent / "fixtures" / "runner"
SUCCESS = RECORDINGS / "success"
E480 = RECORDINGS / "runtime_error_e480"
E500 = RECORDINGS / "setup_error_e500"
E322 = RECORDINGS / "setup_error_e322_openpit"
E140 = RECORDINGS / "setup_error_e140_srcgroup"
KILLED = RECORDINGS / "killed_sigterm"

posix_only = pytest.mark.skipif(
    platform.system() == "Windows", reason="the fake aermod is a bash script",
)


def _deck_with_out(tmp_path: Path, case: Path, name: str = "run") -> Path:
    """Stage ``case``'s deck as ``<name>.inp`` with its ``.out`` written after it."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    inp = tmp_path / f"{name}.inp"
    shutil.copy(case / "aermod.inp", inp)
    out = tmp_path / f"{name}.out"
    shutil.copy(case / "aermod.out", out)
    deck_time = inp.stat().st_mtime
    os.utime(out, (deck_time + 10, deck_time + 10))
    return inp


# ---------------------------------------------------------------------------
# resume_batch
# ---------------------------------------------------------------------------

class TestResumeBatch:

    def test_successful_run_is_done(self, tmp_path):
        inp = _deck_with_out(tmp_path, SUCCESS)
        assert resume_batch([inp], tmp_path) == {"done": [inp], "todo": []}

    @pytest.mark.parametrize("case", [E480, E500, E322, E140, KILLED], ids=lambda p: p.name)
    def test_failed_or_killed_run_is_todo(self, tmp_path, case):
        inp = _deck_with_out(tmp_path, case)
        assert resume_batch([inp], tmp_path) == {"done": [], "todo": [inp]}

    def test_out_cut_off_just_after_setup_is_todo(self, tmp_path):
        """The setup banner near the end of an .out is not a finished run.

        A killed AERMOD's .out ends wherever its output buffer was last
        flushed. Cut the successful run's .out there, right after the
        setup banner: the old tail search found "FINISHES SUCCESSFULLY"
        in it and called the deck done.
        """
        inp = _deck_with_out(tmp_path, SUCCESS)
        text = (SUCCESS / "aermod.out").read_text(encoding="latin-1")
        banner = " *** SETUP Finishes Successfully ***"
        cut = text.index("\n", text.index(banner) + len(banner) + 1)
        out = tmp_path / "run.out"
        out.write_text(text[:cut + 1], encoding="latin-1")
        os.utime(out, (inp.stat().st_mtime + 10,) * 2)
        assert "FINISHES SUCCESSFULLY" in "\n".join(out.read_text().splitlines()[-50:]).upper()
        assert resume_batch([inp], tmp_path)["todo"] == [inp]

    def test_out_older_than_the_deck_is_stale(self, tmp_path):
        """A deck edited after its run must run again."""
        inp = _deck_with_out(tmp_path, SUCCESS)
        out_time = (tmp_path / "run.out").stat().st_mtime
        os.utime(inp, (out_time + 60, out_time + 60))
        assert resume_batch([inp], tmp_path) == {"done": [], "todo": [inp]}

    def test_missing_deck_is_judged_by_its_out(self, tmp_path):
        inp = _deck_with_out(tmp_path / "decks", SUCCESS)
        shutil.move(tmp_path / "decks" / "run.out", tmp_path / "run.out")
        inp.unlink()
        assert resume_batch([inp], tmp_path)["done"] == [inp]

    def test_empty_or_unreadable_out_is_todo(self, tmp_path, monkeypatch):
        import pyaermod.runner_utils as ru

        inp = _deck_with_out(tmp_path, SUCCESS)
        assert _output_is_valid(tmp_path / "run.out", inp) is True

        def _unreadable(path):
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(ru, "_read_message_summary", _unreadable)
        assert _output_is_valid(tmp_path / "run.out", inp) is False
        (tmp_path / "run.out").write_text("")
        assert _output_is_valid(tmp_path / "run.out", inp) is False


@posix_only
def test_timed_out_rerun_is_todo(tmp_path):
    """The pilot's case: a good run, the deck re-run, and the re-run times out.

    The runner used to skip renaming aermod.out on a timeout, so the
    first run's ``run.out`` survived under the deck's name and
    ``resume_batch`` called the deck done.
    """
    inp = _deck_with_out(tmp_path, SUCCESS)
    assert resume_batch([inp], tmp_path)["done"] == [inp]
    exe = tmp_path / "aermod"
    exe.write_text(
        "#!/bin/bash\n"
        f'cp "{KILLED}/aermod.out" aermod.out\n'
        "exec sleep 60\n"
    )
    exe.chmod(0o755)
    result = AERMODRunner(executable_path=exe, log_level="WARNING").run(inp, timeout=5)
    assert result.success is False
    assert resume_batch([inp], tmp_path) == {"done": [], "todo": [inp]}
