"""Tests for ``vfs.models.versioning`` — diff computation, application, replay.

``Version`` model behavior lives in ``test_models.py``; this file pins
the diff machinery's edges: the empty diff in both directions, junk that
parses to no patch, creation from an empty base, the missing-trailing-
newline marker, and replay's snapshot-first contract.
"""

from __future__ import annotations

import pytest

from vfs.models.versioning import _NO_NEWLINE_MARKER, apply_diff, compute_diff, reconstruct_version


def test_compute_diff_of_identical_content_is_empty() -> None:
    assert compute_diff("a\nb\n", "a\nb\n") == ""


def test_apply_empty_diff_returns_the_base() -> None:
    assert apply_diff("base\n", "") == "base\n"


def test_apply_diff_that_parses_to_no_patch_returns_the_base() -> None:
    assert apply_diff("base\n", "not a unified diff\n") == "base\n"


def test_diff_from_an_empty_base_roundtrips() -> None:
    diff = compute_diff("", "hello\nworld\n")
    assert apply_diff("", diff) == "hello\nworld\n"


def test_roundtrip_without_a_trailing_newline() -> None:
    old, new = "a\nb", "a\nc"
    assert apply_diff(old, compute_diff(old, new)) == new


def test_no_newline_marker_lands_after_a_trailing_context_line() -> None:
    # Format-level pin: apply_diff tolerates a missing marker, so a
    # round-trip cannot catch this — the diff string itself must show it.
    assert compute_diff("x\ny\nb", "z\ny\nb").endswith(_NO_NEWLINE_MARKER)


def test_reconstruct_of_no_versions_is_empty() -> None:
    assert reconstruct_version([]) == ""


def test_reconstruct_requires_a_snapshot_first() -> None:
    with pytest.raises(ValueError, match="snapshot"):
        reconstruct_version([(False, "diff")])


def test_reconstruct_replays_diffs_and_later_snapshots() -> None:
    v1, v2, v3 = "one\n", "one\ntwo\n", "three\n"
    assert reconstruct_version([(True, v1), (False, compute_diff(v1, v2))]) == v2
    assert reconstruct_version([(True, v1), (False, compute_diff(v1, v2)), (True, v3)]) == v3
