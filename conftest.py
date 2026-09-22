"""Make the engine-contract package and each engine's own directory importable."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
# Engines import their sibling `engine` module directly.
for engine_dir in (ROOT / "engines").glob("*/server"):
    sys.path.insert(0, str(engine_dir))
