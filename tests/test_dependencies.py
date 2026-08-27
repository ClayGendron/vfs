"""Import hygiene: the engine is Rust; no numeric library rides along."""

from __future__ import annotations

import subprocess
import sys

# A fresh interpreter: the suite's own imports (an extra's driver, a
# benchmark helper) must not vouch for or against the product.
_WALK = """
import importlib, pkgutil, sys, vfs
for info in pkgutil.walk_packages(vfs.__path__, prefix="vfs."):
    try:
        importlib.import_module(info.name)
    except ImportError:
        pass  # an optional extra's module without its driver installed
print(sorted(name for name in sys.modules if name == "numpy" or name.startswith("numpy.")))
"""


def test_importing_every_vfs_module_never_loads_numpy() -> None:
    run = subprocess.run([sys.executable, "-c", _WALK], capture_output=True, text=True, check=True)
    assert run.stdout.strip() == "[]", run.stdout
