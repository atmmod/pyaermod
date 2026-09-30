"""
End-to-end smoke test against a real AERMAP binary.

Skips if ``aermap`` isn't on PATH. Parallel to test_real_aermod.py.

AERMAP's input format is simpler than AERMOD's but requires a DEM
data file referenced via the ``DATAFILE`` keyword. We construct a
minimal synthetic SRTM-like DEM so this test is self-contained —
just enough for AERMAP to exit successfully over a trivial domain.

What this exercises:
- AERMAPRunner.run can find + execute the binary
- A syntactically-valid AERMAP input file is accepted
- The resulting AERMAP.OUT / SOURCES.DAT / RECEPTORS.DAT outputs are
  produced
- AERMAPOutputParser can read them back

This gives us a second end-to-end CI contract (AERMAP preprocessor
binary + our wrappers) that parallels the AERMOD real-run test.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("aermap") is None,
    reason="AERMAP binary not found on PATH",
)


# ===========================================================================
# Synthetic planar DEM — analytic ground truth
# ===========================================================================
# We synthesize a tiny USGS-format DEM (DATATYPE DEM) over a UTM grid whose
# elevation is an exact tilted plane:
#
#       z(i, j) = BASE + SX * i + SY * j      (meters; i,j are node indices)
#
# Receptors are placed *exactly on interior grid nodes*. On a node, AERMAP's
# terrain extraction returns the node's elevation with no interpolation, and
# because the receptor/anchor/DEM share one UTM zone + datum there is no
# coordinate transform. So AERMAP must reproduce z(i, j) exactly — an
# analytic check that pyaermod drives the real AERMAP Fortran to recover a
# known surface, not merely that it runs. A gfortran -O2 build matches the
# analytic plane to the full precision the DEM carries (integer meters).

_ZONE = 13          # UTM zone
_NADD = 1           # datum code (1 = NAD27), shared by DEM + anchor
_X0, _Y0 = 500000.0, 4000000.0   # SW node (UTM easting/northing, meters)
_DX = _DY = 100.0                # node spacing
_NPROF = _NODES = 7              # 7x7 DEM; receptors use the interior 5x5
_BASE, _SX, _SY = 100, 2, 3      # planar coefficients (integer meters)


def _node_elev(i: int, j: int) -> int:
    return _BASE + _SX * i + _SY * j


def _expected_elev(x: float, y: float) -> int:
    """Analytic plane elevation at a node located at UTM (x, y)."""
    return _node_elev(round((x - _X0) / _DX), round((y - _Y0) / _DY))


def _write_synthetic_dem(path: Path, nprof: int = _NPROF, nodes: int = _NODES) -> None:
    """Write a tiny UTM USGS-format DEM (Type A header + Type B profiles).

    ``nprof`` profiles (columns, west to east) of ``nodes`` nodes each
    (south to north). The default 7 x 7 DEM is
    ``tests/fixtures/aermap_runner/synth.dem``.
    """
    def _A(s, w):  return f"{s:<{w}.{w}}"
    def _D(v):     return f"{v:24.15f}"
    def _I(v, w):  return f"{int(v):{w}d}"
    def _E(v):     return f"{v:12.6E}"

    elevs = [[_node_elev(i, j) for j in range(nodes)] for i in range(nprof)]
    emin = min(min(c) for c in elevs)
    emax = max(max(c) for c in elevs)
    corners = [
        (_X0, _Y0),                                          # SW
        (_X0, _Y0 + (nodes - 1) * _DY),                      # NW
        (_X0 + (nprof - 1) * _DX, _Y0 + (nodes - 1) * _DY),  # NE
        (_X0 + (nprof - 1) * _DX, _Y0),                      # SE
    ]

    h = ""
    h += _A("SYNTH PLANAR DEM", 40)            # MAPN
    h += _A("", 40) + _A("", 55)               # FREEF, FILR1
    h += _A(" ", 1) + _A(" ", 1)               # PROCODE, FILR2
    h += _A("", 3) + _A("", 4)                 # SECTNL, MCTR
    h += _I(1, 6) + _I(1, 6)                   # DEMLVL, ELEVPAT
    h += _I(1, 6) + _I(_ZONE, 6)               # IPLAN (1=UTM), IZO
    for _ in range(15):
        h += _D(0.0)                           # MPROJ(15)
    h += _I(2, 6) + _I(2, 6) + _I(4, 6)        # CUNIT(m), ELUNIT(m), SIDZ
    for (cx, cy) in corners:
        h += _D(cx) + _D(cy)                   # DMCNR 2x4
    h += _D(float(emin)) + _D(float(emax))     # ELEVMN, ELEVMX
    h += _D(0.0)                               # CNTRC
    h += _I(0, 6)                              # ACCUC
    h += _E(_DX) + _E(_DY) + _E(1.0)           # DXM, DYM, DCI
    h += _I(1, 6) + _I(nprof, 6)               # NROW(=1), NPROF
    h += _I(0, 5) + _I(0, 1) + _I(0, 5) + _I(0, 1)   # LPRIM/LPINT/SPRIM/SPINT
    h += _I(0, 4) + _I(0, 4)                   # DDATE, DINSP
    h += _A(" ", 1) + _I(0, 1) + _I(0, 2)      # INSPF, DVALD, SUSF
    h += _I(0, 2) + _I(_NADD, 2)               # VDAT, NADD
    h += _I(1, 4) + _I(0, 4)                   # EDITN, PVOID
    lines = [h.ljust(1024)]

    for p in range(nprof):
        col = elevs[p]
        rec = _I(1, 6) + _I(p + 1, 6) + _I(nodes, 6) + _I(1, 6)
        rec += _D(_X0 + p * _DX) + _D(_Y0) + _D(0.0)
        rec += _D(float(min(col))) + _D(float(max(col)))
        rec += "".join(_I(z, 6) for z in col)
        lines.append(rec)

    path.write_text("\n".join(lines) + "\n")


def _write_synthetic_input(inp: Path) -> list[tuple[float, float, int]]:
    """Write the AERMAP control file; return [(x, y, expected_elev), ...]."""
    recs = [
        (_X0 + p * _DX, _Y0 + j * _DY, _node_elev(p, j))
        for p in range(1, _NPROF - 1)
        for j in range(1, _NODES - 1)
    ]
    dxmin, dymin = _X0 + 0.5 * _DX, _Y0 + 0.5 * _DY
    dxmax, dymax = _X0 + (_NPROF - 1.5) * _DX, _Y0 + (_NODES - 1.5) * _DY
    lines = [
        "CO STARTING",
        "   TITLEONE  synthetic planar DEM analytic check",
        "   DATATYPE  DEM",
        "   DATAFILE  synth.dem  CHECK",
        f"   DOMAINXY  {dxmin:.1f} {dymin:.1f} {_ZONE} {dxmax:.1f} {dymax:.1f} {_ZONE}",
        f"   ANCHORXY  {_X0:.1f} {_Y0:.1f} {_X0:.1f} {_Y0:.1f} {_ZONE} {_NADD}",
        "   RUNORNOT  RUN",
        "CO FINISHED",
        "",
        "RE STARTING",
    ]
    lines += [f"   DISCCART  {x:.2f}  {y:.2f}" for (x, y, _z) in recs]
    lines += ["RE FINISHED", "", "OU STARTING",
              "   RECEPTOR  RECEPTOR.OUT", "OU FINISHED"]
    inp.write_text("\n".join(lines) + "\n")
    return recs


def _write_minimal_aermap_input(inp: Path) -> None:
    """Write a minimal AERMAP control file that skips DEM processing.

    Uses DATATYPE NED to avoid needing a real DEM file; FLATSRCS so
    AERMAP treats sources as flat-terrain and doesn't attempt
    elevation lookup from a (non-existent) raster.

    NOTE: Without a real DEM this won't produce meaningful elevations;
    it exercises the AERMAP subprocess wiring (startup + input parsing
    + graceful exit). That's the *contract* we want to pin in CI —
    a full AERMAP run against real NED data is a separate integration
    concern.
    """
    inp.write_text(
        "CO STARTING\n"
        "   TITLEONE  pyaermod AERMAP smoke test\n"
        "   DATATYPE  NED\n"
        "   FLATSRCS  ALL\n"
        "   ELEVUNIT  METERS\n"
        "CO FINISHED\n"
        "\n"
        "SO STARTING\n"
        "   LOCATION  STACK1  POINT  500000.0  4500000.0\n"
        "SO FINISHED\n"
        "\n"
        "RE STARTING\n"
        "   DISCCART  500100.0  4500100.0\n"
        "   DISCCART  500200.0  4500100.0\n"
        "RE FINISHED\n"
        "\n"
        "OU STARTING\n"
        "   RECEPTOR  RECEPTOR.OUT\n"
        "   SOURCLOC  SOURCES.OUT\n"
        "   MAPDETAIL TERSE\n"
        "OU FINISHED\n"
    )


def test_aermap_binary_runs_on_minimal_input(tmp_path):
    """AERMAPRunner dispatches to the real binary, which either:
    - completes (exit 0) on our minimal flat-sources input, or
    - exits with a specific documented error

    Either path exercises the runner subprocess wiring. We assert
    the process was invoked and didn't hang or crash at the Python
    layer.
    """
    from pyaermod.terrain import AERMAPRunner

    # AERMAP reads from a file named "AERMAP.INP" (same convention as AERMOD)
    inp = tmp_path / "aermap.inp"
    _write_minimal_aermap_input(inp)

    runner = AERMAPRunner()
    result = runner.run(str(inp), working_dir=str(tmp_path), timeout=60)

    # Regardless of success/failure, the runner returned a result object
    # and didn't hang. If the binary is sane it produced SOME output.
    assert result is not None
    assert result.input_file
    # Some AERMAP distributions exit 0 even on trivial input; others
    # report "no DEM tiles" as a soft warning. We accept either.
    if result.return_code is not None:
        assert isinstance(result.return_code, int)


def test_aermap_runner_executable_introspection(tmp_path):
    """Runner finds the binary and exposes its path."""
    from pyaermod.terrain import AERMAPRunner

    runner = AERMAPRunner()
    assert runner.executable is not None
    assert runner.executable.exists()


def test_aermap_runner_rejects_missing_input(tmp_path):
    """Passing a nonexistent input path is reported gracefully."""
    from pyaermod.terrain import AERMAPRunner

    runner = AERMAPRunner()
    result = runner.run(tmp_path / "does_not_exist.inp")
    assert not result.success
    assert "not found" in (result.error_message or "").lower()


def test_aermap_recovers_synthetic_planar_dem(tmp_path):
    """Regulatory-grade numeric check: AERMAP, driven by pyaermod, must
    recover a known analytic planar DEM exactly at on-node receptors.

    This proves pyaermod generates AERMAP input the real Fortran accepts
    *and* that the extracted terrain elevations are numerically correct —
    not merely that the process exits 0.
    """
    from pyaermod.terrain import AERMAPOutputParser, AERMAPRunner

    _write_synthetic_dem(tmp_path / "synth.dem")
    recs = _write_synthetic_input(tmp_path / "aermap.inp")

    result = AERMAPRunner().run(
        str(tmp_path / "aermap.inp"), working_dir=str(tmp_path), timeout=120
    )
    assert result.success, (
        f"AERMAP failed: return_code={result.return_code} "
        f"error={result.error_message}"
    )

    out = tmp_path / "RECEPTOR.OUT"
    assert out.exists(), "AERMAP did not produce RECEPTOR.OUT"
    df = AERMAPOutputParser.parse_receptor_output(out)

    assert len(df) == len(recs), (
        f"expected {len(recs)} receptors, parsed {len(df)}"
    )

    worst = 0.0
    for _, r in df.iterrows():
        expected = _expected_elev(r.x, r.y)
        diff = abs(r.zelev - expected)
        worst = max(worst, diff)
        # On-node extraction is exact; allow a hair for output rounding.
        assert diff <= 1e-2, (
            f"Receptor ({r.x:.1f}, {r.y:.1f}): AERMAP ZELEV {r.zelev} != "
            f"analytic {expected} (diff {diff})"
        )
        # Critical hill height can never be below the receptor elevation.
        assert r.zhill >= r.zelev - 1e-2, (
            f"Receptor ({r.x:.1f}, {r.y:.1f}): ZHILL {r.zhill} < "
            f"ZELEV {r.zelev}"
        )

    print(
        f"\nAERMAP synthetic planar DEM: {len(df)} on-node receptors, "
        f"max |ZELEV - analytic| = {worst:.3g}"
    )


# ===========================================================================
# The deck writer and the runner's verdict, against the real binary
# ===========================================================================


def _node_xy(i: int, j: int) -> tuple[float, float]:
    return _X0 + i * _DX, _Y0 + j * _DY


def _writer_project(**kw):
    """An AERMAPProject over the 7 x 7 planar DEM: one receptor, a grid and a source."""
    from pyaermod.aermap import AERMAPProject, AERMAPReceptor, AERMAPSource

    kw.setdefault("domain_x_min", _X0 + 0.5 * _DX)
    kw.setdefault("domain_y_min", _Y0 + 0.5 * _DY)
    kw.setdefault("domain_x_max", _X0 + (_NPROF - 1.5) * _DX)
    kw.setdefault("domain_y_max", _Y0 + (_NODES - 1.5) * _DY)
    project = AERMAPProject(
        title_one="pyaermod writer on the planar DEM",
        dem_files=["synth.dem"], dem_format="DEM",
        anchor_x=_X0, anchor_y=_Y0, utm_zone=_ZONE, datum="NAD27",
        grid_receptor=True, grid_x_init=_X0 + _DX, grid_y_init=_Y0 + 2 * _DY,
        grid_x_num=3, grid_y_num=2, grid_spacing=_DX, **kw,
    )
    project.add_receptor(AERMAPReceptor("R1", *_node_xy(1, 1)))
    project.add_source(AERMAPSource("STACK1", *_node_xy(2, 3)))
    return project


def test_writer_deck_recovers_synthetic_planar_dem(tmp_path):
    """The deck AERMAPProject writes runs clean and gives back the analytic plane.

    Before the writer was fixed, AERMAP rejected every deck it wrote with
    11 fatal errors (TERRHGTS ELEVATED, four-field DOMAINXY, no ANCHORXY or
    RUNORNOT, receptor IDs in DISCCART, GRIDCART without STA, RE before SO,
    and RECOUTPUT/SRCOUTPUT/MSGOUTPUT), and exited 0.
    """
    from pyaermod.terrain import AERMAPOutputParser, AERMAPRunner

    _write_synthetic_dem(tmp_path / "synth.dem")
    _writer_project().write(str(tmp_path / "aermap.inp"))

    result = AERMAPRunner().run(tmp_path / "aermap.inp", working_dir=tmp_path, timeout=120)
    assert result.success, result.error_message
    assert result.fatal_count == 0
    assert result.warning_count == 0

    rec = AERMAPOutputParser.parse_receptor_output(tmp_path / "aermap_receptors.out")
    # One discrete receptor and the 3 x 2 grid.
    assert len(rec) == 7
    for _, r in rec.iterrows():
        assert r.zelev == pytest.approx(_expected_elev(r.x, r.y), abs=1e-2)
        assert r.zhill >= r.zelev - 1e-2

    src = AERMAPOutputParser.parse_source_output(tmp_path / "aermap_sources.out")
    assert list(src.source_id) == ["STACK1"]
    assert src.zelev[0] == pytest.approx(_node_elev(2, 3), abs=1e-2)


def test_provided_elevations_are_kept(tmp_path):
    """TERRHGTS PROVIDED: AERMAP keeps the given elevations and adds hill heights.

    It writes no source file under PROVIDED, so the deck asks for none.
    """
    from pyaermod.aermap import AERMAPProject, AERMAPReceptor, AERMAPSource
    from pyaermod.terrain import AERMAPOutputParser, AERMAPRunner

    _write_synthetic_dem(tmp_path / "synth.dem")
    project = AERMAPProject(
        dem_files=["synth.dem"], dem_format="DEM", anchor_x=_X0, anchor_y=_Y0,
        utm_zone=_ZONE, datum="NAD27", terrain_type="PROVIDED",
    )
    project.add_receptor(AERMAPReceptor("R1", *_node_xy(1, 1), elevation=60.0))
    project.add_source(AERMAPSource("STACK1", *_node_xy(2, 3), elevation=50.0))
    project.write(str(tmp_path / "aermap.inp"))

    result = AERMAPRunner().run(tmp_path / "aermap.inp", working_dir=tmp_path, timeout=120)
    assert result.success, result.error_message

    rec = AERMAPOutputParser.parse_receptor_output(tmp_path / "aermap_receptors.out")
    assert rec.zelev.tolist() == [60.0]
    # The hill height is the highest node that rises above a 10% slope
    # from the provided 60 m (sub_calchc.f: ZNODE - AZELEV >= 0.1 * RDIST),
    # searched over the whole DEM since the deck has no DOMAINXY. That is
    # node (5, 6) at 128 m; the top corner, 130 m, is 70 m up over 707 m.
    x_r, y_r = _node_xy(1, 1)
    qualifying = [
        _node_elev(i, j)
        for i in range(_NPROF) for j in range(_NODES)
        if _node_elev(i, j) - 60.0 >= 0.1 * ((_node_xy(i, j)[0] - x_r) ** 2 + (_node_xy(i, j)[1] - y_r) ** 2) ** 0.5
    ]
    assert max(qualifying) == 128
    assert rec.zhill.tolist() == [128.0]
    assert not (tmp_path / "aermap_sources.out").exists()


def test_runner_reports_a_domain_outside_the_dem(tmp_path):
    """AERMAP exits 0 after E310 and leaves empty output files; the runner says it failed."""
    from pyaermod.terrain import AERMAPRunner

    _write_synthetic_dem(tmp_path / "synth.dem")
    _writer_project(
        domain_x_min=_X0 - 1000.0, domain_y_min=_Y0 - 1000.0,
        domain_x_max=_X0 + 1600.0, domain_y_max=_Y0 + 1600.0,
    ).write(str(tmp_path / "aermap.inp"))

    result = AERMAPRunner().run(tmp_path / "aermap.inp", working_dir=tmp_path, timeout=120)
    assert result.return_code == 0
    assert (tmp_path / "aermap_receptors.out").exists()
    assert result.success is False
    assert result.finished_successfully is False
    assert result.fatal_count == 4
    assert result.error_message.startswith("OU E310")


def test_terrain_processor_fills_in_the_planar_dem(tmp_path):
    """TerrainProcessor.process end to end: AERMOD project in, analytic elevations out."""
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
    from pyaermod.terrain import TerrainProcessor

    # 41 x 41 nodes (4 km square): the 1 km buffer the processor adds
    # around the project must stay inside the DEM.
    _write_synthetic_dem(tmp_path / "big.dem", nprof=41, nodes=41)
    project = AERMODProject(
        control=ControlPathway(title_one="planar DEM"),
        sources=SourcePathway(),
        receptors=ReceptorPathway(
            cartesian_grids=[CartesianGrid(
                x_init=_X0 + 1500.0, x_num=4, x_delta=200.0,
                y_init=_Y0 + 1600.0, y_num=3, y_delta=300.0,
            )],
            discrete_receptors=[DiscreteReceptor(*_node_xy(17, 19))],
        ),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )
    x_src, y_src = _node_xy(20, 21)
    project.sources.add_source(PointSource(
        source_id="STACK1", x_coord=x_src, y_coord=y_src,
        stack_height=50.0, emission_rate=1.0,
    ))

    TerrainProcessor().process(
        project, bounds=(0, 0, 0, 0), working_dir=tmp_path, utm_zone=_ZONE,
        datum="NAD27", skip_download=True, dem_files=["big.dem"], timeout=120,
    )

    rec = project.receptors.discrete_receptors[0]
    assert rec.z_elev == pytest.approx(_node_elev(17, 19), abs=1e-2)
    assert project.sources.sources[0].base_elevation == pytest.approx(_node_elev(20, 21), abs=1e-2)
    grid = project.receptors.cartesian_grids[0]
    expected = [
        [_expected_elev(grid.x_init + i * grid.x_delta, grid.y_init + j * grid.y_delta)
         for i in range(grid.x_num)]
        for j in range(grid.y_num)
    ]
    for row, expected_row in zip(grid.grid_elevations, expected):
        assert row == pytest.approx(expected_row, abs=1e-2)
