# Backlog design checks against dev

The checks below ran against `27f3d24d`. Each entry identifies the behavior exercised and the part of the proposed design that the observation supports.

## Layer 1

| Unit | Executed check | Observation and scope |
|---|---|---|
| 149-2, token verification | With PyJWT 2.15.1, generate an ephemeral 2,048-bit RSA key, sign five RS256 fixtures and decode with a pinned public key, issuer and audience. Require `exp`, `aud`, `iss` and `sub`. Change one claim per fixture. | The valid fixture yielded its original subject. The other four raised `ExpiredSignatureError`, `InvalidAudienceError`, `MissingRequiredClaimError` and `InvalidIssuerError` respectively. This checks the proposed dependency's behavior. The vfs verifier and error mapping await implementation. |
| 170-1, batch rights | Run the existing pointwise, multi-subject and posture-change cases listed below with PostgreSQL 16.2, pgvector 0.6.2 and asyncpg. Run the held-relabel oracle case with its existing SQLite fixture. | All four cases passed. They establish the existing rights behavior the proposed batch result must match. The future batch statement count remains unmeasured. |
| 178-2, ranged reads | In PostgreSQL 16.2 evaluate `octet_length(substring(decode('','hex') FROM 1 FOR 1))`, `octet_length(substring(decode('e29883','hex') FROM 4 FOR 1))` and `substring(NULL::bytea FROM 1 FOR 1) IS NULL`. | The results were 0, 0 and true. A stored empty value and a slice beyond the end remain distinct from a missing body on this engine. The draft records the SQLite result and a separate boundary oracle. The vfs ranged-read verb remains unbuilt. |
| 180-5, retention continuation | Model the four phases with zero to three keys per phase, page allowances 1–4 and slice budgets 1–4. Remove processed roots, retain examined family keys, and compare the concatenated pages against one full ordered traversal. Separately round-trip all seven valid phase/presence combinations in a `struct.Struct(">16sBB16sqq")` record through Fernet. | All 4,096 static pagination cases terminated, visited each key exactly once and respected the per-call allowance. The seven 50-byte records all produced a 169-byte prefixed token. This prototype does not exercise concurrent writes, VFS authorization or a persistence migration. |

The three PostgreSQL nodes belong to `tests/storage/test_conformance.py::TestPostgresConformance` and ran with a private cluster selected by `VFS_TEST_POSTGRES_URL`: `test_holds_says_whether_a_caller_holds_a_level_at_a_path`, `test_a_subject_set_holds_only_what_every_member_holds` and `test_a_posture_change_is_seen_by_a_caller_already_resolved`. The SQLite node was `tests/storage/database/test_rights.py::test_reads_match_the_oracle_while_a_posture_relabel_is_held_midway`.

## PostgreSQL conformance baseline

The complete `pytest -m postgres` selection at `27f3d24d` contains 565 tests. All 565 passed on PostgreSQL 16.2 with pgvector 0.6.2 and the locked asyncpg driver. A first unsharded run reached its six-minute deadline before the final summary. The repeat used the exact collected node IDs in four disjoint groups of 180, 180, 180 and 25. Each group ran with `-n0` against the same private cluster using the repository's isolated fixtures. The four JUnit reports contained 565 distinct test cases, zero omissions, zero skips and zero failures. This establishes a baseline for the existing implementation on one Postgres version. Proposed behaviors are checked separately in the units that own them.

## Layer 2

Unit 175-3's body guard was exercised on PostgreSQL 16.2 through three actual asyncpg connections and a disposable table with a primary key and text body. The predicate `WHERE id=1 AND convert_to(body,'UTF8')=$1 FOR UPDATE` matched the original UTF-8 bytes for `é` and rejected its decomposed encoding. While the first transaction held the matched row, `pg_blocking_pids` identified it as the blocker of a second writer. A third connection read the committed old text before the first transaction released the lock. After the rival update committed, the stale candidate matched zero rows and the third connection read the rival's text. This validates the SQL predicate and lock behavior. The history mutation and end-to-end vfs verb remain separate acceptance checks.

## Layer 3

For 171-1, MCP Python SDK 1.29.0 constructed and round-tripped a `CallToolResult` through `model_dump_json(by_alias=True, exclude_none=True)` and `model_validate_json`. The four content blocks came back as `text`, `image`, `audio` and `resource_link` in that order. The link retained `vfs:///big`, the structured payload kept its four fields and one byte-free row, and `isError` remained false. The fixture supplied two synthetic bytes for each binary block. It tested the SDK's wire object model, without decoding a media file or exercising a VFS adapter or negotiated historical protocol revision.

## Layer 4

For 172-1, the published `wasi_python-0.1.0-py3-none-any.whl` downloaded successfully and its SHA-256 was `3bfb0dcc48ce1ce9f4741e142a3a73e865b2028b7468179588d52f418dabfafc`, matching decision 1. Its Python package imported and resolved the snapshot, plain module, standard library and manifest. A cold `run` of a three-element NumPy and pandas sum with no mounts or grants, two billion fuel and a 90-second guest deadline ended at host exit 137 without a guest result. Restricting the host to one CPU and one allocator arena produced the same outcome. The host exit does not establish a guest trap, a stage exit, a working provider adapter or the proposed 21-call budget.

## Layer 7

For 170-4, a local FastMCP server and an initialized ClientSession exchanged messages through MCP Python SDK 1.29.0's in-memory transport. The server advertised one tool, one resource and one prompt. A call to `twice(21)` returned text `42`, structured content `{"result":42}` and `isError=false`. A negative integer rejected by the tool and an invalid string rejected by argument validation each returned a text block with `isError=true` and no structured content. The same session subsequently read the resource and rendered the prompt. This exercised the SDK pathways the proposed VFS import needs. Checking the resulting rows, exit codes and authorization awaits the adapter.

## Gate preflight

The docs gate (`scripts/docs.sh check`) passed on the work checkout, including 20 Chromium layout tests with the repository-pinned Chrome for Testing 156.0.8078.4. An initial run lacked the browser executable. Installing the checksum-verified pinned headless shell resolved that setup failure.

On the work branch the Python 3.13 CI preflight passed installation, lint, formatting and types. The coverage run lost pytest workers and produced no passing coverage summary. The 10,000-root test `tests/base/test_glob_namespace.py::test_a_wide_scoped_glob_builds_roots_plus_arms` passed by itself without coverage. It exited 137 by itself with the repository's coverage configuration on CPython 3.13.5 and 3.13.18. A separate checkout of unchanged `origin/dev` at `27f3d24d` reproduced exit 137 with the same node, CPython 3.13.18 and the identical native binary. The complete CI script on that control checkout stopped earlier, when the host killed a Rust compiler during installation. These are preflight observations; the final branch gate is still owed.
