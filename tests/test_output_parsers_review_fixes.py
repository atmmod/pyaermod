"""Verifier tests for slice-e findings E1-E5 (fail at HEAD)."""
# ruff: noqa: UP031, RUF005  (printf-style rows mirror Fortran FORMATs)

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

import pyaermod
from pyaermod.aermod_outputs import (
    read_aermod_aux_file,
    read_deposition,
    read_plotfile,
    read_toxxfile,
)
from pyaermod.postfile import read_postfile

FIX = Path(pyaermod.__file__).resolve().parents[2] / "tests" / "fixtures"
ALBANY = FIX / "gui" / "aermod_recordings" / "albany_success" / "outputs"
WASHOUT = FIX / "fortran_exponents" / "washout_conc"
CONC_PLT = FIX / "postfile_types" / "conc" / "high_1h.plt"


def _rec(payload: bytes) -> bytes:
    return struct.pack("<i", len(payload)) + payload + struct.pack("<i", len(payload))


# ------------------------------------------------------------------ E1
def test_e1_multi_year_annual_binary_postfile_is_not_labelled_n_hr(tmp_path):
    """PSTANN writes NUMYRS (1, 2, 3 ...) as IANHRS, one record per year (aermod.f CHK_ENDYR
    increments NUMYRS before PSTANN). Inferred mode must not call those 1-HR, 2-HR, 3-HR."""
    def rec(kurdat, n):
        return _rec(struct.pack("<ii8s", kurdat, n, b"ALL     ") + struct.pack("<2d", 1.0 * n, 2.0 * n))
    f = tmp_path / "ann.bin"
    f.write_bytes(b"".join(rec(k, n) for k, n in [(88123124, 1), (89123124, 2), (90123124, 3)]))
    try:
        result = read_postfile(f)
    except ValueError:
        return  # asking the caller for averaging_period is an acceptable fix
    assert set(result.data["ave"]) == {"ANNUAL"}


# ------------------------------------------------------------------ E2
def _overflowed_plt(tmp_path):
    lines = CONC_PLT.read_text().splitlines()
    hdr = [ln for ln in lines if ln.startswith("*")]
    rows = [ln for ln in lines if not ln.startswith("*")]
    bad = rows[0][:29] + "*" * 13 + rows[0][42:]   # width-preserving: 3rd field is F13.5
    f = tmp_path / "ovf.plt"
    f.write_text("\n".join(hdr + [bad] + rows[1:]) + "\n")
    return f, len(rows)


def test_e2_postfile_keeps_row_with_overflowed_field_as_nan(tmp_path):
    f, n = _overflowed_plt(tmp_path)
    data = read_postfile(f).data
    assert len(data) == n
    assert data["concentration"].isna().sum() == 1


def test_e2_aux_reader_gives_numeric_column_for_overflowed_field(tmp_path):
    f, n = _overflowed_plt(tmp_path)
    df = read_aermod_aux_file(f).to_dataframe()
    assert len(df) == n
    col = next(c for c in df.columns if "CONC" in c.upper())
    assert all(isinstance(v, float) for v in df[col])
    assert sum(math.isnan(v) for v in df[col]) == 1


# ------------------------------------------------------------------ E3
def test_e3_multi_year_max_daily_plotfile_date_is_not_the_rank_token(tmp_path):
    fmt = "(3(1X,F13.5),3(1X,F8.2),2X,A6,2X,A8,2X,A5,5X,A8,2X,10(F13.5,2X,I8.8,2X:))"
    lines = [
        "* AERMOD (26135 ):  test                                                                   10/19/26",
        "* AERMET ( 26135):                                                                          14:10:38",
        "* MODELING OPTIONS USED:   RegDFAULT  CONC  ELEV  RURAL",
        "*         PLOT FILE OF    1ST-HIGHEST MAX DAILY  1-HR VALUES AVERAGED OVER   3 YEARS FOR SOURCE GROUP: ALL     ",
        "*         FOR A TOTAL OF     2 RECEPTORS.",
        "*         FORMAT: " + fmt,
        "*        X             Y      AVERAGE CONC    ZELEV    ZHILL    ZFLAG    AVE     GRP       RANK     NET ID   AVER CONC YR1  DATE YR1  AVER CONC YR2  DATE YR2  AVER CONC YR3  DATE YR3",
        "* ____________  ____________  ____________   ______   ______   ______  ______  ________  ________  ________",
    ]

    def row(x, y, v, vals):
        s = " %13.5f %13.5f %13.5f %8.2f %8.2f %8.2f  %6s  %-8s  %5s     %8s  " % (
            x, y, v, 0, 0, 0, "  1-HR", "ALL", "  1ST", "")
        return (s + "".join("%13.5f  %08d  " % (c, d) for c, d in vals)).rstrip()
    rows = [row(0, 0, 3.0, [(2., 5010101), (3., 6020202), (4., 7030303)]),
            row(100, 0, 6.0, [(5., 5010101), (6., 6020202), (7., 7030303)])]
    f = tmp_path / "my.plt"
    f.write_text("\n".join(lines + rows) + "\n")
    data = read_postfile(f).data
    assert "1ST" not in set(data["date"].astype(str))


# ------------------------------------------------------------------ E4
def test_e4_rankfile_and_maxifile_types_detected_on_real_files():
    assert read_aermod_aux_file(WASHOUT / "rank_1h.rnk").header.file_type == "RANKFILE"
    assert read_aermod_aux_file(WASHOUT / "maxi_1h.max").header.file_type == "MAXIFILE"


def test_e4_read_plotfile_rejects_a_rankfile():
    with pytest.raises(ValueError):
        read_plotfile(WASHOUT / "rank_1h.rnk")


def test_e4_short_term_plotfile_average_and_rank_from_real_headers():
    h24 = read_aermod_aux_file(ALBANY / "pyaermod_24H.plt").header
    h01 = read_aermod_aux_file(ALBANY / "pyaermod_01H.plt").header
    assert h24.averaging_period == "24-HR" and h24.rank == 1   # head says "HIGH   1ST HIGH 24-HR"
    assert h01.averaging_period == "1-HR"
    assert read_aermod_aux_file(ALBANY / "pyaermod_03H.plt").header.averaging_period == "3-HR"


def test_e4_read_deposition_accepts_a_real_deposition_plotfile():
    read_deposition(FIX / "output_parser" / "ddep_only" / "ddep_01H.plt")


# ------------------------------------------------------------------ E5
def test_e5_toxxfile_binary_is_read_or_refused_not_decoded_as_text(tmp_path):
    """ouset.f opens the TOXXFILE FORM='UNFORMATTED'. Reading it as latin-1 lines returns junk."""
    b = _rec(b"title".ljust(80)) + _rec(struct.pack("<7i", 88, 1, 5, 2, 0, 0, 0)) + _rec(struct.pack("<d", 1.5))
    b += _rec(struct.pack("<2i", 100000 + 1000 + 1, 200000 + 1000 + 3)) + _rec(struct.pack("<2d", 2.5, 3.5))
    f = tmp_path / "toxx.bin"
    f.write_bytes(b)
    try:
        result = read_toxxfile(f)
    except (NotImplementedError, ValueError):
        return
    values = [v for rec in result.records for v in (rec.values() if hasattr(rec, "values") else rec)]
    assert 2.5 in values and 3.5 in values
