"""
PyAERMOD Streamlit GUI

Interactive web-based GUI for the full AERMOD workflow:
project setup -> source/receptor editing on maps -> run AERMOD -> visualize -> export.

Launch with:
    pyaermod-gui
    # or
    streamlit run $(python -c "import pyaermod.gui; print(pyaermod.gui.__file__)")

Requires: pip install pyaermod[gui]
"""

from ._env import *
from ._forms import BuildingFormFactory, SourceFormFactory
from ._map import MapEditor
from ._serialize import ProjectSerializer

# ============================================================================
# SESSION STATE MANAGEMENT
# ============================================================================


class SessionStateManager:
    """Manages the AERMODProject and related state in st.session_state."""

    @staticmethod
    def initialize():
        """Set default session state values if not already present."""
        defaults = {
            "project_control": ControlPathway(
                title_one="New PyAERMOD Project",
                title_two="Created with PyAERMOD GUI",
            ),
            "project_sources": SourcePathway(),
            "project_receptors": ReceptorPathway(),
            "project_meteorology": MeteorologyPathway(
                surface_file="", profile_file="",
            ),
            "project_output": OutputPathway(),
            "utm_zone": 16,
            "hemisphere": "N",
            "datum": "WGS84",
            "center_lat": 33.75,
            "center_lon": -84.39,
            "run_result": None,
            "parsed_results": None,
            "postfile_results": None,
            "buildings": [],
            "aermet_mode": "files",
            "aermet_stage1": None,
            "aermet_stage2": None,
            "aermet_stage3": None,
            "project_events": None,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def get_project() -> AERMODProject:
        """Assemble an AERMODProject from session state components."""
        return AERMODProject(
            control=st.session_state["project_control"],
            sources=st.session_state["project_sources"],
            receptors=st.session_state["project_receptors"],
            meteorology=st.session_state["project_meteorology"],
            output=st.session_state["project_output"],
            events=st.session_state.get("project_events"),
        )

    @staticmethod
    def get_transformer() -> Optional["CoordinateTransformer"]:
        """Get CoordinateTransformer from session state UTM settings."""
        if not HAS_GEO:
            return None
        try:
            return CoordinateTransformer(
                utm_zone=st.session_state["utm_zone"],
                hemisphere=st.session_state["hemisphere"],
                datum=st.session_state["datum"],
            )
        except Exception:
            return None


# ============================================================================
# PROJECT SERIALIZER
# ============================================================================


def page_project_setup():
    """Project Setup page."""
    st.header("Project Setup")

    st.subheader("Project Titles")
    title1 = st.text_input(
        "Title Line 1",
        value=st.session_state["project_control"].title_one,
    )
    title2 = st.text_input(
        "Title Line 2",
        value=st.session_state["project_control"].title_two or "",
    )

    st.subheader("Coordinate Reference System")
    col1, col2, col3 = st.columns(3)
    with col1:
        utm_zone = st.number_input(
            "UTM Zone", min_value=1, max_value=60,
            value=st.session_state["utm_zone"],
        )
    with col2:
        hemisphere = st.selectbox(
            "Hemisphere",
            ["N", "S"],
            index=0 if st.session_state["hemisphere"] == "N" else 1,
        )
    with col3:
        datum = st.selectbox(
            "Datum",
            ["WGS84", "NAD83", "NAD27"],
            index=["WGS84", "NAD83", "NAD27"].index(st.session_state["datum"]),
        )

    st.subheader("Map Center (for interactive map views)")
    col4, col5 = st.columns(2)
    with col4:
        center_lat = st.number_input(
            "Latitude", value=st.session_state["center_lat"],
            min_value=-90.0, max_value=90.0, format="%.6f",
        )
    with col5:
        center_lon = st.number_input(
            "Longitude", value=st.session_state["center_lon"],
            min_value=-180.0, max_value=180.0, format="%.6f",
        )

    st.subheader("Model Configuration")
    col6, col7 = st.columns(2)
    with col6:
        pollutant_names = [p.name for p in PollutantType]
        current_poll = st.session_state["project_control"].pollutant_id
        if isinstance(current_poll, PollutantType):
            current_idx = pollutant_names.index(current_poll.name)
        else:
            current_idx = 0
        pollutant = st.selectbox("Pollutant", pollutant_names, index=current_idx)

    with col7:
        terrain_names = [t.name for t in TerrainType]
        current_terrain = st.session_state["project_control"].terrain_type
        if isinstance(current_terrain, TerrainType):
            terrain_idx = terrain_names.index(current_terrain.name)
        else:
            terrain_idx = 0
        terrain = st.selectbox("Terrain Type", terrain_names, index=terrain_idx)

    avg_options = ["1-HR", "2-HR", "3-HR", "4-HR", "6-HR", "8-HR", "12-HR", "24-HR",
                   "ANNUAL", "MONTH", "PERIOD"]
    # Convert stored values (e.g. "24") to display labels (e.g. "24-HR")
    _numeric_periods = {"1", "2", "3", "4", "6", "8", "12", "24"}
    current_avg = [
        f"{p}-HR" if p in _numeric_periods else p
        for p in (st.session_state["project_control"].averaging_periods or [])
    ]
    avg_display = st.multiselect("Averaging Periods", avg_options, default=current_avg)
    # Convert display labels back to backend values (strip "-HR" suffix)
    avg_periods = [p.replace("-HR", "") if p.endswith("-HR") else p for p in avg_display]

    # Deposition options
    with st.expander("Deposition Options"):
        dep_col1, dep_col2 = st.columns(2)
        with dep_col1:
            calc_ddep = st.checkbox(
                "Dry Deposition (DDEP)",
                value=st.session_state["project_control"].calculate_dry_deposition,
                key="setup_ddep",
            )
            calc_wdep = st.checkbox(
                "Wet Deposition (WDEP)",
                value=st.session_state["project_control"].calculate_wet_deposition,
                key="setup_wdep",
            )
        with dep_col2:
            calc_depos = st.checkbox(
                "Total Deposition (DEPOS)",
                value=st.session_state["project_control"].calculate_deposition,
                key="setup_depos",
            )

    # NO2/SO2 Chemistry Options
    chemistry_config = None
    if pollutant == "NO2":
        with st.expander("NO2 Chemistry Options"):
            method_names = [m.name for m in ChemistryMethod]
            existing_chem = getattr(
                st.session_state["project_control"], "chemistry", None,
            )
            default_method_idx = 0
            default_ratio = 0.5
            if existing_chem is not None:
                default_method_idx = method_names.index(existing_chem.method.name)
                default_ratio = existing_chem.default_no2_ratio

            chem_method = st.selectbox(
                "Chemistry Method", method_names, index=default_method_idx,
                key="chem_method",
            )
            no2_ratio_default = st.slider(
                "Default NO2/NOx Ratio", min_value=0.0, max_value=1.0,
                value=default_ratio, step=0.01, key="chem_no2_ratio",
            )

            oz_mode = st.radio(
                "Ozone Data Source",
                ["None", "File", "Uniform Value", "Sector Values"],
                horizontal=True, key="oz_mode",
            )

            ozone_data = None
            if oz_mode == "File":
                oz_file = st.text_input("Ozone Data File Path", value="", key="oz_file")
                if oz_file:
                    ozone_data = OzoneData(ozone_file=oz_file)
            elif oz_mode == "Uniform Value":
                oz_val = st.number_input(
                    "Ozone Concentration (ppb)", min_value=0.0, value=40.0,
                    key="oz_uniform_val",
                )
                ozone_data = OzoneData(uniform_value=oz_val)
            elif oz_mode == "Sector Values":
                n_oz_sectors = st.number_input(
                    "Number of Sectors", min_value=1, max_value=36,
                    value=6, key="oz_n_sectors",
                )
                oz_sector_vals = {}
                for i in range(int(n_oz_sectors)):
                    val = st.number_input(
                        f"Sector {i + 1} O3 (ppb)", min_value=0.0,
                        value=40.0, key=f"oz_sector_{i}",
                    )
                    oz_sector_vals[i + 1] = val
                ozone_data = OzoneData(sector_values=oz_sector_vals)

            nox_file = None
            if chem_method == "GRSM":
                nox_file = st.text_input(
                    "NOx Background File Path", value="", key="nox_file",
                )
                if not nox_file:
                    nox_file = None

            chemistry_config = ChemistryOptions(
                method=ChemistryMethod[chem_method],
                ozone_data=ozone_data,
                default_no2_ratio=no2_ratio_default,
                nox_file=nox_file,
            )

    # Save to session state — update the existing ControlPathway in-place
    # to preserve advanced fields (eventfil, urban_option, low_wind_option, etc.)
    # that are set on other pages.
    st.session_state["utm_zone"] = utm_zone
    st.session_state["hemisphere"] = hemisphere
    st.session_state["datum"] = datum
    st.session_state["center_lat"] = center_lat
    st.session_state["center_lon"] = center_lon
    ctrl = st.session_state["project_control"]
    ctrl.title_one = title1
    ctrl.title_two = title2 if title2 else None
    ctrl.pollutant_id = PollutantType[pollutant]
    ctrl.averaging_periods = avg_periods if avg_periods else ["ANNUAL"]
    ctrl.terrain_type = TerrainType[terrain]
    ctrl.calculate_dry_deposition = calc_ddep
    ctrl.calculate_wet_deposition = calc_wdep
    ctrl.calculate_deposition = calc_depos
    ctrl.chemistry = chemistry_config

    st.success("Project settings saved automatically.")

    # ------------------------------------------------------------------
    # Project Save / Load
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Project File")
    col_save, col_load = st.columns(2)

    with col_save:
        json_str = ProjectSerializer.serialize_session_state()
        # Derive filename from project title (sanitize for filesystem)
        _title = st.session_state["project_control"].title_one or "pyaermod_project"
        _safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in _title).strip()
        _safe_name = _safe_name.replace(" ", "_")[:60] or "pyaermod_project"
        st.download_button(
            "Download Project (.json)",
            json_str.encode("utf-8"),
            file_name=f"{_safe_name}.json",
            mime="application/json",
        )

    with col_load:
        uploaded = st.file_uploader("Load Project", type=["json"], key="project_load")
        if uploaded:
            # Guard against infinite rerun: only load if this is a new file
            file_id = f"{uploaded.name}_{uploaded.size}"
            if st.session_state.get("_last_loaded_project") == file_id:
                st.info("Project already loaded. Upload a different file or clear the uploader to reload.")
            else:
                raw = uploaded.getvalue().decode("utf-8")
                try:
                    new_state = ProjectSerializer.deserialize_session_state(raw)
                    for key, value in new_state.items():
                        st.session_state[key] = value
                    st.session_state["_last_loaded_project"] = file_id
                    st.success("Project loaded successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to load project: {e}")


def page_source_editor():
    """Source Editor page with interactive map."""
    st.header("Source Editor")

    sources = st.session_state["project_sources"].sources
    transformer = SessionStateManager.get_transformer()

    # Persist clicked coordinates across reruns
    if "source_clicked_x" not in st.session_state:
        st.session_state["source_clicked_x"] = 0.0
        st.session_state["source_clicked_y"] = 0.0

    # Determine map center: use last click location if available, else project center
    map_center_lat = st.session_state["center_lat"]
    map_center_lon = st.session_state["center_lon"]
    if transformer and (
        st.session_state["source_clicked_x"] != 0.0
        or st.session_state["source_clicked_y"] != 0.0
    ):
        try:
            click_lat, click_lon = transformer.utm_to_latlon(
                st.session_state["source_clicked_x"],
                st.session_state["source_clicked_y"],
            )
            map_center_lat = click_lat
            map_center_lon = click_lon
        except Exception:
            pass

    # Map and form in columns
    map_col, form_col = st.columns([3, 2])

    with map_col:
        st.subheader("Source Map")
        if HAS_FOLIUM and transformer:
            editor = MapEditor(
                transformer=transformer,
                center=(map_center_lat, map_center_lon),
            )
            clicked_utm = editor.render_source_editor(
                sources, st.session_state.get("buildings", []),
            )
            if clicked_utm:
                st.session_state["source_clicked_x"] = clicked_utm[0]
                st.session_state["source_clicked_y"] = clicked_utm[1]
                st.info(f"Clicked: UTM ({clicked_utm[0]:.2f}, {clicked_utm[1]:.2f})")
        else:
            st.info("Install pyproj and streamlit-folium for interactive map editing.")

    with form_col:
        st.subheader("Add Source")
        source_type = SourceFormFactory.render_source_type_selector()

        default_x = st.session_state["source_clicked_x"]
        default_y = st.session_state["source_clicked_y"]

        new_source = None
        if source_type == "Point":
            new_source = SourceFormFactory.render_point_source_form(default_x, default_y)
        elif source_type == "Area (Rectangular)":
            new_source = SourceFormFactory.render_area_source_form(default_x, default_y)
        elif source_type == "Area (Circular)":
            new_source = SourceFormFactory.render_area_circ_source_form(default_x, default_y)
        elif source_type == "Area (Polygon)":
            new_source = SourceFormFactory.render_area_poly_source_form(default_x, default_y)
        elif source_type == "Volume":
            new_source = SourceFormFactory.render_volume_source_form(default_x, default_y)
        elif source_type == "Line":
            new_source = SourceFormFactory.render_line_source_form(default_x, default_y)
        elif source_type == "RLine (Roadway)":
            new_source = SourceFormFactory.render_rline_source_form(default_x, default_y)
        elif source_type == "RLineExt (Extended Roadway)":
            new_source = SourceFormFactory.render_rlinext_source_form(default_x, default_y)
        elif source_type == "BuoyLine (Buoyant Line)":
            new_source = SourceFormFactory.render_buoyline_source_form(default_x, default_y)
        elif source_type == "OpenPit (Open Pit Mine)":
            new_source = SourceFormFactory.render_openpit_source_form(default_x, default_y)

        if new_source:
            # Validate source ID
            existing_ids = [s.source_id for s in st.session_state["project_sources"].sources]
            if len(new_source.source_id) > 12:
                st.error(f"Source ID '{new_source.source_id}' exceeds 12-character AERMOD limit.")
            elif not new_source.source_id.strip():
                st.error("Source ID cannot be empty.")
            elif new_source.source_id in existing_ids:
                st.error(f"Source ID '{new_source.source_id}' already exists. Use a unique ID.")
            else:
                st.session_state["project_sources"].add_source(new_source)
                st.success(f"Added {type(new_source).__name__}: {new_source.source_id}")
                st.rerun()

    # Source table
    st.subheader("Current Sources")
    if sources:
        rows = []
        for s in sources:
            row = {"ID": s.source_id, "Type": type(s).__name__}
            if hasattr(s, "x_coord"):
                row["X"] = s.x_coord
                row["Y"] = s.y_coord
            elif hasattr(s, "x_start"):
                row["X"] = s.x_start
                row["Y"] = s.y_start
            elif hasattr(s, "vertices") and s.vertices:
                # AreaPolySource — show first vertex as reference location
                row["X"] = s.vertices[0][0]
                row["Y"] = s.vertices[0][1]
            elif hasattr(s, "line_segments") and s.line_segments:
                # BuoyLineSource — show first segment start
                seg = s.line_segments[0]
                row["X"] = seg.x_start
                row["Y"] = seg.y_start
            row["Emission Rate"] = getattr(s, "emission_rate", "N/A")
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # Edit / Delete source
        edit_col, del_col = st.columns(2)
        with del_col:
            delete_idx = st.selectbox(
                "Select source to delete",
                range(len(sources)),
                format_func=lambda i: f"{sources[i].source_id} ({type(sources[i]).__name__})",
                key="src_del_idx",
            )
            if st.button("Delete Selected Source", type="secondary"):
                del st.session_state["project_sources"].sources[delete_idx]
                st.rerun()

        with edit_col:
            edit_idx = st.selectbox(
                "Select source to edit",
                range(len(sources)),
                format_func=lambda i: f"{sources[i].source_id} ({type(sources[i]).__name__})",
                key="src_edit_idx",
            )
            src = sources[edit_idx]
            with st.expander(f"Edit {src.source_id} ({type(src).__name__})", expanded=False):
                _edited = False
                if hasattr(src, "emission_rate"):
                    new_er = st.number_input(
                        "Emission Rate", value=float(src.emission_rate),
                        min_value=0.0, format="%.6f", key=f"edit_er_{edit_idx}",
                    )
                    if new_er != src.emission_rate:
                        src.emission_rate = new_er
                        _edited = True
                if hasattr(src, "stack_height"):
                    new_h = st.number_input(
                        "Stack Height (m)", value=float(src.stack_height),
                        min_value=0.0, key=f"edit_h_{edit_idx}",
                    )
                    if new_h != src.stack_height:
                        src.stack_height = new_h
                        _edited = True
                if hasattr(src, "stack_temp"):
                    new_t = st.number_input(
                        "Stack Temperature (K)", value=float(src.stack_temp),
                        min_value=0.0, key=f"edit_t_{edit_idx}",
                    )
                    if new_t != src.stack_temp:
                        src.stack_temp = new_t
                        _edited = True
                if hasattr(src, "exit_velocity"):
                    new_v = st.number_input(
                        "Exit Velocity (m/s)", value=float(src.exit_velocity),
                        min_value=0.0, key=f"edit_v_{edit_idx}",
                    )
                    if new_v != src.exit_velocity:
                        src.exit_velocity = new_v
                        _edited = True
                if hasattr(src, "stack_diameter"):
                    new_d = st.number_input(
                        "Stack Diameter (m)", value=float(src.stack_diameter),
                        min_value=0.0, key=f"edit_d_{edit_idx}",
                    )
                    if new_d != src.stack_diameter:
                        src.stack_diameter = new_d
                        _edited = True
                if hasattr(src, "release_height"):
                    new_rh = st.number_input(
                        "Release Height (m)", value=float(src.release_height),
                        min_value=0.0, key=f"edit_rh_{edit_idx}",
                    )
                    if new_rh != src.release_height:
                        src.release_height = new_rh
                        _edited = True
                if _edited:
                    st.success("Source updated.")
    else:
        st.info("No sources defined yet. Use the form above or click on the map to add sources.")

    # ------------------------------------------------------------------
    # Source Group Management
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Source Groups")

    sp = st.session_state["project_sources"]
    existing_groups = sp.group_definitions

    if existing_groups:
        group_rows = []
        for g in existing_groups:
            group_rows.append({
                "Group Name": g.group_name,
                "Members": ", ".join(g.member_source_ids),
                "Description": g.description,
            })
        st.dataframe(pd.DataFrame(group_rows), use_container_width=True)

        del_grp_idx = st.selectbox(
            "Select group to delete",
            range(len(existing_groups)),
            format_func=lambda i: existing_groups[i].group_name,
            key="grp_delete_idx",
        )
        if st.button("Delete Selected Group", type="secondary"):
            del sp.group_definitions[del_grp_idx]
            st.rerun()

    with st.expander("Add Source Group", expanded=not bool(existing_groups)):
        available_ids = [s.source_id for s in sources]
        if available_ids:
            with st.form("source_group_form"):
                grp_name = st.text_input(
                    "Group Name (max 8 chars)", value="GRP1", max_chars=8,
                )
                grp_members = st.multiselect("Member Sources", available_ids)
                grp_desc = st.text_input("Description (optional)", value="")

                if st.form_submit_button("Add Source Group"):
                    if grp_name and grp_members:
                        sp.group_definitions.append(
                            SourceGroupDefinition(
                                group_name=grp_name,
                                member_source_ids=grp_members,
                                description=grp_desc,
                            )
                        )
                        st.success(f"Added group: {grp_name}")
                        st.rerun()
                    else:
                        st.error("Group name and at least one member are required.")
        else:
            st.info("Add sources first to create source groups.")

    # ------------------------------------------------------------------
    # Building Downwash (BPIP)
    # ------------------------------------------------------------------
    if HAS_BPIP:
        st.markdown("---")
        st.subheader("Building Downwash (BPIP)")

        buildings = st.session_state.get("buildings", [])

        with st.expander("Add Building", expanded=not bool(buildings)):
            new_building = BuildingFormFactory.render_building_form(
                default_x, default_y,
            )
            if new_building:
                st.session_state["buildings"].append(new_building)
                st.success(f"Added building: {new_building.building_id}")
                st.rerun()

        if buildings:
            bldg_rows = []
            for b in buildings:
                centroid = b.get_centroid()
                bldg_rows.append({
                    "ID": b.building_id,
                    "Height (m)": b.height,
                    "X (centroid)": f"{centroid[0]:.2f}",
                    "Y (centroid)": f"{centroid[1]:.2f}",
                    "Area (m2)": f"{b.get_footprint_area():.1f}",
                })
            st.dataframe(pd.DataFrame(bldg_rows), use_container_width=True)

            del_idx = st.selectbox(
                "Select building to delete",
                range(len(buildings)),
                format_func=lambda i: buildings[i].building_id,
                key="bldg_delete_idx",
            )
            if st.button("Delete Building", type="secondary"):
                del st.session_state["buildings"][del_idx]
                st.rerun()

            # Run BPIP calculation
            downwash_sources = [
                s for s in sources
                if isinstance(s, (PointSource, AreaSource, VolumeSource))
            ]
            if downwash_sources:
                st.markdown("**Calculate Downwash**")
                col_src, col_bldg = st.columns(2)
                with col_src:
                    src_idx = st.selectbox(
                        "Source",
                        range(len(downwash_sources)),
                        format_func=lambda i: (
                            f"{downwash_sources[i].source_id} "
                            f"({type(downwash_sources[i]).__name__})"
                        ),
                        key="bpip_src_idx",
                    )
                with col_bldg:
                    bldg_idx = st.selectbox(
                        "Building",
                        range(len(buildings)),
                        format_func=lambda i: buildings[i].building_id,
                        key="bpip_bldg_idx",
                    )
                if st.button("Run BPIP Calculation", type="primary"):
                    ps = downwash_sources[src_idx]
                    bldg = buildings[bldg_idx]
                    try:
                        calc = BPIPCalculator(bldg, ps.x_coord, ps.y_coord)
                        result = calc.calculate_all()
                        ps.building_height = result.buildhgt
                        ps.building_width = result.buildwid
                        ps.building_length = result.buildlen
                        ps.building_x_offset = result.xbadj
                        ps.building_y_offset = result.ybadj
                        st.success(
                            f"Downwash calculated for {ps.source_id} "
                            f"from {bldg.building_id}"
                        )
                        with st.expander("View BPIP Results"):
                            dirs = [f"{(i+1)*10}\u00b0" for i in range(36)]
                            bpip_df = pd.DataFrame({
                                "Direction": dirs,
                                "BUILDHGT": result.buildhgt,
                                "BUILDWID": result.buildwid,
                                "BUILDLEN": result.buildlen,
                                "XBADJ": result.xbadj,
                                "YBADJ": result.ybadj,
                            })
                            st.dataframe(bpip_df, use_container_width=True)
                    except Exception as e:
                        st.error(f"BPIP calculation failed: {e}")
            else:
                st.info("Add point, area, or volume sources to calculate building downwash.")

    # ------------------------------------------------------------------
    # Background Concentration
    # ------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Background Concentration")

    bg = st.session_state["project_sources"].background
    bg_mode = st.radio(
        "Background Mode",
        ["None", "Uniform", "Period-specific", "Sector-dependent"],
        index=0 if bg is None else (
            1 if bg.uniform_value is not None else (
                2 if bg.period_values else 3
            )
        ),
        key="bg_mode",
        horizontal=True,
    )

    if bg_mode == "Uniform":
        bg_val = st.number_input(
            "Background Concentration (ug/m3)", min_value=0.0, value=0.0,
            key="bg_uniform_val",
        )
        st.session_state["project_sources"].background = BackgroundConcentration(
            uniform_value=bg_val,
        )
    elif bg_mode == "Period-specific":
        avg_periods = st.session_state["project_control"].averaging_periods
        if not avg_periods:
            avg_periods = ["ANNUAL"]
        period_vals = {}
        for period in avg_periods:
            val = st.number_input(
                f"Background for {period} (ug/m3)", min_value=0.0, value=0.0,
                key=f"bg_period_{period}",
            )
            period_vals[period] = val
        st.session_state["project_sources"].background = BackgroundConcentration(
            period_values=period_vals,
        )
    elif bg_mode == "Sector-dependent":
        n_sectors = st.number_input(
            "Number of Sectors", min_value=2, max_value=12, value=4,
            key="bg_n_sectors",
        )
        sectors = []
        sector_values = {}
        step = 360.0 / n_sectors
        avg_periods = st.session_state["project_control"].averaging_periods or ["ANNUAL"]

        for i in range(n_sectors):
            sid = i + 1
            start_dir = i * step
            end_dir = (i + 1) * step
            sectors.append(BackgroundSector(sid, start_dir, end_dir))
            col_dir, col_val = st.columns([1, 2])
            with col_dir:
                st.text(f"Sector {sid}: {start_dir:.0f}-{end_dir:.0f} deg")
            with col_val:
                for period in avg_periods:
                    val = st.number_input(
                        f"S{sid} {period} (ug/m3)", min_value=0.0, value=0.0,
                        key=f"bg_sector_{sid}_{period}",
                    )
                    sector_values[(sid, period)] = val
        st.session_state["project_sources"].background = BackgroundConcentration(
            sectors=sectors,
            sector_values=sector_values,
        )
    else:
        st.session_state["project_sources"].background = None


def _apply_aermap_receptor_elevations(
    discrete_receptors: list, rec_df: "pd.DataFrame", tolerance: float = 0.5,
) -> int:
    """Match AERMAP receptor output to discrete receptors by (x, y) within tolerance."""
    updated = 0
    for rec in discrete_receptors:
        mask = (
            (rec_df["x"] - rec.x_coord).abs() < tolerance
        ) & (
            (rec_df["y"] - rec.y_coord).abs() < tolerance
        )
        match = rec_df[mask]
        if not match.empty:
            rec.z_elev = float(match.iloc[0]["zelev"])
            if "zhill" in match.columns:
                rec.z_hill = float(match.iloc[0]["zhill"])
            updated += 1
    return updated


def _apply_aermap_source_elevations(
    sources: list, src_df: "pd.DataFrame",
) -> int:
    """Match AERMAP source output to sources by source_id."""
    updated = 0
    for source in sources:
        mask = src_df["source_id"].str.strip() == source.source_id.strip()
        match = src_df[mask]
        if not match.empty:
            source.base_elevation = float(match.iloc[0]["zelev"])
            updated += 1
    return updated


def page_receptor_editor():
    """Receptor Editor page with grid definition and map preview."""
    st.header("Receptor Editor")

    receptors = st.session_state["project_receptors"]
    transformer = SessionStateManager.get_transformer()

    tab_cart, tab_polar, tab_discrete, tab_import, tab_aermap = st.tabs([
        "Cartesian Grid", "Polar Grid", "Discrete Receptors",
        "Import CSV", "Import AERMAP Elevations",
    ])

    with tab_cart:
        st.subheader("Cartesian Receptor Grid")
        with st.form("cartesian_grid_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Grid Name", value="GRID1")
                x_min = st.number_input("X Min (UTM m)", value=0.0, format="%.2f")
                x_max = st.number_input("X Max (UTM m)", value=2000.0, format="%.2f")
            with col2:
                spacing = st.number_input("Spacing (m)", value=100.0, min_value=1.0)
                y_min = st.number_input("Y Min (UTM m)", value=0.0, format="%.2f")
                y_max = st.number_input("Y Max (UTM m)", value=2000.0, format="%.2f")

            if st.form_submit_button("Add Cartesian Grid"):
                if x_max <= x_min or y_max <= y_min:
                    st.error("Max coordinates must be greater than Min coordinates.")
                elif spacing > (x_max - x_min) or spacing > (y_max - y_min):
                    st.error("Spacing is larger than the grid extent. Use a smaller spacing.")
                else:
                    grid = CartesianGrid.from_bounds(x_min, x_max, y_min, y_max, spacing, name)
                    receptors.add_cartesian_grid(grid)
                    n_pts = grid.x_num * grid.y_num
                    st.success(f"Added grid '{name}' ({grid.x_num} x {grid.y_num} = {n_pts} receptors)")
                    st.rerun()

    with tab_polar:
        st.subheader("Polar Receptor Grid")
        with st.form("polar_grid_form"):
            col1, col2 = st.columns(2)
            with col1:
                pname = st.text_input("Grid Name", value="POLAR1")
                x_orig = st.number_input("X Origin (UTM m)", value=0.0, format="%.2f")
                y_orig = st.number_input("Y Origin (UTM m)", value=0.0, format="%.2f")
            with col2:
                d_init = st.number_input("Start Distance (m)", value=100.0, min_value=0.0)
                d_num = st.number_input("Number of Rings", value=10, min_value=1, step=1)
                d_delta = st.number_input("Distance Increment (m)", value=100.0, min_value=1.0)
            dir_num = st.number_input("Number of Directions", value=36, min_value=1, step=1)

            if st.form_submit_button("Add Polar Grid"):
                grid = PolarGrid(
                    grid_name=pname, x_origin=x_orig, y_origin=y_orig,
                    dist_init=d_init, dist_num=int(d_num), dist_delta=d_delta,
                    dir_init=0.0, dir_num=int(dir_num),
                    dir_delta=360.0 / int(dir_num),
                )
                receptors.add_polar_grid(grid)
                st.success(f"Added polar grid '{pname}' ({int(d_num)} x {int(dir_num)} = {int(d_num) * int(dir_num)} receptors)")
                st.rerun()

    with tab_discrete:
        st.subheader("Discrete Receptors")

        # Click-to-place via map
        if HAS_FOLIUM and transformer:
            editor = MapEditor(
                transformer=transformer,
                center=(st.session_state["center_lat"], st.session_state["center_lon"]),
            )
            clicked = editor.render_receptor_editor(
                receptors, st.session_state["project_sources"].sources,
            )
            if clicked:
                st.info(f"Clicked: UTM ({clicked[0]:.2f}, {clicked[1]:.2f})")

        with st.form("discrete_receptor_form"):
            dlabel = st.text_input(
                "Label (optional)", value="",
                help="Descriptive name (e.g., School, Hospital). Not sent to AERMOD.",
                key="disc_label",
            )
            col1, col2, col3 = st.columns(3)
            with col1:
                dx = st.number_input("X (UTM m)", value=0.0, format="%.2f", key="disc_x")
            with col2:
                dy = st.number_input("Y (UTM m)", value=0.0, format="%.2f", key="disc_y")
            with col3:
                dz = st.number_input("Z Elevation (m)", value=0.0, format="%.2f", key="disc_z")

            if st.form_submit_button("Add Discrete Receptor"):
                receptors.add_discrete_receptor(DiscreteReceptor(dx, dy, dz, label=dlabel))
                display = f" '{dlabel}'" if dlabel else ""
                st.success(f"Added receptor{display} at ({dx:.2f}, {dy:.2f})")
                st.rerun()

    with tab_import:
        st.subheader("Import Receptors from CSV")
        st.info("Upload a CSV with columns: **x**, **y** (and optionally z_elev, z_hill, label). "
                "Column names are case-insensitive.")
        uploaded = st.file_uploader("Upload CSV", type=["csv"], key="receptor_csv")
        if uploaded:
            df = pd.read_csv(uploaded)
            # Normalize column names to lowercase
            df.columns = [c.strip().lower() for c in df.columns]
            st.dataframe(df.head(10))

            # Validate required columns
            if "x" not in df.columns or "y" not in df.columns:
                st.error(
                    f"CSV must have 'x' and 'y' columns. "
                    f"Found: {', '.join(df.columns)}"
                )
            elif st.button("Import Receptors"):
                count = 0
                for _, row in df.iterrows():
                    z = float(row.get("z_elev", 0.0))
                    zh = float(row.get("z_hill", 0.0))
                    lbl = str(row.get("label", "")) if "label" in df.columns else ""
                    receptors.add_discrete_receptor(
                        DiscreteReceptor(
                            float(row["x"]), float(row["y"]),
                            z_elev=z, z_hill=zh, label=lbl,
                        )
                    )
                    count += 1
                st.success(f"Imported {count} discrete receptors")
                st.rerun()

    with tab_aermap:
        st.subheader("Import Elevations from AERMAP Output")
        if not HAS_TERRAIN:
            st.warning("Terrain module not available. Install with: pip install pyaermod[terrain]")
        else:
            st.info(
                "Upload AERMAP receptor and/or source output files. "
                "Elevations will be matched to existing discrete receptors by (x, y) "
                "coordinate (0.5 m tolerance)."
            )

            # --- Receptor elevations ---
            rec_file = st.file_uploader(
                "AERMAP Receptor Output File",
                type=["out", "txt", "dat"],
                key="aermap_rec_upload",
            )
            if rec_file:
                with tempfile.NamedTemporaryFile(
                    suffix=".out", delete=False, mode="w",
                ) as f:
                    f.write(rec_file.getvalue().decode("utf-8"))
                    temp_path = f.name
                try:
                    rec_df = AERMAPOutputParser.parse_receptor_output(temp_path)
                    st.success(f"Parsed {len(rec_df)} receptor elevations.")
                    st.dataframe(rec_df.head(20), use_container_width=True)

                    has_discrete = bool(receptors.discrete_receptors)
                    has_grids = bool(receptors.cartesian_grids)
                    if not has_discrete and not has_grids:
                        st.warning("No receptors defined to update.")
                    elif st.button("Apply Receptor Elevations"):
                        msgs = []
                        # Apply to discrete receptors
                        if has_discrete:
                            updated = _apply_aermap_receptor_elevations(
                                receptors.discrete_receptors, rec_df,
                            )
                            msgs.append(
                                f"Discrete: updated {updated} of "
                                f"{len(receptors.discrete_receptors)}"
                            )
                        # Apply to Cartesian grids
                        if has_grids:
                            import numpy as np
                            for grid in receptors.cartesian_grids:
                                elevs = np.zeros((grid.y_num, grid.x_num))
                                hills = np.zeros((grid.y_num, grid.x_num))
                                matched = 0
                                for row_i in range(grid.y_num):
                                    y = grid.y_init + row_i * grid.y_delta
                                    for col_i in range(grid.x_num):
                                        x = grid.x_init + col_i * grid.x_delta
                                        dists = (rec_df["x"] - x)**2 + (rec_df["y"] - y)**2
                                        nearest = dists.idxmin()
                                        if dists[nearest] < 1.0:  # 1m tolerance
                                            elevs[row_i, col_i] = rec_df.loc[nearest, "zelev"]
                                            hills[row_i, col_i] = rec_df.loc[nearest, "zhill"]
                                            matched += 1
                                grid.grid_elevations = elevs.tolist()
                                grid.grid_hills = hills.tolist()
                                msgs.append(
                                    f"Grid '{grid.grid_name}': {matched} of "
                                    f"{grid.x_num * grid.y_num} receptors matched"
                                )
                        st.success("Elevations applied. " + "; ".join(msgs))
                        st.rerun()
                except Exception as e:
                    st.error(f"Error parsing AERMAP receptor output: {e}")
                finally:
                    os.unlink(temp_path)

            # --- Source elevations ---
            st.markdown("---")
            src_file = st.file_uploader(
                "AERMAP Source Output File (optional)",
                type=["out", "txt", "dat"],
                key="aermap_src_upload",
            )
            if src_file:
                with tempfile.NamedTemporaryFile(
                    suffix=".out", delete=False, mode="w",
                ) as f:
                    f.write(src_file.getvalue().decode("utf-8"))
                    temp_path = f.name
                try:
                    src_df = AERMAPOutputParser.parse_source_output(temp_path)
                    st.success(f"Parsed {len(src_df)} source elevations.")
                    st.dataframe(src_df, use_container_width=True)

                    sources = st.session_state["project_sources"].sources
                    if not sources:
                        st.warning("No sources defined to update.")
                    elif st.button("Apply Source Elevations"):
                        updated = _apply_aermap_source_elevations(sources, src_df)
                        st.success(f"Updated {updated} of {len(sources)} source elevations.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error parsing AERMAP source output: {e}")
                finally:
                    os.unlink(temp_path)

    # Show discrete receptor table with labels
    if receptors.discrete_receptors:
        st.subheader("Discrete Receptors")
        disc_rows = []
        for i, r in enumerate(receptors.discrete_receptors):
            disc_rows.append({
                "#": i + 1,
                "Label": getattr(r, "label", "") or "",
                "X": r.x_coord,
                "Y": r.y_coord,
                "Z Elev": r.z_elev,
            })
        st.dataframe(pd.DataFrame(disc_rows), use_container_width=True, hide_index=True)

    # Summary
    st.subheader("Receptor Summary")
    n_cart = sum(g.x_num * g.y_num for g in receptors.cartesian_grids)
    n_polar = sum(g.dist_num * g.dir_num for g in receptors.polar_grids)
    n_disc = len(receptors.discrete_receptors)
    st.metric("Total Receptors", n_cart + n_polar + n_disc)
    col1, col2, col3 = st.columns(3)
    col1.metric("Cartesian", n_cart)
    col2.metric("Polar", n_polar)
    col3.metric("Discrete", n_disc)

    if receptors.cartesian_grids or receptors.polar_grids or receptors.discrete_receptors:  # noqa: SIM102
        if st.button("Clear All Receptors", type="secondary"):
            st.session_state["project_receptors"] = ReceptorPathway()
            st.rerun()


def page_meteorology():
    """Meteorology configuration page with dual mode: files or AERMET config."""
    st.header("Meteorology")

    mode_options = ["Use existing .sfc/.pfl files", "Configure AERMET"]
    current_mode = st.session_state.get("aermet_mode", "files")
    mode_idx = 0 if current_mode == "files" else 1
    mode = st.radio("Meteorology Mode", mode_options, index=mode_idx, horizontal=True)
    st.session_state["aermet_mode"] = "files" if mode == mode_options[0] else "configure"

    if st.session_state["aermet_mode"] == "files":
        _render_met_files_mode()
    else:
        _render_aermet_config_mode()


def _render_met_files_mode():
    """Existing .sfc/.pfl file mode for users who ran AERMET externally."""
    met = st.session_state["project_meteorology"]

    st.subheader("Meteorology Files")
    sfc_file = st.text_input("Surface File (.sfc)", value=met.surface_file or "")
    pfl_file = st.text_input("Profile File (.pfl)", value=met.profile_file or "")

    st.subheader("File Upload (optional)")
    st.info("Upload met files to a working directory for the AERMOD run.")
    sfc_upload = st.file_uploader("Upload Surface File", type=["sfc"], key="sfc_upload")
    pfl_upload = st.file_uploader("Upload Profile File", type=["pfl"], key="pfl_upload")

    work_dir = st.text_input("Working Directory", value=str(Path.cwd()))

    if sfc_upload:
        sfc_path = Path(work_dir) / sfc_upload.name
        sfc_path.write_bytes(sfc_upload.getvalue())
        sfc_file = str(sfc_path)
        st.success(f"Saved: {sfc_path}")

    if pfl_upload:
        pfl_path = Path(work_dir) / pfl_upload.name
        pfl_path.write_bytes(pfl_upload.getvalue())
        pfl_file = str(pfl_path)
        st.success(f"Saved: {pfl_path}")

    # Auto-detect station IDs from .sfc header if available
    auto_sf_id = met.surface_station_id
    auto_ua_id = met.upper_air_station_id
    auto_year = met.data_start_year
    auto_base_elev = met.profile_base_elevation
    sfc_path_obj = Path(sfc_file) if sfc_file else None
    if sfc_path_obj and sfc_path_obj.exists():
        try:
            header = sfc_path_obj.read_text(encoding="utf-8", errors="replace").split("\n")[0]
            import re as _re
            ua_match = _re.search(r"UA_ID:\s*(\d+)", header)
            sf_match = _re.search(r"SF_ID:\s*(\w+)", header)
            if ua_match:
                auto_ua_id = int(ua_match.group(1))
            if sf_match:
                # SF_ID may be alphanumeric like KHOU; try numeric parse
                try:
                    auto_sf_id = int(sf_match.group(1))
                except ValueError:
                    auto_sf_id = met.surface_station_id
            # Parse start year from second line (first data record)
            lines_all = sfc_path_obj.read_text(encoding="utf-8", errors="replace").split("\n")
            if len(lines_all) > 1:
                fields = lines_all[1].split()
                if fields:
                    yr = int(fields[0])
                    auto_year = yr if yr > 99 else yr + 2000
        except Exception:
            pass

    st.subheader("Station & Profile Information")
    if sfc_path_obj and not sfc_path_obj.exists() and auto_sf_id == 0:
        st.info(
            "The .sfc file was not found, so station IDs could not be auto-detected. "
            "If you are only previewing the input file (not running AERMOD), you can "
            "leave these at 0. When you provide real .sfc/.pfl files, the IDs will be "
            "detected automatically from the file header."
        )
    else:
        st.caption("AERMOD requires station IDs, data start year, and profile base elevation. "
                   "These are auto-detected from the .sfc file header when available.")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        sf_id = st.number_input("Surface Station ID", value=auto_sf_id, step=1,
                                help="Numeric station ID from SURFDATA keyword")
        ua_id = st.number_input("Upper Air Station ID", value=auto_ua_id, step=1,
                                help="Numeric station ID from UAIRDATA keyword")
    with col_s2:
        data_year = st.number_input("Data Start Year", value=auto_year, min_value=1900, max_value=2100, step=1)
        prof_base = st.number_input("Profile Base Elevation (m MSL)", value=auto_base_elev,
                                    format="%.1f",
                                    help="Base elevation of the met profile data (meters above sea level)")

    # Update existing MeteorologyPathway in-place to preserve optional fields
    # (start_year, start_month, etc.) that may have been set by project load
    met_obj = st.session_state["project_meteorology"]
    met_obj.surface_file = sfc_file
    met_obj.profile_file = pfl_file
    met_obj.surface_station_id = int(sf_id)
    met_obj.upper_air_station_id = int(ua_id)
    met_obj.data_start_year = int(data_year)
    met_obj.profile_base_elevation = float(prof_base)
    st.success("Meteorology settings saved.")


def _render_aermet_config_mode():
    """Full AERMET configuration mode with 3 stages."""
    if not HAS_AERMET:
        st.warning("AERMET module not available.")
        return

    tab1, tab2, tab3 = st.tabs([
        "Stage 1: Data Extract", "Stage 2: Merge", "Stage 3: Boundary Layer",
    ])

    with tab1:
        _render_aermet_stage1()

    with tab2:
        _render_aermet_stage2()

    with tab3:
        _render_aermet_stage3()


def _render_aermet_stage1():
    """AERMET Stage 1: surface/upper-air station config, data files, date range."""
    st.subheader("Stage 1: Extract and QA/QC")

    st.markdown("**Surface Station**")
    col1, col2 = st.columns(2)
    with col1:
        sfc_id = st.text_input("Station ID", value="KATL", key="sfc_station_id")
        sfc_name = st.text_input("Station Name", value="Atlanta Hartsfield", key="sfc_station_name")
        sfc_lat = st.number_input(
            "Latitude", value=33.63, min_value=-90.0, max_value=90.0,
            format="%.4f", key="sfc_lat",
        )
        sfc_lon = st.number_input(
            "Longitude", value=-84.44, min_value=-180.0, max_value=180.0,
            format="%.4f", key="sfc_lon",
        )
    with col2:
        sfc_tz = st.number_input(
            "Time Zone (UTC offset)", value=-5, min_value=-12, max_value=12,
            step=1, key="sfc_tz",
        )
        sfc_elev = st.number_input("Elevation (m)", value=315.0, format="%.1f", key="sfc_elev")
        sfc_anem = st.number_input(
            "Anemometer Height (m)", value=10.0, min_value=0.1, key="sfc_anem",
        )
        sfc_format = st.selectbox(
            "Data Format", ["ISHD", "HUSWO", "SCRAM", "SAMSON"], key="sfc_format",
        )

    st.markdown("**Upper Air Station**")
    col3, col4 = st.columns(2)
    with col3:
        ua_id = st.text_input("Station ID", value="72215", key="ua_station_id")
        ua_name = st.text_input("Station Name", value="Peachtree City", key="ua_station_name")
    with col4:
        ua_lat = st.number_input("Latitude", value=33.36, format="%.4f", key="ua_lat")
        ua_lon = st.number_input("Longitude", value=-84.57, format="%.4f", key="ua_lon")

    st.markdown("**Data Files and Date Range**")
    col5, col6 = st.columns(2)
    with col5:
        sfc_data = st.text_input("Surface Data File", value="", key="sfc_data_file")
        ua_data = st.text_input("Upper Air Data File", value="", key="ua_data_file")
    with col6:
        start_date = st.text_input("Start Date (YYYY/MM/DD)", value="2020/01/01", key="aermet_s1_start")
        end_date = st.text_input("End Date (YYYY/MM/DD)", value="2020/12/31", key="aermet_s1_end")

    if st.button("Save Stage 1 Configuration", key="save_stage1"):
        try:
            sfc_station = AERMETStation(
                station_id=sfc_id, station_name=sfc_name,
                latitude=sfc_lat, longitude=sfc_lon,
                time_zone=int(sfc_tz), elevation=sfc_elev,
                anemometer_height=sfc_anem,
            )
            ua_station = UpperAirStation(
                station_id=ua_id, station_name=ua_name,
                latitude=ua_lat, longitude=ua_lon,
            )
            stage1 = AERMETStage1(
                surface_station=sfc_station, surface_data_file=sfc_data,
                surface_format=sfc_format,
                upper_air_station=ua_station, upper_air_data_file=ua_data,
                start_date=start_date, end_date=end_date,
            )
            st.session_state["aermet_stage1"] = stage1
            st.success("Stage 1 configuration saved.")
        except ValueError as e:
            st.error(str(e))

    # Preview
    stage1 = st.session_state.get("aermet_stage1")
    if stage1 is not None:
        with st.expander("Preview Stage 1 Input"):
            st.code(stage1.to_aermet_input(), language="text")
        st.download_button(
            "Download Stage 1 Input File",
            stage1.to_aermet_input().encode("utf-8"),
            file_name="aermet_stage1.inp",
            mime="text/plain",
            key="dl_stage1",
        )


def _render_aermet_stage2():
    """AERMET Stage 2: merge configuration."""
    st.subheader("Stage 2: Merge Data")

    col1, col2 = st.columns(2)
    with col1:
        sfc_ext = st.text_input("Surface Extract File", value="stage1.ext", key="s2_sfc_ext")
        ua_ext = st.text_input("Upper Air Extract File", value="stage1_ua.ext", key="s2_ua_ext")
    with col2:
        start_date = st.text_input("Start Date", value="2020/01/01", key="aermet_s2_start")
        end_date = st.text_input("End Date", value="2020/12/31", key="aermet_s2_end")
        merge_file = st.text_input("Merge Output File", value="stage2.mrg", key="s2_merge")

    if st.button("Save Stage 2 Configuration", key="save_stage2"):
        stage2 = AERMETStage2(
            surface_extract=sfc_ext,
            upper_air_extract=ua_ext if ua_ext else None,
            start_date=start_date, end_date=end_date,
            merge_file=merge_file,
        )
        st.session_state["aermet_stage2"] = stage2
        st.success("Stage 2 configuration saved.")

    stage2 = st.session_state.get("aermet_stage2")
    if stage2 is not None:
        with st.expander("Preview Stage 2 Input"):
            st.code(stage2.to_aermet_input(), language="text")
        st.download_button(
            "Download Stage 2 Input File",
            stage2.to_aermet_input().encode("utf-8"),
            file_name="aermet_stage2.inp",
            mime="text/plain",
            key="dl_stage2",
        )


def _render_aermet_stage3():
    """AERMET Stage 3: boundary layer parameters with monthly arrays."""
    st.subheader("Stage 3: Boundary Layer Parameters")

    col1, col2 = st.columns(2)
    with col1:
        merge_file = st.text_input("Merge File", value="stage2.mrg", key="s3_merge")
        start_date = st.text_input("Start Date", value="2020/01/01", key="aermet_s3_start")
        end_date = st.text_input("End Date", value="2020/12/31", key="aermet_s3_end")
    with col2:
        sfc_out = st.text_input("Surface Output (.sfc)", value="aermod.sfc", key="s3_sfc_out")
        pfl_out = st.text_input("Profile Output (.pfl)", value="aermod.pfl", key="s3_pfl_out")

    st.markdown("**Monthly Surface Parameters** (12 months: Jan-Dec)")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    # Defaults for suburban area
    default_albedo = [0.35, 0.35, 0.25, 0.18, 0.15, 0.15, 0.15, 0.15, 0.18, 0.25, 0.35, 0.35]
    default_bowen = [1.5, 1.5, 1.0, 0.8, 0.6, 0.5, 0.5, 0.5, 0.6, 0.8, 1.0, 1.5]
    default_roughness = [0.30, 0.30, 0.30, 0.30, 0.50, 0.50, 0.50, 0.50, 0.50, 0.30, 0.30, 0.30]

    monthly_df = pd.DataFrame({
        "Month": months,
        "Albedo": default_albedo,
        "Bowen Ratio": default_bowen,
        "Roughness (m)": default_roughness,
    })

    edited_df = st.data_editor(
        monthly_df, num_rows="fixed", use_container_width=True,
        disabled=["Month"], key="s3_monthly_editor",
    )

    st.markdown("**Site Location** (uses Stage 1 station if configured)")
    use_stage1 = st.checkbox("Use Stage 1 surface station", value=True, key="s3_use_stage1")

    if st.button("Save Stage 3 Configuration", key="save_stage3"):
        try:
            albedo = edited_df["Albedo"].tolist()
            bowen = edited_df["Bowen Ratio"].tolist()
            roughness = edited_df["Roughness (m)"].tolist()

            station = None
            lat = lon = tz = None
            if use_stage1:
                s1 = st.session_state.get("aermet_stage1")
                if s1 and s1.surface_station:
                    station = s1.surface_station
            if station is None:
                st.warning("No Stage 1 station configured. Using project center coordinates.")
                lat = st.session_state.get("center_lat", 33.75)
                lon = st.session_state.get("center_lon", -84.39)
                tz = -5

            stage3 = AERMETStage3(
                merge_file=merge_file,
                station=station,
                latitude=lat, longitude=lon, time_zone=tz,
                albedo=albedo, bowen=bowen, roughness=roughness,
                start_date=start_date, end_date=end_date,
                surface_file=sfc_out, profile_file=pfl_out,
            )
            st.session_state["aermet_stage3"] = stage3

            # Also update the meteorology pathway so AERMOD can find the files
            # Try to extract numeric station IDs and elevation from AERMET config
            _sf_id = 0
            _ua_id = 0
            _base_elev = 0.0
            # start_date is a string like "2020/01/01" from st.text_input
            try:
                _data_yr = int(start_date.split("/")[0]) if start_date else 2020
            except (ValueError, IndexError):
                _data_yr = 2020
            s1 = st.session_state.get("aermet_stage1")
            if s1:
                if s1.surface_station:
                    with contextlib.suppress(ValueError):
                        _sf_id = int(s1.surface_station.station_id)
                    if s1.surface_station.elevation is not None:
                        _base_elev = s1.surface_station.elevation
                if s1.upper_air_station:
                    with contextlib.suppress(ValueError):
                        _ua_id = int(s1.upper_air_station.station_id)
            st.session_state["project_meteorology"] = MeteorologyPathway(
                surface_file=sfc_out,
                profile_file=pfl_out,
                surface_station_id=_sf_id,
                upper_air_station_id=_ua_id,
                data_start_year=_data_yr,
                profile_base_elevation=_base_elev,
            )
            st.success("Stage 3 configuration saved. Meteorology pathway updated.")
        except ValueError as e:
            st.error(str(e))

    stage3 = st.session_state.get("aermet_stage3")
    if stage3 is not None:
        with st.expander("Preview Stage 3 Input"):
            st.code(stage3.to_aermet_input(), language="text")
        st.download_button(
            "Download Stage 3 Input File",
            stage3.to_aermet_input().encode("utf-8"),
            file_name="aermet_stage3.inp",
            mime="text/plain",
            key="dl_stage3",
        )


def page_run_aermod():
    """Run AERMOD page with validation, preview, and execution."""
    st.header("Run AERMOD")

    project = SessionStateManager.get_project()

    # Validation
    st.subheader("Validation")
    has_validation_errors = False
    if HAS_VALIDATOR:
        try:
            validator = Validator()
            result = validator.validate(project)
            if result.errors:
                has_validation_errors = True
                for err in result.errors:
                    st.error(f"{err.field}: {err.message}")
            if result.warnings:
                for warn in result.warnings:
                    st.warning(f"{warn.field}: {warn.message}")
            if not result.errors and not result.warnings:
                st.success("All validation checks passed.")
        except Exception as e:
            st.warning(f"Validation error: {e}")
    else:
        st.info("Validator module not available.")

    # Input preview
    st.subheader("Generated Input File")
    try:
        inp_text = project.to_aermod_input(validate=False)
        with st.expander("View AERMOD Input File", expanded=False):
            st.code(inp_text, language="text")
        st.download_button(
            label="Download Input File",
            data=inp_text,
            file_name="aermod.inp",
            mime="text/plain",
        )
    except Exception as e:
        st.error(f"Error generating input: {e}")
        inp_text = None

    # Output configuration
    st.subheader("Output Configuration")
    col1, col2 = st.columns(2)
    with col1:
        receptor_table = st.checkbox("Receptor Table", value=True)
        max_table = st.checkbox("Max Value Table", value=True)
    with col2:
        postfile_enabled = st.checkbox("Generate POSTFILE", value=False)
        if postfile_enabled:
            postfile_format = st.selectbox(
                "POSTFILE Format", ["PLOT", "UNFORM"],
                help="PLOT = formatted text, UNFORM = binary",
            )
            postfile_avg = st.selectbox(
                "POSTFILE Averaging Period",
                ["1", "3", "8", "24", "ANNUAL", "PERIOD"],
                help="Averaging period to output in POSTFILE",
            )

    # Output type (shown when deposition is enabled)
    dep_enabled = (
        st.session_state["project_control"].calculate_deposition
        or st.session_state["project_control"].calculate_dry_deposition
        or st.session_state["project_control"].calculate_wet_deposition
    )
    output_type = "CONC"
    if dep_enabled:
        output_type = st.selectbox(
            "Output Type",
            ["CONC", "DEPOS", "DDEP", "WDEP", "DETH"],
            help="Type of output: concentration (CONC) or deposition flux",
        )

    # Update existing OutputPathway in-place to preserve fields set elsewhere
    out = st.session_state["project_output"]
    out.receptor_table = receptor_table
    out.max_table = max_table
    out.output_type = output_type
    if postfile_enabled:
        out.postfile = "postfile.pst"
        out.postfile_averaging = postfile_avg
        out.postfile_source_group = "ALL"
        out.postfile_format = postfile_format
    else:
        out.postfile = None

    # Per-group PLOTFILE options
    groups = st.session_state["project_sources"].group_definitions
    if groups:
        with st.expander("Per-Group Plot Files"):
            st.markdown("Configure separate PLOTFILE outputs for each source group.")
            plot_file_groups = []
            avg_periods = st.session_state["project_control"].averaging_periods
            for grp in groups:
                grp_col1, grp_col2 = st.columns(2)
                with grp_col1:
                    enable_grp = st.checkbox(
                        f"Enable PLOTFILE for {grp.group_name}",
                        key=f"plotfile_grp_{grp.group_name}",
                    )
                if enable_grp:
                    with grp_col2:
                        grp_avg = st.selectbox(
                            f"Averaging for {grp.group_name}",
                            avg_periods if avg_periods else ["ANNUAL"],
                            key=f"plotfile_avg_{grp.group_name}",
                        )
                    plot_file_groups.append(
                        (grp_avg, grp.group_name, f"plotfile_{grp.group_name}.plt")
                    )
            st.session_state["project_output"].plot_file_groups = plot_file_groups

    # Event processing
    with st.expander("Event Processing"):
        event_enabled = st.checkbox("Enable Event Processing", value=False, key="event_enabled")
        if event_enabled:
            n_events = st.number_input(
                "Number of Events", min_value=1, max_value=50, value=1,
                key="n_events",
            )
            events = []
            for i in range(n_events):
                ev_col1, ev_col2, ev_col3 = st.columns(3)
                with ev_col1:
                    ev_name = st.text_input(
                        f"Event {i+1} Name", value=f"EVT{i+1:02d}",
                        max_chars=8, key=f"ev_name_{i}",
                    )
                with ev_col2:
                    ev_start = st.text_input(
                        "Start (YYMMDDHH)", value="24010101",
                        max_chars=8, key=f"ev_start_{i}",
                    )
                with ev_col3:
                    ev_end = st.text_input(
                        "End (YYMMDDHH)", value="24010124",
                        max_chars=8, key=f"ev_end_{i}",
                    )
                events.append(EventPeriod(
                    event_name=ev_name,
                    start_date=ev_start,
                    end_date=ev_end,
                ))
            st.session_state["project_events"] = EventPathway(events=events)
            st.session_state["project_control"] = ControlPathway(
                **{
                    **{
                        f.name: getattr(st.session_state["project_control"], f.name)
                        for f in st.session_state["project_control"].__dataclass_fields__.values()
                    },
                    "eventfil": "events.inp",
                }
            )
        else:
            st.session_state["project_events"] = None
            # Clear stale eventfil reference when events are disabled
            ctrl = st.session_state["project_control"]
            if getattr(ctrl, "eventfil", None):
                ctrl.eventfil = None

    # Run
    st.subheader("Execute AERMOD")

    # Estimated model complexity
    n_sources = len(st.session_state.get("project_sources", SourcePathway()).sources)
    recs = st.session_state.get("project_receptors", ReceptorPathway())
    n_receptors = _count_receptors(recs)
    with st.expander("Model Complexity", expanded=False):
        c1, c2 = st.columns(2)
        c1.metric("Sources", n_sources)
        c2.metric("Receptors", n_receptors)
        if n_sources > 0 and n_receptors > 0:
            complexity = n_sources * n_receptors
            if complexity < 1000:
                st.info("Small model — expected runtime: seconds")
            elif complexity < 50000:
                st.info("Medium model — expected runtime: minutes")
            else:
                st.warning("Large model — expected runtime: tens of minutes or more")

    work_dir = st.text_input("Working Directory", value=str(Path.cwd()), key="run_workdir")
    aermod_exe = st.text_input("AERMOD Executable Path", value="aermod")

    if st.button("Run AERMOD", type="primary"):
        if not inp_text:
            st.error("Cannot run: input file generation failed.")
            return
        if has_validation_errors:
            st.error("Cannot run: fix validation errors above before running AERMOD.")
            return

        with st.spinner("Running AERMOD..."):
            try:
                inp_path = Path(work_dir) / "aermod.inp"
                inp_path.write_text(inp_text)

                # Write event file if event processing is enabled
                ev_pathway = st.session_state.get("project_events")
                if ev_pathway is not None:
                    ev_path = Path(work_dir) / "events.inp"
                    ev_path.write_text(ev_pathway.to_aermod_input())

                if HAS_RUNNER:
                    result = run_aermod(str(inp_path), executable_path=aermod_exe)
                    st.session_state["run_result"] = result

                    if result.success:
                        st.success(f"AERMOD completed successfully. Output: {result.output_file}")

                        # Auto-parse results
                        if HAS_PARSER and result.output_file:
                            parsed = parse_aermod_output(result.output_file)
                            st.session_state["parsed_results"] = parsed
                            st.info("Results parsed automatically. Go to Results Viewer.")
                    else:
                        st.error(f"AERMOD failed. Return code: {result.return_code}")
                        if result.error_message:
                            st.error(result.error_message)
                        if result.stderr:
                            st.code(result.stderr)
                else:
                    st.error("Runner module not available.")
            except Exception as e:
                st.error(f"Execution error: {e}")


def _count_receptors(receptor_pathway):
    """Estimate total receptor count from a ReceptorPathway."""
    count = 0
    for g in getattr(receptor_pathway, "cartesian_grids", []):
        count += getattr(g, "x_num", 0) * getattr(g, "y_num", 0)
    for g in getattr(receptor_pathway, "polar_grids", []):
        count += getattr(g, "dist_num", 0) * getattr(g, "dir_num", 0)
    count += len(getattr(receptor_pathway, "discrete_receptors", []))
    return count


def _compute_statistics_by_period(results, avail_periods):
    """Compute summary statistics for each averaging period.

    Returns a list of dicts suitable for ``pd.DataFrame(rows)``.
    """
    rows = []
    for period in avail_periods:
        conc = results.get_concentrations(period)
        if conc is None or conc.empty:
            continue
        s = conc["concentration"]
        rows.append({
            "Period": period,
            "Mean": round(s.mean(), 4),
            "Max": round(s.max(), 4),
            "P50": round(s.quantile(0.50), 4),
            "P90": round(s.quantile(0.90), 4),
            "P95": round(s.quantile(0.95), 4),
            "P99": round(s.quantile(0.99), 4),
            "Receptors": len(s),
        })
    return rows


def _build_receptor_ranking(conc_df, n=10):
    """Return a ranked DataFrame of the top *n* receptor concentrations."""
    top = conc_df.nlargest(n, "concentration").copy()
    top.insert(0, "Rank", range(1, len(top) + 1))
    # Add percentile column if enough data
    if len(conc_df) > 1:
        max_val = conc_df["concentration"].max()
        if max_val > 0:
            top["Pct of Max"] = (
                top["concentration"] / max_val * 100
            ).round(1).astype(str) + "%"
    return top.reset_index(drop=True)


def _get_available_export_formats():
    """Return a list of export formats based on installed optional dependencies."""
    formats = []
    if HAS_GEO:
        formats.append("GeoTIFF (.tif)")
        formats.append("GeoPackage (.gpkg)")
        formats.append("Shapefile (.shp)")
        formats.append("GeoJSON (.geojson)")
    formats.append("CSV with Lat/Lon")
    return formats


def page_results_viewer():
    """Results Viewer page."""
    st.header("Results Viewer")

    results = st.session_state.get("parsed_results")

    # Allow loading from file
    st.subheader("Load Results")
    uploaded_out = st.file_uploader("Upload AERMOD .out file", type=["out"], key="out_upload")
    if uploaded_out:
        # Guard against re-parsing on every rerun
        out_file_id = f"{uploaded_out.name}_{uploaded_out.size}"
        if st.session_state.get("_last_loaded_out") != out_file_id:
            with tempfile.NamedTemporaryFile(suffix=".out", delete=False, mode="w") as f:
                f.write(uploaded_out.getvalue().decode("utf-8"))
                f.flush()
                temp_out_path = f.name
            try:
                if HAS_PARSER:
                    results = parse_aermod_output(temp_out_path)
                    st.session_state["parsed_results"] = results
                    st.session_state["_last_loaded_out"] = out_file_id
                    st.success("Results loaded and parsed.")
            finally:
                os.unlink(temp_out_path)
        else:
            st.info("Results already loaded.")

    if results is None:
        st.info("No results available. Run AERMOD or upload an .out file.")
        return

    # Summary
    st.subheader("Run Summary")
    if hasattr(results, "run_info") and results.run_info:
        info = results.run_info
        col1, col2, col3 = st.columns(3)
        col1.metric("Sources", getattr(info, "num_sources", "N/A"))
        col2.metric("Receptors", getattr(info, "num_receptors", "N/A"))
        col3.metric("Pollutant", getattr(info, "pollutant_id", "N/A"))

    # Tabs for different views
    tab_map, tab_static, tab_stats, tab_postfile = st.tabs([
        "Interactive Map", "Static Plots", "Statistics", "POSTFILE Viewer",
    ])

    # Get available averaging periods
    avail_periods = list(getattr(results, "concentrations", {}).keys())
    if not avail_periods:
        st.warning(
            "No concentration results were parsed from the AERMOD output. "
            "This may indicate AERMOD reported errors during the run. "
            "Check the output (.out) file for details."
        )
        return

    with tab_map:
        st.subheader("Concentration Map")
        period = st.selectbox("Averaging Period", avail_periods, key="map_period")

        conc_df = results.get_concentrations(period)
        if conc_df is not None and not conc_df.empty:
            transformer = SessionStateManager.get_transformer()
            if transformer and HAS_FOLIUM:
                editor = MapEditor(
                    transformer=transformer,
                    center=(st.session_state["center_lat"], st.session_state["center_lon"]),
                )
                editor.render_concentration_map(
                    conc_df, st.session_state["project_sources"].sources,
                )
            else:
                st.warning("Install pyproj and streamlit-folium for interactive maps.")
        else:
            st.info(f"No concentration data for {period}.")

    with tab_static:
        st.subheader("Static Plots")
        period2 = st.selectbox("Averaging Period", avail_periods, key="static_period")

        if HAS_VIZ:
            viz = AERMODVisualizer(results)

            # Contour plot
            try:
                fig = viz.plot_contours(averaging_period=period2)
                if fig:
                    st.pyplot(fig)
                    plt.close(fig)
            except Exception as e:
                st.warning(f"Could not generate contour plot: {e}")
        else:
            st.info("Install matplotlib for static plots.")

    with tab_stats:
        st.subheader("Concentration Statistics")

        # Cross-period summary table
        summary_rows = _compute_statistics_by_period(results, avail_periods)
        if summary_rows:
            st.subheader("Summary Across All Averaging Periods")
            st.dataframe(
                pd.DataFrame(summary_rows).set_index("Period"),
                use_container_width=True,
            )

        period3 = st.selectbox("Averaging Period", avail_periods, key="stats_period")

        conc_df3 = results.get_concentrations(period3)
        if conc_df3 is not None and not conc_df3.empty:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Maximum", f"{conc_df3['concentration'].max():.4g}")
            col2.metric("Mean", f"{conc_df3['concentration'].mean():.4g}")
            col3.metric("Median", f"{conc_df3['concentration'].median():.4g}")
            col4.metric("Std Dev", f"{conc_df3['concentration'].std():.4g}")

            # Percentile table
            st.subheader("Percentile Distribution")
            percentiles = [50, 75, 90, 95, 98, 99, 99.5, 100]
            pct_data = {
                f"{p}th": conc_df3["concentration"].quantile(p / 100)
                for p in percentiles
            }
            st.dataframe(pd.DataFrame([pct_data]), use_container_width=True)

            # Top receptors with rank
            st.subheader("Top 10 Receptor Concentrations")
            top10 = _build_receptor_ranking(conc_df3, n=10)
            st.dataframe(top10, use_container_width=True)

            # Threshold exceedance
            st.subheader("Exceedance Analysis")
            threshold = st.number_input("Threshold Value", value=0.0, format="%.4g")
            if threshold > 0:
                exceed = conc_df3[conc_df3["concentration"] > threshold]
                st.metric(
                    "Receptors Exceeding Threshold",
                    f"{len(exceed)} / {len(conc_df3)} ({100 * len(exceed) / len(conc_df3):.1f}%)",
                )

    with tab_postfile:
        _render_postfile_viewer()


# ---------------------------------------------------------------------------
# POSTFILE Viewer helpers
# ---------------------------------------------------------------------------

def _postfile_frames_for_animation(postfile_result):
    """
    Extract per-timestep DataFrames with uppercase column names for
    ``AdvancedVisualizer.plot_time_series_animation()``.

    Parameters
    ----------
    postfile_result : PostfileResult
        Parsed POSTFILE data.

    Returns
    -------
    frames : list of pd.DataFrame
        One DataFrame per timestep with columns ``X``, ``Y``, ``CONC``.
    dates : list of str
        Sorted date strings corresponding to each frame.
    """
    dates = sorted(postfile_result.data["date"].unique())
    frames = []
    for date in dates:
        df = postfile_result.get_timestep(date)
        frames.append(df.rename(columns={
            "x": "X", "y": "Y", "concentration": "CONC",
        }))
    return frames, dates


def _render_postfile_viewer():
    """Render the POSTFILE Viewer sub-tab content."""
    st.subheader("POSTFILE Viewer")

    if not HAS_POSTFILE:
        st.warning("POSTFILE parser is not available.")
        return

    # File upload
    uploaded_pst = st.file_uploader(
        "Upload POSTFILE",
        type=["pst", "plt", "out", "dat", "bin"],
        key="postfile_upload",
        help="Upload an AERMOD POSTFILE (text PLOT or binary UNFORM format).",
    )

    if uploaded_pst:
        with tempfile.NamedTemporaryFile(
            suffix=".pst", delete=False,
        ) as tmp:
            tmp.write(uploaded_pst.getvalue())
            tmp.flush()
            temp_pst_path = tmp.name
        try:
            pf_result = read_postfile(temp_pst_path)
            st.session_state["postfile_results"] = pf_result
            st.success(
                f"POSTFILE loaded: {len(pf_result.data)} data rows, "
                f"{pf_result.data['date'].nunique()} timesteps."
            )
        except Exception as e:
            st.error(f"Failed to parse POSTFILE: {e}")
        finally:
            os.unlink(temp_pst_path)

    pf_result = st.session_state.get("postfile_results")
    if pf_result is None or pf_result.data.empty:
        st.info("Upload a POSTFILE to view concentration data over time.")
        return

    # -- Header metadata --
    st.subheader("POSTFILE Metadata")
    hdr = pf_result.header
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Version", hdr.version or "N/A")
    mc2.metric("Pollutant", hdr.pollutant_id or "N/A")
    mc3.metric("Averaging", hdr.averaging_period or "N/A")
    mc4.metric("Source Group", hdr.source_group or "N/A")

    # -- Timestep selector --
    dates = sorted(pf_result.data["date"].unique())
    st.subheader("Timestep Viewer")

    selected_date = st.select_slider(
        "Select Timestep (YYMMDDHH)",
        options=dates,
        value=dates[0],
        key="pf_date_slider",
    )

    ts_df = pf_result.get_timestep(selected_date)
    st.write(f"**{len(ts_df)} receptors** at timestep {selected_date}")

    # Summary metrics for selected timestep
    if not ts_df.empty:
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Max Conc.", f"{ts_df['concentration'].max():.4g}")
        sc2.metric("Mean Conc.", f"{ts_df['concentration'].mean():.4g}")
        sc3.metric("Min Conc.", f"{ts_df['concentration'].min():.4g}")

    # Contour plot for the selected timestep (if matplotlib available)
    if HAS_MATPLOTLIB and not ts_df.empty:
        x_vals = ts_df["x"].values
        y_vals = ts_df["y"].values
        conc_vals = ts_df["concentration"].values

        x_unique = np.unique(x_vals)
        y_unique = np.unique(y_vals)

        # Only produce contour if data forms a grid
        if len(x_unique) > 1 and len(y_unique) > 1 and len(x_unique) * len(y_unique) == len(ts_df):
            try:
                X_grid, Y_grid = np.meshgrid(x_unique, y_unique)
                Z_grid = conc_vals.reshape(len(y_unique), len(x_unique))

                fig, ax = plt.subplots(figsize=(8, 6))
                cf = ax.contourf(X_grid, Y_grid, Z_grid, levels=15, cmap="YlOrRd")
                fig.colorbar(cf, ax=ax, label="Concentration")
                ax.set_xlabel("X (m)")
                ax.set_ylabel("Y (m)")
                ax.set_title(f"Concentration — {selected_date}")
                ax.set_aspect("equal")
                st.pyplot(fig)
                plt.close(fig)
            except Exception as e:
                st.warning(f"Could not render contour plot: {e}")
        else:
            # Non-gridded data — show as scatter plot
            try:
                fig, ax = plt.subplots(figsize=(8, 6))
                sc = ax.scatter(x_vals, y_vals, c=conc_vals, cmap="YlOrRd", s=20)
                fig.colorbar(sc, ax=ax, label="Concentration")
                ax.set_xlabel("X (m)")
                ax.set_ylabel("Y (m)")
                ax.set_title(f"Concentration — {selected_date}")
                ax.set_aspect("equal")
                st.pyplot(fig)
                plt.close(fig)
            except Exception as e:
                st.warning(f"Could not render scatter plot: {e}")

    # -- Data table for selected timestep --
    with st.expander("View Timestep Data Table"):
        st.dataframe(ts_df, use_container_width=True)

    # -- Time-series at a receptor --
    st.subheader("Receptor Time Series")
    receptor_locs = pf_result.data.groupby(["x", "y"]).size().reset_index(name="count")
    receptor_options = [
        f"({row['x']:.1f}, {row['y']:.1f})" for _, row in receptor_locs.iterrows()
    ]
    if receptor_options:
        selected_receptor = st.selectbox(
            "Select Receptor", receptor_options, key="pf_receptor_select"
        )
        # Parse selected coordinates
        parts = selected_receptor.strip("()").split(",")
        rx, ry = float(parts[0].strip()), float(parts[1].strip())
        rec_df = pf_result.get_receptor(rx, ry)

        if not rec_df.empty and HAS_MATPLOTLIB:
            fig_ts, ax_ts = plt.subplots(figsize=(10, 4))
            rec_sorted = rec_df.sort_values("date")
            ax_ts.plot(
                rec_sorted["date"], rec_sorted["concentration"],
                marker="o", markersize=3, linewidth=1,
            )
            ax_ts.set_xlabel("Date (YYMMDDHH)")
            ax_ts.set_ylabel("Concentration")
            ax_ts.set_title(f"Time Series at ({rx:.1f}, {ry:.1f})")
            ax_ts.tick_params(axis="x", rotation=45)
            fig_ts.tight_layout()
            st.pyplot(fig_ts)
            plt.close(fig_ts)

    # -- Animation --
    st.subheader("Animation")
    if not HAS_ADVANCED_VIZ:
        st.info("Advanced visualization module not available for animation.")
    elif len(dates) < 2:
        st.info("Need at least 2 timesteps for animation.")
    else:
        anim_interval = st.slider(
            "Frame interval (ms)", min_value=100, max_value=2000,
            value=500, step=100, key="pf_anim_interval",
        )
        if st.button("Generate Animation GIF", key="pf_gen_anim"):
            frames, frame_dates = _postfile_frames_for_animation(pf_result)

            # Verify frames have gridded data
            df0 = frames[0]
            xu = np.unique(df0["X"].values)
            yu = np.unique(df0["Y"].values)
            if len(xu) < 2 or len(yu) < 2:
                st.warning("Animation requires gridded receptor data with at least 2 unique X and Y values.")
            else:
                with st.spinner("Generating animation..."):
                    gif_fd, gif_path = tempfile.mkstemp(suffix=".gif", prefix="postfile_anim_")
                    os.close(gif_fd)
                    try:
                        AdvancedVisualizer.plot_time_series_animation(
                            dataframes=frames,
                            timestamps=frame_dates,
                            title="POSTFILE Concentration",
                            interval=anim_interval,
                            save_path=gif_path,
                        )
                        plt.close("all")

                        if os.path.exists(gif_path) and os.path.getsize(gif_path) > 0:
                            st.image(gif_path, caption="Concentration Animation")
                            with open(gif_path, "rb") as gf:
                                st.download_button(
                                    "Download GIF",
                                    data=gf.read(),
                                    file_name="postfile_animation.gif",
                                    mime="image/gif",
                                )
                        else:
                            st.warning("Animation file was not generated.")
                    except Exception as e:
                        st.warning(f"Could not generate animation: {e}")
                    finally:
                        if os.path.exists(gif_path):
                            os.unlink(gif_path)


def page_export():
    """Export page for GeoTIFF, Shapefile, and other formats."""
    st.header("Export")

    results = st.session_state.get("parsed_results")
    transformer = SessionStateManager.get_transformer()

    if not HAS_GEO:
        st.error("Geospatial module required. Install with: pip install pyaermod[geo]")
        return

    if not transformer:
        st.warning("Configure UTM zone in Project Setup first.")
        return

    # Show coordinate transformation parameters
    with st.expander("Coordinate Transformation Info", expanded=False):
        utm_zone = st.session_state.get("utm_zone", "N/A")
        hemisphere = st.session_state.get("hemisphere", "N/A")
        st.text(f"UTM Zone: {utm_zone}{hemisphere}")
        st.text("Datum: WGS84")
        st.text(f"Transformer: {type(transformer).__name__}")

    avail_periods = []
    if results:
        avail_periods = list(getattr(results, "concentrations", {}).keys())

    # Export format selection — show formats based on installed dependencies
    available_formats = _get_available_export_formats()
    fmt = st.selectbox("Export Format", available_formats)
    if not HAS_GEO and fmt != "CSV with Lat/Lon":
        st.warning("Install pyaermod[geo] for geospatial exports.")

    if fmt == "GeoTIFF (.tif)":
        st.subheader("GeoTIFF Export")
        if not avail_periods:
            st.info("No concentration results to export. Run AERMOD first.")
            return

        period = st.selectbox("Averaging Period", avail_periods, key="tif_period")
        resolution = st.number_input("Resolution (m)", value=50.0, min_value=1.0)
        method = st.selectbox("Interpolation", ["cubic", "linear", "nearest"])

        if st.button("Generate GeoTIFF"):
            conc_df = results.get_concentrations(period)
            if conc_df is not None and not conc_df.empty:
                with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
                    temp_tif_path = f.name
                try:
                    exporter = RasterExporter(transformer)
                    exporter.export_geotiff(
                        conc_df, temp_tif_path, resolution=resolution, method=method,
                    )
                    with open(temp_tif_path, "rb") as tif:
                        st.download_button(
                            "Download GeoTIFF",
                            tif.read(),
                            file_name=f"concentration_{period}.tif",
                            mime="image/tiff",
                        )
                finally:
                    os.unlink(temp_tif_path)

    elif fmt in ("GeoPackage (.gpkg)", "Shapefile (.shp)", "GeoJSON (.geojson)"):
        driver_map = {
            "GeoPackage (.gpkg)": ("GPKG", ".gpkg"),
            "Shapefile (.shp)": ("ESRI Shapefile", ".shp"),
            "GeoJSON (.geojson)": ("GeoJSON", ".geojson"),
        }
        driver, ext = driver_map[fmt]

        st.subheader(f"{fmt.split('(')[0].strip()} Export")

        export_what = st.multiselect(
            "What to export",
            ["Sources", "Receptors", "Concentrations (points)", "Concentrations (contours)"],
        )

        period = None
        if "Concentrations (points)" in export_what or "Concentrations (contours)" in export_what:
            if avail_periods:
                period = st.selectbox("Averaging Period", avail_periods, key="vec_period")
            else:
                st.warning("No results available.")

        if st.button("Generate Export"):
            factory = GeoDataFrameFactory(transformer)

            with tempfile.TemporaryDirectory() as tmpdir:
                files_to_download = {}

                if "Sources" in export_what:
                    sources = st.session_state["project_sources"].sources
                    if sources:
                        path = Path(tmpdir) / f"sources{ext}"
                        VectorExporter(factory).export_sources(sources, path, driver)
                        files_to_download["sources"] = path

                if "Receptors" in export_what:
                    recs = st.session_state["project_receptors"]
                    path = Path(tmpdir) / f"receptors{ext}"
                    VectorExporter(factory).export_receptors(recs, path, driver)
                    files_to_download["receptors"] = path

                if results and avail_periods and period is not None:
                    conc_df = results.get_concentrations(period)
                    if conc_df is not None and not conc_df.empty:
                        if "Concentrations (points)" in export_what:
                            path = Path(tmpdir) / f"conc_points{ext}"
                            VectorExporter(factory).export_concentrations(
                                conc_df, path, driver, as_contours=False,
                            )
                            files_to_download["conc_points"] = path
                        if "Concentrations (contours)" in export_what:
                            path = Path(tmpdir) / f"conc_contours{ext}"
                            VectorExporter(factory).export_concentrations(
                                conc_df, path, driver, as_contours=True,
                            )
                            files_to_download["conc_contours"] = path

                for name, path in files_to_download.items():
                    if path.exists():
                        with open(path, "rb") as f:
                            st.download_button(
                                f"Download {name}{ext}",
                                f.read(),
                                file_name=f"{name}{ext}",
                                key=f"dl_{name}",
                            )

    elif fmt == "CSV with Lat/Lon":
        st.subheader("CSV Export with Geographic Coordinates")
        if not avail_periods:
            st.info("No concentration results to export.")
            return

        period = st.selectbox("Averaging Period", avail_periods, key="csv_period")
        conc_df = results.get_concentrations(period)
        if conc_df is not None and not conc_df.empty:
            df_geo = transformer.transform_dataframe(conc_df)
            csv = df_geo.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv.encode("utf-8"),
                file_name=f"concentration_{period}_latlon.csv",
                mime="text/csv",
            )
            st.dataframe(df_geo.head(20), use_container_width=True)


# ============================================================================
# MAIN APPLICATION
# ============================================================================


def _app():
    """Streamlit application logic (must be run inside a Streamlit server)."""
    st.set_page_config(
        page_title="PyAERMOD",
        page_icon=":wind_face:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    SessionStateManager.initialize()

    # Sidebar navigation
    st.sidebar.title("PyAERMOD")
    st.sidebar.caption("Atmospheric Dispersion Modeling")

    pages = {
        "Project Setup": page_project_setup,
        "Source Editor": page_source_editor,
        "Receptor Editor": page_receptor_editor,
        "Meteorology": page_meteorology,
        "Run AERMOD": page_run_aermod,
        "Results Viewer": page_results_viewer,
        "Export": page_export,
    }

    # Workflow progress indicator
    st.sidebar.markdown("---")
    st.sidebar.subheader("Workflow Progress")
    has_sources = len(st.session_state["project_sources"].sources) > 0
    has_receptors = (
        len(st.session_state["project_receptors"].cartesian_grids) > 0
        or len(st.session_state["project_receptors"].polar_grids) > 0
        or len(st.session_state["project_receptors"].discrete_receptors) > 0
    )
    has_met = bool(st.session_state["project_meteorology"].surface_file)
    has_results = st.session_state.get("parsed_results") is not None

    has_project = bool(
        st.session_state["project_control"].title_one
        and st.session_state["project_control"].title_one != "New AERMOD Project"
    )
    st.sidebar.checkbox("Project configured", value=has_project, disabled=True)
    st.sidebar.checkbox("Sources defined", value=has_sources, disabled=True)
    st.sidebar.checkbox("Receptors defined", value=has_receptors, disabled=True)
    st.sidebar.checkbox("Meteorology set", value=has_met, disabled=True)
    st.sidebar.checkbox("Results available", value=has_results, disabled=True)

    st.sidebar.markdown("---")
    selection = st.sidebar.radio("Navigation", list(pages.keys()))

    # Render selected page
    pages[selection]()


def main():
    """CLI entry point: launches the Streamlit server to run this GUI."""
    if not HAS_STREAMLIT:
        raise ImportError(
            "Streamlit is required for the GUI. Install with: pip install pyaermod[gui]"
        )
    # Point streamlit at the thin runner script (avoids relative-import errors
    # that occur when streamlit executes gui.py as a standalone script).
    runner_path = str(Path(__file__).with_name("_gui_runner.py"))
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", runner_path, *sys.argv[1:]]))


if __name__ == "__main__":
    _app()
