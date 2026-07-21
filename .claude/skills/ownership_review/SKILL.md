---
name: ownership_review
description: Methodically review and restructure code that has accumulated too much logic by decomposing it into concerns and assigning each to its rightful owner, with duplication as the primary evidence. Use when the user asks to "think in systems", asks "who owns this logic", wants an overloaded function or module restructured, or points at code where "a lot of logic lives here".
---

# Ownership review — think in systems

A procedure for restructuring overloaded code by asking one question per
block of logic: **which system owns this?** The output is an ownership
map and a minimal set of moves — one move per violation — not a rewrite.

The core insight: an overloaded function is rarely "too long" in the
abstract. It is hosting logic that belongs to other layers, and every
symptom below is evidence of a specific owner being bypassed.

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

### 6. Verify behavior preservation before cutting

Before editing, chase every subtle difference the move could introduce:
which of two near-identical values was actually stored (raw vs
validated), which fields are deliberately preserved from old state,
whether validators transform values or only reject them. Read the
implementations involved — do not assume. If the unification *changes*
behavior (e.g. two consumers quietly disagreed), flag it explicitly to
the user as part of the proposal; never smuggle a behavior change
inside a restructure.

### 7. Propose, then land green

Present the ownership table, the moves, and any behavior notes
**before** implementing — the user approves the design, not a diff.
After approval, implement in dependency order (deepest home first:
promoted helpers → engines → shared modules → consumers), then run the
project's full gate: lint, format check, type check, and the whole test
suite. All must pass; fix fallout (dead imports, shadowed names left by
mechanical renames) before reporting. Report what moved, where, and any
behavior notes the user must know.
