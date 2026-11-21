# tier: language
# world: none
( set -u; echo "in sub"; echo "$nosuch"; echo "not reached" ) 2>/dev/null
echo "subshell status=$?"
