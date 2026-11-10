"""PyInstaller entry script for the ``pyaermod-desktop`` bundle.

The bundle used to start from ``src/pyaermod/gui_v2/desktop.py`` itself.
Run as ``__main__`` that module's relative imports fail, so the frozen
app could not start; this launcher imports it as part of the package.

``freeze_support()`` must run before anything else. In a frozen app the
``multiprocessing`` helper processes (the resource tracker NiceGUI starts,
for one) are launched by re-running this executable; without the call each
helper starts the whole app again, which starts another helper, and the
chain outlives the window.
"""

import multiprocessing

multiprocessing.freeze_support()

from pyaermod.gui_v2.desktop import main  # noqa: E402

main()
