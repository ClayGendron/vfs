# POSIX and Related Standards: What Applies to Grover/VFS

- **Date:** 2026-04-18
- **Author:** Human + AI (research synthesis)
- **Status:** Reference — grounds future path, permission, and CLI decisions
- **Audience:** Contributors writing code that interacts with pathnames, pattern matching, permissions, or error reporting

## TL;DR

1. Grover's "everything is a file" story only works if paths *look like* POSIX paths to the human and the LLM. The relevant standard is **IEEE Std 1003.1-2024 (POSIX.1-2024)** — specifically its pathname, pathname-resolution, glob/fnmatch, regex, and errno chapters. Shell Utilities (Vol. 2) is the source of `grep`, `find`, `ls`, and glob semantics.
2. Grover already conforms to POSIX on the load-bearing rules: NFC normalization, NUL/control rejection, `PATH_MAX=4096`, `NAME_MAX=255`, `.`/`..` resolution via `posixpath.normpath`, and explicit flattening of the POSIX §4.13 `//` leading-slash carve-out.
3. The big conformance *gaps* are intentional: no mode bits (`rwxrwxrwx`), no symlinks, no hard links, no `.`/`..` directory entries, no `inode`, no `mtime/atime/ctime` triple, no `umask`. Grover swaps those for a `GroverResult` + `PermissionMap` + `kind` discriminator model. That's a conscious trade, not an oversight — but it has to be defended in every CLI/agent conversation, so this memo names the trade-offs.
4. Beyond POSIX, four adjacent standards shape the design surface: **Unicode TR#15 (NFC)**, the **Filesystem Hierarchy Standard (FHS)**, **Plan 9 / 9P** (the actual origin of "everything is a file"), and the **Linux VFS layer** (the architectural pattern Grover's `base.py` mirrors).
5. A handful of standards that look relevant are *not* load-bearing: XDG Base Directories, RFC 3986 URIs, POSIX.1e ACLs (withdrawn), NFSv4 ACLs. They're listed for completeness so nobody burns a week "aligning with" a spec that Grover has already decided to ignore.

## Why this memo exists

Grover's pitch to an LLM agent is: *this looks like a POSIX filesystem, your training data already teaches you how to use it.* That pitch only holds if the edges where Grover deviates from POSIX are enumerated and intentional. Three failure modes this memo tries to prevent:

- **Silent divergence.** Someone adds a feature that "feels filesystem-y" but accidentally breaks a POSIX invariant the agent has assumed for twenty years (e.g., changing `normalize_path` to keep `//`).
- **Cargo-cult conformance.** Someone implements a POSIX feature (symlinks, mode bits, hard links) because "filesystems have it", even though Grover has explicitly rejected the semantics.
- **Re-litigating solved questions.** Path length limits, illegal characters, `.`/`..` handling, glob grammar — these are decided by POSIX, and Grover should inherit, not re-invent.

## The standards landscape, ranked by how much they apply

| Standard | Relevance | Already conformant? | Where it lives in Grover |
|---|---|---|---|
| **POSIX.1-2024, §3.282 + §4.13 (pathnames, pathname resolution)** | Load-bearing | Yes | `paths.py::normalize_path`, `validate_path` |
| **POSIX.1-2024, §3.283 (Portable Filename Character Set)** | Load-bearing | Partial — Grover is *more* permissive | `paths.py::validate_path` (rejects NUL + controls only) |
| **POSIX.1-2024 Shell & Utilities §2.14 (Pattern Matching)** | Load-bearing | Yes, via `compile_glob` | `patterns.py`, `routing.py::rewrite_glob_for_mount` |
| **POSIX.2 Regular Expressions (BRE/ERE)** | Load-bearing for `grep` | Uses Python `re` (PCRE-ish, not POSIX BRE/ERE) | `query/` AST, `GrepOutputMode` |
| **POSIX.1-2024, `<errno.h>` error taxonomy** | High | Partial — Grover exposes 5 categories, not errno codes | `exceptions.py::_classify_error` |
| **POSIX.1-2024 file-type constants (S_IFDIR, S_IFREG, …)** | Medium | Not adopted — Grover uses `kind` string discriminator instead | `paths.py::ObjectKind` |
| **POSIX.1-2024 mode bits + `umask`** | Medium | Rejected by design — replaced by `PermissionMap` | `permissions.py` |
| **Unicode UAX #15 (NFC normalization)** | Load-bearing | Yes | `paths.py::normalize_path` |
| **ISO/IEC 10646 / UTF-8 pathname support** | Load-bearing | Yes (Python `str` is already USV-safe) | Entire codebase |
| **Plan 9 / 9P protocol** | Architectural inspiration | N/A — cited as the *source* of "everything is a file" | `constitution.md` Art. 1 |
| **Linux VFS pattern** | Architectural inspiration | Yes — `GroverFileSystem` is a near-direct analog | `base.py` |
| **Filesystem Hierarchy Standard (FHS 3.0)** | Mental model | Partial — users pick their own layout under mounts | Mount conventions |
| **POSIX.1e ACLs (draft, withdrawn)** | None | Intentionally ignored — `PermissionMap` is strictly simpler | `permissions.py` |
| **NFSv4 ACLs (RFC 8881 §6)** | None | Intentionally ignored | — |
| **XDG Base Directory Spec** | None | N/A | — |
| **RFC 3986 (URI)** | None | N/A — Grover paths are not URIs and should not be serialized as such | — |

## The POSIX rules Grover inherits by construction

These are the parts of POSIX that Grover's code already honors. Treat them as *invariants to preserve*, not as decisions to revisit.

### Pathname syntax (POSIX.1-2024 §3.282)

- Absolute paths begin with `/`. `normalize_path` enforces this by prepending `/` if missing.
- Path components are separated by `/`. No other separator is honored.
- A NUL byte (`\0`) is never valid in a pathname. `validate_path` rejects it.
- Two `.` and `..` are reserved as "this directory" and "parent directory". `posixpath.normpath` resolves them during `normalize_path`.
- Trailing slashes are not significant *except* that they imply the path must resolve to a directory. Grover strips them, which is safe for the current storage model but worth remembering if symlink-like indirection ever lands.

### Pathname resolution (POSIX.1-2024 §4.13)

POSIX §4.13 ("Pathname Resolution") includes this carve-out:

> A pathname that begins with two successive `<slash>` characters may be interpreted in an implementation-defined manner, although more than two leading `<slash>` characters shall be treated as a single `<slash>` character.

Grover *explicitly* refuses this carve-out and flattens `//x` to `/x`. The reason is in the `normalize_path` docstring and in `paths.py:176-182`: permission rules written against `/x` were bypassable via `//x` otherwise. This is the clearest case in the codebase of "we know about a POSIX degree of freedom and we're spending it."

### Length limits

- `PATH_MAX` = 4096 bytes (Linux convention; POSIX leaves this to `<limits.h>`). Enforced in `validate_path`.
- `NAME_MAX` = 255 bytes per segment. Enforced in `validate_path` and in `validate_user_id`.

These are *Linux* values — POSIX itself only requires `_POSIX_PATH_MAX >= 256` and `_POSIX_NAME_MAX >= 14`. Grover picked the de-facto Linux numbers because that's what LLMs have seen in training data. If macOS (1024) or Windows (260) conformance ever becomes a goal, these are the constants to revisit.

### Glob patterns (POSIX.1-2024 §2.14)

POSIX glob semantics, which `compile_glob` implements:

- `*` matches any string of characters *except* `/` (does not cross directory boundaries).
- `?` matches exactly one character, not `/`.
- `[abc]` / `[a-z]` / `[!abc]` bracket expressions.
- A leading `.` in a filename is *not* matched by `*` or `?` in traditional POSIX shells (the "hidden file" rule). Grover's metadata directories (`.chunks`, `.versions`, `.connections`, `.apis`) depend on this behavior being predictable.

Grover adds `**` for recursive matching, which is a Bash `globstar` / zsh extension, *not* POSIX. This is a deliberate superset — document it clearly in CLI help so agents don't assume POSIX-strict behavior.

## The POSIX rules Grover deliberately does not adopt

These are the big conscious deviations. Each one should be defensible in a design conversation.

### Mode bits and `umask`

POSIX files have a 9-bit mode (`rwxrwxrwx`) plus setuid/setgid/sticky, modified at creation by the process `umask`. Grover replaces this with:

- A per-filesystem `Permission` default (`read` | `read_write`).
- An optional `PermissionMap` with directory-prefix overrides.
- No user/group/other distinction; no execute bit; no `umask`.

**Why:** Grover is a library embedded in an agent application, not a multi-user OS. The real authorization boundary is the `DatabaseFileSystem(user_scoped=True)` user scope, not file-mode triplets. Simulating `rwxrwxrwx` would add API surface without adding security.

**Implication:** `chmod`, `chown`, and `umask`-shaped methods are *not* on the roadmap. If an agent requests them, the correct answer is "Grover uses `PermissionMap`; here's the prefix override for that path."

### Symlinks and hard links

POSIX has `symlink(2)` (`S_IFLNK`), `link(2)` (hard links via shared inode), and `readlink(2)`. Grover has none of these.

**Why:** The `kind` discriminator and connection graph (`/file/.connections/type/target`) already cover the "this path relates to another path" use cases — in a form agents can reason about (graph edges) rather than the ambiguity symlinks introduce (is this file the link or the target?). Path resolution does not recurse.

**Implication:** There is no `ELOOP`, no symlink loop detection, and no `readlink`. A connection is metadata, not indirection — operations on `/a/.connections/…/b` act on the connection record, not on `/b`.

### `.` and `..` as directory entries

POSIX directories contain entries named `.` (self) and `..` (parent). These are never stored; they're computed from path strings and resolved before any storage operation. Consequence: `ls /some/dir` does not return `.` or `..`.

**Implication:** Agent prompts should describe `ls` output as "entries inside the directory" rather than "directory listing" — the latter is ambiguous about `.`/`..`.

### `stat(2)` result shape

POSIX `struct stat` has `st_dev`, `st_ino`, `st_mode`, `st_nlink`, `st_uid`, `st_gid`, `st_rdev`, `st_size`, `st_atim`, `st_mtim`, `st_ctim`, `st_blksize`, `st_blocks`. Grover exposes a `Detail` payload with `kind`, size, content hash, and (where applicable) `extension`, `version_number`, `chunk_name`.

**Why:** `st_ino` is meaningless in a SQL-backed system; `st_uid`/`st_gid` don't exist; atime/ctime add write amplification for no agent benefit. `kind` carries more information than `S_IFREG`/`S_IFDIR` because Grover has five kinds (file, directory, chunk, version, connection, api), not two.

**Implication:** CLI `stat` should emit `kind`, `size`, `hash`, and whatever `Detail` is present — not attempt to produce `struct stat` aliases.

### Error reporting: exceptions, not errno

POSIX systems signal errors via a small errno code. Grover returns (or raises) one of five semantic classes: `NotFoundError`, `MountError`, `WriteConflictError`, `ValidationError`, `GraphError`.

**Mapping (approximate, for mental model only):**

| POSIX errno | Grover class |
|---|---|
| `ENOENT`, `ENOTDIR` (when expected dir) | `NotFoundError` |
| `EACCES`, `EROFS` | `WriteConflictError` (via `"Cannot write"`) |
| `EEXIST` (with `overwrite=False`) | `WriteConflictError` (via `"Already exists"`) |
| `EINVAL`, `ENAMETOOLONG` | `ValidationError` |
| `ENODEV` (no mount for path) | `MountError` |

**Implication:** Don't introduce new exception classes without extending `_classify_error`. And don't paper the POSIX errno names onto Grover output just because they're familiar — the semantic classes are the contract.

## Unicode and encoding

POSIX.1-2024 is the first edition that truly expects UTF-8 pathnames (prior editions treated pathnames as byte strings with no specified encoding). Grover is stricter than POSIX here:

- All pathnames are normalized to **Unicode NFC** (Canonical Composition) — see Unicode Standard Annex #15 (UAX #15, sometimes cross-referenced as the older TR#15 slug). This prevents `café` (composed, 5 code points) and `café` (decomposed, 6) from being different paths.
- C0 control characters (0x01–0x1F) and DEL (0x7F) are rejected.
- C1 control characters (0x80–0x9F) are also rejected — stricter than POSIX, which only forbids NUL.

**Why stricter:** Agent-generated paths are frequently copy-pasted from mixed-encoding sources. NFC + control rejection removes an entire class of "these paths look identical but compare unequal" bugs.

**Known gap:** The Portable Filename Character Set (POSIX §3.283, ASCII letters + digits + `._-`) is *not* enforced. Grover allows arbitrary Unicode identifier characters in path segments. If portability to archaic POSIX systems ever matters (unlikely for a library), this is where to tighten.

## Pattern matching: glob vs. regex

Grover exposes two pattern languages, and they should not be confused:

- **Glob** (`*.py`, `src/**/auth.py`, `[0-9]*.md`): used by `ls`, `find`, `glob`, and mount routing. Implementation: `patterns.py::compile_glob`. Semantics: POSIX glob + `**` (Bash globstar extension). Anchored by path structure.
- **Regex** (BRE/ERE/PCRE): used by `grep` on file content. Implementation: Python `re` module. Semantics: PCRE-flavored, *not* POSIX BRE or ERE.

**Non-obvious detail:** POSIX `grep` (without `-E` or `-P`) is BRE, where `(`, `)`, `{`, `}`, `+`, `?`, `|` are literal unless escaped. Grover's `grep` is Python `re`, where they are metacharacters. An agent trained on Linux `grep(1)` will produce patterns that work differently in Grover. This is a documentation gap worth closing in the CLI reference.

**Non-obvious detail #2:** When Grover is backed by MSSQL and full-text search kicks in, `CONTAINS` pre-filters are *word-tokenized*. `grep "grep"` does not match the word "grepper". This is captured in `feedback_mssql_fts_word_tokens.md` and is a real conformance gap between SQLite-backed Grover and MSSQL-backed Grover.

## Architectural ancestors worth citing

Three non-POSIX lineages show up in the code. Understanding them helps new contributors place Grover in context.

### Plan 9 / 9P

"Everything is a file" was coined for Plan 9 from Bell Labs (Rob Pike et al., 1980s–90s). Plan 9's 9P protocol is the direct ancestor of what Grover is doing: process state, network connections, graphics, and namespaces are all addressable through the file hierarchy, and operations are the same `Twrite`/`Tread`/`Tstat` verbs regardless of what the "file" actually is. Grover's `kind` discriminator is 9P's `QID.type` reinvented for a SQL backend.

**Reference:** Pike, Presotto, Thompson, Trickey. *Plan 9 from Bell Labs.* 1995. The 9P manual pages (`intro(5)` in Plan 9) are the canonical spec.

### Linux VFS (virtual filesystem switch)

Linux's kernel VFS (`fs/namei.c`, `fs/inode.c`, `fs/dcache.c`, `struct file_operations`, `struct inode_operations`) is the architectural pattern `GroverFileSystem` mirrors: an abstract "filesystem" with plug-in implementations (ext4, btrfs, NFS, FUSE), a path-walking layer that dispatches to the right implementation, and a vtable of operations. Grover's `base.py` `_*_impl` terminal pattern is directly analogous to `struct file_operations`. Mount routing is the `lookup` dentry walk, compressed into one function.

**Implication:** When extending Grover with a new backend, the mental model is "implement the ops table for a new VFS"; it's not "subclass a base class and override everything". Terminal vs. delegating methods in `base.py` enforce this distinction.

### FUSE (Filesystem in Userspace)

Grover is not a FUSE filesystem (no kernel involvement), but the *surface area* mirrors FUSE's `struct fuse_operations`. If someone ever wants to expose Grover as a real mountable filesystem, FUSE is the natural bridge: every `_*_impl` method has a FUSE callback equivalent (`getattr`, `readdir`, `open`, `read`, `write`, `unlink`, `rename`, `mkdir`, `rmdir`). The gap is error translation (Grover exceptions ↔ negative errno) and `stat` shape — both solvable.

**Reference:** libfuse documentation, `fuse.h`.

## Standards that look adjacent but do not apply

A brief "not this" list, so time isn't wasted exploring them:

- **XDG Base Directory Specification.** Defines `$XDG_CONFIG_HOME` etc. for user-facing apps. Grover's mount paths are application-chosen; there is no system-level convention to align with.
- **RFC 3986 (URI Generic Syntax).** Grover paths happen to look like URI paths but are not URIs. No scheme, no authority, no percent-encoding, no query/fragment. Don't serialize Grover paths as URIs — it implies guarantees (percent-decoding, normalization rules) Grover doesn't make.
- **POSIX.1e ACLs (draft, withdrawn 1997).** Never ratified. Linux, FreeBSD, and Solaris all implement variants, but the absence of a real standard is why ACLs are a minefield. `PermissionMap` is intentionally simpler.
- **NFSv4 ACLs (RFC 8881 §6).** Richer than POSIX.1e but also vastly more complex (inheritance flags, DENY semantics, 14 permission bits). Wrong shape for Grover's user-scoped model.
- **WebDAV (RFC 4918).** An HTTP-based remote filesystem protocol. If Grover ever needs a networked wire protocol, it's worth a look — but the "everything is a file" pitch works better over a CLI + MCP than over WebDAV verbs.
- **CIFS/SMB, NFS.** Wire protocols. Out of scope until Grover has a client/server deployment story.
- **ZFS / Btrfs snapshotting semantics.** Grover's `.versions/` namespace is conceptually a snapshot but is implemented as per-file version rows, not copy-on-write tree snapshots. The design goals diverge — don't import ZFS terminology.

## Practical implications for current and future Grover work

1. **Keep `normalize_path` strict.** Any future edit that relaxes NUL-rejection, control-char rejection, NFC normalization, or `//`-flattening needs a comment explaining the permission-bypass argument from §4.13 and a test proving permission rules still hold. The comment at `paths.py:166-182` exists precisely so this doesn't get quietly loosened.
2. **Document the glob superset.** `**` is non-POSIX; CLI help should say so. Agents trained on shell fnmatch will otherwise assume `**` is two literal asterisks.
3. **Document the regex flavor.** Grover `grep` uses Python `re`, not POSIX BRE/ERE. Anywhere the CLI documentation says "regular expression", say "Python `re`-flavor regular expression".
4. **Don't add `chmod`/`chown`/`umask`.** If someone files a request, the answer is `PermissionMap`. Rewriting to adopt mode bits would reopen the user/group/other modeling question the project has already declined.
5. **Errno-style errors are a non-goal.** The five-class hierarchy is the contract. Don't introduce `EACCES`, `ENOSPC`, etc. as string tokens in error messages — `_classify_error` keys off substrings and would mis-route.
6. **Any new "filesystem-like" feature gets a POSIX literacy check.** Before landing a `watch`/`inotify`-style subscription API, a `mount --bind`-style alias, or a symlink-equivalent, write down the POSIX analog *and* the reason Grover is either matching, superseding, or rejecting it. The habit keeps the agent story coherent.

## Open questions raised by this survey

- **Locale and collation.** POSIX allows per-locale sort order for `ls`. Grover sorts paths lexicographically on Unicode code points. Is that a problem for non-English deployments? (Probably not — agents don't rely on sort order — but worth naming.)
- **Case sensitivity.** POSIX filesystems are typically case-sensitive; macOS HFS+ and NTFS are case-preserving but case-insensitive. Grover is case-sensitive everywhere. If an enterprise deployment is backed by a case-insensitive DB collation, duplicate-insert races could surface. Not a current issue; worth a test.
- **Content-hash semantics.** Grover stores a content hash in `Detail`. POSIX has no equivalent, but ZFS/Btrfs/git do. Pick one algorithm (SHA-256?) and document it so agents can rely on stability across versions.

## Sources

### Canonical standards
- [IEEE Std 1003.1-2024 / The Open Group Base Specifications Issue 8](https://pubs.opengroup.org/onlinepubs/9799919799/) — POSIX.1-2024; §3.282 pathnames, §3.283 Portable Filename Character Set, §4.13 pathname resolution, §2.14 Shell pattern matching, §9 Regular Expressions, `<errno.h>`, `<limits.h>`
- ISO/IEC 9945:2024 — the ISO-numbered twin of POSIX.1-2024, published 14 June 2024 (iso.org catalog page exists but blocks unauthenticated fetches; search ISO's standards catalog for "9945:2024")
- [Unicode Standard Annex #15 — Normalization Forms](https://unicode.org/reports/tr15/) — NFC/NFD/NFKC/NFKD definitions (the `tr15` URL slug is the historical name; the document's current official designation is UAX #15)
- ISO/IEC 10646:2020 — the Universal Coded Character Set (UCS), aligned with Unicode 13.0 at publication and extended by amendments through Unicode 16.0 (iso.org catalog pages block unauthenticated fetches; search ISO's catalog for "10646:2020")
- [RFC 8881 — NFS Version 4 Protocol](https://www.rfc-editor.org/rfc/rfc8881) — §6 covers NFSv4 ACL semantics
- [Filesystem Hierarchy Standard 3.0](https://refspecs.linuxfoundation.org/fhs.shtml) — `/etc`, `/var`, `/usr`, etc.
- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/)
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986)

### Architectural ancestors
- [Plan 9 from Bell Labs — papers](https://9p.io/sys/doc/) — especially "Plan 9 from Bell Labs" (Pike et al., 1995) and "The Use of Name Spaces in Plan 9" (Pike et al., 1993)
- [9P protocol manual pages](https://9p.io/magic/man2html/5/intro) — `intro(5)`
- [The Linux Kernel: Filesystems](https://www.kernel.org/doc/html/latest/filesystems/vfs.html) — VFS overview
- [libfuse documentation](https://libfuse.github.io/doxygen/) — `fuse.h` / `struct fuse_operations`

### Commentary
- [Eric Raymond, *The Art of Unix Programming*, Ch. 20 (Futures) — "Plan 9: The Way the Future Was"](http://www.catb.org/~esr/writings/taoup/html/plan9.html) — Plan 9 critique (HTTPS cert on catb.org is valid but has SAN quirks; plain `http://` works reliably)
- [Michael Kerrisk, *The Linux Programming Interface*](https://man7.org/tlpi/) — the practical Linux-flavored companion to POSIX
- [Austin Common Standards Revision Group](https://www.opengroup.org/austin/) — the joint IEEE/ISO/Open Group body that maintains POSIX
