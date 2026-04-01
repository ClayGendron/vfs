"""AST nodes for the CLI query language."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from grover.paths import ObjectKind

RenderMode = Literal["action", "content", "ls", "query_list", "stat", "tree"]


@dataclass(frozen=True)
class Visibility:
    """Visibility overrides for metadata-bearing queries."""

    include_all: bool = False
    include_kinds: tuple[ObjectKind, ...] = ()


class QueryNode:
    """Base type for query AST nodes."""


class StageNode(QueryNode):
    """Base type for executable pipeline stages."""


@dataclass(frozen=True)
class PipelineNode(QueryNode):
    source: QueryNode
    stages: tuple[StageNode, ...]


@dataclass(frozen=True)
class UnionNode(QueryNode):
    operands: tuple[QueryNode, ...]


@dataclass(frozen=True)
class ReadCommand(StageNode):
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatCommand(StageNode):
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class LsCommand(StageNode):
    paths: tuple[str, ...] = ()
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class TreeCommand(StageNode):
    paths: tuple[str, ...] = ()
    max_depth: int | None = None
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class DeleteCommand(StageNode):
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class EditCommand(StageNode):
    old: str
    new: str
    paths: tuple[str, ...] = ()
    replace_all: bool = False


@dataclass(frozen=True)
class WriteCommand(StageNode):
    path: str
    content: str
    overwrite: bool = True


@dataclass(frozen=True)
class MkdirCommand(StageNode):
    paths: tuple[str, ...]


@dataclass(frozen=True)
class MoveCommand(StageNode):
    dest: str
    src: str | None = None
    overwrite: bool = True


@dataclass(frozen=True)
class CopyCommand(StageNode):
    dest: str
    src: str | None = None
    overwrite: bool = True


@dataclass(frozen=True)
class MkconnCommand(StageNode):
    connection_type: str
    target: str
    source: str | None = None


@dataclass(frozen=True)
class GlobCommand(StageNode):
    pattern: str
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class GrepCommand(StageNode):
    pattern: str
    case_sensitive: bool = True
    max_results: int | None = None
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class SemanticSearchCommand(StageNode):
    query: str
    k: int = 15
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class LexicalSearchCommand(StageNode):
    query: str
    k: int = 15
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class VectorSearchCommand(StageNode):
    vector: tuple[float, ...]
    k: int = 15
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class GraphTraversalCommand(StageNode):
    method_name: Literal["predecessors", "successors", "ancestors", "descendants", "neighborhood"]
    paths: tuple[str, ...] = ()
    depth: int = 2
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class MeetingGraphCommand(StageNode):
    paths: tuple[str, ...] = ()
    minimal: bool = False
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class RankCommand(StageNode):
    method_name: Literal[
        "pagerank",
        "betweenness_centrality",
        "closeness_centrality",
        "degree_centrality",
        "in_degree_centrality",
        "out_degree_centrality",
        "hits",
    ]
    paths: tuple[str, ...] = ()
    visibility: Visibility = Visibility()


@dataclass(frozen=True)
class SortCommand(StageNode):
    operation: str | None = None
    reverse: bool = True


@dataclass(frozen=True)
class TopCommand(StageNode):
    k: int


@dataclass(frozen=True)
class KindsCommand(StageNode):
    kinds: tuple[ObjectKind, ...]


@dataclass(frozen=True)
class IntersectStage(StageNode):
    query: QueryNode


@dataclass(frozen=True)
class ExceptStage(StageNode):
    query: QueryNode


@dataclass(frozen=True)
class QueryPlan:
    """Parsed query plus the ordered method calls it lowers to."""

    ast: QueryNode
    methods: tuple[str, ...]
    render_mode: RenderMode
