# Writing arc — home.md §1 "Building AI Agents is a Data Engineering Problem"

Beat structure worked out in a writing-coach session (2026-07). Reference when
drafting or revising section 1 of `docs/home.md`.

Target: ~300–350 words, six-ish short paragraphs, two to three sentences per beat.

## Opening — the grabber

- Aphorism: intelligence cannot replace knowledge (antithesis form; avoid the
  "data is knowledge" equation — it collapses the DIKW hierarchy and makes data
  engineers flinch).
- Claim: without context, an LLM is *always guessing*. Concession rhythm:
  modern LLMs are very good at guessing correctly — but still guessing.
- Mechanism sentence (the ML metaphor, relocated here from the old GIGO
  opener): a predictive model predicts on features; an LLM predicts on context.
  Flips the reader's mental picture to "predictive model that needs inputs."

## The memory analogy

- Weights are recall; context is the page open on the desk (recalling vs.
  reading).
- A memory can't be checked; a page can be re-read (verifiability).
- Keep it under three sentences — its power is inverse to its length.

## The misdiagnosis — the hook lands

- When the model guesses wrong, we call it a hallucination and blame the
  model's intelligence.
- Reframe: a hallucination is usually a forced guess — we gave the model
  nothing to read. The model was starved, not stupid.

## History — the oracle era

- 2022–23: no tools, no search. The model's value was the internet compressed
  into its weights.
- Prompt engineering emerged as the craft of extracting that encoded knowledge.

## Why the oracle model is a dead end

- Flaw 1: weights are an average of the public internet — extraction regresses
  to the generic.
- Flaw 2 (the clincher): your codebase, your company, yesterday's decisions
  were never in the weights. No prompt can extract what isn't there.
- Aim the criticism at model-as-oracle, not at prompting as a practice.

## The reframe — parallel definitions

- Context engineering: *what information* the model reasons over.
- Prompt engineering: *how the model is directed* to use it.
- Both essential, distinct jobs. State as a matched pair, same sentence shape.

## The landing — cash the title's check

- Context is data. An enterprise's knowledge lives in its data.
- Data demands engineering, governance, operationalization — the discipline
  organizations already built for tabular data (warehouse, lakehouse).
- No equivalent layer exists for agents: one they can agentically search and
  pull into context. Say this once, precisely — it's the seed sections 3 and 5
  harvest.

## Standing craft notes

- Voice: hold one voice throughout home.md (project voice vs. first person —
  don't mix).
- "Always guessing" replaces GIGO: GIGO is about *bad* input; the real claim is
  *absent* input.
- Keep "intelligence" clean as the reasoning faculty — knowledge is encoded in
  the *weights*, never "into intelligence," or the aphorism unravels.
- Seed the word "context" early; don't say "external information."
