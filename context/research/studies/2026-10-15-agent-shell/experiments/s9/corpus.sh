# S9 fixed 30-command corpus. One command per line; lines starting with '#' are
# comments. Multi-line commands use '\n' escapes and are unescaped by the harness.
# Fixture files (seeded by the harness before the first command):
#   /data/notes.txt   -> "alpha\nTODO fix login\nbeta\nTODO write docs\nalpha\n"
#   /data/config.json -> {"name":"demo","items":[{"id":1},{"id":2}]}
#   /data/people.csv  -> "name,city,age\nann,paris,30\nbob,rome,41\n"
echo hello
ls /data
ls -la /data
cat /data/notes.txt
head -n 2 /data/notes.txt
tail -n 1 /data/notes.txt
wc -l /data/notes.txt
grep -n TODO /data/notes.txt
grep -ri "todo" /data
grep -c . /data/notes.txt
cat /data/notes.txt | sort | uniq -c | sort -rn | head -3
find /data -name "*.json"
cat /data/config.json | jq .name
jq -r '.items[] | .id' /data/config.json
sed 's/TODO/DONE/g' /data/notes.txt
sed -n '2p' /data/notes.txt
awk -F, '{print $2}' /data/people.csv
awk -F, 'NR>1 {sum+=$3} END {print sum}' /data/people.csv
cut -d, -f1 /data/people.csv | tr 'a-z' 'A-Z'
for f in /data/*.txt; do echo "$f: $(wc -l < "$f")"; done
cat <<EOF > /tmp/out.txt\nline one\nline two\nEOF\ncat /tmp/out.txt
x=5; echo $((x * 2))
if [ -f /data/notes.txt ]; then echo yes; else echo no; fi
mkdir -p /tmp/a/b && touch /tmp/a/b/c.txt && ls -R /tmp/a
echo "a b c" | xargs -n1 echo
printf '\x89PNG\r\n\x1a\n' > /tmp/image.png; od -c /tmp/image.png | head -2
cat /tmp/image.png
cat /nonexistent
nosuchcmd
grep -rn "name" /data --include="*.json"; echo "exit=$?"
