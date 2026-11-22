# tier: language
# world: none
r=$( { echo hello >&2 2>/dev/null; } 2>&1 )
echo "r=[$r]"
r=$( { echo hello 2>/dev/null >&2; } 2>&1 )
echo "r=[$r]"
