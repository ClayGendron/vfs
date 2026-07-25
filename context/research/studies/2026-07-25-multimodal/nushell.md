# nushell deep-dive: ByteStream, content_type, and the boundary that renders

Subject: how nushell carries bytes-as-bytes through a structured pipeline, how it
tracks media type, where "text vs binary" gets decided, and what its own MCP
server (nu-mcp, in-tree) does at the model boundary. Repo studied at commit
3f21256 (2026-07-24). This goes deeper than the hermetic-runtime memo's nushell
section (2026-07-24-hermetic-runtime-and-wasm-cli.md §2) and does not repeat it;
the four-variant `PipelineData`, the rejected designs, the external-pipe wire
wart, and the two error channels are covered there.

## 1. What it is: the data model for bytes

`PipelineData` has exactly one case for raw bytes — `ByteStream` — alongside
`Empty`, `Value`, `ListStream` (nu-protocol/src/pipeline/pipeline_data.rs:48-54).
A `ByteStream` is a lazy reader (`Read`, `File`, or child process) tagged with a
three-way **type color**:

```rust
pub enum ByteStreamType { Binary, String, #[default] Unknown }
```
(nu-protocol/src/pipeline/byte_stream.rs:100-114)

The semantics are coercion permissions, not classifications:
- `Binary` "should only be converted to binary, even when the desired type is
  unknown" — `into_string()` on a Binary-typed stream **fails even if the bytes
  are valid UTF-8** (byte_stream.rs:101-103, 649-668).
- `String` promises conventional (not guaranteed) UTF-8; conversion still
  validates (byte_stream.rs:104-109).
- `Unknown` "is used only for external sources where the type can not be
  inherently determined, and having it automatically act as a string or binary
  depending on whether it parses as UTF-8 or not is desirable"
  (byte_stream.rs:160-164). `into_value()` on Unknown: UTF-8 → `Value::String`
  (with trailing-newline trim for external sources), else `Value::Binary`
  (byte_stream.rs:682-700).

Sources set the color at birth: `read_string` → String, `read_binary` → Binary
(byte_stream.rs:320-337); files and child processes and stdin → Unknown
(byte_stream.rs:343-385). Type-cast commands **retype the stream without
collecting it**: `into binary` is `stream.with_type(ByteStreamType::Binary)`
(nu-command/src/conversions/into/binary.rs:165), `into string` likewise
(into/string.rs:180) — a zero-copy relabel, laziness preserved.

The color feeds the static type system: Binary→`Type::Binary`,
String→`Type::String`, Unknown→`Type::Any` (byte_stream.rs:138-146), so parse-
time pipe checking works on byte streams too, degraded gracefully for Unknown.

Crucially, **`Value::Binary` is a bare `Vec<u8>`** (nu-protocol/src/value/
mod.rs:192) — no mime, no filename, no provenance on the value itself. All of
that lives in a sidecar (next section), which turns out to be the story's
central flaw.

## 2. content_type: mime as pipeline metadata, not value data

`PipelineMetadata` rides beside the data in every `PipelineData` variant:

```rust
pub struct PipelineMetadata {
    pub data_source: DataSource,        // e.g. FilePath(PathBuf)
    pub path_columns: Vec<String>,
    pub content_type: Option<String>,   // a mime string
    pub custom: Record,                 // namespaced free-form ("http_response", ...)
}
```
(nu-protocol/src/pipeline/metadata.rs:21-28)

**Producers.**
- `open` without a matching `from <ext>` converter stamps `content_type`
  guessed from the extension (nu-command/src/filesystem/open.rs:249-261), via a
  curated override table + `mime_guess` (open.rs:348-361). If a converter *is*
  found, the parsed structured output carries no content_type — structure
  replaces mime.
- `http get` lowercases the response `content-type` header into metadata
  (nu-command/src/network/http/client.rs:316-325) and *separately* maps it to a
  stream color: `application/octet-stream` → Binary, `charset=utf-8` → String,
  everything else → Unknown (client.rs:317-321). Note the two channels are
  deliberately decoupled: the mime is precise metadata; the color is a coarse
  text/binary judgment used only for coercion and display.
- Serializers stamp what they produced: `to json` sets `application/json`
  (nu-command/src/formats/to/json.rs:78), `to text` sets `text/plain`
  (to/text.rs:236-238), similarly `to csv`, `to xml`, `to msgpack`, etc.

**Consumers** (the part that makes it real, not decorative): `http post/put/
patch/delete` use the *pipeline's* content_type as the outgoing `Content-Type`
header when the user didn't pass one (http/post.rs:210, patch.rs:186,
put.rs:199, delete.rs:193). So `open photo.png | http post $url` sends
`image/png` automatically. Users can read and write it: `metadata`,
`metadata set --content-type` (nu-command/src/debug/metadata_set.rs:65-127).

**Invalidators — the discipline that makes mime honest.** A mime string is a
claim about the *serialized whole*, so commands that transform the bytes must
clear it: `from json` clears content_type once bytes become structure
(from/json.rs:81); `first`/`last`/`skip`/`take`/`bytes at`/`str substring` all
clear it on slicing, with the inline rationale "A slice (or single byte as int)
is not the whole file/stream; drop MIME" (nu-command/src/filters/
first.rs:200-202, plus last.rs, skip_.rs, take_.rs, bytes/at.rs,
str_/substring.rs). This is maintained **by convention, per command** — dozens
of files each independently remember to clear or preserve. It works only
because slicing commands are few; it is exactly the "optional dual channels
rot" failure mode the 057 corpus warns about, held at bay by manual diligence.

**Where the sidecar dies.** Metadata is attached to the *pipeline*, and a
`Value` has no metadata slot. Storing a result in a variable collects the
pipeline to a `Value` and keeps only the value (`StoreVariable`,
nu-engine/src/eval_ir.rs:508-517); the collect helper explicitly transforms
metadata via `for_collect()` (eval_ir.rs:1792-1810), which drops `FilePath`
data sources as "no longer meaningful" (metadata.rs:87-121) — but even the
surviving fields never make it into the variable. So:

```nu
let img = (open photo.png)   # mime is gone
$img | http post $url        # no Content-Type inference anymore
```

The mime survives exactly as long as the value stays inside one unbroken pipe.
This is the single strongest lesson for vfs: **a media type carried as sidecar
metadata, separate from the value it describes, evaporates at every
materialization boundary.** MCP content blocks put `mimeType` *inside* the
block for the same reason.

## 3. Boundary rendering: the renderer is the last command standing

Rendering happens once, at the terminal, through an overridable hook. A
completed REPL pipeline goes through `print_pipeline` (nu-cli/src/
util.rs:208-236): if `display_output` is configured — default hook is the
string `"if (term size).columns >= 100 { table -e } else { table }"`
(nu-protocol/src/config/hooks.rs:21-24) — the hook is evaluated with the
pipeline as input and the *result* is printed raw. No hook → `print_table`,
which invokes the ordinary `table` command (pipeline_data.rs:727-756). So the
projection-to-human is (a) a normal command, (b) user-replaceable, (c) run
exactly once, at the end. Mid-pipeline data is never rendered.

**The binary-on-screen rule** is two-tiered, keyed off the type color:
- Streams *declared* Binary never hit the screen raw: `print_table` routes them
  through `table` (pipeline_data.rs:734-737), and `table` wraps them in a
  streaming pretty-hex dump — `pretty_hex_stream` re-wraps the ByteStream so
  even the hexdump is lazy and interruptible (nu-command/src/viewers/
  table.rs:449-462, 501-560). Same for `Value::Binary` (table.rs:455-462).
- Streams typed String or **Unknown pass through raw** (table.rs:454,
  byte-stream print at pipeline_data.rs:735-737): external command output
  behaves exactly like classic Unix `cat`. So `open --raw mystery.bin` can
  still garbage a terminal; the hexdump guard protects only *declared* binary.
  nushell chose Unix-compatibility for unknowns over safety — the price of
  making externals feel native.
- `print_raw` exists as the deliberate escape hatch that skips the hexdump
  (pipeline_data.rs:758-794).

**Sinks never materialize.** `save` pattern-matches `ByteStream` first and
copies reader→file in chunks with signal checks, including the child-process
case (nu-command/src/filesystem/save.rs:87-105, 511-590). If a `to <ext>`
conversion produced a ByteStream, that too streams straight to disk
(save.rs:162-165). `save` chooses its serializer from the *destination file
extension*, not from content_type — mime metadata is advisory, never load-
bearing for dispatch. Externals get the same treatment: bytes from a
ByteStream are handed to the child's stdin without table-rendering; only
structured values suffer the table-format wire wart (nu-command/src/system/
run_external.rs:484-520, covered in the hermetic memo).

## 4. nu-mcp: what nushell actually does at the model boundary — and what it proves

nushell ships an in-tree MCP server (`nu --mcp`, crates/nu-mcp) exposing a
persistent REPL as an `evaluate` tool. This is the exact seam the vfs brief is
about, built by the closest prior-art team — and its choices are damning
evidence *for* the brief's stance:

- **Every result is a single text block.** The tool result is
  `CallToolResult::success(vec![ContentBlock::text(text)])` plus a JSON
  `structured_content` mirror (nu-mcp/src/evaluation.rs:497-502) — despite
  rmcp's `ContentBlock` supporting image/audio/resource blocks. The typed
  pipeline collapses to NUON text at the wire.
- **Binary output is destroyed, silently.** A ByteStream result is collected
  and passed through `String::from_utf8_lossy` — both the child-process path
  and the file/reader path (evaluation.rs:745-786). Run `open photo.png`
  through nu-mcp and the model receives U+FFFD confetti; the mime metadata that
  survived the whole pipeline is discarded unread at the boundary. There is no
  placeholder, no hexdump, no image block. The one place with a first-class
  bytes channel and a mime channel *and* an MCP SDK with image blocks still
  shipped text-only — multimodal output does not fall out of good pipeline
  design; it must be an explicit boundary contract.
- **Budgets, though, they got right.** Output over a limit (default 10KB,
  `NU_MCP_OUTPUT_LIMIT`, evaluation.rs:18-19) is replaced by a note — "output
  truncated, full result in $history.3" — while the *full* value is stored in a
  server-side ring-buffer history the model can query incrementally
  (evaluation.rs:661-675, history.rs). Elide-with-handle, content-on-request:
  precisely the brief's §5 posture, already proven ergonomic in production
  (they even tuned the job-promotion timeout because "Claude Opus 4.7 gave up
  on nushell" at 10s — evaluation.rs:184-188).
- **The protocol channel must own stdout.** Under `--mcp`, `print` is forced to
  stderr (nu-cli/src/commands/print.rs:62), externals get `Stdio::null()` stdin
  and no terminal inheritance (run_external.rs:258-266), and ANSI is globally
  disabled because "MCP is a computer-to-computer protocol"
  (evaluation.rs:272-275). Errors are shipped as structured NUON records with
  code/severity/labels/line/column, mirrored into JSON (evaluation.rs:37-123).

## 5. Lessons for vfs, numbered against the brief

**Q1 (where blocks live).** nushell's answer — media identity in sidecar
metadata, bytes in a parallel channel — demonstrably fails at materialization
boundaries: content_type dies on variable store (eval_ir.rs:508-517) and must
be hand-cleared by every transforming command (first.rs:200-202 et al.). The
inverse design holds up: the *coercion color* that lives ON the ByteStream
itself (byte_stream.rs:195) survives everything. Put mime/media-kind on the
value (the block/observation), never in envelope-level metadata; reserve
envelope metadata for provenance that legitimately dies at boundaries (their
`for_collect()` shows such a lifecycle rule is needed either way,
metadata.rs:87-121).

**Q2 (block vocabulary).** nushell needs only a three-way *permission* type
(Binary/String/Unknown) for pipeline semantics, and keeps the precise mime as
a separate, finer-grained string. Two-level typing transfers: a coarse tag
that drives algebra/projection decisions (text vs media), plus `mimeType` data
inside the block. Their curated-overrides-then-mime_guess extension map
(open.rs:348-361) is the pragmatic classifier shape.

**Q3 (algebra).** The slicing rule generalizes: any operation that does not
preserve the byte-identity of a media payload must drop or regenerate its
mime claim. For vfs, merge should treat blocks as opaque and immutable —
nushell never edits bytes under a mime, it either passes whole or clears the
claim. Their per-command manual clearing is the anti-pattern; make invalidation
structural (blocks immutable, keyed, whole) rather than conventional.

**Q4 (ordering).** nushell's pipe is single-typed (one stream at a time), so it
has no interleaving story — and its MCP server consequently emits exactly one
text block. No prior art here beyond a warning: a model that can't represent
text-media interleaving mid-pipeline can't produce it at the wire.

**Q5 (budgets).** Adopt nu-mcp's pattern wholesale: byte limit, placeholder
note carrying a stable handle (`$history.N` ≈ a vfs path/id), full content
retained server-side and fetchable in a later call (evaluation.rs:661-675).
Also their lesson that budget parameters need user/model control via
environment (`NU_MCP_OUTPUT_LIMIT`, `NU_MCP_PROMOTE_AFTER`).

**Q6 (stdout rule).** nushell's terminal rule is precedent: declared-binary
never renders raw; the deterministic text projection of binary is a bounded
hexdump produced lazily at the boundary by the ordinary renderer
(table.rs:449-462, 501-560), and the renderer is one overridable chokepoint
(util.rs:208-236) — maps to render.py staying the single text projection.
But their Unknown-passes-raw compromise (fine for a human terminal) is wrong
for an LLM boundary: nu-mcp's from_utf8_lossy mangling is that compromise's
downstream cost. vfs's stdout projection should have no Unknown: classify at
the boundary and emit placeholder for anything non-text.

**Q7 (mime reality).** The wild is dirty: their HTTP path parses mime
defensively (strip quotes, fall back to text/plain — client.rs:994-999) and
maps mime→behavior through a tiny table plus a subtype→`from <ext>` converter
lookup with `x-` stripping (client.rs:1001-1038). Precedent for vfs: carry the
raw mime string intact, but make behavioral decisions off a small normalized
core, and let unrecognized types pass through as data (their `None` converter
case just returns the bytes, client.rs:1033-1035).

**Q8 (executed-code output).** nushell externals produce Unknown byte streams
sniffed at collection (UTF-8 → string, else binary — byte_stream.rs:682-700),
and nu-mcp shows what happens if the boundary doesn't then type the result:
lossy text. So yes — typing executed-program output is the boundary verb's
projection duty; it cannot be inferred reliably upstream (`Unknown` exists
precisely because origin can't know), and the sniff-at-collect fallback is
acceptable only if the media path (declared types, mime) is the primary
channel. Their `is_mcp` plumbing (print→stderr, stdin→null) also shows the
runtime must know it is serving a protocol, not a terminal.

**On the brief's break-from-Unix stance overall.** nushell is the strongest
half-measure on record: typed pipes internally, Unix bytes at every edge
(externals get table-rendered text or raw bytes; unknowns print like cat; MCP
gets lossy text). Every place it kept Unix stdout semantics at a boundary is
now a documented wart (run_external wire format, Unknown-raw terminal risk,
nu-mcp binary mangling); every place it broke from Unix (typed streams,
boundary-only rendering, hexdump for declared binary, streaming save) is the
part that works. The evidence supports the owner's hypothesis — with the
refinement that the break must extend *all the way to the wire*: nushell broke
from Unix in the middle and kept it at the edges, which is exactly backwards
for an LLM consumer. And the "still feels like a CLI" goal is achieved in
nushell by making the renderer an ordinary command applied implicitly at the
end — ceremony-free text by default, structure underneath.
