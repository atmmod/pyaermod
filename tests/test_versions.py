"""Tests for pyaermod.versions and the output-parser version warning."""

from __future__ import annotations

import logging

import pytest

import pyaermod
from pyaermod.output_parser import AERMODOutputParser
from pyaermod.versions import (
    VALIDATED_AERMET_VERSIONS,
    VALIDATED_AERMOD_VERSIONS,
    is_validated_aermet_version,
    is_validated_aermod_version,
)


def _synthetic_out(version: str) -> str:
    return (
        f" *** AERMOD - VERSION {version}  ***   *** Synthetic run ***        08/22/26\n"
        f" *** AERMET - VERSION  26135 ***   ***                   ***        12:00:00\n"
        "\n"
        " **Model Setup Options Selected:\n"
        "\n"
    )


class TestValidatedVersionTuples:
    def test_newest_first_and_current_target(self):
        assert VALIDATED_AERMOD_VERSIONS[0] == "26135"
        assert VALIDATED_AERMET_VERSIONS[0] == "26135"
        assert "24142" in VALIDATED_AERMOD_VERSIONS
        assert "24142" in VALIDATED_AERMET_VERSIONS
        # Newest first: EPA versions are YYDDD strings, so lexical order works.
        assert list(VALIDATED_AERMOD_VERSIONS) == sorted(VALIDATED_AERMOD_VERSIONS, reverse=True)
        assert list(VALIDATED_AERMET_VERSIONS) == sorted(VALIDATED_AERMET_VERSIONS, reverse=True)

    def test_predicates(self):
        assert is_validated_aermod_version("26135")
        assert is_validated_aermod_version(" 24142 ")
        assert not is_validated_aermod_version("23132")
        assert not is_validated_aermod_version(None)
        assert is_validated_aermet_version("26135")
        assert not is_validated_aermet_version("22112")

    def test_exported_from_package_api(self):
        assert pyaermod.VALIDATED_AERMOD_VERSIONS is VALIDATED_AERMOD_VERSIONS
        assert pyaermod.VALIDATED_AERMET_VERSIONS is VALIDATED_AERMET_VERSIONS
        from pyaermod.regulatory_parity import VALIDATED_AERMOD_VERSIONS as via_parity
        assert via_parity is VALIDATED_AERMOD_VERSIONS


class TestOutputParserVersionWarning:
    @pytest.mark.parametrize("version", ["26135", "24142"])
    def test_validated_version_is_silent(self, tmp_path, caplog, version):
        out = tmp_path / "run.out"
        out.write_text(_synthetic_out(version), encoding="latin-1")
        with caplog.at_level(logging.WARNING, logger="pyaermod.output_parser"):
            results = AERMODOutputParser(out).parse()
        assert results.run_info.version == version
        assert not [r for r in caplog.records if "not been validated" in r.getMessage()]

    def test_unvalidated_version_warns_once(self, tmp_path, caplog):
        out = tmp_path / "run.out"
        out.write_text(_synthetic_out("27001"), encoding="latin-1")
        with caplog.at_level(logging.WARNING, logger="pyaermod.output_parser"):
            results = AERMODOutputParser(out).parse()
        assert results.run_info.version == "27001"  # parsed, not rejected
        warnings = [r for r in caplog.records if "not been validated" in r.getMessage()]
        assert len(warnings) == 1
        msg = warnings[0].getMessage()
        assert "27001" in msg
        assert "26135" in msg and "24142" in msg
        assert str(out) in msg

    def test_missing_banner_does_not_warn(self, tmp_path, caplog):
        out = tmp_path / "run.out"
        out.write_text("no banner here\n", encoding="latin-1")
        with caplog.at_level(logging.WARNING, logger="pyaermod.output_parser"):
            results = AERMODOutputParser(out).parse()
        assert results.run_info.version == "Unknown"
        assert not [r for r in caplog.records if "not been validated" in r.getMessage()]
