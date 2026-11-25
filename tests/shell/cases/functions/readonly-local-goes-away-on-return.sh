# tier: language
# world: none
f() { local -r x=inner; echo "in f: $x"; }
f
x=free
echo "after: $x"
