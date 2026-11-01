"""Prepare public semantic model weights once; inference stays local."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trip-planner"))
from utils.providers.rag import prepare_model

if __name__ == "__main__":
    prepare_model()
    print("Local semantic model prepared.")
