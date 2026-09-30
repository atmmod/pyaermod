"""The AERMET deck writers and how AERMETRunner decides a run succeeded.

Both are pinned against real AERMET v26135 runs recorded in
``tests/fixtures/aermet/runs/`` (see ``tests/fixtures/aermet/README.md``):

* ``stage1_success/`` and ``metprep_success/``: pyaermod's decks for EPA's
  test case EX01, which AERMET runs to completion. The METPREP run's
  ``.SFC`` and ``.PFL`` carry the values of EPA's own EX01 output;
* ``metprep_without_stage1/``: error E70, no Stage 1 data to merge;
* ``stage1_wrong_format/``: errors E30 and E39, TD-6201 data declared FSL;
* ``legacy_stage1/``: the deck the writer produced before this rewrite,
  which AERMET rejects with six errors.

AERMET exits with code 0 in every one of these runs. The fake ``aermet``
below replays them: it finds the recording whose deck matches the deck it
is given and writes back that run's stdout, REPORT, MESSAGES and output
files and its exit code. The same checks against the real binary live in
``tests/test_real_aermet_binary.py``.
"""

from __future__ import annotations

import importlib.util
import platform
import warnings
from dataclasses import replace
from pathlib import Path

import pytest

from pyaermod.aermet_runner import (
    AERMETMessage,
    AERMETRunner,
    _summary_counts,
    parse_aermet_messages,
    read_aermet_messages,
    run_aermet_pipeline,
)

FIXTURES = Path(__file__).parent / "fixtures" / "aermet"
EX01 = FIXTURES / "ex01"
RUNS = FIXTURES / "runs"
STAGE1_OK = RUNS / "stage1_success"
METPREP_OK = RUNS / "metprep_success"
NO_STAGE1 = RUNS / "metprep_without_stage1"
WRONG_FORMAT = RUNS / "stage1_wrong_format"
LEGACY = RUNS / "legacy_stage1"
ALL_RUNS = [STAGE1_OK, METPREP_OK, NO_STAGE1, WRONG_FORMAT, LEGACY]

posix_only = pytest.mark.skipif(
    platform.system() == "Windows", reason="the replaying fake aermet is a bash script",
)


def _ex01_stages():
    spec = importlib.util.spec_from_file_location("ex01_decks", FIXTURES / "ex01_decks.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ex01_stages()


def _data_rows(path: Path):
    """The value fields of an SFC/PFL file: two-digit year, no header line."""
    rows = []
    for line in path.read_text().replace("\r", "").splitlines():
        fields = line.split()
        if not fields or line.lstrip()[0].isalpha() or "UA_ID:" in line:
            continue
        fields[0] = str(int(fields[0]) % 100)
        rows.append(fields)
    return rows


# ---------------------------------------------------------------------------
# The recordings: what the rule is built on
# ---------------------------------------------------------------------------

class TestRecordings:

    @pytest.mark.parametrize("case", ALL_RUNS, ids=lambda p: p.name)
    def test_aermet_exits_zero_in_every_case(self, case):
        assert (case / "exit_code.txt").read_text().strip() == "0"

    @pytest.mark.parametrize("case", [NO_STAGE1, WRONG_FORMAT, LEGACY], ids=lambda p: p.name)
    def test_failed_runs_print_the_unsuccessful_banner_and_no_fatal(self, case):
        """Why neither the exit code nor the word FATAL can tell success."""
        out = (case / "stdout.txt").read_text()
        assert "AERMET FINISHED UN-SUCCESSFULLY" in out
        assert "FATAL" not in out.upper()

    def test_metprep_output_matches_epa_ex01(self):
        """pyaermod's EX01 decks reproduce EPA's EX01_MP.SFC and .PFL, value for value."""
        for name in ("EX01_MP.SFC", "EX01_MP.PFL"):
            ours = _data_rows(METPREP_OK / name)
            epa = _data_rows(EX01 / name)
            assert len(ours) == len(epa) > 90
            assert ours == epa, name
        header = (METPREP_OK / "EX01_MP.SFC").read_text().splitlines()[0]
        assert "UA_ID: 00014735  SF_ID: 14735" in header
        assert "VERSION: 26135" in header


# ---------------------------------------------------------------------------
# The deck writers
# ---------------------------------------------------------------------------

class TestEX01Decks:
    """The decks pyaermod writes today are the ones AERMET ran to completion."""

    def test_stage1_deck_is_the_recorded_one(self):
        stage1, _ = _ex01_stages()
        assert stage1.to_aermet_input() == (STAGE1_OK / "deck.inp").read_text()

    def test_metprep_deck_is_the_recorded_one(self):
        _, stage3 = _ex01_stages()
        assert stage3.to_aermet_input() == (METPREP_OK / "deck.inp").read_text()

    def test_stage1_deck_uses_epa_keywords(self):
        stage1, _ = _ex01_stages()
        deck = stage1.to_aermet_input()
        # EPA's EX01_S1.INP: LOCATION 00014735 73.80W 42.75N 5 83.8 (TD-6201,
        # GMT) and LOCATION 14735 42.75N 73.8W 0 83.8 (CD-144, local time).
        assert "LOCATION   00014735 42.75N 73.8W 5 83.8" in deck
        assert "LOCATION   14735 42.75N 73.8W 0 83.8" in deck
        assert "DATA       14735-88.UA 6201FB" in deck
        assert "QAOUT      stage1_ua.qa" in deck
        assert "MESSAGES   stage1.msg" in deck
        for rejected in ("ANEMHGT", "ELEVATION", "\nQA\n", "MESSAGES   2"):
            assert rejected not in deck

    def test_legacy_deck_is_what_the_old_writer_wrote(self):
        """The rejected recording is the old writer's output, so the rejection is the old bug."""
        deck = (LEGACY / "deck.inp").read_text()
        assert "MESSAGES   2" in deck
        assert "ANEMHGT    6.1" in deck
        assert "LOCATION   14735 42.7500 -73.8000 -5" in deck


# ---------------------------------------------------------------------------
# Reading AERMET's messages
# ---------------------------------------------------------------------------

class TestMessages:

    def test_legacy_errors(self):
        messages = read_aermet_messages(LEGACY / "2")
        assert [m.code for m in messages] == ["E01", "E05", "E05", "W04", "E05", "E01", "E01"]
        assert messages[0] == AERMETMessage(
            pathway="SURFACE", severity="E", code="E01", module="CHECK_LINE",
            text="INVALID KEYWORD: ANEMHGT LINE NUMBER:  17",
        )
        # A message about the deck as a whole has no pathway.
        assert messages[-1].pathway == ""
        assert str(messages[-1]) == "E01 CHECK_LINE: INVALID PATH QA LINE NUMBER: 21"

    def test_wrong_format_errors(self):
        messages = read_aermet_messages(WRONG_FORMAT / "stage1.msg")
        errors = [m for m in messages if m.severity == "E"]
        assert [(m.pathway, m.code, m.module) for m in errors] == [
            ("UPPERAIR", "E30", "READ_FSL"), ("UPPERAIR", "E39", "READ_FSL"),
        ]
        assert errors[0].text.startswith("SOUNDING IS NOT FSL FORMAT")

    def test_success_lists_only_information_and_qa(self):
        messages = read_aermet_messages(STAGE1_OK / "stage1.msg")
        assert len(messages) == 46
        assert {m.severity for m in messages} == {"I", "Q"}
        assert messages[0].pathway == "" and messages[0].code == "I01"

    def test_report_summary_counts(self):
        assert _summary_counts((STAGE1_OK / "stage1.out").read_text()) == {
            "E": 0, "W": 0, "I": 16, "Q": 30}
        assert _summary_counts((METPREP_OK / "stage3.out").read_text()) == {
            "E": 0, "W": 9, "I": 25, "Q": 0}
        assert _summary_counts((LEGACY / "stage1.out").read_text())["E"] == 6
        assert _summary_counts((NO_STAGE1 / "stage3.out").read_text())["E"] == 1

    def test_lines_outside_the_layout_are_ignored(self):
        assert parse_aermet_messages("\n AERMET FINISHED SUCCESSFULLY\r\n garbage\n") == []


# ---------------------------------------------------------------------------
# The runner, against a fake aermet that replays the recordings
# ---------------------------------------------------------------------------

_REPLAY = """#!/bin/bash
# Replay the first recorded AERMET run whose deck matches the runstream:
# "$1", or aermet.inp when AERMET is given no argument (readinp).
deck="${{1:-aermet.inp}}"
for case in {cases}; do
    if cmp -s "$deck" "$case/deck.inp"; then
        for f in "$case"/*; do
            case "$(basename "$f")" in
                deck.inp|stdout.txt|exit_code.txt) ;;
                *) cp "$f" . ;;
            esac
        done
        cat "$case/stdout.txt"
        exit "$(cat "$case/exit_code.txt")"
    fi
done
echo "no recording matches $deck" >&2
exit 99
"""


def _replayer(where: Path, cases) -> Path:
    """A fake aermet replaying ``cases``, in that order of preference."""
    exe = where / "aermet"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text(_REPLAY.format(cases=" ".join(f'"{c}"' for c in cases)))
    exe.chmod(0o755)
    return exe


@pytest.fixture
def replaying_aermet(tmp_path):
    """Replays every recording. METPREP's deck is the same with or without
    Stage 1's files, so this one replays the successful METPREP run; tests of
    metprep_without_stage1 build a replayer of their own."""
    return _replayer(tmp_path / "bin", [c for c in ALL_RUNS if c != NO_STAGE1])


@posix_only
class TestRunStage:

    def _run(self, exe, case, work):
        return AERMETRunner(executable_path=exe).run_stage(1, case / "deck.inp", working_dir=work)

    def test_success(self, replaying_aermet, tmp_path):
        result = self._run(replaying_aermet, STAGE1_OK, tmp_path / "w")
        assert result.success is True
        assert result.finished_successfully is True
        assert result.return_code == 0
        assert result.error_message is None
        assert result.message_counts == {"E": 0, "W": 0, "I": 16, "Q": 30}
        assert result.error_count == 0 and result.errors == []
        assert result.report_file == str((tmp_path / "w" / "stage1.out").resolve())
        assert result.message_file == str((tmp_path / "w" / "stage1.msg").resolve())
        # A deck outside the working directory is copied in under its own name.
        assert (tmp_path / "w" / "deck.inp").read_text() == (STAGE1_OK / "deck.inp").read_text()

    @pytest.mark.parametrize(("case", "first"), [
        (LEGACY, "SURFACE E01 CHECK_LINE: INVALID KEYWORD: ANEMHGT LINE NUMBER:  17 (and 5 more error(s))"),
        (WRONG_FORMAT, "UPPERAIR E30 READ_FSL: SOUNDING IS NOT FSL FORMAT"),
        (NO_STAGE1, "METPREP E70 PBL_TEST: NO DATA PERIODS DATES OVERLAP"),
    ], ids=lambda v: v.name if isinstance(v, Path) else "")
    def test_exit_code_zero_after_an_error_is_a_failure(self, tmp_path, case, first):
        result = self._run(_replayer(tmp_path / "bin", [case]), case, tmp_path / "w")
        assert result.return_code == 0
        assert result.success is False
        assert result.finished_successfully is False
        assert result.error_count >= 1
        assert result.error_message.startswith(first)
        assert "AERMET printed 'AERMET FINISHED UN-SUCCESSFULLY'" in result.error_message

    def test_errors_listed_without_the_banner_fail(self, tmp_path):
        """An error in the MESSAGES file fails the run even if the banner says otherwise."""
        exe = tmp_path / "aermet"
        exe.write_text(
            "#!/bin/bash\n"
            "printf ' SURFACE    E05     GETLOC     BAD\\n' > s.msg\n"
            "echo ' AERMET FINISHED SUCCESSFULLY'\n"
        )
        exe.chmod(0o755)
        deck = tmp_path / "deck.inp"
        deck.write_text("JOB\n   REPORT     s.out\n   MESSAGES   s.msg\n")
        result = AERMETRunner(executable_path=exe).run_stage(1, deck, working_dir=tmp_path)
        assert result.finished_successfully is True
        assert result.success is False
        assert result.error_message == "SURFACE E05 GETLOC: BAD"

    def test_no_banner_and_nonzero_exit(self, tmp_path):
        exe = tmp_path / "aermet"
        exe.write_text("#!/bin/bash\necho 'Segmentation fault' >&2\necho ' reading'\nexit 139\n")
        exe.chmod(0o755)
        deck = tmp_path / "deck.inp"
        deck.write_text("** no JOB pathway\n")
        result = AERMETRunner(executable_path=exe).run_stage(1, deck, working_dir=tmp_path)
        assert result.success is False
        assert result.report_file is None and result.message_file is None
        assert result.error_message == (
            "AERMET exited with code 139; AERMET did not print "
            "'AERMET FINISHED SUCCESSFULLY' (last output: reading); stderr: Segmentation fault"
        )

    def test_a_crash_is_reported_with_the_runtime_error(self, tmp_path):
        """AERMET 24142 crashes on METPREP without Stage 1's files; its stderr began so."""
        exe = tmp_path / "aermet"
        exe.write_text(
            "#!/bin/bash\n"
            "echo ' START PROCESSING DATE/TIME: SEPTEMBER 29, 2026  21:20:37 PM'\n"
            "cat >&2 <<'ERR'\n"
            "At line 4179 of file mod_upperair.f90 (unit = 16, file = 'stage1_ua.qa')\n"
            "Fortran runtime error: End of file\n"
            "\n"
            "Error termination. Backtrace:\n"
            "#0  0x1030ae103\n"
            "ERR\n"
            "exit 2\n"
        )
        exe.chmod(0o755)
        deck = tmp_path / "deck.inp"
        deck.write_text("JOB\n")
        result = AERMETRunner(executable_path=exe).run_stage(3, deck, working_dir=tmp_path)
        assert result.success is False
        assert result.error_message.endswith("stderr: Fortran runtime error: End of file")

    def test_counted_errors_without_listed_messages_fail(self, tmp_path):
        exe = tmp_path / "aermet"
        exe.write_text(
            "#!/bin/bash\n"
            "printf '\\n\\n ERROR MESSAGES        2 MESSAGES\\n\\n' > r.out\n"
            "echo ' AERMET FINISHED SUCCESSFULLY'\n"
        )
        exe.chmod(0o755)
        deck = tmp_path / "deck.inp"
        deck.write_text("JOB\n   REPORT     r.out\n")
        result = AERMETRunner(executable_path=exe).run_stage(1, deck, working_dir=tmp_path)
        assert result.success is False
        assert result.error_count == 2
        assert result.error_message == "AERMET counted 2 error message(s)"


@posix_only
class TestPipeline:

    def test_ex01_runs_stage1_then_metprep(self, replaying_aermet, tmp_path):
        stage1, stage3 = _ex01_stages()
        results = run_aermet_pipeline(stage1, None, stage3, working_dir=tmp_path,
                                      executable_path=replaying_aermet)
        assert [(r.stage, r.success) for r in results] == [(1, True), (3, True)]
        assert (tmp_path / "EX01_MP.SFC").read_text() == (METPREP_OK / "EX01_MP.SFC").read_text()
        assert not (tmp_path / "stage2.inp").exists()

    def test_metprep_reads_stage1_qaout_by_default(self, replaying_aermet, tmp_path):
        """A METPREP deck given no input names still reads what Stage 1 wrote."""
        stage1, stage3 = _ex01_stages()
        bare = replace(stage3, upper_air_qaout=None, surface_qaout=None)
        results = run_aermet_pipeline(stage1, None, bare, working_dir=tmp_path,
                                      executable_path=replaying_aermet)
        assert [r.success for r in results] == [True, True]

    def test_failed_stage1_stops_the_pipeline(self, replaying_aermet, tmp_path):
        stage1, stage3 = _ex01_stages()
        wrong = replace(stage1, upper_air_format="FSL")
        results = run_aermet_pipeline(wrong, None, stage3, working_dir=tmp_path,
                                      executable_path=replaying_aermet)
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].errors[0].code == "E30"

    def test_stage2_is_ignored_with_a_warning(self, replaying_aermet, tmp_path):
        from pyaermod.aermet import AERMETStage2

        stage1, stage3 = _ex01_stages()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            stage2 = AERMETStage2()
        with pytest.warns(DeprecationWarning, match="ignores stage2"):
            results = run_aermet_pipeline(stage1, stage2, stage3, working_dir=tmp_path,
                                          executable_path=replaying_aermet)
        assert [r.stage for r in results] == [1, 3]
