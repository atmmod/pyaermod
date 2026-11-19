"""Tests for the output-parser fixes beyond the verifier's (slice-e E1-E8, E11)."""
# ruff: noqa: UP031, RUF005  (printf-style rows mirror Fortran FORMATs)

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

import pyaermod
from pyaermod.aermod_outputs import (
    parse_aermod_header,
    read_aermod_aux_file,
    read_deposition,
    read_toxxfile,
)
from pyaermod.output_parser import AERMODOutputParser
from pyaermod.postfile import (
    HOURLY_MEAN_LIMITATION,
    read_postfile,
    warn_hourly_mean_limitation,
)

FIX = Path(pyaermod.__file__).resolve().parents[2] / "tests" / "fixtures"
CONC_PLT = FIX / "postfile_types" / "conc" / "high_1h.plt"
OUT_DIR = FIX / "output_parser" / "ddep_only"
STACK_ROW = "STACK1           0   0.10000E+03       0.0       0.0     0.0    65.00"


def _rec(payload: bytes) -> bytes:
    return struct.pack("<i", len(payload)) + payload + struct.pack("<i", len(payload))


def _overflowed_plt(tmp_path):
    lines = CONC_PLT.read_text().splitlines()
    hdr = [ln for ln in lines if ln.startswith("*")]
    rows = [ln for ln in lines if not ln.startswith("*")]
    bad = rows[0][:29] + "*" * 13 + rows[0][42:]
    f = tmp_path / "ovf.plt"
    f.write_text("\n".join(hdr + [bad] + rows[1:]) + "\n")
    return f


# ------------------------------------------------------------------ E1
def _annual_file(tmp_path, years):
    def rec(kurdat, n):
        return _rec(struct.pack("<ii8s", kurdat, n, b"ALL     ") + struct.pack("<2d", 1.0 * n, 2.0 * n))
    f = tmp_path / "ann.bin"
    f.write_bytes(b"".join(rec(87123124 + 10000 * n, n) for n in range(1, years + 1)))
    return f


def test_e1_six_year_annual_file_keeps_every_years_values(tmp_path):
    """Years 5 and above used to raise; now the file reads as ANNUAL, one row per year."""
    data = read_postfile(_annual_file(tmp_path, 6)).data
    assert set(data["ave"]) == {"ANNUAL"}
    first = data[data["x"] == 0.0].sort_values("date")
    assert list(first["date"]) == [f"{n:08d}" for n in range(1, 7)]
    assert list(first["concentration"]) == [float(n) for n in range(1, 7)]


def test_e1_explicit_period_still_wins(tmp_path):
    data = read_postfile(_annual_file(tmp_path, 3), averaging_period="ANNUAL").data
    assert set(data["ave"]) == {"ANNUAL"}


def test_e1_constant_ianhrs_short_term_file_is_untouched(tmp_path):
    f = tmp_path / "st.bin"
    f.write_bytes(b"".join(
        _rec(struct.pack("<ii8s", 88010100 + h, 1, b"ALL     ") + struct.pack("<2d", h, h))
        for h in (1, 2, 3)))
    assert set(read_postfile(f).data["ave"]) == {"1-HR"}


# ------------------------------------------------------------------ E2
def test_e2_overflow_warns_once(tmp_path):
    f = _overflowed_plt(tmp_path)
    with pytest.warns(UserWarning, match="asterisks") as seen:
        read_postfile(f)
    assert len([w for w in seen if "asterisks" in str(w.message)]) == 1


def test_e2_aux_reader_keeps_nan_and_infinity_numeric(tmp_path):
    f = tmp_path / "x.plt"
    f.write_text("* PLOTFILE\n* X  Y  CONC\n1.0 2.0 NaN\n3.0 4.0 Infinity\n")
    df = read_aermod_aux_file(f).to_dataframe()
    assert math.isnan(df["CONC"][0]) and math.isinf(df["CONC"][1])


# ------------------------------------------------------------------ E3
def test_e3_multi_year_plotfile_columns(tmp_path):
    fmt = "(3(1X,F13.5),3(1X,F8.2),2X,A6,2X,A8,2X,A5,5X,A8,2X,10(F13.5,2X,I8.8,2X:))"
    head = [
        "* AERMOD (26135 ):  test",
        "* AERMET ( 26135):",
        "* MODELING OPTIONS USED:   RegDFAULT  CONC  ELEV  RURAL",
        "*         PLOT FILE OF    2ND-HIGHEST MAX DAILY 24-HR VALUES AVERAGED OVER   2 YEARS FOR SOURCE GROUP: GRPA    ",
        "*         FOR A TOTAL OF     2 RECEPTORS.",
        "*         FORMAT: " + fmt,
    ]

    def row(x, v, netid, vals):
        s = " %13.5f %13.5f %13.5f %8.2f %8.2f %8.2f  %6s  %-8s  %5s     %8s  " % (
            x, 0, v, 0, 0, 0, " 24-HR", "GRPA", "  2ND", netid)
        return (s + "".join("%13.5f  %08d  " % (c, d) for c, d in vals)).rstrip()
    rows = [row(0, 3.0, "", [(2., 5010101), (4., 6020202)]),
            row(100, 6.0, "NET1", [(5., 5010101), (7., 6020202)])]
    f = tmp_path / "my.plt"
    f.write_text("\n".join(head + rows) + "\n")
    res = read_postfile(f)
    d = res.data
    assert res.header.source_group == "GRPA" and res.header.averaging_period == "24-HR"
    assert list(d["rank"]) == ["2ND", "2ND"]
    assert list(d["concentration"]) == [3.0, 6.0]
    assert list(d["date"]) == ["00000002", "00000002"]   # NUMYRS, as an ANNUAL POSTFILE has it
    assert list(d["yr1_value"]) == [2.0, 5.0] and list(d["yr2_value"]) == [4.0, 7.0]
    assert list(d["yr2_date"]) == ["06020202", "06020202"]


# ------------------------------------------------------------------ E4
@pytest.mark.parametrize("line, period, rank", [
    ("PLOT FILE OF  HIGH   1ST HIGH  1-HR VALUES FOR SOURCE GROUP: ALL", "1-HR", 1),
    ("PLOT FILE OF  HIGH   2ND HIGH 24-HR VALUES FOR SOURCE GROUP: ALL", "24-HR", 2),
    ("PLOT FILE OF  HIGH   8TH HIGH 12-HR VALUES FOR SOURCE GROUP: ALL", "12-HR", 8),
    ("POST/PLOT FILE OF PERIOD VALUES FOR SOURCE GROUP: ALL", "PERIOD", None),
    ("PLOT FILE OF    1ST-HIGHEST MAX DAILY  1-HR VALUES AVERAGED OVER   3 YEARS FOR SOURCE GROUP: ALL",
     "1-HR", 1),
    ("MAXI-FILE FOR  1-HR VALUES >= A THRESHOLD OF    0.000", "1-HR", None),
])
def test_e4_real_header_lines(line, period, rank):
    h = parse_aermod_header(["*         " + line])
    assert h.averaging_period == period and h.rank == rank


def test_e4_season_hour_header_is_seasonhr():
    h = parse_aermod_header(["*         FILE OF SEASON/HOUR VALUES FOR SOURCE GROUP: ALL"])
    assert h.file_type == "SEASONHR" and h.source_group == "ALL"


def test_e4_deposition_plotfile_exposes_its_value_column():
    res = read_deposition(OUT_DIR / "ddep_01H.plt")
    assert res.concentration_column is None   # run_results maps deposition files by this
    assert res.deposition_column == "DRY_DEPO"
    assert res.values() and all(v >= 0 for v in res.values())


def test_e4_read_deposition_keeps_the_ddep_type_names_and_rejects_concentration(tmp_path):
    ok = tmp_path / "a.ddep"
    ok.write_text("* AERMOD:  DDEP\n*   X     Y     CONC\n100.0 200.0 0.0025\n")
    assert read_deposition(ok).n_records == 1
    with pytest.raises(ValueError):
        read_deposition(CONC_PLT)


# ------------------------------------------------------------------ E5
def _toxx_bytes(pairs, npair=100):
    """Records as ouset.f OUTOXX, calc2.f TOXXFL and the flush in aermod.f write them."""
    head2 = struct.pack("<10i", 88, 1, 5, 24, 0, 0, 0, 0, 0, 0)
    head3 = struct.pack("<d9i", 0.5, *([0] * 9))
    codes = [c for c, _ in pairs] + [0] * (npair - len(pairs))
    vals = [v for _, v in pairs] + [0.0] * (npair - len(pairs))
    return (_rec(b"title".ljust(80)) + _rec(head2) + _rec(head3)
            + _rec(struct.pack(f"<{npair}i", *codes)) + _rec(struct.pack(f"<{npair}d", *vals)))


def test_e5_toxxfile_real_layout(tmp_path):
    f = tmp_path / "t.tox"
    f.write_bytes(_toxx_bytes([(100000 * 2 + 1000 * 1 + 4, 2.5), (100000 * 3 + 1000 * 2 + 5, 3.5)]))
    res = read_toxxfile(f)
    assert res.header.file_type == "TOXXFILE"
    assert res.header.extra["NUMREC"] == 5 and res.header.extra["TOXTHR"] == 0.5
    assert res.records == [
        {"ICODE": 201004, "ILINE": 2, "GROUP": 1, "RECEPTOR": 4, "VALUE": 2.5},
        {"ICODE": 302005, "ILINE": 3, "GROUP": 2, "RECEPTOR": 5, "VALUE": 3.5},
    ]


def test_e5_truncated_toxxfile_is_refused(tmp_path):
    f = tmp_path / "t.tox"
    f.write_bytes(_toxx_bytes([(1001, 1.0)])[:-9])
    with pytest.raises(ValueError):
        read_toxxfile(f)


# ------------------------------------------------------------------ E6-E8 (.out)
def test_e6_real_out_fills_dates_periods_and_options():
    info = AERMODOutputParser(str(FIX / "fortran_exponents" / "washout_conc" / "aermod.out")).parse().run_info
    assert info.run_date == "10/02/26"
    assert info.run_time == "16:03:09"
    assert info.averaging_periods == ["1-HR", "PERIOD"]
    assert (info.start_date, info.end_date) == ("1993/05/21", "1993/05/21")
    assert info.urban_option == "RURAL"


def test_e6_short_term_only_periods():
    info = AERMODOutputParser(str(FIX / "psd" / "aermod.out")).parse().run_info
    assert info.averaging_periods == ["1-HR"]


def test_e8_flat_source_is_kept(tmp_path):
    text = (OUT_DIR / "aermod.out").read_text()
    assert STACK_ROW in text
    f = tmp_path / "aermod.out"
    f.write_text(text.replace(STACK_ROW, STACK_ROW.replace("     0.0    65.00", "    FLAT    65.00")))
    res = AERMODOutputParser(str(f)).parse()
    assert [s.source_id for s in res.sources] == ["STACK1"]
    assert res.sources[0].base_elevation == 0.0 and res.sources[0].stack_height == 65.0
    assert res.run_info.num_sources == 1


def test_e7_discrete_polar_receptor_is_absolute(tmp_path):
    text = (OUT_DIR / "aermod.out").read_text()
    text = text.replace(STACK_ROW, STACK_ROW.replace("       0.0       0.0", "    1000.0    2000.0"))
    polar = (
        "\n                                           *** DISCRETE POLAR RECEPTORS ***\n"
        "                                            ORIGIN:    (DIST, DIR, ZELEV, ZHILL, ZFLAG)\n"
        "                                            SRCID:    (METERS,DEG,METERS,METERS,METERS)\n\n"
        " STACK1      : (    500.0,   90.0,    5.0,    6.0,    0.0);  "
        "STACK1      : (    100.0,  180.0,    0.0,    0.0,    0.0); \n"
        " NOSUCH      : (    100.0,    0.0,    0.0,    0.0,    0.0); \n\n"
        " *** AERMOD - VERSION 26135  ***\n")
    f = tmp_path / "aermod.out"
    f.write_text(text + polar)
    res = AERMODOutputParser(str(f)).parse()
    found = {(round(r.x_coord, 3), round(r.y_coord, 3)): r for r in res.receptors}
    # 500 m due east and 100 m due south of STACK1 at (1000, 2000)
    assert set(found) == {(1500.0, 2000.0), (1000.0, 1900.0)}
    assert (found[(1500.0, 2000.0)].z_elev, found[(1500.0, 2000.0)].z_hill) == (5.0, 6.0)


# ------------------------------------------------------------------ E11
def test_e11_hourly_mean_warning_names_the_limitation():
    def averages():
        warn_hourly_mean_limitation("the 24-hour mean")
    with pytest.warns(UserWarning, match="calm or missing") as seen:
        averages()
    assert len(seen) == 1
    assert "75%" in HOURLY_MEAN_LIMITATION
