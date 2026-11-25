# A mounted server is called with the credential the host resolves for the caller

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. Checked against `dev` at `27f3d24d`, it serves [story I4](../../context/standards/roadmap.md), gate f, and is the new spec that story calls for. Its source is [spec 170 §3.1](../../context/specifications/archive/170-tools-and-mcp-servers-as-views/spec.md), which it replaces for a server registered with a resolver. It rests on [the MCP client view](../2026-11-25-a-connected-mcp-server-is-a-directory-of-tools-resources-and-prompts/spec.md), [the trust edge](../2026-11-25-a-verified-token-becomes-an-authority-at-the-edge-and-nowhere-else/spec.md), [the verification of D16](../2026-11-25-the-backlog-converted/decisions/d-mcp-serving-and-credentials.md) and [the kernel's records](../2026-11-22-the-kernel-keeps-records-of-its-own/spec.md).

## The outcome wanted

A host registers a server once and gives it a resolver. Ann and Bob then list the server and run its tools. The server sees Ann's credential on Ann's requests and Bob's on Bob's. Each sees the catalogue the server gives that credential, and neither is ever served the other's.

The credential is the host's. It goes from the resolver into one request header and nowhere else. No result, error, row, stored record, log record, shell variable or child process ever holds it. That is seen by tests that plant a unique secret and search every output for it.

A caller the host has no credential for gets `vfs.unauthenticated` at the tool's path, and no byte is sent to the server. A call for a set of subjects is `vfs.invalid`. Both are seen on a transport spy that counts bytes.

The key idea, said once more: the host holds every credential, VFS asks for one at the moment it sends a request, and VFS keeps it only in memory, on the one connection of the one caller it belongs to.

## Builds on

- [The MCP client view](../2026-11-25-a-connected-mcp-server-is-a-directory-of-tools-resources-and-prompts/spec.md), 170-4, a conversion draft, not built. This spec extends it and specifies none of it again. Relied on by decision number:
  - Decision 2: "`add_mcp(name, server, *, list_floor_ms=None, credentials=None) -> None`"; a static bearer is "a secret string"; "Reject credentials or a nonempty explicit environment on stdio before spawning"; "refuse URL userinfo, credential-bearing redirects and an unencrypted non-loopback credentialed endpoint"; "D16's host resolver and per-principal pool are I4's addition."
  - Decision 3: one supervisor task owns one connection; "`MCP_SERVER_LIMIT=64` per router"; "`MCP_IN_FLIGHT=16` per connection"; excess calls are "`vfs.busy`, exit 1, before send"; a failed attempt backs off "from `MCP_RECONNECT_INITIAL_MS=250` to `MCP_RECONNECT_BACKOFF_MS=30000`"; no network wait holds the topology lock.
  - Decision 4: whole immutable snapshots, the list floor `MCP_LIST_FLOOR_MS=30000`, `MCP_LIST_PAGE_BUDGET=64`, and catalogue bytes charged to `TOOL_CATALOGUE_BYTES`.
  - Decision 5: rights at the literal path come first, before a name, a manual or an error is shown.
  - Decision 8: each reply is captured raw and bounded by `MCP_FRAME_BYTES`, and a `tools/call` is sent once and never again.
  - Decision 9: the table of kinds and exits. Decision 10: what a waiting job saves of a tool call. Decision 11: the numbered block files of a call.
- [The trust edge](../2026-11-25-a-verified-token-becomes-an-authority-at-the-edge-and-nowhere-else/spec.md), 149-2, a conversion draft, not built. Decision 7: "Neither success nor failure logs the token or copies it to the authority." Decision 8: "declare `MAX_TOKEN_BYTES = 16 * 1024` for admission in `vfs.authority`". Decision 10: "Neither a token nor an authority nor a claims mapping is attached as extra data."
- [The verification of D16](../2026-11-25-the-backlog-converted/decisions/d-mcp-serving-and-credentials.md), which ends "HOLDS-AMENDED" and adds a bounded pool. D16 itself is a lean on `dev` (`context/standards/roadmap.md:1227`), not a ruling; choice 1 takes it.
- [Catalogue posture](../2026-11-25-a-catalogue-posture-decides-who-may-see-and-who-may-call-a-tool/spec.md), 170-3, a conversion draft: the `list` and `read` rungs at a catalogue path, and the open inventory at "read or above" (its decision 3).
- [The kernel's records](../2026-11-22-the-kernel-keeps-records-of-its-own/spec.md), specified on `dev` and in flight on `origin/the-kernel-keeps-a-store-of-its-own` and `origin/the-kernel-writes-records-behind-and-sweeps-them`. Decision 3: "A place never prints a password", and `RecordPlace` "leaves `url` and `engine_arguments` out of its `repr`". Decision 21: "no session, policy or tool can reach it."
- [The stored session](../2026-11-22-a-session-is-stored-named-and-forked/spec.md), specified on `dev`, not built. Decision 6: "The owner is the actor and the subjects", and "a token renewed with other scopes is the same caller."
- [The interrupted line](../2026-11-22-an-interrupted-line-replays-its-replies/spec.md), specified on `dev`, not built: "VFS keeps the line's text, its standard input, its environment and its replies while the job waits." [The job contract](../2026-11-22-a-job-is-interrupted-and-resumed/spec.md), decision 7: "The owner of a job is the authority that made the call".
- Story H0, the action log, has no spec. Its rule (ii) on `dev` reads "Never a body, never a credential, never a token" (`context/standards/roadmap.md:304`), and its criterion 5 searches every log row for secret bytes (`:309`). Story X7's search of every log record is not built (`:977-983`).
- Built on `dev`: `Authority` and its five fields (`src/vfs/authority.py:119-131`), `owner_subject` (`:205-216`), the one construction of an error (`src/vfs/results/envelope.py:239-285`), a line's fixed environment (`src/vfs/shell/host.py:51-57`) and `WALL_TIME_BUDGET` (`src/vfs/deadline.py:36`).
- Build order: 149-1 and 149-2; 170-1, 170-2, 170-3 and 170-4 with its three studies; H0; the kernel store's landings; then this spec. Gate f follows gate b, so each of those is due first. The test of the inbound token also needs 171-2's served request.

## Terms

- **Credential.** A secret the host holds that a server accepts as proof of who is calling. Here it is a bearer token.
- **Resolver.** The host's object that answers, for a server and an authority, with that caller's credential.
- **Per-user server.** A server registered with a resolver. A **static server** is one registered with one credential or none, as 170-4 specifies.
- **Caller.** For a per-user server: an authority's actor and its one subject, taken together.
- **Carrier.** The one object on a connection that writes the credential into a request's `Authorization` header.
- **Canary.** A unique secret string that a test plants and then searches for in everything VFS produced.

## What the code does today

Read at `27f3d24d`. A line marked run was executed on 2026-11-25 with Python 3.13.18 on a SQLite storage in memory.

- Nothing of this unit exists. A search of `src/` and `tests/` for `CredentialResolver`, `class Credential`, `add_mcp`, `TokenVerifier` and `authority_from_token` finds nothing (run). The `mcp` and `httpx2` packages are not installed; `httpx` 0.28.1 is (run).
- An `Authority` holds subjects, an actor, a provenance, a narrowing and a source identity, and no credential (`src/vfs/authority.py:127-131`). Its `repr` prints every principal's name (run). `owner_subject` already answers `None` for a set, for the system actor and for the anonymous caller (`:205-216`).
- **An exception's text reaches a result today.** The router builds a detail from a transport exception's own words (`src/vfs/base.py:2979`, `src/vfs/mounts.py:369`). So do the search leg for an embedder's exception (`src/vfs/storage/backends/database/backend.py:654`), the renderer seam (`src/vfs/rendering/seam.py:285-286`) and the engine's classifier (`src/vfs/storage/backends/database/engine.py:392-399`). Run: a storage whose `read` raised `TransportError` with a canary in its text returned `vfs.unavailable.backend`, and the canary was in the error's `message`, in `to_payload()` and in `to_str()`.
- **An error is an open record.** `ResultError` allows extra fields and carries a free `data` mapping (`src/vfs/results/envelope.py:113`, `:120`), and `Result` allows extras too (`:362`). `to_payload` writes all of it (`:747-770`). Run: a canary in `data` and one in an extra field both survived `to_payload` and `from_payload`.
- **A line's environment is fixed.** A line starts with `HOME`, `PATH`, `LC_ALL` and `TZ` (`src/vfs/shell/host.py:51-57`) and `PWD` (`:222`). `cli` takes no environment argument (`src/vfs/base.py:1668-1677`). Run: with a canary in `os.environ`, `export -p`, `declare -x` and `set` printed those five names and shell variables only, and `$VFS_PROBE_SECRET` expanded to nothing.
- **Three log sites exist.** `src/vfs/authority.py:242` and `:256`, and `src/vfs/storage/backends/database/engine.py:201`. None logs an argument, and the first names "the kind of the default's actor, never its name" (`src/vfs/authority.py:230-232`). A lint test holds every logger to its module's name (`tests/lint/test_code_shape.py:556`). Run: the probes above wrote no record on any `vfs` logger.
- **The kernel store is not on `dev`.** There is no `src/vfs/kernel_store`. On its branch every record is written through `insert_rows` and `put_behind` (`origin/the-kernel-writes-records-behind-and-sweeps-them:src/vfs/kernel_store/store.py:281`, `:389`). There is no action log in the tree.
- **The SDK**, read at [python-sdk `77001c96`, MIT](https://github.com/modelcontextprotocol/python-sdk/tree/77001c96f9507be0f4d009b83210a384a5e08bda), the revision 170-4 pins. `streamable_http_client(url, *, http_client=None, ...)` takes a prepared HTTP client, and its docstring says headers and authentication are configured there (`src/mcp/client/streamable_http.py:713-733`). `create_mcp_http_client(headers, timeout, auth)` builds one with an auth handler (`src/mcp/shared/_httpx_utils.py:32-64`). A redirect is followed only inside the endpoint's origin (`:67-131`). The transport logs each outgoing JSON-RPC message at `DEBUG` and the endpoint URL (`streamable_http.py:635`, `:756`); it logs no header. A client's response cache defaults to a store of its own in memory (`src/mcp/client/client.py:423-431`). A stdio child inherits six named variables of the process and any the caller adds (`src/mcp/client/stdio.py:40-58`, `:76-91`, `:129`).
- **`httpx` 0.28.1**, run as a stand-in for `httpx2`. The `repr` of a request's headers hides the `Authorization` value. An auth flow sees each response's status. With `HTTP_PROXY` set, a plain-http request to `127.0.0.1` is routed to the proxy, and with `trust_env=False` it is not.

## The problem

Spec 170 gave a server one credential. Every caller who may run its tools then acts as the host, so a result can carry data the caller's own account at that server would never show. Story I4 asks for the opposite: each caller acts as itself.

That puts a second kind of secret inside VFS. The first kind, a database password, sits in one URL, which `url_of_engine` keeps out of its own error (`src/vfs/storage/backends/database/drivers.py:78-94`). This kind is per caller, arrives on every tool call, and passes next to code whose habit is to copy text outward. The probes above show two such habits on `dev`: an exception's words become an error's message, and an error's `data` and extras cross the wire unexamined. A resolver is host code that can raise, and a transport error names its request, so both habits lead straight to a leak.

It also multiplies state. At the reference deployment 1,000 people and their agents call a server. One connection each, kept for ever, is 1,000 sockets and 1,000 catalogues for one server. A read must not wait on another caller's connection being opened, and no caller may ever be served another's catalogue or body.

## Decisions

1. **The credential comes from the host, and VFS keeps none.** D16's lean (a) is taken, as its verification amends it; choice 1. A per-user server takes its credential from a resolver the host supplies. VFS has no credential store, does no token exchange, never forwards a token it was sent, and refuses a call for a set of subjects. Reason: `Authority` has no field that could hold a credential (`src/vfs/authority.py:127-131`), so identity and proof stay apart; and the host already supplies the identity seam inbound (149-2 decision 6). OAuth on demand is story T7, at 0.2 (`context/standards/roadmap.md:850`).

2. **Two public names, in a core module that needs no extra.** `src/vfs/credentials.py` holds `Credential` and `CredentialResolver`, and both are exported from `vfs`. The module imports `vfs.authority` and `vfs.results` and nothing else, and joins `LAYERS` on the rung of `vfs.pattern_matching`, above `vfs.results` and below `vfs.base`. Reason: `add_mcp` is a method of the router, a type that a public signature names is public (`documentation/maintainers/how-we-name.md`, "Public and private"), and `vfs.base` may not import the optional `vfs.mcp` package, which 149-2 decision 9 places above the public faces. The resolver is a structural protocol with one method, as 149-2's `TokenVerifier` is:

   ```python
   @runtime_checkable
   class CredentialResolver(Protocol):
       async def resolve(self, server: str, authority: Authority) -> Credential | ResultError | None: ...
   ```

   `server` is the name given to `add_mcp`, never a URL. The method is `async` only, as policies and tools are (`agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md:50`). It may be called by many calls at once.

3. **A `Credential` shows nothing of itself.** It is made only by `Credential.bearer(token)`; the bare constructor raises `TypeError`. The token must be a `str` of the RFC 6750 `b64token` grammar, from `CREDENTIAL_MIN_CHARS = 16`, declared in this module, to 149-2's `MAX_TOKEN_BYTES` characters. Any other value raises `ValueError` whose text never repeats the input. The grammar keeps a carriage return or a line feed out of the header. The floor keeps decision 13's search from matching ordinary words.
   - `repr`, `str` and every format of it give `Credential(bearer=<hidden>)`.
   - It has slots and no `__dict__`, and it is frozen. It refuses `pickle`. `copy` and `deepcopy` return the same object. Equality is identity, so no comparison of secrets is offered.
   - It has two readers and no other. `write_header(headers)` sets `Authorization` on a mapping it is handed. `found_in(data)` says whether a `str` or `bytes` value holds the secret. Neither returns the secret, so once `bearer` has returned, no frame of VFS holds the secret under a name.
   - Put by mistake in an error's `data`, it stops `to_payload` with a serialization error that does not name the secret.

   Precedent: `RecordPlace` hides its URL from its `repr` (kernel records, decision 3). A prototype of this class was run against the real envelope: nine renderings, `pickle`, `vars`, `copy` and `to_payload` behaved as written above.

4. **`credentials=` takes four shapes, and a per-user server is registered without connecting.** `None` and a static credential are 170-4's. A `str` is wrapped by `Credential.bearer` as `add_mcp`'s first act and the argument's name is bound to the wrapped value, so no plain string is kept and no later frame holds one. A `Credential` is a static credential. An object with a `resolve` method makes a per-user server. Anything else raises `TypeError`. A credential of either kind with stdio parameters raises `ValueError` before any process is started, and so does one for a plain-http endpoint that is not loopback, or a URL with userinfo; that is 170-4 decision 2, extended to a resolver. `add_mcp` for a per-user server validates, reserves the name, publishes the server's three directories and returns. It opens no connection, because no caller exists yet. This departs from 170-4 decision 2, which connects at registration; a per-user server that cannot be reached is found by the first caller's operation, as `vfs.unavailable.backend`. The synchronous face takes the same four shapes, and a resolver is awaited on the router's own loop.

5. **The caller of a per-user server is one actor and one subject.** The connection key is the pair `(actor.sub, subject.sub)`, read from the authority that `caller_for` returns. A principal's kind and scopes, the provenance, the narrowing and the source identity are not in it. Reason and precedent: this is what the stored session's owner key holds (its decision 6), so a token renewed with other scopes keeps its connection, and an agent acting for Ann never shares one with Ann acting for herself. An authority that is not one such pair is refused before the resolver is asked and before any byte is sent:

   | Authority | Result at the path | Exit | Detail, fixed |
   |---|---|---|---|
   | More than one subject | `vfs.invalid` | 2 | "a server that acts as its caller takes one subject; this authority names several" |
   | The system actor | `vfs.invalid` | 2 | "a server that acts as its caller needs a named caller; the system actor names none" |
   | The anonymous caller | `vfs.unauthenticated` | 126 | "this server acts as a named caller" |

   A set is refused because one member's credential reaches what that member holds, and a set may hold only the least of its members (`tests/support/oracles/grants.py:14`). `unauthenticated` already reads as "Permission denied" in a line (`src/vfs/shell/programs.py:131`, `src/vfs/shell/host.py:99`).

6. **Every local refusal comes before the resolver.** A call to a per-user server passes these gates in this order. The first four ask the resolver nothing and send nothing.

   | Gate | Refusal |
   |---|---|
   | Rights at the literal path, as 170-3 and 170-4 decision 5 rule | `vfs.not_found` 127 below `list`, `vfs.permission_denied` 126 below `read` |
   | The caller's shape, decision 5 | the table above |
   | Room in the pool, a check that closes nothing, decision 9 | `vfs.busy` 1 |
   | With a live snapshot: the tool's presence and the binding of its arguments | `vfs.not_found` 127, `vfs.invalid` 2 |
   | The resolver, once, decision 7 | decision 8 |
   | The open, when the caller has no live connection, then the fourth gate for a caller who had no snapshot | `vfs.unavailable.backend` 1, `vfs.unauthenticated` 126 |
   | The send | 170-4 decision 9 |

   Reason: a caller who may not see a tool must learn nothing, the host's resolver included, and a refusal that VFS can give alone should cost the host nothing. A policy judges the step before the first gate and sees a path and arguments, never a credential.

7. **The resolver is asked when a request is about to be sent, and never by a list refresh.** It is asked exactly once by each `tools/call` request and each `resources/read` request, after the local gates and before the first byte. It is asked once more only by an operation that must open a caller's connection and is neither of those: a read of the catalogue by a caller with no live connection. When one call both opens and calls, one answer serves both. A refresh of a list on a live connection, a cache hit and a close ask nothing. The resolver is handed the server's name and the authority, and nothing else: no request, no header, no token. It is awaited under the call's own wall, the tighter of the line's deadline and `WALL_TIME_BUDGET`, and outside every lock. A continuation of a waiting job (170-4 decision 10) is a `tools/call` request: it asks once, for the authority the job records as its owner, and the saved part of the job holds no credential and no answer. Reason: asking at each call lets the host hand out a short-lived token with no failed call at its expiry. Departure: I4's first criterion says "never during `tools/list`"; this reads it as "a list is never a reason to ask", because story T4's third criterion has `ls` issue one `tools/list` "per server and principal" (`context/standards/roadmap.md:821`), which no caller can send before a credential exists. Choice 2.

8. **An answer is a credential, or the call ends with a fixed fact.**

   | The resolver | Result at the path | Exit | Detail, fixed |
   |---|---|---|---|
   | returns a `Credential` | the call goes on | | |
   | returns `None` or a `ResultError` | `vfs.unauthenticated` | 126 | "the host holds no credential for this caller on this server" |
   | raises, or returns anything else, a bare `str` included | `vfs.unavailable` | 1 | "the host's credential resolver failed" |
   | is still running when the wall passes | `vfs.timeout` | 124 | none |

   In every row but the first, zero bytes are sent and no connection is opened or closed. A returned `ResultError` is not passed on: its message and data are the host's words, and they stop here. A raised exception is not read: not its text, not its arguments, not its cause. One `WARNING` names the server and the exception's class. A cancellation is passed through. A bare string is refused because a string that is not a secret, an error text say, would otherwise be sent as one. Precedent: raw errors are mapped before they cross the public boundary (`context/standards/constitution.md:84`).

9. **One connection per server and caller, in one bounded pool per router.** Each is a supervisor of 170-4 decision 3, with its own snapshot, its own list floor, its own body cache and a response cache store of its own in the SDK's client. `src/vfs/mcp/pool.py` declares `MCP_CALLER_CONNECTIONS: Final = 256`, the most per-caller connections a router holds across all its per-user servers. Static servers are outside it, under `MCP_SERVER_LIMIT`.
   - An open that finds the pool full closes the idle connection used least recently, where idle means no request pending or running. Room is made at the open and never earlier: a prototype that made room before it asked the resolver let a caller with no credential close another caller's connection.
   - With every connection busy, the operation is `vfs.busy`, exit 1, before the resolver, as 170-4 refuses excess work.
   - Concurrent first operations of one caller share one open. Each call still asks the resolver for itself.
   - A snapshot is charged to `TOOL_CATALOGUE_BYTES`. One that does not fit closes idle per-caller connections, least recently used first, and then refuses `vfs.busy`.
   - A caller whose open failed keeps an entry holding only its next eligible instant, by 170-4's backoff. It counts toward the bound and is closed like any idle one.
   - `remove_mcp` and `close` close every connection of the server, as 170-4 closes one, and drop each carrier.

   Reason: the verification of D16 costs an unbounded pool at 1,000 connections a server and takes the rights cache's bound as precedent (`src/vfs/storage/backends/database/rights.py:261-269`). The bound is a cache size and never a limit on callers: a closed connection is opened again by its caller's next operation.

10. **The credential travels in one header, to one origin.** Each connection's HTTP client is built with one carrier, an `httpx2.Auth`; a static server's one connection is carried the same way. The carrier holds the credential last resolved for its caller, in memory, for the life of the connection. A list refresh and the session's closing `DELETE` send that one. The carrier writes the header only on a request to the endpoint's own origin, or to its https form on the same host, and leaves any other request bare. The credential is never put in a URL, a JSON-RPC field, `_meta`, an argument, a word of a line, a variable, standard input or a process environment. A client for a plain-http loopback endpoint is built with `trust_env=False`, so a proxy named by the environment never receives the header; an https endpoint keeps the environment's proxy, since the header then travels inside the tunnel. The credential's memory is released when the carrier is dropped; Python gives no way to wipe a string, and the docs say so.

11. **A request the server refuses with 401 closes that caller's connection, and nothing is sent twice.** The carrier sees each response's status in its own flow, so this needs no reading of the SDK's errors. The operation is `vfs.unauthenticated` at its path, exit 126, with the fixed detail "the server refused this caller's credential". A `tools/call` is never sent again, as 170-4 decision 8 rules. A call or a resource read carried a credential asked for at that moment, so its 401 is final. A catalogue read whose refresh drew the 401 opens the connection once more in the same operation, which asks the resolver once, because a list is safe to send again; a second 401 ends it. A 401 at an open counts as a failed attempt for 170-4's backoff, and before the next eligible instant the caller's operations answer the same fact with no resolver call and no byte. A 403 is the server's own refusal and stays in 170-4's table.

12. **Each caller reads its own catalogue.** `ls /.vfs/mcp` and the three directory names under a server are served from the registration, to any caller the posture lets list them, with no connection. Every entry beneath them is read from the caller's own snapshot, and a caller with none opens its connection first. A tool another caller's listing holds and this caller's does not is `vfs.not_found`, 127, with zero bytes sent, the same as a name no caller has. A listing rooted above a per-user server keeps its other rows: a server whose inside could not be read shows its three directories, and what stopped it is one record at the server's path with severity `warning`, except `vfs.unauthenticated`, which is dropped as a mount's denial is (`src/vfs/listing.py:563-571`). A per-user server adds no path to the open inventory of 170-3 decision 3, because the anonymous caller is refused whatever the posture.

13. **A reply that holds the credential is withheld.** Before 170-4's adapter makes a row, every string of the captured reply and every decoded block of bytes is searched with `found_in` for the credential its request carried. This covers a `tools/call` reply, a `resources/read` reply, a list page and a JSON-RPC error. On a hit the whole reply is dropped. The call is `vfs.unavailable.backend`, exit 1, not retryable, with the fixed detail "the server's reply held the caller's credential and was withheld", and one `WARNING` names the server. A list page with a hit is a failed refresh and publishes nothing. Static servers are searched the same way. Reason: once VFS's own code is clean, an echo from the server is the one way left for the credential to reach a row, a stored reply or a model. The search finds the exact text only. A server that returns the credential encoded or split is not caught, and the docs say so.

14. **No detail, datum or log record is made from material that could hold a credential.** On an MCP connection, and around the resolver, every error detail is one of a fixed set of phrases chosen by what happened; the tables of decisions 5, 8, 11 and 13 are that set, beside 170-4's. No exception's text, no header, no URL and no part of a request is copied into a `message`, a `data` key or an extra field. `data` carries nothing about a credential: not its scheme, its length, its expiry or a hash of it. This departs, for this path only, from the pattern at `src/vfs/base.py:2979`. The module's logger is `vfs.mcp.pool`. It writes a server's name, a count and an exception's class name, at `WARNING` for decisions 8 and 13 and at `DEBUG` for an open, a close and an eviction. It never writes a caller's name, following `src/vfs/authority.py:230-232`.

15. **Each place a credential could reach is closed by name.** Every row has at least one leak test under Tests.

    | Place | Where it is on `dev` | Decided | Leak test |
    |---|---|---|---|
    | An error's message | `src/vfs/base.py:2979`, `src/vfs/mounts.py:369`, `backend.py:654`, `rendering/seam.py:285-286`, `engine.py:392-399` | Decision 14: fixed phrases, no exception text | `test_no_error_holds_the_credential` |
    | A `Result`, its `data`, its extras and its payload | `src/vfs/results/envelope.py:113`, `:120`, `:362`, `:747-770` | Decisions 3 and 14: nothing is attached, and the value cannot be serialized | `test_no_result_or_payload_holds_the_credential`, `test_a_credential_cannot_enter_a_payload` |
    | The rows of a tool's reply, a resource body, a manual | 170-4 decisions 6, 7 and 11; not built | Decision 13: the reply is searched and withheld | `test_a_reply_that_holds_the_credential_is_withheld` |
    | A kernel store record: a job, its pages, a line's replies, a session's shell state, a run's blocks | not on `dev`; `agents/2026-11-22-the-kernel-keeps-records-of-its-own/spec.md:96`; `origin/the-kernel-writes-records-behind-and-sweeps-them:src/vfs/kernel_store/store.py:281`, `:389` | No table gains a column. A job saves no credential and asks again when resumed. What a record holds of a call is its result, which the rows above keep clean | `test_no_kernel_record_holds_a_credential` |
    | An action log row | no code; `context/standards/roadmap.md:304`, `:309` | A `run` row holds what any `run` row holds. The resolver's call is not a row, and no row says whether one was asked | `test_no_action_log_row_holds_a_credential` |
    | A Python log record, VFS's or the SDK's | `src/vfs/authority.py:242`, `:256`; `engine.py:201`; SDK `streamable_http.py:635`, `:756` | Decisions 10 and 14: the header is logged by no one, and the credential is in no message or URL | `test_no_log_record_at_any_level_holds_the_credential` |
    | A line's environment, words and input, and what a waiting job stores of them | `src/vfs/shell/host.py:51-57`, `:191`, `:222`; `src/vfs/base.py:1668-1677` | Decision 10: no variable, word or input is ever made from it | `test_a_line_never_sees_the_credential` |
    | A stdio child's environment and arguments | SDK `stdio.py:40-58`, `:129`; 170-4 decision 2 | Decision 4: no credential is accepted for stdio, and another server's child inherits nothing | `test_no_stdio_child_sees_a_credential` |
    | A proxy the process environment names | `httpx` 0.28.1, run | Decision 10: `trust_env=False` on plain-http loopback | `test_a_loopback_credential_goes_to_no_proxy` |
    | `repr`, `str`, format, `pickle` and copy of the value | no such type | Decision 3 | `test_a_credential_shows_nothing_of_itself` |
    | `repr` of what holds it: the carrier, the connection, the pool, the request | `httpx` 0.28.1, run for the request | No holder prints a field; the request's header is hidden by its own `repr` | `test_no_holder_prints_the_credential` |
    | A traceback printed with its locals | none | Decision 3: the secret is bound to no local name | `test_a_traceback_with_locals_holds_no_credential` |
    | An exception `add_mcp` or `Credential.bearer` raises | none | Decisions 3 and 4: the text never repeats the input | `test_a_bearer_is_checked_before_it_is_kept`, `test_add_mcp_takes_four_shapes_and_refuses_what_it_cannot_carry` |
    | Another caller: a snapshot, a body, a cached response, a connection | SDK `client.py:423-431`; 170-4 decision 4 | Decisions 5, 9 and 12: every one is per connection, and a connection is one caller's | `test_two_callers_share_nothing` |
    | The server, receiving the token a caller sent to VFS | 149-2 decisions 7 and 10 | Decision 16 | `test_the_inbound_bearer_is_never_sent_upstream` |

16. **The token a caller sent to VFS is never an input here.** VFS hands the resolver an `Authority`, which cannot hold a token, and VFS itself keeps the inbound token nowhere (149-2 decisions 7 and 10). So forwarding is not something VFS can do. A host that returned the inbound token from its resolver would be forwarding it by its own hand; the docs name that as forbidden by the MCP specification (`context/standards/roadmap.md:446`).

## Cost

No statement is added on SQLite, on Postgres or on the generic floor. No table, column, index or lock is added, and neither schema format changes. The rights checks of a call are 170-1's and 170-3's, in their chunks of `membership_budget`, unchanged. Everything this spec adds is in memory or on the network, so the least generous engine sets no budget here.

- **Per verb call**, about 150,000 a day. A tool call or a resource read adds one awaited call of the host's resolver, inside the call's own wall, and zero statements. A catalogue read on a live connection adds nothing but a refresh that is due. The search of decision 13 is one pass over a reply already bounded by `MCP_FRAME_BYTES`.
- **Connections.** At most `MCP_CALLER_CONNECTIONS`, 256, beside at most `MCP_SERVER_LIMIT` static ones. At the peak of about 20 calls a second, with a call bounded by `WALL_TIME_BUDGET` of 10 seconds, at most 200 calls are in flight even if every call were a tool call that ran to its wall. So 256 places hold every busy caller and `vfs.busy` is not reached at the reference deployment.
- **Opens.** An open is one negotiation and one list walk of at most four methods of `MCP_LIST_PAGE_BUDGET` pages. With 1,000 callers on 256 places, a caller that returns after being closed pays one open. Opens never exceed operations, and a caller who opens once a session, at 2 to 5 sessions a day, is 2,000 to 5,000 opens a day against 150,000 calls.
- **Refreshes.** A refresh is started only by an operation and at most once a floor on each connection, so list walks never exceed catalogue reads.
- **Memory.** Every snapshot is charged to `TOOL_CATALOGUE_BYTES`, so the catalogues of all callers together are bounded by the one budget 170-4 already declares. A carrier holds one credential of at most `MAX_TOKEN_BYTES`.
- **Waiting.** A read never waits on a writer: no statement is involved. A caller's operation waits only on that caller's own open. The pool's bookkeeping is done between awaits and holds no lock another caller needs. The resolver and the open are awaited outside the topology lock, as 170-4 decision 3 requires.

A recursive listing from `/.vfs/mcp` opens each per-user server it reaches, at most `MCP_SERVER_LIMIT`, and asks the resolver once for each.

## Left as it is

- A static server: one credential, one connection, one catalogue for every caller, eager at `add_mcp`. That is 170-4, and spec 170 §3.1 stands for it.
- A stdio server takes no credential of either kind.
- `Authority` gains no field. `ResultError` and `Result` stay open records; the guards are at the producers.
- The details built from exception text at the five sites named above belong to their own owners and are not changed.
- A line's environment and `cli`'s signature.
- The kernel store's tables and format, and the action log's row.
- Story X7's search of every log record across the whole suite. This spec's canaries are written so that search can take them.

## Tests

Written first and seen failing. They count calls, requests, bytes and connections on a transport spy and a resolver spy, with 170-4's injected clock; none reads a clock. `tests/support/canaries.py` holds one canary for each caller, one static, one inbound, and `assert_no_canary`, which searches text and bytes. The server is 170-4's in-process streamable HTTP fixture.

- `tests/test_credentials.py::test_a_credential_shows_nothing_of_itself`: every rendering, `pickle`, `vars`, attribute assignment, `copy` and `deepcopy`. `::test_a_bearer_is_checked_before_it_is_kept`: the empty string, 15 and 16 characters, the bound and one past it, a space, a carriage return and line feed, a non-string; no message repeats its input. `::test_a_credential_cannot_enter_a_payload`: one placed in `data` stops `to_payload`, and `repr` of the result hides it.
- `tests/test_package.py::test_the_credential_names_import_without_the_extra`: a fresh process with `mcp` and `httpx2` blocked imports both names from `vfs`. `tests/lint/test_code_shape.py::test_imports_point_down_the_ladder` holds the new rung.
- `tests/mcp/test_pool.py::test_add_mcp_takes_four_shapes_and_refuses_what_it_cannot_carry`: each shape; a credential with stdio, with plain http off loopback and with userinfo, each refusal's text searched for the canary; zero processes started, and zero connections opened for a per-user server.
- `tests/mcp/test_pool.py::test_the_resolver_is_asked_once_a_call_and_never_by_a_refresh`: 100 calls by one caller are 100 resolver calls, one `initialize` and one `tools/list` inside the floor; a second caller adds one of each; five refreshes past the floor add five `tools/list` and zero resolver calls; a first listing by a caller with no connection is one resolver call; ten first calls at once are one open; a resource read asks once and its cache hit asks nothing; the resolver's arguments are a `str` and an `Authority`.
- `tests/mcp/test_pool.py::test_a_missing_credential_sends_no_byte`: `None`, a returned error and a wall that passes; the kind, the path, the exit through a line, zero bytes on the spy, zero connections opened or closed.
- `tests/mcp/test_pool.py::test_a_set_the_system_actor_and_the_anonymous_caller_are_refused_first`: the three rows of decision 5, for a call and for a listing; zero resolver calls, zero bytes.
- `tests/mcp/test_pool.py::test_a_resolver_that_raises_discloses_nothing`: an exception whose text, arguments and cause hold a canary, and a returned bare string; `vfs.unavailable` with the fixed detail; one `WARNING` holding the class name; the canary nowhere.
- `tests/mcp/test_pool.py::test_the_pool_is_bounded_and_a_closed_caller_opens_again`: with the bound patched to 3, a fourth caller closes exactly one idle connection; a caller with no credential closes none; the closed caller's next call is one `initialize`; with every connection in flight the answer is `vfs.busy` and zero resolver calls.
- `tests/mcp/test_pool.py::test_a_401_closes_one_callers_connection_and_resends_nothing`: on a call, one `tools/call` sent and none after; on a refresh, one reopen and one resolver call; twice refused, `vfs.unauthenticated`; the other caller's connection untouched.
- `tests/base/test_mcp_view.py::test_a_caller_without_read_never_reaches_the_resolver`: at `none` and at `list`, across `ls`, `stat`, `read`, `glob`, `grep` and `run`; rows, errors and exits equal those of a server that does not exist or a tool that does not; zero resolver calls and zero bytes.
- `tests/base/test_mcp_view.py::test_two_callers_share_nothing`: a server that varies its listing and a resource body by bearer. Each caller's `ls`, `stat` hash, manual, body and tool reply are its own; a tool only Ann's listing holds is `vfs.not_found` for Bob with zero bytes; an agent acting for Ann has a third connection; a spy on every cache counts zero hits across callers.
- `tests/mcp/test_credential_leaks.py`, each on a flow of two callers, a static server, a failed call, a refused call and a recursive listing:
  - `::test_no_error_holds_the_credential` and `::test_no_result_or_payload_holds_the_credential` search every `Result`, its `to_str`, its payload and each error's fields.
  - `::test_a_reply_that_holds_the_credential_is_withheld` covers a text block, a structured value, a decoded blob, an error message and a list page; one `tools/call` is sent, no row is made, and an encoded echo is shown to pass, as the docs state.
  - `::test_no_log_record_at_any_level_holds_the_credential` captures the root logger at `DEBUG`, the SDK's and the HTTP library's loggers included.
  - `::test_a_line_never_sees_the_credential` runs `export -p`, `declare -p` and `set` in a line that also runs the tool, and searches the line's output and replies.
  - `::test_no_stdio_child_sees_a_credential` has a sibling stdio server report its environment and arguments after both a static and a resolved credential were used.
  - `::test_a_loopback_credential_goes_to_no_proxy` sets the proxy variables and counts zero requests at a spy proxy.
  - `::test_no_holder_prints_the_credential` takes `repr` of the pool, a connection, the carrier and a sent request.
  - `::test_a_traceback_with_locals_holds_no_credential` raises inside the fixture mid-send and formats the traceback with locals.
  - `::test_the_inbound_bearer_is_never_sent_upstream` drives a served request (171-2) carrying the inbound canary and searches every outbound request.
  - `::test_no_action_log_row_holds_a_credential` reads every row `fs.calls` returns after the flow, and the table itself.
- `tests/kernel_store/test_credentials.py::test_no_kernel_record_holds_a_credential`: after the flow and an interrupted tool call that is resumed, every row of every table of the kernel store is read and searched, on SQLite and on the Postgres leg, parametrized as `tests/shell/test_engines.py:25-48` is. The resumed call asks the resolver once.

## Scope

In: `src/vfs/credentials.py`; `src/vfs/mcp/pool.py` with the pool, the carrier and the search; the `credentials=` shapes on `add_mcp` in `src/vfs/base.py` and `src/vfs/sync.py`, which 170-4 adds; the per-caller snapshot, floor and caches in 170-4's `src/vfs/mcp/supervisor.py`, `catalogue.py` and `client.py`; the two exports in `src/vfs/__init__.py`; `LAYERS` in `tests/lint/test_code_shape.py`; the tests above and `tests/support/canaries.py`; the wording of I4's first criterion in `context/standards/roadmap.md` when choice 2 is confirmed.

Out: OAuth on demand and a credential a caller supplies, story T7. Token exchange and a vault. A credential for a stdio server. A scheme other than bearer. A call for a set of subjects. The serving side's verifier and per-request authority, 149-2 and [171-2](../2026-11-25-serve-answers-each-request-under-its-own-authority-and-refuses-an-open-mount/spec.md). The action log's schema, H0. The suite-wide log search, X7. The five existing sites that put exception text in a detail.

## What the docs must say

- The docstrings of `Credential`, `CredentialResolver` and `add_mcp`, and a page for the two names under `documentation/reference/python-api/`, since an exported name on no page fails the docs gate. `scripts/docs.sh check` is this spec's docs gate.
- That a per-user server connects at a caller's first operation, and that a listing is the caller's own.
- When the resolver is asked, that it may be asked by many calls at once, that it is the place to cache, and that what it raises is not shown or logged.
- The fixed refusals of decisions 5, 8, 11 and 13, and what a caller should do about each.
- The limits, plainly: the credential lives in the process's memory while its connection does, and Python cannot wipe it. The reply search finds exact text only. A URL is printed by the SDK's logger, so no secret belongs in one. A host that passes a plain `str` holds it in its own frame, where a tracer that captures locals can read it; `Credential.bearer` at the point the secret is read avoids that. A resolver must never return the token a caller sent to VFS.
- The README does not say "as the user" in the OAuth sense (`context/standards/roadmap.md:55`).

## Earlier decisions this reverses

- Spec 170 §3.1, for a per-user server: "every vfs caller who may call its tools acts through the one credential the host configured. `tools/list` is therefore one list per server, not per caller." A static server keeps it.
- 170-4 decision 2, for a per-user server: registration no longer connects.
- Story I4's heading asks for a decision record as well as a spec. Decision records were retired on 2026-10-30; this spec carries the decision.

## Not checked

- Nothing was run on Postgres, and no Postgres result is claimed. `vfs-probe-postgres` is not installed in this container, a connection to port 5432 is refused, and `VFS_TEST_POSTGRES_URL` is unset. No claim of this spec depends on an engine: it adds no statement. The Postgres leg named under Tests is a test for the build.
- The SDK and `httpx2` are not installed. The SDK was read in four source files at the pinned revision and never run. Whether its client sends the carrier's header on every request of a connection, the stream, the resumption and the closing `DELETE` included, and whether a 401 surfaces as the carrier sees it, belong to 170-4's first study.
- The three prototypes are not `dev` code. One is the `Credential` class against the real envelope. One is the pool against a counting fake server, with a real `Authority` and nothing else of VFS: its thirteen counts are the ones the tests name. One is header carriage on `httpx` 0.28.1, which stands in for `httpx2`.
- The loggers of the HTTP library were not read below its client module, and its frames that hold a header's value while they run were not audited. The leak tests over the root logger and over a traceback with locals are what hold them.
- The kernel store, the job contract, the run store and the action log are not on `dev`. What their records hold of a tool call was read from their specs and, for the store, from its branch.
- `MCP_CALLER_CONNECTIONS` rests on arithmetic over the reference deployment and on no measurement. A process's descriptor limit is the host's setting and was not costed.
- No test suite, `scripts/ci.sh` or `scripts/docs.sh check` was run.

## Choices to confirm

No choice below lacks a reversible side, so the build waits for none of them. It waits for the work named under Builds on.

1. **D16.** Taken: the host's resolver, no store, no exchange inside VFS, no forwarding, a set refused. The other sides are a store VFS owns and token exchange at the edge. The side taken adds two names and one argument shape and can be withdrawn until it ships.
2. **What "never during `tools/list`" means.** Taken: the resolver is asked once by each call and once by an operation that opens a caller's connection, and a list refresh never asks. The strict reading asks only at a `tools/call`, which leaves a caller's listing empty until its first call and T4's third criterion unreachable. A third reading asks once per connection and never per call; it costs one failed call at each token's expiry.
3. **The connection key.** Taken: the actor and the one subject, as a stored session's owner is. The roadmap's words are "one connection per distinct principal", which could mean the subject alone. The pair shares less, and merging it later changes only how many connections are opened.
4. **The anonymous caller and the system actor.** Taken: both are refused before the resolver. The other side lets the resolver decide. Admitting them later is an addition.
5. **A credential for a stdio server.** Taken: refused. The other side is one child a caller, handed its credential on a pipe. Nothing lawful carries it today, since the environment is ruled out.
6. **Bearer only.** Taken. `Credential` can gain a second constructor, a named header say, without changing the first.
7. **A reply that holds the credential.** Taken: withheld, with a floor of 16 characters on a credential. The other sides are to pass it, or to cut the secret out and keep the rest. Relaxing later lets through replies that are refused today.
8. **A resolver that raises.** Taken: `vfs.unavailable`, a fixed detail, and a log record of the class name alone. The other sides are to raise it to the caller of the verb, or to log its traceback; either can carry the secret out.
9. **The pool's size.** Taken: 256 for a router, a constant. The other side is a host setting, which can be added beside the constant. The number is arithmetic and not a measurement.
10. **No connection at registration.** Taken. The other side is an argument naming an authority to probe as, which would make the host hold a real caller's credential at startup.

## One line

A server registered with a resolver is called as each caller, on that caller's own bounded connection, with a credential that VFS asks the host for at every call, carries in one header, and lets reach no result, row, record, log, line or child.
