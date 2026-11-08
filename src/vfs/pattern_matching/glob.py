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
silent ``*``. Matching runs on the engine's native glob program, which
never backtracks: one match costs at most a fixed number of word
operations per character of the subject, whatever the wildcards.

    try:
        arms = expand_pattern(pattern)      # gate, brace-expand, cap — or PatternError
    except PatternError as exc:
        ...  # classify invalid, prefixed with the channel label; touch no rows
    gates = [compile_filter(arm, ext=()) for arm in arms]
    kept = [p for p in candidates if any(g.matches(p) for g in gates)]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import product
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, Protocol

from vfs.native import glob_program
from vfs.paths import Path, extract_extension, normalize_ext_channel, normalize_extension

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# Ceiling on the distinct arms one pattern may expand to; callers
# refuse an over-cap expansion loudly rather than fan it out.
MAX_PATTERN_ARMS: Final = 64

# The glob-language channels: glob's pattern, grep's globs, and the
# exclusions both verbs share; one label each, shared by every site that
# mints a channel refusal — the vocabulary cannot drift per verb or layer.
GlobChannel = Literal["pattern", "globs", "globs_not"]
GLOB_CHANNEL_LABELS: Final[Mapping[GlobChannel, str]] = MappingProxyType(
    {"pattern": "glob pattern", "globs": "grep glob", "globs_not": "glob exclusion"}
)

# The row facts `passes_row_filters` reads beside the path: storage rides
# these columns on every candidate fetch so the gate never builds a Path.
ROW_GATE_FIELDS: Final = frozenset({"name", "ext"})

# One program atom: an op and its code-point ranges (see `vfs.native.glob_program`).
GlobAtom = tuple[str, list[tuple[str, str]]]


class GlobProgram(Protocol):
    """The engine's compiled matcher for one glob pattern."""

    def is_match(self, subject: str) -> bool:
        """Whether the whole *subject* matches, from its first character."""
        ...


class PatternError(ValueError):
    """A pattern outside its language, carrying the refusal reason.

    One exception for both pattern languages: the glob expander raises
    it with the offending pattern and the defect (``'{a,b': unclosed
    '{' — …``); the grep verifier raises it with the reason alone. The
    message carries identity and diagnosis and nothing else — the
    channel label and the verb are the caller's to prefix, so a refusal
    reads ``glob exclusion '{a,b': unclosed '{' — …`` on one surface and
    ``grep glob '{a,b': …`` on another from the same text.
    """


@dataclass(frozen=True)
class GlobFilter:
    """The compiled per-candidate predicate; build via :func:`compile_filter`.

    ``pattern`` is the anchored form — the one the SQL prefilter must
    translate, so prefilter and authority read the same text.
    """

    pattern: str
    by_path: bool
    program: GlobProgram
    wanted_ext: frozenset[str]

    def matches(self, path: Path) -> bool:
        """Compiled-program authority over the subject, then the path-derived ext gate."""
        subject = str(path) if self.by_path else path.name
        if not self.program.is_match(subject):
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
        if not self.program.is_match(subject):
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
    """Gate, brace-expand, and cap one pattern — its plain arms, or :class:`PatternError`.

    The one admission call every surface shares: the defect gate
    (:func:`glob_defect`) runs first, then ``{a,b}`` alternates (each
    alternative is arbitrary brace-free pattern text, ``/`` included),
    groups cross-product left to right, and duplicates collapse to
    first appearance. A brace-free pattern returns itself, so the call
    is idempotent over its own output — a surface handed pre-expanded
    arms loses nothing by expanding again. Collection stops one arm
    past :data:`MAX_PATTERN_ARMS` and refuses, so an over-cap expansion
    is detected without being materialized. The refusal names the
    pattern and the defect; the channel label is the caller's.
    """
    defect = glob_defect(pattern)
    if defect is not None:
        raise PatternError(f"{pattern!r}: {defect}")
    if "{" not in pattern:
        return (pattern,)
    parts, _defect = _parse_braces(pattern)
    arms = _cross_product(parts, MAX_PATTERN_ARMS)
    if len(arms) > MAX_PATTERN_ARMS:
        cap = f"expands past the arm cap ({MAX_PATTERN_ARMS}) — narrow the alternation or split the call"
        raise PatternError(f"{pattern!r}: {cap}")
    return tuple(arms)


def expand_channel(channel: GlobChannel, patterns: Sequence[str]) -> tuple[str, ...]:
    """One glob channel's deduped arms, or :class:`PatternError` naming the channel.

    The channel form of :func:`expand_pattern`, for every surface that
    admits a whole channel at once — the router's verbs and the storage
    seam alike: each pattern is admitted in turn, the first refusal
    refuses the channel whole, prefixed with the channel's one label
    (``glob exclusion '{a': unclosed '{' — …``). Only the producing verb
    stays the caller's to stamp.
    """
    expanded: list[str] = []
    for pattern in patterns:
        try:
            expanded.extend(expand_pattern(pattern))
        except PatternError as exc:
            raise PatternError(f"{GLOB_CHANNEL_LABELS[channel]} {exc}") from exc
    return tuple(dict.fromkeys(expanded))


def canonical_pattern(pattern: str) -> str:
    """The canonical anchored form every consumer shares.

    Any ``/`` anchors the pattern at the root and adjacent ``**``
    components collapse to one — the same form ``GlobFilter.pattern``
    carries, exposed for consumers that derive facts from the pattern
    text without compiling a program.
    """
    return _canonical(pattern)


def compile_glob(pattern: str) -> GlobProgram:
    """Compile a defect-free pattern to its authoritative native program, canonicalized first.

    The program's ``is_match(subject)`` answers what ``re.match`` over the
    stdlib's ``glob.translate`` text answers, without backtracking.
    """
    return glob_program(_program(_canonical(pattern), recursive=True))


def compile_filter(pattern: str, ext: tuple[str, ...]) -> GlobFilter:
    """Compile the shared filter: subject rule, canonical pattern, normalized ext set."""
    canonical = _canonical(pattern)
    return GlobFilter(
        pattern=canonical,
        by_path="/" in canonical,
        program=compile_glob(pattern),
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
    for char in pattern:
        if 0xD800 <= ord(char) <= 0xDFFF:
            return f"lone surrogate: U+{ord(char):04X}"
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
    return glob_program(_program(component, recursive=False)).is_match(segment)


def _program(pattern: str, *, recursive: bool) -> list[GlobAtom]:
    """The engine program for *pattern* — the walk the stdlib's ``glob.translate`` makes.

    Fixed to the one call shape every consumer uses: hidden files
    included, ``/`` the only separator. Input is defect-gated and
    canonical — no ``**`` inside a component, no adjacent ``**``. Under
    *recursive* a whole-component ``**`` is ``mid`` (zero or more whole
    segments) or, last, ``tail`` (anything); a bare ``*`` component
    requires a non-empty segment (``one`` then ``star``).
    """
    parts = pattern.split("/")
    last = len(parts) - 1
    atoms: list[GlobAtom] = []
    for index, part in enumerate(parts):
        if recursive and part == "**":
            atoms.append(("tail", []) if index == last else ("mid", []))
            continue
        if part == "*":
            atoms.extend([("one", []), ("star", [])])
        elif part:
            atoms.extend(_component_atoms(part))
        if index < last:
            atoms.append(("sep", []))
    return atoms


def _component_atoms(component: str) -> list[GlobAtom]:
    """One component's atoms: wildcards, classes, literal characters."""
    atoms: list[GlobAtom] = []
    index = 0
    while index < len(component):
        char = component[index]
        index += 1
        if char == "*":
            atoms.append(("star", []))
        elif char == "?":
            atoms.append(("one", []))
        elif char == "[" and (end := _component_class_end(component, index)) is not None:
            atoms.append(_class_atom(component[index:end]))
            index = end + 1
        else:
            atoms.append(("lit", [(char, char)]))
    return atoms


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


def _class_atom(stuff: str) -> GlobAtom:
    """One class interior's atom, its members the ones fnmatch's regex class names.

    The fnmatch chunk walk: a ``-`` past the first member splits chunks,
    and an inverted range (``z-a``) is merged away. The last character
    of each chunk and the first of the next bound a range; every other
    character, ``-`` included, is a member alone. The class is negated
    when the merged text begins with ``!`` — written or exposed by a
    merge (``[z-a!b]`` is ``[^b]``); when that ``!`` is the whole first
    chunk, the joining ``-`` is a member and bounds no range
    (``[--!!-!]`` is ``[^-!]``). An empty class never matches; a bare
    ``!`` matches any character.
    """
    chunks = _class_chunks(stuff)
    text = "-".join(chunks)
    if not text:
        return ("never", [])
    if text == "!":
        return ("dot", [])
    negated = text[0] == "!"
    if negated:
        chunks[0] = chunks[0][1:]
    members: list[tuple[str, str]] = []
    for k, chunk in enumerate(chunks):
        first = 0
        if k > 0:
            if negated and k == 1 and not chunks[0]:
                members.append(("-", "-"))
            else:
                members.append((chunks[k - 1][-1], chunk[0]))
                first = 1
        last = len(chunk) - 1 if k < len(chunks) - 1 else len(chunk)
        members.extend((char, char) for char in chunk[first:last])
    return ("nclass" if negated else "class", _merged_ranges(members))


def _class_chunks(stuff: str) -> list[str]:
    """The class interior split at its range dashes, inverted ranges merged away."""
    if "-" not in stuff:
        return [stuff]
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
        if chunks[k - 1][-1] > chunks[k][0]:
            chunks[k - 1] = chunks[k - 1][:-1] + chunks[k][1:]
            del chunks[k]
    return chunks


def _merged_ranges(members: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Sorted, disjoint ranges covering *members*; touching ranges join."""
    merged: list[tuple[str, str]] = []
    for lo, hi in sorted(members):
        if merged and ord(lo) <= ord(merged[-1][1]) + 1:
            if hi > merged[-1][1]:
                merged[-1] = (merged[-1][0], hi)
            continue
        merged.append((lo, hi))
    return merged
