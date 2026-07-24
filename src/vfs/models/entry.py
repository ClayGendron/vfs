"""Domain models for the VFS namespace.

The central pair:

- :class:`Entry` — the record of one namespace entity: a file or a directory.
  A pure :class:`pydantic.BaseModel`, never bound to a database session: it
  carries fields, the construction-time validators, and pure-data methods
  (``with_content``, ``to_observation``, mount rebasing). Derived per-file
  metadata is not an ``Entry``: chunks, versions, and edges are entry-scoped
  models of their own (:class:`~vfs.models.chunk.Chunk`,
  :class:`~vfs.models.version.Version`, :class:`~vfs.models.edge.Edge`),
  addressed by owning file + discriminator, never by a path. They are minted
  storage-side from staged content (``Chunk.split``, ``Version.create`` —
  each model the single door for its rows); ``Entry`` carries no factories
  for them, because no pipeline caller ever holds an ``Entry`` at minting
  time — the write path holds staged rows, the pack verb holds stored rows.
- :class:`Observation` — the frozen, possibly-partial row every operation
  returns about an entry: mirror fields held in type-lockstep with their
  owning model by a drift test (most mirror ``Entry``; ``version`` mirrors
  ``Version.number``, the ``edge_*`` trio mirrors ``Edge``), plus
  query-relative fields (``score``, ``matches``, ...).

Persistence is a separate artifact entirely. The row definitions — columns,
lengths, indexes, the id backbone — live beside the repository, the only
code that ever holds a ``Session``; a drift test pins every persisted
field to a column. Database identifiers never appear on these models.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, computed_field, field_validator, model_validator

from vfs.models.edge import Edge
from vfs.models.version import Version
from vfs.paths import ObjectKind, Path, is_reserved_directory

# Stored kinds whose rows carry text content; everything else refuses
# content reads and edits and surfaces no content metrics.
CONTENT_KINDS: Final[frozenset[str]] = frozenset({"file", "chunk", "version"})


# ---------------------------------------------------------------------------
# The namespace object model
# ---------------------------------------------------------------------------


class Entry(BaseModel):
    """The full record of one object in the VFS namespace: a file or directory.

    A pure detached value: constructing one runs the validators but never
    touches a database. Both kinds share one row shape — a directory simply
    carries no content — so one model covers them; the genuinely different
    things (chunks, versions, edges) are their own models.

    An ``Entry`` is always the whole truth about its object. It exists in two
    ways only: a caller authors one (validators run, recording intent), or the
    repository hydrates one whole from a stored row. There is no partial
    ``Entry`` — partial, query-time views are ``Observation`` rows. Database
    identifiers (the row ``id``, the ``*_id`` references) never appear on it,
    and neither does the per-entry ``version``: like the ids, it is minted and
    guarded inside the persistence layer and reported on observations — a
    caller cannot author one. ``path`` is the model's only identity.

    ``model_fields_set`` semantics, repo-wide: the set records every field
    *assigned* rather than defaulted — and validator assignments count. After
    construction it holds the caller's keys plus everything the validators
    derived (``kind``, ``name``, ``ext``, the content metrics, the timestamps).
    It is a pure record of caller intent only for fields no validator assigns
    (``mime_type``, ``external_id``, ...) — there it still distinguishes an
    explicit ``None`` from an unset default.
    """

    # --- Identity -----------------------------------------------------------

    path: Path
    name: str = ""
    kind: ObjectKind = "file"
    external_id: str | None = None

    # --- Content ------------------------------------------------------------

    content: str | None = None
    content_hash: str | None = None
    mime_type: str | None = None
    ext: str | None = None

    # --- Metrics ------------------------------------------------------------

    lines: int = 0
    size_bytes: int = 0

    # --- Ownership ----------------------------------------------------------

    owner_id: str | None = None

    # --- Timestamps ---------------------------------------------------------

    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    # --- Derived relationship paths -----------------------------------------

    @computed_field
    @property
    def parent_dir(self) -> Path:
        """Directory containing this node (every entry has one)."""
        return self.path.parent_dir

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

    @field_validator("content")
    @classmethod
    def _reject_null_bytes(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Reject null bytes in stored text — they are invalid in SQL text columns."""
        if isinstance(value, str) and "\x00" in value:
            msg = f"content contains null bytes (path={info.data.get('path')!r})"
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
        overrides a name-lottery inference that would land ``directory`` — and
        an *explicit* ``directory`` alongside explicit content is a
        contradiction that raises rather than destroying either statement.
        Structurally content-free places — the root, the ``/.vfs`` meta root,
        the ``/.agents`` skeleton — refuse content outright instead of being
        reclassified.

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
        if kind == "directory" and content is not None:
            msg = f"content conflicts with kind='directory': a directory carries no content (path={path!r})"
            raise ValueError(msg)
        # Gate on ``is None``, not truthiness: an explicit "" is a caller value,
        # not an omission — it should reach field validation, not be derived over.
        if kind is None:
            inferred = path.kind
            if content is not None and inferred == "directory":
                # Structural classifications are never the name lottery —
                # content there is a caller error, not a file in disguise.
                if is_reserved_directory(path):
                    msg = f"content conflicts with reserved path {path!r}: it is structurally a directory"
                    raise ValueError(msg)
                data["kind"] = "file"
            else:
                data["kind"] = inferred
        if data.get("name") is None:
            data["name"] = path.name
        return data

    @model_validator(mode="after")
    def _derive_and_measure(self) -> Entry:
        """Derive ``ext``, enforce content invariants, measure, stamp times.

        Reads the already-canonical ``self.path`` (gated by the ``Path`` field
        type). ``model_fields_set`` preserves caller-provided values: an
        explicit ``ext`` is kept. ``ext`` derives from the path for every kind
        — a directory named ``foo.bar/`` carries ``ext = "bar"`` (POSIX
        parity).
        """
        fields = self.model_fields_set

        if not self.name and self.path != "/":
            msg = f"name must not be empty (path={self.path!r})"
            raise ValueError(msg)

        if self.path == "/" and self.kind != "directory":
            msg = f"the root path is always a directory (kind={self.kind!r})"
            raise ValueError(msg)

        if "ext" not in fields:
            self.ext = self.path.ext

        # Content invariants. The directory null is pure normalization of
        # absence — presence conflicts raise in _derive_identity.
        if self.kind == "directory":
            self.content = None
        elif self.content is None:
            self.content = ""

        if isinstance(self.content, str):
            self.content_hash, self.size_bytes, self.lines = self._content_metadata(self.content)

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
        status: Literal["created", "updated", "unchanged", "deleted"] | None = None,
        matches: list[Match] | None = None,
    ) -> Observation:
        """Project this entry to a frozen :class:`Observation`.

        Every Entry-owned mirror is projected, ``content`` included — an Entry
        is the whole truth, so its projection is a complete observation, and
        the mask says so: every Entry-owned mirror is populated (a null mirror
        is a true absence on the entry), plus whichever query fields the
        producing operation supplied. Mirrors owned by other models
        (``version``, the ``edge_*`` trio) stay unpopulated. Rows that
        should not carry content (listings, search hits) are built from
        column-projected reads, not from entries.
        """
        supplied = {
            name for name, value in (("score", score), ("status", status), ("matches", matches)) if value is not None
        }
        return Observation(
            path=self.path,
            kind=self.kind,
            content=self.content,
            content_hash=self.content_hash,
            mime_type=self.mime_type,
            size_bytes=self.size_bytes,
            created_at=self.created_at,
            updated_at=self.updated_at,
            score=score,
            status=status,
            matches=matches,
            populated=ENTRY_OWNED_MIRRORS | supplied,
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

        Recomputes the content metrics and stamps ``updated_at``. Versioning
        is not this method's job — minting a :class:`Version` belongs to write
        planning. ``model_copy`` bypasses field validation, so the null-byte
        invariant is enforced here.
        """
        if self.kind == "directory":
            msg = f"Cannot set content on a directory: {self.path}"
            raise ValueError(msg)
        if "\x00" in content:
            msg = f"content contains null bytes (path={self.path!r})"
            raise ValueError(msg)
        content_hash, size_bytes, lines = self._content_metadata(content)
        return self.model_copy(
            update={
                "content": content,
                "content_hash": content_hash,
                "size_bytes": size_bytes,
                "lines": lines,
                "updated_at": datetime.now(UTC),
            },
        )


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

    The read-side counterpart of the domain models: operations construct
    observations; callers never do. **A null field means "not populated by
    this call" — never "absent on the entry."** Mirror fields project
    persisted fields and are held in type-lockstep with their owning model by
    a drift test — most mirror :class:`Entry`; ``version`` mirrors
    :class:`~vfs.models.version.Version`'s ``number`` (one per-entry sequence:
    a stat's ``version`` is the entry's current value, a version row's is its
    label) and the ``edge_*`` trio mirrors :class:`~vfs.models.edge.Edge`
    (see ``OBSERVATION_MIRROR_OWNERS``). Query fields are facts about
    *(entry, operation)* — a score, the matched regions, a write status, a
    delete's trash destination — and are never persisted. ``name`` / ``ext``
    / ``parent_dir`` need no mirrors:
    ``path`` is a :class:`Path`, so they come free (``obs.path.name``).

    ``populated`` is the explicit field mask: the names this call actually
    fetched or supplied. It is what distinguishes "fetched, and null" from
    "not fetched" — consumers assert and narrow by the mask, never by
    null-checking values. Backends stamp it from the requested columns;
    when a constructor omits it, it defaults to the non-None supplied
    fields. The mask itself is not a column: it never renders and cannot
    be projected.
    """

    model_config = ConfigDict(frozen=True)

    # --- Model mirrors -------------------------------------------------------

    path: Path
    kind: ObjectKind | None = None
    content: str | None = None
    content_hash: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    version: int | None = None
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
    status: Literal["created", "updated", "unchanged", "deleted"] | None = None
    trash_path: Path | None = None

    # --- Populated-field mask ------------------------------------------------

    populated: frozenset[str] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _shape_row(cls, data: Any) -> Any:
        """Enforce the content-metrics invariant, then default the unstamped mask.

        Content metrics belong only to content-bearing kinds: a storage
        NOT NULL default or a whole-row fetch must never read as a real
        directory size, so a known non-content kind nulls ``size_bytes``
        here — the model, not backend discipline, owns the rule. An
        unfetched (``None``) kind is left alone. The mask then defaults
        to the non-None supplied fields when the caller didn't stamp it,
        so a stamped mask still reports the nulled metric as
        fetched-and-null.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        kind = data.get("kind")
        if kind is not None and kind not in CONTENT_KINDS:
            data["size_bytes"] = None
        if "populated" not in data:
            data["populated"] = frozenset(k for k, v in data.items() if v is not None and k in cls.model_fields)
        return data

    # -----------------------------------------------------------------------
    # Mount rebasing
    # -----------------------------------------------------------------------

    def with_mount(self, mount: str) -> Observation:
        """Frozen copy re-rooted under *mount* — the router's outbound rebase.

        ``trash_path`` names the same mount-local namespace as ``path``,
        so a populated one rebases alongside it.
        """
        update: dict[str, Any] = {"path": self.path.with_mount(mount)}
        if self.trash_path is not None:
            update["trash_path"] = self.trash_path.with_mount(mount)
        return self.model_copy(update=update)

    def without_mount(self, mount: str) -> Observation:
        """Frozen copy with the *mount* prefix stripped — the inbound rebase."""
        update: dict[str, Any] = {"path": self.path.without_mount(mount)}
        if self.trash_path is not None:
            update["trash_path"] = self.trash_path.without_mount(mount)
        return self.model_copy(update=update)


# Mirror/query partition of Observation's fields. The drift test pins every
# mirror to its owning model's field type; query fields exist on no model.
OBSERVATION_QUERY_FIELDS: Final[frozenset[str]] = frozenset(
    {"score", "matches", "in_degree", "out_degree", "status", "trash_path", "populated"},
)
OBSERVATION_MIRROR_FIELDS: Final[frozenset[str]] = frozenset(Observation.model_fields) - OBSERVATION_QUERY_FIELDS

# Which model owns each mirror, and under what field name there. The drift
# test resolves every mirror through this map; ``Entry`` owns the rest.
_NON_ENTRY_MIRROR_OWNERS: Final[dict[str, tuple[type[BaseModel], str]]] = {
    "version": (Version, "number"),
    "edge_type": (Edge, "edge_type"),
    "edge_weight": (Edge, "weight"),
    "edge_distance": (Edge, "distance"),
}
OBSERVATION_MIRROR_OWNERS: Final[dict[str, tuple[type[BaseModel], str]]] = {
    field: _NON_ENTRY_MIRROR_OWNERS.get(field, (Entry, field)) for field in sorted(OBSERVATION_MIRROR_FIELDS)
}
ENTRY_OWNED_MIRRORS: Final[frozenset[str]] = frozenset(
    field for field, (owner, _) in OBSERVATION_MIRROR_OWNERS.items() if owner is Entry
)
