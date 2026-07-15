"""DatabaseStorage lifecycle tests — construction, first touch, retry, close.

The conformance suite covers verb behavior once families land; this file
holds the DB-specific contract: the construction XOR (built url vs
borrowed session factory — never a bare engine), idempotent provisioning
under the serialization point, schema-version verification, restart
rebind, cross-loop first touch, borrowed-sessions close, and the dialect
policy layer (generic floor, deferred resolution, retryable
classification).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from ulid import ULID

from vfs.models.rows import MAX_TABLE_NAME_LENGTH, SCHEMA_FORMAT_VERSION, ULID_LENGTH, build_vfs_tables
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage import TRAIT_KEYS, TRAIT_VALUES, StorageBackend, SupportsClose, SupportsTraits
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import (
    GENERIC,
    POSTGRESQL,
    SQLITE,
    is_retryable,
    profile_for,
)


def _url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite"


# ---------------------------------------------------------------------------
# Construction XOR
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_url_and_session_factory_together_are_refused(self, tmp_path) -> None:
        factory = async_sessionmaker(create_async_engine(_url(tmp_path)), expire_on_commit=False)
        with pytest.raises(ValueError, match="exactly one"):
            DatabaseStorage(url=_url(tmp_path), session_factory=factory)

    def test_neither_url_nor_session_factory_is_refused(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            DatabaseStorage()

    def test_over_budget_table_name_is_refused_at_construction(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="63-char"):
            DatabaseStorage(url=_url(tmp_path), table_name="x" * (MAX_TABLE_NAME_LENGTH + 1))

    def test_satisfies_the_storage_protocols(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert isinstance(storage, StorageBackend)
        assert isinstance(storage, SupportsClose)
        assert isinstance(storage, SupportsTraits)

    def test_traits_stay_within_the_vocabulary(self, tmp_path) -> None:
        traits = DatabaseStorage(url=_url(tmp_path)).traits()
        assert set(traits) <= TRAIT_KEYS
        assert all(value in TRAIT_VALUES[key] for key, value in traits.items())


# ---------------------------------------------------------------------------
# Dialect policy — generic floor and retryable classification
# ---------------------------------------------------------------------------


class _SqliteError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__("locked")
        self.sqlite_errorcode = code


class _PgError(Exception):
    def __init__(self, state: str) -> None:
        super().__init__("serialization")
        self.sqlstate = state


class TestDialectPolicy:
    def test_unknown_dialect_serves_on_the_generic_floor(self) -> None:
        profile = profile_for("duckdb")
        assert profile.name == "duckdb"
        assert profile.key_byte_budget == GENERIC.key_byte_budget
        assert profile.arbitration == "catch_retry"

    def test_sqlite_busy_is_retryable_but_busy_snapshot_is_not(self) -> None:
        assert is_retryable(SQLITE, _SqliteError(5)) is True
        assert is_retryable(SQLITE, _SqliteError(517)) is False

    def test_serialization_sqlstates_are_retryable(self) -> None:
        assert is_retryable(POSTGRESQL, _PgError("40001")) is True
        assert is_retryable(POSTGRESQL, _PgError("40P01")) is True

    def test_unique_violation_is_never_retryable(self) -> None:
        assert is_retryable(POSTGRESQL, _PgError("23505")) is False

    def test_pyodbc_style_sqlstate_in_args_classifies(self) -> None:
        exc = Exception("40001", "deadlock victim")
        assert is_retryable(GENERIC, exc) is True

    def test_an_exception_with_no_sqlstate_is_not_retryable(self) -> None:
        assert is_retryable(GENERIC, Exception()) is False

    def test_parameter_budget_is_read_from_sqlalchemy(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        host = storage._host
        assert host.parameter_budget == host.engine.dialect.insertmanyvalues_max_parameters
        assert host.parameter_budget >= 999


# ---------------------------------------------------------------------------
# First touch — provision, verify, refuse
# ---------------------------------------------------------------------------


class TestFirstTouch:
    async def test_provisions_meta_and_root_rows(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.first_touch()
        assert result.success is True
        assert storage.mount_identity is not None
        assert len(storage.mount_identity) == ULID_LENGTH
        tables = storage._host.tables
        async with storage._host.engine.connect() as conn:
            meta = (await conn.execute(select(tables.meta))).mappings().one()
            root = (await conn.execute(select(tables.entry))).mappings().one()
        assert meta["schema_format_version"] == SCHEMA_FORMAT_VERSION
        assert meta["mount_identity"] == storage.mount_identity
        assert root["path"] == "/"
        assert root["kind"] == "directory"
        assert root["parent_id"] is None
        await storage.close()

    async def test_is_idempotent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        assert (await storage.first_touch()).success is True
        async with storage._host.engine.connect() as conn:
            count = (await conn.execute(select(storage._host.tables.meta))).all()
        assert len(count) == 1
        await storage.close()

    async def test_applies_database_file_settings(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        async with storage._host.engine.connect() as conn:
            journal = (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar_one()
            page = (await conn.exec_driver_sql("PRAGMA page_size")).scalar_one()
        assert journal == "wal"
        assert page == 16384
        await storage.close()

    async def test_restart_rebind_keeps_the_mount_identity(self, tmp_path) -> None:
        first = DatabaseStorage(url=_url(tmp_path))
        await first.first_touch()
        identity = first.mount_identity
        await first.close()
        second = DatabaseStorage(url=_url(tmp_path))
        assert (await second.first_touch()).success is True
        assert second.mount_identity == identity
        await second.close()

    async def test_version_mismatch_refuses_loudly(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with seeded._host.engine.begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_url(tmp_path))
        result = await stale.first_touch()
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.schema_mismatch
        assert stale.mount_identity is None
        await stale.close()

    async def test_the_first_routed_op_triggers_first_touch(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.stat(path=Path("/"))
        assert result.success is True
        assert result.observations[0].kind == "directory"
        assert storage.mount_identity is not None
        await storage.close()

    async def test_ops_surface_the_mismatch_refusal(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with seeded._host.engine.begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_url(tmp_path))
        result = await stale.stat(path=Path("/"))
        assert result.errors[0].kind == VFSErrorKind.schema_mismatch
        await stale.close()

    async def test_half_provisioned_database_refuses_with_a_classified_error(self, tmp_path) -> None:
        # Root entry present but no meta row: the provision IntegrityError
        # is NOT the designed meta race and must classify, never leak raw.
        tables = build_vfs_tables(table_name="vfs")
        seed = create_async_engine(_url(tmp_path))
        now = datetime.now(UTC)
        async with seed.begin() as conn:
            await conn.run_sync(tables.metadata.create_all)
            await conn.execute(
                insert(tables.entry).values(
                    node_id=str(ULID()),
                    parent_id=None,
                    path="/",
                    name="",
                    kind="directory",
                    revision=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        await seed.dispose()
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.first_touch()
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert "inconsistently provisioned" in result.errors[0].message
        assert storage.mount_identity is None
        await storage.close()

    async def test_two_instances_first_touch_concurrently(self, tmp_path) -> None:
        a = DatabaseStorage(url=_url(tmp_path))
        b = DatabaseStorage(url=_url(tmp_path))
        first, second = await asyncio.gather(a.first_touch(), b.first_touch())
        assert first.success is True
        assert second.success is True
        assert a.mount_identity == b.mount_identity
        async with a._host.engine.connect() as conn:
            rows = (await conn.execute(select(a._host.tables.meta))).all()
        assert len(rows) == 1
        await a.close()
        await b.close()


# ---------------------------------------------------------------------------
# Loops and close
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_construct_on_one_loop_first_touch_on_another(self, tmp_path) -> None:
        async def construct() -> DatabaseStorage:
            return DatabaseStorage(url=_url(tmp_path))

        loop = asyncio.new_event_loop()
        try:
            storage = loop.run_until_complete(construct())
        finally:
            loop.close()

        async def touch_and_close() -> str | None:
            assert (await storage.first_touch()).success is True
            identity = storage.mount_identity
            await storage.close()
            return identity

        assert asyncio.run(touch_and_close()) is not None

    async def test_borrowed_pool_pre_existing_connections_get_session_settings(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        # Pool a connection BEFORE the borrow; checkout must still stamp it.
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        storage = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        assert (await storage.first_touch()).success is True
        async with engine.connect() as conn:  # the app's own pool is stamped too
            like = (await conn.exec_driver_sql("SELECT 'A' LIKE 'a'")).scalar_one()
            timeout = (await conn.exec_driver_sql("PRAGMA busy_timeout")).scalar_one()
        assert like == 0  # case_sensitive_like = ON
        assert timeout == 5000
        await storage.close()
        await engine.dispose()

    async def test_borrowed_close_never_disposes(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        storage = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        assert (await storage.first_touch()).success is True
        await storage.close()
        async with engine.connect() as conn:  # the pool must still serve
            assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
        await engine.dispose()

    async def test_a_borrowed_host_never_holds_an_engine(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        storage = DatabaseStorage(session_factory=async_sessionmaker(engine, expire_on_commit=False))
        with pytest.raises(RuntimeError, match="borrowed host"):
            _ = storage._host.engine
        await engine.dispose()

    async def test_borrowed_dialect_policy_defers_to_first_use(self, tmp_path) -> None:
        engine = create_async_engine(_url(tmp_path))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        calls = 0

        def factory() -> AsyncSession:
            nonlocal calls
            calls += 1
            return maker()

        storage = DatabaseStorage(session_factory=factory)
        assert calls == 0  # construction makes no dialect decision
        assert storage._host.profile.name == "sqlite"
        assert calls == 1  # resolved from the first session's bind
        assert (await storage.first_touch()).success is True
        await storage.close()
        await engine.dispose()

    async def test_built_close_is_idempotent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        await storage.close()
        await storage.close()


# ---------------------------------------------------------------------------
# Read family + glob — seeded directly through Core (writes land later)
# ---------------------------------------------------------------------------


async def _seed(storage: DatabaseStorage, rows: list[tuple[str, str, str | None]]) -> None:
    """Plant rows the way the write slices later will: entries + content.

    Reads land before mutations, so tests seed through Core directly —
    ancestors are minted as directories, files get a content row, and
    every row gets a distinct revision.
    """
    assert (await storage.first_touch()).success is True
    tables = storage._host.tables
    now = datetime.now(UTC)
    async with storage._host.session_factory() as session:
        conn = await session.connection(execution_options={"vfs_writer": True})
        root_id = (await conn.execute(select(tables.entry.c.id).where(tables.entry.c.path == "/"))).scalar_one()
        ids: dict[str, int] = {"/": root_id}
        revision = 0

        async def ensure(path: str, kind: str, content: str | None) -> None:
            nonlocal revision
            if path in ids:
                return
            parent = path.rsplit("/", 1)[0] or "/"
            if parent not in ids:
                await ensure(parent, "directory", None)
            revision += 1
            result = await conn.execute(
                insert(tables.entry)
                .values(
                    node_id=str(ULID()),
                    parent_id=ids[parent],
                    path=path,
                    name=path.rsplit("/", 1)[1],
                    kind=kind,
                    revision=revision,
                    size_bytes=len(content.encode()) if content is not None else 0,
                    lines=content.count("\n") + 1 if content else 0,
                    created_at=now,
                    updated_at=now,
                )
                .returning(tables.entry.c.id)
            )
            entry_id = result.scalar_one()
            ids[path] = entry_id
            if content is not None:
                await conn.execute(insert(tables.content).values(entry_id=entry_id, content=content))

        for path, kind, content in rows:
            await ensure(path, kind, content)
        await session.commit()


class TestReadFamily:
    """Verb behavior over seeded rows — the slice's own verification.

    The conformance suite exercises these paths in full once the write
    slice lands (its fixtures are built through the mutation verbs);
    until then these tests are what proves the read family.
    """

    @pytest.fixture
    async def storage(self, tmp_path):
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(
            storage,
            [
                ("/top.txt", "file", "hello world"),
                ("/docs/Zed.txt", "file", "zulu"),
                ("/docs/a.txt", "file", "alpha"),
                ("/docs/b.md", "file", "bravo"),
                ("/docs/sub/c.txt", "file", "charlie"),
            ],
        )
        yield storage
        await storage.close()

    async def test_read_returns_content(self, storage: DatabaseStorage) -> None:
        result = await storage.read(path=Path("/docs/a.txt"))
        assert result.success is True
        row = result.observations[0]
        assert row.content == "alpha"
        assert row.kind == "file"
        assert row.revision is not None
        assert "content" in row.populated

    async def test_read_on_a_directory_is_wrong_kind(self, storage: DatabaseStorage) -> None:
        result = await storage.read(path=Path("/docs"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert "Is a directory" in result.errors[0].message

    async def test_read_batch_keeps_good_rows_and_classifies_misses(self, storage: DatabaseStorage) -> None:
        from vfs.models import Observation

        targets = [Observation(path=Path("/docs/a.txt")), Observation(path=Path("/missing.txt"))]
        result = await storage.read(observations=targets)
        assert result.success is False
        assert [o.path for o in result.observations] == ["/docs/a.txt"]
        assert result.errors[0].kind == VFSErrorKind.not_found
        assert (result.errors[0].data or {})["target"] == "/missing.txt"

    async def test_stat_shapes_and_mask(self, storage: DatabaseStorage) -> None:
        file_row = (await storage.stat(path=Path("/docs/a.txt"))).observations[0]
        assert file_row.kind == "file"
        assert file_row.size_bytes == len(b"alpha")
        assert file_row.content is None
        assert {"path", "kind", "revision"} <= file_row.populated

        dir_row = (await storage.stat(path=Path("/docs"))).observations[0]
        assert dir_row.kind == "directory"
        assert dir_row.size_bytes is None  # the NOT NULL 0 never reads as a size
        assert "size_bytes" in dir_row.populated  # fetched-and-null stays masked

    async def test_missing_ancestor_classifies_not_found_at_that_component(
        self, storage: DatabaseStorage
    ) -> None:
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/ghost/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.not_found
            assert result.errors[0].path == "/ghost"

    async def test_file_ancestor_classifies_wrong_kind_at_that_component(
        self, storage: DatabaseStorage
    ) -> None:
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/top.txt/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.wrong_kind
            assert result.errors[0].path == "/top.txt"

    async def test_sibling_misses_under_one_dead_ancestor_stay_distinct(self, storage: DatabaseStorage) -> None:
        from vfs.models import Observation

        targets = [Observation(path=Path("/dead/x")), Observation(path=Path("/dead/y"))]
        result = await storage.stat(observations=targets)
        assert len(result.errors) == 2
        assert {(e.data or {}).get("target") for e in result.errors} == {"/dead/x", "/dead/y"}

    async def test_ls_orders_children_by_byte_value(self, storage: DatabaseStorage) -> None:
        result = await storage.ls(path=Path("/docs"))
        assert [o.path for o in result.observations] == [
            "/docs/Zed.txt",  # Z (0x5A) sorts before a (0x61) under binary collation
            "/docs/a.txt",
            "/docs/b.md",
            "/docs/sub",
        ]

    async def test_ls_defaults_to_the_root(self, storage: DatabaseStorage) -> None:
        result = await storage.ls()
        assert [o.path for o in result.observations] == ["/docs", "/top.txt"]

    async def test_ls_file_target_lists_itself(self, storage: DatabaseStorage) -> None:
        result = await storage.ls(path=Path("/top.txt"))
        assert [o.path for o in result.observations] == ["/top.txt"]

    async def test_tree_orders_by_path_and_budgets_depth(self, storage: DatabaseStorage) -> None:
        full = await storage.tree(path=Path("/docs"))
        assert [o.path for o in full.observations] == [
            "/docs/Zed.txt",
            "/docs/a.txt",
            "/docs/b.md",
            "/docs/sub",
            "/docs/sub/c.txt",
        ]
        shallow = await storage.tree(path=Path("/docs"), max_depth=1)
        assert [o.path for o in shallow.observations] == [
            "/docs/Zed.txt",
            "/docs/a.txt",
            "/docs/b.md",
            "/docs/sub",
        ]

    async def test_tree_from_the_root_excludes_the_root_row(self, storage: DatabaseStorage) -> None:
        result = await storage.tree(path=Path("/"), max_depth=1)
        assert [o.path for o in result.observations] == ["/docs", "/top.txt"]

    async def test_tree_on_a_file_returns_just_that_row(self, storage: DatabaseStorage) -> None:
        result = await storage.tree(path=Path("/top.txt"))
        assert [o.path for o in result.observations] == ["/top.txt"]

    async def test_tree_rejects_a_sub_one_max_depth_without_touching_the_database(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.tree(path=Path("/"), max_depth=0)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.invalid
        assert storage.mount_identity is None  # refused before first touch
        await storage.close()

    async def test_projection_narrows_the_select_and_stamps_the_mask(self, storage: DatabaseStorage) -> None:
        result = await storage.stat(path=Path("/docs/a.txt"), columns=frozenset({"size_bytes", "mime_type"}))
        row = result.observations[0]
        assert row.populated == {"path", "kind", "revision", "size_bytes", "mime_type"}
        assert row.mime_type is None  # fetched, and null
        assert row.content_hash is None
        assert "content_hash" not in row.populated  # not fetched

    async def test_read_projection_controls_the_content_fetch(self, storage: DatabaseStorage) -> None:
        without = (await storage.read(path=Path("/docs/a.txt"), columns=frozenset({"path"}))).observations[0]
        assert without.content is None
        assert "content" not in without.populated
        with_content = (
            await storage.read(path=Path("/docs/a.txt"), columns=frozenset({"content"}))
        ).observations[0]
        assert with_content.content == "alpha"
        assert "content" in with_content.populated

    async def test_glob_matches_names_and_full_paths(self, storage: DatabaseStorage) -> None:
        by_name = await storage.glob(pattern="*.txt")
        assert [o.path for o in by_name.observations] == [
            "/docs/Zed.txt",
            "/docs/a.txt",
            "/docs/sub/c.txt",
            "/top.txt",
        ]
        by_path = await storage.glob(pattern="/docs/*.txt")
        assert [o.path for o in by_path.observations] == ["/docs/Zed.txt", "/docs/a.txt", "/docs/sub/c.txt"]

    async def test_glob_scope_ext_and_max_count(self, storage: DatabaseStorage) -> None:
        scoped = await storage.glob(pattern="*", paths=(Path("/docs"),))
        assert all(str(o.path).startswith("/docs") for o in scoped.observations)
        by_ext = await storage.glob(pattern="*", ext=("md",))
        assert [o.path for o in by_ext.observations] == ["/docs/b.md"]
        capped = await storage.glob(pattern="*.txt", max_count=2)
        assert len(capped.observations) == 2

    async def test_glob_character_class_falls_back_to_fnmatch(self, storage: DatabaseStorage) -> None:
        result = await storage.glob(pattern="[ab]*.txt")
        assert [o.path for o in result.observations] == ["/docs/a.txt"]

    async def test_glob_escapes_like_metacharacters(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/da_a.txt", "file", "x"), ("/daxa.txt", "file", "x")])
        result = await storage.glob(pattern="da_a.txt")
        assert [o.path for o in result.observations] == ["/da_a.txt"]
        await storage.close()


class TestNamespaceScopes:
    """The two-scope liveness filter: meta hidden by default, trash always."""

    @pytest.fixture
    async def storage(self, tmp_path):
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(
            storage,
            [
                ("/real.txt", "file", "needle in the open"),
                ("/.vfs/docs/a.txt/__meta__/versions/1", "version", "v1 text"),
                ("/.vfs/trash/bucket/01ARZ", "file", "needle in the trash"),
            ],
        )
        yield storage
        await storage.close()

    async def test_enumeration_hides_the_meta_subtree(self, storage: DatabaseStorage) -> None:
        assert [o.path for o in (await storage.ls(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.tree(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.glob(pattern="*")).observations] == ["/real.txt"]

    async def test_direct_meta_address_bypasses_the_meta_exclusion(self, storage: DatabaseStorage) -> None:
        version = Path("/.vfs/docs/a.txt/__meta__/versions/1")
        stat = await storage.stat(path=version)
        assert stat.success is True
        assert stat.observations[0].kind == "version"
        read = await storage.read(path=version)
        assert read.observations[0].content == "v1 text"
        listing = await storage.ls(path=version.parent_dir)
        assert [o.path for o in listing.observations] == [str(version)]

    async def test_trash_is_invisible_even_from_a_meta_anchor(self, storage: DatabaseStorage) -> None:
        # ls of /.vfs is a direct meta address: docs serves, trash never.
        listing = await storage.ls(path=Path("/.vfs"))
        assert [o.path for o in listing.observations] == ["/.vfs/docs"]
        subtree = await storage.tree(path=Path("/.vfs"))
        assert all("/trash" not in str(o.path) for o in subtree.observations)

    async def test_a_trashed_path_classifies_not_found_through_every_read_verb(
        self, storage: DatabaseStorage
    ) -> None:
        trashed = Path("/.vfs/trash/bucket/01ARZ")
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=trashed)
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.not_found

    async def test_descent_through_a_trashed_row_never_surfaces_it(self, storage: DatabaseStorage) -> None:
        # A child under a trashed FILE must not classify wrong_kind naming
        # the trashed row — the walk would leak what point reads hide.
        result = await storage.read(path=Path("/.vfs/trash/bucket/01ARZ/child"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found

    async def test_trash_misses_classify_uniformly_regardless_of_bucket_existence(
        self, storage: DatabaseStorage
    ) -> None:
        # Identical classification whether or not internal trash rows exist
        # on the probed path — error shape must not reveal trash structure.
        under_real_bucket = await storage.stat(path=Path("/.vfs/trash/bucket/GHOST/x"))
        under_no_bucket = await storage.stat(path=Path("/.vfs/trash/NOBUCKET/x"))
        for result in (under_real_bucket, under_no_bucket):
            assert result.errors[0].kind == VFSErrorKind.not_found
            assert result.errors[0].path == "/.vfs/trash"


class TestReadFailureHandling:
    """Driver failures classify; retryable outcomes restart the method."""

    async def test_read_failure_classifies_unavailable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        async with storage._host.engine.begin() as conn:
            await conn.exec_driver_sql("DROP TABLE vfs")
        result = await storage.stat(path=Path("/"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert result.errors[0].retryable is True
        await storage.close()

    async def test_with_retry_restarts_on_a_retryable_error(self, tmp_path) -> None:
        from sqlalchemy.exc import DBAPIError

        from vfs.storage.backends.database.engine import EngineHost

        host = EngineHost(url=_url(tmp_path), retry_base_delay=0.001)
        calls = 0

        async def flaky() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise DBAPIError("SELECT 1", None, _SqliteError(5))
            return "served"

        assert await host.with_retry(flaky) == "served"
        assert calls == 2
        await host.close()

    async def test_with_retry_gives_up_after_the_attempt_budget(self, tmp_path) -> None:
        from sqlalchemy.exc import DBAPIError

        from vfs.storage.backends.database.engine import EngineHost

        host = EngineHost(url=_url(tmp_path), retry_attempts=2, retry_base_delay=0.001)

        async def always_busy() -> None:
            raise DBAPIError("SELECT 1", None, _SqliteError(5))

        with pytest.raises(DBAPIError):
            await host.with_retry(always_busy)
        await host.close()


class TestUnlandedVerbStubs:
    """Every undeclared verb refuses classified; capabilities stay honest."""

    async def test_unlanded_verbs_refuse_as_unsupported(self, tmp_path) -> None:
        from vfs.storage import ResolvedPair
        from vfs.storage.replace import EditOperation

        storage = DatabaseStorage(url=_url(tmp_path))
        pair = [ResolvedPair(src=Path("/a"), dest=Path("/b"))]
        calls = [
            storage.grep(pattern="x"),
            storage.write(path=Path("/a"), content="x"),
            storage.edit(edits=[EditOperation(old="a", new="b")], path=Path("/a")),
            storage.delete(path=Path("/a")),
            storage.mkdir(path=Path("/a")),
            storage.move(operations=pair),
            storage.copy(operations=pair),
            storage.mkedge(source=Path("/a"), target=Path("/b"), edge_type="imports"),
        ]
        for call in calls:
            result = await call
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.unsupported
        stubbed = {"grep", "write", "edit", "delete", "mkdir", "move", "copy", "mkedge"}
        assert storage.capabilities() == {"read", "stat", "ls", "tree", "glob"}
        assert storage.capabilities().isdisjoint(stubbed)
        await storage.close()

    async def test_stub_verbs_surface_the_first_touch_refusal(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with seeded._host.engine.begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_url(tmp_path))
        result = await stale.write(path=Path("/a"), content="x")
        assert result.errors[0].kind == VFSErrorKind.schema_mismatch
        await stale.close()

    async def test_reads_with_no_targets_return_an_empty_success(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.read()
        assert result.success is True
        assert result.observations == []
        await storage.close()


class TestUnicodeAndCollation:
    """Binary collation over non-ASCII names — ordering and case sensitivity."""

    @pytest.fixture
    async def storage(self, tmp_path):
        storage = DatabaseStorage(url=_url(tmp_path))
        # Case pair as siblings plus ASCII/Greek/CJK/emoji names — distinct
        # rows must coexist and order by UTF-8 byte value.
        self.names = ["A.txt", "a.txt", "Z.txt", "é.txt", "Ω.txt", "中.txt", "😀.txt"]
        await _seed(storage, [(f"/dir/{name}", "file", "x") for name in self.names])
        yield storage
        await storage.close()

    async def test_ls_orders_unicode_names_like_python_codepoint_sort(self, storage: DatabaseStorage) -> None:
        # UTF-8 byte order equals codepoint order, so the binary-collated
        # column must reproduce Python's str sort exactly.
        result = await storage.ls(path=Path("/dir"))
        assert [o.path.name for o in result.observations] == sorted(self.names)

    async def test_case_pair_siblings_are_distinct_rows(self, storage: DatabaseStorage) -> None:
        upper = await storage.stat(path=Path("/dir/A.txt"))
        lower = await storage.stat(path=Path("/dir/a.txt"))
        assert upper.success is True and lower.success is True
        assert upper.observations[0].revision != lower.observations[0].revision

    async def test_glob_stays_case_sensitive_through_the_pool(self, storage: DatabaseStorage) -> None:
        # The LIKE prefilter must not case-fold: case_sensitive_like=ON is
        # stamped per checkout, and fnmatchcase is the authority.
        result = await storage.glob(pattern="A*")
        assert [o.path.name for o in result.observations] == ["A.txt"]

    async def test_point_read_misses_on_case_difference(self, storage: DatabaseStorage) -> None:
        result = await storage.stat(path=Path("/dir/a.TXT"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found


class TestPoolExhaustion:
    async def test_pool_exhaustion_classifies_instead_of_raising(self, tmp_path) -> None:
        # sqlalchemy.exc.TimeoutError is not a DBAPIError: the verb must
        # still classify it, never leak it raw (the no-raw-raise criterion).
        engine = create_async_engine(_url(tmp_path), pool_size=1, max_overflow=0, pool_timeout=0.2)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        storage = DatabaseStorage(session_factory=maker)
        assert (await storage.first_touch()).success is True
        async with maker() as hog:
            await hog.connection()  # hold the only pooled connection
            result = await storage.stat(path=Path("/"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert result.errors[0].retryable is True
        await storage.close()
        await engine.dispose()
