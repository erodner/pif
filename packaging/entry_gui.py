"""PyInstaller entry point for the desktop app (windowed)."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from pif.gui.app import main

    sys.exit(main())
