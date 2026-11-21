# tier: language
# world: none
: > present.txt
[[ -e present.txt ]]; echo "-e present: $?"
[[ -e absent.txt ]]; echo "-e absent: $?"
[ -e present.txt ]; echo "[ -e present ]: $?"
