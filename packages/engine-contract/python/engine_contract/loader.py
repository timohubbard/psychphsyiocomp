"""Load engine modules by engine_id, unambiguously.

Every engine's implementation is `engines/<engine_id>/server/engine.py`, which
is a good convention right up to the moment a second engine exists: putting
both directories on sys.path leaves two modules named `engine`, and `import
engine` then resolves to whichever was inserted last. That is not a theoretical
hazard — it broke the pipeline the first time a second engine was added, with
an ImportError that pointed at the wrong file entirely.

Loading by explicit path under a name derived from the engine_id removes the
ambiguity rather than managing it. Engine IDs contain dots, which are not legal
in module names, so they are flattened.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

#: Repo root, from this file's location inside packages/engine-contract/python/.
_ROOT = Path(__file__).resolve().parents[4]


def engines_dir() -> Path:
    return _ROOT / "engines"


def module_name_for(engine_id: str) -> str:
    return "engine_impl_" + engine_id.replace(".", "_").replace("-", "_")


def load_engine_module(engine_id: str, *, root: Path | None = None) -> ModuleType:
    """Import `engines/<engine_id>/server/engine.py` under a unique name.

    Cached in ``sys.modules`` like any import, so repeated calls are cheap and
    module-level state is shared — which matters because engines hold loaded
    model handles.
    """
    name = module_name_for(engine_id)
    if name in sys.modules:
        return sys.modules[name]

    base = (root or engines_dir()) / engine_id / "server" / "engine.py"
    if not base.exists():
        available = sorted(p.name for p in (root or engines_dir()).iterdir() if p.is_dir())
        raise ModuleNotFoundError(
            f"no engine implementation at {base}. Installed engines: {available}"
        )

    spec = importlib.util.spec_from_file_location(name, base)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build a module spec for {base}")

    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution so a module that imports itself, directly or
    # via a cycle, finds the partially-initialised module rather than re-running
    # it under a second identity.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def installed_engine_ids(root: Path | None = None) -> list[str]:
    """Engine IDs with both a manifest and a server implementation."""
    base = root or engines_dir()
    if not base.exists():
        return []
    return sorted(
        p.name for p in base.iterdir()
        if (p / "engine.manifest.json").exists() and (p / "server" / "engine.py").exists()
    )
