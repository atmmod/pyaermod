"""H-2 / DOCS-1: run_all_qaqc must work on what read_surface_file returns (the documented workflow)."""

from pathlib import Path

from pyaermod import read_surface_file, run_all_qaqc

SFC = Path(__file__).resolve().parent.parent / "fixtures" / "postfile_types" / "HOUSTON_0228.SFC"
if not SFC.exists():    # run from the scratchpad: use the repo checkout
    SFC = Path("<repo>/tests/fixtures/postfile_types/HOUSTON_0228.SFC")


def test_a_surface_file_read_by_the_package_is_not_reported_as_all_missing():
    records = read_surface_file(SFC)["data"].to_dict("records")
    report = run_all_qaqc(records)
    assert report.n_missing == 0, report.dump(limit=10)
    assert not report.by_category("low_wind"), report.dump(limit=10)
