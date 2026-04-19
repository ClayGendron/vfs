# Directory-Level Permissions on a Mount

**Status:** Design proposal — not yet implemented
**Authors:** Clay Gendron + Claude
**Builds on:** §15.17 of `everything_is_a_file.md` (mount-level permissions, commit `59a5765`), §8.2 (LLM Wiki mapping)

---

## 1. Goal

Today a Grover filesystem is either entirely `"read"` or entirely `"read_write"`. The check is mount-wide, lives on the `GroverFileSystem` instance, and is enforced through `check_writable` at five chokepoints in `base.py`.

This proposal adds **directory-level overrides on top of the same mount-wide default**, in either direction:

- A read-only mount that exposes one or more writable subtrees (the LLM Wiki case in §8.2: `/wiki` is read by default, `/wiki/synthesis` is writable so the agent can file new pages back into it).
- A read-write mount that protects one or more subtrees as immutable (a user's workspace mount where `/workspace/.frozen` cannot be touched).

The override is **mount-wide configuration**, not a per-user ACL, not a share, not ReBAC. It moves with the filesystem instance and applies to every caller.

Success criteria:

1. The simple cases (`permissions="read"` and `permissions="read_write"`) work exactly as today — no breakage, no new boilerplate for users who don't need the feature.
2. A single new value type covers the override case in both directions, with one declaration site, type-checked at construction time.
3. Resolution is unambiguous, prefix-aware, and matches conventions Grover already uses elsewhere (longest-prefix match is what mount routing already does).
4. The five existing chokepoints stay the only enforcement points. No new routing surface, no new exception class, no new permission states.
5. Path-aware checks compose cleanly with the candidate-batched and object-batched chokepoints — those currently check at the mount level and need to be tightened to per-path.

---

## 2. Prior art

I surveyed how other systems express "default permission with a list of path-prefix exceptions" so the abstraction Grover lands on is one users can already reason about:

| System | Shape | Notes |
|---|---|---|
| **AWS S3 / IAM** | Statements with `Resource` ARNs containing prefixes (`arn:aws:s3:::bucket/uploads/*`) and explicit `Effect: Allow` / `Effect: Deny`. Explicit `Deny` always wins; otherwise any matching `Allow` grants. | Powerful but surprising — there is no "longest prefix wins", and the dual-direction (`Allow` + `Deny`) introduces overlap reasoning. Good for fine-grained policy, bad for "I just want one writable hole in a read-only mount". |
| **Git sparse-checkout (cone mode)** | A list of directory prefixes; everything inside a listed cone is included. Cone mode exists specifically because the older non-cone glob mode was too expressive and too slow. | The lesson is that **restricting expressiveness to directory prefixes makes the matching algorithm O(M) instead of O(M·N)** and the user model an order of magnitude clearer. Grover should follow the cone-mode posture: directory prefixes only, no globs. |
| **NFS exports / OverlayFS** | Per-export `ro`/`rw` flag, plus bind mounts of read-write directories underneath a read-only export. The read-only-with-writable-hole pattern is achieved by **mounting separate filesystems**, not by an in-export rule list. | Grover already supports this via `add_mount` — but every "writable hole" being a separate mount means a separate engine, a separate graph, and a separate analyzer pipeline. That is far too heavy for the LLM Wiki use case where `/wiki/raw` and `/wiki/synthesis` should share a single graph and a single search index. **In-mount rules are the right abstraction; cross-mount composition is the wrong one.** |
| **Linux fapolicyd / firewall prefix lists / BGP route maps** | Default action plus longest-prefix-match override list. Order-independent, deterministic, well-understood. | This is the model Grover should adopt. It is the same algorithm that mount routing already uses. |
| **Claude Code `sandbox.filesystem.allowWrite` / `denyWrite`** | Two parallel lists, merged across scopes. | This was actively considered and rejected — see §3.2. The two-list approach is more expressive but harder to reason about; it makes it possible to write conflicting rules and then have to define which list wins. |
| **Plan 9 / 9P** | Permissions are part of the file metadata; mounts are dependency injection. | Grover already takes the Plan 9 view that mounts compose namespaces; this proposal extends it without violating that model — rules live on the filesystem instance, not on the parent router. |

**Convergent conclusion across the prior art:** the cleanest, most predictable shape is **one default + an ordered list of (path prefix → permission) overrides, resolved by longest-prefix match**. That's what Grover should ship.

---

## 3. Design decisions

### 3.1 Default + overrides, longest prefix wins

A filesystem has one default permission and zero or more overrides. Each override is `(path_prefix, permission)`. To resolve a path:

1. Find the override whose prefix is the longest prefix of the requested path (using normalized path segments).
2. If one matches, use that override's permission.
3. Otherwise, use the default.
4. Then apply the existing `MUTATING_OPS` check.

This is the same algorithm as `_match_mount` in `base.py:124`. Reusing the same shape means users learn one mental model for "how Grover routes paths" and it covers both mounts and permissions.

### 3.2 Rejected: parallel allow / deny lists

Claude Code's `allowWrite` / `denyWrite` shape was the obvious alternative. I rejected it because:

- It needs a precedence rule (which list wins on overlap?) and that precedence is invisible at the call site.
- It can't represent both directions symmetrically without tying the user's brain in knots — "this mount is read-only except `/synthesis`" is one statement in the longest-prefix model and two-overlapping-rules in the allow/deny model.
- It encourages partial-permission states (a path that is in `allowWrite` but also in a parent `denyRead`), which Grover does not have a use for and which would require introducing read-permission gating that doesn't exist today.

The longest-prefix model degenerates to `[]` for the simple case and grows linearly with the number of carve-outs. The allow/deny model is always a 2D matrix.

### 3.3 Rejected: globs

Glob patterns (`/wiki/raw/**/*.md`) are tempting and would let users say things like "everything in raw is read-only except markdown drafts". Rejected because:

- The git sparse-checkout cone mode story is a cautionary tale. Glob matching is `O(N·M)` and the patterns become opaque to users very quickly.
- Grover already has a glob-based query path (`g.glob()`) for **content** queries. Permission rules are a different concern; conflating them invites confusion.
- The whole point of "directory-level permissions" is that they live at directory boundaries. If a use case really needs file-level granularity, it belongs in shares / ReBAC (§13.11 of `everything_is_a_file.md`), not in mount config.

If a future iteration ever needs glob support, it can be layered on top of the prefix model — the chokepoint will still be `check_writable`. The reverse (starting with globs and trying to make them feel like prefixes) is much harder.

### 3.4 Rules are relative to the filesystem, not the router

A critical question: when a user mounts `DatabaseFileSystem` at `/wiki`, are the override paths written as `/synthesis` (relative to the filesystem's own root) or `/wiki/synthesis` (the absolute router-side path)?

**Decision: relative to the filesystem.** Reasons:

- The filesystem doesn't know what mount path it lives at. It can be unmounted, remounted at a different path, or mounted at multiple paths simultaneously. Storing absolute router-side paths inside the filesystem would couple the two.
- It mirrors how the existing storage works: `_*_impl` methods receive the rebased `rel` path, not the full `path`. Rules should live in the same coordinate system.
- It mirrors Unix: the permissions on `/etc/passwd` say `"/etc/passwd"` regardless of which mountpoint the rootfs happens to be mounted under in a chroot.

This means the routing layer must call `check_writable(fs, op, rel)` — the rebased relative path — not the full virtual path. This is a one-call-site change in `_route_single`, `_route_two_path`, and `mkconn`. (`_route_write_batch` and `_dispatch_candidates` already need restructuring per §6.3 anyway.)

### 3.5 Rules apply to descendants by prefix containment

`/synthesis` matches `/synthesis`, `/synthesis/foo.md`, and `/synthesis/2026/draft.md`, but not `/synthesis-archive` (no shared segment boundary). Match is `path == prefix` or `path.startswith(prefix + "/")` — same form as `_match_mount`.

Metadata children (`/file.py/.chunks/x`, `/file.py/.versions/3`, `/file.py/.connections/imports/util.py`) are matched as descendants of the file, which is the desired behavior — chunking and versioning of a read-only file are themselves mutations and should be rejected.

### 3.6 Backwards compatibility

The string forms `permissions="read"` and `permissions="read_write"` continue to work and mean exactly what they mean today. The new shape is opt-in. Every existing test passes unchanged. The new feature adds one type, one helper module, and a tightening of two chokepoints.

### 3.7 Per-instance scope and the shared-engine caveat

Same as today: rules live on the filesystem instance, not on the engine. The `TestSharedEngineIsNotIsolated` pin in §15.17 still holds — directory-level rules are subject to the same Unix-block-device caveat.

---

## 4. Data model

A single new value type, `PermissionMap`, in `src/grover/permissions.py`:

```python
from dataclasses import dataclass, field
from typing import Literal

Permission = Literal["read", "read_write"]


@dataclass(frozen=True, slots=True)
class PermissionMap:
    """Default permission plus directory-prefix overrides.

    Resolves a path to a Permission via longest-prefix match against
    the override list, falling back to ``default``.

    All override paths are normalized at construction time and stored
    in descending length order so resolution is a single pass.
    """

    default: Permission
    overrides: tuple[tuple[str, Permission], ...] = ()

    def __post_init__(self) -> None:
        # validate + normalize each override path
        normalized: list[tuple[str, Permission]] = []
        seen: set[str] = set()
        for raw_path, perm in self.overrides:
            path = normalize_path(raw_path)
            if path == "/":
                msg = "PermissionMap override path must not be '/' — use 'default' instead"
                raise ValueError(msg)
            if path in seen:
                msg = f"Duplicate override path: {path!r}"
                raise ValueError(msg)
            seen.add(path)
            normalized.append((path, validate_permission(perm)))

        # longest-prefix-first ordering for O(N) resolution
        normalized.sort(key=lambda kv: len(kv[0]), reverse=True)
        object.__setattr__(self, "overrides", tuple(normalized))
        object.__setattr__(self, "default", validate_permission(self.default))

    def resolve(self, path: str) -> Permission:
        """Resolve *path* to a Permission via longest-prefix match."""
        normalized = normalize_path(path)
        for prefix, perm in self.overrides:
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return perm
        return self.default
```

The `Permission` literal stays. The internal field `_permissions` on `GroverFileSystem` becomes `_permission_map: PermissionMap` (or stays as `_permissions` and just changes type — see §6.1).

---

## 5. Public API and DX

### 5.1 The simple case is unchanged

```python
DatabaseFileSystem(engine=engine, permissions="read")
DatabaseFileSystem(engine=engine, permissions="read_write")  # default
```

These continue to work. Internally, a string is normalized to `PermissionMap(default=..., overrides=())`.

### 5.2 The override case — three idioms

The constructor accepts `Permission | PermissionMap`. Three equivalent forms exist for the override case, ranked by what the use case calls for:

**Form A — `read_only` / `read_write` factory helpers (recommended for the common case):**

```python
from grover import permissions

# LLM Wiki: read-only by default, /synthesis is writable
fs = DatabaseFileSystem(
    engine=engine,
    permissions=permissions.read_only(write=["/synthesis"]),
)

# Workspace: writable by default, /workspace/.frozen is immutable
fs = DatabaseFileSystem(
    engine=engine,
    permissions=permissions.read_write(read=["/.frozen"]),
)
```

The factory takes the *opposite* permission's exception list because that's how users naturally describe the carve-out: "read-only with these writable holes" or "writable with these frozen holes". The keyword (`write=` / `read=`) names what the carve-outs grant, not what the default forbids — that reads more naturally.

These desugar to:

```python
permissions.read_only(write=["/synthesis"])
# == PermissionMap(default="read", overrides=(("/synthesis", "read_write"),))

permissions.read_write(read=["/.frozen"])
# == PermissionMap(default="read_write", overrides=(("/.frozen", "read"),))
```

**Form B — explicit `PermissionMap` (recommended when nesting matters):**

```python
fs = DatabaseFileSystem(
    engine=engine,
    permissions=PermissionMap(
        default="read",
        overrides=(
            ("/wiki/synthesis", "read_write"),
            ("/wiki/synthesis/.archive", "read"),  # nested override
        ),
    ),
)
```

This is the only form that supports nested overrides (a writable region inside an otherwise-writable region inside a read-only default). Most users will not need it.

**Form C — dict shorthand on the constructor (sugar for form B):**

```python
fs = DatabaseFileSystem(
    engine=engine,
    permissions={"default": "read", "/synthesis": "read_write"},
)
```

A dict with a `"default"` key is parsed as a `PermissionMap`. I'm proposing this **but flagging it as optional** — the factory helpers (form A) cover 95% of cases more readably, and supporting dicts adds a small parser. Skip if it doesn't carry weight.

### 5.3 Error messages

When a rule rejects a write, the error should make the rule visible:

- Current (mount-level): `"Cannot write to read-only mount: /wiki/raw/foo.md"`
- New (rule-level): `"Cannot write to read-only path '/wiki/raw/foo.md' (read-only by mount rule '/raw')"`

The classification substring `"Cannot write"` stays load-bearing on `WriteConflictError` so no exception-class plumbing changes. (Integrity finding #3 from §15.17 — the substring brittleness — is unchanged by this proposal but should be addressed in the same iteration if we touch this code.)

### 5.4 Worked example: the LLM Wiki mount

The §8.2 mapping table becomes:

```python
from grover import Grover, DatabaseFileSystem, permissions

g = Grover()

wiki = DatabaseFileSystem(
    engine_url="sqlite+aiosqlite:///wiki.db",
    permissions=permissions.read_only(write=["/synthesis", "/index.md", "/log.md"]),
)
await g.add_mount("/wiki", wiki)

# These succeed:
await g.write("/wiki/synthesis/auth-overview.md", "...")
await g.mkconn("/wiki/synthesis/auth-overview.md", "/wiki/raw/rfc-7519.pdf", "references")
await g.edit("/wiki/index.md", old="- old", new="- new")

# These fail with WriteConflictError:
await g.write("/wiki/raw/rfc-7519.pdf", "...")  # /raw is not in the writable set
await g.delete("/wiki/raw/rfc-7519.pdf")
await g.mkdir("/wiki/raw/new-dir")
```

Note that `mkconn` from a writable synthesis page **to** a read-only raw page is allowed because the connection physically lives on the source side (the source's `.connections/` namespace is what gets mutated). This matches the existing `mkconn` chokepoint, which checks the source filesystem.

---

## 6. Implementation plan

### 6.1 `permissions.py` — add `PermissionMap` and update `check_writable`

- Add the `PermissionMap` dataclass from §4.
- Add a `coerce_permissions(value: Permission | PermissionMap | dict) -> PermissionMap` helper called from `validate_permission` (or rename `validate_permission` to `coerce_permissions` and have it return a `PermissionMap`).
- Add `permissions.read_only(*, write: list[str] = ...) -> PermissionMap` and `permissions.read_write(*, read: list[str] = ...) -> PermissionMap` factory helpers.
- Update `check_writable(fs, op, path)` to call `fs._permission_map.resolve(path)` instead of reading `fs._permissions`. The mutation-set check stays the same; only the permission lookup changes.
- Update the rejection message format per §5.3, including the matched rule prefix when one exists. Keep the `"Cannot write"` literal for `_classify_error`.
- Re-document the module docstring: keep the per-instance / shared-engine caveat, add a short section on resolution semantics with one example.

**Lines added:** ~80. **Lines removed:** ~5.

### 6.2 `base.py` — type the constructor and pass relative paths

- Change `permissions: Permission = "read_write"` to `permissions: Permission | PermissionMap | dict[str, Any] = "read_write"` on `GroverFileSystem.__init__`.
- Run the value through `coerce_permissions` and store as `self._permission_map: PermissionMap`. Keep a `self._permissions` property that returns `self._permission_map.default` for any code that still wants the simple form (and to ease the diff for tests that read it).
- In `_route_single` (line 275), pass `rel` to `check_writable` instead of `path`. This is the relative path inside the terminal filesystem, which is the coordinate system the rules use.
- In `mkconn` (line 731), pass `src_rel` instead of `source`.
- In `_route_two_path` (lines 325 / 329), the current code only checks `ops[0].dest` and `ops[0].src`. Replace with a per-op loop that calls `check_writable(dst_fs, op, dst_resolved[i][1])` for every destination, and for `move`, also for every source. Fail fast on the first rejection. (This was already a latent bug for path-aware permissions; for the mount-level case it happens to be sound because all ops in a batch resolve to the same mount, so checking one is checking all.)
- In `_dispatch_candidates` (lines 225–228), the current per-group check uses `prefix or "/"`. Replace with a per-candidate loop: walk the rebased candidates inside each group and call `check_writable(fs, op, candidate.path)` on each. Fail fast.
- In `_route_write_batch` (lines 465–468), same change: walk each object in each group and check the rebased object's path.

The five chokepoints stay the only enforcement points. Their internal granularity goes from per-mount to per-path, which is what the original §15.17 doc note ("the helper just needs to grow a path-match step") anticipated.

**Lines added:** ~30. **Lines removed:** ~10.

### 6.3 `backends/database.py` — forward the new type

- Change the constructor signature to accept `permissions: Permission | PermissionMap | dict[str, Any] = "read_write"`.
- Pass it through to `super().__init__(...)` unchanged. No DFS-specific logic.

This is the only backend change. `LocalFileSystem` and `UserScopedFileSystem` either inherit transparently or need the same one-line forwarding update.

### 6.4 `__init__.py` and `permissions` namespace

- Re-export `PermissionMap` and the `permissions` factory module from `grover/__init__.py` so users can write `from grover import PermissionMap, permissions`.
- The `permissions` name is currently the module name; expose it as both the module (for backwards compat) and as a namespace with the factory helpers.

### 6.5 `client.py` — propagation

`Grover` and `GroverAsync` already accept a `GroverFileSystem` and forward it. No client change is required — the new type rides through transparently.

---

## 7. Edge cases and pitfalls

| Case | Behavior |
|---|---|
| Override path is `/` | Rejected at construction. Use `default` instead. |
| Override path is empty or whitespace | Rejected at construction (via `normalize_path`). |
| Override paths conflict (same path, two perms) | Rejected at construction as a duplicate. |
| Override path matches multiple in the same iteration | Longest wins. Sort order is established at construction time. |
| `path == override_prefix` exactly | Matches. |
| `path == override_prefix + "/"` | Matches via `startswith(prefix + "/")`. |
| `path == override_prefix + "x"` (no boundary) | Does **not** match — `/synthesis-archive` does not match `/synthesis`. |
| Override on a metadata path (`/file.py/.chunks/x`) | Allowed but unusual. Rules normally live on regular files/directories. The match is purely structural. |
| Cross-mount move where some destinations land in writable regions and some don't | Per-op check fails fast on the first rejected destination. No partial writes. |
| Cross-mount copy from a fully readable source mount to a destination mount where some destinations are read-only | Same — fail fast on the first rejected destination. |
| User mounts the same FS instance at two router paths | Rules apply identically at both — they live on the FS, not on the mount. |
| User scoping (`user_scoped=True`) | Rules are checked **before** scoping is applied. The rule paths are written in unscoped form. Users authoring a `PermissionMap` think in user-relative paths; the scoping wrapper layers on top. (Confirm in tests — see §8.) |
| Nested overrides (writable inside read-only inside writable) | Supported via the explicit `PermissionMap` form. Longest-prefix wins guarantees correctness. |
| `permissions.read_only(write=[])` | Equivalent to `permissions="read"`. Allowed; degenerates cleanly. |
| Path normalization tricks (`//x`, `/x/`, `/x/../y`, RTL unicode) | The integrity finding #2 in §15.17 (`//x` not normalized) is **not** fixed by this proposal but is no worse. The new code calls `normalize_path` on rule paths and on the lookup path, so the comparison happens in normalized space. |

---

## 8. Test plan

A new file, `tests/test_directory_permissions.py`, mirroring the structure of `tests/test_permissions.py`:

**`PermissionMap` unit tests** (~15 tests)
- Construction with empty overrides degenerates to default-only.
- Override paths are normalized (`"/foo/"` → `"/foo"`, `"/foo/./bar"` → `"/foo/bar"`).
- Override paths sorted longest-first internally.
- Duplicate override paths rejected.
- Root-as-override rejected.
- Invalid permission strings rejected via `validate_permission`.
- `resolve()` returns default when no overrides match.
- `resolve()` returns longest-matching override.
- Boundary cases: `path == prefix`, `path startswith prefix + "/"`, `path startswith prefix` without slash boundary (no match).
- Nested overrides: `("/a", "rw"), ("/a/b", "ro")` — `/a/x` is `rw`, `/a/b/x` is `ro`, `/a/b` itself is `ro`.
- `frozen=True` enforced.

**Factory helper tests** (~6 tests)
- `permissions.read_only()` with no kwargs → equivalent to `"read"`.
- `permissions.read_only(write=["/x"])` → correct `PermissionMap`.
- `permissions.read_write()` with no kwargs → equivalent to `"read_write"`.
- `permissions.read_write(read=["/x"])` → correct `PermissionMap`.
- Empty list kwargs degenerate cleanly.
- Helpers reject invalid path entries with the same error as `PermissionMap`.

**Integration tests against `DatabaseFileSystem`** (~25 tests)
- Constructor accepts `Permission`, `PermissionMap`, dict (if §5.2 form C is included).
- Read-only mount with one writable subtree: write inside subtree succeeds, write outside fails.
- Read-write mount with one read-only subtree: write outside subtree succeeds, write inside fails.
- All seven mutating ops (`write`, `edit`, `delete`, `mkdir`, `mkconn`, `move`, `copy`) tested in both directions for the writable hole and for the frozen hole.
- Soft and permanent `delete`.
- Batch object writes spanning a writable region and a frozen region — fail fast, no partial writes.
- Candidate-based dispatch (`delete(candidates=...)`, `edit(candidates=...)`) where candidates straddle a permission boundary — fail fast.
- Cross-mount `move` from a read-only mount to a partially-writable mount where the destination lands in a read-only subtree — fails.
- `copy` source from a read-only subtree of a writable mount → still allowed (reads are not mutations).
- `mkconn` with source in a writable subtree and target in a read-only subtree — succeeds (the connection lives on source).
- `mkconn` with source in a read-only subtree — fails.
- Metadata path mutations (`/file.py/.chunks/...`) inherit from the file's permission via prefix matching.
- Nested overrides resolve correctly.
- Same FS instance mounted at two router paths — rules apply identically at both, verified by writing through one mount and confirming the rule fired against the FS-relative path.
- User-scoped filesystem combined with permissions: rules are checked against unscoped paths.

**Regression coverage** — re-run `tests/test_permissions.py` unchanged. Every existing test must pass without modification, since the simple `permissions="read"` / `permissions="read_write"` form is preserved.

**Coverage target:** 100% on `permissions.py`, base.py chokepoints stay at 100%. Total project coverage stays ≥ 99.81%.

---

## 9. Documentation updates

- **`docs/plans/everything_is_a_file.md`** — close §15.17's "Future work / Directory-level permissions" item with a forward reference to a new §15.18 written after implementation. Update §8.2's example to use the new factory syntax (`permissions.read_only(write=[...])`).
- **`Grover_The_Agentic_File_System.md`** — add a short example to the "One Minute Setup" section showing the LLM Wiki mount with directory-level permissions.
- **`permissions.py` module docstring** — replace the "Future work" section with "Resolution semantics", documenting longest-prefix-match and the FS-relative coordinate system. Keep the per-instance / shared-engine caveat verbatim.

---

## 10. Out of scope (explicitly not doing)

- **Per-user ACLs / shares.** That is `grover_shares` and `SupportsReBAC` — separate iteration, separate table, separate axis.
- **Glob patterns in rules.** Explicitly rejected per §3.3.
- **Operation-specific permissions** (e.g., "writable but no delete"). The `Permission` literal stays as `read | read_write`. If a future use case needs it, the literal extends and `validate_permission` grows another exhaustive branch.
- **Runtime mutation of the rule set** (`fs.add_rule(...)`, `fs.remove_rule(...)`). Rules are set at construction and frozen. If a use case appears where rules need to be updated after a mount is live, build a `PermissionMap.with_override(path, perm) -> PermissionMap` immutable update method and require the user to remount.
- **Closing the three integrity findings from §15.17.** Forged connections, double-leading-slash normalization, and `_classify_error` substring brittleness are all still open. They are tracked in §15.17 and should be addressed in their own iteration; bundling them with this would muddy the diff.

---

## 11. Open questions for review

1. **Form C (dict shorthand) — keep or drop?** It adds a small parser. I lean drop unless there's a specific config-file use case where users want to express permissions as JSON/YAML.
2. **Should the `permissions.read_only(write=[...])` factory accept tuples of `(path, "read_write")` for the rare nested case, or keep it strictly to a flat list?** I lean keep flat — the rare nested case uses the explicit `PermissionMap` form.
3. **Naming: `PermissionMap` vs `Permissions` vs `PermissionRules`.** `PermissionMap` is unambiguous (it's a map from path to permission). `Permissions` collides with the existing `permissions.py` module name and the `permissions=` kwarg. `PermissionRules` reads well but implies a richer rule type than we have. I lean `PermissionMap`.
4. **Should `check_writable` return the matched rule prefix in the error context** so that downstream tooling (the CLI, future audit logging) can surface "rejected by rule X" without re-parsing the message? This would require adding a structured field to `GroverResult.errors`, which is a separate concern. Lean: no, leave the structured-error refactor to its own iteration.
5. **Should `_route_two_path`'s switch from "check first op" to "check every op" be filed as a standalone bug fix that also lands without the directory-level feature?** Today's behavior is sound at the mount level (because all ops in a batch resolve to the same mount), so it isn't user-visible. But the new behavior is strictly more correct and the change is small. I lean: include in this PR; mention in the commit message.

---

## 12. Summary

One new immutable value type (`PermissionMap`), one helper module (`permissions.read_only`, `permissions.read_write`), and a tightening of the existing five chokepoints from per-mount to per-path checks. The simple `"read"` / `"read_write"` API is preserved. The mental model — default permission plus longest-prefix overrides — matches mount routing, S3 prefixes, sparse-checkout cone mode, and Linux firewall prefix lists. The LLM Wiki use case (§8.2) becomes a one-line declaration. No new exception class, no new chokepoints, no new persistent state, no per-user complication.
