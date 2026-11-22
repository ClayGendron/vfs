# tier: language
# world: none
x=g
f() { x=changed; local x=l; echo "local x=$x"; }
f
echo "global x=$x"
