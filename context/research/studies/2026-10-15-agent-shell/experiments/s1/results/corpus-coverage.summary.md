## Admission per parser (100 commands)

| parser | admitted | refused | % admitted |
|---|---:|---:|---:|
| bash | 100 | 0 | 100% |
| bashkit | 100 | 0 | 100% |
| just-bash | 100 | 0 | 100% |
| just-bash-py | 100 | 0 | 100% |
| lifo | 93 | 7 | 93% |
| posix | 96 | 4 | 96% |
| shlex | 100 | 0 | 100% |

## Admission per construct (commands containing the construct)

| construct | n | bash | bashkit | just-bash | just-bash-py | lifo | posix | shlex |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pipe | | 18 | 18 | 18 | 18 | 18 | 18 | 18 | 18 |
| and && | 7 | 7 | 7 | 7 | 7 | 6 | 7 | 7 |
| subshell ( ) | 7 | 7 | 7 | 7 | 7 | 4 | 6 | 7 |
| glob * | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 |
| stderr 2>&1 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 |
| redirect > | 8 | 8 | 8 | 8 | 8 | 6 | 8 | 8 |
| heredoc << | 4 | 4 | 4 | 4 | 4 | 1 | 4 | 4 |
| var $X | 13 | 13 | 13 | 13 | 13 | 11 | 12 | 13 |
| stdin < | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 |
| for loop | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| backticks | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| subst $(...) | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 |
| append >> | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| or || | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| function | 2 | 2 | 2 | 2 | 2 | 1 | 1 | 2 |
| if | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| brace {a,b} | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| test [[ | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| arith $(( | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| case | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| while loop | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| background & | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| process subst <( | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 1 |

## Refusals

### bash: 0 refused

### bashkit: 0 refused

### just-bash: 0 refused

### just-bash-py: 0 refused

### lifo: 7 refused
- 13: `cat > notes.md << 'EOF'` -> Expected Word but got RedirectIn ('<')
- 14: `cat <<EOF > config.yaml` -> Expected Word but got RedirectIn ('<')
- 37: `python3 - <<'EOF'` -> Expected Word but got RedirectIn ('<')
- 47: `diff <(sort a.txt) <(sort b.txt)` -> Expected Word but got LParen ('(')
- 71: `function greet() { echo "hi $1"; }` -> unexpected token '('
- 73: `(cd sub && make)` -> unexpected token '('
- 91: `arr=(a b c); echo "${arr[@]}"` -> unexpected token '('

### posix: 4 refused
- 47: `diff <(sort a.txt) <(sort b.txt)` -> cmd:1:6: `<` must be followed by a word
- 71: `function greet() { echo "hi $1"; }` -> cmd:1:15: the `function` builtin is a bash feature; tried parsing as posix
- 78: `ls &> /dev/null` -> cmd:1:4: `&>` redirects are a bash/mksh/zsh feature; tried parsing as posix
- 91: `arr=(a b c); echo "${arr[@]}"` -> cmd:1:5: arrays are a bash/mksh/zsh feature; tried parsing as posix

### shlex: 0 refused

