# Jupyter's display protocol: mimebundles and rich reprs

Study for the multimodal Result content brief
(`context/research/2026-07-25-multimodal-result-content-brief.md`).
Primary sources: `~/Git/Repos/jupyter_client/docs/messaging.rst` (the Jupyter
messaging spec, protocol 5.x) and `~/Git/Repos/ipython/IPython/core/`
(`formatters.py`, `display.py`, `display_functions.py`, `displaypub.py`,
`pylabtools.py`), plus `jupyter_client/jupyter_client/jsonutil.py` for wire
encoding. All paths below are relative to `~/Git/Repos/` unless absolute.

## 1. What it is

Jupyter is the most successful deployed system in which one value carries
multiple typed representations and the consumer picks. Since ~2011 (IPython
0.12's ZMQ kernel split) the architecture has been: code executes in a
*kernel*; its outputs cross to *frontends* (notebook, terminal console,
QtConsole, nbconvert) as typed messages on a pub/sub channel (IOPub). Rich
output is never smuggled through stdout — stdout and stderr are their own
message type (`stream`, text-only by construction:
`jupyter_client/docs/messaging.rst:1522-1529`), while rich values travel as
**mimebundles**: a dict keyed by MIME type whose values are alternative
representations of the *same* object
(`messaging.rst:1541-1545`: "Each message can have multiple representations
of the data; it is up to the frontend to decide which to use and how. A
single message should contain all possible representations of the same
information.").

This is directly the brief's architectural stance, shipped fourteen years
ago: the executing program's stdout remains a Unix text stream forever, and
everything richer crosses the boundary as typed, mime-tagged structure. The
terminal frontend still feels exactly like a REPL because every bundle
carries `text/plain` and the terminal simply selects it — no ceremony, no
manual conversion by the user.

## 2. The data model

### 2.1 The mimebundle: alternatives of ONE value, unordered

`display_data` message shape (`messaging.rst:1554-1575`):

```python
content = {
    'data': dict,       # {mime_type: representation} — alternatives
    'metadata': dict,   # per-mime sub-dicts + global keys
    'transient': dict,  # NOT persisted to documents (5.1+)
}
```

Key structural facts:

- **`data` is a dict — there is no order among representations.** The
  alternatives axis is a *selection* problem, not a sequence problem. The
  consumer holds a ranked preference list (classic notebook's
  `OutputArea.display_order`; terminal IPython effectively ranks
  `text/plain` first) and renders its best match. "Frontends should ignore
  mime-types they do not understand" (`messaging.rst:1688-1689`).
- **`metadata` mirrors `data`'s keys** for per-representation annotation —
  the only spec-defined keys are image width/height and
  `application/json: {expanded}` (`messaging.rst:1585-1600`). IPython also
  stuffs `alt` text there (`ipython/IPython/core/display.py:1104-1105`).
  Lesson: a representation needs an annotation slot *beside* its payload,
  not inside it.
- **`transient` exists solely to mark data that must not be persisted**
  ("Information not to be persisted to a notebook or other documents.
  Intended to live only during a live kernel session",
  `messaging.rst:1570-1572`, `1603`, `1646`). It was added in protocol 5.1
  (2017) — direct evidence that "what crosses the live wire" and "what gets
  written into the durable document" needed to be *different sets*, and
  that the original protocol conflated them.
- `execute_result` (a cell's return value) is "identical to `display_data`
  messages, with the addition of an `execution_count` key"
  (`messaging.rst:1683`, `1699-1712`) — result-of-execution and
  side-effect-display share one representation shape. The pattern also
  spread: `inspect_reply` "is a mime-bundle, like a `display_data` message"
  (`messaging.rst:718-719`), and v5 converted `object_info_reply` to a
  mimebundle (`messaging.rst:2044`).

### 2.2 The producer protocol: rich reprs

`IPython/core/formatters.py` maps Python objects to bundles. Each mime type
has a formatter with a `print_method` hook: `_repr_html_` (line 788),
`_repr_svg_` (819), `_repr_png_` (835), `_repr_jpeg_` (853), `_repr_json_`
(889), `_repr_pdf_` (942), plus `_repr_pretty_` for `text/plain` (669).
IPython 6.1 added `_repr_mimebundle_(include=, exclude=)` returning the
whole dict (or `(data, metadata)` tuple) at once
(`formatters.py:987-1035`), and `_ipython_display_` as an escape hatch for
objects that display *themselves* by making multiple display calls
(`formatters.py:946-964`).

`DisplayFormatter.format` (`formatters.py:148-247`) computes ALL active
representations eagerly and resolves precedence:

1. `_ipython_display_` — object handles itself, short-circuit (line 203).
2. user-registered per-mime formatter (via `for_type`) beats
3. `_repr_mimebundle_` output, which beats
4. the default per-mime `_repr_*_` method (lines 216-231, comment at
   219-223 spells the ladder out).

Two lessons hide in that ladder. First, **precedence ladders accrete**:
three generations of hooks (`_ipython_display_` 2013, per-mime reprs, then
`_repr_mimebundle_` 2017) all still live, and `format()` needs a four-rule
arbitration with an inline comment to stay coherent. A vocabulary designed
once, with one producer entry point, avoids this. Second, **eager
all-representations computation is the cost of consumer choice**: every
display computes every active mime type even though most frontends use one.
`active_types` exists as a whitelist precisely to cut that cost
(`formatters.py:91-109`).

Error isolation is exemplary: `catch_format_error`
(`formatters.py:274-293`) wraps every formatter call — one broken
`_repr_html_` shows a traceback and yields `None` for that mime type; the
rest of the bundle survives. Same philosophy as `Result.from_payload`'s
per-item quarantine.

Notably, the module docstring's *own worked example* today is an
LLM-specific mime type: registering `format_type = 'x-vendor/llm'` /
`print_method = '_repr_llm_'` so any object can carry an LLM-targeted
representation beside `text/plain` (`formatters.py:24-56`). The mimebundle
pattern is already being aimed at exactly the brief's consumer.

### 2.3 The text/plain floor — the brief's stdout rule, in 2011 clothes

- Spec: "A plain text representation should always be provided in the
  `text/plain` mime-type" (`messaging.rst:1686-1687`).
- API docstring: "Minimally all data should have the 'text/plain' data,
  which can be displayed by all frontends"
  (`display_functions.py:50-51`, repeated `displaypub.py:114`).
- Enforcement: `PlainTextFormatter.enabled = Bool(True).tag(config=False)`
  — the one formatter that *cannot be disabled*, with fallback to `repr()`
  (`formatters.py:630-659`). Even `active_types` whitelisting can't remove
  it in practice because the terminal frontend depends on it.
- Even the deprecated pager payload demands it: "Must include text/plain"
  (`messaging.rst:627`).

This is the exact placeholder/stdout rule the brief's question 6 asks for:
every rich value has a mandatory, always-computable text projection, so a
text-only consumer never sees base64 and never sees nothing. Jupyter's floor
is `repr()`-derived (describes the *object*); vfs's floor should be
placeholder-derived (path + mime + size — describes the *addressable
media*), which is strictly better because vfs outputs have addresses and
notebook outputs do not (see §5 on bloat).

### 2.4 Encoding: base64 per value-type, at two seams

The messaging spec never says "base64". Encoding is decided per mime type by
convention and enforced at two places:

- **Producer seam**: image/PDF reprs return base64 `str` (or raw `bytes`)
  — `PNGFormatter`/`JPEGFormatter`/`PDFFormatter` accept
  `_return_type = (bytes, str)` (`formatters.py:837`, `855`, `944`);
  `Image._data_and_metadata` does `b2a_base64(self.data, newline=False)`
  (`display.py:1092`), matplotlib figures likewise
  (`pylabtools.py:117-163`).
- **Transport seam**: `jupyter_client`'s JSON packer catches any raw
  `bytes` that leaked through and base64s them
  (`jupyter_client/jupyter_client/jsonutil.py:117-118`, `161-164`).

Text-native mime types stay text: `image/svg+xml` is carried as its XML
source (the SVG formatter's return type is plain `str`,
`formatters.py:805-819`) — supporting the brief Q6's "SVG passes through as
text". Structured types stay structured: protocol 5.0 changed
`application/json` to be "unpacked JSON data, not double-serialized as a
JSON string" (`messaging.rst:1612-1615`, `2037`) — a deployed lesson that
double-encoding structure into strings is a mistake worth a breaking
protocol change to fix.

Any string is accepted as a mime key ("Any mime-type is valid",
`formatters.py:994`); unknown types ride through and consumers ignore them
(`messaging.rst:1688-1689`). Vendored types use suffixed/vendor names
(`application/vnd.jupyter.widget-view+json`, `x-vendor/llm`). This answers
brief Q7's shape: classify nothing at the seam, carry mime verbatim, let
the consumer's preference list decide — with the text floor guaranteeing
there is always something to show.

## 3. The boundary-rendering story

The kernel side is one narrow funnel: `display()` →
`publish_display_data()` → `DisplayPublisher.publish(data, metadata, *,
transient, update)` (`display_functions.py:36-77`,
`displaypub.py:81-120`). In terminal IPython the base `DisplayPublisher`
just writes the `text/plain` entry to stdout; in ipykernel the ZMQ subclass
emits a `display_data` IOPub message. **The same program, unchanged,
renders text at a text boundary and rich content at a rich boundary** —
selection is the boundary's job, never the emitting code's. That is the
"multimodal CLI that still feels like a CLI" working in production.

The consumer side (notebook/nbconvert) walks its preference list per
bundle. Nothing in the protocol tells the frontend which representation is
"best"; the spec deliberately leaves it "up to the frontend to decide which
to use and how" (`messaging.rst:1542-1543`). For vfs, the MCP projection
plays frontend: per block, pick the representation the model API accepts.

The failed alternative is instructive: **execution payloads** — an untyped
`list(dict)` of frontend action commands (`page`, `set_next_input`,
`edit_magic`) riding on `execute_reply` — are "considered **deprecated**,
though their replacement is not yet implemented"
(`messaging.rst:590-628`, esp. 612). The grab-bag side channel of
frontend-interpreted actions rotted; the typed, self-describing message
stream won. A `content` channel should be typed data, never "instructions
to the renderer".

## 4. Ordering, identity, and updates

Jupyter splits the two axes the brief's Q3/Q4 conflate at its peril:

- **Alternatives axis** (which representation of one value): unordered
  dict, consumer selects. No order needed or provided.
- **Sequence axis** (which outputs, in what order): the ordered stream of
  `stream`/`display_data`/`execute_result` messages on IOPub, bracketed by
  `status: busy` / `status: idle` ("the outputs associated with a given
  execution shall generally arrive between the busy and idle status
  messages", `messaging.rst:1744-1746`). The notebook document (nbformat)
  freezes this as each code cell's `outputs` **list**, in arrival order —
  so a cell interleaving `print(...)` and figure displays persists exactly
  that interleaving as alternating `stream` and `display_data` output
  entries.

The sequence axis's guarantee is *transport arrival order* — and where the
transport guarantee runs out, the spec has a documented hole: asynchronous
output produced after `idle` is "currently undefined in this
specification" (`messaging.rst:1748-1756`). Ordering-by-arrival is fragile;
ordering should be a property of the data structure (an ordered list inside
the result), not of when packets landed. vfs's `Result` is a value, not a
stream, so it can and should own its ordering outright.

**Identity/updates**: outputs have no keys by default. `display_id` —
opt-in, carried in `transient` (`messaging.rst:1605-1609`) — names a
display so a later `update_display_data` message (same shape,
`messaging.rst:1634-1650`) can replace it: "all displays that match the
`display_id` are updated (even if there are multiple)"
(`messaging.rst:1652-1653`). Client-side, `display(obj,
display_id=...)` returns a `DisplayHandle` with `.display()`/`.update()`
(`display_functions.py:290-355`); fresh ids are 16 random bytes
(`display_functions.py:79-81`). Points for the brief's Q3: (a) identity for
media was bolted on six years in (5.1), because streaming/progressive use
cases demanded it — design keying in from the start; (b) the key is
opaque and random, because notebook outputs have no natural address. vfs
media *does* have a natural address — the path — which is a structurally
stronger key than anything Jupyter had available; (c) update semantics are
whole-replacement of all matches, not merge — no algebra was ever attempted
over outputs, so Jupyter offers no evidence on merge semantics, only on
identity.

## 5. Budgets and the bloat pathology

The known real-world failure: **embedded base64 makes the durable document
huge**. Mechanics, all in primary source:

- `Image` defaults to `embed=True` unless constructed from a `url`
  ("Should the image data be embedded using a data URI (True)... Default is
  `True`, unless the keyword argument `url` is set", `display.py:923-930`).
  The rationale given is offline reproducibility: "viewable later with no
  internet connection in the notebook" (`display.py:925-926`). The
  alternative is a link: `Image(url=...)` renders `<img src=...>` with no
  payload (`display.py:1056-1086`) — but "QtConsole is not able to display
  images if `embed` is set to `False`" (`display.py:932`): the link form
  breaks any consumer that can't dereference, which is exactly why embed
  won as the default.
- `retina` mode doubles pixel dimensions (`pylabtools.py:166-183`);
  matplotlib inline embeds a base64 PNG for *every* figure of every
  execution (`pylabtools.py:249-296`); nothing dedups re-executions —
  each run appends fresh bytes into the cell's outputs.
- The protocol's own patches acknowledge the wound: `transient` (5.1)
  exists to keep some data out of the document (`messaging.rst:1570-1572`);
  `figure_formats` lets users trade png→jpeg/svg with `quality` kwargs
  (`pylabtools.py:249-296`); and the wider ecosystem grew strip-on-save
  tooling (nbstripout, jupytext) because diffs and repos drowned in base64.

The structural cause: **notebook outputs have no address**, so the only way
to keep media visible later was to inline the bytes into the document.
vfs does not have this excuse — every artifact has a path, the trash/
restore machinery proves bytes persist independently of any envelope.
So the brief's Q5 posture (elide-with-placeholder by default,
media-on-request) is the correct inversion of Jupyter's default: Jupyter
embedded because it lacked addresses; vfs can link because addresses are
its core primitive. Keep Jupyter's floor (a text description always
present), drop Jupyter's default (bytes always inlined). The QtConsole
caveat is the counter-risk to monitor: a link-only block is worthless to a
consumer that cannot fetch — the placeholder must carry enough (path, mime,
size, description) for the model to *decide* to fetch, and the fetch verb
must actually exist.

## 6. Lessons for vfs, numbered against the brief

1. **Where blocks live (Q1).** Jupyter separates the durable value from
   its representations: the kernel-side object is the truth; bundles are
   *computed at the boundary* by formatters, and what persists (nbformat)
   differs from what rides the live wire (`transient`). This argues for
   the brief's "projection-time concern" pole for the *bytes* — rows stay
   addressable evidence; the MCP renderer materializes payloads — while
   the *order and identity* of content must live in the value itself
   (Jupyter's transport-order hole, §4). A hybrid: ordered typed blocks in
   the Result carrying address+mime+size always and bytes optionally.
2. **Block vocabulary (Q2).** Jupyter's vocabulary is open (any mime
   string), with conventions per family: binary → base64 str, text-native
   → text, structured → unpacked JSON (the 5.0 double-serialization fix,
   `messaging.rst:2037`). Blocks need a metadata slot beside data
   (width/height/alt live in `metadata`, not in the payload). Adopt open
   mime carrying with a small set of *rendering* families rather than a
   closed enum; project onto MCP's taxonomy at the seam the way frontends
   project bundles onto their capabilities.
3. **Keying/algebra (Q3).** Jupyter's only key (`display_id`) is opt-in,
   random, transient, and arrived late; update is replace-all-matches, no
   merge. Evidence: identity matters and should be first-class from day
   one; vfs's path-keying is stronger than anything Jupyter had. No prior
   art here for merge semantics — the algebra question is vfs's own.
4. **Ordering (Q4).** Two axes, never conflated: alternatives of one value
   are an unordered *selection* set; distinct outputs are an ordered
   *sequence*. Jupyter's sequence order rests on transport arrival and has
   a documented undefined case (`messaging.rst:1754`); vfs should make
   order a property of the value.
5. **Budgets (Q5).** Embed-by-default without addresses bloated the
   ecosystem's documents for a decade; `transient`, `figure_formats`, and
   strip-on-save tools are all scar tissue. Elide-with-placeholder is the
   right default *because vfs has addresses*; ensure the fetch path exists
   or the placeholder is a dead link (the QtConsole lesson).
6. **Stdout rule (Q6).** Deployed proof: mandatory `text/plain` floor
   (`messaging.rst:1686`, un-disableable `formatters.py:659`) + stdout as
   a separate text-only `stream` channel = a terminal that feels like a
   terminal and a rich frontend that gets pixels, from the same unchanged
   program. SVG-as-text is already Jupyter practice.
7. **Mime reality (Q7).** Carry mime verbatim; consumers ignore unknown
   types; the floor guarantees something always renders. Don't classify at
   the seam; classify at the consumer (the MCP projection is a frontend
   with a preference list).
8. **Executed-code output (Q8).** Jupyter's answer to "how does a
   program's output become typed blocks": the runtime hooks the display
   path (`sys.displayhook` → `execute_result`; `display()` →
   `display_data`; matplotlib backend → `print_figure` → bundle), while
   raw stdout stays a `stream`. The `run` verb should follow suit: the
   sandbox's displayhook/backend produces typed blocks; bytes written to
   stdout stay text. `execute_result` vs `display_data` (same shape, one
   flag apart) shows return-value and side-effect emissions can share one
   block representation.
9. **Error isolation (bonus).** `catch_format_error`
   (`formatters.py:274-293`): one broken representation never poisons the
   bundle — the same per-item quarantine philosophy `from_payload` already
   has; apply it per content block.
10. **Against the stance? The honest caveats.** (a) Consumer-picks
    multi-representation bundles exist because Jupyter had *many unknown
    frontends*; vfs has essentially one consumer class (LLM harness via
    MCP) plus a text projection — a producer-picked single representation
    per block with a mandatory text floor captures the value at a fraction
    of the machinery (no precedence ladder, no eager all-formats
    computation, no `active_types` whitelisting). (b) Jupyter's hook
    surface accreted three generations of producer protocols; vfs should
    ship one construction path. (c) The 2026 IPython docstring teaching
    `x-vendor/llm` reprs (`formatters.py:24-56`) shows the ecosystem
    converging on the brief's premise from the other direction.
