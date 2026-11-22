# tier: language
# world: none
set -o pipefail
(exit 2) | (exit 3) | true
echo "status=$?"
