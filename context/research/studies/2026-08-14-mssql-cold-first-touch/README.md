# Study: MSSQL cold first touch under an in-flight topology window

Supporting artifacts for
`../../2026-08-14-mssql-cold-first-touch-investigation.md`.

## Contents

- `mssql_cold_first_touch.py` — the base repro: a warm instance frozen
  mid-delete at the `delete:post-collect` seam while a cold
  `DatabaseStorage` issues its first op; short (10 s) and long (45 s)
  holds.
- `mssql_cold_controls.py` — the flavor-isolation controls (C1
  cold+unrelated path, C2 warm+unrelated, C3 warm+deleted subtree) and
  the C4 storm (eight concurrent cold first-touches inside a 60 s
  hold).

## Reproducing

Bring up the MSSQL leg per the `db_test` skill, then:

```sh
uv sync --extra mssql --group dev
VFS_TEST_MSSQL_URL="mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" \
  uv run python mssql_cold_first_touch.py
```

Run record (2026-08-14, Apple Silicon, MSSQL 2022 under Rosetta,
fresh container): every cold first-touch blocked for exactly the
rival's hold (10.1 s / 45.1 s / 60.1 s) and completed clean at
release; warm instances never blocked; zero raw driver failures in
10 cold touches across all shapes. The full MSSQL conformance leg ran
green on the same fresh container immediately after (205 passed /
4 skipped, 70 s).
