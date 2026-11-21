# Tasks

The work that is outstanding, in one list. A task is removed from this file when it is done. Last updated on 2026-11-20.

## Eight branches wait to land

None is pushed and none has a pull request.

One branch stands apart and lands first: `research-logs-are-tracked`, cut from `dev`. It excepts `context/research/studies/` from the `*.log` ignore rule and adds the 41 logs that rule hid, so `test_links_resolve` passes on a fresh clone. It also carries the dead-link fix of branch 1, so that the test passes on it alone. It is merged into branch 7.

The other seven are a stack. Each sits on the one before it, so they reach `dev` in this order.

| | Branch | What it holds |
|---|---|---|
| 1 | `glossary-rules` | The glossary and naming rules, and the fix of three dead links in an archived spec |
| 2 | `public-names-follow-the-naming-rules` | The public names, who may change a mount, and the fixes from its review |
| 3 | `a-mount-is-listed-as-a-directory-is` | What a listing shows at a mount point, and four rounds of fixes |
| 4 | `the-working-agreement-covers-worktrees-codex-and-the-task-list` | Worktrees allowed, the handoff note replaced by this file, the Codex scripts and page |
| 5 | `search-applies-its-file-filters-to-rows-in-hand` | The `search` filter fix and the fixes from its review |
| 6 | `add-mount-takes-a-posture` | `add_mount(..., posture=...)`, the fixes from its review, and the new module `vfs.listing` |
| 7 | `a-call-that-reaches-several-mounts-bounds-each-mount` | Two specs and a research memo, the review records, and this file. No code |

Branches 2, 3, 5 and 6 were each reviewed by a reader that did not write them, and the records are beside each spec in `agents/`. Branches 1, 4 and 7 hold no source code. Checked on 2026-11-19 at commit `25d1f6e1`, the tip of branch 6: `scripts/ci.sh` passes to its end with 5,653 tests and coverage at 100%, `scripts/docs.sh check` passes, and the engine legs pass on Postgres (478), MariaDB (469, with 8 skipped) and Oracle (473). The listing rule on branch 3 has not had a full reading since its fourth round of fixes, only a check that the last two findings were closed.

These tasks stand between the branches and `dev`.

- [ ] **Push each branch and open its pull request to `dev`.** Each push needs approval of its own. `research-logs-are-tracked` goes first, and `dev` is merged into the next branch of the stack after each merge, so that each pull request shows its own change alone. Branch 3 is best read with branch 6 in view: branch 6 moves the listing rules into a module of their own.
- [ ] **Run the SQL Server leg.** It could not run on the machine used on 2026-11-19. Every test failed before any statement was sent, because the ODBC driver could not load OpenSSL: `openssl@3` is installed by Homebrew and is not linked, so `/opt/homebrew/lib/libssl.3.dylib` does not exist. `brew link openssl@3` is the usual cure. It changes the machine, so it was not run.
- [ ] **Run the engine legs once on fresh containers.** The procedure recreates the containers before each run. On 2026-11-19 the legs ran against containers that had been up for three days, because taking them down was not permitted in that session.
- [ ] **Decide whether five logs are pushed as they are.** They hold a home-directory path, which shows an account name: the three `jaq-install` logs of the 2026-10-15 study and `run-a` and `run-e` of the 2026-11-14 study. They are committed on `research-logs-are-tracked` and are not pushed. No log holds a key or a token, by a search for the usual shapes.

## Decisions waiting

- [ ] **Whether the three choices of `add_mount(..., posture=...)` stand.** The default is `None`, which keeps the storage's posture, so a call that names no posture still leaves a new mount open. A given posture replaces the posture stored at the storage's root. No failure puts the earlier posture back. The spec in `agents/2026-11-18-add-mount-takes-a-posture/` gives the cost of each alternative.
- [ ] **The five choices of the time limit.** The specs are `spec.md` and `spec-a-cancelled-call-leaves-its-storage-intact.md` in `agents/2026-11-18-a-call-that-reaches-several-mounts-bounds-each-mount/`. Both were read three times and found fit to build. Nothing is built. The choices, each with its recommendation: a default of 30 seconds, yes; a late call cancelled at its timeout, yes; the addressed storage timed too, no; a late mount marked and probed once in each timeout, yes, as a later landing; and for the cancellation fix, the unit of work shielded and its commit refused when it was cancelled.
- [ ] **Whether a fault in a mounted storage should raise out of a listing of its parent.** A storage that raises an ordinary exception, and not a transport error, now raises out of `ls`, `tree` and `glob` of the directory its mount is in. That is the kernel's rule for a fault. Before the listing rule, `ls` of the parent did not ask the mounted storage. The other choice is a bare row and a warning, as for a storage that cannot be reached.
- [ ] **Whether `glob` may ask the mounted roots after the storages have answered.** It does since the third round of fixes, which costs one more round trip when a pattern matches a mount point. It is what lets a limit be spent only on rows that are shown, and what keeps a storage from being called after `close()`.
- [ ] **Which feature is next.** Write preconditions, spec 174, is the recommendation. The ranged read and the listing cursor are the others considered.

## Defects found and not fixed

Each was shown by a script that ran, unless it says "read". The review records name the reading that found each one.

### A cancelled call

- [ ] **Cancelling a call inside a statement destroys an in-memory storage.** After one cancelled `stat`, the next read fails with `no such table` and the next write starts an empty database. On a file database a cancelled write can land while its caller is told it was cancelled. The cause is found and a fix is specified, in `spec-a-cancelled-call-leaves-its-storage-intact.md`. It is the first landing of the time limit, and it stands alone.

### Changing a mount

- [ ] **`remove_mount` deletes the mount-point directory after the mount lock is released.** An `add_mount` at the same path that runs between the two can end with a live mount on a deleted directory.
- [ ] **`add_mount` restores a deleted file, or a deleted directory that is not empty, and then refuses the mount.** The restored rows stay.
- [ ] **When `close()` lands during the cleanup of `remove_mount`, the detached storage is neither returned nor closed.**
- [ ] **A mount change asks `holds` outside the one place storage calls go through.** A `close()` that lands between the entry check and that call still calls a closed storage. Read.
- [ ] **Three small ones.** `grants` can be masked with `deny_ops`, though it only reads. `add_mount(storage, path="")` falls back to the storage's name. `require_storage` accepts a storage whose members are not callable.

### Listing at a mount point

- [ ] **A `glob` result can name a mount in its error records when the caller's listing was refused.** A record for a mount that cannot `glob`, and a mounted storage's own refusal, both carry the mount's path. Before the listing rule.
- [ ] **A named root of `glob` that is a mount point is not treated as other mount points are.** Its probe returns the row as the storage gave it, even from a failed answer or with a kind that is not a directory. It is asked twice when one of its ancestors is named too, and two answers that differ merge to a row with no version. The limit does not count a row a probe already supplied.
- [ ] **After a region of a `glob` fails, a row in it can come back.** A stored row for a directory above a mount comes back through the merge, and a named root's probe can put its row back.
- [ ] **A storage applies `max_count` before the kernel drops rows hidden beneath a mount.** A stray row in the parent storage beneath a mount path can cost the caller a visible row. Before the listing rule.
- [ ] **The parent's trash listing loses deleted rows that lie beneath a mount path.** Before the listing rule.
- [ ] **A `glob` can call a storage that `remove_mount` has handed back and whose owner has closed it.** The call in flight holds the storage.
- [ ] **`glob` and `grep` over rows in hand look up a missing fact on the mount table as it is when they ask.** A mount replaced while they wait changes the answer. Before the listing rule.
- [ ] **`locate` and `stat` report a file when a second kernel on the same storage replaced a directory above a mount with a file.** Before the listing rule.
- [ ] **In `tree`, a mount whose holder failed loses its own row, and the rows beneath it are still listed.** A mounted storage whose own `tree` returns its root row gives two rows at the mount point.
- [ ] **`stat` of a missing path beneath a hidden directory above a mount names that directory as the missing part.** `stat` of the directory itself returns a bare row.
- [ ] **`read` of a directory above a mount says `not_found` to a caller who holds nothing on it,** where `stat` shows it and a visible directory gives `wrong_kind`.
- [ ] **`read`, the mutating verbs and `locate` take no hop.** A storage that wraps its own kernel recurses without end on them. `ls` and `stat` now take one. Before the listing rule.

### Search over rows in hand

- [ ] **A row at a storage's own root makes the call fail.** A row at a mount point, the row of `/`, and the row of the trash view's head each reach the storage as a path it turns into a glob, and the call fails with `invalid`. `glob("/*")` on any kernel with a mount returns such a row. `grep` given the same row succeeds.
- [ ] **`search` without `observations` does not expand a brace pattern in the kernel, as `grep` does.** `*.{md,rst}` matches nothing there, and a glob that cannot be parsed is refused once by each mount.
- [ ] **`grep` over a held row in the trash view matches nothing and reports nothing.**

## Cost and structure

- [ ] **Two scans of the mount table grow with a batch.** `_permission_layers` scans it once for each row, 2,000,000 visits for 10,000 rows and 200 mounts, and `MountListing.beneath` once for each named root. Before the listing rule.
- [ ] **`Result.merge` removes repeated errors by searching a growing list.** 200 distinct errors cost 19,900 comparisons, so 10,000 would cost about 50,000,000. Before the listing rule.
- [ ] **A storage searches 10,000 rows in hand close to its time budget.** 8 to 9 seconds against 10, on SQLite in memory, measured once by the clock.
- [ ] **A storage builds every `glob` candidate before it applies the limit.** Before the listing rule.
- [ ] **Every mounted root in a listing is asked at once.** With 200 database mounts, one `ls` opens 200 transactions together. Read.
- [ ] **The cost of a listing over mounts is measured on a server engine.** It is counted in calls and not measured.
- [ ] **`gather_settled` and `PathFilters` live in `vfs.listing`.** Three readings said they belong in a module that is not about listings, since writes and searches use them too.
- [ ] **The tests of `vfs.listing` are in `tests/base/test_mount_listing.py`.** The new module has no test file of its own name.

## Words and names

- [ ] **The docstrings of 16 source files follow the docstring rules.** About 265 of 311 break a rule in `documentation/maintainers/how-we-write-docstrings.md`, and about 170 public members have none. The largest files are `rights.py`, `paths.py`, `backend.py`, `labels.py`, `ranking.py` and `sync.py`. The words "router", "bind path", "bind point" and "bind site" remain in them, and in `fanout.py` and `pattern_matching/glob.py`.
- [ ] **Seven words used in docstrings get a glossary entry.** They are gate, capability, permission map, posture, authority, trash view and mount point.
- [ ] **A test name uses an old word.** `test_unmount_and_remount_pass_under_a_rule_beneath_the_site` keeps "remount", because documents under `context/` cite it by name.
- [ ] **A refusal in `update_mount` has an em dash in its message.** "Mount at … changed while it was being updated — retry".
- [ ] **The docs export follows an alias of a type variable.** It now tells a type variable by what the value is, and it does not follow `T = U` or a renamed constructor.

## Tests that fail now and then

- [ ] **The Playwright test "a button that returns to the top shows once the reader scrolls back up".** It failed three times on 2026-11-19 while other work loaded the machine, and passed each time it was run again.
- [ ] **`test_two_writers_crossing_together_analyze_once` in `test_statistics.py` fails under load and passes alone.** Seen on 2026-11-19 while other suites or the engine legs shared the machine. No clock was found in its path on 2026-11-21, and the failure was not reproduced, so its cause is not known. The two `test_reads.py` tests seen failing beside it now run with no glob wall budget, as a counted test must.
