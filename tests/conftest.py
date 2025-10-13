"""Pytest configuration and fixtures for 蔚-上城人 tests.

P5 Update: Ports unified into src/core/ports/ package.
No legacy import patching needed.

NOTE: sys.path manipulation removed to prevent import conflicts.
Poetry + pyproject.toml's packages configuration ensures correct import resolution.
"""

import sys
from pathlib import Path

# Ensure project root is NOT in sys.path to avoid module shadowing
project_root = str(Path(__file__).parent.parent)
while project_root in sys.path:
    sys.path.remove(project_root)
while "." in sys.path:
    sys.path.remove(".")
while "" in sys.path:
    sys.path.remove("")
