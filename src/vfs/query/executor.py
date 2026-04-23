"""Execution engine for the CLI query AST."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING

from vfs.columns import CANDIDATE_FIELD_TO_MODEL_COLUMNS, required_model_columns
from vfs.paths import normalize_path, parse_kind
from vfs.query.ast import (
    CaseMode,
    CopyCommand,
    DeleteCommand,
    EditCommand,
    ExceptStage,
    GlobCommand,
    GraphTraversalCommand,
    GrepCommand,
    GrepOutputMode,
    IntersectStage,
    KindsCommand,
    LexicalSearchCommand,
    LsCommand,
    MeetingGraphCommand,
    MkdirCommand,
    MkedgeCommand,
    MoveCommand,
    PipelineNode,
    QueryNode,
    QueryPlan,
    RankCommand,
    ReadCommand,
    SemanticSearchCommand,
    SortCommand,
    StageNode,
    StatCommand,
    TopCommand,
    TreeCommand,
    UnionNode,
    VectorSearchCommand,
    Visibility,
    WriteCommand,
)
from vfs.results import CANDIDATE_FIELDS, PROJECTION_SENTINELS, Candidate, TwoPathOperation, VFSResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from vfs.base import VirtualFileSystem


async def execute_query(
    filesystem: VirtualFileSystem,
    plan: QueryPlan,
    *,
    initial: VFSResult | None = None,
    user_id: str | None = None,
) -> VFSResult:
    """Execute a parsed query plan against *filesystem*.

    When ``plan.projection`` is set, it flows down to every stage that
    accepts a ``columns`` kwarg so the SELECT pulls exactly the requested
    fields.  After the pipeline finishes, any projected entry-field that
    is null on every entry triggers a single ``fs.read(columns=missing)``
    backfill — that's the one place hydration may issue an extra query,
    and it never bypasses the public read surface.
    """
    result = await _execute_node(
        filesystem,
        plan.ast,
        initial,
        projection=plan.projection,
        user_id=user_id,
    )
    return await _hydrate_projection(filesystem, result, plan.projection, user_id=user_id)


async def _execute_node(
    filesystem: VirtualFileSystem,
    node: QueryNode,
    current: VFSResult | None,
    *,
    projection: tuple[str, ...] | None = None,
    user_id: str | None = None,
) -> VFSResult:
    match node:
        case PipelineNode(source=source, stages=stages):
            result = await _execute_node(filesystem, source, current, projection=projection, user_id=user_id)
            for stage in stages:
                result = await _execute_stage(
                    filesystem,
                    stage,
                    result,
                    projection=projection,
                    user_id=user_id,
                )
            return result
        case UnionNode(operands=operands):
            results = await asyncio.gather(
                *(
                    _execute_node(filesystem, operand, current, projection=projection, user_id=user_id)
                    for operand in operands
                ),
            )
            return filesystem._merge_results(list(results))
        case _:
            assert isinstance(node, StageNode)
            return await _execute_stage(filesystem, node, current, projection=projection, user_id=user_id)


def _cols_for(function: str, projection: tuple[str, ...] | None) -> frozenset[str] | None:
    """Resolve the model-column set for *function* under the user's projection.

    ``None`` projection passes through as ``None`` — the impl falls back
    to its own ``default_columns(function)``.  Otherwise we widen the
    default with whatever model columns back the user-requested entry
    fields.
    """
    if projection is None:
        return None
    return required_model_columns(function, projection)


async def _execute_stage(
    filesystem: VirtualFileSystem,
    stage: StageNode,
    current: VFSResult | None,
    *,
    projection: tuple[str, ...] | None = None,
    user_id: str | None = None,
) -> VFSResult:
    match stage:
        case ReadCommand(paths=paths):
            return await _read_like(
                filesystem.read,
                current,
                paths,
                command_name="read",
                function_name="read",
                columns=_cols_for("read", projection),
                user_id=user_id,
            )
        case StatCommand(paths=paths):
            return await _read_like(
                filesystem.stat,
                current,
                paths,
                command_name="stat",
                function_name="stat",
                columns=_cols_for("stat", projection),
                user_id=user_id,
            )
        case DeleteCommand(paths=paths):
            return await _read_like(
                filesystem.delete,
                current,
                paths,
                command_name="rm",
                function_name="delete",
                user_id=user_id,
            )
        case EditCommand(old=old, new=new, paths=paths, replace_all=replace_all):
            if current is not None and paths:
                raise ValueError("edit cannot combine piped input with explicit paths")
            if current is not None:
                return await filesystem.edit(
                    candidates=current,
                    old=old,
                    new=new,
                    replace_all=replace_all,
                    user_id=user_id,
                )
            if not paths:
                raise ValueError("edit requires a path when it is not used in a pipeline")
            explicit = _paths_result(paths, function="edit")
            return await filesystem.edit(
                candidates=explicit,
                old=old,
                new=new,
                replace_all=replace_all,
                user_id=user_id,
            )
        case WriteCommand(path=path, content=content, overwrite=overwrite):
            if current is not None:
                raise ValueError("write cannot be used in a pipeline")
            return await filesystem.write(
                path=normalize_path(path),
                content=content,
                overwrite=overwrite,
                user_id=user_id,
            )
        case MkdirCommand(paths=paths):
            if current is not None:
                raise ValueError("mkdir cannot be used in a pipeline")
            results = await asyncio.gather(
                *(filesystem.mkdir(normalize_path(path), user_id=user_id) for path in paths),
            )
            return filesystem._merge_results(list(results))
        case MoveCommand(src=src, dest=dest, overwrite=overwrite):
            return await _execute_transfer(filesystem, "move", current, src, dest, overwrite, user_id=user_id)
        case CopyCommand(src=src, dest=dest, overwrite=overwrite):
            return await _execute_transfer(filesystem, "copy", current, src, dest, overwrite, user_id=user_id)
        case MkedgeCommand(source=source, edge_type=edge_type, target=target):
            return await _execute_mkedge(filesystem, current, source, edge_type, target, user_id=user_id)
        case LsCommand(paths=paths):
            ls_cols = _cols_for("ls", projection)
            if current is not None and paths:
                raise ValueError("ls cannot combine piped input with explicit paths")
            if current is not None:
                return await filesystem.ls(candidates=current, columns=ls_cols, user_id=user_id)
            if not paths:
                return await filesystem.ls(path="/", columns=ls_cols, user_id=user_id)
            explicit = _paths_result(paths, function="ls")
            return await filesystem.ls(candidates=explicit, columns=ls_cols, user_id=user_id)
        case TreeCommand(paths=paths, max_depth=max_depth, visibility=visibility):
            roots = tuple(normalize_path(path) for path in paths) if paths else ()
            return await _execute_tree(
                filesystem,
                current,
                roots,
                max_depth,
                visibility,
                columns=_cols_for("tree", projection),
                user_id=user_id,
            )
        case GlobCommand(
            pattern=pattern,
            paths=glob_paths,
            ext=glob_ext,
            max_count=glob_max_count,
            visibility=visibility,
        ):
            result = await _execute_glob(
                filesystem,
                current,
                pattern,
                glob_paths,
                glob_ext,
                glob_max_count,
                visibility,
                columns=_cols_for("glob", projection),
                user_id=user_id,
            )
            return _apply_visibility(result, visibility, {"file", "directory"})
        case GrepCommand(
            pattern=pattern,
            paths=grep_paths,
            ext=grep_ext,
            ext_not=grep_ext_not,
            globs=grep_globs,
            globs_not=grep_globs_not,
            case_mode=case_mode,
            fixed_strings=fixed_strings,
            word_regexp=word_regexp,
            invert_match=invert_match,
            before_context=before_context,
            after_context=after_context,
            output_mode=output_mode,
            max_count=max_count,
            visibility=visibility,
        ):
            result = await _execute_grep(
                filesystem,
                current,
                pattern=pattern,
                paths=grep_paths,
                ext=grep_ext,
                ext_not=grep_ext_not,
                globs=grep_globs,
                globs_not=grep_globs_not,
                case_mode=case_mode,
                fixed_strings=fixed_strings,
                word_regexp=word_regexp,
                invert_match=invert_match,
                before_context=before_context,
                after_context=after_context,
                output_mode=output_mode,
                max_count=max_count,
                visibility=visibility,
                columns=_cols_for("grep", projection),
                user_id=user_id,
            )
            return _apply_visibility(result, visibility, {"file", "directory"})
        case SemanticSearchCommand(query=query, k=k, visibility=visibility):
            result = await filesystem.semantic_search(query=query, k=k, candidates=current, user_id=user_id)
            return _apply_visibility(result, visibility, {"file", "directory"})
        case LexicalSearchCommand(query=query, k=k, visibility=visibility):
            result = await _execute_lexical(filesystem, current, query, k, visibility, user_id=user_id)
            return _apply_visibility(result, visibility, {"file", "directory"})
        case VectorSearchCommand(vector=vector, k=k, visibility=visibility):
            result = await filesystem.vector_search(vector=list(vector), k=k, candidates=current, user_id=user_id)
            return _apply_visibility(result, visibility, {"file", "directory"})
        case GraphTraversalCommand(method_name=method_name, paths=paths, depth=depth, visibility=visibility):
            result = await _execute_graph_traversal(filesystem, current, method_name, paths, depth, user_id=user_id)
            return _apply_visibility(result, visibility, {"file", "directory", "edge"})
        case MeetingGraphCommand(paths=paths, minimal=minimal, visibility=visibility):
            function_name = "min_meeting_subgraph" if minimal else "meeting_subgraph"
            seeds = _seed_candidates(current, paths, "meetinggraph", function_name=function_name)
            result = (
                await filesystem.min_meeting_subgraph(candidates=seeds, user_id=user_id)
                if minimal
                else await filesystem.meeting_subgraph(candidates=seeds, user_id=user_id)
            )
            return _apply_visibility(result, visibility, {"file", "directory", "edge"})
        case RankCommand(method_name=method_name, paths=paths, visibility=visibility):
            result = await _execute_rank(filesystem, current, method_name, paths, user_id=user_id)
            return _apply_visibility(result, visibility, {"file", "directory", "edge"})
        case SortCommand(reverse=reverse):
            if current is None:
                raise ValueError("sort requires piped input")
            return current.sort(reverse=reverse)
        case TopCommand(k=k):
            if current is None:
                raise ValueError("top requires piped input")
            return current.top(k)
        case KindsCommand(kinds=kinds):
            if current is None:
                raise ValueError("kinds requires piped input")
            return current.kinds(*kinds)
        case IntersectStage(query=query):
            if current is None:
                raise ValueError("intersect requires piped input")
            other = await _execute_node(filesystem, query, None, projection=projection, user_id=user_id)
            return current & other
        case ExceptStage(query=query):
            if current is None:
                raise ValueError("except requires piped input")
            other = await _execute_node(filesystem, query, None, projection=projection, user_id=user_id)
            return current - other
        case _:  # pragma: no cover
            raise ValueError(f"Unknown stage: {stage}")


async def _read_like(
    method: Callable[..., Awaitable[VFSResult]],
    current: VFSResult | None,
    paths: tuple[str, ...],
    *,
    command_name: str,
    function_name: str,
    columns: frozenset[str] | None = None,
    user_id: str | None = None,
) -> VFSResult:
    extra: dict[str, object] = {"columns": columns} if columns is not None else {}
    if current is not None and paths:
        raise ValueError(f"{command_name} cannot combine piped input with explicit paths")
    if current is not None:
        return await method(candidates=current, user_id=user_id, **extra)
    if not paths:
        raise ValueError(f"{command_name} requires explicit paths when it is not used in a pipeline")
    explicit = _paths_result(paths, function=function_name)
    return await method(candidates=explicit, user_id=user_id, **extra)


async def _execute_transfer(
    filesystem: VirtualFileSystem,
    op: str,
    current: VFSResult | None,
    src: str | None,
    dest: str,
    overwrite: bool,
    *,
    user_id: str | None = None,
) -> VFSResult:
    normalized_dest = normalize_path(dest)
    match (current, src):
        case (None, None):
            raise ValueError(f"{op} requires a source path when it is not used in a pipeline")
        case (None, str() as source):
            method = filesystem.move if op == "move" else filesystem.copy
            return await method(src=normalize_path(source), dest=normalized_dest, overwrite=overwrite, user_id=user_id)
        case (VFSResult(), str()):
            raise ValueError(f"{op} cannot combine piped input with an explicit source path")
        case (VFSResult(candidates=entries), None):
            if not entries:
                return VFSResult(function=op, candidates=[])
            ops = [
                TwoPathOperation(src=entry.path, dest=_preserve_under_root(normalized_dest, entry.path))
                for entry in entries
            ]
            if op == "move":
                return await filesystem.move(moves=ops, overwrite=overwrite, user_id=user_id)
            return await filesystem.copy(copies=ops, overwrite=overwrite, user_id=user_id)
        case _:  # pragma: no cover
            raise ValueError(f"Invalid arguments for {op}")


async def _execute_mkedge(
    filesystem: VirtualFileSystem,
    current: VFSResult | None,
    source: str | None,
    edge_type: str,
    target: str,
    *,
    user_id: str | None = None,
) -> VFSResult:
    normalized_target = normalize_path(target)
    if current is None:
        if source is None:
            raise ValueError("mkedge requires a source path when it is not used in a pipeline")
        return await filesystem.mkedge(
            source=normalize_path(source),
            target=normalized_target,
            edge_type=edge_type,
            user_id=user_id,
        )
    if source is not None:
        raise ValueError("mkedge cannot combine piped input with an explicit source path")
    results = await asyncio.gather(
        *(
            filesystem.mkedge(
                source=entry.path,
                target=normalized_target,
                edge_type=edge_type,
                user_id=user_id,
            )
            for entry in current.candidates
        )
    )
    return filesystem._merge_results(list(results))


async def _execute_tree(
    filesystem: VirtualFileSystem,
    current: VFSResult | None,
    roots: tuple[str, ...],
    max_depth: int | None,
    visibility: Visibility,
    *,
    columns: frozenset[str] | None = None,
    user_id: str | None = None,
) -> VFSResult:
    if current is not None and roots:
        raise ValueError("tree cannot combine piped input with explicit paths")

    if current is not None:
        roots = tuple(entry.path for entry in current.candidates)
    elif not roots:
        roots = ("/",)

    if visibility.include_all or visibility.include_kinds:
        return await _collect_tree(
            filesystem,
            roots,
            max_depth=max_depth,
            visibility=visibility,
            result_function="tree",
            user_id=user_id,
        )

    results = await asyncio.gather(
        *(filesystem.tree(path=root, max_depth=max_depth, columns=columns, user_id=user_id) for root in roots),
    )
    return filesystem._merge_results(list(results))


async def _execute_glob(
    filesystem: VirtualFileSystem,
    current: VFSResult | None,
    pattern: str,
    paths: tuple[str, ...],
    ext: tuple[str, ...],
    max_count: int | None,
    visibility: Visibility,
    *,
    columns: frozenset[str] | None = None,
    user_id: str | None = None,
) -> VFSResult:
    candidates = current
    if candidates is None and (visibility.include_all or visibility.include_kinds):
        candidates = await _collect_tree(filesystem, ("/",), max_depth=None, visibility=visibility, user_id=user_id)
    return await filesystem.glob(
        pattern=pattern,
        paths=paths,
        ext=ext,
        max_count=max_count,
        columns=columns,
        candidates=candidates,
        user_id=user_id,
    )


async def _execute_grep(
    filesystem: VirtualFileSystem,
    current: VFSResult | None,
    *,
    pattern: str,
    paths: tuple[str, ...],
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
    globs: tuple[str, ...],
    globs_not: tuple[str, ...],
    case_mode: CaseMode,
    fixed_strings: bool,
    word_regexp: bool,
    invert_match: bool,
    before_context: int,
    after_context: int,
    output_mode: GrepOutputMode,
    max_count: int | None,
    visibility: Visibility,
    columns: frozenset[str] | None = None,
    user_id: str | None = None,
) -> VFSResult:
    candidates = current
    if candidates is None and (visibility.include_all or visibility.include_kinds):
        candidates = await _collect_tree(filesystem, ("/",), max_depth=None, visibility=visibility, user_id=user_id)
    if candidates is not None and any(
        _entry_kind(entry) != "file" and entry.content is None for entry in candidates.candidates
    ):
        candidates = await filesystem.read(candidates=candidates, user_id=user_id)
    return await filesystem.grep(
        pattern=pattern,
        paths=paths,
        ext=ext,
        ext_not=ext_not,
        globs=globs,
        globs_not=globs_not,
        case_mode=case_mode,
        fixed_strings=fixed_strings,
        word_regexp=word_regexp,
        invert_match=invert_match,
        before_context=before_context,
        after_context=after_context,
        output_mode=output_mode,
        max_count=max_count,
        columns=columns,
        candidates=candidates,
        user_id=user_id,
    )


async def _execute_lexical(
    filesystem: VirtualFileSystem,
    current: VFSResult | None,
    query: str,
    k: int,
    visibility: Visibility,
    *,
    user_id: str | None = None,
) -> VFSResult:
    candidates = current
    if candidates is None and (visibility.include_all or visibility.include_kinds):
        candidates = await _collect_tree(filesystem, ("/",), max_depth=None, visibility=visibility, user_id=user_id)
    return await filesystem.lexical_search(query=query, k=k, candidates=candidates, user_id=user_id)


async def _execute_graph_traversal(
    filesystem: VirtualFileSystem,
    current: VFSResult | None,
    method_name: str,
    paths: tuple[str, ...],
    depth: int,
    *,
    user_id: str | None = None,
) -> VFSResult:
    method = getattr(filesystem, method_name)
    if current is not None and paths:
        raise ValueError(f"{method_name} cannot combine piped input with explicit paths")
    if current is not None:
        if method_name == "neighborhood":
            return await method(candidates=current, depth=depth, user_id=user_id)
        return await method(candidates=current, user_id=user_id)
    if paths:
        explicit = _paths_result(paths, function=method_name)
        if len(paths) > 1:
            if method_name == "neighborhood":
                return await method(candidates=explicit, depth=depth, user_id=user_id)
            return await method(candidates=explicit, user_id=user_id)
        if method_name == "neighborhood":
            return await method(path=explicit.candidates[0].path, depth=depth, user_id=user_id)
        return await method(path=explicit.candidates[0].path, user_id=user_id)
    raise ValueError(f"{method_name} requires explicit paths when it is not used in a pipeline")


async def _execute_rank(
    filesystem: VirtualFileSystem,
    current: VFSResult | None,
    method_name: str,
    paths: tuple[str, ...],
    *,
    user_id: str | None = None,
) -> VFSResult:
    method = getattr(filesystem, method_name)
    if current is not None and paths:
        raise ValueError(f"{method_name} cannot combine piped input with explicit paths")
    if current is not None:
        return await method(candidates=current, user_id=user_id)
    if paths:
        return await method(candidates=_paths_result(paths, function=method_name), user_id=user_id)
    return await method(user_id=user_id)


def _seed_candidates(
    current: VFSResult | None,
    paths: tuple[str, ...],
    label: str,
    *,
    function_name: str = "",
) -> VFSResult:
    if current is not None and paths:
        raise ValueError(f"{label} cannot combine piped input with explicit paths")
    if current is not None:
        return current
    if not paths:
        raise ValueError(f"{label} requires explicit paths when it is not used in a pipeline")
    return _paths_result(paths, function=function_name)


async def _hydrate_projection(
    filesystem: VirtualFileSystem,
    result: VFSResult,
    projection: tuple[str, ...] | None,
    *,
    user_id: str | None = None,
) -> VFSResult:
    """Backfill any projected entry-fields that are null on every entry.

    Applies only when ``projection`` is set, the result has entries, and
    at least one requested field is null on *all* entries — that's the
    signal that the producing stage didn't populate it.  Mixed states
    (some entries have it, others don't) are left alone: that's a
    legitimate union-of-stages outcome, not a missing column.

    Hydration goes through ``filesystem.read(columns=...)`` — the same
    public surface any caller uses — so it picks up mounts, scoping, and
    permission checks for free.  At most one extra query.
    """
    if not projection or not result.candidates:
        return result

    requested_fields = [name for name in projection if name not in PROJECTION_SENTINELS and name in CANDIDATE_FIELDS]
    if not requested_fields:
        return result

    missing_fields = [name for name in requested_fields if all(getattr(e, name) is None for e in result.candidates)]
    if not missing_fields:
        return result

    missing_cols: frozenset[str] = frozenset()
    for name in missing_fields:
        missing_cols |= CANDIDATE_FIELD_TO_MODEL_COLUMNS.get(name, frozenset())
    if not missing_cols:
        # Only computed fields requested (score / lines) — nothing to read.
        return result

    seed = VFSResult(
        function="read",
        candidates=[Candidate(path=e.path) for e in result.candidates],
    )
    hydrated = await filesystem.read(
        candidates=seed,
        columns=missing_cols,
        user_id=user_id,
    )
    by_path = {e.path: e for e in hydrated.candidates}
    new_entries = []
    for entry in result.candidates:
        fresh = by_path.get(entry.path)
        if fresh is None:
            new_entries.append(entry)
            continue
        update: dict[str, object] = {}
        for name in missing_fields:
            if getattr(entry, name) is None:
                value = getattr(fresh, name)
                if value is not None:
                    update[name] = value
        new_entries.append(entry.model_copy(update=update) if update else entry)
    return result._with_candidates(new_entries)


def _paths_result(paths: tuple[str, ...], function: str = "") -> VFSResult:
    entries = []
    for path in paths:
        normalized = normalize_path(path)
        entries.append(Candidate(path=normalized, kind=parse_kind(normalized)))
    return VFSResult(function=function, candidates=entries)


def _entry_kind(entry: Candidate) -> str:
    return entry.kind or parse_kind(entry.path)


def _preserve_under_root(root: str, source_path: str) -> str:
    relative = normalize_path(source_path).lstrip("/")
    if not relative:
        raise ValueError("Cannot preserve the root path under a destination root")
    return normalize_path(f"{root}/{relative}")


def _apply_visibility(
    result: VFSResult,
    visibility: Visibility,
    defaults: set[str],
) -> VFSResult:
    if visibility.include_all:
        return result
    allowed = set(defaults) | set(visibility.include_kinds)
    filtered = [entry for entry in result.candidates if _entry_kind(entry) in allowed]
    return result._with_candidates(filtered)


async def _collect_tree(
    filesystem: VirtualFileSystem,
    roots: tuple[str, ...],
    *,
    max_depth: int | None,
    visibility: Visibility,
    result_function: str = "ls",
    user_id: str | None = None,
) -> VFSResult:
    queue: deque[tuple[str, int]] = deque((normalize_path(root), 0) for root in roots)
    seen: set[str] = set()
    collected: list[Candidate] = []
    while queue:
        path, depth = queue.popleft()
        if path in seen:
            continue
        seen.add(path)

        if max_depth is not None and depth >= max_depth:
            continue

        listing = await filesystem.ls(path=path, user_id=user_id)
        if not listing.success:
            return listing

        visible_listing = _apply_visibility(listing, visibility, {"file", "directory"})
        collected.extend(visible_listing.candidates)

        for entry in listing.candidates:
            kind = _entry_kind(entry)
            if kind in {"file", "directory"}:
                queue.append((entry.path, depth + 1))

    deduped: dict[str, Candidate] = {entry.path: entry for entry in collected}
    ordered = [deduped[path] for path in sorted(deduped)]
    return VFSResult(function=result_function, candidates=ordered)
