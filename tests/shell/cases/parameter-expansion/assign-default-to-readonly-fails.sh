# tier: language
# world: none
readonly r=
( : "${r:=x}"; echo "not reached" )
echo "status=$?"
echo "r=[$r]"
