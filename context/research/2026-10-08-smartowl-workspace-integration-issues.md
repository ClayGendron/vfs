# vfs bugs and issues found while planning the SmartOwl workspace demo

- **Status:** research memo. Commits us to nothing. Feeds the fixes for the SmartOwl workspace demo and any follow-up specs here.
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Question:** What in vfs v2, at commit `06e14b0`, is broken, misleading, or missing when a host app (SmartOwl) puts an agent and a user on one vfs namespace with a read-only mount and a read-write mount?
- **Method:**
  1. Four research subagents read `src/` and `tests/` at `06e14b0` while planning the SmartOwl integration.
  2. One of them drove the September `wgu_demo` command function against the current `src/` in memory, with two mounts and no database.
  3. Each item below says how it was checked:
     - **ran:** observed in that in-memory run;
     - **read:** read in the code or docs;
     - **unverified:** suspected, not yet confirmed.
- **Full context:** SmartOwl's research record, `smartowl/context/01_research/2026-10-08_vfs-workspace-demo/RESEARCH.md`.

## The short version

There are four kinds of problem:

1. **The README promises things the code doesn't do yet.** Versioning of every change, a `"read_only"` permission string, and backend classes that don't exist.
2. **Agent-facing text has rough edges.** Wrong paths in error messages, a hint an agent can't follow, empty output, unbounded output.
3. **The namespace has three holes.** A writable default root, a writable trash, and permissions that live on the mount object, not the data.
4. **Packaging and setup are awkward for a host app.** No Linux wheel, a version number shared with the old release, and schemas you must create by hand.

Items 7 and 8 are being fixed now, uncommitted, in this checkout.

One line: **the core works and the read-only gate holds, but the docs overpromise, agent-facing text needs polish, and three namespace holes need closing.**

## A. Docs that don't match the code

### 1. "Every mutation is versioned" is not true yet

- **What:** the README says every mutation is "versioned, reversible" (`README.md` L52–55). But no code writes a version row.
  - `write` and `edit` replace the old body in place (`src/vfs/storage/backends/database/writes.py` L1–27).
  - Spec 152 says it directly: "No write path mints a version row today" (`context/specs/active/152-binary-bodies-and-text-renderings/spec.md` L132–135).
  - The `vfs_versions` table and the `Version` model exist (`src/vfs/models/rows.py` L515–536). The only code that touches them is the trash purge (`topology.py` L713). Tests insert version rows by hand.
- **Effect:** an overwrite by `write` or `edit` can't be undone. Delete can be undone, through trash and `restore`. Move can be undone with a second move.
- **Checked:** read.
- **Direction:** either build version minting, or soften the README until it lands.

### 2. The README's permission string is wrong

- **What:** the README says `"read_only"` (`README.md` L110). The code accepts only `"read"` or `"read_write"`, and raises `ValueError` for anything else (`src/vfs/permissions.py` L116–127).
- **Effect:** a user copying the README gets an error at mount time.
- **Checked:** read.

### 3. The README's code example uses classes that don't exist

- **What:** the example imports `DatabaseFileSystem` and `PostgresFileSystem` from `vfs.backends` (`README.md` L31–35). There is no `src/vfs/backends/` package, and neither class exists in v2. The real class is `vfs.storage.backends.DatabaseStorage`.
- **Effect:** the first code a new user runs fails to import.
- **Checked:** read. `ls src/vfs/backends` finds nothing, and a grep for both class names finds nothing.

### 4. `docs/deepagents-integration.md` describes the old API

- **What:** the deepagents integration doc describes the previous-generation API, though a `deepagents` extra exists in `pyproject.toml` (L60). v2 has no deepagents adapter.
- **Checked:** read.

### 5. Tools at paths: `run` exists, the feature doesn't

- **What:** the README says tools at paths are "designed, not built" (`README.md` L19), but `VirtualFileSystem.run` exists (`src/vfs/base.py` L1511–1531).
- **Effect:** easy to misread as working. The September demo's `call get_weather` is a stub inside the demo, not vfs.
- **Checked:** read.

### 6. v2 still calls itself `vfs-py` 0.0.22

- **What:** `pyproject.toml` (L14–15) and `src/vfs/__init__.py` (L1) both say 0.0.22. That is the same name and version as the obsolete PyPI release of the previous generation.
- **Effect:** a host can't tell v2 from the old release by version pin. It has to check imports instead.
- **Checked:** read.

## B. Agent-facing text

### 7. Error messages repeat a mount-local path *(fix in progress)*

- **What:** producers put a path inside `message` in the storage's own coordinates. The renderer prints the correct, rebased path as the locus, then the message prints the wrong one. Example, reading a missing `/mine/missing.md`: `ERROR /mine/missing.md: Not found: /missing.md`.
- **Same pattern elsewhere:** `Already exists: /a.md` and `Is a directory: /`.
- **Why it can't be fixed at the router:** `ResultError` forbids it. Its docstring says rebase seams never touch `message`, and no consumer may parse it (`src/vfs/results/envelope.py` L97–99).
- **Scope:** about 26 producer sites embed a path. They are in `envelope.py`, `editing.py`, `permissions.py`, `base.py`, and the database backend's `topology`, `edges`, `staging`, `writes`, `rights` and `descent` modules.
- **Effect:** an agent may retry the wrong path (`/missing.md`), which sits outside every mount.
- **Checked:** ran.
- **Fix being made:** messages state only the cause (`Not found`). The structured `path` carries the location, and the renderer already prints it.

### 8. The short-pattern grep hint names a Python keyword *(fix in progress)*

- **What:** a grep pattern with no literal run of 3+ characters (`ab`, `\w+`) is refused as `unindexable_pattern`. The hint says "pass allow_scan=True" (`src/vfs/results/kinds.py` L194–198). A command-line caller, which includes every agent, can't pass a Python keyword.
- **Checked:** ran.
- **Fix being made:** caller-neutral wording: "…or request the scan tier."

### 9. Output has no size limit

- **What:** `Result.to_str()` never truncates. In the in-memory run, `read` of a 5,000-line file returned 83,890 characters, and an unscoped `grep` returned 172,782.
- **Effect:** one call can flood an agent's context window. Every host has to build its own cap. Anthropic's guidance is to page and to steer with truncation notes.
- **Checked:** ran.
- **Direction:** an optional render budget with a "narrow with …" or "next page …" note. This is a render option, not a storage limit, so it doesn't conflict with the no-scale-caps rule.

### 10. An empty result renders as an empty string

- **What:** `ls` of an empty directory and a search with no hits both render `""`.
- **Effect:** an agent can't tell "nothing found" from "the tool failed silently."
- **Checked:** ran.
- **Direction:** render `(no matches)` or `(empty directory)`.

### 11. `ls` doesn't mark directories

- **What:** the default projection is the path only (`src/vfs/results/projection.py` L53), so files and directories look the same.
- **Checked:** ran.
- **Direction:** add a trailing `/` on directories in the text rendering.

### 12. Fan-out repeats the same error once per mount

- **What:** an unscoped `grep` that fails the same way on two mounts prints the error twice, once as `mount /` and once as `mount /mine`. By the envelope's value-identity rule they are distinct facts (their `source` differs), so this is correct data. It is noisy text, though.
- **Checked:** ran.
- **Direction:** collapse identical messages in the text renderer only, listing the mounts once.

### 13. `glean` shows the last hit with score 0.0000

- **What:** min-max scaling always maps the lowest hit in a result to exactly `0.0000`.
- **Effect:** it reads as "irrelevant" even when it's a fair match.
- **Checked:** ran.
- **Direction:** show rank, or raw scores, or scale against a fixed floor.

## C. Holes in the namespace

### 14. The default root is writable

- **What:** a `VirtualFileSystem()` with no storage gets an `InMemoryStorage` root with `"read_write"` (`src/vfs/base.py` L320–362). Writes to paths outside every mount, like `write /x` or `mkdir /evil`, succeed.
- **Effect:** the files are invisible to any viewer that lists the mounts, and they vanish on close. This breaks confinement to the mounts.
- **Checked:** read.
- **Possible fix (untested):** after mounting, call `remount("/", deny_ops=MUTATING_OPS)`. Or default the bare root to read-only once it has mounts.

### 15. The trash is writable

- **What:** `/mine/.vfs/trash/...` accepts `write`, `edit` and `move` (`tests/base/test_gates.py` L247–254).
- **Effect:** an agent can overwrite or remove a trashed copy, and so destroy the only way to undo a delete. This matters most under prompt injection.
- **Checked:** read.
- **Possible fix (untested):** mount with `read_write(read=["/.vfs"])`. But that also blocks `restore` through the router, so restore would need its own allowance. vfs has no per-verb prefix rule today; its permission maps are only read or read-write per prefix.

### 16. Permissions live on the mount object, not on the data

- **What:** a permission map belongs to one `VirtualFileSystem` instance (`src/vfs/permissions.py` L57–81). Two instances on the same database and schema share the rows. If one is mounted `read` and the other `read_write`, the writable one can change the "read-only" data.
- **Effect:** hosts must give each read-only mount its own database or schema. That's easy to get wrong.
- **Checked:** read.
- **Direction:** document it prominently. Row-level grants, designed but not built, are the long-term answer.

### 17. A `..` path into a read-only mount has no router-level test

- **What:** paths are canonicalized before routing, so `/mine/../course/x` becomes `/course/x` and meets the `/course` gate (`src/vfs/paths.py` L485–506; path tests in `tests/test_paths.py` L82–101). No test drives that case end to end through the router and the gate.
- **Checked:** read. The behavior is inferred from code.
- **Direction:** add one router-level test.

## D. Host integration and packaging

### 18. No Linux wheel for v2

- **What:** `vfs.native` has no pure-Python fallback (`src/vfs/native.py` L26–41). The only local wheel is `vfs_py-0.0.22-cp311-abi3-macosx_11_0_arm64.whl`.
- **Effect:** a Linux container needs a manylinux wheel built with maturin, or a Rust toolchain in the image. That means compiling about 57 tree-sitter grammars (`crates/vfs-core/Cargo.toml` L17–86), which is slow under x86_64 emulation on an Apple-silicon Mac.
- **Checked:** read. The SmartOwl api container has no cargo or rustc.

### 19. `schema=` requires schemas created by hand

- **What:** `DatabaseStorage(schema=...)` qualifies its tables (`src/vfs/storage/backends/database/engine.py` L133–154). vfs never runs `CREATE SCHEMA`; a grep of `src/vfs` finds none. It does run `CREATE EXTENSION IF NOT EXISTS vector` (`src/vfs/models/rows.py` L876).
- **Effect:** the first touch fails unless the host creates the schema first. The extension step also needs a role that may create extensions.
- **Checked:** read.
- **Direction:** create the schema if it's missing during first-touch provisioning, or name the missing schema in the error.

### 20. Postgres needs asyncpg, so a host's psycopg sessions can't be borrowed

- **What:** the Postgres dialect's bulk insert is `COPY` through asyncpg's `copy_records_to_table` (`src/vfs/storage/backends/database/dialects.py` L808–821).
- **Effect:** a host on psycopg 3, like SmartOwl, can't pass its own session factory. It must give vfs a separate `postgresql+asyncpg://` URL and its own engine.
- **Checked:** read. Not run.
- **Direction:** fall back to a multi-row `INSERT` when the driver isn't asyncpg, or document the requirement.

### 21. Rendering waits for `reindex()`

- **What:** a binary `write` stores bytes with `render_status` `pending`. Until a `reindex()` runs, `read` returns a warning with no content, and `grep` and `glean` skip the file (spec 152 L106–110, L240–251).
- **The lease:** `reindex()` covers the whole storage under a lease. A second concurrent reindex fails with a retryable `conflict` (`src/vfs/storage/backends/database/backend.py` L1016–1047).
- **Effect:** a host's upload endpoint has to call `reindex()` and retry on `conflict`, or show "indexing" until a background reindex finishes.
- **Checked:** read.
- **Direction:** render one entry at write time, or offer a path-scoped reindex.

### 22. `copy` and `move` across mounts are refused

- **What:** a copy or move between mounts is refused as `cross_mount` (`src/vfs/base.py` L2419–2483).
- **Effect:** "copy the course rubric into my files" has to be `read` then `write`. That only works for text, because binary bodies can't go through `edit` or text `write`.
- **Checked:** read. This is by design, but agents will expect `cp` to work.
- **Direction:** a cross-mount copy done as read plus write inside the router, for files only.

### 23. Smaller things

- **Scanned PDFs render empty:** there's no OCR (spec 152 L176–179). DOCX renderings have no page markers.
- **`edit` refuses binary bodies:** this is by design (spec 152 L111–116), but it is worth stating in agent-facing tool text.
- **`glean` doesn't report unrendered files:** it doesn't say how many files were skipped as unrendered. This is open in spec 152, L271–272.
- **Unverified: the default posture.** Calls with no authority run as the anonymous identity (`src/vfs/base.py` L113–114), and `DatabaseStorage` defaults to the `open` posture (`backend.py` L196). Nobody checked that `open` allows anonymous reads and writes on every verb.
- **Unverified: copy onto an occupied destination.** Its docstrings partly conflict about what happens.

## Not vfs, but noted: the September `wgu_demo`

These are in the uncommitted demo, not in `src/`:
- `call get_weather` is a stub table inside the demo.
- An unbalanced quote raises outside its error handling.
- It has no command-length, output-size or timeout bounds.
- It leaves the root writable.
- It has no `delete`, `move`, `copy`, `mkdir`, `restore` or `stat` verbs.
- `grep` scopes with `--path`, not a positional path.
- Its MCP server targets `mcp>=2`.

One line again: **the core and the read-only gate are sound. Fix the README, polish agent-facing text, close the root and trash holes, and make setup easier for host apps.**

## Verification at `06e14b0` (2026-10-08, Claude, same day)

Every item above was re-checked against the live tree, by reading the code and by running an in-memory namespace with a `read` mount at `/course` and a `read_write` mount at `/mine` (both `InMemoryStorage`, permissions set on `add_mount`), plus one sqlite-backed `DatabaseStorage` for the posture question. Verdicts:

| Item | Verdict | Note |
|---|---|---|
| 1–4, 6 | confirmed by reading | `permissions.py`'s own docstring also still says `DatabaseFileSystem`. |
| 5 | accurate, not a bug | `run` is a router verb that dispatches to a storage supporting it. |
| 7, 8 | confirmed by running | the grep *message* says `pass allow_scan=True` too, not only the hint table. |
| 9 | confirmed by running | 5,000-line read: 103,889 chars; unscoped grep over 3,000 hits: 120,782 chars. |
| 10, 11, 13 | confirmed by running | two glean hits print `1.0000` and `0.0000`. |
| 12 | confirmed, understated | the bare root mount errors too: three mounts print four copies. |
| 14 | confirmed by running | `write /x` and `mkdir /evil` succeed on the default root. |
| 15 | partly confirmed | `write` to a trashed path overwrites its body; `delete` on a trashed copy re-trashes it under a second ULID prefix, so the hole is overwrite, not deletion. |
| 16 | confirmed | `permissions.py` L57–81 documents it as a known limitation. |
| 17 | not a bug, a test gap | `write /mine/../course/x.md` is refused `read_only` at `/course/x.md`; no router test pins it. |
| 18 | overstated | no v2 on PyPI and no Linux wheel on disk, but `.github/workflows/publish.yml` already builds manylinux 2_28 and musllinux wheels for x86_64 and aarch64 on a GitHub release. |
| 19 | confirmed by reading | no `CREATE SCHEMA` in `src/`. |
| 20 | confirmed by reading | the Postgres profile pins `bulk_insert="copy"` (`dialects.py` L393) regardless of driver; that branch calls asyncpg's `copy_records_to_table` on the raw connection. |
| 21, 22 | confirmed | copy is refused `cross_mount` even between two `read_write` mounts. |
| 23, posture | now verified | anonymous read, write and delete all succeed on a default `DatabaseStorage` over sqlite. |
| 23, copy docstrings | not found | `topology.py` says an occupied destination refuses `exists` at both sites (L391, L547); the router's `copy` has no docstring. |

Two corrections to the memo itself:

- "Items 7 and 8 are being fixed now, uncommitted, in this checkout" was not true of the vfs checkout at `06e14b0`; its only uncommitted change was `context/open-questions.md`.
- One crash the memo missed: mounting a `VirtualFileSystem` node directly with `add_mount` passes the `StorageBackend` structural check, and `read` and `write` route through it, but `glob` raises `TypeError` because the router passes `patterns=` while the node's verb takes `pattern=`. The README's "mounts nest" sentence invites exactly this shape.

The specs cut from this memo are 153–161 under `../specs/active/`.
