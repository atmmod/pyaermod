"""
Unit tests for pyaermod_terrain module.

Tests DEM downloading (mocked), AERMAP runner, AERMAP output parsing,
and terrain processor pipeline logic.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from pyaermod.input_generator import (
    AERMODProject,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    RLineExtSource,
    SourcePathway,
)
from pyaermod.terrain import (
    AERMAPOutputParser,
    AERMAPRunner,
    AERMAPRunResult,
    DEMDownloader,
    DEMTileInfo,
    TerrainProcessor,
    run_aermap,
)

# ============================================================================
# TestDEMTileInfo
# ============================================================================


class TestDEMTileInfo:

    def test_basic_creation(self):
        tile = DEMTileInfo(
            title="Test Tile",
            download_url="https://example.com/dem.tif",
        )
        assert tile.title == "Test Tile"
        assert tile.download_url == "https://example.com/dem.tif"
        assert tile.format == "GeoTIFF"
        assert tile.size_bytes is None
        assert tile.bounds is None

    def test_full_creation(self):
        tile = DEMTileInfo(
            title="NED 1/3 n41w088",
            download_url="https://prd-tnm.s3.amazonaws.com/n41w088.tif",
            format="GeoTIFF",
            size_bytes=15000000,
            bounds=(-88.0, 40.0, -87.0, 41.0),
        )
        assert tile.size_bytes == 15000000
        assert tile.bounds[0] == -88.0


# ============================================================================
# TestDEMDownloader (mocked requests)
# ============================================================================


class TestDEMDownloader:

    @pytest.fixture
    def mock_requests(self):
        """Mock requests module for DEMDownloader."""
        with patch("pyaermod.terrain.requests") as mock_req, patch("pyaermod.terrain.HAS_REQUESTS", True):
            yield mock_req

    def test_find_tiles_returns_list(self, mock_requests, tmp_path):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Tile 1",
                    "downloadURL": "https://example.com/tile1.tif",
                    "format": "GeoTIFF",
                    "sizeInBytes": 10000000,
                },
                {
                    "title": "Tile 2",
                    "downloadURL": "https://example.com/tile2.tif",
                    "format": "GeoTIFF",
                    "sizeInBytes": 12000000,
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        downloader = DEMDownloader(cache_dir=tmp_path / "cache")
        tiles = downloader.find_tiles((-88.0, 40.0, -87.0, 41.0))

        assert len(tiles) == 2
        assert tiles[0].title == "Tile 1"
        assert tiles[1].download_url == "https://example.com/tile2.tif"

    def test_find_tiles_empty_response(self, mock_requests, tmp_path):
        mock_response = MagicMock()
        mock_response.json.return_value = {"items": []}
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        downloader = DEMDownloader(cache_dir=tmp_path / "cache")
        tiles = downloader.find_tiles((-88.0, 40.0, -87.0, 41.0))
        assert len(tiles) == 0

    def test_find_tiles_skips_no_url(self, mock_requests, tmp_path):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {"title": "No URL", "downloadURL": "", "format": "GeoTIFF"},
                {"title": "Has URL", "downloadURL": "https://example.com/tile.tif"},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        downloader = DEMDownloader(cache_dir=tmp_path / "cache")
        tiles = downloader.find_tiles((-88.0, 40.0, -87.0, 41.0))
        assert len(tiles) == 1
        assert tiles[0].title == "Has URL"

    def test_download_tile_uses_cache(self, mock_requests, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cached_file = cache_dir / "tile.tif"
        cached_file.write_bytes(b"cached data")

        tile = DEMTileInfo("Test", "https://example.com/tile.tif")
        downloader = DEMDownloader(cache_dir=cache_dir)
        result = downloader.download_tile(tile)

        assert result == cached_file
        mock_requests.get.assert_not_called()

    def test_download_tile_fresh(self, mock_requests, tmp_path):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"fake DEM data"]
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        tile = DEMTileInfo("Test", "https://example.com/new_tile.tif")
        downloader = DEMDownloader(cache_dir=tmp_path / "cache")
        result = downloader.download_tile(tile)

        assert result.exists()
        assert result.name == "new_tile.tif"

    def test_download_dem_pipeline(self, mock_requests, tmp_path):
        # find_tiles response
        find_response = MagicMock()
        find_response.json.return_value = {
            "items": [
                {"title": "T1", "downloadURL": "https://example.com/t1.tif", "format": "GeoTIFF"},
            ]
        }
        find_response.raise_for_status = MagicMock()

        # download response
        dl_response = MagicMock()
        dl_response.iter_content.return_value = [b"data"]
        dl_response.raise_for_status = MagicMock()

        mock_requests.get.side_effect = [find_response, dl_response]

        downloader = DEMDownloader(cache_dir=tmp_path / "cache")
        paths = downloader.download_dem((-88.0, 40.0, -87.0, 41.0), tmp_path / "output")

        assert len(paths) == 1
        assert paths[0].exists()


# ============================================================================
# TestAERMAPRunResult
# ============================================================================


class TestAERMAPRunResult:

    def test_success_repr(self):
        result = AERMAPRunResult(
            success=True, input_file="test.inp",
            return_code=0, runtime_seconds=5.2,
        )
        assert "SUCCESS" in repr(result)
        assert "5.2s" in repr(result)

    def test_failure_repr(self):
        result = AERMAPRunResult(
            success=False, input_file="test.inp",
            error_message="timeout",
        )
        assert "FAILED" in repr(result)


# ============================================================================
# TestAERMAPRunner
# ============================================================================


class TestAERMAPRunner:

    def test_missing_executable_raises(self):
        with pytest.raises(FileNotFoundError, match="AERMAP executable not found"):
            AERMAPRunner(executable_path="/nonexistent/aermap")

    def test_missing_input_file(self, tmp_path):
        # Create a fake executable
        fake_exe = tmp_path / "aermap"
        fake_exe.write_text("#!/bin/sh\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMAPRunner(executable_path=str(fake_exe))
        result = runner.run(str(tmp_path / "nonexistent.inp"))

        assert not result.success
        assert "not found" in result.error_message


# ============================================================================
# TestAERMAPOutputParser
# ============================================================================


class TestAERMAPOutputParser:

    def test_parse_disccart_output(self, tmp_path):
        """Test parsing DISCCART receptor output format."""
        content = """** AERMAP Receptor Output
   DISCCART     500000.00    3800000.00    125.30    130.50
   DISCCART     501000.00    3801000.00    150.20    155.80
   DISCCART     502000.00    3802000.00    175.10    180.00
"""
        output_file = tmp_path / "receptor.out"
        output_file.write_text(content)

        df = AERMAPOutputParser.parse_receptor_output(output_file)
        assert len(df) == 3
        assert list(df.columns) == ["x", "y", "zelev", "zhill"]
        assert df.iloc[0]["x"] == pytest.approx(500000.0)
        assert df.iloc[0]["zelev"] == pytest.approx(125.3)
        assert df.iloc[1]["zhill"] == pytest.approx(155.8)

    def test_parse_gridcart_output(self, tmp_path):
        """Test parsing GRIDCART ELEV/HILL receptor output format."""
        content = """** AERMAP Grid Receptor Output
   GRIDCART  GRID     XYINC    500000.00     3  1000.00    3800000.00     2  1000.00
   GRIDCART  GRID     ELEV  1   100.0   110.0   120.0
   GRIDCART  GRID     ELEV  2   105.0   115.0   125.0
   GRIDCART  GRID     HILL  1   110.0   120.0   130.0
   GRIDCART  GRID     HILL  2   115.0   125.0   135.0
"""
        output_file = tmp_path / "receptor_grid.out"
        output_file.write_text(content)

        df = AERMAPOutputParser.parse_receptor_output(output_file)
        assert len(df) == 6  # 3 cols x 2 rows
        assert df.iloc[0]["x"] == pytest.approx(500000.0)
        assert df.iloc[0]["y"] == pytest.approx(3800000.0)
        assert df.iloc[0]["zelev"] == pytest.approx(100.0)
        assert df.iloc[0]["zhill"] == pytest.approx(110.0)

    def test_parse_source_output(self, tmp_path):
        """Test parsing source output format."""
        content = """** AERMAP Source Output
SO LOCATION  STACK1      POINT      500500.00    3800500.00       125.50
SO LOCATION  AREA1       AREA       501000.00    3801000.00       130.25
"""
        output_file = tmp_path / "source.out"
        output_file.write_text(content)

        df = AERMAPOutputParser.parse_source_output(output_file)
        assert len(df) == 2
        assert df.iloc[0]["source_id"] == "STACK1"
        assert df.iloc[0]["source_type"] == "POINT"
        assert df.iloc[0]["x"] == pytest.approx(500500.0)
        assert df.iloc[0]["zelev"] == pytest.approx(125.5)
        assert df.iloc[1]["source_id"] == "AREA1"

    def test_parse_receptor_missing_file(self):
        with pytest.raises(FileNotFoundError):
            AERMAPOutputParser.parse_receptor_output("/nonexistent/file.out")

    def test_parse_source_missing_file(self):
        with pytest.raises(FileNotFoundError):
            AERMAPOutputParser.parse_source_output("/nonexistent/file.out")

    def test_parse_empty_receptor_output(self, tmp_path):
        output_file = tmp_path / "empty.out"
        output_file.write_text("** Empty output\n")
        df = AERMAPOutputParser.parse_receptor_output(output_file)
        assert len(df) == 0

    def test_parse_receptor_skips_comments(self, tmp_path):
        content = """** Comment line
** Another comment
   DISCCART     500000.00    3800000.00    125.30    130.50
** Final comment
"""
        output_file = tmp_path / "commented.out"
        output_file.write_text(content)

        df = AERMAPOutputParser.parse_receptor_output(output_file)
        assert len(df) == 1


# ============================================================================
# TestTerrainProcessor
# ============================================================================


class TestTerrainProcessor:

    @pytest.fixture
    def simple_aermod_project(self):
        control = ControlPathway(title_one="Terrain Test")
        sources = SourcePathway()
        sources.add_source(PointSource(
            source_id="STK1", x_coord=500000.0, y_coord=3800000.0,
            stack_height=50.0, emission_rate=1.0,
        ))
        receptors = ReceptorPathway(
            cartesian_grids=[CartesianGrid(
                x_init=499000.0, x_num=5, x_delta=500.0,
                y_init=3799000.0, y_num=5, y_delta=500.0,
            )],
            discrete_receptors=[
                DiscreteReceptor(x_coord=500000.0, y_coord=3800000.0),
            ],
        )
        meteorology = MeteorologyPathway(
            surface_file="test.sfc", profile_file="test.pfl",
        )
        output = OutputPathway()
        return AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=meteorology, output=output,
        )

    def test_create_aermap_project_basic(self, simple_aermod_project):
        processor = TerrainProcessor()
        aermap = processor.create_aermap_project_from_aermod(
            simple_aermod_project,
            dem_files=["dem1.tif", "dem2.tif"],
            utm_zone=16,
            datum="NAD83",
        )

        assert aermap.utm_zone == 16
        assert aermap.datum == "NAD83"
        assert len(aermap.dem_files) == 2
        assert len(aermap.sources) == 1
        assert aermap.sources[0].source_id == "STK1"
        assert aermap.grid_receptor is True
        assert len(aermap.receptors) == 1  # 1 discrete

    def test_create_aermap_project_generates_valid_input(self, simple_aermod_project):
        processor = TerrainProcessor()
        aermap = processor.create_aermap_project_from_aermod(
            simple_aermod_project,
            dem_files=["dem.tif"],
        )

        inp = aermap.to_aermap_input()
        assert "CO STARTING" in inp
        assert "RE STARTING" in inp
        assert "SO STARTING" in inp
        assert "GRIDCART" in inp
        assert "dem.tif" in inp

    def test_create_aermap_project_no_coords_raises(self):
        project = AERMODProject(
            control=ControlPathway(title_one="Empty"),
            sources=SourcePathway(),
            receptors=ReceptorPathway(),
            meteorology=MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl"),
            output=OutputPathway(),
        )
        processor = TerrainProcessor()
        with pytest.raises(ValueError, match="No source or receptor"):
            processor.create_aermap_project_from_aermod(
                project, dem_files=["dem.tif"],
            )

    def test_update_receptor_elevations(self, simple_aermod_project):
        import pandas as pd
        processor = TerrainProcessor()

        rec_df = pd.DataFrame({
            "x": [500000.0],
            "y": [3800000.0],
            "zelev": [125.5],
            "zhill": [130.0],
        })
        processor._update_receptor_elevations(simple_aermod_project, rec_df)

        rec = simple_aermod_project.receptors.discrete_receptors[0]
        assert rec.z_elev == pytest.approx(125.5)
        assert rec.z_hill == pytest.approx(130.0)

    def test_update_receptor_elevations_empty_df(self, simple_aermod_project):
        import pandas as pd
        processor = TerrainProcessor()
        empty_df = pd.DataFrame(columns=["x", "y", "zelev", "zhill"])
        # Should not raise
        processor._update_receptor_elevations(simple_aermod_project, empty_df)


# ============================================================================
# TestConvenienceFunction
# ============================================================================


class TestConvenienceFunction:

    def test_run_aermap_missing_exe(self):
        """run_aermap should fail gracefully when no executable exists."""
        with pytest.raises(FileNotFoundError):
            run_aermap("/nonexistent/input.inp")


# ============================================================================
# Coverage expansion tests
# ============================================================================


class TestRequireRequests:
    """Test _require_requests guard function (line 27)."""

    def test_raises_when_requests_missing(self):
        from pyaermod import terrain
        original = terrain.HAS_REQUESTS
        try:
            terrain.HAS_REQUESTS = False
            with pytest.raises(ImportError, match="requests is required"):
                terrain._require_requests()
        finally:
            terrain.HAS_REQUESTS = original


class TestDEMDownloaderEdgeCases:
    """Test download_dem with no tiles found (lines 175-176)."""

    def test_download_dem_no_tiles(self, tmp_path):
        downloader = DEMDownloader(cache_dir=tmp_path / "cache")
        with patch.object(downloader, "find_tiles", return_value=[]):
            result = downloader.download_dem(
                bounds=(-88.0, 40.0, -87.0, 41.0),
                output_dir=tmp_path / "output",
            )
        assert result == []


class TestAERMAPRunnerExceptions:
    """Test AERMAP runner exception paths (lines 313-325)."""

    def test_timeout_exception(self, tmp_path):
        """TimeoutExpired → AERMAPRunResult with error message."""
        input_file = tmp_path / "test.inp"
        input_file.write_text("CO STARTING\nCO FINISHED")

        runner = AERMAPRunner.__new__(AERMAPRunner)
        runner.executable = "/usr/bin/true"
        runner.logger = MagicMock()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
            cmd="aermap", timeout=10
        )):
            result = runner.run(str(input_file), working_dir=str(tmp_path), timeout=10)

        assert result.success is False
        assert "timed out" in result.error_message

    def test_generic_exception(self, tmp_path):
        """Generic OSError → AERMAPRunResult with error message."""
        input_file = tmp_path / "test.inp"
        input_file.write_text("CO STARTING\nCO FINISHED")

        runner = AERMAPRunner.__new__(AERMAPRunner)
        runner.executable = "/usr/bin/true"
        runner.logger = MagicMock()

        with patch("subprocess.run", side_effect=OSError("disk full")):
            result = runner.run(str(input_file), working_dir=str(tmp_path))

        assert result.success is False
        assert "disk full" in result.error_message


class TestAERMAPOutputParserMalformed:
    """Test parser with malformed input lines (lines 391-432, 490-491)."""

    def test_malformed_disccart_line(self, tmp_path):
        """Malformed DISCCART → skip, don't crash (lines 391-392)."""
        content = """** AERMAP Receptor Output
   DISCCART     500000.00    NOT_A_NUMBER    125.30    130.50
   DISCCART     501000.00    3801000.00    150.20    155.80
"""
        output_file = tmp_path / "rec.out"
        output_file.write_text(content)
        df = AERMAPOutputParser.parse_receptor_output(output_file)
        assert len(df) == 1  # Only the valid line
        assert df.iloc[0]["x"] == pytest.approx(501000.0)

    def test_malformed_gridcart_elev(self, tmp_path):
        """Malformed GRIDCART ELEV → skip (lines 405-406)."""
        content = """** AERMAP Receptor Output
   RE GRIDCART  GRD1 XYINC 500000.00 3 100.0 3800000.00 3 100.0
   RE GRIDCART  GRD1 ELEV  ABC 125.0 130.0 135.0
   RE GRIDCART  GRD1 ELEV  2 140.0 145.0 150.0
"""
        output_file = tmp_path / "grid.out"
        output_file.write_text(content)
        df = AERMAPOutputParser.parse_receptor_output(output_file)
        # Row 1 malformed → skipped; row 2 valid with grid y_init + 1*delta
        assert len(df) == 3  # Only row 2's 3 values

    def test_malformed_gridcart_hill(self, tmp_path):
        """Malformed GRIDCART HILL → skip (lines 418-419)."""
        content = """** AERMAP Receptor Output
   RE GRIDCART  GRD1 XYINC 500000.00 2 100.0 3800000.00 2 100.0
   RE GRIDCART  GRD1 ELEV  1 125.0 130.0
   RE GRIDCART  GRD1 ELEV  2 135.0 140.0
   RE GRIDCART  GRD1 HILL  1 126.0 131.0
   RE GRIDCART  GRD1 HILL  BADROW 136.0 141.0
"""
        output_file = tmp_path / "hill.out"
        output_file.write_text(content)
        df = AERMAPOutputParser.parse_receptor_output(output_file)
        assert len(df) == 4  # 2×2 grid
        # Row 1 has hill data, row 2 has defaults (0.0) due to malformed HILL line
        row_1 = df[(abs(df["x"] - 500000.00) < 0.5) & (abs(df["y"] - 3800000.00) < 0.5)]
        if not row_1.empty:
            assert row_1.iloc[0]["zhill"] == pytest.approx(126.0)

    def test_malformed_source_location(self, tmp_path):
        """Malformed SO LOCATION → skip (lines 490-491)."""
        content = """** AERMAP Source Output
SO LOCATION  STK1  POINT  NOT_FLOAT  3800500.00  125.5
SO LOCATION  STK2  POINT  501000.00  3801000.00  130.0
"""
        output_file = tmp_path / "src.out"
        output_file.write_text(content)
        df = AERMAPOutputParser.parse_source_output(output_file)
        assert len(df) == 1  # Only STK2
        assert df.iloc[0]["source_id"] == "STK2"


class TestCreateAermapWithLineSources:
    """Test create_aermap_project_from_aermod with line sources (lines 542-544, 581-582)."""

    def test_rlinext_source_extraction(self):
        """RLineExtSource has x_start/y_start → should be used for AERMAP."""
        control = ControlPathway(title_one="Line Source Test")
        sources = SourcePathway()

        # Add a point source and a RLineExtSource
        point = PointSource(
            source_id="PT1", x_coord=100.0, y_coord=200.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        rlinext = RLineExtSource(
            source_id="RL1", x_start=300.0, y_start=400.0, z_start=5.0,
            x_end=500.0, y_end=600.0, z_end=5.0,
            emission_rate=2.0, road_width=10.0,
        )
        sources.add_source(point)
        sources.add_source(rlinext)

        receptors = ReceptorPathway()
        grid = CartesianGrid(x_init=0.0, x_num=3, x_delta=100.0,
                             y_init=0.0, y_num=3, y_delta=100.0)
        receptors.add_cartesian_grid(grid)

        meteorology = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl")
        output = OutputPathway()

        project = AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=meteorology, output=output,
        )

        processor = TerrainProcessor()
        aermap = processor.create_aermap_project_from_aermod(
            project, dem_files=["dem.tif"], utm_zone=16,
        )

        # Should have 2 AERMAP sources (PT1 and RL1)
        assert len(aermap.sources) == 2
        source_ids = [s.source_id for s in aermap.sources]
        assert "PT1" in source_ids
        assert "RL1" in source_ids


class TestUpdateElevationsEdgeCases:
    """Test elevation update edge cases (lines 745-746, 771-774)."""

    def test_grid_elevations_no_match(self):
        """Grid coords don't match parsed data → default 0.0 (lines 745-746)."""
        control = ControlPathway(title_one="Grid No Match")
        sources = SourcePathway()
        point = PointSource(
            source_id="S1", x_coord=100.0, y_coord=100.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        sources.add_source(point)
        grid = CartesianGrid(x_init=0.0, x_num=2, x_delta=100.0,
                             y_init=0.0, y_num=2, y_delta=100.0)
        receptors = ReceptorPathway(cartesian_grids=[grid])
        met = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl")
        output = OutputPathway()
        project = AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=met, output=output,
        )

        # Parsed data with completely different coordinates
        rec_df = pd.DataFrame([
            {"x": 9999.0, "y": 9999.0, "zelev": 500.0, "zhill": 550.0},
        ])

        processor = TerrainProcessor()
        processor._update_grid_receptor_elevations(project, rec_df)

        # Grid should NOT have elevations set (no match → has_data stays False)
        assert not hasattr(grid, "grid_elevations") or grid.grid_elevations is None

    def test_source_elevations_buoyline(self):
        """BuoyLineSource elevation update via segments (lines 771-774)."""
        control = ControlPathway(title_one="Buoy Test")
        sources = SourcePathway()
        seg = BuoyLineSegment(
            source_id="BL1SEG1",
            x_start=100.0, y_start=200.0,
            x_end=300.0, y_end=400.0,
            emission_rate=1.0,
        )
        buoy = BuoyLineSource(
            source_id="BLINE1",
            base_elevation=0.0,
            avg_buoyancy_parameter=0.5,
            avg_line_length=200.0,
            avg_building_separation=50.0,
            avg_building_width=30.0,
            avg_line_width=10.0,
            avg_building_height=15.0,
            line_segments=[seg],
        )
        sources.add_source(buoy)
        receptors = ReceptorPathway()
        receptors.add_discrete_receptor(DiscreteReceptor(x_coord=0, y_coord=0, z_elev=0, z_flag=0))
        met = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl")
        output = OutputPathway()
        project = AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=met, output=output,
        )

        src_df = pd.DataFrame([
            {"source_id": "BL1SEG1", "source_type": "BUOYLINE", "x": 100.0, "y": 200.0, "zelev": 250.0},
        ])

        processor = TerrainProcessor()
        processor._update_source_elevations(project, src_df)

        # BuoyLineSource base_elevation updated from segment match
        assert buoy.base_elevation == pytest.approx(250.0)


class TestTerrainProcessorProcess:
    """Test the full process() pipeline with mocks (lines 641-691)."""

    def test_process_mocked_pipeline(self, tmp_path):
        """Mock all sub-components to test process() flow."""
        control = ControlPathway(title_one="Pipeline Test")
        sources = SourcePathway()
        point = PointSource(
            source_id="S1", x_coord=500000.0, y_coord=3800000.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        sources.add_source(point)
        grid = CartesianGrid(
            x_init=499500.0, x_num=3, x_delta=500.0,
            y_init=3799500.0, y_num=3, y_delta=500.0,
        )
        receptors = ReceptorPathway(cartesian_grids=[grid])
        met = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl")
        output = OutputPathway()
        project = AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=met, output=output,
        )

        processor = TerrainProcessor()

        # Create mock AERMAP run result
        mock_result = AERMAPRunResult(
            success=True, input_file=str(tmp_path / "aermap.inp"),
            return_code=0, runtime_seconds=1.0,
        )

        # Create receptor output file that AERMAP would have produced
        rec_output_dir = tmp_path / "aermap_work"
        rec_output_dir.mkdir(parents=True, exist_ok=True)
        rec_file = rec_output_dir / "aermap_rec.out"
        rec_content = """** AERMAP Receptor Output
   DISCCART     499500.00    3799500.00    100.00    110.00
   DISCCART     500000.00    3799500.00    105.00    115.00
   DISCCART     500500.00    3799500.00    110.00    120.00
"""
        rec_file.write_text(rec_content)

        with patch.object(AERMAPRunner, "__init__", return_value=None), \
             patch.object(AERMAPRunner, "run", return_value=mock_result):
            result = processor.process(
                project,
                bounds=(-88.0, 40.0, -87.0, 41.0),
                aermap_exe="/fake/aermap",
                working_dir=str(rec_output_dir),
                skip_download=True,
                dem_files=["test.tif"],
            )

        # Should return the updated project
        assert result is project

    def test_process_skip_download_requires_dem_files(self, tmp_path):
        """process() with skip_download=True and no dem_files → ValueError."""
        processor = TerrainProcessor()
        control = ControlPathway(title_one="Test")
        sources = SourcePathway()
        point = PointSource(
            source_id="S1", x_coord=0.0, y_coord=0.0,
            base_elevation=0.0, stack_height=20.0, stack_temp=350.0,
            exit_velocity=10.0, stack_diameter=1.0, emission_rate=5.0,
        )
        sources.add_source(point)
        receptors = ReceptorPathway()
        receptors.add_discrete_receptor(DiscreteReceptor(x_coord=0, y_coord=0, z_elev=0, z_flag=0))
        met = MeteorologyPathway(surface_file="t.sfc", profile_file="t.pfl")
        output = OutputPathway()
        project = AERMODProject(
            control=control, sources=sources, receptors=receptors,
            meteorology=met, output=output,
        )

        with pytest.raises(ValueError, match="dem_files required"):
            processor.process(
                project,
                bounds=(-88, 40, -87, 41),
                skip_download=True,
                dem_files=None,
                working_dir=str(tmp_path),
            )
