## Admission per parser (10 commands)

| parser | admitted | refused | % admitted |
|---|---:|---:|---:|
| bash | 2 | 8 | 20% |
| bashkit | 3 | 7 | 30% |
| just-bash | 7 | 3 | 70% |
| just-bash-py | 4 | 6 | 40% |
| lifo | 6 | 4 | 60% |
| posix | 2 | 8 | 20% |
| shlex | 9 | 1 | 90% |

## Admission per construct (commands containing the construct)

| construct | n | bash | bashkit | just-bash | just-bash-py | lifo | posix | shlex |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pipe | | 2 | 0 | 0 | 2 | 0 | 2 | 0 | 2 |
| and && | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 1 |
| subshell ( ) | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 1 |
| glob * | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| heredoc << | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 1 |
| var $X | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| for loop | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| subst $(...) | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 1 |
| if | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| arith $(( | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 1 |

## Refusals

### bash: 8 refused
- 1: `echo "unterminated` -> cmd:1:6: reached EOF without closing quote `"`
- 2: `if [ -f x ]; then echo yes` -> cmd:1:1: `if` statement must end with `fi`
- 3: `echo hi )` -> cmd:1:9: a command can only contain words and redirects; encountered `)`
- 4: `grep -n foo file.txt |` -> cmd:1:22: `|` must be followed by a statement
- 6: `for f in *.py; do echo $f` -> cmd:1:1: `for` statement must end with `done`
- 7: `ls && && pwd` -> cmd:1:4: `&&` must be followed by a statement
- 8: `echo $((1 +))` -> cmd:1:11: `+` must be followed by an expression
- 10: `grep -rn "def " src/ | head -20` -> cmd:2:1: `}` can only be used to close a block

### bashkit: 7 refused
- 1: `echo "unterminated` -> parse error at line 1, column 6: unexpected EOF while looking for matching `"'
- 2: `if [ -f x ]; then echo yes` -> parse error at line 2, column 1: syntax error: unexpected end of file
- 3: `echo hi )` -> parse error at line 1, column 9: syntax error near unexpected token `)'
- 4: `grep -n foo file.txt |` -> parse error at line 2, column 1: syntax error: unexpected end of file
- 6: `for f in *.py; do echo $f` -> parse error at line 2, column 1: syntax error: unexpected end of file
- 7: `ls && && pwd` -> parse error at line 1, column 7: syntax error near unexpected token `&&'
- 10: `grep -rn "def " src/ | head -20` -> parse error at line 2, column 1: syntax error near unexpected token `}'

### just-bash: 3 refused
- 1: `echo "unterminated` -> line 1: unexpected EOF while looking for matching `"'
- 2: `if [ -f x ]; then echo yes` -> Parse error at 1:27: Expected FI, got EOF
- 6: `for f in *.py; do echo $f` -> Parse error at 1:26: Expected DONE, got EOF

### just-bash-py: 6 refused
- 2: `if [ -f x ]; then echo yes` -> ParseException: Expected 'fi' to close if statement at line 1, column 27
- 3: `echo hi )` -> ParseException: Maximum parse iterations exceeded (possible infinite loop) at line 1, column 9
- 4: `grep -n foo file.txt |` -> ParseException: Expected command after pipe at line 1, column 23
- 6: `for f in *.py; do echo $f` -> ParseException: Expected 'done' to close for loop at line 1, column 26
- 7: `ls && && pwd` -> ParseException: Expected command after operator at line 1, column 7
- 10: `grep -rn "def " src/ | head -20` -> ParseException: Maximum parse iterations exceeded (possible infinite loop) at line 2, column 1

### lifo: 4 refused
- 2: `if [ -f x ]; then echo yes` -> Expected 'fi' but got ''
- 3: `echo hi )` -> unexpected token ')'
- 5: `cat <<'EOF'` -> Expected Word but got RedirectIn ('<')
- 6: `for f in *.py; do echo $f` -> Expected 'done' but got ''

### posix: 8 refused
- 1: `echo "unterminated` -> cmd:1:6: reached EOF without closing quote `"`
- 2: `if [ -f x ]; then echo yes` -> cmd:1:1: `if` statement must end with `fi`
- 3: `echo hi )` -> cmd:1:9: a command can only contain words and redirects; encountered `)`
- 4: `grep -n foo file.txt |` -> cmd:1:22: `|` must be followed by a statement
- 6: `for f in *.py; do echo $f` -> cmd:1:1: `for` statement must end with `done`
- 7: `ls && && pwd` -> cmd:1:4: `&&` must be followed by a statement
- 8: `echo $((1 +))` -> cmd:1:11: `+` must be followed by an expression
- 10: `grep -rn "def " src/ | head -20` -> cmd:2:1: `}` can only be used to close a block

### shlex: 1 refused
- 1: `echo "unterminated` -> No closing quotation

