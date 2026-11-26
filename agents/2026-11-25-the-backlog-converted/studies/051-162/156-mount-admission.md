# Study: Mount admission, a `..` gate test, and no bare node as a mount

## Verdict

live-unplaced. The kernel face `AsyncVirtualFileSystem` is still admitted by `add_mount`, `bind` and `__init__(storage=)`, routes `read` and `write`, and then crashes `glob` with `TypeError ... unexpected keyword argument 'patterns'` (EXECUTED, scratch probe at HEAD 0ed462f); the router-level `..` gate test does not exist either (EXECUTED, grep). No roadmap story names the spec, but the README's Known limits already promises the refusal as fact, so the gap is a false public claim that roadmap story R5 criterion 7 (gate b) would catch; it is worth one small spec.

## Against the tree

- The admission checks are structural only: `isinstance(storage, StorageBackend)` in `AsyncVirtualFileSystem.__init__` and in `bind` (READ, `src/vfs/base.py:379`, `src/vfs/base.py:441`); `add_mount` reaches `bind` after a gated mkdir (READ, `src/vfs/base.py:511-553`). `StorageBackend` is a `@runtime_checkable` protocol over the read family plus `name`, `description` and `capabilities()` (READ, `src/vfs/storage/protocol.py:440-458`).
- The kernel face satisfies that structure: `isinstance(AsyncVirtualFileSystem(), StorageBackend)` is `True` (EXECUTED). It has `capabilities()` (READ, `src/vfs/base.py:799`) and `name`/`description` attributes (READ, `src/vfs/base.py:386-388`).
- The crash the spec describes is still true, now on the kernel face: `await fs.add_mount(AsyncVirtualFileSystem(), "/n")` succeeds, `write` and `read` through it succeed, and `glob("/n/**")` raises `TypeError: AsyncVirtualFileSystem.glob() got an unexpected keyword argument 'patterns'. Did you mean 'pattern'?` (EXECUTED). The cause: the storage protocol's `glob(*, patterns: tuple[str, ...], ...)` (READ, `src/vfs/storage/protocol.py:277-282`) against the router's `glob(self, pattern: str, ...)` (READ, `src/vfs/base.py:1265-1268`).
- `AsyncVirtualFileSystem(storage=AsyncVirtualFileSystem())` is accepted (EXECUTED).
- The synchronous face `VirtualFileSystem` (a thread-loop facade, `src/vfs/sync.py`) is not a `StorageBackend` and is already refused by the structural check, with the misleading message "storage must implement the read family (see vfs.storage), got VirtualFileSystem" (EXECUTED, both `add_mount` and `storage=`).
- The synchronous face accepts a kernel-face node: `VirtualFileSystem().add_mount(AsyncVirtualFileSystem(), "/n")` succeeds (EXECUTED), since `sync.add_mount` forwards to the kernel's (READ, `src/vfs/sync.py:212-232`).
- `AsyncSession` is not a `StorageBackend` (EXECUTED); it needs no refusal.
- The `..` canonicalization is correct at the router: with `/mine` and `/course` (`permissions="read"`) mounted on `InMemoryStorage`, `write(path="/mine/../course/x.md")` fails with one `vfs.read_only` error at `/course/x.md` (EXECUTED). The pins stay unit-level: `tests/test_paths.py:84-103` and `locate` at `tests/base/test_mount_admin.py:540` (READ); no test under `tests/` writes through a `..` into a sibling mount (EXECUTED, grep for `"/x/../` shapes found only `tests/results/test_results.py:435`, a payload fixture).
- No nominal check exists: grep for `isinstance(storage, ...VirtualFileSystem)` and "router, not a storage" in `src/vfs` and `tests` returns nothing (EXECUTED).
- Spec 153 landed and archived 2026-10-10 (READ, `context/specifications/archive/153-docs-tell-the-truth-about-v2/spec.md:3`). It softened the README to "Mounts can be bound at any depth" (READ, `README.md:62`) and added the Known limits bullet "Neither face is a storage and neither can be mounted. `add_mount` takes a storage backend (spec 156 makes the refusal explicit)" (READ, `README.md:141`). The first half of that bullet is false for the kernel face at HEAD (INFERRED from the EXECUTED probe).
- Rule 1 (default root) was dropped and the README carries it (READ, `README.md:60`). Rule 2 (trash) was handed to spec 162, still active as `context/specifications/active/162-trash-as-a-tombstone-on-the-row/` (EXECUTED, ls); ADR 074 was retired with the other ADRs on 2026-10-30, so that hand-off rests on spec 162, not the ADR (INFERRED from the task's ground rules).
- Source memo: item 17 and the verification addendum's missed crash (READ, `context/research/2026-10-08-smartowl-workspace-integration-issues.md:144`, `:223`, and the addendum line 27 of that section).

## Where the roadmap places it

- No roadmap row names spec 156, "mount admission", a bare node or a router-as-storage refusal (EXECUTED, grep of `context/standards/roadmap.md` for `156`, `bare node`, `not a storage`, `nest`, `adapter`).
- Nearest placement: R5 "Freeze the surface", gate b, criterion 7, "Every README and docs claim is re-checked against ADR 058 pin 7 at b1" (READ, `context/standards/roadmap.md:936`, `:947`). The Known limits bullet at `README.md:141` fails that re-check today, so either this fix lands before b1 or the bullet is rewritten there (INFERRED).
- The adapter alternative falls under the cut-list row "reference adapters for host frameworks", 0.2+ (READ, `context/standards/roadmap.md:1059`), only loosely; no row places a node-to-storage adapter (INFERRED).
- Gate: unplaced; recommended gate b beside R5, since the change is small, freezes an admission rule of a public method, and makes a README claim true (INFERRED).

## Units proposed

One unit; both slices are a few lines and a few tests and land together.

- Slug: a router is refused as a mount and a dot-dot path meets the sibling's gate. Title: "Binding a `VirtualFileSystem` or `AsyncVirtualFileSystem` as storage raises a `TypeError` that says a router is not a storage, and a write through `..` into a read-only sibling mount is refused at the sibling's path." Gate: unplaced (recommended b, ahead of R5's b1 re-check). Depends on: nothing; R5 criterion 7 reads its result. Rewrite depth: amend (the names `add_mount`/`__init__` stand, `bind` joins them, the face names changed on 2026-11-06, the adapter reference in the message goes, line citations move).

## Open choices, each verified

- Choice: refuse a node at admission, or ship an adapter that forwards a node's verbs under the storage protocol's names (`patterns=` for `pattern`, and the rest); lean refuse now, adapter as its own spec (READ, spec.md Decided semantics item 4). Verification: holds-amended. Consistency: the constitution forbids partial or silent implementations of a declared capability (READ, `context/standards/constitution.md:110`), and today the kernel face is admitted as a storage while its `glob` cannot answer the storage call, which is exactly such a partial implementation; refusal also matches the README's published claim (READ, `README.md:141`) and the cut list deferring adapters to 0.2+ (READ, `context/standards/roadmap.md:1059`). Precedent: the landed structural refusal already rejects non-storages with `TypeError` at `src/vfs/base.py:379` and `:441`, and the sync face is already refused (EXECUTED). Amendment: the message must not say "wrap it in the node adapter", because no adapter exists in the tree (EXECUTED, grep); state instead "a VirtualFileSystem/AsyncVirtualFileSystem is a router, not a storage; mount its storages directly". The refusal covers `bind` as well as `add_mount` and `__init__(storage=)`, because `bind` is the primitive `add_mount` calls and the check lives there (READ, `src/vfs/base.py:441`, `:552`).
- Choice (implicit): where the sync face's nominal check lives. `src/vfs/sync.py` imports `vfs.base` (READ, `src/vfs/sync.py:33`), so `base.py` cannot import the sync class without a cycle, which AGENTS.md forbids papering over. Lean (this study's): `base.py` refuses `AsyncVirtualFileSystem` nominally; `sync.py`'s `__init__`, `bind` and `add_mount` refuse a `VirtualFileSystem` nominally before forwarding, so its message stops reading "must implement the read family". Verification: holds; precedent none found for a split check; rests on the Imports rule in AGENTS.md (no function-local import, a cycle is fixed structurally) and on the existing one-way dependency `sync -> base`.
- Choice (implicit): nominal `isinstance` against the class or a subclass-inclusive check. Lean: `isinstance`, which also refuses subclasses of either face. Verification: holds; precedent none found; rests on the spec's one line, "a mount is a storage", which a router subclass is not.

No `[NEEDS CLARIFICATION]` marker remains unanswered by precedent; none is closed by a later ruling (the 2026-11-15 names ruling does not touch `add_mount`, `bind` or admission; READ, `context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md`, grep for mount/bind).

## What is stale

- "`VirtualFileSystem` handed to `add_mount` passes the structural check": the sync face `VirtualFileSystem` no longer passes (EXECUTED); the face that passes is `AsyncVirtualFileSystem`, named the kernel on 2026-11-06 (READ, `context/standards/roadmap.md:99`, `:816`).
- `base.py` L337, L399 for the structural checks: now `src/vfs/base.py:379` (`__init__`) and `src/vfs/base.py:441` (`bind`); `add_mount` is at `src/vfs/base.py:511` and delegates to `bind` (READ).
- `protocol.py` L414 for `StorageBackend`: now `src/vfs/storage/protocol.py:440-441` (READ).
- The refusal named only for `add_mount` and `__init__`: `bind` is the public primitive that holds the check and must carry it (READ, `src/vfs/base.py:410`, `:441`); the sync face has its own `bind` and `add_mount` (READ, `src/vfs/sync.py:188`, `:212`).
- `test_mount_admin.py` L539 for `locate`: now `tests/base/test_mount_admin.py:540` (READ). `tests/test_paths.py` L82-101: now `:84-103` (READ).
- "The README's 'mounts nest' sentence is softened by 153": done; it reads "Mounts can be bound at any depth" (READ, `README.md:62`), and the Known limits bullet citing this spec was added (READ, `README.md:141`).
- "Dissolved by ADR 074 (accepted)": ADRs were retired 2026-10-30; spec 162 carries the trash rule (EXECUTED, ls of active specs).
- The error message's "node adapter": no such adapter exists (EXECUTED, grep).
- "`scripts/ci.sh 3.13` green": the gate is `scripts/ci.sh` (Python 3.13 by default) per AGENTS.md Tooling (READ, `AGENTS.md`).

## Notes for the conversion

- Roadmap decisions required: none. No D-number in section 16 bears on admission (READ, `context/standards/roadmap.md:1067-1134`, scanned for mount/storage/node rows; D15 and D38 concern `serve()` and a `/.vfs/mounts` view).
- Acceptance the new spec should state: `AsyncVirtualFileSystem().bind(AsyncVirtualFileSystem(), "/n")`, `add_mount(AsyncVirtualFileSystem(), "/n")` and `AsyncVirtualFileSystem(storage=AsyncVirtualFileSystem())` raise `TypeError` naming the router; the same three on the sync face with a `VirtualFileSystem` and with an `AsyncVirtualFileSystem` argument raise the same `TypeError`; `add_mount` refuses before its mkdir, so no mount-point directory is minted (INFERRED from `src/vfs/base.py:545-546`, where the mkdir precedes `bind`; the check must move ahead of the mkdir or be repeated there).
- The `..` test: router level, in `tests/base/test_gates.py`, asserting one `ErrorKind.read_only` with `path == "/course/x.md"` and that the `/course` storage received zero write calls (a counted spy, per AGENTS.md Performance tests); it passes on first run, so tests-first means a test that pins existing behaviour, which the spec says plainly (EXECUTED, the behaviour already holds).
- Tests first: the nominal refusal tests fail at HEAD (EXECUTED: the kernel face is accepted), so they are written and seen red before the check.
- Scale: the change adds one `isinstance` per bind and no statement, row or lock; nothing to cost against the reference deployment (INFERRED).
- The landing updates `README.md:141` to drop "(spec 156 makes the refusal explicit)" once the refusal is explicit, which satisfies R5 criterion 7 for that bullet (INFERRED).
- Out of scope stays as written: default root policy, row-level grants, the trash (spec 162), a node adapter (0.2+ if ever).
