"""Pytest bootstrap — ensure the backend dir (containing the arbicore package)
is importable when running the ArbiCore X test suite."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
