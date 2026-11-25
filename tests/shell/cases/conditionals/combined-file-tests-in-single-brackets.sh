# tier: language
# world: none
: > f.txt
[ -e f.txt -a -f f.txt ]; echo "exists and file: $?"
[ -d f.txt -o -s f.txt ]; echo "dir or non-empty: $?"
[ ! -d f.txt -a -e f.txt ]; echo "not dir and exists: $?"
