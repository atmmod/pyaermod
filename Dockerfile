# PyAERMOD Docker Image
#
# Launches the PyAERMOD Streamlit GUI with all optional dependencies
# pre-installed, ready for one-command use:
#
#   docker build -t pyaermod .
#   docker run -p 8501:8501 pyaermod
#
# Then open http://localhost:8501 in your browser.

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

# Streamlit configuration: disable file watcher (not needed in container),
# bind to all interfaces, disable CORS for local development
RUN mkdir -p /root/.streamlit && \
    printf '[server]\nheadless = true\nport = 8501\naddress = "0.0.0.0"\nenableCORS = false\n\n[browser]\ngatherUsageStats = false\n' \
    > /root/.streamlit/config.toml

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["python", "-m", "streamlit", "run", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "/usr/local/lib/python3.11/site-packages/pyaermod/gui.py"]
