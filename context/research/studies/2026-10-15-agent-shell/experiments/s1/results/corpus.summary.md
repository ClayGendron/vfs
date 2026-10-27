## Admission per parser (100 commands)

| parser | admitted | refused | % admitted |
|---|---:|---:|---:|
| bash | 100 | 0 | 100% |
| bashkit | 100 | 0 | 100% |
| just-bash | 100 | 0 | 100% |
| just-bash-py | 100 | 0 | 100% |
| lifo | 84 | 16 | 84% |
| posix | 98 | 2 | 98% |
| shlex | 100 | 0 | 100% |

## Admission per construct (commands containing the construct)

| construct | n | bash | bashkit | just-bash | just-bash-py | lifo | posix | shlex |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pipe | | 75 | 75 | 75 | 75 | 75 | 65 | 73 | 75 |
| and && | 44 | 44 | 44 | 44 | 44 | 38 | 43 | 44 |
| subshell ( ) | 28 | 28 | 28 | 28 | 28 | 16 | 28 | 28 |
| glob * | 24 | 24 | 24 | 24 | 24 | 23 | 24 | 24 |
| stderr 2>&1 | 17 | 17 | 17 | 17 | 17 | 15 | 16 | 17 |
| redirect > | 15 | 15 | 15 | 15 | 15 | 10 | 15 | 15 |
| heredoc << | 12 | 12 | 12 | 12 | 12 | 1 | 12 | 12 |
| var $X | 13 | 13 | 13 | 13 | 13 | 11 | 12 | 13 |
| stdin < | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| for loop | 5 | 5 | 5 | 5 | 5 | 4 | 5 | 5 |
| backticks | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 |
| subst $(...) | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| append >> | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 |
| or || | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| function | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| if | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| brace {a,b} | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| test [[ | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| arith $(( | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| case | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| while loop | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| background & | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| process subst <( | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 1 |

## Refusals

### bash: 0 refused

### bashkit: 0 refused

### just-bash: 0 refused

### just-bash-py: 0 refused

### lifo: 16 refused
- 17: `cat > /tmp/x/notes.md <<'EOF'` -> Expected Word but got RedirectIn ('<')
- 18: `cd /Users/claygendron/Git/Repos/vfs && cat > context/decisions/081-the` -> Expected Word but got RedirectIn ('<')
- 19: `uv run python - <<'EOF' > /tmp/x/rungs.txt` -> Expected Word but got RedirectIn ('<')
- 20: `cd /Users/claygendron/Git/Repos/vfs && uv run python - <<'EOF' 2>&1 | ` -> Expected Word but got RedirectIn ('<')
- 33: `cat <<'EOF' > /tmp/x/probe.py` -> Expected Word but got RedirectIn ('<')
- 36: `psql "$VFS_TEST_POSTGRES_URL" <<'EOF' | head -20` -> Expected Word but got RedirectIn ('<')
- 38: `cat >> /tmp/x/journal.log <<'EOF'` -> Expected Word but got RedirectIn ('<')
- 50: `cat <<'EOF' | uv run python -` -> Expected Word but got RedirectIn ('<')
- 59: `cd /Users/claygendron/Git/Repos/vfs && (uv run pytest tests/storage -q` -> unexpected token '('
- 60: `(cd crates/vfs-core && cargo test | tail -5); echo "exit=$?"` -> unexpected token '('
- 63: `uv run python - <<'EOF' | head -c 300` -> Expected Word but got RedirectIn ('<')
- 70: `uv run python - <<'EOF'` -> Expected Word but got RedirectIn ('<')
- 73: `diff <(sort /tmp/x/a.txt) <(sort /tmp/x/b.txt) | head` -> Expected Word but got LParen ('(')
- 76: `uv run python - <<'EOF' | head` -> Expected Word but got RedirectIn ('<')
- 95: `cd ~/Git/Repos && for r in oils mvdan-sh brush; do printf "%-10s " "$r` -> TIMEOUT (parser hang)
- 97: `cd /Users/claygendron/Git/Repos/vfs` -> unexpected token '('

### posix: 2 refused
- 23: `cd /Users/claygendron/Git/Repos/vfs && scripts/ci.sh 2>&1 | tail -30; ` -> cmd:1:97: arrays are a bash/mksh/zsh feature; tried parsing as posix
- 73: `diff <(sort /tmp/x/a.txt) <(sort /tmp/x/b.txt) | head` -> cmd:1:6: `<` must be followed by a word

### shlex: 0 refused

