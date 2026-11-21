# tier: language
# world: none
{ set -x; set - a b; } 2>&1
echo "count=$# first=$1"
[[ -o xtrace ]] || echo "xtrace turned off"
