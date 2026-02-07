"""
Unit tests for PyAERMOD BPIP module

Tests building geometry, BPIP calculations, and output formatting.
"""

import math
import pytest
from pyaermod_bpip import Building, BPIPCalculator, BPIPResult
from pyaermod_input_generator import PointSource


# ---------------------------------------------------------------------------
# Building dataclass tests
# ---------------------------------------------------------------------------

class TestBuilding:
    """Test Building geometry dataclass"""

    def test_valid_building(self):
        """Test creating a valid rectangular building"""
        bldg = Building(
            building_id="BLDG1",
            corners=[(0, 0), (40, 0), (40, 30), (0, 30)],
            height=25.0,
        )
        assert bldg.building_id == "BLDG1"
        assert bldg.height == 25.0
        assert len(bldg.corners) == 4

    def test_wrong_corner_count(self):
        """Test that non-4 corners raises ValueError"""
        with pytest.raises(ValueError, match="exactly 4 corners"):
            Building("B1", corners=[(0, 0), (10, 0), (10, 10)], height=10.0)

    def test_five_corners(self):
        """Test that 5 corners raises ValueError"""
        with pytest.raises(ValueError, match="exactly 4 corners"):
            Building(
                "B1",
                corners=[(0, 0), (10, 0), (10, 10), (5, 15), (0, 10)],
                height=10.0,
            )

    def test_negative_height(self):
        """Test that negative height raises ValueError"""
        with pytest.raises(ValueError, match="positive"):
            Building("B1", corners=[(0, 0), (10, 0), (10, 10), (0, 10)], height=-5.0)

    def test_zero_height(self):
        """Test that zero height raises ValueError"""
        with pytest.raises(ValueError, match="positive"):
            Building("B1", corners=[(0, 0), (10, 0), (10, 10), (0, 10)], height=0.0)

    def test_bad_tier_height(self):
        """Test that tier height <= base height raises ValueError"""
        with pytest.raises(ValueError, match="must exceed base height"):
            Building(
                "B1",
                corners=[(0, 0), (10, 0), (10, 10), (0, 10)],
                height=25.0,
                tiers=[(20.0, 0.5)],  # 20 < 25 → invalid
            )

    def test_bad_tier_fraction(self):
        """Test that tier fraction outside (0, 1] raises ValueError"""
        with pytest.raises(ValueError, match="Coverage fraction"):
            Building(
                "B1",
                corners=[(0, 0), (10, 0), (10, 10), (0, 10)],
                height=10.0,
                tiers=[(20.0, 0.0)],  # 0.0 is out of range
            )

        with pytest.raises(ValueError, match="Coverage fraction"):
            Building(
                "B1",
                corners=[(0, 0), (10, 0), (10, 10), (0, 10)],
                height=10.0,
                tiers=[(20.0, 1.5)],  # > 1.0 is out of range
            )


class TestBuildingEffectiveHeight:
    """Test effective height calculations"""

    def test_single_tier(self):
        """Single-tier building returns base height"""
        bldg = Building("B1", [(0, 0), (10, 0), (10, 10), (0, 10)], height=25.0)
        assert bldg.get_effective_height() == 25.0

    def test_no_tiers_explicit_none(self):
        """Explicit None tiers returns base height"""
        bldg = Building(
            "B1", [(0, 0), (10, 0), (10, 10), (0, 10)],
            height=25.0, tiers=None,
        )
        assert bldg.get_effective_height() == 25.0

    def test_multi_tier_weighted(self):
        """Multi-tier returns weighted average"""
        bldg = Building(
            "B1",
            [(0, 0), (10, 0), (10, 10), (0, 10)],
            height=20.0,
            tiers=[(30.0, 0.5)],  # 50% at 30m, 50% at 20m
        )
        expected = 20.0 * 0.5 + 30.0 * 0.5  # = 25.0
        assert bldg.get_effective_height() == pytest.approx(expected)

    def test_multi_tier_two_tiers(self):
        """Two tiers with different coverages"""
        bldg = Building(
            "B1",
            [(0, 0), (10, 0), (10, 10), (0, 10)],
            height=10.0,
            tiers=[(20.0, 0.3), (30.0, 0.2)],
            # base: 50% at 10m, tier1: 30% at 20m, tier2: 20% at 30m
        )
        expected = 10.0 * 0.5 + 20.0 * 0.3 + 30.0 * 0.2  # = 5 + 6 + 6 = 17
        assert bldg.get_effective_height() == pytest.approx(expected)


class TestBuildingFootprintArea:
    """Test footprint area calculations"""

    def test_square_10x10(self):
        """10×10 square = 100 m²"""
        bldg = Building("B1", [(0, 0), (10, 0), (10, 10), (0, 10)], height=10.0)
        assert bldg.get_footprint_area() == pytest.approx(100.0)

    def test_rectangle_10x20(self):
        """10×20 rectangle = 200 m²"""
        bldg = Building("B1", [(0, 0), (20, 0), (20, 10), (0, 10)], height=10.0)
        assert bldg.get_footprint_area() == pytest.approx(200.0)

    def test_offset_rectangle(self):
        """Rectangle not at origin"""
        bldg = Building(
            "B1", [(100, 200), (140, 200), (140, 230), (100, 230)], height=10.0
        )
        assert bldg.get_footprint_area() == pytest.approx(40.0 * 30.0)


class TestBuildingCentroid:
    """Test centroid calculations"""

    def test_origin_centered_square(self):
        """Square centered at origin"""
        bldg = Building(
            "B1", [(-5, -5), (5, -5), (5, 5), (-5, 5)], height=10.0
        )
        cx, cy = bldg.get_centroid()
        assert cx == pytest.approx(0.0)
        assert cy == pytest.approx(0.0)

    def test_offset_square(self):
        """Square at offset location"""
        bldg = Building(
            "B1", [(10, 20), (20, 20), (20, 30), (10, 30)], height=10.0
        )
        cx, cy = bldg.get_centroid()
        assert cx == pytest.approx(15.0)
        assert cy == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# BPIPCalculator tests
# ---------------------------------------------------------------------------

class TestBPIPCalculatorRotation:
    """Test the rotation helper"""

    def test_rotate_x_axis_90(self):
        """(1, 0) rotated 90° CCW → (0, 1)"""
        xr, yr = BPIPCalculator._rotate_point(1.0, 0.0, math.radians(90))
        assert xr == pytest.approx(0.0, abs=1e-10)
        assert yr == pytest.approx(1.0, abs=1e-10)

    def test_rotate_y_axis_90(self):
        """(0, 1) rotated 90° CCW → (-1, 0)"""
        xr, yr = BPIPCalculator._rotate_point(0.0, 1.0, math.radians(90))
        assert xr == pytest.approx(-1.0, abs=1e-10)
        assert yr == pytest.approx(0.0, abs=1e-10)

    def test_rotate_360(self):
        """Full rotation returns to same point"""
        xr, yr = BPIPCalculator._rotate_point(3.0, 4.0, math.radians(360))
        assert xr == pytest.approx(3.0, abs=1e-10)
        assert yr == pytest.approx(4.0, abs=1e-10)

    def test_rotate_zero(self):
        """Zero rotation leaves point unchanged"""
        xr, yr = BPIPCalculator._rotate_point(5.0, 7.0, 0.0)
        assert xr == pytest.approx(5.0)
        assert yr == pytest.approx(7.0)


class TestBPIPCalculatorResults:
    """Test BPIP calculation results"""

    def test_result_has_36_values(self):
        """All result arrays have exactly 36 values"""
        bldg = Building("B1", [(0, 0), (40, 0), (40, 30), (0, 30)], height=25.0)
        calc = BPIPCalculator(bldg, stack_x=20.0, stack_y=15.0)
        result = calc.calculate_all()

        assert len(result.buildhgt) == 36
        assert len(result.buildwid) == 36
        assert len(result.buildlen) == 36
        assert len(result.xbadj) == 36
        assert len(result.ybadj) == 36

    def test_single_tier_constant_height(self):
        """Single-tier building: all 36 heights should be equal"""
        bldg = Building("B1", [(0, 0), (40, 0), (40, 30), (0, 30)], height=25.0)
        calc = BPIPCalculator(bldg, stack_x=20.0, stack_y=15.0)
        result = calc.calculate_all()

        for h in result.buildhgt:
            assert h == pytest.approx(25.0)

    def test_symmetric_building_centered_on_stack(self):
        """Square building centered on stack: XBADJ/YBADJ ≈ 0 for all directions"""
        bldg = Building(
            "B1",
            [(-10, -10), (10, -10), (10, 10), (-10, 10)],
            height=20.0,
        )
        calc = BPIPCalculator(bldg, stack_x=0.0, stack_y=0.0)
        result = calc.calculate_all()

        for xb in result.xbadj:
            assert xb == pytest.approx(0.0, abs=1e-6)
        for yb in result.ybadj:
            assert yb == pytest.approx(0.0, abs=1e-6)

    def test_square_building_width_equals_length(self):
        """Square building: width ≈ length for all directions"""
        bldg = Building(
            "B1",
            [(-15, -15), (15, -15), (15, 15), (-15, 15)],
            height=20.0,
        )
        calc = BPIPCalculator(bldg, stack_x=0.0, stack_y=0.0)
        result = calc.calculate_all()

        for w, l in zip(result.buildwid, result.buildlen):
            # For a square, projections at 45° are larger but equal
            assert w == pytest.approx(l, abs=1e-6)

    def test_rectangular_building_known_geometry(self):
        """
        40×30 building aligned with axes, stack at center.
        North wind (360°): width=40 (E-W extent), length=30 (N-S extent)
        East wind (90°): width=30, length=40
        """
        bldg = Building(
            "B1",
            [(-20, -15), (20, -15), (20, 15), (-20, 15)],
            height=25.0,
        )
        calc = BPIPCalculator(bldg, stack_x=0.0, stack_y=0.0)
        result = calc.calculate_all()

        # Index 35 = 360° = north wind
        # In the rotated frame, wind along +Y: width = X-extent, length = Y-extent
        # For north wind, rotation by -360° ≈ no rotation
        # X-extent of building: -20 to 20 = 40
        # Y-extent of building: -15 to 15 = 30
        assert result.buildwid[35] == pytest.approx(40.0, abs=0.5)
        assert result.buildlen[35] == pytest.approx(30.0, abs=0.5)

        # Index 8 = 90° = east wind
        # Rotation by -90°: x'=y, y'=-x (approx)
        # Original corners rotated: X-extent becomes Y, Y-extent becomes X
        assert result.buildwid[8] == pytest.approx(30.0, abs=0.5)
        assert result.buildlen[8] == pytest.approx(40.0, abs=0.5)

    def test_positive_width_and_length(self):
        """All widths and lengths should be positive"""
        bldg = Building(
            "B1",
            [(100, 200), (140, 200), (140, 230), (100, 230)],
            height=15.0,
        )
        calc = BPIPCalculator(bldg, stack_x=120.0, stack_y=215.0)
        result = calc.calculate_all()

        for w in result.buildwid:
            assert w > 0
        for l in result.buildlen:
            assert l > 0

    def test_offset_building(self):
        """Building not centered on stack produces non-zero offsets"""
        bldg = Building(
            "B1",
            [(50, 50), (80, 50), (80, 70), (50, 70)],
            height=20.0,
        )
        calc = BPIPCalculator(bldg, stack_x=0.0, stack_y=0.0)
        result = calc.calculate_all()

        # At least some XBADJ/YBADJ values should be non-zero
        assert any(abs(x) > 1.0 for x in result.xbadj)
        assert any(abs(y) > 1.0 for y in result.ybadj)


# ---------------------------------------------------------------------------
# PointSource formatting tests
# ---------------------------------------------------------------------------

class TestPointSourceBuildingFormatting:
    """Test PointSource building keyword formatting"""

    def test_scalar_building_single_line(self):
        """Scalar building params produce single output lines"""
        src = PointSource(
            source_id="STK1",
            x_coord=0.0, y_coord=0.0,
            building_height=25.0,
            building_width=40.0,
            building_length=30.0,
            building_x_offset=5.0,
            building_y_offset=-3.0,
        )
        output = src.to_aermod_input()

        assert "BUILDHGT" in output
        assert "BUILDWID" in output
        assert "BUILDLEN" in output
        assert "XBADJ" in output
        assert "YBADJ" in output

        # Each keyword should appear exactly once for scalar values
        assert output.count("BUILDHGT") == 1
        assert output.count("BUILDWID") == 1

    def test_36_value_multiline(self):
        """36-value arrays produce 4 continuation lines (10+10+10+6)"""
        values_36 = [25.0 + i * 0.1 for i in range(36)]
        src = PointSource(
            source_id="STK1",
            x_coord=0.0, y_coord=0.0,
            building_height=values_36,
        )
        output = src.to_aermod_input()

        # BUILDHGT should appear 4 times (4 continuation lines)
        assert output.count("BUILDHGT") == 4

    def test_wrong_list_length_raises(self):
        """List with length ≠ 36 raises ValueError"""
        bad_values = [25.0] * 10
        src = PointSource(
            source_id="STK1",
            x_coord=0.0, y_coord=0.0,
            building_height=bad_values,
        )
        with pytest.raises(ValueError, match="exactly 36 values"):
            src.to_aermod_input()

    def test_backward_compat_no_building(self):
        """PointSource without building params still works"""
        src = PointSource(
            source_id="STK1",
            x_coord=100.0, y_coord=200.0,
            stack_height=50.0,
            emission_rate=1.5,
        )
        output = src.to_aermod_input()

        assert "BUILDHGT" not in output
        assert "BUILDWID" not in output
        assert "STK1" in output
        assert "POINT" in output

    def test_set_building_from_bpip(self):
        """set_building_from_bpip populates all 36-value arrays"""
        bldg = Building(
            "BLDG1",
            [(-20, -15), (20, -15), (20, 15), (-20, 15)],
            height=25.0,
        )
        src = PointSource(
            source_id="STK1",
            x_coord=0.0, y_coord=0.0,
            stack_height=50.0,
        )
        src.set_building_from_bpip(bldg)

        assert isinstance(src.building_height, list)
        assert len(src.building_height) == 36
        assert isinstance(src.building_width, list)
        assert len(src.building_width) == 36
        assert isinstance(src.building_length, list)
        assert len(src.building_length) == 36
        assert isinstance(src.building_x_offset, list)
        assert len(src.building_x_offset) == 36
        assert isinstance(src.building_y_offset, list)
        assert len(src.building_y_offset) == 36

        # Should produce valid AERMOD input
        output = src.to_aermod_input()
        assert output.count("BUILDHGT") == 4
        assert output.count("BUILDWID") == 4
        assert output.count("BUILDLEN") == 4
        assert output.count("XBADJ") == 4
        assert output.count("YBADJ") == 4


# ---------------------------------------------------------------------------
# BPIPResult tests
# ---------------------------------------------------------------------------

class TestBPIPResult:
    """Test BPIPResult dataclass"""

    def test_empty_result(self):
        """Empty result has empty lists"""
        r = BPIPResult()
        assert r.buildhgt == []
        assert r.buildwid == []
        assert r.buildlen == []
        assert r.xbadj == []
        assert r.ybadj == []

    def test_populated_result(self):
        """Populated result stores values"""
        r = BPIPResult(
            buildhgt=[25.0] * 36,
            buildwid=[40.0] * 36,
            buildlen=[30.0] * 36,
            xbadj=[0.0] * 36,
            ybadj=[0.0] * 36,
        )
        assert len(r.buildhgt) == 36
        assert r.buildhgt[0] == 25.0
        assert r.buildwid[0] == 40.0
