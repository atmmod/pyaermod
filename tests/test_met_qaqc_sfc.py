"""H-2 / DOCS-1: run_all_qaqc must work on what read_surface_file returns (the documented workflow)."""

from pathlib import Path

from pyaermod import read_surface_file, run_all_qaqc

SFC = Path(__file__).resolve().parent / "fixtures" / "postfile_types" / "HOUSTON_0228.SFC"


def test_a_surface_file_read_by_the_package_is_not_reported_as_all_missing():
    records = read_surface_file(SFC)["data"].to_dict("records")
    report = run_all_qaqc(records)
    assert report.n_missing == 0, report.dump(limit=10)
    assert not report.by_category("low_wind"), report.dump(limit=10)


def test_kelvin_is_converted_and_aermet_missing_codes_are_missing():
    ok = {"wind_speed": 3.0, "wind_dir": 100.0, "temp": 280.0, "L": -50.0, "Zic": 800.0, "Zim": 500.0,
          "ustar": 0.3}
    bad = dict(ok, wind_speed=999.0, wind_dir=999.0, temp=999.0, L=-99999.0, Zic=-999.0, Zim=-999.0, ustar=-9.0)
    report = run_all_qaqc([ok, bad])
    assert report.n_missing == 1
    assert not report.by_category("extreme"), report.dump()
    assert not report.by_category("stability"), report.dump()


def test_the_isd_style_records_are_still_accepted():
    rec = {"wind_speed_ms": 2.0, "wind_dir": 90.0, "temp_c": 80.0}
    assert run_all_qaqc([rec]).by_category("extreme")
