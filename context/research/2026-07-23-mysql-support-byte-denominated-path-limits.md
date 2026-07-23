# MySQL support and byte-denominated path limits

**Date:** 2026-07-23
**Trigger:** the first real-engine conformance run (`docker/compose.test.yml`)
failed MySQL at `create_all` with error 1071 — the `path` unique index
(VARCHAR(1024), utf8mb4) needs 4,096 bytes against InnoDB's 3,072-byte
cap. `DialectProfile.key_byte_budget` binds writes (`staging.py`,
`within_budget` measures UTF-8 bytes) but no DDL ever consumed it.
**Question:** how should the schema fit every engine's index-key byte cap
— and should path limits themselves become byte-denominated (1024 total,
255 per segment), matching macOS/Windows constraints?

All citations verified first-hand in the read-only reference checkouts
under `~/Git/Repos/`.

## 1. The OS canon measures paths in bytes

- **BSD/macOS:** `PATH_MAX 1024 /* max bytes in pathname */`,
  `NAME_MAX 255 /* max bytes in a file name */` —
  `freebsd-src/sys/sys/syslimits.h:53,60`; macOS inherits these values.
  Enforced as byte counts: `vfs_lookup.c:1194-1197` trips
  `ENAMETOOLONG` on a byte-pointer difference.
- **Linux:** `PATH_MAX 4096`, `NAME_MAX 255`
  (`linux/include/uapi/linux/limits.h:12-13`); the kernel treats
  pathnames as opaque byte strings — `fs/namei.c:255-259` checks
  `strlen(filename) + 1 > PATH_MAX`.
- **pjdfstest** constructs `ENAMETOOLONG` probes by byte length
  (`tests/misc.sh:118-159` — `wc -c`, `cut -b`), reading the live
  limits from `pathconf`.
- **Windows/HFS+ count UTF-16 units instead** (MAX_PATH 260 units;
  NTFS/HFS+ 255-unit components; APFS is 255 UTF-8 *bytes*). A
  255-UTF-8-byte component limit is the conservative floor across all
  of them, but it does reject some names Windows/HFS+ accept (a
  255-character CJK name is ~765 UTF-8 bytes). Background knowledge,
  not repo-cited.

vfs today enforces 1024/255 in *characters* (`paths.py:508,515` —
`len()` on `str`), the one denomination no filesystem uses.

## 2. How storage layers that already run on MySQL survive the cap

- **juicefs** declares every key column byte-typed: `edge.Name` is
  `varbinary(255)` inside `unique(edge)` (`pkg/meta/sql.go:67-68`),
  symlink targets `varbinary(4096)` unindexed (`:188`). Its limits are
  byte counts (`MaxName = 255`, `pkg/meta/interface.go:114-115`)
  enforced as `ENAMETOOLONG` byte checks (`pkg/vfs/vfs.go:195-196` et
  al.). Consequence: **no code or comment anywhere acknowledges the
  767/3072 cap** — byte-typed keys under byte-bounded limits never
  approach it. It sets no charset/ROW_FORMAT DDL at all.
- **jackrabbit-oak RDB** uses one 512-wide ID key across DB2, Oracle,
  Postgres, MySQL, MSSQL — `varchar(512)` on the char-based engines,
  switched to **`varbinary(512)`** on MySQL (`RDBDocumentStoreDB.java:409`,
  rationale OAK-1913 at `:407`: databases that "can not handle 512
  character primary keys") and MSSQL (`:505`). IDs longer than the
  budget are hashed at ID-generation time (`Utils.java:352-378`) —
  bounding the logical key below the smallest engine budget instead of
  encoding per-engine caps.

Both systems converge on the same doctrine: **byte-typed key columns,
byte-bounded logical keys, no per-engine cap arithmetic anywhere.**

## 3. SQLAlchemy facts that bind the design

- **No position on index-key byte caps** — confirmed. The base
  `Dialect` models identifier-name lengths only
  (`engine/interfaces.py:804`); the mysql dialect adds name-length
  limits (`dialects/mysql/base.py:2731-2733`) and nothing about
  767/3072. Owning this in `DialectProfile` is legitimate under the
  house rule (a decision SQLAlchemy takes no position on).
- **MariaDB is a separate variant key.** `MariaDBDialect` has
  `name = "mariadb"` (`dialects/mysql/mariadb.py:34-45`), and variant
  resolution keys strictly off `dialect.name`
  (`sql/type_api.py:1047-1053`). Every mysql variant must be declared
  `with_variant(x, "mysql", "mariadb")` — the docstring's own example
  does exactly that (`type_api.py:721-723`).
- **VARBINARY(n) renders with a length** (`visit_VARBINARY`,
  `dialects/mysql/base.py:2633-2634`). No in-tree TypeDecorator stores
  unicode in VARBINARY; writing one (encode UTF-8 on bind, decode on
  result) is new but idiomatic code — `ULIDKey` in `models/rows.py` is
  the local precedent.
- **Deadlock 1213 / lock-wait 1205 are classified nowhere.**
  `is_disconnect` lists only connection-death codes
  (`dialects/mysql/base.py:2956-2984`); PyMySQL surfaces the raw MySQL
  errno as `args[0]` (`dialects/mysql/pymysql.py:156-175`), not a
  SQLSTATE. Our `_sqlstate_of` therefore never sees MySQL conflicts —
  retry classification needs an errno-based rung. (juicefs retries
  these by message substring, `pkg/meta/sql.go:1212-1217`; errno
  matching is the honest version of the same decision. juicefs pins
  MySQL to REPEATABLE READ via DSN, `sql_mysql.go:63-82` — MySQL's
  engine default, pinned against server config drift.)
- **utf8mb4 is not defaulted.** The dialect documents
  `?charset=utf8mb4` as the recommended explicit connection parameter
  (`dialects/mysql/base.py:345-376`); nothing injects it. Connection
  URLs must carry it or unicode *bodies* (LONGTEXT) are at the mercy
  of the driver default.

## 4. Synthesis — why byte denomination dissolves the problem

The three byte ledgers today disagree: the contract speaks characters
(`paths.py`), the write guard speaks bytes (`staging.py:147`), and the
DDL speaks characters that each engine multiplies by its own bytes-per-
char. Denominating the contract in bytes and byte-typing the key
columns collapses all three into one number:

| Engine | path column today | worst-case key today | after byte denomination |
|---|---|---|---|
| SQLite | VARCHAR(1024) | moot (no hard cap hit) | unchanged, fits |
| Postgres (C collation) | VARCHAR(1024) chars | 4,096 B > its 2,704 B btree comfort only for multibyte | ≤ 1,024 B, fits |
| MSSQL (UTF-8 collation) | VARCHAR(1024) — **already bytes** | 1,024 B, fits | unchanged, fits |
| MySQL utf8mb4 | VARCHAR(1024) chars | **4,096 B > 3,072 — DDL refused** | VARBINARY(1024) = 1,024 B, fits |

- A 1,024-**byte** path fits under every declared `key_byte_budget`
  (min is GENERIC/MSSQL at 1,700) **by construction** — the gap
  between budget and DDL closes because both now measure the same
  thing, and a static pin (`MAX_PATH_LENGTH <= min(budgets)`) makes
  the DDL-fits-everywhere claim a tested invariant instead of a hope.
- MSSQL's UTF-8-collated VARCHAR being byte-denominated stops being a
  latent truncation bug (a 1,024-char multibyte path cannot fit its
  1,024-byte column today) and becomes exactly correct.
- Bytewise ordering — the doctrine `_binary_string` already pins via
  collations — is what VARBINARY gives MySQL natively; LIKE-prefix
  sargability and ORDER BY survive because MySQL compares binary
  strings bytewise, and the escaped-LIKE metacharacters are ASCII.
- The numbers 1024/255 stop being vfs inventions and become macOS's
  `PATH_MAX`/`NAME_MAX` — the tightest major-OS floor, so any path
  that round-trips through a real filesystem round-trips through vfs.

Cost: multibyte paths shrink (1,024 bytes ≈ 341 3-byte CJK chars,
256 4-byte emoji), and names lawful on Windows/HFS+ by UTF-16-unit
count can exceed 255 UTF-8 bytes. That is the same trade POSIX,
APFS, and juicefs already made.

## 5. What MySQL support needs beyond the schema fix

1. **A tuned `MYSQL` profile** (and `mariadb` alias): 3,072-byte key
   budget; 65,535 IN-list elements (the wire protocol's uint16
   placeholder cap); `catch_retry` arbitration — MySQL's
   `ON DUPLICATE KEY UPDATE` takes no conflict target and fires on
   *any* unique index, unsafe with both `UNIQUE(parent_id, name)` and
   unique `path` present; REPEATABLE READ pinned (juicefs precedent);
   errno-based retry set {1213, 1205}.
2. **Errno rung in `is_retryable`** — a `retryable_driver_codes`
   profile field checked when the driver exception carries an integer
   error number, mirroring the existing SQLite-code rung.
3. **`?charset=utf8mb4`** documented in every connection URL (compose
   README, CI workflow).
4. The conformance MySQL leg flips from `continue-on-error` to
   enforcing — it is the regression pin for all of the above.
