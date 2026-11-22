# tier: language
# world: none
mapfile -t -d , parts <<< "a,b,,c"
echo "count=${#parts[@]}"
printf '[%s]\n' "${parts[@]}"
