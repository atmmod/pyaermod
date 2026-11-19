"""Both GUIs must find AERMOD wherever AERMODRunner finds it (arch A3).

EPA ships the binary as ``AERMOD``; on a case-sensitive file system
``shutil.which("aermod")`` does not find it, but AERMODRunner tries
aermod, AERMOD, aermod.exe and AERMOD.EXE. The fake ``which`` below
models a case-sensitive PATH holding only ``AERMOD``.
"""

from __future__ import annotations

import shutil

import pytest

from pyaermod import browser
from pyaermod.gui_v2.pages import run as run_page
from pyaermod.runner import AERMODRunner


@pytest.fixture
def only_upper_case_aermod(tmp_path, monkeypatch):
    exe = tmp_path / "AERMOD"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: str(exe) if name == "AERMOD" else None)
    return exe


def test_runner_finds_upper_case_binary(only_upper_case_aermod):
    assert AERMODRunner().executable == only_upper_case_aermod


def test_pip_gui_agrees_with_runner(only_upper_case_aermod):
    assert run_page._aermod_available()


def test_browser_gui_agrees_with_runner(only_upper_case_aermod, monkeypatch):
    monkeypatch.setattr(browser, "RUNNER_FACTORY", None)
    assert browser._have_aermod()
