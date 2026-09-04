# Study: the delete-vs-mkedge race, staged on five engines

Companion to the memo `../../2026-09-04-delete-vs-mkedge-race.md`.

`race_experiment.py` stages the race deterministically: storage A
freezes at the `mkedge:before-insert` seam, a handler drives a genuine
rival `delete` of the target endpoint through storage B (same table
namespace, its own connections) to commit, then A's insert resumes.
The script then checks whether the stray authored edge exists, whether
`reindex` reclaims it, and what `restore` resurrects. A second probe
(Postgres only) holds `FOR KEY SHARE` / `FOR UPDATE` on the target's
entry row and measures whether the rival delete blocks.

Rerun (engines up via `docker/compose.test.yml`, the four
`VFS_TEST_<ENGINE>_URL` vars exported):

    uv run python race_experiment.py

Result on 2026-09-04 (tree at `65646e5`): the stray lands on all four
client/server engines, survives reindex with zero warnings, and comes
back live after restore; sqlite is immune (the rival delete loses as a
retryable conflict against the single writer). Both Postgres lock
flavors block the rival delete — trash rewrites `path`, a unique key,
so even `FOR KEY SHARE` conflicts.
