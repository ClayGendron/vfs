---
name: teach
description: Teach the user a part of this codebase (a file, module, or concept) as a paced, multi-response learning journey using Diátaxis as the framing. Use when the user asks to "learn", "understand", or "teach me" something, or invokes /teach. This file also accumulates observed lessons — what works and what doesn't — recorded during teaching sessions.
---

# Teach — paced codebase understanding

Turn "help me understand X" into a multi-response learning journey the
user steers. One concept per response. The user controls the pace; the
skill's job is to make omission safe by keeping a visible plan.

## The method

1. **Read the artifact fully before saying anything.** Teach *this*
   code, not the general topic. Anchor claims to `file:line` so
   authority lives in the code, not the prose.
2. **Ground each step in source material before teaching it.** Before
   every part of the journey — each step, each answer to a follow-up —
   reflect on what additional information is needed to fully explain
   it, and go read that first: neighboring modules, the reference
   implementation, specs, decision records, git history. Never teach a
   step from memory of the artifact alone, and never present a
   reconstructed rationale as the recorded one — label what the repo
   decided, what it recorded, and what you inferred.
3. **Model the learner before the content.** Check who they are: repo
   owner vs newcomer, what they built recently (git log), what the gap
   actually is. An owner's gap is usually *consolidation* — the code
   accumulated intricacy piece by piece and they want it to cohere —
   not orientation.
4. **Lay out a Diátaxis-shaped path first** (an advance organizer),
   then teach only step 1. The canonical quadrant order
   (tutorial → how-to → reference → explanation) is for newcomers; for
   an owner seeking coherence, invert it and lead with **Explanation**.
   Say so explicitly when deviating from the framework. Typical path:
   - **Explanation** (several small steps): the ideas the artifact is
     built on — the *why*.
   - **Reference**: a map of the file — entry points, helpers,
     invariants as tables to come back to.
   - **How-to**: trace real operations end to end through the code.
   - **Reference → Tutorial**: hands-on against a scratch setup,
     poking at the thing for real.
5. **One load-bearing idea per response, taught as a causal chain.**
   Ask: which single concept, if missing, makes everything else
   unmotivated? Teach that as a chain (A → so B → so C → therefore D),
   never a list of facts — each fact motivated by the previous one.
6. **Small moves inside a step:**
   - *Definition by contrast* — define the new thing against something
     the learner already knows cold.
   - *Compression via reframe* — chunk surface area down ("five verbs
     are really two machines plus a janitor").
   - *Rehearsal cue* — end with one italicized sentence the learner
     should be able to reproduce tomorrow.
   - *Close with a hook, not a summary* — plant the question that
     makes the next step feel necessary.
7. **Accept clean-but-simplified first passes knowingly** (spiral
   learning): early statements may be slightly too clean; later steps
   sand off the simplification where it's actually wrong. Don't front-
   load nuance that would break the pace.
8. **End every response with the pace back in the user's hands** —
   they ask questions, request a re-explain, or say "next."

One-sentence compression: diagnose the learner, find the single causal
chain the artifact hangs on, show the map, teach only the chain, and
end with the question that makes the next step feel necessary.

## Session log — what works, what doesn't

Recorded observations from real teaching sessions. Append here when
the user reports what landed or flopped; date each entry.

### What works

- **2026-07-25** (topology.py session): the full method above — map
  first, single causal chain, contrast-based definition, line anchors,
  reframe-compression, closing hook — drew "that was a great response"
  on the first step. Inverting Diátaxis for an owner-learner was the
  right call.

### What doesn't

- **2026-07-25** (topology.py session): when the learner asked *why* a
  design choice was made (the trash-chain hard-delete), the first
  answer presented a plausible reconstruction ("refusing would make
  trash undeletable") as if it were the design's actual rationale —
  and the reconstruction was leaky (`permanent=True` was always
  available, so refusal was viable). A one-line "why?" follow-up
  exposed it. The fix that worked: check the recorded rationale first
  (specs, decisions, code comments, the reference implementation)
  before reconstructing one — and **label which is which**: what the
  repo decided, what it recorded, and what I inferred. Chasing the
  "memory parity" comment into `memory.py` produced a strictly better
  answer (a contract argument) than the invented one. Bonus: honest
  design archaeology can surface real design tension — this exchange
  directly led to a contract change (delete never permanent, sweep
  developer-only).
