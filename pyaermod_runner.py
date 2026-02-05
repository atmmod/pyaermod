"""
PyAERMOD Runner

Executes AERMOD binaries from Python with error handling, progress monitoring,
and batch processing capabilities.
"""

import subprocess
import shutil
import logging
import time
from pathlib import Path
from typing import Optional, Union, List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import platform


@dataclass
class AERMODRunResult:
    """Result from an AERMOD execution"""
    success: bool
    input_file: str
    return_code: Optional[int] = None
    runtime_seconds: Optional[float] = None

    # Output files
    output_file: Optional[str] = None
    error_file: Optional[str] = None
    summary_file: Optional[str] = None

    # Execution info
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_message: Optional[str] = None

    # Metadata
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        runtime = f"{self.runtime_seconds:.1f}s" if self.runtime_seconds else "N/A"
        return f"AERMODRunResult({status}, {self.input_file}, runtime={runtime})"


class AERMODRunner:
    """
    Execute AERMOD simulations from Python

    Handles subprocess management, file I/O, error detection, and batch processing.
    """

    def __init__(self,
                 executable_path: Optional[Union[str, Path]] = None,
                 working_dir: Optional[Union[str, Path]] = None,
                 log_level: str = "INFO"):
        """
        Initialize AERMOD runner

        Args:
            executable_path: Path to AERMOD executable. If None, searches PATH.
            working_dir: Default working directory for runs
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        self.executable = self._find_or_set_executable(executable_path)
        self.default_working_dir = Path(working_dir) if working_dir else Path.cwd()

        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(getattr(logging, log_level.upper()))

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.logger.info(f"Initialized AERMOD runner with executable: {self.executable}")

    def _find_or_set_executable(self, path: Optional[Union[str, Path]]) -> Path:
        """Find or validate AERMOD executable"""
        if path:
            exe_path = Path(path)
            if not exe_path.exists():
                raise FileNotFoundError(f"AERMOD executable not found: {path}")
            return exe_path

        # Search in PATH
        system = platform.system()

        # Try common names
        exe_names = ['aermod', 'AERMOD', 'aermod.exe', 'AERMOD.EXE']

        for name in exe_names:
            found = shutil.which(name)
            if found:
                return Path(found)

        # If not found, provide helpful error message
        raise FileNotFoundError(
            "AERMOD executable not found in PATH. Please either:\n"
            "  1. Add AERMOD to your system PATH, or\n"
            "  2. Specify the path explicitly: AERMODRunner(executable_path='/path/to/aermod')\n\n"
            f"System: {system}"
        )

    def run(self,
            input_file: Union[str, Path],
            working_dir: Optional[Union[str, Path]] = None,
            timeout: int = 3600,
            capture_output: bool = True) -> AERMODRunResult:
        """
        Execute AERMOD with given input file

        Args:
            input_file: Path to AERMOD input file (.inp)
            working_dir: Working directory for execution (defaults to input file location)
            timeout: Maximum execution time in seconds (default 1 hour)
            capture_output: Whether to capture stdout/stderr

        Returns:
            AERMODRunResult with execution details and file paths
        """
        input_path = Path(input_file).resolve()

        if not input_path.exists():
            return AERMODRunResult(
                success=False,
                input_file=str(input_path),
                error_message=f"Input file not found: {input_path}"
            )

        # Determine working directory
        if working_dir:
            work_dir = Path(working_dir).resolve()
        else:
            work_dir = input_path.parent

        work_dir.mkdir(parents=True, exist_ok=True)

        # AERMOD expects input file name without extension
        input_name = input_path.stem

        self.logger.info(f"Running AERMOD: {input_name}")
        self.logger.debug(f"  Executable: {self.executable}")
        self.logger.debug(f"  Working dir: {work_dir}")
        self.logger.debug(f"  Timeout: {timeout}s")

        # Expected output files
        output_files = {
            'output': work_dir / f"{input_name}.out",
            'error': work_dir / f"{input_name}.err",
            'summary': work_dir / f"{input_name}.sum"
        }

        start_time = datetime.now()

        try:
            # Execute AERMOD
            result = subprocess.run(
                [str(self.executable), input_name],
                cwd=str(work_dir),
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                check=False
            )

            end_time = datetime.now()
            runtime = (end_time - start_time).total_seconds()

            self.logger.debug(f"AERMOD completed with return code: {result.returncode}")
            self.logger.debug(f"Runtime: {runtime:.2f}s")

            # Check for output files
            has_output = output_files['output'].exists()

            # Determine success
            # AERMOD typically returns 0 on success, but we also check for output file
            success = (result.returncode == 0 and has_output)

            if not success:
                error_msg = self._extract_error_message(result, output_files)
                self.logger.error(f"AERMOD run failed: {error_msg}")
            else:
                self.logger.info(f"AERMOD run succeeded ({runtime:.1f}s)")

            return AERMODRunResult(
                success=success,
                input_file=str(input_path),
                return_code=result.returncode,
                runtime_seconds=runtime,
                output_file=str(output_files['output']) if has_output else None,
                error_file=str(output_files['error']) if output_files['error'].exists() else None,
                summary_file=str(output_files['summary']) if output_files['summary'].exists() else None,
                stdout=result.stdout if capture_output else None,
                stderr=result.stderr if capture_output else None,
                error_message=error_msg if not success else None,
                start_time=start_time,
                end_time=end_time
            )

        except subprocess.TimeoutExpired:
            end_time = datetime.now()
            runtime = (end_time - start_time).total_seconds()

            self.logger.error(f"AERMOD execution timed out after {timeout}s")

            return AERMODRunResult(
                success=False,
                input_file=str(input_path),
                runtime_seconds=runtime,
                error_message=f"Execution timed out after {timeout} seconds",
                start_time=start_time,
                end_time=end_time
            )

        except Exception as e:
            end_time = datetime.now()
            runtime = (end_time - start_time).total_seconds()

            self.logger.error(f"Error running AERMOD: {e}")

            return AERMODRunResult(
                success=False,
                input_file=str(input_path),
                runtime_seconds=runtime,
                error_message=str(e),
                start_time=start_time,
                end_time=end_time
            )

    def _extract_error_message(self,
                               result: subprocess.CompletedProcess,
                               output_files: Dict[str, Path]) -> str:
        """Extract error message from AERMOD output"""
        messages = []

        # Check stderr
        if result.stderr:
            messages.append(f"stderr: {result.stderr[:500]}")

        # Check error file
        if output_files['error'].exists():
            try:
                with open(output_files['error'], 'r') as f:
                    error_content = f.read(1000)
                    if error_content.strip():
                        messages.append(f"Error file: {error_content[:500]}")
            except Exception:
                pass

        # Check output file for errors
        if output_files['output'].exists():
            try:
                with open(output_files['output'], 'r') as f:
                    content = f.read()
                    # Look for error indicators
                    if 'ERROR' in content or 'FATAL' in content:
                        # Extract relevant lines
                        for line in content.split('\n'):
                            if 'ERROR' in line or 'FATAL' in line:
                                messages.append(line.strip())
                                break
            except Exception:
                pass

        if messages:
            return "; ".join(messages)
        else:
            return f"AERMOD failed with return code {result.returncode}"

    def run_batch(self,
                  input_files: List[Union[str, Path]],
                  n_workers: int = 4,
                  timeout: int = 3600,
                  stop_on_error: bool = False) -> List[AERMODRunResult]:
        """
        Run multiple AERMOD simulations in parallel

        Args:
            input_files: List of input file paths
            n_workers: Number of parallel workers
            timeout: Timeout per run (seconds)
            stop_on_error: Whether to stop if any run fails

        Returns:
            List of AERMODRunResult objects
        """
        self.logger.info(f"Starting batch run: {len(input_files)} files, {n_workers} workers")

        results = []
        failed_count = 0

        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # Submit all jobs
            future_to_file = {
                executor.submit(self.run, inp, timeout=timeout): inp
                for inp in input_files
            }

            # Process completed jobs
            for future in as_completed(future_to_file):
                input_file = future_to_file[future]

                try:
                    result = future.result()
                    results.append(result)

                    if result.success:
                        self.logger.info(f"✓ {Path(result.input_file).name} ({result.runtime_seconds:.1f}s)")
                    else:
                        failed_count += 1
                        self.logger.error(f"✗ {Path(result.input_file).name}: {result.error_message}")

                        if stop_on_error:
                            self.logger.error("Stopping batch run due to error")
                            # Cancel pending futures
                            for f in future_to_file:
                                f.cancel()
                            break

                except Exception as e:
                    failed_count += 1
                    self.logger.error(f"✗ {input_file}: Exception: {e}")

                    results.append(AERMODRunResult(
                        success=False,
                        input_file=str(input_file),
                        error_message=str(e)
                    ))

                    if stop_on_error:
                        break

        success_count = len(results) - failed_count
        self.logger.info(
            f"Batch complete: {success_count}/{len(results)} succeeded, "
            f"{failed_count} failed"
        )

        return results

    def validate_input(self, input_file: Union[str, Path]) -> Tuple[bool, List[str]]:
        """
        Validate AERMOD input file (basic checks)

        Args:
            input_file: Path to input file

        Returns:
            (is_valid, list_of_issues)
        """
        issues = []
        input_path = Path(input_file)

        if not input_path.exists():
            return False, [f"Input file does not exist: {input_path}"]

        try:
            with open(input_path, 'r') as f:
                content = f.read()

            # Check for required pathways
            required_pathways = ['CO STARTING', 'SO STARTING', 'RE STARTING',
                               'ME STARTING', 'OU STARTING']

            for pathway in required_pathways:
                if pathway not in content:
                    issues.append(f"Missing required pathway: {pathway}")

            # Check for FINISHED statements
            for pathway in ['CO', 'SO', 'RE', 'ME', 'OU']:
                starting = f'{pathway} STARTING'
                finished = f'{pathway} FINISHED'

                if starting in content and finished not in content:
                    issues.append(f"Pathway {pathway} not properly closed (missing {finished})")

            # Check for RUNORNOT
            if 'RUNORNOT' not in content:
                issues.append("Missing RUNORNOT keyword (required in CO pathway)")

        except Exception as e:
            issues.append(f"Error reading file: {e}")

        return len(issues) == 0, issues


class BatchRunner:
    """
    Helper class for running parameter sweeps and scenario comparisons
    """

    def __init__(self, runner: AERMODRunner):
        """Initialize with an AERMODRunner instance"""
        self.runner = runner

    def parameter_sweep(self,
                       base_project,
                       parameter_name: str,
                       parameter_values: List,
                       output_dir: Union[str, Path],
                       n_workers: int = 4) -> Dict:
        """
        Run a parameter sweep

        Args:
            base_project: Base AERMODProject instance
            parameter_name: Name of parameter to sweep
            parameter_values: List of values to test
            output_dir: Directory for outputs
            n_workers: Number of parallel workers

        Returns:
            Dictionary mapping parameter values to results
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        input_files = []
        param_map = {}

        # Generate input files for each parameter value
        for value in parameter_values:
            # Create modified project
            # (This would need to be customized based on what parameter is being swept)
            filename = output_path / f"run_{parameter_name}_{value}.inp"

            # For now, this is a placeholder
            # In real use, you'd modify base_project and write
            input_files.append(filename)
            param_map[str(filename)] = value

        # Run batch
        results = self.runner.run_batch(input_files, n_workers=n_workers)

        # Map back to parameter values
        result_map = {}
        for result in results:
            param_value = param_map.get(result.input_file)
            if param_value is not None:
                result_map[param_value] = result

        return result_map


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def run_aermod(input_file: Union[str, Path],
               executable_path: Optional[Union[str, Path]] = None,
               timeout: int = 3600) -> AERMODRunResult:
    """
    Quick function to run AERMOD

    Args:
        input_file: Path to input file
        executable_path: Optional path to AERMOD executable
        timeout: Timeout in seconds

    Returns:
        AERMODRunResult
    """
    runner = AERMODRunner(executable_path=executable_path, log_level="WARNING")
    return runner.run(input_file, timeout=timeout)


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    # Example: Run AERMOD from command line
    if len(sys.argv) > 1:
        input_file = sys.argv[1]

        print(f"Running AERMOD with: {input_file}\n")

        # Initialize runner
        runner = AERMODRunner(log_level="INFO")

        # Validate input
        valid, issues = runner.validate_input(input_file)
        if not valid:
            print("Input validation failed:")
            for issue in issues:
                print(f"  - {issue}")
            sys.exit(1)

        print("Input validation passed\n")

        # Run AERMOD
        result = runner.run(input_file)

        # Display results
        print("\n" + "="*70)
        print("AERMOD Run Results")
        print("="*70)
        print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"Runtime: {result.runtime_seconds:.2f} seconds")

        if result.output_file:
            print(f"Output file: {result.output_file}")

        if result.error_message:
            print(f"Error: {result.error_message}")

        print("="*70)

        sys.exit(0 if result.success else 1)

    else:
        print("PyAERMOD Runner")
        print("\nUsage:")
        print("  python pyaermod_runner.py <input_file.inp>")
        print("\nOr import and use:")
        print("  from pyaermod_runner import AERMODRunner")
        print("  runner = AERMODRunner()")
        print("  result = runner.run('myfile.inp')")
        print("  if result.success:")
        print("      print('AERMOD run succeeded!')")
