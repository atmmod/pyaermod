"""Benchmark AERMOD output parsing speed."""
import tempfile
import time
from pathlib import Path

from pyaermod.output_parser import AERMODOutputParser


def _create_synthetic_output(num_receptors, num_periods=3):
    """Generate a minimal synthetic AERMOD .out file."""
    lines = []
    lines.append("                     *** AERMOD - VERSION 24142 ***")
    lines.append("")
    lines.append("                         *** MODEL SETUP OPTIONS ***")
    lines.append("")
    lines.append("   MODELOPT: CONC FLAT")
    lines.append(f"   Number of Receptor Locations:  {num_receptors}")
    lines.append("")
    lines.append("                      *** RECEPTOR SUMMARY ***")
    lines.append("")

    for i in range(num_receptors):
        x = 100.0 + i * 50.0
        y = 200.0
        lines.append(f"   {i+1:6d}  ({x:12.2f}, {y:12.2f})  ELEV = {0.0:8.2f}")

    lines.append("")
    lines.append("         *** THE SUMMARY OF MAXIMUM ANNUAL RESULTS ***")
    lines.append("")
    lines.append(f"{'RANK':>8}{'CONC':>12}{'X':>12}{'Y':>12}")

    for rank in range(1, min(num_receptors, 50) + 1):
        conc = 100.0 / rank
        x = 100.0 + rank * 50.0
        y = 200.0
        lines.append(f"{rank:8d}{conc:12.5f}{x:12.2f}{y:12.2f}")

    return "\n".join(lines)


def benchmark_output_parsing():
    receptor_counts = [100, 500, 1000, 5000]
    iterations = 10

    for n in receptor_counts:
        content = _create_synthetic_output(n)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".out", delete=False
        ) as f:
            f.write(content)
            path = f.name

        start = time.perf_counter()
        for _ in range(iterations):
            try:
                parser = AERMODOutputParser(path)
                parser.parse()
            except Exception:
                pass  # Synthetic output may not fully parse
        elapsed = time.perf_counter() - start

        ms_per_parse = elapsed / iterations * 1000
        print(f"  {n:5d} receptors: {ms_per_parse:8.2f} ms/parse")
        Path(path).unlink()


if __name__ == "__main__":
    print("=== AERMOD Output Parsing Benchmarks ===")
    benchmark_output_parsing()
