"""Entry point for PyInstaller and for running straight from a checkout:

    python launcher.py            (no install needed; any python that has the
                                   dependencies installed)

`python -m trendyreels` works too once the package is installed (pip install -e .).
"""

import os
import sys

# Running from a checkout: make src/ importable without installing.
_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from trendyreels.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
