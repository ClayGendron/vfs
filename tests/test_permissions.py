"""Tests for ``vfs.permissions`` — the map, coercion, and the write gate.

Router-side enforcement (gate order, layering, deny reporting) lives in
``test_base_gates.py``; this file pins the unit surface: the permission
vocabulary, override normalization and rejection, longest-prefix
resolution, coercion, and the metadata-alias candidates of
``check_writable``.
"""

from __future__ import annotations

import pytest

from vfs.paths import Path
from vfs.permissions import PermissionMap, check_writable, coerce_permissions, read_only, validate_permission
from vfs.results import VFSErrorKind

# ---------------------------------------------------------------------------
# Vocabulary and coercion
# ---------------------------------------------------------------------------


def test_validate_permission_accepts_the_two_values() -> None:
    assert validate_permission("read") == "read"
    assert validate_permission("read_write") == "read_write"


def test_validate_permission_rejects_anything_else() -> None:
    with pytest.raises(ValueError, match="must be 'read' or 'read_write'"):
        validate_permission("admin")


def test_coerce_passes_a_map_through_and_wraps_a_string() -> None:
    pmap = read_only()
    assert coerce_permissions(pmap) is pmap
    assert coerce_permissions("read").default == "read"


def test_coerce_rejects_other_types() -> None:
    with pytest.raises(TypeError, match="got int"):
        coerce_permissions(123)  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# PermissionMap — construction and resolution
# ---------------------------------------------------------------------------


def test_override_at_root_is_rejected() -> None:
    with pytest.raises(ValueError, match="use 'default' instead"):
        PermissionMap(overrides=(("/", "read"),))


def test_duplicate_override_paths_are_rejected_after_normalization() -> None:
    with pytest.raises(ValueError, match="Duplicate override path"):
        PermissionMap(overrides=(("/a", "read"), ("/a/", "read_write")))


def test_resolve_uses_longest_prefix_then_default() -> None:
    pmap = PermissionMap(default="read", overrides=(("/inbox", "read_write"),))
    assert pmap.resolve("/inbox/new.txt") == "read_write"
    assert pmap.resolve("/elsewhere") == "read"


# ---------------------------------------------------------------------------
# check_writable — the metadata-alias candidates
# ---------------------------------------------------------------------------


def test_writable_hole_reaches_its_metadata_projection() -> None:
    # /synthesis is writable, so /.vfs/synthesis/... inherits the hole
    # through the alias candidate; unrelated meta paths stay read-only.
    pmap = PermissionMap(default="read", overrides=(("/synthesis", "read_write"),))
    assert check_writable(pmap, "write", Path("/.vfs/synthesis/notes.md")) is None
    denied = check_writable(pmap, "write", Path("/.vfs/other/notes.md"))
    assert denied is not None
    assert denied.errors[0].kind is VFSErrorKind.read_only


def test_explicit_metadata_rule_outranks_the_alias() -> None:
    pmap = PermissionMap(
        default="read",
        overrides=(("/synthesis", "read_write"), ("/.vfs/synthesis", "read")),
    )
    denied = check_writable(pmap, "write", Path("/.vfs/synthesis/notes.md"))
    assert denied is not None
    assert denied.errors[0].kind is VFSErrorKind.read_only
