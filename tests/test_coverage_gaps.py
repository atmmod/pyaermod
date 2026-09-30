"""
Tests for coverage gaps identified in audit.

Priority 1: SRCGROUP/URBANSRC for all source types, ControlPathway options,
            grid validation edge cases.
Priority 4 (item 4): TerrainProcessor.process() orchestration.
Area 3: aermap.from_aermod_project(), advanced_viz import guards,
        geospatial cubic NaN fallback.
"""

import subprocess
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from pyaermod.input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    PointCapSource,
    PointHorSource,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SidewashPointSource,
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
    VolumeSource,
    create_example_project,
)
from pyaermod.validator import Validator

# ============================================================================
# Helpers: minimal source factories
# ============================================================================


def _make_source(source_cls, *, source_groups=None, is_urban=False, urban_area_name=None):
    """Create a minimal source of the given type with optional group/urban settings."""
    kwargs = {}
    if source_groups is not None:
        kwargs["source_groups"] = source_groups
    if is_urban:
        kwargs["is_urban"] = True
    if urban_area_name:
        kwargs["urban_area_name"] = urban_area_name

    if source_cls in (PointSource, PointCapSource, PointHorSource):
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            stack_height=20, stack_temp=350, exit_velocity=10,
            stack_diameter=1, emission_rate=1, **kwargs,
        )
    elif source_cls is AreaSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            initial_lateral_dimension=25, initial_vertical_dimension=50,
            emission_rate=0.001, **kwargs,
        )
    elif source_cls is AreaCircSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            radius=50, emission_rate=0.001, **kwargs,
        )
    elif source_cls is AreaPolySource:
        return source_cls(
            source_id="SRC1",
            vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
            emission_rate=0.001, **kwargs,
        )
    elif source_cls is VolumeSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            release_height=5, initial_lateral_dimension=10,
            initial_vertical_dimension=5, emission_rate=0.001, **kwargs,
        )
    elif source_cls is LineSource:
        return source_cls(
            source_id="SRC1", x_start=0, y_start=0, x_end=100, y_end=0,
            release_height=2, initial_lateral_dimension=5,
            emission_rate=0.001, **kwargs,
        )
    elif source_cls is RLineSource:
        return source_cls(
            source_id="SRC1", x_start=0, y_start=0, x_end=100, y_end=0,
            emission_rate=0.001, release_height=1.5,
            initial_lateral_dimension=3, initial_vertical_dimension=1.5,
            **kwargs,
        )
    elif source_cls is RLineExtSource:
        return source_cls(
            source_id="SRC1",
            x_start=0, y_start=0, z_start=0,
            x_end=100, y_end=0, z_end=0,
            emission_rate=0.001, dcl=10, road_width=20,
            init_sigma_z=1.5, **kwargs,
        )
    elif source_cls is BuoyLineSource:
        seg = BuoyLineSegment(
            source_id="BSEG1", x_start=0, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        return source_cls(
            source_id="BLP1", line_segments=[seg],
            avg_line_length=100, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
            **kwargs,
        )
    elif source_cls is OpenPitSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0,
            x_dimension=100, y_dimension=200,
            emission_rate=0.01, pit_volume=50000,
            **kwargs,
        )
    elif source_cls is SidewashPointSource:
        return source_cls(
            source_id="SRC1", x_coord=0, y_coord=0, emission_rate=1.0,
            release_height=10.0, building_width=20.0, building_length=30.0,
            building_height=15.0, building_angle=0.0, **kwargs,
        )
    else:
        raise ValueError(f"Unknown source class: {source_cls}")


# All source types that support SRCGROUP/URBANSRC
ALL_SOURCE_TYPES = [
    PointSource, AreaSource, AreaCircSource, AreaPolySource,
    VolumeSource, LineSource, RLineSource, RLineExtSource,
    BuoyLineSource, OpenPitSource,
    PointCapSource, PointHorSource, SidewashPointSource,
]


# ============================================================================
# Priority 1a: SRCGROUP and URBANSRC for all source types
# ============================================================================


# The SO keywords after which a SRCGROUP card is fatal (soset.f SOCARD,
# E140): once a group is defined, no source may be defined or changed.
_E140_KEYWORDS = {"LOCATION", "SRCPARAM", "BUILDHGT", "BUILDWID", "BUILDLEN",
                  "XBADJ", "YBADJ", "PLATFORM", "EMISFACT"}


def _so_cards(text):
    return [ln.split() for ln in text.splitlines() if ln.strip() and not ln.startswith("SO ")]


def _group_members(text):
    """{group: [member tokens]} of the SRCGROUP cards, continuations merged."""
    groups = {}
    for toks in _so_cards(text):
        if toks[0] == "SRCGROUP":
            groups.setdefault(toks[1], []).extend(toks[2:])
    return groups


def _member_ids(src):
    if isinstance(src, BuoyLineSource):
        return [seg.source_id for seg in src.line_segments]
    return [src.source_id]


class TestSourceGroupAllTypes:
    """A source's ``source_groups`` are written in the SO pathway's group
    block, after every source, for every source type.

    The source writers used to put ``SRCGROUP grp srcid`` among their own
    cards, so the next source's LOCATION was fatal: the audit's two-OPENPIT
    deck stopped with SO E140 on v26135. And a source naming group ALL
    wrote ``SRCGROUP ALL srcid``, which is E203 (soset.f SOGRP reads only
    BACKGROUND/NOBACKGROUND after ALL), so even ``create_example_project()``
    failed setup.
    """

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_source_text_has_no_group_card(self, source_cls):
        src = _make_source(source_cls, source_groups=["ALL", "GRP1"])
        assert "SRCGROUP" not in src.to_aermod_input()

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_groups_follow_every_source(self, source_cls):
        src = _make_source(source_cls, source_groups=["ALL", "GRP1", "MOBILE"])
        last = AreaSource(source_id="LAST", x_coord=500, y_coord=500,
                          emission_rate=0.001, source_groups=["GRP1"])
        text = SourcePathway(sources=[src, last]).to_aermod_input()
        keywords = [toks[0] for toks in _so_cards(text)]
        first_group = keywords.index("SRCGROUP")
        assert not _E140_KEYWORDS.intersection(keywords[first_group:]), text
        groups = _group_members(text)
        assert groups["ALL"] == []  # a source ID after ALL is E203
        assert groups["GRP1"] == [*_member_ids(src), "LAST"]
        assert groups["MOBILE"] == _member_ids(src)

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_no_source_groups_writes_only_all(self, source_cls):
        src = _make_source(source_cls, source_groups=None)
        text = SourcePathway(sources=[src]).to_aermod_input()
        assert _group_members(text) == {"ALL": []}

    def test_buoyline_group_uses_segment_ids(self):
        """A BUOYLINE source's groups name its segments, not the BLPGROUP ID."""
        seg1 = BuoyLineSegment(
            source_id="BS1", x_start=0, y_start=0,
            x_end=50, y_end=0, emission_rate=1, release_height=10,
        )
        seg2 = BuoyLineSegment(
            source_id="BS2", x_start=50, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg1, seg2],
            avg_line_length=50, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
            source_groups=["LINES"],
        )
        text = SourcePathway(sources=[blp]).to_aermod_input()
        assert "   SRCGROUP  LINES    BS1 BS2" in text.splitlines()

    def test_per_source_groups_join_a_definition_of_the_same_name(self):
        """The members a definition already lists are not repeated (W314),
        and the rest follow the definition as continuation cards of the
        same group: SOGRP files a continuation under the last group
        defined, so the cards of one group must be adjacent."""
        a1 = AreaSource(source_id="A1", x_coord=0, y_coord=0, source_groups=["G1", "G2"])
        a2 = AreaSource(source_id="A2", x_coord=100, y_coord=0, source_groups=["G1"])
        so = SourcePathway(sources=[a1, a2], group_definitions=[
            SourceGroupDefinition("G1", ["A2"]), SourceGroupDefinition("G3", ["A1"])])
        cards = [ln for ln in so.to_aermod_input().splitlines() if "SRCGROUP" in ln]
        assert cards == [
            "   SRCGROUP  ALL",
            "   SRCGROUP  G1       A2",
            "   SRCGROUP  G1       A1",
            "   SRCGROUP  G3       A1",
            "   SRCGROUP  G2       A1",
        ]

    def test_group_names_are_matched_in_upper_case(self):
        """AERMOD upper-cases every card (aermod.f LWRUPR), and SOGRP takes
        a card naming an existing group as a continuation of the group
        defined last. ``Pit`` and ``PIT`` written apart, with ``ROAD``
        between, put A2 in ROAD instead of PIT on v26135 (review deck
        caseA), with no message; they must be one block."""
        a1 = AreaSource(source_id="A1", x_coord=0, y_coord=0, source_groups=["Pit", "ROAD"])
        a2 = AreaSource(source_id="A2", x_coord=300, y_coord=300, source_groups=["PIT"])
        cards = [ln for ln in SourcePathway(sources=[a1, a2]).to_aermod_input().splitlines()
                 if "SRCGROUP" in ln]
        assert cards == [
            "   SRCGROUP  ALL",
            "   SRCGROUP  PIT      A1 A2",
            "   SRCGROUP  ROAD     A1",
        ]

    def test_source_groups_join_a_definition_spelled_differently(self):
        """A source naming ``g1`` joins the definition ``G1``, not the group
        defined after it (review deck caseB gave ``G2  A2, A3``), and a
        member the definition lists as ``a1`` is not repeated."""
        a1 = AreaSource(source_id="A1", x_coord=0, y_coord=0, source_groups=["g1"])
        a2 = AreaSource(source_id="A2", x_coord=300, y_coord=300)
        a3 = AreaSource(source_id="A3", x_coord=600, y_coord=0, source_groups=["g1"])
        so = SourcePathway(sources=[a1, a2, a3], group_definitions=[
            SourceGroupDefinition("G1", ["a1"]), SourceGroupDefinition("G2", ["A2"])])
        cards = [ln for ln in so.to_aermod_input().splitlines() if "SRCGROUP" in ln]
        assert cards == [
            "   SRCGROUP  ALL",
            "   SRCGROUP  G1       a1",
            "   SRCGROUP  G1       A3",
            "   SRCGROUP  G2       A2",
        ]

    def test_long_member_lists_are_split_into_continuation_cards(self):
        """AERMOD reads 512 characters of a line (ISTRG); a group gathered
        from many sources is written ten IDs to a card."""
        srcs = [AreaSource(source_id=f"AREA{i:04d}", x_coord=10.0 * i, y_coord=0,
                           source_groups=["FIELD"]) for i in range(25)]
        text = SourcePathway(sources=srcs).to_aermod_input()
        cards = [ln for ln in text.splitlines() if ln.split()[:2] == ["SRCGROUP", "FIELD"]]
        assert [len(c.split()) - 2 for c in cards] == [10, 10, 5]
        assert _group_members(text)["FIELD"] == [s.source_id for s in srcs]

    def test_psd_credit_writes_no_srcgroup(self):
        """PSDCREDIT forbids SRCGROUP (E105), per-source groups included."""
        src = AreaSource(source_id="A1", x_coord=0, y_coord=0, source_groups=["G1"])
        text = SourcePathway(sources=[src]).to_aermod_input(psd_credit=True)
        assert "SRCGROUP" not in text

    def test_example_project_writes_a_bare_all_card(self):
        """create_example_project() puts its stack in group ALL; the card
        used to read "SRCGROUP ALL STACK1", E203 in AERMOD's setup."""
        text = create_example_project().to_aermod_input(validate=False)
        cards = [ln.split() for ln in text.splitlines() if "SRCGROUP" in ln]
        assert cards == [["SRCGROUP", "ALL"]]


class TestUrbanSourceAllTypes:
    """Test URBANSRC keyword for all 10 source types."""

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_urban_source(self, source_cls):
        """URBANSRC lists source IDs only (soset.f URBANS with one urban
        area); a trailing area name is read as an undefined source, E300."""
        src = _make_source(source_cls, is_urban=True, urban_area_name="METRO1")
        output = src.to_aermod_input()
        urban_lines = [ln.split() for ln in output.splitlines() if "URBANSRC" in ln]
        assert urban_lines
        assert all(len(toks) == 2 for toks in urban_lines), urban_lines
        assert "METRO1" not in output

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_non_urban_omits_keyword(self, source_cls):
        src = _make_source(source_cls, is_urban=False)
        output = src.to_aermod_input()
        assert "URBANSRC" not in output

    @pytest.mark.parametrize("source_cls", ALL_SOURCE_TYPES, ids=lambda c: c.__name__)
    def test_urban_without_name_still_emits_keyword(self, source_cls):
        """is_urban=True needs no area name: URBANSRC names sources only."""
        src = _make_source(source_cls, is_urban=True, urban_area_name=None)
        output = src.to_aermod_input()
        assert "URBANSRC" in output

    def test_buoyline_urbansrc_uses_segment_ids(self):
        """BuoyLineSource emits URBANSRC per segment."""
        seg1 = BuoyLineSegment(
            source_id="BS1", x_start=0, y_start=0,
            x_end=50, y_end=0, emission_rate=1, release_height=10,
        )
        seg2 = BuoyLineSegment(
            source_id="BS2", x_start=50, y_start=0,
            x_end=100, y_end=0, emission_rate=1, release_height=10,
        )
        blp = BuoyLineSource(
            source_id="BLP1", line_segments=[seg1, seg2],
            avg_line_length=50, avg_building_height=20,
            avg_building_width=15, avg_line_width=10,
            avg_building_separation=30, avg_buoyancy_parameter=0.5,
            is_urban=True, urban_area_name="CITYAREA",
        )
        output = blp.to_aermod_input()
        assert "URBANSRC  BS1" in output
        assert "URBANSRC  BS2" in output
        assert "CITYAREA" not in output


# ============================================================================
# Priority 1b: ControlPathway optional model options
# ============================================================================


class TestControlPathwayOptions:
    """Test all optional keywords in ControlPathway.to_aermod_input()."""

    def _make_control(self, **overrides):
        defaults = dict(
            title_one="Test",
            pollutant_id=PollutantType.PM25,
            averaging_periods=["ANNUAL"],
            terrain_type=TerrainType.FLAT,
        )
        defaults.update(overrides)
        return ControlPathway(**defaults)

    def test_deposition_flag(self):
        ctrl = self._make_control(calculate_deposition=True)
        output = ctrl.to_aermod_input()
        assert "DEPOS" in output

    def test_dry_deposition_flag(self):
        ctrl = self._make_control(calculate_dry_deposition=True)
        output = ctrl.to_aermod_input()
        assert "DDEP" in output

    def test_wet_deposition_flag(self):
        ctrl = self._make_control(calculate_wet_deposition=True)
        output = ctrl.to_aermod_input()
        assert "WDEP" in output

    def test_all_deposition_flags(self):
        ctrl = self._make_control(
            calculate_deposition=True,
            calculate_dry_deposition=True,
            calculate_wet_deposition=True,
        )
        output = ctrl.to_aermod_input()
        assert "DEPOS" in output
        assert "DDEP" in output
        assert "WDEP" in output

    def test_halflife(self):
        ctrl = self._make_control(half_life=12345.6789)
        output = ctrl.to_aermod_input()
        assert "HALFLIFE" in output
        assert "12345.6789" in output

    def test_decay_coefficient(self):
        ctrl = self._make_control(decay_coefficient=1.23e-4)
        output = ctrl.to_aermod_input()
        assert "DCAYCOEF" in output
        assert "1.230000e-04" in output

    def test_elevation_units_feet(self):
        ctrl = self._make_control(elevation_units="FEET")
        output = ctrl.to_aermod_input()
        assert "ELEVUNIT  FEET" in output

    def test_elevation_units_meters_omitted(self):
        ctrl = self._make_control(elevation_units="METERS")
        output = ctrl.to_aermod_input()
        assert "ELEVUNIT" not in output

    def test_flagpole_height(self):
        ctrl = self._make_control(flag_pole_height=1.5)
        output = ctrl.to_aermod_input()
        assert "FLAGPOLE  1.50" in output

    def test_urban_option(self):
        """URBANOPT population [name]: coset.f URBOPT reads field 1 as the
        population when the deck has one urban area (E208 otherwise)."""
        ctrl = self._make_control(urban_option="URBANOPT1")
        output = ctrl.to_aermod_input()
        assert "URBANOPT  1000000.0  URBANOPT1" in output

    def test_low_wind_option(self):
        ctrl = self._make_control(low_wind_option="LOWWIND3")
        output = ctrl.to_aermod_input()
        assert "LOW_WIND  LOWWIND3" in output

    def test_all_optional_together(self):
        """All optional CO keywords at once."""
        ctrl = self._make_control(
            calculate_deposition=True,
            half_life=100.0,
            decay_coefficient=5e-5,
            elevation_units="FEET",
            flag_pole_height=2.0,
            urban_option="URBAN1",
            low_wind_option="LOWWIND3",
        )
        output = ctrl.to_aermod_input()
        for kw in ["DEPOS", "HALFLIFE", "DCAYCOEF", "ELEVUNIT", "FLAGPOLE", "URBANOPT", "LOW_WIND"]:
            assert kw in output


# ============================================================================
# Priority 1c: Grid parameter validation edge cases
# ============================================================================


class TestCartesianGridValidation:
    """Test validator catches invalid CartesianGrid parameters."""

    def _validate_project_with_grid(self, **grid_kwargs):
        defaults = dict(x_init=0, x_num=5, x_delta=100, y_init=0, y_num=5, y_delta=100)
        defaults.update(grid_kwargs)
        grid = CartesianGrid(**defaults)
        project = AERMODProject(
            control=ControlPathway(title_one="T"),
            sources=SourcePathway(sources=[
                PointSource(source_id="S1", x_coord=0, y_coord=0,
                            stack_height=20, stack_temp=350, exit_velocity=10,
                            stack_diameter=1, emission_rate=1),
            ]),
            receptors=ReceptorPathway(cartesian_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        return Validator.validate(project)

    def test_x_num_zero(self):
        result = self._validate_project_with_grid(x_num=0)
        fields = [e.field for e in result.errors]
        assert "x_num" in fields

    def test_y_num_zero(self):
        result = self._validate_project_with_grid(y_num=0)
        fields = [e.field for e in result.errors]
        assert "y_num" in fields

    def test_x_delta_zero(self):
        result = self._validate_project_with_grid(x_delta=0)
        fields = [e.field for e in result.errors]
        assert "x_delta" in fields

    def test_y_delta_zero(self):
        result = self._validate_project_with_grid(y_delta=0)
        fields = [e.field for e in result.errors]
        assert "y_delta" in fields

    def test_negative_num(self):
        result = self._validate_project_with_grid(x_num=-1)
        fields = [e.field for e in result.errors]
        assert "x_num" in fields

    def test_negative_delta(self):
        result = self._validate_project_with_grid(x_delta=-50)
        fields = [e.field for e in result.errors]
        assert "x_delta" in fields


class TestPolarGridValidation:
    """Test validator catches invalid PolarGrid parameters."""

    def _validate_project_with_polar(self, **grid_kwargs):
        defaults = dict(
            x_origin=0, y_origin=0,
            dist_num=5, dist_delta=100,
            dir_num=36, dir_delta=10,
        )
        defaults.update(grid_kwargs)
        grid = PolarGrid(**defaults)
        project = AERMODProject(
            control=ControlPathway(title_one="T"),
            sources=SourcePathway(sources=[
                PointSource(source_id="S1", x_coord=0, y_coord=0,
                            stack_height=20, stack_temp=350, exit_velocity=10,
                            stack_diameter=1, emission_rate=1),
            ]),
            receptors=ReceptorPathway(polar_grids=[grid]),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        return Validator.validate(project)

    def test_dist_num_zero(self):
        result = self._validate_project_with_polar(dist_num=0)
        fields = [e.field for e in result.errors]
        assert "dist_num" in fields

    def test_dist_delta_zero(self):
        result = self._validate_project_with_polar(dist_delta=0)
        fields = [e.field for e in result.errors]
        assert "dist_delta" in fields

    def test_dir_num_zero(self):
        result = self._validate_project_with_polar(dir_num=0)
        fields = [e.field for e in result.errors]
        assert "dir_num" in fields

    def test_dir_delta_zero(self):
        result = self._validate_project_with_polar(dir_delta=0)
        fields = [e.field for e in result.errors]
        assert "dir_delta" in fields

    def test_negative_dist_delta(self):
        result = self._validate_project_with_polar(dist_delta=-100)
        fields = [e.field for e in result.errors]
        assert "dist_delta" in fields

    def test_negative_dir_num(self):
        result = self._validate_project_with_polar(dir_num=-1)
        fields = [e.field for e in result.errors]
        assert "dir_num" in fields


# ============================================================================
# Priority 1d: ReceptorPathway elevation_units and polar grid rendering
# ============================================================================


class TestReceptorPathwayBranches:
    """Test untested branches in ReceptorPathway.to_aermod_input()."""

    def test_elevation_units_feet(self):
        rp = ReceptorPathway(
            elevation_units="FEET",
            cartesian_grids=[CartesianGrid(x_init=0, x_num=3, x_delta=100,
                                           y_init=0, y_num=3, y_delta=100)],
        )
        output = rp.to_aermod_input()
        assert "ELEVUNIT  FEET" in output

    def test_polar_grid_through_pathway(self):
        pg = PolarGrid(
            x_origin=500, y_origin=500,
            dist_num=3, dist_delta=100,
            dir_num=4, dir_delta=90,
        )
        rp = ReceptorPathway(polar_grids=[pg])
        output = rp.to_aermod_input()
        assert "RE STARTING" in output
        assert "GRIDPOLR" in output
        assert "RE FINISHED" in output


# ============================================================================
# Priority 1e: create_example_project smoke test
# ============================================================================


class TestExampleProject:
    """Smoke test for the create_example_project() function."""

    def test_creates_valid_project(self):
        project = create_example_project()
        assert project is not None
        output = project.to_aermod_input()
        assert "CO STARTING" in output
        assert "SO STARTING" in output
        assert "RE STARTING" in output
        assert "ME STARTING" in output
        assert "OU STARTING" in output

    def test_example_project_validates(self):
        project = create_example_project()
        result = Validator.validate(project)
        assert result.is_valid, f"Validation errors: {result.errors}"


# ============================================================================
# Item 4: TerrainProcessor.process() full pipeline with more coverage
# ============================================================================


class TestTerrainProcessorProcessFull:
    """
    Test TerrainProcessor.process() covering additional branches:
    - AERMAP failure -> RuntimeError
    - Source elevation output parsing
    - No DEM files -> RuntimeError
    - Download path (mocked)
    """

    def _make_project(self, with_discrete_receptors=True):
        control = ControlPathway(title_one="Terrain Test")
        sources = SourcePathway()
        point = PointSource(
            source_id="S1", x_coord=500000.0, y_coord=3800000.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        sources.add_source(point)
        receptors = ReceptorPathway()
        if with_discrete_receptors:
            receptors.add_discrete_receptor(
                DiscreteReceptor(x_coord=500100.0, y_coord=3800100.0, z_elev=0, z_flag=0)
            )
        grid = CartesianGrid(
            x_init=499500.0, x_num=3, x_delta=500.0,
            y_init=3799500.0, y_num=3, y_delta=500.0,
        )
        receptors.add_cartesian_grid(grid)
        met = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl")
        output = OutputPathway()
        return AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=met, output=output,
        )

    def test_aermap_failure_raises_runtime_error(self, tmp_path):
        """When AERMAP returns success=False, process() raises RuntimeError."""
        from pyaermod.terrain import AERMAPRunner, AERMAPRunResult, TerrainProcessor

        project = self._make_project()
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=False, input_file=str(tmp_path / "aermap.inp"),
            return_code=1, runtime_seconds=0.5,
            error_message="AERMAP failed with return code 1",
        )

        with (
            patch.object(AERMAPRunner, "__init__", return_value=None),
            patch.object(AERMAPRunner, "run", return_value=mock_result),
            pytest.raises(RuntimeError, match="AERMAP failed"),
        ):
                processor.process(
                    project,
                    bounds=(-88, 40, -87, 41),
                    aermap_exe="/fake/aermap",
                    working_dir=str(tmp_path),
                    skip_download=True,
                    dem_files=["test.tif"],
                )

    def test_process_with_source_output(self, tmp_path):
        """process() parses source elevation output when file exists."""
        from pyaermod.terrain import AERMAPRunner, AERMAPRunResult, TerrainProcessor

        project = self._make_project()
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=True, input_file=str(tmp_path / "aermap.inp"),
            return_code=0, runtime_seconds=1.0,
        )

        # Create receptor output with the default AERMAPProject filename
        rec_file = tmp_path / "aermap_receptors.out"
        rec_file.write_text(
            "** AERMAP\n"
            "   DISCCART     500100.00    3800100.00    150.00    160.00\n"
        )

        # Create source output with the default AERMAPProject filename
        src_file = tmp_path / "aermap_sources.out"
        src_file.write_text(
            "** AERMAP Source Output\n"
            "   SO LOCATION  S1           POINT      500000.00    3800000.00      125.00\n"
        )

        with patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run", return_value=mock_result):
            result = processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                aermap_exe="/fake/aermap",
                working_dir=str(tmp_path),
                skip_download=True,
                dem_files=["test.tif"],
            )

        assert result is project
        # Discrete receptor should have been updated
        rec = result.receptors.discrete_receptors[0]
        assert rec.z_elev == 150.0
        assert rec.z_hill == 160.0
        # Source should have been updated
        src = result.sources.sources[0]
        assert src.base_elevation == 125.0

    def test_process_no_dem_files_raises(self, tmp_path):
        """Empty dem_files list -> RuntimeError."""
        from pyaermod.terrain import TerrainProcessor

        project = self._make_project()
        processor = TerrainProcessor()

        with pytest.raises(RuntimeError, match="No DEM files"):
            processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                working_dir=str(tmp_path),
                skip_download=True,
                dem_files=[],
            )

    def test_process_with_download(self, tmp_path):
        """process() with skip_download=False downloads DEM tiles."""
        from pyaermod.terrain import (
            AERMAPRunner,
            AERMAPRunResult,
            DEMDownloader,
            TerrainProcessor,
        )

        project = self._make_project()
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=True, input_file=str(tmp_path / "aermap.inp"),
            return_code=0, runtime_seconds=1.0,
        )

        # Create a fake DEM file for the downloader to return
        dem_file = tmp_path / "dem_data" / "fake.tif"
        dem_file.parent.mkdir(parents=True, exist_ok=True)
        dem_file.write_text("fake dem")

        # Create receptor output (empty, just the header)
        rec_file = tmp_path / "aermap_receptors.out"
        rec_file.write_text("** AERMAP\n")

        with patch.object(DEMDownloader, "download_dem", return_value=[dem_file]), \
             patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run", return_value=mock_result):
            result = processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                aermap_exe="/fake/aermap",
                working_dir=str(tmp_path),
                skip_download=False,
            )

        assert result is project

    def test_process_grid_elevation_update(self, tmp_path):
        """process() updates CartesianGrid receptor elevations."""
        from pyaermod.terrain import AERMAPRunner, AERMAPRunResult, TerrainProcessor

        project = self._make_project(with_discrete_receptors=False)
        processor = TerrainProcessor()

        mock_result = AERMAPRunResult(
            success=True, input_file=str(tmp_path / "aermap.inp"),
            return_code=0, runtime_seconds=1.0,
        )

        # Receptor output for the 3x3 grid, in the form AERMAP writes it:
        # the network echoed under its name with one ELEV and one HILL
        # row per y value.
        grid = project.receptors.cartesian_grids[0]
        name = grid.grid_name
        lines = [
            "** AERMAP",
            f"   GRIDCART  {name:<8} STA",
            f"   GRIDCART  {name:<8} XYINC  {grid.x_init:12.2f} {grid.x_num:5d} {grid.x_delta:10.2f}"
            f"  {grid.y_init:12.2f} {grid.y_num:5d} {grid.y_delta:10.2f}",
        ]
        for sub in ("ELEV", "HILL"):
            for j in range(grid.y_num):
                vals = [100.0 + i * 10 + j * 5 + (10 if sub == "HILL" else 0) for i in range(grid.x_num)]
                lines.append(f"   GRIDCART {name:<8} {sub} {j + 1:4d} " + " ".join(f"{v:8.1f}" for v in vals))
        lines.append(f"   GRIDCART  {name:<8} END")

        rec_file = tmp_path / "aermap_receptors.out"
        rec_file.write_text("\n".join(lines))

        with patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run", return_value=mock_result):
            result = processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                aermap_exe="/fake/aermap",
                working_dir=str(tmp_path),
                skip_download=True,
                dem_files=["test.tif"],
            )

        updated_grid = result.receptors.cartesian_grids[0]
        assert updated_grid.grid_elevations is not None
        assert len(updated_grid.grid_elevations) == 3
        assert len(updated_grid.grid_elevations[0]) == 3
        # First grid point
        assert updated_grid.grid_elevations[0][0] == 100.0
        assert updated_grid.grid_hills[0][0] == 110.0


# ============================================================================
# Bonus: run_aermap convenience function
# ============================================================================


class TestRunAermapConvenience:
    """Test the run_aermap() convenience function."""

    def test_run_aermap_with_missing_input(self, tmp_path):
        from pyaermod.terrain import AERMAPRunner, run_aermap

        # Mock the executable lookup so it doesn't fail before reaching
        # the missing-input-file check
        with patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run") as mock_run:
            mock_run.return_value = MagicMock(
                success=False, error_message="Input file not found"
            )
            result = run_aermap(tmp_path / "nonexistent.inp")

        assert not result.success
        assert "not found" in result.error_message


# ============================================================================
# Bonus: AERMAPRunner timeout exception
# ============================================================================


class TestAERMAPRunnerTimeout:
    """Test AERMAPRunner handles TimeoutExpired."""

    def test_timeout_returns_failure(self, tmp_path):
        from pyaermod.terrain import AERMAPRunner

        inp = tmp_path / "test.inp"
        inp.write_text("test")

        runner = AERMAPRunner.__new__(AERMAPRunner)
        runner.executable = "/fake/aermap"
        runner.logger = MagicMock()

        with patch("pyaermod.terrain.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd="aermap", timeout=10)):
            result = runner.run(str(inp), working_dir=str(tmp_path), timeout=10)

        assert not result.success
        assert "timed out" in result.error_message.lower()


# ============================================================================
# Area 3A: aermap.py from_aermod_project() coverage gaps
# ============================================================================


class TestAERMAPFromAermodProject:
    """Test AERMAPProject.from_aermod_project() edge cases."""

    def _make_aermod_project(self, sources=None, grids=None, discrete_recs=None):
        """Build a minimal AERMODProject with given sources/receptors."""
        sp = SourcePathway()
        if sources:
            for s in sources:
                sp.add_source(s)
        rp = ReceptorPathway()
        if grids:
            for g in grids:
                rp.add_cartesian_grid(g)
        if discrete_recs:
            for r in discrete_recs:
                rp.add_discrete_receptor(r)
        return AERMODProject(
            control=ControlPathway(title_one="Test"),
            sources=sp,
            receptors=rp,
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )

    def test_point_source_to_aermap(self):
        """PointSource coordinates extracted into AERMAP sources."""
        from pyaermod.aermap import AERMAPProject

        project = self._make_aermod_project(
            sources=[PointSource(
                source_id="STK1", x_coord=500.0, y_coord=600.0,
                emission_rate=1.0,
            )],
            discrete_recs=[DiscreteReceptor(x_coord=550, y_coord=650)],
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert len(aermap.sources) == 1
        assert aermap.sources[0].source_id == "STK1"
        assert aermap.sources[0].x_coord == 500.0

    def test_line_source_uses_start_end(self):
        """LineSource (x_start/x_end) is handled by the hasattr branch."""
        from pyaermod.aermap import AERMAPProject

        project = self._make_aermod_project(
            sources=[LineSource(
                source_id="LN1", x_start=100, y_start=200,
                x_end=300, y_end=400,
                emission_rate=0.001, release_height=2,
                initial_lateral_dimension=5,
            )],
            discrete_recs=[DiscreteReceptor(x_coord=200, y_coord=300)],
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert len(aermap.sources) == 1
        assert aermap.sources[0].x_coord == 100.0

    def test_cartesian_grid_receptor(self):
        """CartesianGrid is carried into AERMAPProject.grids under its own name."""
        from pyaermod.aermap import AERMAPProject

        grid = CartesianGrid(x_init=-500, x_num=11, x_delta=100,
                             y_init=-500, y_num=11, y_delta=100)
        project = self._make_aermod_project(
            sources=[PointSource(source_id="S1", x_coord=0, y_coord=0,
                                 emission_rate=1.0)],
            grids=[grid],
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert aermap.grid_receptor is False
        (written,) = aermap.grids
        assert (written.grid_name, written.x_init, written.x_num, written.x_delta) == (grid.grid_name, -500, 11, 100)

    def test_discrete_receptors_to_aermap(self):
        """Discrete receptors get sequential IDs R0001, R0002, ..."""
        from pyaermod.aermap import AERMAPProject

        recs = [
            DiscreteReceptor(x_coord=100, y_coord=200),
            DiscreteReceptor(x_coord=300, y_coord=400),
        ]
        project = self._make_aermod_project(
            sources=[PointSource(source_id="S1", x_coord=0, y_coord=0,
                                 emission_rate=1.0)],
            discrete_recs=recs,
        )
        aermap = AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])
        assert len(aermap.receptors) == 2
        assert aermap.receptors[0].receptor_id == "R0001"
        assert aermap.receptors[1].receptor_id == "R0002"
        assert aermap.receptors[1].x_coord == 300.0

    def test_empty_project_raises_value_error(self):
        """No sources or receptors → ValueError."""
        from pyaermod.aermap import AERMAPProject

        project = self._make_aermod_project()
        with pytest.raises(ValueError, match="No source or receptor coordinates"):
            AERMAPProject.from_aermod_project(project, dem_files=["dem.tif"])


# ============================================================================
# Area 3B: advanced_viz.py import guard tests
# ============================================================================


class TestAdvancedVizImportGuards:
    """Test that AdvancedVisualizer methods raise ImportError when matplotlib unavailable."""

    def test_plot_3d_surface_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_3d_surface(
                    pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_wind_rose_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_wind_rose(
                    np.array([1.0]), np.array([0.0])
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_concentration_profile_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_concentration_profile(
                    pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_time_series_animation_requires_matplotlib(self):
        import pyaermod.advanced_viz as adv_viz
        original = adv_viz.HAS_MATPLOTLIB
        try:
            adv_viz.HAS_MATPLOTLIB = False
            with pytest.raises(ImportError, match="matplotlib"):
                adv_viz.AdvancedVisualizer.plot_time_series_animation(
                    [pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})],
                    ["t0"],
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = original

    def test_plot_time_series_animation_requires_animation(self):
        """If matplotlib exists but animation does not, separate ImportError."""
        import pyaermod.advanced_viz as adv_viz
        orig_mpl = adv_viz.HAS_MATPLOTLIB
        orig_anim = adv_viz.HAS_ANIMATION
        try:
            adv_viz.HAS_MATPLOTLIB = True
            adv_viz.HAS_ANIMATION = False
            with pytest.raises(ImportError, match="animation"):
                adv_viz.AdvancedVisualizer.plot_time_series_animation(
                    [pd.DataFrame({"X": [0], "Y": [0], "CONC": [1.0]})],
                    ["t0"],
                )
        finally:
            adv_viz.HAS_MATPLOTLIB = orig_mpl
            adv_viz.HAS_ANIMATION = orig_anim


# ============================================================================
# Area 3C: geospatial.py cubic NaN fallback
# ============================================================================


class TestGeospatialCubicFallback:
    """Test cubic interpolation NaN fallback in generate_contours()."""

    def _make_contour_generator(self):
        """Create a ContourGenerator with a mock transformer."""
        import pyproj

        from pyaermod.geospatial import ContourGenerator

        mock_transformer = MagicMock()
        mock_transformer.utm_crs = pyproj.CRS(proj="utm", zone=16, datum="WGS84")
        # Bypass __init__ checks by constructing directly
        gen = ContourGenerator.__new__(ContourGenerator)
        gen.transformer = mock_transformer
        return gen

    def test_cubic_nan_fallback_to_linear(self):
        """When cubic produces >30% NaN, method falls back to linear."""
        scipy = pytest.importorskip("scipy")
        pytest.importorskip("geopandas")

        gen = self._make_contour_generator()

        df = pd.DataFrame({
            "x": [0, 100, 200, 0, 100, 200, 0, 100, 200],
            "y": [0, 0, 0, 100, 100, 100, 200, 200, 200],
            "concentration": [1.0, 5.0, 2.0, 3.0, 10.0, 4.0, 1.5, 6.0, 2.5],
        })

        call_count = {"n": 0}
        original_griddata = scipy.interpolate.griddata

        def mock_griddata(points, values, grid, method="linear"):
            call_count["n"] += 1
            if method == "cubic" and call_count["n"] == 1:
                # Return mostly NaN to trigger fallback
                result = np.full(grid[0].shape, np.nan)
                result[0, 0] = 1.0  # Only 1 valid value out of many
                return result
            return original_griddata(points, values, grid, method=method)

        with patch("pyaermod.geospatial.griddata", side_effect=mock_griddata):
            result = gen.generate_contours(
                df, value_col="concentration",
                method="cubic", grid_resolution=50,
            )

        # If fallback occurred, griddata was called at least twice
        assert call_count["n"] >= 2

    def test_contour_codes_none_path(self):
        """Contour path with codes=None still generates contours."""
        pytest.importorskip("scipy")
        geopandas = pytest.importorskip("geopandas")

        gen = self._make_contour_generator()

        # Simple regular grid that should produce clean contours
        x = np.linspace(0, 100, 10)
        y = np.linspace(0, 100, 10)
        xx, yy = np.meshgrid(x, y)
        df = pd.DataFrame({
            "x": xx.ravel(),
            "y": yy.ravel(),
            "concentration": (xx**2 + yy**2).ravel() / 1000,
        })

        result = gen.generate_contours(
            df, value_col="concentration",
            method="linear", grid_resolution=50,
        )
        assert isinstance(result, geopandas.GeoDataFrame)
        assert len(result) > 0


# ============================================================================
# Item 2A: AreaSource/VolumeSource set_building_from_bpip
# ============================================================================


class TestAreaVolumeSourceBPIP:
    """Test set_building_from_bpip for AreaSource and VolumeSource."""

    def _make_building(self):
        from pyaermod.bpip import Building
        return Building(
            "BLDG1",
            [(-20, -15), (20, -15), (20, 15), (-20, 15)],
            height=25.0,
        )

    def test_area_source_set_building_from_bpip(self):
        """AreaSource.set_building_from_bpip populates all 36-value arrays."""
        bldg = self._make_building()
        src = AreaSource(
            source_id="AS1", x_coord=0, y_coord=0,
            initial_lateral_dimension=25, initial_vertical_dimension=50,
            emission_rate=0.001,
        )
        src.set_building_from_bpip(bldg)

        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36
        assert len(src.building_width) == 36
        assert len(src.building_length) == 36
        assert len(src.building_x_offset) == 36
        assert len(src.building_y_offset) == 36

        output = src.to_aermod_input()
        assert output.count("BUILDHGT") == 4
        assert output.count("BUILDWID") == 4

    def test_volume_source_set_building_from_bpip(self):
        """VolumeSource.set_building_from_bpip populates all 36-value arrays."""
        bldg = self._make_building()
        src = VolumeSource(
            source_id="VS1", x_coord=0, y_coord=0,
            release_height=5, initial_lateral_dimension=10,
            initial_vertical_dimension=5, emission_rate=0.001,
        )
        src.set_building_from_bpip(bldg)

        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36
        assert len(src.building_width) == 36

        output = src.to_aermod_input()
        assert output.count("BUILDHGT") == 4
        assert output.count("XBADJ") == 4


# ============================================================================
# Item 2B: MeteorologyPathway WDROTATE
# ============================================================================


class TestMeteorologyFeatures:
    """Test optional MeteorologyPathway features."""

    def test_wind_rotation_output(self):
        """wind_rotation=15.5 produces WDROTATE keyword."""
        met = MeteorologyPathway(
            surface_file="t.sfc", profile_file="t.pfl",
            wind_rotation=15.5,
        )
        output = met.to_aermod_input()
        assert "WDROTATE  15.50" in output

    def test_wind_rotation_none_omits_keyword(self):
        """wind_rotation=None omits WDROTATE keyword."""
        met = MeteorologyPathway(
            surface_file="t.sfc", profile_file="t.pfl",
        )
        output = met.to_aermod_input()
        assert "WDROTATE" not in output


# ============================================================================
# Item 2C: OutputPathway DAYTABLE / MAXIFILE
# ============================================================================


class TestOutputPathwayFeatures:
    """Test optional OutputPathway features (day_table, max_file)."""

    def test_day_table_output(self):
        """day_table=True produces DAYTABLE keyword."""
        out = OutputPathway(day_table=True)
        output = out.to_aermod_input()
        assert "DAYTABLE  ALLAVE" in output

    def test_maxi_file_output(self):
        """maxi_files produce the four-field MAXIFILE line (ouset.f OUMXFL)."""
        from pyaermod.input_generator import MaxiFile
        out = OutputPathway(maxi_files=[MaxiFile("24", "ALL", 30.0, "maxconc.out")])
        output = out.to_aermod_input()
        assert "MAXIFILE  24  ALL  30  maxconc.out" in output

    def test_output_defaults_omit_optional(self):
        """Default OutputPathway omits DAYTABLE and MAXIFILE."""
        out = OutputPathway()
        output = out.to_aermod_input()
        assert "DAYTABLE" not in output
        assert "MAXIFILE" not in output
