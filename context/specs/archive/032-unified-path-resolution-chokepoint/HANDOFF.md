# HANDOFF — paths.py + tests (story 032)

This is the authoritative, confirmed task list for the **current pass**. Where it
conflicts with `design.md` or `vfspath-typed-handle.md`, **this doc wins** — it
records decisions made after those were written.

Read order: this file → `vfspath-typed-handle.md` (the type design) → `design.md`
(the chokepoint background). The repo is mid-refactor; **broken imports and a
non-collecting suite are expected** (see `CLAUDE.md`). Do not chase breakage outside
the scope below.

---

## Decisions (the "why", so you can make judgment calls)

1. **User-scoping is dropped.** The `/{user_id}` path-prefix scheme is being removed.
   Tenant isolation will instead come from a **permission layer over one global
   namespace** (the Unix model: an implementer makes `/users/{name}` and grants that
   principal access to that subtree). The permission system **does not exist yet** —
   what's in `permissions.py` today is static, principal-less mount rules
   (`check_writable` with no `user_id`, no `check_readable`). Building it is a
   **separate, later story**, not part of this pass.
   - Consequence for this pass: **delete** `scope_path` / `unscope_path` /
     `validate_user_id` from `paths.py`. This supersedes `design.md §3`'s scoping
     tier, `§5`'s scoping invariant, and `§7` open-question 1.
   - There is **no `ScopedPath` type.** `VFSPath` is the single path form.

2. **`VFSPath` validates by default; there is no `.parse` and no `mutation=` flag on
   the type.** Structural validity (canonical/legal) is the type's only concern.
   Write-target authorization (`check_mutable_path`) stays in `resolve_path(mutation=
   True)`, called by the router — never on the path type. (Rationale: four reference
   systems — Linux, Plan 9, FreeBSD, fsspec — all keep authorization separate from
   name handling; see `vfspath-typed-handle.md §2, §8`.)

3. **The gate canonicalizes; it does not reject non-canonical input.** `resolve_path`
   runs `normalize_path` *then* `validate_path`. So `VFSPath("/a/../b")` returns
   `VFSPath("/b")` and `VFSPath("rel")` returns `VFSPath("/rel")` — neither raises.
   It raises **only** on what `validate_path` rejects (null bytes, control chars,
   >255-char segment, >1024-char path). Get this right in the tests.

---

## Task 1 — `src/vfs/paths.py`

### 1a. Add the `VFSPath` type

Place it next to `ResolvedPath` / `resolve_path` (around line 331). `VFSPath.__new__`
calls `resolve_path`, and `resolve_path` mints a `VFSPath` (1b) — the mutual
reference is resolved at call time, so ordering within the module doesn't matter as
long as both exist at import. The property helpers (`split_path`, `compute_parent_*`,
`parse_kind`, `is_meta_root_path`, `check_mutable_path`) are all module-level and
already defined. `from __future__ import annotations` is already at the top, so
return annotations need no quotes.

```python
class VFSPath(str):
    """A path that has passed the gate: canonical, validated, safe to route.

    A ``str`` subclass — binds into SQL, f-strings, and dict keys unchanged. One
    constructor, ``VFSPath(value)``: it canonicalizes and validates through
    :func:`resolve_path` and raises ``ValueError`` only on a structurally invalid
    path (null byte, control char, over-long segment/path). Non-canonical input is
    *canonicalized*, not rejected: ``VFSPath("/a/../b") == "/b"``.

    Validates *structure only*. Whether a path is a legal write target is a
    separate concern in ``resolve_path(mutation=True)``, never on this type.

    Derived strings (slicing, ``+``, ``.lstrip``) return plain ``str`` — the badge
    is intentionally not inherited. Re-mint via ``parent_dir`` / ``parent_file`` /
    ``join`` / ``resolve_path`` when you need it back.
    """

    __slots__ = ()

    def __new__(cls, value: str) -> VFSPath:
        # Validate through the one gate; resolve_path mints the branded instance.
        resolved = resolve_path(value)
        if resolved.path is None:
            raise ValueError(resolved.error)
        return resolved.path

    @property
    def parent_dir(self) -> VFSPath:
        """Literal parent directory — same derivation as ``VFSEntry.parent_dir``."""
        return VFSPath(compute_parent_dir(self))

    @property
    def parent_file(self) -> VFSPath | None:
        """Owning file for a chunk/version/edge meta path, else ``None``.

        Same derivation as ``VFSEntry.parent_file``.
        """
        owner = compute_parent_file(self)
        return VFSPath(owner) if owner is not None else None

    @property
    def name(self) -> str:
        """Leaf segment (mirrors ``VFSEntry.name``)."""
        return split_path(self)[1]

    @property
    def kind(self) -> ObjectKind:
        """Structural kind from path markers (mirrors ``VFSEntry.kind``)."""
        return parse_kind(self)

    @property
    def is_meta(self) -> bool:
        """Whether this path is under the reserved ``/.vfs`` tree."""
        return is_meta_root_path(self)

    @property
    def is_mutable_target(self) -> bool:
        """Namespace-grammar half of writability — NOT a permission check.

        ``/`` and the ``/.vfs`` root are never mutable; inverse-edge paths never
        directly writable; meta endpoints and ordinary paths are. Use the function
        ``check_mutable_path`` when the rejection *reason* is needed.
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
            cls,
            core_schema.str_schema(),
        )
```

### 1b. Retype `resolve_path` to mint `VFSPath`

`ResolvedPath.path` (line 334) and the success return (line 355):

```python
class ResolvedPath(NamedTuple):
    path: VFSPath | None      # was: str | None
    error: str | None
```
```python
    # last line of resolve_path — brand directly; VFSPath(canonical) would recurse.
    return ResolvedPath(str.__new__(VFSPath, canonical), None)
```

Everything else in `resolve_path` stays: same signature, still never raises, still
returns `(path, error)`. `str`-treating callers are unaffected — `VFSPath` *is* a `str`.

### 1c. Delete the user-scoping section (lines ~532–589)

Remove all of it:
- the `# User scoping` comment header,
- `_UNSAFE_USER_ID_CHARS`,
- `validate_user_id`,
- `scope_path`,
- `unscope_path`,
- `_strip_user_prefix`.

**Keep `decompose_edge`** (lines ~509–529) — it is *not* scoping; `check_mutable_path`
uses it (line 317). Keep everything else in the file as-is.

### Expected breakage (do NOT fix in this pass)

Deleting the scoping functions breaks these importers — this is the leading edge of a
coordinated scoping rip-out that is **out of scope here**:

- `src/vfs/results.py:29` — `from vfs.paths import ... unscope_path` (used `:415`)
- `src/vfs/backends/database.py:62,64` — imports `scope_path`, `validate_user_id`
  (≈20 call sites: `_scope_path`, the LIKE patterns, edge scoping)
- `src/vfs/backends/postgres.py:31` and `mssql.py:40` — import `scope_path`

`backends/database.py` is *already* broken (it imports `validate_mutation_path`, which
was renamed to `check_mutable_path` — see `design.md §8` step 2, also unfinished).
Both are expected. Leave them for the coordinated teardown + the `check_mutable_path`
rename pass.

---

## Task 2 — tests in `tests/`

`pyproject.toml` has `testpaths = ["tests"]`. Write **`tests/test_paths.py`**.

**Critical:** import **only from `vfs.paths`**. Do not import `vfs.backends`,
`vfs.models`, fixtures, or anything that pulls in the broken backend import — keep the
file self-contained so it collects and runs despite the rest of the tree being broken.
`vfs.paths` itself imports only `posixpath` / `unicodedata` / `typing`, so it loads
clean.

`tests2/test_paths.py` is the **old** version — useful as a reference for the pure
functions, but it is broken (imports the deleted `api_path`, uses the old
`validate_mutation_path` name) and lives in the wrong dir. Port the still-valid cases
into `tests/test_paths.py`; drop the `api_path` cases; rename
`validate_mutation_path` → `check_mutable_path`.

Run with:
```
uv run python -m pytest tests/test_paths.py -q
```

### Coverage checklist

- **`normalize_path`** — idempotent; NFC-folds; absolutizes (`"rel"` → `"/rel"`);
  collapses `.`/`..`/`//`; `""` → `"/"`.
- **`validate_path`** — rejects null byte, control chars (U+0001–U+001F, U+007F,
  U+0080–U+009F), >1024-char path, >255-char segment; accepts `"/"`. (Expects an
  already-normalized path.)
- **`check_mutable_path`** — `/` rejected; `/.vfs` root rejected; chunk/version paths
  ok; `edges/out` ok; `edges/in` (inverse) rejected; reserved meta directories ok;
  arbitrary `/.vfs/...` content rejected.
- **`resolve_path`** — valid → `ResolvedPath(VFSPath, None)` and
  `isinstance(result.path, VFSPath)`; invalid → `(None, reason)`; `mutation=True`
  applies `check_mutable_path` (e.g. `resolve_path("/", mutation=True).path is None`);
  never raises.
- **`VFSPath`** — see Decision 3:
  - `VFSPath("/a/b") == "/a/b"` and `isinstance(..., str)`;
  - `VFSPath("/a/../b") == "/b"`, `VFSPath("rel") == "/rel"` (canonicalized, **no
    raise**);
  - raises `ValueError` on `"/a\x00b"`, a control char, a 256-char segment, a
    1025-char path;
  - `type(VFSPath("/a/b")[1:]) is str` (badge drops on derived strings);
  - properties: `parent_dir`, `parent_file` (None for plain file/dir; the owning file
    for a chunk/version/edge path), `name`, `kind`, `is_meta`, `is_mutable_target` —
    each equals its `paths.py` helper on the same input;
  - `VFSPath("/a").join("b", "c") == "/a/b/c"`; sanity-check no infinite recursion.
- **`parse_kind` / constructors / `decompose_edge`** — port existing cases from
  `tests2/test_paths.py` (chunk/version/edge round-trips, `meta_root`, etc.). Note the
  `api`/`apis` kind was removed — drop those cases.

---

## Out of scope (later stories / passes) — for context only

- **Scoping rip-out** across `results.py` + `database.py`/`postgres.py`/`mssql.py`
  (delete the now-broken scope/unscope call sites). One coordinated pass.
- **Permission layer** (the replacement for scoping) — its own story; the hard part is
  permission-filtered *enumeration* (`ls`/`glob`/`grep`) pushed into SQL, default-deny,
  subtree grants. See the session notes / ask the lead.
- **`check_mutable_path` rename fallout** — update `database.py:63` import + `:1852`
  call from `validate_mutation_path`.
- **`api` kind cleanup** — `models.py:671` and `query/parser.py:902` still reference
  `"api"`; paths.py side is already done.
- **`VFSPath` rollout steps 3–4** (`vfspath-typed-handle.md §9`) — annotate the router
  (`base2.py`) with `path: VFSPath`; have the meta-path constructors return `VFSPath`.
- **`VFSEntry.path` stays `str`** — see `vfspath-typed-handle.md §5` (SQLModel
  `table=True` skips validators; ORM column-inference risk). Do not retype it.

## Definition of done (this pass)

- `paths.py`: `VFSPath` added, `resolve_path`/`ResolvedPath` mint it, scoping
  functions deleted.
- `import vfs.paths` succeeds; `from vfs.paths import VFSPath, resolve_path` works.
- `uv run python -m pytest tests/test_paths.py -q` passes, covering the checklist.
- No attempt made to fix the backend/`results.py` breakage (expected).
