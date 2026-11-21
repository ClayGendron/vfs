# tier: language
# world: none
builtin nosuch_command_name 2>&1
echo "status=$?"
builtin if 2>/dev/null
echo "keyword status=$?"
