# vfs ground truth: the invariant set any content channel must respect

Subject: the internal constraint side of the multimodal-content brief
(`context/research/2026-07-25-multimodal-result-content-brief.md`). All
line cites are against the live tree at commit 276d096. This study is
adversarial by assignment: its job is to give the memo the exact laws a
content-channel design must not break, and to name which of the brief's
three candidate homes strains which law.

Corrections to the brief's own text, found while reading ground truth:

- **There is no `+` operator on `Result`.** The algebra is `|` (union),
  `&` (intersection), `-` (difference), plus the classmethod seams
  `Result.merge` (pure fold of `|`) and `Result.merge_branches`
  (zero-progress demotion) — `src/vfs/results/envelope.py:449-529`. Any
  "does `+` concatenate content in op order" question must be re-asked
  as "what does `|` do", and `|` already has pinned laws.
- **There is no MCP layer in `src/vfs` today.** `find src/vfs -iname
  '*mcp*'` returns nothing; `to_payload()` is documented as the future
  MCP `structured_content` half (`envelope.py:640-641`) and
  `render_result` as "CLI output or a top-level MCP tool"
  (`src/vfs/results/render.py:11-12`). The MCP content-array emitter is
  greenfield — there is no existing seam it can conflict with, only
  seams it must feed from.

---

## (a) The invariants, precisely, with cites

### A. Verdict and evidence

- **A1 — verdict derived, never stored.** `success` is a property (no
  fatal-severity errors), serialized outbound, stripped and re-derived
  inbound (`envelope.py:294-306, 312-315, 640-667, 696-703`). The 057
  corpus calls this the one unanimous finding across errno/9P/FUSE/LSP/
  SQLite/MCP (`context/research/2026-07-08-result-envelope.md:11-21`).
  Consequence for media: **any state where the envelope's evidence and
  what actually ships to the model can disagree is the same doctrine
  class** — e.g. a projection-time re-fetch that ships bytes of a
  different version than the row's `version` field attests.
- **A2 — truthiness is success, emptiness is separate**
  (`envelope.py:377-380`). A media channel must not perturb `__bool__`.

### B. Rows

- **B1 — rows are frozen `Observation`s keyed by `path`**; null means
  "not populated by this call," never "absent on the entry"; the
  `populated` mask is the presence authority
  (`src/vfs/models/entry.py:356-434`).
- **B2 — `Observation` is frozen but NOT open.** `model_config =
  ConfigDict(frozen=True)` with default `extra` (`entry.py:382`) — only
  `Result` and `ResultError` are `extra='allow'` (`envelope.py:107,
  288`). A novel row field from a newer peer is silently stripped at
  `from_payload`'s per-item `Observation.model_validate`. Adding a media
  field to `Observation` is therefore a schema change old clients drop,
  not one that rides through.
- **B3 — content is `str`, text-only, null-byte-free.** `Entry.content:
  str | None` with a null-byte rejection validator (`entry.py:132-139`),
  metrics computed via UTF-8 encode (`entry.py:118-127`);
  `Observation.content: str | None` (`entry.py:388`). **There is no
  binary channel anywhere in the live tree.** A PNG cannot currently be
  stored, read, or observed — the brief's "read of a PNG" presupposes a
  storage-side bytes story that does not yet exist. `mime_type` does
  already exist as an Entry field and Observation mirror
  (`entry.py:88, 390`), and `CONTENT_KINDS` already gates which kinds
  carry content at all (`entry.py:42-43`).
- **B4 — `Match` is the precedent for sub-row structure**: frozen
  regions with `start`/`end` line bounds, own `content`, own `score`,
  anchored inside one row (`entry.py:335-353`). This is the existing
  shape for "a thing positioned within a document."

### C. Algebra (pinned by `tests/test_result_laws.py:58-133`)

- **C1 — `|` is a pure fold**: associative (L1), idempotent over
  path-distinct rows with `Result()` as identity (L2), `success` a
  homomorphism (L3) (`tests/test_result_laws.py:59-82`;
  `envelope.py:272-276`).
- **C2 — row merge is left-wins-by-mask**: right fills only fields
  absent from the left's mask; masks union; filled lists copied;
  `version` is agree-or-null — associative, commutative, idempotent
  (`envelope.py:398-427`). Any new row field automatically inherits this
  merge for free; any *non-row* channel must invent its own merge and
  prove these three properties.
- **C3 — errors dedup by value equality; provenance makes that lawful.**
  Frozen field equality is the dedup key; two mounts failing identically
  stay two facts because `source` differs (`envelope.py:96-101,
  429-443`; diamond-dedup-survives-the-wire pinned at
  `tests/test_result_laws.py:112-134`). A content channel with no
  identity story breaks the diamond: `(a | b) & b` must not double its
  blocks.
- **C4 — `-` consumes only the right side's paths; right errors do not
  propagate** (`envelope.py:471-483`).
- **C5 — policy lives outside the algebra.** `merge` is the plain fold;
  demotion happens only in `merge_branches` under the zero-progress rule
  (`envelope.py:489-529`).
- **C6 — enrichment preserves the envelope.** `sort`/`top`/`filter`/
  `kinds` rebuild via `_with_observations(ops, observations, errors)`
  (`envelope.py:535-575`).
- **C7 — HAZARD: every algebra/enrichment/rebase operation reconstructs
  `Result` field-by-field.** Nine construction sites — `__and__`
  (:453), `__or__` (:465), `__sub__` (:479), `merge` (:504),
  `_demoted` (:529), `_with_observations` (:537), `with_mount` (:602,
  :620), `without_mount` (:630), and the rollup copy in `to_payload`
  (:660) — name `ops`/`observations`/`errors` explicitly. **A new
  declared field silently vanishes at every one of these unless
  threaded through all nine**, and — verified consequence — even
  today's `extra='allow'` fields survive a serialize/deserialize hop
  but are dropped by the first algebra operation on the receiving side.
  "Open model" is a pass-through guarantee, not a merge guarantee.

### D. Rebase

- **D1 — rebase distributes over merge** (L4,
  `tests/test_result_laws.py:83-102`), including overflow rows.
- **D2 — rebase touches `path`/`source`/`data`, never `message`**
  (`envelope.py:97-99`; 9P werrstr scar,
  `2026-07-08-result-envelope.md:62-63`). The brief's instinct that
  blocks are "closer to message" implies rebase-is-identity for
  path-free blocks — but a `resource_link`-style block *carrying a vfs
  path* would be on the `path` side of this line and MUST rebase, or a
  mounted hop ships dangling links.
- **D3 — rebase is total and pure, never raises**: overflow rows drop
  to a `vfs.unaddressable` *warning* with append-once
  `data["vfs.overflow"]`; the original result is untouched
  (`envelope.py:581-620, 154-189`; `without_mount` inverts,
  `envelope.py:191-205, 622-634`).

### E. Wire round-trip

- **E1 — one serializer.** `to_payload` via `model_dump_json`, strict
  JSON-safe, always agreeing with `to_json` (`envelope.py:640-667`;
  057 defense "one serializer / payload display-free,"
  `2026-07-08-result-envelope.md:239`). Binary media therefore crosses
  the structured wire only as a JSON-representable encoding (base64
  string) or not at all.
- **E2 — `from_payload` is lenient, per-item, never raises.** Malformed
  rows/errors quarantine individually (`envelope.py:669-710, 758-779`).
  **Only `observations` and `errors` get per-item treatment**
  (`_validated_items` pops exactly those two, `envelope.py:763-764`); a
  new item list that skips this discipline hits the envelope-level
  `model_validate` at `envelope.py:705`, and one malformed block would
  quarantine the *entire* list as an envelope-field warning
  (`envelope.py:707`) — sibling blocks not salvaged. Any block channel
  must be added to `_validated_items`.
- **E3 — quarantine is bounded at 512 bytes serialized**
  (`_QUARANTINE_CLIP`, `envelope.py:799-831`). A malformed
  multi-megabyte base64 block is clipped to junk on quarantine — media
  loss must be *recorded* (loss-on-record warning), never preserved
  wholesale.
- **E4 — budgets cap the boundary, never the algebra.** `max_errors`
  rollup: group by `(kind, severity, retryable)`, ship head + rollup
  entry with machine-readable `{count, sources}`, severity preserved so
  the verdict is invariant under rollup; in-process nothing is dropped
  (`envelope.py:651-667, 732-756`; agent-CLI lesson "truncation is a
  continuation protocol," `2026-07-08-result-envelope.md:182-184`).
  **This is the mandatory template for media budgets**: elide at
  `to_payload` with a placeholder carrying count/size/address, never
  prune in-process, verdict invariant.
- **E5 — non-finite floats serialize null** (`envelope.py:647-650`) — a
  reminder that the payload is *strict* JSON; no NaN, no bytes.

### F. Errors

- **F1 — kind mandatory, message never load-bearing, machine detail in
  `data` with `vfs.` prefix reserved for envelope machinery**
  (`envelope.py:97-99`; `src/vfs/results/kinds.py:44-50`).
- **F2 — optional dual channels rot.** 9P2000.u's optional errno beside
  the string rotted to a zeroed field
  (`2026-07-08-result-envelope.md:55-63`): "new fields must be
  defaulted-by-construction or derived, never optional-and-parallel."
  This kills any design where a block carries an *optional* text
  alternative, or where media lives in an optional field *duplicating*
  `content` — the parallel channel will be unfilled by real producers
  within a release.
- **F3 — unknown severity reads as error; unknown kinds degrade by
  longest prefix** (`kinds.py:98-113, VFSErrorKind` docstring
  `kinds.py:27-40`). An unknown *block type* from a newer peer needs the
  same doctrine: preserved raw, degraded to a declared fallback (the
  text placeholder), never dropped, never guessed.

### G. Rendering and projection

- **G1 — text is rendered once, at the final human/agent boundary;
  inter-mount hops are structured payload only** (`envelope.py:28-30`;
  `render.py:10-13`).
- **G2 — rendering is pure, no I/O** (`render.py:8-9`). A projection
  layer that *fetches* media bytes cannot live inside `render_result` or
  any peer of it without repealing this.
- **G3 — the renderer defends the text channel's structural integrity
  at the chokepoint**: error lines have one-line-ness *enforced*
  (peer newlines collapsed so an entry cannot forge a sibling line,
  `render.py:91-107`), table cells are pipe-escaped and
  newline-stripped (`render.py:253-255`). The brief's stdout rule
  ("never emit base64 into a text stream") has its enforcement
  precedent here: a chokepoint rule, not producer discipline.
- **G4 — projection does double duty**: the same field-name tuple picks
  render columns and narrows the SQL SELECT (`projection.py:1-16`);
  `populated` is never projectable (`projection.py:29-30`); `read`
  defaults to `("content",)` and `run` to `("path",)`
  (`projection.py:45-57`). A media-bytes field on `Observation` slots
  into this machinery for free — including the *elide-by-default*
  posture: unprojected means never fetched from storage.
- **G5 — several arrangements sort rows by path at render time**
  (e.g. `_render_read`, `render.py:296`; `_render_path_list`,
  `render.py:214`) — producer emission order is already not preserved
  by the text surface. Ordering-as-meaning does not currently exist at
  row granularity.
- **G6 — cross-op merges (`op=None`) must still render** via the
  generic fallback (`envelope.py:317-323`; `render.py:162-180`,
  `projection.py:73-82`). A block channel must define what a merged,
  cross-op content sequence renders as, on both surfaces.

### H. Two-consumer physics (hermetic memo) and scale

- **H1 — values cheap and immutable; laziness only in the pipeline
  channel, never inside a value** (nushell's rejected "streams inside
  Value,"
  `context/research/2026-07-24-hermetic-runtime-and-wasm-cli.md:82-91`).
  An envelope may hold materialized bytes or *reference* a stream; the
  value type itself is never lazy.
- **H2 — the structured→bytes wire format is a decision, not a
  default** (nushell's display-format-as-wire-format wart, memo
  :105-113). The text placeholder for a media block must be one
  declared canonical form, decided before ship.
- **H3 — the renderer is a single overridable chokepoint** (memo
  :115-119) — matches `render_result` staying the only text door.
- **H4 — per-row failures ride in-stream, fatal only on collect** (memo
  :121-129) — undecodable media on one row must not fail a batch.
- **H5 — executed programs bridge as one record `{stdout, stderr,
  exit_code}`** (memo :138-140), and wasm output files land back in vfs
  by write-back at `fd_close` (memo §4.3). Program-produced media
  therefore *naturally becomes vfs entries*, which the `run` result can
  then reference by path — the executed-code question reduces to the
  same reference-vs-inline choice as `read`.
- **H6 — 10,000+-row batches are a supported contract** (CLAUDE.md,
  production posture). Per-row inline base64 at 10k rows is an
  unbounded payload; whatever the design, media inlining needs a
  boundary budget (E4) and a reference form.

---

## (b) The three candidate homes vs the invariants

### Candidate A — `content: list[ContentBlock]` on `Result`

What it strains:

1. **C7 (lethal today, fixable with discipline)**: nine construction
   sites must thread the new field or it silently vanishes on the first
   `|`, `.top()`, or `with_mount`. Every future construction site is a
   standing silent-loss bug.
2. **C1/C3 (the algebra kill-zone)**: an *ordered* list has no path key
   and no natural idempotence. `r | r` duplicates blocks unless they
   dedup by value — but blocks are narrative, where a repeated block
   can be meaningful and where value-dedup of an interleaved sequence
   silently rewrites the story. The diamond `(a | b) & b` double-counts.
   To keep L1/L2 you must either (i) give blocks value identity +
   dedup (collapsing legitimate repeats — the errseq over-collapse
   lesson, `2026-07-08-result-envelope.md:230-232`), or (ii) declare
   blocks *outside* the algebra like `success` — but they are data, not
   a derived verdict, so "outside the algebra" means "lost or
   arbitrarily concatenated on merge," and associativity of
   concatenation holds but idempotence does not. No option preserves
   all of L1/L2/L5 for free.
3. **D2/D3**: blocks that reference paths must rebase (new seam in
   `with_mount`, plus an overflow story); blocks that don't must be
   untouched. A mixed list forces per-block-type rebase dispatch.
4. **E2**: `_validated_items` must learn the list or one malformed
   block quarantines the whole channel.
5. **E4/H6**: a base64-bearing list makes `to_payload` unbounded; needs
   its own max/placeholder/rollup regime.
6. **F2**: if blocks duplicate row data (a read emitting both an
   `observations` row and a text block of the same content), that is an
   optional parallel channel — the exact 9P2000.u rot pattern.

What it satisfies: ordering/interleaving (the brief's Q4) natively —
this is the only home where "text, image, text" is a first-class
sequence. That is its sole structural advantage, and everything else
fights the envelope.

### Candidate B — media as a species of / field on `Observation` rows

What it satisfies:

1. **C1/C2/C3 for free**: a media field (`data`-b64 + existing
   `mime_type`) is just another masked mirror; left-wins-by-mask,
   masks-union, and path-keyed dedup apply unchanged; the law tests
   need no new laws.
2. **D1/D3 for free**: rows already rebase and already have the
   overflow discipline (`envelope.py:588-620`).
3. **E2/E3 for free**: rows already validate per item and quarantine
   clipped.
4. **G4 alignment**: a media field is projectable, SQL-narrowing, and
   elide-by-default (unprojected = unfetched) — the budget posture (E4,
   brief Q5) falls out of existing machinery; the boundary placeholder
   is just the text render of a row whose mask says the bytes field was
   not fetched, with `path`/`mime_type`/`size_bytes` already present as
   fields.
5. **A1**: the bytes ship inside the same envelope as the version that
   attests them — no evidence/emission divergence.

What it strains:

6. **B2**: `Observation` is not open — old clients strip the new field
   at `from_payload`. Acceptable (degrades to today's behavior) but must
   be a conscious compat call.
7. **B3**: requires the real work first — a binary content story in
   storage and models. `content: str` + null-byte rejection means this
   is a storage/model design, not an envelope patch.
8. **Ordering/interleaving (brief Q4) — the honest weakness**: rows are
   a path-keyed set; renderers even re-sort by path (G5). One row =
   one media object works perfectly (`read /charts/q3.png`); a document
   whose figures interleave with its text does not fit row granularity.
   The existing seam for sub-row placement is `Match` (B4): an anchored
   media region (`start`/`end` + payload/reference) inside a row is the
   shape that preserves in-document order without a new top-level
   channel. The MCP projector can then emit an ordered block array *per
   row* mechanically (text-before-anchor, image, text-after).
9. **C2 subtlety**: two observations of the same path from different
   snapshots merging left-wins could pair left's media bytes with
   right's metadata; the `version` agree-or-null rule (envelope.py:
   422-426) already stamps the composite as no-single-snapshot, which
   covers the honesty requirement — but the memo should note media
   fields are version-coupled evidence like `content` already is.

### Candidate C — projection-time only (rows stay bytes-agnostic; the MCP renderer fetches)

What it satisfies: every envelope law trivially — algebra, rebase,
round-trip, budgets are untouched because nothing is added.

What it strains:

1. **G2**: the render/projection layer is pure by doctrine; a fetching
   projector is a new I/O-performing boundary component, not a renderer.
   Placeable (the greenfield MCP adapter sits above render), but it
   repeals "the payload is the whole result."
2. **A1 (the doctrinal kill-shot)**: fetch-at-projection re-reads the
   path *after* the operation; the row attests version N, the wire ships
   bytes of version N+1 (or a 404 for a path that existed at op time).
   The envelope exists to make evidence/verdict divergence
   unrepresentable — this re-opens the same class between evidence and
   emitted content. Mitigable only with version-pinned reads
   (storage-side capability) — at which point the fetch is a formality
   and inlining-at-op-time was simpler.
3. **G1**: between mounts only the structured payload travels. If media
   is not in the payload, only a hop that still holds backend access can
   emit it; a downstream consumer of a forwarded payload cannot. The
   final-boundary MCP server *does* hold access, so single-hop works —
   but the design quietly makes media a final-hop-only privilege, unlike
   every other fact on the envelope.
4. **H5 interplay (partial rescue)**: for executed code, output files
   land in vfs by write-back, so reference-then-fetch has something to
   fetch. Ephemeral non-file output (raw stdout bytes from a wasm CLI)
   still needs an op-time capture.

### First-pass verdict for the memo

No candidate survives alone. The invariant set points at a hybrid: **B
as the carrier** (media is evidence about a path, row-keyed, masked,
budgeted and elided by projection — with `Match`-style anchors for
in-document placement), **C's reference form as the budget posture**
(placeholder + fetch-on-request is `read` with the media field
projected — an existing verb, not a new mechanism), and **A rejected as
a stored channel** but resurrected *as the MCP projector's output type*:
the ordered block array is a *rendering* of rows (deterministic,
per-arrangement, like `render_result`), never stored state. That keeps
ordering a boundary concern (G5 already establishes arrangement-time
ordering) and keeps the algebra clean.

---

## (c) Existing seams where a content channel attaches

| Seam | Where | What attaches |
|---|---|---|
| One serializer | `envelope.py:640` `to_payload` | media budget/elision regime, mirroring `max_errors` (:651-667) |
| Inbound leniency | `envelope.py:758` `_validated_items` | per-item quarantine for any new item list (currently observations+errors only) |
| Rollup template | `envelope.py:732` `_rolled_errors` | the group/head/count pattern media placeholders must copy |
| Text chokepoint | `render.py:33` `render_result`; `render.py:183` `_format_field`; `render.py:287` `_render_read` | the canonical placeholder form (stdout rule, brief Q6); read is where binary would today dump into `content` verbatim |
| Structural defense precedent | `render.py:91-107, 253-255` | enforcement style for "no base64 in text": chokepoint, not discipline |
| Projection vocabulary | `projection.py:30, 45-57` | a media field becomes projectable + SQL-narrowing + default-elided |
| Sub-row anchoring | `entry.py:335` `Match` | the existing shape for ordered in-document regions |
| Mime + kind gates | `entry.py:88, 390` `mime_type`; `entry.py:42` `CONTENT_KINDS` | classification fields already exist; brief Q7's mime reality check lands here |
| Row rebase + overflow | `envelope.py:581-620`; `entry.py:440-457` | free rebase for row-borne media; the pattern path-bearing blocks would have to replicate |
| Run verb | `src/vfs/ops.py:73` `EXEC_OPS`; memo §4.3 write-back | executed-code media becomes vfs entries; `run`'s result references them by path (brief Q8) |
| MCP adapter | **does not exist in `src/vfs`** | greenfield; must be the *only* place ordered block arrays are minted, sibling to (not inside) the pure renderer |

## Mapping to the brief's numbered questions

1. **Where blocks live (Q1)**: candidate analysis above; the invariants
   favor row-borne media + projection-minted block arrays; a stored
   `list[ContentBlock]` on `Result` fails C1/C3/C7 without new laws.
2. **Vocabulary (Q2)**: F3 requires unknown-block-type doctrine
   (preserve raw, degrade to text placeholder) whichever taxonomy is
   chosen; E1 requires every block be strict-JSON.
3. **Algebra (Q3)**: C1-C7 are the exact laws; "what keys a block" has
   only one existing lawful answer — the row's path (plus Match-style
   anchor for sub-row order); rebase must touch path-bearing blocks
   (D2) contra the brief's "blocks are closer to message" instinct.
4. **Ordering (Q4)**: G5 shows row order is already a render-time
   arrangement decision; interleaving belongs to the boundary
   projection, anchored by Match-style regions, not to stored state.
5. **Budgets (Q5)**: E4 is the mandatory template (boundary-only,
   count-on-record, verdict-invariant); G4 gives elide-by-default for
   free if media is a projectable row field.
6. **Stdout rule (Q6)**: G3 is the enforcement precedent; H2 says the
   placeholder form is a pre-ship decision, one canonical rendering.
7. **Mime reality (Q7)**: `mime_type` already exists on Entry and
   Observation; classification-at-seam belongs to the greenfield MCP
   adapter, with F3-style degrade for unknown types.
8. **Executed code (Q8)**: H5 — write-back makes program media into
   entries; `run` references by path; ephemeral stdout bytes need an
   op-time capture rule (the `{stdout, stderr, exit_code}` record).

## Bearing on the "break from Unix" stance

Ground truth already broke from Unix where it matters: pipes between
vfs operations carry `Result` envelopes (structured values), text is
rendered exactly once at the final boundary (G1), and the renderer —
not the producer — owns the text form (G3, H3). The stance's remaining
claim (typed content blocks as the inter-tool medium) is *consistent*
with the invariants only if blocks are a boundary projection of
row-shaped evidence, not a stored parallel channel: the algebra has no
lawful home for an ordered, unkeyed block list (C1/C3/C7), and the
optional-dual-channel doctrine (F2) forbids blocks that shadow row
content. The multimodal CLI the brief wants is achievable as: media as
masked, path-keyed, version-attested row evidence; one canonical
placeholder in text; and a greenfield MCP adapter that deterministically
unrolls rows (with anchors) into MCP's ordered content array.
