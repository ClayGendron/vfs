# Study: Cross-mount copy, where the router does read plus write for files and says so when it did

Spec folder: `context/specifications/active/160-cross-mount-copy-as-read-plus-write/`, which holds `spec.md` alone (39 lines; no `plan.md`, no `tasks.md`). EXECUTED: `ls` of the folder. Tree read at `3166469`, a descendant of `0ed462f` whose only later commits are under `agents/` and docs. EXECUTED: `git rev-parse --short HEAD`, `git log --oneline`.

## Verdict

live-unplaced. Nothing of it is built: `_route_two_path` still refuses every pair whose endpoints resolve to different bindings, files and directories alike, for `copy` as for `move` (READ, `src/vfs/base.py:2421-2424`), and `tests/base/test_dispatch.py:206-216` pins that refusal for both verbs. The roadmap names neither the spec nor the behaviour, so no story or cut-list row places it (EXECUTED: `grep -n "160\|cross.mount\|cross_mount\|EXDEV"` over `context/standards/roadmap.md` finds no hit for this subject).

The gap is worth a spec. Four pieces of evidence, each READ:

- The README's Known-limits list states the refusal and names this spec as the fix (`README.md:139`).
- The `cross_mount` kind's own hint tells a caller to "copy then delete across mounts" (`src/vfs/results/kinds.py:243-247`), advice the router refuses at HEAD. The hint is wrong today, and this spec is what makes it true.
- The shell spec maps `cp S D` to `copy` (`context/specifications/active/167-the-shell-pipeline-core/spec.md:102`), and spec 169 maps `cross_mount` to exit 75 `XDEV` (`context/specifications/active/169-programs-the-index-and-the-vfs-views/spec.md:207`). So `cp` between two mounts in vfs's shell would fail where GNU `cp` copies across filesystems. Story F4 (gate b) builds those program forms (`context/standards/roadmap.md:631-639`).
- The integration memo confirms the refusal between two `read_write` mounts and names this direction (`context/research/2026-10-08-smartowl-workspace-integration-issues.md:180-185`, `:227`).

## Against the tree

The problem statement is still true at HEAD:

- READ: `src/vfs/base.py:2374-2439`. `_route_two_path` resolves both terminals and returns `ErrorKind.cross_mount` at `:2424` when the binding paths differ. That happens before `_gate_entry` at `:2427`. Groups are keyed by the source binding alone (`:2433`), and dispatch runs under `_gather_settled` (`:2436-2439`).
- READ: `src/vfs/base.py:2388-2396`. The docstring still says "the EXDEV rule; no silent copy-and-delete", that all pairs are validated up front, and that atomicity stops at validation.
- READ: `src/vfs/base.py:1248-1259`. The public `copy` is `copy(src, dest, copies=, *, authority=)`, with no `overwrite=` and no `replace=`.

The spec's prerequisites stand at HEAD:

- READ: `src/vfs/models/entry.py:236-251`. `Entry(data=…)` sets `source="bytes"`, sniffs `mime_type` and starts `render_status="pending"`.
- READ: `src/vfs/storage/backends/database/reads.py:106`, `:868-893`, `:1152-1154`. The body fields are `content` and `data`, and a bytes row's `content` is its rendering.
- READ: `src/vfs/base.py:960-1016`. `write(entries=, *, path=, content=, data=, overwrite=True, parents=, authority=)` routes through `_route_entry_batch`.
- READ: `src/vfs/base.py:2751-2800`. `_gate_entry(binding, op, *, write_rels=, read_rels=, subtree=)` already gates a read-only rel for a copy's source.
- INFERRED: no landed archive spec from 2026-10-29 onward touched two-path routing's cross-mount branch. EXECUTED: `grep -rln cross_mount` over `context/specifications/archive/2026-1*` finds two hits, and both are unrelated (a layer-map row naming "the cross-mount merge" of search, and a naming note).

These later landings changed the ground under the spec. None does any part of it.

- READ: `src/vfs/storage/backends/database/topology.py:1-23` and `:450-562`, and `context/specifications/archive/2026-11-14-a-mutation-is-authorized-for-the-rows-it-acts-on-at-its-commit-point.md`. An in-mount copy is now judged against the caller's rights at its commit point (`authorized.py`). It refuses a tombstoned occupant `exists` with the trashed hint, and it fails the batch whole on any per-pair error.
- READ: `src/vfs/storage/backends/database/topology.py:92-108`. An in-mount copy carries the render stamps (`render_status`, `render_source_hash`, `render_generation`, `render_detail`, `render_units`) and `media_width`/`media_height` verbatim. It does not carry `external_id` or edges.
- READ: `src/vfs/storage/backends/database/staging.py:285-310`. `write(overwrite=False)` onto a tombstoned file revives it, "whatever `overwrite` says". It refuses `exists` only when there is a live occupant.
- READ: `context/standards/roadmap.md:966`. Spec 161 is dropped, because its write half landed with the tombstone mint. So the spec's "161 if it lands first" dependency has already been met.

## Where the roadmap places it

- Nowhere. No story heading, no state row, no row in section 15 (`context/standards/roadmap.md:1040-1063`) and no D-row names cross-mount copy (EXECUTED, the grep above).
- Adjacent stories it touches, each READ in `context/standards/roadmap.md`:
  - K2 (`:142`, gate b): `if_absent=` replaces `write(overwrite=False)`.
  - K4 (`:164`): `tree` pages, which matters for the recursive composition rule 1 prescribes.
  - K5 (`:174`): the replay key, which a cross-mount copy would carry to two mounts.
  - K10 (`:219`): under `strict=True`, `copy` needs no stamp on the source.
  - H2 (`:300-301`): `copy` accepts `plan=True`.
  - D4 (`:484`): `copy` gets a 10k statement-count pin.
  - F4 (`:631-639`): `cp`, and `replace=` on transfers.
- INFERRED: the natural home is domain A beside K2 and F4, at gate b. The reason is that F4's `cp` and the `cross_mount` hint are both b-gate surfaces. That placement is not in the roadmap. Needs a ruling: place it as a domain-A story at gate b, at gate f, or list it in section 15 as 0.2.

## Units proposed

One unit. The spec is one landing: one branch in `_route_two_path`, a two-pass grouping, the info record, the README bullet and the `cross_mount` hint.

- Slug: `a cross mount file copy is a read on one mount and a write on the other`.
- Title: "`copy` of a file across mounts reads the source with the caller's authority, writes it at the destination through that mount's own gate, and reports each pair as two operations."
- Gate: unplaced (the lean above is b).
- Depends on: K1 (the ruling of 2026-11-15, decision 7), D7. It does not need K2 first: it can call `write(overwrite=False)` and K2's landing respells the call `if_absent=True`, as decision 12's table says (READ, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md:105`).
- Rewrite depth: amend. The design stands. Line references, two precedents, the parity claims of rules 3 and 6, the memory profile and the argument names have changed.

## Open choices, each verified

The spec carries no `[NEEDS CLARIFICATION]` marker. Its status reads "draft", and rule 6 says "the earlier marker on metadata is resolved" (READ, `spec.md:3`, `:25`). Each choice below is a decision the spec takes as a lean, never ruled, or a fork it leaves implicit.

1. **Files cross and directories do not; a recursive copy is composed by the caller from `tree` plus `copies=` after `mkdir`** (rule 1). HOLDS.
   - Precedent: EXDEV exists because the kernel will not do a cross-device copy itself. `rename(2)` returns EXDEV across filesystems, and `cp`/`mv` do the copy in user space (POSIX `rename()`, The Open Group Base Specifications Issue 7).
   - Precedent: the `cross_mount` hint already prescribes copy-then-delete (READ, `src/vfs/results/kinds.py:246`).
   - Amend the composition note: under K4, `tree` pages on `next_after` (READ, `roadmap.md:164`), so the caller walks pages.
2. **The read projects `{kind, source, mime_type, content, data}` and the write body is chosen by `source`** (rule 1). HOLDS.
   - Precedent: `Entry` refuses `content` on a bytes-sourced entry (READ, `src/vfs/models/entry.py:347-348`).
   - Precedent: a bytes row's `content` is a rendering (READ, `reads.py:868-893`).
3. **Not atomic: the result is the write's result relabelled `ops=("copy",)`, plus one info record per pair, `kind=cross_mount, severity=info`, carrying `data={src, dest, source}`** (rule 2). HOLDS-AMENDED.
   - Precedent for an info record that reuses a refusal kind to report a coverage fact: `_skip_entry` (READ, `src/vfs/base.py:3060-3074`, `unsupported` at `Severity.info`).
   - The spec's cited precedent, `indexing.py` L349-354, no longer holds an info record. The nearest is `indexing.py:226` (READ).
   - Amended text: cite `base.py` `_skip_entry`. Name the data key for the body kind `body_source`, not `source`, because `ResultError` already has a `source` field that holds a provenance path (READ, `src/vfs/results/envelope.py:116-120`).
4. **A read refusal on one pair skips that pair's write and leaves the rest of the batch to dispatch** (rule 2). Needs a ruling.
   - What the tree does: an in-mount copy fails the batch whole on any per-pair error (READ, `topology.py:21-22`), and a database write applies its plan only when it holds no errors (READ, `roadmap.md:249`).
   - What the spec does: it fails per pair across mounts, and validation already stops at the router (READ, `base.py:2393-2396`).
   - The options: (a) per pair, as the spec has it; (b) any read refusal fails every cross-mount pair of the batch before any write dispatches, which matches the in-mount ladder.
5. **No displacement: `overwrite=False`, so an occupied destination refuses `exists` "exactly as in-mount copy does"** (rule 3). This choice has two parts.
   - (a) Refusing a live occupant: HOLDS-AMENDED. Decision 7 rules that transfers refuse by default and that `overwrite=` leaves `write` (READ, the rulings spec, `:71-73`, `:105`; `roadmap.md:1079`). Amended text: "the router writes with `if_absent=True` from the landing of spec 174, `overwrite=False` until then. When F4 adds `copy(replace=True)`, a cross-mount replacing copy is a write over the destination row, which keeps the destination's identity, as decision 6 says of a replacing `copy`" (READ, the rulings spec, `:69`).
   - (b) A tombstoned destination: Needs a ruling. The parity claim FAILS at HEAD. An in-mount copy refuses a tombstoned occupant `exists` with the trashed hint (READ, `topology.py:16-17`, `:277-281`). `write(overwrite=False)` revives it (READ, `staging.py:287-289`), and spec 174 keeps that revive under `if_absent=True` (READ, `context/specifications/active/174-write-preconditions-and-the-guarded-append/spec.md:138-139`). The options: (i) match the in-mount ladder, which needs the destination storage to report the tombstone before the write; (ii) accept the revive and say so, with the tombstoned body kept as a version row. Where a replaced row lives belongs to the deletes spec (READ, the rulings spec, `:144`).
6. **`move` is unchanged and keeps EXDEV** (rule 4). HOLDS.
   - Precedent: POSIX `rename()` returns EXDEV.
   - Precedent: the kind hint (READ, `kinds.py:246`).
   - Precedent: decision 9 lists "a cross-mount `move`" only as a body-reading verb, for spec 175 to settle (READ, the rulings spec, `:81`).
7. **Permissions compose as two ops: `read` on the source binding, and `write` plus composed write permission at the destination rel** (rule 5). HOLDS.
   - Precedent: `_gate_entry` already takes `read_rels` and `write_rels` separately (READ, `base.py:2775-2800`).
   - Precedent: row rights are judged at the commit point by each storage's own verb (READ, the 2026-11-14 archive spec).
8. **What travels: body, kind and declared `mime_type`. Not `external_id`, edges or render stamps; the destination re-renders** (rule 6). HOLDS-AMENDED.
   - The behaviour holds, because the destination's write mints a fresh row and starts `pending` (READ, `entry.py:249-250`).
   - The framing "parity with in-mount copy" FAILS: an in-mount copy carries the render stamps and the media dimensions verbatim (READ, `topology.py:92-108`).
   - Amended text: "A cross-mount copy carries what a write carries. The render stamps, the media dimensions, `external_id` and edges stay behind, unlike an in-mount copy, which carries the render stamps and the dimensions."
9. **Every body of a batch is held in memory at once, stated as an honest profile and not a limit** (Scope). FAILS against the reference deployment and the production posture.
   - The arithmetic: the mean file is 0.3 to 0.7 MB (READ, `AGENTS.md`, the reference deployment table). A 10,000-file cross-mount batch would therefore hold about 3 to 7 GB. AGENTS.md requires every read/write builder to stay bounded at 10,000 files.
   - The precedent determines the alternative. An in-mount copy pages bodies with `byte_chunked` under `BLOB_PAGE_BYTES` (READ, `topology.py:527-562`; `src/vfs/storage/backends/database/dialects.py:103`). Amended text: "the router pages cross-mount pairs by the source's recorded `size_bytes` under a byte budget (one `read`, then one `write`, per page per mount), so at most one page of bodies is in memory."
10. **Grouping twice: one batched `read` per source mount, then one batched `write` per destination mount** (Scope). HOLDS.
    - Precedent: the write path already groups per binding (READ, `base.py:2494-2545`).
    - The spec's cited precedent, a router-internal `self.read(observations=…)` at `base.py` L1845, is gone. EXECUTED: `grep "await self\.(read|write|stat)("` over `base.py` finds no hit. The nearer form is to call `_route_single("read", …)` and `_route_entry_batch` (READ, `base.py:915`, `:1004`).
11. **`161 if it lands first`** (Depends on) and **"or inline under 159"** (rule 1). Both already-ruled.
    - Spec 161 is dropped and its write half has landed (READ, `roadmap.md:966`).
    - Render at write (159) is 0.2 unless D21 says otherwise (READ, `roadmap.md:1053`, `:1093`). The unit states `pending`.

## What is stale

- `_route_two_path L2419–2477` and the EXDEV refusal at `L2466–2472`. Now `src/vfs/base.py:2374-2439`, with the refusal at `:2424` (READ).
- `_route_pairs` coerces input, L2504. Now `_coerce_two_path` at `base.py:2441-2455` and `_route_pairs` at `:2457` (READ).
- `entry.py L236–243` and `Observation.data L443`. The module is now `src/vfs/models/entry.py`: the derivation is at `:236-251` and `Observation` at `:419` with `data` at `:453` (READ).
- `reads.py L100–117 and L525–539`. Now `reads.py:106` (the body fields) and `:868-893` (the rendering served as `content`) (READ).
- `topology.py L590–593` (the `exists` refusal). Now `topology.py:274-281` (`_occupied`, with the trashed hint) and `:186-191` (READ).
- `indexing.py L349–354` (the info-record precedent). That range now holds the chunk publish. The info record is at `indexing.py:226`, and the better precedent is `base.py:3060-3074` (READ).
- `base.py L1845` (`self.read(observations=…)`). No such call exists (EXECUTED, the grep above).
- `tests/base/test_dispatch.py L169` (`test_two_path_cross_mount_rejected`). Now `:206-216`, parametrized over `move` and `copy`. The batch test at `:219-227` mixes a `move` pair (READ).
- `overwrite=False` on the write. Read it as `if_absent=True` from spec 174's landing (READ, the rulings spec, `:105`).
- "161 if it lands first". Spec 161 is dropped (READ, `roadmap.md:966`).
- "On landing: remove the README's cross-mount Known-limits bullet (153)". The bullet is at `README.md:139`, and spec 153 is archived (READ; EXECUTED `ls context/specifications/archive`).
- "`scripts/ci.sh 3.13` green". The gate is `scripts/ci.sh` with 3.13 as its default leg (READ, `AGENTS.md`, Tooling).
- The `Owner:` header names a person. The nine-section shape carries no owner line (INFERRED).

## Notes for the conversion

- Add two edits to the unit's scope:
  - The `cross_mount` hint: "Move within one mount, or copy then delete across mounts." Keep it, but make it true for files, and say that a directory copy across mounts is composed from `tree` (READ, `kinds.py:246`).
  - The `_route_two_path` docstring's "no silent copy-and-delete" sentence: restate it for `move` only.
- Group the cross-mount pairs after the up-front loop. Today the loop returns at the first cross-mount pair (READ, `base.py:2423-2424`). The file-kind check needs the source's `kind`, which only a dispatch can see. So a directory source is refused after the read, at the source path, not in the validation loop. State that ordering in the spec.
- In-mount pairs in the same batch keep their whole-batch atomicity per mount. The spec should say that a mixed batch can land its in-mount pairs while a cross-mount pair is refused. It follows from `_gather_settled` (READ, `base.py:2436-2439`).
- Add criteria the spec lacks:
  - a 10,000-pair cross-mount `copy` whose statement count is a named formula under the byte page and `membership_budget`, in story D4's family (READ, `roadmap.md:484`);
  - `copy(plan=True)` across mounts issues reads but zero mutation statements, if H2 lands first (READ, `roadmap.md:300-301`);
  - a keyed cross-mount copy stores one slice per mount, as spec 177 already says of cross-mount batches (READ, `context/specifications/active/177-replay-the-contract-and-the-request-key/spec.md:198`).
- K3's integrity check refuses a damaged body on read. A cross-mount copy's read therefore refuses a damaged source, and decision 9 leaves `copy`'s answer to spec 175 (READ, the rulings spec, `:81`). Cite it, and do not decide it here.
- Spec 174 already expects this design: "A cross-mount copy passes `Entry` rows read from another mount" (READ, `context/specifications/active/174-write-preconditions-and-the-guarded-append/spec.md:99`).
- Decided 2026-11-15: transfers use `replace=`, default refuse; a replacing `copy` keeps the destination's identity (the rulings spec, decisions 6 and 7). The converted spec reads its rule 3 through these.
