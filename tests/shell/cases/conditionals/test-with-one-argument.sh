# tier: language
# world: none
test x; echo "x: $?"
test ""; echo "empty: $?"
test -n; echo "-n: $?"
test -z; echo "-z: $?"
test !; echo "!: $?"
test =; echo "=: $?"
test 0; echo "0: $?"
