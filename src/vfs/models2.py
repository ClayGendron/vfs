"""Domain models for the VFS.

The central pair:

- :class:`Entry` — the unified kinded record every namespace entity (file,
  directory, chunk, version, edge) shares; the ``kind`` field determines
  which nullable fields are relevant and how operations dispatch. A pure
  :class:`pydantic.BaseModel`, never bound to a database session: it carries
  fields, the construction-time validators, and pure-data methods (``chunk``,
  ``with_content``, ``with_version``, ``create_version_row``,
  ``to_observation``, version reconstruction).
- :class:`Observation` — the frozen, possibly-partial row every operation
  returns about an entry: mirror fields held in type-lockstep with ``Entry``
  by a drift test, plus query-relative fields (``score``, ``matches``, ...).

Persistence is a separate artifact entirely. The row definitions — columns,
lengths, indexes, the id backbone — live beside the repository, the only
code that ever holds a ``Session``; a drift test pins every persisted
``Entry`` field to a column. Database identifiers never appear on these
models.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, computed_field, field_validator, model_validator

from vfs.chunking import (
    NOTEBOOK_EXTENSION,
    grammar_for_extension,
    split_code,
    split_notebook,
    split_with_line_ranges,
)
from vfs.paths import ObjectKind, Path, chunk_path, decompose_edge, is_meta_path, version_path
from vfs.vector import Vector  # noqa: TC001 — Pydantic needs this at runtime for field resolution
from vfs.versioning import create_version as create_version_record
from vfs.versioning import reconstruct_version

# Kinds that never carry content — construction, normalization of absence,
# and with_content all enforce the same set.
_CONTENT_FREE_KINDS: Final[frozenset[str]] = frozenset({"directory", "tool", "skill"})

# ---------------------------------------------------------------------------
# The unified object model
# ---------------------------------------------------------------------------


class Entry(BaseModel):
    """The full record of one object in the VFS namespace.

    Every entity — file, directory, chunk, version, edge — shares this record
    shape; ``kind`` determines which nullable fields are relevant and how
    operations dispatch. A pure detached value: constructing one runs the
    validators but never touches a database.

    An ``Entry`` is always the whole truth about its object. It exists in two
    ways only: a caller authors one (validators run, recording intent), or the
    repository hydrates one whole from a stored row. There is no partial
    ``Entry`` — partial, query-time views are ``Observation`` rows. Database
    identifiers (the row ``id``, the ``*_id`` references) never appear on it:
    they are minted, resolved, and consumed inside the persistence layer.
    ``path`` is the model's only identity.

    ``model_fields_set`` semantics, repo-wide: the set records every field
    *assigned* rather than defaulted — and validator assignments count. After
    construction it holds the caller's keys plus everything the validators
    derived (``kind``, ``name``, ``ext``, the content metrics, the timestamps).
    It is a pure record of caller intent only for fields no validator assigns
    (``description``, ``mime_type``, ...) — there it still distinguishes an
    explicit ``None`` from an unset default. Logic that needs caller intent for
    a validator-assigned field must read the set *inside* validation, before
    the assignment lands (as the version-metrics carve-out in
    ``_derive_and_measure`` does).
    """

    # --- Identity -----------------------------------------------------------

    path: Path
    name: str = ""
    kind: ObjectKind = "file"
    external_id: str | None = None

    # --- Content ------------------------------------------------------------

    content: str | None = None
    description: str | None = None
    version_diff: str | None = None
    content_hash: str | None = None
    mime_type: str | None = None
    ext: str | None = None

    # --- Metrics ------------------------------------------------------------

    lines: int = 0
    size_bytes: int = 0

    # --- Chunk-specific -----------------------------------------------------

    line_start: int | None = None
    line_end: int | None = None

    # --- Search indexing ----------------------------------------------------

    chunked: bool = False
    encoded: bool = False

    # --- Version-specific ---------------------------------------------------

    version_number: int | None = None
    is_snapshot: bool | None = None
    created_by: str | None = None

    # --- Edge-specific ------------------------------------------------------

    edge_type: str | None = None
    edge_weight: float | None = None
    edge_distance: float | None = None

    # --- Embedding ----------------------------------------------------------

    embedding: Vector | None = None

    # --- Ownership ----------------------------------------------------------

    owner_id: str | None = None
    original_path: str | None = None

    # --- Timestamps ---------------------------------------------------------

    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    # --- Derived relationship paths -----------------------------------------

    @computed_field
    @property
    def parent_dir(self) -> Path:
        """Directory containing this node (every kind has one)."""
        return self.path.parent_dir

    @computed_field
    @property
    def parent_file(self) -> Path | None:
        """Owning file for a chunk/version/edge, else None."""
        if self.kind not in {"chunk", "version", "edge"}:
            return None
        return self.path.parent_file

    @computed_field
    @property
    def source_file(self) -> Path | None:
        """Edge tail endpoint, else None."""
        return self.path.source_file if self.kind == "edge" else None

    @computed_field
    @property
    def target_file(self) -> Path | None:
        """Edge head endpoint, else None."""
        return self.path.target_file if self.kind == "edge" else None

    # -----------------------------------------------------------------------
    # Content metrics
    # -----------------------------------------------------------------------

    @staticmethod
    def _content_metadata(content: str) -> tuple[str, int, int]:
        """Return ``(sha256, size_bytes, lines)`` for *content*."""
        encoded = content.encode()
        return (
            hashlib.sha256(encoded).hexdigest(),
            len(encoded),
            content.count("\n") + 1 if content else 0,
        )

    # -----------------------------------------------------------------------
    # Construction and validation
    # -----------------------------------------------------------------------

    @field_validator("content", "description", "version_diff")
    @classmethod
    def _reject_null_bytes(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Reject null bytes in stored text — they are invalid in SQL text columns."""
        if isinstance(value, str) and "\x00" in value:
            msg = f"{info.field_name} contains null bytes (path={info.data.get('path')!r})"
            raise ValueError(msg)
        return value

    @model_validator(mode="before")
    @classmethod
    def _derive_identity(cls, data: Any) -> Any:
        """Derive ``kind`` and ``name`` from the path when the caller omits them.

        Runs before field validation because ``kind`` is required — an absent
        ``kind`` must be filled here or construction fails. This is also the
        only place raw caller intent is readable, so it arbitrates explicitness:
        explicit content is a statement of a content-bearing kind, so it
        overrides a path inference that would land content-free — and an
        *explicit* content-free kind alongside explicit content is a
        contradiction that raises rather than destroying either statement.
        Structurally content-free places refuse content outright instead of
        being reclassified: the root path, the reserved ``/.vfs`` directory
        skeleton, and ``/.agents`` tool/skill unit directories all raise.

        Operates on a copy — the caller's mapping is never mutated. Inject
        *only* the identity projections, never a field whose
        caller-explicitness the write path depends on — injected keys count as
        "set" (see the class docstring for the full ``model_fields_set``
        contract).
        """
        if not isinstance(data, dict):
            return data
        raw = data.get("path")
        if not isinstance(raw, str):
            return data
        data = dict(data)
        path = Path(raw)
        data["path"] = path
        kind = data.get("kind")
        content = data.get("content")
        if content is not None and path == "/":
            msg = "content conflicts with the root path: '/' carries no content"
            raise ValueError(msg)
        # isinstance gate: an unhashable kind must reach field validation as a
        # literal_error, not explode this membership test with a TypeError.
        if isinstance(kind, str) and kind in _CONTENT_FREE_KINDS and content is not None:
            msg = f"content conflicts with kind={kind!r}: a {kind} carries no content (path={path!r})"
            raise ValueError(msg)
        # Gate on ``is None``, not truthiness: an explicit "" is a caller value,
        # not an omission — it should reach field validation, not be derived over.
        if kind is None:
            inferred = path.kind
            if content is not None and inferred in _CONTENT_FREE_KINDS:
                # Structural classifications (/.vfs skeleton, /.agents units) are
                # never the name lottery — content there is a caller error.
                if is_meta_path(path) or inferred != "directory":
                    msg = f"content conflicts with reserved path {path!r}: a {inferred} carries no content"
                    raise ValueError(msg)
                data["kind"] = "file"
            else:
                data["kind"] = inferred
        if data.get("name") is None:
            data["name"] = path.name
        return data

    @model_validator(mode="after")
    def _derive_and_measure(self) -> Entry:
        """Derive ext/edge_type, enforce content invariants, measure, stamp times.

        Reads the already-canonical ``self.path`` (gated by the ``Path`` field
        type). ``model_fields_set`` preserves caller-provided values: an explicit
        ``ext`` is kept, and a version row that arrives with precomputed metrics
        is not re-measured — a non-snapshot version stores a diff, so re-hashing
        its ``content`` would be wrong. The ``fields`` snapshot is taken before
        this validator's own assignments, which themselves register in
        ``model_fields_set``.
        """
        fields = self.model_fields_set

        if not self.name and self.path != "/":
            msg = f"name must not be empty (path={self.path!r})"
            raise ValueError(msg)

        if self.path == "/" and self.kind != "directory":
            msg = f"the root path is always a directory (kind={self.kind!r})"
            raise ValueError(msg)

        # ext: files only (declared kind authoritative); others stay None.
        if "ext" not in fields:
            self.ext = self.path.ext if self.kind == "file" else None

        # edge_type: read from the edge path's grammar.
        if self.kind == "edge" and "edge_type" not in fields:
            parts = decompose_edge(self.path)
            if parts is not None:
                self.edge_type = parts.edge_type

        # Kind-specific content invariants. The content-free null is pure
        # normalization of absence — presence conflicts raise in _derive_identity.
        if self.kind in _CONTENT_FREE_KINDS:
            self.content = None
        elif self.kind == "file" and self.content is None:
            self.content = ""
        if self.kind == "version" and self.content is not None and self.version_diff is not None:
            msg = "Version rows must not set both content and version_diff"
            raise ValueError(msg)

        # Content metrics — measure from content unless a version row carried
        # explicit precomputed values (reconstruction passes them through).
        if isinstance(self.content, str):
            version_explicit = self.kind == "version" and bool({"content_hash", "size_bytes", "lines"} & fields)
            if not version_explicit:
                self.content_hash, self.size_bytes, self.lines = self._content_metadata(self.content)

        # Timestamps default to now.
        now = datetime.now(UTC)
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

        return self

    # -----------------------------------------------------------------------
    # Projection
    # -----------------------------------------------------------------------

    def to_observation(
        self,
        *,
        score: float | None = None,
        status: Literal["created", "updated", "unchanged"] | None = None,
        matches: list[Match] | None = None,
    ) -> Observation:
        """Project this entry to a frozen :class:`Observation`.

        Every mirror is projected, ``content`` included — an Entry is the
        whole truth, so its projection is a complete observation. Rows that
        should not carry content (listings, search hits) are built from
        column-projected reads, not from entries. Query fields are supplied
        by the producing operation.
        """
        return Observation(
            path=self.path,
            kind=self.kind,
            content=self.content,
            description=self.description,
            content_hash=self.content_hash,
            mime_type=self.mime_type,
            size_bytes=self.size_bytes,
            version_number=self.version_number,
            edge_type=self.edge_type,
            edge_weight=self.edge_weight,
            edge_distance=self.edge_distance,
            created_at=self.created_at,
            updated_at=self.updated_at,
            score=score,
            status=status,
            matches=matches,
        )

    # -----------------------------------------------------------------------
    # Mount rebasing
    # -----------------------------------------------------------------------

    def with_mount(self, mount: str) -> Entry:
        """Copy of this entry re-rooted under *mount* (local → global).

        Delegates to :meth:`Path.with_mount`. Only ``path`` and ``name``
        change — and ``name`` only when the root entry takes the mount's
        leaf. The original is untouched.
        """
        path = self.path.with_mount(mount)
        return self.model_copy(update={"path": path, "name": path.name})

    def without_mount(self, mount: str) -> Entry:
        """Copy of this entry with the *mount* prefix stripped (global → local).

        Boundary-aware and raising, like :meth:`Path.without_mount` — a
        path outside *mount* is a routing bug, not a slice.
        """
        path = self.path.without_mount(mount)
        return self.model_copy(update={"path": path, "name": path.name})

    # -----------------------------------------------------------------------
    # Content replacement
    # -----------------------------------------------------------------------

    def with_content(self, content: str) -> Entry:
        """Copy of this entry with *content* replaced and derived state refreshed.

        Recomputes the content metrics, clears the now-stale diff, resets the
        index flags (new content is unchunked and unencoded), and stamps
        ``updated_at``. Versioning is not this method's job — bumping
        ``version_number`` belongs to write planning. ``model_copy`` bypasses
        field validation, so the null-byte invariant is enforced here.
        """
        if self.kind in _CONTENT_FREE_KINDS:
            msg = f"Cannot set content on a {self.kind}: {self.path}"
            raise ValueError(msg)
        if "\x00" in content:
            msg = f"content contains null bytes (path={self.path!r})"
            raise ValueError(msg)
        content_hash, size_bytes, lines = self._content_metadata(content)
        return self.model_copy(
            update={
                "content": content,
                "version_diff": None,
                "content_hash": content_hash,
                "size_bytes": size_bytes,
                "lines": lines,
                "chunked": False,
                "encoded": False,
                "updated_at": datetime.now(UTC),
            },
        )

    # -----------------------------------------------------------------------
    # Versioning
    # -----------------------------------------------------------------------

    def with_version(self, version_number: int) -> Entry:
        """Copy of this entry moved to *version_number*.

        ``file`` tracks its current version in ``version_number`` only — its
        path has no version segment. ``version`` (``.../versions/<N>``) and
        ``chunk`` (``.../chunks/<N>/<name>``) carry the version in the path,
        so the copy's path is rebuilt and ``name`` re-derived.
        """
        if self.kind not in {"file", "version", "chunk"}:
            msg = f"with_version applies only to files, versions, and chunks: kind={self.kind!r}"
            raise ValueError(msg)
        if self.kind == "file":
            return self.model_copy(update={"version_number": version_number})
        owner = self.path.parent_file
        if owner is None:
            msg = f"{self.kind} path has no owning file: {self.path}"
            raise ValueError(msg)
        path = (
            version_path(owner, version_number)
            if self.kind == "version"
            else chunk_path(owner, self.path.name, version_number)
        )
        return self.model_copy(
            update={"version_number": version_number, "path": path, "name": path.name},
        )

    @classmethod
    def create_version_row(
        cls,
        *,
        file_path: str,
        version_number: int,
        version_content: str,
        prev_content: str | None,
        created_by: str,
        force_snapshot: bool = False,
    ) -> Entry:
        """Construct a ``kind="version"`` row for *version_content*.

        Snapshot-vs-diff is decided by :func:`vfs.versioning.create_version`;
        the metrics of the *full* version content are passed explicitly — a
        diff row stores the diff, so the validator must not re-measure its
        stored payload (the explicit-metrics carve-out).
        """
        content_hash, size_bytes, lines = cls._content_metadata(version_content)
        record = create_version_record(
            prev_content=prev_content,
            version_content=version_content,
            version_number=version_number,
            force_snapshot=force_snapshot,
        )
        now = datetime.now(UTC)
        return cls(
            path=version_path(Path(file_path), version_number),
            kind="version",
            content=record.content,
            version_diff=record.version_diff,
            version_number=version_number,
            is_snapshot=record.is_snapshot,
            created_by=created_by,
            content_hash=content_hash,
            size_bytes=size_bytes,
            lines=lines,
            created_at=now,
            updated_at=now,
        )

    def _stored_version_payload(self) -> str:
        """Return the snapshot text or diff payload for a version row."""
        if self.kind != "version":
            msg = f"Stored payload requested for non-version object: {self.path}"
            raise ValueError(msg)
        payload = self.content if self.is_snapshot else self.version_diff
        if payload is None:
            msg = f"Version row missing stored payload: {self.path}"
            raise ValueError(msg)
        return payload

    @classmethod
    def _reconstruct_file_version(
        cls,
        version_rows: list[Entry],
        target_version: int,
    ) -> str:
        """Reconstruct the content for *target_version* from version rows."""
        by_number = {
            row.version_number: row
            for row in version_rows
            if row.version_number is not None and row.version_number <= target_version
        }
        if target_version not in by_number:
            msg = f"Missing version row for v{target_version}"
            raise ValueError(msg)

        snapshot_version: int | None = None
        for num in range(target_version, 0, -1):
            row = by_number.get(num)
            if row is not None and row.is_snapshot:
                snapshot_version = num
                break
        if snapshot_version is None:
            msg = f"Missing snapshot for v{target_version}"
            raise ValueError(msg)

        chain: list[tuple[bool, str]] = []
        for num in range(snapshot_version, target_version + 1):
            row = by_number.get(num)
            if row is None:
                msg = f"Missing version row for v{num}"
                raise ValueError(msg)
            chain.append((bool(row.is_snapshot), row._stored_version_payload()))

        reconstructed = reconstruct_version(chain)
        expected_hash = by_number[target_version].content_hash
        if expected_hash is not None:
            actual_hash, _, _ = cls._content_metadata(reconstructed)
            if actual_hash != expected_hash:
                msg = f"Hash mismatch for v{target_version}"
                raise ValueError(msg)
        return reconstructed

    # -----------------------------------------------------------------------
    # Chunking
    # -----------------------------------------------------------------------

    @staticmethod
    def split_content(content: str, ext: str | None) -> list[tuple[str, int, int]]:
        """Return ``(chunk_text, line_start, line_end)`` tuples for *content*.

        Dispatches on the file extension *ext* (no leading dot): notebooks use
        ``split_notebook``, extensions with a tree-sitter grammar use
        structure-aware ``split_code``, and everything else falls back to the
        recursive separator splitter. Empty list signals "no split required."
        """
        if ext == NOTEBOOK_EXTENSION:
            return split_notebook(content)
        if grammar := grammar_for_extension(ext):
            return split_code(content, language=grammar)
        return split_with_line_ranges(content)

    def chunk(self) -> list[Entry]:
        """Split this file's content into chunk entries. Pure — ``self`` is untouched.

        Content of at least ``GRAM_SIZE`` bytes yields at least one
        ``kind="chunk"`` row (a whole-file chunk when it fits in one); shorter
        content can form no trigram and produces none. Marking the file
        ``chunked`` is the pipeline's job either way — this method only
        derives. Chunk naming is ``<line_start>_<line_end>``, with an
        ``@<char_offset>`` suffix only when chunks would otherwise collide on
        identical line ranges (e.g. one oversized line splitting into several
        chunks).
        """
        if self.kind != "file":
            msg = f"chunk() applies only to files: kind={self.kind!r}"
            raise ValueError(msg)
        content = self.content or ""
        pieces = self.split_content(content, self.ext)
        if not pieces:
            return []

        # Only duplicate (line_start, line_end) ranges need the @<offset>
        # disambiguator; the content.find walk is skipped for unique ranges.
        range_counts: dict[tuple[int, int], int] = {}
        for _text, line_start, line_end in pieces:
            key = (line_start, line_end)
            range_counts[key] = range_counts.get(key, 0) + 1

        version = self.version_number or 1
        new_chunks: list[Entry] = []
        cursor = 0
        for text, line_start, line_end in pieces:
            name = f"{line_start}_{line_end}"
            if range_counts[(line_start, line_end)] > 1:
                offset = content.find(text, cursor)
                if offset == -1:
                    offset = cursor
                cursor = offset + 1
                name = f"{name}@{offset}"
            new_chunks.append(
                Entry(
                    path=chunk_path(self.path, name, version),
                    kind="chunk",
                    content=text,
                    line_start=line_start,
                    line_end=line_end,
                    version_number=version,
                    owner_id=self.owner_id,
                ),
            )
        return new_chunks


# ---------------------------------------------------------------------------
# Observation — one row of what an operation returned
# ---------------------------------------------------------------------------


class Match(BaseModel):
    """One matched region of an entry — a grep window or an indexed-chunk hit.

    Files are not indexed directly; chunks are. So grep/glean surface
    *regions*: ``start`` / ``end`` are 1-indexed line bounds, ``match`` is
    grep's hit line (``None`` when the whole region matched, as in a glean
    chunk hit), and ``content`` is the region's own text. ``Observation.content``
    stays the entry's full content — rendering a match never requires
    fetching the file. ``score`` is the region's own relevance (glean); the
    row-level ``Observation.score`` is the aggregate (max) across regions.
    """

    model_config = ConfigDict(frozen=True)

    start: int
    end: int
    match: int | None = None
    content: str | None = None
    score: float | None = None


class Observation(BaseModel):
    """One frozen row describing what an operation returned about an entry.

    The read-side counterpart of :class:`Entry`: operations construct
    observations; callers never do. **A null field means "not populated by
    this call" — never "absent on the entry."** Mirror fields project
    persisted ``Entry`` fields and are held in type-lockstep by a drift test;
    query fields are facts about *(entry, operation)* — a score, the matched
    regions, a write status — and are never persisted. ``name`` / ``ext`` /
    ``parent_dir`` need no mirrors: ``path`` is a :class:`Path`, so they
    come free (``obs.path.name``).
    """

    model_config = ConfigDict(frozen=True)

    # --- Entry mirrors -------------------------------------------------------

    path: Path
    kind: ObjectKind | None = None
    content: str | None = None
    description: str | None = None
    content_hash: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    version_number: int | None = None
    edge_type: str | None = None
    edge_weight: float | None = None
    edge_distance: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # --- Query-relative ------------------------------------------------------

    score: float | None = None
    matches: list[Match] | None = None
    in_degree: int | None = None
    out_degree: int | None = None
    status: Literal["created", "updated", "unchanged"] | None = None

    # -----------------------------------------------------------------------
    # Mount rebasing
    # -----------------------------------------------------------------------

    def with_mount(self, mount: str) -> Observation:
        """Frozen copy re-rooted under *mount* — the router's outbound rebase."""
        return self.model_copy(update={"path": self.path.with_mount(mount)})

    def without_mount(self, mount: str) -> Observation:
        """Frozen copy with the *mount* prefix stripped — the inbound rebase."""
        return self.model_copy(update={"path": self.path.without_mount(mount)})


# Mirror/query partition of Observation's fields. The drift test pins every
# mirror to its Entry field's type; query fields must never exist on Entry.
OBSERVATION_QUERY_FIELDS: Final[frozenset[str]] = frozenset(
    {"score", "matches", "in_degree", "out_degree", "status"},
)
OBSERVATION_MIRROR_FIELDS: Final[frozenset[str]] = frozenset(Observation.model_fields) - OBSERVATION_QUERY_FIELDS
