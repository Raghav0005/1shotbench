"""WSGI entry point for gunicorn."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import create_app

application = create_app()
