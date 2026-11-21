# tier: language
# world: none
false | true
echo "last stage decides: $?"
true | false
echo "last stage decides: $?"
! true
echo "negated: $?"
false && echo "not printed"
false || echo "printed after a failure"
