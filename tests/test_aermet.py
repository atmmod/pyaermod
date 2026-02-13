"""
Unit tests for PyAERMOD AERMET input generator
"""

import pytest

from pyaermod.aermet import (
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,
    AERMETStation,
    UpperAirStation,
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


class TestAERMETStage1:
    """Test AERMET Stage 1 input generation"""

    def test_basic_stage1_structure(self):
        """Test basic Stage 1 output structure"""
        stage1 = AERMETStage1()
        output = stage1.to_aermet_input()

        assert "** AERMET Stage 1 Input" in output
        assert "JOB" in output
        assert "REPORT" in output
        assert "MESSAGES" in output

    def test_stage1_with_surface_station(self):
        """Test Stage 1 with surface data"""
        station = AERMETStation(
            station_id="KORD",
            station_name="Chicago",
            latitude=41.98,
            longitude=-87.90,
            time_zone=-6,
            elevation=200.0
        )
        stage1 = AERMETStage1(
            surface_station=station,
            surface_data_file="kord_2020.ish",
            surface_format="ISHD",
            start_date="2020/01/01",
            end_date="2020/12/31",
        )
        output = stage1.to_aermet_input()

        assert "SURFACE" in output
        assert "DATA       kord_2020.ish ISHD" in output
        assert "EXTRACT" in output
        assert "XDATES     2020/01/01 TO 2020/12/31" in output
        assert "ANEMHGT    10.0" in output
        assert "LOCATION   KORD 41.9800 -87.9000 -6" in output
        assert "ELEVATION  200.0" in output

    def test_stage1_with_upper_air(self):
        """Test Stage 1 with upper air data"""
        ua = UpperAirStation("72451", "Dodge City", 37.77, -99.97)
        stage1 = AERMETStage1(
            upper_air_station=ua,
            upper_air_data_file="ua_2020.fsl",
        )
        output = stage1.to_aermet_input()

        assert "UPPERAIR" in output
        assert "DATA       ua_2020.fsl FSL" in output
        assert "_ua.ext" in output  # Upper air extract file

    def test_stage1_no_data_no_sections(self):
        """Test that SURFACE/UPPERAIR sections omitted without data"""
        stage1 = AERMETStage1()
        output = stage1.to_aermet_input()

        assert "SURFACE" not in output.split("JOB")[0]  # Not in header
        # The word SURFACE should not appear as a section header
        lines = output.strip().split("\n")
        section_lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith("**")]
        # JOB, REPORT, MESSAGES should be the only non-comment content
        assert "UPPERAIR" not in output

    def test_stage1_custom_output_files(self):
        """Test custom output file names"""
        stage1 = AERMETStage1(
            output_file="custom_s1.out",
            extract_file="custom_s1.ext",
        )
        output = stage1.to_aermet_input()
        assert "REPORT     custom_s1.out" in output

    def test_stage1_messages_level(self):
        """Test messages level setting"""
        stage1 = AERMETStage1(messages=3)
        output = stage1.to_aermet_input()
        assert "MESSAGES   3" in output


class TestAERMETStage2:
    """Test AERMET Stage 2 input generation"""

    def test_basic_stage2(self):
        """Test basic Stage 2 output"""
        stage2 = AERMETStage2()
        output = stage2.to_aermet_input()

        assert "** AERMET Stage 2 Input" in output
        assert "JOB" in output
        assert "SURFACE" in output
        assert "MERGE" in output
        assert "OUTPUT" in output

    def test_stage2_with_upper_air(self):
        """Test Stage 2 with upper air extract"""
        stage2 = AERMETStage2(
            surface_extract="s1_surface.ext",
            upper_air_extract="s1_ua.ext",
        )
        output = stage2.to_aermet_input()

        assert "UPPERAIR" in output
        assert "INPUT      s1_ua.ext" in output
        assert "INPUT      s1_surface.ext" in output

    def test_stage2_without_upper_air(self):
        """Test Stage 2 without upper air"""
        stage2 = AERMETStage2(
            surface_extract="s1_surface.ext",
        )
        output = stage2.to_aermet_input()

        assert "UPPERAIR" not in output

    def test_stage2_merge_output(self):
        """Test merge file output"""
        stage2 = AERMETStage2(merge_file="custom_merge.mrg")
        output = stage2.to_aermet_input()
        assert "OUTPUT     custom_merge.mrg" in output

    def test_stage2_date_range(self):
        """Test date range in merge section"""
        stage2 = AERMETStage2(
            start_date="2021/06/01",
            end_date="2021/08/31",
        )
        output = stage2.to_aermet_input()
        assert "XDATES     2021/06/01 TO 2021/08/31" in output


class TestAERMETStage3:
    """Test AERMET Stage 3 input generation"""

    def test_basic_stage3(self):
        """Test basic Stage 3 output"""
        stage3 = AERMETStage3()
        output = stage3.to_aermet_input()

        assert "** AERMET Stage 3 Input" in output
        assert "JOB" in output
        assert "SURFACE" in output
        assert "METPREP" in output
        assert "OUTPUT" in output
        assert "PROFILE" in output

    def test_stage3_with_station(self):
        """Test Stage 3 with station location"""
        station = AERMETStation(
            station_id="KORD",
            station_name="Chicago",
            latitude=41.98,
            longitude=-87.90,
            time_zone=-6,
        )
        stage3 = AERMETStage3(station=station)
        output = stage3.to_aermet_input()

        assert "LOCATION   KORD 41.9800 -87.9000 -6" in output

    def test_stage3_with_manual_location(self):
        """Test Stage 3 with manual lat/lon"""
        stage3 = AERMETStage3(
            latitude=33.64,
            longitude=-84.43,
            time_zone=-5,
        )
        output = stage3.to_aermet_input()
        assert "LOCATION   SITE 33.6400 -84.4300 -5" in output

    def test_stage3_surface_characteristics(self):
        """Test monthly surface characteristics"""
        stage3 = AERMETStage3(
            albedo=[0.50, 0.50, 0.40, 0.20, 0.15, 0.15, 0.15, 0.15, 0.20, 0.30, 0.40, 0.50],
            bowen=[1.50, 1.50, 1.00, 0.80, 0.70, 0.70, 0.70, 0.70, 0.80, 1.00, 1.50, 1.50],
            roughness=[0.50, 0.50, 0.50, 0.40, 0.30, 0.25, 0.25, 0.25, 0.30, 0.40, 0.50, 0.50],
        )
        output = stage3.to_aermet_input()

        assert "ALBEDO" in output
        assert "BOWEN" in output
        assert "ROUGHNESS" in output
        # Spot-check a value
        assert "0.50" in output

    def test_stage3_freq_sect(self):
        """Test frequency sector"""
        stage3 = AERMETStage3(freq_sect=[0.0, 90.0, 180.0, 270.0])
        output = stage3.to_aermet_input()
        assert "FREQ_SECT  0.0 90.0 180.0 270.0" in output

    def test_stage3_output_files(self):
        """Test output file names"""
        stage3 = AERMETStage3(
            surface_file="custom.sfc",
            profile_file="custom.pfl",
        )
        output = stage3.to_aermet_input()
        assert "OUTPUT     custom.sfc" in output
        assert "PROFILE    custom.pfl" in output

    def test_stage3_merge_input(self):
        """Test merge file input"""
        stage3 = AERMETStage3(merge_file="custom_merge.mrg")
        output = stage3.to_aermet_input()
        assert "INPUT      custom_merge.mrg" in output

    def test_stage3_date_range(self):
        """Test date range"""
        stage3 = AERMETStage3(
            start_date="2022/01/01",
            end_date="2022/12/31",
        )
        output = stage3.to_aermet_input()
        assert "XDATES     2022/01/01 TO 2022/12/31" in output

    def test_stage3_default_surface_params(self):
        """Test default surface parameter arrays"""
        stage3 = AERMETStage3()
        assert len(stage3.albedo) == 12
        assert len(stage3.bowen) == 12
        assert len(stage3.roughness) == 12
        assert all(a == 0.15 for a in stage3.albedo)
        assert all(b == 1.0 for b in stage3.bowen)
        assert all(r == 0.1 for r in stage3.roughness)


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
        """Test that time_zone=0 (UTC) generates LOCATION line"""
        stage3 = AERMETStage3(
            latitude=51.5,
            longitude=0.0,
            time_zone=0,
        )
        output = stage3.to_aermet_input()
        assert "LOCATION   SITE 51.5000 0.0000 0" in output

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

    def test_stage1_qa_pathway(self):
        """Test that QA section appears in Stage 1 output"""
        station = AERMETStation(
            station_id="KORD",
            station_name="Chicago",
            latitude=41.98,
            longitude=-87.90,
            time_zone=-6,
        )
        stage1 = AERMETStage1(
            surface_station=station,
            surface_data_file="kord_2020.ish",
        )
        output = stage1.to_aermet_input()
        assert "QA" in output
        assert "EXTRACT    stage1.qa" in output

    def test_stage1_zero_elevation(self):
        """Test that elevation=0.0 still generates ELEVATION line"""
        station = AERMETStation(
            station_id="KORD",
            station_name="Chicago",
            latitude=41.98,
            longitude=-87.90,
            time_zone=-6,
            elevation=0.0,
        )
        stage1 = AERMETStage1(
            surface_station=station,
            surface_data_file="kord_2020.ish",
        )
        output = stage1.to_aermet_input()
        assert "ELEVATION  0.0" in output
