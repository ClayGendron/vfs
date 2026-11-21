# tier: language
# world: none
declare -A m=([a]=1)
m+=([b]=2 [c]=3)
echo "count=${#m[@]} b=${m[b]} c=${m[c]}"
