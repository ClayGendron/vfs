# The structured-shell lineage: murex, elvish, TermKit

Study for the multimodal Result content brief
(`context/research/2026-07-25-multimodal-result-content-brief.md`).
Three independent answers to "what replaces raw text in the pipe":

- **murex** — bytes stay bytes; every stream carries a mime-derived *type
  tag*; builtins re-marshal per type. (GPL — study only. The sibling
  checkout vanished mid-study; citations are to a fresh shallow clone at
  `<scratchpad>/murex`, commit `8678ad8`, upstream github.com/lmorg/murex.)
- **elvish** — every pipe is *two parallel bands*: a byte file and a Go
  channel of values. (Local checkout commit `26a8bd5`.)
- **TermKit (2011, dead)** — a mime-typed *data* pipe separated from a
  *view* pipe of UI widgets; the closest thing ever built to a
  "multimodal CLI".

`<scratchpad>` = `/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/0dd2c19c-0d3d-4460-bc78-6df9646215d1/scratchpad`.

---

## 1. murex: one mime-like type tag per byte stream

### What it is / the data model

murex keeps Unix byte pipes but attaches a single **data-type tag** to
every stdio stream. The stream interface is `stdio.Io`
(`murex/lang/stdio/interface_io.go:14-39`): alongside `Read`/`Write` it
carries `GetDataType() string` / `SetDataType(string)`, plus typed
iteration hooks — `ReadArray`, `ReadArrayWithType`, `ReadMap`. The tag is
a short string, not a mime type: base types are declared in
`murex/lang/types/types.go:10-26` (`Generic = "*"`, `json`, `csv`,
`str`, `bin`, ...).

Mime types exist at the *edges* and are folded onto murex types by
`MimeToMurex` (`murex/lang/define_mime.go:14-51`): exact table first,
then prefix rules — `text/*` → `str`, and notably
**`audio`, `music`, `video`, `image`, `model` → `types.Binary`**
(`define_mime.go:41-42`). `MurexToMime` (`define_mime.go:96-98`) maps
back out for HTTP bodies.

Each data type registers codecs in global registries:
`RegisterMarshaller`/`MarshalData` (`murex/lang/define_marshal.go:8-44`)
and `RegisterUnmarshaller` (`murex/lang/define_unmarshal.go:14-19`), plus
per-type array/map readers (`murex/lang/stdio/types.go:12-23`). Builtins
like `foreach` and index (`[[ ... ]]`) call these registries, so the same
script works over JSON, YAML, CSV — a builtin unmarshal→transform→marshal
loop keyed off the stream's tag. Type packages live under
`murex/builtins/types/{json,csv,yaml,toml,xml,...}`.

The tag lives on the stream object itself: `Stdin` struct has
`dataType string` next to the buffer
(`murex/builtins/pipes/streams/define.go:22-33`).

### Two revealing warts

**The tag is a concurrency hazard.** `GetDataType`
(`murex/builtins/pipes/streams/utils.go:33-81`) is a spin-loop: the
reader polls until the writer sets the tag or all writers close. The
code is littered with commented-out locks and this comment
(`utils.go:42-46`): *"This should probably be locked to avoid a data
race, but I'm also quite scared locking it might also cause deadlocks
given processes can be terminated at random points"*. `SetDataType` is
write-once — a second set is silently ignored
(`utils.go:84-96`). A single mutable type field on a live stream forced
murex to choose between races and deadlocks.

**Typing stops at the external-process boundary — and the fix was
abandoned.** `murex/lang/exec.go:153-215` contains a fully written but
*commented-out* mechanism: spawn external commands with an extra fd 3
over which the child could announce its murex data type back to the
shell. It never shipped; external commands just get `types.Generic`
(`exec.go:190`, `lang/process.go:157`). Extending the type channel past
processes you own is where the design stalled.

### Media handling and boundary rendering

Media in the pipe is **bytes + tag `bin`, and nothing else**: there is no
marshaller registered for `types.Binary` (no `builtins/types/binary/`;
grep for `RegisterMarshaller` finds only text-shaped formats), so the
pipeline can move an image but never operate on it. All rendering
happens at the boundary, via `open`:

- `open` resolves a data type from extension, or from HTTP Content-Type
  via `MimeToMurex` (`murex/builtins/core/open/open.go:69-90`).
- It then dispatches to a per-type, user-scriptable **openagent**
  (`murex/builtins/core/open/openagent.go`) — a shell block registered
  per data type.
- The default image agent
  (`murex/config/defaults/profile_any.mx:701-795`) is the payoff: it
  sniffs the *terminal's* capability (`$KITTY_WINDOW_ID`,
  `$ITERM_PROFILE`, `$MXTTY`, tmux passthrough...) and renders the image
  inline via kitty icat, iTerm OSC 1337 (`inline=1:` + base64), sixel,
  or a "compatible" ANSI fallback (`open-image`). Same typed bytes, N
  renderings, chosen by consumer capability at the last moment.

So murex, today, in production, is already a small multimodal CLI:
`open photo.jpg` shows pixels in a kitty terminal — but pipes never
carry anything but bytes+tag, and base64 appears only inside a
boundary-specific escape sequence, never on plain stdout.

---

## 2. elvish: mandatory dual bands — and what that honestly costs

### The data model

Every elvish pipe/port carries **both** bands, always. The comment is
the contract (`elvish/pkg/eval/port.go:17-21`): *"Port conveys data
stream. It always consists of a byte band and a channel band."* —
`File *os.File` + `Chan chan any`. There is no "byte-only" or
"value-only" port: placeholders exist so neither field is ever nil —
`ClosedChan`, `BlackholeChan`, `DevNull`, `DummyInputPort`
(`port.go:46-65`).

Pipeline wiring (`elvish/pkg/eval/compile_effect.go:115-135`): each
stage-to-stage link is an `os.Pipe()` **plus** a `chan any` of buffer 32
(`compile_effect.go:67`), with `sendStop`/`readerGone` plumbing so a
value writer learns when the reader form has exited
(`compile_effect.go:141-146`, `port.go:283-296`).

Producers pick a band: `echo` writes bytes, `put` writes values
(`website/learn/unique-semantics.md`, "Structureful IO"). Consumers that
iterate input merge both bands: `IterateInputs`
(`elvish/pkg/eval/frame.go:127-151`) runs two goroutines — one turning
each byte *line* into a string value (`linesToChan`,
`frame.go:153-167`), one draining the channel — into a single merged
chan.

### Does elvish's dual channel rot?

**No — and the reason is instructive.** The brief's invariant is
"optional dual channels rot". Elvish dodges it by making the second
channel *non-optional*: every port has both bands by construction, the
core iteration primitive reads both, and half the builtin library
(`each`, `take`, `count`, `all`, ...) lives on the value band. Fifteen
years in, the value band is the *primary* band; it is byte-only usage
that is the compatibility case. The rot claim is about optionality, and
elvish is the existence proof that mandatory-both does not rot.

### What it costs (both costs verified empirically)

Built `elvish-bin` from the checkout and ran experiments
(binary at `<scratchpad>/elvish-bin`):

**Cost 1 — no total order across bands.** The two bands are physically
separate transports; nothing preserves cross-band ordering. Documented
in the reference (`elvish/website/ref/language.md:977-985`): *"the
ordering between value output and byte output might not agree with the
order in which they happened"*. Observed: five runs of
`put (echo a; put b; echo c; put d)` returned `b d a c`, `a c b d`,
`a b d c`, ... — a different interleaving almost every run. **A
dual-band design cannot express "figure 2 appears after paragraph 3".**
This is fatal to the brief's question 4, where ordered text/image
interleaving is the entire value of the MCP channel.

**Cost 2 — band mismatch deadlocks.** Values piped into a byte-only
consumer have no escape hatch: `range 40 | cat` hangs forever
(observed; killed after timeout). Mechanism from source: `range` blocks
sending value #33 into the 32-slot chan
(`compile_effect.go:67,123`); `cat` reads only the byte band and waits
for EOF; the byte write-end closes only when `range`'s form finishes;
`sendStop` fires only when the *reader form* exits
(`compile_effect.go:141-146`). Nobody moves. Small value counts merely
vanish silently (`put foo | cat` prints nothing of `foo`). Interop with
externals is by explicit serialization instead: `to-json | python ... |
from-json` (`website/learn/unique-semantics.md`, "Interoperability with
External Commands").

### Boundary rendering

Deterministic and tiny, per band-crossing:

- Value band → terminal file: `FilePort` writes `"▶ " + ReprPlain(v) +
  "\n"` per value (`port.go:239-254`); same marker in
  `StringCapturePort` (`port.go:206`). One canonical text projection of
  a value, everywhere.
- Byte band → value context: one string value per line, line ending
  chopped (`ValueCapturePort`, `port.go:155-191`; `linesToChan`).
- Capture keeps bands separate when the caller wants fidelity:
  `CapturePort` returns `([]any, []byte)` (`port.go:126-150`).

No media story at all — elvish values are strings/lists/maps/functions
(`pkg/eval/vals/`); the byte band is the only carrier for binary and
nothing renders it.

---

## 3. TermKit: the multimodal CLI, built once, in 2011

### What it is

Steven Wittens' WebKit+Node.js terminal (repo dormant since Dec 2011;
design post https://acko.net/blog/on-termkit/). Its problem statement
(`TermKit/termkit.txt:5-12`) is uncannily the brief's: the character
grid "is not rich enough to display modern files / media /
visualizations"; "Piping raw/untyped binary or text streams between
apps is bad for everyone: humans have to suffer syntax ... computers
have to suffer ambiguities."

From the design post: *"there is no such thing as plain text. Text is
messy. Text-based formats lie at the basis of every SQL injection, XSS
exploit and encoding error."* The fix: *"separating the 'data' part
from the 'human' part. Then we can use messy text for humans, and pure
data for the machines."*

### The data model: mime-typed data pipe, separate view pipe

Each command gets **5 pipes** (`TermKit/Node-API.md:33-44`): `dataIn`,
`dataOut` (classic stdin/stdout, but *"the streams are prefixed with
MIME headers"* — only `Content-Type` required), `errorOut`, plus
`viewIn`/`viewOut` — a JSON message channel of widget operations
(`view.print`, `view.update`, progress bars, lists, images —
`Node-API.md:155-180`).

`termkit.txt:134-140` states the split precisely: *"The output of a
termkit command is split into data and view. ... Data is a raw binary
stream with meta-data annotation, from one process' stdout to another's
stdin. View is a packetized stream of UI updates and callback events,
going directly to the terminal."* Data flows process→process; view
flows process→display, multiplexed per-process into an *ordered,
addressable tree* (`view.add` with `target` paths,
`termkit.txt:253-297`) — ordering is native because the view stream is
one sequenced channel, not a parallel band.

### Boundary rendering: the formatter

The terminal end of the data pipe is a **formatter**
(`TermKit/Node/shell/formatter.js:33-46`) that reads the mime headers
and picks an output plugin by **specificity**
(`formatter.js:51-68`): prefix match (`image/*`) scores 1, exact type
scores 2, type+schema scores 3; highest wins, hex/fallback otherwise.

- **Two-level vocabulary.** File listings are
  `application/json; schema=termkit.files` — *"The `schema` acts as a
  marker to select the right output plug-in"* (blog;
  `formatter.js:373-377`). Mime carries the transport class; a schema
  parameter carries the semantic shape. Wrapped legacy Unix output is
  `application/octet-stream; schema=termkit.unix`
  (`formatter.js:401-405`).
- **Media by type wrap, not by producer.** The image plugin base64s the
  buffered bytes into a `data:` URI and emits an image *widget*
  (`formatter.js:280-283`); PDF/HTML get sandboxed iframes
  (`formatter.js:158-165,192-198`). The producer stays bytes-dumb:
  *"TermKit `cat` doesn't know how to process PNGs ... it only guesses
  the MIME type based on the filename and pipes the raw data to the
  next process. Then the formatter sends the image to the front-end"*
  (blog). *"you can `cat` a PNG and have it just work."*
- **Budgets with placeholders.** The hex fallback clips at 4096 bytes
  and appends *"N bytes total, M shown"*
  (`formatter.js:452-477`) — elide-with-placeholder at the boundary,
  2011 edition.
- **Unix compatibility by wrapping**: externals piped as
  `application/octet-stream` *"to start with, and enhance specific
  applications with type hints and wrapper scripts"* (blog); typed
  input upgrades behavior transparently — TermKit grep *"supports
  grepping JSON data recursively ... transparently when the input is
  `application/json` instead of `text/plain`"* (blog).

### Why it died, and what that falsifies

The repo's entire life is 2011; roadmap items from 0.3 onward are
unchecked (`termkit.txt:57-101`). The death causes are scope, not data
model: it was simultaneously a new UI toolkit, a new frontend/backend
protocol, a session daemon, a rewrite of `ls`/`grep`/`cat`, and a
desktop app — *"It replaces and/or enhances built-in commands and wraps
external tools"* (`Readme.md:33`) — maintained by one person after a
viral launch. Every useful command needed a bespoke wrapper or output
plugin; until wrapped, tools fell back to escaped-octet-stream display.
Nothing in the record falsifies the typed-pipe idea itself — the parts
that worked (mime-dispatch formatter, cat-a-PNG, schema-tagged JSON)
are exactly the parts murex and nushell later re-grew independently.
What it falsifies is *adoption strategy*: a typed-content system that
demands the whole toolchain convert before it is useful dies of its own
surface area. The brief's "CLI still FEELS like a CLI, no ceremony"
requirement is precisely the lesson.

---

## 4. Lessons for vfs, numbered against the brief

**Q1 — Where blocks live.** murex and TermKit agree: producers emit
bytes + a type annotation; *conversion to display/consumable form is
the boundary's job* (formatter / openagent). That supports keeping
`Result` rows bytes-agnostic with typed annotation, and making the MCP
projection (not the verb) build the wire blocks. elvish is the
counter-model — typed values *in* the channel — and it works only
because both bands are mandatory; but its ordering loss (below) argues
against parallel channels as the representation.

**Q2 — Block vocabulary.** TermKit's `Content-Type` + `schema`
parameter (`application/json; schema=termkit.files`) is the strongest
precedent: adopt the boring transport taxonomy (mime, matching MCP's
blocks so projection is mechanical) and hang vfs-specific semantics on
an orthogonal annotation rather than minting new block types. murex
shows the failure mode of a *private* type vocabulary (`bin`, `*`):
it needs mime↔tag translation tables at every edge
(`define_mime.go`) anyway.

**Q3 — Algebra/keying.** No structured shell has a merge algebra —
streams, not values. Closest datum: murex's tag is write-once and
made concurrency painful (`utils.go` spin-loop); a frozen envelope
merging immutable block sequences avoids the entire class. elvish's
capture (`CapturePort` → `([]any, []byte)`) shows that once you have
two channels, every combinator must answer "what happens to the other
band" — an argument for one channel with typed elements over two.

**Q4 — Ordering.** The decisive finding. elvish's parallel bands lose
cross-band order — documented (`language.md:977-985`) and reproduced
(`put (echo a; put b; echo c; put d)` varies run to run). TermKit and
MCP both use a *single ordered sequence* of typed items and get
interleaving for free. If ordered text-image-text is the point, the
representation must be one sequence of typed blocks, not a text channel
plus a media channel.

**Q5 — Budgets.** TermKit's hex plugin (clip at 4096 +
"N bytes total, M shown") is the exact elide-with-placeholder posture,
applied at the boundary. murex's openagent picks the *cheapest
rendering the consumer supports*, degrading to a text placeholder —
budgets as boundary policy, not producer policy.

**Q6 — The stdout rule.** All three converge on one deterministic text
projection per band-crossing: elvish's `▶ ` + repr per value
(`port.go:244-247`), murex's openagent "compatible" fallback, TermKit's
escaped/hex fallback. None ever put base64 on a plain text stream;
base64 appears only inside boundary-specific envelopes (iTerm OSC
1337, `data:` URIs) that the *consumer* asked for.

**Q7 — Mime reality.** murex collapses all of `audio/ music/ video/
image/ model/` to one opaque tag and keeps the bytes moving
(`define_mime.go:41-42`) — unknown media passes through with its class
intact and only the boundary decides if it can render. TermKit's
specificity ladder (prefix-1 / exact-2 / schema-3, `formatter.js:51-68`)
is a clean pattern for "classify at the seam, degrade by specificity".

**Q8 — Executed-code output.** TermKit's answer for processes it didn't
write: default the stream to `application/octet-stream`, sniff/hint
type at the edge (`cat` guesses from filename), and let wrappers
upgrade specific tools. murex tried to let external programs
self-declare type over fd 3 and abandoned it in comments
(`exec.go:153-215`). Both point the same way: don't expect sandboxed
programs to speak the block protocol; make the `run` verb's boundary
sniff/annotate their byte output into blocks — self-declaration
across a process boundary is the part that historically never shipped.

**On the stance itself.** Three independent designers broke from
raw-text pipes; none went back, and none of the failures indict the
typing. TermKit died of rewrite-the-world scope; elvish's pain points
are structural to *parallel channels*, not to typed content; murex's
pain points are mutable stream state and the external-process seam.
The stance survives with two shape constraints: (a) one ordered
sequence of typed blocks, not dual channels; (b) text-case ergonomics
must be zero-ceremony (murex: `|` still works and untyped means
`generic`; elvish: `echo` unchanged; TermKit: violated this and died).

---

## Citations

- murex clone (commit 8678ad8): `<scratchpad>/murex/lang/stdio/interface_io.go:14-39`;
  `lang/stdio/types.go:12-23`; `lang/types/types.go:10-26`;
  `lang/define_mime.go:14-51,96-98`; `lang/define_marshal.go:8-44`;
  `lang/define_unmarshal.go:14-19`;
  `builtins/pipes/streams/define.go:22-36`;
  `builtins/pipes/streams/utils.go:33-96`; `lang/exec.go:153-215`;
  `lang/process.go:157,258-270`; `builtins/core/open/open.go:49-90`;
  `builtins/core/open/openagent.go`;
  `config/defaults/profile_any.mx:701-795`;
  `docs/user-guide/pipeline.md`.
- elvish (commit 26a8bd5): `/Users/claygendron/Git/Repos/elvish/pkg/eval/port.go:17-34,46-65,91-121,126-150,155-191,193-229,239-254,283-296`;
  `pkg/eval/compile_effect.go:67,106-157`;
  `pkg/eval/frame.go:127-167`;
  `website/learn/unique-semantics.md`;
  `website/ref/language.md:977-985`.
  Experiments: `<scratchpad>/elvish-bin` — `range 40 | cat` deadlock;
  `put (echo a; put b; echo c; put d)` order nondeterminism (5 runs).
- TermKit: `/Users/claygendron/Git/Repos/TermKit/termkit.txt:5-12,57-101,134-140,143-185,216-307`;
  `Node-API.md:33-44,155-180`; `Readme.md:29-35`;
  `Node/shell/formatter.js:33-68,143-172,177-206,268-290,309-377,380-405,437-485`;
  design post https://acko.net/blog/on-termkit/ (fetched 2026-07-25).
