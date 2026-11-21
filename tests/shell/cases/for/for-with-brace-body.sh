# tier: language
# world: none
for x in a b; { echo "brace body $x"; }
for ((i = 0; i < 2; i++)) { echo "c-style brace body $i"; }
