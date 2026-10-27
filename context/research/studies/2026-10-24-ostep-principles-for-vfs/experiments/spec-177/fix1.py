import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
pairs = [
("| 11 of 16 mutating calls replay with no extra state; 6 verbs refuse on replay; a replayed `move` refuses `not_found` with **no data** | EXECUTED (`replay_head.out`, appendix A; study 06 §2.1) |",
 "| Sent twice, 10 of 18 calls answer success and 8 refuse: `write(overwrite=False)`, two `edit`s, strict `mkdir`, `delete`, `restore`, `copy`, `move`. A replayed `move` refuses `not_found` with **no data**. A replayed identical `write` answers `updated` and bumps the version | EXECUTED (`replay_head.out`, appendix A; study 06 §2.1) |"),
("| A driver error escaping `session.commit()` is classified like any other: a disconnect becomes `vfs.unavailable.backend`, `retryable=True` | READ (`engine.py` `classify_failure`, L329–L353);",
 "| A driver error escaping `session.commit()` is classified like any other: a disconnect becomes `vfs.unavailable.backend`, `retryable=True` | READ (`engine.py` `classify_failure`, L329–L356);"),
("| `with_retry` redrives only retryable codes and `StaleSnapshot`; no profile lists a disconnect, so a commit disconnect is never redriven server-side | READ (`engine.py` L298–L327;",
 "| `with_retry` redrives only retryable codes and `StaleSnapshot`; no profile lists a disconnect, so a commit disconnect is never redriven server-side | READ (`engine.py` L298–L327, the catch at L318;"),
("`StaleSnapshot`. `with_retry` catches only `DBAPIError` and\n  `StaleSnapshot` (L316), so it never redrives an in-doubt commit.",
 "`StaleSnapshot`. `with_retry` catches only `DBAPIError` and\n  `StaleSnapshot` (L318), so it never redrives an in-doubt commit."),
("""7. **A repeated key runs nothing.** For each verb in `KEYED_OPS`, a
   second call with the same key within the TTL returns a `Result`
   whose observations equal the first's and whose errors equal the
   first's plus exactly one `vfs.replayed` `info` entry, with **zero**
   mutation statements and exactly one non-control statement (the
   look-up). For `posture`, zero mutation statements when no relabel
   is pending.
8. **A keyless call costs what it cost.** The pinned counts in
   `test_writes.py` (six mutation-class statements for a one-file
   create, seven for a one-edit `edit`) hold unchanged. A keyed miss
   of the one-file create adds exactly three: look-up, claim, one page.""",
"""7. **A repeated key runs nothing.** For each verb in `KEYED_OPS`, a
   second call with the same key within the TTL returns a `Result`
   whose observations equal the first's and whose errors equal the
   first's plus exactly one `vfs.replayed` `info` entry, with **zero**
   mutation statements on every leg. On the SQLite leg it issues
   exactly one non-control statement, the look-up. For `posture`, zero
   mutation statements when no relabel is pending.
8. **A keyless call costs what it cost.** The non-control statement
   counts pinned in `test_writes.py` (6 for a one-file create, 7 for a
   one-edit `edit`) hold unchanged for a keyless call. A keyed miss of
   the one-file create counts exactly 9: the 6, plus look-up, claim
   and one page."""),
]
for old, new in pairs:
    if s.count(old) != 1:
        print("MISS:", old[:70]); continue
    s = s.replace(old, new)
p.write_text(s)
