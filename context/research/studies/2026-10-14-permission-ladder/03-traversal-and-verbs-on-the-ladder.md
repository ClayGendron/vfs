# L3 — The walk, the search verbs and the write verbs on the expanded ladder

Researcher L3, 2026-10-14. Brief: `scratchpad/ladder/BRIEF.md`. Scope addition from Clay (via the coordinator): check every rule against Plan 9's permission model, with `repo:path:line` citations. Script: `scratchpad/ladder/l3_walk_examples.py`; full output: `scratchpad/ladder/l3_walk_examples.out`.

Evidence labels: **EXECUTED** (I ran it), **READ** (I read the code, doc or page and cite it), **INFERRED** (my reasoning). Anything else is `[NOT VERIFIED: why]`.

## Summary

Three rules carry the whole design, and each one has a Plan 9 answer beside it. **(1) Traverse on both endpoints:** a walk passes an edge only when the caller holds `list` on both its endpoints; a `list`-level node is returned bare and is passed, a `none`-level node cuts the walk. Plan 9 says the same about a path walk: each element needs execute on the directory being passed ("a walk in a directory is regarded as executing the directory, not reading it", `plan9:sys/man/5/0intro:562-564`; `plan9:sys/src/cmd/ramfs.c:353-357` checks `Pexec` per element). **(2) A verb's rung is the rung of the field it reads:** names and kinds at `list`, bodies and metadata at `read`, so `glob` matches `list`-level rows while `grep` and `glean` search and count only the readable set; an edge's type is a name-class field and travels at `list`, its weight and distance are measure-class fields and travel at `read`. **(3) The road is derived `list`:** a caller's effective level on a directory is the greater of its granted level and `list`-when-a-row-at-or-above-`list`-lies-beneath. Checked against ADR 070's five rules and the memo's three conditions, nothing changes for `ls`, `tree`, `glob`, `stat`, `read` or any write; what changes is that the walk, and the edge rows, now see a road directory as a node, and memo 2026-09-28 §5.2's "edges on a road directory answer not-found" row flips to "answers bare". The "hidden file → road directory" edge does not leak: its hidden endpoint fails rule 1, so the edge is absent. **For `contribute`:** the executed baseline shows that "alter only your own rows" already rides on the owner floor today (bob overwrote, deleted and restored his own row under a read-only posture, and was refused on the system's row and on a fresh name) — so `contribute` is exactly "`read` plus `create` on the prefix", and the owner floor supplies the rest; Plan 9 has the per-file half (`DMAPPEND`, `libc.h:580`, writes land at the end and `OTRUNC` is ignored, `ramfs.c:422,563-564`) and lacks the per-directory half (no sticky bit: the `DM*` bits are `DIR APPEND EXCL MOUNT AUTH TMP`, `libc.h:579-584`; remove and rename need only write on the parent, `ramfs.c:640`, `lib9p/srv.c:565`, `stat(5):192`). Two leaks surfaced that the ladder should close while it is at it: `rmedge` today gates only the source, so a writer of a visible file can remove an edge to a **hidden** target and learn from `deleted` vs `not_found` that the hidden row exists (EXECUTED); and the walk's `in_degree`/`out_degree` count fields must count only edges with both endpoints at `list` or above, or they inherit the "stored ranking signals count hidden in-links" leak.

## Findings table

| # | Finding | Evidence | Status |
|---|---|---|---|
| 1 | Today a road directory answers `stat`/`ls`/`tree`/`glob` as a bare name (path, kind only), a hidden sibling and an absent name both answer `not_found`, and `mkdir` beneath it is `permission_denied` | `l3_walk_examples.out` §A, §C | EXECUTED |
| 2 | `mkedge` from a writable file to a road directory is `permission_denied` (the target); to a hidden file or an absent path it is `not_found`, identically | §B, §C | EXECUTED |
| 3 | `rmedge` gates the source only: bob (write on `d.md`) removed the system-authored edge `d.md → /priv/secret.md` with status `deleted`, although `secret.md` is hidden to him; a second removal said `not_found`. The pair of answers reveals the hidden row's existence | §C; `backend.py:894` (`gate.targets(... sources, "modify")` only) | EXECUTED |
| 4 | "Alter only your own rows" exists today as the owner floor: under a `shared` (read-only) posture bob overwrote, deleted and restored his own row, authored an edge from it, and was refused on the system's row, on a fresh name, and on an edge from the system's row | §F; `grants.py:468-481` (`admits` owner arm) | EXECUTED |
| 5 | Anonymous is admitted by the **mount root's** posture only: under `private` at `/`, every anonymous call is `unauthenticated`, whatever the posture of `/inbox` | §E, §G; `rights.py:328-332` `posture_refusal` | EXECUTED + READ |
| 6 | Anonymous holds no owner floor (`floor = not authority.is_anonymous`), so under an `inbox` posture anonymous could create but never alter — the natural drop-box behaviour for nobody-in-particular | `rights.py:317` | READ |
| 7 | Edges carry no ownership today; `mkedge` gates source `modify` + target `read`, `rmedge` source `modify` | `edges.py:144,206`; `backend.py:865-866,894` | READ |
| 8 | `glean` computes `N`, `avg_dl`, `df` and the candidate set over the view's admitted rows; `grep` strikes rows with `view.admits` after nomination | `glean.py:249-252,699-754`; `grep.py:261,303` | READ |
| 9 | Plan 9: walk = execute on the directory, per element; `stat` needs no permission and returns mode, atime, mtime, length, uid, gid, muid; a directory opens only `OREAD`, so read *is* listing; `DMAPPEND` files write at the end and ignore `OTRUNC`; no sticky bit; `wstat` of mode/mtime is owner or group leader | `0intro:562-564`; `walk:86-94`; `stat:59-77,183-185,192-205`; `open:64-71`; `ramfs.c:353-357,399-403,414-422,563-564,640,691-695`; `lib9p/srv.c:368-371,386-404,565,644-678`; `lib9p/uid.c:13-35`; `libc.h:545-549,579-587` | READ |
| 10 | lib9p's `filewalk` checks nothing on a walk; permission is checked only at `open` — Plan 9's own library is a "walk unchecked" server | `lib9p/srv.c:300-331` (no `hasperm`), `:396` | READ |
| 11 | SharePoint Contribute = Read + Add/Edit/Delete Items; Google Drive Contributor = view, comment, edit, create — neither vendor ships a "create but not read others" rung | learn.microsoft.com user-permissions page; developers.google.com ref-roles | READ (web) |

Plan 9 clone: `~/Git/Repos/plan9` at `ed1a9c21e` (2025-10-28); MIT-style licence (`LICENSE`, Plan 9 Foundation 2021) — fine to study, nothing copied. `git status` reports three dirty files (`rc/bin/Kill`, two troff fonts), none in the paths I read; I did not fetch (the brief says read-only). Memo 2026-09-28 covers Plan 9 breadth; this report cites only what each rule needs.

## The worked example

Posture `private` at `/`. Rows:

```
/pub/readme.md
/team/plan.md   /team/notes.md
/priv/deep/d.md                      <- bob: read (today: the only grant)
/priv/secret.md
```

Authored edges: `d.md -cites-> secret.md`, `secret.md -cites-> readme.md`, `d.md -cites-> plan.md`, `secret.md -mentions-> /priv` (a hidden file pointing at a road directory — the leak probe).

Bob's rights **under the proposed ladder**: `read` on `/priv/deep/d.md`, `list` on `/team`, nothing else. His effective levels, by the rules below: `/` list (road), `/priv` list (road), `/priv/deep` list (road), `d.md` read, `/team` list (granted), `plan.md` list, `notes.md` list (prefix), `/pub`, `readme.md`, `secret.md` none.

Today (EXECUTED, §A): `tree /` shows `/priv`, `/priv/deep` bare and `d.md` whole; `/team` is absent because nothing beneath it is visible.

## 1. The walk under two rungs

**The hop predicate.** Let `L(x)` be the caller's effective level on row `x` (granted level, the owner floor, the everyone label, and the derived road of §2). A walk in direction `dir` with selected types `T`:

- A seed `s` enters the frontier at depth 0 iff `s` is live and `L(s) >= list`. A hidden or tombstoned seed yields no row and starts no hop (ADR 079 pin 7, unchanged).
- From a frontier node `u` (so `L(u) >= list` by construction), an edge `e = (u, v)` of a type in `T` is **traversed** iff `v` is live, `L(v) >= list`, and `v` is not visited. Then `v` enters the frontier. So every traversed edge has both endpoints at `list` or above — Clay's rule, with `list` as the walk's rung.
- A node at `none` never enters the frontier, so nothing is reached through it (the leak experiment's cut, study 03 §(c), unchanged).
- **A returned node row's fields depend on its own level:** `L(v) >= read` → the requested `columns`, as `tree` returns a visible row; `L(v) == list` → bare: `path`, `kind`, `depth`, nothing else (the `road_observation` shape plus `depth`, `reads.py:624-626`).
- **Edge rows** are the induced edges among returned nodes (pin 8). Every such edge has both endpoints at `>= list` by construction. Each carries `edge_type` always; `edge_weight` and `edge_distance` only when **both** endpoints are at `>= read` (see the argument below). The `fs` type carries no weight or distance anyway.

**Worked example.** `graph("outbound", "/priv/deep/d.md", depth=2)` for bob:

| hop | candidate | `L` | verdict |
|---|---|---|---|
| 0 | `d.md` | read | node, whole, depth 0 |
| 1 | `d.md -cites-> secret.md` | none | cut; edge absent |
| 1 | `d.md -cites-> plan.md` | list | traversed; `plan.md` bare at depth 1 |
| 2 | from `plan.md` | — | no edges |

Rows: `d.md` (whole), `plan.md` (bare); edge `(d.md, cites, plan.md)` with its type and no weight. Today the answer is `d.md` alone. `graph("outbound", "/", edge_types=("fs",))` returns `/`, `/priv`, `/priv/deep`, `/team`, `/team/plan.md`, `/team/notes.md` bare and `d.md` whole — exactly `tree("/")` under the same ladder, which is the acceptance criterion in spec 165.

**Does an edge into a `list`-level node reveal the edge's type?** Yes, and it must. Three arguments.

- *ADR 065 rule 1 only hides what is hidden.* A `list`-level row is not hidden; it is visible with fewer fields. An edge is a row in `vfs_edges` with its own visibility, and the natural rule — the one the walk already enforces — is that an edge is visible iff neither endpoint is absent. ADR 018 pin 1 gates `mkedge` "at both endpoint paths" for the same reason: a fact about two rows is governed by both.
- *The road rule, applied.* "A bare name reveals nothing its visible rows' own paths do not already print" (memo §5.1). The walk reaches `plan.md` *through* the edge; the node row at depth 1 already says "something reachable from `d.md` in one hop is named `/team/plan.md`". Withholding the type would leave the renderer (pin 8: "the edge type on the line") unable to indent, and the subgraph inconsistent. And vfs already shows an edge touching a `list`-level node: `tree` prints `/priv → /priv/deep` for bob today, which is the `fs` edge between two road nodes.
- *Weight and distance are not names.* A similarity extractor's `edge_distance` between `d.md` (readable) and `plan.md` (list) is a number computed from two bodies, one of which the caller may not read. That is the class ADR 065 rule 4 fences ("no ... embedding distance ... touches a row the predicate has not admitted"). It was computed by someone who could read both, and stored; but returning it to a `list`-level caller lets them rank hidden bodies by similarity to a known one. Rule 2 (the field rule) settles it: `edge_type` is a label → `list`; `edge_weight`/`edge_distance` are measures → `read` on both endpoints. The alternative — return the whole edge — is defensible (the edge is "its own row") and simpler; I recommend the split because it costs one condition in the renderer and closes a channel Clay already closed for BM25.

**`meet` through `list`-level intermediaries:** yes — that is the point of the rung. The bridge `d.md … plan.md … x` may pass `plan.md`; it is a non-seed, so `minimal=True` may strip it (pin 10's articulation-point rule is level-blind). A seed the caller holds only `list` on is a lawful seed and is returned bare at depth 0.

**What the walk reveals about `list`-level rows, stated honestly.** A walk from `plan.md` (list) over authored edges reveals `plan.md`'s edges to other `>= list` rows: their existence and types. So `list` must be *defined* as "name, kind, and the row's children and edges by name and type". That is more than NFSv4 `READ_ATTRIBUTES` and exactly Plan 9's read-on-a-directory (names, below). A rung that reveals the name but not the edges would make the walk unable to pass it (no discovering edge to show), so it is not on offer.

**Plan 9's verdict (a).** The walk rule is Plan 9's elementwise rule applied to edges: `walk(5)` — "the implied user of the request must have permission to search the directory ... Subsequent elementwise walks have equivalent restrictions" (`plan9:sys/man/5/walk:86-94`); `0intro(5)` — "A walk in a directory is regarded as executing the directory, not reading it" (`plan9:sys/man/5/0intro:562-564`); `ramfs` checks `perm(f, parent, Pexec)` for every element (`plan9:sys/src/cmd/ramfs.c:353-357`), and `perm` is the owner/group/other bit test (`:849-858`). A `list`-level intermediate node is Plan 9's execute-only directory: passable, not readable. One difference to say out loud: Plan 9 applies the rule to *path* resolution, while vfs's path addressing deliberately does not (ADR 070 context: "reaching a deep path needs no right on its ancestors" — the Windows/SharePoint side; `lib9p`'s own `filewalk` checks nothing at all, `plan9:sys/src/lib9p/srv.c:300-331`, and gates only `open`, `:396`). vfs will hold both: addressing a path is bypass-traverse; walking a graph is elementwise. That is consistent, because the road derives `list` on every ancestor of anything the caller can address, so the elementwise rule would admit those ancestors anyway.

## 2. The road as derived `list`

**Unification rule.** For a directory `D` and caller `c`:

```
L_c(D) = max( granted_c(D),  list  if some row r beneath D has L_c(r) >= list  else none )
```

where `granted_c` is what the resolver computes today (the caller's spans, the owner floor, the everyone label). For a file the second term is always `none`. Note the recursion is well-founded: a `list` grant on `/team/plan.md` puts `/team` and `/` on the road at `list`, exactly as a `read` grant does today — the road's "visible row" becomes "row at `>= list`".

**Against ADR 070's five rules** (READ):

| ADR 070 | Under the rule | Changes? |
|---|---|---|
| 1. On the road = hidden dir with a visible row beneath; from rows that exist, never grant prefixes | `L(D) = list` by the second term; it is computed from rows (the arm roots that exist, the owned rows, the everyone-labelled rows — `rights.py:436-460`), never from prefixes | no |
| 2. Shows as a bare name: path and kind; `stat` the same; `read` → `wrong_kind` | a `list`-level row is the bare shape; a granted `list` directory and a road directory are indistinguishable, which is what "derived `list`" means | no |
| 3. Listing it shows only visible and road children | `ls D` shows the children at `>= list`: under a granted prefix `list` that is all of them; under a derived road only the road and visible ones, because a file beneath a road directory gets no derived term | no |
| 4. Every write beneath is `permission_denied`, decided on the directory before the lookup | `list < contribute`, so the gate's `parent in road` branch (`rights.py:693`) becomes `L(parent) < contribute`; still decided before the name is looked up | no |
| 5. A hidden directory with nothing visible beneath stays absent | both terms are `none` | no |

**Against the memo's three conditions** (`2026-09-28` §5.1): names only, no metadata — the bare shape has no `version`, `updated_at`, `size_bytes`, `owner_id` or child count, and that is the shape a granted `list` row takes too; no probing — `stat /priv/secret.md` is `not_found` like `/priv/nope` (EXECUTED §A), unchanged because a sibling file beneath a road directory stays at `none`; the road from rows, not prefixes — unchanged (a `list` grant on a path with no rows shows nothing).

**Verb outcomes on a road-only directory:** `ls`, `tree`, `glob`, `stat`, `read`, `write`, `mkdir`, `edit`, `delete`, `move`, `copy` — all unchanged (table above). What changes: `graph` (and the `edges` reading of it, ADR 079 pin 9) now returns the road directory as a bare node and passes it; memo §5.2's row "versions, edges, `locate` on `/projects` → not-found: traverse is not read" splits by the field rule — `edges` → bare node and its edges' types (a name-class fact), `locate` (if it ever exists; it is not in `ops.py`) → `list` (a name lookup), `versions` → `read` (bodies). The memo's own §6 wording ("no content, no metadata, no versions, no edges and no statistics") was written when the only visible rung was `read`; the first, second, fourth-as-versions and fifth clauses stand, the "no edges" clause is the one the ladder revises, and the ADR should say so.

**Is that right, or does passing the road leak?** Work the probe. `secret.md -mentions-> /priv`; bob seeds `graph("inbound", "/priv")`. `/priv` is at `list` (road) — a lawful seed, returned bare. The edge's source `secret.md` is at `none` → rule 1 cuts it → the edge is absent, the walk returns `/priv` alone. No leak. The general statement: passing a road node can reveal only edges whose *other* endpoint the caller already holds `>= list` on, and those endpoints' names are already printed by `ls`/`tree`. The one way a road node could still leak is a **count**: `in_degree(/priv)` as a whole-mount number would include the hidden edge. See §3 — counts must be over the visible edge set, or absent on bare rows (they are absent on bare rows by the bare shape; the risk is on `read`-level nodes).

**Plan 9's verdict (b) and (c).** *(b)* "The stat request requires no special permissions" (`plan9:sys/man/5/stat:183-185`); `ramfs` `rstat` has no permission test (`ramfs.c:647-652`), nor does lib9p's `sstat` (`srv.c:590`). Once you can walk to a file you can stat it — the model for "a `list`-level node is returned bare". But Plan 9's stat returns **mode, atime, mtime, length, name, uid, gid, muid** (`stat:50-77`); vfs's bare row must withhold the analogues: `size_bytes` (length), `updated_at`/`created_at` (mtime/atime), `owner_id` (uid), `version` and `content_hash` (no Plan 9 analogue), and the grant state (mode). Memo §5.1 condition 1 measured why: an ancestor's length and mtime move when a hidden sibling appears. *(c)* A directory may be opened only `OREAD`; reading it yields its entries (`plan9:sys/man/5/open:82` "it is illegal to write a directory"; `ramfs.c:399-403`; `lib9p/srv.c:368-371,391-394`). So Plan 9 has no separate list bit: the directory ladder is `x < rx < rwx`. vfs's `list` (names and kinds, free stat withheld) sits **above** `x` (which gives traversal and nothing else) and **below** `rx` (which gives names plus a free full `stat` of each child). A vfs rung for "traverse without even the names" — Plan 9's bare `x` — is not worth having: the one thing `x` buys, reaching a deep path by name, vfs already gives with no right on the ancestors (prefix coverage, ADR 070 context), and the road derives the ancestors' names the moment the caller can see anything beneath. It fails the addendum's third test (no verb needs exactly it).

## 3. The search verbs

**Rule 2, stated:** a verb's rung is the rung of the field it reads. Names and kinds are `list`-class; bodies, metadata, measures and statistics are `read`-class.

| verb | field it reads | rung | `list`-level rows |
|---|---|---|---|
| `glob` | path, kind, extension | `list` | matched, returned bare; `kind=` and `ext=` filters are name-class and apply |
| `grep` | body | `read` | never searched, never a candidate, never counted toward the match |
| `glean` | body, embeddings; `N`, `avg_dl`, `df` | `read` | never a candidate; `_visible_lexicon` and `_visible_corpus` (`glean.py:699-774`) keep joining the **readable** view, not the listable one |
| `ls`, `tree`, `stat` | name, kind (+ metadata when readable) | `list` for presence; fields by the row's own level | shown bare |
| `read` | body | `read` | `permission_denied` — the row is visible, so ADR 065 rule 2 permits a refusal, and the refusal confirms only what `ls` already showed |

Worked example: `glob("/**/*.md")` for bob returns `d.md` (whole) and `plan.md`, `notes.md` (bare); `grep("plan")` returns hits in `d.md` only, and if `d.md` says "see plan.md" the hit is in `d.md`'s body, lawfully; `glean("quarterly plan")` scores `d.md` alone with `N = 1` — `plan.md`'s body is not in `N`, `avg_dl` or any `df`. ADR 065 rule 5's "visible set" must be read as the **readable** set once `list` exists; the ADR should say that word.

Two consequences for the implementation: the `Visibility` object needs two compiled views where it has one today — a `list` view for presence (`glob`, `ls`, `tree`, `stat`, the walk) and a `read` view for bodies — which is the "one more `Rights` compile per level a verb can need" cost the addendum priced; and `grep`'s candidate nominator (open question "grep's candidate budget counts hidden candidates") should narrow by the `read` view, not the `list` view, or `list`-level rows will eat the budget as hidden ones do today.

**"Stored ranking signals may count hidden in-links" — does `list` change it?** It narrows the leak but does not close it. Today the leak is "an in-link from a row the caller cannot see moves a score". Under `list`, an in-link from a `list`-level row is a visible edge (both endpoints `>= list`), so counting it is lawful — the caller could enumerate it with `graph("inbound")`. An in-link from a `none`-level row stays a leak. So the rule for any graph-derived signal, stored or live, is: **count only edges with both endpoints at `>= list` for this caller.** Whole-mount stored in-degree remains unlawful for a partial caller exactly as before; the open question stands, with `list` as the correct visible set for it (not `read`). The same rule binds `Observation.in_degree`/`out_degree` when the walk populates them: over the induced subgraph, or over the caller's visible edge set — never the stored whole-mount count.

## 4. `contribute` and the write verbs

**The executed baseline (§F) says what `contribute` is.** Under a `shared` posture (everyone `read`), bob — holding nothing else — overwrote his own row (`status: updated`), deleted it, restored it and authored an edge from it; he was refused `permission_denied` on the system's row, on a fresh name, and on an edge whose source is the system's row. "Alter or remove only your own rows" is therefore already law, by the owner floor (`grants.py:468-481`; ADR 064 rule 4/5). What `read` lacks and `read_write` has too much of is **creation**. So:

> `contribute` on a prefix = `read` on the prefix + the right to create new rows beneath it. Altering and removing one's own rows is the owner floor, which every rung already carries.

This is the addendum's "`GateMode.create` passes and `modify` falls through to the owner floor", confirmed by execution.

**The write-side table (proposal).** `L` is the caller's effective level; "own" is the owner floor (`owner_id` equals the single subject; a set owns nothing, ADR 064 rule 4; anonymous has no floor, `rights.py:317`).

| verb | gate today (`backend.py`) | rung under the ladder | the `contribute` case, worked |
|---|---|---|---|
| `write` (new path) | `upsert`: creation judged by `write.reaches` on the parent chain | `contribute` at the path (the posture label or a covering span at `>= contribute`) | bob creates `/inbox/new.md` → passes |
| `write` (existing row) | `upsert`: `write.admits(row)` | `read_write`, or own | bob overwrites `sys.md` → denied; his own → passes (EXECUTED today) |
| `write` (tombstoned row at the path, a revive) | judged as an occupied path (ADR 074 item 5) | `read_write`, or own | a stranger's tombstone at the name → denied, not absent; the caller holds `>= read` so the trash view already shows it |
| `edit` | `modify` | `read_write`, or own | same as overwrite |
| `delete` | `modify` + `subtrees(read_write)` | `read_write`, or own on the row **and every row beneath** | bob deletes own file → passes; own directory holding the system's file → denied |
| `restore` | row at `read_write` + `subtrees` (`:740-756`) | same as `delete` (ADR 074 rule 3: "as the delete did") | bob restores his own row → passes (EXECUTED today) |
| `mkdir` | `create` on the path, ancestors by `reaches` | `contribute` at the parent | passes; the directory is bob's (`owner_for`, `authority.py:216-227`) |
| `move` | source `modify` + `subtrees(read_write)`; dest `create` | source: `read_write` or own (whole subtree); dest parent: `contribute` | bob moves his own file into `/inbox/done/` → passes if he may create there |
| `copy` | source `read` + `subtrees(read)`; dest `create` | source `read`; dest parent `contribute`; the copies are the caller's | bob copies `sys.md` to `/inbox/mine.md` → passes, and now owns the copy |
| `mkedge` | source `modify`; target `read` | source: `read_write` or own; target: `list` (by rule 2 — the only field read is its name) | bob authors `bob.md -replies_to-> sys.md` → passes (EXECUTED today at target `read`) |
| `rmedge` | source `modify` only (**leak**, finding 3) | source: `read_write` or own; **target `list` too**, so a hidden target answers `not_found` in the same shape as a missing edge | bob removes an edge from the system's row → denied |
| `grant`/`revoke` | `read_write` at the path | unchanged (`manage` is parked) | a contributor may not share |
| `sweep`, `posture`, members | developer plane | unchanged | — |

Three points need an ADR sentence each.

- **Edges and ownership.** Edges have no `owner_id` (`edges.py:144`). The proposal above makes the *source row's* ownership govern: an edge is part of the source's outbound facts, which is how `mkedge` is gated today (source `modify`). Consequence: a contributor may annotate only rows it owns. If "a contributor may tag anyone's row" is wanted (a plausible inbox use), edges need their own `owner_id` and `rmedge` an ownership test — a schema change for a later spec, not this one. ADR 018 pin 1 ("gate at both endpoint paths") is satisfied either way.
- **`mkedge`'s target at `list`.** Rule 2 says `list`; the conservative choice is to keep `read`. Neither leaks (a `list` row is visible). I recommend `list` because the walk traverses at `list`, and an edge the caller could follow but not author is an odd asymmetry; it also matches Unix, where a symlink may name a file you cannot read.
- **`rmedge` must gate the target.** Finding 3 is a leak today, independent of the ladder: the per-row status (`deleted` vs `not_found`) tells a writer of a visible file whether a hidden path exists. The fix is one more `gate.targets(..., targets, "list")` beside the existing source check, so a hidden target classifies `not_found` **before** the edge lookup and in the same shape the absent-path case produces (the gate's `classify_miss`, not `rmedge_rows`' per-row `not_found` with `vfs.target` data — the two shapes differ today, §C, and must not).

**Can a `contribute` caller trash and restore its own row?** Yes, both by the owner floor; EXECUTED today (§F: `delete` → `deleted`, `restore` → back, version 4). The tombstoned row keeps `owner_id` (ADR 074 rule 1), so the floor holds across the tombstone.

**Plan 9's verdict (d).** Plan 9 has the per-file half and not the per-directory half. `DMAPPEND` (`plan9:sys/include/libc.h:580`): "the file is append-only (offset is ignored in writes)" (`0intro:581-582`); `ramfs` forces `off = r->ndata` on every write (`ramfs.c:563-564`) and skips truncation when the bit is set (`:422`); `open(5)` says `OTRUNC` on an append-only file "succeeds but the file will not be truncated" (`open:64-71`). That is "add but never alter" for one file's bytes. vfs rows are replaced whole on `write`, so the byte-level mode has no row-level analogue; `contribute` is its *namespace-level* analogue: add rows, never replace rows you do not own. The directory half is absent from Plan 9: there is no sticky bit (the mode's attribute bits are `DMDIR DMAPPEND DMEXCL DMMOUNT DMAUTH DMTMP`, `libc.h:579-584`, and `grep -i sticky` over `libc.h` and `sys/man/5` finds nothing), and removal needs only write permission on the **parent** — `ramfs.c:640` (`perm(f, &ram[r->parent], Pwrite)`), `lib9p/srv.c:565`, and rename likewise ("the name can be changed by anyone with write permission in the parent directory", `stat:192`). So a Plan 9 directory where everyone may create is a directory where everyone may delete everyone's files — exactly the posture `contribute` refuses. The addendum's Unix sticky bit and NFSv4 `ADD_FILE` are the right precedents; Plan 9 supplies only the `DMAPPEND` idea and the lesson that "write on the parent" fuses add with remove.

## 5. Leaks and the intersection law

**Total order.** `none 0 < list 1 < read 2 < contribute 3 < read_write 4 (< manage 5)`. The meet is `min` by rank (ADR 066 rule 2; `resolve` already keeps only rows with `LEVEL_RANK[row.level] >= need`, `grants.py:609`), and that stays trivial iff each rung strictly includes the one below:

| rung | includes the rung below? | argument |
|---|---|---|
| `list ⊇ none` | yes | trivially |
| `read ⊇ list` | yes | a readable row's name, kind and edges are among its fields |
| `contribute ⊇ read` | **yes, by decision** | see below |
| `read_write ⊇ contribute` | yes | alter any row ⊇ alter own rows; create ⊇ create |
| `manage ⊇ read_write` | parked; assumed | the open question's option (a) says so |
| `run` | **no** | one may run what one cannot read (the addendum's finding; Unix `x`, Postgres `EXECUTE`) — a second axis, not a rung |

**Must `contribute` include `read`?** Yes, and the vendors agree: SharePoint's Contribute is "Read permissions, plus: Add Items, Edit Items, Delete Items ..." (<https://learn.microsoft.com/en-us/sharepoint/sites/user-permissions-and-permission-levels>); Google Drive's Contributor "grants the ability to view the file, add comments, and edit the file. Can also create files within a shared drive" (<https://developers.google.com/workspace/drive/api/guides/ref-roles>). The pure **drop box** — add, but never read others' rows — is Unix `chmod 733` / Plan 9 `-wx` on a directory: write and execute without read (`ramfs.c:407` creation needs write on the parent; listing needs read, `:417`). It is `contribute − read`, which has no place in a total order. Two reasons not to bend the ladder for it. First, the order is what makes the row label one integer and the meet one `min`; a non-nested rung would need a second column and a per-verb meet (the `run` problem). Second, the vfs reason the drop box exists — a sender should not read other senders' mail — is a question about *who* reads the inbox, and the ladder already answers it with ownership: give senders `contribute` on `/inbox/<sender>/` each (prefix per principal), or make the inbox owner the only reader via a `private` posture plus a per-sender `contribute` card on their own subfolder. The blind shared drop box is a posture question that the current words cannot express; it joins `run` on the second-axis list rather than becoming a rung. Say that in the ADR so nobody re-derives it.

**Under a set** (ADR 066): ownership is per member, and a row is owned by a set only when every member owns it — impossible for a set of two. So a set's `contribute` degrades to `read` + create, with no alter-own; that is monotone (narrowing never widens) and consistent with rule 9 ("ownership of what the set creates is the container's", `owner_id NULL`).

**The stored label.** `everyone_level` stores a rank (ADR 073 rule 1). Inserting `list` below `read` and `contribute` below `read_write` renumbers the ranks; the column is derived and rebuildable from the `*` rows, so the landing relabels once (a chunked relabel, ADR 073 rule 6) — a one-time cost, not a design cost.

**Leaks closed or opened, in one list.**

- Closed by rule 1: reaching anything through a hidden node (study 03's leak), and the "hidden file → road directory" edge (§2).
- Closed by rule 2: `list`-level bodies in BM25 statistics, vector candidates, `grep` hits; edge measures between a readable and a listable row.
- Opened deliberately by `list`, and must be documented as the rung's meaning: the names, kinds and edge types of everything beneath a `list` prefix, and `permission_denied` on `read` of such a row (a lawful refusal, ADR 065 rule 2, because the row is visible).
- Pre-existing and should be closed in the same landing: `rmedge` on a hidden target (finding 3); count fields over hidden edges (§3).
- Not changed: timing (a `list` row's presence check costs what a `read` row's does), the trash view (ADR 074 rule 7 — a tombstoned `list`-level row shows bare with `deleted_at` projected? No: `deleted_at` is metadata; a bare tombstone should show path and kind only, and the trash view should say so).

## 6. The posture words

Posture gives everyone a level at and below a prefix (`POSTURE_LEVELS`, `grants.py:86`). Two new words:

- **`listed`** → everyone `list`. Example: `posture("/", "listed")`. Anonymous `ls /` → every name and kind, bare; `tree /` → the whole hierarchy, bare; `glob` matches names; `read /pub/readme.md` → `permission_denied` (visible, barred); `grep`/`glean` → empty results with no error (the readable set is empty); `graph("outbound", "/pub/readme.md")` → nodes bare, edge types shown, no weights; every write → `permission_denied`, decided on the parent before the lookup. A `read` card on one file then makes that file whole for its holder and nothing else changes. This is the "there is a file here you cannot read, ask for access" posture the addendum wanted.
- **`inbox`** → everyone `contribute`. Example: `posture("/", "inbox")`. Anonymous may `ls`, `read`, `glob`, `grep`, `glean` everything (contribute ⊇ read), may `write` a new path and `mkdir`; may not overwrite, edit, delete, move or `mkedge` from any row — anonymous has no owner floor (`rights.py:317`), so for nobody-in-particular the posture is exactly append-only; a named principal under the same posture may additionally alter the rows it created. Rows anonymous creates: `owner_for` stamps the anonymous subject (`authority.py:216-227`) — the ADR should pin that an anonymous-created row has **no** floor for the next anonymous caller (today `floor = False` for anonymous already guarantees it, finding 6).
- **The gate at the edge:** `posture_refusal` admits anonymous by the **mount root's** level only (`rights.py:328-332`, EXECUTED §E/§G: `private` at `/` makes `/inbox`'s posture irrelevant to anonymous). A deployment wanting an anonymous inbox under a private mount must put the `inbox` word at the root and `private` beneath, or the ADR must change that gate to look at the addressed path's chain. Flag, do not decide here.
- **Everyone capped at `read_write`:** still right. `manage` for everyone would let any caller grant and revoke, which is "no governance" by another name; and the label column need only range 0–4. `open` stays `read_write` and remains the default (ADR 068).

Anonymous in Plan 9 for comparison: `none` is a name that holds the "other" bits only (`lib9p/uid.c:17-19` tests `other` first for every uid), which is what `posture_refusal` plus `floor = False` make of vfs's anonymous.

## 7. Executed baseline

`scratchpad/ladder/l3_walk_examples.py`, run as `uv run python <path>` from the vfs root against `InMemoryStorage`; full output in `l3_walk_examples.out`. The tree is the worked example's; bob holds `read` on `/priv/deep/d.md` (then `read_write` on it in §C to isolate the target answers).

```
== stat /priv (road) ==                     /priv       kind=directory          (bare: path, kind)
== stat /priv/deep (road) ==                /priv/deep  kind=directory
== stat /priv/secret.md (hidden sibling) == ERROR not_found
== stat /priv/nope (absent) ==              ERROR not_found                      (same answer)
== ls / ==                                  /priv       kind=directory          (/pub, /team absent)
== ls /priv (road: trimmed) ==              /priv/deep  kind=directory          (secret.md absent)
== tree / ==                                /priv, /priv/deep bare; /priv/deep/d.md whole
== glob /** ==                              same three rows
== mkedge d.md -> /priv (read-only source) == ERROR permission_denied /priv/deep/d.md ; ERROR permission_denied /priv
   -- bob at read_write on d.md --
== mkedge d.md -> /priv (road target) ==    ERROR permission_denied /priv
== mkedge d.md -> /priv/secret.md ==        ERROR not_found /priv/secret.md
== mkedge d.md -> /priv/nope.md ==          ERROR not_found /priv/nope.md        (same answer)
== rmedge d.md -> secret.md (system-authored) == success; status=deleted        <-- LEAK: hidden target, edge removed
== rmedge d.md -> /priv/nope.md ==          not_found  data={edge_type, vfs.target}
== rmedge d.md -> secret.md again ==        not_found  (so deleted-then-not_found reveals existence)
== mkdir /priv/new (under the road) ==      ERROR permission_denied
== ls / (anonymous, private root) ==        ERROR unauthenticated
   -- §F: shared posture at /inbox, bob owns /inbox/bob.md --
== bob overwrites own row ==                success, status=updated, version 2
== bob overwrites system's row ==           ERROR permission_denied
== bob creates /inbox/new.md ==             ERROR permission_denied              <-- what contribute adds
== bob deletes own row ==                   success, status=deleted
== bob restores own row ==                  success
== bob mkedge own -> sys.md ==              success
== bob mkedge sys.md -> own ==              ERROR permission_denied
```

Baseline the ladder changes: `stat`/`ls`/`tree`/`glob` on the road stay as they are; `mkedge` to a road directory flips from `permission_denied` to pass (target at `list`); `/team` and its files appear bare once bob holds `list` there; `graph` on the road flips from absent to bare-and-passed; `write` of a fresh name under an `inbox`-postured or `contribute`-granted prefix flips from `permission_denied` to pass.

## Plan 9 on the parked `manage` rung (e)

Plan 9 splits "may change the data" from "may change the rules" the way the open question wants: `wstat` lets anyone with write permission on the file change its length, anyone with write on the parent change its name, but only "the owner of the file or the group leader of the file's current group" change mode and mtime, and the gid only the owner-if-member or the leader-of-both (`plan9:sys/man/5/stat:189-215`); `ramfs` enforces it as `Enotowner` unless `f->user` is the file's user or its group (`ramfs.c:691-695`, with the comment "leader=>group itself"), and lib9p's `swstat` refuses type, dev, qid, muid and the `DMDIR` bit outright before delegating (`lib9p/srv.c:644-678`). Two lessons for `manage`: the right to change the rules is tied to **ownership or leadership, not to write** — a writer who is not the owner cannot `chmod` — which is the NFSv4 owner-keeps-`WRITE_ACL` rule the open question already marks "take"; and group leadership is Plan 9's delegation primitive, which lines up with "group ownership" being the other parked question. One sentence for the ADR: `manage` on a row should be what the owner (and a group leader, once groups can own) holds regardless of cards, plus what a `manage` card grants; a `read_write` card alone should not carry it.

## Open questions

1. Whole edge or split edge: return `weight`/`distance` only when both endpoints are at `read` (recommended), or treat the edge as its own fully visible row. The ADR should pick; §1 argues the split.
2. `mkedge`'s target rung: `list` (rule 2) or `read` (today). Recommended `list`.
3. Edge ownership: source-row ownership (recommended now) vs an `owner_id` column on `vfs_edges` (needed if contributors may annotate others' rows).
4. `posture_refusal` reads the root only; an anonymous `inbox` under a private root is unreachable. Change the gate to the addressed chain, or document.
5. Count fields (`in_degree`, `out_degree`) and the stored link signals: the visible edge set is "both endpoints `>= list`"; the open question on stored signals stays open with that set named.
6. The trash view's bare rows: does a tombstoned `list`-level row project `deleted_at`? Rule 2 says no (metadata); ADR 074 rule 7 should get one clause.
7. `[NOT VERIFIED: no Plan 9 system in session]` — every Plan 9 claim is from the man pages and two servers' source, not executed; memo 2026-09-28 executed the Unix side.

## What the ADR should pin

**The three rules.**

1. **Traverse on both endpoints.** A walk passes an edge only when the caller holds the walk's rung — `list` — on both endpoints. A `none` node never enters the frontier; a `list` node enters and is returned bare (path, kind, depth); a `read` node is returned whole. `meet` may route through `list`-level nodes and `minimal=True` may strip them. (Plan 9: a walk executes each directory it passes, `0intro(5)`, `walk(5)`.)
2. **A verb's rung is the rung of the field it reads.** Names, kinds, children and edge types at `list`; bodies, metadata, measures (`size_bytes`, times, `version`, `owner_id`, `edge_weight`, `edge_distance`) and statistics (`N`, `avg_dl`, `df`, candidates, degree counts) at `read`. "Visible set" in ADR 065 rule 5 means the readable set. (Plan 9: `stat` is free but reveals length, mtime, owner and mode — vfs's bare row withholds exactly those.)
3. **The road is derived `list`.** A caller's effective level on a directory is `max(granted, list if a row at >= list lies beneath)`. Nothing changes for `ls`, `tree`, `glob`, `stat`, `read` or any write; `graph` and the edge rows now see a road directory as a `list` node. A bare `x`-only rung is not added (the road and prefix coverage already give what Plan 9's `x` alone gives).

**The verb-to-rung table** (one declared mapping in `ops.py`; "own" is the owner floor, present on every rung for a single named subject, absent for sets and for anonymous):

| verb | rung needed | on what |
|---|---|---|
| `stat`, `ls`, `tree`, `glob` | `list` | the row's presence; fields by the row's own level |
| `read` | `read` | the row |
| `grep`, `glean` | `read` | every row searched, counted or ranked |
| `graph` | `list` to pass or return a node; `read` for its contents and for edge measures | both endpoints of every traversed edge |
| `write` (new), `mkdir` | `contribute` | the parent chain / the creation path |
| `write` (existing), `edit` | `read_write`, or own | the row |
| `delete`, `restore` | `read_write`, or own | the row and every row beneath |
| `move` | `read_write` or own on the source subtree; `contribute` at the destination parent | both |
| `copy` | `read` on the source subtree; `contribute` at the destination parent | both |
| `mkedge` | `read_write` or own on the source; `list` on the target | both endpoints |
| `rmedge` | `read_write` or own on the source; `list` on the target (closes today's leak) | both endpoints |
| `grant`, `revoke`, `grants` | `read_write` (until `manage`) | the path |
| `sweep`, `posture`, `add_member`, `remove_member` | developer plane | — |
| `run` | not a rung; its own axis | — |

**Posture words:** `private → none`, `listed → list`, `shared → read`, `inbox → contribute`, `open → read_write`; everyone is capped at `read_write`; anonymous holds no owner floor, so `inbox` is append-only for anonymous and alter-own for named principals.

**The ladder:** `none < list < read < contribute < read_write` (`manage` parked), each rung strictly including the one below; `contribute` includes `read` (SharePoint, Drive); the blind drop box (`contribute − read`, Plan 9 `-wx`) is a second-axis question beside `run`, not a rung.
