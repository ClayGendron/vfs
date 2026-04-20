"""Composable result types for VFS.

Every VFS operation returns ``VFSResult``. Results carry ``entries`` — a flat
row shape uniform across grep, glob, bm25/vector/semantic search, pagerank,
read/stat/ls, and write/delete. Chaining (set algebra, ``.sort``, ``.top``,
``.filter``) operates in-memory:

    result = await vfs.vector_search("auth", k=5)
    top_3 = result.top(3)

The envelope carries ``function`` (``grep`` | ``glob`` | ``vector_search`` |
``pagerank`` | ``read`` | ... | ``hybrid``) so renderers and downstream
consumers know how the rows were produced.

Serialization:

- ``result.to_json(exclude_none=True)`` — Pydantic JSON for APIs / MCP.
- ``result.to_str(projection=None)`` — text render. ``projection`` selects the
  Entry columns to include; arrangement is function-specific.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs this at runtime for field resolution
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar

from pydantic import BaseModel, ConfigDict

from vfs.paths import split_path, unscope_path

_T = TypeVar("_T")

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# ---------------------------------------------------------------------------
# Operation models — batch inputs for public methods
# ---------------------------------------------------------------------------


class EditOperation(BaseModel):
    """A single find-and-replace edit.

    Multiple ``EditOperation`` objects are applied sequentially — each sees
    the content left by the previous one.
    """

    model_config = ConfigDict(frozen=True)

    old: str
    new: str
    replace_all: bool = False


class TwoPathOperation(BaseModel):
    """A source/destination pair for move or copy."""

    model_config = ConfigDict(frozen=True)

    src: str
    dest: str


# ---------------------------------------------------------------------------
# LineMatch — one matched line plus its context window
# ---------------------------------------------------------------------------


class LineMatch(NamedTuple):
    """One matched line plus its context window. Pure positional data.

    ``start`` / ``end`` / ``match`` are 1-indexed file line numbers. ``match``
    is the hit line; ``start`` and ``end`` bracket the before/after context
    window (equal to ``match`` when no ``-B`` / ``-A`` context is requested).
    """

    start: int
    end: int
    match: int


# ---------------------------------------------------------------------------
# Entry — one row in a result set
# ---------------------------------------------------------------------------


class Entry(BaseModel):
    """Flat row shape — uniform across every VFS function.

    Fields are populated by the function that produced the row. A null field
    means "not populated for this function" (or "not known for this row"),
    never "this row has no such attribute." Projection controls which fields
    the underlying SELECT fetches and which fields the renderer displays.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    kind: str | None = None
    lines: list[LineMatch] | None = None
    content: str | None = None
    size_bytes: int | None = None
    score: float | None = None
    in_degree: int | None = None
    out_degree: int | None = None
    updated_at: datetime | None = None

    @property
    def name(self) -> str:
        """Last segment of the path."""
        return split_path(self.path)[1]


ENTRY_FIELDS: frozenset[str] = frozenset(Entry.model_fields.keys())
"""Every field name on ``Entry`` — used to validate projection input."""

PROJECTION_SENTINELS: frozenset[str] = frozenset({"default", "all"})
"""Projection names that expand to a function-specific or result-derived set."""


# ---------------------------------------------------------------------------
# Function vocabulary
# ---------------------------------------------------------------------------


# Arrangement groups. The envelope's ``function`` key picks an arrangement;
# multiple functions can share an arrangement (e.g. all centrality methods).
_RANKED_SEARCH_FUNCTIONS: frozenset[str] = frozenset(
    {"vector_search", "semantic_search", "lexical_search", "bm25"},
)
_CENTRALITY_FUNCTIONS: frozenset[str] = frozenset(
    {
        "pagerank",
        "betweenness_centrality",
        "closeness_centrality",
        "degree_centrality",
        "in_degree_centrality",
        "out_degree_centrality",
        "hits",
    },
)
_ACTION_FUNCTIONS: frozenset[str] = frozenset(
    {"write", "delete", "edit", "move", "copy", "mkdir", "mkedge"},
)
_PATH_LIST_FUNCTIONS: frozenset[str] = frozenset(
    {"glob", "ls", "hybrid"}
    | {"predecessors", "successors", "ancestors", "descendants", "neighborhood"}
    | {"meeting_subgraph", "min_meeting_subgraph"},
)


# Per-function default projection. Users can override with ``--output`` on
# the CLI or the ``projection=`` kwarg on ``to_str``.
_DEFAULT_PROJECTION: dict[str, tuple[str, ...]] = {
    "grep": ("path", "lines", "content"),
    "glob": ("path",),
    "ls": ("path",),
    "tree": ("path",),
    "read": ("content",),
    "stat": ("path", "kind", "size_bytes", "updated_at"),
    "hybrid": ("path",),
}
for _fn in _RANKED_SEARCH_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path", "score")
for _fn in _CENTRALITY_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path", "score", "in_degree", "out_degree")
for _fn in _ACTION_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path",)
for _fn in ("predecessors", "successors", "ancestors", "descendants", "neighborhood"):
    _DEFAULT_PROJECTION[_fn] = ("path", "kind")
for _fn in ("meeting_subgraph", "min_meeting_subgraph"):
    _DEFAULT_PROJECTION[_fn] = ("path", "kind")


def default_projection(function: str) -> tuple[str, ...]:
    """Return the default projection tuple for *function*. Raises if unknown."""
    try:
        return _DEFAULT_PROJECTION[function]
    except KeyError as exc:
        msg = f"unknown function {function!r}"
        raise ValueError(msg) from exc


def validate_projection(projection: tuple[str, ...] | list[str] | None) -> tuple[str, ...] | None:
    """Return *projection* as a tuple after validating every name.

    ``None`` passes through. A bare string is rejected — ``projection=("path")``
    is a tuple-literal typo (needs a trailing comma) that would otherwise
    iterate character-by-character into an ``unknown field 'p'`` error.
    Every name must be a known ``Entry`` field or a sentinel
    (``default`` / ``all``); unknowns raise ``ValueError``.
    """
    if projection is None:
        return None
    if isinstance(projection, str):
        msg = (
            f"projection must be a tuple or list of field names, not a bare string "
            f"{projection!r}. Did you mean ({projection!r},)?"
        )
        raise TypeError(msg)
    result: list[str] = []
    for name in projection:
        if name not in ENTRY_FIELDS and name not in PROJECTION_SENTINELS:
            msg = f"unknown field {name!r}"
            raise ValueError(msg)
        result.append(name)
    return tuple(result)


def resolve_projection(
    projection: tuple[str, ...] | None,
    function: str,
    entries: list[Entry],
) -> tuple[str, ...]:
    """Expand ``default`` / ``all`` sentinels into concrete Entry field names.

    - ``default`` → ``default_projection(function)``
    - ``all`` → every field that is non-null on at least one entry
    Order is preserved; duplicates are dropped (first-win).
    """
    if projection is None:
        return default_projection(function)
    seen: set[str] = set()
    out: list[str] = []

    def _add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            out.append(name)

    for name in projection:
        if name == "default":
            for field in default_projection(function):
                _add(field)
        elif name == "all":
            populated = {f for e in entries for f in ENTRY_FIELDS if getattr(e, f) is not None}
            for field in Entry.model_fields:
                if field in populated:
                    _add(field)
        else:
            _add(name)
    return tuple(out)


# ---------------------------------------------------------------------------
# VFSResult — unified envelope
# ---------------------------------------------------------------------------


class VFSResult(BaseModel):
    """Unified result from every VFS operation.

    - **Envelope:** ``function`` identifies how the rows were produced; renderers
      and consumers dispatch on it.
    - **Rows:** ``entries`` is the flat row list (``Entry``).
    - **Errors:** ``success`` / ``errors`` carry status independent of the rows.

    Supports:

    - Data inspection: ``.paths``, ``.content``, ``.file``.
    - Set algebra: ``&`` (intersection), ``|`` (union), ``-`` (difference).
      Overlapping paths merge **left wins**. Cross-function ``|`` sets
      ``function="hybrid"``.
    - Enrichment: ``.sort()``, ``.top()``, ``.filter()``, ``.kinds()``.
    - Serialization: ``.to_json()``, ``.to_str(projection=...)``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    errors: list[str] = []
    function: str = ""
    entries: list[Entry] = []

    # -------------------------------------------------------------------
    # Data access
    # -------------------------------------------------------------------

    @property
    def error_message(self) -> str:
        """All errors joined as a single string."""
        return "; ".join(self.errors)

    @property
    def paths(self) -> tuple[str, ...]:
        """All entry paths as a tuple."""
        return tuple(e.path for e in self.entries)

    @property
    def file(self) -> Entry | None:
        """First entry, or ``None`` if empty."""
        return self.entries[0] if self.entries else None

    @property
    def content(self) -> str | None:
        """Content of the first entry, or ``None``."""
        return self.entries[0].content if self.entries else None

    # -------------------------------------------------------------------
    # Iteration / truthiness
    # -------------------------------------------------------------------

    def iter_entries(self) -> Iterator[Entry]:
        """Iterate over entries without overriding BaseModel iteration."""
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __bool__(self) -> bool:
        return self.success and len(self.entries) > 0

    def __contains__(self, path: str) -> bool:
        return path in self.paths

    # -------------------------------------------------------------------
    # Set algebra — left-wins merge on overlap
    # -------------------------------------------------------------------

    def _as_dict(self) -> dict[str, Entry]:
        return {e.path: e for e in self.entries}

    @staticmethod
    def _first_set(a: _T | None, b: _T | None, default: _T | None = None) -> _T | None:
        """Return *a* if not None, else *b*, else *default*."""
        return a if a is not None else (b if b is not None else default)

    @staticmethod
    def _merge_entry(a: Entry, b: Entry) -> Entry:
        """Left entry wins; fall back to right only where left is None."""
        fs = VFSResult._first_set
        return Entry(
            path=a.path,
            kind=fs(a.kind, b.kind),
            lines=fs(a.lines, b.lines),
            content=fs(a.content, b.content),
            size_bytes=fs(a.size_bytes, b.size_bytes),
            score=fs(a.score, b.score),
            in_degree=fs(a.in_degree, b.in_degree),
            out_degree=fs(a.out_degree, b.out_degree),
            updated_at=fs(a.updated_at, b.updated_at),
        )

    def _merged_function(self, other: VFSResult) -> str:
        """Return ``self.function`` when both match, else ``"hybrid"``."""
        if not self.function:
            return other.function
        if not other.function:
            return self.function
        return self.function if self.function == other.function else "hybrid"

    def __and__(self, other: VFSResult) -> VFSResult:
        """Intersection — entries present on both sides, left wins on overlap."""
        left = self._as_dict()
        right = other._as_dict()
        merged = [self._merge_entry(left[p], right[p]) for p in left if p in right]
        return VFSResult(
            function=self._merged_function(other),
            entries=merged,
            success=self.success and other.success,
            errors=self.errors + other.errors,
        )

    def __or__(self, other: VFSResult) -> VFSResult:
        """Union — all entries; left wins on overlap."""
        left = self._as_dict()
        right = other._as_dict()
        merged: dict[str, Entry] = {}
        for p, e in left.items():
            merged[p] = self._merge_entry(e, right[p]) if p in right else e
        for p, e in right.items():
            if p not in merged:
                merged[p] = e
        return VFSResult(
            function=self._merged_function(other),
            entries=list(merged.values()),
            success=self.success and other.success,
            errors=self.errors + other.errors,
        )

    def __sub__(self, other: VFSResult) -> VFSResult:
        """Difference — entries in left whose path is not in right."""
        right_paths = set(other.paths)
        remaining = [e for e in self.entries if e.path not in right_paths]
        return VFSResult(
            function=self.function,
            entries=remaining,
            success=self.success,
            errors=self.errors,
        )

    # -------------------------------------------------------------------
    # Enrichment chains (local, no backend call)
    # -------------------------------------------------------------------

    def _with_entries(self, entries: list[Entry]) -> VFSResult:
        """Return a new result with the given *entries*, preserving envelope."""
        return VFSResult(
            function=self.function,
            entries=entries,
            success=self.success,
            errors=self.errors,
        )

    def add_prefix(self, prefix: str) -> VFSResult:
        """Prepend *prefix* to every entry path, in place."""
        if not prefix:
            return self
        self.entries = [
            e.model_copy(update={"path": prefix + e.path if e.path != "/" else prefix}) for e in self.entries
        ]
        return self

    def strip_user_scope(self, user_id: str) -> VFSResult:
        """Strip the ``/{user_id}`` prefix (and any embedded target prefix) from paths."""
        return self._with_entries([e.model_copy(update={"path": unscope_path(e.path, user_id)}) for e in self.entries])

    def sort(
        self,
        *,
        key: Callable[[Entry], Any] | None = None,
        reverse: bool = True,
    ) -> VFSResult:
        """Re-order entries. Default key is ``entry.score`` (None treated as ``-inf``)."""
        if key is None:

            def key(e: Entry) -> float:
                return e.score if e.score is not None else float("-inf")

        return self._with_entries(sorted(self.entries, key=key, reverse=reverse))

    def top(self, k: int) -> VFSResult:
        """Top *k* entries by score. *k* must be >= 1."""
        if k < 1:
            msg = f"k must be >= 1, got {k}"
            raise ValueError(msg)
        sorted_result = self.sort()
        return sorted_result._with_entries(sorted_result.entries[:k])

    def filter(self, fn: Callable[[Entry], bool]) -> VFSResult:
        """Keep entries where *fn(entry)* is truthy."""
        return self._with_entries([e for e in self.entries if fn(e)])

    def kinds(self, *kinds: str) -> VFSResult:
        """Filter entries by kind."""
        kind_set = set(kinds)
        return self.filter(lambda e: e.kind in kind_set)

    # -------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------

    def to_json(self, *, exclude_none: bool = True) -> str:
        """Pydantic JSON — for APIs, caches, MCP tools."""
        return self.model_dump_json(exclude_none=exclude_none)

    def to_str(self, *, projection: tuple[str, ...] | list[str] | None = None) -> str:
        """Render to text. *projection* selects Entry columns to show.

        - ``None`` → function's default projection.
        - Tuple/list of field names, possibly with ``default`` / ``all`` sentinels.
        - ``success=False`` short-circuits to ``"ERROR: ..."`` regardless of projection.
        - If the result has errors but ``success=True``, the error block is
          appended after the body.
        """
        if not self.success and not self.entries:
            return _render_errors(self.errors)

        proj = validate_projection(projection)
        resolved = resolve_projection(proj, self.function, self.entries)
        body = _render_body(self, resolved)
        note = _render_unpopulated_projection_note(proj, self.entries)

        blocks = [block for block in (body, note, _render_errors(self.errors)) if block]
        return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Rendering — per-function arrangement helpers
# ---------------------------------------------------------------------------


def _render_errors(errors: list[str]) -> str:
    if not errors:
        return ""
    prefix = "ERROR" if len(errors) == 1 else "ERRORS"
    return f"{prefix}: " + "; ".join(errors)


def _render_unpopulated_projection_note(
    projection: tuple[str, ...] | None,
    entries: list[Entry],
) -> str:
    """Return a note for explicitly projected fields that are null-for-all."""
    if projection is None or not entries:
        return ""

    missing: list[str] = []
    seen: set[str] = set()
    for name in projection:
        if name in ENTRY_FIELDS and name not in seen and all(getattr(entry, name) is None for entry in entries):
            seen.add(name)
            missing.append(name)
    if not missing:
        return ""

    fields = ", ".join(missing)
    return f"NOTE: {fields} not populated for any entries."


def _render_body(result: VFSResult, projection: tuple[str, ...]) -> str:
    """Dispatch to the function-specific arrangement helper."""
    fn = result.function
    if fn == "grep":
        return _render_grep(result, projection)
    if fn == "tree":
        return _render_tree(result)
    if fn == "read":
        return _render_read(result, projection)
    if fn == "stat":
        return _render_block(result, projection)
    if fn in _ACTION_FUNCTIONS:
        return _render_action(result)
    return _render_path_list(result, projection)


def _format_field(name: str, value: Any) -> str:
    """Canonical text rendering for a single Entry field value."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value)


_RIGHT_ALIGN_FIELDS: frozenset[str] = frozenset({"size_bytes", "score", "in_degree", "out_degree"})
"""Projection fields that render right-aligned in Markdown tables — numeric values."""


def _render_path_list(result: VFSResult, projection: tuple[str, ...]) -> str:
    """One path per line for a path-only projection; a Markdown table otherwise.

    Markdown is the one textual format agents and chat UIs both parse
    reliably, and tables sidestep the ``:`` ambiguity that bites a
    colon-joined format when cells contain colons (timestamps, tuples).
    Column widths expand to fit the longest cell so pipes line up.
    """
    if projection == ("path",):
        return "\n".join(sorted(e.path for e in result.entries))
    if not result.entries:
        return ""
    rows = [
        [_format_field(f, getattr(e, f, None)) for f in projection]
        for e in sorted(result.entries, key=lambda x: x.path)
    ]
    return _markdown_table(list(projection), rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render *headers* + *rows* as an aligned GitHub-flavored Markdown table.

    Column widths are the max of the header and every cell in that
    column, floored at 3 (GFM minimum divider length).  Numeric fields
    listed in :data:`_RIGHT_ALIGN_FIELDS` get a ``---:`` divider and
    right-padded cells so the digits line up.  ``|`` and embedded
    newlines in cell values are escaped/stripped so each row stays on
    one line.
    """
    cells = [[_escape_table_cell(c) for c in row] for row in rows]
    widths = [max(3, len(h)) for h in headers]
    for row in cells:
        for i, cell in enumerate(row):
            if len(cell) > widths[i]:
                widths[i] = len(cell)

    aligns = ["right" if h in _RIGHT_ALIGN_FIELDS else "left" for h in headers]

    def _cell(value: str, width: int, align: str) -> str:
        return value.rjust(width) if align == "right" else value.ljust(width)

    def _row(values: list[str]) -> str:
        padded = [_cell(v, widths[i], aligns[i]) for i, v in enumerate(values)]
        return "| " + " | ".join(padded) + " |"

    divider_cells = [
        "-" * (widths[i] - 1) + ":" if aligns[i] == "right" else "-" * widths[i] for i in range(len(headers))
    ]
    out = [_row(headers), "| " + " | ".join(divider_cells) + " |"]
    out.extend(_row(row) for row in cells)
    return "\n".join(out)


def _escape_table_cell(value: str) -> str:
    """Keep a cell one-line and pipe-safe."""
    return value.replace("|", r"\|").replace("\n", " ")


def _render_block(result: VFSResult, projection: tuple[str, ...]) -> str:
    """First projection column is the block header; remaining columns are indented."""
    if not projection:
        return ""
    head, *rest = projection
    blocks = []
    for e in sorted(result.entries, key=lambda x: x.path):
        lines = [_format_field(head, getattr(e, head, None))]
        for field in rest:
            value = getattr(e, field, None)
            if value is not None:
                lines.append(f"  {field}: {_format_field(field, value)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_read(result: VFSResult, projection: tuple[str, ...]) -> str:
    """Dump content verbatim. Multi-entry gets ``==> path <==`` headers."""
    if not result.entries:
        return ""
    if projection != ("content",):
        # If the caller asks for more than content, fall back to block format.
        return _render_block(result, projection)
    if len(result.entries) == 1:
        return result.entries[0].content or ""
    blocks = [f"==> {e.path} <==\n{e.content or ''}" for e in sorted(result.entries, key=lambda x: x.path)]
    return "\n\n".join(blocks)


_GREP_LINE_LEVEL_FIELDS: frozenset[str] = frozenset({"path", "lines", "content"})
"""Fields that make sense on a per-source-line basis in grep output."""


def _render_grep(result: VFSResult, projection: tuple[str, ...]) -> str:
    """Ripgrep-style line output — or a Markdown table for entry-level fields.

    When the projection contains only ``path`` / ``lines`` / ``content``
    (grep's native vocabulary), each source line in a match's context
    window becomes its own prefixed row:

    - match lines use ``:`` separators (``path:N:text``).
    - context lines use ``-`` separators (``path-N-text``).

    As soon as the projection asks for entry-level fields
    (``size_bytes``, ``updated_at``, degrees, …) we switch to the
    standard Markdown-table render — those fields are per-file, not
    per-line, and jamming them onto an rg-style line produces ambiguous
    mixed-separator output.  The caller traded line-level detail for a
    tabular entry-level view when they projected metadata.

    ``--files-with-matches`` / ``--count`` output modes produce entries
    with no ``LineMatch`` segments; those render as one path per line.
    """
    if not set(projection).issubset(_GREP_LINE_LEVEL_FIELDS):
        return _render_path_list(result, projection)

    include_path = "path" in projection
    include_lines = "lines" in projection
    include_content = "content" in projection

    lines_out: list[str] = []
    for e in result.entries:
        segments = e.lines or []
        if not segments:
            if include_path:
                lines_out.append(e.path)
            continue

        if not include_content:
            for seg in segments:
                pieces = []
                if include_path:
                    pieces.append(e.path)
                if include_lines:
                    pieces.append(str(seg.match))
                lines_out.append(":".join(pieces))
            continue

        # Multiple matches can share one merged context span. Emit each span
        # once, marking every hit line inside it as a match.
        grouped_segments: dict[tuple[int, int], set[int]] = {}
        for seg in segments:
            grouped_segments.setdefault((seg.start, seg.end), set()).add(seg.match)

        text_lines = (e.content or "").splitlines()
        for (start, end), match_lines in grouped_segments.items():
            for lineno in range(start, end + 1):
                if not (0 < lineno <= len(text_lines)):
                    continue
                is_match = lineno in match_lines
                sep = ":" if is_match else "-"
                pieces = []
                if include_path:
                    pieces.append(e.path)
                if include_lines:
                    pieces.append(str(lineno))
                pieces.append(text_lines[lineno - 1])
                lines_out.append(sep.join(pieces))
    return "\n".join(lines_out)


def _render_tree(result: VFSResult) -> str:
    """ASCII tree of entry paths."""
    paths = sorted(e.path.strip("/").split("/") for e in result.entries if e.path != "/")
    tree: dict[str, dict] = {}
    for parts in paths:
        cursor = tree
        for part in parts:
            cursor = cursor.setdefault(part, {})

    lines: list[str] = []

    def walk(node: dict[str, dict], prefix: str = "") -> None:
        names = sorted(node)
        for index, name in enumerate(names):
            connector = "└── " if index == len(names) - 1 else "├── "
            lines.append(f"{prefix}{connector}{name}")
            extension = "    " if index == len(names) - 1 else "│   "
            walk(node[name], prefix + extension)

    walk(tree)
    return "\n".join(lines)


def _render_action(result: VFSResult) -> str:
    """Action one-liner — ``{Verb} {path}`` or ``{Verb} {N} paths``."""
    count = len(result.entries)
    verb = _verb_for(result.function)
    if count == 0:
        return "No changes"
    if count == 1:
        return f"{verb} {result.entries[0].path}"
    return f"{verb} {count} paths"


def _verb_for(operation: str) -> str:
    match operation:
        case "write":
            return "Wrote"
        case "edit":
            return "Edited"
        case "delete":
            return "Deleted"
        case "move":
            return "Moved"
        case "copy":
            return "Copied"
        case "mkdir":
            return "Created"
        case "mkedge":
            return "Connected"
        case _:
            return operation.replace("_", " ").capitalize() if operation else "Completed"
