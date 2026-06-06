#!/usr/bin/env python3
"""Entry point for the NFCorpus Retrieval Diagnostics Workbench."""

import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import Config
from backend.app import create_app

if __name__ == "__main__":
    Config.ensure_dirs()
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT)
