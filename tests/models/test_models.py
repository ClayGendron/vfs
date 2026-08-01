"""Tests for the pure-Pydantic domain models: Entry, Chunk, Version, Edge, Observation."""

from __future__ import annotations

import hashlib
import json
from types import UnionType
from typing import Union, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from vfs.models import (
    ENTRY_OWNED_MIRRORS,
    OBSERVATION_MIRROR_FIELDS,
    OBSERVATION_MIRROR_OWNERS,
    OBSERVATION_QUERY_FIELDS,
    Chunk,
    Edge,
    Entry,
    Match,
    Observation,
    Version,
)
from vfs.paths import Path, skill_path, tool_path

# ---------------------------------------------------------------------------
# model_fields_set — the repo-wide explicitness contract
# ---------------------------------------------------------------------------


class TestModelFieldsSet:
    """Validator assignments count as "set" — pin the documented contract."""

    def test_records_caller_keys_and_validator_assignments(self) -> None:
        entry = Entry(path=Path("/docs/a.md"), content="hello")
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
            "created_at",
            "updated_at",
        }

    def test_untouched_fields_distinguish_explicit_none_from_unset(self) -> None:
        unset = Entry(path=Path("/docs/a.md"))
        explicit = Entry(path=Path("/docs/a.md"), mime_type=None)
        assert "mime_type" not in unset.model_fields_set
        assert "mime_type" in explicit.model_fields_set

    def test_validator_assignment_of_none_counts_as_set(self) -> None:
        directory = Entry(path=Path("/docs"))
        assert directory.content is None
        assert "content" in directory.model_fields_set


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


class TestConstructionValidation:
    def test_null_bytes_in_content_rejected(self) -> None:
        with pytest.raises(ValidationError, match="null bytes"):
            Entry(path=Path("/a.md"), content="a\x00b")

    def test_empty_name_rejected_for_non_root(self) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Entry(path=Path("/src/auth.py"), name="")

    def test_name_default_does_not_leak_empty(self) -> None:
        assert Entry(path=Path("/src/auth.py")).name == "auth.py"
        assert Entry(path=Path("/")).name == ""

    def test_non_mapping_input_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Entry.model_validate("not a mapping")

    def test_path_is_required(self) -> None:
        with pytest.raises(ValidationError):
            Entry(content="x")  # ty: ignore[missing-argument]

    def test_kind_vocabulary_is_file_or_directory_only(self) -> None:
        for retired in ("chunk", "version", "edge", "tool", "skill"):
            with pytest.raises(ValidationError, match="kind"):
                Entry(path=Path("/x"), kind=retired)  # ty: ignore[invalid-argument-type]

    def test_metadata_fields_left_the_model(self) -> None:
        dropped = {
            "version_diff",
            "version_number",
            "is_snapshot",
            "created_by",
            "line_start",
            "line_end",
            "edge_type",
            "edge_weight",
            "edge_distance",
            "embedding",
        }
        assert not dropped & set(Entry.model_fields)
        assert set(Entry.model_computed_fields) == {"parent_dir"}

    def test_parent_dir_is_the_containing_directory(self) -> None:
        assert Entry(path=Path("/a/b.txt"), content="x").parent_dir == Path("/a")
        assert Entry(path=Path("/top.txt"), content="x").parent_dir == Path("/")

    def test_tool_and_skill_units_are_plain_directories(self) -> None:
        for path in (tool_path("clone-repo"), skill_path("pdf-processing")):
            entry = Entry(path=path)
            assert entry.kind == "directory"
            assert entry.content is None
            assert entry.ext is None

    def test_with_content_rejected_on_a_unit_directory(self) -> None:
        with pytest.raises(ValueError, match="Cannot set content on a directory"):
            Entry(path=tool_path("clone-repo")).with_content("x")

    def test_directory_with_dotted_name_carries_its_ext(self) -> None:
        entry = Entry(path=Path("/a/foo.bar"), kind="directory")
        assert entry.kind == "directory"
        assert entry.ext == "bar"
        assert entry.content is None

    def test_ext_always_derives_from_the_path(self) -> None:
        # The stored column must agree with extract_extension on every
        # row — the glob ext pushdowns are sound only under that law.
        assert Entry(path=Path("/a/b.txt"), content="x", ext="png").ext == "txt"
        assert Entry(path=Path("/notes/journal"), ext="md").ext is None


# ---------------------------------------------------------------------------
# Authoring intent — explicit content is never silently dropped
# ---------------------------------------------------------------------------


class TestAuthoringIntent:
    """Content is a statement of kind; the path heuristic only decides absence."""

    def test_content_forces_file_over_extensionless_guess(self) -> None:
        entry = Entry(path=Path("/notes/journal"), content="hello world")
        assert entry.kind == "file"
        assert entry.content == "hello world"
        assert entry.size_bytes == len(b"hello world")
        assert entry.lines == 1

    def test_heuristic_still_owns_absence(self) -> None:
        inferred_dir = Entry(path=Path("/notes/journal"))
        assert inferred_dir.kind == "directory"
        assert inferred_dir.content is None
        assert Entry(path=Path("/notes/todo")).kind == "file"

    def test_content_reclassifies_meta_scope_paths_like_ordinary_ones(self) -> None:
        # Trash-side paths are ordinary paths in the meta scope: the name
        # lottery reclassifies under content exactly as it would anywhere.
        entry = Entry(path=Path("/.vfs/trash/bucket"), content="x")
        assert entry.kind == "file"
        assert entry.content == "x"

    def test_explicit_directory_with_content_raises(self) -> None:
        with pytest.raises(ValidationError, match="carries no content"):
            Entry(path=Path("/notes/journal"), kind="directory", content="x")

    def test_empty_string_content_is_content(self) -> None:
        entry = Entry(path=Path("/notes/journal"), content="")
        assert entry.kind == "file"
        assert entry.content == ""
        with pytest.raises(ValidationError, match="carries no content"):
            Entry(path=Path("/notes/journal"), kind="directory", content="")

    def test_root_never_carries_content(self) -> None:
        with pytest.raises(ValidationError, match="'/' carries no content"):
            Entry(path=Path("/"), content="hello")
        with pytest.raises(ValidationError, match="'/' carries no content"):
            Entry(path=Path("/"), kind="file", content="hello")
        with pytest.raises(ValidationError, match="'/' carries no content"):
            Entry(path=Path("/"), content="")

    def test_root_is_always_a_directory(self) -> None:
        with pytest.raises(ValidationError, match="always a directory"):
            Entry(path=Path("/"), kind="file")
        root = Entry(path=Path("/"))
        assert root.kind == "directory"
        assert root.content is None

    def test_reserved_directories_refuse_content(self) -> None:
        # Structural spots are never the name lottery: content aimed at them
        # is a caller error, not a file in disguise.
        for path in (
            Path("/.vfs"),
            Path("/.agents"),
            tool_path("clone-repo"),
            skill_path("pdf-processing"),
        ):
            with pytest.raises(ValidationError, match="structurally a directory"):
                Entry(path=path, content="x")

    def test_unhashable_kind_is_a_clean_validation_error(self) -> None:
        for bad_kind in (["directory"], {"directory": 1}):
            with pytest.raises(ValidationError, match="kind"):
                Entry.model_validate({"path": "/x", "kind": bad_kind, "content": "x"})
            with pytest.raises(ValidationError, match="kind"):
                Entry.model_validate({"path": "/x", "kind": bad_kind})

    def test_explicit_none_content_is_not_a_conflict(self) -> None:
        entry = Entry(path=Path("/notes/journal"), kind="directory", content=None)
        assert entry.kind == "directory"
        assert entry.content is None

    def test_explicit_kind_still_wins_over_the_path(self) -> None:
        assert Entry(path=Path("/a/b.md"), kind="directory").kind == "directory"

    def test_model_validate_leaves_caller_mapping_untouched(self) -> None:
        data = {"path": "/a/b.md"}
        Entry.model_validate(data)
        assert data == {"path": "/a/b.md"}

    def test_write_shape_round_trips_through_to_observation(self) -> None:
        entry = Entry(path=Path("/notes/journal"), content="hello world")
        observed = entry.to_observation(status="created")
        assert observed.kind == "file"
        assert observed.content == "hello world"
        assert observed.status == "created"


# ---------------------------------------------------------------------------
# Observation mirror drift — each mirror pinned to its owning model
# ---------------------------------------------------------------------------


def _inner_types(annotation: object) -> set[object]:
    """The annotation's non-None union members; the annotation itself when not a union."""
    if get_origin(annotation) in {Union, UnionType}:
        return {arg for arg in get_args(annotation) if arg is not type(None)}
    return {annotation}


class TestObservationMirrors:
    def test_partition_is_total_and_disjoint(self) -> None:
        assert set(Observation.model_fields) == OBSERVATION_MIRROR_FIELDS | OBSERVATION_QUERY_FIELDS
        assert not (OBSERVATION_MIRROR_FIELDS & OBSERVATION_QUERY_FIELDS)

    def test_owner_map_covers_exactly_the_mirror_set(self) -> None:
        assert set(OBSERVATION_MIRROR_OWNERS) == OBSERVATION_MIRROR_FIELDS
        assert {f for f, (owner, _) in OBSERVATION_MIRROR_OWNERS.items() if owner is Entry} == ENTRY_OWNED_MIRRORS

    def test_every_mirror_matches_its_owning_model_field_type(self) -> None:
        for name in sorted(OBSERVATION_MIRROR_FIELDS):
            owner, owner_field = OBSERVATION_MIRROR_OWNERS[name]
            assert owner_field in owner.model_fields, f"Observation.{name} mirrors no {owner.__name__} field"
            obs = _inner_types(Observation.model_fields[name].annotation)
            owned = _inner_types(owner.model_fields[owner_field].annotation)
            assert obs == owned, f"type drift on {name!r}: Observation {obs} != {owner.__name__}.{owner_field} {owned}"

    def test_non_entry_mirrors_resolve_to_version_and_edge(self) -> None:
        assert OBSERVATION_MIRROR_OWNERS["version"] == (Version, "number")
        assert OBSERVATION_MIRROR_OWNERS["edge_type"] == (Edge, "edge_type")
        assert OBSERVATION_MIRROR_OWNERS["edge_weight"] == (Edge, "weight")
        assert OBSERVATION_MIRROR_OWNERS["edge_distance"] == (Edge, "distance")

    def test_query_fields_never_exist_on_any_model(self) -> None:
        models: tuple[type[BaseModel], ...] = (Entry, Chunk, Version, Edge)
        for name in sorted(OBSERVATION_QUERY_FIELDS):
            for model in models:
                assert name not in model.model_fields, f"query field {name!r} leaked onto {model.__name__}"


# ---------------------------------------------------------------------------
# Entry.to_observation — the projection seam
# ---------------------------------------------------------------------------


class TestEntryToObservation:
    def test_projection_covers_every_entry_owned_mirror(self) -> None:
        entry = Entry(path=Path("/docs/a.md"), content="hello", mime_type="text/markdown")
        obs = entry.to_observation()
        for name in ENTRY_OWNED_MIRRORS:
            assert getattr(obs, name) == getattr(entry, name), f"mirror {name!r} not projected"
            assert getattr(obs, name) is not None, f"mirror {name!r} unexercised by this entry"

    def test_non_entry_mirrors_stay_unpopulated(self) -> None:
        obs = Entry(path=Path("/a.md"), content="x").to_observation()
        for name in OBSERVATION_MIRROR_FIELDS - ENTRY_OWNED_MIRRORS:
            assert getattr(obs, name) is None
            assert name not in obs.populated

    def test_query_fields_come_from_the_operation(self) -> None:
        entry = Entry(path=Path("/a.md"), content="x")
        obs = entry.to_observation(
            score=0.5,
            status="created",
            matches=[Match(start=1, end=1, match=1)],
        )
        assert obs.score == 0.5
        assert obs.status == "created"
        assert obs.matches == [Match(start=1, end=1, match=1)]

    def test_no_query_facts_unless_supplied(self) -> None:
        obs = Entry(path=Path("/a.md"), content="x").to_observation()
        assert obs.score is None
        assert obs.status is None
        assert obs.matches is None


# ---------------------------------------------------------------------------
# Observation populated-field mask
# ---------------------------------------------------------------------------


class TestObservationPopulatedMask:
    def test_defaults_to_non_none_supplied_fields(self) -> None:
        obs = Observation(path=Path("/a.md"), kind="file", content=None)
        assert obs.populated == frozenset({"path", "kind"})

    def test_non_content_kinds_never_carry_content_metrics(self) -> None:
        # The model owns the rule: a storage NOT NULL default (or a wire
        # peer) claiming a directory size is nulled at construction, and a
        # stamped mask still reports the metric as fetched-and-null.
        stamped = Observation(
            path=Path("/d"), kind="directory", size_bytes=5, populated=frozenset({"path", "kind", "size_bytes"})
        )
        assert stamped.size_bytes is None
        assert "size_bytes" in stamped.populated
        wire = Observation.model_validate({"path": "/d", "kind": "directory", "size_bytes": 5})
        assert wire.size_bytes is None
        assert Observation(path=Path("/f"), kind="file", size_bytes=5).size_bytes == 5
        # An unfetched kind cannot be judged, so the metric is left alone.
        assert Observation(path=Path("/x"), size_bytes=5).size_bytes == 5

    def test_explicit_mask_wins_over_derivation(self) -> None:
        # A fetched-but-null column stays in the mask: the mask records what
        # the call fetched, not which values happen to be non-null.
        obs = Observation(path=Path("/a.md"), populated=frozenset({"path", "content"}))
        assert obs.content is None
        assert obs.populated == frozenset({"path", "content"})

    def test_to_observation_populates_every_entry_owned_mirror(self) -> None:
        obs = Entry(path=Path("/a.md"), content="x").to_observation()
        assert obs.populated == ENTRY_OWNED_MIRRORS

    def test_to_observation_adds_supplied_query_fields(self) -> None:
        obs = Entry(path=Path("/a.md"), content="x").to_observation(score=0.5, status="created")
        assert obs.populated == ENTRY_OWNED_MIRRORS | {"score", "status"}

    def test_rebasing_preserves_the_mask(self) -> None:
        obs = Observation(path=Path("/docs/a.md"), populated=frozenset({"path", "content"}))
        assert obs.with_mount("/data").populated == frozenset({"path", "content"})


# ---------------------------------------------------------------------------
# Mount rebasing — copy-returning, never in place
# ---------------------------------------------------------------------------


class TestMountRebasing:
    def test_entry_with_mount_returns_rebased_copy(self) -> None:
        entry = Entry(path=Path("/docs/a.md"), content="x")
        rebased = entry.with_mount("/data")
        assert rebased.path == "/data/docs/a.md"
        assert isinstance(rebased.path, Path)
        assert rebased.name == "a.md"
        assert rebased.content_hash == entry.content_hash
        assert entry.path == "/docs/a.md"  # original untouched

    def test_entry_without_mount_inverts_with_mount(self) -> None:
        entry = Entry(path=Path("/data/docs/a.md"), content="x")
        local = entry.without_mount("/data")
        assert local.path == "/docs/a.md"
        assert local.with_mount("/data").path == entry.path

    def test_root_entry_takes_the_mount_leaf_name(self) -> None:
        root = Entry(path=Path("/"))
        mounted = root.with_mount("/data")
        assert mounted.path == "/data"
        assert mounted.name == "data"
        assert mounted.without_mount("/data").name == root.name

    def test_non_boundary_prefix_is_rejected(self) -> None:
        entry = Entry(path=Path("/mnt/foobar/x.md"), content="x")
        with pytest.raises(ValueError, match="not within mount"):
            entry.without_mount("/mnt/foo")

    def test_observation_rebases_as_frozen_copy(self) -> None:
        obs = Observation(path=Path("/docs/a.md"), score=0.5)
        rebased = obs.with_mount("/data")
        assert rebased.path == "/data/docs/a.md"
        assert rebased.score == 0.5
        assert obs.path == "/docs/a.md"
        assert rebased.without_mount("/data") == obs

    def test_observation_rebase_carries_trash_path(self) -> None:
        obs = Observation(path=Path("/a.md"), trash_path=Path("/.vfs/trash/2026-07-24-05/01A-a.md"))
        rebased = obs.with_mount("/data")
        assert rebased.trash_path == "/data/.vfs/trash/2026-07-24-05/01A-a.md"
        assert rebased.without_mount("/data") == obs


# ---------------------------------------------------------------------------
# Entry.with_content — content replacement, copy-returning
# ---------------------------------------------------------------------------


class TestWithContent:
    def test_returns_refreshed_copy(self) -> None:
        entry = Entry(path=Path("/docs/a.md"), content="old")
        updated = entry.with_content("new content")
        assert updated.content == "new content"
        assert updated.content_hash != entry.content_hash
        assert updated.size_bytes == len(b"new content")
        assert entry.content == "old"  # original untouched

    def test_metrics_match_fresh_construction(self) -> None:
        updated = Entry(path=Path("/a.md"), content="seed").with_content("hello\nworld")
        fresh = Entry(path=Path("/a.md"), content="hello\nworld")
        for field in ("content_hash", "size_bytes", "lines"):
            assert getattr(updated, field) == getattr(fresh, field), field

    def test_directory_rejected(self) -> None:
        with pytest.raises(ValueError, match="Cannot set content on a directory"):
            Entry(path=Path("/docs")).with_content("x")

    def test_null_bytes_rejected(self) -> None:
        entry = Entry(path=Path("/a.md"), content="ok")
        with pytest.raises(ValueError, match="null bytes"):
            entry.with_content("bad\x00byte")


# ---------------------------------------------------------------------------
# Version — creation, payloads, reconstruction
# ---------------------------------------------------------------------------


def _full_metrics(content: str) -> tuple[str, int, int]:
    encoded = content.encode()
    return hashlib.sha256(encoded).hexdigest(), len(encoded), content.count("\n") + 1 if content else 0


def _version(number: int, content: str, prev: str | None, **kwargs: object) -> Version:
    return Version.create(
        file=Path("/a.md"),
        number=number,
        version_content=content,
        prev_content=prev,
        created_by="auto",
        **kwargs,  # ty: ignore[invalid-argument-type]
    )


class TestVersion:
    def test_v1_row_is_a_snapshot(self) -> None:
        row = _version(1, "hello", None, force_snapshot=True)
        assert row.file == "/a.md"
        assert row.is_snapshot is True
        assert row.content == "hello"
        assert row.version_diff is None

    def test_diff_row_keeps_full_content_metrics(self) -> None:
        row = _version(2, "hello\nworld", "hello")
        assert row.is_snapshot is False
        assert row.content is None  # diff rows store no snapshot text
        assert row.version_diff
        # metrics describe the full version content, not the stored diff
        full_hash, full_size, full_lines = _full_metrics("hello\nworld")
        assert row.content_hash == full_hash
        assert row.size_bytes == full_size
        assert row.lines == full_lines

    def test_hydrated_diff_row_is_never_re_measured(self) -> None:
        # A stored diff row round-trips: construction must keep the explicit
        # full-content metrics rather than measuring the diff payload.
        row = _version(2, "hello\nworld", "hello")
        hydrated = Version(**row.model_dump())
        assert hydrated.content_hash == row.content_hash
        assert hydrated.size_bytes == row.size_bytes
        assert hydrated.lines == row.lines

    def test_reconstruction_walks_snapshot_plus_diffs(self) -> None:
        contents = ["one", "one\ntwo", "one\ntwo\nthree"]
        rows = [_version(n + 1, contents[n], contents[n - 1] if n else None) for n in range(3)]
        assert Version.reconstruct(rows, 3) == "one\ntwo\nthree"
        assert Version.reconstruct(rows, 2) == "one\ntwo"

    def test_reconstruction_detects_missing_rows(self) -> None:
        v1 = _version(1, "one", None)
        with pytest.raises(ValueError, match="Missing version row"):
            Version.reconstruct([v1], 2)

    def test_reconstruction_with_no_eligible_rows_is_a_missing_row(self) -> None:
        # Both empty history and all-newer rows leave nothing at or below
        # the target — the same missing-row refusal, before any walk.
        with pytest.raises(ValueError, match="Missing version row"):
            Version.reconstruct([], 1)
        with pytest.raises(ValueError, match="Missing version row"):
            Version.reconstruct([_version(2, "two", None)], 1)

    def test_reconstruction_requires_a_snapshot(self) -> None:
        diff_only = _version(2, "two", "one")
        with pytest.raises(ValueError, match="Missing snapshot"):
            Version.reconstruct([diff_only], 2)

    def test_gapped_labels_reconstruct_in_row_order(self) -> None:
        # Labels are version values (ADR 017): a move ticked the version
        # between v1 and v4, so no row is labeled 2 or 3 — the diff chains
        # from the previous stored row, whatever the label distance.
        v1 = _version(1, "one", None)
        v4 = _version(4, "one\ntwo", "one")
        assert v4.is_snapshot is False
        assert Version.reconstruct([v1, v4], 4) == "one\ntwo"

    def test_a_lost_intermediate_row_fails_the_integrity_net(self) -> None:
        # Numbering continuity is not a signal under gapped labels: a lost
        # diff row surfaces as a failed diff application or a hash mismatch.
        v1 = _version(1, "a\nb\nc", None)
        v2 = _version(2, "a\nb\nc\nd", "a\nb\nc")
        v3 = _version(3, "a\nb\nc\ne", "a\nb\nc\nd")
        assert Version.reconstruct([v1, v2, v3], 3) == "a\nb\nc\ne"
        with pytest.raises(ValueError):
            Version.reconstruct([v1, v3], 3)  # v2 lost, not a legitimate gap

    def test_reconstruction_verifies_content_hash(self) -> None:
        tampered = _version(1, "one", None).model_copy(update={"content_hash": "0" * 64})
        with pytest.raises(ValueError, match="Hash mismatch"):
            Version.reconstruct([tampered], 1)

    def test_stored_payload_must_exist(self) -> None:
        hollow = Version(file=Path("/a.md"), number=1, is_snapshot=True, content_hash="0" * 64)
        with pytest.raises(ValueError, match="missing stored payload"):
            hollow.stored_payload()

    def test_both_payloads_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not set both"):
            Version(
                file=Path("/a.md"),
                number=1,
                is_snapshot=True,
                content="x",
                version_diff="y",
                content_hash="0" * 64,
            )

    def test_null_bytes_in_payloads_rejected(self) -> None:
        with pytest.raises(ValidationError, match="null bytes"):
            Version(file=Path("/a.md"), number=1, is_snapshot=False, version_diff="a\x00b", content_hash="0" * 64)

    def test_number_and_file_are_validated(self) -> None:
        with pytest.raises(ValidationError, match="number must be >= 1"):
            Version(file=Path("/a.md"), number=0, is_snapshot=True, content="x", content_hash="0" * 64)
        with pytest.raises(ValidationError, match="file must reference a file"):
            Version(file=Path("/"), number=1, is_snapshot=True, content="x", content_hash="0" * 64)


# ---------------------------------------------------------------------------
# Chunk — split derivation and validation
# ---------------------------------------------------------------------------


class TestChunk:
    def test_small_content_yields_single_whole_chunk(self) -> None:
        chunks = Chunk.split(file=Path("/docs/a.md"), content="hello\nworld", ext="md")
        assert len(chunks) == 1
        (c,) = chunks
        assert c.file == "/docs/a.md"
        assert c.chunk_index == 0
        assert c.content == "hello\nworld"
        assert (c.line_start, c.line_end) == (1, 2)
        assert c.content_hash == hashlib.sha256(b"hello\nworld").hexdigest()

    def test_sub_gram_content_produces_no_chunks(self) -> None:
        assert Chunk.split(file=Path("/a.md"), content="hi", ext="md") == []

    def test_indexes_enumerate_the_split_in_order(self) -> None:
        chunks = Chunk.split(file=Path("/big.txt"), content="x" * 5000, ext="txt")  # one line, three slices
        assert [c.chunk_index for c in chunks] == [0, 1, 2]
        assert all((c.line_start, c.line_end) == (1, 1) for c in chunks)
        assert sum(len(c.content) for c in chunks) == 5000

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
        chunks = Chunk.split(file=Path("/nb.ipynb"), content=notebook, ext="ipynb")
        assert chunks
        joined = "\n".join(c.content for c in chunks)
        assert "print('hello')" in joined
        assert '"cells"' not in joined  # cell sources, never the raw JSON

    def test_shape_validation(self) -> None:
        with pytest.raises(ValidationError, match="null bytes"):
            Chunk(file=Path("/a.md"), chunk_index=0, line_start=1, line_end=1, content="a\x00b")
        with pytest.raises(ValidationError, match="chunk_index must be >= 0"):
            Chunk(file=Path("/a.md"), chunk_index=-1, line_start=1, line_end=1, content="x")
        with pytest.raises(ValidationError, match="invalid line range"):
            Chunk(file=Path("/a.md"), chunk_index=0, line_start=5, line_end=2, content="x")
        with pytest.raises(ValidationError, match="file must reference a file"):
            Chunk(file=Path("/"), chunk_index=0, line_start=1, line_end=1, content="x")


# ---------------------------------------------------------------------------
# Edge — endpoint and type validation
# ---------------------------------------------------------------------------


class TestEdge:
    def test_valid_edge_defaults(self) -> None:
        edge = Edge(source=Path("/a.md"), target=Path("/b.md"), edge_type="imports")
        assert edge.weight is None
        assert edge.distance is None
        assert edge.version == 1

    def test_root_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="source must not be the root"):
            Edge(source=Path("/"), target=Path("/b.md"), edge_type="imports")

    def test_meta_endpoint_rejected(self) -> None:
        with pytest.raises(ValidationError, match="target must not be a reserved metadata path"):
            Edge(source=Path("/a.md"), target=Path("/.vfs/trash/x"), edge_type="imports")

    def test_unlawful_edge_type_rejected(self) -> None:
        for bad in ("im/ports", "", ".."):
            with pytest.raises(ValidationError, match="edge_type"):
                Edge(source=Path("/a.md"), target=Path("/b.md"), edge_type=bad)

    def test_revision_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="version must be >= 1"):
            Edge(source=Path("/a.md"), target=Path("/b.md"), edge_type="imports", version=0)


# ---------------------------------------------------------------------------
# Observation behavior
# ---------------------------------------------------------------------------


class TestObservation:
    def test_frozen(self) -> None:
        obs = Observation(path=Path("/a.md"))
        with pytest.raises(ValidationError):
            obs.score = 1.0  # ty: ignore[invalid-assignment]

    def test_path_is_branded_and_canonical(self) -> None:
        # deliberately unwrapped: canonicalization must happen in model validation
        obs = Observation(path="docs/../a.md")
        assert isinstance(obs.path, Path)
        assert obs.path == "/a.md"
        assert obs.path.name == "a.md"

    def test_edge_mirrors_surface_on_observation(self) -> None:
        obs = Observation(path=Path("/a.md"), edge_type="references", edge_weight=0.5, edge_distance=1.5)
        assert obs.edge_type == "references"
        assert obs.edge_weight == 0.5
        assert obs.edge_distance == 1.5

    def test_match_regions_carry_their_own_text(self) -> None:
        chunk_hit = Match(start=10, end=42, content="def login(): ...", score=0.91)
        grep_hit = Match(start=3, end=7, match=5, content="retry()")
        obs = Observation(path=Path("/src/auth.py"), matches=[chunk_hit, grep_hit], score=0.91)
        assert obs.content is None  # the file's own content was never fetched
        assert obs.matches is not None
        assert obs.matches[0].match is None  # whole-region hit (glean chunk)
        assert obs.matches[0].score == 0.91  # per-region relevance
        assert obs.matches[1].match == 5  # grep hit line
        assert obs.matches[1].score is None  # grep rows carry no relevance
        assert [m.content for m in obs.matches] == ["def login(): ...", "retry()"]
