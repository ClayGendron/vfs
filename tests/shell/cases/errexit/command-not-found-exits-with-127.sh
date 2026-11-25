# tier: language
# world: none
set -e
echo "before"
nosuchcommand 2>/dev/null
echo "not reached"
