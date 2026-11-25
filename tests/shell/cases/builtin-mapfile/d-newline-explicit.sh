# tier: language
# world: none
readarray -t -d $'\n' arr <<< $'p\nq'
echo "count=${#arr[@]} ${arr[*]}"
