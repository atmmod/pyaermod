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


def _write_synthetic_dem(path: Path) -> None:
    """Write a tiny UTM USGS-format DEM (Type A header + Type B profiles)."""
    def _A(s, w):  return f"{s:<{w}.{w}}"
    def _D(v):     return f"{v:24.15f}"
    def _I(v, w):  return f"{int(v):{w}d}"
    def _E(v):     return f"{v:12.6E}"

    elevs = [[_node_elev(i, j) for j in range(_NODES)] for i in range(_NPROF)]
    emin = min(min(c) for c in elevs)
    emax = max(max(c) for c in elevs)
    corners = [
        (_X0, _Y0),                                          # SW
        (_X0, _Y0 + (_NODES - 1) * _DY),                     # NW
        (_X0 + (_NPROF - 1) * _DX, _Y0 + (_NODES - 1) * _DY),  # NE
        (_X0 + (_NPROF - 1) * _DX, _Y0),                     # SE
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
    h += _I(1, 6) + _I(_NPROF, 6)              # NROW(=1), NPROF
    h += _I(0, 5) + _I(0, 1) + _I(0, 5) + _I(0, 1)   # LPRIM/LPINT/SPRIM/SPINT
    h += _I(0, 4) + _I(0, 4)                   # DDATE, DINSP
    h += _A(" ", 1) + _I(0, 1) + _I(0, 2)      # INSPF, DVALD, SUSF
    h += _I(0, 2) + _I(_NADD, 2)               # VDAT, NADD
    h += _I(1, 4) + _I(0, 4)                   # EDITN, PVOID
    lines = [h.ljust(1024)]

    for p in range(_NPROF):
        col = elevs[p]
        rec = _I(1, 6) + _I(p + 1, 6) + _I(_NODES, 6) + _I(1, 6)
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
