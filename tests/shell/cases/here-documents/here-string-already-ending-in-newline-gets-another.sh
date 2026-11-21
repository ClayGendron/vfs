# tier: language
# world: none
v=$'line\n'
mapfile -t items <<< "$v"
echo "count=${#items[@]}"
printf '[%s]\n' "${items[@]}"
