# 075 — Trash normal-fs parity: one scope, ordinary writes

- **Status:** shaped — drafted 2026-07-18 directly from accepted ADR
  014; no open markers. Ready for plan.md.
- **Date:** 2026-07-18
- **Owner:** Clay Gendron
- **Kind:** contract change (namespace scoping on every read and write
  verb of `DatabaseStorage`); code removal + test rewrite, no schema
  change
- **Depends on:** ADR 014 (binding), 072 (the landed read/write
  pipelines this re-scopes)
- **Relates to:** the future delete/restore/sweep spec (implements ADR
  014 pins 3–5 against the posture this spec lands); spec 012 ingress
  validation (trash paths flow through the ordinary grammar)

## Intent

Spec 072 §9 made `/.vfs/trash` a reserved scope: an unconditional read
filter (`descent.py` `trash_filters`) hides it from every verb, a
plan-time gate (`writes.py` `outside_trash`) refuses writes into it,
and error shapes conceal its structure. ADR 014 retires that model for
normal-fs parity: trash is an ordinary subtree that inherits the meta
scope — hidden from default enumeration because `/.vfs` is, served in
full when anchored, writable under the standard gates. Deletion keeps
hiding deleted files at their original paths via the reparent's path
rewrite (ADR 004), which never depended on the filters.

One sentence: **`/.vfs/trash` is just a directory — the meta scope is
the only namespace rule, and delete/restore/sweep are conventions atop
plain verbs, not a second visibility regime.**

## Shape (pinned)

1. **The trash read scope leaves the system.** `trash_filters` and its
   call sites go: point reads (`reads.py`), enumeration
   (`liveness_filters` reduces to the meta rule alone), the write
   plan's committed snapshot (`writes.py` `_fetch_committed`), and
   miss classification (`descent.py` `classify_misses`). `TRASH_ROOT`
   stays as the conventional location the future delete spec targets.
2. **The write gate leaves the system.** `outside_trash` and `in_trash`
   go; `write`/`mkdir`/`edit` targets under `/.vfs/trash` pass the
   ordinary gates (parent rule, key budget, kind checks) with no
   trash-specific arm. A write there is exactly a write anywhere else
   in the meta subtree.
3. **Trash rows are fully observable when anchored.** `read`, `stat`,
   `ls`, `tree`, `glob`, `grep` serve trash-side paths under the same
   direct-anchor rule as the rest of `/.vfs`; default-scope
   enumeration of `/` still excludes the whole meta subtree
   (unchanged). Descent may name trash components in error shapes; the
   concealment guarantee is dropped, not weakened — the old
   invisibility tests are rewritten to pin visibility, none deleted
   silently.
4. **Docstrings state the one-scope model.** The `descent.py` module
   docstring (two-scope filter, "ingress never admits"), the
   `writes.py` module and gate docstrings, and the rows-side comments
   describing a reserved prefix are rewritten to the parity contract;
   no comment may continue to claim trash is unreachable.
5. **The delete-spec inheritance is recorded, not built.** This spec
   changes no delete/restore/sweep behavior (all stubs today). The
   harness rows the future spec must satisfy under parity are written
   down in its backlog: original path classifies `not_found` after
   delete (by rewrite alone); restore verb on a row without restore
   metadata classifies `invalid`; plain `move` out of trash restores
   anything; the sweep destroys expired buckets wholesale and
   surfaces skipped foreign rows in its result.

## Acceptance criteria

- `trash_filters`, `in_trash`, and `outside_trash` appear nowhere in
  `src/`; `liveness_filters` carries only the meta exclusion.
- A batch write of `/.vfs/trash/2026-07-18-10/x.txt` with
  `parents=True` succeeds, mints the bucket directory chain, and reads
  back byte-identical through `read`; `stat` and an anchored `ls` of
  the bucket serve it; `mkdir` and `edit` under trash likewise take
  the ordinary paths (including their error arms — `exists`,
  `wrong_kind`, parent-rule refusals — with no `invalid`-for-trash
  arm reachable).
- Default-scope `ls /` and `tree /` still surface nothing under
  `/.vfs`; an `ls /.vfs` anchor lists `trash` beside other meta
  children when rows exist there.
- Misses under `/.vfs/trash/...` classify through the standard descent
  ladder (missing ancestor → `not_found` at that component), identical
  in shape to any other meta path — the
  uniform-regardless-of-bucket-existence concealment test is replaced
  by this contract.
- The `tests/` trash family asserts the new posture: visibility when
  anchored, writability, and meta-default hiding; the suite is green
  and `ruff`/`ty` stay at zero across `src/` and `tests/`.
- No docstring or comment in `src/` describes trash as reserved,
  invisible, or write-refused.

## Out of scope

- Implementing delete, restore, or the reclamation sweep (future spec;
  ADR 014 pins 3–5 are its contract).
- The memory backend (no trash concept today; it adopts the same
  observable contract when it grows delete).
- Any schema change — `original_parent_id`/`original_name` and the
  ULID in-bucket naming from 072 §9 stand unchanged.
