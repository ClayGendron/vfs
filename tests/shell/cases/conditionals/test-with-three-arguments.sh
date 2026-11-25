# tier: language
# world: none
test a = a; echo "a = a: $?"
test ! -z x; echo "! -z x: $?"
test '(' x ')'; echo "( x ): $?"
test = = =; echo "= = =: $?"
test ! = !; echo "! = !: $?"
test -n = -n; echo "-n = -n: $?"
