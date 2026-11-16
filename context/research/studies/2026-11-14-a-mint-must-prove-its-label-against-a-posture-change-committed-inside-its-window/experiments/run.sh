#!/bin/sh
# usage: run.sh <copy> <engine> <out-tag> [pytest args...]   — runs the experiment file in <copy> on one engine
# <copy> is a folder beside this script: `git archive HEAD | tar -x` of vfs, the built extension copied into
# src/vfs/, reproducing-node.patch applied, then base.patch, candA.patch or candB.patch over it.
set -u
LAB="$(cd "$(dirname "$0")" && pwd)"
COPY="$LAB/$1"; ENGINE="$2"; TAG="$3"; shift 3
cp "$LAB/test_label_experiment.py" "$COPY/tests/storage/database/test_label_experiment.py"
case "$ENGINE" in
  postgres) export VFS_TEST_POSTGRES_URL="postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" ;;
  mariadb)  export VFS_TEST_MARIADB_URL="mariadb+aiomysql://vfs:vfs@localhost:33062/vfs?charset=utf8mb4" ;;
  # LABEL_EXPERIMENT_MSSQL_DB names another database, such as one with READ_COMMITTED_SNAPSHOT on.
  mssql)    export VFS_TEST_MSSQL_URL="mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/${LABEL_EXPERIMENT_MSSQL_DB:-master}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" ;;
  oracle)   export VFS_TEST_ORACLE_URL="oracle+oracledb_async://vfs:vfs@localhost:15210/?service_name=FREEPDB1" ;;
esac
export LABEL_EXPERIMENT_OUT="$LAB/out/$TAG-$ENGINE.jsonl"
mkdir -p "$LAB/out"; : > "$LABEL_EXPERIMENT_OUT"
cd "$COPY" && PYTHONPATH="$COPY/src:$COPY" uv run --project "${VFS_REPO:?the vfs checkout whose venv runs the copy}" --no-sync python -m pytest \
  tests/storage/database/test_label_experiment.py -m "$ENGINE" -p no:cacheprovider -n 4 -q --no-header --tb=line "$@" \
  > "$LAB/out/$TAG-$ENGINE.log" 2>&1
echo "$TAG-$ENGINE exit=$?" >> "$LAB/out/$TAG-$ENGINE.log"
