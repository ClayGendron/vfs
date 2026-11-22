# tier: language
# world: none
mapfile -t -n 0 arr <<< $'a\nb\nc'
echo "count=${#arr[@]}"
