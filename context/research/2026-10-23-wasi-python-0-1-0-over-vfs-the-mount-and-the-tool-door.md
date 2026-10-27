# wasi-python 0.1.0 over vfs: the mount and the tool door are the whole seam, and the public APIs already carry an authority

- **Status:** research memo (commits us to nothing). Feeds an amendment
  of ADR 086 and a rewrite of spec 172; narrows spec 169b.
- **Date:** 2026-10-23
- **Owner:** Clay Gendron
- **Question:** Clay, 2026-10-23: "Off on the side I build a project
  called wasi-python to be the Python interpreter for this package.
  Research it and make sure it aligns with vfs. I want wasi-python to
  call vfs through its public APIs (we can adjust them if needed) so it
  can make a call with an authority. I do not want to use the grants
  with wasi-python." Read here as: the guest's only filesystem is vfs,
  reached under a vfs `Authority`; no wasi-python `Grant` (a host
  folder preopened into the guest) anywhere.
- **Method:** one session, read-only over `~/Git/Repos/wasi_python`
  at `2cd47507` ("Release 0.1.0", 2026-10-23; Apache-2.0; clean tree
  but for an untracked `test_app/`), and over the published wheel
  `wasi-python==0.1.0` from PyPI, installed into an ephemeral `uv`
  environment (`uv run --with wasi-python`), never into vfs's lockfile.
  Read against ADR 082, ADR 084, ADR 086, spec 169b and spec 172 as
  they stand today. Two experiments were executed over the **public
  APIs of both projects only**, with no change to either tree; their
  scripts and outputs are in
  `studies/2026-10-23-wasi-python-over-vfs/experiments/`. Every claim
  below is labelled EXECUTED (ran here), READ (in a file at the commit
  named) or INFERRED.

## 0. In one paragraph

wasi-python 0.1.0 is no longer the artifact set ADR 086 and spec 172
assumed on 2026-10-16. It ships its own runner (`run`, `run_async`,
`Session`) with wasmtime as a required dependency, a **mount**
protocol that lets embedder code serve the guest's whole filesystem,
and a **tool protocol** through which guest code calls host functions
as `from host import tools`. Those two seams are exactly the two doors
spec 172 wanted to build itself (the preview1 shim over verbs and the
`vfs.call` door). Closing both over one `vfs.Session` gives every
guest file call and every guest verb call the caller's `Authority`,
with no `Grant` and no change to either project: the experiment ran a
pandas CSV job, a mkdir/rename/remove cycle, a refused write into a
read-only mount, a hidden `/.vfs`, a ladder-gated read (Alice refused,
Bob granted), and three verb tools, all through today's public APIs.
What is left is bookkeeping on our side (an errno table, `move`'s
replace rule, the `python` program kind as a thin adapter) and a
rewrite of ADR 086's and spec 172's now-false premises.

## 1. What wasi-python 0.1.0 is, against what vfs assumed

READ unless marked. The right column cites the wasi_python file.

| vfs assumed (ADR 086 / spec 172, 2026-10-16) | wasi-python 0.1.0 today |
|---|---|
| Pin 2 open: CPython 3.15 + wasi-sdk 33 (lean) or 3.14.8 + SDK 24 | **3.15.0** on wasm32-wasip1 (EXECUTED: `sys.version`); the C++-exception line, so matplotlib built. Pin 2 is resolved by the release. |
| Pin 1: numpy and pandas only; sqlite3, bz2, lzma, matplotlib, scipy out of scope | numpy 2.5.2, pandas 3.0.6, **scipy, scikit-learn, statsmodels, matplotlib, sqlite3, bz2, lzma** all import (EXECUTED; matplotlib raises `OSError` until `HOME` is writable, §5 F11), plus about forty pure-Python packages (README). `threading`, `ctypes`, `mmap`, `socket` import; a thread start raises and there is no network (`docs/explanation/security-model.md`). |
| Spec 169b: vfs writes its own preview1 host (`shell/wasi/`), one guest per process, a Python executor hand-off, its own fuel/epoch/memory plumbing | The runner is wasi_python's: `run()`, `run_async()`, `Session`; wasmtime is a plain dependency (`pyproject.toml`); several guests at once (`async_workers`, CPU count up to 8); every limit has a default (`Defaults`). wasi_python decision 13 (2026-10-17): "converge on our runner, but do not edit vfs" (`context/decisions.md:301-305`). |
| Spec 172 §3: a reactor export `vfs_run`, argv and env set per call | The export is `run`, after `_initialize` on the plain reactor; argv and env go through WASI per call (`docs/how-to/embed-from-other-languages.md`). |
| Spec 172 §4 / ADR 086 pin 7: a `vfs` package in the stdlib zip over a `_host.call` C module | One custom import, `host::call(ptr, len, out_ptr_ptr, out_len_ptr)`; frames are opaque bytes; **one optional tool protocol** (v1: `list` and `call`, JSON frames, MCP descriptor names, nine failure kinds) rides on it; the guest's half is the pure-Python package `host` in the zip (`docs/reference/tool-protocol.md`). wasi_python's constitution §5 is **embedder-neutral**: no code, name or test in that repo may refer to vfs (`context/constitution.md:41`; the rule `test_no_embedder_name_in_code` matches `vfs` as a substring). A `vfs` package can never live in that zip. |
| Spec 172 §2: `vfs python install` copies the binary to `/opt/bin/python3.wasm` and the zip to `/opt/lib/python3XY.zip` as rows | The wheel carries the artifact set (`wasi_python.artifacts()`: snapshot, plain reactor, stdlib zip, MANIFEST; about 250 MB unpacked, 94 MB download, EXECUTED) and `run(artifacts=…)` takes a set. The runner preopens the zip itself. Nothing needs to be a vfs row. |
| Spec 169b §b3: two preopens (`/` and `.`), `/.vfs` hidden by the shim | `Mount(provider, "/")` makes the provider the guest's whole filesystem; `root=`, `grants=` and `mounts=` are the only three sources of paths and all default to nothing (`docs/reference/guest-filesystem.md`). Hiding `/.vfs` is the provider's job (the runner "knows nothing about permissions: it calls your provider for every access"). |
| Spec 169b §b4–b5: whole-file staging, write-back at close and sync, a refused write-back never silent | The same contract, in the runner: a file is staged whole at open and handed to the provider whole at close, `fsync` and the call's ending; every refusal lands in `done.files.refused` with `at` and `cause`, "whether a refused write fails the run is yours to decide" (`docs/how-to/mounts.md`). |
| ADR 084 pin 5 budgets | `deadline_s` 60, `memory_bytes` 1 GiB, `fuel` (optional), `output_bytes` 16 MiB, `max_file_calls` 10,000, `max_tool_calls` 1,000, `max_tool_request_bytes` 16 MiB, `max_open_files` 1,024; each tightenable per call; `trapped` is one of four promised strings ("out of fuel", "deadline", "cancelled", "out of file calls") or wasmtime's words, with `exit_code` `None` (`docs/reference/python-api.md`). |
| ADR 086 pin 9: QuickJS-NG for JavaScript | Unchanged; wasi_python is Python only. |

INFERRED: spec 172 was written against the spike's recipe on
2026-10-16; wasi_python then made forty decisions on 2026-10-17 alone
(`context/decisions.md`) and released 0.1.0 on 2026-10-23. Everything
in spec 172 about the build, the host, the door and the install is
stale; §5's documented semantics (int32 default integer, EXECUTED:
`numpy.arange(3).dtype == int32`; no threads; no network) still hold.

## 2. The seam, as the public APIs already shape it

Two objects on wasi_python's side, one on ours.

```
vfs side                                   wasi_python side
--------                                   ----------------
fs = VirtualFileSystem(...)
session = fs.session(Authority.of(alice))  ──┐
                                             ├─► Mount(VfsProvider(session, loop), "/", writable=True)
                                             │       stat / list / read            → session.stat / ls / read
                                             │       write / mkdir / remove        → session.write / mkdir / delete
                                             │       rmdir / rename                → session.delete(cascade=False) / move
                                             │
                                             └─► tools=[ls, grep, write, ...]  each an `async def` closed over `session`
                                                     guest:  from host import tools; tools.grep("MFA", "/docs")

await wasi_python.run_async(["-c", code] | [script, *args], mounts=[...], tools=[...],
                            deadline_s=..., fuel=..., memory_bytes=..., max_file_calls=..., max_tool_calls=...)
```

- **Authority.** The `vfs.Session` is the one place the `Authority`
  lives. Both the provider and every tool call `session.<verb>`, so
  every guest file call and every guest verb call re-enters the
  router's funnel with that authority and every gate fires. This is
  ADR 082 pin 2 ("the filesystem capability is the vfs verb set
  curried with the caller's `Authority`") in wasi_python's own
  recommended shape ("make the tools per request, each closing over
  that caller's authority", `docs/how-to/tools.md`). No `Grant`.
- **Threads and loops.** A provider method is synchronous and runs on
  the thread that called `run`; under `run_async` that is a worker
  thread, never the event loop's. vfs is async-native, so the provider
  posts each verb to vfs's loop with
  `asyncio.run_coroutine_threadsafe(coro, loop).result()`, the
  pattern the mounts guide names. A tool may be `async def` and is
  awaited on the loop that awaits `run_async`. So vfs always calls
  `run_async` (or `Session.run_async`), and the provider carries the
  loop handle. This is the same hand-off spec 169b §b8 designed, now
  owned by wasi_python.
- **Errors.** A refused verb is a classified `Result`. The provider
  maps its first fatal `ErrorKind` to a wasi_python `Errno` by spec
  169b §b7's table; EXECUTED: every one of the 24 kinds has a member
  in wasi_python's `Errno` (the script asserts it). The `NOTCAPABLE`
  the shim used for climbs and the verb budget is not needed: the
  runner owns both (a climb is `EPERM`; the budget is the trap "out of
  file calls"). A tool returns `result.to_payload()`, which is JSON
  and crosses whole; the guest reads `r["success"]`, `r["errors"]`
  and `r["observations"]`.
- **Hidden tree.** The provider answers `ENOENT` for any path with a
  `.vfs` segment before issuing a verb (spec 169b §b3), and drops such
  names from listings.
- **Exit codes.** wasi_python's `trapped` maps onto ADR 084 pin 8:
  "deadline" → 124, "out of fuel" and "out of file calls" → 137, any
  other trap → 134; `exit_code` otherwise. A refused write-back in
  `done.files.refused` makes the stage status 1 even on exit 0, as
  spec 169b §b5 requires.

## 3. Experiment 1 — the whole job over the public APIs (EXECUTED)

`experiments/exp_vfs_mount.py`, output in `exp_vfs_mount.out`. Setup:
`VirtualFileSystem(storage=InMemoryStorage())`, a second
`InMemoryStorage` mounted read-only at `/ro`, four rows written as the
system actor; the guest runs as `Authority.of(Principal("alice"))`
with `Mount(VfsProvider, "/", writable=True)` and three tools.

| Guest did | Saw | vfs verbs |
|---|---|---|
| `os.listdir("/")` | `['data', 'docs', 'out', 'ro']` | `ls` |
| `open("/docs/hello.md").read()`, `os.stat` | the row's text; size 21 | `read`, `stat` |
| `pandas.read_csv("/data/in.csv")`, `to_csv("/out/result.csv")`, read back | `[2, 12]`; the row landed as **text** (`content`, not `data`) | `stat`×n, `read`, `write`×2 |
| `mkdir`, create, `rename`, `remove`, `rmdir` under `/out/sub` | each as POSIX | `mkdir`, `write`×2, `move`, `delete`×2 (+ a `stat` each for the kind check) |
| `open("/ro/locked.md", "w")` | `OSError` errno 69 `EROFS` at open; recorded as `RefusedWrite(method='write', at='open', cause='refused')` while the guest exited 0 | `write` → `vfs.read_only` |
| `open("/.vfs/trash")` | `FileNotFoundError` 44 | none (hidden before any verb) |
| `open("/docs")` | `IsADirectoryError` 31 (from `wrong_kind` with `data.kind == "directory"`) | `read` |
| `tools.ls("/docs")` | `success`, two paths | `ls` |
| `tools.grep("MFA", "/docs")` | `success`, one hit | `grep` |
| `tools.write("/ro/nope.md", "x")` | `success: False`, `errors[0].kind == "vfs.read_only"`, no exception | `write` |
| `tools.write("/out/from_tool.md", …)` | `success` | `write` |

Totals: exit 0, no faults, 40 verbs (20 `stat`, 4 `read`, 5 `write`,
3 `ls`, 1 `mkdir`, 1 `move`, 2 `delete`, 4 tool calls); provider calls
counted by the runner: `stat` 18, `list` 3, `read` 5, `write` 5,
`mkdir` 1, `remove` 1, `rmdir` 1, `rename` 1; tool outcomes all `ok`.

## 4. Experiment 2 — the ladder, rename-replace, the bare CSV job (EXECUTED)

`experiments/exp_vfs_ladder.py`, output in `exp_vfs_ladder.out`.

- **The ladder reaches the guest.** `posture("/secret", "none")` and
  `grant("/secret", "bob", "read")` as the system actor. The same
  guest run twice: as **Alice**, `open("/secret/x.md")` and
  `os.listdir("/secret")` both raise `FileNotFoundError` 44 (vfs
  answers `not_found` to a caller who may not list, so existence is
  hidden, and the mapping carries that through); as **Bob**, the read
  returns `top secret` and the listing `['x.md']`. Two authorities,
  one provider class, no host folder.
- **Rename onto an existing file** (`os.replace("/out/a.txt",
  "/out/b.txt")`) raises `FileExistsError` 20: vfs's `move` answers
  `vfs.exists` today where POSIX replaces. Spec 169b §b6 already
  named this (review probe p7) and spec 167 task zero adds
  `move(…, overwrite=)`. The refusal is recorded (`at='call'`).
- **The bare pandas job** (`read_csv`, `groupby().sum().to_csv`,
  `read_csv` back): exit 0, 21 verbs: 17 `stat`, 2 `read`, 2 `write`.
  Spec 172's criterion 3 (written for the spike's shim) says at most
  15 verbs for a bigger job. The difference has two sources: (a)
  **17 stats** from the guest's path probing before the first read,
  not attributed further here; the mounts contract allows the
  provider to cache, so a per-run stat cache keyed by `(path,
  version)` is the adapter's to add, as spec 172 §3's staged-buffer
  cache was; (b) **two `write` verbs per created file**: "a file
  exists from its open", so a create reaches the provider as
  `write(path, b"")` at open and the body at close. In vfs that is
  two versions per new file. Spec 169b §b4 had planned one `stat`
  at open and no write.

## 5. Findings

- **F1 (EXECUTED).** Today's public APIs on both sides are enough: no
  change to vfs or wasi_python was needed for a guest to read, write,
  list, rename, delete and search vfs rows under one `Authority`.
- **F2 (READ, EXECUTED).** No `Grant` is needed. With `mounts=[Mount(
  provider, "/")]` and no `root=`, the guest's only paths are the
  provider's and the read-only stdlib zip the runner preopens itself.
- **F3 (READ).** The guest-side verb surface is the tool protocol:
  `from host import tools`. A `vfs` module cannot live in the zip
  (embedder-neutral rule), and "a mount never serves the import path":
  only a read-only **grant** may hold an `import_path` entry
  (`_places.py:210`). So `import vfs` inside the guest needs either a
  host folder (which Clay has ruled out) or a wasi_python change (§6).
- **F4 (EXECUTED).** `Result.to_payload()` is a lawful tool value and
  arrives whole; a refused verb is `success: False` with its kind, not
  an exception, matching ADR 084 ("vfs allows or classifies").
- **F5 (EXECUTED).** The 24 `ErrorKind`s map one-to-one onto
  wasi_python's `Errno` by spec 169b §b7's table; `NOTCAPABLE` and
  `FBIG` are the runner's, not ours.
- **F6 (EXECUTED).** A refused write-back is recorded by the runner
  (`done.files.refused`, with `at` and `cause`) on a run that exited
  0. Spec 169b §b5's "never silent" rule is satisfied by reading that
  record; vfs need not keep per-run error state of its own.
- **F7 (READ).** wasi_python's budgets cover ADR 084 pin 5's set:
  `fuel` = `FUEL_BUDGET`, `memory_bytes` = `MEMORY_BYTE_BUDGET`,
  `deadline_s` = the wall budget, `max_file_calls` + `max_tool_calls`
  = `VERB_CALL_BUDGET` (two counters, 10,000 and 1,000 by default),
  `output_bytes` = `STDOUT_BYTE_BUDGET`; staged bytes are bounded by
  `memory_bytes`. A `RunBudgets` value maps field by field.
- **F8 (READ).** Several guests run at once; spec 169b §b8's
  one-guest-per-process rule and its single-thread executor are
  wasi_python's problem, solved (its spec 011 works around
  wasmtime-py's shared callback tables).
- **F9 (EXECUTED).** Two `write` verbs and two versions per created
  file, by "a file exists from its open". The open-time empty write is
  also the permission probe that fails a refused create at `open`, as
  POSIX expects; dropping it would move the refusal to close.
- **F10 (EXECUTED).** `move` has no replace rule yet; `os.replace`
  fails in the guest with `EEXIST` until spec 167's `overwrite=` lands.
- **F11 (EXECUTED).** matplotlib imports only with a writable `HOME`;
  under a mount, `HOME` is read-only unless `env={"HOME": …}` names a
  writable guest path. For vfs that is a per-actor directory the
  authority may write (`/home/<sub>` or the session's `cwd`), passed
  in `env=`.
- **F12 (READ).** wasi_python has a persistent-guest `Session`
  (variables survive across turns; 15 min idle, 1 h lifetime, a trap
  ends it). It is a later fit for vfs's own sessions (spec 148), not
  needed for `python3 script.py`.
- **F13 (EXECUTED).** `os.remove` in the guest tombstones the row
  (vfs `delete`), so a guest's deletes are recoverable through the
  trash, as spec 169's intent says.

## 6. Where the two projects do not yet meet, and the adjustments

None of these blocked the experiment. Ordered by who owns the change.

**vfs (ours):**

1. **`WASI_ERRNO` in `results/kinds.py`** (spec 169b §b7), spelled in
   wasi_python's `Errno` names; the drift test pins one entry per
   kind. The experiment's table is the draft.
2. **`move(…, overwrite=True)`** (spec 167 task zero) so `os.replace`
   and `shutil.move` work in the guest.
3. **The `python` program kind is a thin adapter**, not a host:
   `VfsProvider(session, loop)` (the eight provider methods, the hidden
   tree, the errno map, the text-or-bytes write-back rule of ADR 085
   pin 12, a per-run stat and body cache) and `verb_tools(session)`
   (the verb table minus the grant verbs and `run`, each an `async def`
   with a schema drawn from the verb's own parameters, returning
   `to_payload()`); `run_async` with `RunBudgets` mapped onto the
   call's limits; `trapped` mapped onto the exit-code table; the
   `files.refused` record folded into the stage's `Result`. Spec 172
   §3 and §4 shrink to this.
4. **Spec 169b narrows** to programs that are not Python: generic
   `.wasm` entries stored in vfs, if that kind is still wanted. Its
   preview1 shim, staging, errno table and budgets are the same
   contract wasi_python's runner now implements; the Python guest
   never uses it.
5. **ADR 086 amendments:** pin 1 (the package set is wasi-python's,
   much larger than numpy and pandas); pin 2 resolved (3.15, SDK 33);
   pin 4 (no rows under `/opt`; the artifact set rides in the wheel
   and `run(artifacts=)`); pin 6 (the host is wasi_python's runner);
   pin 7 (the door is the tool protocol; no `vfs` package in the zip).
   Pin 9 (QuickJS) is untouched.

**wasi_python (Clay's; proposals only, that project never takes a vfs
edit):**

6. **Optional: `import_path` entries served by a read-only `Mount`.**
   Today only a read-only grant may serve one. Allowing a read-only
   mount would let vfs ship a guest-side `vfs` helper (a thin wrapper
   over `host.tools` that reconstructs `Result`-shaped objects) as
   rows, with no host folder. Without it, v1's guest API is
   `from host import tools` and the tool names are the verb names.
7. **Optional: a distinct create hook** (`create(path)` or
   `write(path, None)`), so a provider can mint one version per new
   file instead of two, while still refusing at open. Accepting two
   versions at v1 is cheap: the empty first version is one `restore`
   away and the trash view already shows it.
8. **Nothing else.** The mount protocol, the tool protocol, the limits
   and the record already carry everything spec 169b and 172 asked
   for.

## 7. What this memo recommends

- Keep both public APIs as they are for the first landing. The
  adapter in §6 item 3 is the whole of spec 172's host work; write it
  against `wasi-python==0.1.0` pinned and hashed under a
  `vfs-py[python]` extra, as ADR 086 pin 4 already says.
- Guest API at v1: `from host import tools`, tool names equal to verb
  names, `to_payload()` dicts back. Decide §6 item 6 before promising
  `import vfs` to agents.
- Rewrite spec 172 from this memo and amend ADR 086 as §6 item 5
  lists; narrow 169b. Spec 172's counted criteria become operation
  counts read from `done.files.calls` and `done.tools.outcomes`, never
  a clock.

## 8. Open questions for Clay

- **Q1.** Guest-side surface at v1: tools only (`from host import
  tools`), or ask wasi_python for read-only-mount import paths so
  `import vfs` can ship as rows?
- **Q2.** Does vfs still want its own preview1 host (spec 169b) for
  generic stored `.wasm` programs, now that the Python guest runs on
  wasi_python's runner?
- **Q3.** Accept two versions per guest-created file at v1 (F9), or
  propose the create hook to wasi_python first?
- **Q4.** Where is the guest's writable `HOME` in vfs terms (F11): a
  per-actor directory under a fixed prefix, or the session's `cwd`?
- **Q5.** ADR 086's package-set pin: adopt wasi-python's set as
  published per release, with `python3 --version` reading the wheel's
  MANIFEST, rather than naming packages in the ADR?

## Sources

- `~/Git/Repos/wasi_python` at `2cd47507ef7c4e04d95aca059c60368417e01d40`
  (Release 0.1.0, 2026-10-23), Apache-2.0 (`LICENSE`), read-only:
  `tests/public_api.txt`, `src/wasi_python/mounts.py`,
  `src/wasi_python/runner.py`, `src/wasi_python/_places.py`,
  `docs/how-to/mounts.md`, `docs/how-to/tools.md`,
  `docs/reference/tool-protocol.md`, `docs/reference/guest-filesystem.md`,
  `docs/reference/python-api.md`, `docs/explanation/security-model.md`,
  `docs/explanation/sessions.md`, `docs/how-to/embed-from-other-languages.md`,
  `context/constitution.md`, `context/decisions.md` (13, 16, 17, 24,
  37–40), `README.md`.
- PyPI `wasi-python==0.1.0` (CPython 3.15.0, numpy 2.5.2, pandas
  3.0.6), installed with `uv run --with wasi-python`; experiments
  `studies/2026-10-23-wasi-python-over-vfs/experiments/exp_vfs_mount.py`
  and `exp_vfs_ladder.py` with their `.out` files, run on this machine
  against the live `src/` tree (vfs 0.0.22, `ac5c515`).
- vfs: ADR 082, ADR 084, ADR 086; specs 167, 169 (§b1–b9), 170, 172;
  `src/vfs/authority.py`, `src/vfs/session.py`, `src/vfs/base.py`,
  `src/vfs/results/kinds.py`, `src/vfs/results/envelope.py`;
  `context/specs/STATUS.md` (the 2026-10-16 entry);
  `context/open-questions.md` ("Hermetic-runtime guest bet").
