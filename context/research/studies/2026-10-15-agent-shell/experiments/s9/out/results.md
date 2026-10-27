# S9 corpus results

versions: {'just-bash': '0.2.1', 'bashkit': '0.19.0'}

## just-bash-py

exit 0: 28/30

| # | command | exit | stdout (repr, first 160) | stderr (repr, first 160) |
|---|---|---|---|---|
| 1 | `echo hello` | 0 | 'hello\n' | '' |
| 2 | `ls /data` | 0 | 'config.json\nnotes.txt\npeople.csv\n' | '' |
| 3 | `ls -la /data` | 0 | '-rw-r--r--   1 user user       44 Jan  1 00:00 config.json\n-rw-r--r--   1 user user       48 Jan  1 00:00 notes.txt\n-rw-r--r--   1 user user       39 Jan  1  | '' |
| 4 | `cat /data/notes.txt` | 0 | 'alpha\nTODO fix login\nbeta\nTODO write docs\nalpha\n' | '' |
| 5 | `head -n 2 /data/notes.txt` | 0 | 'alpha\nTODO fix login\n' | '' |
| 6 | `tail -n 1 /data/notes.txt` | 0 | 'alpha\n' | '' |
| 7 | `wc -l /data/notes.txt` | 0 | '5 /data/notes.txt\n' | '' |
| 8 | `grep -n TODO /data/notes.txt` | 0 | '2:TODO fix login\n4:TODO write docs\n' | '' |
| 9 | `grep -ri "todo" /data` | 0 | '/data/notes.txt:TODO fix login\n/data/notes.txt:TODO write docs\n' | '' |
| 10 | `grep -c . /data/notes.txt` | 0 | '5\n' | '' |
| 11 | `cat /data/notes.txt \| sort \| uniq -c \| sort -rn \| head -3` | 0 | '      2 alpha\n      1 beta\n      1 TODO write docs\n' | '' |
| 12 | `find /data -name "*.json"` | 0 | '/data/config.json\n' | '' |
| 13 | `cat /data/config.json \| jq .name` | 0 | '"demo"\n' | '' |
| 14 | `jq -r '.items[] \| .id' /data/config.json` | 0 | '1\n2\n' | '' |
| 15 | `sed 's/TODO/DONE/g' /data/notes.txt` | 0 | 'alpha\nDONE fix login\nbeta\nDONE write docs\nalpha\n' | '' |
| 16 | `sed -n '2p' /data/notes.txt` | 0 | 'TODO fix login\n' | '' |
| 17 | `awk -F, '{print $2}' /data/people.csv` | 0 | 'city\nparis\nrome\n' | '' |
| 18 | `awk -F, 'NR>1 {sum+=$3} END {print sum}' /data/people.csv` | 0 | '71\n' | '' |
| 19 | `cut -d, -f1 /data/people.csv \| tr 'a-z' 'A-Z'` | 0 | 'NAME\nANN\nBOB\n' | '' |
| 20 | `for f in /data/*.txt; do echo "$f: $(wc -l < "$f")"; done` | 0 | '/data/notes.txt: 5\n' | '' |
| 21 | `cat <<EOF > /tmp/out.txt\nline one\nline two\nEOF\ncat /tmp/out.txt` | 0 | 'line one\nline two\n' | '' |
| 22 | `x=5; echo $((x * 2))` | 0 | '10\n' | '' |
| 23 | `if [ -f /data/notes.txt ]; then echo yes; else echo no; fi` | 0 | 'yes\n' | '' |
| 24 | `mkdir -p /tmp/a/b && touch /tmp/a/b/c.txt && ls -R /tmp/a` | 0 | 'b\n' | '' |
| 25 | `echo "a b c" \| xargs -n1 echo` | 0 | 'a b c\n' | '' |
| 26 | `printf '\x89PNG\r\n\x1a\n' > /tmp/image.png; od -c /tmp/image.png \| head -2` | 0 | '0000000  302 211   P   N   G  \\r  \\n 032  \\n\n0000011\n' | '' |
| 27 | `cat /tmp/image.png` | 0 | '\x89PNG\r\n\x1a\n' | '' |
| 28 | `cat /nonexistent` | 1 | '' | 'cat: /nonexistent: No such file or directory\n' |
| 29 | `nosuchcmd` | 127 | '' | 'bash: nosuchcmd: command not found\n' |
| 30 | `grep -rn "name" /data --include="*.json"; echo "exit=$?"` | 0 | '1:{"name":"demo","items":[{"id":1},{"id":2}]}\nexit=0\n' | '' |

## bashkit

exit 0: 28/30

| # | command | exit | stdout (repr, first 160) | stderr (repr, first 160) |
|---|---|---|---|---|
| 1 | `echo hello` | 0 | 'hello\n' | '' |
| 2 | `ls /data` | 0 | 'config.json\nnotes.txt\npeople.csv\n' | '' |
| 3 | `ls -la /data` | 0 | '-rw-r--r--       44 2026-10-15 23:30 config.json\n-rw-r--r--       48 2026-10-15 23:30 notes.txt\n-rw-r--r--       39 2026-10-15 23:30 people.csv\n' | '' |
| 4 | `cat /data/notes.txt` | 0 | 'alpha\nTODO fix login\nbeta\nTODO write docs\nalpha\n' | '' |
| 5 | `head -n 2 /data/notes.txt` | 0 | 'alpha\nTODO fix login\n' | '' |
| 6 | `tail -n 1 /data/notes.txt` | 0 | 'alpha\n' | '' |
| 7 | `wc -l /data/notes.txt` | 0 | '5 /data/notes.txt\n' | '' |
| 8 | `grep -n TODO /data/notes.txt` | 0 | '2:TODO fix login\n4:TODO write docs\n' | '' |
| 9 | `grep -ri "todo" /data` | 0 | '/data/notes.txt:TODO fix login\n/data/notes.txt:TODO write docs\n' | '' |
| 10 | `grep -c . /data/notes.txt` | 0 | '5\n' | '' |
| 11 | `cat /data/notes.txt \| sort \| uniq -c \| sort -rn \| head -3` | 0 | '      2 alpha\n      1 beta\n      1 TODO write docs\n' | '' |
| 12 | `find /data -name "*.json"` | 0 | '/data/config.json\n' | '' |
| 13 | `cat /data/config.json \| jq .name` | 0 | '"demo"\n' | '' |
| 14 | `jq -r '.items[] \| .id' /data/config.json` | 0 | '1\n2\n' | '' |
| 15 | `sed 's/TODO/DONE/g' /data/notes.txt` | 0 | 'alpha\nDONE fix login\nbeta\nDONE write docs\nalpha\n' | '' |
| 16 | `sed -n '2p' /data/notes.txt` | 0 | 'TODO fix login\n' | '' |
| 17 | `awk -F, '{print $2}' /data/people.csv` | 0 | 'city\nparis\nrome\n' | '' |
| 18 | `awk -F, 'NR>1 {sum+=$3} END {print sum}' /data/people.csv` | 0 | '71\n' | '' |
| 19 | `cut -d, -f1 /data/people.csv \| tr 'a-z' 'A-Z'` | 0 | 'NAME\nANN\nBOB\n' | '' |
| 20 | `for f in /data/*.txt; do echo "$f: $(wc -l < "$f")"; done` | 0 | '/data/notes.txt: 5\n' | '' |
| 21 | `cat <<EOF > /tmp/out.txt\nline one\nline two\nEOF\ncat /tmp/out.txt` | 0 | 'line one\nline two\n' | '' |
| 22 | `x=5; echo $((x * 2))` | 0 | '10\n' | '' |
| 23 | `if [ -f /data/notes.txt ]; then echo yes; else echo no; fi` | 0 | 'yes\n' | '' |
| 24 | `mkdir -p /tmp/a/b && touch /tmp/a/b/c.txt && ls -R /tmp/a` | 0 | '/tmp/a:\nb\n\n/tmp/a/b:\nc.txt\n' | '' |
| 25 | `echo "a b c" \| xargs -n1 echo` | 0 | 'a\nb\nc\n' | '' |
| 26 | `printf '\x89PNG\r\n\x1a\n' > /tmp/image.png; od -c /tmp/image.png \| head -2` | 0 | '0000000 211   P   N   G  \\r  \\n 032  \\n\n0000010\n' | '' |
| 27 | `cat /tmp/image.png` | 0 | '�PNG\r\n\x1a\n' | '' |
| 28 | `cat /nonexistent` | 1 | '' | 'cat: /nonexistent: No such file or directory\n' |
| 29 | `nosuchcmd` | 127 | '' | 'bash: line 1: nosuchcmd: command not found\n' |
| 30 | `grep -rn "name" /data --include="*.json"; echo "exit=$?"` | 0 | '/data/config.json:1:{"name":"demo","items":[{"id":1},{"id":2}]}\nexit=0\n' | '' |
