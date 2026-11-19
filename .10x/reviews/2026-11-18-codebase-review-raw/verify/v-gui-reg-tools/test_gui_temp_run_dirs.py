"""G8: a run directory the GUI created itself (blank working directory) goes when its run does."""

from pathlib import Path

from pyaermod.gui_v2.session import Session
from pyaermod.input_generator import DiscreteReceptor, PointSource
from pyaermod.runner import AERMODRunResult


class _Runner:
    def run(self, input_file, working_dir, timeout):
        out = Path(working_dir) / "pyaermod_gui.out"
        out.write_text("AERMOD output\n")
        return AERMODRunResult(success=False, input_file=str(input_file), output_file=str(out),
                               error_message="fake")


def test_the_temporary_run_directory_is_removed_when_new_discards_the_run():
    s = Session()
    s.add_source(PointSource(source_id="S", x_coord=0, y_coord=0, stack_height=10, stack_temp=400,
                             exit_velocity=10, stack_diameter=1, emission_rate=1))
    s.add_receptor(DiscreteReceptor(x_coord=100, y_coord=0))
    record = s.start_run(working_dir=None, runner=_Runner())
    work = Path(record.work_dir)
    assert work.is_dir()
    try:
        s.new()                       # the run history, and so its record, is gone
        assert not work.exists(), f"{work} was left behind"
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
