# tier: language
# world: none
declare -A m=([a]=1 [b]=2)
m=([c]=3)
echo "count=${#m[@]} a=[${m[a]-gone}] c=${m[c]}"
