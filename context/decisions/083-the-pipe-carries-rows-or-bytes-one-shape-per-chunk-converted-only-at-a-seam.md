# 083. The pipe carries rows or bytes, one shape per chunk, converted only at a seam by two laws, and errors never cross a byte seam

- **Status:** proposed 2026-10-15. Resolves the open question "Shell
  pipe payload: Result envelopes with a canonical wire serialization,
  or bytes at v1?" (2026-07-24). Feeds spec 167. Depends on ADR 082
  (the ABI's `consumes` and `produces`).
- **Date:** 2026-10-15
- **Amended 2026-10-15** after the pre-build review of spec 167 and Clay's answers: bash line semantics on a pipe, rows only by explicit form (pin 3); no added newline, raw single reads (pin 4).
- **Deciders:** Clay Gendron
- **Decided by:** AI-with-approval (the assistant drafted the laws
  from an executed reference over the live tree; Clay set the
  multimodal requirement that forces rows into the pipe)

## Context

The multimodal requirement decides this. A `read` of an image is a
row with `data` and `mime_type`. If the pipe carried text, the image
would die at the first `|`. So the unit of data in the shell is the
row, and the question is how bytes-shaped programs (`wc`, `sed`, a
wasm `jq`) and row-shaped programs (`ls`, `grep`, `glob`) share a
pipe.

The memo (§5, §11; studies `03-program-abi-and-bin-namespace.md` and
`10-wasm-program-spike.md`) found:

- nushell's `PipelineData` has four cases and its doc comment records
  two rejected designs (everything a stream; streams inside values).
  Across its plugin boundary each stream is one shape, with explicit
  acknowledgements as backpressure and a consumer-side close.
- elvish wires a byte band and a value band between every pair of
  forms; the July memo reproduced the cost: cross-band order is
  nondeterministic and a band mismatch deadlocks.
- PowerShell added byte-preserving native pipes eighteen years after
  shipping; nushell's human table renderer became its wire format to
  external programs and cannot be fixed.
- Both agent-shell leaders retrofitted bytes into their pipes after
  launch (just-bash 3.0, bashkit 0.16) and still carry no media type.
- A Python reference of the ABI and the two laws ran six pipelines over
  the live `InMemoryStorage`: `ls | wc -l` counted entries and `cat f
  | wc -l` counted lines with no special case; `glob | grep` handed
  rows as `observations=` and re-parsed no text; `ls /nope | wc -l`
  first printed 1 because the error line rendered into the pipe, and 0
  after the fix; a 10,000-row `ls | wc -l` ran in 10 chunks at a
  maximum queue depth of 2. The wasm spike moved bytes between three
  wasm stages with the row rendered once at entry and parsed back once
  at exit.

## Options considered

- **Both shapes, one per chunk, programs declare shapes, two laws at
  the seams (chosen).** Pros: what nushell landed; verb chains pass
  rows untouched; byte programs see bytes; media survives. Cons: two
  conversion laws to pin.
- **Rows only; every text program consumes a rendering.** Rejected: a
  wasm `jq` reading JSON would receive a Markdown table.
- **Bytes only at v1, structure later.** Rejected: `glob | grep` would
  re-parse paths from text, the one thing the envelope was built to
  avoid; and every peer that chose it retrofitted bytes later.
- **Two parallel bands (elvish).** Rejected: nondeterministic order and
  deadlocks, reproduced.
- **JSON lines as the default row-to-bytes form.** Rejected: 80% of
  the corpus is text filters that want text; JSON by default would
  print JSON to the agent whenever a verb feeds `head`.

## Decision

Ten pins.

1. **One ordered stream of chunks per pipe.** Each chunk is exactly
   `Rows` (a frozen `Result` slice: rows plus classified errors,
   op-tagged) or `Bytes` (a buffer with a mime). Never both. Values
   are never lazy; laziness lives only in the channel.
2. **Programs declare their shapes.** `consumes` and `produces` are
   each `rows` or `bytes`, and may depend on flags (`shapes(args)`:
   `grep -c` produces bytes, `grep` on stdin consumes bytes). Verb
   builtins produce rows (the
   `write` family also consumes bytes). Text kernels are bytes to
   bytes. Stored programs and guests are bytes to bytes, always. A
   runner builtin that runs another program (`xargs`) takes that
   program's produced shape.
3. **Same shape passes untouched, but a verb never consumes upstream
   rows silently.** `ls /src | grep auth` filters the rendered lines
   and prints `auth.py`, exactly as bash does (Clay, 2026-10-15): a
   verb builtin on a pipe consumes the plain rendering of the upstream
   rows as bytes. Rows reach a verb as `observations=` only through an
   explicit form: `xargs` (`find … | xargs grep x`, the Unix idiom for
   searching those files' contents) or a verb invoked with rows by
   name. Bytes to bytes is the filter chain: raw bytes, no decoding,
   bashkit's "bytes are canonical".
4. **Rows become bytes only for a byte-shaped consumer**, in this
   order: a single `read` row whose body is `data` crosses raw with
   its mime on the chunk, and a single text-bodied `read` row crosses
   as its body with no added newline (`cat a > b` is exact); otherwise
   the rows render through the plain pipe projection with the producing
   op's default arrangement (`ls` one path per line, `grep`
   `path:line:text`), never the display projection's cap or markers.
   Bytes-bodied rows cross as their raw bytes, in order, however many
   there are (`cat a.png b.png | wc -c` is the sum, `cat a.png > b.png`
   is exact, as Unix). The placeholder is a terminal render only and
   never enters a pipe.
5. **Errors never cross a byte seam.** The slice's errors go to the
   producing stage's stderr as rendered lines; only observations
   render into the pipe. A failed verb with zero rows yields zero
   bytes downstream and a non-zero status in the list.
6. **Bytes become rows only for a row-shaped consumer, including the
   terminal boundary**, as exactly one row minted at end of stream:
   valid UTF-8 without NUL is `content` with the producer's mime or
   `text/plain`; anything else is `data` with the sniffed mime, the
   producer's declared mime as fallback. The row's path is
   `/.vfs/run/<call-id>/stdout`, a derived address under the meta
   root, retained per authority in router memory beside a `status`
   record naming each program's path and `content_hash`; a tool or
   MCP call that yields several blocks yields one row per block at
   `/.vfs/run/<call-id>/<i>`. Exit code, status list and stderr ride as extras on the
   `Result`, the `grants=` precedent; the terminal is spec 167 §6's
   `cli` Result. The default projection for program output is
   `content` through `read`'s verbatim arrangement.
7. **The producer fetches what the consumer needs.** The shell knows
   both shapes before it runs the pipeline, so a `read` whose consumer
   is byte-shaped projects `data`; one whose consumer is row-shaped
   keeps the elide-by-default posture. Planning, not sniffing. At the
   terminal boundary, a last stage that is a single bytes read (`cat`
   or `read` with one operand) projects `data`, and the adapter's media
   budget decides what crosses the wire.
8. **JSON is explicit.** `to-json` emits `Result.to_payload()` as one
   `application/json` bytes chunk and `from-json` reverses it. A
   program may not declare a JSON shape at v1.
9. **Bounded queues.** A producer hands at most `ROWS_PER_CHUNK` rows
   or `BYTES_PER_CHUNK` bytes per chunk; each seam is a queue of
   declared depth; memory per seam is `depth × chunk`, independent of
   batch size. A row-shaped consumer that must see everything (`grep`
   scoping, a global sort, `tree`) materializes and its docstring says
   so. Performance pins count chunks, rows and verb calls, never
   seconds.
10. **Early close.** A consumer that stops early (`head -3`) closes its
    stdin; the producer is cancelled at its next emit and reports
    `vfs.cancelled` as info, not failure. `yes | head -1` succeeds.

## Consequences

- `ls | wc -l`, `cat f | wc -l`, `cat a.png > b.png`, `cat a.pdf |
  grep total` (which searches the rendering) and `glob | grep` are all
  correct with no special cases.
- The renderer is the wire's text projection by design, so the
  display-format-as-wire-format wart does not apply; it is canonical
  and ANSI-free.
- `_DEFAULT_PROJECTION["run"]` and the body arrangement for program
  output change (spec 167, task zero).
- A wasm stage is a rows-to-bytes-to-rows adapter with declared edges
  and never sees a `data` column through stdin; it gets bytes through
  a file open and the placeholder through the pipe.
- Large outputs are elided at the boundary under budget and kept at
  the `/.vfs/run` path for a later `read`; retention is ADR 085's.
