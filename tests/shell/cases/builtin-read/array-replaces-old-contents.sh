# tier: language
# world: none
arr=(a b c d e)
read -a arr <<< "x y"
echo "count=${#arr[@]} all=${arr[*]}"
