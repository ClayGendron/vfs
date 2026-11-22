# tier: language
# world: none
v="a b"
[ -n $v ]
echo "status=$?"
[[ -n $v ]]
echo "double brackets: $?"
