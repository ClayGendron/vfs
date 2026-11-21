# tier: language
# world: none
arr=(a b c d)
mapfile -t -O 1 arr <<< $'B\nC'
echo "${arr[*]}"
