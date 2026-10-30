# The permission ladder: a `list` rung and a `contribute` rung, and what a graph walk needs from them

- **Status:** research memo (commits us to nothing). Feeds ADR 080 (proposed, same day) and spec 165 (promoted from seed to draft the same day). Builds on `2026-09-28-traverse-visibility-unix-plan9.md` and does not repeat it.
- **Date:** 2026-10-14
- **Owner:** Clay Gendron
- **Question:** Clay, 2026-10-14, reviewing ADR 079: "if you have access to a file, then you can already see its parent directories ... expand that permission set with this in a new specification ... and we just make a rule that to traverse nodes, you need to have X level of permission on both nodes." And, the same day: make sure the researchers look at Plan 9's permission ladder. The 2026-10-07 addendum in `open-questions.md` had proposed `none < list < read < contribute < read_write < manage`; `manage` stays parked.
- **Method:** three parallel studies under one brief (`studies/2026-10-14-permission-ladder/00-brief.md`): an internal impact map measured on the live tree (every site keyed on a grant level, the compile cost measured, the road baseline executed), a prior-art study of fourteen systems with Plan 9's full model first, and a semantics study that states the walk, search and write rules with worked examples and runs today's baseline for each. Every claim is labelled EXECUTED, READ or INFERRED in the studies.
- **Sources (clones refreshed 2026-10-13 unless noted; licences in `02-prior-art-list-and-contribute.md` §Sources):** `plan9` `ed1a9c21e` (MIT-style, dirty in three unrelated files, not refreshed), `plan9port`, `freebsd-src`, `jackrabbit-oak` `9c7d6d0`, `spicedb` `a1dad93`, `openfga` `526995e`, `gitlabhq` (July 2026 HEAD, refresh not verified), `nuxeo` (same), `postgres` `b128e75e`, `postgrest`, `afs` `1e9b731` (BSL, study only), `mirage` `314f00488`, `eve`, `deepagents`; vendor pages for SharePoint, Google Drive shared drives, S3, Discord and Slack by URL.

## One-paragraph summary

The pure resolver is already rank-generic: adding rungs there is one word and one dict entry. The storage half is not: it assumes exactly two non-none rungs in six places and the verb gates carry eleven level literals, which is exactly what one declared verb-to-rung table replaces. The row label is a dense integer, so inserting `list` below `read` renumbers every stored label and the landing needs a format bump and a label rebuild. Extra rights compiles cost little, because a caller who holds no row at exactly `list` has a `list` compile equal to its `read` compile and the two can be shared. `list` is the one rung needing new machinery: `admits` must answer a rung instead of yes or no, the listing verbs project a `list` row bare in the shape the road already uses, `read` on such a row answers `permission_denied` instead of `not_found`, and `grep` and `glean` score and count the readable set only. `contribute` is almost free: the write gate already splits creation from modification, and "alter only your own rows" already exists today as the owner floor (executed: under a read-only posture a principal overwrote, deleted and restored its own row and was refused on another's). The field confirms the shape. No studied system has both rungs in a total order with "own only", but the parts are everywhere: Nuxeo, SharePoint, GitLab and afs declare a see-the-name rung strictly below read; afs's `readonly < create < append < readwrite` is the clearest contribute ladder; "own" is always keyed by identity (the sticky bit, Postgres row-level security on an owner column, GitLab's authored-only permissions), never by a bit. Plan 9 is three independent bits per class, not a ladder, and it supplies three things worth keeping: the walk rule (execute to pass a directory, checked before the name is looked up), `stat` without read as the shape of `list`, and `DMAPPEND` as append-only on a row; it lacks the sticky bit, so a Plan 9 directory where everyone may create is one where everyone may delete. Three rules carry the design: traverse on both endpoints at `list`; a verb's rung is the rung of the field it reads; the road is derived `list`. One leak found on the way must close in the same landing: `rmedge` gates only the source today, so a writer of a visible file can learn whether a hidden target exists.

## 1. The question in plain terms

A rung is one step on the ladder of what a caller may do with a row. Today there are three: `none` (the row does not exist for you), `read` (you may read it) and `read_write` (you may change it). A rung strictly includes every rung below it, so a row's "everyone" level is one integer and a session's rights are the minimum over its subjects. That total order is what makes the range algebra and the row label cheap, and nothing proposed here breaks it.

Two things the current ladder cannot say. First, "there is a file here you may not read": today a row is whole or absent. The road (ADR 070) shows a hidden directory as a bare name when a visible row lies beneath it, but nothing grants that state on purpose. Second, "you may add here, but only change what you added": today `read_write` on a prefix lets a caller alter everyone's rows.

A graph walk needs the first one. The walk passes through nodes, and the rule Clay set is that passing an edge needs a rung on both of its ends. With only `read` as a visibility rung, a directory the caller may not read cuts an `fs` walk even when `tree` would descend it. With a `list` rung, the walk can pass a node it may name but not read, and the two verbs agree.

## 2. What the live tree assumes (study 01)

Measured by grep and read site by site:

| Where | What it assumes today | Cost of two new rungs |
|---|---|---|
| `grants.py` (the pure resolver) | nothing about the count; compares by rank everywhere | one `Literal` word each, one `LEVEL_RANK` entry each |
| `rights.py` `Resolution`, `resolve_authority`, `weight` | exactly two compiles, named `read` and `write` | a compile per rung a verb can need, in a mapping |
| `rights.py` `WriteGate` | two-way `== "read"` / `== "read_write"` switches | reads the verb's rung from the table |
| `rights.py` `_grant_refusal`, `params.GRANTABLE_LEVELS` | hand-written two-element sets | derived from the ladder |
| `backend.py` verb gates | eleven level literals | replaced by table reads |
| `rows.py` `everyone_level` | a dense integer rank 0, 1, 2 | renumbered to 0..4; `SCHEMA_FORMAT_VERSION` bump; `rebuild_labels` on old mounts |
| `ranges.py` three-seek predicate, `labels.py` relabel | rank comparisons | no change in shape |
| tests | fifteen raw `everyone_level=2` inserts, two three-value pins | become `LEVEL_RANK[...]` |

Compile cost, executed over 20, 400 and 4,000 grant rows: the two compiles take 0.2, 1.4 and 14.3 ms and weigh up to 1.4 MB; four would roughly double that in the worst case. But a `Rights` at level L depends only on rows at rank L or above, so when no row carries exactly `list` the `list` compile equals the `read` compile, and when none carries exactly `contribute` that compile equals `read_write`. Equality held in every trial. Compiles can alias, and the cache grows only for principals who actually hold the new rungs.

The road baseline, executed as a principal holding `read` on one deep file under a private tree: `ls`, `tree`, `stat` and `glob` show the ancestors bare (path and kind only), siblings and hidden files answer `not_found` exactly as an absent name does, `read` on the road directory answers `wrong_kind`, and every write beneath it is `permission_denied` decided on the directory. That table is the regression pin: a granted `list` must preserve every line of it and add only the rows it names.

## 3. What the field does (study 02)

| System | the "see the name" rung | the "add" rung | ladder or bits |
|---|---|---|---|
| Plan 9 | free `stat` after an `x` walk; reveals length, mtime, owner too | `DMAPPEND` on a file; create needs `w` on the parent, which also allows delete | bits (three per class, union of classes) |
| Unix, NFSv4 | `x` on the parent; `READ_ATTRIBUTES` | sticky directory: create, delete own; `ADD_FILE`, `APPEND_DATA` | bits plus one directory mode |
| Jackrabbit Oak | `rep:readNodes`: name, type, child names, no properties | `jcr:addChildNodes` | bits, with named aggregates |
| Nuxeo | `Browse` ⊂ `ReadProperties` ⊂ `Read`, declared | `AddChildren` | inclusion lattice |
| GitLab | Guest: the project's name and issues, no code, on a private project | Guest creates issues and notes; updates only authored items | ladder of integers |
| SharePoint | Limited Access ⊂ Read ⊂ Contribute ⊂ Edit | Contribute: add, edit and delete items, others' too | ladder |
| Google Drive | Viewer; a limited-access folder is seen but not opened | Contributor: create and edit any, no delete | ladder |
| S3 | `ListBucket`: key, size, last-modified, ETag | `PutObject` alone is a drop box | bits |
| afs (BSL) | visibility `meta` | `readonly < create < append < readwrite` | ladder plus a visibility axis |
| SpiceDB, OpenFGA | none; inclusion only where the author writes it | `contributor` as a membership tier | relation graph |

Three conclusions. The consensus for a see-the-name rung is name and kind, nothing else: every extra field is a measured leak (size and mtime reveal activity, owner reveals who, ETag reveals sameness, child count reveals hidden siblings). "Create, never alter" is well attested and sits between read and write wherever read is also held. "Alter only your own" is always keyed by identity: the sticky bit tests the owner of the file, Postgres puts the owner column in the policy, GitLab names authorship in the permission. The products that use the word "Contribute" let a contributor edit others' items, so vfs borrows the word with a stricter meaning and must say so.

Plan 9 in one paragraph. The mode word is three `rwx` triples plus attribute bits; the classes are unioned, so a more specific class never narrows. A walk needs execute on each directory it passes, checked before the name is looked up, and nothing on the node it arrives at. `stat` needs no permission on the file. Reading a directory is listing it, and listing returns every child's full stat. `DMAPPEND` makes a file append-only. `wstat` of mode and group is owner-or-group-leader, never write. There is no sticky bit: delete needs only write on the parent. Plan 9 is not a total order; its nearest ladder reading for directories is `x < rx < rwx`. vfs's `list` sits above Plan 9's bare `x` (which gives traversal and nothing) and below `rx` (which gives names plus full stat of each child).

## 4. The three rules (study 03)

**Rule 1: traverse on both endpoints.** A walk passes an edge only when the caller holds the walk's rung, `list`, on both endpoints. A `none` node never enters the frontier, so nothing is reached through it. A `list` node enters and is returned bare: path, kind, depth. A `read` node is returned whole. `meet` may route a bridge through `list` nodes and `minimal=True` may strip them. Plan 9's walk is the precedent, strengthened: Plan 9 checks the node you leave, vfs checks both, because vfs returns the node it arrives at.

**Rule 2: a verb's rung is the rung of the field it reads.** Names, kinds, children and edge types are `list`-class. Bodies, metadata (size, times, version, owner), measures (edge weight and distance) and statistics (document counts, average length, document frequency, candidates, degree counts) are `read`-class. So `glob` matches `list` rows and returns them bare; `grep` and `glean` never search, count or rank a `list` row; `read` on one answers `permission_denied`, a lawful refusal because the row is visible; ADR 065 rule 5's "visible set" means the readable set. An edge touching a `list` node carries its type and not its weight or distance, because a distance between a readable body and an unreadable one lets a caller rank hidden bodies by similarity, the class ADR 065 rule 4 closed.

**Rule 3: the road is derived `list`.** A caller's effective level on a directory is the greater of its granted level and `list` when a row at `list` or above lies beneath it. Checked against ADR 070's five rules and the September memo's three conditions, nothing changes for `ls`, `tree`, `glob`, `stat`, `read` or any write. What changes is that `graph` and the edge-shaped verbs now see a road directory as a node and pass it. The probe "a hidden file points at a road directory" does not leak: the hidden endpoint fails rule 1 and the edge is absent. The road stays a per-call derivation; compiling it into the caller's pieces would need the compile to read the entries table and be invalidated by ordinary writes.

**`contribute`.** On a prefix, `contribute` is `read` plus the right to create new rows beneath it. Altering and removing one's own rows is the owner floor, which every rung already carries and which the executed baseline shows working today. The write gate's creation branch judges at `contribute`; its occupied branch stays at `read_write`, where the owner floor lives. An overwrite clobbers `owner_id`, so overwriting another's row is refused there. vfs has no append verb and `edit` cannot be judged add-only, so `contribute` means "create a new row"; an append form is a later verb, not a rung. Under a set, ownership is per member, so a set's `contribute` degrades to `read` plus create, which narrows and never widens (ADR 066). Anonymous holds no owner floor, so for anonymous `contribute` is append-only.

**The total order holds.** `list ⊇ none`, `read ⊇ list`, `contribute ⊇ read` (SharePoint and Drive both include read in Contribute), `read_write ⊇ contribute`. The blind drop box (add but never read others' rows, Unix mode `733`, Plan 9 `-wx`) is `contribute − read`; it has no place in a total order and joins `run` on the second-axis list. The question it answers, "who reads the inbox", the ladder already answers with ownership: a `contribute` grant per sender on the sender's own subfolder.

## 5. The verb-to-rung table

One declared mapping in `ops.py`. "Own" is the owner floor, present on every rung for a single named subject, absent for sets and for anonymous.

| Verb | Rung | On what |
|---|---|---|
| `stat`, `ls`, `tree`, `glob` | `list` | presence; fields by the row's own level |
| `read` | `read` | the row |
| `grep`, `glean` | `read` | every row searched, counted or ranked |
| `graph` | `list` to pass or return a node; `read` for contents and edge measures | both endpoints of every traversed edge |
| `write` (new path), `mkdir` | `contribute` | the creation path and minted parents |
| `write` (existing), `edit` | `read_write` or own | the row |
| `delete`, `restore` | `read_write` or own | the row and every row beneath |
| `move` | `read_write` or own on the source subtree; `contribute` at the destination parent | both |
| `copy` | `read` on the source subtree; `contribute` at the destination parent | both |
| `mkedge` | `read_write` or own on the source; `list` on the target | both endpoints |
| `rmedge` | `read_write` or own on the source; `list` on the target | both endpoints (closes today's leak) |
| `grant`, `revoke`, `grants` | `read_write` until `manage` | the path |
| `sweep`, `posture`, members | developer plane | — |
| `run` | not a rung; its own axis | — |

Posture words: `private → none`, `listed → list`, `shared → read`, `inbox → contribute`, `open → read_write`; everyone stays capped at `read_write`.

## 6. Two leaks found on the way

- **`rmedge` gates only the source** (executed). A caller with write on a visible file removed a system-authored edge to a hidden target and got `deleted`; a second removal got `not_found`. The pair reveals the hidden row. Gating the target at `list` before the edge lookup, in the same shape as an absent path, closes it. This is independent of the ladder and should land with it.
- **Degree counts and stored link signals** must count only edges with both endpoints at `list` or above for the caller. The open question on stored ranking signals stays open with that set named.

## 7. What is left for the ADR to pick

Pointers in `../open-questions.md`.

1. Edge measures on an edge touching a `list` node: withhold weight and distance (recommended) or return the whole edge.
2. `mkedge`'s target rung: `list` (recommended, rule 2) or `read` as today.
3. Delete-own under `contribute`: yes (recommended; the sticky bit, and trash is a tombstone) or no (afs, Drive); and whether a directory's owner may remove a contributor's row beneath it (the sticky bit's second test; the owner floor is per row today).
4. Anonymous under an `inbox` posture: the posture refusal admits anonymous by the mount root's posture only, so an `inbox` under a private root is unreachable for anonymous. Change the gate to the addressed path's chain, or document.
5. Rank numbering: dense 0..4 with a format bump now, or sparse (0, 10, 20, ...) to spare the next rung a renumber; this rung renumbers either way.
6. Posture words: `listed` or `browsable`; `inbox` is the field's word for the shape and is recommended.
7. `grants` on a `list` path: `not_found` as the road today, or the caller's own rows.
8. The trash view: a tombstoned `list` row shows bare with no `deleted_at` (rule 2: metadata), which needs one clause on ADR 074.

## One-line version

Add `list` (name and kind, nothing else) below `read` and `contribute` (create, alter only your own) below `read_write`, keep the order total, put every verb's rung in one table, let a walk pass a node at `list` on both ends, treat the road as derived `list`, and close the `rmedge` leak while you are there.
