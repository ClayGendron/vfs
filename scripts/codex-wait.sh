#!/bin/bash
# codex-wait.sh RUNDIR [SECONDS]
#
# Waits for a run that scripts/codex-run.sh started, for at most SECONDS (540 by default).
# The wait has a deadline and the run has none: when the deadline passes, this script stops
# and the run goes on. Call it again to keep waiting.
#
# Exit status:
#   0    the run finished and Codex exited 0; RUNDIR/last.md holds its last message
#   1    the run finished and Codex exited with an error; RUNDIR/stderr.log says why
#   124  the deadline passed and the run is still going
#   3    the run is gone and left no exit code, so it was killed from outside
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "usage: codex-wait.sh RUNDIR [SECONDS]" >&2
  exit 2
fi
run=$1
limit=${2:-540}
deadline=$(( $(date +%s) + limit ))
while [ ! -f "$run/exit_code" ]; do
  if [ -s "$run/pid" ] && ! kill -0 "$(cat "$run/pid")" 2>/dev/null; then
    sleep 3  # the runner writes exit_code just after Codex exits
    [ -f "$run/exit_code" ] && break
    echo "the run is gone and left no exit code: $run" >&2
    exit 3
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "still running after ${limit}s: $run" >&2
    exit 124
  fi
  sleep 5
done
code=$(cat "$run/exit_code")
echo "finished with exit code $code: $run"
[ "$code" = "0" ]
