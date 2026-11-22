# tier: language
# world: none
x=$(exit 3)$(true)
echo "a: $?"
x=$(true)$(exit 4)
echo "b: $?"
