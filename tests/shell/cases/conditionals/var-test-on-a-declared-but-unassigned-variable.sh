# tier: language
# world: none
declare d
[[ -v d ]]; echo "declare without value: $?"
d=""
[[ -v d ]]; echo "after assigning empty: $?"
