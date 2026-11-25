# tier: language
# world: none
x=1
f() { x=changed; echo "in f: $x"; }
x=temp f
echo "after: $x"
