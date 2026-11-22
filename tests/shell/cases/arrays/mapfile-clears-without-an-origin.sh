# tier: language
# world: none
arr=(a b c d e)
mapfile -t arr <<< "only"
echo "count=${#arr[@]} values=${arr[*]}"
