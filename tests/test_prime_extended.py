"""Extended PRIME tests: per-direction GEP + AREA/VOLUME support.

These tests verify two fixes from the v1.5 superreview:

1. gep_from_building now computes the per-direction GEP and maximizes
   over wind sectors (EPA 40 CFR 51.100(ii) correct formulation) rather
   than taking max projected width once.

2. assess_source_downwash / apply_bpip_to_project / suggest_downwash_config
   now accept AreaSource and VolumeSource in addition to PointSource
   — matching AERMOD's own downwash support for those source types.
"""

from __future__ import annotations

import pytest

from pyaermod import (
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
    VolumeSource,
)
from pyaermod.bpip import Building
from pyaermod.prime import (
    GEP_FLOOR_M,
    apply_bpip_to_project,
    assess_source_downwash,
    gep_from_building,
    suggest_downwash_config,
)


def _rectangular_building(height: float, half_len_x: float, half_len_y: float,
                          bid: str = "B1") -> Building:
    """Building with centroid at origin. Projected width varies by
    direction: narrow at 0° and 180° (end-on), wide at 90° and 270°
    (broadside)."""
    return Building(
        building_id=bid,
        corners=[
            (-half_len_x, -half_len_y),
            (half_len_x, -half_len_y),
            (half_len_x, half_len_y),
            (-half_len_x, half_len_y),
        ],
        height=height,
    )


def _tiny_project(sources) -> AERMODProject:
    return AERMODProject(
        control=ControlPathway(
            title_one="test", pollutant_id=PollutantType.SO2,
            averaging_periods=["ANNUAL"],
        ),
        sources=SourcePathway(sources=sources),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(
            surface_file="a.sfc", profile_file="a.pfl",
        ),
        output=OutputPathway(),
    )


# ---------------------------------------------------------------------------
# Per-direction GEP calculation
# ---------------------------------------------------------------------------

class TestGEPPerDirection:
    def test_gep_uses_max_per_direction(self):
        """For a rectangular building wider than tall (20x100 m), the
        GEP must reflect the wide-direction contribution, not average."""
        bldg = _rectangular_building(height=30.0, half_len_x=50.0,
                                     half_len_y=10.0)
        gep = gep_from_building(bldg, stack_x=0.0, stack_y=0.0)
        # Height = 30, max projected width ≈ 100 (broadside); L ≈ 30
        # (lesser). GEP = max(65, 30 + 1.5 × 30) = 75.
        # The per-direction-maximum must be at least this value.
        assert gep >= 75.0

    def test_gep_above_floor_when_building_large(self):
        """Tall + wide building must produce GEP > 65 m floor."""
        bldg = _rectangular_building(height=50.0, half_len_x=40.0,
                                     half_len_y=40.0)
        gep = gep_from_building(bldg, stack_x=0.0, stack_y=0.0)
        # height 50, lesser(50, ~80) = 50, GEP = 50 + 75 = 125
        assert gep > GEP_FLOOR_M
        assert gep >= 100.0

    def test_gep_returns_floor_for_tiny_building(self):
        bldg = _rectangular_building(height=5.0, half_len_x=2.0,
                                     half_len_y=2.0)
        gep = gep_from_building(bldg, stack_x=0.0, stack_y=0.0)
        assert gep == GEP_FLOOR_M


# ---------------------------------------------------------------------------
# AREA source downwash
# ---------------------------------------------------------------------------

class TestAreaSourceDownwash:
    def _area(self, release_height: float = 2.0) -> AreaSource:
        return AreaSource(
            source_id="A1", x_coord=0.0, y_coord=0.0,
            emission_rate=0.001,
            release_height=release_height,
            initial_lateral_dimension=50.0,
            initial_vertical_dimension=50.0,
        )

    def test_assess_downwash_accepts_area_source(self):
        """assess_source_downwash must not raise on an AreaSource."""
        bldg = _rectangular_building(height=20.0, half_len_x=30.0, half_len_y=30.0)
        assessment = assess_source_downwash(self._area(), [bldg])
        assert assessment.source_id == "A1"
        # release height 2 m is well below any plausible GEP
        assert assessment.is_below_gep is True

    def test_apply_bpip_populates_area_source_arrays(self):
        bldg = _rectangular_building(height=20.0, half_len_x=30.0, half_len_y=30.0)
        project = _tiny_project([self._area(release_height=2.0)])
        apply_bpip_to_project(project, [bldg])
        src = project.sources.sources[0]
        # Area source now has 36-value building arrays
        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36

    def test_suggest_downwash_flags_area_source(self):
        """suggest_downwash_config must surface AreaSources that need
        building data, not just PointSources."""
        bldg = _rectangular_building(height=30.0, half_len_x=50.0, half_len_y=50.0)
        project = _tiny_project([self._area(release_height=2.0)])
        warnings = suggest_downwash_config(project, [bldg])
        # Should flag "below GEP, no data"
        assert any("A1" in w and "below GEP" in w for w in warnings)


# ---------------------------------------------------------------------------
# VOLUME source downwash
# ---------------------------------------------------------------------------

class TestVolumeSourceDownwash:
    def _volume(self, release_height: float = 5.0) -> VolumeSource:
        return VolumeSource(
            source_id="V1", x_coord=0.0, y_coord=0.0,
            emission_rate=1.0,
            release_height=release_height,
            initial_lateral_dimension=10.0,
            initial_vertical_dimension=5.0,
        )

    def test_assess_downwash_accepts_volume_source(self):
        bldg = _rectangular_building(height=15.0, half_len_x=20.0, half_len_y=20.0)
        assessment = assess_source_downwash(self._volume(), [bldg])
        assert assessment.source_id == "V1"

    def test_apply_bpip_populates_volume_source_arrays(self):
        bldg = _rectangular_building(height=30.0, half_len_x=50.0, half_len_y=50.0)
        project = _tiny_project([self._volume(release_height=5.0)])
        apply_bpip_to_project(project, [bldg])
        src = project.sources.sources[0]
        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36


# ---------------------------------------------------------------------------
# Mixed project with all three types
# ---------------------------------------------------------------------------

class TestMixedProject:
    def test_all_three_source_types_get_bpip_arrays(self):
        bldg = _rectangular_building(height=25.0, half_len_x=30.0, half_len_y=30.0)
        point = PointSource(
            source_id="P1", x_coord=10.0, y_coord=0.0,
            stack_height=10.0, stack_temp=450.0,
            exit_velocity=10.0, stack_diameter=2.0,
            emission_rate=1.0,
        )
        area = AreaSource(
            source_id="A1", x_coord=0.0, y_coord=20.0,
            emission_rate=0.001, release_height=3.0,
            initial_lateral_dimension=10.0,
            initial_vertical_dimension=10.0,
        )
        vol = VolumeSource(
            source_id="V1", x_coord=-20.0, y_coord=0.0,
            emission_rate=1.0, release_height=5.0,
            initial_lateral_dimension=5.0,
            initial_vertical_dimension=3.0,
        )
        project = _tiny_project([point, area, vol])
        apply_bpip_to_project(project, [bldg])

        for src in project.sources.sources:
            assert isinstance(src.building_height, list), (
                f"{src.source_id} didn't get building_height populated"
            )
            assert len(src.building_height) == 36
