# tier: language
# world: none
set -u
[[ -v maybe ]] && echo "set" || echo "-v is safe under nounset"
echo "${maybe:-default is safe too}"
