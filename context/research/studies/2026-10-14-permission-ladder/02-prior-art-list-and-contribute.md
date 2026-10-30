# L2 — Prior art for a `list` rung and a `contribute` rung in a total-order ladder

- **Date**: 2026-10-14. Researcher L2 of the spec 165 permission-ladder study.
- **Question**: vfs wants `none < list < read < contribute < read_write < manage`, a *total order* (each rung strictly includes every rung below). For each system studied: is its "see the name, not the contents" right strictly below "read" and included by it? Is its "add, alter only your own" right between read and write? Or are these independent bits, as Unix `r/w/x` are?
- **Builds on**: `context/research/2026-09-28-traverse-visibility-unix-plan9.md` (cited below as **the 09-28 memo**). It already covers traverse vs list vs read in Unix, Plan 9, Windows, SharePoint, Drive, S3, NFSv4 and mirage. This report does not repeat it. It adds: the full Plan 9 model, the content repositories (Oak, Nuxeo), the relation stores (SpiceDB, OpenFGA), the role ladders (GitLab, SharePoint, Drive), Postgres/PostgREST, the agent VFSs (afs, mirage, eve, deepagents), and the append-only precedents.
- **Evidence labels**: READ = read in a clone or a vendor page; EXECUTED = a command run today; INFERRED = my reasoning from READ facts; NOT VERIFIED = stated with its reason.

## Summary

The field has no system whose "list" and "contribute" are rungs of a total order *and* whose "contribute" means "alter only your own". The parts exist separately. **`list` below `read`, strictly included:** Nuxeo declares it (`Browse` ⊂ `ReadProperties` ⊂ `Read`), SharePoint declares it (Limited Access ⊂ Read ⊂ Contribute ⊂ Edit), afs declares it as a visibility axis (`meta` vs `full`), GitLab's Guest is it for private projects, and Plan 9's free `stat` is its oldest form. Oak has the bit (`rep:readNodes`) but as an independent bit, not a rung. **`contribute` between read and write:** afs has the clearest precedent, a four-mode total order `readonly < create < append < readwrite`, and SharePoint's `Contribute` and Drive's `Contributor` sit exactly between read and edit — but *none of the three restricts editing to one's own items*. "Own" comes from a different place in every system that has it: the sticky bit (owner of the file or of the directory may unlink), NFSv4 `ACE4_DELETE` on the target versus `ACE4_DELETE_CHILD` on the parent, GitLab's `_update_authored_*` permissions, Postgres RLS policies keyed on a creator column, SharePoint's per-list "edit only their own items" setting, and Discord's "Manage Messages" (delete *others'* messages) versus posting. So the ADR must assemble `contribute` from two precedents: a "create and append, never alter" mode (afs `append`, Plan 9 `DMAPPEND`, NFSv4 `APPEND_DATA`/`ADD_FILE`) plus an "owner may alter their own" floor (the sticky bit, RLS on an owner column) — and vfs already stores `owner_id` on the row, which is the sticky bit's "owner of the file" test. On what `list` should reveal, the systems that reveal more than name and kind (S3: size, mtime, ETag; Plan 9 `stat`: length, mtime, owner, muid; Unix `0711`: link count, size, mtime) are exactly the ones whose leaks the 09-28 memo measured, so name-and-kind is the right floor.

## Sources and licences

All clones are read-only under `~/Git/Repos`. Each was opened for the first time by this study except `plan9`, `plan9port`, `freebsd-src`, `unix-history-repo` and `mirage` (licences recorded in the 09-28 memo and re-checked today). The brief says the set was refreshed 2026-10-13; I did not re-fetch. Commit dates are from `git log -1` (EXECUTED).

| Clone | Default branch, HEAD, date | Licence (READ) |
|---|---|---|
| `jackrabbit-oak` | `origin/trunk` `9c7d6d0` 2026-10-12, clean | Apache-2.0 (`LICENSE.txt`) |
| `spicedb` | `origin/main` `a1dad93` 2026-10-13, clean | Apache-2.0 |
| `openfga` | `origin/main` `526995e` 2026-10-07, clean | Apache-2.0 |
| `gitlabhq` | `origin/master` `c4bbe29d8` 2026-07-08, clean | MIT Expat for `app/`, `lib/`, `config/`; CC BY-SA 4.0 for `doc/`; `ee/` under `ee/LICENSE` (`LICENSE:1-12`). I read `lib/`, `app/`, `config/` and `doc/` only. **[NOT VERIFIED: whether the clone was refreshed on 2026-10-13 — its HEAD is 2026-07-08, three months old for a daily-commit repo.]** |
| `nuxeo` | `origin/2025` `00b5bed6` 2026-07-06, clean | Apache-2.0. [NOT VERIFIED: same refresh doubt.] |
| `postgrest` | `origin/main` `08811db` 2026-09-03, clean | MIT |
| `postgres` | `b128e75e` 2026-10-14, clean | PostgreSQL licence (`COPYRIGHT`) |
| `afs` | `origin/main` `1e9b731` 2026-03-24, clean | **BSL 1.1** (ArcBlock) — study only, per CLAUDE.md |
| `eve` | `origin/main` `23e2e7c9e` 2026-09-15, clean | Apache-2.0 |
| `deepagents` | `origin/main` `1d3232c08` 2026-09-14, clean | MIT |
| `mirage` | `314f00488` 2026-10-13, clean | Apache-2.0 |
| `plan9` | `ed1a9c21e` 2025-10-28, dirty (12 case-collision files, as in the 09-28 memo) | MIT (Plan 9 Foundation) |
| `plan9port` | `b6564bd9` 2026-08-26, clean | MIT |
| `freebsd-src` | `d9e2caccfac1` 2026-10-02, clean, sparse | BSD-2-Clause |
| `unix-history-repo` | V7 branch `e005199`, dirty (2 files) | Caldera licence |

Web pages are cited inline with URLs (READ via WebFetch today).

## 1. Plan 9: the whole permission model, not only the append bit

This section is first because Plan 9 is the one system vfs's rights lens was built on, and the coordinator asked for the full model. Short sentences. One idea each. Every claim is READ from the manual pages and the servers in `plan9` (`sys/man`, `sys/src`) and `plan9port` (`include/libc.h`, `src/lib9p`). Nothing was run.

### 1.1 The mode word

A Plan 9 file's `mode` is one 32-bit word (`plan9:sys/include/libc.h:579-587`, same values in `plan9port:include/libc.h:643-658`).

| Bits | Name | What it means |
|---|---|---|
| bits 8,7,6 | owner `rwx` | read, write, execute for the owner (`plan9:sys/man/5/0intro:560-566`) |
| bits 5,4,3 | group `rwx` | the same for members of the file's group |
| bits 2,1,0 | other `rwx` | the same for everyone else; `DMREAD`=4, `DMWRITE`=2, `DMEXEC`=1 |
| bit 31 | `DMDIR` | the file is a directory; `wstat` may not change it (`stat:195-197`; fossil refuses, `9p.c:225-228`) |
| bit 30 | `DMAPPEND` | append-only: "offset is ignored in writes" (`0intro:581-582`); `OTRUNC` on open is ignored too (`stat:116-120`, `open:69-71`); `wstat` may not change its length (fossil `9p.c:251-256`) |
| bit 29 | `DMEXCL` | exclusive use: one open fid at a time across all clients (`stat:121-130`); a lock, not a right |
| bit 28 | `DMMOUNT` | "mounted channel", a kernel-internal mark; the manual comments it out of the user-visible list (`plan9:sys/man/2/stat:174-175,190`) |
| bit 27 | `DMAUTH` | an authentication file made by `auth` messages (`0intro:586-589`); fossil refuses every write on such a fid (`9p.c:131-133`) |
| bit 26 | `DMTMP` | not included in nightly archives (`0intro:590-591`); no bearing on rights |

What each permission bit permits, by file kind:

- On a **file**: `r` = `open(OREAD)` and read the bytes; `w` = `open(OWRITE)`, write, truncate, change length by `wstat`; `x` = `open(OEXEC)`, which "== read but check execute permission" (`libc.h:548`). ramfs shows the exact mapping: write or truncate needs `Pwrite`, read needs `Pread`, exec needs `Pexec` (`plan9:sys/src/cmd/ramfs.c:413-421`).
- On a **directory**: `r` = read the directory, which returns its entries "exactly as in stat" (`plan9:sys/man/5/read:57-64`) — **so read on a directory IS list, and list returns every stat field of every child**; `w` = create in it (`open:84-90`), remove from it (`remove:24-26`), rename into it (`stat:171-173`); `x` = walk through it (`0intro:563-566`). A directory may be opened only `OREAD` (`ramfs.c:399-403`): there is no separate "list" verb to grant, and no way to grant names without stat fields.

How the three classes combine. **Plan 9 takes the union.** "When the owner attempts to do something to a file, the owner, group, and other permissions are consulted, and if any of them grant the requested permission, the operation is allowed" (`0intro:555-559`). lib9p implements exactly this: it ORs the other bits, then the owner bits if the uid matches, then the group bits (`plan9:sys/src/lib9p/uid.c:13-34`; `plan9port:src/lib9p/uid.c:12-33`). ramfs does the same (`ramfs.c:849-857`). fossil does the same, with one exception for `noworld` users (`plan9:sys/src/cmd/fossil/9p.c:38-60`). Unix is different: it picks one class and stops. The Plan 9 rule means a mode can never give "other" more than the owner gets. That is the same monotonicity vfs already has — grant rows only widen (`src/vfs/storage/grants.py` docstring).

### 1.2 The walk rule, and vfs's edge rule

`walk(5)`: for each element "the file identified by fid must be a directory, and the implied user of the request must have permission to search the directory" (`plan9:sys/man/5/walk:86-92`). "A walk in a directory is regarded as executing the directory, not reading it" (`0intro:563-566`). fossil checks `PermX` on the directory *before* it looks the name up, and `..` is always walkable "so that you can't walk into a directory and then not be able to walk out of it" (`9p.c:842-860`). The 09-28 memo covers cwfs, kfs, the kernel's unchecked `devwalk` and lib9p's unchecked `filewalk`.

The point for spec 164's rule — "to traverse an edge the caller must hold the walk's rung on **both** endpoints": Plan 9's walk needs a right on the **source** only. Walking A → B needs `x` on A. It needs nothing on B. Once at B the caller may `stat` B (free, §1.5) and walk onward only if it has `x` on B. So a Plan 9 walk is a chain of source-side checks; each hop is gated by the node you leave, and the node you arrive at is checked only when you try to leave it or open it. vfs's two-endpoint rule is strictly stronger: it refuses to *arrive* at a node without the rung. That is the right call for vfs (INFERRED): Plan 9 can afford to let you arrive because arriving reveals only what `stat` reveals, and in vfs "arriving" at a graph node returns the node in the result. With `list` as the walk's rung on the intermediate node, vfs's rule becomes "Plan 9's walk, where arriving reveals name and kind only".

### 1.3 `wstat`: who may change mode, name, group — the closest thing to `manage`

`stat(5)` states the rules (`plan9:sys/man/5/stat:168-205`):

| Field | Who may change it | Where enforced |
|---|---|---|
| `name` | anyone with **write on the parent** directory | ramfs `rwstat` (`ramfs.c:676-686`); fossil (`9p.c:313-320`) |
| `length` | anyone with **write on the file**; never on a directory; never on an append-only file | ramfs (`:668-673`); fossil (`:251-262`) |
| `mode`, `mtime` | the **owner**, or the **group leader** of the file's current group | ramfs: owner or group, "because of lack of users file, leader=>group itself" (`:688-696`); fossil: "not owner or group leader" (`:283-294`) |
| `gid` | the owner, if a member of the new group; or the leader of **both** groups | ramfs (`:698-712`); fossil (`:296-310`) |
| `uid` (owner) | **nobody**: "it is illegal to attempt to change the owner of a file" (`stat:203-205`); fossil allows it only under the console's `wstatallow` switch (`:342-352`) |
| `DMDIR` | nobody (`stat:195-197`) |

So Plan 9 splits "may change the data" (write on the file), "may change where it lives" (write on the parent) and "may change who may" (owner or group leader). The third is keyed by **identity**, not by a bit: there is no mode bit that confers it. That is the shape the parked `manage` question in `open-questions.md` calls option (c), owner-only administration — with one addition vfs does not have: a *group leader* who can administer every file in the group. (The 09-28 memo and the `manage` entry already note NFSv4's `WRITE_ACL`; Plan 9 is the identity-keyed version of the same idea.)

### 1.4 Groups: leaders, `none`, the host owner, no root

- The file server's user list is `/adm/users`, one line per user: `id:name:leader:members` (`plan9:sys/man/6/users:8-30`). **Every user is also a group** with that name. The leader field may be empty, "in which case any group member is a group leader" (`users:31-35`). fossil implements that fallback (`plan9:sys/src/cmd/fossil/9user.c:276-305`); the console sets or clears a leader (`sys/man/8/fossilcons:555-568`).
- **`none`** is the unauthenticated user. It can never be a group leader (`9user.c:284-287`), cannot create (`9p.c:597-600`) and cannot write (`9p.c:131-133`). ramfs attaches an empty uname as `none` (`ramfs.c:288-294`).
- **The host owner** is a kernel notion, not a file-server one: `/dev/hostowner` names the user who booted the machine, who "also has group permissions for any local devices" (`plan9:sys/man/3/cons:170-176`). It is not a superuser on a file server.
- **There is no root.** `/adm/users` is owned by `adm` and is changed only from the server console (`users:52-56`). fossil's only overrides are console switches — `fsysNoPermCheck` / `ConNoPermCheck` skip the check (`9p.c:62-65`) and `wstatallow` relaxes `wstat` (`9p.c:283`) — not a user. Two more group conventions shape rights: the `noworld` group masks the world bits "except when walking directories" (`9p.c:49-57`, `sys/man/4/cwfs:131-141`), and if a `write` group exists only its members may write, "no matter what the permission bits say" (`9user.c:164-186`).

### 1.5 `stat` needs no permission on the file — the "see the name, not the contents" precedent

"The stat request requires no special permissions" (`stat:185`). Only the walk to the file's parent is checked (§1.2). What `stat` reveals (`stat:40-85`): `qid`, `mode` (all permission and `DM*` bits), `atime`, `mtime`, `length`, `name`, `uid`, `gid`, `muid` (who last modified it). So a Plan 9 "lister" learns size, both times, owner, group and last modifier of a file it may not open. The `atime` of a directory is bumped by "an attach, walk, or create, all whether successful or not" (`stat:150-160`): a probe channel. vfs's `list` shows name and kind only; §5 argues why.

### 1.6 `ORCLOSE` and `DMTMP`, as they bear on `contribute`

`ORCLOSE` ("remove on close") "requires permission to remove the file from its directory" at open time (`open:72-78`), and lib9p checks `AWRITE` on the parent for it (`plan9:sys/src/lib9p/srv.c:401-405`). Remove itself needs write on the parent (`remove:24-26`; `ramfs.c:640-641`; lib9p `srv.c:565-568`). So in Plan 9 **"may delete your own file" and "may delete any file" are the same right**: write on the directory. Plan 9 has no sticky bit (EXECUTED: zero hits for `sticky`/`ISVTX` in `sys/man/5`, `sys/man/2/stat`, `sys/include/libc.h`). A `contribute` rung that lets a caller remove only its own rows therefore has no Plan 9 precedent; it comes from BSD's sticky directory (§5). `DMTMP` has no bearing.

### 1.7 Is Plan 9 a total order? No. What is the nearest ladder reading?

Plan 9's model is **three independent bits per class, three classes unioned**. `r`, `w`, `x` do not include one another. Write-only files are legal (a drop box: `w` without `r`). Exec-only directories are legal (`x` without `r`: walk by name, no listing).

The nearest total-order *reading*, by object kind:

- **Directories**: `—` < `x` (walk through; `stat` children you can name) < `rx` (list every child with full `stat`) < `rwx` (create, remove, rename). Each step includes the one before. This reading drops `w` without `x` and `r` without `x`, which Plan 9 allows but nobody uses.
- **Files**: `—` < `r` < `rw`. With `DMAPPEND` set on the file, `w` means append. The brief's reading `a < r < rw` is **not** an inclusion chain: append-only write (`w` on a `DMAPPEND` file) does not include read. It is a drop box. The honest chain is `—` < `r` < `r` + append (`rw` on a `DMAPPEND` file) < `rw` on a plain file. Note the last step is a change to the *file's mode bit*, not to the caller's rights: `DMAPPEND` is a property of the row, and every writer of that row is append-only.

What vfs should borrow (INFERRED from the READ facts above):

1. **The walk rule and its order**: check the right on the node before looking up the name; a refusal never depends on existence (the 09-28 memo's verdict, re-confirmed for fossil `9p.c:842-860`).
2. **`stat` without read** as the *shape* of `list` — a node you may name but not open — trimmed to name and kind (§5).
3. **Append-only as a directory-level posture.** Plan 9 only has it per file (`DMAPPEND`). vfs's `inbox` posture would be "every row under here is `DMAPPEND` for the contributor, and new rows may be created". Plan 9 has no per-directory form; afs does (§4.6).
4. **The union rule**: more specific classes never narrow — vfs's "rows only widen" already matches.
5. **Identity-keyed administration** (owner or group leader may change mode and group) as the precedent for `manage`, when that question reopens.

What vfs should not borrow: the bits themselves. Three independent bits per class make 2^3 states; vfs's row label (`everyone_level`) and range algebra need one integer per row and a meet that is `min`. A total order is the design; Plan 9 is prior art for the *rungs*, not for the lattice.

## 2. The table

Columns: the "list" rung — its name, what it reveals, and whether it sits strictly below read in a total order; the "contribute" rung — its name and what it allows (create / append / modify own / delete own / modify others); and whether the system is a ladder or bits.

| System | "list" rung: name — reveals — strictly below read? | "contribute" rung: name — create / append / modify own / delete own / modify others | Ladder or bits |
|---|---|---|---|
| **Plan 9** (§1) | `x` on the parent + free `stat` — name, kind, **length, mtime, atime, owner, group, muid** — *not a rung*: `r` on the directory is the list; `x`-only is a weaker right that still reveals full `stat` | `DMAPPEND` on the file (`w` on it = append) — create: via `w` on the parent (any writer) / append: yes / modify own: no concept / delete own: = delete any (write on parent) / modify others: yes if `w` | **bits** (3 per class, union of classes) |
| **Unix / FreeBSD** (09-28 memo; §5 here) | `x` on the parent — name probing + full `stat` — bits | sticky dir `S_ISTXT`: create: `w` on dir / append: `O_APPEND` is a flag, not a right / delete own: **yes, owner of file or dir** (`ufs_lookup.c:117-125`) / rename own: same (`ufs_vnops.c:1628-1637`) / modify others: `w` on the file decides | **bits** + one per-directory mode |
| **NFSv4 ACL** (RFC 8881 §6.2.1.3; FreeBSD `acl.h`) | `ACE4_READ_ATTRIBUTES` — "basic attributes (non-ACLs)" — a bit, not a rung | `ACE4_ADD_FILE`, `ACE4_ADD_SUBDIRECTORY`, `ACE4_APPEND_DATA` ("modify ... only starting at EOF"); delete own: `ACE4_DELETE` on the target vs `ACE4_DELETE_CHILD` on the parent, sticky bit noted; modify others: `WRITE_DATA` | **bits** (14 mask bits) |
| **Jackrabbit Oak / JCR** (§4.1) | `rep:readNodes` — node existence and name, child names, primary type; **no properties** — an independent bit; `jcr:read` = `readNodes` + `readProperties` | `jcr:addChildNodes` on the parent (+ `rep:addProperties` for content) — create: yes / append: no concept / modify own: **no concept** / delete own: no concept / modify others: `jcr:modifyProperties`, a separate bit | **bits** (aggregates are named unions) |
| **Nuxeo** (§4.4) | `Browse` — "know about a document, but not necessarily get detailed information" — **yes**: `ReadProperties` ⊃ `Browse`, `Read` ⊃ both, declared | `AddChildren` on the folder — create: yes / append: no / modify own: **no concept** / delete own: `Remove` on doc AND `RemoveChildren` on parent / modify others: `WriteProperties` | **inclusion lattice** with a 3-rung UI (Read < ReadWrite < Everything) |
| **SpiceDB / OpenFGA** (§4.2) | none; `can_see` in an OpenFGA fixture is a synonym of `can_view` | `contributor` appears only as a membership tier (SpiceDB `lookupsametypes.yaml:16`) | **relation graph**; ladder written by hand (`view = viewer + edit`) |
| **GitLab** (§4.3) | **Guest** — project exists, name, issues, members; **no code** on private projects — **yes**: integers 10 < 20 < 30 < 40 < 50, each role `inherits_from` the lower | Guest: `create_issue`, `create_note`, `upload_file`; **`_update_authored_work_item`, `_update_authored_snippet`, `_delete_authored_timelog`** — own-only, by permission name | **ladder** (integer compare), with two off-ladder roles (Planner, Security Manager) |
| **Postgres / PostgREST** (§4.5) | column privilege `GRANT SELECT (name)` — the row exists, the chosen columns only — **yes** as a subset of SELECT; RLS = absent | `GRANT INSERT` without UPDATE/DELETE = create only; own: RLS policy `USING (owner = current_user)` for UPDATE/DELETE; PostgREST's "write-only" table = drop box | **bits** (privileges) + predicates (RLS) |
| **SharePoint** (§4.7) | **Limited Access** (Open; no View Items) — route to an item, name — **yes**: Read = "Limited Access permissions, plus View Items, Open Items …" | **Contribute** = Read + Add Items, **Edit Items, Delete Items**, Delete Versions — modify others: **yes**; "own items only" is a per-list setting (Override List Behaviors overrides it) | **ladder** (each level "X permissions, plus:") |
| **Google Drive shared drives** (§4.8) | Viewer (sees names and contents) — Drive's limited-access folder "can see … but can't open" (09-28 memo) | **Contributor** = view, comment, **edit files** (any), create, restore from trash; cannot move within the drive, cannot trash — modify others: yes; delete own: **no** | **ladder** (Viewer < Commenter < Contributor < Content manager < Manager) |
| **S3** (§4.9) | `s3:ListBucket` — Key, **Size, LastModified, ETag**, StorageClass; Owner on request — independent action | `s3:PutObject` without `GetObject`/`DeleteObject` = drop box; no append | **bits** (IAM actions) |
| **afs** (§4.6, BSL) | visibility `meta` — "Content hidden, metadata only" — an axis beside the access mode | access mode **`create`** ("Create only") and **`append`** ("Create and append"); delete, rename, exec: No — modify others: no; modify own: no | **ladder**: `readonly < create < append < readwrite`, plus a 2-value visibility axis |
| **mirage** | hide/show (absent vs visible; 09-28 memo) — no list-only | none; `append` is a VFS method, mounts are read-only or writable | **two states** per path + ask/deny on commands |
| **deepagents** | none (`ls` is a "read" operation) | none; operations are `read` / `write` | **two bits** per glob, allow/deny/interrupt |
| **eve** | n/a (memory, not files) | `byPrincipal` scope: each principal's records are its own partition; "own" = authenticated principal id, never model input | **partition**, not a ladder |
| **Discord / Slack** (one line) | n/a | Discord: `SEND_MESSAGES` posts; `MANAGE_MESSAGES` "Allows for deletion of other users messages" — "own" is the default, "others" is the extra bit. Slack: `who_can_post` per channel | **bits** |

## 3. What `list` should reveal

**The consensus is "name and kind".** Every system that shows an entry the caller may not open shows at least its name and whether it is a container: Plan 9 `stat` (name + `DMDIR`), Nuxeo `Browse` (the document in a folder listing or a search result, `NXCore-Security.txt:98-102`), SharePoint Limited Access (the route to an item), GitLab Guest (the project's name and that it is a project), afs `meta`, Oak `rep:readNodes` (node name and primary type — type is needed to render a tree), S3 `CommonPrefixes` (a prefix is a "directory"). Kind is needed for navigation: an agent cannot decide whether to `ls` or `read` a name without it, and Unix's `scandir` returns it from the directory entry with no `stat` (09-28 memo §2.1 item 6).

**Each extra field adds a leak the field has already measured:**

| Field | Who reveals it at the list rung | The leak |
|---|---|---|
| size / length | S3 (`Size`), Plan 9 `stat` (`length`), Unix `0711` (`stat` on the parent) | activity and content shape: a growing log, an empty vs full file; the 09-28 memo saw APFS directory size move when a hidden sibling appeared |
| mtime | S3 (`LastModified`), Plan 9 `stat`, Unix | *when* someone worked on it; Plan 9's directory `atime` moves on failed walks, a probe channel (`stat:150-160`) |
| owner / muid | Plan 9 `stat` (`uid`, `muid`), S3 `Owner` on request | *who* works on it; vfs's `owner_id` is also the key of the owner floor, so revealing it tells a lister which rows a given principal can always read |
| ETag / hash | S3 | whether two unreadable files have the same content; whether content changed between two listings |
| child count / link count | Unix (`nlink`), Oak `hasNodes` under `rep:readNodes` | how many hidden siblings exist; the 09-28 memo watched the link count go 4 → 5 |
| version | vfs's own `version` column | same as mtime: a change counter on a row you cannot read |

Oak is the one system that lets a lister see children's *names* without properties and asks nothing about size, because a JCR node has no size — its "content" is properties, all behind `rep:readProperties` (`oak-doc/.../mappingtoprivileges.md:41-48`). That is the cleanest statement of the floor: **name, kind, and the child names you may also list; nothing that is a property of the body.** Nuxeo's wording — "know about a document, but not necessarily get detailed information about it" — is the posture sentence vfs wants.

Two vfs-specific points (INFERRED): `list` on a directory must show only children at `list` or above, trimmed as the road is (ADR 070), or the directory's child *count* leaks. And the `version` and `updated_at` columns are the vfs equivalents of mtime and link count; the 09-28 memo already names them as must-not-show on a road directory (§5.1 condition 1). The same rule should hold for a `list`-level file.

## 4. Evidence per source

### 4.1 Jackrabbit Oak (JCR)

- The privilege set (READ): `jcr:read` aggregates `rep:readNodes` and `rep:readProperties`; `jcr:modifyProperties` aggregates `rep:addProperties`, `rep:alterProperties`, `rep:removeProperties`; `jcr:write` aggregates `jcr:modifyProperties`, `jcr:addChildNodes`, `jcr:removeChildNodes`, `jcr:removeNode`; `rep:write` adds `jcr:nodeTypeManagement` (`jackrabbit-oak:oak-security-spi/src/main/java/org/apache/jackrabbit/oak/spi/security/privilege/PrivilegeConstants.java:245-249`). The non-aggregates are listed at `:230-236`.
- They are **bits**: `PrivilegeBits.java:41-49` assigns one bit each (`READ_NODES = 1`, `READ_PROPERTIES = 2`, …) and `READ = READ_NODES | READ_PROPERTIES` (`:63`). `calculatePermissions` (`:265-296`) maps `READ_NODES` alone to `Permissions.READ_NODE` and `READ_PROPERTIES` alone to `Permissions.READ_PROPERTY` — so a principal can read *properties* of a node it cannot *see*. A total order forbids that state; Oak allows it.
- "See the node name but not its properties" is `rep:readNodes` without `rep:readProperties`. The API mapping says what that buys: `Session.nodeExists`, `Session.getNode`, `Node.hasNode`, `Node.hasNodes`, `Node.getNodes` need `rep:readNodes`; `Node.getProperty`, `Node.getProperties`, `Session.getProperty` need `rep:readProperties` (`oak-doc/src/site/markdown/security/privilege/mappingtoprivileges.md:30-48`). The doc frames it as finer-grained deny, not as a rung: "specifying `rep:readNodes` or `rep:readProperties` privileges allows to grant or deny access to nodes and properties" (`oak-doc/.../permission.md:230-236`; `privilege/default.md:77-86`). Tests exercise the split both ways (`oak-jcr/src/test/.../ReadPropertyTest.java:45-68`: allow `readProperties` only; deny `readNodes` only).
- `TreePermission` has the split in its interface: `canRead()` (the tree), `canRead(PropertyState)`, `canReadProperties()`, `canReadAll()` (`oak-security-spi/.../TreePermission.java:51-80`). Inside, the cached `ReadStatus` is a **three-step chain** `THIS ⊂ THIS|PROPERTIES ⊂ ALL` (`oak-core/.../permission/ReadStatus.java:25-62`) — Oak's evaluator keeps a mini-ladder (node < node+properties < subtree) even though the grant model is bits. `CompiledPermissionImpl.canRead()` asks for `READ_NODE` and marks `skipped` when an entry carries only `READ_PROPERTY` (`oak-core/.../CompiledPermissionImpl.java:520-546`).
- "Add child but not modify": `Node.addNode` needs `jcr:addChildNodes` **on the parent** (`mappingtoprivileges.md:78`); `calculateWritePermissions` grants `ADD_NODE` from the parent's bits only (`PrivilegeBits.java:299-305`). Removal needs `jcr:removeChildNodes` on the parent **and** `jcr:removeNode` on the node (`:307-324`) — the NFSv4 `DELETE_CHILD`/`DELETE` pair. Writing the new node's properties still needs `rep:addProperties` at the new path (inherited from the parent's ACL in practice; INFERRED). Oak has **no "own" notion** in its privilege set: nothing says "alter nodes you created". A contributor is `addChildNodes + addProperties` without `alterProperties`, `removeProperties`, `removeNode`: create and fill, never change — and never change your own either.

### 4.2 SpiceDB and OpenFGA

- SpiceDB's canonical ladder: `permission edit = editor`, `permission view = viewer + edit + parent->view` (`spicedb:internal/namespace/test/testdata/schema/basic.zed:5-14`); the dev playground schema has `permission write = writer`, `permission view = reader + write` (`development/schema.yaml:9-14`); the README's folder example is `permission view = viewer + parent->view` (`README.md:188`). The inclusion `edit ⊆ view` holds **only because the author wrote `view = … + edit`**; the schema language has no notion of a rung above another.
- OpenFGA, the same shape: `define editor: [user] or editor from parent`, `define viewer: editor` (`openfga:docs/check/README.md:59-60`); `define viewer: [user, user:*, group#member] or editor or viewer from parent` (`docs/list_objects/example/example.md:29-30`).
- No "lister" below viewer in either repo. OpenFGA's `define can_see: can_view` (`openfga:assets/tests/consolidated_1_1_tests.yaml:6425`) is a synonym in a test of relation chaining, not a name-only right. SpiceDB's `contributor` (`internal/services/integrationtesting/testconfigs/lookupsametypes.yaml:15-16`) is a *membership tier* of a usergroup (`member = direct_member + contributor + manager`), not an add-only right on a resource. No "own" notion exists in either schema language; "the creator may edit" is modelled as a relation `creator: user` on the resource plus `permission edit = editor + creator` (the `creator` relation at `lookupsametypes.yaml:8` is of that shape).
- **What this means for borrowing their words.** `viewer`, `editor`, `owner` are the field's names for the rungs, and `view`/`edit` the names for the checks. But these systems are relation graphs: a permission is a set expression, two permissions may overlap without either including the other, and nothing stops `edit` from admitting a subject `view` refuses. vfs can borrow the *words* and must not borrow the *structure*: in vfs the inclusion is a law of the label (`LEVEL_RANK`), not a convention of the schema author.

### 4.3 GitLab

- The ladder is integers: `NO_ACCESS 0, MINIMAL_ACCESS 5, GUEST 10, PLANNER 15, REPORTER 20, SECURITY_MANAGER 25, DEVELOPER 30, MAINTAINER 40, OWNER 50, ADMIN 60` (`gitlabhq:lib/gitlab/access.rb:11-21`). Checks compare: `team_access_level >= Gitlab::Access::GUEST` (`app/policies/project_policy.rb:55-59`); the level is the max over memberships (`project.max_member_access_for_user`, `:1032-1037`). Roles are declared with `inherits_from` so each includes the lower: `reporter.yml` inherits `guest` (`config/authz/roles/reporter.yml:4-6`), and the policy concern enables every inherited permission (`app/policies/concerns/authz/role_permissions.rb:8-24`).
- **GitLab's ladder has sprouted two off-ladder roles.** `level_encompasses?` carves out `PLANNER` and `SECURITY_MANAGER` as `non_hierarchy_roles` that "can only be assigned by owners or by users with the same role" (`access.rb:44-52`). A warning for vfs: once a role is not a strict superset of the one below, the integer compare lies, and special cases appear.
- **Guest is the `list` rung for a private project.** The role description: "View and comment on issues and epics. Cannot push code or access repository. This role applies to private and internal projects only" (`config/authz/roles/guest.yml:2-4`; `doc/user/permissions.md:54`). Guest's raw permissions include `read_project`, `read_project_member`, `read_issue`, `read_wiki`, `read_release` and **not** `read_code` or `download_code` (`guest.yml:6-62`); Reporter adds `read_code`, `download_code` (`reporter.yml:46-47,62`). `rule { guest }.enable :read_project` (`project_policy.rb:325`). The docs' repository table marks Guest ✓ for "View project code" with footnote 1: "users with the Guest role are able to perform this action only on public and internal projects (not on private projects)" (`doc/user/permissions.md:803,829-832`). So on a private project a Guest sees that the project exists, its name, description, members and issues — name and kind and a little more — and nothing of its contents.
- **Guest is also a `contribute` rung with an "own" qualifier.** Guest holds `create_issue`, `create_note`, `create_task`, `create_work_item`, `upload_file` and the authored-only set `_update_authored_work_item`, `_update_authored_snippet`, `_reopen_authored_work_item`, `_delete_authored_timelog` (`guest.yml:6-30`). The leading underscore marks a permission conditioned on the record (authored by, assigned to), and `admin_issue` (edit anyone's) is Reporter's (`reporter.yml:17`). This is the closest precedent in the study to vfs's "create, and alter only your own": a total-order role whose write permissions are split by authorship.

### 4.4 Nuxeo

- The permission lattice is declared as `include`s (`nuxeo:modules/core/nuxeo-core/src/main/resources/OSGI-INF/permissions-contrib.xml:14-73`): `Browse` atomic; `ReadProperties` includes `Browse`; `Read` includes `Browse`, `ReadVersion`, `ReadProperties`, `ReadChildren`, `ReadLifeCycle`, `ReadSecurity`, `ReviewParticipant`; `Write` includes `AddChildren`, `WriteProperties`, `Remove`, `ManageWorkflows`, `WriteLifeCycle`, `WriteVersion`; `ReadWrite` = `Read` + `Write`; `Everything` is "god-level". The provider validates that every included permission was registered first (`DefaultPermissionProvider.java:218-230`).
- The spec text (`modules/core/nuxeo-core/doc/NXCore-Security.txt:65-106`): "`Browse`: know about a document, but not necessarily get detailed information about it"; "`ReadProperties` … gives access to all the document's content … `ReadProperties` implies `Browse`"; "`ReadChildren`: read the list of children of a folder"; "To view a document when a folder is listed, the `Browse` permission is needed on the document. To view a document in a search result, the `Browse` permission is needed"; "To remove a document, `RemoveChildren` is needed on the parent folder *and* `Remove` is needed on the document itself."
- Enforcement (`modules/core/nuxeo-core/src/main/java/org/nuxeo/ecm/core/api/AbstractSession.java`): `exists()` is `hasPermission(doc, BROWSE)` (`:855-861`); queries are filtered by the `BROWSE` permission set (`:1282`); `getChild` checks `READ_CHILDREN` on the parent then `READ` on the child (`:866-871`); listing a folder checks `READ_CHILDREN` (`:868-1029`, eleven sites); create checks `ADD_CHILDREN` on the destination (`:773`, `:2141`); remove checks `REMOVE_CHILDREN` on the parent (`:1384`, `:1464-1466`).
- **So Nuxeo's `Browse` is the best-matched `list` precedent**: an entry you can see in a listing and in search results but not open, and it is strictly included by `ReadProperties` and `Read` by declaration. It is still a grant unit, not a rung of a total order — `AddChildren` can be granted without `Read`, and `Browse` on the child plus `ReadChildren` on the parent are two separate facts (vfs's `list` on the directory would imply both). The UI collapses the lattice to a three-rung ladder: `Read`, `ReadWrite` (shown with a `denyPermission="Write"`), `Everything` (`permissions-contrib.xml:102-106`). Nuxeo's `AddChildren` without `WriteProperties` is "create, never alter" and has **no "own" notion**; creator-based editing is a policy over `dc:creator` [NOT VERIFIED: I did not read the security-policy module].

### 4.5 Postgres and PostgREST

- **Column privileges** express "the row exists, these columns only": `GRANT SELECT (col1), UPDATE (col1) ON mytable TO miriam_rw` (`postgres:doc/src/sgml/ddl.sgml:2857`); "A user may perform SELECT … on a column if they hold that privilege for either the specific column or its whole table" (`doc/src/sgml/ref/grant.sgml:358-364`). A role with `SELECT (path, kind)` sees every row's path and kind; `SELECT *` fails. That is vfs's `list` as a column set — but per table, not per row: to show some rows at `list` and others at `read` you need two roles, a view, or RLS.
- **Row-level security** is the other axis: "Rows for which the expression does not return true will not be processed" (`ddl.sgml:2953-2960`); with RLS on and no policy, "no rows are visible or can be modified" (`:2935-2941`). That is ADR 065's hidden-is-absent. So Postgres has *two* mechanisms where vfs has one label: RLS for `none` vs visible, column privileges for `list` vs `read`. A UI over PostgREST shows a column-restricted row as a row with missing fields; it never shows a row RLS hid.
- **`contribute` in Postgres terms** is `GRANT INSERT` without `UPDATE`/`DELETE` (create, never alter), plus the standard RLS recipe for "own": a policy `FOR UPDATE USING (owner = current_user)`. Postgres has no built-in "own row" right; the owner column and the policy are the application's. PostgREST documents the pure drop box: a "write-only" table where `Prefer: return=headers-only` fails because the role cannot select the row back (`postgrest:docs/references/api/preferences.rst:141`).

### 4.6 The agent VFSs: afs, mirage, eve, deepagents

- **afs (BSL 1.1, study only)** has the most direct precedent for both rungs. Access modes form a four-row table whose rows each include the previous (`afs:spec/afs-protocol.md:538-545`): `readonly` (read, list, stat, search, explain: Yes; write, delete, exec, rename: No), **`create`** (write: "Create only"), **`append`** (write: "Create and append"), `readwrite` (all Yes). The type is `"readonly" | "create" | "append" | "readwrite"` (`packages/core/src/type.ts:99`). Neither `create` nor `append` allows delete or rename, and neither says anything about "own" — a contributor cannot alter even its own file. Visibility is a separate two-value axis: `full` "Content and metadata visible", **`meta` "Content hidden, metadata only"** (`spec/afs-protocol.md:548-551`) [NOT VERIFIED: which metadata fields `meta` returns; the spec does not list them]. afs also grades *actions* by severity (`ambient < boundary < critical`) and policies by what they allow (`safe < standard < full`) (`:553-570`) — a third ladder, over side effects.
- **mirage**: `hide`/`show` for paths, `allow`/`ask`/`deny` for commands ("a hidden path is not merely unreadable but absent", `mirage:README.md:86`); refusals are `deny`/`pending`/`failed` (`python/mirage/types.py:755-780`). No list-only state; no append-only right (`append` is a VFS method, `python/mirage/vfs/base.py:406-422`; mounts are read-only or writable, `base.py:217`). The 09-28 memo covers its road rule.
- **eve**: `byPrincipal` is a *scope*, "an authorization partition, not a model-selected routing hint"; it is derived from authenticated context, "deliberately excludes messages, user-authored turn input", and returns `null` (slot disabled) for anonymous and runtime principals (`eve:research/first-class-memory.md:346-356,402-411`). Relevance: eve's definition of "own" — the authenticated principal id, stamped by the runtime, never by the model — is the rule vfs's `owner_id` should follow, and `open-questions.md` already flags that the system-actor path does not validate a declared `owner_id`.
- **deepagents**: `FilesystemOperation = Literal["read", "write"]` (`deepagents:libs/deepagents/deepagents/middleware/filesystem.py:123`); rules are `allow`/`deny`/`interrupt` per glob (`:387-406`). `ls`, `glob`, `grep` are "read". No list-only, no append-only, no "own".

### 4.7 SharePoint (web)

Source: <https://learn.microsoft.com/en-us/sharepoint/sites/user-permissions-and-permission-levels> (READ 2026-10-14). The team-site levels are a declared ladder, each "X permissions, plus:":

- **Limited Access**: View Application Pages, Browse User Information, Use Remote Interfaces, Use Client Integration Features, Open. (The 09-28 memo: the route to an item; no View Items.)
- **Read** = Limited Access + View Items, Open Items, View Versions, Create Alerts, Use Self-Service Site Creation, View Pages.
- **Contribute** = Read + **Add Items, Edit Items, Delete Items, Delete Versions**, Browse Directories, Edit Personal User Information, Manage Personal Views, Add/Remove/Update Personal Web Parts. "Edit Items: Edit items in lists, edit documents in document libraries" — **any item, not only your own**.
- **Edit** = Contribute + Manage Lists. **Design** = Edit + pages, themes, Approve Items. **Full Control** = all.
- The "own items only" rule is a **per-list setting**, not a level: the Design-level permission "Override List Behaviors" is described as "change or override settings that allow users to read/edit only their own items". So SharePoint's "contribute your own" = Contribute level + the list's item-level setting; the level alone edits everything.
- **View Only** is a sibling, not a rung: it has View Items but not Open Items (cannot download), which neither includes nor is included by Read.

### 4.8 Google Drive shared drives (web)

Source: <https://support.google.com/a/users/answer/9310460> (READ 2026-10-14; the table on <https://support.google.com/a/users/answer/9310352> is partial). The access levels are a ladder: **Viewer** (view) < **Commenter** (+ comment) < **Contributor** (+ edit files, create and add files and folders, add people on specific files, restore from Trash, move from My Drive in) < **Content manager** (+ move within the drive, move to Trash) < **Manager** (+ permanently delete, add/remove members). Verified rule for Contributor: it **can edit any file** and **cannot trash any file, including its own**; the brief's "add and edit own, not others'" is not what the table says. One footnote: "In Google Drive for desktop or files in the Chrome OS Files app, Contributor access gives only read access to files." Drive's "Contributor" is therefore "create and edit, never delete or move" — delete is the step Drive withholds, not editing others' work.

### 4.9 S3 (web)

Source: <https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html> (READ 2026-10-14). "To use this operation … you must have permission to perform the `s3:ListBucket` action"; no per-object permission is required. Each `Contents` entry carries `Key`, `LastModified`, `ETag`, `Size`, `StorageClass`, optionally `Owner` (with `fetch-owner=true`), `ChecksumAlgorithm`, `RestoreStatus`. So an S3 lister learns **size, mtime and a content hash** of every object it cannot `GetObject`. Directories are `CommonPrefixes` (a prefix is the only "kind"). The 09-28 memo §4.4 covers the console walkthrough.

### 4.10 Discord and Slack (one line each, web)

Discord's developer reference splits `SEND_MESSAGES` ("sending messages in a channel") from `MANAGE_MESSAGES` ("Allows for deletion of other users messages") — deleting *others'* is the extra bit; deleting your own needs no permission [NOT VERIFIED from Discord's page itself; from
<https://docs.discord.com/developers/platform/server-and-channel-management>
via search summary]. Slack restricts posting per channel with a `who_can_post`
preference (admins, org admins, specific users)
(<https://slack.com/help/articles/4409225141907-Manage-who-can-set-channel-posting-permissions>,
<https://docs.slack.dev/reference/methods/admin.conversations.setConversationPrefs>);
whether it blocks editing your own earlier posts was not found.

## 5. What `contribute` should allow

The field's "contribute"-shaped rights, side by side:

| Right | create new | append to existing | edit own | delete own | edit others | delete others |
|---|---|---|---|---|---|---|
| afs `create` | yes | no | no | no | no | no |
| afs `append` | yes | yes | no | no | no | no |
| Plan 9 `DMAPPEND` + `w` | (parent decides) | yes | no (append only) | = delete any | append only | = delete any |
| NFSv4 `ADD_FILE` + `APPEND_DATA` | yes | yes | no | `DELETE` on target | no | `DELETE_CHILD` |
| BSD sticky directory + `w` on dir | yes | (file bits) | (file bits) | **yes** | (file bits) | **no** |
| Oak `addChildNodes` + `addProperties` | yes | no | no | no | no | no |
| Nuxeo `AddChildren` | yes | no | no | no | no | no |
| Postgres `INSERT` + RLS on owner | yes | no | by policy | by policy | no | no |
| GitLab Guest | issues, notes, uploads | n/a | **authored only** | authored timelog | no | no |
| SharePoint Contribute | yes | n/a | yes | yes | **yes** | **yes** |
| Drive Contributor | yes | n/a | yes | **no** | **yes** | no |
| Discord Send Messages | yes | n/a | own | own | no | no (Manage Messages) |

Three things follow.

1. **"Create and append, never alter" is well attested** (afs, Plan 9, NFSv4, Oak, Nuxeo, Postgres `INSERT`). It is the drop-box / journal / add-only ingest shape the addendum names. Every one of these is strictly between read and write when read is also held: a creator can do everything a reader can, plus create; a writer can do everything a creator can.
2. **"Alter only your own" is attested but always keyed by identity, never by a bit**: the sticky directory tests ownership of the file or of the directory (`freebsd-src:sys/ufs/ufs/ufs_lookup.c:117-125`, `sys/ufs/ufs/ufs_vnops.c:1628-1637`, `sys/fs/tmpfs/tmpfs_vnops.c:192-199`; RFC 8881 §6.2.1.3.2 names it for NFSv4); GitLab names authorship in the permission (`_update_authored_*`); Postgres puts the owner column in the policy; Discord makes "own" the default and "others" the extra bit. The products that call the level "Contribute"/"Contributor" (SharePoint, Drive) do **not** restrict to own; SharePoint moves "own only" to a list setting and Drive withholds delete instead.
3. **So vfs's `contribute` = (2) layered on (1), and vfs already has the key.** The owner floor (`Rights.admits(path, owner_id, everyone_level)`, `src/vfs/storage/grants.py:468-485`; EXECUTED today: with `read` on `/eng`, `write admits` is False and `owner floor write` is True) already says "a principal may always write a row it owns". `contribute` then needs only: `GateMode.create` passes at `contribute`; `modify`/`upsert` of an existing row falls through to the owner floor (the addendum's own phrasing, matching `GateMode = Literal["modify", "upsert", "create", "read"]`, `src/vfs/storage/backends/database/rights.py:154-157`). "Own" is `owner_id` on the row, which the sticky bit calls "owner of the file". The sticky bit's *second* test — "or owner of the directory" — maps to "the directory's owner holds `read_write` below it", which the owner floor does not give today (the floor is per row, not per subtree); the ADR should say whether a directory owner may remove a contributor's row under it.

Two sub-questions the ADR must answer, with the precedent for each:

- **Is append a separate thing from create for vfs?** Plan 9 and NFSv4 say yes at the byte level (offset ignored). vfs's `write` is whole-body; its `edit` is a body transform. An agent "appending to a journal" in vfs is `edit` on a row it may not own. afs's ladder puts `create` below `append` (one more thing allowed), so "create only" is a real posture there. vfs can fold them: `contribute` = create + alter own, and "append to someone else's row" is not a rung but a verb (`append`) that could later map to `contribute` on the row [INFERRED]. If vfs ever wants afs's `create`-only rung, the order would be `read < create < contribute < read_write`, which still nests.
- **May a contributor delete its own row?** The sticky bit says yes; afs, Drive and Oak say no; GitLab says yes for authored timelogs. With trash as a tombstone (ADR 074), delete is reversible, so "yes" costs little [INFERRED].

## 6. Posture words

What the field calls "everyone can see names" and "everyone can add":

| Shape | Names in the field | Source |
|---|---|---|
| everyone sees the entry, cannot open it | SharePoint **Limited Access**; Nuxeo **Browse**; afs visibility **`meta`**; GitLab **Guest** ("visibility into a project … but should not have the ability to make changes", `access.rb:86`); Windows ABE's opposite (hide what you cannot open); Drive "can see the restricted folder but can't open it" | §4.4, §4.6, §4.3, §4.7, 09-28 memo §4.3 |
| everyone can add, nobody alters others' | SharePoint **Contribute** (but it edits others'); Drive **Contributor** (edits others', cannot delete); afs **`append`** / **`create`**; Unix **sticky** `/tmp` ("append-only directories", `ufs_lookup.c:121`); Plan 9 **`DMAPPEND`** ("append only", `chmod(1):92`); Discord **Send Messages**; Slack **who can post**; the mail **inbox** / **drop box** / **maildir** idiom; GitLab Guest's "create issue, update authored" | §5 |

For vfs's two posture words:

- **`listed`** for "everyone holds `list`": no system uses the word as a level, but every system's word for the state is about *seeing* ("Limited Access", "Browse", "meta", "Guest … visibility"). `listed` reads well beside `open`/`shared`/`private` because it says what the row is to the public — a name in a listing. The alternative `browsable` (Nuxeo) says the same with a verb the field already uses for exactly this rung.
- **`inbox`** for "everyone holds `contribute`": the field's product words are "Contribute"/"Contributor", but both products let a contributor edit others' work, so borrowing the *word* for the rung while giving it the stricter meaning is a mild mismatch — acceptable if the docstring says "create, and alter only your own". For the *posture*, `inbox` is better than `contribute` because it names the shape, not the rung: a place anyone can drop into and nobody can rifle through others' deposits. Unix calls the same thing a sticky `/tmp`; FreeBSD's comment calls it an "append-only directory" (`ufs_lookup.c:117-121`). `dropbox` is the other field word; it implies write-without-read (Postgres's "write-only" table), which vfs's `contribute` is not (it includes `read`). So: rung `contribute`, posture `inbox`, and the docstring should say that an `inbox` is readable by all, unlike a drop box.

## 7. Open questions

1. **A `list`-level file vs a `list`-level directory.** Nuxeo separates `Browse` (on the child) from `ReadChildren` (on the parent). vfs's one rung on a prefix covers both; the ADR should say that `list` on a directory lists children that are themselves at `list` or above and no others (otherwise the child count leaks, §3).
2. **Does `list` reveal kind only, or kind and the child names you may also list?** Oak's answer (name, type, child names) is the floor; S3 and Plan 9 reveal more. §3 says kind plus the trimmed child names.
3. **Is Postgres's two-axis model (RLS for existence, column privileges for fields) a better fit than one label?** No for vfs: the row label must be one integer for the range algebra, and `list` is exactly "visible row, restricted columns" — the ADR can say that in those words.
4. **Should vfs keep afs's `create`-only rung?** Not now; it nests if wanted later (§5).
5. **The directory owner's say over contributors' rows** (the sticky bit's second test) — needs a decision (§5 item 3).
6. **Clone freshness**: `gitlabhq` and `nuxeo` HEADs are July 2026; if they were not refreshed on 2026-10-13, line numbers in `project_policy.rb` and `guest.yml` may have moved, though the role integers and the YAML shape are stable.

## What the ADR should pin

1. **The ladder is a total order and the label is one integer.** `none < list
   < read < contribute < read_write` (`manage` parked). Each rung includes
   every lower rung by law, not by schema convention — the lesson of
   SpiceDB/OpenFGA (inclusion only because the author wrote `view = viewer +
   edit`) and of GitLab's two off-ladder roles.
2. **`list` reveals path and kind, nothing else.** Not size, mtime, version,
   owner, hash or child count — each is a measured leak (S3 `Size`/`ETag`,
   Plan 9 `length`/`mtime`/`muid`, Unix link count). Oak's `rep:readNodes` and
   Nuxeo's `Browse` ("know about a document, but not … detailed information")
   are the precedents. A `list` directory lists only children at `list` or
   above. `read`, `grep`, `glean`, `versions`, edges and `locate` on a `list`
   row answer `permission_denied` (not not-found: the row is visible).
3. **`list` is Plan 9's free `stat`, trimmed; the walk rule is Plan 9's,
   strengthened.** Check the rung before looking the name up; a refusal
   never depends on existence. A graph walk needs the walk's rung on both
   endpoints (stricter than Plan 9's source-only `x`, because vfs returns the
   node).
4. **`contribute` = create + alter-own, built from two precedents.** "Create,
   never alter" (afs `append`, Plan 9 `DMAPPEND`, NFSv4 `ADD_FILE`/
   `APPEND_DATA`, Oak `addChildNodes`, Nuxeo `AddChildren`, Postgres
   `INSERT`) plus "own" keyed by identity (the sticky bit, Postgres RLS on the
   owner column, GitLab `_update_authored_*`). In vfs: `GateMode.create`
   passes at `contribute`; `modify`/`upsert`/delete fall through to the
   existing owner floor; **"own" is `owner_id` on the row**, stamped by the
   runtime from the authority, never from the payload (eve's `byPrincipal`
   rule; the open question on system-actor `owner_id` validation should close
   with this ADR).
5. **Say explicitly that vfs's `contribute` is stricter than SharePoint's
   Contribute and Drive's Contributor**, which edit others' items; the word
   is borrowed, the rule is the sticky directory's.
6. **Decide delete-own** (lean yes: sticky bit, and trash is a tombstone) and
   **the directory owner's reach over contributors' rows** (the sticky bit's
   "or owner of the directory").
7. **Posture words**: `listed` (everyone holds `list`) and `inbox` (everyone
   holds `contribute`; readable by all, unlike a drop box); everyone capped at
   `read_write`.
8. **One verb→rung table in `ops.py`**, and the 62 literal `"read"` /
   `"read_write"` sites across six modules (EXECUTED: `grep -rn` over
   `src/vfs`, files `params.py`, `permissions.py`, `base.py`,
   `storage/grants.py`, `backends/database/backend.py`,
   `backends/database/rights.py`) read the table rather than the literal.
9. **Do not borrow bits.** Plan 9's three independent bits, Oak's privilege
   bits, NFSv4's mask, Postgres's privilege set: prior art for the rungs'
   meanings, not for the lattice. The one Plan 9 structural rule worth
   keeping is the union (classes never narrow), which vfs's "rows only widen"
   already is.
