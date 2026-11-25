# tier: language
# world: none
set -o pipefail
false | true
echo "on: $?"
set +o pipefail
false | true
echo "off: $?"
