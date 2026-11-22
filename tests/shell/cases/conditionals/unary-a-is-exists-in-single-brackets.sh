# tier: language
# world: none
: > here.txt
[ -a here.txt ]; echo "-a here: $?"
[ -a missing ]; echo "-a missing: $?"
