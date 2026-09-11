# 070 — Authority: the verified subject set, the actor, and the session that carries them

- **Status:** **landed 2026-09-06** (slices A to E in one landing; see
  *Landing notes* at the end). Rewritten 2026-09-06 around ADR 062 to
  067 (ratified by Clay the same day) after the principals and
  permissions research programme
  (`../../../research/2026-09-05-principals-and-permissions-research-plan.md`,
  synthesis `../../../research/2026-09-05-permissions-synthesis.md`).
  The 2026-07-10 draft (research review of eight repo lenses, decisions
  1 to 7) is superseded by this text; its decisions 4, 6 and 7 survive
  as written and are restated below; its decision 1 shape is replaced.
  History is in git.
- **Date:** 2026-09-06 (original draft 2026-07-10)
- **Owner:** Clay Gendron
- **Kind:** feature (the identity layer: `Principal`, `Authority`, the
  threading of one authority through the funnel into storage, the
  fail-closed default, the session facade, and attribution of actor
  and subjects on every version row)
- **Depends on:** the live router (spec 056 Pass A), 047 (the router
  error vocabulary; this spec adds one kind), ADR 013/017 (version
  rows; this spec adds columns)
- **Decisions it implements:** ADR 062 (authority), ADR 063 rules 1, 2,
  4 (the session never widens itself; rights re-derived per call), ADR
  064 rules 1, 3 (actor and subjects on every version row; the chain
  kept, the current actor used)
- **Feeds:** 058 (the spine consumes the authority), 148 (sessions:
  narrowing, sub-sessions, `pending`), 149 (`serve()` auth: token in,
  authority out)
- **Prior art:** the research programme's five lens memos; the July
  research review folded into this spec (postgrest's verify-once
  pipeline, starlette's named absence, fastmcp's session triple,
  authlib's claim validation)

## Intent

Today `user_id` is a fully plumbed, inert `str | None`: every public
verb accepts it, `_call_storage` forwards it, nothing verifies or
enforces it, and `None` means unscoped access. Two properties make it
a liability as `serve()` approaches: it is caller-asserted (a
confused-deputy shape), and it fails open.

The trust model, in one line (unchanged since July):

> **Verified at the edge. Trusted as data inside. Enforced in
> storage.**

What changed with ADR 062 is *what* is verified and threaded. Not one
subject string but an **authority**: the non-empty set of principals
whose grants apply (the **subjects**), the principal doing the work
(the **actor**), and what the session has given up (the
**narrowing**). An agent acting for one person is the common case; an
agent acting for a group chat is a set; a person at a keyboard is a
subject acting as its own actor; a batch job is the system actor with
no subject. Every version row records the actor and every subject, so
the audit never loses the pair (the failure Plan 9's auth server and
Kerberos both have on record).

This spec delivers the type, the threading, the fail-closed default,
the facade and the attribution. It does not enforce a single grant:
that is 058's job, and 058 reads the authority this spec delivers.

## Decisions

1. **Two frozen value types, one construction site each.**

   ```python
   @dataclass(frozen=True, slots=True)
   class Principal:
       sub: str                                  # verified name
       kind: Literal["user", "service", "system"] = "user"
       scopes: frozenset[str] = frozenset()

   @dataclass(frozen=True, slots=True)
   class Authority:
       subjects: frozenset[Principal]            # non-empty, or system
       actor: Principal
       narrowing: Narrowing = Narrowing.NONE     # spec 148 fills this
       provenance: Provenance                    # edge | constructed | system
       source_identity: str | None = None       # set once at the edge

       @classmethod
       def of(cls, principal) -> Authority: ...           # subject acting as itself
       @classmethod
       def on_behalf_of(cls, subjects, *, actor) -> Authority: ...
       @classmethod
       def system(cls) -> Authority: ...                  # the marked exception
   ```

   `sub` mirrors the JWT claim so token-to-principal is transparent;
   `owner_id` and 058's `principal_id` store `sub` unchanged. `kind`
   is ADR 062's three principal kinds: a `service` principal is an
   agent deployed as its own identity (rule 5) and may sit in a set
   like any user; `system` is the actor of `Authority.system()` and
   nothing else. `Narrowing` is an opaque type whose only value in
   this spec is `NONE` ("nothing given up"); spec 148 gives it
   content without changing this signature. `Provenance` is ADR 064's
   three-valued mark. Sanctioned construction sites: the three
   classmethods, 149's `authority_from_token`, and tests; a bare
   `Authority(...)` or `Principal(kind="system")` elsewhere in `src/`
   is pinned by a grep-shaped test. `Authority.system()` is
   wire-underivable: 149's factory refuses a validly signed token
   whose `sub` is the reserved system name.

   **Invariants enforced at construction** (a violation is a
   `ValueError`, it can only come from `src/` code): `subjects` is
   non-empty unless `actor.kind == "system"`; a `system` principal
   never appears in `subjects`; `actor` is never `None`; the set is
   bounded by `MAX_SUBJECTS` (a declared constant; ADR 066 rule 8) and
   an oversize set is refused at the *edge* with the classified kind
   below, so the type's `ValueError` is narrowing only.

2. **Threading stays per call through the funnel; the field swaps
   type.** `user_id: str | None = None` becomes
   `authority: Authority | None = None` on every public verb, every
   `_route_*` helper, `_call_storage`, and every storage-protocol
   method. `params.py`'s `_USER` spec becomes `_AUTHORITY` with the
   same "never on the wire" doc. Storage receives the **object**, not
   a name: 058's chokepoint reads `subjects` (ADR 067 rule 2) and
   the write pipeline reads `actor`, `subjects` and `provenance` for
   attribution. This closes the July fork ("full object vs bare
   `sub`"): the object.

3. **Absence fails closed; privilege is a named default.** No mode
   knob. A verb reaching the router with no authority and no
   configured default is refused before resolution and dispatch with
   a new error kind, **`vfs.unauthenticated`** (the 401 to
   `permission_denied`'s 403: "who are you" vs "you may not"). The
   escape hatch is a constructor argument, not a mode:

   ```python
   vfs = VirtualFileSystem(storage=..., default_authority=Authority.system())   # ETL
   async with vfs.session(authority) as s: ...                                  # app
   ```

   An omitted authority falls back to `default_authority`; if neither
   exists, refuse. `default_authority=Authority.of(Principal("anon"))`
   is the future public-read shape once 058 can express it. Caller
   identity is not row ownership: the system path stamps `owner_id`
   as data in the write payload; the app path derives it from the
   subjects per ADR 064 rule 4 (one subject: that subject; a set:
   NULL).

4. **Rights are re-derived per call, never cached at open** (ADR 063
   rule 2). The authority is a value; nothing in this spec or in 058
   memoises a *decision* on it across calls. (058 memoises the
   *resolved grant rows* keyed by grant revision, which is not the
   same thing.)

5. **`Session` is an authority-scoped facade, opened as a context
   manager, and closed is final.**

   ```python
   async with vfs.session(authority) as s:
       result = await s.read("/reports/q2.md")      # no identity arg
   ```

   The session holds exactly the authority and its lifecycle. Every
   verb delegates into the existing funnel with
   `authority=self._authority`; there is no second dispatch path,
   pinned by the equality test (session-mediated result equals the
   direct call with the same authority) that must outlive this spec.
   A closed session refuses with a structured error and never
   reopens (SQLAlchemy's `close_resets_only` retrofit is the cost of
   deciding this lazily). Bare verbs keep the `authority` kwarg (the
   session is sugar; enforcement is authority-*presence* at the
   funnel). The session gains `narrow(...)` and sub-sessions in 148;
   this spec adds no state beyond the authority.

6. **Attribution on every version row** (ADR 064 rules 1, 3). The
   versions table gains `actor` (replacing the semantics of
   `created_by`, which is renamed), `provenance`, and
   `source_identity`; a side table `version_subjects(entry_id,
   version_number, principal_id)` holds one row per subject. The write
   pipeline fills them from the authority at the single point where
   version rows are minted. `grant_revision` is 058's column (it needs
   the grants table). A read of `versions` for an entry returns the
   actor and the subject list with each version.

7. **Wire rules, restated and delegated.** Inbound: identity enters
   from the transport, never from tool arguments; `serve()` verifies
   audience, signature, issuer and expiry at a `TokenVerifier`-shaped
   seam and constructs the authority server-side; no served tool
   exposes an `authority` parameter (spec 149 builds it). Outbound: no
   token passthrough; a remote mount receives verified names under the
   near side's attestation as a *trusted subsystem* or a token
   exchange (RFC 8693), and maps `(issuer, sub)` into its own
   principal space, never bare `sub` and never its own `system()`
   (spec 149; ADR 062 rule 6).

## Non-goals

- Authentication (no IdP, no token issuance): the hosting runtime owns
  who the caller is; vfs owns the type and the seam.
- Any grant, level or predicate: 058.
- Narrowing, sub-sessions, `pending`, the ask ledger, the join leak
  notice: 148.
- The `serve()` transport and the token factory: 149.
- Share links and capability tokens (the old 009): a future spec.
- `user_scoped` path rewriting: gone (ADR 006); `permissions.py`'s
  docstring reference is deleted in this spec's slice B.

## Acceptance criteria

- No public verb, `_route_*` helper, `_call_storage`, or
  storage-protocol method accepts `user_id`; the parameter is
  `authority: Authority | None` everywhere identity flows, and
  `params.py` describes it.
- `Principal` and `Authority` are frozen and hashable; construction
  invariants (non-empty subjects unless system, no system in subjects,
  `MAX_SUBJECTS`) are pinned; `grep -rn "Authority(" src/` hits only
  the classmethods and 149's factory, pinned as a test.
- With no `default_authority`, an identity-bearing verb called without
  one returns `vfs.unauthenticated` without reaching resolution or
  dispatch; with `default_authority` set, the funnel receives it,
  asserted at `_call_storage`.
- `Session` is an async context manager whose verbs take no identity
  argument; session-mediated and direct results are equal; a closed
  session refuses and cannot reopen.
- Every version row minted through the app path carries `actor`,
  `provenance`, `source_identity` and one `version_subjects` row per
  subject; the system path carries `actor = system`, `provenance =
  system`, no subject rows.
- `InMemoryStorage` and `DatabaseStorage` conform to the new protocol
  signatures (accept; enforcement is 058's); the conformance suite
  passes the authority through and asserts attribution.
- `ruff`, `ruff format --check` and `ty` clean; `scripts/ci.sh 3.13`
  green; the engine legs pass with the new versions columns.

## Slices

| Slice | Content | Lands green? |
|---|---|---|
| A | `vfs/authority.py`: `Principal`, `Authority`, `Narrowing.NONE`, `Provenance`, `MAX_SUBJECTS`; the `unauthenticated` kind | yes, pure |
| B | the rename through router, params, protocol, both storages, tests; delete the `user_scoped` docstring | yes, mechanical |
| C | `default_authority`, the fail-closed gate, the `_call_storage` assertion | yes |
| D | `Session` facade and the equality invariant | yes |
| E | versions attribution columns and side table; write pipeline fills them; `versions` read returns them; schema version bump | yes, with the engine legs |

## Open questions

- None marked. The July markers are resolved by the ADRs: full object
  (D2), knob deleted (D3), session as sugar (D5), no claims payload
  (scopes suffice until 149 names a reader), groups not on the
  principal (ADR 067 rule 3), `system()` bypass scope (ADR 062 rule 4).

## Landing notes (2026-09-06)

- **What landed.** `vfs/authority.py` (`Principal`, `Authority` with
  the three doors, `Narrowing.NONE`, `Provenance`, `MAX_SUBJECTS = 64`,
  `SYSTEM_NAME`, and `owner_for`); the `vfs.unauthenticated` kind with
  its contract row and an `UnauthenticatedError` class; `params.py`'s
  `_AUTHORITY` spec with an `authority` param kind that refuses any
  non-`Authority` value as `invalid`; the rename through every public
  verb, every `_route_*` helper, `_dispatch_entry`, `_call_storage`,
  the storage protocols, `DatabaseStorage`, `WritePlan`, the trash
  chain and the copy minting; `default_authority` on the constructor
  with the fail-closed gate inside `_gate_params` (garbage still
  outranks anonymity) and the narrowing at `_call_storage`
  (`_admitted`); `vfs/session.py` with the `Session` facade and
  `VirtualFileSystem.session(authority)`; the versions schema and
  model attribution. `permissions.py` lost its `user_scoped`
  docstring section.
- **The control plane runs as the system actor.** The bind-site
  probes, the mount-point `mkdir` and `delete` behind `add_mount` and
  `remove_mount`, and `locate(exists=True)`'s stat pass
  `Authority.system()` explicitly, whatever default or caller is
  configured. Mount administration is the router's own work, not a
  caller's, and the grants of 058 will not govern it.
- **Ownership derives from the authority now.** `owner_for` decides
  the entry row's `owner_id` at every minting site (write, edit,
  mkdir, the copy tree, the trash bucket chain): one subject owns what
  it makes, a set owns nothing (the container governs), the system
  actor stamps the payload's declared `owner_id`, and no authority
  stamps nothing. The declared owner rides on the staged row so the
  system path can honour it; the edit snapshot now reads `owner_id`.
- **The storage seam keeps `Authority | None`.** The router always
  passes one (the gate refuses otherwise), so `None` at a backend
  method means unrouted direct use — the conformance suite and dev
  scripts. Whether a backend refuses `None` is 058's call, made when
  enforcement moves into storage.
- **Slice E is schema and model only; no write path mints a version
  row.** The `versions` table gains `actor` (replacing `created_by`),
  `provenance` and `source_identity`; `version_subjects(entry_id,
  version_number, principal_id)` is a new side table; the schema
  format is 13; sweep clears the side table with the rest.
  `Version.create` takes the authority whole and fills the four
  fields. But the live tree mints no version row anywhere (STATUS.md,
  *Version content history*: no spec exists), so "the single point
  where version rows are minted" and the versions read that returns
  actor and subjects both wait on that story; the attribution is ready
  for it, and this spec's acceptance line for minted rows is vacuous
  until then.
- **A closed session refuses as `invalid`** ("the session is closed
  and cannot reopen; open a new one") and re-entering one raises
  `ValueError`. Spec 148 may want a narrower kind once `pending` and
  the widen refusal exist; nothing pins the choice beyond the tests.
- **Tests.** `tests/test_authority.py` (the type), `tests/base/
  test_authority.py` (the gate per verb, the default and explicit
  authorities reaching storage, the control plane as system, the
  session equality and signature pins per verb, closed-is-final, the
  grep-shaped construction-site pin), attribution tests on `Version`
  and on the write path's owner. Every router constructed in the
  existing suites passes `default_authority=Authority.system()` — the
  ETL shape — because the gate now fails closed; `RecorderStorage`
  records the authority behind each call beside its kwargs.

## Amended 2026-09-06 (ADR 068): absence is anonymous, not refused

Decision 3's ingress refusal is superseded the same day it landed.
Clay: the default posture is open, and an open mount must not require
a principal. Landed as: `Principal` gains the `anonymous` kind with the
reserved name `anon`, `Authority.anonymous()` is the fourth door (its
only shape: the anonymous principal as sole subject and actor), the
router substitutes it when a call names no authority and no default is
configured, the ingress gate no longer refuses, and `owner_for` gives
anonymous rows a NULL owner. The `vfs.unauthenticated` kind stays and
moves to the mount: spec 058's spine produces it when an anonymous
call reaches a `shared` or `private` posture. `default_authority`
stays for the ETL shape. The suites drop the
`default_authority=Authority.system()` lines this landing had added.
