"""The edit verb's shared semantics — one meaning for every backend.

Every storage backend adjudicates an edit identically: the target must be
a content-bearing row, the edit sequence threads through the replacement
engine, and the result re-enters ``Entry`` validation so edits obey the
same content invariants writes do. That agreement lives here rather than
in each backend, so it cannot drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from pydantic import ValidationError

from vfs.models import Entry
from vfs.results import ResultError, VFSErrorKind, classified, validation_message
from vfs.storage.replace import apply_edits

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.paths import ObjectKind, Path
    from vfs.storage.replace import EditOperation

# Stored kinds whose rows carry text content; everything else refuses
# content reads and edits and surfaces no content metrics.
CONTENT_KINDS: Final[frozenset[str]] = frozenset({"file", "chunk", "version"})


def edited_entry(
    target: Path, *, kind: str, content: str | None, edits: Sequence[EditOperation]
) -> Entry | ResultError:
    """Apply *edits* to one target: a validated ``Entry`` or a classified error.

    A non-content kind or absent content is ``wrong_kind``; a failed
    replacement is ``invalid``; and the edited content is ``invalid``
    when ``Entry`` — owner of every content invariant — rejects it.
    """
    if kind not in CONTENT_KINDS or content is None:
        return classified(VFSErrorKind.wrong_kind, f"No editable content: {target}", target)
    outcome = apply_edits(content, edits)
    if not outcome.success or outcome.content is None:
        return classified(VFSErrorKind.invalid, outcome.error or "edit failed", target)
    try:
        # Stored kinds wider than ObjectKind (chunk, version) are Entry's to refuse.
        return Entry(path=target, kind=cast("ObjectKind", kind), content=outcome.content)
    except ValidationError as exc:
        return classified(VFSErrorKind.invalid, validation_message(exc), target)
