"""The oracles referee the engine, so they must not dispatch to it."""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import tests.support.oracles as oracles


def test_oracles_import_nothing_from_the_seam() -> None:
    for info in pkgutil.iter_modules(oracles.__path__, prefix=f"{oracles.__name__}."):
        module = importlib.import_module(info.name)
        source = inspect.getsource(module)
        assert "vfs.native" not in source and "_native" not in source, info.name
        bound = {name for name, value in vars(module).items() if getattr(value, "__module__", None) == "vfs.native"}
        assert not bound, (info.name, bound)
