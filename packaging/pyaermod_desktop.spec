# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the pyaermod desktop bundle.

Launches the NiceGUI app inside a pywebview window. The same spec is
used on Windows, macOS, and Linux:

- Windows and Linux build a single-file executable (onefile).
- macOS builds a onedir ``.app`` bundle (``COLLECT`` + ``BUNDLE``). A
  onefile executable inside a ``.app`` unpacks its libraries at run
  time, so they cannot be signed in place or notarized, and PyInstaller
  7 makes that combination an error.

Usage::

    pip install pyinstaller "pyaermod[gui-desktop]"
    pyinstaller packaging/pyaermod_desktop.spec --clean --noconfirm

Output lands in ``dist/pyaermod-desktop`` (Linux),
``dist/pyaermod-desktop.exe`` (Windows) or
``dist/pyaermod-desktop.app`` (macOS).

macOS signing: set ``MACOS_SIGN_IDENTITY`` to a Developer ID
Application identity in the keychain and PyInstaller signs every
collected binary, the executable and the bundle with it, with the
hardened runtime, a secure timestamp and
``packaging/entitlements.plist``. Unset (or empty), the bundle is
ad-hoc signed, which runs on the machine that built it but is blocked
by Gatekeeper once downloaded. Notarization is a separate step; see
``.github/workflows/build_desktop.yml`` and ``RELEASING.md``.
"""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------
# NiceGUI / pywebview have a number of dynamically-loaded modules that
# PyInstaller's static analysis misses. Adding them explicitly here is
# the well-trodden path; the alternatives (auto-detect via traces) are
# slow and fragile.
hidden = []
for pkg in (
    "nicegui",
    "engineio",
    "socketio",
    "uvicorn",
    "fastapi",
    "starlette",
    "anyio",
    "watchfiles",
    "webview",
    "pyaermod",
):
    hidden += collect_submodules(pkg)

# Pull in NiceGUI's bundled JS / CSS / template assets.
datas = collect_data_files("nicegui")
# Ditto for pywebview if available.
try:
    datas += collect_data_files("webview")
except Exception:  # noqa: BLE001
    pass


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------
ROOT = Path(SPECPATH).resolve().parent
# A launcher, not desktop.py: run as __main__, desktop.py's relative
# imports fail.
ENTRY = ROOT / "packaging" / "desktop_entry.py"

block_cipher = None

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Streamlit isn't needed in the desktop bundle — keep size down.
        "streamlit",
        # Test deps
        "pytest",
        "hypothesis",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# The bundle version is the package version, read from pyproject.toml so
# that it cannot drift from the release (and so the spec does not depend
# on which pyaermod happens to be importable at build time).
with open(ROOT / "pyproject.toml", "rb") as _fp:
    VERSION = tomllib.load(_fp)["project"]["version"]

is_macos = sys.platform == "darwin"

# macOS signing. An unset or empty MACOS_SIGN_IDENTITY means ad-hoc.
# The entitlements only take effect under the hardened runtime, which
# PyInstaller switches on when it is given a real identity.
CODESIGN_IDENTITY = (os.environ.get("MACOS_SIGN_IDENTITY") or None) if is_macos else None
ENTITLEMENTS = str(ROOT / "packaging" / "entitlements.plist") if is_macos else None

# Options shared by the onefile (Windows, Linux) and onedir (macOS) EXE.
exe_options = dict(
    name="pyaermod-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,         # UPX trips antivirus on Windows; not worth it.
    upx_exclude=[],
    console=False,     # GUI app — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=is_macos,  # macOS: handle "open via Finder" args
    target_arch=None,  # native: arm64 on the macos-latest runner
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=ENTITLEMENTS,
    icon=None,
)

if is_macos:
    # onedir: the executable holds only the bootloader and the Python
    # archive; libraries and data files sit beside it in the bundle,
    # where each one is signed in place.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        **exe_options,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="pyaermod-desktop",
    )
    app = BUNDLE(
        coll,
        name="pyaermod-desktop.app",
        icon=None,
        bundle_identifier="org.atmmod.pyaermod-desktop",
        version=VERSION,
        info_plist={
            "CFBundleName": "PyAERMOD",
            "CFBundleDisplayName": "PyAERMOD",
            "CFBundleVersion": VERSION,
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
else:
    # onefile: everything is packed into the one executable.
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        runtime_tmpdir=None,
        **exe_options,
    )
