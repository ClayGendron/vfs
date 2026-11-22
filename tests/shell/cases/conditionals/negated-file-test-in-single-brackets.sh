# tier: language
# world: none
[ ! -e missing.txt ]; echo "! -e missing: $?"
: > here.txt
[ ! -e here.txt ]; echo "! -e here: $?"
