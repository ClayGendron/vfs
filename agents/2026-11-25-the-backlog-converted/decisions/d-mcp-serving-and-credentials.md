# Decisions verified: MCP servers as the user, vfs serve, MCP tasks, stamps over the wire

Scope: rows D16, D24, D25, D38 and D51 of `context/standards/roadmap.md` section 16, verified on 2026-11-25. EXECUTED: `git rev-parse --short HEAD` printed `09dad59`, not the `0ed462f` the task named; every READ citation below is against the working tree at that commit. EXECUTED: a fetch of `modelcontextprotocol.io` failed, because that host is not reachable from this session's network; every MCP-specification claim below is therefore cited from the repository's own MCP memos and specs, not from the live page.

Common ground. READ `src/vfs/` holds no `mcp/` package, no `cli.py`, and `pyproject.toml` has no `[project.scripts]` table, so no landed work settles any row here. READ D2 (`roadmap.md:1074`): "MCP ships with 0.1.0" (Decided 2026-11-15), so option (iii), the structural cut, is not taken.

## D16. MCP servers that act as the user get their credential from a host-supplied resolver; vfs keeps no credential store, does no token exchange inside `Authority`, and refuses a subject set

Lean (`roadmap.md:1088`): (a) at 0.1.0 (or 0.2 under D2 (iii)); never (c) inside `Authority`; refuse subject sets.

Verification: HOLDS-AMENDED.

Decision text: "A mounted MCP server that acts as the user takes its credential from a host-supplied `CredentialResolver.resolve(server, authority) -> Credential | ResultError`, called at most once per `tools/call` and never during `tools/list`. vfs keeps no credential store. It never forwards the inbound token. It does no token exchange inside `Authority`. It holds one connection per `(server, principal)` in a pool bounded by a declared constant, closing the least recently used connection past the bound and reopening it on the next call. A call under a subject set of more than one principal to a server configured with a resolver is refused `vfs.invalid`, with zero bytes sent."

Reason, part 1. INFERRED: the parenthetical "0.2 under D2 (iii)" is void, because D2 ruled that MCP ships in 0.1.0. That leaves I4 at gate f in 0.1.0 (READ `roadmap.md:408`).

Reason, part 2. INFERRED: the lean as written opens one connection per distinct principal with no bound. At the reference deployment's 1,000 callers, that is up to 1,000 connections per server. For a stdio server it is also up to 1,000 child processes. A pool bounded the way the rights cache is bounded keeps the profile honest without declaring a cap on callers.

Reason, part 3. INFERRED: a set is refused because a per-user server has one credential per principal. Acting on one member's credential would reach what that member holds. The meet law gives a set only the minimum over its members, so one member's reach can be more than the set may have.

Precedent for the resolver (a host-supplied seam).
- READ spec 171 §0 (`171-.../spec.md:35`): the host already supplies the identity seam inbound as `token_verifier=`.
- READ spec 170 §3.1 (`170-.../spec.md:58-61`): the host already supplies `credentials=` per server. Credentials never touch `os.environ`.

Precedent for never forwarding the token, and for no exchange inside `Authority`.
- READ spec 149 rule 4 (`149-.../spec.md:21`): a backend never forwards the inbound token. The two shapes it allows are a trusted subsystem and RFC 8693 token exchange, and both belong to the backend, not to `Authority`.
- READ `src/vfs/authority.py:116-128`: `Authority` holds subjects, actor, provenance, narrowing and source identity. It holds no credential field.
- READ `roadmap.md:410`: the MCP specification forbids forwarding the client's token upstream.
- READ the 2026-10-28 audit (`studies/2026-10-28-the-0-1-0-roadmap-audits/04-shell-tools-mcp-and-wasi.md:327`): RFC 8707 audience binding would refuse a forwarded token anyway.

Precedent for refusing a subject set.
- READ spec 149 rule 2 (`149-.../spec.md:18`): "No token carries a set."
- READ `tests/support/oracles/grants.py:14`: a subject set holds the minimum over its subjects.

Precedent for a catalogue per principal. READ the 2026-08-10 memo (`context/research/2026-08-10-mcp-2026-07-28-stateless-revision.md:106`): "Lists may still vary by the authorization presented."

Precedent for the bounded pool. READ `src/vfs/storage/backends/database/rights.py:261-269`: `RightsCache` evicts the least recently used entry past either of two declared bounds.

Specs affected:
- the new I4 spec, which amends spec 170 §3.1;
- spec 170 (§3.1 and §3.3: the supervisor becomes one task per pooled connection);
- spec 149 (rule 4 is cited and not changed).

## D24. `vfs serve` and `python -m vfs.mcp` ship in 0.1.0, reversing spec 171 decision 7

Lean (`roadmap.md:1096`): Yes.

Verification: HOLDS.

Decision text: "0.1.0 ships the console script `vfs = "vfs.cli:main"` with `serve`, `sh` and `rebuild`, plus `python -m vfs.mcp` with the same flags. All three build the router through one constructor, `vfs.mcp.router_from_url(url, *, embedder=None, workdir="/", authority=None, verifier=None)`. This reverses spec 171 decision 7."

Reason, part 1. READ: spec 171 decision 7 (`171-.../spec.md:18,43`) withheld the command for one reason only: nothing said how to build a router from a URL. M2 (`roadmap.md:779-783`) supplies that constructor, so the reason no longer holds.

Reason, part 2. INFERRED: the command keeps every rule `serve()` already enforces:
- the system actor is refused (`--as system` exits 64 before binding);
- an open mount is refused (exit 78 unless `--allow-open`);
- the core install imports nothing from `mcp`.

Reason, part 3. INFERRED: a URL passed as a host flag is not a connection string inside a path argument, so Article 4 (`constitution.md:111`) is not touched.

Precedent:
- READ `context/research/2026-06-09-direction-and-developer-first-strategy.md:118`: "Ship the CLI and the MCP server as one launch", noting that no `vfs` console script ships.
- READ the 2026-10-28 audit (`04-shell-tools-mcp-and-wasi.md:212,334-336`): the same entry point is named there as story S13.
- The exit codes 64 (`EX_USAGE`) and 78 (`EX_CONFIG`) are BSD `sysexits.h` values. That is a public convention; it was not fetched here.

Specs affected:
- spec 171 (decision 7, the §0 sentence at line 43, and the Scope line 190 "a `vfs serve` console command");
- the new M2 spec.

## D25. A suspended `cli` line is not an MCP task in 0.1.0; a client finds a stopped run through `/.vfs/jobs`

Lean (`roadmap.md:1097`): No.

Verification: HOLDS.

Decision text: "In 0.1.0, `serve()` declares no `io.modelcontextprotocol/tasks` extension and never answers `resultType: "task"`. A `cli` line that stops on an ask returns `input_required` (M3), or a `complete` error result on an older revision. The stopped run is listed under `/.vfs/jobs` and continued through the `answer` and `resume` tools."

Reason, part 1. READ: every `cli` line is bounded by `WALL_TIME_BUDGET`, 10 s (spec 171 §1.4, `171-.../spec.md:93`). So no line runs long enough to need a background handle.

Reason, part 2. READ: a stopped line already has a durable home, the run ledger, and a read view, `/.vfs/jobs` (H4, `roadmap.md:320,331`).

Reason, part 3. READ: cancellation is carried by the core protocol, because closing the response stream cancels the request (2026-08-10 memo, line 54). That meets Article 5's progress-and-cancellation rule (`constitution.md:123`) for a call bounded at 10 s. INFERRED: the MCP surface carries cancellation through stream close, which is what Article 5 asks of it.

Precedent:
- READ 2026-08-10 memo, lines 58 and 87-95: tasks are an optional extension. A server "may legitimately offer neither resumability nor tasks". The extension is not wire-compatible with the 2025-11-25 experimental version. It removed `tasks/list`, so the client is the only registry of its task IDs.
- READ spec 149 rule 5 (`149-.../spec.md:22`): served tools are `complete`-only until an ask rung exists. The ask rides MRTR `input_required`, not tasks.
- READ spec 171 Scope (`171-.../spec.md:190`): tasks are out.
- READ `roadmap.md:1053`: MCP tasks are deferred to 0.2.

Specs affected:
- spec 171 (Scope, unchanged);
- the new M3 and H4 specs;
- spec 148 (its 2026-10-15 amendment says `pending` maps to the tasks extension's `input_required`; the wire mapping is MRTR's core `input_required` instead).

## D38. There is no `/.vfs/mounts` view in 0.1.0; `mounts()` is the API

Lean (`roadmap.md:1110`): No; `mounts()` is the API.

Verification: HOLDS-AMENDED.

Decision text: "0.1.0 serves no `/.vfs/mounts` head. A read of it is `not_found` and a write is `vfs.invalid`, as for any reserved, unserved head. The mount table is read through `mounts()` on the developer plane. A read-only projection rendered under the caller's authority, in the shape of Plan 9's `/proc/n/ns`, is a 0.2 item. The `/.vfs/mounts/data.json` example in the `paths.py` module docstring is removed with T1."

Reason, part 1. READ: `mounts()` (`src/vfs/base.py:695-716`) is replayable, takes no authority, and echoes `permissions`, `deny_ops` and `storage_type` (`base.py:180-204`). Serving it as a view would need a per-caller filter and a decision on what an agent may learn about topology. ADR 022's topology rule, restated in spec 171 §0 (`171-.../spec.md:51`), keeps topology off the agent surface.

Reason, part 2. INFERRED: the amendment adds two things. It names 0.2 for the projection, because Article 3 (`constitution.md:96-98`) says the project SHOULD follow Plan 9, and Plan 9 does print its namespace. It also clears a docstring that documents a file that does not exist.

Precedent:
- READ study 07 (`studies/2026-10-15-agent-shell/07-session-state.md:67,156`): `ls /.vfs/mounts` answers `not_found`. "The mount table stays out of the namespace at v1", with the `/proc/n/ns` projection named as the later shape.
- READ spec 169 §a2 (`169-.../spec.md:58,61`): `mounts()` never reads the view table, and `mounts()` rows are meant to be replayable.
- READ `roadmap.md:1053`: the view is listed for 0.2.
- READ `src/vfs/paths.py:8,14`: the docstring names `/.vfs/mounts/data.json` as a file.

Specs affected:
- spec 169 (T1 criterion 3, and the reserved heads in §a1);
- the docstring of `src/vfs/paths.py`, which T1 already touches.

## D51. Over MCP, the read-before-write guard is the precondition the client carries; `serve()` keeps no stamp table per principal

Lean (`roadmap.md:1123`): keep a bounded, process-local stamp table per principal inside `serve()`, which amends spec 171's "no sessions" to "no session handles".

Verification: FAILS.

Decision text: "`serve()` keeps no stamp table in 0.1.0, and spec 171's no-sessions rule stands unamended. Every row a tool returns carries `version` and `content_hash` in `structuredContent`. The `write`, `edit`, `move` and `delete` tools take `if_version` (K2). Each mutating tool's description tells the model to pass the version it read. The K10 session guard is an in-process `Session` feature and does not reach the wire."

Reason 1: it defeats the guard when one principal runs two conversations. INFERRED: a table keyed by principal is shared by every conversation of that principal. Agent A reads `/a` at v1. Agent B, acting for the same principal, writes `/a` to v2, and the table's stamp moves to v2. A's later write is then filled with `if_version=v2` and overwrites B's change with no conflict. The guard fails silently in the case it exists for. Article 5 (`constitution.md:121`) forbids silent clobbering on a path that declares itself revision-guarded.

Reason 2: there is no connection to sweep with. READ the 2026-08-10 memo, lines 17 and 23: 2026-07-28 has no sessions and is load-balanced round robin with no sticky sessions. A process-local table gives a different answer depending on which instance a request reaches. "Swept with the connection" has no connection to attach to over HTTP.

Precedent for the alternative, which the precedent determines.
- READ 2026-08-10 memo, line 107 (SEP-2567): cross-call state is a value the client carries, and "possession is not authorization".
- READ K10's own Why (`roadmap.md:215`): it names a model's context window as the largest client cache. It also names Anthropic's `content_sha256` and MongoDB's `IfMatch`, which are both preconditions carried by the client.
- READ spec 171 rebase note (`171-.../spec.md:273`): the `write` tool already gains `if_version`.
- READ spec 171 §1.4 (`171-.../spec.md:94`): a sealed session handle is named there as later work. Any wire guard keyed by conversation belongs to that handle, in 0.2, not to a table keyed by principal.

Specs affected:
- spec 171 (§0 identity, §1.3 tool descriptions, and the 174 rebase note);
- the new K10 spec (criterion 8 ends at "stamps never cross the wire");
- the new M1 spec;
- the `roadmap.md:1060` row for 0.2.
