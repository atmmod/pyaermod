# Verdicts: v-run-out-geo
Tests (all in this directory; each fails at HEAD for the stated reason; run with the scratchpad venv; geo/folium/rasterio were all installed so nothing skipped):
test_runners.py (D1,D3,D4,D5), test_output.py (E1-E5), test_geo.py (G1-G5,G7,G8,G11,G12). Test files use only pyaermod + tests/fixtures; no conftest fixtures needed.

## D1 CONFIRMED (medium)
runner.py _stage -> _claim takes the flock, _prepare raises (dir named a.out cannot be unlinked), run() never reaches _unstage; the stdout/stderr opens at 435-436 are outside the try. With the exception kept alive the lock stays held (flock free test fails). Test: test_d1_failed_stage_or_capture_leaves_no_lock_or_link[a.out|a.subproc.stdout] (also asserts no aermod.inp left; the lock assertion is what fails first).
Fix blast radius: small. Judgement call: re-raise vs return failed AERMODRunResult (docstring says result); returning a failed result changes what callers see (today an exception). The test accepts neither choice beyond "lock released, no link left".

## D2 CONFIRMED BY DOCUMENTATION, not reproduced (Windows)
Python docs for msvcrt.locking: LK_LOCK "tries again after 1 second; after 10 attempts ... OSError is raised". Code at runner.py:1413-1415 uses LK_LOCK and the docstring promises unbounded blocking. No macOS test possible; a fake-msvcrt test would only assert the implementation, so none written. Fix (loop on LK_NBLCK with sleep) is safe.

## D3 CONFIRMED (medium)
Stand-in run 1 writes AERSCREEN.OUT + aerscreen.log with the success banner; stand-in run 2 prints an error, writes nothing, exits 0 -> success=True and summary parsed from the old output. Test: test_d3_aerscreen_does_not_report_success_from_a_previous_runs_files. (Whether real AERSCREEN truncates its log first is unknown; the stale-file hole is real regardless.) Fix: delete or snapshot-compare (the `before` snapshot exists). Blast radius: tests/test_aerscreen_runner.py stand-ins write fresh files each run so they should still pass.

## D4 PARTLY (medium)
True from the code: success = rc 0 and no "FATAL" in stdout; nothing checks that sfcchar_file was written, stderr unread. Test test_d4_... (stand-in exits 0, prints "ERROR", writes nothing -> must not be success) fails at HEAD. NOT verified: that real AERSURFACE actually exits 0 after an error (no binary here, no recorded stdout). Fix would BREAK existing tests: tests/test_aersurface_runner.py:54-60 (test_successful_run_writes_deck) uses a stand-in that writes nothing and asserts success; it must be updated to write the sfc file. Maintainer judgement: strictness vs a real run that writes the file elsewhere (relative sfcchar path resolves against the work dir; absolute paths elsewhere would need handling).

## D5 CONFIRMED (medium)
AERSCREEN stand-in backgrounds `sleep 60`; after run(timeout=1) returns "timed out" the grandchild is alive. Test: test_d5_aerscreen_timeout_kills_the_childs_children (kills the sleeper in its finally). Same mechanism applies to AERMET/AERSURFACE/AERMOD runners but only AERSCREEN has real children. Fix needs start_new_session + killpg (POSIX) and a Windows branch; Windows path untested here.

## E1 CONFIRMED (medium)
Fortran: aermod.f CHK_ENDYR (8055-8085) does NUMYRS=NUMYRS+1 then CALL PSTANN; output.f PSTANN writes `KURDAT, NUMYRS, GRPID, ...` per year. So an N-year ANNUAL file has IANHRS 1..N. Synthetic 3-year file reads as 1-HR/2-HR/3-HR with no warning. Test: test_e1_multi_year_annual_binary_postfile_is_not_labelled_n_hr (accepts either label ANNUAL or a ValueError asking for averaging_period). Note the file is synthetic (no real multi-year binary fixture).

## E2 CONFIRMED (medium)
Overflow row (13 asterisks in a width-preserving edit of tests/fixtures/postfile_types/conc/high_1h.plt): read_postfile returns 2 of 3 rows, no warning; aux reader returns the str. Tests: test_e2_postfile_keeps_row_with_overflowed_field_as_nan, test_e2_aux_reader_gives_numeric_column_for_overflowed_field. Expected behaviour (NaN, keep row) is the .out parser's existing convention; a judgement call only on whether to also warn.

## E3 CONFIRMED (medium)
Synthetic file written to the real FORMAT (output.f 9009 per reviewer) -> read_postfile date == "1ST". Test: test_e3_multi_year_max_daily_plotfile_date_is_not_the_rank_token. Synthetic header (no real fixture; test_real_cases.py:526 already notes the gap). I did not re-derive FORMAT 9009 from output.f myself beyond the reviewer's citation; the test asserts only that the rank token is not used as the date.

## E4 CONFIRMED (medium), one sub-claim REFUTED
Real fixtures: rank_1h.rnk and maxi_1h.max (tests/fixtures/fortran_exponents/washout_conc) -> file_type None (headers "RANK-FILE OF", "MAXI-FILE FOR"). albany_success 24H/01H/03H .plt -> averaging_period None; 24H file reports rank 24 for "HIGH   1ST HIGH 24-HR". read_deposition(output_parser/ddep_only/ddep_01H.plt) raises ValueError. read_plotfile(rank file) does not raise (guard off).
REFUTED part: "read_rankfile on a PLOTFILE passes": a real PLOTFILE is detected as PLOTFILE, so read_rankfile on it does raise; only the reverse (and any type-None file) slips through. Item 4 (SEASONHR branch) not tested (no real SEASONHR fixture).
Tests: test_e4_rankfile_and_maxifile_types_detected_on_real_files, test_e4_read_plotfile_rejects_a_rankfile, test_e4_short_term_plotfile_average_and_rank_from_real_headers, test_e4_read_deposition_accepts_a_real_deposition_plotfile.
Blast radius: tests/test_aermod_outputs.py uses invented headers (rank == 8 etc.); they must keep passing or be moved to real headers. read_deposition's DDEP/WDEP/TOTDEP types are public API (judgement: keep as alias).

## E5 CONFIRMED (medium)
ouset.f opens TOXXFILE FORM='UNFORMATTED' (reviewer's citation; I did not re-open ouset.f:2438). A binary file built to that layout returns latin-1 garbage records. Test: test_e5_toxxfile_binary_is_read_or_refused_not_decoded_as_text (passes if reader decodes values 2.5/3.5 or raises NotImplementedError/ValueError). Synthetic binary, no real TOXXFILE fixture. Minimum fix is the guard.

## E10 CONFIRMED (medium, performance; no pytest)
Measured: 1000 receptors x 400 binary hourly records = 400,000 rows took 3.8 s and 199 MB peak (tracemalloc) = ~500 bytes/row, so 8.76 M rows (1000 receptors x a year) is ~4.3 GB. Reviewer's 5.5 GB estimate is the right order. Perf, so no failing test written; a memory-ceiling test would be flaky.

## E11 CONFIRMED by Fortran (medium), judgement call, no test
calc2.f AVER (2407-2450): SNUM = MAX(NUMHRS-NUMCLM-NUMMSG, DNINT(0.75*NUMHRS+0.4)) and averaging is skipped when KAVE==1. output.f PERAVE: SNUM = IANHRS-IANCLM-IANMSG. So the reviewer's divisors are right. POSTFL (calc2.f ~2936-2965; called from the hour loop aermod.f ~1893 every averaging step) writes only X,Y,AVEVAL,ZELEV,ZHILL,ZFLAG,CHRAVE,GRPID,KURDAT,NETID (text) or KURDAT,KAVE,GRPID,values (binary): no calm/missing flag. An hourly POSTFILE therefore cannot reproduce AERMOD's 24-h/PERIOD mean on days with calm/missing hours; pyaermod's groupby mean divides by row count. Not repairable from the file; options are documentation or an optional calm-mask input. I did not check that calm-hour values are exactly 0 (affects only the size of the error, not its existence). Decision for maintainer.

## G1 CONFIRMED (high)
Hand-computed from soset.f 3036-3062: SW(1000,2000), X=40,Y=10: angle 0 -> (1000,2000),(1000,2010),(1040,2010),(1040,2000); angle 90 -> (1000,2000),(1010,2000),(1010,1960),(1000,1960). footprints.source_footprint matches (asserted as control in the test). geospatial gives area 1600 (centre-based, swapped, half-width). Tests: test_g1_area_polygon_corners_match_soset[0.0|90.0]. Cyclic-order/direction-insensitive comparison.

## G2 CONFIRMED (high, angle != 0 only)
soset.f 3524-3553 as above; angle 0 geospatial is right (that parametrisation passes), angle 90 gives (1000,2000),(1000,2040),(990,2040),(990,2000). Test: test_g2_openpit_polygon_corners_match_soset[90.0].
Blast radius for G1+G2 fix (use footprints): exported AREA/OPENPIT geometries change for every user (they were wrong); existing tests in tests/test_geospatial*.py may pin old coordinates. Check before merging. Also changes AREACIRC if G10 is done wholesale (separate finding, not tested here).

## G3 CONFIRMED (high)
Single-peak plume, bands from contourf: every band is MultiPolygon with is_valid False and no interiors (matplotlib 3.11.2). Test: test_g3_contour_bands_are_valid_nonoverlapping_with_holes (validity, presence of holes, areas sum equals union area; fails at the validity assert). Correct fix must be checked on matplotlib 3.7 and 3.8+ both paths (generate_contours has two code paths).

## G4 CONFIRMED (medium)
PolarGrid(origin_source_id="S1") with S1 at (500000,4500000): export_all writes the receptor at x=100.0 instead of 500100. footprints.receptor_points (control, asserted) gives (500100, 4500000). Test goes through the public VectorExporter.export_all so it fits any fix signature. Reviewer's extra claim (grid z_elev scalar, polar z_elev 0.0) not tested (READ only).

## G5 CONFIRMED (medium)
With requests.get mocked (no network) a stream that fails after 8192 bytes leaves the final-named .tif; a second call returns it as a cache hit without downloading. Test: test_g5_interrupted_dem_download_does_not_leave_a_cache_hit (asserts file absent after the failure and that a second call hits the network).

## G7 CONFIRMED (medium)
to_kmz with Point, Line, Area, AreaCirc: placemarks P1, A1, C1 only. L1 is dropped; A1/C1 are points. Test: test_g7_kmz_has_every_source_and_draws_areas_as_polygons. The "unused styles / per-source Transformer" sub-claims are READ only. Note the GUI wraps rows in _Point (results.py:655), so GUI output is unaffected; direct to_kmz callers are.

## G8 CONFIRMED (medium)
create_interactive_map with UTM x/y returns a folium Map whose location is (4500250, 500250). Test: test_g8_... passes if it raises ValueError or the centre is a valid lat/lon. Blast radius: existing tests/test_visualization.py::TestCreateInteractiveMap uses local x/y in +-500 m (not lat/lon either) with no zone; a fix that raises or requires a zone would break test_returns_map and siblings unless the new argument is optional with a no-conversion default. DESIGN DECISION for the maintainer (add utm_zone/transformer vs raise).

## G11 CONFIRMED (medium)
x-major table (X outer loop) -> plot_3d_surface passes Z with Z[0,1]=1 where the value at (x=100,y=0) is 10; assertion compares every Z[i,j] with the lookup for (X[i,j],Y[i,j]). Test: test_g11_surface_grid_is_independent_of_row_order (spies Axes3D.plot_surface). Only plot_3d_surface exercised; comparison grid (line 282) and animation (365) share the same reshape (READ).

## G12 CONFIRMED but a convention call (medium)
plot_concentration_profile with UTM X (500000..500500) draws axvline at 0: xlim becomes (-25025, 525525). Test: test_g12_profile_does_not_draw_a_source_line_at_x_zero_for_utm_data. For source-centred data (the shape the existing test fixtures use) 0,0 is the source, so the marker is right there; maintainer must decide whether the convention is "coordinates relative to the source" (then document it) or add source_xy=None. The (0,0) triangle in create_comparison_grid not separately tested.
