import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
pairs = [
("| `delete` | `deleted` | `not_found` with `vfs.trashed`, `vfs.deleted_at` (unchanged) | recognisable |",
 "| `delete` | `deleted` | `not_found` with `vfs.trashed`, `vfs.deleted_at` (as today) | recognisable |"),
("""- The rows the ladders read must carry the columns the mask judges
  by. `SNAPSHOT_COLUMNS` (`serialized.py` L72) gains `content_hash`,
  `owner_id` and `everyone_level`. That widens a row read by about 80
  bytes and adds no statement.""",
"""- The rows the ladders read must carry the columns the mask judges
  by. `SNAPSHOT_COLUMNS` (`serialized.py` L72), restore's
  `_TOMBSTONE_COLUMNS` and the row `mkdir_rows`' plan holds each gain
  whichever of `content_hash`, `owner_id` and `everyone_level` they
  lack. That widens a row read by under 100 bytes and adds no
  statement."""),
("""13. **The replay row is reclaimed by `sweep`.** 10,000 keyed calls with
    `replay_hours=0` plus 3 with the default: `sweep()` at the trash
    view leaves 3 head rows and their pages, reports `replays_swept ==
    10_000`, and spends exactly 2 statements on the arm whatever the
    count (counted at 3 and at 10,000). A `sweep` at a path leaves the
    replay store untouched.""",
"""13. **The replay row is reclaimed by `sweep`.** 3 live answers from
    real keyed calls, plus 10,000 expired head rows and their pages
    bulk-inserted by the test: `sweep()` at the trash view leaves the 3
    and their pages, reports `replays_swept == 10_000`, and spends
    exactly 2 statements on the arm whatever the count (counted with 3
    expired rows and with 10,000). A `sweep` at a path leaves the
    replay store untouched."""),
("""11. **Overlapping sends run once.** Two sends of one key, the second
    issued from a seam inside the first's transaction: the change
    happens once (version +1 once, one version row), and both callers
    get the same observations, the second with `vfs.replayed`. On the
    four server legs the second waits on the claim; on SQLite it
    queues behind `BEGIN IMMEDIATE`.""",
"""11. **Overlapping sends run once.** Two sends of one key overlap: a
    seam inside the first call's transaction starts the second as a
    task, and the test awaits it after the first returns. The change
    happens once (version +1 once, one version row), and both callers
    get the same observations, the second with `vfs.replayed`. On the
    four server legs the second waits on the claim; on the SQLite legs
    it queues behind `BEGIN IMMEDIATE` and then finds the answer."""),
("pin 15's axis table for the store\n  (§3.8). It answers the idempotency half of the open question \"MCP\n  2026-07-28: long-batch execution model and serving-stack choice for\n  serve()\" (§9).",
 "pin 15's axis table for the store\n  (§3.8). It answers the idempotency half of the open question \"MCP\n  2026-07-28: long-batch execution model and serving-stack choice for\n  serve()\" (§8)."),
("the MCP tasks extension (the other half of the open\nquestion, §9).", "the MCP tasks extension (the other half of the open\nquestion, §8)."),
]
for old, new in pairs:
    if s.count(old) != 1:
        print("MISS:", old[:80]); continue
    s = s.replace(old, new)
# move the open-question section before Scope, renumbered 8
start = s.index("## 9. The open question this spec answers")
end = s.index("## Appendix: the probes")
section = s[start:end].replace("## 9. The open question this spec answers", "## 8. The open question this spec answers")
s = s[:start] + s[end:]
scope = s.index("## Scope")
s = s[:scope] + section + s[scope:]
p.write_text(s)
