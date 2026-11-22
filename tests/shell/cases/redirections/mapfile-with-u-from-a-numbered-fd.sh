# tier: language
# world: none
printf 'x\ny\nz\n' > f
mapfile -t -u 4 arr 4< f
echo "${#arr[@]}: ${arr[*]}"
