# tier: language
# world: none
x=global
unsetter() { unset x; }
f() { local x=local; unsetter; echo "in f after unsetter: [${x-unset}]"; }
f
echo "after: [${x-unset}]"
