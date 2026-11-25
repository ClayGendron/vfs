# tier: language
# world: none
: > exists.txt
[[ exists.txt -nt missing ]]; echo "exists -nt missing: $?"
[[ missing -nt exists.txt ]]; echo "missing -nt exists: $?"
[[ missing -ot exists.txt ]]; echo "missing -ot exists: $?"
[[ exists.txt -ot missing ]]; echo "exists -ot missing: $?"
