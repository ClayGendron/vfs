"""Composable result envelope for VFS — Observation rows in, text or payload out.

Every VFS operation returns ``Result``. Results carry ``observations`` —
the frozen :class:`vfs.models2.Observation` rows uniform across grep, glob,
search, graph queries, read/stat/ls, and writes — plus structured errors.
Chaining (set algebra, ``.sort``, ``.top``, ``.filter``) operates in-memory,
and a result's observations are the standard input when operations chain:

    found = await vfs.glob("**/*.py")
    hits = await vfs.grep("auth", observations=found.observations)
    print(hits.top(3))                      # CLI text render
    obs = hits.first()                      # Observation | None

Wire contract: ``to_payload()`` / ``from_payload()`` round-trip losslessly,
so a result can cross an MCP boundary as ``structured_content`` and
reconstruct intact on the far side (``is_error`` maps to ``not success``).
Between mounts only the structured payload travels; text is rendered once,
at the final human/agent boundary, via ``to_str()`` / ``str(result)``.
"""

from __future__ import annotations

import json
import math
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, field_validator

from vfs.models2 import Observation
from vfs.paths import Path  # noqa: TC001 — Pydantic needs this at runtime for field resolution
from vfs.render import render_result

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

# ---------------------------------------------------------------------------
# Structured errors
# ---------------------------------------------------------------------------


class VFSErrorKind(StrEnum):
    """Typed vocabulary for what went wrong — stable on the wire.

    Values are namespaced strings so payloads stay readable. The vocabulary
    maps onto POSIX errno / Plan 9 / JSON-RPC families. A kind this client
    predates is preserved as its raw string by ``ResultError`` (see its
    ``kind`` field), so a newer peer's novel kind never poisons the payload.
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
    invalid = "vfs.invalid"  # EINVAL / ENAMETOOLONG

    # — concurrency / preconditions —
    conflict = "vfs.conflict"  # ESTALE / EBUSY
    cross_mount = "vfs.cross_mount"  # EXDEV

    # — runtime liveness —
    unavailable = "vfs.unavailable"  # EIO / ECONNREFUSED / ENOSPC
    timeout = "vfs.timeout"  # ETIMEDOUT
    cancelled = "vfs.cancelled"  # ECANCELED / EINTR
    internal = "vfs.internal"  # JSON-RPC INTERNAL_ERROR — the VFS itself broke


class ResultError(BaseModel):
    """One structured failure carried on a result.

    ``kind`` is for code (dispatch, retry policy, the raise rule); ``message``
    is the prose an agent reads; ``path`` pins the failure to an entry when
    one is implicated; ``data`` carries optional machine-readable detail that
    does not belong in prose (the conflicting revision, a ``retry_after``) —
    the JSON-RPC / MCP ``error.data`` analogue. The kind travels in the
    payload — a remote mount's error must keep its kind across the MCP hop —
    but text rendering shows prose only. A kind outside this client's
    ``VFSErrorKind`` vocabulary is kept as its raw string (round-trip safe);
    consumers should treat unknown kinds as ``unrecognized``. Producers
    construct from the enum.
    """

    model_config = ConfigDict(frozen=True)

    kind: VFSErrorKind | str
    message: str
    path: Path | None = None
    data: dict[str, Any] | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_known_kind(cls, value: object) -> object:
        """Map a known kind to the enum; keep an unknown string as-is.

        ``VFSErrorKind(value)`` already rejects any non-member (unknown string,
        or a non-string that Pydantic then validates and refuses), so no
        ``isinstance`` guard is needed. ``TypeError`` covers an unhashable
        value that the enum lookup cannot key on.
        """
        try:
            return VFSErrorKind(value)
        except (ValueError, TypeError):
            return value

    def with_mount(self, mount: str) -> ResultError:
        """Frozen copy with ``path`` re-rooted under *mount* (outbound rebase)."""
        if self.path is None:
            return self
        return self.model_copy(update={"path": self.path.with_mount(mount)})

    def without_mount(self, mount: str) -> ResultError:
        """Frozen copy with the *mount* prefix stripped from ``path`` (inbound rebase)."""
        if self.path is None:
            return self
        return self.model_copy(update={"path": self.path.without_mount(mount)})


# ---------------------------------------------------------------------------
# Result — unified envelope
# ---------------------------------------------------------------------------


class Result(BaseModel):
    """Unified result from every VFS operation.

    - **Envelope:** ``function`` identifies how the rows were produced;
      renderers and consumers dispatch on it. It is a free string validated
      against ``vfs.projection.KNOWN_FUNCTIONS`` — unknown names render with
      a fallback arrangement rather than failing.
    - **Rows:** ``observations`` is the frozen row list (``Observation``).
    - **Errors:** ``success`` / ``errors`` carry structured status
      independent of the rows.

    Supports:

    - Row access: ``.first()``, ``.one()``, ``.paths``, and the sequence
      protocol (``len``, iteration, indexing, ``in`` by path).
    - Set algebra: ``&`` (intersection), ``|`` (union), ``-`` (difference).
      Overlapping paths merge **left wins**, filling fields the left row
      left null. Cross-function ``|`` sets ``function="hybrid"``.
    - Enrichment: ``.sort()``, ``.top()``, ``.filter()``, ``.kinds()``.
    - Routing: ``.with_mount()`` / ``.without_mount()`` rebase every row
      and error path across a mount boundary.
    - Serialization: ``.to_payload()`` / ``.from_payload()`` (lossless wire
      dict), ``.to_json()``, ``.to_str(projection=...)``.
    """

    function: str = ""
    observations: list[Observation] = []
    success: bool = True
    errors: list[ResultError] = []

    # -------------------------------------------------------------------
    # Row access
    # -------------------------------------------------------------------

    @property
    def error_message(self) -> str:
        """All error messages joined as a single string."""
        return "; ".join(e.message for e in self.errors)

    @property
    def paths(self) -> tuple[Path, ...]:
        """All observation paths as a tuple."""
        return tuple(o.path for o in self.observations)

    def first(self) -> Observation | None:
        """First observation, or ``None`` if empty."""
        return self.observations[0] if self.observations else None

    def one(self) -> Observation:
        """The sole observation. Raises ``ValueError`` unless exactly one row."""
        if len(self.observations) != 1:
            fn = f" (function={self.function!r})" if self.function else ""
            msg = f"expected exactly one observation, got {len(self.observations)}{fn}"
            raise ValueError(msg)
        return self.observations[0]

    # -------------------------------------------------------------------
    # Sequence protocol
    # -------------------------------------------------------------------

    def __iter__(self) -> Iterator[Observation]:  # type: ignore[override]
        # Overrides BaseModel's (key, value) iteration: a result reads as a
        # sequence of rows. model_dump/model_dump_json are unaffected.
        return iter(self.observations)

    def __getitem__(self, index: int | slice) -> Observation | list[Observation]:
        return self.observations[index]

    def __len__(self) -> int:
        return len(self.observations)

    def __bool__(self) -> bool:
        return self.success and len(self.observations) > 0

    def __contains__(self, path: str) -> bool:
        return path in self.paths

    # -------------------------------------------------------------------
    # Set algebra — left-wins merge on overlap
    # -------------------------------------------------------------------
    # Algebra keys rows by path. Left rows are kept in order (duplicate
    # paths within the left side all survive); duplicate paths on the
    # right collapse first-wins as a merge source.

    def _as_dict(self) -> dict[str, Observation]:
        """Path → first observation with that path."""
        out: dict[str, Observation] = {}
        for o in self.observations:
            out.setdefault(o.path, o)
        return out

    @staticmethod
    def _merge_observation(a: Observation, b: Observation) -> Observation:
        """Left observation wins; fill from right only where left is None.

        Filled list fields are copied so frozen rows never share a mutable
        list across results.
        """
        updates: dict[str, Any] = {}
        for name in Observation.model_fields:
            if getattr(a, name) is not None:
                continue
            value = getattr(b, name)
            if value is not None:
                updates[name] = list(value) if isinstance(value, list) else value
        return a.model_copy(update=updates) if updates else a

    def _combined_errors(self, other: Result) -> list[ResultError]:
        """Concatenate errors, dropping only the *same* error object twice.

        Diamond-shaped chains (``(a | b) & b``) carry the identical
        ``ResultError`` instance down both arms, so an identity check drops
        that repeat. Equality would over-collapse: fan-out merges results
        from distinct terminals, and two mounts failing identically (e.g.
        ``unavailable`` with ``path=None``) produce equal-but-separate
        errors that are two real failures — keep both so a caller counting
        errors sees every downed mount.
        """
        seen = {id(e) for e in self.errors}
        return self.errors + [e for e in other.errors if id(e) not in seen]

    def _merged_function(self, other: Result) -> str:
        """Shared function when both agree (or only one is set), else ``"hybrid"``."""
        if not self.function or not other.function:
            return self.function or other.function
        return self.function if self.function == other.function else "hybrid"

    def __and__(self, other: Result) -> Result:
        """Intersection — observations present on both sides, left wins on overlap."""
        right = other._as_dict()
        merged = [self._merge_observation(o, right[o.path]) for o in self.observations if o.path in right]
        return Result(
            function=self._merged_function(other),
            observations=merged,
            success=self.success and other.success,
            errors=self._combined_errors(other),
        )

    def __or__(self, other: Result) -> Result:
        """Union — all observations; left wins on overlap."""
        right = other._as_dict()
        left_paths = {o.path for o in self.observations}
        merged = [self._merge_observation(o, right[o.path]) if o.path in right else o for o in self.observations]
        merged += [o for o in other.observations if o.path not in left_paths]
        return Result(
            function=self._merged_function(other),
            observations=merged,
            success=self.success and other.success,
            errors=self._combined_errors(other),
        )

    def __sub__(self, other: Result) -> Result:
        """Difference — observations in left whose path is not in right.

        Only the right side's *paths* are consumed; its errors and success
        do not propagate (subtracting a failed result is not a failure).
        """
        right_paths = set(other.paths)
        remaining = [o for o in self.observations if o.path not in right_paths]
        return Result(
            function=self.function,
            observations=remaining,
            success=self.success,
            errors=self.errors,
        )

    # -------------------------------------------------------------------
    # Enrichment chains (local, no backend call)
    # -------------------------------------------------------------------

    def _with_observations(self, observations: list[Observation]) -> Result:
        """Return a new result with the given *observations*, preserving envelope."""
        return Result(
            function=self.function,
            observations=observations,
            success=self.success,
            errors=self.errors,
        )

    def sort(
        self,
        *,
        key: Callable[[Observation], Any] | None = None,
        reverse: bool = True,
    ) -> Result:
        """Re-order observations. Default key is ``score`` (None/NaN treated as ``-inf``)."""
        if key is None:

            def key(o: Observation) -> float:
                score = o.score
                if score is None or math.isnan(score):
                    return float("-inf")
                return score

        return self._with_observations(sorted(self.observations, key=key, reverse=reverse))

    def top(self, k: int) -> Result:
        """Top *k* observations by score. *k* must be >= 1."""
        if k < 1:
            msg = f"k must be >= 1, got {k}"
            raise ValueError(msg)
        sorted_result = self.sort()
        return sorted_result._with_observations(sorted_result.observations[:k])

    def filter(self, fn: Callable[[Observation], bool]) -> Result:
        """Keep observations where *fn(observation)* is truthy."""
        return self._with_observations([o for o in self.observations if fn(o)])

    def kinds(self, *kinds: str) -> Result:
        """Filter observations by kind."""
        kind_set = set(kinds)
        return self.filter(lambda o: o.kind in kind_set)

    # -------------------------------------------------------------------
    # Mount rebasing
    # -------------------------------------------------------------------

    def with_mount(self, mount: str) -> Result:
        """New result with every row and error path re-rooted under *mount*.

        The router's outbound rebase. An empty or root *mount* is the
        identity. Pure — the original result is untouched.
        """
        if not mount or mount == "/":
            return self
        return Result(
            function=self.function,
            observations=[o.with_mount(mount) for o in self.observations],
            success=self.success,
            errors=[e.with_mount(mount) for e in self.errors],
        )

    def without_mount(self, mount: str) -> Result:
        """New result with the *mount* prefix stripped from every row and error path.

        The inbound rebase; raising like :meth:`Path.without_mount` — a
        path outside *mount* is a routing bug, not a slice.
        """
        if not mount or mount == "/":
            return self
        return Result(
            function=self.function,
            observations=[o.without_mount(mount) for o in self.observations],
            success=self.success,
            errors=[e.without_mount(mount) for e in self.errors],
        )

    # -------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------

    def to_payload(self, *, exclude_none: bool = True) -> dict[str, Any]:
        """JSON-safe dict for the wire — MCP ``structured_content``.

        Lossless with :meth:`from_payload`: dropped ``None`` fields restore
        as defaults, so ``from_payload(to_payload()) == self``. One caveat:
        non-finite floats (``nan`` / ``inf``) serialize as ``null`` — JSON
        has no encoding for them — so a non-finite score restores as
        ``None``. Built through ``model_dump_json`` so the payload is
        strict-JSON-safe and always agrees with :meth:`to_json`.
        """
        return json.loads(self.model_dump_json(exclude_none=exclude_none))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Result:
        """Reconstruct a result from a wire payload — the inbound MCP half."""
        return cls.model_validate(payload)

    def to_json(self, *, exclude_none: bool = True) -> str:
        """Pydantic JSON string — ``to_payload`` serialized."""
        return self.model_dump_json(exclude_none=exclude_none)

    def to_str(self, *, projection: tuple[str, ...] | list[str] | None = None) -> str:
        """Render to text via :func:`vfs.render.render_result`.

        *projection* selects Observation columns; ``None`` uses the
        function's default. Arrangement is function-specific.
        """
        return render_result(self, projection=projection)

    def __str__(self) -> str:
        """Delegate to ``to_str()`` for default text rendering."""
        return self.to_str()
