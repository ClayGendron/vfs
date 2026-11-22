# tier: language
# world: none
(set -o pipefail; false | true; echo "inside: $?")
false | true
echo "outside: $?"
