"""pytest plugin: count first touches (mounts provisioned) and statements per test file across a run."""
from collections import Counter
import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

MOUNTS: Counter[str] = Counter()
STMTS: Counter[str] = Counter()
CURRENT = ["<none>"]

@event.listens_for(Engine, "before_cursor_execute")
def _count(conn, cursor, statement, parameters, context, executemany):
    STMTS[CURRENT[0]] += 1
    if statement.lstrip().upper().startswith("CREATE TABLE") and "vfs_meta" in statement:
        MOUNTS[CURRENT[0]] += 1

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    CURRENT[0] = item.nodeid.split("::")[0]
    yield

def pytest_sessionfinish(session, exitstatus):
    out = open("/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/347b653a-7845-4856-b8cd-ee69edeba111/scratchpad/rights/suite_counts.txt", "w")
    out.write(f"TOTAL mounts={sum(MOUNTS.values())} statements={sum(STMTS.values())}\n")
    for f in sorted(MOUNTS, key=lambda k: -MOUNTS[k]):
        out.write(f"{MOUNTS[f]:6d} mounts {STMTS[f]:8d} stmts  {f}\n")
    out.close()
