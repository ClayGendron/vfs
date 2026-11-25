# tier: language
# world: none
a=(1 2 3 4)
r=()
for (( i = ${#a[@]} - 1; i >= 0; i-- )); do r+=("${a[i]}"); done
echo "${r[*]}"
