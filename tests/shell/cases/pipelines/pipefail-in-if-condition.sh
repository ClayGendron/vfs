# tier: language
# world: none
set -o pipefail
if false | true; then echo "then branch"; else echo "else branch"; fi
