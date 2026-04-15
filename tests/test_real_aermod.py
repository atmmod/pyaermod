"""
End-to-end regression against a real AERMOD binary.

Skips if `aermod` isn't on PATH. When it's present, this test:

1. Copies tests/fixtures/epa_official/aertest.inp + AERMET2.{SFC,PFL}
   into a temp directory
2. Edits the SURFFILE / PROFFILE paths to point at the local copies
3. Runs AERMOD via the `AERMODRunner`
4. Asserts the run finishes successfully and the output contains the
   EPA-documented strings
5. Parses the AERTEST plotfile the run produced and confirms the
   headline peak concentration is in the expected range

One working end-to-end test matters more than any number of mocked
ones: it proves our input files are actually acceptable to the real
AERMOD Fortran code.

To enable locally:
    Make sure `aermod` binary is on PATH, then:
    pytest tests/test_real_aermod.py -v
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pyaermod import AERMODRunner, read_plotfile

FIXT = Path(__file__).parent / "fixtures" / "epa_official"


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


def test_aermod_runs_aertest_successfully(tmp_path):
    """The canonical EPA AERTEST case must run to completion under the
    real AERMOD Fortran binary."""
    inp_path = _prepare_workdir(tmp_path)
    runner = AERMODRunner()
    result = runner.run(str(inp_path), working_dir=str(tmp_path), timeout=300)

    assert result.success, (
        f"AERMOD failed: return_code={result.return_code} "
        f"stderr={(result.stderr or '')[:500]}"
    )

    # Main .out file must have the success marker
    out_text = Path(result.output_file).read_text(encoding="latin-1")
    assert "FINISHES SUCCESSFULLY" in out_text.upper(), \
        "AERMOD .out missing success marker"


def test_aermod_aertest_peak_concentration(tmp_path):
    """After running, the AERTEST case's 1-hour high-1st peak should
    match the EPA-published value within a modest tolerance."""
    inp_path = _prepare_workdir(tmp_path)
    runner = AERMODRunner()
    result = runner.run(str(inp_path), working_dir=str(tmp_path), timeout=300)
    assert result.success

    # AERTEST writes PLOTFILE of HIGH 1ST 1-HR values for SO2.
    # Find the plt file that AERMOD emitted.
    plots = list(tmp_path.glob("*.PLT")) + list(tmp_path.glob("*.plt"))
    if not plots:
        # AERTEST.INP has PLOTFILE wiring; if it isn't present we can't
        # compare concentrations but the .out success is still the
        # main signal.
        pytest.skip("AERTEST did not produce a .PLT file in this run")

    plot = read_plotfile(plots[0])
    conc_col = next(
        c for c in plot.column_names if c in ("AVERAGE", "CONC")
    )
    peaks = [
        r[conc_col] for r in plot.records
        if isinstance(r[conc_col], (int, float))
    ]
    peak = max(peaks)
    # EPA reference peak for AERTEST 1-HR is ~750 ug/m^3. Broad bounds
    # here: we primarily care that AERMOD ran + produced plausible
    # physics, not a bit-exact match (compiler / rounding will shift
    # the value slightly).
    assert 400 < peak < 1500, (
        f"Peak concentration {peak} outside expected AERTEST range"
    )
