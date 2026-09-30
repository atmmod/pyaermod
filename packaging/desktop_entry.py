"""PyInstaller entry script for the ``pyaermod-desktop`` bundle.

The bundle used to start from ``src/pyaermod/gui_v2/desktop.py`` itself.
Run as ``__main__`` that module's relative imports fail, so the frozen
app could not start; this launcher imports it as part of the package.
"""

from pyaermod.gui_v2.desktop import main

main()
