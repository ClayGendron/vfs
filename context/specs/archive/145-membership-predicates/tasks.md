# 145 — tasks

## Slice A — the helper and the profile
- [x] A1 `membership.py`: `membership`, `locked_lookup`, the cast rule.
- [x] A2 `dialects.py`: `MembershipForm`, `membership` field, MSSQL
      `in_list_budget=2_000`, `row_lock_hint="UPDLOCK, FORCESEEK"`;
      `rows.py` exports `MSSQL_UTF8_COLLATION`.
- [x] A3 Rendering pins: `test_membership.py`; `TestLockRows` and the
      budget pin trued.

## Slice B — the routing
- [x] B1 38 chunk-scale sites through `membership()`; the profile plumbed
      to a fixed point (three rings of callers); direct test callers.
- [x] B2 The three guard reads through `locked_lookup`.

## Slice C — legs, scale, landing
- [x] C1 Contract canary batch (`test_a_membership_batch_past_the_chunk_
      finds_every_path_including_non_latin`); mssql lock-profile and
      predicate pins in `test_conformance.py`.
- [x] C2 Four legs green (947 passed); SQL Server 10k-edge create
      18.1 s → 2.4 s, zero escalations.
- [x] C3 `scripts/ci.sh 3.13` green at 100 %; landing note written.
- [x] C4 Committed `b77ce36`; archived; STATUS bullet.
