# tier: language
# world: none
mapfile -t -d , arr <<< "a,b,c"
echo "count=${#arr[@]}"
printf '%q\n' "${arr[@]}"
