# Mirage: the design patterns worth learning from, mapped onto vfs

- **Status**: research memo (commits us to nothing; feeds a positioning
  refresh, spec 070 (principal-scoped sessions), spec 058 / ADR 021 (row
  grants), spec 054 (`serve()`), and the "vfs Catalog" plane named in
  ADR 058)
- **Date**: 2026-09-04
- **Owner**: Clay Gendron
- **Question**: Mirage (Strukto AI) is the one project in the field that
  is building the same product as vfs — a unified virtual filesystem for
  agents, mounted from many sources, with per-path permissions. What does
  it do really well — in code and in the concepts it abstracts — and
  where does that show an area vfs should improve?
- **Method**: fresh clone of `strukto-ai/mirage` into `~/Git/Repos/mirage`
  (upstream default branch `main`, commit `67389cc`, 2026-09-03), a
  line-level read of its design digest (`AGENTS.md`, 705 lines — every
  rule carries the bug that motivated it), its docs (`docs/home/*.mdx`),
  and the Python packages that own each concern (`types.py`, `resource/`,
  `ops/`, `policy/`, `workspace/mount/`, `workspace/executor/fanout.py`,
  `workspace/node/admission.py`, `core/hierarchy/`, `core/postgres/`,
  `cache/`, `watch/`, `errors/`, `agents/`, `provision/`,
  `workspace/snapshot/`). Then a read of the vfs seams each pattern maps
  onto (`src/vfs/base.py`, `permissions.py`, `results/kinds.py`,
  `results/envelope.py`, `storage/protocol.py`, `models/entry.py`,
  `models/version.py`, `ops.py`) and the ADRs and specs that govern them.
  Cites and describes only — every line of vfs code stays ours.
- **License**: Apache-2.0 (`LICENSE`, re-confirmed on the refreshed
  checkout). Study freely; copy nothing.
- **Sources line**: `strukto-ai/mirage` @ `67389cc` (2026-09-03),
  2,126 commits since 2026-05-06, 30 authors, 1,728 commits (81 %) by one
  author. Python: 208 k source lines, 223 k test lines. TypeScript:
  216 k source, 178 k test. 56 registered resources, 63 builtin command
  packages. Public numbers: 3.6 k stars, v0.0.6 tagged 2026-09-03.

---

## 1. Bottom line

Mirage and vfs made the same bet — the filesystem is the agent's
interface, and enforcement belongs on the data itself — and then spent
their effort in opposite places. Mirage spent it on **breadth and the
shell**: 56 backends, a bash rewritten from the ground up so pipes work
across S3 and Slack, a FUSE adapter, sandboxed runtimes, a TypeScript
twin. vfs spent it on **depth and the database**: one SQL backend that is
correct on five engines at 10,000-row batches, four search verbs with a
fused ranker, typed edges, a Rust engine, versioned and reversible
mutation.

The overlap is the **namespace and the permission model**, and there
Mirage is ahead in three specific ways vfs should close:

1. **Hide is a first-class verb, distinct from deny.** A hidden path
   answers `ENOENT` and drops out of every listing; a denied path is
   present and refused. vfs has only read/read-write today, and
   `permission_denied` is a reserved kind nothing produces. Spec 058's
   ladder already has an `(invisible)` rung — Mirage supplies the exact
   leak rules that rung needs (§3.7, §4.1).
2. **The permission gate is explainable and askable.** `ws.explain(line)`
   renders the exact refusal an agent would see without running the
   line, from the same table the gate uses; an `ask` rule turns a refusal
   into a question in a decision ledger a host answers. vfs's gate is
   pure and cheap to expose the same way, and a `pending` answer is one
   child kind away in its hierarchical error vocabulary (§3.9, §3.10,
   §4.2, §4.3).
3. **Facts a rule fired on are structured, not prose.** Mirage's
   `Refusal` record carries the reason, the rule's source, and the scope
   beside a bash-voiced stderr that says nothing. vfs's `check_writable`
   puts the winning rule prefix in the message — a load-bearing fact in
   the one field its own contract says no consumer may parse (§4.4).

Beyond permissions, four patterns are worth lifting when the roadmap
reaches them: the **hierarchy kit** for API-backed mounts (one
declarative tree description that readdir, stat, read and search all
classify through, so "the file surface and the search surface cannot
disagree"); the **snapshot/drift triad** (cache is the optimization,
fingerprint the verifier, revision pin the recovery); **stale-write
protection at the agent-tool tier**; and **notify-driven watch** where
cache invalidation completes before delivery. And one positioning fact
stands out: Mirage mounts a *foreign* Postgres schema as files
(`<schema>/tables/<t>/rows.jsonl`); vfs's database backend stores vfs's
*own* tables. "Mount your database as a file system" means different
things in the two READMEs (§4.7).

What vfs should **not** take: the virtualized bash, GNU-byte-exact
conformance, FUSE, the breadth-first backend catalog, and the TS twin —
each is a consequence of a bet vfs deliberately did not make (§5).

---

## 2. What Mirage is

**Shape.** A `Workspace` holds a mount table (`prefix → Mount(resource,
mode)`), a policy stack, a session manager, a namespace node table (the
symlink and attribute overlay), a cache, and an observer. An agent
reaches it three ways, all through one dispatcher: a bash line
(`ws.execute("grep -r x /s3 /slack")`), a typed op facade (`ws.fs.read`),
or a kernel mount (FUSE / FSKit / WinFsp). The docs describe four layers:
agent → Mirage bash + VFS → dispatcher + cache → the mounted services
(`docs/home/architecture.mdx`).

**Mount modes** form a cumulative ladder `READ < WRITE < EXEC`
(`types.py` `MountMode`, `weaker_mode`). A profile can weaken a mount's
mode for one session and never raise it.

**The resource abstraction.** `BaseResource` (`resource/base.py`) is a
class with an `accessor` (the backend handle), an index cache, a table of
ops, a list of registered commands, and a handful of declared facts:
`SUPPORTS_SNAPSHOT`, `SIZES_ALWAYS_KNOWN`, `caches_reads`, `index_ttl`,
`storage_id()`, `statfs()`, `delta_hook()`. `GenericResource`
(`resource/generic.py`) builds a whole backend from one `CommandIO` table
whose minimum is `readdir`/`read_bytes`/`stat`; every optional slot
unlocks more surface (`write` enables the mutation family, `find` and
`du_size` become native fast paths).

**The bet.** Mirage's own line is "a Virtual Terminal for AI Agents": the
filesystem gives context, virtualized CLIs (`git`, `slack`, `ntn`) give
actions, routed runtimes (in-process, monty, WASI, Docker, E2B, SSH)
give compute, and profiles give control. Everything is spelled in bash.
Six agent tools ride on top (`execute`, `read`, `write`, `edit`, `ls`,
`grep`) with adapters for seven frameworks and an MCP server.

**How it differs from vfs in one table.**

| | Mirage | vfs |
| --- | --- | --- |
| Unit of truth | a shell line, parsed by tree-sitter | a verb call, `paths in → Result out` |
| Agent surface | bash text; six tools; MCP | typed `Result`; `cli` is a front door that re-enters verbs (`ops.py`) |
| Backends | 56, mostly API-backed, rendered on read | one SQL backend owning its schema; in-memory; adapters |
| Search | `grep` / `rg` / `find` with per-backend push-down | `glob` · `grep` · `glean` · `graph`, fused ranking, typed edges |
| Mutation | POSIX ops; snapshot + git-style versioning of the workspace | versioned entries, trash/restore, reversible batches |
| Permissions | profiles: allow/ask/deny on commands, hide/show on paths, mode narrowing, script policies | per-mount `PermissionMap` (read / read_write), composed most-restrictive-wins; principals and grants designed, not built |
| Scale posture | agent loops; per-command output caps; bounded API walks | 10 k-row batches on five engines; bounded statements by declared budget |
| Engine | Python + TypeScript twins, parity-gated | Python + Rust kernels |

---

## 3. What Mirage does well

Each pattern below names the mechanism, where it lives, why it is good,
and what vfs has today. Verdicts are collected in §4.

### A. Namespace and routing

#### 3.1 One door

Every plane — the shell, the typed `ws.fs` facade, FUSE, the runtime
guests, `find -delete`, the warm cache — reaches a backend through the
workspace dispatcher, and the dispatcher runs the whole pipeline once:
link follow, session grants, admission policies, cache read-through,
namespace structure, write invalidation. `ops/ops.py` says why in its
docstring: a second pipeline "drifted from the real one exactly as
expected: it served no cache, saw no namespace structure, and fired the
gates only when a caller remembered to hand it policies." `dispatch` is
therefore a required constructor argument; there is no workspace-less
mode.

*vfs today:* the same principle, already pinned — every public verb
routes through `_dispatch_entry` / `_call_storage`, the storage protocol
is the only seam, and `cli` is a meta-verb that re-enters public methods
so "every gate fires on the real verb" (`ops.py`). Parity.

#### 3.2 The name plane lives above every backend

Symlinks, mount boundaries, the `chmod`/`chown`/`touch` attribute
overlay, and the child names a directory owes to deeper mounts are
**namespace state, not backend state** (`AGENTS.md` "Symlinks",
`workspace/mount/namespace/`). No resource stores or reports a link; a
new backend needs no symlink code at all. Commands consume these facts
through one injected object, `NamespaceView` (`ops/types.py`):
`links: LinkView`, `mounts: MountView`, `stat_overlay`, `child_mounts`,
`user`. A command opts in by *reading a field*; there is no registry of
link-aware commands and no keyword threaded through every builder. The
docstring states the rule: "a command that grows a new name-plane need
adds a field read, not a new keyword threaded through `execute_cmd`,
every builder, and the generic."

*vfs today:* the mount table is the router's, mount-point directories
are stored rows in the owning storage (ADR 009), and there are no
symlinks or attribute overlays. The bind-alias story (roadmap 018) is
where this pattern applies: aliases as namespace-owned state that no
backend sees.

#### 3.3 Two questions about a mount boundary, because one name leaked

`MountView` deliberately has two methods that look alike:
`descendants` (every mount root under a path, for a caller *avoiding*
one) and `visible_descendants` (only the ones this session may be told
about, for a caller *naming* one). The docstring explains: a hidden
mount still shadows the parent backend's keys, so those keys must stay
out of a walk's entries and a directory's total — but its *name* is the
one thing the hide exists to withhold. `tar` prunes by one and warns by
the other. `ops/namespace_view.py` applies the same rule to listings:
`visible_child_segments` tests the *full* path of each mount or link
that owes a directory a segment, never the segment, because testing the
segment "leaked the name of a namespace-only ancestor whose only mount
the session hides."

*vfs today:* `_shadow_filter` drops rows under deeper bindings; there is
no notion of a binding the caller may not be told about. This is the
enumeration half of the hide verb (§3.7).

#### 3.4 Namespace-only directories: listing and stat must agree

`/data/x` exists when a mount sits at `/data/x/y` even though the
`/data` backend holds nothing at `/x`. `namespace_listing` and
`namespace_stat` derive both answers from one union of mount prefixes
and link paths, "so the shell and the ops surface cannot disagree about
what a directory holds," and a directory `readdir` can serve "must stat
as a directory, or `os.walk` and `Path.is_dir` break on it."

*vfs today:* moot by construction — vfs stores the mount-point directory
as a row (`bind` requires an existing empty directory; `add_mount`
mkdirs first). vfs's answer is stronger: the shape is stored, never
synthesized. Keep it.

#### 3.5 Fan-out over nested mounts

`workspace/executor/fanout.py` reruns a traversal command
(`find`, `du`, `grep -r`, `rg`, `ls -R`) once per descendant mount,
adjusts `-maxdepth`/`-mindepth` by the prefix delta, filters the parent
mount's output for lines under a descendant prefix (the parent backend
may hold shadowed keys), folds `du` blocks into one tree, path-sorts
single-operand `find` so a mount root prints before its descendants
(GNU's invariant), and lets a descendant that answers 127 ("does not
serve this command") contribute nothing rather than fail the walk. The
descendant list is session-filtered (`_allowed_descendants`): the
comment records that enumerating through the raw registry "is exactly
how `grep -r x /` leaked a walled-off mount's contents."

*vfs today:* `_route_fanout`, `_tree_region`, `_shadow_filter`, the
capability-skip as an info-severity record, and the zero-progress merge
rule cover the same ground, in typed rows rather than rendered text —
the row shape makes the merge trivial where Mirage has to re-parse `du`
lines. Parity, with vfs's shape the better one.

### B. Permissions and policy

#### 3.6 The profile is the one document; a session binds one; it only narrows

`SessionProfile` (`policy/profile.py`) is "the whole permission document
a session runs under ... the only place permissions are written. There
is no workspace-wide block and no mount-owned block above it." Its
blocks: `commands` (`allow` — the session's tool set; `ask`; `deny`),
`paths` (`hide`, `show`), `vars` (`hide`), `mounts` (per-prefix `mode`,
`commands`, `paths` — narrowing only), `cwd`, `env`, and `policy` (a
script and the engine it runs on). The document is frozen "so two agents
with the same profile share one object and neither can bend the other's
view." A session names its profile at creation and keeps it for life;
the workspace's default session follows `profiles.default`
(`docs/home/permissions.mdx`).

Two rules decide a line against it, and the docstring calls them "the
whole law": a rule naming no path is read by verb (deny before ask
before allow) wherever it is written; a rule carrying paths, and every
hide, is read by **anchor depth** — the number of literal components
before the first wildcard (`utils/hidden.py` `anchor_depth`;
`/repo/sealed/*` is 2, `/repo/*` is 1, `*.key` is 0) — the deeper entry
wins, ties break by verb.

*vfs today:* `PermissionMap` is per-mount configuration in code, two
values (`read`, `read_write`), longest-prefix override resolution,
composed along the mount path most-restrictive-wins (`permissions.py`,
ADR 006). Longest prefix *is* anchor depth for exact paths; Mirage's
contribution is the extension to patterns and the explicit "only
narrows" contract between a mount's declared mode and a session's view.
Spec 070's session facade is where a profile-shaped document would land.

#### 3.7 Hide is not deny

"Hiding is not a refusal. A hidden path answers `ENOENT`, so the session
never learns the name; a denied path stays in the listing and fails when
read. The same `/vault` can be denied for one role and hidden for
another." (`docs/home/permissions.mdx`). The mechanics that make the
promise hold:

- A hide is **subtree-closed on all three planes** — an exact entry
  contains its subtree, a component pattern (`*.env`) matches any
  segment, an anchored pattern is tested against every ancestor
  (`utils/hidden.py` `hide_depth`).
- A hide group may carry a `reason`, kept in an **operator-only side
  table** (`HideReason`) and never rendered: "a reason on a nonexistent
  path would confirm the path exists."
- `show` re-opens a subtree inside a hidden region when its anchor is
  deeper, and may state the mode below its anchor — same anchor-depth
  rule, so hide and show are one axis.
- An **unlisted command is "command not found" (127)**, not "permission
  denied" (126), "so an unlisted tool never leaks that it exists"
  (`policy/types.py` `Explanation`). The 127 row carries no `Refusal`
  record for the same reason.
- Native fast paths (a backend's own `find`, `du -s` asking for one
  total) **fork to the guarded walk** when a hide could cover an entry
  inside the subtree they answer for, and stay native when none can
  (`context/session_context.py` `hidden_paths_intersect`) — so a
  push-down cannot be used to count what the session cannot see.

*vfs today:* none of this. `VFSErrorKind.permission_denied` is declared
(EACCES) and mapped to an exception, but nothing in `src/` produces it;
reads are never gated. ADR 006 names "permission-filtered enumeration
(ls/glob/grep that hide unreadable subtrees per principal) must
eventually be pushed into backends" as the hard part; spec 058's ladder
is `(invisible) < read < read_write`. Mirage's rule set is the
specification that rung needs.

#### 3.8 Per-subject judgment

A line is judged subject by subject (`policy/match/rule.py` `Subject`,
`subjects`; `policy/match/decide.py` `decide`): every path the line
names first, then the operands of a subtree command (`rm -r /x` takes
`/x/locked/*` along) with `mv`'s destination special-cased (an ancestor
of the scope does not count). The docstring records the bug: "with
`deny cp /protected/*` and a deeper `ask cp /review/deep/*`,
`cp /protected/secret /review/deep/out` is the source's deny, and reading
one best match for the whole line answered it with the destination's
ask instead, so a nod meant for the destination carried the protected
file out." Two comparators are deliberately mirror images: *within* one
subject specificity leads (depth, then verb); *across* subjects severity
leads (a deny anywhere refuses the line). Every ask that won a subject
is reported (`Ruling.asks`) and the door requires all of them.

*vfs today:* `_route_two_path` gates both ends of a `move` and the
destination of a `copy` (`write_rels`), so the write half of this is
already per-subject. The read half does not exist because reads are not
gated. When they are (§3.7), the source of a `copy` becomes a subject.

#### 3.9 Ask, and the decision ledger

An `ask` rule guards a command instead of refusing it outright. The
line does not run; the agent reads `Permission denied` (126) with a
`pending` refusal record naming an ask id; the question lands in
`ws.decisions` for a host to answer through an `on_ask` handler, the
CLI, or REST. `policy/decisions.py` keeps **one record type, one
store**: a `Decision` with no outcome is a question waiting, one with
an outcome is a question settled, "so listing what is waiting and
reading what was settled are the same query over the same records
rather than two stores that can disagree" — the docstring says the two
stores existed once and did disagree. An answer's reach is its `Scope`:
`ONCE` covers the exact line (compared field by field —
`command`, `argv`, `cwd` — never by re-deriving an id), `SESSION` covers
every line the same rule asks about; nothing reaches another session,
and an answer never re-opens a deny. A run killed while the host is
deciding is `Abandoned`: the eventual answer is dropped rather than
banked "against a run that no longer exists," which the next identical
line would otherwise take with nobody asked.

*vfs today:* no ask. The hierarchical kind vocabulary could carry it as
a child of `permission_denied` (§4.3).

#### 3.10 Explain: the dry run is the gate

`ws.explain(line, session_id)` runs the admission gate without running
the line and answers with an `Explanation` whose `exit_code` and
`stderr` "come out of the one outcome table, so an explanation of a
refused line is byte-identical to the refusal" (`policy/types.py`;
`workspace/node/explain.py`). It reports the outcome, the rule that
spoke, where in the document it was written (`source`: `top` or
`mounts./repo`), the operand it matched, and the paths the rules were
shown after hides dropped what the session cannot see. An ask reads the
session's standing grants and stops: "a dry run must not spend one,
record a question or reach the host."

*vfs today:* nothing, but the gate is pure — `_gate_params`,
`_gate_entry`, `check_writable_composed`, `_busy_guard` — and already
returns the `Result` a refusal would carry. Exposing it is cheap (§4.2).

#### 3.11 The refusal record beside a voice that says nothing

`Refusal` (`types.py`) rides `IOResult.refusal`: `kind` (`deny`,
`pending`, `failed`), `reason`, `policy` (the class that spoke, stamped
by the chain "so no policy names itself"), `scope`, `ask_id`. stderr
keeps bash's voice, "which says nothing about who refused or why." A
command-scoped deny is `<cmd>: Permission denied` at 126; an
operand-scoped one keeps GNU's voice (`cat: /vault/aws.token: <reason>`,
exit 1) because there the reason *is* the diagnostic. "Exit codes
derive from the plane and the scope, never from a number a policy
picks." An adapter that hands the agent text appends the reason line
once, and only if the text does not already say why
(`agents/io_text.py` `says_why`).

Two supporting rules: `VALIDITY` (`policy/types.py`) pins which action
kinds each hook may return (`pre_command`: Deny | Ask; `pre_ops`: Deny;
`post_ops`: Deny | Limit; `post_execute`: Limit; `pre_session`: Deny) —
"returning a kind the hook cannot carry is a loud `PolicyError`, never a
silent allow." And a policy that raises **fails closed**, naming itself
(`failed=True`).

*vfs today:* `ResultError` is the same idea at the envelope: `kind` for
code, `message` for prose, `data` for machine detail, and the contract
"no consumer may parse `message`." The gap is that `check_writable`
puts the winning rule in the message only (§4.4).

#### 3.12 The entry gate: entries reached mid-walk are judged by the same law

The admission gate judges the paths a line *names*; a walk (`grep -r`,
`find`, `du`, `cp -r`, `tar`) then reaches entries no rule has seen. So
the dispatcher binds an `Admitted` record to the session context for the
command's run, and the commands tier asks it before each read, write, or
listing (`workspace/node/admission.py` `Admitted.check`, `EntryGate` in
`types.py`). Judged paths pass; every other entry runs `io_refusal`
under literally the same comparator as the gate (`better_match`): anchor
depth first, deny before ask at equal depth, an ask satisfied by a grant
the line already holds. The op door has a twin (`op_refusal`) for
entries reached with no admitted command behind them — FUSE, the cache,
the host's facade — where "an ask that wins here is a refusal like a
deny: there is no line to ask about and this door cannot wait on a
host."

*vfs today:* a verb names its targets; storage does the walking inside
one statement. When per-principal read filtering lands (spec 058: "reads
filter sets, writes check points"), the predicate compiled into the
SELECT is vfs's entry gate — the same idea at the right tier for a
database. The lesson to keep is the *one comparator* rule: the predicate
and the point check must agree on precedence.

#### 3.13 Scriptable policy in a sandboxed engine

A profile may name a `policy: {script, runtime}`; the script defines
`pre_command(ctx)`, `pre_ops(ctx)`, `pre_session(ctx)` and answers with
`return`. `ctx` is plain JSON (`policy/script.py` `script_context`):
the command's name, argv, tokens, program, resolved paths, operands,
whether it walks; the session id, agent, cwd; the mount prefixes. The
engine is one of the workspace's runtimes (monty is the worked example),
so a python policy "may `open()` a file the line names and judge what it
holds, not only what it is called," and the policy's own reads clear
the op door without being judged by the policy that is asking
(`_POLICY_READ` contextvar). Like every policy, a script "can only
restrict, never grant past a deny."

*vfs today:* nothing, but ADR 021 §1 says subtraction "enters as a
policy-layer expression over grants, never as a row." Mirage's script
policy *is* a policy-layer expression engine, and monty is already in
vfs's reference set for the hermetic-runtime direction. One engine could
serve both.

#### 3.14 Limits aggregate per field, tightest wins

`Limit` (`types.py`) carries `max_bytes`, `max_lines`, `timeout_seconds`,
`on_exceed`, each field annotated with its own `Aggr(rule)`
(`_min_positive`, `_prefer_error`); `Limit.aggr` merges any number of
limits by each field's declared rule. Bounds stack across policy
composition, cross-mount fan-out, and layered config with one law.

*vfs today:* row caps (`_cap_rows`), the hop budget, and the fan-out
deadline spec (051) each carry their own merge. A per-field aggregation
declared beside the field is a tidy shape if those ever become one
`Budget`.

### C. Backends

#### 3.15 The hierarchy kit: one tree description, every verb classifies through it

`core/hierarchy/` is Mirage's best abstraction. A backend describes its
fixed API tree once as a tuple of `Scope`s (`core/hierarchy/scope.py`):
each scope is a sequence of literal segments and `Slot`s, a slot has a
`Codec` (suffix, validator — `INT_JSON`, `DATE`, `JSONL_NAME`), an
optional `id_key` for `<label>__<id>` composite segments, and may be
`variadic` (Notion pages nest arbitrarily). `make_detect_scope` compiles
the table into a classifier. Then `make_readdir`, `make_read`,
`make_read_range`, stat, unlink and **search** all classify through the
same `detect_scope`; the comment on `core/postgres/scope.py` states the
payoff: "readdir, stat, read AND the grep/rg search push-down all
classify through it, so the file surface and the search surface cannot
disagree about what a path means."

The kit owns everything a backend author would otherwise re-spell:
existence `guards` (so a schema that does not exist is `ENOENT` even on
a warm cache), the index probe and write-back, `entry_listers` (a
directory proven by its parent's listing costs no API call), a
`DirListing` with `seeds` (one fetch that proves descendant listings
caches them too), `partial` listings that must not be cached as the
directory, and `windowed` readers for kinds whose content is windowed at
the source (Postgres rows take `limit`/`offset` pushed into the query).
`per_accessor` caches a config-shaped route table per mount for backends
whose tree depends on mount config.

*vfs today:* one backend, whose tree is stored rather than derived, so
the kit has no consumer yet. The mission says "eventually live APIs";
roadmap 020 mounts remote backends. When an API-backed mount arrives,
this is the shape — and the invariant to carry over now is the one in
that comment: **glob, grep and glean must classify a path the way
`stat` does**, which vfs already holds for its SQL backend by sharing
one `scope` module (`storage/backends/database/scope.py`).

#### 3.16 Postgres as files

`core/postgres/` renders a *foreign* database: `database.json`
(schemas, tables with row/size estimates, views, all FK relationships),
then `<schema>/tables/<table>/{schema.json, semantic.json, rows.jsonl}`
and `<schema>/views/...`. `schema.json` carries columns, PK, FKs,
indexes; `semantic.json` carries comments, enum labels, and `pg_stats`
column statistics (best-effort, never runs `ANALYZE` — "a write and a
cost on the user's DB"). `rows.jsonl` refuses a whole read past
`max_read_rows` / `max_read_bytes` with a message that names `head`,
`tail`, `wc`, `grep`, or `limit`/`offset` as the way in
(`core/postgres/read.py`). `grep` pushes down to `LIKE`/`ILIKE` over the
text-typed columns with wildcards escaped (`search.py`), and the
rendered metadata files are grepped by rendering and scanning, because
"the only honest way to match them is to render and scan." Two size
rules are enforced everywhere: `FileStat.size` is the rendered content's
length or `None`, never a storage-side number ("a confidently wrong
size is worse than an unknown one"), and `statfs` never fabricates a
total (`CapacityState.NA` for a table surface).

*vfs today:* `DatabaseFileSystem` owns its own tables — entries, chunks,
versions, edges, postings — on the engine you point it at. It does not
expose an *existing* schema as files. See §4.7.

#### 3.17 Declared facts, not sniffed ones

Capabilities are class constants read off the class (`SUPPORTS_SNAPSHOT`,
`SIZES_ALWAYS_KNOWN`, `caches_reads`, `index_ttl`), and the parity gate
dumps them from class *declarations* because "construction is not
inert — `buildResource('github', {})` issues an HTTP request and
`postgres` opens a connection" (`spec/README.md`). `delta_hook()`
returns `None` by default rather than living behind a capability
protocol, because "the protocol only ever answered 'does this resource
have one', which a None default answers with no `isinstance`, no import,
and no second place to keep in step." `storage_id()` lets two mounts
over one bucket refuse a self-move rather than copy an object over
itself; the default treats every instance as its own storage — "the
safe direction to be wrong in."

*vfs today:* `capabilities()` is self-declared ("never structural
sniffing"), traits are a declared vocabulary with a drift test, and
`MountMeta.caps = declared_caps - deny_ops` is derived at construction so
the three cannot drift. Parity; `storage_id` is the one small idea worth
noting for roadmap 019 (union mounts and shadow resolution), where two
bindings may front one engine.

#### 3.18 A backend from one table

`GenericResource` turns one `CommandIO` table into a full backend: the
generic command set is generated, glob resolution is wired, ops for
FUSE and os-interception are derived, and `overrides` / `commands` /
`ops` are the escape hatches a builtin uses too. `_DIRECT_OPS` maps the
table's slots onto the attribute surface an out-of-tree caller already
reads off `ram`, `s3`, `disk`, so a kit backend "publishes exactly what
it can answer."

*vfs today:* the protocol families (`SupportsRead` as the verb minimum,
then `SupportsMutation`, `SupportsPatternSearch`, `SupportsGlean`,
`SupportsGraph`, `SupportsRun`) are the same idea expressed as
protocols. What vfs lacks is the *generator*: a backend author must
write `glob`, `grep`, `tree` themselves. A `GenericStorage` that derives
`ls`/`tree`/`glob`/`grep` from `read`+`stat`+a listing primitive would
lower the floor for adapters and remote mounts — a real ergonomic gap,
but only once there is a second in-process backend to serve.

### D. Cache, watch, snapshot, versions

#### 3.19 Cache coherence discharged at the mutation site

`CacheManager` (`cache/manager.py`) owns "post-mutation cache coherence
for one mount": a write has two consequences — the file-cache entry is
stale and the parent listing in the index (including *negative*
knowledge that the path did not exist) is stale — and both are
discharged synchronously where the mutator already emits its observe
record, "so invalidation happens before the next command in a pipeline
runs." The index distinguishes `invalidate` (mark stale, keep) from
`clear` (empty), because a backend whose index *is* its listing "cannot
tell an invalidation from an empty repository." The cache key is
*derived* from the virtual path against the manager's own prefix, never
inferred from the caller's `resource_path`, because the earlier version
that inferred "cannot be done ... inferring wrong is quiet rather than
loud — a key one level off simply evicts nothing — which is why it
survived." Read-through wrappers capture the active manager
**eagerly**, because a lazy consumer drains after the mount's scope is
gone (`cache/read_through.py`).

*vfs today:* no cache layer — the roadmap says caching is "a layer (a
`VirtualFileSystem` decorator), not a protocol feature," with
`Entry.version` + `content_hash` as the validation primitives. When that
decorator is written, Mirage's three rules — invalidate at the mutation
site, expire-don't-clear for listings, derive keys never infer — are the
ones to carry.

#### 3.20 Notify-driven watch

`Watcher` (`watch/watcher.py`) runs no background loop. Changes enter
through `notify(FileEvent)` from whatever detection the consumer runs —
a webhook, a queue bridge, a ten-line poll over a resource's
`delta_hook()`. "The one guarantee: cache invalidation for a change
completes before it reaches any subscriber queue, so a consumer reacting
to a change always reads fresh content." A `DeltaHook.pull(root,
checkpoint)` "must not read through mirage's caches; a hook that
consults the read/index cache compares the cache to itself and detects
nothing." `ListingDeltaHook` is the generic fallback: snapshot
`{virtual: fingerprint}`, diff consecutive snapshots. A `MOVE` evicts
both sides; `UNKNOWN` ("precision was lost") evicts the subtree. Watch
scopes are GNU-glob shaped: `/dir/*` is the entries at that level,
`/dir/*/` is everything inside child directories.

*vfs today:* no watch. vfs's versions table makes a `DeltaHook` nearly
free — `updated_at > checkpoint` or `version > checkpoint` is one indexed
range scan — which is a stronger foundation than a listing diff.

#### 3.21 Snapshot, drift, revision pin

A snapshot is one tar: mount configs (secrets redacted), sessions,
history, finished jobs, cache bytes for touched paths, one fingerprint
per remote read, and an optional per-path `revision` where the backend
exposes one (S3 `VersionId`, Drive `revisionId`, a commit SHA). On load,
`STRICT` stats every fingerprinted path against live and raises
`ContentDriftError` before any read; a pinned path skips the check and
reads the exact recorded revision. The docs state the triad: "The cache
is the optimization, the fingerprint is the verifier, and the pin is the
recovery — three independent guarantees that 'what you replay equals
what you captured'" (`docs/home/snapshot.mdx`). Only files the agent
*read* are fingerprinted; a resource opts in with `SUPPORTS_SNAPSHOT`
and must then fill `FileStat.fingerprint`, "a snapshot that claims to
have one" otherwise.

*vfs today:* per-entry revisions (ADR 013/017) give every write a
version and every version a content hash — the *pin* exists natively
for vfs's own store. What is absent is the *session-level* capture: "what
did this agent read, at which version," and the replay that pins reads
to those versions. That is an audit story ADR 058 names and the Catalog
plane would want (§4.8).

#### 3.22 Stale-write protection at the tool tier

`FileVersionTracker` (`agents/file_version.py`) refuses a write to a file
that moved under the agent. Two stamps per path, "because a read and an
edit are different promises": `read` records what the agent was shown,
`read_for_edit` what it is about to rewrite. Stamps cover the
**rendered** bytes, "which is what the read tool hands the agent"; the
key is the path with symlink prefixes resolved, "one key per file, not
per spelling," because an edit through the other name "would find no
prior version and skip the staleness check entirely." After a write,
the tracker re-reads and stamps *what a later read will return*, not
the bytes handed in, because a rendering mount "would make the very
next write or edit look stale with nobody having touched the file."
The `edit` tool refuses when `old_string` is absent or appears more than
once, and `write` refuses to overwrite.

*vfs today:* `conflict` (ESTALE) with `retry_class=refresh` and
`data['version']` exists at the envelope, and `Observation.version` is
on every row, so the storage tier can already refuse a stale write when
the caller supplies the version it read. What is missing is the *tool
tier* that remembers the version on the agent's behalf — the MCP
`serve()` (spec 054) is where a read-stamp / edit-check belongs.

### E. The agent surface and accounting

#### 3.23 Six tools, framework-independent

`MirageToolOperations` (`agents/tool_operations.py`) implements the six
tools once — `execute`, `read` (line-numbered, `offset`/`limit`),
`write` (new files only), `edit` (unique `old_string`, `replace_all`),
`ls`, `grep` — over the workspace, returning a `ToolResult(text,
is_error)`; MCP and each of seven framework adapters
(`langchain`, `openai_agents`, `pydantic_ai`, `claude_agent_sdk`,
`agno`, `camel`, `openhands`) render that one shape. The MCP server
marks `read`/`ls`/`grep` with `readOnlyHint`. The system prompt is built
from the mounts: each resource declares a `PROMPT` and a `WRITE_PROMPT`
(appended when mounted writable), and `Workspace.file_prompt` composes
them (`agents/prompts.py`).

*vfs today:* the verb surface is the wire contract (spec 045) and the
`Result` payload already round-trips MCP structured content; `serve()`
is not built. The two ideas worth taking are small: a per-mount
*prompt fragment* so the agent's system prompt is derived from the mount
table rather than hand-written (the Catalog's "what is in the
namespace" rendered for the agent), and `readOnlyHint` from `READ_OPS`.

#### 3.24 Op records and cost before execution

Every op through the facade leaves an `OpRecord` — op, path, the server
that answered (`ram` for a cache hit), bytes moved, timing — and the
door stamps the report "at the moment of completion, so even a foreign
error the door never defined leaves the transfer on the books"
(`ops/ops.py` `_call`). `network_bytes` vs `cache_bytes` are derived
views. `Producer` (`types.py`) rides the IO envelope naming the command
and the mount prefixes it spanned. `ProvisionResult` (`provision/`)
estimates a line's cost *before* execution — network and cache bytes as
low/high ranges, op counts, optional USD — with a `Precision` lattice
(`EXACT < RANGE < UPPER_BOUND < UNKNOWN`) where "missing knowledge is
carried by precision, not by null fields," and per-operator combiners
(`|`, `;`, `&&` sum; `||` takes a min/max envelope).

*vfs today:* `ResultError.source` stamps provenance per hop; nothing
records per-op cost or cache-vs-network. This is audit, and the Catalog
plane is its consumer (§4.8).

### F. Engineering practice

#### 3.25 Errors named once; every boundary keeps a total table

`FsCondition` (`errors/types.py`) names each condition once; POSIX,
WASI preview1, and monty's CPython errnos each keep only a table from
those names to their own numbers, "and each table's own test fails a
half-added member." One classifier (`errors/classify.py`) maps
exceptions to conditions with class arms before errno arms, most
specific first, and refuses to name a bare `ValueError` `ENOENT` because
backends raise it "for refusals that are not absence."

*vfs today:* `VFSErrorKind` + `KIND_CONTRACTS` + `kind_family` are the
same design, stronger: hierarchical kinds, aliases as permanent
tombstones, a normative retry class and hint per kind. Parity; the
"every table stays total, and a test fails a half-added member" rule
already exists as vfs's drift tests.

#### 3.26 Parity and conformance gates that cannot go stale

`spec/` dumps every command's spec and every resource's capabilities and
config fields from the *live registries* in both languages and diffs
them; `conformance/cases/*.json` pin exact stdout/stderr bytes and exit
codes per backend with an **explicit matrix** ("listing a backend is a
claim of support — a missing command there is a failure, not a skip")
and a `divergence` key as the only way to narrow it; every exemption
file is **stale-checked** — "an entry cannot outlive the divergence it
documents," and "an exemption counts as used only when it actually
suppresses a live divergence." GNU behavior is pinned against
`debian:stable-slim` in Docker before any command's semantics change.

*vfs today:* `tests/storage/test_conformance.py` runs the storage suite
against the in-memory and database backends, and the `db_test` skill
runs it on real engines; the mutant ledger (`standards/mutant-ledger.md`)
is an allowlist. The one rule to lift is *stale exemptions fail*: any
allowlist in vfs's tests (curated mutants, skipped legs) should be
checked against the live tree so a fixed divergence cannot keep its
exemption.

#### 3.27 Meta-tests that enforce the style guide

`tests/commands/test_no_object_annotations.py`, `test_no_raw_flag_reads`,
`test_no_dead_flag_params`, `test_flag_query_names`,
`tests/test_nested_functions_are_closures.py`, and the 1:1 src/test
mirror rule (`AGENTS.md` "Rules") each turn a convention into a red
build. The nested-function test is the sharpest: nesting is allowed
only when the inner function *captures* the enclosing scope; "a helper
written inside a function although it reads only its own arguments ...
rebuilds a function object per call and hides a testable unit where no
test can reach it."

*vfs today:* drift tests pin signatures, traits, observation mirrors,
and the params table; ruff covers imports. Two of Mirage's are cheap to
add and match CLAUDE.md's own rules: no `object` annotations (the
"we did not decide" smell) and nested-functions-must-be-closures.

#### 3.28 The design digest carries the bug that motivated each rule

`AGENTS.md` is 705 lines and almost every rule ends with the failure it
prevents: "which is how `leftover.txt` came to be listed as a child of
`/base`," "that is what made `git add` store a symlink as a regular
file," "a key one level off simply evicts nothing — which is why it
survived." Comments in code do the same. It reads as a ledger of
post-mortems compiled into rules.

*vfs today:* `context/` separates research, decisions, and specs and
records the *why* in ADRs; CLAUDE.md records corrections with the
incident (the `git checkout` rule). Parity in spirit; the difference is
placement — Mirage keeps the ledger beside the code, vfs keeps it in
`context/`. No change recommended; noted because it is why Mirage's
code is unusually legible for its size.

---

## 4. Mapping onto vfs: gaps and recommendations

Legend: **adopt** — take the concept now, in vfs's own shape; **adapt**
— take it when the roadmap reaches the consumer; **parity** — vfs
already has it, sometimes better; **skip** — a consequence of a bet vfs
did not make.

| # | Mirage pattern | vfs today | Verdict |
| --- | --- | --- | --- |
| 3.1 | one door | `_dispatch_entry` / `_call_storage`; `cli` re-enters verbs | parity |
| 3.2 | name plane above backends | mount table only; no links/overlay | adapt (roadmap 018 bind aliases) |
| 3.3 | `descendants` vs `visible_descendants` | `_shadow_filter`, no hidden bindings | **adopt** with hide (§4.1) |
| 3.4 | namespace-only directories | stored mount-point rows — stronger | parity |
| 3.5 | fan-out with shadow filtering | `_route_fanout`, typed rows | parity (vfs shape better) |
| 3.6 | profile document; session binds; only narrows | per-mount `PermissionMap` in code | **adopt** in spec 070 (§4.5) |
| 3.7 | hide ≠ deny; no-name-leak rules | no read gating; `permission_denied` unproduced | **adopt** in spec 058 (§4.1) |
| 3.8 | per-subject judgment | write side per-subject; no read side | adopt with §4.1 |
| 3.9 | ask + decision ledger | none | **adopt** as a kind + ledger (§4.3) |
| 3.10 | explain / dry run | gate is pure; not exposed | **adopt** (§4.2) |
| 3.11 | structured refusal beside voiced text; `VALIDITY`; fail closed | `ResultError` kind/message/data | parity; fix rule-in-message (§4.4) |
| 3.12 | entry gate = same comparator mid-walk | SELECT predicate is vfs's entry gate (058) | adapt; keep "one comparator" |
| 3.13 | script policies in a sandbox | none; ADR 021 wants policy-layer subtraction | adapt (§4.6) |
| 3.14 | per-field `Aggr` on limits | separate merges | adapt if budgets unify (spec 051) |
| 3.15 | hierarchy kit | one stored-tree backend | adapt (roadmap 020, live APIs) |
| 3.16 | foreign Postgres as files | vfs owns its own tables | positioning fact (§4.7) |
| 3.17 | declared facts; `storage_id` | `capabilities()`, traits, derived `caps` | parity; note `storage_id` for 019 |
| 3.18 | a backend from one table | protocol families; no generator | adapt when a second backend exists |
| 3.19 | cache coherence at mutation site | no cache layer yet | adapt (the decorator) |
| 3.20 | notify-driven watch | none; versions make delta trivial | adapt |
| 3.21 | snapshot / drift / pin | per-entry revisions; no session capture | adapt (§4.8) |
| 3.22 | tool-tier stale-write protection | `conflict` + version at storage | **adopt** in spec 054 `serve()` |
| 3.23 | six tools; per-mount prompt fragment; `readOnlyHint` | wire contract pinned; `serve()` unbuilt | adopt the two small ideas in 054 |
| 3.24 | op records; cost before execution | `source` provenance only | adapt (§4.8) |
| 3.25 | conditions named once; total tables | `VFSErrorKind` + contracts — stronger | parity |
| 3.26 | stale exemptions fail | mutant ledger, skips | **adopt** the rule |
| 3.27 | style meta-tests | drift tests | adopt two (`object`, closures) |
| 3.28 | bug-carrying design digest | `context/` + ADRs | parity |

### 4.1 Hide as the `invisible` rung, with Mirage's leak rules

Spec 058's ladder already reads `(invisible) < read < read_write`.
Mirage supplies the rules that make `invisible` mean what it says, and
each maps onto a vfs seam:

- **A hidden path answers `not_found`, never `permission_denied`.** In
  vfs terms the kind is `vfs.not_found` and the `Result` carries no
  hint that a rule fired. (Mirage: `ENOENT`, no `Refusal` record, the
  reason in an operator-only side table.)
- **Hide is subtree-closed and drops out of every enumeration** — `ls`,
  `tree`, `glob`, `grep`, `glean`, `graph`. For vfs's SQL backend this is
  the read predicate spec 058 already plans ("reads filter sets"); the
  point Mirage adds is that a *native push-down* — vfs's gram planner,
  segment postings, the ranked legs — must not count or rank what the
  predicate hides. The predicate has to reach nomination, not just the
  final fetch, or a hidden row can still influence a score or a count.
  This is the same shape as the 2026-08-17 path-indexing memo's
  "scope must reach nomination" argument.
- **A binding the principal may not see is not named in a listing, a
  tree, or a `cross_mount` error.** vfs's `MountInfo` / `mounts()` and
  every router-minted message that spells a mount path need a
  visible-to-this-principal filter — Mirage's `visible_descendants`.
- **Distinguish "not a verb for you" from "refused".** Mirage's 127 vs
  126. vfs's analogue is `unsupported` (capability) vs
  `permission_denied` (policy), which `_gate_entry` already orders
  capability-first so "an incapable entry reads as `unsupported`, never
  as a policy denial." Keep that order; add the rule that a
  *hidden* mount reads as `not_found`, not `unsupported`.
- **A read-side subject.** Once reads are gated, the source of a `copy`
  and the observations handed to a chained verb become subjects
  (§3.8); `_route_two_path` already gates per end for writes, so the
  shape exists.

This touches ADR 021 (additive-only grants — hide fits as a *level*,
not a deny row) and spec 058's remaining forks. It does not need
Mirage's pattern grammar: vfs grants are path prefixes by decision.

### 4.2 `explain` — the gate as a verb

`_gate_params → _gate_entry → check_writable_composed → _busy_guard` is
pure and already returns the classified `Result` a refusal would carry.
Expose it: `vfs.explain(op, path=..., user_id=..., **params) -> Result`
that runs every router-side gate and none of the storage, returning the
exact `Result` — kind, message, `data` — the real call would refuse
with, or an empty success. Mirage's two rules to keep: the explanation
is rendered **from the same table** as the refusal (vfs: it *is* the
same `Result`), and a dry run **spends nothing** — no version bump, no
ask recorded, no storage touched. Once principals land, `explain` is
the Catalog's "who can reach what" query, answered by the enforcement
code itself rather than by a second model of it.

### 4.3 Ask as a child kind, with a ledger

vfs's kind vocabulary is hierarchical by design: a consumer that does
not know `vfs.permission_denied.pending` degrades to
`vfs.permission_denied`. So an ask is one kind and one `data` record
away: `kind=vfs.permission_denied.pending`, `data={'vfs.ask_id': ...}`,
`retry_class=refresh` (retry after the host answers). The ledger is the
part worth copying carefully: **one record type** for pending and
settled, `scope ∈ {once, session}`, coverage compared on the recorded
fields rather than a re-derived id, and an abandoned wait that drops the
eventual answer. MCP's 2026-07-28 revision has elicitation and tasks;
an ask is a task whose completion is a host decision, which is how
`serve()` (spec 054) would surface it.

### 4.4 Put the winning rule in `data`, not the message

`check_writable` renders `read-only by mount rule '/x'` into `message`
and sets nothing in `data`. The envelope's own contract says "every
load-bearing fact must be a structured field" and "no consumer may
parse `message`." Mirage's `Ruling.source` (`top` / `mounts./repo`)
and `matched_path` are the fields: add `data={'vfs.rule_prefix': ...,
'vfs.rule_mount': ...}` to the `read_only` error. Small, and it is what
`explain` (§4.2) and the Catalog will read.

### 4.5 A profile-shaped session document for spec 070

Spec 070 delivers `Principal` and a session facade. Mirage's shape is
worth adopting for the facade: **one frozen document per profile**, a
session binds exactly one at creation, the document can only *narrow*
what the mount table declares (a mount's declared mode is the ceiling;
`weaker_mode`), and an omitted mount keeps its own mode — "a profile
that must not reach a mount hides it," rather than getting a permission
error that names it. vfs already composes `PermissionMap` layers
most-restrictive-wins; a session layer is one more layer in
`_permission_layers`, outermost first. The `allow` list (the session's
verb set: an unlisted verb is `unsupported`, not `permission_denied`)
maps directly onto `MountMeta.deny_ops`, which is already "the mounter's
op mask" — a session op mask is the same subtraction one layer down.

### 4.6 Policy-layer expressions as sandboxed scripts

ADR 021 §1 forecloses deny rows and says subtraction "enters as a
policy-layer expression over grants." Mirage shows one working shape for
that expression: a script that defines `pre_op(ctx)` with `ctx` as plain
JSON, runs in a sandboxed engine attached to the workspace, may read
files through the same door (its own reads exempt from its own
judgment), and can only restrict. vfs already tracks monty for the
hermetic-runtime direction; one engine could serve both the `run` verb
and the policy hook. Defer until 058 needs subtraction; record the shape
now so it is not re-derived.

### 4.7 A positioning fact: "mount your database" means two things

Mirage's Postgres resource mounts an **existing** schema read-only as a
rendered tree; vfs's `DatabaseFileSystem` **provisions its own tables**
on the engine you name and stores vfs entries there. Both READMEs say
"mount your database as a filesystem"; a reader arriving from Mirage
will expect the former. Two consequences:

- The README line should say which one vfs is: *the namespace lives in
  the database you already run* — same engine, same backups, same
  access controls, vfs's own tables — not *your tables rendered as
  files*.
- A foreign-schema mount (`/enterprise/public/tables/orders/rows.jsonl`)
  is a plausible future backend for vfs and would slot into the
  hierarchy kit (§3.15). It is not on the roadmap; it should be an
  explicit non-goal or an explicit later wave, not silence.

### 4.8 Audit: what the agent read, at what version, at what cost

Three Mirage mechanisms together form a read-side audit vfs lacks:
per-op records with cache-vs-network bytes (§3.24), a session snapshot
of *what was read and its fingerprint* (§3.21), and cost estimation
before execution. vfs has the write-side audit (revisions, ADR 013/017)
and a natural pin (every version has a content hash). The Catalog plane
(ADR 058) is the consumer: "what changed" is answerable today; "what did
this agent see, and would replaying it see the same" is not. Record as
a later-wave item; the version table makes the pin free once a session
records `(path, version)` per read.

---

## 5. What not to take

- **The virtualized bash.** Mirage's unit of truth is a shell line; a
  large share of its code (`shell/`, `workspace/expand/`,
  `commands/spec/`, the `ntn`/`git`/`slack` CLIs, `serde` imitation)
  exists to be GNU-exact. vfs decided that `cli` is a front door that
  re-enters typed verbs (`ops.py`), and returns rows, not text. That
  decision is what makes vfs's fan-out merge trivial where Mirage
  re-parses `du` output, and it is what makes `Result` a wire contract.
  Keep it.
- **Byte-exact GNU conformance.** A consequence of the above. vfs's
  conformance is on the storage protocol, which is the right seam for a
  library whose consumers are code.
- **FUSE / FSKit / WinFsp.** Explicitly out of vfs's scope; Mirage's
  own `AGENTS.md` FUSE section is a catalogue of platform traps.
- **Breadth-first backends.** 56 resources, most API-backed and
  rendered on read, with per-backend caps against rate limits. vfs's
  scale contract (10 k-row batches, five engines) is the opposite
  posture and the harder one; do not dilute it to add a Slack mount.
- **The TypeScript twin and its parity gates.** A cost Mirage pays for
  the browser and edge; vfs has one engine by decision (ADR 057).
- **Per-command output caps as policy.** Mirage's `Limit` caps rendered
  bytes at the workspace boundary because its output is text; vfs's
  row caps and `truncated` kind already do this at the row level with a
  classified error the agent can act on.
- **"No backward compatibility" as a rule.** Mirage states it outright
  (`AGENTS.md`); vfs's kind vocabulary already treats shipped strings as
  permanent (aliases as tombstones). Different stage, different
  obligation.

---

## 6. The competitive read, refreshed

Yesterday's survey (chat, 2026-09-03) put Mirage as the direct
competitor; the clone confirms it and sharpens it:

- **Velocity and concentration.** 2,126 commits in four months, 81 % by
  one author, 30 contributors total. The design digest is unusually
  coherent for that reason and that risk.
- **The overlap is the namespace and permissions, and Mirage shipped
  permissions first.** v0.0.6 (2026-09-03) is the permissions framework;
  profiles, asks, explain, script policies, hide/show, and the entry gate
  are all landed and documented. vfs's equivalents are designed
  (specs 058, 070; ADR 021) and not built.
- **The moat is unchanged.** Nothing in Mirage answers "what does this
  mean" or "how does this connect": no ranked retrieval, no fusion, no
  typed edges, no graph verb, no versioned rows, no batch contract. Its
  `grep` push-down is `LIKE` over text columns; its Postgres tree is
  read-only.
- **Its best abstractions are the ones vfs will need next**, in the
  order the roadmap reaches them: the profile document (070), hide and
  the entry gate (058), explain and ask (the Catalog), the hierarchy kit
  (020), watch and cache coherence (the caching decorator), snapshot and
  op records (audit).

---

## 7. Suggested next steps

1. **Fold §4.1 into spec 058** as the specification of the `invisible`
   rung — the four leak rules and the nomination-reaching predicate —
   and note in ADR 021 that hide is a level, consistent with
   additive-only grants.
2. **Fold §4.5 into spec 070**: the session document as one frozen
   profile that only narrows, an op mask as one more `deny_ops` layer,
   omitted mounts keep their mode.
3. **Open a small spec for `explain` (§4.2) and the `data` fix (§4.4)**
   — both are router-only, no storage change, and land before principals.
4. **Reserve `vfs.permission_denied.pending`** in the kind vocabulary
   with its contract row now (§4.3), so the wire is pinned before
   `serve()` speaks it; the ledger comes with 054.
5. **Add the two meta-tests** (§3.27) and the stale-exemption rule
   (§3.26) to `standards/testing.md`.
6. **Amend the README line** on "mount your database" per §4.7, and add
   a foreign-schema mount to `roadmap.md` as either a later wave or an
   explicit non-goal.
7. **Record §3.15, §3.19–3.21 as design input** on the roadmap items
   they serve (020, the caching decorator, watch) so they are not
   re-researched.

---

## Sources

All paths under `~/Git/Repos/mirage` @ `67389cc` unless noted.

- Design digest: `AGENTS.md` (== `CLAUDE.md`, 705 lines) — sections
  "CLIs", "Mount boundaries", "Symlinks", "FUSE", "Rules", "Config
  doors".
- Docs: `docs/home/introduction.mdx`, `architecture.mdx`,
  `permissions.mdx`, `policy-engine.mdx`, `snapshot.mdx`,
  `observer.mdx`.
- Types: `python/mirage/types.py` (`MountMode`, `weaker_mode`,
  `HiddenPaths`, `ShowEntry`, `EntryGate`, `Limit`/`Aggr`, `Producer`,
  `Refusal`, `PathSpec`, `FileChangeKind`, `CapacityState`).
- Namespace: `python/mirage/ops/types.py` (`NamespaceView`, `MountView`,
  `LinkView`, `SessionView`), `ops/namespace_view.py`, `ops/ops.py`,
  `ops/registry.py`, `workspace/mount/mount.py`,
  `workspace/mount/namespace/`, `workspace/executor/fanout.py`.
- Policy: `python/mirage/policy/types.py`, `profile.py`, `decisions.py`,
  `script.py`, `policies.py`, `match/rule.py`, `match/decide.py`,
  `builtin/mount_root.py`, `utils/hidden.py`,
  `context/session_context.py`, `workspace/node/admission.py`,
  `workspace/node/explain.py`.
- Backends: `python/mirage/resource/base.py`, `resource/generic.py`,
  `resource/registry.py`, `core/hierarchy/{scope,codec,readdir,read,
  probe,bind}.py`, `core/postgres/{scope,readdir,read,search,client,
  _schema_json}.py`.
- Cache / watch / snapshot: `python/mirage/cache/{manager,read_through}.py`,
  `cache/index/store.py`, `watch/{watcher,delta,base,events}.py`,
  `workspace/snapshot/state.py`.
- Agent surface: `python/mirage/agents/{tool_operations,file_version,
  io_text,prompts,tool_descriptions}.py`, `agents/mcp/server.py`,
  `provision/types.py`.
- Gates: `spec/README.md`, `conformance/README.md`.
- vfs seams read for the mapping: `src/vfs/base.py` (module docstring,
  `MountMeta`, `_gate_params`, `_gate_entry`, `_permission_layers`,
  `_busy_guard`, `_shadow_filter`, `_route_two_path`, `_tree_region`),
  `src/vfs/permissions.py`, `src/vfs/ops.py`, `src/vfs/results/kinds.py`,
  `src/vfs/results/envelope.py`, `src/vfs/storage/protocol.py`,
  `src/vfs/models/entry.py`, `src/vfs/models/version.py`;
  `context/decisions/006`, `021`, `058`; `context/specs/active/054`,
  `056`, `058`, `070`; `context/standards/mission.md`, `roadmap.md`;
  `context/research/2026-08-27-agent-access-layer-positioning.md` §3.
