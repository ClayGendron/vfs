# tier: language
# world: none
true
echo "true: $?"
false
echo "false: $?"
(exit 42)
echo "exit 42: $?"
nosuchcommand 2>/dev/null
echo "not found: $?"
