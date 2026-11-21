# tier: language
# world: none
r=$( { echo via-dev-stderr > /dev/stderr; } 2>&1 )
echo "r=[$r]"
r=$( { echo hidden > /dev/stderr; } 2>/dev/null )
echo "r=[$r]"
