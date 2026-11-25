# tier: language
# world: none
declare -A m=([a]=1 [b]=2 [c]=3)
unset 'm[b]'
echo "count=${#m[@]} b=[${m[b]-gone}]"
unset m
echo "after unset: count=${#m[@]}"
