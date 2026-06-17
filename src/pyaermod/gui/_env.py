"""Shared imports and optional-dependency flags for the PyAERMOD GUI.

Single import hub for the gui package: every gui submodule does
`from ._env import *`, so optional deps (streamlit, folium, geospatial, ...)
and their HAS_* flags are resolved in exactly one place.
"""
import contextlib
import dataclasses
import json
import math
import os
import subprocess
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False
    st = None  # Allow module import for testing; main() will check

try:
    import folium
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# PyAERMOD imports
from ..input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    DepositionMethod,
    DiscreteReceptor,
    EventPathway,
    EventPeriod,
    GasDepositionParams,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    OzoneData,
    ParticleDepositionParams,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SourceGroupDefinition,
    SourcePathway,
    SourceType,
    StreetCanyon,
    TerrainType,
    VolumeSource,
)

try:
    from ..geospatial import (
        ContourGenerator,
        CoordinateTransformer,
        GeoDataFrameFactory,
        RasterExporter,
        VectorExporter,
        export_concentration_geotiff,
        export_concentration_shapefile,
    )
    HAS_GEO = True
except ImportError:
    HAS_GEO = False

try:
    from ..runner import AERMODRunner, run_aermod
    HAS_RUNNER = True
except ImportError:
    HAS_RUNNER = False

try:
    from ..output_parser import AERMODOutputParser, parse_aermod_output
    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False

try:
    from ..postfile import (
        PostfileParser,
        PostfileResult,
        UnformattedPostfileParser,
        read_postfile,
    )
    HAS_POSTFILE = True
except ImportError:
    HAS_POSTFILE = False

try:
    from ..advanced_viz import AdvancedVisualizer
    HAS_ADVANCED_VIZ = True
except ImportError:
    HAS_ADVANCED_VIZ = False

try:
    from ..validator import Validator
    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False

try:
    from ..visualization import AERMODVisualizer
    HAS_VIZ = True
except ImportError:
    HAS_VIZ = False

try:
    from ..terrain import AERMAPOutputParser
    HAS_TERRAIN = True
except ImportError:
    HAS_TERRAIN = False

try:
    from ..bpip import BPIPCalculator, BPIPResult, Building
    HAS_BPIP = True
except ImportError:
    HAS_BPIP = False

try:
    from ..aermet import (
        AERMETStage1,
        AERMETStage2,
        AERMETStage3,
        AERMETStation,
        UpperAirStation,
    )
    HAS_AERMET = True
except ImportError:
    HAS_AERMET = False
