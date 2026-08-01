"""Per-op parameter table — the router's ingress contract, declared once.

One :class:`ParamSpec` row per public-verb parameter and one
:class:`ShapeRule` set per op. Three consumers read the table: the router's
ingress gate (``VirtualFileSystem._gate_params``), the signature drift test,
and the wire dialect's schema projection. The module is a leaf — stdlib plus
``vfs.ops`` only — so schema consumers never import the router.

    param_violation("tree", {"max_depth": "2"})
    # → "tree max_depth must be an integer >= 1, got '2'"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple, get_args

from vfs.ops import GRAPH_METHODS, CaseMode, GrepOutputMode

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from vfs.ops import Op

# ---------------------------------------------------------------------------
# Module constants and shared types
# ---------------------------------------------------------------------------

ParamKind = Literal[
    "path",  # gated downstream by resolve_path — presence checked here only
    "str",
    "int",
    "bool",
    "dict",
    "str_seq",  # tuple or list of str; str/bytes/iterables rejected
    "str_set",  # frozenset/set/tuple/list of str
    "observations",  # model kinds: declared for drift/schema, validated
    "entries",  # downstream where their classes live
    "edits",
    "pairs",
]

_MODEL_KINDS: Final[frozenset[str]] = frozenset({"observations", "entries", "edits", "pairs"})

CASE_MODES: Final[frozenset[str]] = frozenset(get_args(CaseMode))
OUTPUT_MODES: Final[frozenset[str]] = frozenset(get_args(GrepOutputMode))


class ParamSpec(NamedTuple):
    """One parameter's ingress contract — type kind, domain, and schema facts.

    ``nullable`` mirrors the signature: ``None`` passes only where the
    annotation says ``| None`` — a JSON ``null`` against anything else
    classifies through the kind's own type message.
    """

    name: str
    kind: ParamKind
    required: bool = False
    nullable: bool = True
    minimum: int | None = None
    choices: frozenset[str] | None = None
    default: object = None
    doc: str = ""


class ShapeRule(NamedTuple):
    """Input-shape rule over two parameter groups.

    A group is *present* when any member is supplied (see ``_present``).
    ``exactly_one=True`` demands exactly one group, fully supplied;
    ``False`` only forbids both (neither is fine).
    """

    groups: tuple[tuple[str, ...], tuple[str, ...]]
    exactly_one: bool
    msg_both: str
    msg_missing: str = ""


_USER: Final = ParamSpec("user_id", "str", doc="local caller identity; never on the wire")
_COLUMNS: Final = ParamSpec("columns", "str_set", doc="observation fields to fetch and render")
_OBSERVATIONS: Final = ParamSpec("observations", "observations", doc="row-addressed targets")
_SCOPE_PATHS: Final = ParamSpec(
    "paths", "str_seq", nullable=False, default=(), doc="scope paths; empty means every entry"
)

PARAMS: Final[dict[Op, tuple[ParamSpec, ...]]] = {
    "read": (
        ParamSpec("path", "path", doc="the entry to read"),
        _OBSERVATIONS,
        _COLUMNS,
        _USER,
    ),
    "stat": (
        ParamSpec("path", "path", doc="the entry to stat"),
        _OBSERVATIONS,
        _COLUMNS,
        _USER,
    ),
    "ls": (
        ParamSpec("path", "path", doc="the directory to list"),
        _OBSERVATIONS,
        _COLUMNS,
        _USER,
    ),
    "tree": (
        ParamSpec("path", "path", required=True, doc="the region root"),
        ParamSpec("max_depth", "int", minimum=1, doc="depth budget; None is unbounded"),
        _COLUMNS,
        _USER,
    ),
    "write": (
        ParamSpec("entries", "entries", doc="batch form: entries route by their own paths"),
        ParamSpec("path", "path", doc="single form: the file to write"),
        ParamSpec("content", "str", doc="single form: the file's content"),
        ParamSpec("overwrite", "bool", nullable=False, default=True, doc="replace an existing file"),
        ParamSpec("parents", "bool", nullable=False, default=False, doc="mint missing ancestors, mkdir -p style"),
        _USER,
    ),
    "edit": (
        ParamSpec("path", "path", doc="the file to edit"),
        ParamSpec("old", "str", doc="sugar form: text to find"),
        ParamSpec("new", "str", doc="sugar form: replacement text"),
        ParamSpec("edits", "edits", doc="native form: sequential, atomic EditOperation list"),
        _OBSERVATIONS,
        ParamSpec("replace_all", "bool", nullable=False, default=False, doc="replace every match of old"),
        _USER,
    ),
    "delete": (
        ParamSpec("path", "path", doc="the entry to delete"),
        _OBSERVATIONS,
        ParamSpec("cascade", "bool", nullable=False, default=True, doc="delete the subtree beneath a directory"),
        _USER,
    ),
    "restore": (
        ParamSpec("path", "path", doc="the original path — or the exact trash-side path — of the row to restore"),
        _OBSERVATIONS,
        ParamSpec("overwrite", "bool", nullable=False, default=False, doc="replace an occupant at the original site"),
        _USER,
    ),
    "sweep": (
        ParamSpec(
            "path",
            "path",
            nullable=False,
            default="/.vfs/trash",
            doc="a trash-root address runs retention over expired buckets; any other address purges wholesale",
        ),
        _USER,
    ),
    "mkdir": (
        ParamSpec("path", "path", required=True, doc="the directory to create"),
        ParamSpec("parents", "bool", nullable=False, default=False, doc="mint missing ancestors"),
        ParamSpec("exist_ok", "bool", nullable=False, default=False, doc="forgive an existing directory"),
        _USER,
    ),
    "mkedge": (
        ParamSpec("source", "path", required=True, doc="edge tail endpoint"),
        ParamSpec("target", "path", required=True, doc="edge head endpoint"),
        ParamSpec("edge_type", "str", required=True, doc="edge label, one path segment"),
        _USER,
    ),
    "move": (
        ParamSpec("src", "path", doc="single form: source path"),
        ParamSpec("dest", "path", doc="single form: destination path"),
        ParamSpec("moves", "pairs", doc="batch form: (src, dest) pairs"),
        ParamSpec("overwrite", "bool", nullable=False, default=True, doc="replace an occupied destination file"),
        _USER,
    ),
    "copy": (
        ParamSpec("src", "path", doc="single form: source path"),
        ParamSpec("dest", "path", doc="single form: destination path"),
        ParamSpec("copies", "pairs", doc="batch form: (src, dest) pairs"),
        ParamSpec("overwrite", "bool", nullable=False, default=True, doc="replace an occupied destination file"),
        _USER,
    ),
    "glob": (
        ParamSpec(
            "pattern", "str", required=True, doc="glob: * within a segment, ** across; a / anchors at each scope root"
        ),
        _SCOPE_PATHS,
        _OBSERVATIONS,
        ParamSpec("ext", "str_seq", nullable=False, default=(), doc="keep only these extensions"),
        ParamSpec("max_count", "int", minimum=1, doc="bound per entry and on the merged result"),
        _COLUMNS,
        _USER,
    ),
    "grep": (
        ParamSpec("pattern", "str", required=True, doc="regex (or literal with fixed_strings)"),
        _SCOPE_PATHS,
        _OBSERVATIONS,
        ParamSpec("ext", "str_seq", nullable=False, default=(), doc="keep only these extensions"),
        ParamSpec("ext_not", "str_seq", nullable=False, default=(), doc="drop these extensions"),
        ParamSpec("globs", "str_seq", nullable=False, default=(), doc="keep only paths matching these globs"),
        ParamSpec("globs_not", "str_seq", nullable=False, default=(), doc="drop paths matching these globs"),
        ParamSpec("case_mode", "str", nullable=False, choices=CASE_MODES, default="sensitive", doc="case sensitivity"),
        ParamSpec("fixed_strings", "bool", nullable=False, default=False, doc="treat pattern as a literal"),
        ParamSpec("word_regexp", "bool", nullable=False, default=False, doc="match whole words only"),
        ParamSpec("invert_match", "bool", nullable=False, default=False, doc="report non-matching lines"),
        ParamSpec("before_context", "int", nullable=False, minimum=0, default=0, doc="context lines before a match"),
        ParamSpec("after_context", "int", nullable=False, minimum=0, default=0, doc="context lines after a match"),
        ParamSpec("output_mode", "str", nullable=False, choices=OUTPUT_MODES, default="lines", doc="row shape"),
        ParamSpec("max_count", "int", minimum=1, doc="matches per file, ripgrep's -m"),
        ParamSpec("allow_scan", "bool", nullable=False, default=False, doc="opt into an unindexed scan tier"),
        _COLUMNS,
        _USER,
    ),
    "glean": (
        ParamSpec("query", "str", required=True, doc="ranked-search text"),
        ParamSpec(
            "limit", "int", nullable=False, minimum=1, default=10, doc="bound per entry and on the merged result"
        ),
        _SCOPE_PATHS,
        _OBSERVATIONS,
        _COLUMNS,
        _USER,
    ),
    "graph": (
        ParamSpec("method", "str", required=True, choices=GRAPH_METHODS, doc="traversal to run"),
        ParamSpec("path", "path", doc="the node to start from"),
        _OBSERVATIONS,
        ParamSpec("depth", "int", minimum=1, doc="traversal depth budget"),
        _USER,
    ),
    "run": (
        ParamSpec("path", "path", required=True, doc="the tool to execute"),
        ParamSpec("arguments", "dict", doc="tool arguments; the tool's own schema governs values"),
        _USER,
    ),
}

_ONE_TARGET: Final = ShapeRule(
    (("path",), ("observations",)),
    exactly_one=True,
    msg_both="Exactly one of path or observations must be provided",
    msg_missing="Exactly one of path or observations must be provided",
)

RULES: Final[dict[Op, tuple[ShapeRule, ...]]] = {
    "read": (_ONE_TARGET,),
    "stat": (_ONE_TARGET,),
    "ls": (_ONE_TARGET,),
    "delete": (_ONE_TARGET,),
    "restore": (_ONE_TARGET,),
    "graph": (_ONE_TARGET,),
    "edit": (
        _ONE_TARGET,
        ShapeRule(
            (("edits",), ("old", "new")),
            exactly_one=True,
            msg_both="edit takes old/new or an edits list, not both",
            msg_missing="edit requires old and new strings, or an edits list",
        ),
    ),
    "write": (
        ShapeRule(
            (("entries",), ("path", "content")),
            exactly_one=True,
            msg_both="write takes entries or path/content, not both",
            msg_missing="write requires entries or path and content",
        ),
    ),
    "move": (
        ShapeRule(
            (("moves",), ("src", "dest")),
            exactly_one=True,
            msg_both="move takes src/dest or a batch list, not both",
            msg_missing="move requires src and dest, or a batch list",
        ),
    ),
    "copy": (
        ShapeRule(
            (("copies",), ("src", "dest")),
            exactly_one=True,
            msg_both="copy takes src/dest or a batch list, not both",
            msg_missing="copy requires src and dest, or a batch list",
        ),
    ),
    "glob": (
        ShapeRule(
            (("paths",), ("observations",)),
            exactly_one=False,
            msg_both="glob takes paths or observations, not both",
        ),
    ),
    "grep": (
        ShapeRule(
            (("paths",), ("observations",)),
            exactly_one=False,
            msg_both="grep takes paths or observations, not both",
        ),
    ),
    "glean": (
        ShapeRule(
            (("paths",), ("observations",)),
            exactly_one=False,
            msg_both="glean takes paths or observations, not both",
        ),
    ),
}


# ---------------------------------------------------------------------------
# The check — types first, then input shape
# ---------------------------------------------------------------------------


def param_violation(op: Op, params: Mapping[str, object]) -> str | None:
    """First ingress violation for *op* against the supplied *params*.

    ``None`` means every supplied value is well-typed, in-domain, and the
    op's input shape holds. Types are checked before shape rules so garbage
    containers report as type errors and presence tests run on typed
    values. Pure and total — the router mints the classified refusal.
    """
    specs = PARAMS[op]
    for spec in specs:
        if spec.name not in params:
            continue
        problem = _check_value(op, spec, params[spec.name])
        if problem is not None:
            return problem
    by_name = {spec.name: spec for spec in specs}
    for rule in RULES.get(op, ()):
        problem = _check_shape(rule, by_name, params)
        if problem is not None:
            return problem
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_value(op: Op, spec: ParamSpec, value: object) -> str | None:
    """Type and domain check for one supplied value.

    A ``None`` against a non-nullable spec falls through to the kind
    check, which names the expected type (``got NoneType``).
    """
    if value is None:
        if spec.required:
            return f"{op} {spec.name} is required"
        if spec.nullable:
            return None
    kind = spec.kind
    if kind == "path" or kind in _MODEL_KINDS:
        return None
    if kind == "str":
        if not isinstance(value, str):
            return f"{op} {spec.name} must be a string, got {type(value).__name__}"
        if spec.choices is not None and value not in spec.choices:
            return f"{op} {spec.name} must be one of {sorted(spec.choices)}, got {value!r}"
        return None
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int) or (spec.minimum is not None and value < spec.minimum):
            bound = "" if spec.minimum is None else f" >= {spec.minimum}"
            return f"{op} {spec.name} must be an integer{bound}, got {value!r}"
        return None
    if kind == "bool":
        if not isinstance(value, bool):
            return f"{op} {spec.name} must be a boolean, got {type(value).__name__}"
        return None
    if kind == "dict":
        if not isinstance(value, dict):
            return f"{op} {spec.name} must be a dict, got {type(value).__name__}"
        return None
    if kind == "str_seq":
        if not isinstance(value, (tuple, list)):
            return f"{op} {spec.name} must be a tuple of strings, got {type(value).__name__}"
        return _check_items(op, spec, value)
    if not isinstance(value, (frozenset, set, tuple, list)):  # str_set
        return f"{op} {spec.name} must be a set of strings, got {type(value).__name__}"
    return _check_items(op, spec, value)


def _check_items(op: Op, spec: ParamSpec, value: Iterable[object]) -> str | None:
    for item in value:
        if not isinstance(item, str):
            return f"{op} {spec.name} items must be strings, got {type(item).__name__}"
    return None


def _check_shape(
    rule: ShapeRule,
    by_name: Mapping[str, ParamSpec],
    params: Mapping[str, object],
) -> str | None:
    """Evaluate one shape rule; values are already type-checked."""
    first, second = rule.groups
    first_present = any(_present(by_name[name], params) for name in first)
    second_present = any(_present(by_name[name], params) for name in second)
    if first_present and second_present:
        return rule.msg_both
    if not rule.exactly_one:
        return None
    if not first_present and not second_present:
        return rule.msg_missing
    chosen = first if first_present else second
    if not all(_present(by_name[name], params) for name in chosen):
        return rule.msg_missing
    return None


def _present(spec: ParamSpec, params: Mapping[str, object]) -> bool:
    """Whether a parameter was meaningfully supplied.

    ``None`` is absent everywhere; an empty scope sequence is absent too —
    fan-out's ``paths=()`` default means "every entry," not a scope.
    """
    value = params.get(spec.name)
    if value is None:
        return False
    if spec.kind == "str_seq" and isinstance(value, (tuple, list)):
        return len(value) > 0
    return True
