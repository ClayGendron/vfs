# tier: language
# world: none
mapfile -t -n 2 arr <<< $'a\nb\nc\nd'
echo "count=${#arr[@]} ${arr[*]}"
