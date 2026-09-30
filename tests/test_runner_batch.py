"""Batch runs: results in input order, and what ``resume_batch`` counts as done.

``AERMODRunner.run_batch`` used to return its results in the order the
runs finished, so ``zip(input_files, results)`` paired decks with other
decks' results; the 2026-09-29 pilot had to re-key its first batch by
hand. ``resume_batch`` used to count a deck as done when the last 50
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


# ---------------------------------------------------------------------------
# run_batch returns results in input order
# ---------------------------------------------------------------------------

# A fake aermod whose deck says which deck must finish before it does
# ("** after <name>"). It waits for that deck's marker file, writes the
# successful recording as its aermod.out and leaves its own marker, so the
# runs finish in the order the chain sets, not the order they were given.
_CHAINED = """#!/bin/bash
me="$(basename "$(readlink aermod.inp)" .inp)"
after="$(sed -n 's/^\\*\\* after //p' aermod.inp)"
if [ -n "$after" ]; then
    for _ in $(seq 3000); do
        [ -e "{markers}/$after.done" ] && break
        sleep 0.1
    done
    [ -e "{markers}/$after.done" ] || exit 7
    sleep 1
fi
cp "{success}/aermod.out" aermod.out
touch "{markers}/$me.done"
exit 0
"""


@posix_only
def test_run_batch_returns_input_order_whatever_order_runs_finish(tmp_path):
    """Four decks that finish in reverse order come back in input order."""
    markers = tmp_path / "markers"
    markers.mkdir()
    exe = tmp_path / "aermod"
    exe.write_text(_CHAINED.format(markers=markers, success=SUCCESS))
    exe.chmod(0o755)

    names = ["a", "b", "c", "d"]
    finish_after = {"a": "b", "b": "c", "c": "d", "d": None}  # d, c, b, a
    deck = (SUCCESS / "aermod.inp").read_text()
    inputs = []
    for name in names:
        work = tmp_path / name  # one directory each, so the runs overlap
        work.mkdir()
        inp = work / f"{name}.inp"
        after = finish_after[name]
        inp.write_text((f"** after {after}\n" if after else "") + deck)
        inputs.append(inp)

    runner = AERMODRunner(executable_path=exe, log_level="WARNING")
    results = runner.run_batch(inputs, n_workers=4, timeout=300)

    assert [r.success for r in results] == [True] * 4, [r.error_message for r in results]
    finished = sorted(results, key=lambda r: r.end_time)
    assert [Path(r.input_file).stem for r in finished] == ["d", "c", "b", "a"]
    assert [r.input_file for r in results] == [str(p.resolve()) for p in inputs]
    for inp, result in zip(inputs, results):
        assert result.output_file == str(inp.with_suffix(".out").resolve())


# A fake aermod for stop_on_error. The deck's "** role" line says what it
# does: "fail" leaves a marker and writes no aermod.out, so its run fails
# at once; "slow" waits for that marker and then runs 2 s more, so it is
# still running when the batch stops; any other deck runs 2 s. Each
# deck that runs to the end writes the successful recording.
_STOPPING = """#!/bin/bash
role="$(sed -n 's/^\\*\\* role //p' aermod.inp)"
if [ "$role" = fail ]; then
    touch "{markers}/failed"
    exit 0
fi
if [ "$role" = slow ]; then
    for _ in $(seq 3000); do
        [ -e "{markers}/failed" ] && break
        sleep 0.1
    done
fi
sleep 2
cp "{success}/aermod.out" aermod.out
exit 0
"""


@posix_only
def test_run_batch_stop_on_error_returns_one_result_per_deck(tmp_path):
    """A stopped batch still pairs every deck with its own result, in input order.

    Deck 0 is still running when deck 1 fails, so its result arrives
    after the stop, and the last decks are never started. The results
    used to omit both, so ``zip(input_files, results)`` paired deck 0
    with deck 1's failure.
    """
    markers = tmp_path / "markers"
    markers.mkdir()
    exe = tmp_path / "aermod"
    exe.write_text(_STOPPING.format(markers=markers, success=SUCCESS))
    exe.chmod(0o755)
    deck = (SUCCESS / "aermod.inp").read_text()
    roles = ["slow", "fail"] + ["plain"] * 8
    inputs = []
    for i, role in enumerate(roles):
        work = tmp_path / f"d{i}"
        work.mkdir()
        inp = work / f"d{i}.inp"
        inp.write_text(f"** role {role}\n" + deck)
        inputs.append(inp)

    runner = AERMODRunner(executable_path=exe, log_level="CRITICAL")
    results = runner.run_batch(inputs, n_workers=2, timeout=300, stop_on_error=True)

    assert [r.input_file for r in results] == [str(p.resolve()) for p in inputs]
    assert results[0].success is True, results[0].error_message
    assert results[0].output_file == str(inputs[0].with_suffix(".out").resolve())
    assert results[1].success is False
    assert not results[1].error_message.startswith("Not run")
    not_run = "Not run: the batch stopped after an earlier run failed"
    for result in results[2:]:
        assert result.success or result.error_message == not_run, result.error_message
    # Two workers and the executor's one queued call leave at most four
    # of the plain decks started before the stop; the last one never is.
    assert results[-1].error_message == not_run
    assert results[-1].output_file is None
