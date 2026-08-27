# Proposal: an Explanation page for paths in the VFS namespace

> **What this is.** A proposal — spine options and reasoning — for a Diátaxis
> *Explanation* covering `src/vfs/paths.py`. It does not ghostwrite the page.
> It names the one load-bearing decision, offers candidate spines, and sketches
> the skeleton for the recommended one. Per the coaching contract: the author
> writes; this flags and forces the choice.

---

## 0. Diagnosis (before any prose)

Two things are already true that constrain this page:

1. **`reference/metadata-paths.md` already owns the contract.** The
   `/.vfs/<endpoint>/__meta__/...` grammar — segment-by-segment, every reserved
   constant, every fixed invariant — is Reference's job and is already stubbed
   to the SQLite-file-format model. **This page must not restate the grammar.**
   The #1 failure mode here is conflation: an Explanation that quietly becomes a
   second, prose-shaped copy of the format table. If a sentence is *what the
   format is*, it belongs in reference; if it is *why the format is shaped this
   way*, it belongs here.

2. **`home.md` already planted the seed this page should pay off.** Core Idea #1
   is "everything is addressed by path"; the metadata-namespace section shows
   `chunks/`, `versions/`, `edges/` as paths "instead of being hidden behind
   side channels." That clause is an unpaid promise — it asserts the design
   without arguing it. **This Explanation is where that promise gets paid.**

So the page's job is narrow and real: make the *design argument* for why VFS
turned metadata into addressable paths and a validated path into a type —
naming the alternatives it rejected and their failure modes (the SQLite
"As An Application File Format" shape your framework already points at for the
explanation bucket).

---

## 1. The load-bearing decision: one page or two?

`paths.py` carries **two distinct convictions**, and they sit in different
places on the Diátaxis cognition axis:

- **The namespace conviction** — metadata is data *about* user content, and VFS
  reflects it into a parallel tree under `/.vfs` rather than inlining it as
  columns or hiding it behind an API. This is an argument about the **data
  model**.
- **The type conviction** — a path that has passed the gate (`VFSPath`) is a
  different *kind of thing* than the string a caller handed in. Validation
  happens once, at one chokepoint; everything downstream is safe by
  construction. This is an argument about the **code's safety discipline**
  (parse, don't validate).

They are related but not the same argument, and trying to make both on one page
risks the conflation failure above. **This is the decision to make before
writing a word.** Three ways to resolve it — see §3.

---

## 2. Candidate spines

Three theses the page (or pages) could be built around. Each optimizes for a
different thing.

### Spine A — "The path is the address; nothing hides behind it"
*Optimizes for: continuity with `home.md`'s everything-is-a-file thesis.*

The backbone: chunks, versions, and edges *could* have been columns on a row, a
side table, or a metadata API. VFS makes each one a path. Walk the rejected
alternatives and their failure modes (a side channel the agent can't `glob`; a
metadata API that doesn't compose with search). Land on the payoff already
claimed in `home.md`: because everything is a path, search output is graph
input — composition falls out of addressing.

### Spine B — "A validated path is a different type than a string"
*Optimizes for: the safety/correctness story (parse, don't validate).*

The backbone: `VFSPath` is a badge a string earns by passing one gate
(`resolve_path` → normalize once → validate → brand). Argue why this is a type
and not a convention or a scattering of `if`-checks: the alternative is every
router and storage call re-validating (and disagreeing), or trusting raw input
and routing a `/.vfs/../` traversal into storage. Name the deliberate seams —
normalization vs. validation vs. mutability vs. *permission* are four separate
concerns, and the page argues why collapsing any two is a bug.

### Spine C — "Two namespaces, one mirrored in the other"
*Optimizes for: the spatial mental model.*

The backbone: `/.vfs` is a reflection of user space, and metadata hangs off the
*reflected* path before crossing the `__meta__` boundary. Argue why reflected
rather than inlined; why out-edges are the canonical writable projection and
in-edges a derived read-only view of the same fact (one source of truth, two
ways to navigate to it). Risk: this is the spine most likely to slide into
restating the grammar — it has to stay on *why reflected*, not *what the
segments are*.

---

## 3. Recommendation

**Two pages, written in order — but only commit to the first now.**

- **Page 1 (write first): the namespace.** Spine **A as the thesis, Spine C as
  the mechanism that delivers it.** A says *why paths*; C says *how the tree is
  shaped to make that work*. Together they pay off the `home.md` promise and
  stay clear of `VFSPath`-the-type. Working title candidates:
  *"Why metadata is a path"* / *"Everything about a file is also a file."*

- **Page 2 (later, if it earns its place): the type.** Spine **B** as a
  standalone *parse-don't-validate* explanation. It's a genuinely separate
  argument and strong enough to stand alone, but it builds *on* Page 1 (you
  can't argue the gate's value until the reader believes paths are the
  interface). Defer it; don't force two pages today.

Why not one page fusing all three: A/C is about the data model, B is about code
discipline — different reader question ("how do I think about the namespace?"
vs. "why can I trust a path object?"). One page would serve neither cleanly.

If you'd rather ship a single page, fold B into one short section of Page 1 and
accept that it under-serves the type argument — flagging that tradeoff rather
than hiding it.

---

## 4. Proposed skeleton for Page 1 (headings + intent, no prose)

Stub-comment style per your Step 1 convention — the constraint stays in front
of the writer; delete the comments when the page is done.

```
<!--
DIÁTAXIS TYPE: Explanation (understanding-oriented)
THE RULE: Make the design argument. Name each rejected alternative and its
failure mode. Do NOT restate the format grammar — that is reference/metadata-paths.md.
Pays off the "instead of being hidden behind side channels" promise in home.md.
SOURCE: src/vfs/paths.py (module docstring + VFSPath + resolve_path rationale)
-->

# <title — Spine A>

## Metadata is data about a file — so it gets a path too
<!-- Thesis. The one sentence the page defends. Tie straight to home.md #1. -->

## The alternatives, and where they fail
<!-- Side channel / extra columns / metadata API. Each one's specific failure
mode for an AGENT: can't glob it, can't pipe it into graph, can't reason about
its place in the namespace. This is the SQLite-app-file-format move. -->

## A mirror, not an inline
<!-- Spine C as mechanism: why /.vfs reflects user space and metadata hangs off
the reflected path. Why reflected beats inlined. NO segment grammar here. -->

## One fact, two ways to reach it
<!-- Out-edge canonical + writable; in-edge derived + read-only. Why a single
source of truth projected both directions, not two stored facts. -->

## What this buys: search output is graph input
<!-- The payoff. Composition falls out of universal addressing. Land the thread
home.md opened. -->

## See also
<!-- Link reference/metadata-paths.md for the format; the (future) VFSPath
type page. Explanation links out, does not duplicate. -->
```

---

## 5. Raw material available from `paths.py` (for the writer)

Design *whys* present in the code, sorted by which spine they feed:

- **A / C (Page 1):** module docstring (the canonical mirror layout); the
  out-edge/in-edge split (`edge_out_path` canonical vs. `edge_in_path` inverse;
  `check_mutable_path` forbidding direct writes to inverse edges); metadata
  reflected under `/.vfs` before the `__meta__` boundary.
- **B (Page 2):** `VFSPath` docstring (the "badge," `str`-subclass so it binds
  into SQL/f-strings unchanged, badge deliberately not inherited on slicing);
  `resolve_path` as the single gate that never raises; `normalize_path` (pure,
  idempotent, single-pass) vs. `validate_path` (structure only) vs.
  `check_mutable_path` (grammar, *not* permission) — the four-concern
  separation is the spine of B.

Stays **out** (it's reference, not explanation): the segment grammar, the
`chunks/<version>/<name>` / `versions/<N>` / `edges/<dir>/<type>/<target>`
shapes, the forbidden-character set, length limits, the extensionless-files
list.

---

## 6. Generative questions (to pull the conviction into the prose)

An Explanation's argument has to be *yours*, not reconstructed from the code.
These are the questions whose answers become the sections:

1. What did you personally hit — in an agent loop or a real ingest — that made
   "metadata behind a side channel" unacceptable? (→ the failure-mode section)
2. Was there a version of VFS where metadata *was* columns or a side table?
   What broke? (→ the rejected-alternatives section; if it never existed, the
   argument is hypothetical and should say so honestly)
3. Why mirror under `/.vfs` rather than, say, a `.meta` suffix on the file's own
   path? What does the separate root buy? (→ the "mirror, not inline" section)
4. In-edges are derived, never written directly. What confusion or bug did that
   one-source-of-truth rule prevent? (→ "one fact, two ways")

---

## Next decision

**Pick the spine resolution in §3: two pages (recommended), or one fused page.**
That choice determines the title and whether the skeleton in §4 ships as-is or
absorbs a `VFSPath` section. Everything downstream waits on it.
