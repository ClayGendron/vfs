# tier: language
# world: none
[[ -o noglob ]] && echo "noglob on" || echo "noglob off"
set -f
[[ -o noglob ]] && echo "noglob on" || echo "noglob off"
set -o nounset
[[ -o nounset ]] && echo "nounset on"
set +o nounset
[[ -o nounset ]] || echo "nounset off"
