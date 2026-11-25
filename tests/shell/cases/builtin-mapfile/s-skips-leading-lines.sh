# tier: language
# world: none
mapfile -t -s 2 arr <<< $'skip1\nskip2\nkeep1\nkeep2'
echo "count=${#arr[@]} ${arr[*]}"
