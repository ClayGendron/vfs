"""Tests for the VFSResult envelope: row access, algebra, rebasing, the wire."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from vfs.models2 import Match, Observation
from vfs.results2 import ResultError, VFSErrorKind, VFSResult


def obs(path: str, **kwargs: object) -> Observation:
    return Observation(path=path, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Structured errors
# ---------------------------------------------------------------------------


class TestResultError:
    def test_kind_serializes_to_namespaced_value(self) -> None:
        err = ResultError(kind=VFSErrorKind.not_found, message="no such path", path="/a/b.md")
        assert err.model_dump(mode="json")["kind"] == "vfs.not_found"

    def test_kind_parses_from_wire_value(self) -> None:
        err = ResultError.model_validate({"kind": "vfs.timeout", "message": "took too long"})
        assert err.kind is VFSErrorKind.timeout
        assert err.path is None

    def test_unknown_kind_from_newer_peer_is_preserved_as_string(self) -> None:
        err = ResultError.model_validate({"kind": "vfs.quota_exceeded", "message": "over quota"})
        assert err.kind == "vfs.quota_exceeded"
        assert not isinstance(err.kind, VFSErrorKind)
        restored = ResultError.model_validate(err.model_dump(mode="json"))
        assert restored == err

    def test_frozen(self) -> None:
        err = ResultError(kind=VFSErrorKind.invalid, message="bad")
        with pytest.raises(Exception, match="frozen"):
            err.message = "other"  # type: ignore[misc]

    def test_mount_rebase_round_trip(self) -> None:
        err = ResultError(kind=VFSErrorKind.not_found, message="gone", path="/docs/a.md")
        rebased = err.with_mount("/data")
        assert rebased.path == "/data/docs/a.md"
        assert rebased.without_mount("/data") == err

    def test_mount_rebase_without_path_is_identity(self) -> None:
        err = ResultError(kind=VFSErrorKind.unavailable, message="backend down")
        assert err.with_mount("/data") is err
        assert err.without_mount("/data") is err


# ---------------------------------------------------------------------------
# Row access and sequence protocol
# ---------------------------------------------------------------------------


class TestRowAccess:
    def test_empty_result(self) -> None:
        result = VFSResult()
        assert not result
        assert len(result) == 0
        assert result.first() is None
        assert result.paths == ()
        assert list(result) == []

    def test_sequence_protocol(self) -> None:
        result = VFSResult(function="ls", observations=[obs("/a.md"), obs("/b.md")])
        assert bool(result)
        assert len(result) == 2
        assert result[0].path == "/a.md"
        assert result[-1].path == "/b.md"
        assert result[0:2] == result.observations
        assert [o.path for o in result] == ["/a.md", "/b.md"]
        assert "/a.md" in result
        assert "/missing.md" not in result

    def test_first_and_one(self) -> None:
        single = VFSResult(observations=[obs("/a.md", content="hello")])
        assert single.first() is single.observations[0]
        assert single.one().content == "hello"

    def test_one_raises_on_zero_and_many(self) -> None:
        with pytest.raises(ValueError, match="got 0"):
            VFSResult(function="read").one()
        with pytest.raises(ValueError, match="got 2"):
            VFSResult(observations=[obs("/a.md"), obs("/b.md")]).one()

    def test_failed_result_is_falsy_even_with_rows(self) -> None:
        result = VFSResult(
            observations=[obs("/a.md")],
            success=False,
            errors=[ResultError(kind=VFSErrorKind.unavailable, message="partial")],
        )
        assert not result
        assert result.error_message == "partial"


# ---------------------------------------------------------------------------
# Set algebra
# ---------------------------------------------------------------------------


class TestSetAlgebra:
    def test_intersection_keeps_common_paths(self) -> None:
        a = VFSResult(function="glob", observations=[obs("/a.md"), obs("/b.md")])
        b = VFSResult(function="glob", observations=[obs("/b.md"), obs("/c.md")])
        assert (a & b).paths == ("/b.md",)

    def test_union_left_wins_and_fills_nulls(self) -> None:
        a = VFSResult(function="vector_search", observations=[obs("/a.md", score=0.9)])
        b = VFSResult(function="stat", observations=[obs("/a.md", score=0.1, size_bytes=42)])
        merged = (a | b).one()
        assert merged.score == 0.9  # left wins
        assert merged.size_bytes == 42  # right fills the null

    def test_cross_function_union_is_hybrid(self) -> None:
        a = VFSResult(function="glob", observations=[obs("/a.md")])
        b = VFSResult(function="grep", observations=[obs("/b.md")])
        assert (a | b).function == "hybrid"
        assert (a | a).function == "glob"

    def test_difference(self) -> None:
        a = VFSResult(function="glob", observations=[obs("/a.md"), obs("/b.md")])
        b = VFSResult(function="grep", observations=[obs("/b.md")])
        diff = a - b
        assert diff.paths == ("/a.md",)
        assert diff.function == "glob"

    def test_errors_and_success_propagate(self) -> None:
        err = ResultError(kind=VFSErrorKind.timeout, message="slow mount")
        a = VFSResult(observations=[obs("/a.md")])
        b = VFSResult(success=False, errors=[err])
        combined = a | b
        assert not combined.success
        assert combined.errors == [err]

    def test_union_with_empty_preserves_duplicate_paths(self) -> None:
        dup = VFSResult(function="grep", observations=[obs("/a.md", score=0.9), obs("/a.md", score=0.1)])
        empty = VFSResult(function="grep")
        assert (dup | empty).observations == dup.observations
        assert (empty | dup).observations == dup.observations

    def test_diamond_chains_do_not_duplicate_errors(self) -> None:
        err = ResultError(kind=VFSErrorKind.unavailable, message="mount down")
        a = VFSResult(observations=[obs("/a.md")])
        b = VFSResult(success=False, errors=[err], observations=[obs("/a.md")])
        assert ((a | b) & b).errors == [err]

    def test_merge_does_not_alias_the_right_rows_matches_list(self) -> None:
        right_row = obs("/a.md", matches=[Match(start=1, end=2)])
        left = VFSResult(observations=[obs("/a.md")])
        right = VFSResult(observations=[right_row])
        merged = (left | right).one()
        assert merged.matches == right_row.matches
        assert merged.matches is not right_row.matches


# ---------------------------------------------------------------------------
# Enrichment chains
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_sort_default_is_score_descending_none_last(self) -> None:
        result = VFSResult(
            observations=[obs("/low.md", score=0.1), obs("/none.md"), obs("/high.md", score=0.9)],
        )
        assert result.sort().paths == ("/high.md", "/low.md", "/none.md")

    def test_top_sorts_then_slices(self) -> None:
        result = VFSResult(
            function="bm25",
            observations=[obs("/low.md", score=0.1), obs("/high.md", score=0.9)],
        )
        top = result.top(1)
        assert top.paths == ("/high.md",)
        assert top.function == "bm25"

    def test_top_rejects_non_positive_k(self) -> None:
        with pytest.raises(ValueError, match="k must be >= 1"):
            VFSResult().top(0)

    def test_sort_treats_nan_score_as_lowest(self) -> None:
        # NaN compares false against everything; an unguarded key corrupts the
        # sort and top() drops the real leaders. NaN must sink like None.
        result = VFSResult(
            function="bm25",
            observations=[
                obs("/a.md", score=1.0),
                obs("/nan.md", score=float("nan")),
                obs("/b.md", score=5.0),
                obs("/c.md", score=4.0),
            ],
        )
        assert result.sort().paths == ("/b.md", "/c.md", "/a.md", "/nan.md")
        assert result.top(2).paths == ("/b.md", "/c.md")

    def test_filter_and_kinds(self) -> None:
        result = VFSResult(
            observations=[obs("/a.md", kind="file"), obs("/docs", kind="directory")],
        )
        assert result.filter(lambda o: o.kind == "file").paths == ("/a.md",)
        assert result.kinds("directory").paths == ("/docs",)

    def test_chains_preserve_envelope(self) -> None:
        err = ResultError(kind=VFSErrorKind.unavailable, message="one mount down")
        result = VFSResult(
            function="vector_search",
            observations=[obs("/a.md", score=0.5)],
            errors=[err],
        )
        chained = result.sort().filter(lambda o: True)
        assert chained.function == "vector_search"
        assert chained.errors == [err]


# ---------------------------------------------------------------------------
# Mount rebasing
# ---------------------------------------------------------------------------


class TestMountRebasing:
    def test_with_mount_rebases_rows_and_error_paths(self) -> None:
        result = VFSResult(
            function="ls",
            observations=[obs("/a.md"), obs("/")],
            errors=[ResultError(kind=VFSErrorKind.not_found, message="gone", path="/b.md")],
        )
        rebased = result.with_mount("/data")
        assert rebased.paths == ("/data/a.md", "/data")
        assert rebased.errors[0].path == "/data/b.md"

    def test_without_mount_inverts_with_mount(self) -> None:
        result = VFSResult(function="ls", observations=[obs("/a.md")])
        assert result.with_mount("/data").without_mount("/data") == result

    def test_root_and_empty_mount_are_identity(self) -> None:
        result = VFSResult(observations=[obs("/a.md")])
        assert result.with_mount("/") is result
        assert result.with_mount("") is result
        assert result.without_mount("/") is result

    def test_rebase_is_pure(self) -> None:
        result = VFSResult(observations=[obs("/a.md")])
        result.with_mount("/data")
        assert result.paths == ("/a.md",)


# ---------------------------------------------------------------------------
# Serialization — the wire contract
# ---------------------------------------------------------------------------


def rich_result() -> VFSResult:
    return VFSResult(
        function="grep",
        observations=[
            obs(
                "/src/auth.py",
                kind="file",
                size_bytes=120,
                updated_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
                score=0.75,
                matches=[Match(start=3, end=5, match=4, content="a\nb\nc", score=0.9)],
            ),
            obs("/src/db.py", status="updated"),
        ],
        success=False,
        errors=[ResultError(kind=VFSErrorKind.permission_denied, message="read-only mount", path="/ro/x.md")],
    )


class TestWireContract:
    def test_payload_round_trip_is_lossless(self) -> None:
        result = rich_result()
        assert VFSResult.from_payload(result.to_payload()) == result

    def test_payload_round_trip_without_exclude_none(self) -> None:
        result = rich_result()
        assert VFSResult.from_payload(result.to_payload(exclude_none=False)) == result

    def test_payload_is_json_safe(self) -> None:
        payload = rich_result().to_payload()
        row = payload["observations"][0]
        assert isinstance(row["path"], str)
        assert isinstance(row["updated_at"], str)
        assert payload["errors"][0]["kind"] == "vfs.permission_denied"

    def test_payload_paths_revalidate_through_the_gate(self) -> None:
        payload = rich_result().to_payload()
        payload["observations"][0]["path"] = "/a/../b.md"
        restored = VFSResult.from_payload(payload)
        assert restored.observations[0].path == "/b.md"

    def test_exclude_none_drops_unpopulated_fields(self) -> None:
        payload = VFSResult(observations=[obs("/a.md")]).to_payload()
        assert "score" not in payload["observations"][0]

    def test_to_json_matches_payload(self) -> None:
        result = rich_result()
        assert json.loads(result.to_json()) == result.to_payload()

    def test_non_finite_scores_are_json_safe_and_restore_as_none(self) -> None:
        result = VFSResult(
            function="bm25",
            observations=[obs("/a.md", score=float("nan")), obs("/b.md", score=float("inf"))],
        )
        payload = result.to_payload()
        json.dumps(payload, allow_nan=False)  # strict JSON must not raise
        assert json.loads(result.to_json()) == payload
        restored = VFSResult.from_payload(payload)
        assert restored.observations[0].score is None
        assert restored.observations[1].score is None

    def test_payload_survives_an_actual_json_wire(self) -> None:
        result = rich_result()
        wire = json.loads(json.dumps(result.to_payload(), allow_nan=False))
        assert VFSResult.from_payload(wire) == result

    def test_str_delegates_to_render(self) -> None:
        result = VFSResult(function="glob", observations=[obs("/b.md"), obs("/a.md")])
        assert str(result) == "/a.md\n/b.md"
