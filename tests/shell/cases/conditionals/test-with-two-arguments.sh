# tier: language
# world: none
test ! x; echo "! x: $?"
test ! ""; echo "! empty: $?"
test -z x; echo "-z x: $?"
test -n ""; echo "-n empty: $?"
test -n =; echo "-n =: $?"
