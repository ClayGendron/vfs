# tier: language
# world: none
declare -A m=([one]=1 [two]=2 [three]=3)
echo "one=${m[one]} two=${m[two]} three=${m[three]} count=${#m[@]}"
