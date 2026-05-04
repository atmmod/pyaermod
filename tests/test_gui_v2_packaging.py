"""Smoke tests for the desktop packaging artifacts.

These don't run PyInstaller (which requires the target OS). They
validate that the spec file and CI workflow are present and well-formed,
catching obvious typos / removals at PR time rather than at release.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_pyinstaller_spec_present():
    spec = REPO_ROOT / "packaging" / "pyaermod_desktop.spec"
    assert spec.exists(), "PyInstaller spec missing"
    text = spec.read_text(encoding="utf-8")
    assert "pyaermod-desktop" in text
    assert "BUNDLE" in text  # macOS .app step exists
    assert "console=False" in text  # GUI app, not console


def test_build_desktop_workflow_present():
    wf = REPO_ROOT / ".github" / "workflows" / "build_desktop.yml"
    assert wf.exists(), "build_desktop workflow missing"
    text = wf.read_text(encoding="utf-8")
    # All three OSes covered
    for os_runner in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert os_runner in text, f"workflow missing {os_runner}"


def test_desktop_doc_present():
    doc = REPO_ROOT / "docs" / "desktop.md"
    assert doc.exists(), "docs/desktop.md missing"
    text = doc.read_text(encoding="utf-8")
    # Coarse content checks
    assert "pyaermod-desktop" in text
    assert "AERMOD" in text


def test_pyproject_console_scripts_register_desktop():
    py = REPO_ROOT / "pyproject.toml"
    text = py.read_text(encoding="utf-8")
    assert 'pyaermod-desktop = "pyaermod.gui_v2.desktop:main"' in text
    assert 'pyaermod-app = "pyaermod.gui_v2:main"' in text


def test_extras_include_gui_modern_desktop():
    py = REPO_ROOT / "pyproject.toml"
    text = py.read_text(encoding="utf-8")
    assert "gui-modern-desktop" in text
    assert "pywebview" in text
