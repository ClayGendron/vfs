# tier: language
# world: none
true | false
[[ 1 == 2 ]]
echo "cond: ${PIPESTATUS[*]}"
true | false
(( 0 ))
echo "arith: ${PIPESTATUS[*]}"
true | false
! [[ 1 == 1 ]]
echo "negated: ${PIPESTATUS[*]}"
true | false
for ((i = 0; i < 1; i++)); do false | true; done
echo "arithmetic for: ${PIPESTATUS[*]}"
