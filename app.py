"""Root-level Streamlit entry point."""

from pathlib import Path
import runpy
import sys

APP_DIRECTORY = Path(__file__).resolve().parent / "trip-planner"
sys.path.insert(0, str(APP_DIRECTORY))
runpy.run_path(str(APP_DIRECTORY / "app.py"), run_name="__main__")
