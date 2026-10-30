# Study 02: Files and directories, the API (OSTEP chapter 39)

- **Date:** 2026-10-24
- **Brief:** `00-brief.md` in this folder.
- **Source:** OSTEP v1.10, chapter 39, *Interlude: Files and Directories* (PDF pages 506 to 534). Page numbers below are the chapter's own printed page numbers, 1 to 29. Chapter page N is PDF page 505 + N. Every idea from the book is paraphrased; nothing is quoted.
- **vfs at:** `main`, HEAD `ac5c515`.
- **Labels:** **READ** (the book or a vfs file), **EXECUTED** (ran here with `uv run`), **INFERRED** (my reasoning).
- **The probe:** one script, run with `uv run python` against `InMemoryStorage` through `VirtualFileSystem`. It wrote a file, tried the write-temp-then-rename idiom, rewrote a file, stat'ed it, deleted a non-empty directory without cascade, moved a directory into itself, wrote a body at a directory path, and listed a directory. Its results are cited as EXECUTED below. The script was scratch and is not kept in the repo.
- **The six asked questions, where answered:** (a) atomic rename: principle 6. (b) fsync and durability: principle 7. (c) file descriptors: principles 8 and 9. (d) low-level name vs path: principles 1 and 2. (e) directory format: principles 3 and 4. (f) links and permission bits: principles 13, 14 and 15.

---

## 1. What the chapter says

Chapter 39 is the API chapter for persistent storage. It comes before the chapters on how a file system is built. Its question: how should an OS manage a device that keeps data after power loss, and what interface should programs see (p. 1).

It names two abstractions (p. 1 to 2). A **file** is a linear array of bytes. It also has a **low-level name**, a number the user rarely sees, called the **inode number**. A **directory** also has an inode number. Its content is a list of pairs: a human-readable name and the low-level name it maps to. Directories inside directories make a **directory tree**, rooted at `/`. The file system does not care what a file contains. A suffix like `.c` is a naming convention, not a rule (p. 2 to 3).

Then it walks the calls (p. 3 to 18). `open` returns a **file descriptor**: a small per-process integer that works as a capability (a token that grants the power to act) (p. 4). The descriptor points into a system-wide **open file table**. Each entry there holds the **current offset** (where the next read or write starts) (p. 7 to 9). `lseek` moves that offset; it does no disk I/O (p. 8). `fork` and `dup` can share one table entry, so two descriptors share one offset (p. 9 to 11). `write` usually lands in memory first; `fsync` forces it to the device, and a new file also needs its directory synced (p. 12). `rename` is atomic with respect to crashes. That gives the standard safe-update idiom: write a temp file, fsync it, rename it over the old name (p. 14). `stat` returns **metadata** (size, inode number, owner, times, link count) kept in the **inode** (p. 14 to 15). `unlink` removes a name (p. 15 to 16). Nobody writes a directory directly; the file system owns its format, and you change it only by creating or removing things inside it (p. 16). Every directory holds `.` and `..` (p. 16). `readdir` returns only names and inode numbers, so `ls -l` calls `stat` on each one (p. 17 to 18). `rmdir` refuses a non-empty directory (p. 18).

The rest is naming and sharing (p. 18 to 27). A **hard link** is a second name for the same inode. The inode keeps a **link count**; a file is truly deleted only when the last name goes (p. 18 to 20). Hard links cannot point at directories (cycles) or cross file systems (inode numbers are local) (p. 20). A **symbolic link** is a small file whose body is a path. It can dangle when its target goes (p. 20 to 22). **Permission bits** give read, write and execute to owner, group and everyone else; `chmod` changes them (p. 22 to 23). The execute bit on a directory means you may enter it (p. 23). A **superuser** can do anything, which is itself a risk (p. 23). **Access control lists** (AFS keeps one per directory) are finer than bits (p. 23 to 24). A side note warns of **TOCTTOU** (time of check to time of use): a gap between checking a file and using it lets an attacker swap the file, often with a rename or a symlink. The book says a transactional file system would cure it, but few exist (p. 25). Last, `mkfs` writes an empty file system onto a device, and `mount` grafts it onto an existing directory so many file systems form one tree (p. 24 to 26).

---

## 2. Principles vfs should adopt

Each item: the principle, where it comes from, where vfs stands, and the one concrete change it implies (if any).

### 1. A file has two names: a permanent low-level name and a human path.

- **Book:** p. 1 to 2; the key-terms box on p. 27. **READ.**
- **vfs today: follows it in storage, hides it at the API.**
  - The entries table has `entry_id` (a ULID, a sortable 128-bit id), minted once and never reused. That is the inode number. `src/vfs/models/rows.py` lines 427 to 431. **READ.**
  - `UNIQUE(parent_id, name)` (line 482) is the directory's (name, low-level name) pair, exactly the chapter's shape. **READ.**
  - `path` is a cache that can be rebuilt from `parent_id` + `name` (ADR 004 pin 3; ADR 019). **READ.**
  - A rename keeps the `entry_id`. A delete-then-recreate at the same path mints a new one (ADR 004 pin 1). **READ.**
  - But no caller can see the id. `Observation` has no id field (`src/vfs/models/entry.py` lines 424 to 440), and `Entry` says path is its only identity (same file, class docstring). **READ.**
- **So:** the chapter's `stat` reports the inode number for a reason. It lets a tool tell two cases apart. Case one: the same file moved here. Case two: a new file reused the name. vfs keeps that fact and throws it away at the edge. **INFERRED.**
- **Change:** expose `entry_id` as a read-only, projectable column on `stat`/`ls` rows. Add no verb that takes it as an address. Rights, routing and every verb stay keyed by path. **INFERRED.**

### 2. Decide where rights live: on the low-level name, or on the place.

- **Book:** Unix keeps permission bits in the inode, so a rename does not change who may read a file (p. 14 to 15, p. 22). AFS keeps an ACL per directory, so rights come from where a file sits (p. 23 to 24). **READ.**
- **vfs today: follows AFS, on purpose.** Grants attach to path prefixes (ADR 021 decision 2; ADR 072). The everyone level is a column on the row, rewritten when a row moves (ADR 073 decision 1). The owner (`owner_id`) does sit on the row and travels with it (`rows.py` line 471). **READ.**
- **So:** in vfs, `move` can change who may read a file. In Unix, `mv` cannot. Both are lawful designs; the chapter shows both. vfs has the AFS one, and it is the only one compatible with rights compiled into the search query (ADRs 067, 072). **INFERRED.**
- **Change:** none to the model. Say it plainly in the `move` docstring and the user docs: a move takes on the destination's rights. **INFERRED.**

### 3. Nobody writes a directory directly; the file system owns it.

- **Book:** p. 16. **READ.**
- **vfs today: follows it, and goes further.** A directory has no body at all. `Entry` refuses content with an explicit directory kind (`entry.py`, `_derive_identity`). **READ.** A `write` with content at an existing directory path returns `wrong_kind`. **EXECUTED.** There is no directory file and no on-disk directory format. The children of a directory are the answer to `WHERE parent_id = X` (ADR 004 amendments; `rows.py` line 482). **READ.** Creating a child bumps the parent's version, which plays the part of a directory's modification time (`writes.py` module docstring). **READ.**
- **Note on `.` and `..`:** vfs never lists them (`ls` of a directory returned only its child; **EXECUTED**). The path gate removes them by text: `Path("/a/../b") == "/b"` (`paths.py`, `Path` docstring). **READ.** Text-only `..` is correct only because there are no symlinks (see principle 14). **INFERRED.**
- **Change:** none.

### 4. A listing is cheap names; details are a second step.

- **Book:** `readdir` gives a name and an inode number. `ls -l` then calls `stat` once per entry (p. 17 to 18). **READ.**
- **vfs today: better than the book on the second step, worse on the first.** `ls` returns the stat columns (kind, size, version, times, hash, mime type) in the same rows. **EXECUTED** (the `populated` mask of the `ls` row). No per-entry `stat` is needed. But `ls` has no cursor: a 10,000-child directory comes back whole, in one answer (yesterday's memo §2, study S05, **READ**).
- **Change:** the listing cursor yesterday's memo already names (§4.2, step 2). The chapter adds a reason: its `readdir` is a loop that reads one entry at a time, so a directory listing is stateful iteration by design (p. 17). vfs should keep that iteration out of the kernel and pass a resume key instead. **INFERRED.**

### 5. Removing a whole tree must be deliberate.

- **Book:** `rmdir` refuses a non-empty directory (p. 18). Powerful commands like `rm -rf` can destroy a lot with few keystrokes (p. 17). **READ.**
- **vfs today: half follows, with a different safety net.** `delete` defaults to `cascade=True` (`src/vfs/base.py`, `delete` signature). **READ.** `cascade=False` on a non-empty directory returns `not_empty`, the `rmdir` rule. **EXECUTED.** The net is reversibility instead of refusal. A delete is a tombstone (a marker that hides the row but keeps it); `restore` brings it back; only `sweep` destroys, and `sweep` is never offered to agents (ADRs 027, 074). **READ.**
- **Change:** none in the kernel. A POSIX-shaped front's `rmdir` should map to `cascade=False`, as yesterday's memo proposes (§4.2). **INFERRED.**

### 6. Make an update atomic, so a crash leaves old or new, never half.

This is question (a).

- **Book:** `rename` is (usually) atomic under a crash. The safe-update idiom is: write a temp file, `fsync` it, `close` it, then `rename` it over the real name (p. 14). **READ.**
- **vfs today: the goal is met without the idiom.**
  - Every verb is one database transaction. The backend method owns it (`writes.py` module docstring; `protocol.py` module docstring). **READ.**
  - A `write` over an existing file replaces the body in that transaction. The old body is kept as a version. The version went from 1 to 2 on a rewrite. **EXECUTED.**
  - A batch is all or nothing. A failed plan runs no mutation statement at all, at any size, including 10,000 entries (`writes.py` docstring). **READ.** That is stronger than `rename`: the book's idiom makes one file atomic; a vfs batch makes many files atomic together. **INFERRED.**
  - `move` keeps the `entry_id` and rewrites only the path cache (ADR 004 consequences; `topology.py` docstring). **READ.**
- **But the idiom itself fails today.** Write `/a.txt.tmp`, then `move("/a.txt.tmp", "/a.txt")` over an existing `/a.txt`: the move returns `exists`. **EXECUTED.** That is decided: an occupied destination always refuses (ADR 027 amendment, spec 101). **READ.**
- **Why it matters:** POSIX-shaped programs use the idiom everywhere. Python's own atomic-save pattern is temp file plus `os.replace`. A WASI Python guest will issue it as a rename over an existing name. **INFERRED.**
- **Change:** spec 167's `move(..., overwrite=True)` (spec 167 decision 7; **READ**) must serve the WASI front's rename too, not only the shell's `mv`. And it must decide one thing the chapter makes visible: **whose identity survives?** In POSIX the name ends up on the *source's* inode, and the old inode loses a link (p. 14, p. 19 to 20). Spec 167 keeps the replaced body as a version, which reads as the *target's* history continuing. Pick one on purpose, and say what happens to edges that pointed at the losing `entry_id`. **INFERRED.**

### 7. Written and durable are different promises; say which one you give.

This is question (b).

- **Book:** a `write` normally sits in memory for seconds. `fsync` forces it to the device. A new file also needs its directory synced, a step programs often forget (p. 12). Doing this well and fast is hard (p. 27). **READ.**
- **vfs today: one promise, mostly honest.**
  - The kernel buffers nothing. A verb returns after its transaction commits. On a tuned SQL engine, commit is the fsync. **INFERRED** from the transaction ownership above.
  - The directory entry (the `(parent_id, name)` row) and the body commit in the same transaction. So the chapter's forgotten second sync (the directory) cannot be forgotten. **INFERRED.**
  - SQLite runs with `synchronous = FULL` and WAL (`dialects.py` lines 399 and 407). **READ.**
  - The storage declares a `durability` trait, `full` or `relaxed` (`protocol.py` lines 74 to 84). Tuned profiles claim `full` (`backend.py` lines 297 to 300). **READ.**
- **The gap:** `InMemoryStorage` is SQLite `:memory:`, and it declares `durability: full`. **EXECUTED.** A memory database survives no crash. The trait is read off the profile's name, not off the live connection. The same is true on Postgres: nothing reads the server's `synchronous_commit` setting (no match for it in `src/vfs`). **READ.**
- **Where fsync does belong:** in the fronts that buffer. The WASI front stages a file whole at open and hands it back at close or `fsync` (the WASI memo, line 60). **READ.** There, the chapter's model applies word for word: until write-back, the data is not in vfs. **INFERRED.**
- **Change:** derive the `durability` trait from the live connection. A `:memory:` database must not claim `full`. This is CLAUDE.md's own rule: read engine facts off the live object. **INFERRED.**

### 8. A file descriptor is a per-process capability; keep it out of the kernel.

This is question (c).

- **Book:** a descriptor is a small integer, private to one process. The OS hands it out after a permission check at `open`, and it then works as a capability (p. 4, p. 27). It indexes a per-process array that points into the shared open file table (p. 4, p. 7). **READ.**
- **vfs today: follows yesterday's memo.** No verb opens, closes or holds anything. The seam has no handle, offset or cursor (yesterday's memo §2, S05 fact 2). Handles live in the fronts: the WASI provider keeps its own table (memo §4.2, §4.4). **READ.**
- **The chapter adds a reason the memo did not give.** A descriptor is checked **once**, at `open`. After that, it carries the right with it. vfs judges rights on **every** call (ADR 084 pin 2: the `read` is issued on every run, a cache hit included; ADR 067: rights compile into each statement). **READ.** A kernel handle would bring back the check-once model, and with it the lag where a revoked right still works through an open handle. **INFERRED.**
- **Change:** when the kernel ADR is written, add one rule: **a front's handle carries a path and an offset, never a right.** Every kernel call the handle makes is gated fresh. **INFERRED.**

### 9. A position inside a file belongs to the caller, not to the file.

- **Book:** the current offset lives in the open file table entry, one per `open` (p. 7 to 9). `lseek` only changes that number (p. 8). `fork` and `dup` can share one offset between two descriptors (p. 9 to 11). The book's own example of random access is reading from an index at chosen offsets (p. 7). **READ.**
- **vfs today: has no offset at all.** `read` returns the whole body (memo §2). Inside a file, vfs addresses text by content and line: `edit` matches an old string (`base.py`, `edit`), and search matches report regions. **READ.**
- **Change:** a per-call byte range on `read`, as yesterday's memo proposes (§4.2, step 4). That is `pread` (a read at an explicit offset), not `lseek`. The offset stays in the caller. **INFERRED.**

### 10. Check and act in one step, or an attacker lives in the gap.

- **Book:** TOCTTOU. A service checks a file, then uses it. Between the two, someone swaps the file (with a rename or a symlink). The cure the book names is a transactional file system (p. 25). **READ.**
- **vfs today: is that transactional file system, inside the kernel.** Backends check and act in one call, because a separate check would race (ADR 011, scope rule). Writes plan against a snapshot and every update is guarded on what it judged; a miss redrives the whole verb (`writes.py` and `topology.py` docstrings). **READ.**
- **The gap reopens above the kernel.** Spec 167's `>>` is a `read` then a `write` with no version check. The spec says concurrent appends can lose data (spec 167, Redirections). **READ.** The WASI front reads at open and writes back at close. The WASI memo names no version check on that write-back. **READ.** Both are the chapter's check-then-use gap, as a lost update. **INFERRED.**
- **Change:** `write(if_version=...)`, the open question on write preconditions on the wire (`context/open-questions.md`) and yesterday's memo step 3. Both fronts above should use it. **INFERRED.**

### 11. Name everything through one tree.

- **Book:** Unix names devices, pipes and even processes as files. One naming scheme keeps the model simple (p. 3). `/proc` and `tmpfs` sit in the same tree (p. 26). **READ.**
- **vfs today: half follows, on purpose.** Trash, mount metadata, the program and skill views, and run outputs are paths under `/.vfs` (`paths.py` docstring; ADR 082). **READ.** Versions, chunks and edges are not: they are addressed by owning file plus a key, never by a path (`paths.py` docstring; ADR 016). **READ.**
- **Change:** none now. Yesterday's memo already names a future `history(path)` read (§4.3). **INFERRED.**

### 12. Build a file system empty, then graft it onto an existing directory.

- **Book:** `mkfs` writes an empty file system with a root. `mount` pastes it at an existing directory. `mount` with no arguments lists what is mounted where (p. 24 to 26). **READ.**
- **vfs today: follows closely.** A database storage provisions its schema on first touch (`engine.py`; ADR 078 adds the lock row then). `bind` grafts storage onto an existing empty directory, the Linux `graft_tree` rule; mount points are plain stored directories (ADR 009; `base.py` module docstring). `mounts()` lists the table (`base.py`). A verb whose two paths sit in different mounts returns `cross_mount`, which is `EXDEV` (`results/kinds.py` line 80). **READ.**
- **Change:** none.

### 13. Hard links: keep refusing them.

This is half of question (f).

- **Book:** a hard link is a second directory entry for one inode. The inode counts its names; the data goes only when the count hits zero, which is why removal is called `unlink` (p. 18 to 20). Hard links cannot reach directories or other file systems (p. 20). **READ.**
- **vfs today: refuses them.** One path per entry is the grant coordinate (ADR 021 decision 2). The full-dirent end-state that would allow them is parked (`open-questions.md`, Full dirent model). **READ.**
- **Does the chapter give a reason to revisit? No.** **INFERRED**, for three reasons:
  1. The chapter's use case is two names for one file. vfs serves that with typed edges, which key on `entry_id` and so survive a move (ADR 004; ADR 018). **READ** (the keying).
  2. Under AFS-style rights (principle 2), a file with two paths has two answers to the question of who may read it. The chapter's Unix model avoids that only because it keeps rights on the inode.
  3. The link count exists to decide when to free data. vfs never frees on delete; only `sweep` destroys (ADR 027). The counter would have no job.
- **One thing the chapter does change:** its argument that links cannot cross file systems rests on inode numbers being local (p. 20). vfs ids are globally unique (ADR 004 pin 1). So the cross-mount refusal on edges (`base.py`, `mkedge` docstring) is a choice, not a necessity. **INFERRED.**
- **Change:** none.

### 14. Symbolic links: keep refusing them.

This is the other half of question (f).

- **Book:** a symlink is a third kind of file whose body is a path. It dangles when the target goes (p. 20 to 22). Symlinks are a main tool of TOCTTOU attacks; `O_NOFOLLOW` exists to refuse them (p. 25). **READ.**
- **vfs today: refuses them.** `ObjectKind` is only `file` or `directory` (`paths.py` line 37). **READ.**
- **The chapter gives three reasons to keep it that way.** **INFERRED.**
  1. Without symlinks, `..` can be resolved by text alone (principle 3). With them, it cannot.
  2. ADR 011 says path resolution is I/O-free, and that symlink-like things would force a re-decision of the router's shape. **READ.**
  3. The TOCTTOU attack in the chapter needs a symlink or a rename in the gap. vfs has no symlinks and no gap (principle 10).
- **And edges beat symlinks for agents:** a symlink names a path and breaks on a rename. An edge names an `entry_id` and follows the move. **INFERRED.**
- **Change:** none. A POSIX front must answer `symlink`, `link` and `readlink` with `unsupported` (`ENOTSUP`, `results/kinds.py` line 69). **INFERRED.**

### 15. Permission bits: have the concept, not the bits.

The last part of question (f).

- **Book:** read, write and execute, for owner, group and other; `chmod` sets them (p. 22 to 23). On a directory, execute means you may enter it (p. 23). ACLs are the finer tool (p. 23 to 24). A superuser can do anything and is a risk for that reason (p. 23). **READ.**
- **vfs today: has every concept, under its own names.** **READ** unless marked.

  | Book | vfs |
  |---|---|
  | owner (uid) | `owner_id` on the row (`rows.py` line 471) |
  | group (gid) | groups as memberships (ADR 071) |
  | other bits | `everyone_level` on the row (ADR 073) |
  | read / write bits | the ladder `none < list < read < add < contribute < read_write` (ADR 080 pin 1) |
  | directory execute bit | the `list` rung and the road rule (ADRs 070, 080 pin 2); **INFERRED** match |
  | file execute bit | none: running a program is `read` on it (ADR 084 pin 2) |
  | ACL | grant rows on path prefixes (ADRs 021, 072) |
  | superuser | the system actor bypasses grants (ADR 021 decision 4) |

- **Change:** none in the kernel. No `chmod`; rights change through `grant`, `revoke` and `posture`. ADR 082 pin 5 already refuses fake mode bits in `ls -la`. If a FUSE front ever needs `st_mode`, it should compute it from the caller's rung on that row, and label it as such. **INFERRED.**

---

## 3. Nouns and verbs

**Adopt name** = use the book's word. **Adopt concept** = keep vfs's own word. **Not have** = deliberately absent.

### Nouns

| Book | What it is | vfs today | Call | Reason |
|---|---|---|---|---|
| file | bytes with a low-level name (p. 1) | file entry (`kind="file"`) | adopt name | same idea; vfs also keeps text and bytes bodies |
| inode number, low-level name | permanent id (p. 1 to 2) | `entry_id` ULID, hidden | adopt concept, expose read-only | principle 1 |
| inode | per-file metadata record (p. 15) | the `entries` row | adopt concept | the row is the inode, plus the dirent |
| directory | list of (name, id) pairs (p. 2) | directory entry; children by `parent_id` | adopt name | principle 3 |
| directory entry (dirent) | one (name, id) pair (p. 18) | the `(parent_id, name)` unique key | adopt concept | no separate table (open question, parked) |
| directory tree, root | the hierarchy, `/` (p. 2) | the namespace, `ROOT` (`paths.py`) | adopt name | same |
| absolute pathname | full path from root (p. 2) | `Path` (branded, canonical) | adopt concept | every public path is absolute |
| `.` and `..` | self and parent entries (p. 16) | removed by text at the gate | not have as entries | no symlinks, so text is exact |
| current working directory | process's relative base (p. 3) | none in the kernel | not have | a front's concern (the shell's session) |
| file descriptor | per-process capability (p. 4) | none | not have in kernel | principle 8; fronts own it |
| open file table, `struct file` | shared offset, mode, refcount (p. 7 to 8) | none | not have in kernel | no open state in vfs |
| current offset | next read/write position (p. 7) | none | not have | ranges per call instead (principle 9) |
| stdin, stdout, stderr | descriptors 0, 1, 2 (p. 6) | the shell's streams (spec 167) | front only | a pipeline concept |
| metadata, `struct stat` | size, id, owner, times, links (p. 14 to 15) | `Observation` stat columns | adopt concept | see the stat row map below |
| link count | names per inode (p. 19) | none | not have | no hard links; delete never frees |
| hard link | second name for one inode (p. 18) | none | not have | principle 13 |
| symbolic link | file whose body is a path (p. 20) | none | not have | principle 14 |
| dangling reference | link to a gone target (p. 21) | an edge to a tombstoned row | adopt concept | edges are id-keyed and survive moves |
| permission bits | rwx for owner/group/other (p. 22) | the rung ladder | adopt concept | principle 15 |
| ACL | per-directory rights list (p. 23) | grant rows on path prefixes | adopt concept | AFS shape, principle 2 |
| superuser | bypasses all checks (p. 23) | system actor | adopt concept | named, and kept off the edge (ADR 068) |
| capability | a token that grants power (p. 4) | `Authority` | adopt concept | rights travel with the call, not a handle |
| file system (instance) | what `mkfs` makes (p. 24) | a storage backend | adopt concept | one database = one file system |
| mount point | directory where a file system is grafted (p. 25) | bind site, a stored directory | adopt name | ADR 009 |
| TOCTTOU | check-then-use race (p. 25) | none as a word | adopt name | it names the lost-update gap in principle 10 |

**The `stat` row map** (book field to vfs, p. 15):

| `struct stat` | vfs | Note |
|---|---|---|
| `st_ino` | `entry_id`, not on the row | principle 1 |
| `st_mode` (type) | `kind` | |
| `st_mode` (bits) | none on the row | rights are per caller; see principle 15 |
| `st_nlink` | none | no hard links |
| `st_uid` | `owner_id`, not on `Observation` | INFERRED: worth a projectable column too |
| `st_gid` | none | groups are subjects, not a file field |
| `st_size` | `size_bytes` | |
| `st_blocks`, `st_blksize` | none | rows, not blocks |
| `st_atime` | none | INFERRED: a read should not write |
| `st_mtime` | `updated_at` | |
| `st_ctime` | none | |
| (none in POSIX) | `created_at`, `version`, `content_hash`, `mime_type` | vfs is richer here |

### Verbs

| Book | What it does | vfs today | Call | Reason |
|---|---|---|---|---|
| `open` with `O_CREAT` | create a file (p. 3) | `write` | adopt concept | create is a write; `if_absent=` would be `O_EXCL` (memo §4.2) |
| `creat` | old create call (p. 4) | none | not have | `write` covers it |
| `O_TRUNC` | empty a file at open (p. 4) | `write` with an empty body | adopt concept | memo §4.2 |
| `open` (to read) | get a descriptor (p. 6) | none | not have in kernel | principle 8 |
| `read` | bytes at the offset (p. 6) | `read`, whole body | adopt name | add `range=` (principle 9) |
| `write` | bytes at the offset (p. 6) | `write`, whole body, mints a version | adopt name | add `if_version=` (principle 10) |
| `close` | drop the descriptor (p. 6) | none | not have in kernel | |
| `lseek` | move the offset (p. 7) | none | not have | offset belongs to the caller |
| `fork`, `dup` sharing | two descriptors, one offset (p. 9 to 11) | none | not have | no processes in the kernel |
| `fsync` | force data to the device (p. 12) | implicit: every verb commits | adopt concept | principle 7; fronts that buffer need it |
| `rename` | atomic new name (p. 12 to 14) | `move`, refuses an occupant | adopt concept | add `overwrite=` (principle 6) |
| `stat`, `fstat` | read metadata (p. 14) | `stat` | adopt name | |
| `unlink` | remove a name (p. 16) | `delete`, a tombstone | adopt concept | vfs never frees on delete |
| `mkdir` | make a directory (p. 16) | `mkdir` | adopt name | |
| `opendir`, `readdir`, `closedir` | iterate a directory (p. 17) | `ls`, whole | adopt concept | add a cursor (principle 4) |
| `rmdir` | remove an empty directory (p. 18) | `delete(cascade=False)` | adopt concept | a front may spell it `rmdir` |
| `rm -rf` | remove a tree (p. 17) | `delete` (default cascade) | adopt concept | safe because reversible |
| `link` (`ln`) | add a hard link (p. 18) | none | not have | principle 13 |
| `symlink` (`ln -s`) | add a symlink (p. 20) | none | not have | principle 14 |
| `chmod` | set mode bits (p. 22) | none | not have | `grant`, `revoke`, `posture` instead |
| `fs setacl` | edit an ACL (p. 24) | `grant`, `revoke` | adopt concept | |
| `mkfs` | make an empty file system (p. 24) | first-touch provisioning | adopt concept | |
| `mount` | graft at a directory (p. 25) | `bind`, `add_mount` | adopt concept | ADR 009 |
| `mount` (list) | show mounts (p. 26) | `mounts()` | adopt concept | |
| `strace` | trace a program's calls (p. 5) | none | not in kernel | version rows name the actor (ADR 064); tracing is a front's tool |

---

## 4. What does not transfer

- **A row is not a block.** The chapter's stat has block counts and block sizes (p. 15), and its `lseek` aside is about disk heads (p. 8). vfs stores whole rows. The cost to watch is statements and bind parameters, not seeks. **INFERRED.**
- **There is no page cache to flush.** The chapter's `write` is fast because it lands in memory and is flushed later (p. 12). vfs has no write-back layer in the kernel. The engine's commit is the flush. So `fsync` is not a verb; it is a property of every verb. **INFERRED.**
- **There are no processes.** Descriptors, the per-process array, `fork` and `dup` all assume a long-lived process (p. 4, p. 9 to 11). vfs's callers are agents over a stateless wire, CLI calls and ETL batches. A caller holds an `Authority`, not an open file. **INFERRED.**
- **Delete never frees.** The chapter's `unlink` frees the inode when the last name goes (p. 20). vfs's delete only hides the row; `sweep` is the one destroyer (ADR 027). So link counts and freeing logic have nothing to do. **READ** (ADR) and **INFERRED**.
- **The file system knows what is in the file.** The chapter says the file system does not care about file structure, and suffixes are convention (p. 2 to 3). vfs reads bodies to index, chunk, render and rank them. It even infers `kind` from the name when the caller omits it (`paths.py`, `parse_kind`). This is the deepest break, and it is vfs's reason to exist. **READ** and **INFERRED.**
- **Every caller sees a different tree.** In the chapter, all users see one tree; permissions refuse access but names still show (p. 22). In vfs, a hidden row is absent, and refusals never confirm that it exists (ADR 065). Only directories on the way to a visible row show, as bare names (ADR 070). **READ.**
- **Atomicity is not special to rename.** The chapter has to point out that one call, `rename`, is crash-atomic (p. 14). In vfs every verb, and every batch, is crash-atomic, because each is one transaction. **INFERRED.**
- **Ids are global, not per file system.** Inode numbers are unique only inside one file system (p. 20). `entry_id` is unique across mounts and survives dump and restore (ADR 004 pin 1). **READ.**
- **`mmap` has no analogue.** The persistent-memory aside maps file bytes into an address space (p. 13). A database row cannot be mapped into a guest's memory; a WASI guest stages a copy. **INFERRED.**

---

## 5. The one design lesson

The chapter splits a file system into a durable part (one permanent low-level name per file, in a directory of name-to-id pairs) and a per-process part (descriptors, offsets, buffered writes, `fsync`). vfs already has the durable part in its rows, and every verb is one committed, freshly gated transaction, so the per-process part belongs in the fronts, and a front's handle must never carry a right. What vfs should still take is three small things: show the low-level name on `stat`, let `move` replace so write-then-rename works, and make the `durability` claim match the live engine.
