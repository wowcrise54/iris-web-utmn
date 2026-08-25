#!/usr/bin/env python3
"""
Pytest configuration and fixtures for OpenCTI module tests.
"""
import sys
import os
from pathlib import Path

# Add source directory to path for imports
source_path = Path(__file__).parent.parent.parent / "source"
if str(source_path) not in sys.path:
    sys.path.insert(0, str(source_path))
