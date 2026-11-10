# PyAERMOD Docker Image
#
# Serves the PyAERMOD GUI (the NiceGUI app, `pyaermod-app`) with all
# optional dependencies pre-installed, ready for one-command use:
#
#   docker build -t pyaermod .
#   docker run -p 127.0.0.1:8080:8080 pyaermod
#
# Then open http://localhost:8080 in your browser.
#
# The GUI reads and writes files and runs AERMOD for anyone who can reach
# it, so publish the port on 127.0.0.1 as above unless the network is
# trusted. The image has no AERMOD executable: mount one on the PATH, for
# example `-v /path/to/aermod:/usr/local/bin/aermod:ro`.

FROM python:3.11-slim-bookworm

LABEL maintainer="Shannon Capps"
LABEL description="PyAERMOD — Python wrapper for EPA's AERMOD with interactive GUI"

# System dependencies required by GDAL (geopandas, rasterio)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgdal-dev \
        gdal-bin \
        gcc \
        g++ \
        && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package files needed for install (setup.py reads README.md)
COPY setup.py pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir ".[all]"

# Copy remaining project files
COPY docs/ docs/
COPY examples/ examples/
COPY CHANGELOG.md LICENSE ./

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/')" || exit 1

# In a container the server listens on every interface (the published port
# reaches it from the host) and there is no browser to open.
CMD ["pyaermod-app", "--host", "0.0.0.0", "--port", "8080", "--no-browser"]
