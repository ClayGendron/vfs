#!/bin/sh
# usage: hang.sh <copy> <tag> <threads> <writers>
# Runs the contention node on the SQL Server leg with the loop's executor at <threads>. When the node records
# a hang, or writes no line in 220 s, it reads what the server's sessions are waiting on and stops the run:
# a hung run cannot stop itself, and one whose threads are all blocked cannot even record that it hung.
# Run one at a time: the stop is by the node's command line.
LAB="$(cd "$(dirname "$0")" && pwd)"
COPY="$1"; TAG="$2"
export LABEL_EXPERIMENT_THREADS="$3" LABEL_EXPERIMENT_WRITERS="$4"
"$LAB/run.sh" "$COPY" mssql "$TAG" -k contention -n 1 &
OUT="$LAB/out/$TAG-mssql.jsonl"
SERVER="$LAB/out/$TAG-mssql.server.txt"
i=0
while [ $i -lt 110 ]; do
  sleep 2; i=$((i + 1))
  if grep -q '"hung": ' "$OUT" 2>/dev/null; then break; fi
  # run.sh writes its exit line last: a run that died early is not waited out.
  if grep -q ' exit=' "$LAB/out/$TAG-mssql.log" 2>/dev/null; then break; fi
done
if ! grep -q '"hung": false' "$OUT" 2>/dev/null; then
  if grep -q '"hung": true' "$OUT" 2>/dev/null; then echo "the node recorded the hang" > "$SERVER"
  elif grep -q ' exit=' "$LAB/out/$TAG-mssql.log" 2>/dev/null; then echo "the run ended without a result line" > "$SERVER"
  else echo "the node wrote no line in 220 s" > "$SERVER"; fi
  docker exec vfs-test-mssql-1 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'vfsStr0ngPassw0rd' -C -h -1 -W -Q "SET NOCOUNT ON; SELECT 'blocked requests', COUNT(*) FROM sys.dm_exec_requests WHERE blocking_session_id <> 0; SELECT 'idle sessions holding a transaction', COUNT(*) FROM sys.dm_exec_sessions WHERE session_id > 50 AND status = 'sleeping' AND open_transaction_count > 0; SELECT 'requests waiting on a shared lock', COUNT(*) FROM sys.dm_exec_requests WHERE blocking_session_id <> 0 AND wait_type = 'LCK_M_S'; SELECT 'requests waiting on an update or exclusive lock', COUNT(*) FROM sys.dm_exec_requests WHERE blocking_session_id <> 0 AND wait_type IN ('LCK_M_U', 'LCK_M_X'); SELECT 'waits on the stamps table', COUNT(*) FROM sys.dm_exec_requests r CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t WHERE r.blocking_session_id <> 0 AND t.text LIKE '%vfs_principal_revisions%'; SELECT 'longest wait in seconds', MAX(wait_time) / 1000 FROM sys.dm_exec_requests WHERE blocking_session_id <> 0" >> "$SERVER" 2>&1
  for p in $(ps -eo pid,command | grep "[t]est_label_experiment.py -m mssql" | awk '{print $1}'); do kill -9 "$p"; done
  pkill -9 -f "exec\(eval\(sys.stdin.readline" 2>/dev/null
fi
wait 2>/dev/null
echo "== $TAG"; cut -c1-300 "$OUT"; cat "$SERVER" 2>/dev/null
