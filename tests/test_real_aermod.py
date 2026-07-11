"""
End-to-end regression against a real AERMOD binary.

Skips if `aermod` isn't on PATH. When it's present, this module:

1. Copies tests/fixtures/epa_official/aertest.inp + AERMET2.{SFC,PFL}
   into a temp directory and rewrites the met paths to bare filenames
2. Runs AERMOD once (shared session fixture) via the `AERMODRunner`
3. Asserts the run finishes successfully with the EPA success marker
4. Parses the AERTEST plotfile the run produced and confirms:
   - the headline peak concentration is in the expected range, and
   - **every receptor** matches EPA's published reference plotfile
     (tests/fixtures/epa_official/AERTEST_01H.PLT) to a tight tolerance.

Step 4's full-field comparison is the regulatory-grade check: it proves
pyaermod drives the real AERMOD Fortran to reproduce EPA's own published
concentrations, not merely that a run completes. The reference file was
produced by EPA with AERMOD 24142; a gfortran -O2 build of the same EPA
source reproduces all 144 AERTEST receptors bit-for-bit (to the 5 decimal
places the PLT format carries), so the tolerance below is tight with only
modest headroom for cross-compiler last-digit rounding.

One working end-to-end test matters more than any number of mocked
ones: it proves our input files are actually acceptable to the real
AERMOD Fortran code *and* numerically correct.

To enable locally:
    Make sure the `aermod` binary is on PATH, then:
    pytest tests/test_real_aermod.py -v
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyaermod import AERMODRunner, read_plotfile

FIXT = Path(__file__).parent / "fixtures" / "epa_official"

# Empirically, a gfortran -O2 build of the EPA AERMOD source reproduces the
# vendored EPA reference plotfile exactly. We allow a small relative tolerance
# (0.01%) plus a tiny absolute floor so the test stays robust to last-digit
# rounding differences across compilers/platforms while still catching any real
# regression (an input-generation bug shifts concentrations by far more than
# this). Loosen `REL_TOL` toward 1e-3 only if a CI compiler shows genuine drift.
REL_TOL = 1e-4
ABS_TOL = 1e-3

# The plotfile concentration column. read_plotfile() splits the "AVERAGE CONC"
# header field into two tokens; the value lives in AVERAGE.
CONC_COL = "AVERAGE"


def _aermod_available() -> bool:
    return shutil.which("aermod") is not None


pytestmark = pytest.mark.skipif(
    not _aermod_available(),
    reason="AERMOD binary not found on PATH",
)


def _prepare_workdir(work: Path) -> Path:
    """Copy AERTEST + met files into `work` and rewrite met paths.

    AERTEST's shipped input file uses relative paths of the form
    `../meteorology/AERMET2.SFC`. We flatten that to bare filenames
    so the test doesn't depend on the EPA archive layout.
    """
    shutil.copy(FIXT / "AERMET2.SFC", work / "AERMET2.SFC")
    shutil.copy(FIXT / "AERMET2.PFL", work / "AERMET2.PFL")
    text = (FIXT / "aertest.inp").read_text(encoding="utf-8")
    # Flatten every relative path that assumed the EPA archive layout.
    replacements = {
        "../meteorology/AERMET2.SFC": "AERMET2.SFC",
        "../meteorology/AERMET2.PFL": "AERMET2.PFL",
        "../Outputs/AERTEST_ERRORS.OUT": "AERTEST_ERRORS.OUT",
        "../Outputs/AERTEST.SUM": "AERTEST.SUM",
        "../plotfiles/AERTEST_01H.PLT": "AERTEST_01H.PLT",
        "../postfiles/AERTEST_01H.PST": "AERTEST_01H.PST",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    inp_path = work / "aertest.inp"
    inp_path.write_text(text, encoding="utf-8")
    return inp_path


@pytest.fixture(scope="session")
def aertest_run(tmp_path_factory):
    """Run the EPA AERTEST case once for the whole module.

    Returns the (RunResult, working_dir) pair so each test can make its
    own assertions without paying for repeated AERMOD invocations.
    """
    work = tmp_path_factory.mktemp("aertest")
    inp_path = _prepare_workdir(work)
    result = AERMODRunner().run(str(inp_path), working_dir=str(work), timeout=300)
    return result, work


def _receptor_conc_map(plot) -> dict[tuple[float, float], float]:
    """Map (x, y) -> concentration for every receptor in a parsed plotfile."""
    out: dict[tuple[float, float], float] = {}
    for r in plot.records:
        val = r[CONC_COL]
        if isinstance(val, (int, float)):
            out[(round(r["X"], 3), round(r["Y"], 3))] = val
    return out


def test_aermod_runs_aertest_successfully(aertest_run):
    """The canonical EPA AERTEST case must run to completion under the
    real AERMOD Fortran binary."""
    result, _work = aertest_run

    assert result.success, (
        f"AERMOD failed: return_code={result.return_code} "
        f"stderr={(result.stderr or '')[:500]}"
    )

    # Main .out file must have the success marker
    out_text = Path(result.output_file).read_text(encoding="latin-1")
    assert "FINISHES SUCCESSFULLY" in out_text.upper(), \
        "AERMOD .out missing success marker"


def test_aermod_aertest_peak_concentration(aertest_run):
    """After running, the AERTEST case's 1-hour high-1st peak should
    match the EPA-published value within a modest tolerance."""
    result, work = aertest_run
    assert result.success

    plots = list(work.glob("*.PLT")) + list(work.glob("*.plt"))
    if not plots:
        pytest.skip("AERTEST did not produce a .PLT file in this run")

    peak = max(_receptor_conc_map(read_plotfile(plots[0])).values())
    # EPA reference peak for AERTEST 1-HR is ~753.66 ug/m^3. Broad bounds
    # here; the bit-level check lives in the reference-comparison test.
    assert 400 < peak < 1500, (
        f"Peak concentration {peak} outside expected AERTEST range"
    )


def test_aermod_aertest_matches_epa_reference(aertest_run):
    """Every AERTEST receptor must match EPA's published reference plotfile.

    This is the regulatory-grade regression: it proves pyaermod drives the
    real AERMOD Fortran to reproduce EPA's own published concentrations
    receptor-for-receptor, not merely that a run completes.
    """
    result, work = aertest_run
    assert result.success

    plots = list(work.glob("*.PLT")) + list(work.glob("*.plt"))
    if not plots:
        pytest.skip("AERTEST did not produce a .PLT file in this run")

    got = _receptor_conc_map(read_plotfile(plots[0]))
    ref = _receptor_conc_map(read_plotfile(FIXT / "AERTEST_01H.PLT"))

    # The reference pins the AERTEST grid at 144 receptors.
    assert len(ref) == 144, f"reference receptor count changed: {len(ref)}"
    assert set(got) == set(ref), (
        "receptor coordinates differ from EPA reference; "
        f"symmetric difference: {sorted(set(got) ^ set(ref))[:5]}"
    )

    worst = None  # (rel_diff, coord, got, ref)
    for coord, ref_val in ref.items():
        got_val = got[coord]
        abs_diff = abs(got_val - ref_val)
        rel_diff = abs_diff / abs(ref_val) if ref_val else abs_diff
        if worst is None or rel_diff > worst[0]:
            worst = (rel_diff, coord, got_val, ref_val)
        assert abs_diff <= ABS_TOL + REL_TOL * abs(ref_val), (
            f"Receptor {coord}: got {got_val}, EPA reference {ref_val} "
            f"(abs diff {abs_diff:.6g}, rel diff {rel_diff:.3e}) "
            f"exceeds tolerance (rtol={REL_TOL}, atol={ABS_TOL})"
        )

    # Surface the closeness even on success — useful when CI tightens tol.
    print(
        f"\nAERTEST vs EPA reference: {len(ref)} receptors, "
        f"max rel diff {worst[0]:.3e} at {worst[1]} "
        f"(got {worst[2]}, ref {worst[3]})"
    )
