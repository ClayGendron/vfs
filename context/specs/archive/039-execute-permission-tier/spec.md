# 039 — Execute Permission Tier for the `run` Verb

- **Status: closed as superseded, 2026-08-25** (archived in the
  active-spec closure pass; nothing here lands). The per-path /
  per-principal execute policy question that would reopen it is
  recorded in `../../../open-questions.md`; the identity half is 070's.
  Original status kept below.
- **Status (original):** draft, superseded in practice by 068 (landed 2026-07-11):
  `deny_ops` is the execution lever — `run` stays outside the
  permission-map vocabulary. Two deliberate supersessions recorded
  there: denied execution classifies `unsupported` (040's capability
  slot), not this spec's `permission_denied`; and per-path execute
  carve-outs stay unexpressed (`deny_ops` is per-entry). Reopen only if
  per-path or per-principal execute policy becomes real.
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** feature (permission model) + policy decision
- **Depends on:** 036 (router verb surface — `run`), 035 (op classes:
  `EXEC_OPS`), 034 (MCP-native mounts — the tool catalogs this gates)
- **Enables:** mounting third-party MCP tool catalogs with an explicit,
  auditable execution policy instead of an implicit always-allow

## Intent

Give execution its own permission dimension. Today `Permission` is
`read | read_write` and `run` is deliberately not write-gated
(`base2.py:1247` — "not a namespace mutation, so it takes no
write-authorization gate"). The consequence: **a mount constructed with
`permissions="read"` executes its tools without restriction.** For MCP
tool catalogs, execution is the single most security-relevant operation
in the system, and right now the policy is implicit and unconfigurable.

This story makes the policy explicit: permissions become *rights sets*
(`read` / `write` / `execute`), `run` is gated at the router chokepoint
like every mutation, and the string sugar keeps today's ergonomics.

## Why

- `ops.py` already recognizes execution as its own class (`EXEC_OPS`,
  "not a namespace mutation, not a read") — the op vocabulary made the
  distinction; the permission model never caught up.
- Read-only is the natural mount mode for a tool catalog (you cannot edit
  the vendor's catalog), so overloading `read` to also mean "may not
  execute" would break the primary use case. Execution must be
  *orthogonal* to write, not a rung above it.
- A parent mounting an untrusted catalog needs a one-line way to say
  "discoverable but not runnable" (`read`, no execute) and "runnable
  except these" (execute with carve-outs). Neither is expressible today.

## Decided policy (signed off 2026-07-03)

**Execute defaults to granted.** Both string forms — `"read"` and
`"read_write"` — include `execute`, so every existing construction keeps
its current behavior and the tool-catalog default (read-only mount,
runnable tools) stays a one-word config. Locking execution down is the
explicit act:

```python
permissions="read"                      # discover + run (today's behavior, now explicit)
permissions=permissions.no_execute()    # discover only — audit/quarantine a catalog
permissions=permissions.read_only(      # runnable, except the dangerous family
    execute_not=["/deploy"],
)
```

The alternative (deny-by-default) was rejected: it would make every
existing mount of a tool catalog silently dead until reconfigured, and
"mounted but not runnable" is the *rare* intent, not the common one.

## Design

### D1 — `Rights` replaces the two-value `Permission`

```python
# vfs/permissions.py

Right = Literal["read", "write", "execute"]
Rights = frozenset[Right]

READ: Final[Rights] = frozenset({"read", "execute"})
READ_WRITE: Final[Rights] = frozenset({"read", "write", "execute"})
READ_NO_EXEC: Final[Rights] = frozenset({"read"})

_STRING_FORMS: Final[dict[str, Rights]] = {
    "read": READ,             # sugar keeps today's semantics: read implies execute
    "read_write": READ_WRITE,
}
```

`PermissionMap` stores `Rights` per rule; construction accepts the string
forms anywhere a `Rights` is accepted, via one coercion:

```python
def coerce_rights(value: Rights | str) -> Rights:
    if isinstance(value, frozenset):
        unknown = value - {"read", "write", "execute"}
        if unknown:
            msg = f"Unknown rights: {sorted(unknown)}"
            raise ValueError(msg)
        return value
    rights = _STRING_FORMS.get(value)
    if rights is None:
        msg = f"permissions must be 'read', 'read_write', or a Rights set, got {value!r}"
        raise ValueError(msg)
    return rights
```

`resolve` keeps longest-prefix semantics unchanged; only the resolved
value's type widens from a two-value literal to a `Rights` set.

### D2 — one gate function keyed by op class

`check_writable` generalizes to `check_allowed`: the required right comes
from the op's class in `vfs.ops`, so the router keeps calling one
function at every chokepoint and `run` is gated for free:

```python
# vfs/permissions.py

def required_right(op: str) -> Right | None:
    """The right an op needs beyond read, or None for pure reads."""
    if op in MUTATING_OPS:
        return "write"
    if op in EXEC_OPS:
        return "execute"
    return None


def check_allowed(
    fs: VirtualFileSystem,
    op: str,
    rel: Path,
    *,
    mount_prefix: Path = _ROOT,
) -> Result | None:
    """Classified error if *op* needs a right the resolved rules deny, else None."""
    right = required_right(op)
    if right is None:
        return None
    resolved = _resolve_with_meta_alias(fs._permission_map, rel)
    if right in resolved.rights:
        return None
    full = rel.with_mount(mount_prefix)
    kind = VFSErrorKind.read_only if right == "write" else VFSErrorKind.permission_denied
    rule = f"mount rule '{resolved.rule_prefix}'" if resolved.rule_prefix else "mount default"
    return fs._error(
        f"Operation {op!r} requires the {right!r} right on '{full}' ({rule})",
        kind=kind,
        function=op,
        path=full,
    )
```

Error-kind mapping: denied **writes** keep `read_only` (EROFS — the
established contract); denied **execution** is `permission_denied`
(EACCES) — a read-only surface is not what's wrong with a non-runnable
tool.

Router change is one rename at each chokepoint (`_route_single`,
`_dispatch_grouped_observations`, `_route_two_path`,
`_route_entry_batch`, `mkedge`) plus `run`'s docstring dropping the
"takes no write-authorization gate" sentence — the gate now covers it via
`required_right`.

### D3 — sugar factories

Existing factories keep their names and gain the execute carve-outs;
one new factory covers the quarantine case:

```python
def read_only(*, write: Iterable[str] = (), execute_not: Iterable[str] = ()) -> PermissionMap:
    """Read-only default (executable), with writable holes and non-runnable holes.

    >>> m = read_only(write=["/synthesis"], execute_not=["/deploy"])
    >>> m.resolve("/synthesis/page.md") >= {"write"}
    True
    >>> "execute" in m.resolve("/deploy/prod")
    False
    """


def read_write(*, read: Iterable[str] = (), execute_not: Iterable[str] = ()) -> PermissionMap:
    """Writable default (executable), with read-only holes and non-runnable holes."""


def no_execute() -> PermissionMap:
    """Read-only, nothing runnable — the audit/quarantine map for a new catalog."""
    return PermissionMap(default=READ_NO_EXEC)
```

Overlapping carve-outs (a path in both `write=` and `execute_not=`)
compose by set difference on the same rule, not by two competing rules —
construction merges them so longest-prefix resolution stays single-pass.

### D4 — incidental cleanups in `permissions.py` (same files, same story)

- `_permission_candidates` hardcodes `"/.vfs"`; import and use
  `METADATA_ROOT` from `vfs.paths` (one source of truth — a rename would
  silently break the alias today).
- `check_allowed` reaching into `fs._permission_map` / `fs._error` is
  friend-module coupling; expose a read-only `permission_map` property on
  `VirtualFileSystem` and keep `_error` composition in the router by
  having `check_allowed` return a `(kind, message, path)` denial tuple
  the chokepoint wraps. (Small, but it removes the last private-attr
  reach across the module seam.)

## Interaction with `capabilities()`

Orthogonal and both apply: `capabilities()` says what a terminal *can*
answer (absent op → `unsupported`, no wire call); rights say what this
mount is *allowed* to do (denied `run` → `permission_denied`). Order
stays capability-then-permission, matching the existing chokepoints, so
an incapable catalog still reads as `unsupported`, not as a policy
denial.

## Test plan

1. **Default grant:** `permissions="read"` mount executes a tool
   (regression pin for today's behavior, now intentional).
2. **Quarantine:** `no_execute()` mount — `ls`/`read`/`stat` on the tool
   succeed, `run` returns `permission_denied` with the rule in the
   message; nothing dispatches to the impl (spy fs).
3. **Carve-outs:** `read_only(execute_not=["/deploy"])` — `/deploy/x`
   denied, sibling `/tools/y` runs; longest-prefix beats default.
4. **Kind mapping:** denied write still `read_only`; denied run is
   `permission_denied`; boundary adapter (story 037) maps each to its
   exception.
5. **Chokepoint coverage:** parametrize `EXEC_OPS | MUTATING_OPS` over
   the gate to pin that every non-read op consults `required_right`
   (drift-test style, alongside the 035 ones).
6. **Coercion:** string forms resolve to the documented sets; unknown
   right names raise at construction.

## Open questions

None — the implicit-grant question was signed off 2026-07-03 (`read`
implies execute; revisit only if a real deployment asks for
deny-by-default), and per-user execution is out by doctrine: rights
resolution here is user-blind, and per-user policy belongs to the
ReBAC/share layer, mirroring the user-scoping doctrine in this module's
docstring.
