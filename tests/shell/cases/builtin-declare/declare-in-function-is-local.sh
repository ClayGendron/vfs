# tier: language
# world: none
x=outside
f() { declare x=inside; echo "in f: $x"; }
f
echo "after f: $x"
