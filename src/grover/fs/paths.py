"""Path format utilities for chunk and version references.

Canonical formats:
- Chunk ref:   ``/src/auth.py#login``
- Version ref: ``/src/auth.py@3``

These are synthetic path identifiers — not real VFS paths. They encode
a base file path plus a chunk symbol or version number.
"""

from __future__ import annotations


def build_chunk_ref(file_path: str, chunk_id: str) -> str:
    """Build the canonical chunk reference path for a symbol.

    >>> build_chunk_ref("/src/auth.py", "login")
    '/src/auth.py#login'
    >>> build_chunk_ref("/src/auth.py", "Client.connect")
    '/src/auth.py#Client.connect'
    """
    return f"{file_path}#{chunk_id}"


def build_version_ref(file_path: str, version: int) -> str:
    """Build a version reference path.

    >>> build_version_ref("/src/auth.py", 3)
    '/src/auth.py@3'
    """
    return f"{file_path}@{version}"


def parse_ref(path: str) -> tuple[str, str | None, int | None]:
    """Parse a path that may contain ``#chunk`` or ``@version`` suffixes.

    Returns ``(base_path, chunk_id, version)``. At most one of *chunk_id*
    or *version* will be non-``None``.

    >>> parse_ref("/src/auth.py#login")
    ('/src/auth.py', 'login', None)
    >>> parse_ref("/src/auth.py@3")
    ('/src/auth.py', None, 3)
    >>> parse_ref("/src/auth.py")
    ('/src/auth.py', None, None)
    """
    # Check for # first — a chunk ref cannot also be a version ref.
    # The suffix after # must not contain / (that would be a # in a dir name).
    hash_idx = path.rfind("#")
    if hash_idx > 0:
        chunk_id = path[hash_idx + 1 :]
        if chunk_id and "/" not in chunk_id:
            return path[:hash_idx], chunk_id, None

    # Check for @ version suffix.
    at_idx = path.rfind("@")
    if at_idx > 0:
        base = path[:at_idx]
        ver_str = path[at_idx + 1 :]
        try:
            version = int(ver_str)
            return base, None, version
        except ValueError:
            pass

    return path, None, None


def is_chunk_ref(path: str) -> bool:
    """Return ``True`` if *path* contains a ``#chunk`` suffix."""
    hash_idx = path.rfind("#")
    if hash_idx <= 0:
        return False
    suffix = path[hash_idx + 1 :]
    return bool(suffix) and "/" not in suffix


def is_version_ref(path: str) -> bool:
    """Return ``True`` if *path* contains an ``@version`` suffix."""
    at_idx = path.rfind("@")
    if at_idx <= 0:
        return False
    ver_str = path[at_idx + 1 :]
    try:
        int(ver_str)
        return True
    except ValueError:
        return False


def strip_ref(path: str) -> str:
    """Return the base file path, stripping any ``#chunk`` or ``@version`` suffix.

    >>> strip_ref("/src/auth.py#login")
    '/src/auth.py'
    >>> strip_ref("/src/auth.py@3")
    '/src/auth.py'
    >>> strip_ref("/src/auth.py")
    '/src/auth.py'
    """
    base, _, _ = parse_ref(path)
    return base
