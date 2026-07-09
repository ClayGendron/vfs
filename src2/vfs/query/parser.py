"""Hand-rolled parser for the CLI query language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast, overload

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
from vfs.query.types import resolve_type_aliases
from vfs.results import validate_projection

if TYPE_CHECKING:
    from collections.abc import Callable

    from vfs.paths import ObjectKind


class QuerySyntaxError(ValueError):
    """Raised when the query string is syntactically invalid."""


class QueryExecutionError(ValueError):
    """Raised when a parsed query cannot be executed."""


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


FlagValue = str | bool | tuple[str, ...]


@dataclass(frozen=True)
class CommandSpec:
    """Declarative parser spec for one CLI command family.

    ``flags`` maps flag names to their arity (0 = boolean, 1 = takes a
    value).  ``repeatable`` marks flags that may appear more than once —
    their values are collected into a tuple instead of rejected as
    duplicates.  Short flags (``-t``) live alongside long flags
    (``--type``) in the same dict; aliases pointing at the same logical
    option should all be listed in ``repeatable`` together if any is.
    """

    canonical_name: str
    aliases: tuple[str, ...]
    flags: dict[str, int]
    builder: Callable[[list[str], dict[str, FlagValue]], StageNode]
    repeatable: frozenset[str] = frozenset()


def tokenize(query: str) -> tuple[Token, ...]:
    """Tokenize a CLI query string."""
    tokens: list[Token] = []
    i = 0
    while i < len(query):
        ch = query[i]
        match ch:
            case " " | "\t" | "\r" | "\n":
                i += 1
            case "(":
                tokens.append(Token("lparen", ch, i))
                i += 1
            case ")":
                tokens.append(Token("rparen", ch, i))
                i += 1
            case "|":
                tokens.append(Token("pipe", ch, i))
                i += 1
            case "&":
                tokens.append(Token("amp", ch, i))
                i += 1
            case "'" | '"':
                quote = ch
                start = i
                i += 1
                chars: list[str] = []
                while i < len(query):
                    current = query[i]
                    match current:
                        case "\\":
                            if i + 1 >= len(query):
                                raise QuerySyntaxError(f"Unterminated escape sequence at position {i}")
                            chars.append(query[i + 1])
                            i += 2
                        case _ if current == quote:
                            tokens.append(Token("string", "".join(chars), start))
                            i += 1
                            break
                        case _:
                            chars.append(current)
                            i += 1
                else:
                    raise QuerySyntaxError(f"Unterminated string starting at position {start}")
            case _:
                start = i
                while i < len(query):
                    current = query[i]
                    match current:
                        case " " | "\t" | "\r" | "\n" | "(" | ")" | "|" | "&":
                            break
                        case _:
                            i += 1
                tokens.append(Token("word", query[start:i], start))

    return tuple(tokens)


class _Parser:
    def __init__(self, tokens: tuple[Token, ...]) -> None:
        self._tokens = tokens
        self._index = 0

    def parse(self) -> QueryNode:
        if not self._tokens:
            raise QuerySyntaxError("Query cannot be empty")
        node = self._parse_union()
        if not self._at_end():
            token = self._peek()
            raise QuerySyntaxError(f"Unexpected token {token.value!r} at position {token.position}")
        return node

    def _parse_union(self) -> QueryNode:
        operands = [self._parse_pipeline()]
        while self._match("amp"):
            operands.append(self._parse_pipeline())
        return operands[0] if len(operands) == 1 else UnionNode(tuple(operands))

    def _parse_pipeline(self) -> QueryNode:
        source = self._parse_primary()
        stages: list[StageNode] = []
        while self._match("pipe"):
            stages.append(self._parse_stage())
        return source if not stages else PipelineNode(source=source, stages=tuple(stages))

    def _parse_primary(self) -> QueryNode:
        if self._match("lparen"):
            expr = self._parse_union()
            self._expect("rparen", "Expected ')' to close grouped expression")
            return expr
        return self._parse_stage()

    def _parse_stage(self) -> StageNode:
        token = self._expect("word", "Expected a command name")
        name = token.value.lower()
        if name in {"intersect", "except"}:
            self._expect("lparen", f"Expected '(' after {name}")
            query = self._parse_union()
            self._expect("rparen", "Expected ')' to close subquery")
            return IntersectStage(query) if name == "intersect" else ExceptStage(query)

        args: list[str] = []
        while not self._at_end():
            token = self._peek()
            if token.kind in {"pipe", "amp", "rparen"}:
                break
            if token.kind not in {"word", "string"}:
                raise QuerySyntaxError(f"Unexpected token {token.value!r} at position {token.position}")
            args.append(self._advance().value)
        return _build_command(name, args)

    def _at_end(self) -> bool:
        return self._index >= len(self._tokens)

    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _match(self, kind: str) -> bool:
        if self._at_end() or self._peek().kind != kind:
            return False
        self._index += 1
        return True

    def _expect(self, kind: str, message: str) -> Token:
        if self._at_end():
            raise QuerySyntaxError(message)
        token = self._peek()
        if token.kind != kind:
            raise QuerySyntaxError(f"{message} at position {token.position}")
        self._index += 1
        return token


def parse_query(query: str) -> QueryPlan:
    """Parse *query* into an AST and an ordered execution plan.

    Recognizes a top-level ``--output`` flag — a comma-separated list of
    Candidate field names (or the ``default`` / ``all`` sentinels) that
    selects what each returned entry should carry.  ``--output`` may
    appear anywhere in the query and applies to the whole pipeline.
    Unknown field names raise :class:`QuerySyntaxError` at parse time.
    """
    tokens, projection = _extract_output_flag(tokenize(query))
    ast = _Parser(tokens).parse()
    return QueryPlan(
        ast=ast,
        methods=_planned_methods(ast),
        projection=projection,
    )


def _extract_output_flag(
    tokens: tuple[Token, ...],
) -> tuple[tuple[Token, ...], tuple[str, ...] | None]:
    """Strip ``--output`` (and its value) from the token stream.

    Accepts both ``--output path,score`` (two tokens) and
    ``--output=path,score`` (one token) forms.  Comma-splits the value
    into individual projection names and validates them via
    :func:`validate_projection` so unknowns surface immediately, before
    any backend work happens.

    Returns the filtered token stream plus the projection tuple (or
    ``None`` if no flag was present).  Repeating ``--output`` is an
    error — the user almost certainly meant to combine names in one
    comma-separated list.
    """
    out: list[Token] = []
    projection: tuple[str, ...] | None = None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        raw_value: str | None = None
        consumed = 1
        if token.kind == "word" and token.value == "--output":
            if i + 1 >= len(tokens) or tokens[i + 1].kind not in {"word", "string"}:
                msg = f"--output requires a value at position {token.position}"
                raise QuerySyntaxError(msg)
            raw_value = tokens[i + 1].value
            consumed = 2
        elif token.kind == "word" and token.value.startswith("--output="):
            raw_value = token.value[len("--output=") :]

        if raw_value is not None:
            if projection is not None:
                msg = f"--output may only be specified once (position {token.position})"
                raise QuerySyntaxError(msg)
            names = tuple(n for n in (part.strip() for part in raw_value.split(",")) if n)
            if not names:
                msg = f"--output requires at least one field name at position {token.position}"
                raise QuerySyntaxError(msg)
            try:
                projection = validate_projection(names)
            except ValueError as exc:
                raise QuerySyntaxError(str(exc)) from exc
            i += consumed
            continue

        out.append(token)
        i += 1
    return tuple(out), projection


def _build_read(positionals: list[str], _options: dict[str, FlagValue]) -> StageNode:
    return ReadCommand(paths=tuple(positionals))


def _build_stat(positionals: list[str], _options: dict[str, FlagValue]) -> StageNode:
    return StatCommand(paths=tuple(positionals))


def _build_ls(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    return LsCommand(paths=tuple(positionals), visibility=_parse_visibility(options))


def _build_tree(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if len(positionals) > 1:
        raise QuerySyntaxError("tree accepts at most one explicit path")
    return TreeCommand(
        paths=tuple(positionals),
        max_depth=_parse_int_option(options, "--depth"),
        visibility=_parse_visibility(options),
    )


def _build_delete(positionals: list[str], _options: dict[str, FlagValue]) -> StageNode:
    return DeleteCommand(paths=tuple(positionals))


def _build_edit(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if len(positionals) < 2:
        raise QuerySyntaxError("edit requires old and new strings, with an optional path prefix")
    return EditCommand(
        old=positionals[-2],
        new=positionals[-1],
        paths=tuple(positionals[:-2]),
        replace_all="--all" in options,
    )


def _build_write(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    overwrite = _parse_overwrite(options)
    if len(positionals) != 2:
        raise QuerySyntaxError("write requires a path and content string")
    return WriteCommand(path=positionals[0], content=positionals[1], overwrite=overwrite)


def _build_mkdir(positionals: list[str], _options: dict[str, FlagValue]) -> StageNode:
    if not positionals:
        raise QuerySyntaxError("mkdir requires at least one path")
    return MkdirCommand(paths=tuple(positionals))


def _build_move(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    overwrite = _parse_overwrite(options)
    if len(positionals) == 1:
        return MoveCommand(dest=positionals[0], overwrite=overwrite)
    if len(positionals) == 2:
        return MoveCommand(src=positionals[0], dest=positionals[1], overwrite=overwrite)
    raise QuerySyntaxError("mv requires 'src dest' or, in a pipeline, just 'dest-root'")


def _build_copy(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    overwrite = _parse_overwrite(options)
    if len(positionals) == 1:
        return CopyCommand(dest=positionals[0], overwrite=overwrite)
    if len(positionals) == 2:
        return CopyCommand(src=positionals[0], dest=positionals[1], overwrite=overwrite)
    raise QuerySyntaxError("cp requires 'src dest' or, in a pipeline, just 'dest-root'")


def _looks_like_path(value: str) -> bool:
    return value.startswith("/") or "/" in value


def _build_mkedge(positionals: list[str], _options: dict[str, FlagValue]) -> StageNode:
    if len(positionals) == 2:
        first, second = positionals
        if _looks_like_path(first) and not _looks_like_path(second):
            return MkedgeCommand(target=first, edge_type=second)
        return MkedgeCommand(edge_type=first, target=second)
    if len(positionals) == 3:
        source, second, third = positionals
        if _looks_like_path(second) and not _looks_like_path(third):
            return MkedgeCommand(source=source, target=second, edge_type=third)
        return MkedgeCommand(source=source, edge_type=second, target=third)
    raise QuerySyntaxError("mkedge requires 'source target type' or, in a pipeline, 'target type'")


def _build_glob(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if not positionals:
        raise QuerySyntaxError("glob requires a pattern")
    return GlobCommand(
        pattern=positionals[0],
        paths=tuple(positionals[1:]),
        ext=_parse_type_option(options),
        max_count=_parse_int_aliased(options, "--max-count", "-m"),
        visibility=_parse_visibility(options),
    )


def _build_grep(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if not positionals:
        raise QuerySyntaxError("grep requires a pattern")
    return GrepCommand(
        pattern=positionals[0],
        paths=tuple(positionals[1:]),
        ext=_parse_type_option(options),
        ext_not=_parse_type_not_option(options),
        globs=_parse_glob_option(options, negated=False),
        globs_not=_parse_glob_option(options, negated=True),
        case_mode=_parse_case_mode(options),
        fixed_strings=_flag_set(options, "--fixed-strings", "-F"),
        word_regexp=_flag_set(options, "--word-regexp", "-w"),
        invert_match=_flag_set(options, "--invert-match", "-v"),
        before_context=_parse_context_option(options, "--before-context", "-B"),
        after_context=_parse_context_option(options, "--after-context", "-A"),
        output_mode=_parse_grep_output_mode(options),
        max_count=_parse_int_aliased(options, "--max-count", "-m"),
        visibility=_parse_visibility(options),
    )


def _build_search(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if len(positionals) != 1:
        raise QuerySyntaxError("search requires exactly one query string")
    return SemanticSearchCommand(
        query=positionals[0],
        k=_parse_int_option(options, "--k", default=15),
        visibility=_parse_visibility(options),
    )


def _build_lsearch(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if len(positionals) != 1:
        raise QuerySyntaxError("lsearch requires exactly one query string")
    return LexicalSearchCommand(
        query=positionals[0],
        k=_parse_int_option(options, "--k", default=15),
        visibility=_parse_visibility(options),
    )


def _build_vsearch(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if not positionals:
        raise QuerySyntaxError("vsearch requires one or more numeric vector values")
    return VectorSearchCommand(
        vector=_parse_vector(positionals),
        k=_parse_int_option(options, "--k", default=15),
        visibility=_parse_visibility(options),
    )


def _build_meetinggraph(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    return MeetingGraphCommand(
        paths=tuple(positionals),
        minimal="--min" in options,
        visibility=_parse_visibility(options),
    )


TraversalMethod = Literal["predecessors", "successors", "ancestors", "descendants", "neighborhood"]
RankMethod = Literal[
    "pagerank",
    "betweenness_centrality",
    "closeness_centrality",
    "degree_centrality",
    "in_degree_centrality",
    "out_degree_centrality",
    "hits",
]


def _build_graph_traversal(method_name: TraversalMethod) -> Callable[[list[str], dict[str, FlagValue]], StageNode]:
    def _builder(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
        return GraphTraversalCommand(
            method_name=method_name,
            paths=tuple(positionals),
            depth=_parse_int_option(options, "--depth", default=2) if method_name == "neighborhood" else 2,
            visibility=_parse_visibility(options),
        )

    return _builder


def _build_rank(method_name: RankMethod) -> Callable[[list[str], dict[str, FlagValue]], StageNode]:
    def _builder(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
        return RankCommand(method_name, tuple(positionals), _parse_visibility(options))

    return _builder


def _build_sort(positionals: list[str], options: dict[str, FlagValue]) -> StageNode:
    if positionals:
        raise QuerySyntaxError("sort does not accept positional arguments")
    return SortCommand(reverse="--asc" not in options)


def _build_top(positionals: list[str], _options: dict[str, FlagValue]) -> StageNode:
    if len(positionals) != 1:
        raise QuerySyntaxError("top requires exactly one integer")
    return TopCommand(k=_parse_int(positionals[0], "top"))


def _build_kinds(positionals: list[str], _options: dict[str, FlagValue]) -> StageNode:
    if not positionals:
        raise QuerySyntaxError("kinds requires at least one kind")
    return KindsCommand(kinds=tuple(_parse_kind_name(kind) for kind in positionals))


_COMMAND_SPECS = (
    CommandSpec("read", ("read", "cat"), {}, _build_read),
    CommandSpec("stat", ("stat",), {}, _build_stat),
    CommandSpec("ls", ("ls", "list"), {"--all": 0, "--include": 1}, _build_ls),
    CommandSpec("tree", ("tree",), {"--depth": 1, "--all": 0, "--include": 1}, _build_tree),
    CommandSpec("delete", ("rm", "delete", "del"), {}, _build_delete),
    CommandSpec("edit", ("edit",), {"--all": 0}, _build_edit),
    CommandSpec("write", ("write",), {"--overwrite": 0, "--no-overwrite": 0}, _build_write),
    CommandSpec("mkdir", ("mkdir",), {}, _build_mkdir),
    CommandSpec("move", ("mv", "move"), {"--overwrite": 0, "--no-overwrite": 0}, _build_move),
    CommandSpec("copy", ("cp", "copy"), {"--overwrite": 0, "--no-overwrite": 0}, _build_copy),
    CommandSpec("mkedge", ("mkedge",), {}, _build_mkedge),
    CommandSpec(
        "glob",
        ("glob",),
        {
            "--all": 0,
            "--include": 1,
            "--type": 1,
            "-t": 1,
            "--max-count": 1,
            "-m": 1,
        },
        _build_glob,
        repeatable=frozenset({"--type", "-t"}),
    ),
    CommandSpec(
        "grep",
        ("grep",),
        {
            # Visibility (VFS native)
            "--all": 0,
            "--include": 1,
            # Case
            "--ignore-case": 0,
            "-i": 0,
            "--case-sensitive": 0,
            "-s": 0,
            "--smart-case": 0,
            "-S": 0,
            # Pattern interpretation
            "--fixed-strings": 0,
            "-F": 0,
            "--word-regexp": 0,
            "-w": 0,
            "--invert-match": 0,
            "-v": 0,
            # File selection
            "--type": 1,
            "-t": 1,
            "--type-not": 1,
            "-T": 1,
            "--glob": 1,
            "-g": 1,
            # Output mode
            "--files-with-matches": 0,
            "-l": 0,
            "--count": 0,
            "-c": 0,
            "--files": 0,
            # Context
            "--context": 1,
            "-C": 1,
            "--before-context": 1,
            "-B": 1,
            "--after-context": 1,
            "-A": 1,
            # Limits
            "--max-count": 1,
            "-m": 1,
            # rg-compat no-ops (accepted, currently ignored)
            "--hidden": 0,
            "--no-ignore": 0,
            "--no-ignore-vcs": 0,
            "--no-ignore-parent": 0,
            "--no-ignore-global": 0,
            "--follow": 0,
            "--binary": 0,
            "--text": 0,
        },
        _build_grep,
        repeatable=frozenset({"--type", "-t", "--type-not", "-T", "--glob", "-g"}),
    ),
    CommandSpec("search", ("search",), {"--all": 0, "--include": 1, "--k": 1}, _build_search),
    CommandSpec("lsearch", ("lsearch",), {"--all": 0, "--include": 1, "--k": 1}, _build_lsearch),
    CommandSpec("vsearch", ("vsearch", "vectorsearch"), {"--all": 0, "--include": 1, "--k": 1}, _build_vsearch),
    CommandSpec(
        "pred",
        ("pred", "predecessors"),
        {"--all": 0, "--include": 1},
        _build_graph_traversal("predecessors"),
    ),
    CommandSpec(
        "succ",
        ("succ", "successors"),
        {"--all": 0, "--include": 1},
        _build_graph_traversal("successors"),
    ),
    CommandSpec(
        "anc",
        ("anc", "ancestors"),
        {"--all": 0, "--include": 1},
        _build_graph_traversal("ancestors"),
    ),
    CommandSpec(
        "desc",
        ("desc", "descendants"),
        {"--all": 0, "--include": 1},
        _build_graph_traversal("descendants"),
    ),
    CommandSpec(
        "nbr",
        ("nbr", "neighborhood"),
        {"--all": 0, "--include": 1, "--depth": 1},
        _build_graph_traversal("neighborhood"),
    ),
    CommandSpec(
        "meetinggraph",
        ("meetinggraph", "meeting", "meeting_subgraph"),
        {"--all": 0, "--include": 1, "--min": 0},
        _build_meetinggraph,
    ),
    CommandSpec("pagerank", ("pagerank",), {"--all": 0, "--include": 1}, _build_rank("pagerank")),
    CommandSpec(
        "betweenness",
        ("betweenness",),
        {"--all": 0, "--include": 1},
        _build_rank("betweenness_centrality"),
    ),
    CommandSpec(
        "closeness",
        ("closeness",),
        {"--all": 0, "--include": 1},
        _build_rank("closeness_centrality"),
    ),
    CommandSpec("degree", ("degree",), {"--all": 0, "--include": 1}, _build_rank("degree_centrality")),
    CommandSpec(
        "indegree",
        ("indegree",),
        {"--all": 0, "--include": 1},
        _build_rank("in_degree_centrality"),
    ),
    CommandSpec(
        "outdegree",
        ("outdegree",),
        {"--all": 0, "--include": 1},
        _build_rank("out_degree_centrality"),
    ),
    CommandSpec("hits", ("hits",), {"--all": 0, "--include": 1}, _build_rank("hits")),
    CommandSpec("sort", ("sort",), {"--asc": 0}, _build_sort),
    CommandSpec("top", ("top",), {}, _build_top),
    CommandSpec("kinds", ("kinds",), {}, _build_kinds),
)

_COMMAND_REGISTRY = {alias: spec for spec in _COMMAND_SPECS for alias in spec.aliases}


def _build_command(name: str, args: list[str]) -> StageNode:
    spec = _COMMAND_REGISTRY.get(name)
    if spec is None:
        raise QuerySyntaxError(f"Unknown command: {name}")
    positionals, options = _split_flags(args, spec.flags, spec.repeatable)
    return spec.builder(positionals, options)


def _is_flag(token: str, spec: dict[str, int]) -> bool:
    """Return True if *token* should be treated as a flag.

    Long flags (``--foo``) are always flag-shaped — an unknown ``--``
    token is an error.  Short flags (``-t``) are only recognized when
    they match the spec; a stray ``-`` or ``-1`` passes through as a
    positional so negative numbers and literal dashes still work.
    """
    if token.startswith("--"):
        return True
    return token.startswith("-") and len(token) > 1 and token in spec


def _split_flags(
    args: list[str],
    spec: dict[str, int],
    repeatable: frozenset[str],
) -> tuple[list[str], dict[str, FlagValue]]:
    positionals: list[str] = []
    options: dict[str, FlagValue] = {}
    index = 0
    while index < len(args):
        current = args[index]
        if _is_flag(current, spec):
            if current not in spec:
                raise QuerySyntaxError(f"Unknown flag: {current}")
            arity = spec[current]
            is_repeatable = current in repeatable
            if current in options and not is_repeatable:
                raise QuerySyntaxError(f"Duplicate flag: {current}")
            if arity == 0:
                options[current] = True
                index += 1
                continue
            if index + 1 >= len(args):
                raise QuerySyntaxError(f"Flag {current} requires a value")
            value = args[index + 1]
            if _is_flag(value, spec):
                raise QuerySyntaxError(f"Flag {current} requires a value")
            if is_repeatable:
                existing = cast("tuple[str, ...]", options.get(current, ()))
                options[current] = (*existing, value)
            else:
                options[current] = value
            index += 2
            continue
        positionals.append(current)
        index += 1
    return positionals, options


def _parse_visibility(options: dict[str, FlagValue]) -> Visibility:
    if "--all" in options and "--include" in options:
        raise QuerySyntaxError("Cannot combine --all and --include")
    include_all = "--all" in options
    include_kinds: tuple[ObjectKind, ...] = ()
    if "--include" in options:
        raw = str(options["--include"])
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            raise QuerySyntaxError("--include requires at least one kind")
        include_kinds = tuple(_parse_kind_name(part) for part in parts)
    return Visibility(include_all=include_all, include_kinds=include_kinds)


def _parse_overwrite(options: dict[str, FlagValue]) -> bool:
    if "--overwrite" in options and "--no-overwrite" in options:
        raise QuerySyntaxError("Cannot combine --overwrite and --no-overwrite")
    return "--no-overwrite" not in options


# ---------------------------------------------------------------------------
# ripgrep-compatible grep/glob option helpers
# ---------------------------------------------------------------------------


def _flag_set(options: dict[str, FlagValue], *aliases: str) -> bool:
    """Return True if any of the flag aliases is present and truthy."""
    return any(alias in options for alias in aliases)


def _collect_values(options: dict[str, FlagValue], *aliases: str) -> tuple[str, ...]:
    """Collect repeatable flag values across all aliases in order."""
    result: list[str] = []
    for alias in aliases:
        value = options.get(alias)
        if value is None or value is False or value is True:
            continue
        if isinstance(value, tuple):
            result.extend(value)
        else:
            result.append(str(value))
    return tuple(result)


def _parse_type_option(options: dict[str, FlagValue]) -> tuple[str, ...]:
    raw = _collect_values(options, "--type", "-t")
    return resolve_type_aliases(raw)


def _parse_type_not_option(options: dict[str, FlagValue]) -> tuple[str, ...]:
    raw = _collect_values(options, "--type-not", "-T")
    return resolve_type_aliases(raw)


def _parse_glob_option(options: dict[str, FlagValue], *, negated: bool) -> tuple[str, ...]:
    raw = _collect_values(options, "--glob", "-g")
    result: list[str] = []
    for pattern in raw:
        is_negated = pattern.startswith("!")
        stripped = pattern[1:] if is_negated else pattern
        if not stripped:
            raise QuerySyntaxError("--glob pattern cannot be empty")
        if is_negated == negated:
            result.append(stripped)
    return tuple(result)


def _parse_case_mode(options: dict[str, FlagValue]) -> CaseMode:
    insensitive = _flag_set(options, "--ignore-case", "-i")
    sensitive = _flag_set(options, "--case-sensitive", "-s")
    smart = _flag_set(options, "--smart-case", "-S")
    if int(insensitive) + int(sensitive) + int(smart) > 1:
        raise QuerySyntaxError(
            "grep cannot combine case flags — pick at most one of -i/-s/-S",
        )
    if insensitive:
        return "insensitive"
    if smart:
        return "smart"
    return "sensitive"


def _parse_grep_output_mode(options: dict[str, FlagValue]) -> GrepOutputMode:
    files = _flag_set(options, "--files-with-matches", "-l") or _flag_set(options, "--files")
    count = _flag_set(options, "--count", "-c")
    if files and count:
        raise QuerySyntaxError("grep output flags are mutually exclusive: pick at most one of -l/-c")
    if files:
        return "files"
    if count:
        return "count"
    return "lines"


def _parse_context_option(options: dict[str, FlagValue], *aliases: str) -> int:
    """Parse a context-window flag (-A/-B) with fallback to -C/--context.

    rg semantics: ``-C N`` sets both ``-A`` and ``-B`` unless overridden.
    """
    for alias in aliases:
        if alias in options:
            return _parse_int(str(options[alias]), alias)
    if "--context" in options:
        return _parse_int(str(options["--context"]), "--context")
    if "-C" in options:
        return _parse_int(str(options["-C"]), "-C")
    return 0


def _parse_int_aliased(options: dict[str, FlagValue], *aliases: str) -> int | None:
    for alias in aliases:
        if alias in options:
            return _parse_int(str(options[alias]), alias)
    return None


@overload
def _parse_int_option(
    options: dict[str, FlagValue],
    flag: str,
    *,
    default: int,
) -> int: ...


@overload
def _parse_int_option(
    options: dict[str, FlagValue],
    flag: str,
    *,
    default: None = None,
) -> int | None: ...


def _parse_int_option(
    options: dict[str, FlagValue],
    flag: str,
    *,
    default: int | None = None,
) -> int | None:
    if flag not in options:
        return default
    return _parse_int(str(options[flag]), flag)


def _parse_int(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise QuerySyntaxError(f"{label} requires an integer, got {value!r}") from exc


def _parse_vector(values: list[str]) -> tuple[float, ...]:
    if len(values) == 1:
        value = values[0].strip()
        if value.startswith("[") and value.endswith("]"):
            value = value[1:-1]
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if parts:
            values = parts
    vector: list[float] = []
    for value in values:
        try:
            vector.append(float(value))
        except ValueError as exc:
            raise QuerySyntaxError(f"vsearch requires numeric values, got {value!r}") from exc
    if not vector:
        raise QuerySyntaxError("vsearch requires at least one numeric value")
    return tuple(vector)


def _parse_kind_name(name: str) -> ObjectKind:
    canonical = name.lower()
    match canonical:
        case "file" | "files":
            return "file"
        case "directory" | "directories" | "dir" | "dirs":
            return "directory"
        case "chunk" | "chunks":
            return "chunk"
        case "version" | "versions":
            return "version"
        case "edge" | "edges":
            return "edge"
        case "api" | "apis":
            return "api"
        case _:
            raise QuerySyntaxError(f"Unknown kind: {name}")


def _planned_methods(node: QueryNode) -> tuple[str, ...]:
    match node:
        case PipelineNode(source=source, stages=stages):
            methods = list(_planned_methods(source))
            for stage in stages:
                methods.extend(_planned_methods(stage))
            return tuple(methods)
        case UnionNode(operands=operands):
            methods: list[str] = []
            for operand in operands:
                methods.extend(_planned_methods(operand))
            return tuple(methods)
        case ReadCommand():
            return ("read",)
        case StatCommand():
            return ("stat",)
        case LsCommand():
            return ("ls",)
        case TreeCommand():
            return ("tree",)
        case DeleteCommand():
            return ("delete",)
        case EditCommand():
            return ("edit",)
        case WriteCommand():
            return ("write",)
        case MkdirCommand():
            return ("mkdir",)
        case MoveCommand():
            return ("move",)
        case CopyCommand():
            return ("copy",)
        case MkedgeCommand():
            return ("mkedge",)
        case GlobCommand():
            return ("glob",)
        case GrepCommand():
            return ("grep",)
        case SemanticSearchCommand():
            return ("semantic_search",)
        case LexicalSearchCommand():
            return ("lexical_search",)
        case VectorSearchCommand():
            return ("vector_search",)
        case GraphTraversalCommand(method_name=method_name):
            return (method_name,)
        case MeetingGraphCommand(minimal=True):
            return ("min_meeting_subgraph",)
        case MeetingGraphCommand():
            return ("meeting_subgraph",)
        case RankCommand(method_name=method_name):
            return (method_name,)
        case SortCommand():
            return ("sort",)
        case TopCommand():
            return ("top",)
        case KindsCommand():
            return ("kinds",)
        case IntersectStage(query=query) | ExceptStage(query=query):
            return _planned_methods(query)
        case _:  # pragma: no cover
            raise ValueError(f"Unknown node type: {node}")
