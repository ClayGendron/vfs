# tier: language
# world: none
declare -n r=fresh
echo "before=[${fresh-unset}]"
r=made
declare -p fresh
