# tier: language
# world: none
[[ -o noglob ]]; echo "noglob before: $?"
set -f
[[ -o noglob ]]; echo "noglob after set -f: $?"
set +f
[[ -o no_such_option ]]; echo "unknown option: $?"
[ -o errexit ]; echo "[ -o errexit ]: $?"
