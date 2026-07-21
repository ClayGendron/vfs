---
name: contract_review
description: Adversarially verify an implementation against its declared contracts — docstrings, specs, ADRs, type signatures, and error-classification tables — catching both broken promises and behavior no contract mentions. Use when the user asks to "review against the spec", "check the contract", asks "does the code still match the docstring/ADR", wants a diff or branch checked for documentation drift, or before landing a change that touches documented behavior.
---

# Contract review — the code vs. its promises

A procedure for reviewing a diff or branch through one lens: **every
behavior is governed by a written promise, and when code and promise
disagree, exactly one side is wrong.** The output is a findings list
where each finding names the wrong side — code or contract — with a
quote from both.

The core insight: most review defects hide in the gap between what the
code *does* and what something *says* it does. Prose that lies about
correct code is still a defect — stale documentation measurably breeds
future bugs, because the next editor trusts the words. In this repo the
default arbitration is written down: code is a build artifact of
`context/`; when they disagree, fix the code unless the context is
demonstrably wrong.

## Process

### 1. Inventory every contract governing the touched code

Before reading any implementation, collect the promises. For each
touched module/function, gather:

- **Docstrings** — module and function, including docstrings of callers
  that describe what the touched code will do for them.
- **Type signatures** — parameter and return types, `Good | Error`
  unions, `None`-ability, declared exceptions. A signature is a contract
  the type checker only partially enforces; read what it *claims*.
- **Specs and ADRs** — the open spec in `context/specs/` the branch
  serves, plus any ADR in `context/decisions/` naming this behavior.
- **Error-classification tables and invariants** — error taxonomies,
  frozensets of accepted values, and repo-wide invariants from
  `CLAUDE.md` (e.g. no statement grows unboundedly with batch size;
  10,000+ file batches are a supported contract).

Build a **contract register**: source (file:line), the promise in its
own words, and the code it governs. Touched public behavior with no
findable contract is itself a finding — an undocumented boundary.

### 2. Read contract-first, predict, then verify

Take an adversarial stance borrowed from perspective-based reading:
read the contract *before* the code and write down what the code must
therefore do — inputs it must reject, outputs it must produce, errors
it must classify. Only then read the implementation and check the
predictions. Reading code first invites rationalizing whatever it does;
reading the promise first makes every deviation jump out.

### 3. Compare in both directions

**Direction A — broken promises.** For each register entry, locate the
code that delivers it. A promise with no delivering code, or code that
contradicts it, is a defect. Check the caller's side too: does the code
demand preconditions the contract never imposed on callers?

**Direction B — silent contract growth.** Re-read the diff asking what
the code now does that *no* contract mentions: new parameters, new
error paths, new side effects, changed ordering, widened accepted
input, behavior on inputs the old code rejected. Undeclared behavior is
not free bonus — it is a contract nobody agreed to, which callers will
depend on and nobody will preserve. Every such behavior gets a finding:
either the contract must grow to cover it, or the behavior must go.

### 4. Audit docstring and comment honesty

Prose that lies about what the code does is a defect **even when the
code is correct**. Hunt the classic decay signatures:

- Parameter or field names in prose that no longer exist in the
  signature.
- "Always"/"never"/"only" claims falsified by a branch added in this
  diff.
- Examples in docstrings that would no longer run or return what they
  show.
- Comments explaining a *why* that the diff just invalidated.

The fix for a lying comment is usually to fix the comment — but first
ask whether the prose records the intended behavior and the code
drifted. Intent decides which side is wrong, not recency.

**Boundary with ownership review.** This lens judges whether the prose
is *true*, not whether the implementation sits in the right module. A
promise that is honoured, but honoured in every caller rather than
where it is declared, is a placement defect owned by
`ownership_review` — leave it there rather than filing it twice.

### 5. Probe contract completeness at boundaries

Where the contract is silent, the code is deciding policy in the dark.
At every touched public boundary ask:

- **Errors** — is every failure mode classified? Does each raised or
  returned error appear in the declared taxonomy, and does prose say
  which failures are lawful answers (`None`) vs loud violations?
- **Edges** — empty input, duplicate keys, a 10,000-item batch,
  ordering of results, partial-failure behavior mid-batch, concurrent
  callers. If the code has an answer the contract doesn't state, file a
  contract-gap finding: the answer exists, it just isn't promised.

### 6. Hold the evidence standard

Every finding must quote **both sides of the disagreement**: the exact
contract line and the exact code line, each with a `file:line`
reference. A paraphrase is not evidence. If you cannot produce both
quotes, it is a hunch, not a contract finding — either dig until you
can, or drop it. Verify quotes by re-reading the cited lines before
reporting; a review that misquotes a contract is itself lying prose.

### 7. Deliver the findings

Report a findings list, most severe first. Each finding states:

- **Severity** — *breach* (code violates a declared promise), *growth*
  (undeclared behavior at a boundary), *decay* (prose lies about
  correct code), *gap* (contract silent where the code decides).
- **Which side is wrong** — code or contract — and *why*, arguing from
  intent: what was the promise for, and which artifact still serves it.
  Default when intent is unrecoverable: the contract wins.
- **The two quotes** with `file:line` for each.
- **Fix direction** in one line (change the code / change the prose /
  extend the contract), without writing the fix.

Close with the boundaries checked and found clean — a contract review
that reports only findings hides how much of the surface was verified.
