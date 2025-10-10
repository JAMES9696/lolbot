"""Pytest configuration and fixtures for 蔚-上城人 tests.

P5 Update: Ports unified into src/core/ports/ package.
No legacy import patching needed.
"""

import sys
from pathlib import Path

# Add project root to path for clean imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
