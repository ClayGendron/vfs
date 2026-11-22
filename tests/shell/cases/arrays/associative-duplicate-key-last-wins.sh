# tier: language
# world: none
declare -A m=([k]=first [k]=second)
echo "k=${m[k]} count=${#m[@]}"
