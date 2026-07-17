# `VFSPath` — a typed handle for canonical paths

*A companion to [`design.md`](./design.md). The chokepoint (`resolve_path`) makes
path canonicalization happen in **one place at runtime**. This proposal adds a
**type** that lets the rest of the codebase *prove*, statically, that a path it
holds has already been through that place. The gate is the door; `VFSPath` is the
stamp the door puts on what passes. Every `file:line` was read against the tree
(`src/vfs/paths.py`, `src/vfs/models.py`, `src/vfs/base2.py`).*

> **Status (2026-06):** implementation handed off — see **`HANDOFF.md`** for the
> exact, confirmed task list. Two design decisions postdate the body below and
> override it where they conflict: (1) the constructor **validates by default**,
> there is no `.parse` and no `mutation=` flag on the type (already reflected); and
> (2) **user-scoping is dropped** — there is no `ScopedPath`; `VFSPath` is the single
> path form (§8 updated; the rest of any scoped-form discussion is moot).

---

## 1. The problem this solves (and the one it doesn't)

`design.md §2` names three forms a path takes — **raw**, **canonical**, **scoped**
— and gives the chokepoint one job: keep the conversions in one place. After the
gate lands, the invariant in `§2 rule 1` is real but **invisible**:

> Downstream code may assume any path it holds is already canonical and never
> re-normalize defensively.

That "may assume" is a comment, not a guarantee. Nothing stops a future function
from being handed a raw string and routing it un-normalized; nothing tells a reader
of `_resolve_terminal` whether its `path` argument has been through the gate or not.
The chokepoint enforces validity at *the boundary it passed through*; it does not
make validity a property of *the object that travels*.

`VFSPath` closes that gap for the **canonical** form only. It is a `str` subclass
that, by construction, means "this passed the gate." It deliberately does **not**
try to type the *scoped* form or *authorization* — those are separate axes (`§9`).

## 2. The core decision: the constructor validates

The type's promise is "if you hold a `VFSPath`, it passed the gate." For that
promise to hold, **the obvious, discoverable constructor must be the safe one.**
`VFSPath(value)` runs the full gate and raises on rejection — there is no normal way
to mint an un-validated `VFSPath`. The dangerous shortcut should never be the path of
least resistance; here it simply does not exist in the public API.

This does **not** re-fuse the three concerns `design.md §6` split (D1/D3). The pure
functions stay separate — `normalize_path`, `validate_path`, `check_mutable_path`
are untouched and still independently callable. `__new__` does not re-implement them;
it *delegates to `resolve_path`*, the same composer the router uses. The chokepoint
stays the one place validation logic lives; the constructor is just a second *caller*
of it that happens to raise instead of returning a result.

One constructor, plus the non-raising gate — the same *structural* validation reached
through two error channels:

| constructor | validates | error channel | use where |
|---|---|---|---|
| `VFSPath(value)` | structure only (normalize + `validate_path`) | raises `ValueError` | any raising boundary: Pydantic field, mount setup |
| `resolve_path(value, *, mutation=...)` | structure, **plus** the write-target check when `mutation=True` | **never raises**; returns `ResolvedPath` | the router boundary |

`VFSPath` validates **structure and nothing else**. Write-target authorization
(`check_mutable_path`: may anyone write at this path in the namespace grammar?) is a
*separate concern* (`design.md §6` D1) and lives only in `resolve_path(mutation=True)`,
which the router calls and whose decision it consumes immediately. There is
deliberately **no** `VFSPath` constructor that takes a `mutation` flag — being a
`VFSPath` says a path is structurally legal, never that it is a legal write target.
`/.vfs` is a valid `VFSPath` and an illegal write target at the same time (§8).

`VFSPath(...)` and the non-raising `resolve_path` are the same structural validation
through two doors: callers that need an exception (Pydantic, mount setup) construct
directly; the router, which must turn rejection into a `VFSResult` (`design.md §4`),
uses `resolve_path`. Neither re-validates the other's work — §3.2 shows the single
internal brand step that keeps it to one validation.

> **One deferred cost, named honestly.** Because every `VFSPath(...)` validates,
> wrapping storage rows that are *already* canonical (`VFSPath(row.path)` in a query
> loop) re-runs the gate it doesn't need. For now that cost is accepted — correctness
> over speed. If profiling ever shows it matters, the answer is a single, explicitly
> named, greppable escape hatch (`VFSPath.trusted(...)`), added then and reviewed as
> the one unchecked mint site — deliberately **out of scope here**.

## 3. Proposed code

### 3.1 The type (`src/vfs/paths.py`, beside `resolve_path` / `ResolvedPath`)

```python
class VFSPath(str):
    """A path that has passed the gate: canonical, validated, safe to route.

    A ``str`` subclass, so it binds into SQL, f-strings, and dict keys with no
    adaptation.  One constructor, ``VFSPath(value)``: it runs the structural
    gate and raises ``ValueError`` on rejection.  There is no way to mint an
    un-validated ``VFSPath`` through the public API.

    It validates *structure only* — canonical, absolute, legal characters and
    lengths.  Whether a path is a legal *write target* is a separate concern
    that lives in ``resolve_path(mutation=True)``, not on this type: being a
    ``VFSPath`` never implies "you may write here."

    Derived strings (slicing, ``+``, ``.lstrip``) return plain ``str`` — the
    "validated" badge is deliberately not inherited, because a derived path is
    not necessarily still canonical.  Re-mint through ``parent_dir`` /
    ``parent_file`` / ``join`` / ``resolve_path`` when you need the badge back.

    The read-only properties — ``parent_dir``, ``parent_file``, ``name``,
    ``kind``, ``is_meta``, ``is_mutable_target`` — are pure functions of the path
    string, each delegating to the same ``paths.py`` helper the model uses, so a
    path and its stored ``VFSEntry`` always agree.  None of them imply
    authorization: ``is_mutable_target`` is the namespace-grammar half only (see
    its docstring).
    """

    __slots__ = ()

    def __new__(cls, value: str) -> VFSPath:
        # Validate through the one gate; resolve_path mints the branded instance.
        # Structure only — no mutation/write-target check (that is resolve_path's).
        resolved = resolve_path(value)
        if resolved.path is None:
            raise ValueError(resolved.error)
        return resolved.path

    @property
    def parent_dir(self) -> VFSPath:
        """The literal parent directory — same derivation as ``VFSEntry.parent_dir``."""
        return VFSPath(compute_parent_dir(self))

    @property
    def parent_file(self) -> VFSPath | None:
        """Owning file for a chunk/version/edge meta path, else ``None``.

        Same derivation as ``VFSEntry.parent_file``: chunks, versions, and edges
        resolve to the file they hang off under ``__meta__``; plain files and
        directories have no parent file.
        """
        owner = compute_parent_file(self)
        return VFSPath(owner) if owner is not None else None

    @property
    def name(self) -> str:
        """The leaf segment (mirrors ``VFSEntry.name``)."""
        return split_path(self)[1]

    @property
    def kind(self) -> str:
        """Structural kind inferred from path markers (mirrors ``VFSEntry.kind``).

        ``file`` / ``directory`` / ``chunk`` / ``version`` / ``edge``.
        """
        return parse_kind(self)

    @property
    def is_meta(self) -> bool:
        """Whether this path lives under the reserved ``/.vfs`` metadata tree."""
        return is_meta_root_path(self)

    @property
    def is_mutable_target(self) -> bool:
        """Whether the namespace grammar permits writes at this path at all.

        The path-intrinsic half of writability: ``/`` and the ``/.vfs`` root are
        never mutable; inverse-edge paths are never directly writable; meta
        endpoints and ordinary paths are.  NOT a permission check — whether a
        given caller may write (op, principal, mount) is ``check_writable``.  Use
        the function ``check_mutable_path`` when the rejection *reason* is needed.
        """
        ok, _ = check_mutable_path(self)
        return ok

    def join(self, *parts: str) -> VFSPath:
        """Join and re-canonicalize through the gate (parts may add ``..``)."""
        return VFSPath(posixpath.join(self, *parts))

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        # Validate-and-coerce at model boundaries; serialize back to a plain str.
        from pydantic_core import core_schema

        return core_schema.no_info_after_validator_function(
            cls,                          # VFSPath(value): structural validation
            core_schema.str_schema(),
        )
```

`__new__` delegates to `resolve_path`, and `resolve_path` mints the instance with a
bare `str.__new__` (§3.2) — *not* by calling `VFSPath(...)` again, which would
recurse. That one low-level brand is the only construction that bypasses the gate,
and it runs *inside* the gate, immediately after validation succeeds. It is not
public API, so no caller can reach an un-validated `VFSPath`.

### 3.2 The one gate change — `resolve_path` mints the brand

So the type and the gate share exactly one validation path: the gate is the only
code that turns a raw string into a `VFSPath`. It mints with `str.__new__` — the
single in-gate brand step, reached only *after* validation has succeeded, and the
reason `VFSPath.__new__` can safely delegate back to `resolve_path` without recursing.

```python
class ResolvedPath(NamedTuple):
    path: VFSPath | None      # was: str | None
    error: str | None


def resolve_path(path: str, *, mutation: bool = False) -> ResolvedPath:
    canonical = normalize_path(path)
    valid, reason = validate_path(canonical)
    if not valid:
        return ResolvedPath(None, reason)
    if mutation:
        ok, reason = check_mutable_path(canonical)
        if not ok:
            return ResolvedPath(None, reason)
    # Brand the validated string directly; VFSPath(canonical) would re-enter the gate.
    return ResolvedPath(str.__new__(VFSPath, canonical), None)
```

Nothing else about the gate changes: same signature, still never raises, still
returns `(path, error)`. Callers that treat `.path` as a `str` keep working —
`VFSPath` *is* a `str`.

## 4. Where the type threads through the four fundamentals

The rule of placement: **`VFSPath` goes where a path is produced and flows as a
value, not where it is an ORM column.** Validity here is enforced on the write path
(the gate + the model's before-validator), and the type should mark that path.

- **paths** — `resolve_path` mints `VFSPath` (§3.2). The meta-path constructors
  (`chunk_path`, `version_path`, `edge_out_path`) build canonical strings, so they
  can return `VFSPath(...)` to brand machine-authored paths — a re-validation that is
  cheap and one-shot at construction (not in a hot loop).
- **base** — `_route_single` already does `path = resolved.path`; that local is now
  statically a `VFSPath`. Annotating `_resolve_terminal` / `_group_candidates_by_terminal`
  with `path: VFSPath` turns `design.md §2 rule 1` from prose into a type fact: a
  function that takes `VFSPath` is *documented and checked* to receive only gated
  paths, and can drop any defensive re-normalization.
- **models** — see §5. The field stays `str`.
- **database** — rows read back are known-canonical, but they still re-enter through
  the validating `VFSPath(row.path)` (the deferred cost noted in §2; a `trusted`
  escape hatch is intentionally not added yet). SQL binding is unaffected —
  `self._model.path == path` and `.like(...)` see a `str`.

## 5. Why `VFSEntry.path` stays `str`

The tempting change — `VFSEntry.path: VFSPath` (`models.py:128`) — is the **weakest**
placement in this repo, for three model-specific reasons:

1. **`table=True` subclasses skip validators.** The note at `models.py:619` says it:
   *table=True ctors skip validators.* `VFSEntry` (`:93`, table=False) is the
   validating base; each mount mints a private `table=True` subclass (`:102`, `:823`)
   that bypasses Pydantic validation on `__init__`. A field-level `VFSPath`
   coercion rides that same machinery, so on the class that actually stores it
   **wouldn't run** — and on DB hydration SQLAlchemy populates attributes directly,
   handing back a plain `str`. The annotation would claim `VFSPath` while the runtime
   value is `str` exactly at the read seam. A type that lies is worse than no type.
2. **The real work is in `_normalize_and_derive` (`models.py:643`), and the type
   can't absorb it.** That `mode="before"` validator normalizes `path` and then
   derives `name`, `parent_dir`, `parent_file`, and infers `kind` *from the canonical
   form*. A before-validator runs *before* field coercion and still needs to
   normalize itself to derive the siblings — so a `VFSPath` field is mostly redundant
   with work the validator already does. Nothing gets deleted.
3. **SQLAlchemy column-type inference is a live risk.** The annotation drives the SA
   column type through `SQLModelMetaclass` (`models.py:37`). A `str` subclass may map
   to `VARCHAR` cleanly or may force an explicit `sa_type=String` — and with
   `table=True` minting done in a custom metaclass, that has to be *verified to even
   class-define*, not assumed.

The invariant "stored paths are canonical" is already guaranteed by the model's
before-validator and the write-path gate. Retyping the column adds ORM risk and a
guarantee the storage class won't honor. Leave it `str`; put the type on the gate
output and the router values, where the enforcement actually is.

## 6. Alternatives considered

| approach | runtime guarantee | `isinstance` distinct? | why not |
|---|---|---|---|
| **`Annotated[str, AfterValidator(...)]`** | inside Pydantic only | no | validates at a boundary, creates no travelling type; nothing holds outside a model |
| **`NewType("VFSPath", str)`** | none | no | pure static fiction; zero runtime check, so no invariant at all |
| **trusting `__new__`** | weak — forgeable by accident | yes | the obvious constructor mints un-validated paths; the type's promise is only as good as caller discipline (the smell that prompted this revision) |
| **validating `__new__`** *(proposed)* | strong — every public mint is gated | yes | re-validates known-canonical storage rows (the §2 deferred cost) and the `str`-subclass-returns-`str` caveat — both acceptable |

The `str` subclass is the only option that makes validity a property of the
*object* rather than the *boundary*. Routing all public construction through the gate
is what makes that property trustworthy rather than aspirational.

## 7. The known caveat

String methods return plain `str`, not `VFSPath`: `p.lower()`, `p[1:]`, `p + "x"`,
`p.lstrip("/")` all drop the badge. This is *wanted* — a sliced or concatenated path
isn't necessarily still canonical, so it shouldn't silently keep the stamp. When a
derived path must stay branded, go through `parent_dir` / `parent_file` / `join`
(which re-mint) or back through `resolve_path`. Document it loudly so no one expects
the badge to survive arithmetic.

## 8. What this deliberately leaves out

- **Scoping — dropped entirely (decision, 2026-06).** User-path scoping
  (`/{user_id}` prefixing) is being removed; tenant isolation moves to a permission
  layer over one global namespace (the Unix model — see `HANDOFF.md §Decisions`).
  There is therefore **no `ScopedPath`**, and `VFSPath` is the **single** path form
  (raw → canonical, full stop). `scope_path` / `unscope_path` / `validate_user_id`
  are deleted from `paths.py`. This supersedes `design.md §3`'s scoping tier and
  `§7` open-question 1.
- **Authorization.** `mutation=` write-target rules stay in `check_mutable_path` /
  the gate. `VFSPath` means "structurally a valid canonical path," never "you may
  write here" — separate concerns (`design.md` D1). `/.vfs` is a valid `VFSPath` and
  an illegal write target at the same time.

## 9. Rollout

Each step is independently landable and rides the same invariant.

- **Step 1 — `resolve_path` mints `VFSPath`** via `str.__new__` (§3.2) and
  `ResolvedPath.path` retypes to `VFSPath | None`. The gate is the one validation
  site, so the type comes first. Pure type change; existing `str`-treating callers
  unaffected.
- **Step 2 — add the `VFSPath` type** (validating `__new__`; the `parent_dir`,
  `parent_file`, `name`, `kind`, `is_meta`, `is_mutable_target` properties; `join`;
  pydantic hook). Test: the gate **canonicalizes**, it does not reject non-canonical
  input — `VFSPath("/a/../b") == "/b"` and `VFSPath("rel") == "/rel"`; it raises only
  on what `validate_path` rejects (`VFSPath("/a\x00b")`, control chars, a >255-char
  segment, a >1024-char path); `isinstance(VFSPath("/a"), str)` is `True`; derived
  strings (`p[1:]`, `p + "x"`) are plain `str`; `VFSPath(...)` does not recurse; each
  property matches its `paths.py` helper and the corresponding `VFSEntry` field.
  Write-target rejection stays tested on `resolve_path(mutation=True)`, not the type.
- **Step 3 — annotate the router** (`_route_single`, `_resolve_terminal`,
  `_group_candidates_by_terminal`) with `path: VFSPath`; drop any defensive
  re-normalization the type now proves unnecessary.
- **Step 4 — brand the meta-path constructors** (`chunk_path` / `version_path` /
  `edge_out_path` return `VFSPath`) and wrap storage-row reads as `VFSPath(row.path)`
  (re-validating for now; §2).
- **Deferred — `VFSEntry.path`** stays `str` (§5) unless and until the `table=True`
  validation story changes; revisit only with an empirical check that SA column
  inference accepts the subclass.
- **Deferred — `VFSPath.trusted(...)`** the unchecked escape hatch for hot read
  loops, added only if profiling demands it (§2); out of scope here.
