# tier: language
# world: none
declare -A m=([a]=1)
m+=([b]=2)
m[a]+=0
echo "a=${m[a]} b=${m[b]} count=${#m[@]}"
