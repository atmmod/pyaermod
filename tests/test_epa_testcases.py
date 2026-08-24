"""Tests for pyaermod.epa_testcases — EPA reference-set discovery.

Exercises both EPA directory-name conventions, the env-var override,
version-preference rules, and the AERMOD version probes, all against
throw-away directories (no EPA archive required).
"""

from __future__ import annotations

import os
import platform
import stat
from pathlib import Path

import pytest

from pyaermod.epa_testcases import (
    ENV_VAR,
    EPATestCaseSet,
    aermod_binary_version,
    describe_set,
    find_epa_testcase_set,
    list_epa_testcase_sets,
    parse_aermod_version,
    read_aermod_version,
)

BANNER = " *** AERMOD - VERSION 26135  ***   *** A Simple Example Problem ***        07/09/26\n"


def _make_set(root: Path, name: str, *, complete: bool = True, banner: str | None = None) -> Path:
    """Create a fake EPA set directory with the expected sub-tree."""
    p = root / name
    (p / "inputs").mkdir(parents=True)
    if complete:
        (p / "postfiles").mkdir()
        (p / "meteorology").mkdir()
    if banner is not None:
        (p / "Outputs").mkdir()
        (p / "Outputs" / "AERTEST.SUM").write_text(banner, encoding="latin-1")
    return p


class TestNameParsing:
    @pytest.mark.parametrize(
        ("name", "aermet", "aermod"),
        [
            ("aermet_24142_aermod_24142", "24142", "24142"),   # pre-2026 bundle
            ("aermet24142_aermod24142", "24142", "24142"),     # July-2026 bundle
            ("aermet24142_aermod26135", "24142", "26135"),
            ("aermet26135_aermod26135", "26135", "26135"),
            ("AERMET_24142_AERMOD_26135", "24142", "26135"),   # case-insensitive
        ],
    )
    def test_both_naming_conventions(self, tmp_path, name, aermet, aermod):
        s = describe_set(tmp_path / name)
        assert s.aermet_version == aermet
        assert s.aermod_version == aermod
        assert s.name == name

    def test_unnamed_set_reads_banner_from_outputs(self, tmp_path):
        p = _make_set(tmp_path, "my_epa_fixtures", banner=BANNER)
        s = describe_set(p)
        assert s.aermet_version is None
        assert s.aermod_version == "26135"

    def test_unnamed_set_without_outputs_has_unknown_version(self, tmp_path):
        p = _make_set(tmp_path, "fixtures")
        s = describe_set(p)
        assert s.aermod_version is None
        assert "AERMOD ?" in s.describe()

    def test_paths_and_exists(self, tmp_path):
        p = _make_set(tmp_path, "aermet24142_aermod24142")
        s = describe_set(p)
        assert s.inputs == p / "inputs"
        assert s.postfiles == p / "postfiles"
        assert s.meteorology == p / "meteorology"
        assert s.plotfiles == p / "plotfiles"
        assert s.outputs == p / "Outputs"
        assert s.exists()
        incomplete = describe_set(_make_set(tmp_path, "aermet24142_aermod26135", complete=False))
        assert not incomplete.exists()


class TestListing:
    def test_missing_root_is_empty(self, tmp_path):
        assert list_epa_testcase_sets(tmp_path / "nope") == []

    def test_lists_only_aermet_aermod_dirs(self, tmp_path):
        _make_set(tmp_path, "aermet_24142_aermod_24142")
        _make_set(tmp_path, "aermet24142_aermod26135")
        (tmp_path / "plots_aermet24142_aermod24142_v_aermet26135_aermod26135").mkdir()
        (tmp_path / "Compare_AERMOD_test_cases.R").write_text("# R script")
        names = [s.name for s in list_epa_testcase_sets(tmp_path)]
        assert names == ["aermet24142_aermod26135", "aermet_24142_aermod_24142"]


class TestSelection:
    def test_none_when_absent(self, tmp_path):
        assert find_epa_testcase_set(tmp_path / "test_cases", env={}) is None

    def test_single_legacy_set(self, tmp_path):
        _make_set(tmp_path, "aermet_24142_aermod_24142")
        chosen = find_epa_testcase_set(tmp_path, env={})
        assert chosen is not None
        assert chosen.name == "aermet_24142_aermod_24142"

    def test_prefers_set_matching_binary_version(self, tmp_path):
        _make_set(tmp_path, "aermet24142_aermod24142")
        _make_set(tmp_path, "aermet24142_aermod26135")
        _make_set(tmp_path, "aermet26135_aermod26135")
        assert find_epa_testcase_set(tmp_path, aermod_version="24142", env={}).name == \
            "aermet24142_aermod24142"
        # Two sets for AERMOD 26135 -> the one with the newer AERMET wins.
        assert find_epa_testcase_set(tmp_path, aermod_version="26135", env={}).name == \
            "aermet26135_aermod26135"

    def test_falls_back_to_newest_when_no_version_match(self, tmp_path):
        _make_set(tmp_path, "aermet_24142_aermod_24142")
        _make_set(tmp_path, "aermet24142_aermod26135")
        chosen = find_epa_testcase_set(tmp_path, aermod_version="99999", env={})
        assert chosen.name == "aermet24142_aermod26135"
        assert chosen.aermod_version != "99999"  # caller can detect the mismatch

    def test_newest_without_version_hint(self, tmp_path):
        _make_set(tmp_path, "aermet26135_aermod26135")
        _make_set(tmp_path, "aermet_24142_aermod_24142")
        assert find_epa_testcase_set(tmp_path, env={}).name == "aermet26135_aermod26135"

    def test_prefers_validated_release_over_merely_newest(self, tmp_path):
        """Absent a binary, 26135 (validated) beats a newer, unvalidated set."""
        _make_set(tmp_path, "aermet_24142_aermod_24142")
        _make_set(tmp_path, "aermet26135_aermod26135")
        _make_set(tmp_path, "aermet27001_aermod27001")  # hypothetical future release
        assert find_epa_testcase_set(tmp_path, env={}).name == "aermet26135_aermod26135"
        # ... unless the binary under test *is* that newer release.
        assert find_epa_testcase_set(tmp_path, aermod_version="27001", env={}).name == \
            "aermet27001_aermod27001"
        # Only unvalidated sets present -> newest wins.
        import shutil
        shutil.rmtree(tmp_path / "aermet26135_aermod26135")
        shutil.rmtree(tmp_path / "aermet_24142_aermod_24142")
        _make_set(tmp_path, "aermet27001_aermod27150")
        assert find_epa_testcase_set(tmp_path, env={}).name == "aermet27001_aermod27150"

    def test_incomplete_sets_are_ignored(self, tmp_path):
        _make_set(tmp_path, "aermet26135_aermod26135", complete=False)
        _make_set(tmp_path, "aermet24142_aermod24142")
        assert find_epa_testcase_set(tmp_path, env={}).name == "aermet24142_aermod24142"

    def test_env_override_wins(self, tmp_path):
        _make_set(tmp_path, "aermet26135_aermod26135")
        pinned = _make_set(tmp_path / "elsewhere", "aermet24142_aermod24142")
        chosen = find_epa_testcase_set(
            tmp_path, aermod_version="26135", env={ENV_VAR: str(pinned)},
        )
        assert chosen.path == pinned.resolve()
        assert chosen.aermod_version == "24142"

    def test_env_override_is_returned_even_if_missing(self, tmp_path):
        """A bad override must surface as a bad path, not a silent fallback."""
        _make_set(tmp_path, "aermet26135_aermod26135")
        chosen = find_epa_testcase_set(tmp_path, env={ENV_VAR: str(tmp_path / "missing")})
        assert chosen is not None
        assert chosen.path == (tmp_path / "missing").resolve()
        assert not chosen.exists()

    def test_default_root_is_cwd_test_cases(self, tmp_path, monkeypatch):
        _make_set(tmp_path / "test_cases", "aermet24142_aermod24142")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert find_epa_testcase_set().name == "aermet24142_aermod24142"


class TestVersionProbes:
    def test_parse_banner_and_usage(self):
        assert parse_aermod_version(BANNER) == "26135"
        assert parse_aermod_version(" Usage: AERMOD 26135  takes either no or one or two parameters.") == "26135"
        assert parse_aermod_version("*** AERMOD - VERSION 24142  ***") == "24142"
        assert parse_aermod_version("no version here") is None

    def test_read_version_tolerates_latin1(self, tmp_path):
        f = tmp_path / "run.out"
        f.write_bytes(b"\xb0" + BANNER.encode("latin-1") + b"\xff\xfe more")
        assert read_aermod_version(f) == "26135"

    def test_read_version_missing_file(self, tmp_path):
        assert read_aermod_version(tmp_path / "nope.out") is None

    def test_binary_version_none_when_no_aermod(self, monkeypatch):
        monkeypatch.setattr("pyaermod.epa_testcases.shutil.which", lambda _name: None)
        assert aermod_binary_version() is None

    def test_binary_version_none_when_exec_fails(self, tmp_path):
        assert aermod_binary_version(tmp_path / "not-a-binary") is None

    @pytest.mark.skipif(platform.system() == "Windows", reason="POSIX shell stub")
    def test_binary_version_from_help_output(self, tmp_path):
        """A stub that mimics AERMOD's --help banner (and its stray .TMP file)."""
        exe = tmp_path / "aermod"
        exe.write_text(
            "#!/bin/sh\n"
            "echo ' usage: 0, 1, or 2 args'\n"
            "echo ' Usage: AERMOD 26135  takes either no or one or two parameters.'\n"
            "touch ./--help_ERRMSG.TMP\n"
        )
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        assert aermod_binary_version(exe) == "26135"
        # The probe ran in a scratch dir: nothing leaked next to the binary or into cwd.
        assert not (tmp_path / "--help_ERRMSG.TMP").exists()
        assert not (Path(os.getcwd()) / "--help_ERRMSG.TMP").exists()


def test_dataclass_is_frozen(tmp_path):
    s = EPATestCaseSet(tmp_path, "24142", "24142")
    with pytest.raises(AttributeError):
        s.aermod_version = "26135"  # type: ignore[misc]
