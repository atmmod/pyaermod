# slice-g findings (geospatial, footprints, kmz, visualization, advanced_viz, terrain, terrain_utils, aermap, aermet)

Repro scripts: <scratch>/repro/slice-g/{geom,holes,polar,kmz,adv,dl}.py
Fortran checked: aermod/soset.f ARVERT-equivalent vertex code at 3036-3062 (AREA) and 3524-3553 (OPENPIT): SW vertex first, p2 = p1 + Yinit*(sin a, cos a), p3 = p2 + Xinit*(cos a, -sin a), p4 = p3 - Yinit*(sin a, cos a); aermap/aermap_source_code_24142/aermap.f WRITRZ (8600-8714) and WRITDC FORMATs 3030/3031.

## Status of open 11-11 items in this slice (all three STILL PRESENT at HEAD)
- AREA polygon export wrong: G1 below (VERIFIED).
- OPENPIT rotation sign reversed: G2 (VERIFIED).
- Contour bands with holes become overlapping polygons: G3 (VERIFIED).
footprints.py is correct for AREA, OPENPIT, AREACIRC, AREAPOLY, line types (matches soset.f numerically, see geom.py). It is the right owner of the geometry; geospatial.py simply does not use it (nothing outside gui_v2/plan_view.py imports footprints).

---------------------------------------------------------------------------------------------------

### G1 [BUG] [high] sources_to_geodataframe: AREA rectangle is centred, half-width, x/y swapped, 4x the area, wrong rotation
- Where: src/pyaermod/geospatial.py:326-348
- What: treats x_coord/y_coord as the centre, uses Xinit as the y half-extent and Yinit as the x half-extent, and rotates CCW about the centre. AERMOD: SW vertex, Xinit east side, Yinit north side (both FULL lengths), rotated clockwise about the SW vertex. Every exported AREA polygon (GPKG/shapefile/GeoJSON via VectorExporter.export_sources/export_all) is in the wrong place, wrong orientation and 4x the area.
- Evidence: VERIFIED (repro/slice-g/geom.py). AREA at SW (1000,2000), Xinit=40, Yinit=10, angle 0: AERMOD/footprints give (1000,2000),(1000,2010),(1040,2010),(1040,2000), area 400; geospatial gives (990,1960),(1010,1960),(1010,2040),(990,2040), area 1600. At angle 90 AERMOD gives (1000,2000),(1010,2000),(1010,1960),(1000,1960); geospatial gives (1040,1990),(1040,2010),(960,2010),(960,1990).
- Fix: use footprints.source_footprint (see G10); Polygon(fp.parts[0]).

### G2 [BUG] [high] sources_to_geodataframe: OPENPIT rotates counter-clockwise
- Where: src/pyaermod/geospatial.py:279-300
- What: corners are SW + (Xinit east, Yinit north), correct at angle 0, but the rotation uses the CCW matrix (x cos - y sin, x sin + y cos). AERMOD rotates clockwise (soset.f 3532-3553). At any nonzero angle the pit is mirrored about its SW corner's north axis.
- Evidence: VERIFIED (geom.py). Pit SW (1000,2000), X=40, Y=10, angle 90: AERMOD (1000,2000),(1010,2000),(1010,1960),(1000,1960); geospatial (1000,2000),(1000,2040),(990,2040),(990,2000).
- Fix: same as G1.

### G3 [BUG] [high] ContourGenerator.generate_contours: rings of a band become overlapping solid polygons (holes lost), MultiPolygons invalid
- Where: src/pyaermod/geospatial.py:583-603
- What: every sub-path of a contourf level path (outer ring AND hole rings) is turned into its own Polygon and wrapped in MultiPolygon(polys). An annular band (any single-peak plume's middle bands) is therefore a disc covering its hole, overlapping the inner bands. The result is also not a valid MultiPolygon.
- Evidence: VERIFIED (holes.py, matplotlib 3.11.2): single Gaussian peak, levels [0,.3,.5,.9,1.1]: bands "0 - 0.3", "0.3 - 0.5", "0.5 - 0.9" are MultiPolygon, valid=False, 0 interiors; band areas sum to 5.95e6 m2 while the domain is 4.0e6 m2 (the 0-0.3 band alone is 4.7e6).
- Fix: combine the rings of one level with even-odd fill: `functools.reduce(lambda a, b: a.symmetric_difference(b), polys)` (after `Polygon(...).buffer(0)` for invalid rings), or use `path.to_polygons()` plus shapely `unary_union` of exterior-minus-interiors. Also drop the silent `except Exception: continue` (592). ContourPolygon in kmz_export has only outerBoundaryIs, so the KMZ path cannot carry holes either (G7).

### G4 [BUG] [medium] receptors_to_geodataframe ignores PolarGrid.origin_source_id (and other grid attributes)
- Where: src/pyaermod/geospatial.py:400-412 (also 389-398)
- What: polar receptors are placed about x_origin/y_origin, which are 0,0 when the grid is centred on a source (GRIDPOLR ORIG srcid). The method has no `sources` argument, so it cannot look the source up. The z_elev column is the grid scalar even when grid_elevations/elevations are filled (AERMAP-updated grids), and polar z_elev is hard-coded 0.0.
- Evidence: VERIFIED (polar.py): polar grid origin_source_id="S1" at (500000,4500000), one receptor 100 m east: geospatial gives (100.0, 6e-15); footprints.receptor_points gives (500100, 4500000).
- Fix: `receptors_to_geodataframe(receptors, sources=())` using `footprints.receptor_points(grid, sources=sources)` (G10) and pass project.sources.sources from VectorExporter.export_all.

### G5 [BUG] [medium] DEM tile download: truncated file is kept under its final name and then used as a cache hit
- Where: src/pyaermod/terrain.py:257-274
- What: the body is streamed straight to `output_dir/filename`. A connection reset, timeout or Ctrl-C mid-download leaves a truncated file; the next call sees `output_path.exists()` and returns it (the uncompress step swallows the read error, write_uncompressed_geotiff:110). AERMAP then reads a corrupt DEM. No size check against `tile.size_bytes` / Content-Length either.
- Evidence: VERIFIED (dl.py, requests.get mocked): after an 8192-byte partial write and a ConnectionError, a second call with the network disabled returns the truncated tif without downloading.
- Fix: write to `output_path.with_name(name + ".part")`, compare with Content-Length (or tile.size_bytes) when known, `os.replace` on success, unlink `.part` on exception. Remote file name: `Path(url).name` cannot contain a separator, so there is no traversal; a URL ending in `/..` gives name `..` (exists, returned as "cached"); reject names in ("", ".", "..") for tidiness (LOW).

### G6 [BUG] [medium] find_tiles asks the TNM API for max=50 products and never pages
- Where: src/pyaermod/terrain.py:177-182
- What: `"max": 50` with no `offset` loop. The API lists every dated version of a tile, so 50 products can be 15-25 distinct tiles; `newest_only` is applied after the cut. A large bounding box silently returns a DEM with holes (AERMAP E310 or zero terrain where tiles are missing).
- Evidence: READ (no network allowed). The response's `total` field is available.
- Fix: loop `offset` until `len(items) >= data["total"]` (cap the pages), and log a warning if truncated.

### G7 [BUG] [medium] KMZ export drops line sources and draws AREA/AREACIRC/OPENPIT as points; defines styles it never uses
- Where: src/pyaermod/kmz_export.py:219-254, 147-156
- What: sources are placed only via `vertices` (AREAPOLY) or `x_coord`/`y_coord`. LineSource, RLineSource, RLineExtSource and BuoyLineSource have neither (x_start/x_end) and vanish silently; AreaSource, AreaCircSource, OpenPitSource become a point at the SW corner/centre. `_placemark_line` (147-156) and the styles source-point, source-line, receptor (220, 222, 223) are never used (point placemarks carry no styleUrl). The GUI (gui_v2/pages/results.py:655-669) works around this by wrapping each summary row in a `_Point`.
- Evidence: VERIFIED (kmz.py): sources [Point, Line, Area, AreaCirc] -> placemarks P1, A1, C1 (L1 missing, A1 and C1 are points). KML itself is well-formed XML (parsed with minidom); namespace output is correct. ContourPolygon has no holes field and nothing converts a GeoDataFrame from ContourGenerator into ContourPolygon.
- Fix: iterate `source_footprint(src)` (G10): POINT -> `_placemark_point`, POLYGON -> `_placemark_polygon`, LINES -> `_placemark_line`; delete the unused styles. Also `_build_transformer` is constructed per call, i.e. once per source (302 sources = 302 `Transformer.from_crs`); build it once in `to_kmz`. UTM zone/hemisphere to EPSG is a third copy (G9).

### G8 [BUG] [medium] interactive map uses UTM metres as latitude/longitude
- Where: src/pyaermod/visualization.py:317-321 (centre), 331 (HeatMap data), 355 (markers), 364 (max marker)
- What: x/y are UTM easting/northing but folium takes (lat, lon). `center = (y_mid, x_mid)` is e.g. (4.5e6, 5e5): invalid latitude, so the map shows nothing useful; markers and the heat map have the same problem. There is no zone/hemisphere argument and no call to CoordinateTransformer.
- Evidence: READ. Only `center` can be overridden, and it does not fix the heat/marker coordinates.
- Fix: add `utm_zone`, `northern_hemisphere` (or a transformer) and convert once with `CoordinateTransformer.transform_dataframe`; or raise a clear error when no zone is given. Same page already has a `to_kmz` path that does this right.

### G9 [BUG] [low] UTM zone from longitude is wrong at 180 deg, and implemented three times
- Where: src/pyaermod/terrain_utils.py:102-112; src/pyaermod/geospatial.py:143 (`from_latlon`); src/pyaermod/kmz_export.py:74
- What: `floor((lon+180)/6)+1` gives 61 for lon=180.0 (accepted by the range check). Norway/Svalbard exceptions ignored (documentation only). Three separate zone/EPSG constructions (`32600+zone`, a `proj=utm` CRS, `from_latlon`).
- Evidence: VERIFIED (polar.py): `utm_zone_for_lon(180.0)` -> 61; `CoordinateTransformer.from_latlon(0, 180.0)` -> ValueError "UTM zone must be 1-60, got 61".
- Fix: one `min(int((lon + 180) // 6) + 1, 60)` in terrain_utils (or geospatial), imported by the others. Southern hemisphere handling in geospatial/kmz/terrain_utils is otherwise correct (south=True / 327xx / lat<0).

### G10 [CONCISION] [high] geospatial.py rebuilds the geometry footprints.py already owns (and gets it wrong); kmz_export does a weaker third version
- Where: geospatial.py:257-366 (sources, ~110 lines) and 386-421 (receptors, ~35 lines); kmz_export.py:227-254 (~28 lines)
- What: footprints.source_footprint/receptor_points are dependency-free, tested (tests/test_footprints.py) and match soset.f. geospatial.py duplicates it per source type with 4 of 7 geometry branches wrong (G1, G2, G4; AREACIRC uses an inscribed CCW-from-east polygon with `360 // max(n, 6)` step so n=7 gives 8 points and n=100 gives 120 (not the equal-area, north-first polygon AERMOD builds); BUOYLINE with no segments becomes `Point(0, 0)` where footprints raises ValueError).
- Change: geospatial keeps only an attribute table per type (emission_rate, release_height, ... ~20 lines) and builds shapely geometry from the Footprint: POINT -> Point, POLYGON -> Polygon, LINES -> LineString (1 part) or MultiLineString. Receptors: `[Point(p) for p in receptor_points(grid, sources=...)]` per grid. kmz_export consumes the same Footprint. Estimated saving: ~60 lines in geospatial, ~15 in kmz, plus three bug classes closed. Tests: tests/test_geospatial*.py, tests/test_kmz_export.py, tests/test_footprints.py (add the AREA/OPENPIT numbers from geom.py as geospatial regression tests).
- Owner: footprints.py (geometry); geospatial.py and kmz_export.py adapt.

### G11 [BUG] [medium] advanced_viz: grids built with reshape(len(y), len(x)) assume rows sorted y-major and complete
- Where: src/pyaermod/advanced_viz.py:69, 282, 365 (and the animation reuses the first frame's axes for every frame, 355-365)
- What: if the DataFrame is x-major, sorted otherwise, or missing receptors, the field is silently transposed/misplaced (or raises on a non-rectangular set). No sort or pivot.
- Evidence: VERIFIED (adv.py): 3x2 x-major table with CONC = 10*ix + iy gives Z[0,1] = 1 (that value belongs to x=0,y=100), while the true value at (100,0) is 10.
- Fix: `Z = df.pivot(index='Y', columns='X', values='CONC')` (sorted axes, NaN for gaps); one helper used at the three sites.

### G12 [BUG] [medium] advanced_viz hard-codes the source at (0, 0)
- Where: src/pyaermod/advanced_viz.py:219 (`axvline(0)` "Source"), 291, 374 (`ax.plot(0, 0, 'k^')`)
- What: results are in UTM or site coordinates; the "Source" marker and line are drawn at x=0/y=0, off the data for any real run (axes then stretch to include 0,0 or the marker is off-plot).
- Fix: take `source_xy=None` parameters and draw only when given.

### G13 [BUG] [low] wind rose bins are not centred on compass points; stacking recomputes histograms; dropped speeds
- Where: src/pyaermod/advanced_viz.py:136-157
- What: `np.linspace(0, 360, bins+1)` edges put "N" in 0-22.5 deg (bar centre 11.25). Winds due north (0 and 359 deg) land in two bars at 11.25 and 348.75 instead of one bar at 0. Speeds >= 100 and NaN are dropped but stay in the denominator. The `bottom=` expression recomputes every earlier histogram (O(bins^2)).
- Evidence: VERIFIED (adv.py): 50 winds at 0 deg + 50 at 359 deg give bars at 11.25 and 348.75 (50 % each).
- Fix: edges `np.linspace(-180/bins, 360-180/bins, bins+1)` with `(dirs + 180/bins) % 360`; keep a running `bottom` array; use `np.histogram2d` or a loop once.

### G14 [BUG] [low] animation fps becomes 0 for interval > 1000 ms
- Where: src/pyaermod/advanced_viz.py:392
- What: `PillowWriter(fps=1000//interval)`; interval=2000 gives fps=0 (VERIFIED value in adv.py; PillowWriter then divides by it on save: READ). Use `max(1, round(1000 / interval))`.

### G15 [BUG] [low] plot_contours: scatter fallbacks ignore save_path; cubic interpolation on collinear points; pyplot state
- Where: src/pyaermod/visualization.py:193-196, 210-213 (early `return fig` before the savefig at 277); 205 (`griddata(method='cubic')` on a single row/column raises QhullError although len(x) >= 4)
- What: the guard only checks the count of points, not that they span 2-D. All figures come from pyplot (`plt.subplots`/`plt.figure`) so repeated calls in a server/GUI leak figures (geospatial.py already switched to `Figure()` for this reason).
- Fix: apply `save_path` before each return (use one `_finish` helper, G16); catch QhullError and fall back to scatter; build figures with `Figure()` in library code.

### G16 [CONCISION] [medium] plotting boilerplate duplicated between visualization.py and advanced_viz.py
- Where: visualization.py 155-156, 401-402, 464-465 (matplotlib guard); 276-279, 436-437, 512-513 (savefig); advanced_viz.py 57-58, 123-124, 189-190, 251-252, 335-338 (guard) and 100-101, 166-167, 230-231, 314-315 (savefig); the unique/meshgrid/reshape block at 66-69, 279-282, 356-365; two unrelated column conventions (x/y/concentration in visualization, X/Y/CONC in advanced_viz) although `plotfile_frame` (visualization.py:35) already normalises.
- Change: one private module (e.g. `_plotting.py`, ~25 lines): `require_matplotlib()`, `finish(fig, save_path, dpi=300)`, `grid_from_xy(df)` (pivot, G11), and `plotfile_frame` accepted by AdvancedVisualizer so both classes read the same frame. Estimated removal ~60-70 lines net, and G11/G14/G15 fixed in one place. Tests: tests/test_visualization*.py, tests/test_advanced_viz*.py (existing figures-render tests).
- Owner: a shared module imported by both; plotfile_frame moves there.

### G17 [CONCISION] [low] demo `__main__` blocks (~245 lines) in library modules
- Where: aermap.py:745-823 (79), aermet.py:1259-1300 (42), visualization.py:565-608 (44), advanced_viz.py:398-479 (82)
- What: print-banner demos that write files into the working directory; excluded from coverage (.coveragerc `if __name__ == .__main__`), duplicated by examples/ and docs. Check cli.py and docs for `python -m pyaermod.visualization` before removing that one block (its usage text is the only documentation of that entry point).
- Change: delete (or move to examples/); no public API change.

### G18 [CONCISION] [low] geospatial per-row Point construction
- Where: geospatial.py:374, 442, 459 (`[Point(row.x, row.y) for ...]`, `iterrows` at 442 is the slow one)
- Change: `gpd.points_from_xy(df[x_col], df[y_col])` at all three; also in `generate_contours`/`export_geotiff` the NaN-fraction fallback block is copy-pasted (528-538 vs 696-702): one `_interpolate(x, y, z, grid, method)` helper. ~15 lines, large speed-up for 100k-receptor frames. Tests: test_geospatial*.py.

### G19 [CONCISION/DEAD] [low] terrain_utils / terrain / aermap leftovers
- SRTM skeleton: terrain_utils.py:119-162 (SRTMTileInfo, srtm_tile_name, srtm_tiles_for_bbox, ~45 lines) has no downloader; the module docstring (line 10) advertises `SRTMDownloader`, which does not exist (DOCS). Exported by api.py and tested, so deprecate rather than delete, or implement.
- `AERMAPDomain` (aermap.py:19-36) is not used by AERMAPProject or anything but geospatial.from_aermap_domain (tests only) and api.py; the method always sets hemisphere 'N' (documented). Candidate to deprecate.
- `create_grid_receptors_for_aermap` (aermap.py:725-742) is used only by one test. Minor bug: `int((x_max - x_min) / spacing) + 1` truncates float error: `(0.3 - 0.0) / 0.1` = 2.9999999999999996 gives 3 points, not 4 (READ/arithmetic). Use `int(round(...))` or `floor(x + 1e-9)`.
- terrain.py:986 `hasattr(aermap_project, "source_output") and ...` is always true. terrain.py:945-946: `DEMDownloader(cache_dir=work_dir/"dem_cache")` but tiles are saved to `work_dir/"dem_data"`, so `dem_cache` is never used (naming confusion; the cache check in download_tile applies to dem_data).
- terrain_utils.mosaic_dem_tiles (173-199) copies the first tile's profile, so a mosaic of USGS LZW/tiled tiles is itself LZW/tiled; AERMAP 24142 cannot read that (E455, per write_uncompressed_geotiff's own docstring). PLAUSIBLE, not run (needs rasterio and a compressed fixture). Call `write_uncompressed_geotiff` on the output or drop `compress`/`tiled` from the profile.
- terrain_utils.hill_height_diagnostics (286-356) compares consecutive records in file order, so the gradient test fires at the seam between two networks or from the end of one polar row to the next (LOW, PLAUSIBLE); the trailing flat-run anomaly reports x=y=0.

### G20 [BUG] [low] AERMAP deck cannot express a southern-hemisphere zone
- Where: src/pyaermod/aermap.py:487, 660-661 (`utm_zone` int, written as given); aermap/aermap_source_code_24142/sub_utmgeo.f:21-22
- What: UTMGEO documents that southern-hemisphere UTM-to-geographic conversion takes the zone number "preceded by a minus sign". AERMAPProject writes `utm_zone` as given and has no hemisphere field, and `utm_zone` is not range-checked (1-60). PLAUSIBLE: I did not trace whether ANCHORXY/DOMAINXY pass a negative zone through to UTMGEO, so this needs an AERMAP run with a southern site (or reading aermap.f's ANCHORXY and CHKEXT) before acting.

### G21 [BUG] [low] AERMET helpers
- write_aermet_runfile (aermet.py:805-841): the script is written to `run_aermet_stageN.sh` in the CURRENT directory, not `output_path` (docstring suggests the run directory is the script's concern; the file location is surprising), the deck and directory paths are interpolated into double quotes with no escaping (a path containing `"`, `$` or a backtick breaks or injects into the script), and `AERMET_EXE="aermet"` cannot be configured. READ.
- read_profile_file labels column 9 `temp_diff` (aermet.py:1036, 1075); the AERMET .PFL column is the ambient temperature (the comment on the same line says "or ambient temp"). Missing-value sentinels (999, 99.0, -999) are returned as data. READ; not checked against a .PFL fixture here.
- AERMETStation.time_zone is `int`; `int(time_zone)` truncates a half-hour zone (+5.5) to 5 silently (aermet.py:389, 409, 752). AERMET's adjustment field is an integer, so reject non-integers instead of truncating. READ.
- The Stage 1/METPREP writers otherwise match the keyword rules their comments cite; I did not re-verify each against aermet/ Fortran (only read for internal consistency).

---------------------------------------------------------------------------------------------------

## Checked and found fine
- aermap.py AERMAP deck writer, and terrain.py parsers: DISCCART (3030/3031: 2xF12.2 then F10.2 values), GRIDCART/GRIDPOLR ELEV/HILL/FLAG lines (3015-3017: `3X,A8,1X,A8,1X,'ELEV ',I4,6(1X,F8.1)`, rows = outer loop J, six values per line) are parsed correctly by whitespace splitting; FLAG rows are ignored; verdict parsing follows SUMTBL. Row index to y/direction mapping relies on the fixture-backed behaviour already tested; I did not re-derive RECART's receptor order.
- matplotlib 3.7 vs >=3.8 branches in generate_contours are both needed at the declared floor (matplotlib>=3.7; get_paths() on a ContourSet arrives in 3.8). Small point: on 3.8/3.9 `hasattr(cs, "collections")` itself emits a MatplotlibDeprecationWarning; test `hasattr(cs, "get_paths")` first.
- KMZ: valid KML 2.2 XML, closed rings, AABBGGRR colours, one colour per level.
- Southern-hemisphere CRS construction in CoordinateTransformer, kmz (327xx) and utm_epsg (lat < 0) is correct.
- Terrain remote filename: no path traversal possible via Path(url).name (see G5).

## Not looked at
- gui_v2/plan_view.py (consumer of footprints), aermet_runner.py, the AERMOD output parsers feeding the visualizers, and how GUI pages call these modules beyond the KMZ wrapper.
- No test files read beyond grepping for usage; no full test run (per brief). rasterio paths (mosaic, reproject, uncompressed rewrite) not executed.
- aermet.py keyword-by-keyword verification against aermet/ Fortran was not repeated.
