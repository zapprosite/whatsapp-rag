"""
conftest.py — pytest configuration for autonomous_refiner
"""
import sys
from pathlib import Path

# Ensure the project root is on the path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))