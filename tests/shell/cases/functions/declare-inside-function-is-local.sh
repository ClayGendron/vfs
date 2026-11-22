# tier: language
# world: none
f() { declare v=inside; echo "in f: $v"; }
v=outside
f
echo "after: $v"
unset v
f
echo "unset before, after: [${v-unset}]"
