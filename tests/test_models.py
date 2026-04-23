"""Tests for vfs.models — VFSEntry and minted entry-table classes."""

from __future__ import annotations

import hashlib

import pytest
from sqlmodel import Field, Session, SQLModel, create_engine, select

from vfs.models import (
    VFSEntry,
    _build_entry_table_class,
    postgres_vector_column_spec,
    resolve_embedding_vector_type,
)
from vfs.vector import NativeEmbeddingConfig, Vector, VectorType

# =========================================================================
# Path normalization and validation in the model
# =========================================================================


class TestPathHandling:
    def test_normalizes_path(self):
        obj = VFSEntry(path="src/auth.py")
        assert obj.path == "/src/auth.py"

    def test_resolves_double_slashes(self):
        obj = VFSEntry(path="/src//auth.py")
        assert obj.path == "/src/auth.py"

    def test_resolves_dot_dot(self):
        obj = VFSEntry(path="/src/../auth.py")
        assert obj.path == "/auth.py"

    def test_null_byte_rejected(self):
        with pytest.raises((ValueError, Exception)):
            VFSEntry(path="/foo\x00bar")

    def test_control_char_rejected(self):
        with pytest.raises((ValueError, Exception)):
            VFSEntry(path="/foo\x01bar")

    def test_del_rejected(self):
        with pytest.raises((ValueError, Exception)):
            VFSEntry(path="/foo\x7fbar")

    def test_empty_path_is_root(self):
        obj = VFSEntry(path="")
        assert obj.path == "/"


# =========================================================================
# Kind inference
# =========================================================================


class TestKindInference:
    def test_file_from_extension(self):
        obj = VFSEntry(path="/src/auth.py")
        assert obj.kind == "file"

    def test_directory(self):
        obj = VFSEntry(path="/src")
        assert obj.kind == "directory"

    def test_chunk(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/chunks/login")
        assert obj.kind == "chunk"

    def test_version(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/versions/3")
        assert obj.kind == "version"

    def test_connection(self):
        obj = VFSEntry(path="/.vfs/a.py/__meta__/edges/out/imports/b.py")
        assert obj.kind == "edge"

    def test_api(self):
        obj = VFSEntry(path="/.vfs/jira/__meta__/apis/ticket")
        assert obj.kind == "api"

    def test_dotfile(self):
        obj = VFSEntry(path="/.bashrc")
        assert obj.kind == "file"

    def test_extensionless_file(self):
        obj = VFSEntry(path="/Makefile")
        assert obj.kind == "file"

    def test_explicit_kind_preserved(self):
        obj = VFSEntry(path="/myapp", kind="file")
        assert obj.kind == "file"


# =========================================================================
# Extension derivation — files only
# =========================================================================


class TestExtensionDerivation:
    def test_file_ext_populated(self):
        obj = VFSEntry(path="/src/auth.py")
        assert obj.ext == "py"

    def test_file_ext_lowercased(self):
        obj = VFSEntry(path="/src/Foo.PY")
        assert obj.ext == "py"

    def test_extensionless_file_has_null_ext(self):
        obj = VFSEntry(path="/Makefile")
        assert obj.kind == "file"
        assert obj.ext is None

    def test_dotfile_has_null_ext(self):
        obj = VFSEntry(path="/.env")
        assert obj.kind == "file"
        assert obj.ext is None

    def test_dotfile_with_extension(self):
        obj = VFSEntry(path="/.eslintrc.json")
        assert obj.ext == "json"

    def test_directory_has_null_ext(self):
        obj = VFSEntry(path="/src")
        assert obj.kind == "directory"
        assert obj.ext is None

    def test_chunk_has_null_ext_even_if_name_has_dot(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/chunks/login")
        assert obj.kind == "chunk"
        assert obj.ext is None

    def test_version_has_null_ext(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/versions/3")
        assert obj.kind == "version"
        assert obj.ext is None

    def test_connection_has_null_ext_despite_py_suffix(self):
        """Connection paths end in a target like `/b.py` but are not files —
        the index must not pollute with non-file rows."""
        obj = VFSEntry(path="/.vfs/a.py/__meta__/edges/out/imports/b.py")
        assert obj.kind == "edge"
        assert obj.ext is None

    def test_api_has_null_ext(self):
        obj = VFSEntry(path="/.vfs/jira/__meta__/apis/ticket")
        assert obj.kind == "api"
        assert obj.ext is None

    def test_explicit_ext_preserved(self):
        obj = VFSEntry(path="/src/auth.py", ext="python")
        assert obj.ext == "python"

    def test_rederive_updates_ext_on_move(self):
        obj = VFSEntry(path="/src/auth.py")
        assert obj.ext == "py"
        obj.path = "/src/auth.ts"
        obj._rederive_path_fields()
        assert obj.ext == "ts"

    def test_rederive_clears_ext_on_move_to_extensionless(self):
        obj = VFSEntry(path="/src/auth.py")
        assert obj.ext == "py"
        obj.path = "/src/Makefile"
        obj._rederive_path_fields()
        assert obj.ext is None


# =========================================================================
# Parent path derivation
# =========================================================================


class TestName:
    def test_file(self):
        obj = VFSEntry(path="/src/auth.py")
        assert obj.name == "auth.py"

    def test_directory(self):
        obj = VFSEntry(path="/src")
        assert obj.name == "src"

    def test_root(self):
        obj = VFSEntry(path="/")
        assert obj.name == ""

    def test_chunk(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/chunks/login")
        assert obj.name == "login"

    def test_version(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/versions/3")
        assert obj.name == "3"

    def test_connection(self):
        obj = VFSEntry(path="/.vfs/a.py/__meta__/edges/out/imports/src/utils.py")
        assert obj.name == "utils.py"

    def test_api(self):
        obj = VFSEntry(path="/.vfs/jira/__meta__/apis/ticket")
        assert obj.name == "ticket"

    def test_explicit_name_preserved(self):
        obj = VFSEntry(path="/src/auth.py", name="custom")
        assert obj.name == "custom"


class TestParentPath:
    def test_file(self):
        obj = VFSEntry(path="/src/auth.py")
        assert obj.parent_path == "/src"

    def test_root_child(self):
        obj = VFSEntry(path="/src")
        assert obj.parent_path == "/"

    def test_root(self):
        obj = VFSEntry(path="/")
        assert obj.parent_path == "/"

    def test_chunk_parent_is_owning_file(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/chunks/login")
        assert obj.parent_path == "/.vfs/src/auth.py/__meta__/chunks"

    def test_edge_parent_uses_literal_projected_parent(self):
        obj = VFSEntry(path="/.vfs/a.py/__meta__/edges/out/imports/b.py")
        assert obj.parent_path == "/.vfs/a.py/__meta__/edges/out/imports"

    def test_explicit_parent_preserved(self):
        obj = VFSEntry(path="/src/auth.py", parent_path="/custom")
        assert obj.parent_path == "/custom"


# =========================================================================
# Edge decomposition
# =========================================================================


class TestEdgeDecomposition:
    def test_fields_extracted(self):
        obj = VFSEntry(path="/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py")
        assert obj.source_path == "/src/auth.py"
        assert obj.target_path == "/src/utils.py"
        assert obj.edge_type == "imports"

    def test_deep_target(self):
        obj = VFSEntry(path="/.vfs/a.py/__meta__/edges/out/calls/deep/nested/path.py")
        assert obj.target_path == "/deep/nested/path.py"

    def test_explicit_edge_fields_preserved(self):
        obj = VFSEntry(
            path="/.vfs/a.py/__meta__/edges/out/imports/b.py",
            source_path="/custom",
            target_path="/custom-target",
            edge_type="custom-type",
        )
        assert obj.source_path == "/custom"
        assert obj.target_path == "/custom-target"
        assert obj.edge_type == "custom-type"

    def test_non_edge_path_has_no_decomposition(self):
        obj = VFSEntry(path="/src/auth.py")
        assert obj.source_path is None
        assert obj.target_path is None
        assert obj.edge_type is None


# =========================================================================
# Content metrics
# =========================================================================


class TestContentMetrics:
    def test_content_with_text(self):
        obj = VFSEntry(path="/a.py", content="def login():\n    pass")
        assert obj.content_hash is not None
        assert obj.size_bytes == len(b"def login():\n    pass")
        assert obj.lines == 2
        assert obj.tokens == 0
        assert obj.lexical_tokens == VFSEntry._lexical_token_count(
            "def login():\n    pass",
        )

    def test_single_line_no_newline(self):
        obj = VFSEntry(path="/a.py", content="hello")
        assert obj.lines == 1

    def test_trailing_newline(self):
        obj = VFSEntry(path="/a.py", content="a\nb\n")
        assert obj.lines == 3

    def test_empty_string_content(self):
        obj = VFSEntry(path="/empty.txt", content="")
        assert obj.content_hash == hashlib.sha256(b"").hexdigest()
        assert obj.size_bytes == 0
        assert obj.lines == 0

    def test_none_content(self):
        obj = VFSEntry(path="/dir")
        assert obj.content is None
        assert obj.content_hash is None
        assert obj.size_bytes == 0
        assert obj.lines == 0

    def test_hash_recomputed_even_if_explicit(self):
        obj = VFSEntry(path="/a.py", content="hello", content_hash="bogus")
        assert obj.content_hash == hashlib.sha256(b"hello").hexdigest()

    def test_version_row_factory_uses_reconstructed_metadata(self):
        row = VFSEntry.create_version_row(
            file_path="/a.py",
            version_number=2,
            version_content="new",
            prev_content="old",
            created_by="auto",
        )
        assert row.kind == "version"
        assert row.is_snapshot is False
        assert row.content is None
        assert row.version_diff is not None
        assert row.content_hash == hashlib.sha256(b"new").hexdigest()
        assert row.size_bytes == len(b"new")
        assert row.lines == 1
        assert row.tokens == 0
        assert row.lexical_tokens == VFSEntry._lexical_token_count("new")

    def test_version_row_preserves_explicit_metadata(self):
        obj = VFSEntry(
            path="/.vfs/a.py/__meta__/versions/2",
            kind="version",
            content=None,
            version_diff="diff payload",
            content_hash="abc",
            size_bytes=123,
            lines=7,
            version_number=2,
            is_snapshot=False,
        )
        assert obj.content is None
        assert obj.version_diff == "diff payload"
        assert obj.content_hash == "abc"
        assert obj.size_bytes == 123
        assert obj.lines == 7


# =========================================================================
# Timestamps
# =========================================================================


class TestTimestamps:
    def test_auto_set(self):
        obj = VFSEntry(path="/a.py")
        assert obj.created_at is not None
        assert obj.updated_at is not None

    def test_created_at_equals_updated_at(self):
        obj = VFSEntry(path="/a.py")
        # Both set from the same `now` in the validator
        assert obj.created_at == obj.updated_at

    def test_explicit_created_at_preserved(self):
        from datetime import UTC, datetime

        ts = datetime(2020, 1, 1, tzinfo=UTC)
        obj = VFSEntry(path="/a.py", created_at=ts)
        assert obj.created_at == ts

    def test_deleted_at_defaults_to_none(self):
        obj = VFSEntry(path="/a.py")
        assert obj.deleted_at is None


# =========================================================================
# ID generation
# =========================================================================


class TestId:
    def test_auto_generated(self):
        obj = VFSEntry(path="/a.py")
        assert obj.id is not None
        assert len(obj.id) == 36  # UUID format

    def test_unique_across_instances(self):
        a = VFSEntry(path="/a.py")
        b = VFSEntry(path="/b.py")
        assert a.id != b.id

    def test_explicit_id_preserved(self):
        obj = VFSEntry(path="/a.py", id="custom-id")
        assert obj.id == "custom-id"


# =========================================================================
# Embedding
# =========================================================================


class TestEmbedding:
    def test_defaults_to_none(self):
        obj = VFSEntry(path="/a.py")
        assert obj.embedding is None

    def test_accepts_list(self):
        obj = VFSEntry(path="/a.py", embedding=Vector([0.1, 0.2, 0.3]))
        assert isinstance(obj.embedding, Vector)
        assert list(obj.embedding) == [0.1, 0.2, 0.3]

    def test_accepts_vector(self):
        vec = Vector([1.0, 2.0])
        obj = VFSEntry(path="/a.py", embedding=vec)
        assert obj.embedding is vec


# =========================================================================
# VFSEntry base vs minted table class
# =========================================================================


class TestBaseVsMinted:
    def test_base_is_not_a_table(self):
        assert not VFSEntry.model_config.get("table", False)

    def test_minted_is_a_table(self):
        table_class = _build_entry_table_class(table_name="vfs_entries")
        assert table_class.model_config.get("table", False)
        assert table_class.__tablename__ == "vfs_entries"

    def test_minted_table_name_is_configurable(self):
        table_class = _build_entry_table_class(table_name="acme_entries")
        assert table_class.__tablename__ == "acme_entries"

    def test_base_runs_field_validator(self):
        entry = VFSEntry(path="/src/auth.py", content="x")
        assert entry.kind == "file"
        assert entry.content_hash is not None


class TestContentMutation:
    def test_update_content_recomputes_lexical_tokens(self):
        obj = VFSEntry(path="/a.py", content="hello")
        original_lexical_tokens = obj.lexical_tokens
        obj.update_content("hello world from vfs")
        assert obj.lexical_tokens == VFSEntry._lexical_token_count(
            "hello world from vfs",
        )
        assert obj.lexical_tokens != original_lexical_tokens


# =========================================================================
# add_prefix / strip_prefix
# =========================================================================


class TestAddStripPrefix:
    def test_strip_prefix_rederives_fields(self):
        obj = VFSEntry(path="/data/sub/file.py", content="code")
        obj.strip_prefix("/data/sub")
        assert obj.path == "/file.py"
        assert obj.name == "file.py"
        assert obj.parent_path == "/"

    def test_add_prefix_rederives_fields(self):
        obj = VFSEntry(path="/file.py", content="code")
        obj.add_prefix("/data/sub")
        assert obj.path == "/data/sub/file.py"
        assert obj.name == "file.py"
        assert obj.parent_path == "/data/sub"

    def test_roundtrip(self):
        obj = VFSEntry(path="/mount/deep/file.py", content="x")
        obj.strip_prefix("/mount")
        assert obj.path == "/deep/file.py"
        obj.add_prefix("/mount")
        assert obj.path == "/mount/deep/file.py"

    def test_empty_prefix_is_noop(self):
        obj = VFSEntry(path="/file.py", content="x")
        obj.add_prefix("")
        assert obj.path == "/file.py"
        obj.strip_prefix("")
        assert obj.path == "/file.py"

    def test_strip_to_root(self):
        obj = VFSEntry(path="/data", content="x")
        obj.strip_prefix("/data")
        assert obj.path == "/"

    def test_returns_self(self):
        obj = VFSEntry(path="/a.py", content="x")
        assert obj.add_prefix("/m") is obj
        assert obj.strip_prefix("/m") is obj

    def test_chunk_kind_preserved(self):
        obj = VFSEntry(path="/.vfs/src/mod.py/__meta__/chunks/fn", content="def fn(): pass")
        obj.strip_prefix("/.vfs/src")
        assert obj.path == "/mod.py/__meta__/chunks/fn"
        assert obj.kind == "chunk"
        assert obj.parent_path == "/mod.py/__meta__/chunks"

    # -- add_prefix normalization ------------------------------------------

    def test_add_prefix_without_leading_slash(self):
        obj = VFSEntry(path="/test.py", content="x")
        obj.add_prefix("snhu")
        assert obj.path == "/snhu/test.py"

    def test_add_prefix_with_trailing_slash(self):
        obj = VFSEntry(path="/test.py", content="x")
        obj.add_prefix("/snhu/")
        assert obj.path == "/snhu/test.py"

    @pytest.mark.parametrize("prefix", ["snhu", "/snhu", "snhu/", "/snhu/"])
    def test_path_always_has_leading_slash_after_add_prefix(self, prefix):
        obj = VFSEntry(path="/file.py", content="x")
        obj.add_prefix(prefix)
        assert obj.path.startswith("/")
        assert obj.path == "/snhu/file.py"

    # -- strip_prefix safety -----------------------------------------------

    def test_strip_prefix_mismatch_raises(self):
        obj = VFSEntry(path="/other/file.py", content="x")
        with pytest.raises(ValueError, match="does not start with prefix"):
            obj.strip_prefix("/data")

    def test_strip_prefix_partial_segment_raises(self):
        obj = VFSEntry(path="/database/file.py", content="x")
        with pytest.raises(ValueError, match="does not start with prefix"):
            obj.strip_prefix("/data")

    def test_strip_prefix_normalizes_prefix(self):
        obj = VFSEntry(path="/snhu/test.py", content="x")
        obj.strip_prefix("snhu")
        assert obj.path == "/test.py"

    def test_path_always_has_leading_slash_after_strip_prefix(self):
        obj = VFSEntry(path="/mount/deep/file.py", content="x")
        obj.strip_prefix("/mount")
        assert obj.path.startswith("/")
        assert obj.path == "/deep/file.py"

    # -- _rederive_path_fields normalization --------------------------------

    def test_rederive_normalizes_path(self):
        obj = VFSEntry(path="/a.py", content="x")
        obj.path = "bad/path"  # bypass validator
        obj._rederive_path_fields()
        assert obj.path == "/bad/path"
        assert obj.name == "path"
        assert obj.parent_path == "/bad"

    # -- roundtrip with unnormalized prefix --------------------------------

    def test_roundtrip_unnormalized_prefix(self):
        obj = VFSEntry(path="/deep/file.py", content="x")
        obj.add_prefix("mount")
        assert obj.path == "/mount/deep/file.py"
        obj.strip_prefix("mount")
        assert obj.path == "/deep/file.py"


# DB round-trip
# =========================================================================


class TestDBRoundTrip:
    @pytest.fixture()
    def mint(self):
        """Mint a fresh table class and bound engine for each test."""
        table_class = _build_entry_table_class(table_name="vfs_entries")
        engine = create_engine("sqlite://")
        table_class.metadata.create_all(engine)
        return table_class, engine

    def test_insert_and_load(self, mint):
        table_class, engine = mint
        entry = VFSEntry(path="/src/auth.py", content="def login(): pass")
        expected_hash = entry.content_hash
        with Session(engine) as s:
            s.add(table_class(**entry.model_dump()))
            s.commit()

        with Session(engine) as s:
            loaded = s.exec(select(table_class).where(table_class.path == "/src/auth.py")).one()
            assert loaded.path == "/src/auth.py"
            assert loaded.kind == "file"
            assert loaded.parent_path == "/src"
            assert loaded.content == "def login(): pass"
            assert loaded.content_hash == expected_hash

    def test_embedding_round_trip(self, mint):
        table_class, engine = mint
        entry = VFSEntry(path="/a.py", embedding=Vector([0.1, 0.2, 0.3]))
        with Session(engine) as s:
            s.add(table_class(**entry.model_dump()))
            s.commit()

        with Session(engine) as s:
            loaded = s.exec(select(table_class).where(table_class.path == "/a.py")).one()
            assert isinstance(loaded.embedding, Vector)
            assert list(loaded.embedding) == [0.1, 0.2, 0.3]

    def test_edge_round_trip(self, mint):
        table_class, engine = mint
        entry = VFSEntry(path="/.vfs/a.py/__meta__/edges/out/imports/b.py")
        with Session(engine) as s:
            s.add(table_class(**entry.model_dump()))
            s.commit()

        with Session(engine) as s:
            loaded = s.exec(
                select(table_class).where(table_class.path == "/.vfs/a.py/__meta__/edges/out/imports/b.py")
            ).one()
            assert loaded.kind == "edge"
            assert loaded.source_path == "/a.py"
            assert loaded.target_path == "/b.py"
            assert loaded.edge_type == "imports"

    def test_native_embedding_uses_portable_round_trip_on_sqlite(self):
        """Native pgvector config falls back to JSON-text storage on non-Postgres dialects."""
        native = NativeEmbeddingConfig(dimension=3)
        table_class = _build_entry_table_class(table_name="vfs_entries", native_embedding=native)
        engine = create_engine("sqlite://")
        table_class.metadata.create_all(engine)
        entry = VFSEntry(path="/native.py", embedding=Vector([0.1, 0.2, 0.3]))
        with Session(engine) as s:
            s.add(table_class(**entry.model_dump()))
            s.commit()

        with Session(engine) as s:
            loaded = s.exec(select(table_class).where(table_class.path == "/native.py")).one()
            assert isinstance(loaded.embedding, Vector)
            assert loaded.embedding.dimension == 3
            assert list(loaded.embedding) == [0.1, 0.2, 0.3]


class TestPostgresVectorModelHelpers:
    def test_each_mint_call_returns_a_fresh_class(self):
        """Each filesystem instance gets its own minted class — no shared cache."""
        first = _build_entry_table_class(
            table_name="vfs_entries", native_embedding=NativeEmbeddingConfig(dimension=1536)
        )
        second = _build_entry_table_class(
            table_name="vfs_entries", native_embedding=NativeEmbeddingConfig(dimension=1536)
        )
        assert first is not second
        assert first.__table__ is not second.__table__

    def test_vector_spec_comes_from_model_declaration(self):
        native = NativeEmbeddingConfig(dimension=1536)
        table_class = _build_entry_table_class(table_name="vfs_entries", native_embedding=native)
        spec = postgres_vector_column_spec(table_class)
        assert spec.column_name == "embedding"
        assert spec.dimension == 1536
        assert spec.index_method == "hnsw"
        assert spec.operator_class == "vector_cosine_ops"

    def test_vector_spec_preserves_nondefault_metric_and_index_method(self):
        native = NativeEmbeddingConfig(
            dimension=1536,
            index_method="ivfflat",
            operator_class="vector_ip_ops",
        )
        table_class = _build_entry_table_class(table_name="vfs_entries", native_embedding=native)
        spec = postgres_vector_column_spec(table_class)
        assert spec.index_method == "ivfflat"
        assert spec.operator_class == "vector_ip_ops"
        assert spec.index_name == "ix_vfs_entries_embedding_vector_ip_ivfflat"


# =========================================================================
# plan_file_write
# =========================================================================


class TestPlanFileWrite:
    """Unit tests for VFSEntry.plan_file_write fast/slow path."""

    @staticmethod
    def _make_file(content: str, version_number: int) -> VFSEntry:
        """Build a file object with consistent hash/version state."""
        obj = VFSEntry(path="/test.txt", content=content)
        obj.version_number = version_number
        return obj

    def test_fast_path_skips_reconstruction(self):
        """When latest_version_hash matches file hash, chain_verified=True."""
        obj = self._make_file("hello", version_number=1)
        plan = obj.plan_file_write(
            "world",
            latest_version_hash=obj.content_hash,
        )
        assert plan.chain_verified is True
        assert plan.final_content == "world"
        assert plan.final_version_number == 2
        assert len(plan.version_rows) == 1
        assert plan.version_rows[0].created_by == "auto"

    def test_no_latest_hash_signals_unverified(self):
        """No latest_version_hash and no version_rows → chain_verified=False."""
        obj = self._make_file("hello", version_number=1)
        plan = obj.plan_file_write("world", latest_version_hash=None)
        assert plan.chain_verified is False

    def test_mismatched_latest_hash_signals_unverified(self):
        """Wrong latest_version_hash → chain_verified=False."""
        obj = self._make_file("hello", version_number=1)
        plan = obj.plan_file_write("world", latest_version_hash="wrong_hash")
        assert plan.chain_verified is False

    def test_same_content_returns_noop_plan(self):
        """Same content → no new version rows."""
        obj = self._make_file("hello", version_number=1)
        plan = obj.plan_file_write(
            "hello",
            latest_version_hash=obj.content_hash,
        )
        assert plan.chain_verified is True
        assert len(plan.version_rows) == 0
        assert plan.final_version_number == 1

    def test_version_number_zero_creates_initial_snapshot(self):
        """First write creates v1 snapshot regardless of hash args."""
        obj = self._make_file("hello", version_number=0)
        plan = obj.plan_file_write("hello")
        assert plan.final_version_number == 1
        assert len(plan.version_rows) == 1
        assert plan.version_rows[0].is_snapshot is True

    def test_external_edit_detected_by_hash_mismatch(self):
        """File hash ≠ stored hash → external snapshot, even with latest_version_hash."""
        obj = self._make_file("original", version_number=1)
        # Simulate external edit: change content without updating hash
        obj.content = "tampered"
        plan = obj.plan_file_write(
            "new_content",
            latest_version_hash=obj.content_hash,  # matches stored, not observed
        )
        assert plan.chain_verified is True  # external path handles it directly
        assert plan.final_version_number == 3  # external=2, new=3
        external_row = plan.version_rows[0]
        assert external_row.created_by == "external"
        assert external_row.is_snapshot is True


# ==================================================================
# Edge case coverage — _stored_version_payload
# ==================================================================


class TestStoredVersionPayload:
    def test_non_version_raises(self):
        obj = VFSEntry(path="/a.py", kind="file", content="x")
        with pytest.raises(ValueError, match="non-version object"):
            obj._stored_version_payload()

    def test_missing_payload_raises(self):
        obj = VFSEntry(
            path="/a.py@1",
            kind="version",
            content=None,
            version_diff=None,
            is_snapshot=False,
        )
        with pytest.raises(ValueError, match="missing stored payload"):
            obj._stored_version_payload()


# ==================================================================
# Edge case coverage — _reconstruct_file_version
# ==================================================================


class TestReconstructFileVersion:
    def test_missing_target_version_raises(self):
        with pytest.raises(ValueError, match="Missing version row for v2"):
            VFSEntry._reconstruct_file_version([], target_version=2)

    def test_missing_snapshot_raises(self):
        row = VFSEntry(
            path="/a.py@1",
            kind="version",
            content=None,
            version_diff="some diff",
            version_number=1,
            is_snapshot=False,
        )
        with pytest.raises(ValueError, match="Missing snapshot"):
            VFSEntry._reconstruct_file_version([row], target_version=1)

    def test_missing_intermediate_version_raises(self):
        snapshot = VFSEntry(
            path="/a.py@1",
            kind="version",
            content="base",
            version_number=1,
            is_snapshot=True,
        )
        # v2 is missing, asking for v3
        v3 = VFSEntry(
            path="/a.py@3",
            kind="version",
            content=None,
            version_diff="diff",
            version_number=3,
            is_snapshot=False,
        )
        with pytest.raises(ValueError, match="Missing version row for v2"):
            VFSEntry._reconstruct_file_version([snapshot, v3], target_version=3)

    def test_hash_mismatch_raises(self):
        snapshot = VFSEntry(
            path="/a.py@1",
            kind="version",
            content="base content",
            version_number=1,
            is_snapshot=True,
            content_hash="wrong_hash",
        )
        with pytest.raises(ValueError, match="Hash mismatch"):
            VFSEntry._reconstruct_file_version([snapshot], target_version=1)


# ==================================================================
# Edge case coverage — plan_file_write and update_content
# ==================================================================


class TestPlanFileWriteEdgeCases:
    def test_directory_raises(self):
        obj = VFSEntry(path="/mydir", kind="directory")
        with pytest.raises(ValueError, match="Version planning only applies to files"):
            obj.plan_file_write("content")


class TestUpdateContentEdgeCases:
    def test_directory_raises(self):
        obj = VFSEntry(path="/mydir", kind="directory")
        with pytest.raises(ValueError, match="Cannot set content on a directory"):
            obj.update_content("x")


# ==================================================================
# Edge case coverage — model validator
# ==================================================================


class TestValidatorEdgeCases:
    def test_null_bytes_in_version_diff_rejected(self):
        with pytest.raises(ValueError, match="version_diff contains null bytes"):
            VFSEntry(
                path="/a.py@1",
                kind="version",
                version_diff="has\x00null",
                version_number=1,
                is_snapshot=False,
            )

    def test_both_content_and_version_diff_rejected(self):
        with pytest.raises(ValueError, match="must not set both content and version_diff"):
            VFSEntry(
                path="/a.py@1",
                kind="version",
                content="text",
                version_diff="diff",
                version_number=1,
                is_snapshot=False,
            )

    def test_version_with_explicit_content_hash(self):
        h = hashlib.sha256(b"hello").hexdigest()
        obj = VFSEntry(
            path="/a.py@1",
            kind="version",
            content="hello",
            version_number=1,
            is_snapshot=True,
            content_hash=h,
        )
        assert obj.content_hash == h


# ==================================================================
# Coverage: models.py line 479 — non-string path returns data
# ==================================================================


class TestNonStringPath:
    def test_non_string_path_skips_normalization(self):
        """Line 479: when path is not a string, validator returns early.

        The before-validator returns without normalizing, then Pydantic
        field validation rejects the non-string path.
        """
        with pytest.raises((ValueError, Exception)):
            VFSEntry.model_validate({"path": 42, "content": "stuff"})


# ==================================================================
# Coverage: models.py lines 523-524 — content null bytes rejected
# ==================================================================


class TestContentNullBytes:
    def test_null_bytes_in_content_rejected(self):
        """Lines 523-524: content containing null bytes raises ValueError."""
        with pytest.raises(ValueError, match="Content contains null bytes"):
            VFSEntry(path="/a.py", content="has\x00null")


# ==================================================================
# Coverage: models.py line 314 — reconstruct when hash is None
# ==================================================================


class TestReconstructVersionHashNone:
    def test_hash_none_skips_verification(self):
        """Line 314: when content_hash is None, hash check is skipped."""
        snapshot = VFSEntry(
            path="/a.py@1",
            kind="version",
            version_number=1,
            is_snapshot=True,
            content="hello world",
        )
        # Force content_hash to None after construction
        object.__setattr__(snapshot, "content_hash", None)
        result = VFSEntry._reconstruct_file_version([snapshot], target_version=1)
        assert result == "hello world"


# ==================================================================
# Coverage: models.py line 55 — finish_init=False skips validation
# ==================================================================


class TestFinishInitFalse:
    def test_orm_load_skips_validation(self):
        """Line 55: when finish_init is False, ValidatedSQLModel.__init__ returns early.

        With finish_init=False the custom validator code is skipped
        (SQLModel's ORM-load path). The object is created but attributes
        may not be set since validation was bypassed.
        """
        from sqlmodel._compat import finish_init

        token = finish_init.set(False)
        try:
            # With finish_init=False, the validated init returns early.
            # This simulates what happens during ORM loads.
            obj = VFSEntry()  # ty: ignore[missing-argument]
            # Object exists but path was not set (no validation ran)
            assert obj is not None
        finally:
            finish_init.reset(token)


# ==================================================================
# Additional helper/error coverage
# ==================================================================


class TestModelHelperErrors:
    def test_unknown_kind_rejected(self):
        with pytest.raises(ValueError, match="Unknown kind"):
            VFSEntry(path="/mystery", kind="mystery")

    def test_version_diff_null_bytes_rejected(self):
        with pytest.raises(ValueError, match="version_diff contains null bytes"):
            VFSEntry(
                path="/.vfs/a.py/__meta__/versions/1",
                kind="version",
                version_diff="bad\x00diff",
            )

    def test_version_rows_cannot_set_both_snapshot_and_diff(self):
        with pytest.raises(ValueError, match="must not set both content and version_diff"):
            VFSEntry(
                path="/.vfs/a.py/__meta__/versions/1",
                kind="version",
                content="snapshot",
                version_diff="delta",
            )

    def test_resolve_embedding_vector_type_requires_embedding_column(self):
        with pytest.raises(ValueError, match="does not declare an 'embedding' column"):
            resolve_embedding_vector_type(VFSEntry)

    def test_resolve_embedding_vector_type_requires_vector_type(self):
        class PlainEmbeddingModel(SQLModel, table=True):
            __tablename__ = "plain_embedding_model_coverage"

            id: int | None = Field(default=None, primary_key=True)
            embedding: str | None = None

        with pytest.raises(ValueError, match="must use VectorType"):
            resolve_embedding_vector_type(PlainEmbeddingModel)

    def test_postgres_vector_column_spec_requires_native_pgvector_model(self):
        """A minted class without native_embedding has a portable VectorType, not postgres_native."""
        table_class = _build_entry_table_class(table_name="vfs_entries")
        with pytest.raises(ValueError, match="postgres_native=True"):
            postgres_vector_column_spec(table_class)

    def test_resolve_embedding_vector_type_returns_vector_metadata(self):
        class NativeEmbeddingModel(SQLModel, table=True):
            __tablename__ = "native_embedding_model_coverage"

            id: int | None = Field(default=None, primary_key=True)
            embedding: Vector | None = Field(default=None, sa_type=VectorType(dimension=4))

        vector_type = resolve_embedding_vector_type(NativeEmbeddingModel)
        assert isinstance(vector_type, VectorType)
        assert vector_type.dimension == 4
