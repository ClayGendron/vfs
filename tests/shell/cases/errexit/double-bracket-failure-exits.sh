# tier: language
# world: none
set -e
[[ a == a ]]
echo "first passed"
[[ a == b ]]
echo "not reached"
