"""Text renderers for query results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grover.paths import split_path

if TYPE_CHECKING:
    from grover.query.ast import RenderMode
    from grover.results import Candidate, GroverResult


def render_query_result(
    result: GroverResult,
    *,
    mode: RenderMode,
) -> str:
    """Render *result* into a human-readable text response."""
    if not result.success and not result.candidates:
        return _render_errors(result.errors)

    match mode:
        case "content":
            body = _render_content(result)
        case "action":
            body = _render_action(result)
        case "ls":
            body = _render_ls(result)
        case "tree":
            body = _render_tree(result)
        case "stat":
            body = _render_stat(result)
        case "query_list":
            body = _render_query_list(result)
        case _:
            raise AssertionError(f"Unhandled render mode: {mode}")

    if result.errors:
        error_block = _render_errors(result.errors)
        return f"{body}\n\n{error_block}" if body else error_block
    return body


def _render_content(result: GroverResult) -> str:
    if not result.candidates:
        return ""
    if len(result.candidates) == 1:
        return result.candidates[0].content or ""

    blocks = []
    for candidate in sorted(result.candidates, key=lambda item: item.path):
        header = f"==> {candidate.path} <=="
        body = candidate.content or ""
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks)


def _render_action(result: GroverResult) -> str:
    if result.errors and not result.candidates:
        return _render_errors(result.errors)
    operation = _last_operation(result)
    count = len(result.candidates)
    if count == 0:
        return "No changes"
    if count == 1:
        path = result.candidates[0].path
        return f"{_verb_for(operation)} {path}"
    return f"{_verb_for(operation)} {count} paths"


def _render_ls(result: GroverResult) -> str:
    names = sorted(_display_name(candidate) for candidate in result.candidates)
    return "\n".join(names)


def _render_tree(result: GroverResult) -> str:
    paths = sorted(candidate.path.strip("/").split("/") for candidate in result.candidates if candidate.path != "/")
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


def _render_stat(result: GroverResult) -> str:
    blocks = []
    for candidate in sorted(result.candidates, key=lambda item: item.path):
        lines = [candidate.path]
        for label, value in (
            ("kind", candidate.kind),
            ("lines", candidate.lines),
            ("size_bytes", candidate.size_bytes),
            ("tokens", candidate.tokens),
            ("mime_type", candidate.mime_type),
            ("created_at", candidate.created_at),
            ("updated_at", candidate.updated_at),
        ):
            if value is not None:
                lines.append(f"{label}: {value}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_query_list(result: GroverResult) -> str:
    ranked = any(candidate.score for candidate in result.candidates)
    lines = []
    for candidate in sorted(result.candidates, key=lambda item: item.path):
        if ranked:
            lines.append(f"{candidate.path}\t{candidate.score:.4f}")
        else:
            lines.append(candidate.path)
    return "\n".join(lines)


def _render_errors(errors: list[str]) -> str:
    return "\n".join(f"Error: {error}" for error in errors)


def _last_operation(result: GroverResult) -> str:
    for candidate in result.candidates:
        if candidate.details:
            return candidate.details[-1].operation
    return "completed"


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
        case "mkconn":
            return "Connected"
        case _:
            return operation.replace("_", " ").capitalize()


def _display_name(candidate: Candidate) -> str:
    _, name = split_path(candidate.path)
    return name or candidate.path
