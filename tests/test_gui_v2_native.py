"""Tier T0 tests for the desktop window hooks (:mod:`pyaermod.gui_v2._native`).

A stub stands in for the pywebview window: pywebview is optional, and a
real native dialog cannot be driven from a test (J10 in WP-G7 checks the
bundle).
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

from pyaermod.gui_v2 import _native

REPO = Path(__file__).resolve().parent.parent


class _StubWindow:
    def __init__(self, result):
        self.result = result
        self.calls: list = []

    def create_file_dialog(self, kind, **kwargs):
        self.calls.append((kind, kwargs))
        return self.result


@pytest.fixture
def window(monkeypatch):
    """Install a stub window; the module forgets it afterwards."""
    def install(result):
        stub = _StubWindow(result)
        monkeypatch.setattr(_native, "_WINDOW", stub)
        return stub
    return install


def test_set_window_is_seen_by_native_window(monkeypatch):
    monkeypatch.setattr(_native, "_WINDOW", None)
    assert _native.native_window() is None
    marker = object()
    _native.set_window(marker)
    assert _native.native_window() is marker
    _native.set_window(None)
    assert _native.native_window() is None


@pytest.mark.parametrize("result, expected", [
    ("/home/me/p.json", Path("/home/me/p.json")),
    (("/home/me/t.json",), Path("/home/me/t.json")),
    (["/home/me/l.json", "/ignored.json"], Path("/home/me/l.json")),
    ((), None),
    ("", None),
    (None, None),
])
def test_ask_save_path_normalizes_str_tuple_and_none(window, monkeypatch, result, expected):
    monkeypatch.setitem(sys.modules, "webview", None)      # pywebview absent
    stub = window(result)
    assert _native.ask_save_path("suggested.json") == expected
    kind, kwargs = stub.calls[0]
    assert kind == 30
    assert kwargs == {"save_filename": "suggested.json",
                      "file_types": ("PyAERMOD project (*.json)",)}


def test_ask_save_path_uses_pywebviews_save_dialog_kind(window, monkeypatch):
    fake = types.ModuleType("webview")
    fake.FileDialog = types.SimpleNamespace(SAVE="SAVE-KIND")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "webview", fake)
    stub = window(("/x.json",))
    _native.ask_save_path("x.json")
    assert stub.calls[0][0] == "SAVE-KIND"
    # A pywebview without FileDialog falls back to its numeric constant.
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    _native.ask_save_path("x.json")
    assert stub.calls[1][0] == 30


def test_ask_save_path_without_a_window_is_an_error(monkeypatch):
    monkeypatch.setattr(_native, "_WINDOW", None)
    with pytest.raises(RuntimeError, match="no desktop window"):
        _native.ask_save_path("p.json")


def test_packaging_entry_imports_desktop_main():
    entry = REPO / "packaging" / "desktop_entry.py"
    tree = ast.parse(entry.read_text(encoding="utf-8"))
    imports = [(n.module, [a.name for a in n.names]) for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom)]
    assert ("pyaermod.gui_v2.desktop", ["main"]) in imports
    calls = [n.value.func.id for n in tree.body
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Name)]
    assert calls == ["main"]
    spec = (REPO / "packaging" / "pyaermod_desktop.spec").read_text(encoding="utf-8")
    assert 'ENTRY = ROOT / "packaging" / "desktop_entry.py"' in spec
