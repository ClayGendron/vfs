# 178 — The ranged read: `read(range=)` in bytes, served by the engine's own slice, and a row that says which slice it carries

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same day) and the two memos it stands on. Not started. One open `[NEEDS CLARIFICATION]` (§7, slices and the integrity check).
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** feature (one new argument on `read` through the router, the session, the params table and the storage seam; one value type `ByteRange`; two query fields on `Observation`; one `DialectProfile` field and one SQL module for the per-dialect slice; one trait; a kernel-side fallback; one render marker; a conformance family on every engine leg).
- **Depends on:** ADR 087. Lands after spec 175 (integrity) in the ADR's order, because §7 decides how a slice meets the verify-on-read check. If it lands first, §7's lean is simply the state of the world until 175 arrives. Nothing else blocks it. Spec 179's access-path harness does not exist yet, so this spec builds the small counter it needs (§9) and 179 absorbs it.
- **Decisions it implements:** ADR 087 pin 3 (`read` takes `range=(offset, length)` served by the dialect's substring over the body column), pin 12 (a ranged-read row says which slice it carries), pin 2's fallback pattern (a backend that cannot serve the argument is still served it through the kernel), pin 14 (counted bytes moved), pin 15 (the axis table, §10).
- **Research it stands on:** `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md` (§2.7, §5 step 6); `../../../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md` (§1, §4.2 the `read` row, §4.5 bodies stay whole rows, §5 cheaper where the body is big, §7 step 4); `../../../research/2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md` (§1 whole-file staging, F7); studies under `../../../research/studies/2026-10-24-ostep-principles-for-vfs/`: `02-files-and-directories-the-api.md` principle 9 (a position belongs to the caller: `pread`, not `lseek`), `03-file-system-implementation-vsfs.md` principle 8 (the 4 MiB table: a read fetches the whole body; TOAST slices and SQLite overflow pages exist under the engine), `04-locality-and-log-structure-ffs-lfs-ssd.md` P10 (the bytes column is `EXTERNAL` on Postgres, so a substring is a ranged fetch), `06-distribution-nfs-afs.md` principle 10 (match the transfer unit to the workload).

## Intent

Today `read` returns the whole body, always. A 4 MiB file costs 4,194,300 bytes to look at its first line. After this spec a caller can say `read(path, range=(offset, length))` and get only that slice. The slice is cut by the database engine, so only the slice crosses the wire. The position stays with the caller, as `pread` does. There is no seek and no handle.

The unit is the byte, for both kinds of body. For a bytes body the slice is the raw bytes. For a text body the slice is cut from the UTF-8 bytes and then widened to whole characters, so it always decodes. The row says exactly which bytes it carries, and `size_bytes` still says how big the whole body is. With no `range`, nothing about `read` changes.

## Terms used below

- **Body.** The stored file content. A text row's body is `content` (a `str`, stored in `vfs_content`). A bytes row's body is `data` (raw `bytes`, stored in `vfs_blobs`); its `content` is a rendering.
- **Slice.** The part of one body a ranged read returns.
- **Window.** The bytes the engine sends back for one row. For a `data` slice the window is the slice. For a `content` slice it is the slice plus up to 3 bytes on each side, so vfs can widen the slice to whole characters.
- **Body bytes moved.** The bytes of body values the read builder receives from the engine for one call: ADR 087 pin 14's third counting unit.
- **Engine leg.** One real database the test suite runs against: SQLite, Postgres, SQL Server, MariaDB, Oracle.

## 1. The argument

- **One value type**, `ByteRange(NamedTuple)` with `offset: int` and `length: int`, in `src/vfs/ops.py` beside `TwoPathOperation` (the module the params table already imports). A plain 2-tuple is accepted too, because a `NamedTuple` is a tuple; the type exists so no code decodes `range[0]` as a hidden "offset".
- **The signatures.** `VirtualFileSystem.read` (`base.py:902`), `Session.read` (`session.py:82`), `SupportsRead.read` (`storage/protocol.py:118`) and `DatabaseStorage.read` (`database/backend.py:307`) gain `range: ByteRange | None = None`, keyword-only. `stat`, `ls` and `tree` do not.
- **The name is `range`, as ADR 087 pin 3 says.** It shadows the builtin, and ruff's `A002` refuses it (EXECUTED: `ruff check --select A` on a one-line probe reports `A002 Function argument range is shadowing a Python builtin`). The fix is one line in `pyproject.toml`: `[tool.ruff.lint.flake8-builtins] builtins-ignorelist = ["range"]`. No body that takes the argument calls the builtin. The alternative, `byte_range=`, was weighed and dropped: opendal and HTTP call it a range, the kernel memo and ADR 087 use the word, and the MCP tool shows the name to a model.
- **The params table** (`params.py`). A new `ParamKind`, `"range"`. `_check_value` accepts a `tuple` or `list` of exactly two `int`s (never `bool`), each `>= 0` and `<= INT_CEILING` (`params.py:59`, 2^31 − 1). The message names the parameter: `read range must be (offset, length), two integers >= 0 and <= 2147483647, got …`. `PARAMS["read"]` gains `ParamSpec("range", "range", doc="byte slice (offset, length) of the one body read")`.
- **Why the ceiling is not a designed cap.** `size_bytes` is an `Integer` column (`models/rows.py:440`), so no body larger than 2^31 − 1 bytes can be recorded today, and the engines cap one value below that anyway (Postgres 1 GB, SQLite's default 10^9 bytes, SQL Server 2 GB). The offset is exactly as wide as the size it indexes. If `size_bytes` ever widens to `BigInteger`, the range widens in the same change. The docstring says so.
- **One body per ranged read.** A new `ValueRule`, `OneBody(param= "range")`, in `VALUE_RULES["read"]`: when `range` is given, the projection must carry exactly one body field. `columns=None` is the default projection, which carries `content`, so it passes. `columns` with both `content` and `data` is `invalid` ("a ranged read slices one body; project content or data"). `columns` with neither is `invalid` ("range slices a body; project content or data"). The rule lives in the table, so spec 171's schema and the drift test see it.
- **One range per call.** The same `range` applies to every target, the single `path` or every row of `observations=`. §5 says why per-path ranges wait.

## 2. The unit: bytes, for both bodies

### 2.1 Why bytes and not characters

A character count would suit a model reading text. But SQL engines do not agree on what a character is, and three consumers need bytes:

| Engine | What `SUBSTR`/`SUBSTRING` counts on vfs's text column | Evidence |
|---|---|---|
| SQLite (`TEXT`) | code points | EXECUTED: `substr(content, 2, 3)` of `"aé€😀\n…"` is `'é€😀'` |
| Postgres (`text`, UTF8 server) | code points | READ: `text_substring`, `src/backend/utils/adt/varlena.c:586–718` (postgres `b128e75e`, 2026-10-14) |
| MariaDB (`LONGTEXT`, utf8mb4) | code points | INFERRED from the MariaDB manual |
| SQL Server (`VARCHAR(MAX)`, UTF-8 collation) | code points for UTF-8 `varchar`, not yet run here | INFERRED; the leg would pin it |
| Oracle (`CLOB`, AL32UTF8 database) | UTF-16 code units: a CLOB in a multibyte database is stored as AL16UTF16, so 😀 counts as 2 | INFERRED from Oracle's LOB documentation |

So "characters" would give a different slice on Oracle for any body with an emoji. That is a silent wrong answer. Bytes mean the same thing on every engine.

And the consumers that need a range are byte-shaped:

- `size_bytes` and `content_hash` are measured on the UTF-8 bytes (`measure_text`, `models/version.py:66`). A caller pages a body against `size_bytes`, so the offset must be in the same unit.
- `pread`, WASI `fd_read`, HTTP `Range` and opendal's `read(range)` all count bytes (kernel memo §1).
- `head -c`, `tail -c` and a Parquet footer are byte positions.

### 2.2 Bytes of a text body

`range` on `content` addresses the UTF-8 bytes of the text, the same bytes `size_bytes` counts. On a bytes row, `content` is the rendering, and `range` addresses the rendering's UTF-8 bytes.

### 2.3 A byte offset inside a multibyte character: snap outward

A UTF-8 character is 1 to 4 bytes. A byte offset can land in the middle of one. The rule:

- **The served slice is the smallest run of whole characters that covers the requested bytes.** The start moves back to the first byte of its character. The end moves forward to the end of its character. Each moves at most 3 bytes.
- The row reports the bytes it actually serves (`range_start`, `range_length`, §3). The text always decodes.
- A non-empty range that starts inside the body always serves at least one character. So an empty slice means only one thing: the offset is at or past the end (POSIX `pread` behaves the same way).
- `length == 0` serves an empty slice at `offset`, with no widening.
- **Paging is lossless when the caller continues from the served end** (`range_start + range_length`). The served end is always a character boundary, so the next slice starts clean.
- **A byte-exact consumer cuts locally.** The served slice always covers the requested bytes. A consumer that needs exactly `[offset, offset + length)` (a WASI `fd_read`, `head -c`) encodes the served text and cuts `[offset − range_start, offset − range_start + length)`. No second call is needed.

Why outward and not inward. Shrinking inward never over-delivers, but a request of 1 to 3 bytes inside one character would answer empty in the middle of a file. A pager that stops on an empty answer would stop early. And a byte-exact consumer could not cut locally; it would have to widen its own request first. Refusing (`invalid`) was rejected too: the caller cannot know where the boundaries are.

EXECUTED (authoring probe, `uv run` against `InMemoryStorage`, a prototype of the rule; it becomes the oracle test in task 3): on a 77-byte body of 1-, 2-, 3- and 4-byte characters, every `(offset, length)` with both from 0 to 80, 6,561 cases: the served text always decoded, always covered the request, never moved more than 3 bytes on either side, and never came back empty for a non-empty request inside the body. Paging from the served end rebuilt the body exactly for page sizes 1 to 8.

Text that is not valid UTF-8 can reach a row only by an out-of-band writer (ADR 087 pin 8). A window that does not decode is classified the way spec 175 classifies a body that fails its hash. It is never served with replacement characters.

### 2.4 Bytes of a bytes body

`range` on `data` (projected with `columns={"data", …}`) addresses the raw bytes. No widening, no decoding. The window is the slice.

## 3. The row

`Observation` (`models/entry.py:404`) gains two query-relative fields, facts about *(entry, operation)* like `score` and `depth`:

| Field | Type | Meaning |
|---|---|---|
| `range_start` | `int \| None` | the byte offset of the first served byte in the sliced body |
| `range_length` | `int \| None` | the number of bytes served |

- Both join `OBSERVATION_QUERY_FIELDS` (`entry.py:515`). They are never persisted and need no mirror.
- **They are populated exactly when a ranged read served a body value.** The `populated` mask then holds the body field (`content` or `data`) plus both range fields. A consumer narrows by the mask, never by a null check, as the `Observation` docstring already requires.
- **`size_bytes` and `content_hash` stay the whole body's.** They describe the entry, not the call. A caller learns the total from `size_bytes` and can check a fully paged body against `content_hash` end to end, without trusting vfs.
- **The end of the body.** A served slice that ends before the requested end (`range_start + range_length < offset + length`) has reached the end of the body. Outward snapping only ever moves the end later, so a short slice means the end and nothing else. This holds for a rendering too, whose length is not stored.
- **A range past the end** answers an empty slice: `content == ""` or `data == b""`, `range_start == offset`, `range_length == 0`, `success` true, no error. This is `pread` at end of file.
- **What does not change.** A directory target is `wrong_kind`. A missing target classifies through the descent ladder. A row the caller may list but not read is `permission_denied`. A bytes row whose rendering is pending answers `content=None` with the existing render note (`render_notes`, `reads.py`), and carries no range fields because no body was served. A text row read with `columns={"data"}` answers `data=None`, fetched-and-null, as today, with no range fields. A trash-view target slices its tombstoned row's body exactly as a whole read serves it.

## 4. The engine's slice, per dialect

### 4.1 SQLAlchemy takes no position, so the profile declares the spelling

EXECUTED (compiling the candidates against the five dialects with SQLAlchemy 2.0.52, no engine): SQLAlchemy has no portable substring. `func.substr` renders `substr(...)` on every dialect, and SQL Server has no `SUBSTR`. `func.substring` renders `SUBSTRING(x FROM s FOR n)` on Postgres and `substring(x, s, n)` elsewhere, and Oracle has no `SUBSTRING`. Casting text to bytes is worse: `cast(content, LargeBinary)` renders `CAST(... AS BYTEA)` on Postgres (an I/O cast that reads backslashes as escapes), `CAST(... AS IMAGE)` on SQL Server and `CAST(... AS BLOB)` on Oracle, where a CLOB will not cast. The only generic function SQLAlchemy offers in this area is `char_length`.

So this is exactly the kind of decision CLAUDE.md allows a profile field for. The shape copies `range_source` in `dialects.py` and its `@compiles` constructs in `ranges.py`:

- `DialectProfile` gains `body_slice: BodySlice | None = None`, with `BodySlice = Literal["substr", "substring_from", "substring_cast", "substring_binary", "lob_function"]`. Each tuned profile names its spelling. `GENERIC` declares `None`.
- A new module `src/vfs/storage/backends/database/slices.py` holds one `FunctionElement` per spelling with its `@compiles`, and one public builder: `body_window(column, *, text: bool, window: Window, form: BodySlice) -> ColumnElement[bytes]`. `Window` is a `NamedTuple` of `sql_start` (1-based), `count` and `prefix_end` (§4.3).
- The `content_bytes` field (`dialects.py:358`) is not reused. It promises a *cheap reinterpreting* cast for grep's whole-body fetch and is declared only on SQLite. A ranged read needs a *correct* UTF-8 byte view on every engine, and may transcode to get it.

### 4.2 The spellings

`:s` is the 1-based window start, `:n` the window length, `:e` the prefix bound (§4.3). Every bind is a constant per statement.

| Engine | `data` (bytes body) | `content` (text body, as UTF-8 bytes) | What the engine reads inside | Evidence |
|---|---|---|---|---|
| SQLite | `substr(data, :s, :n)` | `substr(CAST(content AS BLOB), :s, :n)` | the whole value, in process: `substr` loads the full payload (`sqlite3_value_blob`, `src/func.c` `substrFunc`; only `length()`/`octet_length()`/`typeof()` skip the load, `src/vdbe.c:3279`; sqlite `3d17c3f9e`) | EXECUTED: both return the exact bytes; a 64 KiB `data` slice returned 65,536 bytes; past the end returned length 0 |
| Postgres | `substring(data from :s for :n)` | `substring(convert_to(substring(content from 1 for :e), 'UTF8') from :s for :n)` | `data`: only the TOAST chunks the slice covers, because the column is `EXTERNAL` (`rows.py:887`; `bytea_substring` → `DatumGetByteaPSlice`, `src/backend/utils/adt/bytea.c:98–154`; `detoast_attr_slice`, `src/backend/access/common/detoast.c:206`). `content`: a prefix of at most 4 × `:e` bytes, decompressed only that far (`text_substring` fetches a prefix slice for a multibyte encoding, `varlena.c:643–718`; `detoast.c:244`), then `convert_to` reads that prefix whole (`pg_convert`, `src/backend/utils/mb/mbutils.c:564`) | READ |
| SQL Server | `SUBSTRING(data, :s, :n)` | `SUBSTRING(CAST(content AS VARBINARY(MAX)), :s, :n)` | not yet measured; the cast likely materialises the whole value | INFERRED; the column's UTF-8 collation (`rows.py:252`) makes the cast a byte copy of UTF-8 |
| MariaDB | `SUBSTRING(data, :s, :n)` | `SUBSTRING(CAST(content AS BINARY), :s, :n)` | the whole value, likely | INFERRED; the column is utf8mb4 on the leg's server (the leg URL pins `charset=utf8mb4`, `.claude/skills/db_test/SKILL.md:94`) |
| Oracle | `vfs_blob_slice(data, :s, :n)` | `vfs_text_slice(content, :s, :n, :e)` | `data`: only the LOB pages the slice covers (`DBMS_LOB.COPY` with a source offset). `content`: the first `:e` UTF-16 units, converted to UTF-8 (`DBMS_LOB.CONVERTTOBLOB` with an amount) | INFERRED; task 1 proves it on the leg |
| generic floor | none: the kernel slices (§6) | none | the whole value, sent whole | by design, declared by the trait |

### 4.3 The window, computed once in Python

- `data`: `sql_start = offset + 1`, `count = length`.
- `content`: `window_start = max(0, offset − 3)`, `window_end = min(offset + length + 3, INT_CEILING)`, `sql_start = window_start + 1`, `count = window_end − window_start`.
- `prefix_end` bounds how much of the text the engine must touch on Postgres and Oracle. The bytes before `window_end` lie inside the first `window_end` characters, because a character is at least one byte. On Oracle it is `window_end + 1` UTF-16 units: a unit is at least one UTF-8 byte too, and the extra unit keeps a surrogate pair from being split at the cut.
- The snap of §2.3 then runs on the window in Python (`vfs.storage.slicing.snap_text`). It scans at most 6 bytes and calls `bytes.decode`, which is C. This is small, stdlib work, so it stays Python under CLAUDE.md's rule; the Rust engine is not involved.

### 4.4 Oracle: one inline function per statement, not 2,000-byte pieces

Oracle has no SQL function that returns a byte slice of a CLOB. And `DBMS_LOB.SUBSTR`, called from SQL, returns at most 2,000 bytes of RAW or 4,000 bytes of `VARCHAR2` (32,767 under `MAX_STRING_SIZE = EXTENDED`, which vfs cannot assume). A 4 MiB slice would be 2,098 pieces. Pieces could ride as rows from a `CONNECT BY` generator, but that still leaves the CLOB unsolved, because `DBMS_LOB.SUBSTR` on a CLOB counts UTF-16 units.

So the Oracle statement declares two PL/SQL functions inline, in the query's own `WITH` clause (Oracle 12c and later; vfs targets 23ai for its vector leg). Inline functions need no `CREATE PROCEDURE` privilege and leave no schema object behind, so an existing mount needs no migration. The shape, which task 1 proves and may adjust:

```sql
WITH
  FUNCTION vfs_blob_slice(b BLOB, s NUMBER, n NUMBER) RETURN BLOB IS
    r BLOB;
    have NUMBER := DBMS_LOB.GETLENGTH(b);
  BEGIN
    DBMS_LOB.CREATETEMPORARY(r, TRUE, DBMS_LOB.CALL);
    IF n > 0 AND s <= have THEN
      DBMS_LOB.COPY(r, b, LEAST(n, have - s + 1), 1, s);
    END IF;
    RETURN r;
  END;
  FUNCTION vfs_text_slice(c CLOB, s NUMBER, n NUMBER, e NUMBER) RETURN BLOB IS
    whole BLOB;
    dst INTEGER := 1; src INTEGER := 1;
    ctx INTEGER := DBMS_LOB.DEFAULT_LANG_CTX; warn INTEGER;
  BEGIN
    DBMS_LOB.CREATETEMPORARY(whole, TRUE, DBMS_LOB.CALL);
    DBMS_LOB.CONVERTTOBLOB(whole, c, LEAST(e, DBMS_LOB.GETLENGTH(c)),
                           dst, src, NLS_CHARSET_ID('AL32UTF8'), ctx, warn);
    RETURN vfs_blob_slice(whole, s, n);
  END;
SELECT ... vfs_text_slice(vfs_content.content, :s, :n, :e) AS content ...
```

- The `WITH FUNCTION` text must lead the statement, so it cannot be a column-level construct. `slices.py` adds one `Select` wrapper with an Oracle `@compiles` that prepends the declarations the statement uses. Every other dialect compiles the wrapper as the plain select.
- python-oracledb returns the BLOB as `bytes`, as it returns every body today.
- **No per-call cap applies.** `DBMS_LOB.COPY` and `CONVERTTOBLOB` take any amount, so a slice larger than 2,000 or 32,767 bytes is one call and one statement. Criterion 6 pins it with a 100,000-byte slice.
- **If the leg refuses inline PL/SQL** (a driver or server setting task 1 finds), the fallback is the same two functions created as schema objects by an `after_create` DDL listener on `vfs_blobs`, the pattern `_attach_blob_storage_ddl` already uses for Postgres (`rows.py:887`). That needs `CREATE PROCEDURE` and a first-touch check for mounts that predate it. Task 1 records which one landed.

## 5. The statement, and batches of 10,000

- **A ranged read is the same one statement as a whole read.** `read_rows` (`reads.py:149`) passes the window to `_point_rows`, and `_entry_projection` (`reads.py:900`) puts `body_window(...)` labelled `content` or `data` in the select list where the bare body column stands today. The rest is untouched: the targets and their ancestors in one membership (`rows_by_path`, `descent.py:155`), the outer join to the body table, the screen, the descent ladder. An ancestor or directory row has no body, so its window is `NULL`.
- **Counts as the system actor.** EXECUTED (authoring probe, SQLite): a whole `read` of a 4 MiB text body is 1 statement and moves 4,194,300 body bytes; of a 4 MiB bytes body with `columns={"data"}`, 1 statement and 4,194,304 bytes. A ranged read stays at 1 statement. The same probe ran the SQLite spellings directly: a 64 KiB slice at offset 1,000,003 moved 65,542 bytes for `content` (the slice plus the 6 window bytes; the snap served 65,538 bytes starting at 1,000,002) and 65,536 bytes for `data`, both exact against the body.
- **Bounded at any batch size.** The membership already chunks by `membership_budget(profile, parameter_budget)` through `chunked()` (`dialects.py:651`, `:683`). A ranged read adds 2 binds (`data`) or 3 binds (`content`) per statement, all constants, inside the 32-bind `_FILTER_BIND_RESERVE` (`dialects.py:644`). So a 10,000-path ranged read issues exactly as many statements as a 10,000-path whole read. For 10,000 files in one directory that is 10,002 keys (the files, the directory, the root), so 11 statements at Oracle's 1,000-element floor (`membership_budget` = min(1,000, 32,700 − 32); SQL Server's is min(2,000, 2,099 − 32) = 2,000, so 6). The count does not change with the range. Body bytes moved are at most `N × (length + 6)`.
- **One range per call.** A per-path range has one strong use, a batch of Parquet footers at different offsets, and it needs a shape this spec does not want to guess (a `ranges=` mapping, or ranged input rows, which would make callers construct `Observation`s). Until then the footer job is two calls: a `stat` batch, then one ranged `read` per distinct offset. Named as a follow-up, not built.
- **A suffix range** (`tail -c N` without a `stat`, HTTP's `bytes=-N`) is also a follow-up. It needs the body length inside the statement, which `size_bytes` gives for a source body but not for a rendering. `tail -c` is a `stat` then a ranged `read` until then.

## 6. The kernel serves `range=` to a backend that cannot

ADR 087 pin 2: a backend that declares no index is still served `grep` through the kernel, by a scan over `read`. The ranged read follows the same rule.

- **A new trait**, `read_range`, with the one value `"engine"` (`TraitKey` and `TRAIT_VALUES`, `protocol.py:73–78`). It means: this backend cuts the slice before the body leaves storage. `DatabaseStorage.traits()` (`backend.py:288`) declares it when `profile.body_slice is not None`, so on the five tuned profiles and never on the generic floor.
- **The router keeps a trait snapshot.** `MountMeta` (`base.py:141`) gains `declared_traits`, taken from `storage.traits()` at bind time, exactly as `declared_caps` is taken from `capabilities()`.
- **The fallback.** When `range` is given and the binding does not declare `read_range`, the router calls the backend's `read` without `range` and slices each served body itself with `vfs.storage.slicing.slice_rows(result, range)`: encode, take the window, snap. The row is the same row the engine path returns. A backend that does not declare the trait is never passed `range`, so a minimal third-party backend need not implement it.
- **Honest cost.** The fallback moves the whole body. The trait says so, the docstring says so, and the conformance family pins both paths to identical rows. It is the generic floor's answer, never a designed limit.
- `DatabaseStorage.read(range=...)` called directly on the generic floor (no router) uses the same `slice_rows`, so the backend never answers differently from the router.

## 7. A slice and the integrity check

Spec 175 makes `read` compare the served body's sha256 with `content_hash` and classify a mismatch, or a missing body behind a hashed entry, as an error (ADR 087 pin 9, Clay: verify on every read). A slice cannot be compared with a hash of the whole body.

- **The missing-body half still holds.** A ranged read of a row whose body row is gone (the outer join answers `NULL` behind a hashed entry) is classified exactly as spec 175 classifies a whole read. That check needs no hash.
- **A slice that covers the whole body is verified.** When the window holds the whole body (`offset == 0` and the window ended before `count`), vfs has every byte and runs spec 175's check as for a whole read. `read(range=(0, size_bytes))` is a whole read.
- **A slice served by the kernel fallback is verified,** because the backend's whole read verified the body before the router cut it.
- **Lean: any other slice is served unverified.** Its row carries the range fields, and a sliced row is by definition not compared. The read tool's docstring says so. A client that pages the whole body can check `content_hash` itself (§3).
- `[NEEDS CLARIFICATION: serve a partial slice unverified (lean), or verify the whole body inside the engine on every ranged read — Postgres `sha256()`, SQL Server `HASHBYTES('SHA2_256', …)`, MariaDB `SHA2(…, 256)`, Oracle `DBMS_CRYPTO.HASH` inside the inline function, SQLite a registered function — and ship only a boolean beside the slice? The second keeps "verify on every read" literally true and still moves only the slice over the wire, but it reads the whole body inside the engine on every call, which gives back most of the engine-side saving for `data` on Postgres and Oracle, and it is five per-dialect spellings with their own caps to prove.]`

## 8. The verb-tool rendering says it is a slice

`_render_read` (`results/render.py:310`) prints `content` verbatim. For a sliced row it adds one trailing line, so a model reading the `read` tool sees where it is and how to go on:

```
[slice: bytes 1000002–1065540 of 4194300; next range=(1065540, 65536)]
```

- The numbers are `range_start`, `range_start + range_length`, `size_bytes` (omitted with its `of` when not projected) and the next request at the served end with the caller's own length. A slice that reached the end prints `[slice: bytes A–B of N; end]`.
- A whole read renders byte for byte as today.
- This is the verb-tool rendering only. The shell's `cat` and `head` write the body raw into the pipe (spec 167 decision 3) and never see the marker.

## 9. Counting body bytes moved

Spec 179's access-path harness does not exist yet. This spec adds the smallest counter that pins its criteria, in `tests/support/access.py`, and 179 absorbs it.

- Every body value the read builder receives passes through one function, `vfs.storage.slicing.served_window`, on the engine path and the fallback alike. The counter spies on it and sums `len()` of each window: the body bytes moved for the call.
- Statements are counted with the `before_cursor_execute` listener the read tests already use (`tests/storage/database/test_reads.py:301`).
- On SQLite the counter is cross-checked against a cursor-level count of returned bytes (the method of `research/studies/2026-10-24-ostep-principles-for-vfs/experiments/s03/access_paths.py`), so a regression that fetched the whole body in a second statement and threw it away would still show.

## 10. The axis table (ADR 087 pin 15)

| Axis | Whole read today | Ranged read |
|---|---|---|
| Agent latency | 1 statement as the system actor | 1 statement; same rights statements under a principal |
| ETL throughput | N bodies whole | N slices, same statement count |
| Boundedness | membership-chunked | same chunks, 2–3 constant binds more |
| Correctness under rivals | one snapshot | one snapshot; two slices from two calls may come from two versions, and the row's `version` says which |
| Atomic unit | n/a (a read) | n/a |
| Dialect reach | every dialect | engine-cut on the five, kernel-cut on the floor |
| Protection | rights judged per row | identical: same gate, same screen, same `permission_denied` |
| Overhead above the engine | whole body over the wire | slice + ≤ 6 bytes over the wire; whole body inside the engine on SQLite, SQL Server and MariaDB, a prefix on Postgres and Oracle text, only the covered pages for Postgres and Oracle `data` |

The rivals row matters for paging: a caller who pages a body across several calls can see two versions if someone writes in between. The row's `version` tells it. Paging with a version check is the WASI follow-up's job (§11), using spec 174's `if_version` thinking on the read side.

## 11. The fronts (named follow-ups, not this spec)

- **WASI (spec 172, spec 169 §b4–b5).** wasi-python 0.1.0's mount protocol stages every file whole at open: `FileProvider.read(path)` returns the whole file (wasi_python `docs/reference/python-api.md`, `docs/how-to/mounts.md:29, 89`: "a 1-byte read stages the file"; `2cd47507`, 2026-10-23). A ranged `fd_read` therefore needs a ranged provider call in wasi_python first, which is that project's decision (it is embedder-neutral). The provider would then serve `fd_read` and `fd_pread` with `read(range=)` and cut locally (§2.3) for large bodies, and keep whole staging for small ones and for any file opened for write. Named, not built.
- **The shell (spec 167 §4).** `head -c N P` is `read(P, range=(0, N))` with a local cut. `head -n N P` reads doubling windows from 0 (64 KiB first) until N newlines or the end. `tail -c N P` is `stat` then `read(range=(size − N, N))`. `tail -n N P` reads doubling windows back from the end. Each stops on the end rule of §3. A pipe operand (`cat f | head`) is unchanged.
- **MCP (spec 171).** The `read` tool's input gains `range`. The marker of §8 tells the model how to continue past spec 167's 32,768-character display cap.

## Scope

In: §1–§9. The argument on the router, the session, the protocol, the backend and the params table; `ByteRange`; the two row fields; the `body_slice` profile field and `slices.py` with the five spellings; the snap; the `read_range` trait, the `MountMeta` snapshot and the kernel fallback; the integrity interplay at its lean; the render marker; the body-bytes counter; the conformance family on every engine leg; the `pyproject.toml` ignorelist line.

Out: per-path ranges and suffix ranges (§5); ranged writes and chunked bodies (kernel memo §4.5: only if a front demands ranged writes); a ranged read of a version row (spec 180's history read); the WASI, shell and MCP uses (§11, each its own spec's task); an in-engine hash of the whole body (§7's alternative); a `stat` that returns a rendering's length.

## Acceptance criteria

Counts and states, never clocks. "Every engine leg" means SQLite in the default run and Postgres, SQL Server, MariaDB and Oracle when their `VFS_TEST_<ENGINE>_URL` is set.

1. **`range` absent leaves every read pin unchanged.** No existing assertion in `tests/` about `read` is edited. The conformance battery's read family passes unchanged on every engine leg. A whole read's `populated` mask holds neither range field (checked over every row of the battery's read cases).
2. **A 4 MiB body moves the slice, never the body, on every engine leg.** A 4 MiB text body built from 1-, 2-, 3- and 4-byte characters and a 4 MiB bytes body; one ranged read each of 65,536 bytes at offset 1,000,003, as the system actor. Statements: exactly as many as a whole read of the same path (1 on SQLite). Body bytes moved (§9): at most 65,542 for `content` and exactly 65,536 for `data`, against 4,194,300 and 4,194,304 for the whole reads. The same pair as a named principal holding `read`: the statement count equals the whole read's under that principal.
3. **A slice inside a multibyte character answers by the outward rule.** On SQLite, every `(offset, length)` with both from 0 to 80 over a 77-byte mixed body (6,561 cases): the served text decodes, equals the body's bytes at `[range_start, range_start + range_length)`, covers the request, moves each edge at most 3 bytes, and is non-empty for every non-empty request that starts inside the body. On every other engine leg, a fixed set of 64 of those cases (every edge class: lead byte, each continuation byte, the last byte, past the end) gives the same rows as SQLite.
4. **Paging rebuilds the body.** Paging a 4 MiB mixed body from offset 0 with length 65,536, each call starting at the previous served end, ends on a short slice after at most `ceil(4,194,300 / 65,536) + 1` = 65 calls, and the concatenation's sha256 equals the row's `content_hash`, on every engine leg.
5. **A range past the end is empty, not an error.** `offset == size_bytes`, `offset > size_bytes` and `length == 0` each answer `success`, one row, an empty body, `range_length == 0` and `range_start == offset`, with zero errors.
6. **Oracle serves slices over its per-call caps.** On the Oracle leg: a 100,000-byte slice (over the 2,000-byte SQL RAW cap and the 32,767-byte PL/SQL cap) of a 4 MiB BLOB at offset 1,000,003, and of a 4 MiB CLOB with characters outside the BMP, each answers the exact bytes the other legs answer, in one statement. Task 1 records whether the inline or the schema-function form landed.
7. **The gate.** `read` with `range` set to `(-1, 1)`, `(0, -1)`, `(True, 1)`, `(0, 2**31)`, `(1,)`, `"0,1"`, or with `columns` holding both or neither body field, is `invalid` naming `range`, with zero statements issued (counted). A directory target is `wrong_kind` and a list-only row is `permission_denied`, exactly as without `range`.
8. **Bounded at 10,000.** A ranged read of 10,000 paths under one directory issues the same statement count as a whole read of the same 10,000 paths, on SQLite and on a profile pinned to Oracle's 1,000-element floor; no statement holds more than `membership_budget` keys plus 3 range binds (counted from the recorded parameters). Body bytes moved are at most 10,000 × (length
   + 6).
9. **Bytes rows.** A PNG row read with `range` and default columns slices its rendering (or answers the pending note with no range fields when unrendered). With `columns={"data", …}` it slices the raw bytes, exactly, with no widening.
10. **The kernel fallback.** A test-double backend that declares no `read_range` trait, and `DatabaseStorage` on a profile with `body_slice=None`, each answer rows identical to the engine path on the criteria 3 and 5 corpus (compared field by field), while the counter shows the whole body moved. The double's `read` never receives a `range` keyword (spied: zero calls with it).
11. **Integrity, at the lean.** A whole-body slice (`(0, size_bytes)`) of a body changed underneath vfs is classified as spec 175 classifies a whole read. A ranged read of a row whose body row was deleted underneath vfs is classified as spec 175 classifies the missing body. A partial slice of a changed body is served, with its range fields. (Rewritten if Clay answers §7 the other way.)
12. **Traits and drift.** `read_range` is in `TRAIT_VALUES`; the traits drift test passes; `DatabaseStorage` declares it on the five tuned profiles and not on the generic floor. `range_start` and `range_length` are in `OBSERVATION_QUERY_FIELDS`; the mirror drift test passes. `PARAMS["read"]` holds `range`, and spec 171's projection drift test (when it exists) names it projected.
13. **The marker.** The verb-tool render of a sliced row ends with exactly one marker line of §8's grammar; a whole read's render is byte-for-byte unchanged against the current fixtures.
14. **Green.** `scripts/ci.sh` is green at 100% coverage after every task. The four real-engine legs are green before task 4 lands.

## ADR amendments this spec needs

- **ADR 087 pin 3:** "`read` takes `range=(offset, length)` served by the dialect's substring over the body column" gains: in bytes, for both bodies (the raw bytes of `data`, the UTF-8 bytes of `content`); a text slice snaps outward to whole characters and reports what it served; one range per call; Oracle's slice is an inline PL/SQL function, not `DBMS_LOB.SUBSTR` pieces; a backend that does not declare the `read_range` trait is served the range by the kernel over a whole `read`.
- **ADR 087 pin 12:** "a ranged-read row says which slice it carries" becomes: `range_start` and `range_length`, query-relative fields, populated exactly when a slice was served; `size_bytes` and `content_hash` stay the whole body's; a short slice means the end.
- **ADR 087 pin 9:** gains §7's answer once Clay gives it. At the lean: a partial slice is served unverified; a whole-body slice and a kernel-cut slice are verified; the missing-body check applies to every ranged read.
- **ADR 010** (the envelope): already amended by ADR 087 for this; the two field names above are what it records.

## Rebase notes for specs 167, 171 and 172

- **167 §4 (read-shaped text forms):** with a file operand, `head -c`, `head -n`, `tail -c` and `tail -n` read through `read(range=)` as §11 describes, instead of reading the whole body. With a pipe operand they are unchanged. 167's §4.1 table gains these four rows. 167 slice A owns `render.py`; §8's marker lands in this spec and 167 should not undo it.
- **171 §1.1:** the `range` `ParamKind` projects to a JSON object `{"offset": integer, "length": integer}`, both `minimum: 0`, `maximum: 2147483647`, and `call_args` turns it into a `ByteRange`. An object, not a two-item array, so a model sees the names. §4's `RESOURCE_READ_BYTE_BUDGET` refusal can name the `read` tool's `range` as the way to read a large row; ranged *resource* reads stay out, as 171 says.
- **172 (and 169 §b4–b5):** whole-file staging stays at v1. A ranged `fd_read` waits on a ranged provider call in wasi_python's mount protocol, which is that project's decision; when it exists, the provider serves reads of large read-only opens with `read(range=)` and cuts locally (§2.3). The staged-buffer cache's key is unaffected.

## Landing notes

(Filled in on landing.)
