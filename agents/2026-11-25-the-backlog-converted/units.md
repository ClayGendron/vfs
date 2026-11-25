# The thirty numbered specs of the backlog are archived, dropped or converted into 88 units, each one spec and one pull request

This map says, for each numbered folder under `context/specifications/active/`, whether it is archived as landed, dropped as overtaken, or converted, and for each converted folder the units it becomes. A unit is one spec that one pull request can carry, green at its end, as `agents/templates/spec.md` defines it. Each unit has a key (the source's number and an ordinal), the path its spec will take, a title that states the behaviour, the roadmap gate it serves (`a`, `b`, `f`, `0.2`, `0.1.x`, or unplaced where no roadmap story places it) and what it depends on. A dependency is written as a unit key of this map, as `landed:` with the archived spec or the folder already in the tree, as `story <ID>, no spec` for a roadmap story that has no spec and no unit here, as `dated spec:` with the file name of a spec under `context/specifications/active/` dated 2026-11, or as the deletes spec, which is not yet written and has no roadmap story. A dependency on a roadmap story is resolved to the units that land the shape relied on; where a story's units form a chain, its last unit stands for the chain. Ordering preferences are left out. The verdicts and the proposed units come from the thirty studies under `studies/`, read with the decision verifications under `decisions/` and with sections 4 to 15 of `context/standards/roadmap.md`. No two proposed units were merged: none fails to be green apart from another and none is a few lines that rides another. A unit that two studies proposed appears once, under the source that owns it: the removal of `run` is 167-1, the bounded renderer of spec 155 is 167-3, the operation groups are 181-1, the split of the conformance battery is 179-1, and the history read of spec 161 is 180-1 and 180-2. Where two studies name each other, the roadmap's sequencing decides the order: 174-1 lands before 175-2, 171-1 before 170-4, 167-1 before 181-1, 178-2 before 179-10, and 172-1 before 169-4. The graph of unit dependencies has no cycle.

| Source | Action | Reason |
|---|---|---|
| `051-fanout-deadline-budget` | convert | Study verdict live at gate f, by rewrite: no fan-out chokepoint has a time budget and nothing produces `vfs.timeout`. The roadmap counts the folder as overtaken only in the sense that story H6 rewrites it, and the study converts it as H6's two units. |
| `080-mysql-batch-update-statements` | convert | Study verdict live at 0.2 (story D5): on MariaDB a guarded overwrite batch is still one round trip per row. Slice A, the research, is done; slice B is one unit. |
| `102-set-based-scattered-delete` | drop-overtaken | Study verdict overtaken: the delete arm it reshapes no longer exists, because the tombstone delete is set-based and flat in the batch size. The scattered-pair cost of `move` and `copy` it leaves behind is a different verb and design, recorded by story D4's pins and designed after the deletes spec. Replaced by landed spec 162-trash-as-a-tombstone-on-the-row, the tombstone delete (in the tree; archived by this map). |
| `147-import-edge-extractor` | convert | Study verdict live at 0.2 (story E8): no import kernel, resolver or `imports` edge exists. The design stands and converts by amendment into two units. |
| `148-sessions-narrowing-and-pending` | convert | Study verdict live in two parts: section 5 (`pending` and the ask ledger) is story H3 at gate b, rewritten onto the action log and the replay store; sections 1 to 4 and 6 (narrowing, child sessions, join) are 0.2. |
| `149-serve-auth-token-to-authority` | convert | Study verdict live at gate b (story I1): no door token, edge factory or verifier exists. Rule 3 and the open-mount refusal move to 171-2, rule 4 to 170-5 and rule 5 to story M3. |
| `152-binary-bodies-and-text-renderings` | convert-and-archive-landed-part | Study verdict partly landed: slices A and B are in the tree and are archived with a landing note; two unmet promises of slice B, slice C (images) and slice D (the documentation) remain as four units. |
| `155-the-text-renderer-for-agents` | drop-overtaken | Study verdict overtaken: the spec folded itself into spec 167 slice A on 2026-10-15 and none of it is built. Its budget, markers, slash, error collapse and rank column ride unit 167-3. Replaced by 167-3. |
| `156-mount-admission` | convert | Study verdict live and unplaced: the kernel face is still admitted as a storage and then fails `glob`, and no router-level `..` gate test exists, while the README states the refusal as fact. One small unit. |
| `157-postgres-provisioning-for-host-apps` | convert | Study verdict live at gate b (storage story D3): first touch creates no schema, a privilege refusal classifies `internal` and the bulk path ignores the driver. Rule 3 (the extension step) is overtaken by the landed probe-and-refuse design and is dropped from the units. |
| `159-render-at-write` | convert | Study verdict live at 0.2 (story E8, decision D21): a bytes write still returns `pending`. The gap narrowed to the interval before the next `refresh`; one unit. |
| `160-cross-mount-copy-as-read-plus-write` | convert | Study verdict live and unplaced: the router still refuses every cross-mount pair, while the README, the `cross_mount` hint and the shell's `cp` all assume the copy. One unit. |
| `161-every-mutation-mints-a-version-row` | drop-overtaken | Study verdict overtaken: the mint is in the tree, the read side is story K8 converted from spec 180's read slice, and its age-based retention is contradicted by the ruling that keeps the full history. Three facts ride unit 180-1. Replaced by landed spec 162-trash-as-a-tombstone-on-the-row for the mint (in the tree; archived by this map); units 180-1 and 180-2 for the read side. |
| `162-trash-as-a-tombstone-on-the-row` | archive-landed | Study verdict landed: both slices are in the tree and the engine legs run in CI. Archived with a landing note; the deletes spec revisits the design as new work. |
| `165-the-permission-ladder-list-and-contribute` | archive-landed | Study verdict landed: all three slices are in the tree with the four engine legs green. Archived after its stale names are corrected or footnoted. |
| `167-the-shell-pipeline-core` | convert | Study verdict live across gates a, b and f (stories F1 to F5, F7 and K9's `run` task): nothing of the shell is built. Ten units, with spec 155's content folded into 167-3. |
| `168-text-program-kernels` | convert | Study verdict live at gate f for slices a and b (story F6) and 0.1.x for slice c: nothing is built and all of it stands on the shell. Four units. |
| `169-programs-the-index-and-the-vfs-views` | convert | Study verdict live in three parts: slice a is story T1 and slice c is story T2, both gate b; slice b and the first programs are story T6 at 0.2. Five units. |
| `170-tools-and-mcp-servers-as-views` | convert | Study verdict live at gate b (stories I3a, T3, I3b, T4) and gate f (I4): nothing is built. Its removal of `run` belongs to 167-1. Five units. |
| `171-the-mcp-adapter-and-the-cli-tool` | convert | Study verdict live at gate b (stories M1 and I2): no MCP package exists. Three units; `vfs serve` is story M2 and `pending` on the wire is story M3, neither of which this folder carries. |
| `172-the-wasi-python-runtime` | convert | Study verdict live at gate b by rewrite (stories T5a and T5b): nothing is built and the build, runner and door are now the wasi-python wheel's. Three units, one of them a spike. |
| `173-spike-a-static-wasi-cpython-with-numpy-compiled-in` | archive-landed | Study verdict landed: the spike ran on 2026-10-16 and every deliverable is in the tree. Archived with its landing notes; its facts feed unit 172-1. |
| `174-write-preconditions-and-the-guarded-append` | convert | Study verdict live at gate b (story K2): no precondition, exclusive create, guarded append or `unchanged` answer exists. Four units. |
| `175-integrity-verify-on-read-and-scrub` | convert-and-archive-landed-part | Study verdict partly landed: the threshold's move and a one-hop offload rule landed on 2026-11-07 and are archived with a note; verify on read, the hash on written rows and the repair act remain as three units. Slice D (`scrub`) is overtaken by the dated lint spec's byte layer. |
| `176-the-listing-cursor` | convert | Study verdict live at gate b (story K4): no `after=`, `limit=` or `next_after` exists. Three units; the third (a stored depth column) is unplaced. |
| `177-replay-the-contract-and-the-request-key` | convert | Study verdict live at gate b (story K5): a replayed `move` still refuses bare and `edit` applies twice. Four units. |
| `178-the-ranged-read` | convert | Study verdict live at gate b (story K6): `read` takes no range on any face. Three units. |
| `179-the-storage-seam-as-the-kernel` | convert | Study verdict live across two gates: the battery split and the protocol regroup must precede the freeze (story K9, gate b); the rest is story K7 at gate f or unplaced. Ten units. |
| `180-history-pack-on-reindex-and-the-bounded-sweep` | convert | Study verdict live: the history read is story K8 at gate f; pack, the bounded retention pass and the gauge are 0.2; none is built. Six units, with spec 161's read side folded into 180-1. |
| `181-the-public-surface-regrouped-by-kernel-group` | convert | Study verdict live at gate b for the groups and `entry_id` (story K9): none is built. Four units; chaining onto `Result` and the derived-verb oracles are unplaced. |

## `051-fanout-deadline-budget`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 051-1 | `../2026-11-25-a-deadline-on-a-read-fan-out-cancels-the-hung-mount-and-reports-a-timeout/spec.md` | A read verb given a deadline returns within it, keeping every settled mount's rows and one `vfs.timeout` record at each unanswered mount's prefix, and a mutating verb given one is refused `vfs.invalid` before any statement. | f | landed: 2026-11-07-bounded-work-has-one-home.md |
| 051-2 | `../2026-11-25-cancel-marks-a-pending-ask-or-a-stopped-run-and-the-re-send-answers-cancelled/spec.md` | `cancel(ticket)` marks one pending ask and `cancel(run_id)` marks a run and every open ask, after which the re-send or `resume` answers `vfs.cancelled`. | f | 148-1, story H1, no spec, story H4, no spec |

## `080-mysql-batch-update-statements`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 080-1 | `../2026-11-25-mariadb-guarded-and-absorbing-updates-run-one-statement-per-chunk/spec.md` | On MariaDB a guarded overwrite batch of N rows issues ceil(N / rows_per_statement) UPDATE statements, with the same observations as today. | 0.2 | landed: 079-guarded-update-statement-attribution |

## `147-import-edge-extractor`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 147-1 | `../2026-11-25-python-import-statements-are-read-by-an-engine-kernel/spec.md` | The engine returns every Python import statement in a batch of bodies, with its module path, imported names, relative level and folded referring line, and nothing found inside strings or comments. | 0.2 | landed: 138-reference-edge-extractor |
| 147-2 | `../2026-11-25-python-imports-become-imports-edges-in-the-index-pass/spec.md` | `rebuild` and `refresh` mint one `imports` edge per resolved source-to-module pair, weight the statement count, replace only a re-extracted source's extracted `imports` rows, and report unresolved imports in an info record beside the links leg. | 0.2 | 147-1 |

## `148-sessions-narrowing-and-pending`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 148-1 | `../2026-11-25-a-policy-hook-stops-a-kernel-verb-into-a-pending-result-an-answer-admits-once/spec.md` | A call a policy hook or a liftable refusal stops returns a pending result with a ticket, and an attributed answer lets the identical call through exactly once. | b | 177-3, 177-4, story H0, no spec, story H1, no spec, story H2, no spec |
| 148-2 | `../2026-11-25-a-session-narrows-by-a-subtractive-profile-and-a-child-session-inherits-it/spec.md` | `session.narrow(profile)` returns a session that can do no more than before, hides paths before any lookup, and refuses a denied verb with a kind distinct from a grant refusal; a child session inherits the parent's narrowing, subjects and source identity and ends with its parent. | 0.2 | landed: 070-principal-scoped-sessions, landed: 058-row-level-permission-grants |
| 148-3 | `../2026-11-25-a-joiner-narrows-the-next-call-and-is-told-which-surfaced-paths-it-cannot-see/spec.md` | `session.join(principal)` narrows the very next call to the new subject set, re-grades nothing already surfaced, and returns the surfaced paths the joiner cannot read. | 0.2 | 148-2, 167-5 |

## `149-serve-auth-token-to-authority`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 149-1 | `../2026-11-25-a-bare-authority-constructor-is-closed-by-a-door-token/spec.md` | A bare `Authority(...)` built outside `vfs.authority` raises `TypeError` naming the doors, while `copy` and `pickle` round-trip. | b | nothing |
| 149-2 | `../2026-11-25-a-verified-token-becomes-an-authority-at-the-edge-and-nowhere-else/spec.md` | `authority_from_token(claims)` turns verified claims into an `Authority` with `provenance="edge"`, refuses reserved subjects as `vfs.invalid`, and the shipped `TokenVerifier` refuses a bad token as `vfs.unauthenticated`. | b | 149-1 |
| 149-3 | `../2026-11-25-a-trusted-subsystem-names-the-members-of-a-room-and-the-authority-says-attested/spec.md` | A verified `service` token whose declared scope allows it may name subject members as data, and the authority built from it carries `provenance="attested"`, distinct from `edge`. | b | 149-2, 171-2 |

## `152-binary-bodies-and-text-renderings`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 152-1 | `../2026-11-25-an-unchanged-bytes-overwrite-keeps-its-rendering/spec.md` | Writing the same bytes over a bytes entry keeps its rendering and its stamp, so the next index pass renders nothing. | unplaced | landed: 152-binary-bodies-and-text-renderings slices A and B (in the tree; archived by this map) |
| 152-2 | `../2026-11-25-search-says-how-many-bytes-rows-it-could-not-read/spec.md` | A search over a mount holding pending or unrendered bytes entries reports their count on its result, as the index pass does. | unplaced (fits gate b under domain E) | landed: 152-binary-bodies-and-text-renderings slices A and B (in the tree; archived by this map) |
| 152-3 | `../2026-11-25-an-image-written-as-bytes-renders-a-metadata-header/spec.md` | An image written as bytes renders a header of format, dimensions and readable EXIF tags, stores its width and height, and a PDF's embedded images get the same placeholder line docx and pptx emit. | 0.2 | landed: 152-binary-bodies-and-text-renderings slices A and B (in the tree; archived by this map) |
| 152-4 | `../2026-11-25-binary-bodies-are-documented-on-the-docs-site/spec.md` | The docs site explains how to store and search documents, what a rendering and a render status are, and the unit-marker grammar, with glossary entries for source, rendering, unit marker and render status. | f | story X3, no spec, story X4, no spec |

## `156-mount-admission`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 156-1 | `../2026-11-25-a-router-is-refused-as-a-mount-and-a-dot-dot-path-meets-the-siblings-gate/spec.md` | Binding a `VirtualFileSystem` or `AsyncVirtualFileSystem` as storage raises a `TypeError` that says a router is not a storage, and a write through `..` into a read-only sibling mount is refused at the sibling's path. | unplaced (lean b, ahead of story R5's re-check) | nothing |

## `157-postgres-provisioning-for-host-apps`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 157-1 | `../2026-11-25-first-touch-creates-the-mounts-schema-and-names-a-privilege-refusal/spec.md` | A mount with `schema=` on Postgres or SQL Server creates its schema at first touch when it is absent, and a role that may not create it is refused `unavailable` naming the schema and the privilege, never `internal`. | b | nothing |
| 157-2 | `../2026-11-25-the-bulk-insert-path-follows-the-driver-on-the-connection/spec.md` | A bulk insert takes asyncpg's binary `COPY` only when the connection's driver is asyncpg; a psycopg 3 session factory runs the conformance contract and lands a 10,000-file write through Core in at least two counted pages. | b | nothing |
| 157-3 | `../2026-11-25-a-borrowed-sql-server-factory-is-checked-and-the-facade-installs-extensions/spec.md` | A borrowed `mssql+aioodbc` factory without `use_setinputsizes=False` is refused `invalid` at first touch naming the argument, and `install_extensions(path)` runs one mount's install from the facade. | b | 157-1 |

## `159-render-at-write`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 159-1 | `../2026-11-25-a-small-binary-write-renders-its-own-bytes-before-it-returns/spec.md` | A write of at most sixteen binaries totalling one blob page renders them outside its transaction and returns them readable and greppable; a larger write stays pending for the next refresh or rebuild. | 0.2 | landed: 152-binary-bodies-and-text-renderings slices A and B (in the tree; archived by this map), landed: 2026-10-31-refresh-the-incremental-index-verb.md |

## `160-cross-mount-copy-as-read-plus-write`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 160-1 | `../2026-11-25-a-cross-mount-file-copy-is-a-read-on-one-mount-and-a-write-on-the-other/spec.md` | `copy` of a file across mounts reads the source with the caller's authority, writes it at the destination through that mount's own gate, and reports each pair as two operations. | unplaced (lean b) | dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md |

## `167-the-shell-pipeline-core`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 167-1 | `../2026-11-25-the-dead-run-verb-leaves-every-face/spec.md` | `run` and `SupportsRun` are gone from the vocabulary, the rungs, the params table, both kernel classes, both synchronous classes, the protocol and the README, and `ALL_OPS` has 24 members. | b | nothing |
| 167-2 | `../2026-11-25-a-bytes-row-renders-a-placeholder-and-leaves-the-payload-only-when-asked/spec.md` | A bytes-sourced row prints one `[binary <path> <mime> <size>B v<version>]` line in every arrangement, and `to_payload()` carries no bytes unless `include_bytes=True`. | a | nothing |
| 167-3 | `../2026-11-25-the-verb-renderer-is-bounded-never-silent-and-marks-kind-and-rank/spec.md` | A rendered result stops at a declared character budget with one marker, says when it is empty, marks directories with a slash, prints identical fan-out errors once, and ranks search hits by position. | a | nothing |
| 167-4 | `../2026-11-25-the-shell-parses-the-whole-bash-grammar-before-anything-runs/spec.md` | Every bash construct parses to an AST in one pass under four counted budgets, malformed text is one `vfs.invalid.syntax` with a caret, and only the D47 and D48 words are refused as `vfs.unsupported.construct`. | a | nothing |
| 167-5 | `../2026-11-25-a-pipeline-runs-gated-verbs-through-cli-with-the-minimal-programs/spec.md` | `cli` on both kernel classes and both synchronous classes runs a parsed line as bounded stage tasks whose every verb re-enters the public router as the admitted caller, prints what bash prints, and returns one Result with the status list. | b | 167-1, 167-2, 167-3, 167-4, 174-2, 174-4, 176-1 |
| 167-6 | `../2026-11-25-glob-matches-case-insensitively-on-every-engine/spec.md` | `glob(case_mode="insensitive")` matches a case-folded filter in one statement per mount on SQLite and on each engine leg, with an index-served prefilter costed at the reference deployment. | b | nothing |
| 167-7 | `../2026-11-25-move-and-copy-take-replace-and-a-move-keeps-the-moved-file/spec.md` | `move(src, dest, replace=True)` lands on an occupied file keeping the moved file's `entry_id` and leaves the replaced file undoable, `copy(replace=True)` keeps the destination's identity, and a directory over a directory is `vfs.exists`. | b | 177-1, the deletes spec, not yet written (no roadmap story), dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md |
| 167-8 | `../2026-11-25-the-program-forms-set-e-and-the-never-table-answer-as-gnu-and-bash-do/spec.md` | Every form of the program table, `set -e` with its POSIX exemptions, and every never-class name answer as GNU and bash do against committed fixtures, with `grant`, `revoke` and `grants` spelled in the shell and `trav` resolved to `traverse` at parse time. | b | 167-5, 167-7, 178-2 |
| 167-9 | `../2026-11-25-the-shell-runs-control-flow-functions-arithmetic-and-arrays/spec.md` | `for`, `while`, `until`, `if`, `case`, functions, arithmetic, arrays and the parameter operators run with every verb gated, under declared loop and function-depth budgets, with bounded `&` and `wait` and the nondeterministic words recorded for resume. | b | 167-4, 167-8, 174-4 |
| 167-10 | `../2026-11-25-a-replay-corpus-measures-shell-coverage-and-a-reference-page-lists-the-surface/spec.md` | A synthesized replay corpus reports parse, resolve, flag and run rates with an in-scope run rate of at least 85%, the Oils rate is published beside it, and `documentation/reference/shell.md` lists the grammar, programs, exit codes, budgets and refusals. | f | 167-8, 167-9, 168-3, story H5, no spec |

## `168-text-program-kernels`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 168-1 | `../2026-11-25-the-shells-text-programs-run-as-rust-cores-behind-one-feed-and-drain-seam/spec.md` | The six text programs spec 167 wrote in Python run as Rust cores behind one feed-and-drain seam, and match their Python forms byte for byte. | f | 167-8 |
| 168-2 | `../2026-11-25-sort-uniq-tr-and-tee-run-as-kernels-pinned-by-gnu-fixtures/spec.md` | `sort`, `uniq`, `tr` and `tee` run as kernels pinned by recorded GNU fixtures and the split law, and `awk` and `jq` refuse with a hint. | f | 168-1 |
| 168-3 | `../2026-11-25-xargs-and-find-exec-dispatch-through-the-runner-so-no-program-runs-another/spec.md` | `xargs` turns bytes into batched child dispatches through the union, and `find -exec` and `-delete` are planner rewrites, so no program ever runs another. | f | 167-5, 167-8 |
| 168-4 | `../2026-11-25-diff-and-cmp-run-as-kernels-that-answer-as-gnu-does/spec.md` | `diff` prints a Myers unified diff under the line's deadline and `cmp` compares two inputs in step, as GNU does. | 0.1.x | 168-1 |

## `169-programs-the-index-and-the-vfs-views`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 169-1 | `../2026-11-25-the-meta-root-is-synthesized-and-refuses-every-write-beneath-it/spec.md` | `/.vfs` is a directory on every storage, nothing can be written beneath it, a wasm module is sniffed as `application/wasm`, and `/.agents` is gone. | b | nothing |
| 169-2 | `../2026-11-25-the-router-serves-the-program-and-skill-views-and-resolves-a-name-by-the-index/spec.md` | `ls /.vfs/bin` and `/.vfs/skills` list every callable a caller may see, a name resolves in one batched `stat` per mount, and an install is a gated write. | b | 169-1, 167-5, 167-8 |
| 169-3 | `../2026-11-25-every-shell-call-leaves-a-run-record-as-rows-in-the-root-bindings-storage/spec.md` | After a `cli` call, `/.vfs/run/<id>/stdout` and `/status` are rows in the root binding's storage, readable from another process and by no other principal. | b | 169-2, 167-5, 177-3, story H0, no spec |
| 169-4 | `../2026-11-25-a-generic-wasm-host-runs-stored-programs-with-the-callers-verbs/spec.md` | A `.wasm` core module stored in an indexed directory runs by name under fuel, memory, verb and wall budgets, and every file it touches goes through the caller's gated verbs. | 0.2 | 169-2, 172-1 |
| 169-5 | `../2026-11-25-the-first-installed-programs-resolve-by-their-unix-names/spec.md` | `vfs install` fetches a pinned, hash-checked uutils, jaq and awk into `/opt/bin`, and each resolves by its Unix name. | 0.2 | 169-4, story M2, no spec |

## `170-tools-and-mcp-servers-as-views`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 170-1 | `../2026-11-25-a-callers-rung-at-many-catalogue-paths-is-one-chunked-statement-per-budget-slice/spec.md` | `SupportsGrants.rungs_at(paths, *, authority)` returns the caller's rung at each path from posture rows and spans on its chain, in `ceil(len(paths) / membership_budget)` statements on every engine leg, equal to a Python oracle. | b | 167-1, 181-1 |
| 170-2 | `../2026-11-25-a-registered-host-function-is-a-file-under-the-tools-view-and-a-command-by-name/spec.md` | A host function registered once appears at `/.vfs/tools/<name>` and in `/.vfs/bin`, reading it never runs it, and typing its name runs it through one gated door with flags mapped from its schema. | b | 167-1, 167-5, 167-8, 169-2, 169-3, 170-1 |
| 170-3 | `../2026-11-25-a-catalogue-posture-decides-who-may-see-and-who-may-call-a-tool/spec.md` | `grant` and `posture` at a catalogue path are lawful, the mutating verbs there are `vfs.invalid`, and with posture `list` a caller sees every tool's name and calling one is exit 126 with zero invocations. | b | 169-2, 170-1, 170-2 |
| 170-4 | `../2026-11-25-a-connected-mcp-server-is-a-directory-of-tools-resources-and-prompts/spec.md` | A server connected with `add_mcp` appears under `/.vfs/mcp/<name>/`, its tool calls come back as rows by the inbound block table, each failure around a call maps to its kind and exit, and one supervisor task owns each connection. | b | 170-3, 171-1, story H1, no spec |
| 170-5 | `../2026-11-25-a-mounted-server-is-called-with-the-credential-the-host-resolves-for-the-caller/spec.md` | `add_mcp(..., credentials=)` takes a static credential or a `CredentialResolver`, opens one connection per distinct principal, and never lets the credential reach a row, a result, a log or a child's environment. | f | 170-4, 149-2 |

## `171-the-mcp-adapter-and-the-cli-tool`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 171-1 | `../2026-11-25-the-wire-adapter-projects-a-result-to-mcp-blocks-within-budget/spec.md` | A `Result` becomes one capped text block, typed media blocks, resource links and a byte-free `structuredContent` holding exactly the rows the text showed, and an MCP tool result comes back to a `Result`. | b | 167-1, 167-2, 167-3, 174-4, 176-1, 177-1, 177-4 |
| 171-2 | `../2026-11-25-serve-answers-each-request-under-its-own-authority-and-refuses-an-open-mount/spec.md` | `serve(fs, transport=…)` lists every verb of `AGENT_OPS` as a tool, runs every request under an authority derived for that request alone and never the system actor, refuses to start over an open mount, and reads `vfs:///` resources within a byte budget. | b | 171-1, 149-2 |
| 171-3 | `../2026-11-25-the-cli-tool-runs-one-shell-line-per-call-at-the-wire/spec.md` | The `cli` tool runs one line in a fresh shell at `workdir`, reports a program's non-zero exit as evidence and not as a tool error, and returns an image when the line ends by reading one. | b | 171-2, 167-5, 167-8, 167-9 |

## `172-the-wasi-python-runtime`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 172-1 | `../2026-11-25-the-python-guest-runs-over-wasi-python-as-the-caller/spec.md` | A Python script with numpy and pandas runs inside a WASI guest whose only file system and only verb door are the caller's vfs session, and every refusal reaches the stage classified. | b | 167-5, 167-7, 167-8, 169-2, 174-2, 174-3 |
| 172-2 | `../2026-11-25-a-spike-asks-whether-the-wasi-python-runner-can-host-quickjs/spec.md` | A one-afternoon spike runs a QuickJS-NG `wasm32-wasip1` module under the wasi-python runner's mount and tool protocols and reports whether it can host it. | a | nothing |
| 172-3 | `../2026-11-25-the-javascript-guest-runs-over-the-same-door-as-the-python-guest/spec.md` | A JavaScript program runs in a QuickJS-NG guest under the same provider, door, errno table and exit codes as the Python guest, behind its own extra. | b | 172-1, 172-2 |

## `174-write-preconditions-and-the-guarded-append`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 174-1 | `../2026-11-25-an-identical-body-write-reports-unchanged-and-leaves-the-version-alone/spec.md` | A write or edit whose final body, kind, source and type equal the stored row's reports `unchanged`, mints nothing and writes nothing. | b | dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md |
| 174-2 | `../2026-11-25-an-exclusive-create-replaces-overwrite-on-write-and-is-judged-at-add/spec.md` | `write(if_absent=True)` creates only where no live row stands, refuses `exists` carrying the occupant's version and hash, and `overwrite=` leaves `write`. | b | dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md |
| 174-3 | `../2026-11-25-a-write-that-names-the-version-it-read-is-refused-when-the-row-moved-on/spec.md` | `write(if_version=N)` and `write(entries, if_versions={path: N})` refuse `vfs.conflict` with the current version and write nothing when any named row is not at its expected version. | b | 174-1, dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md |
| 174-4 | `../2026-11-25-append-is-one-locked-read-modify-write-so-concurrent-appends-keep-every-line/spec.md` | `write(append=True)` reads and extends each target inside one transaction under a row lock, at rung `add`, so twenty concurrent appends keep twenty lines on every engine. | b | 174-1, 174-2, 174-3, dated spec: 2026-11-15-on-sql-server-a-read-never-waits-on-a-write.md |

## `175-integrity-verify-on-read-and-scrub`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 175-1 | `../2026-11-25-a-read-refuses-a-body-that-fails-its-recorded-hash/spec.md` | `read` checks every body it serves against its recorded hash and refuses a mismatched, missing or unhashed body with `vfs.unavailable.integrity`, unless the caller asks for the salvage read. | b | dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md, landed: 2026-11-07-storage-measures-every-body-it-stores.md |
| 175-2 | `../2026-11-25-every-written-row-reports-its-hash-and-no-verb-launders-a-damaged-body/spec.md` | Every row `write`, `edit`, `copy` and `move` returns carries `content_hash`; `edit` refuses a damaged pre-image with `vfs.unavailable.integrity`; an overwrite of a damaged body succeeds with a warning and its version row keeps the recorded hash. | b | 175-1, 174-1 |
| 175-3 | `../2026-11-25-the-system-actor-accepts-a-damaged-body-as-found/spec.md` | Only the system actor can accept a body that fails its hash as it stands, which writes a new version whose `content_hash` is the body's own, so history records the acceptance. | b | 175-1, 175-2 |

## `176-the-listing-cursor`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 176-1 | `../2026-11-25-ls-tree-and-glob-page-on-a-path-key-served-by-a-derived-page-in-the-router/spec.md` | `ls`, `tree` and `glob` take `after=` and `limit=` and return the last row's path as `Result.next_after`, paged correctly across every mount for every backend. | b | dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md |
| 176-2 | `../2026-11-25-native-keyset-pages-in-the-database-storage-read-around-tombstones/spec.md` | On every engine a listing page costs a fixed number of statements and visits at most `limit + 1` live rows, however many deleted rows share its directory. | b | 176-1, the deletes spec, not yet written (no roadmap story) |
| 176-3 | `../2026-11-25-a-tree-under-max-depth-pages-on-a-stored-depth-column/spec.md` | A `tree` with `max_depth` visits at most `max_depth × (limit + 1)` rows a page, because each row stores its depth beside its path. | unplaced | 176-2 |

## `177-replay-the-contract-and-the-request-key`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 177-1 | `../2026-11-25-every-mutating-verb-sent-twice-answers-as-a-pinned-replay-table-says/spec.md` | Every write-gated verb sent twice answers as its row of a replay table in `ops.py` says, and a refused replay names what it found. | b | 174-1 |
| 177-2 | `../2026-11-25-a-commit-whose-connection-drops-answers-in-doubt/spec.md` | A connection lost during `COMMIT` answers `vfs.unavailable.in_doubt`, retry class `refresh`, and is never redriven. | b | nothing |
| 177-3 | `../2026-11-25-a-keyed-call-stores-its-answer-with-its-change-and-a-resend-gets-it-back/spec.md` | A mutation sent with a request key stores its whole `Result` in the same transaction as its change, and a resend with the same key gets that answer back with one `vfs.replayed` record and no mutation statement. | b | 177-2 |
| 177-4 | `../2026-11-25-request-key-is-an-argument-of-every-keyed-verb-at-the-router/spec.md` | `request_key` is a keyword argument of the twelve keyed verbs on every face, and a keyed call to a mount without the `replay` trait is `vfs.unsupported`. | b | 177-3 |

## `178-the-ranged-read`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 178-1 | `../2026-11-25-the-engine-cuts-a-byte-slice-of-a-body-on-every-tuned-dialect/spec.md` | Each tuned dialect returns the exact bytes of a body slice, for `data` raw and for `content` as UTF-8, in one statement. | b | nothing |
| 178-2 | `../2026-11-25-read-takes-a-byte-range-and-the-row-says-which-slice-it-carries/spec.md` | `read(path, range=(offset, length))` serves the slice cut by the engine, snapped outward to whole characters on text, with `range_start` and `range_length` on the row, and a backend that cannot cut is served the range by the router. | b | 178-1 |
| 178-3 | `../2026-11-25-a-ranged-read-meets-the-integrity-check/spec.md` | A ranged read of a body whose stored row is missing or whose whole-body slice fails its hash is classified as a whole read is, and a partial slice is treated as the integrity ruling says. | b | 178-2, 175-1 |

## `179-the-storage-seam-as-the-kernel`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 179-1 | `../2026-11-25-the-conformance-battery-is-split-by-kernel-operation-with-no-test-lost/spec.md` | The storage and grants contracts become one package of mixins by kernel operation, and the collected node ids before and after the split are equal line for line. | b | nothing |
| 179-2 | `../2026-11-25-the-storage-protocols-are-regrouped-into-families-before-the-freeze/spec.md` | The storage seam's protocol families follow the kernel's operation groups, the write family no longer carries the edges or the trash, and the old family names are gone before the surface freezes. | b | 167-1, 179-1, 181-1 |
| 179-3 | `../2026-11-25-the-seam-states-its-atomic-unit-and-its-two-atomicity-models/spec.md` | Every backend declares its atomic unit as a trait, every mutating seam method names its model in one table, and the protocol module's docstring states the atomic unit, the fault model and the two halves of the gate once. | f | nothing |
| 179-4 | `../2026-11-25-durability-is-read-from-the-live-connection/spec.md` | A mount's durability trait comes from one probe of the engine's own setting at first touch, and an in-memory store declares none. | f | nothing |
| 179-5 | `../2026-11-25-a-failed-engine-call-carries-the-engines-own-code-as-a-field/spec.md` | Every classified engine failure and every exhausted-retry conflict carries the driver's own error code in `data["vfs.engine_error"]`, read from driver attributes and never from message text. | f | nothing |
| 179-6 | `../2026-11-25-a-batch-with-one-bad-row-writes-nothing-on-any-engine/spec.md` | A mutation batch with one bad row returns only that row's error, commits nothing and leaves every table of the mount unchanged, at ten thousand rows and on every engine leg, while a batch across two mounts is atomic per mount only. | f | 179-1 |
| 179-7 | `../2026-11-25-a-crash-at-any-mutating-statement-or-seam-leaves-the-store-whole/spec.md` | A fault at every mutating statement and a crash at every named seam of every whole-batch verb leaves the store equal to its before-image after a reopen, a retryable fault is redriven once and counted, and resumable passes converge on the next call. | f | 179-5, 179-6 |
| 179-8 | `../2026-11-25-each-kernel-verbs-access-path-is-a-reviewed-golden-table/spec.md` | Every kernel verb's ordered statements, rows and payload bytes at the system actor, a named principal and anonymous are pinned per engine family, so a new statement appears only as a reviewed fixture diff. | unplaced | 179-1 |
| 179-9 | `../2026-11-25-a-named-caller-revalidates-its-rights-in-one-statement/spec.md` | A named or anonymous caller's cached rights are revalidated by one statement instead of two, and the rights cache counts its hits, misses, stale entries and evictions. | unplaced | 179-8, dated spec: 2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md |
| 179-10 | `../2026-11-25-a-backend-that-lacks-a-derivable-verb-is-still-served-it/spec.md` | A backend that declares only the file read and write families is served `tree`, `copy`, `glob`, `grep` and, once guarded writes exist, `edit` by the kernel, with the same rows as a native backend, and declares through `features()` which arguments it serves itself. | f | 179-2, 174-3, 176-1, 177-4, 178-2 |

## `180-history-pack-on-reindex-and-the-bounded-sweep`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 180-1 | `../2026-11-25-a-files-replaced-versions-are-listed-newest-first-in-pages-with-who-wrote-each/spec.md` | `versions(path)` lists a file's version rows newest first, a bounded page at a time, each row carrying its label, hash, size, source, time and attribution, under the read rung on the file's current path. | f | 176-1, 181-1, dated spec: 2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md |
| 180-2 | `../2026-11-25-any-prior-version-of-a-file-is-read-back-whole-and-verified-by-its-hash/spec.md` | `read(path, version=N)` returns body N, rebuilt from its chain and checked against its stored hash, and a mismatch is `vfs.unavailable.integrity`, never success. | f | 175-1, 180-1 |
| 180-3 | `../2026-11-25-the-full-index-pass-packs-cold-history-into-snapshots-and-verified-forward-diffs/spec.md` | `rebuild` runs a `pack` phase that rewrites cold version rows into one snapshot and at most nine forward diffs each, lands a diff only when it is smaller and has reconstructed the body by hash, and never deletes a row or changes its attribution. | 0.2 | 180-2 |
| 180-4 | `../2026-11-25-the-trash-retention-pass-reclaims-in-short-slices-one-transaction-each/spec.md` | The retention arm of the irreversible verb runs in slices of at most one membership budget, each its own transaction under the serialization point, and its orphan reclaim walks `vfs_content`, `vfs_blobs` and `vfs_versions` in `entry_id` windows instead of a whole-table anti-join. | 0.2 | the deletes spec, not yet written (no roadmap story) |
| 180-5 | `../2026-11-25-a-retention-pass-resumes-from-where-the-last-call-stopped/spec.md` | The retention arm takes `limit=` and `after=`, processes at most `limit` units a call, and returns a resumption key that the next call continues from. | 0.2 | 180-4, 176-1 |
| 180-6 | `../2026-11-25-a-gauge-reports-how-much-garbage-a-mount-holds/spec.md` | A storage-level maintenance read beside `rebuild()` counts tombstones, expired tombstones, version rows, unjudged rows and logical and stored version bytes in exactly two statements. | 0.2 | 180-3, 180-4 |

## `181-the-public-surface-regrouped-by-kernel-group`

| Key | Spec | Title | Gate | Depends on |
|---|---|---|---|---|
| 181-1 | `../2026-11-25-every-routed-op-sits-in-one-group-and-every-face-lists-the-verbs-in-that-order/spec.md` | Every routed op sits in exactly one group in `ops.py`, and the op literal, the needs table, the parameter table and the four public faces list the verbs in that one order, held by drift tests. | b | 167-1 |
| 181-2 | `../2026-11-25-every-row-reports-the-entrys-permanent-id-and-its-owner/spec.md` | Read rows and mutation rows carry `entry_id` and `owner_id` as projectable, read-only columns at the read rung, a bare row carries neither, and a write of an input naming `entry_id` is refused `vfs.invalid`. | b | nothing |
| 181-3 | `../2026-11-25-chaining-moves-onto-the-result-and-the-query-verbs-lose-rows-in-hand/spec.md` | `Result.pipe` hands a result's rows to the next verb, public `vfs.chain.glob` and `vfs.chain.grep` filter rows in hand, and `glob` and `grep` take no `observations=`. | unplaced | 181-1 |
| 181-4 | `../2026-11-25-the-derived-verbs-are-pinned-to-their-definitions-by-oracles/spec.md` | `tree` equals `ls` repeated and `edit` equals a read then a guarded write, row for row, at the system actor and at a principal with a partial view, and `delete(cascade=False)` on a non-empty directory is `not_empty`. | unplaced | 174-3 |
