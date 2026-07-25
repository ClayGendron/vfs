"""The operation vocabulary — every verb a filesystem can answer.

The single source of truth for op names and their dispatch classes. The
router (``vfs.base``), the permission gate (``vfs.permissions``), and the
projection table (``vfs.results.projection``) all import from here; none defines
its own copy. A verb's class decides how it is routed and gated:

    MUTATING_OPS    → write-permission check + mutation path resolution
    TWO_PATH_OPS    → source/target routing (may cross mounts → cross_mount)
    READ_OPS        → routed, no write gate
    EXEC_OPS        → routed, no write gate; executes rather than reads

``cli`` is deliberately absent: it is a meta-verb that parses a command
string into these ops and re-enters through their public methods, so every
gate fires on the real verb. It is a front door, not an op.

The ``graph`` op routes and reports as one verb: traversal only, with the
standard result projection — centrality is an index-time background
process, not a query-time verb. The envelope's ``Result.ops`` speaks this
same vocabulary; per-method function names are retired.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

# One name per verb, typed so an op string is checkable at the seams that
# construct dispatch calls (the router's public methods pass literals).
# Peer-supplied op names stay plain ``str`` — ``capabilities()`` may
# advertise ops this client does not know.
Op = Literal[
    "read",
    "write",
    "edit",
    "delete",
    "restore",
    "sweep",
    "stat",
    "mkdir",
    "mkedge",
    "move",
    "copy",
    "ls",
    "tree",
    "glob",
    "grep",
    "glean",
    "graph",
    "run",
]

MUTATING_OPS: Final[frozenset[Op]] = frozenset(
    {"write", "edit", "delete", "restore", "sweep", "mkdir", "mkedge", "move", "copy"},
)
"""Ops that mutate the backing store — write-gated at every chokepoint."""

TWO_PATH_OPS: Final[frozenset[Op]] = frozenset({"move", "copy"})
"""Mutations addressing a source and a target, routed as a pair."""


class TwoPathOperation(NamedTuple):
    """A source/destination pair for move or copy — the caller-facing input shape."""

    src: str
    dest: str


READ_OPS: Final[frozenset[Op]] = frozenset(
    {"read", "stat", "ls", "tree", "glob", "grep", "glean", "graph"},
)
"""Ops that only observe — they must keep working on read-only mounts."""

EXEC_OPS: Final[frozenset[Op]] = frozenset({"run"})
"""Ops that execute a capability — not a namespace mutation, not a read."""

DEVELOPER_OPS: Final[frozenset[Op]] = frozenset({"sweep"})
"""Developer-plane ops: never registered on any agent-facing tool surface
(MCP serve, CLI) — Python-API only. Sweep destroys; agents only delete."""

ALL_OPS: Final[frozenset[Op]] = MUTATING_OPS | READ_OPS | EXEC_OPS
"""Every routed op. The drift test pins the router's public surface to this."""

# Grep option vocabularies — shared by the router, the storage protocols,
# and the CLI grammar when it lands.
CaseMode = Literal["sensitive", "insensitive", "smart"]
GrepOutputMode = Literal["lines", "files", "count"]

GRAPH_METHODS: Final[frozenset[str]] = frozenset(
    {"predecessors", "successors", "ancestors", "descendants", "neighborhood"}
    | {"meeting_subgraph", "min_meeting_subgraph"},
)
"""Graph traversal vocabulary — the only methods the ``graph`` verb accepts."""
