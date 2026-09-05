# afs: typed verbs over a wire, `explain` as a description, and `exec` guards — mapped onto vfs

- **Status**: research memo (commits us to nothing; feeds spec 045 (verb
  wire contract), spec 054 (`serve()`), spec 058 (row grants), spec 070
  (principal-scoped sessions), the `explain` proposal in the Mirage memo
  §4.2, and the `run` verb's future capability catalog)
- **Date**: 2026-09-04
- **Owner**: Clay Gendron
- **Question**: afs (ArcBlock's "Agentic File System") chose the same
  *shape* as vfs — a fixed set of typed verbs, spoken over a wire, with
  providers mounted at paths — rather than Mirage's bash. It made
  `explain` and `search` first-class verbs and put a guard in front of
  `exec`. What exactly is its protocol, its verb set, its provider
  contract, its permission and guard model, and its search model? What
  does it do well, and where does it show vfs an improvement?
- **Method**: a line-level read of the clone at `~/Git/Repos/afs` —
  the protocol spec (`spec/afs-protocol.md`, 1,334 lines), the core
  router (`packages/core/src/afs.ts`, 3,002 lines) and its type surface
  (`type.ts`, `error.ts`, `policy.ts`, `afs-explain.ts`,
  `provider/base.ts`, `provider/decorators.ts`), the HTTP transport
  (`providers/http/src/{protocol,handler,client,errors}.ts`), two
  provider search implementations (`providers/fs`, `providers/sqlite`),
  the provider conformance suites (`packages/testing/src/suites/`), and
  the wire-level conformance corpus (`conformance/specs/l1–l6`). Then a
  read of the vfs seams each pattern maps onto (`src/vfs/base.py`,
  `ops.py`, `params.py`, `results/kinds.py`, `results/envelope.py`,
  `storage/protocol.py`, spec 045) and the Mirage memo §3.10 / §4.2.
  Cites and describes only — every line of vfs code stays ours.
- **License**: Business Source License 1.1 (`LICENSE`): Licensor
  ArcBlock, Inc.; Additional Use Grant forbids offering it as a managed
  service; Change Date 2030-03-07; Change License Apache-2.0. BSL is
  fine to study. Copy nothing.
- **Sources line**: `AIGNE-io/afs` @ `1e9b731` (2026-03-24), **one
  squashed commit** authored "ArcBlock Engineering" — an OSS mirror of an
  internal repo (its `CLAUDE.md` still lists `kv`, `s3`, `slack`, `ec2`
  providers and an `intent/` folder that are not in this checkout).
  Commit message says v1.11.0-beta.18; `package.json` says
  1.11.0-beta.13. TypeScript: 94 k source lines, 86 k test lines, 283
  test files, ~5.5 k test cases. Core is 15.7 k lines; the UI provider
  alone is 25.6 k. Two protocol specs (AFS 1,334 lines, AUP 1,221 lines),
  both marked "0.1-draft, extracted from the TypeScript reference
  implementation".

---

## 1. Bottom line

afs and vfs agree on the shape and disagree on the discipline. Both
say: a small fixed vocabulary of verbs, every data source behind a
path, one router that resolves the path and dispatches to the mounted
provider, results that cross a wire as JSON. That agreement is worth
recording, because Mirage made the other bet (bash), and afs is a
second independent team landing where vfs did.

Where afs is ahead, it is ahead in **surface area a product needs**,
not in the contract underneath it:

1. **`explain` is a description, not a dry run.** afs's `explain(path)`
   returns markdown prose that says what is at a path and what you can
   do there (§3.4). Mirage's `explain` runs the permission gate and
   returns the exact refusal. These are two different verbs wearing one
   name. vfs should keep Mirage's meaning for `explain` (the gate as a
   verb, Mirage memo §4.2) and serve afs's meaning through what it
   already has — `stat`, `capabilities()`, the `/.vfs` meta subtree —
   plus one small addition: a per-mount description fragment at a
   well-known meta path (§4.1).
2. **The `exec` guard has one genuinely good idea: a severity floor
   set by the trust of the source.** An action declares its own risk
   (`ambient` / `boundary` / `critical`); a policy on the mount says how
   much risk is allowed; and a provider that is remote or can spawn
   processes *cannot* self-declare its actions as harmless — the floor
   from its `riskLevel` overrides the self-attestation (§3.5). vfs's
   `run` has no catalog yet. When it grows one, this is the rule to
   take (§4.3).
3. **A language-agnostic conformance corpus for the wire.** Six levels
   of YAML specs, executed over HTTP against *any* server, with the
   compositor's own behaviour (routing, root explain, guard, change
   propagation) pinned as L3–L6 (§3.8). vfs conformance-tests its
   storage protocol thoroughly and its wire not at all. Spec 045 pins
   the request schema; this is the executable half it lacks (§4.5).

Where vfs is ahead, it is ahead in exactly the places the wire will
punish afs: afs's typed in-process error codes (`AFS_NOT_FOUND`,
`AFS_SEVERITY_DENIED`, …) are **thrown away at the HTTP boundary and
re-derived by substring-matching the error message** into six numeric
codes (§3.2); the client then regex-parses the message to get the path
back. afs has no policy for an unknown request parameter or an unknown
verb beyond "400, `Unknown method`", no protocol version field, and
several router seams that throw a plain `Error` instead of a typed one.
Its fan-out `search` concatenates provider results in mount order with
no ranking and aborts the whole fan-out on the first provider error
(§3.6). Its provider contract discovers supported operations by
checking whether a method exists — the structural sniffing vfs's
storage protocol rejects by design (§3.3).

One-line version: **afs confirms the typed-verb bet; take its severity
floor and its wire-level conformance corpus; keep `explain` as the gate's
dry run and serve afs-style descriptions from data vfs already has.**

---

## 2. What afs is

**Shape.** An `AFS` object holds a mount table keyed by
`(namespace, path)` and dispatches nine operations — `read`, `list`,
`stat`, `write`, `delete`, `rename`, `search`, `exec`, `explain` — plus
two batch forms (`batchWrite`, `batchDelete`) to the provider whose
mount path is the longest prefix of the request path
(`packages/core/src/afs.ts:1227-1300`). A provider is any object that
implements a *subset* of those methods; the only required field is
`name` (`type.ts:450-583`). Providers ship as packages: local `fs`,
`git`, `json`, `toml`, `sqlite`, `markdown`, `http` (a client that
mounts a *remote* afs), `mcp` (mounts an MCP server as a provider), and
`ui`.

**The bet.** afs's own line is "everything is context": databases, APIs
and devices become paths an agent can read, write, search and act on
(`README.md`). Three things extend the filesystem metaphor: `exec`
(actions live at `<path>/.actions/<name>`), `explain` (self-description
for agents), and `search` (cross-source). The agent surface is eight MCP
tools, one per verb (`packages/cli/src/mcp/tools.ts:24-308`), with
batch write and delete folded into `afs_write` / `afs_delete` via an
`entries` argument.

**The larger product.** Half the repo is AFS-UI and AUP — a declarative
UI tree an agent writes to `/ui/.../tree` that a browser or terminal
renders, with user events coming back as `exec` calls. That half bears
on the namespace only through *overlay mounts* (§3.7). There is also a
DID-based trust gate for providers, a capability-enforcement sandbox,
and a credential vault — all product concerns outside this memo's
question.

**How it differs from vfs in one table.**

| | afs | vfs |
| --- | --- | --- |
| Verbs | 9 + 2 batch (`read list stat write delete rename search exec explain`) | 19 (`ops.py`): read family, mutation family incl. `edit`/`restore`/`sweep`/`mkedge`, `glob grep glean graph`, `run` |
| Unit of truth | a method call; `{method, params}` on the wire | a verb call, `paths in → Result out`; `Result.to_payload()` on the wire |
| Provider minimum | `name`; any subset of methods; ops discovered by `typeof` | `capabilities()` self-declaration; `SupportsRead` is the verb minimum |
| Access control | per-mount `accessMode` ladder (`readonly < create < append < readwrite`), `visibility` (`full`/`meta`), field redaction, exec severity policy | per-mount `PermissionMap` (read / read_write) composed most-restrictive-wins; `deny_ops` mask; principals and grants designed (058, 070) |
| Errors | `AFSError` subclasses with string codes in-process; six numeric codes on the wire, derived from the message | hierarchical `VFSErrorKind` strings, contract table, lossless wire round-trip |
| Search | one verb; per-provider push-down (ripgrep, FTS5); concatenated, unranked | four verbs; typed rows; fused ranking; partial results per mount |
| Conformance | 21 provider suites (bun:test) + YAML L1–L6 over HTTP | storage protocol suite on five engines; no wire suite |
| Scale posture | agent loops; `list.limit` 1000 default; batch = sequential loop | 10 k-row batches on five engines; bounded statements |

---

## 3. What afs does — and what it does well

Each pattern names the mechanism, where it lives, why it is good, and
what vfs has today. Verdicts are collected in §4.

### 3.1 The eight verbs: signatures, shapes, errors

The verb table below is from the spec (`spec/afs-protocol.md` §3) and
checked against `type.ts`.

| Verb | Request | Response | Declared errors |
| --- | --- | --- | --- |
| `read` | `path`, opts `{filter?, startLine?, endLine?, as?}` | `{data?: AFSEntry, message?}` | `AFS_NOT_FOUND`, `AFS_ACCESS_MODE` |
| `list` | `path`, opts `{maxDepth=1, offset=0, limit=1000, orderBy?, pattern?, filter?, maxChildren?, onOverflow?}` | `{data: AFSEntry[], total?, message?}` | — |
| `stat` | `path` | `{data?: AFSEntry-without-content}` | `AFS_NOT_FOUND` |
| `write` | `path`, `content: {content?, meta?, patches?}`, opts `{mode?}` | `{data: AFSEntry}` | `AFS_READONLY`, `AFS_ALREADY_EXISTS`, `AFS_NOT_FOUND`, `AFS_ACCESS_MODE`, `PATCH_TARGET_*` |
| `delete` | `path`, opts `{recursive?}` | `{message?}` | `AFS_READONLY`, `AFS_ACCESS_MODE` |
| `rename` | `oldPath`, `newPath`, opts `{overwrite?}` | `{message?}` | same-mount only |
| `search` | `path`, `query`, opts `{limit?, caseSensitive?}` | `{data: AFSEntry[], message?}` | — |
| `exec` | `path`, `args`, opts `{onChunk?}` | `{success, data?, error?{code,message,details?}, usage?}` | `AFS_SEVERITY_DENIED`, `AFS_VALIDATION_ERROR`, `AFS_READONLY`, `AFS_NOT_FOUND` |
| `explain` | `path`, opts `{format: "markdown" \| "text"}` | `{format, content: string}` | `AFS_NOT_FOUND` |

Three things worth noticing.

*The entry is one open record.* `AFSEntry` is `{id, path, content?,
meta?, actions?, summary?, linkTo?, createdAt?, updatedAt?, agentId?,
userId?, sessionId?}` and `meta` is `Record<string, any>` with a few
named keys (`kind`, `kinds`, `childrenCount`, `size`, `description`,
`events`) (`type.ts:1036-1095`). There is no file/directory
distinction: `childrenCount` carries it — `undefined` leaf, `0` empty
container, `N` exact, `-1` "has children, count unknown"
(`type.ts:1053-1067`). That last value is a good small idea: a lazy
provider can say "directory, don't know how many" without lying.

*`write` has six modes.* `replace` (default), `append`, `prepend`,
`patch`, `create`, `update` (`type.ts:286-294`). `patch` takes an array
of `{op: str_replace|insert_before|insert_after|delete, target,
content?}` where `target` must be unique in the document — ambiguity is
a typed error (`error.ts:84-89`). This is vfs's `edit` verb in a
different coat; the modes are the ones an agent actually reaches for.

*`exec` carries usage.* `AFSExecResult.usage` is `{tokens?: {input,
output, total}, cost?, durationMs?, ...}` (`type.ts:389-411`). A verb
that can call an LLM reports what it spent. vfs's `run` returns a bare
`Result`.

*vfs today:* nineteen verbs in `ops.py`, each with a `ParamSpec` row in
`params.py` that the ingress gate, the drift test, and the wire schema
all read from. afs has no equivalent table: parameter types live only in
TypeScript interfaces, and the HTTP handler casts `params` without
checking them (`providers/http/src/handler.ts:266-323`).

### 3.2 The wire: one POST, `{method, params}` in, `{success, data | error}` out

*Mechanism.* Everything is `POST /rpc` with a JSON body. Two request
shapes are accepted: named — `{"method": "read", "params": {"path":
"/x", "options": {...}}}` — and positional — `{"method": "read",
"args": ["/x", {...}]}` (`handler.ts:161-223`). The positional form is
a *transparent proxy*: the server does
`module[method](...args)` after checking the name against a blocklist
of prototype methods (`constructor`, `__proto__`, `toString`, …) and an
allowlist of the nine verbs (`protocol.ts:151-186`;
`handler.ts:176-202`). The response is `{success: true, data}` or
`{success: false, error: {code, message, details?}}`
(`protocol.ts:45-64`). HTTP status is 200 for every dispatched
operation; 400/401/405/413 mark transport-level faults only
(`spec/afs-protocol.md` §10.1).

*Error codes on the wire.* Six integers: `0 OK`, `1 NOT_FOUND`,
`2 PERMISSION_DENIED`, `3 CONFLICT`, `4 PARTIAL`, `5 RUNTIME_ERROR`,
`6 UNAUTHORIZED` (`protocol.ts:70-85`). Here is the weakness. Core afs
throws typed `AFSError` subclasses whose `.code` is a string —
`AFS_NOT_FOUND`, `AFS_READONLY`, `AFS_ACCESS_MODE`,
`AFS_SEVERITY_DENIED`, `AFS_VALIDATION_ERROR`, `AFS_MOUNT_FAILED`,
`PATCH_TARGET_AMBIGUOUS` (`packages/core/src/error.ts`). The HTTP
handler never reads that field. It calls `mapErrorToCode(error)`, which
lower-cases `error.message` and looks for substrings: "not found" /
"enoent" → 1; "permission" / "readonly" / "access denied" → 2;
"conflict" / "already exists" → 3; else 5
(`providers/http/src/errors.ts:108-138`). So `AFS_SEVERITY_DENIED`
("severity 'boundary' exceeds policy 'safe'") crosses the wire as
`5 RUNTIME_ERROR`, indistinguishable from a crash. On the far side, the
client rebuilds a not-found error by regex-matching `/Path not found:\s*(.+)/`
against the message to recover the path (`client.ts:273-278`). The
typed fact existed, was dropped, and was re-guessed from prose.

*Unknown verbs, unknown params, versions.* An unknown method is HTTP 400
with `RUNTIME_ERROR "Unknown method: x"` (`handler.ts:206-211`);
the L1 conformance spec pins only `success: false` for it
(`conformance/specs/l1/errors.yaml`). An unknown *parameter* has no
policy at all: in named mode the handler destructures the fields it
knows and drops the rest silently; in positional mode whatever was sent
is passed straight to the provider method. There is no protocol version
in the request or response; the spec calls itself "0.1-draft".

*Binary and streaming.* Binary content is never base64'd inside JSON:
`read` returns `content: null` with `meta.contentType` and `meta.size`,
and the bytes come from a separate `GET` (spec §10.3). Streaming `exec`
is NDJSON: `{"type":"chunk", ...}` lines then one `{"type":"result"}`
(spec §10.4). Both are sensible and vfs will need answers to both when
`serve()` lands.

*Why the shape is still right.* One endpoint, one envelope, `success`
as a top-level boolean, errors as data not status — this is the same
shape vfs's `Result` takes across MCP (`results/envelope.py` module
docstring). The disagreement is about what goes *inside* `error`.

*vfs today:* `ResultError.kind` is a dotted string from a hierarchical
vocabulary, dispatched by longest known prefix; unknown kinds from a
newer peer are preserved raw and degrade to their parent; `message` is
declared non-load-bearing and "no consumer may parse" it
(`results/kinds.py:24-56`; `envelope.py:76-105`). Spec 045 decides the
request half: an unknown param is `invalid`, never ignored; an unknown
op is `unrecognized`; `user_id` never crosses the wire. afs is the
counter-example that shows why each of those rules exists.

### 3.3 The provider contract: `name` plus any subset of methods

*Mechanism.* `AFSModule` (`type.ts:450-583`) requires `name` and makes
everything else optional: `description`, `uri`, `accessMode`
(default `readonly`), `visibility`, `actionPolicy`, `sensitiveFields`,
`sensitivity`, `riskLevel`, `blockedActions`, `allowedActions`,
lifecycle hooks (`ready`, `close`, `onMount`, `setEventSink`,
`setSecretCapability`), and the nine operation methods. The router
checks `typeof module.write === "function"` before dispatch
(`afs.ts:1795-1799`) and the conformance suite pins that unsupported
operations are `undefined`, not stubs
(`packages/testing/src/suites/no-handler.ts:112-133`).

Most providers extend `AFSBaseProvider` and declare routes with
decorators: `@List("/")`, `@Read("/:table/:pk")`, `@Search("/:path*")`,
`@Explain("/:path*")`, `@Actions.Exec("/issues/:number", "close")`
(`provider/decorators.ts`). Patterns are `URLPattern`s ranked by a
specificity score — static segment 100, named param 10, wildcard 1,
+5 per segment (`provider/router.ts:31-79`). At construction the base
class *removes* any operation method that has no registered route, by
shadowing it with `undefined` on the instance
(`provider/base.ts:190-218`), so that `typeof` sniffing tells the truth.
`getOperationsDeclaration()` then derives the capability set from which
methods survived, AND-ed with `accessMode === "readwrite"` for the
mutating ones (`base.ts:220-241`).

*The static half.* A provider *class* also declares `manifest()` —
name, description, `uriTemplate` (e.g. `s3://{bucket}/{prefix+?}`), a
Zod schema for all config, a category from a fixed list, capability
tags from a fixed vocabulary, a security declaration (`resourceAccess`,
`riskLevel`, `dataSensitivity`), and a runtime-capability manifest
(network egress, filesystem paths, process spawn, secrets)
(`type.ts:683-796`). And optionally `treeSchema()`: the path patterns
it serves, the ops at each, and `bestFor` / `notFor` hints, "max 3
items, max 20 chars each" (`type.ts:891-914`). That last field is aimed
squarely at an agent choosing which mount to use.

*Mount routing.* Longest-prefix match on segment boundaries
(`afs.ts:1255-1297`). Parent/child mounts are forbidden — `/data` and
`/data/sub` cannot both be mounts (spec §4) — with one exception, the
`.aup/{name}` overlay (§3.7). Providers receive the mount-relative
subpath; results are rebased by `joinURL(modulePath, entry.path)` on
the way out (`afs.ts:1600-1603`, `1991-1996`). Mounts live in
namespaces addressed as `@ns:path`; namespaces never conflict
(`afs.ts:1215-1222`). Mount-time health check: `stat`/`read` then `list`
with a timeout, failing as `AFS_MOUNT_FAILED` unless `lenient`
(`afs.ts:771-840`).

*Why the good parts are good.* The decorator router is a real
productivity win for API-backed providers: a GitHub provider is a dozen
patterned handlers. `treeSchema.bestFor/notFor` and the controlled
category/tag vocabularies are agent-facing catalog data that vfs's
Catalog plane (ADR 058) will want. The severity of a provider's *own*
risk (`riskLevel`) being declared statically is what makes the exec
floor (§3.5) possible.

*The weak part.* Capability is inferred from method presence. afs
mitigates this with `removeUnimplementedMethods`, but an `http` client
provider mounting a remote afs still has to *guess* — its class defines
all nine methods, so it advertises all nine whatever the far side
supports; an unsupported far-side op comes back as a 400 at call time
(`handler.ts:250-253`). vfs's storage protocol says exactly why this is
wrong: "self-declaration, never structural sniffing, so an adapter or
wire client answers with its real set rather than its method surface"
(`storage/protocol.py` module docstring; `base.py:604-617`).

*vfs today:* `capabilities()` on every backend, declared once and
snapshotted into `MountMeta.declared_caps` at bind; `caps =
declared_caps - deny_ops` is what every gate reads
(`base.py:103-128`). Protocol families (`SupportsRead`,
`SupportsMutation`, `SupportsPatternSearch`, `SupportsGlean`,
`SupportsGraph`, `SupportsRun`) group the methods. No decorator router,
because vfs has one stored-tree backend rather than fifty API shims —
that is the roadmap-020 conversation, already noted in the Mirage memo
(§3.15).

### 3.4 `explain`: a description of a path, rendered as markdown

This is the verb the question was most about, so here is exactly what
it does.

*Signature.* `explain(path, {format?: "markdown" | "text"}) →
{format, content: string}` (`type.ts:446-448`;
`meta/type.ts:102-107`). The return is prose. There is no structured
field — no list of operations, no permission verdict, no schema object
— only a string an LLM can read.

*The router's resolution chain* (`afs.ts:2566-2684`):

1. `.as/` paths (alternate representations) get a one-line answer.
2. Root system paths: `/` → `explainRoot`; `/.actions[/name]` →
   `explainRootAction`; `/.meta[/...]` → `explainRootMeta`;
   `/.knowledge[/...]` → `explainKnowledge`.
3. Otherwise resolve the mount. If the path is *above* a mount (a
   virtual intermediate directory) → a two-line "Virtual directory,
   N children" answer.
4. Try the provider's own `explain()`. A `NotFound` from it falls
   through; any other `AFSError` propagates.
5. If nothing yet, try to `read` `<path>/.afs/README.md` — a
   convention: a directory can carry its own explanation as a file.
6. If still nothing, `stat` the path and render the metadata as
   markdown (`buildExplainFromStat`: size, children, modified,
   description, provider, kind, kinds, actions;
   `afs-explain.ts:31-78`).
7. If even `stat` fails, throw a plain `Error("No explain or stat
   handler …")` — not an `AFSError` (`afs.ts:2676-2680`).
8. Finally, append any `.afs/skills/` discovered at the path.

*What root explain says.* A fixed intro, a "Mounted Providers" list
(name, mount path, first line of description), the eight verbs with
one-line glosses, root actions (`mount`, `unmount`) from their
`inputSchema`, a "Quick Start", and the built-in systems (`.meta`,
`.actions`, `.afs/`, `.knowledge/`) (`afs-explain.ts:102-192`). The
Quick Start still names `/web/sites` and `/modules/aignehub` — paths
from the internal product, not from anything in this checkout
(`afs-explain.ts:167-170`). It is the clearest evidence that this repo
is a mirror.

*What a provider's explain says.* The `fs` provider's handler
(`providers/fs/src/index.ts:982-1041`): prefer `.afs/README.md` if the
path is a directory; else render name, path, type, size, metadata,
resolved kind schema, and a sorted child list.

*Is it a dry run of the gate?* No. Nothing in the chain consults
`accessMode`, `actionPolicy`, `blockedActions` or `visibility`. An
`explain("/readonly-mount/file")` says nothing about the fact that
`write` would be refused. The permission facts live in a different
discovery surface: `read("/.meta/.capabilities")` returns an aggregated
`OperationsDeclaration` per provider — eight booleans, already AND-ed
with access mode (`capabilities/types.ts:69-82`; `base.ts:225-241`;
`afs.ts:1534-1547`) — and `read("/.knowledge")` returns a markdown index
of every mount's actions and docs (`afs.ts:2746-2790`).

*The conformance pin.* Every provider *must* implement `explain` and
return non-empty content for `/`
(`packages/testing/src/suites/explain-existence.ts:16-31`). The L4 wire
specs pin that root explain contains "Mounted Providers" and every
mount name, that a mount root and a file path return markdown, and that
a missing path is `success: false`
(`conformance/specs/l4/explain-mount.yaml`).

*Why it is good anyway.* The *fallback ladder* is the good part.
Provider prose → a README the operator wrote → metadata rendered as
prose → error. An agent never gets an empty answer for a real path, and
an operator can improve the answer for any directory by dropping a file
in it. That is cheap and it composes.

*Why it is not enough.* Prose cannot be dispatched on. An agent that
wants to know "may I write here?" has to read English and guess. vfs's
position — every load-bearing fact is a structured field, prose is
rendered last (`envelope.py` docstring) — applies to descriptions as
much as to errors. And two of the ladder's rungs are computed by
*calling other verbs* (`read` of the README, `stat`), which is fine in
process and doubles the round trips over a wire.

*vfs today:* no `explain`. The Mirage memo §4.2 proposes one with the
*other* meaning: run `_gate_params → _gate_entry →
check_writable_composed → _busy_guard` without touching storage and
return the exact `Result` the real call would refuse with. That gate is
pure today (`base.py:2461-2554`). The description side of afs's verb is
mostly already answerable: `stat` for the entry, `capabilities()` for
the ops, the `/.vfs` reserved subtree for metadata
(`storage/protocol.py` docstring), `KIND_CONTRACTS` for the hint text
per refusal. What is missing is one thing: a place for the operator's
prose about a mount (§4.1).

### 3.5 The `exec` guard: severity × policy × floor, with block/allow lists

*Mechanism.* An action is an entry at `<node>/.actions/<name>`. Its
metadata may carry `severity` and `inputSchema`; an `ActionSummary`
on the parent entry lists it (`type.ts:375-384`). Three severities —
`ambient` (no side effects), `boundary` (side effects, reversible),
`critical` (destructive) — and three policies a mount can set —
`safe` (ambient only), `standard` (+ boundary), `full` (all)
(`type.ts:108-124`; `afs.ts:633-637`).

*Evaluation order in `AFS.exec`* (`afs.ts:2006-2094`):

1. Resolve the mount. No mount or no `exec` → plain `Error` (not typed;
   `afs.ts:2020-2023`).
2. If the subpath is the mount root, look for `blocklet.yaml` /
   `program.yaml` and, if found, run it as a program instead (§15 of the
   spec; out of scope here).
3. `checkWritePermission(module, "exec")` — `exec` needs `readwrite`;
   `readonly` → `AFS_READONLY`; `create`/`append` → `AFS_ACCESS_MODE`
   (`afs.ts:548-583`).
4. `checkActionPolicy(module, subpath)` (`afs.ts:710-762`):
   - extract the action name from `/.actions/<name>$`;
   - **`blockedActions` wins over everything** → `AFS_SEVERITY_DENIED`
     with severity `"blocked-by-policy"`;
   - `allowedActions` skips the severity check (but never the block
     list);
   - no `actionPolicy` on the mount → no enforcement ("backward
     compatible"); `full` → allowed;
   - otherwise **call `module.read(subpath)`** to fetch the action's
     `meta.severity`; missing or unreadable → default `boundary`
     ("safe-by-default", `afs.ts:736`);
   - **apply the floor**: `riskLevel` `system` / `external` / `local` →
     floor `boundary`; `sandboxed` → no floor. The effective severity is
     the *higher* of self-declared and floor (`afs.ts:652-672`);
   - refuse if the policy's allowed set does not contain it →
     `AFSSeverityError(actionName, severity, policy)` — a typed error
     carrying all three facts as fields (`error.ts:64-79`).
5. `validateExecInput` (`afs.ts:2146-2200`): **call `module.read(subpath)`
   again** for `meta.inputSchema`; convert JSON Schema to Zod; on
   mismatch → `AFS_VALIDATION_ERROR` with field-level messages; an
   unconvertible schema degrades to "skip validation".
6. Inject the `afs` root (or a capability-scoped proxy when isolation is
   on) into `options.context` and dispatch.

*Policy resolution.* A provider ships named `SecurityProfile`s; the user
picks one and overrides. Merge rules: `blockedActions` and
`sensitiveFields` are *unions* (a user can add but never remove a
provider's own blocks); `allowedActions` is *replaced*; scalars: user
wins (`policy.ts:12-43`). Non-exec verbs are explicitly unaffected by
action policy (spec §4 "Exec Guard", rule 6; pinned by
`conformance/specs/l5/exec-guard-policy.yaml`).

*Is there an ask/approve path?* **No.** A refusal is terminal. The only
interactive primitive in the codebase is `AuthContext.collect()` for
gathering credentials at mount time (`type.ts:20-59`), which is a
different thing. Mirage has `ask` with a decision ledger; afs does not.

*Why the floor is the good idea.* Self-attested risk is worthless on
its own: a malicious or sloppy remote provider labels `rm -rf` as
`ambient`. afs ties the *minimum* severity to a fact the *host* knows
about the provider — whether it is sandboxed, remote, local, or can
spawn processes — and lets self-attestation only *raise* it. That is
the same instinct as vfs's "restriction composes downward and can only
tighten" (`base.py:2510-2531`), applied to executables. The
block-beats-allow-beats-policy order and the union-only merge for blocks
are the same instinct again.

*The smells.* Two `read()` round-trips per `exec` (severity, then
schema) — each a network call for a remote provider. `undefined`
policy meaning "no enforcement" is a fail-open default dressed as
compatibility. The action name is parsed from the path with a regex
(`afs.ts:714`), so an action at a path that does not end in
`/.actions/<name>` bypasses the guard entirely — which is exactly the
case for program execution in step 2.

*vfs today:* `run` is one verb in `EXEC_OPS` — "routed, no write gate;
executes rather than reads" (`ops.py`) — with the `SupportsRun` protocol
taking `path` and `arguments` (`storage/protocol.py:339-349`). The only
guard is the mount's `deny_ops` mask. There is no catalog of runnables,
no declared severity, no schema validation of `arguments` at the router
(`_gate_params` checks the *shape* of `arguments` as a dict, not its
contents). The Mirage memo already proposes `permission_denied.pending`
as the ask kind (§4.3).

### 3.6 `search`: push-down per provider, concatenated at the root

*Mechanism.* One verb, `search(path, query, {limit?, caseSensitive?})`.
The router finds every mount at or under `path`, skips those without
`search`, throws a plain `Error` if any has `visibility: "meta"`, calls
each provider's `search(subpath, query, options)`, rebases the returned
paths, and concatenates (`afs.ts:1969-2004`). Mount order is
longest-path-first (`afs.ts:1297`), so results from the deepest mount
come first — an accident of routing, not a ranking. Messages are joined
with `"; "`. **The first provider that throws aborts the whole
fan-out** (`afs.ts:1998-2000`); there is no partial result. `limit` is
not applied at the root — each provider applies its own, so a root
search over N mounts can return N × limit rows.

*Push-down.* The `fs` provider spawns ripgrep (`@vscode/ripgrep`),
walks JSON match lines, applies mount-level ignore patterns and
`.gitignore`, de-duplicates by file, `stat`s each hit, and returns one
entry per *file* with `summary` = the first matching line
(`providers/fs/src/index.ts:862-945`). The `sqlite` provider uses FTS5:
one `MATCH` query per configured table with `LIMIT ceil(limit /
tables)`, `highlight()` for a snippet, and a `console.warn` on any
per-table failure (`providers/sqlite/src/operations/search.ts:48-125`).
So the *unit* of a search result differs by provider — a file here, a
row there — and there is no score field on `AFSEntry` at all.

*What is good.* Push-down to the engine that already indexes the data
(ripgrep, FTS5) is the right call and vfs makes the same one. The
conformance pin that "after `write` to one mount, `search("/")` MUST
find the new content" (L6, `change-propagation.yaml`) is a good
cross-verb invariant to state.

*What is not.* No ranking, no fusion, no score, no partial results, no
root-level limit, and a `visibility: meta` mount anywhere under the
scope turns the whole search into an untyped error. For an agent, a
root search over a dozen mounts is an unordered pile.

*vfs today:* four verbs (`glob`, `grep`, `glean`, `graph`); fan-out via
`_route_fanout` with per-mount errors carried as classified partial
results; typed `Observation` rows with a uniform shape across verbs;
`glean` fuses lexical and vector legs with a ranker (ADR 053); scope
crosses the storage seam only as composed pattern text
(`storage/protocol.py` docstring). vfs is ahead here by a wide margin;
nothing to take.

### 3.7 Overlay mounts and the AUP provider — the one namespace fact

AUP (Agentic Universal Primitives) is a UI tree — 17 node types with
`props`, a read-only data binding `src` (an afs path) and a read-write
binding `bind`, and events that map to `exec` calls
(`spec/aup-protocol.md` §1–2). The UI provider exposes browser sessions
as paths; an agent `write`s a tree to `/ui/web/sessions/<sid>/tree`.

The namespace consequence: afs forbids nested mounts *except* at
`<any-mount-subpath>/.aup/<name>`, where a "supplementary provider" may
be layered onto an existing data mount to give it a UI view
(`afs.ts:585-625`, `917-926`; spec §19). The longest-prefix sort exists
partly so these overlays win over their parent (`afs.ts:1294-1297`).
That is a product-specific hole punched in a routing rule. vfs's rule —
mounts nest freely, `no_overlay` seals a subtree, shadow-filtering drops
rows a deeper binding owns (`base.py:120-143`) — is the general form and
needs no exception. Nothing else in AUP bears on the namespace.

### 3.8 Conformance: 21 provider suites plus a language-agnostic YAML corpus

*Provider level.* `runProviderTests({name, createProvider, structure,
...})` runs 21 suites against a provider *in process*: structure, read,
search, meta, explain, access mode, error types, entry fields, list
options, path normalization, deep list, no-handler, route params,
metadata richness, explain existence, capabilities, plus optional
execute/action/write/delete cases; and a `security/` set — path
traversal, symlink escape, input injection, resource exhaustion,
sensitive-field leak, error-info leak, manifest validation
(`packages/testing/src/suites/`). The fixture is a *declared tree* —
the provider's expected shape — and the suites derive their cases from
it. Every provider in the repo carries `test/conformance.test.ts`, and
`CLAUDE.md` calls it "non-negotiable".

*Wire level.* `conformance/` is a runner that reads YAML documents and
executes them as HTTP requests against *any* server that speaks the
`/rpc` protocol — "Swift, Kotlin, Go, Rust, or any other language"
(`README.md`; `conformance/src/runner.ts:1-12`). Six levels:

| Level | Pins |
| --- | --- |
| L1 | read, list, stat, write, delete, search, unknown method |
| L2 | write→read cycle, delete verify, search-after-write, write modes, AUP session over WebSocket |
| L3 | longest-prefix routing, cross-mount isolation, root list, cross-mount search |
| L4 | root explain lists mounts and verbs; mount and file explain; missing path is `success: false` |
| L5 | exec guard: `safe` policy blocks `boundary` actions; read/write unaffected; blocked list |
| L6 | after write, stat and root search see it; after delete, neither does |

A spec is a `name`, an `operation`, `params`, and an `expect` tree with
matchers (`contains`, `gte`, `length`, `type`), or a `steps` list with
`store` to thread a value from one step to the next
(`conformance/specs/l3/cross-mount-search.yaml`;
`conformance/src/assertions.ts`).

*Why this is good.* The spec text says "Any AFS Core implementation …
that passes all levels is considered a fully compliant compositor"
(`spec/afs-protocol.md` §4). The compositor's *own* behaviour — not
just a provider's — is pinned by executable, transport-level tests that
a second implementation can run without sharing a line of code. That
is the property vfs wants for spec 045 and for the MCP peer in 054.

*The honest caveat.* The provider suites are permissive in places: the
`explain` suite accepts "either a function or undefined" and treats a
thrown `Error` whose message mentions "explain" as a pass
(`suites/explain.ts:18-82`); the `no-handler` suite requires
`accessMode ∈ {readonly, readwrite}` while the type allows `create` and
`append` (`suites/no-handler.ts:135-139`; `type.ts:99`). The wire
corpus is small (24 + 9 + 16 + 8 + 6 + 3 tests).

*vfs today:* a storage-protocol conformance suite run against SQLite in
CI and against Postgres, MariaDB, SQL Server and Oracle via the
`db_test` skill; signature drift tests against `params.py`. No
wire-level corpus; `serve()` is unbuilt (spec 054).

### 3.9 Smaller patterns worth one line each

- **Access-mode ladder with `create` and `append` rungs**
  (`type.ts:92-99`; `afs.ts:548-583`): `create` allows only
  `write(mode: create)` — a drop box; `append` allows create and
  append — an audit log. Both are "write, but only in ways that cannot
  destroy". vfs's ladder has read and read_write only.
- **`visibility: "meta"`** (`type.ts:101-106`; `afs.ts:1605-1609`):
  `read` returns the entry without `content`; `search` is refused. A
  "you may know it exists and how big it is, not what it says" level.
- **Field redaction** (`afs.ts:678-700`, `1426-1429`, `1595-1598`):
  `sensitiveFields` are replaced by `"[REDACTED]"` recursively in
  `content` and `meta` on `read` and `list`, unless `sensitivity:
  "full"`. Users can add fields, never remove the provider's own.
- **`.as/<format>` alternate representations** (`afs.ts:1500-1506`):
  `read("/x/.as/html")` asks the provider for another rendering;
  `list("/x/.as")` enumerates them via `supportedAs()`. vfs's
  extension channel (`normalize_ext_channel`, `expand_channel`) is the
  cousin.
- **Batch is a loop** (`afs.ts:1853-1876`): `batchWrite` calls `write`
  per entry sequentially, catches each error into `{path, success:
  false, error: message}`, and counts. Per-entry fail-safe is the right
  contract; a sequential loop of N round trips is not a 10 k-row
  design. vfs's batch verbs are per-target classified *and* bounded by
  statement budget.
- **Change records** (`type.ts:76-90`; `afs.ts:1818-1823`): every
  successful `write`/`delete`/`rename`/`mount`/`unmount` emits a record
  to an injected listener; providers can emit typed events with a
  declared `dataSchema`. Design input for vfs's watch item.
- **Mount-time health check with `lenient`** (`afs.ts:771-840`,
  `986-1050`): `stat` then `list` with a timeout before the mount is
  live; `check(path)` awaits the probe. vfs's `_probe_bind_site` proves
  the bind site is an empty directory — a different check with the same
  instinct.
- **Path guard** (`packages/provider-utils/src/path-guard.ts`): logical
  `..` check, then a `realpath` symlink check, throwing
  `AFS_PERMISSION_DENIED` — a code that exists nowhere in `error.ts`'s
  class list. Small evidence that the string-code vocabulary is not
  closed.

---

## 4. Mapping onto vfs: gaps and recommendations

Legend: **adopt** — take the concept now, in vfs's own shape; **adapt**
— take it when the roadmap reaches the consumer; **parity** — vfs
already has it, sometimes better; **skip** — a consequence of a bet vfs
did not make.

| # | afs pattern | vfs today | Verdict |
| --- | --- | --- | --- |
| 3.1 | nine typed verbs, one open entry record | 19 verbs, `ParamSpec` table, typed `Observation` rows | parity (vfs stronger: params are a table) |
| 3.1 | `childrenCount: -1` = "has children, count unknown" | `Observation` fields; no lazy-count sentinel | adapt when a lazy backend exists |
| 3.1 | six write modes incl. `patch` with unique-target rule | `write` + `edit` (`EditOperation`) | parity |
| 3.1 | `usage` (tokens, cost, duration) on `exec` | `run` returns a bare `Result` | **adopt** for `run` (§4.3) |
| 3.2 | one POST, `{success, data \| error}` envelope | `Result.to_payload()` over MCP | parity |
| 3.2 | typed codes dropped at the wire, re-derived from message | `kind` is the wire; message non-load-bearing | parity — afs is the cautionary tale (§4.4) |
| 3.2 | no unknown-param policy; no version | spec 045: unknown param → `invalid` | parity; 045 is right (§4.4) |
| 3.2 | binary out-of-band; NDJSON streaming for `exec` | undecided for `serve()` | adapt in 054 |
| 3.3 | `name` + any subset of methods; ops by `typeof` | `capabilities()` self-declaration | parity (vfs stronger) |
| 3.3 | decorator route table per provider | one stored-tree backend | adapt with roadmap 020 (Mirage §3.15) |
| 3.3 | `treeSchema.bestFor / notFor`, controlled categories and tags | none | adapt for the Catalog plane (§4.2) |
| 3.3 | `riskLevel` declared statically per provider | none | **adopt** with the floor (§4.3) |
| 3.3 | `@ns:path` namespaces | one router = one namespace | skip |
| 3.4 | `explain` = markdown description with a fallback ladder | no `explain`; Mirage §4.2 proposes the dry run | **adapt**: keep the dry-run meaning; add a mount description fragment (§4.1) |
| 3.4 | `.afs/README.md` convention | `/.vfs` reserved meta subtree | **adopt** the convention at a `/.vfs` path (§4.1) |
| 3.4 | `/.meta/.capabilities` → per-provider op booleans | `capabilities()` per mount | parity |
| 3.5 | severity × policy × floor; block > allow > policy | `deny_ops` mask only | **adopt** when `run` gets a catalog (§4.3) |
| 3.5 | JSON-Schema validation of `args` at the router | `_gate_params` checks shape only | adapt with the catalog (§4.3) |
| 3.5 | no ask path | Mirage §4.3 `permission_denied.pending` | parity (vfs plan is ahead) |
| 3.6 | one `search`; push-down; concatenated; abort on first error | four verbs; fused ranking; partial results | parity (vfs far ahead) |
| 3.7 | `.aup/{name}` overlay exception to no-nesting | free nesting + `no_overlay` + shadow filter | parity (vfs general) |
| 3.8 | YAML wire-conformance corpus, L1–L6, any language | storage conformance only | **adopt** for 045/054 (§4.5) |
| 3.8 | declared-tree provider fixture drives 21 suites | storage suite with fixtures | parity |
| 3.9 | `create` / `append` write-only rungs | read / read_write | adapt into spec 058's ladder as a question (§4.6) |
| 3.9 | `visibility: meta` | spec 058 `(invisible)` rung is stronger | parity; note the middle rung (§4.6) |
| 3.9 | field redaction by policy | `columns` projection, no policy | adapt in spec 070 |
| 3.9 | batch as sequential loop with per-entry results | per-target classification, bounded statements | parity (vfs stronger) |
| 3.9 | change records / typed events | none | adapt (watch) |
| 3.9 | mount health check + `lenient` | `_probe_bind_site` | parity |

### 4.1 Two verbs named `explain`; keep the gate, add the fragment

The Mirage memo §4.2 proposes `vfs.explain(op, path=..., **params) ->
Result`: run every router-side gate and none of the storage, return the
exact `Result` the real call would refuse with. afs's `explain` is a
different thing: a description of a path for an agent to read. Both are
useful. They should not share a name, and vfs should not build a
prose-rendering verb.

Recommendation, in three parts.

1. **`explain` stays the dry run.** Its answer is a `Result` — kind,
   message, `data` — from the same gates the real call runs. This is
   the thing an agent can dispatch on ("may I write here?"), and afs
   shows what happens without it: the agent reads markdown and guesses.
2. **The description is already data vfs has.** What afs renders is
   `stat` (size, children, kind, timestamps) plus the mount's
   `capabilities()` plus the operator's prose. The first two are
   verbs today; the third is the gap.
3. **Adopt the README convention, at a `/.vfs` path.** afs's `.afs/
   README.md` is a good, cheap idea: an operator can improve the
   explanation of any directory by writing a file. vfs already reserves
   `/.vfs` as a meta subtree that default enumeration hides and direct
   addressing serves (`storage/protocol.py` docstring). A mount-level
   description at a well-known path under it becomes the "per-mount
   prompt fragment" the Mirage memo (§3.23) wants for spec 054's
   `serve()` — and it is a stored row, versioned like everything else,
   not a string in a manifest. Render it into tool descriptions at the
   MCP boundary; never make it the answer to a permission question.

Two rules from afs's ladder to keep even so: never return empty for a
real path (fall through to `stat`), and let a provider's own answer
win over the synthesized one.

### 4.2 Catalog data the Catalog plane will want

`treeSchema.bestFor` / `notFor` (three items, twenty characters each),
the controlled `category` list, and the `capabilityTags` vocabulary are
agent-facing selection hints (`type.ts:891-975`). ADR 058's Catalog
plane is where vfs will answer "which mount should I use for X". Record
these three as design input there: short, controlled, per mount, and
distinct from the free prose in §4.1. The `-1` "children, count
unknown" sentinel belongs in the same note for the day a lazy
API-backed mount exists.

### 4.3 The severity floor, for `run`

vfs's `run` has no catalog of what can be run, no declared risk, and no
schema check on `arguments`. afs shows the shape of all three, and one
rule worth taking exactly:

- Every runnable declares a severity; the *host* assigns each mount a
  trust tier; the effective severity is the **higher** of the two.
  Self-attestation can only raise risk, never lower it.
- Block beats allow beats policy; block lists merge by union so a
  narrower layer can add blocks and never remove them. This is the
  same "restriction composes downward and can only tighten" rule
  `_permission_layers` already enforces for writes (`base.py:2510-2531`).
- A missing declaration reads as the *middle* tier, not the bottom.
- No `undefined`-means-no-enforcement default. vfs's existing posture —
  unknown dialects get the floor, unknown severity reads as error — is
  the right one.
- Validate `arguments` against a declared schema at the router and
  classify a mismatch as `invalid`, the same channel `_gate_params`
  uses — one read to fetch both severity and schema, not two.
- Report `usage` on the `Result` (tokens, cost, wall time) so the audit
  story (Mirage memo §4.8) has a number to record.

This lands when `run` grows a catalog, which is not scheduled. Record it
against `SupportsRun` so it is not re-researched.

### 4.4 The wire: afs is the counter-example spec 045 needed

Spec 045 made three decisions on paper: an unknown request param is
`invalid`, never ignored; an unknown op is `unrecognized`; `user_id`
never crosses the wire. afs makes none of those decisions and shows the
cost of each:

- **Kinds must ride the wire as data.** afs has typed codes in process
  and loses them at the boundary, because the transport layer was
  written against `Error.message` (§3.2). vfs's rule that `message` is
  non-load-bearing and `kind` is the dispatch key is exactly the fix.
  Add one drift test to 045's list: every `VFSErrorKind` value survives
  `to_payload → from_payload` unchanged, and no code path in `serve()`
  or the routing mount inspects `message` to classify.
- **Positional "transparent proxy" mode is a footgun.** `module[method]
  (...args)` after a name allowlist (`handler.ts:245-255`) means the
  server has no idea what it forwarded. vfs's routing mount should
  accept named params only, validated by `params.py`.
- **A version field costs nothing now and cannot be added later
  without skew.** afs has none. 045 should pin one on the request
  envelope even if the only value is `1`.
- **Errors are per-mount partial results, not aborts.** afs's fan-out
  search throws on the first provider failure (§3.6). vfs's
  `_route_fanout` already carries per-mount failures beside healthy
  rows; keep that as a stated wire property.

### 4.5 A wire-level conformance corpus for 045 and 054

afs's L1–L6 YAML corpus is the executable half of a protocol spec: any
implementation, in any language, runs the same requests and must
produce the same shaped answers. vfs has this for storage (five
engines) and not for the verb surface. When spec 054 builds `serve()`
and spec 034 builds the routing mount, there will be two peers speaking
the wire — the trigger 045 itself names for moving the schema next to
`ops.py`. Recommendation: the same trigger creates
`tests/wire/` — YAML or plain pytest fixtures, one document per verb per
behaviour, run against an in-process `serve()` today and a remote later.
The levels to borrow: single-verb shapes; cross-verb invariants
(write→stat, write→grep, delete→neither); router behaviour (longest
prefix, isolation, root listing); gate behaviour (read-only refusal,
`deny_ops`, kinds on the wire). afs's `store` step-threading and its
`contains` / `gte` / `length` matchers are the whole DSL needed.

### 4.6 The access-mode ladder: two rungs to consider, one to note

Spec 058's ladder reads `(invisible) < read < read_write`. afs has, in
effect, `invisible-content (meta) < read < create < append < readwrite`
(§3.9). Two of those are worth an open question in 058:

- **`create`-only** — may add new entries, may not overwrite or delete:
  a drop box. **`append`-only** — may add and may extend, never
  overwrite: an audit log. Both are "write without destruction", and
  both are things an operator asks for. Whether they are rungs on the
  path ladder or per-op grants on top of `read_write` (058's row-grant
  vocabulary could express "write but only mode=create") is the
  question. Do not decide here; note it.
- **`meta` visibility** — exists, size, kind, but not content — is a
  rung *between* invisible and read. Mirage's leak rules (Mirage memo
  §4.1) say what invisible must hide; `meta` is the level where the
  name leaks and the content does not. 058's ladder can name it or
  reject it explicitly.

Field redaction by policy (`sensitiveFields`) is a spec 070 concern:
a session document that narrows `columns` per mount is the vfs shape of
it.

---

## 5. What not to take

- **The nine-verb minimalism.** afs's single `search` and single
  `exec` are what a general-purpose product needs. vfs's four search
  verbs, typed edges, versioned mutation and reversible batches are the
  reason it exists. Do not collapse them toward afs's surface to look
  simpler.
- **`explain` as prose.** Covered in §4.1. A verb whose only return is
  a string cannot be dispatched on, cannot be tested for more than
  "contains", and doubles round trips over a wire.
- **Method-presence capability discovery.** `removeUnimplementedMethods`
  is a clever patch on a design vfs already rejected
  (`storage/protocol.py`).
- **Transparent-proxy positional RPC.** §4.4.
- **Message-substring error mapping.** §3.2, §4.4.
- **Sequential batch loops.** afs's `batchWrite` is N round trips with
  no bound; vfs's 10 k-row contract on five engines is the opposite
  posture and the harder one.
- **`undefined` policy means no enforcement.** Fail-open defaults do
  not fit a project whose unknown dialect gets the conservative floor.
- **Namespaces as `@ns:path`.** One `VirtualFileSystem` = one namespace
  = one policy layer is the Linux shape and composes through storage
  adapters; a string prefix on every path does not.
- **The `.aup` overlay exception.** A product-specific hole in a routing
  rule; vfs's free nesting plus `no_overlay` plus shadow filtering is
  the general rule.
- **The DID trust gate, capability enforcer, vault, program execution,
  and AFS-UI/AUP.** Real engineering, all outside the question, all
  consequences of afs being an application platform rather than a
  storage layer.

---

## 6. Next steps

1. **Amend the Mirage memo's `explain` proposal when it becomes a
   spec** (§4.1): the verb is the gate's dry run; the description side
   is `stat` + `capabilities()` + a mount description row at a
   well-known `/.vfs` path; that row is the per-mount prompt fragment
   spec 054 consumes.
2. **Add to spec 045** (§4.4): a request-envelope version field; a
   named-params-only rule for the routing mount; a kind round-trip
   drift test; and the explicit statement that no wire seam classifies
   from `message`.
3. **Add to spec 054's test plan** (§4.5): a wire-level conformance
   corpus with afs's six-level structure as the outline, run in-process
   against `serve()` first.
4. **Open two questions in spec 058** (§4.6): `create`/`append` as
   rungs or as grants; `meta` visibility as a named rung between
   invisible and read.
5. **Record §4.3 against `SupportsRun`** as design input for the day
   `run` grows a catalog: declared severity, host trust floor,
   block > allow > policy with union-only blocks, schema-validated
   arguments, `usage` on the result.
6. **Record §4.2 against ADR 058's Catalog plane**: `bestFor`/`notFor`,
   controlled categories and tags, the `-1` lazy-count sentinel.
7. **Note in `roadmap.md`'s watch item** that afs's change records and
   typed event declarations (§3.9) are design input, beside Mirage's
   notify-driven watch.

---

## Sources

All paths under `~/Git/Repos/afs` @ `1e9b731` unless noted.

- Positioning and specs: `README.md`, `CLAUDE.md` (450 lines; names
  the internal repo and providers absent from this mirror),
  `spec/afs-protocol.md` (§2 entry model, §3 operations, §4 mount
  system and compositor rules, §5 access control, §6 error codes,
  §8 provider interface, §9 capabilities, §10 transport, §12
  knowledge, §17 edge cases, §19 overlay mounts, §21 tree schema),
  `spec/aup-protocol.md` §1–2, `LICENSE`.
- Core types and errors: `packages/core/src/type.ts` (`AFSAccessMode`
  92-99, `AFSVisibility` 101-106, `ActionSeverity`/`ActionPolicy`
  108-124, `SecurityProfile` 126-159, options/results 186-303, batch
  305-352, exec/usage 354-433, `AFSModule` 450-583, `ProviderManifest`
  683-715, capability manifest 744-796, `ProviderTreeSchema` 886-914,
  vocabularies 916-975, `AFSEntry` 1036-1095), `error.ts`,
  `policy.ts`, `meta/type.ts:99-107`, `capabilities/types.ts:69-82`.
- Router: `packages/core/src/afs.ts` (`checkWritePermission` 548-583,
  `POLICY_ALLOWED`/floor 633-672, `maskSensitiveFields` 678-700,
  `checkActionPolicy` 710-762, mount check 771-840, `check` 1050-1064,
  `findModulesInNamespace` 1227-1300, `list` 1302-1464, `read`
  1496-1622, `write` 1778-1825, `batchWrite` 1853-1876, `search`
  1953-2004, `exec` 2006-2094, `validateExecInput` 2146-2200, `stat`
  2420-2470, `explain` 2566-2684, `.knowledge` 2746-2790),
  `afs-explain.ts` (31-78, 102-192, 197-267).
- Provider contract: `packages/core/src/provider/base.ts` (55-125,
  190-241), `provider/router.ts:31-79`, `provider/decorators.ts`
  (72-134, 212-338), `provider/types.ts:1-60`,
  `packages/provider-utils/src/path-guard.ts`.
- Transport: `providers/http/src/protocol.ts` (26-64, 70-85, 151-186),
  `handler.ts` (90-255, 260-323), `client.ts` (196-292),
  `errors.ts` (1-88, 108-138).
- Search push-down: `providers/fs/src/index.ts:862-945` (ripgrep) and
  `982-1041` (explain); `providers/sqlite/src/operations/search.ts:48-125`
  (FTS5).
- Agent surface: `packages/cli/src/mcp/tools.ts:24-308` (eight tools).
- Conformance: `packages/testing/src/suites/{explain,explain-existence,
  access-mode,error-types,no-handler}.ts`, `suites/security/`;
  `conformance/src/runner.ts`, `conformance/specs/l1/errors.yaml`,
  `l3/cross-mount-search.yaml`, `l4/explain-mount.yaml`,
  `l5/exec-guard-policy.yaml`, `l6/change-propagation.yaml`.
- vfs seams read for the mapping: `src/vfs/base.py` (module docstring,
  `MountMeta` 103-128, `capabilities` 604-617, `_gate_params`
  2461-2473, `_gate_entry` 2475-2508, `_permission_layers` 2510-2531,
  `_busy_guard` 2533-2554, `_dispatch_entry` 2556-2566),
  `src/vfs/ops.py`, `src/vfs/params.py` (docstring, `ParamSpec`),
  `src/vfs/results/kinds.py` (`VFSErrorKind`, `Severity`,
  `KIND_CONTRACTS`), `src/vfs/results/envelope.py` (docstring,
  `ResultError` 76-116), `src/vfs/storage/protocol.py` (docstring,
  `SupportsRun` 339-349), `context/specs/active/045-verb-wire-contract/
  spec.md`, `context/research/2026-09-04-mirage-design-patterns.md`
  §3.10, §3.23, §4.1–4.3, §4.8.
