# 024. Byte-Denominated Path Limits, Byte-Typed Key Columns, MySQL Profile

- **Status:** accepted 2026-07-23 — the byte-denomination angle proposed
  by Clay in session (target macOS's 1024/255), confirmed by research,
  implemented the same day.
- **Date:** 2026-07-23
- **Deciders:** Clay Gendron
- **Context source:**
  `research/2026-07-23-mysql-support-byte-denominated-path-limits.md` —
  triggered by the first real-engine conformance run: MySQL refuses the
  schema (error 1071) because the path unique index's utf8mb4 worst
  case (4,096 bytes) exceeds InnoDB's 3,072-byte cap, exposing that
  `key_byte_budget` bound writes but never DDL.

## Decisions

### 1. Path limits are byte counts, matching the OS canon

`MAX_PATH_LENGTH` (1024) and `MAX_SEGMENT_LENGTH` (255) denominate
**UTF-8 bytes**, not characters — the same numbers, the units every
real filesystem uses (BSD/macOS `PATH_MAX`/`NAME_MAX` are exactly
1024/255 *bytes*; Linux enforces byte counts; APFS components are 255
UTF-8 bytes). Validation and rebase-overflow checks measure
`len(s.encode())`. ASCII paths are unaffected; multibyte paths shrink
(≈341 CJK chars, ≈256 emoji), the same trade POSIX and APFS made.
1024 bytes is the tightest major-OS floor: any path that round-trips a
real filesystem round-trips vfs.

### 2. Key columns are byte-typed where the engine counts characters

`_binary_string` becomes a `TypeDecorator` that compiles to
`VARBINARY(n)` on mysql/mariadb (UTF-8 encode on bind, decode on
result), keeping the existing collation-pinned `String` where a pin
exists (postgres, mssql; SQLite's default BINARY collation is already
bytewise). Bytewise ordering — the doctrine the collations existed to
pin — is native to binary types; LIKE-prefix sargability survives
(ASCII metacharacters, bytewise comparison). Oracle and unmeasured
engines take the plain character-typed `String` fallback with no
collation pin (`VARCHAR2(n CHAR)` on Oracle) — bytewise order there
rests on engine defaults (`NLS_SORT=BINARY`), an accepted degradation,
not a pinned contract. Every variant names **both** `"mysql"` and
`"mariadb"` — SQLAlchemy resolves variants strictly by
`dialect.name`, and MariaDB's is `"mariadb"`.

### 3. The budget↔DDL gap closes by construction, and is pinned

With byte-denominated limits and byte-typed keys, the worst-case index
key equals the contract number (1,024 ≤ every declared
`key_byte_budget`, min 1,700). A unit test pins
`MAX_PATH_LENGTH <= min(profile.key_byte_budget)` and the mysql
`VARBINARY(1024)` compilation, so "the DDL fits every engine" is a
tested invariant, not a hope. `within_budget` stays as the runtime
guard for future tighter profiles. This also retires MSSQL's latent
truncation hazard: its UTF-8-collated `VARCHAR(1024)` was already
byte-denominated, and the contract now agrees with it.

### 4. MySQL joins the tuned profiles; MariaDB rides the same policy

`MYSQL` profile: `key_byte_budget=3_072`, `in_list_budget=65_535` (the
wire protocol's uint16 placeholder cap), `catch_retry` arbitration —
`ON DUPLICATE KEY UPDATE` takes no conflict target and fires on *any*
unique index, unsafe beside both `UNIQUE(parent_id, name)` and unique
`path` — and `REPEATABLE READ` pinned for op sessions (the engine
default, pinned against server config drift; juicefs does the same).
`mariadb` registers the same policy under its own name. Durability
declares `full` (InnoDB's default flush-at-commit).

### 5. Retry classification gains an errno rung

MySQL deadlock (1213) and lock-wait timeout (1205) surface as raw
driver error numbers, not SQLSTATEs — SQLAlchemy classifies neither.
`DialectProfile` gains `retryable_driver_codes` (integer errnos),
checked by `is_retryable` when the driver exception carries an integer
first argument, mirroring the SQLite-code rung. Only the mysql-family
profiles populate it.

### 6. utf8mb4 travels in the URL

Connection URLs carry `?charset=utf8mb4` (documented in
`docker/README.md`, used by CI). The dialect does not default it, and
unicode text bodies (LONGTEXT) depend on it; key columns no longer do.

## Consequences

- The MySQL conformance leg flips from `continue-on-error` to
  enforcing — it is the regression pin for the schema, profile, and
  retry decisions.
- "Unknown dialects are served, not refused" regains truth on the most
  common unknown dialect; MariaDB is served as a first-class alias.
- Rejected alternatives: prefix indexes (`mysql_length`) — prefix
  uniqueness is stricter than path uniqueness; shrinking the declared
  char length — reintroduces the char/byte mismatch in the other
  direction; hashing long keys (Oak's fallback) — unnecessary once the
  logical key is bounded under every budget.
