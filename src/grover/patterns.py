"""Glob pattern matching — SQL LIKE translation and regex-based glob matching."""

from __future__ import annotations

import re
from dataclasses import dataclass

from grover.paths import normalize_path

_GLOB_METACHARS = frozenset("*?[{")


def glob_to_sql_like(pattern: str, base_path: str = "/") -> str | None:
    """Translate a glob pattern to a SQL LIKE clause for pre-filtering.

    Returns None for patterns containing ``[seq]`` character classes,
    which cannot be expressed in LIKE. The caller should fall back to
    loading all paths and filtering with ``match_glob()``.

    This is a performance optimisation only — ``match_glob()`` is the
    authoritative filter.
    """
    if "[" in pattern:
        return None

    # Normalise base so we can prepend it
    base_path = normalize_path(base_path)

    # Build the full virtual pattern
    if pattern.startswith("/"):
        full = pattern
    elif base_path == "/":
        full = "/" + pattern
    else:
        full = base_path + "/" + pattern

    # Translate glob tokens → LIKE tokens
    like = ""
    i = 0
    while i < len(full):
        ch = full[i]
        if ch == "*":
            # ** → % (any depth), * → match within one segment
            if i + 1 < len(full) and full[i + 1] == "*":
                like += "%"
                i += 2
                # Skip trailing /
                if i < len(full) and full[i] == "/":
                    i += 1
                continue
            # Single * — we still use % here because LIKE has no
            # single-segment wildcard.  match_glob post-filters.
            like += "%"
        elif ch == "?":
            like += "_"
        elif ch == "%":
            like += "\\%"
        elif ch == "_":
            like += "\\_"
        else:
            like += ch
        i += 1

    return like


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a glob pattern to a compiled regex.

    - ``*`` matches any characters except ``/``
    - ``**`` matches any characters including ``/`` (zero or more path segments)
    - ``?`` matches a single character except ``/``
    - ``[seq]`` matches any character in *seq*
    """
    result = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # **/ → zero or more directory levels
                if i + 2 < len(pattern) and pattern[i + 2] == "/":
                    result += "(?:.*/)?"
                    i += 3
                else:
                    result += ".*"
                    i += 2
                continue
            result += "[^/]*"
        elif ch == "?":
            result += "[^/]"
        elif ch == "[":
            j = i + 1
            while j < len(pattern) and pattern[j] != "]":
                j += 1
            if j >= len(pattern):
                # Unclosed bracket — treat [ as literal
                result += re.escape(ch)
            else:
                bracket = pattern[i : j + 1]
                # Translate glob negation [!...] to regex negation [^...]
                if bracket.startswith("[!"):
                    bracket = "[^" + bracket[2:]
                result += bracket
                i = j
        else:
            result += re.escape(ch)
        i += 1
    return re.compile("^" + result + "$")


def compile_glob(pattern: str, base_path: str = "/") -> re.Pattern[str] | None:
    """Compile a glob *pattern* into a regex for repeated matching.

    Returns ``None`` if the pattern is malformed.  Use the returned
    regex with ``regex.match(path) is not None`` to test individual
    paths efficiently without recompiling.
    """
    base_path = normalize_path(base_path)

    if pattern.startswith("/"):
        full_pattern = pattern
    elif base_path == "/":
        full_pattern = "/" + pattern
    else:
        full_pattern = base_path + "/" + pattern

    try:
        return _glob_to_regex(full_pattern)
    except re.error:
        return None


@dataclass(frozen=True)
class GlobDecomposition:
    """Structural breakdown of a glob for index-seek pushdown.

    - ``prefix``: leading literal path anchor (e.g. ``"/src"``) or ``None``.
    - ``ext``: ``(ext,)`` when the pattern tail is ``**/*.<literal-ext>``;
      otherwise ``()``.
    - ``files_only``: ``True`` iff the decomposer recovered an ``ext`` from
      the tail. The caller can then narrow ``kind`` to files and drop the
      authoritative regex, because ``ext IS NULL`` on directory rows.
    - ``residual_regex``: the compiled authoritative regex. ``None`` only
      when the pattern is fully expressible as ``prefix + **/*.<ext>`` so
      the caller can drop ``REGEXP_LIKE`` entirely.
    """

    prefix: str | None
    ext: tuple[str, ...]
    files_only: bool
    residual_regex: re.Pattern[str] | None


def _is_literal_ext_tail(segment: str) -> str | None:
    """Return the literal ext iff *segment* has shape ``*.<literal-ext>``.

    The ext must contain no glob metacharacters and no dots. Returns the
    lowercased ext with length ≤ 32 (matching ``extract_extension``), or
    ``None`` if the segment does not match.
    """
    if not segment.startswith("*."):
        return None
    ext = segment[2:]
    if not ext or len(ext) > 32:
        return None
    for ch in ext:
        if ch in _GLOB_METACHARS or ch == ".":
            return None
    return ext.lower()


def decompose_glob(pattern: str, base_path: str = "/") -> GlobDecomposition:
    """Decompose a glob into a literal prefix and trailing ``*.<ext>``.

    This is a conservative structural analysis used by SQL backends to
    push the glob through the ``(ext, kind)`` composite index and a
    sargable ``LIKE`` prefix predicate. Anything not recognised falls
    through to a compiled residual regex, so correctness is always
    preserved — the optimisation is opportunistic.
    """
    base_path = normalize_path(base_path)

    if pattern.startswith("/"):
        full_pattern = pattern
    elif base_path == "/":
        full_pattern = "/" + pattern
    else:
        full_pattern = base_path + "/" + pattern

    stripped = full_pattern.lstrip("/")
    parts = stripped.split("/") if stripped else []

    literal_count = 0
    for seg in parts:
        if any(ch in _GLOB_METACHARS for ch in seg):
            break
        literal_count += 1

    literal_segments = parts[:literal_count]
    remainder = parts[literal_count:]

    prefix: str | None = "/" + "/".join(literal_segments) if literal_segments else None

    ext: tuple[str, ...] = ()
    files_only = False
    residual: re.Pattern[str] | None

    if len(remainder) == 2 and remainder[0] == "**":
        tail_ext = _is_literal_ext_tail(remainder[1])
        if tail_ext is not None:
            ext = (tail_ext,)
            files_only = True
            residual = None
        else:
            residual = compile_glob(pattern, base_path)
    else:
        residual = compile_glob(pattern, base_path)

    return GlobDecomposition(
        prefix=prefix,
        ext=ext,
        files_only=files_only,
        residual_regex=residual,
    )


def match_glob(path: str, pattern: str, base_path: str = "/") -> bool:
    """Authoritative glob match for a virtual path against *pattern*.

    Handles ``*``, ``?``, ``[seq]``, and ``**`` (recursive).
    Uses a regex translation that correctly prevents ``*`` from
    crossing directory boundaries while allowing ``**`` to match
    across any number of path segments.

    For matching many paths against the same pattern, use
    :func:`compile_glob` to avoid repeated regex compilation.
    """
    regex = compile_glob(pattern, base_path)
    if regex is None:
        return False
    return regex.match(path) is not None
