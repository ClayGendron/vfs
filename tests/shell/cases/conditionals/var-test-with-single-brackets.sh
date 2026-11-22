# tier: language
# world: none
x=1
[ -v x ]; echo "[ -v x ]: $?"
test -v no_such; echo "test -v no_such: $?"
