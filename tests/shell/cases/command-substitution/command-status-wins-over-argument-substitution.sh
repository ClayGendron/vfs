# tier: language
# world: none
true $(exit 9)
echo "true: $?"
false $(true)
echo "false: $?"
