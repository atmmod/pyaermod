"""
POSTFILE and PLOTFILE reading for every set of output types on MODELOPT.

The files under tests/fixtures/postfile_types/ are what AERMOD v26135
wrote for one deck run with each of the 15 non-empty sets of CONC, DEPOS,
DDEP and WDEP (plus one with the keywords out of AERMOD's order); see the
README there. Each run writes the same 1-hour values twice, as a text
POSTFILE for source group ALL and a binary one for group STK, which holds
the same single source, so the two formats check each other.
"""

from pathlib import Path

import numpy as np
import pytest

from pyaermod.postfile import (
    OUTPUT_TYPES,
    PostfileParser,
    UnformattedPostfileParser,
    _normalize_output_types,
    read_postfile,
)

FIXTURES = Path(__file__).parent / "fixtures" / "postfile_types"

COLUMN = {"CONC": "concentration", "DEPOS": "total_depo",
          "DDEP": "dry_depo", "WDEP": "wet_depo"}

# case directory -> output types in AERMOD's order
CASES = {
    "conc": ("CONC",),
    "depos": ("DEPOS",),
    "ddep": ("DDEP",),
    "wdep": ("WDEP",),
    "conc_depos": ("CONC", "DEPOS"),
    "conc_ddep": ("CONC", "DDEP"),
    "conc_wdep": ("CONC", "WDEP"),
    "depos_ddep": ("DEPOS", "DDEP"),
    "depos_wdep": ("DEPOS", "WDEP"),
    "ddep_wdep": ("DDEP", "WDEP"),
    "conc_depos_ddep": ("CONC", "DEPOS", "DDEP"),
    "conc_depos_wdep": ("CONC", "DEPOS", "WDEP"),
    "conc_ddep_wdep": ("CONC", "DDEP", "WDEP"),
    "depos_ddep_wdep": ("DEPOS", "DDEP", "WDEP"),
    "conc_depos_ddep_wdep": ("CONC", "DEPOS", "DDEP", "WDEP"),
    "wdep_ddep_conc_keyword_order": ("CONC", "DDEP", "WDEP"),
}
MULTI = [c for c, t in CASES.items() if len(t) > 1]
SINGLE = [c for c, t in CASES.items() if len(t) == 1]

RECEPTORS = [(-50.0, -150.0), (-130.0, -400.0), (-270.0, -750.0)]
DATES = ["96022811", "96022812", "96022813", "96022814"]
TAIL = ["zelev", "zhill", "zflag", "ave", "grp", "date"]

# The first row of the four-type text POSTFILE, as AERMOD printed it:
#   -50.00000  -150.00000  487.72309  0.13153  0.12277  0.00875  0.00 ...
FIRST_ROW_ALL_TYPES = {"concentration": 487.72309, "total_depo": 0.13153,
                       "dry_depo": 0.12277, "wet_depo": 0.00875}


def _modelopt(case):
    deck = (FIXTURES / case / "aermod.inp").read_text().splitlines()
    return next(line for line in deck if "MODELOPT" in line).split(None, 1)[1]


def _columns(types):
    return ["concentration"] if len(types) == 1 else [COLUMN[t] for t in types]


def _text(case):
    return read_postfile(FIXTURES / case / "post_1h.pst")


def _binary(case, **kw):
    return read_postfile(FIXTURES / case / "post_1h.bin",
                         receptor_coords=RECEPTORS, **kw)


# ---------------------------------------------------------------------------
# Text POSTFILE
# ---------------------------------------------------------------------------

class TestTextPostfileTypes:

    @pytest.mark.parametrize("case", list(CASES))
    def test_columns_follow_the_header(self, case):
        types = CASES[case]
        result = _text(case)
        assert result.output_types == types
        assert list(result.data.columns) == ["x", "y", *_columns(types), *TAIL]

    @pytest.mark.parametrize("case", list(CASES))
    def test_fields_after_the_values_are_not_shifted(self, case):
        data = _text(case).data
        assert len(data) == 12
        assert (data["ave"] == "1-HR").all()
        assert (data["grp"] == "ALL").all()
        assert list(data["date"].unique()) == DATES
        assert (data[["zelev", "zhill", "zflag"]] == 0.0).all().all()
        assert list(zip(data["x"], data["y"]))[:3] == RECEPTORS

    def test_four_types_first_row(self):
        row = _text("conc_depos_ddep_wdep").data.iloc[0]
        for column, value in FIRST_ROW_ALL_TYPES.items():
            assert row[column] == pytest.approx(value, abs=1e-5)

    @pytest.mark.parametrize("case", list(CASES))
    def test_each_type_has_the_same_values_in_every_run(self, case):
        """A type's values do not depend on which other types the run wrote."""
        result = _text(case)
        reference = _text("conc_depos_ddep_wdep")
        for t in CASES[case]:
            np.testing.assert_allclose(
                result.data[result.column_for(t)].to_numpy(),
                reference.data[COLUMN[t]].to_numpy(), atol=1e-5)

    def test_total_is_dry_plus_wet(self):
        data = _text("conc_depos_ddep_wdep").data
        np.testing.assert_allclose(
            data["total_depo"], data["dry_depo"] + data["wet_depo"], atol=2e-5)
        assert (data["wet_depo"] > 0).all()

    def test_keyword_order_does_not_change_the_columns(self):
        a = _text("wdep_ddep_conc_keyword_order").data
        b = _text("conc_ddep_wdep").data
        assert list(a.columns) == list(b.columns)
        np.testing.assert_allclose(a["wet_depo"], b["wet_depo"])

    def test_single_type_values_stay_in_concentration(self):
        for case in SINGLE:
            result = _text(case)
            assert result.column_for(CASES[case][0]) == "concentration"
            assert "dry_depo" not in result.data.columns

    def test_file_without_conc_has_no_concentration_column(self):
        result = _text("ddep_wdep")
        assert "concentration" not in result.data.columns
        # the summaries use the first output type
        assert result.max_concentration == pytest.approx(result.data["dry_depo"].max())
        idx = result.data["dry_depo"].idxmax()
        assert result.max_location == (result.data.loc[idx, "x"], result.data.loc[idx, "y"])
        assert list(result.get_max_by_receptor().columns) == ["x", "y", "dry_depo"]

    def test_matching_output_types_are_accepted(self):
        path = FIXTURES / "conc_ddep" / "post_1h.pst"
        result = read_postfile(path, output_types=["DDEP", "CONC"])
        assert result.output_types == ("CONC", "DDEP")

    def test_conflicting_output_types_raise(self):
        path = FIXTURES / "conc_ddep" / "post_1h.pst"
        with pytest.raises(ValueError, match="header names output types"):
            read_postfile(path, output_types="CONC WDEP")


class TestTextPostfileWithoutLabels:
    """Files derived from a real POSTFILE by deleting header lines."""

    def _strip(self, tmp_path, case, drop):
        lines = (FIXTURES / case / "post_1h.pst").read_text().splitlines(keepends=True)
        kept = [line for line in lines if not any(d in line for d in drop)]
        path = tmp_path / f"{case}.pst"
        path.write_text("".join(kept))
        return path

    def test_modelopt_line_names_the_types(self, tmp_path):
        path = self._strip(tmp_path, "depos_wdep", ["AVERAGE CONC", "TOTAL DEPO"])
        result = read_postfile(path)
        assert result.output_types == ("DEPOS", "WDEP")
        assert list(result.data.columns[2:4]) == ["total_depo", "wet_depo"]

    def test_two_unnamed_columns_need_output_types(self, tmp_path):
        path = self._strip(tmp_path, "depos_wdep", ["TOTAL DEPO", "MODELING OPTIONS"])
        with pytest.raises(ValueError, match="pass output_types"):
            read_postfile(path)
        result = read_postfile(path, output_types="DEPOS WDEP")
        assert result.data["ave"].iloc[0] == "1-HR"
        np.testing.assert_allclose(result.data["wet_depo"], _text("depos_wdep").data["wet_depo"])

    def test_four_unnamed_columns_are_all_four_types(self, tmp_path):
        path = self._strip(tmp_path, "conc_depos_ddep_wdep", ["TOTAL DEPO", "MODELING OPTIONS"])
        assert read_postfile(path).output_types == OUTPUT_TYPES

    def test_three_unnamed_columns_keep_the_earlier_reading(self, tmp_path):
        path = self._strip(tmp_path, "conc_ddep_wdep", ["AVERAGE CONC", "MODELING OPTIONS"])
        result = read_postfile(path)
        assert result.output_types == ("CONC", "DDEP", "WDEP")
        np.testing.assert_allclose(result.data["wet_depo"], _text("conc_ddep_wdep").data["wet_depo"])

    def _replace_options(self, path, options):
        lines = path.read_text().splitlines(keepends=True)
        path.write_text("".join(
            f"* MODELING OPTIONS USED:   {options}\n" if "MODELING OPTIONS" in line else line
            for line in lines))

    def test_options_that_disagree_with_the_format_line_are_not_used(self, tmp_path):
        path = self._strip(tmp_path, "depos_wdep", ["TOTAL DEPO"])
        self._replace_options(path, "RegDFAULT  CONC  DDEP  WDEP  ELEV")
        with pytest.raises(ValueError, match="pass output_types"):
            read_postfile(path)

    def test_options_without_output_types_leave_one_column(self, tmp_path):
        path = self._strip(tmp_path, "conc", ["AVERAGE CONC"])
        self._replace_options(path, "RegDFAULT  ELEV  RURAL")
        result = read_postfile(path)
        assert result.output_types is None
        assert list(result.data.columns) == ["x", "y", "concentration", *TAIL]

    def test_header_only_file_gets_the_type_columns(self, tmp_path):
        lines = (FIXTURES / "depos_ddep" / "post_1h.pst").read_text().splitlines(keepends=True)
        path = tmp_path / "header_only.pst"
        path.write_text("".join(line for line in lines if line.startswith("*")))
        result = read_postfile(path)
        assert result.data.empty
        assert list(result.data.columns) == ["x", "y", "total_depo", "dry_depo", *TAIL]


# ---------------------------------------------------------------------------
# PLOTFILE of first-highest values
# ---------------------------------------------------------------------------

class TestPlotfileTypes:

    @pytest.mark.parametrize("case", list(CASES))
    def test_columns_rank_and_date(self, case):
        types = CASES[case]
        result = read_postfile(FIXTURES / case / "high_1h.plt")
        assert result.output_types == types
        assert list(result.data.columns) == [
            "x", "y", *_columns(types), "zelev", "zhill", "zflag", "ave", "grp", "rank", "date"]
        assert (result.data["rank"] == "1ST").all()
        # NET ID is blank for DISCCART receptors; the date is still read
        assert result.data["date"].isin(DATES).all()

    @pytest.mark.parametrize("case", list(CASES))
    def test_highs_are_the_postfile_maxima(self, case):
        high = read_postfile(FIXTURES / case / "high_1h.plt")
        post = _text(case)
        for t in CASES[case]:
            column = post.column_for(t)
            by_receptor = post.data.groupby(["x", "y"], sort=False)[column].max()
            np.testing.assert_allclose(high.data[column].to_numpy(), by_receptor.to_numpy(), atol=1e-5)

    def test_date_is_that_of_the_first_type(self):
        # DATE(CONC): AERMOD prints the date of the first type's high value
        high = read_postfile(FIXTURES / "conc_wdep" / "high_1h.plt").data
        post = _text("conc_wdep").data
        first = post[(post.x == -50.0) & (post.y == -150.0)]
        assert high["date"].iloc[0] == first.loc[first["concentration"].idxmax(), "date"]
        assert first.loc[first["wet_depo"].idxmax(), "date"] != high["date"].iloc[0]


# ---------------------------------------------------------------------------
# Binary (UNFORM) POSTFILE
# ---------------------------------------------------------------------------

class TestBinaryPostfileTypes:

    @pytest.mark.parametrize("case", list(CASES))
    def test_modelopt_line_gives_the_layout(self, case):
        types = CASES[case]
        result = _binary(case, output_types=_modelopt(case))
        assert result.output_types == types
        assert list(result.data.columns) == ["x", "y", *_columns(types), *TAIL]
        assert len(result.data) == 12
        assert list(result.data["date"].unique()) == DATES

    @pytest.mark.parametrize("case", list(CASES))
    def test_binary_matches_text(self, case):
        text = _text(case)
        binary = _binary(case, output_types=list(reversed(CASES[case])))
        for t in CASES[case]:
            column = text.column_for(t)
            np.testing.assert_allclose(binary.data[column], text.data[column], atol=6e-6)
        assert (binary.data["grp"] == "STK").all()

    def test_four_types_first_row(self):
        row = _binary("conc_depos_ddep_wdep", num_receptors=3).data.iloc[0]
        for column, value in FIRST_ROW_ALL_TYPES.items():
            assert row[column] == pytest.approx(value, abs=6e-6)

    def test_num_receptors_settles_four_types(self):
        result = _binary("conc_depos_ddep_wdep", num_receptors=3)
        assert result.output_types == OUTPUT_TYPES

    def test_num_receptors_keeps_the_three_type_default(self):
        result = _binary("conc_ddep_wdep", num_receptors=3)
        assert result.output_types == ("CONC", "DDEP", "WDEP")
        np.testing.assert_allclose(result.data["wet_depo"], _text("conc_ddep_wdep").data["wet_depo"], atol=6e-6)

    def test_single_type_with_the_wrong_receptor_count_raises(self):
        with pytest.raises(ValueError, match="Expected 2 values but record contains 3"):
            _binary("conc", num_receptors=2)
        assert _binary("conc", num_receptors=3).output_types is None

    def test_two_types_without_output_types_raise(self):
        with pytest.raises(ValueError, match="pass output_types"):
            _binary("ddep_wdep", num_receptors=3)

    def test_single_type_is_unchanged(self):
        result = _binary("conc")
        assert result.output_types is None
        assert list(result.data.columns) == ["x", "y", "concentration", *TAIL]
        np.testing.assert_allclose(result.data["concentration"], _text("conc").data["concentration"], atol=6e-6)
        ddep = _binary("ddep", output_types="DDEP")
        assert ddep.output_types == ("DDEP",)
        assert ddep.column_for("DDEP") == "concentration"

    def test_wrong_number_of_types_raises(self):
        # 9 values per record (3 types x 3 receptors) cannot be 2 types
        with pytest.raises(ValueError, match="not divisible by 2"):
            _binary("conc_ddep_wdep", output_types="CONC DDEP")

    def test_wrong_types_that_divide_the_record_are_caught_by_the_coords(self):
        # 12 values per record read as 3 types would be 4 receptors
        with pytest.raises(ValueError, match="receptor_coords has 3 receptors"):
            _binary("conc_depos_ddep_wdep", output_types="CONC DDEP WDEP")
        with pytest.raises(ValueError, match="num_receptors=3"):
            _binary("conc_depos_ddep_wdep", output_types="CONC DDEP WDEP", num_receptors=3)

    def test_output_types_disagreeing_with_num_receptors_raise(self):
        with pytest.raises(ValueError, match="num_receptors=4"):
            _binary("conc_ddep", output_types="CONC DDEP", num_receptors=4)

    def test_has_deposition_conflicts_are_rejected(self):
        path = FIXTURES / "conc_ddep" / "post_1h.bin"
        with pytest.raises(ValueError, match="has_deposition=True"):
            UnformattedPostfileParser(path, has_deposition=True, output_types="CONC DDEP")
        with pytest.raises(ValueError, match="has_deposition=False"):
            UnformattedPostfileParser(path, has_deposition=False, output_types="CONC DDEP")
        result = UnformattedPostfileParser(
            FIXTURES / "conc_ddep_wdep" / "post_1h.bin",
            has_deposition=True, output_types=["CONC", "DDEP", "WDEP"]).parse()
        assert result.output_types == ("CONC", "DDEP", "WDEP")

    def test_empty_file_gets_the_type_columns(self, tmp_path):
        path = tmp_path / "empty.bin"
        path.write_bytes(b"")
        result = UnformattedPostfileParser(path, output_types="DEPOS WDEP").parse()
        assert result.data.empty
        assert result.output_types == ("DEPOS", "WDEP")
        assert list(result.data.columns) == ["x", "y", "total_depo", "wet_depo", *TAIL]


# ---------------------------------------------------------------------------
# PERIOD POSTFILE (PSTANN in output.f)
# ---------------------------------------------------------------------------

class TestPeriodPostfileTypes:

    @pytest.mark.parametrize("case", list(CASES))
    def test_text_columns_follow_the_header(self, case):
        types = CASES[case]
        result = read_postfile(FIXTURES / case / "post_per.pst")
        assert result.output_types == types
        assert result.header.averaging_period == "PERIOD"
        assert list(result.data.columns) == ["x", "y", *_columns(types), *TAIL]
        assert len(result.data) == 3
        # the four hours of the run where a 1-hour file has its date
        assert (result.data["date"] == "00000004").all()
        assert (result.data["ave"] == "PERIOD").all()

    @pytest.mark.parametrize("case", list(CASES))
    def test_period_value_is_the_mean_of_the_hours(self, case):
        period = read_postfile(FIXTURES / case / "post_per.pst")
        hourly = _text(case)
        for t in CASES[case]:
            column = period.column_for(t)
            mean = hourly.data.groupby(["x", "y"], sort=False)[column].mean()
            # deposition is summed over the hours, concentration averaged
            expected = mean * 4 if t != "CONC" else mean
            np.testing.assert_allclose(period.data[column].to_numpy(), expected.to_numpy(), atol=4e-5)

    @pytest.mark.parametrize("case", list(CASES))
    def test_binary_matches_text(self, case):
        text = read_postfile(FIXTURES / case / "post_per.pst")
        binary = read_postfile(FIXTURES / case / "post_per.bin",
                               receptor_coords=RECEPTORS, output_types=_modelopt(case))
        assert binary.output_types == CASES[case]
        assert list(binary.data.columns) == list(text.data.columns)
        for t in CASES[case]:
            column = text.column_for(t)
            np.testing.assert_allclose(binary.data[column], text.data[column], atol=6e-6)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestOutputTypeNames:

    def test_modelopt_string(self):
        assert _normalize_output_types("DFAULT WDEP FLAT CONC") == ("CONC", "WDEP")
        # no output type on MODELOPT: AERMOD assumes CONC (W205)
        assert _normalize_output_types("DFAULT FLAT") == ("CONC",)
        assert _normalize_output_types(None) is None

    def test_names(self):
        assert _normalize_output_types(["wdep", "Depos"]) == ("DEPOS", "WDEP")
        with pytest.raises(ValueError, match="Unknown output type"):
            _normalize_output_types(["CONC", "DRYDEP"])
        with pytest.raises(ValueError, match="empty"):
            _normalize_output_types([])

    def test_column_for(self):
        result = _text("conc_depos_ddep_wdep")
        assert [result.column_for(t) for t in OUTPUT_TYPES] == [
            "concentration", "total_depo", "dry_depo", "wet_depo"]
        assert result.column_for("ddep") == "dry_depo"
        with pytest.raises(KeyError, match="WDEP is not in this file"):
            _text("conc_ddep").column_for("WDEP")
        with pytest.raises(ValueError, match="Unknown output type"):
            result.column_for("DRY")

    def test_column_for_without_named_types(self, tmp_path):
        # a binary file read without output_types does not know its types
        result = _binary("conc")
        assert result.column_for("CONC") == "concentration"
        with pytest.raises(KeyError, match="does not name its output types"):
            result.column_for("DDEP")

    def test_parser_class_takes_output_types(self):
        parser = PostfileParser(FIXTURES / "ddep_wdep" / "post_1h.pst", output_types="DDEP WDEP")
        assert parser.parse().output_types == ("DDEP", "WDEP")
