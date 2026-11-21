# tier: language
# world: none
test ! a = a; echo "! a = a: $?"
test ! a = b; echo "! a = b: $?"
test '(' -n x ')'; echo "( -n x ): $?"
test '(' -z x ')'; echo "( -z x ): $?"
