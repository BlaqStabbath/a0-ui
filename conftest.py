"""Pytest config: ensure project root is on sys.path so 'a0_ui' is importable."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
