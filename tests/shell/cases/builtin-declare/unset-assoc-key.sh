# tier: language
# world: none
declare -A m=([k]=1 [j]=2)
unset 'm[k]'
echo "count=${#m[@]} j=${m[j]} k=[${m[k]-unset}]"
