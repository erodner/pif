"""PyInstaller entry point for the bundled command line tool `pif`."""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        from pif.runner import selftest

        sys.exit(selftest())
    from pif.cli import app

    app()
