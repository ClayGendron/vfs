# Review of spec 169 — programs, the index and the `/.vfs` views

- **Date:** 2026-10-15
- **Reviewer:** pre-build review, read as the developer who must build it. Tree at `main` (`ac5c515`), working tree as found. Nothing under `src/`, `tests/` or the spec was modified.
- **What I read:** spec 169 (all 193 lines); its parent spec 167; ADR 082 pins 6–12, ADR 084 pins 2, 5, 7, 8, ADR 083 pin 6, ADR 085 pin 12, and ADR 063 and ADR 064 where the spec touches them; the memo §5, §6, §8, §12; studies 03, 04, 06, 10; the executed shims `experiments/e1/shim/{vfs_wasi.py,host.py}` and `experiments/s4/shim.py`; the live tree: `paths.py`, `base.py` (routing, `bind`, `add_mount`, `MountMeta`, `_validate_deny_ops`, `_gate_entry`, `_route_entry_batch`, the hop budget), `storage/backends/database/{trash.py,reads.py,descent.py}`, `skills.py`, `models/media.py`, `models/entry.py`, `models/rows.py`, `authority.py`, `results/kinds.py`, `pyproject.toml`.
- **Evidence labels:** **EXECUTED** (a script ran against the live tree; script and output sit in `experiments/r169/`), **READ** (file read, `file:line`), **INFERRED** (my reasoning from the two).
- **Probes:** `p1_routing`, `p2_install_and_gates`, `p4_fold_classification`, `p6_suffixless`, `p7_rename_over` run with `uv run python`. `p3_silent_writeback` and `p5_trap_classifier` need wasmtime, which is not a dependency, so they run with `uv run --with wasmtime python`. `p3` drives the E1 spike's own shim and host with no changes.

## Readiness score: 47 / 100

| # | Dimension | Score | Why, in one line |
|---|---|---|---|
| 1 | Intent and scope | 7 / 10 | The intent paragraph is sharp. The scope is four landings in one. |
| 2 | Fidelity to the ADRs and the research | 9 / 15 | Mostly faithful. It drops study 06's bin posture, the spike's stub set, ADR 084's `FUEL_BUDGET`, and it bends ADR 064. |
| 3 | Buildable against the live tree | 7 / 20 | §1 names no routing mechanism, and the live router has no seam for one. The union's columns do not fit `Observation`. |
| 4 | Contract precision | 6 / 15 | The open fold, the errno table, the write-back rule, the trap classes and the attribution are each loose or wrong. |
| 5 | Authority and safety | 5 / 10 | A refused write-back is lost silently. Any principal can plant a program every other principal runs as themselves. |
| 6 | Scale and production posture | 5 / 10 | One guest per process. Resolution by `ls` of a whole bin directory. `/.vfs/run` has no store. |
| 7 | Acceptance criteria testable by counts | 5 / 10 | Criterion 3's counts contradict §4. Criterion 5's memory case cannot be told apart. No tightening seam for tests. |
| 8 | Slicing and landability | 3 / 10 | §5 needs spec 171's CLI and contradicts §3. Nothing can land green as one piece. |

## Findings, most severe first

### 1. §1 has no routing mechanism, and the live router has nowhere to put one — **blocking**

- **Spec lines 44–47:** "The router serves the namespace views at the root."
- **Problem.** Today `/.vfs/...` is not a view at the root. It is an ordinary stored subtree of the root storage. The router sends it there by longest prefix like any other path. Nothing in the router intercepts it.
- **Evidence.**
  - EXECUTED `p1_routing.out`: `locate("/.vfs/bin/jq")` answers `mount=/ storage_path=/.vfs/bin/jq`. `write /.vfs/bin/x.wasm` succeeds. `mkdir /.vfs/skills` succeeds. After that, `ls /.vfs` lists the stored `bin` and `skills` rows beside the synthesized `trash`.
  - EXECUTED: on a fresh node, `ls /.vfs` and `stat /.vfs` are `not_found`, and so is `ls /data/.vfs` at a mount. Only `ls /.vfs/trash` works. READ `reads.py:229`: the meta root lists only when a row is stored there, and only then gets the trash head added (`_with_trash_view`, `reads.py:960`). So criterion 1 fails today even for `trash`.
  - READ `paths.py:810-840`: `check_mutable_path` says "every other path, the meta scope included, is a lawful write target". Only `/.vfs` itself and paths beneath the trash head are refused.
  - READ `base.py:2755-2760`: `_match_mount` walks `_bindings` only. `base.py:822-844`: a mount path may not contain the `.vfs` segment. EXECUTED: `bind(..., "/.vfs/bin")` raises "Mount path may not use the reserved metadata segment".
- **Router code or a synthetic storage?** I weighed three shapes.
  - *A `ViewStorage` bound into `_bindings` at `/.vfs/bin`.* It fails on five counts. `_normalize_mount_path` refuses the path. `bind` probes for a stored empty directory at the site. `mounts()` would list it, and its rows are meant to be replayable. `_bindings_beneath("/")` would hand it every unscoped `glob` and `grep`, breaking the meta-hidden rule. `with_mount` would rebase any source path carried in `edge_target`.
  - *Special cases in each route helper.* There are at least nine helpers (`_route_single`, `_dispatch_grouped_observations`, `_route_fanout`, `_route_two_path`, `_route_pairs`, `_route_entry_batch`, `_route_edge_batch`, `_tree_region`, `_route_grant`, plus `locate`). That is shotgun surgery.
  - *A router-owned view table consulted by `_match_mount` (proposed).* Every helper already resolves through `_match_mount`/`_resolve_terminal`. So one lookup there routes every verb. The table is not `_bindings`, so `mounts()`, `bind`, the busy guard and `_bindings_beneath` never see it. Unscoped fan-outs never reach a view. That is the meta-hidden rule by construction. The capability gate then gives `unsupported` for any verb a view does not serve.
- **Amendment (spec text, replaces lines 44–47).**
  > "The router keeps a second table, `_views: dict[Path, Binding]`, keyed by head path (`/.vfs/bin`, `/.vfs/skills`, `/.vfs/run`). It is separate from the mount table. `_match_mount` consults it first, for a path equal to a head or beneath one, at the root only. `mounts()`, `bind`, `unbind`, the busy guard and `_bindings_beneath` never read it. A view is an object with the read protocol; its `meta.caps` is the verb list below; it is built at construction and never owned by `close()`. A view answers each call by re-entering the router's public verbs with the call's authority, so every gate fires and the hop budget counts the re-entry.
  >
  > `check_mutable_path` refuses every path strictly beneath `/.vfs/`, except the trash head for `sweep`. This holds in global and in mount coordinates, so `/data/.vfs/bin/x` is refused too. The router adds the detail naming the index's writable directories; `resolve_path` stays index-blind.
  >
  > The database backend synthesizes its meta root. `stat /.vfs` is a directory and `ls /.vfs` lists `trash`, whether or not a row is stored there. At the root, the router appends its own served heads (`bin`, `skills`, `run`) to the root storage's answer. Reserved, unserved heads (`sessions`, `jobs`, and `tools`, `mcp` until spec 170) do not list; a read of one is `not_found`; a write is `invalid`.
  >
  > Verbs per head. `bin`: `stat`, `ls`, `glob`, `read` (a read forwards to the source row). `skills`: `stat`, `ls`, `tree`, `glob`, `grep`, `read` (beneath a unit, a path forwards to the same path under the unit's source). `run`: `stat`, `ls`, `read`. Every other verb is `unsupported` by the capability gate. Mutations are `invalid` before it."
- **Legacy rows.** No production data exists. Say so: "no stored row lives beneath `/.vfs`; the write refusal makes it an invariant from this landing on."

### 2. The union's columns do not fit `Observation` — **blocking**

- **Spec lines 49–52:** columns `kind` (`program`, `tool`, `mcp`) and `source` (the real path).
- **Problem.** Both names are taken, with other types. `Observation.kind` is `ObjectKind = Literal["file", "directory"]`. `Observation.source` is `Source = Literal["text", "bytes"]`. Both are mirror fields pinned to `Entry` by a drift test. So `kind="program"` and `source="/opt/bin/upper.wasm"` fail validation.
- **Evidence.** READ `models/entry.py:393-444` (the fields), `entry.py:504` (`OBSERVATION_QUERY_FIELDS`), and the mirror-owner map below it. READ `models/media.py` (`Source`).
- **Amendment.**
  > "A union row is `kind="file"` (or `"directory"` for a skill unit) at its view address (`/.vfs/bin/jq`). Two new query fields carry the rest: `callable_kind: Literal["program", "tool", "mcp", "skill"] | None` and `resolved: Path | None` (the source path, in router coordinates). Both join `OBSERVATION_QUERY_FIELDS`, the projection allow-list, the renderer's `ls -l` columns and `to_payload`. `with_mount` and `without_mount` never touch `resolved`. The source row's own fields (`version`, `size_bytes`, `mime_type`, `content_hash`, `updated_at`) ride under their own names, at the source row's projection for this caller: a caller holding `list` on the source sees the union row bare (`path`, `kind`, `callable_kind`)."
- EXECUTED `p2_install_and_gates.out`: bob, holding `list` on `/opt/bin`, gets `populated=['kind', 'path']` from `stat` and `ls`. The union must not show him more than that.

### 3. A refused write-back is lost: the guest exits 0 and the file is unchanged — **blocking**

- **Spec lines 109–111:** "`fd_close` of a dirty buffer is one `write`; a program that exits or traps still flushes every dirty buffer."
- **Problem.** Whole-file staging moves every write error to `fd_close`. Rust's `std::fs::File` ignores errors on close when it drops. So a refused `write` never reaches the program. The program prints success and exits 0. The flush after exit or trap has no program left to tell.
- **Evidence.** EXECUTED `p3_silent_writeback.out` (the E1 shim and host, unchanged). Bob may read `/data` but not write it. `upper /data/in.txt /data/out.txt` as bob: `exit=0 stdout=b'2\n'`. `/data/out.txt` is still `'untouched\n'`, version 1. The same `write` called directly as bob is `vfs.permission_denied`.
- **The fold makes it worse.** In study 04's fold (`s4/shim.py:323-331`), an `O_CREAT|O_TRUNC` open costs zero verbs. An `O_CREAT` open of a name whose parent is missing stages an empty buffer. EXECUTED `p4_fold_classification.out`: `read /nodir/x.txt` is `not_found` with `path=/nodir` (the parent), not the target. Both cases fail only at close, silently.
- **Amendment (spec text).**
  > "Every verb the shim issues records its classified errors in per-run state, beside the exit code. The run's `Result` carries them as errors on the stage, path included. A run whose guest exited 0 but whose state holds a failed flush has stage status 1, and the shell writes one stderr line per failed path (`<program>: <path>: <phrase>`). `fd_sync` and `fd_datasync` flush the buffer now (one `write`) and return its errno, so a program that syncs sees the failure. A create open (`O_CREAT`) whose read misses checks that the miss names the target itself (`error.path == target`); a miss at an ancestor is `ENOENT` at open, as POSIX says."
- **Add criterion:** "`upper` run by a caller without write on the output: stage status 1, one `permission_denied` error on the output path, the file unchanged."

### 4. §4 restates the open fold wrongly, and criterion 3's counts contradict it — **blocking**

- **Spec lines 105–108 vs 172–175.** §4 says `path_open` is one `read`, classified from its error. Criterion 3 then asks for `{ls 1, read 2, stat 2, write 1}` on the first run. Those are the spike's *unfolded* counts: a `stat` before every `read` and every `write` (study 10 §4a). Under §4's own fold there is no `stat` at open. A developer cannot satisfy both.
- **Evidence.**
  - READ `e1/shim/vfs_wasi.py:542-577`: the E1 shim stats first, then reads. READ `s4/shim.py:298-343`: the S4 fold has four branches, not two. `O_DIRECTORY` is one `ls`. `O_EXCL` is one `stat`. `O_CREAT|O_TRUNC` is zero verbs. Anything else is one `read`. On `wrong_kind` it answers `EISDIR` when the open asks to write.
  - EXECUTED `p4_fold_classification.out`: `wrong_kind` means two different things. `read /data/sub` gives `path=/data/sub, data={'kind': 'directory'}` (the target is a directory). `read /data/in.txt/child` gives `path=/data/in.txt, data={'kind': 'file', ...}` (an ancestor is a file). Only the first is a directory open.
- **Amendment (replaces lines 105–108).**
  > "`path_open` costs at most one verb. `O_DIRECTORY`: one `ls`, materialized into the fd. `O_CREAT|O_EXCL`: one `stat`; `exists` is `EEXIST`. `O_CREAT|O_TRUNC`: one `stat` (no body), so a directory, a missing parent or a hidden name is known at open. Otherwise: one `read` with `columns={content, data, kind, size_bytes, mime_type, version}`. Classify its error: `not_found` at the target is `ENOENT`, or an empty dirty buffer under `O_CREAT`; `not_found` at an ancestor is `ENOENT`; `wrong_kind` with `error.path == target` and `data.kind == "directory"` is a directory open (`EISDIR` if the rights ask to write, else the `ls` happens at the first `fd_readdir`); any other `wrong_kind` is `ENOTDIR`."
- **Amend criterion 3** to the honest counts. Resolution by one batched `stat` (finding 15). The program load by one `read` (finding 8). Then `in.txt` by one `read`, `out.txt` by one `stat` and one `write`. With `O_CREAT|O_TRUNC` as one `stat` and finding 8's gate `read` plus a body `read` on a miss, that gives: "first run `{stat 2, read 3, write 1}` and one compile; second run `{stat 2, read 2, write 1}` and zero compiles." Count compiles with a spy on the cache-miss path.

### 5. §3 refuses what §5 installs; §5 is not buildable here — **blocking**

- **Spec lines 93–94** ("Installing over a kernel name is `invalid`") **vs 153–155** (`jaq` installed as `/opt/bin/jq.wasm`) and **line 73** (`prefer_stored=("sed",)`).
- **Problem.** `jq` is a kernel name. READ spec 168 line 59: "`jq` (forms) … the full language arrives as a wasm program (spec 169)". So §3 refuses §5's own install. `prefer_stored` also has nothing to promote: the stored entry it names can never be written.
- **Three more gaps in §5.**
  - `coreutils.wasm` is one multicall binary. Nothing says how `pr` or `fmt` resolve to it, or what argv[0] the guest sees. vfs has no links (`path_link` is a stub).
  - `vfs install coreutils` is a console command. vfs has no console script today (READ `pyproject.toml`). Spec 171 brings `vfs serve`, and 171 says it is "independent of 168–170".
  - Building uutils and jaq for `wasm32-wasip1` in CI is a new CI job and a release-asset story (study 10 §2: jaq 3.1 failed twice before 1.6 built).
- **Amendment.**
  > "The install refusal covers only a name that is in the kernel table and not in `Index.prefer_stored`, and it fires in the router's mutation gate for `write`, `copy` and `move` whose destination is `<an indexed program directory>/<name>.<runtime suffix>`. `add_index_path` is never refused; resolution still never serves an unpromoted kernel name."
  >
  > Move §5 to its own spec, after 171. It owns the CI build, the release asset and its hash, the `vfs install` command, and a multicall rule (for example, a stored alias row whose content names the binary and the argv[0] it passes).
- If Clay prefers to drop the write-time refusal, see question 4.

### 6. The trap classes in §4 cannot be built; `FUEL_BUDGET` is missing — **blocking**

- **Spec lines 130–132:** "`TrapCode` classifies `timeout` (INTERRUPT) from `budget_exhausted` (UNREACHABLE after an allocation failure, MEMORY_OUT_OF_BOUNDS)." **Criterion 5:** "a greedy one trips `budget_exhausted`".
- **Problem 1.** The host cannot tell "hit the memory budget" from "the guest aborted". Both are `UNREACHABLE`. A Rust panic, an `unwrap` on `None` and an out-of-memory abort all look the same. The only difference is the guest's stderr text, and the house rule is never to classify by message. `MEMORY_OUT_OF_BOUNDS` is a guest bug, not a budget.
- **Evidence.** EXECUTED `p5_trap_classifier.out`. `alloc` under a 32 MiB limit: `trap UNREACHABLE`, memory at trap 16,842,752 bytes. That is *not* near the cap, because the Rust vector asked to double. A WAT `unreachable` at 64 KiB: `trap UNREACHABLE` too. A "near the cap" heuristic fails. Study 10 §5 already marked a `ResourceLimiter` from Python as not verified.
- **Problem 2.** ADR 084 pin 5 declares `FUEL_BUDGET` 2 × 10⁹. §4 never wires it. Fuel is exact. EXECUTED: a spin loop under fuel 1,000,000 traps `OUT_OF_FUEL` having consumed exactly 1,000,000; under 2,000,000, exactly 2,000,000. That is a count, which is what tests should assert. Also EXECUTED: a module compiled without fuel is refused by a fuel engine ("compiled without fuel support but it is enabled"). So the fuel flag must be in the cache key, or every cache hit becomes a load failure.
- **Amendment (replaces lines 130–132).**
  > "`Config.consume_fuel` is on and every store gets `set_fuel(FUEL_BUDGET)`. Classes: `INTERRUPT` is `vfs.timeout` (exit 124). `OUT_OF_FUEL` is `vfs.budget_exhausted` (its exit code is question 3). The verb budget is `vfs.budget_exhausted`. Every other trap is a guest abort: exit 134, the trap code in the stage's data, the guest's own stderr kept. An out-of-memory guest is reported as the abort it is; the store limit still bounds host memory."
- **Amend criterion 5:** "A spinning program under a tightened fuel budget trips `budget_exhausted` having consumed exactly that budget (counted). A spinning program under a tightened wall budget trips `timeout` (marked `slow`). A greedy program under the memory budget exits 134 and the host process's memory stays bounded. A program over the verb budget trips `budget_exhausted` after exactly `VERB_CALL_BUDGET` verbs." Name the exit code for `budget_exhausted` in `shell/status.py` (167 owns the table).

### 7. One preopen `/` ignores the shell's `cwd` — **should fix**

- **Spec lines 102–103:** "one preopen `/`; `fd_prestat_get(4)` answers `BADF`".
- **Problem.** wasi-libc resolves a relative path against the first preopen. With only `/`, a guest started in `cwd=/data` opens `rel.txt` as `/rel.txt`. Spec 167 §6 gives the session a `cwd`, and agents type relative paths.
- **Evidence.** READ study 04 line 45 (EXECUTED there): "a relative guest path `data/hello.txt` arrived identically (wasi-libc's cwd is the first preopen; `std::env::current_dir()` printed `"/"`)". The spike passed only absolute paths (study 10 §4a).
- **Amendment.**
  > "Two preopens: fd 3 is `/`, fd 4 is `.` bound to the call's `cwd` (wasmtime's own `--dir .` shape). `fd_prestat_get(5)` answers `BADF`. `..` may climb from the `cwd` preopen to `/`; a path that climbs above `/` is `NOTCAPABLE` before any verb."
- Criterion 4's "`../../etc/passwd` answers `NOTCAPABLE` with zero verb calls" then holds only from `cwd=/`. Say "from `cwd=/`".

### 8. The cache: the execute gate must not depend on a cache miss; the key, the place and the trust are loose — **should fix**

- **Spec lines 138–140.**
- **Problem 1: the gate.** ADR 084 pin 2: executing is `read` on the entry. The spike's loader skips `read` on a cache hit (READ `e1/shim/host.py:132-136`: `if key.exists(): return Module.deserialize_file(...)`). EXECUTED `p3`: a caller with only `list` on `/bin` still failed, but only because a `list` row carries no `version`. So the key could not be formed. The gate held by accident of projection. And keying on a hash read at resolution time leaves a gap between resolve and run.
- **Problem 2: the key.** Finding 6 shows the fuel flag must be in it.
- **Problem 3: "the scratch root" is not defined.** No scratch root exists in the live tree. `Module.deserialize_file` trusts the file. wasmtime documents deserialize as unsafe on untrusted input: a file someone else can write is host code execution. Concurrent writers need an atomic rename. A cache with no bound grows by about 9 MB per jaq version (study 10 §6).
- **Evidence.** EXECUTED `p2`: `read(columns={"content_hash", "version"})` is gated at `read` and fetches no body. Bob at `list` gets `permission_denied`; at `read` he gets the hash and version.
- **Amendment (replaces lines 138–140).**
  > "Every execution issues one gated `read` of the program entry: `columns={content_hash, version, mime_type}`. Its hash keys the cache. On a miss, a second `read` with `columns={data}` fetches the body; the run stops if that read's hash differs from the first (the program changed under us; retry once). Key: `(wasmtime version, config fingerprint including epoch interruption and fuel, content_hash)`. The cache directory is a constructor argument of the host (default: a per-user cache directory created `0700`); files are written to a temporary name and renamed into place; a file that fails to deserialize is deleted and recompiled. Eviction is least-recently-used beyond a declared byte budget, and that budget is a cache bound, not a scale cap."

### 9. The process-wide guest lock serializes every program in a server process — **should fix**

- **Spec lines 132–135.**
- **Problem.** Production runs many agents in one process. Under this rule one guest runs at a time, and the lock is held across the guest's verb I/O (database round trips). The spec does not say whether time spent waiting for the lock counts against the line's deadline. If it does, a busy process times out programs that never ran. If it does not, latency has no bound. A lock taken inside `run_in_executor` workers also parks a default-executor thread per waiting run.
- **Also:** `loop.run_in_executor` does not copy context variables. READ `e1/shim/host.py:203`. The hop budget is a `ContextVar` (READ `base.py:2723-2743`). So a guest's verbs run with a fresh hop budget, and any per-line deadline kept in a context variable is lost too.
- **Also:** criterion 7 ("8,000 of 8,000") cannot fail under a lock. It tests the lock, not the recorded-exit rule.
- **Evidence.** READ study 04 (the handle-slab race in the 49.0.0 wheel) and study 10 §7 (13.4% wrong exit codes without the recorded-state rule). The lock is justified today. The spec should say what it costs.
- **Amendment.**
  > "Guests run on one dedicated single-thread executor; that executor is the serialization. A queued run waits as an asyncio task, never as a parked thread, and its wait counts against the line's `WALL_TIME_BUDGET`. The worker runs under `contextvars.copy_context()`, so the hop budget and the deadline cross the thread hop. The docstring says plainly that one guest runs at a time per process, until wasmtime-py's trap global is thread-local or the Rust host lands."
- **Replace criterion 7:** "(a) A unit test raises a foreign exception object out of `_start` and the exit code is read from per-run state. (b) Two concurrent `cli` calls in one process each get their own exit code and both complete (counted)."

### 10. The stub list diverges from what ran — **should fix**

- **Spec lines 100–102:** "the 24 functions real …, `path_link` and the rest as `NOTSUP`/`NOSYS` stubs".
- **Problem.** The spike ran 35 real and 11 stubs (study 10 §10). Study 04's table sets `fd_sync` and `fd_datasync` to success and names a clock-only `poll_oneoff` as "the honest minimum" (study 04 lines 228, 232). Under the spec's list these become `NOTSUP`: `fd_sync`, `fd_datasync`, `fd_advise`, `fd_fdstat_set_flags`, `fd_filestat_set_times`, `fd_renumber`, `fd_pread`, `fd_pwrite`, `sched_yield`, `clock_res_get`, `poll_oneoff`. A Rust program that calls `sync_all` would then fail. So would `touch`-like tools that set times, and anything that sleeps (`std::thread::sleep` uses `poll_oneoff` on wasip1). The spike's six binaries never hit a stub, but uutils is about a hundred programs.
- **Amendment.**
  > "Real: the spike's 35. `fd_sync`/`fd_datasync` flush (finding 3). `fd_filestat_set_times` and `path_filestat_set_times` accept and ignore (vfs stamps its own `updated_at`). `poll_oneoff` serves clock subscriptions only, bounded by the remaining deadline, and answers `NOTSUP` for fd subscriptions. Stubs (`NOTSUP`): `fd_allocate`, `path_link`, `path_readlink`, `path_symlink`, `proc_raise`, the four `sock_*`. Stubs always return an int and never raise."

### 11. `path_rename` over an existing file fails — **should fix**

- **Spec line 115–116:** "`path_rename` is `move`".
- **Problem.** POSIX `rename` replaces an existing destination file. vfs `move` never replaces. Many tools write a temporary file and rename it over the target.
- **Evidence.** EXECUTED `p7_rename_over.out`: `move("/d/.out.txt.tmp", "/d/out.txt")` is `vfs.exists`. The target keeps `"old"`.
- **Amendment.**
  > "`path_rename` onto an existing file is `delete(dest)` then `move` (two verbs; the old body lands in the trash, so the replace is recoverable). Onto an existing directory it is `EISDIR` or `ENOTEMPTY` as POSIX says. `cross_mount` is `EXDEV`."

### 12. The write-back rule is undefined at its edges — **should fix**

- **Spec lines 120–121:** "UTF-8 with the extension agreeing is `content=`, else `data=`".
- **Problem.** "The extension agreeing" names no table. And text with a NUL byte cannot be `content`: `Entry` rejects it (READ `entry.py`, `_reject_null_bytes`). ADR 083 pin 6 already says "valid UTF-8 without NUL". Without that clause the `write` fails `invalid` at close and is lost (finding 3).
- **Amendment.**
  > "An existing row keeps its source when the new body allows it: a text row stays text if the body is UTF-8 without NUL; a bytes row stays bytes. A new row is `content` when the body is UTF-8 without NUL and the extension is not on the binary list (the extensions `_MAGIC` and the renderer registry claim: `png`, `jpg`, `gif`, `tiff`, `webp`, `pdf`, `zip`, the OOXML set, `wasm`); else `data`."

### 13. Attribution through `source_identity` breaks ADR 064 and overflows its column — **should fix**

- **Spec lines 136–137:** "the run's `Authority` unchanged, with the program's path and `content_hash` stamped in `source_identity`".
- **Problems.** (a) "Unchanged" and "stamped" contradict. `Authority` is frozen; stamping makes a new one. (b) ADR 064 rule 3: `source_identity` is "set once at the edge and inherited by every sub-session" and "records who started the chain". Overwriting it erases the edge identity. (c) READ `rows.py:546`: the column is `_string(255)`. A path is up to 1,024 bytes (`paths.py`, `MAX_PATH_LENGTH`) plus 64 hex characters of hash. SQLite does not enforce the length. Postgres, SQL Server and Oracle do. That is a design that only works on SQLite.
- **Amendment.**
  > "The run's `Authority` is passed unchanged. The version row gains one column, `program_hash` (`String(64)`, nullable): the content hash of the program whose run wrote the version. The path is not stored; the hash names the bytes. This is the spec's one schema change, and it bumps the format." Or, if Clay prefers no schema change: "attribution of program runs is deferred; the run's audit lives in the `Result` extras." (Question 5.)

### 14. "The `ErrorKind` table carries each kind's errno" — it does not yet — **should fix**

- **Spec lines 117–119.**
- **Problem.** The errno lives only in comments (READ `results/kinds.py:57-90`). Some comments name two (`wrong_kind`: ENOTDIR / EISDIR; `permission_denied`: EACCES / EPERM). Some name a non-errno (`unauthenticated`: "401"). The spike mapped `cross_mount` to `NOTCAPABLE` (READ `e1/shim/vfs_wasi.py:45-55`); the comment and the spec say EXDEV; the S4 shim says EXDEV.
- **Amendment.**
  > "`KindContract` gains `wasi_errno: int`, in preview1 numbering, with one value per kind: `not_found` 44, `exists` 20, `wrong_kind` 54 (the shim picks 31 when the target is a directory opened for write), `not_empty` 55, `unauthenticated` and `permission_denied` 2, `read_only` 69, `unsupported` 58, `unrecognized` 52, `invalid` 28, `unaddressable` 37, `cross_mount` 75, `busy` 10, `conflict` 72, `budget_exhausted` 29, `timeout` 73, `cancelled` 11, `unavailable` and `internal` 29. A drift test pins one value per kind."

### 15. Resolution by `ls` does not scale, and the resolution unit is unstated — **should fix**

- **Spec lines 53–54** ("Resolution and listing run `stat` and `ls`").
- **Problem.** The spike resolved with one `ls` of the whole bin directory per command (READ `e1/shim/host.py:118-128`). A bin directory of 10,000 programs makes every command fetch 10,000 rows. The index can span mounts and several suffixes.
- **Amendment.**
  > "Resolving one name is one `stat(observations=…)` over the candidates in order: each index directory (session prefix first) × each runtime suffix. The router groups it per mount, so it is one dispatch per mount and bounded by `dirs × suffixes`, never by directory size. The first visible hit wins. Listing `/.vfs/bin` is one `ls` per index directory; its cost grows with the directories, and the docstring says so."

### 16. Any principal can plant a program every other principal runs as themselves — **should fix (product choice)**

- **Spec lines 66–69, 81–84, 88–93.**
- **Problem.** A program runs as its *caller*. So whoever can write an indexed directory chooses code that runs with every caller's rights. Kernel names are protected; every other name is not. With `prefer_stored=("sed",)`, `sed` is not protected either. A fresh mount's default posture is `read_write` (READ `storage/backends/database/backend.py:205`). Study 06 F5 leaned "`read` for everyone" on the bin directory (Plan 9's `r-x`); the spec dropped it. And if `/opt/bin` is minted by the first agent `write`, that agent owns the directory.
- **Evidence.** EXECUTED `p2`: under the default open posture, bob overwrites ann's `/opt/bin/x.wasm` (version 2). Spec 169 sets no posture on `/opt/bin`.
- **Amendment (if Clay agrees, question 1).**
  > "At construction the node mints each configured program and skill directory as the system actor, with posture `read` when the governing posture is wider. Installing needs a grant (`add` or more) on the directory. `ls /.vfs/bin` is empty until the first install." This also answers the second `[NEEDS CLARIFICATION]`.

### 17. `/.vfs/run` has no store, owner or lifetime — **should fix**

- **Spec lines 58–60.**
- **Problem.** The router has no session. `cli(authority=…)` may be called with no session at all. The spec does not say where output rows live, who may read them (any principal who guesses a call id?), how a call id is minted, or what happens in a second worker process.
- **Amendment.** Either move `/.vfs/run` to a later slice, or pin a minimum:
  > "Output rows live in a router-memory ring keyed by the exact `Authority` value: `RUN_RETENTION_CALLS` calls, each row capped at `STDOUT_BYTE_BUDGET`. Only an equal `Authority` reads them; any other caller gets `not_found`. Call ids are ULIDs. Rows are lost on restart and are not shared across processes; the docstring says so."

### 18. The session `path` cannot reach `/.vfs/bin` — **should fix**

- **Spec line 71** puts the session prefix in the resolution order. **Line 48** serves `/.vfs/bin` from the router.
- **Problem.** The router sees only the authority, not the `Session` (READ `session.py`: every verb forwards `authority=self._authority`). So `type jq` (the shell, which knows the session) and `ls /.vfs/bin` (the router) disagree when a session prefix shadows a name.
- **Amendment.** "`/.vfs/bin` is the host index only. Session prefixes show in `type -a` and `which -a`, which mark the winner." ADR 063 is not at risk: the prefix is order, not rights, and every lookup is a gated `stat`. Drop "it can already list" as a check (it buys nothing once each `stat` is gated), or make it one `stat` at prepend time.

### 19. `deny_ops` is the wrong place for program names — **should fix**

- **Spec lines 95–96.**
- **Problem.** `deny_ops` is typed `Iterable[Op]` and validated against the op vocabulary. Program names would share that space with verb names: is `write` the verb or a program? Read-family names are refused (`grep`). "The shell's mount meta" names no binding: the shell has no mount. And today a program name is silently accepted and does nothing.
- **Evidence.** EXECUTED `p1`: `VirtualFileSystem(deny_ops=["jq"])` is accepted with no effect; `deny_ops=["grep"]` raises. READ `base.py:846-862`.
- **Amendment.** "`Index(masked=frozenset[str])` holds the masked program names. A masked name resolves to `unsupported`, exit 126. A kernel name in `masked` is a `ValueError` at construction. `deny_ops` is unchanged." (This departs from ADR 084 pin 8's wording, not its intent.)

### 20. Budgets: no tightening seam, the staging budget's scope, and the verb trip — **should fix**

- **Spec lines 123–128** and criterion 5.
- **Problems.**
  - ADR 084 pin 6: "a mount may tighten, never loosen". Neither 167 nor 169 names the API. Every budget test needs it. A 10-second wall budget per spin test is not acceptable.
  - `STAGING_BYTE_BUDGET` "sized against" the memory budget: per open file or per run? Staged buffers live in host Python memory, outside the store limit. Only a per-run total bounds the host.
  - Staging fetches the body before it can check its size. So the check runs on `size_bytes` after the read.
  - The verb-budget trip: host imports must never raise (memo §6), except under the recorded-state rule.
  - Time inside a verb is not covered by the epoch (ADR 084 pin 5). The shim's `.result()` waits forever.
  - `WALL_TIME_BUDGET` already exists twice in `src/`, with a different meaning (READ `grep.py:122`, `glean.py:146`).
- **Amendment.**
  > "`shell/budgets.py` declares a frozen `RunBudgets` (fuel, memory, verb calls, staging bytes, wall time). `VirtualFileSystem(shell_budgets=…)` and `cli(…, budgets=…)` may tighten it field by field; a looser value is `invalid`. `STAGING_BYTE_BUDGET` bounds the sum of every open buffer plus stdin and stdout in one run; an open that would pass it is `FBIG` (22), judged on `size_bytes`. A verb-budget trip records `budget_exhausted` in per-run state and returns `NOTCAPABLE`; the next host call raises the recorded sentinel. Each posted verb waits with `future.result(timeout=remaining)` and is cancelled on expiry. The shell's line deadline gets its own name (`LINE_WALL_TIME_BUDGET`)."

### 21. The wasmtime dependency and the test fixtures are not decided — **should fix**

- **Problem.** wasmtime is not a dependency. EXECUTED: `uv run python -c "import wasmtime"` is `ModuleNotFoundError`. The spikes ran with `--with wasmtime`. The spec does not say core dependency or extra (`vfs-py[wasm]`). The 100% coverage gate needs it in the dev group. Criteria 3–8 need guest binaries; the spec does not say where they come from. A test run cannot depend on a Rust toolchain or the network.
- **Amendment.**
  > "wasmtime is an optional extra, `wasm`; without it the host answers `unsupported` naming the extra, and the dev group carries it. Shim tests use WAT guests compiled at test time with `wasmtime.wat2wasm`. Two Rust guests (`upper`, `fsops`) are checked in under `tests/fixtures/wasm/` with their sources and a rebuild script; `jaq` (MIT, 3.7 MB) is fetched by a `slow` test leg with a pinned hash, or criterion 6 moves with §5."

### 22. Streaming and early close for a wasm stage are unstated — **should fix**

- **Spec lines 141–143.**
- **Problem.** ADR 083 streams 64 KiB chunks with a queue depth of 2. The spike handed the guest its whole stdin as one buffer. The spec does not say which. It does not say what `prog | head -3` does to a running guest: the epoch cannot cancel from outside, and a store's deadline is fixed at creation.
- **Amendment.** "At v1 a wasm stage materializes its stdin (bounded by the upstream's `STDOUT_BYTE_BUDGET`) and its stdout (bounded by its own). Early close sets a cancel flag in per-run state; the next host call raises the recorded sentinel and the stage reports `cancelled` as info. The docstring names streaming `fd_read` over the queue as the next step."

### 23. The skills view and `Skill.to_entries(at=)` are under-specified — **should fix**

- **Spec lines 42–43, 55–57.**
- **Problems.** Is each skill-index entry a skill, or a container of skills? ADR 082 pin 9 says a repo's `.claude/skills` "becomes a skill-index entry". That is a container. Discovery depth is unstated. The union key (skill name) and the first-wins rule are unstated. `to_entries(at=…)`: is `at` the container or the unit? The Agent Skills rule "the name must match its parent directory" (READ `skills.py:33-34`) holds only if `at` is the container.
- **Amendment.** "A skill-index entry is a container: its skills are the directories `<entry>/<name>/` holding `SKILL.md`, found with one `glob <entry>/*/SKILL.md` per entry. The union key is `<name>`; first entry wins. `Skill.to_entries(at=container)` writes `<container>/<name>/SKILL.md`."
- The retirement also touches `models/entry.py:183` (`is_reserved_directory`), `tests/test_paths.py`, `tests/test_skills.py`, `tests/models/test_models.py` and `README.md:96`. List them in the plan.

### 24. The two `[NEEDS CLARIFICATION]`s — **should fix (recommendations)**

- **Two suffixes, one basename (lines 78–80).** Agree with the lean: a declared order, `.wasm` first. Add the case no one named. EXECUTED `p6_suffixless.out`: a suffix-less `/opt/bin/jq` holding bytes is a legal file today. Proposed: "the suffix order is `.wasm`, then the spec-172 suffixes, then none. A suffix-less bytes row runs when its mime is `application/wasm`. `ls /.vfs/bin` shows the winner; `type -a` shows all."
- **`/opt/bin` on a fresh node (lines 81–84).** Minted by the host at construction, as the system actor (finding 16), not by the first agent write.

### 25. Nits (one list)

- Header line 12 calls `application/wasm` "one schema fact". A mime value is not a schema change. The new `Observation` fields (finding 2) and any version column (finding 13) are.
- `application/wasm` comes from `_MAGIC`, not a "mime table". There is no extension table (READ `media.py:81-113`). EXECUTED `p2`: `.wasm` bodies sniff as `application/octet-stream` today. Add the core-module signature `\0asm\x01\x00\x00\x00`. A component (`\0asm\x0d\x00\x01\x00`) must not match: the host runs core modules only.
- Line 90: a text file named `.wasm` refused as `wrong_kind` maps to ENOTDIR/EISDIR, which misleads. Use `invalid` ("not a wasm module"), exit 126, like bash's "cannot execute binary file". EXECUTED `p2`: such a row has `source=text, mime=None`; key the check on `mime_type == "application/wasm"`.
- Criterion 6's "zero file verbs" means zero verbs from the guest. `cat` itself issues one `read`.
- Line 61–62 hides `/.vfs` from the guest. Say whether `<mount>/.vfs` is hidden too.
- `_invalid_path` returns `path=None` (EXECUTED `p1`). The view refusal should carry the path, so the agent sees which address it tried.
- `add_index_path`/`remove_index_path` should mutate under `_mount_lock` and have a read-back (`index()`), like `mounts()`.
- Name the modules. Where do `Index` and the views live (`vfs/views.py`?), and confirm `base.py` never imports `vfs.shell`.

## What the spec gets right

- Programs as ordinary entries, installed by `write`. EXECUTED `p2`: install, overwrite and versioning already work. A same-bytes reinstall advances the version, so keying the cache on `content_hash` is right.
- Execution as `read` on the entry, with 126 and 127 falling out of the existing gates. EXECUTED `p2`: `list` gives a bare `stat` and `permission_denied` on `read`; no grant gives `not_found`.
- The exit-code rule (record in per-run state, never read it from the exception) and "every store gets a memory limit" are exactly the spike's fixes.
- `rmdir` as `delete(cascade=False)`, and `..`-escape refusal before any verb.
- Keeping `/.vfs` out of unscoped search. EXECUTED `p1`: unscoped `glob **/*.wasm` already hides `/.vfs/bin/x.wasm`, and the router-owned table of finding 1 keeps it so.
- Retiring `/.agents` and `run` in favour of an index: it removes a convention vfs never needed.

## Proposed split

1. **169a — the views and the index (no wasm).** Finding 1's view table, the `/.vfs` write refusal and the meta-root synthesis; `Observation` fields; `/.vfs/bin` and `/.vfs/skills`; `Index`, `add_index_path`, `masked`, `prefer_stored`; the batched-`stat` resolution; `type`/`which` from the view; `application/wasm` by magic; the install rules and the `/opt/bin` posture; `/.agents` retired; `Skill.to_entries(at=)`. A resolved program answers `unsupported` ("no runtime installed") until 169b. Testable with no wasmtime.
2. **169b — the WASI host.** Findings 3, 4, 6–14, 20–22: the shim, the fold, write-back, rename, budgets, fuel, the cache, the executor, the errno column, attribution, the `wasm` extra and the WAT fixtures.
3. **169c — `/.vfs/run`.** After its retention is decided (finding 17). It could also fold into 167's output-row work.
4. **Its own spec, after 171 — first programs.** uutils and jaq builds in CI, release assets and hashes, `vfs install`, the multicall rule (finding 5).

## Questions only Clay can answer

1. **Who may install into `/opt/bin` by default?** (finding 16.) A program runs as its caller, so an open bin directory lets any principal choose code that runs with everyone's rights. Proposed: the host mints `/opt/bin` as the system actor with posture `read`; installing needs a grant. The cost: in the in-process open default, an agent cannot install until the host grants it.
2. **One guest at a time per process: is that acceptable for 0.1?** (finding 9.) Proposed: yes, with an honest docstring, and queue wait counting against the line's deadline. The alternative is the Rust host now.
3. **What exit code does `budget_exhausted` give a stage?** (finding 6.) Timeout is 124 by the table. Fuel and verb exhaustion have no code yet. Proposed: 124 for both, with the kind telling them apart.
4. **Keep the write-time refusal of kernel names?** (finding 5.) Resolution already never serves an unpromoted kernel name. The refusal adds a mutation-gate rule across `write`, `copy` and `move` that couples the router to the shell's table. Proposed: keep it, scoped to names not in `prefer_stored`. The alternative is to drop it and let `type -a` show the shadowed entry.
5. **Program attribution: a version column now, or later?** (finding 13.) Proposed: one nullable `program_hash` column and a format bump. The alternative is no schema change, with attribution kept in the `Result` extras only.

## Verdict

The spec is not ready to build. Its direction is right. A program is an entry. Executing is `read`. The gates already give 126 and 127. The spike proved the host. But the hardest part, §1, names no mechanism. The live router sends `/.vfs/...` to the root storage as an ordinary stored subtree. There is no seam for a view, and the union's columns collide with `Observation`'s typed fields. In §4, three things contradict what ran: the fold, the counts and the trap classes. And one executed probe shows a refused write-back is lost while the program exits 0. Fix findings 1–6 in the spec text, take the split above, and 169a can be built against the live tree as it stands. In one line: right design, no router seam yet, a silent-write hole in the host, and four landings packed into one spec.

## Executed scripts

All in `./experiments/r169/`, each with its `.out` beside it.

- `p1_routing.py`: which binding owns each `/.vfs` path; `ls`/`stat` of the meta root at the root and at a mount; writes into would-be views (succeed today); unscoped vs scoped `glob`; `bind` at `/.vfs/bin` (refused); `deny_ops` with a program name (silently accepted).
- `p2_install_and_gates.py`: `sniff_mime` on wasm magic (`octet-stream`); install, a text `.wasm` and a same-bytes reinstall; the `list`/`read`/none gates a resolver relies on; `read(columns={content_hash, version})` as the cheap execute gate; bob overwriting ann's program under the default posture.
- `p3_silent_writeback.py` (`--with wasmtime`): the E1 shim and host, unchanged. A refused write-back exits 0 and leaves the file untouched; a `list`-only caller is refused only because its row lacks a version.
- `p4_fold_classification.py`: the error kinds a read-first `path_open` sees, including the two meanings of `wrong_kind` and an ancestor `not_found`.
- `p5_trap_classifier.py` (`--with wasmtime`): `UNREACHABLE` for both out-of-memory and a plain abort, with memory far from the cap; `OUT_OF_FUEL` exact to the unit; cross-config deserialize refused.
- `p6_suffixless.py`: a suffix-less program file, `jq`, `jq.wasm` and `jq.py` side by side.
- `p7_rename_over.py`: `move` onto an existing file is `vfs.exists`.
