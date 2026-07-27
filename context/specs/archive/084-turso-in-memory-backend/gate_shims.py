"""Pytest plugin: temporary shims that make pyturso 0.7.1 loadable under
SQLAlchemy 2.0.46 — gate evidence only, never shipped.

Shim 1: has_stop, required by the aiosqlite base dialect's __init__.
Shim 2: isolation_level proxy on the generic adapted connection, required
by vfs's checkout listener (aiosqlite's own adapter provides this;
pyturso uses the generic adapter, which does not).
"""

from sqlalchemy.connectors.asyncio import AsyncAdapt_dbapi_connection
from turso.sqlalchemy.dialect import AsyncAdapt_turso_dbapi

if not hasattr(AsyncAdapt_turso_dbapi, "has_stop"):
    AsyncAdapt_turso_dbapi.has_stop = False


def _get_isolation(self):
    return self._connection.isolation_level


def _set_isolation(self, value):
    self._connection.isolation_level = value


if not hasattr(AsyncAdapt_dbapi_connection, "isolation_level"):
    AsyncAdapt_dbapi_connection.isolation_level = property(_get_isolation, _set_isolation)
