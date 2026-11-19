#!/bin/bash
# codex-run.sh PROMPT_FILE WORKDIR MODEL RUNDIR
#
# Starts one headless Codex run, detached and with no time limit, and returns at once.
# RUNDIR is made, and it gets: prompt.md meta.env pid session_id events.jsonl stderr.log
# last.md rollout.jsonl ended_at exit_code. The run is finished when exit_code is there.
# Wait for it with scripts/codex-wait.sh. documentation/maintainers/how-we-run-codex.md
# says why each flag is set.
#
# Optional environment:
#   SANDBOX  read-only, workspace-write (the default) or danger-full-access
#   EXTRA    more flags for `codex exec`, such as --skip-git-repo-check
#   CODEX    the binary to run, `codex` by default
set -euo pipefail
if [ $# -ne 4 ]; then
  echo "usage: codex-run.sh PROMPT_FILE WORKDIR MODEL RUNDIR" >&2
  exit 2
fi
prompt=$1 workdir=$2 model=$3 run=$4
mkdir -p "$run"
run=$(cd "$run" && pwd)
cp "$prompt" "$run/prompt.md"
{
  echo "model=$model"
  echo "workdir=$workdir"
  echo "sandbox=${SANDBOX:-workspace-write}"
  echo "extra=${EXTRA:-}"
  echo "codex_version=$(${CODEX:-codex} --version)"
  echo "started_at=$(date -u +%FT%TZ)"
} > "$run/meta.env"

# The runner. Codex runs in the foreground so it keeps a normal SIGINT, its clean-stop signal.
# A side watcher records the session id and keeps the machine awake while Codex lives.
runner='
run=$1; shift
cd "$run"
trap ":" INT TERM
(
  until [ -s pid ]; do sleep 1; done
  caffeinate -i -w "$(cat pid)" 2>/dev/null &
  until [ -s session_id ] || ! kill -0 "$(cat pid)" 2>/dev/null; do
    jq -r "select(.type==\"thread.started\").thread_id" < <(head -1 events.jsonl 2>/dev/null) > sid.tmp 2>/dev/null || true
    [ -s sid.tmp ] && mv sid.tmp session_id
    sleep 1
  done
) &
rc=0
bash -c "echo \$\$ > pid; exec \"\$@\"" codex "$@" -o "$run/last.md" - \
  < prompt.md > events.jsonl 2> stderr.log || rc=$?
r=$(find ~/.codex/sessions -name "*$(cat session_id 2>/dev/null).jsonl" 2>/dev/null | head -1)
[ -s session_id ] && [ -n "$r" ] && cp "$r" rollout.jsonl
date -u +%FT%TZ > ended_at
echo $rc > exit_code.tmp && mv exit_code.tmp exit_code
'

# perl gives the run a session and a process group of its own, so a kill aimed at the caller's
# group misses it. It also puts SIGINT back to its default, which `&` in a script turns off.
nohup perl -MPOSIX -e '$SIG{INT}="DEFAULT"; POSIX::setsid(); exec @ARGV' \
  /bin/bash -c "$runner" runner "$run" \
  "${CODEX:-codex}" exec --json \
    -m "$model" -C "$workdir" -s "${SANDBOX:-workspace-write}" \
    -c 'model_reasoning_effort="high"' \
    -c 'project_doc_max_bytes=262144' \
    -c 'sandbox_workspace_write.exclude_slash_tmp=true' \
    -c 'sandbox_workspace_write.exclude_tmpdir_env_var=true' \
    ${EXTRA:-} \
  < /dev/null > "$run/runner.log" 2>&1 &
echo "$run"
