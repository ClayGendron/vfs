#!/bin/zsh
# The remaining legs, one at a time: MariaDB 1M, SQL Server 1M, Postgres 10M on a disk-backed throwaway
# container (the shared test container keeps its data in tmpfs and the 8 GB Docker VM reset under 10M rows),
# then SQLite 10M. Leaves the containers it started stopped and removed.
set -u
HERE=${0:A:h}; OUT=$HERE/results; LOG=${LOG_DIR:-$OUT}
cd /Users/claygendron/Git/Repos/vfs
run() { echo "== $1 $3 files: $(date +%T)"; uv run python -I $HERE/rollup_experiment.py --url "$2" --files $3 --out $OUT/$1-$3.json > $LOG/$1-$3.log 2>&1 && echo "   ok $(date +%T)" || echo "   FAILED $(date +%T), see $LOG/$1-$3.log"; }
run mariadb "mariadb+aiomysql://vfs:vfs@localhost:33062/vfs?charset=utf8mb4" 1000000
run mssql   "mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes" 1000000
docker stop -t 60 vfs-test-mssql-1 vfs-test-mariadb-1 >/dev/null 2>&1; docker rm vfs-test-mssql-1 vfs-test-mariadb-1 >/dev/null 2>&1
docker run -d --name exp-pg -e POSTGRES_USER=vfs -e POSTGRES_PASSWORD=vfs -e POSTGRES_DB=vfs -p 54329:5432 pgvector/pgvector:pg17 >/dev/null
for i in $(seq 1 60); do docker exec exp-pg pg_isready -U vfs -d vfs >/dev/null 2>&1 && break; sleep 2; done
run postgres "postgresql+asyncpg://vfs:vfs@localhost:54329/vfs" 10000000
docker stop -t 30 exp-pg >/dev/null 2>&1; docker rm -v exp-pg >/dev/null 2>&1
run sqlite "sqlite+aiosqlite:///$SCRATCH/rollup-sqlite-10m.db" 10000000
echo "== remaining legs done $(date +%T)"
