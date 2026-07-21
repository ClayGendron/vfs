"""Composable result envelope for VFS — evidence in, verdict derived.

Every VFS operation returns ``Result``. Results carry ``observations`` —
the frozen :class:`vfs.models.Observation` rows uniform across grep, glob,
search, graph queries, read/stat/ls, and writes — plus structured errors.
Chaining (set algebra, ``.sort``, ``.top``, ``.filter``) operates in-memory,
and a result's observations are the standard input when operations chain:

    found = await vfs.glob("**/*.py")
    hits = await vfs.grep("auth", observations=found.observations)
    print(hits.top(3))                      # CLI text render
    obs = hits.first()                      # Observation | None

The envelope carries **evidence**: frozen error values with severity,
provenance (``source``), and pinned locus semantics. Every verdict —
``success``, ``is_error``, retry class, rendering — is **derived** from
that evidence, so a verdict that disagrees with its evidence is
unrepresentable. ``success`` is a property (no fatal-severity errors),
serialized outbound for ``isError``-checking MCP clients and ignored
inbound.

Wire contract: ``to_payload()`` / ``from_payload()`` round-trip losslessly,
so a result can cross an MCP boundary as ``structured_content`` and
reconstruct intact on the far side (``is_error`` maps to ``not success``).
Both models are open (``extra='allow'``): fields this client predates ride
through a hop instead of being stripped, and ``from_payload`` validates
per item — one malformed row quarantines as a warning, never poisons its
siblings, and never raises. Between mounts only the structured payload
travels; text is rendered once, at the final human/agent boundary, via
``to_str()`` / ``str(result)``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from vfs.models import Observation
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.results.kinds import (
    _KIND_ALIASES,
    KIND_CONTRACTS,
    KindContract,
    RetryClass,
    Severity,
    VFSErrorKind,
    kind_family,
)
from vfs.results.render import render_result

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

# The vocabulary and contract tables live in vfs.results.kinds (shared with the
# renderer); re-exported here as the envelope's one import surface.
__all__ = [
    "KIND_CONTRACTS",
    "KindContract",
    "Result",
    "ResultError",
    "RetryClass",
    "Severity",
    "VFSErrorKind",
    "kind_family",
]

# ---------------------------------------------------------------------------
# Structured errors
# ---------------------------------------------------------------------------


class ResultError(BaseModel):
    """One structured failure carried on a result — a frozen fact.

    ``kind`` is for code (dispatch, retry policy, the raise rule);
    ``message`` is the prose an agent reads; ``severity`` is the trust
    tier (:class:`Severity` — unknown reads as error); ``path`` pins the
    failure to an entry when one is implicated, **in the reader's
    namespace, rebased every hop** — ``None`` means "no single entry
    implicated", in which case ``source`` carries the locus. ``source``
    is provenance: the bind path of the producing hop in the reader's
    namespace, stamped structurally by the rebase seam (``with_mount``),
    never by producers. ``data`` carries optional machine-readable detail
    that does not belong in prose — the JSON-RPC / MCP ``error.data``
    analogue; envelope machinery writes only ``vfs.``-prefixed keys.

    **Identity is value identity.** Frozen field equality is the dedup
    key across merges and wire hops; two mounts failing identically stay
    two facts because their ``source`` differs. Producers wanting
    N-occurrence semantics from one source must add a ``data``
    discriminator — distinct facts must differ in some field.

    **No consumer may parse ``message``.** It is non-load-bearing and
    truncatable; every load-bearing fact must be a structured field.
    Rebase seams touch ``path``/``source``/``data``, never ``message``.

    The model is open (``extra='allow'``): fields from a newer peer ride
    through this hop and join value equality. A kind outside this
    client's vocabulary is kept as its raw string (round-trip safe);
    dispatchers degrade it via :func:`kind_family`.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    kind: VFSErrorKind | str
    message: str
    severity: Severity | str = Severity.error
    path: Path | None = None
    source: Path | None = None
    data: dict[str, Any] | None = None
    # Orthogonal to the kind-derived retry_class: the producing backend's
    # classifier saw a transient condition — same op, unchanged, may succeed.
    retryable: bool = False

    @field_validator("kind", mode="before")
    @classmethod
    def _coerce_known_kind(cls, value: object) -> object:
        """Resolve aliases, map a known kind to the enum, keep unknowns as-is.

        ``VFSErrorKind(value)`` rejects any non-member; ``TypeError`` covers
        non-string values, which Pydantic then validates and refuses.
        """
        if isinstance(value, str):
            value = _KIND_ALIASES.get(value, value)
        try:
            return VFSErrorKind(value)
        except (ValueError, TypeError):
            return value

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_known_severity(cls, value: object) -> object:
        """Map a known severity to the enum; keep an unknown string as-is."""
        try:
            return Severity(value)
        except (ValueError, TypeError):
            return value

    @property
    def is_fatal(self) -> bool:
        """Whether this entry fails its envelope — unknown severity reads as error."""
        return self.severity not in (Severity.warning, Severity.info)

    @property
    def retry_class(self) -> RetryClass | None:
        """Contract-table retry class via :func:`kind_family`; unknown kind → ``None``."""
        family = kind_family(self.kind)
        return KIND_CONTRACTS[family].retry_class if family is not None else None

    def with_mount(self, mount: str) -> ResultError:
        """Frozen copy re-rooted under *mount* — the outbound rebase, and
        the provenance stamp: always a copy, always transforms.

        The first hop stamps ``source=mount``; every later hop re-roots
        the existing ``source`` — so which mount produced this error
        survives any merge depth and any number of wire crossings, with
        zero producer discipline. A ``path`` whose rebased form would
        exceed ``MAX_PATH_LENGTH`` cannot exist as a ``Path`` (hard
        invariant), so it rebases to ``path=None`` with the producing
        frame's entry-local path (``path`` stripped of ``source``)
        preserved append-once in ``data["vfs.overflow"]`` — recorded
        once, never clobbered; ``source`` keeps rebasing, so the row's
        address reconstructs at any depth as ``source + local_path``. A
        ``source`` that itself overflows clamps to *mount* — the seam
        never raises, and the nearest addressable locus wins.
        """
        mount = Path(mount)
        overflows = self.source is not None and len(mount) + len(self.source) > MAX_PATH_LENGTH
        if self.source is None or (overflows and mount != "/" and self.source != "/"):
            source = mount
        else:
            source = self.source.with_mount(mount)
        updates: dict[str, Any] = {"source": source}
        if self.path is not None:
            if mount != "/" and self.path != "/" and len(mount) + len(self.path) > MAX_PATH_LENGTH:
                data = dict(self.data or {})
                if "vfs.overflow" not in data:
                    local = self.path
                    if self.source is not None:
                        try:
                            local = self.path.without_mount(self.source)
                        except ValueError:
                            local = self.path
                    data["vfs.overflow"] = {"local_path": str(local)}
                updates |= {"path": None, "data": data}
            else:
                updates["path"] = self.path.with_mount(mount)
        return self.model_copy(update=updates)

    def without_mount(self, mount: str) -> ResultError:
        """Frozen copy with the *mount* prefix stripped from ``path`` and
        ``source`` — the inbound rebase, inverse of :meth:`with_mount`.

        A ``source`` that strips to ``/`` returns to ``None``: in the
        producer's own frame the error has no upstream hop, so the
        round-trip ``e.with_mount(m).without_mount(m) == e`` holds.
        """
        updates: dict[str, Any] = {}
        if self.path is not None:
            updates["path"] = self.path.without_mount(mount)
        if self.source is not None:
            stripped = self.source.without_mount(mount)
            updates["source"] = None if stripped == "/" else stripped
        return self.model_copy(update=updates) if updates else self


def classified(
    kind: VFSErrorKind,
    message: str,
    path: Path | None = None,
    *,
    target: Path | None = None,
) -> ResultError:
    """One classified error; *target* names the requested row for merge dedup.

    The ``data`` discriminator keeps value-identical failures from distinct
    batch targets as distinct facts — the envelope's documented contract.
    """
    data = {"target": str(target)} if target is not None else None
    return ResultError(kind=kind, message=message, path=path, data=data)


def validation_message(exc: ValidationError) -> str:
    """Flatten a pydantic ``ValidationError`` into one agent-facing line.

    Every failure reports — deduplicated, caller order — so a multi-field
    rejection reads whole instead of surfacing one arbitrary first error.
    """
    return "; ".join(dict.fromkeys(error["msg"] for error in exc.errors()))


# ---------------------------------------------------------------------------
# Result — unified envelope
# ---------------------------------------------------------------------------


class Result(BaseModel):
    """Unified result from every VFS operation — evidence in, verdict derived.

    - **Envelope:** ``ops`` records every op whose rows were merged in
      (ordered union under ``|``) — one vocabulary with the router's
      ``vfs.ops``, kept open ``str`` because a peer may report ops this
      client predates. The ``.op`` property yields the sole op, or
      ``None`` for a cross-op merge — renderers fall back to a generic
      arrangement on ``None``.
    - **Rows:** ``observations`` is the frozen row list (``Observation``).
    - **Errors:** ``errors`` carries structured evidence; ``success`` is a
      **property** — true iff no fatal-severity entry — serialized
      outbound by ``to_payload`` and ignored inbound (``from_payload``
      re-derives it). The lying verdict-beside-evidence state is
      unrepresentable.

    The model is open (``extra='allow'``): unknown fields from newer peers
    round-trip through this hop instead of being stripped.

    Supports:

    - Row access: ``.first()``, ``.one()``, ``.paths``, and the sequence
      protocol (``len``, iteration, indexing, ``in`` by path).
    - Set algebra: ``&`` (intersection), ``|`` (union), ``-`` (difference).
      ``|`` is a pure fold — associative, idempotent over path-distinct
      rows, with ``Result()`` as identity — and rebase distributes over
      it. Overlapping paths merge **left wins by mask**: the right fills
      only fields the left never fetched, masks union, and a version
      disagreement stamps the merged version null (see
      :meth:`_merge_observation`). Policy lives outside the algebra:
      ``merge`` is the plain fold, ``merge_branches`` adds fan-out
      demotion.
    - Enrichment: ``.sort()``, ``.top()``, ``.filter()``, ``.kinds()``.
    - Routing: ``.with_mount()`` / ``.without_mount()`` rebase every row
      and error across a mount boundary and stamp error provenance.
    - Serialization: ``.to_payload()`` / ``.from_payload()`` (open,
      per-item-lenient wire dict), ``.to_json()``, ``.to_str()``.
    """

    model_config = ConfigDict(extra="allow")

    ops: tuple[str, ...] = ()
    observations: list[Observation] = []
    errors: list[ResultError] = []

    @model_validator(mode="before")
    @classmethod
    def _drop_stored_verdict(cls, data: Any) -> Any:
        """Drop any stored verdict before validation.

        ``success`` on inbound data is ignored and re-derived — a wire
        payload cannot assert a verdict its evidence does not support,
        and the emitted key must not ride along as an extra field.
        """
        if isinstance(data, dict) and "success" in data:
            data = dict(data)
            data.pop("success")
        return data

    # -------------------------------------------------------------------
    # Verdict and evidence accessors — all derived
    # -------------------------------------------------------------------

    @property
    def success(self) -> bool:
        """Derived verdict: true iff no fatal-severity error entry."""
        return not any(e.is_fatal for e in self.errors)

    @property
    def op(self) -> str | None:
        """The sole producing op, or ``None`` for a cross-op merge."""
        return self.ops[0] if len(self.ops) == 1 else None

    @property
    def failures(self) -> list[ResultError]:
        """Fatal-severity entries — the evidence behind ``success is False``."""
        return [e for e in self.errors if e.is_fatal]

    @property
    def warnings(self) -> list[ResultError]:
        """Warning-severity entries — loss on record, rows still trustworthy."""
        return [e for e in self.errors if e.severity == Severity.warning]

    @property
    def error_message(self) -> str:
        """All error messages joined as a single string."""
        return "; ".join(e.message for e in self.errors)

    # -------------------------------------------------------------------
    # Row access
    # -------------------------------------------------------------------

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
            fn = f" (op={self.op!r})" if self.op else ""
            msg = f"expected exactly one observation, got {len(self.observations)}{fn}"
            raise ValueError(msg)
        return self.observations[0]

    # -------------------------------------------------------------------
    # Sequence protocol
    # -------------------------------------------------------------------

    def __iter__(self) -> Iterator[Observation]:  # ty: ignore[invalid-method-override]
        # Overrides BaseModel's (key, value) iteration: a result reads as a
        # sequence of rows. model_dump/model_dump_json are unaffected.
        return iter(self.observations)

    def __getitem__(self, index: int | slice) -> Observation | list[Observation]:
        return self.observations[index]

    def __len__(self) -> int:
        return len(self.observations)

    def __bool__(self) -> bool:
        # Truthiness is success, nothing more: a successful glob with zero
        # matches is truthy. Emptiness is a separate fact — use len()/first().
        return self.success

    def __contains__(self, path: str) -> bool:
        return path in self.paths

    # -------------------------------------------------------------------
    # Set algebra — left-wins-by-mask merge on overlap
    # -------------------------------------------------------------------
    # Algebra keys rows by path: left rows survive in order; right rows
    # merge first-wins-by-mask where paths overlap, append otherwise.

    def _as_dict(self) -> dict[str, Observation]:
        """Path → first observation with that path."""
        out: dict[str, Observation] = {}
        for o in self.observations:
            out.setdefault(o.path, o)
        return out

    @staticmethod
    def _merge_observation(a: Observation, b: Observation) -> Observation:
        """Mask-driven fill: left wins every field it fetched; the right
        fills only fields absent from the left's mask; masks union.

        Presence is the ``populated`` mask, never value-nullness — a left
        field fetched-and-null is a fact and is never overwritten (the
        statx/NFS discipline; a null check would be the 9P wstat sentinel
        conflation the mask exists to kill). Filled list fields are copied
        so frozen rows never share a mutable list across results.

        ``version`` is the row's snapshot coordinate, not fillable state:
        when both sides carry differing versions the merged row stamps
        ``version=None`` (still masked) — a composite of two snapshots
        claims no single one, and a version-guarded consumer must re-stat.
        Same-version and one-sided merges keep the value, so the rule is
        agree-or-null: associative, commutative, idempotent.
        """
        updates: dict[str, Any] = {}
        for name in Observation.model_fields:
            if name == "populated" or name in a.populated or name not in b.populated:
                continue
            value = getattr(b, name)
            updates[name] = list(value) if isinstance(value, list) else value
        if "version" in a.populated and "version" in b.populated and a.version != b.version:
            updates["version"] = None
        mask = a.populated | b.populated
        if mask != a.populated:
            updates["populated"] = mask
        return a.model_copy(update=updates) if updates else a

    def _combined_errors(self, other: Result) -> list[ResultError]:
        """Concatenate errors, dropping repeats by **value equality**.

        Diamond-shaped chains (``(a | b) & b``) carry the same error fact
        down both arms — equal values collapse to one, on both sides of a
        wire hop. Two mounts failing identically stay two facts because
        their ``source`` differs (provenance is what makes equality-dedup
        lawful). List containment, not a set: ``data`` dicts are
        unhashable.
        """
        combined = list(self.errors)
        for e in other.errors:
            if e not in combined:
                combined.append(e)
        return combined

    def _merged_ops(self, other: Result) -> tuple[str, ...]:
        """Ordered union — lossless, both sides' op names survive."""
        return self.ops + tuple(o for o in other.ops if o not in self.ops)

    def __and__(self, other: Result) -> Result:
        """Intersection — observations present on both sides, left wins by mask."""
        right = other._as_dict()
        merged = [self._merge_observation(o, right[o.path]) for o in self.observations if o.path in right]
        return Result(
            ops=self._merged_ops(other),
            observations=merged,
            errors=self._combined_errors(other),
        )

    def __or__(self, other: Result) -> Result:
        """Union — all observations; left wins by mask on overlap."""
        right = other._as_dict()
        left_paths = {o.path for o in self.observations}
        merged = [self._merge_observation(o, right[o.path]) if o.path in right else o for o in self.observations]
        merged += [o for o in other.observations if o.path not in left_paths]
        return Result(
            ops=self._merged_ops(other),
            observations=merged,
            errors=self._combined_errors(other),
        )

    def __sub__(self, other: Result) -> Result:
        """Difference — observations in left whose path is not in right.

        Only the right side's *paths* are consumed; its errors do not
        propagate (subtracting a failed result is not a failure).
        """
        right_paths = set(other.paths)
        remaining = [o for o in self.observations if o.path not in right_paths]
        return Result(
            ops=self.ops,
            observations=remaining,
            errors=self.errors,
        )

    # -------------------------------------------------------------------
    # Merge policy — the router's seams over the pure fold
    # -------------------------------------------------------------------

    @classmethod
    def merge(cls, results: Iterable[Result], *, op: str | None = None) -> Result:
        """Plain fold of ``|`` over *results* — no policy, fully lawful.

        For scoped and grouped dispatch, where every branch answers for an
        entry the caller named: any fatal entry fails the merged envelope.
        *op* seeds the envelope's verb for an empty merge. Rows for the
        same global path fuse left-wins by mask; at bind paths this
        decorates the owner's row with the mounted root's fields (the two
        rows are the same entry seen from both sides of the seam — their
        counters are unrelated, so the decorated row's version reads
        null) — bind paths are the one place branch row-sets are *not*
        disjoint.
        """
        merged = cls(ops=(op,) if op else ())
        for r in results:
            merged = merged | r
        return merged

    @classmethod
    def merge_branches(cls, results: Iterable[Result], *, op: str | None = None) -> Result:
        """Fan-out merge under the **zero-progress rule** — the only
        demotion seam.

        If any branch produced rows or succeeded, failed branches' fatal
        entries demote to warnings — kind, source, data, and retry class
        intact — and the envelope succeeds: one dead mount among live
        ones is loss on record, not failure. If every branch failed,
        errors stay fatal. For unscoped fan-out and tree descent only;
        scoped dispatch never demotes — an entry the caller named fails
        loudly.
        """
        branches = list(results)
        if any(r.observations or r.success for r in branches):
            branches = [r if r.success else r._demoted() for r in branches]
        return cls.merge(branches, op=op)

    def _demoted(self) -> Result:
        """Copy with every fatal entry demoted to warning severity."""
        errors = [e.model_copy(update={"severity": Severity.warning}) if e.is_fatal else e for e in self.errors]
        return Result(ops=self.ops, observations=self.observations, errors=errors)

    # -------------------------------------------------------------------
    # Enrichment chains (local, no backend call)
    # -------------------------------------------------------------------

    def _with_observations(self, observations: list[Observation]) -> Result:
        """Return a new result with the given *observations*, preserving envelope."""
        return Result(
            ops=self.ops,
            observations=observations,
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
        """New result re-rooted under *mount* — the router's outbound
        rebase and the provenance-stamping seam.

        Every row rebases; every error rebases **and** gains/re-roots its
        ``source`` (see :meth:`ResultError.with_mount`) — a root *mount*
        is a real hop for provenance even though row paths are unchanged.
        An empty *mount* is the identity. A row whose global path would
        exceed ``MAX_PATH_LENGTH`` cannot exist as a ``Path`` (hard
        invariant), so it is dropped from the rows and recorded as a
        ``vfs.unaddressable`` **warning** — the row exists but is not
        addressable through this mount; loss on record, envelope still
        successful. Its locus is ``source`` plus the append-once
        ``data["vfs.overflow"]`` local path. Pure — the original is
        untouched.
        """
        if not mount:
            return self
        mount = Path(mount)
        errors = [e.with_mount(mount) for e in self.errors]
        if mount == "/":
            return Result(ops=self.ops, observations=self.observations, errors=errors)
        observations: list[Observation] = []
        for o in self.observations:
            if o.path != "/" and len(mount) + len(o.path) > MAX_PATH_LENGTH:
                errors.append(
                    ResultError(
                        kind=VFSErrorKind.unaddressable,
                        message=(
                            f"Path exceeds {MAX_PATH_LENGTH} chars when rebased under "
                            f"'{mount}' and cannot be addressed through this mount"
                        ),
                        severity=Severity.warning,
                        source=mount,
                        data={"vfs.overflow": {"local_path": str(o.path)}},
                    )
                )
                continue
            observations.append(o.with_mount(mount))
        return Result(ops=self.ops, observations=observations, errors=errors)

    def without_mount(self, mount: str) -> Result:
        """New result with the *mount* prefix stripped from every row and error.

        The inbound rebase; raising like :meth:`Path.without_mount` — a
        path outside *mount* is a routing bug, not a slice.
        """
        if not mount or mount == "/":
            return self
        return Result(
            ops=self.ops,
            observations=[o.without_mount(mount) for o in self.observations],
            errors=[e.without_mount(mount) for e in self.errors],
        )

    # -------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------

    def to_payload(self, *, exclude_none: bool = True, max_errors: int | None = None) -> dict[str, Any]:
        """JSON-safe dict for the wire — MCP ``structured_content``.

        Emits the **derived** ``success`` (so ``is_error = not success``
        can never lie) beside the evidence. Lossless with
        :meth:`from_payload`: dropped ``None`` fields restore as defaults.
        One caveat: non-finite floats (``nan`` / ``inf``) serialize as
        ``null`` — JSON has no encoding for them — so a non-finite score
        restores as ``None``. Built through ``model_dump_json`` so the
        payload is strict-JSON-safe and always agrees with :meth:`to_json`.

        *max_errors* caps the boundary, never the algebra: when the error
        list exceeds it, errors group by ``(kind, severity)`` — each group
        ships its head plus one rollup entry carrying
        ``data["vfs.rollup"] = {count, sources}``. Severity is preserved
        per group, so the derived verdict is invariant under rollup.
        In-process, nothing is ever dropped.
        """
        target = self
        if max_errors is not None and len(self.errors) > max_errors:
            target = Result(
                ops=self.ops,
                observations=self.observations,
                errors=self._rolled_errors(),
            )
        payload = json.loads(target.model_dump_json(exclude_none=exclude_none))
        payload.pop("success", None)
        return {"success": self.success} | payload

    @classmethod
    def from_payload(cls, payload: Any, *, strict: bool = False) -> Result:
        """Reconstruct a result from a wire payload — the inbound MCP half.

        Lenient by default and **never raises**: observations and errors
        validate per item, so one malformed row from a peer quarantines
        as a warning-severity ``vfs.internal`` entry (raw item preserved
        in ``data["vfs.quarantine"]``) instead of destroying its
        siblings; a malformed error quarantines at error severity (a
        failure fact was asserted, so the envelope must not silently
        succeed); a malformed envelope-level field quarantines as a
        warning with every validated item salvaged. A structurally
        hopeless payload returns a fatal ``vfs.internal`` result. Any ``success`` claim is ignored and
        re-derived — except the one reconciliation rule: a peer claiming
        failure with no classifiable error synthesizes a fatal
        ``vfs.internal`` entry carrying the claim in
        ``data["vfs.claim"]``. *strict=True* restores raise-on-invalid
        for tests.
        """
        if strict:
            return cls.model_validate(payload)
        try:
            if not isinstance(payload, Mapping):
                msg = f"payload is {type(payload).__name__}, not a mapping"
                return cls._hopeless(payload, msg)
            data = dict(payload)
            observations, errors = cls._validated_items(data)
            if data.get("success") is False and not any(e.is_fatal for e in errors):
                errors.append(
                    ResultError(
                        kind=VFSErrorKind.internal,
                        message="Peer payload claimed failure but carried no classifiable error",
                        data={"vfs.claim": {"success": False}},
                    )
                )
            try:
                return cls.model_validate(data | {"observations": observations, "errors": errors})
            except ValidationError as exc:
                errors.append(_quarantine(dict(data), exc, Severity.warning, "envelope fields"))
                return cls(observations=observations, errors=errors)
        except Exception as exc:  # the lenient boundary never raises
            return cls._hopeless(payload, str(exc))

    def to_json(self, *, exclude_none: bool = True) -> str:
        """JSON string — ``to_payload`` serialized."""
        return json.dumps(self.to_payload(exclude_none=exclude_none))

    def to_str(self, *, projection: tuple[str, ...] | list[str] | None = None) -> str:
        """Render to text via :func:`vfs.results.render.render_result`.

        *projection* selects Observation columns; ``None`` uses the
        function's default. Arrangement is function-specific.
        """
        return render_result(self, projection=projection)

    def __str__(self) -> str:
        """Delegate to ``to_str()`` for default text rendering."""
        return self.to_str()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _rolled_errors(self) -> list[ResultError]:
        """Group errors by (kind, severity, retryable); keep each head, roll each tail.

        ``retryable`` is part of the key and stamped on the rollup entry —
        the transient signal survives the boundary for every grouped error.
        """
        groups: dict[tuple[str, str, bool], list[ResultError]] = {}
        for e in self.errors:
            groups.setdefault((str(e.kind), str(e.severity), e.retryable), []).append(e)
        rolled: list[ResultError] = []
        for members in groups.values():
            head, tail = members[0], members[1:]
            rolled.append(head)
            if tail:
                sources = [str(e.source) for e in tail if e.source is not None]
                rolled.append(
                    ResultError(
                        kind=head.kind,
                        message=f"{len(tail)} more {head.kind} error(s) rolled up at the wire boundary",
                        severity=head.severity,
                        retryable=head.retryable,
                        data={"vfs.rollup": {"count": len(tail), "sources": sources}},
                    )
                )
        return rolled

    @classmethod
    def _validated_items(cls, data: dict[str, Any]) -> tuple[list[Observation], list[ResultError]]:
        """Per-item validation with quarantine — pops the item lists from *data*."""
        observations: list[Observation] = []
        errors: list[ResultError] = []
        raw_observations = data.pop("observations", None) or []
        raw_errors = data.pop("errors", None) or []
        if not isinstance(raw_observations, list):
            raw_observations = [raw_observations]
        if not isinstance(raw_errors, list):
            raw_errors = [raw_errors]
        for item in raw_observations:
            try:
                observations.append(Observation.model_validate(item))
            except Exception as exc:  # quarantine, never poison siblings
                errors.append(_quarantine(item, exc, Severity.warning, "observation"))
        for item in raw_errors:
            try:
                errors.append(ResultError.model_validate(item))
            except Exception as exc:  # quarantine, never poison siblings
                errors.append(_quarantine(item, exc, Severity.error, "error"))
        return observations, errors

    @classmethod
    def _hopeless(cls, payload: Any, reason: str) -> Result:
        """Fatal ``vfs.internal`` result for a structurally unusable payload."""
        return cls(
            errors=[
                ResultError(
                    kind=VFSErrorKind.internal,
                    message="Peer payload could not be parsed as a Result",
                    data={"vfs.quarantine": {"item": _clip(repr(payload)), "reason": _clip(reason)}},
                )
            ]
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_QUARANTINE_CLIP = 512  # bound raw peer junk carried in quarantine records


def _quarantine(item: Any, exc: Exception, severity: Severity, what: str) -> ResultError:
    """One quarantined payload item as a ``vfs.internal`` entry, raw item kept.

    The kept item is bounded by *serialized* size: an oversized or
    unserializable item is carried as a clipped string instead — hostile
    peer junk never rides the envelope unbounded.
    """
    raw: Any = item if isinstance(item, (dict, str, int, float, bool)) or item is None else repr(item)
    if isinstance(raw, str):
        raw = _clip(raw)
    else:
        try:
            serialized = json.dumps(raw)
        except (TypeError, ValueError):
            serialized = repr(raw)
        if len(serialized) > _QUARANTINE_CLIP:
            raw = _clip(serialized)
    return ResultError(
        kind=VFSErrorKind.internal,
        message=f"Quarantined malformed {what} from peer payload",
        severity=severity,
        data={"vfs.quarantine": {"item": raw, "reason": _clip(str(exc))}},
    )


def _clip(text: str) -> str:
    """Bound a string for a quarantine record."""
    return text if len(text) <= _QUARANTINE_CLIP else text[:_QUARANTINE_CLIP] + "…"
