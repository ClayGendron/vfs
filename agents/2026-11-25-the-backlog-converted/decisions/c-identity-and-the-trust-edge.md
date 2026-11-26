# Decisions verified: token to authority, serve() refusal, owners, the JOSE library

Rows D13, D14, D15, D17 and D35 of `context/standards/roadmap.md` section 16, verified at HEAD 0ed462f on 2026-11-25. None of the five is marked Decided (READ, `context/standards/roadmap.md:1085-1089`, `:1107`). The 2026-11-15 rulings on names and arguments touch none of them (READ, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md`, its decision list covers D4 to D8, D11, D55, D56). Labels: EXECUTED (a command or fetch ran here), READ (path:line), INFERRED (reasoning).

## D13. The edge ignores a token's `groups` claim

Lean: ignore (READ, `roadmap.md:1085`; spec 149 rule 1, `context/specifications/active/149-serve-auth-token-to-authority/spec.md:16`).

Verification: settled-by-landed-work.

Decision text: `authority_from_token` reads no `groups` claim; a principal's groups come from the `memberships` table alone, resolved per statement, and a token that carries `groups` yields the same `Authority` as the same token without it.

Reason: the landed grants spec already ruled that membership "comes from the `memberships` table only (the token's `groups` claim is ignored)" (READ, `context/specifications/archive/058-row-level-permission-grants/spec.md:32`, `:137`). The tree carries it: `Principal` has no groups field (READ, `src/vfs/authority.py:84-86`) and groups are written only through `add_member` and `remove_member` (READ, `src/vfs/base.py:1691-1712`). Spec 149 at conversion only pins the rule at its new door, which is I1 criterion 4 (READ, `roadmap.md:383`).

Precedent: the group-permissions memo recommends ignoring the claim for four reasons: a multi-subject authority needs every member's groups and one token speaks for one person; remote mounts re-derive; claims are frozen at issue and truncated (Entra replaces the claim past 200 groups in a JWT, Okta fails past 100); and the rights cache keys on the membership revision, which a claim does not bump (READ, `context/research/2026-09-28-group-permissions-max-within-min-across.md:242-252`). Postgres, Plan 9, SpiceDB and AWS IAM all resolve membership from their own store per check (READ, same memo `:236-241`). The memo names the identity-provider route as a system-actor membership sync, not a claim (READ, `:254`).

At the reference deployment: no cost; membership resolution is already the rights compile's, cached per revision (INFERRED).

Specs affected: 149 (rule 1 loses its marker), 171 (consumes the factory unchanged).

## D14. A subject set named by a verified trusted subsystem carries a fourth provenance, `attested`

Lean: add it (READ, `roadmap.md:1086`; spec 149 rule 2, `spec.md:17`).

Verification: holds.

Decision text: `Provenance` gains the value `attested`, minted only where a verified `service` token whose declared scope allows it names the subject members as data; `edge` keeps meaning the edge verified the subject itself, `constructed` keeps meaning trusted in-process code built it, and the version row records which.

Reason: the audit must tell "the edge saw this subject's proof" from "a subsystem vouched for this list", and the record that would show the difference already exists: every version row stores the authority's `provenance` (READ, `src/vfs/storage/backends/database/versions.py:183`; `src/vfs/models/rows.py:552`, `String(16)`, which `attested` fits). The earlier study of spec 149 recorded that provenance is persisted nowhere; that claim is wrong for the version row (READ, the two lines above). The value is one more member of a `Literal` (READ, `src/vfs/authority.py:40`), so no schema change follows (INFERRED). Reusing `constructed` would make a room's member list, named over the wire by a remote service, indistinguishable from a list built by the host's own code (INFERRED).

Precedent: the delegation lens takes Kerberos's two SIDs, "verified at the edge vs asserted by a subsystem", as the provenance class a version row should record (READ, `context/research/2026-09-05-permissions-lens-capabilities-and-delegation.md:134`).

Left to the conversion, not to this row: the carrier of the member list (a token claim, a header or the request `_meta`) and the scope name; the spec 149 study records these as needing a ruling (READ, `agents/2026-11-25-the-backlog-converted/studies/051-162/149-serve-auth-token-to-authority.md:49`). I1's six criteria do not pin `attested` (READ, `roadmap.md:380-385`), so the value can land with the carrier rather than with the factory (INFERRED).

Specs affected: 149 (rule 2), 171 and the H0 action log, whose row carries provenance (READ, `roadmap.md:278`).

## D15. `serve()` treats a mount as open when anonymous can create on it

Lean: refuse when any mount's root everyone-level is `add` or above (READ, `roadmap.md:1087`).

Verification: holds-amended.

Decision text: `serve()` refuses to start, unless `allow_open=True`, while any bound mount holds a posture row (a grant row for `*`) at `add`, `contribute` or `read_write` at any path, or binds a storage with no grant family; the refusal lists each such mount with the paths of its open rows; `read`, `list` and `none` postures serve without the flag; the `/.vfs/tools` and `/.vfs/mcp` catalogue postures count as mounts.

Reason for the threshold: `add` is the lowest rung that lets anonymous create rows (READ, `src/vfs/ops.py:117-121`), and an unauthenticated write is what "open" named: the retired word meant a root `*` row at `read_write`, while `shared` (a root `*` row at `read`) served anonymous reads (READ, `context/specifications/archive/058-row-level-permission-grants/spec.md:22`). Spec 171 keeps that split on the wire, an HTTP request with no token reading a readable mount (READ, `context/specifications/active/171-the-mcp-adapter-and-the-cli-tool/spec.md:19`, `:202`). A literal translation, `read_write` only, would serve a `contribute` mount, where anonymous overwrites anyone's rows, without the flag (INFERRED from `ops.py:120`).

Reason for the amendment: posture is per directory and the deepest prefix wins (READ, `docs/explanation/open-in-process-loud-at-the-edge.md:35-37`). A root at `none` with `/scratch` at `read_write` admits an anonymous write to `/scratch/hello.txt` (READ, same file `:37`; `context/specifications/active/165-the-permission-ladder-list-and-contribute/spec.md:51`), so a root-only check serves that mount silently. A mount whose storage has no grant family enforces no posture at all, so it is open by construction (INFERRED from `src/vfs/storage/protocol.py:378`).

Precedent: the published explanation names Redis and MongoDB listening without authentication, S3's block-public-access default and Firebase's test-mode warning as why open must be "a deliberate word once a network is involved" (READ, `docs/explanation/open-in-process-loud-at-the-edge.md:47-49`). The default posture is `read_write` (READ, `src/vfs/storage/backends/database/engine.py:181`, `backend.py:167`), so a default mount needs the flag on a socket, which is the stated intent (INFERRED).

At the reference deployment: one statement per mount at start, a seek on the `(principal_id, path_prefix)` key for `*` with a three-value level filter (READ, `src/vfs/models/rows.py:840-846`); never per call. A posture raised after start is not re-checked; anonymous calls are still judged by the ladder per call (INFERRED).

Specs affected: 171 (§0 `allow_open`, criterion 10, `spec.md:52`, `:203`), 149 (its last bullet, `spec.md:23`), 170 (the catalogue postures).

## D17. Declared owners are validated, group ownership stays parked, and the default-authority fallback can be made loud

Lean: yes to all three (READ, `roadmap.md:1089`).

Verification: holds-amended.

Decision text: a declared `owner_id` of `*`, `anon`, `system` or one starting `group:` is `vfs.invalid` at the ingress where a declared owner enters, which is `write`'s entries, for every caller, before any statement; ownership stays personal (`group:` owners parked with `manage`); `VirtualFileSystem(..., loud=False)` gains `loud`, and with `loud=True` each call that fell back to `default_authority` emits exactly one `WARNING` record on the `vfs` logger; `cli` and `serve()` refuse the system actor regardless of `loud`.

Amendment: I6 names `write`, `mkdir`, `copy` and `restore` (READ, `roadmap.md:430`). Only `write` takes a declared owner: the staged owner comes from the entry at `src/vfs/storage/backends/database/writes.py:218`; `edit` keeps the row's owner (`writes.py:1292`); `mkdir` stamps `owner_for(authority)` with nothing declared (`topology.py:501`); and a directory's declared owner is not stored (READ, `context/specifications/archive/2026-11-14-a-mutation-is-authorized-for-the-rows-it-acts-on-at-its-commit-point.md:361`). `copy` and `restore` carry an existing row's owner, not a declared one (INFERRED from the same grep, EXECUTED: `owner_for(` has two call sites in `src/`).

Reason: `owner_for` returns the system actor's declaration unchecked (READ, `src/vfs/authority.py:215-227`), and `Rights.admits` matches `owner_id` against subject names (READ, `src/vfs/storage/grants.py:485-497`), so a `group:` owner is a row nobody holds a floor on and `*` or `anon` mimics a reserved name. The same four shapes are already refused as a `Principal`'s `sub` (READ, `src/vfs/authority.py:92-99`), so the check reuses existing constants. The fallback is a silent escalation when the default is the system actor (READ, `context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/05-identity-rights-and-the-trust-edge.md:146`).

Precedent: POSIX `chown` refuses an unsupported owner with `EINVAL` and reserves the change to a privileged process, which matches system-actor-only stamping (INFERRED from POSIX `chown`, not fetched here). Group ownership is parked by the ladder spec (READ, `context/specifications/active/165-the-permission-ladder-list-and-contribute/spec.md:76`). An opt-in constructor flag that logs every call is SQLAlchemy's `echo=False` (EXECUTED: read `.venv/lib/python3.13/site-packages/sqlalchemy/engine/create.py:197-203`). The edge refusal of the system actor is spec 171's (READ, `spec.md:49`).

At the reference deployment: the owner check is a string test per entry with no statement, flat at 10,000 entries; `loud=True` writes up to one record per call, about 150,000 a day, which is why it stays opt-in (INFERRED from AGENTS.md's per-verb multiplier). The `vfs` logger does not exist yet; X7 builds it (READ, `roadmap.md:870-875`).

Specs affected: none of the numbered backlog specs carries I6; it is a roadmap story with no spec (EXECUTED: listing of `context/specifications/active/`). 171 consumes the system-actor refusal; 181 serves `owner_id` (READ, `context/specifications/active/181-the-public-surface-regrouped-by-kernel-group/spec.md:513`).

## D35. The JOSE library behind the served edge is PyJWT, the one the MCP SDK already installs

Lean: `joserfc` (READ, `roadmap.md:1107`).

Verification: fails.

Decision text: the shipped `TokenVerifier` verifies signature, issuer, expiry and audience with PyJWT (`pyjwt[crypto]`), which the `mcp` SDK already requires; it ships in the `vfs-py[mcp]` extra that spec 171 creates, and no separate `vfs-py[serve]` extra is added; `authority_from_token` in `vfs/authority.py` imports neither.

Reason: the official MCP Python SDK lists `pyjwt[crypto]>=2.10.1` among its runtime dependencies and no other JOSE library (EXECUTED: fetched `modelcontextprotocol/python-sdk` `pyproject.toml` on main, 2026-11-25); spec 170 records the same closure for the `mcp` extra (READ, `context/specifications/active/170-tools-and-mcp-servers-as-views/spec.md:151`; `context/research/studies/2026-10-15-agent-shell/15-spec-170-review-before-build.md:191`). `serve()` over HTTP exists only inside `vfs.mcp`, so every install that verifies a token already carries PyJWT (READ, spec 171 `spec.md:35`, `:44`). `joserfc` would add a second JOSE implementation beside it with no check the four checks need that PyJWT lacks: PyJWT's `decode` takes `audience=` and `issuer=`, verifies `exp` by default and refuses a missing required claim (EXECUTED: fetched `jpadilla/pyjwt` `jwt/api_jwt.py` on master). `joserfc` itself is sound, version 1.8.0 of 2026-11-03, BSD-3-Clause, requiring `cryptography` (EXECUTED: PyPI JSON), so the failure is duplication against the tree's recorded dependency closure, not the library's quality (INFERRED). The roadmap's `vfs-py[serve]` contradicts spec 171's single `vfs-py[mcp]` extra (READ, `roadmap.md:381`; spec 171 `spec.md:44`).

Precedent: the SDK's own seam, a `TokenVerifier` protocol with `verify_token(token) -> AccessToken | None`, whose `AccessToken` carries `subject` and a `claims` mapping for `iss` and `act` (EXECUTED: fetched `src/mcp/server/auth/provider.py` on main). The shipped verifier can implement that protocol and fill `subject` and `claims`, which `authority_from_token` then reads, so I1's "one method" protocol need not be a second one (INFERRED).

At the reference deployment: either library verifies in process against cached keys, about 150,000 times a day, with no statement and no per-call round trip to the issuer (INFERRED).

Specs affected: 149 (rule on "never hand-rolled", `spec.md:11`), 171 (the extra and `token_verifier=`), and the roadmap's I1 criterion 2 wording.
