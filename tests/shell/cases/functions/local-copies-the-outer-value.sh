# tier: language
# world: none
x=outer
f() { local x="$x-plus"; echo "in f: $x"; }
f
echo "after: $x"
