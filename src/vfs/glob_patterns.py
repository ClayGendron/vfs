"""The glob pattern language — one compile chokepoint every consumer shares.

Segment-aware semantics, the ones every coding agent already knows:
``*`` matches within one path segment, ``?`` one non-separator
character, a whole-component ``**`` spans any number of segments, and
``[seq]``/``[!seq]`` character classes as usual. Matching is
case-sensitive and dotfiles are ordinary rows. Any ``/`` anchors a
pattern at the root — ``src/*.py`` means ``/src/*.py``, ``*/x.py``
pins depth one, and the any-depth idiom is an explicit leading ``**/``
— while a slash-free pattern matches leaf names at any depth. The ext
filter reads the **path-derived** extension, deliberately never a
stored column. ``**`` inside a component is a refusable defect, not a
silent ``*``.

    if (defect := glob_defect(pattern)) is not None:
        ...  # classify invalid, touch no rows
    glob = compile_filter(pattern, ext=())
    kept = [p for p in candidates if glob.matches(p)]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from glob import translate

from vfs.paths import Path, extract_extension, normalize_extension


@dataclass(frozen=True)
class GlobFilter:
    """The compiled per-candidate predicate; build via :func:`compile_filter`.

    ``pattern`` is the anchored form — the one the SQL prefilter must
    translate, so prefilter and authority read the same text.
    """

    pattern: str
    by_path: bool
    regex: re.Pattern[str]
    wanted_ext: frozenset[str]

    def matches(self, path: Path) -> bool:
        """Compiled-regex authority over the subject, then the path-derived ext gate."""
        subject = str(path) if self.by_path else path.name
        if self.regex.match(subject) is None:
            return False
        return not self.wanted_ext or (extract_extension(path) or "") in self.wanted_ext


# ---------------------------------------------------------------------------
# Validation and compilation
# ---------------------------------------------------------------------------


def glob_defect(pattern: str) -> str | None:
    """The refusable defect in *pattern*, or ``None`` when compilable.

    Two defects, both silent false friends if let through: ``**``
    inside a component (``a**b``, ``***``) — the stdlib collapses it to
    ``*``, hiding a typo'd recursion — and an empty component
    (``/data/``, ``//x``, bare ``/``), which no stored path can ever
    satisfy. Loud refusal beats a false friend.
    """
    components = pattern.split("/")
    for index, component in enumerate(components):
        if "**" in component and component != "**":
            return f"'**' inside a component ({component!r}) — use '**' as a whole path segment"
        if not component and not (index == 0 and len(components) > 1):
            return "empty component — every '/' must separate non-empty segments"
    return None


def compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile a defect-free pattern to its authoritative regex, canonicalized first."""
    return re.compile(translate(_canonical(pattern), recursive=True, include_hidden=True, seps="/"))


def compile_filter(pattern: str, ext: tuple[str, ...]) -> GlobFilter:
    """Compile the shared filter: subject rule, canonical pattern, normalized ext set."""
    canonical = _canonical(pattern)
    return GlobFilter(
        pattern=canonical,
        by_path="/" in canonical,
        regex=compile_glob(pattern),
        wanted_ext=frozenset(e.lstrip(".").lower() for e in ext),
    )


# ---------------------------------------------------------------------------
# Derived pattern facts
# ---------------------------------------------------------------------------


def derive_ext(pattern: str) -> tuple[str, str] | None:
    """(lowercased ext, literal dot-suffix) pinned by the pattern's tail, or ``None``.

    The tail is the literal run after the last segment's last wildcard
    character; a dot inside it with characters after fixes the extension
    of every possible match, normalized by the same law stored
    extensions obey. The dot may open the tail — it marks a suffix of
    matched names, not a whole name, so the dotfile rule does not apply;
    the dot-suffix (original case) is the arm for pure-dotfile names,
    which carry no extension of their own.
    """
    segment = pattern.rsplit("/", 1)[-1]
    cut = max((i for i, ch in enumerate(segment) if ch in "*?]"), default=-1)
    literal = segment[cut + 1 :]
    dot = literal.rfind(".")
    if dot < 0:
        return None
    ext = normalize_extension(literal[dot + 1 :])
    if ext is None:
        return None
    return ext, literal[dot:]


# ---------------------------------------------------------------------------
# Mount-seam residuation
# ---------------------------------------------------------------------------


def effective_pattern(root: Path, pattern: str) -> str:
    """Resolve *pattern* under one scope *root* to its namespace coordinates.

    Name-arm patterns are coordinate-free and pass through untouched. A
    path-arm pattern anchors relative to the root — a leading ``/``
    means the root itself, per the find/rg shape — and joins under it:
    ``effective_pattern("/data", "src/*.py") == "/data/src/*.py"``. For
    the root ``/`` this reduces to plain anchoring.
    """
    if "/" not in pattern:
        return pattern
    anchored = _anchor(pattern)
    base = str(root)
    return anchored if base == "/" else base + anchored


def composed_pattern(root: Path, pattern: str) -> str:
    """Compose *pattern* under one scope *root* into one spatial pattern.

    The whole scoping story as pattern text: a path-arm pattern anchors
    under the root via :func:`effective_pattern`; a name-arm pattern —
    coordinate-free on its own — goes spatial as ``root + /**/ +
    pattern``, the gitignore float spelled out, so ``("/a/data",
    "*.csv")`` composes to ``"/a/data/**/*.csv"`` (which still matches
    direct children: ``**`` spans zero segments). Composition can
    manufacture adjacent ``**`` (name-arm ``**`` composes to
    ``root/**/**``), so canonicalization runs downstream, here.
    """
    if "/" not in pattern:
        base = str(root)
        return _canonical(("" if base == "/" else base) + "/**/" + pattern)
    return _canonical(effective_pattern(root, pattern))


def residuals(pattern: str, mount_path: Path) -> frozenset[tuple[str, ...]]:
    """Residual component-tuples of an anchored *pattern* against one bind path.

    The segment-wise derivative: a literal, wildcard, or class component
    consumes a matching mount segment; ``**`` both survives consumption
    and may match zero components, so one bind segment can leave two
    live derivatives. The empty set is a dead mount — no dispatch. An
    empty tuple in the set is the bind point itself: that row is the
    parent's stored mount-point directory, never a child dispatch. A
    live residual renders back via :func:`render_residual`. Input is
    canonicalized, so the zero-match arm never faces adjacent ``**``.
    """
    state: set[tuple[str, ...]] = {tuple(_canonical(pattern).strip("/").split("/"))}
    for segment in (part for part in str(mount_path).split("/") if part):
        advanced: set[tuple[str, ...]] = set()
        for candidate in state:
            if not candidate:
                continue
            head, rest = candidate[0], candidate[1:]
            if head == "**":
                advanced.add(candidate)
                if rest and rest[0] != "**" and _component_matches(rest[0], segment):
                    advanced.add(rest[1:])
            elif _component_matches(head, segment):
                advanced.add(rest)
        state = advanced
    return frozenset(state)


def render_residual(components: tuple[str, ...]) -> str:
    """Render a live residual back to an entry-local anchored pattern."""
    return "/" + "/".join(components)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _anchor(pattern: str) -> str:
    """Gitignore-exact anchoring: any ``/`` anchors at the root; no ``/`` floats."""
    if "/" in pattern and not pattern.startswith("/"):
        return "/" + pattern
    return pattern


def _canonical(pattern: str) -> str:
    """Anchored form with adjacent ``**`` components collapsed to one.

    ``**/**`` matches exactly what one ``**`` matches, but the extra
    component would starve the residuation derivative's zero-match arm.
    """
    anchored = _anchor(pattern)
    if "/**/**" not in anchored:
        return anchored
    components: list[str] = []
    for component in anchored.split("/"):
        if component == "**" and components and components[-1] == "**":
            continue
        components.append(component)
    return "/".join(components)


def _component_matches(component: str, segment: str) -> bool:
    """One non-``**`` pattern component against one bind-path segment."""
    return re.fullmatch(translate(component, recursive=False, include_hidden=True, seps="/"), segment) is not None
