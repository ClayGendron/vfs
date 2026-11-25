# tier: language
# world: none
test hello = hello; echo "=: $?"
test -z ""; echo "-z: $?"
test 3 -gt 2; echo "-gt: $?"
test ! -n ""; echo "!: $?"
