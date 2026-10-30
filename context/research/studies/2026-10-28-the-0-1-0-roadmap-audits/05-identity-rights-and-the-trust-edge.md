# Audit: identity, authority, sessions, the ladder, row grants, posture, the trust edge

Audited 2026-10-28 against HEAD `90f5883` (2026-10-27), working tree clean (EXECUTED: `git status --short` empty). Labels: READ = I read it, EXECUTED = I ran it, INFERRED = my conclusion from what I read.

Executed verification: `uv run pytest tests/test_authority.py tests/base/test_authority.py tests/base/test_grant_routing.py tests/storage/test_grants.py tests/test_permissions.py -q -o addopts=""` → 235 passed; `tests/storage/database/{test_ladder,test_rights, test_membership,test_labels}.py` → 98 passed. Interpreter check (EXECUTED): no `serve`, no `cli` on `VirtualFileSystem`; `vfs.mcp` not importable; `Narrowing` has one member `NONE`; `vfs.authority.authority_from_token` does not exist; `DatabaseStorage` has no `run`; `RUNGS == ('none','list','read','add','contribute','read_write')`.

---

## 1. Built today (with evidence)

### 1.1 The identity model — **built**

| Piece | Evidence | Label |
|---|---|---|
| `Principal(sub, kind, scopes)`; kinds `user / service / system / anonymous`; reserved names `system` and `anon`; `*` and `group:` refused as a `sub` | `src/vfs/authority.py:35-38, 44-58, 76-107` | READ |
| `Authority(subjects, actor, provenance, narrowing, source_identity)` frozen, hashable; invariants in `__post_init__` (system never a subject; non-empty set unless system; ≤ 64 subjects; anonymous has exactly one shape) | `authority.py:115-149` | READ |
| Four doors: `Authority.of`, `on_behalf_of`, `system()`, `anonymous()` | `authority.py:151-186` | READ |
| `owner_subject` / `owner_for`: one subject owns what it makes; a set, anonymous and system own nothing (system stamps the payload's declared owner) | `authority.py:201-227` | READ |
| Construction-site pin: a bare `Authority(` or a system/anonymous-kind `Principal(` anywhere in `src/` outside `authority.py` fails a test | `tests/base/test_authority.py:246-259` | READ |
| Groups are **not** on the principal; they are rows (`vfs_memberships`) walked per subject at resolve time, nesting ≤ 8 (`MAX_GROUP_DEPTH`), cycle and depth refused at write with `authority_budget` | `src/vfs/storage/grants.py:91-93`; `rights.py:1038-1083, 1132-1175, 1399+`; `models/rows.py:823-831` | READ |
| Group ids are `group:<name>` in the one `principal_id` column; `Principal` refuses them, so a group is never an actor or subject | `authority.py:57-58, 92-94`; ADR 071 rule 7 | READ |

**How a host constructs an Authority today (READ):** in process, by calling a door and passing `authority=` per call, or `fs.session(Authority.of(...))`, or setting `VirtualFileSystem(default_authority=...)` (`base.py:373, 390`). There is **no** token → Authority factory anywhere in `src/` (EXECUTED grep for `authority_from_token`, `provenance="edge"`, `TokenVerifier`: zero hits). The `provenance="edge"` literal exists as a type value (`authority.py:40`) but nothing mints it. The docstring at `authority.py:18-19` ("plus the edge factory that turns a verified token into an authority") and the comment at `tests/base/test_authority.py:247` describe a door that does not exist — see Risks.

### 1.2 Admission and per-call `authority=` — **built**

- Every public verb takes `authority: Authority | None = None` (`base.py:908-1690`, READ). `_admitted` (`base.py:3088-3101`) fills it at `_call_storage` (`base.py:2988`): explicit → `default_authority` → `_ANONYMOUS_AUTHORITY`. Storage always receives a value (ADR 068 rule 4). `locate(..., exists=True)` probes as the admitted caller, not the system (`base.py:760`; pinned `tests/base/test_authority.py:164`).
- Mount administration runs as `_ADMIN_AUTHORITY = Authority.system()` (`base.py:126, 545-575, 826, 837`) — pinned `tests/base/test_authority.py:151`.
- `Session` binds exactly one authority and delegates every verb into the same funnel with `authority=self._authority` (`src/vfs/session.py:36-429`). It caches no rights (`session.py:40-42`). Closed is final; a closed session refuses with `ErrorKind.invalid` (`session.py:424-429`). Pinned: a session verb equals the direct call with the authority filled in; session verbs take no identity argument (`tests/base/test_authority.py:183, 197, 210, 223, 233`).
- `Narrowing` exists with one member `NONE` (`authority.py:65-68`; EXECUTED).

**Answer:** yes, per-call `authority=` is the API shape, and `Session` is sugar that binds it. `session.narrow`, `child`, `join`, `pending` are not built (spec 148 seed).

### 1.3 The ladder — **built, consistent with ADR 080**

- `Rung = none < list < read < add < contribute < read_write`, dense `LEVEL_RANK` 0..5 (`ops.py:110-116`; `storage/grants.py:88`). `GRANTABLE_LEVELS` excludes `none` (a principal row states a positive level; `none` is posture-only) (`grants.py:80-82`).
- `VERB_RUNGS` (`ops.py:134-160`) is the one verb → `Needs(primary, create, traverse)` table: `stat/ls/tree/glob → list`; `read/grep/glean/graph/grants → read`; `write/mkdir/edit/mkedge/rmedge → contribute` (write/mkdir mint at `add`); `delete/restore/move/copy/grant/revoke/posture/sweep/add_member/remove_member → read_write` (move/copy mint at `add`; copy source at `read`); `run → read`.
- The owner floor rides every rung for a single named subject; a set holds a member's floor where every other member holds the rung by grant; anonymous holds none (`grants.py:286-300` `Rights.admits`; `tests/storage/database/test_ladder.py:182-266`).

### 1.4 Grant rows, posture, membership — **built**

| Verb | Router | Storage | Gate | Evidence |
|---|---|---|---|---|
| `grant(path, principal, level)` | `base.py:1593-1615` → `_route_grant` (`2019-2039`) | `rights.py:894-915` | `read_write` at `path` for every subject; lawful principal (not `*`, `system`, `anon`, blank, ≤ 255 chars); level in `GRANTABLE_LEVELS`; anonymous judged `unauthenticated` at path; else `permission_denied` if `list` reaches, else `not_found` | `rights.py:1305-1337, 1349-1354` |
| `revoke(path, principal)` | `base.py:1617-1626` | `rights.py:918-963` | same gate; missing row is a `not_found` **warning** | |
| `grants(path)` | `base.py:1628-1638` | `rights.py:965-1001` | `read` on path; every row if caller holds `read_write`, else only own/groups'/everyone rows; hidden or `list`-only path → `not_found` | |
| `posture(path, rung)` | `base.py:1640-1653` | `rights.py:1004-1035` | `read_write` at path; writes the `*` row, marks a relabel, stamps `*` | |
| `add_member / remove_member(group, member, path="/")` | `base.py:1655-1690` | `rights.py:1038-1112` | **system actor only** (`_membership_refusal`, `rights.py:1339-1346`); path only picks the mount | ADR 071 rule 8 |

- Rows: `vfs_grants(principal_id, path_prefix, level, granted_by, granted_at, revision)` unique on `(principal_id, path_prefix)`; `vfs_memberships`; `vfs_relabels`; `vfs_principal_revisions` (`rows.py:805-852`, READ).
- Posture is a grant row for `EVERYONE_NAME = "*"`; deepest covering prefix wins (`grants.py:134-147` `level_at`); default root posture row is planted at first touch (`rights.py:1115-1124` `posture_row`). The posture vocabulary **is the ladder's rungs** (`Posture = GrantLevel`, `grants.py:85`; EXECUTED `Posture is GrantLevel`); the ADR 068 words `open/shared/private` survive only in prose (see Risks).
- `granted_by` on grant and membership rows records the **actor** (`rights.py:1066`, `_upsert_grant`) — the one audit column on the rights plane.
- Router-side: a `PermissionMap` read-only layer refuses grant **writes** but lets `grants` list (`_route_grant` passes `write_rels`; pinned `tests/base/test_grant_routing.py:89`); a backend without `SupportsGrants` is `unsupported` (`:102`).

### 1.5 Enforcement — where each check lives — **built**

1. **Router, structural, not per caller:** `PermissionMap` per binding (`read`/`read_write` + prefix overrides) composed from `/` to the terminal, only tightens, refuses `ErrorKind.read_only` (`src/vfs/permissions.py:144-320`); mount `deny_ops` (`base.py:380`). This is the older layer; it knows nothing about who.
2. **Storage, anonymous at the addressed path:** `unauthenticated_at` / `unauthenticated_refusals` judge an anonymous caller by the posture **rows** on the chain (never a stored label), refusing `ErrorKind.unauthenticated` when the posture is below the verb's rung (`rights.py:381-410`; `_decide` first line, `:850`).
3. **Storage, the caller's rights compiled into every statement:** `resolve_authority` (`rights.py:322-378`) — system actor → `Resolution.everything()`; else per-subject closures walked, grant rows for subjects+groups read, in-flight posture rows added, `Resolution.compile` (per member union, meet across members, ADR 066), cached in `RightsCache` keyed on `(subjects, principal-revision stamp, relabel marks)` and only stored if the mount revision did not move during the compile. Reads: `Visibility` (`rights.py:457-618`) and the three-seek predicate in `ranges.py` (everyone level ≥ r via `(everyone_level, path)` index ∪ caller's sorted path pieces joined to the path index ∪ owner arms, `UNION ALL`). Mutations: `WriteGate` (`rights.py:630-887`) — one batched fetch of targets and ancestors, judged in app code per `Needs`; hidden and missing both answer `not_found`; a nameable row without the rung answers `permission_denied`; the whole batch fails.
4. **The row label:** `entries.everyone_level` stamped at mint and rewritten by the relabel in bounded chunks behind a cursor (`labels.py`, `rows.py:475`).

**Can a front bypass a check? (INFERRED from READ):**
- Anything in-process can call `Authority.system()` or hold the storage object; that is the documented convention, not a wall (ADR 068; `04-one-call-end-to-end.md:114`).
- `_admitted`'s fallback to `default_authority` means a front that forgets `authority=` silently runs as the host's default — which may be `Authority.system()` (the ETL shape, `base.py:3091-3093`). Spec 171 §0 pins "a handler never passes `None`" and a spy test for it; nothing enforces that today because no front exists.
- `grep` nominates candidates **before** the view is applied and strikes hidden rows in Python; the 25,000 `CANDIDATE_BUDGET` counts hidden candidates, so a partial caller truncates earlier than a whole one (open-questions.md:359-367, "stays open"). Not a leak of bytes, but a visible-set/statistics inconsistency with ADR 065.
- The system actor validates nothing in a declared `owner_id` (it may stamp `*`, `group:x`, `anon`) — open-questions.md:344 ("today it validates nothing").

### 1.6 Scale — **measured in a memo, partially pinned**

- Memo `2026-10-02-grants-at-100k-users-measured.md` (READ, "Bottom line" §): the pre-073 design stopped working between 1k and 10k users (one arm with N holes; 9.2 MB bind; `pieces()` > 60 s at 100k); with the everyone level on the row an ordinary caller compiles to 11–44 pieces, ~2 KB, 22–31 µs at every N; scoped read 2.5 ms on SQLite and Postgres at 100k users; relabel 2 s / 17 s per million rows; algebra linear with zero disagreements over 3.76 M checks and 100k fuzz worlds. **Not measured (§7):** SQL Server, MariaDB, Oracle for the `UNION ALL` shape and the relabel `UPDATE … FROM`; a 64-subject authority with deep closures; concurrent relabel + read.
- Both measured changes landed (ADR 072, 073; spec 058 archived 2026-10-10).
- **Pins in `tests/` (READ):** counted, never clocked — `test_the_fan_spends_one_bind_per_exact_path_and_two_per_open_range` (`test_rights.py:212`), `test_a_cached_caller_costs_its_stamps_and_the_marks_per_call` (`:582`, counts SELECTs), cache eviction by entries and bytes (`:632, :649`), invalidation scope per grantee/group/member (`:479-580`), the relabel held midway (`:386`), oracle parity over random worlds (`tests/storage/test_grants.py:78-150`, `tests/support/grant_worlds.py`). The grants contract runs on every storage leg, engines included (`tests/support/grants_contract.py:3-5`, `tests/storage/test_conformance.py`).
- **Not pinned:** no 10k- or 100k-user world in `tests/` (EXECUTED grep for `100_000|10_000|slow` in the rights tests: none). The memo's numbers are the only record of the scale claim. No pin that the compile size is independent of N.

### 1.7 Audit — **write side built, read side missing**

- `vfs_versions` carries `actor`, `provenance`, `source_identity`, `grant_revision`; `vfs_version_subjects` one row per subject (`rows.py:535-572`; `versions.py:154, 182-198`). Grant and membership rows carry `granted_by` and `granted_at`; the entry row carries `owner_id` only — **no `created_by`** (`rows.py:421-500`, READ).
- **Creates mint nothing** (`versions.py:11`), so a row created by a set or by anonymous (owner NULL) has no recorded creator. ADR 064 rule 1 ("every version row records the actor") holds for replaced bodies only.
- **No read side**: `ops.py` has no `versions`/`history`/`audit` op (EXECUTED grep: none). ADR 087 names a "history" kernel group (`087:85, 118`), unbuilt.

### 1.8 Tools and the permission structure — **designed, not built**

- `run` is an `Op` with `Needs("read")` (`ops.py:156`, "run waits for its own axis") and `SupportsRun` is a protocol (`protocol.py:346-355`), but **no backend implements it** (EXECUTED: `DatabaseStorage` has no `run`); every call is `unsupported`.
- ADR 082 pin 12 retires `run`; ADR 084 pin 2: executing a program is `read` on its entry (`list` → 126, below → 127); pin 7: installing is `write` under the ladder (fresh name `add`, occupied `contribute`/own, delete `read_write`/own). Spec 170: host tools project to `/.vfs/tools/<name>`, MCP tools to `/.vfs/mcp/<server>/tools/<tool>`, as **router-owned views, not rows in any mount**; grants on them go to the root binding's grants table via a new `SupportsGrants. rungs_at(paths, *, authority)` seam (spec 170 §5 "The rungs_at seam"). So a grant can name a tool by its `/.vfs/...` path prefix without the tool being a stored row.
- Spec 170 states plainly: on a fresh node everyone holds `read_write` at `/`, so every caller including anonymous can call every host tool and every MCP tool; a host locks it with `posture("/.vfs/tools", "list", authority=Authority.system())`.

---

## 2. In flight — the specs and ADRs that touch this domain

| Record | Status line (READ) | What it would change |
|---|---|---|
| ADR 062, 063, 064, 065, 066, 067, 068, 070–073 | accepted 2026-09-06 … 2026-09-28; 067 amended by 071/072 | the identity value, the session law, the audit rows, the intersection law, the spine, the row label — all landed except 063 rules 1/3/5 (narrowing, sub-sessions, ask), 068 rule 7 (loud edge) |
| ADR 080 | accepted 2026-10-14 | the six-rung ladder — **landed** (spec 165) |
| ADR 082 | proposed 2026-10-15 | programs; `run` retired; tools run with the host's authority; the Fs capability curried with the caller's Authority |
| ADR 084 | proposed 2026-10-15 | execution policy; executing = `read` on entry; install = `write` under the ladder; **no `ask` inside vfs**; `serve()` refuses the system actor |
| ADR 085 | proposed 2026-10-15 | the MCP adapter: verbs as tools plus `cli` |
| ADR 087 | proposed 2026-10-24 | the kernel: four op groups incl. history and rights; the gate as the one funnel |
| spec 070 | landed 2026-09-06 (archived) | Authority/Session/`default_authority`/anonymous — built |
| spec 058 | landed, archived 2026-10-10 | row grants, posture, membership, label, cache — built |
| spec 165 | landed 2026-10-14 | `list` and `contribute` rungs; `VERB_RUNGS` — built |
| spec 148 | **seed**, not scheduled; 3 `[NEEDS CLARIFICATION]` | `session.narrow(profile)`, `child`, `join`, the `pending` kind and an ask ledger |
| spec 149 | **seed**, not scheduled; amended 2026-10-15 by spec 171; 2 markers | `TokenVerifier` seam (audience/signature/issuer/expiry, "never hand-rolled"), `authority_from_token(claims)`, subject-set attestation (`attested` provenance?), outbound rule for remote mounts (no token forwarding; trusted subsystem or RFC 8693 exchange), the open-mount refusal, the door token |
| spec 170 | draft, not started; needs a 3-piece study first | tools and MCP servers as views; `rungs_at`; per-server credentials; "every vfs caller acts through the one credential the host configured" |
| spec 171 | draft, not started; 1 marker | `serve(fs, transport, authority= | token_verifier=, allow_open=False)`; HTTP: token → `authority_from_token` per request, no token → anonymous; stdio: one `authority=`; system actor refused; spy pin on zero `None` |
| spec 161 | seed; status says "uncommitted" | version mint — **the mint is committed** (`99884aa`, 2026-10-24); status line stale |
| spec 054 | cancelled, archived 2026-09-05 | topology lock holds by construction; rule rides in 171 |
| STATUS.md "Foreign-mount credentials" | direction only, **no spec** | per-subject credential store keyed by mount + `source_identity`; `connect_url`/`complete_connect`; refresh in the backend; missing credential → `unauthenticated` |

---

## 3. Gaps vs the 0.1.0 goal

Rated: built / partial / planned / missing.

| 0.1.0 theme | Item | Rating | Note |
|---|---|---|---|
| (1) public kernel API | per-call `authority=`; `Session` binding | **built** | |
| (1) | `Narrowing` with content, sub-sessions, `pending` | **planned** (148, seed) | ADR 084 pin 4 "no `ask` inside vfs" contradicts 148 §5 `pending` (see Risks) |
| (1) | interrupts | missing here | not an identity concern; nothing in this domain carries a cancellation token |
| (2) storage ×4 | grants contract on every leg | **built** | engine legs run the contract when `VFS_TEST_<ENGINE>_URL` is set |
| (2) | three-seek + relabel measured on MSSQL/Oracle | **partial** | memo §7: unmeasured; no counted pin that compile size is independent of N |
| (6) serve as MCP | `serve()` | **missing** | no `vfs.mcp`; spec 171 draft |
| (6) | token → Authority (`TokenVerifier`, `authority_from_token`) | **missing** | spec 149 seed; the docstring claims an edge factory that does not exist |
| (6) | refusal to start on an open mount (`allow_open`) | **missing** | and "open" has no definition on the ladder (see Risks) |
| (6) | system actor refused on the wire | **planned** | spec 171 §0 |
| (6) | anonymous loud at the edge | **partial** | storage-side `unauthenticated` is built; the edge-side 401 for an invalid token is not |
| (4) MCP servers authenticating as the user | per-principal downstream credential | **missing and undecided** | spec 170 §3.1 designs the opposite (one host credential per server); STATUS.md names a credential-store direction for *foreign mounts*, no spec; see §6 |
| (7) tools follow the permission structure | tool entries as rows a grant can name | **planned** (170) | `rungs_at` seam; `run` retired; today `run` is unsupported everywhere |
| (7) | default posture on `/.vfs/tools` and `/.vfs/mcp` | **planned** | spec 170 accepts "open node lets anyone call every tool" |
| audit | version rows name actor/subjects | **built** (replaced bodies only) | creates mint nothing; no `created_by` on the entry row |
| audit | a read side (who did what) | **missing** | no history op; ADR 087 names the group |
| rights admin | `manage` rung / grant-option; group ownership | **planned** (open questions, parked) | any `read_write` holder can grant and revoke any card at the path |
| rights admin | group membership by a non-system principal | **missing** by decision (ADR 071 rule 8) | "a per-group admin flag is a follow-up" |

---

## 4. Risks — wrong, stale, or contradictory

1. **A door that does not exist is documented as existing.** `authority.py:18-19` ("plus the edge factory that turns a verified token into an authority") and `tests/base/test_authority.py:247` name an edge factory; `src/` has none (EXECUTED). `provenance="edge"` is mintable by nobody, and until spec 149's door token lands any caller can pass `Authority(..., provenance="edge")` and the audit will record an edge proof that never happened (spec 149 "The door token" acknowledges this).
2. **Posture vocabulary split.** Code, tests and docs use rungs (`Posture = GrantLevel`; `posture("/", "none")` in `docs/how-to/share-a-folder-with-grants.md:31`); ADR 068 rule 1, spec 149, spec 171 and `open-in-process-loud-at-the-edge.md:49` still say `open/shared/private` and `allow_open`. The open-mount refusal cannot be written until "open" is defined on the ladder (everyone ≥ `add`? ≥ `contribute`? `read_write` only?).
3. **`pending`/`ask`: two records disagree.** ADR 063 rule 5 and spec 148 §5 give the session a `pending` kind and an ask ledger; ADR 084 pin 4 (proposed, later) says "No `ask` inside vfs. vfs allows or classifies." One must yield.
4. **Spec 149 cites the wrong memo.** It lists `research/2026-08-17-verify-authority-spike.md` as an input; that memo is grep's verify-stage benchmark (READ), nothing to do with tokens.
5. **Spec 161's status says the mint is uncommitted**; `versions.py` was committed 2026-10-24 (`99884aa`, EXECUTED `git log`).
6. **"Creates mint nothing" leaves the audit with holes.** A create by a subject set or by anonymous records no creator anywhere (owner NULL, no version row, no `created_by`). ADR 064's "every version row names the actor" is true but does not cover the first write of a row. ADR 087's history group needs a creation record or a `created_by` column to answer "who made this".
7. **`default_authority` as a silent escalation path.** `_admitted` falls back to the host's default when a front passes `None`; a host whose default is `Authority.system()` (the documented ETL shape) turns every forgotten `authority=` into a system write that honours a payload's declared `owner_id`. Spec 171 pins the spy; nothing in the library makes the fallback loud.
8. **`run` is a declared verb that nothing serves.** It sits in `ALL_OPS`, `VERB_RUNGS` and `SupportsRun`, `VirtualFileSystem.run` exists, and no backend implements it. ADR 082 pin 12 retires it; until spec 167 lands it is dead surface in the public API.
9. **grep's candidate budget counts hidden rows** (open-questions.md:359, "stays open") — a partial caller's `truncated` warning fires earlier than a whole caller's on the same corpus, against ADR 065's visible-set rule and the 10k-batch contract.
10. **Spec 170 vs theme (4).** Spec 170 §3.1 pins "a server's identity is the connection's: every vfs caller who may call its tools acts through the one credential the host configured" — the exact opposite of "MCP servers that authenticate as the user". It is a draft; it needs amending before it is built.
11. **System actor stamps any declared `owner_id`.** `owner_for` returns the payload's `declared` unchecked (`authority.py:225-226`); a batch loader can stamp `*`, `anon` or `group:x` as owner (open-questions.md:344). `Rights.admits` compares `owner_id` to subject names, so `*` never matches, but a `group:` owner silently becomes a row nobody has a floor on.
12. **Memo numbers are not pins.** The 100k-user story lives only in the memo; a regression that makes the compile world-sized again would pass `tests/`.

---

## 5. Proposed roadmap stories

### S1. The trust edge: `TokenVerifier` and `authority_from_token`

**Why.** Theme (6) needs a wall between a bearer token and an `Authority`. Today the only doors are in-process; `provenance="edge"` is a value nobody mints. Spec 149 has the design (verify audience/signature/issuer/expiry through a library, never hand-rolled; `sub` → subject; `act` → actor; `kind` from a claim or client registration; `source_identity` set once; reserved `sub` refused; groups never from the token). This story lands the seam and the factory without the transport, so spec 171 can consume it.

**Depends on.** Nothing in code; decides spec 149's two markers (see §6 Q1, Q2).

**Acceptance criteria.**
1. `vfs.authority.authority_from_token(claims: Mapping) -> Authority | ResultError` exists; it is the fifth door and the only site in `src/` that mints `provenance="edge"`; the construction-site pin in `tests/base/test_authority.py` is widened to assert exactly one `provenance="edge"` site.
2. A `TokenVerifier` protocol with one method, `verify(token: str) -> Claims | ResultError`, and one shipped implementation over a JOSE library behind a new `vfs-py[serve]` extra; the core install imports neither.
3. Claims with `sub == "system"` or `sub == "anon"` or a `sub` starting with `group:` or equal to `*` answer `ErrorKind.invalid`; a verifier failure answers `ErrorKind.unauthenticated`; a missing `aud` answers `unauthenticated` (audience is on by default) — counted over a table of twelve claim shapes.
4. `act` present → `actor = Principal(act.sub, kind=...)`, subjects = `{sub}`; absent → actor = subject. `source_identity == sub` in both cases. `groups` claim is ignored (or verified against memberships — Q2); a test pins the chosen behaviour.
5. The door token (spec 149): a bare `Authority(...)` outside `vfs.authority` raises `TypeError` naming the doors; `copy`/`pickle` of an authority still round-trip.
6. No test asserts elapsed time.

### S2. `serve()`: the MCP front with identity per request

**Why.** Theme (6), "easy to serve vfs as an MCP server", is unbuilt. Spec 171 fixes the signature and the identity rules; this story is the identity half of it: HTTP requests derive an authority per request from the token, stdio takes one authority, the system actor is refused, a request never reaches `_admitted` with `None`, and the edge is loud about an open mount.

**Depends on.** S1; spec 171's adapter (the non-identity half); §6 Q3 (what "open" means on the ladder).

**Acceptance criteria.**
1. `serve(fs, transport="stdio", authority=Authority.system())` raises before binding a transport; so does `serve(fs, transport="http", token_verifier=v)` when `fs._default_authority` is the system actor; the exception names the rule.
2. A spy on `VirtualFileSystem._call_storage` counts zero calls with `authority is None` across the whole MCP test module (counted, not sampled).
3. HTTP, no token: every verb runs as `Authority.anonymous()`; a `read` under a root posture of `read` succeeds and under `none` answers `unauthenticated` with the hint naming the fix. HTTP, invalid token: HTTP 401 and zero storage calls (spy).
4. `serve()` refuses to start while any bound mount's root posture is at or above the rung Q3 names, unless `allow_open=True`; the refusal lists every such mount path. With `allow_open=True` it starts and a test counts one warning line per open mount.
5. A served `write` whose entry declares `owner_id` is refused `invalid` before dispatch (owner stamping is the system actor's alone, and the system actor is off the wire).
6. No served tool and no served schema names `authority`, `observations` or `provenance` (counted over every tool's input schema).
7. The same tests run over stdio and over streamable HTTP with the SDK's in-memory transport; no real socket in `tests/`.

### S3. Tools and MCP tools under the ladder (`rungs_at`, posture on the catalogues)

**Why.** Theme (7): "everything is a file, including tools, and follows the same permission structure." Spec 170 designs tools as router-owned views at `/.vfs/tools/<name>` and `/.vfs/mcp/<server>/tools/<tool>` whose rung comes from the root binding's grant rows through a new `rungs_at` seam, and ADR 084 pins executing = `read` on the entry, listing = `list`, install = `write` under the ladder. This story is the permission slice of spec 170, so a grant can name a tool before the shell runs it.

**Depends on.** Spec 169/170's catalogues (`ToolView`, `McpView`); ADR 082/084 acceptance; `run` retired (spec 167 task zero).

**Acceptance criteria.**
1. `SupportsGrants.rungs_at(paths, *, authority) -> dict[Path, Rung]` on the database backend issues exactly `ceil(len(paths) / membership_budget)` statements for 10,000 paths (counted with a statement spy) on SQLite and on each engine leg; its answer for every path equals `Rights.reaches` ∘ `level_at` over the posture rows on the chain, checked against the Python oracle over the random grant worlds.
2. `grant("/.vfs/tools/deploy", "ann", "read")` is lawful and lists under `grants("/.vfs/tools/deploy")`; `write`, `mkdir`, `delete`, `move` at a catalogue path answer `invalid` with zero storage mutations (spy).
3. With `posture("/.vfs/tools", "list")`: anonymous `ls /.vfs/tools` names every tool bare (path and kind only); `cat /.vfs/tools/deploy` answers `permission_denied`; calling it answers exit 126 and zero invocations of the host function (counted). With posture `none`: `ls` shows nothing, a call answers 127.
4. A principal holding `read` on `/.vfs/mcp/github` can call every tool under it and `read` every resource; one holding `list` can name them and call none; the per-server `tools/list` is issued once per refresh regardless of caller count (counted).
5. `type deploy` and `cat /.vfs/tools/deploy` render the trust line ("runs on the host, with the host's authority" / "runs on <server>") and never invoke the tool (invocation counter stays at zero across the read family).
6. `run` is gone from `ALL_OPS`, `VERB_RUNGS`, `EXEC_OPS`, `SupportsRun` and `VirtualFileSystem`; `ty` and the `assert_never` arm hold.

### S4. MCP servers that act as the user: the per-principal credential seam

**Why.** Theme (4) asks for mounted MCP servers that authenticate as the user. Spec 170 §3.1 currently pins one credential per server for every caller; STATUS.md names a credential-store direction for foreign mounts with no spec; spec 149 D4 forbids forwarding the inbound token. This story decides the shape (§6 Q4) and lands the seam so a server connection resolves the caller's credential at call time.

**Depends on.** S1 (`source_identity` is the key), S3 (the catalogue), §6 Q4, Q5. A research pass is required first (rclone, Nango, MCP authorization 2026-07-28, Entra OBO, RFC 8693) — the memo STATUS.md already asks for.

**Acceptance criteria** (written against the recommended option, a host-supplied `CredentialResolver`; adjust if Q4 chooses otherwise).
1. `add_mcp(name, server=..., credentials=...)` accepts either a static credential (today's shape) or a `CredentialResolver` protocol with one method `resolve(server: str, authority: Authority) -> Credential | ResultError`, called at most once per `tools/call` and never during `tools/list` (counted).
2. A resolver answer of `None`/`ResultError` makes the call answer `ErrorKind.unauthenticated` at the tool's path with a hint naming the server; zero bytes are sent to the server (transport spy).
3. A subject set over a per-user server answers a classified refusal (Q5: `invalid` or `permission_denied`) unless every member resolves and the host opts into the per-member fan; the fan issues exactly `len(subjects)` calls (counted).
4. The credential never appears in any `Result`, any row, any log line, or `os.environ` of a stdio subprocess (a test greps every captured output and the child's environment for the secret bytes).
5. The MCP connection per `(server, principal)` is reused across calls: for 100 calls by one principal exactly one `initialize` handshake is issued (counted); a second principal issues a second.
6. A shipped reference resolver backed by a `vfs_credentials`-style table is **not** in this story (it is the foreign-mount credential store; a later story) — the test suite's resolver is an in-memory dict.

### S5. The audit read side: `history` and a creation record

**Why.** ADR 064 promises "who did what"; the write side is built for replaced bodies, but creates leave no record and nothing reads version rows back. ADR 087 names a history group. Serving vfs to many principals without a way to ask "who wrote this" is a governance gap.

**Depends on.** ADR 087 acceptance (naming the op); spec 161/162 (the mint).

**Acceptance criteria.**
1. A `created_by` column (actor `sub`) on `vfs_entries`, stamped from the admitted authority on every mint, including anonymous (`anon`) and the system actor (`system`); the format version bumps; a creation by a two-member set stamps the actor and writes no version row.
2. A `history(path)` op at rung `read` returns the version rows for the path with `actor`, `provenance`, `source_identity`, `subjects`, `grant_revision`, `created_at`; a hidden path answers `not_found`; a `list`-only path answers `permission_denied`.
3. `history` on 10,000 paths in one call issues `ceil(10000 / membership_budget)` statements for the entry lookup and one chunked statement per budget slice for the subjects join (counted), on SQLite and on each engine leg.
4. Every version row written through the router under a non-system authority has `provenance in {"constructed", "edge"}` and `grant_revision ==` the mount's revision at the write (asserted over the grants contract world).

### S6. Scale pins for the rights compile and the three-seek predicate

**Why.** The 100k-user story is a memo; `tests/` has no world larger than a few hundred rows. A regression that re-introduces a world-sized compile would pass CI. Clay's rule is to count operations, never clocks, so the pins count pieces, binds, statements and rows visited.

**Depends on.** Nothing; `slow`-marked.

**Acceptance criteria.**
1. A generated world with 10,000 users, one private home each (`read_write` self-grant), 100 shared folders, 50 groups, five groups per user: an ordinary caller's `Rights` at `read` holds ≤ 64 pieces and ≤ 4 KiB of bind bytes (`weight()`), and the same bound holds at 1,000 users — the compile is independent of N.
2. `ls /` for that caller issues one visibility statement whose text is identical to the 1,000-user world's (statement text captured and compared), and its range join carries exactly the caller's pieces.
3. A posture change on a 100,000-row subtree runs in `ceil(rows / RELABEL_CHUNK)` UPDATE statements with the chunk constant named, and a read held midway agrees with the oracle on every row.
4. A 64-subject authority whose members each sit in eight nested groups resolves in a bounded number of membership statements (`≤ 8 × ceil(64 / membership_budget)`) and the meet equals the oracle.
5. The pins run on the SQLite leg by default and on each engine leg when the URL is set; MSSQL and Oracle planner shape (seek, not scan) is checked by `EXPLAIN`-text assertion where the dialect exposes one.

### S7. `manage`: separating "may change the data" from "may change who may"

**Why.** Today any `read_write` holder can grant up to `read_write` and revoke any card at the path, including the card its own rights stand on; an owner under a `none` posture cannot share its own row because the grant gate reads spans and the everyone level, never the owner floor (open-questions.md:348-357). Serving many principals makes this the first governance complaint. ADR 080 parked `manage` ("would append, not insert").

**Depends on.** §6 Q6; a short prior-art memo (NFSv4 `WRITE_ACL`, Postgres grant option, FreeBSD `VADMIN`).

**Acceptance criteria** (option (a), a rung).
1. `RUNGS` gains `manage` after `read_write`; `LEVEL_RANK["manage"] == 6`; `GRANTABLE_LEVELS` includes it; posture is capped at `read_write` (`posture(path, "manage")` is `invalid`); the format version bumps.
2. `grant`, `revoke`, `posture` need `manage` at the path; `read_write` alone answers `permission_denied`; the owner floor includes `manage` on the caller's own rows.
3. A caller cannot revoke the card its own `manage` stands on (`invalid`, naming the card); the system actor still can.
4. A grant never exceeds the grantor's level at the path (a `manage` holder may grant `manage`; a `contribute` holder may grant nothing).
5. The grants contract and the ladder tests pass unchanged except for the three gate assertions that move from `read_write` to `manage`.

### S8. Sessions that narrow: `narrow`, `child`, and the fate of `pending`

**Why.** ADR 063 is law and `Narrowing` is a stub. Sub-agents and tool runs want a session that holds less than its parent (ADR 084 pin 3 says a program may "hold less later through `Narrowing`"). This is spec 148's first two powers; `pending` is decided separately (§6 Q7).

**Depends on.** §6 Q7, Q8; spec 148's markers.

**Acceptance criteria.**
1. `Narrowing` becomes a frozen value with `paths` (hide/show globs) and `verbs` (deny list); `session.narrow(profile)` returns a new session; a property test over random profiles shows the child's admitted set ⊆ the parent's on every verb (the oracle over the grant worlds) and `narrow` never adds a right.
2. A verb denied by profile answers `permission_denied` with a `profile` sub-detail, distinct from a grant refusal; a hidden-by-profile path answers `not_found`.
3. `session.child(profile=...)` holds the meet; closing the parent closes the child (a child verb after parent close is `invalid`).
4. The narrowing is recorded on every version row the session writes (a column or the `provenance` detail — Q8); `history` shows it.
5. Zero extra storage statements per call for a session with a profile (the profile is applied at the router; counted).

---

## 6. Open questions Clay must decide

1. **Spec 149 marker 1 — groups from the token.** Ignore a `groups` claim (the lean) or verify it against memberships? Recommendation: ignore; groups are rows.
2. **Spec 149 marker 2 — `attested` provenance.** When a trusted subsystem names a subject set as data, is that `constructed` or a fourth value `attested`? Recommendation: add `attested`; the audit should distinguish "the edge saw each member" from "a service vouched for the list".
3. **What "open" means on the ladder** for the `serve()` refusal. ADR 068's `open/shared/private` became six rungs. Recommendation: refuse when any mount's root everyone-level is `add` or above (anonymous can create); `read` and `list` serve without a flag. Spec 171 and ADR 068 rule 7 need the word changed.
4. **MCP servers acting as the user — which shape.** Options: (a) host-supplied `CredentialResolver(server, authority)` callback — simplest, keeps vfs free of OAuth, the host owns the vault; (b) a vfs-owned credential store (encrypted rows keyed by mount + `source_identity`, `connect_url`/`complete_connect`) — the STATUS.md direction, more to build, ships a reference; (c) RFC 8693 token exchange at the edge (vfs holds the inbound token and exchanges it per server) — contradicts ADR 062/149's "an authority holds no secret" unless the exchange lives outside the `Authority`. **Recommendation:** (a) for 0.1.0 with (b) as a shipped reference resolver later; never (c) inside the `Authority`. Spec 170 §3.1 must be amended either way.
5. **Subject sets over a per-user server.** Refuse (`invalid`), or fan per member and intersect? Recommendation: refuse at 0.1.0; name the fan as a later opt-in.
6. **`manage` as a rung vs a per-card grant option vs owner-only admin.** Recommendation: the rung (a) — one `LEVEL_RANK` entry, the gate asks `manage`, the algebra unchanged.
7. **`pending`/`ask`.** ADR 063 rule 5 and spec 148 say yes; ADR 084 pin 4 says no. Recommendation: accept 084 for 0.1.0 (vfs allows or classifies; the host asks) and mark 148 §5 deferred, so S8 can land without a ledger.
8. **Should narrowing be recorded on version rows?** ADR 064 records actor, subjects, provenance, grant revision; it is silent on narrowing. Recommendation: yes, as a short `narrowing` detail on the version row, so an audit can tell a full session from a narrowed sub-agent.
9. **Group ownership and the system actor's declared `owner_id`.** Keep ownership personal and validate declared owners (refuse `*`, `anon`, `system`, `group:`), or allow `group:` owners with an owner leg over the closure? Recommendation for 0.1.0: validate and refuse; park group ownership.
10. **Creation attribution.** A `created_by` column (S5 AC 1) or a creation version row with no body? Recommendation: the column; a bodiless version row changes the mint's "nothing lost, nothing minted" rule.
11. **Who may add members below the system actor.** ADR 071 rule 8 reserves it; a `manage` holder on `/` or a per-group admin flag? Decide with Q6.
