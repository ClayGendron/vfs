# tier: language
# world: none
add() { items+=("$1"); }
items=()
add one
add "two three"
echo "count=${#items[@]} last=[${items[-1]}]"
