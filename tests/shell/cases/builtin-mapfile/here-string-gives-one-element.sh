# tier: language
# world: none
mapfile -t arr <<< "single line"
echo "count=${#arr[@]} [${arr[0]}]"
