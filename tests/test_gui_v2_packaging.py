"""Smoke tests for the desktop packaging artifacts.

These don't run PyInstaller (which requires the target OS). They
validate that the spec file and CI workflow are present and well-formed,
catching obvious typos / removals at PR time rather than at release.
"""

from __future__ import annotations

import plistlib
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "packaging" / "pyaermod_desktop.spec"
ENTITLEMENTS = REPO_ROOT / "packaging" / "entitlements.plist"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build_desktop.yml"

SIGNING_SECRETS = (
    "MACOS_CERT_P12_BASE64",
    "MACOS_CERT_PASSWORD",
    "MACOS_SIGN_IDENTITY",
    "APPLE_API_KEY_P8_BASE64",
    "APPLE_API_KEY_ID",
    "APPLE_API_ISSUER_ID",
)

# Hardened-runtime exceptions the signed macOS app is allowed to claim.
# Empty: the bundle runs without any. Adding a key to
# packaging/entitlements.plist means adding it here too, with the reason
# in the plist's comment.
ALLOWED_ENTITLEMENTS: frozenset[str] = frozenset()


def _workflow_steps() -> dict[str, str]:
    """The named steps of the build job, as ``{name: text of the step}``.

    Read as text, not YAML: PyYAML is not a test dependency.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    chunks = re.split(r"^      - name: ", text.split("\n    steps:\n", 1)[1], flags=re.MULTILINE)[1:]
    return {chunk.split("\n", 1)[0].strip(): chunk for chunk in chunks}


def _step(name_part: str) -> str:
    matches = [body for name, body in _workflow_steps().items() if name_part in name]
    assert len(matches) == 1, f"expected one workflow step named like {name_part!r}, found {len(matches)}"
    return matches[0]


def _step_condition(name_part: str) -> str:
    conditions = re.findall(r"^        if: (.+)$", _step(name_part), flags=re.MULTILINE)
    assert len(conditions) == 1, f"step {name_part!r} should have one `if:`"
    return conditions[0].strip()


def test_pyinstaller_spec_present():
    assert SPEC.exists(), "PyInstaller spec missing"
    text = SPEC.read_text(encoding="utf-8")
    assert "pyaermod-desktop" in text
    assert "BUNDLE" in text  # macOS .app step exists
    assert "console=False" in text  # GUI app, not console


def test_entry_script_calls_freeze_support_before_importing_the_app():
    """Without it every multiprocessing helper re-launches the frozen app."""
    text = (REPO_ROOT / "packaging" / "desktop_entry.py").read_text(encoding="utf-8")
    call = text.index("\nmultiprocessing.freeze_support()")
    assert call < text.index("\nfrom pyaermod.gui_v2.desktop import main")


def test_spec_builds_onedir_bundle_on_macos():
    """A onefile EXE inside a .app cannot be notarized (and PyInstaller 7
    rejects it), so the macOS bundle wraps a COLLECT."""
    text = SPEC.read_text(encoding="utf-8")
    macos, other = text.split("if is_macos:\n", 1)[1].split("\nelse:\n", 1)
    assert "exclude_binaries=True" in macos
    assert re.search(r"coll = COLLECT\(\s*exe,\s*a\.binaries,", macos)
    assert re.search(r"BUNDLE\(\s*coll,", macos)
    # Windows and Linux stay onefile: the binaries go into the EXE and
    # nothing is collected beside it.
    assert "a.binaries" in other
    assert "COLLECT" not in other
    assert "exclude_binaries" not in other


def test_spec_signs_with_the_identity_from_the_environment():
    text = SPEC.read_text(encoding="utf-8")
    assert 'os.environ.get("MACOS_SIGN_IDENTITY") or None' in text
    assert "codesign_identity=CODESIGN_IDENTITY" in text
    assert "entitlements_file=ENTITLEMENTS" in text
    assert '"entitlements.plist"' in text
    assert "codesign_identity=None" not in text


def test_spec_takes_the_bundle_version_from_pyproject():
    text = SPEC.read_text(encoding="utf-8")
    assert 'tomllib.load(_fp)["project"]["version"]' in text
    assert '"CFBundleVersion": VERSION' in text
    assert '"CFBundleShortVersionString": VERSION' in text
    # No version number written into the spec, the released one included.
    with open(REPO_ROOT / "pyproject.toml", "rb") as fp:
        current = tomllib.load(fp)["project"]["version"]
    assert current not in text
    assert not re.search(r"""["']\d+\.\d+\.\d+["']""", text)


def test_spec_names_the_extra_that_exists():
    text = SPEC.read_text(encoding="utf-8")
    assert "gui-modern-desktop" not in text
    assert "pyaermod[gui-desktop]" in text


def test_entitlements_file_is_a_valid_minimal_plist():
    assert ENTITLEMENTS.exists(), "packaging/entitlements.plist missing"
    with open(ENTITLEMENTS, "rb") as fp:
        entitlements = plistlib.load(fp)
    assert isinstance(entitlements, dict)
    assert set(entitlements) <= ALLOWED_ENTITLEMENTS
    # A notarized app must not be debuggable by other processes.
    assert "com.apple.security.get-task-allow" not in entitlements


def test_build_desktop_workflow_present():
    assert WORKFLOW.exists(), "build_desktop workflow missing"
    text = WORKFLOW.read_text(encoding="utf-8")
    # All three OSes covered
    for os_runner in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert os_runner in text, f"workflow missing {os_runner}"


def test_workflow_asset_paths_are_unchanged():
    text = WORKFLOW.read_text(encoding="utf-8")
    matrix = dict(re.findall(r"- os: (\S+)\n\s+artifact: \S+\n\s+bin_glob: (\S+)", text))
    assert matrix == {
        "ubuntu-latest": "dist/pyaermod-desktop",
        "macos-latest": "dist/pyaermod-desktop-macos.zip",
        "windows-latest": "dist/pyaermod-desktop.exe",
    }


def test_workflow_cannot_be_triggered_by_a_pull_request():
    """The signing secrets must stay out of reach of unmerged code."""
    text = WORKFLOW.read_text(encoding="utf-8")
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
    assert re.findall(r"^  (\w+):", triggers, flags=re.MULTILINE) == ["workflow_dispatch", "release"]
    assert "pull_request" not in triggers
    # Read-only by default; the build job may write release assets, nothing else.
    assert "\npermissions:\n  contents: read\n\njobs:" in text
    assert re.findall(r"^    permissions:\n((?:      .+\n)+)", text, flags=re.MULTILINE) == [
        '      contents: write  # "Attach to release" uploads the release assets\n'
    ]


@pytest.mark.parametrize("secret", SIGNING_SECRETS)
def test_workflow_reads_each_signing_secret(secret):
    assert f"secrets.{secret}" in WORKFLOW.read_text(encoding="utf-8")


def test_workflow_signs_notarizes_and_staples_the_macos_bundle():
    text = WORKFLOW.read_text(encoding="utf-8")
    for needle in (
        "security create-keychain",
        "security set-key-partition-list",
        "codesign --verify --deep --strict",
        "codesign -dv --verbose=4",
        "ditto -c -k --keepParent dist/pyaermod-desktop.app dist/pyaermod-desktop-macos.zip",
        "xcrun notarytool submit",
        "xcrun notarytool log",
        "xcrun stapler staple",
        "xcrun stapler validate",
        "spctl -a -vvv -t exec",
        "security delete-keychain",
    ):
        assert needle in text, f"workflow missing {needle!r}"
    assert "zip -ry" not in text  # ditto keeps what the notary ticket covers
    assert "set -x" not in text  # would print the secrets


def test_workflow_signing_steps_run_only_on_macos_with_the_secrets():
    signed_only = "runner.os == 'macOS' && steps.signing.outputs.enabled == 'true'"
    for name in ("Import the Developer ID certificate", "Verify the macOS code signature",
                 "Notarize the macOS bundle", "Staple the ticket"):
        assert _step_condition(name) == signed_only, name
    assert "\n        id: signing\n" in _step("Check macOS signing secrets")
    # The ad-hoc zip is still made without the secrets.
    assert _step_condition("Zip macOS .app bundle") == "runner.os == 'macOS'"
    assert _step_condition("Delete the temporary keychain") == "always() && runner.os == 'macOS'"


def test_workflow_steps_run_in_signing_order():
    names = list(_workflow_steps())
    order = [
        "Check macOS signing secrets",
        "Import the Developer ID certificate into a temporary keychain",
        "Build desktop bundle",
        "Verify the macOS code signature",
        "Zip macOS .app bundle",
        "Notarize the macOS bundle",
        "Staple the ticket, re-zip and check with Gatekeeper",
        "Delete the temporary keychain and key files",
        "Upload artifact",
        "Attach to release",
    ]
    assert [n for n in names if n in order] == order


def test_workflow_refuses_an_unsigned_release_and_warns_otherwise():
    script = _step("Check macOS signing secrets")
    assert "EVENT_NAME: ${{ github.event_name }}" in script
    release_branch = script.split('if [ "$EVENT_NAME" = "release" ]; then', 1)[1]
    refuse, warn = release_branch.split("\n          fi\n", 1)
    assert "::error::" in refuse and "exit 1" in refuse
    assert "::warning::" in warn and "Gatekeeper" in warn
    assert "enabled=false" in warn


def test_workflow_passes_the_identity_to_the_build_only_when_signing():
    assert (
        "MACOS_SIGN_IDENTITY: ${{ steps.signing.outputs.enabled == 'true' && secrets.MACOS_SIGN_IDENTITY || '' }}"
        in _step("Build desktop bundle")
    )


def test_desktop_doc_present():
    doc = REPO_ROOT / "docs" / "desktop.md"
    assert doc.exists(), "docs/desktop.md missing"
    text = doc.read_text(encoding="utf-8")
    # Coarse content checks
    assert "pyaermod-desktop" in text
    assert "AERMOD" in text


def test_desktop_doc_names_the_real_release_assets():
    text = (REPO_ROOT / "docs" / "desktop.md").read_text(encoding="utf-8")
    for asset in ("pyaermod-desktop.exe", "pyaermod-desktop-macos.zip"):
        assert asset in text
    # Names the workflow has never produced.
    for wrong in ("pyaermod-desktop-windows-x64.zip", "pyaermod-desktop-linux-x64.tar.gz", "universal"):
        assert wrong not in text
    assert "arm64" in text
    assert "xattr -dr com.apple.quarantine" in text


def test_pyproject_console_scripts_register_desktop():
    py = REPO_ROOT / "pyproject.toml"
    text = py.read_text(encoding="utf-8")
    assert 'pyaermod-desktop = "pyaermod.gui_v2.desktop:main"' in text
    assert 'pyaermod-app = "pyaermod.gui_v2:main"' in text


def test_extras_include_gui_desktop():
    py = REPO_ROOT / "pyproject.toml"
    text = py.read_text(encoding="utf-8")
    assert "gui-desktop" in text
    assert "pywebview" in text
