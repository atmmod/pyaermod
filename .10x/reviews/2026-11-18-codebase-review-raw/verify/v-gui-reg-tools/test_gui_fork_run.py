"""G7: a forked tab must not present a run that is still going as "no run in progress".

Which of hand-over or adopt is right is the maintainer's choice; either way the fork must
know about the run (so Run is disabled and Cancel is offered) or never be created.
"""

from pyaermod.gui_v2.session import Session
from pyaermod.input_generator import DiscreteReceptor, PointSource


class _Handle:
    cancelled = False

    def cancel(self):
        self.cancelled = True
        return True


class _HangingRunner:
    """A background runner whose AERMOD never finishes during the test."""

    def start(self, input_file, working_dir, timeout, on_progress, on_finish):
        return _Handle()


def test_a_fork_made_during_a_run_still_shows_the_run_in_progress(tmp_path):
    s = Session(tab_id="a")
    s.add_source(PointSource(source_id="S", x_coord=0, y_coord=0, stack_height=10, stack_temp=400,
                             exit_velocity=10, stack_diameter=1, emission_rate=1))
    s.add_receptor(DiscreteReceptor(x_coord=100, y_coord=0))
    s.start_run(working_dir=tmp_path, runner=_HangingRunner(), background=True)
    assert s.run_in_progress is not None
    other = s.fork("b")
    assert other.run_in_progress is not None, "the fork offers Run and no Cancel while AERMOD runs"
