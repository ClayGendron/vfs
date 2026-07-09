"""Tests for projection: validation, defaults, and sentinel resolution."""

from __future__ import annotations

from typing import Any

import pytest

from vfs.models import Observation
from vfs.paths import Path
from vfs.results.projection import (
    FALLBACK_PROJECTION,
    KNOWN_FUNCTIONS,
    OBSERVATION_FIELDS,
    default_projection,
    is_known_function,
    resolve_projection,
    validate_projection,
)


def obs(path: str, **kwargs: Any) -> Observation:
    return Observation(path=Path(path), **kwargs)


class TestVocabulary:
    def test_observation_fields_track_the_model(self) -> None:
        assert frozenset(Observation.model_fields) == OBSERVATION_FIELDS

    def test_every_default_projection_uses_real_fields(self) -> None:
        for function in KNOWN_FUNCTIONS:
            for field in default_projection(function):
                assert field in OBSERVATION_FIELDS, f"{function}: {field}"

    def test_is_known_function(self) -> None:
        assert is_known_function("grep")
        assert is_known_function("glean")
        assert not is_known_function("future_op")


class TestDefaultProjection:
    def test_grep_default_is_matches_not_content(self) -> None:
        assert default_projection("grep") == ("path", "matches")

    def test_unknown_function_falls_back(self) -> None:
        assert default_projection("future_op") == FALLBACK_PROJECTION


class TestValidateProjection:
    def test_none_passes_through(self) -> None:
        assert validate_projection(None) is None

    def test_list_becomes_tuple(self) -> None:
        assert validate_projection(["path", "score"]) == ("path", "score")

    def test_sentinels_are_accepted(self) -> None:
        assert validate_projection(("default", "all")) == ("default", "all")

    def test_bare_string_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="bare string"):
            validate_projection("path")  # ty: ignore[invalid-argument-type]

    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown field 'lines'"):
            validate_projection(("path", "lines"))

    def test_empty_projection_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            validate_projection(())
        with pytest.raises(ValueError, match="must not be empty"):
            validate_projection([])

    def test_non_sequence_inputs_are_rejected(self) -> None:
        with pytest.raises(TypeError, match="tuple or list"):
            validate_projection(b"path")  # ty: ignore[invalid-argument-type]
        with pytest.raises(TypeError, match="tuple or list"):
            validate_projection({"path": 1})  # ty: ignore[invalid-argument-type]
        with pytest.raises(TypeError, match="tuple or list"):
            validate_projection(name for name in ("path",))  # ty: ignore[invalid-argument-type]

    def test_non_string_items_are_rejected_cleanly(self) -> None:
        with pytest.raises(TypeError, match="field-name strings"):
            validate_projection(("path", 5))  # ty: ignore[invalid-argument-type]
        with pytest.raises(TypeError, match="field-name strings"):
            validate_projection((["path"],))  # ty: ignore[invalid-argument-type]


class TestResolveProjection:
    def test_none_resolves_to_function_default(self) -> None:
        assert resolve_projection(None, "stat", []) == ("path", "kind", "size_bytes", "updated_at")

    def test_default_sentinel_expands_in_place(self) -> None:
        assert resolve_projection(("default", "score"), "grep", []) == ("path", "matches", "score")

    def test_all_sentinel_expands_to_populated_fields(self) -> None:
        rows = [obs("/a.md", kind="file"), obs("/b.md", score=0.5)]
        resolved = resolve_projection(("all",), "glob", rows)
        assert set(resolved) == {"path", "kind", "score"}

    def test_duplicates_drop_first_win(self) -> None:
        assert resolve_projection(("score", "default"), "glean", []) == ("score", "path")
