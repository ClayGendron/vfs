# 169 — Programs, the index and the `/.vfs` views: install by write, resolve through a union, run under a WASI host

- **Status:** draft — cut 2026-10-15 from ADR 082 pins 6–12 and ADR 084 pins 2, 7, 8, with the executed spike as the mechanism; amended the same day from the pre-build review (`research/studies/2026-10-15-agent-shell/14-spec-169-review-before-build.md`) and Clay's five decisions on it. Lands after spec 167, in three slices (169a, 169b, 169c); the first programs land after spec 171. Not started. One `[NEEDS CLARIFICATION]` in §b8.
- **Date:** 2026-10-15
- **Owner:** Clay Gendron
- **Kind:** feature. 169a: a router-owned view table under `/.vfs`, the program and skill index, the union resolver, two `Observation` query fields, `application/wasm` by magic, the `/.agents` families retired. 169b: a WASI preview1 host in Python (`shell/wasi/`) with whole-file staging, fuel and wall budgets, a compiled-module cache, and the optional extra `vfs-py[wasm]`. 169c: the `/.vfs/run` view. No stored schema changes and no format bump.
- **Depends on:** spec 167 (the ABI, the runner, the `cli` meta-verb, `Session.path`, the exit-code table in `shell/status.py`, and `move(…, overwrite=)` — decided 2026-10-15 for 167's task zero); ADR 082 (pins 6–12); ADR 084 (pins 2, 5, 6, 7, 8); ADR 083 pin 6; ADR 085 pin 12. The trash view as built (`storage/backends/database/trash.py`, `reads.py`'s view heads) is the precedent for a derived view.
- **Decisions it carries (Clay, 2026-10-15, on the review):**
  1. `/opt/bin` is created by the host as the system actor at posture `read`; installing needs an `add` grant; `vfs install` runs as the host.
  2. One guest at a time per process is acceptable for 0.1; the Rust host in `crates/vfs-core` is the named direction.
  3. A `budget_exhausted` kill gives the stage exit 137 (128 + SIGKILL); `timeout` stays 124.
  4. Writes over kernel names are refused at write time, scoped to names not in `prefer_stored`.
  5. No program-attribution column at v1. The `/.vfs/run` record (169c) is the record. There is no `source_identity` stamp.
- **Research it stands on:** the memo §5, §6, §8, §12 and studies `03-program-abi-and-bin-namespace.md`, `04-filesystem-over-the- sandbox-boundary.md`, `06-execution-policy.md`, `10-wasm-program-spike.md`; the executed shim and host in `experiments/e1/shim/` and `experiments/s4/shim.py`; the review's probes in `experiments/r169/`.

## Intent

After this spec a host registers which directories hold programs and skills, and `ls /.vfs/bin` lists every callable with its kind. An agent holding an `add` grant installs a program by writing a `.wasm` file into an indexed directory, and runs it by name. Every file the program touches goes through the caller's verbs with the caller's authority. Its deletes land in the trash. Its writes mint versions. A write the caller may not make fails loudly, even when the program exits 0. A spinning program is killed by a count, not a clock. The same name can later be served by a different kind without the agent noticing.

## Slices

| Slice | What lands | Needs wasmtime |
|---|---|---|
| **169a** | The `/.vfs` tree and its refusals, the router-owned view table, `/.vfs/bin` and `/.vfs/skills`, the index, resolution, install rules, `/.agents` retired | no |
| **169b** | The WASI host: the shim, staging, write-back, budgets, traps, the cache, the executor, the errno mapping, the extra and its fixtures | yes (optional extra) |
| **169c** | `/.vfs/run`: the per-call record and output rows | no |
| **Final section** | The first programs: uutils, jaq, a wasi awk, `vfs install` | lands after spec 171 |

Each slice lands green on its own. Between 169a and 169b a resolved program answers `unsupported` with exit 126 (§a5).

---

## 169a — The views and the index

### a1. The `/.vfs` tree: heads, owners, refusals (ADR 082 pins 6–8)

- `paths.py` declares the view heads as one table, `VIEW_HEADS`, mapping a head name to its owner:

  | Head | Owner | Served | Slice |
  |---|---|---|---|
  | `trash` | each backend | `<mount>/.vfs/trash`, per mount | as today |
  | `bin` | the router | `/.vfs/bin`, at the root only | 169a |
  | `skills` | the router | `/.vfs/skills`, at the root only | 169a |
  | `run` | the router | `/.vfs/run`, at the root only | 169c |
  | `tools`, `mcp` | the router | at the root only | spec 170 (reserved here) |
  | `sessions`, `jobs` | — | reserved, unserved | — |

- **Writes anywhere under `/.vfs/` are refused.** `check_mutable_path` refuses every path strictly beneath `/.vfs/`, except the trash head for `sweep`. It holds in global and in mount coordinates, so `/data/.vfs/bin/x` is refused too. The refusal is `invalid`. It carries the path the caller sent (today `_invalid_path` carries `path=None`). The router adds a detail naming the index's writable program directories; `resolve_path` stays index-blind.
- **The grant verbs are not mutations here.** `grant`, `revoke`, `grants` and `posture` at a `/.vfs` path stay lawful and resolve through the mount table only (never the view table), so their rows live in the root binding's grants table. Spec 170 relies on this.
- **The backend synthesizes its meta root.** `stat /.vfs` is a directory and `ls /.vfs` lists `trash`, in every storage's own coordinates, whether or not a row is stored there. (Today both are `not_found` on a fresh node, and `ls /data/.vfs` too; only `ls /.vfs/trash` works.) At the root, the router appends its served heads (`bin`, `skills`, and `run` from 169c) to the root storage's answer. Reserved, unserved heads do not list; a read of one is `not_found`; a write is `invalid`.
- **No stored row lives beneath `/.vfs`.** The write refusal makes it an invariant from this landing on. There is no production data to migrate.
- The `/.vfs` tree stays hidden from unscoped `glob` and `grep` (today's meta-scoped rule). §a2's table keeps it so by construction.

### a2. The router-owned view table

- The router keeps a second table, `_views: dict[Path, Binding]`, keyed by head path (`/.vfs/bin`, `/.vfs/skills`, `/.vfs/run`). It is separate from the mount table.
- `_match_mount` consults it first, for a path equal to a head or beneath one, at the root only. Every route helper already resolves through `_match_mount`/`_resolve_terminal`, so this one lookup routes every verb. `_route_grant` resolves through the mount table only (§a1).
- `mounts()`, `bind`, `unbind`, `close()`, the busy guard and `_bindings_beneath` never read `_views`. So an unscoped fan-out (`glob **`, `grep -r /`) never reaches a view.
- A view is an object with the read protocol. Its `meta.caps` is the verb list below; the capability gate answers `unsupported` for any other read verb. Mutations are `invalid` before that (§a1). A view is built at construction and is never owned by `close()`.
- A view answers each call by re-entering the router's public verbs with the call's authority. Every gate fires. The hop budget counts the re-entry.
- Why not a storage bound into the mount table: a mount path may not hold the `.vfs` segment; `bind` probes for a stored empty directory; `mounts()` rows are meant to be replayable; `_bindings_beneath("/")` would send unscoped searches into the view; `with_mount` would rebase a source path. (Review finding 1, probe `p1_routing`.)

**Verbs per view:**

| View | Verbs served | What `read` and paths beneath mean |
|---|---|---|
| `/.vfs/bin` | `stat`, `ls`, `glob`, `read` | `read /.vfs/bin/<name>` forwards to the resolved source row under the caller's authority |
| `/.vfs/skills` | `stat`, `ls`, `tree`, `glob`, `grep`, `read` | `/.vfs/skills/<name>/<rest>` forwards to `<rest>` under the unit's source directory |
| `/.vfs/run` (169c) | `stat`, `ls`, `read` | §c1 |

A `glob` scoped to a view filters the view's synthesized rows in memory. Its cost grows with the index, and the docstring says so.

### a3. The union rows (`Observation` fields)

- A union row is `kind="file"` (or `"directory"` for a skill unit) at its view address (`/.vfs/bin/jq`). `kind` keeps its `ObjectKind` meaning and `source` keeps its `text`/`bytes` meaning; both are mirror fields pinned by the drift test.
- Two new query fields carry the rest:
  - `callable_kind: Literal["program", "tool", "mcp", "skill"] | None`
  - `resolved: Path | None` — the source path, in router coordinates.
- Both join `OBSERVATION_QUERY_FIELDS`, the projection allow-list, the renderer's `ls -l` columns and `to_payload`. `with_mount` and `without_mount` never touch `resolved`.
- The source row's own fields (`version`, `size_bytes`, `mime_type`, `content_hash`, `updated_at`) ride under their own names, at the source row's projection for this caller. **A caller holding `list` on the source sees the union row bare** (`path`, `kind`, `callable_kind`). A caller below `list` does not see it.

### a4. The index (ADR 082 pins 9–10)

- `VirtualFileSystem(index=Index(programs=("/opt/bin",), skills=(), prefer_stored=(), masked=()))` is the default. `Index` is frozen.
- `add_index_path(kind, path)` and `remove_index_path(kind, path)`, with `kind: Literal["programs", "skills"]`, are async admin methods beside `add_mount`. They take no authority, are not ops, and mutate under `_mount_lock`. `index()` reads the table back, like `mounts()`. The index is runtime table state; nothing about it is stored.
- **Program directories are minted by the host** (Clay, decision 1). Before the first verb that addresses or resolves through a configured program directory, the router runs, once per process and as the system actor: `mkdir(dir, parents=True, exist_ok=True)` and `posture(dir, "read")`. A directory that already exists is left as found, posture included. A directory on a storage that does not declare `posture` gets the `mkdir` only. Installing therefore needs an `add` grant on the directory. `ls /.vfs/bin` is empty until the first install. Skill directories are found, never minted.
- A mounted repository's `bin/` joins only when the host lists it.
- The index is host configuration. It widens nothing: every lookup is a gated `stat` under the caller's authority (ADR 063 holds).
- `Index` and the views live in `vfs/views.py`. `base.py` never imports `vfs.shell`.

### a5. Resolution

- **Order.** Shell-state builtins, then the kernel program table, then the session's `path` prefix, then the index in order. A word with a slash names an entry directly.
- **One batched `stat`, never an `ls`.** Resolving one name is one `stat(observations=…)` over the candidates in order: each directory (session prefix first, then the index) × each runtime suffix. The router groups it per mount, so it is one dispatch per mount, bounded by `directories × suffixes`, never by directory size. The first visible hit wins.
- **Suffixes.** The order is `.wasm`, then spec 172's suffixes, then none. `jq.wasm` serves `jq`; the suffix selects the runtime. A suffix-less bytes row runs when its mime is `application/wasm`. When two candidates share a basename in one directory, the first in this order wins: `ls /.vfs/bin` shows the winner and `type -a` shows every one, marking the shadowed.
- **Outcomes.** No visible candidate: 127. A name in `Index.masked`: `unsupported`, 126 (ADR 084 pin 8, moved off `deny_ops`, §a6). A candidate the caller can `list` but not `read`: 126 at execution (§b9). A program found while no runtime is installed (169a alone, or the `wasm` extra absent): `unsupported` naming the extra, 126.
- **The session `path` reaches the view.** The `Session` facade sets a context variable holding its `path` for the duration of each call. `/.vfs/bin` and resolution read it and prepend those directories. A call made without a session sees the host index only. It is order, not rights: each candidate is still a gated `stat`. "Directories it can already list" is not checked at prepend time; a directory the caller cannot see simply misses.
- **Kernel names.** The shell's kernel table exports its names as `KERNEL_NAMES: frozenset[str]` in `vfs/ops.py` beside the verb vocabulary (a leaf module), so the router reads it without importing `vfs.shell`. A drift test pins it to the table. Resolution never serves a stored entry under a kernel name unless the name is in `Index.prefer_stored`.

### a6. Install (ADR 084 pins 7, 8)

- A program is an entry with `source = bytes` and `mime_type = application/wasm`. The mime comes from the magic table: `_MAGIC` gains the core-module signature `\0asm\x01\x00\x00\x00`. A component (`\0asm\x0d\x00\x01\x00`) does not match: the host runs core modules only. (Today a `.wasm` body sniffs as `application/octet-stream`.)
- A row whose mime is not `application/wasm` (a text file named `x.wasm`) is refused at execution as `invalid` ("not a wasm module"), exit 126, like bash's "cannot execute binary file".
- Install is `write(path, data=, parents=True)` under the ladder: `add` for a fresh name, `contribute` or own for an occupied one, `read_write` or own to delete. Every overwrite is a version, so a bad install is one `restore` away. Under the host's `read` posture on `/opt/bin` (§a4), an agent needs an `add` grant.
- **Kernel names are refused at write time** (Clay, decision 4). The refusal fires in the router's mutation gate for `write`, `copy` and `move` whose destination is `<an indexed program directory>/<name>` plus a runtime suffix or none, when `<name>` is in `KERNEL_NAMES` and not in `Index.prefer_stored`. It is `invalid`, with a detail naming `prefer_stored`. `add_index_path` is never refused.
- **Masking.** `Index(masked=frozenset[str])` holds the masked program names. A masked name resolves to `unsupported`, exit 126. A kernel name in `masked` is a `ValueError` at construction (a builtin is masked through its verb). `deny_ops` is unchanged and still takes only op names. (Today `deny_ops=["jq"]` is accepted and does nothing.)

### a7. The skills view and the retirement of `/.agents`

- A skill-index entry is a **container**: its skills are the directories `<entry>/<name>/` holding `SKILL.md`, found with one `glob <entry>/*/SKILL.md` per entry. The union key is `<name>`; the first entry in index order wins. `/.vfs/skills` lists the unit directories with `callable_kind="skill"` and `resolved` the unit's path.
- `paths.py`: `AGENTS_ROOT`, `AGENT_FAMILIES`, `tool_path`, `skill_path`, `tool_manifest_path`, `skill_manifest_path` and the `/.agents` rule in `is_reserved_directory` go.
- `Skill.to_entries(at=container)` writes `<container>/<name>/SKILL.md` and its resources, so the Agent Skills rule "the name matches its parent directory" still holds.
- The retirement also touches `models/entry.py` (the `is_reserved_directory` check), `tests/test_paths.py`, `tests/test_skills.py`, `tests/models/test_models.py` and the README's namespace block.

### Acceptance criteria (169a)

Every count below is counted with a spy. None is timed.

1. On a fresh node, `ls /.vfs` at the root lists `bin`, `skills` and `trash`; `ls /data/.vfs` at a mount lists `trash` only; `stat /.vfs` is a directory at both.
2. `write`, `mkdir`, `move` and `copy` into `/.vfs/bin/x`, `/.vfs/sessions/x`, `/.vfs/other` and `/data/.vfs/bin/x` are each `invalid` with the caller's path and the index detail; `sweep /.vfs/trash` still passes; `posture` on `/.vfs/bin` passes and lands in the root binding's grants table.
3. An unscoped `glob **` and `grep -r` make zero calls to any view; `mounts()` lists no view; `locate("/.vfs/bin/jq")` names the view.
4. The first resolution on a fresh node mints `/opt/bin` once, as the system actor, at posture `read` (one `mkdir`, one `posture`; a second resolution adds none). An agent's `write /opt/bin/ upper.wasm` is `permission_denied` with no grant and `created` with an `add` grant.
5. `ls /.vfs/bin` shows `upper` with `callable_kind=program`, `resolved=/opt/bin/upper.wasm`, `mime_type=application/wasm`. A caller holding `list` sees the row bare. A caller below `list` does not see it.
6. Resolving a name over a 10,000-file program directory is one `stat` dispatch per mount and zero `ls`.
7. `write /opt/bin/sed.wasm` is `invalid`; with `prefer_stored= ("sed",)` it is `created` and `sed` resolves to it.
8. A name in `masked` is `unsupported`, 126. A text file named `x.wasm` is `invalid`, 126.
9. A session with `path=("/home/ann/bin",)` sees its own `jq.wasm` in `ls /.vfs/bin` and in `type jq`; the same call without the session sees the index only.
10. `/.vfs/skills` over two containers sharing one skill name shows the first; discovery is one `glob` per container; `read /.vfs/skills/<name>/SKILL.md` returns the source body.
11. With no runtime installed, a resolved program is `unsupported` naming `vfs-py[wasm]`, 126.
12. `/.agents` names are gone from `src/`, the drift tests pass, and `scripts/ci.sh` is green at 100%; the four engine legs green.

---

## 169b — The WASI host (`shell/wasi/`)

### b1. The dependency and the fixtures

- wasmtime is an optional extra, `vfs-py[wasm]`. Without it the host answers `unsupported` naming the extra (§a5). The dev group carries it, so the 100% coverage gate runs the host.
- Shim tests use WAT guests compiled at test time with `wasmtime.wat2wasm`: no Rust toolchain and no network in a test run.
- Two Rust guests from the spike (`upper`, `fsops`; 83 KB and 104 KB) are checked in under `tests/fixtures/wasm/` with their sources and a rebuild script.

### b2. The preview1 functions

- **Real: the spike's 35.** Beyond the memo's 24, these are real: `fd_sync` and `fd_datasync` flush the buffer now (§b5); `fd_filestat_set_times` and `path_filestat_set_times` accept and ignore (vfs stamps its own `updated_at`); `poll_oneoff` serves clock subscriptions only, bounded by the remaining deadline, and answers `NOTSUP` for fd subscriptions; `fd_pread`, `fd_pwrite`, `fd_renumber`, `fd_advise`, `fd_fdstat_set_flags`, `fd_fdstat_set_rights`, `sched_yield` and `clock_res_get` work on the buffers or succeed.
- **Stubs (`NOTSUP`):** `fd_allocate`, `path_link`, `path_readlink`, `path_symlink`, `proc_raise`, and the four `sock_*`. Stubs always return an int and never raise. `path_link` must exist, or instantiation traps.
- `fd_fdstat_get` reports a character device for stdio. EOF is `0` with success.

### b3. Paths, preopens and the hidden tree

- **Two preopens.** fd 3 is `/`. fd 4 is `.`, bound to the call's `cwd` (spec 167's `Session.cwd` or the call's `workdir`). `fd_prestat_get(5)` answers `BADF`, which ends wasi-libc's scan. So a relative path opens against the shell's `cwd`, not `/`.
- `..` may climb from the `cwd` preopen up to `/`. A path that climbs above `/`, or an absolute path from a guest that bypassed libc, is `NOTCAPABLE` before any verb.
- **`/.vfs` is hidden from the guest.** A path with any `.vfs` segment is `ENOENT` before any verb. This also hides an ordinary directory named `.vfs` deep inside a mount; that is accepted. The rest of the namespace is what the authority sees.

### b4. Opening a file: at most one verb

`path_open` issues at most one verb:

| Open flags | Verb at open | Classification |
|---|---|---|
| `O_DIRECTORY` | one `ls`, materialized into the fd | its errno |
| `O_CREAT \| O_EXCL` | one `stat` | `exists` → `EEXIST`; a miss at the target → empty dirty buffer |
| `O_CREAT \| O_TRUNC` | one `stat` (no body) | a directory → `EISDIR`; a miss at an ancestor → `ENOENT`; a hidden or denied name → its errno; else an empty dirty buffer |
| anything else | one `read`, `columns={content, data, kind, size_bytes, mime_type, version}` | below |

How a `read` error is classified:

- `not_found` whose `path` is the target: `ENOENT`, or an empty dirty buffer under `O_CREAT`.
- `not_found` whose `path` is an ancestor: `ENOENT`, even under `O_CREAT` (POSIX: a create under a missing parent fails at open).
- `wrong_kind` with `error.path == target` and `data.kind == "directory"`: a directory open. `EISDIR` if the rights ask to write; otherwise the `ls` happens at the first `fd_readdir`.
- Any other `wrong_kind` (an ancestor is a file): `ENOTDIR`.
- Anything else: its errno (§b7).

A body arrives as `data` when present, else `content` encoded as UTF-8. `fd_readdir` serves the materialized listing with `.` and `..` and the cookie protocol, one `ls` per directory fd.

### b5. Staging, write-back and close

- `fd_read`, `fd_write`, `fd_seek`, `fd_tell` and `fd_filestat_set_size` work on the buffer. Nothing between open and close touches the database.
- `fd_close` of a dirty buffer is one `write`. `fd_sync` and `fd_datasync` flush now (one `write`) and return its errno, so a program that syncs sees a failure at the sync.
- **A refused write-back is never silent.** Every verb the shim issues records its classified errors in per-run state, beside the exit code. The close (or sync) returns the errno to the guest. The run's `Result` carries each error on the stage, path included. A run whose guest exited 0 but whose state holds a failed flush has stage status 1, and the shell writes one stderr line per failed path (`<program>: <path>: <phrase>`). Rust's `File` ignores errors on drop, so this is the only way such a program's caller learns. (Review probe `p3`: today the spike's shim exits 0 and leaves the file unchanged.)
- A program that exits or traps still flushes every dirty buffer. Its failures land in the `Result` the same way.
- **Write-back (ADR 085 pin 12).** An existing row keeps its source when the new body allows it: a text row stays text if the body is UTF-8 without NUL; a bytes row stays bytes. A new row is `content` when the body is UTF-8 without NUL and the extension is not on the binary list, else `data`. The binary list is the extensions the magic table and the renderer registry claim: `png`, `jpg`, `jpeg`, `gif`, `tif`, `tiff`, `webp`, `pdf`, `zip`, the OOXML extensions, and `wasm`. A body with a NUL is never `content` (`Entry` rejects it).

### b6. The other path calls

- `path_filestat_get` is one `stat`.
- `path_create_directory` is `mkdir`.
- `path_unlink_file` is a `stat` then `delete`; a directory is `EISDIR` before the `delete`.
- `path_remove_directory` is `delete(cascade=False)`, never a cascade.
- `path_rename` is `move(src, dest, overwrite=True)` (spec 167 adds `overwrite=`). A file destination is replaced and the replaced row is recoverable as 167 defines; a directory destination is `EISDIR` or `ENOTEMPTY` as POSIX says; `cross_mount` is `EXDEV`. (Review probe `p7`: today `move` onto an existing file is `vfs.exists`.)

### b7. The errno mapping

- `results/kinds.py` declares `WASI_ERRNO: Final[Mapping[ErrorKind, int]]` beside `ErrorKind`, in preview1 numbering, one value per kind. A drift test pins one entry for every kind, so a new kind gets its errno when it is minted.

  | Kind | errno |
  |---|---|
  | `not_found` | 44 `NOENT` |
  | `exists` | 20 `EXIST` |
  | `wrong_kind` | 54 `NOTDIR` (the shim picks 31 `ISDIR` per §b4) |
  | `not_empty` | 55 `NOTEMPTY` |
  | `unauthenticated`, `permission_denied` | 2 `ACCES` |
  | `read_only` | 69 `ROFS` |
  | `unsupported` | 58 `NOTSUP` |
  | `unrecognized` | 52 `NOSYS` |
  | `invalid`, `unindexable_pattern` | 28 `INVAL` |
  | `unaddressable` | 37 `NAMETOOLONG` |
  | `cross_mount` | 75 `XDEV` |
  | `busy` | 10 `BUSY` |
  | `conflict` | 72 `STALE` |
  | `budget_exhausted`, `truncated`, `authority_budget` | 29 `IO` |
  | `timeout` | 73 `TIMEDOUT` |
  | `cancelled` | 11 `CANCELED` |
  | `unavailable`, `backend_unavailable`, `schema_mismatch`, `internal` | 29 `IO` |

- The ladder reaches the guest as errno only. There are no mode bits.
- The staging budget answers 22 `FBIG` (§b8).

### b8. Run: executor, context, budgets, traps

- **One guest at a time per process** (Clay, decision 2). Guests run on one dedicated single-thread executor, and that executor is the serialization. A queued run waits as an asyncio task, never as a parked thread, and its wait counts against the line's deadline. The docstring says plainly that one guest runs at a time per process until wasmtime-py's trap global is thread-local, and names the Rust host in `crates/vfs-core` as the direction.
- **Context crosses the hand-off.** The worker runs under `contextvars.copy_context()`, so the hop budget, the line deadline and the session `path` (§a5) reach every verb the guest posts. Each verb is posted onto the event loop with `run_coroutine_threadsafe` and awaited with `future.result(timeout=remaining)`; on expiry it is cancelled and the run is a `timeout`.
- Per run: a fresh `Linker`, a `Store` with `set_limits(memory_size= MEMORY_BYTE_BUDGET)` (always; without it a guest takes host memory until wasm32's own 4 GiB ceiling), `set_fuel(FUEL_BUDGET)`, and an epoch deadline from the remaining line deadline; one ticker thread per engine. `Config.consume_fuel` and `Config.epoch_interruption` are both on.
- **The exit code** is recorded in per-run state before `proc_exit` raises. The embedder reads it from that state on any exception and never from the exception object.
- **Budgets.** `shell/budgets.py` declares a frozen `RunBudgets`: `FUEL_BUDGET` 2 × 10⁹, `MEMORY_BYTE_BUDGET` 256 MiB, `VERB_CALL_BUDGET` 10,000, `STAGING_BYTE_BUDGET` 256 MiB, and the line's wall budget. `VirtualFileSystem(shell_budgets=…)` and `cli(…, budgets=…)` may tighten it field by field; a looser value is `invalid`. Tests tighten through these seams. (A mount-level seam, ADR 084 pin 6, is not in this spec.)
- `STAGING_BYTE_BUDGET` bounds the sum of every open buffer plus stdin and stdout in one run, because staged buffers live in host memory outside the store limit. An open that would pass it is `FBIG`, judged on the read's `size_bytes`.
- **The verb budget.** At `VERB_CALL_BUDGET` dispatches the shim records `budget_exhausted` in per-run state and returns `NOTCAPABLE`; the next host call raises the recorded sentinel. A recorded kind wins over any later trap.
- **Traps and exit codes** (Clay, decision 3):

  | Cause | Kind | Stage exit |
  |---|---|---|
  | `TrapCode.INTERRUPT` (the epoch deadline) | `vfs.timeout` | 124 |
  | `TrapCode.OUT_OF_FUEL` | `vfs.budget_exhausted` | 137 |
  | the verb budget (recorded) | `vfs.budget_exhausted` | 137 |
  | any other trap (a guest abort) | none; the trap code rides in the stage's data | 134 |

  An out-of-memory guest is reported as the abort it is: the host cannot tell it from a panic (both are `UNREACHABLE`; review probe `p5`), and the store limit still bounds host memory. The guest's own stderr is kept. Stdout written before a kill is kept. `[NEEDS CLARIFICATION: Clay settled 137 and 124; is 134 (128 + SIGABRT) right for a guest abort? Leaning: yes.]`
- **Attribution.** The run's `Authority` is passed unchanged. There is no `source_identity` stamp and no attribution column (Clay, decision 5). The program's path and `content_hash` ride in the `Result` extras (`programs`), and 169c's record keeps them.

### b9. Load: the execute gate and the cache

- **Every run issues one gated `read`** of the program entry, even on a cache hit: `columns={content_hash, version, mime_type}`. This is ADR 084 pin 2 made literal: `permission_denied` here is 126. Its hash keys the cache.
- On a miss, a second `read` with `columns={data}` fetches the body. If its hash differs from the first, the program changed between the two; the load retries once.
- **The key** is `(wasmtime version, config fingerprint, content_hash)`. The fingerprint includes epoch interruption and fuel: a fuel engine refuses a module compiled without fuel, so a key without it turns every hit into a load failure (review probe `p5`).
- **The directory and its trust.** `VirtualFileSystem( wasm_cache_dir=…)` sets it; the default is a per-user cache directory (`$XDG_CACHE_HOME/vfs/wasm`, else `~/.cache/vfs/wasm`), created `0700`. `Module.deserialize_file` trusts its input, so a directory another user can write is host code execution: the host refuses a directory it does not own or that others can write. Files are written to a temporary name and renamed into place. A file that fails to deserialize is deleted and recompiled.
- Eviction is least-recently-used beyond `WASM_CACHE_BYTE_BUDGET` (1 GiB). That is a cache bound, not a scale cap.

### b10. The pipe: a bytes-to-bytes stage (ADR 083)

- A stored program consumes and produces bytes. The shell renders incoming rows to text with the placeholder for media; a program that wants a file's bytes opens it (`path_open`).
- **At v1 a wasm stage materializes** its stdin (bounded by the upstream's `STDOUT_BYTE_BUDGET`) and its stdout (bounded by its own, with spec 167's truncation warning). Stdout is lifted into one row at the end (ADR 083 pin 6). The docstring names streaming `fd_read` over the stage queue as the next step.
- **Early close** (`prog | head -1`) sets a cancel flag in per-run state; the next host call raises the recorded sentinel, and the stage reports `cancelled` as info.

### Acceptance criteria (169b)

Counted with spies; the clock is only ever a kill switch.

1. `upper /data/in.txt /data/out.txt`, first run: verb calls `{stat 2, read 3, write 1}` (one resolution `stat`, the gate `read`, the body `read` on the miss, the input `read`, the output `stat`, the close `write`) and one compile. Second run: `{stat 2, read 2, write 1}` and zero compiles. The output row is at version 1, then 2.
2. `upper` run by a caller who may read but not write `/data`: the close returns `ACCES` to the guest; stage status 1 although the guest exited 0; one `permission_denied` error on `/data/out.txt`; the file unchanged.
3. A relative `upper in.txt out.txt` from `cwd=/data` reads `/data/in.txt`. A guest `rm` lands in `/.vfs/trash`. A guest `rmdir` on a non-empty directory is `ENOTEMPTY`. From `cwd=/`, a guest `../../etc/passwd` is `NOTCAPABLE` with zero verb calls. A guest open of `/.vfs/trash` is `ENOENT` with zero verb calls.
4. The `wrong_kind` cases of §b4: a directory opened for read is a directory fd; opened for write, `EISDIR`; a path under a file, `ENOTDIR`; a create under a missing parent, `ENOENT` at open.
5. A guest renaming a temporary file over an existing one replaces it in one `move`.
6. A WAT spin loop under a tightened fuel budget is killed with `budget_exhausted`, exit 137, having consumed exactly that budget. A spin loop under a tightened wall budget is `timeout`, exit 124 (marked `slow`). A guest over a tightened verb budget is `budget_exhausted`, exit 137, after exactly that many verbs. A greedy guest exits 134 and every store was given the memory limit (spied). Stdout written before each kill is kept.
7. A caller holding `list` on a program whose module is already cached gets 126: one `read` refused, zero deserializes.
8. A same-bytes reinstall advances the version and hits the cache (zero compiles). A fuel-off fingerprint and a fuel-on fingerprint are two keys. A corrupt cache file is deleted and recompiled once.
9. A unit test raises a foreign exception object out of `_start`, and the exit code is read from per-run state. Two concurrent `cli` calls in one process each get their own exit code and both complete.
10. A guest's verbs see the caller's remaining hop budget and session `path` (the context crossed the hand-off; spied).
11. The write-back table: a UTF-8 `.txt` is `content`; a UTF-8 `.png` is `data`; UTF-8 with a NUL is `data`; an existing bytes row stays bytes.
12. `WASI_ERRNO` has one entry per `ErrorKind` (drift test).
13. `prog | head -1` stops the guest: the stage reports `cancelled` as info and the guest issues no host verb after the cancel.
14. `scripts/ci.sh` green at 100%; the four engine legs green.

---

## 169c — The `/.vfs/run` view

### c1. The record

- Every `cli` call that runs at least one stage gets a call id (a ULID) and a record under `/.vfs/run/<call-id>/`:
  - `stdout`: the call's output row (ADR 083 pin 6), as already addressed.
  - `status`: a JSON row with the command, and per stage the program name, `callable_kind`, `resolved` path, `content_hash`, exit code and status; plus the stderr text.
- This record is the attribution of program runs at v1 (Clay, decision 5).
- **Store and owner.** Records live in a router-memory ring keyed by the exact `Authority` value: `RUN_RETENTION_CALLS` (64) calls per authority, each row capped at `STDOUT_BYTE_BUDGET`, and `RUN_RETENTION_BYTES` (64 MiB) across all authorities, evicting the least recently used. Only an equal `Authority` reads a record; any other caller gets `not_found`. `ls /.vfs/run` lists the caller's records, newest first.
- **Lifetime.** Records are lost on restart and are not shared across processes; the docstring says so. Persisting them is a named future, not a cap.
- Verbs: `stat`, `ls`, `read` (§a2).

### Acceptance criteria (169c)

1. After `cat /data/a.txt | upper`, `read /.vfs/run/<id>/stdout` returns the output and `read /.vfs/run/<id>/status` names `/opt/bin/upper.wasm` and its `content_hash`.
2. Another authority's `read` of the same record is `not_found`.
3. The 65th call evicts the first for that authority (counted); the byte budget evicts across authorities (counted).
4. `scripts/ci.sh` green at 100%.

---

## Lands after spec 171 — the first programs

- **`vfs install`** is a host command on spec 171's CLI. It runs as the host (the system actor), fetches a pinned release asset, verifies its hash, and writes it into `/opt/bin`.
- **uutils coreutils**: the `feat_wasm` set built for `wasm32-wasip1` in CI and shipped as one `coreutils.wasm` multicall binary. The kernel table's names win; the wasm set serves names no kernel has yet (`pr`, `fmt`, `tsort`, `numfmt`, `shuf`, `csplit`, …). This section decides the multicall rule: how `pr` resolves to `coreutils.wasm` and which argv[0] the guest sees (vfs has no links).
- **jaq** (MIT) built the same way as `/opt/bin/jq.wasm`. `jq` is a kernel name (spec 168), so a host lists it in `prefer_stored` to install and promote it. The criterion `cat /data/users.json | jq '.users[].name'` runs through the installed jaq with zero verbs from the guest (`cat` issues its own one `read`).
- **A wasi awk**, chosen by licence and by whether its dependency closure builds for `wasm32-wasip1` (study 10 §2's filter: no C allocator, no file lock, no REPL).
- The CI job that builds these guests and publishes their assets and hashes.

## Scope

In: 169a, 169b, 169c as above. Out: tools and MCP views (170); the MCP wire and the CLI (171); guest interpreters (172); the first programs (the section above, after 171); a union create (`bind -c`); the Rust host; jobs; streaming wasm stages; chunked reads of large bytes rows (named future); a mount-level budget seam.

## Landing notes

(Filled in on landing.)
