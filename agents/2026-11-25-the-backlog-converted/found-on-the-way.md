# What the cross-check of the backlog specs found that no spec settles: six rulings, twelve defects on dev and seventeen pieces of work with no owner

Each of the 72 specs of this conversion was written against `dev` at `27f3d24d`. The 36 written first were then checked against the specs written after them, each by a reader that ran small probes on `dev`'s code. This page lists what those checks found and could not close inside one spec. Every item is also stated in the spec that found it, under its Choices to confirm, its Scope, Out, or its Not checked; the unit key in brackets names that spec, and [state-on-dev.md](state-on-dev.md) maps a key to its directory. "Run" means a probe executed on `dev`'s code on SQLite or the in-memory storage. Nothing here was run on Postgres.

## Rulings the specs wait on, or take a side on that a ruling can overturn

1. **Whether a row carries the entry's permanent id.** The unit was planned as "every row reports the entry's permanent id and its owner". The spec decides the opposite: no row carries `entry_id`, and a row's `vid` names the entry at its version. The kernel ruling it rests on gave as its reason that a caller holding an id to a moved file still holds it afterwards; a `vid` cannot tell the same entry at a later version from another entry. Leaving the id off is the additive side, and the replay table and the replace argument follow it. [181-2 choice 1; 177-1; 167-7]
2. **Whether `set_posture` is a keyed verb.** Eleven keyed verbs answer a resend exactly; a twelfth needs a posture change that can be resumed and a different promise for unfinished work. No side is taken and the keyed `set_posture` waits. The replay table is written to hold either way. [177-3; 177-4; 177-1 decision 19]
3. **Who calls retention.** The deployment by an explicit call, the rebuild, or a job. An unattended caller removes data in deployments that never ask for retention today, so no side is taken. The pass is written to hold for any caller. [180-5 choice 1; 180-4 decision 22]
4. **Which of `tree` and `ls` is right at a depth bound.** Run: under `max_depth`, `tree` leaves out a hidden directory that is the road only to rows deeper than the bound, and `ls` lists it, in 2 of 12 comparisons in a fixed world and 14 of 432 over random grant worlds. The difference is pinned and neither verb is changed. [181-4 choice 4; 179-10 decision 5]
5. **Smaller choices that wait on a result or a ruling.** What a bare backend must provide for a composed read, copy and edit [179-10]; the action log's transaction seam, which story H0 has no spec for [169-3; 170-4]; whether `run` is a public tool on the wire, decision D63 [171-1]; which exit status an interrupted stage reports, 75 or 149 [167-10]; the result of the D49 spike, which decides the JavaScript guest's engine [172-3; 169-4 decision 12]; which awk is shipped [169-5]; the owner column of a bare row in `ls -l`, which clashes with a built spec of `dev` [181-2].
6. **What a Python stage's fuel pays for.** Run on the pinned runner: importing NumPy and pandas costs about 4.6 billion fuel units, more than twice the 2 billion a stage the archived budget allows, so no script that imports them could run under it. The spec keeps 2 billion and starts each stage from one image of the import made per process, from which the outcome's CSV job costs about 10 million. The other side is no image and a default near 10 billion, which charges every stage about 2.3 seconds of a core before its first line runs [172-1, choice 4].

## Defects on dev's code, each run

1. `grep` with `allow_scan=True` over a text body whose stored bytes are not UTF-8 raises a raw `UnicodeDecodeError` on SQLite, with no result. No unit carries it. [175-1]
2. On a SQLite database whose text encoding is UTF-16, `write` and a whole `read` are right, and `grep` for a word the file holds answers success with no row. Nothing under `src/vfs` reads the database's encoding. No unit carries it. [178-1]
3. `sweep("/.vfs/trash")` raises a raw `OverflowError` when `trash_days` is 800,000 or more. [180-4 decision 23 clamps it]
4. `sweep` leaves orphaned version rows: all six in a world with residue in three families. [180-4 reclaims them]
5. A `copy` that loses its redrives answers a `conflict` whose message holds the source's stored entry id. [181-2 decision 15]
6. An `Entry` handed an `entry_id` key drops it silently and the write succeeds. [181-2 decision 11 refuses it]
7. A write of the recorded bytes over a damaged or missing body is dropped as `unchanged`, and the damage stays. [175-2 decision 6]
8. A create-only write names an occupant's version and content hash to a caller for whom `stat` is `not_found`, in one state only: a stored label lower than its folder's posture with no relabel pending. That state was reached by editing the database, and no verb was found to produce it. With settled labels the hash goes only to a caller who may read the file, because `add` sits above `read`. [177-1 decision 21 judges the occupant at `read`]
9. A shell line prints `Invalid argument` for any refusal of the `unavailable` family: a damaged body, a failed write, a commit in doubt. The shell maps a refusal by its exact kind and its table has no row for the family. No unit adds the row. [175-1; 177-2 decision 27; 167-5]
10. A native `edit` refused for its text or its target's kind answers `permission_denied` to a caller with `read` and not `read_write`, where a read followed by a guarded write answers `invalid` or `wrong_kind`. [181-4 decision 15 pins it]
11. Bytes outside a row's `data` column, in an error's `data` or an extra field, are written as text when they decode as UTF-8 and raise a serialization error otherwise. No unit carries it. [167-2]
12. Whole-input shell stages are not charged to `memory_bytes`: four `sort`s each holding 900,000 bytes under a 1 MiB budget all ended 0, on a prototype of the read schedule. No unit carries it. [168-2]

Two tests of `dev` itself fail at `27f3d24d`, on the unchanged tree: `tests/scripts/test_docs_export.py::test_the_real_glossary_exports` (the glossary gained terms the test's list lacks) and `tests/scripts/test_docs_site.py::test_no_line_of_code_in_a_page_is_wider_than_64_characters` (36 lines of `documentation/how-to/interrupt-a-job-and-ask-a-person.md`). This work changes neither file.

## Work that no spec owns

Each is a Scope, Out bullet in the spec named, which states what a caller gets today and that the work owes a spec of its own.

1. The shell's text for the `unavailable` family, defect 9 above. [175-1; 177-2]
2. `cp -r` and `mv` across mounts. [160-1]
3. A rule for the hint printed on an `info` line. [160-1 decision 20; 167-3]
4. Ranked search over tools and manifests. [169-1; 170-2; 170-4]
5. A case fold for the `globs` of `grep` and `search`, `find -iname`, and a stored folded key. [167-6]
6. A character cap on the errors section of a rendered result, which would reverse roadmap story F1 criterion 3. [167-3]
7. A rollup count entry that lists the distinct engine codes of its tail. [179-5]
8. Detecting or repairing a stored label that disagrees with its posture. [177-1]
9. A replayed `set_posture` rewrites every label again at the first send's cost. [177-1]
10. A slice of a prior version of a file. [178-1; 180-2 refuses it]
11. A SQLite database whose text encoding is not UTF-8, defect 2 above. [178-1]
12. Snapshots or persistent state for a guest. [172-2]
13. A wire backend's dropped connection, which answers `vfs.unavailable.backend` at the mount root and is not retryable. [177-2]
14. The page that tells a caller a batch with one bad row writes nothing. [179-3; 179-6]
15. A stored record of when a retention pass ran and what it removed. [180-4; 180-6]
16. The definition sentences of the `tree` and `edit` docstrings, and the kernel-surface statement of the archived spec 181, sections 7.1 and 7.2. [181-1]
17. A conformance row for `run`, and the frozen list of public names. [179-1; 181-2]

The roadmap's story T1, criteria 2, 4 and 5, still carries the program index and `/opt/bin` wording that the views spec ends. [169-1; 169-2]

## Two conflicts between specs that the check closed

The Python guest pinned `wasi-python` 0.1.0, which requires `wasmtime` 49, and the generic wasm host pinned `wasmtime` 51; the resolver found no solution for the pair. Both guests now pin 0.1.6, and the host is built over the Rust embedding already in `vfs-core`, with no extra and no Python binding. [172-1 decision 1; 172-3 decision 2; 169-4 decisions 1 and 12]

Three specs each add sentences to the fault-model docstring of the storage protocol. Applied in all six orders they give one text. [179-3 decision 10; 175-1; 177-2; 179-5]
