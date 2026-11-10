"""How the GUI is distributed: through PyPI (and conda), not as downloads.

The ``pyaermod-app`` and ``pyaermod-desktop`` console scripts and the
``gui-desktop`` extra are the whole of the desktop packaging. The
PyInstaller bundles that releases up to 2.2.0 carried are no longer
built, so nothing in the repository may build one, and the docs must
not send users to download one.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_DOC = REPO_ROOT / "docs" / "desktop.md"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Directories that are not part of the source tree: environments, build
# output and the gitignored Fortran sources. Hidden directories (.git,
# caches, other checkouts under .claude/worktrees) are skipped as well.
_SKIPPED_DIRS = frozenset({"venv", "env", "node_modules", "build", "dist", "site", "aermod", "aermap"})


def _pyproject() -> dict:
    with open(REPO_ROOT / "pyproject.toml", "rb") as fp:
        return tomllib.load(fp)


def _source_tree_files(pattern: str) -> list[Path]:
    return [
        path for path in REPO_ROOT.rglob(pattern)
        if not any(part in _SKIPPED_DIRS or part.startswith(".")
                   for part in path.relative_to(REPO_ROOT).parts[:-1])
    ]


# ---------------------------------------------------------------------------
# What is shipped: console scripts and the extra
# ---------------------------------------------------------------------------

def test_pyproject_console_scripts_register_desktop():
    scripts = _pyproject()["project"]["scripts"]
    assert scripts["pyaermod-desktop"] == "pyaermod.gui_v2.desktop:main"
    assert scripts["pyaermod-app"] == "pyaermod.gui_v2:main"


def test_extras_include_gui_desktop():
    extras = _pyproject()["project"]["optional-dependencies"]
    desktop = " ".join(extras["gui-desktop"])
    assert "pywebview" in desktop
    assert "nicegui" in desktop


# ---------------------------------------------------------------------------
# What is no longer shipped: the PyInstaller bundles and their pipeline
# ---------------------------------------------------------------------------

def test_no_pyinstaller_spec_in_the_repo():
    assert _source_tree_files("*.spec") == []
    assert not (REPO_ROOT / "packaging").exists()


def test_no_desktop_build_workflow():
    assert not (WORKFLOWS / "build_desktop.yml").exists()
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        text = workflow.read_text(encoding="utf-8")
        assert "pyinstaller" not in text.lower(), workflow.name
        # No leftover of the macOS signing and notarization steps.
        for needle in ("MACOS_SIGN_IDENTITY", "MACOS_CERT_", "notarytool", "codesign"):
            assert needle not in text, f"{workflow.name} mentions {needle}"


def test_pyinstaller_is_not_a_dependency():
    project = _pyproject()["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements += extra
    assert not [r for r in requirements if r.lower().startswith("pyinstaller")]


def test_releasing_guide_has_no_desktop_build_or_signing_steps():
    text = (REPO_ROOT / "RELEASING.md").read_text(encoding="utf-8")
    for needle in ("build_desktop", "PyInstaller", "MACOS_", "APPLE_API_", "notariz", "entitlements"):
        assert needle not in text, f"RELEASING.md still mentions {needle}"
    assert "No desktop binaries are built or attached" in text


# ---------------------------------------------------------------------------
# The docs page
# ---------------------------------------------------------------------------

def test_desktop_doc_present_and_in_the_nav():
    assert DESKTOP_DOC.exists(), "docs/desktop.md missing"
    assert re.search(r"^\s+- [^:\n]+: desktop\.md$", (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"),
                     flags=re.MULTILINE)


def test_desktop_doc_installs_with_pip():
    text = DESKTOP_DOC.read_text(encoding="utf-8")
    assert 'pip install "pyaermod[gui-desktop]"' in text
    assert "pyaermod-desktop" in text
    # Linux needs a pywebview backend, and AERMOD is not included.
    assert "pywebview[qt]" in text
    assert "GTK" in text
    assert "AERMOD" in text and "PATH" in text


def test_desktop_doc_says_the_downloads_are_discontinued():
    text = DESKTOP_DOC.read_text(encoding="utf-8")
    assert "## Desktop downloads discontinued" in text
    notice = text.split("## Desktop downloads discontinued", 1)[1].split("\n## ", 1)[0]
    assert "no longer built" in notice
    assert "2.2.0" in notice
    assert "unsigned" in notice
    # The workaround for an old macOS download stays.
    assert "xattr -dr com.apple.quarantine" in notice
    assert "Open Anyway" in notice


@pytest.mark.parametrize("doc", ["desktop.md", "index.md", "architecture.md"])
def test_docs_do_not_offer_a_desktop_download(doc):
    """Nothing outside the discontinued notice describes a bundle to
    download, build or sign."""
    text = (REPO_ROOT / "docs" / doc).read_text(encoding="utf-8")
    head, _, rest = text.partition("## Desktop downloads discontinued")
    after = rest.split("\n## ", 1)[1] if "\n## " in rest else ""
    live = head + after
    for needle in (
        "pyaermod-desktop.exe",
        "pyaermod-desktop-macos",
        "pyaermod-desktop.app",
        "releases page",
        "github.com/atmmod/pyaermod/releases",
        "pre-built",
        "Pre-built",
        "desktop bundle",
        "PyInstaller",
        "pyinstaller",
        "notarized",
        "MACOS_SIGN_IDENTITY",
        "packaging/",
    ):
        assert needle not in live, f"docs/{doc} still mentions {needle!r} outside the discontinued notice"
