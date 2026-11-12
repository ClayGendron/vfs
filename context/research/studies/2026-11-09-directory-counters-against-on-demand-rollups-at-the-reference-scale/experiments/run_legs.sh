#!/bin/zsh
# Runs the rollup experiment on every engine in turn (never concurrently: the wall-clock facts want a quiet machine).
set -u
HERE=${0:A:h}
OUT=$HERE/results; mkdir -p $OUT
LOG=${LOG_DIR:-$HERE/results}
cd /Users/claygendron/Git/Repos/vfs
run() { # name url files
  echo "== $1 $3 files: $(date +%T)"
  uv run python -I $HERE/rollup_experiment.py --url "$2" --files $3 --out $OUT/$1-$3.json > $LOG/$1-$3.log 2>&1 && echo "   ok $(date +%T)" || echo "   FAILED, see $LOG/$1-$3.log"
}
run sqlite   "sqlite+aiosqlite:///$SCRATCH/rollup-sqlite.db" 1000000
run postgres "postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" 1000000
run mariadb  "mariadb+aiomysql://vfs:vfs@localhost:33062/vfs?charset=utf8mb4" 1000000
run oracle   "oracle+oracledb_async://vfs:vfs@localhost:15210/?service_name=FREEPDB1" 1000000
run mssql    "mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" 1000000
run postgres "postgresql+asyncpg://vfs:vfs@localhost:54320/vfs" 10000000
echo "== all legs done $(date +%T)"
