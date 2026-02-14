"""
Tests for pyaermod __init__.py utility functions.

Covers get_version(), print_info(), and _check_dependencies().
"""

import warnings
from unittest.mock import patch

import pytest

import pyaermod


class TestGetVersion:
    def test_returns_version_string(self):
        result = pyaermod.get_version()
        assert result == pyaermod.__version__

    def test_version_format(self):
        version = pyaermod.get_version()
        # Should be semver-like: X.Y.Z
        parts = version.split(".")
        assert len(parts) >= 2


class TestPrintInfo:
    def test_outputs_version(self, capsys):
        pyaermod.print_info()
        captured = capsys.readouterr()
        assert pyaermod.__version__ in captured.out

    def test_outputs_author(self, capsys):
        pyaermod.print_info()
        captured = capsys.readouterr()
        assert pyaermod.__author__ in captured.out

    def test_outputs_url(self, capsys):
        pyaermod.print_info()
        captured = capsys.readouterr()
        assert pyaermod.__url__ in captured.out


class TestCheckDependencies:
    def test_no_warnings_when_all_installed(self):
        """All deps are installed in test env, so no warnings expected."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pyaermod._check_dependencies()
            import_warnings = [x for x in w if issubclass(x.category, ImportWarning)]
            assert len(import_warnings) == 0

    def test_warns_when_matplotlib_missing(self):
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "matplotlib":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import), warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pyaermod._check_dependencies()
            msgs = [str(x.message) for x in w if issubclass(x.category, ImportWarning)]
            assert any("matplotlib" in m for m in msgs)

    def test_warns_when_folium_missing(self):
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "folium":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import), warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pyaermod._check_dependencies()
            msgs = [str(x.message) for x in w if issubclass(x.category, ImportWarning)]
            assert any("folium" in m for m in msgs)

    def test_warns_when_scipy_missing(self):
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "scipy":
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import), warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pyaermod._check_dependencies()
            msgs = [str(x.message) for x in w if issubclass(x.category, ImportWarning)]
            assert any("scipy" in m for m in msgs)
