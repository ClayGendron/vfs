# tier: language
# world: none
set -eo pipefail
true | true
echo "ok so far"
false | true
echo "not reached"
