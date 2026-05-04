# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the pyaermod desktop bundle.

Builds a single-file executable that launches the NiceGUI app inside a
pywebview window. The same spec is used on Windows, macOS, and Linux —
PyInstaller picks per-OS defaults from sys.platform at build time.

Usage::

    pip install pyinstaller pyaermod[gui-modern-desktop]
    pyinstaller packaging/pyaermod_desktop.spec --clean --noconfirm

Output lands in ``dist/pyaermod-desktop`` (Linux/Win) or
``dist/pyaermod-desktop.app`` (macOS).
"""
from __future__ import annotations

import sys
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
ENTRY = ROOT / "src" / "pyaermod" / "gui_v2" / "desktop.py"

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

# macOS: build a .app bundle. Other OSes: single-file binary.
is_macos = sys.platform == "darwin"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="pyaermod-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,         # UPX trips antivirus on Windows; not worth it.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # GUI app — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=is_macos,  # macOS: handle "open via Finder" args
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

if is_macos:
    app = BUNDLE(
        exe,
        name="pyaermod-desktop.app",
        icon=None,
        bundle_identifier="org.atmmod.pyaermod-desktop",
        info_plist={
            "CFBundleName": "PyAERMOD",
            "CFBundleDisplayName": "PyAERMOD",
            "CFBundleVersion": "1.9.0",
            "CFBundleShortVersionString": "1.9.0",
            "NSHighResolutionCapable": True,
        },
    )
