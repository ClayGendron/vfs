# 153 — Docs tell the truth about v2: every README claim matches the live tree

- **Status:** landed and archived 2026-10-10 — commit `4b598bc`; the gate `scripts/ci.sh` ran green on 2026-10-10 at `b446c76`.
- **Earlier status:** **built 2026-10-10, awaiting Clay's review** — every
  scope item landed in one pass over `0760fe9`; ruff, format, ty and
  the doc fences green (the full `scripts/ci.sh` leg was not run, at
  Clay's ask); see *Landing notes* at the end. Cut 2026-10-08 from the
  SmartOwl integration memo; revised 2026-10-08 after a review against
  `0760fe9` (banner, Status section, the third versioning sentence,
  the Sybil doc-test, five dead extras, the `docs/` audit)
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** docs (README, `docs/`, one module docstring, `pyproject.toml`
  extras); no code behaviour changes
- **Depends on:** nothing lands first. 161 (version rows on every
  mutation) decides when the versioning sentences come back; 160
  removes the cross-mount bullet when it lands; 156 owns the "mounts
  nest" sentence.
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  items 1–5, 16, 22 and 23.

## Intent

The README is the first thing a host developer reads, and today its
first code block does not import, its permission string raises, and
its verb table promises an undo that no write path provides. A host
copying the README fails at mount time. Make every sentence in the
README true of the live tree at the commit it ships with, say plainly
what is designed but not built, and remove or quarantine the
previous-generation pages under `docs/` so a reader cannot land on
them.

One line: the README describes the code that exists, not the code we
want, and no page under `docs/` describes code that no longer exists.

## What is wrong today (verified 2026-10-08 against `0760fe9`)

1. **Versioning, three places.** `README.md` L52–55 calls mutations
   "versioned, reversible" and says "a mutation is always versioned so
   it can be undone"; L87 shows `versions/2 — history — operations are
   reversible` in the "Everything is a file" tree. No write path mints
   a version row; `write` and `edit` replace the body in place. Only
   delete is reversible, through trash and `restore`.
2. **Permission string.** L110 says `"read_only"`. `validate_permission`
   (`src/vfs/permissions.py` L116–127) accepts `"read"` and
   `"read_write"` and raises `ValueError` on anything else.
3. **Backend classes.** L31–35 import `DatabaseFileSystem` and
   `PostgresFileSystem` from `vfs.backends`. There is no such package;
   the class is `vfs.storage.backends.DatabaseStorage`, constructed
   with `url=` or `session_factory=`.
4. **The banner understates what is built.** L19 says principals and
   row-level grants are "designed, not built". `Authority` and
   `Principal` are exported from `vfs`; `grant`, `revoke`, `posture`
   and `grants` are router verbs (`src/vfs/base.py` L904–971); spec 058
   is built (2026-09-29) and awaiting Clay's review.
5. **The Status section is stale.** L118 says "1,094 tests"; `pytest
   --co` collects 5,266. L119 says the vector leg and the cross-mount
   rerank are "the open specs"; both landed.
6. **Previous-generation pages under `docs/`.** `docs/` holds 67
   markdown files; 23 name `DatabaseFileSystem`, `PostgresFileSystem`,
   `MSSQLFileSystem`, `VFSClientAsync` or `vfs.backends`. Seven sit
   outside `docs/plans/`: `api.md`, `architecture.md`,
   `fs_architecture.md`, `index.md`, `internals/fs.md`,
   `internals/write_pipeline.md`, `deepagents-integration.md`. None is
   in the mkdocs nav, but `index.md` is what mkdocs serves at the site
   root. The other 42 are `docs/plans/*.md`, previous-generation
   planning notes. The pages that *are* in the nav (tutorials, how-to,
   reference, explanation) already run through Sybil in
   `docs/conftest.py`, and `scripts/ci.sh` runs `pytest docs`.
7. **Tools at paths.** The banner says tools at paths are "designed,
   not built" while `VirtualFileSystem.run` exists (L1511). True, but a
   reader cannot tell what `run` does today.
8. **Permissions per instance.** `src/vfs/permissions.py` L57–81
   documents that a permission map lives on the node, not the data,
   and two nodes on one schema do not see each other's maps. The
   docstring names `DatabaseFileSystem` three times (L61, L62, L81),
   and the README never mentions the limitation.
9. **Default posture.** A `DatabaseStorage` provisions `open`
   (ADR 068; `backend.py` L196); anonymous read, write and delete all
   succeed. The README does not say so.
10. **Cross-mount copy and move.** Refused `cross_mount` by design
    (`base.py` L2470, L2678); the README does not say so.
11. **Binary edit.** `edit` refuses a bytes body by design (152 §1;
    `writes.py` L947–948, kind `unsupported` today, which 154
    reclassifies); the README does not say so.
12. **"Mounts nest" (L42).** The sentence invites `add_mount(node)`,
    which is accepted today and then crashes `glob`. Spec 156 decides
    whether that becomes a refusal or an adapter; this spec softens
    the sentence to "mounts can be bound at any depth".
13. **Dead extras.** `pyproject.toml` declares optional extras with no
    importer anywhere under `src/vfs`: `deepagents`, `search`
    (usearch), `pinecone`, `databricks`, `langgraph`. The `all` extra
    pulls every one in. `langchain` (`embedding/langchain.py`) and
    `embed-local` (`embedding/model2vec.py`) are real and stay; the
    driver extras load through SQLAlchemy from the URL and stay.

## Scope

- **The first code block.** Rewrite it against the live API: one
  `VirtualFileSystem`, two `DatabaseStorage` mounts on sqlite (`url=`
  for one, `session_factory=` for the other, so the block executes
  with no server), `permissions="read"` on one `add_mount`. Name
  `InMemoryStorage` where L105's example today defines its own
  `MemoryStorage`.
- **The block runs under Sybil.** `README.md` joins the Sybil run
  (`docs/conftest.py` gains a root-level pattern, or a
  `tests/docs/test_readme.py` feeds Sybil the README). Every python
  fence in the README executes, not merely imports. The `tests/docs/`
  folder does not exist today; create it only if the conftest route
  is not taken.
- **Permission strings.** Replace `"read_only"` with `"read"` and name
  the three forms a permission map takes (`"read"`, `"read_write"`, a
  per-prefix map).
- **Versioning, three sentences.** "Mutate" in the verb table answers
  *changes; delete is reversible through trash and `restore`*. The
  L55 sentence and the L87 tree line leave until 161 lands, and
  161's landing note restores both.
- **Banner and Status.** Rewrite L19 against spec 058's status:
  principals and row-level grants are built and under review; tools at
  paths are not built. Rewrite the Status section against the
  collected test count and the landed specs (the vector leg, the
  rerank, 150, 152); keep "Released" as is (no release is planned).
- **The default root.** One sentence where the first code block
  builds the router: `VirtualFileSystem()` with no `storage` gets an
  `InMemoryStorage`, a `DatabaseStorage` on a private in-process SQLite
  database; writes outside every mount land there and live as long as
  the process. Pass `storage=` to put something durable at `/`.
- **Known limits.** A short section with five bullets, each linking
  by relative path into `context/`: permissions are enforced at the
  node and row-level grants are built but under review (spec 058, ADR
  073); a fresh storage is `open` and anonymous callers may write
  until the posture changes (ADR 068); copy and move do not cross a
  mount boundary (spec 160 removes this bullet on landing); `edit`
  does not touch a binary body, use `write` (spec 154 names the
  refusal kind); a `VirtualFileSystem` is not a storage and cannot be
  mounted (spec 156).
- **`run`.** One sentence under the banner: the verb exists and routes
  to a storage that declares `SupportsRun`; no shipped storage does.
- **`docs/`.** Delete the six previous-generation pages outside the
  nav (`api.md`, `architecture.md`, `fs_architecture.md`, `index.md`,
  `internals/fs.md`, `internals/write_pipeline.md`); mkdocs then
  serves `home.md` at the root (set `index` in `mkdocs.yml` if it
  needs telling). Replace `deepagents-integration.md` with a stub that
  says the v2 adapter is not written and points at the
  `BackendProtocol` study in the 2026-09-15 landscape memo, or delete
  it. The ranking fixture copy under
  `tests/fixtures/ranking/vfs_native/corpus/docs/` is cited by
  `qrels.txt` and stays.
  Resolved 2026-10-10 (Clay: "do that cleanup work"): the deepagents
  page and `docs/plans/` (31 previous-generation planning notes; the
  count above was 42 in error) are deleted outright; the memos and
  ADRs are the design record.
- **Extras.** Remove `deepagents`, `search`, `pinecone`, `databricks`
  and `langgraph` from `pyproject.toml` and from `all`; re-lock.
- **Docstring.** `permissions.py`: `DatabaseFileSystem` →
  `VirtualFileSystem` (three sites).
- Out of scope: the version verb (161), any release, the mount
  refusal (156), any code behaviour.

## Acceptance criteria

- Every python fence in `README.md` executes under Sybil in `pytest
  docs` (or `pytest tests/docs`), and every page in the mkdocs nav
  still passes.
- `grep -rn '"read_only"' README.md docs/` returns nothing.
- `grep -rnE "DatabaseFileSystem|PostgresFileSystem|MSSQLFileSystem|VFSClientAsync|vfs\.backends" README.md docs/ src/`
  returns nothing (`read_only` is a live kind and factory name across
  `src/` and is not part of the grep).
- The README has a **Known limits** section with the five bullets
  above, each linking into `context/`; the banner names what spec 058
  built; the Status section's test count matches `pytest --co`.
- `pyproject.toml` declares no extra without an importer under
  `src/vfs` or a driver loaded by SQLAlchemy; `uv.lock` is committed
  after the change.
- `scripts/ci.sh 3.13` green.

## Landing notes (2026-10-10)

Built in one pass over `0760fe9`. Where the landing differs from the
scope above, the reason:

- **The Sybil doc-test moved to a root `conftest.py`.** A
  `pytest_collect_file` hook in `docs/conftest.py` only sees files under
  `docs/`, so the "root-level pattern" route cannot reach `README.md`.
  The one conftest now collects the README and the four Diátaxis
  directories; `docs/conftest.py` is gone; CI and `scripts/ci.sh` run
  `pytest docs README.md` and lint `conftest.py`. Because the root
  conftest imports Sybil on every `pytest` start, `sybil` moved from
  the `docs` dependency group to `dev`.
- **Each page runs inside its scratch directory.** Setup `chdir`s into
  the page's temp dir and teardown restores it, so the README's
  relative `sqlite+aiosqlite:///enterprise.db` lands there, not in the
  repo. The README stays self-contained: no hidden fixture is used.
- **`docs/home.md` is now `docs/index.md`.** With `index.md` deleted
  mkdocs built no root page at all (`site/` had `home/` and a
  `404.html`, no `index.html`); mkdocs has no setting that names
  another file, so the home page took the conventional name and the
  nav entry follows it. The tutorial stub's "source to migrate from"
  comment now points at the README's first block.
- **`graph` gets the same sentence as `run`.** The search block's
  `graph` line executes and comes back `unsupported`: no shipped
  storage declares the graph family. The banner and the `graph` bullet
  say so, beside the `run` sentence the scope asked for.
- **Counts corrected.** `docs/` held 66 pages, `docs/plans/` 31 (the
  scope said 67 and 42). `pytest --co` collects 5,266, which the
  Status section now states.
- **A finding for a later spec, not fixed here.** A `DatabaseStorage`
  given a *borrowed* `session_factory` over a `sqlite+aiosqlite:///:memory:`
  engine serves `write` but fails `grep` with "cannot start a
  transaction within a transaction": the engine host serializes
  sessions on the single shared connection only when it owns the
  engine (the `url=` form). The README avoids the shape by borrowing a
  file-backed engine. Pointer in `open-questions.md`.
