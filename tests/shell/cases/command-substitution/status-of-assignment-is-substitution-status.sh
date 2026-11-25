# tier: language
# world: none
x=$(false)
echo "false: $?"
x=$(exit 7)
echo "exit 7: $?"
x=$(true)
echo "true: $?"
