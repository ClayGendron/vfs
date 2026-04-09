#!/usr/bin/env bash
set -euo pipefail

/opt/mssql/bin/sqlservr &
SQLSERVR_PID=$!

echo "[entrypoint] waiting for SQL Server to accept connections..."
for i in {1..60}; do
  if /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa \
       -P "${MSSQL_SA_PASSWORD:?MSSQL_SA_PASSWORD must be set}" \
       -C -N -l 2 -Q "SELECT 1" >/dev/null 2>&1; then
    echo "[entrypoint] SQL Server is up."
    break
  fi
  sleep 2
  if [ "$i" = "60" ]; then
    echo "[entrypoint] SQL Server failed to become ready" >&2
    exit 1
  fi
done

echo "[entrypoint] ensuring grover_test database exists..."
/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa \
    -P "${MSSQL_SA_PASSWORD}" -C -N \
    -i /usr/local/share/init-db.sql

echo "[entrypoint] init complete; handing off to sqlservr (PID=${SQLSERVR_PID})"
wait "${SQLSERVR_PID}"
