"""The read family over seeded rows — verbs, scopes, failures, collation.

Reads land before mutations, so every case here seeds through Core and
then exercises the read verbs: content and metadata shapes, projection
masks, the namespace liveness scopes, failure classification and retry,
unicode ordering under binary collation, and the stubs standing in for
verbs that have not landed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import event, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from ulid import ULID

from tests.support.database_helpers import _SqliteError, _url
from vfs.models import Entry, Observation
from vfs.models.rows import SCHEMA_FORMAT_VERSION, build_vfs_tables
from vfs.paths import Path, extract_extension
from vfs.results import VFSErrorKind
from vfs.results.projection import OBSERVATION_FIELDS
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import StaleSnapshot
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.reads import ENTRY_OBSERVATION_FIELDS, _glob_like

# ---------------------------------------------------------------------------
# Read family + glob — seeded directly through Core (writes land later)
# ---------------------------------------------------------------------------


async def _seed(storage: DatabaseStorage, rows: list[tuple[str, str, str | None]]) -> None:
    """Plant rows the way the write slices later will: entries + content.

    Reads land before mutations, so tests seed through Core directly —
    ancestors are minted as directories, files get a content row, and
    every row gets a distinct version.
    """
    assert (await storage.first_touch()).success is True
    tables = storage._host.tables
    now = datetime.now(UTC)
    async with storage._host.session_factory() as session:
        conn = await session.connection(execution_options={"vfs_writer": True})
        root_key = (await conn.execute(select(tables.entry.c.entry_id).where(tables.entry.c.path == "/"))).scalar_one()
        ids: dict[str, str] = {"/": root_key}
        version = 0

        async def ensure(path: str, kind: str, content: str | None) -> None:
            nonlocal version
            if path in ids:
                return
            parent = path.rsplit("/", 1)[0] or "/"
            if parent not in ids:
                await ensure(parent, "directory", None)
            version += 1
            entry_key = str(ULID())
            await conn.execute(
                insert(tables.entry).values(
                    entry_id=entry_key,
                    parent_id=ids[parent],
                    path=path,
                    name=path.rsplit("/", 1)[1],
                    kind=kind,
                    ext=Path(path).ext,
                    version=version,
                    size_bytes=len(content.encode()) if content is not None else 0,
                    lines=content.count("\n") + 1 if content else 0,
                    created_at=now,
                    updated_at=now,
                )
            )
            ids[path] = entry_key
            if content is not None:
                await conn.execute(insert(tables.content).values(entry_id=entry_key, created_at=now, content=content))

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
        assert row.version is not None
        assert "content" in row.populated

    async def test_read_on_a_directory_is_wrong_kind(self, storage: DatabaseStorage) -> None:
        result = await storage.read(path=Path("/docs"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert "Is a directory" in result.errors[0].message

    async def test_read_batch_keeps_good_rows_and_classifies_misses(self, storage: DatabaseStorage) -> None:
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
        assert {"path", "kind", "version"} <= file_row.populated

        dir_row = (await storage.stat(path=Path("/docs"))).observations[0]
        assert dir_row.kind == "directory"
        assert dir_row.size_bytes is None  # the NOT NULL 0 never reads as a size
        assert "size_bytes" in dir_row.populated  # fetched-and-null stays masked

    async def test_missing_ancestor_classifies_not_found_at_that_component(self, storage: DatabaseStorage) -> None:
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/ghost/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.not_found
            assert result.errors[0].path == "/ghost"

    async def test_file_ancestor_classifies_wrong_kind_at_that_component(self, storage: DatabaseStorage) -> None:
        for verb in (storage.read, storage.stat, storage.ls, storage.tree):
            result = await verb(path=Path("/top.txt/deep/x.txt"))
            assert result.success is False
            assert result.errors[0].kind == VFSErrorKind.wrong_kind
            assert result.errors[0].path == "/top.txt"

    async def test_sibling_misses_under_one_dead_ancestor_stay_distinct(self, storage: DatabaseStorage) -> None:
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
        assert row.populated == {"path", "kind", "version", "size_bytes", "mime_type"}
        assert row.mime_type is None  # fetched, and null
        assert row.content_hash is None
        assert "content_hash" not in row.populated  # not fetched

    async def test_read_projection_controls_the_content_fetch(self, storage: DatabaseStorage) -> None:
        without = (await storage.read(path=Path("/docs/a.txt"), columns=frozenset({"path"}))).observations[0]
        assert without.content is None
        assert "content" not in without.populated
        with_content = (await storage.read(path=Path("/docs/a.txt"), columns=frozenset({"content"}))).observations[0]
        assert with_content.content == "alpha"
        assert "content" in with_content.populated

    async def test_projection_of_an_unbacked_field_serves_identity_only(self, storage: DatabaseStorage) -> None:
        # A requested field with no entries-table column is dropped from
        # the mask, never a raw column lookup that would raise past _execute.
        result = await storage.stat(path=Path("/docs/a.txt"), columns=frozenset({"score", "content"}))
        assert result.success is True
        assert result.observations[0].populated == {"path", "kind", "version"}

    def test_entry_observation_fields_track_the_column_vocabulary(self) -> None:
        # Drift pin: the servable set is exactly the Observation fields
        # the entries table backs — a new mirrored column must land here.
        cols = {c.name for c in build_vfs_tables(table_name="vfs").entry.columns}
        assert OBSERVATION_FIELDS & cols == ENTRY_OBSERVATION_FIELDS

    async def test_glob_matches_names_and_full_paths(self, storage: DatabaseStorage) -> None:
        by_name = await storage.glob(patterns=("*.txt",))
        assert [o.path for o in by_name.observations] == [
            "/docs/Zed.txt",
            "/docs/a.txt",
            "/docs/sub/c.txt",
            "/top.txt",
        ]
        by_path = await storage.glob(patterns=("/docs/*.txt",))
        assert [o.path for o in by_path.observations] == ["/docs/Zed.txt", "/docs/a.txt"]
        recursive = await storage.glob(patterns=("/docs/**/*.txt",))
        assert [o.path for o in recursive.observations] == ["/docs/Zed.txt", "/docs/a.txt", "/docs/sub/c.txt"]

    async def test_glob_scope_ext_and_max_count(self, storage: DatabaseStorage) -> None:
        scoped = await storage.glob(patterns=("*",), observations=[Observation(path=Path("/docs"))])
        assert all(str(o.path).startswith("/docs") for o in scoped.observations)
        by_ext = await storage.glob(patterns=("*",), ext=("md",))
        assert [o.path for o in by_ext.observations] == ["/docs/b.md"]
        capped = await storage.glob(patterns=("*.txt",), max_count=2)
        assert len(capped.observations) == 2

    async def test_glob_character_class_falls_back_to_fnmatch(self, storage: DatabaseStorage) -> None:
        result = await storage.glob(patterns=("[ab]*.txt",))
        assert [o.path for o in result.observations] == ["/docs/a.txt"]

    async def test_glob_escapes_like_metacharacters(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/da_a.txt", "file", "x"), ("/daxa.txt", "file", "x")])
        result = await storage.glob(patterns=("da_a.txt",))
        assert [o.path for o in result.observations] == ["/da_a.txt"]
        await storage.close()

    async def test_read_family_emits_selects_only_and_ls_keys_on_parent_id(self, tmp_path) -> None:
        # The module docstring's statement-shape promises, pinned the way
        # the write family pins its counts: SELECTs only, and ls children
        # come from parent_id equality — never a path prefix scan.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/docs/a.txt", "file", "alpha")])
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        assert (await storage.read(path=Path("/docs/a.txt"))).success is True
        assert (await storage.stat(path=Path("/docs/a.txt"))).success is True
        assert (await storage.ls(path=Path("/docs"))).success is True
        assert (await storage.tree(path=Path("/"))).success is True
        assert (await storage.glob(patterns=("*.txt",))).success is True
        queries = [s for s in statements if not s.startswith(("BEGIN", "COMMIT", "ROLLBACK", "PRAGMA"))]
        assert queries and all(s.lstrip().startswith("SELECT") for s in queries), queries
        children = [s for s in queries if "parent_id IN" in s]
        assert children, queries
        await storage.close()

    async def test_prefix_escaping_bounds_tree_and_scoped_glob(self, tmp_path) -> None:
        # The escaped LIKE prefix is the sole subtree filter for both
        # verbs: a metacharacter in a directory name must not widen it.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/da_a/x.txt", "file", "in"), ("/daxa/y.txt", "file", "out")])
        subtree = await storage.tree(path=Path("/da_a"))
        assert [str(o.path) for o in subtree.observations] == ["/da_a/x.txt"]
        scoped = await storage.glob(patterns=("*",), observations=[Observation(path=Path("/da_a"))])
        assert [str(o.path) for o in scoped.observations] == ["/da_a", "/da_a/x.txt"]
        await storage.close()


class TestGlobLikeTranslator:
    """Unit rows on the LIKE prefilter translation — superset by construction.

    The translation must never under-match the glob authority: a whole
    ``**`` component fuses with its trailing separator into one ``%`` so
    the zero-depth match survives; anything inexpressible returns None
    and falls back to the escaped literal-prefix LIKE.
    """

    def test_whole_double_star_component_fuses_with_its_separator(self) -> None:
        # The motivating row: /docs/%%/%.txt would demand a literal slash
        # and silently drop the zero-depth match /docs/a.txt.
        assert _glob_like("/docs/**/*.txt") == "/docs/%%.txt"

    def test_double_star_at_the_edges(self) -> None:
        assert _glob_like("/docs/**") == "/docs/%"
        assert _glob_like("**/*.txt") == "%%.txt"
        assert _glob_like("**") == "%"

    def test_single_star_and_question_stay_deliberately_loose(self) -> None:
        assert _glob_like("/docs/*.txt") == "/docs/%.txt"
        assert _glob_like("/d?cs/a.txt") == "/d_cs/a.txt"

    def test_mid_component_double_star_is_inexpressible(self) -> None:
        assert _glob_like("/docs/a**b.txt") is None
        assert _glob_like("/docs/***/x.txt") is None
        assert _glob_like("a**b") is None

    def test_character_class_is_inexpressible(self) -> None:
        assert _glob_like("/docs/[ab].txt") is None

    def test_like_metacharacters_escape_including_backslash(self) -> None:
        assert _glob_like("/da_a/x%y.txt") == "/da\\_a/x\\%y.txt"
        assert _glob_like("/a\\b/*.txt") == "/a\\\\b/%.txt"

    def test_no_emitted_like_contains_a_dangling_escape(self) -> None:
        # Postgres errors data-dependently on a dangling-escape LIKE, so
        # the invariant is structural: every escape char starts a pair.
        patterns = ["/a\\", "\\", "/docs/*\\", "/x%\\", "**/x\\", "/_%\\\\"]
        for pattern in patterns:
            like = _glob_like(pattern)
            assert like is not None
            i = 0
            while i < len(like):
                if like[i] == "\\":
                    assert i + 1 < len(like), f"dangling escape in {like!r}"
                    i += 2
                else:
                    i += 1


class TestExtPushdown:
    """The ext filters reach SQL as AND-ed narrowing; the verify stays on."""

    @staticmethod
    def _recorded(storage: DatabaseStorage) -> list[str]:
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        return statements

    async def test_ext_parameter_pushes_down_as_membership(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/a.py", "file", "x"), ("/b.txt", "file", "x")])
        statements = self._recorded(storage)
        result = await storage.glob(patterns=("*",), ext=("py",))
        assert [str(o.path) for o in result.observations] == ["/a.py"]
        assert any("ext IN" in s for s in statements), statements
        await storage.close()

    async def test_pattern_derived_ext_narrows_with_the_dotfile_arm(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/a.txt", "file", "x"), ("/b.py", "file", "x")])
        statements = self._recorded(storage)
        result = await storage.glob(patterns=("**/*.txt",))
        assert [str(o.path) for o in result.observations] == ["/a.txt"]
        derived = [s for s in statements if "ext = " in s]
        assert derived and all("name = " in s for s in derived), statements
        await storage.close()

    async def test_oversized_ext_tuple_skips_the_pushdown(self, tmp_path) -> None:
        # A filter never becomes a fan-out: past the membership budget the
        # Python gate alone narrows, and the result is identical.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/a.py", "file", "x")])
        oversized = (*(f"e{i}" for i in range(storage._host.membership_budget + 1)), "py")
        statements = self._recorded(storage)
        result = await storage.glob(patterns=("*",), ext=oversized)
        assert [str(o.path) for o in result.observations] == ["/a.py"]
        assert not any("ext IN" in s for s in statements), statements
        await storage.close()

    async def test_ext_binds_shrink_the_pattern_fan_chunk(self, tmp_path, monkeypatch) -> None:
        # The ext membership rides inside every arm, so its binds buy
        # arms out of each chunk — the sum stays inside the engine's
        # parameter budget instead of exceeding it.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/d0/a.py", "file", "x")])
        roots = [Observation(path=Path(f"/d{i}")) for i in range(20)]
        statements = self._recorded(storage)
        await storage.glob(patterns=("*",), observations=roots, ext=("py", "e1", "e2", "e3", "e4", "e5"))
        fanned = [s for s in statements if "ext IN" in s]
        # Budget 48 → membership 16: 6 ext binds beside 6 fixed arm
        # binds leave one arm per chunk — 20 chunks for 20 roots.
        assert len(fanned) == 20, len(fanned)

    async def test_stored_ext_agrees_with_the_path_law_on_every_row(self, tmp_path) -> None:
        # One law, whole table: after writes, minted parents, renames on
        # both transfer verbs, and a trash hop, every stored ext equals
        # extract_extension of the row's own path.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.first_touch()).success is True
        await storage.write(entries=[Entry(path=Path("/a/b.txt"), content="x")], parents=True)
        await storage.mkdir(path=Path("/v1.py"))
        await storage.write(entries=[Entry(path=Path("/v1.py/c.md"), content="x")])
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/a/b.txt"), dest=Path("/a/d.png"))])).success
        assert (await storage.move(operations=[ResolvedPair(src=Path("/a/d.png"), dest=Path("/a/e"))])).success
        assert (await storage.delete(path=Path("/v1.py/c.md"))).success is True
        tables = storage._host.tables
        async with storage._host.session_factory() as session:
            rows = (await session.execute(select(tables.entry.c.path, tables.entry.c.ext))).all()
        assert len(rows) >= 7
        for path, ext in rows:
            assert ext == extract_extension(Path(path)), (path, ext)
        await storage.close()

    async def test_dot_only_ext_element_never_drops_extensionless_rows(self, tmp_path) -> None:
        # ext=(".",) normalizes to the empty extension, which matches
        # extensionless rows in the Python gate; SQL IN ('') would drop
        # them (stored ext is NULL), so the pushdown must stand down.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/README", "file", "x"), ("/a.py", "file", "x")])
        result = await storage.glob(patterns=("*",), ext=(".",))
        assert [str(o.path) for o in result.observations] == ["/README"]
        await storage.close()


class TestPatternFan:
    """The batched executor: pure-OR arms, dead-arm drops, one session."""

    async def test_a_contradicted_arm_is_dead_before_sql(self, tmp_path) -> None:
        # A derived ext contradicting the caller's set is provably empty:
        # the arm never reaches SQL, and the live arm still serves.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/a/x.py", "file", "x"), ("/b/y.txt", "file", "x")])
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        result = await storage.glob(patterns=("/a/**/*.py", "/b/**/*.txt"), ext=("py",))
        assert [str(o.path) for o in result.observations] == ["/a/x.py"]
        [fan] = [s for s in statements if "LIKE" in s]
        assert ".txt" not in fan
        await storage.close()

    async def test_multi_index_or_plan_survives_the_ext_facts(self, tmp_path) -> None:
        # The measured ~350x cliff: one conjunct beside the fan demotes
        # the whole WHERE to a scan. Every ext fact rides inside its
        # arm, so the plan must keep the multi-index OR — no table scan.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/a/x.py", "file", "x"), ("/b/y.txt", "file", "x")])
        recorded: list[tuple[str, tuple[str, ...]]] = []

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            recorded.append((statement, parameters))

        result = await storage.glob(patterns=("/a/**/*.py", "/b/**/*.txt"), ext=("py", "txt"))
        assert [str(o.path) for o in result.observations] == ["/a/x.py", "/b/y.txt"]
        [(fan, params)] = [(s, p) for s, p in recorded if "LIKE" in s and s.startswith("SELECT")]
        literal = fan
        for value in params:
            literal = literal.replace("?", f"'{value}'", 1)
        async with storage._host.session_factory() as session:
            plan = (await session.execute(text("EXPLAIN QUERY PLAN " + literal))).all()
        details = [row[-1] for row in plan]
        assert any("MULTI-INDEX OR" in detail for detail in details), details
        assert not any("SCAN" in detail for detail in details), details
        await storage.close()

    async def test_contract_scale_pattern_batch_chunks_within_budget(self, tmp_path) -> None:
        # The scale row: 10k patterns in one call chunk at the measured
        # 200-arm width — 50 fan statements, every one inside the
        # engine's bind and depth caps, one session throughout.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/part00000/a.parquet", "file", "x")])
        checkouts = 0
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "checkout")
        def checked_out(dbapi_conn, connection_record, connection_proxy) -> None:
            nonlocal checkouts
            checkouts += 1

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        patterns = tuple(f"/part{i:05}/**/*.parquet" for i in range(10_000))
        result = await storage.glob(patterns=patterns)
        assert [str(o.path) for o in result.observations] == ["/part00000/a.parquet"]
        fan = [s for s in statements if "LIKE" in s and s.startswith("SELECT")]
        assert len(fan) == 50
        assert checkouts == 1
        await storage.close()

    async def test_chunked_fan_serves_in_one_session(self, tmp_path, monkeypatch) -> None:
        # Many chunks, one snapshot: the whole batched call — root
        # probes, fan chunks, miss classification — checks out exactly
        # one connection, so no chunk can observe a different world.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(storage, [("/d00/a.py", "file", "x")])
        checkouts = 0
        statements: list[str] = []

        @event.listens_for(storage._host.engine.sync_engine, "checkout")
        def checked_out(dbapi_conn, connection_record, connection_proxy) -> None:
            nonlocal checkouts
            checkouts += 1

        @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append(statement)

        roots = [Observation(path=Path(f"/d{i:02}")) for i in range(12)]
        result = await storage.glob(patterns=("*",), observations=roots)
        assert result.success is False  # eleven ghost roots classify loudly
        assert [str(o.path) for o in result.observations] == ["/d00", "/d00/a.py"]
        fan = [s for s in statements if "LIKE" in s and s.startswith("SELECT")]
        assert len(fan) > 1, fan  # the arms chunked across statements
        assert checkouts == 1
        await storage.close()


class TestNamespaceScopes:
    """The meta-scope liveness filter: hidden by default, served when anchored."""

    @pytest.fixture
    async def storage(self, tmp_path):
        storage = DatabaseStorage(url=_url(tmp_path))
        await _seed(
            storage,
            [
                ("/real.txt", "file", "needle in the open"),
                ("/.vfs/docs/a.txt", "file", "meta doc text"),
                ("/.vfs/trash/bucket/01ARZ", "file", "needle in the trash"),
            ],
        )
        yield storage
        await storage.close()

    async def test_enumeration_hides_the_meta_subtree(self, storage: DatabaseStorage) -> None:
        assert [o.path for o in (await storage.ls(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.tree(path=Path("/"))).observations] == ["/real.txt"]
        assert [o.path for o in (await storage.glob(patterns=("*",))).observations] == ["/real.txt"]

    async def test_direct_meta_address_bypasses_the_meta_exclusion(self, storage: DatabaseStorage) -> None:
        doc = Path("/.vfs/docs/a.txt")
        stat = await storage.stat(path=doc)
        assert stat.success is True
        assert stat.observations[0].kind == "file"
        read = await storage.read(path=doc)
        assert read.observations[0].content == "meta doc text"
        listing = await storage.ls(path=doc.parent_dir)
        assert [o.path for o in listing.observations] == [str(doc)]

    async def test_batch_ls_keeps_liveness_scopes_apart(self, storage: DatabaseStorage) -> None:
        # One batch, both liveness classes: the meta target serves its
        # children while the non-meta parent's listing stays meta-free.
        batch = [Observation(path=Path("/")), Observation(path=Path("/.vfs"))]
        listing = await storage.ls(observations=batch)
        assert listing.success is True
        assert [str(o.path) for o in listing.observations] == ["/real.txt", "/.vfs/docs", "/.vfs/trash"]

    async def test_glob_meta_bypass_is_per_pattern_not_query_wide(self, storage: DatabaseStorage) -> None:
        # ROOT plus a meta root: only the meta-prefixed arm serves meta
        # rows — /.vfs itself and sibling meta trees stay hidden.
        roots = [Observation(path=Path("/")), Observation(path=Path("/.vfs/trash"))]
        result = await storage.glob(patterns=("*",), observations=roots)
        assert [str(o.path) for o in result.observations] == [
            "/.vfs/trash",
            "/.vfs/trash/bucket",
            "/.vfs/trash/bucket/01ARZ",
            "/real.txt",
        ]

    async def test_trash_serves_beside_other_meta_children_when_anchored(self, storage: DatabaseStorage) -> None:
        # Trash is an ordinary meta subtree: an ls of /.vfs lists it.
        listing = await storage.ls(path=Path("/.vfs"))
        assert [o.path for o in listing.observations] == ["/.vfs/docs", "/.vfs/trash"]
        subtree = await storage.tree(path=Path("/.vfs"))
        assert "/.vfs/trash/bucket/01ARZ" in [str(o.path) for o in subtree.observations]

    async def test_a_trash_side_path_serves_through_every_read_verb(self, storage: DatabaseStorage) -> None:
        trashed = Path("/.vfs/trash/bucket/01ARZ")
        assert (await storage.read(path=trashed)).observations[0].content == "needle in the trash"
        assert (await storage.stat(path=trashed)).observations[0].kind == "file"
        listing = await storage.ls(path=trashed.parent_dir)
        assert [o.path for o in listing.observations] == [str(trashed)]
        scoped = await storage.glob(patterns=("*",), observations=[Observation(path=Path("/.vfs/trash"))])
        assert str(trashed) in [str(o.path) for o in scoped.observations]

    async def test_descent_through_a_trash_side_file_takes_the_standard_ladder(self, storage: DatabaseStorage) -> None:
        # A child under a trash-side FILE classifies wrong_kind naming the
        # file — identical to descent anywhere else in the namespace.
        result = await storage.read(path=Path("/.vfs/trash/bucket/01ARZ/child"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/.vfs/trash/bucket/01ARZ"

    async def test_trash_misses_classify_at_their_first_failing_component(self, storage: DatabaseStorage) -> None:
        # The standard descent ladder, not a uniform concealment shape:
        # each miss names its own first missing ancestor.
        under_real_bucket = await storage.stat(path=Path("/.vfs/trash/bucket/GHOST/x"))
        assert under_real_bucket.errors[0].kind == VFSErrorKind.not_found
        assert under_real_bucket.errors[0].path == "/.vfs/trash/bucket/GHOST"
        under_no_bucket = await storage.stat(path=Path("/.vfs/trash/NOBUCKET/x"))
        assert under_no_bucket.errors[0].kind == VFSErrorKind.not_found
        assert under_no_bucket.errors[0].path == "/.vfs/trash/NOBUCKET"


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
        # Exhaustion has one channel: a retryable engine outcome leaves as
        # StaleSnapshot with the native error as its cause, never raw.
        host = EngineHost(url=_url(tmp_path), retry_attempts=2, retry_base_delay=0.001)

        async def always_busy() -> None:
            raise DBAPIError("SELECT 1", None, _SqliteError(5))

        with pytest.raises(StaleSnapshot) as caught:
            await host.with_retry(always_busy)
        assert isinstance(caught.value.__cause__, DBAPIError)
        assert "outlived 2 attempts" in caught.value.context

        async def never_retryable() -> None:
            raise DBAPIError("SELECT 1", None, _SqliteError(1))

        with pytest.raises(DBAPIError):
            await host.with_retry(never_retryable)
        await host.close()

    async def test_write_failure_classifies_unavailable(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.first_touch()
        async with storage._host.engine.begin() as conn:
            await conn.exec_driver_sql("DROP TABLE vfs")
        result = await storage.write(entries=[Entry(path=Path("/f.txt"), content="x")])
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert result.errors[0].retryable is True
        await storage.close()

    async def test_unreachable_database_refuses_stub_verbs_classified(self, tmp_path) -> None:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/absent/vfs.sqlite")
        result = await storage.grep(pattern="x")  # a stub verb still gates on first touch
        assert result.ops == ("grep",)
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unavailable
        assert "First touch failed" in result.errors[0].message
        await storage.close()


class TestUnlandedVerbStubs:
    """Undeclared verbs stay off the capability set; stubs refuse classified.

    mkedge is the last classified stub — its subtraction from the
    derived surface pins that mid-story honesty.
    """

    async def test_unlanded_verbs_refuse_as_unsupported(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        result = await storage.mkedge(source=Path("/a"), target=Path("/b"), edge_type="imports")
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.unsupported
        assert storage.capabilities() == {
            "read",
            "stat",
            "ls",
            "tree",
            "glob",
            "grep",
            "write",
            "edit",
            "mkdir",
            "delete",
            "restore",
            "sweep",
            "move",
            "copy",
        }
        assert "mkedge" not in storage.capabilities()
        await storage.close()

    async def test_mutation_verbs_surface_the_first_touch_refusal(self, tmp_path) -> None:
        seeded = DatabaseStorage(url=_url(tmp_path))
        await seeded.first_touch()
        meta = seeded._host.tables.meta
        async with seeded._host.engine.begin() as conn:
            await conn.execute(update(meta).values(schema_format_version=SCHEMA_FORMAT_VERSION + 1))
        await seeded.close()
        stale = DatabaseStorage(url=_url(tmp_path))
        for call in (
            stale.write(entries=[Entry(path=Path("/a"), content="x")]),
            stale.mkedge(source=Path("/a"), target=Path("/b"), edge_type="imports"),
            stale.reindex(),
        ):
            result = await call
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
        assert upper.observations[0].version != lower.observations[0].version

    async def test_glob_stays_case_sensitive_through_the_pool(self, storage: DatabaseStorage) -> None:
        # The LIKE prefilter must not case-fold: case_sensitive_like=ON is
        # stamped per checkout, and fnmatchcase is the authority.
        result = await storage.glob(patterns=("A*",))
        assert [o.path.name for o in result.observations] == ["A.txt"]

    async def test_point_read_misses_on_case_difference(self, storage: DatabaseStorage) -> None:
        result = await storage.stat(path=Path("/dir/a.TXT"))
        assert result.success is False
        assert result.errors[0].kind == VFSErrorKind.not_found
