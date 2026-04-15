"""Tests for the auxiliary AERMOD text-output readers."""

from __future__ import annotations

import pytest

from pyaermod.aermod_outputs import (
    parse_aermod_header,
    read_aermod_aux_file,
    read_deposition,
    read_maxifile,
    read_plotfile,
    read_rankfile,
    read_seasonhr,
    read_toxxfile,
)

# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

class TestParseHeader:
    def test_plotfile_header(self):
        lines = [
            "* AERMOD (22112): Example Model                    PLOTFILE 01/01/2022",
            "* Averaging Period: ANNUAL      Source Group: ALL",
            "*        X              Y       CONC",
        ]
        h = parse_aermod_header(lines)
        assert h.file_type == "PLOTFILE"
        assert h.averaging_period == "ANNUAL"
        assert h.source_group == "ALL"
        assert h.model_version == "22112"
        assert h.column_names == ["X", "Y", "CONC"]

    def test_maxifile_header_with_rank(self):
        lines = [
            "* AERMOD (23132):                                    MAXIFILE",
            "* Averaging Period: 24-HR    Source Group: GRP1  HIGH-8TH",
            "* RANK        X           Y         CONC         DATE",
        ]
        h = parse_aermod_header(lines)
        assert h.file_type == "MAXIFILE"
        assert h.rank == 8
        assert h.averaging_period == "24-HR"
        assert h.source_group == "GRP1"
        assert h.column_names == ["RANK", "X", "Y", "CONC", "DATE"]

    def test_empty_header(self):
        h = parse_aermod_header([])
        assert h.file_type is None
        assert h.column_names == []


# ---------------------------------------------------------------------------
# PLOTFILE
# ---------------------------------------------------------------------------

class TestReadPlotfile:
    def test_parses_plotfile(self, tmp_path):
        path = tmp_path / "grp_all.plt"
        path.write_text("""\
* AERMOD (22112): test                                  PLOTFILE
* Averaging Period: ANNUAL    Source Group: ALL
*        X              Y       CONC
    -500.00        -500.00      1.234E-01
    -400.00        -500.00      2.345E-01
     500.00         500.00      0.987
""")
        res = read_plotfile(path)
        assert res.header.file_type == "PLOTFILE"
        assert res.header.averaging_period == "ANNUAL"
        assert res.n_records == 3
        assert res.records[0]["X"] == pytest.approx(-500.0)
        assert res.records[0]["CONC"] == pytest.approx(0.1234)

    def test_wrong_type_errors(self, tmp_path):
        path = tmp_path / "x.plt"
        path.write_text("""\
* MAXIFILE
*  X  Y  CONC
1 2 3
""")
        with pytest.raises(ValueError, match="MAXIFILE"):
            read_plotfile(path)


# ---------------------------------------------------------------------------
# MAXIFILE / RANKFILE
# ---------------------------------------------------------------------------

class TestReadMaxifile:
    def test_parses_maxifile(self, tmp_path):
        path = tmp_path / "ri.max"
        path.write_text("""\
* AERMOD (23132):                                    MAXIFILE
* Averaging Period: 24-HR   Source Group: ALL  HIGH-1ST
* RANK        X           Y         CONC         DATE
     1     500.00      500.00       1.234    2020012400
     2     400.00      500.00       0.987    2020011500
""")
        res = read_maxifile(path)
        assert res.header.file_type == "MAXIFILE"
        assert res.header.rank == 1
        assert res.n_records == 2
        assert res.records[0]["RANK"] == 1
        assert res.records[1]["CONC"] == pytest.approx(0.987)


class TestReadRankfile:
    def test_parses_rankfile(self, tmp_path):
        path = tmp_path / "ri.rnk"
        path.write_text("""\
* AERMOD (23132):  RANKFILE
* Averaging: 24-HR   Source Group: ALL
* RANK        X           Y         CONC         DATE
     1     500.00      500.00       5.0    2020010224
""")
        res = read_rankfile(path)
        assert res.header.file_type == "RANKFILE"
        assert res.n_records == 1


# ---------------------------------------------------------------------------
# SEASONHR
# ---------------------------------------------------------------------------

class TestReadSeasonhr:
    def test_infers_96_columns(self, tmp_path):
        # 2 coords + 96 seasonal-hour slots
        vals = " ".join(f"{i * 0.001:.3f}" for i in range(96))
        body = f"    100.00     200.00   {vals}\n"
        path = tmp_path / "x.shr"
        path.write_text(f"""\
* AERMOD:  SEASONHR
* Source Group: ALL
{body}""")
        res = read_seasonhr(path)
        assert res.header.file_type == "SEASONHR"
        assert res.n_records == 1
        cols = res.column_names
        assert "WIN_01" in cols and "FAL_24" in cols
        assert len(cols) == 98


# ---------------------------------------------------------------------------
# Deposition
# ---------------------------------------------------------------------------

class TestReadDeposition:
    def test_ddep(self, tmp_path):
        path = tmp_path / "run.ddep"
        path.write_text("""\
* AERMOD:  DDEP
* Averaging Period: ANNUAL   Source Group: ALL
*   X     Y     CONC
100.0 200.0 0.0025
""")
        res = read_deposition(path)
        assert res.header.file_type == "DDEP"
        assert res.n_records == 1
        assert res.records[0]["CONC"] == pytest.approx(0.0025)

    def test_rejects_non_deposition(self, tmp_path):
        path = tmp_path / "x.plt"
        path.write_text("* PLOTFILE\n* X Y CONC\n1 2 3\n")
        with pytest.raises(ValueError):
            read_deposition(path)


# ---------------------------------------------------------------------------
# TOXXFILE
# ---------------------------------------------------------------------------

class TestReadToxxfile:
    def test_parses(self, tmp_path):
        path = tmp_path / "x.tox"
        path.write_text("""\
* TOXXFILE
* Averaging Period: 1-HR
* RANK  X  Y  CONC  DATE
1 0 0 0.5 2020010101
""")
        res = read_toxxfile(path)
        assert res.header.file_type == "TOXXFILE"
        assert res.records[0]["CONC"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Generic reader
# ---------------------------------------------------------------------------

class TestGenericReader:
    def test_dispatch_on_header(self, tmp_path):
        path = tmp_path / "m.out"
        path.write_text("""\
* PLOTFILE
* X  Y  CONC
0 0 1.5
""")
        res = read_aermod_aux_file(path)
        assert res.header.file_type == "PLOTFILE"
        assert res.records == [{"X": 0, "Y": 0, "CONC": 1.5}]

    def test_dataframe_conversion(self, tmp_path):
        pd = pytest.importorskip("pandas")
        path = tmp_path / "m.out"
        path.write_text("""\
* PLOTFILE
* X  Y  CONC
0 0 1.5
1 1 2.5
""")
        df = read_aermod_aux_file(path).to_dataframe()
        assert list(df.columns) == ["X", "Y", "CONC"]
        assert len(df) == 2
