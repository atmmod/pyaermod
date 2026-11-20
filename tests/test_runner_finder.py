"""One search for the AERMOD executable, shared by the runner and both GUIs."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod import runner
from pyaermod.gui_v2 import readiness


def test_a_given_path_is_used_and_a_missing_one_refused(tmp_path):
    exe = tmp_path / "my_aermod"
    exe.write_text("")
    assert runner.find_aermod_executable(exe) == exe
    with pytest.raises(FileNotFoundError):
        runner.find_aermod_executable(tmp_path / "absent")


@pytest.mark.parametrize("name", runner.AERMOD_EXECUTABLE_NAMES)
def test_each_name_is_found_on_path(monkeypatch, name):
    monkeypatch.setattr(runner.shutil, "which",
                        lambda n: f"/opt/{n}" if n == name else None)
    assert runner.find_aermod_executable() == Path(f"/opt/{name}")
    assert readiness.aermod_available()


def test_nothing_on_path(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda n: None)
    with pytest.raises(FileNotFoundError, match="not found in PATH"):
        runner.find_aermod_executable()
    assert not readiness.aermod_available()
