"""Tests for the EPA SCRAM download registry.

The offline tests check the registry's shape. The network test is the
one that matters: it re-lists each SCRAM directory and asserts every
registered filename is still there, so an EPA rename fails here rather
than as a 404 in a CI job months later. It is marked ``slow`` (and
skipped without ``$PYAERMOD_NETWORK_TESTS``) because it reaches out to
gaftp.epa.gov, which rate-limits.
"""

from __future__ import annotations

import dataclasses
import os
import re
import urllib.error
import urllib.request

import pytest

from pyaermod.epa_sources import (
    EPA_SOURCES,
    SCRAM_ROOT,
    EPASource,
    get_source,
    listing_url,
    programs,
    source_url,
)

NETWORK = os.environ.get("PYAERMOD_NETWORK_TESTS")


class TestRegistryShape:
    def test_every_entry_is_a_zip_under_scram_root(self):
        for key, src in EPA_SOURCES.items():
            assert src.url.startswith(SCRAM_ROOT + "/"), key
            assert src.filename.endswith(".zip"), key
            assert src.key == key

    def test_kinds_are_known(self):
        assert {s.kind for s in EPA_SOURCES.values()} <= {
            "source", "test_cases", "executable",
        }

    def test_the_programs_pyaermod_drives_are_registered(self):
        have = {s.program for s in EPA_SOURCES.values()}
        for program in ("aermod", "aermet", "aermap", "aersurface",
                        "aerscreen", "bpipprime"):
            assert program in have, program

    def test_aerscreen_is_under_screening_not_related(self):
        # The whole point of discovering rather than guessing: AERSCREEN
        # does not live beside the other auxiliary programs.
        assert "screening/aerscreen" in source_url("aerscreen")
        assert "related/" not in source_url("aerscreen")

    def test_aersurface_test_cases_filename_is_singular(self):
        # ...and the test-case archives are not consistently named.
        assert source_url("aersurface", "test_cases").endswith(
            "aersurface_testcase.zip"
        )
        assert source_url("aerscreen", "test_cases").endswith(
            "aerscreen_test_cases.zip"
        )

    def test_listing_url_is_the_parent_directory(self):
        src = get_source("bpipprime")
        assert src.url.startswith(listing_url("bpipprime"))
        assert listing_url("bpipprime").endswith("/")

    def test_unknown_lookup_lists_what_exists(self):
        with pytest.raises(KeyError, match="available"):
            get_source("nosuchmodel")
        with pytest.raises(KeyError, match="available"):
            get_source("aermod", "nosuchkind")

    def test_programs_maps_to_source_archives(self):
        mapping = programs()
        assert mapping["aermod"] == source_url("aermod")
        # makemet has a source archive and no test cases; still listed.
        assert mapping["makemet"].endswith("makemet_code.zip")

    def test_lookup_is_case_insensitive(self):
        assert get_source("AERMOD", "SOURCE") is get_source("aermod", "source")

    def test_entry_is_hashable_and_frozen(self):
        src = get_source("aermod")
        assert isinstance(src, EPASource)
        with pytest.raises(dataclasses.FrozenInstanceError):
            src.filename = "other.zip"  # type: ignore[misc]


def _list_directory(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "pyaermod-tests"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read().decode("latin-1", errors="replace")


@pytest.mark.slow
@pytest.mark.skipif(
    not NETWORK, reason="set PYAERMOD_NETWORK_TESTS=1 to reach gaftp.epa.gov"
)
class TestRegistryMatchesSCRAM:
    def test_every_registered_file_is_in_its_listing(self):
        listings: dict[str, str] = {}
        missing = []
        for key, src in sorted(EPA_SOURCES.items()):
            if src.listing_url not in listings:
                try:
                    listings[src.listing_url] = _list_directory(src.listing_url)
                except (urllib.error.URLError, TimeoutError) as exc:
                    pytest.skip(f"SCRAM unreachable ({src.listing_url}): {exc}")
            names = set(
                re.findall(r'href="([^"]+)"', listings[src.listing_url])
            )
            if src.filename not in names:
                missing.append((key, src.url, sorted(
                    n for n in names if n.endswith(".zip")
                )))
        assert not missing, (
            "registered archives no longer present in their SCRAM listing:\n"
            + "\n".join(
                f"  {k}: {u}\n    zips actually there: {z}"
                for k, u, z in missing
            )
        )
