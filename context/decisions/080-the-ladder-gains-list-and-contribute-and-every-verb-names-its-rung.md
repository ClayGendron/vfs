# 080. The ladder gains `list`, `add` and `contribute`, every verb names its rung in one table, and a walk passes a node at `list` on both ends

- **Status:** accepted 2026-10-14 (Clay: "accepted, please implement
  the full 165 spec"; every clarification answered by Clay the same
  day). Spec 165 landed the same day; its landing notes record one
  rule the build added (an overwrite or edit keeps the row's owner,
  below). Amends ADR 070 (the road is derived `list`), ADR 065 rule 5 ("visible
  set" means the readable set), ADR 073 (the label's domain is six
  ranks), ADR 068 (the posture words are the rungs; rule 6: anonymous
  is judged at the addressed path), ADR 074 rule 7
  (a tombstoned `list` row shows bare), and ADR 079 pin 2 (the walk's
  rung is `list` for passing, `read` for contents). Resolves the
  2026-10-07 addendum in `open-questions.md`; `manage` stays parked.
  Amended 2026-10-15 by ADR 082 and ADR 084: `run` is retired, so
  pin 9's "`run` on its own axis" has no verb; executing a program
  is `read` on its entry.
- **Date:** 2026-10-14
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay set the rule on 2026-10-14 — "to
  traverse nodes you need X level of permission on both nodes" — and
  asked for the expanded ladder in its own spec before the graph verb;
  the assistant led three research studies and drafted the pins)

## Context

Today the ladder is `none < read < read_write`. A row is whole or
absent to a caller, and `read_write` on a prefix lets a caller alter
everyone's rows beneath it. Two needs have outgrown that. An agent
should be able to learn "there is a file here you may not read, ask
for access", and walk down to what it may read; the road of ADR 070
does this for directories by derivation but nothing grants it. And a
graph walk must be able to pass a node the caller may name but not
read, as a Unix path walk passes a directory with the execute bit,
without ever showing its contents; with `read` as the only visibility
rung, an `fs` walk and `tree` disagree at every road directory.

The memo `research/2026-10-14-the-permission-ladder-list-and-contribute.md`
measured the live tree, surveyed fourteen systems with Plan 9's full
model first, and stated the rules with worked examples. The facts:

- The pure resolver is rank-generic; the storage half assumes two
  non-none rungs in six places and the verb gates carry eleven level
  literals. The row label is a dense integer, so inserting a rung
  renumbers every stored label.
- Extra compiles are cheap: a caller holding no row at exactly `list`
  has a `list` compile equal to its `read` compile, so compiles alias.
- "Alter only your own rows" already exists as the owner floor
  (executed); what `read` lacks is creation.
- The field's see-the-name rung reveals name and kind; every further
  field is a measured leak. "Own" is keyed by identity everywhere, never
  by a bit. Plan 9 is bits, not a ladder; its walk rule, free `stat`
  and `DMAPPEND` are the parts worth keeping, and it lacks the sticky
  bit.
- `rmedge` gates only the source today and leaks a hidden target's
  existence (executed).

## Options considered

- **Three rungs in the total order (chosen).** `none < list < read <
  add < contribute < read_write`. Pros: one integer label and a `min`
  meet stay; `list` is the road's existing shape, granted; `add` is the
  existing creation branch at a lower rung; `contribute` is the
  occupied branch's overwrite and edit legs at a lower rung. Cons: a
  renumbering of stored labels; `admits` must answer a rung; five
  compiles per caller in the worst case, aliased when unused.
- **Independent bits (Plan 9, NFSv4, Oak).** Pros: expresses the blind
  drop box and traverse-without-names. Cons: the label becomes a
  bitmask, the meet becomes per verb, the range algebra and ADR 072/073
  are rewritten. Rejected.
- **Keep `read` as the only visibility rung and route `fs` walks to
  `tree`.** Pros: no ladder change. Cons: the walk and the edge verbs
  keep answering `not_found` on a road directory; "ask for access" has
  no state. Rejected by Clay's rule.
- **One rung named `contribute` with the sticky-bit meaning** (the
  memo's draft). Rejected by Clay once the precedent was verified:
  SharePoint's Contribute and Drive's Contributor edit others' items,
  so the word must carry edit-any, and the own-only step is `add`.

## Decision

Twelve pins.

**The ladder:**

1. **`none < list < read < add < contribute < read_write`**, a total
   order, each rung strictly including the one below; `manage` stays
   parked. `LEVEL_RANK` is dense 0..5; `everyone_level` stores the rank; the
   landing bumps `SCHEMA_FORMAT_VERSION` and old mounts are
   re-provisioned, as every format bump before it. Dense ranks:
   `manage` would append, not insert.
2. **`list` reveals path and kind and nothing else.** Not size, times,
   version, owner, hash, child count or body. A `list` directory lists
   only children at `list` or above. `read` on a `list` row answers
   `permission_denied`, never `not_found`: the row is visible, so the
   refusal confirms only what the listing already showed (ADR 065
   rule 2). Every mutation on a `list` row is `permission_denied`,
   decided before the name is looked up — including a creation at an
   occupied `list` name (`mkdir(exist_ok=True)`, `write` without
   overwrite), which is judged by the row's rung, never answered
   `exists` or `unchanged`. A tombstoned `list` row answers a plain
   `not_found` on the live side: the trashed hint and its `deleted_at`
   ride only on a tombstone the caller may `read`.
3. **Two rungs between `read` and `read_write`, each with the field's
   meaning.** `add` is `read` plus the right to create rows beneath the
   prefix: the sticky directory (Unix `/tmp`), afs's `create`, NFSv4
   `ADD_FILE`. `contribute` is `add` plus the right to overwrite and
   edit any row beneath the prefix, but not to trash, move or restore
   one: SharePoint's Contribute ("Read permissions, plus: Add Items,
   Edit Items …", verified 2026-10-14) and Drive's Contributor ("view
   the file, add comments, and edit the file"; trash needs Content
   manager), the shape Clay asked for the word to keep. It is coherent
   in vfs because every overwrite mints a version, so a contributor's
   edit is always recoverable and trash is the one act that feels
   destructive. Altering and removing one's own rows is the owner
   floor, which every rung carries for a single named subject; a set
   holds a member's floor on that member's own rows wherever every
   other member holds the rung by grant (ADR 064, ADR 066), and
   anonymous holds none; so an `add` holder trashes and
   restores its own rows, a `contribute` holder edits anyone's and
   trashes only its own, and `read_write` does everything. The write
   gate's creation branch judges at `add`; its occupied branch judges
   at `contribute` for overwrite and edit and at `read_write` for
   delete, move and restore, the owner floor riding each. A `write` at
   a tombstoned row is a restore, judged at `read_write` or own
   (Clay, 2026-10-14): a deleted row keeps its name and its owner until
   a permanent delete clears it, so nobody else revives it at
   `contribute`. There is no
   byte-append rung: vfs has no append verb; a later one maps to `add`
   on the row. A directory's owner has no extra reach over rows it does
   not own: the floor stays per row. (The memo recommended one rung
   named `contribute` with `add`'s meaning; Clay split it on
   2026-10-14 once the precedent was verified.)
4. **The blind drop box is not a rung.** "Add but never read others'
   rows" is `add − read` (Unix `733`, Plan 9 `-wx`); it breaks
   the order and joins `run` on the second-axis list. Who may read a
   drop-in folder is answered by ownership and per-sender `contribute`
   grants.

**The rules:**

5. **Traverse on both endpoints.** A walk passes an edge only when the
   caller holds `list` on both endpoints. A `none` node never enters
   the frontier; a `list` node enters and is returned bare (path, kind,
   depth); a `read` node is returned whole. `meet` may route through
   `list` nodes and `minimal=True` may strip them. (Plan 9's walk rule,
   strengthened to both ends because vfs returns the node it reaches.)
6. **A verb's rung is the rung of the field it reads.** Names, kinds,
   children and edge types are `list`-class; bodies, metadata, measures
   (edge weight and distance) and statistics are `read`-class. `glob`
   matches `list` rows; `grep` and `glean` never search, count or rank
   one; "visible set" in ADR 065 rule 5 means the readable set; degree
   counts and stored link signals count only edges with both endpoints
   at `list` or above. An edge touching a `list` node carries its type
   and not its weight or distance (Clay, 2026-10-14).
7. **The road is derived `list`.** A caller's effective level on a
   directory is the greater of its granted level and `list` when a row
   at `list` or above lies beneath. Nothing changes for `ls`, `tree`,
   `glob`, `stat`, `read` or any write; `graph` and the edge verbs now
   see a road directory as a `list` node and pass it. The road stays a
   per-call derivation, never a compiled span. No rung for "traverse
   without even the names" is added.

**The table:**

8. **One verb-to-rung table in `ops.py`.** Every `Op` has an entry
   naming the rung it needs on its target, on a fresh target it
   creates, and on a row it only passes or reads; the gates and the
   read views consult the table and carry no level literals. A drift
   test pins one entry per `Op` and the invariants: a mutation never
   sits below `add`, a read never mints, creating is never harder
   than modifying.
9. **The entries**: `stat`, `ls`, `tree`, `glob` at `list`; `read`,
   `grep`, `glean` at `read`; `graph` passes at `list` and returns
   contents at `read`; `write` of a new path and `mkdir` at `add`;
   `write` of an existing row and `edit` at `contribute` or own;
   `delete` and `restore` at `read_write` or own; `move` at
   `read_write` or own on the source subtree and `add` at the
   destination parent; `copy` at `read` on the source subtree and
   `add` at the destination; `mkedge` and `rmedge` at `contribute` or
   own on the source (an edge is an edit of the source row's facts) and
   `list` on the target; `grant`, `revoke`, `grants` at
   `read_write` until `manage`; `sweep`, `posture` and the membership
   verbs on the developer plane; `run` on its own axis. `mkedge`'s
   target is at `list` (rule 2: the walk may follow it, so the caller
   may name it); `grants` on a `list` path answers `not_found`, as the
   road does today.
10. **`rmedge` checks its target at `list`.** A hidden target and an
    absent target answer the identical per-row record `rmedge` already
    gives an absent one — a `not_found` warning naming the source and
    the target, the batch committing what it found — so neither the
    row's answer nor the batch's outcome reveals a hidden row (Clay,
    2026-10-14). This closes a leak that exists today.

**The machinery and the words:**

11. **`Visibility` carries one compile per rung a verb can need and
    `admits` answers a rung**, not a bool; callers compare it with
    their table entry (`Rights.admits` itself stays a bool at its
    level). A `Resolution` holds a mapping from rung to `Rights`; when
    no row and no pending posture sits at exactly rung L, `at(L)` is a
    `Rights` at level L built on the same compiled pieces as `at(L+1)`
    — the pieces alias, never the `Rights` object, because a `Rights`
    compares and admits by its own level. Every gate leg that passes a
    row it has seen compares the row's rung with its slot of the verb's
    entry: `traverse` for a source it only reads (`copy`) and for an
    edge target, `create` for an occupied creation, `primary` for the
    occupied branch; a leg whose slot is `list` passes a road
    directory. The road probes run at the `list` compile. The bare
    projection is one function serving granted `list` rows and road
    directories alike. A tombstoned `list` row in the trash view shows
    bare with no `deleted_at`. An old-format mount is re-provisioned,
    as every format bump before it (specs 143, 162): there is no
    in-place relabel door.
12. **A posture is named by the rung everyone holds.** The posture
    words are the ladder's own: `none`, `list`, `read`, `add`,
    `contribute`, `read_write` (Clay, 2026-10-14: "go with 1 for
    sure"). `open`,
    `shared` and `private` retire; `posture("/", "read_write")` is the
    default ADR 068 chose under its old name, and the serve-time
    refusal keys on that rung. Everyone stays capped at `read_write`.
    An `add` or `contribute` posture is readable by all, unlike a drop
    box. Anonymous owns nothing (ADR 068 rule 5: a NULL `owner_id`,
    executed 2026-10-14) and holds no owner floor, so under an `add`
    posture anonymous may create and may never alter or trash anything,
    its own creations included, and under a `contribute` posture it may
    also edit any row but still trash none; a named principal alters
    and trashes its own. **Anonymous is judged at the addressed path**
    (Clay, 2026-10-14), the same deepest-posture-wins rule every named
    caller already gets: the `unauthenticated` refusal compares, per
    target, the lowest rung the verb can need there (`create` on a fresh
    name, `traverse` on a source it only reads, `primary` otherwise)
    with the level the posture rows on that path's chain give everyone
    — read from the posture rows, never from the stored label, which
    lags during a relabel — not with the mount root's row alone. A
    pattern scope is judged at each pattern's literal prefix; `tree`,
    `ls` and `stat` at the path named; a two-path verb at each path;
    a batch per target. Anonymous never derives the road (Clay,
    2026-10-14): under a `none` root with an open `/scratch`, an
    anonymous `ls("/")` is `unauthenticated` and `ls("/scratch")`
    works — the Unix and Plan 9 answer for the `other` class, where
    listing a directory needs read on it and no road exists for
    anyone; the road is the SharePoint and Drive precedent ADR 070
    chose for named callers. So `posture("/", "none")`
    with `posture("/scratch", "read_write")` lets an anonymous
    `write("/scratch/hello.txt", …)` create the file and refuses the
    same call at `/notes.txt`. ADR 068 rule 6 is amended to that
    effect.

## Consequences

- **Easier:** "ask for access" has a state; the walk and `tree` agree;
  one table replaces sixty-odd level literals; the owner floor does the
  work of "own only"; the road and `list` share one projection and one
  set of refusals; `graph` reads its rung from the table and spec 164
  needs no rights code of its own.
- **Harder:** every stored label renumbers once, so an old mount is
  re-provisioned; `Visibility.admits` changes type and twenty-one call
  sites compare against a rung; the listing verbs
  carry two needs; the cache weight grows for principals holding the
  new rungs; ADRs 065, 068, 070, 073, 074 and 079 carry amendments.
- **Committed to:** spec 165 implements pins 1–12; the regression pin
  is the executed road baseline (every line unchanged, new rows only
  where `list` is granted); `graph` traverses at `list`; the `rmedge`
  leak closes in the same landing; the README's permission strings
  name six rungs and six postures.
- **Added at the build (2026-10-14):** an overwrite or an edit keeps
  the row's owner. The tree had stamped the last writer as owner on
  every overwrite (a documented rule in
  `docs/explanation/ownership-and-attribution.md`); under pin 3 that
  rule let a `contribute` holder take a row in one write and trash it
  in the next, so it went: ownership is set at creation and moves only
  by a permanent delete (ADR 064 rule 5 extended). Flagged to Clay at
  the landing.
- **Not decided here** (pointers in `../open-questions.md`): `manage`;
  group ownership; an append verb.

Evidence: `research/2026-10-14-the-permission-ladder-list-and-contribute.md`
and its studies under `research/studies/2026-10-14-permission-ladder/`
(the impact map with the compile measurement and the road baseline; the
fourteen-system survey with Plan 9 first; the worked examples and the
executed `rmedge` leak); `research/2026-09-28-traverse-visibility-unix-plan9.md`;
ADRs 062–074 and 079.
