"""Puts the handler packages on the path so the tests import exactly what ships."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for package in ("", "workflow-service"):
    sys.path.insert(0, str(ROOT / package) if package else str(ROOT))
sys.path.insert(0, str(ROOT / "workflow-service"))
