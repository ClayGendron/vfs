# Study: PowerShell's object pipeline and formatting/output system

- **Subject repo**: `~/Git/Repos/PowerShell` (MIT). All `file:line` cites below are
  relative to that repo unless prefixed.
- **Why studied**: longest-lived production break from Unix text pipes (Monad, 2002;
  shipped 2006; still the primary Windows shell). The exact question it answers is the
  brief's Q6 — *typed values until the last hop, one deterministic default text
  rendering at the boundary* — plus hard evidence about what happens at the seam with
  untyped (native) tools.

## 1. What it is

PowerShell's pipeline never carries text between cmdlets. It carries .NET objects,
each wrapped in a `PSObject` envelope (`src/System.Management.Automation/engine/MshObject.cs:47`)
that adds an *extended type system* (ETS) identity: an ordered list of type names
(`TypeNames` / `InternalTypeNames`, MshObject.cs:820-849) that adapted members and
formatting views key off. Cmdlets `WriteObject()` typed values; there is no cmdlet
stdout. Error/Warning/Verbose/Debug/Information are separate *object* streams, not
fd2 text (visible as `WriteStreamType writeStream` stamped on formatting packets,
`FormatAndOutput/common/FormattingObjects.cs:151`).

Text exists in exactly one place: the formatting and output subsystem
(`src/System.Management.Automation/FormatAndOutput/`), which runs only at the end of
a pipeline — or at an explicit seam with a native program.

## 2. The data model

### 2.1 Objects in flight

- Everything is `PSObject`-wrapped on entry to the pipeline; the wrapper is transparent
  for method calls but carries ETS type names and instance members.
- Type identity is a *name list*, not a CLR type — so deserialized property bags
  (`Deserialized.System.IO.FileInfo`) can still match views and formatting
  (`engine/serialization.cs:685-693`; view matching masks the prefix,
  `FormatAndOutput/common/DisplayDatabase/typeDataQuery.cs:321-326`).

### 2.2 The formatting protocol: an ordered stream of typed render blocks

The most striking find for this brief: PowerShell's own format→output interface is
**an ordered array of typed content blocks**. `Format-*` commands do not produce text;
they emit a document-shaped stream of typed packets that `Out-*` commands consume:

- `FormatStartData` → (`GroupStartData` → `FormatEntryData`* → `GroupEndData`)* →
  `FormatEndData` (`FormatAndOutput/common/FormattingObjects.cs:81-153`).
- The file header states the design outright: these objects are "the communication
  protocol between formatting and output commands … Since format/xxx and out-xxx
  commands can be separated by serialization boundaries, the structure of these
  objects must adhere to the Monad serialization constraints"
  (FormattingObjects.cs:4-23).
- Each packet self-identifies with a GUID-named class-id property
  (`ClassId2e4f51ef21dd47e99d3c952918aff9cd`, FormattingObjects.cs:42-50) so the
  protocol survives being flattened into property bags by remoting; `Out-*` re-inflates
  packets through `FormatObjectDeserializer` / `FormatInfoDataClassFactory`
  (`FormatAndOutput/common/FormattingObjectsDeserializer.cs:348-411`).
- Packets carry *shape* (`TableHeaderInfo`, `ListViewHeaderInfo`, `WideViewHeaderInfo`,
  `ComplexViewHeaderInfo`) and *entries* (`TableRowEntry`, `ListViewEntry`,
  `RawTextFormatEntry`…) — i.e. a small closed vocabulary of render-block types.
- Out-of-band packets (`FormatEntryData.outOfBand`, FormattingObjects.cs:150) let
  errors, warnings, and scalar strings interleave *inside* an ordered document
  sequence without breaking the table/list context — ordering is meaning.

So PowerShell is simultaneously the precedent for "typed values until the boundary"
*and* for "the boundary projection is itself an ordered typed-block document."

## 3. The boundary rule (Q6 precedent)

### 3.1 Out-Default is host-injected — zero ceremony for the text case

The interactive host appends `Out-Default` to every command the user types; the user
never writes it:

- ConsoleHost executor: "then add out-default to the pipeline to render everything"
  (`src/Microsoft.PowerShell.ConsoleHost/host/msh/Executor.cs:186-198`, and
  `GetOutDefaultCommand` at Executor.cs:324-326, injected per-statement at 353-378).
- The cmdlet's own doc comment: "this command it implicitly inject by the powershell
  host at the end of the pipeline as the default sink"
  (`FormatAndOutput/out-console/OutConsole.cs:37-44`).
- `LocalPipeline` does the same for API invocations that request text
  (`engine/hostifaces/LocalPipeline.cs:308-326`).

This is why PowerShell *feels* like a normal CLI: `ls` prints a table with no
formatting ceremony, yet no text ever existed mid-pipeline. The "multimodal CLI feels
like a CLI" ergonomic is proven viable at 20-year production scale.

### 3.2 One renderer, selected deterministically

`Out-Default`/`Out-Host` wrap `OutputManagerInner`, which routes objects by ETS type
name to a sub-pipeline ending in `out-lineoutput`
(`FormatAndOutput/common/OutputManager.cs:19-134, 201-246, 302-313`). The `Out-*`
layer "assumes the presence of a pre-processing formatting command" and, when raw
objects arrive, spins up `format-default` itself
(`FormatAndOutput/common/BaseOutputtingCommand.cs:42-56`). Default view selection is
fully deterministic:

1. Pre-formatted packets pass through untouched ("we are already formatted…",
   `FormatAndOutput/common/BaseFormattingCommand.cs:208-217`).
2. Known scalar/leaf types and property-less objects render out-of-band as raw
   `ToString()` text (`FormatViewManager.cs:506-511, 539-549` —
   `GenerateOutOfBandObjectAsToString` → `RawTextFormatEntry`). Strings print as
   strings; no table ceremony.
3. Otherwise the display database (compiled-in `*.format.ps1xml`,
   `FormatAndOutput/DefaultFormatters/`) is matched by type-name list; e.g. `FileInfo`
   gets the Mode/LastWriteTime/Length/Name table
   (`DefaultFormatters/FileSystem_format_ps1xml.cs:72-95`).
4. No registered view → heuristic: shape from type, else **table if the default
   property set has ≤ 4 properties, else list** (`FormatViewManager.cs:399-429`;
   `typeDataQuery.cs:333-339`; threshold constant 4 at
   `DisplayDatabase/displayDescriptionData.cs:192-199`).

### 3.3 …but the rendering is device-parameterized, and that caused pain

The "one deterministic rendering" is parameterized by terminal width (fallback 80
columns, `FormatAndOutput/out-console/ConsoleLineOutput.cs:507, 101-124`), by a 300 ms
autosize buffering window for column widths (`BaseOutputtingCommand.cs:144-153`), and
— since 7.2 — by ANSI decoration, which needed a global policy knob
(`$PSStyle.OutputRendering`, `FormatAndOutput/common/PSStyle.cs:14-21, 642`) to decide
whether escape sequences reach redirected output. Formatting failures render as
in-band cell text `#ERR` / `#FMTERR` (`displayDescriptionData.cs:181-187`).
Lesson: make the boundary rendering *canonical* (width-independent, decoration-free)
if it will ever be consumed by machines/models rather than terminals.

## 4. The native seam: how untyped tools degrade — and what it destroyed

### 4.1 Objects → native stdin: the same renderer, again

Objects piped into a native executable are rendered by *the very same formatting
system*: `NativeCommandProcessor` runs a steppable `Out-String -Stream` pipeline and
writes each rendered line to the child's stdin
(`engine/NativeCommandProcessor.cs:2387, 2305-2330`). Raw `byte[]`/`byte` values
bypass rendering and hit the stream directly (NativeCommandProcessor.cs:2288-2300).
This is the crucial coherence property: there is exactly **one** text projection,
reused at every text seam — display, native stdin, `Out-File`. vfs's stdout rule
should copy this: the placeholder rendering for a media block must be the same
everywhere text is demanded.

### 4.2 Native stdout → objects: lines as strings

Native stdout is read line-by-line (`process.BeginOutputReadLine()`,
NativeCommandProcessor.cs:2038) and each line enters the pipeline as a `string`
object (`ProcessOutputObject` queue, NativeCommandProcessor.cs:113-133, 991,
2078, 1517-1560), decoded with `Console.OutputEncoding` or `$PSNativeCommandUseErrorActionPreference`-era
overrides (NativeCommandProcessor.cs:1649-1727, 2371). A `#< CLIXML` magic first line
upgrades the stream to deserialized objects (Serialization: `XmlCliTag`,
`src/Microsoft.PowerShell.ConsoleHost/host/msh/Serialization.cs:50, 159`;
NativeCommandProcessor.cs:2062-2071).

### 4.3 The 18-year binary-data bug and the BytePipe fix

Because *everything* crossing the native seam became decoded strings, piping binary
data through PowerShell corrupted it for nearly two decades (`tar | gzip`-style
pipelines, media bytes). The fix only landed as the 7.4-era experimental feature
**PSNativeCommandPreserveBytePipe**: when the pipeline builder detects two adjacent
native commands, it wires their fds together as a raw byte stream that never enters
the object world (`engine/pipeline.cs:270-292` — `DownStreamNativeCommand` /
`UpstreamIsNativeCommand`; `engine/BytePipe.cs:18-113` — `NativeCommandProcessorBytePipe`,
`FileBytePipe` for `>` redirection; wiring at NativeCommandProcessor.cs:970-1010).

This is the strongest single piece of evidence in the study: **a typed pipeline that
forces all foreign output through text-line decoding will destroy media**, and
retrofitting bytes-as-bytes later is expensive and bolted-on. nushell's
`ByteStream`-until-boundary (already in the vfs hermetic memo) is the same lesson
learned earlier; PowerShell proves the cost of not having it.

## 5. The wire projection: dual output formats at the host boundary

The console host picks the projection *once, at the boundary*, not per-cmdlet:
`-OutputFormat Text` (default) injects `Out-Default`; `-OutputFormat XML` skips
formatting entirely and serializes objects as CLIXML to stdout behind the
`#< CLIXML` tag (`Executor.cs:186` — outputter added only "if OutputFormat ==
Serialization.DataFormat.Text"; `ConsoleHost.cs:1416-1443`;
`Serialization.cs:86-106`). Remoting serialization is depth-limited (default depth
constants at `engine/serialization.cs:48, 215`) and produces `Deserialized.*`
property bags — type fidelity and methods are lost, only data and type *names*
survive. Precedent for `Result`: one envelope, two projections (text vs structured),
selected by the consumer's channel; and a warning that lossy serialization is
tolerable only because type *names* still key behavior on the far side.

## 6. Ergonomic wins and pains (what 20 years surfaced)

**Wins**

- Zero-ceremony text case: host-injected `Out-Default`; scalars/strings render raw
  (ToString out-of-band path), so `echo hi` behaves exactly like Unix.
- Rich objects compose without parsing (`ls | where Length -gt 1kb | sort
  LastWriteTime`); the display never constrains the data.
- Per-type curated default views (the ps1xml database) give consistent, legible
  output for thousands of types, with a sane 4-property table/list fallback for
  unknown ones.
- Ordered document protocol with out-of-band interleaving means errors appear *in
  place* amid tabular output without corrupting it.

**Pains**

- **Format-object leakage**: `Format-Table | Export-Csv` emits serialized
  `FormatStartData`/`FormatEntryData` garbage, because render blocks are ordinary
  pipeline values distinguishable only by convention. `Out-Default` itself must
  filter them from `-OutVariable` *by string-prefix match on the type name*
  (`OutConsole.cs:106-115` — checks
  `"Microsoft.PowerShell.Commands.Internal.Format"`); the formatter detects
  already-formatted input the same way (`BaseFormattingCommand.cs:212-217`). The
  boundary rule is enforced nowhere in the type system.
- **Flattening surprises**: any object reaching a `[string]` parameter, string
  interpolation, or the native seam collapses via `ToString()`/`Out-String`; what
  survives depends on the *display view*, not the data (a `FileInfo` becomes its
  view line; columns truncate at the 80-col fallback width). Display-width-dependent
  data loss at a semantic boundary.
- **Two views of one value**: default views show a property subset, so users
  routinely believe data is missing when only the *view* elided it.
- **Binary corruption at the native seam** until BytePipe (§4.3).
- **Heavy machinery**: the view system (four shapes × ps1xml loader × autosize ×
  grouping) is thousands of lines; the extensible-view database is powerful but is
  the single most complex subsystem in the shell.

## 7. Lessons for vfs, numbered against the brief

1. **Where blocks live (Q1)**: PowerShell keeps *data* typed in the pipeline and
   generates *render blocks* only at the boundary — and its one great regret is that
   those render blocks are pipeline-visible values (§6 leakage). Supports: `Result`
   carries typed media as first-class evidence (bytes + mime), and MCP content
   blocks are **projection output**, never envelope state that can leak back into
   chaining. If blocks must round-trip (`from_payload`), give them a real type tag,
   not a conventional marker — PowerShell's GUID-property hack
   (FormattingObjects.cs:42-50) is what "no proper tag" looks like after 20 years.
2. **Block vocabulary (Q2)**: the format protocol is a small closed set of packet
   types (start/group/entry/end × 4 shapes) and it survived unchanged since v1;
   per-type *extensible views* are where the complexity lives. Adopt MCP's tiny
   closed taxonomy at the wire; if vfs ever wants curated per-type renderings, that
   is a separate (expensive) display-database concern, not a wire concern.
3. **Algebra/keying (Q3)**: no precedent for merge — format packets are an
   *unkeyed ordered sequence*, and that is the point: content is document-shaped,
   not set-shaped. Supports treating `content` as order-preserving concatenation
   under `+` (op order), unlike keyed row merge; rebase has no analog and should not
   touch blocks.
4. **Ordering (Q4)**: strongest precedent studied — the entire format protocol is an
   ordered stateful document stream with explicit brackets, designed to survive
   serialization boundaries intact (FormattingObjects.cs:4-23). Out-of-band
   interleaving inside a sequence (FormattingObjects.cs:150) is exactly the
   text-image-text interleaving pattern the brief wants.
5. **Budgets (Q5)**: precedent for bounded rendering: `$FormatEnumerationLimit`
   caps enumerated members (`BaseFormattingCommand.cs:85`), autosize caches only a
   window (300 ms / first-N, BaseOutputtingCommand.cs:144-153), errors render as
   fixed elision markers (`#ERR`, displayDescriptionData.cs:181-187). Elide with a
   deterministic marker, never with silence.
6. **The stdout rule (Q6)**: fully vindicated. One deterministic default rendering,
   applied at the last hop, *injected by the host* so the text case needs zero
   ceremony (Executor.cs:186-198) — and critically, the **same** renderer is reused
   at every other text seam (native stdin via `Out-String -Stream`,
   NativeCommandProcessor.cs:2387). Two amendments from PowerShell's scars: make the
   canonical text rendering device-independent (no width/ANSI parameterization —
   §3.3), and never let base64/bytes reach the text projection (the pre-BytePipe
   corruption era, §4.3).
7. **Mime reality (Q7)**: PowerShell's seam transcodes everything through
   console-encoding text and destroyed unknown byte content for 18 years; the fix
   was opaque end-to-end byte passthrough (BytePipe). Supports: pass unknown media
   through with mime intact as opaque bytes; classify/transcode never at the seam.
8. **Executed-code output (Q8)**: native processes *are* PowerShell's executed
   programs, and their output enters the object world as decoded text lines unless
   both endpoints are byte-aware (pipeline.cs:270-292). Cautionary precedent: if the
   vfs `run` verb scrapes sandbox stdout as text, media is lost at birth. Capture
   typed/byte output at the source (declared output channel or fs artifacts), and
   make stdout-scraping the fallback, not the model.

**On the owner's stance**: PowerShell is 20 years of production evidence that
breaking from Unix text pipes works and can still feel like a CLI — provided (a) the
default rendering is host-injected and deterministic, (b) render/wire blocks are a
boundary product, not pipeline currency, and (c) foreign/binary content crosses seams
as opaque bytes, never through the text projection. Its failures are precisely the
places where those three rules were violated.

## Key citations

- OutConsole.cs:37-44, 106-115 — Out-Default doc comment; format-object filtering hack
- Executor.cs:186-198, 324-378 — host injection of Out-Default; Text-format-only
- FormattingObjects.cs:4-23, 42-50, 81-153 — typed ordered format protocol, GUID tags, outOfBand
- BaseOutputtingCommand.cs:42-56, 120-166 — out-* assumes/spawns formatter; packet state machine
- FormatViewManager.cs:399-429, 466-549 — shape heuristics; scalar ToString out-of-band
- typeDataQuery.cs:302-339 + displayDescriptionData.cs:192-199 — table-if-≤4-properties
- NativeCommandProcessor.cs:2288-2330, 2387, 2038, 991-1010 — Out-String at native stdin; byte passthrough; line-decoded stdout
- pipeline.cs:270-292 + BytePipe.cs:18-113 — native-to-native raw byte binding (PSNativeCommandPreserveBytePipe)
- Serialization.cs:50, 86-106, 159 + ConsoleHost.cs:1416-1443 — CLIXML dual projection
- serialization.cs:48, 215, 685-693 — depth-limited property-bag remoting, Deserialized. prefix
- PSStyle.cs:14-21, 642 + ConsoleLineOutput.cs:101-124, 507 — device-parameterized rendering knobs
