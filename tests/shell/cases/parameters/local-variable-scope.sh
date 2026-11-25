# tier: language
# world: none
x=out
f() { local x=in; echo "in f: $x"; }
f
echo "after: $x"
