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
