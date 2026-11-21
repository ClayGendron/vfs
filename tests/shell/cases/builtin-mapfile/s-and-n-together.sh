# tier: language
# world: none
mapfile -t -s 1 -n 2 arr <<< $'h\na\nb\nc'
echo "${arr[*]}"
