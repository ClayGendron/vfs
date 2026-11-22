# tier: language
# world: none
f() { echo "in f"; exit 6; }
( f; echo "not reached" )
echo "subshell status=$?"
echo "script continues"
