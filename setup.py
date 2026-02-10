"""
Setup script for pyaermod
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read long description from README
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="pyaermod",
    version="0.2.0",
    author="Shannon Capps",
    author_email="shannon.capps@gmail.com",
    description="Python wrapper for EPA's AERMOD air dispersion model",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/atmmod/pyaermod",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Atmospheric Science",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "numpy>=1.20.0",
        "pandas>=1.3.0",
    ],
    extras_require={
        "viz": [
            "matplotlib>=3.3.0",
            "scipy>=1.7.0",
            "folium>=0.12.0",
        ],
        "geo": [
            "pyproj>=3.0.0",
            "geopandas>=0.10.0",
            "rasterio>=1.2.0",
            "shapely>=1.8.0",
            "scipy>=1.7.0",
        ],
        "gui": [
            "streamlit>=1.28.0",
            "streamlit-folium>=0.15.0",
            "folium>=0.14.0",
            "pyproj>=3.0.0",
            "geopandas>=0.10.0",
            "rasterio>=1.2.0",
            "shapely>=1.8.0",
            "scipy>=1.7.0",
            "matplotlib>=3.3.0",
        ],
        "terrain": [
            "requests>=2.25.0",
        ],
        "all": [
            "matplotlib>=3.3.0",
            "scipy>=1.7.0",
            "folium>=0.14.0",
            "pyproj>=3.0.0",
            "geopandas>=0.10.0",
            "rasterio>=1.2.0",
            "shapely>=1.8.0",
            "streamlit>=1.28.0",
            "streamlit-folium>=0.15.0",
            "requests>=2.25.0",
        ],
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.0",
            "black>=21.0",
            "flake8>=3.9",
        ],
    },
    entry_points={
        "console_scripts": [
            "pyaermod-gui=pyaermod.gui:main",
        ],
    },
    keywords="aermod air quality dispersion modeling atmospheric",
    project_urls={
        "Bug Reports": "https://github.com/atmmod/pyaermod/issues",
        "Source": "https://github.com/atmmod/pyaermod",
        "Documentation": "https://github.com/atmmod/pyaermod/blob/main/README.md",
    },
)
