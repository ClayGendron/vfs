#!/usr/bin/env python3
# ruff: noqa: E402, T201
"""Probe an existing Postgres-backed repo snapshot through ``VFSClient.cli``.

Usage:
    uv run python scripts/postgres_repo_cli_probe.py
    uv run python scripts/postgres_repo_cli_probe.py --strict-perf
    ./scripts/postgres_repo_cli_probe.sh --keep-scratch

The script assumes the repository content is already loaded into a
PostgreSQL database compatible with ``PostgresFileSystem``. It mounts that
database at ``/repo`` by default, then drives correctness, edge-case, and
performance probes through the public CLI query surface.

When the corpus already contains native pgvector embeddings, the script also
executes a direct vector-search smoke check through the public client API.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vfs.backends.postgres import PostgresFileSystem, _parse_vector_dimension
from vfs.client import VFSClient
from vfs.exceptions import NotFoundError, VFSError, WriteConflictError
from vfs.models import postgres_native_vfs_object_model
from vfs.query import QuerySyntaxError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


DEFAULT_DB_URL = os.environ.get("VFS_REPO_DB_URL", "postgresql+asyncpg://localhost/vfs_repo_case")
DEFAULT_MOUNT = os.environ.get("VFS_REPO_MOUNT", "repo")

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass(frozen=True)
class ProbeRecord:
    label: str
    status: str
    query: str | None
    duration_ms: float | None
    detail: str


@dataclass(frozen=True)
class PerfTarget:
    label: str
    query: str
    soft_budget_ms: float


def _quote(value: str) -> str:
    """Return *value* as a query-safe double-quoted string token.

    Keep literal newlines intact so the CLI parser receives multi-line
    content as actual text rather than the two-character sequence ``\n``.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _normalize_mount(value: str) -> str:
    mount = value.strip("/")
    if not mount or "/" in mount:
        raise ValueError(f"Mount must be a single path segment, got {value!r}")
    return mount


def _mount_path(mount: str, relative_path: str) -> str:
    rel = relative_path.lstrip("/")
    return f"/{mount}" if not rel else f"/{mount}/{rel}"


def _format_duration(duration_ms: float | None) -> str:
    return "--" if duration_ms is None else f"{duration_ms:8.1f} ms"


def _banner(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


def _parse_vector_literal(value: str) -> list[float]:
    return [float(part) for part in value.strip("[]").split(",") if part]


class ProbeRunner:
    def __init__(
        self,
        *,
        client: VFSClient,
        repo_root: Path,
        mount: str,
        scratch_root: str,
        scratch_disk_root: Path,
    ) -> None:
        self.client = client
        self.repo_root = repo_root
        self.mount = mount
        self.mount_root = f"/{mount}"
        self.scratch_root = scratch_root
        self.scratch_relative_root = scratch_root.removeprefix(self.mount_root).lstrip("/")
        self.scratch_disk_root = scratch_disk_root
        self.records: list[ProbeRecord] = []

    @property
    def failure_count(self) -> int:
        return sum(record.status == "FAIL" for record in self.records)

    @property
    def warning_count(self) -> int:
        return sum(record.status == "WARN" for record in self.records)

    def _record(
        self,
        *,
        label: str,
        status: str,
        detail: str,
        query: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        self.records.append(
            ProbeRecord(
                label=label,
                status=status,
                query=query,
                duration_ms=duration_ms,
                detail=detail,
            )
        )
        color = GREEN if status == "PASS" else RED if status == "FAIL" else YELLOW
        print(f"{color}{BOLD}{status:<4}{RESET} {_format_duration(duration_ms)}  {label}")
        if detail:
            print(f"      {detail}")
        if query:
            print(f"      query: {query}")

    def _run_cli(self, query: str) -> tuple[str, float]:
        started = time.perf_counter()
        rendered = self.client.cli(query)
        duration_ms = (time.perf_counter() - started) * 1000.0
        return rendered, duration_ms

    def scratch_path(self, relative_path: str) -> str:
        return _mount_path(self.mount, f"{self.scratch_relative_root}/{relative_path.lstrip('/')}")

    def custom_check(self, label: str, func: Callable[[], str]) -> None:
        started = time.perf_counter()
        try:
            detail = func()
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self._record(label=label, status="FAIL", detail=str(exc), duration_ms=duration_ms)
            return
        duration_ms = (time.perf_counter() - started) * 1000.0
        self._record(label=label, status="PASS", detail=detail, duration_ms=duration_ms)

    def expect_exact(self, label: str, query: str, expected: str) -> None:
        try:
            rendered, duration_ms = self._run_cli(query)
            if rendered != expected:
                msg = f"Expected exact output {expected!r}, got {rendered!r}"
                raise AssertionError(msg)
        except Exception as exc:
            self._record(label=label, status="FAIL", detail=str(exc), query=query)
            return
        self._record(
            label=label,
            status="PASS",
            detail=f"{len(rendered)} rendered bytes",
            query=query,
            duration_ms=duration_ms,
        )

    def expect_nonempty(self, label: str, query: str) -> str:
        try:
            rendered, duration_ms = self._run_cli(query)
            if not rendered.strip():
                raise AssertionError("Expected non-empty CLI output")
        except Exception as exc:
            self._record(label=label, status="FAIL", detail=str(exc), query=query)
            return ""
        self._record(
            label=label,
            status="PASS",
            detail=f"{len(rendered.splitlines())} output lines",
            query=query,
            duration_ms=duration_ms,
        )
        return rendered

    def expect_contains(
        self,
        label: str,
        query: str,
        *,
        must_contain: Sequence[str] = (),
        must_not_contain: Sequence[str] = (),
    ) -> str:
        try:
            rendered, duration_ms = self._run_cli(query)
            for token in must_contain:
                if token not in rendered:
                    raise AssertionError(f"Missing expected token {token!r}")
            for token in must_not_contain:
                if token in rendered:
                    raise AssertionError(f"Unexpected token present {token!r}")
        except Exception as exc:
            self._record(label=label, status="FAIL", detail=str(exc), query=query)
            return ""
        self._record(
            label=label,
            status="PASS",
            detail=f"{len(rendered)} rendered bytes",
            query=query,
            duration_ms=duration_ms,
        )
        return rendered

    def expect_empty(self, label: str, query: str) -> None:
        try:
            rendered, duration_ms = self._run_cli(query)
            if rendered != "":
                raise AssertionError(f"Expected empty output, got {rendered!r}")
        except Exception as exc:
            self._record(label=label, status="FAIL", detail=str(exc), query=query)
            return
        self._record(
            label=label,
            status="PASS",
            detail="empty output as expected",
            query=query,
            duration_ms=duration_ms,
        )

    def expect_raises(
        self,
        label: str,
        query: str,
        *,
        exc_type: type[BaseException],
        contains: str | None = None,
    ) -> None:
        started = time.perf_counter()
        try:
            self.client.cli(query)
        except exc_type as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            if contains is not None and contains not in str(exc):
                self._record(
                    label=label,
                    status="FAIL",
                    detail=f"Raised {type(exc).__name__}, but message did not contain {contains!r}: {exc}",
                    query=query,
                    duration_ms=duration_ms,
                )
                return
            self._record(
                label=label,
                status="PASS",
                detail=f"raised {type(exc).__name__}: {exc}",
                query=query,
                duration_ms=duration_ms,
            )
            return
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self._record(
                label=label,
                status="FAIL",
                detail=f"Raised {type(exc).__name__}, expected {exc_type.__name__}: {exc}",
                query=query,
                duration_ms=duration_ms,
            )
            return

        duration_ms = (time.perf_counter() - started) * 1000.0
        self._record(
            label=label,
            status="FAIL",
            detail=f"Expected {exc_type.__name__}, but query succeeded",
            query=query,
            duration_ms=duration_ms,
        )

    def perf_check(self, target: PerfTarget, *, strict: bool) -> None:
        try:
            rendered, duration_ms = self._run_cli(target.query)
            if not rendered.strip():
                raise AssertionError("Expected non-empty output from performance probe")
        except Exception as exc:
            self._record(label=target.label, status="FAIL", detail=str(exc), query=target.query)
            return

        detail = (
            f"{len(rendered)} rendered bytes, {len(rendered.splitlines())} output lines, "
            f"soft budget {target.soft_budget_ms:.0f} ms"
        )
        if duration_ms > target.soft_budget_ms:
            status = "FAIL" if strict else "WARN"
            detail = detail + f"; over budget by {duration_ms - target.soft_budget_ms:.1f} ms"
        else:
            status = "PASS"
        self._record(label=target.label, status=status, detail=detail, query=target.query, duration_ms=duration_ms)

    def print_summary(self) -> None:
        _banner("Summary")
        passed = sum(record.status == "PASS" for record in self.records)
        failed = self.failure_count
        warned = self.warning_count
        print(f"Passed:  {passed}")
        print(f"Failed:  {failed}")
        print(f"Warnings:{warned}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe an existing repo snapshot in Postgres through VFSClient.cli().")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="Async SQLAlchemy URL for the loaded PostgreSQL DB.")
    parser.add_argument("--mount", default=DEFAULT_MOUNT, help="Single mount segment to expose the DB at.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Local repo root used only for disk-vs-DB safety checks.",
    )
    parser.add_argument(
        "--read-path",
        default="README.md",
        help="Repo-relative path expected to exist both on disk and in the mounted DB snapshot.",
    )
    parser.add_argument(
        "--scratch-prefix",
        default="__db_probe__",
        help="Repo-relative prefix for DB-only scratch paths.",
    )
    parser.add_argument(
        "--skip-perf",
        action="store_true",
        help="Run correctness and edge-case probes only.",
    )
    parser.add_argument(
        "--strict-perf",
        action="store_true",
        help="Turn soft performance budget overruns into failures.",
    )
    parser.add_argument(
        "--keep-scratch",
        action="store_true",
        help="Leave scratch files in the database after the probe finishes.",
    )
    parser.add_argument(
        "--perf-max-count",
        type=int,
        default=250,
        help="Max result fanout for expensive CLI probes.",
    )
    parser.add_argument(
        "--perf-budget-ms",
        type=float,
        default=1500.0,
        help="Base soft budget for performance probes.",
    )
    parser.add_argument(
        "--tree-depth",
        type=int,
        default=4,
        help="Depth to use for tree probes.",
    )
    return parser


def open_client(db_url: str, mount: str) -> VFSClient:
    client = VFSClient()

    async def _build_filesystem() -> tuple[PostgresFileSystem, tuple[str, list[float]] | None]:
        engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
        async with engine.connect() as conn:
            type_row = (
                await conn.execute(
                    sql_text(
                        """
                        SELECT format_type(a.atttypid, a.atttypmod)
                        FROM pg_attribute AS a
                        JOIN pg_class AS c ON c.oid = a.attrelid
                        WHERE c.relname = 'vfs_objects'
                          AND a.attname = 'embedding'
                          AND NOT a.attisdropped
                        """
                    )
                )
            ).first()
            native_dimension = _parse_vector_dimension(type_row[0]) if type_row is not None else None

            native_vector_sample: tuple[str, list[float]] | None = None
            if native_dimension is not None:
                sample_row = (
                    await conn.execute(
                        sql_text(
                            """
                            SELECT path, embedding::text
                            FROM vfs_objects
                            WHERE embedding IS NOT NULL
                            LIMIT 1
                            """
                        )
                    )
                ).first()
                if sample_row is not None:
                    native_vector_sample = (sample_row[0], _parse_vector_literal(sample_row[1]))

        filesystem = (
            PostgresFileSystem(engine=engine, model=postgres_native_vfs_object_model(dimension=native_dimension))
            if native_dimension is not None
            else PostgresFileSystem(engine=engine)
        )
        async with filesystem._use_session() as session:
            await filesystem._verify_fulltext_schema(session)
            await filesystem._verify_pattern_schema(session)
        return filesystem, native_vector_sample

    filesystem, native_vector_sample = client._run(_build_filesystem())
    client.add_mount(mount, filesystem)
    client._native_vector_sample = native_vector_sample  # type: ignore[attr-defined]
    return client


def run_correctness_suite(
    runner: ProbeRunner,
    *,
    read_path: str,
) -> None:
    _banner("Correctness")

    notes_path = runner.scratch_path("notes.md")
    percent_path = runner.scratch_path("100%/report.txt")
    secret_path = runner.scratch_path("100_items/secret.txt")
    underscore_path = runner.scratch_path("a_/f.py")
    bystander_path = runner.scratch_path("ab/g.py")

    disk_read_path = runner.repo_root / read_path
    if not disk_read_path.exists():
        raise FileNotFoundError(f"Disk path not found for read probe: {disk_read_path}")
    read_expected = disk_read_path.read_text(encoding="utf-8")

    runner.expect_nonempty(
        "mounted repo snapshot is non-empty",
        f"glob {_quote(f'{runner.mount_root}/**/*')} --max-count 3",
    )
    runner.expect_contains(
        "root listing exposes expected top-level directories",
        f"ls {runner.mount_root}",
        must_contain=(f"{runner.mount_root}/src", f"{runner.mount_root}/tests"),
    )
    runner.expect_contains(
        "stat works on a real repo file",
        f"stat {_mount_path(runner.mount, read_path)} --output path,kind,size_bytes",
        must_contain=(_mount_path(runner.mount, read_path), "file"),
    )
    runner.expect_exact(
        "read matches the on-disk repo file",
        f"read {_mount_path(runner.mount, read_path)}",
        read_expected,
    )

    initial_notes = 'alpha first\nalpha second\nALPHA third\nbeta_beta token\n100% literal\nquoted "value"\n'
    after_unique_edit = initial_notes.replace("alpha first", "omega first")
    after_all_edit = after_unique_edit.replace("alpha", "omega")

    runner.custom_check(
        "scratch path does not exist on disk before DB-only writes",
        lambda: (
            "confirmed absent"
            if not runner.scratch_disk_root.exists()
            else (_raise(RuntimeError(f"Scratch disk path already exists: {runner.scratch_disk_root}")))
        ),
    )
    runner.expect_exact(
        "write creates a DB-only scratch file",
        f"write {notes_path} {_quote(initial_notes)}",
        f"Wrote {notes_path}",
    )
    runner.expect_exact("read returns scratch content verbatim", f"read {notes_path}", initial_notes)
    runner.custom_check(
        "write did not create a real repo file",
        lambda: (
            "still absent on disk"
            if not runner.scratch_disk_root.exists()
            else (_raise(RuntimeError(f"Unexpected disk mutation under {runner.scratch_disk_root}")))
        ),
    )
    runner.expect_raises(
        "write --no-overwrite rejects duplicates",
        f"write {notes_path} {_quote('should fail')} --no-overwrite",
        exc_type=WriteConflictError,
        contains="overwrite=False",
    )
    runner.expect_raises(
        "edit rejects ambiguous repeated matches without more context",
        f"edit {notes_path} {_quote('alpha')} {_quote('omega')}",
        exc_type=VFSError,
        contains="Found 2 matches",
    )
    runner.expect_exact(
        "edit succeeds when the old string is unique",
        f"edit {notes_path} {_quote('alpha first')} {_quote('omega first')}",
        f"Edited {notes_path}",
    )
    runner.expect_exact("post-edit read shows the unique replacement", f"read {notes_path}", after_unique_edit)
    runner.expect_exact(
        "edit --all replaces the remaining lowercase match",
        f"edit {notes_path} {_quote('alpha')} {_quote('omega')} --all",
        f"Edited {notes_path}",
    )
    runner.expect_exact("post-edit read shows replace-all result", f"read {notes_path}", after_all_edit)

    runner.expect_contains(
        "grep finds only the edited lowercase lines",
        f"grep {_quote('omega')} {notes_path}",
        must_contain=(f"{notes_path}:1:omega first", f"{notes_path}:2:omega second"),
        must_not_contain=("ALPHA third",),
    )
    runner.expect_contains(
        "grep --count surfaces line counts through --output",
        f"grep {_quote('omega|ALPHA')} {notes_path} --ignore-case --count --output path,score",
        must_contain=(notes_path, "3.0"),
    )
    runner.expect_contains(
        "grep fixed-strings matches literal percent signs",
        f"grep {_quote('100%')} {notes_path} --fixed-strings",
        must_contain=("100% literal",),
    )
    runner.expect_empty(
        "grep --word-regexp does not treat beta_beta as bare beta",
        f"grep {_quote('beta')} {notes_path} --word-regexp",
    )
    runner.expect_contains(
        "grep fixed-strings still finds beta_beta",
        f"grep {_quote('beta_beta')} {notes_path} --fixed-strings",
        must_contain=("beta_beta token",),
    )
    runner.expect_contains(
        "anchored grep still matches non-first lines",
        f"grep {_quote('^omega')} {notes_path}",
        must_contain=(f"{notes_path}:2:omega second",),
        must_not_contain=(f"{notes_path}:1:omega first",),
    )

    runner.expect_exact(
        "write percent-escaped path",
        f"write {percent_path} {_quote('percent target')}",
        f"Wrote {percent_path}",
    )
    runner.expect_exact(
        "write sibling percent path",
        f"write {secret_path} {_quote('keep out')}",
        f"Wrote {secret_path}",
    )
    runner.expect_exact(
        "write underscore-escaped path",
        f"write {underscore_path} {_quote('underscore target')}",
        f"Wrote {underscore_path}",
    )
    runner.expect_exact(
        "write bystander underscore path",
        f"write {bystander_path} {_quote('bystander')}",
        f"Wrote {bystander_path}",
    )
    runner.expect_contains(
        "tree renders the scratch hierarchy",
        f"tree {runner.scratch_root} --depth 4",
        must_contain=("notes.md", "100%", "100_items", "a_", "ab"),
    )
    runner.expect_contains(
        "glob escapes percent correctly",
        f"glob {_quote(f'{runner.scratch_root}/100%/*.txt')}",
        must_contain=(percent_path,),
        must_not_contain=(secret_path,),
    )
    runner.expect_contains(
        "glob escapes underscore correctly",
        f"glob {_quote(f'{runner.scratch_root}/a_/*.py')}",
        must_contain=(underscore_path,),
        must_not_contain=(bystander_path,),
    )
    runner.expect_contains(
        "glob character classes stay correct",
        f"glob {_quote(f'{runner.scratch_root}/[a][_]/*.py')}",
        must_contain=(underscore_path,),
        must_not_contain=(bystander_path,),
    )
    runner.expect_exact(
        "chain glob | grep | read resolves a single DB-only file",
        f"glob {_quote(f'{runner.scratch_root}/100%/*.txt')} | grep {_quote('percent target')} | read",
        "percent target",
    )
    runner.expect_contains(
        "chain against the loaded repo finds and reads real content",
        f"glob {_quote(f'{runner.mount_root}/src/**/*.py')} | grep {_quote('class VFSClient')} | read",
        must_contain=("class VFSClient",),
    )
    runner.custom_check(
        "scratch path is still absent on disk after all DB mutations",
        lambda: (
            "disk remained untouched"
            if not runner.scratch_disk_root.exists()
            else (_raise(RuntimeError(f"Unexpected disk mutation under {runner.scratch_disk_root}")))
        ),
    )


def run_negative_suite(runner: ProbeRunner) -> None:
    _banner("Negative Cases")

    missing_path = runner.scratch_path("missing.txt")
    existing_notes = runner.scratch_path("notes.md")

    runner.expect_raises(
        "read missing path raises NotFoundError",
        f"read {missing_path}",
        exc_type=NotFoundError,
        contains="Not found",
    )
    runner.expect_raises(
        "edit missing path raises NotFoundError",
        f"edit {missing_path} {_quote('x')} {_quote('y')}",
        exc_type=NotFoundError,
        contains="Not found",
    )
    runner.expect_raises(
        "parser rejects malformed write syntax",
        f"write {existing_notes}",
        exc_type=QuerySyntaxError,
        contains="write requires a path and content string",
    )
    runner.expect_raises(
        "parser rejects conflicting grep case flags",
        f"grep {_quote('omega')} {existing_notes} --ignore-case --case-sensitive",
        exc_type=QuerySyntaxError,
        contains="cannot combine",
    )


def run_lexical_suite(runner: ProbeRunner) -> None:
    _banner("Lexical Search")

    focus_path = runner.scratch_path("lexical/focus.md")
    support_path = runner.scratch_path("lexical/support.md")
    noise_path = runner.scratch_path("lexical/noise.md")

    runner.expect_exact(
        "write lexical focus file",
        f"write {focus_path} {_quote('authentication authentication timeout playbook')}",
        f"Wrote {focus_path}",
    )
    runner.expect_exact(
        "write lexical support file",
        f"write {support_path} {_quote('authentication timeout notes')}",
        f"Wrote {support_path}",
    )
    runner.expect_exact(
        "write lexical noise file",
        f"write {noise_path} {_quote('completely unrelated content')}",
        f"Wrote {noise_path}",
    )

    def _check() -> str:
        result = runner.client.lexical_search("authentication timeout", k=2)
        if result.function != "lexical_search":
            raise AssertionError(f"Expected lexical_search result envelope, got {result.function!r}")
        if not result.entries:
            raise AssertionError("Expected lexical_search to return at least one match")
        top = result.entries[0]
        if top.path != focus_path:
            raise AssertionError(f"Expected top lexical hit {focus_path}, got {top.path}")
        if top.content is None or "authentication" not in top.content:
            raise AssertionError("Expected lexical_search top hit to hydrate content")
        if top.score is None or not (0.0 <= top.score < 1.0):
            raise AssertionError(f"Expected a bounded ts_rank_cd score in [0, 1), got {top.score!r}")
        return f"top hit {top.path} scored {top.score:.4f} via native FTS"

    runner.custom_check("lexical_search returns hydrated native-FTS-ranked results", _check)


def run_native_vector_suite(runner: ProbeRunner) -> None:
    _banner("Native Vector")

    sample = getattr(runner.client, "_native_vector_sample", None)
    if sample is None:
        runner._record(
            label="native vector probe",
            status="WARN",
            detail="no native pgvector embeddings found; skipped vector_search smoke check",
        )
        return

    sample_path, sample_vector = sample
    mounted_sample_path = _mount_path(runner.mount, sample_path)

    def _check() -> str:
        result = runner.client.vector_search(sample_vector, k=5)
        if mounted_sample_path not in result.paths:
            raise AssertionError(f"Expected native vector_search to include {mounted_sample_path}, got {result.paths}")
        if any(entry.content is not None for entry in result.entries):
            raise AssertionError("vector_search returned content; expected path + score only")
        return f"top hit set contains {mounted_sample_path}"

    runner.custom_check("native vector_search returns embedded row", _check)


def run_performance_suite(
    runner: ProbeRunner,
    *,
    perf_max_count: int,
    perf_budget_ms: float,
    tree_depth: int,
    strict: bool,
) -> None:
    _banner("Performance")

    targets = [
        PerfTarget(
            label="glob over the loaded repo",
            query=f"glob {_quote(f'{runner.mount_root}/**/*.py')} --max-count {perf_max_count}",
            soft_budget_ms=perf_budget_ms,
        ),
        PerfTarget(
            label="grep over src/ for definitions",
            query=f"grep {_quote('def ')} {runner.mount_root}/src --max-count {perf_max_count}",
            soft_budget_ms=perf_budget_ms,
        ),
        PerfTarget(
            label="grep count over tests/ with projected score",
            query=(
                f"grep {_quote('async def|def ')} {runner.mount_root}/tests --ignore-case "
                f"--count --output path,score --max-count {perf_max_count}"
            ),
            soft_budget_ms=perf_budget_ms,
        ),
        PerfTarget(
            label="tree over src/",
            query=f"tree {runner.mount_root}/src --depth {tree_depth}",
            soft_budget_ms=perf_budget_ms,
        ),
        PerfTarget(
            label="chain glob | grep | read on repo code",
            query=f"glob {_quote(f'{runner.mount_root}/src/**/*.py')} | grep {_quote('class ')} | top 20",
            soft_budget_ms=perf_budget_ms * 1.5,
        ),
    ]

    for target in targets:
        runner.perf_check(target, strict=strict)


def cleanup_scratch(runner: ProbeRunner) -> None:
    try:
        runner.client.cli(f"rm {runner.scratch_root}")
    except VFSError:
        return


def _raise(exc: Exception) -> str:
    raise exc


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        mount = _normalize_mount(args.mount)
    except ValueError as exc:
        parser.error(str(exc))

    repo_root = args.repo_root.resolve()
    run_id = time.strftime("%Y%m%d_%H%M%S")
    scratch_root = _mount_path(mount, f"{args.scratch_prefix.strip('/')}/{run_id}")
    scratch_disk_root = repo_root / args.scratch_prefix.strip("/") / run_id

    _banner("Configuration")
    print(f"repo_root:   {repo_root}")
    print(f"db_url:      {args.db_url}")
    print(f"mount_root:  /{mount}")
    print(f"scratch_root:{scratch_root}")
    print(f"keep_scratch:{args.keep_scratch}")

    client: VFSClient | None = None
    runner: ProbeRunner | None = None
    try:
        client = open_client(args.db_url, mount)
        runner = ProbeRunner(
            client=client,
            repo_root=repo_root,
            mount=mount,
            scratch_root=scratch_root,
            scratch_disk_root=scratch_disk_root,
        )

        run_correctness_suite(runner, read_path=args.read_path)
        run_lexical_suite(runner)
        run_negative_suite(runner)
        run_native_vector_suite(runner)
        if not args.skip_perf:
            run_performance_suite(
                runner,
                perf_max_count=args.perf_max_count,
                perf_budget_ms=args.perf_budget_ms,
                tree_depth=args.tree_depth,
                strict=args.strict_perf,
            )
    except Exception as exc:
        print(f"\n{RED}{BOLD}FATAL{RESET} {type(exc).__name__}: {exc}")
        return 2
    finally:
        if runner is not None and not args.keep_scratch:
            cleanup_scratch(runner)
        if client is not None:
            client.close()

    assert runner is not None
    runner.print_summary()
    return 1 if runner.failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
