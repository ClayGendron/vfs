"""Probe I: DDL bisect. Same 9-column insert (entry_id, path, name, kind,
lines, size_bytes, chunked, encoded, indexable) into variants of the entry
table's DDL. Bare pyodbc, one 300-row fast_executemany call. Reports rows
landed when the cursor is closed right away, and the pending result count
when drained with nextset()."""
from __future__ import annotations

import os

import pyodbc

import rl_common as C

N = 300
U8 = "COLLATE Latin1_General_100_BIN2_UTF8"
COLS = "(entry_id, path, name, kind, lines, size_bytes, chunked, encoded, indexable)"


def full(identity="BIGINT NOT NULL IDENTITY", bit="BIT", u8=U8, uq=True, extra=True):
    parts = [f"id {identity}", "entry_id BINARY(16) NOT NULL", "parent_id BINARY(16) NULL"]
    if extra:
        parts += [f"external_id VARCHAR(1024) {u8} NULL"]
    parts += [f"path VARCHAR(1024) {u8} NOT NULL", f"name VARCHAR(255) {u8} NOT NULL", "kind VARCHAR(32) NOT NULL"]
    if extra:
        parts += ["version BIGINT NULL", "content_hash VARCHAR(64) NULL", f"mime_type VARCHAR(255) {u8} NULL", f"ext VARCHAR(32) {u8} NULL"]
    parts += ["lines INTEGER NOT NULL", "size_bytes INTEGER NOT NULL", f"chunked {bit} NOT NULL", f"encoded {bit} NOT NULL", f"indexable {bit} NOT NULL"]
    if extra:
        parts += ["chunk_source_hash VARCHAR(64) NULL", f"chunk_generation VARCHAR(32) {u8} NULL", f"owner_id VARCHAR(255) {u8} NULL",
                  "original_parent_id BINARY(16) NULL", f"original_name VARCHAR(255) {u8} NULL",
                  "created_at DATETIMEOFFSET NULL", "updated_at DATETIMEOFFSET NULL", "deleted_at DATETIMEOFFSET NULL"]
    if "IDENTITY" in identity or "NOT NULL" in identity:
        parts += ["PRIMARY KEY (id)"]
    if uq:
        parts += ["CONSTRAINT uq_%s_parent_name UNIQUE (parent_id, name)"]
    return ", ".join(parts)


INDEXES = [
    "CREATE UNIQUE INDEX ix_%s_entry_id ON %s (entry_id)",
    "CREATE UNIQUE INDEX ix_%s_path ON %s (path)",
    "CREATE INDEX ix_%s_kind ON %s (kind)",
    "CREATE INDEX ix_%s_ext ON %s (ext)",
    "CREATE INDEX ix_%s_owner_id ON %s (owner_id)",
    "CREATE INDEX ix_%s_ext_kind ON %s (ext, kind)",
    "CREATE INDEX ix_%s_encoded_kind ON %s (encoded, kind)",
    "CREATE INDEX ix_%s_restore ON %s (original_parent_id, original_name)",
]

CASES = {
    "A_full_ddl+all_indexes": (full(), INDEXES),
    "B_full_ddl_no_indexes": (full(), []),
    "C_no_identity": (full(identity="BIGINT NULL"), []),
    "D_int_identity": (full(identity="INT NOT NULL IDENTITY"), []),
    "E_no_unique_constraint": (full(uq=False), []),
    "F_bits_as_int": (full(bit="INT"), []),
    "G_no_utf8_collation": (full(u8=""), []),
    "H_only_inserted_cols+identity": (full(extra=False), []),
    "I_only_inserted_cols_no_identity": (full(identity="BIGINT NULL", extra=False), []),
    "J_only_inserted_cols_no_identity_no_uq": (full(identity="BIGINT NULL", extra=False, uq=False), []),
    "K_no_identity+all_indexes": (full(identity="BIGINT NULL"), INDEXES),
    "L_only_path_unique_index": (full(identity="BIGINT NULL", uq=False), [INDEXES[1]]),
    "M_only_entry_id_unique_index": (full(identity="BIGINT NULL", uq=False), [INDEXES[0]]),
    "N_only_kind_index": (full(identity="BIGINT NULL", uq=False), [INDEXES[2]]),
}


def run(conn, table, params, mode):
    cur = conn.cursor()
    cur.fast_executemany = True
    error, nextsets = None, 0
    try:
        cur.executemany(f"INSERT INTO {table} {COLS} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", params)
        if mode == "drain":
            while cur.nextset():
                nextsets += 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    cur.close()
    conn.commit()
    landed = conn.cursor().execute(f"SELECT COUNT(*) FROM {table}").fetchval()
    conn.commit()
    return landed, nextsets, error


def main() -> None:
    conn = pyodbc.connect(C.ODBC, autocommit=False)
    for name, (ddl, indexes) in CASES.items():
        results = {}
        for mode in ("close", "drain"):
            table = f"rl_i_{name.split('_')[0]}_{mode}"
            cur = conn.cursor()
            cur.execute(f"IF OBJECT_ID('{table}') IS NOT NULL DROP TABLE {table}")
            cur.execute(f"CREATE TABLE {table} ({ddl.replace('%s', table)})")
            for ix in indexes:
                cur.execute(ix % (table, table))
            conn.commit()
            params = [(C.ULID().bytes, f"/i/{name}/{i}", str(i), "file", 0, 0, 0, 0, 0) for i in range(N)]
            results[mode] = run(conn, table, params, mode)
            conn.cursor().execute(f"DROP TABLE {table}")
            conn.commit()
        C.record(probe="I-ddl-bisect", case=name, n=N, landed_on_close=results["close"][0], landed_on_drain=results["drain"][0],
                 pending_results=results["drain"][1], error=results["close"][2] or results["drain"][2], ddl=ddl, indexes=len(indexes))
    conn.close()


if __name__ == "__main__":
    main()
