# 053 — Router Review Cleanups: Small Findings from the base2 Line-by-Line

- **Status: closed 2026-08-25** (the active-spec closure pass). Item 1
  ruled rather than rewritten: every `assert` in `src/` (five in
  `base.py`, one in `pattern_matching/grep.py`, re-surveyed 2026-08-25)
  is a type-narrowing statement that follows an ingress gate which
  already refused the bad shape — none is a validation the caller can
  reach, so `python -O` changes no behavior. The rule is recorded in
  `CLAUDE.md` (*Code conventions*: asserts narrow, never validate) so
  the pattern stays consistent. Items 2–4 obsolete or stale as
  triaged below; item 5's remote-staleness note belongs to the wire
  contract (045) and is carried there by reference. No code change.
- **Status (original):** draft — collects the minor findings from the 2026-07-07
  base2 review; each item is independently landable.
  Re-triaged 2026-07-10 against post-069/071 `base.py`: items 3 and 4
  are **obsolete** (the spine and `SPINE_READ_OPS` were deleted by
  056/069); item 2 is **stale** (`_merge_results` is gone — re-derive
  against `_merge_fanout` before acting); item 1 **survives** (bare
  asserts remain in `_route_single`/`_route_two_path`, though the
  named `src_prefix == dest_prefix` assert no longer exists); item 5
  survives as a note, but its call sites are renamed/gone.
- **Date:** 2026-07-07
- **Owner:** Clay Gendron
- **Kind:** chore (correctness hygiene; no behavior change intended
  except where noted)
- **Depends on:** —
- **Related:** 050 (spine/input-shape divergence), 051 (fan-out
  deadline), 052 (max_count semantics), 039 (`run` permission tier) —
  the *large* findings, specced separately

## Findings

### 1. Bare `assert`s on routing invariants

`_route_two_path` holds its same-terminal-⇒-same-prefix invariant with
a bare `assert src_prefix == dest_prefix`; `_route_single` has an
`assert path is not None`. Both invariants genuinely hold (the mount
graph is a tree; the XOR check precedes the assert), but `python -O`
strips them, and the first guards the correctness of gating both
endpoints with one call. Either make the first a real
`VFSErrorKind.internal` guard or restate why `-O` is out of scope for
this codebase (and then keep asserts consistently).

### 2. Overlapping self-scopes double-dispatch, and the losslessness claim

In `_route_fanout` with `paths=`, a spine scope (e.g. `/data`) and a
non-spine self scope (e.g. `/data/sub` when no mount sits below it)
both dispatch to self storage — two local calls whose row sets can
overlap. The path-keyed union in `Result.__or__` dedups the rows, so
the output is right, but `_merge_results`'s docstring argues
losslessness *from* "terminals have disjoint mount prefixes," which
this case violates (same terminal, twice). Fix either side: subsume
self scopes the way expanded mounts are subsumed (drop self scopes
covered by a spine expansion / by each other), or correct the
docstring's argument to include the same-terminal overlap case.

### 3. Spine-synthesized rows ignore `columns`

`_spine_row` and `_spine_ls`'s synthesized observations always carry
`path`/`kind`/`description`, whatever the caller's `columns`
projection requested; `_spine_read`'s `stat` arm drops `**kwargs`
silently. Harmless today, but it means a column-projected `ls` returns
differently-shaped rows for stored vs. synthesized entries. Decide:
synthesized rows honor the projection (null out unrequested fields),
or the projection contract states that identity fields are always
present. Cheap either way; do it before a wire consumer bakes in the
accident.

### 4. Dead grouped-`tree` arms in the dispatch funnels

`SPINE_READ_OPS` includes `tree`, so `_dispatch_grouped_observations`
nominally handles grouped `tree` — but the public `tree(path, ...)`
has no observations parameter, so the path is unreachable; worse,
`_call_remote`'s remote leg would call `fs.tree(observations=...)`,
which no signature accepts. Unreachable by construction today, a
`TypeError` trap if `tree` ever grows a row-shaped input. Either give
the grouped path an explicit "tree takes no observations" rejection or
note the invariant where `SPINE_READ_OPS` feeds the grouped dispatch.

### 5. `capabilities()` recomputation and the remote-staleness question

`capabilities()` walks the entire subtree, and a single dispatch may
compute it several times (`_gate_terminal`, `_storage_answers`,
per-mount fan-out checks, `_spine_tree` descents). Fine at
dozens-of-mounts scale — do not optimize yet — but two things are
worth recording: (a) there is no memoization story if it ever shows up
in a profile (the mount table changes rarely and under a lock, so an
invalidation hook is natural); (b) for a remote/MCP mount the
"derived from reality" property stops at the proxy — its override
answers from a cached claim, and the no-probe rule then trusts it.
(b) belongs to the wire-contract work (045/034); it is noted here so
the derived-honesty docstring doesn't over-promise.

## Acceptance criteria

- Each item resolved by a small commit or an explicit "won't fix"
  note added to this spec with the reason.
- No public-surface behavior change except item 3 (if projection is
  chosen) — everything else is guards, docstrings, and dead-path
  hygiene.
