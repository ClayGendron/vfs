# tier: language
# world: none
items=3
more() { ((items > 0)); }
while more; do echo "item $items"; ((items--)); done
