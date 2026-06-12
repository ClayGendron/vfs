"""Tests for the pure-Pydantic domain models: Entry, Observation, Match."""

from __future__ import annotations

import json
from types import UnionType
from typing import Union, get_args, get_origin

import pytest
from pydantic import ValidationError

from vfs.models2 import (
    OBSERVATION_MIRROR_FIELDS,
    OBSERVATION_QUERY_FIELDS,
    Entry,
    Match,
    Observation,
)
from vfs.paths import VFSPath, chunk_path, edge_out_path, version_path

# ---------------------------------------------------------------------------
# model_fields_set — the repo-wide explicitness contract
# ---------------------------------------------------------------------------


class TestModelFieldsSet:
    """Validator assignments count as "set" — pin the documented contract."""

    def test_records_caller_keys_and_validator_assignments(self) -> None:
        entry = Entry(path="/docs/a.md", content="hello")
        assert entry.model_fields_set == {
            # caller keys
            "path",
            "content",
            # before-validator identity injections
            "kind",
            "name",
            # after-validator derivations
            "ext",
            "content_hash",
            "size_bytes",
            "lines",
            "lexical_tokens",
            "created_at",
            "updated_at",
        }

    def test_untouched_fields_distinguish_explicit_none_from_unset(self) -> None:
        unset = Entry(path="/docs/a.md")
        explicit = Entry(path="/docs/a.md", description=None)
        assert "description" not in unset.model_fields_set
        assert "description" in explicit.model_fields_set

    def test_validator_assignment_of_none_counts_as_set(self) -> None:
        directory = Entry(path="/docs")
        assert directory.content is None
        assert "content" in directory.model_fields_set


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


class TestConstructionValidation:
    def test_null_bytes_in_content_rejected(self) -> None:
        with pytest.raises(ValidationError, match="null bytes"):
            Entry(path="/a.md", content="a\x00b")

    def test_null_bytes_in_version_diff_rejected(self) -> None:
        with pytest.raises(ValidationError, match="null bytes"):
            Entry(path=version_path(VFSPath("/a.md"), 2), version_diff="a\x00b")

    def test_non_mapping_input_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Entry.model_validate("not a mapping")

    def test_path_is_required(self) -> None:
        with pytest.raises(ValidationError):
            Entry(content="x")  # type: ignore[call-arg]

    def test_version_row_rejects_content_and_diff_together(self) -> None:
        with pytest.raises(ValidationError, match="must not set both"):
            Entry(path=version_path(VFSPath("/a.md"), 1), content="x", version_diff="y")


# ---------------------------------------------------------------------------
# Derived relationship projections
# ---------------------------------------------------------------------------


class TestDerivedProjections:
    def test_file_projections(self) -> None:
        file = Entry(path="/docs/a.md", content="x")
        assert file.parent_dir == "/docs"
        assert isinstance(file.parent_dir, VFSPath)
        assert file.parent_file is None  # files own chunks; nothing owns them
        assert file.source_file is None
        assert file.target_file is None

    def test_edge_identity_and_endpoints_derive_from_path(self) -> None:
        edge = Entry(path=edge_out_path(VFSPath("/a.md"), VFSPath("/b.md"), "references"))
        assert edge.kind == "edge"
        assert edge.edge_type == "references"
        assert edge.source_file == "/a.md"
        assert edge.target_file == "/b.md"
        assert edge.parent_file == "/a.md"

    def test_explicit_edge_type_is_preserved(self) -> None:
        edge = Entry(
            path=edge_out_path(VFSPath("/a.md"), VFSPath("/b.md"), "references"),
            edge_type="custom",
        )
        assert edge.edge_type == "custom"


# ---------------------------------------------------------------------------
# Entry / Observation drift
# ---------------------------------------------------------------------------


def _inner_types(annotation: object) -> set[object]:
    """The annotation's non-None union members; the annotation itself when not a union."""
    if get_origin(annotation) in {Union, UnionType}:
        return {arg for arg in get_args(annotation) if arg is not type(None)}
    return {annotation}


class TestObservationMirrorsEntry:
    def test_partition_is_total_and_disjoint(self) -> None:
        assert set(Observation.model_fields) == OBSERVATION_MIRROR_FIELDS | OBSERVATION_QUERY_FIELDS
        assert not (OBSERVATION_MIRROR_FIELDS & OBSERVATION_QUERY_FIELDS)

    def test_every_mirror_matches_its_entry_field_type(self) -> None:
        for name in sorted(OBSERVATION_MIRROR_FIELDS):
            assert name in Entry.model_fields, f"Observation.{name} mirrors no Entry field"
            obs = _inner_types(Observation.model_fields[name].annotation)
            entry = _inner_types(Entry.model_fields[name].annotation)
            assert obs == entry, f"type drift on {name!r}: Observation {obs} != Entry {entry}"

    def test_query_fields_never_exist_on_entry(self) -> None:
        for name in sorted(OBSERVATION_QUERY_FIELDS):
            assert name not in Entry.model_fields, f"query field {name!r} leaked onto Entry"


# ---------------------------------------------------------------------------
# Entry.to_observation — the projection seam
# ---------------------------------------------------------------------------


class TestEntryToObservation:
    def test_projection_covers_every_mirror_field(self) -> None:
        entry = Entry(
            path="/docs/a.md",
            content="hello",
            description="greeting",
            mime_type="text/markdown",
            version_number=3,
        )
        obs = entry.to_observation()
        for name in OBSERVATION_MIRROR_FIELDS:
            entry_value = getattr(entry, name)
            assert entry_value is not None, f"test setup must populate {name!r}"
            assert getattr(obs, name) == entry_value, f"mirror {name!r} not projected"

    def test_query_fields_come_from_the_operation(self) -> None:
        entry = Entry(path="/a.md", content="x")
        obs = entry.to_observation(
            score=0.5,
            status="created",
            matches=[Match(start=1, end=1, match=1)],
        )
        assert obs.score == 0.5
        assert obs.status == "created"
        assert obs.matches == [Match(start=1, end=1, match=1)]

    def test_no_query_facts_unless_supplied(self) -> None:
        obs = Entry(path="/a.md", content="x").to_observation()
        assert obs.score is None
        assert obs.status is None
        assert obs.matches is None


# ---------------------------------------------------------------------------
# Mount rebasing — copy-returning, never in place
# ---------------------------------------------------------------------------


class TestMountRebasing:
    def test_entry_with_mount_returns_rebased_copy(self) -> None:
        entry = Entry(path="/docs/a.md", content="x")
        rebased = entry.with_mount("/data")
        assert rebased.path == "/data/docs/a.md"
        assert isinstance(rebased.path, VFSPath)
        assert rebased.name == "a.md"
        assert rebased.content_hash == entry.content_hash
        assert entry.path == "/docs/a.md"  # original untouched

    def test_entry_without_mount_inverts_with_mount(self) -> None:
        entry = Entry(path="/data/docs/a.md", content="x")
        local = entry.without_mount("/data")
        assert local.path == "/docs/a.md"
        assert local.with_mount("/data").path == entry.path

    def test_root_entry_takes_the_mount_leaf_name(self) -> None:
        root = Entry(path="/")
        mounted = root.with_mount("/data")
        assert mounted.path == "/data"
        assert mounted.name == "data"
        assert mounted.without_mount("/data").name == root.name

    def test_non_boundary_prefix_is_rejected(self) -> None:
        entry = Entry(path="/mnt/foobar/x.md", content="x")
        with pytest.raises(ValueError, match="not within mount"):
            entry.without_mount("/mnt/foo")

    def test_observation_rebases_as_frozen_copy(self) -> None:
        obs = Observation(path="/docs/a.md", score=0.5)
        rebased = obs.with_mount("/data")
        assert rebased.path == "/data/docs/a.md"
        assert rebased.score == 0.5
        assert obs.path == "/docs/a.md"
        assert rebased.without_mount("/data") == obs


# ---------------------------------------------------------------------------
# Entry.with_content — content replacement, copy-returning
# ---------------------------------------------------------------------------


class TestWithContent:
    def test_returns_refreshed_copy(self) -> None:
        entry = Entry(path="/docs/a.md", content="old", chunked=True, encoded=True)
        updated = entry.with_content("new content")
        assert updated.content == "new content"
        assert updated.content_hash != entry.content_hash
        assert updated.size_bytes == len(b"new content")
        assert updated.version_diff is None
        assert updated.chunked is False  # new content must be re-indexed
        assert updated.encoded is False
        assert entry.content == "old"  # original untouched
        assert entry.chunked is True

    def test_metrics_match_fresh_construction(self) -> None:
        updated = Entry(path="/a.md", content="seed").with_content("hello\nworld")
        fresh = Entry(path="/a.md", content="hello\nworld")
        for field in ("content_hash", "size_bytes", "lines", "lexical_tokens"):
            assert getattr(updated, field) == getattr(fresh, field), field

    def test_directory_rejected(self) -> None:
        with pytest.raises(ValueError, match="Cannot set content on a directory"):
            Entry(path="/docs").with_content("x")

    def test_null_bytes_rejected(self) -> None:
        entry = Entry(path="/a.md", content="ok")
        with pytest.raises(ValueError, match="null bytes"):
            entry.with_content("bad\x00byte")


# ---------------------------------------------------------------------------
# Versioning — create_version_row, with_version, reconstruction
# ---------------------------------------------------------------------------


class TestVersioning:
    def test_v1_row_is_a_snapshot(self) -> None:
        row = Entry.create_version_row(
            file_path="/docs/a.md",
            version_number=1,
            version_content="hello",
            prev_content=None,
            created_by="auto",
            force_snapshot=True,
        )
        assert row.kind == "version"
        assert row.is_snapshot is True
        assert row.content == "hello"
        assert row.version_diff is None
        assert row.name == "1"
        assert row.path.parent_file == "/docs/a.md"

    def test_diff_row_keeps_full_content_metrics(self) -> None:
        row = Entry.create_version_row(
            file_path="/docs/a.md",
            version_number=2,
            version_content="hello\nworld",
            prev_content="hello",
            created_by="auto",
        )
        assert row.is_snapshot is False
        assert row.content is None  # diff rows store no snapshot text
        assert row.version_diff
        # metrics describe the full version content, not the stored diff
        full_hash, full_size, full_lines = Entry._content_metadata("hello\nworld")
        assert row.content_hash == full_hash
        assert row.size_bytes == full_size
        assert row.lines == full_lines

    def test_reconstruction_walks_snapshot_plus_diffs(self) -> None:
        contents = ["one", "one\ntwo", "one\ntwo\nthree"]
        rows = [
            Entry.create_version_row(
                file_path="/a.md",
                version_number=n + 1,
                version_content=contents[n],
                prev_content=contents[n - 1] if n else None,
                created_by="auto",
            )
            for n in range(3)
        ]
        assert Entry._reconstruct_file_version(rows, 3) == "one\ntwo\nthree"
        assert Entry._reconstruct_file_version(rows, 2) == "one\ntwo"

    def test_reconstruction_detects_missing_rows(self) -> None:
        v1 = Entry.create_version_row(
            file_path="/a.md",
            version_number=1,
            version_content="one",
            prev_content=None,
            created_by="auto",
        )
        with pytest.raises(ValueError, match="Missing version row"):
            Entry._reconstruct_file_version([v1], 2)

    def test_with_version_on_file_keeps_path(self) -> None:
        file = Entry(path="/a.md", content="x")
        bumped = file.with_version(4)
        assert bumped.version_number == 4
        assert bumped.path == file.path
        assert file.version_number is None  # original untouched

    def test_with_version_rebuilds_version_path_and_name(self) -> None:
        v1 = Entry.create_version_row(
            file_path="/a.md",
            version_number=1,
            version_content="x",
            prev_content=None,
            created_by="auto",
        )
        v2 = v1.with_version(2)
        assert v2.path == version_path(VFSPath("/a.md"), 2)
        assert v2.name == "2"
        assert v1.name == "1"  # original untouched

    def test_with_version_moves_chunk_keeping_leaf(self) -> None:
        chunk = Entry(path=chunk_path(VFSPath("/a.md"), "10_42", 1), content="seg")
        moved = chunk.with_version(2)
        assert moved.path == chunk_path(VFSPath("/a.md"), "10_42", 2)
        assert moved.name == "10_42"
        assert moved.version_number == 2

    def test_with_version_rejects_other_kinds(self) -> None:
        with pytest.raises(ValueError, match="applies only to"):
            Entry(path="/docs").with_version(2)

    def test_with_version_requires_an_owning_file(self) -> None:
        rootless = Entry(path="/a.md", kind="version")  # forced kind, plain file path
        with pytest.raises(ValueError, match="no owning file"):
            rootless.with_version(2)

    def test_stored_payload_requires_version_kind(self) -> None:
        with pytest.raises(ValueError, match="non-version"):
            Entry(path="/a.md", content="x")._stored_version_payload()

    def test_stored_payload_must_exist(self) -> None:
        hollow = Entry(path=version_path(VFSPath("/a.md"), 1), is_snapshot=True)
        with pytest.raises(ValueError, match="missing stored payload"):
            hollow._stored_version_payload()

    def test_reconstruction_requires_a_snapshot(self) -> None:
        diff_only = Entry.create_version_row(
            file_path="/a.md",
            version_number=2,
            version_content="two",
            prev_content="one",
            created_by="auto",
        )
        with pytest.raises(ValueError, match="Missing snapshot"):
            Entry._reconstruct_file_version([diff_only], 2)

    def test_reconstruction_detects_gap_in_diff_chain(self) -> None:
        v1 = Entry.create_version_row(
            file_path="/a.md",
            version_number=1,
            version_content="one",
            prev_content=None,
            created_by="auto",
        )
        v3 = Entry.create_version_row(
            file_path="/a.md",
            version_number=3,
            version_content="three",
            prev_content="two",
            created_by="auto",
        )
        with pytest.raises(ValueError, match="Missing version row for v2"):
            Entry._reconstruct_file_version([v1, v3], 3)

    def test_reconstruction_verifies_content_hash(self) -> None:
        v1 = Entry.create_version_row(
            file_path="/a.md",
            version_number=1,
            version_content="one",
            prev_content=None,
            created_by="auto",
        )
        tampered = v1.model_copy(update={"content_hash": "0" * 64})
        with pytest.raises(ValueError, match="Hash mismatch"):
            Entry._reconstruct_file_version([tampered], 1)


# ---------------------------------------------------------------------------
# Chunking — pure derivation of chunk entries
# ---------------------------------------------------------------------------


class TestChunking:
    def test_small_file_yields_single_whole_chunk(self) -> None:
        file = Entry(path="/docs/a.md", content="hello\nworld", owner_id="u1")
        chunks = file.chunk()
        assert len(chunks) == 1
        (c,) = chunks
        assert c.kind == "chunk"
        assert c.content == "hello\nworld"
        assert (c.line_start, c.line_end) == (1, 2)
        assert c.name == "1_2"
        assert c.path == chunk_path(file.path, "1_2", 1)
        assert c.version_number == 1  # file had no version yet
        assert c.owner_id == "u1"
        assert c.parent_file == "/docs/a.md"

    def test_chunk_is_pure_pipeline_owns_the_flag(self) -> None:
        file = Entry(path="/a.md", content="hello world")
        file.chunk()
        assert file.chunked is False  # marking chunked is the pipeline's job

    def test_sub_gram_content_produces_no_chunks(self) -> None:
        assert Entry(path="/a.md", content="hi").chunk() == []

    def test_file_version_flows_into_chunk_paths(self) -> None:
        file = Entry(path="/a.md", content="some content", version_number=3)
        (c,) = file.chunk()
        assert c.path == chunk_path(file.path, "1_1", 3)
        assert c.version_number == 3

    def test_colliding_line_ranges_get_offset_suffix(self) -> None:
        file = Entry(path="/big.txt", content="x" * 5000)  # one line, three slices
        chunks = file.chunk()
        assert len(chunks) == 3
        names = [c.name for c in chunks]
        assert len(set(names)) == len(names)  # disambiguated
        assert all(n.startswith("1_1@") for n in names)
        assert sum(len(c.content or "") for c in chunks) == 5000

    def test_non_file_rejected(self) -> None:
        with pytest.raises(ValueError, match="applies only to files"):
            Entry(path="/docs").chunk()

    def test_notebooks_split_by_cell_source(self) -> None:
        notebook = json.dumps(
            {
                "cells": [
                    {"cell_type": "code", "source": ["print('hello')\n", "print('world')\n"]},
                    {"cell_type": "markdown", "source": ["# Title\n"]},
                ],
                "metadata": {},
                "nbformat": 4,
            },
        )
        chunks = Entry(path="/nb.ipynb", content=notebook).chunk()
        assert chunks
        joined = "\n".join(c.content or "" for c in chunks)
        assert "print('hello')" in joined
        assert '"cells"' not in joined  # cell sources, never the raw JSON

    def test_unfindable_duplicate_text_falls_back_to_cursor_offset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two identical pieces over one occurrence: the second find() misses
        # and the cursor stands in as the disambiguating offset.
        monkeypatch.setattr(Entry, "split_content", staticmethod(lambda content, ext: [("ab", 1, 1), ("ab", 1, 1)]))
        chunks = Entry(path="/a.md", content="ab").chunk()
        assert [c.name for c in chunks] == ["1_1@0", "1_1@1"]


# ---------------------------------------------------------------------------
# Observation behavior
# ---------------------------------------------------------------------------


class TestObservation:
    def test_frozen(self) -> None:
        obs = Observation(path="/a.md")
        with pytest.raises(ValidationError):
            obs.score = 1.0  # type: ignore[misc]

    def test_path_is_branded_and_canonical(self) -> None:
        obs = Observation(path="docs/../a.md")
        assert isinstance(obs.path, VFSPath)
        assert obs.path == "/a.md"
        assert obs.path.name == "a.md"

    def test_match_regions_carry_their_own_text(self) -> None:
        chunk_hit = Match(start=10, end=42, content="def login(): ...", score=0.91)
        grep_hit = Match(start=3, end=7, match=5, content="retry()")
        obs = Observation(path="/src/auth.py", matches=[chunk_hit, grep_hit], score=0.91)
        assert obs.content is None  # the file's own content was never fetched
        assert obs.matches is not None
        assert obs.matches[0].match is None  # whole-region hit (glean chunk)
        assert obs.matches[0].score == 0.91  # per-region relevance
        assert obs.matches[1].match == 5  # grep hit line
        assert obs.matches[1].score is None  # grep rows carry no relevance
        assert [m.content for m in obs.matches] == ["def login(): ...", "retry()"]
