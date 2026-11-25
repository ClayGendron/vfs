# tier: language
# world: none
false | true
echo "default=$?"
set -o pipefail
false | true
echo "pipefail=$?"
(exit 3) | (exit 4) | true
echo "rightmost=$?"
true | true
echo "all ok=$?"
