"""Benchmark POSTFILE parsing (text and binary formats)."""
import contextlib
import struct
import tempfile
import time
from pathlib import Path

from pyaermod.postfile import read_postfile


def _create_text_postfile(num_receptors, num_timesteps):
    """Generate a synthetic formatted (text) POSTFILE."""
    lines = []
    lines.append("* AERMOD POSTFILE")
    lines.append(f"* NUMREC = {num_receptors}")

    for t in range(num_timesteps):
        date = 24010101 + t
        for r in range(num_receptors):
            x = 100.0 + r * 50.0
            y = 200.0
            conc = 10.0 / (r + 1)
            lines.append(f" {date:>10d}  {x:12.2f}  {y:12.2f}  {conc:12.5f}  ALL")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pst", delete=False
    ) as f:
        f.write("\n".join(lines))
        return f.name


def _create_binary_postfile(num_receptors, num_timesteps):
    """Generate a synthetic unformatted (binary) POSTFILE."""
    with tempfile.NamedTemporaryFile(suffix=".pst", delete=False) as f:
        for t in range(num_timesteps):
            kurdat = 24010101 + t
            ianhrs = 1
            grpid = b"ALL     "
            vals = [10.0 / (r + 1) for r in range(num_receptors)]

            # Fortran unformatted record: marker + data + marker
            data = struct.pack("<i", kurdat)
            data += struct.pack("<i", ianhrs)
            data += grpid
            data += struct.pack(f"<{num_receptors}d", *vals)

            rec_len = len(data)
            f.write(struct.pack("<i", rec_len))
            f.write(data)
            f.write(struct.pack("<i", rec_len))

        return f.name


def benchmark_postfile_parsing():
    configs = [
        (50, 100),
        (100, 100),
        (200, 100),
        (50, 1000),
    ]

    for nrec, nts in configs:
        # Text format
        text_path = _create_text_postfile(nrec, nts)
        start = time.perf_counter()
        with contextlib.suppress(Exception):
            read_postfile(text_path)
        text_time = time.perf_counter() - start

        # Binary format
        bin_path = _create_binary_postfile(nrec, nts)
        start = time.perf_counter()
        with contextlib.suppress(Exception):
            read_postfile(bin_path)
        bin_time = time.perf_counter() - start

        ratio = text_time / bin_time if bin_time > 0 else float("inf")
        print(
            f"  {nrec:4d} rec x {nts:5d} ts: "
            f"text={text_time:.3f}s  binary={bin_time:.3f}s  ratio={ratio:.1f}x"
        )

        Path(text_path).unlink()
        Path(bin_path).unlink()


if __name__ == "__main__":
    print("=== POSTFILE Parsing Benchmarks ===")
    benchmark_postfile_parsing()
