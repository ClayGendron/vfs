"""Text rendering for Result — the human/agent-facing string surface.

One entry point, :func:`render_result`, dispatches on the result's
``function`` into a per-arrangement renderer: ripgrep-style lines for grep,
an ASCII tree, verbatim content for read, Markdown tables for everything
tabular, one-liners for actions, and a dedicated write formatter. Rendering
is pure — it reads what is on the envelope and never performs I/O.

Text is rendered once, at the final human/agent boundary (CLI output or a
top-level MCP tool). Inter-mount hops travel as structured payloads only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vfs.models2 import Match
from vfs.projection import ACTION_FUNCTIONS, OBSERVATION_FIELDS, resolve_projection, validate_projection

if TYPE_CHECKING:
    from vfs.models2 import Observation
    from vfs.results2 import Result, ResultError


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render_result(result: Result, *, projection: tuple[str, ...] | list[str] | None = None) -> str:
    """Render *result* to text. *projection* selects Observation columns to show.

    - ``None`` → function's default projection.
    - Tuple/list of field names, possibly with ``default`` / ``all`` sentinels.
    - ``write`` results use a dedicated ``write errors:`` / ``write success:``
      formatter regardless of projection.
    - For other functions, ``success=False`` with no observations
      short-circuits to ``"ERROR: ..."``.
    - If the result has errors but ``success=True``, the error block is
      appended after the body.

    A bad projection raises on every path — including write and error
    results that ignore it for the body — so a typo fails the same way
    regardless of what result it lands on.
    """
    proj = validate_projection(projection)

    if result.function == "write":
        return _render_write(result)

    if not result.success and not result.observations:
        return _render_errors(result.errors)

    resolved = resolve_projection(proj, result.function, result.observations)
    body = _render_body(result, resolved)
    note = _render_unpopulated_projection_note(result, proj)

    blocks = [block for block in (body, note, _render_errors(result.errors)) if block]
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_errors(errors: list[ResultError]) -> str:
    """Prose error block — messages only; the kind stays structured-side."""
    if not errors:
        return ""
    prefix = "ERROR" if len(errors) == 1 else "ERRORS"
    return f"{prefix}: " + "; ".join(e.message for e in errors)


# Functions whose body ignores per-field projection columns — a
# "not populated" note about columns is meaningless under them.
_PROJECTION_FREE_FUNCTIONS: frozenset[str] = frozenset({"tree"}) | ACTION_FUNCTIONS


def _render_unpopulated_projection_note(result: Result, projection: tuple[str, ...] | None) -> str:
    """Return a note for explicitly projected fields that render nothing.

    Only fields the caller named outright are considered (``default`` / ``all``
    expand elsewhere). A field counts as populated when the body renderer shows
    data for it on at least one row; for ``grep`` the per-line fields draw from
    the match regions, so a field carried by ``matches`` counts even when the
    Observation column is null. Functions whose body ignores projection columns
    (``tree``, the action one-liners) never emit the note.
    """
    observations = result.observations
    if projection is None or not observations:
        return ""
    if result.function in _PROJECTION_FREE_FUNCTIONS:
        return ""

    missing: list[str] = []
    seen: set[str] = set()
    for name in projection:
        if name not in OBSERVATION_FIELDS or name in seen:
            continue
        seen.add(name)
        if _field_unpopulated(result.function, name, observations):
            missing.append(name)
    if not missing:
        return ""

    fields = ", ".join(missing)
    return f"NOTE: {fields} not populated for any observations."


def _field_unpopulated(function: str, field: str, observations: list[Observation]) -> bool:
    """Whether *field* has no rendered data on any row, accounting for its source.

    ``grep`` renders ``path`` / ``matches`` / ``content`` from the per-line
    match regions, so those fields read from ``matches`` (with the Observation
    column as a fallback for ``content``) rather than the column alone.
    """
    if function == "grep" and field in _GREP_LINE_LEVEL_FIELDS:
        if field == "path":
            return False
        if field == "matches":
            return all(not o.matches for o in observations)
        return all(o.content is None and not any(m.content for m in (o.matches or [])) for o in observations)
    return all(getattr(o, field) is None for o in observations)


def _render_body(result: Result, projection: tuple[str, ...]) -> str:
    """Dispatch to the function-specific arrangement helper.

    Unknown functions fall through to the path-list/table renderer — the
    forward-compatible fallback for a function name this client predates.
    """
    fn = result.function
    if fn == "grep":
        return _render_grep(result, projection)
    if fn == "tree":
        return _render_tree(result)
    if fn == "read":
        return _render_read(result, projection)
    if fn == "stat":
        return _render_block(result, projection)
    if fn in ACTION_FUNCTIONS:
        return _render_action(result)
    return _render_path_list(result, projection)


def _format_field(name: str, value: Any) -> str:
    """Canonical text rendering for a single Observation field value."""
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list):
        return ",".join(f"{v.start}-{v.end}" if isinstance(v, Match) else str(v) for v in value)
    return str(value)


_RIGHT_ALIGN_FIELDS: frozenset[str] = frozenset(
    {"size_bytes", "score", "in_degree", "out_degree", "version_number"},
)
"""Projection fields that render right-aligned in Markdown tables — numeric values."""


def _render_path_list(result: Result, projection: tuple[str, ...]) -> str:
    """One path per line for a path-only projection; a Markdown table otherwise.

    Markdown is the one textual format agents and chat UIs both parse
    reliably, and tables sidestep the ``:`` ambiguity that bites a
    colon-joined format when cells contain colons (timestamps, tuples).
    Column widths expand to fit the longest cell so pipes line up.
    """
    if projection == ("path",):
        return "\n".join(sorted(o.path for o in result.observations))
    if not result.observations:
        return ""
    rows = [
        [_format_field(f, getattr(o, f, None)) for f in projection]
        for o in sorted(result.observations, key=lambda x: x.path)
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
    return value.replace("|", r"\|").replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def _render_block(result: Result, projection: tuple[str, ...]) -> str:
    """First projection column is the block header; remaining columns are indented.

    A multi-line field value keeps its continuation lines indented under the
    field label so the block structure survives embedded newlines.
    """
    if not projection:
        return ""
    head, *rest = projection
    blocks = []
    for o in sorted(result.observations, key=lambda x: x.path):
        lines = [_format_field(head, getattr(o, head, None))]
        for field in rest:
            value = getattr(o, field, None)
            if value is not None:
                lines.append(_format_block_field(field, _format_field(field, value)))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _format_block_field(field: str, rendered: str) -> str:
    """``  field: value`` with any continuation lines indented under the label."""
    first, *rest = rendered.split("\n")
    head = f"  {field}: {first}"
    if not rest:
        return head
    return "\n".join([head, *(f"    {line}" for line in rest)])


def _render_read(result: Result, projection: tuple[str, ...]) -> str:
    """Dump content verbatim. Multi-observation gets ``==> path <==`` headers."""
    if not result.observations:
        return ""
    if projection != ("content",):
        # If the caller asks for more than content, fall back to block format.
        return _render_block(result, projection)
    if len(result.observations) == 1:
        return result.observations[0].content or ""
    blocks = [f"==> {o.path} <==\n{o.content or ''}" for o in sorted(result.observations, key=lambda x: x.path)]
    return "\n\n".join(blocks)


_GREP_LINE_LEVEL_FIELDS: frozenset[str] = frozenset({"path", "matches", "content"})
"""Fields that make sense on a per-source-line basis in grep output."""


def _render_grep(result: Result, projection: tuple[str, ...]) -> str:
    """Ripgrep-style line output — or a Markdown table for row-level fields.

    When the projection contains only ``path`` / ``matches`` / ``content``
    (grep's native vocabulary), each source line in a match's region becomes
    its own prefixed row:

    - match lines use ``:`` separators (``path:N:text``).
    - context lines use ``-`` separators (``path-N-text``).

    Region text comes from ``Match.content`` (each region carries its own
    text), falling back to slicing ``Observation.content`` when the region
    text was not fetched. A ``Match`` with ``match=None`` is a whole-region
    hit (an indexed-chunk match) — every line in it renders as a match.

    As soon as the projection asks for row-level fields (``size_bytes``,
    ``updated_at``, degrees, …) we switch to the standard Markdown-table
    render — those fields are per-file, not per-line, and jamming them onto
    an rg-style line produces ambiguous mixed-separator output.

    A path-only projection renders one line per file regardless of how many
    regions it matched — the files-with-matches view. ``--files-with-matches``
    / ``--count`` output modes produce observations with no ``Match`` regions
    and render the same way.
    """
    if not set(projection).issubset(_GREP_LINE_LEVEL_FIELDS):
        return _render_path_list(result, projection)

    include_path = "path" in projection
    include_numbers = "matches" in projection
    if not include_numbers and "content" not in projection:
        # Path-only projection — the files-with-matches view, one line per row.
        return "\n".join(sorted(o.path for o in result.observations))

    lines_out: list[str] = []
    for o in result.observations:
        regions = o.matches or []
        if not regions:
            if include_path:
                lines_out.append(o.path)
            continue

        # Multiple matches can share one merged region span. Emit each span
        # once; collect every hit line inside it. A None hit marks the whole
        # span as matched; the first non-empty region text wins.
        grouped: dict[tuple[int, int], tuple[set[int], bool, str | None]] = {}
        for region in regions:
            key = (region.start, region.end)
            hits, whole, text = grouped.get(key, (set(), False, None))
            if region.match is None:
                whole = True
            else:
                hits.add(region.match)
            if not text:
                text = region.content
            grouped[key] = (hits, whole, text)

        for (start, end), (hits, whole, region_text) in grouped.items():
            text_lines = _region_lines(start, end, region_text, o.content)
            if text_lines is None:
                linenos = range(start, end + 1) if whole else sorted(hits)
                for lineno in linenos:
                    pieces = []
                    if include_path:
                        pieces.append(str(o.path))
                    if include_numbers:
                        pieces.append(str(lineno))
                    if pieces:
                        lines_out.append(":".join(pieces))
                continue
            for lineno, text in text_lines:
                is_match = whole or lineno in hits
                sep = ":" if is_match else "-"
                pieces = []
                if include_path:
                    pieces.append(str(o.path))
                if include_numbers:
                    pieces.append(str(lineno))
                pieces.append(text)
                lines_out.append(sep.join(pieces))
    return "\n".join(lines_out)


def _region_lines(
    start: int,
    end: int,
    region_text: str | None,
    full_content: str | None,
) -> list[tuple[int, str]] | None:
    """Return ``(lineno, text)`` pairs for a match region, or None without text.

    Prefers the region's own text; an empty-string region falls back to
    slicing the full content, then to bare empty lines for the span — empty
    is treated as "text not carried", never as "render nothing". Line
    numbers are 1-indexed file positions.
    """
    if region_text:
        return list(enumerate(region_text.splitlines(), start=start))
    if full_content:
        text_lines = full_content.splitlines()
        return [(n, text_lines[n - 1]) for n in range(start, end + 1) if 0 < n <= len(text_lines)]
    if region_text is not None:
        return [(n, "") for n in range(start, end + 1)]
    return None


def _render_tree(result: Result) -> str:
    """ASCII tree of observation paths."""
    paths = sorted(o.path.strip("/").split("/") for o in result.observations if o.path != "/")
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


def _render_action(result: Result) -> str:
    """Action one-liner — ``{Verb} {path}`` or ``{Verb} {N} paths``."""
    count = len(result.observations)
    verb = _verb_for(result.function)
    if count == 0:
        return "No changes"
    if count == 1:
        return f"{verb} {result.observations[0].path}"
    return f"{verb} {count} paths"


# Kinds counted in the write-success summary. Versions are deliberately omitted
# (they are bookkeeping rows the agent does not need to know about).
_WRITE_SUMMARY_KINDS: tuple[str, ...] = ("file", "chunk", "edge")

# File write statuses, in breakdown order. A missing status reads as created.
_FILE_STATUSES: tuple[str, ...] = ("created", "updated", "unchanged")


def _render_write(result: Result) -> str:
    """Render a ``write`` result.

    Up to two blocks, errors first when present. Empty results render
    ``write: nothing to do``. The summary line counts files/chunks/edges
    only; version rows are excluded. Single-file batches append a
    ``  <status> <path>`` line below the summary.
    """
    error_block = _render_write_errors(result.errors)
    success_block = _render_write_success(result.observations)

    if not error_block and not success_block:
        return "write: nothing to do"

    blocks = [b for b in (error_block, success_block) if b]
    return "\n\n".join(blocks)


def _render_write_errors(errors: list[ResultError]) -> str:
    if not errors:
        return ""
    lines = ["write errors:", *(f"  {err.message}" for err in errors)]
    return "\n".join(lines)


def _render_write_success(observations: list[Observation]) -> str:
    """Summarize a write: a reconciling file breakdown plus chunk/edge counts.

    File rows are reported by status — created / updated / unchanged — and the
    buckets always sum to the file count (a missing status reads as created).
    Chunks and edges are bare counts; version rows are excluded. A single-file
    write appends a ``  <status> <path>`` detail line.
    """
    files = [o for o in observations if o.kind == "file"]
    other: dict[str, int] = {}
    for o in observations:
        if o.kind in _WRITE_SUMMARY_KINDS and o.kind != "file":
            other[o.kind] = other.get(o.kind, 0) + 1

    if not files and not other:
        return ""

    parts: list[str] = []
    if files:
        parts.append(_file_summary(files))
    parts += [_pluralize(kind, other[kind]) for kind in _WRITE_SUMMARY_KINDS if other.get(kind)]

    summary = "write success: " + ", ".join(parts)
    if len(files) == 1:
        o = files[0]
        return f"{summary}\n\n  {o.status or 'created'} {o.path}"
    return summary


def _file_summary(files: list[Observation]) -> str:
    """``N files (a created, b updated, c unchanged)``; status omitted for one file.

    Every file lands in exactly one bucket (a missing status reads as created),
    so the breakdown always reconciles with the count, reported in
    created/updated/unchanged order.
    """
    if len(files) == 1:
        return "1 file"
    counts: dict[str, int] = {}
    for o in files:
        status = o.status or "created"
        counts[status] = counts.get(status, 0) + 1
    breakdown = ", ".join(f"{counts[s]} {s}" for s in _FILE_STATUSES if s in counts)
    return f"{_pluralize('file', len(files))} ({breakdown})"


def _pluralize(kind: str, n: int) -> str:
    word = kind if n == 1 else kind + "s"
    return f"{n} {word}"


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
