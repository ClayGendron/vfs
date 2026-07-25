# Terminal-side media rendering: how a CLI shows media to a HUMAN

- **Study for**: multimodal Result content brief
  (`context/research/2026-07-25-multimodal-result-content-brief.md`)
- **Subject**: the human-facing half of a "multimodal CLI" — the three
  inline-graphics protocols, real tools that use them, agent-CLI precedent
  (Claude Code's own issue tracker), and the fallback ladder when graphics
  are unavailable.
- **Method**: online primary sources — protocol specs, terminal docs, tool
  READMEs, GitHub issues. All claims cited by URL.
- **Date**: 2026-07-25

---

## 1. What it is: three incompatible wire protocols, one shared shape

There is no standard for putting pixels in a terminal. Three protocols
coexist in 2026, all with the same abstract shape — *an escape-sequence
envelope around base64 (or palette-encoded) image bytes, injected into the
ordinary output stream* — and mutually incompatible framing.

### 1.1 Kitty graphics protocol (APC)

Spec: https://sw.kovidgoyal.net/kitty/graphics-protocol/

- Framing: `ESC _ G <k=v,k=v,...> ; <base64 payload> ESC \` — an APC
  (Application Programming Command) with comma-separated control keys.
- Pixel formats: `f=24` RGB, `f=32` RGBA (default), `f=100` PNG (terminal
  reads dimensions from the file itself).
- Transmission media (`t=` key): `d` direct-in-escape, `f` file path,
  `t` temp file (terminal deletes it), `s` POSIX shared memory. **Remote
  clients (ssh) must use direct transmission with chunking** — file paths
  are meaningless across the connection. Chunks: `m=1`/`m=0` continuation
  flag, max 4096 bytes per chunk, multiple of 4.
- Explicit capability **query**: `a=q` with a 1x1 probe image followed by
  `CSI c` (DA1); a supporting terminal answers `OK` (or an error) *before*
  the DA1 reply, so the client gets a bounded-time yes/no.
- Placement model is the richest of the three: image id + placement id,
  z-index (images under text), pixel offsets within cells, animation
  frames, relative placements.
- **Unicode placeholders** (since kitty 0.28): image cells are represented
  by the character `U+10EEEE` with row/column encoded in combining
  diacritics and image id in the foreground color. This makes the image
  *survive programs that only understand text* — tmux, vim — because the
  placeholder cells travel as ordinary styled text and the outer terminal
  resolves them to pixels. This is the protocol designers' own admission
  that text is the substrate everything must degrade through.

### 1.2 iTerm2 inline images (OSC 1337 File)

Spec: https://iterm2.com/documentation-images.html

- Framing: `ESC ] 1337 ; File = [key=value;...] : <base64 bytes> BEL`.
- Keys: `name` (base64 filename), `size` (bytes, for progress),
  `width`/`height` (in cells, px, %, or `auto`), `preserveAspectRatio`,
  `inline=1` (without it the payload is a *download*, not a display).
- Much simpler than kitty: no ids, no placements, one shot. The whole
  file — any format the emulator can decode — goes in one sequence.
- tmux: iTerm2 3.5+ added a chunked `MultipartFile`/`FilePart`/`FileEnd`
  variant specifically because tmux caps escape-sequence length.
- Detection: a separate "Feature Reporting protocol"; in practice tools
  key off `TERM_PROGRAM=iTerm.app` (env heuristic — see §3).

### 1.3 Sixel (DEC, 1987)

Support matrix: https://www.arewesixelyet.com/

- Framing: `DCS q <sixel data> ST` — pixels encoded six-scanlines-at-a-time
  as printable characters, palette-based (classically 256 colors, no
  alpha; some modern emulators do better).
- The only protocol with a *standardized* detection path: DA1 (`CSI c`)
  response containing extension code `4`
  (https://vt100.net/docs/vt510-rm/DA1.html).
- 2026 support (arewesixelyet.com): **yes** — xterm (default since patch
  #359), iTerm2 ≥3.3, WezTerm, foot ≥1.2, Konsole ≥22.04, mlterm,
  Contour, tmux (≥3.4, only if compiled `--enable-sixel`). **No** —
  kitty (deliberately refuses; considers sixel obsolete), Alacritty,
  Windows Terminal (open issue), GNOME Terminal and every VTE-based
  terminal (waiting on upstream VTE), Rio.

### 1.4 Who renders what in 2026 (cross-protocol matrix)

- **kitty protocol**: kitty, Ghostty (since 1.0, one of the most complete
  implementations including unicode placeholders — per Mitchell Hashimoto,
  https://x.com/mitchellh/status/2041253090205249584; libghostty now
  exposes it to embedders), Konsole ≥22.04, WezTerm (partial), st
  (patched), Warp, wayst (https://terminfo.dev/extensions/kitty-graphics-protocol).
- **OSC 1337**: iTerm2, WezTerm, mintty, Konsole; VS Code's integrated
  terminal supports images via the xterm.js image addon (sixel + iTerm2
  protocol, opt-in setting) — noted in anthropics/claude-code#2266.
- **sixel**: the widest legacy net (see §1.3) but with the two most
  popular GPU terminals (kitty, Alacritty) and Windows Terminal missing.
- **Nothing at all**: Alacritty (pixels rejected on principle), plain
  Linux console, CI logs, pagers, `> file` redirection — the fallback
  ladder is not an edge case, it is the *median* case.

## 2. The data model each protocol implies

Strip the framing and all three protocols carry the same tuple:

    (bytes, format/mime, intended size, optional name/id)

- Kitty `f=100` PNG and OSC 1337 both accept a compressed container and
  let the terminal decode — mime matters, not pixels.
- Kitty `f=24/32` and sixel are raw-pixel channels — the *sender* decodes
  and must know width/height.
- All three demand **chunking with declared budgets** (kitty: 4096 B per
  APC chunk; iTerm2 MultipartFile exists because tmux capped sequences at
  256 B, later 1 MiB; WezTerm caps images ~25 Mpx). Exactly the vfs
  boundedness doctrine, applied to a different wire: no escape sequence
  may grow unboundedly with payload size.

None of the three protocols carries *semantic* metadata (no description,
no source path). That belongs to the layer above — the tool that decides
to render — which is precisely where vfs's placeholder text (path, mime,
size, description) would live.

## 3. Detection: negotiation at runtime, never static

Best practice converged across implementations (blessed, notcurses, timg,
chafa; https://blessed.readthedocs.io/en/latest/terminal.html,
https://vtdn.dev/docs/dcs/xtversion/):

1. **Ask the terminal, with a timeout.** Kitty query (`a=q` probe) for the
   kitty protocol; DA1 extension `4` for sixel; XTVERSION/XTGETTCAP for
   emulator identity. A terminal that doesn't answer within the timeout is
   treated as dumb. This is a *round-trip on the tty* — it requires a
   controlling terminal and cannot be done when stdout is a pipe.
2. **Fall back to environment heuristics** (`TERM`, `TERM_PROGRAM`,
   `KITTY_WINDOW_ID`) only when queries fail — env vars are explicitly
   documented as unreliable because ssh does not forward them and
   multiplexers rewrite `TERM`.
3. **`isatty()` gates everything.** Piped/redirected stdout must never
   receive graphics escapes.

The multiplexer tax: tmux consumes unknown escapes by default.
`allow-passthrough on` (tmux ≥3.2) lets a client wrap sequences in a DCS
passthrough envelope so the *outer* terminal sees them — but then tmux
cannot account for the cells the image occupies, so scrolling and
window-switching corrupt the display (kovidgoyal/kitty discussion #4021;
https://tmuxai.dev/tmux-allow-passthrough/). The clean paths are: sixel
natively in tmux ≥3.4, or kitty unicode placeholders (only kitty and
Ghostty resolve them). tmux#4902 tracks native kitty-protocol support —
still open. Every real tool documents tmux as its main known-broken
configuration.

## 4. How real tools use them: the ladder is the product

### timg (https://github.com/hzeller/timg)

Backends ranked by fidelity: kitty → iTerm2 → sixel → unicode **quarter
blocks** → half blocks. Auto-detects, user can force with `-p{k,i,s,h,q}`.
Documents that tmux filters high-res protocols (workaround: tmux ≥3.3 +
kitty + explicit `-pk`), that ssh works *because* everything rides
standard escape codes, and ships a sixel alignment workaround env var.
The block modes are not an afterthought — quarter blocks trade color
accuracy for spatial resolution and are the default fallback.

### chafa (https://hpjansson.org/chafa/)

Same ladder as a library: sixels, kitty, iTerm2, and "unicode mosaics" —
character art from selectable symbol ranges, degrading through truecolor →
256 → 16 → FG/BG. Its identity is the degradation path: "works with most
modern and classic terminals" means *the bottom rung is always renderable*.

### ranger (https://github.com/ranger/ranger/wiki/Image-Previews)

A grab-bag of eight methods (w3mimgdisplay, ueberzug, urxvt, iTerm2,
kitty, wezterm, mpv, imv) chosen *manually* by the user in config —
evidence of what happens without a negotiation layer: the wiki is a
catalog of caveats (w3m breaks under compositors, "black stripes",
ueberzug breaks with tabs, everything breaks in tmux). The lesson is
negative: shipping N backends without auto-negotiation exports the
compatibility matrix onto the user.

### kitty icat

`kitten icat` refuses to run when it cannot query the tty (needs the
query round-trip described in §3), and transparently re-encodes/chunks
for ssh. It is the reference client for "ask first, then send."

## 5. Agent-CLI precedent: Claude Code's own issue tracker

Directly on point for "should vfs's CLI render media inline."

### anthropics/claude-code#2266 (closed) and #54546 (closed as duplicate)

- #2266 (https://github.com/anthropics/claude-code/issues/2266) requests
  terminal graphics support, proposes exactly the timg ladder (kitty →
  iTerm2 → sixel → unicode blocks) with auto-detection via env +
  capability queries.
- #54546 (https://github.com/anthropics/claude-code/issues/54546)
  contains the sharpest architectural analysis. The blocker is **not**
  protocol availability, it is the TUI:

      [1] model output → [2] TUI renderer → [3] PTY → [4] terminal

  - The markdown/TUI renderer sanitizes OSC/APC sequences out of model
    output (layer 1→2).
  - Bash tool stdout is captured, not forwarded to the PTY (2→3).
  - Even bytes injected straight into the PTY get clobbered by the next
    repaint, because the TUI's **row accounting does not know an image's
    height** (3→4). Six workarounds tested, all failed, including
    writes to `/dev/tty` and AppleScript injection.
  - Scrollback re-render regenerates the transcript from text — the
    image never comes back.
- Status as of 2026-07: **nothing shipped**; multiple duplicates open
  (#29254, #35893, #36476, #17044). What users actually get today is the
  placeholder: `Read` on a PNG puts the image into *model* context and
  prints a text stand-in into the transcript — i.e. Claude Code already
  lives the brief's asymmetry (model sees pixels via typed blocks; human
  sees a placeholder line) and the human-side upgrade is the unshipped
  part.

The transferable finding: **inline graphics are hard for repaint-loop
TUIs and easy for print-and-scroll CLIs.** timg, imgcat, `kitten icat`
work everywhere the protocols do, because they write once into the scroll
stream and never repaint. A TUI must integrate image height into its
layout model (reserve rows) — a rewrite-grade change (#54546's proposed
fix). Whether vfs's CLI can render inline is therefore decided by its
*rendering architecture*, not by protocol support.

## 6. The mirror of Jupyter: one canonical text form + negotiated riches

Jupyter's display model (mime bundles: kernel emits
`{"image/png": ..., "text/plain": ...}`, the *frontend* selects the
richest representation it can render;
https://jupyter-client.readthedocs.io/en/stable/messaging.html#display-data)
is exactly what terminal-side rendering re-derives independently:

- The **producer** (verb/kernel) declares what the thing *is* (bytes +
  mime + name), never how to draw it.
- The **boundary** (frontend/CLI) owns a ladder of renderings and picks
  the best one the consumer can accept — after *asking* the consumer.
- `text/plain` is mandatory in Jupyter bundles for the same reason a
  placeholder line is mandatory here: some consumer will always be
  text-only, and that rung must be deterministic and always present.

Kitty's unicode placeholders make the same concession *inside* the
protocol: when the transport is text-only (tmux), the image degrades to
specially-styled text that a capable outer layer can re-inflate.

## 7. Lessons for vfs, numbered against the brief

- **(Q2, block vocabulary)** The human boundary needs the identical tuple
  the MCP boundary needs — bytes, mime, size, name/path — and nothing
  more. All three terminal protocols consume base64+format; MCP image
  blocks consume base64+mimeType. One media block shape feeds both
  projections mechanically. Dimensions (w/h) are worth carrying if cheap:
  raw-pixel protocols (sixel, kitty f=24/32) and TUI row-reservation both
  want them.

- **(Q6, the stdout rule — the core lesson)** Every mature tool has ONE
  always-available text rung plus optional richer renderings negotiated
  per terminal. vfs should define one **canonical placeholder text form**
  (path + mime + byte size + description) as the *only* thing the text
  projection ever emits for media, and treat inline graphics as a
  CLI-boundary *enhancement* selected by tty negotiation — never as a
  property of the Result. This is Jupyter's frontend-selects model with
  the placeholder playing `text/plain`. Base64 in a text stream is worse
  than useless on the human side too: it is thousands of lines of noise
  that also breaks pagers.

- **(Q5, budgets)** The terminal side independently reinvented vfs's
  boundedness doctrine: kitty chunks APC at 4096 B, iTerm2 grew a
  multipart mode for tmux's sequence cap, WezTerm caps image pixels.
  Any media pipeline must chunk by declared per-consumer budgets — the
  same shape as `membership_budget`/`chunked()` in the database backend.
  Also: rendering is a *pull* decision made at the boundary after
  negotiation, which matches the brief's elide-with-placeholder,
  media-on-request default.

- **(Q4, ordering)** Terminal graphics are strictly stream-ordered — an
  image occupies rows at the point in the scroll where its escape was
  emitted, exactly the "figure appears in place" property the brief wants
  from MCP content arrays. The Claude Code failure shows what breaks it:
  a renderer that regenerates output from a lossy (text-only) model of
  the transcript loses the images. Order must live in the representation,
  not be reconstructed.

- **(Q1, where blocks live)** Terminal evidence favors *projection-time
  rendering over stored renderings*: no tool stores sixel or APC bytes;
  all store the source image and render at the boundary for the consumer
  actually present. Supports keeping Result media as source bytes/refs +
  mime, with each projection (text, MCP, terminal-graphics) deriving its
  own form.

- **(Q7, mime reality)** Terminals are *more* permissive than model APIs
  (iTerm2 renders "any format the emulator decodes"; kitty f=100 is
  PNG-only, raw modes take anything decodable sender-side). So mime
  passthrough with boundary-specific narrowing is the working pattern:
  keep the true mime on the block; each boundary decides render vs
  placeholder from its own accept-list.

- **(Feasibility of vfs CLI inline rendering)** High, *conditional on
  architecture*. If the vfs CLI is print-and-scroll (write result, exit —
  like timg/icat), inline media is a contained feature: on `isatty`, run
  the query ladder (kitty `a=q` → DA1 sixel bit → `TERM_PROGRAM` env
  fallback, all with timeouts), then emit kitty-APC / OSC 1337 / sixel /
  chafa-style unicode blocks / placeholder, in that order of preference.
  kitty+Ghostty+WezTerm+Konsole covers most developer terminals via the
  kitty protocol alone; sixel catches xterm/foot/mlterm/VS Code; the
  block+placeholder rungs cover Alacritty, Windows Terminal, pipes, CI.
  If the CLI becomes a repaint-loop TUI, inline images become a layout
  feature (row reservation, scrollback re-render fidelity) — the exact
  wall Claude Code hit and has not shipped past as of 2026-07. tmux
  should be documented as degraded (placeholder or sixel-if-compiled)
  rather than fought.

- **(Q8, executed-code output)** Same boundary logic: a matplotlib PNG
  from the sandbox is source bytes + mime in a typed block; whether it
  becomes an MCP image block, a kitty APC, or a placeholder line is
  decided per consumer at projection time. No layer below the boundary
  should ever pick an encoding.

## 8. Bearing on the "break from Unix" stance

Terminal-side evidence *supports* the stance, from the opposite shore:

1. Even the maximally-Unix world of terminal emulators concluded that raw
   text streams cannot carry media — all three protocols are typed,
   framed envelopes (control keys + mime/format + base64) smuggled
   through the text channel. The "content block" already exists at the
   human boundary; it is just spelled in escape sequences.
2. The pain of that smuggling (tmux eating sequences, TUIs sanitizing
   them, chunk caps, detection round-trips) is precisely the cost of NOT
   having a typed channel — an argument for vfs keeping blocks typed
   end-to-end and only encoding at the last boundary.
3. The stance's "still FEELS like a CLI" half is validated by timg/icat:
   a text-first CLI with negotiated media enhancement needs no ceremony —
   the user runs `read chart.png`, and the boundary decides between
   pixels and a placeholder. The one non-negotiable is the deterministic
   placeholder rung; everything above it is progressive enhancement.

## Sources

- https://sw.kovidgoyal.net/kitty/graphics-protocol/
- https://iterm2.com/documentation-images.html
- https://www.arewesixelyet.com/
- https://vt100.net/docs/vt510-rm/DA1.html
- https://github.com/anthropics/claude-code/issues/2266
- https://github.com/anthropics/claude-code/issues/54546
- https://github.com/anthropics/claude-code/issues/29254 (and dupes
  #35893, #36476, #17044)
- https://github.com/hzeller/timg
- https://hpjansson.org/chafa/
- https://github.com/ranger/ranger/wiki/Image-Previews
- https://github.com/kovidgoyal/kitty/discussions/4021
- https://github.com/tmux/tmux/issues/4902
- https://tmuxai.dev/tmux-allow-passthrough/
- https://terminfo.dev/extensions/kitty-graphics-protocol
- https://x.com/mitchellh/status/2041253090205249584
- https://blessed.readthedocs.io/en/latest/terminal.html
- https://vtdn.dev/docs/dcs/xtversion/
- https://jupyter-client.readthedocs.io/en/stable/messaging.html#display-data
