"""Regression tests for AERMODOutputParser large-file handling.

Before the v1.5 fix, AERMODOutputParser read the entire .OUT file into
memory via f.read(). AERMOD runs with dense receptors can produce .OUT
files well above 500 MB; slurping those would OOM.

These tests verify the head+tail fallback handles large files without
OOMing AND preserves the header/summary metadata users care about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.output_parser import AERMODOutputParser


def _write_synthetic_out(path: Path, header: str, middle_bytes: int, footer: str) -> None:
    """Write a fake AERMOD .OUT with a small header + N bytes of filler
    + a small footer. Used to simulate multi-hundred-MB outputs without
    actually generating them."""
    with open(path, "w", encoding="ascii") as f:
        f.write(header)
        # Pad with a repeating 1 KB block until we've written middle_bytes
        chunk = "x" * 1024 + "\n"  # 1025 bytes per write
        written = 0
        while written < middle_bytes:
            f.write(chunk)
            written += len(chunk)
        f.write(footer)


EPA_HEADER = """\
 *** AERMOD - VERSION 24142  *** *** LARGE TEST                                     ***
 *** AERMET - VERSION 24142  *** ***                                                ***
 MODELOPTs: NonDFAULT CONC ELEV RURAL SigA&SigW
 Pollutant/Gas ID: SO2
 Averaging Time Period: 1-HR
 Jobname: LARGE
 Run Date: 04-22-2026
 Run Time: 12:34:56
"""

EPA_FOOTER = """\

     *** FINISHED SUCCESSFULLY ***
"""


class TestSmallFileStillSlurped:
    """Files under the cap use the old full-read path."""

    def test_small_file_not_truncated(self, tmp_path):
        out = tmp_path / "small.out"
        _write_synthetic_out(out, EPA_HEADER, middle_bytes=1024, footer=EPA_FOOTER)
        parser = AERMODOutputParser(out)
        assert not parser.truncated
        # Full contents present
        assert "AERMOD - VERSION 24142" in parser.content
        assert "FINISHED SUCCESSFULLY" in parser.content


class TestLargeFileTruncated:
    """Files over the cap load head + tail only."""

    def test_size_above_cap_triggers_head_tail(self, tmp_path):
        """With max_slurp_bytes=1 KB we force the fallback flag."""
        out = tmp_path / "big.out"
        _write_synthetic_out(out, EPA_HEADER, middle_bytes=200_000, footer=EPA_FOOTER)
        parser = AERMODOutputParser(out, max_slurp_bytes=1024)
        # truncated flag set
        assert parser.truncated
        # Header metadata (beginning) preserved
        assert "AERMOD - VERSION 24142" in parser.content
        # Footer (end) preserved
        assert "FINISHED SUCCESSFULLY" in parser.content
        # When size < HEAD + TAIL no middle is actually cut — see
        # test_content_bounded_when_truncated below for the real
        # truncation case.

    def test_content_bounded_when_truncated(self, tmp_path):
        """Truncated content must be << file size."""
        out = tmp_path / "big.out"
        # Middle is 10 MB, cap is 1 KB → head (2MB) + tail (64MB) cap
        # exceeds the file, so nothing is actually cut. Use a bigger
        # middle so truncation kicks in.
        _write_synthetic_out(out, EPA_HEADER, middle_bytes=70 * 1024 * 1024,
                             footer=EPA_FOOTER)
        file_size = out.stat().st_size
        # max_slurp_bytes=1 forces truncation
        parser = AERMODOutputParser(out, max_slurp_bytes=1)
        assert parser.truncated
        # Content is head (2 MB) + marker + tail (64 MB) << full 70 MB+
        assert len(parser.content) < file_size
        # Header + footer still present
        assert "LARGE TEST" in parser.content
        assert "FINISHED SUCCESSFULLY" in parser.content

    def test_opt_in_force_truncation(self, tmp_path):
        """max_slurp_bytes=0 forces head+tail regardless of file size."""
        out = tmp_path / "any.out"
        _write_synthetic_out(out, EPA_HEADER, middle_bytes=10_000, footer=EPA_FOOTER)
        parser = AERMODOutputParser(out, max_slurp_bytes=0)
        assert parser.truncated

    def test_header_parse_survives_truncation(self, tmp_path):
        """Parser still extracts ModelRunInfo (version, pollutant) from
        the head-only slice of a large file."""
        out = tmp_path / "big.out"
        _write_synthetic_out(out, EPA_HEADER, middle_bytes=200_000, footer=EPA_FOOTER)
        parser = AERMODOutputParser(out, max_slurp_bytes=1024)
        results = parser.parse()
        # run_info is populated from the header block
        assert results.run_info is not None
        assert results.run_info.version == "24142"
        assert results.run_info.pollutant_id == "SO2"


class TestBackwardsCompat:
    def test_default_cap_is_500mb(self):
        assert AERMODOutputParser.MAX_SLURP_BYTES == 500 * 1024 * 1024

    def test_no_truncated_attr_for_small_existing_usage(self, tmp_path):
        """Existing callers that don't pass max_slurp_bytes should still
        get fully-slurped content on normal files."""
        out = tmp_path / "normal.out"
        _write_synthetic_out(out, EPA_HEADER, middle_bytes=1024, footer=EPA_FOOTER)
        parser = AERMODOutputParser(out)  # no kwarg
        assert parser.truncated is False
