"""The operation vocabulary — every verb a filesystem can answer.

The single source of truth for op names and their dispatch classes. The
router (``vfs.base``), the permission gate (``vfs.permissions``), and the
projection table (``vfs.results.projection``) all import from here; none defines
its own copy. A verb's class decides how it is routed and gated:

    MUTATING_OPS    → write-permission check + mutation path resolution
    TWO_PATH_OPS    → source/target routing (may cross mounts → cross_mount)
    READ_OPS        → routed, no write gate
    EXEC_OPS        → routed, no write gate; executes rather than reads
    GRANT_OPS       → routed to the mount holding the path; the writing
                      ones are write-gated, and none touches a row

``cli`` is deliberately absent: it is a meta-verb that parses a command
string into these ops and re-enters through their public methods, so every
gate fires on the real verb. It is a front door, not an op.

The ``graph`` op routes and reports as one verb: traversal only —
``outbound`` follows each edge from its source to its target, ``inbound``
follows it back, ``neighborhood`` ignores the arrow, and ``meet`` returns
the subgraph that joins the seeds — with its own hierarchical rendering.
Centrality is an index-time background process, not a query-time verb.
The envelope's ``Result.ops`` speaks this same vocabulary; per-method
function names are retired.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple, get_args

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
    "rmedge",
    "move",
    "copy",
    "ls",
    "tree",
    "glob",
    "grep",
    "glean",
    "graph",
    "run",
    "grant",
    "revoke",
    "grants",
    "posture",
    "add_member",
    "remove_member",
]

MUTATING_OPS: Final[frozenset[Op]] = frozenset(
    {"write", "edit", "delete", "restore", "sweep", "mkdir", "mkedge", "rmedge", "move", "copy"},
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

GRANT_OPS: Final[frozenset[Op]] = frozenset({"grant", "revoke", "grants", "posture", "add_member", "remove_member"})
"""Ops over the grant and membership rows — who may see and write what."""

GRANT_WRITE_OPS: Final[frozenset[Op]] = GRANT_OPS - {"grants"}
"""The grant ops that change a row; ``grants`` only lists."""

WRITE_GATED_OPS: Final[frozenset[Op]] = MUTATING_OPS | GRANT_WRITE_OPS
"""Every op a read-only mount refuses: the mutations and the grant writes."""

DEVELOPER_OPS: Final[frozenset[Op]] = frozenset({"sweep", "posture", "add_member", "remove_member"})
"""Developer-plane ops: never registered on any agent-facing tool surface
(MCP serve, CLI) — Python-API only. Sweep destroys; agents only delete.
Posture and group membership shape a whole mount's policy, so they stay
with the operator too."""

ALL_OPS: Final[frozenset[Op]] = MUTATING_OPS | READ_OPS | EXEC_OPS | GRANT_OPS
"""Every routed op. The drift test pins the router's public surface to this."""

# ---------------------------------------------------------------------------
# The ladder — the rung each verb needs
# ---------------------------------------------------------------------------

Rung = Literal["none", "list", "read", "add", "contribute", "read_write"]
"""A rung of the permission ladder. Each rung includes every one below it:
``list`` names a row (path and kind), ``read`` reads it, ``add`` creates
beneath a prefix and alters only one's own rows, ``contribute`` also
overwrites and edits anyone's, ``read_write`` trashes, moves and grants."""

RUNGS: Final[tuple[Rung, ...]] = get_args(Rung)
"""The ladder in order, lowest first — the rank of a rung is its index here."""


class Needs(NamedTuple):
    """The rungs one verb needs: on its target, on a fresh name it mints, on a row it only passes or reads.

    ``primary`` judges an occupied target (the owner floor riding for a
    mutation); ``create`` judges a fresh name and an occupied name a
    creation lands on; ``traverse`` judges a row the verb reads without
    changing — a copy's source, an edge's target, a walk's node.
    """

    primary: Rung
    create: Rung | None = None
    traverse: Rung | None = None


VERB_RUNGS: Final[dict[Op, Needs]] = {
    "read": Needs("read"),
    "stat": Needs("list"),
    "ls": Needs("list"),
    "tree": Needs("list"),
    "glob": Needs("list"),
    "grep": Needs("read"),
    "glean": Needs("read"),
    "graph": Needs("read", traverse="list"),
    "write": Needs("contribute", create="add"),
    "edit": Needs("contribute"),
    "mkdir": Needs("contribute", create="add"),
    "delete": Needs("read_write"),
    "restore": Needs("read_write"),
    "move": Needs("read_write", create="add"),
    "copy": Needs("read_write", create="add", traverse="read"),
    "mkedge": Needs("contribute", traverse="list"),
    "rmedge": Needs("contribute", traverse="list"),
    "grant": Needs("read_write"),
    "revoke": Needs("read_write"),
    "posture": Needs("read_write"),
    "grants": Needs("read"),
    "run": Needs("read"),
    "sweep": Needs("read_write"),
    "add_member": Needs("read_write"),
    "remove_member": Needs("read_write"),
}
"""The one verb-to-rung table: every gate and view reads its rung here and carries no literal.

The listing verbs name rows at ``list`` and show each row's fields by
the rung the caller holds on it; ``grep`` and ``glean`` search only what
the caller reads; a walk passes nodes at ``list`` and returns contents
at ``read``. A mutation judges a fresh name at ``create`` and an
occupied row at ``primary`` or by the owner floor; a tombstoned row a
write lands on is judged as a restore. ``grants`` lists at ``read``; the
developer-plane verbs sit at ``read_write``; ``run`` waits for its own
axis.
"""

# Grep option vocabularies — shared by the router, the storage protocols,
# and the CLI grammar when it lands.
CaseMode = Literal["sensitive", "insensitive", "smart"]
GrepOutputMode = Literal["lines", "files", "count"]

# The graph walk's defaults, carried by the verb's signature and by the
# params table alike: the gate never substitutes a schema default.
GRAPH_DEPTH_DEFAULT: Final = 1
GRAPH_LIMIT_DEFAULT: Final = 128

GRAPH_METHODS: Final[frozenset[str]] = frozenset({"inbound", "outbound", "neighborhood", "meet"})
"""Graph traversal vocabulary — the only methods the ``graph`` verb accepts.

``outbound`` follows each edge from its ``source`` to its ``target`` (the
direction ``mkedge`` was given), ``inbound`` follows it from ``target``
back to ``source``, ``neighborhood`` follows both, and ``meet`` returns the
subgraph that joins the seeds.
"""
