"""Library code must not write to stdout/stderr; it must use ``logging``.

Two guarantees are pinned here:

1. ``import pyaermod`` is silent in a fresh interpreter — no banner, no
   ``Warning: ... not installed`` chatter on stdout or stderr, regardless
   of which optional extras are present.
2. Progress messages that used to be ``print()`` calls inside library
   modules (``visualization``, ``output_parser``) now go through the
   module logger, so callers can route or silence them.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap

import pytest

import pyaermod.visualization as viz
from pyaermod.output_parser import AERMODResults, ConcentrationResult, ModelRunInfo


def _run_python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True, text=True, check=False,
    )


class TestImportIsSilent:
    def test_import_pyaermod_writes_nothing(self):
        proc = _run_python("import pyaermod")
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == ""
        assert not [
            line for line in proc.stderr.splitlines() if "Warning:" in line
        ], proc.stderr

    def test_import_silent_when_optional_viz_deps_missing(self):
        """Simulate a bare install: block folium/matplotlib before importing.

        ``sys.modules[name] = None`` makes ``import name`` raise
        ImportError, which is exactly the code path that used to print
        ``Warning: folium not installed.`` at import time.
        """
        proc = _run_python("""
            import sys
            for name in ("folium", "matplotlib", "matplotlib.pyplot"):
                sys.modules[name] = None
            import pyaermod
            import pyaermod.visualization as v
            assert not v.HAS_FOLIUM
            assert not v.HAS_MATPLOTLIB
        """)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == ""
        assert "not installed" not in proc.stderr

    def test_missing_dep_notice_is_debug_logged(self):
        """The one-time 'not installed' notice goes to the module logger at DEBUG."""
        proc = _run_python("""
            import logging, sys
            logging.basicConfig(level=logging.DEBUG, stream=sys.stderr, format="%(name)s|%(levelname)s|%(message)s")
            sys.modules["folium"] = None
            import pyaermod.visualization
        """)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout == ""
        assert "pyaermod.visualization|DEBUG|folium not installed" in proc.stderr


class TestLibraryUsesLogging:
    @pytest.mark.skipif(not viz.HAS_MATPLOTLIB, reason="matplotlib not installed")
    def test_plot_contours_save_logs_not_prints(self, tmp_path, capsys, caplog,
                                               sample_concentration_df):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        df = sample_concentration_df
        imax = df["concentration"].idxmax()
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "SILENCE_TEST"),
            sources=[], receptors=[],
            concentrations={"ANNUAL": ConcentrationResult(
                averaging_period="ANNUAL", data=df,
                max_value=float(df.loc[imax, "concentration"]),
                max_location=(float(df.loc[imax, "x"]), float(df.loc[imax, "y"])),
            )},
            output_file="silence.out",
        )
        target = tmp_path / "contour.png"
        with caplog.at_level(logging.INFO, logger="pyaermod.visualization"):
            fig = viz.AERMODVisualizer(results).plot_contours(
                show_sources=False, show_max=False, save_path=target, dpi=50,
            )
        plt.close(fig)
        assert target.exists()
        assert capsys.readouterr().out == ""
        assert any("Figure saved to" in r.getMessage() for r in caplog.records)

    def test_export_csv_logs_not_prints(self, tmp_path, capsys, caplog):
        results = AERMODResults(
            run_info=ModelRunInfo("24142", "SILENCE_TEST"),
            sources=[], receptors=[], concentrations={}, output_file="x.out",
        )
        with caplog.at_level(logging.INFO, logger="pyaermod.output_parser"):
            results.export_to_csv(tmp_path / "csv_out")
        assert (tmp_path / "csv_out").is_dir()
        assert capsys.readouterr().out == ""
        assert any("Exported results to" in r.getMessage() for r in caplog.records)
