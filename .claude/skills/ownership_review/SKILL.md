---
name: ownership_review
description: Review the code a commit set touched (or a named code area) for logic that has accumulated in the wrong place, decomposing it into concerns and assigning each to its rightful owner, with duplication as the primary evidence. Produces an ownership map and proposed moves — it never edits the tree. Use when the user asks to "think in systems", asks "who owns this logic", wants a commit's code or an overloaded module reviewed for placement, or points at code where "a lot of logic lives here".
---

# Ownership review — think in systems

A procedure for reviewing code by asking one question per block of
logic: **which system owns this?** The output is an ownership map and
a minimal set of proposed moves — one move per violation — not a
rewrite.

## Scope

The unit of review is a **commit set** — one commit or a contiguous
range — or an explicitly named code area. The functions and modules the
set's diff touched are the units to decompose; read them whole at the
tip commit (placement is judged on the full unit, not the hunk), and
read the neighbors logic might belong to. When invoked standalone with
no scope handed in, default to the latest commit — widened to the whole
landing when the tip commits are one change split into pieces — and
state the resolved SHAs in the report. Report placement defects the set
introduced or worsened; pre-existing misplacement the diff merely
brushed is a note, not a finding.

The core insight: an overloaded function is rarely "too long" in the
abstract. It is hosting logic that belongs to other layers, and every
symptom below is evidence of a specific owner being bypassed.

**This skill is read-only.** It proposes moves; it never makes them.
Never modify, stash, checkout, or commit anything in the repo — the
deliverable is the table, the moves, and the behavior notes, and the
user decides whether any of it lands. Scratch scripts, if you need one
to check behavior, go under the session scratchpad only.

## Process

### 1. Decompose the code into concerns, not lines

Read the whole unit and label each block with what it *does* (data
fetch, gate check, transformation, bookkeeping, error construction…).
Then, for each label, name the layer that should own it. Build a table:

| Logic | Rightful owner | Today |

A block is correctly placed when its owner column matches the module it
sits in. The table is the deliverable of this step — it makes violations
visible before any code moves, and it is what you show the user.

### 2. Hunt duplication — the strongest evidence

For every concern, search the codebase for the same logic elsewhere
(grep for distinctive strings: error messages, constant values, helper
names — not just function names). **Verbatim duplication across sibling
modules is the signature of shared semantics living at the wrong
layer** — each copy proves no layer owns the meaning, so the copies will
drift the first time one is edited alone. Check constants and small
helpers too, not just the big block: duplicated collections and
duplicated error constructors mark the same disease.

### 3. Check declared contracts against implementation location

Read the docstrings and type definitions involved. A docstring that
*promises* a behavior which is actually implemented in every caller
(e.g. a type declaring "items are applied sequentially" while the
sequencing loop lives in each call site) is an ownership violation: a
promise should be implemented where it is declared.

### 4. Look for feature envy

Any block that reaches into another object's internals (getting a
sub-object then picking fields off it to answer a question) is that
object's method waiting to be written. The object owning the *data*
owns the *question* — move the logic, keep the call.

### 5. Derive the moves — one per violation, minimal new surface

For each violation, choose the new home by these rules:

- **Shared semantics get exactly one home** that every consumer
  imports — a small new module is fine; its docstring states *why* the
  agreement lives there ("so it cannot drift").
- **Pure engines stay leaves.** An algorithm/utility module must not
  grow domain imports. Give it the pure part (the loop, the
  computation); put the domain-aware wrapper (classification,
  validation, error minting) one layer up.
- **Promote duplicated helpers to the layer that owns their contract.**
  If a helper implements a contract documented on a type, it belongs
  beside that type, not in any consumer.
- **Encode outcomes in types.** Prefer a `Good | Error` union return
  over an `(good, error)` pair — the union says "exactly one outcome
  exists" and the type checker forces callers to dispatch on it.
- **Loud vs lawful absence.** A lookup whose miss is a lawful answer
  returns `None`; a lookup whose precondition guarantees presence
  raises on a miss, so a violated precondition fails loudly instead of
  flowing on as a misleading `None`. Choose deliberately per method and
  say which in the docstring.

### 6. Check behavior preservation for every proposed move

A move is only proposable if it preserves behavior, so chase every
subtle difference the move *would* introduce: which of two
near-identical values was actually stored (raw vs validated), which
fields are deliberately preserved from old state, whether validators
transform values or only reject them. Read the implementations
involved — do not assume. If the unification *changes* behavior (e.g.
two consumers quietly disagreed), that divergence is itself the most
valuable finding: two copies that were never actually identical are a
latent bug the duplication was hiding. Report it as its own finding,
never as a footnote to the move.

### 7. Evidence standard

Every finding names the block of logic (`file:line`), the layer that
should own it, and the layer hosting it today. A duplication finding
quotes **both** copies with their paths — the distinctive string you
grepped, in each home. "This function is doing too much" is not a
finding; "this validation is implemented identically at `a.py:40` and
`b.py:88`, so neither layer owns the rule" is. If you cannot name the
rightful owner, you have a question, not a violation.

### 8. Deliver findings

Report the ownership table from step 1 first — it is the map that makes
every finding legible — then a severity-ordered list of violations.
Classify each by kind:

- **misplacement** — logic hosted by a module that does not own it.
- **duplication** — one semantic rule with several homes, so no layer
  owns the meaning and the copies will drift.
- **envy** — a block reaching into another object's internals to answer
  a question that object should answer itself.
- **leak** — domain knowledge (classification, validation, error
  minting) inside a module meant to stay a pure leaf.
- **divergence** — copies that were supposed to be identical and are
  not; the latent bug from step 6.

Severity follows blast radius, not size: a divergence or a
misplacement that lets an invariant be bypassed outranks a tidy-looking
duplication of two constants. For each finding give the proposed move
in one line (from where, to where, why there) and any behavior note the
move would carry. Close with the concerns you checked and found
correctly placed, so a clean area is distinguishable from an unexamined
one.
