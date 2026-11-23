#!/usr/bin/env bash
# Probe four MCP-to-CLI clients against fake_server.py: argument coercion, isError, a large result,
# a missing required argument. Each case reports exit code, stdout/stderr sizes and heads, and how
# many tools/call requests reached the server. Every client call carries its own 60 s deadline.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
S="${SCRATCH:?set SCRATCH to the scratch directory holding tools/}"
SERVER="python3 -I $HERE/fake_server.py"
LOG="$S/fake_server.log"
export FAKE_SERVER_LOG="$LOG"
export MCPC_HOME_DIR="$S/mcpc-home"
PMC="bun run $S/tools/pmc/src/index.ts"
MCPORTER="$S/tools/npmtools/node_modules/.bin/mcporter"
MCPC="$S/tools/npmtools/node_modules/.bin/mcpc"
MCP2CLI="uv tool run --from mcp2cli==3.9.0 mcp2cli"
: > "$LOG"
mkdir -p "$MCPC_HOME_DIR" "$S/work"
cat > "$S/work/mcp_servers.json" <<EOF
{"mcpServers": {"fake": {"command": "python3", "args": ["-I", "$HERE/fake_server.py"]}}}
EOF

calls() { grep -c '"tools/call"' "$LOG" || true; }

probe() {
  local label="$1"; shift
  local before; before=$(calls)
  local out err code
  out=$(cd "$S/work" && timeout 60 "$@" 2>"$S/work/stderr.txt"); code=$?
  err=$(cat "$S/work/stderr.txt")
  local after; after=$(calls)
  printf '### %s\nexit=%s stdout_chars=%s stderr_chars=%s wire_calls=%s\n' \
    "$label" "$code" "${#out}" "${#err}" "$((after - before))"
  printf 'stdout_head: %s\n' "$(printf '%s' "$out" | head -c 240 | tr '\n' ' ')"
  printf 'stdout_tail: %s\n' "$(printf '%s' "$out" | tail -c 160 | tr '\n' ' ')"
  printf 'stderr_head: %s\n\n' "$(printf '%s' "$err" | head -c 240 | tr '\n' ' ')"
}

ARGS_JSON='{"query":"hi","limit":5,"tags":["a,b","c"],"mode":"fast","verbose":true,"filter":{"field":"x","op":"eq"}}'

echo "## philschmid/mcp-cli 0.3.0 (JSON argument only)"
export MCP_NO_DAEMON=1
probe "pmc echo json" $PMC -c "$S/work/mcp_servers.json" call fake echo "$ARGS_JSON"
probe "pmc fail" $PMC -c "$S/work/mcp_servers.json" call fake fail '{}'
probe "pmc big" $PMC -c "$S/work/mcp_servers.json" call fake big '{}'
probe "pmc echo missing required" $PMC -c "$S/work/mcp_servers.json" call fake echo '{}'
probe "pmc grep tools" $PMC -c "$S/work/mcp_servers.json" grep '*e*'

echo "## mcp2cli 3.9.0 (flags from the schema)"
probe "mcp2cli echo flags" $MCP2CLI --mcp-stdio "$SERVER" echo --query hi --limit 5 --tags 'a,b' --mode fast --verbose --filter '{"field":"x","op":"eq"}'
probe "mcp2cli echo json-array tags" $MCP2CLI --mcp-stdio "$SERVER" echo --query hi --tags '["a,b","c"]'
probe "mcp2cli echo bad integer" $MCP2CLI --mcp-stdio "$SERVER" echo --query hi --limit five
probe "mcp2cli echo bad enum" $MCP2CLI --mcp-stdio "$SERVER" echo --query hi --mode medium
probe "mcp2cli echo missing required" $MCP2CLI --mcp-stdio "$SERVER" echo --limit 5
probe "mcp2cli fail" $MCP2CLI --mcp-stdio "$SERVER" fail
probe "mcp2cli fail --json" $MCP2CLI --mcp-stdio "$SERVER" --json fail
probe "mcp2cli big" $MCP2CLI --mcp-stdio "$SERVER" big
probe "mcp2cli echo --help" $MCP2CLI --mcp-stdio "$SERVER" echo --help

echo "## mcporter 0.17.1 (key=value and function-call syntax)"
probe "mcporter echo kv" $MCPORTER call --stdio "$SERVER" --name fake echo query=hi limit=5 'tags=["a,b","c"]' mode=fast verbose=true 'filter={"field":"x","op":"eq"}'
probe "mcporter echo call-expr" $MCPORTER call --stdio "$SERVER" --name fake 'fake.echo(query: "hi", limit: 5, tags: ["a,b", "c"], filter: {field: "x", op: "eq"})'
probe "mcporter echo bad enum" $MCPORTER call --stdio "$SERVER" --name fake echo query=hi mode=medium
probe "mcporter echo missing required" $MCPORTER call --stdio "$SERVER" --name fake echo limit=5
probe "mcporter fail" $MCPORTER call --stdio "$SERVER" --name fake fail
probe "mcporter big" $MCPORTER call --stdio "$SERVER" --name fake big

echo "## apify/mcpc 0.8.0 (key:=value, sessions)"
probe "mcpc connect" $MCPC connect "$S/work/mcp_servers.json:fake" @fake
probe "mcpc echo kv" $MCPC @fake tools-call echo query:=hi limit:=5 'tags:=["a,b","c"]' mode:=fast verbose:=true 'filter:={"field":"x","op":"eq"}'
probe "mcpc echo missing required" $MCPC @fake tools-call echo limit:=5
probe "mcpc fail" $MCPC @fake tools-call fail
probe "mcpc big" $MCPC @fake tools-call big
probe "mcpc big --max-chars 1000" $MCPC --max-chars 1000 @fake tools-call big
probe "mcpc big --json" $MCPC --json @fake tools-call big
probe "mcpc grep" $MCPC @fake grep big
probe "mcpc close" $MCPC close @fake
