# tier: language
# world: none
declare -A m=([k]=v)
declare -a m 2>/dev/null
echo "status=$?"
declare -p m
