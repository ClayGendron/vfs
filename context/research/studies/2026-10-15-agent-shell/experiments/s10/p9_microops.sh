#!/bin/sh
# S10: per-operation 9P cost. One fresh server + one fresh v9fs mount per shell operation,
# so the server's report isolates that operation's T-messages, vfs verbs and SQL statements.
# usage: sh p9_microops.sh   (from the vfs repo root; needs Docker Desktop and the vfs-s10-sci image)
set -u
E=context/research/studies/2026-10-15-agent-shell/experiments/s10
OUT=$E/out_p9_microops_per_op.txt
: > "$OUT"
PORT=5650
run_op() {
  name="$1"; cmd="$2"
  PORT=$((PORT + 1))
  uv run python -I "$E/p9_server.py" --port $PORT --report "$E/tmp_p9_$name.json" > /dev/null 2>&1 &
  sleep 2
  docker run --rm --cap-add SYS_ADMIN --security-opt apparmor=unconfined vfs-s10-sci sh -c "IP=\$(getent ahostsv4 host.docker.internal | awk '{print \$1}' | head -1); mkdir -p /mnt/vfs && mount -t 9p -o trans=tcp,port=$PORT,version=9p2000,uname=agent-7,aname=/,dfltuid=0,dfltgid=0 \$IP /mnt/vfs && cd /mnt/vfs && $cmd; cd /; umount /mnt/vfs" > /dev/null 2>&1
  sleep 1
  pkill -TERM -f "p9_server.py --port $PORT"
  sleep 2
  uv run --no-project python -I -c "
import json; d=json.load(open('$E/tmp_p9_$name.json'))
m={k:v for k,v in d['messages'].items() if k not in ('Tversion','Tattach')}
print('$name'.ljust(14), 'msgs', m, '| verbs', d['verbs'], '| sql', d['sql_total'] - d['sql_per_message'].get('Tattach', 0))
" >> "$OUT"
  rm -f "$E/tmp_p9_$name.json"
}
run_op mount_only "true"
run_op cat        "cat data/sales.csv > /dev/null"
run_op ls         "ls out > /dev/null"
run_op stat       "stat data/sales.csv > /dev/null"
run_op write_new  "echo abc > out/new.txt"
run_op mkdir      "mkdir out/d"
run_op rm         "rm scripts/job.py"
run_op mv         "mv data/sales.csv data/sales2.csv"
run_op py_read    "python -c 'open(\"data/sales.csv\").read()'"
run_op py_write   "python -c 'open(\"out/x.bin\",\"wb\").write(bytes(range(256)))'"
cat "$OUT"
