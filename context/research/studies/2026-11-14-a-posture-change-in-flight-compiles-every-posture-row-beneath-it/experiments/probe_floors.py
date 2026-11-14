"""Probe 5: every rights-bearing statement, compiled per profile, against the engine floors, as a caller's grants grow.

Pure compile (no server): for a caller holding G direct grants on sibling folders (and the
heavy shape: 50 groups with K grants each plus 100 direct), build its Rights with the resolver,
then per profile: the clause fan (no range source, and the scan tier everywhere), its packed
groups, the range-source derived table, the road's owner tests. Each statement is compiled on
its dialect and its binds counted with render_postcompile; SQLite statements are also executed
against an empty schema so SQLite's own parser judges the expression depth.
"""

from __future__ import annotations

import json
import math
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[5]))  # the repository root

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from vfs.models.rows import build_vfs_tables  # noqa: E402
from vfs.storage.backends.database.dialects import (  # noqa: E402
    EXPRESSION_DEPTH_RESERVE,
    GENERIC,
    PROFILES,
    membership_budget,
)
from vfs.storage.backends.database.ranges import hole_free, visible_entries  # noqa: E402
from vfs.storage.backends.database.rights import _OWNER_PIECES_PER_UNIT, visibility_clauses  # noqa: E402
from vfs.storage.backends.database.scope import _packed  # noqa: E402
from vfs.storage.grants import GrantRow, resolve  # noqa: E402

TABLES = build_vfs_tables()
ENTRY = TABLES.entry
DIALECTS = {
    "sqlite": sqlite.dialect(),
    "postgresql": postgresql.asyncpg.dialect(),
    "mssql": mssql.dialect(),
    "mariadb": mysql.dialect(),
    "oracle": oracle.dialect(),
    "generic": sqlite.dialect(),
}
CAPS = {"sqlite": 32_766, "postgresql": 32_767, "mssql": 2_100, "mariadb": 65_535, "oracle": 65_535, "generic": 1_000}
ENGINE = create_engine("sqlite://")
TABLES.metadata.create_all(ENGINE)


def binds(stmt, dialect) -> int:
    return len(stmt.compile(dialect=dialect, compile_kwargs={"render_postcompile": True}).positiontup or []) or len(
        stmt.compile(dialect=dialect, compile_kwargs={"render_postcompile": True}).params
    )


def bound_bytes(stmt, dialect) -> int:
    params = stmt.compile(dialect=dialect, compile_kwargs={"render_postcompile": True}).params
    total = 0
    for v in params.values():
        if isinstance(v, str):
            total += len(v.encode())
        elif isinstance(v, list):
            total += sum(len(x.encode()) for x in v if isinstance(x, str))
    return total


def sqlite_accepts(predicate) -> str:
    try:
        with ENGINE.connect() as conn:
            conn.execute(select(func.count()).select_from(ENTRY).where(predicate))
        return "ok"
    except OperationalError as exc:
        return str(exc.orig)[:60]


def rights_for(direct: int, groups: int = 0, per_group: int = 0, *, level: str = "read"):
    rows = [GrantRow("x", "/home/x", "read_write")]
    rows += [GrantRow("x", f"/p/{i:06}", level) for i in range(direct)]
    names = [f"group:g{g:02}" for g in range(groups)]
    for g, name in enumerate(names):
        rows += [GrantRow(name, f"/q/{g:02}/{k:05}", level) for k in range(per_group)]
    return resolve({"x": frozenset(names)}, rows, level)


def report(label: str, rights) -> None:
    r = rights.ranges()
    owner = sum(len(p.points) + len(p.opens) for _, p in r.owners)
    arms = len(r.arms.points) + len(r.arms.opens)
    print(f"== {label}: arm pieces={arms} owner pieces={owner} json≈{len(json.dumps([r.arms.points, r.arms.opens]))}B")
    for name, profile in [*PROFILES.items(), ("generic", GENERIC)]:
        dialect = DIALECTS[name]
        pb = dialect.insertmanyvalues_max_parameters
        clauses = visibility_clauses(ENTRY, rights, profile, pb) or []
        cmax = max((binds(select(ENTRY.c.id).where(c.predicate), dialect) for c in clauses), default=0)
        cap = min(pb // 2, profile.expression_depth_budget - EXPRESSION_DEPTH_RESERVE)
        groups = _packed(clauses, cap)
        gmax = max((binds(select(ENTRY.c.id).where(g.predicate), dialect) for g in groups), default=0)
        line = (
            f"  {name:10} fan clauses={len(clauses):4} max binds={cmax:5} | scan groups={len(groups):4} "
            f"max binds={gmax:5} (engine cap {CAPS[name]})"
        )
        if name in ("sqlite", "generic") and groups:
            line += f" sqlite-parse={sqlite_accepts(groups[0].predicate)}"
        if profile.range_source is not None and not rights.whole and not rights.empty:
            visible = visible_entries(ENTRY, r, rights.need, profile)
            stmt = select(func.count()).select_from(ENTRY.join(visible, visible.c.entry_id == ENTRY.c.entry_id))
            line += f" | range join binds={binds(stmt, dialect)} bound bytes={bound_bytes(stmt, dialect)}"
        per_chunk = max(1, membership_budget(profile, pb) - 3 - 2 * _OWNER_PIECES_PER_UNIT)
        line += f" | road owner tests={math.ceil(owner / _OWNER_PIECES_PER_UNIT)} per {per_chunk} candidates"
        print(line)


def holes_report(deeper: int) -> None:
    """A partial caller's compile while a posture over *deeper* narrower postures is being relabelled."""
    rows = [GrantRow("*", "/", "read"), GrantRow("x", "/home/x", "read_write")]
    rows += [GrantRow("*", f"/home/u{i:05}", "none") for i in range(deeper)]
    rights = resolve({"x": frozenset()}, rows, "read", pending=["/"])
    r = rights.ranges()
    print(f"== in flight at / over {deeper} deeper postures: hole pieces={len(r.holes.points) + len(r.holes.opens)} "
          f"spans={len(rights.spans)} whole={rights.whole}")
    rows[0] = GrantRow("*", "/", "list")
    rights = resolve({"x": frozenset()}, rows, "read", pending=["/"])
    r = rights.ranges()
    holes = len(r.holes.points) + len(r.holes.opens)
    print(f"   narrowing / to list: hole pieces={holes}")
    for name, profile in [*PROFILES.items(), ("generic", GENERIC)]:
        dialect = DIALECTS[name]
        pred = hole_free(ENTRY.c.path, r.holes, profile)
        stmt = select(ENTRY.c.id).where(pred)
        pb = dialect.insertmanyvalues_max_parameters
        clauses = visibility_clauses(ENTRY, rights, profile, pb) or []
        cap = min(pb // 2, profile.expression_depth_budget - EXPRESSION_DEPTH_RESERVE)
        groups = _packed(clauses, cap)
        line = f"  {name:10} road hole_free binds={binds(stmt, dialect):6} bytes={bound_bytes(stmt, dialect)}"
        line += f" | scan-tier statements per arm chunk={len(groups)} (fan clauses {len(clauses)})"
        if name in ("sqlite", "generic"):
            line += f" sqlite-parse={sqlite_accepts(pred)}"
        print(line)


def main() -> None:
    for g in (34, 100, 500, 1000, 5000, 20000):
        report(f"direct grants G={g}", rights_for(g))
    for k in (2, 20, 100):
        report(f"50 groups x {k} grants + 100 direct", rights_for(100, 50, k))
    for d in (100, 1000, 10000):
        holes_report(d)


main()
