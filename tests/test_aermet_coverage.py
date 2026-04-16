"""
Additional coverage tests for pyaermod/aermet.py.

Targets the three remaining uncovered lines:
  - Line 568: `continue` when a profile line has < 9 tokens
  - Lines 586-587: `except (ValueError, IndexError): continue` for malformed profile lines
"""

import pytest

from pyaermod.aermet import read_profile_file


class TestReadProfileFileMissingLines:
    """Cover the two skipping branches inside read_profile_file()."""

    def _write_pfl(self, tmp_path, lines):
        pfl = tmp_path / "test.pfl"
        pfl.write_text("\n".join(lines) + "\n")
        return pfl

    def test_short_line_is_skipped(self, tmp_path):
        """Lines with fewer than 9 tokens are silently skipped (line 568)."""
        good = "2020  1  1  1   10.0  0  280.0  3.10  268.2"
        short = "2020  1  1  1"  # only 4 tokens — hits `if len(parts) < 9: continue`
        pfl = self._write_pfl(tmp_path, [good, short])

        result = read_profile_file(pfl)
        df = result["data"]
        # Only the good row survives
        assert len(df) == 1
        assert df.iloc[0]["height"] == pytest.approx(10.0)

    def test_malformed_line_is_skipped(self, tmp_path):
        """Lines that raise ValueError during float() conversion are skipped (lines 586-587)."""
        good = "2020  1  1  1   10.0  0  280.0  3.10  268.2"
        # 9 tokens but the 5th (height) is non-numeric → float() raises ValueError
        bad = "2020  1  1  1  BADHT  0  280.0  3.10  268.2"
        pfl = self._write_pfl(tmp_path, [good, bad])

        result = read_profile_file(pfl)
        df = result["data"]
        # Only the good row survives
        assert len(df) == 1
        assert df.iloc[0]["wind_dir"] == pytest.approx(280.0)
