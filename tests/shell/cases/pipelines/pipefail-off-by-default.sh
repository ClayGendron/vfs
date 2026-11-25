# tier: language
# world: none
(exit 2) | true
echo "status=$?"
[[ -o pipefail ]] && echo on || echo off
