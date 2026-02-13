"""
Unit tests for PyAERMOD AERMAP input generator
"""

import pytest

from pyaermod.aermap import (
    AERMAPDomain,
    AERMAPProject,
    AERMAPReceptor,
    AERMAPSource,
    create_grid_receptors_for_aermap,
)


class TestAERMAPDomain:
    """Test AERMAPDomain dataclass"""

    def test_basic_domain(self):
        """Test basic domain creation"""
        domain = AERMAPDomain(
            anchor_x=400000.0,
            anchor_y=4650000.0,
            num_x_points=41,
            num_y_points=41,
            spacing=100.0
        )
        assert domain.anchor_x == 400000.0
        assert domain.anchor_y == 4650000.0
        assert domain.num_x_points == 41
        assert domain.spacing == 100.0
        assert domain.utm_zone == 16  # default
        assert domain.datum == "NAD83"  # default

    def test_domain_custom_datum(self):
        """Test domain with custom UTM zone and datum"""
        domain = AERMAPDomain(
            anchor_x=500000.0,
            anchor_y=3800000.0,
            num_x_points=20,
            num_y_points=20,
            spacing=250.0,
            utm_zone=17,
            datum="WGS84"
        )
        assert domain.utm_zone == 17
        assert domain.datum == "WGS84"

    def test_domain_dem_files(self):
        """Test domain with DEM file list"""
        domain = AERMAPDomain(
            anchor_x=400000.0,
            anchor_y=4650000.0,
            num_x_points=10,
            num_y_points=10,
            spacing=100.0,
            dem_files=["tile1.dem", "tile2.dem"]
        )
        assert len(domain.dem_files) == 2
        assert "tile1.dem" in domain.dem_files


class TestAERMAPReceptor:
    """Test AERMAPReceptor dataclass"""

    def test_receptor_without_elevation(self):
        """Test receptor without pre-set elevation"""
        rec = AERMAPReceptor("R001", 401000.0, 4651000.0)
        assert rec.receptor_id == "R001"
        assert rec.x_coord == 401000.0
        assert rec.y_coord == 4651000.0
        assert rec.elevation is None

    def test_receptor_with_elevation(self):
        """Test receptor with explicit elevation"""
        rec = AERMAPReceptor("R002", 402000.0, 4652000.0, elevation=150.0)
        assert rec.elevation == 150.0


class TestAERMAPSource:
    """Test AERMAPSource dataclass"""

    def test_source_without_elevation(self):
        """Test source without pre-set elevation"""
        src = AERMAPSource("STACK1", 401500.0, 4651500.0)
        assert src.source_id == "STACK1"
        assert src.elevation is None

    def test_source_with_elevation(self):
        """Test source with explicit elevation"""
        src = AERMAPSource("STACK2", 402000.0, 4652000.0, elevation=200.0)
        assert src.elevation == 200.0


class TestAERMAPProject:
    """Test AERMAPProject input generation"""

    def test_basic_project_structure(self):
        """Test basic project output has required sections"""
        project = AERMAPProject(
            title_one="Test AERMAP",
            dem_files=["test.dem"],
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        output = project.to_aermap_input()

        assert "CO STARTING" in output
        assert "CO FINISHED" in output
        assert "OU STARTING" in output
        assert "OU FINISHED" in output
        assert "TITLEONE  Test AERMAP" in output
        assert "DATATYPE  NED" in output
        assert "TERRHGTS  FLAT" in output

    def test_domain_xy_in_output(self):
        """Test DOMAINXY line is correct"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
            utm_zone=16,
            datum="NAD83",
        )
        output = project.to_aermap_input()
        assert "DOMAINXY  400000.00 4650000.00 16 NAD83" in output

    def test_missing_anchor_raises_error(self):
        """Test that None anchor coordinates raise ValueError"""
        project = AERMAPProject()  # anchor_x and anchor_y default to None
        with pytest.raises(ValueError, match="anchor_x and anchor_y must be provided"):
            project.to_aermap_input()

    def test_title_two(self):
        """Test optional second title"""
        project = AERMAPProject(
            title_one="Title One",
            title_two="Title Two",
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        output = project.to_aermap_input()
        assert "TITLETWO  Title Two" in output

    def test_dem_files_in_output(self):
        """Test DEM file entries"""
        project = AERMAPProject(
            dem_files=["n41w088.dem", "n41w089.dem"],
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        output = project.to_aermap_input()
        assert "DATAFILE  n41w088.dem" in output
        assert "DATAFILE  n41w089.dem" in output

    def test_discrete_receptors(self):
        """Test project with discrete receptors"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0))
        project.add_receptor(AERMAPReceptor("R002", 402000.0, 4651000.0))

        output = project.to_aermap_input()
        assert "RE STARTING" in output
        assert "RE FINISHED" in output
        assert "DISCCART" in output
        assert "R001" in output
        assert "R002" in output
        assert "RECOUTPUT" in output

    def test_receptor_with_elevation_format(self):
        """Test receptor with elevation has 3 coordinate fields"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0, elevation=150.0))

        output = project.to_aermap_input()
        assert "150.00" in output

    def test_sources(self):
        """Test project with sources"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        project.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0))

        output = project.to_aermap_input()
        assert "SO STARTING" in output
        assert "SO FINISHED" in output
        assert "LOCATION" in output
        assert "STACK1" in output
        assert "SRCOUTPUT" in output

    def test_grid_receptors(self):
        """Test grid receptor output"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
            grid_receptor=True,
            grid_x_init=400000.0,
            grid_y_init=4650000.0,
            grid_x_num=21,
            grid_y_num=21,
            grid_spacing=100.0,
        )
        output = project.to_aermap_input()
        assert "RE STARTING" in output
        assert "GRIDCART" in output
        assert "XYINC" in output

    def test_elevated_terrain(self):
        """Test elevated terrain type"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
            terrain_type="ELEVATED",
        )
        output = project.to_aermap_input()
        assert "TERRHGTS  ELEVATED" in output

    def test_no_receptors_no_re_section(self):
        """Test that RE section is omitted when no receptors"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        output = project.to_aermap_input()
        assert "RE STARTING" not in output

    def test_no_sources_no_so_section(self):
        """Test that SO section is omitted when no sources"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        output = project.to_aermap_input()
        assert "SO STARTING" not in output

    def test_write_file(self, tmp_path):
        """Test writing AERMAP input to file"""
        project = AERMAPProject(
            title_one="Write Test",
            anchor_x=400000.0,
            anchor_y=4650000.0,
        )
        filepath = str(tmp_path / "test_aermap.inp")
        result = project.write(filepath)

        assert result == filepath
        with open(filepath) as f:
            content = f.read()
        assert "Write Test" in content

    def test_output_files_in_output(self):
        """Test output file names appear in generated input"""
        project = AERMAPProject(
            anchor_x=400000.0,
            anchor_y=4650000.0,
            receptor_output="custom_rec.out",
            message_file="custom.msg",
        )
        project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0))

        output = project.to_aermap_input()
        assert "RECOUTPUT custom_rec.out" in output
        assert "MSGOUTPUT custom.msg" in output


class TestCreateGridReceptors:
    """Test create_grid_receptors_for_aermap helper"""

    def test_basic_grid_params(self):
        """Test grid parameter calculation"""
        x_init, y_init, x_num, y_num = create_grid_receptors_for_aermap(
            x_min=0.0, x_max=1000.0,
            y_min=0.0, y_max=1000.0,
            spacing=100.0
        )
        assert x_init == 0.0
        assert y_init == 0.0
        assert x_num == 11
        assert y_num == 11

    def test_asymmetric_grid(self):
        """Test asymmetric domain"""
        x_init, y_init, x_num, y_num = create_grid_receptors_for_aermap(
            x_min=100.0, x_max=500.0,
            y_min=200.0, y_max=1200.0,
            spacing=100.0
        )
        assert x_init == 100.0
        assert y_init == 200.0
        assert x_num == 5
        assert y_num == 11

    def test_fine_spacing(self):
        """Test fine grid spacing"""
        _x_init, _y_init, x_num, y_num = create_grid_receptors_for_aermap(
            x_min=0.0, x_max=100.0,
            y_min=0.0, y_max=100.0,
            spacing=10.0
        )
        assert x_num == 11
        assert y_num == 11
