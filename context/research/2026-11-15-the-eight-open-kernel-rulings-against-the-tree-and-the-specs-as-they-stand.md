# The eight open kernel rulings cost nothing to make today and cannot be made after the beta; the tree contradicts none of the kernel plan, and the rulings need three more words than were asked for

Clay chose roadmap story K1 as the next spec on 2026-11-15, asking "Can we work on another spec research, write, and review while we wait?" and picking "K1 kernel rulings" from the choices offered. K1 asks that the kernel's public names and argument families be decided and written down once. The decisions it waits on were listed in a decision record, ADR 087 of 2026-10-24, which left eight items for Clay to rule on; decision records were retired from the tree on 2026-10-30. One researcher checked each item against the tree and the twelve numbered specs that stand on the record, in about half an hour, with no database and no test run. The brief, the study and the retired record are in [the studies folder](studies/2026-11-15-the-eight-open-kernel-rulings-against-the-tree-and-the-specs-as-they-stand/00-brief.md). No intention: the work is one roadmap story. The spec that carries the rulings is [the kernel's public names and argument families are ruled](../specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md).

Labels: EXECUTED means a command ran on 2026-11-15 and the claim reports its output; READ means read in the file cited, at `08c372af` for vfs; INFERRED means reasoning from the two. Every claim below is from [the study](studies/2026-11-15-the-eight-open-kernel-rulings-against-the-tree-and-the-specs-as-they-stand/01-the-open-rulings-against-the-tree-and-the-specs.md), which gives the file and line or the command for each.

## Sources

vfs at `08c372af`: `src/vfs/base.py`, `ops.py`, `session.py`, `sync.py`, `params.py`, `results/envelope.py`, `results/kinds.py`, `models/rows.py`, `models/version.py`, and under `src/vfs/storage/backends/database/` the files `topology.py`, `staging.py`, `writes.py`, `versions.py`, `trash.py` and `maintenance.py`. The retired record, printed by `git show 3667fec2^:context/decisions/087-the-kernel-is-the-gate-and-everything-under-it-and-every-front-is-a-facet.md` and kept in the studies folder's `experiments/`. The numbered specs 167, 169, 171, 172 and 174 to 181 under `context/specifications/active/`. [The kernel memo](2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md) and [the OSTEP memo](2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md) with their studies. [The constitution](../standards/constitution.md), [the release standard](../standards/release.md) and [the roadmap](../standards/roadmap.md). No reference clone was opened and no web page read: the prior art is in the two memos.

## The answer

Every one of the eight items can be ruled today at the cost of edits alone, because no alpha has shipped, and none can be changed once the beta begins. The researcher's lean matched the record's on all eight. No pin of the record is contradicted by code. The rulings need three more words than the record asked for: the name of the flag that lets a move or a copy land on an existing file, the type of the paging key's field, and how a replayed replacing move is recognised. And story K1's three acceptance criteria cannot be met as the roadmap words them, because the record and the page they name are gone; the precedent since is that a spec carries each ruling as a numbered decision.

## 1. A ruling costs edits today and is closed at the beta

READ: the release standard lets an alpha change anything and a beta change nothing but bugs, with "no rename, removal or change of meaning", and the beta begins when the public surface is frozen. READ: `pyproject.toml` still says `0.0.22`. So the cost of each choice below is a count of edits, not of users (INFERRED).

## 2. The eight items: what stands today and what the other choice costs

| Item | Today | The other choice costs | The study's lean |
|---|---|---|---|
| 1. `delete` and `move`, or `remove` and `rename` | READ: `delete` and `move` at every layer, six definitions each; the class already has `remove_mount` and `remove_member`. | EXECUTED: about 470 edits for `delete` and about 290 for `move` in `src/` and `tests/`, and the strings in every `Result.ops`. | Keep. Ten systems in the earlier studies split three ways on the removal word. |
| 2. The paging key: a field of `Result`, or a separate return | READ: `Result` has three fields and no key; merges drop extras. | EXECUTED: 424 call sites of `ls`, `tree` and `glob`, and twelve public signatures; READ: the constitution says every verb returns the one result type. | A field. |
| 3. Flat names, or groups as namespaces | EXECUTED: 25 flat verbs on each of four classes; the groups are declared nowhere in code. | EXECUTED: about 470 call sites, up from the 381 spec 181 counted; sixteen new objects. | Flat, with the groups named once. |
| 4. Whose identity survives `move(replace=True)` | READ: no transfer replaces an occupant; every occupant refuses `exists`, a tombstoned one included. The schema holds one row per path and per parent and name, tombstones included. | INFERRED: keeping the source's identity needs a schema change, or destroys the replaced file with no undo. | The destination's. |
| 5. The hash threshold and the integrity kind | READ: the threshold is built, `MEASURE_OFFLOAD_BYTES = 100_000`; no integrity kind exists among the 24. | INFERRED: a top-level kind gives an unknowing caller no family to fall back on; plain `unavailable` says "retry" for a fault no retry heals. | Keep 100,000; the child `vfs.unavailable.integrity`. |
| 6. The replay row's life and the withheld hint | EXECUTED: nothing built: no request key, no replay store, no MCP adapter. | INFERRED: one hour contradicts the 24 hours the roadmap gives the ask and run ledgers on the same key; setting the hint lets a host resend a move that already landed. | 24 hours; withhold. |
| 7. `overwrite=` leaves `write` | EXECUTED: `overwrite: bool = True` on six signatures; 66 uses in 15 test files; one how-to page teaches it. | INFERRED: keeping it freezes two spellings of one rule beside `if_absent=`. | It leaves. |
| 8. The hot window and the history verb's name | EXECUTED: nothing built: no pack, no reader of the versions table, no history verb. | INFERRED: `history` collides with the shell's builtin and the session's field; a window of 0 makes the most recent undo read up to ten rows. | `PACK_HOT_ROWS = 1`; `versions`. |

Two facts bear on item 4 beyond the table. READ: POSIX keeps the source's inode on a rename over an existing file, and the test suite the earlier study read expects it. READ: a write that lands on a tombstoned file revives it "whatever `overwrite` says", and a write over a live occupant leaves the occupant's owner in place. What a revive hands a second caller was not executed by this study; [the deletes memo](2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity.md) runs it.

## 3. Three more words the rulings need

The flag's name. EXECUTED: `overwrite=` is written 43 times in 12 files under the active specs: 22 name a flag on `move` and `copy` and 21 name `write`'s. `replace=` is written 10 times in four files. READ: the roadmap says spec 181 writes `replace=`; it does not, its lean is `overwrite=` on the transfers "because `write` already has it". INFERRED: if the word leaves `write`, that reason is gone, and the two flags have opposite defaults: `write` replaces unless told not to, a transfer refuses unless told to.

The field's type. READ: spec 176 types the key as a path, gated and rebased across mounts like a row's path. Specs 175 and 180 say their scrub, sweep and versions keys "ride" that field as opaque strings. INFERRED: a path field cannot carry them, so the ruling must say the type.

A replayed replacing move. READ: spec 177 recognises a replayed `move` by finding the same `entry_id` at the destination. INFERRED: that holds when the source's identity survives a replace and fails when the destination's does.

One word beside these. READ: the constitution's Article 1.5 names the write precondition `if_revision=`; specs 174 and after write `if_version=`, and the row's field is `version`.

## 4. The record and its page are gone, and K1's criteria name them

READ: commit `3667fec2` removed `context/decisions/` and `context/architecture/`. EXECUTED: the active specs and the standards still write the record's number 151 times in 14 files, and cite 48 retired records 495 times in 35 files. K1's first criterion asks for a status line on the record and its third for an empty list on the architecture page; neither file exists. Its second asks that a search of the active specs for `overwrite=` find only spec 174's note; meeting it means editing 43 places, among them a recorded probe output and the checked-off record of a built spec (INFERRED).

READ: four rules written since say where a ruling goes. The frozen status page says a record's pending pins "are answered in the spec that implements them". The process page says a numbered spec is converted in place when it is picked up to build. The two-faces spec decided "the active numbered specs are not rewritten", and the verb-rename spec decided an active spec is "built against the new names with its text unedited". So the precedent is one spec that carries each ruling as a numbered decision with a table for reading the old words (INFERRED).

## 5. The seventeen pins: none contradicted by code

READ, pin by pin in the study's table. Built as the record says: the gate, the query verbs inside the kernel for the one backend, the absences of pin 4, path-ordered locks and jittered retries, flat names, the tombstone, the write-path hash threshold. Not built: every new argument, `entry_id` as a column, the read-side hash check and `scrub`, the replay store, `pack` and the bounded sweep, the access-path family, the engine's error code in a result, a replacing move. Stale by words only: pin 1 and pin 7 name verbs since renamed (`glean`, `graph`, `reindex`), and the README's group names differ from pin 1's. Overtaken: pin 15's table of eight axes is carried by no standard, and `AGENTS.md` now has the reference deployment in its place.

## 6. Sixteen undecided choices stand outside the eight

EXECUTED: specs 174 to 181 hold 28 clarification markers. The eight items and the flag's name answer 12. Sixteen remain, and at least four name a public argument or a default: the listing's default page size, the key's shape, and whether `observations=` becomes a list of paths (INFERRED). So the stories after K1 cannot freeze every name on these rulings alone; each numbered spec settles its own when it is converted.

## What this memo does not settle

- Whether tombstones are designed correctly, and how a replacing move keeps the moved file's identity. [The deletes memo](2026-11-15-deletes-tombstones-and-a-move-that-keeps-its-identity.md) carries it.
- What agent harnesses call the removal and move operations. The experiment: the study the verb-rename spec ran for `search` and `traverse`, run for `delete` and `move`.
- Whether 100,000 bytes holds on an x86 machine of the class CI uses. The experiment: `offload_threshold.py` from the OSTEP studies folder, run there with the pool at that machine's core count.
- Whether 24 hours is long enough for a resume. The experiment: a read of how long the durable-workflow hosts in the catalog keep a resumable step.
- Whether the three probes the record rests on still reproduce at this commit. The experiment: the probe scripts under the OSTEP studies' `experiments/`, run on the in-memory store.

## One line

All eight kernel rulings can be made today for the price of edits, the tree contradicts none of the plan, and the spec that carries them must also name the transfer flag, type the paging key and say how a replayed replacing move is known.
