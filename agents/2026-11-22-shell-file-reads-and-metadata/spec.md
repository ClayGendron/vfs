# Every shell open is a fresh public read, and predicates ask the caller's rights

Draft implementation contract from the November 22, 2026 review of `cbda2721`. Verified against `dev` at `5a823ea` and amended on 2026-11-22 (`agents/2026-11-22-shell-review/reviews/verification.md`). Every problem of the draft reproduced. Its design is replaced by three rulings:

- The shell reads through the public `read` verb, one call for each open, and builds no storage path of its own. The draft's exact-bytes mode, SQLite incremental blob reader, Postgres byte projection with its dual write and backfill, and line-scoped reader protocol are withdrawn.
- The guard against a changed file is the session's, in `agents/2026-11-22-the-session-remembers-what-it-read/`. The draft's `if_identity`, `GuardedWrite`, `if_object` and namespace incarnation are withdrawn.
- No feature is negotiated with a host, since the module and its host ship together.

## The outcome wanted

Each time a line opens a file, the caller's rights and the file's current version are judged again, and every byte a reader gets comes from the one version that open saw. `test -r`, `test -w`, `-nt` and `-ot` answer from the caller's rights and the files' times. A listing is read a page at a time, and a warning on a partial result reaches the line's result.

## Builds on

`src/vfs/shell/host.py`, the public `read`, `stat` and `ls(after=, limit=)` verbs, and `crates/vfs-shell/src/machine/test.rs`. A prefix read such as `head -c 10 f` rides spec 178's public `read(range=)` when it lands (roadmap K6); until then an open reads the whole body, as today.

## The problem

Each was run on 2026-11-22 at `dev` `5a823ea`.

- **The body cache is keyed by path.** `cat f; cat f`, with another caller's edit between the two, prints the old body twice from one router read. Around a revoke it prints the secret twice, where a fresh line is refused. The cache serves a held body at any offset to any later open.
- **A reader's next chunk can come from a newer version.** When a mutating program makes the host forget its bodies, or the reading cap evicts one, the next 64 KiB refill goes back to the router: `{ read -r x; touch z; grep -c ^A; } < a` mixed two versions of `a`.
- **The cache costs grow with what it holds.** Each insert scans every held path: 200 empty files cost 20,100 visits and 400 cost 80,200. Keys and empty bodies are charged nothing, and the 64 MiB and 128 MiB caps are not tied to the line's `memory_bytes`.
- **A listing is one unpaged call.** `ls` over 3,000 children is one `ls(after=None, limit=None)` of 3,000 rows, all built before the reply.
- **A warning on a successful partial result is dropped.** A `truncated` warning on an `ls` or a `glob` row set never reaches `LineResult.errors`.
- **The rights predicates mean "exists".** `-r`, `-w`, `-O` and `-G` are true for a file the caller may only list, and `>>` to a `-w` file is then refused. `-nt` and `-ot` compare existence only.

## Decisions

1. **An open is one public `read`, held by that open alone.** Built on 2026-11-22. The host reads the whole body once when a line opens a file, and keeps it with the open description until its last descriptor closes or the line ends. A duplicated descriptor shares it and its cursor. A second open of the same path, at any offset, is a new `read`, so it is judged under the caller's rights and sees the current version. There is no cache across opens, so nothing is evicted and no reader is refilled from another version. Through a session the read leaves a stamp, as any read does.
2. **Held bodies give way, and a body read again must be the version its open saw.** A body is held only while its open has not read its end, keyed by the open; the machine names the open on each read by the key of its first one. Past `READING_BYTES`, 128 MiB, the body read least recently gives way, never the one being read. Opens that saw one body of one path, by its version and its content hash, share it, so two descriptors of one file read in step hold it once; the hash is asked for with the body, since a version alone does not name a file, as a move that frees a path shows. Its open keeps the version and hash it saw, and a later read of it reads the body again: the same pair is served, and a different one refuses the read with a `vfs.conflict` warning on the line. Two different files read in step whose bodies together pass the limit each read again at every chunk, the profile the base had. So memory follows the open readers, and no reader mixes versions. Built on 2026-11-22.
3. **A listing is paged.** The host calls `ls(after=, limit=128)` and follows `next_after` until it is absent, replying a page at a time. Each page is charged while held.
4. **Warnings on a successful partial result reach the line.** A warning on a successful `read`, `stat`, `ls`, `glob`, `grep` or `search` result is kept through the existing deduplicating collector, in the served programs of `src/vfs/shell/programs.py` too. An ordinary negative probe, such as `test -e` on an absent path, keeps nothing.
5. **`stat` can report the caller's rights.** `stat(columns=...)` gains the optional columns `can_read` and `can_write`, computed by the router from the same admission checks the verbs use: for a file, the body read and an overwrite; for a directory, a listing and the creation of a child. A later real mutation is judged again. The host asks for them only for `-r`, `-w`, `-O` and `-G`, and maps an unknown value to false.
6. **`-nt` and `-ot` compare `updated_at`.** Times are compared as UTC instants at microsecond precision. Equal times compare false. `-nt` is true when only the left file exists, and `-ot` when only the right does.

## Tests

- `tests/shell/test_host.py`, built on 2026-11-22 as `test_each_open_of_a_file_is_a_fresh_read_that_sees_an_edit`, `test_an_open_after_a_revoke_is_refused`, `test_one_open_reads_one_version_across_its_chunks`, `test_two_opens_of_one_file_are_two_reads`, `test_a_body_given_way_is_read_again_only_at_the_version_its_open_saw` and `test_bodies_whose_readers_stopped_early_are_bounded`:
  - `cat f; cat f` around an edit prints both bodies, with two router reads;
  - around a revoke the second `cat` is refused;
  - the `read -r x; touch z; grep` line reads one version only;
  - 200 and 400 empty files cost work in proportion, counted;
  - a body that gave way is read again at its open's version, or refused.
- A spied `ls` over 300 children is three paged calls.
- A `truncated` warning on `ls` and on `glob` reaches `LineResult.errors` once.
- `-r`, `-w`, `-nt` and `-ot` over read-only, writable, list-only and masked files, under `[ ]` and `[[ ]]`, against the verbs' own answers, on memory and SQLite.

## Verification

`cargo test --release -p vfs-shell -p vfs-shell-wasm` and `uv run pytest tests/shell`, with the Postgres leg for the `stat` columns. Update `documentation/reference/shell.md` with the read profile and the predicates.

## One line

Every open in the shell is a fresh public read held by that open alone, and the rights predicates ask the caller's real rights.
