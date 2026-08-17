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
import sys
from dataclasses import dataclass
from itertools import product
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple

from vfs.paths import Path, extract_extension, normalize_ext_channel, normalize_extension

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# Ceiling on the distinct arms one pattern may expand to; callers
# refuse an over-cap expansion loudly rather than fan it out.
MAX_PATTERN_ARMS: Final = 64

# One label per glob-language channel, shared by every site that mints a
# channel refusal — the vocabulary cannot drift per verb or per layer.
GLOB_CHANNEL_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {"pattern": "glob pattern", "globs": "grep glob", "globs_not": "glob exclusion"}
)


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

    def hits(self, path: str, name: str, ext: str | None) -> bool:
        """The same verdict as :meth:`matches`, off row facts already in hand.

        *name* and *ext* must be the path's own leaf name and derived
        extension (storage's stored columns mirror both by invariant) —
        no ``Path`` is minted on this arm. Parity with :meth:`matches`
        is pinned by test.
        """
        subject = path if self.by_path else name
        if self.regex.match(subject) is None:
            return False
        return not self.wanted_ext or (ext or "") in self.wanted_ext


# ---------------------------------------------------------------------------
# Validation and compilation
# ---------------------------------------------------------------------------


_METACHARS: Final = re.compile(r"[*?\[\]{}]")


def escape_glob(text: str) -> str:
    """Quote *text* so the pattern language reads it as literal path text.

    Class notation — ``[`` becomes ``[[]``, ``*`` becomes ``[*]`` — because
    the language has no escape character, and a one-member class survives
    every downstream parser (``[{]`` never opens a brace group, ``[]]``
    closes correctly). Every seam that splices a caller's *path* into
    pattern text routes it through here first: a path is addressed
    literally, never reinterpreted as glob syntax.
    """
    return _METACHARS.sub(r"[\g<0>]", text)


def glob_defect(pattern: str) -> str | None:
    """The refusable defect in *pattern*, or ``None`` when compilable.

    Three defect families, all silent false friends if let through:
    ``**`` inside a component (``a**b``, ``***``) — the stdlib
    collapses it to ``*``, hiding a typo'd recursion; an empty
    component (``/data/``, ``//x``, bare ``/``), which no stored path
    can ever satisfy; and malformed braces (unclosed ``{``, bare
    ``}``, empty ``{}``, nesting) — a bare brace outside a character
    class either alternates or refuses, never silently literal. A
    brace pattern is gated twice: structure on the raw text, then the
    component checks per expansion arm, the refusal naming the arm
    expansion manufactured (``x/{a,}`` yields the empty-component arm
    ``x/``). Loud refusal beats a false friend.
    """
    if "{" in pattern or "}" in pattern:
        parts, brace_defect = _parse_braces(pattern)
        if brace_defect is not None:
            return brace_defect
        if any(isinstance(part, tuple) for part in parts):
            for arm in _cross_product(parts, MAX_PATTERN_ARMS):
                if (defect := _component_defect(arm)) is not None:
                    return f"{defect} (expansion arm {arm!r})"
            return None
    return _component_defect(pattern)


def expand_pattern(pattern: str) -> tuple[str, ...]:
    """The defect-free pattern's brace expansion — plain arms, order kept.

    ``{a,b}`` alternates (each alternative is arbitrary brace-free
    pattern text, ``/`` included), groups cross-product left to right,
    and duplicates collapse to first appearance. A brace-free pattern
    returns itself. Collection stops one arm past
    :data:`MAX_PATTERN_ARMS`, so an over-cap expansion is detected
    without being materialized — callers refuse at the cap. Input must
    be defect-free, same contract as :func:`compile_glob`.
    """
    if "{" not in pattern:
        return (pattern,)
    parts, _defect = _parse_braces(pattern)
    return tuple(_cross_product(parts, MAX_PATTERN_ARMS))


def canonical_pattern(pattern: str) -> str:
    """The canonical anchored form every consumer shares.

    Any ``/`` anchors the pattern at the root and adjacent ``**``
    components collapse to one — the same form ``GlobFilter.pattern``
    carries, exposed for consumers that derive facts from the pattern
    text without compiling a regex.
    """
    return _canonical(pattern)


def compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile a defect-free pattern to its authoritative regex, canonicalized first."""
    return re.compile(_translate(_canonical(pattern), recursive=True))


def compile_filter(pattern: str, ext: tuple[str, ...]) -> GlobFilter:
    """Compile the shared filter: subject rule, canonical pattern, normalized ext set."""
    canonical = _canonical(pattern)
    return GlobFilter(
        pattern=canonical,
        by_path="/" in canonical,
        regex=compile_glob(pattern),
        wanted_ext=normalize_ext_channel(ext),
    )


# ---------------------------------------------------------------------------
# Path filtering — glob as a pure predicate over paths in hand
# ---------------------------------------------------------------------------


def passes_filters(
    path: Path,
    gates: list[GlobFilter],
    not_gates: list[GlobFilter],
    wanted: frozenset[str],
    unwanted: frozenset[str],
) -> bool:
    """Glob admission/exclusion and the ext facts, per candidate path.

    Carries no meta rule: enumeration liveness is the enumerating
    surface's concern (storage layers it on top), and paths already in
    a caller's hand are never hidden.
    """
    if gates and not any(gate.matches(path) for gate in gates):
        return False
    if any(gate.matches(path) for gate in not_gates):
        return False
    extension = extract_extension(path) or ""
    if wanted and extension not in wanted:
        return False
    return not (unwanted and extension in unwanted)


def passes_row_filters(
    path: str,
    name: str,
    ext: str | None,
    gates: list[GlobFilter],
    not_gates: list[GlobFilter],
    wanted: frozenset[str],
    unwanted: frozenset[str],
) -> bool:
    """The :func:`passes_filters` law over row facts already in hand.

    The hot-loop arm: storage passes each candidate's stored path,
    name, and extension columns — which mirror the path by invariant —
    so no ``Path`` is constructed per candidate. Same channel order,
    same verdicts; parity is pinned by test.
    """
    if gates and not any(gate.hits(path, name, ext) for gate in gates):
        return False
    if any(gate.hits(path, name, ext) for gate in not_gates):
        return False
    extension = ext or ""
    if wanted and extension not in wanted:
        return False
    return not (unwanted and extension in unwanted)


def filter_paths(paths: Sequence[Path], pattern: str, ext: tuple[str, ...] = ()) -> list[Path]:
    """The paths in *paths* the compiled *pattern* matches, order preserved.

    A pure predicate over paths already in a caller's hand — duplicates
    pass through, and no liveness rule applies (what a caller holds is
    never hidden). Callers gate ``glob_defect`` first; searching *under*
    paths is the scope channel's job, not this filter's.
    """
    gate = compile_filter(pattern, ext)
    return [path for path in paths if gate.matches(path)]


# ---------------------------------------------------------------------------
# Derived pattern facts
# ---------------------------------------------------------------------------


class DerivedExt(NamedTuple):
    """The extension fact a pattern's tail pins; build via :func:`derive_ext`.

    ``ext`` is normalized by the stored-extension law (lowercased);
    ``dot_suffix`` keeps the original case — the arm for pure-dotfile
    names, which carry no extension of their own.
    """

    ext: str
    dot_suffix: str


def derive_ext(pattern: str) -> DerivedExt | None:
    """The extension fact pinned by the pattern's tail, or ``None``.

    The tail is the literal run after the last segment's last wildcard
    character; a dot inside it with characters after fixes the extension
    of every possible match, normalized by the same law stored
    extensions obey. The dot may open the tail — it marks a suffix of
    matched names, not a whole name, so the dotfile rule does not apply.
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
    return DerivedExt(ext=ext, dot_suffix=literal[dot:])


# ---------------------------------------------------------------------------
# Composition and residuation — the router's pattern algebra
# ---------------------------------------------------------------------------


def effective_pattern(root: Path, pattern: str) -> str:
    """Resolve *pattern* under one scope *root* to its namespace coordinates.

    Name-arm patterns are coordinate-free and pass through untouched. A
    path-arm pattern anchors relative to the root — a leading ``/``
    means the root itself, per the find/rg shape — and joins under it:
    ``effective_pattern("/data", "src/*.py") == "/data/src/*.py"``. For
    the root ``/`` this reduces to plain anchoring. The root is a
    *path*, immune to glob syntax: its text crosses into the pattern
    through :func:`escape_glob`, so ``/data/[x]`` addresses exactly the
    directory named ``[x]``.
    """
    if "/" not in pattern:
        return pattern
    anchored = _anchor(pattern)
    base = escape_glob(str(root))
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
    ``root/**/**``), so canonicalization runs downstream, here. The
    root's text is glob-escaped, same law as :func:`effective_pattern`.
    """
    if "/" not in pattern:
        base = escape_glob(str(root))
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


def _component_defect(pattern: str) -> str | None:
    """The component-shaped defect in a brace-free pattern, or ``None``."""
    components = pattern.split("/")
    for index, component in enumerate(components):
        if "**" in component and component != "**":
            return f"'**' inside a component ({component!r}) — use '**' as a whole path segment"
        if not component and not (index == 0 and len(components) > 1):
            return "empty component — every '/' must separate non-empty segments"
    return None


def _parse_braces(pattern: str) -> tuple[list[str | tuple[str, ...]], str | None]:
    """Split *pattern* into literal runs and alternation groups.

    Character classes are opaque — ``[{]`` never opens a group — and a
    comma splits only at group top level. The second item is the brace
    defect, or ``None``; a defect leaves the parse partial.
    """
    parts: list[str | tuple[str, ...]] = []
    buffer: list[str] = []
    alternatives: list[str] | None = None
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "[" and (end := _class_end(pattern, index)) is not None:
            buffer.append(pattern[index : end + 1])
            index = end + 1
            continue
        if char == "{":
            if alternatives is not None:
                return parts, "nested braces — a brace group cannot contain '{'"
            parts.append("".join(buffer))
            buffer, alternatives = [], []
        elif char == "}":
            if alternatives is None:
                return parts, "unmatched '}' — no open brace group"
            alternatives.append("".join(buffer))
            buffer = []
            if alternatives == [""]:
                return parts, "empty brace group '{}' — a group needs an alternative"
            parts.append(tuple(alternatives))
            alternatives = None
        elif char == "," and alternatives is not None:
            alternatives.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
        index += 1
    if alternatives is not None:
        return parts, "unclosed '{' — every brace group needs its '}'"
    parts.append("".join(buffer))
    return parts, None


def _class_end(pattern: str, start: int) -> int | None:
    """Index of the ``]`` closing the class opened at *start*, or ``None`` when literal."""
    index = start + 1
    if index < len(pattern) and pattern[index] in "!^":
        index += 1
    if index < len(pattern) and pattern[index] == "]":
        index += 1
    end = pattern.find("]", index)
    return end if end != -1 else None


def _cross_product(parts: Sequence[str | tuple[str, ...]], limit: int) -> list[str]:
    """Deduped left-to-right cross-product, stopping one arm past *limit*."""
    pools = [(part,) if isinstance(part, str) else tuple(dict.fromkeys(part)) for part in parts]
    arms: dict[str, None] = {}
    for combo in product(*pools):
        arms["".join(combo)] = None
        if len(arms) > limit:
            break
    return list(arms)


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
    return re.fullmatch(_translate(component, recursive=False), segment) is not None


# The stdlib translators switched their end-of-string anchor to \z in 3.14;
# mirror them exactly (\z is a re.error before 3.14).
_END_OF_STRING: Final = r"\z" if sys.version_info >= (3, 14) else r"\Z"


def _translate(pattern: str, *, recursive: bool) -> str:
    """Regex source for *pattern* — segment-aware, dotfiles ordinary, ``/`` seps.

    An original implementation of the ``glob.translate`` contract (stdlib
    3.13+, newer than the project floor), fixed to the one call shape every
    consumer uses: hidden files included, ``/`` the only separator. Input
    is defect-gated and canonical — no ``**`` inside a component, no
    adjacent ``**`` — so the stdlib's collapses for both are omitted here.
    Parity with the stdlib is pinned textually by the differential test
    wherever the stdlib function exists. ``**`` as a whole component spans
    zero or more segments only under *recursive*; a bare ``*`` component
    requires a non-empty segment.
    """
    parts = pattern.split("/")
    last = len(parts) - 1
    pieces: list[str] = []
    for index, part in enumerate(parts):
        if recursive and part == "**":
            pieces.append(".*" if index == last else "(?:.+/)?")
            continue
        if part == "*":
            pieces.append("[^/]+")
        elif part:
            pieces.append(_translate_component(part))
        if index < last:
            pieces.append("/")
    return "(?s:" + "".join(pieces) + ")" + _END_OF_STRING


def _translate_component(component: str) -> str:
    """One component's regex source: wildcards, classes, escaped literals."""
    pieces: list[str] = []
    index = 0
    while index < len(component):
        char = component[index]
        index += 1
        if char == "*":
            pieces.append("[^/]*")
        elif char == "?":
            pieces.append("[^/]")
        elif char == "[" and (end := _component_class_end(component, index)) is not None:
            pieces.append(_translate_class(component[index:end]))
            index = end + 1
        else:
            pieces.append(re.escape(char))
    return "".join(pieces)


def _component_class_end(component: str, start: int) -> int | None:
    """Index of the ``]`` closing the class opened at *start*, or ``None`` when literal.

    The fnmatch scan: only ``!`` negates (a leading ``^`` is an ordinary
    member), unlike :func:`_class_end`, whose ``!^`` opacity serves the
    brace parser.
    """
    index = start
    if index < len(component) and component[index] == "!":
        index += 1
    if index < len(component) and component[index] == "]":
        index += 1
    end = component.find("]", index)
    return end if end != -1 else None


def _translate_class(stuff: str) -> str:
    """One class interior's regex source, empty ranges pruned fnmatch-style."""
    if "-" not in stuff:
        body = stuff.replace("\\", r"\\")
    else:
        chunks: list[str] = []
        start = 0
        probe = 2 if stuff[0] == "!" else 1
        while (hit := stuff.find("-", probe)) >= 0:
            chunks.append(stuff[start:hit])
            # A range consumes the dash and its bounds; probe past them.
            start, probe = hit + 1, hit + 3
        if rest := stuff[start:]:
            chunks.append(rest)
        else:
            chunks[-1] += "-"
        for k in range(len(chunks) - 1, 0, -1):
            # An inverted range ([z-a]) is invalid regex; merge it away.
            if chunks[k - 1][-1] > chunks[k][0]:
                chunks[k - 1] = chunks[k - 1][:-1] + chunks[k][1:]
                del chunks[k]
        body = "-".join(s.replace("\\", r"\\").replace("-", r"\-") for s in chunks)
    body = re.sub(r"([&~|])", r"\\\1", body)
    if not body:
        return "(?!)"
    if body == "!":
        # A negated empty range matches any character (fnmatch's rule);
        # falling through would emit the invalid class [^].
        return "."
    if body[0] == "!":
        body = "^" + body[1:]
    elif body[0] in "^[":
        body = "\\" + body
    return "[" + body + "]"
