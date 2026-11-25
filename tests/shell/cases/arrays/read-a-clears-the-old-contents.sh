# tier: language
# world: none
arr=(old1 old2 old3 old4)
read -r -a arr <<< "new"
echo "count=${#arr[@]} values=${arr[*]}"
