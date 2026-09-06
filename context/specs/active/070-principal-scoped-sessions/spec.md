# 070 — Authority: the verified subject set, the actor, and the session that carries them

- **Status:** shaped — **rewritten 2026-09-06 around ADR 062 to 067**
  (ratified by Clay the same day) after the principals and permissions
  research programme
  (`../../../research/2026-09-05-principals-and-permissions-research-plan.md`,
  synthesis `../../../research/2026-09-05-permissions-synthesis.md`).
  The 2026-07-10 draft (research review of eight repo lenses, decisions
  1 to 7) is superseded by this text; its decisions 4, 6 and 7 survive
  as written and are restated below; its decision 1 shape is replaced.
  History is in git. Awaiting Clay's read before implementation
  (Clay, 2026-09-06: "rewrite the specs only, then stop for review").
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
