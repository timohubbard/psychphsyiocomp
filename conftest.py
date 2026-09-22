"""Make the engine-contract package importable, and nothing else ambiguous.

Engine implementations are deliberately NOT placed on sys.path. Every engine's
implementation is `engines/<engine_id>/server/engine.py`, so putting those
directories on the path leaves several modules named `engine` and `import
engine` resolves to whichever was inserted last. That is not hypothetical: it
silently imported the facial engine into the gaze engine's test module.

Tests load their engine through `engine_contract.loader.load_engine_module`,
which imports by explicit path under a name derived from the engine_id.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))
