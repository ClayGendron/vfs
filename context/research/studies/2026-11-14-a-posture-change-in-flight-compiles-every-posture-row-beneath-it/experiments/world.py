"""Probe support: the I5 world, built fast, and a statement recorder.

Every probe that imports this module takes, as its first argument, the
directory its SQLite databases live in (DATA below); run it from the
repository root with `uv run python <probe> <data-dir> ...`.

World(N): root posture `read`; one private home per user at /home/<user>
(posture `none`, the user's own `read_write` row, two files the user owns);
100 shared folders /shared/sNNN (posture `none`, five files), each granting
`read` to three groups, `read_write` to one, `read` to ten random users;
50 groups, five per user. The named callers have the same rows at every N:
ann (ordinary, groups g00..g04), heavy (all 50 groups), granted (a direct
`read` row on all 100 folders), admin (`read_write` at /).
"""

from __future__ import annotations

import json
import pathlib
import random
import sys
from datetime import UTC, datetime

# The repository root: experiments/ <- study/ <- studies/ <- research/ <- context/ <- the root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5]))
DATA = sys.argv[1] if len(sys.argv) > 1 else "."

from sqlalchemy import event, insert  # noqa: E402

from tests.support.statements import is_statistics_statement  # noqa: E402
from vfs.authority import Authority, Principal  # noqa: E402
from vfs.models import Entry  # noqa: E402
from vfs.paths import Path  # noqa: E402
from vfs.storage.backends.database import DatabaseStorage  # noqa: E402

SYSTEM = Authority.system()
FOLDERS = 100
GROUPS = 50
PER_USER = 5
CALLERS = ("ann", "heavy", "granted", "admin")


def group(i: int) -> str:
    return f"group:g{i:02}"


def plan(n: int, seed: int = 7):
    """Grant rows, memberships, entries for an N-user world; the shares are drawn from a seed independent of N."""
    users = [f"u{i:05}" for i in range(n)]
    rows: list[tuple[str, str, str]] = []
    members: list[tuple[str, str]] = []
    entries: list[Entry] = []
    share_rng = random.Random(seed)
    for j in range(FOLDERS):
        share = f"/shared/s{j:03}"
        rows.append(("*", share, "none"))
        picked = share_rng.sample(range(GROUPS), 4)
        for g in picked[:3]:
            rows.append((group(g), share, "read"))
        rows.append((group(picked[3]), share, "read_write"))
        entries += [Entry(path=Path(f"{share}/f{k}.md"), content=f"share {j} file {k} needle") for k in range(5)]
    user_rng = random.Random(seed * 1000 + n)
    for j in range(FOLDERS):
        for u in user_rng.sample(users, min(10, n)):
            rows.append((u, f"/shared/s{j:03}", "read"))
    for u in [*users, *CALLERS]:
        home = f"/home/{u}"
        rows.append(("*", home, "none"))
        rows.append((u, home, "read_write"))
        entries += [Entry(path=Path(f"{home}/f{k}.md"), content=f"{u} note {k} needle", owner_id=u) for k in range(2)]
    for u in users:
        for g in user_rng.sample(range(GROUPS), PER_USER):
            members.append((u, group(g)))
    members += [("ann", group(g)) for g in range(PER_USER)]
    members += [("heavy", group(g)) for g in range(GROUPS)]
    rows += [("granted", f"/shared/s{j:03}", "read") for j in range(FOLDERS)]
    rows.append(("admin", "/", "read_write"))
    return rows, members, entries


async def build(url: str, n: int, seed: int = 7) -> DatabaseStorage:
    storage = DatabaseStorage(url=url, posture="read")
    assert (await storage.mkdir(path=Path("/home"), authority=SYSTEM)).success
    assert (await storage.mkdir(path=Path("/shared"), authority=SYSTEM)).success
    rows, members, entries = plan(n, seed)
    host = storage._host
    now = datetime.now(UTC)
    async with host.session_factory() as session, session.begin():
        grants = [
            {"principal_id": p, "path_prefix": prefix, "level": level, "granted_by": "system", "granted_at": now, "revision": 1}
            for p, prefix, level in rows
        ]
        for k in range(0, len(grants), 5000):
            await session.execute(insert(host.tables.grants), grants[k : k + 5000])
        ms = [{"principal_id": m, "group_id": g, "granted_by": "system", "granted_at": now} for m, g in members]
        for k in range(0, len(ms), 5000):
            await session.execute(insert(host.tables.memberships), ms[k : k + 5000])
    for k in range(0, len(entries), 10_000):
        written = await storage.write(entries=entries[k : k + 10_000], parents=True, authority=SYSTEM)
        assert written.success, written.errors[:3]
    return storage


def who(name: str) -> Authority:
    if name == "system":
        return SYSTEM
    if name == "anonymous":
        return Authority.anonymous()
    if name == "pair":
        return Authority.on_behalf_of({Principal("ann"), Principal("heavy")}, actor=Principal("agent", kind="service"))
    return Authority.of(Principal(name))


class Recorder:
    """Every verb statement the engine runs while armed: text, bind count, bound bytes."""

    def __init__(self, storage: DatabaseStorage) -> None:
        self.rows: list[tuple[str, int, int]] = []
        self.armed = False
        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", self._record)

    def _record(self, conn, cursor, statement, parameters, context, executemany) -> None:
        if not self.armed or is_statistics_statement(statement):
            return
        params = parameters if isinstance(parameters, (list, tuple)) else list((parameters or {}).values())
        if executemany:
            params = [p for row in params for p in (row if isinstance(row, (list, tuple)) else row.values())]
        size = sum(len(v.encode()) if isinstance(v, str) else len(v) if isinstance(v, bytes) else 0 for v in params)
        self.rows.append((statement, len(params), size))

    async def run(self, coro):
        self.rows = []
        self.armed = True
        try:
            result = await coro
        finally:
            self.armed = False
        return result, list(self.rows)


def biggest_bound(rows) -> int:
    return max((size for _, _, size in rows), default=0)


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True)
