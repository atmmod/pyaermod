"""Tests for Priority 7 advanced features.

Feature 1: Source Group Management
Feature 2: NO2/SO2 Chemistry Options
Feature 3: Building Downwash Expansion (AreaSource/VolumeSource)
Feature 4: Terrain Pipeline Improvements
"""

import numpy as np
import pandas as pd
import pytest

from pyaermod.input_generator import (
    AERMODProject,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    OzoneData,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourceGroupDefinition,
    SourcePathway,
    VolumeSource,
    _building_downwash_lines,
    _format_building_keyword,
)
from pyaermod.validator import Validator

# ============================================================================
# FEATURE 1: SOURCE GROUP MANAGEMENT
# ============================================================================

class TestSourceGroupDefinition:
    """Tests for SourceGroupDefinition dataclass."""

    def test_basic_creation(self):
        group = SourceGroupDefinition(
            group_name="STACKS",
            member_source_ids=["STK1", "STK2"],
            description="All stacks",
        )
        assert group.group_name == "STACKS"
        assert group.member_source_ids == ["STK1", "STK2"]
        assert group.description == "All stacks"

    def test_default_empty_members(self):
        group = SourceGroupDefinition(group_name="GRP1")
        assert group.member_source_ids == []
        assert group.description == ""

    def test_max_name_length(self):
        group = SourceGroupDefinition(group_name="12345678")
        assert len(group.group_name) == 8


class TestSourcePathwayGroups:
    """Tests for centralized source group management in SourcePathway."""

    def test_add_group(self):
        sp = SourcePathway()
        grp = SourceGroupDefinition("GRP1", ["STK1"])
        sp.add_group(grp)
        assert len(sp.group_definitions) == 1
        assert sp.group_definitions[0].group_name == "GRP1"

    def test_srcgroup_all_emitted(self, valid_point_source):
        sp = SourcePathway()
        sp.add_source(valid_point_source)
        output = sp.to_aermod_input()
        assert "SRCGROUP  ALL      STK1" in output

    def test_srcgroup_all_multiple_sources(self):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        sp.add_source(PointSource(
            source_id="STK2", x_coord=100, y_coord=100,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        output = sp.to_aermod_input()
        assert "SRCGROUP  ALL      STK1 STK2" in output

    def test_srcgroup_all_with_buoyline(self):
        sp = SourcePathway()
        bl = BuoyLineSource(
            source_id="BL1",
            avg_line_length=100, avg_building_height=10,
            avg_building_width=20, avg_line_width=5,
            avg_building_separation=30, avg_buoyancy_parameter=1.0,
            line_segments=[
                BuoyLineSegment("SEG1", 0, 0, 100, 0),
                BuoyLineSegment("SEG2", 100, 0, 200, 0),
            ],
        )
        sp.add_source(bl)
        output = sp.to_aermod_input()
        # BUOYLINE segment IDs should appear in SRCGROUP ALL
        assert "SRCGROUP  ALL      SEG1 SEG2" in output

    def test_custom_group_emitted(self, valid_point_source):
        sp = SourcePathway()
        sp.add_source(valid_point_source)
        sp.add_group(SourceGroupDefinition("STACKS", ["STK1"]))
        output = sp.to_aermod_input()
        assert "SRCGROUP  STACKS   STK1" in output

    def test_custom_group_multiple_members(self):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="S1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        sp.add_source(PointSource(
            source_id="S2", x_coord=100, y_coord=100,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        sp.add_group(SourceGroupDefinition("BOTH", ["S1", "S2"]))
        output = sp.to_aermod_input()
        assert "SRCGROUP  BOTH     S1 S2" in output

    def test_multiple_custom_groups(self, valid_point_source):
        sp = SourcePathway()
        sp.add_source(valid_point_source)
        sp.add_source(AreaSource(source_id="AREA1", x_coord=0, y_coord=0))
        sp.add_group(SourceGroupDefinition("POINTS", ["STK1"]))
        sp.add_group(SourceGroupDefinition("AREAS", ["AREA1"]))
        output = sp.to_aermod_input()
        assert "SRCGROUP  POINTS" in output
        assert "SRCGROUP  AREAS" in output


class TestOutputPathwayPlotFileGroups:
    """Tests for per-group PLOTFILE output."""

    def test_per_group_plotfile_emitted(self):
        op = OutputPathway(
            plot_file_groups=[
                ("ANNUAL", "STACKS", "stacks_annual.plt"),
                ("24", "AREAS", "areas_24hr.plt"),
            ],
        )
        output = op.to_aermod_input()
        assert "PLOTFILE  ANNUAL  STACKS  CONC  FIRST  stacks_annual.plt" in output
        assert "PLOTFILE  24  AREAS  CONC  FIRST  areas_24hr.plt" in output

    def test_per_group_plotfile_with_main_plotfile(self):
        op = OutputPathway(
            plot_file="main.plt",
            plot_file_groups=[("ANNUAL", "GRP1", "grp1.plt")],
        )
        output = op.to_aermod_input()
        assert "PLOTFILE  ANNUAL  ALL" in output
        assert "PLOTFILE  ANNUAL  GRP1" in output

    def test_empty_plot_file_groups(self):
        op = OutputPathway()
        output = op.to_aermod_input()
        # Should not contain per-group PLOTFILE lines
        lines = output.split("\n")
        plotfile_lines = [l for l in lines if "PLOTFILE" in l]
        assert len(plotfile_lines) == 0


class TestSourceGroupValidation:
    """Tests for source group validation."""

    def _make_project(self, groups=None):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        if groups:
            for g in groups:
                sp.add_group(g)
        return AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

    def test_valid_group(self):
        proj = self._make_project([SourceGroupDefinition("STACKS", ["STK1"])])
        result = Validator.validate(proj)
        assert result.is_valid

    def test_group_name_too_long(self):
        proj = self._make_project([SourceGroupDefinition("TOOLONGNAME", ["STK1"])])
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("exceeds 8 characters" in str(e) for e in result.errors)

    def test_duplicate_group_names(self):
        proj = self._make_project([
            SourceGroupDefinition("GRP1", ["STK1"]),
            SourceGroupDefinition("GRP1", ["STK1"]),
        ])
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("duplicate group name" in str(e) for e in result.errors)

    def test_dangling_member_id(self):
        proj = self._make_project([SourceGroupDefinition("GRP1", ["NONEXIST"])])
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("not found" in str(e) for e in result.errors)


# ============================================================================
# FEATURE 2: NO2/SO2 CHEMISTRY OPTIONS
# ============================================================================

class TestChemistryClasses:
    """Tests for chemistry-related dataclasses."""

    def test_chemistry_method_values(self):
        assert ChemistryMethod.OLM.value == "OLM"
        assert ChemistryMethod.PVMRM.value == "PVMRM"
        assert ChemistryMethod.ARM2.value == "ARM2"
        assert ChemistryMethod.GRSM.value == "GRSM"

    def test_ozone_data_file(self):
        oz = OzoneData(ozone_file="ozone.dat")
        assert oz.ozone_file == "ozone.dat"
        assert oz.uniform_value is None

    def test_ozone_data_uniform(self):
        oz = OzoneData(uniform_value=40.0)
        assert oz.uniform_value == 40.0

    def test_ozone_data_sectors(self):
        oz = OzoneData(sector_values={1: 40.0, 2: 45.0})
        assert len(oz.sector_values) == 2

    def test_chemistry_options_defaults(self):
        chem = ChemistryOptions()
        assert chem.method == ChemistryMethod.ARM2
        assert chem.default_no2_ratio == 0.5
        assert chem.ozone_data is None
        assert chem.olm_groups == []

    def test_chemistry_with_olm_groups(self):
        grp = SourceGroupDefinition("OLMGRP1", ["STK1", "STK2"])
        chem = ChemistryOptions(
            method=ChemistryMethod.OLM,
            ozone_data=OzoneData(ozone_file="ozone.dat"),
            olm_groups=[grp],
        )
        assert len(chem.olm_groups) == 1


class TestChemistryControlPathway:
    """Tests for chemistry in ControlPathway output."""

    def test_modelopt_arm2(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(method=ChemistryMethod.ARM2),
        )
        output = ctrl.to_aermod_input()
        assert "MODELOPT  CONC FLAT ARM2" in output

    def test_modelopt_olm(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.OLM,
                ozone_data=OzoneData(ozone_file="ozone.dat"),
            ),
        )
        output = ctrl.to_aermod_input()
        assert "MODELOPT  CONC FLAT OLM" in output

    def test_modelopt_pvmrm(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.PVMRM,
                ozone_data=OzoneData(ozone_file="ozone.dat"),
            ),
        )
        output = ctrl.to_aermod_input()
        assert "PVMRM" in output

    def test_modelopt_grsm(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.GRSM,
                ozone_data=OzoneData(ozone_file="ozone.dat"),
                nox_file="nox_bg.dat",
            ),
        )
        output = ctrl.to_aermod_input()
        assert "GRSM" in output
        assert "NOXVALUE  nox_bg.dat" in output

    def test_o3values_file(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.OLM,
                ozone_data=OzoneData(ozone_file="ozone.dat"),
            ),
        )
        output = ctrl.to_aermod_input()
        assert "O3VALUES  ozone.dat" in output

    def test_o3values_uniform(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.PVMRM,
                ozone_data=OzoneData(uniform_value=40.0),
            ),
        )
        output = ctrl.to_aermod_input()
        assert "O3VALUES  UNIFORM  40" in output

    def test_o3values_sector(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(
                method=ChemistryMethod.OLM,
                ozone_data=OzoneData(sector_values={1: 40.0, 2: 45.0}),
            ),
        )
        output = ctrl.to_aermod_input()
        assert "O3VALUES  SECTOR  1" in output
        assert "O3VALUES  SECTOR  2" in output

    def test_no2stack_emitted(self):
        ctrl = ControlPathway(
            title_one="Test",
            pollutant_id=PollutantType.NO2,
            chemistry=ChemistryOptions(default_no2_ratio=0.75),
        )
        output = ctrl.to_aermod_input()
        assert "NO2STACK  0.7500" in output

    def test_no_chemistry_no_extra_keywords(self):
        ctrl = ControlPathway(title_one="Test", pollutant_id=PollutantType.NO2)
        output = ctrl.to_aermod_input()
        assert "O3VALUES" not in output
        assert "NO2STACK" not in output
        assert "NOXVALUE" not in output


class TestPointSourceNO2Ratio:
    """Tests for per-source NO2/NOx ratio."""

    def test_no2_ratio_emitted(self):
        src = PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400,
            exit_velocity=10, no2_ratio=0.75,
        )
        output = src.to_aermod_input()
        assert "NO2RATIO  STK1     0.7500" in output

    def test_no2_ratio_not_emitted_when_none(self, valid_point_source):
        output = valid_point_source.to_aermod_input()
        assert "NO2RATIO" not in output


class TestOLMGroupEmission:
    """Tests for OLMGROUP keyword in SO pathway."""

    def test_olmgroup_emitted(self):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        sp.add_source(PointSource(
            source_id="STK2", x_coord=100, y_coord=100,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        chem = ChemistryOptions(
            method=ChemistryMethod.OLM,
            ozone_data=OzoneData(ozone_file="ozone.dat"),
            olm_groups=[SourceGroupDefinition("OLMGRP", ["STK1", "STK2"])],
        )
        output = sp.to_aermod_input(chemistry=chem)
        assert "OLMGROUP  OLMGRP   STK1 STK2" in output

    def test_no_olmgroup_without_chemistry(self, valid_point_source):
        sp = SourcePathway()
        sp.add_source(valid_point_source)
        output = sp.to_aermod_input()
        assert "OLMGROUP" not in output


class TestChemistryValidation:
    """Tests for chemistry validation."""

    def _make_project(self, chemistry=None, pollutant=PollutantType.NO2):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        return AERMODProject(
            control=ControlPathway(
                title_one="Test", pollutant_id=pollutant, chemistry=chemistry,
            ),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

    def test_valid_arm2(self):
        proj = self._make_project(ChemistryOptions(method=ChemistryMethod.ARM2))
        result = Validator.validate(proj)
        assert result.is_valid

    def test_wrong_pollutant(self):
        proj = self._make_project(
            ChemistryOptions(method=ChemistryMethod.ARM2),
            pollutant=PollutantType.PM25,
        )
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("require pollutant_id=NO2" in str(e) for e in result.errors)

    def test_olm_requires_ozone(self):
        proj = self._make_project(ChemistryOptions(method=ChemistryMethod.OLM))
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("ozone data required" in str(e) for e in result.errors)

    def test_pvmrm_requires_ozone(self):
        proj = self._make_project(ChemistryOptions(method=ChemistryMethod.PVMRM))
        result = Validator.validate(proj)
        assert not result.is_valid

    def test_grsm_requires_ozone(self):
        proj = self._make_project(ChemistryOptions(method=ChemistryMethod.GRSM))
        result = Validator.validate(proj)
        assert not result.is_valid

    def test_olm_with_ozone_valid(self):
        proj = self._make_project(ChemistryOptions(
            method=ChemistryMethod.OLM,
            ozone_data=OzoneData(ozone_file="ozone.dat"),
        ))
        result = Validator.validate(proj)
        assert result.is_valid

    def test_invalid_no2_ratio_low(self):
        proj = self._make_project(ChemistryOptions(default_no2_ratio=-0.1))
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("between 0 and 1" in str(e) for e in result.errors)

    def test_invalid_no2_ratio_high(self):
        proj = self._make_project(ChemistryOptions(default_no2_ratio=1.5))
        result = Validator.validate(proj)
        assert not result.is_valid

    def test_negative_ozone_uniform(self):
        proj = self._make_project(ChemistryOptions(
            ozone_data=OzoneData(uniform_value=-10.0),
        ))
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("ozone_data.uniform_value" in str(e) for e in result.errors)

    def test_negative_ozone_sector(self):
        proj = self._make_project(ChemistryOptions(
            ozone_data=OzoneData(sector_values={1: -5.0}),
        ))
        result = Validator.validate(proj)
        assert not result.is_valid

    def test_grsm_nox_file_warning(self):
        proj = self._make_project(ChemistryOptions(
            method=ChemistryMethod.GRSM,
            ozone_data=OzoneData(ozone_file="ozone.dat"),
        ))
        result = Validator.validate(proj)
        # Should produce a warning about missing nox_file
        assert any("NOx background file" in str(e) for e in result.errors)

    def test_olm_group_name_too_long(self):
        proj = self._make_project(ChemistryOptions(
            method=ChemistryMethod.OLM,
            ozone_data=OzoneData(ozone_file="ozone.dat"),
            olm_groups=[SourceGroupDefinition("TOOLONGNAME", ["STK1"])],
        ))
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("exceeds 8 characters" in str(e) for e in result.errors)

    def test_point_source_no2_ratio_invalid(self):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400,
            exit_velocity=10, no2_ratio=1.5,
        ))
        proj = AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.NO2),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("no2_ratio" in str(e) for e in result.errors)


class TestChemistryFullProject:
    """Integration tests for chemistry in full project output."""

    def test_full_project_with_olm(self):
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400,
            exit_velocity=10, no2_ratio=0.8,
        ))
        proj = AERMODProject(
            control=ControlPathway(
                title_one="OLM Test",
                pollutant_id=PollutantType.NO2,
                chemistry=ChemistryOptions(
                    method=ChemistryMethod.OLM,
                    ozone_data=OzoneData(ozone_file="ozone.dat"),
                    default_no2_ratio=0.5,
                    olm_groups=[SourceGroupDefinition("OLMGRP", ["STK1"])],
                ),
            ),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        output = proj.to_aermod_input()
        assert "MODELOPT  CONC FLAT OLM" in output
        assert "O3VALUES  ozone.dat" in output
        assert "NO2STACK  0.5000" in output
        assert "NO2RATIO  STK1     0.8000" in output
        assert "OLMGROUP  OLMGRP   STK1" in output


# ============================================================================
# FEATURE 3: BUILDING DOWNWASH EXPANSION
# ============================================================================

class TestModuleLevelBuildingHelper:
    """Tests for module-level _format_building_keyword function."""

    def test_scalar_value(self):
        lines = _format_building_keyword("STK1", "BUILDHGT", 25.0)
        assert len(lines) == 1
        assert "BUILDHGT" in lines[0]
        assert "STK1" in lines[0]
        assert "25.00" in lines[0]

    def test_36_value_list(self):
        values = [float(i) for i in range(36)]
        lines = _format_building_keyword("STK1", "BUILDWID", values)
        # 36 values / 10 per line = 4 lines (10+10+10+6)
        assert len(lines) == 4
        assert "BUILDWID" in lines[0]

    def test_wrong_list_length(self):
        with pytest.raises(ValueError, match="exactly 36"):
            _format_building_keyword("STK1", "BUILDHGT", [1.0] * 10)

    def test_integer_value_treated_as_scalar(self):
        lines = _format_building_keyword("STK1", "BUILDHGT", 25)
        assert len(lines) == 1


class TestBuildingDownwashLines:
    """Tests for _building_downwash_lines helper."""

    def test_no_building_fields(self, valid_point_source):
        lines = _building_downwash_lines(valid_point_source.source_id, valid_point_source)
        assert lines == []

    def test_all_building_fields(self):
        src = PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
            building_height=20.0, building_width=15.0,
            building_length=30.0, building_x_offset=-5.0, building_y_offset=-3.0,
        )
        lines = _building_downwash_lines("STK1", src)
        assert len(lines) == 5
        keywords = [l.split()[0] for l in lines]
        assert "BUILDHGT" in keywords
        assert "BUILDWID" in keywords
        assert "BUILDLEN" in keywords
        assert "XBADJ" in keywords
        assert "YBADJ" in keywords


class TestAreaSourceBuildingDownwash:
    """Tests for building downwash on AreaSource."""

    def test_area_source_with_scalar_building(self):
        src = AreaSource(
            source_id="AREA1", x_coord=0, y_coord=0,
            building_height=20.0, building_width=15.0,
        )
        output = src.to_aermod_input()
        assert "BUILDHGT" in output
        assert "BUILDWID" in output

    def test_area_source_with_36_value_building(self):
        values = [10.0 + i * 0.5 for i in range(36)]
        src = AreaSource(
            source_id="AREA1", x_coord=0, y_coord=0,
            building_height=values,
        )
        output = src.to_aermod_input()
        assert "BUILDHGT" in output
        # 4 lines for 36 values
        buildhgt_lines = [l for l in output.split("\n") if "BUILDHGT" in l]
        assert len(buildhgt_lines) == 4

    def test_area_source_no_building(self, valid_area_source):
        output = valid_area_source.to_aermod_input()
        assert "BUILDHGT" not in output

    def test_area_source_all_building_fields(self):
        src = AreaSource(
            source_id="AREA1", x_coord=0, y_coord=0,
            building_height=20.0, building_width=15.0,
            building_length=30.0, building_x_offset=-5.0,
            building_y_offset=-3.0,
        )
        output = src.to_aermod_input()
        for kw in ("BUILDHGT", "BUILDWID", "BUILDLEN", "XBADJ", "YBADJ"):
            assert kw in output


class TestVolumeSourceBuildingDownwash:
    """Tests for building downwash on VolumeSource."""

    def test_volume_source_with_scalar_building(self):
        src = VolumeSource(
            source_id="VOL1", x_coord=0, y_coord=0,
            building_height=20.0, building_width=15.0,
        )
        output = src.to_aermod_input()
        assert "BUILDHGT" in output
        assert "BUILDWID" in output

    def test_volume_source_with_36_value_building(self):
        values = [10.0 + i * 0.5 for i in range(36)]
        src = VolumeSource(
            source_id="VOL1", x_coord=0, y_coord=0,
            building_height=values,
        )
        output = src.to_aermod_input()
        assert "BUILDHGT" in output

    def test_volume_source_no_building(self, valid_volume_source):
        output = valid_volume_source.to_aermod_input()
        assert "BUILDHGT" not in output


class TestBuildingDownwashValidation:
    """Tests for building downwash validation on AreaSource/VolumeSource."""

    def _make_project_with_area(self, **area_kwargs):
        sp = SourcePathway()
        sp.add_source(AreaSource(source_id="AREA1", x_coord=0, y_coord=0, **area_kwargs))
        return AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

    def _make_project_with_volume(self, **vol_kwargs):
        sp = SourcePathway()
        sp.add_source(VolumeSource(source_id="VOL1", x_coord=0, y_coord=0, **vol_kwargs))
        return AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

    def test_area_source_valid_building(self):
        proj = self._make_project_with_area(building_height=20.0)
        result = Validator.validate(proj)
        assert result.is_valid

    def test_area_source_wrong_list_length(self):
        proj = self._make_project_with_area(building_height=[1.0] * 10)
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("exactly 36 values" in str(e) for e in result.errors)

    def test_volume_source_valid_building(self):
        proj = self._make_project_with_volume(building_height=20.0)
        result = Validator.validate(proj)
        assert result.is_valid

    def test_volume_source_wrong_list_length(self):
        proj = self._make_project_with_volume(building_height=[1.0] * 20)
        result = Validator.validate(proj)
        assert not result.is_valid
        assert any("exactly 36 values" in str(e) for e in result.errors)


class TestPointSourceBuildingBackwardCompat:
    """Verify PointSource building downwash still works after refactoring."""

    def test_scalar_building_output(self):
        src = PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
            building_height=20.0,
        )
        output = src.to_aermod_input()
        assert "BUILDHGT" in output
        assert "20.00" in output

    def test_36_value_building_output(self):
        values = [15.0] * 36
        src = PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
            building_height=values,
        )
        output = src.to_aermod_input()
        assert "BUILDHGT" in output

    def test_instance_method_still_works(self):
        src = PointSource(
            source_id="STK1", x_coord=0, y_coord=0,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        )
        lines = src._format_building_keyword("BUILDHGT", 25.0)
        assert len(lines) == 1
        assert "STK1" in lines[0]


# ============================================================================
# FEATURE 4: TERRAIN PIPELINE IMPROVEMENTS
# ============================================================================

class TestCartesianGridElevations:
    """Tests for CartesianGrid ELEV/HILL output."""

    def test_no_elevations_backward_compat(self):
        grid = CartesianGrid()
        output = grid.to_aermod_input()
        assert "ELEV" not in output
        assert "HILL" not in output
        # Should be single line with XYINC
        assert "XYINC" in output

    def test_grid_elevations_emitted(self):
        grid = CartesianGrid(
            grid_name="GRID1", x_num=3, y_num=2,
            grid_elevations=[
                [100.0, 105.0, 110.0],  # row 0
                [102.0, 107.0, 112.0],  # row 1
            ],
        )
        output = grid.to_aermod_input()
        assert "ELEV" in output
        assert "100.0" in output
        assert "112.0" in output

    def test_grid_hills_emitted(self):
        grid = CartesianGrid(
            grid_name="GRID1", x_num=3, y_num=2,
            grid_hills=[
                [200.0, 205.0, 210.0],
                [202.0, 207.0, 212.0],
            ],
        )
        output = grid.to_aermod_input()
        assert "HILL" in output
        assert "200.0" in output

    def test_elev_and_hill_together(self):
        grid = CartesianGrid(
            grid_name="GRID1", x_num=3, y_num=2,
            grid_elevations=[[100.0, 105.0, 110.0], [102.0, 107.0, 112.0]],
            grid_hills=[[200.0, 205.0, 210.0], [202.0, 207.0, 212.0]],
        )
        output = grid.to_aermod_input()
        assert "ELEV" in output
        assert "HILL" in output

    def test_elev_row_index_starts_at_1(self):
        grid = CartesianGrid(
            grid_name="GRID1", x_num=2, y_num=2,
            grid_elevations=[[100.0, 105.0], [110.0, 115.0]],
        )
        output = grid.to_aermod_input()
        lines = [l for l in output.split("\n") if "ELEV" in l]
        # Row indices should be 1 and 2
        assert "    1" in lines[0]
        assert "    2" in lines[1]

    def test_large_grid_wraps_at_6_values(self):
        # 10 columns should produce 2 ELEV lines per row (6+4)
        row = [100.0 + i for i in range(10)]
        grid = CartesianGrid(
            grid_name="GRID1", x_num=10, y_num=1,
            grid_elevations=[row],
        )
        output = grid.to_aermod_input()
        elev_lines = [l for l in output.split("\n") if "ELEV" in l]
        assert len(elev_lines) == 2  # 10 values = 6 + 4

    def test_f8_1_format(self):
        grid = CartesianGrid(
            grid_name="GRID1", x_num=2, y_num=1,
            grid_elevations=[[123.4, 567.8]],
        )
        output = grid.to_aermod_input()
        assert "   123.4" in output
        assert "   567.8" in output


class TestTerrainProcessorGridUpdate:
    """Tests for TerrainProcessor grid elevation updates."""

    def test_update_grid_receptor_elevations(self):
        from pyaermod.terrain import TerrainProcessor

        proc = TerrainProcessor()

        # Create a simple 3x2 grid
        grid = CartesianGrid(
            grid_name="GRD1",
            x_init=0.0, x_num=3, x_delta=100.0,
            y_init=0.0, y_num=2, y_delta=100.0,
        )
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=50, y_coord=50,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        proj = AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

        # Mock AERMAP output DataFrame
        xs = [0.0, 100.0, 200.0, 0.0, 100.0, 200.0]
        ys = [0.0, 0.0, 0.0, 100.0, 100.0, 100.0]
        elevs = [100.0, 105.0, 110.0, 102.0, 107.0, 112.0]
        hills = [200.0, 205.0, 210.0, 202.0, 207.0, 212.0]
        rec_df = pd.DataFrame({"x": xs, "y": ys, "zelev": elevs, "zhill": hills})

        proc._update_grid_receptor_elevations(proj, rec_df)

        assert grid.grid_elevations is not None
        assert grid.grid_hills is not None
        assert grid.grid_elevations[0] == [100.0, 105.0, 110.0]
        assert grid.grid_elevations[1] == [102.0, 107.0, 112.0]
        assert grid.grid_hills[0] == [200.0, 205.0, 210.0]

    def test_update_grid_empty_df(self):
        from pyaermod.terrain import TerrainProcessor

        proc = TerrainProcessor()
        grid = CartesianGrid(grid_name="GRD1", x_num=3, y_num=2)
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=50, y_coord=50,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        proj = AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        proc._update_grid_receptor_elevations(proj, pd.DataFrame())
        assert grid.grid_elevations is None

    def test_update_source_elevations(self):
        from pyaermod.terrain import TerrainProcessor

        proc = TerrainProcessor()
        sp = SourcePathway()
        stk = PointSource(
            source_id="STK1", x_coord=50, y_coord=50,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        )
        sp.add_source(stk)
        proj = AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

        src_df = pd.DataFrame({
            "source_id": ["STK1"],
            "zelev": [150.0],
        })
        proc._update_source_elevations(proj, src_df)
        assert stk.base_elevation == 150.0

    def test_update_source_elevations_empty(self):
        from pyaermod.terrain import TerrainProcessor

        proc = TerrainProcessor()
        sp = SourcePathway()
        stk = PointSource(
            source_id="STK1", x_coord=50, y_coord=50,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        )
        sp.add_source(stk)
        proj = AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        proc._update_source_elevations(proj, pd.DataFrame())
        assert stk.base_elevation == 0.0

    def test_update_source_elevations_no_match(self):
        from pyaermod.terrain import TerrainProcessor

        proc = TerrainProcessor()
        sp = SourcePathway()
        stk = PointSource(
            source_id="STK1", x_coord=50, y_coord=50,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        )
        sp.add_source(stk)
        proj = AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        src_df = pd.DataFrame({
            "source_id": ["STK99"],
            "zelev": [150.0],
        })
        proc._update_source_elevations(proj, src_df)
        assert stk.base_elevation == 0.0  # unchanged


class TestCartesianGridWithElevationsInProject:
    """Test that ELEV/HILL lines appear in full project output."""

    def test_full_project_with_grid_elevations(self):
        grid = CartesianGrid(
            grid_name="GRID1", x_num=3, y_num=2,
            x_delta=100.0, y_delta=100.0,
            grid_elevations=[[100.0, 105.0, 110.0], [102.0, 107.0, 112.0]],
            grid_hills=[[200.0, 205.0, 210.0], [202.0, 207.0, 212.0]],
        )
        sp = SourcePathway()
        sp.add_source(PointSource(
            source_id="STK1", x_coord=50, y_coord=50,
            stack_height=30, stack_diameter=1, stack_temp=400, exit_velocity=10,
        ))
        proj = AERMODProject(
            control=ControlPathway(title_one="Test", pollutant_id=PollutantType.PM25),
            sources=sp,
            receptors=ReceptorPathway(cartesian_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        output = proj.to_aermod_input()
        assert "GRIDCART  GRID1    ELEV" in output
        assert "GRIDCART  GRID1    HILL" in output
