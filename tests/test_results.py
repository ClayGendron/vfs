"""Tests for the Result envelope: row access, algebra, rebasing, the wire."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from vfs.models2 import Match, Observation
from vfs.paths import MAX_PATH_LENGTH
from vfs.results2 import Result, ResultError, Severity, VFSErrorKind


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

    def test_data_defaults_none(self) -> None:
        assert ResultError(kind=VFSErrorKind.invalid, message="x").data is None

    def test_data_round_trips_on_the_wire(self) -> None:
        err = ResultError(
            kind=VFSErrorKind.conflict,
            message="stale revision",
            path="/a.md",
            data={"expected": 3, "actual": 5},
        )
        restored = ResultError.model_validate(err.model_dump(mode="json"))
        assert restored.data == {"expected": 3, "actual": 5}
        assert restored == err

    def test_mount_rebase_round_trip(self) -> None:
        err = ResultError(kind=VFSErrorKind.not_found, message="gone", path="/docs/a.md")
        rebased = err.with_mount("/data")
        assert rebased.path == "/data/docs/a.md"
        assert rebased.without_mount("/data") == err

    def test_mount_rebase_always_stamps_provenance(self) -> None:
        # with_mount is never the identity: the first hop stamps source and
        # every later hop re-roots it; without_mount inverts the round-trip.
        err = ResultError(kind=VFSErrorKind.unavailable, message="backend down")
        hop = err.with_mount("/data")
        assert hop is not err
        assert hop.source == "/data"
        assert hop.with_mount("/outer").source == "/outer/data"
        assert hop.without_mount("/data") == err


# ---------------------------------------------------------------------------
# Row access and sequence protocol
# ---------------------------------------------------------------------------


class TestRowAccess:
    def test_empty_result(self) -> None:
        # Truthiness is success alone: a successful glob with zero matches
        # is truthy — emptiness is len()'s fact, not __bool__'s.
        result = Result()
        assert result
        assert len(result) == 0
        assert result.first() is None
        assert result.paths == ()
        assert list(result) == []

    def test_sequence_protocol(self) -> None:
        result = Result(ops=("ls",), observations=[obs("/a.md"), obs("/b.md")])
        assert bool(result)
        assert len(result) == 2
        assert result[0].path == "/a.md"
        assert result[-1].path == "/b.md"
        assert result[0:2] == result.observations
        assert [o.path for o in result] == ["/a.md", "/b.md"]
        assert "/a.md" in result
        assert "/missing.md" not in result

    def test_first_and_one(self) -> None:
        single = Result(observations=[obs("/a.md", content="hello")])
        assert single.first() is single.observations[0]
        assert single.one().content == "hello"

    def test_one_raises_on_zero_and_many(self) -> None:
        with pytest.raises(ValueError, match="got 0"):
            Result(ops=("read",)).one()
        with pytest.raises(ValueError, match="got 2"):
            Result(observations=[obs("/a.md"), obs("/b.md")]).one()

    def test_failed_result_is_falsy_even_with_rows(self) -> None:
        result = Result(
            observations=[obs("/a.md")],
            errors=[ResultError(kind=VFSErrorKind.unavailable, message="partial")],
        )
        assert not result
        assert result.error_message == "partial"


# ---------------------------------------------------------------------------
# Set algebra
# ---------------------------------------------------------------------------


class TestSetAlgebra:
    def test_intersection_keeps_common_paths(self) -> None:
        a = Result(ops=("glob",), observations=[obs("/a.md"), obs("/b.md")])
        b = Result(ops=("glob",), observations=[obs("/b.md"), obs("/c.md")])
        assert (a & b).paths == ("/b.md",)

    def test_union_left_wins_and_fills_nulls(self) -> None:
        a = Result(ops=("glean",), observations=[obs("/a.md", score=0.9)])
        b = Result(ops=("stat",), observations=[obs("/a.md", score=0.1, size_bytes=42)])
        merged = (a | b).one()
        assert merged.score == 0.9  # left wins
        assert merged.size_bytes == 42  # right fills the null

    def test_cross_op_union_keeps_both_ops(self) -> None:
        # Ordered union, no in-band sentinel: both producing ops survive,
        # and .op reads None so renderers fall back to the generic shape.
        a = Result(ops=("glob",), observations=[obs("/a.md")])
        b = Result(ops=("grep",), observations=[obs("/b.md")])
        assert (a | b).ops == ("glob", "grep")
        assert (a | b).op is None
        assert (a | a).op == "glob"

    def test_difference(self) -> None:
        a = Result(ops=("glob",), observations=[obs("/a.md"), obs("/b.md")])
        b = Result(ops=("grep",), observations=[obs("/b.md")])
        diff = a - b
        assert diff.paths == ("/a.md",)
        assert diff.op == "glob"

    def test_errors_and_success_propagate(self) -> None:
        err = ResultError(kind=VFSErrorKind.timeout, message="slow mount")
        a = Result(observations=[obs("/a.md")])
        b = Result(errors=[err])
        combined = a | b
        assert not combined.success
        assert combined.errors == [err]

    def test_union_with_empty_preserves_duplicate_paths(self) -> None:
        dup = Result(ops=("grep",), observations=[obs("/a.md", score=0.9), obs("/a.md", score=0.1)])
        empty = Result(ops=("grep",))
        assert (dup | empty).observations == dup.observations
        assert (empty | dup).observations == dup.observations

    def test_diamond_chains_do_not_duplicate_errors(self) -> None:
        err = ResultError(kind=VFSErrorKind.unavailable, message="mount down")
        a = Result(observations=[obs("/a.md")])
        b = Result(errors=[err], observations=[obs("/a.md")])
        assert ((a | b) & b).errors == [err]

    def test_merge_does_not_alias_the_right_rows_matches_list(self) -> None:
        right_row = obs("/a.md", matches=[Match(start=1, end=2)])
        left = Result(observations=[obs("/a.md")])
        right = Result(observations=[right_row])
        merged = (left | right).one()
        assert merged.matches == right_row.matches
        assert merged.matches is not right_row.matches


# ---------------------------------------------------------------------------
# Enrichment chains
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_sort_default_is_score_descending_none_last(self) -> None:
        result = Result(
            observations=[obs("/low.md", score=0.1), obs("/none.md"), obs("/high.md", score=0.9)],
        )
        assert result.sort().paths == ("/high.md", "/low.md", "/none.md")

    def test_top_sorts_then_slices(self) -> None:
        result = Result(
            ops=("glean",),
            observations=[obs("/low.md", score=0.1), obs("/high.md", score=0.9)],
        )
        top = result.top(1)
        assert top.paths == ("/high.md",)
        assert top.op == "glean"

    def test_top_rejects_non_positive_k(self) -> None:
        with pytest.raises(ValueError, match="k must be >= 1"):
            Result().top(0)

    def test_sort_honors_custom_key(self) -> None:
        result = Result(observations=[obs("/b.md"), obs("/a.md"), obs("/c.md")])
        ordered = result.sort(key=lambda o: o.path, reverse=False)
        assert ordered.paths == ("/a.md", "/b.md", "/c.md")

    def test_sort_treats_nan_score_as_lowest(self) -> None:
        # NaN compares false against everything; an unguarded key corrupts the
        # sort and top() drops the real leaders. NaN must sink like None.
        result = Result(
            ops=("glean",),
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
        result = Result(
            observations=[obs("/a.md", kind="file"), obs("/docs", kind="directory")],
        )
        assert result.filter(lambda o: o.kind == "file").paths == ("/a.md",)
        assert result.kinds("directory").paths == ("/docs",)

    def test_chains_preserve_envelope(self) -> None:
        err = ResultError(kind=VFSErrorKind.unavailable, message="one mount down")
        result = Result(
            ops=("glean",),
            observations=[obs("/a.md", score=0.5)],
            errors=[err],
        )
        chained = result.sort().filter(lambda o: True)
        assert chained.op == "glean"
        assert chained.errors == [err]


# ---------------------------------------------------------------------------
# Mount rebasing
# ---------------------------------------------------------------------------


class TestMountRebasing:
    def test_with_mount_rebases_rows_and_error_paths(self) -> None:
        result = Result(
            ops=("ls",),
            observations=[obs("/a.md"), obs("/")],
            errors=[ResultError(kind=VFSErrorKind.not_found, message="gone", path="/b.md")],
        )
        rebased = result.with_mount("/data")
        assert rebased.paths == ("/data/a.md", "/data")
        assert rebased.errors[0].path == "/data/b.md"

    def test_without_mount_inverts_with_mount(self) -> None:
        result = Result(ops=("ls",), observations=[obs("/a.md")])
        assert result.with_mount("/data").without_mount("/data") == result

    def test_empty_mount_is_identity_and_root_is_a_real_hop(self) -> None:
        # "" is the identity; "/" is a real hop for provenance even though
        # row paths are unchanged — an errorless result stays equal.
        result = Result(observations=[obs("/a.md")])
        assert result.with_mount("") is result
        assert result.without_mount("/") is result
        rooted = result.with_mount("/")
        assert rooted.paths == ("/a.md",)
        assert rooted == result

    def test_rebase_is_pure(self) -> None:
        result = Result(observations=[obs("/a.md")])
        result.with_mount("/data")
        assert result.paths == ("/a.md",)


# ---------------------------------------------------------------------------
# Rebase overflow classification — the router seam never raises
# ---------------------------------------------------------------------------

# A valid 1004-char local path; overflows once rebased under the 31-char mount.
DEEP_LOCAL = "/" + "/".join(["a" * 250] * 4)
LONG_MOUNT = "/" + "m" * 30


class TestRebaseOverflow:
    def test_overflow_row_becomes_unaddressable_warning(self) -> None:
        result = Result(ops=("glob",), observations=[obs(DEEP_LOCAL), obs("/ok.py")])
        rebased = result.with_mount(LONG_MOUNT)
        assert rebased.success is True  # loss on record, not failure
        assert rebased.paths == (f"{LONG_MOUNT}/ok.py",)  # sibling row survives
        [err] = rebased.errors
        assert err.kind is VFSErrorKind.unaddressable
        assert err.severity is Severity.warning
        assert err.path is None
        assert err.source == LONG_MOUNT
        assert str(MAX_PATH_LENGTH) in err.message
        assert err.data == {"vfs.overflow": {"local_path": DEEP_LOCAL}}

    def test_row_at_exactly_the_limit_survives(self) -> None:
        mount = "/" + "m" * 19  # 20 + 1004 == 1024
        rebased = Result(observations=[obs(DEEP_LOCAL)]).with_mount(mount)
        assert rebased.success is True
        assert rebased.errors == []
        assert len(rebased.paths[0]) == MAX_PATH_LENGTH

    def test_overflow_rebase_is_pure(self) -> None:
        result = Result(observations=[obs(DEEP_LOCAL)])
        result.with_mount(LONG_MOUNT)
        assert result.paths == (DEEP_LOCAL,)
        assert result.success is True
        assert result.errors == []

    def test_error_path_overflow_drops_to_none_and_keeps_location_in_data(self) -> None:
        err = ResultError(
            kind=VFSErrorKind.not_found,
            message="missing",
            path=DEEP_LOCAL,
            data={"attempt": 1},
        )
        rebased = err.with_mount(LONG_MOUNT)
        assert rebased.path is None
        assert rebased.kind is VFSErrorKind.not_found
        assert rebased.message == "missing"
        assert rebased.source == LONG_MOUNT
        assert rebased.data == {"attempt": 1, "vfs.overflow": {"local_path": DEEP_LOCAL}}

    def test_error_path_at_exactly_the_limit_rebases(self) -> None:
        mount = "/" + "m" * 19
        err = ResultError(kind=VFSErrorKind.not_found, message="missing", path=DEEP_LOCAL)
        rebased = err.with_mount(mount)
        assert rebased.path is not None
        assert len(rebased.path) == MAX_PATH_LENGTH


# ---------------------------------------------------------------------------
# Serialization — the wire contract
# ---------------------------------------------------------------------------


def rich_result() -> Result:
    return Result(
        ops=("grep",),
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
        errors=[ResultError(kind=VFSErrorKind.permission_denied, message="read-only mount", path="/ro/x.md")],
    )


class TestWireContract:
    def test_payload_round_trip_is_lossless(self) -> None:
        result = rich_result()
        assert Result.from_payload(result.to_payload()) == result

    def test_payload_round_trip_without_exclude_none(self) -> None:
        result = rich_result()
        assert Result.from_payload(result.to_payload(exclude_none=False)) == result

    def test_payload_is_json_safe(self) -> None:
        payload = rich_result().to_payload()
        row = payload["observations"][0]
        assert isinstance(row["path"], str)
        assert isinstance(row["updated_at"], str)
        assert payload["errors"][0]["kind"] == "vfs.permission_denied"

    def test_payload_paths_revalidate_through_the_gate(self) -> None:
        payload = rich_result().to_payload()
        payload["observations"][0]["path"] = "/a/../b.md"
        restored = Result.from_payload(payload)
        assert restored.observations[0].path == "/b.md"

    def test_exclude_none_drops_unpopulated_fields(self) -> None:
        payload = Result(observations=[obs("/a.md")]).to_payload()
        assert "score" not in payload["observations"][0]

    def test_to_json_matches_payload(self) -> None:
        result = rich_result()
        assert json.loads(result.to_json()) == result.to_payload()

    def test_non_finite_scores_are_json_safe_and_restore_as_none(self) -> None:
        result = Result(
            ops=("glean",),
            observations=[obs("/a.md", score=float("nan")), obs("/b.md", score=float("inf"))],
        )
        payload = result.to_payload()
        json.dumps(payload, allow_nan=False)  # strict JSON must not raise
        assert json.loads(result.to_json()) == payload
        restored = Result.from_payload(payload)
        assert restored.observations[0].score is None
        assert restored.observations[1].score is None

    def test_payload_survives_an_actual_json_wire(self) -> None:
        result = rich_result()
        wire = json.loads(json.dumps(result.to_payload(), allow_nan=False))
        assert Result.from_payload(wire) == result

    def test_str_delegates_to_render(self) -> None:
        result = Result(ops=("glob",), observations=[obs("/b.md"), obs("/a.md")])
        assert str(result) == "/a.md\n/b.md"
