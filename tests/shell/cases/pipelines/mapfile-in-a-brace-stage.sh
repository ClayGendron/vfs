# tier: language
# world: none
printf '%s\n' x y z | { mapfile -t arr; echo "count=${#arr[@]} middle=${arr[1]}"; }
