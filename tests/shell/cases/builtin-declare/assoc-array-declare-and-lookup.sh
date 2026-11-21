# tier: language
# world: none
declare -A m=([key]=value [other]='two words')
echo "key=${m[key]}"
echo "other=${m[other]}"
echo "count=${#m[@]}"
echo "missing=[${m[nope]-unset}]"
