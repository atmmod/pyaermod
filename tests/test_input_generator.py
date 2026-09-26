"""
Unit tests for PyAERMOD input generator

Tests input file generation for all source types.
"""

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DepositionMethod,
    EventLocation,
    EventPathway,
    EventPeriod,
    GasDepositionParams,
    LineSource,
    MeteorologyPathway,
    Method2Params,
    OpenPitSource,
    OutputPathway,
    ParticleDepositionParams,
    PlatformParams,
    PointCapSource,
    PointHorSource,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SaveFile,
    SidewashPointSource,
    SourcePathway,
    StreetCanyon,
    TerrainType,
    VolumeSource,
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
        # Rotation angle is the 5th param on SRCPARAM, not AREAVERT
        assert "SRCPARAM" in output
        assert "45.00" in output
        assert "AREAVERT" not in output


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
        # Single LOCATION line with both endpoints
        assert output.count("LOCATION") == 1
        assert "-100.0000" in output
        assert "100.0000" in output


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
        # Single LOCATION line with both endpoints
        assert output.count("LOCATION") == 1


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

        output_text = project.to_aermod_input(validate=False)

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
        rbarrier_line = next(l for l in output.split("\n") if "RBARRIER" in l)
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
        srcparam_line = next(l for l in output.split("\n") if "SRCPARAM" in l)
        assert "0.001360" in srcparam_line
        assert "30.00" in srcparam_line


class TestStreetCanyon:
    """Test street canyon approximation for RLINE sources"""

    def test_aspect_ratio(self):
        canyon = StreetCanyon(building_height=20.0, street_width=10.0)
        assert canyon.aspect_ratio == 2.0

    def test_aspect_ratio_zero_width(self):
        canyon = StreetCanyon(building_height=20.0, street_width=0.0)
        assert canyon.aspect_ratio == 0.0

    def test_isolated_roughness_no_effect(self):
        """AR < 0.65 should leave sigma-z unchanged"""
        canyon = StreetCanyon(building_height=6.0, street_width=20.0)  # AR = 0.3
        assert canyon.aspect_ratio < 0.65
        assert canyon.adjusted_sigma_z(1.5) == 1.5
        assert canyon.concentration_factor() == 1.0

    def test_skimming_flow_increases_sigma_z(self):
        """AR ~1.0 should increase sigma-z"""
        canyon = StreetCanyon(building_height=20.0, street_width=20.0)  # AR = 1.0
        base_sz = 1.5
        adj_sz = canyon.adjusted_sigma_z(base_sz)
        assert adj_sz > base_sz

    def test_deep_canyon_larger_concentration_factor(self):
        """Higher AR should produce a larger concentration factor"""
        shallow = StreetCanyon(building_height=20.0, street_width=20.0)  # AR = 1.0
        deep = StreetCanyon(building_height=30.0, street_width=10.0)     # AR = 3.0
        assert deep.concentration_factor() > shallow.concentration_factor()

    def test_wider_canyon_same_height_more_sigma_z(self):
        """With same height, wider canyon has larger recirc zone → more sigma-z"""
        narrow = StreetCanyon(building_height=20.0, street_width=10.0)
        wide = StreetCanyon(building_height=20.0, street_width=20.0)
        base_sz = 1.5
        assert wide.adjusted_sigma_z(base_sz) > narrow.adjusted_sigma_z(base_sz)

    def test_concentration_factor_cap(self):
        """Factor should be capped at 3.0"""
        canyon = StreetCanyon(building_height=100.0, street_width=10.0)  # AR = 10
        assert canyon.concentration_factor() == 3.0

    def test_rline_with_canyon_modifies_output(self):
        """RLINE source with canyon should have adjusted emission rate and sigma-z"""
        canyon = StreetCanyon(building_height=20.0, street_width=20.0)
        source_plain = RLineSource(
            source_id="HWY1", x_start=0.0, y_start=0.0,
            x_end=1000.0, y_end=0.0, emission_rate=0.002,
        )
        source_canyon = RLineSource(
            source_id="HWY2", x_start=0.0, y_start=0.0,
            x_end=1000.0, y_end=0.0, emission_rate=0.002,
            street_canyon=canyon,
        )
        plain_out = source_plain.to_aermod_input()
        canyon_out = source_canyon.to_aermod_input()

        # Extract SRCPARAM lines
        plain_sp = next(l for l in plain_out.split("\n") if "SRCPARAM" in l)
        canyon_sp = next(l for l in canyon_out.split("\n") if "SRCPARAM" in l)

        # Canyon version should have higher emission rate
        plain_erate = float(plain_sp.split()[2])
        canyon_erate = float(canyon_sp.split()[2])
        assert canyon_erate > plain_erate

        # Canyon version should have larger sigma-z (last field, index 5)
        plain_sz = float(plain_sp.split()[5])
        canyon_sz = float(canyon_sp.split()[5])
        assert canyon_sz > plain_sz

    def test_rlinext_with_canyon_modifies_output(self):
        """RLINEXT source with canyon should have adjusted emission rate and sigma-z"""
        canyon = StreetCanyon(building_height=15.0, street_width=15.0)
        source = RLineExtSource(
            source_id="REXT1",
            x_start=0.0, y_start=0.0, z_start=1.5,
            x_end=500.0, y_end=0.0, z_end=1.5,
            emission_rate=0.001, init_sigma_z=1.5,
            street_canyon=canyon,
        )
        output = source.to_aermod_input()
        srcparam_line = next(l for l in output.split("\n") if "SRCPARAM" in l)
        parts = srcparam_line.split()
        erate = float(parts[2])
        sigma_z = float(parts[5])
        assert erate > 0.001
        assert sigma_z > 1.5

    def test_rline_no_canyon_default(self):
        """Without canyon, output should be unchanged"""
        source = RLineSource(
            source_id="HWY1", x_start=0.0, y_start=0.0,
            x_end=1000.0, y_end=0.0, emission_rate=0.002,
            initial_vertical_dimension=1.5,
        )
        output = source.to_aermod_input()
        srcparam_line = next(l for l in output.split("\n") if "SRCPARAM" in l)
        assert "0.002000" in srcparam_line
        assert "1.50" in srcparam_line


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
        blpgroup_line = next(l for l in output.split("\n") if "BLPGROUP" in l)
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
        srcparam_line = next(l for l in output.split("\n") if "SRCPARAM" in l)
        assert "45.00" in srcparam_line

    def test_openpit_no_angle_by_default(self):
        source = OpenPitSource(
            source_id="PIT3",
            x_coord=0.0, y_coord=0.0,
            x_dimension=200.0, y_dimension=100.0, pit_volume=100000.0,
        )
        output = source.to_aermod_input()
        srcparam_line = next(l for l in output.split("\n") if "SRCPARAM" in l)
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
            BackgroundSector(1, 0.0),
            BackgroundSector(2, 90.0),
        ]
        bg = BackgroundConcentration(
            sectors=sectors,
            sector_values={(1, "ANNUAL"): 5.0, (2, "ANNUAL"): 8.0},
        )
        output = bg.to_aermod_input()
        assert "BGSECTOR  0.0 90.0" in output
        assert "BACKGRND  SECT1  ANNUAL  5" in output
        assert "BACKGRND  SECT2  ANNUAL  8" in output

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
                diffusivity=0.22, diffusivity_water=1.8e-5,
                cuticular_resistance=732.0, henry_constant=0.011,
            ),
        )
        output = source.to_aermod_input()
        assert "GASDEPOS" in output
        assert "STK1" in output
        assert "0.22" in output
        assert "0.011" in output

    def test_gas_deposition_writes_aermod_field_order(self):
        """GASDEPOS srcid Da Dw rcl Henry, all four required (soset.f GASDEP)."""
        source = AreaSource(
            source_id="AREA1", x_coord=0.0, y_coord=0.0,
            emission_rate=1.0,
            gas_deposition=GasDepositionParams(0.08962, 1.04e-5, 2.51e4, 557.0),
        )
        line = next(ln for ln in source.to_aermod_input().splitlines()
                    if "GASDEPOS" in ln)
        assert [float(t) for t in line.split()[2:]] == [0.08962, 1.04e-5, 2.51e4, 557.0]

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

    def test_deposition_method_writes_no_method_line(self):
        # There is no METHOD keyword in AERMOD (modules.f; SO E105, probe
        # deck 20): the field is kept for compatibility and writes nothing.
        source = PointSource(
            source_id="STK1", x_coord=0.0, y_coord=0.0,
            stack_height=50.0, emission_rate=1.0,
            deposition_method=(DepositionMethod.DRYDPLT, 0.5),
        )
        output = source.to_aermod_input()
        assert "METHOD" not in output and "DRYDPLT" not in output

    def test_method_2_line(self):
        # soset.f METH_2: METHOD_2 srcid finemass dg (EPA's testpart deck)
        source = PointSource(
            source_id="STACK1", x_coord=0.0, y_coord=0.0,
            stack_height=35.0, emission_rate=100.0,
            method_2=Method2Params(0.55, 1.2),
        )
        lines = source.to_aermod_input().splitlines()
        assert [ln.split() for ln in lines if ln.split()[0] == "METHOD_2"] == \
            [["METHOD_2", "STACK1", "0.55", "1.2"]]

    def test_platform_line(self):
        # soset.f PLATFM: PLATFORM srcid elev hb wb, after the downwash arrays
        source = PointSource(
            source_id="STACK1", x_coord=0.0, y_coord=0.0, stack_height=35.0,
            building_height=20.0, platform=PlatformParams(0.0, 20.0, 30.0),
        )
        lines = [ln.split() for ln in source.to_aermod_input().splitlines()]
        keywords = [ln[0] for ln in lines]
        assert keywords.index("PLATFORM") > keywords.index("BUILDHGT")
        assert lines[keywords.index("PLATFORM")] == ["PLATFORM", "STACK1", "0", "20", "30"]

    def test_point_cap_and_hor_location_types(self):
        cap = PointCapSource("C1", 0.0, 0.0, stack_height=10.0)
        hor = PointHorSource("H1", 0.0, 0.0, stack_height=10.0)
        assert cap.to_aermod_input().splitlines()[0].split()[:3] == ["LOCATION", "C1", "POINTCAP"]
        assert hor.to_aermod_input().splitlines()[0].split()[:3] == ["LOCATION", "H1", "POINTHOR"]
        assert isinstance(cap, PointSource)

    def test_swpoint_srcparam(self):
        src = SidewashPointSource("SW1", 0.0, 0.0, emission_rate=1.0, release_height=10.0,
                                  building_width=20.0, building_length=30.0,
                                  building_height=15.0, building_angle=90.0)
        lines = [ln.split() for ln in src.to_aermod_input().splitlines()]
        assert lines[0][:3] == ["LOCATION", "SW1", "SWPOINT"]
        assert lines[1] == ["SRCPARAM", "SW1", "1.000000", "10.00", "20.00", "30.00", "15.00", "90.00"]

    def test_fixed_columns_do_not_round_a_value_away(self):
        # EPA's capped deck: an exit velocity of 0.001 m/s must survive
        # the 8.2f column (it became 0.00).
        src = PointSource("S", 0.0, 0.0, stack_height=65.0, stack_temp=425.0,
                          exit_velocity=0.001, stack_diameter=5.0, emission_rate=500.0)
        assert src.to_aermod_input().splitlines()[1].split() == \
            ["SRCPARAM", "S", "500.000000", "65.00", "425.00", "0.001", "5.00"]
        # ... while a binary-noise sum keeps the column's text: 12345.67 + 0.05
        # is 12345.720000000001, whose 12.4f text is right and whose
        # six-significant-digit fallback (12345.7) would not be.
        from pyaermod.sources import _fx
        assert _fx(12345.67 + 0.05, "12.4f") == "  12345.7200"
        assert _fx(0.1 + 0.2, "12.4f") == "      0.3000"
        assert _fx(0.001, "8.2f") == "   0.001"

    def test_bound_columns_write_what_the_slow_check_would(self):
        # The writers call the columns bound once per spec (printf-style
        # formatting and a float-only exactness test); the benchmark
        # workflow gates the 1000-source deck at 25 % slower than main, and
        # parsing the column text back for every number was 50 % on its
        # own. The text must still be format()'s wherever the column holds
        # the value to one part in a million, and the fallback elsewhere.
        import math
        import random

        from pyaermod.sources import _aermod_number, _f8_2, _f10_6, _f12_2, _f12_4, _fx

        def reference(value, spec):
            text = format(value, spec)
            if value == 0 or abs(float(text) - value) <= 1e-6 * abs(value):
                return text
            return f"{_aermod_number(value):>{int(spec.split('.')[0])}}"

        rng = random.Random(26135)
        values = [rng.uniform(-1e6, 1e6) for _ in range(300)]
        values += [round(rng.uniform(-1000, 1000), 2) for _ in range(300)]
        values += [rng.uniform(-1, 1) for _ in range(300)]
        values += [0.0, -0.0, 0.001, -0.001, 0.125, 0.126, 1e30, 1e-30, 12345.67 + 0.05,
                   99999.12 + 5000.0, 0.1 + 0.2, float("inf"), float("-inf")]
        columns = ((_f8_2, "8.2f"), (_f10_6, "10.6f"), (_f12_2, "12.2f"), (_f12_4, "12.4f"))
        for fixed, spec in columns:
            for value in values:
                assert fixed(value) == reference(value, spec) == _fx(value, spec), (value, spec)
            assert fixed(math.nan) == format(math.nan, spec)
        # The fallback does fire: a value the column cannot hold keeps its digits.
        assert _f8_2(0.126) == "   0.126"
        assert _f12_4(0.00001) == "     1.0e-05"  # STODBL wants a decimal point before the exponent

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
                diffusivity=0.22, diffusivity_water=1.8e-5,
                cuticular_resistance=732.0, henry_constant=0.011,
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

    def test_output_type_is_not_written_into_plotfile(self):
        """AERMOD's PLOTFILE takes no output-type field.

        Writing one is a fatal "Too Many Parameters"; the quantity to
        output is a MODELOPT setting on the CO pathway.
        """
        output = OutputPathway(plot_file="test.plt", output_type="DDEP")
        text = output.to_aermod_input()
        assert "PLOTFILE" in text
        assert "test.plt" in text
        assert "DDEP" not in text

    def test_output_type_is_not_written_into_postfile(self):
        """POSTFILE's fifth field is the format keyword, not a type.

        AERMOD rejects anything there that is not PLOT or UNFORM.
        """
        output = OutputPathway(
            postfile="test.pst", postfile_averaging="ANNUAL",
            output_type="WDEP",
        )
        text = output.to_aermod_input()
        assert "   POSTFILE  ANNUAL  ALL  PLOT  test.pst" in text
        assert "WDEP" not in text

    def test_output_quantity_comes_from_modelopt(self):
        """Where the output type actually lives: the CO pathway."""
        control = ControlPathway(
            title_one="t", calculate_concentration=False,
            calculate_dry_deposition=True,
        )
        text = control.to_aermod_input()
        modelopt = next(
            ln for ln in text.splitlines() if "MODELOPT" in ln
        )
        assert "DDEP" in modelopt
        assert "CONC" not in modelopt


class TestEventProcessing:
    """The EV pathway in the layout AERMOD writes for EVENTFIL (probe 29b)."""

    @staticmethod
    def _events():
        return EventPathway(events=[
            EventPeriod("H001H01001", 1, "88030214", "G2", 52.33812,
                        EventLocation(500.0, 500.0, 0.0, 0.0, 0.0)),
            EventPeriod("EVT02", 24, 88030224, location=EventLocation(700.0, 45.0, 12.5, polar=True)),
        ])

    @staticmethod
    def _project(**kw):
        return AERMODProject(
            control=ControlPathway(title_one="Test", eventfil="events.inp",
                                   averaging_periods=["1", "24"]),
            sources=SourcePathway(),
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
            **kw,
        )

    def test_event_pathway_generation(self):
        lines = self._events().to_aermod_input().splitlines()
        assert lines[0] == "EV STARTING" and lines[-1] == "EV FINISHED"
        # EVENTPER evname aveper grpid date conc; EVENTLOC evname XR= x YR= y ze zh zf
        assert lines[1].split() == ["EVENTPER", "H001H01001", "1", "G2", "88030214", "52.33812"]
        assert lines[2].split() == ["EVENTLOC", "H001H01001", "XR=", "500.000000", "YR=",
                                    "500.000000", "0.0000", "0.0000", "0.0000"]
        # ALL by default, an integer date is zero-padded to eight digits,
        # a polar receptor uses RNG=/DIR=, and no flagpole leaves the field off.
        assert lines[3].split() == ["EVENTPER", "EVT02", "24", "ALL", "88030224", "0.00000"]
        assert lines[4].split() == ["EVENTLOC", "EVT02", "RNG=", "700.000000", "DIR=",
                                    "45.000000", "12.5000", "0.0000"]

    def test_event_without_location_writes_eventper_only(self):
        ep = EventPathway(events=[EventPeriod("E1", 1, "88030101")])
        assert [ln.split()[0] for ln in ep.to_aermod_input().splitlines()[1:-1]] == ["EVENTPER"]

    def test_control_pathway_eventfil(self):
        control = ControlPathway(title_one="Test", eventfil="events.inp")
        assert "EVENTFIL  events.inp" in control.to_aermod_input()
        control.eventfil_option = "SOCONT"
        assert "   EVENTFIL  events.inp  SOCONT" in control.to_aermod_input().splitlines()

    def test_control_pathway_no_eventfil(self):
        control = ControlPathway(title_one="Test")
        output = control.to_aermod_input()
        assert "EVENTFIL" not in output

    def test_project_with_events(self):
        project = self._project(events=self._events())
        # The main deck carries EVENTFIL and no EV block.
        main_input = project.to_aermod_input(validate=False)
        assert "EVENTFIL" in main_input and "EV STARTING" not in main_input
        # The event deck is CO SO ME EV OU: no RE, EV before OU, no EVENTFIL.
        ev_input = project.to_aermod_input(validate=False, event_processing=True)
        order = [ln.split()[0] for ln in ev_input.splitlines() if ln.endswith("STARTING")]
        assert order == ["CO", "SO", "ME", "EV", "OU"]
        assert "EVENTFIL" not in ev_input
        ou = ev_input[ev_input.index("OU STARTING"):]
        assert ou.split("\n")[1:-1] == ["   EVENTOUT  DETAIL"]

    def test_event_deck_takes_eventout_from_the_project(self):
        project = self._project(events=self._events())
        project.control.eventfil_option = "SOCONT"
        assert "   EVENTOUT  SOCONT" in project.to_aermod_input(validate=False, event_processing=True)
        project.output.event_output = "DETAIL"
        assert "   EVENTOUT  DETAIL" in project.to_aermod_input(validate=False, event_processing=True)
        project.output.file_format = "EXP"
        ou = project.to_aermod_input(validate=False, event_processing=True).split("OU STARTING")[1]
        assert ou.split("\n")[1:3] == ["   FILEFORM  EXP", "   EVENTOUT  DETAIL"]

    def test_event_deck_leaves_out_the_keywords_evonly_skips(self):
        # coset.f/meset.f dispatch EVENTFIL, SAVEFILE, INITFILE, MULTYEAR
        # and STARTEND only when .NOT.EVONLY.
        project = self._project(events=self._events())
        project.control.save_file = SaveFile("save.fil")
        project.meteorology.start_year, project.meteorology.start_month = 1988, 3
        project.meteorology.start_day = 1
        project.meteorology.end_year, project.meteorology.end_month = 1988, 3
        project.meteorology.end_day = 10
        main = project.to_aermod_input(validate=False)
        assert "SAVEFILE" in main and "STARTEND" in main
        ev = project.to_aermod_input(validate=False, event_processing=True)
        assert "SAVEFILE" not in ev and "STARTEND" not in ev

    def test_project_write_with_events(self, tmp_path):
        project = self._project(events=self._events())
        main_file = tmp_path / "aermod.inp"
        event_file = tmp_path / "events.inp"
        project.write(main_file, event_filename=event_file, validate=False)
        assert "EVENTFIL" in main_file.read_text()
        event_text = event_file.read_text()
        assert event_text.startswith("CO STARTING") and "EVENTPER" in event_text
        assert "RE STARTING" not in event_text

    def test_add_event(self):
        ep = EventPathway()
        ep.add_event(EventPeriod("EVT01", 1, "88030101"))
        assert len(ep.events) == 1
        assert "EVT01" in ep.to_aermod_input()


# ---------------------------------------------------------------------------
# Parametrized tests: source type keywords
# ---------------------------------------------------------------------------


class TestParametrizedSourceKeywords:
    """Parametrized tests verifying that all 10 source types produce correct AERMOD keywords."""

    @pytest.mark.parametrize(
        "source_cls,kwargs,expected_keywords",
        [
            (
                PointSource,
                {
                    "source_id": "S1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "stack_height": 50.0,
                    "stack_diameter": 1.5,
                    "stack_temp": 400.0,
                    "exit_velocity": 10.0,
                    "emission_rate": 1.0,
                },
                ["LOCATION", "POINT", "SRCPARAM"],
            ),
            (
                AreaSource,
                {
                    "source_id": "A1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "emission_rate": 0.5,
                    "initial_lateral_dimension": 100.0,
                    "initial_vertical_dimension": 100.0,
                },
                ["LOCATION", "AREA", "SRCPARAM"],
            ),
            (
                VolumeSource,
                {
                    "source_id": "V1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "emission_rate": 0.3,
                    "release_height": 5.0,
                    "initial_lateral_dimension": 10.0,
                    "initial_vertical_dimension": 5.0,
                },
                ["LOCATION", "VOLUME", "SRCPARAM"],
            ),
            (
                LineSource,
                {
                    "source_id": "L1",
                    "x_start": -100.0,
                    "y_start": 0.0,
                    "x_end": 100.0,
                    "y_end": 0.0,
                    "emission_rate": 0.001,
                },
                ["LOCATION", "LINE", "SRCPARAM"],
            ),
            (
                RLineSource,
                {
                    "source_id": "R1",
                    "x_start": 0.0,
                    "y_start": 0.0,
                    "x_end": 1000.0,
                    "y_end": 0.0,
                    "emission_rate": 0.002,
                },
                ["LOCATION", "RLINE", "SRCPARAM"],
            ),
            (
                RLineExtSource,
                {
                    "source_id": "RX1",
                    "x_start": 500000.0,
                    "y_start": 4200000.0,
                    "z_start": 1.5,
                    "x_end": 500500.0,
                    "y_end": 4200000.0,
                    "z_end": 1.5,
                    "emission_rate": 0.00136,
                    "road_width": 30.0,
                },
                ["LOCATION", "RLINEXT", "SRCPARAM"],
            ),
            (
                AreaCircSource,
                {
                    "source_id": "C1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "radius": 50.0,
                    "num_vertices": 20,
                },
                ["LOCATION", "AREACIRC", "SRCPARAM"],
            ),
            (
                AreaPolySource,
                {
                    "source_id": "P1",
                    "vertices": [(0, 0), (100, 0), (100, 100), (0, 100)],
                },
                ["LOCATION", "AREAPOLY", "SRCPARAM", "AREAVERT"],
            ),
            (
                OpenPitSource,
                {
                    "source_id": "OP1",
                    "x_coord": 500000.0,
                    "y_coord": 4200000.0,
                    "x_dimension": 200.0,
                    "y_dimension": 100.0,
                    "pit_volume": 100000.0,
                },
                ["LOCATION", "OPENPIT", "SRCPARAM"],
            ),
            (
                BuoyLineSource,
                {
                    "source_id": "BL1",
                    "avg_line_length": 100.0,
                    "avg_building_height": 15.0,
                    "avg_building_width": 10.0,
                    "avg_line_width": 5.0,
                    "avg_building_separation": 20.0,
                    "avg_buoyancy_parameter": 500.0,
                    "line_segments": [
                        BuoyLineSegment(
                            source_id="BL01",
                            x_start=500000,
                            y_start=4200000,
                            x_end=500100,
                            y_end=4200000,
                            emission_rate=10.5,
                            release_height=4.5,
                        ),
                    ],
                },
                ["LOCATION", "BUOYLINE", "SRCPARAM", "BLPINPUT", "BLPGROUP"],
            ),
        ],
        ids=[
            "PointSource",
            "AreaSource",
            "VolumeSource",
            "LineSource",
            "RLineSource",
            "RLineExtSource",
            "AreaCircSource",
            "AreaPolySource",
            "OpenPitSource",
            "BuoyLineSource",
        ],
    )
    def test_source_type_keywords(self, source_cls, kwargs, expected_keywords):
        """Each source type must produce its expected AERMOD keywords."""
        source = source_cls(**kwargs)
        output = source.to_aermod_input()
        for kw in expected_keywords:
            assert kw in output, (
                f"{source_cls.__name__} output missing keyword '{kw}'"
            )


# ---------------------------------------------------------------------------
# Parametrized tests: deposition keywords across source types
# ---------------------------------------------------------------------------


class TestParametrizedDepositionKeywords:
    """Parametrized tests verifying deposition keywords across representative source types."""

    @pytest.mark.parametrize(
        "source_cls,base_kwargs",
        [
            (
                PointSource,
                {
                    "source_id": "S1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "stack_height": 50,
                    "stack_diameter": 1.5,
                    "stack_temp": 400,
                    "exit_velocity": 10,
                    "emission_rate": 1.0,
                },
            ),
            (
                AreaSource,
                {
                    "source_id": "A1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "emission_rate": 0.5,
                    "initial_lateral_dimension": 100,
                    "initial_vertical_dimension": 100,
                },
            ),
            (
                VolumeSource,
                {
                    "source_id": "V1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "emission_rate": 0.3,
                    "release_height": 5,
                    "initial_lateral_dimension": 10,
                    "initial_vertical_dimension": 5,
                },
            ),
            (
                LineSource,
                {
                    "source_id": "L1",
                    "x_start": 0,
                    "y_start": 0,
                    "x_end": 100,
                    "y_end": 0,
                    "emission_rate": 1.0,
                },
            ),
            (
                RLineSource,
                {
                    "source_id": "R1",
                    "x_start": 0,
                    "y_start": 0,
                    "x_end": 1000,
                    "y_end": 0,
                    "emission_rate": 0.002,
                },
            ),
            (
                RLineExtSource,
                {
                    "source_id": "RX1",
                    "x_start": 0.0,
                    "y_start": 0.0,
                    "z_start": 1.5,
                    "x_end": 500.0,
                    "y_end": 0.0,
                    "z_end": 1.5,
                    "emission_rate": 0.001,
                    "road_width": 30.0,
                },
            ),
            (
                AreaCircSource,
                {
                    "source_id": "C1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "radius": 50.0,
                },
            ),
            (
                AreaPolySource,
                {
                    "source_id": "P1",
                    "vertices": [(0, 0), (100, 0), (100, 100), (0, 100)],
                },
            ),
            (
                OpenPitSource,
                {
                    "source_id": "OP1",
                    "x_coord": 0.0,
                    "y_coord": 0.0,
                    "x_dimension": 200.0,
                    "y_dimension": 100.0,
                    "pit_volume": 100000.0,
                },
            ),
        ],
        ids=[
            "PointSource",
            "AreaSource",
            "VolumeSource",
            "LineSource",
            "RLineSource",
            "RLineExtSource",
            "AreaCircSource",
            "AreaPolySource",
            "OpenPitSource",
        ],
    )
    def test_gas_deposition_keywords(self, source_cls, base_kwargs):
        """Gas deposition parameters must produce GASDEPOS keyword for all source types."""
        gas_dep = GasDepositionParams(
            diffusivity=0.15, diffusivity_water=2e-5,
            cuticular_resistance=500.0, henry_constant=0.01,
        )
        source = source_cls(**base_kwargs, gas_deposition=gas_dep)
        output = source.to_aermod_input()
        assert "GASDEPOS" in output, (
            f"{source_cls.__name__} with gas_deposition missing GASDEPOS keyword"
        )

    @pytest.mark.parametrize(
        "source_cls,base_kwargs",
        [
            (
                PointSource,
                {
                    "source_id": "S1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "stack_height": 50,
                    "stack_diameter": 1.5,
                    "stack_temp": 400,
                    "exit_velocity": 10,
                    "emission_rate": 1.0,
                },
            ),
            (
                AreaSource,
                {
                    "source_id": "A1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "emission_rate": 0.5,
                    "initial_lateral_dimension": 100,
                    "initial_vertical_dimension": 100,
                },
            ),
            (
                VolumeSource,
                {
                    "source_id": "V1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "emission_rate": 0.3,
                    "release_height": 5,
                    "initial_lateral_dimension": 10,
                    "initial_vertical_dimension": 5,
                },
            ),
        ],
        ids=["PointSource", "AreaSource", "VolumeSource"],
    )
    def test_particle_deposition_keywords(self, source_cls, base_kwargs):
        """Particle deposition params must produce PARTDIAM/MASSFRAX/PARTDENS keywords."""
        particle_dep = ParticleDepositionParams(
            diameters=[1.0, 5.0, 10.0],
            mass_fractions=[0.3, 0.5, 0.2],
            densities=[2.5, 2.5, 2.5],
        )
        source = source_cls(**base_kwargs, particle_deposition=particle_dep)
        output = source.to_aermod_input()
        assert "PARTDIAM" in output
        assert "MASSFRAX" in output
        assert "PARTDENS" in output

    @pytest.mark.parametrize(
        "source_cls,base_kwargs",
        [
            (
                PointSource,
                {
                    "source_id": "S1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "stack_height": 50,
                    "stack_diameter": 1.5,
                    "stack_temp": 400,
                    "exit_velocity": 10,
                    "emission_rate": 1.0,
                },
            ),
            (
                AreaSource,
                {
                    "source_id": "A1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "emission_rate": 0.5,
                    "initial_lateral_dimension": 100,
                    "initial_vertical_dimension": 100,
                },
            ),
            (
                VolumeSource,
                {
                    "source_id": "V1",
                    "x_coord": 0,
                    "y_coord": 0,
                    "emission_rate": 0.3,
                    "release_height": 5,
                    "initial_lateral_dimension": 10,
                    "initial_vertical_dimension": 5,
                },
            ),
        ],
        ids=["PointSource", "AreaSource", "VolumeSource"],
    )
    def test_no_deposition_omits_keywords(self, source_cls, base_kwargs):
        """Sources without deposition params must not produce deposition keywords."""
        source = source_cls(**base_kwargs)
        output = source.to_aermod_input()
        assert "GASDEPOS" not in output
        assert "PARTDIAM" not in output
        assert "MASSFRAX" not in output
        assert "PARTDENS" not in output
        assert "METHOD" not in output


# ============================================================================
# CO restart / NOx background / gas-deposition defaults and OU design-value
# keywords: field layouts per AERMOD v26135 coset.f and ouset.f
# ============================================================================

def _control(**kwargs):
    from pyaermod.input_generator import ControlPathway
    return ControlPathway(title_one="t", **kwargs).to_aermod_input()


class TestRestartKeywordWriting:
    def test_multyear_forms(self):
        from pyaermod.input_generator import MultiYear
        assert "   MULTYEAR  y2.sav  y1.sav\n" in _control(multiyear=MultiYear("y2.sav", "y1.sav"))
        assert "   MULTYEAR  y1.sav\n" in _control(multiyear=MultiYear("y1.sav"))
        assert "   MULTYEAR  H6H  y1.sav\n" in _control(multiyear=MultiYear("y1.sav", h6h=True))

    def test_savefile_forms(self):
        from pyaermod.input_generator import SaveFile
        assert "   SAVEFILE\n" in _control(save_file=SaveFile())
        assert "   SAVEFILE  s.sav\n" in _control(save_file=SaveFile("s.sav"))
        assert "   SAVEFILE  s.sav  30\n" in _control(save_file=SaveFile("s.sav", 30))
        # An alternate file lives in field 5, so the increment (AERMOD's
        # default of 1) has to be written even when the caller left it out.
        assert "   SAVEFILE  s.sav  1  s2.sav\n" in _control(
            save_file=SaveFile("s.sav", alternate_filename="s2.sav"))

    def test_initfile_forms(self):
        from pyaermod.input_generator import InitFile
        assert "   INITFILE\n" in _control(init_file=InitFile())
        assert "   INITFILE  i.sav\n" in _control(init_file=InitFile("i.sav"))

    def test_restart_keywords_precede_runornot(self):
        from pyaermod.input_generator import SaveFile
        text = _control(save_file=SaveFile("s.sav"))
        assert text.index("SAVEFILE") < text.index("RUNORNOT")


class TestNOxBackgroundWriting:
    def _chem(self, nox=None, oz=None, method=None):
        from pyaermod.input_generator import ChemistryMethod, ChemistryOptions
        return _control(pollutant_id="NO2", chemistry=ChemistryOptions(
            method=method or ChemistryMethod.GRSM, ozone_data=oz, nox_background=nox))

    def test_value_file_and_profile_lines(self):
        from pyaermod.input_generator import NOxBackground, TemporalValues
        text = self._chem(NOxBackground(
            value=10.0, value_units="PPB", hourly_file="nox.dat",
            file_units="PPB", file_format="(i2,3i3,f9.3)",
        ))
        assert "   NOXVALUE  10  PPB\n" in text
        assert "   NOX_FILE  nox.dat  PPB  (i2,3i3,f9.3)\n" in text
        text = self._chem(NOxBackground(varying=TemporalValues("SEASON", [1, 2, 3, 4]), units="UG/M3"))
        assert "   NOX_UNIT  UG/M3\n" in text
        assert "   NOX_VALS  SEASON  1 2 3 4\n" in text

    def test_long_profiles_wrap_at_twelve_values(self):
        from pyaermod.input_generator import NOxBackground, TemporalValues
        text = self._chem(NOxBackground(varying=TemporalValues("HROFDY", list(range(24)))))
        lines = [ln for ln in text.splitlines() if "NOX_VALS" in ln]
        assert len(lines) == 2
        assert lines[0].endswith("HROFDY  0 1 2 3 4 5 6 7 8 9 10 11")
        assert lines[1].endswith("HROFDY  12 13 14 15 16 17 18 19 20 21 22 23")

    def test_file_format_without_units_gets_the_default_units_slot(self):
        # coset.f reads field 4 as units, field 5 as format: a format alone
        # would be taken for units and rejected (E203).
        from pyaermod.input_generator import NOxBackground
        text = self._chem(NOxBackground(hourly_file="nox.dat", file_format="FREE"))
        assert "   NOX_FILE  nox.dat  UG/M3  FREE\n" in text

    def test_sector_forms(self):
        from pyaermod.input_generator import BackgroundSpec, NOxBackground
        text = self._chem(NOxBackground(
            sectors=[0.0, 180.0],
            by_sector={1: BackgroundSpec(value=20.0), 2: BackgroundSpec(hourly_file="s2.dat")},
        ))
        assert "   NOXSECTR  0  180\n" in text
        assert "   NOXVALUE  SECT1  20\n" in text
        assert "   NOX_FILE  SECT2  s2.dat\n" in text

    def test_nox_file_shorthand_writes_nox_file_keyword(self):
        from pyaermod.input_generator import ChemistryMethod, ChemistryOptions
        text = _control(pollutant_id="NO2", chemistry=ChemistryOptions(
            method=ChemistryMethod.GRSM, nox_file="bg.dat"))
        assert "   NOX_FILE  bg.dat\n" in text
        assert "NOXVALUE" not in text

    def test_nox_background_wins_over_shorthand(self):
        from pyaermod.input_generator import ChemistryMethod, ChemistryOptions, NOxBackground
        text = _control(pollutant_id="NO2", chemistry=ChemistryOptions(
            method=ChemistryMethod.GRSM, nox_file="old.dat",
            nox_background=NOxBackground(value=5.0)))
        assert "old.dat" not in text
        assert "   NOXVALUE  5\n" in text

    def test_ozone_sector_units_and_profile_lines(self):
        from pyaermod.input_generator import BackgroundSpec, OzoneData, TemporalValues
        text = self._chem(oz=OzoneData(
            uniform_value=40.0, uniform_units="PPB",
            ozone_file="o3.dat", ozone_file_units="PPB", ozone_file_format="(i2,3i3,f9.3)",
            sectors=[0.0, 120.0, 240.0], units="PPB",
            by_sector={2: BackgroundSpec(varying=TemporalValues("ANNUAL", [45.0]))},
            sector_values={1: 40.0, 2: 99.0},
        ))
        assert "   O3SECTOR  0  120  240\n" in text
        assert "   OZONUNIT  PPB\n" in text
        assert "   OZONEVAL  40  PPB\n" in text
        assert "   OZONEFIL  o3.dat  PPB  (i2,3i3,f9.3)\n" in text
        assert "   O3VALUES  SECT2  ANNUAL  45\n" in text
        assert "   OZONEVAL  SECT1  40\n" in text
        # by_sector is authoritative: the sector_values entry for the same
        # sector is not written a second time.
        assert "OZONEVAL  SECT2" not in text


class TestGasDepositionDefaultWriting:
    def test_all_four_keywords(self):
        from pyaermod.input_generator import GasDepositionDefaults
        text = _control(
            alpha=True,
            gas_deposition_defaults=GasDepositionDefaults(0.5, 0.25, 0.75, "SO2"),
            gas_deposition_seasons=[4, 4, 4, 5, 1, 1, 1, 1, 1, 2, 3, 3],
            gas_deposition_land_use=[4] * 36,
        )
        assert "   GASDEPDF  0.5  0.25  0.75  SO2\n" in text
        assert "   GDSEASON  4  4  4  5  1  1  1  1  1  2  3  3\n" in text
        assert "   GDLANUSE  " + "  ".join(["4"] * 36) + "\n" in text
        assert "   GASDEPVD  0.01\n" in _control(alpha=True, gas_deposition_velocity=0.01)

    def test_species_is_optional(self):
        from pyaermod.input_generator import GasDepositionDefaults
        text = _control(alpha=True, gas_deposition_defaults=GasDepositionDefaults(0.5, 0.25, 0.75))
        assert "   GASDEPDF  0.5  0.25  0.75\n" in text


class TestDesignValueOutputWriting:
    def test_fileform_is_written_first(self):
        from pyaermod.input_generator import OutputPathway
        lines = OutputPathway(file_format="EXP", postfile="p.pst",
                              postfile_averaging="1").to_aermod_input().splitlines()
        assert lines[1] == "   FILEFORM  EXP"
        assert "FILEFORM" not in OutputPathway().to_aermod_input()

    def test_maxdaily_mxdybyyr_field_layout(self):
        from pyaermod.input_generator import MaxDailyFile, OutputPathway
        text = OutputPathway(
            max_daily_files=[MaxDailyFile("ALL", "md.dat")],
            max_daily_by_year_files=[MaxDailyFile("STK", "my.dat", file_unit=52)],
        ).to_aermod_input()
        assert "   MAXDAILY  ALL  md.dat\n" in text
        assert "   MXDYBYYR  STK  my.dat  52\n" in text

    def test_maxdcont_both_forms(self):
        from pyaermod.input_generator import MaxDailyContribution, OutputPathway
        text = OutputPathway(
            receptor_table_rank=13,
            max_daily_contributions=[
                MaxDailyContribution("ALL", 8, "h8h.out", lower_rank=8),
                MaxDailyContribution("ALL", 8, "thr.out", threshold=188.0, file_unit=53),
            ],
        ).to_aermod_input()
        assert "   MAXDCONT  ALL  8  8  h8h.out\n" in text
        assert "   MAXDCONT  ALL  8  THRESH  188  thr.out  53\n" in text

    def test_maxdcont_needs_exactly_one_bound(self):
        from pyaermod.input_generator import MaxDailyContribution
        with pytest.raises(ValueError, match="exactly one"):
            MaxDailyContribution("ALL", 8, "f.out")
        with pytest.raises(ValueError, match="exactly one"):
            MaxDailyContribution("ALL", 8, "f.out", lower_rank=8, threshold=1.0)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
