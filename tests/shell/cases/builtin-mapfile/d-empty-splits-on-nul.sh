# tier: language
# world: none
mapfile -t -d '' arr < <(printf '%s\0' "one" "two words" "three")
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
