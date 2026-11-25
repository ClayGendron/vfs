# tier: language
# world: none
test a = a -a b = b; echo "and: $?"
test a = b -o b = b; echo "or: $?"
test ! a = b -a x; echo "! ... -a x: $?"
