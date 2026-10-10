"""Error vocabulary and contract tables — what went wrong, on the wire.

The kind vocabulary (:class:`ErrorKind`), the severity trust tiers
(:class:`Severity`), and the normative per-kind contract table
(:data:`KIND_CONTRACTS` — phrase, retry class, agent hint, ``path``
referent) live here so both the envelope (``vfs.results``) and the
renderer (``vfs.results.render``) can consume them without a cycle. The
table owns every word a ``vfs.*`` error carries: the envelope composes
``message`` from the phrase, the renderer appends the hint and retry
directive, and no producer writes prose. :func:`kind_family` is the
normative dispatch rule for the hierarchical vocabulary.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Kind vocabulary
# ---------------------------------------------------------------------------


class ErrorKind(StrEnum):
    """Typed vocabulary for what went wrong — stable on the wire.

    Values are dotted, namespaced strings mapping onto POSIX errno /
    Plan 9 / JSON-RPC families. The vocabulary is **hierarchical**:
    consumers dispatch by longest known dotted prefix (:func:`kind_family`),
    so an unknown child kind from a newer peer (``vfs.unavailable.dns``)
    degrades to its known parent (``vfs.unavailable``) before falling to
    base handling. A kind with no known prefix is preserved as its raw
    string by ``ResultError`` (see ``vfs.results``) and handled at the
    broadest tier — the boundary adapter raises it as base ``VFSError``,
    never a narrower class that would misstate an unknown failure.

    **Namespace partition** (pinned before any independent peer ships):
    ``vfs.*`` is reserved for this core vocabulary; backend- or
    mount-minted kinds must use ``x.<vendor>.*``. Shipped values are never
    renamed or reused — a retired value becomes a permanent inbound alias
    in ``_KIND_ALIASES`` (``vfs.backend_unavailable`` is the first).

    **Producer exclusivity:** only capability gates emit ``unsupported``;
    only dispatch emits ``unrecognized``.

    **Per-kind ``data`` records** (absence means "not known", never a
    default): ``busy`` / ``unavailable.*`` / ``timeout`` may carry
    ``retry_after_ms``; ``conflict`` may carry ``version`` (the current
    version to retry with). Envelope machinery writes only
    ``vfs.``-prefixed keys into ``data`` (``vfs.overflow``, ``vfs.rollup``,
    ``vfs.quarantine``, ``vfs.claim``); producer keys are unprefixed.

    Each kind's retry class, agent-facing hint, and ``path`` referent live
    in :data:`KIND_CONTRACTS` — a normative contract table, not wire data.
    """

    # namespace / object existence
    not_found = "vfs.not_found"  # ENOENT: the entry, or an ancestor on its path, does not exist
    exists = "vfs.exists"  # EEXIST: the site is occupied and this verb never replaces an occupant
    wrong_kind = "vfs.wrong_kind"  # ENOTDIR / EISDIR: the entry exists but its kind rejects the verb
    not_empty = "vfs.not_empty"  # ENOTEMPTY: the directory has live children and the verb does not cascade

    # authorization
    unauthenticated = "vfs.unauthenticated"  # 401: the target's posture needs a named authority; who are you
    permission_denied = "vfs.permission_denied"  # EACCES / EPERM / 403: the caller is known and may not
    read_only = "vfs.read_only"  # EROFS: the mount or prefix is read-only, whoever the caller is

    # capability / method discovery
    unsupported = "vfs.unsupported"  # ENOSYS / ENOTSUP: the storage does not declare the verb
    unrecognized = "vfs.unrecognized"  # JSON-RPC METHOD_NOT_FOUND: the verb name is not in the vocabulary

    # request validity
    invalid = "vfs.invalid"  # EINVAL / ENAMETOOLONG: the caller's input is wrong and the caller can fix it
    unindexable_pattern = "vfs.invalid.unindexable_pattern"  # EINVAL: no gram predicate; the scan tier overrides
    unaddressable = "vfs.unaddressable"  # ENAMETOOLONG: a real row exceeds MAX_PATH_LENGTH through this mount

    # concurrency / preconditions
    conflict = "vfs.conflict"  # ESTALE: the precondition is stale; re-read and retry with the current version
    busy = "vfs.busy"  # EBUSY: a live bind site the data plane may not mutate; unmount first
    cross_mount = "vfs.cross_mount"  # EXDEV: the verb's endpoints resolve to different mounts
    budget_exhausted = "vfs.budget_exhausted"  # ELOOP: the hop or TTL budget is spent; not retryable
    truncated = "vfs.budget_exhausted.truncated"  # ELOOP: a runtime budget cut the result; refine, do not retry
    authority_budget = "vfs.budget_exhausted.authority"  # ELOOP: an oversize subject set or group nesting

    # runtime liveness
    unavailable = "vfs.unavailable"  # EIO / ECONNREFUSED / ENOSPC: a resource failed; retry shortly
    backend_unavailable = "vfs.unavailable.backend"  # ENOTCONN / ESHUTDOWN: the mount's transport is down
    schema_mismatch = "vfs.unavailable.schema"  # EIO: the database was provisioned by an incompatible schema
    timeout = "vfs.timeout"  # ETIMEDOUT: the deadline passed before the work finished
    cancelled = "vfs.cancelled"  # ECANCELED / EINTR: the work was cancelled or interrupted
    internal = "vfs.internal"  # JSON-RPC INTERNAL_ERROR: vfs itself broke; report it


# Permanent inbound tombstones: shipped kind strings that were re-parented.
# Never delete an entry; never reuse a retired string for a new meaning.
_KIND_ALIASES: dict[str, str] = {
    "vfs.backend_unavailable": "vfs.unavailable.backend",
}

_KIND_VALUES = frozenset(kind.value for kind in ErrorKind)


class Severity(StrEnum):
    """Trust contract per tier, carried on every ``ResultError``.

    - ``error``: something the caller asked for failed; fails the envelope.
    - ``warning``: loss or caveat on record — rows present are trustworthy
      and ``success`` is unaffected.
    - ``info``: advisory (capability skips, rollups); never a failure.

    An unknown or absent severity **reads as error** — the unknown is never
    silently downgraded (``is_fatal`` treats it as fatal).
    """

    error = "error"
    warning = "warning"
    info = "info"


class RetryClass(StrEnum):
    """What a retry of the same request can achieve — derived, never wired.

    ``never``: no retry of this request can succeed as-is. ``transient``:
    retry after a delay may succeed (honor ``retry_after_ms`` when
    present). ``refresh``: re-read state first, then retry with current
    preconditions (e.g. the ``version`` in ``data``).
    """

    never = "never"
    transient = "transient"
    refresh = "refresh"


class KindContract(NamedTuple):
    """Normative per-kind contract: the phrase, retry class, agent hint, ``path`` referent.

    ``phrase`` is the message every error of the kind carries — composed
    by the envelope's constructor, never written at a producer site. It
    names no locus: the renderer attaches ``path`` and the second entry
    after every rebase has run, so a phrase can never carry the wrong
    coordinates.
    """

    phrase: str
    retry_class: RetryClass
    hint: str
    path_means: str


# The contract table is normative and versioned with the vocabulary — it
# lives in code, not on the wire, so a wrong word is fixable everywhere.
KIND_CONTRACTS: dict[ErrorKind, KindContract] = {
    ErrorKind.not_found: KindContract(
        "Not found",
        RetryClass.never,
        "Check the path with ls or glob, or create the entry first.",
        "the entry that does not exist",
    ),
    ErrorKind.exists: KindContract(
        "Already exists",
        RetryClass.never,
        "Use a different path or remove the existing entry first.",
        "the entry that already exists",
    ),
    ErrorKind.wrong_kind: KindContract(
        "Wrong kind",
        RetryClass.never,
        "Check the entry's kind with stat and use a verb that applies to it.",
        "the entry whose kind rejects the verb",
    ),
    ErrorKind.not_empty: KindContract(
        "Directory not empty",
        RetryClass.never,
        "Empty the directory before removing it.",
        "the non-empty directory",
    ),
    ErrorKind.unauthenticated: KindContract(
        "Unauthenticated",
        RetryClass.never,
        "This mount's posture needs a name: open a session with an authority, or configure a default.",
        "None — source carries the locus",
    ),
    ErrorKind.permission_denied: KindContract(
        "Permission denied",
        RetryClass.never,
        "Target a path this caller may access, or request access.",
        "the entry access was denied to",
    ),
    ErrorKind.read_only: KindContract(
        "Read-only",
        RetryClass.never,
        "Target a writable mount; this one is read-only.",
        "the entry on the read-only mount",
    ),
    ErrorKind.unsupported: KindContract(
        "Unsupported",
        RetryClass.never,
        "This mount does not support the verb; target a mount that does.",
        "the entry's bind path (capability failures anchor to the mount)",
    ),
    ErrorKind.unrecognized: KindContract(
        "Unrecognized verb",
        RetryClass.never,
        "Check the verb name against this server's advertised tools.",
        "None — source carries the locus",
    ),
    ErrorKind.invalid: KindContract(
        "Invalid",
        RetryClass.never,
        "Fix the flagged parameter and retry.",
        "the entry the invalid input named, when one is implicated",
    ),
    ErrorKind.unindexable_pattern: KindContract(
        "Unindexable pattern",
        RetryClass.never,
        "Include a literal of 3+ characters in the pattern, or request the scan tier (`allow_scan`).",
        "None — source carries the locus",
    ),
    ErrorKind.unaddressable: KindContract(
        "Unaddressable",
        RetryClass.never,
        "Access the entry through a shallower mount; its global path exceeds the limit here.",
        "None — reconstruct the locus as source + data['vfs.overflow']['local_path']",
    ),
    ErrorKind.conflict: KindContract(
        "Conflict",
        RetryClass.refresh,
        "Re-read the entry and retry with its current version.",
        "the entry whose version is stale",
    ),
    ErrorKind.busy: KindContract(
        "Busy",
        RetryClass.transient,
        "Unmount the bind site first, then retry.",
        "the live bind site the data plane may not mutate",
    ),
    ErrorKind.cross_mount: KindContract(
        "Crosses a mount boundary",
        RetryClass.never,
        "Move within one mount, or copy then delete across mounts.",
        "the entry on the far side of the mount boundary",
    ),
    ErrorKind.budget_exhausted: KindContract(
        "Budget exhausted",
        RetryClass.never,
        "Raise the hop budget or shorten the mount chain; a retry will exhaust it again.",
        "None — source carries the locus",
    ),
    ErrorKind.truncated: KindContract(
        "Truncated",
        RetryClass.never,
        "Narrow the pattern, add filters, or scope the call; the result was cut at a runtime budget.",
        "None — source carries the locus",
    ),
    ErrorKind.authority_budget: KindContract(
        "Authority budget exceeded",
        RetryClass.never,
        "Act for fewer subjects at once, or flatten the group nesting; a retry will exceed the bound again.",
        "None — source carries the locus",
    ),
    ErrorKind.unavailable: KindContract(
        "Unavailable",
        RetryClass.transient,
        "Retry shortly; the resource is temporarily unavailable.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
    ErrorKind.backend_unavailable: KindContract(
        "Backend unavailable",
        RetryClass.transient,
        "Check the mount's backend connection, then retry.",
        "the entry's bind path — the mount whose transport is down",
    ),
    ErrorKind.schema_mismatch: KindContract(
        "Schema mismatch",
        RetryClass.never,
        "This mount's database was provisioned by an incompatible schema version; upgrade or re-provision it.",
        "None — source carries the mount",
    ),
    ErrorKind.timeout: KindContract(
        "Timed out",
        RetryClass.transient,
        "Retry with a longer deadline or a narrower scope.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
    ErrorKind.cancelled: KindContract(
        "Cancelled",
        RetryClass.transient,
        "Retry if the cancellation was not requested by this caller.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
    ErrorKind.internal: KindContract(
        "Internal error",
        RetryClass.never,
        "Report this failure; retrying the same request is unlikely to help.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def kind_family(kind: ErrorKind | str) -> ErrorKind | None:
    """Resolve *kind* to its longest known dotted prefix in the vocabulary.

    The normative dispatch rule for hierarchical kinds: aliases resolve
    first, an exact member returns itself, and an unknown child degrades
    segment by segment (``vfs.unavailable.dns`` → ``vfs.unavailable``).
    Returns ``None`` when no prefix is known — the consumer falls back to
    its broadest handling, assuming nothing.
    """
    value = _KIND_ALIASES.get(str(kind), str(kind))
    while True:
        if value in _KIND_VALUES:
            return ErrorKind(value)
        if "." not in value:
            return None
        value, _ = value.rsplit(".", 1)
