"""Source and building input forms for the PyAERMOD GUI."""
from ._env import *


class SourceFormFactory:
    """Generates Streamlit form widgets for each AERMOD source type."""

    SOURCE_TYPES = [
        "Point", "Area (Rectangular)", "Area (Circular)",
        "Area (Polygon)", "Volume", "Line", "RLine (Roadway)",
        "RLineExt (Extended Roadway)", "BuoyLine (Buoyant Line)",
        "OpenPit (Open Pit Mine)",
    ]

    @staticmethod
    def render_source_type_selector() -> str:
        return st.selectbox("Source Type", SourceFormFactory.SOURCE_TYPES, key="source_type_selector")

    @staticmethod
    def render_point_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[PointSource]:
        with st.form("point_source_form"):
            st.subheader("Point Source Parameters")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="STACK1", key="pt_sid")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f", key="pt_x")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f", key="pt_y")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f", key="pt_elev")
            with col2:
                height = st.number_input("Stack Height (m)", value=50.0, min_value=0.0, key="pt_height")
                temp = st.number_input("Stack Temperature (K)", value=400.0, min_value=0.0, key="pt_temp")
                vel = st.number_input("Exit Velocity (m/s)", value=15.0, min_value=0.0, key="pt_vel")
                diam = st.number_input("Stack Diameter (m)", value=2.0, min_value=0.0, key="pt_diam")
            erate = st.number_input("Emission Rate (g/s)", value=1.5, min_value=0.0, format="%.6f", key="pt_erate")
            no2_r = st.number_input(
                "NO2/NOx Ratio (optional, 0-1)", value=0.0,
                min_value=0.0, max_value=1.0, step=0.01, format="%.2f",
                help="Per-source NO2/NOx ratio. Leave at 0 to use default.",
                key="pt_no2r",
            )

            if st.form_submit_button("Add Point Source"):
                return PointSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    stack_height=height, stack_temp=temp,
                    exit_velocity=vel, stack_diameter=diam,
                    emission_rate=erate,
                    no2_ratio=no2_r if no2_r > 0 else None,
                )
        return None

    @staticmethod
    def render_area_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[AreaSource]:
        with st.form("area_source_form"):
            st.subheader("Rectangular Area Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="AREA1", key="area_sid")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f", key="area_x")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f", key="area_y")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f", key="area_elev")
            with col2:
                rh = st.number_input("Release Height (m)", value=2.0, min_value=0.0, key="area_rh")
                lat_dim = st.number_input("Half-Width Y (m)", value=25.0, min_value=0.0, key="area_lat_dim")
                vert_dim = st.number_input("Half-Width X (m)", value=50.0, min_value=0.0, key="area_vert_dim")
                angle = st.number_input("Rotation Angle (deg)", value=0.0, key="area_angle")
            erate = st.number_input("Emission Rate (g/s/m2)", value=0.0001, format="%.6f", key="area_erate")

            if st.form_submit_button("Add Area Source"):
                return AreaSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    release_height=rh, initial_lateral_dimension=lat_dim,
                    initial_vertical_dimension=vert_dim, angle=angle,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_area_circ_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[AreaCircSource]:
        with st.form("area_circ_source_form"):
            st.subheader("Circular Area Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="CIRC1")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                rh = st.number_input("Release Height (m)", value=2.0, min_value=0.0)
                radius = st.number_input("Radius (m)", value=100.0, min_value=0.1)
                nverts = st.number_input("Num Vertices", value=20, min_value=3, step=1)
            erate = st.number_input("Emission Rate (g/s/m2)", value=0.0001, format="%.6f")

            if st.form_submit_button("Add Circular Area Source"):
                return AreaCircSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    release_height=rh, radius=radius,
                    num_vertices=int(nverts), emission_rate=erate,
                )
        return None

    @staticmethod
    def render_area_poly_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[AreaPolySource]:
        nv = st.number_input(
            "Number of Vertices", value=4, min_value=3, max_value=20, step=1,
            key="poly_vertex_count",
        )
        with st.form("area_poly_source_form"):
            st.subheader("Polygonal Area Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="POLY1")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                rh = st.number_input("Release Height (m)", value=2.0, min_value=0.0)
                erate = st.number_input("Emission Rate (g/s/m2)", value=0.0001, format="%.6f")

            st.markdown("**Vertex Coordinates (UTM m)**")
            vertices = []
            for i in range(int(nv)):
                c1, c2 = st.columns(2)
                with c1:
                    vx = st.number_input(
                        f"V{i+1} X", value=default_x + i * 50.0,
                        format="%.2f", key=f"poly_vx_{i}",
                    )
                with c2:
                    vy = st.number_input(
                        f"V{i+1} Y", value=default_y + (i % 2) * 50.0,
                        format="%.2f", key=f"poly_vy_{i}",
                    )
                vertices.append((vx, vy))

            if st.form_submit_button("Add Polygon Source"):
                return AreaPolySource(
                    source_id=sid, vertices=vertices, base_elevation=elev,
                    release_height=rh, emission_rate=erate,
                )
        return None

    @staticmethod
    def render_volume_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[VolumeSource]:
        with st.form("volume_source_form"):
            st.subheader("Volume Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="VOL1")
                x = st.number_input("X Coordinate (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("Y Coordinate (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                rh = st.number_input("Release Height (m)", value=10.0, min_value=0.0)
                lat_dim = st.number_input("Initial Sigma-Y (m)", value=7.0, min_value=0.0)
                vert_dim = st.number_input("Initial Sigma-Z (m)", value=3.5, min_value=0.0)
            erate = st.number_input("Emission Rate (g/s)", value=1.0, format="%.6f")

            if st.form_submit_button("Add Volume Source"):
                return VolumeSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    release_height=rh, initial_lateral_dimension=lat_dim,
                    initial_vertical_dimension=vert_dim,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_line_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[LineSource]:
        with st.form("line_source_form"):
            st.subheader("Line Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="LINE1")
                xs = st.number_input("X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Y Start (UTM m)", value=default_y, format="%.2f")
            with col2:
                xe = st.number_input("X End (UTM m)", value=default_x + 500, format="%.2f")
                ye = st.number_input("Y End (UTM m)", value=default_y, format="%.2f")
                rh = st.number_input("Release Height (m)", value=0.0, min_value=0.0)
            elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f", key="line_elev")
            lat_dim = st.number_input("Initial Sigma-Y (m)", value=1.0, min_value=0.0)
            erate = st.number_input("Emission Rate (g/s/m)", value=0.001, format="%.6f")

            if st.form_submit_button("Add Line Source"):
                return LineSource(
                    source_id=sid, x_start=xs, y_start=ys,
                    x_end=xe, y_end=ye, release_height=rh,
                    base_elevation=elev,
                    initial_lateral_dimension=lat_dim,
                    emission_rate=erate,
                )
        return None

    @staticmethod
    def render_rline_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[RLineSource]:
        with st.form("rline_source_form"):
            st.subheader("Roadway (RLINE) Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="ROAD1")
                xs = st.number_input("X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Y Start (UTM m)", value=default_y, format="%.2f")
            with col2:
                xe = st.number_input("X End (UTM m)", value=default_x + 1000, format="%.2f")
                ye = st.number_input("Y End (UTM m)", value=default_y, format="%.2f")
                rh = st.number_input("Release Height (m)", value=0.5, min_value=0.0)
            elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f", key="rline_elev")
            col3, col4 = st.columns(2)
            with col3:
                lat_dim = st.number_input("Lane Half-Width (m)", value=3.0, min_value=0.0)
            with col4:
                vert_dim = st.number_input("Initial Mixing (m)", value=1.5, min_value=0.0)
            erate = st.number_input("Emission Rate (g/s/m)", value=0.001, format="%.6f")

            st.markdown("**Street Canyon (optional)**")
            use_canyon = st.checkbox("Enable street canyon approximation", key="rline_canyon")
            canyon_kwargs = {}
            if use_canyon:
                cc1, cc2 = st.columns(2)
                with cc1:
                    bh = st.number_input("Building Height (m)", value=15.0, min_value=0.1, key="rline_bh")
                with cc2:
                    sw = st.number_input("Street Width (m)", value=20.0, min_value=0.1, key="rline_sw")
                canyon_kwargs["street_canyon"] = StreetCanyon(building_height=bh, street_width=sw)
                ar = bh / sw
                factor = canyon_kwargs["street_canyon"].concentration_factor()
                st.caption(f"Aspect ratio H/W = {ar:.2f} — concentration factor = {factor:.2f}x")

            if st.form_submit_button("Add Roadway Source"):
                return RLineSource(
                    source_id=sid, x_start=xs, y_start=ys,
                    x_end=xe, y_end=ye, release_height=rh,
                    base_elevation=elev,
                    initial_lateral_dimension=lat_dim,
                    initial_vertical_dimension=vert_dim,
                    emission_rate=erate,
                    **canyon_kwargs,
                )
        return None

    @staticmethod
    def render_rlinext_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[RLineExtSource]:
        with st.form("rlinext_source_form"):
            st.subheader("Extended Roadway (RLINEXT) Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="REXT1")
                xs = st.number_input("X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Y Start (UTM m)", value=default_y, format="%.2f")
                zs = st.number_input("Z Start (m)", value=1.5, min_value=0.0)
            with col2:
                xe = st.number_input("X End (UTM m)", value=default_x + 500, format="%.2f")
                ye = st.number_input("Y End (UTM m)", value=default_y, format="%.2f")
                ze = st.number_input("Z End (m)", value=1.5, min_value=0.0)
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            col3, col4 = st.columns(2)
            with col3:
                width = st.number_input("Road Width (m)", value=30.0, min_value=0.1)
                dcl = st.number_input("Centerline Offset (m)", value=0.0)
            with col4:
                isz = st.number_input("Initial Sigma-Z (m)", value=1.5, min_value=0.0)
            erate = st.number_input("Emission Rate (g/m/s)", value=0.001, format="%.6f")

            st.markdown("**Depression (optional)**")
            col5, col6 = st.columns(2)
            with col5:
                depth = st.number_input("Depression Depth (m, negative)", value=0.0, max_value=0.0)
                wtop = st.number_input("Depression Top Width (m)", value=0.0, min_value=0.0)
            with col6:
                wbot = st.number_input("Depression Bottom Width (m)", value=0.0, min_value=0.0)

            st.markdown("**Street Canyon (optional)**")
            use_canyon = st.checkbox("Enable street canyon approximation", key="rlinext_canyon")
            canyon_obj = None
            if use_canyon:
                cc1, cc2 = st.columns(2)
                with cc1:
                    bh = st.number_input("Building Height (m)", value=15.0, min_value=0.1, key="rlinext_bh")
                with cc2:
                    sw = st.number_input("Street Width (m)", value=20.0, min_value=0.1, key="rlinext_sw")
                canyon_obj = StreetCanyon(building_height=bh, street_width=sw)
                ar = bh / sw
                factor = canyon_obj.concentration_factor()
                st.caption(f"Aspect ratio H/W = {ar:.2f} — concentration factor = {factor:.2f}x")

            if st.form_submit_button("Add RLINEXT Source"):
                kwargs = dict(
                    source_id=sid, x_start=xs, y_start=ys, z_start=zs,
                    x_end=xe, y_end=ye, z_end=ze, base_elevation=elev,
                    emission_rate=erate, dcl=dcl, road_width=width,
                    init_sigma_z=isz,
                )
                if depth < 0:
                    kwargs.update(depression_depth=depth, depression_wtop=wtop,
                                  depression_wbottom=wbot)
                if canyon_obj is not None:
                    kwargs["street_canyon"] = canyon_obj
                return RLineExtSource(**kwargs)
        return None

    @staticmethod
    def render_buoyline_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[BuoyLineSource]:
        with st.form("buoyline_source_form"):
            st.subheader("Buoyant Line Source")
            sid = st.text_input("Group ID", value="BLP1")
            st.markdown("**Average Plume Rise Parameters (BLPINPUT)**")
            col1, col2 = st.columns(2)
            with col1:
                avg_ll = st.number_input("Avg Line Length (m)", value=100.0, min_value=0.1)
                avg_bh = st.number_input("Avg Building Height (m)", value=15.0, min_value=0.1)
                avg_bw = st.number_input("Avg Building Width (m)", value=10.0, min_value=0.1)
            with col2:
                avg_lw = st.number_input("Avg Line Width (m)", value=5.0, min_value=0.1)
                avg_bs = st.number_input("Avg Building Separation (m)", value=20.0, min_value=0.0)
                avg_bp = st.number_input("Avg Buoyancy Param (m4/s3)", value=500.0, min_value=0.0, format="%.2f")
            st.markdown("**Line Segment**")
            col3, col4 = st.columns(2)
            with col3:
                seg_id = st.text_input("Segment ID", value="BL01")
                xs = st.number_input("Seg X Start (UTM m)", value=default_x, format="%.2f")
                ys = st.number_input("Seg Y Start (UTM m)", value=default_y, format="%.2f")
            with col4:
                xe = st.number_input("Seg X End (UTM m)", value=default_x + 100, format="%.2f")
                ye = st.number_input("Seg Y End (UTM m)", value=default_y, format="%.2f")
                rh = st.number_input("Seg Release Height (m)", value=4.5, min_value=0.0)
            erate = st.number_input("Seg Emission Rate (g/s)", value=10.0, format="%.6f")

            if st.form_submit_button("Add Buoyant Line Source"):
                seg = BuoyLineSegment(
                    source_id=seg_id, x_start=xs, y_start=ys,
                    x_end=xe, y_end=ye, emission_rate=erate,
                    release_height=rh,
                )
                return BuoyLineSource(
                    source_id=sid,
                    avg_line_length=avg_ll, avg_building_height=avg_bh,
                    avg_building_width=avg_bw, avg_line_width=avg_lw,
                    avg_building_separation=avg_bs, avg_buoyancy_parameter=avg_bp,
                    line_segments=[seg],
                )
        return None

    @staticmethod
    def render_openpit_source_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional[OpenPitSource]:
        with st.form("openpit_source_form"):
            st.subheader("Open Pit Source")
            col1, col2 = st.columns(2)
            with col1:
                sid = st.text_input("Source ID", value="PIT1")
                x = st.number_input("SW Corner X (UTM m)", value=default_x, format="%.2f")
                y = st.number_input("SW Corner Y (UTM m)", value=default_y, format="%.2f")
                elev = st.number_input("Base Elevation (m)", value=0.0, format="%.2f")
            with col2:
                xdim = st.number_input("X Dimension (m)", value=200.0, min_value=0.1)
                ydim = st.number_input("Y Dimension (m)", value=100.0, min_value=0.1)
                vol = st.number_input("Pit Volume (m3)", value=100000.0, min_value=0.1, format="%.2f")
                angle = st.number_input("Rotation Angle (deg)", value=0.0)
            erate = st.number_input("Emission Rate (g/s/m2)", value=0.005, format="%.6f")
            rh = st.number_input("Release Height (m)", value=0.0, min_value=0.0)

            if st.form_submit_button("Add Open Pit Source"):
                return OpenPitSource(
                    source_id=sid, x_coord=x, y_coord=y, base_elevation=elev,
                    emission_rate=erate, release_height=rh,
                    x_dimension=xdim, y_dimension=ydim,
                    pit_volume=vol, angle=angle,
                )
        return None


# ============================================================================
# BUILDING FORM FACTORY (BPIP)
# ============================================================================


class BuildingFormFactory:
    """Generates Streamlit form widgets for building definitions."""

    @staticmethod
    def render_building_form(
        default_x: float = 0.0, default_y: float = 0.0,
    ) -> Optional["Building"]:
        if not HAS_BPIP:
            st.warning("BPIP module not available.")
            return None

        with st.form("building_form"):
            st.subheader("Building Definition")
            col1, col2 = st.columns(2)
            with col1:
                bid = st.text_input("Building ID", value="BLDG1")
                height = st.number_input("Building Height (m)", value=20.0, min_value=0.1)
            with col2:
                st.markdown("**4 corners (counterclockwise)**")

            st.markdown("**Corner Coordinates (UTM m)**")
            # Default: rectangular building around center
            default_corners = [
                (default_x, default_y),
                (default_x + 50, default_y),
                (default_x + 50, default_y + 30),
                (default_x, default_y + 30),
            ]
            corners = []
            for i in range(4):
                c1, c2 = st.columns(2)
                with c1:
                    cx = st.number_input(
                        f"Corner {i+1} X", value=default_corners[i][0],
                        format="%.2f", key=f"bldg_cx_{i}",
                    )
                with c2:
                    cy = st.number_input(
                        f"Corner {i+1} Y", value=default_corners[i][1],
                        format="%.2f", key=f"bldg_cy_{i}",
                    )
                corners.append((cx, cy))

            if st.form_submit_button("Add Building"):
                try:
                    return Building(
                        building_id=bid, corners=corners, height=height,
                    )
                except ValueError as e:
                    st.error(str(e))
        return None


# ============================================================================
# GUI PAGES
