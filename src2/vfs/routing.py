"""Mount-routing helpers for ``glob`` / ``grep`` fanout.

Mount paths on a single router are single-segment by construction (see
:meth:`vfs.base.VirtualFileSystem._normalize_mount_path`); the helpers
below assume that. Multi-level chains are router-to-router, with each
level applying its own rewrite recursively as it dispatches.

Strategy used by :class:`vfs.base.VirtualFileSystem` for absolute
glob patterns and literal-prefix path filters:

1. **Exact rewrite** when provable — literal-prefix match against the
   mount, or single-segment glob consumption against the mount name.
2. **Safe-superset query + router-side authoritative re-filter** when
   the pattern can't be exactly consumed (the leading segment is
   ``**``, which absorbs zero or more path segments and is ambiguous).
3. **Skip the mount entirely** when the pattern provably cannot match
   anything inside it (literal segment that does not match the mount
   name, no wildcard escape hatch).

These helpers are pure and unaware of the router that calls them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vfs.patterns import compile_glob

if TYPE_CHECKING:
    import re

    from vfs.base import VirtualFileSystem


@dataclass(frozen=True)
class GlobMountPlan:
    mount_path: str
    filesystem: VirtualFileSystem
    rewritten_pattern: str
    rewritten_paths: tuple[str, ...]
    needs_post_filter: bool


@dataclass(frozen=True)
class GrepMountPlan:
    mount_path: str
    filesystem: VirtualFileSystem
    rewritten_paths: tuple[str, ...]
    mount_globs: tuple[str, ...]
    mount_globs_not: tuple[str, ...]
    post_include_regexes: tuple[re.Pattern[str], ...]
    post_exclude_regexes: tuple[re.Pattern[str], ...]
    needs_router_filter: bool


def first_segment(path: str) -> tuple[str, str]:
    """Split an absolute path into ``(first_segment, rest_with_leading_slash)``.

    ``/foo/bar`` → ``('foo', '/bar')``; ``/foo`` → ``('foo', '/')``;
    ``/`` → ``('', '/')``. Non-absolute paths return ``('', path)``.
    """
    if not path.startswith("/") or path == "/":
        return "", path
    rest = path[1:]
    slash = rest.find("/")
    if slash == -1:
        return rest, "/"
    return rest[:slash], rest[slash:]


def glob_segment_matches(segment: str, name: str) -> bool:
    """True if the single-segment glob *segment* matches *name*.

    Returns False for segments containing ``**`` because those represent
    zero-or-more path segments, not a single segment, and would need
    superset-fallback handling at the caller.
    """
    if "**" in segment:
        return False
    regex = compile_glob("/" + segment)
    if regex is None:
        return False
    return regex.match("/" + name) is not None


def rewrite_glob_for_mount(pattern: str, mount_path: str) -> tuple[str | None, bool]:
    """Try to rewrite a glob *pattern* for dispatch to a single mount.

    Returns ``(rewritten_pattern, needs_post_filter)``:

    - ``("/relative", False)`` — exact rewrite. Dispatch as-is and trust
      the mount's result without further filtering.
    - ``("/**", True)`` — broad superset. Dispatch ``/**`` to the mount
      and re-apply the original pattern at the router after rebasing.
    - ``(None, False)`` — pattern provably cannot match anything inside
      this mount. Skip the mount entirely.

    Relative patterns (no leading ``/``) pass through unchanged with no
    post-filter; every mount sees them as-is and matches against its
    own mount-relative paths.
    """
    if not pattern.startswith("/"):
        return pattern, False

    normalized = pattern.rstrip("/") or "/"

    # Literal-prefix match: pattern is exactly the mount or strictly under it.
    if normalized == mount_path:
        return "/", False
    if normalized.startswith(mount_path + "/"):
        return normalized[len(mount_path) :], False

    # Segment-aware consumption of the first absolute segment.
    first, rest = first_segment(normalized)
    if first == "":
        return None, False
    if "**" in first:
        # Ambiguous: ``**`` matches zero or more segments, so the first
        # segment could absorb the mount or could leave it unconsumed.
        # Fall back to the safe superset and let the router re-filter.
        return "/**", True

    mount_name = mount_path.lstrip("/")
    if glob_segment_matches(first, mount_name):
        return rest, False

    return None, False


def rewrite_path_for_mount(path: str, mount_path: str) -> str | None:
    """Strip *mount_path* from a literal *path* prefix.

    Returns the mount-relative path, or ``None`` if *path* doesn't
    target this mount. Relative paths pass through unchanged so the
    backend's ``_scope_filter_prefix`` can normalize them.
    """
    if not path.startswith("/"):
        return path
    normalized = path.rstrip("/") or "/"
    if normalized == mount_path:
        return "/"
    if normalized.startswith(mount_path + "/"):
        return normalized[len(mount_path) :]
    return None
