---
name: verify_findings
description: Adversarially verify one code-review finding by trying to refute it — reproduce the claimed failure, check declared intent, and check reachability — before it is allowed to reach the user. Use when a review agent hands you a single finding to verify, when the user asks "is this a real bug", "verify this finding", or "check this claim", or as the per-finding quality gate in a multi-agent review.
---

# Verify findings — kill it or confirm it

You receive exactly **one finding** produced by a review agent. Your job
is not to polish it, agree with it, or extend it: your job is to
**refute it**. Every false positive that reaches the reader costs
attention and burns trust in the whole review; a reader who hits a few
bogus findings starts ignoring real ones. The finding earns its place
in the report only if a genuine, effortful attempt to kill it fails.

The reviewer already made the affirmative case. You never re-argue it —
prosecuting and defending in one head is how confirmation bias wins.
You only look for the evidence that would make the finding false, and
you report honestly when you cannot find any.

## Ground rules

- **Never modify the repo.** Scratch scripts, harnesses, and fixture
  files go under the session scratchpad directory only. No edits to
  `src/`, `tests/`, or anything else in the tree — verification is
  read-and-execute, not write.
- **Run everything through uv from the repo root**: `uv run python
  <scratch-script>`, `uv run pytest tests/ -q`, `uv run ty check`.
- **Do not trust the reviewer's reasoning chain.** Re-derive from the
  code and documents yourself; a plausible-sounding chain is exactly
  what a false positive looks like from the inside.

## Process

### 1. Restate the finding as a falsifiable claim

Rewrite it in the form: *given inputs/state X, operation Y produces Z
(wrong value, exception, corruption, contract violation), whereas the
contract says W.* Every element must be concrete — a real call, real
arguments, a specific wrong outcome.

If the finding cannot be restated this way ("this feels fragile",
"this might confuse maintainers", "consider refactoring"), it is not a
defect claim. **Downgrade it to a question immediately** and skip to
the deliverable — do not spend execution effort on an unfalsifiable
statement, and do not let it masquerade as a bug.

### 2. Attempt refutation from three angles

Work all three. Any one of them can kill the finding; only surviving
all three can confirm it.

**a. Reproduce it.** Write a minimal scratch script that performs the
claimed failing operation and observe the actual outcome. Minimal
means trimmed to the claim: the smallest inputs and fewest calls that
should trigger the failure. If the claim involves scale (batch limits,
bind-parameter budgets), reproduce at the boundary, not at toy size.
For structural claims that cannot execute (type unsoundness, a race
seen by inspection, dialect-cap arithmetic), **independently
re-derive** the conclusion: read the actual code path from the entry
point down, doing your own derivation before comparing it with the
reviewer's. If your derivation disagrees with theirs, the disagreement
is the lead — chase it to ground.

**b. Check intent.** Declared intent lives in module docstrings,
`context/specs/`, and the ADRs in `context/decisions/`. Read the ones
covering the behavior. A behavior those documents intend is **not a
defect**, no matter how surprising — at most it is a design note. Be
precise about what the document actually commits to: "the spec doesn't
forbid it" is not intent; a docstring or decision that names the
behavior is.

**c. Check materiality.** Trace whether the claimed scenario can arise
through the public surface at all. Follow real call paths from public
entry points to the claimed bad state. A failure that requires inputs
no caller can produce, or a state an upstream invariant already
excludes, is unreachable — and an unreachable defect is not a finding,
though a load-bearing but unstated invariant may be worth a question.

### 3. Deliver a verdict — never "probably"

Exactly one of:

- **CONFIRMED** — the failure reproduced (or the structural claim
  independently re-derived), no docstring/spec/ADR declares it
  intended, and the scenario is reachable from the public surface.
  All three, or it is not confirmed.
- **REFUTED** — one of the angles killed it. State which one and show
  the evidence: the executed output contradicting the claim, the
  intent line declaring the behavior deliberate, or the guard that
  makes the scenario unreachable.
- **DOWNGRADED** — the observation is real but the finding as filed is
  wrong: severity inflated, or it is actually a question or design
  note rather than a defect. State the corrected form.

Hedged verdicts are banned. If you cannot decide within reasonable
effort, that is itself information: downgrade to a question and name
the specific unknown that blocked you (e.g. "requires a live Oracle
instance to observe the cap"). "Probably a bug" reaching the reader is
the exact failure this gate exists to prevent.

### 4. Meet the evidence standard

The verdict must be decided by something you can quote:

- A reproduction verdict quotes **executed output** — the actual
  traceback, the actual wrong value next to the expected one, or the
  passing run that contradicts the claim. Never a prediction of what
  the code "would" do.
- An intent or materiality verdict quotes **the specific line** — the
  docstring sentence, spec passage, or ADR decision; the guard clause
  or invariant that blocks the path — with its file path.
- A re-derivation verdict shows the derivation: the code path walked,
  step by step, to the confirmed or contradicted conclusion.

If the deciding evidence cannot be quoted, the verdict is not earned.

## Deliverable

Return the original finding annotated with:

1. **Verdict** — CONFIRMED, REFUTED, or DOWNGRADED.
2. **Evidence** — the quoted output or contract line that decided it,
   with file paths, per the standard above.
3. **For CONFIRMED only**: a **corrected severity**, judged from what
   verification actually showed (reachability, likelihood, blast
   radius) rather than inherited from the reviewer, and the **minimal
   repro** — the smallest script/steps that demonstrate the failure,
   ready for the reader to run with `uv run python`.
4. **For DOWNGRADED**: the corrected form — the question to ask or the
   design note to record — replacing the original claim.

The annotation is the whole deliverable. Do not add new findings you
noticed along the way; note them in one line as leads for a reviewer,
unverified.
