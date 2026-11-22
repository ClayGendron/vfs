# tier: language
# world: none
f() { if false; then :; fi; }
f
echo "f returned $?"
g() { if true; then return 6; fi; }
g
echo "g returned $?"
