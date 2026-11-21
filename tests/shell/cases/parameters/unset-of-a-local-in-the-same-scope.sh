# tier: language
# world: none
x=global
f() { local x=local; unset x; echo "in f: [${x-unset}]"; }
f
echo "after: $x"
