# tier: language
# world: none
f() { for v in a b; do :; done; }
g() { local w; for w in c d; do :; done; }
f; g
echo "v=[$v] w=[${w-unset}]"
