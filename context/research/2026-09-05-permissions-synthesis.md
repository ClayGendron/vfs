# Principals and permissions: the synthesis (Phase 3)

- **Status**: research memo, Phase 3 of the principals and permissions
  programme (`2026-09-05-principals-and-permissions-research-plan.md`).
  It digests the framing memo, the five lens memos and the two studies
  into one verdict table, states whether the hypothesis survived, and
  hands the result to six proposed decision records (ADR 062 to 067)
  that await Clay's ratification. Commits us to nothing by itself.
- **Date**: 2026-09-05
- **Owner**: Clay Gendron
- **Question**: Does the hypothesis (subject, actor, attenuation, with a
  subject *set* for the multiplayer case and the intersection law for
  read and write) survive fifty years of prior art and two measured
  studies? Where does it need correcting, and what is still open?
- **Method**: a read of the seven Phase 0 to 2 memos (below), their
  thirteen-question verdicts tabulated, the threat table checked row by
  row against the drafted rules, and the studies' numbers carried into
  the decisions they settle. No new sources.
- **Inputs**:
  `2026-09-05-permissions-framing-threat-model-and-requirements.md`
  (64 threat rows, seven audiences, the frozen rubric);
  `2026-09-05-permissions-lens-unix-lineage.md` (L1);
  `2026-09-05-permissions-lens-plan9.md` (L2);
  `2026-09-05-permissions-lens-capabilities-and-delegation.md` (L3);
  `2026-09-05-permissions-lens-authz-engines-and-databases.md` (L4);
  `2026-09-05-permissions-lens-agent-native-2026.md` (L5);
  `2026-09-05-permissions-predicate-at-scale.md` (S1, with
  `studies/2026-09-05-permissions-predicate-at-scale/`);
  `2026-09-05-glean-statistics-leak.md` (S2, with
  `studies/2026-09-05-glean-statistics-leak/`).

## Bottom line

The hypothesis survives with three corrections, and the multiplayer
rule survives with one exact precedent and two rules of its own.

1. **The pair is right; the precedent for it is wrong.** Unix's real
   and effective uid and Plan 9's `hostid` and `uid` are the
   actor/subject pair, but Unix built it to run *above* the invoker
   (setuid) and Plan 9 throws it away at the boundary (the auth server
   writes one name into both ticket slots). vfs keeps the pair to
   attribute and to narrow, and never lets a boundary drop it.
2. **"Never widens" is a law about the session, not about the
   principal.** No system runs on intersection alone; each ships one
   gated, marked widening. Every 2026 harness widens by a human click.
   The correct statement is: the session never widens *itself*; a
   principal widens by an attributed grant row that the session sees on
   its next call; one actor (system) is the marked exception.
3. **The subject set is a session construct on the grant spine, never
   a wire object.** Every token in the field has one subject; tokens
   attenuate one authority block and cannot express the meet of two
   people's grants. The meet is computed where the grants live.
4. **Conjunctive authority has one shipped precedent and it is exact:**
   SpiceDB's intersection arrow. Every member must hold the right, an
   empty set denies, membership is read live. The field's vendors ship
   three approximations (space-only, asker-plus-leak-gate, per-room
   service account) and none is the meet.
5. **The enforcement spine is the field's consensus and the measured
   shape is not the one ADR 021 sketched.** Compile in app code at one
   chokepoint, yes; but resolve the caller's covering prefixes first
   and ship a bounded literal, which is 3 to 19x faster than the
   correlated `EXISTS` and is the only shape that stays flat as a
   subject set grows (22 ms at n = 20, the same as one principal).
6. **Visibility must reach statistics.** Global BM25 statistics leak
   the hidden set totally, on scores, ranks and the merge's export;
   visible-set statistics close it at no measured ranking cost.

One line: **authority is a subject set, an actor and a narrowing;
rights are the meet of the subjects' grants, cut by the actor's
profile and the session, compiled to a bounded literal at one
chokepoint, applied before any content function and to the statistics
themselves, attributed to actor and subjects on every version row, and
widened only by an attributed grant outside the session.**

## 1. The verdict table

Verdicts are relative to the hypothesis (Q1 to Q12) and to the
multiplayer intersection rule (Q13). S = supports, Q = qualified,
N = no precedent, C = contradicts.

| # | Question | L1 Unix | L2 Plan 9 | L3 Capabilities | L4 Engines/DBs | L5 Agent-native | Studies |
|---|---|---|---|---|---|---|---|
| Q1 | Subject and actor distinct? | Q (split exists to widen) | Q (pair collapsed at boundary) | S (1966 paper; `act`) | Q (three-level identity; no OBO) | Q (identity tier ships it; harnesses have no subject) | |
| Q2 | Attenuation, narrowing only? | S (capability era) / C (setuid) | S (`none`, `RFNOMNT`) | Q (universal, but every system has one gated widening) | S (one widening primitive) | Q sessions / C delegation chains | |
| Q3 | Enforcement where? | S (one chokepoint per object) | S (in the server, per request) | S (checked at every use) | S (compiled into the query) | S (resource server, cooperatively) | S1: chokepoint priced |
| Q4 | Unit of protection | Q (object) | Q (mode bits) | Q (references) | S (path prefix; fork sharpened) | Q (tool+args) | S1: prefixes cheap |
| Q5 | Hide vs deny | Q (denies, never lies) | S (projection vs refusal) | S (preopens) | S (six leak classes) | S (disabled search vs preview gate) | S2: stats leak total |
| Q6 | Groups | C (union) / S tenants | S timing; groups widen | Q (no groups by design) | S (memberships per query) | Q (resolved at token issuance) | S1: literal groups |
| Q7 | Creation defaults, ownership, move | S (container beats creator) | S (inherit mask; owner immutable) | S (inherit = intersect) | Q (no umask; move = exit + entry) | N | |
| Q8 | Audit | N | Q (`muid` one name) | Q (in the credential) | Q (which rule decided) | Q (only Entra records both) | |
| Q9 | Failure modes | S | S | S | S | S | |
| Q10 | Revert vs rights | N | S (dump under same perms) | N (macaroon version pin) | N (zookie near miss) | N | |
| Q11 | Scale, portability | Q | N | Q | S (+ one constraint) | Q | S1: no shape breaks a budget |
| Q13 | Conjunctive authority | Q → N (meets are self-narrowing) | N (`srv -a` is the anti-pattern) | Q (conjunctive credentials, not authority) | **S** (SpiceDB `.all()`) | N (three approximations) | S1: intersection flat; S2: set stats fine |

Reading the columns: Q3, Q5, Q7 and Q9 are settled by consensus. Q1
and Q2 are settled with the corrections above. Q6 splits cleanly:
groups widen a *principal's* rights everywhere (union), which is fine
inside one subject's grants and forbidden across subjects, exactly the
algebra Landlock uses (union within a layer, intersection across
layers). Q8 and Q10 are ours to define; the nearest shapes are one
attribution row per party and "revert is a write". Q13 has one exact
precedent and otherwise silence.

## 2. What the studies settled

| Study | Finding | Decision it settles |
|---|---|---|
| S1 | pre-resolved prefix literal 3 to 19x faster than correlated `EXISTS` on Postgres, never slower elsewhere | ADR 067 rule 2 (amends 021 D3) |
| S1 | ranked join-back of 1,000 ids 3 to 20 ms on every engine under `membership_budget` | ADR 067 rule 5 |
| S1 | write point check: resolve in app code, 11 ms per 10k paths, one statement | ADR 067 rule 4 |
| S1 | materialised visibility 1,850x the entry table under everyone-grants | ADR 067 rejects it |
| S1 | membership subquery 35 s / 188 s; literal group list 13 to 110 ms | ADR 067 rule 3 (closes 021's groups fork) |
| S1 | subject set of 20: `EXISTS` AND 314 ms, `HAVING` 130 ms, prefix intersection 22 ms | ADR 066 rule 3, ADR 067 rule 2 |
| S1 | literal forms bounded by grant count, not batch | ADR 067 rule 6 (declared caps) |
| S2 | leak total on scores, ranks and `lexical_stats` at h = 50 % (precision and recall 1.0; hidden N within 2) | ADR 065 rules 4, 5 |
| S2 | visible-set statistics: nDCG@10 within noise on every partition | ADR 065 rule 5 |
| S2 | coarsening residual recall 0.91; stale snapshot 0.42 | ADR 065 rejects coarsening |
| S2 | intersection statistics within 0.017 of global down to a 17 % corpus | ADR 066 consequence (quality pin) |

## 3. The threat table, answered

The framing memo's 64 rows reduce to five failures plus the
multiplayer group. Each has a rule now:

| Failure class (rows) | Rule |
|---|---|
| Acting with the library's authority, confused deputy (T12 to T15) | ADR 062 rule 1: the actor contributes no rights; 070 D6 stands |
| Narrowing that leaves a way back (T19 to T21) | ADR 063 rules 1, 4: copy-on-write session, widening is a new session |
| Policy evaluated on rows the caller cannot see (T34 to T40) | ADR 065 rules 4, 5: predicate before content functions; visible-set statistics |
| Identity or token crossing a wire (T26 to T33) | ADR 062 rule 6, ADR 066 rule 3: verified names attested, meet re-derived far side |
| Check then act, TOCTOU (T37, T57) | ADR 063 rule 2 and ADR 067 rule 4: rights per statement; batch gate before the first byte; `explain` advisory |
| Multiplayer (T58 to T64) | ADR 066: intersection on read and write, hidden-for-any, joining narrows, leaving never widens, actor adds nothing |

## 4. What the hypothesis looks like now

```
Authority = (subjects: non-empty set of Principal, actor: Principal, narrowing: Profile)

rights(stmt) = ⋂_{s ∈ subjects} grants(s)          # ADR 067: resolved rows → covering prefixes
             ∩ profile(actor)                       # ADR 062 rule 1: never adds
             ∩ narrowing                            # ADR 063: only shrinks, per call
             ∩ structure                            # path maps, op masks, topology locks

hidden(row)  = ∃ s ∈ subjects : row ∉ visible(s)     # ADR 065 rule 7
stats(query) = over ⋂_{s} visible(s)                 # ADR 065 rule 5
audit(row)   = (actor, subjects[], provenance, grant_revision)   # ADR 064
owner(row)   = the one subject if |subjects| = 1, else NULL      # ADR 064 rule 4
widen        = a grant row by a principal, outside the session  # ADR 063 rule 2
exception    = Principal.system(): skips grants, stamped         # ADR 062 rule 4
```

## 5. The decision records

| ADR | Title | Ratifies / amends |
|---|---|---|
| 062 | Authority is a subject set, an actor and a narrowing | supersedes 070 D1's shape; keeps 070 D4, D6, D7; refines 006, 058 |
| 063 | The session never widens itself | binds 070's facade, roadmap 023, the `ask` rung |
| 064 | Every version row names actor and subjects; ownership from the container | amends 013/017; resolves 021's NULL-owner fork |
| 065 | Hidden rows are absent; statistics over the visible set | binds 058's `invisible` rung, `glean`, `rerank.py`, `grep` |
| 066 | The subject set and the intersection law | new |
| 067 | The enforcement spine compiles to a bounded literal | ratifies 021 D1, D2, D4; amends D3; closes the groups fork |

## 6. Still open, deliberately

- **Re-grading on join.** Whether a session may re-grade content it
  already surfaced when a lower-cleared member joins is a product
  decision (ADR 066 leaves it; the field widens the joiner instead).
- **The `ask` rung's wire shape.** ADR 063 fixes the semantics (a
  Result bound to a request digest); the MRTR `requestState` shape
  waits on the `serve()` spec.
- **Nested group depth and the prefix cap values.** ADR 067 declares
  them; S1's scripts size them per engine when spec 058 is written.
- **Fork B2 and vectors.** S2 measured the lexical leg. The embedding
  leg's distance function runs under the same predicate (ADR 065
  rule 4); whether any vector statistic leaks is a follow-up.
- **The remote-mount attestation.** ADR 062 rule 6 says verified names
  cross under the near side's attestation; the mechanism is the
  `serve()` spec's (070 D7's trusted-subsystem shape).

## 7. What happens next

1. Clay ratifies, amends or rejects ADR 062 to 067.
2. Spec 070 is rewritten around `Authority`; spec 058 is written in
   full against ADR 067 with S1's scripts as its benchmark; a sessions
   spec (narrowing, sub-sessions, `pending`) and the `serve()` auth
   spec are seeded.
3. The pjdfstest-shaped permission conformance suite (L1's take row)
   enumerates (authority, object state, verb) triples, one result kind
   per clause, and S2's scripts become the leak regression.
