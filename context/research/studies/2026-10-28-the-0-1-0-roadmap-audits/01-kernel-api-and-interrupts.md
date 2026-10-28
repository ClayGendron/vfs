# Audit: the public kernel API and interrupts (human-in-the-loop)

Audited 2026-10-28 against `main` at `90f5883` (`docs(context): the architecture map`). Read-only. Every claim is labelled READ (I read it), EXECUTED (I ran it) or INFERRED.

Line numbers are for `src/vfs/base.py` unless another file is named.

---

## 1. Built today

### 1.1 The public surface of `VirtualFileSystem` (READ, `base.py`)

`VirtualFileSystem.__dict__` holds 36 public members: 11 control-plane members and 25 routed verbs. The drift test `tests/test_ops.py:246` (`test_router_public_verbs_are_exactly_the_registered_ops`) pins `public coroutines − MANAGEMENT_METHODS == ALL_OPS`, where `MANAGEMENT_METHODS = {add_mount, remove_mount, bind, unbind, remount, close, locate, locate_edge}` (`tests/test_ops.py:37`). `mounts`, `session` and `capabilities` are synchronous and so fall outside that test.

**Constructor** (L360): `VirtualFileSystem(*, name=None, title=None, description=None, storage: StorageBackend | None = None, permissions: Permission | PermissionMap = "read_write", deny_ops: Iterable[Op] = (), no_overlay=False, hop_budget: int = 16, close_timeout: float = 10.0, rerankers: Iterable[Reranker] = (BM25Rerank(),), default_authority: Authority | None = None)`. A `None` storage becomes `InMemoryStorage()` (L377).

**Control plane (11):**

| Member | Signature | Line |
|---|---|---|
| `bind` | `async (storage, path, *, permissions=None, deny_ops=(), no_overlay=False, owned=True) -> None` | 408 |
| `unbind` | `async (path) -> Binding` | 486 |
| `add_mount` | `async (storage, path=None, *, parents=False, permissions=None, deny_ops=(), no_overlay=False, owned=True) -> None` | 509 |
| `remove_mount` | `async (path) -> None` | 556 |
| `remount` | `async (path, *, permissions=None, deny_ops=None, no_overlay=None, refresh_caps=False) -> None` | 581 |
| `close` | `async () -> None` | 650 |
| `mounts` | `() -> tuple[MountInfo, ...]` (sync) | 693 |
| `locate` | `async (path, *, exists=False, authority=None) -> Location` | 734 |
| `locate_edge` | `async (source, target, *, exists=False, authority=None) -> EdgeLocation` | 762 |
| `session` | `(authority: Authority) -> Session` (sync) | 787 |
| `capabilities` | `() -> frozenset[str]` (sync) | 797 |

**Routed verbs (25).** Every one returns `Result` and takes `authority: Authority | None = None` keyword-only.

| Verb | Signature (minus `authority`) | Line |
|---|---|---|
| `read` | `(path=None, observations=None, *, columns=None)` | 902 |
| `stat` | same as `read` | 915 |
| `ls` | same as `read` | 928 |
| `tree` | `(path, max_depth=None, *, columns=None)` | 941 |
| `write` | `(entries=None, *, path=None, content=None, data=None, overwrite=True, parents=False)` | 958 |
| `edit` | `(path=None, old=None, new=None, edits=None, observations=None, replace_all=False)` | 1010 |
| `delete` | `(path=None, observations=None, *, cascade=True)` | 1053 |
| `restore` | `(path=None, observations=None)` | 1088 |
| `sweep` | `(path="/.vfs/trash")` | 1111 |
| `mkdir` | `(path, *, parents=False, exist_ok=False)` | 1135 |
| `mkedge` | `(edges=None, *, source=None, target=None, edge_type=None, provenance="system")` | 1155 |
| `rmedge` | `(edges=None, *, source=None, target=None, edge_type=None)` | 1200 |
| `move` | `(src=None, dest=None, moves=None)` | 1227 |
| `copy` | `(src=None, dest=None, copies=None)` | 1240 |
| `glob` | `(pattern, *, paths=(), observations=None, ext=(), ext_not=(), globs_not=(), kind=None, max_count=None, columns=None)` | 1257 |
| `grep` | `(pattern, *, paths=(), observations=None, ext=(), ext_not=(), globs=(), globs_not=(), case_mode="sensitive", fixed_strings=False, word_regexp=False, invert_match=False, before_context=0, after_context=0, output_mode="lines", max_count=None, allow_scan=False, columns=None)` | 1349 |
| `glean` | `(query, *, limit=10, paths=(), observations=None, ext=(), ext_not=(), globs=(), globs_not=(), columns=None)` | 1463 |
| `graph` | `(method, path=None, observations=None, *, depth=1, edge_types=(), edge_types_not=(), minimal=False, limit=128, columns=None)` | 1524 |
| `run` | `(path, *, arguments=None)` | 1571 |
| `grant` | `(path, principal, level)` | 1593 |
| `revoke` | `(path, principal)` | 1617 |
| `grants` | `(path)` | 1628 |
| `posture` | `(path, posture)` | 1640 |
| `add_member` | `(group, member, *, path="/")` | 1655 |
| `remove_member` | `(group, member, *, path="/")` | 1674 |

### 1.2 `Session` (READ, `src/vfs/session.py`)

`Session(fs, authority)`; `__slots__ = ("_authority", "_closed", "_fs")`. Public: `authority` (property), `closed` (property), `async close()`, `__aenter__`/`__aexit__`, and the same 25 verbs with `authority` removed from each signature (`session.py:78–412`). Every verb is `_refuse_closed(op)` then `self._fs.<verb>(..., authority=self._authority)`. A closed session answers `invalid` with detail "the session is closed and cannot reopen" (`session.py:423`). `__aenter__` on a closed session raises `ValueError` (`session.py:64`) — the one place the facade raises rather than classifies.

Pinned by `tests/base/test_authority.py:183–233`: a session verb equals the direct call with the authority filled in (parametrised over every op); session verbs take no identity argument; a closed session dispatches nothing. `Session` holds no state beyond the authority: no `cwd`, no narrowing content (`Authority.narrowing` is `Narrowing.NONE`, the enum's only value, `authority.py:68`), no `child()`, no `narrow()`, no `cli()`.

### 1.3 The gate (READ)

The path every verb walks, in order:

1. `_gate_params(op, **params)` L2835 — the per-op table in `vfs/params.py` (`PARAMS` L139, `RULES` L403, `VALUE_RULES` L486); a violation classifies `invalid` naming the parameter. Identity is not gated here (docstring L2841–2845). `tests/test_params.py:28` pins every verb signature to the table; `:162` pins "garbage classifies invalid with zero dispatch"; `:175`/`:182` pin that the param gate beats a closed table and a busy site.
2. `resolve_path` (`vfs/paths.py`) mints the branded `Path`; reserved grammar.
3. `_resolve_terminal` L2785 — longest-prefix match to a `Binding(path, storage, meta)`.
4. `_busy_guard` L2924 — `delete`, `restore`, `sweep`, `move`, `copy` may not hit a live bind site (`busy`).
5. `_gate_entry(binding, op, *, write_rels, read_rels)` L2852 — capability (`meta.caps`, `unsupported`) → reserved grammar for mutations (`check_reserved_path`, `invalid`) → `check_writable_composed` over `_permission_layers` L2901 (`read_only`/`permission_denied`). Order pinned by `tests/base/test_gates.py:337,347`.
6. `_dispatch_entry` L2942 → `_call_storage` L2956: `_admitted(authority)` L3088 fills the explicit authority, else `default_authority`, else `Authority.anonymous()`; then a fixed `match op:` with one arm per verb ending in `assert_never(op)` L3083. A backend lacking the `Supports*` family classifies `unsupported` (`_backend_unsupported` L3103); `TransportError` normalises to `backend_unavailable` L3085.
7. On the way out: `Result.with_mount(binding.path)` then `_shadow_filter` L3111.

Fan-out (`_route_fanout` L2041, `_gather_settled` L3133) awaits every sibling with no deadline; `CancelledError` re-raises untouched and outranks impl bugs (docstring L3142–3145). There is no `timeout` producer anywhere in `src/` (EXECUTED: `grep -rn "ErrorKind.timeout\|ErrorKind.cancelled" src/vfs` returns only `kinds.py`).

### 1.4 The vocabulary (READ, `src/vfs/ops.py`)

`Op` is a 25-member `Literal` (L36–62). Dispatch classes: `MUTATING_OPS` (10), `TWO_PATH_OPS` (2), `READ_OPS` (8), `EXEC_OPS` (`{"run"}`), `GRANT_OPS` (6), `DEVELOPER_OPS = {sweep, posture, add_member, remove_member}` (never on an agent-facing surface, L96). `VERB_RUNGS` (L139) names every verb's rung; `run` sits at `read` with the note "waits for its own axis" — which ADR 084 says is retired. `ALL_OPS` L103 is the drift anchor. There is no `OpGroup` (spec 181's kernel-group axis) yet.

### 1.5 The envelope (READ, `src/vfs/results/`)

`Result` (`envelope.py:316`): three declared fields `ops: tuple[str, ...]`, `observations: list[Observation]`, `errors: list[ResultError]`; `extra="allow"`; `success` is a derived property (no fatal-severity error); set algebra `& | -`, `merge`, `merge_branches`, `sort/top/filter/kinds`, `with_mount/without_mount`, `to_payload/from_payload/to_json/to_str`. The grant verbs' answers ride as undeclared extras `grants=`, `members=`, `relabel=` (protocol docstring `protocol.py:362`). There is no `next_after`, no `status`, no `pending` field.

`ErrorKind` (`kinds.py:28–96`) has 23 kinds in six families. Relevant to this domain: `conflict` (ESTALE; `data` may carry `version`, no producer sets it), `busy`, `budget_exhausted` + `.truncated` + `.authority`, `timeout` (ETIMEDOUT, **no producer**), `cancelled` (ECANCELED/EINTR, **no producer**), `internal`. There is no `pending`, no `input_required`, no `interrupted`. `KIND_CONTRACTS` gives each kind a phrase, `RetryClass` (`never | transient | refresh`) and hint. The namespace partition reserves `vfs.*` for core and `x.<vendor>.*` for backends (L38–41), so a new kernel kind must be `vfs.pending`, not an extension.

`vfs/exceptions.py:121` `raise_if_failed(result)` is the only raise-shaped adapter: it maps a failed `Result` to a `VFSError` subclass. It is still async-agnostic — not a sync facade.

### 1.6 The storage seam (READ, `src/vfs/storage/protocol.py`)

Families: `SupportsRead` (read/stat/ls/tree, the minimum), `SupportsMutation` (the ten mutations incl. mkedge/rmedge), `SupportsPatternSearch` (glob/grep), `SupportsGlean`, `SupportsGraph`, `SupportsRun`, `SupportsGrants`, plus optional `SupportsTraits`, `SupportsReindex`, `SupportsClose`. `StorageBackend = SupportsRead + name + description + capabilities()`. `TRAIT_KEYS` (L71): grep_tier, grep_staleness, glean_signals, glean_staleness, version_encoding, durability, arbitration. No `features()`, no `atomic_unit` trait, no `replay` trait. Every mutation method in the protocol takes whole bodies and no precondition: `write(*, entries, overwrite=True, parents=False, authority=None)` L152.

### 1.7 What exists of the ADR 087 arguments (READ)

| ADR 087 argument | Today |
|---|---|
| `ls/tree/glob(after=, limit=)` + `Result.next_after` | **Absent.** `glob` has `max_count` (a cap, not a cursor); `ls`/`tree` take no limit at all. |
| `read(range=)` | **Absent.** `read` takes `columns` only. |
| `write(if_version=, if_absent=, append=)` | **Absent.** `write` has `overwrite` (bool) and `parents`. `overwrite=False` is create-exclusive on a live occupant (spec 174 §0). |
| `move/copy(replace=)` | **Absent.** Occupant handling is the backend's (`exists`). |
| `request_key` | **Absent.** No `token` ParamKind, no replay store, no `replay` trait. |
| `versions(path)`, `read(path, version=)` | **Absent.** No history read verb; version rows exist (`rows.py:535`) but no verb serves them. |
| `scrub` | **Absent.** `content_hash` is stored (`rows.py:495` index) and never compared on read (EXECUTED, §1.8). |
| `entry_id` on `stat`/`ls` rows | **Absent** from the row projection. |
| `OpGroup`, `features()`, `atomic_unit` trait | **Absent.** |

### 1.8 The three ADR 087 probes are still live defects (EXECUTED)

Script: `/tmp/claude-0/-home-user-vfs/b12de1a3-b6d8-5d68-8b2c-bafd27ab036c/scratchpad/probes.py`, run with `uv run python`, against `VirtualFileSystem(storage=InMemoryStorage(), default_authority=Authority.system())` — `InMemoryStorage` is `DatabaseStorage` over `sqlite+aiosqlite:///:memory:` (`memory.py:32`), so this is the production write path.

```
[lost-update]   20 appends reported success=20/20; lines surviving=1
[rotten-body]   rows corrupted out of band: 1
                read success=True errors=[] content='ROTTEN' stored_hash=b94d27b9934d...
[replayed-move] first:  success=True kinds=[]
                replay: success=False kinds=['vfs.not_found'] data=[None] paths=['/a.txt']
                never:  success=False kinds=['vfs.not_found'] data=[None] paths=['/nope.txt']
```

All three reproduce exactly as ADR 087 §Context describes: twenty concurrent read-then-write appends all succeed and one line survives; a body overwritten with raw SQL reads back as success with the stale hash on the row; a replayed `move` is indistinguishable from a move of a path that never existed (same kind, no `data`).

### 1.9 Sync facade (READ / EXECUTED)

None. `src/vfs/` has no `run_sync`, no `asyncio.run` wrapper, no `SyncSession`; the only `sync` hits in `base.py` are the words "synchronously" in docstrings. `grep -rn -i "jupyter\|sync facade" context/decisions context/specs/active context/architecture` finds one mention: ADR 002 L26 ("`await dbfs.setup()` on the Jupyter kernel loop"). The README's Status (L135) says the *released* 0.0.22 on PyPI ships "sync/async clients" — that is the archived `src2/` generation, not live code.

### 1.10 Interrupts, pending, cancellation, progress (EXECUTED grep)

`grep -rn -i "pending|input_required|elicit|cancel|deadline|interrupt|resum" src/vfs`:

- `pending` — only `render_status = "pending"` (a bytes row not yet rendered, `models/media.py:22`) and posture relabel "pending rows" (`grants.py:369`, `rights.py:188`). Nothing request-shaped.
- `input_required`, `elicit`, `interrupt` — zero hits.
- `cancel` — only asyncio mechanics: `close()` and `_gather_settled` in `base.py`, the lease heartbeat task in `backend.py:1154–1171`. No `ErrorKind.cancelled` is ever minted.
- `deadline` — only grep's internal wall-clock budget (`grep.py:215`, `scope.py:245`, `rendering/markdown.py:100`), which emits `budget_exhausted.truncated` as a **warning** (`grep.py:369`), never `timeout`.
- Progress — nothing (no `progressToken`, no callback, no streaming seam).

### 1.11 How the conformance suite is organised and how many tests pin the surface (READ + EXECUTED)

- `tests/storage/test_conformance.py` (813 lines) only *instantiates* legs: `TestMemoryConformance` (marked `slow`), `TestSqliteConformance`, and Postgres/MariaDB/MSSQL/Oracle classes that skip without `VFS_TEST_<ENGINE>_URL`, each inheriting `StorageContract` + `GrantsContract`; plus ~40 engine-specific regression classes (bind budgets, torn rows, segment cascades, blob columns, ranking pins).
- The contract lives in `tests/support/storage_contract.py` (2,784 lines, **220** `def test_`), sectioned by banner: POSIX parent/site rules; ls/read/tree/stat shapes; the descent ladder; move/copy; edit; delete; restore; sweep; LIKE decoys; enumeration liveness; grep taxonomy; reindex; glean; mkedge; graph; per-row classification; version stamping; batch observations reflect committed state. `tests/support/grants_contract.py` adds **75** tests. The suite is organised by *verb and behaviour*, not by ADR 087's four kernel groups (spec 179 §6 proposes the regroup).
- EXECUTED `uv run --all-extras pytest tests/storage/test_conformance.py --co -q` → **1978 collected, 644 selected** here (1,334 deselected engine-leg tests). Whole suite: **5780 collected, 4332 selected**. Note: a plain `uv run pytest` (without `--all-extras`) fails to *collect* this file — `tests/support/documents.py:15` imports `docx` unconditionally; CLAUDE.md's `uv sync --all-extras --group dev` is required.
- The router surface itself is pinned by `tests/base/*` (**391** tests: dispatch 153, mounts 77, glob namespace 36, mount admin 33, gates 28, grep namespace 23, authority 16, grant routing 14, glean merge 11), `tests/test_ops.py` (20), `tests/test_params.py` (11), `tests/test_authority.py` (19), `tests/results/*` (242), `tests/storage/test_protocol.py` (20).

---

## 2. In flight

| Document | Status line (READ) | What it would change in this domain |
|---|---|---|
| **ADR 087** (`decisions/087-*.md`) | *proposed 2026-10-24*; six pins are leans pending Clay; amended same day by specs 174–181 | Names the kernel = gate + four groups (22 verbs) + derived verbs (`tree`, `edit`, `rmdir`); adds the four arguments (cursor, range, preconditions/append, replace); verify-on-read; replay table + request key; `versions`; `pack`; bounded `sweep`; access-path tables as tests; `Result` gains the resumption key (lean). Pin 1 writes the rights group's last member as `members`; code has `add_member`/`remove_member` and spec 181 keeps the two. |
| **Spec 174** write preconditions | draft, cut 2026-10-24 | `write(if_version=, if_absent=, append=)`, batch `if_versions={path: version}`, `unchanged` status on identical body, `conflict` with `data["version"]`; proposes `overwrite=` leaves `write`. Fixes probe 1. |
| **Spec 175** integrity | draft | sha256 compared on every `read` (and version reads); a fault believed only when two reads agree; every written row returns `content_hash`; a new kind (or `unavailable`, pending Clay); report-only `scrub` (slice D needs 176's key). Fixes probe 2. |
| **Spec 176** listing cursor | draft | `ls/tree/glob(after=, limit=)`, `Result.next_after: Path | None` (declared field, lean), keyset on `(parent_id, name)`, `vfs/results/paging.py` frontier merge for fan-out, text render `more: after=...`. Schema bump. |
| **Spec 177** replay | draft | A pinned per-verb replay table; `move` replay names the occupant by `entry_id`; `request_key: str` (`token` ParamKind, 1–255 printable ASCII) on twelve verbs + `Session`; `replay` trait; a replay store in the mount's schema with 24 h TTL (lean) swept with the trash; in-doubt commit classified apart; `idempotentHint` for MCP. Fixes probe 3. |
| **Spec 178** ranged read | draft | `read(range=(offset, length))` in bytes via the dialect's substring; a row that says its slice; kernel serves it to a backend that cannot. |
| **Spec 179** seam as kernel | draft | Protocols regrouped by kernel group (`SupportsFileRead`, `SupportsFileWrite`, `SupportsCopy`, `SupportsTree`, `SupportsEdit`, `SupportsEdges`, `SupportsTrash`, `SupportsRights`…); `features()`; `atomic_unit` and live `durability` traits; derived ops when a backend lacks them; retry/rights-cache counters; the conformance battery reorganised by kernel operation + mixed-batch, crash-point and access-path families. |
| **Spec 180** history | draft; depends on 176, 175 | `pack` as a `reindex` phase; `sweep(limit=)` with a key; garbage gauge; `versions(path)`; `read(path, version=N)`. |
| **Spec 181** surface regrouped | draft; lands last; depends on 167 slice A, 174, 175, 176, 179 | `OpGroup` in `ops.py`; `entry_id`/`owner_id` read-only on rows; `Result.pipe()` and `vfs/chain.py` replace the rows-in-hand meaning of `observations=` on glob/grep; `base.py`/`session.py`/`params.py` reordered by group; derived verbs documented as facets. |
| **Spec 051** fan-out deadline | draft, 2026-07-07 | A per-dispatch time budget at the fan-out chokepoints; `timeout` per unanswered mount; mutations exempt (lean). Stale: names `VFSErrorKind` and `_spine_tree`, neither exists. |
| **Spec 148** sessions, narrowing, `pending` | seed, 2026-09-06; amended 2026-10-15 | `Session.narrow(profile)`, `child()`, `join()`; the `pending` kind with a request digest + TTL; an **ask ledger** answered through the grant channel (one-shot allowance or grant row); open: ledger in storage per mount or on the router. Amendment: `pending` maps to the MCP tasks extension's `input_required`; `/.vfs/sessions` and `/.vfs/jobs` reserved; close cancels. |
| **Spec 149** serve: token → authority | (not re-read in full) §5 | `pending` on the wire is MRTR's `input_required` with an integrity-protected `requestState` (principal, TTL, digest); "until an ask rung exists, served tools are `complete`-only". |
| **Spec 167** the shell | draft | `VirtualFileSystem.cli(command | argv, *, authority, workdir)` and `Session.cli`; `Session` gains `cwd`, `env`, `last_status`, `history`; `run` and `SupportsRun` removed (slice A); `cli` joins `MANAGEMENT_METHODS`. |
| **Spec 170** tools and MCP servers as views | draft | An elicitation (`input_required`) from a mounted MCP server classifies `vfs.unsupported` (exit 126), citing ADR 084 pin 4 "no ask inside vfs". |
| **Spec 171** MCP adapter | draft | Scope *out*: tasks, MRTR (`input_required`), progress. |
| **ADR 063** session law | accepted 2026-09-06 | Rule 5: "`ask` is a Result, bound to the request": a `pending` kind carrying a digest; an answer is a one-shot allowance or a grant row; timeout is the host's policy. |
| **ADR 084** gate order is the execution policy | proposed 2026-10-15 | Pin 4: "**No `ask` inside vfs.** vfs allows or classifies. A host that wants a human in the loop uses its own tool-permission layer." Pin 9: `cancelled` and `timeout` are the shell's kinds, no new kind. |
| **ADR 082** programs and tools | proposed 2026-10-15 | Pin 12 retires `run` and `SupportsRun`; the MCP tool is "one router-internal gated door". |
| Constitution Art. 2 / Art. 5 (`standards/constitution.md`) | standing | Art. 2 §3 "every listing… MUST accept a limit… with a refine or cursor mechanism"; Art. 5 "Writes declare their conflict mode… Silent clobbering is forbidden"; "Long-running ops expose progress and cancellation when the transport allows. MCP surfaces MUST carry them". |

---

## 3. Gaps versus the 0.1.0 goal

Mapped to Clay's themes.

**Theme 1 — a public kernel API everything goes through, with interrupts.**

- G1. The kernel API is *implicit*: it is `VirtualFileSystem`'s 25 coroutines plus the private gate. There is no `OpGroup`, no stated atomic unit, no declared feature set, and the three probes above are live. ADR 087 is proposed, not accepted; none of specs 174–181 has started.
- G2. There is **no interrupt primitive at all**: no `pending` kind, no resumption token, no ledger, no `resume` entry point, no producer of `cancelled` or `timeout`, no progress seam. The decision records disagree with each other about whether one should exist (§4 R1).
- G3. `Session` is a pure authority facade. Spec 148's narrowing, child sessions and `pending` are a seed from 2026-09 that nobody has scheduled.
- G4. No deadline on fan-out (spec 051, draft since July): one hung remote mount stalls every namespace-wide query, and the `timeout` kind that was reserved for it is unproduced.

**Theme 5 — sync calls for Jupyter and ETL.**

- G5. No sync facade exists in live code. Every public verb is `async def`; the only consumer shapes documented are `await` and `async with`. ETL callers today must run their own loop.

**Theme 6 / 4 / 7 — serve as MCP; three interruptible tool kinds; everything is a file.**

- G6. `run` is still a routed verb with a protocol family (`SupportsRun`) that no shipped storage implements (`tests/base/test_gates.py:172` pins it as `unsupported` on the default root). ADR 082 pin 12 retires it; spec 167 slice A has not landed. Until it does, the drift tests and the README advertise a verb that is dead on arrival.
- G7. Spec 170 maps a mounted MCP server's elicitation to `unsupported`. That is the opposite of "all tool kinds interruptible".

**Theme 2 — storage on four engines.** Out of this audit's domain, but every argument in §1.7 must land on all four legs; spec 176's keyset, 177's replay store and 178's substring each carry a per-dialect spelling.

---

## 4. Risks: wrong, stale, or contradictory

- **R1. Two lines of decision contradict each other on human-in-the-loop.** ADR 063 rule 5 (accepted) and spec 148 §5 / spec 149 §5 define a `pending` Result kind, a request digest and an ask ledger. ADR 084 pin 4 (proposed, later) says "No `ask` inside vfs", the glossary (`architecture/glossary.md:611`) and architecture page 11 repeat it, and spec 170 classifies an upstream elicitation as `unsupported`. Clay's theme 1 ("interrupts/human-in-the-loop like LangGraph tool interrupts") sides with 063/148. A reconciling ADR is needed before any story in §5 can be specified; the roadmap cannot carry both.
- **R2. The constitution is violated by live code and stale in its citations.** Art. 5 "Writes declare their conflict mode… Silent clobbering is forbidden": probe 1 is silent clobbering (EXECUTED). Art. 2 §3 "every listing MUST accept a limit": `ls` and `tree` take none (READ). Art. 5 "MCP surfaces MUST carry progress and cancellation": spec 171 scopes both out. Art. 2 §1 cites `VFSResult` at `src/vfs/results.py:250` and a seven-kind taxonomy; the live type is `Result` with 23 kinds.
- **R3. `run` is retired on paper and live in code.** `ops.py` (`EXEC_OPS`, `VERB_RUNGS["run"]` "waits for its own axis"), `base.py:1571`, `session.py:377`, `protocol.py` `SupportsRun`, `params.py` `"run"`, `README.md:60` ("Execute | `run`") all still carry it. Architecture page 02 correctly flags the drift.
- **R4. Spec 051 is stale and unowned.** It names `VFSErrorKind` and `_spine_tree`, neither of which exists; it leaves both of its `[NEEDS CLARIFICATION]` forks open since July; `timeout` has had no producer for four months.
- **R5. `ErrorKind.cancelled` has no producer and no contract test beyond the vocabulary.** `_gather_settled` re-raises `CancelledError` raw; a front (MCP, shell) that catches cancellation has no classified shape to return. ADR 084 pin 9 says the shell will emit it, so the kernel will have a producer only in a facet — a facet minting a kernel kind is a smell against ADR 087 pin 1.
- **R6. README Status is stale**: "5,266 tests" (live count 5,780); "Released 0.0.22 ships sync/async clients" describes the archived generation; the verb table still lists `run`.
- **R7. `Session.__aenter__` raises `ValueError` on a closed session** (`session.py:64`) while every verb classifies. One raise-shaped door on a facade whose contract is "never raises".
- **R8. The in-process trust tier is a convention** (ADR 087 pin 5, ADR 068): `default_authority=Authority.system()` on the router is the ETL shape, and `Session` cannot prevent a caller reaching `fs` or constructing `Authority.system()`. Any interrupt/ledger design must assume the in-process answerer is trusted code, and the wire is where the wall is.
- **R9. The conformance file does not collect without the `documents` extra** (`tests/support/documents.py:15` `import docx` at module top). A contributor who runs `uv sync` without `--all-extras` loses the entire 1,978-item conformance collection with an `ImportError`, not a skip.
- **R10. Spec 181 §1.6 counts 36 public members; ADR 087 pin 1 counts 22 kernel verbs; `ALL_OPS` is 25.** Three numbers for one surface, all correct on their own terms (25 = 22 + `tree` + `edit` + `run`), but a reader has to do the arithmetic.

---

## 5. Proposed roadmap stories

Ordering follows ADR 087's "order of harm" with the interrupt work inserted where it depends on the replay key.

### K1. Reconcile the ask question: one ADR on interrupts, cancellation and progress

**Why.** R1 blocks everything else in theme 1. ADR 063/spec 148 say a `pending` Result exists; ADR 084 pin 4 says no ask inside vfs. Clay's 0.1.0 theme wants LangGraph-style interrupts across host tools, mounted MCP servers and CLI programs. The ADR must choose, name the kind, say where the ledger lives (storage per mount, as spec 177's replay store does, or the router), and amend ADR 084 pin 4 and spec 170's elicitation row. It should also give `cancelled` and `timeout` their producers (kernel, not facet) so R5 closes.
**Depends on.** Nothing; it unblocks K6–K8.
**Acceptance.**
1. The ADR is accepted and lists the amendments to ADR 084 pin 4, spec 148 §5, spec 149 §5, spec 170 §(failures table), spec 171 scope, glossary L611.
2. `ErrorKind` gains exactly one new core kind for the suspended call (lean: `vfs.pending`, retry class `resume`, a new `RetryClass` value) and `KIND_CONTRACTS` carries its phrase, hint and `path` referent; `tests/results/test_result_laws.py` round-trips it through `to_payload`/`from_payload`.
3. A table in the ADR says, per producer (gate refusal a principal could allow; host tool; mounted MCP elicitation; CLI program), whether the call is suspendable and what the resumption token carries.
4. The ADR states the one model: a kernel call is never held open across an interrupt — it is refused with a ticket and re-driven — and names what a tool must be for that to be correct (restartable under `request_key`).

### K2. Write preconditions and the guarded append (spec 174)

**Why.** Probe 1 is a live data-loss defect on every engine (EXECUTED here on SQLite; spec 174 §0 says the same at `ba77449`). Constitution Art. 5 forbids silent clobbering. `if_version=` is also what `edit`-as-derived-verb, the WASI write-back and the shell's `>>` need.
**Depends on.** ADR 087 accepted (pins 3, 6, 10).
**Acceptance.**
1. `write(if_version=N)` on a row at version N+1 returns `conflict` with `data["version"] == N+1`, issues zero mutation statements (count statements on the SQLAlchemy `before_cursor_execute` hook), on SQLite, Postgres, MSSQL and Oracle legs.
2. Twenty concurrent `write(append=True)` of one line each to one file leave twenty lines; each call commits exactly one version row; a guard miss on a `reprobe` dialect classifies `conflict` and on a `redrive` dialect reruns from a fresh snapshot (counted via the retry counter, spec 179 §5.1).
3. `write(if_absent=True)` on a live occupant is `exists`; on a tombstone it revives (ADR 074 rule 5) and reports `created`.
4. A 10,000-entry batch with `if_versions={...}` and one stale row writes zero rows; statements issued grow by at most one chunked select per `membership_budget`.
5. An identical rewrite reports `unchanged`, leaves `version` untouched and issues no content `INSERT`.
6. `tests/test_params.py::test_every_verb_signature_matches_the_table` holds for the new parameters; `Session.write` forwards them.

### K3. Integrity: verify on read, hash on every written row (spec 175 slices A–C)

**Why.** Probe 2: an out-of-band writer (the ETL job with SQL credentials ADR 087 pin 8 names) is served as success. The hash is already stored and indexed; it is simply never compared.
**Depends on.** K1 only for the kind's name (ADR 087 leaves "its own kind or `unavailable`" pending Clay).
**Acceptance.**
1. After `UPDATE vfs_content SET content='ROTTEN'` the next `read` returns no row content and one error of the chosen kind with `path` the entry; `success is False`, on all four engine legs.
2. A fault is reported only when two reads agree (spec 175 §3.3): the second read is counted as exactly one extra statement.
3. Every row a `write`, `edit`, `copy` or `move` returns carries `content_hash` equal to `hashlib.sha256(body).hexdigest()`; pinned on the memory leg.
4. Bodies ≥ `MEASURE_OFFLOAD_BYTES` hash on a worker thread: `asyncio.to_thread` call count equals the number of large bodies in the batch, zero for small ones (extend `tests/base/test_dispatch.py::test_a_large_body_is_measured_off_the_loop`).

### K4. The listing cursor (spec 176)

**Why.** Constitution Art. 2 §3 is violated today; the MCP tool surface and the shell's `ls`/`find` cannot page; spec 180's `sweep` and spec 175's `scrub` reuse the key.
**Depends on.** ADR 087 pin 12 (Clay: field on `Result` or a pair).
**Acceptance.**
1. `ls(path, limit=1000)` over a 10,000-child directory returns 1,000 rows and `next_after == rows[-1].path`; `ls(path, after=key, limit=1000)` ten times visits each child exactly once; rows visited per page ≤ 1,001 on each engine (counted on the keyset statement).
2. A tombstone between two pages is never emitted and never stalls the key (spec 176 §2.2).
3. `tree` and `glob` page on the same path key; a fan-out over three mounts merges pages by the frontier rule and emits one key.
4. `Result | Result` sets `next_after = None`; `with_mount` rebases it; `render_result` prints `more: after=...` only when set.
5. The MCP projection carries `next_after` in `structuredContent`.

### K5. Replay: the per-verb contract and `request_key` (spec 177)

**Why.** Probe 3: a lost reply leaves an MCP client unable to tell "already moved" from "never existed". `request_key` is also the natural resumption key for K6's interrupts (the ledger row and the replay row are the same shape: a fingerprint of the exact request plus its stored answer).
**Depends on.** K2 (the `unchanged` row of the replay table); K4 for the sweep arm.
**Acceptance.**
1. A replayed `move` returns `not_found` with `data["vfs.occupant"]` naming the destination and its `entry_id`; a move of a never-existing path carries no occupant.
2. Every mutating verb sent twice matches the pinned replay table row (the table is a test, one row per verb, on the memory and sqlite legs).
3. `write(path, content, request_key=k)` twice issues the second time exactly one replay-store select and zero mutation statements, and returns a `Result` equal to the first.
4. A keyed call to a mount without the `replay` trait is `unsupported` at the capability step with the pinned detail.
5. A 10,000-row keyed `write` stores its answer under the dialect's byte budget (packed; spec 177 §3.5) and `sweep` reclaims replay rows older than the TTL, counting rows deleted.
6. A connection lost during `COMMIT` classifies apart from one lost before it (the in-doubt kind), pinned with the `seams` injector on sqlite.

### K6. The `pending` Result and the ask ledger (spec 148 §5 rebuilt on K1 and K5)

**Why.** This is the kernel half of "interrupts like LangGraph". A verb the gate refuses but a principal could allow — and a tool that asks for input — must return a `Result` the caller can hand to a human, and the human's answer must admit exactly one re-run. The design (§6 below) keeps ADR 010 (evidence in, verdict derived), ADR 063 rule 5 (ask is a Result bound to the request), ADR 064 (attributed answers) and spec 177 (the ledger is the replay store's sibling table in the mount's schema).
**Depends on.** K1, K5.
**Acceptance.**
1. `fs.delete("/x", authority=alice)` under a posture alice cannot delete returns `success=False`, one `vfs.pending` error with `data["vfs.interrupt"] = {ticket, digest, expires_at, needs: "grant:read_write@/x"}`, and dispatches zero mutation statements.
2. `fs.answer(ticket, allow=True, authority=bob)` — bob holding `read_write` at `/x` — writes one ledger row attributed to bob (actor and subjects, ADR 064) and no entry row.
3. Re-sending the identical call with `request_key=ticket` proceeds once and commits; the second re-send is refused `pending` again (one-shot spent); an answer from a principal without the right is `permission_denied` and the ledger gains no row.
4. A changed argument (different `path`, `content` or authority shape) produces a different digest and is not admitted by the earlier answer.
5. An expired ticket is `pending` with `data["vfs.interrupt"]["expired"] = True`; `sweep` reclaims expired ledger rows (rows counted).
6. The ledger lives in the mount's schema (one table beside the replay store) so a resume from a second process against the same database succeeds; pinned on the sqlite-file leg with two `DatabaseStorage` instances over one file.
7. `Session.answer` does not exist: the answer channel is the grant channel (ADR 063 rule 2); pinned by the session-surface drift test.

### K7. Cancellation and deadlines as kernel facts (spec 051 rewritten)

**Why.** `timeout` and `cancelled` are reserved and unproduced; one hung mount stalls every fan-out; a front has no classified shape to return on cancel. Constitution Art. 5 asks for cancellation on MCP surfaces.
**Depends on.** K1 (the producer lives in the kernel, not the shell).
**Acceptance.**
1. `grep(pattern, deadline=…)` over one fast mount and one mount whose `grep` never returns yields the fast mount's rows and one `timeout` error with `path` the slow mount's prefix; `success=False`; the slow coroutine is cancelled (count of cancelled tasks = 1).
2. A deadline on a mutation is refused `invalid` (lean (a) of spec 051) or classifies the in-doubt kind — one of the two, pinned.
3. An outer `CancelledError` still re-raises untouched and outranks a timeout (`_gather_settled` contract).
4. A front that catches cancellation can mint `cancelled` through one kernel helper; the renderer's text for it is pinned.
5. No deadline configured → statement counts identical to today on every leg.

### K8. The sync facade for Jupyter and ETL

**Why.** Theme 5. There is no sync entry point in live code. The right shape is a thin facet (ADR 087 pin 1: a front adds only its own machinery) that owns a loop/thread and forwards every verb to the one gate — never a second dispatch path.
**Depends on.** Nothing in the kernel; but it should land after K4/K5 so its surface drift test covers the new arguments once.
**Acceptance.**
1. `vfs.sync.SyncFileSystem(fs)` and `SyncSession` expose exactly the router's `ALL_OPS` and `MANAGEMENT_METHODS` as plain functions (drift test mirrors `tests/test_ops.py:246`); each forwards with the same keyword names (signature test mirrors `tests/test_params.py:28`).
2. A sync call made from inside a running event loop (the Jupyter case) does not deadlock and does not spawn a loop per call: loop/thread creations counted, one per facade.
3. A 10,000-entry `write` through the facade issues the same statement count as the async call.
4. `raise_if_failed` composes: `SyncFileSystem(..., raise_on_failure=True)` maps a failed `Result` to the `VFSError` subclass `exception_for_kind` names.

### K9. Retire `run`; the kernel groups and `entry_id` (spec 167 slice A + spec 181)

**Why.** R3 and R10. `run` has no implementation and ADR 082 retires it; the kernel groups give the conformance suite and the docs one axis; `entry_id` is what K5's replay refusal and K6's ledger name.
**Depends on.** K2–K5 for the arguments the regroup documents.
**Acceptance.**
1. `"run"` leaves `Op`, `EXEC_OPS`, `VERB_RUNGS`, `PARAMS`, `base.py`, `session.py`, `SupportsRun`, `README.md`; `ALL_OPS` has 24 members; `tests/base/test_gates.py:172,182` are replaced by a pin that the name is `unrecognized` on the MCP surface.
2. `OpGroup` in `ops.py` assigns every op exactly one of `filesystem | query | history | rights | derived`; a drift test pins the five sets to ADR 087 pin 1 (with `add_member`/`remove_member` as the two members verbs).
3. `stat` and `ls` rows carry `entry_id` in the populated mask; `write` of an `Entry` carrying `entry_id` is `invalid` (read-only, proved four ways per spec 181 §3.6).
4. The conformance battery is reorganised by kernel operation with no test lost (count before == count after, spec 179 §6.2).

---

## 6. The interrupt design, concretely

How a LangGraph `interrupt()` → `Command(resume=…)` maps onto vfs. Short sentences; the key idea said twice.

**The LangGraph model.** A node calls `interrupt(payload)`. The graph stops and returns the payload. The human answers. The graph re-runs the node *from its start*, and this time `interrupt()` returns the answer instead of stopping. The checkpointer holds the state between the two runs. Nothing is held open in memory across the pause.

**The vfs mapping.** The same shape, with vfs words:

| LangGraph | vfs |
|---|---|
| `interrupt(payload)` | a `Result` with `success=False` and one `vfs.pending` error whose `data["vfs.interrupt"]` is the payload |
| the checkpoint | a ledger row in the mount's schema: `(ticket, digest, authority shape, needs, expires_at, answer, answered_by)` — the replay store's sibling (spec 177 §3.1), swept with the trash |
| `Command(resume=value)` | an attributed answer written through the grant channel (`fs.answer(ticket, …, authority=approver)`), then the caller re-sends the **same** call with `request_key=ticket` |
| the node re-runs from its start | the verb re-enters the gate from `_gate_params`; the gate's storage half consults the ledger in the same transaction that judges rights (one more seek on the ticket) |
| the thread id | `request_key` (spec 177's token) — one value serves replay and resume |

**What the `pending` record carries.** `kind="vfs.pending"`, `severity=error` (so `success` is false and nothing downstream mistakes it for rows), `path` = the entry the request addressed, `data["vfs.interrupt"] = {"ticket": str, "digest": sha256 of (op, canonical args, authority shape, grant revision) per spec 148 §5, "needs": "grant:<rung>@<path>" | "input:<json schema>", "expires_at": iso, "producer": "gate" | "tool:<path>" | "mcp:<mount>"}`. `RetryClass` gains `resume`. The renderer prints the hint "answer the ticket, then resend with request_key=…".

**Who may produce it.** Three producers, one shape:
1. *The gate*, when a refusal is one a principal could lift (spec 148's case). This is a rights refusal with a ticket attached; it costs no statement beyond the refusal's own.
2. *A host-defined tool* (theme 4, kind one). The tool's Python function returns or raises an `Interrupt(payload)`; the router-internal gated door (ADR 082 pin 12) converts it into the `pending` record and writes the ledger row.
3. *A mounted MCP server's elicitation* (theme 4, kind two) and *a CLI program* (kind three). Today spec 170 maps elicitation to `unsupported`; under K1 it becomes `pending` with `producer="mcp:<mount>"` and the elicitation's schema as `needs`.

**What must be true for suspend-and-resume to be correct.**

*In process:* (a) the re-run is a fresh gate pass, so a right revoked between the ask and the answer is honoured (ADR 063 rule 2); (b) the digest is deterministic over canonical arguments — spec 177 §3.3's fingerprint does this already; (c) the answer is attributed and one-shot or a grant row (ADR 063 rule 5, ADR 064); (d) the answerer is trusted code or a principal who holds the right — in process the gate is a convention (R8), so the ledger must record *who* answered, not trust the caller's claim.

*Across a process boundary (MCP):* everything above, plus (e) the ledger is durable in the mount's database, not on the router — a resume may arrive at a different server process; (f) the ticket on the wire is integrity-protected (spec 149 §5's `requestState`) so a client cannot forge an answered ticket; (g) a tool that was interrupted is **restarted, never resumed mid-body**: vfs holds no coroutine open across the pause. A tool that cannot be restarted must keep its own checkpoint as a file under `/.vfs/jobs/<ticket>` (spec 148's reserved view head) and read it on re-run. That is the one honest constraint: vfs gives tools a durable ticket and a durable file, not a frozen stack frame.

*Cancellation and progress* ride the same ticket: `cancel(ticket)` marks the ledger row and the next gate pass refuses `cancelled`; progress is a row under `/.vfs/jobs` the tool updates with ordinary `write(if_version=)` and the client polls with `read` — the MCP tasks extension's `ttlMs` and status map onto it when spec 171 lets tasks in.

**One-line version.** A pending call is a refusal with a ticket; the answer is a grant-channel row; the resume is the same call re-sent with the ticket as its request key; nothing is ever held open.

---

## 7. Open questions Clay must decide

1. **Ask or no ask.** ADR 063/spec 148 (yes, a `pending` kind) versus ADR 084 pin 4 (no ask inside vfs). Theme 1 implies the former; ADR 084 pin 4, spec 170's elicitation row, the glossary and page 11 must be amended if so.
2. **Where the ledger lives**: the mount's schema (durable, survives a process boundary, swept with the trash, like spec 177's replay store) or the router (one per instance, in-process only). The MCP theme forces storage.
3. **The kind's name and retry class**: `vfs.pending` with a new `RetryClass.resume`, or reuse `permission_denied` with a sub-kind (`vfs.permission_denied.pending`) so unknown peers degrade to a denial.
4. **Are tools restarted or resumed?** The design above says restarted under `request_key`; a tool that cannot be restarted checkpoints under `/.vfs/jobs`. Confirm, because it rules out a "frozen coroutine" implementation that some hosts would expect.
5. **The `pending`-producing tool kinds**: do host tools get `Interrupt` as a return value or an exception? Does a CLI program signal it by exit code (ADR 084 pin 5 style) or by a structured stderr line?
6. ADR 087's six leans: `delete`/`move` names; `next_after` on `Result` or a pair; flat names vs groups as namespaces; `move(replace=)` identity; the integrity kind; the replay TTL and `idempotentHint`; `overwrite=` leaving `write`.
7. **Deadline placement** (spec 051): per call, per mount, or both; and whether mutations take one at all.
8. **The sync facade's loop strategy**: a private thread with its own loop (works inside Jupyter), or `asyncio.run` per call (fails inside a running loop).
9. **Constitution refresh**: Art. 2 §1 and Art. 5 cite dead names and promise progress/cancellation on MCP; amend or formally defer.
10. **Does `run` leave before 0.1.0** (spec 167 slice A) so the 0.1.0 surface is the 24 verbs ADR 087 names?
