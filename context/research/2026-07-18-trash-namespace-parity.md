# Trash namespace parity — should trash be a normal, visible subtree?

- **Date:** 2026-07-18
- **Status:** verified 2026-07-18 — JuiceFS section cited file:line
  against the local checkout; desktop-trash sections cite public specs
  from model knowledge (flagged inline)
- **Method:** one researcher over the local `~/Git/Repos/juicefs`
  checkout (file:line citations); desktop trash conventions
  (freedesktop.org, macOS, Windows) summarized from their public
  specifications and flagged where not locally verifiable; vfs current
  state inventoried from the live tree at `writes.py` /
  `descent.py` / `reads.py` / `rows.py` and spec 072.
- **Question:** the 2026-07-18 session raised normal-fs parity for the
  trash namespace: on a desktop OS, trash is an ordinary directory —
  browsable, restorable by drag-out, and writable — while vfs v1 pinned
  trash as a reserved, read-invisible, write-refused internal scope
  (spec 072 §9). Which model should vfs ship, and what exactly changes
  if parity wins?

## Bottom line

Desktop filesystems uniformly treat trash as an **ordinary directory
plus a convention**, not a filesystem-enforced scope: freedesktop and
macOS enforce nothing at the fs layer; Windows uses ACLs (permissions,
not semantics). The one distributed-fs precedent with an *enforced*
trash (JuiceFS) makes it visible-but-restricted: browsable and
restorable, but creates inside it are refused (see the JuiceFS section
for the file:line contract). vfs's v1 "invisible reserved scope" is
therefore the strictest model in the reviewed field — stricter than
every shipped system. Parity is coherent in vfs because **deletion
hides by path rewrite, not by filter**: a trashed row's path cache is
rewritten under `/.vfs/trash/...`, so the pjdfstest contract (original
path classifies `not_found` through every read verb) survives with the
read filters gone. What the filters and the write gate actually buy
today is concealment of trash *structure* — and that is a convention
choice, not a correctness requirement, exactly as on a desktop.

## 1. Current vfs state (the model being reconsidered)

Inventory of where the reserved-scope model lives in the tree:

- **The scope constant and predicates** — `TRASH_ROOT =
  f"{METADATA_ROOT}/trash"` (`/.vfs/trash`), `in_trash`,
  `trash_filters` (`src/vfs/storage/backends/database/descent.py:40,
  101-125`). `trash_filters` is documented as "the unconditional
  scope: no verb ever surfaces a trashed row" — applied to point reads
  as well as enumeration, and never bypassed by a direct meta anchor.
- **Read side** — point reads apply `trash_filters`
  (`reads.py:299`); enumeration applies `liveness_filters`, which is
  trash-always-hidden plus meta-hidden-by-default
  (`descent.py:92-98`).
- **Write side** — the `outside_trash` plan gate classifies any write
  target under the trash prefix as `invalid` before any SQL runs
  (`writes.py:256-272`); `_fetch_committed` applies `trash_filters`
  to the plan snapshot (`writes.py:486`), so the write path cannot
  even see trash rows.
- **Descent** — `classify_misses` filters trash from the ancestor
  query so a trashed ancestor reads as missing, and the test suite
  pins that error shapes must not reveal trash structure
  (`descent.py:50-62`; `tests/test_backends_database.py:618-627`).
- **Schema** — restore metadata is identity-based row columns:
  `original_parent_id`, `original_name`
  (`src/vfs/models/rows.py:54-58`); the in-bucket name is the node
  ULID (spec 072 §9).
- **The governing pin** — spec 072 §9: "Trash is backend-internal
  state in v1: trash nodes are rows reachable by `parent_id`, not
  addressable paths — `paths.py`'s grammar gains no trash shape, and a
  routed list-the-trash/restore namespace is a recorded follow-up
  story. Trashed rows' path caches are rewritten under a reserved
  internal `/.vfs/trash/...` prefix that ingress never admits."
- **Not yet built** — `delete` is a stub
  (`backend.py:247-256`); restore and the reclamation sweep are
  unimplemented; the memory backend has no trash concept. The scoping
  machinery and schema exist; the verbs that would populate trash do
  not. A model change now re-scopes future work rather than rewriting
  shipped verbs.

**The load-bearing observation:** what makes a deleted file invisible
at its *original* path is the reparent itself — delete rewrites the
row's path cache under the trash prefix in the same transaction (ADR
004; spec 072 §9). The read filters hide the *trash-side* paths only.
Dropping the filters does not resurrect deleted files at their old
paths; it makes the trash side browsable.

## 2. Desktop prior art — trash as convention, not enforcement

*(Flagged: this section summarizes public specifications from model
knowledge; no local checkout carries them. Claims are stated at the
level the specs themselves pin.)*

- **freedesktop.org Trash specification v1.0** (Linux desktops):
  trash is `$XDG_DATA_HOME/Trash` — an **ordinary directory** with
  `files/` (the trashed items, under their original names, suffixed on
  collision) and `info/` (one `.trashinfo` sidecar per item recording
  original `Path` and `DeletionDate`). Nothing at the filesystem layer
  restricts reads or writes; the spec instead tells *implementations*
  (file managers) to tolerate foreign state — items in `files/`
  without a matching `.trashinfo` record are surfaced to the user
  rather than hidden or destroyed. Restore is a plain rename out.
- **macOS `~/.Trash`**: an ordinary directory whose only concealment
  is the dotfile convention (hidden from default `ls`/Finder listing,
  fully addressable when named). Direct writes succeed; Finder's
  optional "remove items after 30 days" purges *whatever is there* on
  age — the precedent that "written into trash" means "accepted the
  reaper."
- **Windows `$Recycle.Bin`**: the closest to enforcement — hidden +
  system attributes and per-SID ACL'd subfolders, with `$I` (metadata)
  / `$R` (payload) file pairs. But the mechanism is permissions, not
  filesystem semantics: with rights, direct writes land, and the shell
  tolerates or ignores foreign files.

The shared shape across all three: **visibility is the norm,
restore-by-move is the norm, metadata lives beside (not inside) the
name, and cleanup tolerates foreign rows.** Concealment, where it
exists at all, is a listing convention (dotfile) or an ACL — never a
"reads pretend it does not exist" filter.

## 3. JuiceFS — the enforced-trash precedent (visible, immutable)

The one reviewed system that *enforces* a trash contract at the
filesystem layer chose **visible-but-immutable**, sitting between the
desktop model and vfs's v1 reserved scope. File:line findings from the
local checkout:

- **Visible by default, addressable by anyone.** `.trash` is a real
  metadata row (`pkg/meta/sql.go:684-696`, mode 0555) whose root
  dirent is synthesized into every root readdir unless
  `--hide-internal` (`pkg/vfs/vfs.go:455-462`;
  `pkg/vfs/internal.go:84`); lookup-by-name is special-cased for all
  users (`pkg/meta/base.go:1273-1279`). Bucket dirs and trashed
  entries are ordinary rows browsed through the normal readdir path —
  layout `.trash/<YYYY-MM-DD-HH>/<origParent>-<ino>-<origName>`.
- **Reads are open to everyone; mutation is closed to everyone.** Any
  user may stat, list, and read-open per the preserved file modes;
  but create/mkdir/symlink with a trash parent is `EPERM` *including
  for root* (`base.go:1591-1593`), hardlink into trash `EPERM`
  (`base.go:1690-1695`), rename **into or within** trash `EPERM` even
  for root (`base.go:1879`), write-open and truncate of trashed files
  `EPERM` (`base.go:2059-2063`; `sql.go:1606-1608`), chmod/chown of
  trashed entries `EPERM` (`sql.go:1515-1517`).
- **Root's three verbs:** unlink-in-trash (purge, `base.go:1782`),
  rmdir of nested dirs (`base.go:1813`), and rename-out (restore,
  `base.go:1879`), the last gated by an internal-only `RenameRestore`
  flag (`interface.go:78`; `sql.go:2325-2327`); the `restore` CLI
  additionally requires OS root (`cmd/restore.go:48-51`). Delete's
  own reparent bypasses the public guards at the engine layer.
- **The closed world is what the sweeper leans on.**
  `CleanupTrashBefore` parses every child name of `.trash` as an
  hourly timestamp; an unparseable child is warned and **skipped
  forever**, never deleted (`base.go:3182-3187`), while everything
  *inside* an expired bucket is destroyed wholesale
  (`base.go:3191-3199`). Because nothing can be created in trash via
  the FS API, foreign rows are impossible short of raw DB writes —
  the sweeper's name-parsing assumption is safe by construction.
- **Scars already cited in W6 reconfirmed:** trash-entry name
  truncation at MaxName with only a warning (`base.go:3053-3060`) —
  vfs's ULID in-bucket names avoid it; restore `EEXIST` classifies as
  a conflict (`cmd/restore.go:144-146`).

SeaweedFS has no server-side trash at all; Jackrabbit Oak likewise
(grep-confirmed absence). So the enforced-trash precedent pool is
JuiceFS alone, and its choice decomposes cleanly: **visibility is
uncontroversial** (it ships visible-by-default, like `~/.Trash`);
**writability is where it diverges from the desktop**, buying a
closed-world invariant its timestamp-parsing sweeper depends on. A
parity design that opens writes must therefore also adopt the
freedesktop/desktop stance on cleanup — tolerate foreign state
explicitly — rather than inherit JuiceFS's assumption.

## 4. What parity means in vfs terms

Mapping the desktop model onto the current tree:

1. **Trash inherits the meta scope instead of owning a stricter one.**
   `/.vfs/trash` sits inside `/.vfs`, which is already
   hidden-by-default in enumeration and addressable when anchored
   (`descent.py:92-98`) — exactly the dotfile convention. Parity =
   delete `trash_filters` as a separate concept; the meta exclusion
   alone remains. Trash becomes browsable via `ls /.vfs/trash/...`,
   invisible to a default-scope `ls /`.
2. **The write gate goes.** `outside_trash` (`writes.py:256-272`)
   and the ingress refusal of trash-prefixed paths are retired; writes
   into trash are ordinary writes. The "write-only hole" rationale
   dissolves *because* the read filters go with it — the two guards
   must leave together (removing only the write gate strands writes
   behind `_fetch_committed`'s filter and produces phantom-parent
   misfires against the unique index).
3. **Delete/restore/sweep semantics are unchanged in shape.** Delete
   still reparents into time-bucketed nodes in one transaction;
   restore is still move-out (now expressible as a plain user `move`,
   with the dedicated restore verb consuming `original_parent_id` /
   `original_name`); the sweep still reaps expired buckets — now
   including foreign rows parked there by direct writes, the
   macOS-30-day precedent, which the spec must state loudly.
4. **The pjdfstest contract survives untouched.** Original-path
   `not_found` is delivered by the path rewrite, not the filter (§1).
   Harness rows that change are the trash-side ones: trashed rows
   *are* now visible at their trash paths, and the
   error-shape-conceals-trash-structure test inverts.
5. **Foreign rows need one pinned answer each place metadata is
   assumed:** the restore verb on a row with NULL restore metadata
   (classify `invalid`, or degrade to plain move — needs a pin);
   the sweeper on rows without bucket discipline (reap by bucket
   subtree, freedesktop-style tolerance); collision between a
   user-created name and a ULID mint (none — ULIDs and user names
   coexist under `(parent_id, name)` uniqueness like any directory).

## 5. What the reserved model bought, honestly

The costs of parity, so the decision is eyes-open:

- **Structure concealment ends.** Bucket layout, ULID names, and
  deletion cadence become observable. The
  `test_trash_misses_classify_uniformly_regardless_of_bucket_existence`
  guarantee (error shapes reveal nothing) is deliberately dropped.
- **"No verb ever surfaces a trashed row" ends.** Enumeration under an
  explicit `/.vfs/trash` anchor, grep with meta scope, and graph verbs
  need their trash posture re-derived from the meta scope rules alone.
- **The sweep gains a duty**: it may destroy user-authored rows (aged
  buckets), which the reserved model made impossible by construction.
  Precedented (macOS purge), but it must be a documented contract, not
  an accident.

## 6. Sources

- vfs live tree: `src/vfs/storage/backends/database/{descent,writes,
  reads}.py`, `src/vfs/models/rows.py`,
  `tests/test_backends_database.py` (cited inline)
- `context/specs/072-database-storage-backend/spec.md` §9;
  `context/decisions/004-stable-node-identity.md`
- `context/research/2026-07-13-database-storage-write-pipeline.md` W6
  (trash-reparent resolution and its JuiceFS citations)
- freedesktop.org Trash specification v1.0; macOS/Windows behavior —
  from model knowledge, flagged above
- JuiceFS local checkout — pending section §3
