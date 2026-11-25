# tier: language
# world: none
let "x = 2 + 3"
echo "x=$x"
let x = 1 2>/dev/null
echo "unquoted status: $?"
