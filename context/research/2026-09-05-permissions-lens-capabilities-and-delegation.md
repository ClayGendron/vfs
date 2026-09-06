# Permissions lens L3: capabilities and delegation

- **Status**: research memo, Phase 1 lens L3 of the principals and
  permissions programme (`2026-09-05-principals-and-permissions-research-plan.md`).
  Commits us to nothing. Feeds the Phase 3 synthesis, spec 070, spec
  058 and ADR 021.
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Question**: The plan's hypothesis says effective rights are
  `grants(subject) ∩ profile(actor) ∩ session narrowing`, and that a
  session can only narrow, never widen. Capability systems and
  delegation tokens are that hypothesis in its purest form: authority
  is a thing you hold, and the holder can only cut it down. Where does
  "intersection only" hold, where does it break, what did each system
  bolt on when it broke, who holds the credential, and does anything
  here mint a credential that is valid only if several principals all
  agree (the multiplayer case, Q13)?
- **Method**: line-level read of the local clones named below
  (Capsicum and Casper in `freebsd-src`; the WASI preview2 filesystem
  WIT and the WASI capabilities doc; `wasmtime-py`'s preopen seam;
  monty's security and filesystem docs; the biscuit specification;
  authlib's RFC 8693 stub, RFC 7662 introspection and JOSE claims;
  the SPIFFE standards including the new WIT-SVID and Broker API).
  Primary papers and vendor docs fetched on 2026-09-05: Dennis and
  Van Horn 1966, Hardy 1988, Miller, Yee and Shapiro 2003, Birgisson
  et al. 2014, the MS-SFU Kerberos S4U specification, AWS STS and IAM
  docs, RFC 8693, RFC 9396, the WIMSE charter and architecture draft.
  The thirteen rubric questions are answered in order with a verdict
  each. The framing memo (Phase 0) does not exist yet, so the rubric
  is the plan's §2 verbatim. Cites and describes only; no code is
  copied.
- **License**: `freebsd-src` BSD-2-Clause (`COPYRIGHT`, read from
  `HEAD` because the sparse checkout excludes it); `WASI` W3C
  Community Contributor License Agreement (`LICENSE.md`);
  `wasmtime-py` Apache-2.0; `monty` MIT (Pydantic Services Inc.);
  `biscuit` Apache-2.0; `authlib` BSD-3-Clause (a `COMMERCIAL-LICENSE`
  file sits beside it; the BSD grant is what we study under);
  `spiffe` Apache-2.0. All study-only; nothing copied.
- **Sources line**: `freebsd-src` @ `2e33355ee2bf` (2026-09-05, clean,
  sparse checkout of `sys/` and `share/man/man9/`; `lib/libcasper`
  and `lib/libsys` man pages read via `git show HEAD:`); `WASI` @
  `bed33fa` (2026-09-03, detached at `origin/main`; the preview1
  `legacy/` tree is gone from `main`, so preview1 `docs.md` was read
  from the `snapshot-01` branch on GitHub); `wasmtime-py` @ `2ed8d10`
  (2026-08-20); `monty` @ `302e0f27` (2026-09-05); `biscuit` @
  `b3d3fe2` (2025-10-21, shallow; this is the specification repo, the
  Rust crate `biscuit-auth` is not cloned and was read on GitHub);
  `authlib` @ `c529a61` (2026-08-31); `spiffe` @ `99470b9`
  (2026-09-02). Web, all read 2026-09-05: Dennis and Van Horn, CACM
  9(3) 1966, princeton.edu mirror; Hardy, OSR 22(4) 1988, wpi.edu
  mirror; Miller, Yee, Shapiro, "Capability Myths Demolished" 2003,
  papers.agoric.com; Birgisson et al., "Macaroons", NDSS 2014,
  static.googleusercontent.com; MS-SFU protocol overview, S4U2proxy
  and abstract data model pages, learn.microsoft.com; AWS IAM
  "Policies and permissions" (session policies), "Monitor and control
  actions taken with assumed roles" (SourceIdentity), "Pass session
  tags", "The confused deputy problem", "Access to AWS accounts owned
  by third parties" (ExternalId), STS `AssumeRole` API reference;
  RFC 8693 and RFC 9396 at rfc-editor.org; WIMSE charter at
  datatracker.ietf.org and `draft-ietf-wimse-arch-08` (2026-07-06);
  WASI `path-resolution.md` from the `wasi-filesystem` repo. Not
  reachable: Miller's 2006 thesis "Robust Composition" (erights.org
  refused the connection, the JHU repository returned 403); the 2003
  paper by the same author stands in for it, as the plan allows.

---

## Bottom line

Every system in this lens agrees with the hypothesis on one point and
disagrees on another.

The agreement: **the holder of authority can only cut it down.**
Capsicum refuses any `cap_rights_limit` that adds a bit
(`CAPFAIL_INCREASE`). WASI's `fd_fdstat_set_rights` "can only be used
to remove rights". A macaroon holder can add caveats and never remove
one. A biscuit holder can append blocks and never edit one. An AWS
session policy is intersected with the role policy and "cannot grant
more permissions". This is the session law, and it has fifty years of
precedent.

The disagreement: **no system runs on intersection alone.** Each one
ships a named, gated widening: Casper (a helper with ambient authority
the sandbox gave up), macaroon third-party caveats (a discharger adds
proof the holder cannot), biscuit third-party blocks (facts a
designated key may add), Kerberos S4U2self (protocol transition, a
service minting a ticket for a user who never authenticated), AWS
resource-based policies that name a session ARN (explicitly *not*
limited by the session policy). The lesson for vfs is not "allow
widening"; it is "name the one escape hatch, gate it, and mark its use
in the audit", which is exactly what Kerberos does with the
`SERVICE_ASSERTED_IDENTITY` SID.

On multiplayer (Q13): conjunctive *credentials* exist (a macaroon
that needs several discharges, a biscuit whose checks need facts from
several signers). Conjunctive *authority*, rights equal to the meet of
several subjects' grants, does not. Every token here attenuates one
authority block. So the subject set cannot be modelled as blocks
appended to a token; the meet must be computed where the grants live,
at session open, and a change to the set is a re-mint.

## Q1. Subject, actor, and "on behalf of"

**Verdict: supports.** The actor/subject split is in the 1966 paper
and in every delegation protocol since. What varies is whether the
*subject* is a first-class field or only context.

- Dennis and Van Horn define a *principal* as "an individual or group
  of individuals to whom charges are made for the expenditure of
  system resources", and a *computation* runs "on his behalf". When
  the supervisor creates a computation for a principal it places an
  owned capability to that principal's root directory in the C-list,
  and "the principal is then said to own this computation" (CACM 9(3),
  pp. 145 and 152). The `owner j` meta-instruction lets a lender
  "verify that the borrower computation is in fact owned by a certain
  principal" (p. 154). That is a callee inspecting the caller's subject
  in 1966.
- Hardy's compiler "serves two masters and carries some authority from
  each". The failed fix was a "switch hats" call to pick one of two
  authorities; "it soon became clear, however, that more than two
  'authorities' were necessary for some of our applications" (Hardy
  1988, p. 37). Note that for Q13: a deputy with N subjects was already
  the case that broke the hat-switching design.
- RFC 8693 §1.1 draws the line vfs wants: impersonation means "A is
  given all the rights that B has ... and is indistinguishable from
  B"; delegation means "A still has its own identity separate from B
  ... any actions taken are being taken by A representing B". The
  `subject_token` is "the identity of the party on behalf of whom the
  request is being made"; the `actor_token` is "the identity of the
  acting party" (§2.1). The `act` claim carries the actor inside the
  subject's token (§4.1).
- Kerberos S4U2proxy issues a ticket whose `cname`/`crealm` "are that
  of the user, not Service 1" (MS-SFU §1.3.3 step 7). The subject is
  the ticket's client; the actor is whoever presents it. The two
  well-known SIDs `AUTHENTICATION_AUTHORITY_ASSERTED_IDENTITY`
  (S-1-18-1) and `SERVICE_ASSERTED_IDENTITY` (S-1-18-2) tell the
  back end whether the KDC or a service vouched for that subject
  (Microsoft, "Kerberos constrained delegation overview").
- AWS: the actor is the role session (`assumed-role/DevRole/Dev1` in
  CloudTrail's `userIdentity.arn`); `SourceIdentity` is the human or
  system that started the chain, set once and immutable. AWS is
  explicit that it "doesn't control the value of the source identity"
  (IAM, "Monitor and control actions"): the subject is a string the
  IdP asserts, not a verified principal.
- SPIFFE models the actor only. A SPIFFE ID names a workload
  (`spiffe:SPIFFE-ID.md:75-78`); a JWT-SVID's `sub` "MUST be set to
  the SPIFFE ID of the workload" (`spiffe:JWT-SVID.md:74`). The user
  is absent from the standards; the SPIFFE-ID security section only
  warns that a foreign trust domain's "customer was authenticated"
  assertion should not be trusted blindly (`spiffe:SPIFFE-ID.md:186-194`).
  The Broker API is the on-behalf-of shape for *workloads*: a broker
  fetches SVIDs "on behalf of a referenced workload" and "MUST NOT use
  these SVIDs ... for any other workload" (`spiffe:SPIFFE_Broker_API.md:399`).
- WIMSE's charter names the gap: workloads must make "authorization
  decisions based on the original caller, their context, and the
  actions of other workloads that acted on a transaction", and the
  token should carry "user identity, platform attestation, and SBOM
  artifacts" as context. The architecture draft (`-08`, §3.4.11)
  requires that "each hop in the chain MUST explicitly scope and
  re-bind the security context so that downstream services can reliably
  evaluate provenance".
- Casper inverts the roles: the sandboxed process is the caller, and
  the casper daemon is a privileged actor that does work the sandbox
  cannot (`freebsd-src:lib/libcasper/libcasper/libcasper.3`, "library
  for handling application capabilities"). The subject is implicit
  (same uid); Casper has no notion of acting for a *different*
  principal.

## Q2. Attenuation: how authority narrows, and whether it can widen

**Verdict: qualified.** Narrowing-only is universal and structural.
Widening exists in every system, but always as a separately named,
separately gated operation. The hypothesis survives if vfs treats the
escape hatch the same way.

Narrowing, by mechanism:

- **Capsicum (kernel, per descriptor).** `kern_cap_rights_limit` runs
  `_cap_check(cap_rights(fdp, fd), rights, CAPFAIL_INCREASE)` before
  storing the new mask
  (`freebsd-src:sys/kern/sys_capability.c:245`): the new set must be
  contained in the old (`cap_rights_contains`,
  `freebsd-src:sys/kern/subr_capability.c:369`), or the call fails
  with `ENOTCAPABLE`. The man page says it plainly: rights "can be
  reduced (but never expanded)" (`freebsd-src:lib/libsys/cap_rights_limit.2`).
  The sub-limits follow the same law: `cap_ioctl_limit_check` refuses
  any command not already in the old list
  (`sys_capability.c:400-412`), and `sys_cap_fcntls_limit` fails if
  `(fcntlrights & ~fdep->fde_fcntls) != 0` (`sys_capability.c:574-600`).
  `cap_enter` sets `CRED_FLAG_CAPMODE` on a fresh ucred and there is
  no `cap_exit` (`sys_capability.c:101-116`); the mode is inherited by
  every descendant (`cap_enter.2`). Capability mode removes ambient
  authority at the namespace: `namei` returns `ECAPMODE` for any lookup
  starting at `AT_FDCWD` and refuses absolute paths
  (`freebsd-src:sys/kern/vfs_lookup.c:355-375`).
- **WASI (runtime, per descriptor).** Preview1's `path_open` takes
  `fs_rights_base` ("rights that apply to this file descriptor") and
  `fs_rights_inheriting` ("maximum set of rights that may be installed
  on new file descriptors" opened through it); `fd_fdstat_set_rights`
  "can only be used to remove rights, and returns `errno::notcapable`
  if called in a way that would attempt to add rights" (WASI
  `snapshot-01`, `phases/snapshot/docs.md`). Preview2 replaced the
  bitmask with two descriptor flags and one rule: if the base
  descriptor lacks `mutate-directory`, `open-at` with `write`,
  `mutate-directory`, `create` or `truncate` "fails with
  `error-code::read-only`" (`WASI:proposals/filesystem/wit/types.wit:526-535`),
  and a descriptor without the flag refuses every operation that
  "would ... obtain another handle which would permit any of those"
  (`types.wit:103-111`). `wasmtime-py` exposes the whole thing as one
  bool: `preopen_dir(path, guest_path, fs_mutable=True)`
  (`wasmtime-py:wasmtime/_wasi.py:172-188`).
- **monty (interpreter, per mount).** "There is no ambient authority.
  With no mounts and no host functions configured, the sandbox cannot
  read a file ... Not 'it is blocked', the capability does not exist in
  the bytecode VM" (`monty:docs/security.md:22-33`). A `MountDir` has a
  `mode` of `read-only`, `read-write` or `overlay`; "Confinement is
  structural, not a check. Each mount opens a directory descriptor
  (`cap_std::fs::Dir`) once, at mount time, and every operation runs
  relative to that descriptor" (`monty:docs/filesystem.md:101-108`).
- **Macaroons (token, per caveat).** A macaroon's signature is a
  chained HMAC; adding a caveat re-keys the chain with the previous
  signature, so "from an attenuated token we cannot go back to a more
  general one" (biscuit's own summary, `biscuit:DESIGN.md:36-44`). The
  paper: "A macaroon may have multiple caveats on the same attribute,
  ... in which case all the caveats' predicates must hold true"
  (§III). Attenuation happens with no round trip to the minting
  service (§III, Fig. 2, "Macaroon restrictions").
- **Biscuit (token, per block).** "The holder of a biscuit token can at
  any time create a new token by adding a block with more checks, thus
  restricting the rights of the new token, but they cannot remove
  existing blocks without invalidating the signature"
  (`biscuit:SPECIFICATIONS.md:37-43`). The scope rule closes the loop
  that macaroons leave open: a later block's facts are invisible to
  the authority block's rules and to the authorizer, so a holder who
  appends `right("file2", "read")` gains nothing
  (`SPECIFICATIONS.md:251-268`). `seal` produces a token that "cannot
  be attenuated" (biscuit-rust `token/mod.rs`, `seal`, ~line 303).
- **AWS STS (session, per policy document).** "The resulting session's
  permissions are the intersection of the role's identity-based policy
  and the session policies. You cannot use session policies to grant
  more permissions than those allowed by the identity-based policy"
  (`AssumeRole` API, `Policy` parameter). Permissions boundaries and
  SCPs stack the same way: each "does not grant permissions" and only
  caps.
- **RFC 9396.** On refresh "the client can ask for a new access token
  with 'fewer permissions'" (§6.1), but the RFC concedes there is "no
  standardized mechanism to compare two arbitrary authorization detail
  requests". Attenuation needs a lattice; rich authorization details
  do not define one.

Where intersection-only breaks, and what was added:

| System | The widening | The gate | What marks it |
|---|---|---|---|
| Casper | The daemon holds ambient authority (DNS, open-by-name via `cap_fileargs`) the sandbox surrendered at `cap_enter` | Each service's `limit_func` "must not allow the extension of service limits" (`freebsd-src:lib/libcasper/libcasper/libcasper_service.3:32-41`), enforced by service code, not the kernel (`service.c:351-362`) | none in the kernel audit; the sandbox chose the limits |
| Macaroons | Third-party caveats: a discharger (auth service, audit service) adds a proof the holder cannot forge; "a form of privilege amplification" when credentials are split (§VI) | The discharge is bound to the request (`bindForRequest`, §IV-B) so a stolen discharge is useless elsewhere | the discharge macaroon itself |
| Biscuit | Third-party blocks "to either expand a token or fulfill special checks" (`SPECIFICATIONS.md:1188-1190`) | Only rules that say `trusting <pk>` see those facts (`SPECIFICATIONS.md:274-300`); the authority block "can't carry an external signature" (`:988-1000`) | the external signature on the block |
| Kerberos | S4U2self, "protocol transition": a service gets a ticket for a user who "authenticates to the service in some way other than by using Kerberos" (MS-SFU §1.3.3) | `TrustedToAuthenticationForDelegation` decides whether the S4U2self ticket is FORWARDABLE (MS-SFU abstract data model); resource-based delegation "always allows protocol transition" and moves the gate to the resource's ACL | `SERVICE_ASSERTED_IDENTITY` SID on the ticket |
| AWS | A resource-based policy that names the *session* ARN: "The resource-based policy permissions are not limited by the session policy" (IAM, "Session policies") | none; it is a documented hole | CloudTrail shows the session ARN |
| Capsicum | none inside capability mode; the only way out is a descriptor received over a socket from a process outside the sandbox | `recvmsg` needs `CAP_RECV` and the sender's consent | `AUDIT_ARG_RIGHTS` on the limit call (`sys_capability.c:301`) |

The pattern: widening is never a property of the holder's token. It is
a *second party's* act (a discharger, a signer, the KDC, the resource
owner, a process outside the sandbox), and the best systems stamp the
result so the relying party can tell.

## Q3. Where enforcement sits

**Verdict: supports** (one chokepoint, checked at every use).

- Capsicum keeps the decision in one file on purpose: "we want to keep
  all capability permission evaluation in this one file"
  (`freebsd-src:sys/kern/sys_capability.c:211`). `cap_check` is called
  at descriptor lookup on every syscall; the path walk has its own
  strict-relative check in `namei` (`vfs_lookup.c:282-299` for `..`
  escapes, `:355-375` for absolute paths). The rights mask is updated
  under `seqc_write_begin/end` (`sys_capability.c:247`) so a
  concurrent check never sees a torn mask.
- WASI: the host resolves every path "relative to a base directory
  handle" and fails with `not-permitted` if resolution leaves it
  (`types.wit:12-17`); the reference design maps to `RESOLVE_BENEATH`
  / `O_RESOLVE_BENEATH` (`wasi-filesystem/path-resolution.md`).
- monty: "The interpreter performs no filesystem I/O at all. It
  suspends with a description of the operation it wants, and a host
  component decides what to do about it" (`monty:docs/security.md:29-31`);
  the one dispatcher is `MountTable::handle_os_call`
  (`docs/filesystem.md:248-249`).
- Macaroons and biscuits verify at the target, per request, with
  request facts (`resource`, `operation`, time, IP) supplied by the
  authorizer (`biscuit:SPECIFICATIONS.md:616-676`; Macaroons §IV-C,
  "three stage process").
- Kerberos splits it: the KDC decides at ticket issue whether Service 1
  may delegate to Service 2 (`ServicesAllowedToSendForwardedTicketsTo`
  or the resource's `ServicesAllowedToReceiveForwardedTicketsFrom`),
  then Service 2 applies its ACL to the user in the ticket.
- AWS evaluates at the called service, combining identity policy,
  session policy, boundary and resource policy per request.

None of these compiles the check into a database query; that is vfs's
own choice (ADR 021 D3). What they share is that the check runs at
*every* use of the reference, never once at open. See Q11 for the
cost of carrying that into SQL.

## Q4. Unit of protection

**Verdict: qualified.** The capability lineage protects *references*
(a descriptor, a C-list index, an object). The two newest sandboxes in
the set (WASI preview2, monty) protect *path prefixes rooted at a
reference*. That hybrid is what ADR 021 D2 already chose.

- Dennis and Van Horn: the unit is the C-list entry, "each capability
  ... locates by means of a pointer some computing object, and
  indicates the actions that the computation may perform" (p. 145).
  Names live in directories, separate from capabilities; a name is
  "a convenience for principals" (p. 153).
- Miller, Yee, Shapiro: Property A, "No Designation Without
  Authority": in ACL systems "designation and authorization are
  necessarily separated" and "their recombination is likely to lead to
  confused deputies" (§Separable Designators). Paths are the
  designator; the grant table is the authority; ADR 021 recombines
  them at query time. This is the hazard to keep in view, not a
  disqualifier: the paper's own table rates Unix file descriptors
  "yes" on Property A because the descriptor is a reference.
- Capsicum: a descriptor plus a 64-bit-array rights mask
  (`freebsd-src:sys/sys/capsicum.h:81-121`); `CAP_LOOKUP` is the one
  right that turns a directory descriptor into a *prefix* grant, since
  `*at` calls with that descriptor walk beneath it.
- WASI: `get-directories` returns `list<tuple<descriptor, string>>`
  (`WASI:proposals/filesystem/wit/preopens.wit:9`); every operation is
  a relative path under one of those descriptors.
- monty: `MountDir(host_path, virtual_path, mode)`; virtual paths are
  always POSIX and "a host path never leaks in" (`docs/filesystem.md:9,
  104-106`).
- Macaroons and biscuits: the unit is whatever predicate the target
  chooses; the paper's running example is `chunk ∈ {100..500}` (§III),
  biscuit's is `right("file1", "read")` (`SPECIFICATIONS.md:323-360`).
- AWS: ARN patterns and tags (session tags feed `aws:PrincipalTag`
  for ABAC). SPIFFE: a URI path whose "meaning ... is left open-ended"
  (`spiffe:SPIFFE-ID.md:76`).

## Q5. Hide versus deny

**Verdict: supports** (the leak rule has a precedent in the sandboxes).

- WASI's path-resolution design refuses `../../../stuff` "even if it
  resolves back inside the sandbox, because it would leak information
  about the existence of directories outside the sandbox"
  (`wasi-filesystem/path-resolution.md`). Reading a symlink whose
  target is absolute fails with `not-permitted`
  (`WASI:proposals/filesystem/wit/types.wit:552-558`). That is hide,
  not deny: the refusal is shaped so the caller learns nothing about
  what lies outside.
- Capsicum distinguishes two refusals: `ENOTCAPABLE` (the descriptor
  lacks the right) and `ECAPMODE` (the operation is meaningless in the
  sandbox, e.g. a lookup from `AT_FDCWD`). Both are deny with a
  reason; nothing is hidden, and `kern.trap_enotcap` can turn either
  into `SIGTRAP` for debugging (`cap_enter.2`).
- monty hides the host: `Path.resolve()` returns virtual paths, and
  the overlay mode "refuse[s] symlinks entirely"
  (`docs/filesystem.md:104-112`).
- Macaroons name the probing attack and shrug: "attackers may try to
  add third-party caveats to probe for private information ... similar
  attacks are equally possible in many existing authorization
  frameworks" (§V-C). Their mitigation is on the *discharger*: a
  discharge service "may remove this birthdate-assertion caveat when
  it issues a discharge macaroon, to not reveal the bearer's age".
- Kerberos and AWS have no hide rung; AWS `AccessDenied` on a
  non-existent resource is the same error as on an existing one only
  by accident of policy shape.

Traversal: Capsicum's `CAP_LOOKUP` is directory-execute made explicit,
and `lookup_cap_dotdot` decides whether `..` may walk back over
"directories which were previously walked by us"
(`vfs_lookup.c:355-362`). Without it, a sandboxed process cannot even
name its parent. That is the strictest reading of "walk needs a
right on every step".

## Q6. Groups, roles, tenants

**Verdict: qualified.** Capability systems have no groups by design
(authority is per holder). Token systems resolve membership at *use*
time through a third party, or carry it as an attribute resolved at
*login*.

- Dennis and Van Horn: "a group principal" owns shared segments, and a
  user gains access to "the directory of the group principal" by
  `link` (p. 151, 154). Group is a principal, not a membership table.
- Macaroons resolve groups at request time by a third-party caveat:
  "as long as that logged-in user is in group G at A" (§II). The
  target never sees the membership; it sees a discharge from A.
- Biscuit resolves at authorization time: the authorizer loads "lists
  of users and roles" as facts (`SPECIFICATIONS.md:640-645`), and the
  authority block's rules turn them into rights ("if there is an
  ambient resource and we own it, we can read it",
  `SPECIFICATIONS.md:365-402`).
- Kerberos resolves at login: the PAC in the ticket carries the user's
  group SIDs, and S4U2proxy copies "the authorization data ... from the
  service ticket" into the delegated ticket (MS-SFU §1.3.3 step 6).
  Group membership is therefore frozen for the ticket lifetime, which
  is the temporal-accuracy hazard SPIFFE warns about: "role or group
  membership, and access policies are all examples of assertions that
  are more likely to change between the time of SVID issuance and the
  time of validation" (`spiffe:SPIFFE-ID.md:163-168`).
- AWS: tags at session time, up to 50, transitive across role
  chaining; a transitive tag "cannot be changed" by later roles and
  the operation fails if a later session tries to pass one with the
  same key (`AssumeRole`, `Tags`). Tenancy is the account; trust
  domains are SPIFFE's tenant, and "an entity with role 'admin' in
  trust domain A is not assumed to be an 'admin' in ... trust domain B"
  (`spiffe:SPIFFE-ID.md:170-175`).

For ADR 021's open groups fork this lens says: whichever way vfs goes,
record *when* membership is resolved, because every system here that
resolves at login has a documented staleness hazard, and every one
that resolves at use pays a third party per request.

## Q7. Defaults on creation, ownership, move and copy

**Verdict: supports** (inheritance is intersection with the parent).

- Capsicum: a descriptor from `openat` "inherits capability rights
  from the 'parent' file descriptor" (`cap_rights_limit.2`), and
  `CAP_CREATE`, `CAP_MKDIRAT`, `CAP_UNLINKAT`, `CAP_RENAMEAT_SOURCE`
  are separate bits on the *directory* descriptor
  (`capsicum.h:112-175`), so creation and deletion are directory
  rights, exactly the POSIX shape.
- WASI preview1's `fs_rights_inheriting` is a umask for rights: the
  ceiling a child descriptor can have. Preview2 collapsed it to
  `mutate-directory` on the parent.
- Dennis and Van Horn: a created object enters the C-list "with an O
  indicator" (owned); `grant` passes a capability to an inferior sphere
  "with restricted access authority", and "cannot be used to pass a
  capability that is not implied by a capability present in the higher
  sphere" (p. 149). An attempt "to enlarge the class of reference
  permitted to a nonowned segment is also deemed a sphere violation"
  (p. 153). Ownership transfer: "we assume there can be no more than
  one owner of an object", and they record the orphan case where an
  owner removes a shared segment and "the only alternatives are to
  assign ownership to one of A, B or C (but how do we choose?)"
  (p. 153). That question is open in spec 058 too.
- Macaroons: a derived macaroon is "a strict attenuation" (§III); copy
  is free and unrecorded (bearer); there is no move.
- AWS: a role session cannot mint a longer-lived or wider session;
  role chaining caps duration at one hour (`AssumeRole`,
  `DurationSeconds`).

## Q8. Audit

**Verdict: qualified.** Chains are recorded in the *credential*
(nested `act`, Kerberos delegation info, biscuit block order,
transitive tags) and in the *issuer's log* (CloudTrail, `AUDIT_ARG_RIGHTS`).
What is *not* recorded, anywhere here, is who added a first-party
caveat. Attribution of the actor is strong; attribution of the
narrowing is weak.

- RFC 8693 §4.1: "The outermost `act` claim represents the current
  actor while nested `act` claims represent prior actors. The least
  recent actor is the most deeply nested." But "the consumer of a token
  MUST only consider the token's top-level claims and the party
  identified as the current actor"; the nested chain is "for audit"
  only. The example carries `sub`, `act.sub`, `act.act.sub`
  (Fig. 6).
- Kerberos: the delegated ticket carries an `S4U_DELEGATION_INFO`
  structure (MS-SFU, S4U2proxy page) listing the transited services;
  and the two asserted-identity SIDs record *how* the subject was
  vouched for. The client, however, "cannot detect that delegation
  will be, or has been, performed" (MS-SFU, S4U2proxy). The subject is
  never told.
- AWS: `SourceIdentity` is "set once", "persists when a role is used
  to assume another role", and "cannot be changed during the role
  session"; CloudTrail records it in `sessionContext.sourceIdentity`
  next to `sessionIssuer` (the role) and the session ARN (the actor).
  Transitive session tags ride the same way. AWS notes one hole: "The
  source identity information is not captured by CloudTrail when an
  AWS service or service-linked role carries out an action on behalf
  of a federated or workforce identity."
- Capsicum: every limit call is audited with the fd and the rights
  (`sys_capability.c:301-302`); every refusal can be ktraced with the
  needed and held rights (`_cap_check`, `:156-167`).
- Biscuit: each block has an index and a `revocation_id` (its
  signature, `SPECIFICATIONS.md:651-656`); a third-party block carries
  the signer's public key. A *first-party* block has no author: any
  holder could have appended it. Errors name `block_id` and `check_id`
  (biscuit-rust `FailedBlockCheck`).
- Macaroons: caveat order is the only provenance. The paper's design
  goal runs the other way: the target verifies "without TS knowing
  that the request from C is on behalf of a user 'bob' (thus
  protecting the user's privacy)" (§III). Anonymity of the narrower is
  a feature there and a bug for vfs.
- SPIFFE WIT-SVID adds proof of possession (`cnf`), so a token in a
  log proves *which key* presented it (`spiffe:WIT-SVID.md:212-222`),
  which JWT-SVID bearer tokens cannot (`JWT-SVID.md:117-124`).

For vfs's version row this says: record actor and subject as
first-class columns (RFC 8693's `sub` + `act`, AWS's session ARN +
`SourceIdentity`), record the *provenance class* of the subject
(Kerberos's two SIDs: verified at the edge vs asserted by a
subsystem), and do not expect the narrowing itself to be attributable
unless vfs stamps it at session open.

## Q9. Failure modes on record

**Verdict: supports** (the structural fix is capabilities; the
conventional fix is an out-of-band identifier the deputy must echo).

- **Confused deputy, structural.** Hardy: "The fundamental problem is
  that the compiler runs with authority stemming from two sources"; the
  fix is that "the capability both identifies the file and authorizes
  the compiler to write there ... no ASCII character names are
  required, no authority checking mechanisms are executed" (1988,
  p. 37). Miller, Yee, Shapiro generalize: "In a system where
  designation and authority are inseparable, this common type of
  confused deputy problem ... simply cannot occur"; and "Eliminating
  ambient authority helps make it possible to avoid confused deputies,
  but doesn't guarantee that deputies will never be confused" (2003,
  §Avoiding Confused Deputy Problems). Even in a capability system, a
  deputy "deciding to try all available keys puts one at risk".
- **Confused deputy, by convention.** AWS `ExternalId`: the deputy
  (Example Corp) generates a per-customer value and the customer pins
  it in the trust policy; "Even if another customer supplies Example
  Corp with your ARN, it cannot control the external ID that Example
  Corp includes in its request". It "is not a secret" and "can be seen
  by anyone with permission to view the role". Cross-service:
  `aws:SourceArn` / `aws:SourceAccount` on service-principal grants.
  Both work only if the deputy always includes the right value; AWS
  tells vendors to "test whether you can assume the role both with and
  without the correct external ID" and refuse to onboard if the
  latter works. This is the same shape as 070 D6's "no served tool
  exposes a `principal` parameter": the deputy must never take the
  subject from its caller.
- **Unconstrained delegation.** A forwarded TGT "does not constrain
  Service 1's use ... Service 1 can continue to masquerade as a
  legitimate user to other services" (MS-SFU §1.3.3 steps 13-15).
  Constrained delegation replaced it with the KDC's allow-list.
- **Protocol transition.** S4U2self lets a service mint a ticket for
  any user it names; resource-based constrained delegation "can't use
  the Trusted-to-Authenticate-for-Delegation bit ... The KDC always
  allows protocol transition" and pushes the decision to the
  resource's ACL via the asserted-identity SIDs (Microsoft, KCD
  overview). vfs's equivalent is the trusted-subsystem shape in 070 D7,
  and the lesson is the same: mark it.
- **Replay and audience.** JWT-SVID: "if Alice has a token with
  audiences Bob and Chuck, and transmits that token to Chuck, then
  Chuck can impersonate Alice by sending the same token to Bob"
  (`spiffe:JWT-SVID.md:120-121`); single audience is "strongly
  recommended". WIT-SVID: "MUST NOT be presented as a bearer token"
  (`WIT-SVID.md:218-221`). Macaroons bind discharges to the
  authorizing macaroon (`bindForRequest`) because "an attack is
  possible if the client accidentally makes a request to a principal
  other than the original target" (§IV-B). authlib's claims validator
  rejects a token whose `aud` does not contain the expected value
  (`authlib:authlib/jose/rfc7519/claims.py:130-162`); RFC 7662
  introspection returns `{"active": false}` for unknown tokens rather
  than an error (`authlib:authlib/oauth2/rfc7662/introspection.py:69-81`).
- **TOCTOU.** Capsicum updates the rights mask under a seqlock
  (`sys_capability.c:247`), and the strict-relative walk re-checks each
  `..` against the directories "previously walked by us"
  (`vfs_lookup.c:282-299`). WASI's design "remains effective even in
  the presence of outside processes accessing the same filesystem,
  including renaming" (`path-resolution.md`). monty: "directories
  swapped mid-operation cannot reach outside" the mount's descriptor
  (`docs/filesystem.md:104-105`).
- **Passthrough.** Casper's own comment names the risk of a helper
  that accepts a caller's stated limits: "When new connection comes in
  with different limits we won't be able to access requested
  resources" (`freebsd-src:lib/libcasper/libcasper/service.c:60-61`);
  the fix is that limits only shrink. monty: "A host function that
  takes a path and reads it ... is an unconstrained filesystem or
  network primitive that you wrote" (`docs/security.md:82-86`). Both
  are the confused deputy one layer up, which is what 070 D7 forbids.

## Q10. Reversibility and permission together

**Verdict: no precedent** for "who may revert whose change", with one
qualified lead.

None of the capability or token systems here has a notion of a
revertible action. Their answer to "undo" is *revocation of
authority*, not reversal of effects: Miller's revocable forwarder
("When Alice wants to revoke Bob's access to Carol, she invokes R,
telling it to stop forwarding", 2003, §Revocable Access), biscuit's
per-block `revocation_id`, macaroons' four strategies (short life,
freshness caveats, revocation lists, "splitting credentials", §II).

The one lead is macaroons §V-E, "Revocation and Versioning": "the
operation `delete` may be added to a target service that offers
previously-immutable, read-only storage, and the existing macaroons for
this target may not constrain the operations in requests. In this
case, the service may implement a default-deny policy for the `delete`
operation ... As a more principled approach, target services may
*version* aspects of their service, and embed first-party predicates in
macaroons that constrain the authorized versions." Read for vfs: a
right can be pinned to a version range, so "revert to v3" is an
operation that needs a right over v3, not a right over the current
row. Whether a holder whose rights were narrowed *after* v3 may still
revert to it is exactly the question the paper does not answer.

The capability answer to "can a revert exceed the actor's rights?" is
mechanical: a revert is a write, a write needs the write capability,
and the capability the actor holds now is what counts (Capsicum checks
`fde_rights` at every syscall, not at open). So under a pure capability
reading, an actor narrowed to read-only cannot revert anything, even
its own earlier write. Whether vfs wants that is a policy question
for Phase 3.

## Q11. Scale and portability, and the cost to SQL enforcement

**Verdict: qualified.** A capability is checked at the reference; a
grant row is checked in the query. The two reconcile if vfs keeps
grants as rows (the authority block) and treats session narrowing as a
*bounded* caveat list compiled into the same predicate as AND terms.
That is what ADR 021 D1 already describes for deny ("a policy-layer
expression over grants, never ... a row").

What each system tells us about size:

- Capsicum rights are a fixed array of `uint64_t`
  (`freebsd-src:sys/sys/caprights.h`, `cr_rights[CAP_RIGHTS_VERSION + 2]`);
  `cap_ioctls_limit` caps the list at `IOCTLS_MAX_COUNT`
  (`sys_capability.c:424`). Attenuation state is constant-size by
  construction.
- AWS caps a session policy at 2,048 plaintext characters, 10 managed
  policy ARNs, and 50 tags, with a separate packed-size limit and a
  `PackedPolicyTooLarge` error (`AssumeRole`). The narrowing document
  is small on purpose; the *grants* (identity policies) live server
  side and are not shipped with the session.
- Macaroons and biscuits ship the narrowing with the request and
  evaluate it against request facts; biscuit's authorizer additionally
  loads "lists of users and roles" per request
  (`SPECIFICATIONS.md:640-645`). The paper measures verification at
  "96.3 µs" in Python for four caveats (Table II). Neither system
  pushes the check into a datastore; both are per-object gates.

The reconciliation with ADR 021:

1. **Grants stay rows, checked by `EXISTS`.** Nothing in this lens
   argues for shipping the grant set in a token; AWS explicitly keeps
   identity policies server side and ships only the narrowing.
2. **Narrowing is a bounded list of restrictive terms.** A profile or
   session caveat (`path under /team/x`, `read only`, `not before
   version N`) compiles to an AND clause on the same query. Because
   caveats only subtract, the read predicate remains
   `EXISTS(grant) AND caveat_1 AND ... AND caveat_k`, and `k` is
   declared and small, the AWS way. No `IN`-list grows with batch
   size, so the `membership_budget` rule is untouched; the bind count
   grows with `k`, not with rows.
3. **Reference-time checks still happen once per statement.** Capsicum
   checks the mask on every syscall; vfs's equivalent is that every
   verb passes the one chokepoint. What vfs cannot do is Capsicum's
   "check at the descriptor, not the name": the path *is* the
   designator, and ADR 021 D2 accepts that recombination cost.
4. **Portability is free.** AND-terms of string prefix and integer
   comparisons are the portable subset on every SQLAlchemy dialect;
   nothing here needs a JSON policy engine in the database.

The open cost is Q13's: a subject set of size `n` multiplies the
`EXISTS`, and S1 in the plan is the study that prices it.

## Q12. Take / adapt / reject for vfs

See the table after Q13.

## Q13. Many subjects at once

**Verdict: qualified** relative to the multiplayer intersection rule.
Conjunctive *credentials* have precedent. Conjunctive *authority*
(rights equal to the meet of several subjects' grants) has none.

What exists:

- Macaroons are conjunctive by construction: "all the caveats'
  predicates must hold true" (§III), and a macaroon may "require any
  number of holder-of-key proofs to be presented with authorized
  requests" (§III). The paper's example needs a discharge from an
  authentication service *and* could need one from an audit service:
  "caveats that require proof that the requests have been audited and
  approved by an abuse-detection service, and come from a specific
  device with a particular authenticated user" (§II). That is m-of-m
  authorization across several parties. §V-F adds that disjunction
  ("only one needs to be discharged") is possible but is a separate
  design. There is no threshold (k-of-n) construction; the paper
  reduces to "proof-carrying authorization" and stops there.
- Biscuit: checks accumulate across blocks and all must pass
  (`SPECIFICATIONS.md:303-306`); a check `trusting <pk>` needs a fact
  signed by that key, so two such checks need two signers. Again
  m-of-m, no threshold, and the signers *supply facts*, they do not
  contribute authority blocks.
- AWS: up to 10 session policies, but they are OR'd among themselves
  ("If multiple policies apply to a request, AWS applies a logical OR
  across all of those policies") and then intersected with the one
  role. Several policies do not mean several subjects.
- Capsicum: `cap_rights_contains` is a subset test on one descriptor;
  `cap_rights_merge` (`subr_capability.c:320`) is a union used by the
  kernel, never by a sandboxed caller. No multi-holder construct.
- Dennis and Van Horn: a group is a principal that *widens* what its
  members reach (Unix supplementary groups, the case the plan names as
  the opposite of the rule).
- Hardy: the deputy with more than two authorities is what broke
  "switch hats". Multiplayer forbids the hat-switch entirely: the agent
  must not choose which member's authority to use. Intersection is the
  design that removes the choice, and therefore removes this class of
  confusion. That is an argument *for* the rule that no system here
  makes but every one of them supports.

What does not exist, and what it implies:

- **Tokens attenuate one authority block.** Biscuit's scope rule
  guarantees a later block cannot add rights; macaroons' HMAC chain
  guarantees a later caveat cannot remove one. Neither can express
  "the authority is the meet of Alice's grants and Bob's grants",
  because grants are not in the token, only checks are. So the subject
  set cannot be a chain of per-member blocks. The meet has to be
  computed where the grants live, once, when the session is minted.
  That lands on ADR 021's spine, not on a token.
- **Ownership of what the set creates: no precedent.** Dennis and Van
  Horn already flagged the orphan ("but how do we choose?"). Kerberos
  writes the *user* as `cname` even when a service acted. RFC 8693
  says the top-level `sub` is the party whose rights apply. The
  nearest analogue is "owner = the subject set, as a set", which no
  system here can represent because none has a set-valued subject.
- **Audit of a set: partial precedent.** Macaroons record the
  discharges (one per third party); biscuit records one external
  signature per third-party block; AWS records transitive tags and one
  `SourceIdentity`. So "one attribution row per member" has a shape.
  "The set as a single principal id" does not.
- **Mid-session change: re-mint.** Macaroons and biscuits are
  immutable; adding a member means a new token (a narrower one, if the
  new member holds less). AWS: a chained session cannot outlive its
  parent and cannot change `SourceIdentity`. 070's "refresh → new
  session" rule is the same instinct. A member *leaving* is the harder
  case: nothing here widens a live credential, so the honest answer
  is "the session stays at the old meet until re-minted".
- **Hide-if-hidden-from-any: supports by analogy.** WASI hides
  anything outside the preopen for *every* caller; a macaroon with two
  dischargers reveals nothing to a bearer missing either. The leak
  rule follows from conjunction.
- **Composition with the actor's profile and with admin.** All the
  attenuation systems compose by intersection with whatever else
  caps the session (AWS: "the intersection of the session policy, the
  permissions boundary, and the identity-based policy"). Admin as a
  member of the set is just another term in the meet; admin as the
  *actor* bypassing the meet is the `Principal.system()` case in
  ADR 021 D4 and has its analogue in AWS's resource-policy-on-session
  hole, which is to say it must be an explicit, marked exception.

## Take / adapt / reject for vfs

| Item | Decision | Why |
|---|---|---|
| Narrowing-only as a hard invariant of sessions and profiles: any operation that would add a right is refused, the way `cap_rights_limit` refuses `CAPFAIL_INCREASE` | **take** | universal across the lens; the check is a subset test, cheap and auditable |
| One named widening path, gated by a second party, stamped in the audit (Kerberos `SERVICE_ASSERTED_IDENTITY`; biscuit external signature) | **adapt** | 070 D7's trusted-subsystem shape needs the stamp; the version row should carry "subject verified at edge" vs "subject asserted by subsystem" |
| Actor and subject as two first-class columns on every version row, with the delegation chain kept but only the current actor used for policy (RFC 8693 §4.1) | **take** | direct precedent; avoids policy evaluated over stale chain members |
| `SourceIdentity` semantics: set once at session open, immutable, inherited by any sub-session | **take** | the audit needs one stable "who started this" across nested agents |
| Grants as rows; session narrowing as a bounded AND-list compiled at the chokepoint (AWS's 2,048-character session policy as the model) | **take** | reconciles capabilities with ADR 021 D1/D3 without shipping grants in a token |
| A declared budget on caveat count per session, with a refusal kind when exceeded (`PackedPolicyTooLarge`) | **take** | keeps the compiled predicate bounded on every dialect |
| Deputy never accepts the subject from its caller; confused-deputy defence is structural at `serve()` (070 D6), with an `ExternalId`-style pinned value only where a remote deputy must echo context | **take** | Hardy and AWS agree from opposite ends |
| Hide-not-deny for anything outside the caller's visible set, including `..`-style probes that would "resolve back inside" | **take** | WASI's exact rule; matches 058's `invisible` rung |
| Group membership resolved at query time (biscuit facts, macaroon third-party discharge) rather than frozen into the session | **adapt** | closes ADR 021's fork toward "resolve per query" for correctness; S1 must price the join |
| Version-pinned rights (macaroons §V-E): a right may name a version range, so revert is a write that needs a right over the target version | **adapt** | the only lead on Q10; needs Phase 3 to decide whether a narrowed actor may revert its own earlier write |
| Subject set computed as the meet of grants at session open, on the grant spine, then attenuated; membership change is a re-mint | **adapt** | no token can express a multi-subject authority block; the spine can |
| Per-member attribution rows for a set session (one discharge per party) rather than a synthetic set principal id | **adapt** | the only audit shape with precedent; ownership of set-created rows stays an open Phase 3 question |
| Shipping grants inside a bearer token (macaroon/biscuit style) and verifying per object | **reject** | vfs's grants are large and mutable; every system here keeps the big policy server side and ships only the narrowing |
| Multi-audience or bearer-only identity tokens between vfs components | **reject** | JWT-SVID §7.2 replay; WIT-SVID forbids bearer presentation; 070 D7 already bans passthrough |
| A `switch hats` API for an agent serving several principals (pick one subject per call) | **reject** | Hardy's failed fix; multiplayer's intersection removes the choice instead |
| Casper-style helper that holds ambient authority on behalf of the sandbox | **reject** for the data plane | vfs's boundary is the data; the harness owns process helpers (plan §6) |

## Limits

- **Miller 2006 was not reachable.** The 2003 "Capability Myths
  Demolished" paper by Miller, Yee and Shapiro carries the same
  seven-property model and the confused-deputy argument, and is what
  is cited above. The thesis's caretaker and membrane patterns are
  known to the author but not quoted here.
- **The biscuit clone is the specification, not the Rust crate.** The
  attenuation and authorization code (`append`, `seal`,
  `append_third_party`, `authorize_inner`, `TrustedOrigins`) was read
  on GitHub, and line numbers there are approximate. If Phase 3 needs
  the crate, clone `eclipse-biscuit/biscuit-rust` (Apache-2.0) and
  re-cite.
- **`freebsd-src` is a sparse checkout.** `lib/libcasper` and the
  Capsicum man pages in `lib/libsys` were read with `git show HEAD:`,
  which is read-only and does not touch the working tree. Casper's
  service-side limit code was read at the lines given; the per-service
  limit functions (`cap_dns`, `cap_fileargs`) were not read line by
  line.
- **WASI preview1 has left `main`.** Its `docs.md` was read from the
  `snapshot-01` branch on GitHub. Preview2's WIT in the clone is what
  vfs should model on anyway.
- **authlib has no RFC 8693 mechanics.** `authlib/oauth2/rfc8693/`
  is an eight-line docstring; spec 070's review already recorded this.
  The `act`/`may_act` semantics above come from the RFC.
- **AWS and Microsoft docs are vendor prose**, not code. Where a
  behaviour matters (the resource-policy-on-session hole; the
  resource-based constrained delegation rule on protocol transition)
  the sentence is quoted so a reader can check it.
- **No measurements.** Q11's cost claims are structural (what grows
  with what). S1 in the plan is where numbers come from, and this
  memo's only ask of S1 is to include the `k`-caveat AND-list and the
  `n`-subject meet in its matrix.
- **Threshold (k-of-n) authority has no precedent in this set.** The
  claim is limited to the sources studied; the lens did not survey
  threshold-signature or multi-party-computation literature, which the
  plan did not ask for.
