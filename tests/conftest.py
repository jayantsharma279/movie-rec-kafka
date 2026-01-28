"""
Test environment setup script.

This file ensures that the repository root is included in Python's import path
so that all test modules can correctly import packages under the `scripts/`
directory (e.g., `from scripts.models import train_svd`).

Pytest automatically loads this file before running any tests, making
imports consistent across the suite without requiring relative paths.
"""

import sys
from pathlib import Path

# Resolve repository root (parent of the tests directory)
ROOT = Path(__file__).resolve().parents[1]

# Add repository root to sys.path to enable absolute imports
sys.path.insert(0, str(ROOT))
