> **Provenance.** Moved from `vfs-app/` on 2026-07-03; kept as design history.
> This as-built handoff predates later changes: sections describing the
> TerminalTape/Values homepage components and the Topbar "pill nav", and some
> `clamp()` values, no longer match the code.

# vfs.dev · design & brand handoff

A complete description of what is currently shipping at `vfs-app/`. A designer
should be able to read this top-to-bottom and reconstruct the site faithfully
in Figma (or rebuild it in any framework) before iterating.

This document describes **the current implementation** — not aspirations. For
the open recommendations / direction-of-travel, see the sibling
`design-recommendation.md`. The two are meant to be read together: this one is
the as-built spec, that one is the next-pass intent.

Everything described here is implemented in:

- `vfs-app/` — the production site (React 19 + Vite + Tailwind v4 + a small
  shadcn/ui surface, deployed at vfs.dev).
- `vfs-brand/` — a sibling lookbook (Bun + React, served at `localhost:3000`)
  that holds the brand exploration the production site is derived from. The
  active brand world is **Pluto · Protocol**; the others are vestigial.

---

## 1 · Brand essence

### 1.1 What vfs is

> **vfs · One Namespace for Enterprise-Scale Context Engineering.**
> Mount data, tools, and retrieval systems behind one virtual file system so
> agents can search, traverse, and act across enterprise context.

- Domain: `vfs.dev`
- Stage: **alpha** (target milestone `2026-Q2`)
- License: Apache 2.0
- Tagline (footer / fallback): *"The Context Layer for Enterprise Agents."*

The product story has three load-bearing claims, all visible in copy:

1. **Everything is a file** — Unix-style namespace over heterogeneous
   enterprise data.
2. **One result envelope** — every operation returns a `VFSResult`; results
   support set algebra (`&`, `|`, `-`).
3. **Composable Unix verbs** — `grep | nbr | pagerank | top` over mounted
   stores, the same way an LLM was already trained to use a shell.

These three claims drive the homepage, the about page, and the terminal REPL.
A redesign must preserve them — the visual language exists to serve them.

### 1.2 Brand world: **Pluto · Protocol**

Named after Pluto (the ninth planet) in homage to **Plan 9 from Bell Labs**,
the distributed OS whose central claim was *"everything is a file"* — the same
claim vfs makes.

Mood:

- **Plan 9 / instrument / spec sheet.** Not a SaaS landing page.
- Industrial, schematic, monochrome with a single saturated wire.
- **No** Vercel-school dark-mesh hero, **no** purple "AI-era" gradients, **no**
  rounded SaaS cards.
- The site should look like an RFC, an engineering datasheet, or a Bell Labs
  monograph — rendered in the browser.

### 1.3 Voice

A four-row "good vs. bad" guide already lives in `vfs-brand/src/directions/Protocol.tsx`.
Replicating it here so it survives the brand repo:

| ✅ Good (RFC-2119, declarative) | ❌ Bad (SaaS rhetoric) |
| --- | --- |
| "A vfs server MUST implement read, write, list, stat." | "VFS empowers your agents to seamlessly orchestrate retrieval." |
| "Capability negotiation happens at initialize. No probing." | "Our intelligent platform auto-detects what your data needs." |
| "Entry carries path, version, content_hash, size. Nothing else is identity." | "VFS uses advanced AI to understand your data relationships." |
| "curl vfs.dev \| sh — the homepage is the spec." | "Book a demo to unlock the power of agentic retrieval." |

Rules of thumb:

- Lowercase wherever possible (`vfs`, `alpha`, `apache 2.0`, nav labels).
- Mono uppercase with wide tracking for **labels** only.
- Use code voice (`/enterprise/auth.py`, `VFSResult`, `if_version`) instead of
  marketing nouns.
- Never use "AI-native", "intelligent", "seamless", "unlock", or "demo".

---

## 2 · Color system

The single source of truth is `src/index.css`. All values flow through CSS
custom properties so light/dark are toggled by adding `.dark` to `<html>`.

### 2.1 Light mode — *paper*

| Token | Hex | Role |
| --- | --- | --- |
| `--bg` | `#f1f1ee` | **Frost** — page background ("paper") |
| `--card` | `#e4e4df` | **Plain** — raised surface |
| `--card-strong` | `#0f1012` | inverse slab (used for code samples / install button) |
| `--fg` | `#0b0b0d` | **Night** — body ink |
| `--accent` | `#2f58cf` | **Cobalt** — the only saturated pigment |
| `--pressed` | `#183988` | **Indigo** — activated/hover states |
| `--ok` | `#3d7d3f` | **Charon** — status only |
| `--muted` | `rgba(11,11,13,0.70)` | secondary text |
| `--quiet` | `rgba(11,11,13,0.46)` | tertiary text / labels |
| `--rule` | `rgba(11,11,13,0.14)` | hairline borders |

### 2.2 Dark mode — *ink*

| Token | Hex | Role |
| --- | --- | --- |
| `--bg` | `#0f1012` | **Night** — paper in ink mode |
| `--card` | `#18191c` | **Shadow** — raised surface |
| `--card-strong` | `#050507` | deepest slab |
| `--fg` | `#e7e7e8` | **Ice** — body ink |
| `--accent` | `#4d7cf3` | **Cobalt** (lifted to hold contrast in ink) |
| `--pressed` | `#2c54be` | **Azurite** |
| `--ok` | `#86c17a` | **Charon** (lifted for ink) |
| `--muted` | `rgba(231,231,232,0.70)` | |
| `--quiet` | `rgba(231,231,232,0.46)` | |
| `--rule` | `rgba(231,231,232,0.14)` | |

### 2.3 Rules

- **Cobalt is the only saturated pigment.** It appears only as `signal` or
  `pressed` — never as a surface, label, or rule color. It is the "wire" the
  eye is allowed to find first.
- All grayscale is fully desaturated. No warmth, no tint, no ornament.
- Hover/highlight states use `color-mix(in oklab, var(--accent) 4%–10%, var(--bg))`
  rather than a separate hover token — keeps the system tight.
- `::selection` is `color-mix(in oklab, var(--accent) 70%, transparent)` with
  `color: var(--bg)` (a cobalt halo against ink/paper).

### 2.4 Theme toggle

- Three modes: **light**, **dark**, **system** (default `system`).
- Toggle: top-right dropdown with sun/moon/monitor icons; also keyboard
  shortcut **`d`** (cycles dark ↔ light, ignoring text inputs).
- Stored in `localStorage["theme"]`.
- HTML `meta[name=theme-color]` is set per scheme:
  - light → `#f1f1ee`
  - dark → `#0f1012`

---

## 3 · Typography

Four variable fonts, loaded via `@fontsource-variable/*`:

| Token | Family | Used for |
| --- | --- | --- |
| `--font-brand` | **Saira Variable** | The wordmark "vfs" and large hero headlines. |
| `--font-display` | **Space Grotesk Variable** | Section titles, taglines, value-card titles, blog item titles. |
| `--font-body` | **Geist Variable** | Body prose. Default `<html>` font. |
| `--font-mono` | **JetBrains Mono Variable** | Labels, code, install chip, terminal output, footer listing — every fact-bearing surface. |

Tailwind utility shortcuts: `font-brand`, `font-display`, `font-sans`
(= body), `font-mono`. There are also CSS classes `.brand`, `.display`, `.mono`
for use inside markup that's not in JSX.

Body opens with `font-feature-settings: "ss01", "cv11"` for Geist's preferred
stylistic + character variants.

### 3.1 Type scale (concrete sizes)

These are exactly what the site renders today; reproduce them faithfully if
recreating in Figma.

**Hero · headline** (`.vfs-hero-headline`)
- font: Saira (brand), weight 500, letter-spacing −0.022em
- size: `clamp(40px, 5.6vw, 88px)`, line-height 1.02
- max width: 18ch
- color: `--fg`

**Hero · lede** (`.vfs-hero-lede`)
- font: Space Grotesk (display), weight 300, letter-spacing −0.005em
- size: `clamp(16px, 1.4vw, 20px)`, line-height 1.55
- max width: 56ch
- color: `--muted`

**Hero · mark row** (small "● vfs ……… v0.0.22" line above the headline)
- mono, 11px, tracking 0.22em, uppercase, color `--quiet`
- a 9×9px solid cobalt square sigil, then `vfs` in **Saira 14px / 600 / lowercase**, then version flush right (10px / 0.26em)
- bottom-bordered with a 1px hairline `--rule`

**Section label** (`.vfs-section-label`)
- mono, 10px, tracking 0.28em, uppercase, color `--quiet`
- prefixed by a 32×1px hairline `currentColor` (`::before`)
- bottom margin 36px

**Subsection tagline** (the left column of every numbered section on the home page)
- font: Space Grotesk, weight 500, letter-spacing −0.012em
- size: `clamp(22px, 2.2vw, 30px)`, line-height 1.25 (some sections bump to `clamp(28px, 3vw, 40px)` / 1.1)

**Body prose**
- font: Geist
- size: 15px (occasionally 14px for compact rows), line-height 1.6 – 1.7
- color: `--muted`
- max-width: ~`max-w-prose` (≈ 65ch)

**Page-title supersize** (Blog `.vfs-blog-title`, Terminal `.vfs-term-title`, About lede, NotFound)
- font: Saira, weight 500, letter-spacing −0.01em
- size: `clamp(56px, 9vw, 128px)` (Blog) — this is the largest type on the site
- line-height 0.88–0.92

**Mono labels everywhere else**
- 10px / 0.28em / uppercase / color `--quiet` is the dominant label flavor.
- 11px / 0.22em / uppercase appears on slightly larger labels (mark row, integrations).
- 9px / 0.32em / uppercase is reserved for the spec-strip cell labels (the smallest label in the system).

### 3.2 Why four fonts

The split is deliberate:

- **Saira** carries identity — the wordmark, hero, page titles. It is the only
  type the user remembers seeing.
- **Space Grotesk** carries hierarchy — section titles and taglines.
- **Geist** carries information density — readable prose at 15px.
- **JetBrains Mono** carries factuality — anything claiming to be a fact, a
  spec, or a path is mono.

A redesigner can collapse Saira ↔ Space Grotesk in theory (the `vfs-brand`
exploration uses Space Grotesk for both) but the current production app
**uses Saira for `--font-brand`**. Keep the four-stack unless the brief
explicitly asks for consolidation.

---

## 4 · Information architecture

### 4.1 Routes (`src/App.tsx`)

| Path | File | Purpose |
| --- | --- | --- |
| `/` | `routes/Home.tsx` | Hero + 6 numbered sections + footer. The pitch. |
| `/about` | `routes/About.tsx` | Thesis, three core components, set algebra demo, backends/clients tables, status. |
| `/blog` | `routes/Blog.tsx` | Stub list of three "coming soon" posts. |
| `/terminal` | `routes/Terminal.tsx` | Live in-browser REPL over an in-memory fake filesystem. |
| `*` | `routes/NotFound.tsx` | `stat: <path>: No such entry` + cobalt-underlined link back. |

Every page is wrapped in `RootLayout` (`components/layout/RootLayout.tsx`)
which renders `<Topbar />`, `<Outlet />`, `<FilesystemFooter />`, and
react-router's `<ScrollRestoration />`.

### 4.2 The "filesystem" metaphor in the IA

This is the **most important brand decision** and must be preserved.

- The footer is not a sitemap, it's a directory listing — a fake `curl
  vfs.dev | sh` followed by an `ls`-style block of paths and descriptions
  (`src/lib/site.ts` · `FS_LISTING`).
- The 404 page reads `stat: /nope: No such entry` and offers `cd /` as the
  recovery action.
- Section labels are numbered like a spec: `vfs / 01 · on-wire`, `vfs / 02 ·
  integrations`, `about / 03 · composable results`.
- The `/terminal` route is a real REPL with `ls`, `cd`, `cat`, `tree`, `stat`,
  `pwd`, `clear`, `help`, `whoami`, `echo`. It uses a deterministic in-memory
  tree (`src/lib/fakeFs.ts`) so every visitor sees the same paths.

A redesigner is welcome to refresh the visual treatment of the footer
listing, but the *behavior* — site nav as a directory — should stay.

---

## 5 · Layout system

### 5.1 Page chrome

- **Sticky topbar** (`.vfs-chrome`) at the top of every route. Translucent
  paper at 82% with a 14px blur, hairline bottom rule.
- **No sidebar.** Every layout is single-column with internal grids.
- **Filesystem footer** at the bottom of every route (a 2-column directory
  listing on desktop, single column on mobile).
- **Page gutter:** `8vw` left/right is the dominant horizontal padding token —
  used by hero, sections, footer, terminal, blog. Reproduce this rather than a
  fixed max-width.

### 5.2 Section primitive

`<Section label="vfs / 01 · on-wire" tight={false}>` (`components/brand/Section.tsx`).

- Padding: `112px 8vw` (or `72px 8vw` when `tight`).
- Bottom border: 1px `--rule` (suppressed on the last section).
- Renders an optional **Section label** (`.vfs-section-label`) above the
  children — the one with the 32×1px leading rule.
- Children are unconstrained; most sections use a 1fr / 2.4fr grid for a
  short tagline on the left and a paragraph + artifact on the right (see
  `Home.tsx` for the recurring pattern).

### 5.3 Grid conventions

- "Short claim ↔ long support" uses `grid-template-columns: minmax(0, 1fr)
  minmax(0, 2.4fr)` (or 1fr / 1.6fr for hero-adjacent grids). Always 12 columns
  worth of content; left side is the loud claim, right side is the soft prose
  + artifact.
- Card grids (Values, Integrations) use `repeat(auto-fit, minmax(220–250px,
  1fr))` with a 1px hairline grid (no inner gap; cells share borders).

### 5.4 Hero stage

The hero is its own full-bleed primitive (`SpecHero`), not a `Section`. It
sits at `padding: 40px 8vw 56px`, min-height 88vh, and uses a 1.1fr / 1fr
grid: text on the left, code sample on the right. Below 980px it stacks.

The hero ends with a centered "install chip" — see Component inventory.

---

## 6 · Component inventory

All brand components live in `src/components/brand/`. A few use shadcn/ui
primitives (Card, Badge, Separator, Input, ScrollArea, DropdownMenu) but the
visual language is overridden by `src/styles/brand.css` so the shadcn defaults
(rounded corners, soft shadows) do not bleed through.

> **Square-corner rule:** `--radius` is `0.125rem` (2px). Most surfaces use
> `border-radius: 2px` or `0`. Pills exist only on the topbar nav and the
> theme/icon buttons. **Do not introduce new rounded-card vocabulary.**

### 6.1 `SpecHero`

`components/brand/SpecHero.tsx` · CSS `.vfs-hero*`.

Slots:

- `topLeft`, `topRight` — small mono cells in the very top row (currently
  unused on `/`, but the hook is there).
- `mark`, `version` — the wordmark row (small sigil + lowercase "vfs" + version flush right). Currently unused on `/` because `headline` carries identity instead, but available.
- **`headline`** — the main display line. Saira, ~88px desktop.
- **`lede`** — the supporting paragraph beneath the headline.
- `side` — small mono metadata under the lede (dashed top rule). Currently unused on `/`.
- **`code`** — the right-column sample (a `<Sample />` block).
- **`install`** — `{ cmd: string }`; renders the centered install button.

Install button (`.vfs-install-btn`):

- Width `min(420px, 75%)`, centered.
- Inverse slab: `--card-strong` on `--bg`. Cobalt `$` sigil.
- 18×36px padding, 2px radius.
- 1px translateY on hover; 3px translateY shadow on hover.
- Click writes the command (`pip install vfs-py` by default) to clipboard and
  flashes the background to cobalt for 1.2 s with `is-copied`.

### 6.2 `Sample`

`components/brand/Sample.tsx` · CSS `.vfs-sample*`.

A code block dressed as a spec figure, used everywhere on every page.

- Outer: 1px hairline border on `--card-strong` slab, 3px radius.
- Header bar (`.vfs-sample-head`): 13×18px, mono 10px / 0.22em / uppercase,
  two cells (left = label, right = kind), bottom 1px rule.
- Body (`.vfs-sample-body`): mono 13px / 1.7, 24×26px padding, `white-space:
  pre`, horizontal scroll allowed.
- Color tokens (used as `<span class>` inside children):
  - `.prompt` — cobalt, `user-select: none`.
  - `.comment` — italicized, dimmed.
  - `.path` — bright (`--bg` on the slab).
  - `.out` — dimmer.
  - `.hit` — cobalt highlight on a 25% mix.

Sample bodies in the hero shrink to 12px / 1.65 / 18×20px padding.

### 6.3 `SpecStrip`

`components/brand/SpecStrip.tsx` · CSS `.vfs-spec-strip*`.

A row of mono fact cells that sits directly under the hero. Reads like a
fact-sheet, not a marketing band.

- Six cells: tests · coverage · backends · retrieval · runtime · license.
- Each cell: 22×24px padding, vertical stack of label (9px / 0.32em / uppercase
  / quiet) over value (mono 14px / 500 / uppercase).
- The first two cells (`tests`, `coverage`) have their **value in cobalt** —
  the only saturated points in the strip. Everything else is `--fg`.
- 1px right border between cells; 1px top + bottom rules to frame the band.
- Wraps to two columns under 720px.

Data lives at `SITE.metrics` in `src/lib/site.ts`.

### 6.4 `IntegrationsGrid`

`components/brand/IntegrationsGrid.tsx` · CSS `.vfs-integrations*`.

A plain-text ecosystem grid. Six groups: backends, retrieval, graph, agents,
embeddings, interfaces. **No logos.**

- 1px outer hairline; cells share 1px borders.
- Each cell has a small head: a cobalt mono `./` marker, then the group name
  in mono 11px / 0.24em / uppercase, then a 1px rule.
- Items are mono 13px with a `·` dot column, dim-color text.
- Hover: cell background mixes 4% cobalt into paper.

### 6.5 `Positioning`

`components/brand/Positioning.tsx` · CSS `.vfs-positioning*-table`.

The "If you already use… / vfs adds…" comparison.

- Two-column table (~0.95fr / 1.7fr), 1px outer border.
- Header row uses a faint 5%-fg fill, mono 10px / 0.28em labels.
- Each row:
  - Left cell: mono 14px, prefixed with a cobalt `↳` arrow; "if you already
    use a vector database".
  - Right cell: Space Grotesk 15–17px, "vfs adds paths, CRUD, …"
- Hover: row mixes 4% cobalt into paper.
- Below 760px: the head hides, rows stack, left cell becomes a soft fg-tinted
  cap with a dashed bottom border.

### 6.6 `TerminalTape`

`components/brand/TerminalTape.tsx` · CSS `.vfs-tape*`.

A **non-animated** scripted preview of `/terminal` rendered as an inverse
slab. The point is trustworthiness: what's drawn is what `vfs` actually does.

Layout, top to bottom:

1. Bar (`.vfs-tape-bar`) — mono 10px label "tty / preview" left, "vfs ·
   noninteractive" right.
2. Body — three command lines using `$` prompts in cobalt, then a hairline
   dashed rule, then three result rows: `path<TAB>score`. Scores are cobalt,
   tabular-nums.
3. CTA bar (`.vfs-tape-cta`) — flush right, a small mono link "Open the REPL
   →" with a 1px translucent border. Hover lifts to cobalt.

### 6.7 `Values`

`components/brand/Values.tsx` · CSS `.vfs-value*`.

Card grid for principles. Currently used on the homepage with four items
(Agent-first, Everything is a file, Small composable tools, Bring your own
infra).

- Grid: `repeat(auto-fit, minmax(250px, 1fr))`, 16px gap.
- Each card: `--card` background, 1px `--rule` border, **no radius**, 28×24px
  padding.
- Top row: a mono label "CAP. 01", "CAP. 02"…
- Title: Space Grotesk 22px / 500.
- Body: Geist 14px / 1.6 / `--muted`.
- Hover: border mixes 50% cobalt into rule.

### 6.8 `Section`

Already covered (see §5.2). Trivial wrapper, but every section on every page
uses it.

### 6.9 Topbar (`components/layout/Topbar.tsx`)

Three columns:

- **Left** — `vfs<dot>` wordmark in Saira 22px, the dot is a 0.18×0.18em cobalt
  filled circle, slightly raised. It's a `<NavLink>` to `/`.
- **Middle** — pill nav. A 1px hairline rounded-full container with 4 inline
  links (home / about / blog / terminal). Active state is solid `--fg` background
  with `--bg` text. Inactive is 55% fg → 100% on hover.
- **Right** — three controls in a row:
  - `alpha · v0.0.22` (latest GitHub release, links to release page; hidden
    on mobile).
  - GitHub icon link in a 30×30px hairline circle.
  - Theme dropdown trigger in the same 30×30px hairline circle.

The version comes from `useLatestRelease()` (`src/hooks/useLatestRelease.ts`),
which calls `https://api.github.com/repos/ClayGendron/vfs/releases/latest` and
falls back to `SITE.versionFallback` ("v0.0.22").

### 6.10 Filesystem footer (`components/layout/FilesystemFooter.tsx`)

Two-column grid (1fr / 1.3fr).

- Left: a Space Grotesk 22–30px lede line with a cobalt-italic word —
  *"The homepage **is** the filesystem."* — and a sub-paragraph.
- Right: a `<pre>` directory listing styled like a real `ls -l` plus a
  fake `$ curl vfs.dev | sh` prompt at the top and a blinking-cursor `_` at
  the bottom. Paths link to internal routes (`/about`, `/blog`, `/terminal`)
  and external (GitHub).
- Bottom baseline (full-width): mono 10px labels — `© vfs.dev · apache 2.0`
  on the left, `built with vfs · served from a filesystem` on the right.

The listing uses fixed-width left padding (`pad(d.path, col)`) so the
descriptions line up like a real terminal listing. Don't simulate this with
CSS columns — it has to be character-aligned to read right.

### 6.11 Terminal (`routes/Terminal.tsx`)

A working REPL implemented in React.

- Title: "terminal" in Saira `clamp(44px, 7vw, 88px)`.
- Right side of header: three mono lines — *live repl · in-memory vfs* /
  *mount · root /* / *no network — every byte is local*.
- Shell: 1px-rule-bordered slab (`--card-strong`), min-height 520px.
  - Status bar: `$ vfs --repl` left, `cwd /<path>` right.
  - Body: scrollable, prompts in cobalt, paths in dim-bg, errors in
    `#ff8a7a`, ok in `--ok`.
  - Input row: cobalt prompt + invisible `<input>` + a 7×14px blinking
    cursor (1.1s steps animation).
- Up/Down arrows walk command history; `cmd/ctrl+L` clears.
- All commands operate on the in-memory tree from `src/lib/fakeFs.ts`. There
  is **no network**.

### 6.12 Blog (`routes/Blog.tsx`)

- Page title "blog" in Saira `clamp(56px, 9vw, 128px)` — the largest type on
  the site.
- Three stub items, marked `aria-disabled` and titled "Coming soon".
- Item layout: a 120px mono date column / Space Grotesk title + Geist sub /
  mono CTA column on the right (`6 min · soon`).
- Hover: shifts the row 8px to the right and tints the title cobalt.

### 6.13 About (`routes/About.tsx`)

Five sections, each a `<Section>`:

1. **Lede** — a giant Saira "The context\nlayer." with a cobalt period, then
   the description and two prose paragraphs.
2. **Core components** — three cells (file system / retrieval / graph) sharing
   1px hairline rules; each cell has a "01/02/03" mono cap.
3. **Composable results** — short tagline + a `<Sample>` showing set-algebra
   over `VFSResult`.
4. **Backends · clients** — two parallel definition lists with hairline-ruled
   rows; left is backends, right is clients.
5. **Status · roadmap** — three squared-off Badges (alpha / target / apache),
   a body paragraph with bolded test count, a Separator, then a 2-col grid of
   roadmap items each prefixed by a cobalt `→`.

Note `Badge` is used with `rounded-none` everywhere — square corners are
non-negotiable.

### 6.14 NotFound (`routes/NotFound.tsx`)

- Mono cap "404 · NO SUCH ENTRY".
- Saira `clamp(72px, 12vw, 160px)` "/404" title.
- A code-styled `stat: <pathname>: No such entry` line.
- Recovery: an underlined cobalt `cd /` link.

---

## 7 · Iconography

- **@phosphor-icons/react**, weight `regular`, size 4 (≈16px).
- Used in: GitHub link, theme dropdown (Sun / Moon / Monitor), and theme
  dropdown items.
- Icons sit inside 30×30px hairline circles in the topbar; otherwise they're
  inline at body size.

A redesigner can swap to Lucide or another set without disrupting layout, but
**must preserve the regular weight and the hairline circle frame** for parity
with the chrome density.

---

## 8 · Imagery, motion, ornament

There is **none**. By design.

- No photography, no illustration, no abstract gradients, no mesh, no logos
  (other than the GitHub mark in the topbar).
- The only motion in the system:
  - Theme transitions are temporarily disabled while `.dark` is toggled (see
    `disableTransitionsTemporarily()` in `theme-provider.tsx`) so light/dark
    is an instant swap, not a fade.
  - Install button: 0.15s transform.
  - Cards (Value, Integration, Positioning row): 0.2s background/border.
  - Terminal cursor: 1.1s steps blink.
  - Tape CTA arrow: 0.18s `translateX(3px)` on hover.
- No scroll-jacking, no parallax, no reveal animations.

Keeping motion this thin is a brand choice. Adding any motion-driven hero or
"AI shimmer" treatment will fight the spec-sheet identity.

---

## 9 · Content reference

### 9.1 The `SITE` object (`src/lib/site.ts`)

The single source of truth for all chrome copy. Reproduced here so a designer
working in Figma has exact strings:

```ts
SITE = {
  name: "vfs",
  tagline: "The Context Layer for Enterprise Agents.",
  headline: "One Namespace for Enterprise-Scale Context Engineering.",
  description:
    "Mount data, tools, and retrieval systems behind one virtual file system " +
    "so agents can search, traverse, and act across enterprise context.",
  domain: "vfs.dev",
  github: "https://github.com/ClayGendron/vfs",
  pypi: "https://pypi.org/project/vfs-py/",
  stage: "alpha",
  milestone: "2026-Q2",
  versionFallback: "v0.0.22",
  install: { python: "pip install vfs-py", … },
  metrics: [ tests / coverage / backends / retrieval / runtime / license ],
  integrations: [ backends, retrieval, graph, agents, embeddings, interfaces ],
  positioning: [ vector DB / fsspec / retrievers / graph DB rows ],
}
```

### 9.2 Homepage section order (`routes/Home.tsx`)

1. Hero (headline + lede + Sample + install chip)
2. **Spec strip** — six mono fact cells
3. **`vfs / 01 · on-wire`** — "One result contract. One method per verb." + a
   two-column `<Sample>` showing async client + result envelope.
4. **`vfs / 02 · integrations`** — "Mount the stack you already run." +
   `IntegrationsGrid`.
5. **`vfs / 03 · why vfs?`** — "Not a vector DB. Not a retriever. A namespace." +
   `Positioning`.
6. **`vfs / 04 · the interface agents already know`** — "grep. neighborhood.
   pagerank." + `TerminalTape`.
7. **`vfs / 05 · principles`** — `Values` (Agent-first, Everything is a file,
   Small composable tools, Bring your own infra).
8. **`vfs / 06 · status`** *(tight)* — "alpha · v0.0.x", a paragraph about
   what's done and what's next, three CTA links (try the repl / read the thesis
   / source), and a `Sample` showing all install extras.

The "`vfs / NN · …`" labels live on every section. Section ordering matters
— see `design-recommendation.md` for the rationale (demo-first, principles
last).

---

## 10 · Tech reference (for whoever rebuilds it)

- **Build**: Vite 7, React 19, TypeScript ~5.9. `bun dev` (or `vite`).
- **Styling**: Tailwind v4 (`@tailwindcss/vite`) plus `tw-animate-css`. The
  `@theme inline { … }` block in `index.css` binds Tailwind utilities to brand
  tokens (so `bg-paper`, `text-ink`, `text-signal` all work).
- **shadcn/ui**: only Card, Badge, Separator, Input, ScrollArea, DropdownMenu,
  Tooltip, Sonner, Button are installed (`components.json`). Most are restyled
  to look square and inverted.
- **Routing**: react-router-dom 7. `BrowserRouter` (not Hash), with
  `<ScrollRestoration />` so back/forward feels right.
- **State**: nothing global beyond the theme provider and route state.
- **Network**: a single `fetch` to `api.github.com` for the latest release tag
  (cached in component state, falls back to `versionFallback`).
- **No CMS, no MDX yet.** Blog posts are stubs in `Blog.tsx`. Adding a real
  MDX/markdown pipeline is open work — not part of the brand.

---

## 11 · How to recreate this in Figma

Suggested page order for the Figma file:

1. **Brand foundations** — palette (light + dark side-by-side), type stack
   (the four families with samples at the sizes in §3.1), iconography rules,
   motion rules, voice grid.
2. **Components** — one frame per brand component in §6, each rendered at
   ~1440px wide with annotations:
   - SpecHero (with and without `headline`/`mark`/`side` slots).
   - Sample (full size, hero-shrink size).
   - SpecStrip (desktop + 2-col mobile).
   - IntegrationsGrid (auto-fit).
   - Positioning (table + stacked mobile).
   - TerminalTape.
   - Values (4 cards).
   - Topbar.
   - FilesystemFooter.
   - Section primitive (label + body grid).
3. **Pages** — full-page boards at 1440px and 390px:
   - Home (with all 8 stops in §9.2).
   - About.
   - Blog.
   - Terminal.
   - 404.
4. **Both modes** — duplicate every page board into a Dark column. Token swap
   only; nothing else changes.

The CSS in `src/index.css` and `src/styles/brand.css` is the canonical
reference for any pixel value not captured here. If something in Figma
disagrees with `brand.css`, **trust `brand.css`** — it's what ships.

---

## 12 · What to keep when iterating

These are the brand-defining choices. A redesign that drops any of them
breaks the system:

1. **Pluto palette** — desaturated grayscale, single cobalt wire. Cobalt only
   in signal/pressed roles.
2. **Square corners** (2px max). No SaaS cards.
3. **Hairline rules** at `--rule` (14% ink) — these are the dominant
   separator, not gaps or shadows.
4. **Mono labels** at 9–11px, 0.22–0.32em tracking, uppercase, `--quiet`.
   The site's signature texture.
5. **`vfs / NN · …` section numbering** — reads like a spec, not a brochure.
6. **Filesystem-as-IA** — the footer is a directory listing, the 404 is a
   `stat:` error, sections are numbered, `/terminal` is real.
7. **Code in the hero** — a real, pasteable Python sample is the first
   visible artifact.
8. **No marketing chrome** — no demo CTA, no "trusted by" logos, no enterprise
   testimonials. Alpha is stated honestly.

## 13 · What's open for change

These are deliberately not load-bearing and a designer can revisit:

- **Pill nav** in the topbar — currently full-rounded, contrasting with
  everything else. Either commit to the pill (and add a second pill somewhere
  to balance it) or square it off to match.
- **Blog list visual** — the 120px date column / hover-shift pattern is
  workable but ordinary; the brand could push harder here.
- **Terminal page** — the title is huge but the right-column meta is small;
  re-balance is welcome.
- **About page** — the 5-section structure is fine but section 4 (backends ·
  clients) is the densest text on the site and could become a cleaner schematic.
- **Iconography surface** — only a few icons are used today; if more enter
  the system, codify a weight/stroke standard before adding them.

The recommendation document
(`vfs-app/design-recommendation.md`) covers further direction-of-travel
decisions — read it after this one for the strategic context.

---

*End of handoff.*
