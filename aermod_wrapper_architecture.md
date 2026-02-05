# AERMOD Python Wrapper - Technical Architecture

## Executive Summary

This document outlines the technical architecture for a Python wrapper around the AERMOD Fortran codebase. The wrapper aims to provide an accessible, API-driven interface for regulatory dispersion modeling without requiring expensive consulting services or direct Fortran expertise.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                     │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐│
│  │ CLI Tool   │  │ Python API   │  │ Web Dashboard (opt.) ││
│  └────────────┘  └──────────────┘  └──────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              Core Python Wrapper (pyaermod)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Configuration & Parameter Management                 │  │
│  │  - Input validation                                   │  │
│  │  - Parameter serialization                            │  │
│  │  - Project templates                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Input File Generation                                │  │
│  │  - AERMOD control file (.inp)                        │  │
│  │  - Source configuration                               │  │
│  │  - Receptor grid generation                           │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Process Management                                   │  │
│  │  - AERMOD executable wrapper                         │  │
│  │  - AERMET integration                                │  │
│  │  - AERMAP integration                                │  │
│  │  - Error handling & logging                          │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Output Parsing & Processing                         │  │
│  │  - Result file parsing                               │  │
│  │  - Data structure conversion (to DataFrame/NetCDF)  │  │
│  │  - Statistical analysis                              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                  Data Integration Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Meteorology  │  │ Terrain/Maps │  │ Emissions Data   │ │
│  │ APIs         │  │ APIs         │  │ Sources          │ │
│  └──────────────┘  └──────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              Visualization & Export Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Plotly/      │  │ Folium/      │  │ Report           │ │
│  │ Matplotlib   │  │ Leaflet      │  │ Generation       │ │
│  │ (Contours)   │  │ (Interactive)│  │ (PDF/HTML)       │ │
│  └──────────────┘  └──────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   AERMOD Fortran Core                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ AERMOD       │  │ AERMET       │  │ AERMAP           │ │
│  │ (dispersion) │  │ (met prep)   │  │ (terrain prep)   │ │
│  └──────────────┘  └──────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Configuration & Parameter Management

**Purpose**: Provide a Pythonic interface for AERMOD configuration

**Key Features**:
- Object-oriented parameter definition using dataclasses or Pydantic models
- JSON/YAML configuration file support
- Input validation with clear error messages
- Default parameter sets for common scenarios
- Template system for regulatory compliance (EPA guidelines)

**Example API**:
```python
from pyaermod import AERMODProject, PointSource, ReceptorGrid

project = AERMODProject(
    name="facility_assessment",
    pollutant="PM2.5",
    averaging_periods=["1HR", "24HR", "ANNUAL"]
)

# Define emission source
stack = PointSource(
    id="STACK1",
    location=(latitude, longitude, elevation),
    height=50.0,  # meters
    diameter=2.0,
    temperature=400.0,  # K
    velocity=15.0,  # m/s
    emission_rate=1.5  # g/s
)

# Define receptor grid
grid = ReceptorGrid.from_bounds(
    bounds=(min_x, min_y, max_x, max_y),
    spacing=100,  # meters
    coordinate_system="UTM"
)
```

### 2. Input File Generation

**Purpose**: Convert Python objects to AERMOD-compatible input files

**Components**:
- **Control File Generator**: Creates .inp files from Python objects
- **Receptor Generator**: Handles Cartesian/polar grids, discrete receptors, fence lines
- **Source Configuration**: Supports point, area, volume, line sources
- **Keyword Parser**: Validates AERMOD keywords and options

**File Structure**:
```
CO STARTING
   TITLEONE  Project generated by pyaermod
   MODELOPT  CONC FLAT
   AVERTIME  1 24 ANNUAL
   POLLUTID  PM25
   RUNORNOT  RUN
CO FINISHED

SO STARTING
   LOCATION  STACK1 POINT <x> <y> <base_elev>
   SRCPARAM  STACK1 <emission> <height> <temp> <velocity> <diameter>
SO FINISHED

RE STARTING
   ... (receptor definitions)
RE FINISHED
```

### 3. Process Management & Execution

**Purpose**: Orchestrate AERMOD executable runs

**Features**:
- Subprocess management with timeout controls
- Platform-specific executable detection (Windows .exe, Linux binary)
- Environment variable configuration
- Progress monitoring and log capture
- Parallel run support for sensitivity analysis
- Resource management (temp directories, cleanup)

**Implementation**:
```python
class AERMODRunner:
    def __init__(self, executable_path=None):
        self.executable = executable_path or self._find_aermod()

    def run(self, input_file, working_dir=None, timeout=3600):
        """Execute AERMOD with error handling"""
        # Validate inputs
        # Set up working directory
        # Execute subprocess
        # Capture stdout/stderr
        # Parse return codes
        # Return results object

    def run_batch(self, scenarios, n_workers=4):
        """Run multiple scenarios in parallel"""
        # Use multiprocessing Pool or concurrent.futures
```

### 4. Data Integration Layer

**Purpose**: Connect to external data sources

**API Integrations**:

#### Meteorological Data
- **NOAA ISD**: Historical surface observations
- **ERA5/MERRA-2**: Reanalysis data via climate APIs
- **Local weather stations**: Custom data ingestion
- **AERMINUTE**: 1-minute ASOS data for AERMET processing

```python
from pyaermod.data import MeteorologicalData

# Fetch and prepare meteorological data
met_data = MeteorologicalData.from_noaa(
    station_id="KDEN",
    start_date="2023-01-01",
    end_date="2023-12-31"
)

# Automatically run AERMET preprocessing
surface_file, profile_file = met_data.prepare_for_aermod(
    output_dir="./met_processed"
)
```

#### Terrain/Elevation Data
- **USGS NED**: National Elevation Dataset
- **SRTM**: Shuttle Radar Topography Mission
- **OpenTopography**: High-resolution DEM access
- Automatic AERMAP execution

```python
from pyaermod.terrain import TerrainProcessor

terrain = TerrainProcessor.from_usgs(
    bounds=(min_lon, min_lat, max_lon, max_lat),
    resolution=10  # meters
)

# Generate AERMAP terrain file
terrain_file = terrain.process_for_aermod(
    receptors=grid,
    sources=[stack]
)
```

#### Base Maps for Visualization
- **OpenStreetMap**: Tile layers
- **Mapbox**: Custom styling
- **ESRI**: Satellite imagery
- **Census TIGER**: Boundaries and features

### 5. Output Parsing & Analysis

**Purpose**: Extract and structure AERMOD results

**Features**:
- Parse .out files for concentration/deposition results
- Convert to pandas DataFrame or xarray Dataset
- Calculate statistical summaries (max, percentiles, exceedances)
- Spatial interpolation for smooth contours
- Time-series extraction at specific receptors
- Regulatory compliance checking (NAAQS comparison)

**Output Structure**:
```python
class AERMODResults:
    def __init__(self, output_file):
        self.metadata = self._parse_header()
        self.concentrations = self._parse_concentrations()

    def to_dataframe(self, averaging_period="24HR"):
        """Returns DataFrame with columns: x, y, concentration, rank, etc."""

    def get_max_impact(self, averaging_period="24HR"):
        """Returns location and value of maximum impact"""

    def check_compliance(self, standard, background=0.0):
        """Compare against regulatory standard"""

    def to_netcdf(self, output_path):
        """Export as NetCDF for GIS integration"""
```

### 6. Visualization Layer

**Purpose**: Create publication-ready graphics and interactive maps

**Visualization Types**:

#### Static Plots (Matplotlib/Plotly)
- Concentration contour plots
- Isopleths with customizable levels
- Source/receptor overlays
- Time-series plots
- Exceedance probability plots

```python
from pyaermod.viz import plot_contours

fig = plot_contours(
    results,
    averaging_period="ANNUAL",
    levels=[5, 10, 15, 20, 25],  # μg/m³
    colormap="YlOrRd",
    show_sources=True,
    show_max_location=True
)
fig.save("output.png", dpi=300)
```

#### Interactive Maps (Folium/Plotly)
- Leaflet-based web maps
- Zoom/pan capabilities
- Popup information on click
- Multiple layer controls
- Export to standalone HTML

```python
from pyaermod.viz import create_interactive_map

map_obj = create_interactive_map(
    results,
    basemap="OpenStreetMap",
    opacity=0.6,
    add_legend=True
)
map_obj.save("results_map.html")
```

#### Automated Reports
- PDF generation with charts and tables
- HTML dashboards with embedded visualizations
- Markdown reports for documentation
- Compliance summary sheets

### 7. Project Management

**Purpose**: Handle multi-scenario projects

**Features**:
- Project directory structure
- Version control for configurations
- Scenario comparison tools
- Sensitivity analysis automation
- Parameter sweep utilities

```python
from pyaermod import Project

proj = Project("facility_permit_renewal")

# Define base scenario
base = proj.create_scenario("baseline", ...)

# Create variations
for rate in [0.5, 1.0, 1.5, 2.0]:
    scenario = base.copy()
    scenario.sources["STACK1"].emission_rate = rate
    proj.add_scenario(f"emission_{rate}", scenario)

# Run all scenarios
results = proj.run_all(parallel=True, n_workers=4)

# Compare results
comparison = proj.compare_scenarios(
    metric="max_24hr_concentration"
)
```

## Technology Stack

### Core Dependencies

**Essential**:
- `numpy`: Numerical operations, array handling
- `pandas`: Tabular data manipulation
- `pydantic` or `dataclasses`: Configuration validation
- `click` or `typer`: CLI interface
- `subprocess`: AERMOD execution
- `pathlib`: Cross-platform path handling

**Data Integration**:
- `requests`: API calls
- `xarray`: Multi-dimensional arrays (meteorological data)
- `rasterio`: Geospatial raster data (terrain)
- `geopandas`: Vector geospatial data
- `pyproj`: Coordinate transformations

**Visualization**:
- `matplotlib`: Basic plotting
- `plotly`: Interactive charts
- `folium`: Interactive maps
- `contextily`: Basemap tiles
- `reportlab` or `weasyprint`: PDF generation

**Optional**:
- `dask`: Large-scale parallel computing
- `netCDF4`: NetCDF file I/O
- `h5py`: HDF5 for large datasets
- `streamlit` or `dash`: Web dashboard
- `pytest`: Testing framework
- `sphinx`: Documentation generation

### Fortran Integration Strategy

**Approach 1: Subprocess Wrapper (Recommended for MVP)**
- No Fortran recompilation needed
- Use existing EPA-certified binaries
- Communicate via input/output files
- Pros: Simple, regulatory acceptance maintained
- Cons: File I/O overhead, no in-memory access

**Approach 2: F2PY Integration (Future Enhancement)**
- Wrap specific Fortran subroutines with f2py
- Call Fortran directly from Python
- Pros: Performance, memory efficiency
- Cons: Compilation complexity, certification concerns

**Approach 3: ISO C Binding (Advanced)**
- Create C interface to Fortran
- Use ctypes/cffi from Python
- Pros: Performance, cleaner interface
- Cons: Significant refactoring required

**MVP Recommendation**: Start with subprocess wrapper, design API to abstract execution method for future upgrades.

## Data Flow

### Typical Workflow

```
1. User Input (Python API or CLI)
           ↓
2. Configuration Validation
           ↓
3. Fetch External Data (met, terrain, maps)
           ↓
4. Generate AERMOD Input Files (.inp)
           ↓
5. Execute AERMOD Fortran Binary
           ↓
6. Parse Output Files (.out)
           ↓
7. Post-process Results (statistics, interpolation)
           ↓
8. Generate Visualizations (plots, maps)
           ↓
9. Create Reports (PDF/HTML)
           ↓
10. Return Results to User
```

### File Organization

```
project_root/
├── pyaermod/               # Main package
│   ├── __init__.py
│   ├── config/            # Configuration models
│   │   ├── sources.py
│   │   ├── receptors.py
│   │   ├── meteorology.py
│   │   └── project.py
│   ├── core/              # Core functionality
│   │   ├── input_writer.py
│   │   ├── runner.py
│   │   ├── output_parser.py
│   │   └── validator.py
│   ├── data/              # Data integration
│   │   ├── met_sources.py
│   │   ├── terrain.py
│   │   └── maps.py
│   ├── viz/               # Visualization
│   │   ├── plots.py
│   │   ├── maps.py
│   │   └── reports.py
│   ├── utils/             # Utilities
│   │   ├── coordinates.py
│   │   ├── units.py
│   │   └── validation.py
│   └── cli/               # Command-line interface
│       └── commands.py
├── tests/                 # Test suite
├── docs/                  # Documentation
├── examples/              # Example scripts
├── binaries/              # AERMOD executables (optional)
│   ├── linux/
│   └── windows/
└── setup.py
```

## API Design Principles

### 1. Pythonic Interface
- Follow PEP 8 naming conventions
- Use context managers for resource handling
- Provide sensible defaults
- Support both OOP and functional styles

### 2. Progressive Disclosure
- Simple tasks should be simple
- Advanced features available but not required
- Sane defaults based on EPA guidance

### 3. Type Safety
- Use type hints throughout
- Runtime validation with Pydantic
- Clear error messages

### 4. Flexibility
- Support multiple input formats (JSON, YAML, Python objects)
- Allow both high-level and low-level control
- Provide escape hatches for custom AERMOD keywords

## Error Handling & Logging

### Error Categories

1. **Configuration Errors**: Invalid parameters, missing required fields
2. **Execution Errors**: AERMOD runtime failures, missing executables
3. **Data Errors**: API failures, invalid meteorological data
4. **I/O Errors**: File access, disk space issues

### Logging Strategy

```python
import logging

# Structured logging with different levels
logger = logging.getLogger("pyaermod")

# User-friendly messages
logger.info("Starting AERMOD run for project: facility_assessment")
logger.warning("Meteorological data contains gaps, interpolating...")
logger.error("AERMOD execution failed: invalid source configuration")

# Debug mode for development
logger.debug(f"Generated input file:\n{input_content}")
```

### User Feedback

- Progress bars for long operations (tqdm)
- Clear error messages with suggestions
- Validation errors before execution (fail fast)
- Summary statistics after completion

## Testing Strategy

### Unit Tests
- Configuration object creation and validation
- Input file generation (compare against known-good files)
- Output parsing (use EPA test cases)
- Coordinate transformations
- Data validation logic

### Integration Tests
- Full AERMOD runs with EPA test datasets
- API data fetching (with mocking)
- End-to-end workflow tests

### Regression Tests
- Compare results against previous versions
- Validate against EPA reference implementations
- Ensure regulatory compliance is maintained

### Test Data
- Include EPA's test case suite
- Create minimal synthetic examples
- Document expected outputs

## Documentation Requirements

### User Documentation

1. **Quick Start Guide**
   - Installation instructions
   - First model run in 5 minutes
   - Basic concepts

2. **Tutorial Series**
   - Point source modeling
   - Area source modeling
   - Working with meteorological data
   - Visualization options
   - Batch processing

3. **API Reference**
   - Auto-generated from docstrings (Sphinx)
   - Type annotations
   - Examples for each function

4. **How-To Guides**
   - Regulatory compliance workflows
   - Data integration recipes
   - Custom visualization
   - Performance optimization

5. **FAQ & Troubleshooting**
   - Common errors and solutions
   - AERMOD-specific gotchas
   - Platform-specific issues

### Developer Documentation

1. **Architecture Overview** (this document)
2. **Contributing Guide**
   - Code style
   - Testing requirements
   - Pull request process

3. **API Design Rationale**
4. **Fortran Interface Details**
5. **Release Process**

### Regulatory Documentation

1. **EPA Compliance Statement**
   - Which AERMOD version is wrapped
   - Certification status
   - Limitations and disclaimers

2. **Validation Report**
   - Comparison with EPA test cases
   - Numerical precision analysis
   - Known differences (if any)

## Performance Considerations

### Optimization Strategies

1. **Parallel Execution**
   - Multi-scenario runs via multiprocessing
   - Batch processing for sensitivity analysis

2. **Caching**
   - Meteorological data caching
   - Terrain data caching
   - Parsed output caching

3. **Lazy Loading**
   - Only load data when needed
   - Stream large output files

4. **Efficient Data Structures**
   - Use numpy arrays for receptor grids
   - Consider HDF5 for large datasets

### Scalability

- Support for large receptor grids (>10,000 points)
- Multiple years of meteorological data
- Batch processing 100+ scenarios
- Cloud deployment considerations (Docker containers)

## Security & Validation

### Input Validation
- Sanitize user inputs to prevent injection attacks
- Validate coordinate ranges
- Check file paths for directory traversal

### API Key Management
- Support environment variables for API credentials
- Secure storage recommendations
- No hardcoded secrets

### Output Validation
- Verify AERMOD execution success
- Check for numerical anomalies
- Validate against physical constraints

## Deployment Options

### Local Installation
```bash
pip install pyaermod
# Installs Python package, user provides AERMOD binaries
```

### Docker Container
```dockerfile
FROM python:3.11
RUN apt-get update && apt-get install -y gfortran
COPY aermod-binaries/ /usr/local/bin/
RUN pip install pyaermod
```

### Cloud Deployment
- AWS Lambda for API endpoints (if execution time permits)
- EC2/GCE for long-running jobs
- Kubernetes for scalable batch processing

## Licensing & Compliance

### Wrapper License
- MIT or Apache 2.0 (permissive for commercial use)
- Clear attribution requirements

### AERMOD Binaries
- EPA public domain (no license restrictions)
- Include EPA's disclaimer
- Cite appropriate technical documentation

### Dependencies
- Verify all dependencies have compatible licenses
- Document any GPL dependencies (if used)

## Roadmap & Phasing

### Phase 1: MVP (Months 1-3)
- Core subprocess wrapper
- Basic input file generation
- Simple output parsing
- CLI tool
- Point and area sources
- Static visualization
- Documentation

### Phase 2: Data Integration (Months 4-6)
- NOAA meteorological data API
- USGS terrain data integration
- AERMET/AERMAP automation
- Interactive maps
- Basic web dashboard

### Phase 3: Advanced Features (Months 7-9)
- Volume and line sources
- Building downwash (BPIP integration)
- Sensitivity analysis tools
- Advanced visualization (3D, time-lapse)
- Automated report generation
- Performance optimization

### Phase 4: Enterprise Features (Months 10-12)
- Multi-user project management
- Version control integration
- Cloud deployment
- API authentication
- Database backend for results
- Advanced statistical analysis

## Success Metrics

### Technical Metrics
- 100% pass rate on EPA test cases
- <5% performance overhead vs. direct AERMOD execution
- Support for 95% of common use cases
- <100ms for input file generation
- <10s for result parsing (typical run)

### User Metrics
- Reduce modeling time by 50% vs. manual workflow
- Enable non-experts to run compliant models
- >80% user satisfaction score
- <2 hours to first successful model run (new users)

### Business Metrics
- Eliminate need for consulting fees for routine models
- Enable in-house regulatory compliance
- Reduce project turnaround time
- Lower barrier to entry for air quality modeling

## Risk Mitigation

### Regulatory Acceptance Risk
- **Mitigation**: Maintain exact AERMOD binary usage, provide validation documentation
- **Fallback**: Export inputs for verification in AERMOD View or other approved tools

### Fortran Dependency Risk
- **Mitigation**: Abstract execution layer to support multiple AERMOD versions
- **Fallback**: Document manual AERMOD execution procedures

### Data API Reliability Risk
- **Mitigation**: Implement caching, support offline mode with user-provided data
- **Fallback**: Detailed documentation for manual data preparation

### Maintenance Burden Risk
- **Mitigation**: Comprehensive test suite, modular architecture
- **Fallback**: Community contribution model, commercial support option

## Conclusion

This architecture provides a robust foundation for a Python wrapper around AERMOD that balances:
- **Accessibility**: Pythonic API, clear documentation
- **Regulatory Compliance**: Maintains EPA-certified calculations
- **Extensibility**: Modular design for future enhancements
- **Performance**: Efficient data handling and parallel execution
- **Practicality**: Focused on real-world use cases

The phased approach allows for incremental development while delivering value at each stage. The MVP focuses on core functionality to eliminate consulting dependencies, while later phases add sophisticated features for power users.

## References

- EPA AERMOD Implementation Guide
- AERMOD Model Formulation Document
- EPA SCRAM Website (Support Center for Regulatory Atmospheric Modeling)
- ISO 19115 (Geographic Information Metadata)
- CF Conventions (Climate and Forecast Metadata)
