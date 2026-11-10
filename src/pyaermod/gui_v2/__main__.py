"""``python -m pyaermod.gui_v2``: the same as the ``pyaermod-app`` command.

For when the command is not on ``PATH`` (an environment that is not
activated, or a ``pip install --user`` whose scripts directory is not on
it) but its Python is at hand.
"""

from . import main

if __name__ == "__main__":
    main()
