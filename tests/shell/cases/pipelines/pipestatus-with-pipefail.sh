# tier: language
# world: none
set -o pipefail
(exit 4) | true | (exit 2) | true
echo "status=$? pipestatus=${PIPESTATUS[*]}"
