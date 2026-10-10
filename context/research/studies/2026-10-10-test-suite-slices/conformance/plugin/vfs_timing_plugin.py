"""Scratch pytest plugin: wall/CPU accumulators around the storage lifecycle, printed at session end."""
import functools, time
from collections import defaultdict
import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
STMT = {'total': 0, 'first_touch': 0, 'in_touch': 0}

@event.listens_for(Engine, 'before_cursor_execute')
def _count(conn, cursor, statement, parameters, context, executemany):
    STMT['total'] += 1
    if STMT['in_touch']:
        STMT['first_touch'] += 1
from sqlalchemy.sql.schema import MetaData
from vfs.storage.backends.database import engine as engine_mod
from vfs.storage.backends.database.backend import DatabaseStorage
from vfs.embedding import HashEmbeddingProvider

ACC = defaultdict(lambda: [0.0, 0.0, 0])

def _wrap_sync(label, fn):
    @functools.wraps(fn)
    def inner(*a, **k):
        w0 = time.perf_counter(); c0 = time.process_time()
        try:
            return fn(*a, **k)
        finally:
            ACC[label][0] += time.perf_counter() - w0; ACC[label][1] += time.process_time() - c0; ACC[label][2] += 1
    return inner

def _wrap_async(label, fn):
    @functools.wraps(fn)
    async def inner(*a, **k):
        w0 = time.perf_counter(); c0 = time.process_time()
        try:
            return await fn(*a, **k)
        finally:
            ACC[label][0] += time.perf_counter() - w0; ACC[label][1] += time.process_time() - c0; ACC[label][2] += 1
    return inner

VERBS = ["write","read","stat","ls","mkdir","delete","restore","move","copy","grep","glob","glean","reindex","tree","grant","grants","revoke","edges","rmedge","addedge","posture"]

def _wrap_touch(fn):
    @functools.wraps(fn)
    async def inner(*a, **k):
        STMT['in_touch'] += 1
        try:
            return await fn(*a, **k)
        finally:
            STMT['in_touch'] -= 1
    return inner

def pytest_configure(config):
    engine_mod.EngineHost._first_touch = _wrap_async("first_touch", _wrap_touch(engine_mod.EngineHost._first_touch))
    engine_mod.EngineHost._verify_or_provision = _wrap_async("  verify_or_provision", engine_mod.EngineHost._verify_or_provision)
    engine_mod.EngineHost._apply_file_settings = _wrap_async("  apply_file_settings", engine_mod.EngineHost._apply_file_settings)
    engine_mod.EngineHost._probe_sqlite_vec = _wrap_async("  probe_sqlite_vec", engine_mod.EngineHost._probe_sqlite_vec)
    engine_mod.EngineHost.close = _wrap_async("host.close", engine_mod.EngineHost.close)
    engine_mod.EngineHost.__init__ = _wrap_sync("EngineHost.__init__", engine_mod.EngineHost.__init__)
    MetaData.create_all = _wrap_sync("    create_all", MetaData.create_all)
    HashEmbeddingProvider.embed_documents = _wrap_async("hash embed_documents", HashEmbeddingProvider.embed_documents)
    for v in VERBS:
        if hasattr(DatabaseStorage, v):
            setattr(DatabaseStorage, v, _wrap_async(f"verb {v}", getattr(DatabaseStorage, v)))

PHASES = defaultdict(float)
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    w0 = time.perf_counter(); c0 = time.process_time()
    yield
    PHASES["protocol wall"] += time.perf_counter() - w0; PHASES["protocol cpu"] += time.process_time() - c0

def pytest_terminal_summary(terminalreporter):
    tr = terminalreporter
    tr.write_sep("=", "vfs timing plugin")
    tr.write_line(f"{'label':28s} {'calls':>7s} {'wall s':>8s} {'cpu s':>8s}")
    for label, (w, c, n) in ACC.items():
        tr.write_line(f"{label:28s} {n:7d} {w:8.2f} {c:8.2f}")
    tr.write_line(f"statements total={STMT['total']} in_first_touch={STMT['first_touch']}")
    for k, v in PHASES.items():
        tr.write_line(f"{k:28s} {'':7s} {v:8.2f}")
