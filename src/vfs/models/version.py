"""The ``Version`` model — one stored version of a file's content.

A version is entry-scoped metadata, not a namespace entry: its identity is
``(file, number)`` — mirroring the ``versions`` table's
``(entry_id, version_number)`` key. It carries no ``path`` or ``name`` and
is never placed in the namespace. ``number`` is the owning entry's
*version* stamped in the same write transaction — one per-entry sequence,
no separate counter. Rows are minted for material content writes
only, so a file's labels may gap where non-content changes (a move, a
metadata write) ticked the entry's version; gaps are expected, never an error.

A version records a *content state*, never an entry state: entry identity and
authored metadata (path, name, ext, mime_type) are current-entry facts with no
history — a rename or metadata write mints nothing, and the label gap is the
entire record that it happened. Reconstruction is self-contained over stored
rows; it consults nothing on the current entry.

:meth:`Version.create` is the single construction door for new versions:
snapshot-vs-diff is decided by :func:`vfs.models.versioning.create_version`,
and the metrics of the *full* version content are always passed explicitly —
a diff row stores the diff, so nothing here ever re-measures a stored
payload. :meth:`Version.reconstruct` walks stored rows in label order from
the nearest snapshot — each diff transforms the previous row's content,
whatever the label distance — and verifies the target's content hash.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

from vfs.models.versioning import create_version as create_version_record
from vfs.models.versioning import reconstruct_version
from vfs.paths import Path  # noqa: TC001 — Pydantic needs this at runtime for field resolution


class Version(BaseModel):
    """One version row, addressed by its owning file + version number.

    ``file`` references the owning file by its path — a reference, not this
    version's own address. Exactly one payload is stored: a snapshot's full
    ``content`` or a non-snapshot's ``version_diff``.
    ``content_hash``/``size_bytes``/``lines`` always describe the *full*
    content of this version — for a diff row they are the metrics of the
    reconstructed text, never of the stored diff.
    """

    file: Path
    number: int
    is_snapshot: bool
    content: str | None = None
    version_diff: str | None = None
    content_hash: str
    lines: int = 0
    size_bytes: int = 0
    created_by: str | None = None
    created_at: datetime | None = None

    @field_validator("content", "version_diff")
    @classmethod
    def _reject_null_bytes(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Reject null bytes in stored text — they are invalid in SQL text columns."""
        if isinstance(value, str) and "\x00" in value:
            msg = f"{info.field_name} contains null bytes"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> Version:
        if self.file == "/":
            msg = "file must reference a file, not the root"
            raise ValueError(msg)
        if self.number < 1:
            msg = f"number must be >= 1, got {self.number}"
            raise ValueError(msg)
        if self.content is not None and self.version_diff is not None:
            msg = "Version rows must not set both content and version_diff"
            raise ValueError(msg)
        return self

    @classmethod
    def create(
        cls,
        *,
        file: Path,
        number: int,
        version_content: str,
        prev_content: str | None,
        created_by: str | None,
        force_snapshot: bool = False,
    ) -> Version:
        """Construct the stored row for *version_content* — the one construction door.

        Snapshot-vs-diff is decided by the versioning provider; the metrics are
        measured here from the full content and stored explicitly.
        """
        record = create_version_record(
            prev_content=prev_content,
            version_content=version_content,
            version_number=number,
            force_snapshot=force_snapshot,
        )
        encoded = version_content.encode()
        return cls(
            file=file,
            number=number,
            is_snapshot=record.is_snapshot,
            content=record.content,
            version_diff=record.version_diff,
            content_hash=hashlib.sha256(encoded).hexdigest(),
            size_bytes=len(encoded),
            lines=version_content.count("\n") + 1 if version_content else 0,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )

    def stored_payload(self) -> str:
        """Return the snapshot text or diff payload this row stores."""
        payload = self.content if self.is_snapshot else self.version_diff
        if payload is None:
            msg = f"Version row missing stored payload: {self.file} v{self.number}"
            raise ValueError(msg)
        return payload

    @classmethod
    def reconstruct(cls, versions: list[Version], target_version: int) -> str:
        """Reconstruct the full content of *target_version* from stored rows.

        Order-based, never dense-range: labels are the owning entry's per-entry version values and
        may gap where non-content changes ticked the sequence. Walks the stored
        rows labeled ≤ target in ascending order from the nearest snapshot,
        applying each diff to the previous row's content, then verifies the
        result against the target row's ``content_hash`` — the hash check,
        not numbering continuity, is what surfaces a lost intermediate row.
        """
        eligible = (row for row in versions if row.number <= target_version)
        ordered = sorted(eligible, key=lambda row: row.number)
        if not ordered or ordered[-1].number != target_version:
            msg = f"Missing version row for v{target_version}"
            raise ValueError(msg)

        snapshot_index = next((i for i in range(len(ordered) - 1, -1, -1) if ordered[i].is_snapshot), None)
        if snapshot_index is None:
            msg = f"Missing snapshot for v{target_version}"
            raise ValueError(msg)

        chain = [(row.is_snapshot, row.stored_payload()) for row in ordered[snapshot_index:]]
        reconstructed = reconstruct_version(chain)
        expected_hash = ordered[-1].content_hash
        actual_hash = hashlib.sha256(reconstructed.encode()).hexdigest()
        if actual_hash != expected_hash:
            msg = f"Hash mismatch for v{target_version}"
            raise ValueError(msg)
        return reconstructed
