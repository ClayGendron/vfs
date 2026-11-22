# tier: language
# world: none
f() { { echo "in group"; return 5; }; echo never; }
f
echo "f returned $?"
