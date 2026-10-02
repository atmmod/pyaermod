"""Values AERMOD prints with a three-digit exponent and no letter E.

Fortran ``E13.6`` writes 2.82465e-104 as ``0.282465-103``. The runs in
``tests/fixtures/fortran_exponents/`` (see its README) are real AERMOD
v26135 output holding such numbers; every expected value below is one
AERMOD printed there, quoted in the comment beside it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from pyaermod._fortran import fortran_float
from pyaermod.aermod_outputs import (
    read_aermod_aux_file,
    read_event_output,
    read_maxifile,
    read_plotfile,
    read_rankfile,
)
from pyaermod.design_values import read_maxdaily
from pyaermod.ensemble import MANIFEST_NAME, EnsembleManifest, EnsembleManifestEntry, collect_plotfiles
from pyaermod.input_reader import parse_aermod_input, read_aermod_input
from pyaermod.output_parser import AERMODOutputParser, parse_aermod_output
from pyaermod.pathways import EventPeriod
from pyaermod.postfile import read_postfile

RUNS = Path(__file__).parent / "fixtures" / "fortran_exponents"
WASHOUT = RUNS / "washout"
CONC_ONLY = RUNS / "washout_conc"

#: The five receptors 15 to 27 km downwind, where every value is tiny.
FAR = [(12833.05, 7427.88), (13663.68, 5682.30), (14241.02, 3837.02),
       (17375.34, 10050.29), (23602.25, 13645.31)]

#: Hour 20 at those receptors, as AERMOD printed it in post_1h.pst:
#: AVERAGE CONC, TOTAL DEPO, DRY DEPO, WET DEPO.
HOUR_20_FAR = [
    (2.82465e-104, 4.52288e-106, 1.39704e-107, 4.38317e-106),  # 0.282465-103 0.452288-105 ...
    (7.82577e-104, 1.25715e-105, 3.87053e-107, 1.21844e-105),  # 0.782577-103 0.125715-104 ...
    (1.49224e-105, 2.38511e-107, 7.38044e-109, 2.31131e-107),  # 0.149224-104 0.238511-106 ...
    (8.41488e-141, 1.65960e-142, 4.16190e-144, 1.61798e-142),  # 0.841488-140 0.165960-141 ...
    (9.71887e-191, 2.36191e-192, 4.80684e-194, 2.31385e-192),  # 0.971887-190 0.236191-191 ...
]

THREE_DIGIT = re.compile(r"\d\.\d+[-+]\d{3}(?!\d)")

AERMOD_EXE = shutil.which("aermod")


# ---------------------------------------------------------------------------
# The number itself
# ---------------------------------------------------------------------------

class TestFortranFloat:
    @pytest.mark.parametrize(("text", "value"), [
        ("0.282465-103", 2.82465e-104),
        ("0.971887-190", 9.71887e-191),
        ("-0.500000-100", -5.0e-101),
        ("0.100000+101", 1.0e100),
        ("+.5-100", 5.0e-101),
        ("5.-100", 5.0e-100),
        ("  0.282465-103 ", 2.82465e-104),
    ])
    def test_reads_the_e_free_three_digit_exponent(self, text, value):
        assert fortran_float(text) == pytest.approx(value, rel=1e-12, abs=0)

    @pytest.mark.parametrize("text", ["0.282465E-03", "0.282465E-103", "1.5", "-2", "7", "1e5"])
    def test_reads_what_float_reads_unchanged(self, text):
        assert fortran_float(text) == float(text)

    @pytest.mark.parametrize("text", [
        "0.282465-10",      # Fortran writes a two-digit exponent with the E
        "0.282465-1",
        "0.282465-1030",    # no exponent has four digits
        "282465-103",       # Ew.d always writes the decimal point
        "0.282465--103",
        "0.282465-+103",
        "0.282465 -103",
        "0.282465-103x",
        "0.282465-103.",
        ".-103",
        "1-HR",
        "",
    ])
    def test_rejects_anything_else(self, text):
        with pytest.raises(ValueError):
            fortran_float(text)


def test_every_recorded_file_holds_three_digit_exponents():
    """The fixture is only a test while AERMOD's files hold such numbers."""
    files = [WASHOUT / n for n in ("aermod.out", "post_1h.pst", "high_1h.plt", "period.plt")]
    files += [CONC_ONLY / n for n in ("aermod.out", "post_1h.pst", "high_1h.plt",
                                      "maxi_1h.max", "rank_1h.rnk", "evfile.inp")]
    files += [RUNS / "events" / "aermod.out"]
    for path in files:
        assert THREE_DIGIT.search(path.read_text(encoding="latin-1")), path


# ---------------------------------------------------------------------------
# PLOTFILE, MAXIFILE, RANKFILE (pyaermod.aermod_outputs)
# ---------------------------------------------------------------------------

VALUE_COLUMNS = ["AVERAGE_CONC", "TOTAL_DEPO", "DRY_DEPO", "WET_DEPO"]


class TestAuxFiles:
    def test_plotfile_values_are_numbers(self):
        df = read_plotfile(WASHOUT / "high_1h.plt").to_dataframe()
        assert len(df) == 7
        for column in VALUE_COLUMNS:
            assert df[column].dtype.kind == "f", column
        far = df.iloc[2:]
        assert list(zip(far["X"], far["Y"])) == FAR
        for (_, row), expected in zip(far.iterrows(), HOUR_20_FAR):
            assert list(row[VALUE_COLUMNS]) == pytest.approx(list(expected), rel=1e-12, abs=0)
        # 1732.05 1000.00  0.871646E+01 0.975268E-04 0.975268E-04 0.186269E-15
        assert list(df.loc[0, VALUE_COLUMNS]) == pytest.approx(
            [8.71646, 9.75268e-05, 9.75268e-05, 1.86269e-16], rel=1e-12, abs=0)

    def test_period_plotfile_values_are_numbers(self):
        df = read_plotfile(WASHOUT / "period.plt").to_dataframe()
        # 12833.05 7427.88  0.941550-104 (PERIOD average over 3 hours)
        # 23602.25 13645.31 0.323962-190
        assert df["AVERAGE_CONC"].tolist()[2] == pytest.approx(9.41550e-105, rel=1e-12, abs=0)
        assert df["AVERAGE_CONC"].tolist()[6] == pytest.approx(3.23962e-191, rel=1e-12, abs=0)
        assert all(isinstance(v, float) for c in VALUE_COLUMNS for v in df[c])

    def test_single_type_plotfile(self):
        df = read_plotfile(CONC_ONLY / "high_1h.plt").to_dataframe()
        assert df["AVERAGE_CONC"].tolist() == pytest.approx([r[0] for r in HOUR_20_FAR], rel=1e-12, abs=0)

    def test_maxifile(self):
        df = read_maxifile(CONC_ONLY / "maxi_1h.max").to_dataframe()
        assert df["AVERAGE_CONC"].tolist() == pytest.approx([r[0] for r in HOUR_20_FAR], rel=1e-12, abs=0)

    def test_rankfile(self):
        (rec,) = read_rankfile(CONC_ONLY / "rank_1h.rnk").records
        # 1  0.782577-103 93052120   13663.68000    5682.30000
        assert rec["AVERAGE_CONC"] == pytest.approx(7.82577e-104, rel=1e-12, abs=0)
        assert (rec["DATE"], rec["X"], rec["Y"]) == (93052120, 13663.68, 5682.30)

    def test_malformed_value_stays_text(self, tmp_path):
        path = tmp_path / "bad.plt"
        text = (WASHOUT / "high_1h.plt").read_text()
        path.write_text(text.replace("0.282465-103", "0.2824-65-10"))
        df = read_aermod_aux_file(path).to_dataframe()
        assert df["AVERAGE_CONC"].tolist()[2] == "0.2824-65-10"


def test_ensemble_collect_plotfiles(tmp_path):
    """pyaermod.ensemble collects PERIOD PLOTFILEs like this one; a column
    with one such value went to the .npz as text."""
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    shutil.copy(WASHOUT / "period.plt", run_dir)
    EnsembleManifest(path=tmp_path / MANIFEST_NAME).put(EnsembleManifestEntry(
        input_file=str(run_dir / "run.inp"), status="success", run_id="run1",
        run_dir="run1", outputs={"PLOTFILE": ["period.plt"]}))
    table = collect_plotfiles(tmp_path, run_ids=["run1"])
    # 23602.25 13645.31 ... 0.231385-191 (WET DEPO, PERIOD)
    assert table["wet_depo"].tolist()[6] == pytest.approx(2.31385e-192, rel=1e-12, abs=0)
    with np.load(tmp_path / "plotfiles.npz") as npz:
        for column in ("average_conc", "total_depo", "dry_depo", "wet_depo"):
            assert npz[column].dtype.kind == "f", column
            np.testing.assert_array_equal(npz[column], table[column].to_numpy())


# ---------------------------------------------------------------------------
# POSTFILE reader (pyaermod.postfile), on POSTFILEs and PLOTFILEs
# ---------------------------------------------------------------------------

POST_COLUMNS = ["concentration", "total_depo", "dry_depo", "wet_depo"]


class TestPostfile:
    def test_no_row_is_dropped(self):
        data = read_postfile(WASHOUT / "post_1h.pst").data
        # 3 hours x 7 receptors; the rows with tiny values used to vanish.
        assert len(data) == 21
        hour_20 = data[data["date"] == "93052120"]
        far = hour_20[hour_20["x"] > 10000]
        assert list(zip(far["x"], far["y"])) == FAR
        for (_, row), expected in zip(far.iterrows(), HOUR_20_FAR):
            assert list(row[POST_COLUMNS]) == pytest.approx(list(expected), rel=1e-12, abs=0)

    @pytest.mark.parametrize("name", ["high_1h.plt", "period.plt"])
    def test_plotfiles(self, name):
        data = read_postfile(WASHOUT / name).data
        assert len(data) == 7
        plot = read_plotfile(WASHOUT / name).to_dataframe()
        for post_col, plot_col in zip(POST_COLUMNS, VALUE_COLUMNS):
            assert data[post_col].tolist() == plot[plot_col].tolist()

    def test_single_type(self):
        data = read_postfile(CONC_ONLY / "post_1h.pst").data
        assert data["concentration"].tolist() == pytest.approx(
            [r[0] for r in HOUR_20_FAR], rel=1e-12, abs=0)

    def test_headerless_layout_is_inferred(self, tmp_path):
        rows = [ln for ln in (WASHOUT / "post_1h.pst").read_text().splitlines()
                if not ln.startswith("*")]
        # Start at hour 20, so the first row (which the layout is read
        # from) has three-digit exponents in all four value columns.
        path = tmp_path / "noheader.pst"
        path.write_text("\n".join(rows[9:]) + "\n")
        data = read_postfile(path).data
        assert len(data) == 12
        assert data.iloc[0][POST_COLUMNS].tolist() == pytest.approx(
            list(HOUR_20_FAR[0]), rel=1e-12, abs=0)

    def test_malformed_value_is_not_a_row(self, tmp_path):
        path = tmp_path / "bad.pst"
        text = (WASHOUT / "post_1h.pst").read_text()
        path.write_text(text.replace("0.282465-103", "0.28246-5-10"))
        assert len(read_postfile(path).data) == 20


# ---------------------------------------------------------------------------
# aermod.out summary tables (pyaermod.output_parser)
# ---------------------------------------------------------------------------

class TestSummaryTables:
    def test_period_table_keeps_every_row(self):
        results = AERMODOutputParser(WASHOUT / "aermod.out").parse()
        period = results.concentrations["PERIOD"].data
        assert len(period) == 10
        # 3RD HIGHEST VALUE IS  0.260859-103 AT (   13663.68,     5682.30, ...
        # 7TH HIGHEST VALUE IS  0.323962-190 AT (   23602.25,    13645.31, ...
        assert period["concentration"].tolist()[2] == pytest.approx(2.60859e-104, rel=1e-12, abs=0)
        assert period["value_text"].tolist()[2] == "0.260859-103"
        assert period["concentration"].tolist()[6] == pytest.approx(3.23962e-191, rel=1e-12, abs=0)
        # The summary is the PERIOD PLOTFILE, ranked.
        plot = read_plotfile(WASHOUT / "period.plt").to_dataframe()
        assert period["concentration"].tolist()[:7] == sorted(plot["AVERAGE_CONC"], reverse=True)

    def test_deposition_tables(self):
        results = AERMODOutputParser(WASHOUT / "aermod.out").parse()
        plot = read_plotfile(WASHOUT / "period.plt").to_dataframe()
        for kind, column in (("DEPOS", "TOTAL_DEPO"), ("DDEP", "DRY_DEPO"), ("WDEP", "WET_DEPO")):
            table = results.deposition[kind]["PERIOD"].data
            assert len(table) == 10, kind
            assert table["concentration"].tolist()[:7] == sorted(plot[column], reverse=True), kind

    def test_highest_value_with_a_three_digit_exponent(self):
        results = AERMODOutputParser(CONC_ONLY / "aermod.out").parse()
        # HIGH   1ST HIGH VALUE IS  0.782577-103  ON 93052120: AT (   13663.68,     5682.30, ...
        one_hour = results.concentrations["1HR"]
        assert one_hour.max_value == pytest.approx(7.82577e-104, rel=1e-12, abs=0)
        assert one_hour.max_location == (13663.68, 5682.30)
        assert one_hour.data["date"].tolist() == ["93052120"]

    def test_value_is_reader(self):
        text = (CONC_ONLY / "aermod.out").read_text(encoding="latin-1")
        result = AERMODOutputParser._parse_epa_value_is_format(text, "1HR")
        assert result is not None
        assert result.data["concentration"].tolist()[:2] == pytest.approx(
            [7.82577e-104, 2.82465e-104], rel=1e-12, abs=0)

    def test_source_emission_rate(self, tmp_path):
        # OPENPIT SOURCE DATA: PIT  1  0.10000E-04  -500.0 ... (E11.5); a
        # rate below 1e-99 would be printed without the E.
        path = tmp_path / "rate.out"
        text = (WASHOUT / "aermod.out").read_text(encoding="latin-1")
        assert " PIT              1   0.10000E-04 " in text
        path.write_text(text.replace("   0.10000E-04 ", "   0.10000-100 "))
        (pit,) = AERMODOutputParser(path).parse().sources
        assert (pit.source_id, pit.source_type) == ("PIT", "OPENPIT")
        assert pit.emission_rate == pytest.approx(1.0e-101, rel=1e-12, abs=0)

    def test_pyaermod_layout_emission_rate_and_rows(self, tmp_path):
        # The SOURCE LOCATIONS / ANNUAL RESULTS layout of
        # tests/test_output_parser_coverage.py, with E-free values.
        path = tmp_path / "pyaermod.out"
        path.write_text(
            "*** AERMOD - VERSION 24142 ***\n\n"
            "*** SOURCE LOCATIONS ***\n\n"
            "   SOURCE   TYPE       X-COORD      Y-COORD    BASE_ELEV  HGT   TEMP    VELOC   DIAM   EMISS\n"
            "   STK1     POINT      100.00       200.00       5.00      75.0  400.0   15.0    2.5    0.12500-100\n\n"
            "*** ANNUAL RESULTS ***\n\n"
            "   100.00    200.00    0.850000-100\n"
            "   300.00    400.00    4.200\n")
        results = parse_aermod_output(str(path))
        (stk1,) = results.sources
        assert stk1.emission_rate == pytest.approx(1.25e-101, rel=1e-12, abs=0)
        annual = results.concentrations["ANNUAL"].data
        assert annual["concentration"].tolist() == pytest.approx([8.5e-101, 4.2], rel=1e-12, abs=0)

    def test_malformed_value_is_not_a_row(self, tmp_path):
        path = tmp_path / "bad.out"
        text = (WASHOUT / "aermod.out").read_text(encoding="latin-1")
        path.write_text(text.replace("VALUE IS  0.260859-103", "VALUE IS  0.26085-9-10"))
        period = AERMODOutputParser(path).parse().concentrations["PERIOD"].data
        assert len(period) == 9


# ---------------------------------------------------------------------------
# EVENT source contributions
# ---------------------------------------------------------------------------

def test_event_source_contributions():
    near, far = read_event_output(RUNS / "events" / "aermod.out")
    # *** GROUP VALUE =   0.568898E-13 ***   PIT 0.568898E-13   PIT2 0.205726E-22
    assert near.group_value == pytest.approx(5.68898e-14, rel=1e-12, abs=0)
    assert near.contributions == pytest.approx({"PIT": 5.68898e-14, "PIT2": 2.05726e-23}, rel=1e-12, abs=0)
    # *** GROUP VALUE =   0.282465-103 ***   PIT 0.282465-103   PIT2 0.378148-112
    assert (far.event_name, far.x, far.y) == ("FAR", 12833.05, 7427.88)
    assert far.group_value == pytest.approx(2.82465e-104, rel=1e-12, abs=0)
    assert far.contributions == pytest.approx({"PIT": 2.82465e-104, "PIT2": 3.78148e-113}, rel=1e-12, abs=0)


def test_event_contribution_with_a_positive_exponent(tmp_path):
    """``0.1+101`` is the other sign of the same E13.6 form (1e100 and up)."""
    text = (RUNS / "events" / "aermod.out").read_text(encoding="latin-1")
    pairs = "  PIT             0.282465-103             PIT2            0.378148-112"
    assert pairs in text
    path = tmp_path / "plus.out"
    path.write_text(text.replace(pairs, pairs.replace("0.282465-103", "0.282465+101")))
    _, far = read_event_output(path)
    assert far.contributions == pytest.approx({"PIT": 2.82465e100, "PIT2": 3.78148e-113}, rel=1e-12, abs=0)


# ---------------------------------------------------------------------------
# EVENTFIL: the event deck AERMOD writes (pyaermod.input_reader, pathways)
# ---------------------------------------------------------------------------

#: washout_conc/evfile.inp: the 1-hour first high (H001H01001) and the
#: five MAXIFILE events (threshold 0.0), as AERMOD wrote them in E17.6.
EVENTFIL_EVENTS = [
    ("H001H01001", 7.82577e-104, (13663.68, 5682.30)),  # 0.782577-103
    ("TH01000001", 2.82465e-104, (12833.05, 7427.88)),  # 0.282465-103
    ("TH01000002", 7.82577e-104, (13663.68, 5682.30)),
    ("TH01000003", 1.49224e-105, (14241.02, 3837.02)),  # 0.149224-104
    ("TH01000004", 8.41488e-141, (17375.34, 10050.29)),
    ("TH01000005", 9.71887e-191, (23602.25, 13645.31)),  # 0.971887-190
]


def test_eventfil_events_are_read():
    project = read_aermod_input(CONC_ONLY / "evfile.inp")
    assert [u.keyword for u in project.unparsed_lines] == []
    events = project.events.events
    assert [e.event_name for e in events] == [name for name, _, _ in EVENTFIL_EVENTS]
    for event, (_, conc, xy) in zip(events, EVENTFIL_EVENTS):
        assert event.original_conc == pytest.approx(conc, rel=1e-12, abs=0)
        assert (event.location.x, event.location.y) == xy
        assert (event.averaging_period, event.source_group, event.date_text) == (1, "ALL", "93052120")


@pytest.mark.parametrize(("value", "field"), [
    (52.33812, "52.33812"),        # FILEFORM FIX: F17.5, as before
    (0.0, "0.00000"),
    (0.0306833, "3.06833E-02"),    # FILEFORM EXP 0.306833E-01: F17.5 would give 0.03068
    (-0.0306833, "-3.06833E-02"),
    (1.13318, "1.13318"),
    (1e-30, "1.E-30"),             # the smallest exponent STODBL reads
    (2.82465e-104, "0.00000"),     # 0.282465-103: no field AERMOD reads
    (float("nan"), "nan"),         # no E form: F17.5, as before
    (float("inf"), "inf"),
    (float("-inf"), "-inf"),
])
def test_eventper_concentration_field(value, field):
    (line,) = EventPeriod("E1", 1, "93052120", original_conc=value).to_aermod_lines()
    assert line.split()[-1] == field
    assert line.endswith(f" {field:>17}")


def _run_aermod(deck: str, work: Path) -> str:
    work.mkdir()
    for name in ("CORDERO_1993-05-21.SFC", "CORDERO_1993-05-21.PFL"):
        shutil.copy(RUNS / name, work)
    (work / "aermod.inp").write_text(deck)
    subprocess.run([AERMOD_EXE], cwd=work, capture_output=True, timeout=300, check=False)
    out = (work / "aermod.out").read_text(encoding="latin-1")
    assert "AERMOD Finishes Successfully" in out
    return out


@pytest.mark.skipif(AERMOD_EXE is None, reason="aermod not on PATH; build with scripts/build_aermod.sh")
class TestEventDeckRewrite:
    def test_rewritten_eventfil_runs(self, tmp_path):
        """AERMOD reads its own 0.282465-103 as a negative number and
        so skips its EVENTPER check; pyaermod writes 0.00000, which
        AERMOD also leaves unchecked. The events come out the same.

        AERMOD wrote ``EVENTOUT DETAIL``; both runs use ``SOCONT``, the
        table :func:`read_event_output` reads."""
        original = (CONC_ONLY / "evfile.inp").read_text()
        assert "   EVENTOUT  DETAIL\n" in original
        original = original.replace("   EVENTOUT  DETAIL\n", "   EVENTOUT  SOCONT\n")
        out_ref = _run_aermod(original, tmp_path / "aermod")
        written = parse_aermod_input(original).to_aermod_input()
        out = _run_aermod(written, tmp_path / "pyaermod")
        for text in (out_ref, out):
            assert "W497" not in text and "E208" not in text
        ref = read_event_output(tmp_path / "aermod" / "aermod.out")
        new = read_event_output(tmp_path / "pyaermod" / "aermod.out")
        assert [(e.event_name, e.group_value) for e in new] == [(e.event_name, e.group_value) for e in ref]
        assert [e.group_value for e in new] == pytest.approx([c for _, c, _ in EVENTFIL_EVENTS], rel=1e-12, abs=0)

    def test_exp_concentration_is_written_so_aermod_checks_it(self, tmp_path):
        """An EXP EVENTFIL value such as 0.306833E-01 written as F17.5
        (0.03068) makes AERMOD stop trusting the event (W497)."""
        deck = (RUNS / "events" / "aermod.inp").read_text()
        deck = re.sub(r"EV STARTING\n.*EV FINISHED", (
            "EV STARTING\n"
            "   EVENTPER  N12  1  ALL  93052112  0.0\n"
            "   EVENTLOC  N12  XR=  1732.05  YR=  1000.00  0.0  0.0  0.0\n"
            "EV FINISHED"), deck, flags=re.DOTALL)
        _run_aermod(deck, tmp_path / "probe")
        (probe,) = read_event_output(tmp_path / "probe" / "aermod.out")
        assert 1e-5 < probe.group_value < 1.0  # F17.5 would lose digits
        project = parse_aermod_input(deck)
        project.events.events[0].original_conc = probe.group_value
        out = _run_aermod(project.to_aermod_input(), tmp_path / "pyaermod")
        assert "W497" not in out
        (event,) = read_event_output(tmp_path / "pyaermod" / "aermod.out")
        assert event.group_value == probe.group_value


# ---------------------------------------------------------------------------
# MAXDAILY (pyaermod.design_values)
# ---------------------------------------------------------------------------

def _maxdaily(path: Path, value: str) -> Path:
    # ouset.f MXDFRM with OU FILEFORM EXP (without DFAULT for a criteria
    # pollutant): (2(1X,F13.5),1X,E13.6,3(1X,F8.2),2X,A6,2X,A8,2X,I4,2X,I3,2X,I8.8,2X,A8)
    path.write_text(
        "*         FORMAT: (2(1X,F13.5),1X,E13.6,3(1X,F8.2),2X,A6,2X,A8,2X,I4,2X,I3,2X,I8.8,2X,A8)\n"
        f"   12833.05000    7427.88000 {value:>13}     0.00     0.00     0.00    1-HR  ALL     "
        "    141   20  93052120          \n")
    return path


def test_maxdaily_value(tmp_path):
    df = read_maxdaily(_maxdaily(tmp_path / "m.dat", "0.282465-103"))
    assert df["concentration"].tolist() == pytest.approx([2.82465e-104], rel=1e-12, abs=0)


def test_maxdaily_malformed_value_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        read_maxdaily(_maxdaily(tmp_path / "m.dat", "0.28246-5-10"))
