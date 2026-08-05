"""Error vocabulary and contract tables — what went wrong, on the wire.

The kind vocabulary (:class:`VFSErrorKind`), the severity trust tiers
(:class:`Severity`), and the normative per-kind contract table
(:data:`KIND_CONTRACTS` — retry class, agent hint, ``path`` referent)
live here so both the envelope (``vfs.results``) and the renderer
(``vfs.results.render``) can consume them without a cycle: hints and retry
directives are contract, not wire data, and the renderer is where they
become text. :func:`kind_family` is the normative dispatch rule for the
hierarchical vocabulary.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Kind vocabulary
# ---------------------------------------------------------------------------


class VFSErrorKind(StrEnum):
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

    # — namespace / object existence —
    not_found = "vfs.not_found"  # ENOENT
    exists = "vfs.exists"  # EEXIST
    wrong_kind = "vfs.wrong_kind"  # ENOTDIR / EISDIR
    not_empty = "vfs.not_empty"  # ENOTEMPTY

    # — authorization —
    permission_denied = "vfs.permission_denied"  # EACCES / EPERM
    read_only = "vfs.read_only"  # EROFS — read-only target, distinct from authorization

    # — capability / method discovery —
    unsupported = "vfs.unsupported"  # ENOSYS / ENOTSUP
    unrecognized = "vfs.unrecognized"  # JSON-RPC METHOD_NOT_FOUND

    # — request validity —
    invalid = "vfs.invalid"  # EINVAL / ENAMETOOLONG — caller-fixable, only
    unindexable_pattern = "vfs.invalid.unindexable_pattern"  # no gram predicate; allow_scan overrides
    unaddressable = "vfs.unaddressable"  # a real row exceeds MAX_PATH_LENGTH through this mount

    # — concurrency / preconditions —
    conflict = "vfs.conflict"  # ESTALE
    busy = "vfs.busy"  # EBUSY — a live bind site the data plane may not mutate
    cross_mount = "vfs.cross_mount"  # EXDEV
    budget_exhausted = "vfs.budget_exhausted"  # ELOOP — hop/TTL budget spent; not retryable
    truncated = "vfs.budget_exhausted.truncated"  # a runtime budget cut the result; refine, don't retry

    # — runtime liveness —
    unavailable = "vfs.unavailable"  # EIO / ECONNREFUSED / ENOSPC
    backend_unavailable = "vfs.unavailable.backend"  # ENOTCONN / ESHUTDOWN — mount's transport is down
    schema_mismatch = "vfs.unavailable.schema"  # database provisioned by an incompatible schema version
    timeout = "vfs.timeout"  # ETIMEDOUT
    cancelled = "vfs.cancelled"  # ECANCELED / EINTR
    internal = "vfs.internal"  # JSON-RPC INTERNAL_ERROR — the VFS itself broke


# Permanent inbound tombstones: shipped kind strings that were re-parented.
# Never delete an entry; never reuse a retired string for a new meaning.
_KIND_ALIASES: dict[str, str] = {
    "vfs.backend_unavailable": "vfs.unavailable.backend",
}

_KIND_VALUES = frozenset(kind.value for kind in VFSErrorKind)


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
    """Normative per-kind contract: retry class, agent hint, ``path`` referent."""

    retry_class: RetryClass
    hint: str
    path_means: str


# The contract table is normative and versioned with the vocabulary — it
# lives in code, not on the wire, so a wrong hint is fixable everywhere.
KIND_CONTRACTS: dict[VFSErrorKind, KindContract] = {
    VFSErrorKind.not_found: KindContract(
        RetryClass.never,
        "Check the path with ls or glob, or create the entry first.",
        "the entry that does not exist",
    ),
    VFSErrorKind.exists: KindContract(
        RetryClass.never,
        "Use a different path or remove the existing entry first.",
        "the entry that already exists",
    ),
    VFSErrorKind.wrong_kind: KindContract(
        RetryClass.never,
        "Check the entry's kind with stat and use a verb that applies to it.",
        "the entry whose kind rejects the verb",
    ),
    VFSErrorKind.not_empty: KindContract(
        RetryClass.never,
        "Empty the directory before removing it.",
        "the non-empty directory",
    ),
    VFSErrorKind.permission_denied: KindContract(
        RetryClass.never,
        "Target a path this caller may access, or request access.",
        "the entry access was denied to",
    ),
    VFSErrorKind.read_only: KindContract(
        RetryClass.never,
        "Target a writable mount; this one is read-only.",
        "the entry on the read-only mount",
    ),
    VFSErrorKind.unsupported: KindContract(
        RetryClass.never,
        "This mount does not support the verb; target a mount that does.",
        "the entry's bind path (capability failures anchor to the mount)",
    ),
    VFSErrorKind.unrecognized: KindContract(
        RetryClass.never,
        "Check the verb name against this server's advertised tools.",
        "None — source carries the locus",
    ),
    VFSErrorKind.invalid: KindContract(
        RetryClass.never,
        "Fix the flagged parameter and retry.",
        "the entry the invalid input named, when one is implicated",
    ),
    VFSErrorKind.unindexable_pattern: KindContract(
        RetryClass.never,
        "Include a literal of 3+ characters in the pattern, or pass allow_scan=True to run the scan tier.",
        "None — source carries the locus",
    ),
    VFSErrorKind.unaddressable: KindContract(
        RetryClass.never,
        "Access the entry through a shallower mount; its global path exceeds the limit here.",
        "None — reconstruct the locus as source + data['vfs.overflow']['local_path']",
    ),
    VFSErrorKind.conflict: KindContract(
        RetryClass.refresh,
        "Re-read the entry and retry with its current version.",
        "the entry whose version is stale",
    ),
    VFSErrorKind.busy: KindContract(
        RetryClass.transient,
        "Unmount the bind site first, then retry.",
        "the live bind site the data plane may not mutate",
    ),
    VFSErrorKind.cross_mount: KindContract(
        RetryClass.never,
        "Move within one mount, or copy then delete across mounts.",
        "the entry on the far side of the mount boundary",
    ),
    VFSErrorKind.budget_exhausted: KindContract(
        RetryClass.never,
        "Raise the hop budget or shorten the mount chain; a retry will exhaust it again.",
        "None — source carries the locus",
    ),
    VFSErrorKind.truncated: KindContract(
        RetryClass.never,
        "Narrow the pattern, add filters, or scope the call; the result was cut at a runtime budget.",
        "None — source carries the locus",
    ),
    VFSErrorKind.unavailable: KindContract(
        RetryClass.transient,
        "Retry shortly; the resource is temporarily unavailable.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
    VFSErrorKind.backend_unavailable: KindContract(
        RetryClass.transient,
        "Check the mount's backend connection, then retry.",
        "the entry's bind path — the mount whose transport is down",
    ),
    VFSErrorKind.schema_mismatch: KindContract(
        RetryClass.never,
        "This mount's database was provisioned by an incompatible schema version; upgrade or re-provision it.",
        "None — source carries the mount",
    ),
    VFSErrorKind.timeout: KindContract(
        RetryClass.transient,
        "Retry with a longer deadline or a narrower scope.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
    VFSErrorKind.cancelled: KindContract(
        RetryClass.transient,
        "Retry if the cancellation was not requested by this caller.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
    VFSErrorKind.internal: KindContract(
        RetryClass.never,
        "Report this failure; retrying the same request is unlikely to help.",
        "the implicated entry, when one is known; otherwise None with source as locus",
    ),
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def kind_family(kind: VFSErrorKind | str) -> VFSErrorKind | None:
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
            return VFSErrorKind(value)
        if "." not in value:
            return None
        value, _ = value.rsplit(".", 1)
