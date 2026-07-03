# 045 — The Verb Surface Is a Wire Contract: Pin It Before a Remote Speaks It

- **Status:** draft
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** analysis + contract (schema pinning, skew policy) — feeds 034
- **Depends on:** 036 (router verb surface — the signatures being
  pinned), 035 (op vocabulary), 037 (single result channel — the outbound
  half of the contract already exists: `Result.to_payload`)
- **Enables:** 034 (a routing mount is exactly "this contract over MCP" —
  it should consume a written schema, not mirror Python signatures by
  hand), the outbound `vfs serve` sibling, version-skewed peers that fail
  classified instead of crashing

## Intent

Every dispatch to a child forwards the parent's full kwarg set into the
child's *public method*: `getattr(fs, op)(path=rel, user_id=user_id,
**kwargs)` (`base2.py:515`, `:572`, `:650`, `:720`, `:742`, `:812`). That
makes the Python signatures of the 16 verbs the de-facto protocol between
namespace nodes — today enforced by nothing but both sides being the same
codebase in the same process.

The result half of the wire contract is already deliberate: `Result.
to_payload()` / `from_payload()` round-trip losslessly, unknown error
kinds are preserved as raw strings so "a newer peer's novel kind never
poisons the payload" (`results2.py`). The **request half has no
equivalent.** No written schema says what `grep` takes, no policy says
what a receiver does with a param it doesn't know, and skew today fails
as `TypeError` — which `_gather_settled` classifies as an impl bug and
re-raises raw (`base2.py:833-843`). A version-skewed peer would crash the
caller's turn instead of answering `invalid`.

This story is the paper exercise plus the pin: walk one fan-out `grep`
through a hypothetical routing mount, write down the request schema for
every verb, decide the unknown-param policy, and land drift tests so the
Python surface and the written contract cannot diverge. It deliberately
lands *before* 034 builds the mount class, so 034 implements a contract
rather than reverse-engineering one.

## Why — the skew scenarios that force a decision

- **Newer caller, older receiver.** Parent's `grep` grows a kwarg (the
  16-param signature at `base2.py:960-980` has grown steadily:
  `case_mode`, `word_regexp`, context windows all landed post-035). An
  older peer receiving the unknown param must choose: reject classified,
  or ignore. Today's in-process answer is `TypeError` → raw crash on the
  impl-bug channel — the one channel 037 reserved for *our* bugs, now
  reachable by *someone else's version*.
- **Older caller, newer receiver.** Must be safe by construction: every
  param addition ships with a default that preserves prior behavior.
  That rule exists implicitly (every recent addition did so); it is not
  written anywhere a reviewer would check.
- **The result half already chose.** Unknown error kinds pass through;
  non-finite scores degrade documented. The request half should be
  decided with the same care, not inherited from `TypeError`.

And one asymmetry worth writing down: the **request** direction is where
tolerant-reader is *dangerous*. Silently ignoring an unknown request
param can invert meaning — a receiver that drops `invert_match=True`
returns exactly the wrong lines, successfully. Results tolerate unknowns
safely; requests often cannot.

## The question being answered

For each verb: what is its canonical request payload (param names, JSON
types, defaults, which are required), and what must a receiver do with a
param outside its vocabulary?

"Answered" means:

1. **A written schema** — `contracts/verbs.md` (or JSON Schema files) in
   this story folder, one entry per op in `ALL_OPS`, covering name, type,
   default, required/optional, and semantics one line each. The MCP
   projection (how these become `inputSchema` on a VFS-protocol server)
   sketched alongside, since 034's routing mount consumes exactly that.
2. **A skew policy, decided and recorded** — proposed:
   - *Receiver:* an unknown request param is `invalid`, classified, never
     ignored (the `invert_match` inversion above is the argument; a
     receiver that cannot honor a stated constraint must not answer as if
     it had). Explicitly *not* tolerant-reader on requests.
   - *Caller:* new params always carry behavior-preserving defaults, and
     the caller omits default-valued params from the wire (an older
     receiver then only errors when the caller actually *uses* a feature
     it lacks — skew hurts precisely when it must, never gratuitously).
   - *Classification:* signature mismatch at the boundary is `invalid`
     (or `unrecognized` for a whole unknown op — the kind already exists
     for exactly this, `results2.py:63`), never a raw `TypeError`.
3. **Drift tests** — the 035 pattern extended: a test that introspects
   each public verb's signature and compares names/defaults/annotations
   against the written schema table, so editing a signature without
   editing the contract fails CI, and vice versa.
4. **Capability granularity — decided (2026-07-03): op-level only.**
   `capabilities()` stays a set of op names; there is no param-level
   negotiation. The omit-defaults caller rule is what makes this safe —
   an older receiver only sees a param when the caller actually uses the
   feature, and then it fails classified. Param-level negotiation is
   protocol-committee machinery deferred until a real peer proves the
   need.
5. **Identity is connection-derived — decided (2026-07-03):** `user_id`
   is **not** part of the wire contract. VFS is OAuth-native at the
   boundary: a remote server derives the principal from its own
   session/connection auth, never from a caller-asserted string in the
   request payload (which would be spoofable the moment a boundary is
   crossed — and `user_id` has no OAuth-native meaning anyway).
   In-process mounts keep passing `user_id` as today; the schema marks
   it local-only, excluded from every wire payload, and the MCP
   projection simply has no such field.

## Out of scope

- Building the MCP adapter/serializer itself — 034 and the `vfs serve`
  sibling own the transport; this story hands them the contract.
- In-process Python callers passing garbage kwargs — that stays a
  `TypeError` at the outermost public method, correctly: the wire seam is
  where the policy binds, not local Python misuse.
- Changing any verb's current parameters or semantics — pinning, not
  revising. (If writing the schema surfaces a param that shouldn't
  survive contact with the wire, that spawns its own story.)

## Test plan

1. **Schema drift:** the introspection test above — every op in
   `ALL_OPS`, both directions (signature param missing from contract;
   contract param missing from signature).
2. **Defaults preserve behavior:** for each verb, calling with only
   required params equals calling with all defaults spelled out
   (parametrized over the schema table — this is the older-caller
   guarantee, executable).
3. **Paper-walk artifact:** the fan-out `grep` walk (parent → routing
   mount → remote, request and result payloads at each hop) checked into
   the folder as `research.md` — the concrete trace 034 implements
   against.

## Open questions

None — granularity and identity are decided above (items 4 and 5). The
schema's long-term home is settled by rule rather than debate: it lives
in this story folder until 034 consumes it mechanically, at which point
it moves `vfs/ops.py`-adjacent as the table the drift test and the MCP
`inputSchema` generator both read — two consumers is the trigger, not a
future discussion.
