"""
Unit tests for PyAERMOD input generator

Tests input file generation for all source types.
"""

import pytest
from pyaermod_input_generator import (
    ControlPathway,
    SourcePathway,
    PointSource,
    AreaSource,
    AreaCircSource,
    AreaPolySource,
    VolumeSource,
    LineSource,
    RLineSource,
    ReceptorPathway,
    CartesianGrid,
    PolarGrid,
    MeteorologyPathway,
    OutputPathway,
    AERMODProject,
    PollutantType,
    TerrainType
)


class TestControlPathway:
    """Test Control pathway generation"""

    def test_basic_control(self):
        """Test basic control pathway"""
        control = ControlPathway(
            title_one="Test Project",
            pollutant_id=PollutantType.PM25,
            averaging_periods=["ANNUAL"],
            terrain_type=TerrainType.FLAT
        )

        output = control.to_aermod_input()
        assert "CO STARTING" in output
        assert "Test Project" in output
        assert "PM25" in output
        assert "ANNUAL" in output
        assert "CO FINISHED" in output

    def test_multiple_averaging_periods(self):
        """Test multiple averaging periods"""
        control = ControlPathway(
            title_one="Multi-Period Test",
            averaging_periods=["ANNUAL", "24", "1"]
        )

        output = control.to_aermod_input()
        assert "ANNUAL" in output
        assert "24" in output


class TestPointSource:
    """Test point source generation"""

    def test_basic_point_source(self):
        """Test basic point source"""
        source = PointSource(
            source_id="STACK1",
            x_coord=100.0,
            y_coord=200.0,
            base_elevation=10.0,
            stack_height=50.0,
            stack_temp=400.0,
            exit_velocity=15.0,
            stack_diameter=2.0,
            emission_rate=1.5
        )

        output = source.to_aermod_input()
        assert "STACK1" in output
        assert "POINT" in output
        assert "100.0000" in output
        assert "200.0000" in output

    def test_source_groups(self):
        """Test source groups"""
        source = PointSource(
            source_id="STACK1",
            x_coord=0, y_coord=0,
            source_groups=["ALL", "STACKS"]
        )

        output = source.to_aermod_input()
        assert "SRCGROUP  ALL" in output
        assert "SRCGROUP  STACKS" in output


class TestAreaSource:
    """Test area source generation"""

    def test_rectangular_area(self):
        """Test rectangular area source"""
        source = AreaSource(
            source_id="PILE1",
            x_coord=0, y_coord=0,
            initial_lateral_dimension=25.0,
            initial_vertical_dimension=50.0,
            emission_rate=0.0001
        )

        output = source.to_aermod_input()
        assert "PILE1" in output
        assert "AREA" in output
        assert "25.00" in output
        assert "50.00" in output

    def test_rotated_area(self):
        """Test rotated area source"""
        source = AreaSource(
            source_id="AREA1",
            x_coord=0, y_coord=0,
            angle=45.0
        )

        output = source.to_aermod_input()
        assert "AREAVERT" in output
        assert "45.00" in output


class TestAreaCircSource:
    """Test circular area source"""

    def test_circular_area(self):
        """Test circular area source"""
        source = AreaCircSource(
            source_id="TANK1",
            x_coord=0, y_coord=0,
            radius=50.0,
            num_vertices=20
        )

        output = source.to_aermod_input()
        assert "TANK1" in output
        assert "AREACIRC" in output


class TestAreaPolySource:
    """Test polygonal area source"""

    def test_polygonal_area(self):
        """Test polygonal area source"""
        vertices = [(0, 0), (100, 0), (100, 100), (0, 100)]
        source = AreaPolySource(
            source_id="POLY1",
            vertices=vertices
        )

        output = source.to_aermod_input()
        assert "POLY1" in output
        assert "AREAPOLY" in output
        assert "AREAVERT" in output


class TestVolumeSource:
    """Test volume source generation"""

    def test_basic_volume(self):
        """Test basic volume source"""
        source = VolumeSource(
            source_id="BLDG1",
            x_coord=0, y_coord=0,
            release_height=10.0,
            initial_lateral_dimension=5.0,
            initial_vertical_dimension=3.0,
            emission_rate=2.0
        )

        output = source.to_aermod_input()
        assert "BLDG1" in output
        assert "VOLUME" in output
        assert "10.00" in output
        assert "5.00" in output
        assert "3.00" in output


class TestLineSource:
    """Test line source generation"""

    def test_basic_line(self):
        """Test basic line source"""
        source = LineSource(
            source_id="ROAD1",
            x_start=-100.0,
            y_start=0.0,
            x_end=100.0,
            y_end=0.0,
            emission_rate=0.001
        )

        output = source.to_aermod_input()
        assert "ROAD1" in output
        assert "LINE" in output
        assert output.count("LOCATION") == 2  # Two location keywords


class TestRLineSource:
    """Test RLINE source generation"""

    def test_basic_rline(self):
        """Test basic RLINE source"""
        source = RLineSource(
            source_id="HWY1",
            x_start=0.0,
            y_start=0.0,
            x_end=1000.0,
            y_end=0.0,
            emission_rate=0.002
        )

        output = source.to_aermod_input()
        assert "HWY1" in output
        assert "RLINE" in output
        assert output.count("LOCATION") == 2


class TestReceptorPathway:
    """Test receptor generation"""

    def test_cartesian_grid(self):
        """Test Cartesian grid"""
        grid = CartesianGrid.from_bounds(
            x_min=0, x_max=1000,
            y_min=0, y_max=1000,
            spacing=100
        )

        output = grid.to_aermod_input()
        assert "GRIDCART" in output
        assert "XYINC" in output

    def test_polar_grid(self):
        """Test polar grid"""
        grid = PolarGrid(
            x_origin=0, y_origin=0,
            dist_init=100.0,
            dist_num=3,
            dist_delta=400.0,
            dir_init=0.0,
            dir_num=4,
            dir_delta=90.0
        )

        output = grid.to_aermod_input()
        assert "GRIDPOLR" in output
        assert "ORIG" in output
        assert "DIST" in output
        assert "GDIR" in output


class TestPointSourceBuildingBackwardCompat:
    """Test backward compatibility of scalar building params"""

    def test_building_downwash_scalar(self):
        """Scalar building params produce correct AERMOD keywords"""
        source = PointSource(
            source_id="STACK1",
            x_coord=0.0, y_coord=0.0,
            stack_height=50.0,
            emission_rate=1.5,
            building_height=25.0,
            building_width=40.0,
            building_length=30.0,
            building_x_offset=5.0,
            building_y_offset=-3.0,
        )
        output = source.to_aermod_input()

        assert "BUILDHGT" in output
        assert "BUILDWID" in output
        assert "BUILDLEN" in output
        assert "XBADJ" in output
        assert "YBADJ" in output
        assert "25.00" in output
        assert "40.00" in output
        assert "30.00" in output


class TestAERMODProject:
    """Test complete project generation"""

    def test_complete_project(self):
        """Test complete AERMOD project"""
        control = ControlPathway(
            title_one="Integration Test",
            pollutant_id=PollutantType.SO2
        )

        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="S1",
            x_coord=0, y_coord=0,
            stack_height=50.0
        ))

        receptors = ReceptorPathway()
        receptors.add_cartesian_grid(
            CartesianGrid.from_bounds(
                x_min=-500, x_max=500,
                y_min=-500, y_max=500,
                spacing=100
            )
        )

        meteorology = MeteorologyPathway(
            surface_file="test.sfc",
            profile_file="test.pfl"
        )

        output = OutputPathway()

        project = AERMODProject(
            control=control,
            sources=sources,
            receptors=receptors,
            meteorology=meteorology,
            output=output
        )

        output_text = project.to_aermod_input()

        # Check all pathways present
        assert "CO STARTING" in output_text
        assert "SO STARTING" in output_text
        assert "RE STARTING" in output_text
        assert "ME STARTING" in output_text
        assert "OU STARTING" in output_text

        # Check all pathways closed
        assert "CO FINISHED" in output_text
        assert "SO FINISHED" in output_text
        assert "RE FINISHED" in output_text
        assert "ME FINISHED" in output_text
        assert "OU FINISHED" in output_text


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
