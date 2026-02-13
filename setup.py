"""
Backward-compatible setup.py shim.

All package metadata is defined in pyproject.toml.
This file exists only for editable installs with older pip versions.
"""

from setuptools import setup

setup()
