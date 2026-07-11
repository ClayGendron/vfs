# 069 — Routing decomposition: total steps, refusal checks, one plan per fan-out

- **Status:** implemented 2026-07-10 (landing commit `22a3f33`) — research
  review 2026-07-10 (3 primary-source lenses: Linux v6.12
  `namei.c`/`pnode.c`, Plan 9 4th-edition `chan.c`/`devmnt.c`,
  V7→4.4BSD `namei`; **no fatal objections**; four amendments
  recorded below). All open questions resolved with owner
  2026-07-10 (the fusion fork declined on verified `vfs_rmdir`
  sequencing — see decision 2). Landed: 1196 pre-existing tests
  green unmodified, 14 new direct tests, ruff/ty clean, fan-out
  body 42 lines.
- **Date:** 2026-07-10
- **Owner:** Clay Gendron
- **Kind:** refactor (router internals — dispatch-shape decomposition;
  no verb-surface or wire changes)
- **Depends on:** 056 (storage mounts — one table, one funnel), 057
  (result envelope — classified refusals)
- **Prior art:** 053 (router review cleanups); the three-fork
  assessment of `_route_single` / `_route_two_path` / `_route_fanout`
  (design discussion, 2026-07-10)

## Intent

The three routing methods have grown past the point where their phases
read as phases. `_route_fanout` is ~95 lines interleaving validation,
scope classification, dispatch assembly, and merge policy;
`_route_single` and `_route_two_path` repeat a resolve-and-classify
block that appears eight times across the file; the file's two subtlest
invariants — subsumption pinning and the capability-skip rule — are
reachable only through a full router-plus-mounts test setup.

This story decomposes the routing methods along their phase seams
**under one typing rule**, so the decomposition cannot reintroduce the
two-headed return shapes it is cleaning up:

> **A function returns one type. The only union is `X | None`.**
> Value-producing steps are *total* — they always return their value.
> Policy checks are *partial* — they return `Result | None`, where the
> `Result` is a refusal and `None` means proceed. No function both
> produces a value and refuses.

The rule is already the file's better half. `resolve_path` returns the
`ResolvedPath` product (`path: Path | None`, `error: str | None` —
each field independently `X | None`); `_resolve_terminal` is total;
`_gate_entry` and `_busy_guard` are refusal checks. The violations are
the newer code: `_enter_hop` returns `Result | Token` (decision 5
normalizes it), and the earlier decomposition sketch proposed
`Path | Result` and `Plan | Result` helpers (rejected here; decisions
1 and 3 give the compliant shapes).

## Decisions

1. **Invalid-path classification is one total function, and the
   resolve idiom stays put.** The eight resolve-and-classify sites
   keep their two-line shape — `resolved = resolve_path(raw, ...)`
   then a `resolved.path is None` branch, which narrows cleanly for
   `ty` — but the failure branch calls one helper instead of minting
   its own error:

   ```python
   def _invalid_path(self, resolved: ResolvedPath, raw: str, op: Op) -> Result:
   ```

   Total (called only in the failure branch, always returns a
   refusal), single return type, message canonical at one site. A
   `Path | Result` union helper was considered and rejected: it
   violates the rule and defeats `ty` narrowing at every call site.

2. **`_busy_guard` and `_gate_entry` stay separate; call sites
   sequence them.** *(Resolved with owner 2026-07-10 — a
   `_refuse_target` fusion was designed, researched, and declined;
   see Declined.)* The two checks have different subjects — the busy
   guard asks the *mount table* (is this a live bind site?), the gate
   asks the *entry* (declared capability, composed permissions) — and
   the file keeps table concerns and entry-policy concerns in
   separate sections. The routing methods call both, in order, at the
   call site; the protection for future verbs is the suite's pin that
   deleting a bind site is `busy`, not an abstraction.

   Verified precedent (local mainline clone, post-v6.12):
   `may_delete_dentry` is implemented in `fs/namei.c` and knows
   nothing about mounts; the busy predicate `__is_local_mountpoint`
   is implemented in `fs/namespace.c` behind a `fs/mount.h` inline;
   `vfs_rmdir` orchestrates them sequentially at the call site —
   permission, capability (`-EPERM` for a missing `->rmdir` op), then
   `-EBUSY`. Two named checks, two files, never fused — and mainline
   has since *exported* `may_delete_dentry` standalone, promoting the
   split.

   **Guardrail: `_route_two_path`'s check order is a contract.** Its
   pinned order is resolve-src → resolve-dest → busy-src → busy-dest;
   a per-endpoint pipeline reorders the checks and flips the reported
   kind from `invalid` to `busy` on a batch pairing a bind-site src
   with an invalid dest. The pair loop takes decision 1 only, and the
   order is pinned by the mandatory precedence test (acceptance
   criteria), not by docstring alone.

3. **Fan-out scope classification returns a plan; the plan carries its
   own refusal.** The ~43-line classification block in `_route_fanout`
   (path validation, region detection and expansion, capability-skip
   dedup, the scoped-entry gate) lifts into:

   ```python
   class _FanoutPlan(NamedTuple):
       scoped: dict[Path, tuple[Binding, list[Path]]]
       unscoped: dict[Path, Binding]
       skips: list[ResultError]
       refusal: Result | None = None

   def _classify_fanout_scopes(self, op: Op, paths: tuple[str, ...]) -> _FanoutPlan:
   ```

   Every field is total or `X | None`, so the rule holds without
   asserts: a refusing plan carries empty collections, and the caller
   checks `plan.refusal` before assembling dispatch. The helper is a
   method (it needs `_resolve_terminal`, `_bindings_beneath`,
   `_gate_entry`, `_skip_entry`) but is synchronous with zero awaits —
   testable against a mounted router with no dispatch. First-bad-path
   early return and the `setdefault` skip dedup survive verbatim.
   `_FanoutPlan` lives beside the fan-out group per the file-layout
   rule (private types sit with their user).

4. **Merge policy becomes a pure function.** The pinned/demotable
   arithmetic — a subsumed named entry answers as a branch but merges
   plain — lifts into:

   ```python
   @staticmethod
   def _merge_fanout(
       named: list[Result],
       branch_results: list[tuple[Path, Result]],
       scoped_keys: frozenset[Path],
       op: Op,
   ) -> Result:
   ```

   No self, no async, no router state — bind paths instead of
   bindings, so the subsumption-pinning rule gets direct unit tests
   with hand-built `Result`s. Skips stay outside: they rejoin via
   `_with_skips` after the merge, so the invariant that coverage
   records never feed the zero-progress arithmetic is now visible in
   the signatures rather than asserted in a comment.

5. **`_enter_hop` normalizes to the rule.** Today it returns
   `Result | Token[int | None]` — the file's one standing violation.
   It becomes:

   ```python
   class _HopGrant(NamedTuple):
       token: Token[int | None] | None
       refusal: Result | None

   def _enter_hop(self, *, op: Op) -> _HopGrant:
   ```

   Callers check `grant.refusal`, and `_exit_hop(grant.token)` accepts
   `None` (no-op). Both call sites (`_tree_entry`, `_route_fanout`)
   keep their `try/finally` shape. An async context manager was
   considered and rejected: it cannot early-return the caller's
   refusal, so every site would keep the check anyway and pay an
   indent level for it.

6. **`ResolvedTerminal` grows a `full` property**
   (`rel.with_mount(binding.path)`), removing the re-derivations in
   `_tree_entry` and the pair loop. Total, two lines.

7. **Grouped-observation dispatch resolves once.**
   `_dispatch_grouped_observations` resolves every path in its
   validation loop, then `_group_observations_by_terminal` re-resolves
   terminals from scratch. The validation loop passes its resolved
   paths through; the double resolution dies. Behavior identical.

8. **File layout truing-up.** `_route_pairs` moves from the
   "public methods — mutations" banner to the dispatch-shapes section
   beside its siblings; `_coerce_two_path` moves to internal helpers.
   No code changes.

## Research review (2026-07-10) — Linux, Plan 9, classic Unix

Three lenses, each verifying against fetched primary source (Linux
v6.12 raw tree; the 0intro Plan 9 4th-edition mirror; TUHS V7 and
4.3BSD, 4.4BSD `vfs_lookup.c`). Verdicts per decision:

| Decision | Linux | Plan 9 | Classic Unix |
|---|---|---|---|
| 1 invalid-path mint | supports (in intent) | supports (`parsename` + canonical error strings) | supports (V7's scattered `u.u_error` sites are the anti-pattern) |
| 2 checks stay separate + guardrail | split verified (`vfs_rmdir` sequences `may_delete_dentry` then `-EBUSY`; predicates live in separate files); guardrail supported (`do_renameat2` endpoint order) | guardrail spirit only | flag warning (A3) fed the decline |
| 3 `_FanoutPlan` | supports — via `renamedata`, not `nameidata` | qualified (`Elemlist` = the parse half) | supports strongly (the `nameidata` move itself) |
| 4 `_merge_fanout` | no precedent (nearest, `propagate_mnt`, is worse) | supports the law (graded Rwalk; Rerror only on zero progress) | no precedent |
| 5 `_HopGrant` | supports strongly (`set_nameidata`/`restore_nameidata` inherit-and-write-back ≅ the ContextVar token) | no precedent, structurally justified | supports (`ni_loopcnt`→`ELOOP` as classified refusal) |
| 6 `.full` property | supports (`nd->inode` caching idiom) | supports (walk carries the accumulated name) | supports |
| 7 resolve once | supports (re-walks are deliberate retries, never re-resolution) | supports (monotonic element consumption) | supports strongly (4.3BSD rename re-lookup comments — proto-TOCTOU) |
| 8 layout | n/a | n/a | n/a |

**The recorded defense of the no-union rule** (resolves the research
question below): Linux's ERR_PTR is C economics — one register, no
product types, no pattern matching, hot-path zero-cost — and still
breeds a known bug class (forgotten `IS_ERR`); where semantics beat
registers, Linux itself separates check from produce (the `may_*`
family returns 0-or-errno ≅ our `Result | None`, kept apart from the
dentry pipeline). Plan 9 never adopted the union even in C: `walk()`
returns status plus out-params, `waserror()` is confined behind seams
(`ewalk` converts it to nil exactly where components compose), and
the wire carries only Rerror values and graded Rwalk. The V7→4.4BSD
trajectory is a fifteen-year migration off overloaded returns: V7
`namei` returned `inode | NULL` where NULL meant three things
disambiguated by five globals; 4.3BSD ran two error channels at once;
4.4BSD ended it — the refusal is the sole `int` return, values live
in the `nameidata` product. The rule adopts what all three systems
converged on and discards only what C forced.

**Amendments adopted from the review:**

- **A1 — the plan is output-only, forever.** `_FanoutPlan` never
  grows input fields (row caps, kwargs, hop state); BSD's
  `nameidata` accreted I/O state (`ni_iovec`) that 4.4 had to cut
  back out. Its `refusal` field is the sanctioned *sole* carrier for
  classification refusal — never a second channel beside a returned
  `Result` (4.3BSD's dual `ni_error`/`u.u_error` is the recorded
  failure mode).
- **A2 — the rule's scope is router-side table-fact checks only.**
  Backend methods check-and-act in one call by design (056; `mkdir`
  has no site probe) because a separated check would race. This spec
  must never be cited to split a backend into a check-then-produce
  pair.
- **A3 — one-flag budget on fused checks.** V7's `flag 0/1/2` and
  4.3BSD's `LOCKPARENT`/`NOCACHE`/`FOLLOW` soup show flag accretion
  is how fused checks decay. This fed the decline of the
  `_refuse_target` fusion and stands as the budget for any future
  fused check (including `_gate_entry`, currently flagless beyond
  `write_rels`).
- **A4 — the split rides on I/O-free resolution.** The total/refusal
  seams exist because `_resolve_terminal` is a synchronous table
  match (056's stored shape). Plan 9 is the evidence for what happens
  otherwise: when resolution requires storage I/O (`walk()` is device
  I/O with per-step mount checks), resolve and dispatch must
  interleave and these seams collapse. If symlink-alikes or
  per-component gates ever arrive, this spec's shape is re-litigated,
  not patched.

**Divergence on record (pre-existing, not this spec's concern):**
`vfs_rename` checks permission before capability (`may_delete`, then
`-EPERM` for a missing `->rename` op) — the reverse of our pinned
capability-then-permission order. Linux's shape conflates policy with
capability; our `unsupported`-never-reads-as-denial contract is the
deliberate un-conflation, kept. Likewise `vfs_rmdir` runs its busy
check *last* (it must sit under `inode_lock` to be stable), where our
busy guard runs first; ours is a lock-free table fact, so the
position is free and the earlier refusal is the cheaper one.

**Precedent notes:** our fan-out skip records *exceed* precedent —
Plan 9's `unionread` silently skips an errored union element and
tells the caller nothing; the info-severity coverage record is the
improvement, kept. The zero-progress rule is graded Rwalk almost
verbatim (partial progress is success-with-less; only zero progress
is loud).

## Declined — assessed and rejected, recorded so they stay rejected

- **A generic `_route_batch` engine** unifying
  `_dispatch_grouped_observations` and `_route_entry_batch` via
  `get_path`/`rebase` callables. The two methods are the same
  algorithm, but callback threading is indirection of exactly the
  kind this file refuses — every abstraction in base.py is a named
  contract, not a hook. Two readable 50-line methods beat one
  45-line engine read through parameters. Decision 7 takes the real
  defect instead.
- **A `_dispatch_groups` gather-and-merge tail helper.** Needs a
  stringly `payload_key` (`"observations"` / `"operations"` /
  `"entries"`); trades twelve visible lines for opacity.
- **Unifying `_route_fanout` and `_tree_entry` descent machinery.**
  The shared plumbing is already factored (`_bindings_beneath`,
  `_skip_entry`, `_with_skips`, `merge_branches`); what differs is
  policy — depth-budget arithmetic, no row cap, no pinning. An
  abstraction over two call sites with a knob per difference makes
  both harder to read.
- **A dispatch-override table for the `tree` detour in
  `_route_single`.** One op, one detour, already extracted as
  `_tree_entry`; a table with a single row is ceremony.
- **The `_refuse_target` fusion (busy guard + gate in one refusal
  check).** Declined with owner 2026-07-10. Site-fit: both halves
  fire together only in `_route_single`'s delete path; in
  `_route_entry_batch` it degenerates to `_gate_entry` with a dead
  flag; in grouped-observation dispatch the two checks run at
  different loop positions; in `mkedge` the derived-path check
  doesn't fit the shape. Domain-fit: the busy guard is table state,
  the gate is entry policy, and the verified Linux precedent keeps
  exactly that split (`may_delete_dentry` in `fs/namei.c`,
  `__is_local_mountpoint` in `fs/namespace.c`, sequenced by the
  caller in `vfs_rmdir` — never fused). The `may_lookup` precedent
  supports fused *policy* checks, which `_gate_entry` already is.
- **`SUBTREE_GUARDED_OPS` as ops.py vocabulary.** Falls with the
  fusion: with no `subtree_guard` flag to feed, a one-member
  frozenset serving two inline `op == "delete"` sites is noise.

## Non-goals

- No verb-surface, wire, or storage-protocol changes; no new ops.
- No behavior changes: error kinds, messages, severities, check
  ordering, and merge semantics are pinned by the existing suite and
  must survive unmodified.
- The memory backend's `_put_file -> Result | Observation` union is
  the same smell in a different file; out of scope here, noted for
  the backend conformance story.
- `SUBTREE_GUARDED_OPS` as ops.py vocabulary — resolved 2026-07-10:
  declined with the fusion (see Declined).

## Acceptance criteria

- The full `tests/` suite passes unmodified — the refactor is proven
  behavior-preserving by black-box tests only.
- New direct unit tests: `_merge_fanout` (pinning survives
  subsumption; demotion applies only to unpinned branches) and
  `_classify_fanout_scopes` (region expansion, skip dedup,
  first-bad-path refusal), plus `_HopGrant` exhaustion.
- A two-path **multi-fault precedence test** (bind-site src paired
  with invalid dest reports `invalid`, not `busy`) — mandatory, not
  optional: the check order becomes suite-pinned, not
  docstring-pinned (4.3BSD's rename history says documented order
  rots; see research review).
- `ruff` and `ty` clean over `src/vfs/base.py` and touched tests.
- No function in base.py returns a union other than `X | None`.
- `_route_fanout` body reads as its four phases; target ≤ 45 lines.

## Open questions

- ~~The `_refuse_target` fusion~~ — **resolved with owner
  2026-07-10: declined.** The deciding evidence, verified on the
  local mainline clone: both check halves co-fire at only one call
  site, and Linux keeps exactly this split — `may_delete_dentry`
  (entry policy, `fs/namei.c`) and `__is_local_mountpoint` (table
  state, `fs/namespace.c`) are separate named checks sequenced by
  the caller, never fused, with `may_delete_dentry` since exported
  standalone. The `may_lookup` precedent supports fused *policy*
  checks — which `_gate_entry` already is. Full record in Declined.
- ~~Research review~~ — **resolved 2026-07-10**: all three lenses
  support the total-producer / refusal-check split and the
  plan-object shape; no fatals. The recorded defense of the no-union
  rule lives in the research-review section above. ERR_PTR turned
  out to be C economics, not a design endorsement — where semantics
  beat registers, Linux itself uses the spec's split (`may_*`), and
  Plan 9 and 4.4BSD never adopted the union at all.
