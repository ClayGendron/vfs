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

A call's rows are judged in batches, off the event loop: the call's
patterns become one :class:`GlobGates`, whose native set is built once
per call on a worker and judges every row of a stage in one hop
(``judge_rows`` in the storage offload seam), under the stage's wall.
The filter law then reads each row's verdict here, in Python.

    try:
        arms = expand_pattern(pattern)      # gate, brace-expand, cap — or PatternError
    except PatternError as exc:
        ...  # classify invalid, prefixed with the channel label; touch no rows
    gates = compile_gates(arms, globs_not, ext=ext)
    verdicts, completed = await judge_rows(pool, gates, rows, deadline=deadline)
    kept = [row for row, verdict in zip(rows, verdicts) if gates.admits(verdict, ext_of(row))]
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, Protocol

from vfs.native import glob_program, glob_set
from vfs.paths import Path, normalize_ext_channel, normalize_extension

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

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

# The row facts `GlobGates` reads beside the path: storage rides these
# columns on every candidate fetch so the gate never builds a Path.
ROW_GATE_FIELDS: Final = frozenset({"name", "ext"})

# One program atom: an op and its code-point ranges (see `vfs.native.glob_program`).
GlobAtom = tuple[str, list[tuple[str, str]]]

# One row a set judges: its path and its leaf name.
GlobRow = tuple[str, str]


class GlobProgram(Protocol):
    """The engine's compiled matcher for one glob pattern."""

    def is_match(self, subject: str) -> bool:
        """Whether the whole *subject* matches, from its first character."""
        ...


class GlobSet(Protocol):
    """The engine's matcher for one call's programs in groups (see `vfs.native.glob_set`)."""

    def judge(self, rows: Sequence[GlobRow], *, budget: float | None) -> tuple[list[int | None], bool]:
        """Each row's verdict word, ``None`` where *budget* stopped it, and whether every row was judged."""
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
    """One canonical pattern and its subject rule; build via :func:`compile_filter`.

    ``pattern`` is the anchored form — the one the SQL prefilter must
    translate, so prefilter and authority read the same text; ``by_path``
    says whether it matches the row's path or its leaf name. Matching
    is :class:`GlobGates`'s, over every row of a call at once.
    """

    pattern: str
    by_path: bool


@dataclass(frozen=True)
class ScopeChannel:
    """A call's scope as two channels: the roots, and the arms judged beneath them.

    A row is admitted by the scope when a root covers it (its path lies
    strictly beneath the root) and either its **remainder** (its path
    with the root's text cut from the front, so it begins with ``/``)
    matches a path arm, anchored with a leading ``/``, or its leaf name
    matches a name arm. It is excluded when a covering root's remainder
    or the name matches an ``arms_not`` arm. Every covering root is read,
    so nested and overlapping roots answer as their compositions do: the
    channel is exactly :func:`composed_pattern` over every root and arm,
    without composing. The roots are paths, never pattern text.
    """

    roots: tuple[Path, ...]
    arms: tuple[str, ...]
    arms_not: tuple[str, ...] = ()


class ScopePair(NamedTuple):
    """One row judged under one covering root: its remainder, its name, and whether the root is marked."""

    remainder: str
    name: str
    marked: bool


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
    ``x/``). Loud refusal beats a false friend. A pattern that expands
    past the arm cap has no component defect here: its walk stops on
    partial arms, which cannot name the defects of whole ones, and
    :func:`expand_pattern` refuses it by the cap.
    """
    return _admit(pattern).defect


def expand_pattern(pattern: str) -> tuple[str, ...]:
    """Gate, brace-expand, and cap one pattern — its plain arms, or :class:`PatternError`.

    The one admission call every surface shares: the defect gate
    (:func:`glob_defect`) runs first, then ``{a,b}`` alternates (each
    alternative is arbitrary brace-free pattern text, ``/`` included),
    groups cross-product left to right, and duplicates collapse to
    first appearance. A brace-free pattern returns itself, so the call
    is idempotent over its own output — a surface handed pre-expanded
    arms loses nothing by expanding again. The walk stops once its
    distinct partial arms pass :data:`MAX_PATTERN_ARMS` and refuses, so
    an over-cap expansion is detected without being materialized, and
    the work is linear in the pattern's text. The refusal names the
    pattern and the defect, or the cap; the channel label is the caller's.
    """
    admitted = _admit(pattern)
    if admitted.defect is not None:
        raise PatternError(f"{pattern!r}: {admitted.defect}")
    if admitted.arms is None:
        cap = f"expands past the arm cap ({MAX_PATTERN_ARMS}) — narrow the alternation or split the call"
        raise PatternError(f"{pattern!r}: {cap}")
    return admitted.arms


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


def compile_filter(pattern: str) -> GlobFilter:
    """The shared filter: the canonical pattern and its subject rule; no program is built."""
    canonical = _canonical(pattern)
    return GlobFilter(pattern=canonical, by_path="/" in canonical)


# ---------------------------------------------------------------------------
# The call's gates — the filter law over one native set's verdicts
# ---------------------------------------------------------------------------

# A verdict's bits: an unmarked admission, a marked one, an exclusion.
_UNMARKED: Final = 1 << 0
_MARKED: Final = 1 << 1
_EXCLUDED: Final = 1 << 2

# A scope pair's bits in the scope set: an arm matched, an exclusion arm matched.
_ARM: Final = 1 << 0
_ARM_NOT: Final = 1 << 1

# Rows the scope's pair walk takes between two reads of its deadline.
PAIR_ROWS_PER_CHECK: Final = 64


class _ScopeGates(NamedTuple):
    """The scope part of one call's gates: its roots, its marked roots, its arms and exclusion arms."""

    roots: frozenset[str]
    marked: frozenset[str]
    arms: tuple[GlobFilter, ...]
    arms_not: tuple[GlobFilter, ...]


class GlobGates:
    """One call's glob channels and ext facts: one native set judges, the law reads its verdicts.

    Build via :func:`compile_gates`. ``admissions`` and ``exclusions``
    are the call's distinct canonical filters (the SQL prefilters read
    them), ``wanted`` and ``unwanted`` its normalized ext sets. The set
    puts the unmarked admissions in group 0, the marked ones in group 1
    and the exclusions in group 2, each distinct pattern built once.
    It is built lazily, at most once, by the first hop that asks; the
    hops of one call may run concurrently, so the build holds a lock.

    A call with a :class:`ScopeChannel` holds a second set beside it,
    built the same way under the same lock: the scope's arms and
    exclusion arms, each compiled once whatever the number of roots.
    It judges one pair per covering root (:meth:`pairs`), and a row's
    verdict is its entry-wide word joined with its pairs' words.
    """

    def __init__(
        self,
        admissions: tuple[GlobFilter, ...],
        exclusions: tuple[GlobFilter, ...],
        marked: frozenset[str],
        wanted: frozenset[str],
        unwanted: frozenset[str],
        scope: _ScopeGates | None = None,
    ) -> None:
        self.admissions = admissions
        self.exclusions = exclusions
        self.wanted = wanted
        self.unwanted = unwanted
        self.scope_roots = frozenset() if scope is None else scope.roots
        self._marked = marked
        self._scope = scope
        self._lock = threading.Lock()
        self._built = False
        self._set: GlobSet | None = None
        self._scope_built = False
        self._scope_set: GlobSet | None = None

    @property
    def has_patterns(self) -> bool:
        """Whether any row needs the engine: the ext facts alone need none."""
        return self.has_entry_patterns or (self._scope is not None and bool(self._scope.arms or self._scope.arms_not))

    @property
    def has_entry_patterns(self) -> bool:
        """Whether the entry-wide channels hold a pattern, so the entry-wide set judges."""
        return bool(self.admissions or self.exclusions)

    @property
    def scoped(self) -> bool:
        """Whether the call carries a scope channel: an admission then needs a matching arm."""
        return self._scope is not None

    def native(self, deadline: float | None) -> GlobSet | None:
        """The call's native set, built once; ``None`` once a build reached *deadline*.

        One atom walk per distinct pattern, the clock checked before
        each, then one native construction under the budget left. A
        build that reaches the deadline stops and is never retried, so
        every later hop on these gates answers its rows unjudged. The
        walk is Python and holds the GIL in turns on its worker; the
        construction releases it.
        """
        with self._lock:
            if self._built:
                return self._set
            self._built = True
            patterns = list(dict.fromkeys(gate.pattern for gate in (*self.admissions, *self.exclusions)))
            programs: list[tuple[list[GlobAtom], bool]] = []
            for pattern in patterns:
                if deadline is not None and monotonic() > deadline:
                    return None
                programs.append((_program(pattern, recursive=True), "/" in pattern))
            index = {pattern: position for position, pattern in enumerate(patterns)}
            groups = [
                [index[gate.pattern] for gate in self.admissions if gate.pattern not in self._marked],
                [index[gate.pattern] for gate in self.admissions if gate.pattern in self._marked],
                [index[gate.pattern] for gate in self.exclusions],
            ]
            budget = None if deadline is None else max(0.0, deadline - monotonic())
            self._set = glob_set(programs, groups, budget=budget)
            return self._set

    def scope_native(self, deadline: float | None) -> GlobSet | None:
        """The scope's native set, built once: the arms in group 0, the exclusion arms in group 1.

        ``None`` once a build reached *deadline*, never retried, and for
        gates without a scope. A path arm matches a pair's remainder, a
        name arm its name; each distinct arm is one program.
        """
        scope = self._scope
        if scope is None:
            return None
        with self._lock:
            if self._scope_built:
                return self._scope_set
            self._scope_built = True
            patterns = list(dict.fromkeys(gate.pattern for gate in (*scope.arms, *scope.arms_not)))
            programs: list[tuple[list[GlobAtom], bool]] = []
            for pattern in patterns:
                if deadline is not None and monotonic() > deadline:
                    return None
                programs.append((_program(pattern, recursive=True), "/" in pattern))
            index = {pattern: position for position, pattern in enumerate(patterns)}
            groups = [[index[gate.pattern] for gate in scope.arms], [index[gate.pattern] for gate in scope.arms_not]]
            budget = None if deadline is None else max(0.0, deadline - monotonic())
            self._scope_set = glob_set(programs, groups, budget=budget)
            return self._scope_set

    def pairs(self, path: str, name: str) -> Iterator[ScopePair]:
        """One pair per scope root strictly above *path*, deepest root first.

        The walk visits the path's ancestors, at most its segments, and
        looks each up among the hashed roots. A pair is marked when its
        root is one the caller's predicate marks.
        """
        roots = self.scope_roots
        cut = path.rfind("/")
        while cut > 0:
            root = path[:cut]
            if root in roots:
                yield ScopePair(path[cut:], name, self._scope is not None and root in self._scope.marked)
            cut = path.rfind("/", 0, cut)

    def judge_scope(
        self, rows: Sequence[GlobRow], verdicts: Sequence[int | None], *, deadline: float | None
    ) -> tuple[list[int | None], bool]:
        """*verdicts* (the entry-wide words) joined with each row's pairs' words, and whether every pair was judged.

        The pairs are built here, the deadline read before every 64th
        row; a row the walk did not reach, or a pair the set did not
        judge, is unjudged. A pair's arm match is a marked admission
        under a marked root and an unmarked one otherwise; its exclusion
        arm match is an exclusion. Gates without a scope answer
        *verdicts* unchanged.
        """
        joined = list(verdicts)
        if self._scope is None:
            return joined, True
        native = self.scope_native(deadline)
        if native is None:
            return [None] * len(rows), False
        subjects: list[GlobRow] = []
        owners: list[tuple[int, bool]] = []
        reached = len(rows)
        for position, (path, name) in enumerate(rows):
            if position % PAIR_ROWS_PER_CHECK == 0 and deadline is not None and monotonic() > deadline:
                reached = position
                break
            for pair in self.pairs(path, name):
                subjects.append((pair.remainder, pair.name))
                owners.append((position, pair.marked))
        judged: list[int | None] = []
        completed = True
        if subjects:
            budget = None if deadline is None else max(0.0, deadline - monotonic())
            judged, completed = native.judge(subjects, budget=budget)
        for (position, marked), word in zip(owners, judged, strict=True):
            current = joined[position]
            if current is not None:
                joined[position] = None if word is None else current | _pair_bits(word, marked=marked)
        joined[reached:] = [None] * (len(rows) - reached)
        return joined, completed and reached == len(rows)

    def admits(self, verdict: int | None, ext: str | None, *, marked_only: bool = False) -> bool:
        """Whether a row with this *verdict* and derived extension passes the law.

        An unjudged row (``None``) never passes: it may match no
        admission, or an exclusion. Under *marked_only* (storage's row
        beneath the meta root) only a marked admission admits; otherwise
        any admission does, when the gates hold one or a scope. Any
        exclusion rejects; then the wanted and unwanted extensions apply.
        """
        if verdict is None:
            return False
        if marked_only:
            if not verdict & _MARKED:
                return False
        elif (self.admissions or self._scope is not None) and not verdict & (_UNMARKED | _MARKED):
            return False
        if verdict & _EXCLUDED:
            return False
        extension = ext or ""
        if self.wanted and extension not in self.wanted:
            return False
        return not (self.unwanted and extension in self.unwanted)


def compile_gates(
    admissions: Sequence[str],
    exclusions: Sequence[str] = (),
    *,
    ext: tuple[str, ...] = (),
    ext_not: tuple[str, ...] = (),
    marked: Callable[[str], bool] | None = None,
    scope: ScopeChannel | None = None,
) -> GlobGates:
    """One call's gates: the channels canonicalized and deduped, the ext sets normalized.

    *marked* is the caller's predicate over a canonical admission (the
    pattern layer knows nothing of storage's meta subtree); with none,
    no admission is marked. A *scope* is compiled beside the entry-wide
    channels: its arms as given, a path arm anchored, and its roots
    hashed, a root marked when the predicate marks its text. No program
    is built here.
    """
    admitted = _filters(admissions)
    excluded = _filters(exclusions)
    flagged = frozenset(gate.pattern for gate in admitted if marked is not None and marked(gate.pattern))
    part: _ScopeGates | None = None
    if scope is not None:
        roots = frozenset(str(root) for root in scope.roots)
        marked_roots = frozenset(root for root in roots if marked is not None and marked(root))
        part = _ScopeGates(roots, marked_roots, _filters(scope.arms), _filters(scope.arms_not))
    wanted, unwanted = normalize_ext_channel(ext), normalize_ext_channel(ext_not)
    return GlobGates(admitted, excluded, flagged, wanted, unwanted, part)


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


def _filters(patterns: Sequence[str]) -> tuple[GlobFilter, ...]:
    """A channel's distinct canonical filters, in first-appearance order."""
    return tuple(compile_filter(pattern) for pattern in dict.fromkeys(_canonical(p) for p in patterns))


def _pair_bits(word: int, *, marked: bool) -> int:
    """A scope pair's set word as the call's verdict bits: an arm admits, marked under a marked root."""
    bits = 0
    if word & _ARM:
        bits |= _MARKED if marked else _UNMARKED
    if word & _ARM_NOT:
        bits |= _EXCLUDED
    return bits


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


class _Admitted(NamedTuple):
    """One pattern's admission walk: its arms (``None`` past the cap) and its defect."""

    arms: tuple[str, ...] | None
    defect: str | None


def _admit(pattern: str) -> _Admitted:
    """The one admission walk: the brace structure, one expansion, the arms' component defects."""
    if "{" not in pattern and "}" not in pattern:
        return _Admitted((pattern,), _component_defect(pattern))
    parts, brace_defect = _parse_braces(pattern)
    if brace_defect is not None:
        return _Admitted(None, brace_defect)
    if not any(isinstance(part, tuple) for part in parts):
        return _Admitted((pattern,), _component_defect(pattern))
    arms = _cross_product(parts, MAX_PATTERN_ARMS)
    if arms is None:
        return _Admitted(None, None)
    for arm in arms:
        if (defect := _component_defect(arm)) is not None:
            return _Admitted(None, f"{defect} (expansion arm {arm!r})")
    return _Admitted(tuple(arms), None)


def _cross_product(parts: Sequence[str | tuple[str, ...]], limit: int) -> list[str] | None:
    """Deduped left-to-right cross-product in first-appearance order, ``None`` past *limit*.

    Expands group by group, keeping only distinct partial arms; a part
    with one distinct alternative joins a pending literal instead. A
    fixed suffix keeps distinct arms distinct, so the set never shrinks
    and a partial set past *limit* already refuses; a group of two
    distinct alternatives grows it, so at most *limit* groups expand.
    """
    arms = [""]
    pending = ""
    for part in parts:
        pool = (part,) if isinstance(part, str) else tuple(dict.fromkeys(part))
        if len(pool) == 1:
            pending += pool[0]
            continue
        expanded = _expand_group(arms, pending, pool, limit)
        if expanded is None:
            return None
        arms, pending = expanded, ""
    return [arm + pending for arm in arms]


def _expand_group(arms: list[str], pending: str, pool: tuple[str, ...], limit: int) -> list[str] | None:
    """Each partial arm, the pending literal, then each alternative: distinct, ``None`` past *limit*."""
    joined: dict[str, None] = {}
    for arm in arms:
        head = arm + pending
        for alternative in pool:
            joined[head + alternative] = None
            if len(joined) > limit:
                return None
    return list(joined)


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
