# Who composes the error message: thirteen filesystems, storage layers and agent frameworks

- **Status:** research memo (commits us to nothing). Feeds ADR 076
  (proposed, same day) and the 2026-10-10 rewrite of spec 154.
- **Date:** 2026-10-10
- **Owner:** Clay Gendron
- **Question:** Clay, 2026-10-10, reviewing spec 154: "it would make
  sense to me for the router to compose the message, the message
  shouldn't be written by storage, storage should send structured
  data back to the router which then composes the message. is this
  the right thinking? what do our prior arts do?" The sub-questions:
  in each project, what does the producer return (a code, a string, a
  struct); where is the text composed and where is the path attached;
  when a path is rebased across a mount or sub-filesystem boundary,
  does the text follow; and is the text ever load-bearing, parsed by
  a caller to decide behaviour.
- **Method:**
  1. Read the live tree at `4b598bc`: `results/envelope.py` (the
     model, the two seams, the three constructors), `results/kinds.py`
     (the vocabulary and the contract table), `results/render.py` (the
     error line), and every producer site (`grep` for `classified(`
     and `ResultError(` across `src/vfs`: 109 sites in 20 files).
  2. Tallied the distinct message wordings per kind at those sites.
  3. Two read-only subagent studies of the reference clones, one on
     the filesystem heritage, one on storage layers and agent
     frameworks, each asked the four sub-questions and told to cite
     `file:line` and copy nothing.
- **Sources (clones studied as found on 2026-10-10, not refreshed
  first; two are dirty, noted; licences read from the checkout):**
  `plan9` `ed1a9c21e` (2025-10-28, dirty; Plan 9 Foundation MIT-style
  licence); `plan9port` `b6564bd9` (2026-08-26; same); `freebsd-src`
  `d9e2caccfac1` (2026-10-02; BSD-2-Clause per its `COPYRIGHT`; the
  checkout holds `sys/` and `share/man/man9` only, no libc); `linux`
  `faeab1661` (2026-04-18, dirty; GPL-2.0 with syscall exception,
  studied only); `libfuse` `ff326b1` (2026-04-17; LGPL-2.1 library,
  GPL-2.0 utilities, studied only); `pjdfstest` `85a8aea`
  (2026-08-07; BSD-2-Clause); `opendal` `8fcab84` (2026-09-04;
  Apache-2.0); `pyfilesystem2` `77a8562` (2025-05-17; MIT);
  `filesystem_spec` `13b0bce` (2026-09-01; BSD-3-Clause);
  `python-sdk` `7bb486a1` (2026-09-05; MIT); `modelcontextprotocol`
  `e76e9c57` (2026-09-04; licence file records a transition from MIT);
  `mirage` `3273608e9` (2026-10-08; Apache-2.0); `afs` `1e9b731`
  (2026-03-24; BSL 1.1, studied only); `agentfs` `0a014eb`
  (2026-06-03; no licence text in the checkout, README claims MIT);
  `deepagents` `1d3232c08` (2026-09-14; MIT). Nothing copied from any
  of them.

## Bottom line

Three models. The producer returns a bare code and the consumer's
library supplies the words (Unix, FUSE, the POSIX test suite). The
producer returns fields and a template renders the text late, so a
rebased field renders a rebased message (opendal, pyfilesystem2,
mirage). Or the producer writes prose with the path inside it, and
every sub-filesystem seam leaks the inner path (Plan 9, fsspec, afs,
deepagents). Only the first two stay correct across a mount boundary.
vfs today is in the third model with the second model's parts already
built: a hierarchical kind, a structured locus, a seam that rebases
fields, and a contract table consulted at render time. One piece, the
message, is still authored by the producer, and that is where every
leak lives.

Clay's instinct, that storage should return structured data and
someone downstream should compose the words, is the first two models.
The refinement the prior art suggests is *who*: not the router at the
mount seam, which does not know when an error is final, but the
renderer, from fields, after every rebase has run. That is `strerror`
plus the program prepending the file name, and it is opendal's
`Display` and pyfilesystem2's `__str__`.

## 1. vfs today

- **The line.** `_error_line` renders `SEVERITY <path>: <message> —
  <hint> (retry: <class>)`. Locus from `path` (or `mount <source>`),
  hint and retry class from `KIND_CONTRACTS` by `kind_family`, message
  from the producer.
- **The doors.** 67 raw `ResultError(...)` calls and 53 calls to
  `classified(kind, message, path, *, target, retryable)`. Both take
  prose. The router's `_error(message, *, kind, op, ...)` helper is
  documented as "pass the prose message" and has 25 callers.
- **The wordings collapse.** Of the one-line `classified` sites:
  "Not found" with `{path}`, `{target}`, `{ancestor}`, `{named}`,
  `{endpoint}`, `{staged.path}` and `{link}`; "Not a directory" five
  ways; "Already exists", "Directory not empty", "Permission denied",
  "Is {article} {kind}" once each. The kind already names the phrase.
- **Two categories resist a template.** Driver text ("grep failed:
  cannot start a transaction within a transaction", `engine.py`) and
  parameter causes ("max_depth must be >= 1, got 0", `backend.py`;
  "Cannot move {src} into itself", `topology.py`). These need a slot
  for a cause that is not the kind.
- **The second entry is opaque.** `classified()` writes `target` to
  `data["target"]` in the producer's coordinates as a merge
  discriminator; `with_mount` never rebases it.

## 2. The filesystem heritage

### 2.1 Unix: errno and `strerror`

- **Producer returns:** an integer. `linux/include/uapi/asm-generic/
  errno-base.h:6`, `freebsd-src/sys/sys/errno.h:49`; kernel code
  returns `-ENOENT` (`linux/fs/namei.c:1639`) or `ENOENT`
  (`freebsd-src/sys/kern/vfs_lookup.c:508,722`). The text in those
  headers is C comments.
- **Text composed:** in the user's libc (`strerror`, `perror`,
  `err(3)`), not in these checkouts (the FreeBSD clone has no
  `lib/libc`; Linux has no libc). Linux's own `lib/errname.c:217`
  turns a number into its *symbol name* for `printk` (`%pe`,
  `Documentation/core-api/printk-formats.rst:101`).
- **Path attached:** by the program, at print time. The kernel never
  attaches one.
- **Load-bearing:** no; callers branch on the number.

### 2.2 libfuse

- **Producer returns:** a negative errno (`include/fuse.h:335-339`;
  `example/passthrough.c:90`); the low-level `fuse_reply_err` takes
  a positive one (`include/fuse_lowlevel.h:1380-1383`).
- **Text:** none. The reply header to the kernel is a 32-bit error
  number with no text field (`include/fuse_kernel.h:1046-1050`). The
  library rejects values that are not real errnos and substitutes
  `-ERANGE` (`lib/fuse_lowlevel.c:320-331`).

### 2.3 pjdfstest

- Its helper turns `errno` into the symbol name, "ENOENT", or the raw
  number if unknown (`pjdfstest.c:1216`, table `1346-1721`). Tests are
  written `expect ENOENT open ...` (`tests/open/04.t:15`) and `expect`
  regex-matches the last output line against the name
  (`tests/misc.sh:38-43`). `strerror` text appears only in the suite's
  own setup failures (`pjdfstest.c:1251`). The name is the contract;
  the readable text never is.

### 2.4 Plan 9 and plan9port: the counter-example

- **Producer returns:** a string. The 9P reply struct has a text field
  for `Rerror` (`plan9/sys/include/fcall.h:23`); servers pass a text
  reason to `respond` (`plan9/sys/src/lib9p/srv.c:745`, `:33`).
  plan9port adds a numeric field for 9P2000.u
  (`plan9port/include/fcall.h:46`).
- **Text composed:** the kernel's strings live in `9/port/error.h`
  (e.g. "file does not exist", `:9`), turned into a table by
  `9/port/mkerrstr`. A mounted server's text is re-raised unchanged
  (`9/port/devmnt.c:191`, `:750`).
- **Path attached:** by the kernel, into the string. `namelenerror`
  writes the quoted, possibly shortened, path in front of the text
  (`9/port/chan.c:1250-1291`, from `namec` at `:1418` and
  `sysfile.c:1186`). Programs still prepend the name themselves:
  `cat` uses "can't open %s: %r" (`cmd/cat.c:28`), as do `ls`
  (`cmd/ls.c:99`) and `rm` (`cmd/rm.c:13`). Users see the name twice,
  which is the vfs symptom exactly.
- **Load-bearing:** yes. `upas/common/libsys.c:514` compares the whole
  string to "file does not exist"; `ndb/cs.c:1642`,
  `upas/fs/plan9.c:189`, `ssh2/dial.c:107,287` and `con/con.c:653`
  search for substrings.

## 3. Storage layers

### 3.1 opendal (the model to copy)

- **Shape:** `Error` has kind, message, status, operation, a list of
  key-value context pairs, source and backtrace
  (`core/core/src/types/error.rs:243-253`).
- **Who writes the words:** the service writes a short phrase only.
  `new_std_io_error` uses the io error kind as the message
  (`core/core/src/raw/std_io_util.rs:42`); the fs service adds only
  `service_operation` context (`services/fs/src/core.rs:342-353`).
- **Where the path goes:** `ErrorContextLayer`, above the service,
  attaches `path`, `from` and `to` as context keys
  (`core/core/src/layers/error_context.rs:95-162`); the operator
  builder installs it automatically
  (`core/core/src/types/operator/builder.rs:46`). `with_operation`
  pushes the earlier operation into context as `called`
  (`error.rs:364-371`).
- **Rebasing:** not needed. The layer records the operator-relative
  path before the service joins it with its root, and the message
  never held a path.
- **Load-bearing:** no. `Display` builds the text from fields every
  time (`error.rs:255-282`); callers branch on the kind.

### 3.2 pyfilesystem2

- **Shape:** `ResourceError` stores `path` and `exc`
  (`fs/errors.py:254-266`); each subclass has a `default_message`
  template such as "resource '{path}' not found" (`:272`).
- **Who writes the words:** `__str__` fills the template from the
  error's own attributes each time it prints (`errors.py:83-86`).
- **Rebasing:** yes. `SubFS.delegate_path` maps to the parent's
  coordinates (`fs/subfs.py:51-54`); each `WrapFS` method wraps the
  delegated call in `unwrap_errors(path)` (`fs/wrapfs.py:115,129`),
  which sets `e.path` back to the caller's path
  (`fs/error_tools.py:109-117`). Because the text renders late, it
  rebases too. Two gaps: only `ResourceError` is caught, so
  `PathError` subclasses keep the delegate path; and an explicit
  `msg=` with the path already formatted in would not be rewritten
  (inferred, no call site traced).
- **Load-bearing:** no; callers use the class and `.path`.

### 3.3 fsspec

- **Shape:** a builtin `FileNotFoundError(path)` with one argument
  (`fsspec/implementations/memory.py:175`, `fsspec/spec.py:761`),
  which sets no `filename`, so the path exists only as the message.
  Only arrow uses the three-argument errno form
  (`implementations/arrow.py:122`).
- **Rebasing:** no. `DirFileSystem` joins paths
  (`implementations/dirfs.py:65-83`) and fixes `info["name"]` on
  success (`:277-281`) but has no try/except, so errors leak the full
  delegate path.

## 4. The wire: MCP

- **Shape:** `Error` is code, message and optional data
  (`modelcontextprotocol/schema/draft/schema.ts:241-254`). The only
  rule on composition: message "SHOULD be limited to a concise single
  sentence" (`:247`); `data` is sender-defined.
- **Tool failures:** the tool writes the text; it goes in result
  content with `isError` (`schema.ts:1827-1837`), and the spec's
  example is a free-text hint for the model
  (`docs/specification/draft/server/tools.mdx:761-787`). The Python
  SDK turns `ToolError` into `CallToolResult(text=str(exc),
  is_error=True)` (`python-sdk/src/mcp/server/mcpserver/server.py:447`)
  and collapses unexpected crashes to "Error executing tool <name>"
  (`src/mcp/server/mcpserver/exceptions.py:60-73`). No path field;
  rebasing not addressed.
- **Load-bearing:** by design; the text is what the model reads. This
  is why `message` must stay a populated string on vfs's wire.

## 5. Agent frameworks

### 5.1 mirage

- Builders `fs_error`, `enoent`, `eacces` produce a real `OSError`
  with errno, a POSIX phrase and the path in `filename`
  (`python/mirage/errors/fs.py:44-75`). The path used is
  `PathSpec.virtual`, the mount-level spelling (`fs.py:39-41`,
  `types.py:830`), so it is correct from construction. The shell layer
  writes its own "<target>: <strerror>" line from the target as typed;
  its docstring says it never uses `str(exc)` because backend prose
  once leaked out as the path
  (`workspace/executor/redirect.py:851-861`). Callers branch on errno
  (`workspace/dispatcher/dispatcher.py:1068`).

### 5.2 afs

- `AFSError` has a code; `AFSNotFoundError` adds a path with a default
  message "Path not found: ${path}"
  (`packages/core/src/error.ts:4-33`). The router calls
  `module.read(subpath)` with no try/catch (`afs.ts:1589`), so a
  provider's error leaks the sub-path (the UI provider throws with
  "/primitives/x", `providers/ui/src/ui-provider.ts:1753`). A bug at
  `afs.ts:1584-1586` passes prose as the path argument, so `.path`
  holds a sentence. Callers branch on `instanceof` (`afs.ts:2528`).

### 5.3 agentfs

- The Rust `FsError` is a bare enum with a fixed message and no path
  (`sdk/rust/src/filesystem/mod.rs:23-53`), mapped through `to_errno`
  (`:60`). The TypeScript side is Node-style: `code`, `syscall`,
  `path`, plus a message "CODE: base, syscall 'path'" built at
  creation (`sdk/typescript/src/errors.ts:37-51`). No rebasing found.

### 5.4 deepagents

- Downloads and uploads use typed codes (`file_not_found`,
  `permission_denied`; `backends/protocol.py:39-62`). Read, write,
  edit and ls return only `error: str` (`:207`, `:290`, `:308`), and
  the backend writes the path into it: "File '...' not found"
  (`backends/filesystem.py:447`), "Path '...': not_a_directory"
  (`:291`). `CompositeBackend.read` strips the route from `path` but
  not from the error string (`backends/composite.py:407-408`); `edit`
  fixes `res.path` and not the text (`:759-762`). The middleware
  searches the text for `not_a_directory` to decide delete behaviour
  (`middleware/filesystem.py:516,535`): prose that is load-bearing,
  the failure mode vfs's envelope law already forbids.

## 6. What this means for vfs

| | code only | fields, rendered late | producer prose |
|---|---|---|---|
| Correct across a mount seam | yes | yes | no |
| Carries a cause the code cannot | no | yes (context / detail) | yes |
| Text parseable by accident | no | no | yes, and done (Plan 9, deepagents) |
| vfs has the parts | kind | kind, path, data, seam, contract table | today |

- The kind is the code. The contract table is `strerror`'s table and
  already holds the hint and the retry class; the phrase belongs
  beside them.
- opendal's short message plus context keys is the shape for the two
  causes a template cannot carry: a path-free `detail`, and named
  fields in `data`.
- pyfilesystem2 shows the late-render rule and its two gaps: every
  door must go through the template, and an explicit message
  parameter is the leak. Hence one constructor with no message
  argument.
- mirage shows the alternative of stamping the mount-level path at
  construction. vfs cannot: a storage does not know its mount, and an
  error may cross several. The seam already rebases `path`; it must
  also rebase the second entry, which pyfilesystem2 never handles.
- MCP keeps `message` on the wire as a populated sentence; derivation
  at construction satisfies it with no new field.

Open to the decision record: whether the phrase composes at
construction (safe, because the phrase holds no locus) or at render
(purer, but makes `message` a derived wire field). ADR 076 picks
construction.
