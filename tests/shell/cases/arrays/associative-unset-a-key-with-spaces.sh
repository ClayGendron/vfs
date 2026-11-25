# tier: language
# world: none
declare -A m
m["a b"]=1
m[c]=2
unset 'm[a b]'
echo "count=${#m[@]} a b=[${m[a b]-gone}] c=${m[c]}"
