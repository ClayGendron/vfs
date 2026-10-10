"""Scratch plugin: per-test verb sequence; everything before the last verb call counts as 'arrange'."""
import functools, time
from collections import defaultdict
import pytest
from vfs.storage.backends.database.backend import DatabaseStorage
from vfs.storage.backends.database import engine as engine_mod

VERBS = ["write","read","stat","ls","mkdir","delete","restore","move","copy","grep","glob","glean","reindex","tree","grant","grants","revoke","edges","rmedge","addedge","posture"]
CUR = {"seq": []}
TOUCH = {"t": 0.0}

def _wrap(v, fn):
    @functools.wraps(fn)
    async def inner(*a, **k):
        w0 = time.perf_counter(); t0 = TOUCH["t"]
        try:
            return await fn(*a, **k)
        finally:
            CUR["seq"].append((v, time.perf_counter() - w0 - (TOUCH["t"] - t0)))
    return inner

def _wrap_touch(fn):
    @functools.wraps(fn)
    async def inner(*a, **k):
        w0 = time.perf_counter()
        try:
            return await fn(*a, **k)
        finally:
            TOUCH["t"] += time.perf_counter() - w0
    return inner

def pytest_configure(config):
    engine_mod.EngineHost._first_touch = _wrap_touch(engine_mod.EngineHost._first_touch)
    for v in VERBS:
        if hasattr(DatabaseStorage, v):
            setattr(DatabaseStorage, v, _wrap(v, getattr(DatabaseStorage, v)))

TOT = defaultdict(float); N = {"tests": 0, "single": 0}
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    CUR["seq"] = []
    yield
    seq = CUR["seq"]
    N["tests"] += 1
    if not seq:
        return
    if len(seq) == 1:
        N["single"] += 1
    TOT["arrange"] += sum(d for _, d in seq[:-1])
    TOT["last verb"] += seq[-1][1]
    TOT["verbs per test"] += len(seq)

def pytest_terminal_summary(terminalreporter):
    tr = terminalreporter
    tr.write_sep("=", "verb sequence")
    tr.write_line(f"tests={N['tests']} single-verb tests={N['single']} first_touch total={TOUCH['t']:.2f}s")
    for k, v in TOT.items():
        tr.write_line(f"{k:16s} {v:8.2f}")
