"""Streamlit entry script for pyaermod GUI.

This file is executed by `streamlit run` from the `main()` entry point.
It exists because `streamlit run gui.py` treats gui.py as a standalone
script, which breaks relative imports.  This thin wrapper uses absolute
imports so the package resolves correctly.
"""

from pyaermod.gui import _app

_app()
