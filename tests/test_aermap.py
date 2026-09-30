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
RECORDED_NETWORKS = RECORDED_SUCCESS.parent / "networks"


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

    def test_from_aermod_project_with_a_buffer_sets_the_domain_and_the_format(self):
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
        assert aermap.grid_receptor is False
        assert [(g.grid_name, g.x_delta, g.y_delta) for g in aermap.grids] == [("GRID1", 100.0, 50.0)]
        output = aermap.to_aermap_input()
        assert _cards(output, "DOMAINXY") == [
            ["499500.00", "3999500.00", "13", "501000.00", "4001000.00", "13"],
        ]
        # Anchored at the extent's south-west corner, to itself.
        assert _cards(output, "ANCHORXY") == [
            ["500000.00", "4000000.00", "500000.00", "4000000.00", "13", "4"],
        ]

        tif = AERMAPProject.from_aermod_project(project, dem_files=["a.dem", "b.tif"])
        assert tif.dem_format == "NED"
        forced = AERMAPProject.from_aermod_project(project, dem_files=["x.img"], dem_format="DEM")
        assert forced.dem_format == "DEM"


def networks_project():
    """The deck AERMAP ran clean in tests/fixtures/aermap_runner/networks/.

    One discrete receptor, two Cartesian and two polar grids, and one
    source of every AERMAP source type but POINTHOR, on the 7 x 7 planar DEM.
    """
    from pyaermod.receptors import CartesianGrid, PolarGrid

    p = AERMAPProject(
        title_one="pyaermod AERMAP networks recording", dem_files=["synth.dem"],
        dem_format="DEM", anchor_x=500000.0, anchor_y=4000000.0, utm_zone=13, datum="NAD27",
        grids=[
            CartesianGrid(grid_name="G1", x_init=500100.0, x_num=3, x_delta=100.0,
                          y_init=4000200.0, y_num=2, y_delta=100.0),
            CartesianGrid(grid_name="G2", x_points=[500150.0, 500250.0, 500450.0],
                          y_points=[4000150.0, 4000350.0]),
            PolarGrid(grid_name="P1", x_origin=500300.0, y_origin=4000300.0,
                      dist_init=100.0, dist_num=2, dist_delta=100.0,
                      dir_init=0.0, dir_num=4, dir_delta=90.0),
            PolarGrid(grid_name="P2", origin_source_id="STK", distances=[50.0, 150.0],
                      directions=[45.0, 135.0, 225.0]),
        ],
    )
    p.add_receptor(AERMAPReceptor("R1", 500100.0, 4000100.0))
    for sid, stype, x, y in [
        ("STK", "POINT", 500200.0, 4000300.0), ("CAP", "POINTCAP", 500300.0, 4000200.0),
        ("VOL", "VOLUME", 500400.0, 4000200.0), ("AR", "AREA", 500100.0, 4000500.0),
        ("AC", "AREACIRC", 500250.0, 4000250.0), ("AP", "AREAPOLY", 500350.0, 4000450.0),
        ("PIT", "OPENPIT", 500450.0, 4000150.0),
    ]:
        p.add_source(AERMAPSource(sid, x, y, source_type=stype))
    p.add_source(AERMAPSource("LN", 500100.0, 4000400.0, source_type="LINE",
                              x_end=500400.0, y_end=4000400.0, width=10.0))
    p.add_source(AERMAPSource("RL", 500100.0, 4000100.0, source_type="RLINE",
                              x_end=500300.0, y_end=4000300.0))
    p.add_source(AERMAPSource("BL1", 500200.0, 4000500.0, source_type="BUOYLINE",
                              x_end=500300.0, y_end=4000500.0))
    return p


class TestSourceTypes:
    """SO LOCATION in SOLOCA's layout (aermap.f): each source type AERMAP 24142 reads."""

    def test_writes_the_recorded_networks_deck(self):
        assert networks_project().to_aermap_input() == (RECORDED_NETWORKS / "aermap.inp").read_text()

    def test_line_sources_carry_both_ends(self):
        cards = {row[0]: row[1:] for row in _cards(networks_project().to_aermap_input(), "LOCATION")}
        assert cards["LN"] == ["LINE", "500100.00", "4000400.00", "500400.00", "4000400.00", "10.00"]
        assert cards["RL"] == ["RLINE", "500100.00", "4000100.00", "500300.00", "4000300.00"]
        assert cards["BL1"] == ["BUOYLINE", "500200.00", "4000500.00", "500300.00", "4000500.00"]
        assert cards["AP"] == ["AREAPOLY", "500350.00", "4000450.00"]

    def test_provided_elevation_follows_the_width(self):
        project = _project(terrain_type="PROVIDED")
        project.add_receptor(AERMAPReceptor("R1", 1.0, 2.0, elevation=5.0))
        project.add_source(AERMAPSource("LN", 1.0, 2.0, elevation=7.0, source_type="LINE",
                                        x_end=3.0, y_end=4.0, width=6.0))
        assert _cards(project.to_aermap_input(), "LOCATION") == [
            ["LN", "LINE", "1.00", "2.00", "3.00", "4.00", "6.00", "7.00"],
        ]

    @pytest.mark.parametrize("kw, match", [
        ({"source_type": "SWPOINT"}, "no source type 'SWPOINT'"),
        ({"source_type": "RLINEXT"}, "no source type 'RLINEXT'"),
        ({"source_type": "RLINE"}, "needs x_end and y_end"),
        ({"source_type": "LINE", "x_end": 1.0, "y_end": 1.0}, "needs its width"),
        ({"source_type": "LINE", "x_end": 1.0, "y_end": 1.0, "width": 0.0}, "needs its width"),
    ])
    def test_a_source_aermap_cannot_read_raises(self, kw, match):
        project = _project()
        project.add_source(AERMAPSource("S1", 0.0, 0.0, **kw))
        with pytest.raises(ValueError, match=match):
            project.to_aermap_input()

    @pytest.mark.parametrize("source_id", ["A" * 13, "TWO WORDS", ""])
    def test_a_source_id_aermap_would_cut_raises(self, source_id):
        project = _project()
        project.add_source(AERMAPSource(source_id, 0.0, 0.0))
        with pytest.raises(ValueError, match="E206"):
            project.to_aermap_input()


class TestReceptorNetworks:
    """GRIDCART and GRIDPOLR blocks in AERMAP's syntax (RECART / REPOLR in aermap.f)."""

    def test_every_network_is_written_under_its_name(self):
        output = networks_project().to_aermap_input()
        assert _cards(output, "GRIDCART") == [
            ["G1", "STA"],
            ["G1", "XYINC", "500100.00", "3", "100.00", "4000200.00", "2", "100.00"],
            ["G1", "END"],
            ["G2", "STA"],
            ["G2", "XPNTS", "500150.00", "500250.00", "500450.00"],
            ["G2", "YPNTS", "4000150.00", "4000350.00"],
            ["G2", "END"],
        ]
        assert _cards(output, "GRIDPOLR") == [
            ["P1", "STA"], ["P1", "ORIG", "500300.00", "4000300.00"],
            ["P1", "DIST", "100.00", "200.00"], ["P1", "GDIR", "4", "0.00", "90.00"], ["P1", "END"],
            # Centred on STK: written with STK's coordinates.
            ["P2", "STA"], ["P2", "ORIG", "500200.00", "4000300.00"],
            ["P2", "DIST", "50.00", "150.00"], ["P2", "DDIR", "45.00", "135.00", "225.00"], ["P2", "END"],
        ]

    def test_long_lists_span_lines(self):
        from pyaermod.receptors import CartesianGrid

        project = _project(grids=[CartesianGrid(grid_name="G", x_points=[float(i) for i in range(8)],
                                                y_points=[0.0])])
        xpnts = [row for row in _cards(project.to_aermap_input(), "GRIDCART") if row[1] == "XPNTS"]
        assert [len(row) - 2 for row in xpnts] == [6, 2]

    def test_the_legacy_grid_and_the_networks_together(self):
        from pyaermod.receptors import CartesianGrid

        output = _project(grid_receptor=True, grids=[CartesianGrid(grid_name="G1")]).to_aermap_input()
        assert [row[0] for row in _cards(output, "GRIDCART") if row[1] == "STA"] == ["GRID", "G1"]

    @pytest.mark.parametrize("names, match", [
        (["TOOLONGID"], "1 to 8 characters"),
        (["G 1"], "no blanks"),
        (["G1", "G1"], "unique"),
        (["GRID"], "unique"),
    ])
    def test_network_names_aermap_would_confuse_raise(self, names, match):
        from pyaermod.receptors import CartesianGrid

        project = _project(grid_receptor=True, grids=[CartesianGrid(grid_name=n) for n in names])
        if names != ["GRID"]:
            project.grid_receptor = False
        with pytest.raises(ValueError, match=match):
            project.to_aermap_input()

    def test_empty_networks_raise(self):
        from pyaermod.receptors import CartesianGrid, PolarGrid

        with pytest.raises(ValueError, match="Cartesian grid G has no receptors"):
            _project(grids=[CartesianGrid(grid_name="G", x_points=[], y_points=[1.0])]).to_aermap_input()
        with pytest.raises(ValueError, match="polar grid P has no receptors"):
            _project(grids=[PolarGrid(grid_name="P", distances=[])]).to_aermap_input()

    @pytest.mark.parametrize("sources", [[], [AERMAPSource("RL", 0.0, 0.0, source_type="RLINE", x_end=1.0, y_end=1.0)]])
    def test_a_polar_origin_that_is_not_a_point_source_raises(self, sources):
        from pyaermod.receptors import PolarGrid

        project = _project(grids=[PolarGrid(grid_name="P", origin_source_id="RL")], sources=sources)
        project.add_receptor(AERMAPReceptor("R1", 0.0, 0.0))
        with pytest.raises(ValueError, match="not a single-point source"):
            project.to_aermap_input()

    def test_provided_with_a_network_raises(self):
        from pyaermod.receptors import CartesianGrid

        project = _project(terrain_type="PROVIDED", grids=[CartesianGrid()])
        project.add_receptor(AERMAPReceptor("R1", 0.0, 0.0, elevation=1.0))
        with pytest.raises(ValueError, match="grid receptors"):
            project.to_aermap_input()


class TestNadGrids:
    """NADGRIDS (aermap.f NADGRIDS; sub_nadcon.f opens NGPATH//'conus.las')."""

    def test_no_directory_writes_no_card(self):
        assert "NADGRIDS" not in _with_receptor_and_source().to_aermap_input()

    @pytest.mark.parametrize("path, written", [
        ("/data/nadcon", "/data/nadcon/"),
        ("/data/nadcon/", "/data/nadcon/"),
        ("C:\\nadcon\\", "C:\\nadcon\\"),
    ])
    def test_the_directory_ends_in_a_separator(self, path, written):
        output = _with_receptor_and_source(nad_grids_dir=path).to_aermap_input()
        assert _cards(output, "NADGRIDS") == [[written]]

    def test_a_directory_with_a_space_is_quoted(self):
        output = _with_receptor_and_source(nad_grids_dir="/my data").to_aermap_input()
        assert '   NADGRIDS  "/my data/"' in output


class TestFromAermodProject:
    """from_aermod_project writes every source and receptor network AERMAP can place."""

    @staticmethod
    def _aermod(sources=(), cartesian=(), polar=(), discrete=()):
        from pyaermod.input_generator import (
            AERMODProject,
            ControlPathway,
            MeteorologyPathway,
            OutputPathway,
            ReceptorPathway,
            SourcePathway,
        )

        project = AERMODProject(
            control=ControlPathway(title_one="t"),
            sources=SourcePathway(),
            receptors=ReceptorPathway(
                cartesian_grids=list(cartesian), polar_grids=list(polar),
                discrete_receptors=list(discrete),
            ),
            meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
            output=OutputPathway(),
        )
        for src in sources:
            project.sources.add_source(src)
        return project

    def test_no_domain_by_default(self):
        """Without DOMAINXY AERMAP searches the whole DEM for hill heights."""
        from pyaermod.input_generator import DiscreteReceptor

        aermap = AERMAPProject.from_aermod_project(
            self._aermod(discrete=[DiscreteReceptor(500500.0, 4000500.0)]), dem_files=["a.dem"],
        )
        assert aermap.domain_x_min is None
        assert "DOMAINXY" not in aermap.to_aermap_input()

    def test_every_source_type_is_placed(self):
        from pyaermod.sources import (
            AreaCircSource,
            AreaPolySource,
            AreaSource,
            BuoyLineSegment,
            BuoyLineSource,
            LineSource,
            OpenPitSource,
            PointCapSource,
            PointHorSource,
            PointSource,
            RLineExtSource,
            RLineSource,
            SidewashPointSource,
            VolumeSource,
        )

        buoy = BuoyLineSource(
            source_id="BLG", avg_line_length=100.0, avg_building_height=10.0, avg_building_width=10.0,
            avg_line_width=5.0, avg_building_separation=5.0, avg_buoyancy_parameter=100.0,
            line_segments=[
                BuoyLineSegment("BL1", 10.0, 20.0, 30.0, 20.0),
                BuoyLineSegment("BL2", 10.0, 40.0, 30.0, 40.0),
            ],
        )
        sources = [
            PointSource("PT", 1.0, 2.0), PointCapSource("CAP", 1.0, 2.0), PointHorSource("HOR", 1.0, 2.0),
            SidewashPointSource("SW", 1.0, 2.0), VolumeSource("VOL", 1.0, 2.0), AreaSource("AR", 1.0, 2.0),
            AreaCircSource("AC", 1.0, 2.0), OpenPitSource("PIT", 1.0, 2.0),
            AreaPolySource("AP", vertices=[(5.0, 6.0), (9.0, 6.0), (9.0, -3.0)]),
            LineSource("LN", 0.0, 0.0, 100.0, 0.0, initial_lateral_dimension=8.0),
            RLineSource("RL", 0.0, 0.0, 50.0, 50.0),
            RLineExtSource("RX", 0.0, 0.0, 1.0, 60.0, 60.0, 1.0),
            buoy,
        ]
        aermap = AERMAPProject.from_aermod_project(self._aermod(sources=sources), dem_files=["a.dem"])
        placed = {(s.source_id, s.source_type, s.x_coord, s.y_coord, s.x_end, s.y_end, s.width)
                  for s in aermap.sources}
        assert placed == {
            ("PT", "POINT", 1.0, 2.0, None, None, None),
            ("CAP", "POINTCAP", 1.0, 2.0, None, None, None),
            ("HOR", "POINTHOR", 1.0, 2.0, None, None, None),
            ("SW", "POINT", 1.0, 2.0, None, None, None),
            ("VOL", "VOLUME", 1.0, 2.0, None, None, None),
            ("AR", "AREA", 1.0, 2.0, None, None, None),
            ("AC", "AREACIRC", 1.0, 2.0, None, None, None),
            ("PIT", "OPENPIT", 1.0, 2.0, None, None, None),
            ("AP", "AREAPOLY", 5.0, 6.0, None, None, None),
            ("LN", "LINE", 0.0, 0.0, 100.0, 0.0, 8.0),
            ("RL", "RLINE", 0.0, 0.0, 50.0, 50.0, None),
            ("RX", "RLINE", 0.0, 0.0, 60.0, 60.0, None),
            ("BL1", "BUOYLINE", 10.0, 20.0, 30.0, 20.0, None),
            ("BL2", "BUOYLINE", 10.0, 40.0, 30.0, 40.0, None),
        }
        # The polygon's far vertex and the line ends count toward the extent.
        assert (aermap.anchor_x, aermap.anchor_y) == (0.0, -3.0)
        with_domain = AERMAPProject.from_aermod_project(
            self._aermod(sources=sources), dem_files=["a.dem"], buffer=10.0,
        )
        assert (with_domain.domain_x_min, with_domain.domain_y_min) == (-10.0, -13.0)
        assert (with_domain.domain_x_max, with_domain.domain_y_max) == (110.0, 70.0)
        aermap.to_aermap_input()

    @pytest.mark.parametrize("make, match", [
        (lambda: "not a source", "cannot place source 'not a source' of type str"),
        (lambda: __import__("pyaermod.sources", fromlist=["AreaPolySource"]).AreaPolySource("AP", vertices=[]),
         "AREAPOLY source AP has no vertices"),
        (lambda: __import__("pyaermod.sources", fromlist=["BuoyLineSource"]).BuoyLineSource(
            "BLG", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0), "BUOYLINE source BLG has no line segments"),
    ])
    def test_a_source_it_cannot_place_raises(self, make, match):
        project = self._aermod()
        project.sources.sources.append(make())
        with pytest.raises(ValueError, match=match):
            AERMAPProject.from_aermod_project(project, dem_files=["a.dem"])

    def test_every_grid_is_carried_without_its_old_elevations(self):
        from pyaermod.receptors import CartesianGrid, PolarGrid
        from pyaermod.sources import PointSource

        g1 = CartesianGrid(grid_name="G1", x_init=0.0, x_num=2, x_delta=10.0, y_init=0.0, y_num=2, y_delta=10.0,
                           grid_elevations=[[1.0, 1.0], [1.0, 1.0]], grid_hills=[[1.0, 1.0], [1.0, 1.0]])
        g2 = CartesianGrid(grid_name="G2", x_points=[-50.0, 5.0], y_points=[5.0])
        p1 = PolarGrid(grid_name="P1", x_origin=0.0, y_origin=0.0, distances=[100.0], directions=[0.0],
                       elevations=[[3.0]])
        p2 = PolarGrid(grid_name="P2", origin_source_id="STK", distances=[20.0], directions=[90.0])
        aermap = AERMAPProject.from_aermod_project(
            self._aermod(sources=[PointSource("STK", 500.0, 0.0)], cartesian=[g1, g2], polar=[p1, p2]),
            dem_files=["a.dem"], buffer=0.0,
        )
        assert [g.grid_name for g in aermap.grids] == ["G1", "G2", "P1", "P2"]
        assert aermap.grids[0].grid_elevations is None and aermap.grids[2].elevations is None
        # The AERMOD project's own grids are left alone.
        assert g1.grid_elevations is not None and p1.elevations == [[3.0]]
        # Extent: G2's x points, P1's 100 m ring, and P2's 20 m ring around STK.
        assert (aermap.domain_x_min, aermap.domain_y_min) == (-100.0, -100.0)
        assert (aermap.domain_x_max, aermap.domain_y_max) == (520.0, 100.0)
        rows = _cards(aermap.to_aermap_input(), "GRIDPOLR")
        assert ["P2", "ORIG", "500.00", "0.00"] in rows

    def test_nad_grids_dir_is_passed_on(self):
        from pyaermod.input_generator import DiscreteReceptor

        aermap = AERMAPProject.from_aermod_project(
            self._aermod(discrete=[DiscreteReceptor(1.0, 2.0)]), dem_files=["a.dem"], nad_grids_dir="/nadcon",
        )
        assert _cards(aermap.to_aermap_input(), "NADGRIDS") == [["/nadcon/"]]


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
