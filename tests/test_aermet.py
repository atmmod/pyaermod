"""
Unit tests for PyAERMOD AERMET input generator
"""

import pytest

from pyaermod.aermet import (
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,
    AERMETStation,
    OnsiteData,
    ProfileFileHeader,
    SurfaceFileHeader,
    UpperAirStation,
    parse_sfc_header,
    read_profile_file,
    read_surface_file,
    write_aermet_runfile,
)


class TestAERMETStation:
    """Test AERMETStation dataclass"""

    def test_basic_station(self):
        """Test basic station creation"""
        station = AERMETStation(
            station_id="KORD",
            station_name="Chicago O'Hare",
            latitude=41.98,
            longitude=-87.90,
            time_zone=-6
        )
        assert station.station_id == "KORD"
        assert station.latitude == 41.98
        assert station.longitude == -87.90
        assert station.time_zone == -6
        assert station.anemometer_height == 10.0  # default
        assert station.elevation is None  # default

    def test_station_with_elevation(self):
        """Test station with optional parameters"""
        station = AERMETStation(
            station_id="KATL",
            station_name="Atlanta",
            latitude=33.64,
            longitude=-84.43,
            time_zone=-5,
            elevation=315.0,
            anemometer_height=6.1
        )
        assert station.elevation == 315.0
        assert station.anemometer_height == 6.1


class TestUpperAirStation:
    """Test UpperAirStation dataclass"""

    def test_basic_upper_air(self):
        """Test basic upper air station"""
        ua = UpperAirStation(
            station_id="72451",
            station_name="Dodge City",
            latitude=37.77,
            longitude=-99.97
        )
        assert ua.station_id == "72451"
        assert ua.station_name == "Dodge City"


def _chicago(**kw):
    return AERMETStation(station_id="94846", station_name="Chicago", latitude=41.98,
                         longitude=-87.90, time_zone=-6, **kw)


def _dodge_city(**kw):
    return UpperAirStation("72451", "Dodge City", 37.77, -99.97, **kw)


def _lines(deck):
    return [line.strip() for line in deck.splitlines()]


class TestAERMETStage1:
    """Stage 1 decks in the syntax of AERMET 24142 and 26135.

    tests/test_aermet_status.py pins the EX01 deck against a real AERMET
    run; these tests pin each rule the writer follows.
    """

    def test_basic_stage1_structure(self):
        output = AERMETStage1().to_aermet_input()
        assert "** AERMET Stage 1 Input" in output
        assert "JOB" in _lines(output)
        assert "REPORT     stage1.out" in output
        assert "MESSAGES   stage1.msg" in output

    def test_stage1_with_surface_station(self):
        stage1 = AERMETStage1(
            surface_station=_chicago(elevation=200.0),
            surface_data_file="kord_2020.ish", surface_format="ISHD",
            start_date="2020/01/01", end_date="2020/12/31",
        )
        lines = _lines(stage1.to_aermet_input())
        surface = lines[lines.index("SURFACE"):]
        assert surface[1:6] == [
            "DATA       kord_2020.ish ISHD",
            "EXTRACT    stage1.ext",
            "QAOUT      stage1.qa",
            "XDATES     2020/01/01 TO 2020/12/31",
            # ISHD is in GMT: adjustment 6 for UTC-6; the elevation is field 5.
            "LOCATION   94846 41.98N 87.9W 6 200",
        ]
        # AERMET rejects these keywords on SURFACE (E01) and has no QA pathway.
        for rejected in ("ANEMHGT", "ELEVATION", "QA"):
            assert rejected not in lines

    def test_stage1_with_upper_air(self):
        stage1 = AERMETStage1(
            surface_station=_chicago(),
            upper_air_station=_dodge_city(elevation=790.0),
            upper_air_data_file="ua_2020.fsl",
            upper_air_audit=["UATT", "UAWS"],
            upper_air_extra=["MODIFY"],
        )
        lines = _lines(stage1.to_aermet_input())
        ua = lines[lines.index("UPPERAIR"):]
        assert ua[1:8] == [
            "DATA       ua_2020.fsl FSL",
            "EXTRACT    stage1_ua.ext",
            "QAOUT      stage1_ua.qa",
            "XDATES     2020/01/01 TO 2020/12/31",
            # Upper air is in GMT; the zone falls back to the surface station's.
            "LOCATION   72451 37.77N 99.97W 6 790",
            "AUDIT      UATT UAWS",
            "MODIFY",
        ]

    @pytest.mark.parametrize("fmt", ["IGRA", "6201FB", "6201VB", "fsl"])
    def test_upper_air_formats(self, fmt):
        stage1 = AERMETStage1(
            upper_air_station=_dodge_city(elevation=790.0, time_zone=-6),
            upper_air_data_file="ua.dat", upper_air_format=fmt,
        )
        assert f"DATA       ua.dat {fmt.upper()}" in stage1.to_aermet_input()

    def test_upper_air_needs_an_elevation(self):
        stage1 = AERMETStage1(upper_air_station=_dodge_city(time_zone=-6),
                              upper_air_data_file="ua.fsl")
        with pytest.raises(ValueError, match="E05"):
            stage1.to_aermet_input()

    def test_upper_air_needs_a_time_zone(self):
        stage1 = AERMETStage1(upper_air_station=_dodge_city(elevation=790.0),
                              upper_air_data_file="ua.fsl")
        with pytest.raises(ValueError, match="time_zone"):
            stage1.to_aermet_input()
        stage1.upper_air_time_adjustment = 5
        assert "LOCATION   72451 37.77N 99.97W 5 790" in stage1.to_aermet_input()

    def test_unknown_formats_are_rejected(self):
        with pytest.raises(ValueError, match="Upper-air format 'TD6201'"):
            AERMETStage1(upper_air_station=_dodge_city(elevation=1.0, time_zone=0),
                         upper_air_data_file="u", upper_air_format="TD6201").to_aermet_input()
        with pytest.raises(ValueError, match="Surface format '3280VB'"):
            AERMETStage1(surface_station=_chicago(), surface_data_file="s",
                         surface_format="3280VB").to_aermet_input()

    @pytest.mark.parametrize(("fmt", "adjustment"), [
        ("ISHD", "6"), ("CD144", "0"), ("CD144FB", "0"), ("SAMSON", "0"), ("HUSWO", "0"),
    ])
    def test_surface_time_adjustment_follows_the_format(self, fmt, adjustment):
        stage1 = AERMETStage1(surface_station=_chicago(), surface_data_file="s.dat",
                              surface_format=fmt)
        assert f"LOCATION   94846 41.98N 87.9W {adjustment}\n" in stage1.to_aermet_input()

    @pytest.mark.parametrize("fmt", ["SCRAM", "GHCN"])
    def test_surface_time_adjustment_is_asked_for_when_unknown(self, fmt):
        stage1 = AERMETStage1(surface_station=_chicago(), surface_data_file="s.dat",
                              surface_format=fmt)
        with pytest.raises(ValueError, match="surface_time_adjustment"):
            stage1.to_aermet_input()
        stage1.surface_time_adjustment = 0
        assert "LOCATION   94846 41.98N 87.9W 0" in stage1.to_aermet_input()

    def test_stage1_no_data_no_sections(self):
        lines = _lines(AERMETStage1().to_aermet_input())
        assert "UPPERAIR" not in lines
        assert "SURFACE" not in lines
        assert "ONSITE" not in lines

    def test_stage1_custom_output_files(self):
        stage1 = AERMETStage1(
            surface_station=_chicago(), surface_data_file="my data.ish",
            output_file="custom_s1.out", extract_file="custom_s1.ext",
            qa_file="custom_s1.qa", message_file="custom_s1.msg",
        )
        output = stage1.to_aermet_input()
        assert "REPORT     custom_s1.out" in output
        assert "MESSAGES   custom_s1.msg" in output
        assert "EXTRACT    custom_s1.ext" in output
        assert "QAOUT      custom_s1.qa" in output
        # A file name with a blank is quoted.
        assert 'DATA       "my data.ish" ISHD' in output
        assert stage1.upper_air_extract == "custom_s1_ua.ext"
        assert stage1.upper_air_qaout == "custom_s1_ua.qa"

    def test_messages_level_is_ignored_with_a_warning(self):
        """MESSAGES names a file; the old level 3 would open a file named 3."""
        with pytest.warns(DeprecationWarning, match="MESSAGES keyword names a file"):
            output = AERMETStage1(messages=3).to_aermet_input()
        assert "MESSAGES   stage1.msg" in output
        assert "MESSAGES   s.msg" in AERMETStage1(messages="s.msg").to_aermet_input()

    def test_station_id_must_be_one_word(self):
        stage1 = AERMETStage1(
            surface_station=AERMETStation("KO RD", "x", 41.98, -87.9, -6),
            surface_data_file="s.ish",
        )
        with pytest.raises(ValueError, match="one word"):
            stage1.to_aermet_input()

    @pytest.mark.parametrize("sid", ["KATL", "K13874", "13874A", "-13874"])
    def test_surface_station_id_must_be_a_number(self, sid):
        """METPREP reads the SURFACE ID back with read(sfid,*)iwban (read_ext in
        mod_surface.f90) and crashes on KATL, after Stage 1 accepted it."""
        stage1 = AERMETStage1(
            surface_station=AERMETStation(sid, "Atlanta", 33.63, -84.44, -5),
            surface_data_file="s.ish",
        )
        with pytest.raises(ValueError, match="WBAN"):
            stage1.to_aermet_input()

    def test_surface_station_id_may_have_leading_zeros(self):
        stage1 = AERMETStage1(
            surface_station=AERMETStation("00013874", "Atlanta", 33.63, -84.44, -5),
            surface_data_file="s.ish",
        )
        assert "LOCATION   00013874 33.63N 84.44W 5" in stage1.to_aermet_input()

    def test_upper_air_and_metprep_ids_need_not_be_numbers(self):
        """Only the SURFACE ID is read back as an integer."""
        stage1 = AERMETStage1(
            upper_air_station=UpperAirStation("FFC", "Peachtree City", 33.36, -84.57,
                                              elevation=245.0, time_zone=-5),
            upper_air_data_file="ua.fsl",
        )
        assert "LOCATION   FFC 33.36N 84.57W 5 245" in stage1.to_aermet_input()
        stage3 = AERMETStage3(station=AERMETStation("KATL", "Atlanta", 33.63, -84.44, -5))
        assert "LOCATION   KATL 33.63N 84.44W 5" in stage3.to_aermet_input()

    def test_station_ids_longer_than_eight_characters_raise(self):
        """getloc keeps a station ID in character(len=8)."""
        long_surface = AERMETStage1(
            surface_station=AERMETStation("123456789", "x", 33.63, -84.44, -5),
            surface_data_file="s.ish",
        )
        with pytest.raises(ValueError, match="8 characters"):
            long_surface.to_aermet_input()
        long_upper_air = AERMETStage1(
            upper_air_station=UpperAirStation("PEACHTREE", "x", 33.36, -84.57,
                                              elevation=245.0, time_zone=-5),
            upper_air_data_file="ua.fsl",
        )
        with pytest.raises(ValueError, match="8 characters"):
            long_upper_air.to_aermet_input()
        assert "LOCATION   12345678 " in AERMETStage1(
            surface_station=AERMETStation("12345678", "x", 33.63, -84.44, -5),
            surface_data_file="s.ish",
        ).to_aermet_input()

    def test_southern_and_eastern_coordinates(self):
        stage1 = AERMETStage1(
            surface_station=AERMETStation("947670", "Sydney", -33.95, 151.18, 10),
            surface_data_file="s.ish",
        )
        assert "LOCATION   947670 33.95S 151.18E -10" in stage1.to_aermet_input()

    def test_onsite_pathway(self):
        onsite = OnsiteData(
            "CORDERO", 44.2, -105.5, "imldata3.met",
            read_records=[["OSYR", "OSMO", "OSDY", "OSHR", "WS01"], ["TT01"]],
            format_records=["(4i2,f6.2)", "(f6.1)"],
            threshold=0.5, heights=[10.0, 60.0], delta_temp=[(1, 2.0, 10.0)],
            obs_per_hour=4, audit=["WS01"], elevation=1500.0,
            extra_keywords=["RANGE TT01 -30 < 40 -99"],
        )
        stage1 = AERMETStage1(onsite=onsite, start_date="1993/5/19", end_date="1993/7/18")
        lines = _lines(stage1.to_aermet_input())
        assert lines[lines.index("ONSITE"):][1:] == [
            "DATA       imldata3.met",
            "QAOUT      stage1_os.qa",
            "XDATES     1993/5/19 TO 1993/7/18",
            "LOCATION   CORDERO 44.2N 105.5W 0 1500",
            "READ 1     OSYR OSMO OSDY OSHR WS01",
            "FORMAT 1   (4i2,f6.2)",
            "READ 2     TT01",
            "FORMAT 2   (f6.1)",
            "THRESHOLD  0.5",
            "OSHEIGHTS  10 60",
            "DELTA_TEMP 1 2 10",
            "OBS/HOUR   4",
            "AUDIT      WS01",
            "RANGE TT01 -30 < 40 -99",
        ]

    def test_onsite_validation(self):
        with pytest.raises(ValueError, match="pair up"):
            OnsiteData("OS", 0, 0, "f", read_records=[["OSYR"]], format_records=[])
        with pytest.raises(ValueError, match="at least one"):
            OnsiteData("OS", 0, 0, "f", read_records=[], format_records=[])
        with pytest.raises(ValueError, match="latitude"):
            OnsiteData("OS", 95, 0, "f", read_records=[["A"]], format_records=["(a)"])
        with pytest.raises(ValueError, match="longitude"):
            OnsiteData("OS", 0, 195, "f", read_records=[["A"]], format_records=["(a)"])

    def test_location_elevation_needs_the_adjustment(self):
        from pyaermod.aermet import _location

        with pytest.raises(ValueError, match="after the time adjustment"):
            _location("ID", 1.0, 1.0, None, 10.0)
        assert _location("ID", 1.0, -1.0) == "ID 1N 1W"


class TestAERMETStage2:
    """The merge stage does not exist in AERMET 11 and later."""

    def test_stage2_is_deprecated(self):
        with pytest.warns(DeprecationWarning, match="no merge stage"):
            stage2 = AERMETStage2(surface_extract="s1_surface.ext", merge_file="m.mrg")
        # Its fields stay so old code keeps constructing it.
        assert stage2.surface_extract == "s1_surface.ext"
        assert stage2.merge_file == "m.mrg"

    def test_stage2_writes_no_deck(self):
        with pytest.warns(DeprecationWarning):
            stage2 = AERMETStage2()
        with pytest.raises(NotImplementedError, match="AERMETStage3"):
            stage2.to_aermet_input()


class TestAERMETStage3:
    """METPREP (AERMET's stage 2) decks."""

    def test_basic_stage3(self):
        lines = _lines(AERMETStage3(nws_height=10).to_aermet_input())
        assert lines[:3] == ["** AERMET Stage 3 Input (AERMET stage 2, METPREP)",
                             "** Job: STAGE3", "**"]
        # With no input names it reads Stage 1's default QAOUT files.
        assert lines[lines.index("UPPERAIR") + 1] == "QAOUT      stage1_ua.qa"
        assert lines[lines.index("SURFACE") + 1] == "QAOUT      stage1.qa"
        metprep = lines[lines.index("METPREP"):]
        assert metprep[1:] == [
            "XDATES     2020/01/01 TO 2020/12/31",
            "METHOD     REFLEVEL SUBNWS",
            "NWS_HGT    WIND 10",
            "OUTPUT     aermod.sfc",
            "PROFILE    aermod.pfl",
            "FREQ_SECT  ANNUAL 1",
            "SECTOR     1 0 360",
            "SITE_CHAR  1 1 0.15 1 0.1",
        ]
        # METPREP's DATA keyword is obsolete, and AERMET has no ALBEDO,
        # BOWEN or ROUGHNESS keywords.
        for rejected in ("DATA", "ALBEDO", "BOWEN", "ROUGHNESS"):
            assert not any(line.startswith(rejected) for line in metprep)

    def test_nws_only_deck_gets_subnws(self):
        """AERMET 26135 stops with E87 on NWS-only data without METHOD REFLEVEL SUBNWS."""
        lines = _lines(AERMETStage3(station=_chicago()).to_aermet_input())
        assert lines.count("METHOD     REFLEVEL SUBNWS") == 1
        assert "NWS_HGT    WIND 10" in lines

    def test_subnws_given_is_not_repeated(self):
        stage3 = AERMETStage3(station=_chicago(),
                              methods=[("WIND_DIR", "RANDOM"), ("reflevel", "subnws")])
        methods = [line for line in _lines(stage3.to_aermet_input()) if line.startswith("METHOD")]
        assert methods == ["METHOD     WIND_DIR RANDOM", "METHOD     REFLEVEL SUBNWS"]

    def test_onsite_deck_gets_no_default_subnws(self):
        stage3 = AERMETStage3(surface_qaout="sf.qa", onsite_qaout="os.qa")
        assert "SUBNWS" not in stage3.to_aermet_input()
        stage3 = AERMETStage3(upper_air_qaout="ua.qa", onsite_qaout="os.qa")
        assert "SUBNWS" not in stage3.to_aermet_input()

    def test_subnws_needs_the_nws_height(self):
        """SUBNWS without NWS_HGT is AERMET error E72."""
        with pytest.raises(ValueError, match="E72"):
            AERMETStage3().to_aermet_input()
        with pytest.raises(ValueError, match="E72"):
            AERMETStage3(surface_qaout="sf.qa", onsite_qaout="os.qa",
                         methods=[("REFLEVEL", "SUBNWS")]).to_aermet_input()

    def test_stage3_with_station(self):
        stage3 = AERMETStage3(station=_chicago(anemometer_height=6.1))
        output = stage3.to_aermet_input()
        assert "LOCATION   94846 41.98N 87.9W 6" in output
        assert "NWS_HGT    WIND 6.1" in output

    def test_stage3_with_manual_location(self):
        stage3 = AERMETStage3(latitude=33.64, longitude=-84.43, time_zone=-5, nws_height=10)
        output = stage3.to_aermet_input()
        assert "LOCATION   SITE 33.64N 84.43W 5" in output
        assert "NWS_HGT    WIND 10" in output

    def test_monthly_lists_become_monthly_site_char(self):
        stage3 = AERMETStage3(
            nws_height=10,
            albedo=[0.50, 0.50, 0.40, 0.20, 0.15, 0.15, 0.15, 0.15, 0.20, 0.30, 0.40, 0.50],
            bowen=[1.50, 1.50, 1.00, 0.80, 0.70, 0.70, 0.70, 0.70, 0.80, 1.00, 1.50, 1.50],
            roughness=[0.50, 0.50, 0.50, 0.40, 0.30, 0.25, 0.25, 0.25, 0.30, 0.40, 0.50, 0.50],
        )
        lines = _lines(stage3.to_aermet_input())
        assert "FREQ_SECT  MONTHLY 1" in lines
        site = [line for line in lines if line.startswith("SITE_CHAR")]
        assert len(site) == 12
        assert site[0] == "SITE_CHAR  1 1 0.5 1.5 0.5"
        assert site[4] == "SITE_CHAR  5 1 0.15 0.7 0.3"

    def test_site_char_records_and_sectors(self):
        stage3 = AERMETStage3(
            nws_height=10,
            frequency="seasonal", num_sectors=2, sectors=[(0, 180), (180, 360)],
            site_char=[(s, k, 0.15, 2.0, 0.1 * k) for s in range(1, 5) for k in (1, 2)]
            + ["4 2 0.2 1.0 0.25"],
        )
        lines = _lines(stage3.to_aermet_input())
        assert "FREQ_SECT  SEASONAL 2" in lines
        assert "SECTOR     1 0 180" in lines
        assert "SECTOR     2 180 360" in lines
        assert "SITE_CHAR  1 2 0.15 2 0.2" in lines
        assert lines[lines.index("SITE_CHAR  4 2 0.15 2 0.2") + 1] == "SITE_CHAR  4 2 0.2 1.0 0.25"

    def test_sector_count_must_match(self):
        stage3 = AERMETStage3(nws_height=10, num_sectors=2, site_char=[(1, 1, 0.1, 1, 0.1)])
        with pytest.raises(ValueError, match="num_sectors=2 needs 2"):
            stage3.to_aermet_input()

    def test_monthly_lists_describe_one_sector(self):
        with pytest.raises(ValueError, match="one 0-360 sector"):
            AERMETStage3(nws_height=10, num_sectors=4).to_aermet_input()

    def test_frequency_is_validated(self):
        with pytest.raises(ValueError, match="frequency must be one of"):
            AERMETStage3(frequency="WEEKLY")
        with pytest.raises(ValueError, match="secondary_frequency"):
            AERMETStage3(secondary_frequency="DAILY")

    def test_aersurf_and_secondary_site(self):
        stage3 = AERMETStage3(
            nws_height=10,
            aersurf_file="aersurface.out", secondary_aersurf_file="nws.out",
            asos_1min_file="aerminute.dat", surface_qaout="sf.qa", onsite_qaout="os.qa",
            methods=[("reflevel", "subnws")], extra_lines=["UAWINDOW -1 1"],
        )
        lines = _lines(stage3.to_aermet_input())
        assert "UPPERAIR" not in lines
        assert lines[lines.index("SURFACE"):][1:3] == [
            "QAOUT      sf.qa", "ASOS1MIN   aerminute.dat"]
        assert lines[lines.index("ONSITE") + 1] == "QAOUT      os.qa"
        assert "AERSURF    aersurface.out" in lines
        assert "AERSURF2   nws.out" in lines
        assert "METHOD     REFLEVEL SUBNWS" in lines
        assert lines[-1] == "UAWINDOW -1 1"
        assert not any(line.startswith("SITE_CHAR") for line in lines)

    def test_secondary_site_char(self):
        stage3 = AERMETStage3(nws_height=10, site_char=[(1, 1, 0.2, 3.0, 0.1)],
                              secondary_site_char=[(1, 1, 0.2, 3.0, 0.1)])
        lines = _lines(stage3.to_aermet_input())
        assert lines[-3:] == ["FREQ_SECT2 ANNUAL 1", "SECTOR2    1 0 360",
                              "SITE_CHAR2 1 1 0.2 3 0.1"]

    def test_stage3_output_files(self):
        stage3 = AERMETStage3(nws_height=10, surface_file="custom.sfc", profile_file="custom.pfl",
                              message_file="m.msg")
        output = stage3.to_aermet_input()
        assert "OUTPUT     custom.sfc" in output
        assert "PROFILE    custom.pfl" in output
        assert "MESSAGES   m.msg" in output

    def test_merge_file_is_ignored(self):
        """METPREP's DATA keyword is obsolete: AERMET merges the QAOUT files itself."""
        output = AERMETStage3(nws_height=10, merge_file="custom_merge.mrg").to_aermet_input()
        assert "custom_merge.mrg" not in output

    def test_messages_level_is_ignored_with_a_warning(self):
        with pytest.warns(DeprecationWarning, match="AERMETStage3.messages=2"):
            output = AERMETStage3(nws_height=10, messages=2).to_aermet_input()
        assert "MESSAGES   stage3.msg" in output

    def test_stage3_date_range(self):
        stage3 = AERMETStage3(nws_height=10, start_date="2022/01/01", end_date="2022/12/31")
        assert "XDATES     2022/01/01 TO 2022/12/31" in stage3.to_aermet_input()

    def test_stage3_default_surface_params(self):
        stage3 = AERMETStage3()
        assert stage3.albedo == [0.15] * 12
        assert stage3.bowen == [1.0] * 12
        assert stage3.roughness == [0.1] * 12

    def test_with_inputs_from_names_only_the_pathways_stage1_runs(self):
        stage1 = AERMETStage1(surface_station=_chicago(), surface_data_file="s.ish",
                              qa_file="sf.qa")
        stage3 = AERMETStage3(nws_height=10).with_inputs_from(stage1)
        assert (stage3.upper_air_qaout, stage3.surface_qaout, stage3.onsite_qaout) == (
            None, "sf.qa", None)
        lines = _lines(stage3.to_aermet_input())
        assert "UPPERAIR" not in lines
        assert lines[lines.index("SURFACE") + 1] == "QAOUT      sf.qa"

    def test_with_inputs_from_keeps_names_given(self):
        stage3 = AERMETStage3(surface_qaout="mine.qa")
        assert stage3.with_inputs_from(AERMETStage1()) is stage3


class TestWriteAERMETRunfile:
    """Test write_aermet_runfile function"""

    def test_creates_file(self, tmp_path):
        """Test that write_aermet_runfile creates a file"""
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = write_aermet_runfile(1, "stage1.inp")
            assert os.path.exists(result)
        finally:
            os.chdir(original_cwd)

    def test_content_includes_stage_number(self, tmp_path):
        """Test that the script content includes the correct stage number"""
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            write_aermet_runfile(2, "stage2.inp")
            with open("run_aermet_stage2.sh") as f:
                content = f.read()
            assert "Stage 2" in content
        finally:
            os.chdir(original_cwd)

    def test_script_passes_the_runstream_and_checks_the_banner(self, tmp_path, monkeypatch):
        """AERMET reads the runstream named as its argument, not stdin, and exits 0 on failure."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "stage1.inp").write_text("JOB\n")
        content = (tmp_path / write_aermet_runfile(1, "stage1.inp", "out")).read_text()
        assert f'INPUT_FILE="{(tmp_path / "stage1.inp").resolve()}"' in content
        assert '"$AERMET_EXE" "$INPUT_FILE"' in content
        assert "< " not in content
        assert 'grep -q "AERMET FINISHED SUCCESSFULLY"' in content

    def test_file_is_executable(self, tmp_path):
        """Test that the created script file is executable"""
        import os
        import stat
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = write_aermet_runfile(3, "stage3.inp")
            file_stat = os.stat(result)
            assert file_stat.st_mode & stat.S_IXUSR
        finally:
            os.chdir(original_cwd)


class TestAERMETEdgeCases:
    """Test edge cases and validation"""

    def test_station_invalid_latitude(self):
        """Test that invalid latitude raises ValueError"""
        with pytest.raises(ValueError, match="latitude"):
            AERMETStation(
                station_id="TEST",
                station_name="Test",
                latitude=91.0,
                longitude=0.0,
                time_zone=0,
            )

    def test_station_invalid_longitude(self):
        """Test that invalid longitude raises ValueError"""
        with pytest.raises(ValueError, match="longitude"):
            AERMETStation(
                station_id="TEST",
                station_name="Test",
                latitude=0.0,
                longitude=181.0,
                time_zone=0,
            )

    def test_station_zero_anemometer_height(self):
        """Test that zero anemometer height raises ValueError"""
        with pytest.raises(ValueError, match="anemometer_height"):
            AERMETStation(
                station_id="TEST",
                station_name="Test",
                latitude=0.0,
                longitude=0.0,
                time_zone=0,
                anemometer_height=0.0,
            )

    def test_upper_air_invalid_latitude(self):
        """Test that invalid upper air latitude raises ValueError"""
        with pytest.raises(ValueError, match="latitude"):
            UpperAirStation(
                station_id="99999",
                station_name="Bad",
                latitude=-91.0,
                longitude=0.0,
            )

    def test_stage3_falsy_time_zone(self):
        """time_zone=0 (UTC) still writes the LOCATION line, with adjustment 0."""
        stage3 = AERMETStage3(nws_height=10, latitude=51.5, longitude=0.0, time_zone=0)
        assert "LOCATION   SITE 51.5N 0E 0" in stage3.to_aermet_input()

    def test_stage3_partial_location(self):
        """Test that partial location parameters raise ValueError"""
        with pytest.raises(ValueError, match="latitude, longitude, and time_zone"):
            AERMETStage3(
                latitude=33.64,
            )

    def test_stage3_invalid_albedo_length(self):
        """Test that non-12-element albedo raises ValueError"""
        with pytest.raises(ValueError, match="albedo"):
            AERMETStage3(albedo=[0.15, 0.15, 0.15])

    def test_stage3_invalid_bowen_length(self):
        """Test that non-12-element bowen raises ValueError"""
        with pytest.raises(ValueError, match="bowen"):
            AERMETStage3(bowen=[1.0] * 6)

    def test_stage3_invalid_roughness_length(self):
        """Test that non-12-element roughness raises ValueError"""
        with pytest.raises(ValueError, match="roughness"):
            AERMETStage3(roughness=[0.1])

    def test_stage1_zero_elevation(self):
        """elevation=0.0 (sea level) is still written, as LOCATION's fifth field."""
        stage1 = AERMETStage1(surface_station=_chicago(elevation=0.0),
                              surface_data_file="kord_2020.ish")
        assert "LOCATION   94846 41.98N 87.9W 6 0" in stage1.to_aermet_input()


# ============================================================================
# UpperAirStation validation
# ============================================================================


class TestUpperAirStationValidation:
    """Test UpperAirStation __post_init__ validation."""

    def test_upper_air_invalid_longitude(self):
        """UpperAirStation rejects longitude outside -180..180."""
        with pytest.raises(ValueError, match="longitude"):
            UpperAirStation(
                station_id="99999",
                station_name="Bad",
                latitude=40.0,
                longitude=200.0,
            )


# ============================================================================
# parse_sfc_header() tests
# ============================================================================


class TestParseSfcHeader:
    """Test parsing of .SFC file header lines."""

    def test_full_header_all_fields(self):
        """Full header with all standard fields is parsed correctly."""
        hdr_line = (
            "  42.750N   73.800W  UA_ID: 72518  SF_ID: 14735"
            "  OS_ID: 99999  VERSION: 21DRF  ADJ-U*"
        )
        hdr = parse_sfc_header(hdr_line)
        assert hdr.latitude == pytest.approx(42.75)
        assert hdr.longitude == pytest.approx(-73.8)
        assert hdr.ua_id == "72518"
        assert hdr.sf_id == "14735"
        assert hdr.os_id == "99999"
        assert hdr.version == "21DRF"
        assert "ADJ-U*" in hdr.options

    def test_southern_hemisphere_latitude(self):
        """Southern hemisphere latitude is negative."""
        hdr = parse_sfc_header("  33.500S  151.200E  UA_ID: 94767  SF_ID: 94767  OS_ID: 99999  VERSION: 21DRF")
        assert hdr.latitude == pytest.approx(-33.5)

    def test_eastern_longitude(self):
        """Eastern longitude is positive."""
        hdr = parse_sfc_header("  35.680N  139.770E  UA_ID: 47662  SF_ID: 47662  OS_ID: 99999  VERSION: 21DRF")
        assert hdr.longitude == pytest.approx(139.77)

    def test_partial_header_lat_lon_only(self):
        """Header with only lat/lon — IDs and version stay as defaults."""
        hdr = parse_sfc_header("  41.300N   72.100W")
        assert hdr.latitude == pytest.approx(41.3)
        assert hdr.longitude == pytest.approx(-72.1)
        assert hdr.ua_id == ""
        assert hdr.sf_id == ""
        assert hdr.version == ""

    def test_empty_header(self):
        """Empty string produces all defaults."""
        hdr = parse_sfc_header("")
        assert hdr.latitude == 0.0
        assert hdr.longitude == 0.0
        assert hdr.ua_id == ""
        assert hdr.version == ""


# ============================================================================
# read_surface_file() tests
# ============================================================================


class TestReadSurfaceFile:
    """Test reading of AERMET .SFC surface meteorology files."""

    def _write_sfc(self, tmp_path, header, data_lines):
        """Helper: write header + data lines to a .sfc file."""
        sfc = tmp_path / "test.sfc"
        content = header + "\n" + "\n".join(data_lines) + "\n"
        sfc.write_text(content)
        return sfc

    def test_basic_20_column_sfc(self, tmp_path):
        """Parse a standard 20-column .SFC file."""
        header = "  42.750N   73.800W  UA_ID: 72518  SF_ID: 14735  OS_ID: 99999  VERSION: 21DRF"
        # year month day jday hour H ustar wstar VPTG Zic Zim L z0 BOWEN ALBEDO ws wd zrw temp zrt
        row1 = "2020  1  1   1  1  -28.3  0.234  -9.000  0.005  -999.  121.  -28.4  0.300  1.00  0.20  3.10  280.  10.0  268.2  2.0"
        row2 = "2020  1  1   1  2  -15.1  0.310  -9.000  0.005  -999.  150.  -40.0  0.300  1.00  0.20  4.50  290.  10.0  267.8  2.0"
        sfc = self._write_sfc(tmp_path, header, [row1, row2])

        result = read_surface_file(sfc)
        assert result["header"].latitude == pytest.approx(42.75)
        assert result["header"].ua_id == "72518"

        df = result["data"]
        assert len(df) == 2
        assert df.iloc[0]["year"] == 2020
        assert df.iloc[0]["wind_speed"] == pytest.approx(3.1)
        assert df.iloc[1]["wind_dir"] == pytest.approx(290.0)

    def test_sfc_with_optional_columns(self, tmp_path):
        """Parse a 27-column .SFC file with optional trailing columns."""
        header = "  42.750N   73.800W  UA_ID: 72518  SF_ID: 14735  OS_ID: 99999  VERSION: 21DRF"
        # 20 standard cols + ipcode pamt rh pres ccvr method subs
        row = (
            "2020  1  1   1  1  -28.3  0.234  -9.000  0.005  -999.  121.  -28.4"
            "  0.300  1.00  0.20  3.10  280.  10.0  268.2  2.0"
            "  0  0.00  55.0  1013.0  8  NAD  SUB"
        )
        sfc = self._write_sfc(tmp_path, header, [row])

        result = read_surface_file(sfc)
        df = result["data"]
        assert len(df) == 1
        assert df.iloc[0]["ipcode"] == 0
        assert df.iloc[0]["rh"] == pytest.approx(55.0)
        assert df.iloc[0]["pres"] == pytest.approx(1013.0)
        assert df.iloc[0]["ccvr"] == 8
        assert df.iloc[0]["method"] == "NAD"
        assert df.iloc[0]["subs"] == "SUB"

    def test_sfc_malformed_line_skipped(self, tmp_path):
        """Malformed lines (short or non-numeric) are silently skipped."""
        header = "  42.750N   73.800W  UA_ID: 72518  SF_ID: 14735  OS_ID: 99999  VERSION: 21DRF"
        good = "2020  1  1   1  1  -28.3  0.234  -9.000  0.005  -999.  121.  -28.4  0.300  1.00  0.20  3.10  280.  10.0  268.2  2.0"
        short = "2020  1  1   1  2"  # < 20 columns → skipped
        bad = "2020  1  1   1  3  BADVAL  0.234  -9.000  X  -999.  121.  -28.4  0.300  1.00  0.20  3.10  280.  10.0  268.2  2.0"
        sfc = self._write_sfc(tmp_path, header, [good, short, bad])

        result = read_surface_file(sfc)
        df = result["data"]
        assert len(df) == 1  # only the good row survived

    def test_sfc_empty_data(self, tmp_path):
        """Header only, no data lines → empty DataFrame."""
        header = "  42.750N   73.800W  UA_ID: 72518  SF_ID: 14735  OS_ID: 99999  VERSION: 21DRF"
        sfc = self._write_sfc(tmp_path, header, [])

        result = read_surface_file(sfc)
        assert len(result["data"]) == 0
        assert result["header"].latitude == pytest.approx(42.75)


# ============================================================================
# read_profile_file() tests
# ============================================================================


class TestReadProfileFile:
    """Test reading of AERMET .PFL profile files."""

    def _write_pfl(self, tmp_path, data_lines):
        """Helper: write data lines to a .pfl file (no header line)."""
        pfl = tmp_path / "test.pfl"
        pfl.write_text("\n".join(data_lines) + "\n")
        return pfl

    def test_basic_9_column_pfl(self, tmp_path):
        """Parse a standard 9-column .PFL file."""
        # year month day hour height top_flag wind_dir wind_speed temp_diff
        row1 = "2020  1  1  1   10.0  0  280.0  3.10  268.2"
        row2 = "2020  1  1  1   50.0  1  285.0  4.20  267.5"
        row3 = "2020  1  1  2   10.0  0  290.0  4.50  267.8"
        pfl = self._write_pfl(tmp_path, [row1, row2, row3])

        result = read_profile_file(pfl)
        df = result["data"]
        assert len(df) == 3
        assert df.iloc[0]["height"] == pytest.approx(10.0)
        assert df.iloc[1]["wind_speed"] == pytest.approx(4.2)
        assert df.iloc[2]["wind_dir"] == pytest.approx(290.0)

        hdr = result["header"]
        assert hdr.num_hours == 2  # 2 distinct (year,month,day,hour) groups
        assert hdr.num_levels == 2  # heights: 10.0, 50.0
        assert sorted(hdr.heights) == [10.0, 50.0]

    def test_pfl_with_optional_columns(self, tmp_path):
        """Parse an 11-column .PFL file with sigma_theta and sigma_w."""
        row = "2020  1  1  1   10.0  0  280.0  3.10  268.2  15.3  0.45"
        pfl = self._write_pfl(tmp_path, [row])

        result = read_profile_file(pfl)
        df = result["data"]
        assert len(df) == 1
        assert df.iloc[0]["sigma_theta"] == pytest.approx(15.3)
        assert df.iloc[0]["sigma_w"] == pytest.approx(0.45)

    def test_pfl_empty_file(self, tmp_path):
        """Empty .PFL file → empty DataFrame, header defaults."""
        pfl = tmp_path / "empty.pfl"
        pfl.write_text("")

        result = read_profile_file(pfl)
        assert len(result["data"]) == 0
        assert result["header"].num_hours == 0
        assert result["header"].num_levels == 0
        assert result["header"].heights == []
