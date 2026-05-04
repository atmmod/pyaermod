"""
JSON save/load for the GUI v2 :class:`AppState`.

UI-framework-agnostic: the legacy Streamlit ``ProjectSerializer`` is
tightly coupled to ``st.session_state`` and lives in :mod:`pyaermod.gui`.
This module is the headless equivalent — both GUIs can converge on it
once Streamlit is deprecated in v2.0.

Format
------

Top-level JSON dict::

    {
      "pyaermod_version": "1.9.0",
      "save_format_version": 1,
      "project": <AERMODProject as dataclass-asdict tree, with _type tags>
    }

Source / receptor lists carry per-element ``_type`` discriminators so
the loader can dispatch to the right dataclass on read-back. Enums are
encoded as ``{"_enum": "EnumClass.MEMBER"}``.
"""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import Path
from typing import Any, Type, Union

from ..input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BuoyLineSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    PointSource,
    PolarGrid,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SourcePathway,
    VolumeSource,
)

SAVE_FORMAT_VERSION = 1


_SOURCE_TYPES: dict[str, Type] = {
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

_RECEPTOR_TYPES: dict[str, Type] = {
    "CartesianGrid": CartesianGrid,
    "PolarGrid": PolarGrid,
    "DiscreteReceptor": DiscreteReceptor,
}


# ---------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------

class _Encoder(json.JSONEncoder):
    """JSON encoder for dataclasses, Enums, and numpy scalars."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return {"_enum": f"{type(obj).__name__}.{obj.name}"}
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            d = dataclasses.asdict(obj)
            d["_type"] = type(obj).__name__
            return d
        try:  # numpy scalars when the user mixed numpy values into the project
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


def _project_to_jsonable(project: AERMODProject) -> dict:
    """Convert an AERMODProject to a JSON-serializable dict tree.

    Adds ``_type`` discriminators for source / receptor list elements
    so the loader can dispatch on read.
    """
    d = json.loads(json.dumps(project, cls=_Encoder))
    # The default asdict path drops _type for *list elements* — we need
    # the discriminator on each source / receptor entry. Re-attach it
    # by walking the original project tree.
    if project.sources is not None and project.sources.sources:
        d["sources"]["sources"] = [
            {**dataclasses.asdict(s), "_type": type(s).__name__}
            for s in project.sources.sources
        ]
    if project.receptors is not None:
        for fname in ("cartesian_grids", "polar_grids", "discrete_receptors"):
            arr = getattr(project.receptors, fname, None)
            if arr:
                d["receptors"][fname] = [
                    {**dataclasses.asdict(r), "_type": type(r).__name__}
                    for r in arr
                ]
    return d


# ---------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------

def _strip(obj: Any) -> Any:
    """Drop _type / _enum tags before passing kwargs to a dataclass ctor."""
    if isinstance(obj, dict):
        if "_enum" in obj:
            return obj  # leave for resolve_enums; not a kwargs payload
        return {k: _strip(v) for k, v in obj.items() if k != "_type"}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def _resolve_enums(obj: Any, enum_lookup: dict[str, Type[Enum]]) -> Any:
    if isinstance(obj, dict):
        if "_enum" in obj:
            cls_name, member = obj["_enum"].split(".", 1)
            cls = enum_lookup.get(cls_name)
            if cls is None:
                return obj  # unknown enum; pass through
            return cls[member]
        return {k: _resolve_enums(v, enum_lookup) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_enums(v, enum_lookup) for v in obj]
    return obj


def _build_dataclass(cls: Type, payload: dict) -> Any:
    """Instantiate a dataclass from a payload dict, ignoring unknown keys."""
    valid = set(cls.__dataclass_fields__.keys())
    kwargs = {k: v for k, v in payload.items() if k in valid}
    return cls(**kwargs)


def _enum_lookup() -> dict[str, Type[Enum]]:
    """Build the enum-class registry used during deserialization."""
    from ..input_generator import (
        ChemistryMethod,
        DepositionMethod,
        PollutantType,
        SourceType,
        TerrainType,
    )
    return {
        "PollutantType": PollutantType,
        "SourceType": SourceType,
        "TerrainType": TerrainType,
        "ChemistryMethod": ChemistryMethod,
        "DepositionMethod": DepositionMethod,
    }


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def save_project(
    project: AERMODProject, path: Union[str, Path],
) -> Path:
    """Write ``project`` to ``path`` as JSON. Returns the path."""
    from .. import __version__

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pyaermod_version": __version__,
        "save_format_version": SAVE_FORMAT_VERSION,
        "project": _project_to_jsonable(project),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def load_project(path: Union[str, Path]) -> AERMODProject:
    """Read an AERMODProject from a JSON file written by :func:`save_project`.

    Tolerates older save formats by reading what's there and filling
    missing fields with dataclass defaults.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "project" not in raw:
        raise ValueError(f"{path}: not a pyaermod project file")
    sfv = raw.get("save_format_version")
    if sfv is not None and sfv > SAVE_FORMAT_VERSION:
        raise ValueError(
            f"{path}: save_format_version={sfv} is newer than this build "
            f"supports (max {SAVE_FORMAT_VERSION}). Upgrade pyaermod."
        )
    enums = _enum_lookup()
    project_dict = _resolve_enums(raw["project"], enums)

    # Pathways
    control_d = _strip(project_dict.get("control", {}))
    control = _build_dataclass(ControlPathway, control_d)

    src_payload = project_dict.get("sources", {})
    src_list_raw = src_payload.get("sources", []) if src_payload else []
    sources_list = []
    for s in src_list_raw:
        cls = _SOURCE_TYPES.get(s.get("_type", ""))
        if cls is None:
            continue
        sources_list.append(_build_dataclass(cls, _strip(s)))
    sources = SourcePathway(sources=sources_list)

    rec_payload = project_dict.get("receptors", {}) or {}
    cart = [
        _build_dataclass(CartesianGrid, _strip(g))
        for g in rec_payload.get("cartesian_grids", []) or []
        if g.get("_type") == "CartesianGrid"
    ]
    pol = [
        _build_dataclass(PolarGrid, _strip(g))
        for g in rec_payload.get("polar_grids", []) or []
        if g.get("_type") == "PolarGrid"
    ]
    disc = [
        _build_dataclass(DiscreteReceptor, _strip(g))
        for g in rec_payload.get("discrete_receptors", []) or []
        if g.get("_type") == "DiscreteReceptor"
    ]
    receptors = ReceptorPathway(
        cartesian_grids=cart, polar_grids=pol, discrete_receptors=disc,
    )

    met_d = _strip(project_dict.get("meteorology", {}) or {})
    meteorology = _build_dataclass(MeteorologyPathway, met_d)
    out_d = _strip(project_dict.get("output", {}) or {})
    output = _build_dataclass(OutputPathway, out_d)

    return AERMODProject(
        control=control, sources=sources, receptors=receptors,
        meteorology=meteorology, output=output,
    )


__all__ = [
    "SAVE_FORMAT_VERSION",
    "load_project",
    "save_project",
]
