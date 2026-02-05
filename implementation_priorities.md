# PyAERMOD Implementation Priorities

## Analysis Based on AERMOD Source Code (Version 24142)

After reviewing the AERMOD Fortran source code, user guide, and quick reference guide, here are the components ranked by implementation ease and priority for the MVP.

## Immediate Priorities (Easiest → High Value)

### 1. **Input File Generation** ⭐ EASIEST & HIGHEST VALUE

**Why This First:**
- Clear, well-documented format from the source code
- All 120 keywords are defined in `modules.f` line 1545-1571
- Structured pathway system: CO (Control), SO (Source), RE (Receptor), ME (Meteorology), OU (Output)
- No complex parsing required - just string formatting
- Enables immediate productivity gains

**Keywords Identified from Source:**
```
Control Pathway (CO):
- STARTING, FINISHED, TITLEONE, TITLETWO
- MODELOPT, AVERTIME, POLLUTID, RUNORNOT
- ELEVUNIT, FLAGPOLE, URBANOPT
- LOW_WIND, OZONEVAL, NO2EQUIL, etc.

Source Pathway (SO):
- LOCATION, SRCPARAM (point sources)
- BUILDHGT, BUILDWID, BUILDLEN (building downwash)
- AREAVERT (area sources)
- EMISFACT, EMISUNIT, HOUREMIS
- SRCGROUP, URBANSRC, NO2RATIO

Receptor Pathway (RE):
- GRIDCART, GRIDPOLR
- DISCCART, DISCPOLR
- EVALCART

Meteorology Pathway (ME):
- SURFFILE, PROFFILE, SURFDATA, UAIRDATA
- STARTEND, DAYRANGE, WINDCATS

Output Pathway (OU):
- RECTABLE, MAXTABLE, DAYTABLE
- SUMMFILE, MAXIFILE, POSTFILE, PLOTFILE
```

**Implementation Approach:**
```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ControlPathway:
    title_one: str
    title_two: Optional[str] = None
    model_options: List[str] = None  # ['CONC', 'FLAT', 'DFAULT']
    averaging_periods: List[str] = None  # ['1', '24', 'ANNUAL']
    pollutant_id: str = 'OTHER'
    terrain_type: str = 'FLAT'

    def to_aermod_input(self) -> str:
        lines = ['CO STARTING']
        lines.append(f'   TITLEONE  {self.title_one}')
        if self.title_two:
            lines.append(f'   TITLETWO  {self.title_two}')

        modelopt = ' '.join(self.model_options or ['CONC', 'FLAT'])
        lines.append(f'   MODELOPT  {modelopt}')

        avertime = ' '.join(self.averaging_periods or ['ANNUAL'])
        lines.append(f'   AVERTIME  {avertime}')

        lines.append(f'   POLLUTID  {self.pollutant_id}')
        lines.append('   RUNORNOT  RUN')
        lines.append('CO FINISHED')
        return '\n'.join(lines)

@dataclass
class PointSource:
    source_id: str
    x_coord: float
    y_coord: float
    base_elevation: float
    stack_height: float
    stack_temp: float  # Kelvin
    exit_velocity: float  # m/s
    stack_diameter: float  # meters
    emission_rate: float  # g/s

    def to_aermod_input(self) -> str:
        lines = []
        # LOCATION keyword
        lines.append(f'   LOCATION  {self.source_id:<8} POINT  '
                    f'{self.x_coord:12.4f} {self.y_coord:12.4f} '
                    f'{self.base_elevation:8.2f}')

        # SRCPARAM keyword
        lines.append(f'   SRCPARAM  {self.source_id:<8} '
                    f'{self.emission_rate:10.6f} {self.stack_height:8.2f} '
                    f'{self.stack_temp:8.2f} {self.exit_velocity:8.2f} '
                    f'{self.stack_diameter:8.2f}')
        return '\n'.join(lines)

class AERMODInputWriter:
    def __init__(self):
        self.control = None
        self.sources = []
        self.receptors = None
        self.meteorology = None
        self.output = None

    def write(self, filename: str):
        with open(filename, 'w') as f:
            # Control Pathway
            f.write(self.control.to_aermod_input() + '\n\n')

            # Source Pathway
            f.write('SO STARTING\n')
            for source in self.sources:
                f.write(source.to_aermod_input() + '\n')
            f.write('SO FINISHED\n\n')

            # Receptor Pathway
            f.write(self.receptors.to_aermod_input() + '\n\n')

            # Meteorology Pathway
            f.write(self.meteorology.to_aermod_input() + '\n\n')

            # Output Pathway
            f.write(self.output.to_aermod_input() + '\n')
```

**Effort Estimate:** 2-3 days for basic implementation, 1 week with validation

---

### 2. **Output File Parsing** ⭐ SECOND EASIEST

**Why This Second:**
- Output format is consistent and well-structured
- Can validate input generation by parsing results
- Enables immediate feedback loop for testing
- Key to making the wrapper useful

**Output File Structure (from source analysis):**

The output file (`output.f` and `evoutput.f`) contains:
1. Header with run information
2. Source summaries
3. Receptor summaries
4. Results tables by averaging period
5. Maximum value tables

**Typical Output Format:**
```
*** AERMOD - VERSION  24142 ***

*** Jobname: Example_Run
    Run Date: 02-05-26
    Run Time: 10:30:00

**  Model Setup Options Selected **
                         CONC -- Concentration Calculation
                         FLAT -- Flat Terrain

** MODELING PERIOD **
   STARTING DATE: 01/01/23
   ENDING DATE:   12/31/23

*** RECEPTOR LOCATIONS ***
  X-COORD    Y-COORD    ZELEV    ZHILL    ZFLAG
  1000.00    1000.00     0.00     0.00     0.00
  ...

*** ANNUAL RESULTS ***
  X-COORD    Y-COORD    CONC (UG/M3)
  1000.00    1000.00      5.234
```

**Parser Implementation:**
```python
import re
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class AERMODResults:
    version: str
    jobname: str
    run_date: str
    model_options: List[str]
    averaging_periods: List[str]
    receptors: pd.DataFrame
    concentrations: Dict[str, pd.DataFrame]  # keyed by averaging period
    max_values: Dict[str, tuple]  # (x, y, value) by averaging period

    @classmethod
    def from_file(cls, output_file: str):
        """Parse AERMOD output file"""
        with open(output_file, 'r') as f:
            content = f.read()

        # Parse header
        version = re.search(r'AERMOD - VERSION\s+(\d+)', content).group(1)
        jobname = re.search(r'Jobname:\s+(.+)', content).group(1).strip()
        run_date = re.search(r'Run Date:\s+(.+)', content).group(1).strip()

        # Parse model options
        model_options = re.findall(r'^\s+(\w+)\s+--', content, re.MULTILINE)

        # Parse results tables
        concentrations = {}
        for period in ['ANNUAL', '24-HOUR', '1-HOUR']:
            conc_df = cls._parse_concentration_table(content, period)
            if conc_df is not None:
                concentrations[period] = conc_df

        # Parse maximum values
        max_values = cls._parse_max_values(content)

        return cls(
            version=version,
            jobname=jobname,
            run_date=run_date,
            model_options=model_options,
            averaging_periods=list(concentrations.keys()),
            receptors=None,  # Parsed separately
            concentrations=concentrations,
            max_values=max_values
        )

    @staticmethod
    def _parse_concentration_table(content: str, period: str) -> pd.DataFrame:
        """Extract concentration table for given averaging period"""
        # Find table section
        pattern = f'\*\*\* {period} RESULTS \*\*\*.*?\n(.*?)(?:\*\*\*|\Z)'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            return None

        table_text = match.group(1)

        # Parse table rows
        data = []
        for line in table_text.split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 3 and parts[0].replace('.','').replace('-','').isdigit():
                data.append({
                    'x': float(parts[0]),
                    'y': float(parts[1]),
                    'concentration': float(parts[2])
                })

        return pd.DataFrame(data)

    def to_dataframe(self, averaging_period: str = 'ANNUAL') -> pd.DataFrame:
        """Return concentrations as DataFrame"""
        return self.concentrations.get(averaging_period)

    def get_max_concentration(self, averaging_period: str = 'ANNUAL'):
        """Return maximum concentration and location"""
        df = self.concentrations.get(averaging_period)
        if df is None:
            return None

        max_idx = df['concentration'].idxmax()
        return {
            'x': df.loc[max_idx, 'x'],
            'y': df.loc[max_idx, 'y'],
            'concentration': df.loc[max_idx, 'concentration']
        }
```

**Effort Estimate:** 3-4 days with robust error handling

---

### 3. **Receptor Grid Generation** ⭐ MODERATE

**Why This Third:**
- Relatively straightforward geometric calculations
- Well-defined in AERMOD documentation
- Essential for any model run

**Receptor Types from Source Code:**
- `GRIDCART` - Cartesian grid
- `GRIDPOLR` - Polar grid
- `DISCCART` - Discrete Cartesian points
- `DISCPOLR` - Discrete polar points
- `EVALCART` - Evaluation points (for model evaluation)

**Implementation:**
```python
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class CartesianGrid:
    x_init: float
    x_num: int
    x_delta: float
    y_init: float
    y_num: int
    y_delta: float
    z_elev: float = 0.0
    z_hill: float = 0.0
    z_flag: float = 0.0

    def generate_points(self) -> np.ndarray:
        """Generate receptor grid points"""
        x = self.x_init + np.arange(self.x_num) * self.x_delta
        y = self.y_init + np.arange(self.y_num) * self.y_delta

        xx, yy = np.meshgrid(x, y)

        points = np.column_stack([
            xx.ravel(),
            yy.ravel(),
            np.full(xx.size, self.z_elev),
            np.full(xx.size, self.z_hill),
            np.full(xx.size, self.z_flag)
        ])

        return points

    def to_aermod_input(self) -> str:
        """Generate AERMOD input"""
        return (f'   GRIDCART  GRID1  XYINC  '
                f'{self.x_init:10.2f} {self.x_num:5d} {self.x_delta:8.2f}  '
                f'{self.y_init:10.2f} {self.y_num:5d} {self.y_delta:8.2f}')

@dataclass
class PolarGrid:
    x_origin: float
    y_origin: float
    distance_init: float
    distance_num: int
    distance_delta: float
    direction_init: float
    direction_num: int
    direction_delta: float
    z_elev: float = 0.0

    def generate_points(self) -> np.ndarray:
        """Generate polar grid points"""
        distances = self.distance_init + np.arange(self.distance_num) * self.distance_delta
        directions = self.direction_init + np.arange(self.direction_num) * self.direction_delta

        points = []
        for dist in distances:
            for dir_deg in directions:
                dir_rad = np.radians(dir_deg)
                x = self.x_origin + dist * np.sin(dir_rad)
                y = self.y_origin + dist * np.cos(dir_rad)
                points.append([x, y, self.z_elev, 0.0, 0.0])

        return np.array(points)

    def to_aermod_input(self) -> str:
        return (f'   GRIDPOLR  GRID1  ORIG  '
                f'{self.x_origin:10.2f} {self.y_origin:10.2f}\n'
                f'   GRIDPOLR  GRID1  DIST  '
                f'{self.distance_init:10.2f} {self.distance_num:5d} {self.distance_delta:8.2f}\n'
                f'   GRIDPOLR  GRID1  GDIR  '
                f'{self.direction_init:6.1f} {self.direction_num:5d} {self.direction_delta:6.1f}')

class ReceptorGrid:
    """Factory for creating different receptor types"""

    @staticmethod
    def cartesian(x_range: Tuple[float, float], y_range: Tuple[float, float],
                  spacing: float = 100.0) -> CartesianGrid:
        """Create Cartesian grid from bounds and spacing"""
        x_min, x_max = x_range
        y_min, y_max = y_range

        x_num = int((x_max - x_min) / spacing) + 1
        y_num = int((y_max - y_min) / spacing) + 1

        return CartesianGrid(
            x_init=x_min,
            x_num=x_num,
            x_delta=spacing,
            y_init=y_min,
            y_num=y_num,
            y_delta=spacing
        )

    @staticmethod
    def polar_rings(origin: Tuple[float, float],
                    radii: List[float],
                    num_directions: int = 36) -> PolarGrid:
        """Create polar grid with specified radii"""
        return PolarGrid(
            x_origin=origin[0],
            y_origin=origin[1],
            distance_init=radii[0],
            distance_num=len(radii),
            distance_delta=radii[1] - radii[0] if len(radii) > 1 else 100,
            direction_init=0.0,
            direction_num=num_directions,
            direction_delta=360.0 / num_directions
        )
```

**Effort Estimate:** 2-3 days

---

### 4. **Process Execution Wrapper** ⭐ EASY

**Why This Fourth:**
- Straightforward subprocess management
- Well-understood Python pattern
- Enables end-to-end testing

**Implementation:**
```python
import subprocess
import shutil
from pathlib import Path
from typing import Optional
import logging

class AERMODRunner:
    def __init__(self, executable_path: Optional[str] = None):
        """Initialize runner with AERMOD executable"""
        if executable_path:
            self.executable = Path(executable_path)
        else:
            self.executable = self._find_aermod_executable()

        if not self.executable or not self.executable.exists():
            raise FileNotFoundError(
                "AERMOD executable not found. Please specify path or "
                "add to system PATH"
            )

        self.logger = logging.getLogger(__name__)

    def _find_aermod_executable(self) -> Optional[Path]:
        """Search for AERMOD executable in system PATH"""
        # Windows
        aermod_exe = shutil.which('aermod.exe')
        if aermod_exe:
            return Path(aermod_exe)

        # Linux/Mac
        aermod_bin = shutil.which('aermod')
        if aermod_bin:
            return Path(aermod_bin)

        return None

    def run(self, input_file: str, working_dir: Optional[str] = None,
            timeout: int = 3600) -> dict:
        """
        Execute AERMOD with given input file

        Args:
            input_file: Path to AERMOD input file (.inp)
            working_dir: Directory to run AERMOD in
            timeout: Maximum execution time in seconds

        Returns:
            dict with status, stdout, stderr, output_files
        """
        input_path = Path(input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        if working_dir is None:
            working_dir = input_path.parent

        work_path = Path(working_dir)
        work_path.mkdir(parents=True, exist_ok=True)

        # AERMOD expects input file name without extension as argument
        input_name = input_path.stem

        self.logger.info(f"Running AERMOD with input: {input_file}")
        self.logger.debug(f"Executable: {self.executable}")
        self.logger.debug(f"Working directory: {working_dir}")

        try:
            result = subprocess.run(
                [str(self.executable), input_name],
                cwd=str(work_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )

            # Check for output files
            output_files = {
                'main': work_path / f"{input_name}.out",
                'error': work_path / f"{input_name}.err",
                'summary': work_path / f"{input_name}.sum"
            }

            # Determine success
            success = (
                result.returncode == 0 and
                output_files['main'].exists()
            )

            if not success:
                self.logger.error(f"AERMOD failed with return code: {result.returncode}")
                if result.stderr:
                    self.logger.error(f"STDERR: {result.stderr}")
            else:
                self.logger.info("AERMOD completed successfully")

            return {
                'success': success,
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'output_files': {k: str(v) for k, v in output_files.items()
                                if v.exists()}
            }

        except subprocess.TimeoutExpired:
            self.logger.error(f"AERMOD execution timed out after {timeout} seconds")
            return {
                'success': False,
                'error': 'timeout',
                'timeout': timeout
            }
        except Exception as e:
            self.logger.error(f"Error running AERMOD: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def run_batch(self, input_files: List[str], n_workers: int = 4) -> List[dict]:
        """Run multiple AERMOD scenarios in parallel"""
        from concurrent.futures import ProcessPoolExecutor, as_completed

        results = []
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(self.run, inp_file): inp_file
                for inp_file in input_files
            }

            for future in as_completed(futures):
                input_file = futures[future]
                try:
                    result = future.result()
                    result['input_file'] = input_file
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Failed to process {input_file}: {e}")
                    results.append({
                        'success': False,
                        'input_file': input_file,
                        'error': str(e)
                    })

        return results
```

**Effort Estimate:** 1-2 days

---

## Moderate Complexity (Week 2-3)

### 5. **Configuration Validation**

- Validate parameter ranges based on AERMOD requirements
- Check required vs. optional keywords
- Cross-validate related parameters
- Based on pathway status arrays (ICSTAT, ISSTAT, etc.) found in source

### 6. **Meteorological Data Integration**

- SURFFILE/PROFFILE parsing
- Connection to NOAA APIs
- AERMET wrapper for data preprocessing

### 7. **Basic Visualization**

- Matplotlib contour plots
- Source/receptor overlay maps
- Max concentration markers

---

## Advanced Features (Month 2+)

### 8. **Area and Volume Sources**

More complex geometry in `soset.f`:
- AREAVERT (area source vertices)
- AREACIRC (circular areas)
- VOLUME sources
- OPENPIT sources

### 9. **Building Downwash (PRIME)**

Complex calculations in `prime.f`:
- BUILDHGT, BUILDWID, BUILDLEN keywords
- Direction-dependent building dimensions
- PRIME algorithm integration

### 10. **Advanced Output Processing**

- POSTFILE format (detailed concentration fields)
- PLOTFILE format (for external plotting)
- TOXXFILE format (for toxic analyses)

---

## Recommended MVP Sequence

**Week 1: Core Input/Output**
1. Input file generation (day 1-3)
2. Output parsing (day 3-5)
3. Integration tests with EPA test cases (day 5-7)

**Week 2: Receptors & Execution**
1. Receptor grid generation (day 1-3)
2. Process wrapper (day 3-4)
3. End-to-end workflow (day 4-7)

**Week 3: Polish & Document**
1. Configuration validation (day 1-3)
2. Error handling improvements (day 3-5)
3. Documentation and examples (day 5-7)

---

## Key Files from Source Code Analysis

### Input Parsing Logic
- **`coset.f`** (7,676 lines) - Control pathway processing
- **`soset.f`** (8,578 lines) - Source pathway processing
- **`reset.f`** (2,524 lines) - Receptor pathway processing
- **`meset.f`** (2,514 lines) - Meteorology pathway processing
- **`ouset.f`** (4,019 lines) - Output pathway processing

### Data Structures
- **`modules.f`** (4,093 lines) - All global variables and arrays
  - Line 1545-1571: All 120 AERMOD keywords defined
  - Physical constants (G, VONKAR, etc.)
  - Array dimensions and status flags

### Calculations
- **`calc1.f`** (14,190 lines) - Primary dispersion calculations
- **`calc2.f`** (4,137 lines) - Secondary calculations
- **`prime.f`** (5,506 lines) - Building downwash

### Output Generation
- **`output.f`** (3,482 lines) - Standard output formatting
- **`evoutput.f`** - Event output formatting

---

## Testing Strategy with EPA Test Cases

AERMOD distribution includes test case inputs. We should:

1. **Parse EPA test inputs** - Validate our input parser
2. **Generate equivalent inputs** - Test our input writer
3. **Compare outputs** - Ensure numerical accuracy
4. **Document differences** - Any formatting variations

---

## Conclusion

**Start with Input Generation + Output Parsing** - These are the highest value, lowest complexity components. With just these two, you can:

1. Generate AERMOD input files from Python
2. Run existing AERMOD binary
3. Parse results back into Python/pandas
4. Eliminate 80% of manual AERMOD work

This gives immediate value while laying the foundation for more sophisticated features.

**Estimated Timeline to MVP:**
- **3 weeks** for core functionality (input/output/execution)
- **Additional 2-3 weeks** for polish, validation, and documentation
- **Total:** 5-6 weeks to production-ready MVP

The source code has given us a complete reference for all keywords, pathways, and data structures, making implementation much more straightforward than reverse-engineering from documentation alone.
