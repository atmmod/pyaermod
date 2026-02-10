"""
Integration tests for PyAERMOD

Tests the full workflow from input generation through execution to output parsing.
Tests are marked with pytest.mark.integration and can be run separately.

Some tests require AERMOD executables (aermod, aermet, aermap) to be available
in the system PATH. These tests are automatically skipped if executables are not found.
"""

import pytest
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

# Import all components
from pyaermod_input_generator import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    PointSource,
    AreaSource,
    VolumeSource,
    ReceptorPathway,
    CartesianGrid,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
)
from pyaermod_runner import AERMODRunner
from pyaermod_output_parser import AERMODOutputParser, parse_aermod_output
from pyaermod_aermet import (
    AERMETStation,
    UpperAirStation,
    AERMETStage1,
    AERMETStage2,
    AERMETStage3,
)
from pyaermod_validator import Validator

# Try to import geospatial and postfile modules
try:
    from pyaermod_postfile import read_postfile, PostfileResult
    HAS_POSTFILE = True
except ImportError:
    HAS_POSTFILE = False

try:
    from pyaermod_geospatial import (
        CoordinateTransformer,
        export_concentration_geotiff,
        export_concentration_shapefile,
    )
    HAS_GEOSPATIAL = True
except ImportError:
    HAS_GEOSPATIAL = False


# Utility functions
def find_executable(name):
    """Find executable in PATH or local directories, return None if not found"""
    # First check PATH
    exe = shutil.which(name)
    if exe:
        return exe

    # Check local directories relative to this test file
    test_dir = Path(__file__).parent.parent
    local_paths = {
        'aermod': test_dir / 'aermod' / 'aermod',
        'aermet': test_dir / 'aermet' / 'aermet_source_code_24142' / 'aermet',
    }

    if name in local_paths and local_paths[name].exists():
        return str(local_paths[name])

    return None


def find_aermap():
    """Find AERMAP executable in PATH or local directories."""
    exe = shutil.which("aermap")
    if exe:
        return exe
    test_dir = Path(__file__).parent.parent
    local = test_dir / "aermap" / "aermap_source_code_24142" / "aermap"
    if local.exists():
        return str(local)
    return None

AERMOD_EXE = find_executable("aermod")
AERMET_EXE = find_executable("aermet")
AERMAP_EXE = find_aermap()

# Skip markers
requires_aermod = pytest.mark.skipif(
    AERMOD_EXE is None,
    reason="aermod executable not found in PATH"
)
requires_aermet = pytest.mark.skipif(
    AERMET_EXE is None,
    reason="aermet executable not found in PATH"
)
requires_aermap = pytest.mark.skipif(
    AERMAP_EXE is None,
    reason="aermap executable not found in PATH"
)
requires_postfile = pytest.mark.skipif(
    not HAS_POSTFILE,
    reason="postfile module not available"
)
requires_geospatial = pytest.mark.skipif(
    not HAS_GEOSPATIAL,
    reason="geospatial module not available"
)


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for tests"""
    workspace = tmp_path / "aermod_test"
    workspace.mkdir()
    return workspace


@pytest.fixture
def simple_project():
    """Create a simple AERMOD project for testing"""
    control = ControlPathway(
        title_one="Integration Test - Simple Project",
        title_two="Simple single source test case",
        averaging_periods=["1"],
        pollutant_id="SO2",
        terrain_type="FLAT",
        calculate_concentration=True,
    )

    # Single point source
    source = PointSource(
        source_id="STACK1",
        x_coord=0.0,
        y_coord=0.0,
        base_elevation=0.0,
        stack_height=50.0,
        stack_temp=400.0,
        exit_velocity=15.0,
        stack_diameter=2.0,
        emission_rate=10.0,
    )
    sources = SourcePathway()
    sources.add_source(source)

    # Small receptor grid
    grid = CartesianGrid(
        x_init=-500.0,
        x_num=11,
        x_delta=100.0,
        y_init=-500.0,
        y_num=11,
        y_delta=100.0,
    )
    receptors = ReceptorPathway(cartesian_grids=[grid])

    # Meteorology (will need actual file for execution tests)
    meteorology = MeteorologyPathway(
        surface_file="test.sfc",
        profile_file="test.pfl",
    )

    # Output
    output = OutputPathway(
        receptor_table=True,
        max_table_rank=10,
    )

    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output,
    )


@pytest.fixture
def multi_source_project():
    """Create a project with multiple source types"""
    control = ControlPathway(
        title_one="Integration Test - Multiple Sources",
        title_two="Multiple source types test case",
        averaging_periods=["1", "24"],
        pollutant_id="PM25",
        terrain_type="FLAT",
        calculate_concentration=True,
    )

    # Point source
    point = PointSource(
        source_id="POINT1",
        x_coord=100.0,
        y_coord=200.0,
        base_elevation=0.0,
        stack_height=25.0,
        stack_temp=350.0,
        exit_velocity=10.0,
        stack_diameter=1.5,
        emission_rate=5.0,
    )

    # Area source
    area = AreaSource(
        source_id="AREA1",
        x_coord=300.0,
        y_coord=400.0,
        base_elevation=0.0,
        release_height=5.0,
        initial_vertical_dimension=100.0,  # x half-width
        initial_lateral_dimension=100.0,   # y half-width
        emission_rate=2.0,
        angle=0.0,
    )

    # Volume source
    volume = VolumeSource(
        source_id="VOLUME1",
        x_coord=-200.0,
        y_coord=-300.0,
        base_elevation=0.0,
        release_height=10.0,
        initial_vertical_dimension=5.0,
        initial_lateral_dimension=20.0,
        emission_rate=3.0,
    )

    sources = SourcePathway()
    sources.add_source(point)
    sources.add_source(area)
    sources.add_source(volume)

    # Receptors - grid plus discrete points
    grid = CartesianGrid(
        x_init=-1000.0,
        x_num=21,
        x_delta=100.0,
        y_init=-1000.0,
        y_num=21,
        y_delta=100.0,
    )

    receptors = ReceptorPathway()
    receptors.add_cartesian_grid(grid)
    receptors.add_discrete_receptor(DiscreteReceptor(x_coord=0.0, y_coord=0.0, z_elev=0.0, z_flag=0))
    receptors.add_discrete_receptor(DiscreteReceptor(x_coord=500.0, y_coord=500.0, z_elev=0.0, z_flag=0))

    meteorology = MeteorologyPathway(
        surface_file="test.sfc",
        profile_file="test.pfl",
    )

    output = OutputPathway(
        receptor_table=True,
        max_table_rank=50,
    )

    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output,
    )


# ============================================================================
# Input Generation Tests
# ============================================================================

@pytest.mark.integration
class TestInputGeneration:
    """Test complete input file generation with validation"""

    def test_simple_project_generates_valid_input(self, simple_project, temp_workspace):
        """Test that a simple project generates valid AERMOD input"""
        output_file = temp_workspace / "test_simple.inp"

        # Generate input
        inp_text = simple_project.to_aermod_input(validate=True)

        # Write to file
        output_file.write_text(inp_text)

        # Verify file exists and has content
        assert output_file.exists()
        assert output_file.stat().st_size > 0

        # Check key sections
        assert "CO STARTING" in inp_text
        assert "SO STARTING" in inp_text
        assert "RE STARTING" in inp_text
        assert "ME STARTING" in inp_text
        assert "OU STARTING" in inp_text
        assert "CO FINISHED" in inp_text

    def test_multi_source_project_generates_valid_input(self, multi_source_project, temp_workspace):
        """Test that multi-source project generates valid input"""
        output_file = temp_workspace / "test_multi.inp"

        # Generate and validate
        inp_text = multi_source_project.to_aermod_input(validate=True)
        output_file.write_text(inp_text)

        # Check all source types present
        assert "POINT1" in inp_text
        assert "AREA1" in inp_text
        assert "VOLUME1" in inp_text
        assert "LOCATION  POINT1" in inp_text
        assert "LOCATION  AREA1" in inp_text
        assert "LOCATION  VOLUME1" in inp_text
        assert "SRCPARAM  POINT1" in inp_text
        assert "SRCPARAM  AREA1" in inp_text
        assert "SRCPARAM  VOLUME1" in inp_text

    def test_validation_catches_errors(self):
        """Test that validation catches configuration errors"""
        # Create invalid project (negative stack height)
        control = ControlPathway(
            title_one="Invalid",
            calculate_concentration=True,
        )
        invalid_source = PointSource(
            source_id="BAD",
            x_coord=0.0,
            y_coord=0.0,
            base_elevation=0.0,
            stack_height=-10.0,  # Invalid!
            stack_temp=300.0,
            exit_velocity=10.0,
            stack_diameter=1.0,
            emission_rate=1.0,
        )
        sources = SourcePathway()
        sources.add_source(invalid_source)
        receptors = ReceptorPathway()
        receptors.add_discrete_receptor(DiscreteReceptor(x_coord=0, y_coord=0, z_elev=0, z_flag=0))
        meteorology = MeteorologyPathway(surface_file="test.sfc", profile_file="test.pfl")
        output = OutputPathway()

        project = AERMODProject(
            control=control,
            sources=sources,
            receptors=receptors,
            meteorology=meteorology,
            output=output,
        )

        # Should raise ValueError when validating
        with pytest.raises(ValueError, match="stack_height"):
            project.to_aermod_input(validate=True)


# ============================================================================
# AERMET Input Generation Tests
# ============================================================================

@pytest.mark.integration
class TestAERMETInputGeneration:
    """Test AERMET input file generation"""

    def test_stage1_generates_complete_input(self, temp_workspace):
        """Test Stage 1 input generation with all components"""
        station = AERMETStation(
            station_id="KORD",
            station_name="Chicago O'Hare",
            latitude=41.98,
            longitude=-87.90,
            time_zone=-6,
            elevation=200.0,
            anemometer_height=10.0,
        )

        upper_air = UpperAirStation(
            station_id="72451",
            station_name="Dodge City",
            latitude=37.77,
            longitude=-99.97,
        )

        stage1 = AERMETStage1(
            job_id="TEST_S1",
            surface_station=station,
            surface_data_file="kord_2020.ish",
            upper_air_station=upper_air,
            upper_air_data_file="ua_2020.fsl",
            start_date="2020/01/01",
            end_date="2020/12/31",
        )

        output = stage1.to_aermet_input()
        output_file = temp_workspace / "stage1.inp"
        output_file.write_text(output)

        # Verify all sections present
        assert "SURFACE" in output
        assert "UPPERAIR" in output
        assert "QA" in output
        assert "DATA       kord_2020.ish ISHD" in output
        assert "DATA       ua_2020.fsl FSL" in output
        assert "LOCATION   KORD 41.9800 -87.9000 -6" in output
        assert "ELEVATION  200.0" in output

    def test_stage2_generates_merge_input(self, temp_workspace):
        """Test Stage 2 merge input generation"""
        stage2 = AERMETStage2(
            job_id="TEST_S2",
            surface_extract="stage1_sfc.ext",
            upper_air_extract="stage1_ua.ext",
            start_date="2020/01/01",
            end_date="2020/12/31",
            merge_file="merged.mrg",
        )

        output = stage2.to_aermet_input()
        output_file = temp_workspace / "stage2.inp"
        output_file.write_text(output)

        assert "MERGE" in output
        assert "OUTPUT     merged.mrg" in output
        assert "INPUT      stage1_sfc.ext" in output
        assert "INPUT      stage1_ua.ext" in output

    def test_stage3_generates_metprep_input(self, temp_workspace):
        """Test Stage 3 METPREP input generation"""
        station = AERMETStation(
            station_id="TEST",
            station_name="Test Station",
            latitude=40.0,
            longitude=-105.0,
            time_zone=-7,
        )

        # Custom surface characteristics
        albedo = [0.50, 0.50, 0.40, 0.20, 0.15, 0.15, 0.15, 0.15, 0.20, 0.30, 0.40, 0.50]
        bowen = [1.50, 1.50, 1.00, 0.80, 0.70, 0.70, 0.70, 0.70, 0.80, 1.00, 1.50, 1.50]
        roughness = [0.50, 0.50, 0.50, 0.40, 0.30, 0.25, 0.25, 0.25, 0.30, 0.40, 0.50, 0.50]

        stage3 = AERMETStage3(
            job_id="TEST_S3",
            station=station,
            merge_file="merged.mrg",
            surface_file="test.sfc",
            profile_file="test.pfl",
            start_date="2020/01/01",
            end_date="2020/12/31",
            albedo=albedo,
            bowen=bowen,
            roughness=roughness,
        )

        output = stage3.to_aermet_input()
        output_file = temp_workspace / "stage3.inp"
        output_file.write_text(output)

        assert "METPREP" in output
        assert "LOCATION   TEST 40.0000 -105.0000 -7" in output
        assert "OUTPUT     test.sfc" in output
        assert "PROFILE    test.pfl" in output
        assert "ALBEDO" in output
        assert "BOWEN" in output
        assert "ROUGHNESS" in output

    def test_aermet_edge_cases_handled(self, temp_workspace):
        """Test AERMET edge cases that were previously buggy"""
        # Test time_zone=0 (UTC)
        station_utc = AERMETStation(
            station_id="TEST",
            station_name="Greenwich",
            latitude=51.5,
            longitude=0.0,
            time_zone=0,  # UTC - was previously dropped
        )

        stage3 = AERMETStage3(station=station_utc)
        output = stage3.to_aermet_input()

        # Should include time_zone=0
        assert "51.5000 0.0000 0" in output

        # Test elevation=0.0 (sea level)
        station_sealevel = AERMETStation(
            station_id="TEST",
            station_name="Sea Level",
            latitude=0.0,
            longitude=0.0,
            time_zone=0,
            elevation=0.0,  # Was previously dropped
        )

        stage1 = AERMETStage1(
            surface_station=station_sealevel,
            surface_data_file="test.dat",
        )
        output = stage1.to_aermet_input()

        # Should include elevation=0.0
        assert "ELEVATION  0.0" in output


# ============================================================================
# End-to-End Workflow Tests (require executables)
# ============================================================================

@pytest.mark.integration
@requires_aermod
class TestAERMODExecution:
    """Test actual AERMOD execution (requires aermod executable)"""

    def test_simple_project_runs_successfully(self, simple_project, temp_workspace):
        """Test that a simple project can run through AERMOD"""
        # This test requires meteorology files - create minimal dummy files
        # or skip if they don't exist
        pytest.skip("Requires actual meteorology files - manual test only")

    def test_runner_handles_missing_files(self, simple_project, temp_workspace):
        """Test that runner properly reports missing input files"""
        # Generate input file
        input_file = temp_workspace / "test.inp"
        inp_text = simple_project.to_aermod_input(validate=False, check_files=False)
        input_file.write_text(inp_text)

        # Try to run (will fail due to missing met files)
        runner = AERMODRunner(executable_path=AERMOD_EXE)
        result = runner.run(str(input_file), working_dir=str(temp_workspace))

        # Should complete but may have errors
        assert result.input_file == str(input_file)
        assert result.return_code is not None


@pytest.mark.integration
@requires_aermet
class TestAERMETExecution:
    """Test actual AERMET execution (requires aermet executable)"""

    def test_aermet_stage1_can_be_generated(self, temp_workspace):
        """Test that Stage 1 input can be generated (execution requires data)"""
        station = AERMETStation(
            station_id="TEST",
            station_name="Test",
            latitude=40.0,
            longitude=-100.0,
            time_zone=-6,
        )

        stage1 = AERMETStage1(
            surface_station=station,
            surface_data_file="test_data.ish",
        )

        input_file = temp_workspace / "stage1.inp"
        input_file.write_text(stage1.to_aermet_input())

        assert input_file.exists()
        assert input_file.stat().st_size > 100


# ============================================================================
# Output Parsing Tests
# ============================================================================

@pytest.mark.integration
class TestOutputParsing:
    """Test output file parsing"""

    def test_parse_minimal_output_file(self, temp_workspace):
        """Test parsing a minimal AERMOD output file"""
        # Create minimal output file
        output_content = """
*** AERMOD - VERSION  21112                                                       ***
*** Integration Test
***

                          *** SETUP Error Messages ***

 *** No Errors Found ***

                          *** Model Setup Options ***

        CONC
        FLAT

      Model Execution Terminated Normally
"""
        output_file = temp_workspace / "test.out"
        output_file.write_text(output_content)

        # Parse it
        parser = AERMODOutputParser(str(output_file))

        # Should parse without error (output_file is a Path object)
        assert str(parser.output_file) == str(output_file)

    def test_output_parser_handles_missing_file(self):
        """Test that parser handles missing files gracefully"""
        with pytest.raises(FileNotFoundError):
            parse_aermod_output("/nonexistent/file.out")


@pytest.mark.integration
@requires_postfile
class TestPOSTFILEParsing:
    """Test POSTFILE output parsing"""

    def test_postfile_can_be_generated_in_input(self, simple_project, temp_workspace):
        """Test that POSTFILE keyword is generated in input files"""
        # Add POSTFILE to output pathway
        simple_project.output.postfile = "results.pst"
        simple_project.output.postfile_averaging = "1-HR"
        simple_project.output.postfile_format = "UNFORM"

        inp_text = simple_project.to_aermod_input(validate=False, check_files=False)

        # Check POSTFILE keyword present
        assert "POSTFILE" in inp_text
        assert "results.pst" in inp_text

    def test_parse_formatted_postfile(self, temp_workspace):
        """Test parsing a formatted POSTFILE"""
        # Create minimal formatted POSTFILE
        postfile_content = """* AERMOD ( 21112):  Integration Test
* MODELING OPTIONS USED:  CONC   FLAT
* AVERTIME: 1-HR
* POLLUTID: SO2
* SRCGROUP: ALL
*    X         Y        CONC    ZELEV    ZHILL   ZFLAG   AVE   GRP     DATE(CONC)
*  (met)     (met)   (ug/m^3)   (m)      (m)             (hr)        (YYMMDDHH)
      0.000     0.000   0.12345   0.00     0.00    0.00     1   ALL    20010101
    100.000   100.000   0.23456   0.00     0.00    0.00     1   ALL    20010101
"""
        postfile_path = temp_workspace / "test.pst"
        postfile_path.write_text(postfile_content)

        # Parse it
        result = read_postfile(str(postfile_path))

        assert result is not None
        assert result.header.pollutant_id == "SO2"
        assert result.header.averaging_period == "1-HR"
        assert len(result.data) == 2
        assert result.max_concentration > 0


# ============================================================================
# Geospatial Export Tests
# ============================================================================

@pytest.mark.integration
@requires_geospatial
class TestGeospatialWorkflow:
    """Test geospatial conversion and export workflow"""

    def test_coordinate_transformation_roundtrip(self):
        """Test UTM to lat/lon and back"""
        transformer = CoordinateTransformer.from_latlon(40.0, -105.0)

        # Convert to UTM and back
        x, y = transformer.latlon_to_utm(40.0, -105.0)
        lat, lon = transformer.utm_to_latlon(x, y)

        # Should be very close (within 0.0001 degrees)
        assert abs(lat - 40.0) < 0.0001
        assert abs(lon - (-105.0)) < 0.0001

    def test_export_concentrations_as_geotiff(self, temp_workspace):
        """Test exporting concentration grid as GeoTIFF"""
        import pandas as pd

        # Create synthetic concentration data
        data = {
            'x': [0, 100, 200, 0, 100, 200],
            'y': [0, 0, 0, 100, 100, 100],
            'concentration': [1.0, 2.0, 3.0, 1.5, 2.5, 3.5],
        }
        df = pd.DataFrame(data)

        # Create transformer
        transformer = CoordinateTransformer(utm_zone=13, hemisphere='N')

        # Export as GeoTIFF
        output_path = temp_workspace / "test.tif"
        export_concentration_geotiff(
            df,
            str(output_path),
            utm_zone=13,
            hemisphere='N',
        )

        # Verify file created
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_export_concentrations_as_shapefile(self, temp_workspace):
        """Test exporting concentration points as shapefile"""
        import pandas as pd

        # Create synthetic data with proper 2D grid
        data = {
            'x': [0, 100, 0, 100],
            'y': [0, 0, 100, 100],
            'concentration': [1.0, 2.0, 1.5, 3.0],
        }
        df = pd.DataFrame(data)

        # Export as shapefile
        output_path = temp_workspace / "test.shp"
        export_concentration_shapefile(
            df,
            str(output_path),
            utm_zone=13,
            hemisphere='N',
        )

        # Verify files created (shapefile is multiple files)
        assert output_path.exists()


# ============================================================================
# Full Pipeline Tests
# ============================================================================

@pytest.mark.integration
class TestFullPipeline:
    """Test complete workflow from input generation to output parsing"""

    def test_input_validation_output_generation_cycle(self, multi_source_project, temp_workspace):
        """Test: generate input -> validate -> write -> read back"""
        # Generate input
        inp_text = multi_source_project.to_aermod_input(validate=True)

        # Write to file
        input_file = temp_workspace / "full_test.inp"
        input_file.write_text(inp_text)

        # Read back and verify
        content = input_file.read_text()

        # Should contain all pathways
        assert "CO STARTING" in content
        assert "SO STARTING" in content
        assert "RE STARTING" in content
        assert "ME STARTING" in content
        assert "OU STARTING" in content

        # Should have all source IDs
        assert "POINT1" in content
        assert "AREA1" in content
        assert "VOLUME1" in content

    @requires_postfile
    @requires_geospatial
    def test_postfile_to_geospatial_export(self, temp_workspace):
        """Test: parse POSTFILE -> convert to GeoDataFrame -> export"""
        # Create minimal POSTFILE with non-collinear points
        postfile_content = """* AERMOD ( 21112):  Full Pipeline Test
* MODELING OPTIONS USED:  CONC   FLAT
* AVERTIME: 1-HR
* POLLUTID: PM25
* SRCGROUP: ALL
*    X         Y        CONC    ZELEV    ZHILL   ZFLAG   AVE   GRP     DATE(CONC)
      0.000     0.000   1.23000   0.00     0.00    0.00     1   ALL    20010101
    100.000     0.000   2.34000   0.00     0.00    0.00     1   ALL    20010101
      0.000   100.000   1.50000   0.00     0.00    0.00     1   ALL    20010101
    100.000   100.000   3.45000   0.00     0.00    0.00     1   ALL    20010101
"""
        postfile_path = temp_workspace / "pipeline.pst"
        postfile_path.write_text(postfile_content)

        # Parse POSTFILE
        result = read_postfile(str(postfile_path))
        assert result is not None

        # Convert to DataFrame
        df = result.to_dataframe()
        assert len(df) == 4  # 4 points (2x2 grid)

        # Export as GeoTIFF
        geotiff_path = temp_workspace / "pipeline.tif"
        export_concentration_geotiff(
            df[['x', 'y', 'concentration']],
            str(geotiff_path),
            utm_zone=13,
            hemisphere='N',
        )

        assert geotiff_path.exists()


# ============================================================================
# AERMAP Integration Tests
# ============================================================================

@pytest.mark.integration
class TestAERMAPInputGeneration:
    """Test AERMAP input file generation and terrain pipeline logic"""

    def test_aermap_project_generates_valid_input(self, temp_workspace):
        """Test that an AERMAPProject generates valid AERMAP input"""
        from pyaermod_aermap import AERMAPProject, AERMAPReceptor, AERMAPSource

        project = AERMAPProject(
            title_one="Integration Test AERMAP",
            dem_files=["n41w088.tif"],
            dem_format="NED",
            anchor_x=400000.0,
            anchor_y=4600000.0,
            utm_zone=16,
            datum="NAD83",
            terrain_type="ELEVATED",
            grid_receptor=True,
            grid_x_init=400000.0,
            grid_y_init=4600000.0,
            grid_x_num=11,
            grid_y_num=11,
            grid_spacing=100.0,
        )
        project.add_source(AERMAPSource("STK1", 400500.0, 4600500.0))
        project.add_receptor(AERMAPReceptor("R001", 400500.0, 4600500.0))

        inp = project.to_aermap_input()
        output_file = temp_workspace / "aermap.inp"
        output_file.write_text(inp)

        assert output_file.exists()
        assert "CO STARTING" in inp
        assert "RE STARTING" in inp
        assert "SO STARTING" in inp
        assert "GRIDCART" in inp
        assert "DISCCART" in inp
        assert "n41w088.tif" in inp
        assert "STK1" in inp

    def test_aermap_from_aermod_project(self, simple_project, temp_workspace):
        """Test creating AERMAPProject from AERMODProject"""
        from pyaermod_aermap import AERMAPProject

        aermap = AERMAPProject.from_aermod_project(
            simple_project,
            dem_files=["test_dem.tif"],
            utm_zone=16,
            datum="NAD83",
        )

        inp = aermap.to_aermap_input()
        assert "CO STARTING" in inp
        assert "STACK1" in inp
        assert "test_dem.tif" in inp
        assert aermap.terrain_type == "ELEVATED"

    def test_terrain_processor_bridge(self, simple_project):
        """Test TerrainProcessor.create_aermap_project_from_aermod"""
        from pyaermod_terrain import TerrainProcessor

        processor = TerrainProcessor()
        aermap = processor.create_aermap_project_from_aermod(
            simple_project,
            dem_files=["dem1.tif", "dem2.tif"],
            utm_zone=16,
        )

        assert len(aermap.dem_files) == 2
        assert len(aermap.sources) == 1
        assert aermap.grid_receptor is True

    def test_aermap_output_parser_disccart(self, temp_workspace):
        """Test parsing AERMAP discrete receptor output"""
        from pyaermod_terrain import AERMAPOutputParser

        content = """** AERMAP Receptor Output
   DISCCART     500000.00    3800000.00    125.30    130.50
   DISCCART     501000.00    3801000.00    150.20    155.80
"""
        output_file = temp_workspace / "aermap_rec.out"
        output_file.write_text(content)

        df = AERMAPOutputParser.parse_receptor_output(output_file)
        assert len(df) == 2
        assert df.iloc[0]["zelev"] == pytest.approx(125.3)

    def test_aermap_output_parser_source(self, temp_workspace):
        """Test parsing AERMAP source output"""
        from pyaermod_terrain import AERMAPOutputParser

        content = """** AERMAP Source Output
SO LOCATION  STACK1      POINT      500500.00    3800500.00       125.50
"""
        output_file = temp_workspace / "aermap_src.out"
        output_file.write_text(content)

        df = AERMAPOutputParser.parse_source_output(output_file)
        assert len(df) == 1
        assert df.iloc[0]["source_id"] == "STACK1"
        assert df.iloc[0]["zelev"] == pytest.approx(125.5)


@pytest.mark.integration
@requires_aermap
class TestAERMAPExecution:
    """Test actual AERMAP execution (requires aermap executable)"""

    def test_aermap_can_be_invoked(self, temp_workspace):
        """Test that AERMAP can be invoked (will fail without DEM files)"""
        from pyaermod_aermap import AERMAPProject, AERMAPSource

        project = AERMAPProject(
            title_one="AERMAP Execution Test",
            dem_files=["nonexistent.tif"],
            anchor_x=400000.0,
            anchor_y=4600000.0,
            utm_zone=16,
        )
        project.add_source(AERMAPSource("STK1", 400500.0, 4600500.0))

        input_file = temp_workspace / "aermap_test.inp"
        project.write(str(input_file))

        from pyaermod_terrain import AERMAPRunner
        runner = AERMAPRunner(executable_path=AERMAP_EXE)
        result = runner.run(str(input_file), working_dir=str(temp_workspace))

        # Will fail due to missing DEM, but should not crash
        assert result.input_file == str(input_file.resolve())
        assert result.return_code is not None
