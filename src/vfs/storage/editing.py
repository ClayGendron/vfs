"""The edit verb's shared semantics — one meaning for every backend.

Every storage backend adjudicates an edit identically: the target must be
a content-bearing row, the edit sequence threads through the replacement
engine, and the result re-enters ``Entry`` validation so edits obey the
same content invariants writes do. That agreement lives here rather than
in each backend, so it cannot drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from vfs.models import CONTENT_KINDS, Entry
from vfs.results import ErrorKind, ResultError, classified, validation_message
from vfs.storage.replace import apply_edits

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.paths import ObjectKind, Path
    from vfs.storage.replace import EditOperation


def edited_entry(
    target: Path, *, kind: str, content: str | None, edits: Sequence[EditOperation]
) -> Entry | ResultError:
    """Apply *edits* to one target: a validated ``Entry`` or a classified error.

    A non-content kind or absent content is ``wrong_kind``; a failed
    replacement is ``invalid``; and the edited content is ``invalid``
    when ``Entry`` — owner of every content invariant — rejects it.
    """
    if kind not in CONTENT_KINDS or content is None:
        return classified(ErrorKind.wrong_kind, target, detail="no editable content", data={"kind": kind})
    outcome = apply_edits(content, edits)
    if not outcome.success or outcome.content is None:
        return classified(ErrorKind.invalid, target, detail=outcome.error or "the edit did not apply")
    try:
        # Stored kinds wider than ObjectKind (chunk, version) are Entry's to refuse.
        return Entry(path=target, kind=cast("ObjectKind", kind), content=outcome.content)
    except ValidationError as exc:
        return classified(ErrorKind.invalid, target, detail=validation_message(exc))
