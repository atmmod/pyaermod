"""G4: a run's Results must describe that run when the working directory is reused."""

from pathlib import Path

from pyaermod.gui_v2 import run_results
from pyaermod.gui_v2.session import Session
from pyaermod.input_generator import DiscreteReceptor, PointSource
from pyaermod.runner import AERMODRunResult


class _Runner:
    def run(self, input_file, working_dir, timeout):
        out = Path(working_dir) / "pyaermod_gui.out"
        out.write_text("AERMOD output\n")
        return AERMODRunResult(success=False, input_file=str(input_file), output_file=str(out),
                               error_message="fake")


def _session():
    s = Session()
    s.add_source(PointSource(source_id="S", x_coord=0, y_coord=0, stack_height=10, stack_temp=400,
                             exit_velocity=10, stack_diameter=1, emission_rate=1))
    s.add_receptor(DiscreteReceptor(x_coord=100, y_coord=0))
    return s


def test_run_ones_view_shows_run_ones_deck_after_run_two_starts_in_the_same_folder(tmp_path):
    s = _session()
    s.set_control(title_one="RUN ONE")
    first = s.start_run(working_dir=tmp_path, runner=_Runner())
    s.set_control(title_one="RUN TWO")
    s.start_run(working_dir=tmp_path, runner=_Runner())
    # The Results step builds run 1's view only now (its page was not showing, or the
    # build was still hashing a large file when Run was clicked again).
    deck = run_results.view_of(first).deck.read()
    assert b"RUN ONE" in deck and b"RUN TWO" not in deck
