# 040 — One Terminal Gate for Every Dispatch Chokepoint

- **Status:** draft
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** refactor (router gate consolidation) + fix (structured error
  payload consistency)
- **Depends on:** 036 (router verb surface — the five chokepoints), 037
  (single result channel — gate failures are classified results)
- **Enables:** 039 (the `check_writable` → `check_allowed` rename becomes
  a one-line swap inside the gate instead of five call-site edits), 041
  (mount-spine visibility — expanded spine targets run the same gate)

## Intent

Every dispatch chokepoint runs the same three checks before touching a
terminal, in the same pinned order:

1. **Routability** — the terminal is `self` without storage → `not_found`
2. **Capability** — the terminal's `capabilities()` lacks the op →
   `unsupported` (the no-probe rule)
3. **Permission** — the op mutates a read-only path → `read_only`

Today that triple is hand-copied at five sites — `_route_single`,
`_dispatch_grouped_observations`, `_route_two_path`, `_route_entry_batch`,
`mkedge` (plus the routability/capability pair in `_route_fanout`'s scoped
branch) — and the copies have already drifted on the error payload. This
story extracts one `_gate_terminal` helper, makes every gate error carry
the structured `path` it implicates, and pins the gate order with tests so
the next permission tier (039) lands in one place.

## Why — verified drift

Reproduced against `base2.py` at `06cf551` (`repro.py` in this folder):

```text
no-mount (single write)          kind=not_found    path=None
permission (single write)        kind=read_only    path=None
permission (entry batch)         kind=read_only    path=None
permission (move pair)           kind=read_only    path=None
capability (single grep scoped)  kind=unsupported  path='/dim/sub'
capability (grouped stat)        kind=unsupported  path=None
```

- `ResultError.path` exists precisely so consumers don't parse prose, and
  the router leaves it `None` on almost every gate failure. The one
  exception — capability errors — sets it at some sites
  (`base2.py:561`, `:705`) and passes `None` at others (`base2.py:499`).
  An agent that wants to know *which* path was refused must regex the
  message.
- `_route_two_path` gates the dest with `mount_prefix=src_prefix`
  (`base2.py:632`), discarding the dest's own prefix. Correct today only
  because same-terminal is enforced first; any future relaxation of the
  cross-mount rule would silently mis-report dest denials.
- The gate *order* (routability → capability → permission) is a real
  contract — an incapable catalog must read as `unsupported`, not as a
  policy denial (039 depends on this) — but it lives only as five code
  sequences. Nothing pins it.
- Grouped dispatch rebases capability errors after the fact
  (`cap_err.with_mount(prefix)`, `base2.py:501`) while the other sites
  compose them pre-rebased — two conventions for the same rebase.

None of these is a live bug in isolation; together they are exactly how
five copies rot. 039 is about to edit all five sites at once — extract
first, then 039 touches one line.

## Design

### D1 — `_gate_terminal`, the one gate

```python
def _gate_terminal(
    self,
    fs: VirtualFileSystem,
    op: Op,
    prefix: Path,
    *,
    report: Path,
    write_rels: Sequence[Path] = (),
) -> Result | None:
    """Routability → capability → permission, in the pinned order.

    *report* is the terminal-relative path implicated in terminal-level
    failures (routability, capability); it is reported router-side —
    rebased under *prefix* — so the caller always sees the path they
    typed. *write_rels* are the terminal-relative paths the permission
    gate checks (empty when the write target is derived later, as in
    mkedge's pre-delegation gate). Returns the first classified failure,
    else ``None``.
    """
    reported = report.with_mount(prefix)
    if fs is self and not self._storage:
        return self._error(
            f"No mount found for path: {reported}",
            kind=VFSErrorKind.not_found, function=op, path=reported,
        )
    err = self._capability_error(fs, op, reported)
    if err is not None:
        return err
    for rel in write_rels:
        err = check_writable(fs, op, rel, mount_prefix=prefix)
        if err is not None:
            return err
    return None
```

Call-site mapping (mechanical):

| Site | `report` | `write_rels` |
| --- | --- | --- |
| `_route_single` | `rel` | `(rel,)` |
| `_dispatch_grouped_observations` (per group) | `group[0].path` | all group paths |
| `_route_two_path` (per pair) | `src_rel` | move: `(src_rel, dest_rel)`; copy: `(dest_rel,)` |
| `_route_entry_batch` (per entry) | `rel` | `(rel,)` |
| `_route_fanout` scoped (per scope) | `rel` | `(rel,)` — no-ops, reads |
| `mkedge` pre-delegation | `src_rel` | `()` — target derived later |

`mkedge`'s local branch keeps its direct `check_writable(edge_path)` call:
the write target is the *derived* canonical edge path, not a caller path,
and deriving it belongs after delegation (the child re-derives in its own
coordinates). A one-line comment at the site says exactly that.

`check_writable` no-ops for non-mutating ops (it already gates on
`MUTATING_OPS`), so passing `write_rels` uniformly at read sites costs
nothing and keeps the call shape identical everywhere.

### D2 — every gate error carries a structured `path`

The rule, stated once and enforced by the helper: **the `path` on a gate
error is always router-side — the path the caller addressed, never a
terminal-local coordinate.** Changes:

- `check_writable` passes `path=full` on both of its `fs._error` calls
  (`permissions.py:290-299`) — it already computes `full` for the message.
- The no-mount and capability errors get `path=reported` via D1.
- Grouped dispatch drops its after-the-fact `cap_err.with_mount(prefix)`;
  the helper composes errors router-side from the start.

One behavioral note to document in the changelog: the capability error for
a `copy`/`move` pair currently implicates the *src* path; under D1's table
it still does (`report=src_rel`) — no change, now by stated rule instead
of by accident.

### D3 — the dest gate uses the dest's own prefix

`_route_two_path` keeps the dest terminal's prefix from `_resolve_terminal`
instead of discarding it, and passes it to the gate for `dest_rel`. A
behavioral no-op today (same terminal ⇒ same prefix, enforced one check
earlier) that removes the trap D2's audit tripped over.

### D4 — incidental, same seam: "cannot verify" is not "conflict"

`add_mount` reports every `_is_path_mountable` failure as "storage
contents conflict with that mount point" (`base2.py:170`), including the
case where the lineage probe came back `unavailable` — a wrong diagnosis
that sends an operator hunting phantom files while the real problem is a
downed backend. `_is_path_mountable` returns `(ok, reason)` like the other
namespace checks (`check_mutable_path` sets the precedent), with `_probe`
supplying the classified reason; `add_mount` raises the reason it was
given. Private seam, no public surface change.

## Out of scope

- The rights model and `run` gating — story 039, which lands *on top of*
  this gate (its D2 `check_allowed` replaces `check_writable` inside
  `_gate_terminal` only).
- Any change to gate *order* or gate *kinds* — this story pins existing
  semantics; it does not revise them.
- Spine-path routability (ls/stat on `/` and mount ancestors) — story
  041, which reuses this gate for its expanded targets.

## Test plan

1. **No behavior drift:** the full existing suite passes untouched except
   assertions on error payloads, which gain `path` expectations.
2. **Structured path, everywhere:** parametrize the repro matrix — each
   chokepoint (single, grouped, pair, entry batch, mkedge, scoped fanout)
   × each gate failure reachable there — and assert `error.path` equals
   the router-side path the caller addressed. The repro script's six
   `path=None`/inconsistent rows become the regression pins.
3. **Order pins:** a terminal that is simultaneously incapable and
   read-only fails `unsupported` (capability outranks permission); a pure
   router with no mount at the path fails `not_found` even when the op is
   also outside `self.capabilities()` (routability outranks capability).
4. **Copy asymmetry preserved:** copy's src on a read-only region still
   dispatches (no write gate on a copy source); move's src still denies.
5. **Mount diagnosis:** `add_mount` over a storage backend whose probe
   fails `unavailable` raises a "cannot verify" message, not a contents
   conflict; a genuine content collision keeps the conflict message.

## Open questions

- Should `_capability_error` fold into `_gate_terminal` entirely (it has
  no other callers after this story)? Current call: yes, inline it —
  one fewer seam. Flagged in case a future remote-catalog story wants a
  standalone capability probe.
