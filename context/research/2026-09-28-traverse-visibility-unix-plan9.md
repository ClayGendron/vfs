# Traverse visibility: can a caller see the directories above a grant?

- **Status**: research memo. Commits us to nothing. Input to spec 058's
  read rules (§1 coverage, §5 reads filter, §6 writes check).
- **Date**: 2026-09-28
- **Owner**: Clay Gendron
- **Question**: Alice holds `read` on `/projects/alpha` and nothing
  else. As spec 058 is written, the directories above her grant are
  hidden: `ls /` shows her nothing, and `ls /projects` answers
  not-found. Should they stay hidden (option **a**, strict), or should
  they appear as bare directory names on the road to her grant (option
  **b**, traverse visibility)? Clay's rule: "if there is a clear
  precedent we should follow it."
- **Method**: executed repros on macOS and Linux (study folder below);
  line-level reading of the path walk in V6, V7, Linux, FreeBSD, the
  Plan 9 kernel, lib9p and three Plan 9 file servers; pjdfstest's
  pins; vendor documentation for Windows, SharePoint, Google Drive,
  S3 and NFSv4; the mirage source. This memo is narrower than the
  2026-09-05 lens memos
  (`2026-09-05-permissions-lens-unix-lineage.md`,
  `2026-09-05-permissions-lens-plan9.md`). Those ran nothing and did not
  ask about ancestors. This one measures.
- **Study**: `studies/2026-09-28-traverse-visibility/` (`repro.sh`,
  `errno_matrix.py`, `results.md`, `README.md` with rerun steps).
- **Sources** (refreshed 2026-09-28; licence re-checked after refresh):
  - `linux`: studied at `faeab166` (2026-04-18). **Not refreshed.**
    The clone is dirty (13 case-collision files, e.g.
    `xt_CONNMARK.h` vs `xt_connmark.h`, on a case-insensitive disk), so
    no checkout was allowed. `git fetch` ran for more than 10 minutes
    (the clone is shallow, 11.7M objects to index) and was stopped
    unfinished. `origin/master` is still `faeab166`, and nothing was
    checked out; see §7.
    GPL-2.0 WITH Linux-syscall-note (`COPYING`).
  - `freebsd-src`: refreshed to `origin/main` `ee05a360b02e`
    (2026-09-28). Sparse checkout (`sys/kern`, `sys/sys`, `sys/fs`,
    `sys/vm`, `sys/ufs`, `share/man/man9`). BSD 2-clause (`COPYRIGHT`).
  - `unix-history-repo`: upstream default is
    `Research-PDP7-Snapshot-Development`, which has no `namei` worth
    reading. Studied `origin/Research-V7-Snapshot-Development`
    `e005199` (1979-08-25) and `Research-V6-Snapshot-Development`
    `b3ca6bb` (1975-07-18), both fetched today and read with
    `git show`. Clone dirty (2 case-collision files), not checked out.
    Caldera licence for V1 to V7 (`LICENSE`, `Caldera-license.pdf`).
  - `plan9`: `origin/main` `ed1a9c21e` (2025-10-28); fetch found
    nothing newer, and HEAD already equals it. Clone dirty (12
    case-collision files), not checked out. MIT, Plan 9 Foundation
    2021 (`LICENSE`).
  - `plan9port`: `origin/master` `b6564bd9` (2026-08-26), current.
    MIT, Plan 9 Foundation 2021 (`LICENSE`).
  - `pjdfstest`: `origin/master` `85a8aea` (2026-08-07), current.
    BSD 2-clause (`COPYING`).
  - `mirage`: fetched; read at `origin/main` `e01d62a` (2026-09-28)
    with `git show`, working tree left untouched. Apache-2.0.
  - Web sources are cited inline with URLs.

## 1. The question, in plain terms

A few terms first.

- A **grant** is a row that says "this principal may read (or read and
  write) everything at or under this path prefix."
- An **ancestor** of a grant is a directory above its prefix. For
  `/projects/alpha`, the ancestors are `/` and `/projects`.
- To **traverse** (Unix says *search*) a directory is to go through
  it to a child whose name you already know.
- To **list** a directory is to learn the names inside it.
- To **read** is to see content or metadata.
- **Hidden** in vfs means absent: the row answers not-found, exactly
  like a path that does not exist (ADR 065).

Spec 058's coverage rule is `path = prefix OR path LIKE prefix || '/%'`.
It covers the prefix and everything under it. It covers nothing above
it. So for Alice:

- She can read `/projects/alpha/notes.md` if she knows that path.
- `ls /projects` answers not-found.
- `ls /` shows nothing she can use.

Option (a) keeps this. Option (b) would show `/` containing `projects`,
and `/projects` containing only `alpha`. It would show names only: no
content and no metadata.

The question is whether an established system already made this call,
so that we can follow it.

## 2. Unix: three separate rights, and no right flows upward

### 2.1 What the kernel does (executed)

The repro builds `P/alpha/file.txt` (Alice's grant) and `P/beta/` (a
sibling she should not learn about). Then it sets the mode of `P`, the
ancestor, and tries every operation. It runs as one non-root user. For
the owner, only the owner bits count, so owner mode `0100` behaves
exactly like the classic `0711` home directory does for everyone else.
The results were the same on macOS 25.5 (APFS) and on Linux 7.0
(overlayfs, in Docker, uid 1000).

| Operation | `rwx` | `--x` search only | `r--` list only | `---` |
|---|---|---|---|---|
| list `P` | names | **EACCES** | names | EACCES |
| stat `P` itself | ok | **ok, full metadata** | ok | ok |
| stat `P/beta` (exists) | ok | **ok** | EACCES | EACCES |
| stat `P/nope` (missing) | ENOENT | **ENOENT** | **EACCES** | **EACCES** |
| read `P/alpha/file.txt` | ok | **ok** | EACCES | EACCES |
| list `P/alpha` | ok | **ok** | EACCES | EACCES |
| glob `P/*` | both | **empty, no error** | both | empty, no error |
| `mkdir -p P/alpha/new/deep` | ok | **ok** | EACCES | EACCES |
| `mkdir P/gamma` | ok | EACCES | EACCES | EACCES |

Full captures are in `studies/2026-09-28-traverse-visibility/results.md`.

Here is what the table says, one idea at a time.

1. **Search and list are different rights.** `x` on a directory lets
   you go through it by name. `r` lets you learn the names. Either one
   works without the other.
2. **Search alone reaches the grant.** With `--x` on `P`, the caller
   reads the deep file, lists the deep directory and creates under it.
   It cannot list `P`. This is the Unix shape of "reach it, but don't
   browse to it."
3. **No search hides existence.** Without `x` on `P`, every name under
   `P` answers EACCES. That includes names that do not exist. So the
   caller cannot tell "there" from "not there." The kernel checks
   the right *before* it looks up the name.
4. **Search leaks two things.** A search-only caller can stat `P`
   itself, with full metadata, because stat needs search on the
   *parent* only. And it can probe guessed names: an existing sibling
   answers ok, a missing one answers ENOENT.
5. **The metadata carries the hidden siblings.** In the leak probe, a
   hidden sibling appeared. The search-only caller saw `P`'s link count
   go from 4 to 5 and its mtime move. On APFS it also saw the size grow
   (128 to 160). It then confirmed the new name by guessing it.
6. **List without search shows names and kinds.** `os.scandir` on an
   `r--` directory returned `alpha:dir` and `beta:dir`. The kind comes
   from the directory entry itself, with no stat.

### 2.2 Where it lives in code

The rule is the same in every Unix we read. The walk checks search
permission on each directory **before** it looks up the next name.

- **V6** (1975): `access(dp, IEXEC)` on the directory, then the name
  is gathered and searched
  (`unix-history-repo@b3ca6bb:usr/sys/ken/nami.c:64-65`).
- **V7** (1979): the comment reads "dp must be a directory and must
  have X permission", then `access(dp, IEXEC)`, then the directory scan
  (`unix-history-repo@e005199:usr/sys/sys/nami.c:83-93`). `access()`
  sets `EACCES` when the bits do not allow it (`usr/sys/sys/fio.c:144-174`,
  `EACCES` at `:172`). The V7 manual names the right: "execute
  (search in directory)" (`usr/man/man1/chmod.1:53`).
- **Linux**: `link_path_walk` (`linux:fs/namei.c:2574`) calls
  `may_lookup` (`:2600`) before `hash_name` and the lookup (`:2605`).
  `may_lookup` (`:1951`) checks `MAY_EXEC` through
  `lookup_inode_permission_may_exec` (`:678`). That helper's comment
  says "majority of real-world traversal happens on inodes which grant
  it for everyone" (`:670`), and it fast-paths mode `0111`. Opening a
  directory to list it goes through `may_open` (`:4238`), which asks
  for read.
- **FreeBSD**: `vfs_cache_lookup` (`freebsd-src:sys/kern/vfs_cache.c:3192`)
  calls `vn_dir_check_exec` (`:3210`) before `cache_lookup`, so even a
  cached name is gated first. `vn_dir_check_exec` is `VOP_ACCESS(vp,
  VEXEC, ...)` (`sys/kern/vfs_subr.c:7350-7359`). tmpfs does the same
  (`sys/fs/tmpfs/tmpfs_vnops.c:251`), and the lockless fast path calls
  `VOP_FPLOOKUP_VEXEC` (`sys/kern/vfs_cache.c:6309`). Opening for read
  adds `VREAD` (`sys/kern/vfs_vnops.c:460-461`).
- **pjdfstest** pins the rule in 11 test files, each titled "returns
  EACCES when search permission is denied for a component of the path
  prefix": `chflags`, `chmod`, `chown`, `ftruncate`, `mkdir`, `mkfifo`,
  `mknod`, `open`, `rmdir/07`, `truncate`, `unlink` (e.g.
  `pjdfstest:tests/open/05.t:4,23`; `tests/mkdir/05.t:4,23`). The
  `mkdir` case is a name that does not exist yet, and it still answers
  EACCES. No pjdfstest case probes a *missing* name under an
  unsearchable directory. Our repro fills that gap: it is EACCES.

### 2.3 What Unix says about Alice

The key fact: **Unix never grants anything upward.** A right on
`/projects/alpha` says nothing about `/projects`. Each directory carries
its own bits, set by whoever owns it.

So a literal Unix answer to "Alice has read on `/projects/alpha` and
nothing else" is harsher than either option. With no `x` on
`/projects`, Alice cannot reach her grant at all. Every path answers
EACCES.

In practice nobody runs Unix that way. The convention is that
directories are world-searchable. Linux's own fast path is built on
that assumption (`namei.c:670`). There are two common shapes:

- `0755` (the default): everyone can search **and list**. Alice would
  see `beta` and every other sibling. That leaks more than option (b).
- `0711` (the home-directory privacy idiom): everyone can search, no
  one can list. Alice reaches her grant by full path. She cannot list
  `/projects`. But she can stat it (metadata leak) and probe sibling
  names (existence leak).

vfs's prefix grant already behaves as if every ancestor were
searchable: Alice reaches `/projects/alpha/notes.md` with no row on
`/projects`. So vfs has already taken the "traversal is free" side.
The open question is only about *listing* and *stat* on the ancestors.
On those, Unix gives no single answer. It leaves them to the owner's
bits.

## 3. Plan 9: the same split, stated more cleanly

### 3.1 Walk is execute, listing is read, stat is free

- `intro(5)`: "A walk in a directory is regarded as executing the
  directory, not reading it" (`plan9:sys/man/5/0intro:563-566`).
- `walk(5)`: for each element, "the implied user of the request must
  have permission to search the directory"
  (`plan9:sys/man/5/walk:86-92`). If the first element fails, the reply
  is an error. If a later one fails, the reply lists the qids that
  succeeded (`:96-110`). So the client learns how far it got, but only
  through directories it was allowed to search.
- `read(5)`: reading a directory returns its entries
  (`plan9:sys/man/5/read:57-64`). To read, you must open for read, and
  that checks read permission (fossil `9p.c:709`; lib9p
  `srv.c:376-397`).
- `stat(5)`: "The stat request requires no special permissions"
  (`plan9:sys/man/5/stat:185`). As in Unix, once you can walk to a
  directory, its metadata is yours.

### 3.2 The file servers check before they look

- **fossil**: `rwalk` checks `PermX` on the directory first, then calls
  `fileWalk` for the name (`plan9:sys/src/cmd/fossil/9p.c:854-863`). A
  denied walk returns "permission denied" (`:15`) whether or not the
  name exists. A missing name under a searchable directory returns
  "file does not exist" (`sys/src/cmd/fossil/error.c:26`). `..` is
  always walkable "so that you can't walk into a directory and then
  not be able to walk out of it" (`9p.c:844-849`).
- **cwfs**: `walkname` checks `DEXEC` and returns `Eaccess` before it
  scans the directory (`plan9:sys/src/cmd/cwfs/9p2.c:430-436`). The
  strings are "access permission denied" and "directory entry not
  found" (`sys/src/cmd/cwfs/data.c:12-13`).
- **kfs**: the same check in the same place
  (`plan9:sys/src/cmd/disk/kfs/9p2.c:391-397`; strings at `dat.c:59-60`).

This is the Unix order: check the right on the directory, then look up
the name. So "denied" never depends on whether the name exists.

### 3.3 Where Plan 9 does not check at all

- **Kernel devices**: `devwalk` checks no permission
  (`plan9:sys/src/9/port/dev.c:169-262`). `devpermcheck` runs only at
  open (`:339-355`, called from `devopen` at `:371`).
- **lib9p in-memory trees**: `filewalk` walks with no permission check
  (`plan9:sys/src/lib9p/srv.c:109-130`). `hasperm` is called at open
  and create only (`srv.c:396-403`; same in
  `plan9port:src/lib9p/srv.c:401-407`).

So in half of Plan 9, traversal is simply free, as on Windows by
default (§4.1).

### 3.4 What Plan 9 changed from Unix

Two things are new. Neither changes the split.

1. **Traversal is a smaller right than reading, on purpose.** The
   `noworld` group has "attenuated access privileges": world bits are
   masked off, "except when walking directories"
   (`plan9:sys/man/4/cwfs:131-141`). fossil implements it: world
   execute on a *directory* is honoured even for `noworld` users,
   while every other world bit is not
   (`plan9:sys/src/cmd/fossil/9p.c:49-57`). So Plan 9 lets even its
   sandboxed users traverse, and nothing more.
2. **Hiding is a separate layer, and it keeps ancestors on purpose.**
   `exportfs -P` runs the filter before it stats, so a filtered name
   answers "does not exist" whether or not it is there
   (`plan9:sys/src/cmd/exportfs/exportfs.c:627-630`). It checks *every
   path component* against the pattern
   (`sys/src/cmd/exportfs/pattern.c:72-97`), and it trims directory
   listings to admitted entries (`pattern.c:126-131`). The consequence
   matters here. To export something deep, the pattern must also admit
   each ancestor, or the walk stops at the first one. Once admitted,
   an ancestor lists only the admitted children. That is option (b),
   but written by hand in the pattern file.

Plan 9's other answer to "share something deep" is the name space:
`bind` the deep directory into the other user's name space under a new
name. Then there are no ancestors to show. That is the Google Drive
shape (§4.3).

Running Plan 9 code was not attempted. Every claim in this section is a
reading of source and manual pages.

## 4. Modern precedents

### 4.1 Windows: traversal is free by default; listing is not

- "Bypass traverse checking" (`SeChangeNotifyPrivilege`) is held by
  Everyone by default. It lets a user "navigate an object path ...
  without being checked for the Traverse Folder special access
  permission. This user right doesn't allow the user to list the
  contents of a folder."
  <https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/security-policy-settings/bypass-traverse-checking>
- Russinovich: with it, "NTFS only checks the permissions on the
  directory or file you open, not on any parent directories"; the
  reason for the default is performance.
  <https://learn.microsoft.com/en-us/archive/blogs/markrussinovich/the-bypass-traverse-checking-or-is-it-the-change-notify-privilege>
- **Access-based enumeration (ABE)**: "If a user does not have Read (or
  equivalent) permissions for a folder, Windows hides the folder from
  the user's view." On a share of home directories, "users ... can see
  only their personal home directories; other users' folders are
  hidden." <https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2008-R2-and-2008/dd772681(v=ws.10)>
  Microsoft's own advice on the traverse page is to use ABE "when you
  want to prevent users from seeing any folder or file to which they
  don't have access."

Put the two defaults together and you get option (a). Alice reaches
`\\share\projects\alpha` by its full path, because traversal is free.
ABE hides `projects` from the share root, because she holds no read on
it. Listing `projects` directly is refused. To make the road visible,
the administrator must grant a list right on each ancestor by hand.
ABE then trims those listings to what she can open. That hand-made
recipe is option (b).

### 4.2 SharePoint: the road is granted automatically

SharePoint does that recipe for you. Limited Access "is designed to be
combined with fine-grained permissions to enable users to access a
specific list, document library, folder, list item, or document,
without enabling them to access the whole site. Limited Access can't be
edited or deleted." It contains Open ("open a website, list, or folder
to access items inside that container"), View Application Pages,
Browse User Information, Use Remote Interfaces and Use Client
Integration Features. It does **not** contain View Items.
<https://learn.microsoft.com/en-us/sharepoint/sites/user-permissions-and-permission-levels>

SharePoint assigns it to the parent containers on its own when an item
is shared with someone who has no access to the parent, "to give users
a route to the one item you shared with them"
(<https://o365reports.com/limited-access-in-sharepoint-online/>;
<https://www.syskit.com/blog/sharepoint-permission-inheritance>).
Limited-access lockdown mode, on by default for publishing sites,
strips it further so those users cannot open application pages
(<https://learn.microsoft.com/en-us/sharepoint/understanding-permission-levels>).
In Unix terms: an automatic `x` on every ancestor, and no `r`.

### 4.3 Google Drive: re-root instead of showing the road

A folder shared with you appears in "Shared with me" once you open it
from the invitation or link
(<https://support.google.com/drive/answer/7166529>). It is presented at
a new root, with no parent chain. I found no Google document that
states what a recipient sees of the owner's parent folders. Community
threads and third-party guides say the parents are not shown, but
treat that as reported, not documented.

Drive's *downward* rule is documented, and it is worth knowing. When a
folder has limited access, people who hold only the parent "can see
the restricted folder in Drive but can't open it"
(<https://developers.google.com/workspace/drive/api/guides/limited-expansive-access>).
So Drive shows a bare name without content. It does this in the other
direction from option (b).

### 4.4 S3 / IAM: listing is a separate, prefix-scoped grant

S3 has no directories, only keys, and listing is its own action,
`s3:ListBucket`, which can be scoped with an `s3:prefix` condition.
AWS's own walkthrough gives Alice `Development/*` and then, so that
the console can navigate, a separate statement allowing `ListBucket`
with `s3:prefix = ""` at the bucket root. At the root the console then
shows `Development/`, `Finance/` and `Private/`. That is a full sibling
listing, granted by hand.
<https://docs.aws.amazon.com/AmazonS3/latest/userguide/walkthrough1.html>
So S3 takes the most leaky shape, and only when an administrator
writes it.

### 4.5 NFSv4 ACLs: the split, in the protocol

RFC 8881 §6.2.1.3.1 defines `ACE4_LIST_DIRECTORY` ("Permission to list
the contents of a directory", operation `READDIR`) and, for a
directory, `ACE4_EXECUTE` ("Permission to traverse/search a directory",
operation `LOOKUP`) as separate mask bits.
<https://www.rfc-editor.org/rfc/rfc8881.html> Nothing is inherited
upward.

### 4.6 mirage: the direct competitor chose option (b)

mirage's `path_visible` is the whole composition rule for its
hide/show profiles. Its third step: "a hidden directory stays visible
when a visible show anchors strictly below it, so the road to a
carve-out exists (`hide /repo` + `show /repo/public` keeps `/repo`
listable, holding only the carve-out)"
(`mirage@e01d62a:python/mirage/utils/hidden.py:241-282`). A test pins
it: `/repo` allowed, `/repo/public/index.html` allowed,
`/repo/secrets` refused
(`python/tests/context/test_session_context.py:386-393`).

mirage also chose how refusals read. A create under a hidden directory
answers ENOENT, "the answer every read gives for that directory, so
probing creates cannot map a profile's hidden prefixes." A hidden name
under a visible parent answers EACCES (`:396-401`).

### 4.7 The precedents side by side

| System | Reach deep with no right above? | Ancestor listing | Ancestor metadata | Who makes the road |
|---|---|---|---|---|
| Unix, `0755` convention | yes (world `x`) | full, siblings shown | yes | owner's bits |
| Unix, `0711` idiom | yes | refused (EACCES) | yes, and names are probeable | owner's bits |
| Plan 9 disk servers | needs `x`, like Unix | needs `r` | yes (stat is free) | owner's bits |
| Plan 9 devices, lib9p | yes, walk is unchecked | needs `r` at open | yes | nobody; always open |
| Plan 9 `exportfs -P` | only if the pattern admits every ancestor | trimmed to admitted names | yes | the pattern author, by hand |
| Windows default + ABE | yes (bypass traverse) | ancestor hidden (no read) | no | admin, by hand |
| Windows + list-on-ancestors + ABE | yes | trimmed to what you can open | partial | admin, by hand |
| SharePoint | yes (Limited Access) | not View Items | no | **automatic** |
| Google Drive | yes | not shown; re-rooted | no | n/a (re-root) |
| S3 walkthrough | yes | full sibling listing | n/a | admin, by hand |
| NFSv4 ACL | needs `EXECUTE` | needs `LIST_DIRECTORY` | yes | owner, by hand |
| mirage | yes | **trimmed to the road** | not studied | **automatic** |

## 5. Mapping to vfs

### 5.1 The fact that makes this easy

Every path vfs hands Alice already names its ancestors.
`/projects/alpha/notes.md` contains the string `/projects`. vfs has no
implicit parents (ADR 003), so a visible row's parent directories exist
as rows. So under **either** option, Alice already knows that `/` holds
`projects` and that `/projects` holds `alpha`. She learns it from any
`glob`, `grep` or `glean` result.

This means one thing. **Showing an ancestor as a bare name reveals
nothing new, if and only if the ancestor is on the path to a row Alice
can already see.** The two options carry the same information. They
differ in discoverability and in consistency, not in secrecy.

That holds only under three conditions. Each one comes from a leak the
Unix repro measured.

1. **Names only, no metadata.** Unix's search-only caller saw the link
   count, size and mtime of the ancestor move when a hidden sibling
   appeared (§2.1). vfs has the same channel. A namespace change bumps
   the parent's `version`
   (`src/vfs/storage/backends/database/topology.py:986-988`, called at
   `:267`, `:387`, `:712`). `updated_at`, `version`, `size_bytes`,
   `owner_id` and any child count on a traverse-only ancestor must not
   be shown.
2. **No probing.** Unix's `0711` lets a caller confirm a guessed
   sibling (§2.1, item 4). In vfs, `stat /projects/beta` must answer
   not-found, the same as `/projects/nope`. That is already true under
   ADR 065. Option (b) must not weaken it.
3. **The road comes from visible rows, not from grant prefixes.** If
   the road were computed from grant prefixes, a grant on
   `/projects/alpha` made before `alpha` exists would show `/projects`.
   Alice would learn that `/projects` exists, which no visible row
   told her. Rule: *an ancestor is traversable iff it is an ancestor of
   a row the caller (or the session's subject set) can see.* The owner
   floor counts: a row Alice owns makes its ancestors traversable.

### 5.2 Verb by verb

Setup: posture `private`. Rows `/projects/`, `/projects/alpha/`,
`/projects/alpha/notes.md`, `/projects/beta/`,
`/projects/beta/secret.md`. Alice holds `read` on `/projects/alpha`.
The third column is option (b) with the three conditions above; call
it (b′).

| Alice calls | (a) strict, as written | (b′) traverse, road from visible rows | Unix, `0711` ancestors (for reference) |
|---|---|---|---|
| `ls /` | empty (the mount root is structure) | `projects/` | EACCES |
| `ls /projects` | not-found | `alpha/` only | EACCES |
| `stat /projects` | not-found | directory, path and kind only | ok, full metadata |
| `stat /projects/beta` | not-found | not-found | ok (probe works) |
| `stat /projects/nope` | not-found | not-found | ENOENT |
| `read /projects` | not-found | the ordinary "is a directory" answer | EISDIR |
| `tree /` | the alpha subtree has no visible parent: orphaned or empty | `/ → projects → alpha → notes.md` | `find` stops at `/` |
| `glob /*` | nothing | `/projects` | nothing, silently |
| `glob /**/*.md` | `/projects/alpha/notes.md` (names the ancestor anyway) | same | nothing, silently |
| `grep`, `glean` | alpha rows only | alpha rows only; ancestors have no content and add nothing to statistics | n/a |
| `versions`, edges, `locate` on `/projects` | not-found | not-found: traverse is not read | n/a |
| `write /projects/alpha/x.md` (read-only grant) | permission_denied | permission_denied | EACCES |
| `mkdir /projects/gamma` | not-found (parent hidden) | permission_denied, decided on the parent before the name is looked up | EACCES |
| `mkdir /projects/alpha/x/y`, `parents=True` (with `read_write`) | must skip the hidden, existing `/projects` silently, never reporting it as created or as existing | ancestors are visible directories; `exist_ok` behaves normally | ok |

Three rows deserve a sentence each.

- **`mkdir /projects/gamma` under (b′).** The answer must not depend on
  whether `gamma` exists hidden. Unix gets this by checking the
  directory's right before it looks up the name (§2.2; fossil and cwfs
  do the same, §3.2). vfs should do the same: a traverse-only parent
  refuses every create as `permission_denied`, decided before any
  lookup. mirage answers EACCES here for the same reason (§4.6).
- **`tree /` under (a).** The only visible subtree hangs from a hidden
  parent. The tree builder must either drop it or print a subtree
  with no root. Both are awkward, and both still print `/projects` in
  the paths.
- **`mkdir -p` under (a).** Creating parents means asking "does
  `/projects` exist?" Under (a) the honest answers are "yes", which is
  a leak, or "not found", which is false. The implementation has to
  special-case it. Under (b′) the question has a true answer that
  leaks nothing.

### 5.3 What each option leaks, precisely

- **(a) strict**: leaks nothing beyond the visible set. Its cost is
  discoverability: an agent that starts with `ls /` finds nothing and
  must be told the path. It is also inconsistent: `glob` and `grep`
  results print ancestor names that `ls` and `stat` deny exist.
- **(b) as first posed, "ancestors of a covering prefix"**: leaks
  whether an ancestor exists when the grant's own root does not exist
  yet (condition 3).
- **(b′), "ancestors of a visible row", names only**: leaks nothing
  beyond the visible set. This is stricter than Unix `0711` (no
  metadata, no probing) and stricter than S3's walkthrough (no
  siblings).
- **Under the default `open` posture none of this arises.** Every
  subject holds `read_write` at `/`, so no ancestor is ever hidden. The
  question exists only under `shared` or `private` postures, or below a
  nested private prefix.

For a subject set (ADR 066), the road is computed from the session's
visible set, the meet, never from one member's.

## 6. Verdict and recommendation

**Is there a clear precedent? Partly yes, and partly no.**

- **Yes: traverse, list and read are three separate rights.** Every
  system studied separates them: Unix, Plan 9, NFSv4, Windows,
  SharePoint, S3. vfs should keep them separate. An ancestor on the
  road gets traverse only. It never gets read, so no content, no
  metadata, no versions, no edges and no statistics.
- **Yes: the check comes before the lookup.** V6, V7, Linux, FreeBSD,
  fossil, cwfs, kfs and `exportfs` all decide "may you go here?" before
  asking "is it here?" That is why a refusal never depends on
  existence. vfs should decide a write under a traverse-only ancestor
  the same way.
- **Yes: reaching a deep path needs no right on its ancestors.** This
  is Windows by default, SharePoint by automation, and Plan 9's
  devices and lib9p trees. vfs's prefix coverage already does it.
- **No: on listing an ancestor, the field splits.** The operating
  systems (Unix, Plan 9, Windows, NFSv4) and S3 never grant listing
  upward automatically. They leave the road to an administrator: a
  `chmod`, a "list this folder only" entry plus ABE, an `exportfs`
  pattern, an S3 prefix statement. The sharing products that care
  about navigation (SharePoint, mirage) grant the road automatically.
  When a listing is shown in a system that hides things, it is
  trimmed to what the caller may open (ABE, `exportfs -P`, mirage).
  No precedent picks between (a) and (b) for us.

**Recommendation: option (b′).** The precedent does not decide it, so
decide on vfs's own terms:

1. It leaks nothing that (a) does not (§5.1).
2. Agents are a first-class audience, and agents discover by `ls /` and
   `tree /`. (a) gives them an empty root.
3. It removes two awkward special cases in (a): `tree` orphans and
   `mkdir -p` over a hidden parent.
4. It matches the hiding family vfs already joined in ADR 065: hidden
   entries are absent, and listings are trimmed, not refused (ABE,
   `exportfs -P`, mirage).
5. It follows every part of the precedent that *is* clear: traverse
   is separate from read, and the check comes before the lookup.

Stated as a rule for spec 058: *a directory that is an ancestor of a
row the authority can see is traversable. A traversable directory
appears in listings, `glob` and `tree` as a bare name. Listing it shows
only its visible or traversable children. `stat` on it returns path and
kind only. `read` on it gives the answer any directory gives. Its
versions, edges and `locate` answer not-found. Every write under
it answers `permission_denied`, decided on the directory before the
target name is looked up.*

How to compute the road at a 10k batch is a spec question, not a
research one. Two notes for whoever writes it. The resolver's arm
prefixes give the road cheaply, in app code, but only if each arm's
root row is checked to exist (condition 3). And owner-floor rows can
sit under any directory, so they need their own bounded `EXISTS`.

If Clay prefers (a), it stays safe. Because the two options carry the
same information, switching later needs no security review. It changes
only what `ls`, `stat`, `tree` and `glob` show.

## 7. What was not verified

- Linux was read at `faeab166` (2026-04-18), not at today's upstream
  head (see Sources). The rule itself is 50 years old and was also
  executed on a 7.0 kernel today, so drift is unlikely to matter. Line
  numbers may have moved.
- Plan 9 code was read, not run.
- SharePoint's exact rendering of a library for a Limited Access user
  (with and without lockdown mode) was not tested. The documented
  intent is a route to the item, and Limited Access lacks View Items.
- Google Drive's upward behavior is reported by users, not documented
  by Google.
- mirage was read for its composition rule. How mirage renders
  metadata on a road directory was not studied.
- Windows was not run; its behavior is taken from Microsoft's
  documentation.

## One-line version

Unix and Plan 9 always keep "go through", "list" and "read" apart, and
always check before they look. Nobody auto-grants listing upward except
the sharing products (SharePoint, mirage). So there is no clear
precedent for (a) versus (b). Since showing the road leaks nothing that
vfs's own result paths do not already print, show ancestors of visible
rows as bare names, with no metadata and no probing (option b′).
