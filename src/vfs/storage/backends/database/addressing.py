"""Where a pattern or a scope points, and where an anonymous caller is judged for it.

Two questions about pattern text, asked before any row is read. Which
side of the tombstone does an arm search: :func:`address_channel` strips
the ``/.vfs/trash`` head from the arms beneath it. And which directory
does a pattern address: the deepest one its literal prefix names
(:func:`addressed_by`), the place an anonymous caller's posture is
judged. A scope channel is judged where its roots composed with its arms
would be (:func:`scope_judged`), and that set is built as paths, from
each root's literal directory and each arm's, never by composing the
text and parsing it back.

    scope = ScopeChannel(roots=(Path("/r"),), arms=("src/**", "*.py"))
    scope_judged(("/z/*.md",), scope, deadline=deadline)   # ['/z', '/r/src', '/r']

The module reads paths and pattern text only: no table, no session and
no statement, so the read builders and the backend both stand on it.
"""

from __future__ import annotations

from itertools import product
from typing import TYPE_CHECKING

from vfs.paths import ROOT, TRASH_ROOT, Address, address_of
from vfs.pattern_matching import GLOB_CHANNEL_LABELS, PatternError, effective_pattern, escape_glob, expand_channel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.deadline import Deadline
    from vfs.paths import Path
    from vfs.pattern_matching import GlobChannel, ScopeChannel


# ---------------------------------------------------------------------------
# Addressing — the side of the tombstone, and the literal prefix
# ---------------------------------------------------------------------------


def address_channel(channel: GlobChannel, patterns: Sequence[str]) -> tuple[Address, ...]:
    """One glob channel's arms, each addressed to the side of the tombstone it searches.

    The one pattern-side resolution of the trash view, shared by glob,
    grep and search: the channel is admitted whole, then every arm under
    the head is stripped to the pattern it names. The bare head is a
    directory, not a pattern — it is refused as the bare root is, naming
    the channel, so no verb ever compiles the stripped ``/``.
    """
    addresses: list[Address] = []
    for pattern in expand_channel(channel, patterns):
        address = address_of(pattern)
        if address.trashed and address.stored == "/":
            label = GLOB_CHANNEL_LABELS[channel]
            detail = f"the view's head is a directory, not a pattern; scope beneath it with {TRASH_ROOT + '/**'!r}"
            raise PatternError(f"{label} {pattern!r}: {detail}")
        addresses.append(address)
    return tuple(addresses)


def literal_prefix(pattern: str) -> str:
    """The text of *pattern* before its first ``*``, ``?`` or ``[``; the whole of it when it holds none."""
    index = min((i for i, ch in enumerate(pattern) if ch in "*?["), default=len(pattern))
    return pattern[:index]


# ---------------------------------------------------------------------------
# The judged paths — where an anonymous caller's posture is read
# ---------------------------------------------------------------------------


def addressed_by(patterns: Sequence[str]) -> list[str]:
    """The path each pattern addresses — the directory its literal prefix names — where anonymous is judged.

    A pattern's scope is the deepest directory its literal prefix names
    once braces are expanded: ``/scratch/**`` and ``/scratch/a*`` are
    judged at ``/scratch``, a bare ``**`` at the root, a trash-view
    pattern at the path beneath the head. No pattern at all is the
    whole mount, judged at the root. A pattern the fan will refuse is
    judged at the root: the refusal, not the posture, answers it.
    """
    if not patterns:
        return [ROOT]
    try:
        addresses = address_channel("pattern", patterns)
    except PatternError:
        return [ROOT]
    return list(dict.fromkeys(_addressed_paths(addresses)))


def scope_judged(patterns: Sequence[str], scope: ScopeChannel, *, deadline: Deadline) -> list[str] | None:
    """The paths an anonymous caller is judged at for *patterns* and *scope*, or ``None`` past *deadline*.

    The set is the one composition judges: :func:`addressed_by` over the
    entry-wide *patterns* and over every root joined with every arm as
    one pattern. It is built without that text. A root that holds no
    metacharacter is judged at its stored path joined with each arm's
    literal directory (``/r`` under ``src/**`` at ``/r/src``, under
    ``*.py`` at ``/r``); a root that holds one is judged once, at the
    deepest directory above its first, because composition escapes a
    root into one-member classes and the literal prefix stops at the
    first ``[``. The caller hands the paths on through
    :func:`~vfs.paths.address_of`, and the sets are equal there.

    The order is the caller's: the entry-wide paths first, in
    :func:`addressed_by`'s order, then each root's paths in root order
    and arm order, each path at its first appearance. A refusable
    pattern or arm answers the root at once, the refusal and not the
    posture answering it. A scope with no arm or no root judges nothing
    of its own: the answer is the entry-wide paths, or the root when
    there is no entry-wide pattern either, the whole mount.

    The work is the product of roots and arms, so it runs on a worker,
    reading *deadline* between chunks of patterns, of roots and of
    joined pairs. Each pass counts what it reached: fewer patterns
    addressed, fewer roots read or fewer pairs joined than were given
    answers ``None``, never the part that was reached, which would be
    judged as the whole call. A scope ``admit_scope`` refuses (a root
    stored at ``/``, a live root above the trash head) is out of
    contract here: its joined text means more than its parts.
    """
    addressed: dict[str, None] = {}
    reached = 0
    for chunk in deadline.chunks(patterns):
        try:
            addresses = address_channel("pattern", chunk)
        except PatternError:
            return [ROOT]
        addressed.update(dict.fromkeys(_addressed_paths(addresses)))
        reached += len(chunk)
    if reached < len(patterns):
        return None
    try:
        arms = expand_channel("pattern", scope.arms)
    except PatternError:
        return [ROOT]
    if not arms or not scope.roots:
        return list(addressed) or [ROOT]
    bases: list[tuple[str, bool]] = []
    for roots in deadline.chunks(scope.roots):
        bases.extend(_root_base(root) for root in roots)
    if len(bases) < len(scope.roots):
        return None
    directories = list(dict.fromkeys(_arm_directory(arm) for arm in arms))
    pairs = 0
    for joined in deadline.chunks(product(bases, directories)):
        for (base, whole), directory in joined:
            addressed.setdefault(base + directory if whole else base)
        pairs += len(joined)
    return list(addressed) if pairs == len(bases) * len(directories) else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _addressed_paths(addresses: Sequence[Address]) -> list[str]:
    """Each admitted pattern's addressed path: the deepest directory its literal prefix names."""
    addressed: list[str] = []
    for address in addresses:
        prefix = literal_prefix(address.stored)
        scope = prefix if prefix.endswith("/") else prefix.rsplit("/", 1)[0] + "/"
        addressed.append(scope.rstrip("/") if scope.startswith("/") and scope != "/" else ROOT)
    return addressed


def _root_base(root: Path) -> tuple[str, bool]:
    """A scope root as composition reads it: its judged directory, and whether each arm's joins beneath it.

    The root's stored form on its side of the tombstone reads back whole
    when it holds no metacharacter: it is the directory, and ``True``
    says each arm's literal directory joins under it. Otherwise the
    escaped root's literal prefix stops at its first metacharacter, and
    the directory is the deepest one above that, the same for every arm.
    """
    stored = address_of(str(root)).stored
    escaped = escape_glob(stored)
    if literal_prefix(escaped) == escaped:
        return stored, True
    [directory] = _addressed_paths((Address(escaped, trashed=False),))
    return directory, False


def _arm_directory(arm: str) -> str:
    """The directory an arm's text names before its first metacharacter, relative to its root; empty when none.

    A name arm floats beneath the root and names no directory. A path
    arm is anchored as composition anchors it, cut at its first ``*``,
    ``?`` or ``[``, then cut back to before its last ``/``: ``src/**``
    and ``src/a*.py`` give ``/src``, ``[ab]/**`` and ``**/x.py`` give
    nothing. The text is read as it stands and never addressed to a side
    of the tombstone: an arm that begins ``/.vfs/trash`` names a
    directory beneath its root, not the trash view.
    """
    if "/" not in arm:
        return ""
    return literal_prefix(effective_pattern(ROOT, arm)).rsplit("/", 1)[0]
