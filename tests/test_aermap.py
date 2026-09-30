"""
Unit tests for PyAERMOD AERMAP input generator
"""

from pathlib import Path

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


RECORDED_SUCCESS = Path(__file__).parent / "fixtures" / "aermap_runner" / "success"


def _cards(output: str, keyword: str):
    """The fields of every runstream line whose keyword is ``keyword``."""
    rows = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == keyword:
            rows.append(fields[1:])
        elif len(fields) >= 3 and fields[1] == keyword:
            rows.append(fields[2:])
    return rows


def _project(**kw):
    kw.setdefault("dem_files", ["test.dem"])
    kw.setdefault("anchor_x", 400000.0)
    kw.setdefault("anchor_y", 4650000.0)
    return AERMAPProject(**kw)


def _with_receptor_and_source(**kw):
    project = _project(**kw)
    project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0))
    project.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0))
    return project


class TestAERMAPProject:
    """The runstream follows AERMAP 24142's syntax (aermap.f), keyword by keyword."""

    def test_writes_the_recorded_deck_aermap_accepted(self):
        """The deck AERMAP ran with 0 fatal errors in tests/fixtures/aermap_runner/success/."""
        project = AERMAPProject(
            title_one="pyaermod AERMAP runner recording", dem_files=["synth.dem"],
            dem_format="DEM", anchor_x=500000.0, anchor_y=4000000.0, utm_zone=13,
            datum="NAD27", grid_receptor=True, grid_x_init=500100.0,
            grid_y_init=4000200.0, grid_x_num=3, grid_y_num=2, grid_spacing=100.0,
            domain_x_min=500050.0, domain_y_min=4000050.0,
            domain_x_max=500550.0, domain_y_max=4000550.0,
        )
        project.add_receptor(AERMAPReceptor("R0001", 500100.0, 4000100.0))
        project.add_source(AERMAPSource("STACK1", 500200.0, 4000300.0))
        assert project.to_aermap_input() == (RECORDED_SUCCESS / "aermap.inp").read_text()

    def test_basic_project_structure(self):
        output = _with_receptor_and_source(title_one="Test AERMAP").to_aermap_input()
        assert "CO STARTING" in output
        assert "CO FINISHED" in output
        assert "OU STARTING" in output
        assert "OU FINISHED" in output
        assert "TITLEONE  Test AERMAP" in output
        assert "DATATYPE  NED" in output
        assert _cards(output, "TERRHGTS") == [["EXTRACT"]]
        assert _cards(output, "RUNORNOT") == [["RUN"]]

    def test_pathways_in_the_order_aermap_requires(self):
        """SETORD: CO, SO, RE, OU; SO after RE is fatal E120."""
        output = _with_receptor_and_source().to_aermap_input()
        starts = [line.split()[0] for line in output.splitlines() if line.endswith(" STARTING")]
        assert starts == ["CO", "SO", "RE", "OU"]

    def test_anchorxy_has_six_fields(self):
        """ANCHOR: Xauser Yauser Xutm Yutm Zone Nada; mandatory (E130 without it)."""
        output = _with_receptor_and_source(utm_zone=16, datum="NAD83").to_aermap_input()
        assert _cards(output, "ANCHORXY") == [
            ["400000.00", "4650000.00", "400000.00", "4650000.00", "16", "4"],
        ]

    def test_anchor_with_local_user_coordinates(self):
        output = _with_receptor_and_source(
            anchor_x=0.0, anchor_y=0.0, anchor_utm_x=400000.0, anchor_utm_y=4650000.0,
        ).to_aermap_input()
        assert _cards(output, "ANCHORXY") == [
            ["0.00", "0.00", "400000.00", "4650000.00", "16", "4"],
        ]

    @pytest.mark.parametrize(("datum", "code"), [
        ("NAD27", "1"), ("WGS72", "2"), ("WGS84", "3"), ("NAD83", "4"), ("nad83", "4"),
        (0, "0"), (7, "7"),
    ])
    def test_datum_becomes_the_nada_code(self, datum, code):
        output = _with_receptor_and_source(datum=datum).to_aermap_input()
        assert _cards(output, "ANCHORXY")[0][-1] == code

    @pytest.mark.parametrize("datum", ["NAD99", 8, -1, True])
    def test_unknown_datum_raises(self, datum):
        with pytest.raises(ValueError, match="datum="):
            _with_receptor_and_source(datum=datum).to_aermap_input()

    def test_domainxy_has_six_fields(self):
        """DOMAIN: Xdmin Ydmin Zonmin Xdmax Ydmax Zonmax (E200 with four)."""
        output = _with_receptor_and_source(
            utm_zone=16, domain_x_min=399000.0, domain_y_min=4649000.0,
            domain_x_max=403000.0, domain_y_max=4653000.0,
        ).to_aermap_input()
        assert _cards(output, "DOMAINXY") == [
            ["399000.00", "4649000.00", "16", "403000.00", "4653000.00", "16"],
        ]

    def test_no_domain_leaves_domainxy_out(self):
        """Without DOMAINXY, AERMAP takes the domain from the DEM files."""
        assert "DOMAINXY" not in _with_receptor_and_source().to_aermap_input()

    def test_partial_domain_raises(self):
        with pytest.raises(ValueError, match="all four"):
            _with_receptor_and_source(domain_x_min=399000.0).to_aermap_input()

    def test_inverted_domain_raises(self):
        with pytest.raises(ValueError, match="south-west"):
            _with_receptor_and_source(
                domain_x_min=403000.0, domain_y_min=4649000.0,
                domain_x_max=399000.0, domain_y_max=4653000.0,
            ).to_aermap_input()

    def test_missing_anchor_raises_error(self):
        project = AERMAPProject(dem_files=["test.dem"])  # anchor_x and anchor_y default to None
        project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0))
        with pytest.raises(ValueError, match="anchor_x and anchor_y must be provided"):
            project.to_aermap_input()

    def test_missing_dem_raises(self):
        project = _with_receptor_and_source(dem_files=[])
        with pytest.raises(ValueError, match="DEM file"):
            project.to_aermap_input()

    def test_no_receptor_and_no_source_raises(self):
        """OUCARD: E194 without RECEPTOR or SOURCLOC."""
        with pytest.raises(ValueError, match="at least one receptor or source"):
            _project().to_aermap_input()

    def test_title_two(self):
        output = _with_receptor_and_source(title_one="Title One", title_two="Title Two").to_aermap_input()
        assert "TITLETWO  Title Two" in output

    def test_dem_files_in_output(self):
        output = _with_receptor_and_source(dem_files=["n41w088.tif", "n41w089.tif"]).to_aermap_input()
        assert _cards(output, "DATAFILE") == [["n41w088.tif"], ["n41w089.tif"]]

    def test_dem_path_with_a_space_is_quoted(self):
        output = _with_receptor_and_source(dem_files=["/data/my dems/n41w088.tif"]).to_aermap_input()
        assert '   DATAFILE  "/data/my dems/n41w088.tif"' in output

    def test_dem_path_too_long_raises(self):
        with pytest.raises(ValueError, match="at most 200"):
            _with_receptor_and_source(dem_files=["d/" * 100 + "x.tif"]).to_aermap_input()

    def test_dem_path_with_a_quote_raises(self):
        with pytest.raises(ValueError, match="double quote"):
            _with_receptor_and_source(dem_files=['a"b.tif']).to_aermap_input()

    @pytest.mark.parametrize(("fmt", "written"), [("NED", "NED"), ("DEM", "DEM"), ("dem7", "DEM7")])
    def test_datatype(self, fmt, written):
        output = _with_receptor_and_source(dem_format=fmt).to_aermap_input()
        assert _cards(output, "DATATYPE") == [[written]]

    @pytest.mark.parametrize("fmt", ["SRTM", "GTOPO30"])
    def test_unsupported_datatype_raises(self, fmt):
        with pytest.raises(ValueError, match="dem_format="):
            _with_receptor_and_source(dem_format=fmt).to_aermap_input()

    def test_discrete_receptors_carry_no_id(self):
        """DISCAR reads x y [zelev]; an ID in the x field is fatal E208."""
        project = _project()
        project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0))
        project.add_receptor(AERMAPReceptor("R002", 402000.0, 4651000.0))
        output = project.to_aermap_input()
        assert "RE STARTING" in output
        assert "RE FINISHED" in output
        assert _cards(output, "DISCCART") == [
            ["401000.00", "4651000.00"], ["402000.00", "4651000.00"],
        ]
        assert "R001" not in output
        assert _cards(output, "RECEPTOR") == [["aermap_receptors.out"]]
        assert "SOURCLOC" not in output
        assert "SO STARTING" not in output

    def test_extract_leaves_given_elevations_out(self):
        """With EXTRACT, AERMAP ignores a given elevation (W229); the deck omits it."""
        project = _project()
        project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0, elevation=150.0))
        project.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0, elevation=160.0))
        output = project.to_aermap_input()
        assert _cards(output, "DISCCART") == [["401000.00", "4651000.00"]]
        assert _cards(output, "LOCATION") == [["STACK1", "POINT", "401500.00", "4651500.00"]]

    def test_provided_writes_the_elevations(self):
        project = _project(terrain_type="PROVIDED")
        project.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0, elevation=150.0))
        project.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0, elevation=160.0))
        output = project.to_aermap_input()
        assert _cards(output, "TERRHGTS") == [["PROVIDED"]]
        assert _cards(output, "DISCCART") == [["401000.00", "4651000.00", "150.00"]]
        assert _cards(output, "LOCATION") == [
            ["STACK1", "POINT", "401500.00", "4651500.00", "160.00"],
        ]
        # AERMAP leaves the SOURCLOC file empty under PROVIDED.
        assert _cards(output, "RECEPTOR") == [["aermap_receptors.out"]]
        assert "SOURCLOC" not in output

    def test_provided_without_a_receptor_raises(self):
        project = _project(terrain_type="PROVIDED")
        project.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0, elevation=160.0))
        with pytest.raises(ValueError, match="at least one discrete receptor"):
            project.to_aermap_input()

    def test_provided_without_an_elevation_raises(self):
        """AERMAP would take 0 m (W205, W228) for the missing elevations."""
        project = _with_receptor_and_source(terrain_type="PROVIDED")
        with pytest.raises(ValueError, match="missing on: R001, STACK1"):
            project.to_aermap_input()

    def test_provided_with_a_grid_raises(self):
        """A PROVIDED grid without ELEV rows gets 0 m elevations (W214)."""
        project = _project(terrain_type="PROVIDED", grid_receptor=True)
        with pytest.raises(ValueError, match="grid receptors"):
            project.to_aermap_input()

    def test_sources(self):
        project = _project()
        project.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0))
        output = project.to_aermap_input()
        assert "SO STARTING" in output
        assert "SO FINISHED" in output
        assert _cards(output, "LOCATION") == [["STACK1", "POINT", "401500.00", "4651500.00"]]
        assert _cards(output, "SOURCLOC") == [["aermap_sources.out"]]
        # Sources alone are a valid AERMAP run (P010 in AERMAP 24142).
        assert "RE STARTING" not in output
        assert "   RECEPTOR" not in output

    def test_grid_receptors_are_a_sta_end_block(self):
        """RECART: STA must open the network (E200 'STA' without it)."""
        output = _project(
            grid_receptor=True, grid_x_init=400000.0, grid_y_init=4650000.0,
            grid_x_num=21, grid_y_num=11, grid_spacing=100.0, grid_y_spacing=50.0,
        ).to_aermap_input()
        assert _cards(output, "GRIDCART") == [
            ["GRID", "STA"],
            ["GRID", "XYINC", "400000.00", "21", "100.00", "4650000.00", "11", "50.00"],
            ["GRID", "END"],
        ]
        assert _cards(output, "RECEPTOR") == [["aermap_receptors.out"]]

    def test_grid_y_spacing_defaults_to_grid_spacing(self):
        output = _project(grid_receptor=True, grid_spacing=250.0).to_aermap_input()
        assert _cards(output, "GRIDCART")[1][-1] == "250.00"

    @pytest.mark.parametrize("terrain_type", ["EXTRACT", "extract", "ELEVATED"])
    def test_extract_and_its_old_name(self, terrain_type):
        """ELEVATED, which AERMAP rejects (E203), is read as the EXTRACT it meant."""
        output = _with_receptor_and_source(terrain_type=terrain_type).to_aermap_input()
        assert _cards(output, "TERRHGTS") == [["EXTRACT"]]

    def test_flat_raises(self):
        with pytest.raises(ValueError, match=r"TerrainType\.FLAT"):
            _with_receptor_and_source(terrain_type="FLAT").to_aermap_input()

    def test_write_file(self, tmp_path):
        project = _with_receptor_and_source(title_one="Write Test")
        filepath = str(tmp_path / "test_aermap.inp")
        result = project.write(filepath)

        assert result == filepath
        with open(filepath) as f:
            content = f.read()
        assert "Write Test" in content

    def test_output_files_in_output(self):
        project = _with_receptor_and_source(
            receptor_output="custom_rec.out", source_output="custom src.out",
            message_file="custom.msg",
        )
        output = project.to_aermap_input()
        assert "   RECEPTOR  custom_rec.out" in output
        assert '   SOURCLOC  "custom src.out"' in output
        # AERMAP has no message-file keyword; it writes <input stem>.out.
        assert "custom.msg" not in output
        for old_keyword in ("RECOUTPUT", "SRCOUTPUT", "MSGOUTPUT"):
            assert old_keyword not in output

    def test_from_aermod_project_sets_the_domain_and_the_format(self):
        from pyaermod.input_generator import (
            AERMODProject,
            CartesianGrid,
            ControlPathway,
            DiscreteReceptor,
            MeteorologyPathway,
            OutputPathway,
            PointSource,
            ReceptorPathway,
            SourcePathway,
        )

        project = AERMODProject(
            control=ControlPathway(title_one="t"),
            sources=SourcePathway(),
            receptors=ReceptorPathway(
                cartesian_grids=[CartesianGrid(
                    x_init=500000.0, x_num=3, x_delta=100.0,
                    y_init=4000000.0, y_num=4, y_delta=50.0,
                )],
                discrete_receptors=[DiscreteReceptor(x_coord=500500.0, y_coord=4000500.0)],
            ),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )
        project.sources.add_source(PointSource(
            source_id="STK1", x_coord=500100.0, y_coord=4000100.0,
            stack_height=50.0, emission_rate=1.0,
        ))
        aermap = AERMAPProject.from_aermod_project(
            project, dem_files=["a.dem", "b.DEM"], utm_zone=13, buffer=500.0,
        )
        assert aermap.dem_format == "DEM"
        assert aermap.terrain_type == "EXTRACT"
        assert (aermap.domain_x_min, aermap.domain_y_min) == (499500.0, 3999500.0)
        assert (aermap.domain_x_max, aermap.domain_y_max) == (501000.0, 4001000.0)
        assert aermap.grid_spacing == 100.0
        assert aermap.grid_y_spacing == 50.0
        output = aermap.to_aermap_input()
        assert _cards(output, "DOMAINXY") == [
            ["499500.00", "3999500.00", "13", "501000.00", "4001000.00", "13"],
        ]
        assert _cards(output, "ANCHORXY") == [
            ["499500.00", "3999500.00", "499500.00", "3999500.00", "13", "4"],
        ]

        tif = AERMAPProject.from_aermod_project(project, dem_files=["a.dem", "b.tif"])
        assert tif.dem_format == "NED"
        forced = AERMAPProject.from_aermod_project(project, dem_files=["x.img"], dem_format="DEM")
        assert forced.dem_format == "DEM"


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
