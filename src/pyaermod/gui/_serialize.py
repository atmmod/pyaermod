"""Project save/load (JSON serialization) for the PyAERMOD GUI."""
from ._env import *


class ProjectSerializer:
    """Serialize/deserialize PyAERMOD GUI session state to/from JSON."""

    SAVE_FORMAT_VERSION = 1

    SOURCE_TYPE_MAP = {
        "PointSource": PointSource,
        "AreaSource": AreaSource,
        "AreaCircSource": AreaCircSource,
        "AreaPolySource": AreaPolySource,
        "VolumeSource": VolumeSource,
        "LineSource": LineSource,
        "RLineSource": RLineSource,
        "RLineExtSource": RLineExtSource,
        "BuoyLineSource": BuoyLineSource,
        "OpenPitSource": OpenPitSource,
    }

    RECEPTOR_TYPE_MAP = {
        "CartesianGrid": CartesianGrid,
        "PolarGrid": PolarGrid,
        "DiscreteReceptor": DiscreteReceptor,
    }

    PATHWAY_FIELDS = [
        "project_control", "project_sources", "project_receptors",
        "project_meteorology", "project_output",
    ]

    GEO_FIELDS = ["utm_zone", "hemisphere", "datum", "center_lat", "center_lon"]

    class _Encoder(json.JSONEncoder):
        """Custom JSON encoder for dataclasses, Enums, and numpy types."""

        def default(self, obj):
            if isinstance(obj, Enum):
                return {"_enum": f"{type(obj).__name__}.{obj.name}"}
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                d = dataclasses.asdict(obj)
                d["_type"] = type(obj).__name__
                return d
            # Handle numpy scalar types (int64, float64, bool_)
            try:
                import numpy as np
                if isinstance(obj, np.integer):
                    return int(obj)
                if isinstance(obj, np.floating):
                    return float(obj)
                if isinstance(obj, np.bool_):
                    return bool(obj)
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
            except ImportError:
                pass
            return super().default(obj)

    @classmethod
    def serialize_session_state(cls) -> str:
        """Convert current session state to JSON string."""
        from pyaermod import __version__

        data = {
            "pyaermod_version": __version__,
            "save_format_version": cls.SAVE_FORMAT_VERSION,
        }

        # Pathways
        for key in cls.PATHWAY_FIELDS:
            obj = st.session_state.get(key)
            if obj is not None:
                if key == "project_sources":
                    # Inject _type for each source
                    src_list = []
                    for src in obj.sources:
                        d = dataclasses.asdict(src)
                        d["_type"] = type(src).__name__
                        src_list.append(d)
                    bg_data = None
                    if obj.background is not None:
                        bg_data = dataclasses.asdict(obj.background)
                        # Convert tuple keys in sector_values to lists for JSON
                        if bg_data.get("sector_values"):
                            bg_data["sector_values"] = [
                                [k[0], k[1], v]
                                for k, v in bg_data["sector_values"].items()
                            ]
                    group_defs = [dataclasses.asdict(g) for g in obj.group_definitions]
                    data[key] = {
                        "sources": src_list,
                        "background": bg_data,
                        "group_definitions": group_defs,
                    }
                elif key == "project_receptors":
                    data[key] = {
                        "cartesian_grids": [dataclasses.asdict(g) for g in obj.cartesian_grids],
                        "polar_grids": [dataclasses.asdict(g) for g in obj.polar_grids],
                        "discrete_receptors": [dataclasses.asdict(r) for r in obj.discrete_receptors],
                        "elevation_units": obj.elevation_units,
                    }
                else:
                    data[key] = dataclasses.asdict(obj)

        # Geo settings
        data["geo_settings"] = {k: st.session_state.get(k) for k in cls.GEO_FIELDS}

        # Buildings (for BPIP)
        buildings = st.session_state.get("buildings", [])
        data["buildings"] = [dataclasses.asdict(b) for b in buildings]

        # AERMET config
        aermet_config = {"mode": st.session_state.get("aermet_mode", "files")}
        for key in ("aermet_stage1", "aermet_stage2", "aermet_stage3"):
            obj = st.session_state.get(key)
            if obj is not None:
                d = dataclasses.asdict(obj)
                d["_type"] = type(obj).__name__
                aermet_config[key] = d
            else:
                aermet_config[key] = None
        data["aermet_config"] = aermet_config

        # Event processing
        events = st.session_state.get("project_events")
        if events is not None:
            data["project_events"] = dataclasses.asdict(events)
        else:
            data["project_events"] = None

        return json.dumps(data, cls=cls._Encoder, indent=2)

    @classmethod
    def deserialize_session_state(cls, json_str: str) -> dict:
        """Parse JSON and reconstruct session state objects."""
        data = json.loads(json_str)

        version = data.get("save_format_version", 0)
        if version > cls.SAVE_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported save format version {version} "
                f"(max supported: {cls.SAVE_FORMAT_VERSION})"
            )

        result = {}

        # Control pathway
        if "project_control" in data:
            result["project_control"] = cls._deserialize_control(data["project_control"])

        # Sources
        if "project_sources" in data:
            sources = []
            for src_data in data["project_sources"].get("sources", []):
                sources.append(cls._deserialize_source(src_data))
            sp = SourcePathway()
            sp.sources = sources
            bg_data = data["project_sources"].get("background")
            if bg_data:
                sectors = None
                if bg_data.get("sectors"):
                    sectors = [
                        BackgroundSector(**s) for s in bg_data["sectors"]
                    ]
                sector_values = None
                if bg_data.get("sector_values"):
                    sector_values = {
                        (item[0], item[1]): item[2]
                        for item in bg_data["sector_values"]
                    }
                sp.background = BackgroundConcentration(
                    uniform_value=bg_data.get("uniform_value"),
                    period_values=bg_data.get("period_values"),
                    sectors=sectors,
                    sector_values=sector_values,
                )
            # Reconstruct source group definitions
            for gd in data["project_sources"].get("group_definitions", []):
                gd_copy = dict(gd)
                gd_copy.pop("_type", None)
                sp.group_definitions.append(SourceGroupDefinition(**gd_copy))

            result["project_sources"] = sp

        # Receptors
        if "project_receptors" in data:
            result["project_receptors"] = cls._deserialize_receptors(data["project_receptors"])

        # Meteorology
        if "project_meteorology" in data:
            d = data["project_meteorology"]
            d.pop("_type", None)
            result["project_meteorology"] = MeteorologyPathway(**d)

        # Output
        if "project_output" in data:
            d = data["project_output"]
            d.pop("_type", None)
            # Convert plot_file_groups back to tuples
            if d.get("plot_file_groups"):
                d["plot_file_groups"] = [tuple(item) for item in d["plot_file_groups"]]
            result["project_output"] = OutputPathway(**d)

        # Geo settings
        geo = data.get("geo_settings", {})
        for k in cls.GEO_FIELDS:
            if k in geo:
                result[k] = geo[k]

        # Buildings
        if "buildings" in data:
            try:
                from ..bpip import Building
                result["buildings"] = [cls._deserialize_building(b) for b in data["buildings"]]
            except ImportError:
                result["buildings"] = []

        # AERMET config
        aermet = data.get("aermet_config", {})
        if aermet:
            result["aermet_mode"] = aermet.get("mode", "files")
            for key, stage_cls in [
                ("aermet_stage1", AERMETStage1 if HAS_AERMET else None),
                ("aermet_stage2", AERMETStage2 if HAS_AERMET else None),
                ("aermet_stage3", AERMETStage3 if HAS_AERMET else None),
            ]:
                d = aermet.get(key)
                if d is not None and stage_cls is not None:
                    result[key] = cls._deserialize_aermet_stage(d, stage_cls)
                else:
                    result[key] = None

        # Events
        events_data = data.get("project_events")
        if events_data:
            event_list = [
                EventPeriod(**ep) for ep in events_data.get("events", [])
            ]
            result["project_events"] = EventPathway(events=event_list)
        else:
            result["project_events"] = None

        return result

    @classmethod
    def _resolve_enum(cls, value):
        """Resolve an enum dict like {'_enum': 'PollutantType.PM25'} to actual Enum."""
        if isinstance(value, dict) and "_enum" in value:
            enum_str = value["_enum"]
            cls_name, member_name = enum_str.split(".", 1)
            enum_classes = {
                "PollutantType": PollutantType,
                "TerrainType": TerrainType,
                "SourceType": SourceType,
                "ChemistryMethod": ChemistryMethod,
                "DepositionMethod": DepositionMethod,
            }
            enum_cls = enum_classes.get(cls_name)
            if enum_cls:
                return enum_cls[member_name]
        return value

    @classmethod
    def _deserialize_control(cls, data: dict) -> ControlPathway:
        """Reconstruct ControlPathway with enums."""
        d = dict(data)
        d.pop("_type", None)
        if "pollutant_id" in d:
            d["pollutant_id"] = cls._resolve_enum(d["pollutant_id"])
        if "terrain_type" in d:
            d["terrain_type"] = cls._resolve_enum(d["terrain_type"])

        # Reconstruct chemistry options
        if "chemistry" in d and d["chemistry"] is not None:
            chem_data = dict(d["chemistry"])
            chem_data.pop("_type", None)
            if "method" in chem_data:
                chem_data["method"] = cls._resolve_enum(chem_data["method"])
            if "ozone_data" in chem_data and chem_data["ozone_data"] is not None:
                oz_data = dict(chem_data["ozone_data"])
                oz_data.pop("_type", None)
                # JSON serializes Dict[int, float] keys as strings; convert back
                if oz_data.get("sector_values") is not None:
                    oz_data["sector_values"] = {
                        int(k): v for k, v in oz_data["sector_values"].items()
                    }
                chem_data["ozone_data"] = OzoneData(**oz_data)
            if chem_data.get("olm_groups"):
                chem_data["olm_groups"] = [
                    SourceGroupDefinition(**{k: v for k, v in g.items() if k != "_type"})
                    for g in chem_data["olm_groups"]
                ]
            else:
                chem_data["olm_groups"] = []
            d["chemistry"] = ChemistryOptions(**chem_data)

        return ControlPathway(**d)

    @classmethod
    def _deserialize_source(cls, data: dict):
        """Reconstruct a source object from dict with _type key."""
        d = dict(data)
        type_name = d.pop("_type", None)
        if type_name not in cls.SOURCE_TYPE_MAP:
            raise ValueError(f"Unknown source type: {type_name}")

        src_cls = cls.SOURCE_TYPE_MAP[type_name]

        # Handle AreaPolySource: convert vertex lists back to tuples
        if type_name == "AreaPolySource" and "vertices" in d:
            d["vertices"] = [tuple(v) for v in d["vertices"]]

        # Handle BuoyLineSource: reconstruct nested BuoyLineSegments
        if type_name == "BuoyLineSource" and "line_segments" in d:
            segments = []
            for seg_data in d["line_segments"]:
                seg_data.pop("_type", None)
                segments.append(BuoyLineSegment(**seg_data))
            d["line_segments"] = segments

        # Reconstruct deposition parameter dataclasses
        if d.get("gas_deposition") is not None and isinstance(d["gas_deposition"], dict):
            d["gas_deposition"] = GasDepositionParams(**d["gas_deposition"])
        if d.get("particle_deposition") is not None and isinstance(d["particle_deposition"], dict):
            d["particle_deposition"] = ParticleDepositionParams(**d["particle_deposition"])
        if d.get("deposition_method") is not None and isinstance(d["deposition_method"], list):
            enum_val = cls._resolve_enum(d["deposition_method"][0])
            d["deposition_method"] = (enum_val, d["deposition_method"][1])

        # Reconstruct StreetCanyon if present
        if d.get("street_canyon") is not None and isinstance(d["street_canyon"], dict):
            d["street_canyon"] = StreetCanyon(**d["street_canyon"])

        return src_cls(**d)

    @classmethod
    def _deserialize_receptors(cls, data: dict) -> ReceptorPathway:
        """Reconstruct ReceptorPathway with grids and discrete receptors."""
        rp = ReceptorPathway()
        rp.elevation_units = data.get("elevation_units", "METERS")

        for g in data.get("cartesian_grids", []):
            g.pop("_type", None)
            rp.cartesian_grids.append(CartesianGrid(**g))
        for g in data.get("polar_grids", []):
            g.pop("_type", None)
            rp.polar_grids.append(PolarGrid(**g))
        for r in data.get("discrete_receptors", []):
            r.pop("_type", None)
            rp.discrete_receptors.append(DiscreteReceptor(**r))

        return rp

    @classmethod
    def _deserialize_building(cls, data: dict):
        """Reconstruct a Building object from dict."""
        from ..bpip import Building
        d = dict(data)
        d.pop("_type", None)
        # Convert corner lists to tuples
        if "corners" in d:
            d["corners"] = [tuple(c) for c in d["corners"]]
        # Convert tier lists to tuples
        if d.get("tiers") is not None:
            d["tiers"] = [tuple(t) for t in d["tiers"]]
        return Building(**d)

    @classmethod
    def _deserialize_aermet_stage(cls, data: dict, stage_cls):
        """Reconstruct an AERMET stage object from dict."""
        d = dict(data)
        d.pop("_type", None)

        # Reconstruct nested station objects
        if "surface_station" in d and d["surface_station"] is not None:
            sd = dict(d["surface_station"])
            sd.pop("_type", None)
            d["surface_station"] = AERMETStation(**sd)
        if "upper_air_station" in d and d["upper_air_station"] is not None:
            ud = dict(d["upper_air_station"])
            ud.pop("_type", None)
            d["upper_air_station"] = UpperAirStation(**ud)
        if "station" in d and d["station"] is not None:
            sd = dict(d["station"])
            sd.pop("_type", None)
            d["station"] = AERMETStation(**sd)

        return stage_cls(**d)


# ============================================================================
# MAP EDITOR
# ============================================================================
