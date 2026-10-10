"""Cache build_vfs_tables() so every mount shares one MetaData (measurement only)."""
import functools
from vfs.storage.backends.database import engine as engine_module
_orig = engine_module.build_vfs_tables
_cache = {}
def cached(*a, **k):
    key=(a, tuple(sorted(k.items())))
    if key not in _cache: _cache[key]=_orig(*a, **k)
    return _cache[key]
engine_module.build_vfs_tables = cached
