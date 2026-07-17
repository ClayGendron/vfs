# 027 — Embedded Code Execution

- **Status:** draft
- **Date:** 2026-05-14
- **Owner:** Clay Gendron
- **Kind:** feature · execution · capability extension
- **Depends on:** 001, 015, 026
- **Enables:** one-turn fan-out across vfs operations; path-stored
  package bundles (later); skills-as-files (later); `/dev/quickjs`
  and `/proc/repl` synthetic mounts (later)

## Intent

Add one new public verb, `exec`, that runs a `.js` file stored in
vfs through an embedded QuickJS runtime. Scripts call vfs methods
through a `globalThis.vfs` bridge that delegates to the caller's
`VFSClient` — same permissions, same versioning, same routing.
Returns `VFSResult`.

```python
await g.write('/scripts/sales.js', """
const csv  = await vfs.read({ path: '/data/sales.csv' });
const rows = csv.trim().split('\\n').slice(1).map(r => r.split(','));
const hi   = rows.filter(r => Number(r[2]) > 1000);
await vfs.write({
  path: '/data/sales_high_value.csv',
  content: hi.map(r => r.join(',')).join('\\n'),
});
return { kept: hi.length, total: hi.reduce((s, r) => s + Number(r[2]), 0) };
""")

await g.exec('/scripts/sales.js')
# VFSResult(function="exec",
#           candidates=[Candidate(content='<result>{"kept":42,"total":81234}</result>')])
```

After this story, an agent that wants to filter+rank+dedupe results
no longer asks the model to issue six tool calls — it writes one
script, executes it, gets the answer.

## Why

- **Round-trip collapse.** Multi-step retrieval costs N model turns
  today. With `exec`, one turn writes a script that does all N steps
  in-process. ~N× fewer tokens, ~N× lower latency, same agent
  harness.
- **Programs are files.** Scripts are addressable, versioned by
  `versioning.py`, grep-able, permission-gated by `permissions.py`.
  The agent can read its own script to understand what ran, edit it
  for v2, or `grep /scripts` to find prior work. **No new
  infrastructure to make any of this true** — every primitive is the
  one vfs already has.
- **Capability discipline holds.** A script does not get new
  authority. It runs as the caller's `user_id`; every JS call routes
  through the public API and re-checks permissions; the runtime has
  no `fetch`, no `fs`, no `process`. Code in the sandbox cannot
  reach outside the namespace it was invoked through.
- **Constitution-clean.** No new `Entry.kind` (scripts are
  `kind=file`). No new primitive. The runtime is a `VFSClient`
  subsystem, not a per-mount backend. Opt-in behind the `[quickjs]`
  extra; the core install is unchanged.
- **Plan 9 lineage (Article 3).** Scripts compose through the
  namespace (read in, write out), I/O is text-shaped, and the
  program is a file.

## Scope

### In

1. **New public verb `exec` on `VirtualFileSystem`.**

   ```python
   async def exec(
       self,
       path: str,
       *,
       user_id: str | None = None,
       timeout: float | None = None,
       memory_limit: int | None = None,
   ) -> VFSResult: ...
   ```

   Reads the script at `path`, runs its content through the embedded
   runtime, returns one `VFSResult` whose single Candidate carries
   the rendered stdout and final value.

2. **QuickJS runtime via `quickjs-rs`** (the PyO3 + rquickjs binding
   that `langchain-quickjs` uses). Confined to a new
   `src/vfs/runtime/` module. Single dep behind `vfs[quickjs]`;
   absent the extra, `exec` raises `Unsupported` from the same
   chokepoint other capability checks use.

3. **`globalThis.vfs` bridge — 11 methods.** Available inside a
   script as `await vfs.<camelCase>({...kwargs})`:

   `read`, `write`, `edit`, `ls`, `glob`, `grep`, `semanticSearch`,
   `lexicalSearch`, `vectorSearch`, `pagerank`, `runQuery`.

   Anything else is reachable through `runQuery` (which takes a full
   pipeline string). Lifecycle (`addMount`/`removeMount`) and
   ambient-destructive ops (`delete`, `move`, `copy`) are
   deliberately omitted from v1.

4. **`VFSResult` round-trip.** Arguments to bridge calls are JS
   objects → Python kwargs. Return values are
   `result.model_dump(mode='json')` → JS objects. Set algebra stays
   Python-side; JS callers compose by passing
   `{candidates: result.candidates}` between calls.

5. **Caller identity is inherited; capabilities are not widened.**
   The bridge sets `user_id=<caller>` on every delegated call. A
   script cannot forge a different identity. Permission enforcement
   is exactly what it is today — it happens inside the public API
   the bridge calls.

6. **Error taxonomy round-trips.** A vfs error raised inside a
   bridge call surfaces in JS as a `VFSError` with a `.kind` string
   matching the taxonomy from story 026 (`NotFound`,
   `PermissionDenied`, `WrongKind`, `Unsupported`, `Conflict`,
   `CrossMount`, `Unavailable`, `Invalid`, `Timeout`, `Cancelled`).
   A script can `try/catch (e)` and dispatch on `e.kind`. Unhandled
   JS-side errors map back to `Invalid` on the Python side.

7. **Sandbox limits.** Per-call timeout (default 5s, override via
   kwarg), runtime-wide memory limit (default 64 MiB), stdout/stderr
   capture, no network, no real filesystem. Each `exec` gets a fresh
   context; the Runtime itself is reused per process.

8. **Console capture.** `console.log`/`.warn`/`.error` is captured
   and rendered as `<stdout>...</stdout>` in the returned Candidate's
   `content`. Final expression value (or last `return`) renders as
   `<result>...</result>`. Same wire format `langchain-quickjs`
   settled on — keeps prompt shape consistent across agent
   frameworks.

9. **Capability declaration.** `VFSClient` declares a new
   `execute_code` capability in its capability map. Set true when
   the `[quickjs]` extra is installed and the runtime imports
   succeed; false otherwise.

### Out

- **Cross-turn persistence.** Scripts are pure. State lives in vfs
  (write to `/tmp/foo`, read it back). Snapshot/restore is v2.
- **Package imports.** No `@/skills/`, no `@/packages/`, no
  bare-specifier resolution to a vfs path. Single-file scripts only.
- **TypeScript signature injection** into agent prompts. The bridge
  has the schemas (from Pydantic), but `.d.ts` emission is its own
  story.
- **`/dev/quickjs` and `/proc/repl/<sid>/*` synthetic mounts.**
  Defer; requires new write-triggered-side-effect machinery in
  `routing.py` that doesn't exist today.
- **CLI parser support for `exec`.** Python entrypoint first; CLI is
  a small follow-up.
- **Binary read mode.** Parquet/Arrow/images need
  `vfs.read({mode: 'binary'})` and a content-type-aware return
  shape; bigger than this story.
- **`delete`/`move`/`copy` in the bridge.** Destructive ops want
  explicit capability narrowing not afforded in v1. Use `runQuery`
  if you really need them.

## Acceptance criteria

1. `pip install vfs-py[quickjs]` succeeds on macOS/Linux/Windows for
   CPython 3.12+ from upstream `quickjs-rs` wheels.
2. `await g.exec('/scripts/hello.js')` runs a script and returns one
   `VFSResult` whose single Candidate carries `<stdout>` and
   `<result>` blocks.
3. A script that calls `vfs.read('/no/such/path')` sees
   `{kind: 'NotFound'}` in `catch`, not a Python traceback.
4. A script that tries to write where the caller cannot write fails
   with `{kind: 'PermissionDenied'}` from JS-land; `permissions.py`
   is unchanged.
5. A 6-second `while(true){}` halts at 5s and surfaces `Timeout`.
6. Script writes are recorded by `versioning.py` exactly like any
   other write. `read('/scripts/foo.js@v2')` returns v2;
   `exec('/scripts/foo.js')` runs head.
7. Without the `quickjs` extra installed, `exec` raises `Unsupported`
   from the same chokepoint other capability checks use.

## Risks

- **New dependency surface.** `quickjs-rs` is a PyO3 wheel; we
  accept its bus factor. Mitigation: confine imports to
  `vfs/runtime/`, gate behind `[quickjs]`, keep the bridge thin
  enough that swapping to PyMiniRacer/PythonMonkey is a one-file
  change.
- **Permission attack surface.** A JS script can call public methods
  in patterns we haven't fuzzed. Mitigation: every bridge call goes
  through the same `_route_*` chokepoint the CLI uses; add fuzz
  tests that drive bridge calls.
- **Mental-model drift.** Agents may learn to write scripts for
  things that should be one CLI call. Mitigation: docs lead with
  `g.cli('grep ... | pagerank | top 15')` as the default; `exec` is
  for things pipelines can't express.

## Open questions

1. **Where does the runtime sit in the constitution?** Article 4
   names "future runtime" as a backend kind, but QuickJS is not a
   filesystem — it doesn't implement `read/write/grep/...`. Either
   Article 4 generalizes (*backend → subsystem*) or the runtime sits
   beside the backend taxonomy as a separate concept. Resolve
   before v1 ships, or land with a noted decision in
   `context/decisions/`.
2. **Should `exec` accept `--cap` overrides?** v1 inherits the
   caller's identity; nothing else narrows it. A future story may
   add per-`exec` capability narrowing (read-only subtree, explicit
   network grants). `**kwargs` is reserved for this.
3. **Composition with story 023 (per-session namespaces).** Most
   natural answer: each session has its own Runtime, scripts see
   the session's overlay, not the global router. Worth confirming
   before 023 lands.
4. **Content-type registry vs. a single `exec` verb.** The Plan 9
   move: `run /scripts/foo.js` dispatches to QuickJS via `.js`
   registration, `run /scripts/foo.py` to a sandboxed Python.
   Probably yes eventually; v1 ships `exec` as a single verb.
   Registry is the v2 generalization.

## References

### Codebase
- `src/vfs/client.py` — `VFSClient` public surface
- `src/vfs/base.py:1108-1145` — `run_query`, `cli` (template for the
  new `exec` verb)
- `src/vfs/results.py:87,247` — `Candidate`, `VFSResult` shape
- `src/vfs/permissions.py:132-302` — enforcement chokepoint scripts
  inherit
- `src/vfs/versioning.py:23-66` — script versioning, free
- `src/vfs/routing.py:36-145` — routing layer scripts call through
- `pyproject.toml:42-60` — optional-deps pattern

### Project context
- `context/constitution.md` — Article 3 (Plan 9 lineage), Article 4
  ("future runtime" hook)
- `context/stories/023-per-session-namespaces` — overlay composition
  (Open Q §3)
- `context/stories/026-vfsresult-by-mount` — error taxonomy the
  bridge surfaces

### External precedent
- `langchain-quickjs` 0.1.2 (May 2026) — reference impl at
  `~/Git/Repos/deepagents/libs/partners/quickjs/`
- `_repl.py:339-936` — Runtime/Context/Slot pattern to port
- `_ptc.py:38-80` — camelCase mapping, schema → TS signature
  renderer
- Anthropic Agent Skills (Oct 2025) — adjacent "code-as-file"
  precedent
