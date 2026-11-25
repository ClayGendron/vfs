# tier: language
# world: none
x=$(exit 5)
echo "assign: $?"
x=$(exit 5) y=$(exit 6)
echo "two assigns: $?"
x=plain
echo "plain assign: $?"
