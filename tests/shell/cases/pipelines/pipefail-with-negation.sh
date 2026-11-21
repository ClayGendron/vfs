# tier: language
# world: none
set -o pipefail
! false | true
echo "negated: $?"
! true | true
echo "negated success: $?"
