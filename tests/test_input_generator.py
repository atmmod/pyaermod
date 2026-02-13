"""
Unit tests for PyAERMOD input generator

Tests input file generation for all source types.
"""

import pytest
from pyaermod.input_generator import (
    BackgroundConcentration,
    BackgroundSector,
    ControlPathway,
    DepositionMethod,
    EventPathway,
    EventPeriod,
    GasDepositionParams,
    ParticleDepositionParams,
    SourcePathway,
    PointSource,
    AreaSource,
    AreaCircSource,
    AreaPolySource,
    VolumeSource,
    LineSource,
    RLineSource,
    RLineExtSource,
    BuoyLineSource,
    BuoyLineSegment,
    OpenPitSource,
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


class TestRLineExtSource:
    """Test RLINEXT source generation"""

    def test_basic_rlinext(self):
        source = RLineExtSource(
            source_id="REXT1",
            x_start=500000.0, y_start=4200000.0, z_start=1.5,
            x_end=500500.0, y_end=4200000.0, z_end=1.5,
            emission_rate=0.00136, road_width=30.0,
        )
        output = source.to_aermod_input()
        assert "REXT1" in output
        assert "RLINEXT" in output
        # Single LOCATION line with 6 coordinates
        assert output.count("LOCATION") == 1

    def test_rlinext_with_barrier(self):
        source = RLineExtSource(
            source_id="REXT2",
            x_start=0.0, y_start=0.0, z_start=1.0,
            x_end=500.0, y_end=0.0, z_end=1.0,
            barrier_height_1=3.0, barrier_dcl_1=-20.0,
            barrier_height_2=3.0, barrier_dcl_2=20.0,
        )
        output = source.to_aermod_input()
        assert "RBARRIER" in output

    def test_rlinext_single_barrier(self):
        source = RLineExtSource(
            source_id="REXT3",
            x_start=0.0, y_start=0.0, z_start=1.0,
            x_end=500.0, y_end=0.0, z_end=1.0,
            barrier_height_1=3.0, barrier_dcl_1=-20.0,
        )
        output = source.to_aermod_input()
        assert "RBARRIER" in output
        # Only one barrier — no second set of height/dcl
        rbarrier_line = [l for l in output.split("\n") if "RBARRIER" in l][0]
        parts = rbarrier_line.split()
        assert len(parts) == 4  # RBARRIER SrcID Ht Dcl

    def test_rlinext_with_depression(self):
        source = RLineExtSource(
            source_id="REXT4",
            x_start=0.0, y_start=0.0, z_start=1.0,
            x_end=500.0, y_end=0.0, z_end=1.0,
            depression_depth=-3.0, depression_wtop=40.0, depression_wbottom=30.0,
        )
        output = source.to_aermod_input()
        assert "RDEPRESS" in output

    def test_rlinext_no_depression_by_default(self):
        source = RLineExtSource(
            source_id="REXT5",
            x_start=0.0, y_start=0.0, z_start=1.0,
            x_end=500.0, y_end=0.0, z_end=1.0,
        )
        output = source.to_aermod_input()
        assert "RDEPRESS" not in output
        assert "RBARRIER" not in output

    def test_rlinext_srcparam_fields(self):
        source = RLineExtSource(
            source_id="REXT6",
            x_start=0.0, y_start=0.0, z_start=1.5,
            x_end=500.0, y_end=0.0, z_end=1.5,
            emission_rate=0.00136, dcl=5.0,
            road_width=30.0, init_sigma_z=2.0,
        )
        output = source.to_aermod_input()
        assert "SRCPARAM" in output
        srcparam_line = [l for l in output.split("\n") if "SRCPARAM" in l][0]
        assert "0.001360" in srcparam_line
        assert "30.00" in srcparam_line


class TestBuoyLineSource:
    """Test BUOYLINE source generation"""

    def test_basic_buoyline(self):
        source = BuoyLineSource(
            source_id="BLP1",
            avg_line_length=100.0, avg_building_height=15.0,
            avg_building_width=10.0, avg_line_width=5.0,
            avg_building_separation=20.0, avg_buoyancy_parameter=500.0,
            line_segments=[
                BuoyLineSegment(
                    source_id="BL01",
                    x_start=500000, y_start=4200000,
                    x_end=500100, y_end=4200000,
                    emission_rate=10.5, release_height=4.5,
                ),
            ],
        )
        output = source.to_aermod_input()
        assert "BUOYLINE" in output
        assert "BL01" in output
        assert "BLPINPUT" in output
        assert "BLPGROUP" in output

    def test_multiple_segments(self):
        source = BuoyLineSource(
            source_id="BLP2",
            avg_line_length=100.0, avg_building_height=15.0,
            avg_building_width=10.0, avg_line_width=5.0,
            avg_building_separation=20.0, avg_buoyancy_parameter=500.0,
            line_segments=[
                BuoyLineSegment(source_id="BL01", x_start=0, y_start=0, x_end=100, y_end=0),
                BuoyLineSegment(source_id="BL02", x_start=0, y_start=50, x_end=100, y_end=50),
            ],
        )
        output = source.to_aermod_input()
        assert output.count("LOCATION") == 2  # one per segment
        assert output.count("SRCPARAM") == 2  # one per segment
        assert "BL01" in output
        assert "BL02" in output
        # BLPGROUP should list both segment IDs
        blpgroup_line = [l for l in output.split("\n") if "BLPGROUP" in l][0]
        assert "BL01" in blpgroup_line
        assert "BL02" in blpgroup_line

    def test_emission_rate_property(self):
        source = BuoyLineSource(
            source_id="BLP3",
            avg_line_length=100.0, avg_building_height=15.0,
            avg_building_width=10.0, avg_line_width=5.0,
            avg_building_separation=20.0, avg_buoyancy_parameter=500.0,
            line_segments=[
                BuoyLineSegment(source_id="BL01", x_start=0, y_start=0, x_end=100, y_end=0, emission_rate=1.0),
                BuoyLineSegment(source_id="BL02", x_start=0, y_start=50, x_end=100, y_end=50, emission_rate=2.0),
            ],
        )
        assert source.emission_rate == 3.0
        assert source.number_of_lines == 2


class TestOpenPitSource:
    """Test OPENPIT source generation"""

    def test_basic_openpit(self):
        source = OpenPitSource(
            source_id="PIT1",
            x_coord=500000.0, y_coord=4200000.0,
            x_dimension=200.0, y_dimension=100.0,
            pit_volume=100000.0,
        )
        output = source.to_aermod_input()
        assert "PIT1" in output
        assert "OPENPIT" in output
        assert "SRCPARAM" in output
        assert output.count("LOCATION") == 1

    def test_openpit_with_angle(self):
        source = OpenPitSource(
            source_id="PIT2",
            x_coord=0.0, y_coord=0.0,
            x_dimension=200.0, y_dimension=100.0,
            pit_volume=100000.0, angle=45.0,
        )
        output = source.to_aermod_input()
        srcparam_line = [l for l in output.split("\n") if "SRCPARAM" in l][0]
        assert "45.00" in srcparam_line

    def test_openpit_no_angle_by_default(self):
        source = OpenPitSource(
            source_id="PIT3",
            x_coord=0.0, y_coord=0.0,
            x_dimension=200.0, y_dimension=100.0, pit_volume=100000.0,
        )
        output = source.to_aermod_input()
        srcparam_line = [l for l in output.split("\n") if "SRCPARAM" in l][0]
        # Should not have angle field
        parts = srcparam_line.split()
        assert len(parts) == 7  # SRCPARAM SrcID Qemis Hs Xinit Yinit Volume

    def test_effective_depth(self):
        source = OpenPitSource(
            source_id="PIT4",
            x_coord=0.0, y_coord=0.0,
            x_dimension=200.0, y_dimension=100.0,
            pit_volume=400000.0,
        )
        assert source.effective_depth == pytest.approx(20.0)

    def test_openpit_volume_in_output(self):
        source = OpenPitSource(
            source_id="PIT5",
            x_coord=0.0, y_coord=0.0,
            x_dimension=200.0, y_dimension=100.0,
            pit_volume=123456.0,
        )
        output = source.to_aermod_input()
        assert "123456.00" in output


class TestBackgroundConcentration:
    """Test background concentration keyword generation."""

    def test_uniform_background(self):
        bg = BackgroundConcentration(uniform_value=5.0)
        output = bg.to_aermod_input()
        assert "BACKGRND" in output
        assert "5" in output

    def test_period_specific_background(self):
        bg = BackgroundConcentration(period_values={"ANNUAL": 5.0, "24": 10.0})
        output = bg.to_aermod_input()
        assert "BACKGRND  ANNUAL  5" in output
        assert "BACKGRND  24  10" in output

    def test_sector_dependent_background(self):
        sectors = [
            BackgroundSector(1, 0.0, 90.0),
            BackgroundSector(2, 90.0, 180.0),
        ]
        bg = BackgroundConcentration(
            sectors=sectors,
            sector_values={(1, "ANNUAL"): 5.0, (2, "ANNUAL"): 8.0},
        )
        output = bg.to_aermod_input()
        assert "BGSECTOR" in output
        assert "0.0" in output
        assert "90.0" in output
        assert "180.0" in output
        assert "BACKGRND  1  ANNUAL  5" in output
        assert "BACKGRND  2  ANNUAL  8" in output

    def test_source_pathway_with_background(self):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="S1", x_coord=0.0, y_coord=0.0,
            stack_height=50.0, emission_rate=1.0,
        ))
        sp.background = BackgroundConcentration(uniform_value=3.0)
        output = sp.to_aermod_input()
        assert "SO STARTING" in output
        assert "SO FINISHED" in output
        assert "BACKGRND" in output
        # Background should appear after sources but before SO FINISHED
        assert output.index("BACKGRND") > output.index("SRCPARAM")
        assert output.index("BACKGRND") < output.index("SO FINISHED")

    def test_source_pathway_no_background(self):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="S1", x_coord=0.0, y_coord=0.0,
            stack_height=50.0, emission_rate=1.0,
        ))
        output = sp.to_aermod_input()
        assert "BACKGRND" not in output

    def test_empty_background(self):
        """BackgroundConcentration with no values set produces empty output."""
        bg = BackgroundConcentration()
        output = bg.to_aermod_input()
        assert output == ""


class TestDepositionParameters:
    """Test deposition keyword generation."""

    def test_gas_deposition_henry(self):
        source = PointSource(
            source_id="STK1", x_coord=0.0, y_coord=0.0,
            stack_height=50.0, emission_rate=1.0,
            gas_deposition=GasDepositionParams(
                diffusivity=0.22, alpha_r=1000.0,
                reactivity=0.5, henry_constant=0.011,
            ),
        )
        output = source.to_aermod_input()
        assert "GASDEPOS" in output
        assert "STK1" in output
        assert "0.22" in output
        assert "0.011" in output

    def test_gas_deposition_dry_dep_velocity(self):
        source = AreaSource(
            source_id="AREA1", x_coord=0.0, y_coord=0.0,
            emission_rate=1.0,
            gas_deposition=GasDepositionParams(
                diffusivity=0.15, alpha_r=500.0,
                reactivity=0.8, dry_dep_velocity=0.5,
            ),
        )
        output = source.to_aermod_input()
        assert "GASDEPOS" in output
        assert "0.5" in output

    def test_particle_deposition(self):
        source = PointSource(
            source_id="STK1", x_coord=0.0, y_coord=0.0,
            stack_height=50.0, emission_rate=1.0,
            particle_deposition=ParticleDepositionParams(
                diameters=[1.0, 5.0, 10.0],
                mass_fractions=[0.3, 0.5, 0.2],
                densities=[2.5, 2.5, 2.5],
            ),
        )
        output = source.to_aermod_input()
        assert "PARTDIAM" in output
        assert "MASSFRAX" in output
        assert "PARTDENS" in output

    def test_deposition_method(self):
        source = PointSource(
            source_id="STK1", x_coord=0.0, y_coord=0.0,
            stack_height=50.0, emission_rate=1.0,
            deposition_method=(DepositionMethod.DRYDPLT, 0.5),
        )
        output = source.to_aermod_input()
        assert "METHOD" in output
        assert "DRYDPLT" in output
        assert "0.5" in output

    def test_no_deposition_omits_keywords(self):
        source = PointSource(
            source_id="STK1", x_coord=0.0, y_coord=0.0,
            stack_height=50.0, emission_rate=1.0,
        )
        output = source.to_aermod_input()
        assert "GASDEPOS" not in output
        assert "PARTDIAM" not in output
        assert "METHOD" not in output

    def test_deposition_on_line_source(self):
        source = LineSource(
            source_id="LN1", x_start=0.0, y_start=0.0,
            x_end=100.0, y_end=100.0, emission_rate=1.0,
            gas_deposition=GasDepositionParams(
                diffusivity=0.22, alpha_r=1000.0,
                reactivity=0.5, henry_constant=0.011,
            ),
        )
        output = source.to_aermod_input()
        assert "GASDEPOS" in output

    def test_deposition_on_volume_source(self):
        source = VolumeSource(
            source_id="VOL1", x_coord=0.0, y_coord=0.0,
            emission_rate=1.0,
            particle_deposition=ParticleDepositionParams(
                diameters=[2.5], mass_fractions=[1.0], densities=[2.0],
            ),
        )
        output = source.to_aermod_input()
        assert "PARTDIAM" in output
        assert "MASSFRAX" in output
        assert "PARTDENS" in output

    def test_output_type_in_plotfile(self):
        output = OutputPathway(plot_file="test.plt", output_type="DDEP")
        text = output.to_aermod_input()
        assert "PLOTFILE" in text
        assert "DDEP" in text

    def test_output_type_in_postfile(self):
        output = OutputPathway(
            postfile="test.pst", postfile_averaging="ANNUAL",
            output_type="WDEP",
        )
        text = output.to_aermod_input()
        assert "POSTFILE" in text
        assert "WDEP" in text

    def test_output_type_default_conc(self):
        output = OutputPathway(plot_file="test.plt")
        text = output.to_aermod_input()
        assert "CONC" in text


class TestEventProcessing:
    """Test event pathway generation."""

    def test_event_pathway_generation(self):
        ep = EventPathway(events=[
            EventPeriod("EVT01", "24010101", "24010124"),
            EventPeriod("EVT02", "24020101", "24020224", source_group="GRP1"),
        ])
        output = ep.to_aermod_input()
        assert "EV STARTING" in output
        assert "EV FINISHED" in output
        assert "EVENTPER" in output
        assert "EVT01" in output
        assert "24010101" in output
        assert "GRP1" in output

    def test_event_pathway_default_source_group(self):
        ep = EventPathway(events=[
            EventPeriod("EVT01", "24010101", "24010124"),
        ])
        output = ep.to_aermod_input()
        assert "ALL" in output

    def test_control_pathway_eventfil(self):
        control = ControlPathway(
            title_one="Test", eventfil="events.inp",
        )
        output = control.to_aermod_input()
        assert "EVENTFIL  events.inp" in output

    def test_control_pathway_no_eventfil(self):
        control = ControlPathway(title_one="Test")
        output = control.to_aermod_input()
        assert "EVENTFIL" not in output

    def test_project_with_events(self):
        project = AERMODProject(
            control=ControlPathway(title_one="Test", eventfil="events.inp"),
            sources=SourcePathway(),
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
            events=EventPathway(events=[
                EventPeriod("EVT01", "24010101", "24010124"),
            ]),
        )
        # Main input should have EVENTFIL
        main_input = project.to_aermod_input()
        assert "EVENTFIL" in main_input
        # Event pathway generates separately
        ev_input = project.events.to_aermod_input()
        assert "EV STARTING" in ev_input

    def test_project_write_with_events(self, tmp_path):
        project = AERMODProject(
            control=ControlPathway(title_one="Test", eventfil="events.inp"),
            sources=SourcePathway(),
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
            events=EventPathway(events=[
                EventPeriod("EVT01", "24010101", "24010124"),
            ]),
        )
        main_file = tmp_path / "aermod.inp"
        event_file = tmp_path / "events.inp"
        project.write(main_file, event_filename=event_file)
        assert main_file.exists()
        assert event_file.exists()
        assert "EVENTFIL" in main_file.read_text()
        assert "EVENTPER" in event_file.read_text()

    def test_add_event(self):
        ep = EventPathway()
        ep.add_event(EventPeriod("EVT01", "24010101", "24010124"))
        assert len(ep.events) == 1
        output = ep.to_aermod_input()
        assert "EVT01" in output


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
