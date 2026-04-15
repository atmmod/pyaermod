"""Tests for the shared optional-dependency helper."""

from __future__ import annotations

import pytest

from pyaermod._optional import optional_import, require


class TestOptionalImport:
    def test_returns_module_when_present(self):
        # stdlib json is always present
        mod = optional_import("json")
        assert mod is not None and mod.__name__ == "json"

    def test_returns_none_when_missing(self):
        mod = optional_import("this_package_does_not_exist_xyz123")
        assert mod is None


class TestRequire:
    def test_returns_module_when_present(self):
        import json
        assert require(json, "json") is json

    def test_raises_when_none(self):
        with pytest.raises(ImportError, match="foo is required"):
            require(None, "foo")

    def test_pip_extra_in_error(self):
        with pytest.raises(ImportError, match=r"pyaermod\[hpc\]"):
            require(None, "tqdm", pip_extra="hpc")

    def test_plain_pip_hint_when_no_extra(self):
        with pytest.raises(ImportError, match="pip install foo"):
            require(None, "foo")


class TestModuleLevelConsistency:
    """HAS_X flags across modules should still agree with their module variables."""

    def test_terrain_utils(self):
        from pyaermod import terrain_utils
        assert (terrain_utils._pyproj is not None) == terrain_utils.HAS_PYPROJ
        assert (terrain_utils.rasterio is not None) == terrain_utils.HAS_RASTERIO

    def test_met_ingest(self):
        from pyaermod import met_ingest
        assert (met_ingest.requests is not None) == met_ingest.HAS_REQUESTS

    def test_runner_utils(self):
        from pyaermod import runner_utils
        assert (runner_utils.tqdm is not None) == runner_utils.HAS_TQDM

    def test_aermod_outputs(self):
        from pyaermod import aermod_outputs
        assert (aermod_outputs.pd is not None) == aermod_outputs.HAS_PANDAS
