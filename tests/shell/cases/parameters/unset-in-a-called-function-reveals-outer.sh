# tier: language
# world: none
x=global
g() { unset x; }
f() { local x=local; g; echo "in f: [${x-unset}]"; }
f
echo "after: $x"
