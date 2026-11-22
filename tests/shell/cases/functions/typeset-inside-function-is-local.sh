# tier: language
# world: none
f() { typeset v=inside; echo "in f: $v"; }
v=outside
f
echo "after: $v"
