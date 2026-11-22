# The session remembers what it read, and refuses a change to a file that moved on

A draft, written on 2026-11-22 from roadmap story K10 (`context/standards/roadmap.md`) and the rulings recorded at the end of `agents/2026-11-22-shell-review/reviews/verification.md`. It is not reviewed, and nothing is built. Where this spec and K10's text disagree, this spec is the later ruling: K10 filled in `if_version=` alone, left strict off by default and bounded the stamps at 4,096.

## The outcome wanted

An agent reads `/notes.md` at version 5 through its session. When it later writes, edits, moves or deletes `/notes.md` through the same session and the file is at version 7, or is now a different file, nothing changes and the call is refused with the reason that the file changed since it was read and must be read again. The agent's code carries no version. The shell gets the same guard, because a line runs through a session: `cat f` then `sed -i ... f` is guarded, and so is `rm -i f`, and so is the second chunk of a long redirection.

## Builds on

- `agents/2026-11-20-write-takes-preconditions-and-an-append/`: `write(if_version=, if_versions=, if_absent=, append=)`, its guard `version = base AND path = ...` on the material `UPDATE`, and `conflict` carrying the current `version`.
- `src/vfs/session.py` and `src/vfs/sync_session.py`: a session binds one authority to one conversation and delegates every verb to the router's funnel. It is sugar over the public verbs, and stays so.
- `src/vfs/shell/host.py`: the shell's host answers each request with one public verb.

## The problem

Each was run on 2026-11-22 at `dev` `5a823ea`.

- A caller that reads and writes back must carry the version itself. Nothing remembers it for the caller, and nothing in the shell carries it: `sed -i` writes back unguarded.
- A version alone does not name a file. Versions count across a delete and a re-create (v1, v2, a delete, v4), and a move onto a tombstoned path is refused `exists`, so those cases are caught. But a move that frees the path is not: move `/x/p` away, then write, move or copy another file to `/x/p`, and the new file can stand at the version the caller saw. `write(if_version=...)` then overwrites it. Shown four ways.
- An entry id alone does not name a state of a file either: a delete and a later write at the same path revive the row with its old `entry_id`.
- `delete` and `move` take no precondition at all.
- `Observation` carries `version` and `content_hash`, and no `entry_id`.

## Terms

- **Etag.** An opaque string the router mints for a row from its mount, its `entry_id` and its `version`. Two etags are equal when they name the same entry at the same version. An etag grants nothing; rights are judged on every call as before.
- **Stamp.** A session's memory that it saw a path at an etag.
- **Strict.** The session's rule that an existing file it holds no stamp for cannot be changed through it.

## Decisions

1. **Every row that names a file or a directory carries its etag.** `Observation` gains `etag: str | None`, filled by every verb that returns a row with a `version`: `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search`, and the results of `write`, `edit`, `move`, `copy` and `mkdir`. A row with no version carries none. The etag is part of the public result and crosses the wire like any other field.

2. **`write`, `edit`, `delete` and `move` take `if_match=`, and a batch write takes `if_matches=`.** The value is an etag. The precondition holds when the row at the path is the same entry at the same version. It is checked inside the transaction that mutates: the write guard becomes `entry_id = :e AND version = :v AND path = ...`, and the delete and the move gain the same terms on the statements that change the row. It adds no statement. A mismatch is `conflict` with the row's current `version` in `data`, as `if_version` gives today; a malformed or foreign etag is `invalid` before any storage is called. `if_match` is exclusive with `if_version` and `if_absent`. For a directory the precondition compares the entry and the version on a cascading delete, and the entry alone on a non-cascading one, since its children's changes move its version and an empty directory hides nothing.

3. **A session stamps what it is shown.** Each row with an etag that a session returns to its caller sets or refreshes the stamp of its path. A successful mutation refreshes the stamp from its own result, so a session reads its own writes; a delete drops the stamp of the path and every path beneath it; a move carries the stamps of the source to the destination. Bodies and listings both stamp: file content, `grep` matches, and `ls`, `tree`, `glob`, `find` and `stat` rows.

4. **A session fills in the precondition.** When the caller gives none of `if_match`, `if_version` or `if_absent`, the session passes `if_match=` from the stamp of the target. An explicit precondition always wins and reaches storage unchanged.

5. **Strict is on by default.** A session opened with `fs.session(authority)` refuses to change an existing file it holds no stamp for, with these rules:

   | Call | With a stamp | With no stamp |
   |---|---|---|
   | `write` of one path | `if_match` | sent with `if_absent=True`: a new file is made; an existing one is refused |
   | `write(append=True)` | `if_match` | unguarded, as today: an append destroys nothing |
   | `edit` | `if_match` | refused, nothing dispatched |
   | `delete` of a file | `if_match` | refused, nothing dispatched |
   | `delete` of a directory | `if_match` on the directory alone, never on what is beneath it | refused, nothing dispatched |
   | `move` | `if_match` on the source | refused, nothing dispatched |
   | `copy` | no precondition on the source, which does not change | no precondition |
   | `write(entries=...)` | `if_matches` for the stamped paths | each unstamped path must be absent |

   Both refusals, unread and changed, are `conflict` with `data["reason"]` set to `"unread"` or `"changed"`, and a message that says to read the file again. `fs.session(authority, strict=False)` keeps the precondition of a stamped path and lets an unstamped one through unguarded. A caller that uses the router directly keeps today's behaviour.

6. **A line is its own session.** `fs.cli(line, authority=...)` runs the line through a strict session that lives for the line alone. `Session.cli` runs it through that session's own stamps, which outlive the line, so `cat f` in one line and `sed -i ... f` in the next are guarded. The shell's host is handed the session for every effect and the router for its own probes: the stat before a redirection, before a removal and before a `test`, and the stat that resolves a program, never stamp.

7. **A writer that spans chunks is guarded by its own stamp.** The first write of a redirection makes or truncates the file and stamps it from its result. Each following chunk is an append with `if_match` from the stamp, and its result refreshes the stamp. A replaced, moved or deleted target fails the writer with status 1 and its later chunks are not sent. A single `echo x >> f` on a file the session never read stays unguarded, so twenty concurrent lines appending to one log leave twenty lines. Two multi-chunk writers that interleave on one file conflict, and the second fails.

8. **The stamps are bounded by bytes.** `SESSION_STAMP_BYTES`, a declared constant of 64 MiB, bounds a session's stamps, each charged its path's UTF-8 bytes plus a fixed 64. The least recently touched stamp is evicted past it, and an evicted path is unstamped. Eviction never makes a call succeed that would be refused; under strict it can make a change refused as unread, which another read clears. `close()` drops the stamps.

9. **The sync session shares one implementation.** `SyncSession` and `AsyncSession` hold the same stamp table type and rules, and X1's parity test covers `strict=` and the refusals.

## Scale

- **Per verb call.** One dictionary lookup and one store for each path a call names or returns. A 10,000-row `glob` writes 10,000 stamps in memory. No statement and no connection.
- **Per file write.** The precondition is two more terms on a statement the write already runs. Nothing on the index path.
- **Per batch.** A 10,000-entry `write(entries=...)` carries `if_matches` for its stamped paths through the same chunked builder as `if_versions`, with the same statement count.
- **Memory.** At most `SESSION_STAMP_BYTES` per open session; a line's session lives for the line.

## Tests

- `tests/session/test_stamps.py`, on memory, SQLite and the Postgres leg:
  - Read through a session, write through another caller, write through the session: refused `changed` with the new version, and zero mutation statements.
  - The four moves that free a path: move away, then write, move or copy a different file to the path, or move the parent. Each refused `changed`.
  - A delete and a re-create between read and write: refused `changed`.
  - Read then write twice: both succeed.
  - An explicit `if_version` reaches storage unchanged.
  - Strict refuses an unstamped edit, delete and move with nothing dispatched. It makes a new file. It refuses an unstamped overwrite through `if_absent`. It lets an unstamped append through.
  - `strict=False` lets the same calls through.
  - Each read verb stamps, one parametrized case per verb; a row without a version stamps nothing.
  - Eviction is counted at the byte bound.
- `tests/shell/test_host.py`:
  - `cat f` then `sed -i` with an edit by another caller between them: refused, and `f` keeps the other caller's body. The same across two `Session.cli` lines.
  - `rm -i f` with `y` and an edit between the prompt and the delete: refused.
  - A three-chunk redirection with a replacement between chunks: status 1, and the replacement intact.
  - `echo x >> log` from twenty concurrent lines: twenty lines.
  - `fs.cli("sed -i s/a/b/ f")` on a file the line never read: refused as unread, until `cat f` comes first.
- A statement-count pin that `if_match` adds no statement to `write`, `edit`, `delete` or `move`.

## Scope

`Observation`, the router's `write`, `edit`, `delete` and `move`, the database backend's guards on SQLite and Postgres, the parameter registry and API drift tests, both sessions, `fs.cli`, the shell's host, the reference page and the four public faces.

## Not decided here

Whether `serve()` keeps a per-principal stamp table, so that agents over MCP get the guard without a session object, is roadmap decision D51.

## One line

A session remembers each file it read by entry and version, and vfs refuses to change a file that moved on since, or one the session never read.
